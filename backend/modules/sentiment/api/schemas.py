"""
Pydantic schemas for Sentiment Analysis Module API (Module 4).

Changes from original:
  - Fixed: AnalysisResponse was defined TWICE (second one silently
    overwrote the first — now merged into one correct definition)
  - Renamed: reddit_mention_count → review_count (source-agnostic)
  - Removed: TrendData / SentimentTrend (no time-based data from Trustpilot)
  - Removed: EmotionData schema (emotion data stored in analysis_data JSON)
  - Kept:    PainPointData, DesireData, KeywordData (used by frontend)
"""

from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# ============================================================
# BRAND
# ============================================================
class BrandResponse(BaseModel):
    brand_id:           str
    brand_name:         str
    website_url:        Optional[str]       = None
    product_categories: Optional[List[str]] = None
    created_at:         Optional[datetime]  = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        return cls(
            brand_id=str(obj.brand_id),
            brand_name=obj.brand_name,
            website_url=obj.website_url,
            product_categories=obj.product_categories,
            created_at=obj.created_at,
        )


# ============================================================
# PAIN POINT
# ============================================================
class PainPointData(BaseModel):
    title:         str
    category:      str
    mention_count: int
    percentage:    float
    examples:      Optional[List[str]] = None


# ============================================================
# DESIRE
# ============================================================
class DesireData(BaseModel):
    title:         str
    category:      str
    mention_count: int
    percentage:    float
    examples:      Optional[List[str]] = None


# ============================================================
# KEYWORD
# ============================================================
class KeywordData(BaseModel):
    keyword:   str
    frequency: int


# ============================================================
# ANALYSIS REQUEST
# ============================================================
class AnalysisRequest(BaseModel):
    brand_id:   str
    time_range: Optional[int] = 30   # reserved for future use


# ============================================================
# ANALYSIS RESPONSE  (single, correct definition)
# ============================================================
class AnalysisResponse(BaseModel):
    analysis_id:             str
    brand_id:                str
    overall_sentiment_score: float
    dominant_emotion:        Optional[str]             = None
    review_count:            int                       # renamed from reddit_mention_count
    pain_points:             Optional[List[PainPointData]]  = None
    desires:                 Optional[List[DesireData]]     = None
    trending_keywords:       Optional[List[KeywordData]]    = None
    analysis_data:           Optional[Any]             = None
    created_at:              Optional[datetime]        = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        return cls(
            analysis_id=str(obj.analysis_id),
            brand_id=str(obj.brand_id),
            overall_sentiment_score=obj.overall_sentiment_score,
            dominant_emotion=obj.dominant_emotion,
            review_count=obj.review_count,
            analysis_data=obj.analysis_data,
            created_at=obj.created_at,
        )