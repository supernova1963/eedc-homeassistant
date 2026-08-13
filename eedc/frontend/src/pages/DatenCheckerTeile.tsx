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
import { useState, useEffect, useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { v3RouteZuV4 } from '../config/v3ZuV4Route'
import {
  RefreshCw, XCircle, AlertTriangle, Info,
  CheckCircle, ChevronRight, ChevronDown, Wrench,
} from 'lucide-react'
import { LoadingSpinner, Button } from '../components/ui'
import { KPICard } from '../components/ui'
import { datenCheckerApi, type DatenCheckResponse, type CheckErgebnis } from '../api/datenChecker'
import { energieProfilApi } from '../api/energie_profil'
import { monatsdatenApi } from '../api/monatsdaten'
import { baueBereichsMeldung, baueTagesMeldung, type ReparaturMeldung } from './datenCheckerMeldungen'
import { fmtZahl, formatDatum } from '../lib'
import {
  KATEGORIE_LABELS as kategorieLabels,
  KATEGORIE_REIHENFOLGE as kategorieReihenfolge,
  SEVERITY_CONFIG,
  type CheckSchwere,
} from '../config/datenCheckerKategorien'

// ─── Severity-Helfer ──────────────────────────────────────────────────────────
// Kategorie-Labels/-Reihenfolge + Severity-Config sind SoT in
// config/datenCheckerKategorien.ts (geteilt mit dem IA-V4-Komponenten-Hub).

function severityIcon(schwere: string) {
  const cfg = SEVERITY_CONFIG[schwere as CheckSchwere]
  if (!cfg) return null
  const Icon = cfg.icon
  return <Icon className={`h-4 w-4 ${cfg.colorClass} flex-shrink-0`} />
}

function severityBadge(counts: Record<string, number>) {
  const parts: string[] = []
  if (counts.error > 0) parts.push(`${counts.error} Fehler`)  // Singular = Plural
  if (counts.warning > 0) {
    parts.push(`${counts.warning} ${counts.warning === 1 ? 'Warnung' : 'Warnungen'}`)
  }
  if (counts.info > 0) {
    parts.push(`${counts.info} ${counts.info === 1 ? 'Hinweis' : 'Hinweise'}`)
  }
  if (parts.length === 0) return 'OK'
  return parts.join(', ')
}

// ─── Kategorie-Sektion ─────────────────────────────────────────────────────────

function KategorieSektion({
  kategorie,
  ergebnisse,
  defaultOpen,
  onReaggregate,
  onReaggregateBereich,
  onGeraetewerteLoeschen,
  reparaturBusy,
}: {
  kategorie: string
  ergebnisse: CheckErgebnis[]
  defaultOpen: boolean
  onReaggregate?: (anlageId: number, datum: string) => Promise<void>
  onReaggregateBereich?: (anlageId: number, von: string, bis: string) => Promise<void>
  onGeraetewerteLoeschen?: (anlageId: number, jahr: number, monat: number) => Promise<void>
  reparaturBusy?: string | null  // key = `${anlage_id}:${datum}` (Einzeltag) bzw. `${anlage_id}:${von}:${bis}` (Bereich) bzw. `${anlage_id}:${jahr}-${monat}` (#349)
}) {
  const [open, setOpen] = useState(defaultOpen)
  const navigate = useNavigate()
  // Geteilte Datei (V3-Seite + V4-Daten-Block): „Beheben"-Links unter /v4 auf den
  // re-kategorisierten V4-Reiter umbiegen (Donor-Ziele bleiben V3 → R6).

  const counts = useMemo(() => {
    const c = { error: 0, warning: 0, info: 0, ok: 0 }
    ergebnisse.forEach((e) => { c[e.schwere] = (c[e.schwere] || 0) + 1 })
    return c
  }, [ergebnisse])

  const hasIssues = counts.error > 0 || counts.warning > 0

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <div className="bg-gray-50 dark:bg-gray-800">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="w-full justify-between text-left"
        >
          <span className="flex items-center gap-2">
            {open ? (
              <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            )}
            <span className="font-medium text-sm text-gray-900 dark:text-white">
              {kategorieLabels[kategorie] || kategorie}
            </span>
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            hasIssues
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
              : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          }`}>
            {severityBadge(counts)}
          </span>
        </Button>
      </div>

      {open && (
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {ergebnisse.map((e, i) => {
            const actionAnlageId = e.action_kind === 'reaggregate_day'
              ? Number(e.action_params?.anlage_id) : undefined
            const actionDatum = e.action_kind === 'reaggregate_day'
              ? String(e.action_params?.datum ?? '') : undefined
            const reparaturKey = actionAnlageId && actionDatum
              ? `${actionAnlageId}:${actionDatum}` : null /* de-de-allow: interner State-Key (Busy-Kennung), keine Anzeige */
            const isReparaturBusy = reparaturKey && reparaturBusy === reparaturKey

            // v3.45.9: Bereichs-Reparatur (Batterie-Vorzeichen-Historie).
            const rangeAnlageId = e.action_kind === 'reaggregate_range'
              ? Number(e.action_params?.anlage_id) : undefined
            const rangeVon = e.action_kind === 'reaggregate_range'
              ? String(e.action_params?.von ?? '') : undefined
            const rangeBis = e.action_kind === 'reaggregate_range'
              ? String(e.action_params?.bis ?? '') : undefined
            const rangeKey = rangeAnlageId && rangeVon && rangeBis
              ? `${rangeAnlageId}:${rangeVon}:${rangeBis}` : null
            const isRangeBusy = rangeKey && reparaturBusy === rangeKey

            // #349: Messwerte ohne Zählerzeile entfernen.
            const gwAnlageId = e.action_kind === 'geraetewerte_loeschen'
              ? Number(e.action_params?.anlage_id) : undefined
            const gwJahr = e.action_kind === 'geraetewerte_loeschen'
              ? Number(e.action_params?.jahr) : undefined
            const gwMonat = e.action_kind === 'geraetewerte_loeschen'
              ? Number(e.action_params?.monat) : undefined
            const gwKey = gwAnlageId && gwJahr && gwMonat
              ? `${gwAnlageId}:${gwJahr}-${gwMonat}` : null
            const isGwBusy = gwKey && reparaturBusy === gwKey

            return (
              <div
                key={i}
                className="flex items-start gap-3 px-4 py-2.5"
              >
                <div className="mt-0.5">{severityIcon(e.schwere)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800 dark:text-gray-200">{e.meldung}</p>
                  {e.details && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 whitespace-pre-line">{e.details}</p>
                  )}
                </div>
                {e.action_kind === 'reaggregate_day' && onReaggregate && actionAnlageId && actionDatum && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="flex-shrink-0"
                    onClick={() => onReaggregate(actionAnlageId, actionDatum)}
                    disabled={!!reparaturBusy}
                    loading={!!isReparaturBusy}
                  >
                    {!isReparaturBusy && <Wrench className="h-3 w-3 mr-1" />}
                    {e.action_label ?? 'Tag reparieren'}
                  </Button>
                )}
                {e.action_kind === 'reaggregate_range' && onReaggregateBereich && rangeAnlageId && rangeVon && rangeBis && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="flex-shrink-0"
                    onClick={() => onReaggregateBereich(rangeAnlageId, rangeVon, rangeBis)}
                    disabled={!!reparaturBusy}
                    loading={!!isRangeBusy}
                  >
                    {!isRangeBusy && <Wrench className="h-3 w-3 mr-1" />}
                    {e.action_label ?? 'Zeitraum neu aggregieren'}
                  </Button>
                )}
                {e.action_kind === 'geraetewerte_loeschen' && onGeraetewerteLoeschen
                  && gwAnlageId && gwJahr && gwMonat && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="flex-shrink-0"
                    onClick={() => onGeraetewerteLoeschen(gwAnlageId, gwJahr, gwMonat)}
                    disabled={!!reparaturBusy}
                    loading={!!isGwBusy}
                  >
                    {!isGwBusy && <Wrench className="h-3 w-3 mr-1" />}
                    {e.action_label ?? 'Messwerte entfernen'}
                  </Button>
                )}
                {e.link && !e.action_kind && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="flex-shrink-0"
                    onClick={() => navigate(v3RouteZuV4(e.link!) ?? e.link!)}
                  >
                    Beheben
                    <ChevronRight className="h-3 w-3 ml-0.5" />
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Verwaltung (Prüf-Lauf + KPI + Abdeckung + Kategorien + Reparatur) ─────────

/**
 * Voller Daten-Checker. Wird von der IST-Seite (V3-Hülle) und dem V4-Daten-Block
 * geteilt. `anlageId` ist bereits aufgelöst; `kopfZusatz` (z. B. Anlage-Auswahl)
 * wandert links in die Kopfleiste.
 */
export function DatenCheckerVerwaltung({ anlageId, kopfZusatz }: { anlageId: number; kopfZusatz?: ReactNode }) {
  const [result, setResult] = useState<DatenCheckResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [reparaturBusy, setReparaturBusy] = useState<string | null>(null)
  // `hinweis` (bernstein) ist der dritte Zustand, den es braucht: der Lauf ist
  // durchgelaufen, hat aber nichts (oder nur teilweise etwas) geschrieben —
  // weder Erfolg noch Fehler. Ohne ihn stand „aggregiert" auch dann da, wenn
  // kein einziger Tag verwertbare Daten hatte.
  const [reparaturMessage, setReparaturMessage] = useState<ReparaturMeldung | null>(null)

  // Etappe 6 v3.31.1: Per-Tag-Reparatur über bestehenden reaggregate-tag-Endpoint.
  const handleReaggregateDay = async (anlageId: number, datum: string) => {
    const key = `${anlageId}:${datum}`
    setReparaturBusy(key)
    setReparaturMessage(null)
    try {
      const result = await energieProfilApi.reaggregateTag(anlageId, datum, true)
      // Rückmeldung aus dem TATSÄCHLICHEN Lauf (SoT: baueTagesMeldung, dieselbe
      // Datei wie der Bereichs-Pfad) — `status: "ok"` heißt nur „durchgelaufen".
      // Die PV-Tagessumme vor/nach bleibt darin erhalten (#290-Frage „hat sich
      // etwas bewegt?"), ergänzt um die Aussage je Komponente (N-58).
      setReparaturMessage(baueTagesMeldung(result, datum))
      // Daten-Checker neu laden → Eintrag verschwindet, wenn Drift jetzt unter Schwelle
      setRefreshKey(k => k + 1)
    } catch (e) {
      setReparaturMessage({
        art: 'fehler',
        text: e instanceof Error ? e.message : `Reparatur für ${formatDatum(datum)} fehlgeschlagen`,
      })
    } finally {
      setReparaturBusy(null)
    }
  }

  // v3.45.9: Bereichs-Reparatur (Batterie-Vorzeichen-Historie) über den
  // bestehenden reaggregate-bereich-Endpoint (max 31 Tage/Lauf, Cap im Backend).
  const handleReaggregateBereich = async (anlageId: number, von: string, bis: string) => {
    const key = `${anlageId}:${von}:${bis}`
    setReparaturBusy(key)
    setReparaturMessage(null)
    try {
      const r = await energieProfilApi.reaggregateBereich(anlageId, von, bis, true)
      // Rückmeldung aus den TATSÄCHLICHEN Zählern (SoT: baueBereichsMeldung) —
      // `status: "ok"` heißt nur „durchgelaufen", nicht „etwas geschrieben".
      setReparaturMessage(baueBereichsMeldung(r, von, bis))
      // Daten-Checker neu laden → Einträge verschwinden, wenn der Konflikt weg ist.
      setRefreshKey(k => k + 1)
    } catch (e) {
      setReparaturMessage({
        art: 'fehler',
        text: e instanceof Error ? e.message : `Reaggregation ${von}–${bis} fehlgeschlagen`,
      })
    } finally {
      setReparaturBusy(null)
    }
  }

  // #349: Messwerte eines Monats entfernen, dessen Zählerzeile gelöscht wurde.
  // Die einzige Aktion dieser Seite, die Daten **löscht** — deshalb mit
  // Rückfrage, und die Rückfrage nennt den Monat statt „diesen Eintrag".
  const handleGeraetewerteLoeschen = async (anlageId: number, jahr: number, monat: number) => {
    const key = `${anlageId}:${jahr}-${monat}`
    const monatText = `${String(monat).padStart(2, '0')}/${jahr}`
    if (!window.confirm(
      `Messwerte einzelner Komponenten für ${monatText} endgültig entfernen?\n\n` +
      'Der Monat hat keine Zählerzeile mehr. Wenn du die Werte behalten willst, ' +
      'erfasse den Monat stattdessen neu — dann gehören sie wieder dazu.'
    )) return

    setReparaturBusy(key)
    setReparaturMessage(null)
    try {
      const r = await monatsdatenApi.deleteVerwaisteGeraetewerte(anlageId, jahr, monat)
      setReparaturMessage({
        art: r.geloescht > 0 ? 'ok' : 'hinweis',
        text: r.geloescht > 0
          ? `${monatText}: ${r.geloescht} Messwert-Zeile(n) entfernt (${r.komponenten.join(', ')}).`
          : `${monatText}: es war nichts mehr zu entfernen.`,
      })
      setRefreshKey(k => k + 1)
    } catch (e) {
      setReparaturMessage({
        art: 'fehler',
        text: e instanceof Error ? e.message : `${monatText} konnte nicht bereinigt werden`,
      })
    } finally {
      setReparaturBusy(null)
    }
  }

  // Check laden wenn Anlage ausgewählt / neu angefordert
  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await datenCheckerApi.check(anlageId)
        setResult(data)
      } catch {
        setError('Fehler beim Laden der Prüfergebnisse')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [anlageId, refreshKey])

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
        <div className="flex items-center gap-2">{kopfZusatz}</div>
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
          {/* KPI-Karten */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KPICard
              title="Fehler"
              value={result.zusammenfassung.error}
              icon={XCircle}
              color={result.zusammenfassung.error > 0 ? 'red' : 'gray'}
            />
            <KPICard
              title="Warnungen"
              value={result.zusammenfassung.warning}
              icon={AlertTriangle}
              color={result.zusammenfassung.warning > 0 ? 'yellow' : 'gray'}
            />
            <KPICard
              title="Hinweise"
              value={result.zusammenfassung.info}
              icon={Info}
              color={result.zusammenfassung.info > 0 ? 'blue' : 'gray'}
            />
            <KPICard
              title="OK"
              value={result.zusammenfassung.ok}
              icon={CheckCircle}
              color="green"
            />
          </div>

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

          {/* Kategorien */}
          <div className="space-y-3">
            {kategorieReihenfolge.map((kat) => {
              const items = grouped[kat]
              if (!items || items.length === 0) return null
              const hasIssues = items.some((e) => e.schwere === 'error' || e.schwere === 'warning')
              return (
                <KategorieSektion
                  key={kat}
                  kategorie={kat}
                  ergebnisse={items}
                  defaultOpen={hasIssues}
                  onReaggregate={handleReaggregateDay}
                  onReaggregateBereich={handleReaggregateBereich}
                  onGeraetewerteLoeschen={handleGeraetewerteLoeschen}
                  reparaturBusy={reparaturBusy}
                />
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
