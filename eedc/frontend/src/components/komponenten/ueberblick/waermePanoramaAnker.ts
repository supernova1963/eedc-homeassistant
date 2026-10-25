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
