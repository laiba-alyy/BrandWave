'use client'

/**
 * BrandWave Dashboard — login ke baad ka pehla safha.
 *
 * ── Dhancha ────────────────────────────────────────────────────────────────
 * Safha lamba hai aur hisson mein banta hai, taake 12 panels ek doosre mein
 * ghul na jayen:
 *
 *   1. Hero band        — brand kaun hai + chaar sab se ahem numbers
 *   2. Stat tiles       — har module ka ek headline number
 *   3. Search visibility— SEO gauge, factor radar, audit health, keywords
 *   4. Customer voice   — sentiment donut, emotions, sources, themes
 *   5. Catalogue        — category breakdown + store locale
 *   6. Content & automation — content mix, chatbot, insights readiness
 *   7. Module cards     — har module ka darwaza
 *
 * ── Sirf ASLI data ─────────────────────────────────────────────────────────
 * Har chart wo dikhata hai jo DB mein pehle se mehfooz hai. Koi trend line
 * nahi hai kyunke history rakhi hi nahi jati (SEO audit har brand ki EK row
 * update karta hai; sentiment ki har row aakhri run ka snapshot hai). Jahan
 * data na ho wahan chart ki jagah dostana dawat aati hai — khali chart ya
 * farzi number nahi.
 *
 * ── Ek request ─────────────────────────────────────────────────────────────
 * Saara data /api/dashboard/summary se aata hai. Har panel apna module call
 * karta to landing par ek darjan requests jatin, har ek ka apna Supabase
 * token round-trip.
 *
 * ── recharts dynamic hai ───────────────────────────────────────────────────
 * Chart library ka bundle chhota nahi aur ye safha sab se ziyada khulta hai.
 * `next/dynamic` (ssr: false) se safhe ka dhancha aur numbers foran render
 * hote hain; charts uske baad aate hain.
 */

import { useCallback, useMemo } from 'react'
import { useCachedData } from '@/lib/dataCache'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { authHeaders } from '@/lib/authHeaders'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import {
  buildCards, CardSkeleton, EmptyBrandState, ModuleCard, type Summary,
} from '@/components/dashboard/ModuleCards'
import {
  DashboardHero, HeroSkeleton, PanelSkeleton, SectionHeading, StatTiles,
  type StatTile,
} from '@/components/dashboard/DashboardHero'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Charts — client par, page shell ke baad ────────────────────────────────
const loader = () => <PanelSkeleton height={200} />
const C = {
  Panel: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.ChartPanel), { ssr: false, loading: loader }),
  Empty: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.ChartEmpty), { ssr: false }),
  SeoGauge: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.SeoGauge), { ssr: false, loading: loader }),
  SeoRadar: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.SeoFactorRadar), { ssr: false, loading: loader }),
  Health: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.AuditHealthBar), { ssr: false, loading: loader }),
  Keywords: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.KeywordOpportunity), { ssr: false, loading: loader }),
  Donut: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.SentimentDonutChart), { ssr: false, loading: loader }),
  Emotions: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.EmotionsChart), { ssr: false, loading: loader }),
  Sources: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.ReviewSources), { ssr: false, loading: loader }),
  ReviewKeywords: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.ReviewKeywords), { ssr: false, loading: loader }),
  Themes: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.ThemeList), { ssr: false }),
  Categories: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.CategoryDonut), { ssr: false, loading: loader }),
  ContentMix: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.ContentMixChart), { ssr: false, loading: loader }),
  Insights: dynamic(() => import('@/components/dashboard/DashboardCharts').then(m => m.InsightsReadiness), { ssr: false, loading: loader }),
}

const num = (n: number) => n.toLocaleString()

/** Chhota "View →" link jo har panel ke sar par baithta hai. */
function PanelLink({ href, label = 'View' }: { href: string; label?: string }) {
  return (
    <Link
      href={href}
      className="dsh__link"
    >
      {label} →
    </Link>
  )
}

const tileIcon = (d: string) => (
  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.9">
    <path d={d} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export default function DashboardPage() {
  const { brands, activeBrand, activeBrandId, loading: brandsLoading } = useActiveBrand()

  // NOTE: session check aur `users` row yahan se nikal chuke hain — dono ab
  // ActiveBrandProvider (ek dafa) aur DashboardShell (auth guard) ke zimme hain.

  /*
   * Summary ab CACHE se aati hai (dekho lib/dataCache).
   *
   * Pehle har dafa dashboard kholne par `loading = true` se shuru hone wali ek
   * fetch chalti thi, aur graphs 2-3 second khaali rehte the — chahe user abhi
   * abhi kisi doosre page par gaya aur foran wapas aaya ho. Ab pehli dafa hi
   * network par jata hai; uske baad dashboard FORAN render hota hai aur taza
   * numbers background mein aa kar update ho jate hain.
   */
  const summaryKey = activeBrandId != null
    ? `dashboard:summary:${activeBrandId}:`
    : null

  const {
    data: summary, loading, error, refresh: reloadSummary,
  } = useCachedData<Summary | null>(
    summaryKey,
    useCallback(async () => {
      const res = await fetch(`${API_URL}/api/dashboard/summary?brand_profile_id=${activeBrandId}`, {
        headers: await authHeaders(),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(
          typeof body?.detail === 'string' ? body.detail
            : `Could not load your dashboard (${res.status})`
        )
      }
      return (await res.json()) as Summary
    }, [activeBrandId]),
  )

  const brandName = brandLabel(activeBrand) || summary?.brand?.business_name || 'Your brand'
  const cards = useMemo(() => buildCards(summary, brandName), [summary, brandName])

  const m = summary?.modules
  const seo = m?.seo
  const sentiment = m?.sentiment
  const products = m?.products
  const chatbot = m?.chatbot

  // ── Hero ke chips + numbers ──────────────────────────────────────────────
  const chips = useMemo(() => {
    const out: string[] = []
    if (summary?.brand?.platform) out.push(titleCase(summary.brand.platform))
    if (products?.store_country) out.push(products.store_country)
    if (products?.store_currency) out.push(products.store_currency)
    if (products?.price_range) out.push(titleCase(String(products.price_range).replace(/[-_]/g, ' ')))
    return out
  }, [summary, products])

  const heroStats = useMemo(() => [
    {
      label: 'Products',
      value: products?.count ? num(products.count) : '—',
      hint: products?.categories?.length
        ? `${products.categories.length} categories`
        : 'Import your store to fill this',
    },
    {
      label: 'SEO score',
      value: seo?.score != null ? String(seo.score) : '—',
      hint: seo?.score != null ? 'out of 100' : 'Run your first audit',
    },
    {
      label: 'Positive reviews',
      value: sentiment?.positive_percent != null ? `${sentiment.positive_percent}%` : '—',
      hint: sentiment?.review_count ? `${num(sentiment.review_count)} reviews analysed` : 'No analysis yet',
    },
    {
      label: 'Conversations',
      value: chatbot?.conversation_count != null ? num(chatbot.conversation_count) : '—',
      hint: chatbot?.active_count ? `${chatbot.active_count} bot${chatbot.active_count === 1 ? '' : 's'} live` : 'No chatbot yet',
    },
  ], [products, seo, sentiment, chatbot])

  // ── Stat tiles ───────────────────────────────────────────────────────────
  const tiles: StatTile[] = useMemo(() => {
    const contentTotal = (summary?.content_mix ?? []).reduce((s, c) => s + c.count, 0)
    return [
      {
        key: 'keywords',
        label: 'Target keywords',
        value: seo?.keyword_count ? num(seo.keyword_count) : '—',
        hint: seo?.keyword_count ? 'Google-validated set' : 'Generate your keyword set',
        accent: '#0EA5E9',
        icon: tileIcon('M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z'),
      },
      {
        key: 'content',
        label: 'Content created',
        value: contentTotal ? num(contentTotal) : '—',
        hint: contentTotal ? 'blogs, keywords and ads' : 'Nothing generated yet',
        accent: '#A855F7',
        icon: tileIcon('M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'),
      },
      {
        key: 'reviews',
        label: 'Reviews analysed',
        value: sentiment?.review_count ? num(sentiment.review_count) : '—',
        hint: sentiment?.dominant_emotion
          ? `Mostly ${sentiment.dominant_emotion}`
          : 'Run sentiment analysis',
        accent: '#10B981',
        icon: tileIcon('M7 8h10M7 12h4m1 8a9 9 0 100-18 9 9 0 000 18z'),
      },
      {
        key: 'health',
        label: 'Products needing work',
        value: seo?.health ? num(seo.health.needs_work) : '—',
        hint: seo?.health ? `of ${num(seo.health.good + seo.health.warning + seo.health.needs_work)} checked` : 'Run your first audit',
        accent: '#F43F5E',
        icon: tileIcon('M12 9v2m0 4h.01M5 19h14a2 2 0 001.84-2.75L13.74 4a2 2 0 00-3.5 0l-7.1 12.25A2 2 0 004.99 19z'),
      },
    ]
  }, [summary, seo, sentiment])

  const busy = loading || brandsLoading

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">

        <div className="dsh__top">
          <div>
            <h1>Dashboard</h1>
            <p className="dsh__sub">Every module for this brand, in one view</p>
          </div>
          <div className="dsh__topactions">
            {/*
              Brand Profile ka shortcut. Pehle profile tak pohanchne ke liye
              user ko Data Scraping page se guzarna parta tha — jab ke profile
              sab se ziyada dekhi jane wali cheez hai. Link tabhi dikhta hai jab
              koi brand select ho, warna profile page brand ke baghair khulta
              aur seedha /business/scraping par bounce kar deta.
            */}
            {activeBrandId != null && (
              <Link
                href={`/business/scraping/profile?brand_profile_id=${activeBrandId}`}
                prefetch
                className="dsh__btn dsh__btn--ghost dsh__btn--sm"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 5.5h16v13H4zM4 10h16M9 14h6" />
                </svg>
                Brand Profile
              </Link>
            )}
            <BrandSwitcher />
          </div>
        </div>

        <div className="dsh__body" style={{ maxWidth: 1400 }}>
          {brandsLoading ? (
            <>
              <HeroSkeleton />
              <div className="dsh__grid dsh__grid--4">
                {Array.from({ length: 4 }).map((_, i) => <PanelSkeleton key={i} height={116} />)}
              </div>
            </>
          ) : brands.length === 0 ? (
            <EmptyBrandState
              title="Let's set up your first brand"
              body="Import your store and BrandWave will fill this dashboard with your products, SEO, sentiment and ads."
              cta="Add your brand"
            />
          ) : activeBrandId == null ? (
            <EmptyBrandState
              title="Select a brand to see your dashboard"
              body="Pick a brand from the switcher above and its summary will appear here."
              cta="Go to brands"
            />
          ) : (
            <>

              {error && (
                <div className="dsh__note" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{error}</span>
                  <button
                    onClick={() => { void reloadSummary() }}
                    className="dsh__btn dsh__btn--ink dsh__btn--sm"
                  >
                    Retry
                  </button>
                </div>
              )}

              {/* ── 1. Hero ─────────────────────────────────────────────── */}
              {busy ? <HeroSkeleton /> : (
                <DashboardHero
                  brandName={brandName}
                  websiteUrl={summary?.brand?.website_url}
                  chips={chips}
                  stats={heroStats}
                />
              )}

              {/* ── 2. Stat tiles ───────────────────────────────────────── */}
              {busy ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {Array.from({ length: 4 }).map((_, i) => <PanelSkeleton key={i} height={116} />)}
                </div>
              ) : <StatTiles tiles={tiles} />}

              {/* ── 3. Search visibility ────────────────────────────────── */}
              <section>
                <SectionHeading
                  title="Search visibility"
                  subtitle="How your product pages look to Google"
                  action={<PanelLink href="/business/seo" label="Open SEO" />}
                />
                {busy ? (
                  <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-4">
                    {Array.from({ length: 4 }).map((_, i) => <PanelSkeleton key={i} />)}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-4">
                    <C.Panel title="Overall score" subtitle="Weighted across every factor" accent="#F0A63C">
                      {seo?.available && seo.score != null
                        ? <C.SeoGauge score={seo.score} lastAudit={seo.last_audit} />
                        : <C.Empty message="Run your first SEO audit to score your titles, descriptions, keywords and tags." />}
                    </C.Panel>

                    <C.Panel title="Factor breakdown" subtitle="Where you're strong, where you're not" accent="#6366F1">
                      {seo?.factors?.length
                        ? <C.SeoRadar factors={seo.factors} />
                        : <C.Empty message="Factor scores appear once an audit has run." />}
                    </C.Panel>

                    <C.Panel title="Product health" subtitle="Every product the audit checked" accent="#10B981">
                      {seo?.health
                        ? <C.Health health={seo.health} coverage={seo.coverage} />
                        : <C.Empty message="Run an audit to see how many products pass, warn or need work." />}
                    </C.Panel>

                    <C.Panel title="Top keyword opportunities" subtitle="Ranked by opportunity score" accent="#0EA5E9"
                      action={<PanelLink href="/business/seo/keywords" />}>
                      {seo?.top_keywords?.length
                        ? <C.Keywords keywords={seo.top_keywords} />
                        : <C.Empty message="Generate keywords and your best opportunities will be ranked here." />}
                    </C.Panel>
                  </div>
                )}
              </section>

              {/* ── 4. Customer voice ───────────────────────────────────── */}
              <section>
                <SectionHeading
                  title="Customer voice"
                  subtitle="What people say about you, from real reviews"
                  action={<PanelLink href="/business/sentiment" label="Open sentiment" />}
                />
                {busy ? (
                  <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-4">
                    {Array.from({ length: 4 }).map((_, i) => <PanelSkeleton key={i} />)}
                  </div>
                ) : !sentiment?.available ? (
                  <C.Panel title="Sentiment" subtitle="Not analysed yet" accent="#10B981">
                    <C.Empty message="Run a sentiment analysis and we'll break your reviews into positive, negative and neutral, with the emotions and themes behind them." />
                  </C.Panel>
                ) : (
                  <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-4">
                    <C.Panel title="Sentiment split" subtitle={`${num(sentiment.review_count ?? 0)} reviews analysed`} accent="#10B981">
                      {sentiment.breakdown
                        ? <C.Donut breakdown={sentiment.breakdown} />
                        : <C.Empty message="This analysis predates the detailed breakdown. Re-run it to see the split." />}
                    </C.Panel>

                    <C.Panel title="Emotions" subtitle="Detected across every review" accent="#A855F7">
                      {sentiment.emotions?.length
                        ? <C.Emotions emotions={sentiment.emotions} />
                        : <C.Empty message="Your latest analysis didn't return emotion counts. Re-run it to pick them up." />}
                    </C.Panel>

                    <C.Panel title="Most mentioned" subtitle="Words that come up again and again" accent="#F0A63C">
                      {sentiment.keywords?.length
                        ? <C.ReviewKeywords keywords={sentiment.keywords} />
                        : <C.Empty message="Keyword frequencies appear after your next analysis." />}
                    </C.Panel>

                    <C.Panel title="Where reviews came from" subtitle="Sources searched in the last run" accent="#0EA5E9">
                      {sentiment.sources?.length
                        ? <C.Sources sources={sentiment.sources} />
                        : <C.Empty message="Source breakdown appears after your next analysis." />}
                    </C.Panel>
                  </div>
                )}

                {/* Themes — sirf tab jab dono mein se kuch ho */}
                {!busy && sentiment?.available &&
                  ((sentiment.loved?.length ?? 0) > 0 || (sentiment.pain_points?.length ?? 0) > 0) && (
                  <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
                    {(sentiment.loved?.length ?? 0) > 0 && (
                      <C.Panel title="What customers love" subtitle="Themes pulled from positive reviews" accent="#10B981">
                        <C.Themes items={sentiment.loved!} tone="loved" />
                      </C.Panel>
                    )}
                    {(sentiment.pain_points?.length ?? 0) > 0 && (
                      <C.Panel title="What frustrates them" subtitle="Themes pulled from negative reviews" accent="#F43F5E">
                        <C.Themes items={sentiment.pain_points!} tone="pain" />
                      </C.Panel>
                    )}
                  </div>
                )}
              </section>

              {/* ── 5. Catalogue ────────────────────────────────────────── */}
              <section>
                <SectionHeading
                  title="Catalogue"
                  subtitle="What you sell, by category"
                  action={<PanelLink href="/business/scraping/profile" label="Open catalogue" />}
                />
                {busy ? <PanelSkeleton height={240} /> : (
                  <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                    <C.Panel className="xl:col-span-2" title="Product mix" subtitle="Every product, grouped by detected category" accent="#F0A63C">
                      {products?.categories?.length
                        ? <C.Categories categories={products.categories} />
                        : <C.Empty message="Import your store and your catalogue breakdown will appear here." />}
                    </C.Panel>

                    <C.Panel title="Store profile" subtitle="Detected during import" accent="#6366F1">
                      <dl className="space-y-3.5">
                        {[
                          ['Platform', summary?.brand?.platform ? titleCase(summary.brand.platform) : null],
                          ['Market', products?.store_country],
                          ['Currency', products?.store_currency],
                          ['Price range', products?.price_range ? titleCase(String(products.price_range).replace(/[-_]/g, ' ')) : null],
                          ['Categories', products?.categories?.length ? String(products.categories.length) : null],
                        ].map(([label, value]) => (
                          <div key={label as string} className="flex items-baseline justify-between gap-4 border-b border-[#fbfaf7] pb-3 last:border-0 last:pb-0">
                            <dt className="text-[12px] text-[#8b877d]">{label}</dt>
                            <dd className="text-[13px] font-semibold text-[#14140f]">{value || '—'}</dd>
                          </div>
                        ))}
                      </dl>
                    </C.Panel>
                  </div>
                )}
              </section>

              {/* ── 6. Content & automation ─────────────────────────────── */}
              <section>
                <SectionHeading
                  title="Content &amp; automation"
                  subtitle="What BrandWave has produced for this brand"
                />
                {busy ? (
                  <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                    {Array.from({ length: 3 }).map((_, i) => <PanelSkeleton key={i} />)}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                    <C.Panel title="Content mix" subtitle="Everything generated so far" accent="#A855F7">
                      <C.ContentMix items={summary?.content_mix ?? []} />
                    </C.Panel>

                    <C.Panel title="Support automation" subtitle="Your customer-facing chatbot" accent="#14B8A6"
                      action={<PanelLink href="/business/chatbot" />}>
                      {chatbot?.available ? (
                        <dl className="grid grid-cols-3 gap-3 pt-2">
                          {[
                            ['Bots', chatbot.bot_count ?? 0],
                            ['Live', chatbot.active_count ?? 0],
                            ['Chats', chatbot.conversation_count ?? 0],
                          ].map(([label, value]) => (
                            <div key={label as string}>
                              <dt className="text-[11px] font-medium uppercase tracking-[0.1em] text-[#8b877d]">{label}</dt>
                              <dd className="mt-1.5 text-[24px] font-bold leading-none tracking-tight text-[#14140f] tabular-nums">
                                {num(Number(value))}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <C.Empty message="Create a chatbot, upload your policies, and it will answer customer questions on your store." />
                      )}
                    </C.Panel>

                    <C.Panel title="Insights readiness" subtitle="Data available for AI recommendations" accent="#F0A63C"
                      action={<PanelLink href="/business/improvement" />}>
                      {m?.insights?.sources?.length
                        ? <C.Insights sources={m.insights.sources} />
                        : <C.Empty message="Import your store to start building the data insights run on." />}
                    </C.Panel>
                  </div>
                )}
              </section>

              {/* ── 7. Module cards ─────────────────────────────────────── */}
              <section className="pb-4">
                <SectionHeading title="All modules" subtitle="Jump into any part of BrandWave" />
                {busy ? (
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {Array.from({ length: 7 }).map((_, i) => <CardSkeleton key={i} />)}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {cards.map((card, i) => <ModuleCard key={card.key} card={card} index={i} />)}
                  </div>
                )}
              </section>

            </>
          )}
        </div>
      </div>
    </main>
  )
}

function titleCase(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
