/**
 * PrognoseQuellenBefund — was die Auto-Erkennung der gewählten Prognosequelle
 * tatsächlich gefunden hat.
 *
 * ⭐ Anlass (Burkard, Issue #401, 2026-08-30): Die Erkennung matcht Entity-IDs
 * über Präfix und Suffix. Beides sind Konventionen des Integrationsautors, keine
 * Garantien — eine Entity-ID entsteht in Home Assistant beim ersten Anlegen und
 * wandert später nicht mit, wenn die Integration ihre Namen ändert. Bei ihm
 * hießen sechs SFML-Entities `sensor.none_*`, weil eine frühe SFML-Fassung den
 * Gerätenamen nicht setzte; die friendly names stimmten alle.
 *
 * Die Oberfläche sagte dazu **nichts**: entweder kamen Werte oder es gab eine
 * Fehlermeldung. Dass vier von sechs Rollen fehlten, war nur im Add-on-Container
 * zu sehen — er hat genau dort nachgesehen und sich dann mit sechs
 * Template-Sensoren beholfen, die dieselben Werte unter den gesuchten Namen
 * spiegeln.
 *
 * ⚠ Diese Anzeige behebt das nicht, sie macht es sichtbar. Das ist die
 * Voraussetzung dafür, dass jemand überhaupt etwas unternimmt: Wer nicht sieht,
 * dass etwas fehlt, sucht auch nicht danach.
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

  if (!s.gefunden) {
    return (
      <div className="mt-2">
        <Alert type="warning">
          <span className="font-medium">Keine {name}-Sensoren erkannt.</span>{' '}
          {s.fehler ?? 'Die Erkennung sucht Entitäten an ihrer Entity-ID.'} Heißen deine
          Entitäten anders — etwa weil die Integration ihre Namen später geändert hat —,
          findet eedc sie nicht, auch wenn die angezeigten Namen stimmen.
        </Alert>
      </div>
    )
  }

  const fehlend = s.rollen.filter(r => !r.gefunden)
  if (fehlend.length === 0) {
    return (
      <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
        {name}: alle {s.anzahl_gesamt} Sensoren erkannt.
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
          statt einen aus einer anderen Quelle zu schätzen. Die Erkennung sucht an der
          Entity-ID; stimmen bei dir nur die angezeigten Namen, findet sie die Entität nicht.
        </Alert>
      ) : (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Nicht erkannt: {fehlend.map(r => r.label).join(' · ')} — für die Anzeige nicht nötig.
        </p>
      )}
    </div>
  )
}
