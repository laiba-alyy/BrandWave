'use client'

/**
 * Ek hi jagah se error message dikhane ke liye.
 *
 * Wajah: SEO ke paanchon pages `if (res.ok) {...}` + `catch {}` karte the.
 * Yani 400 (multi-brand ambiguity), 429 (Groq rate limit) aur 500 — sab
 * BILKUL ek jaise dikhte the: spinner ruk jata tha aur screen par kuch nahi
 * badalta tha. User ko lagta tha button dead hai, to wo dobara click karta,
 * jis se rate limit aur bigar jati.
 *
 * Backend har case mein saaf `detail` message bhejta hai — usay dikhana hi
 * kaafi tha.
 */
export default function ErrorBanner({
  message,
  onDismiss,
  className = '',
}: {
  message: string
  onDismiss?: () => void
  className?: string
}) {
  if (!message) return null

  return (
    <div
      role="alert"
      className={`mb-5 flex items-start gap-2.5 rounded-xl border border-[#e6c3c8] bg-[#fbeaec] px-4 py-3 ${className}`}
    >
      <svg
        className="mt-0.5 h-4 w-4 shrink-0 text-[#96203f]"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0zM12 9v4M12 17h.01"
        />
      </svg>
      <p className="flex-1 text-xs font-semibold leading-relaxed text-[#96203f]">{message}</p>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 rounded px-1 text-[#e6c3c8] transition-colors hover:text-[#96203f] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#e6c3c8]"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  )
}
