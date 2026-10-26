/**
 * Anker-Karte des Wärme/Klima-Panoramas (Konzept #433 Stufe 2, P-433-2 E1).
 *
 * ⚠ **Von Hand gemessen am Bild v4, 23.10.2026; neues Bild = neue Karte.**
 * Die Werte sind x/y in Prozent des Bildes (1312 × 816) und gelten für Tag- und
 * Nachtbild gleich — beide sind bildgleich erzeugt, das ist die Voraussetzung
 * dieser Tabelle. Quelle: Vorhaben-Blatt «Geräte-Schaubilder», Abschnitt
 * „Wärme/Klima-Panorama v4 aktiv" (Tabelle A–O, P/Q/R) — hier 1:1 übernommen,
 * dazu der feste Anker „Himmel" für die Außentemperatur.
 *
 * **Das Bild zeigt immer alle Gerätearten, deine Anlage zeigen die Kacheln**
 * (B2): welcher Wert an welchem Objekt hängt, entscheidet `kachelAnker.ts`.
 * Seit P-433-3 S1 trägt D die Zusatzheizung (`ANKER_ZUSATZHEIZUNG`); «Vorlauf · Rücklauf» steht seit S2-8 am
 * Heizkreis nach dem Stammdatum `vorlauftemperatur` — K Fußbodenheizung, J Heizkörper, sonst G Hydraulikmodul
 * (`vorlaufAnker` in `kachelAnker.ts`); O bleibt die Luft/Luft-Außeneinheit; H, P, Q, R sind Raumkontext ohne Pin.
 *
 * **Reihe je Anker (P-433-2d, Gernot 26.10.2026): Technik oben, Räume unten** — {@link ANKER_REIHE} neben der Karte,
 * gelesen über {@link ankerReihe}; die Bildlage (y < 50 %, {@link bildReihe}) gilt für Anker ohne Eintrag und als Ziel
 * des Reihenwechsels bei Kreuzung (`ueberblickLayout.ts`).
 *
 * **Zwei Plätze wie Netz und Speicher (P-433-2e, Gernot 26.10.2026):** {@link PLATZ_ANKER} nennt die Anker, deren
 * Gerätekachel am Desktop neben dem Haus steht statt in einer Reihe — links die Wärmepumpe, rechts die
 * Klima-Außeneinheit. Die Lage der Plätze ist am Bild v4 gemessen (siehe dort); neues Bild = neue Messung.
 */

export const PANORAMA_BREITE = 1312
export const PANORAMA_HOEHE = 816

export const WAERME_PANORAMA = {
  tag: './backgrounds/waerme-panorama-tag.webp',
  nacht: './backgrounds/waerme-panorama-nacht.webp',
} as const

export type AnkerId =
  | 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J' | 'K' | 'L' | 'M' | 'N' | 'O'
  | 'P' | 'Q' | 'R' | 'HIMMEL'

export interface Anker {
  /** Prozent der Bildbreite. */
  x: number
  /** Prozent der Bildhöhe. */
  y: number
  objekt: string
}

export const WAERME_ANKER: Record<AnkerId, Anker> = {
  A: { x: 14.1, y: 57.6, objekt: 'Außeneinheit Luft/Wasser (Rasen)' },
  B: { x: 41.5, y: 74.8, objekt: 'Erdsonden (Bodenschnitt)' },
  C: { x: 20.4, y: 45.3, objekt: 'WP-Schrank mit integriertem Speicher' },
  D: { x: 25.8, y: 46.0, objekt: 'Pufferspeicher mit Heizstab' },
  E: { x: 30.5, y: 43.5, objekt: 'Warmwasserspeicher' },
  F: { x: 30.5, y: 38.2, objekt: 'Warmwasser-WP auf dem Speicher' },
  G: { x: 29.0, y: 31.2, objekt: 'Hydraulikmodul (Rückwand)' },
  H: { x: 35.4, y: 35.5, objekt: 'Verteiler (rechte Wand)' },
  I: { x: 40.8, y: 42.3, objekt: 'Zählerreihe (rechte Wand)' },
  J: { x: 82.7, y: 42.3, objekt: 'Heizkörper (Schlafzimmer)' },
  K: { x: 57.9, y: 65.0, objekt: 'Fußbodenheizung (Wohnbereich)' },
  L: { x: 58.3, y: 17.2, objekt: 'Klima-Innengerät Wohnen hinten' },
  M: { x: 59.8, y: 29.4, objekt: 'Klima-Innengerät Wohnen Mitte' },
  N: { x: 69.7, y: 26.3, objekt: 'Klima-Innengerät Schlafzimmer' },
  O: { x: 89.2, y: 47.8, objekt: 'Klima-Außeneinheit (Hauswand)' },
  P: { x: 49.5, y: 35.5, objekt: 'Küchenzeile' },
  Q: { x: 67.1, y: 53.9, objekt: 'Sofa' },
  R: { x: 77.7, y: 45.3, objekt: 'Bett' },
  // Fester Anker für die Außentemperatur (Bauplan P-433-2 E1): freier Himmel links oben.
  HIMMEL: { x: 14, y: 8, objekt: 'Himmel' },
}

/** Kachelreihe im Bild: oben (über dem Himmel) oder unten (Vorplatz). */
export type Reihe = 'oben' | 'unten'

/**
 * In welcher Reihe die Kacheln eines Ankers stehen (P-433-2d, Gernot 26.10.2026): **Technik oben, Räume unten** —
 * nach der Art des Objekts, nicht nach seiner Lage im Bild.
 *  - oben (Technik): Himmel (Außentemperatur), die Geräte-Objekte A/B/C/F/O, Pufferspeicher mit Heizstab D
 *    (Zusatzheizung), Warmwasserspeicher E, Hydraulikmodul G (dort «Vorlauf · Rücklauf»/«Wärme heute» ohne
 *    Stammdatum — Entscheid Gernot 26.10. zu H1), Zählerreihe I (Strom heute);
 *  - unten (Räume): die Heizkreis-Objekte K (Fußbodenheizung) und J (Heizkörper) — dort stehen «Vorlauf · Rücklauf»
 *    und «Wärme heute», wenn das Stammdatum `vorlauftemperatur` die Heizflächen nennt —, und die Klima-Innengeräte
 *    L/M/N samt Gruppe «Innengeräte (n)».
 * H, P, Q, R tragen keine Kachel und haben keinen Eintrag; für sie (und jeden künftigen Anker ohne Eintrag) gilt die
 * Bildlage, siehe {@link ankerReihe}.
 */
export const ANKER_REIHE: Partial<Record<AnkerId, Reihe>> = {
  HIMMEL: 'oben', A: 'oben', B: 'oben', C: 'oben', D: 'oben', E: 'oben', F: 'oben', G: 'oben', I: 'oben', O: 'oben',
  J: 'unten', K: 'unten', L: 'unten', M: 'unten', N: 'unten',
}

/** Reihe nach der Bildlage: Anker-y < 50 % ⇒ oben. Liegen alle Kacheln so, kreuzt keine Linie der oberen eine der
 *  unteren Reihe (obere Linien enden über, untere unter der Bildmitte) — das Ziel des Reihenwechsels. */
export function bildReihe(id: AnkerId): Reihe {
  return WAERME_ANKER[id].y < 50 ? 'oben' : 'unten'
}

/** Reihe eines Ankers — aus {@link ANKER_REIHE}; ohne Eintrag nach der Bildlage ({@link bildReihe}, Rückfall). */
export function ankerReihe(id: AnkerId): Reihe {
  return ANKER_REIHE[id] ?? bildReihe(id)
}

/**
 * Anker der zwei Einzelplätze neben dem Haus (P-433-2e, Gernot 26.10.2026) — wie Netz (links) und Speicher (rechts)
 * im Energiefluss, nur am Desktop:
 *  - **links** die Gerätekachel der Wärmepumpe an der Außeneinheit A, am WP-Schrank C oder an der Warmwasser-WP F —
 *    **die Reihenfolge der Liste ist die Rangfolge** der Kandidaten (A vor C vor F, Entscheid Master 26.10.2026);
 *  - **rechts** die Gerätekachel an der Klima-Außeneinheit O.
 *
 * ⚠ **Lage gemessen am Bild v4 (Rasterkarte 2 %, Gegenprüfung 26.10.2026); neues Bild = neue Messung.** Das Haus
 * reicht über x 14–92 %, y 9–78 %. Links ist das Bild frei für x < 14 % bis y 44 % (die Wandecke des Technikraums
 * läuft diagonal von (14 %, 34 %) nach (32 %, 22 %) — die Kachel überdeckt sie, 14–18 % Objektpixel, durchscheinend
 * wie im Energiefluss); der Platz endet bei 45 % der Bildhöhe, über der Außeneinheit A (y 50–66 %). Rechts ist das
 * Bild frei für x > 92 % bis y 54 % und ab y 60 % für x > 80 %; der Platz beginnt bei 58 % der Bildhöhe, unter der
 * Klima-Außeneinheit O (y 45–50 %). Die Zahlen 45 % und 58 % stehen in `ueberblickLayout.ts` (Geometrie dort).
 */
export const PLATZ_ANKER: Readonly<Record<'links' | 'rechts', readonly AnkerId[]>> = {
  links: ['A', 'C', 'F'],
  rechts: ['O'],
}
