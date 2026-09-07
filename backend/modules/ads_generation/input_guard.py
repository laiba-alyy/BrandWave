"""
Ad generation ka input guard — user ka likha hua har lafz yahan se guzarta hai.

KYUN: is module mein user ka text DO jagah jata hai jahan wo nuqsan kar sakta
hai — (1) image prompt ban kar Bria/Claid ko, aur (2) Pillow se seedha
generated image PAR. Demo mein koi bhi shakhs box mein gaali, 50,000 harf, ya
control characters daal sakta hai. Un teenon soorton mein pehle kya hota tha:

  * bohat lamba prompt   -> provider 400/413 deta, ya request 200s tak latakti
  * gaali / abuse        -> seedha ad image par chhap jati
  * control chars / RTL  -> Pillow ka draw.text crash ya bigda hua layout
  * khali/spaces         -> khali headline, aur image par bas gradient

Ab har field yahan normalise hoti hai, hadd mein aati hai, aur na-munasib
hone par SAAF 400 milta hai (500 nahi) jise UI dikha sakta hai.

Ye filter jaan boojh kar saada hai: substring nahi, poore LAFZ match karta
hai. "Scunthorpe problem" asli hai — substring matching "classic" ko block kar
deti hai kyunke usmein "ass" hai, aur ek theek-thaak brand ka ad rok deti hai.
"""
import re
import unicodedata

# ── Hadood ────────────────────────────────────────────────────────────────
#
# Ye numbers marzi ke nahi hain:
#   custom_prompt  600 — Bria/Claid ka prompt field. Is se lamba prompt model
#                        ke apne guardrails ke saath muqabla karne lagta hai
#                        aur product ki shakl bigadne lagti hai.
#   ad_text        120 — image PAR chhapta hai. 1024px chaudi image par is se
#                        zyada teen line se aage nikal jata hai aur product
#                        dhak leta hai (dekho image_polish.wrap_to_width).
#   cta             28 — pill button ke andar ek line.
MAX_CUSTOM_PROMPT = 600
MAX_AD_TEXT = 120
MAX_CTA = 28
MAX_CHOICE = 60          # mood / occasion / platform / cta_goal jaise dropdowns


class InvalidAdInput(ValueError):
    """User ka input qabil-e-qubool nahi. Route ise 400 banata hai."""

    def __init__(self, message: str, *, field: str = ""):
        super().__init__(message)
        self.message = message
        self.field = field


# ── Profanity ─────────────────────────────────────────────────────────────
#
# English + Roman Urdu/Hindi gaaliyan. Ye list mukammal nahi ho sakti aur na
# hi hone ka daawa hai — maqsad ye hai ke demo mein koi saaf gaali ad image
# par na chhape. Jo cheez yahan se bach jaye wo bhi kam az kam length aur
# character limits se guzar chuki hoti hai.
#
# NOTE: sirf ad_text (jo image par chhapta hai) aur custom_prompt par lagti
# hai. Product ke naam par NAHI — wo catalogue se aate hain, user se nahi.
_PROFANITY = {
    # english
    "fuck", "fucking", "fucker", "shit", "bullshit", "bitch", "bastard",
    "asshole", "dick", "cock", "pussy", "cunt", "slut", "whore", "nigger",
    "nigga", "faggot", "retard", "rape", "rapist", "porn", "pornhub", "sex",
    "nude", "nudes", "xxx", "milf", "boobs", "penis", "vagina", "wtf", "stfu",
    # roman urdu / hindi
    "gandu", "gaand", "gand", "chutiya", "chutiye", "chut", "lund", "lauda",
    "loda", "madarchod", "madarchood", "behenchod", "bhenchod", "bhosdi",
    "bhosdike", "bhosda", "harami", "haramzada", "haramkhor", "kutta",
    "kutti", "kamina", "kamine", "randi", "rand", "tatti", "chodu", "chod",
    "jhaat", "jhat", "suar", "kanjar", "bhadwa", "dalla", "gashti",
}

# Lafz nikalne ke liye: harf/adad ke ilawa har cheez separator hai. Is se
# "f-u-c-k" aur "fuck!!!" dono ek hi lafz ban jate hain.
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Leetspeak: a$$ -> ass, sh1t -> shit. Sirf aam badle hue harf.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a"})


def _words(text: str) -> list[str]:
    # NFKC yahan bhi: contains_profanity() ko akela bhi call kiya ja sakta hai,
    # aur us soorat mein fullwidth "ｆｕｃｋ" bina normalise kiye bach jata.
    lowered = unicodedata.normalize("NFKC", text).lower().translate(_LEET)
    return _WORD_RE.findall(lowered)


def contains_profanity(text: str) -> bool:
    """Poore LAFZ par match — substring par nahi (dekho module docstring)."""
    if not text:
        return False
    words = _words(text)
    if any(w in _PROFANITY for w in words):
        return True
    # "f u c k" / "c.h.u.t" jaise spaced-out roop: sirf tab jodo jab lagataar
    # single-letter tokens hon, warna har acronym match karne lagega.
    singles = "".join(w for w in words if len(w) == 1)
    return len(singles) >= 4 and any(bad in singles for bad in _PROFANITY)


# ── Normalisation ─────────────────────────────────────────────────────────

# Control characters (\x00 tak), zero-width, aur bidi override — ye teenon
# Pillow ka layout torh sakte hain ya text ko ulta dikha sakte hain.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")
_WS_RE = re.compile(r"\s+")


def clean_text(value: str | None, *, max_len: int, field: str,
               collapse_ws: bool = True) -> str | None:
    """
    Ek user field ko mehfooz shakl mein laao.

    - Unicode NFKC (taake fullwidth/ligature trick se filter na bache)
    - control + zero-width + bidi characters nikaal do
    - whitespace ek space mein
    - hadd se lamba ho to SAAF error, chup-chaap kaat kar nahi

    Truncate jaan boojh kar nahi karte: agar user ne 5,000 harf likhe hain to
    usay batana chahiye ke sirf pehle 120 chhape, warna wo samjhega ke tool
    toot gaya.
    """
    if value is None:
        return None

    text = unicodedata.normalize("NFKC", str(value))
    text = _CONTROL_RE.sub("", text)
    if collapse_ws:
        text = _WS_RE.sub(" ", text)
    text = text.strip()

    if not text:
        return None

    if len(text) > max_len:
        raise InvalidAdInput(
            f"{field} is too long ({len(text)} characters). "
            f"Please keep it under {max_len}.",
            field=field,
        )
    return text


def clean_ad_text(value: str | None, *, max_len: int, field: str) -> str | None:
    """
    clean_text + profanity check.

    Sirf un fields par jo IMAGE par chhapti hain ya prompt mein jati hain.
    """
    text = clean_text(value, max_len=max_len, field=field)
    if text and contains_profanity(text):
        raise InvalidAdInput(
            "That text contains language we cannot put on a brand ad. "
            "Please rewrite it.",
            field=field,
        )
    return text


def clean_choice(value: str | None, allowed: tuple[str, ...] | None = None, *,
                 field: str = "option") -> str | None:
    """
    Dropdown values. Ye UI se aati hain, magar API seedha bhi call ho sakti
    hai — is liye yahan bhi hadd aur (jahan mumkin ho) allow-list.
    """
    text = clean_text(value, max_len=MAX_CHOICE, field=field)
    if text and allowed and text not in allowed:
        raise InvalidAdInput(
            f"Unknown {field} '{text}'. Choose one of: {', '.join(allowed)}.",
            field=field,
        )
    return text
