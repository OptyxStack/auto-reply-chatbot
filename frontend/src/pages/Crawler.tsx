import { useEffect, useState } from 'react'
import { admin, type CheckWhmcsCookiesResponse, type CrawlTicketsResponse } from '../api/client'
import { Loader2, Globe, Key, Shield, Database, LogIn, CheckCircle2, AlertCircle, Cookie, ExternalLink, Save, Link2 } from 'lucide-react'

const DEFAULT_BASE_URL = 'https://greencloudvps.com/billing/greenvps'
const DEFAULT_LIST_PATH = 'supporttickets.php?filter=1'
const DEFAULT_LOGIN_PATH = 'login.php'
const LOGIN_URL = `${DEFAULT_BASE_URL}/${DEFAULT_LOGIN_PATH}`
const LIST_URL = `${DEFAULT_BASE_URL}/${DEFAULT_LIST_PATH}`

const COOKIE_EXAMPLE = `[
  {"name": "WHMCSxyz", "value": "abc123...", "domain": ".greencloudvps.com", "path": "/"},
  {"name": "PHPSESSID", "value": "...", "domain": ".greencloudvps.com", "path": "/"}
]`

export default function Crawler() {
  const [sessionCookies, setSessionCookies] = useState('')
  const [savingCookies, setSavingCookies] = useState(false)
  const [saveCookiesResult, setSaveCookiesResult] = useState<{ count: number } | null>(null)
  const [saveCookiesError, setSaveCookiesError] = useState<string | null>(null)
  const [cookiesStatus, setCookiesStatus] = useState<{ saved: boolean; count: number } | null>(null)
  const [checkingConnect, setCheckingConnect] = useState(false)
  const [connectResult, setConnectResult] = useState<{ ok: boolean; message: string; debug?: CheckWhmcsCookiesResponse['debug'] } | null>(null)

  const [mode, setMode] = useState<'cookies' | 'creds'>('cookies')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL)
  const [listPath, setListPath] = useState(DEFAULT_LIST_PATH)
  const [loginPath, setLoginPath] = useState(DEFAULT_LOGIN_PATH)
  const [crawling, setCrawling] = useState(false)
  const [crawlResult, setCrawlResult] = useState<CrawlTicketsResponse | null>(null)
  const [crawlError, setCrawlError] = useState<string | null>(null)

  const parseCookies = (text: string): Array<{ name: string; value: string; domain?: string; path?: string }> | null => {
    try {
      const parsed = JSON.parse(text.trim())
      if (!Array.isArray(parsed)) return null
      return parsed.filter((c) => c && typeof c.name === 'string' && c.value != null)
    } catch {
      return null
    }
  }

  useEffect(() => {
    admin.getWhmcsCookies().then(setCookiesStatus).catch(() => setCookiesStatus({ saved: false, count: 0 }))
  }, [saveCookiesResult])

  const [checkDebug, setCheckDebug] = useState(false)

  const handleCheckConnect = async (useInlineCookies: boolean) => {
    setConnectResult(null)
    const cookies = useInlineCookies ? parseCookies(sessionCookies) : null
    if (useInlineCookies && (!cookies || cookies.length === 0)) {
      setConnectResult({ ok: false, message: 'Paste cookies into the field above first' })
      return
    }
    if (!useInlineCookies && (!cookiesStatus?.saved || (cookiesStatus?.count ?? 0) === 0)) {
      setConnectResult({ ok: false, message: 'Save cookies first (section 1)' })
      return
    }
    setCheckingConnect(true)
    try {
      const payload = {
        base_url: baseUrl.trim() || DEFAULT_BASE_URL,
        list_path: listPath.trim() || DEFAULT_LIST_PATH,
        debug: checkDebug,
        ...(cookies && cookies.length > 0 ? { session_cookies: cookies } : {}),
      }
      const res = await admin.checkWhmcsCookies(payload)
      setConnectResult({ ok: res.ok, message: res.message, debug: res.debug })
    } catch (e) {
      setConnectResult({ ok: false, message: e instanceof Error ? e.message : 'Check failed' })
    } finally {
      setCheckingConnect(false)
    }
  }

  const handleSaveCookies = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaveCookiesError(null)
    setSaveCookiesResult(null)
    setConnectResult(null)
    const cookies = parseCookies(sessionCookies)
    if (!cookies || cookies.length === 0) {
      setSaveCookiesError('Paste valid cookies JSON. Format: [{"name":"...","value":"...","domain":"...","path":"/"}]')
      return
    }
    setSavingCookies(true)
    try {
      const res = await admin.saveWhmcsCookies({ session_cookies: cookies })
      setSaveCookiesResult({ count: res.count })
      setSaveCookiesError(null)
    } catch (e) {
      setSaveCookiesError(e instanceof Error ? e.message : 'Failed to save cookies')
    } finally {
      setSavingCookies(false)
    }
  }

  const handleCrawl = async (e: React.FormEvent) => {
    e.preventDefault()
    setCrawlError(null)
    setCrawlResult(null)

    if (mode === 'creds') {
      if (!username.trim() || !password.trim()) {
        setCrawlError('Username and Password are required (note: may be blocked by CAPTCHA)')
        return
      }
    } else {
      if (!cookiesStatus?.saved || (cookiesStatus?.count ?? 0) === 0) {
        setCrawlError('Save cookies first (section 1) or switch to Username/Password')
        return
      }
    }

    setCrawling(true)
    try {
      const payload: Parameters<typeof admin.crawlTickets>[0] = {
        base_url: baseUrl.trim() || DEFAULT_BASE_URL,
        list_path: listPath.trim() || DEFAULT_LIST_PATH,
        login_path: loginPath.trim() || DEFAULT_LOGIN_PATH,
      }
      if (mode === 'cookies') {
        payload.username = undefined
        payload.password = undefined
        payload.session_cookies = undefined
      } else {
        payload.username = username.trim()
        payload.password = password
        payload.totp_code = totpCode.trim() || undefined
      }
      const res = await admin.crawlTickets(payload)
      setCrawlResult(res)
    } catch (e) {
      setCrawlError(e instanceof Error ? e.message : 'Crawl failed')
    } finally {
      setCrawling(false)
    }
  }

  return (
    <div className="animate-slide-up max-w-2xl space-y-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Crawl Tickets WHMCS</h1>
        <p className="text-sm text-muted mt-1">
          Step 1: Save cookies after manual login. Step 2: Crawl ticket list.
        </p>
      </header>

      {/* --- Section 1: Save cookies --- */}
      <section className="bg-surface border border-border rounded-xl p-6">
        <h2 className="text-lg font-medium flex items-center gap-2 mb-4">
          <Cookie size={18} />
          1. Save Session Cookies
        </h2>
        <p className="text-sm text-muted mb-4">
          <strong>Method 1 – Login via browser (recommended):</strong> Run script on local machine, open browser to login, script will fetch cookies and send to API.
        </p>
        <p className="text-xs text-muted mb-2">First time: setup venv and install package</p>
        <div className="mb-2 p-3 rounded-lg bg-primary/50 font-mono text-xs overflow-x-auto space-y-1">
          <div># Windows (PowerShell)</div>
          <div>.\scripts\setup_login.ps1</div>
          <div className="mt-2"># Linux/Mac</div>
          <div>bash scripts/setup_login.sh</div>
        </div>
        <p className="text-xs text-muted mb-2">Then: activate venv and run script</p>
        <div className="mb-4 p-3 rounded-lg bg-primary/50 font-mono text-xs overflow-x-auto space-y-1">
          <div>.\.venv-login\Scripts\Activate.ps1   # Windows</div>
          <div>source .venv-login/bin/activate     # Linux/Mac</div>
          <div className="mt-2">python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key</div>
        </div>
        <p className="text-xs text-muted mb-4">
          Run on local machine (not in Docker). API can run in Docker, use --api-url http://localhost:8000/v1.
        </p>
        <p className="text-sm text-muted mb-4">
          <strong>Method 2 – Copy cookies manually:</strong>{' '}
          <a href={LOGIN_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-accent hover:underline">
            <ExternalLink size={14} />
            Open WHMCS login page
          </a>
          {' → '}Login (solve CAPTCHA if any) → F12 → Application → Cookies → Copy → Paste JSON into field below
        </p>
        <form onSubmit={handleSaveCookies} className="space-y-4">
          <textarea
            value={sessionCookies}
            onChange={(e) => setSessionCookies(e.target.value)}
            placeholder={COOKIE_EXAMPLE}
            rows={5}
            className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100 text-sm font-mono
                       focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                       placeholder:text-muted"
            disabled={savingCookies}
          />
          {saveCookiesError && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-danger/10 border border-danger/30 text-red-300 text-sm">
              <AlertCircle size={16} className="shrink-0" />
              {saveCookiesError}
            </div>
          )}
          <div className="flex gap-2 flex-wrap">
            <button
              type="submit"
              disabled={savingCookies}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                         bg-accent text-white font-medium hover:bg-accent-hover
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {savingCookies ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save size={16} />
                  Save cookies
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => handleCheckConnect(true)}
              disabled={savingCookies || checkingConnect}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                         border border-border bg-primary text-zinc-200 hover:bg-primary/80
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {checkingConnect ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Checking...
                </>
              ) : (
                <>
                  <Link2 size={16} />
                  Check connect
                </>
              )}
            </button>
            <label className="inline-flex items-center gap-2 text-sm text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={checkDebug}
                onChange={(e) => setCheckDebug(e.target.checked)}
                className="rounded border-border"
              />
              Debug
            </label>
          </div>
        </form>
        {connectResult && (
          <div className="mt-4 space-y-2">
            <div className={`flex items-center gap-2 text-sm ${connectResult.ok ? 'text-emerald-300' : 'text-amber-300'}`}>
              {connectResult.ok ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
              {connectResult.message}
            </div>
            {connectResult.debug && Object.keys(connectResult.debug).length > 0 && (
              <pre className="mt-2 p-3 rounded-lg bg-black/30 text-xs text-muted overflow-x-auto max-h-48 overflow-y-auto">
                {JSON.stringify(connectResult.debug, null, 2)}
              </pre>
            )}
          </div>
        )}
        {saveCookiesResult && (
          <div className="mt-4 flex items-center gap-2 text-emerald-300 text-sm">
            <CheckCircle2 size={16} />
            Saved {saveCookiesResult.count} cookies
          </div>
        )}
        {cookiesStatus?.saved && cookiesStatus.count > 0 && !saveCookiesResult && (
          <div className="mt-4 text-sm text-muted">
            {cookiesStatus.count} cookies saved. You can crawl now (section 2).
          </div>
        )}
      </section>

      {/* --- Section 2: Crawl tickets --- */}
      <section className="bg-surface border border-border rounded-xl p-6">
        <h2 className="text-lg font-medium flex items-center gap-2 mb-4">
          <Database size={18} />
          2. Crawl ticket list
        </h2>
        <p className="text-sm text-muted mb-4">
          Use saved cookies or Username/Password. Ticket list at{' '}
          <a href={LIST_URL} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
            supporttickets.php?filter=1
          </a>
        </p>

        <form onSubmit={handleCrawl} className="space-y-5">
          <div className="flex gap-2 p-1 rounded-lg bg-primary/50">
            <button
              type="button"
              onClick={() => setMode('cookies')}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-colors ${
                mode === 'cookies' ? 'bg-accent text-white' : 'text-muted hover:text-zinc-100'
              }`}
            >
              <Cookie size={16} />
              Use saved cookies
            </button>
            <button
              type="button"
              onClick={() => setMode('creds')}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-colors ${
                mode === 'creds' ? 'bg-accent text-white' : 'text-muted hover:text-zinc-100'
              }`}
            >
              <Key size={16} />
              Username / Password
            </button>
          </div>

          {mode === 'cookies' && (
            <div className="text-sm text-muted">
              Will use {cookiesStatus?.count ?? 0} cookies saved in section 1.
            </div>
          )}

          {mode === 'creds' && (
            <>
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-zinc-200 mb-2">
                  <Key size={14} />
                  Username / Email
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="your@email.com"
                  className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100
                             focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                             placeholder:text-muted"
                  autoComplete="username"
                  disabled={crawling}
                />
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-zinc-200 mb-2">
                  <Key size={14} />
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100
                             focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                             placeholder:text-muted"
                  autoComplete="current-password"
                  disabled={crawling}
                />
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-zinc-200 mb-2">
                  <Shield size={14} />
                  2FA Code (Authenticator)
                </label>
                <input
                  type="text"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  placeholder="123456"
                  maxLength={8}
                  className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100
                             focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                             placeholder:text-muted font-mono tracking-widest"
                  autoComplete="one-time-code"
                  disabled={crawling}
                />
              </div>
            </>
          )}

          <div className="border-t border-border pt-4 space-y-4">
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-zinc-200 mb-2">
                <Globe size={14} />
                Base URL
              </label>
              <input
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={DEFAULT_BASE_URL}
                className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100
                           focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                           placeholder:text-muted"
                disabled={crawling}
              />
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-zinc-200 mb-2">
                <Database size={14} />
                List path (ticket list page)
              </label>
              <input
                type="text"
                value={listPath}
                onChange={(e) => setListPath(e.target.value)}
                placeholder={DEFAULT_LIST_PATH}
                className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100
                           focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                           placeholder:text-muted"
                disabled={crawling}
              />
              <p className="text-xs text-muted mt-1">Default: supporttickets.php?filter=1</p>
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-zinc-200 mb-2">
                <LogIn size={14} />
                Login path
              </label>
              <input
                type="text"
                value={loginPath}
                onChange={(e) => setLoginPath(e.target.value)}
                placeholder={DEFAULT_LOGIN_PATH}
                className="w-full px-4 py-2.5 rounded-lg border border-border bg-primary text-zinc-100
                           focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
                           placeholder:text-muted"
                disabled={crawling}
              />
            </div>
          </div>

          {crawlError && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-danger/10 border border-danger/30 text-red-300 text-sm">
              <AlertCircle size={16} className="shrink-0" />
              {crawlError}
            </div>
          )}

          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => handleCheckConnect(false)}
              disabled={crawling || checkingConnect || mode !== 'cookies' || !cookiesStatus?.saved}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                         border border-border bg-primary text-zinc-200 hover:bg-primary/80
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {checkingConnect ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Checking...
                </>
              ) : (
                <>
                  <Link2 size={16} />
                  Check connect
                </>
              )}
            </button>
            <button
              type="submit"
              disabled={crawling}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg
                       bg-accent text-white font-medium hover:bg-accent-hover
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {crawling ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Crawling... (may take 2–5 minutes)
              </>
            ) : (
              <>
                <Database size={18} />
                Start crawl
              </>
            )}
            </button>
          </div>
        </form>
        {connectResult && (
          <div className="mt-4 space-y-2">
            <div className={`flex items-center gap-2 text-sm ${connectResult.ok ? 'text-emerald-300' : 'text-amber-300'}`}>
              {connectResult.ok ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
              {connectResult.message}
            </div>
            {connectResult.debug && Object.keys(connectResult.debug).length > 0 && (
              <pre className="mt-2 p-3 rounded-lg bg-black/30 text-xs text-muted overflow-x-auto max-h-48 overflow-y-auto">
                {JSON.stringify(connectResult.debug, null, 2)}
              </pre>
            )}
          </div>
        )}

        {crawlResult && (
          <div className="mt-6 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 animate-fade-in">
            <div className="flex items-center gap-2 text-emerald-300 font-medium mb-2">
              <CheckCircle2 size={18} />
              Crawl complete
            </div>
            <p className="text-sm text-emerald-200/90">
              Saved <strong>{crawlResult.count}</strong> ticket(s) to{' '}
              {crawlResult.saved_to === 'database' ? (
                <span>database</span>
              ) : (
                <code className="text-xs bg-black/20 px-1.5 py-0.5 rounded">{crawlResult.saved_to}</code>
              )}
              {crawlResult.skipped != null && crawlResult.skipped > 0 && (
                <span className="ml-2 text-amber-300">
                  (skipped {crawlResult.skipped} system alert tickets)
                </span>
              )}
            </p>
            <p className="text-sm text-muted mt-1">
              Go to Tickets page to approve tickets and export to file (only approved tickets are used).
            </p>
            {crawlResult.tickets.length > 0 && (
              <div className="mt-3 max-h-48 overflow-y-auto rounded-lg bg-black/20 p-3 text-xs">
                {crawlResult.tickets.slice(0, 10).map((t) => (
                  <div key={t.external_id} className="py-1.5 border-b border-emerald-500/20 last:border-0">
                    <span className="text-muted">#{t.external_id}</span> {t.subject?.slice(0, 50)}
                    {t.subject && t.subject.length > 50 ? '…' : ''}
                  </div>
                ))}
                {crawlResult.tickets.length > 10 && (
                  <div className="py-1.5 text-muted">
                    ... and {crawlResult.tickets.length - 10} more tickets
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
