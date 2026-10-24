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
 * ab dem vierten an N (das Layout gruppiert sie); Warmwasser-Temperatur → E;
 * Strom heute je Gerät → I; Außentemperatur → Himmel.
 *
 * ⚠ **P13 (ADR-002), Gruppe 2 «Anzeige-Ort nach Bauart»:** die Bauart wählt
 * hier nur, AN WELCHEM OBJEKT eine Kachel steht — nie, OB ein Wert gezeigt
 * wird (das entscheidet allein, ob er geliefert wird). Gelesen über die
 * Client-SoT `lib/investitionParameter.ts` (`istLuftLuft`, `istBrauchwasser`,
 * Parameter-Namen), kein zweiter Bauart-Leser. Klassifiziert in
 * `scripts/check-bauart-roh.mjs::KLASSIFIZIERT`.
 */
import type { LiveDashboardResponse, LiveInnengeraet, LiveKomponente, LiveWetterResponse } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'
import { CHART_COLORS, KATEGORIE_FARBEN, fmtZahl } from '../../../lib'
import { PARAM_WAERMEPUMPE, istBrauchwasser, istKuehlungPassiv, istLuftLuft } from '../../../lib/investitionParameter'
import { formatPower, getNodeColor } from '../../live/EnergieFluss'
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
}

export interface KachelEingaben {
  /** Alle Wärmepumpen der Anlage (E-P2-2: Kacheln aller Geräte im Bild). */
  geraete: Investition[]
  live: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  /** Referenzfarbe des Themas für inaktive Zeilen (`useChartTheme().referenz`). */
  referenz: string
}

export interface KachelErgebnis {
  kacheln: UeberblickKachel[]
  /** Was keine Kachel hat, weil kein Wert kommt — in Anzeige-Reihenfolge. */
  ohneSensor: string[]
}

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

const hatInnenWert = (g: LiveInnengeraet) =>
  g.leistung_w != null || g.ist_temperatur_c != null || g.soll_temperatur_c != null

/**
 * Die Kacheln des Überblicks und die Liste dessen, was ohne Kachel bleibt.
 * Reine Funktion — kein Hook, kein Abruf.
 */
export function baueUeberblickKacheln({ geraete, live, wetter, referenz }: KachelEingaben): KachelErgebnis {
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

  // Warmwasser-Temperatur: die Live-Antwort trägt EINEN Wert (erste Wärmepumpe
  // mit Zuordnung, Builder) — deshalb eine Kachel, nicht je Gerät. Fehlt er,
  // steht er in der Zeile — unabhängig von der Bauart (P13: was ein Gerät
  // liefern kann, sagt die Zuordnung; das Bild zeigt den Speicher ohnehin).
  if (live?.warmwasser_temperatur_c != null) {
    const t = live.warmwasser_temperatur_c
    kacheln.push(wertKachel('wert-warmwasser', 'E', 'Warmwasser', 'droplets', CHART_COLORS.wpWarmwasser,
      `${fmtZahl(t, 1)} °C`, `Warmwasser-Temperatur\nAktuell: ${fmtZahl(t, 1)} °C\nQuelle: Live-Snapshot`, null))
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
