import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from core.config_manager import ConfigManager
from database.models import SessionLocal, TradeProposal
from execution import ExecutionService


logger = logging.getLogger(__name__)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
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
    reasoning: str


class MobileCommander:
    """Telegram mobile command surface for approving/rejecting staged trade proposals."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = str(chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required for MobileCommander.")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required for MobileCommander.")

        self.config_manager = ConfigManager()
        self.execution_service = ExecutionService()
        self.application = Application.builder().token(self.bot_token).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CallbackQueryHandler(self._on_trade_action, pattern=r"^(approve|reject):"))

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized_chat(update):
            return
        if update.message:
            await update.message.reply_text(
                "✅ Mobile Commander connected. You will receive staged trade proposals here."
            )

    async def send_proposal(self, trade_proposal: Any) -> None:
        payload = self._normalize_proposal(trade_proposal)
        text = self._format_proposal_message(payload)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{payload.id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject:{payload.id}"),
                ]
            ]
        )

        await self.application.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    def send_proposal_sync(self, trade_proposal: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.send_proposal(trade_proposal))
        except RuntimeError:
            asyncio.run(self.send_proposal(trade_proposal))

    async def _on_trade_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return

        await query.answer()

        if not self._is_authorized_chat(update):
            await query.edit_message_text("⛔ Unauthorized command source.")
            return

        payload = (query.data or "").split(":", 1)
        if len(payload) != 2:
            await query.edit_message_text("⚠️ Invalid action payload.")
            return

        action, proposal_id_raw = payload
        if not proposal_id_raw.isdigit():
            await query.edit_message_text("⚠️ Invalid proposal ID.")
            return

        proposal_id = int(proposal_id_raw)
        if action == "approve":
            message = self._approve_trade(proposal_id)
        elif action == "reject":
            message = self._reject_trade(proposal_id)
        else:
            message = "⚠️ Unsupported action."

        await query.edit_message_text(message, parse_mode="Markdown", disable_web_page_preview=True)

    def _approve_trade(self, proposal_id: int) -> str:
        with SessionLocal() as session:
            proposal = session.get(TradeProposal, proposal_id)
            if proposal is None:
                return "⚠️ Proposal not found."

            proposal_status = _to_str(getattr(proposal, "status", ""))
            if proposal_status.upper() != "PENDING":
                return f"ℹ️ Proposal already processed with status: *{proposal_status}*"

            setattr(proposal, "status", "APPROVED")
            session.commit()

            symbol = _to_str(getattr(proposal, "symbol", ""))
            action = _to_str(getattr(proposal, "action", ""))
            confidence = _to_int(getattr(proposal, "confidence", 0))

            execution_result = self.execution_service.execute_trade(
                symbol=symbol,
                action=action,
                proposed_size=float(self.config_manager.get_setting("max_risk_per_trade", 0.02)),
                confidence_score=confidence,
            )

        if execution_result.get("executed"):
            return (
                "✅ *Trade Executed*\n"
                f"Asset: `{symbol}`\n"
                f"Action: *{action}*\n"
                f"Confidence: *{confidence}%*"
            )

        return (
            "⚠️ *Trade Approved but Blocked*\n"
            f"Asset: `{symbol}`\n"
            f"Reason: {execution_result.get('reason', 'Unknown risk or execution error')}"
        )

    def _reject_trade(self, proposal_id: int) -> str:
        with SessionLocal() as session:
            proposal = session.get(TradeProposal, proposal_id)
            if proposal is None:
                return "⚠️ Proposal not found."

            proposal_status = _to_str(getattr(proposal, "status", ""))
            if proposal_status.upper() != "PENDING":
                return f"ℹ️ Proposal already processed with status: *{proposal_status}*"

            symbol = _to_str(getattr(proposal, "symbol", ""))
            action = _to_str(getattr(proposal, "action", ""))
            confidence = _to_int(getattr(proposal, "confidence", 0))

            setattr(proposal, "status", "REJECTED")
            session.commit()

            return (
                "🛑 *Trade Rejected*\n"
                f"Asset: `{symbol}`\n"
                f"Action: *{action}*\n"
                f"Confidence: *{confidence}%*"
            )

    def run(self) -> None:
        logger.info("Starting MobileCommander Telegram polling...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

    def start_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="telegram-mobile-commander", daemon=True)
        thread.start()
        logger.info("MobileCommander started in background thread.")
        return thread

    def _normalize_proposal(self, trade_proposal: Any) -> TelegramProposalPayload:
        if isinstance(trade_proposal, TradeProposal):
            return TelegramProposalPayload(
                id=_to_int(getattr(trade_proposal, "id", 0)),
                symbol=_to_str(getattr(trade_proposal, "symbol", "UNKNOWN")),
                action=_to_str(getattr(trade_proposal, "action", "HOLD")),
                confidence=_to_int(getattr(trade_proposal, "confidence", 0)),
                reasoning=_to_str(getattr(trade_proposal, "reasoning", "No reasoning provided.")),
            )

        if isinstance(trade_proposal, dict):
            return TelegramProposalPayload(
                id=_to_int(trade_proposal.get("id") or trade_proposal.get("proposal_id"), 0),
                symbol=_to_str(trade_proposal.get("symbol", "UNKNOWN")),
                action=_to_str(trade_proposal.get("action", "HOLD")),
                confidence=_to_int(trade_proposal.get("confidence") or trade_proposal.get("confidence_score") or 0, 0),
                reasoning=_to_str(trade_proposal.get("reasoning", "No reasoning provided.")),
            )

        raise TypeError("trade_proposal must be a TradeProposal model instance or dict-like payload.")

    def _format_proposal_message(self, proposal: TelegramProposalPayload) -> str:
        action_upper = proposal.action.upper().strip()
        action_emoji = "🟢" if action_upper == "BUY" else "🔴" if action_upper == "SELL" else "🟡"

        return (
            "📡 *New AI Trade Proposal*\n"
            f"ID: `{proposal.id}`\n"
            f"Asset: `{proposal.symbol}`\n"
            f"Action: {action_emoji} *{action_upper}*\n"
            f"Confidence: *{proposal.confidence}%*\n\n"
            "🧠 *Reasoning*\n"
            f"{proposal.reasoning}"
        )

    def _is_authorized_chat(self, update: Update) -> bool:
        if update.effective_chat is None:
            return False
        return str(update.effective_chat.id) == self.chat_id
