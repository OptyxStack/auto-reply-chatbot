import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { documents, type Document, DOC_TYPES } from '../api/client'
import {
  ArrowLeft,
  Save,
  Pencil,
  Trash2,
  Loader2,
  ExternalLink,
  Calendar,
  Layers,
  FileText,
  X,
  Clock,
  Link as LinkIcon,
  Tag,
} from 'lucide-react'

export default function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDocType, setEditDocType] = useState('')
  const [editMetadata, setEditMetadata] = useState('')
  const [saving, setSaving] = useState(false)

  const load = async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const res = await documents.get(id)
      setDoc(res)
      setEditTitle(res.title)
      setEditDocType(res.doc_type)
      setEditMetadata(res.metadata ? JSON.stringify(res.metadata, null, 2) : '{}')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  const handleSave = async () => {
    if (!id || !doc) return
    setSaving(true)
    setError(null)
    try {
      let metadata: Record<string, unknown> | undefined
      try {
        metadata = JSON.parse(editMetadata || '{}')
      } catch {
        setError('Invalid metadata JSON')
        setSaving(false)
        return
      }
      const updated = await documents.update(id, {
        title: editTitle,
        doc_type: editDocType,
        metadata,
      })
      setDoc(updated)
      setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!id || !confirm('Delete this document? Chunks and index will be removed.')) return
    try {
      await documents.delete(id)
      navigate('/documents')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  const inputClass = `w-full px-3 py-2.5 rounded-lg border border-border bg-primary-secondary text-zinc-100 text-sm
                      focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 placeholder:text-muted`

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-muted animate-fade-in">
        <Loader2 size={20} className="animate-spin-slow" />
        <span>Loading document...</span>
      </div>
    )
  }

  if (!doc) {
    return (
      <div className="animate-fade-in">
        <div className="p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm">
          {error || 'Document not found'}
        </div>
        <Link to="/documents" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-zinc-100">
          <ArrowLeft size={16} /> Back to documents
        </Link>
      </div>
    )
  }

  return (
    <div className="animate-slide-up">
      <header className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/documents"
            className="p-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover transition-colors shrink-0"
          >
            <ArrowLeft size={18} />
          </Link>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold truncate">{doc.title || '(Untitled)'}</h1>
            <div className="flex items-center gap-2 text-xs text-muted mt-0.5">
              <code className="font-mono bg-surface-hover px-1.5 py-0.5 rounded">{doc.id.slice(0, 12)}...</code>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {editing ? (
            <>
              <button
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium
                           hover:bg-accent-hover disabled:opacity-50"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? <Loader2 size={14} className="animate-spin-slow" /> : <Save size={14} />}
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-medium
                           text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover"
                onClick={() => setEditing(false)}
              >
                <X size={14} />
                Cancel
              </button>
            </>
          ) : (
            <button
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover"
              onClick={() => setEditing(true)}
            >
              <Pencil size={14} />
              Edit
            </button>
          )}
          <button
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-danger/30 text-danger text-sm font-medium
                       hover:bg-danger/10 transition-colors"
            onClick={handleDelete}
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      </header>

      {error && (
        <div className="p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm animate-fade-in">
          {error}
        </div>
      )}

      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        {editing ? (
          <div className="p-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1.5">Title</label>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className={inputClass}
                aria-label="Title"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1.5">Type</label>
              <select value={editDocType} onChange={(e) => setEditDocType(e.target.value)} className={inputClass} aria-label="Type">
                {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1.5">Metadata (JSON)</label>
              <textarea
                value={editMetadata}
                onChange={(e) => setEditMetadata(e.target.value)}
                className={`${inputClass} font-mono`}
                rows={5}
                aria-label="Metadata JSON"
              />
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border">
            <DetailRow icon={<FileText size={15} />} label="Title" value={doc.title} />
            <DetailRow icon={<LinkIcon size={15} />} label="URL">
              <a
                href={doc.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-accent hover:text-accent-hover text-sm"
              >
                {doc.source_url}
                <ExternalLink size={12} />
              </a>
            </DetailRow>
            <DetailRow icon={<Tag size={15} />} label="Type" value={doc.doc_type} />
            <DetailRow icon={<Layers size={15} />} label="Chunks" value={String(doc.chunks_count)} />
            <DetailRow icon={<Calendar size={15} />} label="Created" value={new Date(doc.created_at).toLocaleString('en-US')} />
            <DetailRow icon={<Clock size={15} />} label="Updated" value={new Date(doc.updated_at).toLocaleString('en-US')} />
            {doc.metadata && Object.keys(doc.metadata).length > 0 && (
              <div className="px-6 py-4">
                <div className="text-xs font-medium text-muted uppercase tracking-wider mb-2">Metadata</div>
                <pre className="font-mono text-xs text-muted-foreground whitespace-pre-wrap break-words bg-primary-tertiary p-3 rounded-lg">
                  {JSON.stringify(doc.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {doc.cleaned_content && (
        <div className="mt-4 bg-surface border border-border rounded-xl overflow-hidden">
          <div className="px-6 py-3 border-b border-border flex items-center gap-2">
            <FileText size={15} className="text-muted" />
            <h3 className="text-sm font-medium">Content</h3>
            <span className="text-xs text-muted ml-auto">
              {doc.cleaned_content.length.toLocaleString()} chars
            </span>
          </div>
          <div className="p-6">
            <pre className="font-mono text-xs text-muted-foreground whitespace-pre-wrap break-words bg-primary-tertiary p-4 rounded-lg max-h-[500px] overflow-auto leading-relaxed">
              {doc.cleaned_content.slice(0, 5000)}
              {doc.cleaned_content.length > 5000 && '\n\n... (truncated)'}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

function DetailRow({
  icon,
  label,
  value,
  children,
}: {
  icon: React.ReactNode
  label: string
  value?: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3 px-6 py-3.5">
      <span className="text-muted shrink-0">{icon}</span>
      <span className="text-xs font-medium text-muted uppercase tracking-wider w-20 shrink-0">{label}</span>
      <span className="text-sm text-zinc-200">{children || value}</span>
    </div>
  )
}
