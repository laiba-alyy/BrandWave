"""
Video ad ke "Advanced prompt" box ka darbaan.

MASLA jo ye hal karta hai — code se tasdeeq shuda:

    build_video_prompt() mein custom prompt form ko REPLACE karta hai, jorta
    nahi. Yani jis lamhe user box mein kuch bhi likhta hai, us ke chune hue
    ad_style / scene / mood / lighting / camera_motion / pacing AUR brand ka
    mulk — saaton cheezein chup-chaap gir jati hain.

    Natija: "123456kjhgfd m123456jhgfwert" likhne par model ko poori creative
    direction ke tor par sirf yehi kachra jata hai. Form bhara hua hota hai
    magar us ka koi asar nahi hota, aur user ko pata bhi nahi chalta ke uska
    video kyun bekar bana.

HAL — teen darje, sab se narm se sab se sakht:

  1. NA-QABIL-E-ISTEMAL prompt (gibberish, keyboard mash, sirf adad):
     prompt ko CHHOR do aur form se video banao. Ye jaan boojh kar block NAHI
     karta — demo ke doran video ban jana chahiye, aur user ko response mein
     saaf bata diya jata hai ke uska prompt kyun istemal nahi hua.

  2. Gaali / abuse: 400. Ye image module ke input_guard se hi aata hai, taake
     dono jagah ek hi list aur ek hi message rahe.

  3. Bohat lamba: 400 apni hadd ke saath.

"Gibberish" ka faisla dictionary se nahi hota (wo ek poori dependency hai aur
Roman Urdu prompts ko ghalat block karti). Uske bajaye SHAKL dekhte hain: asli
alfaz mein vowels hote hain aur lagataar 4+ consonants nahi hote. Ye "neon
rainy Tokyo street" ko guzar deta hai aur "kjhgfd" ko rok deta hai, chahe wo
kisi bhi zaban ka ho.
"""
import logging
import re

from modules.ads_generation.input_guard import (
    InvalidAdInput,
    clean_ad_text,
)

logger = logging.getLogger(__name__)

MAX_VIDEO_PROMPT = 600

# Vowel mein 'y' shamil hai: "rhythm", "gym", "sky" warna gibberish gine jate.
_VOWELS = set("aeiouyàáâãäåèéêëìíîïòóôõöùúûüāēīōūअआइईउऊएओ")
_TOKEN_RE = re.compile(r"[^\s]+")
_ALPHA_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _has_long_repeat(letters: str, limit: int = 4) -> bool:
    """
    Ek hi harf `limit` ya us se zyada dafa lagataar: "aaaa", "hmmmm".

    Regex backreference ke bajaye saada loop - parhne mein saaf hai aur
    escaping ke masail se bhi mehfooz.
    """
    run = 1
    for prev, cur in zip(letters, letters[1:]):
        run = run + 1 if cur == prev else 1
        if run >= limit:
            return True
    return False


def _is_wordlike(token: str) -> bool:
    """
    Ek token asli lafz jaisa lagta hai ya nahi.

    Do shartein — dono asli alfaz mein taqreeban hamesha poori hoti hain:
      * kam az kam ek vowel
      * 4 ya us se zyada consonants lagataar NAHI ("kjhgfd", "qwrtp")
    """
    letters = "".join(_ALPHA_RE.findall(token)).lower()
    if len(letters) < 2:
        return False
    # Token jis mein adad zyada hon ("123456kjhgfd") — lafz nahi.
    if len(letters) < len(token) * 0.6:
        return False
    if not any(ch in _VOWELS for ch in letters):
        return False

    # "aaaaaaaa" / "hahahaha" jaisa mash: ek hi harf 4 dafa lagataar, ya poore
    # token mein sirf 1-2 alag harf. Ye vowel/consonant test se bach jate hain
    # kyunke technically in mein vowel maujood hota hai.
    if _has_long_repeat(letters):
        return False
    if len(letters) >= 5 and len(set(letters)) <= 2:
        return False

    run = 0
    for ch in letters:
        if ch in _VOWELS:
            run = 0
        else:
            run += 1
            if run >= 4:
                return False
    return True


def looks_usable(prompt: str) -> bool:
    """
    Kya is prompt ko creative direction ke tor par bhejna theek hai?

    Narmi jaan boojh kar: shak ka faida user ko jata hai. Sirf wahi prompt
    rad hota hai jo waqai kachra lagta ho.
    """
    tokens = _TOKEN_RE.findall(prompt or "")
    if not tokens:
        return False

    wordlike = [t for t in tokens if _is_wordlike(t)]

    # Ek hi lafz ka prompt ("cinematic") bilkul jaiz hai.
    if len(tokens) == 1:
        return bool(wordlike)

    # Warna: kam az kam do asli lafz, aur aadhe se zyada tokens lafz jaise.
    return len(wordlike) >= 2 and len(wordlike) / len(tokens) >= 0.5


class PromptDecision:
    """
    Prompt ka faisla — aur us ki wajah, taake UI user ko bata sake.

    `used` False ho to caller ko form ke fragments par wapas jana hai
    (build_video_prompt ko custom_prompt=None dena).
    """

    def __init__(self, text: str | None, used: bool, notice: str = ""):
        self.text = text
        self.used = used
        self.notice = notice

    def __repr__(self) -> str:
        return f"PromptDecision(used={self.used}, text={self.text!r})"


def review_prompt(raw: str | None) -> PromptDecision:
    """
    Advanced prompt ko parkho.

    Raises InvalidAdInput (-> 400) sirf gaali aur hadd se lambe prompt par.
    Gibberish par koi exception nahi — wo chup-chaap chhod diya jata hai aur
    `notice` mein wajah chali jati hai.
    """
    # Gaali aur length ki safai image module wali hi — ek hi list, ek hi
    # message, dono modules mein.
    text = clean_ad_text(raw, max_len=MAX_VIDEO_PROMPT, field="Prompt")

    if not text:
        return PromptDecision(None, used=False)

    if not looks_usable(text):
        logger.info("[video] prompt na-qabil-e-istemal, form par wapas: %r", text[:80])
        return PromptDecision(
            None,
            used=False,
            notice=(
                "We could not read your prompt as a description, so the video was "
                "built from your Style, Scene, Mood, Lighting, Camera and Pacing "
                "choices instead. Try something like "
                "\"golden hour rooftop, model walking towards camera\"."
            ),
        )

    return PromptDecision(text, used=True)


__all__ = ["InvalidAdInput", "MAX_VIDEO_PROMPT", "PromptDecision",
           "looks_usable", "review_prompt"]
