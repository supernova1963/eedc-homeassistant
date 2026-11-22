/**
 * SensorwechselDialog — die Abfrage beim Wechsel der Quelle eines Zählers mit eigenen Werten (Sensorwechsel mit Grund,
 * Bauplan B-2, Konzept S-1/S-8; Sitzung 3b). **Die eine Komponente** für alle Wege der Fläche: Feld (HA-Picker, Gateway,
 * Inbound, Keine) und «Preset anwenden» (eine Zeile je Feld).
 *
 * Ablauf: der Aufrufer hat die Änderung schon geprüft (`…/quelle/pruefen` bzw. `…/presets/apply/pruefen`) und öffnet den
 * Dialog nur, wenn eine Zeile `grund_erforderlich` trägt. **Beim Wechsel genau zwei Antworten** (Weg B, Entscheid Gernot
 * 21.11.2026): «Bisherige Werte bleiben» und «Daten vor der Änderung löschen» — was «löschen» tut, sagen die Sätze der
 * Prüf-Antwort (`loeschen`: nur dieses Feld, danach wie von Anfang an zugeordnet, gespeicherte Monate und der Weg zur
 * Handkorrektur, nicht rücknehmbar). «Abbrechen» lässt die bisherige Zuordnung stehen. Der Client rechnet nichts: Zahlen und
 * Sätze kommen aus dem Backend.
 *
 * «Grund nachtragen» an einem verzeichneten Wechsel samt Feld «Falsch seit» (Sitzung B2) und der Nachtrag-Modus am versetzten
 * Abschnitt («Stück», Sitzung B3a) sind seit Weg B entfernt.
 *
 * **«bleiben»** (Sensorwechsel U2 Lauf b, Bauplan Nr. 132/138; intern `fortsetzung`). Zwischen zwei HA-Sensoren trägt die
 * Prüf-Antwort `bleiben` (`BleibenAngaben`): bei «bleiben» zeigt der Dialog unter «Was danach geschieht» ihre Sätze; nur bei
 * Überlappung erscheint das Feld «Der neue Sensor zählt ab» (vorbelegt und begrenzt mit den Stunden aus der Antwort) — eine
 * andere Stunde holt die Vorschau neu (`onBleibenVorschau`, dieselbe Prüf-Route, Vorschau = Lauf). Ohne `bleiben` (jede andere
 * Quelle) bleibt der bisherige Satz zu «bleiben».
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Input, Modal, RadioGroup } from '../ui'
import type { BleibenAngaben, GrundAngabe, QuellePruefung, WechselGrund } from '../../api/datenquellen'
import { formatDatum } from '../../lib/datum'
import { fmtZahl } from '../../lib/einheiten'
import { plural } from '../../lib/plural'

export const DIALOG_TITEL = 'Warum wechselt die Quelle?'
export const GRUND_FORTSETZUNG =
  'Bisherige Werte bleiben — der neue Sensor setzt fort (Zähler oder Gerät getauscht, anderer Sensor für dasselbe Gerät)'
/** Zwischen zwei HA-Sensoren (U2 Lauf b): eedc rechnet wie Home Assistant mit beiden Sensoren. */
export const GRUND_BLEIBEN_HA_FOLGE =
  'Die bisherigen Werte bleiben. eedc rechnet wie Home Assistant mit beiden Sensoren: den bisherigen bis zu seinem letzten ' +
  'Wert, den neuen ab seinem ersten. Die Vorschau unten sagt, was genau geschieht.'
/** Jede andere Quelle (MQTT, Gateway): «bleiben» wie bisher. */
export const GRUND_FORTSETZUNG_FOLGE =
  'Die bisherigen Werte bleiben, und der Unterschied zwischen altem und neuem Zählerstand zählt nicht als Menge. Wo eedc ' +
  'aus den gespeicherten Zählerständen rechnet, zählt die Stunde des Wechsels keinen Zuwachs.'
/** Weg B: die zweite Antwort beim Wechsel. Was sie tut, sagen die Sätze der Prüf-Antwort (`loeschen.saetze`). */
export const GRUND_LOESCHEN = 'Daten vor der Änderung löschen — das Feld beginnt mit dem neuen Sensor neu'
export const GRUND_LOESCHEN_FOLGE =
  'Nur die Daten dieses Felds vor der Änderung werden gelöscht. Was das heißt, steht unten.'
export const ABBRECHEN_HINWEIS = '«Abbrechen» lässt die bisherige Zuordnung unverändert.'
export const VORSCHAU_TITEL = 'Was danach geschieht'
export const VORSCHAU_LAEDT = 'Vorschau wird geladen …'
/** U2 Lauf b: das Feld bei Überlappung (Backend `bleiben.FELD` — die Ablehnungen nennen es wörtlich). */
export const ZAEHLT_AB_LABEL = 'Der neue Sensor zählt ab'
export const ZAEHLT_AB_HINWEIS =
  'Beide Sensoren haben eine Zeit lang gleichzeitig gezählt. Vorbelegt ist die Stunde des Wechsels; eine frühere Stunde ' +
  'nimmst du, wenn der neue Sensor schon ab dann die Werte des Geräts gemessen hat.'
/** Lab-K F5: der zulässige Bereich (Backend: nach der ersten Stunde des neuen Sensors und nicht vor dem vorigen Wechsel des
 *  Felds, bis zur Stunde des Wechsels). */
export const ZAEHLT_AB_BEREICH = (von: string, bis: string) => `Wählbar von ${von} bis ${bis} Uhr.`

/** `YYYY-MM-DDTHH:MM[:SS]` → «TT.MM.JJJJ HH:MM» (nur Anzeige). */
const zeitText = (iso: string): string => `${formatDatum(iso.slice(0, 10))} ${iso.slice(11, 16)}`

/** «hat eigene Werte seit … (n Tage)» und die Stände — nur Anzeige der Backend-Zahlen. */
export function werteSatz(f: QuellePruefung): string {
  const teile: string[] = []
  // Lab-K W1/W2: der früheste eigene Wert (Kanal oder Reihe, Backend) und die Tage mit Ein- oder Mehrzahl.
  if (f.erster_wert) {
    teile.push(`Eigene Werte seit ${formatDatum(f.erster_wert)} (${fmtZahl(f.tage)} ${plural(f.tage, 'Tag', 'Tage')}).`)
  }
  if (f.stand_alt != null) teile.push(`Letzter Stand der bisherigen Quelle: ${fmtZahl(f.stand_alt, 1)}.`)
  if (f.stand_neu != null) teile.push(`Stand der neuen Quelle jetzt: ${fmtZahl(f.stand_neu, 1)}.`)
  return teile.join(' ')
}

/** `YYYY-MM-DDTHH:MM:SS` → Wert eines `datetime-local`-Felds. */
const lokal = (iso: string | null): string => (iso ? iso.slice(0, 16) : '')

interface Wahl {
  grund: WechselGrund | ''
  laedt: boolean
  fehler: string | null
  /** U2 Lauf b: «Der neue Sensor zählt ab» und die Angaben zu «bleiben» an dieser Stunde (anfangs die der Prüfung). */
  zaehltAb: string
  bleiben: BleibenAngaben | null
}

interface Props {
  isOpen: boolean
  /** Die Zeilen der Prüf-Route mit `grund_erforderlich` (Feld: eine, Preset: je Feld eine). */
  fragen: QuellePruefung[]
  /** U2 Lauf b: die Angaben zu «bleiben» an einer anderen Stunde «Der neue Sensor zählt ab» (Prüf-Route mit `zaehlt_ab`). */
  onBleibenVorschau?: (sensorKey: string, zaehltAb: string) => Promise<BleibenAngaben | null>
  onBestaetigen: (gruende: Record<string, GrundAngabe>) => void
  onAbbrechen: () => void
  laeuft?: boolean
  fehler?: string | null
}

export default function SensorwechselDialog({
  isOpen, fragen, onBleibenVorschau, onBestaetigen, onAbbrechen, laeuft, fehler,
}: Props) {
  const [wahl, setWahl] = useState<Record<string, Wahl>>({})

  useEffect(() => {
    setWahl(Object.fromEntries(fragen.map((f) => [f.sensor_key ?? '', {
      grund: '' as const, laedt: false, fehler: null,
      zaehltAb: lokal(f.bleiben?.zaehlt_ab_vorgabe ?? null), bleiben: f.bleiben ?? null,
    }])))
  }, [fragen])

  const setze = (key: string, patch: Partial<Wahl>) =>
    setWahl((w) => ({ ...w, [key]: { ...w[key], ...patch } }))

  // Je Feld die Nummer der jüngsten Anfrage: eine überholte Antwort wird verworfen.
  const anfrage = useRef<Record<string, number>>({})

  // «Der neue Sensor zählt ab» geändert: die Angaben zu «bleiben» an dieser Stunde neu (dieselbe Prüf-Route).
  const ladeBleiben = (key: string, zaehltAb: string) => {
    const nr = (anfrage.current[key] ?? 0) + 1
    anfrage.current[key] = nr
    if (!zaehltAb || !onBleibenVorschau) return
    setze(key, { laedt: true, fehler: null })
    const aktuell = () => anfrage.current[key] === nr
    onBleibenVorschau(key, zaehltAb)
      .then((b) => { if (aktuell()) setze(key, { bleiben: b, laedt: false }) })
      .catch((e) => {
        if (aktuell()) setze(key, { laedt: false, fehler: e instanceof Error ? e.message : 'Vorschau fehlgeschlagen' })
      })
  }

  const bereit = useMemo(() => fragen.length > 0 && fragen.every((f) => {
    const w = wahl[f.sensor_key ?? '']
    if (!w || !w.grund) return false
    if (w.grund === 'fortsetzung') return !w.laedt && !w.fehler
    return w.grund === 'loeschen'
  }), [fragen, wahl])

  const bestaetigen = () => {
    const gruende: Record<string, GrundAngabe> = {}
    for (const f of fragen) {
      const key = f.sensor_key ?? ''
      const w = wahl[key]
      const anders = !!w.zaehltAb && w.zaehltAb !== lokal(f.bleiben?.zaehlt_ab_vorgabe ?? null)
      gruende[key] = w.grund === 'loeschen' ? { grund: 'loeschen' }
        : { grund: 'fortsetzung', ...(anders ? { zaehlt_ab: w.zaehltAb } : {}) }
    }
    onBestaetigen(gruende)
  }

  // U3 b: bei MQTT bzw. zwischen Home Assistant und MQTT sagt die Prüf-Antwort, was «bleiben» tut (`bleiben_satz`).
  const allgemein = (f: QuellePruefung) => f.bleiben_satz ?? GRUND_FORTSETZUNG_FOLGE
  const bleibenFolge = (f: QuellePruefung) => f.bleiben ? GRUND_BLEIBEN_HA_FOLGE : allgemein(f)
  const optionen = (f: QuellePruefung) => [
    { value: 'fortsetzung' as const, label: GRUND_FORTSETZUNG, description: bleibenFolge(f) },
    { value: 'loeschen' as const, label: GRUND_LOESCHEN, description: GRUND_LOESCHEN_FOLGE },
  ]

  return (
    <Modal isOpen={isOpen} onClose={onAbbrechen} title={DIALOG_TITEL} size="lg">
      <div className="space-y-5" data-sensorwechsel-dialog>
        {fragen.map((f) => {
          const key = f.sensor_key ?? ''
          const w = wahl[key]
          if (!w) return null
          return (
            <div key={key} className="space-y-3" data-sensorwechsel-feld={key}>
              <p className="text-sm text-gray-700 dark:text-gray-200">
                <span className="font-medium">{f.label ?? key}</span>
                {werteSatz(f) && <span className="block text-xs text-gray-500 dark:text-gray-400">{werteSatz(f)}</span>}
              </p>
              <RadioGroup<WechselGrund>
                name={`grund-${key}`}
                value={w.grund}
                onChange={(g) => setze(key, { grund: g, fehler: null })}
                options={optionen(f)}
              />
              {w.grund === 'fortsetzung' && w.bleiben && (
                <BleibenTeil sensorKey={key} w={w} onZaehltAb={(v) => { setze(key, { zaehltAb: v }); ladeBleiben(key, v) }} />
              )}
              {w.grund === 'loeschen' && f.loeschen && (
                <div className="space-y-2 pl-6 text-xs" data-loeschen-vorschau={key}>
                  <p className="font-medium text-gray-700 dark:text-gray-200">{VORSCHAU_TITEL}</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-gray-600 dark:text-gray-300">
                    {f.loeschen.saetze.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )
        })}
        <p className="text-xs text-gray-500 dark:text-gray-400">{ABBRECHEN_HINWEIS}</p>
        {fehler && <Alert type="error">{fehler}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onAbbrechen}>Abbrechen</Button>
          <Button type="button" onClick={bestaetigen} disabled={!bereit || laeuft} loading={laeuft} data-sensorwechsel-ok>
            Übernehmen
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/** U2 Lauf b: «bleiben» zwischen zwei HA-Sensoren — bei Überlappung das Feld «Der neue Sensor zählt ab» (Grenzen aus der
 *  Antwort), darunter die Sätze der Vorschau. Nur Anzeige der Backend-Angaben. */
function BleibenTeil({ sensorKey, w, onZaehltAb }: { sensorKey: string; w: Wahl; onZaehltAb: (v: string) => void }) {
  const b = w.bleiben
  if (!b) return null
  return (
    <div className="space-y-2 pl-6">
      {b.ueberlappung && b.zaehlt_ab_frueheste && (
        <Input
          type="datetime-local"
          id={`zaehlt-ab-${sensorKey}`}
          label={ZAEHLT_AB_LABEL}
          hint={`${ZAEHLT_AB_HINWEIS} ${ZAEHLT_AB_BEREICH(zeitText(b.zaehlt_ab_frueheste),
            zeitText(b.zaehlt_ab_spaeteste ?? b.zaehlt_ab_frueheste))}`}
          value={w.zaehltAb}
          min={lokal(b.zaehlt_ab_frueheste)}
          max={lokal(b.zaehlt_ab_spaeteste)}
          step={3600}
          onChange={(e) => onZaehltAb(e.target.value)}
          data-zaehlt-ab={sensorKey}
        />
      )}
      <div className="text-xs" data-bleiben-vorschau={sensorKey}>
        <p className="font-medium text-gray-700 dark:text-gray-200">{VORSCHAU_TITEL}</p>
        {w.laedt && <p className="text-gray-500 dark:text-gray-400">{VORSCHAU_LAEDT}</p>}
        {w.fehler && <Alert type="error">{w.fehler}</Alert>}
        {!w.laedt && !w.fehler && (
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-gray-600 dark:text-gray-300">
            {b.saetze.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        )}
      </div>
    </div>
  )
}
