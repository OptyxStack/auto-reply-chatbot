import { useState, useEffect } from 'react'
import { admin, type DocType, type DocTypeCreate, type DocTypeUpdate } from '../api/client'
import {
  Plus,
  Trash2,
  Edit2,
  Loader2,
  FileType,
  ChevronDown,
  ChevronRight,
  Check,
  X,
} from 'lucide-react'

export default function DocTypeList() {
  const [items, setItems] = useState<DocType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await admin.listDocTypes()
      setItems(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load doc types')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('Delete this doc type? Documents using it may show as "other".')) return
    try {
      await admin.deleteDocType(id)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-24 animate-fade-in">
        <Loader2 size={22} className="animate-spin-slow text-accent" />
        <span className="text-zinc-500">Loading doc types...</span>
      </div>
    )
  }

  return (
    <div className="animate-slide-up">
      <header className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Doc Types</h1>
          <p className="text-sm text-zinc-500 mt-1.5">
            Document type catalog for classifier and document forms (policy, faq, howto, etc.)
          </p>
        </div>
        <button
          className="btn-primary inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium"
          onClick={() => setShowCreateModal(true)}
        >
          <Plus size={16} />
          Add doc type
        </button>
      </header>

      {error && (
        <div className="p-3.5 rounded-xl mb-5 bg-red-500/10 border border-red-500/20 text-red-300 text-sm">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="flex flex-col items-center py-24 text-zinc-500 glass rounded-2xl">
          <FileType size={40} className="mb-4 text-zinc-600" />
          <p className="font-semibold text-zinc-400 mb-1.5">No doc types yet</p>
          <p className="text-sm mb-5">Add doc types to classify documents and use in forms</p>
          <button
            className="btn-primary inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm"
            onClick={() => setShowCreateModal(true)}
          >
            <Plus size={16} />
            Add first doc type
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((dt) => (
            <div key={dt.id} className="glass rounded-xl overflow-hidden">
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.03] transition-colors"
                onClick={() => setExpandedId(expandedId === dt.id ? null : dt.id)}
              >
                <button className="p-1 text-zinc-500">
                  {expandedId === dt.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <span
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium ${
                    dt.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-500/20 text-zinc-500'
                  }`}
                >
                  {dt.enabled ? 'On' : 'Off'}
                </span>
                <span className="font-mono text-sm text-violet-400">{dt.key}</span>
                <span className="text-zinc-600">·</span>
                <span className="text-sm text-zinc-400 truncate flex-1">{dt.label}</span>
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="p-2 rounded-lg text-zinc-500 hover:text-white hover:bg-white/5"
                    onClick={() => setEditingId(editingId === dt.id ? null : dt.id)}
                  >
                    <Edit2 size={14} />
                  </button>
                  <button
                    className="p-2 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-500/10"
                    onClick={(e) => handleDelete(dt.id, e)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              {expandedId === dt.id && (
                <div className="px-4 pb-4 pt-0 border-t border-white/[0.04] mt-0">
                  <div className="mt-3 space-y-3 text-sm">
                    {dt.description && (
                      <div>
                        <div className="text-zinc-500 text-xs mb-1">Description</div>
                        <div className="text-zinc-300 bg-black/20 p-3 rounded-lg">{dt.description}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {editingId === dt.id && (
                <DocTypeEditForm
                  docType={dt}
                  onSave={() => {
                    setEditingId(null)
                    load()
                  }}
                  onCancel={() => setEditingId(null)}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {showCreateModal && (
        <DocTypeCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false)
            load()
          }}
        />
      )}
    </div>
  )
}

function DocTypeEditForm({
  docType,
  onSave,
  onCancel,
}: {
  docType: DocType
  onSave: () => void
  onCancel: () => void
}) {
  const [label, setLabel] = useState(docType.label)
  const [description, setDescription] = useState(docType.description ?? '')
  const [enabled, setEnabled] = useState(docType.enabled)
  const [sortOrder, setSortOrder] = useState(docType.sort_order)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    setSaving(true)
    try {
      const data: DocTypeUpdate = { label, description: description || null, enabled, sort_order: sortOrder }
      await admin.updateDocType(docType.id, data)
      onSave()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to update')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 border-t border-white/[0.04] space-y-3">
      {err && <div className="text-red-400 text-sm">{err}</div>}
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Label</label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="w-full px-3 py-2 rounded-lg input-glass text-sm"
          required
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full px-3 py-2 rounded-lg input-glass text-sm"
          placeholder="e.g. Privacy policy, data policy..."
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-500 mb-1">Sort order</label>
        <input
          type="number"
          value={sortOrder}
          onChange={(e) => setSortOrder(parseInt(e.target.value, 10) || 0)}
          className="w-full px-3 py-2 rounded-lg input-glass text-sm"
        />
      </div>
      <label className="flex items-center gap-2 text-sm text-zinc-400">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="rounded border-white/10"
        />
        Enabled (used in classifier and forms)
      </label>
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="btn-primary px-4 py-2 rounded-lg text-sm flex items-center gap-2">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          Save
        </button>
        <button type="button" onClick={onCancel} className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:text-white">
          Cancel
        </button>
      </div>
    </form>
  )
}

function DocTypeCreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [sortOrder, setSortOrder] = useState(0)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    setSaving(true)
    try {
      const data: DocTypeCreate = {
        key: key.trim().toLowerCase().replace(/\s+/g, '_'),
        label: label.trim(),
        description: description.trim() || null,
        enabled,
        sort_order: sortOrder,
      }
      await admin.createDocType(data)
      onCreated()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="glass rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-lg font-semibold text-white">Add doc type</h2>
          <button onClick={onClose} className="p-2 rounded-lg text-zinc-500 hover:text-white">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {err && <div className="text-red-400 text-sm">{err}</div>}
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Key (unique id, lowercase)</label>
            <input
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="e.g. policy, faq, howto"
              className="w-full px-3 py-2 rounded-lg input-glass text-sm font-mono"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Label</label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Policy"
              className="w-full px-3 py-2 rounded-lg input-glass text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Privacy policy, data policy, general policies"
              rows={2}
              className="w-full px-3 py-2 rounded-lg input-glass text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Sort order</label>
            <input
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(parseInt(e.target.value, 10) || 0)}
              className="w-full px-3 py-2 rounded-lg input-glass text-sm"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-400">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="rounded border-white/10" />
            Enabled
          </label>
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} className="btn-primary px-4 py-2.5 rounded-xl text-sm flex items-center gap-2">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Create
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2.5 rounded-xl text-sm text-zinc-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
