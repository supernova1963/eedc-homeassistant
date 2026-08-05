import type { ChangeEvent } from 'react'

/**
 * Gemeinsame Props der typ-spezifischen Parameterfeld-Komponenten (Slice 5).
 * Werte/Setter kommen aus der `InvestitionForm`-Shell; Validierungs-Helfer nutzt
 * derzeit nur die Wärmepumpe (Pflicht-COP/SCOP/JAZ je Modus).
 */
export interface TypFelderProps {
  paramData: Record<string, string | boolean>
  /** Für `Input name="param_…"` (Event; Shell strippt das `param_`-Präfix). */
  onInputChange: (e: ChangeEvent<HTMLInputElement>) => void
  /** Für `Switch`/`Select`/`RadioGroup` (roher Parametername + Wert). */
  setParam: (name: string, value: string | boolean) => void
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
}
