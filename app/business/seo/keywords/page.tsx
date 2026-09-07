// SEOKeywordsPage.tsx
'use client'

import { useState, useCallback } from 'react'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import { seoGet, seoPost } from '@/lib/seoApi'
import { useCachedData, cacheInvalidate } from '@/lib/dataCache'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { IconCheck, IconCopy } from '@/components/chatbot/shared'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import Link from 'next/link'

interface Keyword {
  keyword: string; search_volume?: number | null; competition?: number | null
  competition_index?: number | null; cpc?: number | null
  intent?: string; opportunity_score?: number; market?: string; source?: string
  // Naye fields — DataForSEO validation ke baad
  difficulty?: number | null
  search_intent?: string; validated?: boolean
}

const formatVolume = (v?: number | null) =>
  v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : String(v)

/* 0-100 difficulty — kam behtar hai (rank karna aasan). Teen alag text
   colours ki jagah ab wohi badge tones jo poore dashboard mein hain. */
const difficultyTone = (d: number) =>
  d <= 30 ? 'dsh__badge--good' : d <= 60 ? 'dsh__badge--warn' : 'dsh__badge--bad'

export default function SEOKeywordsPage() {
  const { activeBrandId, activeBrand, userId } = useActiveBrand()
  const [genError, setGenError] = useState('')
  const [generating, setGenerating] = useState(false)
  const [copiedKeyword, setCopiedKeyword] = useState<number | null>(null)

  /*
   * Cache se (dekho lib/dataCache): dobara is page par aane par data FORAN
   * dikhta hai, spinner ke baghair, aur taza value background mein aati hai.
   */
  const {
    data: keywordData, loading, error: loadError, mutate: setKeywords,
  } = useCachedData<Keyword[]>(
    userId && activeBrandId != null ? `seo:keywords:${activeBrandId}:${userId}` : null,
    useCallback(async () => {
      // 404 = abhi koi keywords generate nahi hue (empty state).
      const data = await seoGet<{ data?: { keywords?: Keyword[] } }>(
        `/api/seo/keywords/${userId}`, activeBrandId
      )
      return data?.data?.keywords || []
    }, [userId, activeBrandId]),
  )

  // Hook cold load par null deta hai; render sites ko hamesha ek array chahiye.
  const keywords = keywordData ?? []

  // Load ki nakami bhi wahi banner dikhata hai jo generate ki nakami dikhata
  // hai. Warna cache hook ki error chup-chaap gum ho jati.
  const shownError = genError || loadError

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const data = await seoPost<{ data?: { keywords?: Keyword[] } }>(
        '/api/seo/keywords/generate', userId, activeBrandId
      )
      setKeywords(data.data?.keywords || [])
      // Dashboard summary keyword count dikhata hai.
      cacheInvalidate(`dashboard:summary:${activeBrandId}:`)
      setGenError('')
    } catch (e) {
      // 400/500 pehle chup-chaap nigal jate the — ab backend ka message dikhta hai
      setGenError(e instanceof Error ? e.message : 'Keyword generation failed')
    }
    finally { setGenerating(false) }
  }

  const handleCopy = async (keyword: string, index: number) => {
    try {
      await navigator.clipboard.writeText(keyword)
      setCopiedKeyword(index)
      setTimeout(() => setCopiedKeyword(null), 1600)
    } catch {
      // clipboard blocked — chup rehna theek hai, button waisa ka waisa
    }
  }

  const validated = keywords.filter(k => k.search_volume != null).length
  const googleChecked = keywords.filter(k => k.source === 'Google Validated').length
  const avgScore = keywords.length
    ? Math.round(keywords.reduce((a, k) => a + (k.opportunity_score || 0), 0) / keywords.length)
    : 0

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">

        <div className="dsh__top">
          <div>
            <Link href="/business/seo" className="dsh__link">← SEO</Link>
            <h1 style={{ marginTop: 6 }}>
              Keyword Suggestions{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}
            </h1>
            <p className="dsh__sub">Google-validated keywords with real search demand</p>
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
                : keywords.length ? 'Regenerate' : 'Generate keywords'}
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
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="dsh__skel" style={{ height: 34 }} />
                ))}
              </div>
            </section>
          ) : keywords.length === 0 ? (
            <section className="dsh__card">
              <div className="dsh__empty">
                <span className="dsh__emptymark">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                    <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
                  </svg>
                </span>
                <h3>No keywords yet</h3>
                <p>
                  Generate thirty target keywords from your catalogue, each checked
                  against real Google Autocomplete demand.
                </p>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="dsh__btn dsh__btn--amber"
                  style={{ marginTop: 8 }}
                >
                  {generating ? <><span className="dsh__spin" />Generating</> : 'Generate keywords'}
                </button>
              </div>
            </section>
          ) : (
            <>
              <section className="dsh__stats">
                <div className="dsh__stat">
                  <span>Keywords</span>
                  <strong>{keywords.length}</strong>
                  <small>ranked by opportunity</small>
                </div>
                <div className="dsh__stat">
                  <span>Google validated</span>
                  <strong>{googleChecked}</strong>
                  <small>confirmed by Autocomplete</small>
                </div>
                <div className="dsh__stat">
                  <span>Avg opportunity</span>
                  <strong>{avgScore}</strong>
                  <small>higher is better</small>
                </div>
              </section>

              {validated === 0 && (
                <div className="dsh__note">
                  <span>
                    Search volume and difficulty need DataForSEO credits. The keywords
                    below are still Google-validated and ranked — only the volume
                    columns are unavailable.
                  </span>
                </div>
              )}

              <section className="dsh__card">
                <div className="dsh__cardhead">
                  <h3>Target keywords</h3>
                  <span className="dsh__badge">{keywords.length} total</span>
                </div>
                <div className="dsh__tablewrap">
                  <table className="dsh__table">
                    <thead>
                      <tr>
                        <th style={{ width: '40%' }}>Keyword</th>
                        <th>Intent</th>
                        <th>Source</th>
                        <th className="dsh__num">Volume</th>
                        <th className="dsh__num">Difficulty</th>
                        <th className="dsh__num">Score</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {keywords.map((kw, i) => (
                        <tr key={i}>
                          <td><b>{kw.keyword}</b></td>
                          <td style={{ textTransform: 'capitalize' }}>
                            {kw.search_intent || kw.intent || 'commercial'}
                          </td>
                          <td>
                            <span className={`dsh__badge${kw.source === 'Google Validated' ? ' dsh__badge--good' : ''}`}>
                              {kw.source === 'Google Validated' ? 'Google' : 'AI'}
                            </span>
                          </td>
                          <td className="dsh__num">{formatVolume(kw.search_volume)}</td>
                          <td className="dsh__num">
                            {kw.difficulty == null ? '—' : (
                              <span className={`dsh__badge ${difficultyTone(kw.difficulty)}`}>
                                {Math.round(kw.difficulty)}
                              </span>
                            )}
                          </td>
                          <td className="dsh__num">{kw.opportunity_score ?? '—'}</td>
                          <td className="dsh__num">
                            <button
                              type="button"
                              onClick={() => handleCopy(kw.keyword, i)}
                              aria-label={`Copy keyword ${kw.keyword}`}
                              title="Copy keyword"
                              className="dsh__link"
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
                            >
                              {copiedKeyword === i
                                ? <><IconCheck className="h-3 w-3" />Copied</>
                                : <><IconCopy className="h-3 w-3" />Copy</>}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <p className="dsh__sectionnote" style={{ margin: '0 2px' }}>
                Opportunity score combines Google validation, how closely the phrase
                matches your products, brand fit, length and buying intent.
              </p>
            </>
          )}

        </div>
      </div>
    </main>
  )
}
