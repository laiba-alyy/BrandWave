'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Link from 'next/link'
import { useActiveBrand } from '@/lib/useActiveBrand'
import { chatbotApi, ChatbotInstance, BotStatus } from '@/lib/chatbotApi'
import {
  BotAvatar,
  ConfirmModal,
  EmptyState,
  ErrorBanner,
  IconBrain,
  IconChat,
  IconClose,
  IconCopy,
  IconDoc,
  IconGrid,
  IconList,
  IconMore,
  IconPause,
  IconPlay,
  IconPlus,
  IconSearch,
  IconSettings,
  IconTrash,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
  categoryName,
  formatDate,
} from '@/components/chatbot/shared'

type ViewMode = 'grid' | 'list'
type StatusFilter = 'all' | BotStatus

const STATUS_TABS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'active', label: 'Active' },
  { id: 'paused', label: 'Paused' },
  { id: 'draft', label: 'Draft' },
]

export default function MyBotsPage() {
  const { userId: ctxUserId } = useActiveBrand()

    // userId SEEDHA context se. Pehle yahan ek local mirror state thi jise ek
  // effect context se sync karta tha — us effect ka koi aur kaam nahi tha,
  // aur wo har mount par ek fazool extra render deta tha.
  const userId = ctxUserId
  const [bots, setBots] = useState<ChatbotInstance[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')

  const [selected, setSelected] = useState<string[]>([])
  const [busyBotId, setBusyBotId] = useState<string | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [openMenu, setOpenMenu] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<ChatbotInstance | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)

  const menuRef = useRef<HTMLDivElement | null>(null)

    const loadBots = useCallback(async (uid: string) => {
    // Error KAAMYABI par saaf hota hai, shuru mein nahi. Pehle yahan pehla
    // kaam `setError('')` tha — pehle await se pehle, yani synchronously —
    // aur chunke ye ek effect se call hota hai, wo mount par ek fazool
    // cascading render deta tha. Reload ke dauran purana error ab screen par
    // rehta hai aur naya data aane par hatta hai.
    try {
      const res = await chatbotApi.getMyBots(uid)
      setBots(res.data ?? [])
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load chatbots')
    } finally {
      setLoading(false)
    }
  }, [])

  // userId context se — pehle yahan ek async getSession() gate tha jo asli
  // request se pehle ek poora tick kha jata tha. Auth guard DashboardShell mein.
    useEffect(() => {
    if (!ctxUserId) return
    /*
     * Mount par data laana — effect ka bilkul jaiz istemal.
     *
     * Rule yahan GHALAT-FEHMI ka shikar hai: ye `await` ki hadd ko nahi
     * samajhta. Neeche wala function apni saari setState calls pehle await ke
     * BAAD karta hai (test kiya gaya: `.then(setX)` par rule chup rehta hai,
     * `await` + setX par shikayat karta hai — halanke dono ek hi cheez hain).
     *
     * Is liye yahan disable justified hai; code mein koi cascading render
     * nahi hai.
     */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadBots(ctxUserId)
  }, [ctxUserId, loadBots])

  // Dropdown ko bahar click par band karo
  useEffect(() => {
    if (!openMenu) return
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpenMenu(null)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [openMenu])

  /* ── Derived ────────────────────────────── */

  const filteredBots = useMemo(() => {
    const query = search.trim().toLowerCase()
    return bots.filter((bot) => {
      if (statusFilter !== 'all' && bot.status !== statusFilter) return false
      if (!query) return true
      return (
        bot.bot_name.toLowerCase().includes(query) ||
        (bot.description ?? '').toLowerCase().includes(query)
      )
    })
  }, [bots, search, statusFilter])

  const stats = useMemo(
    () => ({
      total: bots.length,
      active: bots.filter((b) => b.status === 'active').length,
      conversations: bots.reduce((sum, b) => sum + (b.conversation_count || 0), 0),
      escalated: bots.reduce((sum, b) => sum + (b.escalated_count || 0), 0),
    }),
    [bots]
  )

  /* ── Actions ────────────────────────────── */

  const toggleSelect = (botId: string) =>
    setSelected((prev) => (prev.includes(botId) ? prev.filter((id) => id !== botId) : [...prev, botId]))

  const handleToggleStatus = async (bot: ChatbotInstance) => {
    setOpenMenu(null)
    setBusyBotId(bot.bot_id)
    const nextStatus: BotStatus = bot.status === 'active' ? 'paused' : 'active'
    try {
      const res = await chatbotApi.updateBot(bot.bot_id, { status: nextStatus })
      setBots((prev) => prev.map((b) => (b.bot_id === bot.bot_id ? res.data : b)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update chatbot')
    } finally {
      setBusyBotId(null)
    }
  }

  const handleDuplicate = async (bot: ChatbotInstance) => {
    setOpenMenu(null)
    setBusyBotId(bot.bot_id)
    try {
      const res = await chatbotApi.duplicateBot(bot.bot_id)
      setBots((prev) => [res.data, ...prev])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to duplicate chatbot')
    } finally {
      setBusyBotId(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    const botId = deleteTarget.bot_id
    setBusyBotId(botId)
    try {
      await chatbotApi.deleteBot(botId)
      setBots((prev) => prev.filter((b) => b.bot_id !== botId))
      setSelected((prev) => prev.filter((id) => id !== botId))
      setDeleteTarget(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete chatbot')
      setDeleteTarget(null)
    } finally {
      setBusyBotId(null)
    }
  }

  const handleBulkPause = async () => {
    setBulkBusy(true)
    try {
      await Promise.all(selected.map((id) => chatbotApi.updateBot(id, { status: 'paused' })))
      await loadBots(userId)
      setSelected([])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bulk pause failed')
    } finally {
      setBulkBusy(false)
    }
  }

  const handleBulkDelete = async () => {
    setBulkBusy(true)
    try {
      await Promise.all(selected.map((id) => chatbotApi.deleteBot(id)))
      setBots((prev) => prev.filter((b) => !selected.includes(b.bot_id)))
      setSelected([])
      setBulkDeleteOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bulk delete failed')
      setBulkDeleteOpen(false)
    } finally {
      setBulkBusy(false)
    }
  }

  /* ── Render ─────────────────────────────── */

  const isList = viewMode === 'list'

  return (
    <>
      <PageHeader title="My Bots" subtitle="Manage and monitor all your chatbot assistants">
        <Link href="/business/chatbot/new">
          <motion.span
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all cursor-pointer"
          >
            <IconPlus className="w-3.5 h-3.5" />
            Create New Chatbot
          </motion.span>
        </Link>
      </PageHeader>

      <div className="p-8">
        <ErrorBanner message={error} onRetry={() => userId && loadBots(userId)} />

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <StatCard label="Total Bots" value={stats.total} delay={0} />
          <StatCard label="Active" value={stats.active} accent="emerald" delay={0.05} />
          <StatCard label="Total Conversations" value={stats.conversations} delay={0.1} />
          <StatCard label="Escalated" value={stats.escalated} accent="red" delay={0.15} />
        </div>

        {/* Filters */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-5">
          {/* Search */}
          <div className="relative flex-1 min-w-0">
            <IconSearch className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8b877d]" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search bots by name or description…"
              className="w-full pl-10 pr-9 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d]"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8b877d] hover:text-[#14140f] transition-colors"
                title="Clear search"
              >
                <IconClose className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Status tabs */}
          <div className="flex items-center gap-1 p-1 rounded-xl border border-[#d5d1c6] bg-white shrink-0">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all ${
                  statusFilter === tab.id ? 'bg-black text-white' : 'text-[#8b877d] hover:text-[#14140f]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* View toggle */}
          <div className="flex items-center gap-1 p-1 rounded-xl border border-[#d5d1c6] bg-white shrink-0">
            {([
              { id: 'grid' as const, Icon: IconGrid, label: 'Grid view' },
              { id: 'list' as const, Icon: IconList, label: 'List view' },
            ]).map(({ id, Icon, label }) => (
              <button
                key={id}
                onClick={() => setViewMode(id)}
                title={label}
                className={`p-2 rounded-lg transition-all ${
                  viewMode === id ? 'bg-black text-white' : 'text-[#8b877d] hover:text-[#14140f]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>
        </div>

        {/* Bulk actions */}
        <AnimatePresence>
          {selected.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="flex items-center justify-between gap-4 rounded-xl bg-black px-5 py-3 mb-5"
            >
              <span className="text-xs font-bold text-white">{selected.length} selected</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleBulkPause}
                  disabled={bulkBusy}
                  className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-white/15 text-white hover:bg-white/25 transition-colors disabled:opacity-50"
                >
                  Pause
                </button>
                <button
                  onClick={() => setBulkDeleteOpen(true)}
                  disabled={bulkBusy}
                  className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-[#96203f] text-white hover:bg-[#96203f] transition-colors disabled:opacity-50"
                >
                  Delete
                </button>
                <button
                  onClick={() => setSelected([])}
                  className="p-1.5 text-white/70 hover:text-white transition-colors"
                  title="Clear selection"
                >
                  <IconClose className="w-3.5 h-3.5" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Bots */}
        {loading ? (
          <div className="flex items-center justify-center gap-2.5 py-20 text-xs font-semibold text-[#8b877d]">
            <Spinner />
            Loading chatbots…
          </div>
        ) : filteredBots.length === 0 ? (
          <EmptyState
            icon={IconChat}
            title={
              bots.length === 0
                ? 'No chatbots yet'
                : search
                ? 'No bots match your search'
                : `No ${statusFilter} bots`
            }
            description={
              bots.length === 0
                ? 'Create your first chatbot to start answering customer questions automatically.'
                : 'Try a different search term or switch to another status filter.'
            }
            action={
              bots.length === 0 ? (
                <Link href="/business/chatbot/new">
                  <span className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all cursor-pointer">
                    <IconPlus className="w-3.5 h-3.5" />
                    Create Your First Chatbot
                  </span>
                </Link>
              ) : (
                <button
                  onClick={() => {
                    setSearch('')
                    setStatusFilter('all')
                  }}
                  className="px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors"
                >
                  Clear filters
                </button>
              )
            }
          />
        ) : (
          <div
            className={
              isList ? 'flex flex-col gap-3' : 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4'
            }
          >
            {filteredBots.map((bot, idx) => {
              const isSelected = selected.includes(bot.bot_id)
              const isBusy = busyBotId === bot.bot_id

              return (
                <motion.div
                  key={bot.bot_id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(idx * 0.04, 0.3) }}
                  className={`relative rounded-xl border bg-white transition-all duration-200 ${
                    isSelected ? 'border-black' : 'border-[#d5d1c6] hover:border-[#0a0a0a]'
                  } ${isBusy ? 'opacity-60 pointer-events-none' : ''} ${
                    isList ? 'p-5 flex flex-col md:flex-row md:items-center gap-5' : 'p-6'
                  }`}
                >
                  {/* Header row */}
                  <div className={`flex items-start gap-3.5 ${isList ? 'md:flex-1 md:min-w-0' : 'mb-4'}`}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(bot.bot_id)}
                      className="mt-3.5 w-3.5 h-3.5 accent-black cursor-pointer shrink-0"
                      aria-label={`Select ${bot.bot_name}`}
                    />
                    <BotAvatar name={bot.bot_name} color={bot.primary_color} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-black text-[#14140f] truncate">{bot.bot_name}</h3>
                        <StatusBadge status={bot.status} />
                      </div>
                      <p className="text-[11px] text-[#8b877d] truncate">
                        {categoryName(bot.category)} · {bot.personality}
                      </p>
                    </div>
                  </div>

                  {/* Description — grid view only */}
                  {!isList && (
                    <p className="text-xs text-[#8b877d] leading-relaxed line-clamp-2 mb-4 min-h-[2rem]">
                      {bot.description || 'No description provided.'}
                    </p>
                  )}

                  {/* Quick stats */}
                  <div className={`flex items-center gap-4 ${isList ? 'shrink-0' : 'mb-4'}`}>
                    <div className="flex items-center gap-1.5 text-xs text-[#8b877d]" title="Conversations">
                      <IconChat className="w-3.5 h-3.5 text-[#8b877d]" />
                      <span className="font-bold text-[#14140f]">{bot.conversation_count}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-[#8b877d]" title="Documents">
                      <IconDoc className="w-3.5 h-3.5 text-[#8b877d]" />
                      <span className="font-bold text-[#14140f]">{bot.document_count}</span>
                    </div>
                    <span className="text-[11px] text-[#8b877d]">Created {formatDate(bot.created_at)}</span>
                  </div>

                  {/* Actions */}
                  <div className={`flex items-center gap-2 ${isList ? 'shrink-0' : 'pt-4 border-t border-[#e7e4dc]'}`}>
                    <Link href={`/business/chatbot/${bot.bot_id}`} className="flex-1 md:flex-none">
                      <span className="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-black text-white hover:bg-[#14140f] transition-colors cursor-pointer">
                        <IconSettings className="w-3.5 h-3.5" />
                        Manage
                      </span>
                    </Link>
                    <Link href={`/business/chatbot/${bot.bot_id}/training`} className="flex-1 md:flex-none">
                      <span className="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors cursor-pointer">
                        <IconBrain className="w-3.5 h-3.5" />
                        Train
                      </span>
                    </Link>
                    <Link
                      href={`/business/chatbot/conversations?bot=${bot.bot_id}`}
                      className="flex-1 md:flex-none"
                    >
                      <span className="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors cursor-pointer">
                        <IconChat className="w-3.5 h-3.5" />
                        Chats
                      </span>
                    </Link>

                    {/* More menu */}
                    <div className="relative" ref={openMenu === bot.bot_id ? menuRef : undefined}>
                      <button
                        onClick={() => setOpenMenu(openMenu === bot.bot_id ? null : bot.bot_id)}
                        className="p-2 rounded-lg border border-[#d5d1c6] text-[#8b877d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors"
                        title="More options"
                      >
                        <IconMore className="w-3.5 h-3.5" />
                      </button>

                      <AnimatePresence>
                        {openMenu === bot.bot_id && (
                          <motion.div
                            initial={{ opacity: 0, y: -4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4 }}
                            transition={{ duration: 0.12 }}
                            className="absolute right-0 bottom-full mb-2 w-44 rounded-xl border border-[#d5d1c6] bg-white py-1.5 z-30 shadow-lg"
                          >
                            <button
                              onClick={() => handleDuplicate(bot)}
                              className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-semibold text-[#56544d] hover:bg-[#fbfaf7] transition-colors"
                            >
                              <IconCopy className="w-3.5 h-3.5 text-[#8b877d]" />
                              Duplicate
                            </button>
                            <button
                              onClick={() => handleToggleStatus(bot)}
                              className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-semibold text-[#56544d] hover:bg-[#fbfaf7] transition-colors"
                            >
                              {bot.status === 'active' ? (
                                <>
                                  <IconPause className="w-3.5 h-3.5 text-[#8b877d]" />
                                  Pause
                                </>
                              ) : (
                                <>
                                  <IconPlay className="w-3.5 h-3.5 text-[#8b877d]" />
                                  Resume
                                </>
                              )}
                            </button>
                            <div className="my-1 border-t border-[#e7e4dc]" />
                            <button
                              onClick={() => {
                                setOpenMenu(null)
                                setDeleteTarget(bot)
                              }}
                              className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-semibold text-[#96203f] hover:bg-[#fbeaec] transition-colors"
                            >
                              <IconTrash className="w-3.5 h-3.5" />
                              Delete
                            </button>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        )}
      </div>

      <ConfirmModal
        open={!!deleteTarget}
        title={`Delete ${deleteTarget?.bot_name ?? 'chatbot'}?`}
        description="This permanently removes the chatbot, its conversations and its entire knowledge base. This cannot be undone."
        confirmLabel="Delete chatbot"
        busy={busyBotId === deleteTarget?.bot_id}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmModal
        open={bulkDeleteOpen}
        title={`Delete ${selected.length} chatbot${selected.length === 1 ? '' : 's'}?`}
        description="This permanently removes the selected chatbots, their conversations and their knowledge bases. This cannot be undone."
        confirmLabel="Delete all"
        busy={bulkBusy}
        onConfirm={handleBulkDelete}
        onCancel={() => setBulkDeleteOpen(false)}
      />
    </>
  )
}
