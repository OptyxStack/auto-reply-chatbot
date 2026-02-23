import { useState } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import {
  MessageSquare,
  FileText,
  BarChart3,
  Bot,
  Menu,
  X,
} from 'lucide-react'
import ConversationList from './pages/ConversationList'
import ConversationDetail from './pages/ConversationDetail'
import DocumentList from './pages/DocumentList'
import DocumentDetail from './pages/DocumentDetail'
import Dashboard from './pages/Dashboard'

const NAV_ITEMS = [
  { to: '/', icon: MessageSquare, label: 'Conversations', match: ['/conversations'] },
  { to: '/documents', icon: FileText, label: 'Documents', match: ['/documents'] },
  { to: '/dashboard', icon: BarChart3, label: 'Dashboard', match: ['/dashboard'] },
]

function App() {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const isActive = (item: typeof NAV_ITEMS[0]) => {
    if (item.to === '/' && (location.pathname === '/' || location.pathname.startsWith('/conversations'))) return true
    return item.match.some((m) => location.pathname.startsWith(m))
  }

  return (
    <div className="flex min-h-screen">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`
          fixed top-0 left-0 z-50 h-screen w-[260px] bg-primary-secondary border-r border-border
          flex flex-col transition-transform duration-200 ease-out
          lg:translate-x-0 lg:static lg:z-auto
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <div className="flex items-center gap-3 px-5 h-16 border-b border-border shrink-0">
          <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center">
            <Bot size={18} className="text-accent" />
          </div>
          <div>
            <div className="font-semibold text-sm text-zinc-100 leading-tight">Support AI</div>
            <div className="text-[11px] text-muted leading-tight">Admin Console</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = isActive(item)
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setSidebarOpen(false)}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150
                  ${active
                    ? 'bg-accent/12 text-accent'
                    : 'text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover'
                  }
                `}
              >
                <Icon size={18} strokeWidth={active ? 2 : 1.5} />
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="px-4 py-4 border-t border-border">
          <div className="text-[11px] text-muted">v1.0 &middot; Auto Reply Chatbot</div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-h-screen lg:ml-0">
        <header className="sticky top-0 z-30 flex items-center h-14 px-4 bg-primary/80 backdrop-blur-md border-b border-border lg:hidden">
          <button
            className="p-2 -ml-2 rounded-lg text-muted-foreground hover:text-zinc-100 hover:bg-surface-hover"
            onClick={() => setSidebarOpen(true)}
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <span className="ml-3 font-semibold text-sm">Support AI</span>
        </header>

        <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-[1200px] w-full mx-auto animate-fade-in">
          <Routes>
            <Route path="/" element={<ConversationList />} />
            <Route path="/conversations/:id" element={<ConversationDetail />} />
            <Route path="/documents" element={<DocumentList />} />
            <Route path="/documents/:id" element={<DocumentDetail />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
