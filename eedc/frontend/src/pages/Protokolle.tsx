/**
 * Protokolle – System-Logs + Aktivitätsprotokoll
 *
 * Zwei-Tab-Seite unter System im Einstellungen-Menü.
 * Tab 1: Echtzeit-Logviewer (Ring Buffer, auto-refresh)
 * Tab 2: Persistentes Aktivitätsprotokoll (SQLite, filterbar)
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ScrollText, Activity, RefreshCw, Search,
  CheckCircle, XCircle, ChevronLeft, ChevronRight, Pause, Play,
} from 'lucide-react'
import { systemLogsApi } from '../api/systemLogs'
import type { LogEntry, ActivityEntry, ActivityKategorie } from '../api/systemLogs'

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

  const loadLogs = useCallback(async () => {
    try {
      setLoading(true)
      const data = await systemLogsApi.getLogs({
        level: level || undefined,
        module: module || undefined,
        search: search || undefined,
        limit: 300,
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
                    Keine Log-Einträge gefunden
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        {logs.length} Einträge angezeigt (max. 500 im Speicher, gehen bei Restart verloren)
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

  const [kategorie, setKategorie] = useState<string>('')
  const [erfolg, setErfolg] = useState<string>('')
  const [offset, setOffset] = useState(0)
  const limit = 30

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const data = await systemLogsApi.getActivities({
        kategorie: kategorie || undefined,
        erfolg: erfolg === '' ? undefined : erfolg === 'true',
        limit,
        offset,
      })
      setActivities(data.items)
      setTotal(data.total)
      setError(null)
    } catch {
      setError('Fehler beim Laden der Aktivitäten')
    } finally {
      setLoading(false)
    }
  }, [kategorie, erfolg, offset])

  useEffect(() => {
    systemLogsApi.getKategorien().then(setKategorien).catch(() => {})
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

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
        <div className="flex-1" />
        <button
          onClick={loadData}
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
                  : '–'}
              </p>
            </div>
          </div>
        ))}
        {activities.length === 0 && !loading && (
          <div className="text-center py-8 text-gray-400 dark:text-gray-500">
            Keine Aktivitäten gefunden
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

  const tabs = [
    { id: 'logs' as const, label: 'System-Logs', icon: ScrollText },
    { id: 'activities' as const, label: 'Aktivitäten', icon: Activity },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ScrollText className="w-6 h-6 text-gray-500" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Protokolle
        </h1>
      </div>

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
