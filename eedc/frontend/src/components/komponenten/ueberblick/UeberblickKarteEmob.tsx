/**
 * UeberblickKarteEmob — «Auf einen Blick» der Hub-Typ-Seiten **Wallbox** und **E-Auto** (P-433-2b K1, Bauplan E4;
 * Definitions-Blatt Fassung 3 §1/§2/§4). Ein Modul, zwei Zweige nach `inv.typ`; Gestalt wie die Wärme-Karte
 * (`UeberblickKarte`: `Card`, `data-karte`, `KPI_WERT_SCHRIFT`, Anlagen-Ring, `Zeile`) und im Stil von Matheks
 * Verbraucher-Karte (#433: Kopfzeile mit **einem** Chip, Leistungszeile, Detailblock).
 *
 * Bis zu drei Karten wie bei der Wärmepumpe — in K1 zwei:
 * 1. **Gerätekarte** (`data-karte="geraet"`): Wallbox — Name, Chip «Lädt · PV» (gemessener Ladezustand + Lademodus,
 *    `ladezustandKlartext`; Farbe der Funktion, **keine Rahmenfarbe**, K-3), Ladeleistung groß (bei Abgabe «Abgabe ins
 *    Haus»), Anlagen-Ring, Fahrzeugzeile(n) mit Ladestand-Leiste und Zielmarke, Ziel · Restzeit, eine Fußzeile
 *    «3 Phasen · 16 A · 9,8 kWh in dieser Sitzung · 2 h 10 min», Link «Hersteller-Oberfläche öffnen» (K-10).
 *    E-Auto — Name, eigener Zustands-Chip **nur**, wenn das Auto an keiner Wallbox steht (Leitsatz 8), Chip
 *    «Dienstwagen», Ladestand groß mit Leiste und Ziel, Reichweite, Ring, Ort und Standort (Zone), Ladeleistung nur mit
 *    eigenem Knoten (W3).
 * 2. **«Heute»** (`data-karte="heute"`): Ladung heute und PV-Ladung heute «(Anlage)» aus dem Tag-Detail. Seit
 *    P-433-2b K4 trägt das Tag-Detail die Tagesmengen je Gerät (`emob_heute`): die Ladung kommt von dort (Live-Tageswert
 *    nur Rückfall, D-K4-2; am Auto nur mit eigenem Knoten, K-6), die Wallbox bekommt die **Kopfzahl «PV-Anteil heute»**
 *    mit Herleitung «9,8 kWh PV ÷ 14,7 kWh» (nur gemessen, beide Mengen aus dem Tag-Detail, Layer
 *    `pv_anteil_gemessen_prozent`; ohne sie heißt die Karte «Heute»), das E-Auto die Zeilen «Gefahren heute» und
 *    «Fahrverbrauch heute» (Tages-Δ der Kanal-Stunden). Die Gerätekarte E-Auto zeigt den «Kilometerstand».
 * 3. **«Betrieb heute»** (`data-karte="betrieb-heute"`, P-433-2b K3): Stunden je Zustand des Tages aus der
 *    Zustands-Mitschrift (`TagDetail.emob_betrieb`) — Wallbox «Lädt · Verbunden · Wartet · Fertig» und «Ladevorgänge
 *    heute», E-Auto Laden (lädt · lädt DC · verbunden) und Standort (zu Hause · unterwegs). Zeile nur mit Stunden > 0,
 *    «Heute kein Betrieb» bei gemessener 0, die Karte fehlt ohne Mitschrift. Farbe = Funktion (`funktionsFarbe`,
 *    Ruhezustände Grau), keine neue Farbe, keine Rahmenfarbe; Klartext und Reihenfolge aus dem Backend.
 *
 * **Regeln:** Zeilen und Karten nur mit Wert (kein «–», Mathek-Regel); Zustand nur gemessen — ohne Feld kein Chip
 * (K-2); welches Auto nur aus der Zuordnung des Backends (`fahrzeuge_zuordnung`), bei «geschätzt» alle Autos mit
 * `SATZ_ZUORDNUNG_UNBEKANNT` (K-5); keine Netz-Ladung, keine Kosten, kein CO₂ (B9). ⛔ Der Client rechnet nichts
 * (P12): jede Zahl kommt fertig aus dem Backend, hier wird nur formatiert.
 *
 * **P-433-2b K2a (Bauplan K2 E4):** meldet die Steuerung das Fahrzeug (`fahrzeuge_quelle: 'steuerung'`), nennt die
 * Wallbox-Karte genau das gemeldete Auto (Tooltip «gemeldet von der Steuerung», bei einem Dienstwagen «Dienstwagen
 * ‹Name›»), «Gastfahrzeug lädt/verbunden» (`gast`) oder «Fahrzeug der Steuerung unbekannt» (`fahrzeug_unbekannt`;
 * D2: der gemeldete Name steht nicht hier, sondern im Daten-Checker). «Alle Autos» bei «geschätzt» sind nur die der
 * «geschätzt»-Wallboxen — ein von der Steuerung gemeldetes Auto steht dort nicht noch einmal (W4). Keine Farbe für
 * den Gast, keine Rahmenfarbe (K2-11).
 */
import { Fragment, type ReactNode } from 'react'
import { Parkbar, usePark } from '../../park'
import { KPI_WERT_SCHRIFT } from '../../ui/KPICard'
import LadestandLeiste from '../../ui/LadestandLeiste'
import ModusChip, { ZusatzChip, ladezustandKlartext } from '../../ui/ModusChip'
import { fmtDauer, fmtStundenDauer, fmtZahl } from '../../../lib'
import { funktionsFarbe } from '../../../lib/funktionsFarben'
import { PARAM_WALLBOX } from '../../../lib/investitionParameter'
import { SATZ_ZUORDNUNG_UNBEKANNT, formatPower } from '../../live/EnergieFluss'
import type { LiveDashboardResponse, LiveFahrzeug, LiveKomponente } from '../../../api/liveDashboard'
import type { EmobBetriebZeile, EmobHeuteZeile, TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'
import { AnlagenRing, Karte, KartenKopf, Zeile } from './UeberblickKarte'
import { UEBERBLICK_ALT_KARTE, type UeberblickKartenTeile } from './ueberblickPark'

export interface UeberblickKarteEmobProps {
  inv: Investition
  live: LiveDashboardResponse | null
  tag: TagDetail | null
  /** Mehr als ein Gerät des Typs? Dann zählt nur der exakte Tages-Key (wie `stromHeute`). */
  mehrereGeraete: boolean
  /** P-433-2b S1b: steht die Karte neben dem Schaubild (Desktop ⅓-Spalte)? Dann stehen die Karten ab `xl` untereinander
   *  wie bei der Wärmepumpe; ist das Schaubild geparkt, nebeneinander in voller Breite. */
  nebenSchaubild?: boolean
}

/** Fußzeile der Wallbox-Karte ohne jedes K1-Feld (A7-Vokabular: «zugeordnet»). */
export const FUSSZEILE_WALLBOX = 'Zustand, Sitzung und Ladestrom erscheinen hier, sobald zugeordnet'
/** Fußzeile der Auto-Karte ohne jedes K1-Feld. */
export const FUSSZEILE_EAUTO = 'Zustand, Reichweite und Ziel erscheinen hier, sobald zugeordnet'
/** Text des Links zur Hersteller-Oberfläche (K-10: fester Text, kein Hostname). */
export const OBERFLAECHE_TEXT = 'Hersteller-Oberfläche öffnen'
/** Tooltip der PV-Ladung heute — ein Anlagenwert aus dem Tag-Detail, kann der Live-Ladung vorlaufen (Ü5). */
export const PV_LADUNG_TOOLTIP = 'PV-Anteil aller Ladungen der Anlage heute (Tag-Detail, Stand des letzten Zähler-Snapshots) — kein Wert je Gerät'
/** Tooltip der Ladung heute — derselbe Tageswert wie der Energiefluss-Tooltip. */
export const LADUNG_TOOLTIP = 'Tageswert dieses Geräts (HA-Langzeitstatistik bzw. Tageszähler), derselbe wie im Energiefluss'
/** P-433-2b K4 (K4-6): Tooltip der Ladung heute, wenn die Zahl aus dem Tag-Detail kommt (Vorrang vor dem Live-Pfad). */
export const LADUNG_TAG_TOOLTIP = 'Tageswert aus Zähler'
/** P-433-2b K4: Tooltip der Kopfzahl — nur gemessen, beide Mengen aus dem Tag-Detail (Blatt P2). */
export const PV_ANTEIL_TOOLTIP = 'Gemessener PV-Ladezähler ÷ Ladezähler dieser Wallbox heute (nur abgeschlossene Zählerstände)'

/** Ein Ladezustand «kein Fahrzeug» — dann sagt die Sitzung «letzte Sitzung» (Blatt §1a). */
const KEIN_FAHRZEUG = 'kein_fahrzeug'
/** Der Ladezustand «lädt» — Gast-Zeile «lädt» statt «verbunden». */
const LAEDT = 'laedt'

/** P-433-2b K3: Tooltip der Karte «Betrieb heute» (Grenze «ab Zuordnung» im Handbuch). */
export const BETRIEB_EMOB_TOOLTIP = 'Stunden je Zustand aus der stündlichen Mitschrift, ab Zuordnung'
/** P-433-2b K3: eine gemessene 0 in allen Werten ist eine Auskunft (P4). */
export const KEIN_BETRIEB = 'Heute kein Betrieb'
/** Gruppentitel am E-Auto (zwei Felder auf einer Karte). */
const GRUPPE_TITEL: Record<string, string> = { ladezustand_fahrzeug: 'Laden', zu_hause: 'Standort' }

/** P-433-2b K2a (K2-2): die Steuerung kennt kein Fahrzeug, aber eines lädt bzw. hängt dran. */
export const GAST_LAEDT = 'Gastfahrzeug lädt'
export const GAST_VERBUNDEN = 'Gastfahrzeug verbunden'
/** P-433-2b K2a (K2-10, D2): die Steuerung nennt ein Fahrzeug, das kein E-Auto als Kennung trägt — ohne den Namen. */
export const FAHRZEUG_UNBEKANNT = 'Fahrzeug der Steuerung unbekannt'
export const FUSSZEILE_UNBEKANNT = 'Kennung am E-Auto eintragen — Daten-Checker'
/** Tooltip an der Fahrzeugzeile, wenn die Steuerung das Fahrzeug gemeldet hat. */
export const TOOLTIP_STEUERUNG = 'gemeldet von der Steuerung'

// ── Lesehilfen (rein, exportiert für Proben) ─────────────────────────────────

export function wallboxKnoten(live: LiveDashboardResponse | null, invId: number): LiveKomponente | undefined {
  return live?.komponenten.find((k) => k.key === `wallbox_${invId}`)
}

export function eautoKnoten(live: LiveDashboardResponse | null, invId: number): LiveKomponente | undefined {
  return live?.komponenten.find((k) => k.key === `eauto_${invId}`)
}

/** Wo steht das Auto in der Live-Antwort? An einer Wallbox (mit deren Zuordnung) oder in `fahrzeuge_ohne_wallbox`. */
export function fahrzeugImLive(
  live: LiveDashboardResponse | null, invId: number,
): { fahrzeug: LiveFahrzeug; wallbox: LiveKomponente | null; zuordnung: 'eindeutig' | 'geschaetzt' | null } | null {
  for (const k of live?.komponenten ?? []) {
    const f = k.fahrzeuge?.find((x) => x.investition_id === invId)
    if (f) return { fahrzeug: f, wallbox: k, zuordnung: k.fahrzeuge_zuordnung ?? null }
  }
  const frei = live?.fahrzeuge_ohne_wallbox?.find((x) => x.investition_id === invId)
  return frei ? { fahrzeug: frei, wallbox: null, zuordnung: null } : null
}

/** Alle Autos der «geschätzt»-Wallboxen (die Karte nennt alle, nicht eines). Seit K2a nur diese (W4): ein von der
 * Steuerung gemeldetes Auto steht an seiner Wallbox «eindeutig» und nicht noch einmal in der Liste der anderen. */
export function alleAutosAnWallboxen(live: LiveDashboardResponse | null): LiveFahrzeug[] {
  const gesehen = new Set<number>()
  const out: LiveFahrzeug[] = []
  for (const k of live?.komponenten ?? []) {
    if (k.fahrzeuge_zuordnung !== 'geschaetzt') continue
    for (const f of k.fahrzeuge ?? []) {
      if (!gesehen.has(f.investition_id)) { gesehen.add(f.investition_id); out.push(f) }
    }
  }
  return out
}

/** Phasen, Strom und Restzeit sagen nur mit Wert > 0 etwas («0 Phasen · 0 A» an einer verbundenen, nicht ladenden
 *  Wallbox ist keine Aussage; Lab rc13, 28.10.2026). */
const mitWert = (x: number | null | undefined): x is number => x != null && x > 0

/** «3 Phasen · 16 A · 9,8 kWh in dieser Sitzung · 2 h 10 min» — jeder Teil nur mit Feld, Phasen und Strom nur > 0;
 *  ohne Fahrzeug «letzte Sitzung». */
export function sitzungsTeile(k: LiveKomponente | undefined): string[] {
  if (!k) return []
  const kwh = k.sitzung?.kwh ?? null
  if (k.ladezustand === KEIN_FAHRZEUG) return kwh != null ? [`letzte Sitzung ${fmtZahl(kwh, 1)} kWh`] : []
  const teile: string[] = []
  if (mitWert(k.phasen_aktiv)) teile.push(`${fmtZahl(k.phasen_aktiv, 0)} ${k.phasen_aktiv === 1 ? 'Phase' : 'Phasen'}`)
  if (mitWert(k.ladestrom_a)) teile.push(`${fmtZahl(k.ladestrom_a, 0)} A`)
  if (kwh != null) teile.push(`${fmtZahl(kwh, 1)} kWh in dieser Sitzung`)
  if (k.sitzung?.dauer_s != null) teile.push(fmtDauer(k.sitzung.dauer_s))
  return teile
}

/** «90 % · noch 1 h 20 min» — Ziel und Restzeit der Steuerung bzw. des Autos, jeder Teil nur mit Wert, die Restzeit nur > 0
 *  (das Ziel bleibt auch ohne Restzeit). */
export function zielText(ziel: number | null | undefined, restzeitMin: number | null | undefined): string | null {
  const teile = [
    ziel != null ? `${fmtZahl(ziel, 0)} %` : null,
    mitWert(restzeitMin) ? `noch ${fmtDauer(restzeitMin * 60)}` : null,
  ].filter((t): t is string => t != null)
  return teile.length > 0 ? teile.join(' · ') : null
}

/** Die Adresse der Hersteller-Oberfläche (Stammdatum, K-10) — nur `http(s)`, sonst kein Link. */
export function oberflaecheUrl(inv: Investition): string | null {
  const roh = (inv.parameter as Record<string, unknown> | null | undefined)?.[PARAM_WALLBOX.OBERFLAECHE_URL]
  if (typeof roh !== 'string') return null
  const url = roh.trim()
  return /^https?:\/\//i.test(url) ? url : null
}

/** P-433-2b K4: die Tag-Detail-Zeile dieses Geräts (`emob_heute`), sonst `null`. */
export function heuteZeile(tag: TagDetail | null, invId: number): EmobHeuteZeile | null {
  return (tag?.emob_heute ?? []).find((z) => z.investition_id === invId) ?? null
}

/** Herleitung der Kopfzahl «9,8 kWh PV ÷ 14,7 kWh» — aus denselben zwei Zahlen des Backends, nur formatiert. */
export function herleitungPvAnteil(pvKwh: number | null | undefined, ladungKwh: number | null | undefined): string | null {
  if (pvKwh == null || ladungKwh == null) return null
  return `${fmtZahl(pvKwh, 1)} kWh PV ÷ ${fmtZahl(ladungKwh, 1)} kWh`
}

/** Ladung heute aus `heute_kwh_pro_komponente` — der exakte Key; der Typ-Key nur beim einzigen Gerät. Seit K4 nur der
 *  **Rückfall** ohne Tageswert im Tag-Detail (`emob_heute`, ein Pfad je Karte, D-K4-2). Exportiert für die Zählerkachel
 *  der Szene «Ladepunkt» (P-433-2b S1b, `emobKachelAnker.ts`) — dieselbe Regel. */
export function ladungHeute(live: LiveDashboardResponse | null, key: string, typKey: string, mehrere: boolean): number | null {
  const werte = live?.heute_kwh_pro_komponente
  if (!werte) return null
  return werte[key] ?? (mehrere ? null : werte[typKey] ?? null)
}

// ── Bausteine ────────────────────────────────────────────────────────────────

function Kopf({ name, children }: { name: string; children?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm font-semibold text-gray-900 dark:text-white truncate min-w-0">{name}</span>
      <div className="flex items-center gap-1 shrink-0">{children}</div>
    </div>
  )
}

function GrosseZahl({ titel, wert, data }: { titel: string; wert: string; data: string }) {
  return (
    <div data-zeile={data} className="min-w-0">
      <div className="text-xs text-gray-500 dark:text-gray-400">{titel}</div>
      <div className={`${KPI_WERT_SCHRIFT} font-bold text-gray-900 dark:text-white whitespace-nowrap`}>{wert}</div>
    </div>
  )
}

function Fusszeile({ children }: { children: ReactNode }) {
  return <p className="text-xs text-gray-400 dark:text-gray-500" data-fusszeile>{children}</p>
}

/** Eine Fahrzeugzeile der Wallbox-Karte: «Smart #1 · 62 % · 312 km · Verbunden» und die Leiste mit Zielmarke.
 * `steuerung` (K2a): die Steuerung hat das Auto gemeldet — Tooltip, bei einem Dienstwagen «Dienstwagen ‹Name›». */
function FahrzeugZeile({ f, zielWallbox, steuerung = false }: { f: LiveFahrzeug; zielWallbox: number | null; steuerung?: boolean }) {
  const teile = [
    steuerung && f.dienstwagen ? `Dienstwagen ${f.label}` : f.label,
    f.soc != null ? `${fmtZahl(f.soc, 0)} %` : null,
    f.reichweite_km != null ? `${fmtZahl(f.reichweite_km, 0)} km` : null,
    f.ladezustand_label ?? null,
  ].filter((t): t is string => t != null)
  return (
    <div className="space-y-1" data-fahrzeug={f.investition_id}>
      <div className="text-sm text-gray-700 dark:text-gray-300" data-zeile="fahrzeug" title={steuerung ? TOOLTIP_STEUERUNG : undefined}>{teile.join(' · ')}</div>
      {f.soc != null && <LadestandLeiste soc={f.soc} ziel={f.ziel_prozent ?? zielWallbox} />}
    </div>
  )
}

function OberflaecheLink({ url }: { url: string }) {
  // K-10: ein Link ohne Rahmen (keine Schaltfläche) — eedc wirkt nicht nach außen, es öffnet nur die Seite.
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary-700 dark:text-primary-300 hover:underline" data-oberflaeche-link>
      {OBERFLAECHE_TEXT}
    </a>
  )
}

/** Die Eingänge der Karte «Heute» — eine Stelle für die Karte und ihre Park-Hülle (S1c). */
interface HeuteDaten { ladung: number | null; pvLadung: number | null; zeile: EmobHeuteZeile | null }

function heuteDaten({ inv, live, tag, mehrereGeraete }: UeberblickKarteEmobProps): HeuteDaten {
  // K-6/W3: Ladung heute am Auto nur mit eigenem Knoten — sonst stünde die Wallbox-Energie zweimal da.
  const ladung = inv.typ === 'wallbox'
    ? ladungHeute(live, `wallbox_${inv.id}`, 'wallbox', mehrereGeraete)
    : (eautoKnoten(live, inv.id) ? ladungHeute(live, `eauto_${inv.id}`, 'eauto', true) : null)
  return { ladung, pvLadung: tag?.emob_ladung_pv_kwh ?? null, zeile: heuteZeile(tag, inv.id) }
}

/** Hat die Karte «Heute» einen Wert? */
function heuteDa({ ladung, pvLadung, zeile }: HeuteDaten): boolean {
  return zeile?.ladung_kwh != null || ladung != null || pvLadung != null || zeile?.pv_anteil_prozent != null
    || zeile?.km != null || zeile?.fahrverbrauch_kwh != null
}

/** Welche datenabhängigen Karten erscheinen? (S1c: dieselbe Antwort für die Hüllen und die Meldung des Blocks.) */
export function emobKartenTeile(props: UeberblickKarteEmobProps): UeberblickKartenTeile {
  return { heute: heuteDa(heuteDaten(props)), betrieb: betriebZeilen(props.tag, props.inv.id).length > 0 }
}

function HeuteKarte({ ladung, pvLadung, zeile }: HeuteDaten) {
  // K4-6 (D-K4-2): trägt das Tag-Detail die Ladung, zeigt die Karte diese Zahl; der Live-Wert ist nur Rückfall.
  const ausTag = zeile?.ladung_kwh != null
  const ladungAnzeige = ausTag ? zeile!.ladung_kwh! : ladung
  const anteil = zeile?.pv_anteil_prozent ?? null
  const km = zeile?.km ?? null
  const fahrverbrauch = zeile?.fahrverbrauch_kwh ?? null
  if (!heuteDa({ ladung, pvLadung, zeile })) return null
  const herleitung = anteil != null ? herleitungPvAnteil(zeile?.ladung_pv_kwh, zeile?.ladung_kwh) : null
  return (
    <Karte name="heute">
      {anteil != null ? (
        <div title={PV_ANTEIL_TOOLTIP} className="cursor-help">
          <KartenKopf text="PV-Anteil heute" />
          <div className={`${KPI_WERT_SCHRIFT} font-bold text-gray-900 dark:text-white`} data-zeile="pv-anteil-heute">{fmtZahl(anteil, 0)} %</div>
          {herleitung && <div className="text-xs text-gray-500 dark:text-gray-400" data-herleitung>{herleitung}</div>}
        </div>
      ) : (
        <KartenKopf text="Heute" />
      )}
      <div className="space-y-1">
        {ladungAnzeige != null && (
          <div title={ausTag ? LADUNG_TAG_TOOLTIP : LADUNG_TOOLTIP} className="cursor-help">
            <Zeile label="Ladung heute" data="ladung-heute">{fmtZahl(ladungAnzeige, 1)} kWh</Zeile>
          </div>
        )}
        {pvLadung != null && (
          <div title={PV_LADUNG_TOOLTIP} className="cursor-help">
            <Zeile label="PV-Ladung heute" data="pv-ladung-heute">{fmtZahl(pvLadung, 1)} kWh (Anlage)</Zeile>
          </div>
        )}
        {km != null && <Zeile label="Gefahren heute" data="gefahren-heute">{fmtZahl(km, 0)} km</Zeile>}
        {fahrverbrauch != null && <Zeile label="Fahrverbrauch heute" data="fahrverbrauch-heute">{fmtZahl(fahrverbrauch, 1)} kWh</Zeile>}
      </div>
    </Karte>
  )
}

// ── Wallbox ──────────────────────────────────────────────────────────────────

function WallboxFahrzeuge({ live, k }: { live: LiveDashboardResponse | null; k: LiveKomponente }) {
  if (k.fahrzeuge_zuordnung === 'geschaetzt') {
    const alle = alleAutosAnWallboxen(live)
    if (alle.length === 0) return null
    return (
      <div className="space-y-1" data-fahrzeuge="geschaetzt">
        {alle.map((f) => <FahrzeugZeile key={f.investition_id} f={f} zielWallbox={null} />)}
        <Fusszeile>{SATZ_ZUORDNUNG_UNBEKANNT}</Fusszeile>
      </div>
    )
  }
  const steuerung = k.fahrzeuge_quelle === 'steuerung'
  if (k.gast) {
    return (
      <div className="text-sm text-gray-700 dark:text-gray-300" data-fahrzeuge="gast" data-zeile="fahrzeug" title={TOOLTIP_STEUERUNG}>
        {k.ladezustand === LAEDT ? GAST_LAEDT : GAST_VERBUNDEN}
      </div>
    )
  }
  if (k.fahrzeug_unbekannt) {
    return (
      <div className="space-y-1" data-fahrzeuge="unbekannt">
        <div className="text-sm text-gray-700 dark:text-gray-300" data-zeile="fahrzeug" title={TOOLTIP_STEUERUNG}>{FAHRZEUG_UNBEKANNT}</div>
        <Fusszeile>{FUSSZEILE_UNBEKANNT}</Fusszeile>
      </div>
    )
  }
  const autos = k.fahrzeuge ?? []
  if (autos.length === 0) return null
  return (
    <div className="space-y-2" data-fahrzeuge="eindeutig">
      {autos.map((f) => <FahrzeugZeile key={f.investition_id} f={f} zielWallbox={k.ziel_prozent ?? null} steuerung={steuerung} />)}
    </div>
  )
}

function WallboxGeraeteKarte({ inv, live }: Pick<UeberblickKarteEmobProps, 'inv' | 'live'>) {
  const k = wallboxKnoten(live, inv.id)
  const abgabe = (k?.erzeugung_kw ?? 0) > 0
  const kw = k ? Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0) : null
  const chip = k ? ladezustandKlartext(k) : null
  const ev = live?.gauges?.find((g) => g.key === 'eigenverbrauch') ?? null
  const sitzung = sitzungsTeile(k)
  const ziel = zielText(k?.ziel_prozent, k?.restzeit_min)
  // Vor der ersten Live-Antwort fehlt nichts, es ist nur noch nicht geladen (Regel der Wärme-Karte). Ein zugeordnetes Feld
  // mit 0 (Phasen, Strom, Restzeit) steht nicht in der Zeile, ist aber zugeordnet — kein Fußzeilen-Hinweis.
  const nullWert = k?.phasen_aktiv != null || k?.ladestrom_a != null || k?.restzeit_min != null
  const ohneFelder = live != null && !chip && sitzung.length === 0 && ziel == null && !nullWert
  const url = oberflaecheUrl(inv)

  return (
    <Karte name="geraet">
      <Kopf name={inv.bezeichnung}>
        {k?.ladezustand && chip && <ModusChip modus={k.ladezustand} label={chip} />}
      </Kopf>
      {(kw != null || ev) && (
        <div className="flex items-center justify-between gap-3">
          {kw != null && <GrosseZahl titel={abgabe ? 'Abgabe ins Haus' : 'Ladeleistung jetzt'} wert={formatPower(kw)} data="leistung" />}
          {ev && <AnlagenRing wert={ev.wert} />}
        </div>
      )}
      {k && <WallboxFahrzeuge live={live} k={k} />}
      {ziel != null && <Zeile label="Ziel" data="ziel">{ziel}</Zeile>}
      {/* Lab rc13 (Handy 390): je Teil kein Umbruch — sonst bricht «30 min» zwischen Zahl und Einheit. */}
      {sitzung.length > 0 && (
        <p className="text-xs text-gray-600 dark:text-gray-400" data-zeile="sitzung">
          {sitzung.map((t, i) => <Fragment key={t}>{i > 0 && ' · '}<span className="whitespace-nowrap">{t}</span></Fragment>)}
        </p>
      )}
      {ohneFelder && <Fusszeile>{FUSSZEILE_WALLBOX}</Fusszeile>}
      {url && <OberflaecheLink url={url} />}
    </Karte>
  )
}

// ── «Betrieb heute» (P-433-2b K3) ───────────────────────────────────────────

/** Die Zeilen des Tag-Details für dieses Gerät (Reihenfolge des Backends). */
export function betriebZeilen(tag: TagDetail | null, invId: number): EmobBetriebZeile[] {
  return (tag?.emob_betrieb ?? []).filter((z) => z.investition_id === invId)
}

/** Karte «Betrieb heute» der E-Mobilität — eine eigene Komponente neben der WP-Karte (`UeberblickKarte.BetriebKarte`
 *  kennt Betriebsarten und passives Kühlen). Ohne Zeile keine Karte. */
export function BetriebKarteEmob({ zeilen }: { zeilen: EmobBetriebZeile[] }) {
  if (zeilen.length === 0) return null
  const gruppen = zeilen.map((z) => ({ z, werte: Object.keys(z.stunden).filter((w) => (z.stunden[w] ?? 0) > 0) }))
  const ohneBetrieb = gruppen.every((g) => g.werte.length === 0)
  const wechsel = zeilen.find((z) => z.wechsel != null)?.wechsel ?? null
  const mitTitel = zeilen.length > 1
  return (
    <Karte name="betrieb-heute">
      <KartenKopf text="Betrieb heute" tip={BETRIEB_EMOB_TOOLTIP} />
      {gruppen.filter((g) => g.werte.length > 0).map(({ z, werte }) => (
        <div key={z.feld} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm" data-gruppe={z.feld}>
          {mitTitel && GRUPPE_TITEL[z.feld] && (
            <span className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">{GRUPPE_TITEL[z.feld]}</span>
          )}
          {werte.map((w) => (
            <span key={w} className="inline-flex items-center gap-1.5" data-zeile={`betrieb-${w}`}>
              <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: funktionsFarbe(w) }} data-betrieb-farbe={w} />
              <span className="text-gray-500 dark:text-gray-400">{z.labels[w] ?? w}</span>
              <span className="font-semibold text-gray-900 dark:text-white whitespace-nowrap">{fmtStundenDauer(z.stunden[w])}</span>
            </span>
          ))}
        </div>
      ))}
      {ohneBetrieb && <p className="text-xs text-gray-500 dark:text-gray-400" data-betrieb-ohne>{KEIN_BETRIEB}</p>}
      {wechsel != null && <Zeile label="Ladevorgänge heute" data="ladevorgaenge">{fmtZahl(wechsel, 0)}</Zeile>}
    </Karte>
  )
}

// ── E-Auto ───────────────────────────────────────────────────────────────────

/** Ort des Autos aus der Zuordnung des Backends — eedc rät nicht (K-5, Blatt §4). */
function ortText(info: ReturnType<typeof fahrzeugImLive>): string | null {
  if (!info?.wallbox) return null
  return info.zuordnung === 'eindeutig' ? `an ${info.wallbox.label}` : null
}

function EAutoGeraeteKarte({ inv, live }: Pick<UeberblickKarteEmobProps, 'inv' | 'live'>) {
  const info = fahrzeugImLive(live, inv.id)
  const f = info?.fahrzeug ?? null
  const k = eautoKnoten(live, inv.id)
  const ev = live?.gauges?.find((g) => g.key === 'eigenverbrauch') ?? null
  // Leitsatz 8: der Zustand steht an der Wallbox-Karte; die Auto-Karte trägt ihn nur ohne Wallbox-Zuordnung.
  const eigenerChip = f && !info?.wallbox && f.ladezustand && f.ladezustand_label ? f : null
  const ort = ortText(info)
  const entlaedt = (k?.erzeugung_kw ?? 0) > 0
  const kw = k ? Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0) : null
  const ziel = zielText(f?.ziel_prozent, f?.restzeit_min)
  const ohneFelder = live != null
    && f?.reichweite_km == null && f?.ladezustand == null && ziel == null && f?.restzeit_min == null && f?.zu_hause == null
    && f?.km_stand == null

  return (
    <Karte name="geraet">
      <Kopf name={inv.bezeichnung}>
        {eigenerChip && <ModusChip modus={eigenerChip.ladezustand!} label={eigenerChip.ladezustand_label!} />}
        {f?.dienstwagen && <ZusatzChip text="Dienstwagen" />}
      </Kopf>
      {(f?.soc != null || ev) && (
        <div className="flex items-center justify-between gap-3">
          {f?.soc != null && (
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-baseline gap-3">
                <GrosseZahl titel="Ladestand" wert={`${fmtZahl(f.soc, 0)} %`} data="ladestand" />
                {f.reichweite_km != null && (
                  <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap" data-zeile="reichweite">
                    {fmtZahl(f.reichweite_km, 0)} km
                  </span>
                )}
              </div>
              <LadestandLeiste soc={f.soc} ziel={f.ziel_prozent ?? null} />
            </div>
          )}
          {ev && <AnlagenRing wert={ev.wert} />}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1">
        {ort && <Zeile label="Ort" data="ort">{ort}</Zeile>}
        {f?.zu_hause != null && <Zeile label="Standort" data="standort">{f.zu_hause ? 'Zu Hause' : 'Unterwegs'}</Zeile>}
        {/* W3: Ladeleistung nur mit eigenem Knoten (ein geteilter Sensor hat keinen); V2H als Abgabe. */}
        {kw != null && <Zeile label={entlaedt ? 'Entlädt ins Haus (V2H)' : 'Ladeleistung'} data="ladeleistung">{formatPower(kw)}</Zeile>}
        {ziel != null && <Zeile label="Ziel" data="ziel">{ziel}</Zeile>}
        {f?.km_stand != null && <Zeile label="Kilometerstand" data="kilometerstand">{fmtZahl(f.km_stand, 0)} km</Zeile>}
      </div>
      {info?.zuordnung === 'geschaetzt' && <Fusszeile>{SATZ_ZUORDNUNG_UNBEKANNT}</Fusszeile>}
      {ohneFelder && <Fusszeile>{FUSSZEILE_EAUTO}</Fusszeile>}
    </Karte>
  )
}

/**
 * «Auf einen Blick» der E-Mobilität — seit P-433-2b S1c **je Karte eine Park-Hülle** mit denselben IDs wie Wärme/Klima
 * (`ueberblickPark.ts`); Titel «Wallbox» bzw. «E-Auto», «Heute», «Betrieb». Heute und Betrieb stehen nur mit Werten da
 * — ihre Hülle ebenso. Ist die alte Park-ID `el:ueberblick-karte` geparkt, gelten alle drei als geparkt.
 */
export default function UeberblickKarteEmob(props: UeberblickKarteEmobProps) {
  const park = usePark()
  const { inv, live, tag } = props
  const istWallbox = inv.typ === 'wallbox'
  const heute = heuteDaten(props)
  const teile = emobKartenTeile(props)
  const altGeparkt = park.istGeparkt(UEBERBLICK_ALT_KARTE)
  return (
    <div className={`grid grid-cols-1 md:grid-cols-3${props.nebenSchaubild ? ' xl:grid-cols-1' : ''} gap-3 items-start`} data-ueberblick-karte data-ueberblick-emob={inv.typ}>
      {!altGeparkt && (
        <Parkbar id="el:ueberblick-karte-geraet" titel={istWallbox ? 'Wallbox' : 'E-Auto'}>
          {istWallbox ? <WallboxGeraeteKarte inv={inv} live={live} /> : <EAutoGeraeteKarte inv={inv} live={live} />}
        </Parkbar>
      )}
      {teile.heute && !altGeparkt && (
        <Parkbar id="el:ueberblick-karte-heute" titel="Heute">
          <HeuteKarte {...heute} />
        </Parkbar>
      )}
      {teile.betrieb && !altGeparkt && (
        <Parkbar id="el:ueberblick-karte-betrieb" titel="Betrieb">
          <BetriebKarteEmob zeilen={betriebZeilen(tag, inv.id)} />
        </Parkbar>
      )}
    </div>
  )
}
