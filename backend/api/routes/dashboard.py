"""
Dashboard summary — har module ka chhota sa headline stat, EK request mein.

── Ye endpoint kyun hai ─────────────────────────────────────────────────────
Dashboard par saat cards hain. Agar har card apna module ka endpoint khud call
kare to landing par 7 requests jati hain, har ek apna auth round-trip (Supabase
`GET /auth/v1/user`) le kar. Yahan wo saara kaam EK request mein hota hai: ek
token verification, ek DB session, chand chhoti queries.

── SAKHT USOOL: yahan kuch RE-COMPUTE nahi hota ─────────────────────────────
Har stat ya to `count(*)` hai ya kisi table ki AAKHRI row ka ek column. Koi
LLM call nahi, koi audit dobara nahi chalta, koi scraping nahi. Dashboard ek
padhne wala safha hai — agar ye kuch generate karne lage to har page load
paisa aur rate limit kharch karega.

Isi wajah se Brand Insights ka card "kitni suggestions hain" NAHI dikhata:
generate_improvements() apna nateeja kahin save nahi karta (do Groq calls chal
kar wapas aa jati hain, bas). Us count ko dikhane ka matlab hota har dashboard
load par dobara LLM chalana. Uski jagah card ye batata hai ke insights ke liye
DATA kitna tayar hai — chaar sources mein se kitne bhare hue hain. Ye muft hai
aur sach bhi.

── Ek card girey to poora dashboard na girey ────────────────────────────────
Har module ka block apne try/except mein hai. Kisi module ka table gayab ho,
sentiment models import na hon, ya query fail ho jaye — us card ka `available`
false ho jata hai aur frontend uska dostana empty state dikhata hai. Baqi
cards phir bhi bharay huay aate hain. Jo block fail hua wo `degraded` list
mein aata hai (sirf debugging ke liye; UI use nahi karta).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, or_, text
from sqlalchemy.orm import Session

from database.connection import get_db
from models.ads_generated import GeneratedAd
from models.chatbot import ChatbotInstance, Conversation
from models.seo_result import SEOAuditResult, SEOKeywordSuggestion
from models.video_ads_generated import GeneratedVideoAd
from modules.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _iso(value) -> str | None:
    """DateTime -> ISO string, None-safe."""
    return value.isoformat() if value else None


# ── 1. Brand row + product count ──────────────────────────────────────
def _load_brand(db: Session, user_id: str, brand_profile_id: int) -> dict:
    """
    Brand ki bunyadi maloomat + product count.

    Raw SQL JAAN BOOJH KAR hai, ORM nahi. `db.query(BrandProfile)` poora
    `products` JSON column memory mein khinch leta hai — asimjofa ke liye wo
    akela 9 MB hai, sirf usay gin kar phenkne ke liye. `jsonb_array_length`
    ye kaam Postgres ke andar karta hai aur wapas ek integer aata hai. Yehi
    tareeqa scraping.py ka /my-brands bhi istemal karta hai (wahan is se
    1,355 ms se 267 ms hua tha).

    `user_id = :uid` isi WHERE mein hai — yani ownership check aur data fetch
    ek hi query hain. Doosre ka brand_profile_id bhejne par row milti hi nahi,
    to 404 aata hai (403 nahi — doosre user ko ye batane ki zaroorat nahi ke
    id maujood hai, bas kisi aur ki hai).
    """
    row = db.execute(text("""
        SELECT id, business_name, website_url, platform, logo_url, created_at,
               COALESCE(jsonb_array_length(products::jsonb), 0) AS product_count
        FROM brand_profiles
        WHERE id = :bid AND user_id = :uid
    """), {"bid": brand_profile_id, "uid": user_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Brand not found.")
    return dict(row)


# ── 2. Sentiment ──────────────────────────────────────────────────────
def _sentiment_card(db: Session, brand: dict) -> dict:
    """
    Aakhri sentiment run ka positive % aur review count.

    Query brand_improvement se REUSE hoti hai, dobara nahi likhi. `_latest_
    sentiment` mein website_url-matching ka wo fix hai jo naam se match karne
    wale purane bug ko theek karta hai (sentiment module apna naam
    clean_brand_name() se save karta hai, jo BrandProfile.business_name se
    alag ho sakta hai). Yahan wo query copy karne ka matlab hota ke aage koi
    bug sirf ek jagah theek ho.
    """
    from modules.brand_improvement.service import _latest_sentiment

    name = brand.get("business_name") or brand.get("website_url") or ""
    data = _latest_sentiment(db, name, website_url=brand.get("website_url"))
    if not data:
        return {"available": False}

    score = data.get("overall_sentiment_score")
    reviews = data.get("total_reviews") or 0

    # Ek analysis row jis mein na score hai na reviews, woh "chal chuki hai"
    # ke barabar nahi — card ko empty hi rehna chahiye, warna user ko "0%
    # positive" dikhega jo ghalat matlab deta hai.
    if score is None and not reviews:
        return {"available": False}

    # platforms aur keywords analysis_data mein pehle se mehfooz hain
    # (routes.py :: analyze_from_dropdown -> analysis_data), is liye inhe
    # bhejna muft hai — koi dobara analysis nahi chalti.
    platforms = data.get("platforms") if isinstance(data.get("platforms"), dict) else {}
    sources = sorted(
        ({"name": k, "count": int(v)} for k, v in (platforms or {}).items() if v),
        key=lambda s: s["count"],
        reverse=True,
    )

    raw_keywords = data.get("keywords")
    keywords = []
    if isinstance(raw_keywords, list):
        for k in raw_keywords[:10]:
            if isinstance(k, dict) and k.get("keyword"):
                keywords.append({
                    "keyword": str(k["keyword"]),
                    "frequency": int(k.get("frequency") or 0),
                })

    def _themes(key: str) -> list[str]:
        value = data.get(key)
        return [str(v) for v in value[:4]] if isinstance(value, list) else []

    return {
        "available": True,
        "positive_percent": round(score, 1) if score is not None else None,
        "review_count": reviews,
        "dominant_emotion": data.get("dominant_emotion"),
        "breakdown": _sentiment_breakdown(data.get("sentiment_summary")),
        "emotions": _emotion_counts(data.get("emotions")),
        "sources": sources,
        "keywords": keywords,
        "loved": _themes("loved"),
        "pain_points": _themes("pain_points"),
    }


def _sentiment_breakdown(summary) -> dict | None:
    """
    Positive/negative/neutral ka asli breakdown — donut ke liye.

    Ye analysis_data["sentiment_summary"] se JYON KA TYON aata hai, yahan koi
    hisaab nahi hota. Sirf overall_sentiment_score (positive %) se baqi do
    hisse NIKALE NAHI ja sakte — negative aur neutral ka batwara us ek number
    mein hai hi nahi. Is liye jab tak ye blob na ho, donut nahi banta:
    andaza laga kar chart banana asli data dikhane se bura hai.

    Purani analysis rows mein ye key na ho to None — us soorat mein card apna
    number to dikhata hai, magar donut ki jagah dostana paighaam aata hai.
    """
    if not isinstance(summary, dict):
        return None

    def _int(key: str) -> int:
        value = summary.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    positive, negative, neutral = _int("positive"), _int("negative"), _int("neutral")
    total = positive + negative + neutral
    # Sab sifar = koi review classify hi nahi hua. Khali donut (teen 0% slices)
    # se behtar hai ke chart hi na banay.
    if total <= 0:
        return None

    def _pct(key: str, count: int) -> float:
        stored = summary.get(key)
        if isinstance(stored, (int, float)):
            return round(float(stored), 1)
        # Purani rows mein percent columns na hon to count se bana lo — ye
        # andaza nahi, wahi ginti hai jo ooper aa chuki hai.
        return round(count / total * 100, 1)

    return {
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "total": total,
        "positive_percent": _pct("positive_percent", positive),
        "negative_percent": _pct("negative_percent", negative),
        "neutral_percent": _pct("neutral_percent", neutral),
    }


def _emotion_counts(emotions) -> list[dict]:
    """
    Emotion breakdown — bars ke liye, sab se ziyada wali pehle.

    SIFAR wali emotions nikal di jati hain. Stored blob mein hamesha saaton
    keys hoti hain chahe unka count 0 ho (misal: "satisfied": 0), aur un ki
    khali bars chart ko bhara hua dikhati hain jab ke haqeeqat mein us emotion
    ka koi review nahi mila.

    Label/rang frontend tay karta hai — wo pesh karne ki baat hai. Yahan se
    sirf key aur ginti jati hai, to naye emotion type aane par backend badalna
    nahi parta.
    """
    if not isinstance(emotions, dict):
        return []
    rows = [
        {"key": str(key), "count": int(value)}
        for key, value in emotions.items()
        if isinstance(value, (int, float)) and value > 0
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows


# ── 3. SEO ────────────────────────────────────────────────────────────
def _seo_card(db: Session, user_id: str, brand_id: int) -> dict:
    """
    Aakhri audit ka score + save-shuda keywords ki tadaad.

    Dono queries column-level hain (poori ORM row nahi): SEOAuditResult mein
    paanch JSON issue-blobs hain jo hazaaron products ke liye bare hote hain,
    aur yahan sirf score chahiye.
    """
    # Factor scores aur health counts bhi saath le lo — ye sab isi row ke
    # chhote numeric columns hain, to koi extra query nahi lagti. Dashboard ke
    # radar aur health charts inhi se bantay hain.
    #
    # *_issues JSON blobs YAHAN NAHI aate: unmein hazaaron rows hoti hain
    # (asimjofa: 7.6 MB across five columns) aur dashboard ko sirf ginti
    # chahiye, tafseel nahi. Tafseel SEO ke apne safhe par hai.
    audit = (
        db.query(
            SEOAuditResult.seo_score,
            SEOAuditResult.created_at,
            SEOAuditResult.title_score,
            SEOAuditResult.description_score,
            SEOAuditResult.image_alt_score,
            SEOAuditResult.image_alt_measurable,
            SEOAuditResult.keyword_score,
            SEOAuditResult.tags_score,
            SEOAuditResult.good_count,
            SEOAuditResult.warning_count,
            SEOAuditResult.needs_work_count,
            SEOAuditResult.total_products_audited,
            SEOAuditResult.total_catalogue_products,
        )
        .filter(
            SEOAuditResult.user_id == user_id,
            SEOAuditResult.brand_profile_id == brand_id,
        )
        .order_by(desc(SEOAuditResult.created_at))
        .first()
    )

    # keywords ek chhoti list hai (~30 items), is liye isay laana sasta hai.
    # order_by yahan JAAN BOOJH KAR hai — module ka apna /keywords route
    # bagair order ke .first() karta hai, jo ek se zyada rows par kisi bhi row
    # ko utha sakta hai. Dashboard hamesha TAZA TAREEN dikhaye.
    kw_row = (
        db.query(SEOKeywordSuggestion.keywords)
        .filter(
            SEOKeywordSuggestion.user_id == user_id,
            SEOKeywordSuggestion.brand_profile_id == brand_id,
        )
        .order_by(desc(SEOKeywordSuggestion.created_at))
        .first()
    )
    keywords = kw_row[0] if kw_row else None
    keyword_count = len(keywords) if isinstance(keywords, list) else 0

    if not audit and not keyword_count:
        return {"available": False}

    def _f(value) -> float | None:
        return round(value, 1) if value is not None else None

    factors = None
    health = None
    coverage = None
    if audit:
        # image_alt tab hi factor list mein aata hai jab wo NAAP-NE QABIL ho.
        # Shopify ki products feed alt text expose nahi karti, aisi soorat
        # mein audit us factor ko score se bahar rakhta hai — chart mein 0%
        # ka bar dikhana wahi jhoot dohrana hota (dekho seo_auditor.py).
        alt_measurable = audit.image_alt_measurable is not False
        factors = [
            {"key": "title", "label": "Titles", "score": _f(audit.title_score)},
            {"key": "description", "label": "Descriptions", "score": _f(audit.description_score)},
            {"key": "keyword", "label": "Keywords", "score": _f(audit.keyword_score)},
            {"key": "tags", "label": "Tags", "score": _f(audit.tags_score)},
        ]
        if alt_measurable:
            factors.insert(2, {
                "key": "image_alt", "label": "Image alt", "score": _f(audit.image_alt_score),
            })
        factors = [f for f in factors if f["score"] is not None]

        good = audit.good_count or 0
        warning = audit.warning_count or 0
        needs_work = audit.needs_work_count or 0
        if good or warning or needs_work:
            health = {"good": good, "warning": warning, "needs_work": needs_work}

        if audit.total_products_audited:
            coverage = {
                "audited": audit.total_products_audited,
                "catalogue": audit.total_catalogue_products or audit.total_products_audited,
            }

    # Top keywords — bars ke liye. Poori list nahi bhejte: 30 items ka chart
    # parha nahi jata, aur module ka apna safha poori list dikhata hai.
    top_keywords = []
    if isinstance(keywords, list):
        for k in keywords[:8]:
            if not isinstance(k, dict):
                continue
            name = str(k.get("keyword") or "").strip()
            if not name:
                continue
            top_keywords.append({
                "keyword": name,
                "score": k.get("opportunity_score"),
                "volume": k.get("search_volume"),
                "validated": bool(k.get("google_validated")),
            })

    return {
        "available": True,
        "score": _f(audit.seo_score) if audit else None,
        "keyword_count": keyword_count,
        "last_audit": _iso(audit.created_at) if audit else None,
        "factors": factors,
        "health": health,
        "coverage": coverage,
        "top_keywords": top_keywords,
    }


# ── 3b. Catalogue shape ───────────────────────────────────────────────
def _catalogue_card(db: Session, brand_id: int) -> dict:
    """
    Catalogue ka breakdown — category counts + store locale.

    Categories Postgres ke ANDAR ginte hain. Poora `products` column laa kar
    Python mein ginna 9 MB kheenchta (asimjofa), sirf ek chhoti si list banane
    ke liye. `jsonb_array_elements` wahi tareeqa hai jo scraping.py ka
    products-page endpoint pehle se istemal karta hai.

    Category har product par scraping ke waqt set ho chuki hoti hai
    (detect_product_category), to yahan koi nayi calculation nahi ho rahi —
    sirf ginti.
    """
    row = db.execute(text("""
        SELECT
            b.price_range,
            b.store_country,
            b.store_currency,
            b.product_categories,
            COALESCE((
                SELECT jsonb_object_agg(cat, n)
                FROM (
                    SELECT COALESCE(NULLIF(TRIM(elem->>'category'), ''), 'other') AS cat,
                           count(*) AS n
                    FROM jsonb_array_elements(b.products::jsonb) AS elem
                    GROUP BY 1
                ) g
            ), '{}'::jsonb) AS category_counts
        FROM brand_profiles b
        WHERE b.id = :bid
    """), {"bid": brand_id}).mappings().first()

    if not row:
        return {"available": False}

    counts = row["category_counts"] or {}
    categories = sorted(
        ({"name": k, "count": v} for k, v in counts.items()),
        key=lambda c: c["count"],
        reverse=True,
    )

    return {
        "available": bool(categories),
        "categories": categories,
        "price_range": row["price_range"],
        "store_country": row["store_country"],
        "store_currency": row["store_currency"],
    }


# ── 3c. Written content ───────────────────────────────────────────────
def _content_card(db: Session, user_id: str, brand_id: int) -> dict:
    """
    Kitna content ban chuka hai — blogs, keywords, image ads, video ads.

    Sab `count(*)` hain, koi row body nahi aati. Blog posts ka content column
    hazaaron alfaz ka hota hai; yahan sirf ginti chahiye.
    """
    blogs = db.execute(text("""
        SELECT count(*) FROM seo_blog_posts
        WHERE user_id = :uid AND brand_profile_id = :bid
    """), {"uid": user_id, "bid": brand_id}).scalar() or 0

    return {"blog_count": int(blogs)}


# ── 4. Image / video ads ──────────────────────────────────────────────
def _ads_card(db: Session, model, user_id: str, brand_id: int) -> dict:
    """
    Kitne ads banay + aakhri kab. Dono ad tables ki shakl ek jaisi hai
    (user_id + brand_id + created_at), is liye ek hi function dono chalata hai.
    """
    count = (
        db.query(model.id)
        .filter(model.user_id == user_id, model.brand_id == brand_id)
        .count()
    )
    if not count:
        return {"available": False, "count": 0}

    latest = (
        db.query(model.created_at)
        .filter(model.user_id == user_id, model.brand_id == brand_id)
        .order_by(desc(model.created_at))
        .first()
    )
    return {
        "available": True,
        "count": count,
        "latest": _iso(latest[0]) if latest else None,
    }


# ── 5. Chatbot ────────────────────────────────────────────────────────
def _chatbot_card(db: Session, user_id: str, brand_id: int) -> dict:
    """
    Is brand ke bots ka status + un par kitni conversations hui hain.

    `brand_profile_id IS NULL` bhi shamil hai: chatbot module ke apne routes
    (/my-bots) ab tak sirf user par scope karte hain, aur brand_profile_id
    baad mein add hua tha — yani purane bots ki wo value NULL hai. Sirf
    brand par match karne se aise bots dashboard se GAYAB ho jate, chahe user
    unhe chatbot page par saaf dekh raha ho. NULL ko shamil karna un legacy
    bots ko dikha deta hai, aur kisi DOOSRE brand ke bots phir bhi nahi aate.
    """
    bots = (
        db.query(ChatbotInstance.bot_id, ChatbotInstance.status, ChatbotInstance.is_active)
        .filter(
            ChatbotInstance.user_id == user_id,
            or_(
                ChatbotInstance.brand_profile_id == brand_id,
                ChatbotInstance.brand_profile_id.is_(None),
            ),
        )
        .all()
    )
    if not bots:
        return {"available": False}

    bot_ids = [b[0] for b in bots]
    active = sum(1 for b in bots if b[2] and (b[1] or "active") == "active")

    conversations = (
        db.query(Conversation.id)
        .filter(Conversation.bot_id.in_(bot_ids))
        .count()
    )

    return {
        "available": True,
        "bot_count": len(bots),
        "active_count": active,
        "conversation_count": conversations,
    }


# ── 6. Brand Insights (readiness, not results) ────────────────────────
# Insights jin sources par bantay hain — TAY-SHUDA tarteeb mein.
#
# Tarteeb yahan is liye tay hai ke card in ko chhoti bars ke tor par dikhata
# hai. Agar tarteeb badalti rahe to har load par bars idhar udhar ho jayen,
# aur ek hi brand ka card do dafa alag nazar aaye.
_INSIGHT_SOURCES = [
    ("products", "Products"),
    ("sentiment", "Sentiment"),
    ("seo_audit", "SEO audit"),
    ("keywords", "Keywords"),
]


def _insights_card(products: int, sentiment: dict, seo: dict) -> dict:
    """
    Insights ke liye data kitna tayar hai.

    Ye module apne nateeje SAVE NAHI karta (dekho file ka header), is liye
    yahan koi suggestion count nahi ho sakta bagair LLM dobara chalaye. Jo
    cheez muft mein maloom hai wo ye hai ke jin chaar sources par insights
    bantay hain, un mein se kitne maujood hain — aur wo teenon values yahan
    pehle se calculate ho chuki hain, to is card ki koi EXTRA query nahi hai.

    `sources` mein wo bhi hain jo tayar NAHI — sirf tayar wale bhejne se card
    ye nahi dikha sakta ke "chaar mein se do", jo is card ka poora matlab hai.
    Har entry ka `label` bhi saath jata hai taake bars ke tooltip frontend
    mein dobara na likhne parein.
    """
    ready_map = {
        "products": products > 0,
        "sentiment": bool(sentiment.get("available")),
        "seo_audit": bool(seo.get("available") and seo.get("score") is not None),
        "keywords": bool(seo.get("keyword_count")),
    }
    ready = sum(1 for v in ready_map.values() if v)
    return {
        # Ek bhi source ho to card kuch dikha sakta hai; bilkul khali brand par
        # frontend "pehle scraping chalao" wala empty state dikhata hai.
        "available": ready > 0,
        "sources_ready": ready,
        "sources_total": len(_INSIGHT_SOURCES),
        "sources": [
            {"key": key, "label": label, "ready": ready_map[key]}
            for key, label in _INSIGHT_SOURCES
        ],
    }


# ── Endpoint ──────────────────────────────────────────────────────────
@router.get("/summary")
def dashboard_summary(
    brand_profile_id: int = Query(..., description="Active brand id"),
    caller: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dashboard ke saare cards ka data, ek request mein.

    user_id URL mein NAHI hai — identity token se aati hai. Isi liye yahan
    require_owner ki zaroorat nahi: brand query khud `user_id = caller` par
    filter karti hai.
    """
    brand = _load_brand(db, caller, brand_profile_id)
    brand_id = brand["id"]
    degraded: list[str] = []

    def safe(name: str, fn, fallback: dict):
        """Ek card fail ho to sirf wohi card empty ho — poora dashboard nahi."""
        try:
            return fn()
        except Exception as e:
            logger.warning("[dashboard] %s card unavailable: %s", name, e)
            degraded.append(name)
            return fallback

    sentiment = safe("sentiment", lambda: _sentiment_card(db, brand), {"available": False})
    seo = safe("seo", lambda: _seo_card(db, caller, brand_id), {"available": False})
    image_ads = safe("image_ads", lambda: _ads_card(db, GeneratedAd, caller, brand_id),
                     {"available": False, "count": 0})
    video_ads = safe("video_ads", lambda: _ads_card(db, GeneratedVideoAd, caller, brand_id),
                     {"available": False, "count": 0})
    chatbot = safe("chatbot", lambda: _chatbot_card(db, caller, brand_id), {"available": False})
    catalogue = safe("catalogue", lambda: _catalogue_card(db, brand_id), {"available": False})
    content = safe("content", lambda: _content_card(db, caller, brand_id), {"blog_count": 0})

    product_count = brand.get("product_count") or 0
    products = {
        "available": product_count > 0,
        "count": product_count,
        "platform": brand.get("platform"),
        "categories": catalogue.get("categories") or [],
        "price_range": catalogue.get("price_range"),
        "store_country": catalogue.get("store_country"),
        "store_currency": catalogue.get("store_currency"),
    }
    insights = _insights_card(product_count, sentiment, seo)

    # Content mix — ek jagah par har wo cheez jo user ne banwai hai.
    # Sab counts pehle se calculate ho chuke hain, koi nayi query nahi.
    content_mix = [
        {"key": "blogs", "label": "Blog posts", "count": content.get("blog_count", 0)},
        {"key": "keywords", "label": "Keywords", "count": seo.get("keyword_count", 0) or 0},
        {"key": "image_ads", "label": "Image ads", "count": image_ads.get("count", 0) or 0},
        {"key": "video_ads", "label": "Video ads", "count": video_ads.get("count", 0) or 0},
    ]

    return {
        "success": True,
        "brand": {
            "id": brand_id,
            "business_name": brand.get("business_name"),
            "website_url": brand.get("website_url"),
            "platform": brand.get("platform"),
            "logo_url": brand.get("logo_url"),
            "created_at": _iso(brand.get("created_at")),
        },
        "modules": {
            "sentiment": sentiment,
            "seo": seo,
            "insights": insights,
            "products": products,
            "image_ads": image_ads,
            "video_ads": video_ads,
            "chatbot": chatbot,
        },
        "content_mix": content_mix,
        # Sirf debugging ke liye — UI is par kuch render nahi karta.
        "degraded": degraded,
    }


@router.get("/health")
def health():
    return {"status": "Dashboard module running ✅"}
