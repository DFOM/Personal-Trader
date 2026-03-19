import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from dotenv import load_dotenv

from core.config_manager import ConfigManager
from database.models import SessionLocal, TradeProposal
from execution.alpaca_executor import AlpacaExecutor


logger = logging.getLogger(__name__)
load_dotenv()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


@dataclass
class TelegramProposalPayload:
    id: int
    symbol: str
    action: str
    confidence: int
    suggested_position_size: float
    reasoning: str


class MobileCommander:
    """Asynchronous Telegram command center for staged proposal approvals."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        broadcast_interval_seconds: int = 20,
    ) -> None:
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = _to_str(chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.broadcast_interval_seconds = max(int(broadcast_interval_seconds), 5)

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required for MobileCommander.")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required for MobileCommander.")

        self.config_manager = ConfigManager()
        self.executor = AlpacaExecutor()

        self.application = Application.builder().token(self.bot_token).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CallbackQueryHandler(self._on_trade_action, pattern=r"^(approve|reject):"))
        if self.application.job_queue is not None:
            self.application.job_queue.run_repeating(
                self._broadcast_pending_job,
                interval=self.broadcast_interval_seconds,
                first=3,
                name="pending-proposal-broadcast",
            )

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized_chat(update):
            return
        if update.message:
            await update.message.reply_text(
                "✅ Mobile Commander online. Pending trade proposals will stream here."
            )

    async def _broadcast_pending_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await self.broadcast_pending_proposals()
        except Exception as exc:
            logger.exception("Telegram broadcast loop failed: %s", exc)

    async def broadcast_pending_proposals(self) -> int:
        last_notified = _to_int(self.config_manager.get_setting("telegram_last_notified_proposal_id", 0), 0)

        with SessionLocal() as session:
            proposals = (
                session.query(TradeProposal)
                .filter(TradeProposal.status == "PENDING", TradeProposal.id > last_notified)
                .order_by(TradeProposal.id.asc())
                .limit(25)
                .all()
            )

        sent_count = 0
        max_sent_id = last_notified

        for proposal in proposals:
            payload = self._normalize_proposal(proposal)
            await self.send_proposal(payload)
            sent_count += 1
            max_sent_id = max(max_sent_id, payload.id)

        if max_sent_id > last_notified:
            self.config_manager.set_setting(
                "telegram_last_notified_proposal_id",
                max_sent_id,
                description="Last TradeProposal ID sent to Telegram commander.",
            )

        return sent_count

    async def send_proposal(self, proposal: TelegramProposalPayload) -> None:
        text = self._format_proposal_message(proposal)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{proposal.id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject:{proposal.id}"),
                ]
            ]
        )

        await self.application.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    async def _on_trade_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return

        await query.answer()

        if not self._is_authorized_chat(update):
            await query.edit_message_text("⛔ Unauthorized command source.")
            return

        payload = (query.data or "").split(":", 1)
        if len(payload) != 2 or not payload[1].isdigit():
            await query.edit_message_text("⚠️ Invalid action payload.")
            return

        action, proposal_id_raw = payload
        proposal_id = int(proposal_id_raw)

        try:
            if action == "approve":
                response = self._approve_trade(proposal_id)
            elif action == "reject":
                response = self._reject_trade(proposal_id)
            else:
                response = "⚠️ Unsupported action."
        except Exception as exc:
            logger.exception("Telegram callback action failed: %s", exc)
            response = f"⚠️ Action failed due to error: {exc}"

        await query.edit_message_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    def _approve_trade(self, proposal_id: int) -> str:
        with SessionLocal() as session:
            proposal = session.get(TradeProposal, proposal_id)
            if proposal is None:
                return "⚠️ Proposal not found."

            status = _to_str(getattr(proposal, "status", "")).upper()
            if status != "PENDING":
                return f"ℹ️ Proposal already processed with status: *{status}*"

            symbol = _to_str(getattr(proposal, "symbol", ""))
            action = _to_str(getattr(proposal, "action", "")).upper()
            confidence = _to_int(getattr(proposal, "confidence", 0), 0)
            suggested_size = _to_float(getattr(proposal, "suggested_position_size", 0.0), 0.0)

            setattr(proposal, "status", "APPROVED")
            session.commit()

        side = "buy" if action == "BUY" else "sell"
        execution_response = self.executor.place_market_order(
            symbol=symbol,
            side=side,
            quantity=max(suggested_size, 0.0),
        )

        return (
            "✅ *Trade Executed Successfully*\n\n"
            f"**Asset**: `{symbol}`\n"
            f"**Action**: {'🟢 BUY' if action == 'BUY' else '🔴 SELL'}\n"
            f"**Confidence**: *{confidence}%*\n"
            f"**Position Size**: *{max(suggested_size, 0.0):.4f}*\n"
            f"**Execution Status**: *{_to_str(execution_response.get('status', 'submitted')).upper()}*"
        )

    def _reject_trade(self, proposal_id: int) -> str:
        with SessionLocal() as session:
            proposal = session.get(TradeProposal, proposal_id)
            if proposal is None:
                return "⚠️ Proposal not found."

            status = _to_str(getattr(proposal, "status", "")).upper()
            if status != "PENDING":
                return f"ℹ️ Proposal already processed with status: *{status}*"

            symbol = _to_str(getattr(proposal, "symbol", ""))
            action = _to_str(getattr(proposal, "action", "")).upper()
            confidence = _to_int(getattr(proposal, "confidence", 0), 0)

            setattr(proposal, "status", "REJECTED")
            session.commit()

        return (
            "🛑 *Trade Rejected*\n\n"
            f"**Asset**: `{symbol}`\n"
            f"**Action**: {'🟢 BUY' if action == 'BUY' else '🔴 SELL' if action == 'SELL' else '🟡 HOLD'}\n"
            f"**Confidence**: *{confidence}%*"
        )

    def run(self) -> None:
        logger.info("Starting MobileCommander polling loop.")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

    def start_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="telegram-mobile-commander", daemon=True)
        thread.start()
        logger.info("MobileCommander running in background thread.")
        return thread

    @staticmethod
    def _normalize_proposal(trade_proposal: TradeProposal) -> TelegramProposalPayload:
        return TelegramProposalPayload(
            id=_to_int(getattr(trade_proposal, "id", 0), 0),
            symbol=_to_str(getattr(trade_proposal, "symbol", "UNKNOWN")),
            action=_to_str(getattr(trade_proposal, "action", "HOLD")),
            confidence=_to_int(getattr(trade_proposal, "confidence", 0), 0),
            suggested_position_size=_to_float(getattr(trade_proposal, "suggested_position_size", 0.0), 0.0),
            reasoning=_to_str(getattr(trade_proposal, "reasoning", "No reasoning provided.")),
        )

    @staticmethod
    def _format_proposal_message(proposal: TelegramProposalPayload) -> str:
        action_upper = proposal.action.upper().strip()
        action_emoji = "🟢 BUY" if action_upper == "BUY" else "🔴 SELL" if action_upper == "SELL" else "🟡 HOLD"

        return (
            "📡 *New Pending Trade Proposal*\n\n"
            f"**ID**: `{proposal.id}`\n"
            f"**Asset**: `{proposal.symbol}`\n"
            f"**Action**: {action_emoji}\n"
            f"**Confidence**: *{proposal.confidence}%*\n"
            f"**Suggested Size**: *{proposal.suggested_position_size:.4f}*\n\n"
            "🧠 *AI Thesis*\n"
            f"{proposal.reasoning}"
        )

    def _is_authorized_chat(self, update: Update) -> bool:
        if update.effective_chat is None:
            return False
        return _to_str(update.effective_chat.id) == self.chat_id
