import { FormSection, Input, Select, Alert, RadioGroup } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import type { TypFelderProps } from './types'

const WP_ART_OPTIONEN = [
  { value: 'luft_wasser', label: 'Luft-Wasser (Außenluft → Wasser)' },
  { value: 'sole_wasser', label: 'Sole-Wasser (Erdwärme → Wasser)' },
  { value: 'grundwasser', label: 'Grundwasser-Wärmepumpe' },
  { value: 'luft_luft', label: 'Luft-Luft (Klimaanlage)' },
]

const VORLAUF_OPTIONEN = [
  { value: '35', label: '35 °C (Fußbodenheizung)' },
  { value: '55', label: '55 °C (Heizkörper)' },
]

const ENERGIETRAEGER_OPTIONEN = [
  { value: 'gas', label: 'Erdgas' },
  { value: 'oel', label: 'Heizöl' },
  { value: 'strom', label: 'Strom (Direktheizung)' },
]

const MODUS_OPTIONEN = [
  {
    value: 'gesamt_jaz',
    label: 'Jahresarbeitszahl (JAZ) – Gemessen vor Ort',
    description: 'Gemessene Jahresarbeitszahl am eigenen Standort – der genaueste Wert, wenn verfügbar.',
  },
  {
    value: 'scop',
    label: 'SCOP (EU-Energielabel) – Aus Datenblatt',
    description: 'EU-genormter SCOP vom Energielabel – realistischer als Hersteller-COP, aber standortunabhängig.',
  },
  {
    value: 'getrennte_cops',
    label: 'Getrennte COPs (Heizung/Warmwasser)',
    description: 'Separate COPs für Heizung (~3,9) und Warmwasser (~3,0) – präziser bei unterschiedlichen Betriebspunkten.',
  },
] as const

export function WaermepumpeFelder({ paramData, onInputChange, setParam, zeige, markTouched, setFeldRef }: TypFelderProps) {
  const modus = paramData.effizienz_modus as string
  return (
    <>
      <FormSection title="Wärmepumpe">
        <div className="space-y-4">
          <Select
            label="Wärmepumpenart"
            name="param_wp_art"
            value={paramData.wp_art as string}
            onChange={(e) => setParam('wp_art', e.target.value)}
            options={WP_ART_OPTIONEN}
            hint="Wird für den fairen JAZ-Vergleich in der Community verwendet"
          />
          {paramData.wp_art === 'luft_luft' && (
            <Alert type="info" title="Split-Klimaanlage">
              Es genügt der Stromverbrauchs-Sensor. Heizenergie/Warmwasser sind bei Klimas meist nicht gemessen —
              die JAZ-Kachel bleibt dann leer („—"), die Stromauswertung funktioniert trotzdem.
              Heizwärme- und Warmwasserbedarf werden deshalb nicht abgefragt, und eine Ersparnis
              gegenüber Gas oder Öl weist eedc für Klimaanlagen nicht aus — dafür müsste das Gerät
              eine Heizung ersetzt haben und die Wärme gemessen sein.
            </Alert>
          )}

          <RadioGroup
            label="Berechnungsmodus für Effizienz"
            name="param_effizienz_modus"
            options={MODUS_OPTIONEN}
            value={modus}
            onChange={(v) => setParam('effizienz_modus', v)}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            <Input
              label="Nennleistung (kW)"
              name="param_leistung_kw"
              type="number" step="any" min="0"
              value={paramData.leistung_kw as string}
              onChange={onInputChange}
              hint="Thermische Leistung"
            />

            {modus === 'gesamt_jaz' && (
              <div ref={setFeldRef('jaz')}>
                <Input
                  label="Jahresarbeitszahl (JAZ)"
                  name="param_jaz"
                  type="number" step="any" min="1" max="10"
                  value={paramData.jaz as string}
                  onChange={onInputChange}
                  onBlur={() => markTouched('jaz')}
                  hint="Typisch 3-4 für Luft-WP, 4-5 für Sole-WP"
                  required
                  error={zeige('jaz')}
                />
              </div>
            )}

            {modus === 'scop' && (
              <>
                <div ref={setFeldRef('scop_heizung')}>
                  <Input
                    label="SCOP Heizung"
                    name="param_scop_heizung"
                    type="number" step="any" min="1" max="10"
                    value={paramData.scop_heizung as string}
                    onChange={onInputChange}
                    onBlur={() => markTouched('scop_heizung')}
                    hint="Vom EU-Energielabel (z.B. 4,5)"
                    required
                    error={zeige('scop_heizung')}
                  />
                </div>
                <div ref={setFeldRef('scop_warmwasser')}>
                  <Input
                    label="SCOP Warmwasser"
                    name="param_scop_warmwasser"
                    type="number" step="any" min="1" max="10"
                    value={paramData.scop_warmwasser as string}
                    onChange={onInputChange}
                    onBlur={() => markTouched('scop_warmwasser')}
                    hint="Typisch 2,8-3,5"
                    required
                    error={zeige('scop_warmwasser')}
                  />
                </div>
                <Select
                  label="Vorlauftemperatur (EU-Label)"
                  name="param_vorlauftemperatur"
                  value={paramData.vorlauftemperatur as string}
                  onChange={(e) => setParam('vorlauftemperatur', e.target.value)}
                  options={VORLAUF_OPTIONEN}
                  hint="SCOP-Wert muss zur Vorlauftemperatur passen"
                />
              </>
            )}

            {modus === 'getrennte_cops' && (
              <>
                <div ref={setFeldRef('cop_heizung')}>
                  <Input
                    label="COP Heizung"
                    name="param_cop_heizung"
                    type="number" step="any" min="1" max="10"
                    value={paramData.cop_heizung as string}
                    onChange={onInputChange}
                    onBlur={() => markTouched('cop_heizung')}
                    hint="Typisch 3,5-4,5 (Vorlauf 35 °C)"
                    required
                    error={zeige('cop_heizung')}
                  />
                </div>
                <div ref={setFeldRef('cop_warmwasser')}>
                  <Input
                    label="COP Warmwasser"
                    name="param_cop_warmwasser"
                    type="number" step="any" min="1" max="10"
                    value={paramData.cop_warmwasser as string}
                    onChange={onInputChange}
                    onBlur={() => markTouched('cop_warmwasser')}
                    hint="Typisch 2,5-3,5 (Vorlauf 55 °C)"
                    required
                    error={zeige('cop_warmwasser')}
                  />
                </div>
              </>
            )}

            {/* #263 (3dmaster90) / N-87: Bei einer Split-Klimaanlage gibt es
                weder einen Warmwasserkreis noch einen Heizwärmebedarf aus dem
                Energieausweis. Beide Felder waren mit 12.000/3.000 kWh
                vorbelegt, und die ROI-Auswertung rechnete daraus eine Ersparnis
                gegen eine nie ersetzte Gasheizung. Bei `luft_luft` daher gar
                nicht erst fragen. Bereits gespeicherte Werte bleiben stehen —
                die Klima-Unterstützung ist nicht abgeschlossen (#263), da wird
                nichts weggeworfen, was später noch gebraucht werden könnte. */}
            {paramData.wp_art !== 'luft_luft' && (
              <>
                <Input
                  label="Heizwärmebedarf (kWh/Jahr)"
                  name="param_heizwaermebedarf_kwh"
                  type="number" step="any" min="0"
                  value={paramData.heizwaermebedarf_kwh as string}
                  onChange={onInputChange}
                  hint="Aus Energieausweis oder Schätzung"
                />
                <Input
                  label="Warmwasserbedarf (kWh/Jahr)"
                  name="param_warmwasserbedarf_kwh"
                  type="number" step="any" min="0"
                  value={paramData.warmwasserbedarf_kwh as string}
                  onChange={onInputChange}
                  hint="~500 kWh/Person/Jahr typisch"
                />
              </>
            )}
          </div>

          <SchalterZeile
            checked={paramData.getrennte_strommessung === 'true'}
            onChange={(an) => setParam('getrennte_strommessung', an ? 'true' : 'false')}
            label="Getrennte Strommessung (Heizen / Warmwasser)"
            hint="Aktivieren wenn separate Stromzähler für Heizung und Warmwasser vorhanden sind. Ermöglicht getrennte COP-Berechnung."
          />
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Vergleich mit alter Heizung (ROI)">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
          <Select
            label="Alter Energieträger"
            name="param_alter_energietraeger"
            value={paramData.alter_energietraeger as string}
            onChange={(e) => setParam('alter_energietraeger', e.target.value)}
            options={ENERGIETRAEGER_OPTIONEN}
          />
          <Input
            label="Alter Preis (ct/kWh)"
            name="param_alter_preis_cent_kwh"
            type="number" step="any" min="0"
            value={paramData.alter_preis_cent_kwh as string}
            onChange={onInputChange}
            hint="Gas ~12 ct, Öl ~10 ct"
          />
          <Input
            label="PV-Anteil (%)"
            name="param_pv_anteil_prozent"
            type="number" step="1" min="0" max="100"
            value={paramData.pv_anteil_prozent as string}
            onChange={onInputChange}
            hint="Anteil des WP-Stroms aus PV"
          />
          <Input
            label="Zusatzkosten Alt-Heizung (€/Jahr)"
            name="param_alternativ_zusatzkosten_jahr"
            type="number" step="1" min="0"
            value={paramData.alternativ_zusatzkosten_jahr as string}
            onChange={onInputChange}
            hint="Schornsteinfeger, Wartung, Grundpreis Gaszähler etc."
          />
        </div>
        <div className="mt-4">
          <SchalterZeile
            checked={paramData.sg_ready as boolean}
            onChange={(an) => setParam('sg_ready', an)}
            label="SG Ready (Smart Grid fähig)"
          />
        </div>
      </FormSection>
    </>
  )
}
