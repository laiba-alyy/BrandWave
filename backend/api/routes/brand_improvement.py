"""Brand Improvement Suggestions — API route."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db
from modules.brand_improvement.service import generate_improvements
from modules.llm_config import RateLimitedError
from modules.auth import get_current_user

router = APIRouter()


class ImprovementRequest(BaseModel):
    user_id: str
    brand_profile_id: int
    # "english" (default) or "roman_urdu". Anything unrecognised falls back
    # to English in normalise_language() rather than failing the request.
    language: str = "english"


@router.post("/generate")
def generate(request: ImprovementRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Generate data-backed brand improvement suggestions.

    Gathers sentiment + SEO + product data, sends to LLM with a strict
    "evidence-only" prompt. Returns structured suggestions where every
    recommendation traces to a real data point.
    """
    try:
        result = generate_improvements(
            db=db,
            user_id=caller,
            brand_profile_id=request.brand_profile_id,
            language=request.language,
        )
        return {"success": True, **result}
    except RateLimitedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def health():
    return {"status": "Brand Improvement module running ✅"}
