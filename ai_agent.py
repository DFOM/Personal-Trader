import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
from sqlalchemy.exc import SQLAlchemyError

from database.models import SessionLocal, TradeProposal


class TradeAnalystError(Exception):
    """Raised when the trade analyst fails to produce a valid decision."""


@dataclass
class TradingDecision:
    action: str
    symbol: str
    confidence_score: int
    reasoning: str
    suggested_position_size: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "symbol": self.symbol,
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning,
            "suggested_position_size": self.suggested_position_size,
        }


class TradeAnalyst:
    """Quant-style AI analyst that combines price action + news sentiment."""

    OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        request_timeout: int = 30,
        log_path: str = "logs/ai_decisions_raw.jsonl",
        price_fetcher: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> None:
        self.llm_provider = (llm_provider or os.getenv("LLM_PROVIDER", "openai")).lower().strip()
        self.model_name = model_name or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.request_timeout = request_timeout
        self.log_path = Path(log_path)
        self.price_fetcher = price_fetcher

    def fetch_price_action_24h(self, symbol: str) -> Dict[str, Any]:
        """Fetch last 24h market action for symbol using existing fetcher, with fallback."""
        if self.price_fetcher is not None:
            data = self.price_fetcher(symbol)
            if not isinstance(data, dict):
                raise TradeAnalystError("Price fetcher must return a dictionary payload.")
            return data

        existing_fetcher_data = self._try_existing_fetchers(symbol)
        if existing_fetcher_data is not None:
            return existing_fetcher_data

        return self._fetch_price_action_from_finnhub(symbol)

    def fetch_top_headlines(self, symbol: str, limit: int = 5) -> List[Dict[str, str]]:
        """Fetch top recent headlines for an asset from NewsAPI or Finnhub."""
        news_api_key = os.getenv("NEWSAPI_KEY")
        if news_api_key:
            return self._fetch_newsapi_headlines(symbol=symbol, api_key=news_api_key, limit=limit)

        finnhub_key = os.getenv("FINNHUB_API_KEY")
        if finnhub_key:
            return self._fetch_finnhub_headlines(symbol=symbol, api_key=finnhub_key, limit=limit)

        raise TradeAnalystError(
            "No news API key configured. Set NEWSAPI_KEY or FINNHUB_API_KEY in your environment."
        )

    def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        """Run full analysis and return a strict decision object."""
        market_context = self.fetch_price_action_24h(symbol)
        headlines = self.fetch_top_headlines(symbol, limit=5)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(symbol=symbol, market_data=market_context, headlines=headlines)

        raw_response = self._call_llm(system_prompt=system_prompt, user_prompt=user_prompt)
        parsed_json = self._extract_json(raw_response)
        decision = self._validate_decision(parsed_json, expected_symbol=symbol)

        self._log_raw_decision(symbol=symbol, market_data=market_context, headlines=headlines, raw_output=decision)
        return decision

    def generate_and_stage_proposal(self, symbol: str) -> Dict[str, Any]:
        """Generate AI decision and stage it in DB as PENDING for human approval."""
        decision = self.analyze_symbol(symbol)

        return self.stage_proposal(decision)

    def stage_proposal(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a validated decision to the pending approval queue."""
        required_fields = {"symbol", "action", "confidence_score", "reasoning"}
        missing = [field for field in required_fields if field not in decision]
        if missing:
            raise TradeAnalystError(f"Cannot stage proposal. Missing decision fields: {missing}")

        proposal = TradeProposal(
            symbol=decision["symbol"],
            action=decision["action"],
            confidence=decision["confidence_score"],
            reasoning=decision["reasoning"],
            status="PENDING",
        )

        try:
            with SessionLocal() as session:
                session.add(proposal)
                session.commit()
                session.refresh(proposal)
        except SQLAlchemyError as exc:
            raise TradeAnalystError(
                f"Failed to stage proposal for {decision.get('symbol', 'UNKNOWN')}: {exc}"
            ) from exc

        return {
            "proposal_id": proposal.id,
            "status": proposal.status,
            "decision": decision,
        }

    def _try_existing_fetchers(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Attempt to call a project data fetcher when available."""
        candidate_paths = [
            "app.data.fetchers",
            "data.fetchers",
            "app.data.market_data",
            "data.market_data",
        ]

        for module_path in candidate_paths:
            try:
                module = __import__(module_path, fromlist=["*"])
            except ImportError:
                continue

            for func_name in ["fetch_last_24h", "get_last_24h_price_action", "fetch_price_action_24h"]:
                func = getattr(module, func_name, None)
                if callable(func):
                    result = func(symbol)
                    if isinstance(result, dict):
                        return result
        return None

    def _fetch_price_action_from_finnhub(self, symbol: str) -> Dict[str, Any]:
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        if not finnhub_key:
            raise TradeAnalystError(
                "No price fetcher available and FINNHUB_API_KEY is not set for fallback market data."
            )

        end_time = int(datetime.now(timezone.utc).timestamp())
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())

        is_crypto = "/" in symbol
        if is_crypto:
            exchange = os.getenv("FINNHUB_CRYPTO_EXCHANGE", "BINANCE")
            normalized_symbol = self._normalize_symbol_for_finnhub(symbol)
            endpoint = "https://finnhub.io/api/v1/crypto/candle"
            params = {
                "symbol": f"{exchange}:{normalized_symbol}",
                "resolution": "60",
                "from": start_time,
                "to": end_time,
                "token": finnhub_key,
            }
            source = "finnhub-crypto"
        else:
            normalized_symbol = self._normalize_symbol_for_finnhub(symbol)
            endpoint = "https://finnhub.io/api/v1/stock/candle"
            params = {
                "symbol": normalized_symbol,
                "resolution": "60",
                "from": start_time,
                "to": end_time,
                "token": finnhub_key,
            }
            source = "finnhub-stock"

        response = requests.get(
            endpoint,
            params=params,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("s") != "ok":
            raise TradeAnalystError(f"Finnhub candle response invalid for {symbol}: {payload}")

        closes = payload.get("c", [])
        highs = payload.get("h", [])
        lows = payload.get("l", [])
        volumes = payload.get("v", [])

        if not closes:
            raise TradeAnalystError(f"No 24h price candles returned for {symbol}.")

        return {
            "source": source,
            "symbol": symbol,
            "window": "24h",
            "open": closes[0],
            "close": closes[-1],
            "high": max(highs) if highs else max(closes),
            "low": min(lows) if lows else min(closes),
            "change_pct": ((closes[-1] - closes[0]) / closes[0] * 100) if closes[0] else 0,
            "average_volume": (sum(volumes) / len(volumes)) if volumes else 0,
            "candles": len(closes),
        }

    def _fetch_newsapi_headlines(self, symbol: str, api_key: str, limit: int) -> List[Dict[str, str]]:
        query = self._news_query_from_symbol(symbol)
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max(1, min(limit, 20)),
                "apiKey": api_key,
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()

        payload = response.json()
        articles = payload.get("articles", [])[:limit]
        headlines = [
            {
                "headline": article.get("title", ""),
                "source": (article.get("source") or {}).get("name", "unknown"),
                "published_at": article.get("publishedAt", ""),
            }
            for article in articles
            if article.get("title")
        ]

        if not headlines:
            raise TradeAnalystError(f"No headlines returned from NewsAPI for {symbol}.")
        return headlines

    def _fetch_finnhub_headlines(self, symbol: str, api_key: str, limit: int) -> List[Dict[str, str]]:
        is_crypto = "/" in symbol
        normalized_symbol = self._normalize_symbol_for_finnhub(symbol)

        if is_crypto:
            response = requests.get(
                "https://finnhub.io/api/v1/news",
                params={
                    "category": "crypto",
                    "token": api_key,
                },
                timeout=self.request_timeout,
            )
        else:
            to_date = datetime.now(timezone.utc).date()
            from_date = to_date - timedelta(days=3)
            response = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": normalized_symbol,
                    "from": str(from_date),
                    "to": str(to_date),
                    "token": api_key,
                },
                timeout=self.request_timeout,
            )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, list):
            raise TradeAnalystError(f"Unexpected Finnhub news payload for {symbol}: {payload}")

        if is_crypto:
            symbol_base = symbol.split("/")[0].upper()
            filtered_payload = [
                item
                for item in payload
                if symbol_base in (item.get("headline", "").upper() + " " + item.get("summary", "").upper())
            ]
            payload = filtered_payload or payload

        headlines = []
        for item in payload[: max(1, limit)]:
            headline = item.get("headline")
            if not headline:
                continue
            headlines.append(
                {
                    "headline": headline,
                    "source": item.get("source", "finnhub"),
                    "published_at": datetime.fromtimestamp(
                        item.get("datetime", 0), tz=timezone.utc
                    ).isoformat(),
                }
            )

        if not headlines:
            raise TradeAnalystError(f"No headlines returned from Finnhub for {symbol}.")
        return headlines[:limit]

    def _build_system_prompt(self) -> str:
        return (
            "You are an institutional quantitative trading analyst. "
            "You must evaluate short-term price action and recent news sentiment for a single asset, "
            "assess directional bias and downside risk, and output ONE trading action: BUY, SELL, or HOLD. "
            "Your output must be strict JSON with this exact schema: "
            "{\"action\":\"BUY|SELL|HOLD\",\"symbol\":\"TICKER\",\"confidence_score\":1-100,"
            "\"reasoning\":\"2-3 sentence thesis\",\"suggested_position_size\":0-1}. "
            "Rules: confidence_score must be an integer 1-100; suggested_position_size is the fraction "
            "of total portfolio risk and must be between 0 and 1; keep reasoning concise and evidence-based. "
            "If signals conflict materially, prefer HOLD with lower confidence and smaller size. "
            "Return only JSON and no markdown."
        )

    def _build_user_prompt(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        headlines: List[Dict[str, str]],
    ) -> str:
        return (
            f"Asset: {symbol}\n"
            f"24h Market Data: {json.dumps(market_data, ensure_ascii=False)}\n"
            f"Recent Headlines (top 5): {json.dumps(headlines, ensure_ascii=False)}\n\n"
            "Evaluate trend strength, momentum, and sentiment direction. "
            "Then provide the required JSON decision object."
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        if self.llm_provider == "openai":
            return self._call_openai(system_prompt=system_prompt, user_prompt=user_prompt)
        if self.llm_provider == "anthropic":
            return self._call_anthropic(system_prompt=system_prompt, user_prompt=user_prompt)
        raise TradeAnalystError(
            f"Unsupported LLM_PROVIDER '{self.llm_provider}'. Use 'openai' or 'anthropic'."
        )

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise TradeAnalystError("OPENAI_API_KEY is not set.")

        response = requests.post(
            self.OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise TradeAnalystError(f"OpenAI returned no choices: {payload}")

        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise TradeAnalystError(f"OpenAI returned empty content: {payload}")
        return content

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise TradeAnalystError("ANTHROPIC_API_KEY is not set.")

        response = requests.post(
            self.ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "max_tokens": 500,
                "temperature": 0.1,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()

        payload = response.json()
        content_blocks = payload.get("content") or []
        if not content_blocks:
            raise TradeAnalystError(f"Anthropic returned empty content: {payload}")

        text = "\n".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        ).strip()
        if not text:
            raise TradeAnalystError(f"Anthropic response had no text blocks: {payload}")
        return text

    def _extract_json(self, raw_response: str) -> Dict[str, Any]:
        raw_response = raw_response.strip()
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw_response)
            if not match:
                raise TradeAnalystError("LLM response did not contain valid JSON.")
            return json.loads(match.group(0))

    def _validate_decision(self, payload: Dict[str, Any], expected_symbol: str) -> Dict[str, Any]:
        required_fields = {
            "action",
            "symbol",
            "confidence_score",
            "reasoning",
            "suggested_position_size",
        }
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise TradeAnalystError(f"LLM decision missing fields: {missing}")

        action = str(payload["action"]).upper().strip()
        if action not in {"BUY", "SELL", "HOLD"}:
            raise TradeAnalystError(f"Invalid action '{action}'.")

        symbol = str(payload["symbol"]).strip().upper()
        if symbol != expected_symbol.upper().strip():
            symbol = expected_symbol.upper().strip()

        try:
            confidence_score = int(payload["confidence_score"])
        except (TypeError, ValueError) as exc:
            raise TradeAnalystError("confidence_score must be an integer from 1 to 100.") from exc
        if confidence_score < 1 or confidence_score > 100:
            raise TradeAnalystError("confidence_score must be between 1 and 100.")

        reasoning = str(payload["reasoning"]).strip()
        if not reasoning:
            raise TradeAnalystError("reasoning cannot be empty.")

        try:
            suggested_position_size = float(payload["suggested_position_size"])
        except (TypeError, ValueError) as exc:
            raise TradeAnalystError("suggested_position_size must be numeric.") from exc
        if suggested_position_size < 0 or suggested_position_size > 1:
            raise TradeAnalystError("suggested_position_size must be between 0 and 1.")

        decision = TradingDecision(
            action=action,
            symbol=symbol,
            confidence_score=confidence_score,
            reasoning=reasoning,
            suggested_position_size=suggested_position_size,
        )
        return decision.to_dict()

    def _log_raw_decision(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        headlines: List[Dict[str, str]],
        raw_output: Dict[str, Any],
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "market_data": market_data,
            "headlines": headlines,
            "raw_output": raw_output,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _normalize_symbol_for_finnhub(symbol: str) -> str:
        normalized = symbol.upper().strip()
        if "/" in normalized:
            normalized = normalized.replace("/", "")
            if normalized.endswith("USDT"):
                return normalized
            if normalized.endswith("USD"):
                return normalized[:-3] + "USDT"
        return normalized

    @staticmethod
    def _news_query_from_symbol(symbol: str) -> str:
        symbol = symbol.upper().strip()
        if "/" in symbol:
            base = symbol.split("/")[0]
            return f"{symbol} OR {base} crypto"
        return symbol
