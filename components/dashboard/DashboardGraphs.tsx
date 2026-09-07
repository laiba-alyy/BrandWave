'use client'

/**
 * Dashboard ke bare "hero" graphs — sentiment donut, emotions bars, SEO ring.
 *
 * ── Sirf ASLI data ─────────────────────────────────────────────────────────
 * Har graph wahi dikhata hai jo DB mein pehle se mehfooz hai. Yahan koi
 * time-series ya trend NAHI hai, aur ho bhi nahi sakti: sentiment_analyses ki
 * har row aakhri run ka snapshot hai, hum tareekh-war history rakhte hi nahi.
 * "Pichle hafte se +5%" jaisi line banane ke liye purani run chahiye hoti,
 * jo maujood nahi — is liye wo line jhooti hoti. Jo cheez maujood nahi, us
 * ki jagah dostana paighaam aata hai, khali ya farzi chart nahi.
 *
 * ── Chart library kyun nahi ────────────────────────────────────────────────
 * recharts package.json mein hai, lekin abhi sirf sentiment ke safhe par load
 * hota hai. Dashboard sab se ziyada khulne wala safha hai; us ke bundle mein
 * poori chart library daalne ka koi faida nahi jab donut teen circles hai aur
 * bars chand rects. Inline SVG rakhne se landing page halka rehta hai.
 */

import type { ReactNode } from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'

export interface SentimentBreakdown {
  positive: number
  negative: number
  neutral: number
  total: number
  positive_percent: number
  negative_percent: number
  neutral_percent: number
}

export interface EmotionCount {
  key: string
  count: number
}

// ── Rang ───────────────────────────────────────────────────────────────────
// Positive/negative/neutral = hara / narm surkh / neela. Neutral ka #60a5fa
// wahi hai jo sentiment ke safhe par pehle se chal raha hai, taake do safhon
// par ek hi cheez ka rang alag na lage.
const SENTIMENT_COLORS = {
  positive: '#10b981', // emerald-500
  negative: '#f43f5e', // rose-500 — surkh, magar khaalis red se narm
  neutral: '#60a5fa',  // blue-400
}

// Har emotion ka apna rang. Aapas mein saaf farq rakhna zaroori hai warna
// bars ek doosre mein ghul jati hain.
const EMOTION_STYLES: Record<string, { label: string; color: string }> = {
  happy: { label: 'Happy', color: '#10b981' },        // emerald-500
  satisfied: { label: 'Satisfied', color: '#14b8a6' },// teal-500
  excited: { label: 'Excited', color: '#f59e0b' },    // amber-500
  neutral: { label: 'Neutral', color: '#60a5fa' },    // blue-400
  disappointed: { label: 'Disappointed', color: '#a78bfa' }, // violet-400
  frustrated: { label: 'Frustrated', color: '#fb923c' },     // orange-400
  angry: { label: 'Angry', color: '#f43f5e' },        // rose-500
}

/** Anjaan emotion key bhi tootni nahi chahiye — naam bana lo, rang neutral. */
function emotionStyle(key: string) {
  return (
    EMOTION_STYLES[key.toLowerCase()] ?? {
      label: key.charAt(0).toUpperCase() + key.slice(1),
      color: '#94a3b8', // slate-400
    }
  )
}

// ── Panel ka khol (donut/bars/ring sab isi mein baithte hain) ──────────────
function PanelShell({
  name, icon, tile, href, cta, children,
}: {
  name: string
  icon: ReactNode
  tile: string
  href: string
  cta: string
  children: ReactNode
}) {
  return (
    <Link href={href} className="block h-full">
      <div className="group flex h-full flex-col rounded-xl border border-[#e7e4dc] bg-white p-6 transition-all duration-300 hover:border-[#14140f] hover:shadow-[0_4px_20px_rgba(0,0,0,0.05)]">
        <div className="mb-5 flex items-center gap-2.5">
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${tile}`}>{icon}</span>
          <span className="text-xs font-bold uppercase tracking-wide text-[#8b877d]">{name}</span>
        </div>
        <div className="flex-1">{children}</div>
        <div className="mt-6 flex items-center gap-1 text-xs font-bold text-[#14140f]">
          <span>{cta}</span>
          <span className="transition-transform duration-200 group-hover:translate-x-1">→</span>
        </div>
      </div>
    </Link>
  )
}

export function GraphPanel(props: {
  name: string; icon: ReactNode; tile: string; href: string; children: ReactNode
}) {
  return <PanelShell {...props} cta="View" />
}

/**
 * Jab data hi na ho — chart ki jagah dawat.
 *
 * Sifar wala chart (khali donut, 0-length bars) module ko toota hua dikhata
 * hai. Ye panel usi jagah baithta hai aur seedha us module par le jata hai.
 */
export function GraphInvite({
  name, icon, tile, href, headline, body, cta = 'Start',
}: {
  name: string; icon: ReactNode; tile: string; href: string
  headline: string; body: string
  /** Default "Start" — magar jab analysis CHAL chuki ho aur us mein ye hissa
   *  na ho, to "Start" jhoot hai; wahan caller "View" bhejta hai. */
  cta?: string
}) {
  return (
    <PanelShell name={name} icon={icon} tile={tile} href={href} cta={cta}>
      <div className="flex h-full flex-col justify-center py-6">
        <p className="mb-1.5 text-lg font-bold leading-snug text-[#14140f]">{headline}</p>
        <p className="text-sm leading-relaxed text-[#8b877d]">{body}</p>
      </div>
    </PanelShell>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
//  1. SENTIMENT DONUT
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Positive/negative/neutral ka donut.
 *
 * Har slice ek circle hai jis ka `stroke-dasharray` "itna dikhao, itna
 * chhupao" kehta hai, aur `stroke-dashoffset` usay pichle slice ke baad shuru
 * karta hai. Is tarah teen circles mil kar ek donut ban jate hain — na koi
 * arc path ka hisaab, na koi library.
 *
 * Bilkul 0 wala slice JAAN BOOJH KAR skip hota hai: 0-length arc bhi
 * strokeLinecap ki wajah se ek nuqta chhorr jata hai, jo aise lagta hai jaise
 * us hisse mein kuch hai jab ke hai nahi.
 */
export function SentimentDonut({ breakdown }: { breakdown: SentimentBreakdown }) {
  // 124px JAAN BOOJH KAR — 148 par legend ke liye sirf ~143px bachte the aur
  // "Positive"/"Negative" truncate ho kar "Posi…" ban jate the. Chhota donut
  // legend ko poori jagah deta hai, aur SEO ring bhi isi naap ka hai taake
  // teenon panel ek qatar mein ek jaise lagen.
  const size = 124
  const stroke = 18
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius

  const slices = [
    { key: 'positive', label: 'Positive', count: breakdown.positive, percent: breakdown.positive_percent, color: SENTIMENT_COLORS.positive },
    { key: 'negative', label: 'Negative', count: breakdown.negative, percent: breakdown.negative_percent, color: SENTIMENT_COLORS.negative },
    { key: 'neutral', label: 'Neutral', count: breakdown.neutral, percent: breakdown.neutral_percent, color: SENTIMENT_COLORS.neutral },
  ]

  let cumulative = 0

  return (
    <div className="flex items-center gap-5">
      <motion.div
        className="relative shrink-0"
        style={{ width: size, height: size }}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.45, ease: 'easeOut', delay: 0.15 }}
      >
        <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke="#f3f4f6" strokeWidth={stroke}
          />
          {slices.map((s) => {
            if (s.count <= 0) return null
            const length = (s.count / breakdown.total) * circumference
            const offset = -cumulative
            cumulative += length
            return (
              <circle
                key={s.key}
                cx={size / 2} cy={size / 2} r={radius}
                fill="none" stroke={s.color} strokeWidth={stroke}
                strokeDasharray={`${length} ${circumference - length}`}
                strokeDashoffset={offset}
              />
            )
          })}
        </svg>
        {/* Donut ke beech mein wahi ginti jis par ye poora chart bana hai */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-black leading-none text-[#14140f]">
            {breakdown.total.toLocaleString()}
          </span>
          <span className="mt-1 text-[10px] font-bold uppercase tracking-wide text-[#8b877d]">
            reviews
          </span>
        </div>
      </motion.div>

      {/* Legend — har hissa apne asli percent ke saath.
          Per-slice ginti alag column mein NAHI hai: us se legend itni tang ho
          jati thi ke label hi kat jata tha. Total donut ke beech mein hai aur
          har row ka `title` us hisse ki asli ginti batata hai. */}
      <div className="min-w-0 flex-1 space-y-2.5">
        {slices.map((s) => (
          <div
            key={s.key}
            className="flex items-center gap-2.5"
            title={`${s.label}: ${s.count} of ${breakdown.total} reviews`}
          >
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="min-w-0 flex-1 truncate text-sm text-[#8b877d]">{s.label}</span>
            <span className="shrink-0 text-sm font-black tabular-nums text-[#14140f]">
              {s.percent}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
//  2. EMOTIONS BARS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Emotion counts — sab se buland pehle.
 *
 * Bar ki lambai sab se BARI ginti ke muqable mein hai (total ke nahi), warna
 * chhoti values dikhai hi na dein. Ginti bar ke aage likhi hai, to paimana
 * kabhi mubham nahi rehta.
 */
export function EmotionsBars({ emotions }: { emotions: EmotionCount[] }) {
  // Panel ki bulandi donut ke barabar rakhne ke liye — 6 se ziyada bars ho to
  // panel lamba ho kar grid ki qatar tor deta hai.
  const rows = emotions.slice(0, 6)
  const max = Math.max(...rows.map((e) => e.count), 1)

  return (
    <div className="space-y-3">
      {rows.map((e, i) => {
        const { label, color } = emotionStyle(e.key)
        return (
          <div key={e.key} className="flex items-center gap-3">
            <span className="w-[86px] shrink-0 truncate text-xs font-medium text-[#8b877d]">
              {label}
            </span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-[#fbfaf7]">
              <motion.div
                className="h-full rounded-full"
                style={{ backgroundColor: color }}
                initial={{ width: 0 }}
                animate={{ width: `${(e.count / max) * 100}%` }}
                transition={{ duration: 0.7, ease: 'easeOut', delay: 0.2 + i * 0.07 }}
              />
            </div>
            <span className="w-6 shrink-0 text-right text-sm font-black tabular-nums text-[#14140f]">
              {e.count}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
//  3. SEO SCORE RING
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Audit score 100 mein se — do circles, ek track ek arc.
 *
 * Yehi tareeqa SEO ke apne safhe ke ScoreRing ka hai (app/business/seo/
 * page.tsx), sirf chhota. -rotate-90 arc ko 12 baje se shuru karta hai.
 */
export function SeoScoreRing({ score, keywordCount }: { score: number; keywordCount: number }) {
  // Donut ke barabar naap — teen panels ek qatar mein ek jaise dikhne chahiye.
  const size = 124
  const stroke = 18
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(100, score))
  const offset = circumference - (pct / 100) * circumference

  return (
    <div className="flex items-center gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke="#f3f4f6" strokeWidth={stroke}
          />
          <motion.circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke="#0ea5e9" strokeWidth={stroke} strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1, ease: 'easeOut', delay: 0.2 }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-black leading-none text-[#14140f]">{Math.round(pct)}</span>
          <span className="mt-1 text-[10px] font-bold uppercase tracking-wide text-[#8b877d]">
            out of 100
          </span>
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-sm leading-relaxed text-[#8b877d]">
          Audit score across your product titles, descriptions, alt texts and tags.
        </p>
        <p className="mt-3 text-sm text-[#8b877d]">
          <span className="text-lg font-black text-[#14140f]">{keywordCount.toLocaleString()}</span>
          {' '}keywords tracked
        </p>
      </div>
    </div>
  )
}

/** Graph panels ke liye skeleton — chhote cards se lamba. */
export function GraphSkeleton() {
  return (
    <div className="h-[248px] rounded-xl border border-[#e7e4dc] bg-white p-6">
      <div className="mb-5 flex items-center gap-2.5">
        <div className="h-8 w-8 animate-pulse rounded-lg bg-[#e7e4dc]" />
        <div className="h-3 w-24 animate-pulse rounded bg-[#e7e4dc]" />
      </div>
      <div className="flex items-center gap-5">
        <div className="h-[124px] w-[124px] shrink-0 animate-pulse rounded-full bg-[#e7e4dc]" />
        <div className="flex-1 space-y-3">
          <div className="h-3 w-full animate-pulse rounded bg-[#e7e4dc]" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-[#e7e4dc]" />
          <div className="h-3 w-3/5 animate-pulse rounded bg-[#e7e4dc]" />
        </div>
      </div>
    </div>
  )
}
