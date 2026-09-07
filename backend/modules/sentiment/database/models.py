"""
Database models for Sentiment Analysis Module (Module 4).

Tables used:
  - Brand            : reference to brands onboarded via Module 2
  - SentimentAnalysis: main analysis result (stores all data as JSON)
  - ReviewPost       : audit trail of individual reviews fetched from Trustpilot

Removed (were Reddit-specific / not populated by routes.py):
  - RedditPost       → renamed to ReviewPost (source-agnostic)
  - EmotionBreakdown → data stored inside analysis_data JSON instead
  - PainPoint        → data stored inside analysis_data JSON instead
  - Desire           → data stored inside analysis_data JSON instead
  - SentimentTrend   → removed (time-based data not available from Trustpilot)
  - TrendingKeyword  → data stored inside analysis_data JSON instead
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, UUID, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime
import uuid

# Base ab poore app ka SHARED Base hai, is module ka apna nahi.
#
# Pehle yahan apna `declarative_base()` tha, yani sentiment ki tables ek ALAG
# metadata registry mein rehti thin. Isi wajah se ye module "alag backend"
# lagta tha: main.py ko iske liye ek extra create_all() chalana parta tha, aur
# koi bhi cross-module ForeignKey ya migration tool dono registries ko ek sath
# nahi dekh sakta tha.
#
# Ab har table — brand_profile, seo_result, chatbot, sentiment — ek hi
# metadata mein hai, aur ek create_all() sab bana deta hai.
from database.connection import Base


# ============================================================
# 1. BRAND
#    Reference to brands onboarded via Module 2 (Web Scraping).
#    website_url comes from BrandProfile.website_url — no hardcoding.
# ============================================================
class Brand(Base):
    __tablename__  = "brands"
    __table_args__ = {"schema": "public"}

    brand_id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_name        = Column(String(255), nullable=False)
    website_url       = Column(String(500))
    product_categories = Column(ARRAY(String), default=[])
    created_at        = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 2. SENTIMENT ANALYSIS
#    One row per analysis run.
#    All rich data (pain points, desires, keywords, sentiment
#    breakdown) is stored inside analysis_data as JSON so the
#    frontend can read it directly without extra joins.
# ============================================================
class SentimentAnalysis(Base):
    __tablename__  = "sentiment_analyses"
    __table_args__ = {"schema": "public"}

    analysis_id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id               = Column(UUID(as_uuid=True), ForeignKey("public.brands.brand_id"), nullable=False)
    analysis_date          = Column(DateTime, default=datetime.utcnow)

    # Keep Python attribute `review_count` while mapping to legacy DB column
    # `reddit_mention_count` to stay compatible with existing Neon schema.
    review_count           = Column("reddit_mention_count", Integer, default=0)

    overall_sentiment_score = Column(Float, default=0.0)   # positive_percent (0–100)
    dominant_emotion        = Column(String(50))            # 'positive' | 'negative' | 'neutral'

    # JSON blob — contains everything the frontend needs:
    # {
    #   brand_name, sentiment_summary,
    #   pain_points, desires, keywords,
    #   platforms: { trustpilot: N }
    # }
    analysis_data  = Column(JSON)

    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================
# 3. REVIEW POST  (audit trail)
#    Individual reviews fetched from Trustpilot — kept so you
#    can show "which reviews were used" if needed in the future.
#    NOT required for the main flow; routes.py does not populate
#    this yet — add later if needed.
# ============================================================
class ReviewPost(Base):
    __tablename__  = "review_posts"
    __table_args__ = {"schema": "public"}

    post_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id  = Column(UUID(as_uuid=True), ForeignKey("public.sentiment_analyses.analysis_id"), nullable=False)
    source       = Column(String(50), default="trustpilot")   # extensible for future sources
    content      = Column(Text)
    sentiment    = Column(String(20))                          # positive | negative | neutral
    confidence   = Column(Float)
    fetch_date   = Column(DateTime, default=datetime.utcnow)