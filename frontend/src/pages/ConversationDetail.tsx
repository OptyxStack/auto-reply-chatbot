import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { conversations, type ConversationDetail as ConvDetail, type Message, type FlowDebug } from '../api/client'
import {
  ArrowLeft,
  Copy,
  Check,
  Send,
  Loader2,
  Bot,
  User,
  ChevronDown,
  ChevronRight,
  Zap,
  Search,
  Database,
  FileText,
  Brain,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react'

export default function ConversationDetail() {
  const { id } = useParams<{ id: string }>()
  const [conv, setConv] = useState<ConvDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const load = async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const data = await conversations.get(id)
      setConv(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conversation')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conv?.messages])

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id || !input.trim() || sending) return
    setSending(true)
    setError(null)
    try {
      await conversations.sendMessage(id, input.trim())
      setInput('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send message')
    } finally {
      setSending(false)
    }
  }

  if (!id) return null

  if (loading) return (
    <div className="flex items-center justify-center gap-2 py-20 text-muted animate-fade-in">
      <Loader2 size={20} className="animate-spin-slow" />
      <span>Loading conversation...</span>
    </div>
  )

  if (error && !conv) {
    return (
      <div className="animate-fade-in">
        <div className="p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm">{error}</div>
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-zinc-100">
          <ArrowLeft size={16} /> Back to conversations
        </Link>
      </div>
    )
  }

  if (!conv) return null

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] lg:h-[calc(100vh-2rem)] animate-slide-up">
      <header className="flex items-center gap-3 pb-4 border-b border-border mb-0 shrink-0">
        <Link
          to="/"
          className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold truncate">Conversation</h1>
            <CopyableId id={conv.id} />
          </div>
          <div className="flex items-center gap-3 text-xs text-muted mt-0.5">
            <span className="capitalize">{conv.source_type} / {conv.source_id}</span>
            <span>&middot;</span>
            <span>{new Date(conv.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
            <span>&middot;</span>
            <span>{conv.messages.length} messages</span>
          </div>
        </div>
      </header>

      {error && (
        <div className="p-3 rounded-lg my-3 bg-danger/10 border border-danger/30 text-red-300 text-sm animate-fade-in">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto py-4 space-y-3">
        {conv.messages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-muted">
            <Bot size={32} className="mb-3 text-accent opacity-50" />
            <p className="text-sm">Send a message to start the conversation</p>
          </div>
        )}
        {conv.messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {sending && (
          <div className="flex items-start gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shrink-0 mt-0.5">
              <Bot size={16} className="text-accent" />
            </div>
            <div className="bg-surface border border-border rounded-2xl rounded-tl-md px-4 py-3">
              <div className="flex items-center gap-2 text-muted text-sm">
                <Loader2 size={14} className="animate-spin-slow" />
                Thinking...
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="flex items-end gap-2 pt-4 border-t border-border shrink-0" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          disabled={sending}
          maxLength={10000}
          className="flex-1 px-4 py-3 rounded-xl border border-border bg-surface text-zinc-100 text-sm
                     focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                     placeholder:text-muted disabled:opacity-50"
        />
        <button
          type="submit"
          className="p-3 rounded-xl bg-accent text-white hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          disabled={sending || !input.trim()}
        >
          {sending ? <Loader2 size={18} className="animate-spin-slow" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  )
}

function CopyableId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(id)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-mono text-muted
                 bg-surface-hover hover:text-accent transition-colors"
      title="Copy ID"
    >
      {id.slice(0, 8)}...
      {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
    </button>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const [showFlow, setShowFlow] = useState(false)
  const debug = message.debug
  const hasDebug = debug && (debug.decision != null || debug.confidence != null || debug.trace_id)

  return (
    <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5
          ${isUser ? 'bg-accent' : 'bg-accent/15'}`}
      >
        {isUser ? <User size={16} className="text-white" /> : <Bot size={16} className="text-accent" />}
      </div>

      <div className={`max-w-[80%] min-w-0 ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        <div
          className={`px-4 py-3 text-sm leading-relaxed
            ${isUser
              ? 'bg-accent text-white rounded-2xl rounded-tr-md'
              : 'bg-surface border border-border rounded-2xl rounded-tl-md'
            }`}
        >
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        </div>

        <div className={`flex items-center gap-2 mt-1 px-1 ${isUser ? 'flex-row-reverse' : ''}`}>
          <span className="text-[11px] text-muted">
            {new Date(message.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        {message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {message.citations.map((c, i) => (
              <a
                key={i}
                href={c.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-accent-muted text-accent
                           hover:bg-accent/20 transition-colors"
              >
                <ExternalLink size={10} />
                {c.doc_type || c.source_url || c.chunk_id}
              </a>
            ))}
          </div>
        )}

        {!isUser && hasDebug && (
          <div className="mt-2 w-full">
            <div className="flex flex-wrap items-center gap-1.5 mb-1">
              {debug.decision != null && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-accent-muted text-accent">
                  <Zap size={10} />
                  {debug.decision}
                </span>
              )}
              {debug.confidence != null && (
                <ConfidenceBadge value={debug.confidence} />
              )}
              {debug.intent_cache && (
                <span className="px-2 py-0.5 rounded-md text-[11px] bg-surface-hover text-muted-foreground">
                  cache: {debug.intent_cache}
                </span>
              )}
            </div>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-[11px] text-muted hover:text-muted-foreground transition-colors py-1"
              onClick={() => setShowFlow((v) => !v)}
            >
              {showFlow ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Debug details
            </button>
            {showFlow && <FlowDebugPanel debug={debug} />}
          </div>
        )}
      </div>
    </div>
  )
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'text-emerald-400 bg-emerald-500/10' : pct >= 50 ? 'text-amber-400 bg-amber-500/10' : 'text-red-400 bg-red-500/10'
  return (
    <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ${color}`}>
      {pct}%
    </span>
  )
}

function FlowDebugPanel({ debug }: { debug: FlowDebug }) {
  return (
    <div className="mt-2 bg-primary border border-border rounded-xl overflow-hidden text-xs animate-slide-up">
      {(debug.decision != null || debug.confidence != null || debug.followup_questions?.length) && (
        <DebugSection icon={<Zap size={13} />} title="Decision & Confidence">
          <div className="space-y-1 text-muted-foreground">
            {debug.decision != null && <div>Decision: <span className="text-zinc-300">{debug.decision}</span></div>}
            {debug.confidence != null && <div>Confidence: <span className="text-zinc-300">{(debug.confidence * 100).toFixed(1)}%</span></div>}
            {debug.followup_questions && debug.followup_questions.length > 0 && (
              <div>
                <div className="mb-0.5">Follow-up questions:</div>
                <ul className="list-disc pl-4 space-y-0.5">
                  {debug.followup_questions.map((q, i) => <li key={i} className="text-zinc-300">{q}</li>)}
                </ul>
              </div>
            )}
          </div>
        </DebugSection>
      )}

      <DebugSection icon={<Brain size={13} />} title="Trace & Model">
        <div className="space-y-0.5 text-muted-foreground">
          {debug.trace_id && <div>Trace: <span className="font-mono text-zinc-400">{debug.trace_id}</span></div>}
          {debug.model_used && <div>Model: <span className="text-zinc-300">{debug.model_used}</span></div>}
          {debug.attempt != null && <div>Attempt: <span className="text-zinc-300">{debug.attempt}</span></div>}
          {debug.intent_cache && <div>Intent cache: <span className="text-zinc-300">{debug.intent_cache}</span></div>}
        </div>
      </DebugSection>

      {debug.query_rewrite && (
        <DebugSection icon={<Search size={13} />} title="Query Rewrite">
          <div className="font-mono bg-primary-tertiary p-2.5 rounded-lg space-y-1 text-muted-foreground">
            <div>Keyword: <span className="text-zinc-300">{debug.query_rewrite.keyword_query}</span></div>
            <div>Semantic: <span className="text-zinc-300">{debug.query_rewrite.semantic_query}</span></div>
          </div>
        </DebugSection>
      )}

      {debug.retrieval_stats && (
        <DebugSection icon={<Database size={13} />} title="Retrieval">
          <div className="flex flex-wrap gap-2">
            <StatPill label="BM25" value={debug.retrieval_stats.bm25_count} />
            <StatPill label="Vector" value={debug.retrieval_stats.vector_count} />
            <StatPill label="Merged" value={debug.retrieval_stats.merged_count} />
            <StatPill label="Reranked" value={debug.retrieval_stats.reranked_count} />
          </div>
        </DebugSection>
      )}

      {debug.evidence_summary && debug.evidence_summary.length > 0 && (
        <DebugSection icon={<FileText size={13} />} title={`Evidence (${debug.evidence_summary.length} chunks)`}>
          <div className="space-y-2">
            {debug.evidence_summary.map((e, i) => (
              <div key={i} className="p-2.5 bg-primary-tertiary rounded-lg">
                <div className="flex items-center gap-2 mb-1">
                  <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="text-accent hover:text-accent-hover text-xs">
                    {e.doc_type} &middot; {e.chunk_id.slice(0, 8)}
                  </a>
                  {e.score != null && (
                    <span className="text-muted text-[10px] ml-auto">score: {e.score.toFixed(3)}</span>
                  )}
                </div>
                <div className="text-muted-foreground whitespace-pre-wrap break-words text-[11px] max-h-32 overflow-y-auto leading-relaxed">
                  {e.snippet}
                </div>
              </div>
            ))}
          </div>
        </DebugSection>
      )}

      {debug.prompt_preview && (
        <DebugSection icon={<FileText size={13} />} title="Prompt Preview">
          <div className="space-y-2">
            <div>
              <div className="text-muted mb-1">System ({debug.prompt_preview.system_length} chars)</div>
              <pre className="font-mono text-[11px] whitespace-pre-wrap break-words bg-primary-tertiary p-2.5 rounded-lg text-zinc-400 max-h-40 overflow-y-auto">
                {debug.prompt_preview.system_preview}
              </pre>
            </div>
            <div>
              <div className="text-muted mb-1">User ({debug.prompt_preview.user_length} chars)</div>
              <pre className="font-mono text-[11px] whitespace-pre-wrap break-words bg-primary-tertiary p-2.5 rounded-lg text-zinc-400 max-h-40 overflow-y-auto">
                {debug.prompt_preview.user_preview}
              </pre>
            </div>
          </div>
        </DebugSection>
      )}

      {debug.llm_tokens && (
        <DebugSection icon={<Brain size={13} />} title="LLM Tokens">
          <div className="flex gap-3">
            <StatPill label="Input" value={debug.llm_tokens.input} />
            <StatPill label="Output" value={debug.llm_tokens.output} />
          </div>
        </DebugSection>
      )}

      {debug.reviewer_reasons && debug.reviewer_reasons.length > 0 && (
        <DebugSection icon={<AlertTriangle size={13} />} title="Reviewer">
          <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
            {debug.reviewer_reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </DebugSection>
      )}

      {debug.max_attempts_reached && (
        <div className="px-4 py-2 bg-amber-500/10 border-t border-border text-amber-400 text-xs flex items-center gap-1.5">
          <AlertTriangle size={12} />
          Max retrieval attempts reached
        </div>
      )}
    </div>
  )
}

function DebugSection({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3 border-b border-border last:border-b-0">
      <div className="flex items-center gap-1.5 text-muted font-medium mb-2">
        {icon}
        {title}
      </div>
      {children}
    </div>
  )
}

function StatPill({ label, value }: { label: string; value?: number | null }) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-primary-tertiary rounded-md">
      <span className="text-muted">{label}</span>
      <span className="text-zinc-300 font-medium">{value ?? '-'}</span>
    </div>
  )
}
