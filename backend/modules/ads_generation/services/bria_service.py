"""
Bria — "Lifestyle Product Shot by Text"  (generation_mode = "scene")

Kis liye: product ya model PEHLE SE photo mein maujood hai; sirf scene/background
badalna hai. Perfume, bottle, bag, jewellery, aur woh clothing photos jo already
model par shot hain.

gpt-image-1 se buniyadi farq: Bria product ko REPAINT nahi karta — usi pixels ko
naye background par COMPOSITE karta hai. Isi liye product bilkul waisa hi rehta
hai, jo is module ki asal zaroorat hai.

Endpoint/format 2026-08-29 ko docs se verify kiye gaye:
    POST https://engine.prod.bria-api.com/v1/product/lifestyle_shot_by_text
    header : api_token: <BRIA_API_KEY>
    body   : {image_url, scene_description, sync, num_results,
              placement_type, aspect_ratio, optimize_description}
    200    : {"result": [[image_url, seed, session_id], ...]}
"""
import logging

from modules.ads_generation.prompt_builder import build_scene_description
from modules.ads_generation.services.common import (
    AdImageServiceError,
    aspect_ratio_label,
    post_json,
    product_image_url,
    require_api_key,
    save_image_from_url,
)

logger = logging.getLogger(__name__)

BRIA_URL = "https://engine.prod.bria-api.com/v1/product/lifestyle_shot_by_text"

PROVIDER = "Bria"


def generate_scene_image(product: dict, form_data: dict, brand, width: int, height: int) -> str:
    """
    Asli product photo + scene description -> naya lifestyle shot.

    Return: local file path, bilkul usi shape mein jo openai_service deta tha,
    taake image_polish aur gallery bina tabdeeli chalte rahen.
    """
    api_key = require_api_key("BRIA_API_KEY", PROVIDER)
    image_url = product_image_url(product, PROVIDER)
    scene_description = build_scene_description(product, form_data, brand)

    payload = {
        "image_url": image_url,
        "scene_description": scene_description,
        # sync=True: ek hi result chahiye, is liye block karna theek hai aur
        # route ko polling nahi likhni parti. (Docs: automatic placement ke
        # saath sync false hona chahiye — automatic_aspect_ratio alag hai aur
        # sync=True ke saath verify ho chuka hai.)
        "sync": True,
        "num_results": 1,
        # placement_type="original" shot_size/aspect_ratio dono ko ignore kar
        # deta hai (test mein output hamesha source ka 836x1254 aata tha).
        # automatic_aspect_ratio hi woh mode hai jo maanga hua ratio deta hai.
        "placement_type": "automatic_aspect_ratio",
        "aspect_ratio": aspect_ratio_label(width, height),
        # Bria scene description ko Llama se behtar likhwata hai — quality is se
        # numayan behtar hai. Guardrails phir bhi bheje jate hain; asal tahaffuz
        # ye hai ke Bria product ko repaint karta hi nahi.
        "optimize_description": True,
    }

    logger.info("Bria: requesting lifestyle shot (aspect=%s) for product id=%s",
                payload["aspect_ratio"], product.get("id"))

    data = post_json(BRIA_URL, {"api_token": api_key}, payload, PROVIDER)

    results = data.get("result") or []
    if not results:
        raise AdImageServiceError(
            "Bria did not return an image for this product. "
            "Try a different product or another generation mode.",
            provider=PROVIDER, detail=f"empty result: {str(data)[:500]}",
        )

    first = results[0]
    result_url = first[0] if isinstance(first, (list, tuple)) else first
    if not result_url:
        raise AdImageServiceError(
            "Bria returned an empty image link. Please try again.",
            provider=PROVIDER, detail=f"unexpected result shape: {str(first)[:300]}",
        )

    return save_image_from_url(result_url, PROVIDER, suffix=".png")
