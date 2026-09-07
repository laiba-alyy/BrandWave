"""
Brand context for the in-app AI Assistant.

The assistant used to know NOTHING about the user's brand — it had six
hardcoded paragraphs about how the modules work and a system-prompt line that
told it to deflect if asked about real data. This module gives it the small,
true summary it needs to answer "who is my brand for?" and "what are my
customers complaining about?".

TWO HARD RULES, both learned the expensive way elsewhere in this codebase:

1. SMALL. This block is prepended to EVERY message in a chat, so its cost is
   paid over and over. Never put the product list or raw reviews in here — the
   user already knows their own products, and a catalogue dump would blow the
   token budget exactly like the Brand Improvement truncation bug did. Brand
   identity plus short summaries only; every list is capped and every string
   is trimmed.

2. TRUTHFUL. A module the user has not run yet is reported as MISSING, by
   name, so the assistant can say "you haven't run sentiment yet" instead of
   inventing numbers. Silence would let the model guess. See
   ``missing_modules`` below.

Queries are deliberately REUSED from brand_improvement rather than rewritten:
``_latest_sentiment`` in particular carries a documented website_url-matching
fix, and duplicating it here would risk quietly reintroducing that bug.
"""

import logging

from sqlalchemy.orm import Session

from models.brand_profile import BrandProfile
from modules.brand_improvement.service import (
    _latest_keywords,
    _latest_seo_audit,
    _latest_sentiment,
    _product_stats,
)

logger = logging.getLogger(__name__)


# ── Size caps ─────────────────────────────────
# Tuned so the rendered block stays roughly 900-1,400 characters (~350 tokens)
# even for a brand with every module filled in.
_MAX_DESCRIPTION = 240
_MAX_AUDIENCE = 160
_MAX_CATEGORIES = 6
_MAX_PAIN_POINTS = 5
_MAX_LOVED = 5
_MAX_DESIRES = 3
_MAX_KEYWORDS = 10
_MAX_ITEM_CHARS = 90


def _trim(value, limit: int) -> str | None:
    """Single-line, length-capped string, or None if there's nothing to say."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _short_list(items, cap: int, item_chars: int = _MAX_ITEM_CHARS) -> list[str]:
    """Top ``cap`` entries, each trimmed. Handles str or {"...": ...} rows."""
    out: list[str] = []
    for raw in (items or [])[:cap]:
        if isinstance(raw, dict):
            raw = (
                raw.get("keyword")
                or raw.get("text")
                or raw.get("name")
                or raw.get("point")
                or next((v for v in raw.values() if isinstance(v, str)), None)
            )
        trimmed = _trim(raw, item_chars)
        if trimmed:
            out.append(trimmed)
    return out


def build_brand_context(
    db: Session,
    user_id: str,
    brand_profile_id: int | None,
) -> dict | None:
    """
    Compact, user-scoped snapshot of one brand for the assistant prompt.

    Returns None when there is no brand to talk about. The profile lookup
    filters on user_id AS WELL AS id, so passing someone else's
    brand_profile_id returns nothing rather than leaking their data.
    """
    if not brand_profile_id or not user_id:
        return None

    try:
        profile = (
            db.query(BrandProfile)
            .filter(
                BrandProfile.id == brand_profile_id,
                BrandProfile.user_id == user_id,   # ownership check — do not remove
            )
            .first()
        )
    except Exception as exc:
        logger.warning("[assistant] brand profile lookup failed: %s", exc)
        return None

    if not profile:
        logger.info(
            "[assistant] no brand %s owned by user %s", brand_profile_id, user_id
        )
        return None

    brand_name = profile.business_name or profile.website_url or "this brand"
    missing: list[str] = []

    context: dict = {
        "brand_name": brand_name,
        "website_url": profile.website_url,
        "description": _trim(profile.description, _MAX_DESCRIPTION),
        "target_audience": _trim(profile.target_audience, _MAX_AUDIENCE),
        "categories": _short_list(profile.product_categories, _MAX_CATEGORIES, 40),
        "price_range": _trim(profile.price_range, 40),
        "store_country": _trim(profile.store_country, 40),
        "platform": _trim(profile.platform, 30),
    }

    # ── Catalogue (free — no LLM, no extra query) ──────────────────────
    stats = _product_stats(profile.products or [])
    if stats:
        catalogue = {
            "total_products": stats["total_products"],
            "has_prices": stats["has_prices"],
            "price_range": stats["price_range"],
            "missing_descriptions": stats["missing_descriptions"],
            "missing_images": stats["missing_images"],
        }
        if "missing_image_alt_text" in stats:
            catalogue["missing_image_alt_text"] = stats["missing_image_alt_text"]
            catalogue["missing_image_alt_text_pct"] = stats["missing_image_alt_text_pct"]
        context["catalogue"] = catalogue
    else:
        missing.append("Brand Setup (no products scraped yet)")

    # ── Sentiment ──────────────────────────────────────────────────────
    sentiment = _latest_sentiment(db, brand_name, website_url=profile.website_url)
    if sentiment:
        context["sentiment"] = {
            "total_reviews": sentiment.get("total_reviews"),
            "overall_sentiment_score": sentiment.get("overall_sentiment_score"),
            "dominant_emotion": sentiment.get("dominant_emotion"),
            "summary": _trim(sentiment.get("sentiment_summary"), 220),
            "top_complaints": _short_list(sentiment.get("pain_points"), _MAX_PAIN_POINTS),
            "top_loved": _short_list(sentiment.get("loved"), _MAX_LOVED),
            "customer_desires": _short_list(sentiment.get("desires"), _MAX_DESIRES),
        }
    else:
        missing.append("Sentiment Analysis (not run yet)")

    # ── SEO audit ──────────────────────────────────────────────────────
    audit = _latest_seo_audit(db, user_id, brand_profile_id)
    if audit:
        context["seo_audit"] = {
            "seo_score": audit.get("seo_score"),
            "title_score": audit.get("title_score"),
            "image_alt_score": audit.get("image_alt_score"),
            "products_audited": audit.get("total_products_audited"),
            "needs_work_count": audit.get("needs_work_count"),
        }
    else:
        missing.append("SEO Audit (not run yet)")

    # ── Keywords ───────────────────────────────────────────────────────
    keywords = _latest_keywords(db, user_id, brand_profile_id)
    if keywords:
        context["top_keywords"] = _short_list(keywords, _MAX_KEYWORDS, 40)
    else:
        missing.append("SEO Keywords (not generated yet)")

    context["missing_modules"] = missing
    return context


def render_brand_block(context: dict | None) -> str:
    """
    Turn the context dict into the compact text the system prompt carries.

    Plain lines rather than JSON: it is smaller, and the model quotes it back
    in a more natural voice than it does raw field names.
    """
    if not context:
        return (
            "\n=== THIS USER'S BRAND ===\n"
            "No brand is currently selected, so you do NOT have their brand data "
            "in front of you. If they ask about their own brand, products, reviews "
            "or keywords, say plainly that you can't see a selected brand right now "
            "and ask them to pick one from the brand switcher. Never guess.\n"
        )

    lines = ["\n=== THIS USER'S BRAND (real data — use it, never invent) ==="]
    lines.append(f"Brand: {context['brand_name']}")
    if context.get("website_url"):
        lines.append(f"Website: {context['website_url']}")
    if context.get("description"):
        lines.append(f"What the brand is: {context['description']}")
    if context.get("target_audience"):
        lines.append(f"Who it's for: {context['target_audience']}")
    if context.get("categories"):
        lines.append(f"Main categories: {', '.join(context['categories'])}")

    bits = [
        f"sells in {context['store_country']}" if context.get("store_country") else None,
        f"price range {context['price_range']}" if context.get("price_range") else None,
        f"on {context['platform']}" if context.get("platform") else None,
    ]
    bits = [b for b in bits if b]
    if bits:
        lines.append("Store: " + ", ".join(bits))

    cat = context.get("catalogue")
    if cat:
        line = f"Catalogue: {cat['total_products']} products"
        pr = cat.get("price_range") or {}
        if cat.get("has_prices") and pr.get("min") is not None:
            line += f", prices {pr['min']:g}–{pr['max']:g} (avg {pr['avg']:g})"
        if cat.get("missing_image_alt_text"):
            line += (
                f", {cat['missing_image_alt_text']} product photos have no text "
                f"description attached ({cat['missing_image_alt_text_pct']}%)"
            )
        lines.append(line)

    s = context.get("sentiment")
    if s:
        head = f"Customer reviews: {s.get('total_reviews')} analysed"
        if s.get("overall_sentiment_score") is not None:
            head += f", overall sentiment {s['overall_sentiment_score']}"
        if s.get("dominant_emotion"):
            head += f", dominant emotion {s['dominant_emotion']}"
        lines.append(head)
        if s.get("summary"):
            lines.append(f"  Summary: {s['summary']}")
        if s.get("top_complaints"):
            lines.append("  Top complaints: " + "; ".join(s["top_complaints"]))
        if s.get("top_loved"):
            lines.append("  Most loved: " + "; ".join(s["top_loved"]))
        if s.get("customer_desires"):
            lines.append("  Customers want: " + "; ".join(s["customer_desires"]))

    a = context.get("seo_audit")
    if a:
        lines.append(
            f"SEO audit: overall score {a.get('seo_score')}, "
            f"{a.get('products_audited')} products checked, "
            f"{a.get('needs_work_count')} items need work"
        )
    if context.get("top_keywords"):
        lines.append("Top keywords: " + ", ".join(context["top_keywords"]))

    if context.get("missing_modules"):
        lines.append(
            "NOT RUN YET (you have NO data for these — say so plainly and "
            "suggest running the module, never invent numbers): "
            + "; ".join(context["missing_modules"])
        )

    return "\n".join(lines) + "\n"
