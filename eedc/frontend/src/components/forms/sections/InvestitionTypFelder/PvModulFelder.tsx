import { FormSection, Input } from '../../../ui'
import { fmtZahl } from '../../../../lib'
import type { TypFelderProps } from './types'

/**
 * PV-Modul: nur die optionalen Modul-Details. Die Kern-Felder (Leistung kWp,
 * Ausrichtung, Neigung) liegen in der `InvestitionForm`-Shell (direkte Spalten).
 */
export function PvModulFelder({ paramData, onInputChange, leistungKwp }: TypFelderProps) {
  const anzahl = parseInt(paramData.anzahl_module as string) || 0
  const wp = parseInt(paramData.modul_leistung_wp as string) || 0
  const berechnet = (anzahl * wp) / 1000
  // Querprüfung gegen das Shell-Feld (R22-2a, PN 89782): bisher stand die
  // Rechenprobe unverbunden neben der eingetragenen Leistung, die Abweichung
  // fiel erst dem Daten-Checker als anlagenweite Summe auf — dort ohne Bezug
  // zum verursachenden String. Toleranz 0,1 kWp = dieselbe wie im Checker
  // (`services/daten_checker/stammdaten.py`). Weich, nicht blockierend:
  // Modul-Details sind optional, die kWp bleibt der SoT.
  const eingetragen = parseFloat(leistungKwp ?? '')
  const weichtAb = berechnet > 0 && Number.isFinite(eingetragen) && eingetragen > 0
    && Math.abs(berechnet - eingetragen) > 0.1
  return (
    <FormSection
      variant="erweitert"
      title="Modul-Details (optional)"
      // Bei Abweichung offen starten — eine Warnung hinter dem zugeklappten
      // Chevron wäre keine. Vorhandene Klapp-Mechanik, kein neuer Schalter.
      defaultOpen={weichtAb}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <Input
          label="Anzahl Module"
          name="param_anzahl_module"
          type="number" step="1" min="1"
          value={paramData.anzahl_module as string}
          onChange={onInputChange}
          hint="Anzahl der PV-Module in diesem String"
        />
        <Input
          label="Leistung pro Modul (Wp)"
          name="param_modul_leistung_wp"
          type="number" step="1" min="0"
          value={paramData.modul_leistung_wp as string}
          onChange={onInputChange}
          hint="z.B. 400 Wp, 500 Wp"
        />
        <Input
          label="Modul-Typ"
          name="param_modul_typ"
          type="text"
          value={paramData.modul_typ as string}
          onChange={onInputChange}
          placeholder="z.B. Longi Hi-MO 5"
          hint="Hersteller und Modell"
        />
      </div>
      {berechnet > 0 && (
        weichtAb ? (
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-3">
            Berechnete Leistung: {fmtZahl(berechnet, 2)} kWp — weicht von der
            eingetragenen Leistung ({fmtZahl(eingetragen, 2)} kWp) ab. Anzahl,
            Leistung pro Modul oder das Feld „Leistung (kWp)" prüfen.
          </p>
        ) : (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
            Berechnete Leistung: {fmtZahl(berechnet, 2)} kWp
          </p>
        )
      )}
    </FormSection>
  )
}
