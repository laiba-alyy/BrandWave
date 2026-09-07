import asyncio
import logging
import os
import uuid
from pathlib import Path

from fastapi import (
    APIRouter, Depends, HTTPException, Request, UploadFile, File,
    WebSocket, WebSocketDisconnect,
)
from sqlalchemy.orm import Session

from database.connection import get_db
from models.brand_profile import BrandProfile
from models.chatbot import ChatbotInstance, Conversation, Message, UploadedDocument
from modules.chatbot_automation.schemas import (
    CreateChatbotRequest,
    UpdateChatbotRequest,
    ChatRequest,
    UploadTextRequest,
    UploadFaqRequest,
)
from modules.chatbot_automation.document_processor import extract_text, chunk_text
from modules.chatbot_automation.embeddings_service import generate_embeddings
from modules.chatbot_automation.pinecone_service import store_embeddings, delete_bot_data, delete_vectors
from modules.chatbot_automation.rag_service import get_response
from modules.chatbot_automation.escalation_service import should_escalate, escalate_conversation
from modules.chatbot_automation.ws_manager import ws_manager
from modules.store_locale import store_country
from modules.auth import get_current_user, require_owner, verify_access_token

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
VALID_STATUSES = {"active", "paused", "draft"}


# ── Health Check ──────────────────────────────
@router.get("/health")
def health_check():
    return {"status": "Chatbot automation module is running ✅"}


# ── Create Chatbot ────────────────────────────
@router.post("/create")
def create_chatbot(request: CreateChatbotRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    if not request.bot_name.strip():
        raise HTTPException(status_code=400, detail="Chatbot name cannot be empty")

    status = request.status if request.status in VALID_STATUSES else "active"
    traits = request.personality_traits or []

    # brand_profile_id diya ho to verify karo ke wo brand isi user ka hai —
    # warna bot doosre account ke brand se link ho jayega.
    if request.brand_profile_id is not None:
        owns = db.query(BrandProfile).filter(
            BrandProfile.id == request.brand_profile_id,
            BrandProfile.user_id == caller,
        ).first()
        if not owns:
            raise HTTPException(
                status_code=404,
                detail=f"Brand profile {request.brand_profile_id} not found for this account.",
            )

    bot = ChatbotInstance(
        bot_id=str(uuid.uuid4()),
        user_id=caller,
        brand_profile_id=request.brand_profile_id,
        bot_name=request.bot_name.strip(),
        description=request.description,
        category=request.category or "custom",
        personality=_compose_personality(request.tone, traits, request.personality),
        tone=request.tone or "professional",
        personality_traits=traits,
        custom_prompt=request.custom_prompt,
        welcome_message=request.welcome_message or "Hello! How can I help you today?",
        primary_color=request.primary_color,
        owner_email=request.owner_email,
        status=status,
        is_active=status == "active",
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)

    return {"success": True, "message": "Chatbot created successfully!", "data": _serialize_bot(bot, db)}


# ── Get Active Bot For A User (dashboard status) ──
@router.get("/my-bot/{user_id}")
def get_my_bot(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    bot = (
        db.query(ChatbotInstance)
        .filter(ChatbotInstance.user_id == user_id)
        .order_by(ChatbotInstance.created_at.desc())
        .first()
    )
    if not bot:
        return {"success": True, "data": None}
    return {"success": True, "data": _serialize_bot(bot, db)}


# ── All Bots For A User — With Stats ─────────
@router.get("/my-bots/{user_id}")
def get_my_bots(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    bots = (
        db.query(ChatbotInstance)
        .filter(ChatbotInstance.user_id == user_id)
        .order_by(ChatbotInstance.created_at.desc())
        .all()
    )
    return {"success": True, "data": [_serialize_bot(bot, db) for bot in bots]}


# ── Single Bot ────────────────────────────────
@router.get("/bot/{bot_id}")
def get_bot(bot_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")
    return {"success": True, "data": _serialize_bot(bot, db)}


# ── Update Bot Settings ───────────────────────
@router.patch("/{bot_id}")
def update_chatbot(bot_id: str, request: UpdateChatbotRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    if request.bot_name is not None:
        if not request.bot_name.strip():
            raise HTTPException(status_code=400, detail="Chatbot name cannot be empty")
        bot.bot_name = request.bot_name.strip()
    if request.description is not None:
        bot.description = request.description
    if request.category is not None:
        bot.category = request.category
    if request.tone is not None:
        bot.tone = request.tone
    if request.personality_traits is not None:
        bot.personality_traits = request.personality_traits
    if request.custom_prompt is not None:
        bot.custom_prompt = request.custom_prompt
    if request.welcome_message is not None:
        bot.welcome_message = request.welcome_message
    if request.primary_color is not None:
        bot.primary_color = request.primary_color
    if request.owner_email is not None:
        bot.owner_email = request.owner_email
    if request.brand_profile_id is not None:
        bot.brand_profile_id = request.brand_profile_id

    # Tone/traits badlein to personality string dobara compose ho jaye —
    # RAG prompt isi string ko use karta hai.
    if request.personality is not None:
        bot.personality = request.personality
    elif request.tone is not None or request.personality_traits is not None:
        bot.personality = _compose_personality(bot.tone, bot.personality_traits or [], None)

    # status aur is_active hamesha in sync rehte hain
    if request.status is not None:
        if request.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Status must be active, paused, or draft")
        bot.status = request.status
        bot.is_active = request.status == "active"
    elif request.is_active is not None:
        bot.is_active = request.is_active
        bot.status = "active" if request.is_active else "paused"

    db.commit()
    db.refresh(bot)

    return {"success": True, "message": "Chatbot updated successfully!", "data": _serialize_bot(bot, db)}


# ── Duplicate Bot — Settings Only, Knowledge Base Nahi ──
@router.post("/{bot_id}/duplicate")
def duplicate_chatbot(bot_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    original = _get_bot_or_404(bot_id, db)
    if original.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    copy = ChatbotInstance(
        bot_id=str(uuid.uuid4()),
        user_id=original.user_id,
        brand_profile_id=original.brand_profile_id,
        bot_name=f"{original.bot_name} (Copy)",
        description=original.description,
        category=original.category,
        personality=original.personality,
        tone=original.tone,
        personality_traits=list(original.personality_traits or []),
        custom_prompt=original.custom_prompt,
        welcome_message=original.welcome_message,
        primary_color=original.primary_color,
        owner_email=original.owner_email,
        # Copy draft mein aata hai — knowledge base khali hai, isliye live nahi karna chahiye.
        status="draft",
        is_active=False,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)

    return {
        "success": True,
        "message": "Chatbot duplicated — knowledge base is not copied",
        "data": _serialize_bot(copy, db),
    }


# ── Delete Bot — DB Rows + Pinecone Namespace ──
@router.delete("/{bot_id}")
def delete_chatbot(bot_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    _clear_pinecone_namespace(bot_id)

    conversation_ids = [
        row.id for row in db.query(Conversation.id).filter(Conversation.bot_id == bot_id).all()
    ]
    if conversation_ids:
        db.query(Message).filter(Message.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.bot_id == bot_id).delete(synchronize_session=False)
    db.query(UploadedDocument).filter(UploadedDocument.bot_id == bot_id).delete(synchronize_session=False)
    db.delete(bot)
    db.commit()

    return {"success": True, "message": "Chatbot deleted successfully", "bot_id": bot_id}


# ── Uploaded Documents Of A Bot ───────────────
@router.get("/documents/{bot_id}")
def get_documents(bot_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    documents = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.bot_id == bot_id)
        .order_by(UploadedDocument.uploaded_at.desc())
        .all()
    )

    return {
        "success": True,
        "data": [_serialize_document(d) for d in documents],
        "total_chunks": sum(d.chunks_stored or 0 for d in documents),
    }


# ── Delete ONE Document + Uske Vectors ────────
# NOTE: ye route `/documents/{bot_id}` se PEHLE register hona zaroori hai —
# `{doc_id}` int-constrained hai, isliye numeric path yahan match hota hai
# aur bot_id (uuid string) neeche wale legacy route par jata hai.
@router.delete("/documents/{doc_id:int}")
def delete_document(doc_id: int, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    # Ownership: verify the bot belongs to the caller
    bot = db.query(ChatbotInstance).filter(ChatbotInstance.bot_id == document.bot_id).first()
    if not bot or bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    vector_ids = document.vector_ids or []
    vectors_removed = 0
    if vector_ids:
        try:
            vectors_removed = delete_vectors(document.bot_id, vector_ids)
        except Exception:
            # Pinecone down ho to bhi DB row hatani hai — warna ghost document
            # dashboard mein phansa reh jayega.
            pass

    bot_id = document.bot_id
    filename = document.filename
    db.delete(document)
    db.commit()

    return {
        "success": True,
        "message": f"Deleted {filename}",
        "bot_id": bot_id,
        "vectors_removed": vectors_removed,
        # Purane documents (is feature se pehle upload hue) ke paas vector ids nahi
        # hain — unke vectors namespace mein reh jate hain jab tak KB clear na ho.
        "legacy_vectors": not vector_ids,
    }


# ── Clear Knowledge Base — Wipe Pinecone Namespace ──
@router.delete("/knowledge-base/{bot_id}")
def clear_knowledge_base(bot_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    _clear_pinecone_namespace(bot_id)
    removed = db.query(UploadedDocument).filter(UploadedDocument.bot_id == bot_id).delete(synchronize_session=False)
    db.commit()

    return {
        "success": True,
        "message": f"Knowledge base cleared — removed {removed} document(s)",
        "documents_removed": removed,
    }


# ── Legacy Alias — purane clients ke liye ─────
@router.delete("/documents/{bot_id}")
def clear_knowledge_base_legacy(bot_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    # Keyword args zaroori hain — clear_knowledge_base ka doosra param ab
    # `caller` hai, to positional call Session ko caller ki jagah bhej deta tha.
    return clear_knowledge_base(bot_id, caller=caller, db=db)


# ── Upload Document — Process & Store in Pinecone ──
@router.post("/upload/{bot_id}")
async def upload_document(bot_id: str, caller: str = Depends(get_current_user), file: UploadFile = File(...), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT.")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    try:
        text = extract_text(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in this file.")

    document = _store_knowledge(
        db=db,
        bot_id=bot_id,
        text=text,
        filename=file.filename,
        file_type=ext.lstrip("."),
        file_size=len(file_bytes),
        source_type="document",
    )

    return {
        "success": True,
        "message": f"Processed and stored {document.chunks_stored} chunks from {file.filename}",
        "chunks_stored": document.chunks_stored,
        "document": _serialize_document(document),
    }


# ── Upload Raw Text ───────────────────────────
@router.post("/upload-text/{bot_id}")
def upload_text(bot_id: str, request: UploadTextRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    text = (request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    title = (request.title or "").strip() or "Pasted text"
    document = _store_knowledge(
        db=db,
        bot_id=bot_id,
        text=text,
        filename=title,
        file_type="text",
        file_size=len(text.encode("utf-8")),
        source_type="text",
    )

    return {
        "success": True,
        "message": f"Stored {document.chunks_stored} chunks from pasted text",
        "chunks_stored": document.chunks_stored,
        "document": _serialize_document(document),
    }


# ── Upload FAQ Pairs ──────────────────────────
@router.post("/upload-faq/{bot_id}")
def upload_faq(bot_id: str, request: UploadFaqRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    pairs = [
        (faq.question.strip(), faq.answer.strip())
        for faq in (request.faqs or [])
        if faq.question and faq.question.strip() and faq.answer and faq.answer.strip()
    ]
    if not pairs:
        raise HTTPException(status_code=400, detail="At least one complete question and answer is required")

    # Har FAQ ko Q/A block bana kar bhejte hain — retrieval ke waqt question aur
    # answer ek hi chunk mein rehte hain to match zyada accurate hota hai.
    text = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in pairs)

    title = (request.title or "").strip() or f"FAQ ({len(pairs)} entries)"
    document = _store_knowledge(
        db=db,
        bot_id=bot_id,
        text=text,
        filename=title,
        file_type="faq",
        file_size=len(text.encode("utf-8")),
        source_type="faq",
    )

    return {
        "success": True,
        "message": f"Stored {len(pairs)} FAQ entries",
        "chunks_stored": document.chunks_stored,
        "faqs_stored": len(pairs),
        "document": _serialize_document(document),
    }


# ── Embed Script Tag ──────────────────────────
@router.get("/embed/{bot_id}")
def get_embed_code(
    bot_id: str,
    request: Request,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot_or_404(bot_id, db)
    if bot.user_id != caller:
        raise HTTPException(403, "You can only access your own chatbots.")

    # Ye snippet merchant apni ASLI Shopify store par paste karta hai, is liye
    # ismein aisa URL hona chahiye jo internet se reachable ho.
    #
    # Pehle ye seedha BACKEND_PUBLIC_URL par tha, jiski default
    # "http://localhost:8000" hai — yani deploy ke baad bhi, jab tak koi wo env
    # var set na kare, har merchant ko aisa script tag milta tha jo unki site
    # par kabhi kaam hi nahi kar sakta tha (localhost = merchant ka apna
    # computer). Aur nakami khamoshi se hoti thi.
    #
    # Ab: env var set ho to wahi (deploy ka sahi tareeqa). Na ho to us request
    # ka apna origin le lete hain jis se ye page load hua — wo tqreeban hamesha
    # sahi public URL hota hai. localhost sirf tab bachta hai jab waqai local
    # par chal rahe ho, aur us soorat mein saaf warning bhi jati hai.
    configured = (os.getenv("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")
    api_url = configured or str(request.base_url).rstrip("/")

    warning = None
    if "localhost" in api_url or "127.0.0.1" in api_url:
        warning = (
            "This snippet points at localhost, so it will not work on a live "
            "store — it only works while you are testing on this machine. "
            "Set BACKEND_PUBLIC_URL on the server to your public API address, "
            "then copy this snippet again."
        )
        logger.warning(
            "Embed code for bot_id=%s built with a local URL (%s) — "
            "set BACKEND_PUBLIC_URL before sharing it.", bot_id, api_url,
        )

    welcome = (bot.welcome_message or "Hello! How can I help you today?").replace('"', "&quot;")
    embed_code = (
        f'<script src="{api_url}/chatbot-widget/widget.js" '
        f'data-bot-id="{bot_id}" '
        f'data-api-url="{api_url}" '
        f'data-color="{bot.primary_color}" '
        f'data-bot-name="{bot.bot_name}" '
        f'data-welcome="{welcome}" '
        f'async></script>'
    )

    return {
        "success": True,
        "bot_id": bot_id,
        "embed_code": embed_code,
        "warning": warning,
    }


# ── Customer Chat — RAG Response ──────────────
@router.post("/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    bot = (
        db.query(ChatbotInstance)
        .filter(ChatbotInstance.bot_id == request.bot_id, ChatbotInstance.is_active == True)  # noqa: E712
        .first()
    )
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found or inactive")

    message = (request.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = request.customer_session_id or str(uuid.uuid4())

    # ── LLM PEHLE, DB BAAD MEIN ─────────────────────────────────────────────
    # Pehle conversation + customer message commit hote the aur PHIR LLM call
    # hoti thi. Call fail hone par (rate limit, network) wo rows DB mein reh
    # jate the, to owner ke dashboard par aisi conversations jama ho jati thin
    # jinka koi jawab hi nahi tha. Ab kuch bhi save tab hota hai jab jawab
    # tayar ho — aur dono messages ek hi commit mein jate hain.
    #
    # get_response() SYNC hai (embeddings + Pinecone + Groq, ~7-11s) aur ye
    # route `async` hai, is liye wo poore event loop ko rok deti thi: measure
    # kiya gaya — ek chat ke doran khali /health 0.32s se 10.32s ho gayi thi.
    # Thread mein bhejne se loop azad rehta hai.
    store_market = _bot_store_market(bot, db)
    result = await asyncio.to_thread(
        get_response,
        bot_id=request.bot_id,
        customer_query=message,
        bot_name=bot.bot_name,
        personality=bot.personality,
        custom_prompt=bot.custom_prompt,
        store_market=store_market,
    )

    conversation = (
        db.query(Conversation)
        .filter(Conversation.bot_id == request.bot_id, Conversation.customer_session_id == session_id)
        .first()
    )
    is_new_conversation = conversation is None
    if is_new_conversation:
        conversation = Conversation(bot_id=request.bot_id, customer_session_id=session_id)
        db.add(conversation)
        db.flush()   # id chahiye, magar commit abhi nahi

    db.add(Message(conversation_id=conversation.id, sender="customer", content=message))
    db.add(Message(
        conversation_id=conversation.id,
        sender="bot",
        content=result["response"],
        confidence_score=result["confidence"],
    ))
    db.commit()
    db.refresh(conversation)

    if is_new_conversation:
        await ws_manager.send_to_user(bot.user_id, {
            "type": "new_conversation",
            "conversation_id": conversation.id,
            "bot_id": bot.bot_id,
            "bot_name": bot.bot_name,
            "customer_session_id": session_id,
        })

    # THIS message needs escalation — LLM's decision for this turn only
    escalate_now = result["should_escalate"] or should_escalate(result["confidence"])

    if escalate_now and not conversation.is_escalated:
        reason = (
            "No knowledge base match for customer question"
            if not result["has_context"]
            else "Assistant flagged this conversation for a human"
        )
        await escalate_conversation(db, conversation.id, reason=reason)
        db.refresh(conversation)

    return {
        "conversation_id": conversation.id,
        "customer_session_id": session_id,
        "response": result["response"],
        "confidence": result["confidence"],
        "should_escalate": escalate_now,
        "citations": result["citations"],
        "sources_found": result["sources_found"],
    }


# ── Conversations For Dashboard ───────────────
@router.get("/conversations/{user_id}")
def get_conversations(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    bots = db.query(ChatbotInstance).filter(ChatbotInstance.user_id == user_id).all()
    bot_map = {b.bot_id: b for b in bots}
    if not bot_map:
        return {"success": True, "data": []}

    conversations = (
        db.query(Conversation)
        .filter(Conversation.bot_id.in_(bot_map.keys()))
        .order_by(Conversation.started_at.desc())
        .all()
    )

    data = []
    for conv in conversations:
        last_message = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        message_count = db.query(Message).filter(Message.conversation_id == conv.id).count()
        bot = bot_map.get(conv.bot_id)

        # Avg confidence — sirf bot messages par, dashboard stat ke liye
        scores = [
            row.confidence_score
            for row in db.query(Message.confidence_score)
            .filter(Message.conversation_id == conv.id, Message.sender == "bot")
            .all()
            if row.confidence_score is not None
        ]

        data.append({
            "id": conv.id,
            "bot_id": conv.bot_id,
            "bot_name": bot.bot_name if bot else None,
            "customer_session_id": conv.customer_session_id,
            "started_at": str(conv.started_at) if conv.started_at else None,
            "is_escalated": conv.is_escalated,
            "escalated_at": str(conv.escalated_at) if conv.escalated_at else None,
            "message_count": message_count,
            "last_message": last_message.content if last_message else None,
            "avg_confidence": round(sum(scores) / len(scores), 3) if scores else None,
        })

    return {"success": True, "data": data}


# ── Messages Of A Conversation ────────────────
@router.get("/messages/{conversation_id}")
def get_messages(conversation_id: int, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Ownership: verify the bot belongs to the caller
    bot = db.query(ChatbotInstance).filter(ChatbotInstance.bot_id == conversation.bot_id).first()
    if not bot or bot.user_id != caller:
        raise HTTPException(403, "You can only view conversations for your own chatbots.")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return {
        "success": True,
        "conversation": {
            "id": conversation.id,
            "bot_id": conversation.bot_id,
            "customer_session_id": conversation.customer_session_id,
            "is_escalated": conversation.is_escalated,
            "escalated_at": str(conversation.escalated_at) if conversation.escalated_at else None,
        },
        "data": [
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content,
                "confidence_score": m.confidence_score,
                "created_at": str(m.created_at) if m.created_at else None,
            }
            for m in messages
        ],
    }


# ── Manually Escalate ─────────────────────────
@router.post("/escalate/{conversation_id}")
async def manual_escalate(conversation_id: int, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    # Ownership: verify the conversation belongs to caller's bot
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    bot = db.query(ChatbotInstance).filter(ChatbotInstance.bot_id == conversation.bot_id).first()
    if not bot or bot.user_id != caller:
        raise HTTPException(403, "You can only escalate conversations for your own chatbots.")
    try:
        conversation = await escalate_conversation(db, conversation_id, reason="Manually escalated by business owner")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"success": True, "message": "Conversation escalated", "conversation_id": conversation.id}


# ── WebSocket — Real-time Dashboard Notifications ──
@router.websocket("/ws/{user_id}")
async def chatbot_ws(websocket: WebSocket, user_id: str, token: str | None = None):
    # Browser WebSockets can't send Authorization headers, so the
    # access token arrives as a query parameter (?token=...).
    if not token:
        await websocket.close(code=4001)
        return
    try:
        caller = verify_access_token(token)
        caller_id = caller.get("id")
        if caller_id != user_id:
            await websocket.close(code=4003)
            return
    except (PermissionError, RuntimeError):
        await websocket.close(code=4001)
        return
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id, websocket)


# ── Helpers ────────────────────────────────────
def _get_bot_or_404(bot_id: str, db: Session) -> ChatbotInstance:
    bot = db.query(ChatbotInstance).filter(ChatbotInstance.bot_id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found")
    return bot


def _compose_personality(tone: str | None, traits: list, explicit: str | None) -> str:
    """
    RAG prompt ek plain-English personality string use karta hai. Wizard tone aur
    traits alag bhejta hai, to unhe yahan ek readable line mein jorha jata hai.
    """
    if explicit and explicit.strip() and explicit.strip() != "helpful and friendly":
        return explicit.strip()

    parts = []
    if tone:
        parts.append(tone.strip())
    parts.extend(t.strip() for t in traits if t and t.strip())

    if not parts:
        return "helpful and friendly"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _store_knowledge(
    db: Session,
    bot_id: str,
    text: str,
    filename: str,
    file_type: str,
    file_size: int,
    source_type: str,
) -> UploadedDocument:
    """Text ko chunk + embed karke Pinecone mein store karta hai aur document row banata hai."""
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable content found")

    embeddings = generate_embeddings(chunks)
    vector_ids = store_embeddings(bot_id, chunks, embeddings)

    document = UploadedDocument(
        bot_id=bot_id,
        filename=filename,
        file_type=file_type,
        file_size=file_size,
        chunks_stored=len(chunks),
        source_type=source_type,
        vector_ids=vector_ids,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _serialize_bot(bot: ChatbotInstance, db: Session | None = None) -> dict:
    data = {
        "id": bot.id,
        "bot_id": bot.bot_id,
        "user_id": bot.user_id,
        "bot_name": bot.bot_name,
        "description": bot.description,
        "category": bot.category or "custom",
        "personality": bot.personality,
        "tone": bot.tone or "professional",
        "personality_traits": bot.personality_traits or [],
        "custom_prompt": bot.custom_prompt,
        "welcome_message": bot.welcome_message or "Hello! How can I help you today?",
        "primary_color": bot.primary_color,
        "owner_email": bot.owner_email,
        "brand_profile_id": bot.brand_profile_id,
        "status": bot.status or ("active" if bot.is_active else "paused"),
        "is_active": bot.is_active,
        "created_at": str(bot.created_at) if bot.created_at else None,
        "document_count": 0,
        "chunk_count": 0,
        "conversation_count": 0,
        "escalated_count": 0,
    }
    if db is not None:
        documents = (
            db.query(UploadedDocument.chunks_stored)
            .filter(UploadedDocument.bot_id == bot.bot_id)
            .all()
        )
        data["document_count"] = len(documents)
        data["chunk_count"] = sum(row.chunks_stored or 0 for row in documents)
        data["conversation_count"] = (
            db.query(Conversation).filter(Conversation.bot_id == bot.bot_id).count()
        )
        data["escalated_count"] = (
            db.query(Conversation)
            .filter(Conversation.bot_id == bot.bot_id, Conversation.is_escalated == True)  # noqa: E712
            .count()
        )
    return data


def _serialize_document(document: UploadedDocument) -> dict:
    return {
        "id": document.id,
        "bot_id": document.bot_id,
        "filename": document.filename,
        "file_type": document.file_type,
        "file_size": document.file_size or 0,
        "chunks_stored": document.chunks_stored,
        "source_type": document.source_type or "document",
        "uploaded_at": str(document.uploaded_at) if document.uploaded_at else None,
    }


def _clear_pinecone_namespace(bot_id: str) -> None:
    """Namespace agar exist hi na kare to Pinecone 404 deta hai — usse ignore karo."""
    try:
        delete_bot_data(bot_id)
    except Exception:
        pass


# ── Bot ka market ─────────────────────────────
def _bot_store_market(bot: ChatbotInstance, db: Session):
    """
    Bot ke brand profile se detect ki hui country. Bot kisi brand se linked na
    ho, ya us brand ka market detect na hua ho, to None — aur us soorat mein
    chatbot prompt bilkul country-neutral rehta hai.
    """
    if not bot.brand_profile_id:
        return None
    brand = db.query(BrandProfile).filter(BrandProfile.id == bot.brand_profile_id).first()
    return store_country(brand)
