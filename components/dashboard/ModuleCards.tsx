'use client'

/**
 * Dashboard ke CHHOTE module cards — shakl aur un ka text.
 *
 * Sentiment aur SEO ab yahan NAHI hain: un ke paas asli breakdown data hai,
 * to wo ooper bare graphs ban gaye (components/dashboard/DashboardGraphs.tsx).
 * Unhein yahan bhi rakhna wahi cheez do dafa dikhana hota.
 *
 * Yahan wo module hain jin ke paas ek GINTI hai, ratio nahi:
 * products, brand insights, image ads, video ads, chatbot.
 *
 * Har card ki do halatein hain:
 *   BHARA HUA — bara number + supporting line.
 *   KHALI     — bara "0" ke bajaye ek dawat ("Create your first ad").
 *
 * Khali halat par zor is liye hai ke naye user ka dashboard sifron ka grid
 * nahi hona chahiye; wo toota hua lagta hai, khali nahi.
 */

import type { ReactNode } from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import type { EmotionCount, SentimentBreakdown } from '@/components/dashboard/DashboardCharts'

// ── Backend ke jawab ki shakl (backend/api/routes/dashboard.py) ────────────
export interface InsightSource {
  key: string
  label: string
  ready: boolean
}

/** Ek SEO factor ka score — radar chart ke liye. */
export interface SeoFactor { key: string; label: string; score: number }

/** Audit ke natije ki ginti — segmented bar ke liye. */
export interface AuditHealth { good: number; warning: number; needs_work: number }

export interface TopKeyword {
  keyword: string
  score?: number | null
  volume?: number | null
  validated?: boolean
}

export interface CategoryCount { name: string; count: number }
export interface SourceCount { name: string; count: number }
export interface KeywordFreq { keyword: string; frequency: number }
export interface ContentItem { key: string; label: string; count: number }

export interface Summary {
  brand: {
    id: number
    business_name: string | null
    website_url: string
    platform: string | null
    logo_url?: string | null
    created_at?: string | null
  }
  modules: {
    sentiment: {
      available: boolean
      positive_percent?: number | null
      review_count?: number
      dominant_emotion?: string | null
      /** Donut ke liye — purani analysis rows par null ho sakta hai. */
      breakdown?: SentimentBreakdown | null
      /** Bars ke liye — sirf wo emotions jin ki ginti 0 se ooper hai. */
      emotions?: EmotionCount[]
      /** Reviews kahan se aaye — trustpilot / youtube. */
      sources?: SourceCount[]
      /** Reviews mein sab se zyada dohraye jane wale alfaz. */
      keywords?: KeywordFreq[]
      loved?: string[]
      pain_points?: string[]
    }
    seo: {
      available: boolean
      score?: number | null
      keyword_count?: number
      last_audit?: string | null
      /** image_alt tab hi aata hai jab store ki feed alt text deti ho. */
      factors?: SeoFactor[] | null
      health?: AuditHealth | null
      coverage?: { audited: number; catalogue: number } | null
      top_keywords?: TopKeyword[]
    }
    insights: { available: boolean; sources_ready: number; sources_total: number; sources?: InsightSource[] }
    products: {
      available: boolean
      count: number
      platform?: string | null
      categories?: CategoryCount[]
      price_range?: string | null
      store_country?: string | null
      store_currency?: string | null
    }
    image_ads: { available: boolean; count: number; latest?: string | null }
    video_ads: { available: boolean; count: number; latest?: string | null }
    chatbot: { available: boolean; bot_count?: number; active_count?: number; conversation_count?: number }
  }
  /** Blogs, keywords, image ads, video ads — content mix chart ke liye. */
  content_mix?: ContentItem[]
}

/** Card ka tayar-shuda content — ya to stat, ya dawat. */
export interface CardView {
  key: string
  name: string
  href: string
  icon: ReactNode
  /** Soft accent — sirf icon tile par. Cards khud safed rehte hain taake grid
   *  pur-sukoon lage; saat mukhtalif rangeen cards shor ban jate hain. */
  tile: string
  /** Bara number/stat, ya null agar module abhi khali hai. */
  value: string | null
  /** Stat ke neeche ki chhoti line. */
  support: string
  /** Khali module ke liye dostana dawat. */
  empty: string
  /** Chhota SVG visual — sirf bhare huay card par. */
  visual?: ReactNode
}

const num = (n: number) => n.toLocaleString()

const shortDate = (iso?: string | null) => {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

// ── Icons (sidebar wale hi stroke style mein) ──────────────────────────────
const icons = {
  sentiment: 'M7 8h10M7 12h4m1 8a9 9 0 100-18 9 9 0 000 18zm0 0c1.657 0 3-1.343 3-3H9c0 1.657 1.343 3 3 3z',
  emotions: 'M3 13h2l2 5 3-12 2 7h2m2 0h3',
  seo: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
  insights: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
  products: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
  imageAds: 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z',
  videoAds: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z',
  chatbot: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
}

function Icon({ d }: { d: string }) {
  return (
    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d={d} />
    </svg>
  )
}

/**
 * Har module ka icon + tile ka rang, ek jagah.
 *
 * Graph panels (DashboardGraphs) aur chhote cards dono yahan se lete hain,
 * taake sentiment ka rang do jagah alag alag na ho jaye.
 */
export const MODULE_VISUALS = {
  sentiment: { icon: <Icon d={icons.sentiment} />, tile: 'bg-[#eaf4ee] text-[#12876b]' },
  emotions: { icon: <Icon d={icons.emotions} />, tile: 'bg-[#fdf4e6] text-[#f0a63c]' },
  seo: { icon: <Icon d={icons.seo} />, tile: 'bg-[#fbfaf7] text-[#56544d]' },
} as const

// ── Insights ki chhoti bars ────────────────────────────────────────────────
/**
 * Chaar chhoti bars — har source ke liye ek.
 *
 * Barhti hui bulandi sirf shakl ke liye hai; MAANI rang mein hai — bhari
 * (amber) bar ka matlab wo source maujood hai, halki (grey) ka matlab abhi
 * nahi. Is liye har bar par uske source ka naam bhi `title` mein hai, warna
 * ye mehez sajawat lagti.
 */
function MiniBars({ sources, color }: { sources: InsightSource[]; color: string }) {
  const heights = [14, 21, 28, 35]

  return (
    <div className="flex h-[35px] shrink-0 items-end gap-1.5" aria-hidden="true">
      {sources.map((s, i) => (
        <motion.span
          key={s.key}
          title={`${s.label}: ${s.ready ? 'ready' : 'not yet'}`}
          className="w-1.5 rounded-full"
          style={{
            height: heights[i] ?? heights[heights.length - 1],
            backgroundColor: s.ready ? color : '#f3f4f6',
            // scaleY neeche se barhe, beech se nahi.
            transformOrigin: 'bottom',
          }}
          initial={{ scaleY: 0 }}
          animate={{ scaleY: 1 }}
          transition={{ duration: 0.4, ease: 'easeOut', delay: 0.25 + i * 0.06 }}
        />
      ))}
    </div>
  )
}

/**
 * Summary -> chhote cards.
 *
 * `summary` null ho sakta hai (abhi load nahi hui, ya request fail hui). Us
 * soorat mein har card apni dawat wali shakl mein aata hai — yani fail hone
 * par bhi safha kaam ka rehta hai, khali dabbon ka grid nahi banta.
 */
export function buildCards(summary: Summary | null, brandName: string): CardView[] {
  const m = summary?.modules

  // ── Brand Insights ──
  // Yahan suggestions ki ginti NAHI hai: brand_improvement apne nataij save
  // nahi karta, to us number ke liye har load par LLM chalana parta. Uski
  // jagah readiness dikhti hai — dekho backend route ka header.
  const ins = m?.insights
  const insightsValue = ins?.available ? `${ins.sources_ready}/${ins.sources_total}` : null
  const insightsSupport = ins?.available
    ? `data sources ready${ins.sources_ready === ins.sources_total ? ' — all set' : ''}`
    : 'Data-backed ideas for your brand'

  // ── Products ──
  const p = m?.products
  const productsValue = p?.available ? num(p.count) : null
  const productsSupport = p?.available
    ? `products${p.platform ? ` on ${p.platform}` : ''} · ${brandName}`
    : 'Import your catalogue to begin'

  // ── Image ads ──
  const ia = m?.image_ads
  const iaDate = shortDate(ia?.latest)
  const imageValue = ia?.available ? num(ia.count) : null
  const imageSupport = ia?.available
    ? `ads created${iaDate ? ` · latest ${iaDate}` : ''}`
    : 'Turn products into ad creatives'

  // ── Video ads ──
  const va = m?.video_ads
  const vaDate = shortDate(va?.latest)
  const videoValue = va?.available ? num(va.count) : null
  const videoSupport = va?.available
    ? `videos created${vaDate ? ` · latest ${vaDate}` : ''}`
    : 'Bring your products to life'

  // ── Chatbot ──
  // Bot maujood hai lekin abhi koi baat-cheet nahi hui — ye KHALI nahi hai,
  // is liye card status dikhata hai, dawat nahi. Warna user ka banaya hua bot
  // dashboard par ghayab lagta.
  const c = m?.chatbot
  const conversations = c?.conversation_count ?? 0
  const chatbotValue = c?.available
    ? conversations > 0
      ? num(conversations)
      : c.active_count
        ? 'Live'
        : 'Paused'
    : null
  const chatbotSupport = c?.available
    ? conversations > 0
      ? `conversations · ${c.active_count ?? 0} of ${c.bot_count ?? 0} bots active`
      : `${c.bot_count ?? 0} bot${(c.bot_count ?? 0) === 1 ? '' : 's'} · no conversations yet`
    : 'Answer customers automatically'

  return [
    {
      key: 'products', name: 'Products', href: '/business/scraping',
      icon: <Icon d={icons.products} />, tile: 'bg-[#fbfaf7] text-[#56544d]',
      value: productsValue, support: productsSupport, empty: 'Import your products',
    },
    {
      key: 'insights', name: 'Brand Insights', href: '/business/improvement',
      icon: <Icon d={icons.insights} />, tile: 'bg-[#fdf4e6] text-[#a8620d]',
      value: insightsValue, support: insightsSupport, empty: 'Unlock brand insights',
      // Purane payload mein `sources` sirf tayar keys ki list thi. Agar wahan
      // se object-list na aaye to bars chhod dete hain — card phir bhi apna
      // number dikhata hai, toot-ta nahi.
      visual: ins?.available && Array.isArray(ins.sources) && typeof ins.sources[0] === 'object'
        ? <MiniBars sources={ins.sources} color="#f59e0b" />
        : undefined,
    },
    {
      key: 'image_ads', name: 'Image Ads', href: '/business/ads-generation',
      icon: <Icon d={icons.imageAds} />, tile: 'bg-[#fdf4e6] text-[#f0a63c]',
      value: imageValue, support: imageSupport, empty: 'Create your first ad',
    },
    {
      key: 'video_ads', name: 'Video Ads', href: '/business/video-ads',
      icon: <Icon d={icons.videoAds} />, tile: 'bg-[#fbeaec] text-[#96203f]',
      value: videoValue, support: videoSupport, empty: 'Create your first video',
    },
    {
      key: 'chatbot', name: 'Chatbot', href: '/business/chatbot',
      icon: <Icon d={icons.chatbot} />, tile: 'bg-[#fdf4e6] text-[#f0a63c]',
      value: chatbotValue, support: chatbotSupport, empty: 'Build your first chatbot',
    },
  ]
}

// ── Ek card ────────────────────────────────────────────────────────────────
export function ModuleCard({ card, index }: { card: CardView; index: number }) {
  const filled = card.value !== null

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: 'easeOut' }}
    >
      <Link href={card.href} className="dsh__mod" style={{ height: '100%' }}>
        {/* Sar — module ka naam. Purana version har card par module ke rang ka
            tinted icon tile rakhta tha (emerald / violet / sky); ab wo ink hai,
            kyunke rang ka maani sirf charts mein hai. */}
        <div className="dsh__modtop">
          <h3>{card.name}</h3>
          <span
            aria-hidden="true"
            style={{
              display: 'grid', placeItems: 'center', flex: 'none',
              width: 30, height: 30, borderRadius: 8,
              border: '1px solid var(--line)', background: 'var(--paper-2)',
              color: 'var(--text-dim)',
            }}
          >
            {card.icon}
          </span>
        </div>

        {/* Jism — stat + visual, ya dawat */}
        {filled ? (
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ minWidth: 0 }}>
              <p style={{
                fontFamily: 'var(--f-display)', fontSize: 30, fontWeight: 600,
                lineHeight: 1, letterSpacing: '-0.02em', color: 'var(--text)',
                marginBottom: 7,
              }}>
                {card.value}
              </p>
              <p>{card.support}</p>
            </div>
            {card.visual}
          </div>
        ) : (
          <>
            {/* Khali module: bara "0" ki jagah dawat — ye asal mein AGLA qadam
                hai jo user ko uthana chahiye. */}
            <p style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--text)', lineHeight: 1.45 }}>
              {card.empty}
            </p>
            <p>{card.support}</p>
          </>
        )}

        <span className="dsh__modgo">{filled ? 'View' : 'Start'} →</span>
      </Link>
    </motion.div>
  )
}

export function CardSkeleton() {
  return <div className="dsh__skel" style={{ height: 168, borderRadius: 12 }} />
}

/** Brand hi na ho / select na hua ho — narm, madad-gaar state. */
export function EmptyBrandState({ title, body, cta }: { title: string; body: string; cta: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="dsh__card"
      style={{ maxWidth: 520, margin: '54px auto 0' }}
    >
      <div className="dsh__empty">
        <span className="dsh__emptymark">
          <svg width="17" height="17" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.6}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
        </span>
        <h3>{title}</h3>
        <p>{body}</p>
        <Link href="/business/scraping" className="dsh__btn dsh__btn--ink" style={{ marginTop: 8 }}>
          {cta} →
        </Link>
      </div>
    </motion.div>
  )
}
