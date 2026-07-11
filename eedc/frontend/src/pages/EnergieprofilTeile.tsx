/**
 * Energieprofil — geteilte Teile (nur die PFLEGE-Funktionen).
 *
 * EINE Code-Wahrheit für IST (`pages/Energieprofil.tsx`, dünner Komposer) und
 * IA-V4 (Einstellungen-Katalog-Block „Energieprofil-Pflege", inline wie
 * Monatsdaten/Daten-Checker). **Anzeige ≠ Pflege** (Plan §6): die Tages-Tabelle
 * (`EnergieprofilTageTabelle`) ist ANZEIGE und wandert zu den Zeit-Sichten — sie
 * ist hier NICHT enthalten, sondern wird von der V3-Seite als `tabelleSlot`
 * gereicht (bleibt in V3 an ihrer Stelle, fehlt im V4-Pflege-Block). Der Block
 * trägt: Datenbestand-Status · Lücken-Backfill · Kraftstoffpreis-Backfill ·
 * Löschen · Reparatur-Werkbank. Zahlen de-DE über `fmtZahl`.
 *
 * D14-8 (detLAN #113/#123, Gernot #128 + Gating-Entscheid 2026-07-03): unter
 * `/v4` ist die „Datenverwaltung"-Karte (Lücken/Kraftstoff/Löschen) ausgeblendet
 * — dort läuft alles über das Auswahlfeld der EINEN Reparatur-Werkbank; der
 * Datenbestand ist parkbare Info. V3 bleibt unverändert (IST-Anzeige).
 */
import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { Activity, BarChart3, History, RefreshCw, Trash2, Loader2, Info, Fuel } from 'lucide-react'
import { Button, Card, Alert } from '../components/ui'
import { Parkbar } from '../components/park'
import { useInvestitionen, useV4Basis } from '../hooks'
import { energieProfilApi, type KraftstoffpreisStatus, type AnlageStats } from '../api/energie_profil'
import RepairWorkbench from '../components/repair/RepairWorkbench'
import { fmtZahl } from '../lib'

/**
 * Voller Energieprofil-PFLEGE-Block. Wird von der IST-Seite (V3-Hülle) und dem
 * V4-Daten-Block geteilt. `anlageId` ist bereits aufgelöst; `kopfZusatz` (z. B.
 * Anlage-Auswahl) wandert links in die Kopfleiste; `tabelleSlot` (V3-Anzeige)
 * wird – falls gereicht – zwischen Datenbestand und Datenverwaltung gerendert.
 */
export function EnergieprofilPflege({
  anlageId,
  anlagenname,
  kopfZusatz,
  tabelleSlot,
}: {
  anlageId: number
  anlagenname?: string
  kopfZusatz?: ReactNode
  tabelleSlot?: ReactNode
}) {
  const { investitionen } = useInvestitionen(anlageId)
  const hatEAuto = investitionen.some(i => i.typ === 'e-auto')
  // D14-8-Gate: im V4-Daten-Block übernimmt die Werkbank; V3 behält die Karten.
  const istV4 = !!useV4Basis()

  const [stats, setStats] = useState<AnlageStats | null>(null)
  const [kpStatus, setKpStatus] = useState<KraftstoffpreisStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [runningBackfill, setRunningBackfill] = useState(false)
  const [runningKraftstoff, setRunningKraftstoff] = useState(false)
  const [runningDelete, setRunningDelete] = useState(false)

  const loadStats = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const s = await energieProfilApi.getAnlageStats(anlageId)
      setStats(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Statistik')
    } finally {
      setLoading(false)
    }
  }, [anlageId])

  const loadKraftstoffStatus = useCallback(async () => {
    try {
      const s = await energieProfilApi.getKraftstoffpreisStatus(anlageId)
      setKpStatus(s)
    } catch {
      setKpStatus(null)
    }
  }, [anlageId])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadKraftstoffStatus() }, [loadKraftstoffStatus])

  const handleVollbackfill = async () => {
    if (!window.confirm('Energieprofil-Lücken aus HA-Statistik nachfüllen? Bestehende Tage bleiben unverändert. Das kann einige Minuten dauern.')) return
    try {
      setRunningBackfill(true)
      setMessage(null)
      setError(null)
      const res = await energieProfilApi.vollbackfill(anlageId)
      // #190 Bug B: Skip-Gründe ausweisen, damit „79,4 %"-Cap erklärbar ist
      const teile: string[] = [
        `${res.geschrieben} von ${res.verarbeitet} Tagen geschrieben (${res.von} bis ${res.bis})`,
      ]
      if (res.uebersprungen_keine_daten && res.uebersprungen_keine_daten > 0) {
        teile.push(`${res.uebersprungen_keine_daten} Tage ohne HA-Statistics-Daten übersprungen`)
      }
      if (res.uebersprungen_existiert && res.uebersprungen_existiert > 0) {
        teile.push(`${res.uebersprungen_existiert} Tage bereits vorhanden`)
      }
      setMessage(`Vollbackfill: ${teile.join(' · ')}.`)
      await loadStats()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vollbackfill fehlgeschlagen')
    } finally {
      setRunningBackfill(false)
    }
  }

  const handleKraftstoffBackfill = async () => {
    try {
      setRunningKraftstoff(true)
      setMessage(null)
      setError(null)
      const res = await energieProfilApi.kraftstoffpreisBackfillTages(anlageId)
      if (res.fehler) {
        setError(`Kraftstoffpreis-Backfill: ${res.fehler}`)
      } else {
        setMessage(
          res.aktualisiert > 0
            ? `${res.aktualisiert} Tage mit Kraftstoffpreis (${res.land}) befüllt.`
            : (res.hinweis || 'Keine offenen Tage.')
        )
      }
      await loadKraftstoffStatus()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kraftstoffpreis-Backfill fehlgeschlagen')
    } finally {
      setRunningKraftstoff(false)
    }
  }

  const handleDeleteProfildaten = async () => {
    if (!window.confirm('Alle Energieprofil-Daten für diese Anlage löschen? Der Scheduler berechnet sie neu (max. 15 Min). Monatsdaten bleiben erhalten.')) return
    try {
      setRunningDelete(true)
      setMessage(null)
      setError(null)
      const res = await energieProfilApi.deleteRohdatenAnlage(anlageId)
      setMessage(`${res.geloescht_stundenwerte} Stundenwerte + ${res.geloescht_tagessummen} Tagessummen gelöscht. Scheduler berechnet neu (max. 15 Min).`)
      await loadStats()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Löschen fehlgeschlagen')
    } finally {
      setRunningDelete(false)
    }
  }

  const hatProfildaten = !!stats && (stats.stundenwerte > 0 || stats.tageszusammenfassungen > 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">{kopfZusatz}</div>
        <Button variant="secondary" onClick={() => { loadStats(); loadKraftstoffStatus() }} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </div>

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}

      {/* Datenbestand — D14-8/#128: reine Info, in V4 parkbar (Park-SoT; inert in V3). */}
      {hatProfildaten && stats && (
        <Parkbar id="info:datenbestand" titel="Datenbestand (pro Anlage)">
        <Card>
          <div className="p-3 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <BarChart3 className="h-6 w-6 text-emerald-500" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Datenbestand (pro Anlage)
              </h2>
            </div>

            <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-4">
              <div className="p-2 sm:p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
                  {fmtZahl(stats.stundenwerte, 0)}
                </p>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Stundenwerte</p>
                <p className="text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">24 pro Tag</p>
              </div>
              <div className="p-2 sm:p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
                  {fmtZahl(stats.tageszusammenfassungen, 0)}
                </p>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Tagessummen</p>
                <p className="text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">1 pro Tag</p>
              </div>
              <div className="p-2 sm:p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
                  {fmtZahl(stats.monatswerte, 0)}
                </p>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Monatswerte</p>
                <p className="text-[10px] sm:text-xs text-gray-400 dark:text-gray-500">1 pro Monat</p>
              </div>
            </div>

            {stats.zeitraum && (
              <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    Abdeckung: {stats.zeitraum.tage_mit_daten} von {stats.zeitraum.tage_gesamt} Tagen
                  </span>
                  <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
                    {fmtZahl(stats.zeitraum.abdeckung_prozent, 0)} %
                  </span>
                </div>
                <div className="w-full bg-emerald-200 dark:bg-emerald-800 rounded-sm h-2">
                  <div
                    className="bg-emerald-500 h-2 rounded-sm transition-all"
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
                  Wachstum: ~{fmtZahl(stats.wachstum_pro_monat, 0)} Zeilen/Monat
                  (25 Zeilen/Tag × 30 Tage)
                </p>
              </div>
            )}
          </div>
        </Card>
        </Parkbar>
      )}

      {/* Tages-Energieprofile (Anzeige) — nur wenn die V3-Seite sie reicht. */}
      {tabelleSlot}

      {/* Datenverwaltung — D14-8: nur V3; unter /v4 konsolidiert im
          Werkbank-Auswahlfeld (Lücken · Kraftstoffpreise · Löschen). */}
      {!istV4 && (
      <Card>
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <Activity className="h-6 w-6 text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Datenverwaltung
            </h2>
          </div>

          {/* Energieprofil-Lücken nachfüllen (#190: nur additiv) */}
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4">
            <div className="flex items-start gap-3">
              <History className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-medium text-gray-900 dark:text-white">
                  Energieprofil-Lücken aus HA-Statistik nachfüllen
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Ergänzt fehlende Tage aus den HA Long-Term Statistics — unabhängig von der ~10-Tage-Sensor-Grenze.
                  <strong className="text-gray-700 dark:text-gray-200"> Bestehende Tage bleiben unverändert.</strong>
                  {' '}Sinnvoll nach Erstinstallation, längerem App-Stopp oder Sensor-Mapping-Änderungen.
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  Möchtest du einen einzelnen Tag reparieren, der verzerrt aussieht? Nutze den Daten-Checker
                  (zeigt verdächtige Tage) und den Reload-Knopf in der Tagestabelle (mit Vorschau vor Übernahme).
                </p>
                <div className="mt-3">
                  <Button
                    onClick={handleVollbackfill}
                    disabled={runningBackfill}
                  >
                    {runningBackfill ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <History className="h-4 w-4 mr-2" />}
                    Lücken nachfüllen
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Kraftstoffpreis-Tages-Backfill — rapahl #188: nur bei E-Auto-Anlage. */}
          {hatEAuto && kpStatus && kpStatus.tages_offen > 0 && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4">
              <div className="flex items-start gap-3">
                <Fuel className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    Kraftstoffpreise nachpflegen (Tages-Ebene)
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {fmtZahl(kpStatus.tages_offen, 0)} Tage ohne Kraftstoffpreis.
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
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={handleDeleteProfildaten}
                      loading={runningDelete}
                    >
                      {!runningDelete && <Trash2 className="w-4 h-4 mr-2" />}
                      Energieprofil-Daten löschen
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
      )}

      {/* Reparatur-Werkbank (Etappe 3d Päckchen 4) — Plan + Execute + Verlauf */}
      <RepairWorkbench
        anlageId={anlageId}
        anlagenname={anlagenname}
      />
    </div>
  )
}
