-- ============================================================
-- SENTIMENT ANALYSIS SCHEMA
-- ============================================================

-- Brands (Reference table - created by partner's web scraping)
-- We reference it, don't need to create
-- Create brands table (if not exists)
CREATE TABLE IF NOT EXISTS public.brands (
    brand_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name VARCHAR(255) NOT NULL,
    website_url VARCHAR(500),
    product_categories TEXT[] DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sentiment Analyses
CREATE TABLE IF NOT EXISTS public.sentiment_analyses (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES public.brands(brand_id),
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reddit_mention_count INTEGER DEFAULT 0,
    overall_sentiment_score FLOAT CHECK (overall_sentiment_score BETWEEN 0 AND 100),
    dominant_emotion VARCHAR(50),
    analysis_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Emotion Breakdowns
CREATE TABLE IF NOT EXISTS public.emotion_breakdowns (
    emotion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.sentiment_analyses(analysis_id) ON DELETE CASCADE,
    emotion_type VARCHAR(50) NOT NULL,
    count INTEGER DEFAULT 0,
    percentage FLOAT DEFAULT 0,
    UNIQUE(analysis_id, emotion_type)
);

-- Pain Points
CREATE TABLE IF NOT EXISTS public.pain_points (
    pain_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.sentiment_analyses(analysis_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    mention_count INTEGER DEFAULT 0,
    percentage FLOAT DEFAULT 0,
    examples TEXT[] DEFAULT ARRAY[]::TEXT[]
);

-- Desires
CREATE TABLE IF NOT EXISTS public.desires (
    desire_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.sentiment_analyses(analysis_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    mention_count INTEGER DEFAULT 0,
    percentage FLOAT DEFAULT 0,
    examples TEXT[] DEFAULT ARRAY[]::TEXT[]
);

-- Sentiment Trends
CREATE TABLE IF NOT EXISTS public.sentiment_trends (
    trend_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.sentiment_analyses(analysis_id) ON DELETE CASCADE,
    trend_date TIMESTAMP NOT NULL,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0
);

-- Trending Keywords
CREATE TABLE IF NOT EXISTS public.trending_keywords (
    keyword_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.sentiment_analyses(analysis_id) ON DELETE CASCADE,
    keyword VARCHAR(100) NOT NULL,
    frequency INTEGER DEFAULT 0
);

-- Reddit Posts (Audit Trail)
CREATE TABLE IF NOT EXISTS public.reddit_posts (
    post_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.sentiment_analyses(analysis_id) ON DELETE CASCADE,
    reddit_post_id VARCHAR(255) NOT NULL UNIQUE,
    title TEXT,
    content TEXT,
    url VARCHAR(500),
    score INTEGER,
    comments_count INTEGER,
    fetch_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_sentiment_brand ON public.sentiment_analyses(brand_id);
CREATE INDEX idx_sentiment_date ON public.sentiment_analyses(analysis_date);
CREATE INDEX idx_emotion_analysis ON public.emotion_breakdowns(analysis_id);
CREATE INDEX idx_pain_analysis ON public.pain_points(analysis_id);
CREATE INDEX idx_desire_analysis ON public.desires(analysis_id);
CREATE INDEX idx_trend_analysis ON public.sentiment_trends(analysis_id);
CREATE INDEX idx_keyword_analysis ON public.trending_keywords(analysis_id);
CREATE INDEX idx_reddit_analysis ON public.reddit_posts(analysis_id);