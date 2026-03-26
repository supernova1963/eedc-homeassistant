/**
 * Protokolle – System-Logs + Aktivitätsprotokoll
 *
 * Zwei-Tab-Seite unter System im Einstellungen-Menü.
 * Tab 1: Echtzeit-Logviewer (Ring Buffer, auto-refresh)
 * Tab 2: Persistentes Aktivitätsprotokoll (SQLite, filterbar)
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ScrollText, Activity, RefreshCw, Search, Trash2, ClipboardCopy, Download,
  CheckCircle, XCircle, ChevronLeft, ChevronRight, Pause, Play, Check,
  Bug, RotateCw, AlertTriangle,
} from 'lucide-react'
import { systemLogsApi } from '../api/systemLogs'
import type { LogEntry, ActivityEntry, ActivityKategorie } from '../api/systemLogs'

// ─── Shared: Copy-to-Clipboard mit Feedback ─────────────────────────────────

function useCopyFeedback() {
  const [copied, setCopied] = useState(false)
  const copy = useCallback(async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [])
  return { copied, copy }
}

// ─── Shared: Toast-Nachricht ─────────────────────────────────────────────────

function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDone, 3000)
    return () => clearTimeout(timer)
  }, [onDone])

  return (
    <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 text-sm flex items-center gap-2">
      <Check className="h-4 w-4" />
      {message}
    </div>
  )
}

// ─── Tab: System-Logs ──────────────────────────────────────────────────────

function SystemLogsTab() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [level, setLevel] = useState<string>('')
  const [module, setModule] = useState<string>('')
  const [search, setSearch] = useState<string>('')

  const [autoRefresh, setAutoRefresh] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const { copied, copy } = useCopyFeedback()

  const loadLogs = useCallback(async () => {
    try {
      setLoading(true)
      const data = await systemLogsApi.getLogs({
        level: level || undefined,
        module: module || undefined,
        search: search || undefined,
        limit: 500,
      })
      setLogs(data)
      setError(null)
    } catch {
      setError('Fehler beim Laden der Logs')
    } finally {
      setLoading(false)
    }
  }, [level, module, search])

  useEffect(() => { loadLogs() }, [loadLogs])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(loadLogs, 5000)
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, loadLogs])

  const levelColor = (lvl: string) => {
    switch (lvl) {
      case 'ERROR': case 'CRITICAL': return 'text-red-600 dark:text-red-400'
      case 'WARNING': return 'text-amber-600 dark:text-amber-400'
      case 'DEBUG': return 'text-gray-400 dark:text-gray-500'
      default: return 'text-gray-700 dark:text-gray-300'
    }
  }

  const formatLogsMarkdown = () => {
    const filter = [level && `Level: ${level}`, module && `Modul: ${module}`, search && `Suche: "${search}"`].filter(Boolean).join(', ')
    const header = `## EEDC System-Logs${filter ? ` (${filter})` : ''}\n\n`
    const table = '| Zeit | Level | Modul | Nachricht |\n|------|-------|-------|-----------|\n'
    const rows = logs.map((log) => {
      const zeit = new Date(log.timestamp).toLocaleString('de-DE')
      const msg = log.message.replace(/\|/g, '\\|')
      return `| ${zeit} | ${log.level} | ${log.module} | ${msg} |`
    }).join('\n')
    return header + table + rows
  }

  const downloadLogs = () => {
    const lines = logs.map((log) => {
      const zeit = new Date(log.timestamp).toLocaleString('de-DE')
      return `[${zeit}] ${log.level.padEnd(8)} ${log.module.padEnd(24)} ${log.message}`
    }).join('\n')
    const blob = new Blob([lines], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `eedc-system-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        >
          <option value="">Alle Level</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
        <input
          type="text"
          value={module}
          onChange={(e) => setModule(e.target.value)}
          placeholder="Modul..."
          className="w-40 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        />
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Suche in Nachrichten..."
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 pl-9 pr-3 py-2 text-sm"
          />
        </div>
        <button
          onClick={() => copy(formatLogsMarkdown())}
          disabled={logs.length === 0}
          className={`p-2 rounded-lg transition-colors ${
            copied
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
          } disabled:opacity-30`}
          title="Als Markdown kopieren (f\u00fcr GitHub Issue)"
        >
          {copied ? <Check className="h-4 w-4" /> : <ClipboardCopy className="h-4 w-4" />}
        </button>
        <button
          onClick={downloadLogs}
          disabled={logs.length === 0}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
          title="Als Textdatei herunterladen"
        >
          <Download className="h-4 w-4" />
        </button>
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          className={`p-2 rounded-lg transition-colors ${
            autoRefresh
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
          title={autoRefresh ? 'Auto-Refresh stoppen' : 'Auto-Refresh starten (5s)'}
        >
          {autoRefresh ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>
        <button
          onClick={loadLogs}
          disabled={loading}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
          title="Aktualisieren"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Log-Tabelle */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="max-h-[60vh] overflow-y-auto">
          <table className="w-full text-xs font-mono">
            <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0">
              <tr>
                <th className="text-left p-2 w-36 font-medium text-gray-500 dark:text-gray-400">Zeit</th>
                <th className="text-left p-2 w-20 font-medium text-gray-500 dark:text-gray-400">Level</th>
                <th className="text-left p-2 w-36 font-medium text-gray-500 dark:text-gray-400">Modul</th>
                <th className="text-left p-2 font-medium text-gray-500 dark:text-gray-400">Nachricht</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {logs.map((log, i) => (
                <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="p-2 text-gray-500 whitespace-nowrap">
                    {new Date(log.timestamp).toLocaleString('de-DE', {
                      day: '2-digit', month: '2-digit', hour: '2-digit',
                      minute: '2-digit', second: '2-digit',
                    })}
                  </td>
                  <td className={`p-2 font-bold ${levelColor(log.level)}`}>
                    {log.level}
                  </td>
                  <td className="p-2 text-gray-500 truncate max-w-[160px]" title={log.logger_name}>
                    {log.module}
                  </td>
                  <td className="p-2 break-all text-gray-800 dark:text-gray-200">{log.message}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={4} className="p-8 text-center text-gray-400">
                    Keine Log-Eintr\u00e4ge gefunden
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        {logs.length} Eintr\u00e4ge angezeigt (max. 500 im Speicher, gehen bei Restart verloren)
      </p>
    </div>
  )
}

// ─── Tab: Aktivitäten ──────────────────────────────────────────────────────

function AktivitaetenTab() {
  const [activities, setActivities] = useState<ActivityEntry[]>([])
  const [total, setTotal] = useState(0)
  const [kategorien, setKategorien] = useState<ActivityKategorie[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const [kategorie, setKategorie] = useState<string>('')
  const [erfolg, setErfolg] = useState<string>('')
  const [searchInput, setSearchInput] = useState<string>('')
  const [search, setSearch] = useState<string>('')
  const [offset, setOffset] = useState(0)
  const limit = 30
  const { copied, copy } = useCopyFeedback()

  // Debounce: Suche erst nach 400ms Tipp-Pause auslösen
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput)
      setOffset(0)
    }, 400)
    return () => clearTimeout(timer)
  }, [searchInput])

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const data = await systemLogsApi.getActivities({
        kategorie: kategorie || undefined,
        erfolg: erfolg === '' ? undefined : erfolg === 'true',
        search: search || undefined,
        limit,
        offset,
      })
      setActivities(data.items)
      setTotal(data.total)
      setError(null)
    } catch {
      setError('Fehler beim Laden der Aktivit\u00e4ten')
    } finally {
      setLoading(false)
    }
  }, [kategorie, erfolg, search, offset])

  useEffect(() => {
    systemLogsApi.getKategorien().then(setKategorien).catch(() => {})
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  const formatActivitiesMarkdown = () => {
    const filter = [
      kategorie && `Kategorie: ${kategorien.find((k) => k.id === kategorie)?.label || kategorie}`,
      erfolg === 'true' && 'Erfolgreich',
      erfolg === 'false' && 'Fehlgeschlagen',
      search && `Suche: "${search}"`,
    ].filter(Boolean).join(', ')
    const header = `## EEDC Aktivit\u00e4ten${filter ? ` (${filter})` : ''}\n\n`
    const rows = activities.map((a) => {
      const icon = a.erfolg ? '\u2705' : '\u274c'
      const label = kategorien.find((k) => k.id === a.kategorie)?.label || a.kategorie
      const zeit = a.timestamp ? new Date(a.timestamp).toLocaleString('de-DE') : '\u2013'
      const details = a.details ? ` \u2014 ${a.details}` : ''
      return `- ${icon} **${a.aktion}** [${label}]${details} (${zeit})`
    }).join('\n')
    return header + rows
  }

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={kategorie}
          onChange={(e) => { setKategorie(e.target.value); setOffset(0) }}
          className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        >
          <option value="">Alle Kategorien</option>
          {kategorien.map((k) => (
            <option key={k.id} value={k.id}>{k.label}</option>
          ))}
        </select>
        <select
          value={erfolg}
          onChange={(e) => { setErfolg(e.target.value); setOffset(0) }}
          className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        >
          <option value="">Alle Status</option>
          <option value="true">Erfolgreich</option>
          <option value="false">Fehlgeschlagen</option>
        </select>
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Suche in Aktionen..."
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 pl-9 pr-3 py-2 text-sm"
          />
        </div>
        <button
          onClick={() => copy(formatActivitiesMarkdown())}
          disabled={activities.length === 0}
          className={`p-2 rounded-lg transition-colors ${
            copied
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
          } disabled:opacity-30`}
          title="Als Markdown kopieren (f\u00fcr GitHub Issue)"
        >
          {copied ? <Check className="h-4 w-4" /> : <ClipboardCopy className="h-4 w-4" />}
        </button>
        <button
          onClick={async () => {
            if (!confirm('Alte Eintr\u00e4ge (>90 Tage) bereinigen?')) return
            try {
              const before = total
              await systemLogsApi.cleanupActivities()
              await loadData()
              const removed = before - total
              setToast(removed > 0 ? `${removed} alte Eintr\u00e4ge bereinigt` : 'Keine alten Eintr\u00e4ge vorhanden')
            } catch {
              setError('Bereinigung fehlgeschlagen')
            }
          }}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
          title="Alte Eintr\u00e4ge bereinigen (>90 Tage)"
        >
          <Trash2 className="h-4 w-4" />
        </button>
        <button
          onClick={loadData}
          disabled={loading}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
          title="Aktualisieren"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {toast && <Toast message={toast} onDone={() => setToast(null)} />}

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Aktivitäten-Liste */}
      <div className="space-y-2">
        {activities.map((a) => (
          <div
            key={a.id}
            className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50"
          >
            {a.erfolg ? (
              <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {a.aktion}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
                  {kategorien.find((k) => k.id === a.kategorie)?.label || a.kategorie}
                </span>
              </div>
              {a.details && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 break-all">
                  {a.details}
                </p>
              )}
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                {a.timestamp
                  ? new Date(a.timestamp).toLocaleString('de-DE')
                  : '\u2013'}
              </p>
            </div>
          </div>
        ))}
        {activities.length === 0 && !loading && (
          <div className="text-center py-8 text-gray-400 dark:text-gray-500">
            Keine Aktivit\u00e4ten gefunden
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>Seite {currentPage} von {totalPages} ({total} gesamt)</span>
          <div className="flex gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={offset + limit >= total}
              className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────

export default function Protokolle() {
  const [activeTab, setActiveTab] = useState<'logs' | 'activities'>('logs')
  const [logLevel, setLogLevel] = useState<string>('INFO')
  const [restarting, setRestarting] = useState(false)

  useEffect(() => {
    systemLogsApi.getLogLevel().then((r) => setLogLevel(r.level)).catch(() => {})
  }, [])

  const isDebug = logLevel === 'DEBUG'

  const toggleDebug = async () => {
    const newLevel = isDebug ? 'INFO' : 'DEBUG'
    try {
      const result = await systemLogsApi.setLogLevel(newLevel)
      if (result.erfolg) setLogLevel(result.level)
    } catch { /* ignore */ }
  }

  const handleRestart = async () => {
    if (!confirm('EEDC wirklich neu starten? Die Verbindung wird kurz unterbrochen.')) return
    setRestarting(true)
    try {
      await systemLogsApi.restart()
    } catch { /* Verbindung bricht ab — erwartet */ }
  }

  const tabs = [
    { id: 'logs' as const, label: 'System-Logs', icon: ScrollText },
    { id: 'activities' as const, label: 'Aktivit\u00e4ten', icon: Activity },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        <ScrollText className="w-6 h-6 text-gray-500" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Protokolle
        </h1>
        <div className="flex-1" />
        <button
          onClick={toggleDebug}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            isDebug
              ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 ring-1 ring-amber-300 dark:ring-amber-700'
              : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
          title={isDebug ? 'Debug-Modus deaktivieren (zur\u00fcck auf INFO)' : 'Debug-Modus aktivieren (zeigt alle Detail-Meldungen)'}
        >
          <Bug className="h-4 w-4" />
          {isDebug ? 'Debug aktiv' : 'Debug'}
        </button>
        <button
          onClick={handleRestart}
          disabled={restarting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
          title="EEDC neu starten"
        >
          <RotateCw className={`h-4 w-4 ${restarting ? 'animate-spin' : ''}`} />
          {restarting ? 'Startet neu...' : 'Neustart'}
        </button>
      </div>

      {isDebug && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 text-sm">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          Debug-Modus aktiv — alle Detail-Logs werden aufgezeichnet. Erh\u00f6hter Speicherverbrauch. Nach der Fehlersuche wieder deaktivieren.
        </div>
      )}

      {/* Tab Bar */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-700 dark:text-blue-300'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'logs' ? <SystemLogsTab /> : <AktivitaetenTab />}
    </div>
  )
}
