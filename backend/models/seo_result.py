from sqlalchemy import Column, Index, Integer, String, JSON, DateTime, Float, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from database.connection import Base


class SEOAuditResult(Base):
    __tablename__ = "seo_audit_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    brand_profile_id = Column(Integer, index=True)

    # Overall Score
    seo_score = Column(Float, nullable=True)             # 0-100 overall score

    # Individual Factor Scores (0-100 each)
    title_score = Column(Float, nullable=True)           # Product title quality
    description_score = Column(Float, nullable=True)     # Meta description quality
    image_alt_score = Column(Float, nullable=True)       # Image alt text presence
    # False = is store ki products feed alt text deti hi nahi, to ye factor
    # overall score se bahar rehta hai (0 dena ghalat tha — dekho seo_auditor).
    image_alt_measurable = Column(Boolean, nullable=True, default=True)
    keyword_score = Column(Float, nullable=True)         # Keyword usage in content
    tags_score = Column(Float, nullable=True)            # Tag completeness

    # Audit Results per Factor
    # Each is a JSON list of:
    # {"product_name": "...", "issue": "...", "severity": "Good|Warning|Needs Work", "recommendation": "..."}
    title_issues = Column(JSON, nullable=True)
    description_issues = Column(JSON, nullable=True)
    image_alt_issues = Column(JSON, nullable=True)
    keyword_issues = Column(JSON, nullable=True)
    tags_issues = Column(JSON, nullable=True)

    # Summary counts
    total_products_audited = Column(Integer, nullable=True)   # kitne products actually audit hue (sample size)
    total_catalogue_products = Column(Integer, nullable=True) # brand ke poore catalogue mein kitne products hain
    good_count = Column(Integer, nullable=True)
    warning_count = Column(Integer, nullable=True)
    needs_work_count = Column(Integer, nullable=True)

    # AI Generated Recommendations
    # JSON list of {"product_name": "...", "original_title": "...", "optimized_title": "...",
    #               "original_description": "...", "optimized_description": "..."}
    ai_recommendations = Column(JSON, nullable=True)

    # Suggested keywords used during audit
    suggested_keywords = Column(JSON, nullable=True)     # ["keyword1", "keyword2", ...]

    # Meta
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class SEOBlogPost(Base):
    __tablename__ = "seo_blog_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    brand_profile_id = Column(Integer, index=True)

    # Blog Content
    title = Column(String, nullable=False)               # Blog article title
    content = Column(Text, nullable=False)               # Full article content
    meta_title = Column(String, nullable=True)           # SEO meta title (50-60 chars)
    meta_description = Column(String, nullable=True)     # SEO meta description (150-160 chars)

    # Metrics
    word_count = Column(Integer, nullable=True)          # Auto calculated
    keyword_count = Column(Integer, nullable=True)       # Keywords used count
    keywords_used = Column(JSON, nullable=True)          # ["keyword1", "keyword2", ...]

    # Meta
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class SEOKeywordSuggestion(Base):
    __tablename__ = "seo_keyword_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    brand_profile_id = Column(Integer, index=True)

    # Keywords
    # JSON list of scored, market-specific keyword records.
    keywords = Column(JSON, nullable=False)

    # Meta
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class SEOKeywordMetricCache(Base):
    __tablename__ = "seo_keyword_metric_cache"
    __table_args__ = (UniqueConstraint(
        "normalized_keyword", "country", "language", "provider",
        name="uq_seo_keyword_metric_market",
    ),)

    id = Column(Integer, primary_key=True, index=True)
    normalized_keyword = Column(String, nullable=False, index=True)
    country = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    search_volume = Column(Integer, nullable=True)
    competition = Column(Float, nullable=True)
    competition_index = Column(Integer, nullable=True)
    cpc = Column(Float, nullable=True)
    # Ye do DataForSEO Labs se aate hain (search_volume Google Ads se) —
    # alag endpoints hain, is liye alag alag null ho sakte hain.
    keyword_difficulty = Column(Integer, nullable=True)
    search_intent = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class KeywordCache(Base):
    """
    CATEGORY-level keyword cache — ek jaisi brands ke liye shared khazana.

    ── seo_keyword_metric_cache se farq kya hai ────────────────────────────
    Wo cache EXACT keyword + country + language par chalti hai aur kabhi
    expire nahi hoti. Ye table us se alag sawal ka jawab deti hai:

        "is CATEGORY + COUNTRY ke generic keywords ka data pehle se maujood
         hai kya?"

    Yani jab Maria.B (clothing / PK) ke liye "embroidered lawn suit online"
    ki volume ek baar khareed li gayi, to Asim Jofa (bhi clothing / PK) usi
    keyword par dobara DataForSEO credit nahi jalata.

    ── Yahan SIRF generic keywords aate hain ───────────────────────────────
    "maria b eid collection" jaisa brand keyword is table mein KABHI nahi
    likha jata. Wo ek hi brand ka hota hai, doosri brand ke kaam ka nahi, aur
    us ki volume brand ki apni demand ke saath badalti rehti hai — is liye wo
    hamesha fresh validate hota hai (dekho modules/seo/keyword_cache.py).

    ── cached_at timezone-aware KYUN hai ───────────────────────────────────
    30-din ka TTL isi column par chalta hai. Baqi tables plain DateTime use
    karti hain (Postgres mein wo naive local time ban jata hai), aur naive vs
    aware ka muqabla TTL ko chupke se ghalat kar deta — is liye yahan
    timestamptz hai, taake cutoff ka hisaab har server timezone par sahi rahe.
    """

    __tablename__ = "keyword_cache"
    __table_args__ = (
        UniqueConstraint(
            "category", "store_country", "keyword",
            name="uq_keyword_cache_scope",
        ),
        # Lookup hamesha (category, store_country) par hota hai aur ek hi
        # scope mein hazaaron rows ho sakti hain.
        Index("ix_keyword_cache_scope", "category", "store_country"),
    )

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)          # "clothing", "jewellery", ...
    store_country = Column(String, nullable=False)     # ISO code — "PK", "US"
    keyword = Column(String, nullable=False)           # normalized (lowercase, single spaces)
    search_volume = Column(Integer, nullable=True)
    difficulty = Column(Integer, nullable=True)        # 0-100
    cpc = Column(Float, nullable=True)
    intent = Column(String, nullable=True)             # transactional / commercial / ...
    cached_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ── Additive Schema Migration ─────────────────
# create_all() existing table mein naya column add nahi karta — ye helper
# missing columns ko idempotently add karta hai (wahi pattern jo
# models/chatbot.py mein use hua hai).
_ADDED_COLUMNS = {
    "seo_audit_results": [
        ("total_catalogue_products", "INTEGER"),
        # Shopify ki products feed alt text expose nahi karti, is liye ye
        # factor har store par 0 aata tha aur overall score ko 20 points
        # neeche khinch leta tha. Ab jab feed mein alt text hai hi nahi to
        # factor score se nikal jata hai aur UI wajah dikhata hai.
        ("image_alt_measurable", "BOOLEAN"),
    ],
    "seo_keyword_metric_cache": [
        ("keyword_difficulty", "INTEGER"),
        ("search_intent", "VARCHAR"),
    ],
}


def ensure_seo_schema(engine) -> None:
    """Naye SEO audit columns add karta hai."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in present:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

        # Purane audits ke liye catalogue size pata nahi — sample size hi set kar do
        # taake frontend "1000 of 1000" dikhaye, na ke "1000 of null".
        if "seo_audit_results" in existing_tables:
            conn.execute(text(
                "UPDATE seo_audit_results "
                "SET total_catalogue_products = total_products_audited "
                "WHERE total_catalogue_products IS NULL"
            ))
