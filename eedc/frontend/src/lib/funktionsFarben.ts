/**
 * funktionsFarben — eine Datenrolle, eine Farbe: die Farbe einer **Funktion** des Wärme/Klima-Bereichs
 * (Kanon-Wert des Betriebsmodus `heizen` · `warmwasser` · `kuehlen` · `lueften` · `entfeuchten` und die
 * zwei Reste `system` · `ohne_modus`). SoT seit P-433-2 S2 — vorher in `v4/waermeVerteilung.ts`, von wo
 * der Modus-Chip (`components/ui/ModusChip.tsx`) sie über einen Import `ui → v4` holen musste.
 *
 * Leser: `v4/waermeVerteilung.ts` (Segmente, Stapel, Verlauf) und `components/ui/ModusChip.tsx`.
 *
 * ⚠ **Die Rolle ist die Funktion, nicht das Gerät** — bewusst, mit einem Preis: tragen zwei Geräte
 * dieselbe Funktion bei, haben ihre Segmente denselben Ton (Begründung bei `waermeVerteilung.ts`).
 */
import { CHART_COLORS, ROLLEN_BG } from './colors'

export interface FunktionsFarbe {
  /** Chart-Farbe (Linie, Segment, Farbpunkt des Chips). */
  chart: string
  /** Rollen-Hintergrund (Balken der Verteilung). */
  bg: string
}

const FARBE: Record<string, FunktionsFarbe> = {
  heizen: { chart: CHART_COLORS.wpWaerme, bg: ROLLEN_BG.heizung },
  warmwasser: { chart: CHART_COLORS.wpWarmwasser, bg: ROLLEN_BG.warmwasser },
  kuehlen: { chart: CHART_COLORS.modusKuehlen, bg: ROLLEN_BG.kuehlung },
  lueften: { chart: CHART_COLORS.modusLueften, bg: ROLLEN_BG.lueftung },
  entfeuchten: { chart: CHART_COLORS.modusEntfeuchten, bg: ROLLEN_BG.entfeuchtung },
  // Die **zwei** Reste — getrennt benannt und getrennt gefärbt (Konzept Kap. 3).
  system: { chart: CHART_COLORS.systemRest, bg: ROLLEN_BG.system_rest },
  ohne_modus: { chart: CHART_COLORS.modusNichtAufgeteilt, bg: ROLLEN_BG.nicht_aufgeteilt },
}

const FALLBACK: FunktionsFarbe = { chart: CHART_COLORS.modusNichtAufgeteilt, bg: ROLLEN_BG.nicht_aufgeteilt }

/** Beide Farben einer Funktion; unbekannt (`aus`, `unbestimmt` …) ⇒ die Farbe von «nicht aufgeteilt». */
export function funktionsFarben(funktion: string): FunktionsFarbe {
  return FARBE[funktion] ?? FALLBACK
}

/** Chart-Farbe einer Funktion — der Farbpunkt im Modus-Chip und die Segmente der Wärme-Verteilung. */
export function funktionsFarbe(funktion: string): string {
  return funktionsFarben(funktion).chart
}
