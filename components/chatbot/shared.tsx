'use client'

import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'
import type { BotCategory, BotStatus, BotTone, DocumentSource } from '@/lib/chatbotApi'

/* ──────────────────────────────────────────────
   Constants
   ────────────────────────────────────────────── */

export const CATEGORIES: { id: BotCategory; name: string; description: string }[] = [
  { id: 'ecommerce', name: 'E-commerce', description: 'Products, orders and shipping questions' },
  { id: 'support', name: 'Support', description: 'FAQs, troubleshooting and issue resolution' },
  { id: 'sales', name: 'Sales', description: 'Lead qualification and product enquiries' },
  { id: 'custom', name: 'Custom', description: 'Build from scratch for your own use case' },
]

export const TONES: { id: BotTone; name: string; description: string; sample: string }[] = [
  {
    id: 'professional',
    name: 'Professional',
    description: 'Formal, precise and business-like',
    sample: 'Good day. I can certainly assist you with that enquiry — could you share your order number?',
  },
  {
    id: 'friendly',
    name: 'Friendly',
    description: 'Warm, welcoming and approachable',
    sample: "Hi there! Happy to help you with that — just pop your order number in and I'll take a look.",
  },
  {
    id: 'casual',
    name: 'Casual',
    description: 'Relaxed and conversational',
    sample: "Sure thing! Send over your order number and I'll sort it out for you.",
  },
  {
    id: 'empathetic',
    name: 'Empathetic',
    description: 'Understanding and reassuring',
    sample: "I'm really sorry about the trouble. Let's get this fixed — could you share your order number?",
  },
]

export const TRAITS = ['Helpful', 'Concise', 'Detailed', 'Patient', 'Proactive'] as const

/* Widget ke bubble ka rang — ab dashboard palette se. Pehle yahan indigo/
   sky/green/orange/red thay, jo kisi aur duniya ke rang hain. */
export const COLOR_PRESETS = ['#0a0a0a', '#f0a63c', '#12876b', '#96203f', '#b0761a', '#56544d']

export const STATUS_STYLES: Record<BotStatus, { label: string; badge: string; dot: string }> = {
  active: { label: 'Active', badge: 'dsh__badge dsh__badge--good', dot: 'bg-[#12876b]' },
  paused: { label: 'Paused', badge: 'dsh__badge dsh__badge--warn', dot: 'bg-[#d08a12]' },
  draft: { label: 'Draft', badge: 'dsh__badge', dot: 'bg-[#8b877d]' },
}

export const categoryName = (id: string) =>
  CATEGORIES.find((c) => c.id === id)?.name ?? 'Custom'

export const toneName = (id: string) => TONES.find((t) => t.id === id)?.name ?? 'Professional'

/* ──────────────────────────────────────────────
   Formatting helpers
   ────────────────────────────────────────────── */

export function formatBytes(bytes: number): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Backend naive datetime strings deta hai — unhe UTC maan kar parse karo. */
export function parseDate(value: string | null): Date | null {
  if (!value) return null
  const normalised = /[Zz]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value.replace(' ', 'T')}Z`
  const date = new Date(normalised)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDate(value: string | null): string {
  const date = parseDate(value)
  if (!date) return '—'
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatRelative(value: string | null): string {
  const date = parseDate(value)
  if (!date) return '—'
  const diff = Date.now() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(value)
}

/* ──────────────────────────────────────────────
   Icons — minimal stroked SVGs, no emoji
   ────────────────────────────────────────────── */

type IconProps = { className?: string }
const base = (className?: string) => className ?? 'w-4 h-4'

const Svg = ({ className, children }: IconProps & { children: ReactNode }) => (
  <svg
    className={base(className)}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    {children}
  </svg>
)

export const IconSearch = (p: IconProps) => (
  <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></Svg>
)
export const IconPlus = (p: IconProps) => (
  <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>
)
export const IconClose = (p: IconProps) => (
  <Svg {...p}><path d="M18 6L6 18M6 6l12 12" /></Svg>
)
export const IconGrid = (p: IconProps) => (
  <Svg {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></Svg>
)
export const IconList = (p: IconProps) => (
  <Svg {...p}><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></Svg>
)
export const IconTrash = (p: IconProps) => (
  <Svg {...p}><path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6M10 11v6M14 11v6" /></Svg>
)
export const IconMore = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="5" r="1.4" /><circle cx="12" cy="12" r="1.4" /><circle cx="12" cy="19" r="1.4" /></Svg>
)
export const IconCopy = (p: IconProps) => (
  <Svg {...p}><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></Svg>
)
export const IconPause = (p: IconProps) => (
  <Svg {...p}><path d="M10 4v16M14 4v16" /></Svg>
)
export const IconPlay = (p: IconProps) => (
  <Svg {...p}><path d="M6 4l14 8-14 8V4z" /></Svg>
)
export const IconUpload = (p: IconProps) => (
  <Svg {...p}><path d="M12 16V4M7 9l5-5 5 5M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></Svg>
)
export const IconDoc = (p: IconProps) => (
  <Svg {...p}><path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" /><path d="M14 3v5h5" /></Svg>
)
export const IconText = (p: IconProps) => (
  <Svg {...p}><path d="M4 6h16M4 12h16M4 18h10" /></Svg>
)
export const IconFaq = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 013.9-2 2.3 2.3 0 01.3 3.6c-.7.6-1.7 1-1.7 2M12 17h.01" /></Svg>
)
export const IconChat = (p: IconProps) => (
  <Svg {...p}><path d="M21 12a8 8 0 01-11.5 7.2L3 21l1.8-6.5A8 8 0 1121 12z" /></Svg>
)
export const IconBrain = (p: IconProps) => (
  <Svg {...p}><path d="M9 3a3 3 0 00-3 3 3 3 0 00-1 5.8A3 3 0 006.5 18 3 3 0 0012 19V4.5A2 2 0 009 3zM15 3a3 3 0 013 3 3 3 0 011 5.8A3 3 0 0117.5 18 3 3 0 0112 19" /></Svg>
)
export const IconSettings = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.6 1.6 0 00-1.8-.3 1.6 1.6 0 00-1 1.5V21a2 2 0 11-4 0v-.1A1.6 1.6 0 008 19.4a1.6 1.6 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.6 1.6 0 00.3-1.8 1.6 1.6 0 00-1.5-1H2a2 2 0 110-4h.1A1.6 1.6 0 004.6 8a1.6 1.6 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.6 1.6 0 001.8.3H9a1.6 1.6 0 001-1.5V2a2 2 0 114 0v.1a1.6 1.6 0 001 1.5 1.6 1.6 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.6 1.6 0 00-.3 1.8V9a1.6 1.6 0 001.5 1H22a2 2 0 110 4h-.1a1.6 1.6 0 00-1.5 1z" /></Svg>
)
export const IconAlert = (p: IconProps) => (
  <Svg {...p}><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0zM12 9v4M12 17h.01" /></Svg>
)
export const IconCheck = (p: IconProps) => (
  <Svg {...p}><path d="M20 6L9 17l-5-5" /></Svg>
)
export const IconChevronDown = (p: IconProps) => (
  <Svg {...p}><path d="M6 9l6 6 6-6" /></Svg>
)
export const IconArrowLeft = (p: IconProps) => (
  <Svg {...p}><path d="M19 12H5M12 19l-7-7 7-7" /></Svg>
)
export const IconArrowRight = (p: IconProps) => (
  <Svg {...p}><path d="M5 12h14M12 5l7 7-7 7" /></Svg>
)
export const IconDownload = (p: IconProps) => (
  <Svg {...p}><path d="M12 4v12M7 11l5 5 5-5M4 19v1a1 1 0 001 1h14a1 1 0 001-1v-1" /></Svg>
)
export const IconFilter = (p: IconProps) => (
  <Svg {...p}><path d="M3 5h18M6 12h12M10 19h4" /></Svg>
)
export const IconRefresh = (p: IconProps) => (
  <Svg {...p}><path d="M3 12a9 9 0 0115.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.2L3 16M3 21v-5h5" /></Svg>
)
export const IconLayers = (p: IconProps) => (
  <Svg {...p}><path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5" /></Svg>
)

export const sourceIcon = (source: DocumentSource) => {
  if (source === 'faq') return IconFaq
  if (source === 'text') return IconText
  return IconDoc
}

/* ──────────────────────────────────────────────
   Small shared components
   ────────────────────────────────────────────── */

export function BotAvatar({
  name,
  color,
  size = 'md',
}: {
  name: string
  color: string
  size?: 'sm' | 'md' | 'lg'
}) {
  const dims = size === 'sm' ? 'w-8 h-8 text-xs' : size === 'lg' ? 'w-14 h-14 text-lg' : 'w-11 h-11 text-sm'
  return (
    <div
      className={`${dims} rounded-xl flex items-center justify-center font-black text-white shrink-0`}
      style={{ backgroundColor: color || '#000000' }}
    >
      {(name || 'B').trim().charAt(0).toUpperCase()}
    </div>
  )
}

export function StatusBadge({ status }: { status: BotStatus }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.draft
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-full border ${style.badge}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  )
}

export function StatCard({
  label,
  value,
  accent,
  delay = 0,
}: {
  label: string
  value: string | number
  accent?: 'default' | 'emerald' | 'red' | 'amber'
  delay?: number
}) {
  const styles = {
    default: 'bg-white border-[#d5d1c6] text-[#14140f]',
    emerald: 'bg-[#eaf4ee] border-[#bcd8c8] text-[#12876b]',
    red: 'bg-[#fbeaec] border-[#e6c3c8] text-[#96203f]',
    amber: 'bg-[#fdf4e6] border-[#f2d6a6] text-[#a8620d]',
  }[accent ?? 'default']

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className={`rounded-xl border p-5 ${styles}`}
    >
      <p className="text-3xl font-black mb-1 leading-none">{value}</p>
      <p className="text-xs font-medium opacity-70">{label}</p>
    </motion.div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: (p: IconProps) => ReactNode
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-xl border border-dashed border-[#d5d1c6] bg-white py-16 px-6 text-center">
      <div className="w-12 h-12 rounded-xl bg-[#fbfaf7] border border-[#e7e4dc] flex items-center justify-center mx-auto mb-4 text-[#8b877d]">
        <Icon className="w-5 h-5" />
      </div>
      <h3 className="text-sm font-bold text-[#14140f] mb-1">{title}</h3>
      <p className="text-xs text-[#8b877d] max-w-sm mx-auto mb-5">{description}</p>
      {action}
    </div>
  )
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  if (!message) return null
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-[#e6c3c8] bg-[#fbeaec] px-4 py-3 mb-5">
      <div className="flex items-center gap-2.5 min-w-0">
        <IconAlert className="w-4 h-4 text-[#96203f] shrink-0" />
        <span className="text-xs font-semibold text-[#96203f] truncate">{message}</span>
      </div>
      {onRetry && (
        <button onClick={onRetry} className="text-xs font-bold text-[#96203f] hover:underline shrink-0">
          Retry
        </button>
      )}
    </div>
  )
}

export function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = 'Delete',
  danger = true,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={onCancel}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.15 }}
            className="w-full max-w-sm rounded-xl bg-white border border-[#d5d1c6] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-black text-[#14140f] mb-2">{title}</h3>
            <p className="text-xs text-[#8b877d] leading-relaxed mb-6">{description}</p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={onCancel}
                disabled={busy}
                className="px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                disabled={busy}
                className={`px-4 py-2 text-xs font-bold rounded-lg text-white transition-colors disabled:opacity-50 ${
                  danger ? 'bg-[#96203f] hover:bg-[#96203f]' : 'bg-black hover:bg-[#14140f]'
                }`}
              >
                {busy ? 'Working…' : confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Spinner({ className = 'w-4 h-4' }: { className?: string }) {
  return <div className={`${className} border-2 border-current border-t-transparent rounded-full animate-spin`} />
}

export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children?: ReactNode
}) {
  return (
    <div className="dsh__top">
      <div style={{ minWidth: 0 }}>
        <h1>{title}</h1>
        <p className="dsh__sub">{subtitle}</p>
      </div>
      <div className="dsh__topactions">{children}</div>
    </div>
  )
}
