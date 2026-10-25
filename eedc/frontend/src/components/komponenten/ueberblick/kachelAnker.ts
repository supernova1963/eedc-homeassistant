/**
 * Welche Kachel hängt an welchem Objekt des Wärme/Klima-Panoramas (P-433-2 E1).
 *
 * **Nur zugeordnete Werte haben Kacheln** (B2, Gernot 23.10.): eine Kachel
 * entsteht nur, wenn der Wert `!= null` ist; was fehlt, sammelt
 * `ohneSensor` für die Zeile unter dem Bild („Ohne Sensor, deshalb ohne
 * Kachel: … → Datenquellen zuordnen").
 *
 * **Zuordnung (Bauplan §3 E1):** Leistung + Modus der Wärmepumpe nach Bauart —
 * Luft/Wasser → A · Sole/Grundwasser → C · Brauchwasser → F · Luft/Luft → O;
 * Innengeräte (`innengeraete[]` je Investition) → L, M, N in Listenreihenfolge,
 * ab dem vierten an N (das Layout gruppiert sie); Warmwasser-Temperatur je Gerät → E;
 * Strom heute je Gerät → I; Außentemperatur → Himmel; seit P-433-3 S1 je Gerät
 * «Vorlauf · Rücklauf» → {@link vorlaufAnker} (seit S2-8 am Heizkreis-Objekt nach dem Stammdatum
 * `vorlauftemperatur`: Fußbodenheizung K · Heizkörper J · sonst Hydraulikmodul G) und «Zusatzheizung» →
 * {@link ANKER_ZUSATZHEIZUNG} (eine Regel für alle Bauarten). Die neuen Wert-Kacheln stehen **nicht** in der
 * «Ohne Sensor»-Zeile (G7/E-P3-13): sie sind Zusatzangaben, kein Grundbestand.
 * Seit P-433-2c je Gerät «Wärme heute» aus dem Tag-Detail (`wp_geraete[].waerme_kwh`) am selben Heizkreis-Objekt wie
 * «Vorlauf · Rücklauf» — ebenfalls nur mit Wert und nicht in der «Ohne Sensor»-Zeile.
 *
 * ⚠ **P13 (ADR-002), Gruppe 2 «Anzeige-Ort nach Bauart» bzw. nach Stammdatum (`vorlauftemperatur`, S2-8):** die Bauart wählt
 * hier nur, AN WELCHEM OBJEKT eine Kachel steht — nie, OB ein Wert gezeigt
 * wird (das entscheidet allein, ob er geliefert wird). Gelesen über die
 * Client-SoT `lib/investitionParameter.ts` (`istLuftLuft`, `istBrauchwasser`,
 * Parameter-Namen), kein zweiter Bauart-Leser. Klassifiziert in
 * `scripts/check-bauart-roh.mjs::KLASSIFIZIERT`.
 */
import type { LiveDashboardResponse, LiveInnengeraet, LiveKomponente, LiveWetterResponse } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'
import { CHART_COLORS, KATEGORIE_FARBEN, fmtZahl } from '../../../lib'
import {
  PARAM_WAERMEPUMPE, heizkreisArt, istBrauchwasser, istKuehlungPassiv, istLuftLuft, type HeizkreisArt,
} from '../../../lib/investitionParameter'
import { formatPower, getNodeColor } from '../../live/EnergieFluss'
import { computeDims, type LayoutDims } from '../../live/energieFlussLayout'
import { modusZeile, type ZweiteZeile } from '../../live/EnergieFlussKachel'
import { modusKlartext } from '../../ui/ModusChip'
import type { AnkerId } from './waermePanoramaAnker'

/** Art einer Kachel — bestimmt Gruppierung und Rang im Layout. */
export type KachelArt = 'geraet' | 'innengeraet' | 'wert'

export interface UeberblickKachel {
  /** Stabiler Schlüssel (React-Key, Gruppen-Key). */
  id: string
  art: KachelArt
  anker: AnkerId
  /** Ungekürzter Name (die Kürzung macht die Zeichnung nach `labelMaxChars`). */
  label: string
  icon: string
  /** Rollenfarbe. */
  color: string
  isActive: boolean
  wertText: string
  zweiteZeile: ZweiteZeile | null
  tip: string
  /** Investition, zu der die Kachel gehört (Wert „Außentemperatur": keine). */
  investitionId: number | null
  /** Leistung in kW für die Σ der Gruppenkachel — Gerät: `verbrauch_kw`;
   *  Innengerät: `leistung_w`/1000 oder `null` (nicht gemessen); Wert-Kacheln: fehlt. */
  leistungKw?: number | null
  /** Nur Innengeräte: der Live-Datensatz (für die Liste bei Gruppen). */
  innengeraet?: LiveInnengeraet
  /** P-433-3 S2-6: Werttext in den kompakten Dims (ab 5 Kacheln je Reihe, nodeW 80) — fehlt er, gilt `wertText`.
   *  Gewählt wird er an EINER Stelle, {@link kachelWertText}. */
  wertTextKompakt?: string
}

export interface KachelEingaben {
  /** Alle Wärmepumpen der Anlage (E-P2-2: Kacheln aller Geräte im Bild). */
  geraete: Investition[]
  live: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  /** Referenzfarbe des Themas für inaktive Zeilen (`useChartTheme().referenz`). */
  referenz: string
  /** P-433-2c: Tag-Detail heute (`wp_geraete[].waerme_kwh` für die Kachel «Wärme heute»); fehlt es, keine Kachel. */
  tag?: TagDetail | null
}

export interface KachelErgebnis {
  kacheln: UeberblickKachel[]
  /** Was keine Kachel hat, weil kein Wert kommt — in Anzeige-Reihenfolge. */
  ohneSensor: string[]
}

/** P-433-3 S1: Objekt der Kachel «Vorlauf · Rücklauf», wenn das Stammdatum keine Heizflächen nennt — das
 *  Hydraulikmodul an der Rückwand, wo Vor- und Rücklauf aus der Wärmepumpe austreten (Master 25.10., H1 Option a;
 *  O ist die Klima-Außeneinheit). */
export const ANKER_VORLAUF: AnkerId = 'G'
/** P-433-3 S2-8 (Gernot 25.10.): Stammdatum `vorlauftemperatur` '35' ⇒ Fußbodenheizung im Wohnbereich (K). */
export const ANKER_VORLAUF_FUSSBODENHEIZUNG: AnkerId = 'K'
/** P-433-3 S2-8: Stammdatum `vorlauftemperatur` '55' ⇒ Heizkörper im Schlafzimmer (J). */
export const ANKER_VORLAUF_HEIZKOERPER: AnkerId = 'J'
/** Alle Objekte, an denen «Vorlauf · Rücklauf» stehen kann — für den Rang im Layout. */
export const ANKER_VORLAUF_ALLE: readonly AnkerId[] = [ANKER_VORLAUF, ANKER_VORLAUF_FUSSBODENHEIZUNG, ANKER_VORLAUF_HEIZKOERPER]

const VORLAUF_ANKER_JE_HEIZKREIS: Record<HeizkreisArt, AnkerId> = {
  fussbodenheizung: ANKER_VORLAUF_FUSSBODENHEIZUNG,
  heizkoerper: ANKER_VORLAUF_HEIZKOERPER,
}
const HEIZKREIS_NAME: Record<HeizkreisArt, string> = {
  fussbodenheizung: 'Fußbodenheizung',
  heizkoerper: 'Heizkörper',
}

/**
 * Objekt der Kachel «Vorlauf · Rücklauf» (P-433-3 S2-8, Entscheid Gernot 25.10.2026): der eine Gerätewert sagt im
 * Bild, welche Heizflächen das Haus hat (Fußbodenheizung 30–35 °C, Heizkörper 50–70 °C) — gelesen aus dem Stammdatum
 * `vorlauftemperatur` über die Client-SoT ({@link heizkreisArt}); ohne Angabe das Hydraulikmodul. Heizkreise je Raum
 * sind ein späteres Konzept. P13 Gruppe 2: das Stammdatum wählt den ORT, nie OB der Wert erscheint.
 */
export function vorlaufAnker(inv: Investition): AnkerId {
  const art = heizkreisArt(inv.parameter)
  return art ? VORLAUF_ANKER_JE_HEIZKREIS[art] : ANKER_VORLAUF
}

/** Beschriftung der Karten-Zeile Vorlauf: «Vorlauf (Fußbodenheizung)» · «Vorlauf (Heizkörper)» · «Vorlauf». */
export function vorlaufBeschriftung(inv: Investition): string {
  const art = heizkreisArt(inv.parameter)
  return art ? `Vorlauf (${HEIZKREIS_NAME[art]})` : 'Vorlauf'
}

/** nodeW der kompakten Dims — aus der Layout-SoT, nicht getippt. */
const KOMPAKT_NODE_W = computeDims(5).nodeW

/** Der Werttext einer Kachel für diese Dims (P-433-3 S2-6): in den kompakten Dims der kurze, sonst der volle. */
export function kachelWertText(kachel: Pick<UeberblickKachel, 'wertText' | 'wertTextKompakt'>, dims: Pick<LayoutDims, 'nodeW'>): string {
  return dims.nodeW <= KOMPAKT_NODE_W && kachel.wertTextKompakt ? kachel.wertTextKompakt : kachel.wertText
}
/** P-433-3 S1 (Bauplan S1-3): Objekt der Kachel «Zusatzheizung» — Pufferspeicher mit Heizstab. */
export const ANKER_ZUSATZHEIZUNG: AnkerId = 'D'

/** Sole- und Grundwasser-Wärmepumpen stehen im Bild am Schrank (C). */
const SCHRANK_BAUARTEN: readonly string[] = ['sole_wasser', 'grundwasser']

/** Innengeräte-Anker in Listenreihenfolge; ab dem vierten an N (Gruppe im Layout). */
const INNEN_ANKER: readonly AnkerId[] = ['L', 'M', 'N']

/** Objekt, an dem Leistung und Modus dieser Wärmepumpe stehen. */
export function geraeteAnker(inv: Investition): AnkerId {
  const p = inv.parameter
  if (istLuftLuft(p)) return 'O'
  if (istBrauchwasser(p)) return 'F'
  if (SCHRANK_BAUARTEN.includes(String(p?.[PARAM_WAERMEPUMPE.WP_ART] ?? ''))) return 'C'
  // Luft/Wasser — und Altbestand ohne Bauart (Vorbelegung `luft_wasser`, s. `istLuftLuft`).
  return 'A'
}

/** Kühlt dieses Gerät passiv (Stammdatum `kuehlung_art`, B6)? */
export function kuehltPassiv(inv: Investition | undefined): boolean {
  return istKuehlungPassiv(inv?.parameter?.[PARAM_WAERMEPUMPE.KUEHLUNG_ART] as string | undefined)
}

/** Modus im Klartext — Label vom Backend-Kanon; bei passiver Kühlung «Kühlen (passiv)»; bei gemessener
 *  Ruhe «· Leerlauf» (P-433-1, dieselbe Funktion `modusKlartext` wie Energiefluss und Chip). */
export function modusText(
  k: Pick<LiveKomponente, 'betriebsmodus' | 'betriebsmodus_label' | 'betriebsmodus_aktion_label'>,
  inv: Investition | undefined,
): string | null {
  return modusKlartext(k, istPassivGekuehlt(k, inv))
}

/** «(passiv)» gilt nur im Modus Kühlen eines passiv kühlenden Geräts. */
export function istPassivGekuehlt(k: Pick<LiveKomponente, 'betriebsmodus'>, inv: Investition | undefined): boolean {
  return k.betriebsmodus === 'kuehlen' && kuehltPassiv(inv)
}

/** Live-Knoten einer Wärmepumpe (`waermepumpe_<id>`, Key des Builders). */
export function wpKnoten(live: LiveDashboardResponse | null, invId: number): LiveKomponente | undefined {
  return live?.komponenten.find((k) => k.key === `waermepumpe_${invId}`)
}

/**
 * Strom heute dieses Geräts aus `heute_kwh_pro_komponente` — der exakte Key
 * `waermepumpe_<id>`; der Typ-Key `waermepumpe` nur, wenn es das einzige Gerät
 * ist (sonst trüge jedes Gerät die Summe aller). Eine Regel für Kachel und Karte.
 */
export function stromHeute(live: LiveDashboardResponse | null, invId: number, mehrere: boolean): number | null {
  const werte = live?.heute_kwh_pro_komponente
  if (!werte) return null
  return werte[`waermepumpe_${invId}`] ?? (mehrere ? null : werte['waermepumpe'] ?? null)
}

/**
 * Warmwasser-Temperatur eines Geräts (P-433-3 S1, E-P3-7): der Wert am Knoten `waermepumpe_<id>`.
 * Nur wenn **kein** Wärmepumpen-Knoten einen eigenen Wert trägt (älteres Backend, oder die Wärmepumpe
 * hat keinen Leistungssensor und damit keinen Knoten), gilt der Anlagenwert `warmwasser_temperatur_c`
 * (erste Wärmepumpe mit Wert) — so wie vor P-433-3. Eine Regel für Kachel und Karte.
 */
export function warmwasserC(live: LiveDashboardResponse | null, invId: number): number | null {
  if (!live) return null
  if (hatGeraeteWarmwasser(live)) return wpKnoten(live, invId)?.warmwasser_c ?? null
  return live.warmwasser_temperatur_c ?? null
}

function hatGeraeteWarmwasser(live: LiveDashboardResponse): boolean {
  return live.komponenten.some((k) => k.key.startsWith('waermepumpe_') && k.warmwasser_c != null)
}

/** Zusatzheizung läuft (Leistung > 0) — für den Chip-Zusatz der Karte. */
export function zusatzheizungAktiv(k: Pick<LiveKomponente, 'heizstab_w'> | undefined): boolean {
  return (k?.heizstab_w ?? 0) > 0
}

function geraeteKachel(inv: Investition, k: LiveKomponente, heute: number | null, referenz: string): UeberblickKachel {
  const kw = Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0)
  const color = getNodeColor(k)
  const isActive = kw > 0
  const modus = modusText(k, inv)
  const tip = [
    inv.bezeichnung,
    `Aktuell: ${fmtZahl(k.verbrauch_kw ?? 0, 2)} kW`,
    ...(modus ? [`Betrieb: ${modus}`] : []),
    ...(heute != null ? [`Heute: ${fmtZahl(heute, 1)} kWh`] : []),
    'Quelle: Live-Snapshot',
  ].join('\n')
  return {
    id: `geraet-${inv.id}`, art: 'geraet', anker: geraeteAnker(inv),
    label: inv.bezeichnung, icon: k.icon, color, isActive,
    wertText: formatPower(kw),
    // P-433-1 S1-4: dieselbe Modus-Zeile (Chip) wie im Live-Energiefluss.
    zweiteZeile: modusZeile(k, isActive, referenz, istPassivGekuehlt(k, inv)),
    tip, investitionId: inv.id, leistungKw: k.verbrauch_kw ?? 0,
  }
}

function innengeraetWert(g: LiveInnengeraet): string {
  if (g.ist_temperatur_c != null) return `${fmtZahl(g.ist_temperatur_c, 1)} °C`
  if (g.soll_temperatur_c != null) return `Soll ${fmtZahl(g.soll_temperatur_c, 1)} °C`
  return formatPower((g.leistung_w ?? 0) / 1000)
}

function innengeraetKachel(g: LiveInnengeraet, i: number, referenz: string): UeberblickKachel {
  const color = KATEGORIE_FARBEN.waermepumpe
  // Ohne Leistungswert sagt die Kachel nichts über „läuft" — Rollenfarbe.
  const isActive = g.leistung_w == null || g.leistung_w > 0
  const zweite = g.ist_temperatur_c != null && g.soll_temperatur_c != null
    ? `Soll ${fmtZahl(g.soll_temperatur_c, 1)} °C`
    : g.ist_temperatur_c != null && g.leistung_w != null ? formatPower(g.leistung_w / 1000) : null
  const tip = [
    g.bezeichnung,
    ...(g.ist_temperatur_c != null ? [`Raum: ${fmtZahl(g.ist_temperatur_c, 1)} °C`] : []),
    ...(g.soll_temperatur_c != null ? [`Soll: ${fmtZahl(g.soll_temperatur_c, 1)} °C`] : []),
    ...(g.leistung_w != null ? [`Leistung: ${fmtZahl(g.leistung_w, 0)} W`] : []),
    'Quelle: Live-Snapshot',
  ].join('\n')
  return {
    id: `innen-${g.investition_id}-${g.innengeraet_id}`, art: 'innengeraet',
    anker: INNEN_ANKER[Math.min(i, INNEN_ANKER.length - 1)],
    label: g.bezeichnung, icon: 'fan', color, isActive,
    wertText: innengeraetWert(g),
    zweiteZeile: zweite ? { text: zweite, fill: isActive ? color : referenz } : null,
    tip, investitionId: g.investition_id, innengeraet: g,
    leistungKw: g.leistung_w != null ? g.leistung_w / 1000 : null,
  }
}

/** Eine Wert-Kachel (B12): kein „aktiv", immer Rollenfarbe. */
function wertKachel(id: string, anker: AnkerId, label: string, icon: string, color: string, wertText: string, tip: string, investitionId: number | null): UeberblickKachel {
  return { id, art: 'wert', anker, label, icon, color, isActive: true, wertText, zweiteZeile: null, tip, investitionId }
}

/** «Vorlauf · Rücklauf» eines Geräts (P-433-3 S1) — `null` ohne beide Werte. */
function vorlaufKachel(inv: Investition, k: LiveKomponente, label: (was: string) => string): UeberblickKachel | null {
  const v = k.vorlauf_c ?? null
  const r = k.ruecklauf_c ?? null
  if (v == null && r == null) return null
  const beide = v != null && r != null
  const was = beide ? 'Vorlauf · Rücklauf' : v != null ? 'Vorlauf' : 'Rücklauf'
  const wert = beide ? `${fmtZahl(v, 1)} → ${fmtZahl(r, 1)} °C` : `${fmtZahl((v ?? r) as number, 1)} °C`
  // S2-6 (Lab-Sichtprobe 25.10.): «33,9 → 28,8 °C» füllt die kompakte Kachel (nodeW 80) randlos — dort ganze Grad.
  // Nur Anzeige-Rundung; Tooltip und Karte behalten eine Nachkommastelle.
  const kompakt = beide ? `${fmtZahl(v, 0)} → ${fmtZahl(r, 0)} °C` : undefined
  // Die Spreizung rechnet das Backend (`spreizung_k`, Layer) — der Client zeigt sie nur.
  const spreizung = k.spreizung_k ?? null
  const tip = [
    inv.bezeichnung,
    ...(v != null ? [`Vorlauf: ${fmtZahl(v, 1)} °C`] : []),
    ...(r != null ? [`Rücklauf: ${fmtZahl(r, 1)} °C`] : []),
    ...(spreizung != null ? [`Spreizung: ${fmtZahl(spreizung, 1)} K`] : []),
    // S2-8: die Kachel steht am Heizkreis des Hauses — gemessen wird am Gerät.
    'Vorlauf der Wärmepumpe am Gerät gemessen',
    'Quelle: Live-Snapshot',
  ].join('\n')
  return {
    ...wertKachel(`wert-vorlauf-${inv.id}`, vorlaufAnker(inv), label(was), 'thermometer', CHART_COLORS.wpWaerme,
      wert, tip, inv.id),
    ...(kompakt ? { wertTextKompakt: kompakt } : {}),
  }
}

/** «Zusatzheizung» eines Geräts (P-433-3 S1) — nur mit Wert, auch bei 0 W (der Sensor meldet: steht). */
function zusatzheizungKachel(inv: Investition, k: LiveKomponente, label: (was: string) => string): UeberblickKachel | null {
  if (k.heizstab_w == null) return null
  const w = k.heizstab_w
  return wertKachel(`wert-zusatzheizung-${inv.id}`, ANKER_ZUSATZHEIZUNG, label('Zusatzheizung'), 'heater',
    CHART_COLORS.wpStrom, formatPower(w / 1000),
    `${inv.bezeichnung}\nZusatzheizung: ${fmtZahl(w, 0)} W\nQuelle: Live-Snapshot`, inv.id)
}

/** «Wärme heute» eines Geräts (P-433-2c) — aus dem Tag-Detail (`wp_geraete[].waerme_kwh`, Rechenstelle des
 *  Wärme/Klima-Blocks), am Heizkreis-Objekt wie «Vorlauf · Rücklauf» ({@link vorlaufAnker}); `null` ohne Wert.
 *  Eine Zweitzeile «Heizen · WW» gibt es nicht: die Gerätezeile liefert Wärme je Funktion nicht. */
function waermeKachel(inv: Investition, tag: TagDetail | null | undefined, label: string): UeberblickKachel | null {
  const kwh = tag?.wp_geraete?.find((z) => z.investition_id === inv.id)?.waerme_kwh ?? null
  if (kwh == null) return null
  return wertKachel(`wert-waerme-${inv.id}`, vorlaufAnker(inv), label, 'flame', CHART_COLORS.wpWaerme,
    `${fmtZahl(kwh, 1)} kWh`, `${inv.bezeichnung}\nWärme heute: ${fmtZahl(kwh, 1)} kWh\nQuelle: Tag-Detail (Wärmemengenzähler)`,
    inv.id)
}

const hatInnenWert = (g: LiveInnengeraet) =>
  g.leistung_w != null || g.ist_temperatur_c != null || g.soll_temperatur_c != null

/**
 * Die Kacheln des Überblicks und die Liste dessen, was ohne Kachel bleibt.
 * Reine Funktion — kein Hook, kein Abruf.
 */
export function baueUeberblickKacheln({ geraete, live, wetter, referenz, tag }: KachelEingaben): KachelErgebnis {
  const kacheln: UeberblickKachel[] = []
  const ohneSensor: string[] = []
  const mehrere = geraete.length > 1
  const name = (inv: Investition, was: string) => (mehrere ? `${was} ${inv.bezeichnung}` : was)

  for (const inv of geraete) {
    const k = wpKnoten(live, inv.id)
    if (k) kacheln.push(geraeteKachel(inv, k, stromHeute(live, inv.id, mehrere), referenz))
    else ohneSensor.push(name(inv, 'Leistung'))

    const innen = (live?.innengeraete ?? []).filter((g) => g.investition_id === inv.id && hatInnenWert(g))
    innen.forEach((g, i) => kacheln.push(innengeraetKachel(g, i, referenz)))
    // Angelegte Innengeräte (Stammdatum, nicht die Bauart) ohne einen einzigen Wert.
    const angelegt = inv.parameter?.[PARAM_WAERMEPUMPE.INNENGERAETE]
    if (innen.length === 0 && Array.isArray(angelegt) && angelegt.length > 0) {
      ohneSensor.push(name(inv, 'Innengeräte'))
    }
  }

  // Warmwasser-Temperatur je Gerät (P-433-3 S1, E-P3-7): eine Kachel je Wärmepumpe mit eigenem Wert
  // (`warmwasser_c` am Knoten). Trägt kein Knoten einen, steht wie bisher EINE Kachel mit dem Anlagenwert
  // (`warmwasserC`). Fehlt beides, steht er in der Zeile — unabhängig von der Bauart (P13: was ein Gerät
  // liefern kann, sagt die Zuordnung; das Bild zeigt den Speicher ohnehin).
  const wwTip = (t: number, wer: string) => `${wer}\nAktuell: ${fmtZahl(t, 1)} °C\nQuelle: Live-Snapshot`
  if (live && hatGeraeteWarmwasser(live)) {
    for (const inv of geraete) {
      const t = warmwasserC(live, inv.id)
      if (t == null) continue
      kacheln.push(wertKachel(`wert-warmwasser-${inv.id}`, 'E', name(inv, 'Warmwasser'), 'droplets',
        CHART_COLORS.wpWarmwasser, `${fmtZahl(t, 1)} °C`, wwTip(t, name(inv, 'Warmwasser-Temperatur')), inv.id))
    }
  } else if (live?.warmwasser_temperatur_c != null) {
    const t = live.warmwasser_temperatur_c
    kacheln.push(wertKachel('wert-warmwasser', 'E', 'Warmwasser', 'droplets', CHART_COLORS.wpWarmwasser,
      `${fmtZahl(t, 1)} °C`, wwTip(t, 'Warmwasser-Temperatur'), null))
  } else {
    ohneSensor.push('Warmwasser-Temperatur')
  }

  for (const inv of geraete) {
    const heute = stromHeute(live, inv.id, mehrere)
    if (heute != null) {
      const label = mehrere ? `Strom ${inv.bezeichnung}` : 'Strom heute'
      kacheln.push(wertKachel(`wert-strom-${inv.id}`, 'I', label, 'zap', CHART_COLORS.wpStrom,
        `${fmtZahl(heute, 1)} kWh`, `${inv.bezeichnung}\nStrom heute: ${fmtZahl(heute, 1)} kWh\nQuelle: HA-LTS (Tageszähler)`, inv.id))
    } else {
      ohneSensor.push(name(inv, 'Strom heute'))
    }
  }

  // P-433-3 S1: Vorlauf/Rücklauf und Zusatzheizung je Gerät — nur mit Wert, nie in der «Ohne Sensor»-Zeile (G7).
  for (const inv of geraete) {
    const k = wpKnoten(live, inv.id)
    if (!k) continue
    const label = (was: string) => name(inv, was)
    const vorlauf = vorlaufKachel(inv, k, label)
    if (vorlauf) kacheln.push(vorlauf)
    const zusatz = zusatzheizungKachel(inv, k, label)
    if (zusatz) kacheln.push(zusatz)
  }

  // P-433-2c: «Wärme heute» je Gerät aus dem Tag-Detail — nur mit Wert, nie in der «Ohne Sensor»-Zeile (G7: die
  // Zeile nennt nur Live-Sensoren). Kein Live-Knoten nötig: die Menge kommt aus den Tageszählern.
  for (const inv of geraete) {
    const waerme = waermeKachel(inv, tag, mehrere ? `Wärme ${inv.bezeichnung}` : 'Wärme heute')
    if (waerme) kacheln.push(waerme)
  }

  const aussen = wetter?.aktuell?.temperatur_c
  if (aussen != null) {
    kacheln.push(wertKachel('wert-aussen', 'HIMMEL', 'Außen', 'thermometer', CHART_COLORS.temperatur,
      `${fmtZahl(aussen, 1)} °C`, `Außentemperatur\nAktuell: ${fmtZahl(aussen, 1)} °C\nQuelle: Wetterdienst`, null))
  }
  // Die Außentemperatur fehlt nicht wegen eines Sensors (sie kommt vom
  // Wetterdienst über die Koordinaten) — sie gehört nicht in die Zeile.

  // Vor der ersten Live-Antwort ist nichts „ohne Sensor", nur noch nicht geladen.
  return { kacheln, ohneSensor: live ? ohneSensor : [] }
}
