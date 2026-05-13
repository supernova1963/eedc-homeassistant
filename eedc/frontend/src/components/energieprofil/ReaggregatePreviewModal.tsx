import { Fragment, useState, useEffect, useMemo, useRef } from 'react'
import { Loader2, AlertTriangle, ArrowRight, Info } from 'lucide-react'
import { Modal, Button, Alert } from '../ui'
import { energieProfilApi, type ReaggregatePreviewResponse } from '../../api/energie_profil'

// Nach so vielen Sekunden Apply darf der Modal-X auch im applying-Zustand
// klicken werden — der Backend-Job läuft dann im Hintergrund weiter, der
// User wird nicht mehr blockiert (Etappe 3c P4, Konzept Sektion 6.2).
// Empirischer Resnap-Range: ~25 hourly + ~140 5-Min-Slots × 200 ms ≈ 30 s.
const FORCE_CLOSE_AFTER_MS = 30_000

interface Props {
  anlageId: number
  datum: string | null  // null = Modal geschlossen
  onClose: () => void
  onApplied: (result: { stunden_mit_messdaten: number }) => void
}

const KAT_LABELS: Record<string, string> = {
  pv: 'PV',
  einspeisung: 'Einspeisung',
  netzbezug: 'Netzbezug',
  ladung_batterie: 'Batterie-Ladung',
  entladung_batterie: 'Batterie-Entladung',
  verbrauch_wp: 'WP-Verbrauch',
  ladung_wallbox: 'Wallbox-Ladung',
  verbrauch_eauto: 'E-Auto-Verbrauch',
  erzeugung_sonstiges: 'Sonstige Erzeugung',
  verbrauch_sonstiges: 'Sonstiger Verbrauch',
}

const COUNTER_LABELS: Record<string, string> = {
  wp_starts_anzahl: 'WP-Kompressor-Starts',
}

function fmtKwh(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toFixed(3)
}

function fmtCount(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('de-DE')
}

function diffClass(alt: number | null, neu: number | null): string {
  if (alt === null || neu === null) return ''
  const diff = Math.abs(neu - alt)
  if (diff > 1.0) return 'font-bold text-amber-600 dark:text-amber-400'
  if (diff > 0.1) return 'text-amber-600 dark:text-amber-400'
  return ''
}

// Counter sind Ganzzahlen (Anzahl Starts) — schon eine Abweichung von 1 ist
// auffällig. Threshold für „fett" bei 5, weil Restart-Spikes typischerweise
// die Tageszahl deutlich verziehen.
function counterDiffClass(alt: number | null, neu: number | null): string {
  if (alt === null || neu === null) return ''
  const diff = Math.abs(neu - alt)
  if (diff >= 5) return 'font-bold text-amber-600 dark:text-amber-400'
  if (diff >= 1) return 'text-amber-600 dark:text-amber-400'
  return ''
}

export default function ReaggregatePreviewModal({ anlageId, datum, onClose, onApplied }: Props) {
  const [data, setData] = useState<ReaggregatePreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  // applyMode: null = nicht-applying, 'with_resnap' | 'rebuild_only' = Apply läuft
  const [applyMode, setApplyMode] = useState<null | 'with_resnap' | 'rebuild_only'>(null)
  const [applyElapsedMs, setApplyElapsedMs] = useState(0)
  const [forceCloseAvailable, setForceCloseAvailable] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // AbortController für laufende fetch-Requests — wird beim Schließen gefeuert.
  const abortRef = useRef<AbortController | null>(null)

  const applying = applyMode !== null

  // Vorschau laden — mit AbortController, damit Schließen während Loading
  // den fetch sauber abbricht.
  useEffect(() => {
    if (!datum) {
      setData(null)
      setError(null)
      return
    }
    // #234 detLAN: Modal wird nicht ge-unmountet wenn datum auf null geht
    // (parent rendert `{showReaggregate && <Modal …/>}` permanent, nur die
    // datum-prop wechselt). Daher überleben applyMode / forceCloseAvailable
    // sonst aus dem vorherigen Lauf — Row-Buttons + Modal-Buttons bleiben
    // in "busy"-State stecken. Bei neuem datum hart resetten.
    setApplyMode(null)
    setForceCloseAvailable(false)
    setApplyElapsedMs(0)
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)
    energieProfilApi.reaggregateTagPreview(anlageId, datum, controller.signal)
      .then(setData)
      .catch((e: Error) => {
        if (e.name === 'AbortError') return  // Modal wurde geschlossen, kein Fehler
        setError(e.message || 'Vorschau konnte nicht geladen werden.')
      })
      .finally(() => setLoading(false))
    return () => {
      // Cleanup bei Re-Render / Unmount: laufenden Fetch abbrechen
      controller.abort()
    }
  }, [anlageId, datum])

  // Restzeit-Anzeige + Force-Close-Aktivierung während applying
  useEffect(() => {
    if (!applying) {
      setApplyElapsedMs(0)
      setForceCloseAvailable(false)
      return
    }
    const start = Date.now()
    const interval = setInterval(() => {
      const elapsed = Date.now() - start
      setApplyElapsedMs(elapsed)
      if (elapsed >= FORCE_CLOSE_AFTER_MS && !forceCloseAvailable) {
        setForceCloseAvailable(true)
      }
    }, 500)
    return () => clearInterval(interval)
  }, [applying, forceCloseAvailable])

  // Kategorien sortiert (PV, Einspeisung, Bezug zuerst)
  const kategorien = useMemo(() => {
    if (!data) return []
    const all = new Set(data.slot_deltas.map(s => s.kategorie))
    const order = ['pv', 'einspeisung', 'netzbezug', 'ladung_batterie', 'entladung_batterie',
                   'verbrauch_wp', 'ladung_wallbox', 'verbrauch_eauto',
                   'erzeugung_sonstiges', 'verbrauch_sonstiges']
    return order.filter(k => all.has(k))
  }, [data])

  // Index slot_deltas: stunde × kategorie → {alt, neu}
  const slotIndex = useMemo(() => {
    if (!data) return new Map<string, { alt: number | null; neu: number | null }>()
    const m = new Map<string, { alt: number | null; neu: number | null }>()
    for (const s of data.slot_deltas) {
      m.set(`${s.stunde}|${s.kategorie}`, { alt: s.alt_kwh, neu: s.neu_kwh })
    }
    return m
  }, [data])

  // Sind die Snapshots in der DB bereits konsistent mit HA-Stats? Wenn ja,
  // genügt ein „nur neu rechnen" ohne Resnap — schnell, kein HA-Polling, kein
  // Hänger-Risiko (Befund MartyBr 7.5.2026: Übernehmen für 5.5. blockierte beim
  // Resnap obwohl Snapshots bereits korrekt waren — die Vorschau zeigte alt=neu
  // überall, aber TagesZusammenfassung stand mit altem Wert in der DB).
  // Toleranz: 0.05 kWh für Slot-Deltas (Float-Noise), exakte Gleichheit für
  // Counter-Integer.
  const snapshotsAreCurrent = useMemo(() => {
    if (!data || !data.ha_verfuegbar) return false
    const isEqual = (a: number | null, b: number | null, tol: number): boolean => {
      if (a === null && b === null) return true
      if (a === null || b === null) return false
      return Math.abs(a - b) < tol
    }
    for (const s of data.slot_deltas) {
      if (!isEqual(s.alt_kwh, s.neu_kwh, 0.05)) return false
    }
    for (const c of data.counter_tagesdelta) {
      if (!isEqual(c.alt, c.neu, 0.5)) return false
    }
    return true
  }, [data])

  const handleApply = async (mode: 'with_resnap' | 'rebuild_only') => {
    if (!datum) return
    setApplyMode(mode)
    setError(null)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const mitResnap = mode === 'with_resnap'
      const res = await energieProfilApi.reaggregateTag(anlageId, datum, mitResnap, controller.signal)
      onApplied({ stunden_mit_messdaten: res.stunden_mit_messdaten })
      // #234 detLAN: applyMode auch im Success-Pfad zurücksetzen, sonst
      // bleibt der Modal-Inner-State auf "applying" stehen und der nächste
      // Modal-Aufruf erbt das (siehe Reset-Block im datum-useEffect oben).
      setApplyMode(null)
      onClose()
    } catch (e) {
      // AbortError = User hat Modal geschlossen mit Force-Close — Backend läuft weiter
      if (e instanceof Error && e.name === 'AbortError') return
      setError(e instanceof Error ? e.message : 'Übernahme fehlgeschlagen.')
      setApplyMode(null)
    }
  }

  // Schließen-Handler: bricht laufende Requests ab. Während Apply nur erlaubt
  // wenn forceCloseAvailable (nach 30s) — der Backend-Job läuft dann im
  // Hintergrund weiter, der User kann sich aus dem Spinner befreien.
  const handleClose = () => {
    if (applying && !forceCloseAvailable) return
    abortRef.current?.abort()
    onClose()
  }

  if (!datum) return null

  return (
    <Modal
      isOpen={!!datum}
      onClose={handleClose}
      title={`Vorschau: ${datum} aus HA neu laden`}
      size="xl"
    >
      {loading && (
        <div className="flex items-center justify-center py-8 text-gray-500">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" />
          Lade HA-Werte für Vorschau …
        </div>
      )}

      {error && <Alert type="error" className="mb-3">{error}</Alert>}

      {data && !loading && (
        <>
          {!data.ha_verfuegbar && (
            <Alert type="warning" className="mb-3">
              <AlertTriangle className="inline w-4 h-4 mr-1" />
              HA-Statistics nicht erreichbar — die "Neu"-Spalte ist leer.
              Bei Übernahme wird nichts überschrieben.
            </Alert>
          )}

          <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
            Vergleich der aktuellen Snapshots in der Datenbank (<strong>Alt</strong>) mit den
            Werten, die jetzt aus HA-Statistics kämen (<strong>Neu</strong>). Slot 0 hängt vom
            Vortags-23:00-Snapshot ab — der ist hier mit aufgeführt. Erst nach <em>Übernehmen</em>
            werden die Snapshots überschrieben und der Tag neu aggregiert.
          </p>

          {/* Tagesumme */}
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded">
            <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
              Tagesumme {datum} (kWh)
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="pb-1">Kategorie</th>
                  <th className="pb-1 text-right">Alt</th>
                  <th className="pb-1"><span className="sr-only">wird zu</span></th>
                  <th className="pb-1 text-right">Neu</th>
                </tr>
              </thead>
              <tbody>
                {kategorien.map(k => {
                  const alt = data.tagesumme_alt[k] ?? null
                  const neu = data.tagesumme_neu[k] ?? null
                  return (
                    <tr key={k}>
                      <td className="py-0.5">{KAT_LABELS[k] || k}</td>
                      <td className="py-0.5 text-right tabular-nums">{fmtKwh(alt)}</td>
                      <td className="py-0.5 text-center text-gray-400">
                        <ArrowRight className="inline w-3 h-3" />
                      </td>
                      <td className={`py-0.5 text-right tabular-nums ${diffClass(alt, neu)}`}>
                        {fmtKwh(neu)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Counter-Tagesgesamt (Anzahl-Zähler ohne kWh-Semantik, z. B. WP-Starts) */}
          {data.counter_tagesdelta.length > 0 && (
            <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded">
              <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
                Counter-Tagesgesamt {datum}
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 dark:text-gray-400">
                    <th className="pb-1">Feld</th>
                    <th className="pb-1 text-right">Alt</th>
                    <th className="pb-1"><span className="sr-only">wird zu</span></th>
                    <th className="pb-1 text-right">Neu</th>
                  </tr>
                </thead>
                <tbody>
                  {data.counter_tagesdelta.map(c => (
                    <tr key={c.feld}>
                      <td className="py-0.5">{COUNTER_LABELS[c.feld] || c.feld}</td>
                      <td className="py-0.5 text-right tabular-nums">{fmtCount(c.alt)}</td>
                      <td className="py-0.5 text-center text-gray-400">
                        <ArrowRight className="inline w-3 h-3" />
                      </td>
                      <td className={`py-0.5 text-right tabular-nums ${counterDiffClass(c.alt, c.neu)}`}>
                        {fmtCount(c.neu)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-2">
                Tagesgesamt = snap(Folgetag 00:00) − snap(Tag 00:00). Bei Counter-Spikes
                nach HA-Neustart kann die „neu"-Spalte auseinanderlaufen — vor dem Übernehmen prüfen.
              </p>
            </div>
          )}

          {/* Stundentabelle */}
          <div className="overflow-x-auto max-h-96 border border-gray-200 dark:border-gray-700 rounded">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-100 dark:bg-gray-800 z-10">
                <tr>
                  <th rowSpan={2} className="px-2 py-1 text-left">Stunde</th>
                  {kategorien.map(k => (
                    <th key={k} colSpan={2} className="px-2 py-1 text-center border-l border-gray-200 dark:border-gray-700">
                      {KAT_LABELS[k] || k}
                    </th>
                  ))}
                </tr>
                <tr>
                  {kategorien.map(k => (
                    <Fragment key={k}>
                      <th className="px-2 py-1 text-right border-l border-gray-200 dark:border-gray-700 text-gray-500">Alt</th>
                      <th className="px-2 py-1 text-right text-gray-500">Neu</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 24 }, (_, h) => h).map(h => (
                  <tr
                    key={h}
                    className={h === 0 ? 'bg-blue-50 dark:bg-blue-900/20' : 'odd:bg-gray-50 dark:odd:bg-gray-700/30'}
                  >
                    <td className="px-2 py-1 font-medium tabular-nums">
                      {String(h).padStart(2, '0')}:00
                      {h === 0 && (
                        <span className="ml-1 text-[10px] text-blue-600 dark:text-blue-400" title="Slot 0 = Wert(00:00) − Wert(Vortag 23:00)">
                          ↤ Vortag
                        </span>
                      )}
                    </td>
                    {kategorien.map(k => {
                      const cell = slotIndex.get(`${h}|${k}`)
                      const alt = cell?.alt ?? null
                      const neu = cell?.neu ?? null
                      return (
                        <Fragment key={k}>
                          <td className="px-2 py-1 text-right tabular-nums border-l border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400">
                            {fmtKwh(alt)}
                          </td>
                          <td className={`px-2 py-1 text-right tabular-nums ${diffClass(alt, neu)}`}>
                            {fmtKwh(neu)}
                          </td>
                        </Fragment>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            Auffällige Differenzen sind orange markiert ({'>'} 0.1 kWh) bzw. fett ({'>'} 1 kWh).
            Übernahme schreibt 26 Snapshots (Vortag 23:00 bis Folgetag 00:00) und rechnet
            den Tag neu.
          </p>

          {snapshotsAreCurrent && (
            <Alert type="info" className="mt-3">
              <Info className="inline w-4 h-4 mr-1" />
              Alle Werte stimmen überein — die Snapshots sind bereits aktuell.
              <strong className="ml-1">„Nur neu rechnen"</strong> reicht
              (schnell, kein HA-Polling).
            </Alert>
          )}

          {/* Restzeit-Anzeige während applying */}
          {applying && (
            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/30 rounded text-sm">
              <Loader2 className="inline w-4 h-4 mr-2 animate-spin text-blue-600 dark:text-blue-400" />
              {applyMode === 'with_resnap'
                ? <>HA-Werte ziehen + Tag neu rechnen … läuft seit <strong>{Math.floor(applyElapsedMs / 1000)} s</strong> (typisch ~30 s).</>
                : <>Tag neu rechnen … läuft seit <strong>{Math.floor(applyElapsedMs / 1000)} s</strong> (typisch ~2 s).</>
              }
              {forceCloseAvailable && (
                <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                  Backend hängt offenbar — Modal kann jetzt geschlossen werden,
                  der Job läuft im Hintergrund weiter. Bitte in ein paar Minuten
                  die Vorschau erneut öffnen, um den Endzustand zu prüfen.
                </p>
              )}
            </div>
          )}

          {/* Aktionen — zwei Apply-Buttons (Etappe 3c P4):
              1) "Aus HA neu laden + neu rechnen" (Default, mit_resnap=true)
              2) "Nur neu rechnen" (mit_resnap=false)
              Auto-Erkennung snapshotsAreCurrent setzt visuelle Empfehlung,
              aber beide Wege bleiben immer wählbar. */}
          <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
            <Button
              variant="secondary"
              onClick={handleClose}
              disabled={applying && !forceCloseAvailable}
            >
              {applying && forceCloseAvailable ? 'Im Hintergrund weiterlaufen lassen' : 'Abbrechen'}
            </Button>
            <Button
              variant={snapshotsAreCurrent ? 'primary' : 'secondary'}
              onClick={() => handleApply('rebuild_only')}
              disabled={applying}
              title={snapshotsAreCurrent
                ? 'Empfohlen: Snapshots sind bereits aktuell. Aggregat neu rechnen — schnell, kein HA-Polling.'
                : 'Aggregat aus den vorhandenen Snapshots neu rechnen, ohne HA-Statistics anzufragen.'}
            >
              {applyMode === 'rebuild_only' ? (
                <><Loader2 className="inline w-4 h-4 mr-1 animate-spin" />Rechne neu …</>
              ) : 'Nur neu rechnen'}
            </Button>
            <Button
              variant={snapshotsAreCurrent ? 'secondary' : 'primary'}
              onClick={() => handleApply('with_resnap')}
              disabled={applying || !data.ha_verfuegbar}
              title={data.ha_verfuegbar
                ? 'HA-Werte frisch ziehen, Snapshots überschreiben, Aggregat neu rechnen.'
                : 'HA-Statistics nicht erreichbar.'}
            >
              {applyMode === 'with_resnap' ? (
                <><Loader2 className="inline w-4 h-4 mr-1 animate-spin" />Übernehme …</>
              ) : 'Aus HA neu laden + neu rechnen'}
            </Button>
          </div>
        </>
      )}
    </Modal>
  )
}
