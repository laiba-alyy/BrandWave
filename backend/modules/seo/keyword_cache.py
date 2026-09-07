"""
Category-level keyword cache — ek jaisi brands ka DataForSEO bill batne ke liye.

── Masla ────────────────────────────────────────────────────────────────────
Har keyword run 30 candidates DataForSEO ko bhejta hai. Un mein se zyada tar
GENERIC hain:

    "embroidered lawn suit online", "unstitched 3 piece", "chiffon dupatta price"

Ye keywords Maria.B ke bhi wahi hain aur Asim Jofa ke bhi — dono Pakistani
clothing stores hain. Purane flow mein doosri brand poora bill dobara bharti
thi, jabke jawab bilkul wahi tha jo pehli brand ke waqt khareeda gaya tha.
$1 free credit is tarah 8 run mein khatam ho jata hai.

── Hal ──────────────────────────────────────────────────────────────────────
Candidates ko do dher mein baanto:

  GENERIC   — category + country ki cheez hai, brand ki nahi.
              Cache key = (category, store_country, keyword), TTL 30 din.
              Sirf wo generic keywords khareede jate hain jo cache mein nahi.

  BRANDED   — keyword mein brand ka naam hai ("maria b eid collection").
              Ye kisi doosri brand ke kaam ka nahi, aur is ki demand brand ki
              apni maqbooliyat ke saath badalti hai. Ye HAMESHA fresh validate
              hota hai — na category cache se, na exact-keyword cache se.

Nateeja: category ki pehli brand poora kharcha karti hai, us ke baad har
milti-julti brand sirf apne brand keywords ke paise deti hai.

── Ye faisla generic/branded par KYUN hai, brand-level cache par nahi ───────
Ek brand ki apni cache sirf usi brand ka dobara run sasta karti. Asli bachat
brands ke DARMIYAN hoti hai, aur wo sirf tab mumkin hai jab keyword ka data
brand se azaad ho — yani generic keywords par. Is liye split hi is poore
module ki buniyad hai; TTL aur table us ke baad aate hain.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from models.seo_result import KeywordCache
from modules.scraping.cleaner import CATEGORY_KEYWORDS, PRODUCT_CATEGORIES
from modules.seo.dataforseo import normalize_country, normalize_keyword
from modules.seo.dataforseo_service import (
    EnrichmentResult,
    KeywordMetrics,
    enrich_keywords,
)
from modules.seo.seed_extractor import LOCATION_TERMS, STOPWORDS

logger = logging.getLogger(__name__)

# Search volume mahine mein ek baar update hoti hai aur difficulty us se bhi
# aahista hilti hai. 30 din ek poora refresh cycle hai — is se kam rakhna
# credit jalata hai, zyada rakhna seasonal demand (Eid, sale) miss kar deta hai.
CACHE_TTL_DAYS = 30

# Is se chhote tukre brand alias nahi ban sakte. "b" (Maria.B ka) har doosre
# lafz mein mil jata aur poori generic list ko "brand keyword" bana deta.
MIN_ALIAS_LEN = 4


# ─────────────────────────────────────────────
#  GENERIC VOCABULARY
# ─────────────────────────────────────────────
#
# Brand alias banate waqt ye wo alfaz hain jinhe RADD karna hai. Ek brand ka
# naam "Lawn Story" ho sakta hai — agar "lawn" ko alias maan liya jaye to
# "embroidered lawn suit" branded ban jata aur cache ka poora faida khatam.
# List apne aap scraping ki taxonomy se banti hai, taake ek hi source of truth
# rahe: naya product word wahan add ho to yahan khud aa jata hai.

_GENERIC_WORDS: set[str] = set(STOPWORDS) | set(LOCATION_TERMS) | set(PRODUCT_CATEGORIES)
for _category, _phrases in CATEGORY_KEYWORDS.items():
    _GENERIC_WORDS.update(re.findall(r"[a-z0-9]+", _category))
    for _phrase in _phrases:
        _GENERIC_WORDS.update(re.findall(r"[a-z0-9]+", _phrase.lower()))


# ─────────────────────────────────────────────
#  CATEGORY KEY
# ─────────────────────────────────────────────

# Alag alag stores ek hi cheez ko alag naam dete hain. Cache key stable honi
# chahiye warna do clothing brands ke do alag scope ban jate hain aur cache
# kabhi hit hi nahi hoti.
_CATEGORY_SYNONYMS = {
    "apparel": "clothing", "fashion": "clothing", "clothes": "clothing",
    "garments": "clothing", "womenswear": "clothing", "menswear": "clothing",
    "jewelry": "jewellery", "shoes": "footwear", "perfume": "fragrance",
    "perfumes": "fragrance", "cosmetics": "makeup", "skincare": "beauty",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return _CATEGORY_SYNONYMS.get(slug, slug)


def resolve_category(brand_profile) -> str:
    """
    Is store ki cache category — ASLI catalogue se, na ke scrape ke waqt LLM
    ki andazan business_type se.

    Maria.B ka business_type "multi_category" hai, jo cache key ke tor par
    bekaar hai: har multi-category store us ek hi dher mein gir jata, chahe
    ek kapre beche aur doosra chocolate. 8,255 products mein se 6,198
    "clothing" hain — wahi is store ka asli scope hai.

    Fallback ka silsila: dominant catalogue category -> profile ki
    product_categories -> business_type -> "general".
    """
    counts = Counter()
    for product in getattr(brand_profile, "products", None) or []:
        if not isinstance(product, dict):
            continue
        slug = _slug(product.get("category") or "")
        # "other" ek category nahi, "pata nahi" hai — us par scope banana
        # ghair-mutaliq brands ko ek saath jorh deta.
        if slug and slug != "other":
            counts[slug] += 1
    if counts:
        return counts.most_common(1)[0][0]

    for value in getattr(brand_profile, "product_categories", None) or []:
        slug = _slug(str(value))
        if slug and slug != "other":
            return slug

    return _slug(getattr(brand_profile, "business_type", "") or "") or "general"


# ─────────────────────────────────────────────
#  BRAND DETECTION
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class BrandAliases:
    """
    Brand ko pehchanne ke do tareeqe.

    `collapsed` — naam bina space/punctuation ke ("maria.b" -> "mariab").
        Ye zaroori hai kyunke LLM "maria b", "mariab" aur "maria.b" teenon
        likhta hai, aur domain (mariab.pk) bhi isi shakal mein hota hai.
        Substring match chalta hai, is liye "mariabeidcollection" bhi pakra
        jata hai.

    `tokens` — naam ke wo alag alag lafz jo apne aap mein brand ki pehchan
        hain ("asim", "jofa"). Generic alfaz aur chhote tukre nikal diye jate
        hain, warna har keyword branded ban jata.
    """
    collapsed: frozenset[str]
    tokens: frozenset[str]

    @property
    def known(self) -> bool:
        return bool(self.collapsed or self.tokens)


def _domain_label(url: str) -> str:
    """mariab.pk / www.mariab.pk / https://www.mariab.pk/x -> "mariab"."""
    if not url:
        return ""
    host = urlparse(url if "//" in url else f"//{url}").netloc or url
    host = host.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(".")[0]


def brand_aliases(brand_profile) -> BrandAliases:
    """Brand profile se wo shaklen jinhen keyword mein dhoondna hai."""
    name = (getattr(brand_profile, "business_name", "") or "").lower()
    domain = _domain_label(getattr(brand_profile, "website_url", "") or "")

    collapsed = set()
    for source in (name, domain):
        flat = re.sub(r"[^a-z0-9]", "", source)
        # Chhota flat naam ("hm") kisi bhi lafz ke andar mil jata hai —
        # substring match us par ghalat jawab deta.
        if len(flat) >= MIN_ALIAS_LEN:
            collapsed.add(flat)

    tokens = {
        token for token in re.findall(r"[a-z0-9]+", name)
        if len(token) >= MIN_ALIAS_LEN and token not in _GENERIC_WORDS
    }
    if domain and domain not in _GENERIC_WORDS and len(domain) >= MIN_ALIAS_LEN:
        tokens.add(domain)

    return BrandAliases(frozenset(collapsed), frozenset(tokens))


def is_brand_keyword(keyword: str, aliases: BrandAliases) -> bool:
    """Kya is keyword mein brand ka naam hai?"""
    if not aliases.known:
        return False
    text = normalize_keyword(keyword)
    if any(alias in re.sub(r"[^a-z0-9]", "", text) for alias in aliases.collapsed):
        return True
    return bool(set(re.findall(r"[a-z0-9]+", text)) & aliases.tokens)


@dataclass
class CandidateSplit:
    generic: list[str]
    branded: list[str]


def split_candidates(candidates: list[str], brand_profile) -> CandidateSplit:
    """Candidates ko generic aur brand-specific dher mein baanto."""
    aliases = brand_aliases(brand_profile)
    generic, branded = [], []
    for keyword in candidates:
        (branded if is_brand_keyword(keyword, aliases) else generic).append(keyword)
    return CandidateSplit(generic=generic, branded=branded)


# ─────────────────────────────────────────────
#  CACHE READ / WRITE
# ─────────────────────────────────────────────

def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)


def load_cached(
    db: Session,
    category: str,
    country: str,
    keywords: list[str],
) -> dict[str, KeywordMetrics]:
    """
    Is category+country ke liye jo generic keywords TAAZA cache mein hain.

    30 din se purani rows yahan se nahi aatin — wo aage ja kar dobara
    khareedi jayengi aur usi row par likh di jayengi.
    """
    if not keywords or not category or not country:
        return {}
    try:
        rows = db.query(KeywordCache).filter(
            KeywordCache.category == category,
            KeywordCache.store_country == country,
            KeywordCache.keyword.in_(keywords),
            KeywordCache.cached_at >= _cutoff(),
        ).all()
    except Exception as exc:
        # Cache padhna kabhi keyword generation ko na rokay — miss maan kar
        # aage barho, DataForSEO ya LLM fallback phir bhi chalega.
        db.rollback()
        logger.warning("[keyword-cache] read skipped: %s", exc)
        return {}

    return {
        row.keyword: KeywordMetrics(
            keyword=row.keyword,
            search_volume=row.search_volume,
            cpc=row.cpc,
            keyword_difficulty=row.difficulty,
            search_intent=row.intent,
        )
        for row in rows
    }


def save_cached(
    db: Session,
    category: str,
    country: str,
    metrics: dict[str, KeywordMetrics],
) -> int:
    """
    Naye generic metrics cache mein likho (upsert). Best-effort — cache write
    ki nakami par poora keyword flow nahi girna chahiye.
    """
    if not metrics or not category or not country:
        return 0
    try:
        existing = {
            row.keyword: row
            for row in db.query(KeywordCache).filter(
                KeywordCache.category == category,
                KeywordCache.store_country == country,
                KeywordCache.keyword.in_(list(metrics)),
            ).all()
        }
        now = datetime.now(timezone.utc)
        written = 0
        for keyword, metric in metrics.items():
            if not metric.has_data:
                # Bina data ke row likhna cache ko zeher deta: agla run use
                # "hit" samajh kar keyword ko khaali metrics de deta.
                continue
            row = existing.get(keyword)
            if row is None:
                row = KeywordCache(
                    category=category, store_country=country, keyword=keyword,
                )
                db.add(row)
            row.search_volume = metric.search_volume
            row.difficulty = (
                metric.keyword_difficulty
                if metric.keyword_difficulty is not None
                else metric.competition_index
            )
            row.cpc = metric.cpc
            row.intent = metric.search_intent
            # cached_at HAR write par naya — TTL isi par chalta hai, warna
            # ek baar likha row 30 din baad refresh ho kar bhi "purana" rehta.
            row.cached_at = now
            written += 1
        db.commit()
        return written
    except Exception as exc:
        db.rollback()
        logger.warning("[keyword-cache] write skipped: %s", exc)
        return 0


# ─────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────

def enrich_with_cache(
    db: Session,
    candidates: list[str],
    brand_profile,
    country: str,
    language: str = "en",
    *,
    want_related: bool = False,
) -> EnrichmentResult:
    """
    `enrich_keywords` ka cache-aware version. Shakal bilkul wahi hai — caller
    ko sirf ek EnrichmentResult milta hai — magar beech mein category cache
    lagti hai.

    Chaar qadam:
      1. Candidates ko generic / branded mein baanto.
      2. Generic ke liye category cache dekho (30 din TTL).
      3. Jo bacha (uncached generic + SAARE branded) sirf wo DataForSEO ko
         bhejo — ek hi call mein, kyunke volume per REQUEST charge hoti hai.
      4. Naye generic metrics cache mein likho.

    RAISE ye bhi kabhi nahi karta: enrich_keywords khud nahi karta, aur cache
    ke dono raaste (read/write) best-effort hain.
    """
    normalized = list(dict.fromkeys(
        normalize_keyword(k) for k in candidates if (k or "").strip()
    ))
    if not normalized:
        return EnrichmentResult(available=False, reason="no keywords to enrich")

    try:
        country_code = normalize_country(country or "")
    except Exception:
        country_code = (country or "").strip().upper()

    category = resolve_category(brand_profile)
    split = split_candidates(normalized, brand_profile)

    # ── 2. Cache ────────────────────────────────────────────────────────
    cached = load_cached(db, category, country_code, split.generic)

    # ── 3. Jo cache mein nahi ───────────────────────────────────────────
    # Branded keywords yahan HAMESHA aate hain (cache mein wo hote hi nahi),
    # aur always_fresh unhe exact-keyword cache se bhi bachata hai.
    to_validate = [k for k in normalized if k not in cached]

    if to_validate:
        result = enrich_keywords(
            db, to_validate, country, language,
            want_related=want_related,
            always_fresh=set(split.branded),
        )
    else:
        # Ek bhi API call ki zaroorat nahi — poora batch cache se.
        result = EnrichmentResult(available=True, reason="category cache")

    # ── 4. Naye generic metrics cache mein ──────────────────────────────
    generic = set(split.generic)
    fresh_generic = {
        keyword: metric for keyword, metric in result.metrics.items()
        if keyword in generic and metric.has_data
    }
    written = save_cached(db, category, country_code, fresh_generic)

    metrics = dict(result.metrics)
    metrics.update(cached)

    stats = {
        "category": category,
        "country": country_code,
        "generic": len(split.generic),
        "branded": len(split.branded),
        "from_cache": len(cached),
        "validated_live": len(to_validate),
        "cache_writes": written,
        "ttl_days": CACHE_TTL_DAYS,
    }
    logger.info(
        "[keyword-cache] %s/%s — %d generic (%d cached, %d fresh), "
        "%d brand keywords, %d rows cached, cost $%.4f",
        category, country_code, len(split.generic), len(cached),
        len(split.generic) - len(cached), len(split.branded), written, result.cost,
    )

    # Cache se data mila to enrichment "available" hai chahe live call nakaam
    # ho gayi ho — user ko aadhe keywords par asli volume phir bhi milti hai.
    available = result.available or bool(cached)
    reason = result.reason
    if cached and not result.available:
        reason = f"partial: live call failed ({result.reason}), served category cache"

    return EnrichmentResult(
        metrics=metrics,
        available=available,
        reason=reason,
        related=result.related,
        cost=result.cost,
        cache_stats=stats,
    )
