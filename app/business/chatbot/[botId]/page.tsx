'use client'

import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useActiveBrand } from '@/lib/useActiveBrand'
import { chatbotApi, ChatbotInstance, BotCategory, BotStatus, BotTone } from '@/lib/chatbotApi'
import {
  CATEGORIES,
  COLOR_PRESETS,
  TONES,
  TRAITS,
  BotAvatar,
  ConfirmModal,
  ErrorBanner,
  IconArrowLeft,
  IconBrain,
  IconChat,
  IconCheck,
  IconCopy,
  IconPause,
  IconPlay,
  IconTrash,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
  formatDate,
} from '@/components/chatbot/shared'

export default function BotDetailPage() {
  const params = useParams<{ botId: string }>()
  const router = useRouter()
  const { userId: ctxUserId } = useActiveBrand()
  const botId = params.botId

  const [bot, setBot] = useState<ChatbotInstance | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  // Editable fields
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState<BotCategory>('custom')
  const [tone, setTone] = useState<BotTone>('professional')
  const [traits, setTraits] = useState<string[]>([])
  const [customPrompt, setCustomPrompt] = useState('')
  const [welcomeMessage, setWelcomeMessage] = useState('')
  const [color, setColor] = useState(COLOR_PRESETS[0])

  const [embedCode, setEmbedCode] = useState('')
  const [copied, setCopied] = useState(false)

  const hydrate = useCallback((data: ChatbotInstance) => {
    setBot(data)
    setName(data.bot_name)
    setDescription(data.description ?? '')
    setCategory(data.category)
    setTone(data.tone)
    // Backend lowercase traits store karta hai — UI chips Title Case hain.
    setTraits(
      (data.personality_traits ?? []).map(
        (t) => TRAITS.find((known) => known.toLowerCase() === t.toLowerCase()) ?? t
      )
    )
    setCustomPrompt(data.custom_prompt ?? '')
    setWelcomeMessage(data.welcome_message ?? '')
    setColor(data.primary_color)
  }, [])

  // Auth guard DashboardShell mein hai — yahan sirf bot ka data.
  useEffect(() => {
    if (!ctxUserId) return
    const init = async () => {
      try {
        // Embed code bot ke saath hi maang lo — pehle wo bot load hone ke BAAD
        // shuru hota tha, yani do sequential round-trips.
        const [res, embed] = await Promise.all([
          chatbotApi.getBot(botId),
          // Embed code optional hai — settings phir bhi editable rehni chahiye
          chatbotApi.getEmbedCode(botId).catch(() => null),
        ])
        hydrate(res.data)
        if (embed) setEmbedCode(embed.embed_code)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load chatbot')
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [ctxUserId, botId, hydrate])

  const handleSave = async () => {
    if (!name.trim()) {
      setError('Chatbot name cannot be empty')
      return
    }
    if (!welcomeMessage.trim()) {
      setError('Welcome message cannot be empty')
      return
    }

    setSaving(true)
    setError('')
    setNotice('')
    try {
      const res = await chatbotApi.updateBot(botId, {
        bot_name: name.trim(),
        description: description.trim() || null,
        category,
        tone,
        personality_traits: traits.map((t) => t.toLowerCase()),
        custom_prompt: customPrompt.trim() || null,
        welcome_message: welcomeMessage.trim(),
        primary_color: color,
      })
      hydrate(res.data)
      setNotice('Settings saved')

      // Embed code mein color/name aate hain — save ke baad refresh karo
      try {
        const embed = await chatbotApi.getEmbedCode(botId)
        setEmbedCode(embed.embed_code)
      } catch {
        // non-critical
      }

      setTimeout(() => setNotice(''), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleStatus = async () => {
    if (!bot) return
    const next: BotStatus = bot.status === 'active' ? 'paused' : 'active'
    setBusy(true)
    try {
      const res = await chatbotApi.updateBot(botId, { status: next })
      hydrate(res.data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update status')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    setBusy(true)
    try {
      await chatbotApi.deleteBot(botId)
      router.push('/business/chatbot')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete chatbot')
      setBusy(false)
      setDeleteOpen(false)
    }
  }

  const copyEmbed = async () => {
    try {
      await navigator.clipboard.writeText(embedCode)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('Could not copy — select the code and copy it manually.')
    }
  }

  if (loading) {
    return (
      <>
        <PageHeader title="Chatbot" subtitle="Loading settings…" />
        <div className="flex items-center justify-center gap-2.5 py-24 text-xs font-semibold text-[#8b877d]">
          <Spinner />
          Loading chatbot…
        </div>
      </>
    )
  }

  if (!bot) {
    return (
      <>
        <PageHeader title="Chatbot" subtitle="Not found" />
        <div className="p-8">
          <ErrorBanner message={error || 'This chatbot could not be found.'} />
          <Link href="/business/chatbot">
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all cursor-pointer">
              <IconArrowLeft className="w-3.5 h-3.5" />
              Back to My Bots
            </span>
          </Link>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader title={bot.bot_name} subtitle="Manage this chatbot's settings and embed code">
        <Link href="/business/chatbot">
          <span className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:bg-[#fbfaf7] transition-colors cursor-pointer">
            <IconArrowLeft className="w-3.5 h-3.5" />
            My Bots
          </span>
        </Link>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-black text-white text-xs font-bold rounded-lg hover:bg-[#14140f] transition-all disabled:opacity-50"
        >
          {saving ? <Spinner className="w-3.5 h-3.5" /> : <IconCheck className="w-3.5 h-3.5" />}
          {saving ? 'Saving…' : 'Save Changes'}
        </motion.button>
      </PageHeader>

      <div className="p-8 max-w-5xl">
        <ErrorBanner message={error} />
        {notice && (
          <div className="flex items-center gap-2.5 rounded-xl border border-[#bcd8c8] bg-[#eaf4ee] px-4 py-3 mb-5">
            <IconCheck className="w-4 h-4 text-[#12876b]" />
            <span className="text-xs font-semibold text-[#12876b]">{notice}</span>
          </div>
        )}

        {/* Identity + stats */}
        <div className="rounded-xl border border-[#d5d1c6] bg-white p-6 mb-6">
          <div className="flex flex-col md:flex-row md:items-center gap-5 mb-6">
            <BotAvatar name={bot.bot_name} color={bot.primary_color} size="lg" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2.5 mb-1.5">
                <h2 className="text-lg font-black text-[#14140f] truncate">{bot.bot_name}</h2>
                <StatusBadge status={bot.status} />
              </div>
              <p className="text-xs text-[#8b877d] mb-1">{bot.description || 'No description provided.'}</p>
              <p className="text-[11px] text-[#8b877d] font-mono">
                {bot.bot_id} · created {formatDate(bot.created_at)}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={handleToggleStatus}
                disabled={busy}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors disabled:opacity-50"
              >
                {bot.status === 'active' ? (
                  <>
                    <IconPause className="w-3.5 h-3.5" />
                    Pause
                  </>
                ) : (
                  <>
                    <IconPlay className="w-3.5 h-3.5" />
                    Resume
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Conversations" value={bot.conversation_count} delay={0} />
            <StatCard label="Escalated" value={bot.escalated_count} accent="red" delay={0.05} />
            <StatCard label="Documents" value={bot.document_count} delay={0.1} />
            <StatCard label="Indexed Chunks" value={bot.chunk_count} delay={0.15} />
          </div>

          <div className="flex flex-wrap items-center gap-2 mt-5 pt-5 border-t border-[#e7e4dc]">
            <Link href={`/business/chatbot/${botId}/training`}>
              <span className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors cursor-pointer">
                <IconBrain className="w-3.5 h-3.5" />
                Knowledge Base
              </span>
            </Link>
            <Link href={`/business/chatbot/conversations?bot=${botId}`}>
              <span className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors cursor-pointer">
                <IconChat className="w-3.5 h-3.5" />
                Conversations
              </span>
            </Link>
          </div>
        </div>

        {/* Settings */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Basics */}
          <div className="rounded-xl border border-[#d5d1c6] bg-white p-6">
            <h3 className="text-sm font-black text-[#14140f] mb-5">Basics</h3>

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#14140f] mb-2">Bot Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f]"
              />
            </div>

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#14140f] mb-2">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder="What does this bot do?"
                className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] resize-none"
              />
            </div>

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#14140f] mb-2">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as BotCategory)}
                className="w-full px-4 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] bg-white"
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#14140f] mb-2">Welcome Message</label>
              <textarea
                value={welcomeMessage}
                onChange={(e) => setWelcomeMessage(e.target.value)}
                rows={2}
                className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] resize-none"
              />
            </div>
          </div>

          {/* Personality */}
          <div className="rounded-xl border border-[#d5d1c6] bg-white p-6">
            <h3 className="text-sm font-black text-[#14140f] mb-5">Personality</h3>

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#14140f] mb-2">Tone</label>
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value as BotTone)}
                className="w-full px-4 py-2.5 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] bg-white"
              >
                {TONES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} — {t.description}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#14140f] mb-2.5">Traits</label>
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

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#14140f] mb-2">Custom Instructions</label>
              <textarea
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                rows={4}
                placeholder="Extra behaviour rules for this bot…"
                className="w-full px-4 py-3 text-xs rounded-xl border border-[#d5d1c6] focus:border-black focus:outline-none transition-colors text-[#14140f] placeholder:text-[#8b877d] resize-none"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-[#14140f] mb-2.5">Primary Color</label>
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
          </div>
        </div>

        {/* Embed */}
        <div className="rounded-xl border border-[#d5d1c6] bg-white p-6 mb-6">
          <div className="flex items-center justify-between gap-4 mb-2">
            <h3 className="text-sm font-black text-[#14140f]">Website Embed</h3>
            <button
              onClick={copyEmbed}
              disabled={!embedCode}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-lg border border-[#d5d1c6] text-[#56544d] hover:border-[#0a0a0a] hover:text-[#14140f] transition-colors disabled:opacity-40"
            >
              {copied ? <IconCheck className="w-3.5 h-3.5" /> : <IconCopy className="w-3.5 h-3.5" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
                    <p className="text-xs text-[#8b877d] mb-4">
            Save your changes above first, so the widget picks up the latest name and colour.
            Then copy this code and follow the six steps below.
          </p>
          <pre className="rounded-xl bg-[#fbfaf7] border border-[#d5d1c6] p-4 text-[11px] font-mono text-[#14140f] overflow-x-auto whitespace-pre-wrap break-all">
                        {embedCode || 'Embed code unavailable — try reloading the page.'}
          </pre>
        </div>

        {/* ── Shopify install guide ─────────────────────────────────────────
            Zyada tar brand owners developer nahi hain. Pehle yahan sirf ek
            line thi -- "paste before </body>" -- jo un ke liye kaafi nahi
            thi: unhein ye pata hi nahi hota ke theme ka code kahan khulta hai.
            Ab poora rasta likha hai, wohi alfaz jo Shopify admin me dikhte
            hain, taake screen par dhoondhna aasan rahe. */}
        <div className="rounded-xl border border-[#d5d1c6] bg-white p-6 mb-6">
          <h3 className="text-sm font-black text-[#14140f]">How to add this to your Shopify store</h3>
          <p className="mt-1 mb-5 text-xs text-[#8b877d]">
            No coding needed &mdash; you are pasting one line into your theme. It takes about two
            minutes, and you can undo it any time by deleting the same line.
          </p>

          <ol className="space-y-4">
            {[
              {
                t: 'Log in to your Shopify admin',
                d: <>Go to <span className="font-mono text-[#14140f]">admin.shopify.com</span> and sign in to the store you want the chatbot on.</>,
              },
              {
                t: 'Open Online Store \u2192 Themes',
                d: <>In the left sidebar click <b className="text-[#14140f]">Online Store</b>, then <b className="text-[#14140f]">Themes</b>.</>,
              },
              {
                t: 'Open the code editor',
                d: <>Find your <b className="text-[#14140f]">active theme</b> (the one marked &ldquo;Current theme&rdquo;), click the <b className="text-[#14140f]">&hellip;</b> three-dots button next to it, and choose <b className="text-[#14140f]">Edit code</b>.</>,
              },
              {
                t: 'Open theme.liquid',
                d: <>In the file list on the left, under <b className="text-[#14140f]">Layout</b>, click <span className="font-mono text-[#14140f]">theme.liquid</span>. Every Shopify theme has this file &mdash; it is the main layout, so the chatbot loads on every page of your store.</>,
              },
              {
                t: 'Scroll to the bottom and find </body>',
                d: <>Scroll right to the end of the file. Near the last few lines you will see <span className="font-mono text-[#14140f]">&lt;/body&gt;</span>. If it is hard to spot, click inside the code and press <b className="text-[#14140f]">Ctrl&nbsp;+&nbsp;F</b> (<b className="text-[#14140f]">Cmd&nbsp;+&nbsp;F</b> on Mac) and search for it.</>,
              },
              {
                t: 'Paste the code just above </body>, then Save',
                d: <>Put your cursor on the empty line directly <b className="text-[#14140f]">above</b> <span className="font-mono text-[#14140f]">&lt;/body&gt;</span>, paste, and click <b className="text-[#14140f]">Save</b> at the top right. Open your storefront &mdash; the chat bubble appears in the bottom corner.</>,
              },
            ].map((step, i) => (
              <li key={step.t} className="flex gap-3.5">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-[#0a0a0a] text-[10px] font-bold text-white">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-bold text-[#14140f]">{step.t}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-[#56544d]">{step.d}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-5 rounded-lg border border-[#f2d6a6] bg-[#fdf4e6] px-4 py-3">
            <p className="text-xs font-bold text-[#a8620d]">Two things worth knowing</p>
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs leading-relaxed text-[#a8620d]">
              <li>Editing <span className="font-mono">theme.liquid</span> is safe and reversible &mdash; to remove the chatbot later, delete the same line and save.</li>
              <li>Paste it once. Adding it to more than one file makes two chat bubbles appear.</li>
            </ul>
          </div>
        </div>


        {/* Danger zone */}
        <div className="rounded-xl border border-[#e6c3c8] bg-[#fbeaec] p-6">
          <h3 className="text-sm font-black text-[#96203f] mb-1">Danger Zone</h3>
          <p className="text-xs text-[#96203f] mb-4">
            Deleting this chatbot removes its conversations and knowledge base permanently.
          </p>
          <button
            onClick={() => setDeleteOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-[#96203f] text-white text-xs font-bold rounded-lg hover:bg-[#96203f] transition-colors"
          >
            <IconTrash className="w-3.5 h-3.5" />
            Delete Chatbot
          </button>
        </div>
      </div>

      <ConfirmModal
        open={deleteOpen}
        title={`Delete ${bot.bot_name}?`}
        description="This permanently removes the chatbot, its conversations and its entire knowledge base. This cannot be undone."
        confirmLabel="Delete chatbot"
        busy={busy}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />
    </>
  )
}
