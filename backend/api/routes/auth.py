"""
Account lifecycle endpoints.

Abhi sirf ek hi hai: account deletion, jo Neon + Pinecone + Supabase teeno
saaf karti hai. Tafseel modules/account_deletion.py mein.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db
from modules.account_deletion import (
    delete_supabase_user,
    delete_user_data,
    verify_access_token,
)

router = APIRouter()


class DeleteAccountRequest(BaseModel):
    # dry_run=True par kuch delete nahi hota, sirf counts aati hain. UI ise
    # "aap ka kya kya delete hoga" dikhane ke liye use kar sakti hai.
    dry_run: bool = False


def _authorize(user_id: str, authorization: str | None) -> dict:
    """
    Sirf khud user (ya admin) apna account delete kar sakta hai.

    Baqi backend routes user_id ko bharose ke saath plain param ki tarah lete
    hain, magar ye endpoint DESTRUCTIVE hai — bina token ke koi bhi kisi ka
    bhi account uda sakta tha. Is liye yahan token lazmi hai aur uska user id
    path ke user_id se match karna chahiye.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token. Send the signed-in user's Supabase access token.",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        caller = verify_access_token(token)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    caller_id = caller.get("id")
    is_admin = (caller.get("user_metadata") or {}).get("role") == "admin"
    if caller_id != user_id and not is_admin:
        raise HTTPException(
            status_code=403, detail="You can only delete your own account."
        )
    return caller


@router.post("/delete-account/{user_id}")
def delete_account(
    user_id: str,
    request: DeleteAccountRequest = DeleteAccountRequest(),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    User ka poora account delete karta hai — Neon, Pinecone, Supabase.

    Sequence:
      1. Neon + Pinecone ka saara data (delete_user_data)
      2. Supabase users row + auth record (delete_supabase_user)

    Supabase JAAN BOOJH KAR aakhir mein hai. Agar step 1 beech mein fail ho
    jaye to auth record zinda rehta hai — user dobara login kar ke retry kar
    sakta hai. Ulta tarteeb mein wo apne bache hue data tak pahunch hi na pata.
    """
    _authorize(user_id, authorization)

    try:
        data_report = delete_user_data(user_id, db, dry_run=request.dry_run)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Data deletion failed: {e}")

    try:
        supabase_report = delete_supabase_user(user_id, dry_run=request.dry_run)
    except Exception as e:
        # Neon/Pinecone ja chuka hai magar auth record reh gaya. Ye 500 hai,
        # "success" nahi — purana flow yahin jhoot bolta tha.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Business data was deleted, but the Supabase account could not be "
                f"removed: {e}. Please retry — the remaining steps are idempotent."
            ),
        )

    return {
        "success": True,
        "message": (
            "Dry run — nothing was deleted."
            if request.dry_run
            else "Account and all associated data deleted."
        ),
        "deleted": {**data_report, "supabase": supabase_report},
    }
