/**
 * JahrRahmen — Sicht-Rahmen der Cockpit/Jahr-Sicht. {@link JahrHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (Jahr) + Status-Badge (läuft/abgeschlossen)
 * + Aktualisieren + Quellen-Provenance (aus `feld_quellen` der aggregierten Monate).
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { ReloadButton } from './ReloadButton'
import { PROVENANZ_BADGE, provenanzQuellen, ProvenanzQuellenZeile } from './ProvenanzQuellen'
import { LAUFEND_ZUSTAND } from '../lib'

export function JahrHeader({ jahr, laedtJahr, laufend, d, onReload, reloading }: {
  /** Das Jahr, zu dem die Zahlen unter dem Kopf gehören — nicht zwingend das gewählte. */
  jahr: number
  /**
   * Das **gewählte** Jahr, solange seine Zahlen noch laden (sonst `null`).
   * Dieselbe Bauform wie `TagHeader.laedtTag` und `MonatHeader.laedtTitel`.
   */
  laedtJahr?: number | null
  laufend: boolean
  d: AktuellerMonatResponse | null
  onReload?: () => void
  reloading?: boolean
}) {
  // #360/E3 bewusst OHNE Monatskontext: die Jahresroute faltet zwölf Monate zu
  // EINER Badge-Liste. Ein Connector-Zeitraum je Quelle wäre hier entweder falsch
  // (welcher Monat?) oder eine Liste von zwölf — die Teilabdeckung gehört in die
  // Monats-Sicht, wo sie zu genau einem Wert gehört.
  const quellen = d ? provenanzQuellen(d.feld_quellen) : []
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{jahr}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? LAUFEND_ZUSTAND.badge
            : 'bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'läuft' : 'abgeschlossen'}
        </span>
        {laedtJahr != null && (
          <span
            className={PROVENANZ_BADGE}
            title="Die Zahlen gehören noch zum angezeigten Jahr. Sobald das gewählte Jahr geladen ist, wechselt die ganze Sicht auf einmal."
          >
            lädt {laedtJahr} …
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {laufend && onReload && <ReloadButton onClick={onReload} loading={!!reloading} />}
        <ProvenanzQuellenZeile quellen={quellen} />
      </div>
    </div>
  )
}
