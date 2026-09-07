import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.brand_profile import BrandProfile
from models.seo_result import SEOAuditResult
from modules.seo.seed_extractor import (
    STOPWORDS,
    audit_seed_keywords,
    has_location,
    strip_location,
)


# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────

# Ideal lengths
TITLE_MIN = 30
TITLE_MAX = 70
DESC_MIN = 120
DESC_MAX = 170

# Audit sample size.
# Pehle 100 tha, jab catalogs ~1,000 products ke the (10% coverage). Pagination
# fix ke baad catalogs 7,000-10,000 products ke hain, to 100 ka matlab sirf 1.4%
# coverage tha — aur hamesha wahi pehle 100 (newest) products, jo poore store ka
# representative sample nahi hain. 1,000 par coverage 10x behtar hai aur cost
# na ke barabar: 5 factors × 1,000 products = ~4 ms.
MAX_AUDIT_PRODUCTS = 1000

# Score weights (must sum to 100)
WEIGHTS = {
    "title": 0.20,
    "description": 0.20,
    "image_alt": 0.20,
    "keyword": 0.20,
    "tags": 0.20,
}


# ─────────────────────────────────────────────
#  ISSUE STORAGE
# ─────────────────────────────────────────────

def actionable_issues(issues: list) -> list:
    """
    Sirf wo rows rakhta hai jinke liye user kuch kar sakta hai.

    "Good" rows ~60% hote hain aur koi information nahi dete — unki ginti
    pehle se good_count mein mojood hai. Poore catalogue par ye rows JSON
    columns ko bhaari kar deti hain (7,157 products = 7.63 MB across the five
    *_issues columns), isliye inhe store nahi karte.
    """
    return [i for i in issues if i.get("severity") != "Good"]


# ─────────────────────────────────────────────
#  INDIVIDUAL FACTOR AUDITORS
# ─────────────────────────────────────────────

def audit_titles(products: list) -> dict:
    """
    Product title quality check.
    Good: 30-70 chars
    Warning: 20-29 or 71-90 chars
    Needs Work: <20 or >90 chars or missing
    """
    issues = []
    good = warning = needs_work = 0

    for p in products:
        name = (p.get("name") or "").strip()
        length = len(name)

        if not name:
            severity = "Needs Work"
            issue = "Product title is missing"
            recommendation = "Add a descriptive product title between 30-70 characters"
            needs_work += 1
        elif length < TITLE_MIN:
            severity = "Warning"
            issue = f"Title too short ({length} chars) — ideal is 30-70 chars"
            recommendation = f"Expand title to be more descriptive. Current: '{name}'"
            warning += 1
        elif length > TITLE_MAX:
            severity = "Warning"
            issue = f"Title too long ({length} chars) — ideal is 30-70 chars"
            recommendation = f"Shorten title to under 70 characters. Current: '{name}'"
            warning += 1
        else:
            severity = "Good"
            issue = "Title length is optimal"
            recommendation = None
            good += 1

        issues.append({
            "product_name": name or "Unknown",
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
            "current_length": length,
        })

    total = len(products)
    score = round((good / total) * 100, 1) if total > 0 else 0

    return {
        "score": score,
        "issues": issues,
        "good": good,
        "warning": warning,
        "needs_work": needs_work,
    }


def audit_descriptions(products: list) -> dict:
    """
    Meta description quality check.
    Good: 120-170 chars
    Warning: 80-119 or 171-200 chars
    Needs Work: <80 or >200 chars or missing
    """
    issues = []
    good = warning = needs_work = 0

    for p in products:
        desc = (p.get("description") or "").strip()
        length = len(desc)

        if not desc:
            severity = "Needs Work"
            issue = "Product description is missing"
            recommendation = "Add a product description between 120-170 characters for better SEO"
            needs_work += 1
        elif length < 80:
            severity = "Needs Work"
            issue = f"Description too short ({length} chars) — ideal is 120-170 chars"
            recommendation = "Write a more detailed product description with key features and benefits"
            needs_work += 1
        elif length < DESC_MIN:
            severity = "Warning"
            issue = f"Description slightly short ({length} chars) — ideal is 120-170 chars"
            recommendation = "Expand description slightly to reach 120 characters minimum"
            warning += 1
        elif length > 200:
            severity = "Warning"
            issue = f"Description too long ({length} chars) — ideal is 120-170 chars"
            recommendation = "Trim description to under 170 characters for optimal SEO"
            warning += 1
        else:
            severity = "Good"
            issue = "Description length is optimal"
            recommendation = None
            good += 1

        issues.append({
            "product_name": p.get("name") or "Unknown",
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
            "current_length": length,
        })

    total = len(products)
    score = round(((good + warning * 0.5) / total) * 100, 1) if total > 0 else 0

    return {
        "score": score,
        "issues": issues,
        "good": good,
        "warning": warning,
        "needs_work": needs_work,
    }


def audit_image_alts(products: list) -> dict:
    """
    Image alt text presence check.
    Good: alt text exists and is descriptive (>10 chars)
    Warning: alt text exists but too short (<10 chars)
    Needs Work: alt text missing or empty
    """
    issues = []
    good = warning = needs_work = 0

    for p in products:
        alt = (p.get("image_alt") or "").strip()
        name = (p.get("name") or "Unknown").strip()

        if not alt:
            severity = "Needs Work"
            issue = "Image alt text is missing"
            recommendation = f"Add descriptive alt text to product image. Suggested: '{name}'"
            needs_work += 1
        elif len(alt) < 10:
            severity = "Warning"
            issue = f"Image alt text too short ('{alt}')"
            recommendation = "Make alt text more descriptive — describe what is shown in the image"
            warning += 1
        else:
            severity = "Good"
            issue = "Image alt text is present and descriptive"
            recommendation = None
            good += 1

        issues.append({
            "product_name": name,
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
            "current_alt": alt or None,
        })

    total = len(products)
    score = round(((good + warning * 0.5) / total) * 100, 1) if total > 0 else 0

    # ── "Store publishes no alt text at all" ko 0/100 mat kaho ───────────────
    #
    # Shopify ki /products.json feed mein `images[].alt` tqreeban hamesha null
    # hoti hai — merchant ne alt text likha ho tab bhi. Nateeja: har store ka
    # image_alt score 0.0 aata tha, aur ye factor overall score ka 20% hai, to
    # HAR brand ka score ~80 par cap ho jata tha aur panel hamesha khali bar
    # dikhata tha. Ye brand ki SEO ki khaami nahi, data source ki hadd hai.
    #
    # Farq yun karte hain: agar catalogue mein KISI EK product par bhi alt text
    # mila, to feed alt text deti hai aur baaqi ka khali hona asli finding hai.
    # Ek bhi na mile to factor "not_measurable" hai — overall score se nikal
    # jata hai (dekho calculate_seo_score) aur UI usay 0 ki jagah wajah dikhata.
    measurable = (good + warning) > 0

    return {
        "score": score,
        "issues": issues if measurable else [],
        "good": good,
        "warning": warning,
        "needs_work": needs_work if measurable else 0,
        "measurable": measurable,
        "not_measurable_reason": None if measurable else (
            "This store's product feed does not publish image alt text, so it "
            "cannot be measured here. Alt text set inside the Shopify theme is "
            "not exposed by the products feed."
        ),
    }


# ── Keyword Usage ────────────────────────────────────────────────────────────
#
# ── Ye factor kyun dobara likha gaya ─────────────────────────────────────────
# Do bugs the, aur dono mil kar Maria.B par score 0.0% de rahe the:
#
#   1. TARGET KEYWORDS HI GHALAT THE. Generator "Karachi embroidered lawn
#      suit" jaise keywords bana raha tha. Audit poochta tha "kya kisi product
#      ke title mein 'Karachi embroidered lawn suit' hai?" — jawab hamesha
#      nahi tha, kyunke store apne titles mein sheher likhta hi nahi.
#
#   2. MATCHING KA TAREEQA HI GHALAT THA. `kw in name` poore phrase ko ek
#      substring ki tarah dhoondta tha. Ye ab bhi fail hota hai chahe keyword
#      bilkul saaf ho: keyword "embroidered lawn suit 3 piece" aur title
#      "3 Piece Unstitched Embroidered Lawn Suit" — insaan ke liye ye match
#      hai, `in` ke liye nahi. Long-tail keyword kabhi bhi kisi title ka
#      exact substring nahi hota, is liye ye check hamesha 0 dene wala tha.
#
# Ab: keywords se location nikal jati hai (bug 1), aur matching TOKEN level par
# hoti hai — keyword ke content words ka kitna hissa title/description mein
# maujood hai (bug 2).

# Kitne content words milen to keyword "use hua" mana jaye. 0.6 ka matlab:
# 5 lafz wale keyword ke 3 lafz. Poora phrase maangna (1.0) wahi purana
# substring wala masla hai; aadha se kam (0.4) par har keyword har product se
# match kar jata hai aur factor bekaar ho jata hai.
KEYWORD_MATCH_RATIO = 0.6


def _keyword_tokens(keyword: str) -> list[str]:
    """Keyword ke content words — modifiers aur glue words nikaal kar."""
    return [
        w for w in re.findall(r"[a-z0-9]+", (keyword or "").lower())
        if w not in STOPWORDS
    ]


def prepare_target_keywords(products: list, target_keywords: list) -> list[str]:
    """
    Audit ke liye match karne layak keywords.

    Brand ke generate kiye hue keywords hon to unhe location se saaf kar ke
    use karo; na hon (ya saaf hone ke baad kuch na bache) to catalogue se
    seeds nikaal lo — bina LLM, bina API. Seeds definition ke mutabiq
    products se match karte hain, is liye score haqeeqi aata hai.
    """
    cleaned = []
    for keyword in target_keywords or []:
        keyword = strip_location(keyword) if has_location(keyword) else (keyword or "").strip().lower()
        if _keyword_tokens(keyword):
            cleaned.append(keyword)

    # Dedupe, tarteeb qaayam rakhte hue.
    cleaned = list(dict.fromkeys(cleaned))
    if cleaned:
        return cleaned
    return audit_seed_keywords(products)


def audit_keywords(products: list, target_keywords: list) -> dict:
    """
    Keyword usage check — kya target keywords title ya description mein hain?
    Good: keyword title mein mila
    Warning: sirf description mein mila
    Needs Work: kahin nahi mila
    """
    issues = []
    good = warning = needs_work = 0

    keywords = prepare_target_keywords(products, target_keywords)
    if not keywords:
        return {
            "score": 50,
            "issues": [],
            "good": 0,
            "warning": len(products),
            "needs_work": 0,
            "keywords_used": [],
        }

    # Tokens ek hi baar nikaalo — 1,000 products x 20 keywords par ye har
    # product ke andar dobara karna 20,000 regex calls ban jata hai.
    tokenized = [(kw, _keyword_tokens(kw)) for kw in keywords]
    tokenized = [(kw, tokens) for kw, tokens in tokenized if tokens]

    for p in products:
        product_name = (p.get("name") or "Unknown").strip()
        title_words = set(re.findall(r"[a-z0-9]+", (p.get("name") or "").lower()))
        desc_words = set(re.findall(r"[a-z0-9]+", (p.get("description") or "").lower()))

        matched_in_title = []
        matched_in_desc = []
        for keyword, tokens in tokenized:
            needed = max(1, round(len(tokens) * KEYWORD_MATCH_RATIO))
            if sum(t in title_words for t in tokens) >= needed:
                matched_in_title.append(keyword)
            elif sum(t in desc_words for t in tokens) >= needed:
                matched_in_desc.append(keyword)

        if matched_in_title:
            severity = "Good"
            issue = f"Target keyword found in product title: {', '.join(matched_in_title[:3])}"
            recommendation = None
            good += 1
        elif matched_in_desc:
            severity = "Warning"
            issue = (
                f"Target keyword found in description only: "
                f"{', '.join(matched_in_desc[:3])} — consider adding to the title"
            )
            recommendation = "Include a relevant keyword naturally in the product title"
            warning += 1
        else:
            severity = "Needs Work"
            issue = "No target keywords found in title or description"
            recommendation = (
                f"Naturally incorporate relevant keywords like: "
                f"{', '.join(keywords[:3])}"
            )
            needs_work += 1

        issues.append({
            "product_name": product_name,
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
        })

    total = len(products)
    score = round(((good + warning * 0.5) / total) * 100, 1) if total > 0 else 0

    return {
        "score": score,
        "issues": issues,
        "good": good,
        "warning": warning,
        "needs_work": needs_work,
        # Audit ne ASAL mein kis cheez par match kiya — yehi "Target Keywords
        # Used in Audit" mein dikhta hai. Pehle wahan wo generated keywords
        # jate the jo audit se match hi nahi karte the.
        "keywords_used": keywords,
    }


def audit_tags(products: list) -> dict:
    """
    Tag completeness check.
    Good: 3 or more tags
    Warning: 1-2 tags
    Needs Work: no tags
    """
    issues = []
    good = warning = needs_work = 0

    for p in products:
        tags = p.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        tag_count = len(tags)
        product_name = (p.get("name") or "Unknown").strip()
        category = (p.get("category") or "").strip()

        if tag_count >= 3:
            severity = "Good"
            issue = f"Product has {tag_count} tags — good for discoverability"
            recommendation = None
            good += 1
        elif tag_count > 0:
            severity = "Warning"
            issue = f"Product has only {tag_count} tag(s) — add more for better discoverability"
            recommendation = f"Add at least 3 relevant tags. Example: category, material, occasion, gender"
            warning += 1
        else:
            severity = "Needs Work"
            issue = "Product has no tags — affects Shopify collection and search discoverability"
            recommendation = f"Add tags like: {category}, season, gender, occasion, material"
            needs_work += 1

        issues.append({
            "product_name": product_name,
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
            "tag_count": tag_count,
            "current_tags": tags[:5],  # show max 5 tags
        })

    total = len(products)
    score = round(((good + warning * 0.5) / total) * 100, 1) if total > 0 else 0

    return {
        "score": score,
        "issues": issues,
        "good": good,
        "warning": warning,
        "needs_work": needs_work,
    }


# ─────────────────────────────────────────────
#  OVERALL SCORE CALCULATOR
# ─────────────────────────────────────────────

def calculate_seo_score(
    title_score: float,
    description_score: float,
    image_alt_score: float,
    keyword_score: float,
    tags_score: float,
    *,
    image_alt_measurable: bool = True,
) -> float:
    """
    Weighted average of all factor scores.

    image_alt_measurable=False hone par wo factor score se BILKUL nikal jata
    hai aur baaqi 4 factors ke weights dobara normalize hote hain. Warna har
    Shopify store ko 20 points ki aisi saza milti thi jo uske control mein hi
    nahi (dekho audit_image_alts).
    """
    parts = [
        (title_score, WEIGHTS["title"]),
        (description_score, WEIGHTS["description"]),
        (keyword_score, WEIGHTS["keyword"]),
        (tags_score, WEIGHTS["tags"]),
    ]
    if image_alt_measurable:
        parts.append((image_alt_score, WEIGHTS["image_alt"]))

    total_weight = sum(w for _, w in parts) or 1.0
    score = sum(s * w for s, w in parts) / total_weight
    return round(score, 1)


# ─────────────────────────────────────────────
#  PRODUCT LOADING
# ─────────────────────────────────────────────

def _load_audit_products(db: Session, profile_id: int, limit: int):
    """
    Audit ke liye products ka slice — Postgres se, sirf 5 fields jo scoring
    functions actually padhti hain (name, description, image_alt, tags, category).

    Poora column pull karna waste tha: bare catalogue ka 88% data transfer hota
    tha jo kabhi audit hi nahi hota (MAX_AUDIT_PRODUCTS cap ki wajah se).

    Return: (products, catalogue_total)
    """
    row = db.execute(text("""
        SELECT
            COALESCE(jsonb_array_length(products::jsonb), 0) AS total,
            COALESCE((
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'name',        elem->'name',
                        'description', elem->'description',
                        'image_alt',   elem->'image_alt',
                        'tags',        elem->'tags',
                        'category',    elem->'category'
                    ) ORDER BY ord
                )
                FROM jsonb_array_elements(products::jsonb) WITH ORDINALITY AS t(elem, ord)
                WHERE ord <= :lim
            ), '[]'::jsonb) AS page
        FROM brand_profiles
        WHERE id = :pid
    """), {"pid": profile_id, "lim": limit}).mappings().first()

    if not row:
        return [], 0
    return row["page"] or [], row["total"] or 0


# ─────────────────────────────────────────────
#  MAIN AUDIT FUNCTION
# ─────────────────────────────────────────────

def run_seo_audit(
    brand_profile: BrandProfile,
    target_keywords: list,
    db: Session,
) -> SEOAuditResult:
    """
    Full SEO audit on brand profile products.
    Uses already scraped data from DB — no re-scraping.
    """

    # Pehle poora products column ORM se load hota tha — 7,157-product catalogue
    # par 5.24 MB aur 2,855 ms, sirf pehle 1,000 audit karne ke liye. Ab Postgres
    # hi sirf zaroori slice aur sirf wo 5 fields bhejta hai jo scoring padhti hai:
    # 0.61 MB / 355 ms (8x tez).
    audit_products, catalogue_total = _load_audit_products(
        db, brand_profile.id, MAX_AUDIT_PRODUCTS
    )
    total = len(audit_products)

    if total == 0:
        raise Exception("No products found in brand profile to audit")

    coverage = round(total / catalogue_total * 100, 1) if catalogue_total else 0
    print(
        f"Auditing {total} of {catalogue_total} products "
        f"({coverage}% coverage) for user {brand_profile.user_id}..."
    )

    # Run all 5 factor audits
    title_result = audit_titles(audit_products)
    description_result = audit_descriptions(audit_products)
    image_alt_result = audit_image_alts(audit_products)
    keyword_result = audit_keywords(audit_products, target_keywords)

    # "Target Keywords Used in Audit" mein WOHI keywords jane chahiyen jin par
    # audit ne asal mein match kiya. Pehle yahan raw generated keywords jate
    # the — is liye report "Karachi embroidered lawn suit" ko target keyword
    # bata kar 0% score dikhati thi, aur user ke paas samajhne ka koi zariya
    # nahi tha ke wo keyword kabhi match kar hi nahi sakta tha.
    keywords_used = keyword_result.get("keywords_used") or []
    tags_result = audit_tags(audit_products)

    print(f"✅ Title score: {title_result['score']}")
    print(f"✅ Description score: {description_result['score']}")
    print(f"✅ Image alt score: {image_alt_result['score']}")
    print(f"✅ Keyword score: {keyword_result['score']}")
    print(f"✅ Tags score: {tags_result['score']}")

    # Calculate overall score
    image_alt_measurable = image_alt_result.get("measurable", True)
    if not image_alt_measurable:
        print("ℹ️  Image alt: feed publishes none — factor excluded from score")

    overall_score = calculate_seo_score(
        title_result["score"],
        description_result["score"],
        image_alt_result["score"],
        keyword_result["score"],
        tags_result["score"],
        image_alt_measurable=image_alt_measurable,
    )

    print(f"✅ Overall SEO score: {overall_score}")

    # Total counts across all factors
    total_good = (
        title_result["good"] + description_result["good"] +
        image_alt_result["good"] + keyword_result["good"] + tags_result["good"]
    )
    total_warning = (
        title_result["warning"] + description_result["warning"] +
        image_alt_result["warning"] + keyword_result["warning"] + tags_result["warning"]
    )
    total_needs_work = (
        title_result["needs_work"] + description_result["needs_work"] +
        image_alt_result["needs_work"] + keyword_result["needs_work"] + tags_result["needs_work"]
    )

    # Save or update audit result in DB
    existing = db.query(SEOAuditResult).filter(
        SEOAuditResult.user_id == brand_profile.user_id,
        SEOAuditResult.brand_profile_id == brand_profile.id,
    ).order_by(SEOAuditResult.created_at.desc()).first()

    if existing:
        existing.seo_score = overall_score
        existing.title_score = title_result["score"]
        existing.description_score = description_result["score"]
        existing.image_alt_score = image_alt_result["score"]
        existing.image_alt_measurable = image_alt_measurable
        existing.keyword_score = keyword_result["score"]
        existing.tags_score = tags_result["score"]
        existing.title_issues = actionable_issues(title_result["issues"])
        existing.description_issues = actionable_issues(description_result["issues"])
        existing.image_alt_issues = actionable_issues(image_alt_result["issues"])
        existing.keyword_issues = actionable_issues(keyword_result["issues"])
        existing.tags_issues = actionable_issues(tags_result["issues"])
        existing.total_products_audited = total
        existing.total_catalogue_products = catalogue_total
        existing.good_count = total_good
        existing.warning_count = total_warning
        existing.needs_work_count = total_needs_work
        existing.suggested_keywords = keywords_used
        from datetime import datetime, timezone
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    audit_result = SEOAuditResult(
        user_id=brand_profile.user_id,
        brand_profile_id=brand_profile.id,
        seo_score=overall_score,
        title_score=title_result["score"],
        description_score=description_result["score"],
        image_alt_score=image_alt_result["score"],
        image_alt_measurable=image_alt_measurable,
        keyword_score=keyword_result["score"],
        tags_score=tags_result["score"],
        title_issues=actionable_issues(title_result["issues"]),
        description_issues=actionable_issues(description_result["issues"]),
        image_alt_issues=actionable_issues(image_alt_result["issues"]),
        keyword_issues=actionable_issues(keyword_result["issues"]),
        tags_issues=actionable_issues(tags_result["issues"]),
        total_products_audited=total,
        total_catalogue_products=catalogue_total,
        good_count=total_good,
        warning_count=total_warning,
        needs_work_count=total_needs_work,
        suggested_keywords=keywords_used,
    )

    db.add(audit_result)
    db.commit()
    db.refresh(audit_result)

    print(f" Audit saved! ID: {audit_result.id}")
    return audit_result