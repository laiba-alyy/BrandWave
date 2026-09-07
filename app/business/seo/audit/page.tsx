'use client'

import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { authHeaders } from '@/lib/authHeaders'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import { seoGet, seoPost } from '@/lib/seoApi'
import { useCachedData, cacheInvalidate } from '@/lib/dataCache'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import Link from 'next/link'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Issue {
  product_name: string
  issue: string
  severity: 'Good' | 'Warning' | 'Needs Work'
  recommendation: string | null
}

interface AuditResult {
  id: number
  seo_score: number
  title_score: number
  description_score: number
  image_alt_score: number
  // false = is store ki Shopify feed alt text publish hi nahi karti, to
  // ye factor score se bahar hai (0% dikhana gumraah kun tha).
  image_alt_measurable?: boolean
  keyword_score: number
  tags_score: number
  title_issues: Issue[]
  description_issues: Issue[]
  image_alt_issues: Issue[]
  keyword_issues: Issue[]
  tags_issues: Issue[]
  total_products_audited: number
  total_catalogue_products: number | null
  good_count: number
  warning_count: number
  needs_work_count: number
  suggested_keywords: string[]
}

/* Severity ab teen alag rang-schemes nahi — ek badge, teen tones, wohi jo
   poore dashboard mein hain. */
const SEVERITY_BADGE: Record<Issue['severity'], string> = {
  Good: 'dsh__badge--good',
  Warning: 'dsh__badge--warn',
  'Needs Work': 'dsh__badge--bad',
}

function AuditSection({
  title, score, issues, notMeasurable, notMeasurableNote,
}: {
  title: string
  score: number
  issues: Issue[]
  notMeasurable?: boolean
  notMeasurableNote?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const problems = issues.filter(i => i.severity !== 'Good')

  // Jo factor measure hi nahi ho sakta, usay 0% ke sath dikhana brand par
  // ilzam lagana hai. Uski jagah neutral 'Not measurable' state.
  if (notMeasurable) {
    return (
      <section className="dsh__card">
        <div className="dsh__cardhead">
          <h3>{title}</h3>
          <span className="dsh__badge">Not measurable</span>
        </div>
        <p style={{ padding: '14px 20px 18px', fontSize: 13, color: 'var(--text-mute)', lineHeight: 1.6 }}>
          {notMeasurableNote}
        </p>
      </section>
    )
  }

  return (
    <section className="dsh__card">
      <button
        onClick={() => setExpanded(!expanded)}
        style={{ width: '100%', textAlign: 'left', display: 'block' }}
      >
        <div className="dsh__cardhead">
          <h3>{title}</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="dsh__badge">
              {problems.length === 0 ? 'All clear' : `${problems.length} issues`}
            </span>
            <span style={{ fontFamily: 'var(--f-mono)', fontSize: 12.5, color: 'var(--text)' }}>
              {Math.round(score)}%
            </span>
            <motion.span
              animate={{ rotate: expanded ? 180 : 0 }}
              style={{ fontSize: 10, color: 'var(--text-mute)' }}
            >
              ▼
            </motion.span>
          </div>
        </div>
        <div style={{ padding: '14px 20px' }}>
          <div className="dsh__metertrack">
            <motion.div
              className={`dsh__meterfill${score < 40 ? ' dsh__meterfill--amber' : ''}`}
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(0, Math.min(100, score))}%` }}
              transition={{ duration: 0.8 }}
            />
          </div>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: 'hidden', borderTop: '1px solid var(--line)' }}
          >
            {problems.length === 0 ? (
              <div className="dsh__empty" style={{ padding: '34px 24px' }}>
                <p>Every product in the sample passed this check.</p>
              </div>
            ) : (
              <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                {problems.slice(0, 20).map((issue, i) => (
                  <div className="dsh__row" key={i}>
                    <div className="dsh__rowmain">
                      <b>{issue.product_name}</b>
                      <span>{issue.issue}</span>
                      {issue.recommendation && (
                        <span style={{ color: 'var(--amber-deep)' }}>{issue.recommendation}</span>
                      )}
                    </div>
                    <div className="dsh__rowactions">
                      <span className={`dsh__badge ${SEVERITY_BADGE[issue.severity]}`}>
                        {issue.severity}
                      </span>
                    </div>
                  </div>
                ))}
                {problems.length > 20 && (
                  <p style={{ padding: '13px 20px', fontSize: 12.5, color: 'var(--text-mute)' }}>
                    Showing the first 20 of {problems.length}. Export the PDF for the full list.
                  </p>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

export default function SEOAuditPage() {
  const { activeBrandId, activeBrand, userId } = useActiveBrand()
  const [running, setRunning] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [runError, setRunError] = useState('')

  /*
   * Cache se (dekho lib/dataCache): dobara is page par aane par data FORAN
   * dikhta hai, spinner ke baghair, aur taza value background mein aati hai.
   */
  const {
    data: audit, loading, error: loadError, mutate: setAudit,
  } = useCachedData<AuditResult | null>(
    userId && activeBrandId != null ? `seo:audit:${activeBrandId}:${userId}` : null,
    useCallback(async () => {
      const data = await seoGet<{ data?: AuditResult }>(`/api/seo/audit/${userId}`, activeBrandId)
      return data?.data ?? null
    }, [userId, activeBrandId]),
  )

  // Run-audit ki nakami aur load ki nakami — dono ek hi banner mein.
  const error = runError || loadError
  const setError = setRunError

  const handleRunAudit = async () => {
    setRunning(true)
    setError('')
    try {
      // Keyword generation pehle chalti hai aur wahi request rate limit ke sab
      // se qareeb hoti hai. Pehle uska natija check hi nahi hota tha.
      await seoPost('/api/seo/keywords/generate', userId, activeBrandId)
      const data = await seoPost<{ data?: AuditResult }>('/api/seo/audit/run', userId, activeBrandId)
      setAudit(data.data ?? null)
      // Audit chalane se pehle keywords bhi regenerate hue, aur audit row ki
      // ai_recommendations reset hui — un dono pages ki cached copy ab purani
      // hai. Dashboard summary mein SEO score dikhta hai, wo bhi.
      cacheInvalidate(`seo:keywords:${activeBrandId}:`)
      cacheInvalidate(`seo:content:${activeBrandId}:`)
      cacheInvalidate(`dashboard:summary:${activeBrandId}:`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not run the SEO audit')
    }
    finally { setRunning(false) }
  }

  const handleDownloadPDF = async () => {
    setDownloading(true)
    setError('')
    try {
      if (activeBrandId == null) throw new Error('Pick a brand first, then export the PDF.')
      const res = await fetch(
        `${API_URL}/api/seo/audit/${userId}/export/pdf?brand_profile_id=${activeBrandId}`,
        { headers: await authHeaders() }
      )
      // PDF blob hai, JSON nahi — is liye ye seoGet se nahi jata, magar
      // nakami ab chup-chaap nahi guzarti.
      if (!res.ok) throw new Error('Could not build the PDF. Run the audit first, then try again.')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'seo_audit.pdf'; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not download the PDF')
    }
    finally { setDownloading(false) }
  }

  const coveragePct = audit && audit.total_catalogue_products
    ? Math.round((audit.total_products_audited / audit.total_catalogue_products) * 100)
    : null

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">

        <div className="dsh__top">
          <div>
            <Link href="/business/seo" className="dsh__link">← SEO</Link>
            <h1 style={{ marginTop: 6 }}>
              SEO Audit{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}
            </h1>
            <p className="dsh__sub">Per-product analysis of your store search health</p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            {audit && (
              <button
                onClick={handleDownloadPDF}
                disabled={downloading}
                className="dsh__btn dsh__btn--ghost dsh__btn--sm"
              >
                {downloading ? <><span className="dsh__spin" />Building</> : 'Export PDF'}
              </button>
            )}
            <button
              onClick={handleRunAudit}
              disabled={running}
              className="dsh__btn dsh__btn--amber dsh__btn--sm"
            >
              {running
                ? <><span className="dsh__spin" />Running</>
                : audit ? 'Re-run audit' : 'Run audit'}
            </button>
          </div>
        </div>

        <div className="dsh__body">

          {error && (
            <div className="dsh__note dsh__note--bad"><span>{error}</span></div>
          )}

          {loading ? (
            <section className="dsh__card">
              <div style={{ padding: 20, display: 'grid', gap: 12 }}>
                <div className="dsh__skel" style={{ height: 18, width: '32%' }} />
                <div className="dsh__skel" style={{ height: 110 }} />
                <div className="dsh__skel" style={{ height: 110 }} />
              </div>
            </section>
          ) : !audit ? (
            <section className="dsh__card">
              <div className="dsh__empty">
                <span className="dsh__emptymark">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                    <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
                  </svg>
                </span>
                <h3>No audit yet</h3>
                <p>
                  Run your first audit to score every product title, description,
                  alt text, keyword and tag in your catalogue.
                </p>
                <button
                  onClick={handleRunAudit}
                  disabled={running}
                  className="dsh__btn dsh__btn--amber"
                  style={{ marginTop: 8 }}
                >
                  {running ? <><span className="dsh__spin" />Running audit</> : 'Start SEO audit'}
                </button>
              </div>
            </section>
          ) : (
            <>
              <section className="dsh__stats dsh__stats--4">
                <div className="dsh__stat">
                  <span>SEO score</span>
                  <strong>{Math.round(audit.seo_score)}</strong>
                  <small>out of 100</small>
                </div>
                <div className="dsh__stat">
                  <span>Good</span>
                  <strong>{audit.good_count.toLocaleString()}</strong>
                  <small>products passing</small>
                </div>
                <div className="dsh__stat">
                  <span>Warning</span>
                  <strong>{audit.warning_count.toLocaleString()}</strong>
                  <small>need a small fix</small>
                </div>
                <div className="dsh__stat">
                  <span>Needs work</span>
                  <strong>{audit.needs_work_count.toLocaleString()}</strong>
                  <small>need rewriting</small>
                </div>
              </section>

              {/* Coverage note — audit poore catalogue par nahi chalti, isliye
                  saaf batao ke score kitne products ke sample par bana hai. */}
              {coveragePct != null && audit.total_catalogue_products != null
                && audit.total_catalogue_products > audit.total_products_audited && (
                <div className="dsh__note">
                  <span>
                    Audited {audit.total_products_audited.toLocaleString()} of{' '}
                    {audit.total_catalogue_products.toLocaleString()} products
                    ({coveragePct}% of your catalogue). Scores are based on this sample.
                  </span>
                </div>
              )}

              {audit.suggested_keywords?.length > 0 && (
                <section className="dsh__card">
                  <div className="dsh__cardhead">
                    <h3>Target keywords used in this audit</h3>
                    <span className="dsh__badge">{audit.suggested_keywords.length}</span>
                  </div>
                  <div style={{ padding: '16px 20px 18px', display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                    {audit.suggested_keywords.map((kw, i) => (
                      <span className="dsh__badge" key={i} style={{ textTransform: 'none', letterSpacing: 0 }}>
                        {kw}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              <div className="dsh__section">
                <div>
                  <p className="dsh__eyebrow">Findings</p>
                  <h2>Factor breakdown</h2>
                  <p className="dsh__sectionnote">Open any factor to see the products behind its score.</p>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <AuditSection title="Product title quality" score={audit.title_score} issues={audit.title_issues || []} />
                <AuditSection title="Meta description quality" score={audit.description_score} issues={audit.description_issues || []} />
                <AuditSection
                  title="Image alt texts"
                  score={audit.image_alt_score}
                  issues={audit.image_alt_issues || []}
                  notMeasurable={audit.image_alt_measurable === false}
                  notMeasurableNote="This store's Shopify product feed does not publish image alt text, so it cannot be checked here. Alt text set inside your theme is not exposed by the feed."
                />
                <AuditSection title="Keyword usage" score={audit.keyword_score} issues={audit.keyword_issues || []} />
                <AuditSection title="Tag completeness" score={audit.tags_score} issues={audit.tags_issues || []} />
              </div>
            </>
          )}

        </div>
      </div>
    </main>
  )
}
