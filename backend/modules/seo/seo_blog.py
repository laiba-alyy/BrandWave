import os
import re
from sqlalchemy import cast, String
from dotenv import load_dotenv
from models.brand_profile import BrandProfile
from models.seo_result import SEOBlogPost, SEOKeywordSuggestion
from sqlalchemy.orm import Session
from modules.llm_config import (
    RateLimitedError,
    TruncatedCompletionError,
    chat_completion,
    check_raw_response,
    get_groq_config,
    reasoning_params,
)
from modules.store_locale import market_block, store_country

load_dotenv()

# Client aur model llm_config se — dekho PURPOSE_MODELS.


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _count_words(text: str) -> int:
    """Count words in text"""
    return len(text.split()) if text else 0


def _extract_keywords_found(text: str, keywords: list) -> list:
    """Return list of keywords that appear in text"""
    if not text or not keywords:
        return []
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


# ─────────────────────────────────────────────
#  BLOG GENERATION
# ─────────────────────────────────────────────

def generate_blog_post(
    brand_profile: BrandProfile,
    db: Session,
    topic: str = None,
) -> SEOBlogPost:
    """
    LLM se SEO optimized blog article generate karo.
    800-1200 words with H2, H3 structure.
    Plain text format — no JSON to avoid control character errors.
    """

    # Get existing keywords from DB if available
    keyword_suggestion = db.query(SEOKeywordSuggestion).filter(
        SEOKeywordSuggestion.user_id == brand_profile.user_id,
        SEOKeywordSuggestion.brand_profile_id == brand_profile.id,
    ).order_by(SEOKeywordSuggestion.created_at.desc()).first()

    keywords = []
    if keyword_suggestion and keyword_suggestion.keywords:
        high = [k["keyword"] for k in keyword_suggestion.keywords if k.get("relevance") == "High"]
        medium = [k["keyword"] for k in keyword_suggestion.keywords if k.get("relevance") == "Medium"]
        keywords = (high + medium)[:5]

    # Sample products for context
    products = brand_profile.products or []
    sample_products = [p.get("name", "") for p in products[:6] if p.get("name")]

    # Topic — user provided or auto generate
    if not topic:
        topic = _auto_generate_topic(brand_profile, keywords)

    keywords_str = ", ".join(keywords) if keywords else "relevant keywords"

    prompt = f"""
You are an SEO content writer creating a blog article for a Shopify store.

{market_block(brand_profile)}

Store: {brand_profile.business_name}
Business Type: {brand_profile.business_type}
Target Audience: {brand_profile.target_audience}
Price Range: {brand_profile.price_range}
Categories: {brand_profile.product_categories}
Sample Products: {sample_products}
Target Keywords: {keywords_str}
Blog Topic: {topic}

Write a complete SEO-optimized blog article. Format your response EXACTLY like this:

META_TITLE: your meta title here
META_DESCRIPTION: your meta description here
TITLE: your blog title here
CONTENT:
your full blog content here

Rules:
- META_TITLE must be 50-60 characters
- META_DESCRIPTION must be 150-160 characters
- CONTENT must be 800-1200 words
- Use ## for H2 headings and ### for H3 headings inside CONTENT
- Naturally integrate 3-5 target keywords — no keyword stuffing
- Write in a helpful, informative tone for the STORE MARKET audience above.
- Do NOT name any city or region, and do NOT name any country other than the
  home country given above. Never write the article for a secondary shipping
  market — seasons and cultural references must not imply a foreign location.
- Include practical tips, product references, and buying advice
- Do not use JSON format
- Do not add any extra labels or markers — only the 4 fields above
"""

    # 800-1200 word article ko ~1,500-2,000 output tokens chahiye. 2,000 par
    # article beech mein kat jata tha (aur chup-chaap DB mein save ho jata tha).
    # gpt-oss-120b output se PEHLE reasoning tokens kharch karta hai, to 2,500
    # par bhi article kat raha tha (finish_reason="length"). reasoning_effort=low
    # + bara budget. Blog prompt chhota (~500 tokens) hai, is liye 6,000 output
    # ke saath bhi total 8,000 TPM limit ke andar rehta hai.
    BLOG_MAX_TOKENS = 6000

    # SDK client ki jagah chat_completion: is se blog ko poora lane failover
    # milta hai (OpenAI -> Groq primary -> Groq alt). SDK wala raasta client
    # ke saath key BAANDH deta tha, is liye 429 par kahin ja hi nahi sakta tha.
    _key, model = get_groq_config("seo_blog")

    try:
        response = chat_completion(
            "seo_blog",
            {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": BLOG_MAX_TOKENS,
                **reasoning_params(model),
            },
            timeout=120,
            what="Blog article generation",
        )

        # finish_reason == "length" ka matlab article ADHOORA hai — save mat karo
        result = check_raw_response(
            response, "Blog article generation", max_tokens=BLOG_MAX_TOKENS
        )

        # Parse plain text format
        meta_title = ""
        meta_description = ""
        title = ""
        content_lines = []
        in_content = False

        for line in result.split("\n"):
            if line.startswith("META_TITLE:"):
                meta_title = line.replace("META_TITLE:", "").strip()
            elif line.startswith("META_DESCRIPTION:"):
                meta_description = line.replace("META_DESCRIPTION:", "").strip()
            elif line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("CONTENT:"):
                in_content = True
            elif in_content:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()

        # Validate
        if not title:
            raise ValueError("Could not parse blog title from LLM response")
        if not content:
            raise ValueError("Could not parse blog content from LLM response")

        # Fallback for missing meta fields
        if not meta_title:
            meta_title = title[:60]
        if not meta_description:
            meta_description = re.sub(r'[#\n]', ' ', content)[:160].strip()

        word_count = _count_words(content)

        # Sanity check — prompt 800-1200 words maangta hai. Agar iske aadhe se
        # bhi kam aaya to output adhoora hai, chahe finish_reason "stop" hi ho
        # (model kabhi kabhi khud hi jaldi ruk jata hai). Adhoora article save
        # karne se behtar hai user ko batana.
        MIN_ACCEPTABLE_WORDS = 400
        if word_count < MIN_ACCEPTABLE_WORDS:
            raise TruncatedCompletionError(
                f"Blog article came back too short ({word_count} words, "
                f"expected 800-1200). Generation was likely cut short — please try again."
            )

        keywords_found = _extract_keywords_found(content, keywords)
        keyword_count = len(keywords_found)

        print(f"✅ Blog generated: '{title}'")
        print(f"✅ Word count: {word_count}")
        print(f"✅ Keywords used: {keywords_found}")

        # Save to DB
        blog_post = SEOBlogPost(
            user_id=brand_profile.user_id,
            brand_profile_id=brand_profile.id,
            title=title,
            content=content,
            meta_title=meta_title[:60],
            meta_description=meta_description[:160],
            word_count=word_count,
            keyword_count=keyword_count,
            keywords_used=keywords_found,
        )

        db.add(blog_post)
        db.commit()
        db.refresh(blog_post)

        print(f"✅ Blog saved! ID: {blog_post.id}")
        return blog_post

    # Rate limit ko generic Exception mein lapetna matlab route 500 degi aur
    # frontend "please wait a minute" ke bajaye generic error dikhayega.
    except RateLimitedError:
        raise

    except Exception as e:
        print(f"Blog generation error: {e}")
        raise Exception(f"Failed to generate blog post: {str(e)}")


def _auto_generate_topic(brand_profile: BrandProfile, keywords: list) -> str:
    """Auto generate blog topic from brand context"""
    categories = brand_profile.product_categories or []
    name = brand_profile.business_name or "our store"

    if keywords:
        return f"Complete Guide to {keywords[0].title()} — {name}"

    # Templates ka geo hissa store ki apni country se aata hai. Pehle in mein
    # ek hi mulk hardcoded tha, to har store ka blog topic usi mulk ka ban jata
    # tha. Country detect na ho to topic bilkul geo-free rehta hai.
    country = store_country(brand_profile)
    category = categories[0] if categories else "products"
    geo = f" in {country}" if country else ""

    topic_templates = [
        f"Top {category} trends{geo} this season",
        f"How to choose the best {category} for your needs",
        f"Complete guide to shopping for {category} online{geo}",
        f"Why {name} is the best choice for {category}{geo}",
    ]

    return topic_templates[0]


# ─────────────────────────────────────────────
#  BLOG HISTORY
# ─────────────────────────────────────────────

def get_blog_history(
    user_id: int,
    brand_profile_id: int,
    db: Session,
) -> list:
    """User ke saare blog posts fetch karo — newest first"""
    posts = db.query(SEOBlogPost).filter(
        SEOBlogPost.user_id == user_id,
        SEOBlogPost.brand_profile_id == brand_profile_id,
    ).order_by(SEOBlogPost.created_at.desc()).all()

    return [_serialize_blog(post) for post in posts]


def get_blog_post(
    blog_id: int,
    user_id: int,
    db: Session,
) -> SEOBlogPost:
    """Single blog post fetch karo by ID"""
    post = db.query(SEOBlogPost).filter(
        SEOBlogPost.id == blog_id,
        SEOBlogPost.user_id == user_id,
    ).first()

    if not post:
        raise Exception(f"Blog post {blog_id} not found")

    return post


def delete_blog_post(
    blog_id: int,
    user_id: int,
    db: Session,
) -> bool:
    """Blog post delete karo"""
    post = db.query(SEOBlogPost).filter(
        SEOBlogPost.id == blog_id,
        SEOBlogPost.user_id == user_id,
    ).first()

    if not post:
        raise Exception(f"Blog post {blog_id} not found")

    db.delete(post)
    db.commit()
    return True


# ─────────────────────────────────────────────
#  SERIALIZER
# ─────────────────────────────────────────────

def _serialize_blog(post: SEOBlogPost) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "meta_title": post.meta_title,
        "meta_description": post.meta_description,
        "word_count": post.word_count,
        "keyword_count": post.keyword_count,
        "keywords_used": post.keywords_used,
        "created_at": str(post.created_at) if post.created_at else None,
        "updated_at": str(post.updated_at) if post.updated_at else None,
    }