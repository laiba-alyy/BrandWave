'use client'

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useSearchParams } from 'next/navigation'
import { useActiveBrand } from '@/lib/useActiveBrand'
import {
  chatbotApi,
  wsUrl,
  ChatbotInstance,
  ConversationSummary,
  MessageItem,
} from '@/lib/chatbotApi'
import {
  BotAvatar,
  EmptyState,
  ErrorBanner,
  IconAlert,
  IconChat,
  IconChevronDown,
  IconClose,
  IconDownload,
  IconFilter,
  IconSearch,
  PageHeader,
  Spinner,
  StatCard,
  formatRelative,
  parseDate,
} from '@/components/chatbot/shared'

type DateRange = 'all' | 'today' | 'yesterday' | 'last7' | 'last30'
type StatusFilter = 'all' | 'active' | 'escalated'

const DATE_RANGES: { id: DateRange; label: string }[] = [
  { id: 'all', label: 'All time' },
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'last7', label: 'Last 7 days' },
  { id: 'last30', label: 'Last 30 days' },
]

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'active', label: 'Active' },
  { id: 'escalated', label: 'Escalated' },
]

/** Conversation ka start date range ke andar aata hai ya nahi. */
function withinRange(startedAt: string | null, range: DateRange): boolean {
  if (range === 'all') return true
  const date = parseDate(startedAt)
  if (!date) return false

  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)

  if (range === 'today') return date >= startOfToday
  if (range === 'yesterday') {
    const startOfYesterday = new Date(startOfToday)
    startOfYesterday.setDate(startOfYesterday.getDate() - 1)
    return date >= startOfYesterday && date < startOfToday
  }

  const days = range === 'last7' ? 7 : 30
  const cutoff = new Date(startOfToday)
  cutoff.setDate(cutoff.getDate() - (days - 1))
  return date >= cutoff
}

// useSearchParams ko Suspense boundary chahiye — warna `next build` prerender
// step par fail karta hai.
export default function ConversationsPage() {
  return (
    <Suspense
      fallback={
        <>
          <PageHeader title="Conversations" subtitle="Loading…" />
          <div className="flex items-center justify-center gap-2.5 py-24 text-xs font-semibold text-[#8b877d]">
            <Spinner />
            Loading conversations…
          </div>
        </>
      }
    >
      <ConversationsView />
    </Suspense>
  )
}

function ConversationsView() {
  const { userId: ctxUserId } = useActiveBrand()
  const searchParams = useSearchParams()

  const [userId, setUserId] = useState('')
  const [bots, setBots] = useState<ChatbotInstance[]>([])
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filters
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [botFilter, setBotFilter] = useState(searchParams.get('bot') ?? 'all')
  const [dateRange, setDateRange] = useState<DateRange>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Detail panel
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [escalating, setEscalating] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  // WS handler ek hi baar bindta hai — khuli conversation ka id ref se padho
  // taake handler ko har selection par dobara subscribe na karna pare.
  const selectedIdRef = useRef<number | null>(null)
  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])

  /* ── Search debounce ────────────────────── */
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim().toLowerCase()), 350)
    return () => clearTimeout(timer)
  }, [searchInput])

  /* ── Data loading ───────────────────────── */

  const loadConversations = useCallback(async (uid: string) => {
    try {
      const res = await chatbotApi.getConversations(uid)
      setConversations(res.data ?? [])
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conversations')
    }
  }, [])

  // userId context se — auth guard DashboardShell mein hai.
  useEffect(() => {
    if (!ctxUserId) return
    const init = async () => {
      setUserId(ctxUserId)

      // Bots aur conversations ek doosre par depend nahi karte — PARALLEL.
      // Pehle sequential the, yani bot list ka poora round-trip conversations
      // se pehle khali screen par guzarta tha.
      const botsPromise = chatbotApi.getMyBots(ctxUserId)
        .then(res => setBots(res.data ?? []))
        .catch(() => {
          // Bot filter optional hai — fail ho to conversations phir bhi dikhao
        })

      await Promise.all([botsPromise, loadConversations(ctxUserId)])
      setLoading(false)
    }
    init()
  }, [ctxUserId, loadConversations])

  /* ── Real-time updates ──────────────────── */

  useEffect(() => {
    if (!userId) return

    const ws = new WebSocket(wsUrl(`/api/chatbot/ws/${userId}`))
    wsRef.current = ws

    ws.onmessage = async () => {
      // new_conversation ya escalation event — list refresh karo aur agar khuli
      // conversation hai to uske messages bhi dobara load karo.
      await loadConversations(userId)
      const openId = selectedIdRef.current
      if (openId) {
        try {
          const res = await chatbotApi.getMessages(openId)
          setMessages(res.data ?? [])
        } catch {
          // detail refresh non-critical
        }
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [userId, loadConversations])

  /* ── Derived ────────────────────────────── */

  const filtered = useMemo(
    () =>
      conversations.filter((conv) => {
        if (botFilter !== 'all' && conv.bot_id !== botFilter) return false
        if (statusFilter === 'escalated' && !conv.is_escalated) return false
        if (statusFilter === 'active' && conv.is_escalated) return false
        if (!withinRange(conv.started_at, dateRange)) return false
        if (!search) return true
        return (
          conv.customer_session_id.toLowerCase().includes(search) ||
          (conv.last_message ?? '').toLowerCase().includes(search) ||
          (conv.bot_name ?? '').toLowerCase().includes(search)
        )
      }),
    [conversations, botFilter, statusFilter, dateRange, search]
  )

  const stats = useMemo(() => {
    const escalated = conversations.filter((c) => c.is_escalated).length
    const scores = conversations
      .map((c) => c.avg_confidence)
      .filter((s): s is number => s !== null && s !== undefined)
    return {
      total: conversations.length,
      active: conversations.length - escalated,
      escalated,
      avgConfidence: scores.length
        ? `${Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100)}%`
        : '—',
    }
  }, [conversations])

  const selectedConversation = conversations.find((c) => c.id === selectedId) ?? null
  const activeFilterCount =
    (botFilter !== 'all' ? 1 : 0) + (dateRange !== 'all' ? 1 : 0) + (statusFilter !== 'all' ? 1 : 0)

  const botColor = (botId: string) => bots.find((b) => b.bot_id === botId)?.primary_color ?? '#000000'

  /* ── Actions ────────────────────────────── */

  const selectConversation = async (id: number) => {
    setSelectedId(id)
    setLoadingMessages(true)
    setMessages([])
    try {
      const res = await chatbotApi.getMessages(id)
      setMessages(res.data ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load messages')
    } finally {
      setLoadingMessages(false)
    }
  }

  const handleEscalate = async () => {
    if (!selectedId) return
    setEscalating(true)
    try {
      await chatbotApi.escalate(selectedId)
      setConversations((prev) =>
        prev.map((c) => (c.id === selectedId ? { ...c, is_escalated: true } : c))
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to escalate conversation')
    } finally {
      setEscalating(false)
    }
  }

  const handleExport = () => {
    if (!selectedConversation) return

    const lines = [
      `Conversation transcript`,
      `Bot: ${selectedConversation.bot_name ?? 'Chatbot'}`,
      `Session: ${selectedConversation.customer_session_id}`,
      `Started: ${parseDate(selectedConversation.started_at)?.toLocaleString() ?? 'Unknown'}`,
      `Status: ${selectedConversation.is_escalated ? 'Escalated' : 'Active'}`,
      ``,
      ...messages.map((m) => {
        const time = parseDate(m.created_at)?.toLocaleString() ?? ''
        const who = m.sender === 'customer' ? 'Customer' : 'Bot'
        const confidence =
          m.sender === 'bot' && m.confidence_score !== null
            ? ` (confidence ${Math.round(m.confidence_score * 100)}%)`
            : ''
        return `[${time}] ${who}${confidence}:\n${m.content}\n`
      }),
    ]

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `transcript-${selectedConversation.customer_session_id.slice(0, 8)}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  /* ── Render ─────────────────────────────── */

  return (
    <>
      <PageHeader title="Conversations" subtitle="Live customer chats — escalated ones need your attention">
        <button
          onClick={() => userId && loadConversations(userId)}
          className="px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors"
        >
          Refresh
        </button>
      </PageHeader>

      <div className="px-8 pt-6">
        <ErrorBanner message={error} onRetry={() => userId && loadConversations(userId)} />

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
          <StatCard label="Total" value={stats.total} delay={0} />
          <StatCard label="Active" value={stats.active} accent="emerald" delay={0.05} />
          <StatCard label="Escalated" value={stats.escalated} accent="red" delay={0.1} />
          <StatCard label="Avg Confidence" value={stats.avgConfidence} delay={0.15} />
        </div>

        {/* Search + filter toggle */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 min-w-0">
            <IconSearch className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8b877d]" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by session, message or bot name…"
              className="w-full pl-10 pr-9 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d]"
            />
            {searchInput && (
              <button
                onClick={() => setSearchInput('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8b877d] hover:text-[#14140f] transition-colors"
                title="Clear search"
              >
                <IconClose className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <button
            onClick={() => setShowFilters((v) => !v)}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold rounded-xl border transition-colors shrink-0 ${
              showFilters || activeFilterCount > 0
                ? 'border-black text-[#14140f]'
                : 'border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a]'
            }`}
          >
            <IconFilter className="w-3.5 h-3.5" />
            Filters
            {activeFilterCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-black text-white text-[10px] font-black flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
            <IconChevronDown className={`w-3 h-3 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {/* Advanced filters */}
        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="rounded-xl border border-[#d5d1c6] bg-white p-5 mb-4 space-y-5">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d] mb-2.5">Bot</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => setBotFilter('all')}
                      className={`px-3.5 py-1.5 text-xs font-bold rounded-lg border transition-all ${
                        botFilter === 'all'
                          ? 'bg-black text-white border-black'
                          : 'bg-white text-[#56544d] border-[#d5d1c6] hover:border-[#0a0a0a]'
                      }`}
                    >
                      All Bots
                    </button>
                    {bots.map((bot) => (
                      <button
                        key={bot.bot_id}
                        onClick={() => setBotFilter(bot.bot_id)}
                        className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-bold rounded-lg border transition-all ${
                          botFilter === bot.bot_id
                            ? 'bg-black text-white border-black'
                            : 'bg-white text-[#56544d] border-[#d5d1c6] hover:border-[#0a0a0a]'
                        }`}
                      >
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: bot.primary_color }}
                        />
                        {bot.bot_name}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d] mb-2.5">
                    Date Range
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {DATE_RANGES.map((r) => (
                      <button
                        key={r.id}
                        onClick={() => setDateRange(r.id)}
                        className={`px-3.5 py-1.5 text-xs font-bold rounded-lg border transition-all ${
                          dateRange === r.id
                            ? 'bg-black text-white border-black'
                            : 'bg-white text-[#56544d] border-[#d5d1c6] hover:border-[#0a0a0a]'
                        }`}
                      >
                        {r.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d] mb-2.5">Status</p>
                  <div className="flex flex-wrap gap-2">
                    {STATUS_FILTERS.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setStatusFilter(s.id)}
                        className={`px-3.5 py-1.5 text-xs font-bold rounded-lg border transition-all ${
                          statusFilter === s.id
                            ? 'bg-black text-white border-black'
                            : 'bg-white text-[#56544d] border-[#d5d1c6] hover:border-[#0a0a0a]'
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>

                {activeFilterCount > 0 && (
                  <button
                    onClick={() => {
                      setBotFilter('all')
                      setDateRange('all')
                      setStatusFilter('all')
                    }}
                    className="text-xs font-bold text-[#8b877d] hover:text-[#14140f] transition-colors"
                  >
                    Clear all filters
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Split layout */}
      <div className="flex border-t border-[#e7e4dc] h-[calc(100vh-56px)]">
        {/* List */}
        <div className="w-full lg:w-[380px] border-r border-[#e7e4dc] overflow-y-auto shrink-0">
          {loading ? (
            <div className="flex items-center justify-center gap-2.5 py-16 text-xs font-semibold text-[#8b877d]">
              <Spinner />
              Loading…
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={IconChat}
                title={conversations.length === 0 ? 'No conversations yet' : 'No matches'}
                description={
                  conversations.length === 0
                    ? 'Customer chats will appear here in real time once your widget is live.'
                    : 'Try a different search term or adjust your filters.'
                }
              />
            </div>
          ) : (
            filtered.map((conv) => (
              <button
                key={conv.id}
                onClick={() => selectConversation(conv.id)}
                className={`w-full text-left px-5 py-4 border-b border-[#fbfaf7] transition-colors ${
                  selectedId === conv.id ? 'bg-[#fbfaf7]' : 'hover:bg-[#fbfaf7]'
                } ${conv.is_escalated ? 'border-l-4 border-l-red-500' : ''}`}
              >
                <div className="flex items-start gap-3">
                  <BotAvatar
                    name={conv.bot_name ?? 'Bot'}
                    color={botColor(conv.bot_id)}
                    size="sm"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <p className="text-xs font-black text-[#14140f] truncate">
                        {conv.bot_name ?? 'Chatbot'}
                      </p>
                      {conv.is_escalated ? (
                        <span className="shrink-0 text-[9px] font-black uppercase tracking-wide px-2 py-0.5 rounded-full bg-[#e6c3c8] text-[#96203f]">
                          Escalated
                        </span>
                      ) : (
                        <span className="shrink-0 text-[9px] font-black uppercase tracking-wide px-2 py-0.5 rounded-full bg-[#eaf4ee] text-[#12876b]">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] font-mono text-[#8b877d] truncate mb-1.5">
                      {conv.customer_session_id.slice(0, 16)}…
                    </p>
                    <p className="text-xs text-[#8b877d] line-clamp-2 mb-2 leading-relaxed">
                      {conv.last_message || 'No messages yet'}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-[#8b877d]">
                      <span>{conv.message_count} messages</span>
                      <span>{formatRelative(conv.started_at)}</span>
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Details */}
        <div className="hidden lg:flex flex-1 flex-col bg-[#fbfaf7]">
          {!selectedConversation ? (
            <div className="flex-1 flex items-center justify-center p-8">
              <div className="text-center max-w-xs">
                <div className="w-12 h-12 rounded-xl bg-white border border-[#d5d1c6] flex items-center justify-center mx-auto mb-4 text-[#8b877d]">
                  <IconChat className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-[#14140f] mb-1">No conversation selected</h3>
                <p className="text-xs text-[#8b877d]">
                  Pick a conversation from the list to read the full thread and see confidence scores.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Detail header */}
              <div className="px-6 py-4 bg-white border-b border-[#e7e4dc] flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <BotAvatar
                    name={selectedConversation.bot_name ?? 'Bot'}
                    color={botColor(selectedConversation.bot_id)}
                    size="sm"
                  />
                  <div className="min-w-0">
                    <p className="text-xs font-black text-[#14140f] truncate">
                      {selectedConversation.bot_name ?? 'Chatbot'}
                    </p>
                    <p className="text-[11px] font-mono text-[#8b877d] truncate">
                      {selectedConversation.customer_session_id}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={handleExport}
                    disabled={messages.length === 0}
                    className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors disabled:opacity-40"
                    title="Download transcript"
                  >
                    <IconDownload className="w-3.5 h-3.5" />
                    Export
                  </button>
                  {selectedConversation.is_escalated ? (
                    <span className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold rounded-lg bg-[#e6c3c8] text-[#96203f]">
                      <IconAlert className="w-3.5 h-3.5" />
                      Escalated
                    </span>
                  ) : (
                    <button
                      onClick={handleEscalate}
                      disabled={escalating}
                      className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold rounded-lg bg-[#fbeaec] text-[#96203f] hover:bg-[#e6c3c8] transition-colors disabled:opacity-50"
                    >
                      {escalating ? <Spinner className="w-3.5 h-3.5" /> : <IconAlert className="w-3.5 h-3.5" />}
                      Escalate
                    </button>
                  )}
                </div>
              </div>

              {/* Session info + stats */}
              <div className="px-6 py-4 bg-white border-b border-[#e7e4dc] grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  ['Started', parseDate(selectedConversation.started_at)?.toLocaleString() ?? '—'],
                  ['Messages', String(selectedConversation.message_count)],
                  ['Status', selectedConversation.is_escalated ? 'Escalated' : 'Active'],
                  [
                    'Avg Confidence',
                    selectedConversation.avg_confidence !== null
                      ? `${Math.round(selectedConversation.avg_confidence * 100)}%`
                      : '—',
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="min-w-0">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-[#8b877d] mb-1">
                      {label}
                    </p>
                    <p className="text-xs font-bold text-[#14140f] truncate">{value}</p>
                  </div>
                ))}
              </div>

              {/* Message thread */}
              <div className="flex-1 overflow-y-auto p-6 space-y-3">
                {loadingMessages ? (
                  <div className="flex items-center justify-center gap-2.5 py-12 text-xs font-semibold text-[#8b877d]">
                    <Spinner />
                    Loading messages…
                  </div>
                ) : messages.length === 0 ? (
                  <div className="text-center py-12 text-xs text-[#8b877d]">
                    No messages in this conversation yet.
                  </div>
                ) : (
                  messages.map((m) => (
                    <div
                      key={m.id}
                      className={`flex ${m.sender === 'customer' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div className="max-w-[70%]">
                        <div
                          className={`rounded-xl px-4 py-2.5 text-xs leading-relaxed ${
                            m.sender === 'customer'
                              ? 'bg-black text-white rounded-br-sm'
                              : 'bg-white text-[#14140f] border border-[#d5d1c6] rounded-bl-sm'
                          }`}
                        >
                          <p className="whitespace-pre-wrap">{m.content}</p>
                        </div>
                        <div
                          className={`flex items-center gap-2 mt-1.5 px-1 text-[10px] text-[#8b877d] ${
                            m.sender === 'customer' ? 'justify-end' : 'justify-start'
                          }`}
                        >
                          <span>{m.sender === 'customer' ? 'Customer' : 'Bot'}</span>
                          <span>·</span>
                          <span>{parseDate(m.created_at)?.toLocaleTimeString() ?? ''}</span>
                          {m.sender === 'bot' && m.confidence_score !== null && (
                            <>
                              <span>·</span>
                              <span
                                className={`font-bold ${
                                  m.confidence_score >= 0.7
                                    ? 'text-[#12876b]'
                                    : m.confidence_score >= 0.5
                                    ? 'text-[#a8620d]'
                                    : 'text-[#96203f]'
                                }`}
                              >
                                {Math.round(m.confidence_score * 100)}% confidence
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
