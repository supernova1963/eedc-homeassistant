/**
 * Aufteilung des Stromverbrauchs nach Betriebsmodus (#263 K-2, S4 · Konzept §4).
 *
 * Eine Split-Klimaanlage heizt und kühlt über denselben Zähler. Wo eedc den
 * Betriebsmodus mitschreibt, kann es sagen, welcher Teil des Verbrauchs wohin
 * ging — hier steht diese Aufteilung, und **nur** hier ist sie eine eigene
 * Zahl. Sie ist eine **Teilmenge** des Gesamtverbrauchs und wird nirgends
 * aufaddiert (dieselbe Bauform wie `ladung_pv_kwh` bei der Wallbox).
 *
 * ⚠ **Ohne Modus-Signal erscheint dieser Block gar nicht** — statt mit Nullen.
 * Eine 0 hieße „hat nicht geheizt"; das weiß eedc ohne Sensor nicht
 * (ADR-002/P4, die N-258-Klasse, an der F-42 hing).
 */
import { fmtCalc } from '../ui'
import { VerteilungsBalken } from '../blocks'
import { ROLLEN_BG } from '../../lib'

/** Die Felder, die der Block braucht — Ausschnitt aus `WaermepumpeZusammenfassung`. */
export interface ModusSplitDaten {
  gesamt_stromverbrauch_kwh: number
  modus_strom_heizen_kwh?: number
  modus_strom_kuehlen_kwh?: number
  modus_nicht_aufgeteilt_kwh?: number
  modus_abdeckung_h?: number
  gesamt_heizenergie_kwh?: number
  waerme_abgeleitet?: boolean
  waerme_abgeleitet_faktor?: number | null
}

/** Hat dieses Gerät überhaupt eine Aufteilung? Auch der Hub-Block fragt das. */
export function hatModusSplit(z: ModusSplitDaten | undefined | null): boolean {
  return !!z && z.modus_abdeckung_h != null && z.modus_abdeckung_h > 0
}

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

function anteil(teil: number | undefined, gesamt: number): string {
  if (teil == null || !gesamt) return ''
  return ` (${fmtCalc((teil / gesamt) * 100, 0, '—')} %)`
}

export function WaermepumpeModusSplit({ zusammenfassung: z }: { zusammenfassung: ModusSplitDaten }) {
  const gesamt = z.gesamt_stromverbrauch_kwh || 0
  const heizen = z.modus_strom_heizen_kwh
  const kuehlen = z.modus_strom_kuehlen_kwh
  const rest = z.modus_nicht_aufgeteilt_kwh

  return (
    <div className="space-y-3">
      <VerteilungsBalken segmente={[
        { label: 'Heizen', wert: heizen ?? 0, farbe: ROLLEN_BG.heizung },
        { label: 'Kühlen', wert: kuehlen ?? 0, farbe: ROLLEN_BG.kuehlung },
        { label: 'Nicht aufgeteilt', wert: rest ?? 0, farbe: ROLLEN_BG.nicht_aufgeteilt },
      ]} />

      <dl className="text-sm space-y-1">
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">Strom gesamt</dt>
          <dd className="font-medium">{fmt(gesamt)} kWh</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">davon Heizen</dt>
          <dd>{fmt(heizen)} kWh{anteil(heizen, gesamt)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">davon Kühlen</dt>
          <dd>{fmt(kuehlen)} kWh{anteil(kuehlen, gesamt)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">nicht aufgeteilt</dt>
          <dd>{fmt(rest)} kWh{anteil(rest, gesamt)}</dd>
        </div>
        <div className="flex justify-between border-t border-gray-100 dark:border-gray-800 pt-1">
          <dt className="text-gray-600 dark:text-gray-400">Modus erfasst</dt>
          <dd>{fmt(z.modus_abdeckung_h, 0)} Stunden</dd>
        </div>
      </dl>

      {/* Die Wärme steht hier nur, wenn sie abgeleitet ist — als Wert MIT
          Herkunft. Gemessene Wärme hat ihren Platz in der Wärme-Aufteilung
          und braucht hier keine zweite Anzeige. */}
      {z.waerme_abgeleitet && z.gesamt_heizenergie_kwh != null && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Heizwärme {fmt(z.gesamt_heizenergie_kwh)} kWh — <strong>abgeleitet</strong> aus
          dem Heiz-Strom
          {z.waerme_abgeleitet_faktor != null && <> × {fmtCalc(z.waerme_abgeleitet_faktor, 2, '—')}</>}
          , nicht gemessen. Deshalb steht bei der JAZ „—": aus einer gerechneten
          Wärme kommt wieder genau der Faktor heraus, mit dem sie gerechnet wurde.
        </p>
      )}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        „Nicht aufgeteilt" ist Standby und alles, was weder Heizen noch Kühlen war
        (Lüften, Entfeuchten, Automatik ohne Rückmeldung) — dazu die Zeit, in der
        eedc keinen Modus mitlesen konnte. Die Aufteilung entsteht nur für Zeiten
        mit laufender Datenanbindung; rückwirkend gibt es sie nicht.
      </p>
    </div>
  )
}
