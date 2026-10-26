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
 * **Reihen (P-433-2d): Technik oben, Räume unten** — die Reihe kommt aus der
 * Zuordnung Anker ⇒ Reihe neben der Anker-Karte (`ankerReihe`, `ANKER_REIHE`):
 * oben Himmel, Geräte, Speicher, Zählerreihe; unten Heizkreise (Vorlauf · Rücklauf,
 * Wärme heute an K/J) und Innengeräte. Nur ein Anker ohne Eintrag fällt auf die
 * Bildlage zurück (Anker-y < 50 % ⇒ oben). Reihen-y aus der Geometrie — Stapel-Optik
 * und Fokusrahmen einer Gruppe dürfen nicht über den Bildrand (Ü3).
 *
 * **Reihenwechsel bei Kreuzung (Entscheid Gernot 26.10.2026, H1):** kreuzt nach der
 * Entkreuzung je Reihe eine Linie der oberen Reihe eine der unteren, wechselt eine
 * beteiligte Kachel, deren Reihe nicht ihrer Bildlage entspricht, in die Reihe ihrer
 * Bildlage, und das Layout wird neu gerechnet (Kapazität, «Weitere» inklusive).
 * Gewählt wird der Platz mit dem größten Abstand Anker-y ↔ Reihen-y, bei Gleichstand
 * der kleinere Schlüssel. Jeder Wechsel ist endgültig, also höchstens n Läufe; im
 * schlimmsten Fall steht jede Kachel in der Reihe ihrer Bildlage, und dort kreuzt
 * keine Linie die andere Reihe (obere Linien enden über, untere unter der Bildmitte).
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
 *
 * **Zwei Plätze wie Netz und Speicher (P-433-2e, Gernot 26.10.2026), nur Desktop:**
 * neben den zwei Reihen stehen zwei feste Einzelplätze — links die Gerätekachel der
 * Wärmepumpe am ersten belegten Anker in der Rangfolge A → C → F (weitere Geräte am
 * selben Anker mit ihr als «Wärmepumpen (n)»), rechts die Gerätekachel an der Klima-Außeneinheit O
 * (`PLATZ_ANKER`). Die Plätze werden **vor** den Reihen aus der Kachelliste genommen;
 * die Reihen rechnet derselbe 2d-Lauf ({@link layoutReihen}), `dims` aus den Reihen
 * (die Plätze zählen nicht). Lage: x am Bildrand wie die äußerste Reihenkachel, y =
 * Anker-y geklemmt — links zwischen Unterkante der oberen Reihe + Abstand und 45 %
 * der Bildhöhe, rechts zwischen 58 % und Oberkante der unteren Reihe − Abstand.
 * Ist der rechte Platz belegt, endet die untere Reihe eine Kachelbreite früher
 * (Kapazität − 1). Die Linie läuft von der dem Anker nächsten Kante (Anker unter der
 * Kachel ⇒ Unterkante, über ihr ⇒ Oberkante, sonst die zugewandte Seitenkante; Anker
 * in der Kachel ⇒ keine Linie). **Rückfall:** schneidet die Linie eines Platzes eine
 * Reihenlinie (gezeichnet oder Mitte → Anker, wie beim Reihenwechsel) oder trifft eine
 * Reihenlinie bzw. Mitte → Anker-Strecke das Platz-Rechteck, bleibt die Kachel in
 * ihrer Reihe und die Reihen werden neu gerechnet; links wird dann der nächste
 * Anker-Rang versucht (höchstens drei Versuche, je ein Reihenlauf), bevor der Platz
 * leer bleibt — ohne Platz ist es das 2d-Layout. Handy (< 500 px): keine Plätze, das
 * Layout ist das 2d-Layout.
 */
import { ABSTAND_REIHE, computeDims, kapazitaet, type LayoutDims } from '../../live/energieFlussLayout'
import { STAPEL_VERSATZ } from '../../live/EnergieFlussKachel'
import { PANORAMA_BREITE, PANORAMA_HOEHE, PLATZ_ANKER, WAERME_ANKER, ankerReihe, bildReihe, type AnkerId, type Reihe } from './waermePanoramaAnker'
import { ANKER_VORLAUF_ALLE, ANKER_ZUSATZHEIZUNG, type KachelArt } from './kachelAnker'

/** Was das Layout von einer Kachel wissen muss. */
export interface LayoutKachel {
  id: string
  art: KachelArt
  anker: AnkerId
}

export type GruppenArt = 'geraete' | 'innengeraete' | 'weitere'

/** Wo ein Platz steht: in einer der zwei Reihen oder in einem der zwei Einzelplätze neben dem Haus (P-433-2e). */
export type Seite = Reihe | 'links' | 'rechts'

/** Ein Platz in einer Reihe oder neben dem Haus: eine Kachel oder eine Gruppe. */
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
  seite: Seite
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
  /** Einzelplatz links neben dem Haus (Wärmepumpe an A/C/F) — `null` am Handy, ohne solches Gerät oder nach Rückfall. */
  links: Platz<T> | null
  /** Einzelplatz rechts unter der Klima-Außeneinheit (Gerät an O) — `null` am Handy, ohne solches Gerät oder nach Rückfall. */
  rechts: Platz<T> | null
  /** Beschriftung am Bildschirm in px (Probe gegen die Energiefluss-Mindestschrift). */
  schriftPx: number
  /** Kachel-IDs, die wegen einer Kreuzung in die Reihe ihrer Bildlage gewechselt sind (in Wechsel-Reihenfolge). */
  reihenwechsel: string[]
  /** Kachel-IDs, die ihren Einzelplatz wegen einer Kreuzung verloren haben und in ihrer Reihe stehen (je Lauf links vor rechts). */
  rueckfall: string[]
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

function platzAus<T extends LayoutKachel>(mitglieder: T[], gruppe: GruppenArt | null, anker: AnkerId | null, seite: Seite, key: string): Platz<T> {
  const punkte = mitglieder.map((m) => ankerPunkt(m.anker))
  const { ax, ay } = anker
    ? ankerPunkt(anker)
    : { ax: punkte.reduce((s, p) => s + p.ax, 0) / punkte.length, ay: punkte.reduce((s, p) => s + p.ay, 0) / punkte.length }
  return { key, mitglieder, gruppe, anker, ax, ay, x: ax, y: 0, seite, linie: null }
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

/** Passt eine Reihe mit `n` Kacheln in die Zeichenbreite `W` (Größe nach `computeDims(n)`)? `gekuerzt`: die Reihe
 *  endet eine Kachelbreite früher (belegter rechter Platz, P-433-2e) — Kapazität − 1. */
function passtIn(W: number, n: number, gekuerzt = false): boolean {
  const nodeW = computeDims(n).nodeW
  return n <= kapazitaet(gekuerzt ? W - (nodeW + ABSTAND_REIHE) : W, nodeW)
}

/** Schritte 2 und 3: bis die Reihe in `W` passt. */
function aufKapazitaet<T extends LayoutKachel>(plaetze: Platz<T>[], W: number, reihe: 'oben' | 'unten', gekuerzt = false): Platz<T>[] {
  const passt = (n: number) => passtIn(W, n, gekuerzt)
  if (passt(plaetze.length)) return plaetze
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
  if (passt(cur.length)) return cur
  // 3. Rest nach Rang in «Weitere (n)».
  let ziel = cur.length - 1
  while (ziel > 1 && !passt(ziel)) ziel--
  const geordnet = [...cur].sort((a, b) => rang(a) - rang(b) || a.ax - b.ax)
  const bleibt = geordnet.slice(0, ziel - 1)
  const rest = geordnet.slice(ziel - 1).flatMap((p) => p.mitglieder)
  return [...bleibt, platzAus(rest, 'weitere', null, reihe, 'grp-weitere')]
}

/** x-Lage: Anker-x, geklemmt, 1-D-Schub auf Mindestabstand (W1). `gekuerzt`: die Reihe endet eine Kachelbreite
 *  früher (belegter rechter Platz, P-433-2e). */
function verteileX(plaetze: Platz[], dims: LayoutDims, k: number, gekuerzt = false): void {
  if (plaetze.length === 0) return
  plaetze.sort((a, b) => a.ax - b.ax)
  const rand = (dims.nodeW / 2 + 15) * k
  const schritt = (dims.nodeW + ABSTAND_REIHE) * k
  const lo = rand
  const hi = PANORAMA_BREITE - rand - (gekuerzt ? schritt : 0)
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
  const kante = p.seite === 'oben' ? p.y + halbH : p.y - halbH
  const zeigtWeg = p.seite === 'oben' ? p.ay > kante : p.ay < kante
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

/**
 * Kreuzen sich die Linien zweier Plätze aus verschiedenen Reihen (Reihenwechsel, H1)? Geprüft werden die gezeichnete
 * Linie (Kachelkante → Anker) und die Strecke Kachelmitte → Anker — so läuft auch keine Linie unter der Kachel der
 * anderen Reihe hindurch. Nur Plätze mit Linie zählen.
 */
function kreuzenZwischen(a: Platz, b: Platz): boolean {
  if (!a.linie || !b.linie) return false
  const mitte = (p: Platz): Segment => ({ x1: p.x, y1: p.y, x2: p.ax, y2: p.ay })
  return schneiden(a.linie, b.linie) || schneiden(mitte(a), mitte(b))
}

/** Gibt es eine Kreuzung zwischen einer Linie der oberen und einer der unteren Reihe? */
export function hatKreuzungZwischen(oben: Platz[], unten: Platz[]): boolean {
  return oben.some((a) => unten.some((b) => kreuzenZwischen(a, b)))
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
 * Das Layout für eine Spaltenbreite `ctr` (px): zwei Reihen und — am Desktop — die zwei Einzelplätze (P-433-2e).
 */
export function layoutUeberblick<T extends LayoutKachel>(kacheln: T[], ctr: number): UeberblickLayout<T> {
  if (ctr < 500) return { ...layoutReihen(kacheln, ctr), links: null, rechts: null, rueckfall: [] }
  const kandidatenLinks = platzKandidaten(kacheln, PLATZ_ANKER.links)
  const kandidatenRechts = platzKandidaten(kacheln, PLATZ_ANKER.rechts)
  let links = kandidatenLinks.shift() ?? []
  let rechts = kandidatenRechts.shift() ?? []
  const rueckfall: string[] = []
  // Jeder weitere Lauf hat mindestens einen Kandidaten endgültig aufgegeben (links höchstens drei Anker-Ränge, rechts
  // einer); ohne Platz ist es das 2d-Layout, und dort gibt es nichts zu prüfen.
  for (;;) {
    const imPlatz = new Set<T>([...links, ...rechts])
    const reihen = layoutReihen(kacheln.filter((t) => !imPlatz.has(t)), ctr, rechts.length > 0)
    const zeilen = [...reihen.oben, ...reihen.unten]
    const L = links.length ? platzGeometrie(links, 'links', reihen.dims, reihen.k) : null
    const R = rechts.length ? platzGeometrie(rechts, 'rechts', reihen.dims, reihen.k) : null
    const fallL = L != null && platzKollidiert(L, zeilen, reihen.dims, reihen.k)
    const fallR = R != null && platzKollidiert(R, zeilen, reihen.dims, reihen.k)
    if (!fallL && !fallR) return { ...reihen, links: L, rechts: R, rueckfall }
    if (fallL) { rueckfall.push(...links.map((t) => t.id)); links = kandidatenLinks.shift() ?? [] }
    if (fallR) { rueckfall.push(...rechts.map((t) => t.id)); rechts = kandidatenRechts.shift() ?? [] }
  }
}

/**
 * Die Kandidaten eines Einzelplatzes in **fester Anker-Rangfolge** (Reihenfolge von `anker`, links A → C → F;
 * Entscheid Master 26.10.2026 — die Platzwahl hängt nicht von der Listenreihenfolge der Geräte ab): je Anker alle
 * Geräte daran in Listenreihenfolge (mehrere bilden «Wärmepumpen (n)», wie in der Reihe). Fällt ein Kandidat zurück,
 * wird der nächste Rang versucht, bevor der Platz leer bleibt; Geräte, die nicht im Platz stehen, stehen in der Reihe.
 */
function platzKandidaten<T extends LayoutKachel>(kacheln: T[], anker: readonly AnkerId[]): T[][] {
  return anker
    .map((a) => kacheln.filter((t) => t.art === 'geraet' && t.anker === a))
    .filter((gruppe) => gruppe.length > 0)
}

/** Unterkante des linken Platzes in Bildhöhe: über der Außeneinheit A (gemessen am Bild v4, siehe `PLATZ_ANKER`). */
const PLATZ_LINKS_BIS = 0.45
/** Oberkante des rechten Platzes in Bildhöhe: unter der Klima-Außeneinheit O (gemessen am Bild v4, siehe `PLATZ_ANKER`). */
const PLATZ_RECHTS_AB = 0.58

/**
 * Lage und Linie eines Einzelplatzes (P-433-2e): x am Bildrand wie die äußerste Reihenkachel
 * (`(nodeW/2 + 15)·k` vom Rand), y = Anker-y geklemmt — links auf [Unterkante obere Reihe + 12k + nodeH·k/2,
 * 45 % − nodeH·k/2], rechts auf [58 % + nodeH·k/2, Oberkante untere Reihe − 12k − nodeH·k/2].
 */
export function platzGeometrie<T extends LayoutKachel>(mitglieder: T[], seite: 'links' | 'rechts', dims: LayoutDims, k: number): Platz<T> {
  const anker = mitglieder[0].anker
  const p = platzAus(mitglieder, mitglieder.length > 1 ? 'geraete' : null, anker, seite, mitglieder.length > 1 ? `grp-geraete-${anker}` : mitglieder[0].id)
  const ry = reihenY(dims, k)
  const halbH = (dims.nodeH / 2) * k
  const rand = (dims.nodeW / 2 + 15) * k
  const abstand = ABSTAND_REIHE * k
  const [lo, hi] = seite === 'links'
    ? [ry.oben + halbH + abstand + halbH, PLATZ_LINKS_BIS * PANORAMA_HOEHE - halbH]
    : [PLATZ_RECHTS_AB * PANORAMA_HOEHE + halbH, ry.unten - halbH - abstand - halbH]
  p.x = seite === 'links' ? rand : PANORAMA_BREITE - rand
  p.y = Math.min(Math.max(p.ay, lo), hi)
  setzePlatzLinie(p, dims, k)
  return p
}

/** Linie eines Einzelplatzes von der dem Anker nächsten Kante: Anker unter der Kachel ⇒ Unterkante, über ihr ⇒
 *  Oberkante, sonst die zugewandte Seitenkante (am linken Platz die innere, rechte); Anker in der Kachel ⇒ keine Linie. */
function setzePlatzLinie(p: Platz, dims: LayoutDims, k: number): void {
  const halbW = (dims.nodeW / 2) * k
  const halbH = (dims.nodeH / 2) * k
  const ende = { x2: p.ax, y2: p.ay }
  if (!p.anker) p.linie = null
  else if (p.ay > p.y + halbH) p.linie = { x1: p.x, y1: p.y + halbH, ...ende }
  else if (p.ay < p.y - halbH) p.linie = { x1: p.x, y1: p.y - halbH, ...ende }
  else if (p.ax > p.x + halbW) p.linie = { x1: p.x + halbW, y1: p.y, ...ende }
  else if (p.ax < p.x - halbW) p.linie = { x1: p.x - halbW, y1: p.y, ...ende }
  else p.linie = null
}

/** Das Rechteck einer Kachel in Bildeinheiten. */
export function kachelRechteck(p: Platz, dims: LayoutDims, k: number): { x0: number; y0: number; x1: number; y1: number } {
  const halbW = (dims.nodeW / 2) * k
  const halbH = (dims.nodeH / 2) * k
  return { x0: p.x - halbW, y0: p.y - halbH, x1: p.x + halbW, y1: p.y + halbH }
}

/** Läuft die Strecke durch das Innere des Rechtecks (Liang–Barsky; Berührung von Kante oder Ecke zählt nicht)? */
export function trifftRechteck(s: Segment, r: { x0: number; y0: number; x1: number; y1: number }): boolean {
  const dx = s.x2 - s.x1
  const dy = s.y2 - s.y1
  let t0 = 0
  let t1 = 1
  for (const [q, d] of [[s.x1 - r.x0, -dx], [r.x1 - s.x1, dx], [s.y1 - r.y0, -dy], [r.y1 - s.y1, dy]] as const) {
    if (d === 0) { if (q < 0) return false; continue }
    const t = q / d
    if (d < 0) t0 = Math.max(t0, t)
    else t1 = Math.min(t1, t)
    if (t0 > t1) return false
  }
  if (t0 >= t1) return false
  const tm = (t0 + t1) / 2
  const x = s.x1 + tm * dx
  const y = s.y1 + tm * dy
  return x > r.x0 && x < r.x1 && y > r.y0 && y < r.y1
}

/** Mitte → Anker eines Platzes (die Strecke, die auch unter der Kachel verläuft). */
function mitteAnker(p: Platz): Segment {
  return { x1: p.x, y1: p.y, x2: p.ax, y2: p.ay }
}

/**
 * Probe eines Einzelplatzes gegen die Reihen (P-433-2e, E-2e-4): (i) seine Linie schneidet eine Reihenlinie — beide
 * Strecken wie beim Reihenwechsel ({@link kreuzenZwischen}); (ii) eine Reihenlinie oder deren Strecke Mitte → Anker
 * läuft durch das Platz-Rechteck. Nur Reihenplätze mit Linie zählen.
 */
export function platzKollidiert(p: Platz, reihen: Platz[], dims: LayoutDims, k: number): boolean {
  const r = kachelRechteck(p, dims, k)
  return reihen.some((q) => q.linie != null
    && (kreuzenZwischen(p, q) || trifftRechteck(q.linie, r) || trifftRechteck(mitteAnker(q), r)))
}

/**
 * Die zwei Reihen ohne Einzelplätze — das Layout von P-433-2d (Reihenregel, Reihenwechsel bei Kreuzung), unverändert;
 * am Handy ist es das ganze Layout. `untenGekuerzt`: die untere Reihe endet eine Kachelbreite früher (belegter
 * rechter Platz, P-433-2e).
 */
export function layoutReihen<T extends LayoutKachel>(kacheln: T[], ctr: number, untenGekuerzt = false): Omit<UeberblickLayout<T>, 'links' | 'rechts' | 'rueckfall'> {
  const W = zeichenbreite(ctr)
  const k = PANORAMA_BREITE / W
  const gewechselt = new Set<string>()
  const reiheVon = (t: T): Reihe => (gewechselt.has(t.id) ? bildReihe(t.anker) : ankerReihe(t.anker))
  // Höchstens n + 1 Läufe: jeder weitere Lauf hat mindestens eine Kachel endgültig gewechselt.
  for (let lauf = 0; ; lauf++) {
    const l = reihenLayout(kacheln, W, k, reiheVon, untenGekuerzt)
    const platz = lauf <= kacheln.length ? wechselKandidat(l.oben, l.unten, reiheVon) : null
    if (!platz) {
      return {
        W, k, dims: l.dims, geraet: ctr < 500 ? 'handy' : 'desktop', oben: l.oben, unten: l.unten,
        schriftPx: l.dims.labelFontSize * ctr / W, reihenwechsel: [...gewechselt],
      }
    }
    for (const m of platz.mitglieder) if (reiheVon(m) !== bildReihe(m.anker)) gewechselt.add(m.id)
  }
}

/** Ein Lauf: Reihen nach `reiheVon`, Kapazität, x-Lage, Linien, Entkreuzung je Reihe. */
function reihenLayout<T extends LayoutKachel>(kacheln: T[], W: number, k: number, reiheVon: (t: T) => Reihe, untenGekuerzt: boolean) {
  const oben = aufKapazitaet(grundgruppen(kacheln.filter((t) => reiheVon(t) === 'oben'), 'oben'), W, 'oben')
  const unten = aufKapazitaet(grundgruppen(kacheln.filter((t) => reiheVon(t) === 'unten'), 'unten'), W, 'unten', untenGekuerzt)
  const dims = computeDims(Math.max(oben.length, unten.length, 1))
  const ry = reihenY(dims, k)
  for (const [reihe, y, gekuerzt] of [[oben, ry.oben, false], [unten, ry.unten, untenGekuerzt]] as const) {
    verteileX(reihe, dims, k, gekuerzt)
    reihe.forEach((p) => { p.y = y; setzeLinie(p, dims, k) })
    entkreuze(reihe, dims, k)
  }
  return { oben, unten, dims }
}

/**
 * Der Platz, der wegen einer Kreuzung zwischen den Reihen wechselt ({@link kreuzenZwischen}) — oder `null`, wenn
 * keine Linie der oberen eine der unteren Reihe schneidet. Kandidat ist nur ein Platz an einer Kreuzung mit mindestens einem Mitglied außerhalb
 * der Reihe seiner Bildlage (zwei Plätze in ihrer Bildlage kreuzen sich nie); davon der mit dem größten Abstand
 * Anker-y ↔ Reihen-y, bei Gleichstand der kleinere Schlüssel.
 */
function wechselKandidat<T extends LayoutKachel>(oben: Platz<T>[], unten: Platz<T>[], reiheVon: (t: T) => Reihe): Platz<T> | null {
  const beteiligt = new Set<Platz<T>>()
  for (const a of oben) for (const b of unten) {
    if (kreuzenZwischen(a, b)) { beteiligt.add(a); beteiligt.add(b) }
  }
  const kandidaten = [...beteiligt].filter((p) => p.mitglieder.some((m) => reiheVon(m) !== bildReihe(m.anker)))
  kandidaten.sort((a, b) => Math.abs(b.ay - b.y) - Math.abs(a.ay - a.y) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
  return kandidaten[0] ?? null
}
