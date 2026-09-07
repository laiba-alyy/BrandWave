/*
 * Auth pages ke chhote presentational tukde — brand lockup, icons, alerts.
 * Yahan koi hook/state nahi hai, is liye ye server aur client dono taraf se
 * import ho sakte hain (pages server hain, forms 'use client').
 */
import Link from 'next/link'
import Logo from '@/components/home/Logo'

export function AuthBrand({ href = '/' }: { href?: string }) {
  return (
    <Link className="au__brand" href={href}>
      <Logo size={26} />
      BrandWave
    </Link>
  )
}

export function Spinner() {
  return <span className="au__spin" aria-hidden="true" />
}

export function Alert({
  kind,
  children,
}: {
  kind: 'error' | 'ok'
  children: React.ReactNode
}) {
  return (
    <div className={`au__alert au__alert--${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {kind === 'error' ? <IconAlert /> : <IconCheckCircle />}
      <span>{children}</span>
    </div>
  )
}

/* ---------------- icons ---------------- */

const stroke = {
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function IconMail({ className = 'au__icon' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m3.5 7.5 7.36 4.9a2 2 0 0 0 2.28 0l7.36-4.9" />
    </svg>
  )
}

export function IconLock({ className = 'au__icon' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <rect x="4" y="10" width="16" height="10" rx="2.5" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2" />
    </svg>
  )
}

export function IconStore({ className = 'au__icon' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <path d="M4 9h16v10a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19V9ZM4 9l1.4-4.2A1.5 1.5 0 0 1 6.8 3.7h10.4a1.5 1.5 0 0 1 1.4 1.1L20 9M9.5 20.5V14h5v6.5" />
    </svg>
  )
}

export function IconEye({ off = false }: { off?: boolean }) {
  return off ? (
    <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <path d="M4 4.5 20 20M10.6 10.7a2 2 0 0 0 2.8 2.8" />
      <path d="M6.6 6.9C4.7 8.2 3.3 10 2.5 12c1.6 3.8 5.3 6.3 9.5 6.3 1.5 0 3-.3 4.3-.9M17.9 16A11.6 11.6 0 0 0 21.5 12C19.9 8.2 16.2 5.7 12 5.7c-.9 0-1.8.1-2.6.3" />
    </svg>
  ) : (
    <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <path d="M2.5 12C4.1 8.2 7.8 5.7 12 5.7s7.9 2.5 9.5 6.3c-1.6 3.8-5.3 6.3-9.5 6.3S4.1 15.8 2.5 12Z" />
      <circle cx="12" cy="12" r="2.6" />
    </svg>
  )
}

export function IconArrow() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true" {...stroke} strokeWidth={1.7}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  )
}

export function IconArrowLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" {...stroke} strokeWidth={1.7}>
      <path d="M13 8H3M7 4 3 8l4 4" />
    </svg>
  )
}

export function IconCheck() {
  return (
    <svg width="9" height="9" viewBox="0 0 12 12" aria-hidden="true" {...stroke} strokeWidth={2.2}>
      <path d="M2 6.4 4.6 9 10 3.2" />
    </svg>
  )
}

export function IconCheckCircle() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.3 2.6 2.6L16 9.5" />
    </svg>
  )
}

export function IconAlert() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.6v5.2M12 16.2h.01" />
    </svg>
  )
}

export function IconEnvelopeBig() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" {...stroke} strokeWidth={1.5}>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m3.5 7.5 7.36 4.9a2 2 0 0 0 2.28 0l7.36-4.9" />
    </svg>
  )
}

export function IconKeyBig() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" {...stroke} strokeWidth={1.5}>
      <circle cx="8.5" cy="12" r="4" />
      <path d="M12.5 12H21M18 12v3M15.5 12v2.2" />
    </svg>
  )
}

export function IconGoogle() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.77 3.28-8.03z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-1.01.68-2.3 1.09-3.71 1.09-2.85 0-5.27-1.925-6.14-4.5H3.36v2.86C5.08 20.7 8.41 23 12 23z"
      />
      <path
        fill="#FBBC04"
        d="M5.84 14.09c-.22-.68-.35-1.41-.35-2.09s.13-1.41.35-2.09V6.62H3.36C2.43 8.64 2 10.74 2 12c0 1.26.43 2.36 1.36 3.38l2.48-1.29z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.4 0 2.67.47 3.66 1.45l2.73-2.73C17.46 2.09 14.97 1 12 1c-3.59 0-6.92 2.3-8.64 5.62l2.48 1.29c.87-2.58 3.29-4.53 6.16-4.53z"
      />
    </svg>
  )
}
