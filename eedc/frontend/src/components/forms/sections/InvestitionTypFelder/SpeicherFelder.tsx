import { FormSection, Input } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import type { TypFelderProps } from './types'

export function SpeicherFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  const arbitrage = paramData.arbitrage_faehig as boolean
  return (
    <>
      <FormSection title="Speicher">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <Input
            label="Kapazität (kWh)"
            name="param_kapazitaet_kwh"
            type="number" step="any" min="0"
            value={paramData.kapazitaet_kwh as string}
            onChange={onInputChange}
          />
          <Input
            label="Nutzbare Kapazität (kWh)"
            name="param_nutzbare_kapazitaet_kwh"
            type="number" step="any" min="0"
            value={paramData.nutzbare_kapazitaet_kwh as string}
            onChange={onInputChange}
            hint="Typisch 90-95 % der Gesamtkapazität"
          />
          <Input
            label="Max. Ladeleistung (kW)"
            name="param_max_ladeleistung_kw"
            type="number" step="any" min="0"
            value={paramData.max_ladeleistung_kw as string}
            onChange={onInputChange}
          />
          <Input
            label="Max. Entladeleistung (kW)"
            name="param_max_entladeleistung_kw"
            type="number" step="any" min="0"
            value={paramData.max_entladeleistung_kw as string}
            onChange={onInputChange}
          />
          <Input
            label="Wirkungsgrad (%)"
            name="param_wirkungsgrad_prozent"
            type="number" step="any" min="0" max="100"
            value={paramData.wirkungsgrad_prozent as string}
            onChange={onInputChange}
          />
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Netzladung & Arbitrage">
        <div className="space-y-3">
          <SchalterZeile
            checked={(paramData.laedt_aus_netz as boolean) || arbitrage}
            disabled={arbitrage}
            onChange={(an) => setParam('laedt_aus_netz', an)}
            label="Lädt aus dem Netz (z. B. Backup-/Notladung)"
            hint={arbitrage ? 'Automatisch aktiv durch Arbitrage' : undefined}
          />
          <SchalterZeile
            checked={arbitrage}
            onChange={(an) => setParam('arbitrage_faehig', an)}
            label="Arbitrage-fähig (Netzladen bei Niedrigtarif)"
          />
        </div>
      </FormSection>
    </>
  )
}
