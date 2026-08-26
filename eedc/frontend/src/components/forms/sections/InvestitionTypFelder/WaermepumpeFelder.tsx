import { X } from 'lucide-react'
import { FormSection, Input, Select, Alert, RadioGroup, Button } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import type { Innengeraet } from '../../../../lib/investitionParameter'
import { istLuftLuft } from '../../../../lib/investitionParameter'
import type { TypFelderProps } from './types'

/**
 * Innengeraete einer Split-Klimaanlage (#263).
 *
 * **Die Liste ist selbst der Schalter:** "Multisplit" wird aus ihrer Laenge
 * abgeleitet und nirgends gespeichert - Schalter und Liste koennen damit nicht
 * auseinanderlaufen. Wer nichts eintraegt, hat einen Monosplit, und alles bleibt
 * bitgleich zu vorher.
 *
 * Die ID wird vergeben und nie wiederverwendet. Sie steht im Feld-Key der
 * Sensor-Zuordnung; eine Positionsnummer wuerde beim Loeschen des mittleren
 * Geraets alle folgenden Zuordnungen auf den falschen Raum umhaengen.
 *
 * Controls = SoT (Style-Guide Teil D): `Input` fuer die Bezeichnung, `Button`
 * fuer Anlegen/Entfernen - dasselbe Zeilen-Muster wie
 * `forms/SonstigePositionenFields`, keine zweite Komponentenklasse.
 */
function InnengeraeteListe({
  geraete, onChange,
}: { geraete: Innengeraet[]; onChange: (next: Innengeraet[]) => void }) {
  const naechsteId = geraete.reduce((max, g) => Math.max(max, g.id), 0) + 1

  return (
    <div className="space-y-2">
      <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        Innengeraete
      </span>
      {geraete.map((g, index) => (
        <div key={g.id} className="flex items-center gap-2">
          <div className="flex-1">
            <Input
              label=""
              name={`innengeraet_${g.id}`}
              aria-label={`Bezeichnung Innengeraet ${index + 1}`}
              value={g.bezeichnung}
              placeholder="z. B. Wohnzimmer"
              onChange={(e) => onChange(geraete.map(
                (x) => (x.id === g.id ? { ...x, bezeichnung: e.target.value } : x),
              ))}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onChange(geraete.filter((x) => x.id !== g.id))}
            title={`Innengeraet ${index + 1} entfernen`}
            aria-label={`Innengeraet ${index + 1} entfernen`}
            className="text-red-500 hover:text-red-600 dark:text-red-400"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => onChange([...geraete, { id: naechsteId, bezeichnung: '' }])}
      >
        + Innengeraet
      </Button>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Nur noetig, wenn mehrere Innengeraete an einem Aussengeraet haengen
        (Multisplit). Jedes bekommt eigene Felder unter{' '}
        <em>Einstellungen &rarr; Datenquellen</em> - Verbrauch je Betriebsart,
        Leistung und Raumtemperatur. Alle sind optional: kein Sensor, keine
        Anzeige. Ohne Eintrag bleibt alles wie bisher.
      </p>
    </div>
  )
}

const WP_ART_OPTIONEN = [
  { value: 'luft_wasser', label: 'Luft-Wasser (Außenluft → Wasser)' },
  { value: 'sole_wasser', label: 'Sole-Wasser (Erdwärme → Wasser)' },
  { value: 'grundwasser', label: 'Grundwasser-Wärmepumpe' },
  { value: 'luft_luft', label: 'Luft-Luft (Klimaanlage)' },
  // SOLL Wärme/Klima §2.1/A6 — ein Gerät, das nur Warmwasser macht. Es steht
  // hier, obwohl es dafür KEINEN bekannten Anwender gibt (Entscheid Gernot,
  // 26.08.2026): Ein Modell, das einen realen Gerätetyp nicht ausdrücken kann,
  // ist später nicht nachrüstbar — die bis dahin gespeicherten Daten wären dann
  // falsch, nicht bloß unvollständig.
  { value: 'brauchwasser', label: 'Brauchwasser-Wärmepumpe (nur Warmwasser)' },
]

// R2 (SOLL §3.2b) — **eine** Regel, zwei Vorzeichen. Die Texte beschreiben die
// Lage und bewerten den Anwender nicht: Wer seinen Heizstab am WP-Zähler hat,
// macht nichts falsch — eedc kann daraus nur keine Arbeitszahl bilden.
const ABGRENZUNG_OPTIONEN = [
  {
    value: '',
    label: 'Kein Fremdanteil',
    description: 'Der Stromzähler und der Wärmemengenzähler gehören beide allein zu diesem Gerät.',
  },
  {
    value: 'fremdstrom',
    label: 'Heizstab-Strom liegt mit auf dem Stromzähler',
    description: 'Seine Wärme läuft NICHT über den Wärmemengenzähler. Der Stromwert enthält dann '
      + 'mehr, als die gemessene Wärme abdeckt — die Mengen bleiben richtig, die Arbeitszahl entfällt.',
  },
  {
    value: 'fremdwaerme',
    label: 'Ein zweiter Erzeuger speist denselben Heizkreis',
    description: 'Gas- oder Ölkessel im bivalenten Betrieb: Der Wärmemengenzähler misst beide, '
      + 'der Stromzähler kennt nur die Wärmepumpe. Umgekehrter Fall, gleiche Folge.',
  },
] as const

// SOLL §4.1/§7 A5 — passive Kühlung läuft nur über Umwälzpumpen. Ihre Kennzahl
// ist KORREKT, nur um ein Vielfaches höher; gesperrt wird deshalb nie die Zahl,
// sondern immer nur ihr Vergleich (Community-Benchmark).
const KUEHLUNG_OPTIONEN = [
  { value: 'keine', label: 'Kühlt nicht' },
  { value: 'aktiv', label: 'Aktiv (Kompressor / Umkehrbetrieb)' },
  { value: 'passiv', label: 'Passiv (nur Umwälzpumpen, „natural cooling")' },
]

const VORLAUF_OPTIONEN = [
  { value: '35', label: '35 °C (Fußbodenheizung)' },
  { value: '55', label: '55 °C (Heizkörper)' },
]

const ENERGIETRAEGER_OPTIONEN = [
  { value: 'gas', label: 'Erdgas' },
  { value: 'oel', label: 'Heizöl' },
  { value: 'strom', label: 'Strom (Direktheizung)' },
  { value: 'nichts', label: 'Nichts ersetzt (Neubau)' },
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
            /* N-280: Der Hinweis nannte bis 2026-08-18 NUR die Nebenwirkung
               („Community-Vergleich") und verschwieg die Hauptwirkung — die
               Wärmepumpenart steuert, welche Messwerte eedc von diesem Gerät
               überhaupt erwartet. Zwei gemeldete Klimaanlagen laufen deshalb
               als „Luft-Wasser" (azywietz-web, #383): die Beschriftung ließ
               das Feld wie eine Statistik-Einstellung aussehen. */
            hint="Legt fest, welche Messwerte eedc von diesem Gerät erwartet — eine Klimaanlage wird nicht nach Heizwärme gefragt. Zusätzlich für den fairen JAZ-Vergleich in der Community."
          />
          {istLuftLuft(paramData) && (
            <Alert type="info" title="Split-Klimaanlage">
              Es genügt der Stromverbrauchs-Sensor. Heizenergie und Warmwasser sind bei Klimas meist
              nicht gemessen — die JAZ-Kachel bleibt dann leer („—"), die Stromauswertung funktioniert
              trotzdem. <strong>Heizt du mit dem Gerät</strong>, trag unten den Heizwärmebedarf ein;
              dann rechnet eedc die Wirtschaftlichkeit gegenüber der ersetzten Heizung wie bei jeder
              anderen Wärmepumpe. <strong>Kühlst du nur</strong>, wähle beim alten Energieträger
              „Nichts ersetzt (Neubau)" — dann wird nichts verglichen.
              <br /><br />
              <strong>Neu: eedc kann den Betriebsmodus mitschreiben.</strong> Ordne unter
              Einstellungen → Datenquellen das Feld „Betriebsmodus" zu (die climate-Entität
              deines Geräts), dann hält eedc ab sofort stündlich fest, ob geheizt oder gekühlt
              wurde. <strong>Das lässt sich nicht nachtragen</strong> — Home Assistant bewahrt
              solche Zustände nur wenige Tage auf. Wer die Aufteilung später sehen will, ordnet
              den Sensor also besser jetzt zu als dann. Die Auswertung dazu (Heiz-/Kühlstrom
              getrennt, Kühl-Effizienz SEER) ist noch in Arbeit (Thema #263).
            </Alert>
          )}

          {/* R2 (SOLL Wärme/Klima §3.2b) — die beiden Angaben, die eedc NICHT
              sehen kann. Ob ein Heizstab auf dem WP-Zähler liegt oder ein
              Gaskessel denselben Kreis speist, steht in keinen Daten; die
              Verletzung „mehrere Geräte, nur eines meldet Wärme" erkennt eedc
              dagegen selbst (`WpFakten.waerme_deckt_nicht_alle_geraete`).

              ⚠ Beide Angaben ändern KEINE Menge — sie nehmen nur die
              Arbeitszahl weg, weil Zähler und Nutzen dann für verschiedene
              Dinge stehen. Das steht so auch im Hinweis unter dem Feld: eedc
              ist nicht die Strom-Polizei. */}
          <Select
            label="Fremdanteil auf den Zählern"
            name="param_abgrenzung"
            value={(paramData.abgrenzung as string) ?? ''}
            onChange={(e) => setParam('abgrenzung', e.target.value)}
            options={ABGRENZUNG_OPTIONEN.map((o) => ({ value: o.value, label: o.label }))}
            hint={
              ABGRENZUNG_OPTIONEN.find(
                (o) => o.value === ((paramData.abgrenzung as string) ?? ''),
              )?.description
            }
          />

          <Select
            label="Kühlung"
            name="param_kuehlung_art"
            value={(paramData.kuehlung_art as string) ?? 'keine'}
            onChange={(e) => setParam('kuehlung_art', e.target.value)}
            options={KUEHLUNG_OPTIONEN}
            hint="Passiv gekühlte Anlagen erreichen ein Vielfaches der Effizienz aktiv gekühlter — eedc vergleicht sie deshalb nicht miteinander. Die eigenen Zahlen bleiben davon unberührt."
          />

          {istLuftLuft(paramData) && (
            <InnengeraeteListe
              geraete={(paramData.innengeraete as Innengeraet[]) ?? []}
              onChange={(next) => setParam('innengeraete', next)}
            />
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

            {/* N-88/F2b (2026-08-16): Der Guard `wp_art !== 'luft_luft'` ist hier
                WEG. Er beruhte auf der Annahme, eine Split-Klimaanlage ersetze nie
                eine Heizung — und die ist falsch (Gernot): Eine Luft-Luft-WP kann
                sehr wohl eine Gasheizung ersetzen. Wer damit heizt, muss den
                Bedarf eintragen können, sonst bleibt seine Zeile für immer
                unbewertet.

                Was bleibt: die Felder werden für `luft_luft` NICHT vorbelegt
                (`investitionFormHelpers.ts::getInitialParamData`) — genau das war
                der N-87-Defekt, nicht das Feld selbst. Wer nur kühlt, lässt sie
                leer und wählt oben „Nichts ersetzt (Neubau)".

                Nebenwirkung, bewusst: Damit ist auch N-91 entschärft — die aus
                einem Typwechsel im offenen Formular übernommene Vorbelegung ist
                jetzt SICHTBAR und damit korrigierbar, statt unbemerkt
                mitgespeichert zu werden. */}
            <Input
              label="Heizwärmebedarf (kWh/Jahr)"
              name="param_heizwaermebedarf_kwh"
              type="number" step="any" min="0"
              value={paramData.heizwaermebedarf_kwh as string}
              onChange={onInputChange}
              hint={istLuftLuft(paramData)
                ? 'Nur wenn du mit dem Gerät heizt — sonst leer lassen'
                : 'Aus Energieausweis oder Schätzung'}
            />
            <Input
              label="Warmwasserbedarf (kWh/Jahr)"
              name="param_warmwasserbedarf_kwh"
              type="number" step="any" min="0"
              value={paramData.warmwasserbedarf_kwh as string}
              onChange={onInputChange}
              hint={istLuftLuft(paramData)
                ? 'Split-Geräte haben keinen Warmwasserkreis — meist leer'
                : '~500 kWh/Person/Jahr typisch'}
            />
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
