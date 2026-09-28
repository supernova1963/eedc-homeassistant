/**
 * energieFlussLayout — die reine Layout-Logik des Energiefluss-Diagramms (kein JSX).
 *
 * Aus `EnergieFluss.tsx` herausgezogen (Bau A §A2, #341/#348), damit sie ohne
 * Render prüfbar ist — reiner Umzug, Signaturen und Verhalten unverändert.
 *
 * Bau A §A3 ergänzt darunter (Abschnitt „Eine Reihe je Zone") Kaskaden, Maßstab
 * und Faltung als **eigene** Funktion `layoutEnergieFluss`. Der alte Pfad
 * (`layoutNodes`, `flowPath`) bleibt bis zur Verdrahtung in §A4 unverändert —
 * `EnergieFluss.tsx` liest ihn weiter, es gibt keinen Zwischenzustand im Bild.
 */

import type { LiveFahrzeug, LiveGauge, LiveKomponente } from '../../api/liveDashboard'
import { SONSTIGES_KATEGORIE_LABELS, compareTyp } from '../../lib/constants'

export interface NodePosition {
  x: number
  y: number
  komp: LiveKomponente
}

// ─── Layout ─────────────────────────────────────────────────────────

export const W_DEFAULT = 600

/** Verteile n Items gleichmäßig auf einer Linie */
export function distribute(n: number, minX: number, maxX: number): number[] {
  if (n === 0) return []
  if (n === 1) return [(minX + maxX) / 2]
  const step = (maxX - minX) / (n - 1)
  return Array.from({ length: n }, (_, i) => minX + i * step)
}

/** Dynamische Dimensionen abhängig von der max. Anzahl Komponenten pro Zeile */
export interface LayoutDims {
  nodeW: number
  nodeH: number
  nodeR: number
  hausR: number
  cy: number
  verbraucherY: number
  kwFontSize: number
  labelFontSize: number
  socFontSize: number
  labelMaxChars: number
  iconSize: number
  hausIconSize: number
}

export function computeDims(maxPerRow: number): LayoutDims {
  // Ab 5+ Items pro Zeile: kompakte Darstellung
  if (maxPerRow >= 5) {
    return {
      nodeW: 80, nodeH: 48, nodeR: 10, hausR: 34,
      cy: 170, verbraucherY: 305,
      kwFontSize: 10, labelFontSize: 8.5, socFontSize: 9,
      labelMaxChars: 11, iconSize: 16, hausIconSize: 24,
    }
  }
  // 4 Items: leicht reduziert
  if (maxPerRow >= 4) {
    return {
      nodeW: 88, nodeH: 52, nodeR: 10, hausR: 36,
      cy: 175, verbraucherY: 310,
      kwFontSize: 10.5, labelFontSize: 8.5, socFontSize: 9.5,
      labelMaxChars: 12, iconSize: 17, hausIconSize: 24,
    }
  }
  // ≤3 Items: Standard-Größe (proportional zur Sidebar)
  return {
    nodeW: 100, nodeH: 58, nodeR: 12, hausR: 38,
    cy: 180, verbraucherY: 320,
    kwFontSize: 11, labelFontSize: 9, socFontSize: 10,
    labelMaxChars: 14, iconSize: 17, hausIconSize: 26,
  }
}

export interface LayoutResult {
  nodes: NodePosition[]
  dims: LayoutDims
}

export function layoutNodes(komponenten: LiveKomponente[], W: number = W_DEFAULT): LayoutResult {
  const erzeuger = komponenten.filter(k => k.key.startsWith('pv_'))
  const netz = komponenten.filter(k => k.key === 'netz')
  const speicher = komponenten.filter(k => k.key.startsWith('batterie_'))
  // Kinder (E-Autos mit parent_key) separat behandeln
  const kinder = komponenten.filter(k => k.parent_key)
  const kinderKeys = new Set(kinder.map(k => k.key))
  const verbraucher = komponenten.filter(k =>
    !k.key.startsWith('pv_') && k.key !== 'netz' &&
    !k.key.startsWith('batterie_') && k.key !== 'haushalt' &&
    !kinderKeys.has(k.key)
  )

  // Kinder direkt nach ihrem Parent einreihen (z.B. E-Auto neben Wallbox)
  const kinderByParent = new Map<string, LiveKomponente[]>()
  kinder.forEach(k => {
    const list = kinderByParent.get(k.parent_key!) || []
    list.push(k)
    kinderByParent.set(k.parent_key!, list)
  })
  const alleUnten: LiveKomponente[] = []
  verbraucher.forEach(v => {
    alleUnten.push(v)
    const kids = kinderByParent.get(v.key)
    if (kids) kids.forEach(k => alleUnten.push(k))
  })
  // Kinder ohne passenden Parent am Ende anhängen
  kinder.forEach(k => {
    if (!alleUnten.includes(k)) alleUnten.push(k)
  })

  const maxPerRow = Math.max(erzeuger.length, alleUnten.length, 1)
  const dims = computeDims(maxPerRow)
  const { nodeW, nodeH, cy: CY } = dims

  const nodes: NodePosition[] = []

  // Dynamische Ränder: nutzt die volle Breite besser aus
  const margin = nodeW / 2 + 15

  // Oben: Erzeuger (volle Breite abzüglich Rand)
  const ezXs = distribute(erzeuger.length, margin, W - margin)
  erzeuger.forEach((k, i) => nodes.push({ x: ezXs[i], y: 50, komp: k }))

  // Links: Netz
  netz.forEach(k => nodes.push({ x: margin, y: CY, komp: k }))

  // Rechts: Speicher — vertikal gestapelt bei mehreren
  const spX = W - margin
  speicher.forEach((k, i) => {
    const offsetY = speicher.length > 1
      ? (i - (speicher.length - 1) / 2) * (nodeH + 10)
      : 0
    nodes.push({ x: spX, y: CY + offsetY, komp: k })
  })

  // Unten: Verbraucher + Kinder zusammen in einer Reihe
  const vrXs = distribute(alleUnten.length, margin, W - margin)
  alleUnten.forEach((k, i) => nodes.push({ x: vrXs[i], y: dims.verbraucherY, komp: k }))

  return { nodes, dims }
}

// ─── SVG Helpers ────────────────────────────────────────────────────

/** Quadratic Bezier Pfad von Knoten zu Zielpunkt */
export function flowPath(nx: number, ny: number, tx: number, ty: number): string {
  const mx = (nx + tx) / 2
  const my = (ny + ty) / 2
  const dx = tx - nx
  const dy = ty - ny
  const len = Math.sqrt(dx * dx + dy * dy) || 1
  const perpX = -dy / len * 25
  const perpY = dx / len * 25
  return `M ${nx} ${ny} Q ${mx + perpX} ${my + perpY} ${tx} ${ty}`
}

// ═══════════════════════════════════════════════════════════════════
// Eine Reihe je Zone — Kaskaden, Maßstab, Faltung (Bau A §A3, #341/#348)
// ═══════════════════════════════════════════════════════════════════
//
// Normative Grundlage: Plan `1-ok-2-ok-magical-panda.md` §1.3–1.5 und
// Vorlage Bau A §A3. Referenz-Implementierung ist der Muster-Abschnitt
// „Tech-Layout: eine Reihe je Zone" (`energiefluss-szene.v5.html` Z. 350–401);
// wo diese Datei davon abweicht, steht der Grund am Ort.
//
// ⛔ Gruppen und gefaltete Autos entstehen NUR hier. Sie erscheinen nie in
// `komponenten`, nie in `pvCount` und nie in `nettoHausverbrauch` von
// `EnergieFluss.tsx` — die Bilanz sieht dieselben Knoten wie vorher.

/** Höhe der Zeichenfläche bei Maßstab 1; die y-Anker von `computeDims` sind darauf geeicht. */
export const H_BASIS = 380
/** Mindestabstand zweier Kacheln in einer Reihe (Plan 19.09. §3a). */
export const ABSTAND_REIHE = 12
/** Unterhalb dieses Abstands gelten zwei Kacheln als überlappend (Muster `ueberlappt(…, 4)`). */
export const ABSTAND_MIN = 4
/** Mindestschrift am Bildschirm, gedeckelt durch die heutige Schrift (Plan §Entscheidungen). */
export const MINDEST_SCHRIFT_PX = 12
/** Ab dieser Kartenbreite gilt der Desktop-Maßstab (Zoom), darunter Handy (360/450, kein Zoom). */
export const DESKTOP_AB_PX = 500

/**
 * Wie viele Kacheln fasst eine Reihe der Breite `W`, ohne dass sich zwei
 * berühren (Plan 19.09. §3a): Mittelpunkte von `nodeW/2 + 15` bis
 * `W − nodeW/2 − 15`, Schritt ≥ `nodeW + ABSTAND_REIHE`.
 * 3 bei 360, 4 bei 450, 6 bei 600 (je mit `nodeW` 80).
 */
export function kapazitaet(W: number, nodeW: number): number {
  return Math.max(1, 1 + Math.floor((W - nodeW - 30) / (nodeW + ABSTAND_REIHE)))
}

/** Breite, die eine Reihe mit `n` Kacheln der Breite `nodeW` überlappungsfrei braucht. */
export function wBedarf(n: number, nodeW: number): number {
  return nodeW + 30 + (n - 1) * (nodeW + ABSTAND_REIHE)
}

// ─── Klassifikation ─────────────────────────────────────────────────

export type Zone = 'oben' | 'links' | 'rechts' | 'unten'
export type SonstigesZweig = 'erzeuger' | 'abgabe' | 'speicher' | 'verbraucher'

/** Key-Präfix → Investitionstyp. Das Präfix ist für altes und neues Backend identisch. */
const PRAEFIX_TYP: Record<string, string> = {
  pv: 'pv-module',
  batterie: 'speicher',
  eauto: 'e-auto',
  wallbox: 'wallbox',
  waermepumpe: 'waermepumpe',
  sonstige: 'sonstiges',
}

export interface Klassifikation {
  /** `null` = keine Kachel (der Haushalt ist die Mitte). */
  zone: Zone | null
  /** Sortier-Typ für `compareTyp`. */
  typ: string | null
  /** Gruppierklasse — nur Gleichartiges wird gebündelt; `null` = gruppiert nie. */
  klasse: string | null
}

/** Präfix eines Knoten-Keys — dieselbe Zerlegung wie `getColor` (`split('_')[0]`). */
export function praefix(key: string): string {
  return key.split('_')[0]
}

/**
 * Buchungszweig einer Sonstigen (Plan §1.3): `erzeuger` · `abgabe` · `speicher`;
 * alles andere — `verbraucher`, `zaehler`, unbekannt — ist `verbraucher`.
 * Fehlt die Kategorie (älteres Backend; neues Backend bei „Automatisch"),
 * entscheidet die Seite: `erzeugung_kw` gesetzt ⇒ Erzeuger. Mit dem neuen
 * Backend landet eine Sonstige ohne Kategorie ohnehin im Verbraucher-Zweig
 * des Builders (`erzeugung_kw = None`), die Regel ist dort also deckungsgleich.
 * ⚠ Grenznotiz (Vorlage §A3, hingenommen): ein sonstiger SPEICHER ohne
 * `kategorie` (nur altes Backend) wechselt mit der Flussrichtung den Zweig.
 */
export function sonstigesZweig(k: LiveKomponente): SonstigesZweig {
  const kat = k.kategorie
  if (kat === 'erzeuger' || kat === 'abgabe' || kat === 'speicher') return kat
  if (kat != null && kat !== '') return 'verbraucher'
  return k.erzeugung_kw != null ? 'erzeuger' : 'verbraucher'
}

/**
 * Zone und Gruppierklasse eines Knotens — primär über das Key-Präfix,
 * `typ`/`kategorie` verfeinern (PV: BKW vs. Modul für die Sortierung;
 * Sonstiges: der Buchungszweig).
 */
export function klassifiziere(k: LiveKomponente): Klassifikation {
  if (k.key === 'netz') return { zone: 'links', typ: null, klasse: null }
  if (k.key === 'haushalt') return { zone: null, typ: null, klasse: null }
  const p = praefix(k.key)
  if (p === 'pv') return { zone: 'oben', typ: k.typ ?? PRAEFIX_TYP.pv, klasse: 'pv' }
  if (p === 'batterie') return { zone: 'rechts', typ: PRAEFIX_TYP.batterie, klasse: 'speicher' }
  if (p === 'sonstige') return { zone: 'unten', typ: PRAEFIX_TYP.sonstige, klasse: `sonstiges:${sonstigesZweig(k)}` }
  if (p in PRAEFIX_TYP) return { zone: 'unten', typ: PRAEFIX_TYP[p], klasse: PRAEFIX_TYP[p] }
  // Unbekanntes Präfix (baut der Builder heute nicht): steht unten, wird aber
  // nie mit etwas anderem gebündelt — „nur Gleichartiges" lässt sich ohne
  // bekannte Klasse nicht belegen, und ein Gruppen-Key träfe keine Farbe.
  return { zone: 'unten', typ: k.typ ?? null, klasse: null }
}

// ─── Kacheln ────────────────────────────────────────────────────────

/** Was die Wallbox-Kachel vom Auto zeigt (Plan §1.4a) — Rendering ist §A4. */
export type KachelAuto =
  /** Ein Auto: Füllstand = sein Ladestand, dazu „ID.4 52 %". */
  | { art: 'auto'; auto: LiveFahrzeug }
  /** Mehrere Autos, keines lädt eindeutig: Ladestände nebeneinander, ohne Füllstand. */
  | { art: 'ladestaende'; autos: LiveFahrzeug[] }

/**
 * Eine Kachel vor der Platzierung. Eine Einzelkachel trägt ihren Original-
 * Knoten; eine Gruppe trägt einen synthetischen Knoten (`<präfix>_grp[_<slug>]`)
 * und ihre Mitglieder.
 */
export interface Kachel {
  komp: LiveKomponente
  /** Nur Gruppen: die Original-Knoten, flach. */
  mitglieder?: LiveKomponente[]
  /** Sortierschlüssel: Typ (Gruppe erbt ihn) … */
  sortTyp: string | null
  /** … und Investitions-ID (Gruppe: die kleinste ihrer Mitglieder). */
  sortId: number
  klasse: string | null
  /**
   * Füllstand, den der gezeichnete Knoten SELBST trägt (Speicher-Gruppe:
   * kapazitätsgewichtet; Wallbox: Ladestand des Autos). `null` = ausdrücklich
   * kein Füllstand; fehlt das Feld, bleibt es beim Bestand (`gauges`).
   */
  ladestand?: number | null
  /** Nur Gruppen: „Heute"-kWh als Σ der Mitglieds-Keys, nur wenn alle bekannt. */
  heuteKwh?: number | null
  /** Nur Gruppen: aktive Mitglieder gegen die Netto-Richtung (Tooltip-Markierung). */
  gegenlaeufig?: LiveKomponente[]
  /** Wallbox (einzeln oder in einer Gruppe): die Autos. */
  fahrzeuge?: LiveFahrzeug[]
  fahrzeugeZuordnung?: 'eindeutig' | 'geschaetzt'
  /** Nur Wallbox-Einzelkachel: was die Kachel vom Auto zeigt; `null` = kein Auto auf der Kachel. */
  kachelAuto?: KachelAuto | null
}

export interface GezeichneterKnoten extends Kachel, NodePosition {
  zone: Zone
}

/** Investitions-ID aus dem Key (`batterie_3` → 3); ohne Ziffern-Endung ans Ende. */
function idAus(key: string): number {
  const m = /_(\d+)$/.exec(key)
  return m ? Number(m[1]) : Number.POSITIVE_INFINITY
}

function vergleicheZahl(a: number, b: number): number {
  return a === b ? 0 : a < b ? -1 : 1
}

/**
 * Reihenfolge stabil über Abfragen (Plan §1.5): `compareTyp`, dann ID; eine
 * Gruppe erbt Typ und kleinste Mitglieds-ID. Der Key entscheidet nur den
 * (theoretischen) Gleichstand — nie ein Messwert.
 */
export function vergleicheKacheln(a: Kachel, b: Kachel): number {
  return compareTyp({ typ: a.sortTyp }, { typ: b.sortTyp })
    || vergleicheZahl(a.sortId, b.sortId)
    || (a.komp.key < b.komp.key ? -1 : a.komp.key > b.komp.key ? 1 : 0)
}

function einzelKachel(k: LiveKomponente, kl: Klassifikation): Kachel {
  return { komp: k, sortTyp: kl.typ, sortId: idAus(k.key), klasse: kl.klasse }
}

const r3 = (x: number) => Math.round(x * 1000) / 1000

/** Netto-Leistung einer Mitgliedermenge: Σ Erzeugung − Σ Verbrauch, auf die passende Seite. */
function nettoLeistung(ms: LiveKomponente[]): Pick<LiveKomponente, 'erzeugung_kw' | 'verbrauch_kw'> {
  const netto = r3(ms.reduce((s, m) => s + (m.erzeugung_kw ?? 0) - (m.verbrauch_kw ?? 0), 0))
  return { erzeugung_kw: netto > 0 ? netto : null, verbrauch_kw: netto < 0 ? -netto : null }
}

/** „Heute"-kWh einer Gruppe = Σ der Mitglieds-Keys — nur wenn jeder Wert bekannt ist (P4). */
function heuteSumme(ms: LiveKomponente[], tagesWerte?: Record<string, number | null>): number | null {
  if (!tagesWerte) return null
  let s = 0
  for (const m of ms) {
    const v = tagesWerte[m.key]
    if (v == null) return null
    s += v
  }
  return r3(s)
}

/** Ladestand aus den Gauges (`batterie_3` → `soc_3`) — dieselbe Zuordnung wie `getSoc`. */
function socAusGauges(key: string, gauges?: LiveGauge[]): number | null {
  const m = /_(\d+)$/.exec(key)
  if (!m || !gauges) return null
  const g = gauges.find(x => x.key === `soc_${m[1]}`)
  return g ? g.wert : null
}

interface GruppenArt {
  key: string
  label: string
  icon: string
  typ: string
  kategorie?: string
}

export interface LayoutEingaben {
  /** Ladestände (`soc_<id>`) — für Speicher-Gruppen und Autos ohne `fahrzeuge`. */
  gauges?: LiveGauge[]
  /** „Heute"-kWh je Knoten-Key (`heute_kwh_pro_komponente`). */
  tagesWerte?: Record<string, number | null>
}

/**
 * Baut eine Gruppenkachel aus Teilen (Einzel- oder Gruppenkacheln, flach
 * aufgelöst). Werte nach Plan §1.4: Leistung netto (bei gleichgerichteten
 * Mitgliedern = Σ), „Heute" Σ nur vollständig.
 */
function gruppenKachel(
  art: GruppenArt, teile: Kachel[], klasse: string | null, eingaben: LayoutEingaben,
  zusatz: (mitglieder: LiveKomponente[]) => Partial<LiveKomponente> = () => ({}),
): Kachel {
  // Mitglieder in derselben stabilen Reihenfolge wie die Kacheln (Typ, dann ID).
  const mitglieder = teile.flatMap(t => t.mitglieder ?? [t.komp])
    .map(m => einzelKachel(m, klassifiziere(m)))
    .sort(vergleicheKacheln)
    .map(k => k.komp)
  const netto = nettoLeistung(mitglieder)
  const quelle = netto.erzeugung_kw != null
  const senke = netto.verbrauch_kw != null
  const gegenlaeufig = mitglieder.filter(m =>
    (quelle && (m.verbrauch_kw ?? 0) > 0) || (senke && (m.erzeugung_kw ?? 0) > 0))
  const kachel: Kachel = {
    komp: {
      key: art.key, label: art.label, icon: art.icon, typ: art.typ,
      kategorie: art.kategorie ?? null, ...netto, ...zusatz(mitglieder),
    },
    mitglieder,
    sortTyp: art.typ,
    sortId: Math.min(...mitglieder.map(m => idAus(m.key))),
    klasse,
    heuteKwh: heuteSumme(mitglieder, eingaben.tagesWerte),
    gegenlaeufig,
  }
  const mitAutos = teile.filter(t => t.fahrzeuge && t.fahrzeuge.length > 0)
  if (mitAutos.length > 0) {
    const nachId = new Map<number, LiveFahrzeug>()
    mitAutos.forEach(t => t.fahrzeuge!.forEach(f => { if (!nachId.has(f.investition_id)) nachId.set(f.investition_id, f) }))
    kachel.fahrzeuge = [...nachId.values()].sort((a, b) => vergleicheZahl(a.investition_id, b.investition_id))
    kachel.fahrzeugeZuordnung = mitAutos.every(t => t.fahrzeugeZuordnung === 'eindeutig') ? 'eindeutig' : 'geschaetzt'
    kachel.kachelAuto = null
  }
  return kachel
}

/**
 * PV-Gruppe: dazu Σ kWp, aber nur wenn JEDES Mitglied eine Nennleistung
 * trägt — sonst `null`, und die Auslastung entfällt (P4; die Semantik „nicht
 * ermittelbar" aus dem Builder, nie 0 kWp).
 * `leistung_kwp` ist hier das Feld der Live-Response (Builder:
 * `get_erzeuger_kwp`, also schon effektiv) — Allowlist (F) in
 * `check-kennwert-roh.mjs`.
 */
function pvGruppe(key: string, label: string, teile: Kachel[], eingaben: LayoutEingaben): Kachel {
  const typ = teile.map(t => t.sortTyp).sort((a, b) => compareTyp({ typ: a }, { typ: b }))[0] ?? PRAEFIX_TYP.pv
  return gruppenKachel({ key, label, icon: 'sun', typ }, teile, 'pv', eingaben, mitglieder => {
    const kwp = mitglieder.map(mitglied => mitglied.leistung_kwp)
    return {
      leistung_kwp: kwp.every(v => v != null && v > 0)
        ? r3(kwp.reduce<number>((s, v) => s + (v ?? 0), 0))
        : null,
    }
  })
}

/**
 * Speicher-Gruppe „Speicher (n)": Leistung netto; Ladestand kapazitäts-
 * gewichtet — nur wenn jedes Mitglied Ladestand UND Kapazität hat, sonst kein
 * Füllstand (P4). Der Ladestand steht am Knoten, nicht in `gauges`.
 */
export function speicherGruppe(speicher: Kachel[], eingaben: LayoutEingaben): Kachel {
  const ms = speicher.flatMap(t => t.mitglieder ?? [t.komp])
  const socs = ms.map(m => socAusGauges(m.key, eingaben.gauges))
  const kaps = ms.map(m => m.kapazitaet_kwh ?? null)
  const kapVoll = kaps.every(v => v != null && v > 0)
  const summeKap = kaps.reduce<number>((s, v) => s + (v ?? 0), 0)
  const g = gruppenKachel(
    { key: 'batterie_grp', label: 'Speicher', icon: 'battery', typ: PRAEFIX_TYP.batterie },
    speicher, 'speicher', eingaben, () => ({ kapazitaet_kwh: kapVoll ? r3(summeKap) : null }),
  )
  g.ladestand = kapVoll && socs.every(s => s != null)
    ? Math.round(socs.reduce<number>((s, soc, i) => s + (soc as number) * (kaps[i] as number), 0) / summeKap)
    : null
  return g
}

// ─── Wallbox-Kachel: das Auto steckt darin (Plan §1.4a) ─────────────

/**
 * Die Autos einer Wallbox. Neues Backend: `fahrzeuge` + `fahrzeuge_zuordnung`
 * (eine Zuordnung, auch Autos ohne eigenen Knoten). Älteres Backend: der
 * Client faltet die `parent_key`-Kinder selbst — Label aus dem Knoten,
 * Ladestand aus `gauges`, Leistung vorzeichenbehaftet wie `LiveFahrzeug.kw`.
 */
export function wallboxFahrzeuge(
  wallbox: LiveKomponente, kinder: LiveKomponente[], wallboxAnzahl: number, gauges?: LiveGauge[],
): { fahrzeuge: LiveFahrzeug[]; zuordnung: 'eindeutig' | 'geschaetzt' } {
  const standard = wallboxAnzahl === 1 ? 'eindeutig' : 'geschaetzt'
  if (wallbox.fahrzeuge != null) {
    return { fahrzeuge: wallbox.fahrzeuge, zuordnung: wallbox.fahrzeuge_zuordnung ?? standard }
  }
  const fahrzeuge = kinder
    .filter(c => c.parent_key === wallbox.key)
    .map<LiveFahrzeug>(c => ({
      investition_id: idAus(c.key),
      label: c.label,
      soc: socAusGauges(c.key, gauges),
      kw: c.verbrauch_kw != null ? c.verbrauch_kw : c.erzeugung_kw != null ? -c.erzeugung_kw : null,
      v2h: (c.erzeugung_kw ?? 0) > 0,
    }))
    .sort((a, b) => vergleicheZahl(a.investition_id, b.investition_id))
  return { fahrzeuge, zuordnung: standard }
}

/**
 * Was die Wallbox-Kachel vom Auto zeigt (Plan §1.4a):
 * * eindeutig, ein Auto — dessen Ladestand als Füllstand, dazu Name + %;
 * * eindeutig, mehrere — das eine ladende (`kw > 0`); lädt keines (oder mehr
 *   als eines), die Ladestände nebeneinander OHNE Füllstand;
 * * geschätzt (≥ 2 Wallboxen) — kein Auto auf der Kachel; die Autos stehen
 *   nur im Tooltip/Overlay mit dem Satz „weiß eedc noch nicht" (§A4/A5).
 */
export function wallboxKachelAuto(
  fahrzeuge: LiveFahrzeug[], zuordnung: 'eindeutig' | 'geschaetzt',
): { kachelAuto: KachelAuto | null; ladestand: number | null } {
  if (zuordnung !== 'eindeutig' || fahrzeuge.length === 0) return { kachelAuto: null, ladestand: null }
  const laedt = fahrzeuge.filter(f => (f.kw ?? 0) > 0)
  const fokus = laedt.length === 1 ? laedt[0] : fahrzeuge.length === 1 ? fahrzeuge[0] : null
  if (fokus) return { kachelAuto: { art: 'auto', auto: fokus }, ladestand: fokus.soc }
  return { kachelAuto: { art: 'ladestaende', autos: fahrzeuge }, ladestand: null }
}

// ─── Kaskaden ───────────────────────────────────────────────────────

export type StufenName = 'einzeln' | 'ausrichtung' | 'traeger' | 'gesamt' | 'klasse' | 'weitere'

export interface Stufe {
  name: StufenName
  kacheln: Kachel[]
}

/** Kompassrang der PV-Ausrichtungsgruppen: Ost · Süd · West · Nord, Zwischenrichtungen dazwischen. */
const KOMPASS = ['Ost', 'Südost', 'Süd', 'Südwest', 'West', 'Nordwest', 'Nord', 'Nordost']
/** Label der Restgruppe (Module ohne Merkmal) — steht immer zuletzt. */
export const REST_LABEL = 'Weitere'

function kompassRang(label: string): number {
  if (label === REST_LABEL) return KOMPASS.length + 2
  const i = KOMPASS.indexOf(label)
  // „Ost-West" (EIN Label, N-527) und jedes künftige Label: nach den acht
  // Richtungen, vor „Weitere".
  return i >= 0 ? i : KOMPASS.length + 1
}

/** Key-Slug: ASCII-Kleinbuchstaben ohne Ziffern — so endet kein Gruppen-Key auf `_<Ziffern>`. */
function slug(label: string): string {
  const s = label.toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .replace(/[^a-z]+/g, '')
  return s || 'gruppe'
}

/**
 * Bündelt PV-Kacheln nach einem Merkmal. `null`, wenn die Stufe nichts
 * trennt: sie gilt nur bei ≥ 2 Kacheln MIT Merkmal und ≥ 2 verschiedenen
 * Werten (eine einzige Gruppe „Süd" wäre kein Gewinn). Kacheln ohne Merkmal
 * landen in der Restgruppe „Weitere" — nie in einer Richtung, nie unterschlagen.
 * Eine „Gruppe" mit einem Mitglied bleibt Einzelkachel.
 */
function merkmalsGruppen<T extends string | number>(
  kacheln: Kachel[],
  merkmal: (k: LiveKomponente) => T | null | undefined,
  gruppe: (wert: T, teile: Kachel[]) => Kachel,
  rest: (teile: Kachel[]) => Kachel,
  reihenfolge: (a: [T | null, Kachel[]], b: [T | null, Kachel[]]) => number,
): Kachel[] | null {
  const mit = kacheln.filter(k => merkmal(k.komp) != null)
  if (mit.length < 2 || new Set(mit.map(k => merkmal(k.komp))).size < 2) return null
  const nachWert = new Map<T | null, Kachel[]>()
  kacheln.forEach(k => {
    const w = merkmal(k.komp) ?? null
    const liste = nachWert.get(w) ?? []
    liste.push(k)
    nachWert.set(w, liste)
  })
  return [...nachWert.entries()].sort(reihenfolge).map(([w, teile]) =>
    teile.length === 1 ? teile[0] : w == null ? rest(teile) : gruppe(w, teile))
}

/**
 * Kaskade oben (Plan §1.3): einzeln → nach Ausrichtung → nach Träger →
 * „PV gesamt". Eine Stufe, die die Kachelzahl nicht senkt, wird übersprungen.
 * Ohne `ausrichtung_label`/`traeger_id` (älteres Backend) entfallen diese
 * beiden Stufen von selbst; der `pv_gesamt`-Fallback ist eine Kachel und
 * wird nie gruppiert.
 */
export function pvKaskade(pv: Kachel[], eingaben: LayoutEingaben = {}): Stufe[] {
  const einzeln = [...pv].sort(vergleicheKacheln)
  const stufen: Stufe[] = [{ name: 'einzeln', kacheln: einzeln }]
  if (einzeln.length <= 1) return stufen

  const nachAusrichtung = merkmalsGruppen<string>(
    einzeln,
    k => k.ausrichtung_label,
    (label, teile) => pvGruppe(`pv_grp_${slug(label)}`, label, teile, eingaben),
    teile => pvGruppe(`pv_grp_${slug(REST_LABEL)}`, REST_LABEL, teile, eingaben),
    ([a, ta], [b, tb]) => vergleicheZahl(kompassRang(a ?? REST_LABEL), kompassRang(b ?? REST_LABEL))
      || vergleicheKacheln(ta[0], tb[0]),
  )
  let unbenannt = 0
  const nachTraeger = merkmalsGruppen<number>(
    einzeln,
    k => k.traeger_id,
    (id, teile) => {
      // Der BKW-Rest trägt seine eigene ID als `traeger_id` — ist er dabei,
      // heißt die Gruppe wie er. Einen Wechselrichter-Namen kennt die
      // Response nicht; dann eine neutrale Nummer in Sortierreihenfolge.
      // Key `pv_grp_tr<id>`: vor den Ziffern steht `r`, nicht `_` — `getSoc`
      // (`/_(\d+)$/`) greift also nicht.
      const selbst = teile.find(t => idAus(t.komp.key) === id)
      return pvGruppe(`pv_grp_tr${id}`, selbst ? selbst.komp.label : `PV-Gruppe ${++unbenannt}`, teile, eingaben)
    },
    teile => pvGruppe(`pv_grp_${slug(REST_LABEL)}`, REST_LABEL, teile, eingaben),
    ([a, ta], [b, tb]) => vergleicheZahl(a == null ? 1 : 0, b == null ? 1 : 0) || vergleicheKacheln(ta[0], tb[0]),
  )
  const gesamt = [pvGruppe('pv_grp_gesamt', 'PV gesamt', einzeln, eingaben)]

  const kandidaten: [StufenName, Kachel[] | null][] = [
    ['ausrichtung', nachAusrichtung], ['traeger', nachTraeger], ['gesamt', gesamt],
  ]
  for (const [name, kacheln] of kandidaten) {
    if (kacheln && kacheln.length < stufen[stufen.length - 1].kacheln.length) stufen.push({ name, kacheln })
  }
  return stufen
}

/** Gruppen der unteren Reihe — je Klasse ein Key, der eine `KATEGORIE_FARBEN`-Farbe trifft. */
const UNTEN_GRUPPEN: Record<string, GruppenArt> = {
  waermepumpe: { key: 'waermepumpe_grp', label: 'Wärmepumpen', icon: 'flame', typ: 'waermepumpe' },
  wallbox: { key: 'wallbox_grp', label: 'Laden', icon: 'plug', typ: 'wallbox' },
  'e-auto': { key: 'eauto_grp', label: 'E-Autos', icon: 'car', typ: 'e-auto' },
  'sonstiges:verbraucher': { key: 'sonstige_grp_verbraucher', label: 'Sonstige', icon: 'wrench', typ: 'sonstiges', kategorie: 'verbraucher' },
  'sonstiges:erzeuger': { key: 'sonstige_grp_erzeuger', label: SONSTIGES_KATEGORIE_LABELS.erzeuger, icon: 'wrench', typ: 'sonstiges', kategorie: 'erzeuger' },
  'sonstiges:abgabe': { key: 'sonstige_grp_abgabe', label: SONSTIGES_KATEGORIE_LABELS.abgabe, icon: 'wrench', typ: 'sonstiges', kategorie: 'abgabe' },
  'sonstiges:speicher': { key: 'sonstige_grp_speicher', label: SONSTIGES_KATEGORIE_LABELS.speicher, icon: 'wrench', typ: 'sonstiges', kategorie: 'speicher' },
}

/** Handy-Notnagel „Weitere Verbraucher" — neutral (Sonstige-Grau), nur Verbraucher. */
const WEITERE: GruppenArt = { key: 'sonstige_grp_weitere', label: REST_LABEL, icon: 'wrench', typ: 'sonstiges', kategorie: 'verbraucher' }
const WEITERE_KLASSE = 'weitere'

/**
 * Ein Schritt der unteren Kaskade: die Klasse mit den meisten noch einzelnen
 * Kacheln (≥ 2) wird gebündelt; Gleichstand nach `INVESTITION_TYP_ORDER`
 * (`compareTyp`), dann nach der kleinsten Mitglieds-ID. `null`, wenn keine
 * Klasse mehr ≥ 2 Kacheln hat.
 */
function klassenSchritt(kacheln: Kachel[], eingaben: LayoutEingaben): Kachel[] | null {
  const nachKlasse = new Map<string, Kachel[]>()
  kacheln.forEach(k => {
    if (k.mitglieder || k.klasse == null || !(k.klasse in UNTEN_GRUPPEN)) return
    const liste = nachKlasse.get(k.klasse) ?? []
    liste.push(k)
    nachKlasse.set(k.klasse, liste)
  })
  let best: [string, Kachel[]] | null = null
  for (const eintrag of nachKlasse) {
    const [kl, ms] = eintrag
    if (ms.length < 2) continue
    if (!best) { best = eintrag; continue }
    const [bkl, bms] = best
    const besser = ms.length > bms.length
      || (ms.length === bms.length && (
        compareTyp({ typ: UNTEN_GRUPPEN[kl].typ }, { typ: UNTEN_GRUPPEN[bkl].typ })
        || vergleicheZahl(Math.min(...ms.map(m => m.sortId)), Math.min(...bms.map(m => m.sortId)))) < 0)
    if (besser) best = eintrag
  }
  if (!best) return null
  const [kl, ms] = best
  const gruppe = gruppenKachel(UNTEN_GRUPPEN[kl], ms, kl, eingaben)
  return [...kacheln.filter(k => !ms.includes(k)), gruppe].sort(vergleicheKacheln)
}

/**
 * Rang im Handy-Notnagel (Plan §1.3, feste Reihenfolge statt nach Leistung,
 * damit die Zusammensetzung zwischen zwei Abfragen nicht springt): Sonstige
 * und Abgabe, dann E-Autos ohne Wallbox, dann Wärmepumpen, zuletzt Wallboxen.
 * Erzeuger (BHKW), Speicher und Unbekanntes: nie (`Infinity`).
 */
function weitereRang(k: Kachel): number {
  switch (k.klasse) {
    case WEITERE_KLASSE: return -1
    case 'sonstiges:verbraucher':
    case 'sonstiges:abgabe': return 0
    case 'e-auto': return 1
    case 'waermepumpe': return 2
    case 'wallbox': return 3
    default: return Number.POSITIVE_INFINITY
  }
}

/** Ein Notnagel-Schritt: die zwei ranghöchsten Verbraucher-Kacheln werden „Weitere". */
function weitereSchritt(kacheln: Kachel[], eingaben: LayoutEingaben): Kachel[] | null {
  const verbraucher = kacheln
    .map((k, i) => ({ k, i, rang: weitereRang(k) }))
    .filter(e => Number.isFinite(e.rang))
    .sort((a, b) => a.rang - b.rang || a.i - b.i)
  if (verbraucher.length < 2) return null
  const zwei = verbraucher.slice(0, 2).map(e => e.k)
  const gruppe = gruppenKachel(WEITERE, zwei, WEITERE_KLASSE, eingaben)
  return [...kacheln.filter(k => !zwei.includes(k)), gruppe].sort(vergleicheKacheln)
}

/**
 * Kaskade unten (Plan §1.3): einzeln → schrittweise die Klasse mit den
 * meisten Kacheln → am Handy der Notnagel „Weitere Verbraucher". Am Desktop
 * gibt es keinen Notnagel (Vorlage §4); ist die Kaskade dort erschöpft, zoomt
 * das Bild auch unter die Mindestschrift.
 */
export function untenKaskade(unten: Kachel[], handy: boolean, eingaben: LayoutEingaben = {}): Stufe[] {
  let cur = [...unten].sort(vergleicheKacheln)
  const stufen: Stufe[] = [{ name: 'einzeln', kacheln: cur }]
  for (let next = klassenSchritt(cur, eingaben); next; next = klassenSchritt(cur, eingaben)) {
    cur = next
    stufen.push({ name: 'klasse', kacheln: cur })
  }
  if (handy) {
    for (let next = weitereSchritt(cur, eingaben); next; next = weitereSchritt(cur, eingaben)) {
      cur = next
      stufen.push({ name: 'weitere', kacheln: cur })
    }
  }
  return stufen
}

// ─── Maßstab: Zirkel Kachelgröße ↔ Anzahl (Plan §1.3a, 19.09. §3b) ──

export interface BuehnenMass {
  /** Gemessene Kartenbreite in px. */
  breitePx: number
  /**
   * Nur im Vollbild (⤢): die gemessene Höhe. Dann bleibt die Höhe der
   * Zeichenfläche `380·k` und die BREITE wird `380·k·(breite/höhe)` — nie
   * umgekehrt, die y-Anker von `computeDims` sind auf 380 geeicht. Unter
   * 500 px Breite gilt auch im Vollbild der Handy-Maßstab (360/450, kein
   * Zoom). Die Verdrahtung (Prop `vollbild`) ist §A4.
   */
  vollbild?: { hoehePx: number } | null
}

export interface Massstab {
  geraet: 'desktop' | 'handy'
  /** Zeichenfläche in Einheiten. */
  W: number
  H: number
  /** Zoom-Faktor der Zeichenfläche gegenüber heute (Handy: immer 1). */
  k: number
  /** Größenstufe der Kacheln — hängt an der längeren der beiden Reihen. */
  dims: LayoutDims
  /** Gewählte Stufe der oberen/unteren Kaskade (Index). */
  iP: number
  iU: number
  /** Gerenderte Beschriftung in px. */
  schriftPx: number
  /** Desktop: min(12, heutige Schrift); Handy: `null` (dort entscheidet `kapazitaet`). */
  mindestSchriftPx: number | null
}

/** Passt eine Reihe mit `n` Kacheln auf die Handy-Breite `W`? */
function passtHandy(W: number, n: number): boolean {
  return n <= kapazitaet(W, computeDims(n).nodeW)
}

/**
 * Wählt je Reihe die Kaskadenstufe und den Maßstab.
 *
 * **Desktop (Karte ≥ 500 px)** — Kandidaten-Schleife wie im Muster: je
 * Stufenpaar `dims = computeDims(max(nP, nU))`, Breitenbedarf beider Reihen
 * mit DIESEM `nodeW`, `Wn = max(600, …)`, Zoom `k = Wn/600`, gerenderte
 * Schrift `labF·Karte/Wn`. Reicht sie nicht an die Mindestschrift
 * `min(12, labF·Karte/600)`, eskaliert die vollere Reihe um eine Stufe. Ist
 * keine Stufe mehr frei (Erschöpfung), bleibt der Zoom — auch unter die
 * Mindestschrift, besser als Überlappung.
 *
 * **Handy (< 500 px)** — 360/450 Einheiten, kein Zoom; je Reihe die erste
 * Stufe, die `kapazitaet` fasst.
 *
 * Nimmt nur die Kachelzahlen je Stufe — rein und ohne Knoten prüfbar.
 */
export function waehleStufen(pvAnzahlen: number[], untenAnzahlen: number[], mass: BuehnenMass): Massstab {
  const ctr = mass.breitePx
  const letzteP = Math.max(pvAnzahlen.length - 1, 0)
  const letzteU = Math.max(untenAnzahlen.length - 1, 0)
  const n = (liste: number[], i: number) => liste[i] ?? 0
  let iP = 0
  let iU = 0

  if (ctr < DESKTOP_AB_PX) {
    const W = ctr < 375 ? 360 : 450
    while (iP < letzteP && !passtHandy(W, n(pvAnzahlen, iP))) iP++
    while (iU < letzteU && !passtHandy(W, n(untenAnzahlen, iU))) iU++
    const dims = computeDims(Math.max(n(pvAnzahlen, iP), n(untenAnzahlen, iU), 1))
    return {
      geraet: 'handy', W, H: H_BASIS, k: 1, dims, iP, iU,
      schriftPx: dims.labelFontSize * ctr / W, mindestSchriftPx: null,
    }
  }

  const hoehe = mass.vollbild?.hoehePx
  const vollbild = hoehe != null && hoehe > 0
  // Heutige Schrift: die 600×380-Zeichenfläche passt sich in die Karte (bzw.
  // ins Overlay) ein — in der Karte ist das `Breite/600`.
  const heuteZoom = vollbild ? Math.min(ctr / W_DEFAULT, hoehe / H_BASIS) : ctr / W_DEFAULT
  const verhaeltnis = vollbild ? ctr / hoehe : W_DEFAULT / H_BASIS
  let ergebnis: Massstab | null = null
  for (let schritt = 0; schritt <= letzteP + letzteU + 1; schritt++) {
    const nP = n(pvAnzahlen, iP)
    const nU = n(untenAnzahlen, iU)
    const dims = computeDims(Math.max(nP, nU, 1))
    const bedarf = Math.max(W_DEFAULT, wBedarf(nP, dims.nodeW), wBedarf(nU, dims.nodeW))
    const k = vollbild ? Math.max(1, bedarf / (H_BASIS * verhaeltnis)) : bedarf / W_DEFAULT
    const W = vollbild ? H_BASIS * k * verhaeltnis : bedarf
    const schriftPx = dims.labelFontSize * ctr / W
    const mindestSchriftPx = Math.min(MINDEST_SCHRIFT_PX, dims.labelFontSize * heuteZoom)
    ergebnis = { geraet: 'desktop', W, H: H_BASIS * k, k, dims, iP, iU, schriftPx, mindestSchriftPx }
    if (schriftPx >= mindestSchriftPx - 1e-9) break
    const pvKann = iP < letzteP
    const untenKann = iU < letzteU
    if (nP >= nU && pvKann) iP++
    else if (untenKann) iU++
    else if (pvKann) iP++
    else break
  }
  return ergebnis!
}

// ─── Überlappung: EINE Funktion, produktiv und als Test-Wächter ──────

/**
 * Überlappungsfrei = keine zwei Kachel-Rechtecke kommen sich näher als
 * `ABSTAND_MIN`, und keine Kachel schneidet den Hauskreis. Produktiv
 * entscheidet sie, ob der Speicher-Stapel bleiben darf (Plan §1.3); die
 * Tests prüfen mit ihr jedes Layout.
 */
export function ueberlappungsfrei(
  nodes: { x: number; y: number }[],
  dims: Pick<LayoutDims, 'nodeW' | 'nodeH' | 'hausR'>,
  haus: { x: number; y: number },
): boolean {
  const { nodeW, nodeH, hausR } = dims
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j]
      if (Math.abs(a.x - b.x) < nodeW + ABSTAND_MIN && Math.abs(a.y - b.y) < nodeH + ABSTAND_MIN) return false
    }
    const nx = Math.min(Math.max(haus.x, a.x - nodeW / 2), a.x + nodeW / 2)
    const ny = Math.min(Math.max(haus.y, a.y - nodeH / 2), a.y + nodeH / 2)
    if ((nx - haus.x) ** 2 + (ny - haus.y) ** 2 < hausR ** 2) return false
  }
  return true
}

// ─── Das Layout ─────────────────────────────────────────────────────

export interface EnergieFlussLayout extends LayoutResult {
  nodes: GezeichneterKnoten[]
  /**
   * Größenstufe der Kacheln; `cy`/`verbraucherY` sind bereits um den
   * senkrechten Versatz `(H − 380)/2` verschoben (Inhalt mittig).
   */
  dims: LayoutDims
  W: number
  H: number
  /** Hausmitte. */
  CX: number
  CY: number
  k: number
  geraet: 'desktop' | 'handy'
  schriftPx: number
  mindestSchriftPx: number | null
  /** Größte Leistung über die GEZEICHNETEN Knoten (Liniendicke; Gruppen überschreiten sonst das Maximum). */
  maxKw: number
  stufen: {
    oben: { name: StufenName; index: number; anzahl: number }
    unten: { name: StufenName; index: number; anzahl: number }
    speicherGruppiert: boolean
  }
}

/**
 * Das Layout „eine Reihe je Zone" (Bau A §A3): Kinder (`parent_key`) werden
 * nie gezeichnet — das Auto steckt in der Wallbox-Kachel —, jede Linie endet
 * damit am Haus, und bei einer Reihe je Zone kreuzt sich keine.
 * Zonen in der Reihenfolge oben → unten → rechts, weil die Speicherspalte an
 * den Randkacheln der beiden Reihen hängt.
 */
export function layoutEnergieFluss(
  komponenten: LiveKomponente[], mass: BuehnenMass, eingaben: LayoutEingaben = {},
): EnergieFlussLayout {
  const kinder = komponenten.filter(k => k.parent_key)
  const oben: Kachel[] = []
  const unten: Kachel[] = []
  const rechts: Kachel[] = []
  let netz: Kachel | null = null
  const wallboxAnzahl = komponenten.filter(k => !k.parent_key && praefix(k.key) === 'wallbox').length

  for (const k of komponenten) {
    if (k.parent_key) continue
    const kl = klassifiziere(k)
    const kachel = einzelKachel(k, kl)
    if (kl.zone === 'oben') oben.push(kachel)
    else if (kl.zone === 'rechts') rechts.push(kachel)
    else if (kl.zone === 'links') netz = kachel
    else if (kl.zone === 'unten') {
      if (kl.klasse === 'wallbox') {
        const { fahrzeuge, zuordnung } = wallboxFahrzeuge(k, kinder, wallboxAnzahl, eingaben.gauges)
        const { kachelAuto, ladestand } = wallboxKachelAuto(fahrzeuge, zuordnung)
        Object.assign(kachel, { fahrzeuge, fahrzeugeZuordnung: zuordnung, kachelAuto, ladestand })
      }
      unten.push(kachel)
    }
  }

  const pvK = pvKaskade(oben, eingaben)
  const uK = untenKaskade(unten, mass.breitePx < DESKTOP_AB_PX, eingaben)
  const m = waehleStufen(pvK.map(s => s.kacheln.length), uK.map(s => s.kacheln.length), mass)
  const obenStufe = pvK[m.iP]
  const untenStufe = uK[m.iU]

  const yOff = (m.H - H_BASIS) / 2
  const dims: LayoutDims = { ...m.dims, cy: m.dims.cy + yOff, verbraucherY: m.dims.verbraucherY + yOff }
  const margin = dims.nodeW / 2 + 15
  const CX = m.W / 2
  const CY = dims.cy
  const nodes: GezeichneterKnoten[] = []

  const obenXs = distribute(obenStufe.kacheln.length, margin, m.W - margin)
  obenStufe.kacheln.forEach((k, i) => nodes.push({ ...k, x: obenXs[i], y: 50 + yOff, zone: 'oben' }))
  const untenXs = distribute(untenStufe.kacheln.length, margin, m.W - margin)
  untenStufe.kacheln.forEach((k, i) => nodes.push({ ...k, x: untenXs[i], y: dims.verbraucherY, zone: 'unten' }))
  if (netz) nodes.push({ ...(netz as Kachel), x: margin, y: CY, zone: 'links' })

  const stapel = (liste: Kachel[]): GezeichneterKnoten[] => liste.map((k, i) => ({
    ...k,
    x: m.W - margin,
    y: CY + (liste.length > 1 ? (i - (liste.length - 1) / 2) * (dims.nodeH + 10) : 0),
    zone: 'rechts' as const,
  }))
  const speicher = [...rechts].sort(vergleicheKacheln)
  let rechtsKnoten = stapel(speicher)
  const speicherGruppiert = speicher.length > 1
    && !ueberlappungsfrei([...nodes, ...rechtsKnoten], dims, { x: CX, y: CY })
  if (speicherGruppiert) rechtsKnoten = stapel([speicherGruppe(speicher, eingaben)])
  nodes.push(...rechtsKnoten)

  const maxKw = Math.max(...nodes.flatMap(n => [n.komp.erzeugung_kw ?? 0, n.komp.verbrauch_kw ?? 0]), 0.1)

  return {
    nodes, dims, W: m.W, H: m.H, CX, CY, k: m.k, geraet: m.geraet,
    schriftPx: m.schriftPx, mindestSchriftPx: m.mindestSchriftPx, maxKw,
    stufen: {
      oben: { name: obenStufe.name, index: m.iP, anzahl: pvK.length },
      unten: { name: untenStufe.name, index: m.iU, anzahl: uK.length },
      speicherGruppiert,
    },
  }
}
