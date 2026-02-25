import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { conversations, type Conversation, type SourceType } from '../api/client'
import {
  Plus,
  Trash2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Loader2,
  MessageSquare,
  Ticket,
  Radio,
  X,
} from 'lucide-react'

export default function ConversationList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Conversation[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const pageSize = 15

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await conversations.list(page, pageSize)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [page])

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('Delete this conversation?')) return
    try {
      await conversations.delete(id)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="animate-slide-up">
      <header className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Conversations</h1>
          <p className="text-sm text-muted mt-1">Manage and view all customer conversations</p>
        </div>
        <button
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium
                     hover:bg-accent-hover shadow-[0_0_0_1px_rgba(99,102,241,0.5)] hover:shadow-[0_0_0_1px_rgba(129,140,248,0.5)]"
          onClick={() => setShowCreateModal(true)}
        >
          <Plus size={16} />
          New conversation
        </button>
      </header>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm animate-fade-in">
          {error}
        </div>
      )}

      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-muted">
            <Loader2 size={18} className="animate-spin-slow" />
            <span className="text-sm">Loading conversations...</span>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-muted">
            <div className="w-12 h-12 rounded-xl bg-accent-muted flex items-center justify-center mb-4">
              <MessageSquare size={24} className="text-accent" />
            </div>
            <p className="font-medium text-zinc-300 mb-1">No conversations yet</p>
            <p className="text-sm mb-4">Create your first conversation to get started</p>
            <button
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover"
              onClick={() => setShowCreateModal(true)}
            >
              <Plus size={16} />
              Create conversation
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">ID</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Source</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Source ID</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Created</th>
                <th className="px-4 py-3 text-right text-muted font-medium text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-border-subtle last:border-b-0 hover:bg-surface-hover transition-colors cursor-pointer group"
                  onClick={() => navigate(`/conversations/${c.id}`)}
                >
                  <td className="px-4 py-3.5">
                    <code className="text-xs text-accent bg-accent-muted px-1.5 py-0.5 rounded font-mono">
                      {c.id.slice(0, 8)}
                    </code>
                  </td>
                  <td className="px-4 py-3.5">
                    <SourceBadge type={c.source_type} />
                  </td>
                  <td className="px-4 py-3.5 text-muted-foreground">{c.source_id}</td>
                  <td className="px-4 py-3.5 text-muted-foreground">
                    {new Date(c.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    <span className="text-muted ml-1.5 text-xs">
                      {new Date(c.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Link
                        to={`/conversations/${c.id}`}
                        className="p-1.5 rounded-md text-muted-foreground hover:text-zinc-100 hover:bg-primary-tertiary"
                        onClick={(e) => e.stopPropagation()}
                        title="View"
                      >
                        <ExternalLink size={15} />
                      </Link>
                      <button
                        className="p-1.5 rounded-md text-muted hover:text-danger hover:bg-danger/10"
                        onClick={(e) => handleDelete(c.id, e)}
                        title="Delete"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm text-muted">
            {total} total &middot; page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft size={18} />
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const p = page <= 3 ? i + 1 : page + i - 2
              if (p < 1 || p > totalPages) return null
              return (
                <button
                  key={p}
                  className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors
                    ${p === page
                      ? 'bg-accent text-white'
                      : 'text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover'
                    }`}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              )
            })}
            <button
              className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}

      {showCreateModal && (
        <CreateConversationModal
          onSuccess={(conv) => {
            setShowCreateModal(false)
            navigate(`/conversations/${conv.id}`)
          }}
          onCancel={() => setShowCreateModal(false)}
        />
      )}
    </div>
  )
}

function SourceBadge({ type }: { type: string }) {
  const isTicket = type === 'ticket'
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md capitalize
        ${isTicket
          ? 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20'
          : 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20'
        }`}
    >
      {isTicket ? <Ticket size={12} /> : <Radio size={12} />}
      {type}
    </span>
  )
}

function CreateConversationModal({
  onSuccess,
  onCancel,
}: {
  onSuccess: (c: Conversation) => void
  onCancel: () => void
}) {
  const [sourceType, setSourceType] = useState<SourceType>('ticket')
  const [sourceId, setSourceId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!sourceId.trim()) {
      setError('Please enter ticket or livechat ID')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const conv = await conversations.create(sourceType, sourceId.trim())
      onSuccess(conv)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[1000] p-4 animate-fade-in" onClick={onCancel}>
      <div
        className="bg-surface border border-border rounded-xl w-full max-w-[480px] shadow-2xl animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold">New conversation</h2>
          <button
            className="p-1.5 rounded-lg text-muted hover:text-zinc-100 hover:bg-surface-hover"
            onClick={onCancel}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>
        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-danger/10 border border-danger/30 text-red-300 text-sm">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1.5">Source type</label>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as SourceType)}
              className="w-full px-3 py-2.5 rounded-lg border border-border bg-primary-secondary text-zinc-100 text-sm
                         focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
              aria-label="Source type"
            >
              <option value="ticket">Ticket</option>
              <option value="livechat">Livechat</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1.5">
              {sourceType === 'ticket' ? 'Ticket' : 'Livechat'} ID
            </label>
            <input
              type="text"
              placeholder="e.g. ticket ID or livechat ID"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              className="w-full px-3 py-2.5 rounded-lg border border-border bg-primary-secondary text-zinc-100 text-sm
                         focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                         placeholder:text-muted"
              aria-label="ID"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-border">
          <button
            className="px-4 py-2.5 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium
                       hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting && <Loader2 size={14} className="animate-spin-slow" />}
            {submitting ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}
