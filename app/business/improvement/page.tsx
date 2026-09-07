'use client'

import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useActiveBrand } from '@/lib/useActiveBrand'
import { seoPost } from '@/lib/seoApi'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'

// ── Types ─────────────────────────────────────────────────────────────────────
interface Suggestion {
  problem?: string
  suggestion: string
  evidence: string
  priority: 'high' | 'medium' | 'low'
  area: string
  confidence: 'high' | 'medium' | 'low'
}

interface GrowthOpportunity {
  opportunity: string
  what_to_do: string
  evidence: string
  priority: 'high' | 'medium' | 'low'
  area: string
  confidence: 'high' | 'medium' | 'low'
}

interface ImprovementResult {
  suggestions: Suggestion[]
  growth_opportunities: GrowthOpportunity[]
  data_sources_used: string[]
  data_available: boolean
  insufficient_data_reason?: string | null
  brand_name?: string
  language?: Language
}

// ── Output language ──────────────────────────────────────────────────────────
// Only the human-facing text changes; evidence numbers stay in English.
type Language = 'english' | 'roman_urdu'

const LANGUAGES: { value: Language; label: string }[] = [
  { value: 'english',    label: 'English' },
  { value: 'roman_urdu', label: 'Roman Urdu' },
]

// ── Area config ──────────────────────────────────────────────────────────────
const AREA_LABELS: Record<string, { label: string }> = {
  delivery:             { label: 'Delivery & Shipping' },
  product_quality:      { label: 'Product Quality' },
  customer_service:     { label: 'Customer Service' },
  pricing:              { label: 'Pricing' },
  seo:                  { label: 'Search Visibility' },
  product_descriptions: { label: 'Product Descriptions' },
  images:               { label: 'Photos & Images' },
  tags:                 { label: 'Tags & Categories' },
  product_range:        { label: 'Product Range' },
  brand_positioning:    { label: 'Brand Positioning' },
  website:              { label: 'Website' },
}

/* Confidence ab badge tone se aata hai, apne alag rangon se nahi - wohi
   good/warn/neutral jo poore dashboard mein chalte hain. */
const CONFIDENCE_BADGE: Record<string, string> = {
  high:   'dsh__badge--good',
  medium: 'dsh__badge--warn',
  low:    '',
}

const CONFIDENCE_TEXT = {
  high:   'High confidence',
  medium: 'Moderate confidence',
  low:    'Low confidence',
}

const SOURCE_LABELS: Record<string, string> = {
  sentiment:    'Customer Reviews',
  seo_audit:    'SEO Audit',
  seo_keywords: 'Keyword Data',
  products:     'Product Catalogue',
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function BrandImprovementPage() {
  const { activeBrandId, userId, sessionChecked } = useActiveBrand()
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<ImprovementResult | null>(null)
  const [error, setError] = useState('')
  const [language, setLanguage] = useState<Language>('english')

  /*
   * Ye page mount par koi request nahi bhejta — user "Generate" dabata hai.
   * Pehle sirf session + `users` row ke liye do Supabase round-trips lagte the
   * aur tab tak safha spinner dikhata tha. Ab wo dono context mein hain, to
   * loading sirf itni der hai jitni der session resolve hoti hai (aksar foran,
   * kyunke provider root par hai aur navigation par dobara mount nahi hota).
   */
  const loading = !sessionChecked

  const handleGenerate = async (lang: Language = language) => {
    setGenerating(true)
    setError('')
    try {
      const data = await seoPost<{ success: boolean } & ImprovementResult>(
        '/api/brand-improvement/generate', userId, activeBrandId,
        { language: lang }
      )
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  // Switching language re-runs the analysis in that language. A toggle that
  // silently did nothing until you pressed Generate would read as broken —
  // and results must never be half English, half Roman Urdu.
  const handleLanguageChange = (lang: Language) => {
    if (lang === language || generating) return
    setLanguage(lang)
    if (result) handleGenerate(lang)
  }

  // Group suggestions by area, sorted by highest priority first
  const grouped = useMemo(() => {
    if (!result?.suggestions) return {}
    const groups: Record<string, Suggestion[]> = {}
    for (const s of result.suggestions) {
      const area = s.area || 'website'
      if (!groups[area]) groups[area] = []
      groups[area].push(s)
    }
    const priorityOrder = { high: 0, medium: 1, low: 2 }
    return Object.fromEntries(
      Object.entries(groups).sort(([, a], [, b]) => {
        const aMax = Math.min(...a.map(s => priorityOrder[s.priority] ?? 2))
        const bMax = Math.min(...b.map(s => priorityOrder[s.priority] ?? 2))
        return aMax - bMax
      })
    )
  }, [result])

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">
        <div className="dsh__top">
          <div>
            <h1>Brand Insights</h1>
            <p className="dsh__sub">Data-backed suggestions to improve your brand</p>
          </div>
          <div className="dsh__topactions">
            {/* Output language — English default, Roman Urdu opt-in */}
            <div
              role="group"
              aria-label="Insights language"
              style={{ display: 'flex', alignItems: 'center', padding: 2, borderRadius: 9,
                       border: '1px solid var(--line-2)', background: 'var(--paper-2)' }}
            >
              {LANGUAGES.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => handleLanguageChange(value)}
                  disabled={generating}
                  aria-pressed={language === value}
                  className={`dsh__btn dsh__btn--sm ${language === value ? 'dsh__btn--ink' : 'dsh__btn--ghost'}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <BrandSwitcher />
            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              onClick={() => handleGenerate()}
              disabled={generating || !activeBrandId}
              className="dsh__btn dsh__btn--amber dsh__btn--sm"
            >
              {generating ? (
                <>
                  <span className="dsh__spin" />
                  Analyzing
                </>
              ) : (
                <>Generate Insights</>
              )}
            </motion.button>
          </div>
        </div>

        <div className="dsh__body">
          <AnimatePresence mode="wait">
            {error && (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="dsh__note dsh__note--bad"
              >
                <span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {loading ? (
            <section className="dsh__card">
              <div style={{ padding: 20, display: 'grid', gap: 12 }}>
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="dsh__skel" style={{ height: 74 }} />
                ))}
              </div>
            </section>
          ) : !result ? (
            <EmptyState generating={generating} onGenerate={() => handleGenerate()} hasBrand={!!activeBrandId} />
          ) : !result.data_available ? (
            <InsufficientData reason={result.insufficient_data_reason} onGenerate={() => handleGenerate()} />
          ) : result.suggestions.length === 0 ? (
            <NoSuggestions reason={result.insufficient_data_reason} onGenerate={() => handleGenerate()} />
          ) : (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              style={{ display: 'flex', flexDirection: 'column', gap: 20 }}
            >
              {/* Data sources */}
              {result.data_sources_used.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="dsh__eyebrow" style={{ marginRight: 4 }}>Based on</span>
                  {result.data_sources_used.map(src => (
                    <span key={src} className="dsh__badge dsh__badge--warn">
                      {SOURCE_LABELS[src] || src}
                    </span>
                  ))}
                </div>
              )}

              {/* Suggestions grouped by area */}
              <div className="dsh__section">
                <div>
                  <p className="dsh__eyebrow">Action plan</p>
                  <h2>Problems and what to do</h2>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
                {Object.entries(grouped).map(([area, suggestions]) => {
                  const areaConfig = AREA_LABELS[area] || { label: area }
                  return (
                    <section key={area}>
                      <div className="dsh__section" style={{ marginBottom: 12 }}>
                        <div><p className="dsh__eyebrow">{areaConfig.label}</p></div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {suggestions.map((s, i) => (
                          <SuggestionCard key={i} suggestion={s} index={i} />
                        ))}
                      </div>
                    </section>
                  )
                })}
              </div>

              {/* ── Growth Opportunities ── */}
              {result.growth_opportunities && result.growth_opportunities.length > 0 && (
                <div className="mt-14">
                  {/* Divider */}
                  <div className="flex items-center gap-4 mb-8">
                    <div className="h-px flex-1 bg-linear-to-r from-transparent via-[#f0a63c]/50 to-transparent" />
                    <div className="h-px flex-1 bg-linear-to-r from-transparent via-[#f0a63c]/50 to-transparent" />
                  </div>

                  {/* Section header */}
                  <div className="dsh__section" style={{ marginBottom: 16 }}>
                    <div>
                      <p className="dsh__eyebrow">Next moves</p>
                      <h2>Growth opportunities</h2>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <GrowthCard growth={result.growth_opportunities} />
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </div>
      </div>
    </main>
  )
}

// ── Components ────────────────────────────────────────────────────────────────

function SuggestionCard({ suggestion: s, index }: { suggestion: Suggestion; index: number }) {
  const confBadge = CONFIDENCE_BADGE[s.confidence] ?? CONFIDENCE_BADGE.medium
  const confText = CONFIDENCE_TEXT[s.confidence]   || CONFIDENCE_TEXT.medium
  const problem  = s.problem || s.suggestion

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className="dsh__grid dsh__grid--2"
    >
      <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end' }}>
        <span className={`dsh__badge ${confBadge}`}>{confText}</span>
      </div>

      {/* Problem — what's wrong */}
      <div className="dsh__card" style={{ padding: 20 }}>
        <p className="dsh__eyebrow" style={{ marginBottom: 7 }}>Problem</p>
        <p style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--text)' }}>{problem}</p>
      </div>

      {/* Suggestion — what to do */}
      <div className="dsh__card" style={{ padding: 20 }}>
        <p className="dsh__eyebrow" style={{ marginBottom: 7, color: 'var(--amber-deep)' }}>What to do</p>
        <p style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--text)' }}>{s.suggestion}</p>
        <p style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--line)',
                    fontSize: 12.5, lineHeight: 1.6, color: 'var(--text-mute)' }}>{s.evidence}</p>
      </div>
    </motion.div>
  )
}

function GrowthCard({ growth }: { growth: GrowthOpportunity[] }) {

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
        {growth.map((g, index) => {
          const confBadge = CONFIDENCE_BADGE[g.confidence] ?? CONFIDENCE_BADGE.medium
          const confText = CONFIDENCE_TEXT[g.confidence] || CONFIDENCE_TEXT.medium
          const areaConf = AREA_LABELS[g.area] || { label: g.area }

          return (
            <div key={`${g.area}-${index}`}>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center',
                            justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
                <span className="dsh__badge dsh__badge--warn">{areaConf.label}</span>
                <span className={`dsh__badge ${confBadge}`}>{confText}</span>
              </div>
              <div className="dsh__grid dsh__grid--2">
                <div className="dsh__card" style={{ padding: 20 }}>
                  <p className="dsh__eyebrow" style={{ marginBottom: 7 }}>Opportunity</p>
                  <p style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--text)' }}>{g.opportunity}</p>
                </div>
                <div className="dsh__card" style={{ padding: 20 }}>
                  <p className="dsh__eyebrow" style={{ marginBottom: 7, color: 'var(--amber-deep)' }}>What to do</p>
                  <p style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--text)' }}>{g.what_to_do}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </motion.div>
  )
}

function EmptyState({ generating, onGenerate, hasBrand }: { generating: boolean; onGenerate: () => void; hasBrand: boolean }) {
  return (
    <section className="dsh__card">
      <div className="dsh__empty">
        <span className="dsh__emptymark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
            <path d="M12 3v2M12 19v2M3 12h2M19 12h2M6 6l1.5 1.5M16.5 16.5 18 18M18 6l-1.5 1.5M7.5 16.5 6 18" />
            <circle cx="12" cy="12" r="3.5" />
          </svg>
        </span>
        <h3>Brand Insights</h3>
        <p>
          Practical, data-backed suggestions built from your real customer reviews,
          SEO data and product catalogue.
        </p>
        {!hasBrand ? (
          <p style={{ color: 'var(--amber-deep)' }}>Select a brand from the switcher above to get started.</p>
        ) : (
          <button onClick={onGenerate} disabled={generating}
            className="dsh__btn dsh__btn--amber" style={{ marginTop: 8 }}>
            {generating ? <><span className="dsh__spin" />Analyzing</> : 'Generate insights'}
          </button>
        )}
      </div>
    </section>
  )
}

function InsufficientData({ reason, onGenerate }: { reason?: string | null; onGenerate: () => void }) {
  const steps = [
    { step: '1', title: 'Web Scraping', desc: 'Set up your brand and import products (required)' },
    { step: '2', title: 'Sentiment Analysis', desc: 'Analyze customer reviews from Trustpilot and YouTube' },
    { step: '3', title: 'SEO Optimization', desc: 'Generate keywords and run an SEO audit' },
  ]

  return (
    <section className="dsh__card">
      <div className="dsh__empty">
        <h3>Not enough data yet</h3>
        <p>
          {reason || 'We need a bit more data before we can give you meaningful advice.'}
        </p>
      </div>
      <div style={{ borderTop: '1px solid var(--line)', padding: '18px 20px 22px' }}>
        <p className="dsh__eyebrow" style={{ marginBottom: 14 }}>How to unlock richer insights</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {steps.map(item => (
            <div key={item.step} style={{ display: 'flex', alignItems: 'flex-start', gap: 11 }}>
              <span className="dsh__badge dsh__badge--ink">{item.step}</span>
              <div>
                <p style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)' }}>{item.title}</p>
                <p style={{ fontSize: 12.5, color: 'var(--text-mute)' }}>{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
        <button onClick={onGenerate} className="dsh__btn dsh__btn--amber dsh__btn--sm" style={{ marginTop: 18 }}>
          Try again
        </button>
      </div>
    </section>
  )
}

function NoSuggestions({ reason, onGenerate }: { reason?: string | null; onGenerate: () => void }) {
  return (
    <section className="dsh__card">
      <div className="dsh__empty">
        <span className="dsh__emptymark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="m5 12.5 4.5 4.5L19 7.5" />
          </svg>
        </span>
        <h3>Looking good</h3>
        <p>
          {reason || 'Based on the available data your brand is in great shape - no significant issues to address right now.'}
        </p>
        <button onClick={onGenerate} className="dsh__btn dsh__btn--ghost" style={{ marginTop: 8 }}>
          Re-analyze
        </button>
      </div>
    </section>
  )
}
