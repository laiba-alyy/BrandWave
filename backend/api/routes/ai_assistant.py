from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.connection import get_db
from modules.auth import get_current_user
from modules.ai_assistant.schemas import ChatRequest, ChatResponse
from modules.ai_assistant.assistant_service import (
    get_chat_response, get_session_history, get_user_sessions
)

router = APIRouter(tags=["AI Assistant"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Always trust the token, never the request body's user_id.
    reply = get_chat_response(
        db=db,
        user_id=caller,
        session_id=payload.session_id,
        message=payload.message,
        current_page=payload.current_page,
        brand_profile_id=payload.brand_profile_id,
    )
    return ChatResponse(reply=reply, session_id=payload.session_id)


@router.get("/history/{session_id}")
def get_history(
    session_id: str,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Ownership check: only return history if the session belongs to the caller.
    return get_session_history(db, session_id, caller)


@router.get("/sessions/{user_id}")
def get_sessions(
    user_id: str,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if caller != user_id:
        raise HTTPException(403, "You can only view your own sessions.")
    return get_user_sessions(db, user_id)