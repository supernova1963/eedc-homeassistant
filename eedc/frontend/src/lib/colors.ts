/**
 * Zentrale Farbdefinitionen — DIE Farb-SoT des Frontends.
 * (Style-Guide A2 · Regel Nr. 0/0a · VORBEREITUNG-E1-FUNDAMENT §6/§7, entschieden 2026-06-12)
 *
 * Regeln:
 * - KEINE Inline-Hex-Farben in Komponenten/Seiten — jede Farbe kommt von hier.
 *   Wächter: `npm run check:design` (scripts/check-design-konformitaet.mjs).
 * - Neue Farb-Rolle nötig? HIER ergänzen (Regel 0a Stufe 2), nicht lokal hardcoden.
 *   Echte Einzelfall-Ausnahme nur mit Maintainer-Freigabe + Eintrag in der
 *   Ausnahmen-Liste des Wächter-Skripts.
 * - tailwind.config.js importiert dieses Modul (jiti) — Theme kann nicht driften.
 *
 * Entscheide (F1–F4, Gernot 2026-06-12):
 * - F1: Solar-Kanon = #f59e0b (vorher drei Gelbtöne: #f59e0b/#fbbf24/#eab308).
 * - F2: Netzbezug = Dunkelrot #b91c1c (vorher #ef4444); Signal-Rot #ef4444 ist
 *   exklusiv für Kosten/negativ/Fehler. Komponenten-Identität WP bleibt #ef4444
 *   (TYP_COLORS — bewusste, dokumentierte Ko-Existenz).
 * - F3: Status-Achse ok/warnung/kritisch/info (= bisherige Ampel-Schwellen).
 * - F4: #10b981 = Einspeisung/Erlös (Emerald). Speicher-Ladung war früher
 *   #22c55e (Green), las sich aber im selben Stapel zu nah am Einspeisung-
 *   Emerald (IA-V4 #243, Gernot) → jetzt Orange #f97316 (klar abgesetzt, nicht-
 *   grün). #22c55e bleibt für Status-ok / Ersparnis (eigene Achsen/Charts).
 */

// ─── Energie-Rollen (A2-Datentyp-Achse) ─────────────────────────────────────

export const COLORS = {
  solar: '#f59e0b',       // F1: kanonisches Amber
  grid: '#b91c1c',        // F2: Dunkelrot — Netzbezug-Serie überall
  consumption: '#8b5cf6', // Violett
  battery: '#3b82f6',     // Blau
  feedin: '#10b981',      // Emerald (F4: bewusst ≠ #22c55e)
}

// ─── Status-Achse (F3) — Zustände, Ampeln, Badges, Alerts ───────────────────

export const STATUS_COLORS = {
  ok: '#22c55e',       // green-500
  warnung: '#eab308',  // yellow-500
  kritisch: '#ef4444', // Signal-Rot
  info: '#3b82f6',     // blue-500
}

/** 4-stufige Ampel-Skala für Gauges (Status-Achse + Zwischenstufe Orange). */
export const AMPEL_SKALA = {
  gut: STATUS_COLORS.ok,
  maessig: STATUS_COLORS.warnung,
  hoch: '#f97316',     // orange-500 — Zwischenstufe vor kritisch
  kritisch: STATUS_COLORS.kritisch,
}

/** Tailwind-Text-Klassen-Zwilling zu {@link AMPEL_SKALA} (Regel G, 2026-06-25) —
 *  für SOLL/IST-/SoC-Ampeln (Zahl-Färbung). Hell/Dunkel-Paar je Stufe. */
export const AMPEL_TEXT_CLASS = {
  gut: 'text-green-500 dark:text-green-400',
  maessig: 'text-yellow-500 dark:text-yellow-400',
  hoch: 'text-orange-500',
  kritisch: 'text-red-500',
} as const

/** Tailwind-bg-Klassen-Zwilling zu {@link AMPEL_SKALA} (Regel G) — Fortschritts-
 *  balken/Marker. Töne wie die bisherigen Bilanz-Ampeln (gut=500, maessig/hoch=400). */
export const AMPEL_BG_CLASS = {
  gut: 'bg-green-500',
  maessig: 'bg-yellow-400',
  hoch: 'bg-orange-400',
  kritisch: 'bg-red-500',
} as const

/** SOLL/IST-Fortschritts-Stufe aus Erfüllungs-% (≥100 gut, ≥75 mäßig, sonst hoch).
 *  EINE Quelle für die in Monat-/Jahr-Bilanz doppelt kodierte Ampel (Regel G). */
export function sollIstStufe(pct: number): 'gut' | 'maessig' | 'hoch' {
  return pct >= 100 ? 'gut' : pct >= 75 ? 'maessig' : 'hoch'
}

/** Tailwind-Text-Klassen-Zwilling zu {@link STATUS_COLORS} (R3b S18, 2026-07-05 —
 *  Muster = AMPEL_TEXT_CLASS/Regel G): Status-Färbung von Icons/Legenden als EINE
 *  Quelle statt harter Klassen (Drift-Beleg: EinstellungenV4-warn zeigte amber-500
 *  = Solar-Rolle statt Kanon-Gelb). */
export const STATUS_TEXT_CLASS = {
  ok: 'text-green-500',
  warnung: 'text-yellow-500',
  kritisch: 'text-red-500',
  info: 'text-blue-500',
} as const

/**
 * Erfassungs-Zustände Monatsabschluss-V4 (V-c, Gernot 2026-07-12) — die vier
 * Feld-Zustände der Erfassung als EIN Vokabular, wiederholt an Feld · Kopf-Ampel ·
 * Monatsdaten-Tabelle (Konzept `KONZEPT-MONATSABSCHLUSS-V4.md` §5). Bewusst aus der
 * bestehenden Status-Achse abgeleitet, kein neuer Farbsatz (Regel 0a Stufe 2):
 * - `gemessen`  = {@link STATUS_COLORS}.ok (grün, vertrauenswürdig)
 * - `geschaetzt`= {@link STATUS_COLORS}.warnung (gelb, prüfen)
 * - `weicht_ab` = {@link AMPEL_SKALA}.hoch (orange, bewusst entscheiden) — eine Stufe
 *   UNTER Signal-Rot; Rot bleibt exklusiv für harte Blockier-Fehler (negative Zähler)
 * - `fehlt`     = neutral-grau (ruhig; Frischmonat hat viele leere Felder und soll
 *   nicht brüllen — Gernot 2026-07-12)
 *
 * `hex` für Recharts/Inline; `text`/`badge` als Tailwind-Zwillinge (Badge-Tönung wie
 * VERGLEICH_BADGE/QuelleBadge). Icons liegen NICHT hier, sondern in der Zustands-
 * Komponente (`ErfassungZustandBadge`) — colors.ts bleibt rein (tailwind.config via jiti).
 */
export const ERFASSUNG_ZUSTAND = {
  gemessen:   { hex: STATUS_COLORS.ok,      text: 'text-green-500',                   badge: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400' },
  // geprüft teilt bewusst das Grün von gemessen (Farb-Achse bleibt bei 4, Gernot
  // 2026-07-12) — Icon/Label unterscheiden „von dir" von „vom Sensor".
  geprueft:   { hex: STATUS_COLORS.ok,      text: 'text-green-500',                   badge: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400' },
  geschaetzt: { hex: STATUS_COLORS.warnung, text: 'text-yellow-500',                  badge: 'bg-yellow-50 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-300' },
  weicht_ab:  { hex: AMPEL_SKALA.hoch,      text: 'text-orange-500',                  badge: 'bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300' },
  fehlt:      { hex: '#9ca3af', /* gray-400 */ text: 'text-gray-500 dark:text-gray-400', badge: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300' },
  // optional = leiser als „offen" (gray-400, hellere Pille) → leer, aber nicht nötig.
  optional:   { hex: '#9ca3af', /* gray-400 */ text: 'text-gray-400 dark:text-gray-500', badge: 'bg-gray-50 text-gray-400 dark:bg-gray-800 dark:text-gray-500' },
} as const

/**
 * Zustands-Token „laufender Zeitraum" (R3b S18, 2026-07-05): heute/läuft-Markierung
 * der Zeit-Sichten (Badges der Sicht-Köpfe, Pulse-Dots + Wert-Färbung der Rails,
 * ZeitStepper). Emerald — bewusst getrennt von STATUS_COLORS.ok (green-500); die
 * farbliche Nähe zur Einspeisung-Rolle (feedin #10b981) ist bekannt und akzeptiert
 * (unterschiedliche Kontexte: Zustands-Chip vs. Chart-Serie).
 */
export const LAUFEND_ZUSTAND = {
  badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300',
  punkt: 'bg-emerald-400 border-emerald-500 animate-pulse',
  text: 'text-emerald-500 dark:text-emerald-400',
} as const

// ─── Geld-Logik — positiv = grün, negativ/Kosten = Signal-Rot ────────────────

export const GELD_COLORS = {
  ertrag: '#10b981',    // Erlöse (z. B. Einspeisevergütung)
  ersparnis: '#22c55e', // vermiedene Kosten
  kosten: '#ef4444',    // Signal-Rot
  netto: '#059669',     // emerald-600 — Netto-Ertrag
}

/** Tailwind-Text-Klassen-Zwilling zu {@link GELD_COLORS} (Regel E, 2026-06-25) —
 *  für Geld-Zeilen in Tabellen/KPIs (Inline-`text-green-600` etc. verboten). */
export const GELD_TEXT_CLASS = {
  ertrag: 'text-emerald-600 dark:text-emerald-400',
  ersparnis: 'text-green-600 dark:text-green-400',
  kosten: 'text-red-600 dark:text-red-400',
  netto: 'text-emerald-700 dark:text-emerald-400',
} as const

/**
 * Trend-/Delta-Wertungsfärbung (R3b S18, 2026-07-05): „besser = grün, schlechter =
 * rot" für Trends/Abweichungen/Korrekturfaktoren. WICHTIG: der KONSUMENT bestimmt
 * die Richtung — Vorzeichen ≠ Wertung (steigende JAZ = positiv, steigender
 * Verbrauch wäre negativ). Optisch identisch mit GELD_TEXT_CLASS.ersparnis/kosten,
 * semantisch getrennte Rolle (späterer Paletten-/CSS-Var-Umbau stellt beide
 * unabhängig um).
 */
export const TREND_TEXT_CLASS = {
  positiv: 'text-green-600 dark:text-green-400',
  negativ: 'text-red-600 dark:text-red-400',
  neutral: 'text-gray-500 dark:text-gray-400',
} as const

/** CO₂-/Umwelt-Text-Zwilling (R3b S18, 2026-07-05) — an CHART_COLORS.co2Pv
 *  (#10b981 Emerald) verankert; für Einsparungs-Werte in KPIs/Tabellen statt
 *  harter green-600-Klassen. */
export const CO2_TEXT_CLASS = 'text-emerald-600 dark:text-emerald-400'

// ─── Chart-Farben (nach Metrik) ──────────────────────────────────────────────

export const CHART_COLORS = {
  // Energie
  erzeugung: COLORS.solar,
  eigenverbrauch: COLORS.consumption,
  einspeisung: COLORS.feedin,
  netzbezug: COLORS.grid,
  // R17/Verlauf-Vergleich: PV-Anlage vs. BKW getrennt (beide Amber-Familie,
  // BKW heller abgesetzt) + §51-Abzug-Volumen (gedämpft = „nicht vergütet").
  bkw: '#fbbf24',                // Amber-400 (BKW, abgesetzt von PV-Anlage-Solar)
  einspeisungNeg51: '#94a3b8',   // Slate-400 (§51: eingespeist bei neg. Preis, nicht vergütet)
  autarkie: '#3b82f6',           // Blue (Metrik-Farbe, unabhängig von battery)
  evQuote: '#a855f7',            // Purple-500
  direktverbrauch: '#f97316',    // Orange
  spezErtrag: '#eab308',         // Yellow
  // Speicher
  speicherLadung: '#f97316',     // Orange (F4-Revision #243): klar abgesetzt von Einspeisung-Emerald; war #22c55e
  speicherEntladung: '#3b82f6',  // Blue
  speicherEffizienz: '#06b6d4',  // Cyan
  // Wärmepumpe (Komponenten-Identität Rot bleibt — dokumentiert, s. Kopf)
  wpWaerme: '#ef4444',
  wpStrom: '#8b5cf6',
  wpCop: '#f97316',
  // E-Mobilität
  emobKm: '#8b5cf6',
  emobLadung: '#3b82f6',
  emobPvAnteil: '#10b981',
  // CO2
  co2Pv: '#10b981',
  co2Wp: '#ef4444',
  co2Emob: '#8b5cf6',
  // Finanzen (Geld-Logik; wpErsparnis war Fehlfarbe Rot → grün, A2-Bereinigung)
  einspeiseErloes: GELD_COLORS.ertrag,
  evErsparnis: '#8b5cf6',
  wpErsparnis: GELD_COLORS.ersparnis,
  emobErsparnis: '#3b82f6',
  nettoErtrag: GELD_COLORS.netto,
  // Wetter / Umgebung
  temperatur: '#6366f1',         // Indigo
  strahlung: '#f59e0b',          // = solar (GHI/GTI)
  bewoelkung: '#94a3b8',         // slate-400
  niederschlag: '#0ea5e9',       // sky-500
  strompreis: '#a855f7',         // Purple-500
  solarNoon: '#f97316',          // Sonnenhöchststand-Marker (≠ SA/SU = solar)
  // Detail-Rollen (Sweep-Nachträge 2026-06-12, Regel 0a Stufe 2)
  speicherArbitrage: '#8b5cf6',  // Netz-Ladung fürs Arbitrage-Laden (Detail-Stack)
  speicherZyklen: '#8b5cf6',     // Vollzyklen-Verlauf
  wpWarmwasser: '#3b82f6',       // WP-Warmwasser = blau (Gernot 2026-06-25 nach detLAN: „Wasser=blau" — Tester-Wunsch übersteuert die kurzzeitige rot-400-Variante). Heizung = wpWaerme (rot)
  emobV2h: '#06b6d4',            // Vehicle-to-Home-Rückspeisung
}

/** Börsenpreis-Stufen (#335) — EINE Datenrolle (Strompreis), nach Preisniveau abgestuft.
 *
 *  Das ist kein zweiter Farbsatz für eine zweite Rolle, sondern eine Skala **innerhalb**
 *  der Rolle `CHART_COLORS.strompreis`: dieselbe Größe, eingefärbt nach ihrem Abstand zum
 *  optimierten Tages-Ø. Deshalb bleibt die Mitte exakt die Rollenfarbe, und nur die beiden
 *  Enden weichen ab — `guenstig` in Grün, weil genau das die Aussage des Blocks ist
 *  („diese Stunden sind billig"), `teuer` als Gegenpol dazu.
 *
 *  ⚠ **Die beiden Randstufen sind theme-abhängig, und zwar aus Messung, nicht aus
 *  Geschmack.** Eine feste Farbe je Stufe war die erste Fassung, und sie fiel in je einem
 *  Modus unter die 3:1-Schwelle für grafische Objekte (WCAG 1.4.11): Grün-500 erreicht auf
 *  Weiß nur 2,28:1, Purple-700 auf dunklem Grund nur 2,10:1. Beide Enden weichen deshalb
 *  **vom Hintergrund weg** statt in eine feste Richtung — im hellen Modus nach dunkel, im
 *  dunklen nach hell. Muster wie `CHART_ACHSEN.light/.dark`; gelesen über
 *  {@link usePreisstufenFarben}.
 *
 *  ⚠ **`teuer` war bis v4.0.10 die dunklere bzw. hellere Stufe derselben Lila-Familie —
 *  und das trug nicht.** Radiocarbonat hat es an der Legende gemeldet (T89667 #110,
 *  2026-08-07, mit Bild): zwei Lila-Punkte von 8×12 px nebeneinander, für ihn nicht
 *  unterscheidbar. Der Prüf-Blindfleck beim Bau war, jede Stufe nur **gegen den
 *  Hintergrund** zu messen — Sichtbarkeit und Unterscheidbarkeit voneinander sind zwei
 *  verschiedene Prüfungen, und nur die erste war gedeckt.
 *
 *  **Warum ein Farbton-Wechsel und nicht ein größerer Helligkeitsabstand:** Solange die
 *  Mitte die Rollenfarbe Purple-500 bleibt, ist 3:1 zur Mitte **rechnerisch unerreichbar**
 *  — eine Farbe, die 3:1 heller als die Mitte ist, steht praktisch auf dem Hintergrund
 *  (15 Kandidaten durchgerechnet, bester Wert 2,35:1). Die Helligkeits-Achse ist
 *  ausgereizt; die Unterscheidung muss über den Farbton laufen. Rot trägt zusätzlich die
 *  Aussage: `guenstig` grün ↔ `teuer` rot liest sich ohne Legende.
 *
 *  ⚠ **Bewusste Nähe zu {@link COLORS}`.grid` (#b91c1c, Netzbezug), Regel 0a Stufe 3:**
 *  Jedes Rot hat denselben Farbton wie das Netzbezug-Rot, der Abstand ist per Definition
 *  0° und mit keiner Rot-Wahl auflösbar (gemessen: Kontrast 1,55:1 zu red-900). Tragfähig
 *  ist sie, weil der Börsenpreis-Block **keine Netz-Serie enthält** — die beiden begegnen
 *  sich in keinem Bild. Wer hier eine Verbrauchs- oder Netz-Serie ergänzt, löst die
 *  Ausnahme auf und muss neu wählen.
 *
 *  ⚠ **Ehrlich zur Gegenrichtung:** im dunklen Modus sinkt der Helligkeitsabstand
 *  `teuer`↔`guenstig` von 1,74:1 auf 1,20:1 (beide Randstufen müssen dort hell sein).
 *  Getragen wird das vom Farbton-Abstand (142°) **und** davon, dass jeder Legendenpunkt
 *  beschriftet ist — die Farbe ist nicht der einzige Informationsträger (WCAG 1.4.1).
 *
 *  Die Grenzen sind Daten, keine Farben: `guenstig` gilt unterhalb der anlagen-eigenen
 *  Günstig-Schwelle (Backend, ungekappt — nicht der auf fünf gedeckelte Rang), `teuer`
 *  oberhalb des optimierten Ø. Wer die Schwellen ändert, ändert sie im Backend. */
export const PREISSTUFEN_FARBEN = {
  light: {
    guenstig: '#16a34a',   // green-600 · 3,30:1 auf Weiß (green-500 wären 2,28:1)
    normal: '#a855f7',     // = CHART_COLORS.strompreis, in beiden Modi über 3:1
    teuer: '#7f1d1d',      // red-900 · 10,02:1 auf Weiß · 2,53:1 zur Mitte, Farbton 89° entfernt
  },
  dark: {
    guenstig: '#22c55e',   // green-500 · 6,44:1 auf dunklem Grund
    normal: '#a855f7',     // dieselbe Rollenfarbe — die Mitte wandert nicht
    teuer: '#fca5a5',      // red-300 · 7,73:1 auf dunklem Grund · 2,08:1 zur Mitte, Farbton 89° entfernt
  },
} as const

/** E-Auto-/Wallbox-Ladequellen — ein Trio, überall gleich (PV günstig → Extern teuer). */
export const LADEQUELLEN_FARBEN = {
  pv: '#22c55e',
  netz: COLORS.grid,   // Netz-Ladung IST Netzbezug → Dunkelrot
  extern: '#f97316',
}

/** „Du/deine Daten"-Hervorhebung in Community-Vergleichen — überall dieselbe. */
export const EIGENE_SERIE_FARBEN = {
  du: '#3b82f6',
  duRand: '#1d4ed8',   // Rahmen/Outline der eigenen Markierung (z. B. Choropleth)
  region: '#60a5fa',   // Zwischenebene Du ↔ Community
}

/** Hervorhebung einer einzelnen Scheibe/Serie als „die eigene" in Anteils-Charts
 *  (Donut, Verteilungs-Pie) — kräftiger Ring statt Inline-`#000` (D17-6-SoT).
 *  Als Recharts-`stroke` auf der eigenen `<Cell>` gesetzt; `breite` = strokeWidth. */
export const SERIE_HERVORHEBUNG = { ring: '#111827', breite: 2 } // gray-900

/** Karten-Darstellung (Choropleth). */
export const KARTE_FARBEN = { grenze: '#ffffff' }

/** Neutrale/inaktive Datenserie (z. B. übrige Histogramm-Bins). */
export const SERIE_NEUTRAL = '#d1d5db'

/** „Verlust"-/Schwund-Serie (z. B. Speicher-Wirkungsverlust) — dunkler als
 *  {@link SERIE_NEUTRAL} (gray-400 statt gray-300), damit sich der solide Verlust-
 *  Balken klar vom hellen Chart-Hintergrund UND vom Hover-Grau abhebt (detLAN S5,
 *  2026-06-25). Bewusst gedämpft (Verlust = kein „echter" Energiefluss). */
export const VERLUST_FARBE = '#9ca3af'

/** Schwellen-/Warn-Marker in Charts (ReferenceLine + Beschriftung). */
export const MARKER_WARNUNG = { linie: STATUS_COLORS.warnung, text: '#b45309' }

/** Wochentags-Identitätsfarben (Energieprofil-Gruppierung Mo–So + Sammelgruppen). */
export const WOCHENTAG_FARBEN: Record<string, string> = {
  'Mo–Fr': '#3b82f6',
  'Sa–So': '#f97316',
  'Mo': '#6366f1',
  'Di': '#8b5cf6',
  'Mi': '#ec4899',
  'Do': '#14b8a6',
  'Fr': '#84cc16',
  'Sa': '#f59e0b',
  'So': '#ef4444',
}

// ─── SOLL/IST-Vergleichsfarben (zentral für alle SOLL-IST-Diagramme) ────────
//
// Müssen in ALLEN SOLL-IST-Diagrammen gleich sein, damit Nutzer konsistente
// Farben über Tabs/Seiten hinweg sehen (Cockpit, Auswertungen, Aussichten).

export const SOLL_IST_COLORS = {
  soll: '#3b82f6',   // Blau (Prognose)
  ist: '#f59e0b',    // Amber (tatsächlicher Wert)
  abweichung: '#10b981',  // Grün (Differenz-Linie)
}

/** Prognose-Quellen — eine Quelle = überall dieselbe Farbe (Vergleichs-Tab, Charts).
 *  `sfml` ist die vom Anwender gewählte externe Quelle (Solar Forecast ML, nur im
 *  HA-Add-on) — sie erscheint im Vergleich als **Wert**, nie im Genauigkeits-Ranking
 *  ([[project_sfml_tom_ha]], `api/routes/prognosen.py` „KEIN Cross-Quellen-Ranking"). */
export const PROGNOSE_QUELLEN_COLORS = {
  ist: '#22c55e',
  openmeteo: '#eab308',
  eedc: '#f97316',
  solcast: '#3b82f6',
  sfml: '#8b5cf6',
}

/** Tailwind-Text-Klassen-Zwillinge zu {@link PROGNOSE_QUELLEN_COLORS} (R3): die
 *  Quellen-Rolle als Text-Farbe in Tabellen/Headern/Legenden-Text — eine Quelle =
 *  überall dieselbe Farbklasse, statt inline `text-yellow/orange/blue/green-500`. */
export const PROGNOSE_QUELLEN_TEXT = {
  ist: 'text-green-500',
  openmeteo: 'text-yellow-500',
  eedc: 'text-orange-500',
  solcast: 'text-blue-500',
  sfml: 'text-violet-500',
}

// ─── Mehrserien-Paletten ─────────────────────────────────────────────────────

/** Jahres-/Serienvergleich (Balken pro Jahr) — Reihenfolge fix, max. 5 Serien. */
export const SERIEN_PALETTE = ['#f59e0b', '#22c55e', '#3b82f6', '#ef4444', '#8b5cf6']

/** PV-String-Vergleich (bis 6 Strings) — identisch in allen String-Ansichten. */
export const STRING_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899']

/** Tailwind-bg-Klassen-Zwillinge zu STRING_COLORS (Tailwind-500) — für VerteilungsBalken/
 *  Anteils-Darstellungen pro String/Modul (dort sind bg-Klassen statt Inline-Hex nötig). */
export const STRING_BG = ['bg-amber-500', 'bg-blue-500', 'bg-emerald-500', 'bg-violet-500', 'bg-cyan-500', 'bg-pink-500']

/**
 * **Kanonische Datenrollen-Farben (SoT, Gernot 2026-06-24)** — die EINE Quelle
 * für „eine Datenrolle = eine Farbe" (Regel 0a). Jede Rolle trägt den Recharts-
 * **Hex** (Linien/Balken/Pies) UND die **Tailwind-bg-Klasse** (VerteilungsBalken),
 * damit dieselbe Rolle in JEDER Darstellung gleich aussieht. Abgeleitet aus
 * {@link COLORS}; Hex ↔ bg sind aufeinander abgestimmte Tailwind-500-Töne.
 *
 * Vorher lagen die Rollenfarben dreifach auseinander (Inline-`bg-purple/green`
 * in den Bilanzen, `ROLLEN_BG` grün/blau im Hub-Balken, `CHART_COLORS` violett/
 * emerald im Hub-Chart) → behoben, alles zieht jetzt von hier.
 */
export const DATENROLLE = {
  pv:                { hex: COLORS.solar,       bg: 'bg-amber-500',   text: 'text-amber-500',   fill: 'fill-amber-500' },   // PV-Erzeugung
  eigenverbrauch:    { hex: COLORS.consumption, bg: 'bg-violet-500',  text: 'text-violet-500',  fill: 'fill-violet-500' },  // = Direktverbrauch (genutzte PV)
  einspeisung:       { hex: COLORS.feedin,      bg: 'bg-emerald-500', text: 'text-emerald-500', fill: 'fill-emerald-500' }, // ins Netz abgegeben
  netzbezug:         { hex: COLORS.grid,        bg: 'bg-red-700',     text: 'text-red-700',     fill: 'fill-red-700' },     // aus dem Netz bezogen
  speicherLadung:    { hex: '#f97316',          bg: 'bg-orange-500',  text: 'text-orange-500',  fill: 'fill-orange-500' },  // in den Speicher
  speicherEntladung: { hex: COLORS.battery,     bg: 'bg-blue-500',    text: 'text-blue-500',    fill: 'fill-blue-500' },    // aus dem Speicher
  extern:            { hex: '#9ca3af',          bg: 'bg-gray-400',    text: 'text-gray-400',    fill: 'fill-gray-400' },    // externe Ladung
} as const

/** PV-Modul-Palette = Schattierungen der Solar-Farbe (alle Module sind PV) —
 *  bewusst KEINE kategorischen Fremdfarben, damit Module nicht mit den
 *  Verwendungs-Rollen (emerald/orange/violett) im selben Stapel-Chart kollidieren
 *  (Rainer/Gernot 2026-06-24: Westdach=Einspeisung, Süddach≈Speicherladung).
 *
 *  **Regel-Scope (Gernot 2026-06-24):** Amber-Schattierungen NUR dort, wo Module
 *  UND Rollen im selben Chart liegen (Komponenten-Hub PV-Verlauf). Eigenständige
 *  String-/Modul-Charts ohne Rollen (z. B. `PVStringVergleich` SOLL/IST pro
 *  String) behalten die distinkten {@link STRING_COLORS} — dort trennen bunte
 *  Töne mehrere Strings besser und es gibt keine Kollision.
 *
 *  **Keine Identitätsfarbe in der Palette (A20/N49).** Index 3 war `#fbbf24`
 *  (Amber-400) — exakt die BKW-Identität ({@link KOMPONENTEN_FARBEN}
 *  `balkonkraftwerk` / {@link CHART_COLORS}.bkw). Ab dem **vierten** Modul lagen
 *  im Komponenten-Hub-PV-Verlauf zwei Reihen desselben Stapels auf demselben
 *  Ton („mehrere Dachsegmente + BKW"). Jetzt Amber-600. Geprüft wurde die ganze
 *  Palette gegen alle Farben, die in DIESEM Chart vorkommen können — BKW
 *  (#fbbf24), sonstige Erzeuger (#84cc16) und die drei Verwendungs-Serien
 *  Direktverbrauch (#8b5cf6) · Speicherladung (#f97316) · Einspeisung (#10b981);
 *  engster verbleibender Abstand des neuen Tons: ΔE 15,4 gegen Speicherladung
 *  (anderer Stapel). Der Wächter `check-farbkollision.test.ts` hält den Zustand. */
export const PV_MODUL_FARBEN = ['#b45309', '#f59e0b', '#fcd34d', '#d97706', '#78350f', '#fde68a']
export const PV_MODUL_BG = ['bg-amber-700', 'bg-amber-500', 'bg-amber-300', 'bg-amber-600', 'bg-amber-900', 'bg-amber-200']

/** Datenrollen → Tailwind-bg-Klasse für Aufteilungs-Segmente (VerteilungsBalken).
 *  Leitet aus {@link DATENROLLE} ab (keine Parallel-Definition mehr); WP-Roh-
 *  rollen (heizung/warmwasser) sind komponenten-eigene Identitäten. */
export const ROLLEN_BG = {
  pv: DATENROLLE.pv.bg,
  ev: DATENROLLE.eigenverbrauch.bg,
  einspeisung: DATENROLLE.einspeisung.bg,
  netz: DATENROLLE.netzbezug.bg,
  extern: DATENROLLE.extern.bg,
  heizung: 'bg-red-500',       // WP-Heizwärme = WP-Identitätsrot (Regel A; war orange)
  warmwasser: 'bg-blue-500',   // WP-Warmwasser = blau (Gernot 2026-06-25 nach detLAN; = CHART_COLORS.wpWarmwasser + Backend-Live)
  // #263 K-2: der Kühlbetrieb einer Split-Klimaanlage. Bewusst `sky` und nicht
  // `blue` (das ist WP-Warmwasser) und nicht `cyan` (Wallbox-Identität) — beide
  // Rollen hängen am selben Gerät bzw. derselben Sicht, und dieselbe Farbe für
  // zwei Bedeutungen ist genau das, was Regel „eine Datenrolle = eine Farbe"
  // verhindert.
  kuehlung: 'bg-sky-500',
  // E4 (Konzept §2.3, 26.08.): Lüften und Entfeuchten sind **erfassbar, aber
  // keine bewertete Funktion**. Eine Familie, zwei Töne — das sagt „diese
  // beiden gehören zusammen", ohne ihnen die Identität einer bewerteten Rolle
  // zu geben. `indigo` war als einzige Familie unbelegt (erhoben 26.08.);
  // bewusst nicht `sky` (Kühlung), nicht `violet` (Eigenverbrauch), nicht
  // `teal` (E-Auto) und nicht `gray` (das ist der Rest, s. u.).
  lueftung: 'bg-indigo-400',
  entfeuchtung: 'bg-indigo-600',
  // „Weder das eine noch das andere" — Standby und die Zeit ohne Modus-Signal.
  // Neutrales Grau wie `extern`: es ist keine eigene Betriebsart, sondern der
  // Rest. ⚠ **Bis zum 26.08.2026 nannte dieser Kommentar auch Lüften und
  // Entfeuchten** — richtig, solange es für sie keine eigene Zeile gab. Seit
  // E4 gilt beides nebeneinander: **gemessen** bekommen sie ihr Segment,
  // **ungemessen** bleiben sie hier.
  nicht_aufgeteilt: 'bg-gray-400',
  ladung: DATENROLLE.speicherLadung.bg,
  entladung: DATENROLLE.speicherEntladung.bg,
} as const

/** Solar-Intensitäts-Rampe (Sparklines: schwach → stark). */
export const SOLAR_INTENSITAET = ['#fde68a', '#fbbf24', '#f59e0b']

/** Zusatz-/Extra-Serien (dynamische Kategorien jenseits der festen Rollen). */
export const EXTRA_SERIEN_FARBEN = ['#8b5cf6', '#06b6d4', '#84cc16', '#f43f5e', '#fb923c', '#a78bfa']

// ─── Tooltip-Grundfarben (Vorgriff auf den Tooltip-Kanon, Paket P3) ─────────

export const TOOLTIP_FARBEN = {
  bg: '#111827',      // gray-900 — Tooltip-Kanon (P3, = FormelTooltip/ChartTooltip-Fläche)
  text: '#ffffff',
}

/**
 * Hover-/Cursor-Overlay für Charts (S3/S4, Triage 2026-06-24) — die EINE
 * app-weite Hover-Mechanik. Recharts zeichnet `cursor.fill` NUR bei Bar-/
 * Composed-Charts als Highlight-Rechteck (Linien/Flächen behalten ihren
 * Default-Cursor). Mittleres Grau mit NIEDRIGER Alpha → dezent in hell UND
 * dunkel (Dark nicht mehr grell, S3), das **Raster scheint durch** und der
 * **Balken bleibt deckend** (S4: nicht der Balken wird transparent, sondern der
 * Hintergrund). Hebt sich klar von soliden „Verlust"-Grau-Balken ab (S5).
 * Als `cursor={CHART_HOVER_CURSOR}` an `<Tooltip>` setzen.
 */
export const CHART_HOVER_CURSOR = { fill: 'rgba(107, 114, 128, 0.14)' } // gray-500 @ 14 %

/**
 * Strich-Muster für **Prognose-/SOLL-Serien** in Charts (Gernot 2026-06-24) —
 * die EINE app-weite Konvention: „Prognose/SOLL = gestrichelt, IST/gemessen =
 * durchgezogen". Auf `strokeDasharray` von Linien, Flächen-Rändern UND Balken-
 * Rändern setzen (z. B. PVGIS-Prognose, OpenMeteo/Solcast/eedc-Prognose, SOLL).
 * Ersetzt die früheren ad-hoc-Muster `"4 2"`/`"5 3"`.
 *
 * **Geschärfte Semantik (Regel C, Gernot 2026-06-25):** Gestrichelt = Prognose/
 * SOLL **nur, wenn eine IST-Serie im selben Chart liegt** (Prognose vs. gemessen
 * eindeutig). Hilfs-/Summen-/Overlay- und Referenz-/Basis-Modell-Linien (auch in
 * Charts OHNE IST-Serie) nehmen {@link HILFSLINIE_DASH} — sonst liest der Nutzer
 * „gestrichelt = Prognose" falsch (z. B. PVGIS-Referenz gestrichelt, während die
 * genauere trend-korrigierte Hauptprognose solide ist).
 */
export const PROGNOSE_DASH = '5 3'

/**
 * Strich-Muster für **Hilfs-/Referenz-/Summen-Linien** (Regel C, Gernot
 * 2026-06-25) — Overlay-/Aggregat-/Basis-Modell-Linien, die KEINE Prognose-vs-
 * IST-Aussage tragen: Summen-/„Gesamt"-Linien, Strompreis-Overlays, und das
 * Referenz-/Basis-Modell in Charts ohne eigene IST-Serie (PVGIS-Referenz). Hält
 * {@link PROGNOSE_DASH} für die eindeutige Prognose-Markierung frei. Ersetzt die
 * rohen Muster `"4 2"`/`"5 5"`/`"6 3"`.
 */
export const HILFSLINIE_DASH = '4 2'

// ─── Chart-Infrastruktur: Achsen/Grid/Referenzlinien (hell + dunkel) ────────

/** Für Inline-Styles in Charts (Recharts stroke etc.) — Tailwind-Klassen gehen vor. */
export const CHART_ACHSEN = {
  light: { achse: '#6b7280', grid: '#e5e7eb', referenz: '#9ca3af' }, // gray-500/200/400
  dark:  { achse: '#9ca3af', grid: '#374151', referenz: '#6b7280' }, // gray-400/700/500
}

/** Fläche, auf der Charts stehen — der Hex-Zwilling von `bg-white dark:bg-gray-800`.
 *
 *  Nicht zum Färben gedacht (das macht Tailwind), sondern als **Bezugsgröße**: Ob
 *  eine Serienfarbe sichtbar ist, ist eine Aussage über ihren Kontrast zu dieser
 *  Fläche, und die lässt sich nur gegen einen benannten Wert prüfen. Angelegt mit
 *  der Kontrast-Probe der Preisstufen (#335), die sonst zwei Hex-Werte im Test
 *  hätte hartkodieren müssen — und damit die Frage „gegen welchen Hintergrund
 *  eigentlich?" jedem künftigen Leser überlassen. */
export const CHART_FLAECHE = {
  light: '#ffffff',
  dark: '#1f2937',   // gray-800
}

// ─── Komponenten-Identität (Investitionstyp) — kanonische SoT (Regel A) ──────
/**
 * **Kanonische Komponenten-Identitäts-Farbmap (SoT, Gernot 2026-06-24, Regel A)**
 * — die EINE Quelle für „eine Komponente = eine Identitätsfarbe" je Investitions-
 * typ. Jeder Eintrag trägt Recharts-`hex` + Tailwind-`bg` + Tailwind-`text`-Zwilling.
 * **Kollisionsfrei + disjunkt von {@link DATENROLLE}** — Ausnahmen: PV=Amber und
 * Speicher=Blau teilen bewusst die gleichnamige Rolle (Komponente = ihre Rolle).
 * `TYP_COLORS`/`TYP_TEXT_CLASS` UND die Komponenten-Keys von `KATEGORIE_FARBEN`
 * leiten hieraus ab (kein zweiter Satz). SoT-Doc: `docs/drafts/archive/flip-v4/SPEC-IDENTITAETS-FARBMAP.md`.
 */
export const KOMPONENTEN_FARBEN = {
  'pv-module':       { hex: '#f59e0b', bg: 'bg-amber-500',  text: 'text-amber-500',  tint: 'bg-amber-50 dark:bg-amber-900/20' },   // = PV-Rolle (bewusst)
  'wechselrichter':  { hex: '#eab308', bg: 'bg-yellow-500', text: 'text-yellow-500', tint: 'bg-yellow-50 dark:bg-yellow-900/20' },
  'speicher':        { hex: '#3b82f6', bg: 'bg-blue-500',   text: 'text-blue-500',   tint: 'bg-blue-50 dark:bg-blue-900/20' },     // = Speicher-Entladung-Rolle (bewusst)
  'e-auto':          { hex: '#14b8a6', bg: 'bg-teal-500',   text: 'text-teal-500',   tint: 'bg-teal-50 dark:bg-teal-900/20' },     // war Violett (= EV-Rolle) → Teal
  'wallbox':         { hex: '#06b6d4', bg: 'bg-cyan-500',   text: 'text-cyan-500',   tint: 'bg-cyan-50 dark:bg-cyan-900/20' },
  'waermepumpe':     { hex: '#ef4444', bg: 'bg-red-500',    text: 'text-red-500',    tint: 'bg-red-50 dark:bg-red-900/20' },       // Identitäts-Rot (Ko-Existenz Signal-Rot, dokumentiert)
  'balkonkraftwerk': { hex: '#fbbf24', bg: 'bg-amber-400',  text: 'text-amber-400',  tint: 'bg-amber-50 dark:bg-amber-900/20' },   // war Emerald (= Einspeisung-Rolle) → helles Amber
  'sonstiges':       { hex: '#6b7280', bg: 'bg-gray-500',   text: 'text-gray-500',   tint: 'bg-gray-50 dark:bg-gray-900/20' },
  'pv-system':       { hex: '#d97706', bg: 'bg-amber-600',  text: 'text-amber-600',  tint: 'bg-amber-50 dark:bg-amber-900/20' },   // war Orange (= speicherLadung-Rolle) → dunkles Amber
} as const

/** Sonstiger Erzeuger / Mini-BHKW (typ=`sonstiges` + Kategorie `erzeuger`) — eigene
 *  Identität, da KEIN eigener Investitionstyp. Lime, distinkt von PV-Amber/Emerald. */
export const SONSTIGES_ERZEUGER_FARBE = { hex: '#84cc16', bg: 'bg-lime-500', text: 'text-lime-500', tint: 'bg-lime-50 dark:bg-lime-900/20' } as const

// ─── Tagesverlauf-Kategorien ─────────────────────────────────────────────────

/** Farben für Energiefluss-/Bilanz-Visualisierungen (nach Tagesverlauf-Kategorie).
 *  Rollen (pv/netz/batterie) ← {@link COLORS}; Komponenten ← {@link KOMPONENTEN_FARBEN};
 *  `haushalt` = virtuelle Verbrauchs-Aggregat-Serie (eigener Ton, NICHT Einspeisung). */
export const KATEGORIE_FARBEN: Record<string, string> = {
  pv: COLORS.solar,        // F1: war #eab308 — kanonisiert
  netz: COLORS.grid,       // F2: Dunkelrot
  batterie: COLORS.battery,
  eauto: KOMPONENTEN_FARBEN['e-auto'].hex,        // Teal (war #a855f7 = identisch zu wallbox)
  wallbox: KOMPONENTEN_FARBEN['wallbox'].hex,     // Cyan (war #a855f7)
  waermepumpe: KOMPONENTEN_FARBEN['waermepumpe'].hex,  // Rot (war #f97316 = speicherLadung-Rolle)
  sonstige: KOMPONENTEN_FARBEN['sonstiges'].hex,
  haushalt: '#64748b',     // slate-500 — war #10b981 (= Einspeisung-Emerald, semantisch falsch)
}

/**
 * Energiefluss-Kategorien der Monats-Auswertung (Backend `KategorieSumme.kategorie`,
 * `getMonat`) → Label · Balken-Farbe (Tailwind-bg) · Erzeuger/Verbraucher-Gruppe.
 * EINE Quelle für die Kategorien-Anteils-Leiste (M4-Wiederherstellung 2026-07-19,
 * war in `pages/auswertung/EnergieprofilMonat.tsx` inline). Farben aus der
 * Komponenten-Identität ({@link KOMPONENTEN_FARBEN}/{@link SONSTIGES_ERZEUGER_FARBE})
 * bzw. Haushalt-Slate wie {@link KATEGORIE_FARBEN}.haushalt — keine neuen Töne.
 * Backend-Producer: `api/routes/energie_profil/views.py` (ERZEUGER_KAT/VERBRAUCHER_KAT).
 */
export const ENERGIE_KATEGORIE: Record<string, { label: string; bg: string; gruppe: 'erzeuger' | 'verbraucher' }> = {
  pv_module:            { label: 'PV-Module',            bg: KOMPONENTEN_FARBEN['pv-module'].bg,       gruppe: 'erzeuger' },
  bkw:                  { label: 'Balkonkraftwerk',      bg: KOMPONENTEN_FARBEN['balkonkraftwerk'].bg, gruppe: 'erzeuger' },
  sonstige_erzeuger:    { label: 'Sonstige Erzeuger',    bg: SONSTIGES_ERZEUGER_FARBE.bg,              gruppe: 'erzeuger' },
  waermepumpe:          { label: 'Wärmepumpe',           bg: KOMPONENTEN_FARBEN['waermepumpe'].bg,     gruppe: 'verbraucher' },
  wallbox_eauto:        { label: 'Wallbox / E-Auto',     bg: KOMPONENTEN_FARBEN['wallbox'].bg,          gruppe: 'verbraucher' },
  haushalt:             { label: 'Haushalt',             bg: 'bg-slate-500',                            gruppe: 'verbraucher' },
  sonstige_verbraucher: { label: 'Sonstige Verbraucher', bg: KOMPONENTEN_FARBEN['sonstiges'].bg,        gruppe: 'verbraucher' },
}

/**
 * Kategorien die KEINE Energieflüsse darstellen (z.B. Preise, virtuelle Serien).
 * Werden im Verbrauchs-Stacking (WetterWidget etc.) ignoriert.
 * → Neue nicht-Energie-Kategorien hier ergänzen, nicht in einzelnen Komponenten.
 */
export const NICHT_ENERGIE_KATEGORIEN = new Set(['preis', 'virtual'])

/** Kategorien die dedizierte DB-Felder/Spalten haben (kein Extra-Tracking nötig) */
export const DEDIZIERTE_KATEGORIEN = new Set([
  'pv', 'batterie', 'netz', 'haushalt', 'waermepumpe', 'wallbox', 'eauto', 'virtual',
])

// ─── Typ-Farben — abgeleitet aus KOMPONENTEN_FARBEN (eine Quelle) ────────────

/** Komponenten-Identität als Hex je Investitionstyp — **abgeleitet** aus
 *  {@link KOMPONENTEN_FARBEN}, nicht mehr parallel pflegen. */
export const TYP_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(KOMPONENTEN_FARBEN).map(([typ, f]) => [typ, f.hex]),
)

/** Tailwind-Text-Klassen-Zwilling der Komponenten-Identität — **abgeleitet** aus
 *  {@link KOMPONENTEN_FARBEN} (Icon-Farben; Inline-Hex verboten, `check:design`).
 *  Konsumiert von `komponentenStyle.KOMPONENTEN_IDENTITAET`. */
export const TYP_TEXT_CLASS: Record<string, string> = Object.fromEntries(
  Object.entries(KOMPONENTEN_FARBEN).map(([typ, f]) => [typ, f.text]),
)

// ─── Chart-Label-Kanon (Regel D, 2026-06-25) ────────────────────────────────
/**
 * Zentrale `dataKey → Anzeige-Label`-Map — von {@link ChartTooltip} (Default-
 * `nameFormatter`) UND {@link ChartLegende} (Default-`formatter`) konsumiert, damit
 * **Tooltip-Label ≡ Legende-Label per Konstruktion** ist und nie Roh-Keys (`pv`/
 * `bat_neg`/…) durchschlagen. Charts mit dynamischen Serien (z. B. Extra-Serien)
 * übergeben weiterhin einen eigenen Formatter, der diese Defaults übersteuert.
 */
export const CHART_LABELS: Record<string, string> = {
  pv: 'PV', pv_kw: 'PV', erzeugung: 'Erzeugung', gesamterzeugung: 'Gesamterzeugung',
  bat_pos: 'Batterie', bat_neg: 'Batterie ↓', batterie: 'Batterie',
  netz_pos: 'Stromnetz', netz_neg: 'Stromnetz ↓', netzbezug: 'Netzbezug',
  einspeisung: 'Einspeisung', eigenverbrauch: 'Eigenverbrauch', direktverbrauch: 'Direktverbrauch',
  hausverbrauch: 'Hausverbrauch', verbrauch: 'Verbrauch',
  wp: 'Wärmepumpe', wb: 'Wallbox', autarkie: 'Autarkie',
}

/** Vergleichs-Badge (▲ besser / ▼ schlechter) — EIN Token statt 3× wortgleich in
 *  Monat-/Jahr-Bilanz + Rahmen (Regel H, 2026-06-25). Hell+Dunkel-Paar. */
// R3b E3 (Folgepunkt aus Etappe-1-B17): Tönung von -100 auf den B17-Kanon -50
// gehoben (+ dark auf /20) — der Token-Konflikt mit der Badge-Regel war in
// Etappe 1 bewusst an S18 vertagt worden.
export const VERGLEICH_BADGE = {
  besser: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400',
  schlechter: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400',
  /** Keine Richtungsaussage — teilt sich den Ton mit „kein Vergleich moeglich",
   *  weil beide dasselbe sagen: hier steht kein Besser/Schlechter. Gebraucht,
   *  seit die Badges aus den ANGEZEIGTEN Zahlen rechnen (2026-08-29): sehen
   *  beide gleich aus, ist der Abstand 0 und ein gruenes „besser" waere eine
   *  Behauptung. Grau-Schablone der B17-Regel (nicht die /20 der Farbtoene). */
  unveraendert: 'bg-gray-50 text-gray-400 dark:bg-gray-700/50 dark:text-gray-500',
} as const

/** Chart-Flächen-/Dimm-Opazitäten als benannte Tokens statt roher Magic-Numbers
 *  (Regel H, 2026-06-25). */
export const AREA_FILL_OPACITY = 0.3        // Flächen-Füllung (Butterfly/Tagesverlauf)
export const SERIE_GEDIMMT = 0.45           // gedimmte/Teildaten-Serie (Fokus/unvollständig)
export const KONFIDENZ_BAND_OPACITY = 0.1   // Prognose-Konfidenzband
