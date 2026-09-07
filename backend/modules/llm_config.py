"""
Text LLM routing — ek hi jagah. (Groq × 2 keys + OpenAI.)

Ab teen LANES hain, dekho PURPOSE_LANES:

    primary  GROQ_API_KEY    Groq    8,000 TPM per model
    alt      GROKAPIKEY2     Groq    8,000 TPM per model
    openai   OPENAI_API_KEY  OpenAI  ~200,000 TPM (tier 1)

SEO ke teeno step (keywords, content, blog) OpenAI lane par hain aur Groq
unke peeche fallback hai; baaqi sab Groq-first hain aur OpenAI unki teesri
lane hai. Kharcha `record_usage` ledger mein likha jata hai aur
OPENAI_SPEND_CAP_USD par OpenAI lane khud-ba-khud band ho jati hai.

Neeche wali kahani us waqt ki hai jab sirf Groq tha — aur ab bhi wahi sabaq
deti hai: model/provider ka faisla EK jagah rehna chahiye.

Groq text model — ek hi jagah.

Pehle `llama-3.3-70b-versatile` 7 alag files mein hardcoded tha. Groq ne wo
model retire kar diya, to har call 404 dene lagi:

    The model `llama-3.3-70b-versatile` does not exist or you do not have access

Jin call sites mein try/except fallback tha (seo_llm keywords, scraping cleaner)
wo CHUP-CHAAP degraded output dene lage — asli LLM ke bajaye hardcoded fallback.
Jin mein nahi tha (seo_blog) wo 500 karne lage.

Isliye model ab yahan se aata hai. Provider model retire kare to sirf ye file
(ya env var) badalni hai, 7 files dhoondni nahi.

Available models check karne ke liye:
    GET https://api.groq.com/openai/v1/models
"""
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import NamedTuple

# openai/gpt-oss-120b Groq par available hai aur chatbot RAG service pehle se
# isi ko successfully use kar rahi hai.
#
# NOTE: qwen/qwen3.6-27b bhi available hai lekin wo `<think>...` reasoning
# tokens emit karta hai, jo JSON/plain-text parsers ko torh deta hai — isliye
# use default mat banana.
# Model ek hi jagah se aata hai. GROQ_MODEL primary hai; GROQ_TEXT_MODEL
# purane naam ke liye compat mein rakha hai.
logger = logging.getLogger(__name__)

GROQ_TEXT_MODEL = os.getenv("GROQ_MODEL") or os.getenv("GROQ_TEXT_MODEL") or "openai/gpt-oss-120b"


# ── PURPOSE -> MODEL MAP ──────────────────────
#
# *** MODEL BADALNE KE LIYE SIRF YE DICT EDIT KARO. ***
#
# Groq ke rate limits PER-MODEL hain, per-account nahi. Ek hi account par alag
# models chala kar har model ka apna TPM budget milta hai — ye throughput
# barhane ka legitimate tareeqa hai (multiple accounts banana ToS ke khilaf hai).
#
# Measured limits (single key, on_demand tier):
#     openai/gpt-oss-120b     8,000 TPM   1000 RPM   ~2.7s / 150 words
#     openai/gpt-oss-20b      8,000 TPM   1000 RPM   ~2.1s / 150 words
#
# RETIRED by Groq (decommission 21 Sept 2026) — in par kuch mat rakhna:
#     groq/compound-mini     70,000 TPM  — deprecated
#     groq/compound          70,000 TPM  — deprecated
#
# 70,000 TPM wala rasta un ke saath hi khatam ho gaya. Ab har cheez 8,000 TPM
# ke buckets par hai, is liye purpose ko lane ke saath sochna PEHLE se zyada
# ahem hai: limits per-model hain, aur do keys (primary/alt) do alag budget
# dete hain — dekho PURPOSE_LANES.
#
# REJECTED after testing:
#     qwen/qwen3.6-27b   -> <think> blocks + markdown fences, ignores length limits
#     qwen/qwen3.8-27b   -> wahi family; bina test kiye JSON parsers par risk
#     allam-2-7b         -> 4,096 context, too small for our prompts
#
# Har entry env var se override ho sakti hai, code chhue baghair.
DEFAULT_MODEL = "openai/gpt-oss-120b"

PURPOSE_MODELS: dict[str, str] = {
    # quality-critical — validated model par rakhe gaye hain
    "chatbot":      os.getenv("GROQ_MODEL_CHATBOT",      "openai/gpt-oss-120b"),
    "seo_blog":     os.getenv("GROQ_MODEL_SEO_BLOG",     "openai/gpt-oss-120b"),
    "seo_content":  os.getenv("GROQ_MODEL_SEO_CONTENT",  "openai/gpt-oss-120b"),
    # ── compound family se hijrat (Sept 2026) ─────────────────────────
    #
    # Ye teenon pehle groq/compound-mini par thay — us ke 70,000 TPM bucket ke
    # liye. Groq ne compound-mini AUR compound dono retire kar diye
    # (decommission: 21 Sept 2026), is liye wo rasta khatam ho gaya.
    #
    # Ye koi narm degradation nahi hota: retired model 404 deta hai, aur
    # call_with_failover SIRF rate-limit (429/413) par agli lane par jata hai —
    # 404 seedha user tak pahunchta. Bilkul wahi kahani jo is file ke shuru
    # wale docstring mein likhi hai (llama-3.3-70b ke waqt).
    #
    # Account par ab sirf do chat models qabil-e-istemal hain: gpt-oss-120b aur
    # gpt-oss-20b. (qwen3.6/3.8 JAAN BOOJH KAR nahi — wo `<think>` tokens
    # deta hai jo hamare JSON parsers torh deta; safeguard-20b moderation ka
    # model hai, general chat ka nahi.)
    #
    # Teenon kaam user ko SEEDHA nazar aate hain (ad ki headline, video ka
    # prompt, SEO keywords), is liye 20b ke bajaye 120b — quality pehle.
    "seo_keywords": os.getenv("GROQ_MODEL_SEO_KEYWORDS", "openai/gpt-oss-120b"),
    "ad_copy":      os.getenv("GROQ_MODEL_AD_COPY",      "openai/gpt-oss-120b"),
    "video_prompt": os.getenv("GROQ_MODEL_VIDEO_PROMPT", "openai/gpt-oss-120b"),
    # background extraction — user ko direct nazar nahi aata
    "scraping":     os.getenv("GROQ_MODEL_SCRAPING",     "openai/gpt-oss-20b"),
    # in-app assistant — user ki list mein nahi tha, safe default
    "assistant":    os.getenv("GROQ_MODEL_ASSISTANT",    "openai/gpt-oss-120b"),
    # sentiment insights + brand improvement pehle apna key/model khud utha
    # rahe the aur "unknown purpose" warning generate karte the. Ab dono
    # yahan registered hain, to key pool aur failover unko bhi milte hain.
    "sentiment":    os.getenv("GROQ_MODEL_SENTIMENT",    "openai/gpt-oss-120b"),
    "improvement":  os.getenv("GROQ_MODEL_IMPROVEMENT",  "openai/gpt-oss-120b"),
}


# ── Providers / lanes ─────────────────────────
#
# Ab teen LANES hain, do nahi:
#
#     primary  GROQ_API_KEY    Groq   (gpt-oss-120b par 8,000 TPM)
#     alt      GROKAPIKEY2     Groq   (wahi 8,000 TPM, alag key)
#     openai   OPENAI_API_KEY  OpenAI (tier-1 par ~200,000 TPM)
#
# Dono provider AIK HI wire format bolte hain (OpenAI chat-completions), is
# liye lane badalne par sirf base URL, key aur model ka naam badalta hai —
# payload ki shape wahi rehti hai. Isi wajah se ye poora switch call sites
# chhue baghair ho jata hai.
#
# LANE kyun chahiye tha: SEO ke teen step (keywords -> content -> blog) ek hi
# 8,000 TPM ceiling par baithe the. Akela blog hi prompt + 6,000 max_tokens
# reserve kar leta hai, to doosra step bheje jane se PEHLE hi 429 tha. Do Groq
# keys is ko halka karti hain, khatam nahi — 8,000 dono taraf 8,000 hi hai.
# OpenAI lane par wo queue mojood hi nahi.
SLOT_PRIMARY = "primary"
SLOT_ALT = "alt"
SLOT_OPENAI = "openai"

GROQ_SLOTS = (SLOT_PRIMARY, SLOT_ALT)

KEY_ENV_CANDIDATES: dict[str, tuple[str, ...]] = {
    SLOT_PRIMARY: ("GROQ_API_KEY",),
    SLOT_ALT:     ("GROKAPIKEY2", "GROKAPIKEYSentiment", "GROQ_API_KEY_2"),
    SLOT_OPENAI:  ("OPENAI_API_KEY",),
}

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

LANE_BASE_URL: dict[str, str] = {
    SLOT_PRIMARY: GROQ_BASE_URL,
    SLOT_ALT:     GROQ_BASE_URL,
    SLOT_OPENAI:  OPENAI_BASE_URL,
}


def is_openai_lane(slot: str) -> bool:
    return slot == SLOT_OPENAI


# ── OpenAI lane ke models ─────────────────────
#
# gpt-4o-mini JAAN BOOJH KAR chuna gaya hai, gpt-5-mini nahi:
#   * gpt-4o-mini `max_tokens` aur koi bhi `temperature` qubool karta hai —
#     yani हमारे mojooda payloads bilkul waise ke waise chalte hain.
#   * gpt-5-mini `max_completion_tokens` maangta hai aur sirf temperature=1
#     leta hai — us par har SEO call site todni parti.
#
# Cost (approx): $0.15 / 1M input, $0.60 / 1M output. Poori SEO run
# (keywords + content + blog) ~$0.003 — yani $5 mein ~1,600 runs.
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

OPENAI_PURPOSE_MODELS: dict[str, str] = {
    "seo_keywords": os.getenv("OPENAI_MODEL_SEO_KEYWORDS", OPENAI_DEFAULT_MODEL),
    "seo_content":  os.getenv("OPENAI_MODEL_SEO_CONTENT",  OPENAI_DEFAULT_MODEL),
    "seo_blog":     os.getenv("OPENAI_MODEL_SEO_BLOG",     OPENAI_DEFAULT_MODEL),
    "improvement":  os.getenv("OPENAI_MODEL_IMPROVEMENT",  OPENAI_DEFAULT_MODEL),
    "sentiment":    os.getenv("OPENAI_MODEL_SENTIMENT",    OPENAI_DEFAULT_MODEL),
    "video_prompt": os.getenv("OPENAI_MODEL_VIDEO_PROMPT", OPENAI_DEFAULT_MODEL),
}


def model_for(purpose: str, slot: str) -> str:
    """Is purpose ka model, LANE ke hisaab se."""
    if is_openai_lane(slot):
        return OPENAI_PURPOSE_MODELS.get(purpose) or OPENAI_DEFAULT_MODEL
    return PURPOSE_MODELS.get(purpose) or DEFAULT_MODEL


# ── Purpose -> lane chain ─────────────────────
#
# Har purpose ek TARTEEB deta hai, ek slot nahi. Pehli lane jo cooling na ho
# wo chalti hai; 429 par agli, bina rukay.
#
# SEO ke teeno step OpenAI par pehle jate hain — yehi wo module hai jiski
# sub-pages/sub-features ek hi minute mein kai bari calls bhejti hain, aur
# Groq ka 8,000 TPM wahin toot-ta tha. Groq unke peeche fallback hai, to
# OpenAI credit khatam ho jaye ya key ghalat ho to feature band nahi hota.
#
# Baaqi sab Groq-first hi hain (Groq output ZYADA TEZ deta hai, aur muft bhi
# hai); OpenAI un ke liye teesri lane hai — sirf tab chalti hai jab DONO Groq
# keys thak chuki hon. Us soorat mein user ko 25s ka wait aur 429 banner
# milta tha; ab ~2s mein jawab.
PURPOSE_LANES: dict[str, tuple[str, ...]] = {
    # ── OpenAI lane: bari, batch-type generation ──────────────────────
    # Ye wo char hain jo ek click par kai hazaar output tokens maangte hain
    # aur Groq ke 8,000 TPM par queue ban jate the.
    "seo_keywords": (SLOT_OPENAI, SLOT_ALT, SLOT_PRIMARY),
    "seo_content":  (SLOT_OPENAI, SLOT_PRIMARY, SLOT_ALT),
    "seo_blog":     (SLOT_OPENAI, SLOT_PRIMARY, SLOT_ALT),
    # brand insights: DO calls per run (suggestions + growth), ab parallel.
    # Groq par ye do calls 1,500 tokens each reserve karti thin aur TPM pacer
    # unhein serialize kar deta tha — isi liye page itna slow tha.
    "improvement":  (SLOT_OPENAI, SLOT_PRIMARY, SLOT_ALT),

    # ── sentiment: ab OpenAI lane par ─────────────────────────────────
    # Pehle ye Groq-first tha, is soch ke saath ke "apni key = koi TPM
    # sharing nahi". Wo us waqt durust tha jab sentiment ko ~20 reviews
    # milti thin (2 API calls).
    #
    # Third-party YouTube review videos ka source aane ke baad Gymshark par
    # 785 comments aane lage — yani 66 calls. Groq ke gpt-oss-120b par 8,000
    # TPM hai, to wo 16 minute ka intezaar ban gaya aur 429 ka toofan.
    # OpenAI lane par ~200,000 TPM hai (25 guna), is liye poora dataset ek
    # hi minute mein nikal jata hai.
    #
    # Groq ab bhi peeche fallback hai — OpenAI spend cap lag jaye ya key na
    # ho to analysis phir bhi chalti hai, bas dheere.
    "sentiment":    (SLOT_OPENAI, SLOT_PRIMARY, SLOT_ALT),
    # ── ad_copy + video_prompt: PRIMARY key par ───────────────────────
    #
    # Dono ab openai/gpt-oss-120b par hain (compound-mini retire ho gaya), yani
    # dono EK hi 8,000 TPM bucket mein — magar PRIMARY key ke bucket mein.
    # Chatbot aur assistant usi model par hain lekin ALT key par, is liye un se
    # takrao nahi hota: limits per-model PER-KEY hain, aur yehi wajah hai ke
    # in do purposes ko alt lane par nahi rakha gaya.
    #
    # Aapas mein bhi masla nahi: ye do ALAG pages hain (image ad vs video ad),
    # dono ki calls chhoti hain (~1,200 max_tokens), aur ek waqt mein aam tor
    # par ek hi chalta hai.
    #
    # Pehle ye dono compound-mini ke 70,000 TPM bucket par thay. Wo bucket ab
    # mojood nahi — is liye 429 ka imkaan pehle se zyada hai, aur failover
    # chain (alt -> openai) yahan ab pehle se ZYADA ahem hai, sirf ek safety
    # net nahi.
    "ad_copy":      (SLOT_PRIMARY, SLOT_ALT, SLOT_OPENAI),
    "video_prompt": (SLOT_PRIMARY, SLOT_ALT, SLOT_OPENAI),

    # ── GROKAPIKEY2 (alt): chatbot + scraping ─────────────────────────
    # Chatbot ka jawab CHHOTA hona chahiye (600 max_tokens) aur foran aana
    # chahiye — Groq isi kaam mein sab se tez hai, is liye ye jaan boojh kar
    # OpenAI par nahi bheja gaya.
    "chatbot":      (SLOT_ALT, SLOT_PRIMARY, SLOT_OPENAI),
    # scraping alt par hai magar chatbot se takrata nahi: ye gpt-oss-20b par
    # hai, chatbot gpt-oss-120b par — phir wahi per-model bucket wali baat.
    "scraping":     (SLOT_ALT, SLOT_PRIMARY, SLOT_OPENAI),
    # assistant bhi 120b par hai, yani chatbot ke SAATH wala bucket. Dono
    # interactive hain lekin dono chhote (600 + 1,200 tokens) — 8,000 ke
    # andar aaram se, aur ek waqt mein aam tor par ek hi chal raha hota hai.
    "assistant":    (SLOT_ALT, SLOT_PRIMARY, SLOT_OPENAI),
}

# Purana naam — kuch jagah abhi bhi "is purpose ki key" poochha jata hai.
PURPOSE_KEYS: dict[str, str] = {
    purpose: chain[0] for purpose, chain in PURPOSE_LANES.items()
}

GROQ_KEY_ENV = "GROQ_API_KEY"          # legacy naam, purane callers ke liye


def slot_env(slot: str) -> str | None:
    """Is slot ka pehla env naam jis mein waqai key set hai."""
    for name in KEY_ENV_CANDIDATES.get(slot, ()):
        if (os.getenv(name) or "").strip():
            return name
    return None


def env_slot(env: str) -> str:
    """Ulta mapping: env naam se lane. Na mile to primary."""
    for slot, names in KEY_ENV_CANDIDATES.items():
        if env in names:
            return slot
    return SLOT_PRIMARY


def configured_key_envs() -> list[str]:
    """
    GROQ env naam jin mein key set hai — primary pehle, phir alt.

    JAAN BOOJH KAR sirf Groq. brand_improvement ka _TokenPacer aur uska
    raw-POST loop is list par ghoomta hai aur URL khud Groq ka hardcode karta
    hai — yahan OPENAI_API_KEY shamil kar dena us key ko Groq par bhejta.
    Lanes chahiyen to configured_lanes() use karo.
    """
    envs: list[str] = []
    for slot in GROQ_SLOTS:
        name = slot_env(slot)
        if name and name not in envs:
            envs.append(name)
    return envs


def configured_lanes() -> list[str]:
    """Har wo lane jiski key set hai — primary, alt, openai ki tarteeb mein."""
    return [s for s in (SLOT_PRIMARY, SLOT_ALT, SLOT_OPENAI) if slot_env(s)]


# ── OpenAI spend ledger ───────────────────────
#
# Credit PREPAID hai ($5) aur khatam hone par har OpenAI call 429/insufficient
# _quota deti hai. Us se pehle khud ruk jana behtar hai: cap tak pahunchte hi
# OpenAI lane chain se gir jati hai aur sab kuch wapas Groq par chala jata hai
# — feature band nahi hota, sirf purana behaviour wapas aa jata hai.
#
# Billing ANDAZA nahi hai: OpenAI har response mein `usage` bhejta hai, wahi
# se actual prompt/completion tokens le kar likha jata hai.
#
# Ledger ek chhoti JSON file hai. DB table overkill tha — ye state kisi user
# se bandhi hui nahi hai aur restart ke aar-paar bas ek number chahiye.
_SPEND_FILE = Path(os.getenv("OPENAI_SPEND_FILE", "")) if os.getenv("OPENAI_SPEND_FILE")     else Path(__file__).resolve().parent.parent / ".llm_spend.json"

# $5 kharide the; 0.50 ka cushion chhora hai taake aakhri call bhi poori ho
# aur account kabhi hard-fail na kare.
OPENAI_SPEND_CAP_USD = float(os.getenv("OPENAI_SPEND_CAP_USD", "4.50"))

# USD per 1M tokens — (input, output).
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":  (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4o":       (2.50, 10.00),
}
# Model list mein na ho to sab se mehngi maloom qeemat lagao — under-bill kar
# ke cap se guzar jane se behtar hai over-bill kar ke jaldi ruk jana.
_FALLBACK_PRICE = (2.50, 10.00)

# Groq ke model ids. Ye muft hain, in par koi cost record nahi hota.
# Namespaced ("openai/gpt-oss-120b", "groq/compound-mini") aur purane
# non-namespaced ("llama-3.3-70b-versatile", "allam-2-7b") dono.
_GROQ_MODEL_PREFIXES = (
    "openai/", "groq/", "meta-llama/", "qwen/", "moonshotai/", "deepseek",
    "llama", "mixtral", "gemma", "allam", "whisper",
)


def _price_for(model: str) -> tuple[float, float] | None:
    """
    (input, output) per 1M tokens — ya None agar model muft (Groq) hai.

    Lookup PREFIX se hai, exact naam se nahi. OpenAI response mein hamesha
    DATED snapshot aata hai ("gpt-4o-mini-2024-07-18"), alias nahi — exact
    match par har call $0 bill hoti thi aur spend cap kabhi lagta hi nahi.
    Sab se LAMBA prefix jeetta hai, warna "gpt-4o-mini-..." ghalati se
    "gpt-4o" ke mehnge rate par bill hota.
    """
    name = model.strip().lower()
    if any(name.startswith(p) for p in _GROQ_MODEL_PREFIXES):
        return None
    match = max(
        (p for p in _PRICES if name.startswith(p)), key=len, default=None
    )
    if match:
        return _PRICES[match]
    # Anjaan model jo Groq ka bhi nahi — ehtiyatan mehngi qeemat par bill.
    _warn_once(f"[openai] unknown model {model!r} — billing at fallback price")
    return _FALLBACK_PRICE

_spend_lock = threading.Lock()
_spend_usd: float | None = None      # None = abhi file se parha nahi


def _load_spend() -> float:
    global _spend_usd
    if _spend_usd is None:
        try:
            _spend_usd = float(json.loads(_SPEND_FILE.read_text())["usd"])
        except Exception:
            _spend_usd = 0.0
    return _spend_usd


def openai_spend_usd() -> float:
    """Ab tak ka OpenAI kharcha (USD)."""
    with _spend_lock:
        return round(_load_spend(), 6)


def openai_budget_ok() -> bool:
    """Kya OpenAI lane abhi bhi cap ke andar hai?"""
    with _spend_lock:
        if _load_spend() < OPENAI_SPEND_CAP_USD:
            return True
    _warn_once(
        f"[openai] spend cap ${OPENAI_SPEND_CAP_USD:.2f} reached — OpenAI lane "
        f"band. Sab purposes wapas Groq par. Cap barhane ke liye "
        f"OPENAI_SPEND_CAP_USD set karo."
    )
    return False


def record_usage(model: str | None, usage: dict | None) -> None:
    global _spend_usd
    """
    Ek OpenAI response ka kharcha ledger mein jorho.

    Groq models yahan se chup-chaap guzar jate hain — wo _PRICES mein nahi
    hain aur muft hain, to unka koi cost record nahi hota.
    """
    if not model or not usage:
        return
    name = str(model).strip()
    price = _price_for(name)
    if price is None:
        return                      # Groq model — muft, bill nahi
    in_rate, out_rate = price
    cost = (
        (usage.get("prompt_tokens") or 0) * in_rate
        + (usage.get("completion_tokens") or 0) * out_rate
    ) / 1_000_000.0
    if cost <= 0:
        return

    with _spend_lock:
        total = _load_spend() + cost
        _spend_usd = total
        try:
            _SPEND_FILE.write_text(json.dumps({"usd": round(total, 6)}))
        except Exception as exc:               # disk read-only, etc.
            logger.debug("[openai] spend ledger likha nahi ja saka: %s", exc)

    logger.info(
        "[openai] %s: $%.5f (total $%.4f / $%.2f cap)",
        name, cost, total, OPENAI_SPEND_CAP_USD,
    )


def _usage_from(obj) -> dict | None:
    """SDK object ya raw dict — dono se usage nikalo."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get("usage")
    usage = getattr(obj, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
    }


def _model_of(obj) -> str | None:
    if isinstance(obj, dict):
        return obj.get("model")
    return getattr(obj, "model", None)


_warned: set[str] = set()


def _warn_once(message: str) -> None:
    """Ek hi warning baar baar log na ho, lekin CHUP bhi na rahe."""
    if message not in _warned:
        _warned.add(message)
        logger.warning(message)


class _KeyPool:
    """
    Kaunsi key abhi use karni hai — cooldown ke saath.

    Groq 429 dete waqt batata hai ke kitni der baad dobara koshish karo. Pehle
    hum wo poora waqt SO jate the (`time.sleep`). Ab wo key COOLING mark ho
    jati hai aur agli request foran doosri key par chali jati hai — 3-45s ka
    wait 0s ho jata hai, aur do keys ka TPM budget alag alag milta hai.

    Cooldown sirf ek hint hai, guarantee nahi: waqt guzarne par key khud-ba-khud
    dobara available ho jati hai, koi background cleanup nahi chahiye.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cooling: dict[str, float] = {}   # env name -> monotonic deadline

    def available(self, env: str) -> bool:
        with self._lock:
            return time.monotonic() >= self._cooling.get(env, 0.0)

    def mark_cooling(self, env: str, seconds: float | None) -> None:
        """429 ke baad is key ko thori der ke liye side kar do."""
        if not env:
            return
        # Wait hint na mile (413 waghera) to bhi chhota sa cooldown lagao —
        # warna agli request usi thaki hui key par wapas chali jayegi.
        wait = seconds if seconds is not None else _DEFAULT_COOLDOWN_SECONDS
        wait = min(wait, _MAX_COOLDOWN_SECONDS)
        with self._lock:
            self._cooling[env] = max(
                self._cooling.get(env, 0.0), time.monotonic() + wait
            )
        logger.info("[groq] key %s cooling for %.1fs", env, wait)

    def configured(self) -> list[str]:
        """Wo GROQ envs jin mein waqai koi key set hai — primary pehle."""
        return configured_key_envs()

    def lane_chain(self, purpose: str) -> list[str]:
        """
        Is purpose ki lanes, TARTEEB se — sirf wo jo configured bhi hain.

        OpenAI lane spend cap se aage nikal jaye to chain se apne aap gir
        jati hai; baaqi lanes waise hi chalti rehti hain.
        """
        chain = PURPOSE_LANES.get(purpose) or (SLOT_PRIMARY, SLOT_ALT, SLOT_OPENAI)
        out = []
        for slot in chain:
            if not slot_env(slot):
                continue
            if is_openai_lane(slot) and not openai_budget_ok():
                continue
            out.append(slot)
        return out

    def pick_lane(self, purpose: str) -> str | None:
        """
        Chain ki pehli lane jo COOLING na ho.

        Sab cooling hon to pehli hi wapas — call_with_failover phir purana
        wait-and-retry wala raasta le lega.
        """
        chain = self.lane_chain(purpose)
        if not chain:
            # Har lane cap/config se bahar — Groq par hi girne do taake asli
            # error caller tak jaye, chup-chaap None nahi.
            return SLOT_PRIMARY if slot_env(SLOT_PRIMARY) else None

        for slot in chain:
            env = slot_env(slot)
            if env and self.available(env):
                if slot != chain[0]:
                    logger.info(
                        "[llm] %s: %s cooling — %s lane par shift", purpose, chain[0], slot
                    )
                return slot
        return chain[0]

    def next_lane(self, purpose: str, used: list[str]) -> str | None:
        """Chain mein agli lane jo abhi tak aazmai nahi gayi aur cooling bhi nahi."""
        for slot in self.lane_chain(purpose):
            if slot in used:
                continue
            env = slot_env(slot)
            if env and self.available(env):
                return slot
        return None

    def pick(self, purpose: str) -> str | None:
        """Purana API — is purpose ki GROQ key ka env naam."""
        configured = self.configured()
        if not configured:
            return None

        chain = [s for s in (PURPOSE_LANES.get(purpose) or ()) if s in GROQ_SLOTS]
        preferred = next((slot_env(s) for s in chain if slot_env(s)), None)
        if not preferred or preferred not in configured:
            preferred = configured[0]

        if self.available(preferred):
            return preferred
        for env in configured:
            if env != preferred and self.available(env):
                logger.info(
                    "[groq] %s: %s cooling — %s par shift", purpose, preferred, env
                )
                return env
        return preferred

    def other(self, env: str) -> str | None:
        """Failover ke liye doosri configured GROQ key (agar hai)."""
        for candidate in self.configured():
            if candidate != env:
                return candidate
        return None


# Wait hint na ho to itni der key ko side rakho.
_DEFAULT_COOLDOWN_SECONDS = 20.0
# Kitna bhi bara hint aaye, key ko is se zyada der band nahi karte — warna ek
# bara 429 poori demo ke liye key gum kar deta hai.
_MAX_COOLDOWN_SECONDS = 60.0

_key_pool = _KeyPool()


# ── Lane resolution ───────────────────────────
#
# `Lane` ek hi jagah par wo char cheezein rakhta hai jo provider ke sath
# badalti hain. Isi ki wajah se call sites ko nahi pata chalta ke request
# Groq par gayi ya OpenAI par.
class Lane(NamedTuple):
    slot: str          # "primary" | "alt" | "openai"
    key: str | None
    model: str
    env: str           # kis env var se key aayi (cooling/failover ke liye)
    base_url: str

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def is_openai(self) -> bool:
        return is_openai_lane(self.slot)


def lane_for(purpose: str, slot: str) -> Lane:
    """Ek maloom slot ko poori Lane mein badlo."""
    env = slot_env(slot) or KEY_ENV_CANDIDATES.get(slot, (GROQ_KEY_ENV,))[0]
    return Lane(
        slot=slot,
        key=(os.getenv(env) or "").strip() or None,
        model=model_for(purpose, slot),
        env=env,
        base_url=LANE_BASE_URL.get(slot, GROQ_BASE_URL),
    )


def resolve_lane(purpose: str, *, key_env: str | None = None) -> Lane:
    """
    Is purpose ki abhi wali lane — provider, key, model, URL sab ek sath.

    ``key_env`` do to lane pool bypass ho jati hai (purane callers ke liye jo
    apni key khud chunte the).

    Missing key par crash nahi karta: Lane.key None hota hai aur warning log
    hoti hai, taake misconfiguration nazar aaye.
    """
    if purpose not in PURPOSE_MODELS:
        _warn_once(
            f"[llm] unknown purpose {purpose!r} — using {DEFAULT_MODEL}. "
            f"Known: {sorted(PURPOSE_MODELS)}"
        )

    slot = env_slot(key_env) if key_env else (_key_pool.pick_lane(purpose) or SLOT_PRIMARY)
    lane = lane_for(purpose, slot)
    if key_env:
        lane = lane._replace(env=key_env, key=(os.getenv(key_env) or "").strip() or None)
    if not lane.key:
        _warn_once(
            f"[llm] {lane.env} is not set — '{purpose}' calls on the "
            f"{lane.slot} lane will fail."
        )
    return lane


def get_groq_key(purpose: str = "chatbot") -> str | None:
    """Sirf key. Naye code mein resolve_lane() use karo."""
    return get_groq_config(purpose)[0]


def get_groq_config(purpose: str, *, key_env: str | None = None) -> tuple[str | None, str]:
    """
    (api_key, model). Purana signature — naya code resolve_lane() use kare.

    NOTE: ye ab bhi LANE-AWARE hai. seo_llm jaisi call sites is se sirf
    `model` leti hain taake `reasoning_params(model)` sahi lag sake — agar ye
    hamesha Groq ka model deta, to OpenAI lane par jate hi payload mein
    `reasoning_effort` chala jata aur OpenAI 400 de deta.
    """
    lane = resolve_lane(purpose, key_env=key_env)
    return lane.key, lane.model


def resolve_groq(
    purpose: str, *, key_env: str | None = None
) -> tuple[str | None, str, str]:
    """
    (api_key, model, key_env) — SIRF Groq lanes.

    JAAN BOOJH KAR OpenAI lane yahan se nahi aati: iske do caller
    (sentiment/groq_insights aur assistant_service) khud raw POST karte hain
    aur URL mein api.groq.com hardcode hai. Unhein OpenAI key de dena request
    ko ghalat host par bhej deta.

    Naye code ke liye resolve_lane() hai, jo provider bhi batati hai.
    """
    model = PURPOSE_MODELS.get(purpose) or DEFAULT_MODEL
    env = key_env or _key_pool.pick(purpose) or GROQ_KEY_ENV
    key = (os.getenv(env) or "").strip()
    if not key:
        _warn_once(
            f"[groq] {env} is not set — Groq calls for '{purpose}' will fail."
        )
        return None, model, env
    return key, model, env


_clients: dict[tuple[str, str], object] = {}


def groq_client(purpose: str, *, key_env: str | None = None):
    """
    Cached chat client + is purpose ka model.
    Return: (client, model)

    NOTE: har call par lane dobara resolve hoti hai — module import ke waqt EK
    dafa nahi. Ye zaroori hai, warna cooling/failover ka koi asar na hota.
    """
    client, model, _env = groq_client_ex(purpose, key_env=key_env)
    return client, model


def groq_client_ex(purpose: str, *, key_env: str | None = None):
    """groq_client() + istemal hui key ka env naam (failover ke liye)."""
    lane = resolve_lane(purpose, key_env=key_env)
    return client_for(lane), lane.model, lane.env


def client_for(lane: Lane):
    """
    Lane ka SDK client (cached).

    Dono provider ke liye AIK hi class — `openai.OpenAI` — bas base_url alag.
    groq SDK ki jagah ye is liye hai ke `client.chat.completions.create(...)`
    dono par bilkul aik jaisa hai, to call sites ko lane badalne ka pata hi
    nahi chalta. (groq package abhi bhi installed hai, sirf ab zaroori nahi.)
    """
    from openai import OpenAI

    cache_key = (lane.key or "", lane.base_url)
    if cache_key not in _clients:
        _clients[cache_key] = OpenAI(api_key=lane.key, base_url=lane.base_url)
    return _clients[cache_key]


def adapt_payload(payload: dict, lane: Lane) -> dict:
    """
    Payload ko LANE ke hisaab se theek karo.

    Ye ek asli bug ki jagah hai: call site model PEHLE resolve karti hai aur
    `**reasoning_params(model)` payload mein bake kar deti hai. Failover ke
    baad model badal jata hai, magar wo param payload mein baitha reh jata
    hai — Groq ka `reasoning_effort` OpenAI par seedha 400 hai. Is liye har
    request bhejne se pehle model ke hisaab se params yahan chhante jate hain.
    """
    body = {**payload, "model": lane.model}
    if not supports_reasoning_effort(lane.model):
        body.pop("reasoning_effort", None)
    return body


# -- RATE LIMIT: EK RETRY ----------------------
#
# Groq ke limits PER-MODEL aur PER-MINUTE hain (gpt-oss-120b: 8,000 TPM).
# Normal use mein ye hit nahi hoti - poori SEO run + chatbot ~2 minute mein
# phailti hai, to token spend kai windows mein bat jata hai. Lekin demo ke doran
# koi cheez FORAN dobara generate karo to do bari requests ek hi window mein
# aa jati hain aur Groq mana kar deta hai:
#
#     429 rate_limit_exceeded   -> TPM/RPM window bhar gaya (wait se theek hota hai)
#     413 rate_limit_exceeded   -> AKELI request hi limit se bari hai
#
# Groq error body mein exact wait bata deta hai:
#     "Please try again in 3.735s"
#     "Please try again in 1m12.4s"
#
# Policy - jaan boojh kar simple rakhi hai:
#   * sirf EK retry (loop nahi)
#   * sirf tab jab Groq ka bataya wait RETRY_MAX_WAIT_SECONDS se kam ho
#   * MODEL FALLBACK NAHI. Kisi aise model par chup-chaap shift ho jana jiska
#     output validate nahi kiya, 30 second wait karne se ZYADA khatarnak hai -
#     yehi ghalti is file ke shuru wale docstring mein bhi likhi hai.
#
# 413 par wait hint aata hi nahi (request khud bari hai, window ka masla nahi),
# is liye wahan retry apne aap skip ho jati hai - parse_retry_after None deta hai.

# 45s se ghata kar 25s: ab pehla jawab failover hai (agli lane, 0s wait), aur
# yahan tak aane ka matlab hai HAR lane thak chuki hai. Us soorat mein user ko
# 45 second tak spinner dikhane se behtar hai ke saaf 429 aa jaye — frontend ka
# AiRetryBanner usay theek se handle karta hai.
RETRY_MAX_WAIT_SECONDS = 25.0

# Groq ka hint us lamhe ka hisaab hota hai; thora cushion na ho to retry kabhi
# kabhi 1-2 tokens ki wajah se dobara 429 kha jati hai.
_RETRY_BUFFER_SECONDS = 0.5

# Ye do string frontend ko jati hain - wording yahin se aati hai taake har page
# par alag alag na likhni pare.
RATE_LIMIT_MESSAGE = "Rate limit reached, please wait a minute"
RETRYING_MESSAGE = "AI service is busy, retrying..."


class RateLimitedError(Exception):
    """
    Groq rate limit - ya to wait bohat lamba tha, ya retry ke baad bhi nahi bana.

    Ye HTTPException NAHI hai: llm_config ko FastAPI se bandhna nahi tha. Routes
    ise 429 mein badalti hain, aur main.py mein ek global handler bhi laga hai
    un raston ke liye jahan route khud catch nahi karti.
    """

    def __init__(self, retry_after: float | None = None):
        super().__init__(RATE_LIMIT_MESSAGE)
        self.retry_after = retry_after
        self.message = RATE_LIMIT_MESSAGE


# "Please try again in 1m12.4s" / "Please try again in 3.735s"
_WAIT_HINT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def parse_retry_after(text: str) -> float | None:
    """Groq ke error text se wait (seconds) nikaalo. Hint na mile to None."""
    match = _WAIT_HINT_RE.search(text or "")
    if not match:
        return None
    minutes = float(match.group(1) or 0)
    seconds = float(match.group(2))
    return minutes * 60.0 + seconds


def _error_status(exc: Exception) -> int | None:
    """
    HTTP status - dono call patterns ke liye ek hi jagah.

    groq SDK  : APIStatusError.status_code
    requests  : HTTPError.response.status_code
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status


def _error_body(exc: Exception) -> str:
    """Error ka poora text - wait hint aur error code isi mein hote hain."""
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            text = response.text
            if text:
                return text
        except Exception:
            pass
    return str(exc)


def is_rate_limit_error(exc: Exception) -> bool:
    """
    429, ya 413 jo asal mein rate limit ho.

    Sada 413 (payload waqai bara hai) rate limit NAHI hai - us par wait karne ka
    koi faida nahi, is liye usay yahan se guzarne nahi dete.
    """
    status = _error_status(exc)
    if status == 429:
        return True
    if status == 413:
        return "rate_limit" in _error_body(exc).lower()
    return False


class _RetryState:
    """
    "Abhi ek retry ka wait chal raha hai" - frontend ke liye.

    Retry server par hoti hai, is liye browser ko sirf ek lambi pending request
    nazar aati hai. Time-based guess kaam nahi karta: blog generation waise hi
    30s+ leti hai, to spinner jhoot bol kar "retrying" dikhata. Is liye asli
    signal yahan rakha hai aur /api/llm/status se serve hota hai.

    Backend ek single uvicorn process hai, to module-level state kaafi hai.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._resume_at = 0.0
        self._what = ""

    def begin(self, what: str, wait: float) -> None:
        with self._lock:
            self._active += 1
            self._what = what
            self._resume_at = max(self._resume_at, time.monotonic() + wait)

    def end(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            if self._active == 0:
                self._resume_at = 0.0
                self._what = ""

    def snapshot(self) -> dict:
        with self._lock:
            if self._active <= 0:
                return {"retrying": False, "message": None, "seconds_remaining": 0.0}
            remaining = max(0.0, self._resume_at - time.monotonic())
            return {
                "retrying": True,
                "message": RETRYING_MESSAGE,
                "seconds_remaining": round(remaining, 1),
                "what": self._what,
            }


_retry_state = _RetryState()


def retry_status() -> dict:
    """Kya is waqt koi rate-limit wait chal raha hai? (frontend ise poll karta hai)"""
    return _retry_state.snapshot()


def call_with_failover(
    purpose: str,
    run,
    *,
    what: str = "AI request",
    max_wait: float = RETRY_MAX_WAIT_SECONDS,
    key_env: str | None = None,
):
    """
    `run(lane)` chalao — rate limit par PEHLE agli LANE, phir wait.

    Tarteeb:
      1. Is purpose ki pehli lane jo cooling na ho (PURPOSE_LANES ki tarteeb).
      2. 429 -> us lane ko cooling mark karo aur AGLI lane par foran dobara.
         Yahan koi sleep nahi hoti — yehi is poore mechanism ka faida hai.
         SEO purposes ke liye lane 1 OpenAI hai aur 2-3 dono Groq keys, to
         teen mukammal koshishein bina ek second rukay ho jati hain.
      3. Har lane 429 de de -> provider ka bataya wait kar ke ek aakhri
         koshish, bilkul purane behaviour ki tarah.

    `run` ko puri Lane milti hai (key, model, base_url) — is liye wo har
    koshish sahi provider par bhej sakta hai.

    Rate limit ke ilawa har error waise ka waisa upar jata hai.
    """
    lane = resolve_lane(purpose, key_env=key_env)
    if not lane.key:
        # Key hai hi nahi — run() ko chalne do taake asli error caller tak jaye.
        return run(lane)

    tried: list[str] = []
    exc: Exception | None = None
    hint: float | None = None

    while True:
        tried.append(lane.slot)
        try:
            result = run(lane)
            if len(tried) > 1:
                logger.info("[llm] %s kaamyaab — lane %s", what, lane.slot)
            return result
        except Exception as current:
            if not is_rate_limit_error(current):
                raise
            exc = current
            hint = parse_retry_after(_error_body(current))
            _key_pool.mark_cooling(lane.env, hint)

        # ── Step 2: agli lane, bina rukay ────────────────────────────
        nxt = None if key_env else _key_pool.next_lane(purpose, tried)
        if not nxt:
            break
        nxt_lane = lane_for(purpose, nxt)
        if not nxt_lane.key:
            break
        logger.warning(
            "[llm] %s rate limited on %s — %s lane par foran failover",
            what, lane.slot, nxt,
        )
        lane = nxt_lane

    logger.warning("[llm] %s: har lane rate limited — ab wait", what)

    # ── Step 3: purana wait-and-retry-once ───────────────────────────
    return _wait_then_retry(
        lambda: run(resolve_lane(purpose, key_env=key_env)),
        exc=exc,
        wait=hint,
        what=what,
        max_wait=max_wait,
    )


def call_with_retry(make_call, *, what: str = "AI request", max_wait: float = RETRY_MAX_WAIT_SECONDS):
    """
    `make_call()` chalao. Rate limit par Groq ka bataya wait kar ke EK BAAR aur.

    Purana raasta — key already bandhi hui hoti hai, is liye failover nahi ho
    sakta. Naye call sites `call_with_failover(purpose, run)` use karein.

    Rate limit ke ilawa koi bhi error waise ka waisa upar chala jata hai -
    truncation guard, JSON parse errors waghera ka behaviour nahi badla.
    """
    try:
        return make_call()
    except Exception as exc:
        if not is_rate_limit_error(exc):
            raise

        return _wait_then_retry(
            make_call,
            exc=exc,
            wait=parse_retry_after(_error_body(exc)),
            what=what,
            max_wait=max_wait,
        )


def _wait_then_retry(make_call, *, exc: Exception, wait: float | None, what: str, max_wait: float):
    """
    Groq ka bataya wait karo aur EK dafa aur koshish karo.

    Ye aakhri raasta hai — call_with_failover pehle har dusri lane aazma
    chuka hota hai. Yahan pahunchne ka matlab hai ke SAB thak chuki hain.
    """
    if wait is None:
        # 413 "request too large", ya koi naya format. Wait karna bekaar hai.
        logger.warning("[groq] %s rate limited, koi wait hint nahi - retry skip", what)
        raise RateLimitedError() from exc

    if wait > max_wait:
        logger.warning(
            "[groq] %s rate limited, wait %.1fs > %.0fs cap - retry skip", what, wait, max_wait
        )
        raise RateLimitedError(retry_after=wait) from exc

    logger.warning("[groq] %s rate limited - %.1fs wait, phir ek retry", what, wait)
    _retry_state.begin(what, wait + _RETRY_BUFFER_SECONDS)
    try:
        time.sleep(wait + _RETRY_BUFFER_SECONDS)
        result = make_call()
    except Exception as retry_exc:
        if is_rate_limit_error(retry_exc):
            logger.error("[groq] %s retry ke baad bhi rate limited", what)
            raise RateLimitedError(
                retry_after=parse_retry_after(_error_body(retry_exc))
            ) from retry_exc
        raise
    finally:
        _retry_state.end()

    logger.info("[groq] %s retry par kaamyaab", what)
    return result


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def post_with_retry(url: str, *, headers: dict, payload: dict, timeout: int, what: str) -> dict:
    """
    Raw REST call sites ke liye wrapper — key already headers mein bandhi hui.

    requests.post + raise_for_status + .json(), poora call_with_retry ke andar -
    warna retry sirf purani response dobara parse karti.

    Failover chahiye to `chat_completion()` use karo — ye purane callers ke
    liye hai jo apni key khud manage karte hain.
    """
    import requests

    def _call() -> dict:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()

    return call_with_retry(_call, what=what)


def chat_completion(
    purpose: str,
    payload: dict,
    *,
    what: str,
    timeout: int = 60,
    url: str | None = None,
) -> dict:
    """
    Chat completion — provider, key, model aur failover sab yahan handle hote hain.

    `payload` mein `model` mat bhejo; is purpose ki abhi wali lane ka model
    apne aap lag jata hai. 429 par agli lane foran try hoti hai (dekho
    call_with_failover), aur payload har lane ke liye adapt hota hai.

    `url` sirf tab do jab kisi khaas endpoint par bhejna ho; warna lane apna
    URL khud chunti hai (Groq ya OpenAI).

    Return: raw JSON dict, bilkul post_with_retry ki tarah — call sites
    check_raw_response() se hi content nikalti hain.
    """
    import requests

    def _run(lane: Lane) -> dict:
        response = requests.post(
            url or lane.chat_url,
            headers={
                "Authorization": f"Bearer {lane.key}",
                "Content-Type": "application/json",
            },
            json=adapt_payload(payload, lane),
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
        # Billing YAHAN hoti hai, check_raw_response() mein nahi. Har caller
        # us helper ko use nahi karta — brand_improvement apna _extract_content
        # rakhta hai — aur us soorat mein poora kharcha ledger se ghayab ho
        # jata tha, yani spend cap kabhi lagta hi nahi. Ye wo ek jagah hai
        # jahan se HAR lane-routed request guzarti hai.
        record_usage(_model_of(result), _usage_from(result))
        return result

    return call_with_failover(purpose, _run, what=what)


class TruncatedCompletionError(RuntimeError):
    """
    LLM ne output beech mein chhod diya (finish_reason == "length").

    Ye chup-chaap pass ho jata tha: adhoora blog article DB mein complete ki
    tarah save ho jata tha ("1. Identify Your Primary Use" par khatam). Ab har
    call site ise explicitly check karti hai.
    """


def check_finish_reason(finish_reason: str | None, what: str, *, max_tokens: int | None = None) -> None:
    """
    finish_reason validate karta hai. "length" ka matlab hai model token
    ceiling par ruk gaya — output ADHOORA hai, save nahi karna chahiye.
    """
    if finish_reason == "length":
        hint = f" (max_tokens={max_tokens})" if max_tokens else ""
        raise TruncatedCompletionError(
            f"{what} was cut short — the model hit its output limit{hint}. "
            "Please try again."
        )


def check_sdk_response(response, what: str, *, max_tokens: int | None = None) -> str:
    """
    groq SDK response ke liye: finish_reason check + content return.
    Khali content bhi failure hai (gpt-oss reasoning tokens sab kha jaye to
    aisa hota hai).
    """
    record_usage(_model_of(response), _usage_from(response))

    choice = response.choices[0]
    check_finish_reason(getattr(choice, "finish_reason", None), what, max_tokens=max_tokens)

    content = (choice.message.content or "").strip()
    if not content:
        raise TruncatedCompletionError(
            f"{what} returned empty content — the model produced no output. Please try again."
        )
    return content


def check_raw_response(result: dict, what: str, *, max_tokens: int | None = None) -> str:
    """Raw REST (requests.post) response ke liye wahi checks."""
    choices = result.get("choices") or []
    if not choices:
        raise TruncatedCompletionError(f"{what} returned no choices.")

    check_finish_reason(choices[0].get("finish_reason"), what, max_tokens=max_tokens)

    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise TruncatedCompletionError(f"{what} returned empty content. Please try again.")
    return content


# ── Model capability quirks ───────────────────
#
# Har model har param support nahi karta. Model assignment ab PURPOSE_MODELS se
# badal sakti hai, is liye call sites ko model-aware hona chahiye — warna purpose
# ko doosre model par shift karte hi request 400 dene lagti hai.
#
# Measured:
#   openai/gpt-oss-*   reasoning_effort: YES  |  max_tokens: enforced
#   groq/compound*     reasoning_effort: NO (400)  |  max_tokens: IGNORED
#                      (max_tokens=16 diya, 3,329 completion tokens aaye,
#                       finish_reason="stop" — agentic loop apna output khud
#                       decide karta hai)

def supports_reasoning_effort(model: str) -> bool:
    """gpt-oss family hi reasoning_effort leti hai; compound 400 deta hai."""
    return model.startswith("openai/gpt-oss")


def enforces_max_tokens(model: str) -> bool:
    """
    compound* max_tokens ko ignore karta hai — us par truncation guard bhi
    kabhi fire nahi karega, aur per-call token cost bounded nahi hai.
    """
    return not model.startswith("groq/compound")


def reasoning_params(model: str, effort: str = "low") -> dict:
    """
    Model ke hisaab se reasoning params. Unsupported model par khali dict —
    call site bina soche `**reasoning_params(model)` spread kar sakti hai.
    """
    return {"reasoning_effort": effort} if supports_reasoning_effort(model) else {}
