import { authHeaders } from '@/lib/authHeaders'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function wsUrl(path: string): string {
  return `${API_BASE.replace(/^http/, 'ws')}${path}`
}

export type BotStatus = 'active' | 'paused' | 'draft'
export type BotCategory = 'ecommerce' | 'support' | 'sales' | 'custom'
export type BotTone = 'professional' | 'friendly' | 'casual' | 'empathetic'
export type DocumentSource = 'document' | 'text' | 'faq'

export interface ChatbotInstance {
  id: number
  bot_id: string
  user_id: string
  bot_name: string
  description: string | null
  category: BotCategory
  personality: string
  tone: BotTone
  personality_traits: string[]
  custom_prompt: string | null
  welcome_message: string
  primary_color: string
  owner_email: string | null
  brand_profile_id: number | null
  status: BotStatus
  is_active: boolean
  created_at: string | null
  document_count: number
  chunk_count: number
  conversation_count: number
  escalated_count: number
}

export interface UploadedDocumentItem {
  id: number
  bot_id: string
  filename: string
  file_type: string | null
  file_size: number
  chunks_stored: number
  source_type: DocumentSource
  uploaded_at: string | null
}

export interface ConversationSummary {
  id: number
  bot_id: string
  bot_name: string | null
  customer_session_id: string
  started_at: string | null
  is_escalated: boolean
  escalated_at: string | null
  message_count: number
  last_message: string | null
  avg_confidence: number | null
}

export interface MessageItem {
  id: number
  sender: 'customer' | 'bot'
  content: string
  confidence_score: number | null
  created_at: string | null
}

export interface FaqPair {
  question: string
  answer: string
}

export interface CreateBotPayload {
  user_id: string
  bot_name: string
  description?: string | null
  category?: BotCategory
  personality?: string
  tone?: BotTone
  personality_traits?: string[]
  custom_prompt?: string | null
  welcome_message?: string
  primary_color?: string
  owner_email?: string | null
  /** Active brand — link create par hi set ho jata hai. */
  brand_profile_id?: number | null
  status?: BotStatus
}

export type UpdateBotPayload = Partial<Omit<CreateBotPayload, 'user_id'>> & { is_active?: boolean }

interface ApiEnvelope {
  success: boolean
  message?: string
  detail?: string
}

/**
 * FastAPI errors ko readable Error mein badalta hai — warna failed request par
 * UI par `undefined` ya blank message show hota hai.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await authHeaders()
  const mergedHeaders = {
    ...(init?.headers || {}),
    ...auth,
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: mergedHeaders })

  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }

  if (!res.ok) {
    const envelope = body as ApiEnvelope | null
    const detail =
      (typeof envelope?.detail === 'string' && envelope.detail) ||
      envelope?.message ||
      `Request failed (${res.status})`
    throw new Error(detail)
  }

  return body as T
}

export const chatbotApi = {
  // ── Bots ────────────────────────────────────
  getMyBot: (userId: string) =>
    request<{ success: boolean; data: ChatbotInstance | null }>(`/api/chatbot/my-bot/${userId}`),

  getMyBots: (userId: string) =>
    request<{ success: boolean; data: ChatbotInstance[] }>(`/api/chatbot/my-bots/${userId}`),

  getBot: (botId: string) =>
    request<{ success: boolean; data: ChatbotInstance }>(`/api/chatbot/bot/${botId}`),

  createChatbot: (payload: CreateBotPayload) =>
    request<{ success: boolean; message: string; data: ChatbotInstance }>('/api/chatbot/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  updateBot: (botId: string, payload: UpdateBotPayload) =>
    request<{ success: boolean; message: string; data: ChatbotInstance }>(`/api/chatbot/${botId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  duplicateBot: (botId: string) =>
    request<{ success: boolean; message: string; data: ChatbotInstance }>(
      `/api/chatbot/${botId}/duplicate`,
      { method: 'POST' }
    ),

  deleteBot: (botId: string) =>
    request<{ success: boolean; message: string; bot_id: string }>(`/api/chatbot/${botId}`, {
      method: 'DELETE',
    }),

  // ── Knowledge Base ──────────────────────────
  getDocuments: (botId: string) =>
    request<{ success: boolean; data: UploadedDocumentItem[]; total_chunks: number }>(
      `/api/chatbot/documents/${botId}`
    ),

  uploadDocument: (botId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<{
      success: boolean
      message: string
      chunks_stored: number
      document: UploadedDocumentItem
    }>(`/api/chatbot/upload/${botId}`, { method: 'POST', body: formData })
  },

  uploadText: (botId: string, text: string, title?: string) =>
    request<{
      success: boolean
      message: string
      chunks_stored: number
      document: UploadedDocumentItem
    }>(`/api/chatbot/upload-text/${botId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, title: title ?? null }),
    }),

  uploadFaq: (botId: string, faqs: FaqPair[], title?: string) =>
    request<{
      success: boolean
      message: string
      chunks_stored: number
      faqs_stored: number
      document: UploadedDocumentItem
    }>(`/api/chatbot/upload-faq/${botId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ faqs, title: title ?? null }),
    }),

  deleteDocument: (docId: number) =>
    request<{
      success: boolean
      message: string
      bot_id: string
      vectors_removed: number
      legacy_vectors: boolean
    }>(`/api/chatbot/documents/${docId}`, { method: 'DELETE' }),

  clearKnowledgeBase: (botId: string) =>
    request<{ success: boolean; message: string; documents_removed: number }>(
      `/api/chatbot/knowledge-base/${botId}`,
      { method: 'DELETE' }
    ),

  // ── Embed ───────────────────────────────────
  getEmbedCode: (botId: string) =>
    request<{ success: boolean; bot_id: string; embed_code: string }>(`/api/chatbot/embed/${botId}`),

  // ── Conversations ───────────────────────────
  getConversations: (userId: string) =>
    request<{ success: boolean; data: ConversationSummary[] }>(`/api/chatbot/conversations/${userId}`),

  getMessages: (conversationId: number) =>
    request<{
      success: boolean
      conversation: {
        id: number
        bot_id: string
        customer_session_id: string
        is_escalated: boolean
        escalated_at: string | null
      }
      data: MessageItem[]
    }>(`/api/chatbot/messages/${conversationId}`),

  escalate: (conversationId: number) =>
    request<{ success: boolean; message: string; conversation_id: number }>(
      `/api/chatbot/escalate/${conversationId}`,
      { method: 'POST' }
    ),
}
