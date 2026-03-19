import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.config_manager import ConfigManager
from database.models import SessionLocal, TradeProposal, TradeRecord
from execution import ExecutionService


st.set_page_config(
    page_title="Personal Trader | Institutional Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        :root {
            --pt-bg-primary: #060608;
            --pt-bg-secondary: #0d0d12;
            --pt-bg-card: rgba(20, 20, 30, 0.72);
            --pt-border: rgba(170, 86, 255, 0.32);
            --pt-purple: #a855f7;
            --pt-purple-soft: rgba(168, 85, 247, 0.26);
            --pt-neon-green: #39ff88;
            --pt-danger: #ff4d7d;
            --pt-text: #f4f4ff;
            --pt-muted: #b4b6ca;
        }

        .stApp {
            background:
                radial-gradient(circle at 10% 0%, rgba(168, 85, 247, 0.18), transparent 34%),
                radial-gradient(circle at 95% 5%, rgba(57, 255, 136, 0.08), transparent 28%),
                linear-gradient(160deg, #060608 0%, #09090f 55%, #0b0b13 100%);
            color: var(--pt-text);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(10,10,16,0.94) 0%, rgba(8,8,13,0.96) 100%);
            border-right: 1px solid rgba(168, 85, 247, 0.22);
            backdrop-filter: blur(10px);
        }

        [data-testid="stVerticalBlock"] [data-testid="stMetric"] {
            background: var(--pt-bg-card);
            border: 1px solid var(--pt-border);
            border-radius: 16px;
            padding: 14px 16px;
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.45), inset 0 0 0 1px rgba(255,255,255,0.02);
            backdrop-filter: blur(12px);
        }

        [data-testid="stMetric"] label,
        [data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: var(--pt-muted);
        }

        [data-testid="stMetricValue"] {
            color: var(--pt-text);
            letter-spacing: 0.3px;
        }

        [data-testid="stMetricDelta"] {
            color: var(--pt-neon-green) !important;
        }

        .stButton > button,
        [data-testid="baseButton-secondary"],
        [data-testid="baseButton-primary"] {
            border-radius: 10px !important;
            border: 1px solid rgba(168, 85, 247, 0.42) !important;
            background: linear-gradient(135deg, rgba(27, 25, 41, 0.88), rgba(46, 26, 66, 0.88)) !important;
            color: var(--pt-text) !important;
            transition: all 0.22s ease-in-out !important;
            box-shadow: 0 6px 16px rgba(106, 34, 171, 0.26);
        }

        .stButton > button:hover,
        [data-testid="baseButton-secondary"]:hover,
        [data-testid="baseButton-primary"]:hover {
            transform: translateY(-1px) scale(1.01);
            border-color: rgba(57, 255, 136, 0.65) !important;
            box-shadow: 0 10px 24px rgba(168, 85, 247, 0.42);
        }

        .stButton > button:active,
        [data-testid="baseButton-secondary"]:active,
        [data-testid="baseButton-primary"]:active {
            transform: translateY(0);
            box-shadow: 0 4px 10px rgba(168, 85, 247, 0.35);
        }

        [data-testid="stContainer"],
        [data-testid="stExpander"] {
            border-radius: 16px;
            border: 1px solid rgba(168, 85, 247, 0.24);
            background: rgba(18, 18, 28, 0.62);
            backdrop-filter: blur(12px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.36);
        }

        .terminal-card {
            background: var(--pt-bg-card);
            border: 1px solid var(--pt-border);
            border-radius: 16px;
            padding: 14px 16px;
            margin-bottom: 12px;
            box-shadow: 0 8px 26px rgba(0, 0, 0, 0.32);
        }

        .action-buy { color: var(--pt-neon-green); font-weight: 700; }
        .action-sell { color: var(--pt-danger); font-weight: 700; }
        .action-hold { color: #ffd166; font-weight: 700; }

        .section-title {
            margin-top: 2px;
            margin-bottom: 8px;
            letter-spacing: 0.3px;
            color: var(--pt-text);
            text-shadow: 0 0 14px rgba(168, 85, 247, 0.25);
        }

        .section-subtext {
            color: var(--pt-muted);
            margin-bottom: 14px;
        }

        .hud-kicker {
            margin-top: -4px;
            margin-bottom: 14px;
            color: #cfcfff;
            font-size: 0.92rem;
            opacity: 0.85;
        }

        [data-baseweb="tab-list"] {
            gap: 8px;
            background: rgba(12, 11, 20, 0.8);
            padding: 6px;
            border-radius: 12px;
            border: 1px solid rgba(168, 85, 247, 0.22);
        }

        [data-baseweb="tab"] {
            border-radius: 10px !important;
            padding: 8px 14px !important;
            color: #ccc9ff !important;
            transition: all 0.22s ease !important;
        }

        [data-baseweb="tab"]:hover {
            background: rgba(168, 85, 247, 0.18) !important;
            color: #ffffff !important;
        }

        [aria-selected="true"][data-baseweb="tab"] {
            background: linear-gradient(135deg, rgba(168,85,247,0.35), rgba(96,165,250,0.24)) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 22px rgba(112, 40, 180, 0.35);
        }

        .finance-tooltip {
            position: relative;
            display: inline-block;
            color: #d8c6ff;
            border-bottom: 1px dashed rgba(168, 85, 247, 0.7);
            cursor: help;
        }

        .finance-tooltip .finance-tooltiptext {
            visibility: hidden;
            width: 250px;
            background: rgba(10, 10, 18, 0.96);
            color: #eff0ff;
            text-align: left;
            border-radius: 10px;
            border: 1px solid rgba(168, 85, 247, 0.55);
            padding: 10px 12px;
            position: absolute;
            z-index: 999;
            bottom: 132%;
            left: 50%;
            margin-left: -125px;
            box-shadow: 0 14px 30px rgba(0,0,0,0.5);
            opacity: 0;
            transform: translateY(4px);
            transition: opacity 0.2s ease, transform 0.2s ease;
            font-size: 0.82rem;
            line-height: 1.35;
        }

        .finance-tooltip:hover .finance-tooltiptext {
            visibility: visible;
            opacity: 1;
            transform: translateY(0);
        }
    </style>
    """,
    unsafe_allow_html=True,
)


config_manager = ConfigManager()
execution_service = ExecutionService()


def _ensure_setting(key: str, default: Any, description: str) -> Any:
    current_value = config_manager.get_setting(key, default=None)
    if current_value is None:
        return config_manager.set_setting(key, default, description=description)
    return current_value


def _to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _finance_tooltip(term: str, definition: str) -> str:
    return (
        "<span class='finance-tooltip'>"
        f"{term}"
        f"<span class='finance-tooltiptext'>{definition}</span>"
        "</span>"
    )


def _initialize_ui_defaults() -> None:
    config_manager.initialize_default_settings()
    _ensure_setting(
        "daily_loss_limit",
        0.03,
        "Maximum allowable daily drawdown fraction before pause.",
    )
    _ensure_setting(
        "min_ai_confidence_threshold",
        80,
        "Minimum AI confidence required to keep a proposal in queue.",
    )
    _ensure_setting("discord_webhook_url", "", "Discord webhook URL for notifications.")
    _ensure_setting("telegram_webhook_url", "", "Telegram webhook URL for notifications.")
    _ensure_setting("report_frequency", "EOD", "Report cadence: Hourly, EOD, Weekly.")
    _ensure_setting(
        "allowed_stocks",
        ["AAPL", "MSFT", "NVDA"],
        "List of stock symbols approved for strategy execution.",
    )


def _fetch_portfolio_snapshot() -> Dict[str, float]:
    with SessionLocal() as session:
        records = session.query(TradeRecord).all()

    if not records:
        return {
            "total_account_value": 100_000.00,
            "pnl_24h": 0.00,
            "buying_power": 100_000.00,
        }

    signed_notional = np.array(
        [
            (-1 if _to_str(getattr(rec, "side", "")).upper() == "BUY" else 1)
            * _to_float(getattr(rec, "quantity", 0.0))
            * _to_float(getattr(rec, "price", 0.0))
            for rec in records
        ],
        dtype=float,
    )
    total_cashflow = signed_notional.sum()
    now_utc = datetime.now(timezone.utc)

    recent_cashflow = 0.0
    for rec in records:
        rec_ts = getattr(rec, "timestamp", None)
        if rec_ts is None:
            continue
        if rec_ts.tzinfo is None:
            rec_ts = rec_ts.replace(tzinfo=timezone.utc)
        if rec_ts >= now_utc - timedelta(hours=24):
            signed_value = (
                (-1 if _to_str(getattr(rec, "side", "")).upper() == "BUY" else 1)
                * _to_float(getattr(rec, "quantity", 0.0))
                * _to_float(getattr(rec, "price", 0.0))
            )
            recent_cashflow += signed_value

    base_value = 100_000.0
    total_account_value = base_value + total_cashflow
    buying_power = max(base_value * 0.75 - total_cashflow, 0.0)

    return {
        "total_account_value": float(total_account_value),
        "pnl_24h": float(recent_cashflow),
        "buying_power": float(buying_power),
    }


def _fetch_pending_proposals() -> List[TradeProposal]:
    with SessionLocal() as session:
        return (
            session.query(TradeProposal)
            .filter(TradeProposal.status == "PENDING")
            .order_by(TradeProposal.timestamp.asc())
            .all()
        )


def _approve_proposal(proposal_id: int) -> None:
    with SessionLocal() as session:
        proposal = session.get(TradeProposal, proposal_id)
        if proposal is None:
            st.toast(f"Proposal {proposal_id} not found.", icon="⚠️")
            return

        setattr(proposal, "status", "APPROVED")
        session.commit()

        action = _to_str(getattr(proposal, "action", "")).upper()
        symbol = _to_str(getattr(proposal, "symbol", ""))
        confidence = _to_int(getattr(proposal, "confidence", 0))

        if action in {"BUY", "SELL"}:
            try:
                execution_result = execution_service.execute_trade(
                    symbol=symbol,
                    action=action,
                    proposed_size=float(config_manager.get_setting("max_risk_per_trade", 0.02)),
                    confidence_score=confidence,
                )
                if not execution_result.get("executed"):
                    st.toast(
                        f"Approved but blocked by risk controls: {execution_result.get('reason', 'Unknown reason')}",
                        icon="⚠️",
                    )
                    return
            except Exception as exc:
                st.toast(f"Approved but execution failed: {exc}", icon="⚠️")
                return

    st.toast(f"Proposal {proposal_id} approved.", icon="✅")


def _reject_proposal(proposal_id: int) -> None:
    with SessionLocal() as session:
        proposal = session.get(TradeProposal, proposal_id)
        if proposal is None:
            st.toast(f"Proposal {proposal_id} not found.", icon="⚠️")
            return
        setattr(proposal, "status", "REJECTED")
        session.commit()
    st.toast(f"Proposal {proposal_id} rejected.", icon="🛑")


def _load_trade_records_df() -> pd.DataFrame:
    with SessionLocal() as session:
        records = (
            session.query(TradeRecord)
            .order_by(TradeRecord.timestamp.asc())
            .all()
        )

    rows = [
        {
            "id": getattr(rec, "id", None),
            "timestamp": getattr(rec, "timestamp", None),
            "symbol": _to_str(getattr(rec, "symbol", "")),
            "asset_class": _to_str(getattr(rec, "asset_class", "")),
            "side": _to_str(getattr(rec, "side", "")),
            "quantity": _to_float(getattr(rec, "quantity", 0.0)),
            "price": _to_float(getattr(rec, "price", 0.0)),
            "ai_reasoning": _to_str(getattr(rec, "ai_reasoning", "")),
        }
        for rec in records
    ]
    return pd.DataFrame(rows)


def _compute_analytics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "equity_curve": pd.DataFrame(columns=["timestamp", "equity"]),
        }

    signed = np.where(df["side"].str.upper() == "SELL", 1.0, -1.0)
    pnl_proxy = signed * df["quantity"].astype(float) * df["price"].astype(float)
    df_calc = df.copy()
    df_calc["timestamp"] = pd.to_datetime(df_calc["timestamp"], utc=True, errors="coerce")
    df_calc["pnl_proxy"] = pnl_proxy
    df_calc = df_calc.dropna(subset=["timestamp"]).sort_values("timestamp")

    wins = (df_calc["pnl_proxy"] > 0).sum()
    total = len(df_calc)
    win_rate = float((wins / total) * 100) if total > 0 else 0.0

    positive_values = np.asarray(df_calc.loc[df_calc["pnl_proxy"] > 0, "pnl_proxy"], dtype=float)
    negative_values = np.asarray(df_calc.loc[df_calc["pnl_proxy"] < 0, "pnl_proxy"], dtype=float)

    gross_profit = float(np.nan_to_num(positive_values).sum()) if positive_values.size > 0 else 0.0
    gross_loss = float(abs(np.nan_to_num(negative_values).sum())) if negative_values.size > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    df_calc["equity"] = 100_000 + df_calc["pnl_proxy"].cumsum()
    running_max = df_calc["equity"].cummax()
    drawdown = (df_calc["equity"] - running_max) / running_max
    max_drawdown = abs(float(drawdown.min())) * 100 if not drawdown.empty else 0.0

    return {
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
        "profit_factor": profit_factor if np.isfinite(profit_factor) else 999.0,
        "equity_curve": df_calc[["timestamp", "equity"]],
    }


def _fetch_ohlcv_last_30_days(symbol: str) -> pd.DataFrame:
    module_candidates = [
        "app.data.fetchers",
        "data.fetchers",
        "app.data.market_data",
        "data.market_data",
    ]
    function_candidates = ["fetch_ohlcv_30d", "get_ohlcv_30d", "fetch_ohlcv"]

    for module_name in module_candidates:
        try:
            module = __import__(module_name, fromlist=["*"])
        except ImportError:
            continue

        for function_name in function_candidates:
            function = getattr(module, function_name, None)
            if callable(function):
                data = function(symbol)
                if isinstance(data, pd.DataFrame) and not data.empty:
                    frame = data.copy()
                    if "timestamp" not in frame.columns:
                        frame = frame.reset_index().rename(columns={"index": "timestamp"})
                    return frame

    periods = 30
    idx = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq="D")
    seed = abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)
    base = 100 + (seed % 400)
    noise = rng.normal(0, 2.2, periods).cumsum()
    close = base + noise
    open_ = close + rng.normal(0, 1.1, periods)
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 1.5, periods))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 1.5, periods))
    volume = rng.integers(2_000, 50_000, size=periods)

    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def render_command_center() -> None:
    st.markdown("<h2 class='section-title'>🛰️ Command Center</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p class='section-subtext'>Live cockpit for account health and AI-generated actions requiring your approval.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='hud-kicker'>Matte-black mission HUD • Purple command accents • Neon risk signal overlays</div>",
        unsafe_allow_html=True,
    )

    snapshot = _fetch_portfolio_snapshot()
    pnl_24h = snapshot["pnl_24h"]
    exposure_pct = min(max(abs(pnl_24h) / max(snapshot["total_account_value"], 1.0) * 100, 0.0), 100.0)
    queue_count = len(_fetch_pending_proposals())

    col_1, col_2, col_3, col_4, col_5 = st.columns(5)
    col_1.metric("Total Account Value", f"${snapshot['total_account_value']:,.2f}")
    col_2.metric(
        "24h PnL 🟢",
        f"${snapshot['pnl_24h']:,.2f}",
        delta=f"{snapshot['pnl_24h']:,.2f}",
        delta_color="normal",
    )
    col_3.metric("Buying Power", f"${snapshot['buying_power']:,.2f}")
    col_4.metric("Open Queue", f"{queue_count}")
    col_5.metric("Risk Pulse", f"{exposure_pct:.2f}%")

    st.markdown("### 🤖 Pending AI Proposals")
    proposals = _fetch_pending_proposals()

    if not proposals:
        st.info("Queue clear. No pending proposals.")
        return

    for proposal in proposals:
        proposal_action = _to_str(getattr(proposal, "action", "HOLD")).upper()
        proposal_symbol = _to_str(getattr(proposal, "symbol", "UNKNOWN"))
        proposal_confidence = _to_int(getattr(proposal, "confidence", 0))
        proposal_reasoning = _to_str(getattr(proposal, "reasoning", "No reasoning provided."))

        action_class = {
            "BUY": "action-buy",
            "SELL": "action-sell",
            "HOLD": "action-hold",
        }.get(proposal_action, "action-hold")

        with st.container(border=True):
            st.markdown(
                (
                    f"<div class='terminal-card'><strong>{proposal_symbol}</strong> • "
                    f"<span class='{action_class}'>{proposal_action}</span> • "
                    f"Confidence: {proposal_confidence}%</div>"
                ),
                unsafe_allow_html=True,
            )
            st.progress(proposal_confidence / 100, text=f"Confidence Score: {proposal_confidence}%")
            st.write(proposal_reasoning)

            approve_col, reject_col = st.columns(2)
            approve_col.button(
                "Approve",
                key=f"approve_{proposal.id}",
                use_container_width=True,
                on_click=_approve_proposal,
                args=(proposal.id,),
            )
            reject_col.button(
                "Reject",
                key=f"reject_{proposal.id}",
                use_container_width=True,
                on_click=_reject_proposal,
                args=(proposal.id,),
            )


def render_deep_analytics() -> None:
    st.markdown("<h2 class='section-title'>📊 Deep Analytics</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p class='section-subtext'>Quant-grade performance diagnostics and interactive market visualizations.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        (
            "<p class='section-subtext'>"
            f"{_finance_tooltip('Max Drawdown', 'Largest percentage decline from an equity peak to a trough over a period.')}"
            " &nbsp;•&nbsp; "
            f"{_finance_tooltip('Sharpe Ratio', 'Risk-adjusted return metric: excess return divided by volatility.')}"
            " &nbsp;•&nbsp; "
            f"{_finance_tooltip('Slippage', 'Difference between expected execution price and actual fill price.')}"
            "</p>"
        ),
        unsafe_allow_html=True,
    )

    st.subheader("📈 Historical Performance")
    trade_df = _load_trade_records_df()
    metrics = _compute_analytics(trade_df)

    m1, m2, m3 = st.columns(3)
    m1.metric("Win Rate", f"{metrics['win_rate']:.2f}%")
    m2.metric("Max Drawdown", f"{metrics['max_drawdown']:.2f}%")
    m3.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")

    st.subheader("💹 Equity Curve")
    equity_curve = metrics["equity_curve"]
    fig_equity = go.Figure()
    if not equity_curve.empty:
        fig_equity.add_trace(
            go.Scatter(
                x=equity_curve["timestamp"],
                y=equity_curve["equity"],
                mode="lines",
                line=dict(color="#39ff88", width=2.4),
                fill="tozeroy",
                fillcolor="rgba(57,255,136,0.18)",
                hovertemplate="<b>Timestamp</b>: %{x}<br><b>Equity</b>: $%{y:,.2f}<extra></extra>",
                name="Equity",
            )
        )

    fig_equity.update_layout(
        template="plotly_dark",
        paper_bgcolor="#060608",
        plot_bgcolor="#0a0a10",
        font=dict(color="#e8e8ff"),
        margin=dict(l=18, r=18, t=18, b=18),
        xaxis_title="",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified",
    )
    fig_equity.update_xaxes(showgrid=False)
    fig_equity.update_yaxes(showgrid=False)
    st.plotly_chart(fig_equity, use_container_width=True)

    st.subheader("🧭 Asset Screener")
    allowed_crypto = config_manager.get_setting("allowed_crypto", ["BTC/USD", "ETH/USD"])
    allowed_stocks = config_manager.get_setting("allowed_stocks", ["AAPL", "MSFT", "NVDA"])
    traded_symbols = sorted(trade_df["symbol"].unique().tolist()) if not trade_df.empty else []

    universe = []
    for symbol in [*(allowed_crypto or []), *(allowed_stocks or []), *traded_symbols]:
        if symbol not in universe:
            universe.append(symbol)
    if not universe:
        universe = ["BTC/USD", "ETH/USD", "AAPL"]

    selected_asset = st.selectbox("Select Asset", universe)
    ohlcv_df = _fetch_ohlcv_last_30_days(selected_asset)
    ohlcv_df["timestamp"] = pd.to_datetime(ohlcv_df["timestamp"], utc=True, errors="coerce")
    ohlcv_df = ohlcv_df.dropna(subset=["timestamp"]).sort_values("timestamp")
    ohlcv_df["sma_20"] = ohlcv_df["close"].rolling(20, min_periods=1).mean()

    fig_candle = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.72, 0.28],
        subplot_titles=(f"{selected_asset} Price Action", "Volume"),
    )
    fig_candle.add_trace(
        go.Candlestick(
            x=ohlcv_df["timestamp"],
            open=ohlcv_df["open"],
            high=ohlcv_df["high"],
            low=ohlcv_df["low"],
            close=ohlcv_df["close"],
            increasing_line_color="#39ff88",
            decreasing_line_color="#ff4d7d",
            increasing_fillcolor="#39ff88",
            decreasing_fillcolor="#ff4d7d",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Open: %{open:$,.2f}<br>"
                "High: %{high:$,.2f}<br>"
                "Low: %{low:$,.2f}<br>"
                "Close: %{close:$,.2f}<extra></extra>"
            ),
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    fig_candle.add_trace(
        go.Scatter(
            x=ohlcv_df["timestamp"],
            y=ohlcv_df["sma_20"],
            mode="lines",
            line=dict(color="#b072ff", width=2),
            name="SMA(20)",
            hovertemplate="<b>%{x}</b><br>SMA20: $%{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig_candle.add_trace(
        go.Bar(
            x=ohlcv_df["timestamp"],
            y=ohlcv_df["volume"],
            marker_color="rgba(168,85,247,0.55)",
            hovertemplate="<b>%{x}</b><br>Volume: %{y:,.0f}<extra></extra>",
            name="Volume",
        ),
        row=2,
        col=1,
    )
    fig_candle.update_layout(
        template="plotly_dark",
        paper_bgcolor="#060608",
        plot_bgcolor="#0a0a10",
        font=dict(color="#ececff"),
        margin=dict(l=18, r=18, t=18, b=18),
        xaxis_title="",
        yaxis_title="Price",
        yaxis2_title="Volume",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig_candle.update_xaxes(showgrid=False)
    fig_candle.update_yaxes(showgrid=False, row=1, col=1)
    fig_candle.update_yaxes(showgrid=False, row=2, col=1)
    st.plotly_chart(fig_candle, use_container_width=True)

    st.subheader("🧾 Trade History")
    if trade_df.empty:
        st.info("No trade records available yet.")
    else:
        display_df = trade_df.copy()
        display_df["timestamp"] = pd.to_datetime(display_df["timestamp"], utc=True, errors="coerce")
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "timestamp": st.column_config.DatetimeColumn("Timestamp", format="YYYY-MM-DD HH:mm:ss"),
                "price": st.column_config.NumberColumn("Price", format="$%.2f"),
                "quantity": st.column_config.NumberColumn("Quantity", format="%.4f"),
                "ai_reasoning": st.column_config.TextColumn("AI Reasoning", width="large"),
            },
        )


def _on_system_active_toggle() -> None:
    enabled = bool(st.session_state.get("system_active_toggle", False))
    config_manager.set_setting(
        "is_trading_active",
        enabled,
        description="Global switch to enable or disable live/paper trade execution.",
    )
    status_text = "enabled" if enabled else "disabled"
    icon = "✅" if enabled else "⛔"
    st.toast(f"Trading system {status_text}.", icon=icon)


def render_mission_control() -> None:
    st.markdown("<h2 class='section-title'>🛡️ Mission Control</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p class='section-subtext'>Administrative controls for system state, risk posture, and operator communications.</p>",
        unsafe_allow_html=True,
    )

    current_system_active = bool(config_manager.get_setting("is_trading_active", False))
    st.session_state["system_active_toggle"] = current_system_active

    st.toggle(
        "SYSTEM ACTIVE (Trading Enabled)",
        key="system_active_toggle",
        on_change=_on_system_active_toggle,
    )

    st.markdown("### Risk Parameters")
    with st.container(border=True):
        max_risk_fraction = float(config_manager.get_setting("max_risk_per_trade", 0.02))
        daily_loss_fraction = float(config_manager.get_setting("daily_loss_limit", 0.03))

        max_risk_pct = st.slider(
            "Max Portfolio Risk per Trade (%)",
            min_value=0.1,
            max_value=10.0,
            value=float(round(max_risk_fraction * 100, 2)),
            step=0.1,
        )
        daily_loss_pct = st.slider(
            "Daily Loss Limit (%)",
            min_value=0.5,
            max_value=20.0,
            value=float(round(daily_loss_fraction * 100, 2)),
            step=0.5,
        )

    st.markdown("### AI Tuners")
    min_confidence = int(config_manager.get_setting("min_ai_confidence_threshold", 80))
    confidence_threshold = st.slider(
        "Minimum AI Confidence Threshold",
        min_value=50,
        max_value=100,
        value=min_confidence,
        step=1,
    )

    st.markdown("### Notification Hub")
    discord_webhook = st.text_input(
        "Discord Webhook URL",
        value=str(config_manager.get_setting("discord_webhook_url", "")),
        placeholder="https://discord.com/api/webhooks/...",
    )
    telegram_webhook = st.text_input(
        "Telegram Webhook URL",
        value=str(config_manager.get_setting("telegram_webhook_url", "")),
        placeholder="https://api.telegram.org/bot...",
    )
    report_frequency = st.selectbox(
        "Report Frequency",
        ["Hourly", "EOD", "Weekly"],
        index=["Hourly", "EOD", "Weekly"].index(
            str(config_manager.get_setting("report_frequency", "EOD"))
            if str(config_manager.get_setting("report_frequency", "EOD")) in ["Hourly", "EOD", "Weekly"]
            else "EOD"
        ),
    )

    if st.button("Save Configuration", type="primary", use_container_width=True):
        config_manager.set_setting(
            "max_risk_per_trade",
            max_risk_pct / 100,
            description="Maximum account risk allocated to any single trade.",
        )
        config_manager.set_setting(
            "daily_loss_limit",
            daily_loss_pct / 100,
            description="Maximum allowable daily drawdown fraction before pause.",
        )
        config_manager.set_setting(
            "min_ai_confidence_threshold",
            int(confidence_threshold),
            description="Minimum AI confidence required to keep a proposal in queue.",
        )
        config_manager.set_setting(
            "discord_webhook_url",
            discord_webhook.strip(),
            description="Discord webhook URL for notifications.",
        )
        config_manager.set_setting(
            "telegram_webhook_url",
            telegram_webhook.strip(),
            description="Telegram webhook URL for notifications.",
        )
        config_manager.set_setting(
            "report_frequency",
            report_frequency,
            description="Report cadence: Hourly, EOD, Weekly.",
        )
        st.toast("Configuration saved.", icon="💾")


def main() -> None:
    _initialize_ui_defaults()

    with st.sidebar:
        st.markdown("## 🚀 Personal Trader")
        st.caption("Immersive Institutional Command Surface")
        selected_view = st.radio(
            "Navigation",
            options=["🛰️ Command Center", "📊 Deep Analytics", "🛡️ Mission Control"],
            label_visibility="collapsed",
        )
        st.divider()
        database_url = "Configured" if SessionLocal else "Unavailable"
        st.caption(f"Database: {database_url}")
        st.caption(f"UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")

    if selected_view == "🛰️ Command Center":
        render_command_center()
    elif selected_view == "📊 Deep Analytics":
        render_deep_analytics()
    else:
        render_mission_control()


if __name__ == "__main__":
    main()
