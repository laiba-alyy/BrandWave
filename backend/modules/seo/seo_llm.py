"""
SEO LLM module — keyword generation, content optimization.

Keyword Flow:
  Step 1: Extract seeds (sophisticated document-frequency extractor)
  Step 2: LLM generates 30 candidates (with Groq retry)
  Step 3: Google Autocomplete validates + filters junk
  Step 4: Score by validation + product relevance + intent
  Step 5: Top TARGET_KEYWORDS (default 30) returned
  Step 6: Optional DataForSEO enrichment (credit-protected, never crashes)

Fallbacks:
  LLM fail → template phrases (never raw single words)
  Autocomplete fail → all candidates survive, no validation bonus
  DataForSEO fail/unfunded → volume shows N/A, keywords still valid
"""

import json
import logging
import os
import re
import requests
from collections import Counter
from datetime import datetime
from typing import List, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from modules.llm_config import (
    chat_completion,
    get_groq_config,
    post_with_retry,
    check_raw_response,
    reasoning_params,
    RateLimitedError,
)
from modules.seo.seed_extractor import CITIES, DEMONYMS, seed_terms as _extract_seed_terms
from modules.seo.dataforseo_service import account_status, is_configured
from modules.store_locale import COUNTRY_NAME_TO_ISO, ISO_COUNTRY_NAMES

logger = logging.getLogger(__name__)

# ── Location detection (product content location-neutral rehna chahiye) ──
#
# Mulk ke naam POORE phrase ke tor par match hote hain, alag alfaz se nahi:
# "Ivory Coast" ko alfaz mein torne se "ivory" (ek asli fashion colour)
# location ban jata.
#
# Matching word-boundary ke sath hai, plain substring se NAHI. Warna chhote
# mulk ke naam doosre alfaz ke andar match ho jate hain — "oman" to "woman"
# aur "romantic" dono ke andar maujood hai, aur womenswear ki har description
# jhooti location violation ban jati.
_LOCATION_TERMS = (
    {
        re.sub(r"^the\s+", "", str(n).lower().strip())
        for n in list(ISO_COUNTRY_NAMES.values()) + list(COUNTRY_NAME_TO_ISO)
        if str(n).strip()
    }
    | CITIES
    | DEMONYMS
    | {"uae", "usa", "emirates"}
)
_LOCATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in sorted(_LOCATION_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _location_hits(text: str) -> List[str]:
    """Text mein jo bhi country/city/demonym mile, wo wapas do (warna khaali)."""
    return sorted({m.lower() for m in _LOCATION_RE.findall(text or "")})

# ── Country code mapping ──
COUNTRY_CODES = {
    "pakistan": "pk", "united states": "us", "united kingdom": "gb",
    "india": "in", "uae": "ae", "united arab emirates": "ae",
    "canada": "ca", "australia": "au", "saudi arabia": "sa",
    "germany": "de", "france": "fr", "turkey": "tr",
}


def _get_country_code(store_country: str) -> str:
    if not store_country:
        return "pk"
    return COUNTRY_CODES.get(store_country.lower().strip(), "pk")


# ── Credit-protection constants ──
MIN_BALANCE_FOR_ENRICHMENT = 0.10   # USD — skip DataForSEO below this
ENRICH_TOP_N = 8                     # max keywords sent to DataForSEO per run
UNVALIDATED_FLOOR = 30               # min score for unvalidated keywords to survive
_free_mode = False                   # module-level flag: skip balance API re-check


# ── Kitne keywords ───────────────────────────────────────────────────
#
# TARGET_KEYWORDS wo tadaad hai jo user ko waqai milti hai. Baaqi do numbers
# usi se nikalte hain, is liye badalna sirf yahan hai.
#
# LLM_CANDIDATES > TARGET_KEYWORDS kyun: har candidate final list tak nahi
# pahunchta. Google Autocomplete step junk gira deta hai, aur uske baad
# unvalidated keywords par bhi cap lagta hai. 30 candidates maang kar 30
# keywords dena mumkin hi nahi tha — filter ke baad ~15-20 bachte the.
# ~1.7x maang kar filter ko asal mein kuch chunne ko milta hai.
#
# Ye 50 ab mehnga nahi para: keyword generation OpenAI lane par hai (dekho
# llm_config.PURPOSE_LANES), jahan na 8,000 TPM ki queue hai aur 50 phrases
# ka poora jawab ~$0.0005 ka parta hai. Autocomplete validation pehle se
# ThreadPool par hai, to 50 candidates 30 se ziyada der nahi lete.
TARGET_KEYWORDS = int(os.getenv("SEO_TARGET_KEYWORDS", "30"))
LLM_CANDIDATES = int(os.getenv("SEO_LLM_CANDIDATES", str(round(TARGET_KEYWORDS * 1.7))))

# Unvalidated (Google ne confirm nahi kiye) keywords ki hadd — quality guard.
# Pehle ye 8/15 tha, yani list ka aadha. Wahi nisbat 30 par rakhi hai.
MAX_UNVALIDATED = max(4, TARGET_KEYWORDS // 2)


# ═══════════════════════════════════════
# STEP 1 — Seed Extraction from Products
# ═══════════════════════════════════════

def extract_seed_keywords(products: list, max_seeds: int = 15) -> List[str]:
    """
    Products ke titles, categories, tags se seed keywords extract karo.
    No LLM needed — pure Python.
    """
    words = Counter()
    bigrams = Counter()

    stop_words = {
        "the", "a", "an", "and", "or", "of", "for", "in", "on", "to",
        "with", "by", "is", "it", "at", "from", "as", "this", "that",
        "rts", "rtw", "pk", "rs", "new", "set", "piece", "price",
        "|", "-", "&", "/", "–", "—"
    }

    for product in products[:500]:
        title = product.get("name", "").lower()
        category = product.get("category", "").lower()
        tags = " ".join(product.get("tags", [])).lower()

        text = f"{title} {category} {tags}"
        tokens = [w.strip() for w in text.split() if len(w.strip()) > 2 and w.strip() not in stop_words]

        for token in tokens:
            words[token] += 1

        # Bigrams (2-word phrases)
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            bigrams[bigram] += 1

    # Combine top words and bigrams
    seeds = []
    for phrase, count in bigrams.most_common(10):
        if count >= 3:
            seeds.append(phrase)

    for word, count in words.most_common(20):
        if count >= 5 and word not in " ".join(seeds):
            seeds.append(word)

    return seeds[:max_seeds]


# ═══════════════════════════════════════
# STEP 2 — LLM Candidate Generation
# ═══════════════════════════════════════

def _mix(share: float) -> int:
    """Prompt ke breakdown ke liye tadaad — LLM_CANDIDATES ke hisaab se."""
    return max(2, round(LLM_CANDIDATES * share))


def _generate_candidates_with_llm(
    seeds: List[str],
    brand_name: str,
    store_country: str,
    product_categories: list
) -> List[str]:
    """
    Seeds + brand info se LLM 30 keyword candidates generate karta hai.
    Rate-limit par post_with_retry ek baar wait + retry karta hai.
    """
    key, model = get_groq_config("seo_keywords")
    if not key:
        logger.warning("[SEO] GROQ_API_KEY not set — LLM keyword generation skipped")
        return []

    # Saal PROMPT mein diya jata hai, model ke andaze par nahi chhora jata.
    # gpt-4o-mini apni training ka saal maan leta hai (measured: "2023") aur
    # har seasonal keyword do saal purana aa jata hai. Groq wale model par ye
    # nazar nahi aaya tha kyunke uska default saal naya hai — yani ye bug lane
    # switch ke saath hi paida hota.
    current_year = datetime.now().year

    seeds_text = ", ".join(seeds[:10])
    categories_text = ", ".join(product_categories[:5]) if product_categories else "general"
    country = store_country or "international"

    prompt = f"""Generate exactly {LLM_CANDIDATES} SEO keyword phrases for this e-commerce store.

Brand: {brand_name}
Country: {country}
Categories: {categories_text}
Top product terms: {seeds_text}

Generate keywords that REAL customers would type in Google when shopping.

Rules:
- Do NOT add city names (no Karachi, Lahore, Dubai, Sydney, London)
- Country name ONLY when natural: "Pakistani bridal wear" is fine
- "{brand_name} collection" is fine
- Focus on: product type + attribute + buying intent
- The current year is {current_year}. If you mention a year at all, it MUST be
  {current_year} or {current_year + 1} — never an earlier year.
- Include mix of:
  * Brand keywords ({_mix(0.12)}): "{brand_name} [product] collection"
  * Product keywords ({_mix(0.37)}): "[attribute] [product] [intent]"
  * Long-tail keywords ({_mix(0.30)}): "[specific product] buy online"
  * Seasonal/trending ({_mix(0.12)}): "[product] {current_year}" or "[product] [season]"
  * Question / problem keywords ({_mix(0.09)}): "how to style [product]"

Good examples:
- "embroidered lawn suit 3 piece"
- "{brand_name} eid collection {current_year}"
- "buy unstitched chiffon dress online"
- "designer bridal wear price"

Bad examples (DO NOT generate):
- "Karachi embroidered lawn suit"
- "Sydney Pakistani fashion online"
- "Islamabad bridal wear"

Return ONLY a JSON array of {LLM_CANDIDATES} keyword strings. No explanation."""

    # ── max_tokens aur reasoning_effort ─────────────────────────────────────
    # 30 keyword phrases ka JSON khud ~400 tokens hai, magar gpt-oss ek
    # REASONING model hai: wo visible output se PEHLE andaruni reasoning
    # tokens kharch karta hai. 1,200 ke budget mein reasoning hi sab kuch kha
    # jata tha aur jawab beech mein kat jata (finish_reason="length").
    #
    # Us soorat mein pipeline chup-chaap "degraded template keywords" par gir
    # jati thi aur endpoint 200 ke sath wo templates return kar deta tha —
    # user ko lagta ke ye AI keywords hain. Log mein ye asli mein dekha gaya.
    #
    # reasoning_effort="low" reasoning tokens ~aadhe kar deta hai (yehi
    # seo_content aur seo_blog pehle se karte hain), aur budget bhi bara hai.
    # ~60 tokens per keyword phrase (JSON quoting + comma), plus headroom.
    # OpenAI lane par reasoning tokens nahi jalte, magar Groq fallback par
    # jalte hain — is liye budget usi hisaab se khula rakha hai.
    KEYWORDS_MAX_TOKENS = max(3000, LLM_CANDIDATES * 60)

    try:
        result = chat_completion(
            "seo_keywords",
            {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": KEYWORDS_MAX_TOKENS,
                **reasoning_params(model, "low"),
            },
            timeout=60,
            what="SEO keyword generation",
        )
        text = check_raw_response(result, what="SEO keywords", max_tokens=KEYWORDS_MAX_TOKENS)
        text = text.replace("```json", "").replace("```", "").strip()
        keywords = json.loads(text)

        if isinstance(keywords, list):
            return [
                str(k).strip().lower()
                for k in keywords
                if isinstance(k, str) and len(k.strip()) > 3
            ][:LLM_CANDIDATES]
        logger.warning("[SEO] LLM returned non-list: %s", type(keywords))

    except RateLimitedError:
        raise   # propagate to route → 429
    except Exception as e:
        logger.warning("[SEO] LLM keyword generation failed: %s", e)

    return []


# ═══════════════════════════════════════
# STEP 3 — Google Autocomplete Validation
# ═══════════════════════════════════════

def _validate_with_autocomplete(candidates: List[str], country_code: str) -> List[Dict]:
    """
    Google Autocomplete se validate karo — validated keywords rank higher,
    clear junk (unvalidated + low score) is dropped.
    """
    try:
        from modules.seo.google_autocomplete import validate_keywords_with_autocomplete
        validated = validate_keywords_with_autocomplete(candidates, country_code)
    except Exception as e:
        logger.warning("[SEO] Google Autocomplete failed: %s", e)
        validated = [
            {"keyword": k, "google_validated": False, "suggestions_found": 0}
            for k in candidates
        ]

    # Separate validated from unvalidated, drop unvalidated junk
    kept, dropped = [], 0
    for kw_data in validated:
        if kw_data.get("google_validated"):
            kept.append(kw_data)
        else:
            # Pre-score to decide if this unvalidated keyword is worth keeping
            pre = len(kw_data["keyword"].split()) * 5  # word-count proxy
            if pre >= 10:  # 2+ words minimum
                kept.append(kw_data)
            else:
                dropped += 1

    if dropped:
        logger.info("[SEO] Autocomplete filter dropped %d weak unvalidated keywords", dropped)
    return kept


# ═══════════════════════════════════════
# STEP 4 — Scoring
# ═══════════════════════════════════════

def _score_keyword(
    keyword_data: Dict,
    seeds: List[str],
    brand_name: str
) -> float:
    """
    Keyword ko score karo based on:
    - Google validation (+35)
    - Product match (+30)
    - Brand mention (+15)
    - Long-tail bonus (+12/+8)
    - Intent words (+10)
    """
    score = 0.0
    keyword = keyword_data["keyword"].lower()

    # Google validated = real keyword, strongest signal
    if keyword_data.get("google_validated"):
        score += 35

    # Product match — kitne seeds match karte hain
    seed_matches = sum(1 for seed in seeds if seed in keyword)
    score += min(seed_matches * 10, 30)

    # Brand name mention
    if brand_name.lower() in keyword:
        score += 15

    # Long-tail (3+ words) — less competition
    word_count = len(keyword.split())
    if word_count >= 3:
        score += 12
    if word_count >= 4:
        score += 8

    # Buying intent words
    intent_words = ["buy", "shop", "order", "price", "online", "sale", "discount", "collection", "new"]
    if any(w in keyword for w in intent_words):
        score += 10

    return round(score, 1)


def _determine_relevance(score: float) -> str:
    if score >= 60:
        return "High"
    elif score >= 40:
        return "Medium"
    return "Low"


def _detect_intent(keyword: str) -> str:
    keyword_lower = keyword.lower()
    transactional = ["buy", "order", "shop", "purchase", "price", "discount", "sale", "deal"]
    informational = ["how", "what", "guide", "tips", "ideas", "best", "review", "compare"]

    if any(w in keyword_lower for w in transactional):
        return "transactional"
    if any(w in keyword_lower for w in informational):
        return "informational"
    return "commercial"


# ═══════════════════════════════════════
# MAIN — Generate Keywords
# ═══════════════════════════════════════

def generate_keywords(
    brand_name: str,
    products: list,
    product_categories: list,
    store_country: str = "Pakistan",
    target_audience: str = ""
) -> List[Dict]:
    """
    Complete keyword generation pipeline:
    Seeds (sophisticated extractor) → LLM Candidates → Google Autocomplete
    (with filtering) → Scoring → Top TARGET_KEYWORDS (default 30).

    DataForSEO enrichment is NOT done here — the wrapper handles it
    as an optional credit-protected step.
    """
    country_code = _get_country_code(store_country)

    # Step 1: Extract seeds — sophisticated document-frequency extractor
    # 15 se barha kar 20: TARGET_KEYWORDS 30 hai, aur seeds hi wo pool hain
    # jis se LLM phrases banata hai. 15 seeds par 50 candidates maangne se
    # model wohi seed ghuma phira kar dobara likhne lagta hai.
    seeds = _extract_seed_terms(products, limit=max(15, TARGET_KEYWORDS * 2 // 3))
    logger.info("[SEO] Extracted %d seeds: %s...", len(seeds), seeds[:5])

    # Step 2: LLM generates LLM_CANDIDATES candidates (with lane failover)
    candidates = _generate_candidates_with_llm(
        seeds=seeds,
        brand_name=brand_name,
        store_country=store_country,
        product_categories=product_categories
    )
    logger.info("[SEO] LLM generated %d candidates", len(candidates))

    if not candidates:
        # LLM failed — build template phrases, NEVER raw single words
        return _degraded_keywords(seeds, brand_name, country_code)

    # Step 3: Google Autocomplete — validated rank higher, junk dropped
    validated = _validate_with_autocomplete(candidates, country_code)
    validated_count = sum(1 for v in validated if v.get("google_validated"))
    logger.info("[SEO] Autocomplete: %d validated / %d survived (of %d candidates)",
                validated_count, len(validated), len(candidates))

    # Step 4: Score each keyword
    scored = []
    for kw_data in validated:
        score = _score_keyword(kw_data, seeds, brand_name)
        keyword = kw_data["keyword"]
        scored.append({
            "keyword": keyword,
            "relevance": _determine_relevance(score),
            "opportunity_score": score,
            "search_intent": _detect_intent(keyword),
            "source": "Google Validated" if kw_data.get("google_validated") else "AI Suggested",
            "google_validated": kw_data.get("google_validated", False),
            "market": country_code.upper(),
        })

    scored.sort(key=lambda x: x["opportunity_score"], reverse=True)

    # Step 5: Final filter — drop unvalidated keywords below floor,
    # cap unvalidated at MAX_UNVALIDATED to keep quality high
    final = []
    unvalidated_count = 0
    for kw in scored:
        if kw["google_validated"]:
            final.append(kw)
        elif kw["opportunity_score"] >= UNVALIDATED_FLOOR:
            if unvalidated_count < MAX_UNVALIDATED:
                final.append(kw)
                unvalidated_count += 1

    final.sort(key=lambda x: x["opportunity_score"], reverse=True)
    result = final[:TARGET_KEYWORDS]
    logger.info("[SEO] Returning %d keywords (%d validated, %d AI-only)",
                len(result),
                sum(1 for k in result if k["google_validated"]),
                sum(1 for k in result if not k["google_validated"]))
    return result


def _degraded_keywords(seeds: List[str], brand_name: str, country_code: str = "PK") -> List[Dict]:
    """
    LLM failure fallback — builds template PHRASES from seeds, never raw
    single words.  "embroidered lawn buy online" is acceptable;
    "lawn" alone is not.
    """
    if not seeds:
        return []

    templates = [
        "buy {seed} online",
        "{seed} collection",
        "{seed} price",
        "best {seed}",
        "{seed} for women",
        "{brand} {seed}",
        "new {seed} design",
    ]

    keywords = []
    seen = set()
    bn = brand_name.lower() if brand_name else ""

    # 7 templates × seeds. 30 phrases ke liye kam az kam 5 seeds chahiye,
    # magar variety ke liye jitne mil sakein utne.
    for seed in seeds[:max(12, TARGET_KEYWORDS // 2)]:
        for tmpl in templates:
            phrase = tmpl.format(seed=seed, brand=bn).strip()
            if phrase in seen:
                continue
            seen.add(phrase)
            score = 35.0  # baseline for degraded
            if len(phrase.split()) >= 3:
                score += 12
            if bn and bn in phrase:
                score += 10
            keywords.append({
                "keyword": phrase,
                "relevance": _determine_relevance(score),
                "opportunity_score": score,
                "search_intent": _detect_intent(phrase),
                # Ye keywords LLM ne nahi banaye — ye seeds par template
                # lagaya hua natija hain. Pehle inka source bhi "AI Suggested"
                # likha jata tha, yani UI par ye asli AI keywords se bilkul
                # alag nazar hi nahi aate the. Ab saaf likha hai.
                "source": "Template (AI unavailable)",
                "degraded": True,
                "google_validated": False,
                "market": country_code.upper() if country_code else "PK",
            })
            if len(keywords) >= TARGET_KEYWORDS:
                break
        if len(keywords) >= TARGET_KEYWORDS:
            break

    keywords.sort(key=lambda x: x["opportunity_score"], reverse=True)
    logger.warning(
        "[SEO] LLM unavailable — returning %d TEMPLATE keywords (not AI-generated). "
        "Check the Groq error above; DataForSEO enrichment is skipped for these.",
        len(keywords),
    )
    return keywords[:TARGET_KEYWORDS]


# ═══════════════════════════════════════
# Content Optimization (unchanged from existing)
# ═══════════════════════════════════════

def generate_optimized_content(
    products: list,
    keywords: list,
    brand_name: str = "",
    store_country: str | None = None,
) -> list:
    """
    Products ke meta titles aur descriptions optimize karo using LLM.

    Output har item mein wo saare fields hote hain jo UI dikhata hai:
    original_name / original_title / original_description /
    optimized_title / optimized_description / dono _length.

    LOCATION-NEUTRAL by design: is prompt mein market ya secondary-market
    ki koi maloomat NAHI jati. Purana version brand ke ships-to markets
    (jin mein UAE shamil tha) LLM ko de deta tha, aur natija "...Set Dubai"
    jaisay titles thay jabke kisi product data mein Dubai ka zikr bhi nahi.
    Ek lawn suit location-specific product nahi hai.

    store_country sirf logging ke liye hai — prompt mein jaan boojh kar nahi
    jata. Pehle iski default "Pakistan" thi, jo har non-Pakistani brand ke
    liye ghalat thi aur chupke se content mein aa jati thi.
    """
    key, model = get_groq_config("seo_content")

    # Keywords se location-bearing terms nikal do. Multi-market keyword
    # allocation aise keywords bana sakti hai jin mein khud sheher ka naam ho
    # ("maria b abaya dubai") — wo prompt mein aate hi location wapas aa jati.
    clean_keywords, dropped = [], []
    for k in keywords:
        kw = str(k.get("keyword", "") if isinstance(k, dict) else k).strip()
        if not kw:
            continue
        (dropped if _location_hits(kw) else clean_keywords).append(kw)
    if dropped:
        logger.info("[SEO] content prompt se %d location keyword(s) hatae: %s",
                    len(dropped), dropped[:5])

    keyword_text = ", ".join(clean_keywords[:10]) or "(none — use the product details)"
    batch = list(products or [])[:10]
    if not batch:
        logger.warning("[SEO] content generation: is brand ke paas koi product nahi")
        return []

    products_text = ""
    for i, p in enumerate(batch):
        products_text += f"""
Product {i+1}:
  Title: {p.get('name', '')}
  Description: {(p.get('description') or '')[:200]}
  Price: {p.get('price', '')}
  Category: {p.get('category', '')}
"""

    logger.info(
        "[SEO] content generation: brand=%r products=%d keywords=%d "
        "store_country=%r (prompt mein NAHI jata — location-neutral)",
        brand_name, len(batch), len(clean_keywords), store_country,
    )

    # 10 products ka JSON ~750 output tokens hai, lekin gpt-oss output se PEHLE
    # reasoning tokens kharch karta hai — 2,500 par jawab beech mein kat jata tha
    # (finish_reason="length") aur endpoint 200 ke sath 0 items return karta tha.
    # reasoning_effort=low + bara budget, seo_blog.py wale hi tareeqe se.
    CONTENT_MAX_TOKENS = 4000

    def _ask(extra_rule: str = "") -> list:
        prompt = f"""Optimize these {len(batch)} product listings for SEO.
Brand: {brand_name}
Target keywords: {keyword_text}

{products_text}

For each product, in the SAME order, return:
- optimized_title (50-60 chars, include the brand name and the key product attributes)
- optimized_description (150-160 chars, include 1-2 keywords naturally)

Rules:
- Return EXACTLY {len(batch)} objects, in the same order as the products above.
- Use ONLY the real product details shown above. Do NOT invent colours,
  fabrics, occasions, seasons, events or features that are not in the data.
- LOCATION-NEUTRAL: do NOT name any country, city, region or nationality
  anywhere. No "Dubai", "UAE", "Pakistan", "Pakistani", no city names at all.
  These are not location-specific products.
- Include the brand name naturally.
- Make titles descriptive: "Blue Embroidered Lawn Shirt - 3 Piece | {brand_name}"
  NOT generic: "RTS | SHIRT"{extra_rule}

Return ONLY valid JSON array. No markdown, no explanation.
Format: [{{"optimized_title":"...","optimized_description":"..."}}]"""

        result = chat_completion(
            "seo_content",
            {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": CONTENT_MAX_TOKENS,
                **reasoning_params(model),
            },
            timeout=90,
            what="SEO content optimization",
        )
        text = check_raw_response(result, what="SEO content", max_tokens=CONTENT_MAX_TOKENS)
        text = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []

    def _build(parsed: list) -> list:
        """LLM output ko products ke sath index se jorh kar UI ki shape banao.

        original_name model se nahi mangwaya jata — index se product ka asli
        naam le lete hain. Model se echo karwana output tokens bhi zaya karta
        hai aur naam ghalat likhne ka mauqa bhi deta hai.
        """
        out = []
        for i, p in enumerate(batch):
            item = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
            title = str(item.get("optimized_title") or "").strip()
            desc = str(item.get("optimized_description") or "").strip()
            name = p.get("name") or ""
            out.append({
                "original_name": name,
                "original_title": name,
                "original_description": p.get("description") or None,
                "optimized_title": title,
                "optimized_description": desc,
                "optimized_title_length": len(title),
                "optimized_description_length": len(desc),
            })
        return out

    def _violations(recs: list) -> dict:
        bad = {}
        for r in recs:
            hits = _location_hits(r["optimized_title"] + " " + r["optimized_description"])
            if hits:
                bad[r["original_name"]] = hits
        return bad

    try:
        recs = _build(_ask())
        bad = _violations(recs)
        if bad:
            # Prompt mein location hai hi nahi, phir bhi model ne daal di — ek
            # dafa sakht reminder ke sath dobara pooch lo.
            logger.warning("[SEO] content mein location aa gayi, retry: %s", bad)
            retry = _build(_ask(
                "\n- CRITICAL: your previous attempt inserted place names. "
                "Remove every country, city, region and nationality completely."
            ))
            retry_bad = _violations(retry)
            if len(retry_bad) < len(bad):
                recs, bad = retry, retry_bad
            if bad:
                logger.error("[SEO] retry ke baad bhi location maujood: %s", bad)
        return recs

    except RateLimitedError:
        raise   # propagate to route → 429
    except Exception as e:
        logger.warning("[SEO] Content optimization failed: %s", e)
        return []
# ═══════════════════════════════════════
# Credit Protection — balance check
# ═══════════════════════════════════════

def _check_balance() -> float | None:
    """
    Free endpoint se DataForSEO balance check karo.
    Returns balance (USD) or None if check fails.
    """
    try:
        status = account_status()
        if not status.get("usable"):
            logger.info("[SEO] DataForSEO not usable: %s", status.get("reason"))
            return None
        balance = status.get("balance")
        if balance is not None:
            return float(balance)
    except Exception as e:
        logger.warning("[SEO] Balance check failed: %s", e)
    return None


def _enrich_with_dataforseo(
    keywords: List[Dict],
    db,
    profile,
    country: str,
    language: str = "en"
) -> List[Dict]:
    """
    Top keywords ko DataForSEO se enrich karo — search volume, difficulty.
    Credit-protected: skips if balance < MIN_BALANCE_FOR_ENRICHMENT.
    NEVER raises — all failures degrade silently to AI-only keywords.
    """
    global _free_mode

    if db is None:
        return keywords

    # Template fallback keywords par paisa kharch mat karo. Ek run mein
    # $0.1159 laga kar aise keywords enrich hote dekhe gaye jo LLM ne banaye
    # hi nahi the — us data ki koi qeemat nahi.
    if keywords and all(k.get("degraded") for k in keywords):
        logger.warning(
            "[SEO] all keywords are template fallbacks — skipping DataForSEO "
            "enrichment (would have spent credits on non-AI keywords)"
        )
        return keywords

    if not is_configured():
        logger.info("[SEO] DataForSEO not configured — skipping enrichment")
        return keywords

    if _free_mode:
        logger.info("[SEO] Free mode active — skipping DataForSEO (no re-check)")
        return keywords

    # Check balance BEFORE spending (free endpoint, $0 cost)
    balance = _check_balance()
    if balance is not None and balance < MIN_BALANCE_FOR_ENRICHMENT:
        logger.info(
            "[SEO] DataForSEO balance too low ($%.2f < $%.2f) — switching to free mode",
            balance, MIN_BALANCE_FOR_ENRICHMENT,
        )
        _free_mode = True
        return keywords

    # Only enrich top N keywords to minimize cost (~$0.09 per batched request)
    top_keywords = [kw["keyword"] for kw in keywords[:ENRICH_TOP_N]]

    try:
        from modules.seo.keyword_cache import enrich_with_cache

        result = enrich_with_cache(
            db=db,
            candidates=top_keywords,
            brand_profile=profile,
            country=country,
            language=language,
        )

        if not result.available:
            logger.info("[SEO] DataForSEO enrichment unavailable: %s", result.reason)
            return keywords

        # Map metrics back to keyword dicts
        enriched_count = 0
        for kw in keywords:
            metric = result.metrics.get(kw["keyword"].strip().lower())
            if metric and metric.has_data:
                kw["search_volume"] = metric.search_volume
                kw["difficulty"] = metric.keyword_difficulty
                kw["competition"] = metric.competition
                kw["cpc"] = metric.cpc
                if metric.search_intent:
                    kw["search_intent"] = metric.search_intent
                kw["source"] = "DataForSEO Validated"
                enriched_count += 1

        logger.info(
            "[SEO] DataForSEO enriched %d/%d keywords (cost $%.4f, cache: %s)",
            enriched_count, len(top_keywords), result.cost,
            result.cache_stats.get("from_cache", 0),
        )

    except Exception as e:
        logger.warning("[SEO] DataForSEO enrichment failed (non-fatal): %s", e)

    return keywords


# ═══════════════════════════════════════
# Route Wrapper — pipeline + enrichment + DB save
# ═══════════════════════════════════════

def generate_keyword_suggestions(profile, db, market=None, language=None):
    """
    Route se call hoti hai — profile se data extract karke
    generate_keywords pipeline run karo, optional DataForSEO enrichment,
    aur DB mein save karo.
    """
    from models.seo_result import SEOKeywordSuggestion

    # Profile se data extract karo
    brand_name = profile.business_name or ""
    products = profile.products or []
    categories = profile.product_categories or []
    store_country = profile.store_country or market or "Pakistan"
    target_audience = profile.target_audience or ""

    # Run main pipeline (seeds → LLM → Autocomplete → Scoring)
    keywords_list = generate_keywords(
        brand_name=brand_name,
        products=products,
        product_categories=categories,
        store_country=store_country,
        target_audience=target_audience
    )

    # Optional DataForSEO enrichment (credit-protected, never crashes)
    keywords_list = _enrich_with_dataforseo(
        keywords_list, db, profile,
        country=store_country,
        language=language or "en",
    )

    # Format for DB storage
    formatted_keywords = []
    for kw in keywords_list:
        formatted_keywords.append({
            "keyword": kw["keyword"],
            "relevance": kw["relevance"],
            "opportunity_score": kw.get("opportunity_score", 0),
            "search_intent": kw.get("search_intent", "commercial"),
            "source": kw.get("source", "AI Suggested"),
            "google_validated": kw.get("google_validated", False),
            "market": kw.get("market", "PK"),
            "search_volume": kw.get("search_volume"),
            "difficulty": kw.get("difficulty"),
            "competition": kw.get("competition"),
            "cpc": kw.get("cpc"),
        })

    # Purane keywords delete karo is brand ke
    db.query(SEOKeywordSuggestion).filter(
        SEOKeywordSuggestion.brand_profile_id == profile.id
    ).delete(synchronize_session=False)

    suggestion = SEOKeywordSuggestion(
        user_id=profile.user_id,
        brand_profile_id=profile.id,
        keywords=formatted_keywords,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    return suggestion