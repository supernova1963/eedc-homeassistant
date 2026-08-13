/**
 * Energieprofil — geteilte Teile (nur die PFLEGE-Funktionen).
 *
 * Block im Einstellungen-Katalog („Energieprofil-Pflege", inline wie
 * Monatsdaten/Daten-Checker). **Anzeige ≠ Pflege** (Plan §6): die Tages-Anzeige
 * ist der Block „Energieprofile" in `AuswertungenTabelleV4` (Werte-SoT
 * `WerteTabelle`, seit #350 mit Spalten je Erzeuger). Der Pflege-Block trägt:
 * Datenbestand-Status und die Reparatur-Werkbank (Lücken-Backfill ·
 * Kraftstoffpreis-Backfill · Löschen laufen über deren Auswahlfeld).
 * Zahlen de-DE über `fmtZahl`.
 *
 * **`tabelleSlot` ist am 2026-08-04 entfallen** (#350): er reichte die V3-eigene
 * `EnergieprofilTageTabelle` durch, deren Seite (`pages/Energieprofil.tsx`) mit
 * dem V4-Flip verschwand — der Slot hatte seither keinen Setzer, die Tabelle
 * keinen Aufrufer. Der Entscheid dahinter ist älter als der Fund: „V3-Tabelle
 * wird beim Flip mit V3 stillgelegt, kein Umzug, keine zweite Tabellen-Wahrheit"
 * (Gernot, 2026-07-02) — ausgeführt wurde er beim Flip nur nicht.
 *
 * D14-8 (detLAN #113/#123, Gernot #128 + Gating-Entscheid 2026-07-03): die
 * „Datenverwaltung"-Karte (Lücken/Kraftstoff/Löschen) war unter `/v4` ausgeblendet,
 * weil alles über das Auswahlfeld der EINEN Reparatur-Werkbank läuft. **Mit dem
 * V3-Aufräumen 2026-08-13 ist sie entfernt** — samt der drei Handler und des
 * Kraftstoffpreis-Status, den nur sie gelesen hat (ein API-Aufruf je Seitenaufruf
 * weniger). Der Block trägt jetzt: Datenbestand-Status (parkbare Info) · Werkbank.
 */
import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { BarChart3, RefreshCw, Info } from 'lucide-react'
import { Button, Card, Alert } from '../components/ui'
import { Parkbar } from '../components/park'
import { energieProfilApi, type AnlageStats } from '../api/energie_profil'
import RepairWorkbench from '../components/repair/RepairWorkbench'
import { fmtZahl } from '../lib'

/**
 * Voller Energieprofil-PFLEGE-Block. `anlageId` ist bereits aufgelöst;
 * `kopfZusatz` (z. B. Anlage-Auswahl) wandert links in die Kopfleiste.
 */
export function EnergieprofilPflege({
  anlageId,
  anlagenname,
  kopfZusatz,
}: {
  anlageId: number
  anlagenname?: string
  kopfZusatz?: ReactNode
}) {
  // D14-8: Die Datenverwaltungs-Karten (Lücken · Kraftstoffpreise · Löschen) gab es nur
  // in V3; sie sind im Auswahlfeld der Reparatur-Werkbank unten aufgegangen. Der tote
  // `!istV4`-Zweig ist mit dem V3-Aufräumen 2026-08-13 entfernt — mit ihm die drei
  // Handler, ihre Lade-States und der Kraftstoffpreis-Status, den nur er gelesen hat.

  const [stats, setStats] = useState<AnlageStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  useEffect(() => { loadStats() }, [loadStats])

  const hatProfildaten = !!stats && (stats.stundenwerte > 0 || stats.tageszusammenfassungen > 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">{kopfZusatz}</div>
        <Button variant="secondary" onClick={() => loadStats()} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </div>

      {error && <Alert type="error">{error}</Alert>}

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


      {/* Reparatur-Werkbank (Etappe 3d Päckchen 4) — Plan + Execute + Verlauf */}
      <RepairWorkbench
        anlageId={anlageId}
        anlagenname={anlagenname}
      />
    </div>
  )
}
