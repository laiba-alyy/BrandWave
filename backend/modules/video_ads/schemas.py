"""
Video ad module ke request/response models AUR form ka option registry.

Registry yahan (backend par) rehta hai aur `GET /api/video-ads/options` se
frontend ko jata hai. Wajah: har option ke saath us ka PROMPT FRAGMENT bandha
hua hai. Agar labels frontend mein hard-code hote to prompt mapping do jagah
rehti aur ek jagah badalne par chup-chaap purana prompt jata rehta.
"""
import os
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Pydantic `model_` se shuru hone wale fields par warning deta hai (woh namespace
# uske apne `model_dump`/`model_config` ke liye mehfooz hai). Hamara `model_id`
# fal ka model path hai aur naam wazeh hai, is liye namespace khali kar dete hain.
_ALLOW_MODEL_PREFIX = ConfigDict(protected_namespaces=())


# ── Form options ──────────────────────────────────────────────────────────────
# Har option: key -> {"label": user ko dikhne wala naam,
#                     "prompt": woh tukra jo Kling ke prompt mein jata hai}
#
# `prompt` tukre SCENE, LIGHT, CAMERA aur MOTION ke baare mein hain — product ke
# baare mein NAHI. Product input image se aata hai aur usay badalna mana hai
# (dekho prompt_builder.FIXED_INSTRUCTIONS), is liye kisi bhi fragment mein
# product ka hulia mat likho.

AD_STYLES = {
    "elegant_luxury": {
        "label": "Elegant & Luxury",
        "prompt": "An elegant, high-end luxury advertising film look, refined and premium, "
                  "with slow deliberate movement and rich depth of field.",
    },
    "fun_energetic": {
        "label": "Fun & Energetic",
        "prompt": "A fun, upbeat, energetic commercial look, lively and colourful, "
                  "with playful momentum.",
    },
    "minimal_clean": {
        "label": "Minimal & Clean",
        "prompt": "A minimal, clean, modern commercial look with lots of negative space "
                  "and calm, uncluttered composition.",
    },
    "bold_dramatic": {
        "label": "Bold & Dramatic",
        "prompt": "A bold, dramatic, cinematic commercial look with strong contrast "
                  "and a striking hero presentation.",
    },
    "warm_festive": {
        "label": "Warm & Festive",
        "prompt": "A warm, festive, celebratory commercial look with a joyful "
                  "seasonal atmosphere.",
    },
}

SCENES = {
    "studio": {
        "label": "Studio",
        "prompt": "Set on a clean professional studio backdrop with a seamless surface.",
    },
    "outdoor": {
        "label": "Outdoor / Nature",
        "prompt": "Set outdoors in a natural environment with soft depth and gentle "
                  "background movement.",
    },
    "lifestyle": {
        "label": "Lifestyle / Home",
        "prompt": "Set in a tasteful lifestyle interior, like a styled home or cafe table, "
                  "with a softly blurred background.",
    },
    "festive": {
        "label": "Festive / Celebration",
        "prompt": "Set in a festive celebration scene with warm decorative bokeh lights "
                  "in the background.",
    },
    "urban": {
        "label": "Urban / Street",
        "prompt": "Set in a modern urban environment with clean architectural lines "
                  "and a shallow depth of field.",
    },
    "luxury_interior": {
        "label": "Luxury Interior",
        "prompt": "Set in an opulent luxury interior with marble, glass and metallic "
                  "surfaces reflecting softly.",
    },
}

MOODS = {
    "calm_premium": {"label": "Calm & Premium",
                     "prompt": "The mood is calm, confident and premium."},
    "upbeat_playful": {"label": "Upbeat & Playful",
                       "prompt": "The mood is upbeat, cheerful and playful."},
    "cinematic_moody": {"label": "Cinematic & Moody",
                        "prompt": "The mood is cinematic, moody and atmospheric."},
    "fresh_bright": {"label": "Fresh & Bright",
                     "prompt": "The mood is fresh, bright and airy."},
    "romantic_soft": {"label": "Romantic & Soft",
                      "prompt": "The mood is romantic, soft and dreamy."},
}

CAMERA_MOTIONS = {
    "gentle_zoom": {
        "label": "Gentle zoom in",
        "prompt": "Camera: a slow, smooth push-in towards the product, steady and controlled.",
    },
    "slow_pan": {
        "label": "Slow pan",
        "prompt": "Camera: a slow, smooth horizontal pan across the scene, steady and controlled.",
    },
    "slow_orbit": {
        "label": "Slow orbit",
        "prompt": "Camera: a slow, smooth arc orbiting around the product, steady and controlled.",
    },
    "dynamic": {
        "label": "Dynamic",
        "prompt": "Camera: dynamic but smooth movement with a confident sweep and a gentle "
                  "parallax shift.",
    },
    "static_hero": {
        "label": "Static hero shot",
        "prompt": "Camera: locked off and static; only the light, background and atmosphere "
                  "move subtly.",
    },
}

LIGHTING = {
    "soft_daylight": {"label": "Soft daylight",
                      "prompt": "Lighting: soft, natural daylight with gentle shadows."},
    "golden_hour": {"label": "Warm golden hour",
                    "prompt": "Lighting: warm golden-hour light with a soft glow."},
    "bright_studio": {"label": "Bright studio",
                      "prompt": "Lighting: bright, even studio lighting with clean highlights."},
    "dramatic_spotlight": {"label": "Dramatic spotlight",
                           "prompt": "Lighting: a dramatic directional spotlight with deep "
                                     "falloff around the edges."},
}

PACING = {
    "slow": {"label": "Slow & luxurious",
             "prompt": "Pacing: slow and luxurious, one single continuous unhurried shot."},
    "steady": {"label": "Steady",
               "prompt": "Pacing: steady and even, one single continuous shot."},
    "punchy": {"label": "Fast & punchy",
               "prompt": "Pacing: energetic and punchy, but still one single continuous shot."},
}


# ── Length plans ─────────────────────────────────────────────────
# Woh lengths jo user chun sakta hai. Har length ka SEGMENT PLAN ab provider ke
# paas rehta hai, yahan nahi — kyunki har model ki max clip length alag hai:
#
#   Kling : clips 5s/10s   -> 10 = [10],    15 = [10,5],  20 = [10,5,5]
#   Veo   : clips 4s/6s/8s -> 10 = [6,4],   15 = [8,8]+trim, 20 = [8,8,4]
#
# Veo ke teenon durations JUFT hain, is liye un ka koi jorr 15 (TAAQ) nahi
# banta — wahan 16s bana kar 1s trim hota hai. Yeh tafseel providers ke andar
# hai; dekho kling_service.PLANS aur veo_service.build_plans().
SUPPORTED_DURATIONS = (10, 15, 20)

DEFAULT_DURATION = 10

# ── Kaun si length paid credits maangti hai ──────────────────────────────
#
# 20s ki generation 3 billable segments chalati hai (10 wali sirf 1). Free/
# trial credits par ye teen guna kharcha hai, aur demo ke doran koi bhi user
# usay chun kar poora balance ek hi video mein khatam kar sakta hai.
#
# Is liye 20s DEFAULT par band hai. Credits khareedne ke baad kholne ke liye
# sirf env badalni hai — code nahi:
#
#     VIDEO_PAID_DURATIONS=          -> sab khuli
#     VIDEO_PAID_DURATIONS=15,20     -> 15 aur 20 dono band
def _paid_durations() -> frozenset[int]:
    raw = os.getenv("VIDEO_PAID_DURATIONS")
    if raw is None:
        return frozenset({20})
    out = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.add(int(chunk))
    return frozenset(out)


PAID_DURATIONS = _paid_durations()

# Jo lengths abhi bhi khuli hain — error message mein yehi ginwate hain.
FREE_DURATIONS = tuple(s for s in SUPPORTED_DURATIONS if s not in PAID_DURATIONS)


def duration_requires_credits(seconds: int) -> bool:
    return seconds in PAID_DURATIONS


# End card ka text video ke AAKHIR mein lagta hai (dekho end_card.py).
# Ye provider ko nahi jata — locally moviepy se lagta hai, is liye iska koi
# credit nahi lagta aur ye video ko ~3s lamba bhi kar deta hai.
MAX_END_CARD_CHARS = 90

# "Your idea, in your own words" — woh EK line jis se prompt likhwaya jata hai
# (dekho modules/video_ads/prompt_drafter.py). Chhoti JAAN BOOJH KAR: ye poora
# prompt nahi, sirf ishara hai. Poora likhna ho to Advanced box mojood hai.
MAX_IDEA_CHARS = 300

# Source: video ka input image kahan se aa raha hai.
#   "product"  -> scraped catalogue ka product image (DEFAULT / primary rasta)
#   "image_ad" -> pehle se bana hua image ad (generated_ads.id)
VIDEO_SOURCES = ("product", "image_ad")
DEFAULT_SOURCE = "product"

# Prompt kahan se aaya. Sirf record ke liye — generation ka rasta is se nahi
# badalta (dono soorton mein wahi prompt_guard aur wahi fixed layer lagti hai).
#
# Ye rakhna is liye zaroori hai ke bura result aane par ye sawal sab se pehle
# aata hai: prompt AI ne likha tha ya user ne? Us ke baghair drafter ki quality
# gallery se kabhi maapi nahi ja sakti.
#   "form"   -> user ne prompt likha hi nahi, video form ke options se bana
#   "ai"     -> "Write the prompt for me" ka draft (user ne edit kiya ho ya na)
#   "manual" -> user ne khud likha
PROMPT_SOURCES = ("form", "ai", "manual")


def _options_payload(registry: dict) -> list[dict]:
    """Registry ko frontend ke liye ordered list bana deta hai (prompt ke baghair)."""
    return [{"key": k, "label": v["label"]} for k, v in registry.items()]


def build_options_response() -> dict:
    """
    Woh sab kuch jo form ko render karne ke liye chahiye.

    `durations` ab har PLAN ke liye alag aata hai: segment count provider par
    munhasir hai (Kling 10s ek generation mein deta hai, Veo ko do lagti hain),
    to cost warning bhi plan ke saath badalta hai. Local import circular import
    se bachne ke liye hai — dispatch providers ko import karta hai aur woh is
    file ko.

    `prompt` fragments JAAN BOOJH KAR bahar nahi bheje jate.
    """
    from modules.video_ads.dispatch import DEFAULT_PLAN, plan_capabilities

    return {
        "ad_styles": _options_payload(AD_STYLES),
        "scenes": _options_payload(SCENES),
        "moods": _options_payload(MOODS),
        "camera_motions": _options_payload(CAMERA_MOTIONS),
        "lighting": _options_payload(LIGHTING),
        "pacing": _options_payload(PACING),
        "plans": plan_capabilities(),
        "default_plan": DEFAULT_PLAN,
    }


# ── Request / Response ────────────────────────────────────────────────────────

class DraftPromptRequest(BaseModel):
    """
    "Write the prompt for me" — form ke jawabat + user ki ek line.

    Ye generate se ALAG call hai aur is mein koi fal credit kharch nahi hota.
    Product/brand sirf context ke liye chahiye (naam aur market), video ka
    input image is call mein shamil nahi hota.
    """
    brand_id: int

    # Product ka naam/category/description prompt mein context ke tor par jate
    # hain. Sab optional — na milein to draft phir bhi ban jata hai, bas thora aam.
    #
    # `source` wahi do raste hain jo generate par hain. Ye yahan is liye chahiye
    # ke image_ad wale raste par product catalogue se nahi, us bane hue ad ke
    # record se milta hai (generated_ads.product_id) — aur us ke baghair drafter
    # ko pata hi nahi chalta ke video kis cheez ka hai.
    source: str = DEFAULT_SOURCE
    product_id: Optional[int] = None
    product_index: Optional[int] = None
    # source="image_ad" ke liye: generated_ads.id
    source_ad_id: Optional[int] = None

    # Form ke wahi chhe jawabat jo generate par jate hain.
    ad_style: Optional[str] = None
    scene: Optional[str] = None
    mood: Optional[str] = None
    camera_motion: Optional[str] = None
    lighting: Optional[str] = None
    pacing: Optional[str] = None

    # "Zehen mein kya scene hai" — ek line, Roman Urdu bhi chalti hai. Khali
    # ho to drafter sirf form ke options se teen alag scene soch leta hai.
    idea: Optional[str] = Field(default=None, max_length=MAX_IDEA_CHARS)


class DraftPromptResponse(BaseModel):
    # Teen options — user chunta hai, phir chahe to edit karta hai.
    prompts: list[str]
    # Woh farmaishein jo fixed rules rok dengi (frame mein text, ya product ki
    # tabdeeli). Prompt phir bhi banta hai; ye sirf batati hain ke kya nahi
    # hoga aur us ka theek rasta kya hai (misal: End card).
    warnings: list[str] = []


class GenerateVideoAdRequest(BaseModel):
    brand_id: int
    user_id: str

    # Input image ka source. Default "product" — yehi asal rasta hai.
    source: str = DEFAULT_SOURCE
    # source="product" ke liye: product_id authoritative hai; product_index sirf
    # un purane profiles ke liye jo product ids se pehle scrape hue the.
    product_id: Optional[int] = None
    product_index: Optional[int] = None
    # source="image_ad" ke liye: generated_ads.id
    source_ad_id: Optional[int] = None

    # Form ke jawabat — sab optional, taake adhoora form bhi chal jaye.
    ad_style: Optional[str] = None
    scene: Optional[str] = None
    mood: Optional[str] = None
    camera_motion: Optional[str] = None
    lighting: Optional[str] = None
    pacing: Optional[str] = None

    # "Advanced" box. Bhara ho to yehi creative direction banta hai aur form ke
    # style/scene/mood/camera fragments chhor diye jate hain (dekho
    # prompt_builder.build_video_prompt). Fixed rules phir bhi lagti hain.
    custom_prompt: Optional[str] = None

    # Prompt kis rraste se aaya — dekho PROMPT_SOURCES. Anjaan/khali value
    # route par khud-ba-khud theek ho jati hai, is liye purane clients (jo ye
    # field bhejte hi nahi) bilkul waise hi chalte rehte hain.
    prompt_source: Optional[str] = None

    # Video ke aakhir mein chhapne wala text (optional). Provider ko nahi jata.
    end_card_text: Optional[str] = Field(default=None, max_length=300)

    duration_seconds: int = DEFAULT_DURATION

    # Kaun sa provider chalega. Abhi koi asal billing nahi — yeh sirf ek flag
    # hai jo request ke saath aata hai (dekho modules/video_ads/dispatch.py).
    #   "free" -> Kling, "premium" -> Veo 3.1
    # Anjaan value chup-chaap "free" ban jati hai; plan creative input nahi hai
    # ke us par generation rok di jaye.
    user_plan: str = "free"


class GenerateVideoAdResponse(BaseModel):
    model_config = _ALLOW_MODEL_PREFIX

    success: bool
    video_id: int
    video_url: str
    product_name: Optional[str] = None
    duration_seconds: int
    segments: int
    model_id: str
    provider: str
    user_plan: str

    # Prompt na-qabil-e-istemal tha aur form se video bana — UI ye line
    # dikhati hai. Warna user ko lagta hai uska prompt chala tha.
    prompt_notice: Optional[str] = None
    # Video ke aakhir mein card laga ya nahi.
    end_card: bool = False


class VideoGalleryItem(BaseModel):
    video_id: int
    product_name: Optional[str] = None
    video_path: str
    duration_seconds: Optional[int] = None
    segments: Optional[int] = None
    source: Optional[str] = None
    provider: Optional[str] = None
    user_plan: Optional[str] = None
    created_at: str


class VideoGalleryDetail(VideoGalleryItem):
    model_config = _ALLOW_MODEL_PREFIX

    source_image_url: Optional[str] = None
    ad_style: Optional[str] = None
    scene: Optional[str] = None
    mood: Optional[str] = None
    camera_motion: Optional[str] = None
    lighting: Optional[str] = None
    pacing: Optional[str] = None
    custom_prompt: Optional[str] = None
    # "form" | "ai" | "manual" — dekho PROMPT_SOURCES.
    prompt_source: Optional[str] = None
    model_id: Optional[str] = None
    final_prompt: Optional[str] = None
