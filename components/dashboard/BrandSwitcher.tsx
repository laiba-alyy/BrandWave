'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'

/**
 * Top-bar brand switcher.
 *
 * Multi-brand accounts ke liye zaroori hai: har module ab active brand par
 * scope hota hai, to user ko saaf dikhna chahiye ke wo kis brand par kaam kar
 * raha hai aur switch kar sakna chahiye.
 */
export default function BrandSwitcher({ compact = false }: { compact?: boolean }) {
  const router = useRouter()
  const { brands, activeBrand, setActiveBrandId, loading, error, refreshBrands } = useActiveBrand()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  // Skeleton sirf pehli load ke liye. Agar loading kabhi resolve na ho to
  // yahan koi clickable element nahi hota — is liye neeche error/empty dono
  // cases par hamesha ek actionable button render hota hai.
  if (loading) {
    return (
      <div
        className="h-8 w-40 rounded-lg bg-[#e7e4dc] animate-pulse"
        aria-busy="true"
        aria-label="Loading brands"
      />
    )
  }

  if (error) {
    return (
      <button
        onClick={() => refreshBrands()}
        title={error}
        className="flex items-center gap-2 rounded-lg border border-[#e6c3c8] bg-[#fbeaec] px-3 py-1.5 text-xs font-bold text-[#96203f] transition-colors hover:bg-[#e6c3c8]"
      >
        Brands unavailable — retry
      </button>
    )
  }

  // Koi brand hi nahi — switcher ki jagah seedha scraping par bhejo
  if (brands.length === 0) {
    return (
      <button
        onClick={() => router.push('/business/scraping')}
        className="flex items-center gap-2 rounded-lg border border-dashed border-[#c9c5bb] px-3 py-1.5 text-xs font-bold text-[#8b877d] transition-colors hover:border-[#14140f] hover:text-[#14140f]"
      >
        <PlusIcon />
        Add your first brand
      </button>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex max-w-[240px] items-center gap-2 rounded-lg border border-[#d5d1c6] bg-white px-3 py-1.5 transition-colors hover:border-[#14140f]"
        title="Switch brand"
      >
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-black text-[10px] font-black text-white">
          {(brandLabel(activeBrand) || '?').charAt(0).toUpperCase()}
        </span>
        {!compact && (
          <span className="truncate text-xs font-bold text-[#14140f]">
            {brandLabel(activeBrand) || 'Select brand'}
          </span>
        )}
        <svg
          className={`h-3 w-3 shrink-0 text-[#8b877d] transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-xl border border-[#d5d1c6] bg-white shadow-lg"
          >
            <p className="px-3 pt-2.5 pb-1 text-[10px] font-black uppercase tracking-wide text-[#8b877d]">
              Your brands ({brands.length})
            </p>
            <div className="max-h-72 overflow-y-auto py-1">
              {brands.map((b) => {
                const active = activeBrand?.id === b.id
                return (
                  <button
                    key={b.id}
                    onClick={() => {
                      setActiveBrandId(b.id)
                      setOpen(false)
                    }}
                    className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                      active ? 'bg-[#fbfaf7]' : 'hover:bg-[#fbfaf7]'
                    }`}
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-black text-[10px] font-black text-white">
                      {(brandLabel(b) || '?').charAt(0).toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-bold text-[#14140f]">{brandLabel(b)}</span>
                      <span className="block truncate text-[10px] text-[#8b877d]">
                        {b.product_count.toLocaleString()} products
                      </span>
                    </span>
                    {active && (
                      <svg className="h-3.5 w-3.5 shrink-0 text-black" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M20 6L9 17l-5-5" />
                      </svg>
                    )}
                  </button>
                )
              })}
            </div>
            <div className="border-t border-[#e7e4dc]">
              <button
                onClick={() => {
                  setOpen(false)
                  router.push('/business/scraping')
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-xs font-bold text-[#56544d] transition-colors hover:bg-[#fbfaf7]"
              >
                <PlusIcon />
                Add New Brand
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function PlusIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
    </svg>
  )
}
