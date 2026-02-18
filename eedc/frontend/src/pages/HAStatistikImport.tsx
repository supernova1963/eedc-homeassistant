/**
 * HAStatistikImport - Bulk-Import von HA-Langzeitstatistiken
 *
 * Ermöglicht den Import aller historischen Monatsdaten aus der
 * Home Assistant Statistik-Datenbank mit Konflikt-Erkennung.
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Database,
  Download,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Info,
  Loader2,
  Calendar,
  ArrowRight,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { anlagenApi, haStatisticsApi } from '../api'
import type { ImportVorschau, MonatImportStatus } from '../api'
import Alert from '../components/ui/Alert'

interface Anlage {
  id: number
  anlagenname: string
}

export default function HAStatistikImport() {
  const navigate = useNavigate()
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlage, setSelectedAnlage] = useState<number | null>(null)

  const [loading, setLoading] = useState(true)
  const [checkingStatus, setCheckingStatus] = useState(false)
  const [loadingVorschau, setLoadingVorschau] = useState(false)
  const [importing, setImporting] = useState(false)

  const [haVerfuegbar, setHaVerfuegbar] = useState<boolean | null>(null)
  const [haFehler, setHaFehler] = useState<string | null>(null)
  const [vorschau, setVorschau] = useState<ImportVorschau | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [ueberschreibenErlauben, setUeberschreibenErlauben] = useState(false)
  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(new Set())

  // Anlagen laden
  useEffect(() => {
    const loadAnlagen = async () => {
      try {
        const data = await anlagenApi.list()
        setAnlagen(data.map(a => ({ id: a.id, anlagenname: a.anlagenname })))
        if (data.length > 0) {
          setSelectedAnlage(data[0].id)
        }
      } catch (e) {
        setError('Fehler beim Laden der Anlagen')
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    loadAnlagen()
  }, [])

  // HA-Status prüfen
  useEffect(() => {
    const checkStatus = async () => {
      setCheckingStatus(true)
      try {
        const status = await haStatisticsApi.getStatus()
        setHaVerfuegbar(status.verfuegbar)
        setHaFehler(status.fehler || null)
      } catch (e) {
        setHaVerfuegbar(false)
        setHaFehler('Fehler bei der Statusprüfung')
        console.error(e)
      } finally {
        setCheckingStatus(false)
      }
    }
    checkStatus()
  }, [])

  // Vorschau laden
  const loadVorschau = async () => {
    if (!selectedAnlage) return

    setLoadingVorschau(true)
    setError(null)
    setVorschau(null)

    try {
      const data = await haStatisticsApi.getImportVorschau(selectedAnlage)
      setVorschau(data)
    } catch (e) {
      setError('Fehler beim Laden der Vorschau')
      console.error(e)
    } finally {
      setLoadingVorschau(false)
    }
  }

  // Import durchführen
  const handleImport = async () => {
    if (!selectedAnlage || !vorschau) return

    setImporting(true)
    setError(null)
    setSuccess(null)

    try {
      const result = await haStatisticsApi.importieren(selectedAnlage, {
        ueberschreiben_erlauben: ueberschreibenErlauben,
      })

      if (result.success) {
        setSuccess(
          `Import erfolgreich: ${result.importiert} Monate importiert` +
          (result.uebersprungen > 0 ? `, ${result.uebersprungen} übersprungen` : '') +
          (result.fehler > 0 ? `, ${result.fehler} Fehler` : '')
        )
        // Vorschau neu laden
        await loadVorschau()
      } else {
        setError(result.message)
      }
    } catch (e) {
      setError('Fehler beim Import')
      console.error(e)
    } finally {
      setImporting(false)
    }
  }

  const toggleMonth = (key: string) => {
    const newExpanded = new Set(expandedMonths)
    if (newExpanded.has(key)) {
      newExpanded.delete(key)
    } else {
      newExpanded.add(key)
    }
    setExpandedMonths(newExpanded)
  }

  const getAktionIcon = (aktion: string) => {
    switch (aktion) {
      case 'importieren':
        return <CheckCircle className="w-4 h-4 text-green-500" />
      case 'ueberspringen':
        return <ArrowRight className="w-4 h-4 text-gray-400" />
      case 'konflikt':
        return <AlertTriangle className="w-4 h-4 text-amber-500" />
      case 'ueberschreiben':
        return <AlertTriangle className="w-4 h-4 text-red-500" />
      default:
        return <Info className="w-4 h-4 text-blue-500" />
    }
  }

  const getAktionBadge = (aktion: string) => {
    const styles: Record<string, string> = {
      importieren: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
      ueberspringen: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
      konflikt: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
      ueberschreiben: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    }
    const labels: Record<string, string> = {
      importieren: 'Importieren',
      ueberspringen: 'Übersprungen',
      konflikt: 'Konflikt',
      ueberschreiben: 'Überschreiben',
    }
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${styles[aktion] || ''}`}>
        {labels[aktion] || aktion}
      </span>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
          <Database className="w-7 h-7 text-primary-500" />
          HA-Statistik Import
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Importiere historische Monatsdaten aus der Home Assistant Langzeitstatistik-Datenbank.
        </p>
      </div>

      {/* HA-Status */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Datenbank-Status
        </h2>

        {checkingStatus ? (
          <div className="flex items-center gap-2 text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin" />
            Prüfe Verbindung...
          </div>
        ) : haVerfuegbar ? (
          <Alert type="success">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5" />
              Home Assistant Datenbank ist verfügbar
            </div>
          </Alert>
        ) : (
          <Alert type="error">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <XCircle className="w-5 h-5" />
                Home Assistant Datenbank nicht verfügbar
              </div>
              {haFehler && <p className="text-sm">{haFehler}</p>}
              <p className="text-sm">
                Stellen Sie sicher, dass das Add-on mit <code>config:ro</code> Volume-Mapping
                installiert ist. Siehe CHANGELOG v2.0.0 für Upgrade-Anleitung.
              </p>
            </div>
          </Alert>
        )}
      </div>

      {/* Anlage auswählen */}
      {haVerfuegbar && (
        <>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Anlage auswählen
            </h2>

            <div className="flex items-end gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Anlage
                </label>
                <select
                  value={selectedAnlage || ''}
                  onChange={(e) => {
                    setSelectedAnlage(Number(e.target.value))
                    setVorschau(null)
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                >
                  {anlagen.map(a => (
                    <option key={a.id} value={a.id}>{a.anlagenname}</option>
                  ))}
                </select>
              </div>

              <button
                onClick={loadVorschau}
                disabled={!selectedAnlage || loadingVorschau}
                className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
              >
                {loadingVorschau ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Lade...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    Vorschau laden
                  </>
                )}
              </button>
            </div>

            {!vorschau && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">
                Wichtig: Stellen Sie sicher, dass das Sensor-Mapping für diese Anlage konfiguriert ist,
                damit die HA-Sensoren den EEDC-Feldern zugeordnet werden können.
              </p>
            )}
          </div>

          {/* Alerts */}
          {error && <Alert type="error" className="mb-6">{error}</Alert>}
          {success && <Alert type="success" className="mb-6">{success}</Alert>}

          {/* Vorschau */}
          {vorschau && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Import-Vorschau
              </h2>

              {/* Statistik */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <StatBox
                  label="Verfügbare Monate"
                  value={vorschau.verfuegbare_monate}
                  color="blue"
                />
                <StatBox
                  label="Zum Import"
                  value={vorschau.zum_import}
                  color="green"
                />
                <StatBox
                  label="Konflikte"
                  value={vorschau.konflikte}
                  color="amber"
                />
                <StatBox
                  label="Übersprungen"
                  value={vorschau.uebersprungen}
                  color="gray"
                />
              </div>

              {/* Optionen */}
              {vorschau.konflikte > 0 && (
                <div className="mb-6 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ueberschreibenErlauben}
                      onChange={(e) => setUeberschreibenErlauben(e.target.checked)}
                      className="w-4 h-4 rounded border-amber-400 text-amber-600 focus:ring-amber-500"
                    />
                    <div>
                      <span className="font-medium text-amber-800 dark:text-amber-200">
                        Vorhandene Daten überschreiben
                      </span>
                      <p className="text-sm text-amber-600 dark:text-amber-400">
                        {vorschau.konflikte} Monate haben bereits manuell erfasste Werte.
                        Diese werden bei aktivierter Option überschrieben.
                      </p>
                    </div>
                  </label>
                </div>
              )}

              {/* Monatsliste */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden mb-6">
                <div className="max-h-96 overflow-y-auto">
                  {vorschau.monate.map((monat) => (
                    <MonatRow
                      key={`${monat.jahr}-${monat.monat}`}
                      monat={monat}
                      expanded={expandedMonths.has(`${monat.jahr}-${monat.monat}`)}
                      onToggle={() => toggleMonth(`${monat.jahr}-${monat.monat}`)}
                      getAktionIcon={getAktionIcon}
                      getAktionBadge={getAktionBadge}
                      ueberschreibenErlauben={ueberschreibenErlauben}
                    />
                  ))}
                </div>
              </div>

              {/* Import Button */}
              <div className="flex justify-end">
                <button
                  onClick={handleImport}
                  disabled={importing || vorschau.zum_import === 0}
                  className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center gap-2 font-medium"
                >
                  {importing ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Importiere...
                    </>
                  ) : (
                    <>
                      <Download className="w-5 h-5" />
                      {vorschau.zum_import + (ueberschreibenErlauben ? vorschau.konflikte : 0)} Monate importieren
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Navigation */}
      <div className="flex justify-between mt-8">
        <button
          onClick={() => navigate('/einstellungen/sensor-mapping')}
          className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        >
          ← Zurück zu Sensor-Zuordnung
        </button>
        <button
          onClick={() => navigate('/einstellungen/monatsdaten')}
          className="text-primary-600 hover:text-primary-700"
        >
          Zu Monatsdaten →
        </button>
      </div>
    </div>
  )
}

// =============================================================================
// Helper Components
// =============================================================================

function StatBox({
  label,
  value,
  color,
}: {
  label: string
  value: number
  color: 'blue' | 'green' | 'amber' | 'gray'
}) {
  const colors = {
    blue: 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400',
    green: 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400',
    amber: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400',
    gray: 'bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
  }

  return (
    <div className={`p-4 rounded-lg ${colors[color]}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm">{label}</div>
    </div>
  )
}

function MonatRow({
  monat,
  expanded,
  onToggle,
  getAktionIcon,
  getAktionBadge,
  ueberschreibenErlauben,
}: {
  monat: MonatImportStatus
  expanded: boolean
  onToggle: () => void
  getAktionIcon: (aktion: string) => React.ReactNode
  getAktionBadge: (aktion: string) => React.ReactNode
  ueberschreibenErlauben: boolean
}) {
  // Bei Konflikten: Zeige "überschreiben" wenn erlaubt, sonst "konflikt"
  const effektiveAktion = monat.aktion === 'konflikt' && ueberschreibenErlauben
    ? 'ueberschreiben'
    : monat.aktion

  const hasDetails = Object.keys(monat.ha_werte).length > 0 ||
    (monat.vorhandene_werte && Object.keys(monat.vorhandene_werte).length > 0)

  return (
    <div className="border-b border-gray-100 dark:border-gray-700 last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          {hasDetails ? (
            expanded ? (
              <ChevronDown className="w-4 h-4 text-gray-400" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-400" />
            )
          ) : (
            <div className="w-4" />
          )}
          <Calendar className="w-4 h-4 text-gray-400" />
          <span className="font-medium text-gray-900 dark:text-white">
            {monat.monat_name} {monat.jahr}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {getAktionIcon(effektiveAktion)}
          {getAktionBadge(effektiveAktion)}
        </div>
      </button>

      {expanded && hasDetails && (
        <div className="px-4 pb-4 pt-2 bg-gray-50 dark:bg-gray-700/30">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            {monat.grund}
          </p>

          {/* HA-Werte */}
          {Object.keys(monat.ha_werte).length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
                Werte aus HA-Statistik
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(monat.ha_werte).map(([key, value]) => (
                  <div
                    key={key}
                    className="text-sm bg-white dark:bg-gray-800 px-2 py-1 rounded"
                  >
                    <span className="text-gray-500 dark:text-gray-400">{key}:</span>{' '}
                    <span className="font-medium text-gray-900 dark:text-white">
                      {value !== null ? value.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Vorhandene Werte bei Konflikt */}
          {monat.vorhandene_werte && Object.keys(monat.vorhandene_werte).length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-amber-600 dark:text-amber-400 uppercase mb-2">
                Vorhandene Werte (werden {ueberschreibenErlauben ? 'überschrieben' : 'beibehalten'})
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(monat.vorhandene_werte).map(([key, value]) => (
                  <div
                    key={key}
                    className="text-sm bg-amber-50 dark:bg-amber-900/20 px-2 py-1 rounded"
                  >
                    <span className="text-amber-600 dark:text-amber-400">{key}:</span>{' '}
                    <span className="font-medium text-amber-800 dark:text-amber-200">
                      {value !== null ? value.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
