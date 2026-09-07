"""
Bria/Claid services ka shared plumbing.

Dono services ka contract ek jaisa hai:

    generate_*(product, form_data, brand, width, height) -> str   # local file path

Aage jo bhi provider add ho, wahi signature rakhe — routes.py sirf dispatch
karta hai, use provider ke baare mein kuch pata nahi hona chahiye.
"""
import logging
import os
import uuid
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Wahi output folder jo openai_service use karta tha — gallery, /static mount
# aur image_polish sab isi path shape par chalte hain, is liye badla nahi.
OUTPUT_DIR = Path("generated_ads/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Ad image ki upper hadd. Is se bari cheez provider se aaye to wo image nahi,
# koi galti hai — aur usay RAM mein lena server ke liye khatra hai.
_MAX_IMAGE_BYTES = 25 * 1024 * 1024


class AdImageServiceError(Exception):
    """
    Base-image provider ki nakami — user ko dikhane layak shakl mein.

    `message` seedha user tak jata hai, is liye us mein sirf woh baat ho jo
    user samajh sake aur us par amal kar sake. Provider ka raw response
    (jis mein key, internal id ya stack trace ho sakta hai) `detail` mein
    rehta hai aur SIRF server log mein jata hai — response mein kabhi nahi.
    """

    def __init__(self, message: str, *, provider: str = "", detail: str = ""):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.detail = detail


class AdCreditsExhaustedError(AdImageServiceError):
    """
    Provider ka free quota khatam.

    Ye AdImageServiceError se alag class is liye hai ke iska ilaaj alag hai:
    "dobara koshish karein" yahan JHOOT hai — dobara koshish karne se bhi kuch
    nahi hoga. Route ise 402 banata hai aur UI ek alag, saaf panel dikhata hai.

    Bria (100 free) aur Claid (39 baqi) dono demo ke doran khatam ho sakte
    hain, is liye ye soorat chup-chaap 502 "could not generate" ban kar nahi
    guzarni chahiye — warna dekhne wale ko lagta hai project toot gaya.
    """


# Provider har ek apne andaz mein batata hai ke credit khatam hain. Status
# code par bharosa kaafi nahi: kuch 402 dete hain, kuch 403, aur kuch 200 ke
# saath error body. Is liye body mein ye alfaz bhi dekhte hain.
_CREDIT_MARKERS = (
    "insufficient credit", "insufficient_credit", "no credits", "out of credits",
    "credit limit", "not enough credits", "quota exceeded", "quota_exceeded",
    "exceeded your quota", "usage limit", "limit exceeded", "plan limit",
    "subscription", "payment required", "billing", "upgrade your plan",
    "free tier", "trial expired",
)


def _looks_like_credit_exhaustion(status_code: int, body: str) -> bool:
    if status_code == 402:                     # Payment Required — saaf signal
        return True
    low = (body or "").lower()
    return any(marker in low for marker in _CREDIT_MARKERS)


def require_api_key(env_name: str, provider: str) -> str:
    """Key uthao — na mile to saaf message, taake 500 ke bajaye wajah nazar aaye."""
    key = (os.getenv(env_name) or "").strip()
    if not key:
        raise AdImageServiceError(
            f"{provider} is not configured on the server. "
            f"Ask your admin to set {env_name}.",
            provider=provider,
            detail=f"{env_name} missing or empty",
        )
    return key


# Bria aur Claid dono yehi strings lete hain, is liye ek hi map dono ke liye
# kaafi hai. ASPECT_RATIO_MAP (schemas.py) pixels deta hai; providers ko ratio
# chahiye, is liye pixels se ratio yahan nikalte hain.
def aspect_ratio_label(width: int, height: int) -> str:
    if height > width:
        return "9:16"
    if width > height:
        return "16:9"
    return "1:1"


def product_image_url(product: dict, provider: str) -> str:
    """
    Product ka public image URL.

    Claid sirf URL leta hai (base64 support documented nahi hai), aur Bria ke
    liye bhi URL sasta rasta hai — bytes upload karne ki zaroorat nahi. URL na
    ho to yahin saaf error, warna aage provider ka cryptic 4xx aata.
    """
    url = (product.get("image_url") or "").strip()
    if not url:
        raise AdImageServiceError(
            f"This product has no image in the catalogue, so {provider} cannot "
            "generate an ad for it. Re-scrape the store or pick another product.",
            provider=provider,
            detail=f"product id={product.get('id')} has empty image_url",
        )
    return url


def save_image_from_url(url: str, provider: str, suffix: str = ".png") -> str:
    """
    Provider ka result download kar ke OUTPUT_DIR mein rakhta hai.

    Return wahi shape jo openai_service deta tha ("generated_ads/images/<uuid>.png"),
    taake image_polish, DB ka image_path aur gallery — sab bina tabdeeli chalte rahen.
    """
    try:
        # stream=True + size cap: pehle `response.content` poori body seedha
        # RAM mein le aata tha, bina kisi hadd ke. Provider (ya koi redirect)
        # agar bara file de de to server ka memory usi ek request par chala
        # jata. Ad image kabhi 25 MB se bari nahi hoti.
        response = requests.get(url, timeout=90, stream=True)
        response.raise_for_status()

        chunks, total = [], 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > _MAX_IMAGE_BYTES:
                raise AdImageServiceError(
                    f"{provider} returned an unexpectedly large image. Please try again.",
                    provider=provider,
                    detail=f"download exceeded {_MAX_IMAGE_BYTES} bytes from {url}",
                )
            chunks.append(chunk)
        content = b"".join(chunks)
    except requests.RequestException as e:
        raise AdImageServiceError(
            f"{provider} generated the image but it could not be downloaded. "
            "Please try again.",
            provider=provider,
            detail=f"GET {url} failed: {type(e).__name__}: {e}",
        )

    if not content:
        raise AdImageServiceError(
            f"{provider} returned an empty image. Please try again.",
            provider=provider, detail=f"0 bytes from {url}",
        )

    filepath = OUTPUT_DIR / f"{uuid.uuid4().hex}{suffix}"
    with open(filepath, "wb") as f:
        f.write(content)

    logger.info("%s: saved base image -> %s (%d bytes)",
                provider, filepath, len(content))
    return str(filepath)


def post_json(url: str, headers: dict, payload: dict, provider: str, timeout: int = 200):
    """
    POST + saaf error mapping.

    Har failure ko AdImageServiceError banata hai taake route ko provider ke
    HTTP codes ka ilm na rakhna pare, aur raw body kabhi user tak na jaye.
    """
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout:
        raise AdImageServiceError(
            f"{provider} took too long to respond. Please try again.",
            provider=provider, detail=f"timeout after {timeout}s on {url}",
        )
    except requests.RequestException as e:
        raise AdImageServiceError(
            f"Could not reach {provider}. Check the server's internet connection.",
            provider=provider, detail=f"{type(e).__name__}: {e}",
        )

    body = response.text or ""

    # Credits ka check SAB SE PEHLE — warna 402/403 "key ghalat hai" ban jata
    # hai aur user apni sahih key check karta reh jata hai.
    if _looks_like_credit_exhaustion(response.status_code, body):
        raise AdCreditsExhaustedError(
            f"Your {provider} image credits have run out. "
            "Image ad generation is paused until the plan is topped up.",
            provider=provider,
            detail=f"HTTP {response.status_code}: {body[:500]}",
        )

    if response.status_code in (401, 403):
        raise AdImageServiceError(
            f"{provider} rejected the API key. Ask your admin to check it.",
            provider=provider,
            detail=f"HTTP {response.status_code}: {body[:500]}",
        )
    if response.status_code == 429:
        raise AdImageServiceError(
            f"{provider} is rate limiting requests. Please wait a moment and try again.",
            provider=provider,
            detail=f"HTTP 429: {body[:500]}",
        )
    if response.status_code >= 400:
        raise AdImageServiceError(
            f"{provider} could not generate an image for this product. "
            "Try a different product or another generation mode.",
            provider=provider,
            detail=f"HTTP {response.status_code}: {body[:500]}",
        )

    try:
        return response.json()
    except ValueError:
        raise AdImageServiceError(
            f"{provider} returned an unexpected response. Please try again.",
            provider=provider, detail=f"non-JSON body: {response.text[:500]}",
        )
