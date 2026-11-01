/**
 * Anker-Karten der zwei Szenen der E-Mobilität (P-433-2b S1b, Bauplan Fassung 2 §9; Entscheid Gernot 1.11.2026,
 * E-2b-1 neu: zwei Szenen statt eines Panoramas).
 *
 * ⚠ **Gemessen am Bild 1.11.2026 (Bild-Brief `bild-brief-emob-szenen.md` §10, 5-%-Raster); neues Bild = neue Messung.**
 * Die Werte sind x/y in Prozent des Bildes (1312 × 816) und gelten für Tag- und Nachtbild gleich — beide Paare sind
 * bildgleich erzeugt (Versatz 0/0), das ist die Voraussetzung dieser Tabellen.
 *
 * **Die Szene gehört dem gewählten Gerät** (E-2b-22): seine Werte stehen an den Objekten. Weitere Geräte des Typs
 * erreicht der Selektor der Seite — die Szenen haben keinen Nebenanker (B/W entfallen, Gernot 1.11.), `plaetze.rechts`
 * ist leer. Welcher Wert an welchem Objekt hängt, entscheidet `emobKachelAnker.ts`.
 *
 * **Szene «Ladepunkt»** (Wallbox-Seite): Blick in die offene Garage — Wandbox A an der Rückwand (Platz links, ihre
 * Gerätekachel), Zählerkasten Z an der Hauswand («Ladung heute · PV-Anteil»), Stecker S am Heck («Sitzung»), Auto F
 * (Fahrzeugkachel des angesteckten Autos), HIMMEL Reserve an der Hauswand (keine Kachel, E-2b-28). S und F liegen im
 * Bild über der Mitte, stehen aber **ausdrücklich unten** (§9): die Linien laufen vom Vorplatz hinauf, über ihnen bleibt
 * die obere Reihe frei für A und Z.
 *
 * **Szene «Fahrzeug»** (E-Auto-Seite): das durchscheinende Auto vor dem Haus (E-2b-27) — Säulen-Wallbox L (Platz links,
 * Gerätekachel «Laden»; die Linie hängt an der Säule, nicht am Port: kurz und waagerecht), Cockpit C («Reichweite»),
 * Terrasse H («Standort»), Akku B im Unterboden («Ladestand» mit Pegel), Vorderrad R («Gefahren heute»), HIMMEL Reserve.
 *
 * **Platzgrenzen** (§10): links frei bis 45 % der Bildhöhe (Ladepunkt: Garagen-Außenwand; Fahrzeug: Glastür/Beton), rechts
 * ungenutzt (58 %, der Wert hält den Vertrag).
 */
import { KATEGORIE_FARBEN } from '../../../lib'
import type { Anker, GruppenArt, PanoramaDef, Reihe } from './panorama'

// ── Szene «Ladepunkt» ───────────────────────────────────────────────────────

export const LADEPUNKT_PANORAMA = {
  tag: './backgrounds/emob-ladepunkt-tag.webp',
  nacht: './backgrounds/emob-ladepunkt-nacht.webp',
} as const

/** Die Anker-IDs der Szene «Ladepunkt» (eingeengt; der Deskriptor-Vertrag kennt nur `string`). */
export type LadepunktAnkerId = 'A' | 'Z' | 'S' | 'F' | 'HIMMEL'

export const LADEPUNKT_ANKER: Record<LadepunktAnkerId, Anker> = {
  A: { x: 54.0, y: 33.0, objekt: 'Wandbox an der Garagen-Rückwand (LED)' },
  Z: { x: 64.0, y: 33.0, objekt: 'Zählerkasten an der Hauswand neben der Garage' },
  S: { x: 47.6, y: 42.3, objekt: 'Stecker am Auto (rechtes Heck)' },
  F: { x: 33.5, y: 44.0, objekt: 'Auto, Dachmitte' },
  // Reserve (E-2b-28): keine Kachel.
  HIMMEL: { x: 85, y: 10, objekt: 'Hauswand rechts oben (Reserve)' },
}

/** Reihen der Szene «Ladepunkt» (§9): A, Z, HIMMEL oben; **S und F ausdrücklich unten** (Bildlage wäre oben). */
export const LADEPUNKT_REIHE: Readonly<Record<LadepunktAnkerId, Reihe>> = {
  A: 'oben', Z: 'oben', HIMMEL: 'oben', S: 'unten', F: 'unten',
}

/** Gruppennamen: Autos am Auto-Objekt F heißen «E-Autos», die gemischte Gruppe «Weitere». */
function ladepunktGruppenName(gruppe: GruppenArt, anker: string | null): string {
  return gruppe === 'geraete' && anker === 'F' ? 'E-Autos' : 'Weitere'
}

/**
 * Der Deskriptor der Szene «Ladepunkt» (Vertrag `panorama.ts`).
 *  - Platz links: die Gerätekachel der gewählten Wallbox an A; rechts keiner (B entfällt, §9);
 *  - Wert-Rang für «Weitere (n)»: Ladung heute Z 0 · Sitzung S 1 (in «Weitere» wandert zuerst die Sitzung);
 *    das erste Auto an F ist eine Wert-Kachel mit Rang 2 (siehe `emobKachelAnker.ts`, `ladepunktFahrzeuge`);
 *  - Farbe der Gruppe «Weitere»: Rollenfarbe Wallbox.
 */
export const LADEPUNKT_PANORAMA_DEF: PanoramaDef = {
  bilder: LADEPUNKT_PANORAMA,
  aria: 'Schaubild Ladepunkt',
  anker: LADEPUNKT_ANKER,
  reihe: LADEPUNKT_REIHE,
  plaetze: { links: ['A'], rechts: [] },
  platzLinksBis: 0.45,
  platzRechtsAb: 0.58,
  wertRang: { Z: 0, S: 1, F: 2 },
  gruppenName: ladepunktGruppenName,
  farbeWeitere: KATEGORIE_FARBEN.wallbox,
}

// ── Szene «Fahrzeug» ────────────────────────────────────────────────────────

export const FAHRZEUG_PANORAMA = {
  tag: './backgrounds/emob-fahrzeug-tag.webp',
  nacht: './backgrounds/emob-fahrzeug-nacht.webp',
} as const

/** Die Anker-IDs der Szene «Fahrzeug». */
export type FahrzeugAnkerId = 'L' | 'C' | 'H' | 'B' | 'R' | 'HIMMEL'

export const FAHRZEUG_ANKER: Record<FahrzeugAnkerId, Anker> = {
  L: { x: 25.5, y: 42.0, objekt: 'Säulen-Wallbox links vom Auto' },
  C: { x: 52.0, y: 48.0, objekt: 'Cockpit/Lenkrad durch die Scheibe' },
  H: { x: 38.0, y: 24.0, objekt: 'Terrasse vor der Glastür' },
  B: { x: 64.0, y: 57.5, objekt: 'Akku-Platte im Unterboden' },
  R: { x: 54.0, y: 73.0, objekt: 'Vorderrad' },
  // Reserve (E-2b-28): keine Kachel.
  HIMMEL: { x: 85, y: 8, objekt: 'Hauswand rechts oben (Reserve)' },
}

/** Reihen der Szene «Fahrzeug» (§9, §2): H, C, HIMMEL oben; B, R unten; L (Platz links) am Handy unten (§2). */
export const FAHRZEUG_REIHE: Readonly<Record<FahrzeugAnkerId, Reihe>> = {
  H: 'oben', C: 'oben', HIMMEL: 'oben', B: 'unten', R: 'unten', L: 'unten',
}

/**
 * Der Deskriptor der Szene «Fahrzeug» (Vertrag `panorama.ts`).
 *  - Platz links: die Gerätekachel «Laden» des gewählten Autos an der Säule L; rechts keiner (W entfällt, §9);
 *  - Wert-Rang für «Weitere (n)»: Ladestand B 0 · Gefahren R 1 · Reichweite C 2 · Standort H 3 (in «Weitere» wandern
 *    zuerst Standort, dann Reichweite);
 *  - Gruppenname nur «Weitere» (eine Szene, ein Auto); Farbe Rollenfarbe E-Auto.
 */
export const FAHRZEUG_PANORAMA_DEF: PanoramaDef = {
  bilder: FAHRZEUG_PANORAMA,
  aria: 'Schaubild Fahrzeug',
  anker: FAHRZEUG_ANKER,
  reihe: FAHRZEUG_REIHE,
  plaetze: { links: ['L'], rechts: [] },
  platzLinksBis: 0.45,
  platzRechtsAb: 0.58,
  wertRang: { B: 0, R: 1, C: 2, H: 3 },
  gruppenName: () => 'Weitere',
  farbeWeitere: KATEGORIE_FARBEN.eauto,
}

/** Der Deskriptor der Szene eines Typs — Wallbox «Ladepunkt», E-Auto «Fahrzeug». */
export function emobPanorama(typ: string): PanoramaDef {
  return typ === 'wallbox' ? LADEPUNKT_PANORAMA_DEF : FAHRZEUG_PANORAMA_DEF
}
