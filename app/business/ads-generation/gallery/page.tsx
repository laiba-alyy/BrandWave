'use client'

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { adsApi, toImageUrl, downloadFile, type GalleryItem, type GalleryDetail } from '@/lib/adsApi'

const CARD_GRADIENTS = [
  'from-[#8b877d] to-[#56544d]',
  'from-[#8b877d] to-[#8b877d]',
  'from-[#96203f] to-[#96203f]',
  'from-[#d08a12] to-[#a8620d]',
  'from-[#12876b] to-[#12876b]',
]

export default function AdsGalleryPage() {
  const supabase = useMemo(() => createClient(), [])
  const auth = supabase.auth
  const [items, setItems] = useState<GalleryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<GalleryDetail | null>(null)

  useEffect(() => {
    auth.getUser().then(({ data }) => {
      const uid = data.user?.id
      if (uid) {
        adsApi.getGallery(uid).then((res) => {
          setItems(res)
          setLoading(false)
        })
      } else {
        setLoading(false)
      }
    })
  }, [auth])

  const openDetail = async (adId: number) => {
    const d = await adsApi.getGalleryDetail(adId)
    setDetail(d)
  }

  return (
    <div className="min-h-full px-6 lg:px-8 py-6">
      <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-[#8b877d]">Asset Library</p>
            <h1 className="mt-2 text-3xl font-black text-[#14140f]">Generated Ads Gallery</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#56544d]">
              Browse every generated image and video ad in one place, with a cleaner preview flow for quick review and downloads.
            </p>
          </div>
          <Link
            href="/business/ads-generation"
            className="inline-flex items-center justify-center rounded-full bg-[#0a0a0a] px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-[#0a0a0a]/15 transition hover:bg-[#16160f]"
          >
            + New Ad
          </Link>
        </div>

        <div className="mt-6 rounded-xl border border-[#d5d1c6] bg-[#fbfaf7]/80 p-4">
          {loading && <p className="text-sm font-semibold text-[#8b877d]">Loading gallery...</p>}

          {!loading && items.length === 0 && (
            <div className="flex min-h-80 items-center justify-center rounded-xl border border-dashed border-[#c9c5bb] bg-white px-6 text-center">
              <div className="max-w-sm">
                <p className="text-lg font-black text-[#14140f]">No ads have been generated yet</p>
                <p className="mt-2 text-sm font-medium text-[#8b877d]">
                  Create your first ad from the generator and it will appear here automatically.
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {items.map((item, i) => (
              <div
                key={item.ad_id}
                className={`overflow-hidden rounded-xl bg-linear-to-br ${CARD_GRADIENTS[i % CARD_GRADIENTS.length]} p-px shadow-[0_18px_50px_rgba(15,23,42,0.08)]`}
              >
                <div className="overflow-hidden rounded-[23px] bg-white">
                  <div className="relative">
                    <img src={toImageUrl(item.image_path)} alt={item.product_name} className="h-52 w-full object-cover" />
                    {item.video_path && (
                      <span className="absolute left-3 top-3 rounded-full bg-black/80 px-2.5 py-1 text-[11px] font-bold text-white">
                        Video Ready
                      </span>
                    )}
                  </div>
                  <div className="p-4">
                    <p className="truncate text-sm font-black text-[#14140f]">{item.product_name}</p>
                    <p className="mt-1 text-xs font-semibold text-[#8b877d]">
                      {new Date(item.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </p>
                    <div className="mt-4 flex gap-2">
                      <button
                        onClick={() => openDetail(item.ad_id)}
                        className="flex-1 rounded-xl bg-[#e7e4dc] px-3 py-2 text-xs font-black text-[#14140f] transition hover:bg-[#e7e4dc]"
                      >
                        View
                      </button>
                     <button
  onClick={() => downloadFile(toImageUrl(item.image_path), `${item.product_name}_ad.jpg`)}
  className="flex-1 py-1.5 bg-black text-white text-xs font-black rounded-lg text-center"
>
  Download
</button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      {detail && (
        <div
          onClick={() => setDetail(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#0a0a0a]/70 p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-5xl overflow-hidden rounded-[28px] bg-white shadow-[0_30px_120px_rgba(15,23,42,0.35)]"
          >
            <div className="flex items-center justify-between border-b border-[#d5d1c6] px-5 py-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">Ad Details</p>
                <h3 className="mt-1 text-lg font-black text-[#14140f]">{detail.product_name}</h3>
              </div>
              <button onClick={() => setDetail(null)} className="rounded-full p-2 text-[#8b877d] transition hover:bg-[#e7e4dc] hover:text-[#0a0a0a]">✕</button>
            </div>

            <div className="grid gap-0 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="bg-[#0a0a0a] p-4 lg:p-6">
                <div className="space-y-4">
                  <div className="overflow-hidden rounded-[22px] border border-white/10 bg-white/5">
                    <img src={toImageUrl(detail.image_path)} className="w-full object-cover" alt={detail.product_name} />
                  </div>
                  {detail.video_path && (
                    <div className="overflow-hidden rounded-[22px] border border-white/10 bg-black">
                      <video src={toImageUrl(detail.video_path)} controls className="w-full" />
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-5 p-5 lg:p-6">
                <div className="rounded-[22px] border border-[#d5d1c6] bg-[#fbfaf7] p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">Headline</p>
                  <p className="mt-2 text-lg font-black text-[#14140f]">{detail.headline}</p>
                </div>

                <div className="rounded-[22px] border border-[#d5d1c6] bg-[#fbfaf7] p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">Caption</p>
                  <p className="mt-2 text-sm leading-6 text-[#56544d]">{detail.caption}</p>
                </div>

                <div className="rounded-[22px] border border-[#d5d1c6] bg-[#fbfaf7] p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">Hashtags</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {detail.hashtags?.split(',').filter(Boolean).map((h) => (
                      <span key={h} className="rounded-full border border-[#d5d1c6] bg-white px-3 py-1 text-xs font-bold text-[#56544d]">
                        #{h.trim()}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs font-bold text-[#56544d]">
                  <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                    <p className="uppercase tracking-[0.18em] text-[#8b877d]">Platform</p>
                    <p className="mt-1 text-[#14140f]">{detail.platform || '—'}</p>
                  </div>
                  <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                    <p className="uppercase tracking-[0.18em] text-[#8b877d]">Mood</p>
                    <p className="mt-1 text-[#14140f]">{detail.mood || '—'}</p>
                  </div>
                  <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                    <p className="uppercase tracking-[0.18em] text-[#8b877d]">Format</p>
                    <p className="mt-1 text-[#14140f]">{detail.aspect_ratio || '—'}</p>
                  </div>
                  <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                    <p className="uppercase tracking-[0.18em] text-[#8b877d]">Created</p>
                    <p className="mt-1 text-[#14140f]">{new Date(detail.created_at).toLocaleDateString('en-GB')}</p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                 <button
  onClick={() => downloadFile(toImageUrl(detail.image_path), `${detail.product_name}_ad.jpg`)}
  className="flex-1 py-2 bg-black text-white font-black rounded-lg text-sm text-center"
>
  ⬇ Download Image
</button>
{detail.video_path && (
  <button
    onClick={() => downloadFile(toImageUrl(detail.video_path!), `${detail.product_name}_ad.mp4`)}
    className="flex-1 py-2 bg-[#14140f] text-white font-black rounded-lg text-sm text-center"
  >
    ⬇ Download Video
  </button>
)}
                  {detail.video_path ? (
                    <a
                      href={toImageUrl(detail.video_path)}
                      download
                      className="rounded-xl bg-[#56544d] px-4 py-3 text-center text-sm font-black text-white transition hover:bg-[#8b877d]"
                    >
                      Download Video
                    </a>
                  ) : (
                    <div className="rounded-xl border border-dashed border-[#c9c5bb] px-4 py-3 text-center text-sm font-semibold text-[#8b877d]">
                      Video not generated yet
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}