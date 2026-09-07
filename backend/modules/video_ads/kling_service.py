"""
Kling (fal.ai) image-to-video — base generation + extension chain.

── Model path kyun registry mein hai, hardcoded nahi ────────────────────────
fal par Kling ke versions tezi se badalte hain aur SCHEMA bhi saath badalti
hai: v2.1 par source image ka field `image_url` hai, jab ke v2.6/v3 par wahi
field `start_image_url` ho gaya hai, aur naye versions par `generate_audio`
DEFAULT TRUE hai. Sirf model string badal dene se request chup-chaap 422 deti.
Is liye har model apne field mapping ke saath registry mein hai, aur admin
FAL_KLING_MODEL se switch kar sakta hai bina code chhue.

Registry ki tafseelat 2026-08-29 ko fal ke live docs se verify ki gayin.

── Extension kaise hoti hai ─────────────────────────────────────────────────
fal par Kling ka koi alag "extend"/"continuation" endpoint MAUJOOD NAHI hai
(29 Aug 2026 ko model gallery check ki — sirf xAI Grok ke paas extend-video
hai). Kling ki apni video-extension bhi andar se yehi karti hai: pichli clip ka
AAKHRI FRAME lo aur usi se agli generation shuru karo. Hum wahi documented
tareeqa istemal karte hain —

    10s  ->  [10s base]
    15s  ->  [10s base] + [5s extension jo base ke aakhri frame se shuru]
    20s  ->  [10s base] + [5s] + [5s]

— aur phir teenon ko ek file bana dete hain. Ye "alag alag clips ka stitch"
nahi hai: har segment ka pehla frame pichle ka aakhri frame hai, is liye jorr
par jump nazar nahi aata.
"""
import logging
import os

from modules.video_ads.fal_client import VideoAdServiceError
from modules.video_ads.prompt_builder import NEGATIVE_PROMPT

logger = logging.getLogger(__name__)

PROVIDER = "Kling"


# key = fal model id, value = us model ki schema ki woh baatein jo hum par asar
# daalti hain.
#   image_field   : source image ka parameter naam (version ke saath badla hai)
#   audio_field   : audio band karne wala flag, ya None agar model audio banata
#                   hi nahi (v2.1 par audio track hai hi nahi — sab se sasta)
#   supports_cfg  : cfg_scale bhejna theek hai ya nahi
MODEL_REGISTRY: dict[str, dict] = {
    "fal-ai/kling-video/v2.1/standard/image-to-video": {
        "image_field": "image_url", "audio_field": None, "supports_cfg": True,
    },
    "fal-ai/kling-video/v2.1/pro/image-to-video": {
        "image_field": "image_url", "audio_field": None, "supports_cfg": True,
    },
    "fal-ai/kling-video/v2.1/master/image-to-video": {
        "image_field": "image_url", "audio_field": None, "supports_cfg": True,
    },
    "fal-ai/kling-video/v2.6/pro/image-to-video": {
        "image_field": "start_image_url", "audio_field": "generate_audio",
        "supports_cfg": False,
    },
    "fal-ai/kling-video/v3/standard/image-to-video": {
        "image_field": "start_image_url", "audio_field": "generate_audio",
        "supports_cfg": True,
    },
    "fal-ai/kling-video/v3/pro/image-to-video": {
        "image_field": "start_image_url", "audio_field": "generate_audio",
        "supports_cfg": True,
    },
}

# Default: v2.1 standard. Yeh sab se sasta image-to-video tier hai
# (5s = $0.28, 10s = $0.50) aur is mein audio track HAI HI NAHI — yani "audio
# off" schema se hi tay hai, kisi flag par bharosa nahi karna parta. Music baad
# mein alag layer ke tor par lagega.
DEFAULT_MODEL = "fal-ai/kling-video/v2.1/standard/image-to-video"

# Kling par duration ek ENUM hai aur sirf "5" ya "10" leta hai — is liye
# LENGTH_PLANS ke segments bhi anhi do value par bane hain.
ALLOWED_SEGMENT_DURATIONS = ("5", "10")

# Prompt par kitna sakhti se chalna hai. 0.5 fal ka default hai; thoRa upar
# rakhna product-lock aur "no text" guardrails ko zyada wazan deta hai, lekin
# itna upar nahi ke motion be-jaan ho jaye.
CFG_SCALE = float(os.getenv("FAL_KLING_CFG_SCALE", "0.6"))


def resolve_model() -> tuple[str, dict]:
    """
    Chala hua model + us ki schema info.

    FAL_KLING_MODEL set ho lekin registry mein na ho to fauran saaf error —
    warna request fal par jati aur 422 ke saath paisa/waqt zaya hota.
    """
    model_id = (os.getenv("FAL_KLING_MODEL") or "").strip() or DEFAULT_MODEL
    spec = MODEL_REGISTRY.get(model_id)
    if spec is None:
        raise VideoAdServiceError(
            "The configured video model is not supported by this server. "
            "Ask your admin to check FAL_KLING_MODEL.",
            detail=f"FAL_KLING_MODEL={model_id!r} not in MODEL_REGISTRY "
                   f"({', '.join(sorted(MODEL_REGISTRY))})",
        )
    return model_id, spec


def build_payload_for(spec: dict):
    """
    Is model ke liye engine wala payload builder deta hai.

    engine.run_plan ko (image_ref, prompt, seconds) wala saada callable chahiye,
    jab ke Kling ka payload model ki schema par munhasir hai — is liye spec
    yahan closure mein band kar dete hain.
    """
    def build_payload(image_ref: str, prompt: str, seconds: int) -> dict:
        payload = {
            spec["image_field"]: image_ref,
            "prompt": prompt,
            # Kling par duration sirf "5"/"10" hai — Veo ki tarah "8s" NAHI.
            "duration": str(seconds),
            "negative_prompt": NEGATIVE_PROMPT,
        }
        if spec["supports_cfg"]:
            payload["cfg_scale"] = CFG_SCALE
        if spec["audio_field"]:
            # Naye versions par yeh DEFAULT TRUE hai. Explicitly band karna
            # zaroori hai: audio mehnga parta hai aur music baad mein lagega.
            payload[spec["audio_field"]] = False
        return payload

    return build_payload


def _chain(*durations: int) -> list[dict]:
    """Pehla segment base, baqi sab last-frame continuation."""
    return [
        {"seconds": d, "mode": "base" if i == 0 else "last_frame"}
        for i, d in enumerate(durations)
    ]


# Kling ke clips 5s ya 10s ke hote hain, aur 10/15/20 teenon un ka theek jorr
# hain — is liye yahan Veo wali trim ki zaroorat nahi parti.
PLANS: dict[int, dict] = {
    10: {"steps": _chain(10)},
    15: {"steps": _chain(10, 5)},
    20: {"steps": _chain(10, 5, 5)},
}


def get_provider_spec() -> dict:
    """
    engine.run_plan ke liye provider spec.

    Kling ka fal par koi extend endpoint nahi hai (29 Aug 2026 ko model gallery
    check ki), is liye extend_model_id None hai aur har extension last-frame
    chaining se hoti hai.
    """
    model_id, spec = resolve_model()
    return {
        "provider": PROVIDER,
        "model_id": model_id,
        "build_payload": build_payload_for(spec),
        "extend_model_id": None,
        "build_extend_payload": None,
        "plans": PLANS,
    }
