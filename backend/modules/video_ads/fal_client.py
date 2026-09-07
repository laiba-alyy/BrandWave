"""
fal.ai queue API ka patla wrapper — sirf `requests` par, koi naya package nahi.

Yeh file modules/ads_generation/services/common.py ka video wala jorra hai aur
usi usool par chalti hai: har nakami ek saaf `VideoAdServiceError` banti hai
jis ka `message` user ko dikhaya ja sakta hai, aur provider ka raw jawab
(jis mein key, request id ya stack trace ho sakta hai) SIRF `detail` mein
rehta hai jo server log tak mehdood hai.

Endpoints 2026-08-29 ko fal ke live docs se verify kiye gaye:
    submit : POST https://queue.fal.run/{model_id}
    status : GET  https://queue.fal.run/{model_id}/requests/{request_id}/status
    result : GET  https://queue.fal.run/{model_id}/requests/{request_id}
    header : Authorization: Key <FAL_API_KEY>

Video generation seconds nahi, MINUTES leti hai — is liye fal ka seedha
`https://fal.run/...` (synchronous) rasta yahan theek nahi tha; woh lambi
requests par timeout deta hai. Queue + polling hi documented tareeqa hai.
"""
import base64
import logging
import mimetypes
import os
import time
import uuid
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PROVIDER = "Kling (fal.ai)"

QUEUE_BASE = "https://queue.fal.run"

# Wahi folder jo purana video_service use karta tha. main.py `generated_ads` ko
# /static par mount karta hai aur frontend ka toImageUrl() isi shape par chalta
# hai, is liye badla nahi.
OUTPUT_DIR = Path("generated_ads/videos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Ek segment ke liye kitna intezar karein. 10s Kling clip aam tor par 2-5 minute
# leti hai; queue bhari ho to zyada. 15 minute ke baad haar maan lena behtar hai
# — us se aage masla hamare intezar se hal nahi hota.
POLL_TIMEOUT_SECONDS = int(os.getenv("FAL_POLL_TIMEOUT", "900"))
POLL_INTERVAL_SECONDS = 5


class VideoAdServiceError(Exception):
    """
    Video provider ki nakami — user ko dikhane layak shakl mein.

    `message` seedha user tak jata hai. `detail` sirf log ke liye hai.
    """

    def __init__(self, message: str, *, provider: str = PROVIDER, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.detail = detail


class VideoCreditsExhaustedError(VideoAdServiceError):
    """
    fal.ai ke credits khatam.

    VideoAdServiceError se alag class is liye hai ke route ise 402 banata hai,
    502 nahi — aur UI 402 par apna "out of credits" panel dikhati hai. "Please
    try again" is soorat mein jhoot hai: dobara koshish se kuch nahi hoga,
    balance top-up karna parta hai.

    Yehi tarteeb image module mein bhi hai (AdCreditsExhaustedError), taake
    dono jagah ek jaisa bartao rahe.
    """


# fal har haal mein 402 nahi deta — kabhi 400/403 ke saath body mein wajah
# likhta hai. Is liye status ke saath body ke alfaz bhi dekhte hain.
_CREDIT_MARKERS = (
    "insufficient", "no credits", "out of credits", "exhausted", "balance",
    "quota", "billing", "payment required", "top up", "topup",
    "upgrade your plan", "free tier", "spending limit",
)


def _looks_like_credit_exhaustion(status_code: int, body: str) -> bool:
    if status_code == 402:
        return True
    low = (body or "").lower()
    return any(marker in low for marker in _CREDIT_MARKERS)


def require_fal_key() -> str:
    """FAL_API_KEY uthao — na mile to saaf message, 500 ke bajaye asal wajah."""
    key = (os.getenv("FAL_API_KEY") or "").strip()
    if not key:
        raise VideoAdServiceError(
            "Video generation is not configured on the server. "
            "Ask your admin to set FAL_API_KEY.",
            detail="FAL_API_KEY missing or empty",
        )
    return key


def _auth_headers(api_key: str) -> dict:
    # fal ka scheme "Bearer" nahi "Key" hai — Bearer bhejne par 401 aata hai.
    return {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}


def _raise_for_response(response: requests.Response, what: str) -> dict:
    """HTTP status -> saaf user message. Raw body sirf detail mein."""
    body = response.text or ""

    # Credits ka check SAB SE PEHLE — warna 402/403 "key ghalat hai" ban jata
    # hai aur user apni sahih key check karta reh jata hai.
    if _looks_like_credit_exhaustion(response.status_code, body):
        raise VideoCreditsExhaustedError(
            "Your fal.ai video credits have run out. Video ad generation is "
            "paused until the balance is topped up.",
            detail=f"{what}: HTTP {response.status_code}: {body[:500]}",
        )

    if response.status_code in (401, 403):
        raise VideoAdServiceError(
            "fal.ai rejected the API key. Ask your admin to check FAL_API_KEY.",
            detail=f"{what}: HTTP {response.status_code}: {body[:500]}",
        )
    if response.status_code == 429:
        raise VideoAdServiceError(
            "fal.ai rate limit reached. Please wait a moment and try again.",
            detail=f"{what}: HTTP 429: {response.text[:500]}",
        )
    if response.status_code == 422:
        raise VideoAdServiceError(
            "fal.ai rejected the request for this model. The model's inputs may have "
            "changed — ask your admin to check FAL_KLING_MODEL.",
            detail=f"{what}: HTTP 422: {response.text[:500]}",
        )
    if response.status_code >= 400:
        raise VideoAdServiceError(
            "The video service could not process this request. Please try again with "
            "a different product or a shorter length.",
            detail=f"{what}: HTTP {response.status_code}: {response.text[:500]}",
        )

    try:
        return response.json()
    except ValueError:
        raise VideoAdServiceError(
            "The video service returned an unexpected response. Please try again.",
            detail=f"{what}: non-JSON body: {response.text[:500]}",
        )


def _request(method: str, url: str, api_key: str, what: str, payload: dict | None = None,
             timeout: int = 120) -> dict:
    try:
        response = requests.request(
            method, url, headers=_auth_headers(api_key), json=payload, timeout=timeout
        )
    except requests.Timeout:
        raise VideoAdServiceError(
            "fal.ai took too long to respond. Please try again.",
            detail=f"{what}: timeout after {timeout}s on {url}",
        )
    except requests.RequestException as e:
        raise VideoAdServiceError(
            "Could not reach fal.ai. Check the server's internet connection.",
            detail=f"{what}: {type(e).__name__}: {e}",
        )
    return _raise_for_response(response, what)


def run_model(model_id: str, payload: dict, api_key: str) -> dict:
    """
    Ek generation chalao aur mukammal result JSON do (submit + poll).

    JAAN BOOJH KAR koi auto-retry NAHI hai. Har call par paisa lagta hai, to
    nakami par dobara try karne ka faisla user ka hai — hamara nahi.
    """
    submit_url = f"{QUEUE_BASE}/{model_id}"
    submitted = _request("POST", submit_url, api_key, f"submit {model_id}", payload)

    request_id = submitted.get("request_id")
    if not request_id:
        raise VideoAdServiceError(
            "fal.ai did not accept the video request. Please try again.",
            detail=f"submit {model_id}: no request_id in {str(submitted)[:500]}",
        )

    # fal khud status/response URLs deta hai — unhein tarjeeh do. Path khud
    # banane par model id mein koi bhi tabdeeli (nested paths waghera) chup-chaap
    # 404 de sakti hai.
    status_url = submitted.get("status_url") or \
        f"{QUEUE_BASE}/{model_id}/requests/{request_id}/status"
    result_url = submitted.get("response_url") or \
        f"{QUEUE_BASE}/{model_id}/requests/{request_id}"

    logger.info("fal: queued %s request_id=%s", model_id, request_id)

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        status = _request("GET", status_url, api_key, f"status {request_id}", timeout=60)
        state = status.get("status")

        if state == "COMPLETED":
            break
        if state in ("FAILED", "ERROR", "CANCELLED"):
            raise VideoAdServiceError(
                "The video generation failed on fal.ai. Please try again, or try a "
                "different product image.",
                detail=f"status {request_id}: {str(status)[:500]}",
            )
        if time.monotonic() >= deadline:
            raise VideoAdServiceError(
                "The video is taking longer than expected and timed out. It may still "
                "finish on fal.ai — check your fal.ai dashboard before generating again "
                "so you are not charged twice.",
                detail=f"status {request_id}: timed out after {POLL_TIMEOUT_SECONDS}s, "
                       f"last status={state}",
            )
        time.sleep(POLL_INTERVAL_SECONDS)

    return _request("GET", result_url, api_key, f"result {request_id}", timeout=120)


def extract_video_url(result: dict) -> str:
    """
    Result JSON se video ka URL nikalo.

    Kling ka documented output {"video": {"url": ...}} hai, magar fal ke model
    versions mein yeh shape thoRi badalti rehti hai (kuch `url` seedha dete
    hain). Do-teen maroof shapes handle kar lena ek KeyError se behtar hai jab
    generation ka paisa lag chuka ho.
    """
    video = result.get("video")
    if isinstance(video, dict) and video.get("url"):
        return video["url"]
    if isinstance(video, str) and video:
        return video

    videos = result.get("videos")
    if isinstance(videos, list) and videos:
        first = videos[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]
        if isinstance(first, str):
            return first

    if isinstance(result.get("url"), str):
        return result["url"]

    raise VideoAdServiceError(
        "The video service finished but returned no video. Please try again.",
        detail=f"unexpected result shape: {str(result)[:500]}",
    )


# Downloaded video ki upper hadd — is se bara file ek galti hai, aur usay
# disk par likhte rehna server ke liye khatra hai.
_MAX_VIDEO_BYTES = 250 * 1024 * 1024

# Data URI ke liye source image ki hadd. Base64 file ko ~33% bara kar deta
# hai, aur poora payload RAM mein banta hai — bari image yahin rok do.
_MAX_DATA_URI_BYTES = 12 * 1024 * 1024


def download_video(url: str, dest: Path) -> Path:
    """fal ka result download kar ke `dest` par likh do."""
    try:
        response = requests.get(url, timeout=300, stream=True)
        response.raise_for_status()
    except requests.RequestException as e:
        raise VideoAdServiceError(
            "The video was generated but could not be downloaded. Please try again.",
            detail=f"GET {url} failed: {type(e).__name__}: {e}",
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            if not chunk:
                continue
            size += len(chunk)
            # Bina hadd ke stream disk bhar sakti hai. 20s ka 1080p clip bhi
            # ~30 MB hota hai, is liye 250 MB har jaiz soorat se bohat upar hai.
            if size > _MAX_VIDEO_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise VideoAdServiceError(
                    "The generated video was unexpectedly large and was discarded. "
                    "Please try again.",
                    detail=f"download exceeded {_MAX_VIDEO_BYTES} bytes from {url}",
                )
            f.write(chunk)

    logger.info("fal: saved segment -> %s (%d bytes)", dest, size)
    return dest


def new_video_path() -> Path:
    """Gallery ke liye naya output path (wahi shape jo image ads ka hai)."""
    return OUTPUT_DIR / f"{uuid.uuid4().hex}.mp4"


def file_to_data_uri(path: str | Path) -> str:
    """
    Local file ko base64 data URI bana do.

    Kyun zaroorat parti hai: fal ko ek aisa image chahiye jo woh PARH sake.
    Product ke apne image_url public CDN par hote hain (theek), lekin
    (a) extension ka last frame aur (b) local image-ad output sirf is server par
    hote hain — aur dev machine ka localhost fal se nazar nahi aata. Data URI
    file input ke tor par documented hai, is liye kisi public hosting ya alag
    upload step ki zaroorat nahi parti.
    """
    path = Path(path)
    if not path.exists():
        raise VideoAdServiceError(
            "The source image for this video is missing on the server. "
            "Please generate the image ad again, or pick a product instead.",
            detail=f"file not found: {path}",
        )

    # Base64 file ko ~33% bara kar deta hai aur poora payload RAM mein banta
    # hai. Bina hadd ke ek bari image (ya ghalti se koi video) yahan server ka
    # memory kha sakti hai — is liye pehle size dekh lete hain.
    size = path.stat().st_size
    if size > _MAX_DATA_URI_BYTES:
        raise VideoAdServiceError(
            "That source image is too large to use for a video. Please pick "
            "another product or regenerate the image ad.",
            detail=f"{path} is {size} bytes, cap is {_MAX_DATA_URI_BYTES}",
        )

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
