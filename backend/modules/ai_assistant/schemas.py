from pydantic import BaseModel
from typing import Optional, List


class ChatRequest(BaseModel):
    # user_id is no longer required — the backend reads the caller's
    # identity from the Supabase Bearer token.  Kept as optional for
    # backward compat with older clients that still send it.
    user_id: Optional[str] = None
    session_id: str
    message: str
    current_page: Optional[str] = None
    brand_profile_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class ChatHistoryItem(BaseModel):
    sender: str
    message: str


class SessionItem(BaseModel):
    id: str
    title: str
    updated_at: str