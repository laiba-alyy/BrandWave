"""
Claid — "AI Fashion Models"  (generation_mode = "on_model")

Kis liye: garment ki flat-lay ya mannequin photo, jis mein koi model NAHI hai.
Claid us garment ko ek generated model par pehna deta hai.

Agar photo mein pehle se model maujood hai to ye mode ghalat chunav hai —
us surat mein "scene" (Bria) use hota hai.

Endpoint/format 2026-08-29 ko docs se verify kiye gaye:
    POST https://api.claid.ai/v1/image/ai-fashion-models
    header : Authorization: Bearer <CLAID_API_KEY>
    body   : {"input": {"clothing": [url]}, "options": {...}, "output": {...}}
    200    : {"data": {"id", "status", "result_url", ...}}
    poll   : GET https://api.claid.ai/v1/image/ai-fashion-models/{id}
             -> data.status == "DONE"
             -> data.result.output_objects[0].tmp_url

NOTE: Claid `input.clothing` mein sirf PUBLIC URL leta hai — base64 ka koi
documented rasta nahi. Shopify CDN URLs public hain is liye masla nahi, lekin
locally upload ki hui images is mode se nahi guzar sakti.
"""
import logging
import time

import requests

from modules.ads_generation.prompt_builder import build_model_options
from modules.ads_generation.services.common import (
    AdImageServiceError,
    post_json,
    product_image_url,
    require_api_key,
    save_image_from_url,
)

logger = logging.getLogger(__name__)

CLAID_URL = "https://api.claid.ai/v1/image/ai-fashion-models"

PROVIDER = "Claid"

# Job aam taur par ~15-40s leti hai. 5 min ke baad haar maan lete hain taake
# request hamesha ke liye latki na rahe.
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300

TERMINAL_FAILURE_STATUSES = {"ERROR", "CANCELLED"}


def generate_on_model_image(product: dict, form_data: dict, brand, width: int, height: int) -> str:
    """
    Flat/mannequin garment photo -> model ne pehna hua shot.

    Return: local file path, wahi shape jo baaqi flow expect karta hai.
    """
    api_key = require_api_key("CLAID_API_KEY", PROVIDER)
    image_url = product_image_url(product, PROVIDER)
    options = build_model_options(product, form_data, brand, width, height)

    payload = {
        "input": {"clothing": [image_url]},
        "options": options,
        "output": {"format": "jpeg", "number_of_images": 1},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Claid: submitting on-model job (aspect=%s) for product id=%s",
                options.get("aspect_ratio"), product.get("id"))

    data = (post_json(CLAID_URL, headers, payload, PROVIDER, timeout=60) or {}).get("data") or {}

    job_id = data.get("id")
    result_url = data.get("result_url") or (f"{CLAID_URL}/{job_id}" if job_id else None)
    if not result_url:
        raise AdImageServiceError(
            "Claid accepted the request but did not return a job to track. "
            "Please try again.",
            provider=PROVIDER, detail=f"no result_url/id in: {str(data)[:400]}",
        )

    return _await_result(result_url, api_key)


def _await_result(result_url: str, api_key: str) -> str:
    """Job ke DONE hone tak poll karta hai, phir image download karta hai."""
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    last_status = None

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)

        try:
            response = requests.get(result_url, headers=headers, timeout=30)
        except requests.RequestException as e:
            # Ek poll ka fail ho jana job ka fail hona nahi — agli baar dekh lo.
            logger.warning("Claid: poll failed (%s), retrying", type(e).__name__)
            continue

        if response.status_code >= 400:
            raise AdImageServiceError(
                "Claid could not complete this on-model image. "
                "Please try again or use a different product photo.",
                provider=PROVIDER,
                detail=f"poll HTTP {response.status_code}: {response.text[:400]}",
            )

        try:
            data = (response.json() or {}).get("data") or {}
        except ValueError:
            logger.warning("Claid: non-JSON poll body, retrying")
            continue

        last_status = data.get("status")

        if last_status == "DONE":
            outputs = ((data.get("result") or {}).get("output_objects")) or []
            image_url = outputs[0].get("tmp_url") if outputs else None
            if not image_url:
                raise AdImageServiceError(
                    "Claid finished but returned no image. Please try again.",
                    provider=PROVIDER,
                    detail=f"DONE with no output_objects: {str(data)[:400]}",
                )
            return save_image_from_url(image_url, PROVIDER, suffix=".jpg")

        if last_status in TERMINAL_FAILURE_STATUSES:
            raise AdImageServiceError(
                "Claid could not put this garment on a model. This mode needs a "
                "flat-lay or mannequin photo with no person in it — if the photo "
                "already has a model, use Change scene instead.",
                provider=PROVIDER,
                detail=f"status={last_status} errors={str(data.get('errors'))[:400]}",
            )

    raise AdImageServiceError(
        "Claid is taking longer than expected. Please try again in a moment.",
        provider=PROVIDER,
        detail=f"timed out after {POLL_TIMEOUT_SECONDS}s, last status={last_status}",
    )
