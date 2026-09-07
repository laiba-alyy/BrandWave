"""
Brand Improvement Suggestions — data-gathering + strict LLM generation.

Core rule: every suggestion MUST trace to a real data point.
If the data doesn't support a suggestion, the LLM must not produce it.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
import os
import re
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from models.brand_profile import BrandProfile
from models.seo_result import SEOAuditResult, SEOKeywordSuggestion

from modules.llm_config import (
    RateLimitedError,
    TruncatedCompletionError,
    chat_completion,
    get_groq_config,
    reasoning_params,
)

logger = logging.getLogger(__name__)


# ── Token budget ──────────────────────────────
#
# TPM pacing yahan se nikal di gayi hai. Pehle _TokenPacer har key ka apna
# 60-second token bucket rakhta tha aur Groq ki 8,000 TPM ceiling ko LATENCY
# mein badalta tha — brand insights ke lambe wait ki asal wajah wahi thi.
# Ab ye purpose OpenAI lane par pehle jata hai (dekho llm_config.PURPOSE_LANES)
# jahan wo ceiling hai hi nahi, aur Groq fallback par llm_config ka cooling +
# failover kaafi hai.
_MAX_TOKENS = int(os.getenv("BRAND_IMPROVEMENT_MAX_TOKENS", "1500"))

# One retry at a raised ceiling if the model still reports finish_reason
# "length" — a real token-limit hit, not malformed JSON.
_MAX_TOKENS_RETRY = _MAX_TOKENS * 2


# ═══════════════════════════════════════
#  1. DATA GATHERING
# ═══════════════════════════════════════

def _latest_sentiment(
    db: Session,
    brand_name: str,
    website_url: str | None = None,
) -> dict | None:
    """
    Find the most recent sentiment analysis for this brand.

    Sentiment uses its own Brand table (separate from BrandProfile).
    We match on ``website_url`` first (canonical on both sides) then fall
    back to a case-insensitive brand-name match.

    Previously this ONLY matched on brand_name via ``ilike`` — but the
    sentiment route stores names through ``clean_brand_name()`` (title-case,
    domain-stripped), while ``BrandProfile.business_name`` is whatever the
    scraper saved.  Any mismatch caused a silent miss and the LLM never
    saw sentiment data.

    The URL match itself then needed the same treatment.  The sentiment
    route creates its Brand row on ``normalize_store_url(...)`` — scheme
    forced, host lowercased, leading ``www.`` and trailing slash dropped —
    while BrandProfile keeps the URL exactly as the user typed it.  So an
    exact string compare missed every brand whose stored URL carried a
    ``www.``:

        brand_profiles : https://www.mariab.pk
        public.brands  : https://mariab.pk      -> no match

    and for that brand the name fallback missed too ("Maria.B" against the
    cleaned "Maria"), so a dashboard whose analysis had run an hour earlier
    still said "no sentiment yet".  Comparing normalized forms is what the
    sentiment route and ``get_results`` already do, so all three agree on
    what counts as the same store.
    """
    try:
        from modules.sentiment.database.models import Brand, SentimentAnalysis
    except ImportError as exc:
        logger.warning("[improvement] sentiment models not importable: %s", exc)
        return None

    sentiment_brand = None

    # ── Path A: website_url match (most reliable) ─────────────────────────
    if website_url:
        sentiment_brand = (
            db.query(Brand)
            .filter(Brand.website_url == website_url)
            .first()
        )

        # Exact-string miss -> retry on the canonical form.  The brands
        # table holds one row per store, so loading it and comparing in
        # Python is cheaper than teaching SQL the same normalisation rules.
        if not sentiment_brand:
            try:
                from modules.scraping.scraper import normalize_store_url
            except ImportError as exc:
                logger.warning("[improvement] normalize_store_url unavailable: %s", exc)
            else:
                target = normalize_store_url(website_url)
                sentiment_brand = next(
                    (
                        b for b in db.query(Brand).all()
                        if normalize_store_url(b.website_url or "") == target
                    ),
                    None,
                )

    # ── Path B: case-insensitive name match (fallback) ───────────────────
    if not sentiment_brand and brand_name:
        normalized = brand_name.strip().lower()
        # Fetch candidates and compare in Python — avoids DB-specific
        # trimming behaviour and handles extra whitespace.
        candidates = db.query(Brand).filter(
            Brand.brand_name.ilike(f"%{brand_name.strip()}%")
        ).all()
        sentiment_brand = next(
            (b for b in candidates if b.brand_name.strip().lower() == normalized),
            None,
        )
        # Last resort: any ilike hit is better than nothing
        if not sentiment_brand and candidates:
            sentiment_brand = candidates[0]

    if not sentiment_brand:
        logger.info(
            "[improvement] no sentiment Brand found for name=%r url=%r",
            brand_name, website_url,
        )
        return None

    try:
        analysis = (
            db.query(SentimentAnalysis)
            .filter(SentimentAnalysis.brand_id == sentiment_brand.brand_id)
            .order_by(SentimentAnalysis.analysis_date.desc())
            .first()
        )
    except Exception as exc:
        logger.warning(
            "[improvement] SentimentAnalysis query failed for brand_id=%s: %s",
            sentiment_brand.brand_id, exc,
        )
        return None

    if not analysis:
        logger.info(
            "[improvement] no SentimentAnalysis rows for brand_id=%s (brand=%r)",
            sentiment_brand.brand_id, sentiment_brand.brand_name,
        )
        return None

    data = analysis.analysis_data or {}
    logger.info(
        "[improvement] found sentiment analysis %s for %r (%d reviews)",
        analysis.analysis_id, sentiment_brand.brand_name, analysis.review_count or 0,
    )
    return {
        "total_reviews": analysis.review_count or 0,
        "overall_sentiment_score": analysis.overall_sentiment_score,
        "dominant_emotion": analysis.dominant_emotion,
        "sentiment_summary": data.get("sentiment_summary"),
        "pain_points": data.get("pain_points", []),
        "desires": data.get("desires", []),
        "loved": data.get("loved", []),
        "emotions": data.get("emotions", {}),
        "keywords": data.get("keywords", []),
        "platforms": data.get("platforms", {}),
    }


def _latest_seo_audit(db: Session, user_id: str, brand_profile_id: int) -> dict | None:
    """Most recent SEO audit for this brand."""
    try:
        audit = (
            db.query(SEOAuditResult)
            .filter(
                SEOAuditResult.user_id == user_id,
                SEOAuditResult.brand_profile_id == brand_profile_id,
            )
            .order_by(SEOAuditResult.created_at.desc())
            .first()
        )
        if not audit:
            return None

        def _issue_summary(issues: list | None) -> dict:
            if not issues:
                return {"total": 0}
            counts = {"Good": 0, "Warning": 0, "Needs Work": 0}
            for item in issues:
                sev = item.get("severity", "Warning")
                counts[sev] = counts.get(sev, 0) + 1
            sample = [
                {"product": i.get("product_name"), "issue": i.get("issue")}
                for i in issues[:5]
            ]
            return {"total": len(issues), "breakdown": counts, "sample_issues": sample}

        return {
            "seo_score": audit.seo_score,
            "title_score": audit.title_score,
            "description_score": audit.description_score,
            "image_alt_score": audit.image_alt_score,
            "keyword_score": audit.keyword_score,
            "tags_score": audit.tags_score,
            "total_products_audited": audit.total_products_audited,
            "total_catalogue_products": audit.total_catalogue_products,
            "good_count": audit.good_count,
            "warning_count": audit.warning_count,
            "needs_work_count": audit.needs_work_count,
            "title_issues": _issue_summary(audit.title_issues),
            "description_issues": _issue_summary(audit.description_issues),
            "image_alt_issues": _issue_summary(audit.image_alt_issues),
            "keyword_issues": _issue_summary(audit.keyword_issues),
            "tags_issues": _issue_summary(audit.tags_issues),
        }
    except Exception as e:
        logger.warning("[improvement] SEO audit data unavailable: %s", e)
        return None


def _latest_keywords(db: Session, user_id: str, brand_profile_id: int) -> list | None:
    """Most recent keyword suggestions for this brand."""
    try:
        kw = (
            db.query(SEOKeywordSuggestion)
            .filter(
                SEOKeywordSuggestion.user_id == user_id,
                SEOKeywordSuggestion.brand_profile_id == brand_profile_id,
            )
            .first()
        )
        if not kw or not kw.keywords:
            return None
        return kw.keywords
    except Exception as e:
        logger.warning("[improvement] keyword data unavailable: %s", e)
        return None


# Numeric part of a stored price string. The scraper deliberately keeps the
# store's own currency on the value (a hardcoded symbol used to be a bug — see
# extractor.py), so every price arrives prefixed: "Rs. 180000.00", "$ 34.00".
# Grabbing split()[0] took the SYMBOL and threw on every single product.
_PRICE_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _parse_price(raw) -> float | None:
    """First numeric value in a price string, or None if there isn't one."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = _PRICE_NUMBER_RE.search(str(raw))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _has_image(product: dict) -> bool:
    """
    Does this product have an image?

    ``image_url`` is the key EVERY scraper path writes — shopify_api,
    woocommerce_api, woocommerce_html, nextjs_json and jsonld all emit it.
    This used to check ``image``/``images``, which no path has ever written,
    so every product counted as missing and the module confidently told shop
    owners "none of your products have photos" about fully-illustrated stores.
    The other two keys are tolerated only as a cheap guard for legacy rows.
    """
    if (product.get("image_url") or "").strip():
        return True
    if (product.get("image") or "").strip():
        return True
    images = product.get("images")
    return bool(images) if isinstance(images, list) else False


def _product_stats(products: list) -> dict | None:
    """
    Compute summary statistics from the product catalogue.

    Every field here is read by the LLM and repeated to the shop owner as
    fact, so a field-name mismatch does not degrade quietly — it fabricates a
    high-priority problem. Keys must match the scraper's schema exactly:
    ``name, price, description, image_url, image_alt, category, tags, vendor``.
    """
    if not products:
        return None

    total = len(products)
    missing_desc = sum(
        1 for p in products
        if not (p.get("description") or "").strip()
    )

    with_images = sum(1 for p in products if _has_image(p))
    missing_images = total - with_images

    # ── Alt text — measured SEPARATELY from image presence ──────────────
    # These are two different things and must never be merged: a product can
    # have a perfectly good photo and still have no text description on it.
    #
    # Only the shopify_api path records "image_alt". For a product scraped by
    # any other path the field is absent, which means UNKNOWN, not missing —
    # counting those as missing would invent a false finding, the exact bug
    # this function is being fixed for. So the denominator is the products we
    # could actually measure, and when that is zero we report nothing at all.
    alt_checked = [p for p in products if "image_alt" in p and _has_image(p)]
    missing_alt = sum(1 for p in alt_checked if not (p.get("image_alt") or "").strip())

    prices = [v for v in (_parse_price(p.get("price")) for p in products) if v is not None]

    stats = {
        "total_products": total,
        "missing_descriptions": missing_desc,
        "missing_descriptions_pct": round(missing_desc / total * 100, 1) if total else 0,
        "products_with_images": with_images,
        "missing_images": missing_images,
        "missing_images_pct": round(missing_images / total * 100, 1) if total else 0,
        "products_with_price": len(prices),
        "price_range": {
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "avg": round(sum(prices) / len(prices), 2) if prices else None,
        },
        "has_prices": len(prices) > 0,
    }

    if alt_checked:
        stats["images_checked_for_alt_text"] = len(alt_checked)
        stats["missing_image_alt_text"] = missing_alt
        stats["missing_image_alt_text_pct"] = round(missing_alt / len(alt_checked) * 100, 1)

    return stats


def gather_brand_context(
    db: Session,
    user_id: str,
    brand_profile_id: int,
) -> dict[str, Any]:
    """
    Gather ALL available data for this brand into one structured context.

    Missing sources are set to "not_available" — the LLM prompt handles this
    by producing no suggestions for that area.
    """
    # 1. Brand profile (required)
    profile = (
        db.query(BrandProfile)
        .filter(
            BrandProfile.id == brand_profile_id,
            BrandProfile.user_id == user_id,
        )
        .first()
    )
    if not profile:
        return {"error": "Brand profile not found."}

    brand_name = profile.business_name or profile.website_url or "Unknown"
    products = profile.products or []

    context: dict[str, Any] = {
        "brand_name": brand_name,
        "business_description": profile.description or "not_available",
        "product_categories": profile.product_categories or [],
        "price_range": profile.price_range or "not_available",
        "target_audience": profile.target_audience or "not_available",
        "store_country": profile.store_country or "not_available",
        "platform": profile.platform or "not_available",
        "product_stats": _product_stats(products) or "not_available",
    }

    # 2. Sentiment (optional) — match by website_url first, name fallback
    sentiment = _latest_sentiment(db, brand_name, website_url=profile.website_url)
    context["sentiment"] = sentiment if sentiment else "not_available"

    # 3. SEO audit (optional)
    audit = _latest_seo_audit(db, user_id, brand_profile_id)
    context["seo_audit"] = audit if audit else "not_available"

    # 4. SEO keywords (optional)
    keywords = _latest_keywords(db, user_id, brand_profile_id)
    context["seo_keywords"] = keywords if keywords else "not_available"

    return context


# ═══════════════════════════════════════
#  2. LLM PROMPT + CALL
# ═══════════════════════════════════════

# ── Shared language rules (used by BOTH prompts) ────────────────────────
_SHARED_PROMPT_RULES = """
══════════════════════════════════════════
  LANGUAGE RULES — READ CAREFULLY
══════════════════════════════════════════

1. NO JARGON. The shop owner is not a developer or marketer.
   BANNED WORDS (never use these in main text):
   - "alt text" → say "text descriptions attached to photos"
   - "meta description" / "meta tags" → say "the short summary Google shows under your store name"
   - "SEO score" → say "how easy it is for Google to find and show your products"
   - "characters" (as in title length) → say "words" or just describe the length naturally
   - "catalogue" → say "products" or "store"
   - "optimize" / "optimization" → say "improve" or "fix"
   - "accessibility" → say "so all shoppers can understand your products"
   - "conversion rate" → say "the number of visitors who actually buy"
   - "bounce rate" → say "people leaving your store without buying"
   - "schema markup" → say "extra details that help Google understand your products"
   If a technical idea is unavoidable, explain it in plain words right there.

2. NO RAW DATA in main text. Raw numbers, percentages, and field
   names belong ONLY in the "evidence" field.
   BAD:  "missing_image_alt_text_pct: 100.0 — add alt text to improve SEO score"
   GOOD: "None of your product photos have descriptions, so Google can't
          show them in search results and some shoppers can't tell what the
          photo shows."

3. WARM and CONVERSATIONAL. Write like you're texting a friend who asked for
   help with their shop. Use "your" and "you". Be specific but kind.

══════════════════════════════════════════
  PHOTOS vs PHOTO DESCRIPTIONS — DIFFERENT
══════════════════════════════════════════

These are TWO SEPARATE facts in the data. Never merge them, and never read
one as the other:

  "missing_images"            = products with NO PHOTO AT ALL.
  "missing_image_alt_text"    = products that HAVE a photo, but the photo has
                                no text description attached to it.

If "missing_images" is 0, every product HAS a photo. Do NOT say or imply the
shop is missing photos — that would be false, and telling a shop owner a
problem they do not have destroys their trust in everything else you say.
A high "missing_image_alt_text" alongside "missing_images": 0 means the
photos are all there and only the descriptions are absent.

  ✗ FALSE: "None of your products have photos."          (when missing_images is 0)
  ✓ TRUE:  "Your photos are all in place, but none of them have the short
            text descriptions that tell Google — and shoppers using screen
            readers — what each photo shows."

══════════════════════════════════════════
  PROBLEM vs SUGGESTION — MUST BE DIFFERENT
══════════════════════════════════════════

These are two SEPARATE ideas. If they say the same thing, the output is broken.

  "problem" = WHAT IS WRONG and WHY IT HURTS.
  Describe the issue and its impact on their business. Do NOT say what to do.

  "suggestion" = WHAT TO DO ABOUT IT.
  Give a clear, specific action step. Do NOT repeat the problem.

  ✗ WRONG (identical / overlapping):
    problem:    "Your products don't have photos."
    suggestion: "Add photos to your products."

  ✓ RIGHT (genuinely different):
    problem:    "None of your products have photos, so customers can't see
                 what they're buying before ordering — this is one of the
                 biggest reasons people leave a store without buying."
    suggestion: "Take 2-3 clear photos of each product in natural light. Even
                 phone photos work well — the key is that customers can see
                 colours, texture, and detail before they click 'add to cart'."

  ✓ ANOTHER GOOD EXAMPLE:
    problem:    "Many of your product titles are very short — just a name or
                 a code. This means Google has trouble understanding what you
                 sell, and customers browsing your store can't quickly tell
                 what each item is."
    suggestion: "Make each title a short sentence that describes the item.
                 For example, instead of 'Lawn-001' try 'Embroidered Lawn
                 Suit — 3 Piece with Dupatta'. A few extra words make a big
                 difference for both Google and your customers."
"""

# ── Output language ─────────────────────────────────────────────────────
#
# English is the default and costs NOTHING: its rule block is empty, so an
# English prompt is byte-identical to what it was before the toggle existed.
# Only Roman Urdu pays the ~250 extra prompt tokens — on the OpenAI lane
# that is a fraction of a cent and no extra wait at all.
#
# The examples below are not decoration. Asking an LLM for "Roman Urdu" on
# its own reliably produces one of two failure modes: stilted literary Urdu
# transliterated word-for-word, or English with a few Urdu words sprinkled in.
# Concrete sentences in the target register are what actually pin the style.
DEFAULT_LANGUAGE = "english"

_ROMAN_URDU_RULES = """
══════════════════════════════════════════
  OUTPUT LANGUAGE — ROMAN URDU (IMPORTANT)
══════════════════════════════════════════

Write ALL human-facing text in ROMAN URDU: natural, everyday Urdu written in
English (Latin) letters — the way a Pakistani shop owner actually texts.

  * Latin letters ONLY. NEVER use Urdu script (اردو).
  * Simple spoken Urdu, warm and friendly — NOT formal or literary Urdu.
    Avoid heavy words like "mutasir", "behtari", "iqdamat", "tajaweez".
  * Common English business words are NATURAL — keep them in English:
    product, delivery, quality, discount, customer, order, website, photo,
    price, title, review, size, stock, brand, page, search.
  * Do NOT write mostly-English sentences with one or two Urdu words. The
    sentence structure itself must be Urdu.

WRITE EXACTLY IN THIS STYLE:

  problem:    "Aapke bohat se product titles bohat chhote hain, is liye
               customers ko theek se samajh nahi aata ke aap kya bech rahe
               hain — aur Google ko bhi aapke products dhoondne mein
               mushkil hoti hai."
  suggestion: "Har title ko ek chhota sa jumla bana dein jo item ko describe
               kare. Jaise 'Lawn-001' ki jagah 'Embroidered Lawn Suit — 3
               Piece with Dupatta'. Thore se extra words se bohat farq parta
               hai."

  opportunity: "Customers aapki fabric quality ko bohat pasand karte hain —
                yehi aapke brand ki sab se bari khoobi hai."
  what_to_do:  "Fabric quality ko apni marketing ka main point banayein.
                Close-up photos lagayein aur har product title mein iska
                zikar karein."

  problem:    "Aapke kisi bhi product ki photo nahi lagi hui, is liye
               customers ko pata hi nahi chalta ke wo kya khareed rahe hain
               aur wo bina order kiye chale jaate hain."

DO NOT TRANSLATE THESE — leave them exactly as they are:
  * The "evidence" field — it stays in ENGLISH with its original numbers,
    percentages and review quotes ("73.9% of reviews", "500 title issues",
    "'excellent fabric' in 38 reviews"). Numbers are proof, not prose.
  * The "area", "priority" and "confidence" values — these are fixed codes
    (high/medium/low, images, delivery, ...), never words for the reader.

Everything else the shop owner reads — problem, suggestion, opportunity,
what_to_do, insufficient_data_reason — MUST be Roman Urdu.
"""

_LANGUAGE_RULES: dict[str, str] = {
    # Empty on purpose: English adds zero tokens to the prompt.
    "english": "",
    "roman_urdu": _ROMAN_URDU_RULES,
}


def normalise_language(value: str | None) -> str:
    """
    Map whatever arrived from the client to a language we actually support.

    Whitelist, not sanitisation: the request value selects a prompt block we
    wrote, it never reaches the model as free text. An unknown value quietly
    becomes English rather than failing the request.
    """
    key = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in _LANGUAGE_RULES:
        return key
    if key in {"urdu", "romanurdu", "ur", "roman"}:
        return "roman_urdu"
    if key and key != DEFAULT_LANGUAGE:
        _warn_unknown_language(key)
    return DEFAULT_LANGUAGE


_warned_languages: set[str] = set()


def _warn_unknown_language(key: str) -> None:
    if key not in _warned_languages:
        _warned_languages.add(key)
        logger.warning(
            "[improvement] unknown language %r — falling back to %s. Known: %s",
            key, DEFAULT_LANGUAGE, sorted(_LANGUAGE_RULES),
        )


# ── Suggestions prompt (fix-it: problems to solve) ──────────────────────
_SUGGESTIONS_PROMPT_TEMPLATE = """You are a friendly, knowledgeable brand advisor talking directly to a shop owner
over coffee. You will receive REAL data about their brand. Your job is to explain
what PROBLEMS you found and give practical, specific advice to fix them.
{_SHARED_PROMPT_RULES}{language_rules}
══════════════════════════════════════════
  DATA ACCURACY RULES
══════════════════════════════════════════

1. Every suggestion MUST be grounded in a SPECIFIC data point from the input.
   The exact number, percentage, or quote goes in the "evidence" field.
2. Do NOT invent problems. If the data does not show a problem, do NOT suggest a fix.
3. Do NOT give generic advice unless the data specifically supports it.
4. If a section is marked "not_available", produce ZERO suggestions about that area.
5. Confidence MUST reflect data volume:
   - "high": backed by 50+ reviews or a full SEO audit of 100+ products
   - "medium": 10-49 reviews, or partial SEO data
   - "low": fewer than 10 reviews, or very limited data
6. Priority reflects business impact:
   - "high": large data pattern or critical issue (e.g. 60%+ products affected)
   - "medium": notable pattern worth addressing
   - "low": minor improvement opportunity
7. If there is not enough data to make ANY confident suggestions, return an
   empty suggestions array and explain what data is missing in the
   "insufficient_data_reason" field.
8. Area must be one of: "delivery", "product_quality", "customer_service",
   "pricing", "seo", "product_descriptions", "images", "tags", "product_range",
   "brand_positioning", "website".
9. Return between 3 and 12 suggestions. Quality over quantity.

BRAND DATA:
{data_json}

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{{
  "suggestions": [
    {{
      "problem": "what is wrong and why it hurts — in plain, warm English (NOT the same as suggestion)",
      "suggestion": "what specifically to do — a clear action step (NOT a repeat of the problem)",
      "evidence": "the exact data point that proves this is real (numbers, quotes, scores)",
      "priority": "high|medium|low",
      "area": "delivery|product_quality|customer_service|pricing|seo|product_descriptions|images|tags|product_range|brand_positioning|website",
      "confidence": "high|medium|low"
    }}
  ],
  "insufficient_data_reason": null
}}"""

# ── Growth opportunities prompt (forward-looking: strengths to amplify) ─────
_GROWTH_PROMPT_TEMPLATE = """You are a friendly, knowledgeable brand advisor talking directly to a shop owner
over coffee. You will receive REAL data about their brand. Your job is to spot
GROWTH OPPORTUNITIES — positive, forward-looking ideas to help the brand grow
sales, grounded in real data.
{_SHARED_PROMPT_RULES}{language_rules}
══════════════════════════════════════════
  GROWTH OPPORTUNITIES — WHAT TO LOOK FOR
══════════════════════════════════════════

Growth opportunities are DIFFERENT from fix-it suggestions:
  - Suggestions = what's WRONG and how to fix it.
  - Growth opportunities = what's WORKING (or missing) and how to GROW.

Each growth idea must be grounded in REAL data from the input:

  ✓ FROM SENTIMENT STRENGTHS:
    opportunity: "Customers keep praising your fabric quality — it's the
                  thing they love most about your brand."
    what_to_do:  "Make fabric quality the centerpiece of your marketing.
                  Show close-up shots of the fabric, mention it in every
                  product title, and tell the story of how it's sourced."
    evidence:    "'loved' mentions in 38 reviews: 'excellent fabric',
                  'premium quality material', 'soft and comfortable'."

  ✓ FROM SEO DEMAND GAPS:
    opportunity: "'Eid collection 2026' is searched thousands of times
                  but your store has no page or products targeting it."
    what_to_do:  "Create a dedicated Eid collection landing page and
                  tag your festive products there before the season peaks."
    evidence:    "Keyword 'eid collection' — search volume 12,000/mo,
                  your store has 0 products tagged with it."

  ✓ FROM PRODUCT CATALOGUE GAPS:
    opportunity: "You only have 3 products in accessories, but your
                  customers mention wanting matching items in reviews."
    what_to_do:  "Consider expanding your accessories range — customers
                  are already asking for it, so demand is there."
    evidence:    "3 accessories out of 85 total products; 7 reviews
                  mention 'wish they had matching shoes/dupatta'."

  ✓ CROSS-DATA (best kind):
    opportunity: "Customers love your embroidery (mentioned in 20+ reviews)
                  and 'embroidered lawn' has high search demand, yet your
                  SEO titles rarely highlight the embroidery work."
    what_to_do:  "Add 'embroidered' to your product titles and descriptions
                  — it's both what buyers search for AND what your customers
                  rave about. Double win."
    evidence:    "'embroidered' in 23 loved-mentions, keyword 'embroidered
                  lawn suit' volume 8,100/mo, only 2 of 40 titles include it."

BANNED GENERIC GROWTH ADVICE (never say these unless data specifically supports it):
  ✗ "Post more on social media"
  ✗ "Run paid ads" or "use influencers"
  ✗ "Offer discounts"
  ✗ "Improve your brand presence"
  ✗ "Expand to new markets"
  If the data doesn't point to a specific opportunity, return an empty
  growth_opportunities array. NO FILLER.

Growth fields:
  "opportunity" = WHY this is a chance to grow (what strength, gap, or demand)
  "what_to_do"  = WHAT action to take to capture it
  These must be DIFFERENT sentences (not overlapping).

══════════════════════════════════════════
  DATA ACCURACY RULES
══════════════════════════════════════════

1. Every growth idea MUST be grounded in a SPECIFIC data point from the input.
2. Do NOT invent opportunities. If the data doesn't support one, don't suggest it.
3. Do NOT give generic advice ("post more on social media") without specific data.
4. If a section is marked "not_available", produce ZERO growth ideas about that area.
5. Confidence MUST reflect data volume (same scale as suggestions).
6. Priority reflects business impact (same scale as suggestions).
7. If there is not enough data for ANY growth ideas, return an empty array.
8. Area must be one of: "delivery", "product_quality", "customer_service",
   "pricing", "seo", "product_descriptions", "images", "tags", "product_range",
   "brand_positioning", "website".
9. Return between 0 and 6 growth opportunities. Zero is fine if nothing is
   genuinely supported by the data.

BRAND DATA:
{data_json}

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{{
  "growth_opportunities": [
    {{
      "opportunity": "why this is a chance to grow — the strength, gap, or demand you spotted",
      "what_to_do": "what specific action to take — clear next step (NOT a repeat of opportunity)",
      "evidence": "the exact data point that proves this opportunity is real",
      "priority": "high|medium|low",
      "area": "delivery|product_quality|customer_service|pricing|seo|product_descriptions|images|tags|product_range|brand_positioning|website",
      "confidence": "high|medium|low"
    }}
  ],
  "insufficient_data_reason": null
}}"""


def _text_overlap(a: str, b: str) -> float:
    """
    Jaccard-like word overlap between two strings.

    Returns 0.0 (no overlap) to 1.0 (identical).  Used to detect when the
    LLM produced the same sentence for both "problem" and "suggestion".
    """
    # Roman Urdu function words belong here for the same reason the English
    # ones do. Without them, two genuinely different Roman Urdu sentences
    # share "hai / ke / ko / se / mein / aur" and score as near-duplicates,
    # so good items get silently dropped by the overlap filter below.
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "are",
            "for", "it", "this", "that", "your", "you", "with", "on", "by",
            "aap", "aapke", "aapki", "aapka", "ke", "ki", "ka", "ko", "se",
            "mein", "hai", "hain", "aur", "ye", "yeh", "wo", "jo", "bhi",
            "par", "kar", "karein", "ho", "nahi", "liye", "is", "us", "kya"}
    wa = set(w for w in a.lower().split() if w not in stop)
    wb = set(w for w in b.lower().split() if w not in stop)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _try_repair_json(text: str) -> dict | None:
    """
    Salvage a truncated JSON response by rewinding to the last clean boundary.

    The previous version trimmed at most 200 characters off the end. That
    failed exactly when it mattered most: when the cut landed deep inside a
    long "evidence" string, recovery needs to rewind past the whole partial
    value AND its key — routinely 800+ characters — so repair gave up and the
    whole call was discarded.

    This walks the text once and records every index where a value closed
    cleanly outside of a string. Those are the only safe cut points, and the
    rewind distance is unbounded, so a cut anywhere still recovers whatever
    complete items came before it. Candidates are tried newest-first so we
    keep as many items as possible; ``json.loads`` is the final arbiter of
    whether a candidate is actually valid.
    """
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    stack: list[str] = []
    # (cut index, bracket stack still open at that point)
    safe: list[tuple[int, tuple[str, ...]]] = []
    in_str = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            if not in_str:
                safe.append((i + 1, tuple(stack)))
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and ((ch == "}" and stack[-1] == "{")
                          or (ch == "]" and stack[-1] == "[")):
                stack.pop()
            safe.append((i + 1, tuple(stack)))

    for cut, open_stack in reversed(safe):
        candidate = text[:cut].rstrip().rstrip(",")
        closers = "".join("}" if o == "{" else "]" for o in reversed(open_stack))
        try:
            parsed = json.loads(candidate + closers)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_content(result: dict, call_type: str) -> tuple[str, bool]:
    """
    Pull the completion text out of a raw Groq response.

    Returns ``(text, truncated)`` where ``truncated`` means the model stopped
    because it hit its output ceiling (``finish_reason == "length"``), NOT
    because it produced bad JSON.

    This module used to read ``content`` straight out of the dict and never
    look at ``finish_reason``, so a token-limit cutoff surfaced downstream as
    "Unterminated string" — a JSON syntax error for what is actually a budget
    problem. That mislabelling is what sent this bug hunting in the wrong
    direction for so long.
    """
    choices = result.get("choices") or []
    if not choices:
        raise TruncatedCompletionError(
            f"{call_type} returned no choices."
        )

    finish_reason = choices[0].get("finish_reason")
    text = ((choices[0].get("message") or {}).get("content") or "").strip()

    usage = result.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    logger.info(
        "[improvement] %s: finish_reason=%s prompt=%s completion=%s "
        "(reasoning=%s visible=%s)",
        call_type, finish_reason,
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
        details.get("reasoning_tokens"),
        (usage.get("completion_tokens") or 0) - (details.get("reasoning_tokens") or 0),
    )

    if not text and finish_reason != "length":
        raise TruncatedCompletionError(
            f"{call_type} returned empty content — the model produced no output."
        )

    return text, finish_reason == "length"


def _parse_llm_response(result: dict, call_type: str) -> dict:
    """
    Extract text from Groq response, parse JSON, validate items.

    Returns a dict with the relevant list key ("suggestions" or
    "growth_opportunities") populated with validated items.  On failure
    returns an empty dict — caller adds insufficient_data_reason.
    """
    text, _truncated = _extract_content(result, call_type)
    text = text.replace("```json", "").replace("```", "").strip()

    # Try strict parse first, then repair, then give up
    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.info(
            "[improvement] %s JSON incomplete (%s), attempting repair…",
            call_type, exc,
        )
        parsed = _try_repair_json(text)
        if isinstance(parsed, dict):
            logger.info("[improvement] %s: repair recovered the response", call_type)
    if not isinstance(parsed, dict):
        logger.warning("[improvement] %s: JSON parse/repair failed", call_type)
        return {}

    valid_areas = {
        "delivery", "product_quality", "customer_service", "pricing",
        "seo", "product_descriptions", "images", "tags",
        "product_range", "brand_positioning", "website",
    }

    # ── Validate suggestions ──────────────────────────────────────────
    if call_type == "suggestions":
        items = parsed.get("suggestions", [])
        if not isinstance(items, list):
            items = []
        clean = []
        for s in items:
            if not isinstance(s, dict):
                continue
            if not s.get("suggestion") or not s.get("evidence"):
                continue
            if not s.get("problem"):
                s["problem"] = s["suggestion"]
            if _text_overlap(s["problem"], s["suggestion"]) > 0.65:
                logger.info(
                    "[improvement] dropping near-duplicate suggestion "
                    "(overlap %.0f%%): problem=%r  suggestion=%r",
                    _text_overlap(s["problem"], s["suggestion"]) * 100,
                    s["problem"][:60], s["suggestion"][:60],
                )
                continue
            s["area"] = s.get("area", "website") if s.get("area") in valid_areas else "website"
            s["priority"] = s.get("priority", "medium") if s.get("priority") in {"high", "medium", "low"} else "medium"
            s["confidence"] = s.get("confidence", "medium") if s.get("confidence") in {"high", "medium", "low"} else "medium"
            clean.append(s)
        return {"suggestions": clean, "insufficient_data_reason": parsed.get("insufficient_data_reason")}

    # ── Validate growth opportunities ─────────────────────────────────
    if call_type == "growth":
        items = parsed.get("growth_opportunities", [])
        if not isinstance(items, list):
            items = []
        clean = []
        for g in items:
            if not isinstance(g, dict):
                continue
            if not g.get("what_to_do") or not g.get("evidence"):
                continue
            if not g.get("opportunity"):
                g["opportunity"] = g["what_to_do"]
            if _text_overlap(g["opportunity"], g["what_to_do"]) > 0.65:
                logger.info(
                    "[improvement] dropping near-duplicate growth idea "
                    "(overlap %.0f%%): opportunity=%r  what_to_do=%r",
                    _text_overlap(g["opportunity"], g["what_to_do"]) * 100,
                    g["opportunity"][:60], g["what_to_do"][:60],
                )
                continue
            g["area"] = g.get("area", "brand_positioning") if g.get("area") in valid_areas else "brand_positioning"
            g["priority"] = g.get("priority", "medium") if g.get("priority") in {"high", "medium", "low"} else "medium"
            g["confidence"] = g.get("confidence", "medium") if g.get("confidence") in {"high", "medium", "low"} else "medium"
            clean.append(g)
        return {"growth_opportunities": clean, "insufficient_data_reason": parsed.get("insufficient_data_reason")}

    return {}


def _call_llm(context: dict, call_type: str, language: str = DEFAULT_LANGUAGE) -> dict:
    """
    Send brand context to Groq with a task-specific prompt.

    ``call_type``:
      - "suggestions"  → fix-it suggestions prompt
      - "growth"       → growth opportunities prompt

    ``language`` picks the output-language rule block ("english" adds nothing
    to the prompt; "roman_urdu" adds the style block with worked examples).

    Key selection is llm_config's job now.  The "improvement" purpose sits on
    the alt key slot, so it stays off the busy main key — but if that key is
    rate limited, llm_config transparently fails over to the other one instead
    of stalling.  Previously this pinned ``GROKAPIKEYSentiment`` by name, which
    silently returned no suggestions once that variable was renamed.

    Returns parsed items dict, or empty dict on failure.
    """
    language_rules = _LANGUAGE_RULES.get(language, "")
    key, model = get_groq_config("improvement")
    if not key:
        logger.warning(
            "[improvement] no Groq key configured — set GROQ_API_KEY (and "
            "optionally GROKAPIKEY2 for a second rate-limit budget)"
        )
        return {}

    # Normalise context for the prompt
    data_for_prompt = {}
    for section, value in context.items():
        if value == "not_available" or value is None:
            data_for_prompt[section] = "not_available"
        else:
            data_for_prompt[section] = value

    data_json = json.dumps(data_for_prompt, indent=2, default=str, ensure_ascii=False)
    if len(data_json) > 12000:
        data_json = data_json[:12000] + "\n... (truncated)"

    # Pick template
    # The system message states the register too — the model follows the
    # language instruction far more reliably when it appears in both places.
    if language == "roman_urdu":
        voice = (
            "You write the shop owner's text in ROMAN URDU — everyday Urdu in "
            "English letters, never Urdu script — while leaving the 'evidence' "
            "field in English with its original numbers."
        )
    else:
        voice = (
            "You write in simple, everyday English — never technical jargon or "
            "raw field names."
        )

    if call_type == "growth":
        prompt = _GROWTH_PROMPT_TEMPLATE.format(
            _SHARED_PROMPT_RULES=_SHARED_PROMPT_RULES,
            language_rules=language_rules,
            data_json=data_json,
        )
        system_msg = (
            "You are a warm, knowledgeable brand advisor who spots genuine "
            "growth opportunities for business owners. You ONLY suggest ideas "
            "backed by real data. You NEVER invent opportunities or give "
            "generic advice like 'post more on social media'. " + voice
        )
        what = "brand growth opportunities"
    else:
        prompt = _SUGGESTIONS_PROMPT_TEMPLATE.format(
            _SHARED_PROMPT_RULES=_SHARED_PROMPT_RULES,
            language_rules=language_rules,
            data_json=data_json,
        )
        system_msg = (
            "You are a warm, friendly brand advisor who talks to business "
            "owners like a trusted friend. You ONLY make suggestions backed "
            "by real data. You NEVER invent problems or generic advice. " + voice
        )
        what = "brand improvement suggestions"


    def _send(max_tokens: int) -> dict:
        """
        Ek LLM call — chat_completion ke zariye, lane failover ke saath.

        PEHLE yahan apna raw-POST loop tha jo configured_key_envs() par
        ghoomta aur URL mein api.groq.com hardcode karta tha. Us ka matlab ye
        tha ke ye module llm_config ki lanes se BAHAR chal raha tha — yani
        "improvement" ko OpenAI lane par bhejne se yahan kuch na hota.
        Ab wahi routing baaqi sab ke saath share hoti hai.

        _TokenPacer bhi hata diya: wo Groq ke 8,000 TPM ko latency mein badal
        deta tha (yehi is page ke lambe wait ki asal wajah thi). Ab pehli lane
        OpenAI hai jahan ye ceiling hai hi nahi, aur Groq fallback par
        llm_config ka apna cooling/failover kaafi hai.
        """
        return chat_completion(
            "improvement",
            {
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
                # gpt-oss burns ~1,000 tokens on invisible reasoning at the
                # default effort, leaving too little of max_tokens for the
                # JSON itself. "low" measured 196 reasoning tokens instead of
                # 977 on this exact prompt. On the OpenAI lane this param is
                # stripped automatically (adapt_payload) — gpt-4o-mini has no
                # reasoning phase and would 400 on it.
                **reasoning_params(model, "low"),
            },
            timeout=90,
            what=what,
        )

    try:
        result = _send(_MAX_TOKENS)
        _text, truncated = _extract_content(result, call_type)

        # A real token-limit hit — say so, and give it one honest retry with a
        # bigger ceiling instead of pretending the JSON was malformed.
        if truncated:
            logger.warning(
                "[improvement] %s hit its output limit (max_tokens=%d) — "
                "retrying once with max_tokens=%d",
                call_type, _MAX_TOKENS, _MAX_TOKENS_RETRY,
            )
            result = _send(_MAX_TOKENS_RETRY)
            _text, truncated = _extract_content(result, call_type)
            if truncated:
                # Still cut off. Salvage the complete items rather than
                # discarding the whole call.
                logger.warning(
                    "[improvement] %s still truncated at max_tokens=%d — "
                    "salvaging complete items",
                    call_type, _MAX_TOKENS_RETRY,
                )

        return _parse_llm_response(result, call_type)

    except RateLimitedError:
        raise  # propagate to route → 429
    except TruncatedCompletionError as e:
        logger.warning("[improvement] %s: %s", call_type, e)
        return {}
    except Exception as e:
        logger.warning("[improvement] %s LLM call failed: %s", call_type, e)
        return {}


# ═══════════════════════════════════════
#  3. PUBLIC API
# ═══════════════════════════════════════

def generate_improvements(
    db: Session,
    user_id: str,
    brand_profile_id: int,
    language: str | None = DEFAULT_LANGUAGE,
) -> dict:
    """
    Main entry point: gather data → LLM → structured suggestions.

    Returns a dict with:
      - suggestions: list of suggestion objects
      - growth_opportunities: list of growth opportunity objects
      - data_sources_used: which data was available
      - data_available: bool — whether enough data exists
      - insufficient_data_reason: string or None
      - language: which language the human-facing text was written in

    ``language`` applies to BOTH calls, so a page never mixes languages.
    """
    language = normalise_language(language)
    context = gather_brand_context(db, user_id, brand_profile_id)

    if "error" in context:
        return {
            "suggestions": [],
            "growth_opportunities": [],
            "data_sources_used": [],
            "data_available": False,
            "insufficient_data_reason": context["error"],
            "language": language,
        }

    # Check how many data sources are actually available
    sources_available = []
    if context.get("sentiment") != "not_available":
        sources_available.append("sentiment")
    if context.get("seo_audit") != "not_available":
        sources_available.append("seo_audit")
    if context.get("seo_keywords") != "not_available":
        sources_available.append("seo_keywords")
    if context.get("product_stats") != "not_available":
        sources_available.append("products")

    if not sources_available:
        return {
            "suggestions": [],
            "growth_opportunities": [],
            "data_sources_used": [],
            "data_available": False,
            "insufficient_data_reason": (
                "No data available yet. Please run web scraping to set up your brand, "
                "then optionally run sentiment analysis and SEO audit for richer suggestions."
            ),
            "language": language,
        }

    # ── Two separate LLM calls (avoids truncation of combined output) ───
    #
    # Ab ye SAATH chalti hain, ek ke baad ek nahi. Dono ka input wahi `context`
    # hai aur ek doosre par depend nahi karteen, is liye serialize karne ki koi
    # wajah nahi thi — sirf Groq ki TPM ceiling thi, jo hamein rok deti thi.
    # OpenAI lane par wo ceiling nahi hai, to is page ka wait ~aadha ho jata
    # hai (do 1,500-token calls ek saath).
    #
    # Groq par gir jayen (OpenAI cap/key na ho) to bhi ye theek hai:
    # llm_config ka key pool 429 par doosri lane par foran shift kar deta hai.
    with ThreadPoolExecutor(max_workers=2) as pool:
        sugg_future = pool.submit(_call_llm, context, "suggestions", language)
        growth_future = pool.submit(_call_llm, context, "growth", language)
        # RateLimitedError yahan se bhi waise hi upar jati hai jaise pehle
        # sequential calls se jati thi — route use 429 mein badalti hai.
        sugg_result = sugg_future.result()
        growth_result = growth_future.result()

    suggestions = sugg_result.get("suggestions", [])
    growth_opportunities = growth_result.get("growth_opportunities", [])

    # Merge insufficient_data_reason from both calls
    reasons = []
    if sugg_result.get("insufficient_data_reason"):
        reasons.append(sugg_result["insufficient_data_reason"])
    if growth_result.get("insufficient_data_reason"):
        reasons.append(growth_result["insufficient_data_reason"])
    # If both calls failed entirely, tell the user
    if not suggestions and not growth_opportunities and not sugg_result and not growth_result:
        reasons.append("AI generation failed — please try again.")

    return {
        "suggestions": suggestions,
        "growth_opportunities": growth_opportunities,
        "data_sources_used": sources_available,
        "data_available": True,
        "insufficient_data_reason": "; ".join(reasons) if reasons else None,
        "brand_name": context.get("brand_name", "Unknown"),
        "language": language,
    }
