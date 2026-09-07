'use client'

import { useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { useActiveBrand } from '@/lib/useActiveBrand'
import { chatbotApi, BotCategory, BotTone, FaqPair } from '@/lib/chatbotApi'
import {
  CATEGORIES,
  COLOR_PRESETS,
  TONES,
  TRAITS,
  IconArrowLeft,
  IconArrowRight,
  IconCheck,
  IconClose,
  IconDoc,
  IconFaq,
  IconPlus,
  IconText,
  IconUpload,
  PageHeader,
  Spinner,
  formatBytes,
  toneName,
} from '@/components/chatbot/shared'

const STEPS = [
  { n: 1, label: 'Basic Info' },
  { n: 2, label: 'Personality' },
  { n: 3, label: 'Knowledge' },
  { n: 4, label: 'Customize' },
]

const KNOWLEDGE_TABS = [
  { id: 'upload' as const, label: 'Upload Files', Icon: IconUpload },
  { id: 'text' as const, label: 'Text Input', Icon: IconText },
  { id: 'faq' as const, label: 'FAQ Builder', Icon: IconFaq },
]

const ALLOWED_EXT = ['.pdf', '.docx', '.txt']
const MAX_FILE_BYTES = 10 * 1024 * 1024

type KnowledgeTab = (typeof KNOWLEDGE_TABS)[number]['id']

export default function NewChatbotPage() {
  const router = useRouter()

  const { activeBrandId, userId: ctxUserId, user: ctxUser } = useActiveBrand()
    // Dono SEEDHA context se — pehle inhein ek effect sync karta tha jiska aur
  // koi kaam nahi tha. Derived value ke liye state rakhna sirf ek extra
  // render aur do sources of truth deta hai.
  const userId = ctxUserId
  const ownerEmail = ctxUser?.email ?? null
  const [step, setStep] = useState(1)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [progressNote, setProgressNote] = useState('')
  const [sourcesDone, setSourcesDone] = useState(0)
  const [sourcesTotal, setSourcesTotal] = useState(0)

  // Step 1
  const [botName, setBotName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState<BotCategory>('support')

  // Step 2
  const [tone, setTone] = useState<BotTone>('professional')
  const [traits, setTraits] = useState<string[]>(['Helpful'])
  const [customPrompt, setCustomPrompt] = useState('')

  // Step 3
  const [knowledgeTab, setKnowledgeTab] = useState<KnowledgeTab>('upload')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [trainingText, setTrainingText] = useState('')
  const [faqs, setFaqs] = useState<FaqPair[]>([{ question: '', answer: '' }])
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Step 4
  const [displayName, setDisplayName] = useState('')
  const [welcomeMessage, setWelcomeMessage] = useState('Hello! How can I help you today?')
  const [color, setColor] = useState(COLOR_PRESETS[0])

  

  /* ── File handling ──────────────────────── */

  const addFiles = (incoming: FileList | File[]) => {
    const accepted: File[] = []
    const rejected: string[] = []

    Array.from(incoming).forEach((file) => {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (!ALLOWED_EXT.includes(ext)) {
        rejected.push(`${file.name} (unsupported type)`)
        return
      }
      if (file.size > MAX_FILE_BYTES) {
        rejected.push(`${file.name} (over 10MB)`)
        return
      }
      accepted.push(file)
    })

    setError(rejected.length ? `Skipped: ${rejected.join(', ')}` : '')
    if (accepted.length) {
      setFiles((prev) => {
        const seen = new Set(prev.map((f) => `${f.name}:${f.size}`))
        return [...prev, ...accepted.filter((f) => !seen.has(`${f.name}:${f.size}`))]
      })
    }
  }

  const removeFile = (index: number) => setFiles((prev) => prev.filter((_, i) => i !== index))

  /* ── FAQ handling ───────────────────────── */

  const updateFaq = (index: number, field: keyof FaqPair, value: string) =>
    setFaqs((prev) => prev.map((faq, i) => (i === index ? { ...faq, [field]: value } : faq)))

  const removeFaq = (index: number) => setFaqs((prev) => prev.filter((_, i) => i !== index))

  /* ── Validation & navigation ────────────── */

  const validateStep = (target: number): boolean => {
    if (target === 1) {
      if (!botName.trim()) {
        setError('Bot name is required')
        return false
      }
    }
    if (target === 2) {
      if (traits.length === 0) {
        setError('Select at least one personality trait')
        return false
      }
    }
    if (target === 3) {
      if (knowledgeTab === 'faq') {
        const complete = faqs.filter((f) => f.question.trim() && f.answer.trim())
        const partial = faqs.filter(
          (f) => (f.question.trim() && !f.answer.trim()) || (!f.question.trim() && f.answer.trim())
        )
        if (partial.length && !complete.length) {
          setError('Each FAQ needs both a question and an answer')
          return false
        }
      }
    }
    if (target === 4) {
      if (!welcomeMessage.trim()) {
        setError('Welcome message cannot be empty')
        return false
      }
    }
    setError('')
    return true
  }

  const goNext = () => {
    if (!validateStep(step)) return
    setStep((s) => Math.min(s + 1, STEPS.length))
  }

  const goPrev = () => {
    setError('')
    setStep((s) => Math.max(s - 1, 1))
  }

  /* ── Create ─────────────────────────────── */

  const completeFaqs = faqs.filter((f) => f.question.trim() && f.answer.trim())

  const handleCreate = async () => {
    for (let i = 1; i <= STEPS.length; i++) {
      if (!validateStep(i)) {
        setStep(i)
        return
      }
    }

    setCreating(true)
    setError('')
    const warnings: string[] = []

    // Progress asli kaam se aata hai — har source process hone par barhta hai,
    // koi simulated timer nahi.
    const totalSources = files.length + (trainingText.trim() ? 1 : 0) + (completeFaqs.length ? 1 : 0)
    setSourcesTotal(totalSources)
    setSourcesDone(0)

    try {
      setProgressNote('Creating chatbot…')
      const res = await chatbotApi.createChatbot({
        user_id: userId,
        bot_name: displayName.trim() || botName.trim(),
        description: description.trim() || null,
        category,
        tone,
        personality_traits: traits.map((t) => t.toLowerCase()),
        custom_prompt: customPrompt.trim() || null,
        welcome_message: welcomeMessage.trim(),
        primary_color: color,
        owner_email: ownerEmail,
        // Active brand ka link create par hi lag jata hai — koi extra UI nahi.
        brand_profile_id: activeBrandId,
        status: 'active',
      })

      const botId = res.data.bot_id

      // Knowledge base bot banne ke BAAD process hoti hai — koi ek source fail ho
      // jaye to bhi bot bacha rehta hai, sirf warning dikhti hai.
      for (const file of files) {
        setProgressNote(`Processing ${file.name}…`)
        try {
          await chatbotApi.uploadDocument(botId, file)
        } catch (e) {
          warnings.push(`${file.name}: ${e instanceof Error ? e.message : 'upload failed'}`)
        }
        setSourcesDone((n) => n + 1)
      }

      if (trainingText.trim()) {
        setProgressNote('Processing pasted text…')
        try {
          await chatbotApi.uploadText(botId, trainingText.trim(), 'Pasted text')
        } catch (e) {
          warnings.push(`Text: ${e instanceof Error ? e.message : 'failed'}`)
        }
        setSourcesDone((n) => n + 1)
      }

      if (completeFaqs.length) {
        setProgressNote('Processing FAQs…')
        try {
          await chatbotApi.uploadFaq(botId, completeFaqs)
        } catch (e) {
          warnings.push(`FAQ: ${e instanceof Error ? e.message : 'failed'}`)
        }
        setSourcesDone((n) => n + 1)
      }

      if (warnings.length) {
        setCreating(false)
        setProgressNote('')
        setError(
          `Chatbot created, but some knowledge sources failed — ${warnings.join('; ')}. You can retry them from the Knowledge Base page.`
        )
        // Bot ban chuka hai, isliye user ko uske training page par bhejo.
        setTimeout(() => router.push(`/business/chatbot/${botId}/training`), 2500)
        return
      }

      router.push(`/business/chatbot/${botId}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create chatbot')
      setCreating(false)
      setProgressNote('')
    }
  }

  const previewName = displayName.trim() || botName.trim() || 'Assistant'
  const selectedTone = TONES.find((t) => t.id === tone) ?? TONES[0]
  const knowledgeSummary = [
    files.length ? `${files.length} file${files.length === 1 ? '' : 's'}` : null,
    trainingText.trim() ? 'pasted text' : null,
    completeFaqs.length ? `${completeFaqs.length} FAQ${completeFaqs.length === 1 ? '' : 's'}` : null,
  ].filter(Boolean)

  return (
    <>
      <PageHeader title="Create New Chatbot" subtitle="Build your intelligent assistant in four steps">
        <button
          onClick={() => router.push('/business/chatbot')}
          className="px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors"
        >
          Cancel
        </button>
      </PageHeader>

      <div className="p-8 max-w-5xl">
        {/* Step indicator */}
        <div className="flex items-center mb-8">
          {STEPS.map((s, i) => {
            const done = step > s.n
            const active = step === s.n
            return (
              <div key={s.n} className="flex items-center flex-1 last:flex-none">
                <div className="flex flex-col items-center gap-2 shrink-0">
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-black border transition-all duration-300 ${
                      done
                        ? 'bg-black text-white border-black'
                        : active
                        ? 'bg-white text-black border-black'
                        : 'bg-white text-[#c9c5bb] border-[#d5d1c6]'
                    }`}
                  >
                    {done ? <IconCheck className="w-4 h-4" /> : s.n}
                  </div>
                  <span
                    className={`text-[11px] font-bold whitespace-nowrap ${
                      active || done ? 'text-[#14140f]' : 'text-[#c9c5bb]'
                    }`}
                  >
                    {s.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className="flex-1 h-[2px] mx-3 -mt-6 bg-[#d5d1c6] overflow-hidden rounded-full">
                    <motion.div
                      className="h-full bg-black"
                      initial={{ width: 0 }}
                      animate={{ width: step > s.n ? '100%' : '0%' }}
                      transition={{ duration: 0.35 }}
                    />
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="rounded-xl border border-[#d5d1c6] bg-white p-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.2 }}
            >
              {/* ── Step 1 ── */}
              {step === 1 && (
                <div>
                  <h2 className="text-lg font-black text-[#14140f] mb-1">Basic Information</h2>
                  <p className="text-xs text-[#8b877d] mb-7">Start with the fundamentals of your chatbot</p>

                  <div className="mb-5">
                    <label className="block text-xs font-bold text-[#14140f] mb-2">
                      Bot Name <span className="text-[#96203f]">*</span>
                    </label>
                    <input
                      type="text"
                      value={botName}
                      onChange={(e) => setBotName(e.target.value)}
                      placeholder="e.g. Support Assistant, Sales Helper"
                      className="w-full px-4 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d]"
                    />
                    <p className="text-[11px] text-[#8b877d] mt-1.5">
                      Give your bot a unique, descriptive name
                    </p>
                  </div>

                  <div className="mb-6">
                    <label className="block text-xs font-bold text-[#14140f] mb-2">Description</label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      placeholder="What will this bot do? Describe its purpose…"
                      className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] resize-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-[#14140f] mb-3">Category</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {CATEGORIES.map((cat) => (
                        <button
                          key={cat.id}
                          onClick={() => setCategory(cat.id)}
                          className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                            category === cat.id
                              ? 'border-black bg-[#fbfaf7]'
                              : 'border-[#d5d1c6] hover:border-[#0a0a0a]'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-black text-[#14140f]">{cat.name}</span>
                            {category === cat.id && <IconCheck className="w-3.5 h-3.5 text-black" />}
                          </div>
                          <p className="text-[11px] text-[#8b877d] leading-relaxed">{cat.description}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── Step 2 ── */}
              {step === 2 && (
                <div>
                  <h2 className="text-lg font-black text-[#14140f] mb-1">Personality &amp; Tone</h2>
                  <p className="text-xs text-[#8b877d] mb-7">Define how your bot should communicate</p>

                  <div className="mb-6">
                    <label className="block text-xs font-bold text-[#14140f] mb-3">Communication Tone</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {TONES.map((t) => (
                        <button
                          key={t.id}
                          onClick={() => setTone(t.id)}
                          className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                            tone === t.id ? 'border-black bg-[#fbfaf7]' : 'border-[#d5d1c6] hover:border-[#0a0a0a]'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-black text-[#14140f]">{t.name}</span>
                            {tone === t.id && <IconCheck className="w-3.5 h-3.5 text-black" />}
                          </div>
                          <p className="text-[11px] text-[#8b877d]">{t.description}</p>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mb-6">
                    <label className="block text-xs font-bold text-[#14140f] mb-3">
                      Personality Traits <span className="font-medium text-[#8b877d]">(select multiple)</span>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {TRAITS.map((trait) => {
                        const on = traits.includes(trait)
                        return (
                          <button
                            key={trait}
                            onClick={() =>
                              setTraits((prev) =>
                                prev.includes(trait) ? prev.filter((t) => t !== trait) : [...prev, trait]
                              )
                            }
                            className={`px-3.5 py-2 text-xs font-bold rounded-full border transition-all duration-200 ${
                              on
                                ? 'bg-black text-white border-black'
                                : 'bg-white text-[#56544d] border-[#d5d1c6] hover:border-[#0a0a0a]'
                            }`}
                          >
                            {trait}
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <div className="mb-6">
                    <label className="block text-xs font-bold text-[#14140f] mb-2">
                      Custom Instructions <span className="font-medium text-[#8b877d]">(optional)</span>
                    </label>
                    <textarea
                      value={customPrompt}
                      onChange={(e) => setCustomPrompt(e.target.value)}
                      rows={4}
                      placeholder="Add specific instructions for your bot's behaviour — e.g. always mention free returns within 30 days."
                      className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] resize-none"
                    />
                  </div>

                  {/* Live preview */}
                  <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] p-5">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d] mb-3">
                      Live Preview
                    </p>
                    <div className="flex items-start gap-3">
                      <div
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-black text-white shrink-0"
                        style={{ backgroundColor: color }}
                      >
                        {previewName.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <div className="rounded-xl rounded-tl-sm bg-white border border-[#d5d1c6] px-4 py-3 mb-2">
                          <p className="text-xs text-[#14140f] leading-relaxed">{selectedTone.sample}</p>
                        </div>
                        <p className="text-[11px] text-[#8b877d]">
                          {previewName} · {selectedTone.name}
                          {traits.length > 0 && ` · ${traits.join(', ')}`}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Step 3 ── */}
              {step === 3 && (
                <div>
                  <h2 className="text-lg font-black text-[#14140f] mb-1">Knowledge Base</h2>
                  <p className="text-xs text-[#8b877d] mb-7">
                    Everything you add here is processed and indexed after the bot is created
                  </p>

                  <div className="flex items-center gap-1 p-1 rounded-xl border border-[#d5d1c6] bg-white w-fit mb-6">
                    {KNOWLEDGE_TABS.map(({ id, label, Icon }) => (
                      <button
                        key={id}
                        onClick={() => setKnowledgeTab(id)}
                        className={`flex items-center gap-2 px-3.5 py-2 text-xs font-bold rounded-lg transition-all ${
                          knowledgeTab === id ? 'bg-black text-white' : 'text-[#8b877d] hover:text-[#14140f]'
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                        {label}
                      </button>
                    ))}
                  </div>

                  {knowledgeTab === 'upload' && (
                    <div>
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
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setDragging(true)
                        }}
                        onDragLeave={() => setDragging(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setDragging(false)
                          if (e.dataTransfer.files) addFiles(e.dataTransfer.files)
                        }}
                        className={`rounded-xl border-2 border-dashed p-10 text-center cursor-pointer transition-all duration-200 ${
                          dragging ? 'border-black bg-[#fbfaf7]' : 'border-[#d5d1c6] hover:border-[#0a0a0a]'
                        }`}
                      >
                        <div className="w-11 h-11 rounded-xl bg-[#fbfaf7] border border-[#e7e4dc] flex items-center justify-center mx-auto mb-3 text-[#8b877d]">
                          <IconUpload className="w-5 h-5" />
                        </div>
                        <p className="text-xs font-bold text-[#14140f] mb-1">
                          Drag &amp; drop files, or click to browse
                        </p>
                        <p className="text-[11px] text-[#8b877d]">PDF, DOCX or TXT · max 10MB each</p>
                      </div>

                      {files.length > 0 && (
                        <div className="mt-5">
                          <p className="text-xs font-bold text-[#14140f] mb-3">
                            Selected Files ({files.length})
                          </p>
                          <div className="space-y-2">
                            {files.map((file, i) => (
                              <div
                                key={`${file.name}-${i}`}
                                className="flex items-center gap-3 rounded-xl border border-[#d5d1c6] px-4 py-3"
                              >
                                <IconDoc className="w-4 h-4 text-[#8b877d] shrink-0" />
                                <span className="text-xs font-semibold text-[#14140f] truncate flex-1">
                                  {file.name}
                                </span>
                                <span className="text-[11px] text-[#8b877d] shrink-0">
                                  {formatBytes(file.size)}
                                </span>
                                <button
                                  onClick={() => removeFile(i)}
                                  className="text-[#8b877d] hover:text-[#96203f] transition-colors shrink-0"
                                  title="Remove file"
                                >
                                  <IconClose className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {knowledgeTab === 'text' && (
                    <div>
                      <label className="block text-xs font-bold text-[#14140f] mb-2">Training Text</label>
                      <textarea
                        value={trainingText}
                        onChange={(e) => setTrainingText(e.target.value)}
                        rows={12}
                        placeholder="Paste your product info, policies, shipping details, or anything else the bot should know…"
                        className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] resize-none leading-relaxed"
                      />
                      <p className="text-[11px] text-[#8b877d] mt-1.5">
                        {trainingText.trim().split(/\s+/).filter(Boolean).length} words
                      </p>
                    </div>
                  )}

                  {knowledgeTab === 'faq' && (
                    <div>
                      <div className="space-y-3 mb-4">
                        {faqs.map((faq, i) => (
                          <div key={i} className="rounded-xl border border-[#d5d1c6] p-4">
                            <div className="flex items-center justify-between mb-2.5">
                              <span className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d]">
                                FAQ {i + 1}
                              </span>
                              {faqs.length > 1 && (
                                <button
                                  onClick={() => removeFaq(i)}
                                  className="text-[#8b877d] hover:text-[#96203f] transition-colors"
                                  title="Remove FAQ"
                                >
                                  <IconClose className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                            <input
                              type="text"
                              value={faq.question}
                              onChange={(e) => updateFaq(i, 'question', e.target.value)}
                              placeholder="Question — e.g. How long does delivery take?"
                              className="w-full px-3.5 py-2.5 text-xs rounded-lg border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] mb-2"
                            />
                            <textarea
                              value={faq.answer}
                              onChange={(e) => updateFaq(i, 'answer', e.target.value)}
                              rows={2}
                              placeholder="Answer — e.g. Standard delivery takes 3–5 working days."
                              className="w-full px-3.5 py-2.5 text-xs rounded-lg border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] resize-none"
                            />
                          </div>
                        ))}
                      </div>
                      <button
                        onClick={() => setFaqs((prev) => [...prev, { question: '', answer: '' }])}
                        className="flex items-center gap-2 px-4 py-2.5 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors"
                      >
                        <IconPlus className="w-3.5 h-3.5" />
                        Add FAQ
                      </button>
                    </div>
                  )}

                  {knowledgeSummary.length > 0 && (
                    <p className="text-[11px] text-[#8b877d] mt-6 pt-5 border-t border-[#e7e4dc]">
                      Ready to process: {knowledgeSummary.join(' · ')}
                    </p>
                  )}
                </div>
              )}

              {/* ── Step 4 ── */}
              {step === 4 && (
                <div>
                  <h2 className="text-lg font-black text-[#14140f] mb-1">Customize &amp; Review</h2>
                  <p className="text-xs text-[#8b877d] mb-7">
                    Style the widget your customers will see, then create the bot
                  </p>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                    {/* Live widget preview */}
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d] mb-3">
                        Widget Preview
                      </p>
                      <div className="rounded-xl border border-[#d5d1c6] overflow-hidden bg-white max-w-sm">
                        <div
                          className="flex items-center gap-2.5 px-4 py-3.5"
                          style={{ backgroundColor: color }}
                        >
                          <div className="w-7 h-7 rounded-lg bg-white/25 flex items-center justify-center text-[11px] font-black text-white">
                            {previewName.charAt(0).toUpperCase()}
                          </div>
                          <span className="text-xs font-bold text-white truncate">{previewName}</span>
                        </div>
                        <div className="p-4 bg-[#fbfaf7] space-y-2.5 min-h-[150px]">
                          <div className="flex justify-start">
                            <div className="max-w-[80%] rounded-xl rounded-bl-sm bg-white border border-[#d5d1c6] px-3.5 py-2.5">
                              <p className="text-[11px] text-[#14140f] leading-relaxed">
                                {welcomeMessage || 'Welcome message goes here'}
                              </p>
                            </div>
                          </div>
                          <div className="flex justify-end">
                            <div
                              className="max-w-[80%] rounded-xl rounded-br-sm px-3.5 py-2.5"
                              style={{ backgroundColor: color }}
                            >
                              <p className="text-[11px] text-white">I need help with my order</p>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 px-3 py-2.5 border-t border-[#e7e4dc] bg-white">
                          <div className="flex-1 px-3 py-2 rounded-full bg-[#fbfaf7] border border-[#d5d1c6]">
                            <span className="text-[11px] text-[#8b877d]">Type a message…</span>
                          </div>
                          <button
                            className="px-3 py-2 rounded-full text-[11px] font-bold text-white"
                            style={{ backgroundColor: color }}
                            disabled
                          >
                            Send
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Controls */}
                    <div>
                      <div className="mb-5">
                        <label className="block text-xs font-bold text-[#14140f] mb-2">Primary Color</label>
                        <div className="flex flex-wrap items-center gap-2 mb-3">
                          {COLOR_PRESETS.map((preset) => (
                            <button
                              key={preset}
                              onClick={() => setColor(preset)}
                              className={`w-8 h-8 rounded-lg border-2 transition-all ${
                                color.toLowerCase() === preset.toLowerCase()
                                  ? 'border-black scale-110'
                                  : 'border-transparent hover:scale-105'
                              }`}
                              style={{ backgroundColor: preset }}
                              title={preset}
                            />
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={color}
                            onChange={(e) => setColor(e.target.value)}
                            className="w-10 h-9 rounded-lg border border-[#d5d1c6] cursor-pointer bg-white p-0.5"
                          />
                          <input
                            type="text"
                            value={color}
                            onChange={(e) => setColor(e.target.value)}
                            className="flex-1 px-3.5 py-2 text-xs rounded-lg border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] font-mono"
                          />
                        </div>
                      </div>

                      <div className="mb-5">
                        <label className="block text-xs font-bold text-[#14140f] mb-2">Bot Display Name</label>
                        <input
                          type="text"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          placeholder={botName || 'Assistant'}
                          className="w-full px-4 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d]"
                        />
                        <p className="text-[11px] text-[#8b877d] mt-1.5">
                          Leave blank to use &ldquo;{botName || 'Assistant'}&rdquo;
                        </p>
                      </div>

                      <div>
                        <label className="block text-xs font-bold text-[#14140f] mb-2">Welcome Message</label>
                        <textarea
                          value={welcomeMessage}
                          onChange={(e) => setWelcomeMessage(e.target.value)}
                          rows={3}
                          className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] resize-none"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Review summary */}
                  <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] p-5">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-[#8b877d] mb-4">
                      Review
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
                      {[
                        ['Name', botName || '—'],
                        ['Display name', previewName],
                        ['Category', CATEGORIES.find((c) => c.id === category)?.name ?? '—'],
                        ['Tone', toneName(tone)],
                        ['Traits', traits.length ? traits.join(', ') : '—'],
                        ['Custom instructions', customPrompt.trim() ? 'Yes' : 'None'],
                        ['Knowledge sources', knowledgeSummary.length ? knowledgeSummary.join(', ') : 'None'],
                        ['Description', description.trim() || '—'],
                      ].map(([label, value]) => (
                        <div key={label} className="flex items-start justify-between gap-4 min-w-0">
                          <span className="text-[11px] text-[#8b877d] shrink-0">{label}</span>
                          <span className="text-[11px] font-bold text-[#14140f] text-right truncate">
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>

          {/* Error + progress */}
          <div className="mt-7">
            {error && (
              <div className="flex items-start gap-2.5 rounded-xl border border-[#e6c3c8] bg-[#fbeaec] px-4 py-3 mb-4">
                <span className="text-xs font-semibold text-[#96203f] leading-relaxed">{error}</span>
              </div>
            )}
            {creating && progressNote && (
              <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 mb-4">
                <div className="flex items-center gap-2.5">
                  <Spinner className="w-3.5 h-3.5 text-[#8b877d]" />
                  <span className="text-xs font-semibold text-[#56544d] flex-1 truncate">
                    {progressNote}
                  </span>
                  {sourcesTotal > 0 && (
                    <span className="text-[11px] font-bold text-[#8b877d] shrink-0">
                      {sourcesDone} / {sourcesTotal}
                    </span>
                  )}
                </div>
                {sourcesTotal > 0 && (
                  <div className="h-1.5 rounded-full bg-[#d5d1c6] overflow-hidden mt-2.5">
                    <motion.div
                      className="h-full bg-black rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.round((sourcesDone / sourcesTotal) * 100)}%` }}
                      transition={{ duration: 0.3 }}
                    />
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-between gap-3 pt-5 border-t border-[#e7e4dc]">
              <button
                onClick={goPrev}
                disabled={step === 1 || creating}
                className="flex items-center gap-2 px-4 py-2.5 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <IconArrowLeft className="w-3.5 h-3.5" />
                Previous
              </button>

              {step < STEPS.length ? (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={goNext}
                  className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold rounded-lg bg-black text-white hover:bg-[#14140f] transition-all"
                >
                  Continue
                  <IconArrowRight className="w-3.5 h-3.5" />
                </motion.button>
              ) : (
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleCreate}
                  disabled={creating}
                  className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold rounded-lg bg-black text-white hover:bg-[#14140f] transition-all disabled:opacity-50"
                >
                  {creating ? (
                    <>
                      <Spinner className="w-3.5 h-3.5" />
                      Creating…
                    </>
                  ) : (
                    <>
                      <IconCheck className="w-3.5 h-3.5" />
                      Create Chatbot
                    </>
                  )}
                </motion.button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
