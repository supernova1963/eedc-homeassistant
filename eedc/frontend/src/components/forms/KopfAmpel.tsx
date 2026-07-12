/**
 * KopfAmpel — Vollständigkeits-Überblick des Monatsabschlusses (V4 §6.2, F2).
 *
 * „✅ n gemessen · ⚠ n prüfen · ◯ n offen" statt Step-Zähler. Klick auf „n offen"
 * springt zum ersten offenen (gezählten) Feld/Block (`data-erfassung-offen`).
 * Icon/Farbe aus dem einen Zustands-Vokabular (ZUSTAND_META + ERFASSUNG_ZUSTAND).
 */
import type { AmpelZaehlung } from '../../lib/erfassungZustand'
import { ERFASSUNG_ZUSTAND } from '../../lib/colors'
import { ZUSTAND_META } from '../ui'

export default function KopfAmpel({
  ampel,
  onSpringeZuOffen,
}: {
  ampel: AmpelZaehlung
  onSpringeZuOffen: () => void
}) {
  const Fertig = ZUSTAND_META.gemessen.Icon
  const Pruefen = ZUSTAND_META.geschaetzt.Icon
  const Offen = ZUSTAND_META.fehlt.Icon
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm font-medium">
      <span className={`inline-flex items-center gap-1 ${ERFASSUNG_ZUSTAND.gemessen.text}`}>
        <Fertig className="w-4 h-4" /> {ampel.fertig} fertig
      </span>
      <span className={`inline-flex items-center gap-1 ${ERFASSUNG_ZUSTAND.geschaetzt.text}`}>
        <Pruefen className="w-4 h-4" /> {ampel.pruefen} prüfen
      </span>
      {ampel.offen > 0 ? (
        <button
          type="button"
          onClick={onSpringeZuOffen}
          className={`inline-flex items-center gap-1 hover:underline ${ERFASSUNG_ZUSTAND.fehlt.text}`}
        >
          <Offen className="w-4 h-4" /> {ampel.offen} offen
        </button>
      ) : (
        <span className={`inline-flex items-center gap-1 ${ERFASSUNG_ZUSTAND.fehlt.text}`}>
          <Offen className="w-4 h-4" /> 0 offen
        </span>
      )}
    </div>
  )
}
