'use client'

import { useEffect, useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface LlmStatus {
  retrying: boolean
  message: string | null
  seconds_remaining: number
}

/**
 * "AI service is busy, retrying..." banner.
 *
 * Groq ka rate limit hit hone par backend (modules/llm_config.py) Groq ka bataya
 * hua wait karke ek baar dobara try karta hai. Wo wait SERVER par hota hai, is
 * liye browser ko sirf ek lambi pending request nazar aati hai aur spinner jama
 * hua lagta hai.
 *
 * Waqt dekh kar andaza lagana yahan kaam NAHI karta: blog generation normally
 * bhi 30s+ leti hai, to "X second se zyada ho gaya = retry chal rahi hai" wala
 * banner aksar jhoot bolta. Is liye backend asli signal /api/llm/status par
 * deta hai (wahi flag jo call_with_retry set karta hai) aur ye component usay
 * poll karta hai.
 */
export default function AiRetryBanner() {
  const [status, setStatus] = useState<LlmStatus | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      // Tab background mein hai to poll karne ka koi faida nahi
      if (document.visibilityState !== 'visible') return
      try {
        const res = await fetch(`${API_BASE}/api/llm/status`, { cache: 'no-store' })
        if (!res.ok) return
        const data: LlmStatus = await res.json()
        if (!cancelled) setStatus(data)
      } catch {
        // Backend reachable nahi — banner chup rahe. Yahan error dikhana user ko
        // sirf confuse karega, kyunke ye status call unke kaam ka hissa nahi hai.
      }
    }

    poll()
    const id = setInterval(poll, 2000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  if (!status?.retrying) return null

  const seconds = Math.max(0, Math.ceil(status.seconds_remaining))

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed top-4 left-1/2 z-50 -translate-x-1/2 px-4 w-full max-w-md"
    >
      <div className="flex items-center gap-3 rounded-lg border border-[#f2d6a6] bg-[#fdf4e6] px-4 py-3 shadow-lg">
        <svg
          className="h-5 w-5 shrink-0 animate-spin text-[#a8620d]"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <div className="min-w-0">
          <p className="text-sm font-medium text-[#a8620d]">
            {status.message || 'AI service is busy, retrying...'}
          </p>
          <p className="text-xs text-[#a8620d]">
            {seconds > 0
              ? `Waiting ${seconds}s for the rate limit to clear — your request is still running.`
              : 'Retrying your request now...'}
          </p>
        </div>
      </div>
    </div>
  )
}
