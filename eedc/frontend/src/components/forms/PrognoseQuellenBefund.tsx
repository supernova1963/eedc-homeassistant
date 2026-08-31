/**
 * PrognoseQuellenBefund — was die Auto-Erkennung der gewählten Prognosequelle
 * tatsächlich gefunden hat.
 *
 * ⭐ Anlass (Burkard, Issue #401, 2026-08-30): Bei ihm hießen sechs
 * SFML-Entities `sensor.none_*`, weil eine frühe SFML-Fassung den Gerätenamen
 * nicht setzte; die angezeigten Namen stimmten alle. Die Oberfläche sagte dazu
 * **nichts** — dass vier von sechs Rollen fehlten, war nur im Add-on-Container
 * zu sehen. Er hat genau dort nachgesehen und sich dann mit sechs
 * Template-Sensoren beholfen, die dieselben Werte unter den gesuchten Namen
 * spiegeln.
 *
 * ⚠ **Die Texte hier haben sich am 31.08.2026 mitgeändert, und das war Pflicht.**
 * Bis dahin stand hier dreimal „die Erkennung sucht an der Entity-ID" — das war
 * die Wahrheit des Tages und ist seit dem Umbau auf `integration_entities()` +
 * `unique_id` nur noch die **letzte** Stufe. Ein Hinweistext, der dem Anwender
 * eine überholte Ursache nennt, schickt ihn in die falsche Reparatur; er ist
 * genauso ein Fehler wie eine falsche Zahl.
 */
import { Alert } from '../ui'
import type { PrognoseQuellenStatus } from '../../api/aussichten'

const LABEL: Record<string, string> = { sfml: 'Solar Forecast ML', solcast: 'Solcast' }

export default function PrognoseQuellenBefund({ quelle, status }: {
  quelle: string
  status: Record<string, PrognoseQuellenStatus> | null
}) {
  if (quelle !== 'sfml' && quelle !== 'solcast') return null
  const s = status?.[quelle]
  if (!s) return null
  const name = LABEL[quelle] ?? quelle

  // Hat Home Assistant selbst gesagt, welche Entitäten zur Integration gehören?
  // Wenn nicht, gilt wieder die alte Namensliste — und nur dann ist „heißt deine
  // Entität anders?" überhaupt der richtige Rat.
  const ueberNamen = s.menge_quelle !== 'integration_entities'

  if (!s.gefunden) {
    return (
      <div className="mt-2">
        <Alert type="warning">
          <span className="font-medium">Keine {name}-Sensoren erkannt.</span>{' '}
          {s.fehler ?? (ueberNamen
            ? 'Home Assistant hat nicht mitgeteilt, welche Entitäten zu dieser Integration gehören — eedc sucht deshalb an der Entity-ID.'
            : 'Home Assistant kennt die Integration, meldet dafür aber keine Entitäten.')}{' '}
          {ueberNamen
            ? 'Heißen deine Entitäten anders, findet eedc sie auf diesem Weg nicht, auch wenn die angezeigten Namen stimmen.'
            : 'Ist die Integration eingerichtet und liefert sie Werte?'}
        </Alert>
      </div>
    )
  }

  const fehlend = s.rollen.filter(r => !r.gefunden)
  if (fehlend.length === 0) {
    return (
      <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
        {name}: alle {s.anzahl_gesamt} Sensoren erkannt
        {!ueberNamen ? ' — über die Integration, unabhängig von ihren Namen' : ''}.
      </p>
    )
  }

  return (
    <div className="mt-2 space-y-1">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {name}: <span className="font-medium">{s.anzahl_gefunden} von {s.anzahl_gesamt}</span> Sensoren erkannt.
      </p>
      {s.fehlend_wesentlich.length > 0 ? (
        <Alert type="warning">
          <span className="font-medium">Es fehlt: {s.fehlend_wesentlich.join(' · ')}.</span>{' '}
          Ohne Stundenprofil zeigt eedc für diese Quelle keinen verbleibenden Ertrag —
          statt einen aus einer anderen Quelle zu schätzen.{' '}
          {ueberNamen
            ? 'Home Assistant hat die Zugehörigkeit nicht mitgeteilt; eedc sucht deshalb an der Entity-ID und findet eine abweichend benannte Entität nicht.'
            : `eedc kennt ${s.anzahl_entities} Entitäten dieser Integration — diese Rolle ist nicht darunter. Liefert deine Version der Integration sie?`}
        </Alert>
      ) : (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Nicht erkannt: {fehlend.map(r => r.label).join(' · ')} — für die Anzeige nicht nötig.
        </p>
      )}
    </div>
  )
}
