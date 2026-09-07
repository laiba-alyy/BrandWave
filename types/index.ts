export interface Brand {
  brand_id: string;
  brand_name: string;
  website_url?: string;
  product_categories?: string[];
  created_at?: string;
}

export interface SentimentData {
  total_posts: number;
  positive: number;
  negative: number;
  neutral: number;
  positive_percent: number;
  negative_percent: number;
  neutral_percent: number;
}

export interface Keyword {
  keyword: string;
  frequency: number;
}

/** Real emotion counts from Groq — how many reviews express each emotion. */
export interface EmotionCounts {
  happy: number;
  angry: number;
  frustrated: number;
  disappointed: number;
  excited: number;
  satisfied: number;
  neutral: number;
}

export interface AnalysisData {
  brand_name?: string;
  sentiment_summary: SentimentData;
  pain_points: string[];
  desires: string[];
  /** Things customers praised — from Groq. Optional: older saved analyses lack it. */
  loved?: string[];
  /** Real emotion counts — from Groq. Optional: older saved analyses lack it. */
  emotions?: EmotionCounts;
  keywords: Keyword[];
  /**
   * Per-source item counts, e.g. { trustpilot: 20, youtube: 8 }.
   * `youtube` is optional: older saved analyses predate the YouTube source,
   * and brands with no YouTube channel simply report 0.
   */
  platforms: {
    trustpilot: number;
    youtube?: number;
  };
}

export interface AnalysisResult {
  status: string;
  brand_name: string;
  brand_id: string;
  total_reviews: number;
  platforms_searched: {
    trustpilot: number;
    youtube?: number;
    /** Third-party reviewer videos — sirf tab mojood jab user ne opt-in kiya ho. */
    youtube_reviews?: number;
  };
  sentiment: SentimentData;
  /** 'positive' | 'negative' | 'neutral' — true majority of the three. */
  dominant_emotion?: string;
  analysis_id: string;
  analysis_data?: AnalysisData;
  /** true = mehfooz natija dobara diya gaya, live run nahi hua. */
  cached?: boolean;
  /** Ye natija kab bana (ISO). UI "Last analysed 3 hours ago" isi se banata hai. */
  analysed_at?: string | null;
  /** true = YouTube reviewer videos bhi shamil thay (opt-in, ~4 min). */
  deep?: boolean;
}