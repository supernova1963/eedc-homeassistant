import { FormSection, Input, Select, Alert } from '../../../ui'
import { fmtZahl } from '../../../../lib'
import { AUSRICHTUNG_OPTIONEN } from '../investitionFormHelpers'
import { SchalterZeile } from '../SchalterZeile'
import type { TypFelderProps } from './types'

export function BalkonkraftwerkFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  const anzahl = parseInt(paramData.anzahl as string) || 0
  const wp = parseInt(paramData.leistung_wp as string) || 0
  const kwp = (anzahl * wp) / 1000
  return (
    <>
      <FormSection title="Balkonkraftwerk">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <Input
            label="Anzahl Module"
            name="param_anzahl"
            type="number" step="1" min="1"
            value={paramData.anzahl as string}
            onChange={onInputChange}
          />
          <Input
            label="Leistung pro Modul (Wp)"
            name="param_leistung_wp"
            type="number" step="1" min="0"
            value={paramData.leistung_wp as string}
            onChange={onInputChange}
            hint={kwp > 0 ? `= ${fmtZahl(kwp, 2)} kWp` : undefined}
          />
          <Select
            label="Ausrichtung"
            name="param_ausrichtung"
            value={paramData.ausrichtung as string}
            onChange={(e) => setParam('ausrichtung', e.target.value)}
            options={AUSRICHTUNG_OPTIONEN}
          />
          <Input
            label="Neigung (Grad)"
            name="param_neigung_grad"
            type="number" step="1" min="0" max="90"
            value={paramData.neigung_grad as string}
            onChange={onInputChange}
            hint="0° = flach, 90° = senkrecht"
          />
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Speicher">
        <div className="space-y-3">
          <SchalterZeile
            checked={paramData.hat_speicher as boolean}
            onChange={(an) => setParam('hat_speicher', an)}
            label="Mit Speicher (z.B. Anker SOLIX)"
          />
          {paramData.hat_speicher && (
            <>
              <Input
                label="Speicher-Kapazität (Wh)"
                name="param_speicher_kapazitaet_wh"
                type="number" step="1" min="0"
                value={paramData.speicher_kapazitaet_wh as string}
                onChange={onInputChange}
                hint="z.B. 1600 Wh für Anker SOLIX"
              />
              <Alert type="warning">
                Für vollständige Auswertungen (Live-Dashboard, Cockpit, Tagesverlauf) bitte den Speicher
                zusätzlich als separate <strong>Speicher-Investition</strong> erfassen und dort die
                Batterieleistung sowie den SoC-Sensor zuordnen.
              </Alert>
            </>
          )}
        </div>
      </FormSection>
    </>
  )
}
