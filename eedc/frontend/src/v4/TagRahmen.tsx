/**
 * TagRahmen — Sicht-Rahmen der Cockpit/Tag-Sicht. {@link TagHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (langes Datum) + Status-Badge
 * (heute/abgeschlossen) + Aktualisieren + Quellen-Provenance (`TagWerte.datenquelle`).
 */
import type { TagWerte } from '../api/energie_profil'
import { ReloadButton } from './ReloadButton'
// R3b S7: Provenance-Labels + Wochentage aus der SoT (vorher 3 gedriftete lokale Kopien).
import { DATENQUELLE_LABELS, WT_LANG } from '../lib/constants'
// #360: die Quellen-Zeile selbst liegt seither auch nur noch einmal.
import { PROVENANZ_BADGE, ProvenanzQuellenZeile } from './ProvenanzQuellen'
import { LAUFEND_ZUSTAND } from '../lib'

function langesDatum(iso: string): string {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_LANG[d.getDay()]}, ${d.toLocaleDateString('de-DE', { day: '2-digit', month: 'long', year: 'numeric' })}`
}

export function TagHeader({ datum, laufend, tag, onReload, reloading }: {
  datum: string
  laufend: boolean
  tag: TagWerte | null
  onReload?: () => void
  reloading?: boolean
}) {
  const quelle = tag?.datenquelle ? (DATENQUELLE_LABELS[tag.datenquelle] ?? tag.datenquelle) : null
  // F3 (2026-07-29): Am laufenden Tag steht die Tages-Sicht auf den
  // abgeschlossenen Stunden, Live „Heute" zählt die laufende bereits mit —
  // gemessen an Anlage 1 waren das 1,5 kWh Unterschied bei identischer Quelle.
  // Sachlich richtig, aber nirgends ausgewiesen: der Badge sagte nur
  // „Quellen: gespeichert". `stunden_verfuegbar` ist eine ZÄHLUNG verbuchter
  // Stunden, keine Uhrzeit — deshalb „n von 24 Std." statt „Stand 16:00":
  // bei einer Lücke mitten am Tag wäre die Uhrzeit eine falsche Behauptung.
  const stand = laufend && tag && tag.stunden_verfuegbar > 0 && tag.stunden_verfuegbar < 24
    ? tag.stunden_verfuegbar
    : null
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{langesDatum(datum)}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? LAUFEND_ZUSTAND.badge
            : 'bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'heute' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {onReload && <ReloadButton onClick={onReload} loading={!!reloading} />}
        {stand != null && (
          <span
            className={PROVENANZ_BADGE}
            title="Die Tages-Sicht steht auf den abgeschlossenen Stunden. Die laufende Stunde wird erst nach ihrem Ende verbucht — Live „Heute“ zählt sie bereits mit."
          >
            Stand: {stand} von 24 Std. · laufende Stunde fehlt
          </span>
        )}
        <ProvenanzQuellenZeile quellen={quelle ? [{ label: quelle }] : []} />
      </div>
    </div>
  )
}
