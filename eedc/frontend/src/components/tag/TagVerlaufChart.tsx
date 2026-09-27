/**
 * TagVerlaufChart — Butterfly-Stundenchart eines Tages (Quellen ▲ / Senken ▼).
 *
 * Aus der IST-„Tagesdetail"-Sicht (`pages/auswertung/EnergieprofilTab.tsx`)
 * extrahiert, damit Cockpit/Tag (v4) und die IST-Seite EINE Code-Wahrheit teilen
 * (Konvergenz-Leitprinzip, wie Aussicht ↔ EnergieprofilPrognose). Reine
 * Darstellung aus `StundenWert[]` + `SerieInfo[]` (extra Serien) — kein Daten-Laden.
 * Farben ausschließlich aus `lib` (kein Inline-Hex, Regel 0a).
 */
import { useCallback, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { ChartLegende, eedcTooltipProps } from '../ui'
import { EXTRA_SERIEN_FARBEN, PV_MODUL_FARBEN, KATEGORIE_FARBEN, CHART_COLORS, CHART_LABELS, HILFSLINIE_DASH, AREA_FILL_OPACITY, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { pvRestKw, pvSplitKw, wpRestKw, wpSplitKw } from '../../lib/erzeugerSpalten'
import { useChartTheme } from '../../context/ThemeContext'
import { useLegendenToggle } from '../../hooks'
import { erfassteSenken, spanneDerZeile, type SenkenKey } from './TagWerteTabelle'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

interface ChartSerie { dataKey: string; label: string; farbe: string; stackId: 'quellen' | 'senken'; hideLabel?: boolean }

/** Rest-Serie „PV (übrige)" erst ab dieser Stundenleistung — darunter ist der
 *  Rest Rundung, und eine Legenden-Zeile für 0,01 kW verwirrt mehr als sie sagt.
 *  Dieselbe Schwelle gilt für „Wärmepumpe (übrige)" auf der Senkenseite. */
const PV_REST_SCHWELLE_KW = 0.05

/** Ab wie vielen Funktions-Serien die WP-Fläche aufgeschlüsselt wird. Bei einer
 *  einzigen wäre die Funktionsreihe die WP-Reihe unter anderem Namen — dieselbe
 *  Grenze wie `ERZEUGER_MIN_ANZAHL` auf der Quellenseite. */
const WP_SPLIT_MIN_SERIEN = 2

/**
 * Die Serienliste des Butterfly-Charts — **rein**, damit die Regel prüfbar ist.
 *
 * ⚑ **Warum ausgelagert und nicht am gerenderten DOM geprüft** (gemessen
 * 09.09.2026): Recharts zeichnet in jsdom nichts, weil `ResponsiveContainer`
 * dort die Breite 0 hat. Eine Probe „Legendeneintrag nicht im DOM" wäre deshalb
 * grün, ohne je etwas gemessen zu haben — und bliebe grün, wenn die Serie
 * zurückkäme. Genau die Sorte Prüfer, die aufs falsche Objekt zeigt.
 * (Die Stundenwerte-Tabelle daneben lässt sich in dieser Umgebung überhaupt
 * nicht rendern — auch unverändert nicht; deshalb gibt es dort bis heute nur
 * Proben auf reine Funktionen.)
 */
export function baueChartSerien({
  pvAufgeschluesselt, zeigePvRest, erzeugerSerien, extraErzeuger, extraVerbraucher, senkenErfasst,
  wpAufgeschluesselt = false, zeigeWpRest = false, wpSerien = [],
}: {
  pvAufgeschluesselt: boolean
  zeigePvRest: boolean
  erzeugerSerien: SerieInfo[]
  extraErzeuger: SerieInfo[]
  extraVerbraucher: SerieInfo[]
  senkenErfasst: Set<SenkenKey>
  wpAufgeschluesselt?: boolean
  zeigeWpRest?: boolean
  wpSerien?: SerieInfo[]
}): ChartSerie[] {
  const r: ChartSerie[] = []
  if (pvAufgeschluesselt) {
    // Modul-Schattierungen statt kategorischer Fremdfarben: hier liegen Module
    // UND Rollen (Batterie/Netz/Haushalt) im selben Stapel — genau der Scope
    // der Regel an `PV_MODUL_FARBEN`.
    erzeugerSerien.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: PV_MODUL_FARBEN[i % PV_MODUL_FARBEN.length], stackId: 'quellen' }))
    if (zeigePvRest) r.push({ dataKey: 'pv_rest', label: 'PV (übrige)', farbe: KATEGORIE_FARBEN.pv, stackId: 'quellen' })
  } else {
    r.push({ dataKey: 'pv', label: 'PV', farbe: KATEGORIE_FARBEN.pv, stackId: 'quellen' })
  }
  extraErzeuger.forEach((es, i) =>
    r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_SERIEN_FARBEN[i % EXTRA_SERIEN_FARBEN.length], stackId: 'quellen' }))
  r.push({ dataKey: 'bat_pos', label: 'Batterie', farbe: KATEGORIE_FARBEN.batterie, stackId: 'quellen' })
  r.push({ dataKey: 'bat_neg', label: 'Batterie \u2193', farbe: KATEGORIE_FARBEN.batterie, stackId: 'senken', hideLabel: true })
  r.push({ dataKey: 'netz_pos', label: 'Stromnetz', farbe: KATEGORIE_FARBEN.netz, stackId: 'quellen' })
  r.push({ dataKey: 'netz_neg', label: 'Stromnetz \u2193', farbe: KATEGORIE_FARBEN.netz, stackId: 'senken', hideLabel: true })
  r.push({ dataKey: 'hausverbrauch', label: 'Hausverbrauch', farbe: KATEGORIE_FARBEN.haushalt, stackId: 'senken' })
  // JayJayX (simon42 T89667 #309): die beiden **dedizierten** Gerätesenken sind
  // die einzigen, die bis hierher unbedingt im Stapel standen — bei ihm zwei
  // Flächen für Geräte, die er nicht besitzt.
  if (senkenErfasst.has('waermepumpe_kw')) {
    if (wpAufgeschluesselt) {
      // Funktions-Split (WK-09 B1): dieselben zwei Flächen, die Cockpit → Live
      // schon zeichnet — sie **ersetzen** die WP-Fläche, statt obendrauf zu
      // liegen (die `erzeugerSerien`-Regel, eine Senke statt einer Quelle).
      // Farben aus der Rolle, nicht aus der Serienreihenfolge: Heizen = rot,
      // Warmwasser = blau, Kühlen = sky, identisch mit dem Live-Chart
      // (Regel 0a, „eine Datenrolle, eine Farbe").
      //
      // ⭐ Kühlen kam am 13.09.2026 dazu (N-439). Ohne die Zeile fiele ein
      // `_kuehlen`-Key in den Heizen-Zweig und die Kühlfläche stünde **rot**
      // neben dem Heizen-Segment. `modusKuehlen` ist die Rollenfarbe des
      // Kühl-STROMS (= `ROLLEN_BG.kuehlung`); die gemessene Kälte-MENGE trägt
      // dagegen `kaelteGemessen` (teal, N-437) — zwei Größen, zwei Töne.
      wpSerien.forEach((ws) => r.push({
        dataKey: ws.key,
        label: ws.label,
        farbe: ws.key.endsWith('_warmwasser')
          ? CHART_COLORS.wpWarmwasser
          : ws.key.endsWith('_kuehlen')
            ? CHART_COLORS.modusKuehlen
            : CHART_COLORS.wpWaerme,
        stackId: 'senken',
      }))
      // ⚠ **Nicht `KATEGORIE_FARBEN.waermepumpe`** — gemessen 12.09.2026 trägt die
      // Kategorie-Farbe der Wärmepumpe denselben Hexwert wie
      // `CHART_COLORS.wpWaerme` (Heizen, red-500), stünde also BITGLEICH neben
      // dem Heizen-Segment im selben Stapel; zwei Legendenzeilen, eine Farbe.
      // Die Rolle „Anteil, der keiner Funktion zugeordnet ist" hat bereits eine
      // Farbe (`modusNichtAufgeteilt`, = `ROLLEN_BG.nicht_aufgeteilt`), und die
      // gilt hier (Regel 0a Stufe 1: SoT existiert ⇒ anwenden).
      if (zeigeWpRest) r.push({
        dataKey: 'wp_rest', label: 'W\u00e4rmepumpe (\u00fcbrige)',
        farbe: CHART_COLORS.modusNichtAufgeteilt, stackId: 'senken',
      })
    } else {
      r.push({ dataKey: 'wp', label: 'W\u00e4rmepumpe', farbe: KATEGORIE_FARBEN.waermepumpe, stackId: 'senken' })
    }
  }
  if (senkenErfasst.has('wallbox_kw'))
    r.push({ dataKey: 'wb', label: 'Wallbox', farbe: KATEGORIE_FARBEN.wallbox, stackId: 'senken' })
  extraVerbraucher.forEach((es, i) =>
    r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_SERIEN_FARBEN[(extraErzeuger.length + i) % EXTRA_SERIEN_FARBEN.length], stackId: 'senken' }))
  return r
}

/**
 * Wird die WP-Fläche dieses Tages nach Funktion aufgeschlüsselt? — die **eine**
 * Bedingung, damit Serienliste und Punktbauer nicht auseinanderlaufen können.
 *
 * ⚠ Sie hängt AN der erfassten Senke (N-424): ohne `waermepumpe_kw` gibt es gar
 * keine WP-Fläche und damit auch keine, die man aufteilen könnte — die
 * JayJayX-Regel (#309) bleibt die äußere. Ab {@link WP_SPLIT_MIN_SERIEN}
 * Funktions-Serien, weil eine einzelne die WP-Reihe unter anderem Namen wäre.
 */
export function wpIstAufgeschluesselt(senkenErfasst: Set<SenkenKey>, wpSerien: SerieInfo[]): boolean {
  return senkenErfasst.has('waermepumpe_kw') && wpSerien.length >= WP_SPLIT_MIN_SERIEN
}

/** Trägt der Tag einen ungedeckten WP-Rest über der Schwelle? Rein, damit die
 *  Schwelle prüfbar ist — sonst stünde eine Legendenzeile für 0,01 kW da. */
export function zeigtWpRest(daten: StundenWert[], wpKeys: string[]): boolean {
  return daten.some((s) => wpRestKw(s.waermepumpe_kw, s.komponenten, wpKeys) > PV_REST_SCHWELLE_KW)
}

/**
 * Die 24 Chart-Punkte des Butterfly-Charts — **rein**, aus demselben Grund wie
 * {@link baueChartSerien}: Recharts zeichnet in jsdom nichts, eine Probe am
 * gerenderten Chart wäre grün, ohne je etwas gemessen zu haben. Ausgelagert am
 * 12.09.2026 (WK-09 B1), damit die K1-Wache prüfbar wird — *Σ der Senkenflächen
 * einer Stunde bleibt beim Aufschlüsseln bitgleich*.
 */
/**
 * Tooltip-Überschrift einer Stunde — Zählerlücken wie HA (R2, Vorlage §2
 * „Tagesverlauf-Chart"). Trägt der Balken die Energie mehrerer realer Stunden
 * (HA hatte die Stunden davor nicht geschrieben), sagt die Überschrift das.
 */
export function stundenTooltipLabel(
  label: unknown, chartDaten: ReadonlyArray<Record<string, number | string>>,
): string {
  const text = String(label ?? '')
  const punkt = chartDaten.find((p) => p.stunde === text)
  const n = typeof punkt?.spanne === 'number' ? punkt.spanne : 1
  return n > 1 ? `${text} · enthält ${n} Stunden (Lücke in Home Assistant)` : text
}

export function baueChartDaten({
  daten, extraErzeuger, extraVerbraucher, erzeugerSerien, pvAufgeschluesselt, zeigePvRest,
  wpSerien = [], wpAufgeschluesselt = false, zeigeWpRest = false,
}: {
  daten: StundenWert[]
  extraErzeuger: SerieInfo[]
  extraVerbraucher: SerieInfo[]
  erzeugerSerien: SerieInfo[]
  pvAufgeschluesselt: boolean
  zeigePvRest: boolean
  wpSerien?: SerieInfo[]
  wpAufgeschluesselt?: boolean
  zeigeWpRest?: boolean
}): Record<string, number | string>[] {
  const erzeugerKeys = erzeugerSerien.map((es) => es.key)
  const wpKeys = wpSerien.map((ws) => ws.key)
  return Array.from({ length: 24 }, (_, h) => {
    const s   = daten.find(d => d.stunde === h)
    const bat = s?.batterie_kw ?? 0
    const ntz = (s?.netzbezug_kw ?? 0) - (s?.einspeisung_kw ?? 0)
    const vbrSons = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s?.komponenten?.[es.key] ?? 0)), 0)
    const erzSons = extraErzeuger.reduce((a, es) => a + Math.max(0, s?.komponenten?.[es.key] ?? 0), 0)
    // `hausverbrauch` ist dieselbe Differenz wie in der Stundenwerte-Tabelle,
    // hier aber bewusst **ohne** die Unterdrückungs-Regel aus §3 des Konzepts
    // (`berechneHausverbrauch`): `Math.max(0, …)` klemmt den Ausdruck bei
    // fehlendem `verbrauch_kw` algebraisch auf 0 (alle Subtrahenden ≥ 0), der
    // Tooltip blendet Werte < 0,001 ohnehin aus — es entsteht also **keine**
    // falsche Zahl, nur ein Strich auf der Nulllinie. Ein `null` an dieser
    // Stelle ginge in eine **gestapelte** Fläche; dafür gibt es im Baum keine
    // Präzedenz und jsdom kann es nicht nachweisen. Wer die Serie anfasst,
    // zieht die Regel mit — s. `TagWerteTabelle.berechneHausverbrauch`.
    // Zählerlücken wie HA (R2): trägt die Zeile mehr als eine reale Stunde,
    // merkt sich der Punkt die Spanne, und der Tooltip beschriftet den Balken
    // (`stundenTooltipLabel`) — sonst läse man die Energie einer Lücke als
    // Spitze. Die Achse bleibt `h:00`. `?? 0` bleibt (eine fehlende Stunde ist
    // im Stapel eine Nulllinie).
    const punkt: Record<string, number | string> = {
      stunde:       `${h}:00`,
      spanne:       spanneDerZeile(s),
      pv:           s?.pv_kw ?? 0,
      bat_pos:      Math.max(0, bat),
      bat_neg:      Math.min(0, bat),
      netz_pos:     Math.max(0, ntz),
      netz_neg:     Math.min(0, ntz),
      hausverbrauch: -Math.max(0, (s?.verbrauch_kw ?? 0) - (s?.waermepumpe_kw ?? 0) - (s?.wallbox_kw ?? 0) - vbrSons),
      wb:           -(s?.wallbox_kw ?? 0),
      gesamterzeugung: round2((s?.pv_kw ?? 0) + Math.max(0, bat) + erzSons),
    }
    // ⭐ **K1: die Aufschlüsselung ersetzt die WP-Fläche, sie liegt nicht darauf.**
    // `hausverbrauch` oben bleibt **unverändert** auf `waermepumpe_kw` — es ist
    // dieselbe Menge, und eine zweite Subtraktionsformel wäre die F-56-Klasse.
    //
    // ⛔ **Und die Höhe hält in BEIDE Richtungen** (N-449): `wpSplitKw` deckelt
    // die Funktions-Flächen auf den Zähler, wo Σ Split größer ist (Zähler =
    // Menge, Leistungspfad = Form), `wpRestKw` füllt auf, wo er kleiner ist.
    // Σ Funktionsflächen + Rest ist damit exakt `waermepumpe_kw`.
    if (wpAufgeschluesselt) {
      const wpWerte = wpSplitKw(s?.waermepumpe_kw, s?.komponenten, wpKeys)
      for (const key of wpKeys) punkt[key] = wpWerte[key]
      if (zeigeWpRest) punkt.wp_rest = -round2(wpRestKw(s?.waermepumpe_kw, s?.komponenten, wpKeys))
    } else {
      punkt.wp = -(s?.waermepumpe_kw ?? 0)
    }
    for (const es of extraErzeuger)    punkt[es.key] = Math.max(0, s?.komponenten?.[es.key] ?? 0)
    for (const es of extraVerbraucher) punkt[es.key] = Math.min(0, s?.komponenten?.[es.key] ?? 0)
    if (pvAufgeschluesselt) {
      // `gesamterzeugung` oben bleibt auf `pv_kw` — die Aufschlüsselung ändert
      // die Darstellung, nicht die Bilanz.
      //
      // ⛔ **Und die Höhe hält in BEIDE Richtungen** (N-455, dieselbe Regel wie
      // acht Zeilen höher für die Senkenseite): `pvSplitKw` deckelt die
      // String-Flächen auf `pv_kw`, wo ihre Summe größer ist (Zähler = Menge,
      // Leistungspfad = Form), `pvRestKw` füllt auf, wo sie kleiner ist.
      // Σ Stringflächen + Rest ist damit exakt `pv_kw` — vorher konnte der
      // Quellen-Stapel über die PV-Gesamtlinie hinauswachsen.
      const pvWerte = pvSplitKw(s?.pv_kw, s?.komponenten, erzeugerKeys)
      for (const es of erzeugerSerien) punkt[es.key] = pvWerte[es.key]
      if (zeigePvRest) punkt.pv_rest = round2(pvRestKw(s?.pv_kw, s?.komponenten, erzeugerKeys))
    }
    return punkt
  })
}

/** N-566: Default der optionalen Serien-Props — EINE Referenz für alle Renders. Ein `= []` im
 *  Parameter wäre je Render neu und liefe über `pvRest`/`chartSerien`/`chartDaten` in die
 *  Memo-Abhängigkeiten (jeder Render rechnete den Chart neu). Dieselbe Bauform wie
 *  `TagWerteTabelle`, dort mit Effekt und Endlosschleife. */
const KEINE_SERIEN: SerieInfo[] = []

export function TagVerlaufChart({ daten, extraSerien, erzeugerSerien = KEINE_SERIEN, wpSerien = KEINE_SERIEN }: {
  daten: StundenWert[]
  extraSerien: SerieInfo[]
  /** PV-Strings/BKW mit eigenem Sensor (#350, Rainer). Sie **ersetzen** den
   *  PV-Stapel durch seine Bestandteile, statt zusätzlich obendrauf zu liegen —
   *  als Extra-Serie wäre dieselbe Erzeugung zweimal im Stapel (`extraErzeuger`
   *  addiert sich zu `pv`). Was die Strings nicht abdecken, bleibt als
   *  „PV (übrige)" stehen; die Stapelhöhe ist damit unverändert die Erzeugung. */
  erzeugerSerien?: SerieInfo[]
  /** Wärmepumpen-Serien je Funktion (`…_heizen`/`…_warmwasser`, WK-09 B1).
   *  Dieselbe Bauform auf der Senkenseite: sie **ersetzen** die `wp`-Fläche,
   *  der Rest heißt „Wärmepumpe (übrige)". Sie entstehen im Leistungspfad nur,
   *  wenn KEINE „Leistung gesamt" zugeordnet ist
   *  (`live_sensor_config.py::baue_investitions_serien`). */
  wpSerien?: SerieInfo[]
}) {
  const achsen = useChartTheme()
  // B7-Legenden-Toggle; Paar-Mapping: bidirektionale _pos/_neg-Serien (Batterie/Netz)
  // schalten gemeinsam über ihren Basis-Key (Legende zeigt nur den _pos-Eintrag).
  const { istVersteckt, toggleSerie } = useLegendenToggle()
  const basisKey = (k: string) => k.replace(/_(pos|neg)$/, '')
  const extraErzeuger    = useMemo(() => extraSerien.filter(s => s.seite === 'quelle'), [extraSerien])
  const extraVerbraucher = useMemo(() => extraSerien.filter(s => s.seite === 'senke'), [extraSerien])
  // Welche der beiden **dedizierten** Gerätesenken hat dieser Tag überhaupt?
  // Gemeldet von JayJayX (simon42 T89667 #309, 08.09.2026): „In Cockpit/Tag/
  // Stundenverlauf werden mir Wallbox und Wärmepumpe angezeigt und laufen
  // parallel zum Hausverbrauch" — er besitzt keins von beidem. Alle anderen
  // Serien kommen aus der Datenlage (`extraSerien` liefert das Backend nur für
  // Komponenten, die am Tag etwas beigetragen haben); `wp`/`wb` standen als
  // einzige unbedingt im Stapel. Der Live-Block macht es seit jeher richtig
  // (`WetterWidget::vorhandeneKategorien`) — hier fehlte dieselbe Frage.
  // `erfassteSenken` ist bewusst dieselbe Erhebung wie in der Stundenwerte-
  // Tabelle daneben: „kein Key heißt None, nicht 0" (`geraete_spalte_kw`), ein
  // Gerät ohne jede Spur am Tag ist damit von einer Messlücke unterscheidbar.
  const senkenErfasst = useMemo(
    () => erfassteSenken(daten, extraVerbraucher),
    [daten, extraVerbraucher],
  )

  // PV je String: nur aufschlüsseln, wenn es etwas zu trennen gibt (≥ 2 Serien);
  // bei einem Gerät wäre die Gerätereihe die PV-Reihe unter anderem Namen.
  const pvAufgeschluesselt = erzeugerSerien.length >= 2
  // Rest-Regel liegt in `lib/erzeugerSpalten` — dieselbe Fläche, ein Ort.
  const pvRest = useCallback(
    (s: StundenWert | undefined) => pvRestKw(s?.pv_kw, s?.komponenten, erzeugerSerien.map((es) => es.key)),
    [erzeugerSerien],
  )
  const zeigePvRest = useMemo(
    () => pvAufgeschluesselt && daten.some((s) => pvRest(s) > PV_REST_SCHWELLE_KW),
    [pvAufgeschluesselt, daten, pvRest],
  )

  // WP je Funktion: dieselbe Frage wie oben, eine Zeile tiefer im Stapel.
  // ⚠ Die Aufschlüsselung hängt AN der erfassten Senke (N-424): ohne
  // `waermepumpe_kw` gibt es gar keine WP-Fläche, und dann auch keine, die man
  // aufteilen könnte — die JayJayX-Regel (#309) bleibt die äußere.
  const wpAufgeschluesselt = wpIstAufgeschluesselt(senkenErfasst, wpSerien)
  const zeigeWpRest = useMemo(
    () => wpAufgeschluesselt && zeigtWpRest(daten, wpSerien.map((ws) => ws.key)),
    [wpAufgeschluesselt, daten, wpSerien],
  )

  // Chart-Serien analog Live-TagesverlaufChart: bidirektionale in _pos/_neg aufgespalten.
  const chartSerien = useMemo<ChartSerie[]>(
    () => baueChartSerien({
      pvAufgeschluesselt, zeigePvRest, erzeugerSerien,
      extraErzeuger, extraVerbraucher, senkenErfasst,
      wpAufgeschluesselt, zeigeWpRest, wpSerien,
    }),
    [extraErzeuger, extraVerbraucher, erzeugerSerien, pvAufgeschluesselt, zeigePvRest, senkenErfasst,
      wpAufgeschluesselt, zeigeWpRest, wpSerien],
  )

  const chartDaten = useMemo(
    () => baueChartDaten({
      daten, extraErzeuger, extraVerbraucher, erzeugerSerien, pvAufgeschluesselt, zeigePvRest,
      wpSerien, wpAufgeschluesselt, zeigeWpRest,
    }),
    [daten, extraErzeuger, extraVerbraucher, erzeugerSerien, pvAufgeschluesselt, zeigePvRest,
      wpSerien, wpAufgeschluesselt, zeigeWpRest],
  )

  return (
    // D18-3 (detlan #210): KEINE eigene <Card> mehr um den Chart — die
    // Gliederungsebene (BlockShell-Body px-3) trägt den Seitenrand, die
    // IST-Seite hüllt am Aufrufer. YAxis-Breite aus chartAchse (44, wie das
    // Vorbild KomponentenVerlaufChart) statt Recharts-Default 60.
    <div>
      <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between">
        <span>▲ Quellen (Erzeugung, Bezug)</span>
        <span>Stundenmittelwerte aus Energieprofil · gestrichelt = Verfügbare Energie</span>
        <span>▼ Senken (Verbrauch, Einspeisung)</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartDaten} margin={{ top: ACHSEN_MARGIN_TOP, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="stunde" {...xAchse()} interval={2} /* achsen-allow: Zeit-/Kategorie-Achse (Stunde) */ />
          <YAxis {...yAchse(false, 44)} tickFormatter={achsenTick} label={achsenEinheit('kW')} />
          <ReferenceLine y={0} stroke={achsen.referenz} strokeWidth={1.5} />
          <Tooltip {...eedcTooltipProps({
            unit: ' kW', decimals: 2,
            labelFormatter: (label) => stundenTooltipLabel(label, chartDaten),
            nameFormatter: (name) => chartSerien.find(cs => cs.dataKey === name)?.label ?? CHART_LABELS[name] ?? name,
            formatter: (v) => Math.abs(v) < 0.001 ? null : `${v > 0 ? '▲' : '▼'} ${fmtZahl(Math.abs(v), 2)} kW`,
          })} />
          <Legend content={<ChartLegende
            formatter={(value) => chartSerien.find(cs => cs.dataKey === value)?.label ?? value}
            onItemClick={(e) => toggleSerie(basisKey(String(e.dataKey ?? e.value)))}
          />} />

          {chartSerien.map(cs => (
            <Area
              key={cs.dataKey}
              type="monotone"
              dataKey={cs.dataKey}
              name={cs.dataKey}
              fill={cs.farbe}
              stroke={cs.farbe}
              fillOpacity={AREA_FILL_OPACITY}
              strokeWidth={1.5}
              stackId={cs.stackId}
              isAnimationActive={false}
              legendType={cs.hideLabel ? 'none' : undefined}
              hide={istVersteckt(basisKey(cs.dataKey))}
            />
          ))}

          {/* Summen-/Hilfslinie (keine Prognose) → HILFSLINIE_DASH, nicht PROGNOSE_DASH (Regel C).
              D17-1: neutrale Hilfslinien-Farbe (nicht COLORS.solar = PV-Rolle) — sonst wirkte
              „Gesamterzeugung" im Tooltip wie eine Farb-/Wert-Dublette der PV-Zeile. Label
              „Gesamterzeugung" (groß) kommt aus CHART_LABELS (nameFormatter-Fallback oben). */}
          <Line dataKey="gesamterzeugung" name="gesamterzeugung"
            stroke={achsen.referenz} strokeWidth={2} strokeDasharray={HILFSLINIE_DASH}
            dot={false} connectNulls legendType="none" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
