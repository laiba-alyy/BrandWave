'use client';

import { ReactNode, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AnalysisData, AnalysisResult, SentimentData, EmotionCounts } from '@/types';
import { SentimentCharts } from '@/components/SentimentCharts';
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css';
import { authHeaders } from '@/lib/authHeaders';
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand';

const API_URL =
  process.env.NEXT_PUBLIC_SENTIMENT_API ||
  `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/sentiment`;

const analysisSteps = [
  'Searching customer reviews',
  'Running sentiment model',
  'Extracting customer insights',
  'Preparing visual report',
];

const SENTIMENT_CACHE_PREFIX = 'brandwave_sentiment_analysis';

/** "3 hours ago" — cached natije ki umar sach sach dikhane ke liye. */
function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? '' : 's'} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

// ── sub-components ────────────────────────────────────────────────────────────
function SentimentRing({ score, size = 132 }: { score: number; size?: number }) {
  const radius = size / 2 - 10;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.13)" strokeWidth="8" fill="none" />
      <motion.circle
        cx={size / 2} cy={size / 2} r={radius}
        stroke="#f0a63c" strokeWidth="8" fill="none" strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
      />
    </svg>
  );
}

function StatCard({ label, value, tone }: { label: string; value: string | number; tone?: 'green' | 'red' | 'orange' | 'gray' }) {
  /* Rang hata diya gaya hai: chaar tiles, chaar alag rang, aur asli number
     peeche chala jata tha. Ab tile paper hai aur number ink — bilkul wohi
     dsh__stat jo scraping/SEO par chalti hai. `tone` prop signature mein
     rakha hai taake call sites na tootein. */
  void tone;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="dsh__stat"
    >
      <span>{label}</span>
      <strong>{value}</strong>
    </motion.div>
  );
}

function SectionCard({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
      className="dsh__card"
    >
      <div className="dsh__cardhead">
        <h3>{title}</h3>
        <span className="dsh__badge dsh__badge--ink">{number}</span>
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </motion.section>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────
export default function SentimentPage() {

  const { activeBrand, activeBrandId, userId: brandUserId, sessionChecked } = useActiveBrand();
  const [results, setResults]         = useState<AnalysisResult | null>(null);
  const [detailedData, setDetailedData] = useState<AnalysisData | null>(null);
  const [loading, setLoading]         = useState(true);
  const [analyzing, setAnalyzing]     = useState(false);
  const [error, setError]             = useState<string>('');
  const [activeSection, setActiveSection] = useState<'overview' | 'charts' | 'emotions' | 'insights'>('overview');
  const [loadingStep, setLoadingStep] = useState(0);
  // Kab ka natija dikh raha hai — judge poochhe to jawab screen par ho.
  const [analysedAt, setAnalysedAt] = useState<string | null>(null);
  const [fromCache, setFromCache]   = useState(false);
  // Doosron ke YouTube review videos — opt-in. Ye source ~121 YouTube
  // quota units aur ~3 extra minute leta hai, is liye har analysis par
  // default nahi chalta. (Aage chal kar ye paid plan ka hissa hoga.)
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [wasDeep, setWasDeep]           = useState(false);
  const [downloading, setDownloading]   = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  // ── init ───────────────────────────────────────────────────────────────────
  //
  // Session aur `users` row yahan se nikal chuke hain (ab ActiveBrandProvider
  // mein, ek hi dafa). Bacha sirf cache restore, jo sessionStorage se aata hai
  // — yani synchronous, koi network nahi. Is liye ye ab async bhi nahi.
  /*
   * Page par wapas aane par natija bahal karo — DOBARA analyse kiye baghair.
   *
   * Do masle the:
   *   1. Ye effect sirf `sessionChecked` par depend karta tha aur us waqt
   *      `brandwave.activeBrandId` abhi likha hi nahi hota tha. Effect ek
   *      dafa chal kar khali haath lautta aur DOBARA kabhi nahi chalta —
   *      is liye doosre page se wapas aane par screen khali hoti thi.
   *      Ab ye `activeBrandId` par depend karta hai.
   *   2. sessionStorage sirf ISI tab mein hai. Naya tab, ya browser band
   *      kar ke dobara kholna — sab khali. Is liye agar sessionStorage
   *      mein kuch na mile to backend se aakhri mehfooz analysis maang
   *      lete hain (/latest) — us par koi quota kharch nahi hota.
   */
  useEffect(() => {
    if (!sessionChecked) return;
    if (!activeBrandId) { setLoading(false); return; }

    let cancelled = false;

    // (a) foran paint — isi tab ka cache
    try {
      const cached = sessionStorage.getItem(`${SENTIMENT_CACHE_PREFIX}_${activeBrandId}`);
      if (cached) {
        const parsed = JSON.parse(cached) as {
          brand_profile_id?: number;
          results?: AnalysisResult;
          detailedData?: AnalysisData | null;
          analysedAt?: string | null;
        };
        // Brand switch hone par purane brand ka data NAHI dikhana.
        if (parsed.brand_profile_id === activeBrandId) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setResults(parsed.results || null);
          setDetailedData(parsed.detailedData || null);
          setAnalysedAt(parsed.analysedAt || null);
          setFromCache(true);
          setWasDeep(Boolean(parsed.results?.deep));
          setLoading(false);
          return;
        }
      }
    } catch {
      // stale cache — ignore silently
    }

    // (b) is tab mein kuch nahi — backend se aakhri natija (koi quota nahi)
    (async () => {
      try {
        const res = await fetch(
          `${API_URL}/latest?brand_profile_id=${activeBrandId}`,
          { headers: await authHeaders() },
        );
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || data?.status !== 'success') return;
        setResults(data);
        setDetailedData(data.analysis_data || null);
        setAnalysedAt(data.analysed_at || null);
        setFromCache(true);
        setWasDeep(Boolean(data.deep));
      } catch {
        // suhoolat hai, zaroorat nahi — khamoshi se chhoro
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [sessionChecked, activeBrandId]);

  useEffect(() => {
    if (!analyzing) return;
    const t = setInterval(() => setLoadingStep((s) => (s + 1) % analysisSteps.length), 1200);
    return () => clearInterval(t);
  }, [analyzing]);

  // ── analyze (uses active brand from switcher — no typing needed) ──────────
  async function handleAnalyze(forceRefresh = false) {
    if (!activeBrandId) {
      setError('Please select a brand from the switcher above.');
      return;
    }
    setError('');

    try {
      setAnalyzing(true);
      setLoadingStep(0);
      setError('');

      const res = await fetch(
        `${API_URL}/analyze-from-dropdown?brand_profile_id=${activeBrandId}` +
        `&user_id=${encodeURIComponent(brandUserId || '')}` +
        `&refresh=${forceRefresh ? 'true' : 'false'}` +
        `&include_youtube_reviews=${deepAnalysis ? 'true' : 'false'}`,
        { method: 'POST', headers: await authHeaders() }
      );
      const result = await res.json();

      if (!res.ok) {
        setResults(null); setDetailedData(null);
        setError(result?.detail || result?.message || `Request failed (${res.status})`);
        return;
      }

      if (result.status === 'error') {
        setResults(null); setDetailedData(null);
        setError(
          result.message?.includes('not found')
            ? `This brand has not been onboarded yet. Please add it via the Web Scraping module.`
            : result.message || 'An error occurred during analysis.'
        );
      } else if (result.status === 'no_reviews') {
        setResults(null); setDetailedData(null);
        setError(
          `No customer reviews found for "${result.brand_name || brandLabel(activeBrand)}". ` +
          `This brand may not have review data yet.`
        );
      } else if (result.status === 'success' && result.sentiment) {
        setResults(result);
        setDetailedData(result.analysis_data || null);
        setAnalysedAt(result.analysed_at || null);
        setFromCache(Boolean(result.cached));
        setWasDeep(Boolean(result.deep));
        try {
          sessionStorage.setItem(
            `${SENTIMENT_CACHE_PREFIX}_${activeBrandId}`,
            JSON.stringify({
              brand_profile_id: activeBrandId,
              results: result,
              detailedData: result.analysis_data || null,
              analysedAt: result.analysed_at || null,
              deep: Boolean(result.deep),
            })
          );
        } catch { /* quota exceeded — ignore */ }
        setActiveSection('overview');
      } else {
        setResults(null); setDetailedData(null);
        setError(result.message || 'Unexpected response from sentiment API.');
      }
    } catch {
      setError('Analysis failed. Please check your connection and try again.');
    } finally {
      setAnalyzing(false);
    }
  }

  // ── report download ────────────────────────────────────────────────────────
  /*
   * Report ko ASLI PDF file ke taur par save karo.
   *
   * Pehle ye ek popup kholta tha aur `window.print()` chalata tha. Wo
   * download nahi tha — wo print dialog tha: user ko khud "Save as PDF"
   * chunna parta, popup blocker aksar rok deta, aur har browser ka natija
   * alag hota tha.
   *
   * Ab backend reportlab se poori PDF banata hai (wahi library jo SEO
   * reports banati hai) aur `Content-Disposition: attachment` bhejta hai.
   * Yahan sirf blob le kar save karna hai.
   *
   * fetch istemal karte hain, seedha <a href> nahi — endpoint ko
   * Authorization header chahiye, aur anchor headers nahi bhej sakta.
   */
  async function handleDownloadReport() {
    if (!results?.analysis_id) return;
    setDownloading(true);
    setError('');
    try {
      const res = await fetch(
        `${API_URL}/report/${results.analysis_id}/pdf`,
        { headers: await authHeaders() },
      );
      if (!res.ok) {
        setError(
          res.status === 404
            ? 'That report is no longer available. Run the analysis again.'
            : 'Could not build the report. Please try again.',
        );
        return;
      }
      const blob = await res.blob();

      // filename backend ke Content-Disposition se — wahi naam jo server
      // ne chuna (brand + tareekh), taake do reports ek doosre par na chadhein.
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match?.[1] || 'sentiment_report.pdf';

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Blob URL foran revoke karne se kuch browsers download adhoora chhod
      // dete hain — ek chhota sa wafqa de dete hain.
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch {
      setError('Could not download the report. Please check your connection.');
    } finally {
      setDownloading(false);
    }
  }

  const sentiment = results?.sentiment;
  const dominantSentiment = sentiment
    ? sentiment.positive_percent >= sentiment.negative_percent && sentiment.positive_percent >= sentiment.neutral_percent
      ? 'Positive'
      : sentiment.negative_percent >= sentiment.neutral_percent ? 'Negative' : 'Neutral'
    : 'No analysis yet';

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">
        <div className="dsh__top">
          <div>
            <h1>Sentiment Analysis{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}</h1>
            <p className="dsh__sub">
              Customer emotions and sentiment signals from real reviews
              {analysedAt && (
                <> {' · '}
                  <span title={new Date(analysedAt).toLocaleString()}>
                    {fromCache ? 'Last analysed' : 'Analysed'} {timeAgo(analysedAt)}
                    {wasDeep ? ' · including YouTube reviewers' : ''}
                  </span>
                </>
              )}
            </p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            {/* Gehri analysis ka opt-in. Waqt saaf likha hua hai — user ko
                4 minute ka intezaar HAIRAT mein nahi milna chahiye. */}
            <label
              className="snt__deep"
              title="Analyses hundreds of comments from independent YouTube reviewers"
            >
              <input
                type="checkbox"
                checked={deepAnalysis}
                onChange={(e) => setDeepAnalysis(e.target.checked)}
                disabled={analyzing}
              />
              <span>Include YouTube reviewers</span>
              {deepAnalysis && <em>~4 min</em>}
            </label>
            <button
              onClick={() => handleAnalyze(false)}
              disabled={analyzing || !activeBrand}
              className="dsh__btn dsh__btn--amber dsh__btn--sm"
            >
              {analyzing
                ? <><span className="dsh__spin" />Analyzing</>
                : activeBrand
                  ? (results ? 'View analysis' : 'Analyze reviews')
                  : 'Select a brand'}
            </button>
            {/* Refresh cache ko nazarandaz karta hai — yehi wo button hai jo
                sawal aane par sabit karta hai ke data live aa sakta hai. */}
            {results && (
              <button
                onClick={() => handleAnalyze(true)}
                disabled={analyzing || !activeBrand}
                className="dsh__btn dsh__btn--sm"
                title="Fetch fresh reviews instead of the stored result"
              >
                Refresh
              </button>
            )}
          </div>
        </div>
        <div className="dsh__body">

          {/* hero ring */}
          <motion.section
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="dsh__hero"
          >
            {/* Grid overlay hata diya — dash.css saaf kehti hai koi gradient,
                koi glow. Ink panel apne aap mein kaafi hai. */}
            <div className="dsh__ring">
              <SentimentRing score={sentiment?.positive_percent || 0} />
              <div className="dsh__ringval">
                <b>{Math.round(sentiment?.positive_percent || 0)}</b>
                <span>% POSITIVE</span>
              </div>
            </div>
            <div>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
                  <h2>Brand sentiment score</h2>
                  <span className="dsh__badge dsh__badge--warn">{dominantSentiment}</span>
                </div>
                <p className="dsh__herometa">
                  {results
                    ? `Analysis completed for ${results.brand_name} using ${results.total_reviews} customer reviews.`
                    : 'Select a brand from the switcher above and click analyze to see customer sentiment insights.'}
                </p>
                <div style={{ marginTop: 22, display: 'grid', gap: 14 }}>
                  {[
                    { label: 'Positive', value: sentiment?.positive_percent || 0 },
                    { label: 'Negative', value: sentiment?.negative_percent || 0 },
                    { label: 'Neutral',  value: sentiment?.neutral_percent  || 0 },
                  ].map((item) => (
                    <div className="dsh__meter" key={item.label} style={{ marginTop: 0 }}>
                      <div className="dsh__meterhead">
                        <span>{item.label}</span><b>{item.value.toFixed(1)}%</b>
                      </div>
                      <div className="dsh__metertrack">
                        <motion.div className="dsh__meterfill"
                          initial={{ width: 0 }} animate={{ width: `${item.value}%` }}
                          transition={{ duration: 1, delay: 0.2 }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
          </motion.section>

          {/* error banner */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="dsh__note dsh__note--bad"
              >
                <span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* loading spinner */}
          {analyzing && (
            <motion.div
              initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
              className="dsh__card"
            >
              <div className="dsh__empty">
                <span className="dsh__spin" style={{ width: 22, height: 22, color: 'var(--ink)' }} />
                <h3>{analysisSteps[loadingStep]}</h3>
                <p>Step {loadingStep + 1} of 4 — using live customer review data to build the report.</p>
              </div>
            </motion.div>
          )}

          {/* results */}
          {results && sentiment ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'flex-start' }}>
                <div className="dsh__stats dsh__stats--4" style={{ flex: 1, minWidth: 0 }}>
                  <StatCard label="Total Reviews" value={sentiment.total_posts} tone="orange" />
                  <StatCard label="Positive"      value={`${sentiment.positive_percent.toFixed(1)}%`} tone="green" />
                  <StatCard label="Negative"      value={`${sentiment.negative_percent.toFixed(1)}%`} tone="red"   />
                  <StatCard label="Neutral"       value={`${sentiment.neutral_percent.toFixed(1)}%`}  tone="gray"  />
                </div>
                <button
                  onClick={handleDownloadReport}
                  disabled={downloading || !results?.analysis_id}
                  className="dsh__btn dsh__btn--ghost"
                >
                  {downloading ? 'Preparing PDF…' : 'Download report'}
                </button>
              </div>

              <div className="dsh__tabs">
                {[
                  { key: 'overview', label: 'Overview'  },
                  { key: 'charts',   label: 'Charts'    },
                  { key: 'emotions', label: 'Emotions'  },
                  { key: 'insights', label: 'Insights'  },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveSection(tab.key as typeof activeSection)}
                    className={`dsh__tab ${activeSection === tab.key ? 'dsh__tab--on' : ''}`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {activeSection === 'overview'  && <SectionCard number="01" title="Overview"><OverviewContent  brandName={results.brand_name} sentiment={sentiment} /></SectionCard>}
              {activeSection === 'charts'    && <SectionCard number="02" title="Charts"><SentimentCharts sentiment={sentiment} detailedData={detailedData} brandName={results.brand_name} /></SectionCard>}
              {activeSection === 'emotions'  && <SectionCard number="03" title="Emotions"><EmotionsContent sentiment={sentiment} detailedData={detailedData} /></SectionCard>}
              {activeSection === 'insights'  && <SectionCard number="04" title="Insights"><InsightsContent detailedData={detailedData} /></SectionCard>}

              <div ref={reportRef} className="fixed -left-[9999px] top-0 w-[1000px] bg-white p-8">
                <div className="mb-8 rounded-xl bg-black p-8 text-white">
                  <p className="text-sm font-bold text-white/50">BrandWave Sentiment Analysis Report</p>
                  <h1 className="mt-2 text-4xl font-black">{results.brand_name}</h1>
                  <p className="mt-3 text-sm text-white/60">{sentiment.total_posts} customer reviews analyzed</p>
                </div>
                <div className="mb-6 grid grid-cols-4 gap-4">
                  {[
                    { v: sentiment.total_posts,                       l: 'Total Reviews', c: '' },
                    { v: `${sentiment.positive_percent.toFixed(1)}%`, l: 'Positive',      c: 'text-[#12876b]' },
                    { v: `${sentiment.negative_percent.toFixed(1)}%`, l: 'Concerns',      c: 'text-[#96203f]' },
                    { v: `${sentiment.neutral_percent.toFixed(1)}%`,  l: 'Neutral',       c: 'text-[#8b877d]' },
                  ].map((item) => (
                    <div key={item.l} className="rounded-xl border border-[#e7e4dc] p-4">
                      <p className={`text-2xl font-black ${item.c}`}>{item.v}</p>
                      <p className="text-xs text-[#8b877d]">{item.l}</p>
                    </div>
                  ))}
                </div>
                <div className="space-y-8">
                  <section><h2 className="mb-4 text-2xl font-black">Overview</h2><OverviewContent brandName={results.brand_name} sentiment={sentiment} /></section>
                  <section><h2 className="mb-4 text-2xl font-black">Charts</h2><SentimentCharts sentiment={sentiment} detailedData={detailedData} brandName={results.brand_name} /></section>
                  <section><h2 className="mb-4 text-2xl font-black">Emotions</h2><EmotionsContent sentiment={sentiment} detailedData={detailedData} /></section>
                  <section><h2 className="mb-4 text-2xl font-black">Insights</h2><InsightsContent detailedData={detailedData} /></section>
                </div>
              </div>
            </div>
          ) : !loading && !analyzing && (
            <motion.div
              initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-[#e7e4dc] bg-white p-10 text-center"
            >
              <p className="text-4xl font-black text-[#14140f]">0</p>
              <p className="mt-2 text-base font-bold text-black">
                {activeBrand
                  ? `Click "Analyze ${brandLabel(activeBrand)}" to run sentiment analysis.`
                  : 'Select a brand from the switcher above to get started.'}
              </p>
            </motion.div>
          )}
        </div>
      </div>
    </main>
  );
}

function OverviewContent({ brandName, sentiment }: { brandName: string; sentiment: SentimentData }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {[
          { label: 'Positive mentions', value: sentiment.positive, tone: 'text-[#12876b]'  },
          { label: 'Concern mentions',  value: sentiment.negative, tone: 'text-[#96203f]' },
          { label: 'Neutral mentions',  value: sentiment.neutral,  tone: 'text-[#8b877d]'   },
        ].map((item) => (
          <div key={item.label} className="rounded-xl bg-[#fbfaf7] p-4">
            <p className={`text-2xl font-black ${item.tone}`}>{item.value}</p>
            <p className="text-sm font-bold text-black">{item.label}</p>
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-[#e7e4dc] bg-white p-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-bold text-[#14140f]">Overall Sentiment Distribution</p>
          <p className="text-sm font-black text-[#12876b]">{sentiment.positive_percent.toFixed(1)}%</p>
        </div>
        <div className="flex h-5 overflow-hidden rounded-full bg-[#e7e4dc]">
          <motion.div className="bg-[#12876b]"   initial={{ width: 0 }} animate={{ width: `${sentiment.positive_percent}%` }} transition={{ duration: 1 }} />
          <motion.div className="bg-[#96203f]" initial={{ width: 0 }} animate={{ width: `${sentiment.negative_percent}%` }} transition={{ duration: 1, delay: 0.1 }} />
          <motion.div className="bg-[#8b877d]"    initial={{ width: 0 }} animate={{ width: `${sentiment.neutral_percent}%`  }} transition={{ duration: 1, delay: 0.2 }} />
        </div>
        <div className="mt-4 grid grid-cols-3 text-center text-xs">
          <span className="font-bold text-[#12876b]">{sentiment.positive} Positive</span>
          <span className="font-bold text-[#96203f]">{sentiment.negative} Concerns</span>
          <span className="font-bold text-[#8b877d]">{sentiment.neutral} Neutral</span>
        </div>
      </div>
      <p className="text-sm leading-relaxed text-[#56544d]">
        Based on <strong>{sentiment.total_posts}</strong> customer reviews about{' '}
        <span className="font-bold text-[#14140f]">{brandName}</span>, this report summarizes
        the overall customer tone and highlights useful signals for marketing decisions.
      </p>
    </div>
  );
}

// Real emotions ab Groq se aate hain (analysis_data.emotions).
// Purani saved/cached analyses mein ye key nahi hoti — un ke liye neeche
// sentiment counts par fallback hai, taake purana dashboard bhi na toote.
const EMOTION_META: { key: keyof EmotionCounts; name: string; text: string; color: string; tone: string }[] = [
  { key: 'happy',        name: 'Happy',        text: 'Clear satisfaction and delight',      color: 'bg-[#12876b]',   tone: 'text-[#12876b]'   },
  { key: 'satisfied',    name: 'Satisfied',    text: 'Content — expectations were met',     color: 'bg-[#12876b]',tone: 'text-[#12876b]'},
  { key: 'excited',      name: 'Excited',      text: 'Enthusiasm and strong recommendation',color: 'bg-[#d08a12]',  tone: 'text-[#a8620d]'  },
  { key: 'frustrated',   name: 'Frustrated',   text: 'Blocked or repeatedly inconvenienced',color: 'bg-[#d08a12]', tone: 'text-[#a8620d]' },
  { key: 'disappointed', name: 'Disappointed', text: 'Expectations were not met',           color: 'bg-[#96203f]',    tone: 'text-[#96203f]'    },
  { key: 'angry',        name: 'Angry',        text: 'Strong negative reaction',            color: 'bg-[#96203f]',   tone: 'text-[#96203f]'   },
  { key: 'neutral',      name: 'Neutral',      text: 'Factual or balanced mentions',        color: 'bg-[#8b877d]',    tone: 'text-[#56544d]'    },
];

function EmotionsContent({ sentiment, detailedData }: { sentiment: SentimentData; detailedData: AnalysisData | null }) {
  const raw = detailedData?.emotions;
  const hasReal = !!raw && Object.values(raw).some((v) => (v ?? 0) > 0);

  const total = hasReal
    ? Object.values(raw!).reduce((a, b) => a + (b ?? 0), 0) || 1
    : sentiment.total_posts || 1;

  const emotions = hasReal
    ? EMOTION_META
        .map((m) => {
          const value = raw![m.key] ?? 0;
          return { ...m, value, percent: (value / total) * 100 };
        })
        .filter((e) => e.value > 0)
        .sort((a, b) => b.value - a.value)
    : [
        { name: 'Happy',     text: 'Satisfaction and loyalty signals', value: sentiment.positive, percent: sentiment.positive_percent, color: 'bg-[#12876b]',   tone: 'text-[#12876b]'   },
        { name: 'Concerned', text: 'Issues and improvement areas',     value: sentiment.negative, percent: sentiment.negative_percent, color: 'bg-[#96203f]', tone: 'text-[#96203f]' },
        { name: 'Neutral',   text: 'Factual or balanced mentions',     value: sentiment.neutral,  percent: sentiment.neutral_percent,  color: 'bg-[#8b877d]',    tone: 'text-[#56544d]'    },
      ];

  if (emotions.length === 0) {
    return <p className="text-sm font-bold text-black">No emotion data available for this analysis.</p>;
  }

  return (
    <div className="space-y-6">
      {emotions.map((e) => (
        <div key={e.name} className="rounded-xl border border-[#e7e4dc] bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <span className={`text-sm font-black ${e.tone}`}>{e.name}</span>
              <p className="mt-1 text-sm font-bold text-black">{e.text}</p>
            </div>
            <span className="text-sm font-black text-[#14140f]">{e.value} reviews</span>
          </div>
          <div className="h-5 overflow-hidden rounded-full bg-[#e7e4dc]">
            <motion.div
              className={`flex h-full items-center justify-end rounded-full pr-3 text-xs font-black text-white ${e.color}`}
              initial={{ width: 0 }} animate={{ width: `${e.percent}%` }} transition={{ duration: 1 }}
            >
              {e.percent.toFixed(1)}%
            </motion.div>
          </div>
        </div>
      ))}
    </div>
  );
}

function InsightsContent({ detailedData }: { detailedData: AnalysisData | null }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="rounded-xl bg-[#fbfaf7] p-4 lg:col-span-3">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#8b877d]">Top Keywords</p>
        <div className="flex flex-wrap gap-2">
          {detailedData?.keywords?.length
            ? detailedData.keywords.slice(0, 20).map((kw) => (
                <span key={kw.keyword} className="rounded-full border border-[#e7e4dc] bg-[#fbfaf7] px-3 py-1 text-xs font-bold text-[#56544d] transition-colors hover:border-[#c9c5bb]">
                  {kw.keyword} <span className="text-[#c9c5bb]">({kw.frequency})</span>
                </span>
              ))
            : <p className="text-sm font-bold text-black">No keywords found for this analysis.</p>}
        </div>
      </div>
      <div className="rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] p-4">
        <p className="mb-3 text-sm font-bold text-[#8b877d]">Pain Points</p>
        <ul className="list-disc space-y-2 pl-5 text-sm font-semibold text-black">
          {detailedData?.pain_points?.length
            ? detailedData.pain_points.slice(0, 5).map((p) => <li key={p}>{p}</li>)
            : <li>No pain points found.</li>}
        </ul>
      </div>
      <div className="rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] p-4">
        <p className="mb-3 text-sm font-bold text-[#a8620d]">Customer Desires</p>
        <ul className="list-disc space-y-2 pl-5 text-sm font-semibold text-black">
          {detailedData?.desires?.length
            ? detailedData.desires.slice(0, 5).map((d) => <li key={d}>{d}</li>)
            : <li>No desires found.</li>}
        </ul>
      </div>
      {/* NAYA: Groq ab "loved" bhi nikalta hai — jo cheezein customers ko pasand aayin. */}
      <div className="rounded-xl border border-[#bcd8c8] bg-[#eaf4ee] p-4">
        <p className="mb-3 text-sm font-bold text-[#12876b]">What Customers Love</p>
        <ul className="list-disc space-y-2 pl-5 text-sm font-semibold text-black">
          {detailedData?.loved?.length
            ? detailedData.loved.slice(0, 5).map((l) => <li key={l}>{l}</li>)
            : <li>No praise found.</li>}
        </ul>
      </div>
      <div className="rounded-xl border border-white/10 bg-black p-4 text-white shadow-xl shadow-black/10 lg:col-span-3">
        <p className="text-sm font-black text-white">Review Coverage</p>
        <p className="mt-2 text-4xl font-black leading-none text-white">
          {/* Har source ka jorr — naam gina kar NAHI. Pehle yahan sirf
              trustpilot + youtube hardcoded thay, to jab backend ne teesra
              source (youtube_reviews) bhejna shuru kiya to us ki comments
              is total mein chup-chaap ghayab rehtin. */}
          {Object.values(detailedData?.platforms ?? {}).reduce<number>(
            (sum, n) => sum + (Number(n) || 0),
            0,
          )}
        </p>
        <p className="mt-1 text-xs font-semibold text-white/70">
          items used for analysis
        </p>
      </div>
    </div>
  );
}