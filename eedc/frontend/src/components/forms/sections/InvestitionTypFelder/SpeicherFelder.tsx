import { FormSection, Input, Select } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import {
  SPEICHER_KOPPLUNG_LABELS,
  SOC_LEER_PROZENT,
  aufgeloesteSpeicherKopplung,
  leerSchwelleProzent,
} from '../../../../lib/investitionParameter'
import { fmtZahl } from '../../../../lib/einheiten'
import type { TypFelderProps } from './types'

// #351: Die Kopplung ist eine eigene Eigenschaft, keine Folgerung aus der
// Wechselrichter-Zuordnung. Der leere Wert bleibt wählbar und ist die
// Vorbelegung — er sagt „eedc leitet ab", und was daraus folgt, steht im Hint.
const KOPPLUNG_OPTIONEN = [
  { value: '', label: 'Automatisch (aus der Zuordnung)' },
  { value: 'ac', label: SPEICHER_KOPPLUNG_LABELS.ac },
  { value: 'dc', label: SPEICHER_KOPPLUNG_LABELS.dc },
]

export function SpeicherFelder({ paramData, onInputChange, setParam, hatZuordnung }: TypFelderProps) {
  const arbitrage = paramData.arbitrage_faehig as boolean
  const kopplung = (paramData.kopplung as string) || ''
  const abgeleitet = SPEICHER_KOPPLUNG_LABELS[aufgeloesteSpeicherKopplung({}, !!hatZuordnung)]
  // #379 (cbrosius): Aus der nutzbaren Kapazitaet leitet eedc die Entladegrenze
  // ab und faellt damit das Urteil unter „Groesserer Speicher?" — am Eingabefeld
  // stand davon nichts, sein einziger Hinweis („Typisch 90-95 %") zeigte sogar
  // in die Gegenrichtung jedes Anwenders mit eigener Untergrenze. Bauform wie
  // bei `kopplung` weiter unten: die Ableitung steht im Hint, nicht in einem
  // zweiten Feld (Entscheid Gernot 15.08.).
  const brutto = Number(paramData.kapazitaet_kwh)
  const nutzbar = Number(paramData.nutzbare_kapazitaet_kwh)
  const leerSchwelle = leerSchwelleProzent(brutto || null, nutzbar || null)
  const grenzeAbgeleitet = leerSchwelle > SOC_LEER_PROZENT
  const reserveProzent = grenzeAbgeleitet ? (1 - nutzbar / brutto) * 100 : null
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
            hint={grenzeAbgeleitet
              ? `⇒ Entladegrenze ${fmtZahl(reserveProzent, 0)} % — eedc wertet den Speicher ab `
                + `${fmtZahl(leerSchwelle, 0)} % Ladestand als leer (Wirtschaftlichkeit → „Größerer Speicher?“). `
                + 'Dabei nimmt es an, dass die gesamte Reserve unten liegt — fährst du zusätzlich eine obere '
                + 'Ladegrenze, ist diese Untergrenze zu hoch.'
              : 'Typisch 90-95 % der Gesamtkapazität — der ganze Hub, der durch den Speicher geht. Daraus leitet eedc die Entladegrenze ab.'}
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
          <Select
            label="Kopplung"
            name="param_kopplung"
            value={kopplung}
            onChange={(e) => setParam('kopplung', e.target.value)}
            options={KOPPLUNG_OPTIONEN}
            hint={kopplung === ''
              ? `Ohne Angabe: ${abgeleitet} — abgeleitet aus der Wechselrichter-Zuordnung. Ein AC-Speicher am Hybrid-Wechselrichter braucht die Angabe.`
              : 'Bestimmt, an welcher Stelle Ladung und Entladung gemessen werden — die Zuordnung zum Wechselrichter bleibt davon unberührt.'}
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
          {/* #397 (MeinerB): Der Daten-Checker fordert beide Preise, sobald
              Arbitrage an ist — pflegbar waren sie bis dahin nirgends, sein
              Beheben-Link führte in dieses Formular ohne die Felder. Bewusst
              OHNE Vorbelegung (Bauform von `kopplung` darüber und #331): leer
              heißt „nicht gepflegt", und genau das meldet der Checker zu
              Recht. Der Richtwert steht im Hint statt im Feld — vorbelegt
              würde er beim ersten Speichern zur gepflegten Zahl, die niemand
              bestätigt hat. */}
          {arbitrage && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
              <Input
                label="Ø Ladepreis (ct/kWh)"
                name="param_lade_durchschnittspreis_cent"
                type="number" step="any" min="0"
                value={paramData.lade_durchschnittspreis_cent as string}
                onChange={onInputChange}
                hint="Was die Kilowattstunde beim Netzladen im Niedrigtarif kostet. Ohne Angabe rechnet eedc mit 12 ct/kWh."
              />
              <Input
                label="Ø Entladepreis (ct/kWh)"
                name="param_entlade_vermiedener_preis_cent"
                type="number" step="any" min="0"
                value={paramData.entlade_vermiedener_preis_cent as string}
                onChange={onInputChange}
                hint="Der Preis, den das Entladen dir erspart. Ohne Angabe rechnet eedc mit 35 ct/kWh."
              />
            </div>
          )}
        </div>
      </FormSection>
    </>
  )
}
