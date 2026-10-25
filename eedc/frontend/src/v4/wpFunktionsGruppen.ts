/**
 * Die Detail-Liste des Wärme/Klima-Blocks **je Funktion** — Bauschnitt 8
 * (Konzept Wärme/Klima §4 ②, §5 Position 3; SOLL §4.1).
 *
 * Bis 11.09.2026 stand die Liste nach **Größe** geordnet: erst zwei Stromzeilen,
 * dann drei Arbeitszahlen, die Wärme je Funktion nur im Balken darüber, die Kälte
 * nirgends als Zahl. Wer wissen wollte, *warum* die Heizzahl so aussieht, musste
 * die Zutaten über drei Elemente zusammensuchen.
 *
 * ⭐ **Jede Gruppe zeigt Zähler und Nenner ihrer eigenen Zahl.** Heizen und
 * Warmwasser teilen durch den getrennt gemessenen Strom (F5), Kühlen durch den
 * Betriebsart-Strom — genau die Mengen, die hier daneben stehen. Die Proben
 * `test_bs8_funktions_gruppen.py` halten den Vertrag im Backend fest.
 *
 * ⛔ **Keine Überschrift ohne Menge.** Eine Überschrift behauptet, dass das Gerät
 * diese Funktion hat. Eine Split-Klima bekäme sonst „Warmwasser", jede
 * Heizungs-Wärmepumpe im Winter „Kühlen" (Gegenprüfung G7). Eine Funktion ohne
 * Menge, aber mit Grund, bleibt die eine Zeile, die sie bis hierher war —
 * unverändert im Wortlaut, weil der Name die Funktion ohnehin trägt.
 *
 * Reine Funktion, damit sie ohne Render prüfbar ist (Bauform `verlaufRestZeilen`).
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { fmtZahl } from '../lib'
import { GROESSE, imKasten, type GroessenName } from './waermeKlimaSicht'

/**
 * Die **eine** Herleitung einer Arbeitszahl aus Zähler und Nenner, die der Layer benutzt hat (A6) —
 * «25,6 kWh Wärme ÷ 5,6 kWh Strom». P-433-3 S3-9 (Master 25.10.2026): das Backend liefert die Mengen ungerundet,
 * formatiert wird **hier**, mit einer Nachkommastelle (Style-Guide C3) — Tag («Je Funktion», «davon Zusatzheizung»)
 * und Hub (Kennzahl «AZ ohne Zusatzheizung») zeigen für dieselben Mengen denselben Text. `null`, wenn eine Seite
 * fehlt (gesperrte Zahl: keine Rechnung aus „—").
 */
export function herleitungMengen(
  zaehlerKwh: number | null | undefined, nennerKwh: number | null | undefined, zaehlerName = 'Wärme',
): string | null {
  if (zaehlerKwh == null || nennerKwh == null) return null
  return `${fmtZahl(zaehlerKwh, 1)} kWh ${zaehlerName} ÷ ${fmtZahl(nennerKwh, 1)} kWh Strom`
}

export type WpFunktion = 'heizen' | 'warmwasser' | 'kuehlen'

export type FunktionsZeile =
  | { art: 'strom' | 'nutzenergie'; label: string; kwh: number }
  /** ⛔ **Ohne sichtbaren `grund`** — seit der D-Sicht (14.09.2026) trägt eine
   *  Arbeitszahl-Zeile entweder eine Zahl oder ein „—" ohne Text. Ein
   *  **Ausstattungs**-Grund steht im Kasten „Was noch möglich wäre".
   *
   *  ⭐ **Ein ZEITRAUM-Grund steht im `tooltip`** (Entscheid Fable, 14.09.2026,
   *  Gegenlesung zu A-4): Er gehört in keinen Kasten — es gibt nichts zu tun —,
   *  aber er soll auch nicht verschwinden. **S3 bleibt damit erfüllt: der Grund
   *  ist da, eine Geste entfernt**, ohne dass der Block wieder mit Texten
   *  vollläuft. */
  | { art: 'arbeitszahl'; label: string; wert: number | null; tooltip?: string
      /** P-433-3 S3: «16,0 kWh Wärme ÷ 3,9 kWh Strom» aus Zähler/Nenner des Layers — nur am Tag (Monat und Jahr
       *  liefern sie nicht) und nur mit Zahl. */
      herleitung?: string }

export interface FunktionsGruppe {
  funktion: WpFunktion
  titel: string
  zeilen: FunktionsZeile[]
}

/** P-433-3 S2 (#432, Tag/Monat/Jahr): die Zeile «davon Zusatzheizung x kWh · AZ ohne Zusatzheizung y (gerechnet)» unter
 *  den Gruppen — nur mit Heizstab-Zähler (B2). Sie gehört keiner Funktion: der Heizstab-Strom ist eine Teilmenge des
 *  Gerätestroms (H-B), die Zahl die Hauptzahl ohne ihn. Wert ODER Grund kommen fertig aus dem Layer. */
export interface ZusatzheizungZeile {
  kwh: number
  /** «AZ ohne Zusatzheizung» — `null` heißt gesperrt, der Grund steht dann in `grund`. */
  az: number | null
  grund: string | null
  /** Herkunft («gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen») und Herleitung — beim Überfahren. */
  hinweis: string | null
  zaehlerKwh: number | null
  nennerKwh: number | null
}

export interface FunktionsGruppen {
  gruppen: FunktionsGruppe[]
  zusatzheizung?: ZusatzheizungZeile
}

type Zahl = number | null | undefined

interface Definition {
  funktion: WpFunktion
  titel: string
  strom: [string, Zahl]
  nutzenergie: [string, Zahl]
  arbeitszahl: [string, Zahl, string | null | undefined]
  /** Zähler, Nenner und Name des Zählers der Arbeitszahl (P-433-3 S3, Herleitung). */
  herleitung: [Zahl, Zahl, string]
  /** Unter welchem Bezeichner diese Arbeitszahl im Kasten „Was noch möglich
   *  wäre" stehen kann (D-Sicht). */
  kasten: GroessenName
}

/** Die Namen der Mengen sind die des Formulars (S1: *Strom Heizen*, *Heizwärme*,
 *  *Warmwasser-Wärme*); die Kennzahl behält ihren eingeführten Namen. */
function definitionen(d: AktuellerMonatResponse): Definition[] {
  return [
    {
      funktion: 'heizen', titel: 'Heizen',
      strom: ['Strom Heizen', d.wp_strom_heizen_kwh],
      nutzenergie: ['Heizwärme', d.wp_heizung_kwh],
      arbeitszahl: ['Arbeitszahl · Heizen', d.wp_jaz_heizen, d.wp_jaz_heizen_grund],
      herleitung: [d.wp_jaz_heizen_zaehler_kwh, d.wp_jaz_heizen_nenner_kwh, 'Wärme'],
      kasten: GROESSE.heizen,
    },
    {
      funktion: 'warmwasser', titel: 'Warmwasser',
      strom: ['Strom Warmwasser', d.wp_strom_warmwasser_kwh],
      nutzenergie: ['Warmwasser-Wärme', d.wp_warmwasser_kwh],
      arbeitszahl: ['Arbeitszahl · Warmwasser', d.wp_jaz_warmwasser, d.wp_jaz_warmwasser_grund],
      herleitung: [d.wp_jaz_warmwasser_zaehler_kwh, d.wp_jaz_warmwasser_nenner_kwh, 'Wärme'],
      kasten: GROESSE.warmwasser,
    },
    {
      // Kühlen: Betriebsart = Funktion, der Strom ist derselbe wie im Segment
      // „Kühlen" des Betriebsart-Balkens.
      funktion: 'kuehlen', titel: 'Kühlen',
      strom: ['Strom Kühlen', d.wp_modus_strom_kuehlen_kwh],
      nutzenergie: ['Kälte', d.wp_kaelte_kwh],
      arbeitszahl: ['Arbeitszahl · Kühlen', d.wp_jaz_kuehlen, d.wp_jaz_kuehlen_grund],
      herleitung: [d.wp_jaz_kuehlen_zaehler_kwh, d.wp_jaz_kuehlen_nenner_kwh, 'Kälte'],
      kasten: GROESSE.kuehlen,
    },
  ]
}

export function wpFunktionsGruppen(d: AktuellerMonatResponse): FunktionsGruppen {
  const gruppen: FunktionsGruppe[] = []
  const moeglich = d.wp_moeglich ?? []
  for (const def of definitionen(d)) {
    const [azLabel, azWert, azGrund] = def.arbeitszahl
    // ── D-Sicht (Konzept §6, 14.09.2026) ────────────────────────────────────
    //
    // ⛔ **Hier stand bis dahin: „Auch das gesperrte ‚—' erscheint, mit seinem
    // Grund (S3)."** Das war richtig und trotzdem der Grund, warum dieser Block
    // aus Strichen bestand: Ein einziger fehlender Zähler erzeugte zwei bis drei
    // Zeilen, die alle denselben Satz trugen.
    //
    // Jetzt entscheidet der **Layer** über die Klasse des Grundes, und diese
    // Liste liest nur das Ergebnis:
    //
    //   • Grund im Kasten (**Ausstattung**) ⇒ die Zeile entfällt; der Satz steht
    //     einmal am Blockende, mit dem Handgriff daneben.
    //   • Grund **nicht** im Kasten (**Zeitraum**) ⇒ „—" ohne Text, wie bei
    //     einer Heizzahl im Juni: Es gibt nichts zu tun.
    //
    // ⚠ **Die Mengen-Zeilen bleiben unberührt** (K1). Gesperrt wird eine
    // Kennzahl, nie eine Messung.
    const azImKasten = azWert == null && imKasten(moeglich, def.kasten)
    const az: FunktionsZeile | null = (azWert != null || (azGrund && !azImKasten))
      ? {
          art: 'arbeitszahl', label: azLabel, wert: azWert ?? null,
          // D-Sicht 2: ein Zeitraum-Grund zeigt „—" ohne sichtbaren Text — und
          // nennt sich beim Überfahren. Bei vorhandener Zahl gibt es nichts zu
          // erklären.
          tooltip: (azWert == null && azGrund) ? azGrund : undefined,
          herleitung: azWert != null ? (herleitungMengen(...def.herleitung) ?? undefined) : undefined,
        }
      : null
    const hatMenge = (def.strom[1] ?? 0) > 0 || (def.nutzenergie[1] ?? 0) > 0
    if (!hatMenge) {
      // ⛔ **Eine Zeile ohne Menge und ohne Grund-Text hat nichts zu sagen.**
      // Bis zur D-Sicht war sie der Träger des Grundes; der steht jetzt im
      // Kasten. Ein nacktes „Arbeitszahl · Heizen —" wäre genau die
      // Strich-Zeile, gegen die das Paket gebaut ist.
      continue
    }
    const zeilen: FunktionsZeile[] = []
    // `!= null`: eine gemessene 0 bleibt stehen — sie sagt „getrennt erfasst,
    // aktuell nichts", und das ist etwas anderes als „nicht erfasst".
    for (const [label, kwh, art] of [
      [...def.strom, 'strom'], [...def.nutzenergie, 'nutzenergie'],
    ] as const) {
      if (kwh != null) zeilen.push({ art, label, kwh })
    }
    if (az) zeilen.push(az)
    gruppen.push({ funktion: def.funktion, titel: def.titel, zeilen })
  }
  const zusatzheizung = zusatzheizungZeile(d)
  return zusatzheizung ? { gruppen, zusatzheizung } : { gruppen }
}

/** S2: die Zusatzheizung-Zeile aus der Tagesantwort — `undefined` ohne Heizstab-Zähler. */
function zusatzheizungZeile(d: AktuellerMonatResponse): ZusatzheizungZeile | undefined {
  if (d.wp_heizstab_kwh == null) return undefined
  return {
    kwh: d.wp_heizstab_kwh,
    az: d.wp_jaz_ohne_zusatzheizung ?? null,
    grund: d.wp_jaz_ohne_zusatzheizung_grund ?? null,
    hinweis: d.wp_jaz_ohne_zusatzheizung_hinweis ?? null,
    zaehlerKwh: d.wp_jaz_ohne_zusatzheizung_zaehler_kwh ?? null,
    nennerKwh: d.wp_jaz_ohne_zusatzheizung_nenner_kwh ?? null,
  }
}

/** E3 (b): Zeigen die Gruppen einen **getrennt gemessenen** Strom (F5), stehen im
 *  Block zwei verschiedene Strommengen „Heizen" — die der Funktion hier und die
 *  der Betriebsart im Balken (sie enthält den Warmwasser-Strom, IST §888). Dann
 *  muss der Balken sagen, dass er nach Betriebsart aufteilt (S2). */
export function zeigtStromJeFunktion(fg: FunktionsGruppen): boolean {
  return fg.gruppen.some((g) => g.funktion !== 'kuehlen' && g.zeilen.some((z) => z.art === 'strom'))
}
