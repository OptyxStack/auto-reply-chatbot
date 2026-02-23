import { useState, useEffect } from 'react'
import { dashboard } from '../api/client'
import {
  BarChart3,
  Loader2,
  TrendingUp,
  Activity,
  Zap,
  MessageSquare,
  Clock,
  RefreshCw,
} from 'lucide-react'

const METRIC_ICONS: Record<string, typeof Activity> = {
  requests: Activity,
  messages: MessageSquare,
  latency: Clock,
  tokens: Zap,
  conversations: MessageSquare,
}

const METRIC_COLORS = [
  'from-indigo-500/20 to-indigo-500/5 ring-indigo-500/20',
  'from-emerald-500/20 to-emerald-500/5 ring-emerald-500/20',
  'from-amber-500/20 to-amber-500/5 ring-amber-500/20',
  'from-cyan-500/20 to-cyan-500/5 ring-cyan-500/20',
  'from-purple-500/20 to-purple-500/5 ring-purple-500/20',
  'from-rose-500/20 to-rose-500/5 ring-rose-500/20',
]

const METRIC_TEXT_COLORS = [
  'text-indigo-400',
  'text-emerald-400',
  'text-amber-400',
  'text-cyan-400',
  'text-purple-400',
  'text-rose-400',
]

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const res = await dashboard.stats()
      setMetrics(res.metrics || {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load stats')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const entries = Object.entries(metrics).filter(([k]) => k.startsWith('support_ai_'))

  if (loading) return (
    <div className="flex items-center justify-center gap-2 py-20 text-muted animate-fade-in">
      <Loader2 size={20} className="animate-spin-slow" />
      <span>Loading dashboard...</span>
    </div>
  )

  if (error && entries.length === 0) return (
    <div className="animate-fade-in">
      <div className="p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm">{error}</div>
    </div>
  )

  return (
    <div className="animate-slide-up">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted mt-1">Real-time metrics from Prometheus</p>
        </div>
        <button
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-medium
                     text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover transition-colors
                     disabled:opacity-50"
          onClick={() => load(true)}
          disabled={refreshing}
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin-slow' : ''} />
          Refresh
        </button>
      </header>

      {error && (
        <div className="p-3 rounded-lg mb-4 bg-danger/10 border border-danger/30 text-red-300 text-sm animate-fade-in">
          {error}
        </div>
      )}

      {entries.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-muted">
          <div className="w-14 h-14 rounded-2xl bg-accent-muted flex items-center justify-center mb-4">
            <BarChart3 size={28} className="text-accent" />
          </div>
          <p className="font-medium text-zinc-300 mb-1">No metrics available</p>
          <p className="text-sm">Metrics will appear once the system starts processing requests</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {entries.map(([key, value], index) => {
            const name = key.replace('support_ai_', '')
            const iconKey = Object.keys(METRIC_ICONS).find((k) => name.toLowerCase().includes(k))
            const Icon = iconKey ? METRIC_ICONS[iconKey] : TrendingUp
            const colorIdx = index % METRIC_COLORS.length
            const gradientClass = METRIC_COLORS[colorIdx]
            const textColor = METRIC_TEXT_COLORS[colorIdx]

            return (
              <div
                key={key}
                className={`relative overflow-hidden bg-gradient-to-br ${gradientClass} ring-1 rounded-xl p-5 transition-all hover:scale-[1.02]`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-9 h-9 rounded-lg bg-primary/40 flex items-center justify-center ${textColor}`}>
                    <Icon size={18} />
                  </div>
                </div>
                <div className="text-3xl font-bold tracking-tight text-zinc-100 mb-1">
                  {formatMetricValue(value)}
                </div>
                <div className="text-xs font-medium text-muted-foreground capitalize">
                  {name.replace(/_/g, ' ')}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function formatMetricValue(value: number): string {
  if (typeof value !== 'number') return String(value)
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  if (Number.isInteger(value)) return value.toLocaleString()
  return value.toFixed(2)
}
