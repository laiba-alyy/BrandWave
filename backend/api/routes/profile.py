import os
import uuid
from pathlib import Path, PurePath
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database.connection import get_db
from models.user_profile import UserProfile
from modules.auth import get_current_user, require_owner

router = APIRouter()

UPLOAD_DIR = Path("uploads/avatars")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _looks_like_image(data: bytes) -> bool:
    """
    Magic bytes se asli image format check karo.

    Sirf extension check karne se `evil.png` naam ki koi bhi file qubool ho
    jati thi — test mein ek Windows executable (MZ header) 200 le gaya tha.
    Ye files /uploads static mount se serve hoti hain, is liye asli format
    ki tasdeeq zaroori hai.
    """
    if len(data) < 12:
        return False
    return (
        data[:3] == b"\xff\xd8\xff"                        # JPEG
        or data[:8] == b"\x89PNG\r\n\x1a\n"                # PNG
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")  # WEBP
    )


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    business_name: Optional[str] = None
    business_role: Optional[str] = None
    timezone: Optional[str] = None


class UpdateNotificationsRequest(BaseModel):
    notify_escalation: Optional[bool] = None
    notify_weekly_report: Optional[bool] = None
    notify_new_conversation: Optional[bool] = None
    notify_marketing_tips: Optional[bool] = None
    notification_frequency: Optional[str] = None


def _get_or_create_profile(user_id: str, db: Session) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _public_backend_url() -> str:
    return (os.getenv("BACKEND_PUBLIC_URL") or "http://localhost:8000").rstrip("/")


def _avatar_url(profile: UserProfile) -> str | None:
    """
    DB mein rakhi value se browser ke qabil URL banao.

    Pehle upload_avatar poora FILESYSTEM path column mein likhta tha
    (``uploads\\avatars\\<id>_<hex>.png``) aur POST response mein alag se
    theek URL bana kar bhejta tha. Nateeja: upload ke foran baad tasveer
    dikhti thi, magar page reload par frontend
    ``<img src="uploads\\avatars\\...">`` render karta tha — relative path,
    Windows backslashes ke sath — yani toota hua image.

    Ab column mein sirf FILENAME jata hai aur URL har jagah yahin se banti
    hai. Purani rows (poore path wali) ke liye basename nikal lete hain,
    taake pehle se upload shuda avatars bhi theek dikhein.
    """
    stored = (profile.avatar_url or "").strip()
    if not stored:
        return None
    if stored.startswith(("http://", "https://")):
        return stored
    filename = PurePath(stored.replace("\\", "/")).name
    return f"{_public_backend_url()}/uploads/avatars/{filename}"


def _avatar_path(profile: UserProfile) -> Path | None:
    """Disk par is avatar ki jagah — delete/replace ke liye."""
    stored = (profile.avatar_url or "").strip()
    if not stored or stored.startswith(("http://", "https://")):
        return None
    return UPLOAD_DIR / PurePath(stored.replace("\\", "/")).name


def _serialize(profile: UserProfile) -> dict:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "full_name": profile.full_name,
        "phone_number": profile.phone_number,
        "avatar_url": _avatar_url(profile),
        "business_name": profile.business_name,
        "business_role": profile.business_role,
        "notify_escalation": profile.notify_escalation,
        "notify_weekly_report": profile.notify_weekly_report,
        "notify_new_conversation": profile.notify_new_conversation,
        "notify_marketing_tips": profile.notify_marketing_tips,
        "notification_frequency": profile.notification_frequency,
        "two_factor_enabled": profile.two_factor_enabled,
        "theme": profile.theme,
        "timezone": profile.timezone,
        "created_at": str(profile.created_at) if profile.created_at else None,
        "updated_at": str(profile.updated_at) if profile.updated_at else None,
    }


@router.get("/{user_id}")
def get_profile(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    profile = _get_or_create_profile(user_id, db)
    return {"success": True, "data": _serialize(profile)}


@router.patch("/{user_id}")
def update_profile(user_id: str, request: UpdateProfileRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    profile = _get_or_create_profile(user_id, db)

    if request.full_name is not None:
        profile.full_name = request.full_name
    if request.phone_number is not None:
        profile.phone_number = request.phone_number
    if request.business_name is not None:
        profile.business_name = request.business_name
    if request.business_role is not None:
        profile.business_role = request.business_role
    if request.timezone is not None:
        profile.timezone = request.timezone

    db.commit()
    db.refresh(profile)
    return {"success": True, "data": _serialize(profile)}


@router.patch("/{user_id}/notifications")
def update_notifications(user_id: str, request: UpdateNotificationsRequest, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    profile = _get_or_create_profile(user_id, db)

    if request.notify_escalation is not None:
        profile.notify_escalation = request.notify_escalation
    if request.notify_weekly_report is not None:
        profile.notify_weekly_report = request.notify_weekly_report
    if request.notify_new_conversation is not None:
        profile.notify_new_conversation = request.notify_new_conversation
    if request.notify_marketing_tips is not None:
        profile.notify_marketing_tips = request.notify_marketing_tips
    if request.notification_frequency is not None:
        profile.notification_frequency = request.notification_frequency

    db.commit()
    db.refresh(profile)
    return {"success": True, "data": _serialize(profile)}


@router.post("/{user_id}/avatar")
async def upload_avatar(user_id: str, caller: str = Depends(get_current_user), file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP allowed")

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max file size is 5MB")

    # Extension par bharosa kaafi nahi — `evil.png` naam de kar koi bhi file
    # upload ho jati thi (test mein ek Windows executable qubool hui). Magic
    # bytes se asli format check karo; ye files /uploads se serve hoti hain.
    if not _looks_like_image(file_bytes):
        raise HTTPException(
            status_code=400,
            detail="That file is not a valid JPG, PNG or WEBP image.",
        )

    filename = f"{user_id}_{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    profile = _get_or_create_profile(user_id, db)

    # Delete old avatar
    old_path = _avatar_path(profile)
    if old_path and old_path.exists():
        old_path.unlink()

    # Sirf FILENAME store hota hai — URL _avatar_url() banati hai. Poora path
    # rakhne se reload par toota hua image aata tha (dekho _avatar_url).
    profile.avatar_url = filename
    db.commit()
    db.refresh(profile)

    return {
        "success": True,
        "avatar_url": _avatar_url(profile),
        "data": _serialize(profile)
    }


@router.delete("/{user_id}/avatar")
def remove_avatar(user_id: str, caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    require_owner(caller, user_id)
    profile = _get_or_create_profile(user_id, db)

    old_path = _avatar_path(profile)
    if old_path and old_path.exists():
        old_path.unlink()

    profile.avatar_url = None
    db.commit()
    db.refresh(profile)
    return {"success": True, "data": _serialize(profile)}