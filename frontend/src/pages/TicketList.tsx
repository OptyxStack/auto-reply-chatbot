import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { tickets, type Ticket } from '../api/client'
import {
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Ticket as TicketIcon,
  Search,
  Filter,
} from 'lucide-react'

export default function TicketList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Ticket[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterQ, setFilterQ] = useState('')
  const [filterQApplied, setFilterQApplied] = useState('')
  const pageSize = 15

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await tickets.list(
        page,
        pageSize,
        filterStatus || undefined,
        filterQApplied || undefined
      )
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tickets')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setPage(1)
  }, [filterStatus, filterQApplied])

  useEffect(() => {
    load()
  }, [page, filterStatus, filterQApplied])

  const handleSearch = () => setFilterQApplied(filterQ)

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="animate-slide-up">
      <header className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tickets</h1>
          <p className="text-sm text-muted mt-1">Quản lý ticket từ WHMCS và các nguồn khác</p>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            placeholder="Tìm subject, nội dung..."
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-primary-secondary text-zinc-100 text-sm
                       focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 placeholder:text-muted"
          />
        </div>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          aria-label="Lọc theo trạng thái"
          className="px-3 py-2 rounded-lg border border-border bg-primary-secondary text-zinc-100 text-sm
                     focus:outline-none focus:border-accent"
        >
          <option value="">Tất cả trạng thái</option>
          <option value="Open">Open</option>
          <option value="Answered">Answered</option>
          <option value="Customer-Reply">Customer-Reply</option>
          <option value="Closed">Closed</option>
          <option value="In Progress">In Progress</option>
        </select>
        <button
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover"
          onClick={handleSearch}
        >
          <Filter size={16} />
          Lọc
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm animate-fade-in">
          {error}
        </div>
      )}

      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-muted">
            <Loader2 size={18} className="animate-spin-slow" />
            <span className="text-sm">Đang tải tickets...</span>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-muted">
            <div className="w-12 h-12 rounded-xl bg-accent-muted flex items-center justify-center mb-4">
              <TicketIcon size={24} className="text-accent" />
            </div>
            <p className="font-medium text-zinc-300 mb-1">Chưa có ticket nào</p>
            <p className="text-sm">Crawl tickets từ trang Crawl Tickets để thêm dữ liệu</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">ID</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Subject</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Priority</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Khách hàng</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Cập nhật</th>
                <th className="px-4 py-3 text-right text-muted font-medium text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-border-subtle last:border-b-0 hover:bg-surface-hover transition-colors cursor-pointer group"
                  onClick={() => navigate(`/tickets/${t.id}`)}
                >
                  <td className="px-4 py-3.5">
                    <code className="text-xs text-accent bg-accent-muted px-1.5 py-0.5 rounded font-mono">
                      {t.external_id || t.id.slice(0, 8)}
                    </code>
                  </td>
                  <td className="px-4 py-3.5 max-w-[240px]">
                    <span className="truncate block" title={t.subject}>
                      {t.subject || '(Không có tiêu đề)'}
                    </span>
                  </td>
                  <td className="px-4 py-3.5">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="px-4 py-3.5 text-muted-foreground">{t.priority || '-'}</td>
                  <td className="px-4 py-3.5 text-muted-foreground">
                    {t.name || t.email || '-'}
                  </td>
                  <td className="px-4 py-3.5 text-muted-foreground">
                    {t.updated_at
                      ? new Date(t.updated_at).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })
                      : '-'}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Link
                        to={`/tickets/${t.id}`}
                        className="p-1.5 rounded-md text-muted-foreground hover:text-zinc-100 hover:bg-primary-tertiary"
                        onClick={(e) => e.stopPropagation()}
                        title="Xem chi tiết"
                      >
                        <ExternalLink size={15} />
                      </Link>
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
            {total} ticket &middot; trang {page} / {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              title="Trang trước"
              aria-label="Trang trước"
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
              type="button"
              title="Trang sau"
              aria-label="Trang sau"
              className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || '').toLowerCase()
  const colors: Record<string, string> = {
    open: 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20',
    answered: 'bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20',
    'customer-reply': 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20',
    closed: 'bg-zinc-500/10 text-zinc-400 ring-1 ring-zinc-500/20',
    'in progress': 'bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20',
  }
  const cls = colors[s] || 'bg-surface-hover text-muted-foreground ring-1 ring-border'
  return (
    <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-md ${cls}`}>
      {status || 'N/A'}
    </span>
  )
}
