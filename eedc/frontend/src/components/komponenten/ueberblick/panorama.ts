/**
 * Panorama-Deskriptor des Hub-Überblicks (P-433-2b Sitzung 1a, E0; Gegenentwurf G2/W6).
 *
 * Ein Überblick-Schaubild ist **ein Bild mit einer Anker-Karte und Regeln, wo Kacheln stehen**. Was davon zum Bild
 * gehört, steht in einem {@link PanoramaDef} je Bild (Wärme/Klima: `WAERME_PANORAMA_DEF` in `waermePanoramaAnker.ts`);
 * Layout (`ueberblickLayout.ts`) und Zeichnung (`UeberblickSchaubild.tsx`) lesen nur den Deskriptor und kennen kein Bild.
 *
 * **Vertrag (G2):**
 *  - `bilder {tag, nacht}` · `aria` — die zwei bildgleichen Panoramen und ihr Name für Screenreader;
 *  - `anker` — x/y in Prozent des Bildes und das Objekt, je Anker-ID;
 *  - `reihe` — Reihe je Anker (oben/unten nach der Art des Objekts); ohne Eintrag gilt die Bildlage `anker[id].y < 50`
 *    ({@link ankerReihe}, {@link bildReihe}) — sie ist auch das Ziel des Reihenwechsels bei Kreuzung;
 *  - `plaetze {links, rechts}` — die Anker, deren Gerätekachel am Desktop im Einzelplatz neben dem Bild steht; die
 *    Reihenfolge der Liste ist die Rangfolge; `platzLinksBis` / `platzRechtsAb` — Unterkante des linken bzw. Oberkante
 *    des rechten Platzes als Anteil der Bildhöhe (am Bild gemessen; neues Bild = neue Messung);
 *  - `wertRang` — Rang der Wert-Kacheln je Anker für «Weitere (n)» (kleiner = bleibt länger einzeln; ohne Eintrag 9);
 *  - `gruppenName(gruppe, anker)` — Name einer Gruppenkachel; `farbeWeitere` — Farbe der Gruppe «Weitere (n)»;
 *  - `ankerRestgruppe` (optional, Halt H1 der Sitzung 1a) — Anker der Restgruppe «Innengeräte (n−3)» ab dem vierten
 *    Innengerät einer Reihe; ohne Eintrag der Anker des vierten Innengeräts.
 *
 * **Bildmaß:** alle Überblick-Panoramen sind 1312 × 816 (Bauplan B3: Maßstab k = 1312 / W) — {@link PANORAMA_BREITE},
 * {@link PANORAMA_HOEHE}; kein Feld des Deskriptors.
 */

/** Bildbreite aller Überblick-Panoramen (Bildeinheiten). */
export const PANORAMA_BREITE = 1312
/** Bildhöhe aller Überblick-Panoramen (Bildeinheiten). */
export const PANORAMA_HOEHE = 816

/** Anker-ID eines Objekts im Bild — welche es gibt, sagt der Deskriptor des Bildes. */
export type AnkerId = string

/** Art einer Kachel — bestimmt Gruppierung und Rang im Layout. */
export type KachelArt = 'geraet' | 'innengeraet' | 'wert'

/** Art einer Gruppenkachel. */
export type GruppenArt = 'geraete' | 'innengeraete' | 'weitere'

/** Kachelreihe im Bild: oben (über dem Himmel) oder unten (Vorplatz). */
export type Reihe = 'oben' | 'unten'

export interface Anker {
  /** Prozent der Bildbreite. */
  x: number
  /** Prozent der Bildhöhe. */
  y: number
  objekt: string
}

/** Der Deskriptor eines Überblick-Panoramas (Vertrag G2, siehe Kopf). */
export interface PanoramaDef {
  bilder: { readonly tag: string; readonly nacht: string }
  aria: string
  anker: Record<AnkerId, Anker>
  reihe: Partial<Record<AnkerId, Reihe>>
  plaetze: Readonly<Record<'links' | 'rechts', readonly AnkerId[]>>
  platzLinksBis: number
  platzRechtsAb: number
  wertRang: Readonly<Record<AnkerId, number>>
  gruppenName: (gruppe: GruppenArt, anker: AnkerId | null) => string
  farbeWeitere: string
  ankerRestgruppe?: AnkerId
}

/** Reihe nach der Bildlage: Anker-y < 50 % ⇒ oben. Liegen alle Kacheln so, kreuzt keine Linie der oberen eine der
 *  unteren Reihe (obere Linien enden über, untere unter der Bildmitte) — das Ziel des Reihenwechsels. */
export function bildReihe(p: Pick<PanoramaDef, 'anker'>, id: AnkerId): Reihe {
  return p.anker[id].y < 50 ? 'oben' : 'unten'
}

/** Reihe eines Ankers — aus `reihe`; ohne Eintrag nach der Bildlage ({@link bildReihe}, Rückfall). */
export function ankerReihe(p: Pick<PanoramaDef, 'anker' | 'reihe'>, id: AnkerId): Reihe {
  return p.reihe[id] ?? bildReihe(p, id)
}
