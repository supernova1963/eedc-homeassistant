/**
 * Layout der Kacheln auf dem Panorama (P-433-2 E1, Gegenentwurf W1–W3/Ü3/Ü4) —
 * reine Funktion, ohne React.
 *
 * **Maßstab (E-P2-6): wie im Energiefluss.** Das Bild ist 1312 Einheiten breit;
 * die Kachel wird mit `k = 1312 / W` gezeichnet, `W` die Zeichenbreite, die der
 * Energiefluss bei derselben Spaltenbreite hätte (Handy 360/450, sonst 600).
 * Damit sind Kachel und Schrift bei gleicher Spalte **pixelgleich** mit dem
 * Energiefluss — „Handy 1:1" heißt dieselbe Pixelgröße, nicht dieselbe Zahl.
 *
 * **Reihen:** Anker-y < 50 % ⇒ obere Reihe (über dem Himmel), sonst untere
 * (Vorplatz). Reihen-y aus der Geometrie — Stapel-Optik und Fokusrahmen einer
 * Gruppe dürfen nicht über den Bildrand (Ü3).
 *
 * **Kapazität je Reihe:** `kapazitaet(W, nodeW)` aus dem Energiefluss-Layout,
 * `dims = computeDims(max(oben, unten))`. Gruppiert wird in dieser Reihenfolge:
 *   1. immer: Geräte am selben Anker («Wärmepumpen (n)», E-P2-2) und das vierte
 *      und jedes weitere Innengerät («Innengeräte (n−3)» an N);
 *   2. passt die Reihe nicht: alle Innengeräte der Reihe in «Innengeräte (n)»;
 *   3. passt sie dann noch nicht: der Rest nach Rang in «Weitere (n)» (Geräte
 *      vor Innengeräten vor Werten; Werte: Warmwasser, Strom heute, Vorlauf · Rücklauf,
 *      Zusatzheizung, Außen — in «Weitere» wandern zuerst Außen, dann Zusatzheizung,
 *      dann Vorlauf · Rücklauf; P-433-3 S1).
 * Wert-Kacheln bilden nie eine eigene Gruppe (Ü6) — sie können nur in
 * «Weitere» landen.
 *
 * **x-Lage (W1):** Kachel-x = Anker-x, geklemmt auf den Rand, dann in
 * Anker-x-Reihenfolge 1-D auseinandergeschoben, bis der Abstand
 * `ABSTAND_REIHE·k` hält — wie `ueberlappungsfrei` im Energiefluss, kein
 * Gleichverteilen. Danach die **Kreuzungsprobe**: schneiden sich zwei Linien
 * einer Reihe, tauschen die beiden Nachbarn ihre Plätze (höchstens n Durchläufe).
 */
import { ABSTAND_REIHE, computeDims, kapazitaet, type LayoutDims } from '../../live/energieFlussLayout'
import { STAPEL_VERSATZ } from '../../live/EnergieFlussKachel'
import { PANORAMA_BREITE, PANORAMA_HOEHE, WAERME_ANKER, type AnkerId } from './waermePanoramaAnker'
import { ANKER_VORLAUF_ALLE, ANKER_ZUSATZHEIZUNG, type KachelArt } from './kachelAnker'

/** Was das Layout von einer Kachel wissen muss. */
export interface LayoutKachel {
  id: string
  art: KachelArt
  anker: AnkerId
}

export type GruppenArt = 'geraete' | 'innengeraete' | 'weitere'

/** Ein Platz in einer Reihe: eine Kachel oder eine Gruppe. */
export interface Platz<T extends LayoutKachel = LayoutKachel> {
  /** Stabiler Schlüssel: Kachel-ID oder `grp-…`. */
  key: string
  mitglieder: T[]
  /** `null` = Einzelkachel. */
  gruppe: GruppenArt | null
  /** Anker der Linie — `null` bei «Weitere» (gemischte Objekte, keine Linie). */
  anker: AnkerId | null
  /** Ankerpunkt in Bildeinheiten (auch bei «Weitere»: Mittel der Mitglieder, nur zum Ordnen). */
  ax: number
  ay: number
  /** Kachelmitte in Bildeinheiten. */
  x: number
  y: number
  reihe: 'oben' | 'unten'
  /** Linie Kachelkante → Objekt; `null`, wenn der Anker in der Kachel liegt oder es keinen gibt. */
  linie: { x1: number; y1: number; x2: number; y2: number } | null
}

export interface UeberblickLayout<T extends LayoutKachel = LayoutKachel> {
  /** Zeichenbreite des Energieflusses bei dieser Spalte (360 · 450 · 600). */
  W: number
  /** Kachel-Maßstab im Bild: 1312 / W. */
  k: number
  dims: LayoutDims
  geraet: 'desktop' | 'handy'
  oben: Platz<T>[]
  unten: Platz<T>[]
  /** Beschriftung am Bildschirm in px (Probe gegen die Energiefluss-Mindestschrift). */
  schriftPx: number
}

/** Rang innerhalb einer Reihe: kleiner = bleibt zuletzt als Einzelkachel stehen.
 *  ⚠ Der Rang entscheidet NUR, wer zuerst nach «Weitere» wandert — die Reihenfolge in der Reihe ist Anker-x
 *  mit Nachbartausch ({@link verteileX}, {@link entkreuze}). «Vorlauf · Rücklauf» hat seit S2-8 drei mögliche
 *  Objekte (G · K · J), alle mit demselben Rang. */
const WERT_RANG: Record<string, number> = {
  E: 0, I: 1, ...Object.fromEntries(ANKER_VORLAUF_ALLE.map((a) => [a, 2])), [ANKER_ZUSATZHEIZUNG]: 3, HIMMEL: 4,
}
function rang(p: Platz): number {
  if (p.gruppe === 'geraete' || p.mitglieder[0].art === 'geraet') return 0
  if (p.gruppe === 'innengeraete' || p.mitglieder[0].art === 'innengeraet') return 1
  return 2 + (WERT_RANG[p.anker ?? ''] ?? 9) / 10
}

/** Energiefluss-Zeichenbreite für die Spalte (E-P2-6). */
export function zeichenbreite(ctr: number): number {
  if (ctr < 500) return ctr < 375 ? 360 : 450
  return 600
}

function ankerPunkt(id: AnkerId): { ax: number; ay: number } {
  const a = WAERME_ANKER[id]
  return { ax: (a.x / 100) * PANORAMA_BREITE, ay: (a.y / 100) * PANORAMA_HOEHE }
}

function platzAus<T extends LayoutKachel>(mitglieder: T[], gruppe: GruppenArt | null, anker: AnkerId | null, reihe: 'oben' | 'unten', key: string): Platz<T> {
  const punkte = mitglieder.map((m) => ankerPunkt(m.anker))
  const { ax, ay } = anker
    ? ankerPunkt(anker)
    : { ax: punkte.reduce((s, p) => s + p.ax, 0) / punkte.length, ay: punkte.reduce((s, p) => s + p.ay, 0) / punkte.length }
  return { key, mitglieder, gruppe, anker, ax, ay, x: ax, y: 0, reihe, linie: null }
}

/** Schritt 1: immer gruppieren — gleiche Geräte-Anker, Innengeräte ab dem vierten. */
function grundgruppen<T extends LayoutKachel>(kacheln: T[], reihe: 'oben' | 'unten'): Platz<T>[] {
  const plaetze: Platz<T>[] = []
  const geraeteJeAnker = new Map<AnkerId, T[]>()
  const innen: T[] = []
  for (const k of kacheln) {
    if (k.art === 'geraet') geraeteJeAnker.set(k.anker, [...(geraeteJeAnker.get(k.anker) ?? []), k])
    else if (k.art === 'innengeraet') innen.push(k)
    else plaetze.push(platzAus([k], null, k.anker, reihe, k.id))
  }
  for (const [anker, gs] of geraeteJeAnker) {
    plaetze.push(gs.length > 1
      ? platzAus(gs, 'geraete', anker, reihe, `grp-geraete-${anker}`)
      : platzAus(gs, null, anker, reihe, gs[0].id))
  }
  const einzeln = innen.slice(0, 3)
  einzeln.forEach((k) => plaetze.push(platzAus([k], null, k.anker, reihe, k.id)))
  if (innen.length > 3) plaetze.push(platzAus(innen.slice(3), 'innengeraete', 'N', reihe, 'grp-innengeraete-rest'))
  return plaetze
}

/** Passt eine Reihe mit `n` Kacheln in die Zeichenbreite `W` (Größe nach `computeDims(n)`)? */
function passt(W: number, n: number): boolean {
  return n <= kapazitaet(W, computeDims(n).nodeW)
}

/** Schritte 2 und 3: bis die Reihe in `W` passt. */
function aufKapazitaet<T extends LayoutKachel>(plaetze: Platz<T>[], W: number, reihe: 'oben' | 'unten'): Platz<T>[] {
  if (passt(W, plaetze.length)) return plaetze
  // 2. alle Innengeräte der Reihe in eine Gruppe.
  const innen = plaetze.filter((p) => p.gruppe === 'innengeraete' || p.mitglieder[0].art === 'innengeraet')
  let cur = plaetze
  if (innen.length > 1) {
    const mitglieder = innen.flatMap((p) => p.mitglieder)
    cur = [
      ...plaetze.filter((p) => !innen.includes(p)),
      platzAus(mitglieder, 'innengeraete', mitglieder[0].anker, reihe, 'grp-innengeraete'),
    ]
  }
  if (passt(W, cur.length)) return cur
  // 3. Rest nach Rang in «Weitere (n)».
  let ziel = cur.length - 1
  while (ziel > 1 && !passt(W, ziel)) ziel--
  const geordnet = [...cur].sort((a, b) => rang(a) - rang(b) || a.ax - b.ax)
  const bleibt = geordnet.slice(0, ziel - 1)
  const rest = geordnet.slice(ziel - 1).flatMap((p) => p.mitglieder)
  return [...bleibt, platzAus(rest, 'weitere', null, reihe, 'grp-weitere')]
}

/** x-Lage: Anker-x, geklemmt, 1-D-Schub auf Mindestabstand (W1). */
function verteileX(plaetze: Platz[], dims: LayoutDims, k: number): void {
  if (plaetze.length === 0) return
  plaetze.sort((a, b) => a.ax - b.ax)
  const rand = (dims.nodeW / 2 + 15) * k
  const lo = rand
  const hi = PANORAMA_BREITE - rand
  const schritt = (dims.nodeW + ABSTAND_REIHE) * k
  plaetze.forEach((p) => { p.x = Math.min(Math.max(p.ax, lo), hi) })
  for (let i = 1; i < plaetze.length; i++) plaetze[i].x = Math.max(plaetze[i].x, plaetze[i - 1].x + schritt)
  const n = plaetze.length
  if (plaetze[n - 1].x > hi) {
    plaetze[n - 1].x = hi
    for (let i = n - 2; i >= 0; i--) plaetze[i].x = Math.min(plaetze[i].x, plaetze[i + 1].x - schritt)
  }
}

/** Reihen-y aus der Geometrie (Ü3): Kachelhälfte + Stapel + Fokusrahmen, plus 2 Einheiten Luft. */
export function reihenY(dims: LayoutDims, k: number): { oben: number; unten: number } {
  const abstand = (dims.nodeH / 2 + STAPEL_VERSATZ + 3) * k + 2
  return { oben: abstand, unten: PANORAMA_HOEHE - abstand }
}

function setzeLinie(p: Platz, dims: LayoutDims, k: number): void {
  if (!p.anker) { p.linie = null; return }
  const halbH = (dims.nodeH / 2) * k
  const kante = p.reihe === 'oben' ? p.y + halbH : p.y - halbH
  const zeigtWeg = p.reihe === 'oben' ? p.ay > kante : p.ay < kante
  p.linie = zeigtWeg ? { x1: p.x, y1: kante, x2: p.ax, y2: p.ay } : null
}

type Segment = { x1: number; y1: number; x2: number; y2: number }

/** Echter Schnitt zweier Strecken (Berührung an Endpunkten zählt nicht). */
export function schneiden(a: Segment, b: Segment): boolean {
  const kreuz = (ox: number, oy: number, px: number, py: number, qx: number, qy: number) =>
    (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
  const d1 = kreuz(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1)
  const d2 = kreuz(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2)
  const d3 = kreuz(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1)
  const d4 = kreuz(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2)
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
}

/** Gibt es in der Reihe zwei Linien, die sich schneiden? */
export function hatKreuzung(plaetze: Platz[]): boolean {
  const l = plaetze.map((p) => p.linie).filter((x): x is Segment => x != null)
  for (let i = 0; i < l.length; i++) for (let j = i + 1; j < l.length; j++) if (schneiden(l[i], l[j])) return true
  return false
}

/** Kreuzungsprobe mit Nachbartausch (W1): höchstens n Durchläufe. */
function entkreuze(plaetze: Platz[], dims: LayoutDims, k: number): void {
  for (let lauf = 0; lauf < plaetze.length; lauf++) {
    let getauscht = false
    for (let i = 0; i + 1 < plaetze.length; i++) {
      const a = plaetze[i]
      const b = plaetze[i + 1]
      if (!a.linie || !b.linie || !schneiden(a.linie, b.linie)) continue
      ;[a.x, b.x] = [b.x, a.x]
      setzeLinie(a, dims, k)
      setzeLinie(b, dims, k)
      ;[plaetze[i], plaetze[i + 1]] = [b, a]
      getauscht = true
    }
    if (!getauscht) return
  }
}

/**
 * Das Layout für eine Spaltenbreite `ctr` (px).
 */
export function layoutUeberblick<T extends LayoutKachel>(kacheln: T[], ctr: number): UeberblickLayout<T> {
  const W = zeichenbreite(ctr)
  const k = PANORAMA_BREITE / W
  const istOben = (t: T) => WAERME_ANKER[t.anker].y < 50
  const oben = aufKapazitaet(grundgruppen(kacheln.filter(istOben), 'oben'), W, 'oben')
  const unten = aufKapazitaet(grundgruppen(kacheln.filter((t) => !istOben(t)), 'unten'), W, 'unten')
  const dims = computeDims(Math.max(oben.length, unten.length, 1))
  const ry = reihenY(dims, k)
  for (const [reihe, y] of [[oben, ry.oben], [unten, ry.unten]] as const) {
    verteileX(reihe, dims, k)
    reihe.forEach((p) => { p.y = y; setzeLinie(p, dims, k) })
    entkreuze(reihe, dims, k)
  }
  return {
    W, k, dims, geraet: ctr < 500 ? 'handy' : 'desktop', oben, unten,
    schriftPx: dims.labelFontSize * ctr / W,
  }
}
