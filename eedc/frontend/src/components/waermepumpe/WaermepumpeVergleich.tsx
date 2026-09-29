/**
 * WaermepumpeVergleich — der Monats-/Saison-Vergleich mit JAZ ⇄ Strom ⇄ kWh/Kd
 * (Block ⑤ im IA-v4-Hub).
 *
 * - Metrik-Umschalter: Strom (kWh) ⇄ JAZ ⇄ **kWh/Kd** (wetternormiert)
 * - Achsen-Umschalter: Monate (je Jahr ein Balken pro Monat) ⇄ Saison
 *   (Winter/Heizperiode/Sommer über die ganze Laufzeit aggregiert)
 * - Saison: bei getrennter Strommessung nur Heizung (Warmwasser ausgeklammert);
 *   unvollständige Saisons blass + (n/Σ)-Label.
 * Eigener State (Toggles) — self-contained.
 */
import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { ChartLegende, SegmentControl } from '../ui'
import { HerkunftZeile } from '../blocks'
import { MONAT_KURZ, SAISON_FENSTER, SERIEN_PALETTE, CHART_HOVER_CURSOR, SERIE_GEDIMMT, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import type { InvestitionMonatsdaten } from '../../api/investitionen'
import { useLegendenToggle } from '../../hooks'
import { mitAnzahl } from '../../lib/plural'


/** Stromverbrauch eines Monats — aus der Layer-Zeitreihe, Rohspalte nur als Fallback.
 *
 * B3/H-1b (05.09.2026): Bei getrennter Strommessung ist `stromverbrauch_kwh` LEER
 * (der Strom steht in `strom_heizen_kwh`/`strom_warmwasser_kwh`, Registry-Bedingung
 * `!getrennte_strommessung`). Der Strom-Modus zeigte dort keinen einzigen Balken,
 * die Saison-Summe 0 — während die JAZ daneben aus dem Layer stimmte. Der Client
 * kennt `get_wp_strom_kwh` nicht und soll es nicht nachbauen (ADR-002/P12-Richtung):
 * er liest `jaz_je_monat[].strom_kwh`. Die Rohspalte bleibt nur für eine ältere
 * Antwort ohne das Feld. */
export const stromDesMonats = (
  md: InvestitionMonatsdaten,
  jazJeMonat?: { jahr: number; monat: number; strom_kwh?: number | null }[],
): number =>
  jazJeMonat?.find((x) => x.jahr === md.jahr && x.monat === md.monat)?.strom_kwh
  ?? (md.verbrauch_daten.stromverbrauch_kwh || 0)

/** Heizgradtage eines Monats, wie sie das WP-Dashboard liefert. */
export interface HeizgradtageMonat {
  jahr: number
  monat: number
  /** Σ max(0; Heizgrenze − Tagesmittel) über die erfassten Tage. */
  kd: number
  tage_mit_temperatur: number
  tage_im_monat: number
}

/** Metrik des Vergleichs — `kd` = wetternormiert (kWh je Heizgradtag). */
export type VergleichModus = 'jaz' | 'strom' | 'kd'

/**
 * Arbeitszahl je Monat aus dem Layer (ADR-002/P12). **Bis zum 02.09.2026
 * rechnete diese Komponente sie selbst** — an zwei Stellen, aus
 * `heizenergie + warmwasser` durch `stromverbrauch`. Keine der beiden kannte
 * den funktionsfremden Strom (Kuehlen/Lueften/Entfeuchten stand im Nenner)
 * oder die abgeleitete Waerme; im Saison-Zweig wurde daraus zusaetzlich ein
 * Sigma-Quotient ueber Monate mit gemischter Herkunft.
 */
export interface JazMonat {
  jahr: number; monat: number; wert: number | null; grund: string | null
  zaehler_kwh: number | null; nenner_kwh: number | null
  heizen_zaehler_kwh: number | null; heizen_nenner_kwh: number | null
  /** B3/H-1b: Stromverbrauch des Monats nach dem SoT — Rohspalte nur als Fallback. */
  strom_kwh?: number | null
}

/** Wetternormiert wird NUR mit getrennt gemessenem Heizstrom (SOLL §4.1).
 *
 * Der Gesamtstrom enthält Warmwasser, und das hängt nicht vom Wetter ab: Im
 * Übergangsmonat dominiert es den Zähler, während der Nenner gegen 0 läuft. Ein
 * abgeleiteter Modus-Split scheidet aus demselben Grund aus wie beim Nenner
 * einer Arbeitszahl (SOLL-§9-E7) — eine Verteilung ist kein Zähler. */
const GRUND_OHNE_GETRENNTE_MESSUNG =
  'Wetternormiert (kWh je Heizgradtag) nur mit getrennt gemessenem Heizstrom — '
  + 'der Gesamtstrom enthält Warmwasser, das nicht vom Wetter abhängt.'


/** Eine Zeile des Saison-Vergleichs — genau ein Balken. */
export interface SaisonZeile {
  name: string
  value: number | null
  label: string
  vollstaendig: boolean
  fill: string
  /** Style-Guide A6: die eingesetzten Werte, für den Tooltip (nur kWh/Kd). */
  herleitung?: string
}

/**
 * Die Saison-Aggregation als **reine Funktion** — Σ über das Fenster, nie ein
 * Mittel über Monatsquotienten (SOLL §5: eine Kennzahl wird über einen Zeitraum
 * neu gerechnet).
 *
 * ⚑ **Warum ausgelagert und nicht im JSX:** Recharts zeichnet in jsdom nichts
 * (`ResponsiveContainer` hat dort Breite 0). Eine Probe gegen Balken-Labels oder
 * Tooltips wäre grün, ohne je etwas gemessen zu haben — und bliebe grün, wenn
 * die Zahl kippt. Dieselbe Lehre wie in `tagGeraeteSerien.test.tsx`.
 */
export function baueSaisonDaten({
  monatsdaten, jazJeMonat, heizgradtageJeMonat, hatGetrennteStrom, cfg, modus,
  kdAktiv, farben,
}: {
  monatsdaten: InvestitionMonatsdaten[]
  jazJeMonat?: JazMonat[]
  heizgradtageJeMonat?: HeizgradtageMonat[]
  hatGetrennteStrom: boolean
  cfg: (typeof SAISON_FENSTER)[keyof typeof SAISON_FENSTER]
  modus: VergleichModus
  /** Ist der wetternormierte Modus wirklich aktiv (nicht nur gewählt)? */
  kdAktiv: boolean
  farben: readonly string[]
}): SaisonZeile[] {
  const jahre = [...new Set(monatsdaten.map((md) => md.jahr))].sort((a, b) => a - b)
  if (jahre.length === 0) return []
  const spanntJahr = cfg.monate.some((m) => m < cfg.startMonat)
  const minJ = jahre[0], maxJ = jahre[jahre.length - 1]
  const rows: SaisonZeile[] = []
  for (let startJahr = minJ - 1; startJahr <= maxJ; startJahr++) {
    // Sigma Q / Sigma E ueber das Fenster — richtig nach SOLL Paragraph 5
    // (neu berechnen, nie mitteln). **Beide Summen kommen aus dem Layer**
    // (ADR-002/P12): `nenner_kwh` traegt den funktionsfremden Strom bereits
    // abgezogen, und ein Monat ohne gueltige Kennzahl (`wert == null`) geht
    // gar nicht erst ein — sonst entstuende hier der Mischquotient neu, den
    // die Monatszeile gerade verweigert hat.
    // ⚠ Die Namen sagen Q und E, nicht „Waerme" und „Strom": `sumE` ist NICHT
    // der Stromverbrauch des Fensters — der funktionsfremde Anteil (Kuehlen,
    // Lueften, Entfeuchten) ist darin bereits abgezogen. Die alten Namen
    // (`sumWaerme`/`sumStrom`) haetten hier eine Menge behauptet, die so
    // nirgends steht; `sumStromAnzeige` traegt sie weiter fuer den
    // Strom-Modus, der genau das zeigen soll.
    let sumE = 0, sumQ = 0, sumStromAnzeige = 0, monateMitDaten = 0
    // Wetternormierung: Σ Heizstrom ÷ Σ Kd, ebenfalls neu gerechnet (SOLL §5).
    let sumKd = 0, sumHeizstrom = 0, monateNormiert = 0
    for (const m of cfg.monate) {
      const kalenderJahr = m >= cfg.startMonat ? startJahr : startJahr + 1
      const md = monatsdaten.find((x) => x.monat === m && x.jahr === kalenderJahr)
      if (!md) continue
      monateMitDaten++
      const az = jazJeMonat?.find((x) => x.jahr === kalenderJahr && x.monat === m)
      if (kdAktiv) {
        const kd = heizgradtageJeMonat
          ?.find((x) => x.jahr === kalenderJahr && x.monat === m)?.kd ?? null
        // ⛔ Der Zähler ist der **Heizstrom**, nie `strom_kwh`: Letzterer
        // enthält Warmwasser, das der Nenner nicht erklärt.
        const heizstrom = az?.heizen_nenner_kwh
        // ⚠ Ein Monat geht nur ein, wenn er BEIDES trägt. Sonst entstünde
        // Σ Strom aus vier Monaten über Σ Kd aus zweien — eine Zahl, die
        // doppelt so hoch aussieht wie die Anlage arbeitet.
        if (kd != null && kd > 0 && heizstrom != null) {
          sumKd += kd
          sumHeizstrom += heizstrom
          monateNormiert++
        }
        continue
      }
      if (modus !== 'jaz') { sumStromAnzeige += stromDesMonats(md, jazJeMonat); continue }
      const q = hatGetrennteStrom ? az?.heizen_zaehler_kwh : az?.zaehler_kwh
      const e = hatGetrennteStrom ? az?.heizen_nenner_kwh : az?.nenner_kwh
      if (q != null && e != null) { sumQ += q; sumE += e }
    }
    if (monateMitDaten === 0) continue
    // Ein Fenster ohne Heizgradtage (Sommer) bekommt KEINEN Balken — weder
    // eine 0 noch einen Unendlich-Wert. Der Grund steht unter dem Chart.
    if (kdAktiv && sumKd <= 0) continue
    const vollstaendig = kdAktiv
      ? monateNormiert === cfg.monate.length
      : monateMitDaten === cfg.monate.length
    const basisName = spanntJahr
      ? `${String(startJahr % 100).padStart(2, '0')}/${String((startJahr + 1) % 100).padStart(2, '0')}`
      : `${startJahr}`
    const wert = modus === 'jaz'
      ? (sumE > 0 ? Math.round((sumQ / sumE) * 100) / 100 : null)
      : kdAktiv
        ? Math.round((sumHeizstrom / sumKd) * 100) / 100
        : Math.round(sumStromAnzeige)
    // Zweite Vollständigkeits-Achse: „25/26 (2/4 · Temp 2/4)" — die erste Zahl
    // sind die Monate mit Gerätedaten, die zweite die davon, die Heizgradtage
    // UND Heizstrom tragen und damit wirklich in die Summe eingehen.
    const zusatz = kdAktiv
      ? `${monateMitDaten}/${cfg.monate.length} · Temp ${monateNormiert}/${cfg.monate.length}`
      : `${monateMitDaten}/${cfg.monate.length}`
    rows.push({
      name: vollstaendig && monateMitDaten === cfg.monate.length
        ? basisName : `${basisName} (${zusatz})`,
      value: wert,
      label: wert == null
        ? '' : (modus === 'jaz' || kdAktiv ? fmtZahl(wert, 2) : wert.toLocaleString('de-DE')),
      vollstaendig,
      // D12-4: Farbe je Saison-Instanz in die Daten → ChartTooltip-Swatch trifft den Balken (sonst SERIE_NEUTRAL-Grau).
      fill: farben[rows.length % farben.length],
      // Style-Guide A6: die eingesetzten Werte reisen mit der Zeile, damit der
      // Tooltip sie nicht über den Zahlenwert zurücksuchen muss.
      herleitung: kdAktiv
        ? `${fmtZahl(sumHeizstrom, 1)} kWh ÷ ${fmtZahl(sumKd, 1)} Kd`
        : undefined,
    })
  }
  return rows
}

/** Der Tooltip-Text eines Balkens — bei kWh/Kd samt Herleitung (A6). */
export function saisonWertText(
  v: number,
  modus: VergleichModus,
  kdAktiv: boolean,
  herleitung?: string,
): string {
  if (modus === 'jaz') return fmtZahl(v, 2)
  if (!kdAktiv) return `${v} kWh`
  return herleitung
    ? `${fmtZahl(v, 2)} kWh/Kd · ${herleitung}`
    : `${fmtZahl(v, 2)} kWh/Kd`
}

/**
 * Was der Saison-Balken zählt — **je Kennzahl**, nicht nur je Messaufbau (N-452).
 *
 * ⛔ **Der Satz hing bis zum 12.09.2026 allein an `hatGetrennteStrom`** und sagte
 * bei getrennter Messung in *jedem* Modus „Saison-Strom = nur Heizung
 * (Warmwasser ausgeklammert)". Für die **JAZ** stimmt das (sie summiert
 * `heizen_zaehler_kwh`/`heizen_nenner_kwh`), für den **Strom-Balken** nicht: Der
 * zeigt `jaz_je_monat[].strom_kwh`, und das ist der Gesamtstrom des Geräts
 * (`get_wp_strom_kwh` summiert im getrennten Zweig Heizen + Warmwasser und, wo
 * gemessen, den Kühlstrom). Gemessen: 300,0 statt 268,6 kWh, +11,7 %. Der
 * Widerspruch entstand mit B3/H-1b — davor las der Strom-Modus die bei
 * getrennter Messung **leere** Rohspalte, der Balken stand auf 0 und der Satz
 * fiel nicht auf. **Es ändert sich keine Zahl, nur die Auskunft darüber**
 * (SOLL §3.3/S2: „Ein Balken sagt, was er zeigt").
 */
function saisonFussText(
  modus: VergleichModus,
  kdAktiv: boolean,
  hatGetrennteStrom: boolean,
): string {
  if (kdAktiv) {
    return 'Die Heizgradtage des Fensters werden summiert, nicht gemittelt.'
      + ' Normiert wird nur der Heizbetrieb; Warmwasser bleibt außen vor.'
      + ' Ein Monat geht nur ein, wenn er Heizgradtage und Heizstrom trägt.'
  }
  if (modus === 'jaz') {
    return hatGetrennteStrom
      ? 'Saison-JAZ = nur Heizung (Warmwasser ausgeklammert, getrennte Strommessung).'
      : 'Saison-JAZ = alle Funktionen zusammen (inkl. Warmwasser) — keine getrennte Strommessung erfasst.'
  }
  return hatGetrennteStrom
    ? 'Saison-Strom = Gesamtstrom des Geräts (Heizen + Warmwasser, bei gemessenem Kühlzähler auch Kühlen).'
    : 'Saison-Strom inkl. Warmwasser — keine getrennte Strommessung erfasst.'
}

export function WaermepumpeVergleich({ monatsdaten, jazJeMonat, hatGetrennteStrom, heizgradtageJeMonat, heizgradtageGrund, heizgrenzeC }: {
  monatsdaten: InvestitionMonatsdaten[]
  jazJeMonat?: JazMonat[]
  hatGetrennteStrom: boolean
  /** Heizgradtage je Monat — Eigenschaft der **Anlage**, nicht des Geräts. */
  heizgradtageJeMonat?: HeizgradtageMonat[]
  /** Warum die Temperaturreihe weniger hergibt als die Verbrauchshistorie (S3). */
  heizgradtageGrund?: string | null
  /** Die Heizgrenze aus dem Layer — damit der Herkunftssatz sie nicht doppelt führt. */
  heizgrenzeC?: number
}) {
  const stromVon = (md: InvestitionMonatsdaten): number => stromDesMonats(md, jazJeMonat)
  /** (jahr, monat) → Arbeitszahl aus dem Layer. */
  const jazVon = (jahr: number, monat: number): number | null =>
    jazJeMonat?.find((x) => x.jahr === jahr && x.monat === monat)?.wert ?? null
  const [modus, setModus] = useState<VergleichModus>('strom')
  const [achse, setAchse] = useState<'monate' | 'saison'>('monate')
  const [fenster, setFenster] = useState<keyof typeof SAISON_FENSTER>('winter')
  // B7-Legenden-Toggle (Monate-Zweig, Serie = Jahr); Reset bei Modus-/Achsen-Wechsel.
  const legende = useLegendenToggle(`${modus}:${achse}`)

  const jahre = [...new Set(monatsdaten.map((md) => md.jahr))].sort((a, b) => a - b)
  const jahrFarben = SERIEN_PALETTE

  // ─── Wetternormierung: wird sie überhaupt angeboten? (SOLL §4.1, K-3) ──────
  // ⛔ ZWEI Bedingungen, und beide sind nötig. Ohne getrennt gemessenen
  // Heizstrom fehlt der **Zähler**, ohne Temperaturreihe der **Nenner** — die
  // Fußzeile nennt unten den zutreffenden Grund, statt einen leeren Modus
  // anzubieten (SOLL §3.3/S3).
  const hatHeizstrom = (jazJeMonat ?? []).some((x) => x.heizen_nenner_kwh != null)
  const hatHeizgradtage = (heizgradtageJeMonat ?? []).some((h) => h.kd > 0)
  // K-3: NUR auf der Saison-Achse. Auf der Monatsachse stünde für Mai 3,889
  // gegen November 0,531 an derselben Maschine (Faktor 7,3) — Grundlast,
  // Warmwasser-Beimischung und Takt-Verluste skalieren nicht mit Kd und
  // dominieren den Übergangsmonat. Im Juni gibt es gar keinen Nenner.
  const kdMoeglich = achse === 'saison' && hatHeizstrom && hatHeizgradtage
  const kdAktiv = modus === 'kd' && kdMoeglich

  // Monatsvergleich: Jan–Dez als Gruppen, je ein Balken pro Jahr.
  const monatData = Array.from({ length: 12 }, (_, i) => {
    const monat = i + 1
    const entry: Record<string, string | number | null> = { name: MONAT_KURZ[monat] }
    for (const jahr of jahre) {
      const md = monatsdaten.find((m) => m.monat === monat && m.jahr === jahr)
      if (md) {
        const strom = stromVon(md)
        entry[`val_${jahr}`] = modus === 'jaz'
          ? jazVon(jahr, monat)
          : (strom > 0 ? Math.round(strom) : null)
      } else {
        entry[`val_${jahr}`] = null
      }
    }
    return entry
  })

  // Saison-Vergleich: Fokus-Fenster über die gesamte Laufzeit zu Saison-Instanzen.
  const cfg = SAISON_FENSTER[fenster]
  const saisonData = baueSaisonDaten({
    monatsdaten, jazJeMonat, heizgradtageJeMonat, hatGetrennteStrom,
    cfg, modus, kdAktiv, farben: jahrFarben,
  })

  const achsenLabel = modus === 'jaz' ? 'JAZ' : kdAktiv ? 'kWh/Kd' : 'kWh'
  const wertText = (v: number, zeile?: Record<string, unknown>): string =>
    saisonWertText(
      v, modus, kdAktiv,
      typeof zeile?.herleitung === 'string' ? zeile.herleitung : undefined,
    )

  /** Warum es (noch) keine wetternormierte Zahl gibt — S3, nicht „—". */
  const normierungsGrund = hatHeizstrom
    ? (heizgradtageGrund ?? null)
    : GRUND_OHNE_GETRENNTE_MESSUNG

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end flex-wrap gap-2">
        <SegmentControl
          ariaLabel="Kennzahl"
          optionen={kdMoeglich
            ? [{ key: 'strom', label: 'Strom' }, { key: 'jaz', label: 'JAZ' }, { key: 'kd', label: 'kWh/Kd' }] as const
            : [{ key: 'strom', label: 'Strom' }, { key: 'jaz', label: 'JAZ' }] as const}
          value={modus}
          onChange={setModus}
        />
        <SegmentControl
          ariaLabel="Achse"
          optionen={[{ key: 'monate', label: 'Monate' }, { key: 'saison', label: 'Saison' }] as const}
          value={achse}
          onChange={(a) => {
            setAchse(a)
            // K-3: Die normierte Größe gibt es nur über eine Saison. Wer auf
            // „Monate" wechselt, landet auf der Metrik, von der er kam.
            if (a === 'monate' && modus === 'kd') setModus('strom')
          }}
        />
        {achse === 'saison' && (
          <SegmentControl
            ariaLabel="Saison-Fenster"
            optionen={(Object.keys(SAISON_FENSTER) as (keyof typeof SAISON_FENSTER)[]).map((key) => ({
              key, label: SAISON_FENSTER[key].label,
              title: `${SAISON_FENSTER[key].label} (${SAISON_FENSTER[key].bereich})`,
            }))}
            value={fenster}
            onChange={setFenster}
          />
        )}
      </div>

      {kdAktiv && (
        <HerkunftZeile herkunft={{
          zustand: 'gemessen',
          quelleLabel: 'Außentemperatur',
          bezug: 'Heizgradtage',
          hinweis: `Heizgrenze ${fmtZahl(heizgrenzeC ?? 15, 0)} °C · je Tag max(0; ${fmtZahl(heizgrenzeC ?? 15, 0)} °C − Tagesmittel)`,
        }} />
      )}

      {achse === 'saison' && saisonData.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-16">
          {kdAktiv
            ? `Im Fenster ${cfg.label} (${cfg.bereich}) gibt es keine Heizgradtage — eine Wetternormierung ist dort ohne Aussage.`
            : `Keine Daten im Fenster ${cfg.label} (${cfg.bereich}).`}
        </p>
      ) : (
        <div className="h-72 text-gray-700 dark:text-gray-200">
          <ResponsiveContainer width="100%" height="100%">
            {achse === 'monate' ? (
              <BarChart data={monatData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" vertical={false} />
                <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis domain={modus === 'jaz' ? [0, 6] : undefined} {...yAchse(false)} tickFormatter={achsenTick} label={achsenEinheit(modus === 'jaz' ? 'JAZ' : 'kWh')} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip formatter={(v) => modus === 'jaz' ? fmtZahl(v, 2) : `${v} kWh`} />} />
                <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
                {jahre.map((jahr, i) => (
                  <Bar key={jahr} dataKey={`val_${jahr}`} name={`${jahr}`} fill={jahrFarben[i % jahrFarben.length]} hide={legende.istVersteckt(`val_${jahr}`)} />
                ))}
              </BarChart>
            ) : (
              // D17-4: SoT-Margin wie der Monats-Modus (die früheren left:0/bottom:0-Overrides
              // schnitten die längeren, −45°-gedrehten Saison-Labels „23/24 (3/4)" ab).
              // BEWUSST OHNE Legende: der Saison-Modus ist EINE Serie (JAZ bzw. Strom) mit
              // per-Instanz-Farben je Saison — jede Scheibe/Balken IST über die X-Achse +
              // Wert-Label beschriftet; eine Farb-Legende dazu wäre eine Doppel-Beschriftung
              // (Style-Guide B7). Die Blass-Dimmung erklärt der Fuß-Hinweis. (check:charts
              // erlaubt Einzelserien ohne Legende.)
              <BarChart data={saisonData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" vertical={false} />
                <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Saison) */ />
                {/* Domain bei kWh/Kd bewusst frei: die Größenordnung hängt am Gebäude,
                    eine feste Skala wie bei der JAZ [0,6] würde Anlagen abschneiden. */}
                <YAxis domain={modus === 'jaz' ? [0, 6] : undefined} {...yAchse(false)} tickFormatter={achsenTick} label={achsenEinheit(achsenLabel)} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip formatter={(v, _n, zeile) => wertText(v, zeile)} />} />
                <Bar dataKey="value" name={modus === 'jaz' ? 'JAZ' : kdAktiv ? 'Strom je Heizgradtag' : 'Strom'}>
                  {saisonData.map((s, i) => (
                    <Cell key={i} fill={jahrFarben[i % jahrFarben.length]} fillOpacity={s.vollstaendig ? 1 : SERIE_GEDIMMT} />
                  ))}
                  <LabelList dataKey="label" position="top" fill="currentColor" fontSize={13} fontWeight={600} />
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}

      {achse === 'saison' && saisonData.length > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {cfg.label}: {cfg.bereich} ({mitAnzahl(cfg.monate.length, 'Monat', 'Monate')}).{' '}
          {/* ⚠ Die Definition steht bereits in der HerkunftZeile über dem Chart
              (Style-Guide B7: keine Doppelbeschriftung). Hier steht nur, was
              sie NICHT sagt — die Abgrenzung und die Eingangsregel. */}
          {saisonFussText(modus, kdAktiv, hatGetrennteStrom)}{' '}
          Blasse Balken kennzeichnen eine unvollständige Saison.
        </p>
      )}

      {/* S3: Warum die Wetternormierung weniger zeigt als die Sicht daneben —
          der Satz steht auch dann da, wenn es die Schaltfläche gar nicht gibt.
          Genau das ist der Demo-Fall: Winter 24/25 ist vollständig gepflegt und
          hat trotzdem keinen normierten Balken, weil die Temperaturreihe jünger
          ist als die Wärmepumpe. */}
      {achse === 'saison' && normierungsGrund && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{normierungsGrund}</p>
      )}
    </div>
  )
}
