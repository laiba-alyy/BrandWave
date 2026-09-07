'use client'

/**
 * Dashboard ke charts.
 *
 * ── Usool: sirf ASLI, pehle se mehfooz data ────────────────────────────────
 * Har chart wahi dikhata hai jo DB mein already save hai — SEO audit ke factor
 * scores, sentiment run ka breakdown, catalogue ki category counts. Yahan koi
 * hisaab dobara nahi hota aur koi number farzi nahi banta.
 *
 * Isi wajah se yahan koi TIME-SERIES nahi hai: SEO audit har brand ke liye EK
 * hi row rakhta hai (run_seo_audit purani row update karta hai, nayi nahi
 * banata) aur sentiment ki har row aakhri run ka snapshot hai. "Pichle hafte
 * se +5%" jaisi line banane ke liye purana data chahiye hota, jo maujood hi
 * nahi — wo line khoobsurat lagti aur jhooti hoti.
 *
 * Jahan data na ho wahan chart ki jagah dostana khali haalat aati hai.
 *
 * ── recharts kyun, aur dynamic import kyun ─────────────────────────────────
 * Dashboard sab se ziyada khulne wala safha hai. recharts ka bundle chhota
 * nahi, is liye page ise `next/dynamic` se load karta hai (app/business/page.tsx)
 * — safhe ka dhancha aur numbers foran render hote hain, charts baad mein
 * aate hain.
 */

import type { ReactNode } from 'react'
import {
  Bar, BarChart, Cell, Pie, PieChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'

// ── Palette ────────────────────────────────────────────────────────────────
//
// Aath rang, jaan boojh kar chune hue: har ek doosre se saaf alag hai aur
// safed background par kaafi gehra hai (contrast >= 3:1). Pehla rang app ka
// apna amber hai, taake dashboard baqi platform se juda na lage.
//
// Ye rang SAJAWAT nahi hain — har chart mein rang ek maani rakhta hai aur
// legend/label ke saath hi aata hai.
/*
 * Ordered/categorical charts ka RAMP — ek hi hue, light se dark.
 *
 * Pehle yahan aath rangon ka rainbow tha (indigo, teal, rose, sky, emerald,
 * violet, orange). Wo dash.css ke usool ke bilkul khilaf tha, jo saaf likha
 * hai: "Teen rang, aur bas ... koi gradient, koi glow." Dashboard isi wajah se
 * scraping/SEO se alag duniya lagta tha.
 *
 * Ye saare charts (categories, emotions, sources, content mix) apni value ke
 * hisaab se SORTED aate hain, yani inka encoding pehle se MAGNITUDE hai,
 * identity nahi. Us soorat mein single-hue sequential ramp hi durust hai —
 * rainbow us tarteeb ko chhupa deta tha.
 *
 * VALIDATED (dataviz validator, light mode, surface #ffffff, --ordinal):
 *   lightness monotone PASS · adjacent dL PASS · light-end contrast 2.08:1 PASS
 *   · single hue (spread 5 deg) PASS
 * Sab se halka step jaan boojh kar #e5a94e par ruka hai: is se halka rang
 * safed card par 2:1 se neeche gir jata hai aur nazar hi nahi aata.
 */
export const CHART_COLORS = [
  '#e5a94e',
  '#d4901f',
  '#b0761a',
  '#8d5c13',
  '#6b450d',
  '#4a2e07',
]

/*
 * STATUS palette — good / warning / critical.
 *
 * Ye categorical hai (teen alag haalat, ek saath ek hi chart mein), is liye
 * ise CVD ke against pass hona zaroori tha. Purana emerald/amber/rose set
 * FAIL karta tha: rose vs emerald deuteranopia mein delta-E sirf 3.9 tha, yani
 * red-green blindness wale user ke liye "good" aur "needs work" ek hi rang.
 *
 * VALIDATED (dataviz validator, light, surface #ffffff, --pairs all):
 *   lightness band PASS · chroma floor PASS · CVD separation deltaE 10.2
 *   (deutan) PASS · normal-vision 23.1 PASS · contrast >=3:1 PASS
 *
 * Rang hamesha label ya legend ke SAATH aata hai — kabhi akela nahi.
 */
const STATUS = {
  good: '#12876b',
  warning: '#d08a12',
  critical: '#96203f',
}

// Sentiment ke rang platform bhar mein ek jaise rehte hain. Neutral ab
// grey hai, blue nahi: positive/negative ek DIVERGING jori hai aur uska
// midpoint neutral hona chahiye, teesra hue nahi.
const SENTIMENT = {
  positive: STATUS.good,
  negative: STATUS.critical,
  neutral: '#8b877d',
}

// Audit health — wohi status palette.
const HEALTH = {
  good: STATUS.good,
  warning: STATUS.warning,
  needs_work: STATUS.critical,
}

/*
 * Emotions bhi value ke hisaab se sorted aate hain, magar in mein polarity ka
 * maani hai (happy vs angry), is liye khush/na-khush ko status palette se aur
 * darmiyani ko ramp se rang dete hain.
 */
const EMOTION_COLORS: Record<string, string> = {
  happy: STATUS.good,
  satisfied: '#3f9e83',
  excited: CHART_COLORS[0],
  neutral: '#8b877d',
  disappointed: '#b0761a',
  frustrated: '#a4553a',
  angry: STATUS.critical,
}

const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const num = (n: number) => n.toLocaleString()

// recharts ka Tooltip formatter `value`/`name` ko `ValueType | undefined` deta
// hai (kuch bhi ho sakta hai). Har chart mein wahi do line ki casting likhne ke
// bajaye ek chhota wrapper: andar ka function saaf number aur string dekhta hai.
const fmt =
  (f: (value: number, name: string) => [string, string]) =>
  (value: unknown, name: unknown): [string, string] =>
    f(Number(value ?? 0), String(name ?? ''))

// ── Panel chrome ───────────────────────────────────────────────────────────

/**
 * Har chart ka frame.
 *
 * `accent` sirf ek patli upar wali lakeer hai — poora card rangeen karne se
 * grid shor ban jata hai. Asli rang chart ke andar hai.
 */
export function ChartPanel({
  title, subtitle, action, className = '', children,
}: {
  title: string
  subtitle?: string
  /** Ab istemal nahi hota — dekho neeche ka comment. Call sites tootne se bachane ke liye type mein rakha hai. */
  accent?: string
  action?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={`dsh__card ${className}`} style={{ position: 'relative' }}>
      {/* `accent` ab jaan boojh kar nahi lagta. Har panel par module ke rang
          ki 3px patti thi — barah panels, barah rang, aur dash.css ka "ek hi
          accent" wala usool khatam. Prop signature waisi hi rakhi hai taake
          call sites na toote. */}
      <div className="dsh__cardhead" style={{ alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <h3>{title}</h3>
          {subtitle && <p className="dsh__sectionnote" style={{ marginTop: 3 }}>{subtitle}</p>}
        </div>
        {action}
      </div>
      <div style={{ padding: '16px 20px 20px' }}>{children}</div>
    </section>
  )
}

/** Data na hone par — khali chart ya farzi numbers ke bajaye saaf jumla. */
export function ChartEmpty({ message, cta }: { message: string; cta?: ReactNode }) {
  return (
    <div className="dsh__empty" style={{ minHeight: 180, padding: '24px 20px' }}>
      <p>{message}</p>
      {cta}
    </div>
  )
}

/** recharts ka default tooltip safed-par-safed hota hai; ye padha jata hai. */
const tooltipStyle = {
  contentStyle: {
    borderRadius: 12,
    border: '1px solid #e7e4dc',
    boxShadow: '0 8px 24px -12px rgba(16,24,40,0.25)',
    fontSize: 12,
    padding: '8px 12px',
  },
  labelStyle: { fontWeight: 700, color: '#14140f', marginBottom: 2 },
  itemStyle: { color: '#56544d' },
} as const

// ── 1. SEO score gauge ─────────────────────────────────────────────────────

/**
 * Overall SEO score, 0-100.
 *
 * Rang score ke sath badalta hai (hara/amber/surkh) — number aur rang ek hi
 * baat kehte hain, to rang-andha user bhi number parh leta hai.
 */
export function SeoGauge({ score, lastAudit }: { score: number; lastAudit?: string | null }) {
  const color = score >= 70 ? STATUS.good : score >= 40 ? STATUS.warning : STATUS.critical
  const band = score >= 70 ? 'Good' : score >= 40 ? 'Needs attention' : 'Needs work'
  const data = [{ name: 'score', value: score, fill: color }]

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={196}>
        <RadialBarChart
          data={data}
          startAngle={220}
          endAngle={-40}
          innerRadius="72%"
          outerRadius="100%"
          barSize={16}
        >
          {/* domain fix hai taake bar hamesha 0-100 ka hissa dikhaye */}
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} axisLine={false} />
          <RadialBar background={{ fill: '#e7e4dc' }} dataKey="value" cornerRadius={10} />
        </RadialBarChart>
      </ResponsiveContainer>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center pt-4">
        <span className="text-[38px] font-bold leading-none tracking-tight text-[#14140f] tabular-nums">
          {Math.round(score)}
        </span>
        <span className="mt-1 text-[10px] font-bold uppercase tracking-[0.12em]" style={{ color }}>
          {band}
        </span>
      </div>

      {lastAudit && (
        <p className="mt-1 text-center text-[11px] text-[#8b877d]">
          Last audited {new Date(lastAudit).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
        </p>
      )}
    </div>
  )
}

// ── 2. SEO factor radar ────────────────────────────────────────────────────

export interface SeoFactor { key: string; label: string; score: number }

/**
 * Paanch (ya chaar) factors ek saath — kaunsa peeche hai, ek nazar mein.
 *
 * Radar is liye ke saare factors ek hi paimane (0-100) par hain aur maqsad
 * SHAKL dekhna hai, tanha values nahi. Image alt tab hi aata hai jab store ki
 * feed alt text deti ho — backend usay bahar rakh deta hai (dekho seo_auditor).
 */
export function SeoFactorRadar({ factors }: { factors: SeoFactor[] }) {
  return (
    <ResponsiveContainer width="100%" height={208}>
      <RadarChart data={factors} outerRadius="72%">
        <PolarGrid stroke="#e7e4dc" />
        <PolarAngleAxis dataKey="label" tick={{ fill: '#56544d', fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        <Radar
          name="Score"
          dataKey="score"
          stroke="#b0761a"
          fill="#b0761a"
          fillOpacity={0.24}
          strokeWidth={2}
        />
        <Tooltip {...tooltipStyle} formatter={fmt(v => [`${v}/100`, 'Score'])} />
      </RadarChart>
    </ResponsiveContainer>
  )
}

// ── 3. Audit health ────────────────────────────────────────────────────────

export interface AuditHealth { good: number; warning: number; needs_work: number }

/**
 * Audit ke natije: kitne products theek, kitne warning, kitne kaam maangte.
 *
 * Segmented bar — teen hisse ek poore ka, jo pie se behtar parha jata hai jab
 * hisse bare farq ke hon. Har hisse par ginti bhi likhi hai, sirf rang nahi.
 */
export function AuditHealthBar({ health, coverage }: {
  health: AuditHealth
  coverage?: { audited: number; catalogue: number } | null
}) {
  const total = health.good + health.warning + health.needs_work || 1
  const rows = [
    { key: 'good', label: 'Good', value: health.good, color: HEALTH.good },
    { key: 'warning', label: 'Warning', value: health.warning, color: HEALTH.warning },
    { key: 'needs_work', label: 'Needs work', value: health.needs_work, color: HEALTH.needs_work },
  ]

  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-[#e7e4dc]">
        {rows.map((r) => (
          <span
            key={r.key}
            title={`${r.label}: ${num(r.value)}`}
            style={{ width: `${(r.value / total) * 100}%`, backgroundColor: r.color }}
          />
        ))}
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3">
        {rows.map((r) => (
          <div key={r.key}>
            <dt className="flex items-center gap-1.5 text-[11px] font-medium text-[#8b877d]">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: r.color }} />
              {r.label}
            </dt>
            <dd className="mt-1 text-[19px] font-bold leading-none tracking-tight text-[#14140f] tabular-nums">
              {num(r.value)}
            </dd>
            <dd className="mt-0.5 text-[11px] text-[#8b877d] tabular-nums">
              {Math.round((r.value / total) * 100)}%
            </dd>
          </div>
        ))}
      </dl>

      {coverage && coverage.catalogue > coverage.audited && (
        <p className="mt-4 border-t border-[#e7e4dc] pt-3 text-[11px] leading-relaxed text-[#8b877d]">
          Checked <b className="font-semibold text-[#56544d]">{num(coverage.audited)}</b> of{' '}
          {num(coverage.catalogue)} products — a representative sample, not the whole catalogue.
        </p>
      )}
    </div>
  )
}

// ── 4. Sentiment donut ─────────────────────────────────────────────────────

export interface SentimentBreakdown {
  positive: number; negative: number; neutral: number; total: number
  positive_percent: number; negative_percent: number; neutral_percent: number
}

export function SentimentDonutChart({ breakdown }: { breakdown: SentimentBreakdown }) {
  const data = [
    { name: 'Positive', value: breakdown.positive, color: SENTIMENT.positive },
    { name: 'Negative', value: breakdown.negative, color: SENTIMENT.negative },
    { name: 'Neutral', value: breakdown.neutral, color: SENTIMENT.neutral },
  ].filter((d) => d.value > 0)

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={188}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="66%"
            outerRadius="94%"
            paddingAngle={2}
            stroke="none"
          >
            {data.map((d) => <Cell key={d.name} fill={d.color} />)}
          </Pie>
          <Tooltip
            {...tooltipStyle}
            formatter={fmt((v, n) => [`${num(v)} reviews`, n])}
          />
        </PieChart>
      </ResponsiveContainer>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[30px] font-bold leading-none tracking-tight text-[#14140f] tabular-nums">
          {breakdown.positive_percent}%
        </span>
        <span className="mt-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[#12876b]">
          Positive
        </span>
      </div>

      <ul className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1.5">
        {data.map((d) => (
          <li key={d.name} className="flex items-center gap-1.5 text-[11px] text-[#8b877d]">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: d.color }} />
            {d.name}
            <span className="font-semibold text-[#56544d] tabular-nums">{num(d.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── 5. Emotions ────────────────────────────────────────────────────────────

export interface EmotionCount { key: string; count: number }

export function EmotionsChart({ emotions }: { emotions: EmotionCount[] }) {
  const data = emotions
    .slice(0, 7)
    .map((e) => ({
      name: titleCase(e.key),
      count: e.count,
      color: EMOTION_COLORS[e.key.toLowerCase()] ?? '#8b877d',
    }))

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 6, right: 26, top: 4, bottom: 4 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={86}
          tickLine={false}
          axisLine={false}
          tick={{ fill: '#56544d', fontSize: 11 }}
        />
        <Tooltip {...tooltipStyle} cursor={{ fill: '#fbfaf7' }}
          formatter={fmt(v => [`${num(v)} mentions`, 'Count'])} />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={14}>
          {data.map((d) => <Cell key={d.name} fill={d.color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 6. Catalogue categories ────────────────────────────────────────────────

export interface CategoryCount { name: string; count: number }

/**
 * Catalogue kis cheez se bhara hai.
 *
 * Chhoti categories ko "Other" mein jama kar dete hain — 40 slices ka donut
 * kuch nahi kehta. Legend mein poori ginti aur hissa dono hain.
 *
 * Do baatein jin par dhyan chahiye:
 *
 *  1. Scraper khud bhi "other" naam ki category deta hai. Agar wo top 6 mein
 *     aa jaye aur hum uske saath apna roll-up bhi jorh dein to donut mein DO
 *     "Other" slices ban jate hain aur React ki key bhi takra jati hai. Is
 *     liye roll-up maujooda "Other" mein hi jama hota hai.
 *
 *  2. Alag alag raw names ek hi display name ban sakte hain ("home_decor"
 *     aur "home decor" dono "Home Decor"). Is liye React key display name
 *     nahi — har row ki apni `key` hai.
 */
export function CategoryDonut({ categories }: { categories: CategoryCount[] }) {
  const total = categories.reduce((sum, c) => sum + c.count, 0) || 1
  const restCount = categories.slice(6).reduce((sum, c) => sum + c.count, 0)

  const data = categories.slice(0, 6).map((c, i) => ({
    key: `cat-${i}`,
    name: titleCase(c.name.replace(/_/g, ' ')),
    value: c.count,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }))

  if (restCount > 0) {
    const existingOther = data.find((d) => d.name.toLowerCase() === 'other')
    if (existingOther) existingOther.value += restCount
    else data.push({ key: 'cat-other', name: 'Other', value: restCount, color: '#c9c5bb' })
  }

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center">
      <div className="relative w-full max-w-[190px] shrink-0">
        <ResponsiveContainer width="100%" height={176}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius="60%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="none"
            >
              {data.map((d) => <Cell key={d.key} fill={d.color} />)}
            </Pie>
            <Tooltip
              {...tooltipStyle}
              formatter={fmt((v, n) => [
                `${num(v)} products · ${Math.round((v / total) * 100)}%`, n,
              ])}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[22px] font-bold leading-none tracking-tight text-[#14140f] tabular-nums">
            {num(total)}
          </span>
          <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-[#8b877d]">
            Products
          </span>
        </div>
      </div>

      <ul className="w-full min-w-0 space-y-2">
        {data.map((d) => (
          <li key={d.key} className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: d.color }} />
            <span className="min-w-0 flex-1 truncate text-[12px] text-[#56544d]">{d.name}</span>
            <span className="shrink-0 text-[12px] font-semibold text-[#14140f] tabular-nums">
              {num(d.value)}
            </span>
            <span className="w-9 shrink-0 text-right text-[11px] text-[#8b877d] tabular-nums">
              {Math.round((d.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── 7. Keyword frequency (sentiment) ───────────────────────────────────────

export interface KeywordFreq { keyword: string; frequency: number }

/** Reviews mein sab se zyada dohraye jane wale alfaz. */
export function ReviewKeywords({ keywords }: { keywords: KeywordFreq[] }) {
  const data = keywords.slice(0, 8).map((k, i) => ({
    key: `kw-${i}`,
    name: k.keyword,
    count: k.frequency,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }))

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 28)}>
      <BarChart data={data} layout="vertical" margin={{ left: 6, right: 26, top: 4, bottom: 4 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          tickLine={false}
          axisLine={false}
          tick={{ fill: '#56544d', fontSize: 11 }}
        />
        <Tooltip {...tooltipStyle} cursor={{ fill: '#fbfaf7' }}
          formatter={fmt(v => [`mentioned ${num(v)}×`, 'Frequency'])} />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={13}>
          {data.map((d) => <Cell key={d.key} fill={d.color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 8. Content mix ─────────────────────────────────────────────────────────

export interface ContentItem { key: string; label: string; count: number }

export function ContentMixChart({ items }: { items: ContentItem[] }) {
  const data = items.map((it, i) => ({
    ...it,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }))
  const allZero = data.every((d) => d.count === 0)

  if (allZero) {
    return (
      <ChartEmpty message="Nothing generated yet. Blog posts, keywords and ads will show up here as you create them." />
    )
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ left: -18, right: 8, top: 12, bottom: 4 }}>
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={{ stroke: '#e7e4dc' }}
          tick={{ fill: '#56544d', fontSize: 11 }}
          interval={0}
        />
        <YAxis tickLine={false} axisLine={false} tick={{ fill: '#8b877d', fontSize: 11 }} allowDecimals={false} />
        <Tooltip {...tooltipStyle} cursor={{ fill: '#fbfaf7' }}
          formatter={fmt(v => [num(v), 'Created'])} />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} barSize={38}>
          {data.map((d) => <Cell key={d.key} fill={d.color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 9. Review sources ──────────────────────────────────────────────────────

export interface SourceCount { name: string; count: number }

const SOURCE_COLORS: Record<string, string> = {
  trustpilot: '#00B67A',  // Trustpilot ka apna hara
  youtube: '#FF0033',     // YouTube ka apna surkh
}

/** Reviews kahan se aaye — platform ke apne rang, pehchanne mein aasan. */
export function ReviewSources({ sources }: { sources: SourceCount[] }) {
  const total = sources.reduce((s, x) => s + x.count, 0) || 1

  return (
    <ul className="space-y-3.5">
      {sources.map((s, i) => {
        const color = SOURCE_COLORS[s.name.toLowerCase()] ?? CHART_COLORS[i % CHART_COLORS.length]
        const pct = Math.round((s.count / total) * 100)
        return (
          <li key={s.name}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="text-[12px] font-medium text-[#56544d]">{titleCase(s.name)}</span>
              <span className="text-[12px] text-[#8b877d] tabular-nums">
                <b className="font-semibold text-[#14140f]">{num(s.count)}</b> · {pct}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#e7e4dc]">
              <span
                className="block h-full rounded-full transition-[width] duration-700"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

// ── 10. Keyword opportunity ────────────────────────────────────────────────

export interface TopKeyword {
  keyword: string
  score?: number | null
  volume?: number | null
  validated?: boolean
}

/**
 * Behtareen keywords, opportunity score ke saath.
 *
 * `validated` ka matlab hai Google Autocomplete ne is phrase ki tasdeeq ki —
 * yani log waqai ye likhte hain. Wo nishani dikhana zaroori hai, warna
 * AI-generated aur asli-verified keyword ek jaise lagte hain.
 */
export function KeywordOpportunity({ keywords }: { keywords: TopKeyword[] }) {
  const max = Math.max(...keywords.map((k) => k.score ?? 0), 1)

  return (
    <ul className="space-y-2.5">
      {keywords.slice(0, 6).map((k, i) => {
        const score = k.score ?? 0
        const color = CHART_COLORS[i % CHART_COLORS.length]
        return (
          <li key={`${k.keyword}-${i}`}>
            <div className="mb-1 flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-[12px] text-[#56544d]" title={k.keyword}>
                {k.keyword}
              </span>
              {k.validated && (
                <span
                  title="Confirmed by Google Autocomplete — real people search this"
                  className="shrink-0 rounded bg-[#eaf4ee] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[#12876b]"
                >
                  Verified
                </span>
              )}
              <span className="shrink-0 text-[11px] font-semibold text-[#14140f] tabular-nums">
                {Math.round(score)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[#e7e4dc]">
              <span
                className="block h-full rounded-full"
                style={{ width: `${(score / max) * 100}%`, backgroundColor: color }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

// ── 11. Theme chips (loved / pain points) ──────────────────────────────────

export function ThemeList({ items, tone }: { items: string[]; tone: 'loved' | 'pain' }) {
  const styles = tone === 'loved'
    ? { dot: STATUS.good, chip: 'bg-[#eaf4ee] text-[#12876b] border-[#bcd8c8]' }
    : { dot: STATUS.critical, chip: 'bg-[#fbeaec] text-[#96203f] border-[#e6c3c8]' }

  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li
          key={`${item}-${i}`}
          className={`flex items-start gap-2.5 rounded-xl border px-3 py-2.5 text-[12px] leading-relaxed ${styles.chip}`}
        >
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: styles.dot }} />
          <span className="min-w-0">{item}</span>
        </li>
      ))}
    </ul>
  )
}

// ── 12. Insights readiness ─────────────────────────────────────────────────

export interface InsightSource { key: string; label: string; ready: boolean }

export function InsightsReadiness({ sources }: { sources: InsightSource[] }) {
  const ready = sources.filter((s) => s.ready).length

  return (
    <div>
      <div className="mb-4 flex items-baseline gap-2">
        <span className="text-[30px] font-bold leading-none tracking-tight text-[#14140f] tabular-nums">
          {ready}
        </span>
        <span className="text-[13px] text-[#8b877d]">of {sources.length} data sources ready</span>
      </div>
      <ul className="space-y-2">
        {sources.map((s) => (
          <li key={s.key} className="flex items-center gap-2.5">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${
                s.ready ? 'bg-[#12876b]' : 'bg-[#d5d1c6]'
              }`}
            >
              {s.ready && (
                <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="#fff" strokeWidth="2.4">
                  <path d="M2.5 6.2l2.2 2.2 4.8-4.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </span>
            <span className={`text-[12px] ${s.ready ? 'text-[#56544d]' : 'text-[#8b877d]'}`}>
              {s.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
