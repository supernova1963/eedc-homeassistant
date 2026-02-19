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
import type { MonatFeldAuswahl } from '../api/haStatistics'
import Alert from '../components/ui/Alert'

interface Anlage {
  id: number
  anlagenname: string
}

// Import-Modus für schnelle Auswahl
type ImportModus = 'alle' | 'nur_basis' | 'nur_komponenten' | 'manuell'

// Feld-Auswahl State pro Monat
interface FeldAuswahl {
  basis: Set<string>  // Ausgewählte Basis-Felder
  investitionen: Map<number, Set<string>>  // inv_id -> Set von Feldern
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

  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(new Set())
  // Ausgewählte Monate für Import: Map von "jahr-monat" -> boolean
  const [selectedMonths, setSelectedMonths] = useState<Map<string, boolean>>(new Map())
  // Import-Modus
  const [importModus, setImportModus] = useState<ImportModus>('alle')
  // Feld-Auswahl pro Monat: Map von "jahr-monat" -> FeldAuswahl
  const [feldAuswahl, setFeldAuswahl] = useState<Map<string, FeldAuswahl>>(new Map())

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
    setSelectedMonths(new Map())
    setFeldAuswahl(new Map())

    try {
      const data = await haStatisticsApi.getImportVorschau(selectedAnlage)
      setVorschau(data)

      // Initialisiere Auswahl: "importieren" und "konflikt" sind standardmäßig ausgewählt
      const initialSelection = new Map<string, boolean>()
      const initialFeldAuswahl = new Map<string, FeldAuswahl>()

      data.monate.forEach(m => {
        const key = `${m.jahr}-${m.monat}`
        // Standardmäßig ausgewählt wenn importierbar oder Konflikt
        initialSelection.set(key, m.aktion === 'importieren' || m.aktion === 'konflikt')

        // Feld-Auswahl initialisieren: Alle Felder standardmäßig ausgewählt
        const basis = new Set<string>(Object.keys(m.ha_werte))
        const investitionen = new Map<number, Set<string>>()

        if (m.investitionen) {
          m.investitionen.forEach(inv => {
            investitionen.set(inv.investition_id, new Set(Object.keys(inv.ha_werte)))
          })
        }

        initialFeldAuswahl.set(key, { basis, investitionen })
      })

      setSelectedMonths(initialSelection)
      setFeldAuswahl(initialFeldAuswahl)
    } catch (e) {
      setError('Fehler beim Laden der Vorschau')
      console.error(e)
    } finally {
      setLoadingVorschau(false)
    }
  }

  // Monat auswählen/abwählen
  const toggleMonthSelection = (jahr: number, monat: number) => {
    const key = `${jahr}-${monat}`
    const newSelection = new Map(selectedMonths)
    newSelection.set(key, !newSelection.get(key))
    setSelectedMonths(newSelection)
  }

  // Basis-Feld Auswahl umschalten
  const toggleBasisFeld = (jahr: number, monat: number, feld: string) => {
    const key = `${jahr}-${monat}`
    const newFeldAuswahl = new Map(feldAuswahl)
    const current = newFeldAuswahl.get(key) || { basis: new Set(), investitionen: new Map() }
    const newBasis = new Set(current.basis)

    if (newBasis.has(feld)) {
      newBasis.delete(feld)
    } else {
      newBasis.add(feld)
    }

    newFeldAuswahl.set(key, { ...current, basis: newBasis })
    setFeldAuswahl(newFeldAuswahl)
    setImportModus('manuell')
  }

  // Investitions-Feld Auswahl umschalten
  const toggleInvestitionFeld = (jahr: number, monat: number, invId: number, feld: string) => {
    const key = `${jahr}-${monat}`
    const newFeldAuswahl = new Map(feldAuswahl)
    const current = newFeldAuswahl.get(key) || { basis: new Set(), investitionen: new Map() }
    const newInvestitionen = new Map(current.investitionen)
    const invFelder = new Set(newInvestitionen.get(invId) || [])

    if (invFelder.has(feld)) {
      invFelder.delete(feld)
    } else {
      invFelder.add(feld)
    }

    newInvestitionen.set(invId, invFelder)
    newFeldAuswahl.set(key, { ...current, investitionen: newInvestitionen })
    setFeldAuswahl(newFeldAuswahl)
    setImportModus('manuell')
  }

  // Import-Modus ändern und Feld-Auswahl entsprechend anpassen
  const changeImportModus = (modus: ImportModus) => {
    setImportModus(modus)
    if (!vorschau) return

    const newFeldAuswahl = new Map<string, FeldAuswahl>()

    vorschau.monate.forEach(m => {
      const key = `${m.jahr}-${m.monat}`
      let basis = new Set<string>()
      const investitionen = new Map<number, Set<string>>()

      switch (modus) {
        case 'alle':
          // Alle Felder auswählen
          basis = new Set(Object.keys(m.ha_werte))
          m.investitionen?.forEach(inv => {
            investitionen.set(inv.investition_id, new Set(Object.keys(inv.ha_werte)))
          })
          break
        case 'nur_basis':
          // Nur Basis-Felder
          basis = new Set(Object.keys(m.ha_werte))
          break
        case 'nur_komponenten':
          // Nur Komponenten-Felder
          m.investitionen?.forEach(inv => {
            investitionen.set(inv.investition_id, new Set(Object.keys(inv.ha_werte)))
          })
          break
        case 'manuell':
          // Nichts ändern, wird durch einzelne Checkboxen gesteuert
          const existing = feldAuswahl.get(key)
          if (existing) {
            newFeldAuswahl.set(key, existing)
            return
          }
          break
      }

      newFeldAuswahl.set(key, { basis, investitionen })
    })

    setFeldAuswahl(newFeldAuswahl)
  }

  // Berechne Anzahl ausgewählter Monate
  const selectedCount = vorschau?.monate.filter(m => {
    const key = `${m.jahr}-${m.monat}`
    return selectedMonths.get(key) && m.aktion !== 'ueberspringen'
  }).length || 0

  // Import durchführen
  const handleImport = async () => {
    if (!selectedAnlage || !vorschau) return

    // Nur ausgewählte Monate mit Feld-Auswahl importieren
    const ausgewaehlte: MonatFeldAuswahl[] = vorschau.monate
      .filter(m => {
        const key = `${m.jahr}-${m.monat}`
        return selectedMonths.get(key) && m.aktion !== 'ueberspringen'
      })
      .map(m => {
        const key = `${m.jahr}-${m.monat}`
        const auswahl = feldAuswahl.get(key)

        // Basis-Felder: Konvertiere Set zu Array
        const basisFelder = auswahl?.basis.size ? Array.from(auswahl.basis) : []

        // Investitions-Felder: Konvertiere Map<number, Set> zu Record<string, string[]>
        const invFelder: Record<string, string[]> = {}
        auswahl?.investitionen.forEach((felder, invId) => {
          if (felder.size > 0) {
            invFelder[String(invId)] = Array.from(felder)
          }
        })

        return {
          jahr: m.jahr,
          monat: m.monat,
          basis_felder: basisFelder.length > 0 ? basisFelder : [],
          investition_felder: Object.keys(invFelder).length > 0 ? invFelder : {}
        }
      })
      // Filtere Monate ohne ausgewählte Felder
      .filter(m =>
        (m.basis_felder && m.basis_felder.length > 0) ||
        (m.investition_felder && Object.keys(m.investition_felder).length > 0)
      )

    if (ausgewaehlte.length === 0) {
      setError('Keine Felder zum Import ausgewählt')
      return
    }

    setImporting(true)
    setError(null)
    setSuccess(null)

    try {
      const result = await haStatisticsApi.importieren(selectedAnlage, {
        monate: ausgewaehlte,
        ueberschreiben: true, // Ausgewählte Konflikte sollen überschrieben werden
      })

      if (result.erfolg) {
        setSuccess(
          `Import erfolgreich: ${result.importiert} Monate importiert` +
          (result.uebersprungen > 0 ? `, ${result.uebersprungen} übersprungen` : '') +
          (result.ueberschrieben > 0 ? `, ${result.ueberschrieben} überschrieben` : '') +
          (result.fehler.length > 0 ? `, ${result.fehler.length} Fehler` : '')
        )
        // Vorschau neu laden
        await loadVorschau()
      } else {
        setError(result.fehler.join(', ') || 'Import fehlgeschlagen')
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
                  value={vorschau.anzahl_monate}
                  color="blue"
                />
                <StatBox
                  label="Zum Import"
                  value={vorschau.anzahl_importieren}
                  color="green"
                />
                <StatBox
                  label="Konflikte"
                  value={vorschau.anzahl_konflikte}
                  color="amber"
                />
                <StatBox
                  label="Übersprungen"
                  value={vorschau.anzahl_ueberspringen}
                  color="gray"
                />
              </div>

              {/* Import-Modus Auswahl */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Import-Modus
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => changeImportModus('alle')}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      importModus === 'alle'
                        ? 'bg-primary-100 border-primary-500 text-primary-700 dark:bg-primary-900/30 dark:border-primary-400 dark:text-primary-300'
                        : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:border-gray-400'
                    }`}
                  >
                    Alles importieren
                  </button>
                  <button
                    onClick={() => changeImportModus('nur_basis')}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      importModus === 'nur_basis'
                        ? 'bg-primary-100 border-primary-500 text-primary-700 dark:bg-primary-900/30 dark:border-primary-400 dark:text-primary-300'
                        : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:border-gray-400'
                    }`}
                  >
                    Nur Basis (Einspeisung/Netzbezug)
                  </button>
                  <button
                    onClick={() => changeImportModus('nur_komponenten')}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      importModus === 'nur_komponenten'
                        ? 'bg-primary-100 border-primary-500 text-primary-700 dark:bg-primary-900/30 dark:border-primary-400 dark:text-primary-300'
                        : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:border-gray-400'
                    }`}
                  >
                    Nur Komponenten
                  </button>
                  {importModus === 'manuell' && (
                    <span className="px-3 py-1.5 text-sm rounded-lg bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                      Manuell (individuelle Auswahl)
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Klicken Sie auf einzelne Felder in der Vorschau, um die Auswahl anzupassen.
                </p>
              </div>

              {/* Hinweis zur Auswahl */}
              <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  <strong>Hinweis:</strong> Wählen Sie die Monate und Felder aus, die importiert werden sollen.
                  Bei Konflikten (gelb markiert) werden nur die ausgewählten Felder überschrieben.
                </p>
              </div>

              {/* Monatsliste */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden mb-6">
                <div className="max-h-96 overflow-y-auto">
                  {vorschau.monate.map((monat) => {
                    const key = `${monat.jahr}-${monat.monat}`
                    return (
                      <MonatRow
                        key={key}
                        monat={monat}
                        expanded={expandedMonths.has(key)}
                        onToggle={() => toggleMonth(key)}
                        getAktionIcon={getAktionIcon}
                        getAktionBadge={getAktionBadge}
                        selected={selectedMonths.get(key) || false}
                        onSelectionChange={() => toggleMonthSelection(monat.jahr, monat.monat)}
                        feldAuswahl={feldAuswahl.get(key)}
                        onToggleBasisFeld={(feld) => toggleBasisFeld(monat.jahr, monat.monat, feld)}
                        onToggleInvFeld={(invId, feld) => toggleInvestitionFeld(monat.jahr, monat.monat, invId, feld)}
                      />
                    )
                  })}
                </div>
              </div>

              {/* Import Button */}
              <div className="flex justify-end">
                <button
                  onClick={handleImport}
                  disabled={importing || selectedCount === 0}
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
                      {selectedCount} Monate importieren
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
  selected,
  onSelectionChange,
  feldAuswahl,
  onToggleBasisFeld,
  onToggleInvFeld,
}: {
  monat: MonatImportStatus
  expanded: boolean
  onToggle: () => void
  getAktionIcon: (aktion: string) => React.ReactNode
  getAktionBadge: (aktion: string) => React.ReactNode
  selected: boolean
  onSelectionChange: () => void
  feldAuswahl?: FeldAuswahl
  onToggleBasisFeld: (feld: string) => void
  onToggleInvFeld: (invId: number, feld: string) => void
}) {
  // Kann dieser Monat ausgewählt werden?
  const canSelect = monat.aktion !== 'ueberspringen'

  const hasDetails = Object.keys(monat.ha_werte).length > 0 ||
    (monat.vorhandene_werte && Object.keys(monat.vorhandene_werte).length > 0) ||
    (monat.investitionen && monat.investitionen.length > 0)

  return (
    <div className="border-b border-gray-100 dark:border-gray-700 last:border-b-0">
      <div className="flex items-center">
        {/* Checkbox */}
        <div className="px-3 py-3">
          {canSelect ? (
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => {
                e.stopPropagation()
                onSelectionChange()
              }}
              className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
          ) : (
            <div className="w-4 h-4" />
          )}
        </div>

        {/* Rest der Zeile */}
        <button
          onClick={onToggle}
          className="flex-1 px-2 py-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
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
            {getAktionIcon(monat.aktion)}
            {getAktionBadge(monat.aktion)}
          </div>
        </button>
      </div>

      {expanded && hasDetails && (
        <div className="px-4 pb-4 pt-2 bg-gray-50 dark:bg-gray-700/30">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            {monat.grund}
          </p>

          {/* Basis-Werte Vergleichstabelle */}
          {(Object.keys(monat.ha_werte).length > 0 || (monat.vorhandene_werte && Object.keys(monat.vorhandene_werte).length > 0)) && (
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
                Basis-Werte
              </h4>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-600">
                      <th className="w-8 py-1"></th>
                      <th className="text-left py-1 pr-4 font-medium text-gray-600 dark:text-gray-300">Feld</th>
                      <th className="text-right py-1 px-2 font-medium text-gray-600 dark:text-gray-300">Vorhanden</th>
                      <th className="text-right py-1 px-2 font-medium text-blue-600 dark:text-blue-400">HA-Statistik</th>
                      <th className="text-right py-1 pl-2 font-medium text-gray-600 dark:text-gray-300">Diff</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(monat.ha_werte).map(key => {
                      const haWert = monat.ha_werte[key]
                      const vorhWert = monat.vorhandene_werte?.[key] ?? null
                      const diff = haWert !== null && vorhWert !== null ? haWert - vorhWert : null
                      const hatAbweichung = diff !== null && Math.abs(diff) >= 1
                      const isSelected = feldAuswahl?.basis.has(key) ?? true
                      return (
                        <tr
                          key={key}
                          className={`border-b border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600/50 ${
                            hatAbweichung ? 'bg-amber-50/50 dark:bg-amber-900/10' : ''
                          } ${!isSelected ? 'opacity-50' : ''}`}
                          onClick={() => onToggleBasisFeld(key)}
                        >
                          <td className="py-1 pl-2">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {}}
                              className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            />
                          </td>
                          <td className="py-1 pr-4 text-gray-700 dark:text-gray-300">{key}</td>
                          <td className="py-1 px-2 text-right text-gray-600 dark:text-gray-400">
                            {vorhWert !== null && vorhWert !== undefined ? vorhWert.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                          </td>
                          <td className="py-1 px-2 text-right font-medium text-blue-700 dark:text-blue-300">
                            {haWert !== null ? haWert.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                          </td>
                          <td className={`py-1 pl-2 text-right ${hatAbweichung ? 'font-medium text-amber-600 dark:text-amber-400' : 'text-gray-500'}`}>
                            {diff !== null ? (diff >= 0 ? '+' : '') + diff.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Komponenten-Werte */}
          {monat.investitionen && monat.investitionen.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Komponenten
              </h4>
              {monat.investitionen.map(inv => {
                const invFelder = feldAuswahl?.investitionen.get(inv.investition_id)
                return (
                  <div
                    key={inv.investition_id}
                    className={`rounded-lg border p-3 ${
                      inv.hat_abweichung
                        ? 'border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-900/10'
                        : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-medium text-gray-900 dark:text-white text-sm">
                        {inv.bezeichnung}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
                        {inv.typ}
                      </span>
                      {inv.hat_abweichung && (
                        <AlertTriangle className="w-4 h-4 text-amber-500" />
                      )}
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-200 dark:border-gray-600">
                            <th className="w-8 py-1"></th>
                            <th className="text-left py-1 pr-4 font-medium text-gray-600 dark:text-gray-300">Feld</th>
                            <th className="text-right py-1 px-2 font-medium text-gray-600 dark:text-gray-300">Vorhanden</th>
                            <th className="text-right py-1 px-2 font-medium text-blue-600 dark:text-blue-400">HA-Statistik</th>
                            <th className="text-right py-1 pl-2 font-medium text-gray-600 dark:text-gray-300">Diff</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.keys(inv.ha_werte).map(key => {
                            const haWert = inv.ha_werte[key]
                            const vorhWert = inv.vorhandene_werte[key]
                            const diff = haWert !== null && vorhWert !== null ? haWert - vorhWert : null
                            const hatAbweichung = diff !== null && Math.abs(diff) >= 1
                            const isSelected = invFelder?.has(key) ?? true
                            return (
                              <tr
                                key={key}
                                className={`cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600/50 ${
                                  hatAbweichung ? 'bg-amber-50/30 dark:bg-amber-900/5' : ''
                                } ${!isSelected ? 'opacity-50' : ''}`}
                                onClick={() => onToggleInvFeld(inv.investition_id, key)}
                              >
                                <td className="py-1 pl-2">
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => {}}
                                    className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                                  />
                                </td>
                                <td className="py-1 pr-4 text-gray-700 dark:text-gray-300">{key}</td>
                                <td className="py-1 px-2 text-right text-gray-600 dark:text-gray-400">
                                  {vorhWert !== null && vorhWert !== undefined ? vorhWert.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                                </td>
                                <td className="py-1 px-2 text-right font-medium text-blue-700 dark:text-blue-300">
                                  {haWert !== null ? haWert.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                                </td>
                                <td className={`py-1 pl-2 text-right ${hatAbweichung ? 'font-medium text-amber-600 dark:text-amber-400' : 'text-gray-500'}`}>
                                  {diff !== null ? (diff >= 0 ? '+' : '') + diff.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
