import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { documents, admin, type Document, DOC_TYPES } from '../api/client'
import {
  Plus,
  Trash2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileText,
  Search,
  Filter,
  X,
  Layers,
  Download,
  Database,
} from 'lucide-react'

const DOC_TYPE_COLORS: Record<string, string> = {
  policy: 'text-blue-400 bg-blue-500/10 ring-blue-500/20',
  tos: 'text-purple-400 bg-purple-500/10 ring-purple-500/20',
  faq: 'text-emerald-400 bg-emerald-500/10 ring-emerald-500/20',
  howto: 'text-cyan-400 bg-cyan-500/10 ring-cyan-500/20',
  pricing: 'text-amber-400 bg-amber-500/10 ring-amber-500/20',
  other: 'text-muted-foreground bg-surface-hover ring-border',
}

export default function DocumentList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Document[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [filterDocType, setFilterDocType] = useState<string>('')
  const [filterQ, setFilterQ] = useState('')
  const [filterQApplied, setFilterQApplied] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState<{ ok: number; skipped: number; error: number } | null>(null)
  const pageSize = 15

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await documents.list(page, pageSize, filterDocType || undefined, filterQApplied || undefined)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load documents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setPage(1)
  }, [filterDocType, filterQApplied])

  useEffect(() => {
    load()
  }, [page, filterDocType, filterQApplied])

  useEffect(() => {
    if (!ingestResult) return
    const t = setTimeout(() => setIngestResult(null), 5000)
    return () => clearTimeout(t)
  }, [ingestResult])

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('Delete this document? Chunks and index will be removed.')) return
    try {
      await documents.delete(id)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  const handleIngestFromSource = async () => {
    if (!confirm('Ingest documents from source/ folder (custom_docs.json, sample_docs.json, etc.)?')) return
    setIngesting(true)
    setError(null)
    setIngestResult(null)
    try {
      const res = await admin.ingestFromSource()
      setIngestResult(res.results ?? null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ingest failed')
    } finally {
      setIngesting(false)
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="animate-slide-up">
      <header className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-sm text-muted mt-1">Knowledge base documents for AI retrieval</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-medium
                       text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={handleIngestFromSource}
            disabled={ingesting}
            title="Load from source/custom_docs.json, sample_docs.json, etc."
          >
            {ingesting ? <Loader2 size={16} className="animate-spin-slow" /> : <Database size={16} />}
            {ingesting ? 'Ingesting...' : 'Ingest from source'}
          </button>
          <button
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium
                       hover:bg-accent-hover shadow-[0_0_0_1px_rgba(99,102,241,0.5)] hover:shadow-[0_0_0_1px_rgba(129,140,248,0.5)]"
            onClick={() => setShowCreateModal(true)}
          >
            <Plus size={16} />
            Add document
          </button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative">
          <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          <select
            value={filterDocType}
            onChange={(e) => setFilterDocType(e.target.value)}
            className="pl-8 pr-4 py-2.5 rounded-lg border border-border bg-surface text-sm text-zinc-100
                       focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 appearance-none
                       min-w-[160px]"
            aria-label="Filter by type"
          >
            <option value="">All types</option>
            {DOC_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          <input
            type="search"
            placeholder="Search title, URL..."
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && setFilterQApplied(filterQ)}
            className="w-full pl-8 pr-4 py-2.5 rounded-lg border border-border bg-surface text-sm text-zinc-100
                       focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                       placeholder:text-muted"
            aria-label="Search"
          />
        </div>
        <button
          className="px-4 py-2.5 rounded-lg bg-surface border border-border text-sm font-medium text-muted-foreground
                     hover:text-zinc-100 hover:border-accent/50 transition-colors"
          onClick={() => setFilterQApplied(filterQ)}
        >
          Search
        </button>
        {(filterDocType || filterQApplied) && (
          <button
            className="px-3 py-2.5 rounded-lg text-xs text-muted hover:text-zinc-100 hover:bg-surface-hover transition-colors"
            onClick={() => { setFilterDocType(''); setFilterQ(''); setFilterQApplied('') }}
          >
            Clear filters
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm animate-fade-in">
          {error}
        </div>
      )}
      {ingestResult && (
        <div className="flex items-center gap-2 p-3 rounded-lg mb-4 bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm animate-fade-in">
          Ingest complete: {ingestResult.ok} added, {ingestResult.skipped} skipped, {ingestResult.error} errors
        </div>
      )}

      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-muted">
            <Loader2 size={18} className="animate-spin-slow" />
            <span className="text-sm">Loading documents...</span>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-muted">
            <div className="w-12 h-12 rounded-xl bg-accent-muted flex items-center justify-center mb-4">
              <FileText size={24} className="text-accent" />
            </div>
            <p className="font-medium text-zinc-300 mb-1">No documents found</p>
            <p className="text-sm mb-4">
              {filterDocType || filterQApplied ? 'Try adjusting your filters' : 'Add your first document to get started'}
            </p>
            {!filterDocType && !filterQApplied && (
              <button
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover"
                onClick={() => setShowCreateModal(true)}
              >
                <Plus size={16} />
                Add document
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">ID</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Title</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Type</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Chunks</th>
                <th className="px-4 py-3 text-left text-muted font-medium text-xs uppercase tracking-wider">Updated</th>
                <th className="px-4 py-3 text-right text-muted font-medium text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr
                  key={d.id}
                  className="border-b border-border-subtle last:border-b-0 hover:bg-surface-hover transition-colors cursor-pointer group"
                  onClick={() => navigate(`/documents/${d.id}`)}
                >
                  <td className="px-4 py-3.5">
                    <code className="text-xs text-accent bg-accent-muted px-1.5 py-0.5 rounded font-mono">
                      {d.id.slice(0, 8)}
                    </code>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className="text-zinc-200 font-medium">{d.title || '(Untitled)'}</span>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md ring-1 capitalize ${DOC_TYPE_COLORS[d.doc_type] || DOC_TYPE_COLORS.other}`}>
                      {d.doc_type}
                    </span>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      <Layers size={13} className="text-muted" />
                      {d.chunks_count}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-muted-foreground">
                    {new Date(d.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Link
                        to={`/documents/${d.id}`}
                        className="p-1.5 rounded-md text-muted-foreground hover:text-zinc-100 hover:bg-primary-tertiary"
                        onClick={(e) => e.stopPropagation()}
                        title="View"
                      >
                        <ExternalLink size={15} />
                      </Link>
                      <button
                        className="p-1.5 rounded-md text-muted hover:text-danger hover:bg-danger/10"
                        onClick={(e) => handleDelete(d.id, e)}
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
              className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
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
              className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}

      {showCreateModal && (
        <CreateDocumentModal
          onSuccess={(doc) => {
            setShowCreateModal(false)
            navigate(`/documents/${doc.id}`)
          }}
          onCancel={() => setShowCreateModal(false)}
        />
      )}
    </div>
  )
}

function CreateDocumentModal({
  onSuccess,
  onCancel,
}: {
  onSuccess: (doc: Document) => void
  onCancel: () => void
}) {
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [docType, setDocType] = useState('other')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [fetching, setFetching] = useState(false)

  const handleFetchFromUrl = async () => {
    if (!url.trim()) {
      setError('Please enter URL first')
      return
    }
    setFetching(true)
    setError(null)
    try {
      const res = await documents.fetchFromUrl(url.trim())
      setTitle(res.title)
      setContent(res.content)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch content from URL')
    } finally {
      setFetching(false)
    }
  }

  const handleSubmit = async () => {
    if (!url.trim()) {
      setError('Please enter URL')
      return
    }
    if (!content.trim()) {
      setError('Please enter content')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const doc = await documents.create({
        url: url.trim(),
        title: title.trim() || 'Untitled',
        content: content.trim(),
        doc_type: docType,
      })
      onSuccess(doc)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
    } finally {
      setSubmitting(false)
    }
  }

  const inputClass = `w-full px-3 py-2.5 rounded-lg border border-border bg-primary-secondary text-zinc-100 text-sm
                      focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 placeholder:text-muted`

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[1000] p-4 animate-fade-in" onClick={onCancel}>
      <div
        className="bg-surface border border-border rounded-xl w-full max-w-[600px] max-h-[90vh] overflow-y-auto shadow-2xl animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold">Add document</h2>
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
            <label className="block text-sm font-medium text-muted-foreground mb-1.5">URL <span className="text-danger">*</span></label>
            <div className="flex gap-2">
              <input
                type="url"
                value={url}
                onChange={(e) => { setUrl(e.target.value); setError(null) }}
                placeholder="https://..."
                className={inputClass}
              />
              <button
                type="button"
                onClick={handleFetchFromUrl}
                disabled={fetching || !url.trim()}
                className="shrink-0 inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg border border-border text-sm font-medium
                         text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover disabled:opacity-50 disabled:cursor-not-allowed"
                title="Auto fetch content from URL"
              >
                {fetching ? <Loader2 size={14} className="animate-spin-slow" /> : <Download size={14} />}
                {fetching ? 'Fetching...' : 'Fetch content'}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1.5">Title</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Document title" className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1.5">Type</label>
            <select value={docType} onChange={(e) => setDocType(e.target.value)} className={inputClass} aria-label="Type">
              {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1.5">Content <span className="text-danger">*</span></label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Paste text or HTML content..."
              className={inputClass}
              rows={6}
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
            {submitting ? 'Processing...' : 'Add document'}
          </button>
        </div>
      </div>
    </div>
  )
}
