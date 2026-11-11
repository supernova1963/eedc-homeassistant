/**
 * Daten-Checker — geteilte Teile (Prüf-Lauf + Kategorie-Sektionen + Reparatur-
 * Werkbank).
 *
 * EINE Code-Wahrheit für IST (`pages/DatenChecker.tsx`, dünner Komposer) und
 * IA-V4 (Einstellungen-Katalog-Block „Daten-Checker", inline wie Strompreise/
 * Monatsdaten — Gernot 2026-07-01). Der Aufrufer reicht die bereits aufgelöste
 * `anlageId` und – im Mehr-Anlagen-Fall – einen `kopfZusatz` (Anlage-Auswahl).
 * Zahlen de-DE über `fmtZahl`.
 */
import { useState, useEffect, useMemo, useRef, type ReactNode } from 'react'
import { RefreshCw, ChevronRight, ChevronDown, FileText } from 'lucide-react'
import { LoadingSpinner, Button } from '../components/ui'
import { datenCheckerApi, type DatenCheckResponse, type CheckErgebnis } from '../api/datenChecker'
import DiagnosePaketDialog from '../components/datenchecker/DiagnosePaketDialog'
import BefundHandgriff, { type HandgriffProps } from '../components/datenchecker/BefundHandgriff'
import BefundGruppe from '../components/datenchecker/BefundGruppe'
import HandgriffLeiste from '../components/datenchecker/HandgriffLeiste'
import LoesungswegPanel from '../components/datenchecker/LoesungswegPanel'
import SchwereChips from '../components/datenchecker/SchwereChips'
import { befundZeilen, kategorieOffen } from '../components/datenchecker/befundZeilen'
import type { ReparaturMeldung } from './datenCheckerMeldungen'
import { useSchmaleAchse } from '../hooks/useSchmaleAchse'
import { fmtZahl } from '../lib'
import {
  KATEGORIE_LABELS as kategorieLabels,
  KATEGORIE_REIHENFOLGE as kategorieReihenfolge,
} from '../config/datenCheckerKategorien'

// Kategorie-Labels/-Reihenfolge + Severity-Config sind SoT in config/datenCheckerKategorien.ts (geteilt mit dem
// IA-V4-Komponenten-Hub).

// ─── Kategorie-Sektion ─────────────────────────────────────────────────────────

/**
 * Eine Kategorie (Etappe E5, Konzept §6/§7, Mockup): Kopf mit Chips der Schweren; offen nach K1 (Fehler, Warnung oder
 * eine Aktion), sonst zugeklappt. OK-Zeilen stehen nicht in der Liste (V1) — der Fuß «n Prüfungen bestanden» klappt sie
 * auf. Gleiche Befunde eines Codes stehen als Gruppenzeile (V2). Jede Zeile hat genau einen Handgriff (W-10).
 */
function KategorieSektion({ kategorie, ergebnisse, ...handgriff }: HandgriffProps & {
  kategorie: string
  ergebnisse: CheckErgebnis[]
}) {
  const [open, setOpen] = useState(() => kategorieOffen(ergebnisse))
  const [okOffen, setOkOffen] = useState(false)
  const zaehlung = useMemo(() => {
    const c = { error: 0, warning: 0, info: 0, ok: 0 }
    ergebnisse.forEach((e) => { c[e.schwere] = (c[e.schwere] || 0) + 1 })
    return c
  }, [ergebnisse])
  const zeilen = useMemo(() => befundZeilen(ergebnisse), [ergebnisse])
  const okZeilen = ergebnisse.filter((e) => e.schwere === 'ok')
  const Pfeil = open ? ChevronDown : ChevronRight

  return (
    <section aria-label={kategorieLabels[kategorie] || kategorie}
      className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" data-testid="kategorie">
      <div className="bg-gray-50 dark:bg-gray-800">
        <Button type="button" variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}
          className="w-full justify-between text-left flex-wrap gap-2">
          <span className="flex items-center gap-2">
            <Pfeil className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            <span className="font-medium text-sm text-gray-900 dark:text-white">{kategorieLabels[kategorie] || kategorie}</span>
          </span>
          <SchwereChips zaehlung={zaehlung} />
        </Button>
      </div>

      {open && (
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {zeilen.map((z) => z.art === 'einzel'
            ? <BefundHandgriff key={`${z.befund.code}-${z.befund.meldung}`} befund={z.befund} {...handgriff} />
            : <BefundGruppe key={z.schluessel} glieder={z.glieder} {...handgriff} />)}
          {okZeilen.length > 0 && (
            <div>
              <Button type="button" variant="ghost" size="sm" onClick={() => setOkOffen(!okOffen)} aria-expanded={okOffen}
                className="w-full justify-start text-gray-600 dark:text-gray-400">
                {okOffen ? <ChevronDown className="h-3.5 w-3.5 mr-1" /> : <ChevronRight className="h-3.5 w-3.5 mr-1" />}
                {okZeilen.length} {okZeilen.length === 1 ? 'Prüfung' : 'Prüfungen'} bestanden
              </Button>
              {okOffen && okZeilen.map((e) => (
                <BefundHandgriff key={`${e.code}-${e.meldung}`} befund={e} {...handgriff} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

// ─── Verwaltung (Prüf-Lauf + KPI + Abdeckung + Kategorien + Lösungsweg) ───────

/**
 * Voller Daten-Checker. Genau eine Einbettung: der Katalog-Block `datenchecker`
 * der Kategorie *Daten* (`einstellungenKatalog.tsx`) — die fruehere V3-Seite ist
 * mit dem V4-Flip entfallen. `anlageId` ist bereits aufgelöst; `kopfZusatz`
 * (z. B. Anlage-Auswahl) wandert links in die Kopfleiste.
 */
export function DatenCheckerVerwaltung({ anlageId, kopfZusatz }: { anlageId: number; kopfZusatz?: ReactNode }) {
  const [result, setResult] = useState<DatenCheckResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [diagnoseOffen, setDiagnoseOffen] = useState(false)
  // E3: ein Vorgang zur Zeit (Vorschau offen oder Lauf) und der offene Lösungsweg.
  const [vorgangAktiv, setVorgangAktiv] = useState(false)
  const [loesungsweg, setLoesungsweg] = useState<CheckErgebnis | null>(null)
  // `hinweis` (bernstein) ist der dritte Zustand, den es braucht: der Lauf ist
  // durchgelaufen, hat aber nichts (oder nur teilweise etwas) geschrieben —
  // weder Erfolg noch Fehler.
  const [reparaturMessage, setReparaturMessage] = useState<ReparaturMeldung | null>(null)
  const schmal = useSchmaleAchse()
  const [stand, setStand] = useState<Date | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // E5.7 L2: das Panel steht neben der Liste und klebt unter dem Seitenkopf (`sticky`); geöffnet aus einer unteren
  // Kategorie holt es sich ins Bild (`nearest` scrollt nur, wenn es außerhalb liegt).
  useEffect(() => {
    if (loesungsweg && !schmal) panelRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [loesungsweg, schmal])

  // Nach «Anwenden»: der Satz des Laufs, dann prüft der Checker neu (der Befund verschwindet oder ändert sich, W-11).
  const nachDemLauf = (m: ReparaturMeldung) => {
    setReparaturMessage(m)
    setRefreshKey(k => k + 1)
  }

  // Check laden wenn Anlage ausgewählt / neu angefordert
  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await datenCheckerApi.check(anlageId)
        setResult(data)
        setStand(new Date())
      } catch {
        setError('Fehler beim Laden der Prüfergebnisse')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [anlageId, refreshKey])

  const handgriff: HandgriffProps = {
    anlageId, gesperrt: vorgangAktiv, onVorgang: setVorgangAktiv, onErgebnis: nachDemLauf, onLoesungsweg: setLoesungsweg,
  }

  // Ergebnisse nach Kategorie gruppieren
  const grouped = useMemo(() => {
    if (!result) return {}
    const groups: Record<string, CheckErgebnis[]> = {}
    for (const e of result.ergebnisse) {
      if (!groups[e.kategorie]) groups[e.kategorie] = []
      groups[e.kategorie].push(e)
    }
    return groups
  }, [result])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {kopfZusatz}
          {result && !loading && <KopfZeile result={result} stand={stand} />}
        </div>
        <div className="flex items-center gap-2">
          {/* E1: Diagnose-Paket zum Kopieren oder Herunterladen (Konzept Daten-Checker §8.3). */}
          <Button variant="secondary" size="sm" onClick={() => setDiagnoseOffen(true)} title="Diagnose-Paket">
            <FileText className="h-4 w-4 mr-2" />
            Diagnose-Paket
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => { setResult(null); setRefreshKey(k => k + 1) }}
            disabled={loading}
            title="Aktualisieren"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </Button>
        </div>
      </div>
      <DiagnosePaketDialog isOpen={diagnoseOffen} onClose={() => setDiagnoseOffen(false)} anlageId={anlageId} />

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner />
        </div>
      )}

      {result && !loading && (
        <>
          {/* E5 K2: alle Aktionen über alle Kategorien oben («Das kannst du jetzt tun»). */}
          <HandgriffLeiste ergebnisse={result.ergebnisse} {...handgriff} />

          {/* Monatsdaten-Abdeckung */}
          {result.monatsdaten_abdeckung && result.monatsdaten_abdeckung.erwartet > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Monatsdaten-Abdeckung
                </span>
                <span className="text-sm text-gray-500">
                  {result.monatsdaten_abdeckung.vorhanden} von {result.monatsdaten_abdeckung.erwartet} Monate ({fmtZahl(result.monatsdaten_abdeckung.prozent, 0)} %)
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-2.5">
                <div
                  className={`h-2.5 rounded-sm transition-all ${
                    result.monatsdaten_abdeckung.prozent >= 90
                      ? 'bg-green-500'
                      : result.monatsdaten_abdeckung.prozent >= 70
                        ? 'bg-amber-500'
                        : 'bg-red-500'
                  }`}
                  style={{ width: `${Math.min(100, result.monatsdaten_abdeckung.prozent)}%` }}
                />
              </div>
            </div>
          )}

          {/* Reparatur-Status-Toast */}
          {reparaturMessage && (
            <div className={`px-3 py-2 rounded text-sm ${
              reparaturMessage.art === 'ok'
                ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800'
                : reparaturMessage.art === 'hinweis'
                ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
            }`}>
              {reparaturMessage.text}
            </div>
          )}

          {/* Kategorien — mit offenem Lösungsweg zweispaltig (Panel klebt neben der Liste, E5.7 L2), auf dem Handy Dialog. */}
          <div className={loesungsweg && !schmal ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] items-start' : ''}>
            <div className="space-y-3">
              {kategorieReihenfolge.map((kat) => grouped[kat]?.length
                ? <KategorieSektion key={kat} kategorie={kat} ergebnisse={grouped[kat]} {...handgriff} />
                : null)}
            </div>
            {loesungsweg && (
              <div ref={panelRef} className={schmal ? '' : 'lg:sticky lg:top-4'} data-testid="loesungsweg-spalte">
                <LoesungswegPanel befund={loesungsweg} als={schmal ? 'dialog' : 'einschub'} onClose={() => setLoesungsweg(null)} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}


/** Kopf des Checkers (E5, Mockup): Chips der Zusammenfassung, Stand und die nicht ausführbaren Prüfungen (V4). */
function KopfZeile({ result, stand }: { result: DatenCheckResponse; stand: Date | null }) {
  const nicht = result.nicht_ausfuehrbar ?? []
  const gruende = [...new Set(nicht.map((n) => n.grund))].join(' / ')
  return (
    <span className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400" data-testid="checker-kopf">
      <SchwereChips zaehlung={result.zusammenfassung} />
      {stand && <span>Stand {stand.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</span>}
      {nicht.length > 0 && (
        <span title={nicht.map((n) => n.pruefung).join(', ')}>
          · {nicht.length} {nicht.length === 1 ? 'Prüfung' : 'Prüfungen'} nicht ausführbar ({gruende})
        </span>
      )}
    </span>
  )
}
