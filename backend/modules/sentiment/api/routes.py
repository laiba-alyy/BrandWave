from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from database.connection import get_db
from models.brand_profile import BrandProfile
from modules.sentiment.database.models import Brand, SentimentAnalysis
from modules.sentiment.api.schemas import BrandResponse, AnalysisResponse
from modules.sentiment.services.review_platforms import ReviewPlatformService

# ── NEW sentiment stack ───────────────────────────────────────────────────────
# Sentiment ka faisla ab XLM-RoBERTa model karta hai (88% test accuracy),
# aur insights/emotions Groq nikalta hai.
#
# PURANA (ab use nahi hota, files delete nahi ki gayin):
#   services/sentiment_service.py  -> 3 jumlon par trained fake SVM tha; wo
#                                     har cheez ko "negative" keh deta tha.
#   services/insight_extraction.py -> substring keyword matching thi; 'no'
#                                     keyword "not/now/know" se match ho kar
#                                     tareef ko complaint bana deta tha.
from modules.sentiment.services.model_loader import get_predictor
from modules.sentiment.services import groq_insights

# YouTube ek SUPPLEMENTARY source hai — Trustpilot ke saath, uski jagah nahi.
# Iske comments bilkul usi shape mein aate hain, to pipeline waisi hi rehti hai.
from modules.sentiment.services import youtube_service
from modules.auth import get_current_user
from modules.scraping.scraper import normalize_store_url

import re
import uuid
import asyncio
import logging
import os
from datetime import datetime, timedelta
from collections import Counter
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

router = APIRouter()

review_service = ReviewPlatformService()


# ============================================================
# KEYWORD EXTRACTION
# Purana counter theek kaam karta tha, sirf stopword list choti thi — is liye
# "you", "makes", "this", "was" jaise filler words top keywords ban jate the.
# ============================================================
STOP_WORDS = {
    # articles / conjunctions / prepositions
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "but", "not", "any", "all", "our", "out", "own", "off", "per", "via",
    "into", "onto", "than", "then", "too", "very", "just", "only", "also",
    "some", "such", "each", "both", "more", "most", "other", "over", "under",
    "about", "after", "before", "again", "once", "here", "there", "when",
    "where", "why", "how", "who", "whom", "which", "while", "during",
    # pronouns
    "you", "your", "yours", "they", "them", "their", "theirs", "she", "her",
    "hers", "him", "his", "its", "itself", "himself", "herself", "themselves",
    "myself", "yourself", "ourselves", "one", "ones", "everyone", "someone",
    "anyone", "everything", "something", "anything", "nothing",
    # verbs / auxiliaries
    "was", "were", "been", "being", "are", "have", "has", "had", "having",
    "can", "will", "would", "could", "should", "may", "might", "must", "shall",
    "did", "does", "doing", "done", "get", "got", "getting", "make", "makes",
    "made", "making", "take", "takes", "took", "taken", "give", "gives",
    "gave", "given", "want", "wants", "went", "goes", "going", "come", "came",
    "say", "says", "said", "see", "saw", "seen", "know", "knew", "known",
    "use", "used", "using", "put", "let", "lot", "way", "ways",
    # filler / generic
    "really", "actually", "basically", "definitely", "probably", "maybe",
    "thing", "things", "stuff", "much", "many", "even", "still", "yet",
    "ever", "never", "always", "sometimes", "usually", "now", "today",
    "back", "well", "good", "okay", "yes", "ordered", "order",
    "because", "since", "though", "although", "however", "therefore",
    "every", "another", "around", "already", "enough", "little", "bit",
    "few", "far", "own", "same", "next", "last", "first", "second",
    # Roman Urdu filler — model bilingual hai, to reviews mein Roman Urdu
    # aata hai aur "aur"/"hai"/"kiya" top keywords ban jate the.
    "aur", "hai", "hain", "haan", "nahi", "kiya", "kar", "karo", "karna",
    "kia", "kea", "mein", "main", "may", "kay", "kai", "koi", "kuch",
    "phir", "bhi", "bohat", "bahut", "tha", "thi", "the", "raha", "rahi",
    "jab", "tab", "yeh", "wo", "woh", "iss", "uss", "apna", "apni", "sab",
    "abhi", "agar", "magar", "lekin", "liye", "wala", "wali", "hoga",
}


def extract_keywords(
    texts: list[str], top_n: int = 20, brand_name: str | None = None
) -> list[dict]:
    """
    Top keywords by frequency, filler words nikaal kar.

    brand_name diya ho to brand ke apne naam ke words bhi drop hote hain —
    warna har analysis ka #1 keyword brand ka naam hi hota hai, jo koi
    information nahi deta ("maria(26)" Maria.B ke report par).
    """
    ignore = set(STOP_WORDS)
    if brand_name:
        ignore.update(re.findall(r"\b[a-z]{3,}\b", brand_name.lower()))

    words: list[str] = []
    for text in texts:
        words.extend(re.findall(r"\b[a-z]{3,}\b", (text or "").lower()))

    counter = Counter(words)
    return [
        {"keyword": word, "frequency": count}
        for word, count in counter.most_common(top_n * 5)
        if word not in ignore and count > 1
    ][:top_n]


def summarise_sentiment(predictions: list[dict], total_reviews: int) -> dict:
    """
    Model ki predictions se counts + percentages banao.

    Ye Overview tab aur sentiment chart dono ko feed karta hai, aur shape
    bilkul wahi hai jo frontend ka `SentimentData` type expect karta hai.
    """
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for p in predictions:
        label = p.get("prediction")
        if label in counts:
            counts[label] += 1
        else:
            counts["neutral"] += 1

    total = total_reviews or 1  # ZeroDivisionError se bachao
    return {
        "total_posts":      total_reviews,
        "positive":         counts["positive"],
        "negative":         counts["negative"],
        "neutral":          counts["neutral"],
        "positive_percent": round(counts["positive"] / total * 100, 1),
        "negative_percent": round(counts["negative"] / total * 100, 1),
        "neutral_percent":  round(counts["neutral"]  / total * 100, 1),
    }


def _balanced_sample(reviews: list[dict], cap: int) -> list[str]:
    """
    Har platform se barabar hissa lo, taake ek bara source baqi ko na daba de.

    Masla jo is ne hal kiya: Gymshark par sources thay
    trustpilot=20, youtube=7, youtube_reviews=765. Seedha `texts[:60]` ya
    barabar-faasle ka namoona lene par Groq ko tqreeban sirf YouTube milta
    tha — jab ke Trustpilot ke reviews tasdeeq-shuda khareedari hain aur
    per-item sab se ziyada mustanad.

    Tareeqa: cap ko platforms mein barabar baanto; jis ke paas apne hisse se
    kam hain us ka sab kuch le lo aur bacha hua kota baqi mein dobara baant
    do. Har platform ke andar barabar faasle se chunte hain, taake ek hi
    video/safhe ka jhund na aa jaye.
    """
    if not reviews:
        return []

    # cap <= 0 ka matlab "koi hadd nahi" — SAARI reviews insights mein jayen.
    # (groq_insights.MAX_INSIGHT_REVIEWS ka default yehi 0 hai.) Ye guard na
    # hone par `remaining = 0` ke sath neeche wala loop chalta hi nahi tha aur
    # ye function KHALI list deta tha — natija: 534 comments fetch hue, model
    # ne sab score kiye, magar insights waale LLM ko ek bhi review nahi gayi
    # (0 pain points, $0.00 kharch).
    if cap is None or cap <= 0:
        return [
            t for t in ((r.get("content") or "").strip() for r in reviews) if t
        ]

    buckets: dict[str, list[str]] = {}
    for r in reviews:
        text = (r.get("content") or "").strip()
        if len(text) < 30:          # "nice", emoji — theme ke liye bekaar
            continue
        buckets.setdefault(r.get("platform") or "unknown", []).append(text)

    if not buckets:
        return [(r.get("content") or "").strip() for r in reviews][:cap]

    remaining = cap
    pending = dict(buckets)
    chosen: list[str] = []

    while pending and remaining > 0:
        share = max(1, remaining // len(pending))
        for platform in list(pending):
            pool = pending[platform]
            take = min(share, len(pool), remaining)
            if take <= 0:
                continue
            step = len(pool) / take
            chosen.extend(pool[int(i * step)] for i in range(take))
            remaining -= take
            if take >= len(pool):
                del pending[platform]       # is source ka sab kuch le liya
            else:
                pending[platform] = [p for p in pool if p not in chosen]
            if remaining <= 0:
                break
        # Koi source bacha hi nahi jo aur de sake
        if not any(pending.values()):
            break

    return chosen[:cap]


def normalize_for_match(value: str) -> str:
    """Lowercase + remove all whitespace for case/space-insensitive matching."""
    return ''.join(value.strip().lower().split())


def fetch_brand_profiles_with_retry(db: Session, user_id: str | None = None):
    """
    Retry once for transient OperationalError (e.g., dropped SSL connection).

    user_id diya ho to sirf usi account ke brands aate hain. Pehle ye
    unconditionally .all() karta tha — yani har user ko HAR user ke brands
    dikhte the (cross-account leak, sirf stale-data ka masla nahi).
    """
    for attempt in range(2):
        try:
            q = db.query(BrandProfile)
            if user_id:
                q = q.filter(BrandProfile.user_id == user_id)
            return q.all()
        except OperationalError as e:
            db.rollback()
            if attempt == 0:
                logger.warning(f"Transient DB error while loading brands, retrying once: {e}")
                continue
            raise


def clean_brand_name(raw_name: str, website_url: str = None) -> str:
    value = (raw_name or '').strip()
    if value.startswith('http://') or value.startswith('https://'):
        domain = urlparse(value).netloc
        value  = domain or value
    elif not value and website_url:
        value = urlparse(website_url).netloc or website_url
    value = value.replace('www.', '').split('.')[0].replace('-', ' ').strip()
    return value.title() if value else raw_name


# ============================================================
# 1. GET ALL BRANDS
# ============================================================
@router.get("/brands")
async def get_brands(caller: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return onboarded brands (populated by Module 2), scoped to the account."""
    try:
        brands = fetch_brand_profiles_with_retry(db, caller)
        return [
            {
                'brand_id':          str(b.id),
                'brand_name':        b.business_name or b.website_url,
                'website_url':       b.website_url,
                'product_categories': b.product_categories,
                'created_at':        b.created_at,
            }
            for b in brands
        ]
    except Exception as e:
        logger.error(f"Error fetching brands: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 2. ANALYZE BRAND  (main endpoint)
# ============================================================
# ============================================================
#  ANALYSIS CACHE
# ============================================================
#
# Har click par poori pipeline chalti thi: Trustpilot scrape + YouTube
# (~143 quota units) + sentiment model + Groq insights. Ek hi brand par
# paanch dafa click ka matlab tha paanch guna sab kuch — aur demo ke doran
# YouTube ka rozana budget chand clicks mein khatam.
#
# Ab natija DOBARA istemal hota hai:
#   * Cache BRAND ke sath bandha hai (brand_id). Naye brand ke liye hamesha
#     poori pipeline chalti hai — kisi doosre brand ka data kabhi nahi aata.
#   * Ek HAFTE tak wahi natija milta hai. Us se purana ho to dobara chalti
#     hai, kyunke itne arse mein nayi reviews aa jati hain.
#   * KHALI natije cache nahi hote (neeche dekho) — warna Trustpilot ka ek
#     timeout poore hafte ke liye chipak jata.
#   * `refresh=true` cache ko nazarandaz kar deta hai (UI ka Refresh button).
ANALYSIS_CACHE_DAYS = int(os.getenv("SENTIMENT_CACHE_DAYS", "7"))


def _cached_analysis(
    db: Session, brand_uuid, max_age_days: int = None, require_deep: bool = False
):
    """
    Is brand ka sab se naya analysis, agar wo abhi taza hai.

    DEPTH ka lihaaz rakhna zaroori hai. Ab do tarah ki analysis hoti hai:
      * shallow — Trustpilot + brand ka apna YouTube channel (~25 items, tez)
      * deep    — oopar wala + doosron ke review videos (~800 items, ~4 min)

    Agar user ne pehle shallow chalayi aur phir "include YouTube reviewers"
    tick kiya, to usay shallow natija wapas dena SAAF GHALAT hoga — usne
    zyada gehri analysis maangi hai. Is liye deep request sirf deep cache se
    poori hoti hai.

    Ulta chalta hai: shallow request deep natije se bhi mutmain ho jati hai,
    kyunke deep mein shallow ka saara data pehle se shamil hota hai.

    Khali (0 review wale) natije jaan boojh kar nazarandaz — wo aksar kisi
    aarzi nakami ka nateeja hote hain, aur unhein cache karne ka matlab hai
    ke brand poore hafte ke liye "no reviews" par atak jaye.
    """
    days = ANALYSIS_CACHE_DAYS if max_age_days is None else max_age_days
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = (
        db.query(SentimentAnalysis)
        .filter(
            SentimentAnalysis.brand_id == brand_uuid,
            SentimentAnalysis.analysis_date >= cutoff,
            SentimentAnalysis.review_count > 0,
        )
        .order_by(SentimentAnalysis.analysis_date.desc())
    )

    # AAM RAASTA: sirf sab se naya row chahiye — EK row.
    #
    # Pehle yahan hamesha .limit(20).all() tha, chahe depth ki shart ho ya
    # na ho. Har row apne saath poora `analysis_data` JSON blob laata hai
    # (insights + keywords + emotions), to /latest par 20 blobs uthana parte
    # thay. Neon us-east-1 par hai, is liye ye 2-5 second le raha tha —
    # halanke sirf ek row darkaar tha.
    if not require_deep:
        return query.first()

    # DEEP request: sirf wo row chalega jo deep tha. `deep` flag JSON ke
    # andar hai aur JSON filtering dialect par munhasir hai, is liye chand
    # rows uthaa kar Python mein chhaanate hain — ye kam chalne wala raasta
    # hai (sirf jab user ne checkbox tick kiya ho).
    for row in query.limit(10).all():
        if (row.analysis_data or {}).get("deep") is True:
            return row
    return None


def _analysis_response(analysis, display_name: str, cached: bool) -> dict:
    """
    Stored row -> wahi response shape jo live run deta hai.

    Frontend ko farq mehsoos nahi hona chahiye; sirf `cached` aur
    `analysed_at` extra hain taake UI sach dikha sake.
    """
    data = analysis.analysis_data or {}
    return {
        "status":             "success",
        "brand_name":         data.get("brand_name") or display_name,
        "brand_id":           str(analysis.brand_id),
        "total_reviews":      analysis.review_count or 0,
        "platforms_searched": data.get("platforms") or {},
        "sentiment":          data.get("sentiment_summary") or {},
        "dominant_emotion":   analysis.dominant_emotion,
        "analysis_id":        str(analysis.analysis_id),
        "analysis_data":      data,
        "cached":             cached,
        "analysed_at":        analysis.analysis_date.isoformat() if analysis.analysis_date else None,
        # UI batata hai ke natija kis gehrai se bana — warna user ko samajh
        # nahi aata ke ek run ne 24 items dekhe aur doosre ne 828.
        "deep":               bool(data.get("deep")),
    }


@router.post("/analyze-from-dropdown")
async def analyze_from_dropdown(
    brand_name: str | None = None,
    brand_profile_id: int | None = None,
    refresh: bool = False,
    # Doosron ke YouTube review videos — JAAN BOOJH KAR opt-in.
    # Ye source ~121 quota units aur ~3 extra minute leta hai; har analysis
    # par default chalana rozana budget (10,000 units) chand clicks mein kha
    # jata tha. Ab wahi user pay karta hai jo gehri analysis maangta hai.
    include_youtube_reviews: bool = False,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Two ways to call:
      1. brand_profile_id=N  → direct PK lookup (preferred, used by the
         switcher-driven frontend — same as SEO/ads/improvement modules).
      2. brand_name="Asim Jofa"  → fuzzy name match (legacy fallback for
         any caller that still passes a typed name).

    Both paths converge at the same BrandProfile row and run the identical
    Trustpilot + model + Groq pipeline from there.
    """
    try:
        # ── STEP 1: resolve the BrandProfile row ─────────────────────────────
        # Path A: direct PK lookup (preferred — zero ambiguity, no normalization)
        if brand_profile_id is not None:
            brand = db.query(BrandProfile).filter(
                BrandProfile.id == brand_profile_id
            ).first()
            if brand and brand.user_id != caller:
                brand = None  # cross-account guard
            if not brand:
                return {
                    "status":  "error",
                    "message": f"Brand profile (id={brand_profile_id}) not found. "
                               f"Please onboard it via the Web Scraping module first.",
                }
            raw_input = brand.business_name or brand.website_url or ''
            logger.info(f"Analyzing brand by profile_id={brand_profile_id} → '{raw_input}'")
        else:
            # Path B: fuzzy name match (legacy)
            raw_input = (brand_name or '').strip()
            normalized_in = normalize_for_match(raw_input)
            logger.info(f"Analyzing brand input: '{raw_input}' (normalized: '{normalized_in}')")

            if not normalized_in:
                return {"status": "error", "message": "Brand name cannot be empty."}

            all_brands = fetch_brand_profiles_with_retry(db, caller)
            brand = next(
                (b for b in all_brands
                 if normalize_for_match(b.business_name or '') == normalized_in
                 or normalize_for_match(b.website_url     or '') == normalized_in),
                None
            )

            if not brand:
                return {
                    "status":  "error",
                    "message": f"Brand '{raw_input}' not found in the database. "
                               f"Please onboard it via the Web Scraping module first.",
                }

        if not (brand.website_url or '').strip():
            return {
                "status": "error",
                "message": (
                    f"Brand '{raw_input}' is missing website URL in database. "
                    f"Please refresh this brand in the Web Scraping module first."
                ),
            }

        display_name = clean_brand_name(brand.business_name or raw_input, brand.website_url)
        logger.info(f"Matched brand: id={brand.id}  display='{display_name}'  url={brand.website_url}")

        # ── STEP 2: upsert into sentiment Brand table ─────────────────────────
        # Key website_url par hai, display_name par NAHI.
        #
        # Pehle `Brand.brand_name == display_name` par match hota tha, jo ek
        # GLOBAL namespace tha — brands table mein user_id hai hi nahi. Do
        # accounts ek jaise naam ka store onboard karte (do "Asim Jofa"), to
        # doosre account ki analyses pehle account ke Brand row se ju jatin,
        # aur get_results ki ownership check — jo website_url se chalti hai —
        # ghalat user par resolve hoti. URL har store ke liye unique hai, is
        # liye wahi sahi key hai.
        # URL bhi NORMALIZE kar ke — warna wahi store "www." ke sath aur
        # baghair do alag rows bana leta, bilkul jaisa brand_profiles mein
        # hota tha.
        canonical_url = normalize_store_url(brand.website_url)
        sentiment_brand = next(
            (
                b
                for b in db.query(Brand).all()
                if normalize_store_url(b.website_url or "") == canonical_url
            ),
            None,
        )
        if not sentiment_brand:
            sentiment_brand = Brand(
                brand_name=display_name,
                website_url=canonical_url,
                product_categories=brand.product_categories or [],
            )
            db.add(sentiment_brand)
            db.commit()
            db.refresh(sentiment_brand)
        elif sentiment_brand.brand_name != display_name:
            # Brand ka naam scraping module mein badal gaya — sync kar do,
            # warna reports purane naam par chalti rehti hain.
            sentiment_brand.brand_name = display_name
            db.commit()

        # ── STEP 2b: CACHE — is brand ka taza natija mojood hai? ──────────────
        # Brand resolve hone ke BAAD check karte hain, taake cache hamesha
        # sahi brand ka ho. `refresh=true` par bilkul skip.
        if not refresh:
            hit = _cached_analysis(
                db, sentiment_brand.brand_id, require_deep=include_youtube_reviews
            )
            if hit:
                age_h = (datetime.utcnow() - hit.analysis_date).total_seconds() / 3600
                logger.info(
                    "Cache HIT for %s (analysis %s, %.1fh old) — skipping "
                    "Trustpilot + YouTube + Groq entirely",
                    display_name, hit.analysis_id, age_h,
                )
                return _analysis_response(hit, display_name, cached=True)
            logger.info("Cache MISS for %s — running full pipeline", display_name)

        # ── STEP 2c: TRANSACTION BAND KARO fetch shuru karne se pehle ─────────
        #
        # Neon par `idle_in_transaction_session_timeout = 5min`. Upar wali
        # queries (brand lookup + cache check) ek transaction khol deti hain,
        # aur agar wo khuli reh jaye to Trustpilot + YouTube + sentiment model
        # + Groq — sab is ke andar chalte hain. Gymshark par ye 5 minute se
        # oopar chala gaya aur Neon ne connection hi maar diya:
        #
        #   psycopg.errors.IdleInTransactionSessionTimeout
        #   terminating connection due to idle-in-transaction timeout
        #
        # Sitam ye ke saara kaam MUKAMMAL ho chuka hota tha (Groq ne insights
        # bhi de diye) aur sirf aakhri INSERT girta tha — yani 3 minute ka
        # kaam aur natija 500.
        #
        # commit() transaction band kar deta hai; connection pool mein bekaar
        # para rehta hai jo bilkul theek hai. Aakhri write par SQLAlchemy naya
        # transaction khol lega, aur pool_pre_ping=True (connection.py) us se
        # pehle connection ki sehat check kar leta hai.
        db.commit()

        # ── STEP 3a: fetch real Trustpilot reviews ────────────────────────────
        logger.info(f"Fetching Trustpilot reviews for: {brand.website_url}")
        trustpilot_reviews = await review_service.fetch_trustpilot_reviews(brand.website_url)
        logger.info(f"Trustpilot: {len(trustpilot_reviews)} reviews")

        # ── STEP 3b: fetch YouTube comments (SUPPLEMENTARY) ───────────────────
        # YouTube optional hai: channel na ho, comments band hon, quota khatam
        # ho, ya API error aaye — kuch bhi ho, khali list milti hai aur
        # Trustpilot ka analysis normally chalta rehta hai.
        #
        # youtube_url scraping module ne brand_profiles.social_links JSON mein
        # rakha hota hai (extractor.py :: extract_social_links).
        social_links = brand.social_links if isinstance(brand.social_links, dict) else {}
        youtube_url = (social_links.get("youtube") or "").strip() or None

        youtube_comments = []
        if youtube_url:
            logger.info(f"Fetching YouTube comments for: {youtube_url}")
            # fetch_youtube_comments sync hai (requests). Ise thread mein chalao
            # taake FastAPI ka async event loop block na ho — wahi wajah jis se
            # Trustpilot scraper bhi threadpool mein chalta hai.
            youtube_comments = await asyncio.to_thread(
                youtube_service.fetch_youtube_comments, youtube_url
            )
            logger.info(f"YouTube: {len(youtube_comments)} comments")
        else:
            logger.info("No YouTube URL on this brand — YouTube source skipped.")

        # ── STEP 3c: third-party review videos (SUPPLEMENTARY) ────────────────
        # Brand ke apne channel par comments aksar fans ki hoti hain. Doosron
        # ke banaye "<brand> review" videos par khareedaron ki be-laag raaye
        # milti hai — sizing, qeemat, fabric, delivery.
        #
        # QUOTA: search.list 100 units ka hai (baqi endpoints 1). Ye source
        # ~120 units leta hai, yani rozana 10,000 ke budget mein ~80 analyses.
        # Quota khatam ho jaye to service khali list deti hai aur baqi
        # analysis normally chalti rehti hai.
        review_video_comments = []
        if include_youtube_reviews:
            review_video_comments = await asyncio.to_thread(
                youtube_service.fetch_review_video_comments, display_name, youtube_url
            )
            logger.info(
                "YouTube review videos: %d comments", len(review_video_comments)
            )
        else:
            logger.info(
                "YouTube reviewer videos skipped (not requested) — "
                "saves ~121 quota units and ~3 minutes"
            )

        # ── STEP 3d: combine all sources ──────────────────────────────────────
        # Teenon sources ka shape ek jaisa hai (content/source/platform/is_real),
        # is liye aage ki poori pipeline bina kisi tabdeeli ke chalti hai.
        combined_reviews = (
            trustpilot_reviews + youtube_comments + review_video_comments
        )

        # Source counts — dashboard ka breakdown inhi se banta hai.
        platform_counts = {
            "trustpilot":      len(trustpilot_reviews),
            "youtube":         len(youtube_comments),
        }
        # Key sirf tab daalo jab source waqai chala ho — warna dashboard par
        # "youtube_reviews: 0" nazar aata hai jaise kuch mila hi na ho,
        # halanke poocha hi nahi gaya tha.
        if include_youtube_reviews:
            platform_counts["youtube_reviews"] = len(review_video_comments)

        # NOTE: ye check pehle SIRF Trustpilot par tha aur STEP 3 ke foran baad
        # return kar deta tha — yani jis brand ke Trustpilot reviews na hon uske
        # YouTube comments kabhi fetch hi nahi hote the. Ab dono ke baad chalta hai.
        if not combined_reviews:
            logger.warning(f"No reviews or comments found for {display_name}")
            return {
                "status":        "no_reviews",
                "brand_name":    display_name,
                "total_reviews": 0,
                "platforms_searched": platform_counts,
                "message": (
                    f"No reviews found for {display_name} on Trustpilot"
                    + (" or YouTube." if youtube_url else ".")
                ),
            }

        # platform_counts par loop — naam gina kar NAHI. Pehle yahan sirf
        # trustpilot aur youtube hardcoded thay, to teesra source add hone
        # par log jhoot bolne laga ("58 items (trustpilot=20, youtube=7)"
        # jab ke 31 aur bhi thay). Aage koi source aaye to khud aa jayega.
        logger.info(
            "Fetched %d total items (%s)",
            len(combined_reviews),
            ", ".join(f"{k}={v}" for k, v in sorted(platform_counts.items())),
        )

        # ── STEP 4: sentiment prediction (XLM-RoBERTa, EK batch call) ─────────
        # Pehle har review ke liye alag call hoti thi. Ab saare texts ek saath
        # tokenize aur ek forward pass mein jate hain (~5x tez).
        review_texts = [r.get('content', '') for r in combined_reviews]

        predictor = get_predictor()
        if predictor is None:
            logger.error("Sentiment model unavailable — cannot analyze")
            raise HTTPException(
                status_code=503,
                detail=(
                    "Sentiment model is not loaded on the server. "
                    "Check SENTIMENT_MODEL_DIR and that the model files exist."
                ),
            )

        # predict_batch XLM-RoBERTa ka CPU forward pass hai — 38 reviews par
        # kai second. Ye route async hai, to wo poore event loop ko rok deta
        # tha (measured: khali /health 0.32s se 17.68s). Thread mein bhejo,
        # bilkul waise hi jaise YouTube fetch pehle se jata hai.
        predictions = await asyncio.to_thread(predictor.predict_batch, review_texts)

        # Har review par uska apna sentiment rakh do (audit/debug ke liye)
        for review, pred in zip(combined_reviews, predictions):
            review['sentiment']  = pred['prediction']
            review['confidence'] = pred['confidence']

        # ── STEP 5: summary stats (model = source of truth) ───────────────────
        sentiment_summary = summarise_sentiment(predictions, len(combined_reviews))
        logger.info(f"Sentiment summary: {sentiment_summary}")

        # ── STEP 6: insights + emotions (Groq) ────────────────────────────────
        # Groq SIRF pain points / desires / loved / emotions deta hai.
        # Sentiment ka faisla wo NAHI karta — wo upar model kar chuka hai.
        # Groq calls (sync requests.post, kai batches) — inhein bhi thread mein.
        # Groq ko HAR source se barabar hissa bhejo, mehz pehle N nahi.
        #
        # Gymshark par 20 Trustpilot ke muqable 765 YouTube comments aaye. Seedha
        # namoona lene par Trustpilot ke sirf 2 items pohanchte the — halanke
        # wohi sab se qeemti hain (tasdeeq-shuda khareedari, poora likha hua
        # review). Ab har platform se barabar liya jata hai; jis source ke paas
        # kam hain us ka poora hissa jata hai aur bacha hua kota baqi sources
        # mein baant diya jata hai.
        insight_texts = _balanced_sample(combined_reviews, groq_insights.MAX_INSIGHT_REVIEWS)
        insights = await asyncio.to_thread(groq_insights.extract_insights, insight_texts)
        pain_points = insights['pain_points']
        desires     = insights['desires']
        loved       = insights['loved']
        emotions    = insights['emotions']

        keywords = extract_keywords(review_texts, brand_name=display_name)

        # ── STEP 7: save to DB ────────────────────────────────────────────────
        # dominant_emotion: pehle `positive if positive_percent > 50 else negative`
        # tha — is se 'neutral' KABHI nahi aa sakta tha, chahe zyadatar reviews
        # neutral hi kyun na hon. Ab teeno mein se asli majority chunta hai.
        dominant_emotion = max(
            ('positive', 'negative', 'neutral'),
            key=lambda label: sentiment_summary[label],
        )

        # analysis_data ka shape frontend ke `AnalysisData` type se milta hai.
        # Purani keys (sentiment_summary / pain_points / desires / keywords /
        # platforms) waise hi hain taake dashboard na toote — sirf 'loved' aur
        # 'emotions' NAYI add hui hain.
        analysis_data = {
            'brand_name':        display_name,
            'sentiment_summary': sentiment_summary,
            'pain_points':       pain_points or [],
            'desires':           desires     or [],
            'loved':             loved       or [],
            'emotions':          emotions    or {},
            'keywords':          keywords    or [],
            # Ab dono sources ka breakdown: {'trustpilot': N, 'youtube': M}
            'platforms':         platform_counts,
            # Cache ko yaad rehna chahiye ke ye natija kis gehrai se bana.
            'deep':              include_youtube_reviews,
        }

        analysis = SentimentAnalysis(
            analysis_id=uuid.uuid4(),
            brand_id=sentiment_brand.brand_id,
            review_count=len(combined_reviews),                         # ← renamed field
            overall_sentiment_score=sentiment_summary['positive_percent'],
            dominant_emotion=dominant_emotion,
            analysis_data=analysis_data,
        )
        db.add(analysis)
        db.commit()
        logger.info(f"Saved analysis: {analysis.analysis_id}")

        # ── STEP 8: response ──────────────────────────────────────────────────
        return {
            "status":           "success",
            "brand_name":       display_name,
            "brand_id":         str(sentiment_brand.brand_id),
            "total_reviews":    len(combined_reviews),
            "platforms_searched": platform_counts,
            "sentiment":        sentiment_summary,
            "dominant_emotion": dominant_emotion,
            "analysis_id":      str(analysis.analysis_id),
            "analysis_data":    analysis_data,
            # UI in dono se "Last analysed ..." dikhata hai. Live run par
            # cached=False — taake judge poochhe to jawab saaf ho.
            "cached":           False,
            "analysed_at":      analysis.analysis_date.isoformat() if analysis.analysis_date else None,
            "deep":             include_youtube_reviews,
        }

    except HTTPException:
        # Jaan boojh kar bheji gayi HTTP errors (jaise 503 model-not-loaded)
        # ko waise hi jaane do — warna neeche wala handler unhein 500 bana deta.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in analyze_from_dropdown: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 3. GET RESULTS BY ID
# ============================================================
@router.get("/results/{analysis_id}")
async def get_results(
    analysis_id: str,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ek analysis report id se wapas do — sirf usi account ko jiska brand hai.

    Sentiment ki `brands` table mein user_id nahi hota, is liye ownership
    website_url ke zariye brand_profiles tak trace hoti hai. Warna analysis_id
    janne wala koi bhi kisi aur brand ki poori report parh sakta tha.
    """
    # analysis_id ek UUID column hai. Ghair-UUID string seedha Postgres tak
    # pahunchti thi, jahan se psycopg ka InvalidTextRepresentation aata tha —
    # aur wo POORI SQL query (har column ka naam, table, bound parameters)
    # ke sath 500 response ban kar browser tak chala jata tha.
    # Yahan validate kar lo: ghalat shape ka id sirf 404 hai.
    try:
        uuid.UUID(str(analysis_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        analysis = db.query(SentimentAnalysis).filter(
            SentimentAnalysis.analysis_id == analysis_id
        ).first()
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")

        sentiment_brand = db.query(Brand).filter(
            Brand.brand_id == analysis.brand_id
        ).first()
        owned = None
        if sentiment_brand and (sentiment_brand.website_url or '').strip():
            # URL match NORMALIZE kar ke — warna purane rows jin mein "www." ya
            # trailing slash hai, un ki apni hi reports 403 de deti hain.
            target = normalize_store_url(sentiment_brand.website_url)
            owned = next(
                (
                    p
                    for p in db.query(BrandProfile).filter(
                        BrandProfile.user_id == caller
                    ).all()
                    if normalize_store_url(p.website_url or "") == target
                ),
                None,
            )
        if not owned:
            raise HTTPException(
                status_code=403,
                detail="You can only view analyses for your own brands.",
            )

        return {
            "analysis_id":             str(analysis.analysis_id),
            "brand_id":                str(analysis.brand_id),
            "overall_sentiment_score": analysis.overall_sentiment_score,
            "dominant_emotion":        analysis.dominant_emotion,
            "total_reviews":           analysis.review_count,
            "analysis_data":           analysis.analysis_data,
        }
    except HTTPException:
        # 404/403 ko 500 mein lapetna band — warna caller ko asli wajah nahi milti.
        raise
    except Exception as e:
        logger.error(f"Error fetching results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 4. HEALTH CHECK
# ============================================================
@router.get("/latest")
async def latest_analysis(
    brand_profile_id: int,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Is brand ka aakhri mehfooz analysis — koi fetch nahi, koi quota nahi.

    Kis liye: sentiment page par natija dikh raha hota tha, magar user kisi
    aur page par jaa kar wapas aata to screen khali mil ti thi aur usay
    dobara "Analyse Reviews" dabana parta tha (yani poora kharcha dobara).
    Ab page load par ye endpoint pooch leta hai ke pehle se kuch mojood hai
    ya nahi.

    Ownership wahi tareeqe se check hoti hai jo analyze route mein hai:
    brand_profiles se caller ka brand nikaalte hain, phir usi URL par
    sentiment Brand row match karte hain.
    """
    try:
        brand = (
            db.query(BrandProfile)
            .filter(BrandProfile.id == brand_profile_id, BrandProfile.user_id == caller)
            .first()
        )
        if not brand:
            raise HTTPException(404, "Brand not found for this account.")

        display_name = clean_brand_name(brand.business_name or "", brand.website_url)
        canonical_url = normalize_store_url(brand.website_url)
        sentiment_brand = next(
            (
                b
                for b in db.query(Brand).all()
                if normalize_store_url(b.website_url or "") == canonical_url
            ),
            None,
        )
        if not sentiment_brand:
            return {"status": "none"}

        hit = _cached_analysis(db, sentiment_brand.brand_id)
        if not hit:
            return {"status": "none"}
        return _analysis_response(hit, display_name, cached=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("latest_analysis failed: %s", e, exc_info=True)
        # Ye sirf ek suhoolat hai — nakami par page khali khul jaye, girna nahi chahiye.
        return {"status": "none"}


@router.get("/report/{analysis_id}/pdf")
def download_report_pdf(
    analysis_id: str,
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sentiment report ko ASLI PDF file ke taur par download karo.

    Pehle frontend ek popup kholta tha aur `window.print()` chalata tha — wo
    download nahi, print dialog tha: user ko khud "Save as PDF" chunna parta,
    popup blocker rok deta, aur har browser ka natija alag hota.

    Ab PDF server par banti hai (reportlab, wahi jo SEO module use karta hai)
    aur `Content-Disposition: attachment` ke saath jati hai, to browser bina
    poochhe file save kar deta hai.

    OWNERSHIP: analysis -> sentiment Brand -> website_url -> caller ka
    brand_profile. Yehi zanjeer get_results() bhi istemal karta hai, taake
    koi doosre account ki report ID daal kar us ka data na utha le.
    """
    try:
        analysis = (
            db.query(SentimentAnalysis)
            .filter(SentimentAnalysis.analysis_id == analysis_id)
            .first()
        )
        if not analysis:
            raise HTTPException(404, "That report no longer exists.")

        sentiment_brand = (
            db.query(Brand).filter(Brand.brand_id == analysis.brand_id).first()
        )
        if not sentiment_brand:
            raise HTTPException(404, "That report no longer exists.")

        canonical = normalize_store_url(sentiment_brand.website_url or "")
        owns = any(
            normalize_store_url(p.website_url or "") == canonical
            for p in db.query(BrandProfile).filter(BrandProfile.user_id == caller).all()
        )
        if not owns:
            raise HTTPException(403, "This report belongs to another account.")

        display_name = (analysis.analysis_data or {}).get("brand_name") \
            or sentiment_brand.brand_name or "Brand"

        from modules.sentiment.services.sentiment_pdf import generate_sentiment_pdf
        pdf_bytes = generate_sentiment_pdf(analysis, display_name)

        safe = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_") or "brand"
        stamp = (analysis.analysis_date or datetime.utcnow()).strftime("%Y%m%d")
        filename = f"sentiment_report_{safe}_{stamp}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("PDF export failed for %s: %s", analysis_id, e, exc_info=True)
        raise HTTPException(500, "Could not build the report. Please try again.")


@router.get("/health")
async def health_check():
    return {"status": "Sentiment Module running ✓ (Trustpilot source active)"}