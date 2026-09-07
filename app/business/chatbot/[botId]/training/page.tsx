'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useActiveBrand } from '@/lib/useActiveBrand'
import { chatbotApi, ChatbotInstance, UploadedDocumentItem } from '@/lib/chatbotApi'
import {
  ConfirmModal,
  EmptyState,
  ErrorBanner,
  IconArrowLeft,
  IconBrain,
  IconClose,
  IconDoc,
  IconTrash,
  IconUpload,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
  formatBytes,
  formatDate,
  formatRelative,
  parseDate,
  sourceIcon,
} from '@/components/chatbot/shared'

type Tab = 'overview' | 'documents' | 'history'
type DocWithBot = UploadedDocumentItem & { botName: string; botColor: string }

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'documents', label: 'Documents' },
  { id: 'history', label: 'Upload History' },
]

const ALLOWED_EXT = ['.pdf', '.docx', '.txt']
const MAX_FILE_BYTES = 10 * 1024 * 1024

export default function TrainingPage() {
  const params = useParams<{ botId: string }>()
  const router = useRouter()
  const { userId: ctxUserId } = useActiveBrand()

  const selectedBotId = params.botId
  const isAll = selectedBotId === 'all'

  const [bots, setBots] = useState<ChatbotInstance[]>([])
  const [documents, setDocuments] = useState<DocWithBot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('overview')

  // Upload modal
  const [uploadOpen, setUploadOpen] = useState(false)
  const [modalBotId, setModalBotId] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadedCount, setUploadedCount] = useState(0)
  const [uploadNote, setUploadNote] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Destructive actions
  const [deleteDoc, setDeleteDoc] = useState<DocWithBot | null>(null)
  const [clearOpen, setClearOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const selectedBot = useMemo(
    () => bots.find((b) => b.bot_id === selectedBotId) ?? null,
    [bots, selectedBotId]
  )

  /* ── Data loading ───────────────────────── */

  const loadDocuments = useCallback(async (botList: ChatbotInstance[], botId: string) => {
    const targets = botId === 'all' ? botList : botList.filter((b) => b.bot_id === botId)

    const results = await Promise.all(
      targets.map(async (bot) => {
        try {
          const res = await chatbotApi.getDocuments(bot.bot_id)
          return (res.data ?? []).map((doc) => ({
            ...doc,
            botName: bot.bot_name,
            botColor: bot.primary_color,
          }))
        } catch {
          // Ek bot fail ho to baaki ki documents phir bhi dikhao
          return [] as DocWithBot[]
        }
      })
    )

    const flat = results.flat()
    flat.sort((a, b) => {
      const da = parseDate(a.uploaded_at)?.getTime() ?? 0
      const db = parseDate(b.uploaded_at)?.getTime() ?? 0
      return db - da
    })
    return flat
  }, [])

  const refresh = useCallback(
        async (uid: string) => {
      // NOTE: yahan pehla kaam `setError('')` tha — pehle await se PEHLE,
      // yani synchronously. Chunke ye function ek effect se bhi call hota
      // hai, wo mount par ek fazool cascading render deta tha (react-hooks
      // ka set-state-in-effect isi ko pakarta tha).
      //
      // Ab error KAAMYABI par saaf hota hai. Ye behaviour bhi behtar hai:
      // reload ke dauran purana error screen par rehta hai aur naya data aane
      // par hi hatta hai — beech mein screen khali nahi hoti.
      try {
        const botsRes = await chatbotApi.getMyBots(uid)
        const botList = botsRes.data ?? []
        setBots(botList)

        // botId invalid ho to All Bots par bhej do
        if (!isAll && !botList.some((b) => b.bot_id === selectedBotId)) {
          router.replace('/business/chatbot/all/training')
          return
        }

        setDocuments(await loadDocuments(botList, selectedBotId))
        setError('')
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load knowledge base')
      } finally {
        setLoading(false)
      }
    },
    [isAll, selectedBotId, loadDocuments, router]
  )

  // userId context se — auth guard DashboardShell mein hai.
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
    refresh(ctxUserId)
  }, [ctxUserId, refresh])

  /** Modal khulte waqt target bot set karo — "All Bots" par pehla bot default. */
  const openUploadModal = () => {
    setModalBotId(isAll ? bots[0]?.bot_id ?? '' : selectedBotId)
    setFiles([])
    setUploadedCount(0)
    setUploadNote('')
    setUploadOpen(true)
  }

  const reloadDocuments = async () => {
    setDocuments(await loadDocuments(bots, selectedBotId))
  }

  /* ── Derived stats ──────────────────────── */

  const stats = useMemo(() => {
    const totalChunks = documents.reduce((sum, d) => sum + (d.chunks_stored || 0), 0)
    const latest = documents.reduce<Date | null>((acc, d) => {
      const date = parseDate(d.uploaded_at)
      if (!date) return acc
      return !acc || date > acc ? date : acc
    }, null)
    return { totalDocuments: documents.length, totalChunks, latest }
  }, [documents])

  const historyGroups = useMemo(() => {
    const groups = new Map<string, DocWithBot[]>()
    documents.forEach((doc) => {
      const date = parseDate(doc.uploaded_at)
      const key = date ? date.toDateString() : 'Unknown date'
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(doc)
    })
    return Array.from(groups.entries())
  }, [documents])

  /* ── Upload ─────────────────────────────── */

  const addFiles = (incoming: FileList | File[]) => {
    const accepted: File[] = []
    const rejected: string[] = []

    Array.from(incoming).forEach((file) => {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (!ALLOWED_EXT.includes(ext)) rejected.push(`${file.name} (unsupported type)`)
      else if (file.size > MAX_FILE_BYTES) rejected.push(`${file.name} (over 10MB)`)
      else accepted.push(file)
    })

    setUploadNote(rejected.length ? `Skipped: ${rejected.join(', ')}` : '')
    if (accepted.length) {
      setFiles((prev) => {
        const seen = new Set(prev.map((f) => `${f.name}:${f.size}`))
        return [...prev, ...accepted.filter((f) => !seen.has(`${f.name}:${f.size}`))]
      })
    }
  }

  const closeUploadModal = () => {
    if (uploading) return
    setUploadOpen(false)
    setFiles([])
    setUploadedCount(0)
    setUploadNote('')
  }

  const handleUpload = async () => {
    if (!modalBotId || files.length === 0) return

    setUploading(true)
    setUploadedCount(0)
    setUploadNote('')
    const failures: string[] = []

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      setUploadNote(`Processing ${file.name}…`)
      try {
        await chatbotApi.uploadDocument(modalBotId, file)
      } catch (e) {
        failures.push(`${file.name}: ${e instanceof Error ? e.message : 'failed'}`)
      }
      setUploadedCount(i + 1)
    }

    await reloadDocuments()
    setUploading(false)

    if (failures.length) {
      setUploadNote(`Some uploads failed — ${failures.join('; ')}`)
      setFiles([])
    } else {
      setUploadOpen(false)
      setFiles([])
      setUploadedCount(0)
      setUploadNote('')
    }
  }

  /* ── Delete ─────────────────────────────── */

  const handleDeleteDocument = async () => {
    if (!deleteDoc) return
    setBusy(true)
    try {
      const res = await chatbotApi.deleteDocument(deleteDoc.id)
      setDocuments((prev) => prev.filter((d) => d.id !== deleteDoc.id))
      if (res.legacy_vectors) {
        setError(
          `${deleteDoc.filename} was removed from the list, but it was uploaded before per-document tracking — its vectors stay in the index until you clear the knowledge base.`
        )
      }
      setDeleteDoc(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document')
      setDeleteDoc(null)
    } finally {
      setBusy(false)
    }
  }

  const handleClearKnowledgeBase = async () => {
    if (isAll) return
    setBusy(true)
    try {
      await chatbotApi.clearKnowledgeBase(selectedBotId)
      setDocuments([])
      setClearOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to clear knowledge base')
      setClearOpen(false)
    } finally {
      setBusy(false)
    }
  }

  /* ── Render ─────────────────────────────── */

  const uploadProgress = files.length ? Math.round((uploadedCount / files.length) * 100) : 0

  const documentCard = (doc: DocWithBot) => {
    const Icon = sourceIcon(doc.source_type)
    return (
      <motion.div
        key={doc.id}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-4 rounded-xl border border-[#d5d1c6] bg-white p-5 hover:border-[#0a0a0a] transition-colors"
      >
        <div className="w-10 h-10 rounded-xl bg-[#fbfaf7] border border-[#e7e4dc] flex items-center justify-center text-[#8b877d] shrink-0">
          <Icon className="w-4 h-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-black text-[#14140f] truncate mb-1">{doc.filename}</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#8b877d]">
            <span className="uppercase font-bold">{doc.file_type || doc.source_type}</span>
            <span>{formatBytes(doc.file_size)}</span>
            <span>{doc.chunks_stored} chunks</span>
            <span>{formatDate(doc.uploaded_at)}</span>
            {isAll && <span className="font-semibold text-[#8b877d]">{doc.botName}</span>}
          </div>
        </div>
        <button
          onClick={() => setDeleteDoc(doc)}
          className="p-2 rounded-lg border border-[#d5d1c6] text-[#8b877d] hover:border-[#e6c3c8] hover:text-[#96203f] transition-colors shrink-0"
          title={`Delete ${doc.filename}`}
        >
          <IconTrash className="w-3.5 h-3.5" />
        </button>
      </motion.div>
    )
  }

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        subtitle={
          isAll ? 'Documents across all your chatbots' : `Training data for ${selectedBot?.bot_name ?? 'this bot'}`
        }
      >
        <Link href="/business/chatbot">
          <span className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors cursor-pointer">
            <IconArrowLeft className="w-3.5 h-3.5" />
            My Bots
          </span>
        </Link>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={openUploadModal}
          disabled={bots.length === 0}
          className="flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all disabled:opacity-50"
        >
          <IconUpload className="w-3.5 h-3.5" />
          Upload Documents
        </motion.button>
      </PageHeader>

      <div className="p-8">
        <ErrorBanner message={error} />

        {/* Bot selector */}
        {bots.length > 0 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-5">
            <button
              onClick={() => router.push('/business/chatbot/all/training')}
              className={`px-4 py-2 text-xs font-bold rounded-lg border whitespace-nowrap transition-all ${
                isAll ? 'bg-black text-white border-black' : 'bg-white text-[#56544d] border-[#d5d1c6] hover:border-[#0a0a0a]'
              }`}
            >
              All Bots
            </button>
            {bots.map((bot) => (
              <button
                key={bot.bot_id}
                onClick={() => router.push(`/business/chatbot/${bot.bot_id}/training`)}
                className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border whitespace-nowrap transition-all ${
                  selectedBotId === bot.bot_id
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
        )}

        {/* Tabs */}
        <div className="flex items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-1 p-1 rounded-xl border border-[#d5d1c6] bg-white w-fit">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-4 py-2 text-xs font-bold rounded-lg transition-all ${
                  tab === t.id ? 'bg-black text-white' : 'text-[#8b877d] hover:text-[#14140f]'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {!isAll && documents.length > 0 && (
            <button
              onClick={() => setClearOpen(true)}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#e6c3c8] text-[#96203f] hover:bg-[#fbeaec] transition-colors"
            >
              <IconTrash className="w-3.5 h-3.5" />
              Clear Knowledge Base
            </button>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2.5 py-20 text-xs font-semibold text-[#8b877d]">
            <Spinner />
            Loading knowledge base…
          </div>
        ) : bots.length === 0 ? (
          <EmptyState
            icon={IconBrain}
            title="No chatbots yet"
            description="Create a chatbot first, then upload documents to build its knowledge base."
            action={
              <Link href="/business/chatbot/new">
                <span className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all cursor-pointer">
                  Create Chatbot
                </span>
              </Link>
            }
          />
        ) : (
          <>
            {/* ── Overview ── */}
            {tab === 'overview' && (
              <div>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                  <StatCard label="Total Documents" value={stats.totalDocuments} delay={0} />
                  <StatCard label="Total Chunks" value={stats.totalChunks} delay={0.05} />
                  <StatCard
                    label="Last Updated"
                    value={stats.latest ? formatRelative(stats.latest.toISOString()) : '—'}
                    delay={0.1}
                  />
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15 }}
                    className="rounded-xl border border-[#d5d1c6] bg-white p-5"
                  >
                    <div className="mb-2">
                      {isAll ? (
                        <p className="text-3xl font-black text-[#14140f] leading-none">{bots.length}</p>
                      ) : selectedBot ? (
                        <StatusBadge status={selectedBot.status} />
                      ) : (
                        <p className="text-3xl font-black text-[#14140f] leading-none">—</p>
                      )}
                    </div>
                    <p className="text-xs font-medium text-[#8b877d]">
                      {isAll ? 'Chatbots' : 'Bot Status'}
                    </p>
                  </motion.div>
                </div>

                {documents.length === 0 ? (
                  <EmptyState
                    icon={IconDoc}
                    title="Knowledge base is empty"
                    description="Upload PDFs, Word documents or text files so your bot can answer questions from your own content."
                    action={
                      <button
                        onClick={openUploadModal}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all"
                      >
                        <IconUpload className="w-3.5 h-3.5" />
                        Upload Documents
                      </button>
                    }
                  />
                ) : (
                  <div>
                    <p className="text-xs font-bold text-[#14140f] mb-3">Recent Uploads</p>
                    <div className="space-y-3">{documents.slice(0, 5).map(documentCard)}</div>
                    {documents.length > 5 && (
                      <button
                        onClick={() => setTab('documents')}
                        className="mt-4 text-xs font-bold text-[#14140f] hover:underline"
                      >
                        View all {documents.length} documents →
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Documents ── */}
            {tab === 'documents' &&
              (documents.length === 0 ? (
                <EmptyState
                  icon={IconDoc}
                  title="No documents"
                  description="Nothing has been uploaded to this knowledge base yet."
                  action={
                    <button
                      onClick={openUploadModal}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all"
                    >
                      <IconUpload className="w-3.5 h-3.5" />
                      Upload Documents
                    </button>
                  }
                />
              ) : (
                <div className="space-y-3">{documents.map(documentCard)}</div>
              ))}

            {/* ── Upload History ── */}
            {tab === 'history' &&
              (historyGroups.length === 0 ? (
                <EmptyState
                  icon={IconUpload}
                  title="No upload history"
                  description="Uploads will be listed here grouped by the day they were processed."
                />
              ) : (
                <div className="space-y-7">
                  {historyGroups.map(([day, docs]) => (
                    <div key={day}>
                      <div className="flex items-center gap-3 mb-3">
                        <p className="text-xs font-black text-[#14140f]">
                          {day === 'Unknown date'
                            ? day
                            : new Date(day).toLocaleDateString(undefined, {
                                weekday: 'long',
                                day: 'numeric',
                                month: 'long',
                                year: 'numeric',
                              })}
                        </p>
                        <span className="text-[11px] text-[#8b877d]">
                          {docs.length} upload{docs.length === 1 ? '' : 's'} ·{' '}
                          {docs.reduce((s, d) => s + (d.chunks_stored || 0), 0)} chunks
                        </span>
                      </div>
                      <div className="space-y-3">{docs.map(documentCard)}</div>
                    </div>
                  ))}
                </div>
              ))}
          </>
        )}
      </div>

      {/* ── Upload Modal ── */}
      <AnimatePresence>
        {uploadOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
            onClick={closeUploadModal}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 10 }}
              transition={{ duration: 0.15 }}
              className="w-full max-w-lg max-h-[88vh] overflow-y-auto rounded-xl bg-white border border-[#d5d1c6]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#e7e4dc] sticky top-0 bg-white">
                <h3 className="text-sm font-black text-[#14140f]">Upload Documents</h3>
                <button
                  onClick={closeUploadModal}
                  disabled={uploading}
                  className="text-[#8b877d] hover:text-[#14140f] transition-colors disabled:opacity-40"
                  title="Close"
                >
                  <IconClose className="w-4 h-4" />
                </button>
              </div>

              <div className="p-6">
                {/* Bot selector */}
                <div className="mb-5">
                  <label className="block text-xs font-bold text-[#14140f] mb-2">Target Chatbot</label>
                  <select
                    value={modalBotId}
                    onChange={(e) => setModalBotId(e.target.value)}
                    disabled={uploading}
                    className="w-full px-4 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] bg-white disabled:opacity-50"
                  >
                    {bots.map((bot) => (
                      <option key={bot.bot_id} value={bot.bot_id}>
                        {bot.bot_name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Drop area */}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files) addFiles(e.target.files)
                    e.target.value = ''
                  }}
                />
                <div
                  onClick={() => !uploading && fileInputRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault()
                    if (!uploading) setDragging(true)
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault()
                    setDragging(false)
                    if (!uploading && e.dataTransfer.files) addFiles(e.dataTransfer.files)
                  }}
                  className={`rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200 ${
                    uploading
                      ? 'border-[#d5d1c6] opacity-60'
                      : dragging
                      ? 'border-black bg-[#fbfaf7] cursor-pointer'
                      : 'border-[#d5d1c6] hover:border-[#0a0a0a] cursor-pointer'
                  }`}
                >
                  <div className="w-10 h-10 rounded-xl bg-[#fbfaf7] border border-[#e7e4dc] flex items-center justify-center mx-auto mb-3 text-[#8b877d]">
                    <IconUpload className="w-4 h-4" />
                  </div>
                  <p className="text-xs font-bold text-[#14140f] mb-1">
                    Drag &amp; drop files, or click to browse
                  </p>
                  <p className="text-[11px] text-[#8b877d]">PDF, DOCX or TXT · max 10MB each</p>
                </div>

                {/* Selected files */}
                {files.length > 0 && (
                  <div className="mt-5">
                    <p className="text-xs font-bold text-[#14140f] mb-3">Selected Files ({files.length})</p>
                    <div className="space-y-2">
                      {files.map((file, i) => (
                        <div
                          key={`${file.name}-${i}`}
                          className="flex items-center gap-3 rounded-xl border border-[#d5d1c6] px-4 py-2.5"
                        >
                          <IconDoc className="w-3.5 h-3.5 text-[#8b877d] shrink-0" />
                          <span className="text-xs font-semibold text-[#14140f] truncate flex-1">
                            {file.name}
                          </span>
                          <span className="text-[11px] text-[#8b877d] shrink-0">
                            {formatBytes(file.size)}
                          </span>
                          {!uploading && (
                            <button
                              onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                              className="text-[#8b877d] hover:text-[#96203f] transition-colors shrink-0"
                              title="Remove file"
                            >
                              <IconClose className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Progress */}
                {uploading && (
                  <div className="mt-5">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-[#8b877d] mb-2">
                      <span>
                        {uploadedCount} of {files.length} processed
                      </span>
                      <span>{uploadProgress}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-[#e7e4dc] overflow-hidden">
                      <motion.div
                        className="h-full bg-black rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${uploadProgress}%` }}
                        transition={{ duration: 0.3 }}
                      />
                    </div>
                  </div>
                )}

                {uploadNote && (
                  <p className="mt-4 text-[11px] font-semibold text-[#56544d] leading-relaxed">
                    {uploadNote}
                  </p>
                )}

                <div className="flex items-center justify-end gap-2 mt-6 pt-5 border-t border-[#e7e4dc]">
                  <button
                    onClick={closeUploadModal}
                    disabled={uploading}
                    className="px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleUpload}
                    disabled={uploading || files.length === 0 || !modalBotId}
                    className="flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all disabled:opacity-50"
                  >
                    {uploading ? (
                      <>
                        <Spinner className="w-3.5 h-3.5" />
                        Processing…
                      </>
                    ) : (
                      <>
                        <IconUpload className="w-3.5 h-3.5" />
                        Upload {files.length > 0 && `(${files.length})`}
                      </>
                    )}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <ConfirmModal
        open={!!deleteDoc}
        title="Delete this document?"
        description={`"${deleteDoc?.filename ?? ''}" and its ${deleteDoc?.chunks_stored ?? 0} indexed chunks will be removed. Your bot will no longer answer from this content.`}
        confirmLabel="Delete document"
        busy={busy}
        onConfirm={handleDeleteDocument}
        onCancel={() => setDeleteDoc(null)}
      />

      <ConfirmModal
        open={clearOpen}
        title="Clear the entire knowledge base?"
        description={`All ${documents.length} document(s) for ${selectedBot?.bot_name ?? 'this bot'} will be deleted and its search index wiped. This cannot be undone.`}
        confirmLabel="Clear knowledge base"
        busy={busy}
        onConfirm={handleClearKnowledgeBase}
        onCancel={() => setClearOpen(false)}
      />
    </>
  )
}
