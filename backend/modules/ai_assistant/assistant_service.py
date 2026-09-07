import logging
import os
import re
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.brand_profile import BrandProfile
from models.chat_history import AssistantChatMessage, AssistantChatSession
from modules.ai_assistant.brand_context import build_brand_context, render_brand_block
from modules.llm_config import (
    chat_completion,
    check_raw_response,
    resolve_groq,
    reasoning_params,
)

logger = logging.getLogger(__name__)

# Key/model har call par resolve hote hain taake rate-limit failover chale —
# dekho modules/llm_config.py :: call_with_failover.
GROQ_PURPOSE = "assistant"

# ── Language guard ─────────────────────────────────────────────────
#
# Assistant sirf English ya Roman Urdu (Latin letters) mein baat karta hai.
# Prompt mein ye saaf likha hai, lekin sirf prompt kaafi nahi tha — Devanagari
# Roman Urdu ka statistical padosi hai, aur model us par phisal jata tha.
#
# Doosri (aur badtar) wajah: is chat ki purani replies history ke tor par wapas
# bheji jati hain. Ek dafa Hindi reply save ho gayi to model usay pattern samajh
# kar Hindi jaari rakhta hai — khud ko feed karne wala loop. Is liye do jagah
# guard hai: history mein Devanagari mile to prompt mein explicitly mana karte
# hain, aur output mein mile to EK corrective retry hoti hai.
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

_HISTORY_SCRIPT_NOTE = (
    "NOTE: some earlier assistant replies in this conversation are in "
    "Hindi/Devanagari script. That was a bug, not a style to follow. Ignore "
    "their script completely and reply in English or Roman Urdu (Latin letters)."
)

_RETRY_SCRIPT_NOTE = (
    "Your last reply used Hindi/Devanagari script, which is forbidden. Say the "
    "same thing again using ONLY Latin letters — English, or Roman Urdu (Urdu "
    "spelled with English letters). Do not output a single Devanagari character."
)


def has_devanagari(text: str | None) -> bool:
    """True agar text mein koi bhi Devanagari (Hindi) character hai."""
    return bool(_DEVANAGARI_RE.search(text or ""))

# ── Page contexts — keys MUST match frontend getPageContext() return values ──
PAGE_CONTEXT = {
    "improvement": """User is on the Brand Insights module. Here's how it works:
- Gathers the brand's real data: customer sentiment (pain points, loved features, emotions), SEO audit scores, keyword data, and product catalogue stats
- Sends everything to AI with a strict 'evidence-only' prompt — every suggestion MUST cite a specific data point
- Returns TWO sections: (1) Fix-it Suggestions — problems to fix, grouped by area (delivery, SEO, product quality, images, etc.), each with a clear Problem, What to do, and Evidence line; (2) Growth Opportunities — forward-looking ideas to grow sales, grounded in real data strengths/gaps
- Each card shows its evidence so the user can verify it's real, not invented
- Output language can be switched between English and Roman Urdu via a toggle — switching re-runs the analysis
- If data is missing or thin, suggestions carry a low confidence label or the module says 'not enough data yet'
- Uses a separate Groq API key to avoid rate-limit contention with the main key""",

    "sentiment": """User is on the Sentiment Analysis module. Here's how it works:
- User selects their brand from the brand switcher (same as all other modules)
- System scrapes reviews from Trustpilot AND YouTube comments for that brand
- Reviews are analyzed using a fine-tuned XLM-RoBERTa model that handles both English and Roman Urdu
- Results include: overall sentiment score (%), dominant emotion, pain points (what customers complain about), loved features (what they praise), customer desires, and per-platform breakdowns
- The brand switcher flow replaced the old 'type the brand name' input for consistency
- Common terms to explain: 'sentiment score', 'pain points', 'dominant emotion', 'XLM-RoBERTa'""",

    "seo": """User is on the SEO module. It has several sub-sections:
- Keywords: generates keyword suggestions using DataForSEO API, tailored to the brand's products and target markets
- SEO Audit: audits every product page for meta tags, title quality, image descriptions, keyword usage, and tag coverage — gives each an SEO score
- Blog: generates SEO-optimized blog articles targeting specific keywords
- Content: generates optimized meta descriptions and product copy
- Common terms to explain: 'meta description', 'keyword density', 'alt text', 'SEO score', 'DataForSEO'""",

    "ads-generation": """User is on the Ads Generation module. Here's how it works:
- User selects a product from their scraped catalogue
- User can optionally write a style prompt (e.g. 'festive red theme')
- The system uses AI to write ad copy, then composites it onto the real product photo
- IMPORTANT: If the user asks for help writing a good ad style prompt, convert their simple/layman description (in whatever language they wrote it) into a clear, descriptive English prompt. Example: user says 'acha sa shadi wala look' → you suggest: 'Elegant bridal theme, warm gold tones, festive and celebratory mood'
- This does NOT generate fake AI images — it uses their real product photo to preserve authenticity
- Generated ads are saved to a gallery for download""",

    "video-ads": """User is on the Video Ads module. Here's how it works:
- User picks a product image from their catalogue (or a previously generated image ad)
- User customizes video settings: scene description, mood, camera motion, lighting, pacing, and duration (5s/10s)
- System generates a product video ad using Kling AI via fal.ai — a realistic AI video from a single product photo
- There is also a premium tier option using Veo 3.1 for higher quality with audio
- Generated videos are saved to a gallery for download
- This turns static product photos into short video clips suitable for social media ads""",

    "scraping": """User is on the Brand Setup module. Here's how it works:
- User enters their Shopify store URL
- System extracts products, prices, descriptions, images, brand colors, logo, store country/currency automatically
- It detects the store's locale (country, currency, markets) from meta.json
- This data feeds into every other module (ads, SEO, sentiment matching, brand insights, chatbot, video ads)
- If a brand needs updating, user can re-scrape to refresh all product data""",

    "chatbot": """User is on the Customer Chatbot Automation module. Here's how it works:
- User uploads FAQs, product docs, or any reference material (PDF, text, or plain text)
- System builds a RAG (Retrieval-Augmented Generation) knowledge base from the uploaded documents
- User gets a unique embeddable chatbot widget and a <script> code snippet to paste into their website
- The chatbot answers customer questions using the uploaded knowledge
- Low-confidence queries escalate to the business owner via email alert and dashboard notification
- User can manage multiple chatbots, view conversations, and update knowledge bases""",
}


def build_system_prompt(current_page: str | None, brand_block: str = "") -> str:
    page_info = PAGE_CONTEXT.get(current_page, "User is somewhere on the BrandWave platform.")

    return f"""You are the BrandWave AI Assistant — a friendly, helpful guide inside the BrandWave marketing platform.

LANGUAGE RULE (highest priority — never break this, not even once):
- You may reply in ONLY TWO languages: English, or ROMAN URDU (Urdu written in plain Latin/English letters, e.g. "aapke brand ki reviews mein delivery ka masla sab se zyada hai").
- NEVER use Hindi. NEVER use Devanagari script (characters like आपके, ब्रांड, है). NEVER use Urdu/Arabic script (آپ کے). Every single character you output must be Latin letters, digits, or punctuation.
- Match the user's language: if they write in English, reply in English. If they write in Roman Urdu, Urdu, or anything Hindi/Urdu-like, reply in ROMAN URDU using Latin letters only.
- If the user writes in Devanagari or Urdu script, do NOT mirror their script — still answer in Roman Urdu (Latin letters).
- Brand names, product names and technical terms stay in English as-is.

Your job:
- Explain marketing concepts in simple, plain language, following the LANGUAGE RULE above
- Help users understand what each module does, its flow, and key terms
- Help convert the user's simple/layman descriptions into clear, effective prompts (especially for the Ads Generation module)
- Give general marketing best-practices and suggestions relevant to their current module
- Answer questions about the user's OWN brand, reviews, keywords, and SEO data using the real data provided below
- Keep answers short, clear, and practical
- You can answer questions about ANY module on the platform, not just the one the user is currently viewing

HONESTY RULE (very important):
- If you have real brand data below, USE it truthfully to answer questions about the user's brand, customers, reviews, keywords, etc.
- If a module has NOT been run yet (listed under "NOT RUN YET"), say so plainly and suggest running that module. NEVER invent numbers, reviews, or data that doesn't exist.
- Never guess or make up brand details you don't have. If you don't know, say "I don't have that data yet" and point them to the right module.

CONTENT POLICY (very important, always follow):
- If the user uses abusive language, insults, or asks for anything inappropriate/offensive/unrelated to marketing, do NOT respond to that content or engage with it.
- Instead, politely reply: "Main aise sawalon ka jawab nahi de sakta. Main sirf BrandWave platform aur marketing se related madad kar sakta hoon — koi aur sawal ho to zaroor poochein!"
- Stay strictly focused on marketing, business, and BrandWave platform topics only.

Current page: {page_info}
{brand_block}
Always be encouraging and concise. Reply in English or Roman Urdu ONLY — never in Hindi or Devanagari script."""

def _ensure_session(db: Session, session_id: str, user_id: str, first_message: str):
    """Session record already hai to sirf timestamp bump karo, warna naya banao with a title."""
    session = db.query(AssistantChatSession).filter(AssistantChatSession.id == session_id).first()
    if not session:
        title = first_message[:40] + ("..." if len(first_message) > 40 else "")
        session = AssistantChatSession(id=session_id, user_id=user_id, title=title)
        db.add(session)
    else:
        session.updated_at = datetime.utcnow()
    db.commit()


def get_chat_response(
    db: Session,
    user_id: str,
    session_id: str,
    message: str,
    current_page: str | None,
    brand_profile_id: int | None = None,
) -> str:
    # Build compact brand context for the system prompt (None-safe)
    brand_ctx = build_brand_context(db, user_id, brand_profile_id)
    brand_block = render_brand_block(brand_ctx)

    # Ye line diagnose karne ke liye hai: "assistant kehta hai koi brand select
    # nahi hai" wali shikayat sirf yahan se confirm hoti hai — id aayi thi ya
    # nahi, aur aayi to us user ke naam par brand mila ya nahi.
    logger.info(
        "[assistant] chat user=%s brand_profile_id=%s brand_context=%s",
        user_id,
        brand_profile_id,
        brand_ctx["brand_name"] if brand_ctx else "NONE",
    )

    history = (
        db.query(AssistantChatMessage)
        .filter(AssistantChatMessage.session_id == session_id)
        .order_by(desc(AssistantChatMessage.created_at))
        .limit(10)
        .all()
    )
    history.reverse()

    messages = [{"role": "system", "content": build_system_prompt(current_page, brand_block)}]
    for h in history:
        role = "user" if h.sender == "user" else "assistant"
        messages.append({"role": role, "content": h.message})

    # Purani Hindi replies ko model dobara copy na kare (dekho _HISTORY_SCRIPT_NOTE)
    if any(h.sender == "assistant" and has_devanagari(h.message) for h in history):
        messages.append({"role": "system", "content": _HISTORY_SCRIPT_NOTE})

    messages.append({"role": "user", "content": message})

    ASSISTANT_MAX_TOKENS = 1200

    # reasoning_params model-specific hai, is liye model yahan bhi chahiye —
    # magar sirf params banane ke liye. Asli call chat_completion karta hai,
    # jo model dobara resolve karta hai (aur failover par bhi wahi model rehta).
    _key, _model, _env = resolve_groq(GROQ_PURPOSE)

    payload = {
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": ASSISTANT_MAX_TOKENS,
        **reasoning_params(_model),
    }

    result = chat_completion(
        GROQ_PURPOSE, payload, timeout=30, what="Assistant reply"
    )
    reply = check_raw_response(result, "Assistant reply", max_tokens=ASSISTANT_MAX_TOKENS)

    # Language guard — Devanagari nikla to ek corrective retry.
    if has_devanagari(reply):
        logger.warning("[assistant] reply mein Devanagari tha — Roman Urdu mein dobara maang rahe hain")
        retry_payload = {
            **payload,
            "messages": messages + [
                {"role": "assistant", "content": reply},
                {"role": "system", "content": _RETRY_SCRIPT_NOTE},
            ],
        }
        retry_result = chat_completion(
            GROQ_PURPOSE, retry_payload, timeout=30,
            what="Assistant reply (script fix)",
        )
        retry_reply = check_raw_response(
            retry_result, "Assistant reply (script fix)", max_tokens=ASSISTANT_MAX_TOKENS
        )
        if has_devanagari(retry_reply):
            # Dono koshishein Hindi — phir bhi retry wali rakhte hain, kyunke
            # usmein correction dekha ja chuka hai; log se pata chalta hai ke
            # prompt ko mazbooti chahiye.
            logger.error("[assistant] retry ke baad bhi Devanagari — prompt review karo")
        reply = retry_reply

    # Session record banao/update karo (title first message se banega)
    _ensure_session(db, session_id, user_id, message)

    db.add(AssistantChatMessage(
        user_id=user_id, session_id=session_id, current_page=current_page,
        sender="user", message=message
    ))
    db.add(AssistantChatMessage(
        user_id=user_id, session_id=session_id, current_page=current_page,
        sender="assistant", message=reply
    ))
    db.commit()

    return reply


def get_session_history(db: Session, session_id: str, caller: str | None = None) -> list[dict]:
    # Ownership guard: if caller is provided, verify the session belongs to them.
    if caller:
        session = db.query(AssistantChatSession).filter(
            AssistantChatSession.id == session_id
        ).first()
        if session and session.user_id != caller:
            from fastapi import HTTPException
            raise HTTPException(403, "You can only view your own chat history.")

    history = (
        db.query(AssistantChatMessage)
        .filter(AssistantChatMessage.session_id == session_id)
        .order_by(AssistantChatMessage.created_at)
        .all()
    )
    return [{"sender": h.sender, "message": h.message} for h in history]


def get_user_sessions(db: Session, user_id: str) -> list[dict]:
    sessions = (
        db.query(AssistantChatSession)
        .filter(AssistantChatSession.user_id == user_id)
        .order_by(desc(AssistantChatSession.updated_at))
        .all()
    )
    return [
        {"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat()}
        for s in sessions
    ]