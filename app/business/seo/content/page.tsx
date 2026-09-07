'use client'

import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import { seoGet, seoPost } from '@/lib/seoApi'
import { useCachedData } from '@/lib/dataCache'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import Link from 'next/link'

interface Recommendation {
  original_name: string
  original_title: string
  original_description: string
  optimized_title: string
  optimized_description: string
  optimized_title_length: number
  optimized_description_length: number
}

/* Google title ~50-60 aur description ~150-160 chars render karta hai. Length
   ko badge se dikhana bataata hai ke value in hudood ke andar hai ya nahi. */
const lengthTone = (len: number, min: number, max: number) =>
  len >= min && len <= max ? 'dsh__badge--good' : 'dsh__badge--warn'

/* Before/after ka ek block. Pehle ye rose/green inline styles par tha; ab
   wohi paper card, aur farq badge se batta hai na ke background rang se. */
function Diff({
  label, before, after, len, min, max, copied, onCopy,
}: {
  label: string
  before: string
  after: string
  len: number
  min: number
  max: number
  copied: boolean
  onCopy: () => void
}) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
        <p className="dsh__eyebrow">{label}</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span className={`dsh__badge ${lengthTone(len, min, max)}`}>
            {len} chars · target {min}–{max}
          </span>
          <button onClick={onCopy} className="dsh__link">
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>

      <div className="dsh__grid dsh__grid--2">
        <div style={{ padding: 14, borderRadius: 10, border: '1px solid var(--line)', background: 'var(--paper-2)' }}>
          <p className="dsh__eyebrow" style={{ marginBottom: 7 }}>Before</p>
          <p style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-mute)' }}>
            {before || 'Nothing set'}
          </p>
        </div>
        <div style={{ padding: 14, borderRadius: 10, border: '1px solid var(--amber-line)', background: 'var(--amber-tint)' }}>
          <p className="dsh__eyebrow" style={{ marginBottom: 7, color: 'var(--amber-deep)' }}>After</p>
          <p style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text)' }}>{after}</p>
        </div>
      </div>
    </div>
  )
}

export default function SEOContentPage() {
  const { activeBrandId, activeBrand, userId } = useActiveBrand()
  const [genError, setGenError] = useState('')
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  /*
   * Cache se (dekho lib/dataCache): dobara is page par aane par data FORAN
   * dikhta hai, spinner ke baghair, aur taza value background mein aati hai.
   */
  const {
    data: recommendationData, loading, error: loadError, mutate: setRecommendations,
  } = useCachedData<Recommendation[]>(
    userId && activeBrandId != null ? `seo:content:${activeBrandId}:${userId}` : null,
    useCallback(async () => {
      // 404 = abhi koi audit nahi chali; seoGet us par null deta hai, error nahi.
      const data = await seoGet<{ data?: { ai_recommendations?: unknown } }>(
        `/api/seo/audit/${userId}`, activeBrandId
      )
      return (data?.data?.ai_recommendations as Recommendation[]) || []
    }, [userId, activeBrandId]),
  )

  const recommendations = recommendationData ?? []

  // Load ki nakami bhi wahi banner dikhata hai jo generate ki nakami dikhata hai.
  const shownError = genError || loadError

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const data = await seoPost<{ data?: unknown[] }>(
        '/api/seo/content/generate', userId, activeBrandId
      )
      setRecommendations((data.data || []) as Recommendation[])
      setGenError('')
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Content generation failed')
    }
    finally { setGenerating(false) }
  }

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }

  const titlesInRange = recommendations.filter(
    r => r.optimized_title_length >= 50 && r.optimized_title_length <= 60
  ).length

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">

        <div className="dsh__top">
          <div>
            <Link href="/business/seo" className="dsh__link">← SEO</Link>
            <h1 style={{ marginTop: 6 }}>
              AI Content Optimizer{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}
            </h1>
            <p className="dsh__sub">Rewritten meta titles and descriptions for your products</p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="dsh__btn dsh__btn--amber dsh__btn--sm"
            >
              {generating
                ? <><span className="dsh__spin" />Generating</>
                : recommendations.length ? 'Regenerate' : 'Generate content'}
            </button>
          </div>
        </div>

        <div className="dsh__body">

          {shownError && (
            <div className="dsh__note dsh__note--bad"><span>{shownError}</span></div>
          )}

          {loading ? (
            <section className="dsh__card">
              <div style={{ padding: 20, display: 'grid', gap: 10 }}>
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="dsh__skel" style={{ height: 46 }} />
                ))}
              </div>
            </section>
          ) : recommendations.length === 0 ? (
            <section className="dsh__card">
              <div className="dsh__empty">
                <span className="dsh__emptymark">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                    <path d="M5 6h14M5 12h14M5 18h8" />
                  </svg>
                </span>
                <h3>No AI content yet</h3>
                <p>
                  Run the SEO audit first so the model knows your target keywords,
                  then generate optimized titles and descriptions.
                </p>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="dsh__btn dsh__btn--amber"
                  style={{ marginTop: 8 }}
                >
                  {generating ? <><span className="dsh__spin" />Generating</> : 'Generate AI content'}
                </button>
              </div>
            </section>
          ) : (
            <>
              <section className="dsh__stats">
                <div className="dsh__stat">
                  <span>Products optimized</span>
                  <strong>{recommendations.length}</strong>
                  <small>titles and descriptions rewritten</small>
                </div>
                <div className="dsh__stat">
                  <span>Titles in range</span>
                  <strong>{titlesInRange}</strong>
                  <small>50–60 characters</small>
                </div>
                <div className="dsh__stat">
                  <span>Ready to paste</span>
                  <strong>{recommendations.length * 2}</strong>
                  <small>fields for your Shopify editor</small>
                </div>
              </section>

              <div className="dsh__note">
                <span>
                  Copy each field into your Shopify product editor under the SEO
                  section. Titles render best at 50–60 characters, descriptions at
                  150–160 — anything longer gets truncated in search results.
                </span>
              </div>

              <div className="dsh__section">
                <div>
                  <p className="dsh__eyebrow">Results</p>
                  <h2>Optimized products</h2>
                  <p className="dsh__sectionnote">Open a product to compare before and after.</p>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {recommendations.map((rec, i) => (
                  <section className="dsh__card" key={i}>
                    <button
                      onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                      style={{ width: '100%', textAlign: 'left', display: 'block' }}
                    >
                      <div className="dsh__cardhead">
                        <div style={{ minWidth: 0 }}>
                          <h3 style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {rec.original_name}
                          </h3>
                          <p style={{
                            marginTop: 3, fontSize: 12.5, color: 'var(--text-mute)',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {rec.optimized_title}
                          </p>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 'none' }}>
                          <span className="dsh__badge dsh__badge--ink">Optimized</span>
                          <motion.span
                            animate={{ rotate: expandedIdx === i ? 180 : 0 }}
                            style={{ fontSize: 10, color: 'var(--text-mute)' }}
                          >
                            ▼
                          </motion.span>
                        </div>
                      </div>
                    </button>

                    <AnimatePresence>
                      {expandedIdx === i && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          style={{ overflow: 'hidden', borderTop: '1px solid var(--line)' }}
                        >
                          <div style={{ padding: 20, display: 'grid', gap: 22 }}>
                            <Diff
                              label="Meta title"
                              before={rec.original_title}
                              after={rec.optimized_title}
                              len={rec.optimized_title_length}
                              min={50} max={60}
                              copied={copied === `t${i}`}
                              onCopy={() => handleCopy(rec.optimized_title, `t${i}`)}
                            />
                            <Diff
                              label="Meta description"
                              before={rec.original_description}
                              after={rec.optimized_description}
                              len={rec.optimized_description_length}
                              min={150} max={160}
                              copied={copied === `d${i}`}
                              onCopy={() => handleCopy(rec.optimized_description, `d${i}`)}
                            />
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </section>
                ))}
              </div>
            </>
          )}

        </div>
      </div>
    </main>
  )
}
