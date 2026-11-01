/**
 * Welche Kachel hängt an welchem Objekt der zwei Szenen der E-Mobilität (P-433-2b S1b, Bauplan Fassung 2 §1/§2/§9).
 *
 * **Die Szene gehört dem gewählten Gerät** (E-2b-22): die Kacheln zeigen die Werte der gewählten Wallbox bzw. des
 * gewählten Autos; weitere Geräte des Typs erreicht der Selektor der Seite (kein Nebenanker, §9).
 * **Nur Werte haben Kacheln** (B2, wie Wärme/Klima): eine Kachel entsteht nur mit Wert; was der Grundbestand ist und
 * fehlt, sammelt `ohneSensor` für die Zeile unter dem Bild — Zusatzangaben (Sitzung, Reichweite, Fahrt, Standort,
 * Laden am Auto) stehen dort nicht (G7).
 *
 * **Szene «Ladepunkt»** ({@link baueLadepunktKacheln}):
 *  - **A** Gerätekachel der Wallbox — die Energiefluss-Kachel: Leistung `formatPower`, zweite Zeile Zustands-Chip
 *    (`ladezustandZeile`, bei «Lädt» keiner) sonst die Auto-Zeile (`wallboxKachelAuto` + `autoZeile`, bei «geschätzt»
 *    keine), Pegel = Ladestand des Autos wie dort, Tooltip wie dort (Zustand, Heute, Autos, Satz bei «geschätzt») plus
 *    Gast/unbekannt (Wortlaut der Karte); ohne Knoten Zeile «Leistung ‹Wallbox›»;
 *  - **Z** «Ladung heute» aus dem Tag-Detail (`emob_heute`), Rückfall der Live-Tageswert (`ladungHeute`, D-K4-2, ein Pfad je
 *    Kachel wie die Karte); zweite Zeile «PV-Anteil 67 %» nur mit `pv_anteil_prozent`; ohne Wert Zeile «Ladung heute ‹Wallbox›»;
 *  - **S** «Sitzung» mit `sitzung.kwh`, zweite Zeile die Dauer (> 0) bzw. «letzte Sitzung» ohne Fahrzeug; Tooltip `sitzungsTeile`;
 *  - **F** das Auto an dieser Wallbox — **nur** bei `fahrzeuge_zuordnung === 'eindeutig'` und mit Ladestand («eedc rät
 *    nicht»; bei «geschätzt»/Gast sagt es der A-Tooltip). Das erste nach ID ist die Fahrzeugkachel (Wert-Kachel mit Pegel,
 *    Rang 2 im Deskriptor), weitere Autos stehen als Gerätekacheln am selben Objekt — ab zwei bildet das Layout daraus
 *    «E-Autos (n)» (Gruppen-Regel «Geräte am selben Anker»; Layout unverändert).
 *
 * **Szene «Fahrzeug»** ({@link baueFahrzeugKacheln}):
 *  - **L** Gerätekachel «Laden»: Wert `formatPower(|kw|)` mit gemessener Leistung des Autos, sonst der Zustand im
 *    Klartext; zweite Zeile mit Leistung «entlädt (V2H)» bei `kw < 0`, sonst der Zustands-Chip (`ladezustandZeile`-Form);
 *    Tooltip «an ‹Wallbox›» (nur eindeutig) bzw. «ohne Wallbox», Zustand, «Heute» nur mit eigenem Knoten (W3);
 *  - **B** «Ladestand» mit Pegel, zweite Zeile `zielText`; ohne Wert Zeile «Ladestand ‹Auto›»;
 *  - **C** «Reichweite» (zweite Zeile «Stand ‹km›») bzw. nur «Kilometerstand»;
 *  - **R** «Gefahren heute» (zweite Zeile Fahrverbrauch) bzw. nur «Fahrverbrauch heute» — aus dem Tag-Detail;
 *  - **H** «Standort» «Zu Hause»/«Unterwegs» (HA-Zone).
 *
 * ⛔ **Der Client rechnet nichts** (ADR-002/P12): PV-Anteil nur `pv_anteil_prozent`, Fahrt nur `km`/`fahrverbrauch_kwh`,
 * jede Zahl kommt fertig aus dem Backend und wird hier nur formatiert. Reine Funktionen — kein Hook, kein Abruf.
 */
import type { LiveDashboardResponse, LiveFahrzeug, LiveKomponente } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'
import { KATEGORIE_FARBEN, fmtDauer, fmtZahl } from '../../../lib'
import { funktionsFarbe } from '../../../lib/funktionsFarben'
import {
  SATZ_ZUORDNUNG_UNBEKANNT, autoTip, autoZeile, formatPower, getNodeColor, heuteKwhVon, socColor, zeichenBudget,
} from '../../live/EnergieFluss'
import { computeDims, ladezustandZeile, wallboxKachelAuto } from '../../live/energieFlussLayout'
import type { ZweiteZeile } from '../../live/EnergieFlussKachel'
import { ladezustandKlartext } from '../../ui/ModusChip'
import type { KachelErgebnis, UeberblickKachel } from './kachelAnker'
import {
  FAHRZEUG_UNBEKANNT, GAST_LAEDT, GAST_VERBUNDEN, LADUNG_TAG_TOOLTIP, LADUNG_TOOLTIP, TOOLTIP_STEUERUNG,
  alleAutosAnWallboxen, eautoKnoten, fahrzeugImLive, herleitungPvAnteil, heuteZeile, ladungHeute, sitzungsTeile,
  wallboxKnoten, zielText,
} from './UeberblickKarteEmob'

export interface EmobKachelEingaben {
  /** Das gewählte Gerät — die Szene gehört ihm (E-2b-22). */
  inv: Investition
  /** Alle Geräte des Typs — nur für die Regel des Tageswerts (Typ-Key nur beim einzigen Gerät). */
  geraete: Investition[]
  live: LiveDashboardResponse | null
  /** Tag-Detail heute (`emob_heute`) — fehlt es, keine Tageskacheln aus dem Zähler. */
  tag: TagDetail | null
  /** Referenzfarbe des Themas für gedämpfte Chips (`useChartTheme().referenz`). */
  referenz: string
}

const FARBE_WALLBOX = KATEGORIE_FARBEN.wallbox
const FARBE_EAUTO = KATEGORIE_FARBEN.eauto
/** Der Ladezustand «kein Fahrzeug» — die Sitzung ist dann die letzte (Blatt §1a). */
const KEIN_FAHRZEUG = 'kein_fahrzeug'
/** Der Ladezustand «lädt» — Gast-Zeile «lädt» statt «verbunden». */
const LAEDT = 'laedt'

/** Zeichenbudget der Auto-Zeile an A — die Szene «Ladepunkt» hat höchstens drei Kacheln je Reihe, also die Dims der
 *  Energiefluss-Kachel für ≤ 3 (aus der Layout-SoT, nicht getippt). */
const AUTO_ZEILE_BUDGET = (() => {
  const d = computeDims(3)
  return zeichenBudget(d.nodeW, d.socFontSize)
})()

/** Pegel eines Ladestands — wie der SoC-Pegel im Energiefluss (kräftig, 0,3). */
function socPegel(soc: number): NonNullable<UeberblickKachel['pegel']> {
  return { prozent: soc, fill: socColor(soc), opacity: 0.3 }
}

/** Eine Wert-Kachel (B12 wie Wärme/Klima): kein „aktiv", immer Rollenfarbe. */
function wertKachel(
  id: string, anker: string, label: string, icon: string, color: string, wertText: string,
  zweite: string | null, tip: string, investitionId: number,
): UeberblickKachel {
  return {
    id, art: 'wert', anker, label, icon, color, isActive: true, wertText,
    zweiteZeile: zweite ? { text: zweite, fill: color } : null, tip, investitionId,
  }
}

// ── Szene «Ladepunkt» ───────────────────────────────────────────────────────

/** Tooltip der Wallbox-Kachel — die Zeilen der Energiefluss-Kachel (`EnergieFluss.tsx`) für einen Einzelknoten, dazu
 *  Gast und unbekanntes Fahrzeug im Wortlaut der Karte (K2a). */
function wallboxTip(inv: Investition, k: LiveKomponente, live: LiveDashboardResponse | null): string {
  const teile = [inv.bezeichnung]
  if ((k.erzeugung_kw ?? 0) > 0) teile.push(`Aktuell: ${fmtZahl(k.erzeugung_kw!, 2)} kW (Erzeugung)`)
  if ((k.verbrauch_kw ?? 0) > 0) teile.push(`Aktuell: ${fmtZahl(k.verbrauch_kw!, 2)} kW (Verbrauch)`)
  const zustand = ladezustandKlartext(k)
  if (zustand) teile.push(`Zustand: ${zustand}`)
  const heute = heuteKwhVon(live?.heute_kwh_pro_komponente ?? undefined, k.key)
  if (heute != null) teile.push(`Heute: ${fmtZahl(heute, 1)} kWh`)
  if (k.fahrzeuge_zuordnung === 'eindeutig') {
    (k.fahrzeuge ?? []).forEach((a) => teile.push(`Auto ${autoTip(a)}`))
  } else if (k.fahrzeuge_zuordnung === 'geschaetzt') {
    const alle = alleAutosAnWallboxen(live)
    if (alle.length > 0) {
      teile.push('Autos:')
      alle.forEach((a) => teile.push(`• ${autoTip(a)}`))
      teile.push(SATZ_ZUORDNUNG_UNBEKANNT)
    }
  }
  if (k.gast) teile.push(k.ladezustand === LAEDT ? GAST_LAEDT : GAST_VERBUNDEN)
  if (k.fahrzeug_unbekannt) teile.push(FAHRZEUG_UNBEKANNT)
  return teile.join('\n')
}

/** A — die Gerätekachel der Wallbox, wie im Energiefluss (§1). */
function wallboxKachel(inv: Investition, k: LiveKomponente, live: LiveDashboardResponse | null, referenz: string): UeberblickKachel {
  const kw = Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0)
  const color = getNodeColor(k)
  const { kachelAuto, ladestand } = k.fahrzeuge_zuordnung
    ? wallboxKachelAuto(k.fahrzeuge ?? [], k.fahrzeuge_zuordnung)
    : { kachelAuto: null, ladestand: null }
  const chip = ladezustandZeile(k, referenz)
  const zweite: ZweiteZeile | null = chip
    ?? (kachelAuto ? { text: autoZeile(kachelAuto, AUTO_ZEILE_BUDGET), fill: ladestand != null ? socColor(ladestand) : null } : null)
  return {
    id: `geraet-${inv.id}`, art: 'geraet', anker: 'A',
    label: inv.bezeichnung, icon: k.icon, color, isActive: kw > 0,
    wertText: formatPower(kw), zweiteZeile: zweite,
    pegel: ladestand != null ? socPegel(ladestand) : null,
    tip: wallboxTip(inv, k, live), investitionId: inv.id, leistungKw: k.verbrauch_kw ?? 0,
  }
}

/** Z — «Ladung heute» mit «PV-Anteil» (nur gemessen); `null` ohne Wert. */
function ladungKachel(inv: Investition, live: LiveDashboardResponse | null, tag: TagDetail | null, mehrere: boolean): UeberblickKachel | null {
  const zeile = heuteZeile(tag, inv.id)
  const ausTag = zeile?.ladung_kwh != null
  const kwh = ausTag ? zeile!.ladung_kwh! : ladungHeute(live, `wallbox_${inv.id}`, 'wallbox', mehrere)
  if (kwh == null) return null
  const anteil = zeile?.pv_anteil_prozent ?? null
  const herleitung = anteil != null ? herleitungPvAnteil(zeile?.ladung_pv_kwh, zeile?.ladung_kwh) : null
  const tip = [
    inv.bezeichnung,
    `Ladung heute: ${fmtZahl(kwh, 1)} kWh`,
    ...(anteil != null ? [`PV-Anteil heute: ${fmtZahl(anteil, 0)} %${herleitung ? ` (${herleitung})` : ''}`] : []),
    ausTag ? LADUNG_TAG_TOOLTIP : LADUNG_TOOLTIP,
  ].join('\n')
  return wertKachel(`wert-ladung-${inv.id}`, 'Z', 'Ladung heute', 'zap', FARBE_WALLBOX, `${fmtZahl(kwh, 1)} kWh`,
    anteil != null ? `PV-Anteil ${fmtZahl(anteil, 0)} %` : null, tip, inv.id)
}

/** S — «Sitzung» (Zusatzfeld, nie in der Zeile); `null` ohne `sitzung.kwh`. */
function sitzungKachel(inv: Investition, k: LiveKomponente): UeberblickKachel | null {
  const kwh = k.sitzung?.kwh ?? null
  if (kwh == null) return null
  const dauer = k.sitzung?.dauer_s ?? null
  const zweite = k.ladezustand === KEIN_FAHRZEUG ? 'letzte Sitzung' : dauer != null && dauer > 0 ? fmtDauer(dauer) : null
  const teile = sitzungsTeile(k)
  const tip = [inv.bezeichnung, ...(teile.length > 0 ? [teile.join(' · ')] : []), 'Quelle: Live-Snapshot'].join('\n')
  return wertKachel(`wert-sitzung-${inv.id}`, 'S', 'Sitzung', 'plug', FARBE_WALLBOX, `${fmtZahl(kwh, 1)} kWh`, zweite, tip, inv.id)
}

/** Zweite Zeile einer Fahrzeugkachel: Ziel, sonst gemessene Richtung, sonst keine. */
function fahrzeugZweite(f: LiveFahrzeug, zielWallbox: number | null): string | null {
  const ziel = f.ziel_prozent ?? zielWallbox
  if (ziel != null) return `Ziel ${fmtZahl(ziel, 0)} %`
  // Leistung im Energiefluss-Format (`formatPower`: unter 10 kW in Watt) — ein Format je Szene (Gernot 1.11.2026).
  if (f.kw != null && f.kw > 0) return `lädt ${formatPower(f.kw)}`
  if (f.kw != null && f.kw < 0) return `entlädt ${formatPower(-f.kw)}`
  return null
}

/** Eine Fahrzeugkachel am Auto-Objekt F (Ladestand mit Pegel, Rollenfarbe E-Auto). */
function fahrzeugKachel(f: LiveFahrzeug & { soc: number }, k: LiveKomponente, erstes: boolean): UeberblickKachel {
  const tip = [
    autoTip(f),
    ...(f.dienstwagen ? ['Dienstwagen'] : []),
    ...(k.fahrzeuge_quelle === 'steuerung' ? [TOOLTIP_STEUERUNG] : []),
    `an ${k.label}`,
  ].join('\n')
  const zweite = fahrzeugZweite(f, k.ziel_prozent ?? null)
  return {
    id: `fahrzeug-${f.investition_id}`, art: erstes ? 'wert' : 'geraet', anker: 'F',
    label: f.label, icon: 'car', color: FARBE_EAUTO, isActive: true,
    wertText: `${fmtZahl(f.soc, 0)} %`,
    zweiteZeile: zweite ? { text: zweite, fill: FARBE_EAUTO } : null,
    pegel: socPegel(f.soc), tip, investitionId: f.investition_id, leistungKw: f.kw,
  }
}

/**
 * F — die Autos an dieser Wallbox: nur bei eindeutiger Zuordnung (inkl. Steuerung) und mit Ladestand. Das erste nach ID
 * ist die Fahrzeugkachel (`art: 'wert'`, steht immer einzeln); jedes weitere ist eine Gerätekachel am selben Objekt —
 * ab zwei bildet das Layout «E-Autos (n)» (Rest-Gruppe, §1).
 */
export function ladepunktFahrzeuge(k: LiveKomponente): UeberblickKachel[] {
  if (k.fahrzeuge_zuordnung !== 'eindeutig') return []
  const autos = (k.fahrzeuge ?? [])
    .filter((f): f is LiveFahrzeug & { soc: number } => f.soc != null)
    .sort((a, b) => a.investition_id - b.investition_id)
  return autos.map((f, i) => fahrzeugKachel(f, k, i === 0))
}

/**
 * Die Kacheln der Szene «Ladepunkt» für die gewählte Wallbox und die Liste dessen, was ohne Kachel bleibt
 * («Leistung ‹Wallbox›», «Ladung heute ‹Wallbox›»). Vor der ersten Live-Antwort ist nichts „ohne Sensor".
 */
export function baueLadepunktKacheln({ inv, geraete, live, tag, referenz }: EmobKachelEingaben): KachelErgebnis {
  const kacheln: UeberblickKachel[] = []
  const ohneSensor: string[] = []
  const k = wallboxKnoten(live, inv.id)
  if (k) kacheln.push(wallboxKachel(inv, k, live, referenz))
  else ohneSensor.push(`Leistung ${inv.bezeichnung}`)

  const ladung = ladungKachel(inv, live, tag, geraete.length > 1)
  if (ladung) kacheln.push(ladung)
  else ohneSensor.push(`Ladung heute ${inv.bezeichnung}`)

  if (k) {
    const sitzung = sitzungKachel(inv, k)
    if (sitzung) kacheln.push(sitzung)
    kacheln.push(...ladepunktFahrzeuge(k))
  }
  return { kacheln, ohneSensor: live ? ohneSensor : [] }
}

// ── Szene «Fahrzeug» ────────────────────────────────────────────────────────

/** Ladestand des Autos: aus der Live-Zuordnung, sonst die Gauge `soc_<id>`. */
function ladestandVon(live: LiveDashboardResponse | null, invId: number, f: LiveFahrzeug | null): number | null {
  if (f?.soc != null) return f.soc
  return live?.gauges?.find((g) => g.key === `soc_${invId}`)?.wert ?? null
}

/** Ruhezustände des Fahrzeugs: der Chip steht gedämpft (wie «Kein Fahrzeug»/«Fertig» an der Wallbox). */
const FAHRZEUG_GEDAEMPFT = new Set(['nicht_verbunden', 'fertig'])

/**
 * Zustands-Chip des Fahrzeugs an L — die Form von `ladezustandZeile` (Text, Funktionsfarbe, gedämpft in Ruhe), aber
 * **auch bei «Lädt»**: an der Wallbox weicht der Chip bei «Lädt» der Auto-Zeile; an L gibt es keine Auto-Zeile, der
 * Zustand ist die zweite Zeile (§2). Ohne gemessenen Zustand `null`.
 */
export function fahrzeugZustandZeile(
  f: Pick<LiveFahrzeug, 'ladezustand' | 'ladezustand_label'> | null, referenz: string,
): ZweiteZeile | null {
  if (!f?.ladezustand || !f.ladezustand_label) return null
  const farbe = funktionsFarbe(f.ladezustand)
  const gedaempft = FAHRZEUG_GEDAEMPFT.has(f.ladezustand)
  return { text: f.ladezustand_label, fill: gedaempft ? referenz : farbe, chip: { farbe, gedaempft } }
}

/** L — «Laden» an der Säule: Leistung des Autos (gemessen) oder sein Zustand; `null` ohne beides. */
function ladenKachel(
  inv: Investition, info: ReturnType<typeof fahrzeugImLive>, k: LiveKomponente | undefined,
  live: LiveDashboardResponse | null, referenz: string,
): UeberblickKachel | null {
  const f = info?.fahrzeug ?? null
  const kw = f?.kw ?? null
  const zustand = f?.ladezustand_label ?? null
  if (kw == null && !zustand) return null
  const zweite: ZweiteZeile | null = kw == null
    ? null
    : kw < 0 ? { text: 'entlädt (V2H)', fill: FARBE_EAUTO } : fahrzeugZustandZeile(f, referenz)
  const heute = k ? ladungHeute(live, `eauto_${inv.id}`, 'eauto', true) : null
  const tip = [
    inv.bezeichnung,
    ...(info?.wallbox && info.zuordnung === 'eindeutig' ? [`an ${info.wallbox.label}`] : []),
    ...(info && !info.wallbox ? ['ohne Wallbox'] : []),
    ...(kw != null ? [`Aktuell: ${fmtZahl(Math.abs(kw), 2)} kW (${kw < 0 ? 'entlädt, V2H' : 'lädt'})`] : []),
    ...(zustand ? [`Zustand: ${zustand}`] : []),
    ...(heute != null ? [`Heute: ${fmtZahl(heute, 1)} kWh`] : []),
    'Quelle: Live-Snapshot',
  ].join('\n')
  return {
    id: `geraet-${inv.id}`, art: 'geraet', anker: 'L',
    label: 'Laden', icon: 'plug', color: FARBE_EAUTO, isActive: kw != null && kw !== 0,
    wertText: kw != null ? formatPower(Math.abs(kw)) : zustand!, zweiteZeile: zweite,
    tip, investitionId: inv.id, leistungKw: kw,
  }
}

/** C — «Reichweite» (zweite Zeile «Stand …») bzw. nur «Kilometerstand»; `null` ohne beides. */
function reichweiteKachel(inv: Investition, f: LiveFahrzeug | null): UeberblickKachel | null {
  const rw = f?.reichweite_km ?? null
  const stand = f?.km_stand ?? null
  if (rw == null && stand == null) return null
  const tip = [
    inv.bezeichnung,
    ...(rw != null ? [`Reichweite: ${fmtZahl(rw, 0)} km`] : []),
    ...(stand != null ? [`Kilometerstand: ${fmtZahl(stand, 0)} km`] : []),
    'Quelle: Live-Snapshot',
  ].join('\n')
  return rw != null
    ? wertKachel(`wert-reichweite-${inv.id}`, 'C', 'Reichweite', 'car', FARBE_EAUTO, `${fmtZahl(rw, 0)} km`,
      stand != null ? `Stand ${fmtZahl(stand, 0)} km` : null, tip, inv.id)
    : wertKachel(`wert-reichweite-${inv.id}`, 'C', 'Kilometerstand', 'car', FARBE_EAUTO, `${fmtZahl(stand!, 0)} km`, null, tip, inv.id)
}

/** R — «Gefahren heute» (zweite Zeile Fahrverbrauch) bzw. nur «Fahrverbrauch heute»; `null` ohne beides. */
function fahrtKachel(inv: Investition, tag: TagDetail | null): UeberblickKachel | null {
  const zeile = heuteZeile(tag, inv.id)
  const km = zeile?.km ?? null
  const kwh = zeile?.fahrverbrauch_kwh ?? null
  if (km == null && kwh == null) return null
  const tip = [
    inv.bezeichnung,
    ...(km != null ? [`Gefahren heute: ${fmtZahl(km, 0)} km`] : []),
    ...(kwh != null ? [`Fahrverbrauch heute: ${fmtZahl(kwh, 1)} kWh`] : []),
    'Quelle: Tag-Detail (Kanal-Stunden)',
  ].join('\n')
  return km != null
    ? wertKachel(`wert-fahrt-${inv.id}`, 'R', 'Gefahren heute', 'car', FARBE_EAUTO, `${fmtZahl(km, 0)} km`,
      kwh != null ? `${fmtZahl(kwh, 1)} kWh` : null, tip, inv.id)
    : wertKachel(`wert-fahrt-${inv.id}`, 'R', 'Fahrverbrauch heute', 'car', FARBE_EAUTO, `${fmtZahl(kwh!, 1)} kWh`, null, tip, inv.id)
}

/**
 * Die Kacheln der Szene «Fahrzeug» für das gewählte Auto und die Liste dessen, was ohne Kachel bleibt («Ladestand
 * ‹Auto›»). Vor der ersten Live-Antwort ist nichts „ohne Sensor".
 */
export function baueFahrzeugKacheln({ inv, live, tag, referenz }: EmobKachelEingaben): KachelErgebnis {
  const kacheln: UeberblickKachel[] = []
  const ohneSensor: string[] = []
  const info = fahrzeugImLive(live, inv.id)
  const f = info?.fahrzeug ?? null

  const laden = ladenKachel(inv, info, eautoKnoten(live, inv.id), live, referenz)
  if (laden) kacheln.push(laden)

  const soc = ladestandVon(live, inv.id, f)
  if (soc != null) {
    const ziel = zielText(f?.ziel_prozent, f?.restzeit_min)
    kacheln.push({
      ...wertKachel(`wert-ladestand-${inv.id}`, 'B', 'Ladestand', 'battery', FARBE_EAUTO, `${fmtZahl(soc, 0)} %`, ziel,
        [inv.bezeichnung, `Ladestand: ${fmtZahl(soc, 0)} %`, ...(ziel ? [`Ziel: ${ziel}`] : []), 'Quelle: Live-Snapshot'].join('\n'),
        inv.id),
      pegel: socPegel(soc),
    })
  } else {
    ohneSensor.push(`Ladestand ${inv.bezeichnung}`)
  }

  const reichweite = reichweiteKachel(inv, f)
  if (reichweite) kacheln.push(reichweite)
  const fahrt = fahrtKachel(inv, tag)
  if (fahrt) kacheln.push(fahrt)
  if (f?.zu_hause != null) {
    const ort = f.zu_hause ? 'Zu Hause' : 'Unterwegs'
    kacheln.push(wertKachel(`wert-standort-${inv.id}`, 'H', 'Standort', 'home', FARBE_EAUTO, ort, null,
      `${inv.bezeichnung}\nStandort: ${ort}\nQuelle: HA-Zone`, inv.id))
  }
  return { kacheln, ohneSensor: live ? ohneSensor : [] }
}
