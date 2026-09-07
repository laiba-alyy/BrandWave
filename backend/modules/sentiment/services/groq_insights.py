"""
Groq-based insight extraction for the sentiment module.

SAAF TAQSEEM (hybrid design):
    * SENTIMENT ka faisla SIRF XLM-RoBERTa model karta hai (inference.py).
      Groq ko sentiment decide karne ki ijazat NAHI hai.
    * Groq SIRF ye nikalta hai:
        - pain_points : asli complaints
        - desires     : asli wishes (jo cheez customer chahta hai magar mili nahi)
        - loved       : asli tareef
        - emotions    : reviews ke aar-paar emotion counts

Ye purani `insight_extraction.py` ki jagah leta hai, jo substring keyword
matching karti thi — us mein `'no'` jaisa keyword "not/now/know/nothing" sab se
match ho jata tha, is liye tareef bhi complaint ban jati thi.

Fail-safe: Groq down ho, key missing ho, ya JSON kharab aaye — to khali lists
aur zero counts wapas aate hain. Pipeline kabhi crash nahi hoti.
"""

import json
import logging
import os
import re
import time
from typing import Dict, List

import requests

# Lane routing (OpenAI -> Groq -> Groq2), payload adaptation aur spend
# tracking sab yahan se aate hain. Pehle ye file seedha Groq ko POST karti
# thi, is liye 8,000 TPM par atak jati thi jab ke OpenAI lane khali pari thi.
from modules.llm_config import chat_completion

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

# Model id .env se override ho sakta hai. Default `openai/gpt-oss-120b` hai —
# ye live /models list ke against verify kiya gaya hai (Groq ne 2026 mein kai
# purane llama/mixtral models retire kar diye the, is liye hardcode-from-memory
# na karo; verify_model() se check kar sakte ho).
DEFAULT_MODEL = os.getenv("GROQ_MODEL_SENTIMENT", "openai/gpt-oss-120b")

# Groq API key — selection ab modules/llm_config.py ka key pool karta hai.
# Ye module "sentiment" purpose par hai, jo ALT key slot par baitha hai; us
# slot ka env naam GROKAPIKEY2 / GROKAPIKEYSentiment mein se jo bhi set ho.
# Ek key rate limited ho to pool doosri chun leta hai.
# NOTE: do KEYS ek hi account ki theek hain; do ACCOUNTS Groq ToS ke khilaf hain.
# Sirf error message ke liye — asli selection modules/llm_config.py ka key pool
# karta hai (dekho get_api_key neeche).
KEY_ENV_CANDIDATES = ("GROQ_API_KEY", "GROKAPIKEY2", "GROKAPIKEYSentiment")

# Ek call mein kitne reviews bhejne hain.
# 25 par Trustpilot ke lambe reviews milkar prompt itna bara kar dete the ke
# Groq 413 "Request too large" (org TPM limit) de deta tha. 12 par ek call
# aaram se fit hoti hai; 20 reviews = 2 calls, jo abhi bhi sasta hai.
# Ek call mein kitni reviews. 12 se 40 kiya gaya.
#
# 12 us waqt theek tha jab kul reviews hi ~20 hoti thin. 785 par wo 66 calls
# ban jata hai. OpenAI lane par context bara hai (gpt-4o-mini: 128k) aur TPM
# 200,000 — to 40 aaram se jata hai aur calls 66 se 20 par aa jati hain.
#
# Is se zyada bhi ja sakte hain, magar ek hi prompt mein bohat zyada reviews
# daalne par model tafseel khone lagta hai (chhoti shikayat bari ke neeche
# dab jati hai). 40 quality aur raftaar ke darmiyan hai.
REVIEWS_PER_CALL = int(os.getenv("GROQ_REVIEWS_PER_CALL", "40"))

# Groq ko zyada se zyada itni reviews jati hain (insights ke liye).
#
# KYUN ZAROORI HAI: neeche wala loop har REVIEWS_PER_CALL par ek API call
# karta hai. Jab tak sources ~20 reviews dete thay, ye loop ek-do dafa
# chalta tha (code ka comment bhi yehi kehta tha). Third-party YouTube
# source aane ke baad Gymshark par 785 items aa gaye — yani 66 calls.
# Groq ka free tier 8,000 tokens/minute deta hai aur har call ~1,900 tokens
# maangti hai, to 66 calls ka matlab tha ~16 MINUTE ka intezar aur 429 ka
# toofan.
#
# AHEM: ye cap sirf INSIGHTS par hai. Sentiment MODEL phir bhi SAARI
# reviews par chalta hai (wo local hai aur tez), is liye positive/negative
# percentages poore data par hi bante hain. Groq sirf themes nikaalta hai —
# "kya cheez logon ko pasand/na-pasand hai" — aur us ke liye ek achha
# namoona kaafi hai.
# 0 = koi hadd nahi (default): HAR review insights mein jati hai.
#
# Ye pehle 60 tha, us waqt jab sentiment Groq ki 8,000 TPM par tha aur poora
# dataset bhejna 16 minute lag jata. Ab lane OpenAI hai (200,000 TPM), is
# liye hadd ki zaroorat nahi rahi — aur brand owner ko poore data par bane
# insights milte hain, namoone par nahi.
#
# Agar kabhi waqt ya kharcha baandhna ho to yahan koi number rakh dein;
# sampling ka poora raasta abhi bhi mojood hai.
MAX_INSIGHT_REVIEWS = int(os.getenv("GROQ_MAX_INSIGHT_REVIEWS", "0"))

# Aik review se itne characters se zyada nahi bhejte — Trustpilot par kuch
# reviews bohat lambe hote hain aur poora token budget kha jate hain.
MAX_REVIEW_CHARS = 600

REQUEST_TIMEOUT = 60

# gpt-oss-120b ek REASONING model hai. Default effort par ye apna poora
# max_tokens budget andaruni reasoning par kharch kar deta tha aur visible
# content khali reh jata tha — jis se Groq `json_validate_failed` (400)
# return karta tha aur insights khali aa jate the.
# 'low' se reasoning tokens tqreeban aadhe ho jate hain aur JSON reliably aata hai.
REASONING_EFFORT = "low"
MAX_TOKENS = 2500

# json_validate_failed intermittent hota hai, is liye ek retry.
MAX_ATTEMPTS = 2

# Free "on_demand" tier par gpt-oss-120b ki limit 8,000 tokens/minute hai.
# Do analyses back-to-back chalane par 429 aa jata hai. Groq error body mein
# exact wait bata deta hai ("Please try again in 3.7s"), to wahi wait kar ke
# ek dafa dobara koshish karte hain. Isse zyada wait karna user ko hang lagta
# hai, is liye cap laga hua hai.
MAX_RATE_LIMIT_WAIT = 12.0

EMOTION_KEYS = [
    "happy",
    "angry",
    "frustrated",
    "disappointed",
    "excited",
    "satisfied",
    "neutral",
]


def _empty_result() -> Dict:
    """Har failure path yahi shape wapas karta hai."""
    return {
        "pain_points": [],
        "desires": [],
        "loved": [],
        "emotions": {k: 0 for k in EMOTION_KEYS},
    }


def get_api_key() -> str | None:
    """
    Is module ki Groq key — ab llm_config ke key pool se.

    Pehle yahan `GROKAPIKEYSentiment` naam se hardcoded lookup thi. Wo naam
    .env mein badal gaya (ab GROKAPIKEY2 hai) aur ye chup-chaap shared key par
    gir jata tha. Pool dono naam jaanta hai, aur ek key rate limited ho to
    doosri chun leta hai — yani yahan bhi wahi failover milta hai jo baaqi
    modules ko.
    """
    from modules.llm_config import resolve_groq

    key, _model, env = resolve_groq("sentiment")
    if key:
        logger.debug("[sentiment] using Groq key from %s", env)
        return key

    logger.warning(
        "No Groq API key found (checked %s) — insights will be empty.",
        ", ".join(KEY_ENV_CANDIDATES),
    )
    return None


def verify_model(model: str = DEFAULT_MODEL) -> bool:
    """
    Live /models list ke against check karo ke ye model abhi mojood hai.
    Sirf diagnostics ke liye — normal flow ise call nahi karta.
    """
    key = get_api_key()
    if not key:
        return False
    try:
        r = requests.get(
            GROQ_MODELS_URL,
            headers={"Authorization": f"Bearer {key}", "User-Agent": "BrandWave/1.0"},
            timeout=30,
        )
        r.raise_for_status()
        available = {m["id"] for m in r.json().get("data", [])}
        ok = model in available
        logger.info("Groq model %r available: %s", model, ok)
        return ok
    except Exception as e:
        logger.warning("Could not verify Groq model list: %s", e)
        return False


SYSTEM_PROMPT = (
    "You are a precise customer-feedback analyst for an e-commerce brand. "
    "You read customer reviews and extract structured insights. "
    "You ALWAYS reply with a single valid JSON object and nothing else. "
    "You never decide overall sentiment — that is handled by a separate model."
)


def _build_user_prompt(reviews: List[str]) -> str:
    numbered = "\n".join(
        f"{i}. {t[:MAX_REVIEW_CHARS]}" for i, t in enumerate(reviews, 1)
    )
    return f"""Analyse these {len(reviews)} customer reviews.

Reviews may be in English, Roman Urdu, or a mix. Understand both.

Return ONLY this JSON object:

{{
  "pain_points": ["short specific complaint", ...],
  "desires":     ["short specific wish", ...],
  "loved":       ["short specific praise", ...],
  "emotions": {{
    "happy": 0, "angry": 0, "frustrated": 0, "disappointed": 0,
    "excited": 0, "satisfied": 0, "neutral": 0
  }}
}}

STRICT RULES:
- "pain_points" = things that WENT WRONG. An actual complaint the customer made.
  Example: "Order arrived two weeks late", "Fabric colour faded after one wash".
- "desires" = things the customer WANTS BUT DOES NOT HAVE. A real wish or request.
  Example: "Wants more plus-size options", "Wants cash-on-delivery payment".
  A complaint is NOT a desire. Only include a genuine unmet want.
- "loved" = things the customer PRAISED. Actual positive feedback.
  Example: "Fast delivery", "Beautiful embroidery quality".
- NEVER put the same idea in more than one list.
- NEVER invent anything that is not in the reviews.
- If a category has nothing, return an empty list [] for it. Do not pad it.
- Each item: max 12 words, specific, no numbering, no quotes inside.
- Maximum 8 items per list.
- "emotions" = how many of the {len(reviews)} reviews express each emotion.
  Integers only. A review may count toward at most one emotion.
  The counts must sum to at most {len(reviews)}.

REVIEWS:
{numbered}"""


def _parse_json_safely(raw: str) -> Dict | None:
    """
    Groq ka jawab JSON mein parse karo.

    JSON mode on hone ke bawajood models kabhi kabhi ```json fences ya
    aage-peeche text laga dete hain, is liye defensive parsing.
    """
    if not raw:
        return None

    text = raw.strip()

    # ```json ... ```  ya  ``` ... ```  fences hatao
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Aakhri koshish: pehle { se aakhri } tak ka hissa nikaal kar parse karo
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse Groq response as JSON. First 300 chars: %s", text[:300])
    return None


def _clean_list(value, limit: int = 8) -> List[str]:
    """Jo bhi Groq ne bheja usko saaf string list banao."""
    if not isinstance(value, list):
        return []
    out: List[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip().strip('"').strip()
        if not s or len(s) < 3:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _clean_emotions(value) -> Dict[str, int]:
    """Sirf expected keys, sirf non-negative ints."""
    result = {k: 0 for k in EMOTION_KEYS}
    if not isinstance(value, dict):
        return result
    for k in EMOTION_KEYS:
        raw = value.get(k, 0)
        try:
            result[k] = max(0, int(raw))
        except (TypeError, ValueError):
            result[k] = 0
    return result


def _dedupe_across_lists(data: Dict) -> Dict:
    """
    Ek hi baat do lists mein na aaye. Priority: pain_points > desires > loved.
    (Prompt bhi mana karta hai, magar model kabhi kabhi phir bhi repeat karta hai.)
    """
    seen = set()
    for key in ("pain_points", "desires", "loved"):
        kept = []
        for item in data.get(key, []):
            norm = re.sub(r"[^a-z0-9 ]", "", item.lower()).strip()
            if norm in seen:
                logger.debug("Dropping cross-list duplicate from %s: %r", key, item)
                continue
            seen.add(norm)
            kept.append(item)
        data[key] = kept
    return data


def _parse_retry_after(resp) -> float | None:
    """
    Groq kitna wait bolta hai wo nikalo.

    Pehle Retry-After header, phir error message se
    "Please try again in 3.735s" ya "in 1m12.4s".
    """
    header = resp.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass

    m = re.search(
        r"try again in\s+(?:(\d+)m)?([\d.]+)s", resp.text, re.IGNORECASE
    )
    if m:
        minutes = float(m.group(1) or 0)
        seconds = float(m.group(2))
        # +0.5s buffer taake window bilkul boundary par na lage
        return minutes * 60 + seconds + 0.5
    return None


def _call_groq(reviews: List[str], model: str, key: str) -> Dict | None:
    """
    Ek chunk ke liye LLM call — ab LANE system ke zariye.

    Pehle ye seedha GROQ_URL par POST karta tha, yani llm_config ki lanes,
    failover aur spend-tracking mein se kuch bhi is par lagu nahi hota tha.
    Isi liye jab Groq ki 8,000 TPM bhar jati thi to yahan sirf 429 aur
    intezaar tha — halanke OpenAI lane (200,000 TPM) khali pari thi.

    Ab `chat_completion(purpose="sentiment")` istemal hota hai:
      * lane ka intikhab aur model llm_config se aata hai
      * 429 par agli lane FORAN try hoti hai (OpenAI -> Groq -> Groq2)
      * `adapt_payload` har lane ke liye payload theek kar deta hai
        (Groq ka `reasoning_effort` OpenAI par apne aap hat jata hai)
      * kharcha ledger mein darj hota hai, spend cap chalta rehta hai

    `model` aur `key` parameters signature mein rakhe gaye hain taake purani
    call sites na tootein — ab inhein lane khud tay karti hai.
    """
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(reviews)},
        ],
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "reasoning_effort": REASONING_EFFORT,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = chat_completion(
                "sentiment",
                payload,
                what="Sentiment insights",
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as e:
            # call_with_failover saari lanes aazma chuka hai. Ek chunk ka
            # girna poori analysis nahi giraata — baqi chunks chalte rehte
            # hain aur jo mila us se insights ban jate hain.
            logger.error("Insight chunk failed on every lane (attempt %d/%d): %s",
                         attempt, MAX_ATTEMPTS, e)
            return None

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.warning("LLM response had no content (attempt %d/%d)",
                           attempt, MAX_ATTEMPTS)
            continue

        parsed = _parse_json_safely(content)
        if parsed is not None:
            return parsed
        # json_validate_failed waqtan hota hai (reasoning model ka token
        # budget) — isi liye ek dobara koshish.
        logger.warning("LLM returned unparseable JSON (attempt %d/%d)",
                       attempt, MAX_ATTEMPTS)

    return None


def _sample_for_insights(texts, cap):
    """
    Bara dataset -> chhota, MUTANAWWA (diverse) namoona.

    Do baatein jaan boojh kar:
      * Pehle bohat chhote comments nikaal dete hain ("nice", "🔥") — wo
        theme nikaalne mein kuch nahi dete magar token kha jate hain.
      * Phir BARABAR faasle se chunte hain, shuru ke `cap` nahi lete.
        Combined list source ke hisab se tarteeb mein hoti hai (pehle
        Trustpilot, phir YouTube, phir review videos) — pehle 60 le lete to
        namoona sirf Trustpilot ka hota aur YouTube ki raaye ghayab hoti.
    """
    if len(texts) <= cap:
        return texts
    substantive = [t for t in texts if len(t) >= 30] or texts
    if len(substantive) <= cap:
        return substantive
    step = len(substantive) / cap
    return [substantive[int(i * step)] for i in range(cap)]


def extract_insights(reviews: List[str], model: str = DEFAULT_MODEL) -> Dict:
    """
    Reviews se pain points / desires / loved / emotions nikalo.

    Parameters
    ----------
    reviews : list of review text strings (sirf text, sentiment nahi)

    Returns
    -------
    {
      "pain_points": [str],
      "desires":     [str],
      "loved":       [str],
      "emotions":    {"happy": int, ... "neutral": int}
    }
    Fail hone par sab khali/zero — kabhi exception raise nahi karta.
    """
    if not reviews:
        return _empty_result()

    key = get_api_key()
    if not key:
        return _empty_result()

    texts = [t for t in (r.strip() for r in reviews) if t]
    if not texts:
        return _empty_result()

    combined = _empty_result()

    total_available = len(texts)
    if MAX_INSIGHT_REVIEWS > 0:
        texts = _sample_for_insights(texts, MAX_INSIGHT_REVIEWS)
    if len(texts) < total_available:
        logger.info(
            "Groq insights: sampling %d of %d reviews (cap=%d) -> %d API call(s)",
            len(texts), total_available, MAX_INSIGHT_REVIEWS,
            -(-len(texts) // REVIEWS_PER_CALL),
        )

    for start in range(0, len(texts), REVIEWS_PER_CALL):
        chunk = texts[start : start + REVIEWS_PER_CALL]
        try:
            parsed = _call_groq(chunk, model, key)
        except requests.exceptions.RequestException as e:
            logger.error("Groq request failed: %s", e)
            parsed = None
        except Exception as e:
            logger.error("Unexpected Groq error: %s", e, exc_info=True)
            parsed = None

        if not parsed:
            continue

        combined["pain_points"].extend(_clean_list(parsed.get("pain_points")))
        combined["desires"].extend(_clean_list(parsed.get("desires")))
        combined["loved"].extend(_clean_list(parsed.get("loved")))

        emo = _clean_emotions(parsed.get("emotions"))
        for k in EMOTION_KEYS:
            combined["emotions"][k] += emo[k]

    # Chunks ke beech duplicates hata do, phir lists ke aar-paar
    for k in ("pain_points", "desires", "loved"):
        combined[k] = _clean_list(combined[k])
    combined = _dedupe_across_lists(combined)

    logger.info(
        "Groq insights: %d pain points, %d desires, %d loved, emotions=%s",
        len(combined["pain_points"]),
        len(combined["desires"]),
        len(combined["loved"]),
        combined["emotions"],
    )
    return combined


if __name__ == "__main__":
    # Quick smoke test:
    #   python -m modules.sentiment.services.groq_insights
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()

    print("Model available:", verify_model())
    demo = [
        "Delivery took three weeks, way too slow.",
        "The embroidery is gorgeous, absolutely stunning work!",
        "I wish they offered cash on delivery, card only is annoying.",
        "Fabric faded after the first wash, very disappointed.",
        "Customer support replied in minutes, really helpful team.",
        "Please add bigger sizes, nothing fits me above medium.",
    ]
    print(json.dumps(extract_insights(demo), indent=2))
