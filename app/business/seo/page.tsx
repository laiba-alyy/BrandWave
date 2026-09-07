'use client'

import { useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import { seoGet, seoPost } from '@/lib/seoApi'
import { useCachedData, cacheInvalidate } from '@/lib/dataCache'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import Link from 'next/link'

interface AuditResult {
  seo_score: number
  title_score: number
  description_score: number
  image_alt_score: number
  image_alt_measurable?: boolean
  keyword_score: number
  tags_score: number
  total_products_audited: number
  total_catalogue_products: number | null
  good_count: number
  warning_count: number
  needs_work_count: number
  created_at: string
}

/* Score ring — ab paper/ink/amber palette par. Pehle ye emerald/amber/red
   teen rang badalta tha; reference mein sirf EK accent hai, is liye ring
   hamesha amber hai aur "achha ya bura" badge batata hai, rang nahi. */
function ScoreRing({ score, size = 148 }: { score: number; size?: number }) {
  const radius = size / 2 - 9
  const circumference = 2 * Math.PI * radius
  return (
    <svg width={size} height={size}>
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        stroke="rgba(255,255,255,0.13)" strokeWidth="7" fill="none"
      />
      <motion.circle
        cx={size / 2} cy={size / 2} r={radius}
        stroke="#f0a63c" strokeWidth="7" fill="none" strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: circumference - (score / 100) * circumference }}
        transition={{ duration: 1.1, ease: 'easeOut', delay: 0.15 }}
      />
    </svg>
  )
}

const seoFeatures = [
  {
    n: '01',
    title: 'SEO Audit',
    desc: 'Score every product title, description, alt text, keyword and tag against the checks below.',
    href: '/business/seo/audit',
  },
  {
    n: '02',
    title: 'Keywords',
    desc: 'Thirty AI-generated target keywords, validated against real Google Autocomplete demand.',
    href: '/business/seo/keywords',
  },
  {
    n: '03',
    title: 'AI Content',
    desc: 'Rewritten meta titles and descriptions, sized to the limits Google actually renders.',
    href: '/business/seo/content',
  },
  {
    n: '04',
    title: 'Blog Generator',
    desc: 'Long-form articles built around your target keywords, with meta title and description.',
    href: '/business/seo/blog',
  },
]

/*
 * "Ye audit dekhta kya hai" — ye section sirf page lamba karne ke liye nahi
 * hai. Score ek number hai; user ko ye jaanna chahiye ke wo number BANA kaise.
 * Har row wohi factor hai jo backend (seo_auditor.py) waqai measure karta hai,
 * is liye ye hamesha sach rehta hai.
 */
const CHECKS = [
  { k: 'Title quality', v: '50-60 characters, brand name plus the key product attributes' },
  { k: 'Descriptions', v: '150-160 characters, target keywords used naturally' },
  { k: 'Image alt text', v: 'Descriptive alt on every product image the feed publishes' },
  { k: 'Keyword coverage', v: 'Target keywords actually present in titles and descriptions' },
  { k: 'Tags', v: 'Category and attribute tags filled in, not left blank' },
]

/**
 * Audit poore catalogue par nahi chalta (backend MAX_AUDIT_PRODUCTS = 1000),
 * isliye label mein sample size aur catalogue size dono dikhate hain — warna
 * user samajhta hai ke score poore store ka hai.
 */
function coverageLabel(audit: AuditResult) {
  const total = audit.total_catalogue_products
  if (!total || total <= audit.total_products_audited) return 'Products audited'
  return `Audited of ${total.toLocaleString()}`
}

function scoreBand(score: number) {
  if (score >= 70) return { label: 'Healthy', cls: 'dsh__badge--good' }
  if (score >= 40) return { label: 'Needs attention', cls: 'dsh__badge--warn' }
  return { label: 'Needs work', cls: 'dsh__badge--bad' }
}

export default function SEODashboard() {
  const { activeBrandId, activeBrand, userId } = useActiveBrand()
  const [runningAudit, setRunningAudit] = useState(false)
  const [runError, setRunError] = useState('')

  /*
   * Audit CACHE se aata hai (dekho lib/dataCache). Keywords/Content par ja kar
   * wapas aane par ye foran render hoti hai, dobara network par nahi jati.
   * Key mein brand id shamil hai, to brand switch karne par apne aap alag
   * entry banti hai.
   */
  const auditKey = userId && activeBrandId != null
    ? `seo:audit:${activeBrandId}:${userId}`
    : null

  const {
    data: audit, loading: loadingAudit, error: loadError, mutate: setAudit,
  } = useCachedData<AuditResult | null>(
    auditKey,
    useCallback(async () => {
      // seoGet: 404 -> null (abhi koi audit nahi — ye empty state hai, error nahi).
      const data = await seoGet<{ data?: AuditResult }>(`/api/seo/audit/${userId}`, activeBrandId)
      return data?.data ?? null
    }, [userId, activeBrandId]),
  )

  const error = runError || loadError

  const handleRunAudit = async () => {
    setRunningAudit(true)
    setRunError('')
    try {
      // Keyword generation pehle chalti hai kyunke audit unhi target keywords
      // ke khilaf score karti hai. Iska natija dekhna zaroori hai — warna 429
      // par audit bina keywords ke chal jati aur user ko pata na chalta.
      await seoPost('/api/seo/keywords/generate', userId, activeBrandId)
      const data = await seoPost<{ data?: AuditResult }>('/api/seo/audit/run', userId, activeBrandId)
      setAudit(data.data ?? null)
      // Nayi audit ne do aur cached cheezein purani kar di hain.
      cacheInvalidate(`seo:keywords:${activeBrandId}:`)
      cacheInvalidate(`dashboard:summary:${activeBrandId}:`)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Could not run the SEO audit')
    } finally {
      setRunningAudit(false)
    }
  }

  const band = audit ? scoreBand(audit.seo_score) : null

  const factors = audit
    ? [
        { label: 'Title quality', score: audit.title_score },
        { label: 'Descriptions', score: audit.description_score },
        // Alt text tab hi dikhao jab store ki feed usay publish karti ho —
        // warna har brand ko hamesha 0% dikhta tha, jo uski ghalti nahi hai.
        ...(audit.image_alt_measurable === false
          ? []
          : [{ label: 'Image alt texts', score: audit.image_alt_score }]),
        { label: 'Keyword coverage', score: audit.keyword_score },
        { label: 'Tags', score: audit.tags_score },
      ]
    : []

  // Sab se kamzor teen factors — "ab kya karein" ka jawab isi se banta hai.
  const weakest = [...factors].sort((a, b) => (a.score || 0) - (b.score || 0)).slice(0, 3)

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">

        <div className="dsh__top">
          <div>
            <h1>SEO Optimization{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}</h1>
            <p className="dsh__sub">Audit, optimize and grow your store search visibility</p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            <button
              onClick={handleRunAudit}
              disabled={runningAudit}
              className="dsh__btn dsh__btn--amber dsh__btn--sm"
            >
              {runningAudit
                ? <><span className="dsh__spin" />Running</>
                : audit ? 'Re-run audit' : 'Run SEO audit'}
            </button>
          </div>
        </div>

        <div className="dsh__body">

          {error && (
            <div className="dsh__note dsh__note--bad">
              <span>{error}</span>
            </div>
          )}

          {/* ── Hero: poore page ka sab se ahem number ───────────────── */}
          <section className="dsh__hero">
            <div className="dsh__ring">
              <ScoreRing score={audit?.seo_score || 0} />
              <div className="dsh__ringval">
                <b>{loadingAudit ? '—' : Math.round(audit?.seo_score || 0)}</b>
                <span>/ 100</span>
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <h2>SEO health score</h2>
                {band && <span className={`dsh__badge ${band.cls}`}>{band.label}</span>}
              </div>

              <p className="dsh__herometa">
                {loadingAudit
                  ? 'Loading your latest audit…'
                  : audit
                    ? `Last audited ${new Date(audit.created_at).toLocaleDateString(undefined, {
                        day: 'numeric', month: 'short', year: 'numeric',
                      })} · ${audit.total_products_audited.toLocaleString()} products sampled`
                    : 'No audit has been run for this brand yet. Run one to score your catalogue.'}
              </p>

              {audit && (
                <div className="dsh__herofoot">
                  <div className="dsh__herostat">
                    <span>Good</span>
                    <strong>{audit.good_count.toLocaleString()}</strong>
                  </div>
                  <div className="dsh__herostat">
                    <span>Warning</span>
                    <strong>{audit.warning_count.toLocaleString()}</strong>
                  </div>
                  <div className="dsh__herostat">
                    <span>Needs work</span>
                    <strong>{audit.needs_work_count.toLocaleString()}</strong>
                  </div>
                  <div className="dsh__herostat">
                    <span>{coverageLabel(audit)}</span>
                    <strong>{audit.total_products_audited.toLocaleString()}</strong>
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* ── Score breakdown + next steps ─────────────────────────── */}
          {audit && (
            <>
              <div className="dsh__section">
                <div>
                  <p className="dsh__eyebrow">Breakdown</p>
                  <h2>What is driving the score</h2>
                </div>
              </div>

              <div className="dsh__grid dsh__grid--2">
                <section className="dsh__card">
                  <div className="dsh__cardhead"><h3>Factor scores</h3></div>
                  <div style={{ padding: '18px 20px 22px' }}>
                    {factors.map(f => (
                      <div className="dsh__meter" key={f.label}>
                        <div className="dsh__meterhead">
                          <span>{f.label}</span>
                          <b>{Math.round(f.score || 0)}%</b>
                        </div>
                        <div className="dsh__metertrack">
                          <motion.div
                            className={`dsh__meterfill${(f.score || 0) < 40 ? ' dsh__meterfill--amber' : ''}`}
                            initial={{ width: 0 }}
                            animate={{ width: `${Math.max(0, Math.min(100, f.score || 0))}%` }}
                            transition={{ duration: 0.8, delay: 0.2 }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="dsh__card">
                  <div className="dsh__cardhead"><h3>Where to start</h3></div>
                  <div style={{ padding: '6px 20px 14px' }}>
                    {weakest.map((f, i) => (
                      <div className="dsh__kv" key={f.label}>
                        <dt>
                          <span className="dsh__badge dsh__badge--ink" style={{ marginRight: 9 }}>
                            {String(i + 1).padStart(2, '0')}
                          </span>
                          {f.label}
                        </dt>
                        <dd>{Math.round(f.score || 0)}%</dd>
                      </div>
                    ))}
                    <p className="dsh__sectionnote" style={{ marginTop: 12 }}>
                      Your three weakest factors. Generate AI content to fix titles and
                      descriptions, or review the full audit for per-product detail.
                    </p>
                    <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
                      <Link href="/business/seo/content" className="dsh__btn dsh__btn--ink dsh__btn--sm">
                        Fix with AI content
                      </Link>
                      <Link href="/business/seo/audit" className="dsh__btn dsh__btn--ghost dsh__btn--sm">
                        Full audit
                      </Link>
                    </div>
                  </div>
                </section>
              </div>
            </>
          )}

          {/* ── Module navigation ────────────────────────────────────── */}
          <div className="dsh__section">
            <div>
              <p className="dsh__eyebrow">Workspace</p>
              <h2>SEO tools</h2>
            </div>
          </div>

          <div className="dsh__grid dsh__grid--4">
            {seoFeatures.map(f => (
              <Link key={f.href} href={f.href} className="dsh__mod">
                <div className="dsh__modtop">
                  <h3>{f.title}</h3>
                  <span className="dsh__badge">{f.n}</span>
                </div>
                <p>{f.desc}</p>
                <span className="dsh__modgo">Open →</span>
              </Link>
            ))}
          </div>

          {/* ── Methodology: score kaise banta hai ───────────────────── */}
          <div className="dsh__section">
            <div>
              <p className="dsh__eyebrow">Methodology</p>
              <h2>What the audit checks</h2>
              <p className="dsh__sectionnote">
                Every product in the sample is scored against these five factors.
              </p>
            </div>
          </div>

          <section className="dsh__card">
            <div style={{ padding: '6px 20px 16px' }}>
              {CHECKS.map(c => (
                <div className="dsh__kv" key={c.k}>
                  <dt style={{ color: 'var(--text)', fontWeight: 600 }}>{c.k}</dt>
                  <dd style={{ fontFamily: 'var(--f-body)', fontSize: 13, color: 'var(--text-dim)', textAlign: 'right', maxWidth: '52ch' }}>
                    {c.v}
                  </dd>
                </div>
              ))}
            </div>
          </section>

          {audit && audit.total_catalogue_products
            && audit.total_catalogue_products > audit.total_products_audited && (
            <div className="dsh__note">
              <span>
                Scored on a {audit.total_products_audited.toLocaleString()}-product sample
                of your {audit.total_catalogue_products.toLocaleString()}-product catalogue.
                The sample is representative, so the score tracks the whole store.
              </span>
            </div>
          )}

        </div>
      </div>
    </main>
  )
}
