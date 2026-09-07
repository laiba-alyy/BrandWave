import asyncio
import os
import logging
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models.chatbot import Conversation, ChatbotInstance
from modules.chatbot_automation.ws_manager import ws_manager

load_dotenv()
logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL") or SMTP_USER

CONFIDENCE_THRESHOLD = 0.5

# Background email tasks ke strong references. Iske baghair asyncio task ko
# beech mein garbage-collect kar sakta hai (documented caveat) aur email
# khamoshi se ghayab ho jati.
_email_tasks: set[asyncio.Task] = set()


def _spawn_email(bot, conversation, reason: str) -> None:
    """Escalation email ko background mein bhejo — request ko rokay baghair."""
    task = asyncio.create_task(
        asyncio.to_thread(_send_escalation_email, bot, conversation, reason)
    )
    _email_tasks.add(task)
    task.add_done_callback(_email_tasks.discard)


def should_escalate(confidence: float) -> bool:
    """
    Escalation ka faisla ab LLM karta hai ([ESCALATE] marker), jo confidence score
    mein encode ho jata hai — yahan sirf threshold check hota hai.
    """
    return confidence < CONFIDENCE_THRESHOLD


async def escalate_conversation(
    db: Session,
    conversation_id: int,
    reason: str = "Low confidence response",
) -> Conversation:
    """Conversation ko escalated mark karta hai, email alert aur WS notification bhejta hai."""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")

    if conversation.is_escalated:
        return conversation

    conversation.is_escalated = True
    conversation.escalated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conversation)

    bot = db.query(ChatbotInstance).filter(ChatbotInstance.bot_id == conversation.bot_id).first()

    if bot:
        # SMTP call BLOCKING hai (connect + starttls + login + send, timeout=10s)
        # aur ye function async hai — pehle ye poore event loop ko rok deti thi,
        # yani har escalation par saara backend 10 second tak jam jata tha.
        #
        # Ab background task mein jati hai: customer ko jawab foran mil jata hai
        # aur email apne waqt par chali jati hai. Email ka natija request ke
        # response ko waise bhi affect nahi karta — nakami sirf log hoti hai.
        _spawn_email(bot, conversation, reason)
        await ws_manager.send_to_user(bot.user_id, {
            "type": "escalation",
            "conversation_id": conversation.id,
            "bot_id": conversation.bot_id,
            "bot_name": bot.bot_name,
            "reason": reason,
            "customer_session_id": conversation.customer_session_id,
        })

    return conversation


def _send_escalation_email(bot: ChatbotInstance, conversation: Conversation, reason: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and bot.owner_email):
        logger.warning(
            "Escalation email skipped for bot_id=%s — SMTP not configured or owner_email missing",
            bot.bot_id,
        )
        return False

    subject = f"Chatbot needs your attention — {bot.bot_name}"
    body = (
        f"A customer conversation on your chatbot \"{bot.bot_name}\" needs your attention.\n\n"
        f"Reason: {reason}\n"
        f"Conversation ID: {conversation.id}\n"
        f"Customer Session: {conversation.customer_session_id}\n\n"
        f"Log in to your BrandWave dashboard to review and respond."
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = bot.owner_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [bot.owner_email], msg.as_string())
        return True
    except Exception as e:
        logger.error("Failed to send escalation email for bot_id=%s: %s", bot.bot_id, e)
        return False
