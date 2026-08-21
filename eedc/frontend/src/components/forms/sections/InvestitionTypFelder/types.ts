import type { ChangeEvent } from 'react'
import type { Innengeraet } from '../../../../lib/investitionParameter'

/**
 * Ein Parameter-Wert im Formular. Fast alles ist Text oder Schalter; die
 * Innengeräte-Liste einer Split-Klimaanlage (#263) ist der eine **strukturierte**
 * Wert — sie wandert unverändert durch die Submit-Pipeline, statt durch die
 * Zahl/Text-Konvertierung zu laufen (`InvestitionForm`).
 */
export type ParamWert = string | boolean | Innengeraet[]

/**
 * Gemeinsame Props der typ-spezifischen Parameterfeld-Komponenten (Slice 5).
 * Werte/Setter kommen aus der `InvestitionForm`-Shell; Validierungs-Helfer nutzt
 * derzeit nur die Wärmepumpe (Pflicht-COP/SCOP/JAZ je Modus).
 */
export interface TypFelderProps {
  paramData: Record<string, ParamWert>
  /** Für `Input name="param_…"` (Event; Shell strippt das `param_`-Präfix). */
  onInputChange: (e: ChangeEvent<HTMLInputElement>) => void
  /** Für `Switch`/`Select`/`RadioGroup` (roher Parametername + Wert). */
  setParam: (name: string, value: ParamWert) => void
  /** Sichtbarer Fehler eines Pflichtfelds (nach touched/submitted), sonst undefined. */
  zeige: (name: string) => string | undefined
  markTouched: (name: string) => void
  setFeldRef: (name: string) => (el: HTMLDivElement | null) => void
  /**
   * Rohwert des Shell-Felds `leistung_kwp` — nur das PV-Modul nutzt ihn, für
   * die Querprüfung „Anzahl × Wp ↔ eingetragene kWp" (R22-1/R22-2, PN 89782).
   * Bewusst der Roh-String der Eingabe (nicht `leistung_kwp_effektiv`): die
   * Warnung soll das vergleichen, was gerade im Formular steht.
   */
  leistungKwp?: string
  /**
   * Ob im Formular gerade ein Wechselrichter zugeordnet ist — nur der Speicher
   * nutzt es (#351), um bei „Automatisch" zu zeigen, **was** daraus folgt.
   * Bewusst der Formular-Zustand und nicht der gespeicherte: die Anzeige soll
   * der Auswahl folgen, die der Anwender gerade trifft.
   */
  hatZuordnung?: boolean
  /**
   * Anzahl der PV-Module, die diesem Gerät zugeordnet sind — nur das
   * Balkonkraftwerk nutzt es (N-266). Sind es mehr als 0, hat das BKW seine
   * Nennleistung und seine Ausrichtung an die Module abgetreten: dann ist die
   * eigene `Anzahl × Wp`-Pflege nicht mehr die Quelle, und das Formular sagt
   * das, statt zwei Zahlen dasselbe behaupten zu lassen.
   *
   * `undefined` = noch nicht ermittelt (Anlegen-Fall, kein Fetch nötig).
   */
  modulKinder?: number
}
