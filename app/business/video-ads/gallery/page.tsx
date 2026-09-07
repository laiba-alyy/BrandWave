'use client'

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { downloadFile } from '@/lib/adsApi'
import {
  videoAdsApi, toMediaUrl,
  type VideoGalleryItem, type VideoGalleryDetail,
} from '@/lib/videoAdsApi'

export default function VideoAdsGalleryPage() {
  const supabase = useMemo(() => createClient(), [])
  const auth = supabase.auth
  const [items, setItems] = useState<VideoGalleryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<VideoGalleryDetail | null>(null)

  useEffect(() => {
    auth.getUser().then(({ data }) => {
      const uid = data.user?.id
      if (!uid) {
        setLoading(false)
        return
      }
      videoAdsApi.getGallery(uid)
        .then(setItems)
        .catch((e) => setError(e instanceof Error ? e.message : 'Could not load your videos'))
        .finally(() => setLoading(false))
    })
  }, [auth])

  const openDetail = async (videoId: number) => {
    try {
      setDetail(await videoAdsApi.getGalleryDetail(videoId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load that video')
    }
  }

  return (
    <div className="min-h-full px-6 lg:px-8 py-6">
      <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-[#8b877d]">Asset Library</p>
            <h1 className="mt-2 text-3xl font-black text-[#14140f]">Video Ads Gallery</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#56544d]">
              Every product video ad you have generated, newest first.
            </p>
          </div>
          <Link
            href="/business/video-ads"
            className="inline-flex items-center justify-center rounded-full bg-[#0a0a0a] px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-[#0a0a0a]/15 transition hover:bg-[#16160f]"
          >
            + New Video Ad
          </Link>
        </div>

        <div className="mt-6 rounded-xl border border-[#d5d1c6] bg-[#fbfaf7]/80 p-4">
          {loading && <p className="text-sm font-semibold text-[#8b877d]">Loading videos...</p>}

          {error && (
            <div className="rounded-xl border border-[#e6c3c8] bg-[#fbeaec] p-4 text-sm font-semibold text-[#96203f]">
              {error}
            </div>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="flex min-h-80 items-center justify-center rounded-xl border border-dashed border-[#c9c5bb] bg-white px-6 text-center">
              <div className="max-w-sm">
                <p className="text-lg font-black text-[#14140f]">No video ads yet</p>
                <p className="mt-2 text-sm font-medium text-[#8b877d]">
                  Generate your first product video and it will appear here automatically.
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <div
                key={item.video_id}
                className="overflow-hidden rounded-xl border border-[#d5d1c6] bg-white shadow-[0_18px_50px_rgba(15,23,42,0.08)]"
              >
                <div className="bg-black">
                  <video src={toMediaUrl(item.video_path)} controls loop className="w-full" preload="metadata" />
                </div>
                <div className="p-4">
                  <p className="truncate text-sm font-black text-[#14140f]">
                    {item.product_name || `Video #${item.video_id}`}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-bold">
                    <span className="rounded-full border border-[#d5d1c6] bg-[#fbfaf7] px-2 py-0.5 text-[#56544d]">
                      {item.duration_seconds ? `${item.duration_seconds}s` : 'video'}
                    </span>
                    {item.segments != null && item.segments > 1 && (
                      <span className="rounded-full border border-[#d5d1c6] bg-[#fbfaf7] px-2 py-0.5 text-[#56544d]">
                        {item.segments} segments
                      </span>
                    )}
                    <span className="rounded-full border border-[#d5d1c6] bg-[#fbfaf7] px-2 py-0.5 text-[#56544d]">
                      {item.source === 'image_ad' ? 'from image ad' : 'from product'}
                    </span>
                    {item.provider && (
                      <span className="rounded-full border border-[#f2d6a6] bg-[#fdf4e6] px-2 py-0.5 text-[#a8620d]">
                        {item.provider}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-[11px] font-semibold text-[#8b877d]">
                    {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button
                      onClick={() => openDetail(item.video_id)}
                      className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-2 text-xs font-black text-[#14140f] transition hover:border-[#0a0a0a]"
                    >
                      View
                    </button>
                    <button
                      onClick={() => downloadFile(
                        toMediaUrl(item.video_path),
                        `${(item.product_name || 'product').replace(/[^a-z0-9]/gi, '_')}_video_ad.mp4`
                      )}
                      className="rounded-xl bg-[#0a0a0a] px-3 py-2 text-xs font-black text-white transition hover:bg-[#16160f]"
                    >
                      Download
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {detail && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#0a0a0a]/60 p-6">
          <div className="my-10 w-full max-w-3xl overflow-hidden rounded-[28px] bg-white shadow-[0_30px_120px_rgba(15,23,42,0.35)]">
            <div className="flex items-center justify-between border-b border-[#d5d1c6] p-5">
              <h3 className="text-lg font-black text-[#14140f]">
                {detail.product_name || `Video #${detail.video_id}`}
              </h3>
              <button onClick={() => setDetail(null)} className="text-xl text-[#8b877d] transition hover:text-[#0a0a0a]">✕</button>
            </div>
            <div className="space-y-4 p-5">
              <div className="overflow-hidden rounded-xl bg-black">
                <video src={toMediaUrl(detail.video_path)} controls loop className="w-full" />
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs font-bold text-[#56544d] sm:grid-cols-3">
                {([
                  ['Length', detail.duration_seconds ? `${detail.duration_seconds}s` : '—'],
                  ['Segments', detail.segments ?? '—'],
                  ['Source', detail.source === 'image_ad' ? 'Image ad' : 'Product'],
                  ['Provider', detail.provider ?? '—'],
                  ['Plan', detail.user_plan ?? '—'],
                  ['Style', detail.ad_style ?? '—'],
                  ['Scene', detail.scene ?? '—'],
                  ['Camera', detail.camera_motion ?? '—'],
                ] as [string, string | number][]).map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-2">
                    <p className="uppercase tracking-[0.18em] text-[#8b877d]">{k}</p>
                    <p className="mt-1 truncate text-[#14140f]">{v}</p>
                  </div>
                ))}
              </div>

              {detail.custom_prompt && (
                <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] p-4">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[#8b877d]">Your prompt</p>
                  <p className="mt-2 text-sm leading-6 text-[#56544d]">{detail.custom_prompt}</p>
                </div>
              )}

              <button
                onClick={() => downloadFile(
                  toMediaUrl(detail.video_path),
                  `${(detail.product_name || 'product').replace(/[^a-z0-9]/gi, '_')}_video_ad.mp4`
                )}
                className="w-full rounded-xl bg-[#0a0a0a] px-4 py-3 text-sm font-black text-white transition hover:bg-[#16160f]"
              >
                Download Video
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
