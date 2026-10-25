/**
 * waermeVerlauf — die Serien des Wärme/Klima-Verlaufs, als reine Funktion.
 *
 * Getrennt von der Zeichnung, damit sie ohne Rendering prüfbar ist: Recharts
 * zeichnet in jsdom nichts, eine Probe am gerenderten Chart wäre grün ohne zu
 * messen (Befund aus Sitzung 193, N-424).
 *
 * Die Eingabe ist period-agnostisch — Jahr liefert Monate, Monat liefert Tage,
 * Tag liefert Stunden. Es gibt nur eine Regel-Sammlung, nicht drei.
 */
import { CHART_COLORS } from '../lib'
import { funktionsFarbe } from '../lib/funktionsFarben'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { WaermeVerlaufTag } from '../api/energie_profil'
import type { VerlaufStapel, VerlaufLinie, WaermeVerlaufRow } from './WaermeVerlaufChart'

/** Eine Periode (Monat/Tag/Stunde) mit den Größen, die der Verlauf braucht. */
export interface WaermeVerlaufPunkt {
  /** Beschriftung auf der x-Achse (Monatskürzel, Tagesnummer, Stunde). */
  name: string
  wp_strom_kwh?: number | null
  wp_waerme_kwh?: number | null
  wp_waerme_abgeleitet_kwh?: number | null
  /** Bauschnitt 6b: gemessene **Kälte** — eigene Linie, nie in der Wärme. */
  wp_kaelte_kwh?: number | null
  wp_modus_strom_heizen_kwh?: number | null
  wp_modus_strom_warmwasser_kwh?: number | null
  wp_modus_strom_kuehlen_kwh?: number | null
  wp_modus_strom_lueften_kwh?: number | null
  wp_modus_strom_entfeuchten_kwh?: number | null
  wp_modus_nicht_aufgeteilt_kwh?: number | null
  wp_modus_gemessen?: boolean | null
  wp_modus_abdeckung_h?: number | null
  wp_modus_strom_bezug_kwh?: number | null
  /** WK-09 B2 — die **Summanden** aus den Funktions-Zählern (SOLL §3.3/S2a).
   *  `null`/fehlend heißt „nicht erfasst": dann gibt es die Sicht nicht. */
  wp_funktion_strom_heizen_kwh?: number | null
  wp_funktion_strom_warmwasser_kwh?: number | null
  wp_funktion_uebrige_kwh?: number | null
  /** P-433-3 S3 — die **Wärme** derselben Stunde nach Funktion (Summanden-Zähler, Rest «nicht je Funktion
   *  gemessen»; Σ = `wp_waerme_kwh`). `null`/fehlend: dann bleibt die Wärme die Linie. Nur der Tag trägt sie. */
  wp_waerme_heizen_kwh?: number | null
  wp_waerme_warmwasser_kwh?: number | null
  wp_waerme_uebrige_kwh?: number | null
  /** Monatsmittel der Außentemperatur (°C) — zweite Achse, per Legende
   *  ausblendbar. Fehlt sie, fehlt auch die Linie: Ein kalter Monat ohne
   *  Messreihe ist kein 0-°C-Monat. */
  temperatur_c?: number | null
}

export interface WaermeVerlaufDaten {
  rows: WaermeVerlaufRow[]
  stapel: VerlaufStapel[]
  linien: VerlaufLinie[]
  /** Σ der aufgeteilten Strommenge über alle Perioden (Grundmenge des Stapels). */
  bezugKwh: number
  /** Σ des gesamten Wärmepumpen-Stroms über alle Perioden. */
  stromKwh: number
  /** Hat die **aktive** Sicht überhaupt einen Stapel? */
  hatStapel: boolean
  /** Welche Familie liegt gerade im Balken? Genau eine — nie beide (S2a). */
  sicht: VerlaufSicht
  /** Gibt es die Sicht „nach Funktion" an diesen Daten überhaupt? Sie ist die
   *  Bedingung für den Umschalter, unabhängig davon, was gerade gezeigt wird. */
  hatFunktionsStapel: boolean
  /** Gibt es mindestens eine Periode mit GEMESSENER Wärme? */
  hatGemesseneWaerme: boolean
  /** P-433-3 S3: liegt die Wärme gerade als **Stapel** nach Funktion im Bild (nur Sicht „nach Funktion")? Dann
   *  entfällt die Wärme-Linie — dieselbe Menge zweimal wäre eine Doppelaussage. */
  waermeGestapelt: boolean
  /** Gibt es mindestens eine Periode mit gemessener Kälte? (Bauschnitt 6b) */
  hatGemesseneKaelte: boolean
  /** Gibt es überhaupt Außentemperatur-Werte? */
  hatTemperatur: boolean
}

/** Was sich im Tag keiner Stunde zuordnen ließ — je Größe (N-437, E6 (a)).
 *  Nicht gleichmäßig verteilt, sondern genannt (P4). */
export interface VerlaufRest {
  strom?: number | null
  waerme?: number | null
  kaelte?: number | null
  /** WK-09 B2: dasselbe für die Funktions-Zähler (P4). */
  funktion?: number | null
}

const z = (v: number | null | undefined): number => (v == null ? 0 : v)
const eineStelle = (v: number): number => Math.round(v * 10) / 10

/**
 * ⚠ **Dieselbe Torbedingung wie beim Aufteilungs-Balken** (`hat_modus_split`,
 * `monats_fakten.py`): ohne erfasste Stunde und ohne Betriebsart-Zähler gibt es
 * keine Aufteilung — statt einer Reihe von Nullen. Der Balken über dem Verlauf
 * erscheint in derselben Lage ebenfalls nicht; zwei verschiedene Antworten auf
 * dieselbe Datenlage wären der teurere Fehler.
 */
const hatSplit = (p: WaermeVerlaufPunkt): boolean =>
  !!p.wp_modus_gemessen || z(p.wp_modus_abdeckung_h) > 0

/** Welche **Familie** der Balken gerade stapelt (SOLL §3.3/S2a). */
export type VerlaufSicht = 'betriebsart' | 'funktion'

interface Segment { key: string; feld: keyof WaermeVerlaufPunkt; label: string; farbe: string; immer?: boolean }

/** Die sechs Segmente in der Reihenfolge des Aufteilungs-Balkens — **Teilmengen**
 *  des Stroms je Betriebsart, der Rest heißt *nicht aufgeteilt* (SOLL §3.2). */
const SEGMENTE: Segment[] = [
  { key: 'heizen', feld: 'wp_modus_strom_heizen_kwh', label: 'Heizen', farbe: CHART_COLORS.wpWaerme, immer: true },
  { key: 'warmwasser', feld: 'wp_modus_strom_warmwasser_kwh', label: 'Warmwasser', farbe: CHART_COLORS.wpWarmwasser },
  { key: 'kuehlen', feld: 'wp_modus_strom_kuehlen_kwh', label: 'Kühlen', farbe: CHART_COLORS.modusKuehlen, immer: true },
  { key: 'lueften', feld: 'wp_modus_strom_lueften_kwh', label: 'Lüften', farbe: CHART_COLORS.modusLueften },
  { key: 'entfeuchten', feld: 'wp_modus_strom_entfeuchten_kwh', label: 'Entfeuchten', farbe: CHART_COLORS.modusEntfeuchten },
  { key: 'rest', feld: 'wp_modus_nicht_aufgeteilt_kwh', label: 'Nicht aufgeteilt', farbe: CHART_COLORS.modusNichtAufgeteilt, immer: true },
]

/**
 * Die drei Segmente der Funktions-Sicht — **Summanden**: Heizen + Warmwasser +
 * Übriger Strom = Gesamtstrom (K1). Eigene `key`s, damit die beiden Familien
 * auch versehentlich nie in denselben Balken geraten können; die Farben sind
 * dieselben Rollen wie oben (Regel 0a: eine Datenrolle, eine Farbe).
 *
 * ⚠ Heizen und Warmwasser erscheinen nur mit Menge (E4, Konzept §2.3 *„Wer sie
 * nicht erfasst, sieht sie nicht"*) — eine Brauchwasser-Wärmepumpe hat keine
 * Heizachse. Der Rest steht **immer**: dass nichts übrig bleibt, ist eine
 * Aussage, keine Leerstelle.
 */
const FUNKTIONS_SEGMENTE: Segment[] = [
  { key: 'f_heizen', feld: 'wp_funktion_strom_heizen_kwh', label: 'Heizen', farbe: CHART_COLORS.wpWaerme },
  { key: 'f_warmwasser', feld: 'wp_funktion_strom_warmwasser_kwh', label: 'Warmwasser', farbe: CHART_COLORS.wpWarmwasser },
  { key: 'f_uebrige', feld: 'wp_funktion_uebrige_kwh', label: 'Übriger Strom', farbe: CHART_COLORS.modusNichtAufgeteilt, immer: true },
]

/** Trägt diese Periode überhaupt Funktions-Zähler? Das Backend setzt die drei
 *  Felder genau dann, wenn `funktions_stapel_verfuegbar` gilt — eine zweite
 *  Durchreichung des Flags wäre eine zweite Wahrheit über dieselbe Frage. */
const hatFunktion = (p: WaermeVerlaufPunkt): boolean =>
  p.wp_funktion_strom_heizen_kwh != null || p.wp_funktion_strom_warmwasser_kwh != null

/**
 * P-433-3 S3 (Bauplan S3-4/S3-6, E-P3-1/E-P3-10): die **Wärme** nach Funktion — Heizen und Warmwasser aus den
 * Summanden-Zählern, darüber der Rest **„Wärme nicht je Funktion gemessen"** (gemeinsamer Wärmemengenzähler, Geräte
 * ohne Aufteilung). Die Stapelhöhe ist die gemessene Wärme (`wp_waerme_kwh`) — das Backend bildet den Rest, der Client
 * stapelt nur. Eine eigene Gruppe (`waerme`): sie steht in der Sicht „nach Funktion" **neben** dem Strom-Stapel, nie
 * darauf (andere Größe). Farben aus `lib/funktionsFarben.ts`; der Rest im Ton von „nicht aufgeteilt".
 */
const WAERME_SEGMENTE: Segment[] = [
  { key: 'w_heizen', feld: 'wp_waerme_heizen_kwh', label: 'Wärme Heizen', farbe: funktionsFarbe('heizen') },
  { key: 'w_warmwasser', feld: 'wp_waerme_warmwasser_kwh', label: 'Wärme Warmwasser', farbe: funktionsFarbe('warmwasser') },
  { key: 'w_uebrige', feld: 'wp_waerme_uebrige_kwh', label: 'Wärme nicht je Funktion gemessen', farbe: funktionsFarbe('ohne_modus') },
]

/** Trägt diese Periode den Wärme-Stapel? Das Backend setzt die drei Felder genau dann (`waerme_funktions_stapel_verfuegbar`). */
const hatWaermeFunktion = (p: WaermeVerlaufPunkt): boolean =>
  p.wp_waerme_heizen_kwh != null || p.wp_waerme_warmwasser_kwh != null || p.wp_waerme_uebrige_kwh != null

/**
 * Baut Zeilen und Serien. Serien erscheinen nur, wenn sie etwas zu sagen haben:
 * Warmwasser/Lüften/Entfeuchten nur bei eigenem Zähler (E4, Konzept §2.3
 * *„Wer sie nicht erfasst, sieht sie nicht"*), die Wärmelinie nur mit
 * gemessener Wärme (E7), die Kältelinie nur mit gemessener Kälte.
 */
export function baueWaermeVerlauf(
  punkte: WaermeVerlaufPunkt[], sicht: VerlaufSicht = 'betriebsart',
): WaermeVerlaufDaten {
  // ⭐ **S2a: ein Stapel, eine Familie.** Segmentliste und Tor hängen an der
  // gewählten Sicht — es gibt keinen Zweig, in dem beide Familien zusammen in
  // `stapel` landen könnten. Das ist die Wache gegen den Fehler aus SOLL §3.2
  // („wer sie verwechselt, addiert Teilmengen zu Summanden"), und sie steht
  // hier in der reinen Funktion statt in der Zeichnung.
  const hatFunktionsStapel = punkte.some(hatFunktion)
  const aktiv: VerlaufSicht = sicht === 'funktion' && hatFunktionsStapel ? 'funktion' : 'betriebsart'
  const istFunktion = aktiv === 'funktion'
  const tor = istFunktion ? hatFunktion : hatSplit
  const segmente = istFunktion ? FUNKTIONS_SEGMENTE : SEGMENTE

  const mitSplit = punkte.filter(tor)
  const hatStapel = mitSplit.length > 0

  const aktiveSegmente = segmente.filter(
    (s) => s.immer || mitSplit.some((p) => z(p[s.feld] as number | null | undefined) > 0),
  )

  // E7 (Konzept §8, SOLL §3.3): NUR gemessene Wärme. Der abgeleitete Anteil
  // ist `Strom × Arbeitszahl` — eine Linie daraus hätte exakt die Form der
  // Stromfläche darunter und sagte nichts.
  //
  // ⚠ Hier zählt die MENGE, nicht das Flag `wp_waerme_abgeleitet`. Das Flag
  // heißt „irgendein Teil irgendeines Geräts" und ist für die Kennzahl richtig
  // so; bei einer Wärmepumpe mit Wärmemengenzähler NEBEN einer Klimaanlage
  // ohne einen solchen wäre es gesetzt, obwohl fast die ganze Wärme gemessen
  // ist. Wer danach ausblendet, verliert Gemessenes.
  const gemesseneWaerme = (p: WaermeVerlaufPunkt): number | null => {
    if (p.wp_waerme_kwh == null) return null
    const rest = p.wp_waerme_kwh - z(p.wp_waerme_abgeleitet_kwh)
    return rest > 0 ? eineStelle(rest) : null
  }
  // Bauschnitt 6b: Kälte ist immer gemessen (es gibt keinen Weg, sie
  // abzuleiten) — dieselbe Lückenregel wie bei der Wärme: ≤ 0 ist keine
  // Aussage, sondern eine Lücke in der Linie.
  const gemesseneKaelte = (p: WaermeVerlaufPunkt): number | null =>
    z(p.wp_kaelte_kwh) > 0 ? eineStelle(z(p.wp_kaelte_kwh)) : null
  const hatGemesseneWaerme = punkte.some((p) => gemesseneWaerme(p) != null)
  const hatGemesseneKaelte = punkte.some((p) => gemesseneKaelte(p) != null)
  const hatTemperatur = punkte.some((p) => p.temperatur_c != null)
  // P-433-3 S3: Wärme als Stapel nur in der Sicht „nach Funktion" — sonst die Linie wie bisher.
  const waermeGestapelt = istFunktion && hatGemesseneWaerme && punkte.some(hatWaermeFunktion)
  const waermeSegmente = waermeGestapelt
    ? WAERME_SEGMENTE.filter((s) => s.key === 'w_uebrige' || punkte.some((p) => z(p[s.feld] as number | null | undefined) > 0))
    : []

  const rows: WaermeVerlaufRow[] = punkte.map((p) => {
    const row: WaermeVerlaufRow = { name: p.name }
    const split = tor(p)
    for (const s of aktiveSegmente) {
      // Eine Periode ohne Aufteilung trägt `null`, nicht `0` — sonst stünde
      // dort ein Balken der Höhe 0, der aussieht wie „nichts gelaufen",
      // während die Kachel Strom zeigt.
      row[s.key] = split ? eineStelle(z(p[s.feld] as number | null | undefined)) : null
    }
    if (hatGemesseneWaerme && !waermeGestapelt) row.waerme = gemesseneWaerme(p)
    for (const s of waermeSegmente) {
      row[s.key] = hatWaermeFunktion(p) ? eineStelle(z(p[s.feld] as number | null | undefined)) : null
    }
    if (hatGemesseneKaelte) row.kaelte = gemesseneKaelte(p)
    // ⚠ `null` statt 0, wo kein Wert vorliegt — sonst zöge die Linie den
    // Monat auf den Gefrierpunkt.
    if (hatTemperatur) row.temperatur = p.temperatur_c ?? null
    return row
  })

  const stapel: VerlaufStapel[] = [
    ...(hatStapel ? aktiveSegmente.map((s) => ({ key: s.key, label: s.label, farbe: s.farbe })) : []),
    ...waermeSegmente.map((s) => ({ key: s.key, label: s.label, farbe: s.farbe, gruppe: 'waerme' })),
  ]
  const linien: VerlaufLinie[] = [
    ...(hatGemesseneWaerme && !waermeGestapelt
      ? [{ key: 'waerme', label: 'Wärme (gemessen)', farbe: CHART_COLORS.waermeGemessen, dezimalen: 1 }]
      : []),
    // Bauschnitt 6b: eigene Linie, eigene Farbe (Konzept §8) — NIE mit der
    // Wärme zusammengelegt, und nicht im Ton des Kühlen-Segments darunter.
    ...(hatGemesseneKaelte
      ? [{ key: 'kaelte', label: 'Kälte (gemessen)', farbe: CHART_COLORS.kaelteGemessen, dezimalen: 1 }]
      : []),
    // Zweite Achse: °C gehört nicht auf die kWh-Skala. Per Legenden-Klick
    // ausblendbar wie jede andere Reihe.
    ...(hatTemperatur
      ? [{
          key: 'temperatur', label: 'Außentemperatur',
          farbe: CHART_COLORS.temperatur, achse: 'rechts' as const, dezimalen: 1,
        }]
      : []),
  ]

  return {
    rows, stapel, linien,
    // W-17b: die Grundmenge des Stapels. Sie ist NICHT `wp_strom_kwh` —
    // `modus_strom_bezug_kwh` zählt nur die Geräte mit Aufteilung
    // (`monats_fakten.py`: *„Auf Anlagenebene ist `strom_kwh` der falsche
    // Bezug"*). Der Aufrufer nennt die Differenz, wie der Balken es tut.
    bezugKwh: mitSplit.reduce((a, p) => a + z(p.wp_modus_strom_bezug_kwh), 0),
    stromKwh: punkte.reduce((a, p) => a + z(p.wp_strom_kwh), 0),
    hatStapel,
    sicht: aktiv,
    hatFunktionsStapel,
    hatGemesseneWaerme,
    waermeGestapelt,
    hatGemesseneKaelte,
    hatTemperatur,
  }
}

/** Unterhalb dieser Menge ist ein Rest eine Rundungsfrage, keine Aussage. */
const REST_SCHWELLE_KWH = 0.05

/**
 * Die Rest-Zeilen unter dem Verlauf — **je Größe beschriftet** (N-437, E6 (a)).
 * Drei gleich beschriftete kWh-Zeilen untereinander wären drei Aussagen, die
 * niemand auseinanderhalten kann (W-8: die Beschriftung nennt die Größe).
 */
export function verlaufRestZeilen(rest?: VerlaufRest | null): { label: string; kwh: number }[] {
  if (!rest) return []
  return ([
    ['Strom ohne Stundenzuordnung', rest.strom],
    ['Wärme ohne Stundenzuordnung', rest.waerme],
    ['Kälte ohne Stundenzuordnung', rest.kaelte],
    ['Strom je Funktion ohne Stundenzuordnung', rest.funktion],
  ] as const)
    .filter(([, kwh]) => kwh != null && kwh > REST_SCHWELLE_KWH)
    .map(([label, kwh]) => ({ label, kwh: kwh as number }))
}

/** Erscheint das Verlauf-Element? Auch dann, wenn NUR ein Rest da ist — sonst
 *  bliebe genau der Fall unsichtbar, in dem nichts einer Stunde zuzuordnen war
 *  (S3: was die Sicht nicht zeigen kann, sagt sie). */
export function zeigtVerlauf(v: WaermeVerlaufDaten | null, rest?: VerlaufRest | null): boolean {
  if (!v) return false
  // ⚠ `hatFunktionsStapel` gehört dazu, seit es zwei Sichten gibt (S2a): Eine
  // Wärmepumpe der Sprosse **F5** (getrennte Funktions-Zähler, kein
  // Betriebsart-Zähler, kein Modus-Signal) hat in der Betriebsart-Sicht nichts
  // zu zeigen — ohne diese Bedingung bliebe genau der Fall unsichtbar, für den
  // die zweite Sicht gebaut wurde.
  return v.hatStapel || v.hatFunktionsStapel || v.hatGemesseneWaerme
    || v.hatGemesseneKaelte || verlaufRestZeilen(rest).length > 0
}

/** W-8 — der Titel nennt, was wirklich drinsteht. Die Temperatur ist Kontext,
 *  keine Größe der Anlage; sie steht nicht im Titel. */
export function verlaufTitel(v: WaermeVerlaufDaten): string {
  const gemessen = v.hatGemesseneWaerme && v.hatGemesseneKaelte
    ? 'gemessene Wärme und Kälte'
    : v.hatGemesseneWaerme ? 'gemessene Wärme'
      : v.hatGemesseneKaelte ? 'gemessene Kälte' : null
  // S2a: der Titel nennt die **Familie**, die gerade gestapelt ist — sonst
  // trügen zwei verschiedene Größen unbeschriftet denselben Platz.
  const stapel = v.sicht === 'funktion'
    ? (v.waermeGestapelt ? 'Strom und Wärme nach Funktion' : 'Strom nach Funktion')
    : 'Strom nach Betriebsart'
  // P-433-3 S3: die gestapelte Wärme steht schon im Stapel-Teil des Titels.
  if (v.waermeGestapelt && v.hatStapel) {
    return v.hatGemesseneKaelte ? `Verlauf · ${stapel} und gemessene Kälte` : `Verlauf · ${stapel}`
  }
  if (v.hatStapel && gemessen) {
    return `Verlauf · ${stapel}${gemessen.includes(' und ') ? ', ' : ' und '}${gemessen}`
  }
  if (v.hatStapel) return `Verlauf · ${stapel}`
  return gemessen ? `Verlauf · ${gemessen}` : 'Verlauf'
}

/**
 * Jahr: die Monatsantworten → Punkte (x = Monate). Als reine Funktion, damit
 * eine vergessene Durchreichung rot wird — im `useMemo` der Seite war sie
 * unsichtbar (die N-348-Klasse).
 */
export function punkteAusMonatsantworten(
  antworten: AktuellerMonatResponse[],
  tempJeMonat: Map<number, number | null>,
  monatsName: (monat: number) => string,
): WaermeVerlaufPunkt[] {
  return [...antworten]
    .sort((a, b) => a.monat - b.monat)
    .map((m) => ({
      name: monatsName(m.monat),
      temperatur_c: tempJeMonat.get(m.monat) ?? null,
      wp_strom_kwh: m.wp_strom_kwh,
      wp_waerme_kwh: m.wp_waerme_kwh,
      wp_waerme_abgeleitet_kwh: m.wp_waerme_abgeleitet_kwh,
      wp_kaelte_kwh: m.wp_kaelte_kwh,
      wp_modus_strom_heizen_kwh: m.wp_modus_strom_heizen_kwh,
      wp_modus_strom_warmwasser_kwh: m.wp_modus_strom_warmwasser_kwh,
      wp_modus_strom_kuehlen_kwh: m.wp_modus_strom_kuehlen_kwh,
      wp_modus_strom_lueften_kwh: m.wp_modus_strom_lueften_kwh,
      wp_modus_strom_entfeuchten_kwh: m.wp_modus_strom_entfeuchten_kwh,
      wp_modus_nicht_aufgeteilt_kwh: m.wp_modus_nicht_aufgeteilt_kwh,
      wp_modus_gemessen: m.wp_modus_gemessen,
      wp_modus_abdeckung_h: m.wp_modus_abdeckung_h,
      wp_modus_strom_bezug_kwh: m.wp_modus_strom_bezug_kwh,
      // ⚠ Monat und Jahr tragen KEINE Funktions-Stundenform — S2a gilt „je
      // Stunde". Die Sicht „nach Funktion" gibt es dort deshalb nicht.
    }))
}

/** Monat: die Tageszeilen aus `/waerme-verlauf` → Punkte (x = Tagesnummer). */
export function punkteAusVerlaufsTagen(tage: WaermeVerlaufTag[]): WaermeVerlaufPunkt[] {
  return tage.map((t) => ({
    // Die x-Achse trägt die Tagesnummer — der Monat steht in der Sicht.
    name: String(Number(t.datum.slice(8, 10))),
    temperatur_c: t.temperatur_c,
    wp_strom_kwh: t.wp_strom_kwh,
    wp_waerme_kwh: t.wp_waerme_kwh,
    // ⚠ Auf Tagesebene gibt es keine abgeleitete Wärme — sie entsteht an den
    // Monatszeilen. Was hier steht, ist gemessen (SOLL §3.3/S4).
    wp_waerme_abgeleitet_kwh: null,
    wp_kaelte_kwh: t.wp_kaelte_kwh ?? null,
    wp_modus_strom_heizen_kwh: t.wp_modus_strom_heizen_kwh,
    wp_modus_strom_warmwasser_kwh: t.wp_modus_strom_warmwasser_kwh,
    wp_modus_strom_kuehlen_kwh: t.wp_modus_strom_kuehlen_kwh,
    wp_modus_strom_lueften_kwh: t.wp_modus_strom_lueften_kwh,
    wp_modus_strom_entfeuchten_kwh: t.wp_modus_strom_entfeuchten_kwh,
    wp_modus_nicht_aufgeteilt_kwh: t.wp_modus_nicht_aufgeteilt_kwh,
    wp_modus_gemessen: t.wp_modus_gemessen,
    wp_modus_abdeckung_h: t.wp_modus_abdeckung_h,
    wp_modus_strom_bezug_kwh: t.wp_modus_strom_bezug_kwh,
  }))
}
