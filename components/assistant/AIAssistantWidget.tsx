'use client'

import { useState, useRef, useEffect } from 'react'
import { usePathname } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { useActiveBrand, readStoredActiveBrandId } from '@/lib/useActiveBrand'
import { authHeaders } from '@/lib/authHeaders'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Message {
  sender: 'user' | 'assistant'
  message: string
}

interface SessionItem {
  id: string
  title: string
  updated_at: string
}

function getPageContext(pathname: string): string {
  if (pathname.includes('ads-generation')) return 'ads-generation'
  if (pathname.includes('video-ads')) return 'video-ads'
  if (pathname.includes('improvement')) return 'improvement'
  if (pathname.includes('chatbot')) return 'chatbot'
  if (pathname.includes('seo')) return 'seo'
  if (pathname.includes('sentiment')) return 'sentiment'
  if (pathname.includes('scraping')) return 'scraping'
  return 'general'
}

export default function AIAssistantWidget() {
  const pathname = usePathname()
  const supabase = createClient()
  const { activeBrandId } = useActiveBrand()

  const [isOpen, setIsOpen] = useState(false)
  const [showSidebar, setShowSidebar] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string>('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [loggedIn, setLoggedIn] = useState(true)

  const userIdRef = useRef<string>('')
    // Types types/speech-recognition.d.ts mein hain — Web Speech API abhi
  // TypeScript ki DOM lib mein shamil nahi hai.
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const refreshSessions = async (uid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/assistant/sessions/${uid}`, {
        headers: await authHeaders(),
      })
      if (!res.ok) return []
      const data: SessionItem[] = await res.json()
      setSessions(data)
      return data
    } catch {
      return []
    }
  }

  const loadSessionHistory = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/assistant/history/${sessionId}`, {
        headers: await authHeaders(),
      })
      if (!res.ok) { setMessages([]); return }
      const data: Message[] = await res.json()
      setMessages(data)
    } catch {
      setMessages([])
    }
  }

  const startNewChat = () => {
    const newId = crypto.randomUUID()
    setActiveSessionId(newId)
    sessionStorage.setItem('assistant_active_session', newId)
    setMessages([])
    setShowSidebar(false)
  }

  const selectSession = async (sessionId: string) => {
    setActiveSessionId(sessionId)
    sessionStorage.setItem('assistant_active_session', sessionId)
    await loadSessionHistory(sessionId)
    setShowSidebar(false)
  }

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getUser()
      if (!data.user) {
        // Not logged in — disable the widget entirely.
        // The widget only provides value when it can access the user's
        // own brand data; on public pages there's nothing to show.
        userIdRef.current = ''
        setLoggedIn(false)
        return
      }
      const uid = data.user.id
      userIdRef.current = uid

      const sessionList = await refreshSessions(uid)

      const savedId = sessionStorage.getItem('assistant_active_session')
      if (savedId && sessionList.some((s) => s.id === savedId)) {
        setActiveSessionId(savedId)
        await loadSessionHistory(savedId)
      } else if (sessionList.length > 0) {
        setActiveSessionId(sessionList[0].id)
        sessionStorage.setItem('assistant_active_session', sessionList[0].id)
        await loadSessionHistory(sessionList[0].id)
      } else {
        const newId = crypto.randomUUID()
        setActiveSessionId(newId)
        sessionStorage.setItem('assistant_active_session', newId)
      }
    }
    init()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Voices ko ek dafa "warm up" kar dete hain taake pehli call pe khaali na milen
  useEffect(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      speechSynthesis.getVoices()
    }
  }, [])

  const speak = (text: string) => {
    if (!voiceEnabled) return
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return

    const doSpeak = () => {
      const voices = speechSynthesis.getVoices()
      const utterance = new SpeechSynthesisUtterance(text)

      // Assistant sirf English ya Roman Urdu bolta hai, aur Roman Urdu Latin
      // script hai — achi English voice usay theek parh leti hai. Pehle yahan
      // hi-IN voice sab se pehle chuni jati thi, jo Roman Urdu ko Hindi ke
      // hisaab se ghalat pronounce karti thi (aur upar likhe comment ke bhi
      // khilaf thi). Is liye ab sirf English voices, koi Hindi voice nahi.
      const preferredVoice =
        voices.find((v) => v.lang === 'en-US') ||
        voices.find((v) => v.lang === 'en-GB') ||
        voices.find((v) => v.lang.startsWith('en')) ||
        null

      // Koi English voice na mile to `voices[0]` par nahi girte — wo kisi bhi
      // system par Hindi voice ho sakti hai. Voice unset chhorne par browser
      // apni default voice ko en-US lang ke saath use karta hai.
      if (preferredVoice) utterance.voice = preferredVoice
      utterance.lang = preferredVoice?.lang || 'en-US'
      utterance.rate = 0.95

      speechSynthesis.cancel()
      speechSynthesis.speak(utterance)
    }

    const voices = speechSynthesis.getVoices()
    if (voices.length === 0) {
      speechSynthesis.onvoiceschanged = () => {
        doSpeak()
        speechSynthesis.onvoiceschanged = null
      }
    } else {
      doSpeak()
    }
  }

  const sendMessage = async (text: string) => {
    if (!text.trim() || !activeSessionId) return

    const userMsg: Message = { sender: 'user', message: text }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/assistant/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(await authHeaders()),
        },
        body: JSON.stringify({
          session_id: activeSessionId,
          message: text,
          current_page: getPageContext(pathname),
          // Brand ke baghair assistant "koi brand select nahi hai" keh deta hai,
          // is liye id bhejna zaroori hai. Provider ke brands abhi load ho rahe
          // hon to activeBrandId thori der null rehta hai — us window mein
          // localStorage se last selected brand utha lete hain (wohi key jismein
          // switcher save karta hai), warna user ka pehla sawal brand-less jata.
          brand_profile_id: activeBrandId ?? readStoredActiveBrandId(),
        }),
      })
      const data = await res.json()
      // 429 par backend { detail: "Rate limit reached, please wait a minute" }
      // bhejta hai. Pehle sirf data.reply padha jata tha, to user ko khaali
      // bubble dikhta tha.
      if (!res.ok) {
        throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed')
      }
      const assistantMsg: Message = { sender: 'assistant', message: data.reply }
      setMessages((prev) => [...prev, assistantMsg])
      speak(data.reply)

      // Sidebar list refresh karo (naya title/order dikhane ke liye)
      refreshSessions(userIdRef.current)
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          message:
            err instanceof Error && err.message
              ? err.message
              : 'Sorry, kuch masla ho gaya. Dobara try karein.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const startVoiceInput = () => {
        const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      alert('Aapka browser voice input support nahi karta. Chrome/Edge use karein.')
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-US'
    recognition.interimResults = false

    recognition.onstart = () => setIsListening(true)
    recognition.onend = () => setIsListening(false)
        recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error('Speech recognition error:', event.error)
      setIsListening(false)
    }
        recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0][0].transcript
      sendMessage(transcript)
    }

    recognitionRef.current = recognition
    recognition.start()
  }

  // Hide widget entirely when not logged in (public pages).
  if (!loggedIn) return null

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-black text-white shadow-lg flex items-center justify-center hover:bg-gray-900 transition-all"
      >
        {isOpen ? '✕' : '💬'}
      </button>

      {isOpen && (
        <div className="fixed bottom-24 right-6 z-50 w-[420px] h-[550px] bg-white rounded-xl shadow-2xl border border-gray-200 flex overflow-hidden">

          {/* Sidebar */}
          {showSidebar && (
            <div className="w-40 border-r border-gray-200 flex flex-col bg-gray-50">
              <button
                onClick={startNewChat}
                className="m-2 px-2 py-2 bg-black text-white text-xs font-bold rounded-lg"
              >
                + New Chat
              </button>
              <div className="flex-1 overflow-y-auto">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => selectSession(s.id)}
                    className={`w-full text-left px-2 py-2 text-xs border-b border-gray-100 truncate ${
                      s.id === activeSessionId ? 'bg-gray-200 font-bold' : 'hover:bg-gray-100'
                    }`}
                  >
                    {s.title}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Main chat area */}
          <div className="flex-1 flex flex-col">
            <div className="bg-black text-white px-4 py-3 flex items-center justify-between">
              <button onClick={() => setShowSidebar(!showSidebar)} className="text-sm">☰</button>
              <span className="font-bold text-sm">BrandWave Assistant</span>
              <button
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                className={`text-xs px-2 py-1 rounded ${voiceEnabled ? 'bg-green-600' : 'bg-gray-700'}`}
              >
                🔊 {voiceEnabled ? 'On' : 'Off'}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <p className="text-gray-400 text-sm text-center mt-10">
                  Koi bhi sawal poochein — main aapki BrandWave use karne mein madad karunga.
                </p>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap ${
                      m.sender === 'user' ? 'bg-black text-white' : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    {m.message}
                  </div>
                </div>
              ))}
              {loading && <div className="text-gray-400 text-sm">Assistant type kar raha hai...</div>}
              <div ref={messagesEndRef} />
            </div>

            <div className="border-t border-gray-200 p-3 flex items-center gap-2">
              <button
                onClick={startVoiceInput}
                className={`w-9 h-9 flex items-center justify-center rounded-full ${
                  isListening ? 'bg-red-500 text-white animate-pulse' : 'bg-gray-100'
                }`}
              >
                🎤
              </button>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && sendMessage(input)}
                placeholder="Apna sawal likhein..."
                className="flex-1 border border-gray-300 rounded-full px-3 py-2 text-sm focus:outline-none focus:border-black"
              />
              <button
                onClick={() => sendMessage(input)}
                className="w-9 h-9 flex items-center justify-center rounded-full bg-black text-white"
              >
                ➤
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}