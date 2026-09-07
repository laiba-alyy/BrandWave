"""
user_plan -> video provider.

Wahi usool jo modules/ads_generation/services/dispatch.py ka hai: naya provider
add karne ke liye sirf do cheezein — us ka service module jo `get_provider_spec()`
deta ho, aur us ka entry yahan. Route ko chhoona nahi parta.

── Plan flag ────────────────────────────────────────────────────────────────
Abhi koi asal billing system NAHI hai. `user_plan` bas ek string hai jo request
ke saath aati hai (default "free"). Jab asal subscriptions aayenge to sirf
itna badlega ke yeh value request ke bajaye user ke DB record se aayegi —
provider selection ka baqi saara code wahi rahega.

    free    -> Kling  (sasta, har account ke liye)
    premium -> Veo 3.1
"""
import logging

from modules.video_ads import kling_service, veo_service
from modules.video_ads.fal_client import VideoAdServiceError
from modules.video_ads.schemas import duration_requires_credits

logger = logging.getLogger(__name__)

# Key = woh plan string jo frontend bhejta hai.
PLAN_PROVIDERS = {
    "free": kling_service,
    "premium": veo_service,
}

DEFAULT_PLAN = "free"

# Plan -> woh naam jo user ko dikhe (UI aur error dono mein).
PLAN_LABELS = {
    "free": "Free — Kling",
    "premium": "Premium — Google Veo 3.1",
}


def normalise_plan(user_plan: str | None) -> str:
    """
    Anjaan/khali plan ko chup-chaap "free" bana deta hai.

    Yeh JAAN BOOJH KAR error nahi deta: plan ek billing concept hai, user ka
    creative input nahi. Kisi purane client ya adhoore plan record ki wajah se
    generation rok dena us se bura hai ke woh sasta provider chala le.
    """
    plan = (user_plan or "").strip().lower()
    if plan not in PLAN_PROVIDERS:
        if plan:
            logger.warning("video_ads: unknown user_plan %r, falling back to %r",
                           user_plan, DEFAULT_PLAN)
        return DEFAULT_PLAN
    return plan


def get_provider_spec(user_plan: str | None) -> tuple[str, dict]:
    """
    Plan ke mutabiq provider spec.

    Return: (normalised plan, spec) — spec wahi shakl jo engine.run_plan maangta
    hai (dekho engine.py ka docstring).
    """
    plan = normalise_plan(user_plan)
    service = PLAN_PROVIDERS[plan]
    return plan, service.get_provider_spec()


def plan_capabilities() -> dict:
    """
    Har plan ke liye woh maloomat jo form ko render karne ke liye chahiye.

    Segment count plan aur provider DONO par munhasir hai (Kling 10s ek
    generation mein karta hai, Veo ko do lagti hain), is liye frontend ko yeh
    backend se aana chahiye — warna cost warning ghalat dikhta.
    """
    out = {}
    for plan, service in PLAN_PROVIDERS.items():
        try:
            spec = service.get_provider_spec()
        except VideoAdServiceError as e:
            # Misconfigured override poore form ko na giraye — us plan ko
            # bas skip kar do, doosra plan phir bhi chalta rahe.
            logger.warning("video_ads: plan %r unavailable: %s", plan, e.detail)
            continue

        durations = []
        for seconds, plan_def in sorted(spec["plans"].items()):
            steps = plan_def["steps"]
            extends = sum(1 for s in steps if s["mode"] != "base")
            native = any(s["mode"] == "native_extend" for s in steps)
            if extends == 0:
                detail = "1 generation"
            else:
                word = "extension" if extends == 1 else "extensions"
                detail = f"1 generation + {extends} {word}"
                if native:
                    detail += " (native)"
            # `locked` frontend ko batata hai ke ye length paid credits
            # maangti hai — taake button pehle hi disabled dikhe, aur user
            # generate dabane ke DO minute baad 402 na khaye.
            durations.append({
                "seconds": seconds,
                "segments": len(steps),
                "label": f"{seconds} seconds",
                "detail": detail,
                "locked": duration_requires_credits(seconds),
            })

        out[plan] = {
            "plan": plan,
            "label": PLAN_LABELS.get(plan, plan),
            "provider": spec["provider"],
            "model_id": spec["model_id"],
            "durations": durations,
        }
    return out


def generate_video_ad(
    user_plan: str | None,
    image_ref: str,
    form_data: dict,
    product: dict | None = None,
    brand=None,
) -> dict:
    """
    Plan ke provider se ek mukammal video ad banao.

    Yeh module ka WAAHID entry point hai jo route istemal karta hai — route ko
    Kling/Veo ka farq, model paths, ya extension ke tareeqe ka ilm nahi hona
    chahiye.

    Prompt yahan banta hai (dono providers ke liye EK hi builder — product-lock
    aur no-text guardrails duplicate nahi hote), aur execution engine karta hai.

    Return: {"video_path", "prompt", "model_id", "provider", "user_plan",
             "segments", "duration_seconds"}
    """
    from modules.video_ads import engine, fal_client
    from modules.video_ads.prompt_builder import (
        build_extension_prompt, build_video_prompt,
    )

    plan_name, spec = get_provider_spec(user_plan)

    duration = form_data.get("duration_seconds") or 10
    plan_def = spec["plans"].get(duration)
    if plan_def is None:
        raise VideoAdServiceError(
            f"Unsupported video length for this plan. Choose one of: "
            f"{', '.join(f'{s}s' for s in sorted(spec['plans']))}.",
            provider=spec["provider"],
            detail=f"duration_seconds={duration!r} not in {spec['provider']} plans",
        )

    # Kling aur Veo dono fal par hain — ek hi FAL_API_KEY, ek hi engine.
    api_key = fal_client.require_fal_key()
    runner = engine.run_plan

    # Wahi prompt builder jo pehle sirf Kling ke liye tha — fixed product-lock
    # layer dono providers par bilkul ek jaisi lagti hai.
    base_prompt = build_video_prompt(form_data, product, brand)
    extension_prompt = build_extension_prompt(base_prompt)

    logger.info(
        "video_ads: plan=%s provider=%s model=%s duration=%ds steps=%s product=%s",
        plan_name, spec["provider"], spec["model_id"], duration,
        [(st["seconds"], st["mode"]) for st in plan_def["steps"]],
        (product or {}).get("id"),
    )

    result = runner(
        spec, plan_def, image_ref, base_prompt, extension_prompt, api_key
    )

    return {
        **result,
        "prompt": base_prompt,
        "model_id": spec["model_id"],
        "provider": spec["provider"],
        "user_plan": plan_name,
    }
