'use client'

import { useState, useCallback } from 'react'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import { authHeaders } from '@/lib/authHeaders'
import { seoGet, seoPost } from '@/lib/seoApi'
import { useCachedData, cacheInvalidate } from '@/lib/dataCache'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'
import Link from 'next/link'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BlogPost {
  id: number
  title: string
  content: string
  meta_title: string
  meta_description: string
  word_count: number
  keyword_count: number
  keywords_used: string[]
  created_at: string
}

export default function SEOBlogPage() {
  const { activeBrandId, activeBrand, userId } = useActiveBrand()
  const [genError, setGenError] = useState('')
  const [selectedBlog, setSelectedBlog] = useState<BlogPost | null>(null)
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState<number | null>(null)
  const [topic, setTopic] = useState('')
  const [copied, setCopied] = useState(false)
  const [view, setView] = useState<'list' | 'read'>('list')

  /*
   * Cache se (dekho lib/dataCache): dobara is page par aane par blog list
   * FORAN dikhti hai, spinner ke baghair, aur taza list background mein aati.
   */
  const {
    data: blogData, loading, error: loadError, mutate: setBlogs,
  } = useCachedData<BlogPost[]>(
    userId && activeBrandId != null ? `seo:blogs:${activeBrandId}:${userId}` : null,
    useCallback(async () => {
      const data = await seoGet<{ data?: BlogPost[] }>(`/api/seo/blog/history/${userId}`, activeBrandId)
      return data?.data || []
    }, [userId, activeBrandId]),
  )

  const blogs = blogData ?? []

  // Load ki nakami bhi wahi banner dikhata hai jo generate ki nakami dikhata hai.
  const shownError = genError || loadError

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const data = await seoPost<{ data: BlogPost }>(
        '/api/seo/blog/generate', userId, activeBrandId,
        topic.trim() ? { topic: topic.trim() } : {}
      )
      setBlogs([data.data, ...blogs])
      setSelectedBlog(data.data)
      // Dashboard summary blog count dikhata hai.
      cacheInvalidate(`dashboard:summary:${activeBrandId}:`)
      setView('read')
      setTopic('')
      setGenError('')
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Blog generation failed')
    }
    finally { setGenerating(false) }
  }

  const handleDownloadPDF = async (blogId: number) => {
    setDownloading(blogId)
    try {
      const res = await fetch(`${API_URL}/api/seo/blog/${blogId}/export/pdf?user_id=${userId}`, {
        headers: await authHeaders(),
      })
      if (!res.ok) throw new Error('Could not build the PDF for this article.')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `blog_${blogId}.pdf`; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Could not download the PDF')
    }
    finally { setDownloading(null) }
  }

  /* Markdown ka chhota sa subset jo backend waqai bhejta hai (## / ### / -).
     Ab har line par apni Tailwind classes nahi — .dsh__prose typography
     sambhalta hai, is liye yahan sirf structure bacha hai. */
  const renderContent = (content: string) => content.split('\n').map((line, i) => {
    if (line.startsWith('## ')) return <h2 key={i}>{line.replace('## ', '')}</h2>
    if (line.startsWith('### ')) return <h3 key={i}>{line.replace('### ', '')}</h3>
    if (line.startsWith('- ') || line.startsWith('* ')) return <li key={i}>{line.slice(2)}</li>
    if (line.trim() === '') return null
    return <p key={i}>{line}</p>
  })

  const totalWords = blogs.reduce((a, b) => a + (b.word_count || 0), 0)

  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">

        <div className="dsh__top">
          <div style={{ minWidth: 0 }}>
            {view === 'read' && selectedBlog ? (
              <button onClick={() => setView('list')} className="dsh__link">← All articles</button>
            ) : (
              <Link href="/business/seo" className="dsh__link">← SEO</Link>
            )}
            <h1 style={{ marginTop: 6 }}>
              {view === 'read' && selectedBlog
                ? 'Article'
                : `Blog Generator${activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}`}
            </h1>
            <p className="dsh__sub">
              {view === 'read' && selectedBlog
                ? selectedBlog.title
                : 'SEO-optimized articles built around your target keywords'}
            </p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            {view === 'read' && selectedBlog && (
              <button
                onClick={() => handleDownloadPDF(selectedBlog.id)}
                disabled={downloading === selectedBlog.id}
                className="dsh__btn dsh__btn--ghost dsh__btn--sm"
              >
                {downloading === selectedBlog.id
                  ? <><span className="dsh__spin" />Building</> : 'Export PDF'}
              </button>
            )}
          </div>
        </div>

        <div className="dsh__body">

          {shownError && (
            <div className="dsh__note dsh__note--bad"><span>{shownError}</span></div>
          )}

          {view === 'list' ? (
            <>
              {/* ── Compose ─────────────────────────────────────────── */}
              <section className="dsh__card">
                <div style={{ padding: 'clamp(20px, 2.6vw, 28px)' }}>
                  <p className="dsh__eyebrow">New article</p>
                  <h2 style={{ margin: '8px 0 6px', fontSize: 20 }}>Write a post for this brand</h2>
                  <p style={{ fontSize: 13.5, color: 'var(--text-dim)', maxWidth: '58ch', lineHeight: 1.6 }}>
                    Give it a topic, or leave it blank and the model will pick one from
                    your target keywords and product catalogue.
                  </p>

                  <div style={{ display: 'flex', gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
                    <input
                      value={topic}
                      onChange={e => setTopic(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && !generating && handleGenerate()}
                      placeholder="e.g. How to choose the right unstitched fabric"
                      className="scr__input"
                      style={{ flex: '1 1 320px' }}
                    />
                    <button
                      onClick={handleGenerate}
                      disabled={generating}
                      className="dsh__btn dsh__btn--amber"
                    >
                      {generating
                        ? <><span className="dsh__spin" />Writing article</>
                        : 'Generate article'}
                    </button>
                  </div>
                </div>
              </section>

              {blogs.length > 0 && (
                <section className="dsh__stats">
                  <div className="dsh__stat">
                    <span>Articles</span>
                    <strong>{blogs.length}</strong>
                    <small>published for this brand</small>
                  </div>
                  <div className="dsh__stat">
                    <span>Total words</span>
                    <strong>{totalWords.toLocaleString()}</strong>
                    <small>across every article</small>
                  </div>
                  <div className="dsh__stat">
                    <span>Latest</span>
                    <strong>{blogs[0].word_count.toLocaleString()}</strong>
                    <small>words in the newest post</small>
                  </div>
                </section>
              )}

              {/* ── Library ─────────────────────────────────────────── */}
              {loading ? (
                <section className="dsh__card">
                  <div style={{ padding: 20, display: 'grid', gap: 10 }}>
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="dsh__skel" style={{ height: 42 }} />
                    ))}
                  </div>
                </section>
              ) : blogs.length === 0 ? (
                <section className="dsh__card">
                  <div className="dsh__empty">
                    <span className="dsh__emptymark">
                      <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                        <path d="M5 4h11l3 3v13H5z" /><path d="M8 10h8M8 14h8M8 18h5" />
                      </svg>
                    </span>
                    <h3>No articles yet</h3>
                    <p>Your generated articles will collect here, each with its own meta title and description.</p>
                  </div>
                </section>
              ) : (
                <>
                  <div className="dsh__section">
                    <div>
                      <p className="dsh__eyebrow">Library</p>
                      <h2>Your articles</h2>
                    </div>
                  </div>

                  <section className="dsh__card">
                    {blogs.map(blog => (
                      <div className="dsh__row" key={blog.id}>
                        <div className="dsh__rowmain">
                          <b>{blog.title}</b>
                          <span>
                            {blog.word_count.toLocaleString()} words ·{' '}
                            {blog.keyword_count} keywords ·{' '}
                            {new Date(blog.created_at).toLocaleDateString(undefined, {
                              day: 'numeric', month: 'short', year: 'numeric',
                            })}
                          </span>
                        </div>
                        <div className="dsh__rowactions">
                          <button
                            onClick={() => handleDownloadPDF(blog.id)}
                            disabled={downloading === blog.id}
                            className="dsh__btn dsh__btn--ghost dsh__btn--sm"
                          >
                            {downloading === blog.id ? <span className="dsh__spin" /> : 'PDF'}
                          </button>
                          <button
                            onClick={() => { setSelectedBlog(blog); setView('read') }}
                            className="dsh__btn dsh__btn--ink dsh__btn--sm"
                          >
                            Read
                          </button>
                        </div>
                      </div>
                    ))}
                  </section>
                </>
              )}
            </>
          ) : selectedBlog && (
            <>
              {/* ── Reader ──────────────────────────────────────────── */}
              <section className="dsh__hero" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
                <div>
                  <p className="dsh__eyebrow" style={{ color: '#8d8a80' }}>
                    {new Date(selectedBlog.created_at).toLocaleDateString(undefined, {
                      day: 'numeric', month: 'long', year: 'numeric',
                    })}
                  </p>
                  <h2 style={{ marginTop: 10 }}>{selectedBlog.title}</h2>

                  <div className="dsh__herofoot">
                    <div className="dsh__herostat">
                      <span>Words</span>
                      <strong>{selectedBlog.word_count.toLocaleString()}</strong>
                    </div>
                    <div className="dsh__herostat">
                      <span>Keywords used</span>
                      <strong>{selectedBlog.keyword_count}</strong>
                    </div>
                  </div>

                  {selectedBlog.keywords_used?.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 18 }}>
                      {selectedBlog.keywords_used.map((kw, i) => (
                        <span key={i} style={{
                          padding: '4px 10px', borderRadius: 999, fontSize: 11,
                          background: 'rgba(255,255,255,0.09)', color: '#cfcbc1',
                        }}>
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <section className="dsh__card">
                <div className="dsh__cardhead">
                  <h3>Meta tags</h3>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(selectedBlog.content)
                      setCopied(true); setTimeout(() => setCopied(false), 2000)
                    }}
                    className="dsh__btn dsh__btn--ghost dsh__btn--sm"
                  >
                    {copied ? 'Copied' : 'Copy article'}
                  </button>
                </div>
                <div style={{ padding: '6px 20px 16px' }}>
                  <div className="dsh__kv">
                    <dt>Meta title</dt>
                    <dd style={{ fontFamily: 'var(--f-body)', fontSize: 13, textAlign: 'right', maxWidth: '58ch' }}>
                      {selectedBlog.meta_title}
                    </dd>
                  </div>
                  <div className="dsh__kv">
                    <dt>Meta description</dt>
                    <dd style={{ fontFamily: 'var(--f-body)', fontSize: 13, textAlign: 'right', maxWidth: '58ch' }}>
                      {selectedBlog.meta_description}
                    </dd>
                  </div>
                </div>
              </section>

              <section className="dsh__card">
                <div style={{ padding: 'clamp(22px, 3vw, 34px)' }}>
                  <div className="dsh__prose">{renderContent(selectedBlog.content)}</div>
                </div>
              </section>
            </>
          )}

        </div>
      </div>
    </main>
  )
}
