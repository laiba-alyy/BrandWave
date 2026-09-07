'use client'

/**
 * Dashboard ka hero band aur uske neeche wali KPI tiles.
 *
 * Hero ka kaam ek hi hai: pehli nazar mein batana ke "ye kaunsa brand hai aur
 * is waqt uska haal kya hai". Isi liye brand ka naam, uska store URL, market
 * aur chaar sab se ahem numbers — sab ek hi band mein hain.
 *
 * Rang: gehra slate gradient. Baqi safha safed hai, to ye band safhe ka
 * "anchor" ban jata hai aur numbers us par khul kar parhe jate hain. Amber
 * glow app ke apne accent (#f0a63c) se aata hai.
 */

import type { ReactNode } from 'react'
import { motion } from 'framer-motion'


// ── Hero ───────────────────────────────────────────────────────────────────

export interface HeroStat {
  label: string
  value: string
  /** Chhoti si line jo number ka matlab kholti hai. */
  hint?: string
}

export function DashboardHero({
  brandName, websiteUrl, chips, stats,
}: {
  brandName: string
  websiteUrl?: string | null
  chips: string[]
  stats: HeroStat[]
}) {
  const domain = (websiteUrl || '').replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="dsh__hero"
      style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}
    >
      {/* Do narm glows hata diye gaye hain. dash.css saaf kehti hai
          "koi gradient, koi glow" — aur wo indigo glow poore dashboard mein
          akela aisa rang tha jo palette se bahar tha. */}
      <div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: '14px 24px' }}>
          <div style={{ minWidth: 0 }}>
            <p className="dsh__eyebrow" style={{ color: '#8d8a80' }}>Brand overview</p>
            <h2 style={{ marginTop: 8 }}>{brandName}</h2>
            {domain && (
              <a
                href={websiteUrl || '#'}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  marginTop: 6, display: 'inline-flex', alignItems: 'center', gap: 6,
                  fontSize: 13, color: '#a8a49a',
                }}
              >
                {domain}
                <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"
                    strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </a>
            )}
          </div>

          {chips.length > 0 && (
            <ul style={{ display: 'flex', flexWrap: 'wrap', gap: 6, listStyle: 'none' }}>
              {chips.map((chip) => (
                <li
                  key={chip}
                  style={{
                    padding: '4px 11px', borderRadius: 999, fontSize: 11,
                    border: '1px solid rgba(255,255,255,0.12)',
                    background: 'rgba(255,255,255,0.07)', color: '#cfcbc1',
                  }}
                >
                  {chip}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* KPI strip — hero ke andar, taake "brand + haal" ek hi cheez lage */}
        <dl
          className="dsh__herofoot"
          style={{ marginTop: 24, paddingTop: 22, borderTop: '1px solid rgba(255,255,255,0.12)', gap: '18px 40px' }}
        >
          {stats.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.08 + i * 0.06 }}
              className="dsh__herostat"
              style={{ minWidth: 0 }}
            >
              <dt><span>{s.label}</span></dt>
              <dd><strong>{s.value}</strong></dd>
              {s.hint && (
                <dd style={{ marginTop: 5, fontSize: 11, color: '#8d8a80' }}>{s.hint}</dd>
              )}
            </motion.div>
          ))}
        </dl>
      </div>
    </motion.section>
  )
}

// ── Stat tiles ─────────────────────────────────────────────────────────────

export interface StatTile {
  key: string
  label: string
  value: string
  hint?: string
  /** Icon tile ka rang — har module ka apna. */
  accent: string
  icon: ReactNode
}

/**
 * Chhoti stat tiles.
 *
 * Rang sirf icon tile par hai; card khud safed rehta hai. Chaar poore rangeen
 * cards ek qatar mein shor bante hain aur asli number peeche chala jata hai.
 */
export function StatTiles({ tiles }: { tiles: StatTile[] }) {
  return (
    <div className="dsh__stats dsh__stats--4">
      {tiles.map((t, i) => (
        <motion.div
          key={t.key}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: i * 0.05 }}
          className="dsh__stat"
          style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}
        >
          {/* Purana version har tile par module ke rang ka blurred blob aur
              tinted icon rakhta tha — chaar alag rang ek qatar mein. Ab tile
              paper hai aur icon ink; rang sirf charts mein maani rakhta hai. */}
          <div style={{ minWidth: 0 }}>
            <span>{t.label}</span>
            <strong>{t.value}</strong>
            {t.hint && <small>{t.hint}</small>}
          </div>
          <span
            aria-hidden="true"
            style={{
              display: 'grid', placeItems: 'center', flex: 'none',
              width: 34, height: 34, borderRadius: 9,
              border: '1px solid var(--line)', background: 'var(--paper-2)',
              color: 'var(--text-dim)',
            }}
          >
            {t.icon}
          </span>
        </motion.div>
      ))}
    </div>
  )
}

// ── Section heading ────────────────────────────────────────────────────────

/**
 * Safhe ke hisson ke darmiyan saans.
 *
 * Dashboard ab lamba hai, is liye har hisse ka apna unwan hai — warna 12
 * panels ek doosre mein ghul jate hain aur user ko dhoondna parta hai.
 */
export function SectionHeading({
  title, subtitle, action,
}: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="dsh__section">
      <div>
        <h2>{title}</h2>
        {subtitle && <p className="dsh__sectionnote">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

// ── Skeletons ──────────────────────────────────────────────────────────────

export function HeroSkeleton() {
  return <div className="dsh__skel" style={{ height: 228, borderRadius: 14 }} />
}

export function PanelSkeleton({ height = 268 }: { height?: number }) {
  return <div className="dsh__skel" style={{ height, borderRadius: 12 }} />
}
