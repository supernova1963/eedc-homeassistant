/**
 * waermeVerteilung — Verteilung und Verlauf des Wärme/Klima-Stroms, als reine
 * Funktionen (WK-16c).
 *
 * Getrennt von der Zeichnung, damit sie ohne Rendering prüfbar sind: Recharts
 * zeichnet in jsdom nichts, eine Probe am gerenderten Chart wäre grün, ohne zu
 * messen (N-424). Dieselbe Bauform wie {@link ./waermeVerlauf} daneben.
 *
 * ⛔ **Hier wird nichts gerechnet.** Mengen, Anteile, Herkunft und Kosten kommen
 * fertig aus dem Backend (`services/waerme_verteilung.py`); diese Datei wählt
 * Farbe, Beschriftung und Reihenfolge. Ein Anteil, den der Client selbst bildet,
 * wäre die zweite Stelle — die Klasse, aus der W-3 und F-56 entstanden sind.
 */
import { CHART_COLORS } from '../lib'
import { funktionsFarben } from '../lib/funktionsFarben'
import type { VerteilungSegment, VerteilungVerlauf } from '../api/energie_profil'
import type { VerlaufStapel, VerlaufLinie, WaermeVerlaufRow } from './WaermeVerlaufChart'

/** Die kanonische Reihenfolge der Funktionen — dieselbe wie im Layer
 *  (`core/berechnungen/waerme_verteilung.py::FUNKTIONEN`) und dieselbe wie im
 *  Betriebsart-Balken darüber, damit man die Bilder nebeneinander lesen kann. */
export const FUNKTIONS_ORDER = [
  'heizen', 'warmwasser', 'kuehlen', 'lueften', 'entfeuchten', 'system', 'ohne_modus',
] as const

/*
 * Eine Datenrolle, eine Farbe (Regel 0a) — und die Rolle ist die **Funktion**,
 * nicht das Gerät. Die Tabelle steht seit P-433-2 S2 in `lib/funktionsFarben.ts`
 * (SoT; der Modus-Chip liest dieselbe).
 *
 * ⚠ **Das ist eine bewusste Wahl mit einem Preis:** Tragen zwei Geräte dieselbe
 * Funktion bei („Wärmepumpe Heizen" und „Klimaanlage Heizen"), haben ihre
 * Segmente denselben Ton. Deshalb stehen sie im Stapel **nebeneinander** (die
 * Reihenfolge ist Funktion vor Gerät): Der farbige Block liest sich als
 * *Heizen*, und wer wissen will, welches Gerät wie viel beisteuert, findet es
 * im Balken darüber, in der Legende und im Tooltip — jede Zeile mit ihrem
 * Gerätenamen. Zwei Rot-Töne für dasselbe Heizen wären die Alternative gewesen;
 * sie hätte die Farbe zur Geräte-Identität gemacht und die Rolle verloren.
 */

/** Trägt die Antwort mehr als ein Gerät? Nur dann gehört der Gerätename ins
 *  Label — bei einer einzigen Wärmepumpe wäre er in jeder Zeile dasselbe Wort. */
export function mehrereGeraete(v: VerteilungVerlauf): boolean {
  return new Set(v.segmente.map((s) => s.investition_id)).size > 1
}

/** Die Beschriftung eines Segments. */
export function segmentLabel(s: VerteilungSegment, mitGeraet: boolean): string {
  return mitGeraet ? `${s.geraet} · ${s.funktion_label}` : s.funktion_label
}

/** Reihenfolge im Stapel und im Balken: **Funktion vor Gerät** (s. `lib/funktionsFarben.ts`). */
function sortiert(segmente: VerteilungSegment[]): VerteilungSegment[] {
  const rang = (f: string) => {
    const i = (FUNKTIONS_ORDER as readonly string[]).indexOf(f)
    return i < 0 ? FUNKTIONS_ORDER.length : i
  }
  return [...segmente].sort(
    (a, b) => rang(a.funktion) - rang(b.funktion) || a.investition_id - b.investition_id,
  )
}

/** Wie die Menge dieses Segments zustande kam — ein Wort, kein Satz. */
export function herkunftText(herkunft: string): string {
  if (herkunft === 'gemessen') return 'gemessen'
  if (herkunft === 'abgeleitet') return 'abgeleitet'
  // „Rest" ist weder gemessen noch abgeleitet — er ist die Differenz. Ihm eine
  // der beiden Marken zu geben wäre eine Behauptung über seine Herkunft.
  return 'Differenz'
}

export interface BalkenSegment { label: string; wert: number; farbe: string }

/** Die Zeilen des Aufteilungs-Balkens (SoT `VerteilungsBalken`).
 *
 *  ⭐ **Kein Donut, und das ist der Bestand:** Der Aufteilungs-Donut ist am
 *  19.06.2026 (B7-Revision) durch genau diese Komponente ersetzt worden — eine
 *  Bildsprache für alle Aufteilungen, mit den Werten **in** der Zeile statt in
 *  einer Legende. dietmar1968s Donut zeigt dieselbe Information. */
export function balkenSegmente(v: VerteilungVerlauf): BalkenSegment[] {
  const mitGeraet = mehrereGeraete(v)
  return sortiert(v.segmente.filter((s) => s.kwh > 0)).map((s) => ({
    label: segmentLabel(s, mitGeraet),
    wert: s.kwh,
    farbe: funktionsFarben(s.funktion).bg,
  }))
}

export interface KostenZeile {
  schluessel: string
  label: string
  herkunft: string
  preisCent: number | null
  kostenEuro: number | null
}

/** Die Kostentabelle — *Funktion · Herkunft · Preis · Kosten*.
 *
 *  ⚠ **Die kWh stehen bewusst NICHT noch einmal hier**, sondern im Balken
 *  darüber: `kWh × ct/kWh = €` ist eine triviale Rechnung mit **sichtbaren**
 *  Summanden, und genau die nimmt A6 von der Herleitungspflicht aus. Eine
 *  zweite kWh-Spalte wäre dieselbe Zahl an zwei Orten. */
export function kostenZeilen(v: VerteilungVerlauf): KostenZeile[] {
  const mitGeraet = mehrereGeraete(v)
  return sortiert(v.segmente.filter((s) => s.kwh > 0)).map((s) => ({
    schluessel: s.schluessel,
    label: segmentLabel(s, mitGeraet),
    herkunft: herkunftText(s.herkunft),
    preisCent: s.preis_cent ?? null,
    kostenEuro: s.kosten_euro ?? null,
  }))
}

export interface VerteilungVerlaufDaten {
  rows: WaermeVerlaufRow[]
  stapel: VerlaufStapel[]
  linien: VerlaufLinie[]
  /** `{Zeilen-Name: Symbol}` für die Wetter-Achse; leer, wenn es keine gibt. */
  wetterSymbole: Record<string, string>
  hatTemperatur: boolean
  hatWetter: boolean
}

/** Zeilen und Serien des Verlaufs — für {@link WaermeVerlaufChart}.
 *
 *  ⚠ **Eine Periode ohne Menge trägt `null`, nicht `0`** (P4): Ein Tag, für den
 *  keine Aufteilung vorliegt, ist etwas anderes als ein Tag, an dem nichts lief
 *  — ein Balken der Höhe 0 sähe aus wie das Zweite. */
export function verteilungVerlaufDaten(v: VerteilungVerlauf): VerteilungVerlaufDaten {
  const mitGeraet = mehrereGeraete(v)
  // Ein Segment erscheint im Stapel, wenn es in irgendeiner Periode eine Menge
  // trägt. Die Verteilung darüber kann Segmente führen, die der Verlauf nicht
  // kennt (andere Quelle) — sie als leere Serie zu zeichnen hieße, eine Lücke
  // als Reihe von Nullen darzustellen.
  const imVerlauf = new Set<string>()
  for (const p of v.perioden) {
    for (const [k, kwh] of Object.entries(p.kwh_je_segment)) if (kwh > 0) imVerlauf.add(k)
  }
  const aktiv = sortiert(v.segmente.filter((s) => imVerlauf.has(s.schluessel)))

  const hatTemperatur = v.perioden.some((p) => p.temperatur_c != null)
  const wetterSymbole: Record<string, string> = {}
  for (const p of v.perioden) if (p.wetter_symbol) wetterSymbole[p.label] = p.wetter_symbol

  const rows: WaermeVerlaufRow[] = v.perioden.map((p) => {
    const row: WaermeVerlaufRow = { name: p.label }
    const leer = Object.keys(p.kwh_je_segment).length === 0
    for (const s of aktiv) {
      row[s.schluessel] = leer ? null : Math.round((p.kwh_je_segment[s.schluessel] ?? 0) * 100) / 100
    }
    // ⚠ `null` statt 0, wo kein Wert vorliegt — sonst zöge die Linie den Monat
    // auf den Gefrierpunkt.
    if (hatTemperatur) row.temperatur = p.temperatur_c ?? null
    return row
  })

  return {
    rows,
    stapel: aktiv.map((s) => ({
      key: s.schluessel,
      label: segmentLabel(s, mitGeraet),
      farbe: funktionsFarben(s.funktion).chart,
    })),
    linien: hatTemperatur
      ? [{
          key: 'temperatur', label: 'Außentemperatur',
          farbe: CHART_COLORS.temperatur, achse: 'rechts' as const, dezimalen: 1,
        }]
      : [],
    wetterSymbole,
    hatTemperatur,
    hatWetter: Object.keys(wetterSymbole).length > 0,
  }
}

/** Unterhalb dieser Menge ist eine Differenz eine Rundungsfrage, keine Aussage
 *  — dieselbe Schwelle wie bei den Rest-Zeilen des Verlaufs daneben. */
const DIFFERENZ_SCHWELLE_KWH = 0.05

export interface HinweisZeile { label: string; wert: string }

/**
 * Die Zeilen, die die **Differenzen benennen** statt sie hineinzurechnen.
 *
 * Drei verschiedene Sachverhalte, drei verschiedene Sätze (W-8):
 *
 * 1. *Aufgeteilte Menge X von Y kWh* — ein Gerät ohne jede Aufteilung steht in
 *    keinem Segment (W-17b, dieselbe Zeile wie am Betriebsart-Balken).
 * 2. *Im Verlauf X von Y kWh* — die Perioden kommen aus einer anderen Quelle
 *    als die Verteilung (Tagessäulen gegen Monatszeile, Konzept Kap. 6.3).
 * 3. *Strom ohne Stundenzuordnung* — was keine Stundenform hatte (P4).
 */
export function verteilungHinweise(
  v: VerteilungVerlauf,
  fmt: (n: number | null | undefined, stellen?: number) => string,
): HinweisZeile[] {
  const zeilen: HinweisZeile[] = []
  if (v.aufgeteilt_kwh > 0 && v.menge_kwh - v.aufgeteilt_kwh > DIFFERENZ_SCHWELLE_KWH) {
    zeilen.push({
      label: 'Aufgeteilte Menge',
      wert: `${fmt(v.aufgeteilt_kwh)} von ${fmt(v.menge_kwh)} kWh`,
    })
  }
  if (
    v.perioden.length > 0 && v.aufgeteilt_kwh > 0
    && Math.abs(v.aufgeteilt_kwh - v.verlauf_kwh) > DIFFERENZ_SCHWELLE_KWH
  ) {
    zeilen.push({
      label: 'Im Verlauf erfasst',
      wert: `${fmt(v.verlauf_kwh)} von ${fmt(v.aufgeteilt_kwh)} kWh`,
    })
  }
  if (v.ohne_stundenform_kwh != null && v.ohne_stundenform_kwh > DIFFERENZ_SCHWELLE_KWH) {
    zeilen.push({
      label: 'Strom ohne Stundenzuordnung',
      wert: `${fmt(v.ohne_stundenform_kwh, 1)} kWh`,
    })
  }
  return zeilen
}

/** Erscheint der Blockteil überhaupt? Ohne ein einziges Segment hat er nichts
 *  zu sagen — und ein leerer Kasten ist schlechter als kein Kasten. */
export function zeigtVerteilung(v: VerteilungVerlauf | null | undefined): boolean {
  return !!v && v.segmente.length > 0
}

/** W-8 — der Titel nennt, was wirklich drinsteht, und in welcher Auflösung. */
export function verteilungTitel(v: VerteilungVerlauf): string {
  const stufe = v.stufe === 'stunde' ? 'je Stunde'
    : v.stufe === 'tag' ? 'je Tag' : 'je Monat'
  return `Verteilung & Verlauf · ${stufe}`
}
