import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { tickets, type TicketDetail } from '../api/client'
import {
  ArrowLeft,
  Loader2,
  ExternalLink,
  User,
  Mail,
  Calendar,
  Tag,
  MessageSquare,
} from 'lucide-react'

interface Reply {
  role?: string
  name?: string
  content?: string
  posted?: string
}

export default function TicketDetail() {
  const { id } = useParams<{ id: string }>()
  const [ticket, setTicket] = useState<TicketDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const data = await tickets.get(id)
      setTicket(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load ticket')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  if (!id) return null

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-muted animate-fade-in">
        <Loader2 size={20} className="animate-spin-slow" />
        <span>Đang tải ticket...</span>
      </div>
    )
  }

  if (error && !ticket) {
    return (
      <div className="animate-fade-in">
        <div className="p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm">
          {error}
        </div>
        <Link
          to="/tickets"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-zinc-100"
        >
          <ArrowLeft size={16} /> Quay lại danh sách tickets
        </Link>
      </div>
    )
  }

  if (!ticket) return null

  const replies: Reply[] =
    ticket.metadata && typeof ticket.metadata === 'object' && Array.isArray(ticket.metadata.replies)
      ? (ticket.metadata.replies as Reply[])
      : []

  return (
    <div className="animate-slide-up">
      <header className="flex items-center gap-3 pb-4 border-b border-border mb-6">
        <Link
          to="/tickets"
          className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg font-semibold truncate">{ticket.subject || '(Không có tiêu đề)'}</h1>
            <code className="text-xs text-accent bg-accent-muted px-1.5 py-0.5 rounded font-mono">
              {ticket.external_id || ticket.id.slice(0, 8)}
            </code>
            {ticket.detail_url && (
              <a
                href={ticket.detail_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-hover"
              >
                <ExternalLink size={14} /> Mở trong WHMCS
              </a>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted mt-1 flex-wrap">
            <span className="inline-flex items-center gap-1">
              <Tag size={12} />
              {ticket.status || 'N/A'}
            </span>
            {ticket.priority && (
              <>
                <span>&middot;</span>
                <span>Ưu tiên: {ticket.priority}</span>
              </>
            )}
            {ticket.updated_at && (
              <>
                <span>&middot;</span>
                <span>
                  {new Date(ticket.updated_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          {ticket.description && (
            <section className="bg-surface border border-border rounded-xl p-4">
              <h2 className="text-sm font-medium text-muted mb-2">Mô tả / Nội dung chính</h2>
              <div className="text-sm text-zinc-300 whitespace-pre-wrap">{ticket.description}</div>
            </section>
          )}

          {replies.length > 0 && (
            <section className="bg-surface border border-border rounded-xl overflow-hidden">
              <h2 className="text-sm font-medium text-muted px-4 py-3 border-b border-border flex items-center gap-2">
                <MessageSquare size={16} />
                Hội thoại ({replies.length})
              </h2>
              <div className="divide-y divide-border">
                {replies.map((r, i) => (
                  <div key={i} className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className={`text-xs font-medium px-2 py-0.5 rounded ${
                          r.role === 'staff' || r.role === 'owner'
                            ? 'bg-accent/20 text-accent'
                            : 'bg-surface-hover text-muted-foreground'
                        }`}
                      >
                        {r.role || 'client'}
                      </span>
                      {r.name && <span className="text-sm text-muted">{r.name}</span>}
                      {r.posted && (
                        <span className="text-xs text-muted ml-auto">
                          {new Date(r.posted).toLocaleString('en-US')}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-zinc-300 whitespace-pre-wrap">{r.content || ''}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="space-y-4">
          <section className="bg-surface border border-border rounded-xl p-4">
            <h2 className="text-sm font-medium text-muted mb-3">Thông tin khách hàng</h2>
            <div className="space-y-2 text-sm">
              {ticket.name && (
                <div className="flex items-center gap-2 text-zinc-300">
                  <User size={14} className="text-muted shrink-0" />
                  {ticket.name}
                </div>
              )}
              {ticket.email && (
                <div className="flex items-center gap-2 text-zinc-300">
                  <Mail size={14} className="text-muted shrink-0" />
                  <a
                    href={`mailto:${ticket.email}`}
                    className="text-accent hover:text-accent-hover truncate"
                  >
                    {ticket.email}
                  </a>
                </div>
              )}
              {ticket.client_id && (
                <div className="flex items-center gap-2 text-muted text-xs">
                  Client ID: {ticket.client_id}
                </div>
              )}
              {!ticket.name && !ticket.email && (
                <p className="text-muted text-sm">Không có thông tin</p>
              )}
            </div>
          </section>

          <section className="bg-surface border border-border rounded-xl p-4">
            <h2 className="text-sm font-medium text-muted mb-2">Metadata</h2>
            <div className="text-xs text-muted space-y-1">
              {ticket.source_file && <p>Nguồn: {ticket.source_file}</p>}
              {ticket.created_at && (
                <p className="flex items-center gap-1">
                  <Calendar size={12} />
                  Tạo: {new Date(ticket.created_at).toLocaleString('en-US')}
                </p>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
