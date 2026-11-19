/**
 * SensorwechselDialog — die Abfrage beim Wechsel der Quelle eines Zählers mit eigenen Werten (Sensorwechsel mit Grund,
 * Bauplan B-2, Konzept S-1/S-8; Sitzung 3b). **Die eine Komponente** für alle Wege der Fläche: Feld (HA-Picker, Gateway,
 * Inbound, Keine) und «Preset anwenden» (eine Zeile je Feld).
 *
 * Ablauf: der Aufrufer hat die Änderung schon geprüft (`…/quelle/pruefen` bzw. `…/presets/apply/pruefen`) und öffnet den
 * Dialog nur, wenn eine Zeile `grund_erforderlich` trägt. Je Feld zwei Gründe mit je einem Satz, was danach geschieht; bei
 * «Korrektur» das Feld «falsch seit» (vorbelegt: Beginn der bisherigen Quelle) und die Vorschau des Korrektur-Dienstes
 * (`onVorschau` — dieselbe Prüf-Route mit Grund, Vorschau = Lauf), **bevor** etwas geändert wird. «Abbrechen» lässt die
 * bisherige Zuordnung stehen. Der Client rechnet nichts: Zahlen und Sätze kommen aus dem Backend.
 *
 * **Grund nachtragen** (Sitzung 4, Bauplan B-7): derselbe Dialog für einen schon verzeichneten Wechsel ohne Grund (`nachtrag`):
 * Titel in der Vergangenheit, der Wechsel als Satz oben, nur die zulässigen Gründe (`…/grund/pruefen`: Fortsetzung → Korrektur
 * ja, Korrektur nie mehr; Korrektur nur am jüngsten Wechsel, sonst ein Satz warum), «Falsch seit» vorbelegt mit dem Beginn der
 * Quelle vor dem Wechsel.
 *
 * **Stück** (Sitzung 4b-1, Bauplan «Zu §14» Nr. 96/98/101): am Befund «Zählerstände – versetzter Abschnitt» gibt es nur
 * «Korrektur» über ein festes Stück, am Rückkehr-Wechsel X → A eines Stücks A → X → A «Korrektur» über die Zeit davor — statt
 * des Felds «Falsch seit» steht die Zeit des Stücks.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Input, Modal, RadioGroup } from '../ui'
import type { GrundAngabe, KorrekturVorschau, QuellePruefung, WechselGrund } from '../../api/datenquellen'
import { formatDatum } from '../../lib/datum'
import { fmtZahl } from '../../lib/einheiten'

export const DIALOG_TITEL = 'Warum wechselt die Quelle?'
export const GRUND_FORTSETZUNG = 'Der neue Sensor misst dasselbe weiter (Zähler getauscht, anderer Sensor für dasselbe Gerät)'
export const GRUND_FORTSETZUNG_FOLGE =
  'Die bisherigen Werte bleiben, und der Unterschied zwischen altem und neuem Zählerstand zählt nicht als Menge. Wo eedc ' +
  'aus den gespeicherten Zählerständen rechnet, zählt die Stunde des Wechsels keinen Zuwachs.'
export const GRUND_KORREKTUR = 'Bisher war der falsche Sensor zugeordnet'
export const GRUND_KORREKTUR_FOLGE =
  'Die Werte dieses Felds seit «falsch seit» werden verworfen und — soweit Home Assistant die Geschichte des richtigen ' +
  'Sensors führt — aus ihm neu aufgebaut. Die Vorschau unten sagt, was genau geschieht.'
/** Im Nachtrag liegt der Wechsel in der Vergangenheit: ein fest gespeicherter Tageswert vom Tag des Wechsels bleibt (benannte
 * Grenze, Bauplan «Zu §13» Nr. 87) — neben dem freigegebenen Satz `GRUND_FORTSETZUNG_FOLGE`, der wörtlich bleibt. */
export const NACHTRAG_FORTSETZUNG_ZUSATZ =
  'Hat eedc für den Tag des Wechsels schon einen festen Tageswert gespeichert, bleibt der, wie er ist, und kann den ' +
  'Unterschied weiter enthalten.'
/** Im Nachtrag endet das verworfene Intervall am Wechsel (Bauplan §13 Nr. 69). */
export const NACHTRAG_GRUND_KORREKTUR_FOLGE =
  'Die Werte dieses Felds von «falsch seit» bis zum Wechsel werden verworfen und — soweit Home Assistant die Geschichte ' +
  'des richtigen Sensors führt — aus ihm neu aufgebaut. Die Vorschau unten sagt, was genau geschieht.'
export const FALSCH_SEIT_LABEL = 'Falsch seit'
export const FALSCH_SEIT_HINWEIS = 'Vorbelegt ist der Beginn der bisherigen Quelle; gezählt wird ab der vollen Stunde.'
export const ABBRECHEN_HINWEIS = '«Abbrechen» lässt die bisherige Zuordnung unverändert.'
export const VORSCHAU_TITEL = 'Was danach geschieht'
export const VORSCHAU_LAEDT = 'Vorschau wird geladen …'
export const NACHTRAG_TITEL = 'Warum wechselte die Quelle?'
export const NACHTRAG_FALSCH_SEIT_HINWEIS = 'Vorbelegt ist der Beginn der Quelle vor dem Wechsel; gezählt wird ab der vollen Stunde.'
export const NACHTRAG_ABBRECHEN_HINWEIS = '«Abbrechen» trägt nichts ein.'
export const NACHTRAG_NICHTS = 'Für diesen Wechsel ist kein Grund nachzutragen.'
/** Sitzung 4b-1: Korrektur über ein festes Stück (Befund «Zählerstände – versetzter Abschnitt»; am Rückkehr-Wechsel X → A
 *  eines Stücks A → X → A die Zeit davor) — «Falsch seit» steht fest, die Korrektur endet am Rückgang. */
export const STUECK_GRUND_KORREKTUR_FOLGE =
  'Die Zählerstände dieses Felds aus dieser Zeit werden verworfen und — wo Home Assistant sie für die Quelle davor und ' +
  'danach führt — neu gelesen; sonst bleibt die Zeit ohne Zählerstände. Die Vorschau unten sagt, was das für die ' +
  'Tageswerte heißt.'
export const STUECK_ZEIT = (von: string, bis: string) => `Die Korrektur gilt für die Zeit vom ${von} bis ${bis} Uhr.`

/** «Grund nachtragen»: der Wechsel als Satz, die zulässigen Gründe und — wo «Korrektur» fehlt — warum (alles vom Backend). */
export interface NachtragAngaben {
  wechselSatz: string
  gruende: WechselGrund[]
  korrekturNicht?: string | null
  /** Korrektur über ein festes Stück (ISO-Zeiten vom Backend): kein Feld «Falsch seit». */
  stueck?: { sprung: string; rueckgang: string } | null
}

/** `YYYY-MM-DDTHH:MM[:SS]` → «TT.MM.JJJJ HH:MM» (nur Anzeige). */
const zeitText = (iso: string): string => `${formatDatum(iso.slice(0, 10))} ${iso.slice(11, 16)}`

/** «hat eigene Werte seit … (n Tage)» und die Stände — nur Anzeige der Backend-Zahlen. */
export function werteSatz(f: QuellePruefung): string {
  const teile: string[] = []
  if (f.erster_wert) teile.push(`Eigene Werte seit ${formatDatum(f.erster_wert)} (${fmtZahl(f.tage)} Tage).`)
  if (f.stand_alt != null) teile.push(`Letzter Stand der bisherigen Quelle: ${fmtZahl(f.stand_alt, 1)}.`)
  if (f.stand_neu != null) teile.push(`Stand der neuen Quelle jetzt: ${fmtZahl(f.stand_neu, 1)}.`)
  return teile.join(' ')
}

/** `YYYY-MM-DDTHH:MM:SS` → Wert eines `datetime-local`-Felds. */
const lokal = (iso: string | null): string => (iso ? iso.slice(0, 16) : '')

interface Wahl {
  grund: WechselGrund | ''
  falschSeit: string
  vorschau: KorrekturVorschau | null
  laedt: boolean
  fehler: string | null
}

interface Props {
  isOpen: boolean
  /** Die Zeilen der Prüf-Route mit `grund_erforderlich` (Feld: eine, Preset: je Feld eine). */
  fragen: QuellePruefung[]
  /** Vorschau der Korrektur für einen Schlüssel (Prüf-Route mit Grund «korrektur» und «falsch seit»). */
  onVorschau: (sensorKey: string, falschSeit: string) => Promise<KorrekturVorschau | null>
  onBestaetigen: (gruende: Record<string, GrundAngabe>) => void
  onAbbrechen: () => void
  laeuft?: boolean
  fehler?: string | null
  /** Grund nachtragen an einem verzeichneten Wechsel (eine Zeile); ohne: die Abfrage beim Wechsel. */
  nachtrag?: NachtragAngaben
}

export default function SensorwechselDialog({
  isOpen, fragen, onVorschau, onBestaetigen, onAbbrechen, laeuft, fehler, nachtrag,
}: Props) {
  const [wahl, setWahl] = useState<Record<string, Wahl>>({})

  useEffect(() => {
    setWahl(Object.fromEntries(fragen.map((f) => [f.sensor_key ?? '', {
      grund: '' as const, falschSeit: lokal(f.vorgabe_falsch_seit), vorschau: null, laedt: false, fehler: null,
    }])))
  }, [fragen])

  const setze = (key: string, patch: Partial<Wahl>) =>
    setWahl((w) => ({ ...w, [key]: { ...w[key], ...patch } }))

  // Je Feld die Nummer der jüngsten Anfrage: eine überholte Antwort (früheres «falsch seit») wird verworfen.
  const anfrage = useRef<Record<string, number>>({})

  // Vorschau der Korrektur laden, sobald «Korrektur» gewählt ist und «falsch seit» steht.
  const ladeVorschau = (key: string, falschSeit: string) => {
    const nr = (anfrage.current[key] ?? 0) + 1
    anfrage.current[key] = nr
    if (!falschSeit) { setze(key, { vorschau: null, laedt: false }); return }
    setze(key, { laedt: true, fehler: null })
    const aktuell = () => anfrage.current[key] === nr
    onVorschau(key, falschSeit)
      .then((v) => { if (aktuell()) setze(key, { vorschau: v, laedt: false }) })
      .catch((e) => {
        if (aktuell()) setze(key, { vorschau: null, laedt: false, fehler: e instanceof Error ? e.message : 'Vorschau fehlgeschlagen' })
      })
  }

  const bereit = useMemo(() => fragen.length > 0 && fragen.every((f) => {
    const w = wahl[f.sensor_key ?? '']
    if (!w || !w.grund) return false
    return w.grund === 'fortsetzung' || (!!w.falschSeit && !w.laedt && !!w.vorschau?.startbar)
  }), [fragen, wahl])

  const bestaetigen = () => {
    const gruende: Record<string, GrundAngabe> = {}
    for (const f of fragen) {
      const key = f.sensor_key ?? ''
      const w = wahl[key]
      gruende[key] = w.grund === 'korrektur' ? { grund: 'korrektur', falsch_seit: w.falschSeit } : { grund: 'fortsetzung' }
    }
    onBestaetigen(gruende)
  }

  const optionen = [
    { value: 'fortsetzung' as const, label: GRUND_FORTSETZUNG,
      description: nachtrag ? `${GRUND_FORTSETZUNG_FOLGE} ${NACHTRAG_FORTSETZUNG_ZUSATZ}` : GRUND_FORTSETZUNG_FOLGE },
    { value: 'korrektur' as const, label: GRUND_KORREKTUR,
      description: nachtrag?.stueck ? STUECK_GRUND_KORREKTUR_FOLGE : nachtrag ? NACHTRAG_GRUND_KORREKTUR_FOLGE : GRUND_KORREKTUR_FOLGE },
  ].filter((o) => !nachtrag || nachtrag.gruende.includes(o.value))
  const nichts = !!nachtrag && nachtrag.gruende.length === 0

  return (
    <Modal isOpen={isOpen} onClose={onAbbrechen} title={nachtrag ? NACHTRAG_TITEL : DIALOG_TITEL} size="lg">
      <div className="space-y-5" data-sensorwechsel-dialog>
        {nachtrag && (
          <p className="text-sm text-gray-700 dark:text-gray-200" data-nachtrag-wechsel>{nachtrag.wechselSatz}</p>
        )}
        {nichts && <Alert type="info">{nachtrag?.stueck && nachtrag.korrekturNicht ? nachtrag.korrekturNicht : NACHTRAG_NICHTS}</Alert>}
        {fragen.map((f) => {
          const key = f.sensor_key ?? ''
          const w = wahl[key]
          if (!w || nichts) return null
          return (
            <div key={key} className="space-y-3" data-sensorwechsel-feld={key}>
              <p className="text-sm text-gray-700 dark:text-gray-200">
                <span className="font-medium">{f.label ?? key}</span>
                {werteSatz(f) && <span className="block text-xs text-gray-500 dark:text-gray-400">{werteSatz(f)}</span>}
              </p>
              <RadioGroup<WechselGrund>
                name={`grund-${key}`}
                value={w.grund}
                onChange={(g) => {
                  setze(key, { grund: g })
                  if (g === 'korrektur') ladeVorschau(key, w.falschSeit)
                }}
                options={optionen}
              />
              {nachtrag?.korrekturNicht && (
                <p className="text-xs text-gray-500 dark:text-gray-400" data-korrektur-nicht>{nachtrag.korrekturNicht}</p>
              )}
              {w.grund === 'korrektur' && (
                <div className="space-y-2 pl-6">
                  {nachtrag?.stueck ? (
                    <p className="text-sm text-gray-700 dark:text-gray-200" data-stueck-zeit={key}>
                      {STUECK_ZEIT(zeitText(nachtrag.stueck.sprung), zeitText(nachtrag.stueck.rueckgang))}
                    </p>
                  ) : <Input
                    type="datetime-local"
                    label={FALSCH_SEIT_LABEL}
                    hint={nachtrag ? NACHTRAG_FALSCH_SEIT_HINWEIS : FALSCH_SEIT_HINWEIS}
                    value={w.falschSeit}
                    onChange={(e) => { setze(key, { falschSeit: e.target.value }); ladeVorschau(key, e.target.value) }}
                    data-falsch-seit={key}
                  />}
                  <div className="text-xs" data-korrektur-vorschau={key}>
                    <p className="font-medium text-gray-700 dark:text-gray-200">{VORSCHAU_TITEL}</p>
                    {w.laedt && <p className="text-gray-500 dark:text-gray-400">{VORSCHAU_LAEDT}</p>}
                    {w.fehler && <Alert type="error">{w.fehler}</Alert>}
                    {!w.laedt && w.vorschau && (
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-gray-600 dark:text-gray-300">
                        {w.vorschau.saetze.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
        {!nichts && (
          <p className="text-xs text-gray-500 dark:text-gray-400">{nachtrag ? NACHTRAG_ABBRECHEN_HINWEIS : ABBRECHEN_HINWEIS}</p>
        )}
        {fehler && <Alert type="error">{fehler}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onAbbrechen}>Abbrechen</Button>
          {!nichts && (
            <Button type="button" onClick={bestaetigen} disabled={!bereit || laeuft} loading={laeuft} data-sensorwechsel-ok>
              Übernehmen
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
