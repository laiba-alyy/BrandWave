"""
"Write the prompt for me" — form ke jawabat + user ki ek line se qabil-e-istemal
video prompt.

MASLA jo ye hal karta hai:

    "Advanced: write your own prompt" ek KHALI textarea hai. Jo user technical
    nahi (yani hamare zyada tar users) wo ya to usay khali chhor deta hai, ya
    kuch aisa likh deta hai jo prompt_guard rad kar deta hai. Doosri soorat
    mein video form ke options se banta hai magar user samajhta hai ke us ka
    likha hua chala tha — aur natija bura aane par usay wajah kabhi nahi milti.

HAL: khali page ka masla hi khatam kar do. User form pehle hi bhar chuka hota
hai (style/scene/mood/lighting/camera/pacing), aur jo scene us ke zehen mein
hai wo ek line mein likh sakta hai — Roman Urdu mein bhi. LLM in dono ko mila
kar 2-3 jumlon ka cinematic prompt likh deta hai, jise user EDIT kar sakta hai
ya waise hi rakh sakta hai.

LLM ka kaam yahan TARJUMA hai, IJAAD nahi: intent pehle se structured shakl
mein mojood hai, usay bas achhe alfaz mein dhalna hai. Isi liye ye "ad concept
soch kar do" se kahin zyada bharosemand chalta hai.

── Ye `generate` se ALAG endpoint kyun hai ──────────────────────────────────
Prompt likhne mein koi fal credit kharch nahi hota — sirf ek chhoti text call.
User ko prompt DEKH kar, edit kar ke, phir video banana chahiye. Agar ye
generate ke andar hota to har draft ek billable generation ban jata.

── Lane ka intikhab ────────────────────────────────────────────────────────
Purpose "video_prompt" JAAN BOOJH KAR ad_copy wali lane par hai: PRIMARY key
(GROQ_API_KEY). Chatbot aur assistant usi model par hain magar ALT key
(GROKAPIKEY2) par — aur Groq ki limits per-model PER-KEY hain, is liye dono
ek doosre ko dheema nahi karte.

Model ab openai/gpt-oss-120b hai. Pehle groq/compound-mini tha (70,000 TPM ke
liye), magar Groq ne compound aur compound-mini dono retire kar diye
(decommission: 21 Sept 2026). Dekho modules/llm_config.py ka PURPOSE_MODELS.
"""
import json
import logging
import re

from modules.llm_config import chat_completion, check_raw_response
from modules.store_locale import store_country
from modules.video_ads.prompt_guard import looks_usable
from modules.video_ads.schemas import (
    AD_STYLES, CAMERA_MOTIONS, LIGHTING, MOODS, MAX_IDEA_CHARS, PACING, SCENES,
)

logger = logging.getLogger(__name__)

# Har draft ki hadd. prompt_guard.MAX_VIDEO_PROMPT 600 hai, aur wahan se guzarna
# LAZMI hai warna user ka apna chuna hua draft generate par 400 kha jata. 500 par
# rakha hai taake user us mein thora izafa bhi kar sake.
MAX_DRAFT_CHARS = 500

# Kitne options dikhane hain. Teen — log likhne se behtar CHUNTE hain, aur teen
# ek hi call mein aa jate hain (alag calls teen guna latency hoti).
DRAFT_COUNT = 3

# AB YE WAQAI LAGTA HAI. Pehle model compound-mini tha, jo max_tokens ko chup-
# chaap nazarandaz karta tha — yani ye number bemani tha. gpt-oss ise ENFORCE
# karta hai, aur us se BARHKAR reasoning tokens bhi isi budget se kharch karta
# hai. Teen prompts ka asal output ~300 tokens hai; baqi reasoning ke liye
# chhora hai, warna jawab beech mein katta hai aur check_finish_reason
# TruncatedCompletionError phenkta hai.
DRAFT_MAX_TOKENS = 2500


class PromptDraftError(RuntimeError):
    """
    Draft nahi ban saka.

    Ye HAR soorat mein mehfooz hai: koi video credit kharch nahi hua, aur user
    dobara koshish kar sakta hai ya khud likh sakta hai. Is liye route ise 502
    banata hai, 500 nahi.
    """

    def __init__(self, message: str, detail: str = ""):
        super().__init__(detail or message)
        self.message = message
        self.detail = detail or message


# ── Woh farmaishein jo ho hi nahi saktin ──────────────────────────────────────
#
# prompt_builder.FIXED_INSTRUCTIONS do cheezein HAR generation par rokti hai:
# frame mein koi text, aur product mein koi tabdeeli. User ko ye baat nahi pata
# hoti — wo "50% OFF likh do" ya "isay laal kar do" likhta hai, video ban jata
# hai, aur us mein wo cheez hoti hi nahi. Us ke paas koi wajah nahi hoti.
#
# Is liye ye CHECK LLM par nahi chhora: regex deterministic hai aur har dafa
# wahi jawab deta hai. LLM sirf prompt likhta hai; batana ke "ye nahi ho sakta"
# yahan hota hai.
_TEXT_REQUEST_PATTERNS = (
    r"\btexts?\b", r"\bcaptions?\b", r"\bsubtitles?\b",
    r"\bwrit(?:e|ten|ing)\b", r"\bspell(?:ed|ing)?\b", r"\blogos?\b",
    r"\bwatermarks?\b", r"\bsignage\b", r"\bsign ?boards?\b", r"\bbanners?\b",
    r"\bheadlines?\b", r"\bslogans?\b", r"\btaglines?\b", r"\bprice tags?\b",
    r"\bdiscounts?\b", r"\d+\s*%",
    # Roman Urdu — "likho", "likh do", "likha hua"
    r"\blikh",
)

# Rang ki list ek jagah — do patterns is par ghoomte hain.
_COLOURS = (
    "red|blue|green|black|white|pink|yellow|gold(?:en)?|silver|purple|orange|"
    "brown|grey|gray|beige|maroon|navy|teal"
)

_PRODUCT_CHANGE_PATTERNS = (
    # "change the colour", "change its design", "change product"
    r"\bchange\s+(?:the|its|their)?\s*(?:colou?r|shape|design|product|material)\b",
    r"\brecolou?r\b", r"\bre-?design\b", r"\bdifferent\s+colou?r\b",
    # "make it red", "make the shoes red", "turn the bottle gold", "paint it black"
    rf"\b(?:make|turn|paint)\s+(?:it|them|the\s+\w+(?:\s+\w+)?)\s+(?:{_COLOURS})\b",
    # "in red instead", "red version of it"
    rf"\b(?:{_COLOURS})\s+(?:version|instead)\b",
    # Roman Urdu — "rang badal do", "rang change karo", "design badlo"
    r"\brang\s+(?:badal|change)", r"\bbadal\s+(?:do|kar)", r"\bbadlo\b",
)

TEXT_WARNING = (
    "Videos cannot show text — the AI model renders letters wrongly, so our "
    "rules block them everywhere in the frame. Use the End card text field "
    "below instead: it is drawn on the server, comes out clean, and costs no "
    "extra credits."
)

PRODUCT_WARNING = (
    "The product itself cannot be changed — its colour, shape, material and "
    "any branding on it stay exactly as they are in the photo. Only the scene, "
    "background, lighting and camera movement around it can change."
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def idea_warnings(idea: str | None) -> list[str]:
    """
    User ki line mein koi aisi farmaish hai jo fixed rules rok dengi?

    Ye BLOCK nahi karta — sirf batata hai. Shak ka faida user ko: ho sakta hai
    "banner" us ne mahol ke liye likha ho. Prompt phir bhi banta hai, bas us ke
    saath ye line chali jati hai.
    """
    text = (idea or "").strip()
    if not text:
        return []

    warnings: list[str] = []
    if _matches_any(text, _TEXT_REQUEST_PATTERNS):
        warnings.append(TEXT_WARNING)
    if _matches_any(text, _PRODUCT_CHANGE_PATTERNS):
        warnings.append(PRODUCT_WARNING)
    return warnings


# ── LLM ko di jane wali direction ─────────────────────────────────────────────

def _shorten(text: str, limit: int) -> str:
    """Lambi scraped description ka pehla hissa — lafz ke beech se nahi kaatta."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].strip() + "..."


def _direction_lines(form_data: dict) -> list[str]:
    """
    Form ke chune hue options -> LLM ke liye parhne qabil direction.

    Yahan LABEL ke saath wohi PROMPT FRAGMENT bhi jata hai jo build_video_prompt
    istemal karta. Wajah: fragment mein direction pehle se achhi English mein
    likhi hui hai, to LLM ko andaza nahi lagana parta ke "Bold & Dramatic" ka
    hamare yahan matlab kya hai — aur draft us prompt se mail khata hai jo form
    akela banata.
    """
    lines: list[str] = []
    for title, registry, key in (
        ("Look", AD_STYLES, form_data.get("ad_style")),
        ("Setting", SCENES, form_data.get("scene")),
        ("Mood", MOODS, form_data.get("mood")),
        ("Lighting", LIGHTING, form_data.get("lighting")),
        ("Camera", CAMERA_MOTIONS, form_data.get("camera_motion")),
        ("Pacing", PACING, form_data.get("pacing")),
    ):
        option = registry.get(key or "")
        if option:
            lines.append(f"- {title}: {option['label']} — {option['prompt']}")
    return lines


_RULES_BLOCK = """RULES — every prompt you write must obey all of them:
1. Describe ONLY the scene, background, surface, lighting, atmosphere and camera
   movement. The product is supplied as a real photograph and is animated as-is.
2. NEVER describe the product's own appearance — not its colour, shape, material,
   pattern, size or any logo or branding on it. Do not even name its colour.
3. NEVER ask for text of any kind in the frame: no words, letters, numbers,
   captions, subtitles, signage, price tags, watermarks or logo overlays.
4. It is ONE single continuous shot. No cuts, no scene changes, no "then", no
   second location, no shot list.
5. No people speaking, no story, no unrelated subject matter. This is a product
   commercial.
6. Write in plain cinematic English even if the user's idea is written in Urdu,
   Roman Urdu or any other language.
7. Each prompt is 2-3 sentences and under 400 characters.

Return ONLY valid JSON, no markdown fences and no explanation:
{"prompts": ["first prompt", "second prompt", "third prompt"]}"""


def _build_messages(form_data: dict, idea: str, product: dict | None,
                    brand, count: int) -> list[dict]:
    parts: list[str] = [
        "You write prompts for an image-to-video AI model that animates a real "
        "product photograph into a short commercial. Write "
        f"{count} DIFFERENT prompt options for the same brief.",
        "",
    ]

    # ── Product ka context ────────────────────────────────────────────────
    #
    # Sirf naam kaafi nahi tha: "Ceramic Mug" aur "Silk Scarf" dono ko drafter
    # ek jaisa "polished marble tabletop" de deta tha. Category aur description
    # milne se setting product ke mutabiq banti hai — scarf ke liye kapre wali
    # jagah, mug ke liye cafe/kitchen.
    #
    # Rule 2 phir bhi poori tarah lagti hai: ye maloomat SETTING chunne ke liye
    # hain, product ka hulia likhne ke liye NAHI (wo input photo se aata hai).
    name = ((product or {}).get("name") or "").strip()
    category = ((product or {}).get("category") or "").strip()
    description = ((product or {}).get("description") or "").strip()

    if name:
        parts.append(f"The product in the photo is: {name}")
    if category:
        parts.append(f"Its category is: {category}")
    if description:
        # Scraped descriptions bohat lambi ho sakti hain (kai sau lafz). Poori
        # bhejna prompt ko phula deta hai aur model ka dhyan scene se hata kar
        # marketing copy par le jata hai — pehla hissa hi kaafi hai.
        parts.append(f"Store description (for context only): {_shorten(description, 400)}")
    if name or category or description:
        # Setting ka faisla form karta hai, product nahi — is liye "achhi jagah
        # chuno" kehna bekaar tha: form pehle hi jagah bata chuka hota hai aur
        # model har product ko wahi ek jaisa "marble + floor-to-ceiling window"
        # de deta tha (scarf, mug aur running shoe teenon ko).
        #
        # Product ka asal kaam us jagah ke ANDAR hai: kaunsi satah, kaunsa prop,
        # aur cheez rakhi kahan hai. Joota dalan ki bench par, mug kitchen
        # counter par — dono "lifestyle interior" hi hain.
        parts.append(
            "The Setting from the form decides WHERE the shot happens. Use these "
            "product details only to choose, WITHIN that setting, the surface, "
            "props and placement where this kind of product would genuinely be "
            "used or kept. Avoid generic luxury filler — marble slabs, "
            "floor-to-ceiling windows and pedestals — unless they truly suit this "
            "product. Do NOT restate these details or describe how the product looks."
        )

    country = store_country(brand)
    if country:
        parts.append(
            f"The store sells in {country}, so the setting and any people shown "
            f"should suit shoppers there."
        )

    direction = _direction_lines(form_data)
    if direction:
        parts.append("")
        parts.append("The user picked this direction in the form:")
        parts.extend(direction)

    if idea:
        parts.append("")
        parts.append(
            "The user also described the scene they have in mind, in their own "
            f'words (it may be Urdu or Roman Urdu):\n"{idea}"'
        )
        parts.append(
            "This idea is the MOST important input. Build every option around it "
            "and use the form direction above only for the look, mood, lighting "
            "and camera. If the idea asks for something the rules forbid, simply "
            "leave that part out — do not mention that you left it out."
        )
    else:
        parts.append("")
        parts.append(
            "The user did not describe a scene, so invent three distinctly "
            "different settings that fit the direction above."
        )

    parts.append("")
    parts.append(_RULES_BLOCK)

    return [{"role": "user", "content": "\n".join(parts)}]


# ── Jawab ki safai ────────────────────────────────────────────────────────────

# Model aksar "typographic" unicode nikalta hai — non-breaking hyphen
# ("rain‑spattered"), curly quotes, ellipsis. Textarea mein ye ajeeb lagta hai
# aur user jab us par edit karta hai to aadhe hyphen normal aur aadhe nahi hote.
# Maani kuch nahi badalta, is liye seedha ASCII par le aate hain.
_PUNCT_FIXES = {
    "‑": "-", "‐": "-", "‒": "-", "–": "-", "—": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", " ": " ",
}


def _normalise_punctuation(text: str) -> str:
    for bad, good in _PUNCT_FIXES.items():
        text = text.replace(bad, good)
    return text


def _trim(text: str) -> str:
    """
    Ek line banao aur hadd ke andar lao — aakhri POORE jumle par kaat kar.

    Aadha jumla ("...camera slowly pushes in towards the") prompt ko ajeeb
    banata hai aur model us adhoori baat ko poora karne ki koshish karta hai.
    """
    text = " ".join(_normalise_punctuation(text or "").split())
    if len(text) <= MAX_DRAFT_CHARS:
        return text

    cut = text[:MAX_DRAFT_CHARS]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > MAX_DRAFT_CHARS * 0.5:
            return cut[: idx + 1].strip()
    return cut.rsplit(" ", 1)[0].strip()


def _extract_prompts(raw_text: str) -> list[str]:
    """
    Model ka jawab -> prompts ki list.

    Do shaklein qubool hain: {"prompts": [...]} aur seedhi [...]. Kuch models
    JSON ke gird fence laga dete hain, wo pehle utar diya jata hai (wahi safai
    jo ads_generation/groq_service.py karti hai).
    """
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Kabhi kabhi JSON se pehle ya baad mein ek line likh deta hai — pehle
        # '{' se aakhri '}' tak ka tukra nikal kar dobara koshish.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])

    if isinstance(data, dict):
        items = data.get("prompts") or data.get("options") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    return [x for x in items if isinstance(x, str)]


def _usable_drafts(items: list[str]) -> list[str]:
    """
    Sirf woh drafts jo waqai bheje ja sakte hain.

    `looks_usable` DOBARA yahan chalti hai — wahi darbaan jo generate par
    lagta hai. Draft us se guzar na sake to usay dikhana bemani hai: user
    Generate dabata aur backend chup-chaap form par wapas chala jata.
    """
    out: list[str] = []
    seen: set[str] = set()

    for item in items:
        text = _trim(item)
        if len(text) < 40:          # ek jumla bhi nahi — kaam ka nahi
            continue
        if not looks_usable(text):
            logger.warning("[video] draft prompt guard se nahi guzra: %r", text[:80])
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)

    return out


# ── Public ────────────────────────────────────────────────────────────────────

def draft_prompts(form_data: dict, idea: str | None, product: dict | None = None,
                  brand=None, count: int = DRAFT_COUNT) -> dict:
    """
    Form + user ki line -> {"prompts": [...], "warnings": [...]}

    `warnings` un farmaishon ke baare mein hain jo fixed rules rok dengi (text
    ya product ki tabdeeli) — prompts phir bhi bante hain.
    """
    idea = " ".join((idea or "").split())
    warnings = idea_warnings(idea)

    payload = {
        "messages": _build_messages(form_data, idea, product, brand, count),
        # 0.9 JAAN BOOJH KAR: teen options ka faida hi tab hai jab wo waqai ek
        # doosre se alag hon. Rules prompt mein hain, temperature un ko nahi
        # torta — sirf scene ke alfaz badalta hai.
        "temperature": 0.9,
        "max_tokens": DRAFT_MAX_TOKENS,
        # Lane ke model ke hisaab se adapt_payload ise rakhta ya hata deta hai.
        "reasoning_effort": "low",
    }

    try:
        result = chat_completion(
            "video_prompt", payload, what="Video prompt drafting", timeout=30
        )
        raw_text = check_raw_response(
            result, "Video prompt drafting", max_tokens=DRAFT_MAX_TOKENS
        )
    except Exception as e:  # noqa: BLE001 — har nakami user ke liye ek hi cheez hai
        logger.error("[video] prompt drafting nakaam: %s: %s", type(e).__name__, e)
        raise PromptDraftError(
            "Could not write a prompt just now. Please try again, or write your "
            "own in the box below.",
            detail=f"{type(e).__name__}: {e}",
        ) from e

    try:
        items = _extract_prompts(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("[video] prompt drafting ka jawab JSON nahi tha: %r", raw_text[:200])
        raise PromptDraftError(
            "Could not write a prompt just now. Please try again, or write your "
            "own in the box below.",
            detail=f"bad JSON: {e}",
        ) from e

    prompts = _usable_drafts(items)
    if not prompts:
        logger.error("[video] prompt drafting: koi draft qabil-e-istemal nahi: %r",
                     raw_text[:200])
        raise PromptDraftError(
            "Could not write a usable prompt this time. Please try again, or "
            "write your own in the box below.",
            detail="no usable drafts",
        )

    return {"prompts": prompts[:count], "warnings": warnings}


__all__ = [
    "DRAFT_COUNT", "MAX_IDEA_CHARS", "PromptDraftError",
    "draft_prompts", "idea_warnings",
]
