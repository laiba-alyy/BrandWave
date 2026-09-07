"""
Google Veo 3.1 (fal.ai) image-to-video — "premium" plan ka provider.

Wahi FAL_API_KEY chalti hai jo Kling ke liye hai; fal dono ko host karta hai.

Schemas 2026-08-29 ko fal ki LIVE OpenAPI se li gayin
(https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=...), memory se nahi.

── Tier ka intikhab ─────────────────────────────────────────────────────────
Default `veo3.1/lite/image-to-video` hai: sab se sasta tier ($0.03/s @720p,
audio off), aur Kling ki tarah ise bhi wahi form aur wahi guardrails milte hain.
`fast` aur full tiers bhi registry mein hain; FAL_VEO_MODEL se switch ho jate
hain.

── Do ahem constraints jo segment maths tay karte hain ──────────────────────
1) Veo ka duration enum sirf 4s/6s/8s hai — teenon JUFT (even). Un ka koi bhi
   jorr TAAQ (odd) nahi ban sakta, is liye 15s seedha nahi banta. Hum 16s bana
   kar 1s tail trim karte hain (dekho frame_utils.trim_to). Yeh jorr par cut
   nahi — sirf aakhir se thoRa kam — is liye nazar nahi aata.

2) Veo ka apna extend endpoint MAUJOOD hai, lekin:
     - `veo3.1/lite/extend-video` hai hi NAHI (404) — extend sirf fast/full par
       hai, aur full $0.20/s hai yani lite se ~7 guna mehnga.
     - extend ka input video ZYADA SE ZYADA 8s ka ho sakta hai, jab ke us ka
       output us se lamba hota hai — is liye extend SIRF EK BAAR chal sakta
       hai. 20s kisi bhi soorat mein chaining maangta hai.
   Is liye: default (lite) har jagah last-frame chaining karta hai; `fast` par
   15s native extend se banta hai (8+7 = theek 15), aur 10s/20s phir bhi
   chaining se.
"""
import logging
import os

from modules.video_ads.fal_client import VideoAdServiceError
from modules.video_ads.prompt_builder import NEGATIVE_PROMPT

logger = logging.getLogger(__name__)

PROVIDER = "Veo"

# Veo ke i2v endpoints. Teenon ki input schema ek jaisi hai (live OpenAPI se
# verify ki) — farq sirf qeemat aur resolution options ka hai.
#   extend_model : is tier ke saath chalne wala extend endpoint (ya None)
#   max_clip     : ek generation ki sab se lambi clip
MODEL_REGISTRY: dict[str, dict] = {
    "fal-ai/veo3.1/lite/image-to-video": {
        # Lite ka koi extend endpoint NAHI hai — /lite/extend-video 404 deta hai.
        "extend_model": None,
        "max_clip": 8,
    },
    "fal-ai/veo3.1/fast/image-to-video": {
        "extend_model": "fal-ai/veo3.1/fast/extend-video",
        "max_clip": 8,
    },
    "fal-ai/veo3.1/image-to-video": {
        "extend_model": "fal-ai/veo3.1/extend-video",
        "max_clip": 8,
    },
}

DEFAULT_MODEL = "fal-ai/veo3.1/lite/image-to-video"

# Live OpenAPI se: duration ENUM = ['4s','6s','8s'] (nishan "s" ke saath —
# Kling wahan sirf "5"/"10" bhejta hai, ye farq asal hai).
ALLOWED_CLIP_DURATIONS = (4, 6, 8)

# extend ka `duration` open string hai (koi enum nahi), default "7s". Sirf
# documented default par bharosa karte hain — bina test kiye koi aur value
# bhejna paise ka juwa hai.
EXTEND_SECONDS = 7

# 720p default. 1080p/4k sirf mehngai barhate hain aur social ads ke liye 720p
# kaafi hai; text baad mein alag lagta hai to resolution ki bhi zaroorat nahi.
RESOLUTION = os.getenv("FAL_VEO_RESOLUTION", "720p")


def resolve_model() -> tuple[str, dict]:
    """Chala hua Veo model + us ki spec. Anjaan override par fauran saaf error."""
    model_id = (os.getenv("FAL_VEO_MODEL") or "").strip() or DEFAULT_MODEL
    spec = MODEL_REGISTRY.get(model_id)
    if spec is None:
        raise VideoAdServiceError(
            "The configured premium video model is not supported by this server. "
            "Ask your admin to check FAL_VEO_MODEL.",
            provider=PROVIDER,
            detail=f"FAL_VEO_MODEL={model_id!r} not in MODEL_REGISTRY "
                   f"({', '.join(sorted(MODEL_REGISTRY))})",
        )
    return model_id, spec


def build_payload(image_ref: str, prompt: str, seconds: int) -> dict:
    """Veo i2v ka payload. `duration` "8s" ki shakl mein jata hai, "8" nahi."""
    return {
        "image_url": image_ref,
        "prompt": prompt,
        "duration": f"{seconds}s",
        "negative_prompt": NEGATIVE_PROMPT,
        "resolution": RESOLUTION,
        # fal par yeh DEFAULT TRUE hai. Band karna zaroori hai: audio qeemat
        # tqreeban dugni kar deta hai aur music baad mein alag lagega.
        "generate_audio": False,
    }


def build_extend_payload(video_url: str, prompt: str, seconds: int) -> dict:
    """Veo extend ka payload — image nahi, pichli video ka URL leta hai."""
    return {
        "video_url": video_url,
        "prompt": prompt,
        "duration": f"{seconds}s",
        "negative_prompt": NEGATIVE_PROMPT,
        "resolution": RESOLUTION,
        "generate_audio": False,
    }


def _chain(*durations: int) -> list[dict]:
    """Pehla segment base, baqi sab last-frame continuation."""
    return [
        {"seconds": d, "mode": "base" if i == 0 else "last_frame"}
        for i, d in enumerate(durations)
    ]


def build_plans(model_spec: dict) -> dict[int, dict]:
    """
    Is tier ke liye length -> plan.

    15s do mein se ek tareeqe se banta hai:
      - extend wale tiers par: 8s base + 7s NATIVE EXTEND = theek 15s
      - lite par (jahan extend hai hi nahi): 16s bana kar 1s trim
    10s aur 20s hamesha chaining se — 20s isliye ke extend sirf ek baar chal
    sakta hai (us ka input <=8s hona chahiye, output us se lamba hota hai).
    """
    if model_spec.get("extend_model"):
        fifteen = {
            "steps": [
                {"seconds": 8, "mode": "base"},
                {"seconds": EXTEND_SECONDS, "mode": "native_extend"},
            ],
        }
    else:
        fifteen = {"steps": _chain(8, 8), "trim_to": 15}

    return {
        10: {"steps": _chain(6, 4)},
        15: fifteen,
        20: {"steps": _chain(8, 8, 4)},
    }


def get_provider_spec() -> dict:
    """
    engine.run_plan ke liye provider spec.

    Yehi woh jagah hai jahan Veo ka poora farq (model, payload ki shakl, extend
    ka tareeqa, plans) jama hai — engine.py in mein se kuch nahi jaanta.
    """
    model_id, model_spec = resolve_model()
    return {
        "provider": PROVIDER,
        "model_id": model_id,
        # Veo har frame ke neeche-dayen apna sparkle chipka deta hai; Kling
        # nahi. Flag YAHAN hai taake engine ko provider ke naam par shart na
        # lagani pare — wahi usool jo baqi spec ka hai (engine.py Veo ke baare
        # mein kuch nahi jaanta). Dekho modules/video_ads/veo_watermark.py.
        "watermark": "veo",
        "build_payload": build_payload,
        "extend_model_id": model_spec.get("extend_model"),
        "build_extend_payload": build_extend_payload if model_spec.get("extend_model") else None,
        "plans": build_plans(model_spec),
    }
