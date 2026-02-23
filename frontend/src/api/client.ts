import axios, { type AxiosInstance } from 'axios'

// Use full backend URL in dev (e.g. VITE_API_BASE=http://localhost:8000/v1), relative /v1 in prod (nginx proxies)
const API_BASE = import.meta.env.VITE_API_BASE || '/v1'
// Dùng chung một key cho cả API và Admin (X-API-Key + X-Admin-API-Key)
const API_KEY = import.meta.env.VITE_API_KEY || import.meta.env.VITE_ADMIN_API_KEY || 'dev-key'

const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
    'X-Admin-API-Key': API_KEY,
  },
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.response?.data?.message || err.message || `HTTP ${err.response?.status}`
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  }
)

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { method = 'GET', body, headers: optHeaders } = options
  const res = await http.request<T>({
    url: path,
    method: (method as string).toUpperCase() || 'GET',
    data: body ? (typeof body === 'string' ? JSON.parse(body) : body) : undefined,
    headers: optHeaders as Record<string, string> | undefined,
  })
  if (res.status === 204) return undefined as T
  return res.data as T
}

export type SourceType = 'ticket' | 'livechat'

export const conversations = {
  list: (page = 1, pageSize = 20, sourceType?: string, sourceId?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (sourceType) params.set('source_type', sourceType)
    if (sourceId) params.set('source_id', sourceId)
    return api<{ items: Conversation[]; total: number; page: number; page_size: number }>(
      `/conversations?${params}`
    )
  },
  get: (id: string) =>
    api<ConversationDetail>(`/conversations/${id}`),
  create: (sourceType: SourceType, sourceId: string, metadata?: Record<string, unknown>) =>
    api<Conversation>(`/conversations`, {
      method: 'POST',
      body: JSON.stringify({
        source_type: sourceType,
        source_id: sourceId,
        metadata: metadata ?? {},
      }),
    }),
  update: (id: string, metadata: Record<string, unknown>) =>
    api<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ metadata }),
    }),
  delete: (id: string) =>
    api<void>(`/conversations/${id}`, { method: 'DELETE' }),
  sendMessage: (id: string, content: string) =>
    api<SendMessageResponse>(`/conversations/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
}

export const dashboard = {
  stats: () => api<{ metrics: Record<string, number> }>('/dashboard/stats'),
}

export interface IngestFromSourceResponse {
  status: string
  message?: string
  results?: { ok: number; skipped: number; error: number }
  total?: number
}

export const admin = {
  ingestFromSource: (sourceDir = 'source') =>
    http.post<IngestFromSourceResponse>(`/admin/ingest-from-source`, null, {
      params: { source_dir: sourceDir },
    }).then((res) => res.data),
}

export const DOC_TYPES = ['policy', 'tos', 'faq', 'howto', 'pricing', 'other'] as const

export interface Document {
  id: string
  title: string
  source_url: string
  doc_type: string
  effective_date: string | null
  chunks_count: number
  source_file: string | null
  metadata: Record<string, unknown> | null
  raw_content?: string | null
  cleaned_content?: string | null
  created_at: string
  updated_at: string
}

export interface FetchFromUrlResponse {
  title: string
  content: string
  raw_html?: string | null
}

export const documents = {
  fetchFromUrl: (url: string) =>
    api<FetchFromUrlResponse>(`/documents/fetch-from-url`, {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  list: (page = 1, pageSize = 20, docType?: string, q?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (docType) params.set('doc_type', docType)
    if (q) params.set('q', q)
    return api<{ items: Document[]; total: number; page: number; page_size: number }>(
      `/documents?${params}`
    )
  },
  get: (id: string) => api<Document>(`/documents/${id}`),
  create: (data: {
    url: string
    title?: string
    content?: string
    raw_text?: string
    raw_html?: string
    doc_type?: string
    effective_date?: string
    metadata?: Record<string, unknown>
    source_file?: string
  }) =>
    api<Document>(`/documents`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: { title?: string; doc_type?: string; effective_date?: string; metadata?: Record<string, unknown> }) =>
    api<Document>(`/documents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    api<void>(`/documents/${id}`, { method: 'DELETE' }),
}

export interface Conversation {
  id: string
  source_type: string
  source_id: string
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface FlowDebug {
  trace_id?: string
  attempt?: number
  model_used?: string
  decision?: string
  confidence?: number
  followup_questions?: string[]
  query_rewrite?: { keyword_query: string; semantic_query: string }
  retrieval_stats?: { bm25_count?: number; vector_count?: number; merged_count?: number; reranked_count?: number }
  evidence_summary?: { chunk_id: string; source_url: string; doc_type: string; score?: number; snippet: string }[]
  prompt_preview?: { system_length: number; user_length: number; system_preview: string; user_preview: string }
  llm_tokens?: { input: number; output: number }
  reviewer_reasons?: string[]
  max_attempts_reached?: boolean
  intent_cache?: string
}

export interface Message {
  id: string
  role: string
  content: string
  created_at: string
  citations?: { chunk_id: string; source_url: string; doc_type: string }[]
  debug?: FlowDebug
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface SendMessageResponse {
  conversation_id: string
  message: {
    message_id: string
    content: string
    citations: { chunk_id: string; source_url: string; doc_type: string }[]
    confidence: number
    decision: string
    created_at: string
    debug?: FlowDebug
  }
}
