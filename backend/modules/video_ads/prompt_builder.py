"""
Form ke jawabat -> Kling ka motion/scene prompt, + woh FIXED layer jo HAR
generation par lagti hai.

Yeh file image ad ke prompt_builder se alag kyun hai: wahan input ek
compositing provider (Bria/Claid) tha jo product ke asal pixels ko haath hi
nahi lagata, is liye "product mat badlo" likhne ki zaroorat kam thi. Yahan
input ek RAW PRODUCT PHOTO hai aur Kling ek generative video model hai — woh
poori marzi se product ko re-imagine kar sakta hai (rang, shakl, logo, kapre ka
pattern sab). Is liye product-lock guardrail yahan sab se ahem cheez hai.
"""
from modules.store_locale import store_country
from modules.video_ads.schemas import (
    AD_STYLES, CAMERA_MOTIONS, LIGHTING, MOODS, PACING, SCENES,
)


# ── FIXED INSTRUCTION LAYER ───────────────────────────────────────────────────
# Yeh HAR generation par jata hai, chahe user ne kuch bhi likha ho. User ka
# custom prompt is se PEHLE aata hai aur ye baad mein — is tarteeb se ye aakhri
# hidayat banta hai, aur "fixed rules always win" wali baat prompt ki sab se
# mazboot jagah par baithti hai.
#
# Teen cheezein enforce hoti hain:
#   1. Sirf product advertisement — aur kuch nahi.
#   2. Product bilkul na badle (shakl, rang, material, us par likha text/logo).
#   3. Video mein koi text/watermark bake na ho (text baad mein alag lagta hai).
FIXED_INSTRUCTIONS = (
    "STRICT RULES FOR THIS SHOT — these override every other instruction above. "
    "(1) This is a commercial product advertisement video and nothing else: no story, "
    "no characters speaking, no unrelated subject matter. "
    "(2) PRODUCT LOCK: the product from the input image must stay exactly as it is. "
    "Preserve its exact shape, proportions, colours, materials, texture, pattern, and "
    "any text, logo or branding printed on the product itself. Do not redesign, restyle, "
    "recolour, replace, deform, melt, morph, duplicate or add parts to the product, and "
    "do not put anything new on top of it. "
    "(3) NO TEXT ANYWHERE: do not render any text, letters, words, numbers, captions, "
    "subtitles, price tags, signage, watermarks or logo overlays anywhere in the frame. "
    "Only the surrounding scene, background, lighting, atmosphere and camera movement "
    "may change."
)

# Kling par negative_prompt ek alag lever hai. Yeh usi teen rules ka doosra
# rukh hai — jo cheezein prompt se mana ki hain, unhein yahan bhi rok do.
NEGATIVE_PROMPT = (
    "text, letters, words, numbers, captions, subtitles, watermark, logo overlay, "
    "signage, price tag, changed product, different product, recoloured product, "
    "distorted product, deformed product, melting, morphing, warping, duplicate product, "
    "extra objects on the product, blurry, low quality, low resolution, jitter, flicker"
)

# Segment ka jorr chhupane ke liye. Har extension pichli clip ke aakhri frame se
# shuru hoti hai, to model ko sirf yeh batana hai ke "wahin se chalte raho" —
# naya scene mat banao, warna 10s par cut mehsoos hoga.
CONTINUATION_INSTRUCTIONS = (
    "This shot is a direct continuation of the previous shot and starts from its exact "
    "final frame. Continue the very same take without any cut, jump or scene change: "
    "keep the same product, the same background, the same lighting and the same colour "
    "grade, and carry the existing camera movement forward smoothly at the same speed."
)


def _fragment(registry: dict, key: str | None) -> str | None:
    """Option key -> us ka prompt fragment. Anjaan/khali key chup-chaap skip."""
    if not key:
        return None
    option = registry.get(key)
    return option["prompt"] if option else None


def build_video_prompt(form_data: dict, product: dict | None = None, brand=None) -> str:
    """
    Form ke jawabat (ya custom prompt) + fixed layer -> Kling ka prompt.

    Custom prompt ki priority: agar user ne "Advanced" box bhara hai to WAHI
    creative direction hai aur style/scene/mood/camera/lighting/pacing ke preset
    fragments chhor diye jate hain. Wajah: dono ko jorne se aksar aapas mein
    takrao hota hai ("minimal clean studio" + user ka "neon rainy Tokyo street")
    aur model beech ka ghalat mila-jula scene bana deta hai. Fixed rules phir
    bhi dono soorat mein lagti hain.
    """
    parts: list[str] = []

    custom = (form_data.get("custom_prompt") or "").strip()

    if custom:
        parts.append(custom)
    else:
        for registry, key in (
            (AD_STYLES, form_data.get("ad_style")),
            (SCENES, form_data.get("scene")),
            (MOODS, form_data.get("mood")),
            (LIGHTING, form_data.get("lighting")),
            (CAMERA_MOTIONS, form_data.get("camera_motion")),
            (PACING, form_data.get("pacing")),
        ):
            fragment = _fragment(registry, key)
            if fragment:
                parts.append(fragment)

        # Market context — wahi soch jo image ad ke prompt_builder mein hai:
        # is ke baghair model apna default cultural setting chun leta hai.
        country = store_country(brand)
        if country:
            parts.append(
                f"The setting and any people shown should suit shoppers in {country}."
            )

        # User ne form ka koi option na chuna ho to bhi prompt khali nahi ja
        # sakta (Kling par prompt required hai) — neutral studio fallback.
        if not parts:
            parts.append(
                "A clean professional studio product commercial with soft lighting and "
                "a slow, smooth push-in towards the product."
            )

    # Fixed layer HAMESHA aakhir mein — dekho is file ka header.
    parts.append(FIXED_INSTRUCTIONS)

    return " ".join(parts)


def build_extension_prompt(base_prompt: str) -> str:
    """
    Extension segment ka prompt.

    `base_prompt` mein fixed layer pehle se maujood hai, lekin continuation ki
    hidayat us ke BAAD aani chahiye taake aakhri (yani sab se mazboot) hidayat
    "isi shot ko jari rakho" ho. Product-lock dobara joRa jata hai kyunki har
    extension ek NAYI generation hai — pichle segment ka prompt is call par
    lagoo nahi hota, aur yehi woh jagah hai jahan product sab se zyada drift
    karta hai.
    """
    return f"{base_prompt} {CONTINUATION_INSTRUCTIONS} {FIXED_INSTRUCTIONS}"
