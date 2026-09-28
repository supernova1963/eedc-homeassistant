import { FormSection, Input, Select } from '../../../ui'
import { istZaehlerKategorie } from '../../../../lib/fieldDefinitions'
import { PARAM_SONSTIGES_DEFAULTS, ZAEHLER_ARTEN, ZAEHLER_EINHEITEN } from '../../../../lib/investitionParameter'
import type { TypFelderProps } from './types'

// N-573: Der leere Wert bleibt wählbar und ist die Vorbelegung (Bauform
// `KOPPLUNG_OPTIONEN` in SpeicherFelder, #351) — er sagt „eedc ordnet ein",
// und wie weit diese Einordnung reicht, steht im Hint.
const KATEGORIE_OPTIONEN = [
  { value: '', label: 'Automatisch (nach den Monatswerten)' },
  { value: 'erzeuger', label: 'Erzeuger (z.B. Mini-BHKW, Mini-Wind)' },
  { value: 'verbraucher', label: 'Verbraucher (z.B. Klimaanlage, Pool)' },
  { value: 'abgabe', label: 'Abgabe an Dritte (Mieterstrom, Allgemeinstrom — Zähler an der Übergabestelle)' },
  { value: 'speicher', label: 'Speicher (z.B. Wasserstoff)' },
  // #377 — der dritte Zustand: weder Erzeuger noch Verbraucher.
  { value: 'zaehler', label: 'Verbrauchszähler (Gas, Wasser, Heizöl — wird nur erfasst)' },
]

const ZAEHLER_ART_LABEL: Record<string, string> = {
  gas: 'Gas',
  wasser: 'Wasser',
  heizoel: 'Heizöl',
  pellets: 'Pellets',
  fluessiggas: 'Flüssiggas',
  sonstiges: 'Sonstiges',
}

const ZAEHLER_ART_OPTIONEN = ZAEHLER_ARTEN.map((wert) => ({
  value: wert,
  label: ZAEHLER_ART_LABEL[wert] ?? wert,
}))

const ZAEHLER_EINHEIT_OPTIONEN = ZAEHLER_EINHEITEN.map((wert) => ({
  value: wert,
  label: wert,
}))

export function SonstigesFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  const kategorie = (paramData.kategorie as string) || ''
  const istZaehler = istZaehlerKategorie(kategorie)

  return (
    <FormSection title="Sonstige Investition">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <Select
          label="Kategorie"
          name="param_kategorie"
          value={kategorie}
          onChange={(e) => setParam('kategorie', e.target.value)}
          options={KATEGORIE_OPTIONEN}
          // Beide Wahrheitsgrenzen der Automatik (N-250 · Tages-Σ · Live-Serie),
          // damit „Automatisch" nicht mehr verspricht, als die Leser halten.
          hint={kategorie === ''
            ? 'Ohne Wahl ordnet eedc das Gerät in den Monatsauswertungen nach seinen erfassten Werten '
              + 'als Erzeuger oder Verbraucher ein; in der Live- und Tagesansicht zählt es als Verbraucher. '
              + 'Verbrauchszähler, Abgabe an Dritte und Speicher müssen gewählt werden.'
            : 'Bestimmt welche Monatsdaten erfasst werden'}
        />
        <Input
          label="Beschreibung"
          name="param_beschreibung"
          value={paramData.beschreibung as string}
          onChange={onInputChange}
          placeholder={istZaehler ? 'z.B. Gaszähler Keller' : 'z.B. Mini-Blockheizkraftwerk Viessmann'}
          hint="Kurze Beschreibung der Investition"
        />
      </div>

      {istZaehler && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start mt-4">
            <Select
              label="Was wird gezählt?"
              name="param_zaehler_art"
              value={(paramData.zaehler_art as string) || PARAM_SONSTIGES_DEFAULTS.zaehler_art}
              onChange={(e) => setParam('zaehler_art', e.target.value)}
              options={ZAEHLER_ART_OPTIONEN}
              hint="Nur für Bezeichnung und Symbol"
            />
            <Select
              label="Einheit"
              name="param_zaehler_einheit"
              value={(paramData.zaehler_einheit as string) || PARAM_SONSTIGES_DEFAULTS.zaehler_einheit}
              onChange={(e) => setParam('zaehler_einheit', e.target.value)}
              options={ZAEHLER_EINHEIT_OPTIONEN}
              hint="Steht neben der Zahl — eedc rechnet nichts um"
            />
          </div>
          <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">
            <strong>Ein Verbrauchszähler wird erfasst und angezeigt, aber nicht bewertet.</strong>{' '}
            eedc führt den <strong>Zählerstand</strong> mit und zeigt, wie weit er sich im
            gewählten Zeitraum bewegt hat. In Energiebilanz, Autarkie, Wirtschaftlichkeit,
            CO₂-Bilanz und den Gemeinschaftsdaten taucht er bewusst nicht auf — Gas oder Wasser
            sind Haushaltskosten und gehören nicht in die Rechnung der PV-Anlage.
            <br />
            <span className="mt-1 inline-block">
              Beim <strong>Zählerwechsel</strong> gilt: das alte Gerät stilllegen (Stilllegungsdatum
              setzen) und ein neues anlegen — dann bleibt die bisherige Ablesung erhalten.
            </span>
          </p>
        </>
      )}
    </FormSection>
  )
}
