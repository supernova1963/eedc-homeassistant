import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, BarChart3, History, RefreshCw, Trash2, Loader2, Info, AlertCircle, Fuel } from 'lucide-react'
import { Button, Card, Alert, Select, EmptyState } from '../components/ui'
import { PageHeader, DataLoadingState } from '../components/common'
import { useSelectedAnlage } from '../hooks'
import { energieProfilApi, type KraftstoffpreisStatus, type AnlageStats } from '../api/energie_profil'
import EnergieprofilTageTabelle from '../components/energieprofil/EnergieprofilTageTabelle'

export default function Energieprofil() {
  const navigate = useNavigate()
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  const [stats, setStats] = useState<AnlageStats | null>(null)
  const [kpStatus, setKpStatus] = useState<KraftstoffpreisStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [overwrite, setOverwrite] = useState(false)
  const [runningBackfill, setRunningBackfill] = useState(false)
  const [runningKraftstoff, setRunningKraftstoff] = useState(false)
  const [runningDelete, setRunningDelete] = useState(false)

  const loadStats = useCallback(async () => {
    if (!selectedAnlageId) { setStats(null); setLoading(false); return }
    try {
      setLoading(true)
      setError(null)
      const s = await energieProfilApi.getAnlageStats(selectedAnlageId)
      setStats(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Statistik')
    } finally {
      setLoading(false)
    }
  }, [selectedAnlageId])

  const loadKraftstoffStatus = useCallback(async () => {
    if (!selectedAnlageId) {
      setKpStatus(null)
      return
    }
    try {
      const s = await energieProfilApi.getKraftstoffpreisStatus(selectedAnlageId)
      setKpStatus(s)
    } catch {
      setKpStatus(null)
    }
  }, [selectedAnlageId])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadKraftstoffStatus() }, [loadKraftstoffStatus])

  const handleVollbackfill = async () => {
    if (!selectedAnlageId) return
    const modus = overwrite ? 'überschreiben' : 'Lücken füllen'
    if (!window.confirm(`Vollbackfill aus HA-Statistik starten (${modus})? Das kann einige Minuten dauern.`)) return
    try {
      setRunningBackfill(true)
      setMessage(null)
      setError(null)
      const res = await energieProfilApi.vollbackfill(selectedAnlageId, overwrite)
      setMessage(`Vollbackfill: ${res.geschrieben} von ${res.verarbeitet} Tagen (${res.von} bis ${res.bis}).`)
      await loadStats()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vollbackfill fehlgeschlagen')
    } finally {
      setRunningBackfill(false)
    }
  }

  const handleKraftstoffBackfill = async () => {
    if (!selectedAnlageId) return
    try {
      setRunningKraftstoff(true)
      setMessage(null)
      setError(null)
      const res = await energieProfilApi.kraftstoffpreisBackfillTages(selectedAnlageId)
      setMessage(
        res.aktualisiert > 0
          ? `${res.aktualisiert} Tage mit Kraftstoffpreis (${res.land}) befüllt.`
          : (res.hinweis || 'Keine offenen Tage.')
      )
      await loadKraftstoffStatus()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kraftstoffpreis-Backfill fehlgeschlagen')
    } finally {
      setRunningKraftstoff(false)
    }
  }

  const handleDeleteProfildaten = async () => {
    if (!selectedAnlageId) return
    const anlage = anlagen.find(a => a.id === selectedAnlageId)
    const name = anlage?.anlagenname ?? `Anlage ${selectedAnlageId}`
    if (!window.confirm(`Alle Energieprofil-Daten für "${name}" löschen? Der Scheduler berechnet sie neu (max. 15 Min). Monatsdaten bleiben erhalten.`)) return
    try {
      setRunningDelete(true)
      setMessage(null)
      setError(null)
      const res = await energieProfilApi.deleteRohdatenAnlage(selectedAnlageId)
      setMessage(`${res.geloescht_stundenwerte} Stundenwerte + ${res.geloescht_tagessummen} Tagessummen gelöscht. Scheduler berechnet neu (max. 15 Min).`)
      await loadStats()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Löschen fehlgeschlagen')
    } finally {
      setRunningDelete(false)
    }
  }

  if (anlagenLoading || loading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Energieprofil" />
        <Card>
          <EmptyState
            icon={AlertCircle}
            title="Keine Anlage vorhanden"
            description="Bitte lege zuerst eine Anlage an, bevor du das Energieprofil verwalten kannst."
            action={<Button onClick={() => navigate('/einstellungen/anlage')}>Zur Anlagen-Verwaltung</Button>}
          />
        </Card>
      </div>
    )
  }

  const hatProfildaten = !!stats && (stats.stundenwerte > 0 || stats.tageszusammenfassungen > 0)

  return (
    <div className="space-y-6">
      <PageHeader title="Energieprofil">
        <Select
          value={selectedAnlageId?.toString() || ''}
          onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
          options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
        />
        <Button variant="secondary" onClick={() => { loadStats(); loadKraftstoffStatus() }} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </PageHeader>

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}

      {/* Datenbestand */}
      {hatProfildaten && stats && (
        <Card>
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <BarChart3 className="h-6 w-6 text-emerald-500" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Datenbestand (pro Anlage)
              </h2>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {stats.stundenwerte.toLocaleString('de-DE')}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Stundenwerte</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">24 pro Tag</p>
              </div>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {stats.tageszusammenfassungen.toLocaleString('de-DE')}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Tagessummen</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">1 pro Tag</p>
              </div>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {stats.monatswerte.toLocaleString('de-DE')}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Monatswerte</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">1 pro Monat</p>
              </div>
            </div>

            {stats.zeitraum && (
              <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    Abdeckung: {stats.zeitraum.tage_mit_daten} von {stats.zeitraum.tage_gesamt} Tagen
                  </span>
                  <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
                    {stats.zeitraum.abdeckung_prozent}%
                  </span>
                </div>
                <div className="w-full bg-emerald-200 dark:bg-emerald-800 rounded-full h-2">
                  <div
                    className="bg-emerald-500 h-2 rounded-full transition-all"
                    style={{ width: `${Math.min(100, stats.zeitraum.abdeckung_prozent)}%` }}
                  />
                </div>
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                  {stats.zeitraum.von} bis {stats.zeitraum.bis}
                </p>
              </div>
            )}

            {stats.wachstum_pro_monat > 0 && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex gap-2">
                <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  Wachstum: ~{stats.wachstum_pro_monat.toLocaleString('de-DE')} Zeilen/Monat
                  (25 Zeilen/Tag × 30 Tage)
                </p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Tages-Energieprofile */}
      {selectedAnlageId && <EnergieprofilTageTabelle anlageId={selectedAnlageId} />}

      {/* Datenverwaltung */}
      <Card>
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <Activity className="h-6 w-6 text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Datenverwaltung
            </h2>
          </div>

          {/* Vollbackfill / Verlauf nachberechnen */}
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4">
            <div className="flex items-start gap-3">
              <History className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-medium text-gray-900 dark:text-white">
                  Verlauf aus HA-Statistik nachberechnen
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Füllt Tagesprofile und Tageszusammenfassungen aus den HA Long-Term Statistics
                  für die gesamte verfügbare Historie (unabhängig von der ~10-Tage-Sensor-Grenze).
                </p>

                <div className="mt-3 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    <strong>Empfohlen nach Updates,</strong> die die Energieprofil-Berechnung
                    betreffen (Zähler-Snapshots, Slot-Konvention, Performance Ratio o.ä.).
                    Das Energieprofil wird aus kumulativen Zählerständen berechnet (exakt
                    zum Live Dashboard); ältere Tage können durch Korrekturen abweichen.
                    Starte dann einmalig mit aktivierter Option <em>„Bestehende Tage
                    überschreiben"</em>, damit der gesamte Verlauf konsistent bleibt.
                    Details im CHANGELOG. Der Daten-Checker zeigt unter
                    „Energieprofil-Abdeckung", welche Zähler dafür gemappt sein müssen.
                  </p>
                </div>

                <label className="flex items-center gap-2 mt-3 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(e) => setOverwrite(e.target.checked)}
                    className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                  Bestehende Tage überschreiben (statt nur Lücken füllen)
                </label>
                <div className="mt-3">
                  <Button
                    onClick={handleVollbackfill}
                    disabled={!selectedAnlageId || runningBackfill}
                  >
                    {runningBackfill ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <History className="h-4 w-4 mr-2" />}
                    {overwrite ? 'Verlauf nachberechnen' : 'Vollbackfill starten'}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Kraftstoffpreis-Tages-Backfill */}
          {kpStatus && kpStatus.tages_offen > 0 && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4">
              <div className="flex items-start gap-3">
                <Fuel className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    Kraftstoffpreise nachpflegen (Tages-Ebene)
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {kpStatus.tages_offen.toLocaleString('de-DE')} Tage ohne Kraftstoffpreis.
                    Lädt EU Oil Bulletin Wochenpreise (Euro-Super 95, {kpStatus.land}) in die
                    Tageszusammenfassung.
                  </p>
                  <div className="mt-3">
                    <Button
                      variant="secondary"
                      onClick={handleKraftstoffBackfill}
                      disabled={runningKraftstoff}
                    >
                      {runningKraftstoff ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Fuel className="h-4 w-4 mr-2" />}
                      Kraftstoffpreise nachpflegen
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Energieprofil-Daten löschen (Gefahrenbereich) */}
          {hatProfildaten && (
            <div className="border border-red-200 dark:border-red-800 rounded-lg p-4 bg-red-50/50 dark:bg-red-900/10">
              <div className="flex items-start gap-3">
                <Trash2 className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="font-medium text-red-700 dark:text-red-300">
                    Energieprofil-Daten löschen
                  </h3>
                  <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                    Entfernt alle Stundenwerte und Tageszusammenfassungen. Der Scheduler
                    berechnet sie neu (max. 15 Min). Monatsdaten bleiben erhalten.
                  </p>
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleDeleteProfildaten}
                      disabled={runningDelete}
                      className="flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 disabled:opacity-50"
                    >
                      {runningDelete ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                      Energieprofil-Daten löschen
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
