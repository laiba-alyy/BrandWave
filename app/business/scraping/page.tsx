'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { authHeaders } from '@/lib/authHeaders'
import { useActiveBrand } from '@/lib/useActiveBrand'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import Link from 'next/link'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const STAGES = [
  { label: 'Verifying Shopify store...', percent: 10 },
  { label: 'Website Loaded', percent: 25 },
  { label: 'Content Extracted', percent: 50 },
  { label: 'Brand Analysis', percent: 75 },
  { label: 'Profile Ready', percent: 100 },
]

/*
 * Ye wohi chaar cards hain jo pehle emoji + rainbow gradient par the. Content
 * waisa ka waisa hai; sirf emoji ki jagah stroke icons aa gaye hain taake page
 * paper/ink/orange palette se bahar na jaye.
 */
const OPTIONS = [
  {
    title: 'Extract Text',
    desc: 'Extract text content from the page',
    path: 'M5 5.5h14M5 10h14M5 14.5h9M5 19h6',
  },
  {
    title: 'Extract Links',
    desc: 'Extract all links from the page',
    path: 'M13.8 10.2a4 4 0 0 0-5.6 0l-4 4a4 4 0 1 0 5.6 5.66l1.1-1.1m-.75-4.9a4 4 0 0 0 5.65 0l4-4a4 4 0 0 0-5.65-5.66l-1.1 1.1',
  },
  {
    title: 'Extract Images',
    desc: 'Extract all images from the page',
    path: 'M4 5.5h16v13H4zM4 15l4.5-4.5 4 4 3-2.5L20 16M9 9.5h.01',
  },
  {
    title: 'Extract Data',
    desc: 'Extract structured data (tables, etc.)',
    path: 'M4 5.5h16v13H4zM4 10h16M10 10v8.5M4 14.5h16',
  },
]


interface ScrapeSummary {
  id: number
  website_url: string
  business_name: string
  product_count: number
  status: string
}

export default function ScrapingPage() {
  const router = useRouter()
  const { brands, refreshBrands, setActiveBrandId, userId } = useActiveBrand()
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState('')
  const [stages, setStages] = useState(STAGES.map(s => ({ ...s, done: false })))

  /*
   * "Recent scans" table wahi list hai jo brand switcher dikhata hai.
   *
   * Pehle ye page mount par KHUD /api/scraping/my-brands call karta tha —
   * bilkul wahi request jo ActiveBrandProvider pehle hi bhej chuka hota hai.
   * Yani har visit par ek fazool round-trip, aur us se pehle do aur (session +
   * users row). Ab seedha context se aati hai: koi request nahi, table foran.
   *
   * NOTE: `status` column my-brands kabhi return nahi karta tha, is liye wo
   * cell pehle bhi khali tha — kuch khoya nahi.
   */
  const recentScans: ScrapeSummary[] = brands.map(b => ({
    id: b.id,
    website_url: b.website_url,
    business_name: b.business_name ?? '',
    product_count: b.product_count,
    status: 'completed',
  }))
  const hasProfile = brands.length > 0

  /* Reference ke top row jaise teen tiles — sab pehle se maujood recentScans
     se derive hote hain, koi nayi API call nahi. */
  const totals = useMemo(() => {
    const products = recentScans.reduce(
      (sum, scan) => sum + (Number(scan.product_count) || 0),
      0,
    )
    const latest = recentScans[0]
    return {
      stores: recentScans.length,
      products,
      // Teesri tile bhi number honi chahiye (reference me teeno numeric hain);
      // brand ka naam neeche caption me jata hai.
      latestCount: Number(latest?.product_count) || 0,
      latestName: latest?.business_name ?? null,
    }
  }, [recentScans])

  const handleScrape = async () => {
    if (!url.trim()) { setError('Please enter a website URL'); return }
    if (!userId) { setError('User session not found. Please log in again.'); return }

    setError('')
    setLoading(true)
    setProgress(0)
    setCurrentStage('Verifying Shopify store...')
    setStages(STAGES.map(s => ({ ...s, done: false })))

    const stageTimings = [
      { percent: 25, stage: 'Website Loaded', delay: 3000 },
      { percent: 50, stage: 'Content Extracted', delay: 8000 },
      { percent: 75, stage: 'Brand Analysis', delay: 15000 },
    ]

    stageTimings.forEach(({ percent, stage, delay }) => {
      setTimeout(() => {
        setProgress(percent)
        setCurrentStage(stage)
        setStages(prev => prev.map(s => ({ ...s, done: s.percent <= percent })))
      }, delay)
    })

    try {
      // scrape ke baad switcher/table dono refresh hone chahiye
      const res = await fetch(`${API_URL}/api/scraping/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
        body: JSON.stringify({
          website_url: url.trim(),
          user_id: userId,
        }),
      })

      if (!res.ok) {
        const err = await res.json()
        const detail = err.detail
        const msg = Array.isArray(detail)
          ? detail.map((e: { msg: string }) => e.msg).join(', ')
          : typeof detail === 'string' ? detail : 'Scraping failed. Please try again.'
        setError(msg)
        setLoading(false)
        return
      }

      const data = await res.json()
      setProgress(100)
      setCurrentStage('Profile Ready')
      setStages(STAGES.map(s => ({ ...s, done: true })))
      setLoading(false)

      // Naye brand ka id — aage ka sab kuch isi par chalta hai.
      const newBrandId: number | undefined = data.data?.id

      // 1. Switcher ka cached brand list stale hai — wo sirf page load par
      //    fetch hoti hai, is liye abhi scrape kiya hua brand usme hota hi
      //    nahi tha. refreshBrands() usay dobara fetch karata hai.
      // 2. Active brand ko naye brand par set karo, warna profile page
      //    (aur SEO/ads/chatbot) purana selected brand dikhate rehte hain.
      // Ye await redirect se PEHLE hai: agar list refresh hone se pehle
      // navigate kar gaye to profile page purani list ke saath mount hoga.
      if (newBrandId != null) setActiveBrandId(newBrandId)
      // refreshBrands() switcher AUR neeche wali table dono ko bhar deta hai —
      // table ab isi list se derive hoti hai, is liye yahan se my-brands ka
      // doosra fetch hata diya gaya hai (wo bilkul yehi data laa raha tha).
      await refreshBrands()

      setTimeout(() => {
        // brand_profile_id EXPLICITLY bhejna zaroori hai. Pehle sirf ?url=
        // jata tha, aur profile page `urlBrandId ?? activeBrandId` par girta
        // tha — yani bruvi scrape karne ke baad bhi Alkaram dikhta tha.
        router.push(
          newBrandId != null
            ? `/business/scraping/profile?brand_profile_id=${newBrandId}`
            : `/business/scraping/profile?url=${encodeURIComponent(url.trim())}`
        )
      }, 800)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the server.')
      setLoading(false)
    }
  }

  return (
    <main className={`bw-dash ${brandFontVars}`}>

      <div className="dsh">

        {/* Page header - reference jaisa: serif title + gray sub, right par actions. */}
        <div className="dsh__top">
          <div>
            <h1>Data Scraping</h1>
            <p className="dsh__sub">Catalogue, copy and brand signals from any Shopify store</p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            {hasProfile && (
              <Link href="/business/scraping/profile" className="dsh__btn dsh__btn--ink dsh__btn--sm">
                View profile
              </Link>
            )}
          </div>
        </div>

        <div className="dsh__body">

          {/* Stat tiles sirf tab jab kuch scrape ho chuka ho - warna naye user
              ko teen zeros bina wajah khali lagte hain. */}
          {recentScans.length > 0 && (
            <section className="dsh__stats">
              <div className="dsh__stat">
                <span>Stores connected</span>
                <strong>{totals.stores.toLocaleString()}</strong>
              </div>
              <div className="dsh__stat">
                <span>Products scraped</span>
                <strong>{totals.products.toLocaleString()}</strong>
              </div>
              <div className="dsh__stat">
                <span>Most recent</span>
                <strong>{totals.latestCount.toLocaleString()}</strong>
                <small>{totals.latestName ?? 'Last store you connected'}</small>
              </div>
            </section>
          )}

          {/* Start a scan */}
          <section className="dsh__card scr__start">
            <p className="dsh__eyebrow">Step one</p>
            <h2>Point us at a store</h2>
            <p className="scr__lede">
              Paste a Shopify URL. 
            </p>

            <div className="scr__form">
              <div className="scr__field">
                <label htmlFor="scrape-url">Website URL</label>
                <div className="scr__input">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
                    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M13.83 10.17a4 4 0 0 0-5.66 0l-4 4a4 4 0 1 0 5.66 5.66l1.1-1.1m-.76-4.9a4 4 0 0 0 5.66 0l4-4a4 4 0 0 0-5.66-5.66l-1.1 1.1" />
                  </svg>
                  <input
                    id="scrape-url"
                    type="url"
                    value={url}
                    onChange={e => { setUrl(e.target.value); setError('') }}
                    onKeyDown={e => e.key === 'Enter' && !loading && handleScrape()}
                    placeholder="https://www.alkaramstudio.com"
                    disabled={loading}
                  />
                </div>
              </div>
              <button onClick={handleScrape} disabled={loading} className="dsh__btn dsh__btn--amber">
                {loading ? <span className="dsh__spin" /> : null}
                {loading ? 'Scanning...' : 'Start scraping'}
              </button>
            </div>

            {error && (
              <p className="scr__error">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                  strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7.6v5.2M12 16.2h.01" />
                </svg>
                {error}
              </p>
            )}

            <div className="scr__pills">
              {['Shopify Only', 'No Auth Required', 'Full Catalogue', '~1-3 min for large stores'].map((pill, i) => (
                <span key={i} className="scr__pill">{pill}</span>
              ))}
            </div>
          </section>

          {/* Progress */}
          <AnimatePresence>
            {loading && (
              <motion.section
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="dsh__card scr__prog"
              >
                <div className="scr__proghead">
                  <h3>Scanning your store</h3>
                  <span className="scr__pct">{progress}%</span>
                </div>
                <div className="scr__bar">
                  <motion.div
                    className="scr__barfill"
                    initial={{ width: '0%' }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.4, ease: 'easeOut' }}
                  />
                </div>
                <div>
                  {stages.map((stage, i) => {
                    const now = stage.label === currentStage && !stage.done
                    return (
                      <div
                        key={i}
                        className={`scr__stage${stage.done ? ' scr__stage--done' : now ? ' scr__stage--now' : ''}`}
                      >
                        <span className="scr__dot">
                          {stage.done ? (
                            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor"
                              strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M2 6.4 4.6 9 10 3.2" />
                            </svg>
                          ) : now ? (
                            <span className="scr__pulse" />
                          ) : null}
                        </span>
                        {stage.label}
                      </div>
                    )
                  })}
                </div>
              </motion.section>
            )}
          </AnimatePresence>

          {/* What we pull */}
          {!loading && (
            <section className="dsh__card">
              <div className="dsh__cardhead">
                <h3>What we pull</h3>
                <span className="dsh__eyebrow">Every scan</span>
              </div>
              <div className="scr__grid">
                {OPTIONS.map((opt, i) => (
                  <div key={i} className="scr__opt">
                    <span className="scr__optn">{String(i + 1).padStart(2, '0')}</span>
                    <span className="scr__opticon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d={opt.path} />
                      </svg>
                    </span>
                    <h4>{opt.title}</h4>
                    <p>{opt.desc}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Recent scans */}
          <section className="dsh__card">
            <div className="dsh__cardhead">
              <h3>Recent scans</h3>
              {hasProfile && (
                <Link href="/business/scraping/profile" className="dsh__link">
                  View all
                </Link>
              )}
            </div>

            {recentScans.length > 0 ? (
              <div className="scr__tablewrap">
                <table className="scr__table">
                  <thead>
                    <tr>
                      {['Website', 'Products', 'Status', 'Action'].map(h => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {recentScans.map((scan, i) => (
                      <tr key={scan.id ?? i}>
                        <td>
                          <p className="scr__site">{scan.website_url}</p>
                          <p className="scr__brand">{scan.business_name}</p>
                        </td>
                        <td className="scr__count">
                          {(scan.product_count ?? 0).toLocaleString()} products
                        </td>
                        <td>
                          <span className="scr__status">{scan.status}</span>
                        </td>
                        <td>
                          <Link
                            href={`/business/scraping/profile?brand_profile_id=${scan.id}`}
                            onClick={() => setActiveBrandId(scan.id)}
                            className="dsh__link"
                          >
                            View profile
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="scr__empty">
                <div className="scr__emptymark">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <circle cx="11" cy="11" r="7" />
                    <path d="m20 20-3.6-3.6" />
                  </svg>
                </div>
                <h4>No scans yet</h4>
                <p>Enter a Shopify URL above to get started.</p>
              </div>
            )}

            <div className="scr__safety">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 3l7.5 3v5.4c0 4.5-3.1 8.2-7.5 9.6-4.4-1.4-7.5-5.1-7.5-9.6V6L12 3Z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
              <p>
                Your data is safe with us. We use enterprise-grade security to protect your
                data and ensure privacy.
              </p>
              <button className="dsh__link">Learn more</button>
            </div>
          </section>

        </div>
      </div>
    </main>
  )
}
