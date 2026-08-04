/**
 * Komponenten-Hub Daten-Adapter (IA v4 Phase A.2 — SPEC-KOMPONENTEN.md).
 *
 * Pro Komponententyp EIN Adapter, der die bestehende Dashboard-Quelle
 * (`investitionenApi.get<Typ>Dashboard` bzw. `cockpitApi` für PV-Anlage) auf das
 * generische Hub-Modell normalisiert: je **Gerät** (mehrere desselben Typs →
 * Geräte-Selektor, Art ①) ein {@link KompGeraet} mit den 4 D2-Status-KPIs
 * (Stil-Records aus `lib/komponentenStyle`, SoT) + Aufteilung (VerteilungsBalken,
 * K-B11). Hub = **Gesamtzeitraum/kumulativ** (K-B5): es werden die Lebensdauer-
 * `zusammenfassung`-Felder gelesen, kein Datums-Parameter.
 *
 * Liefert Pflicht-Blöcke (① Status+Aufteilung, ④ Verlauf, ⑤ Vergleich) UND die
 * investitionsspezifischen Blöcke: ① Sekundär-KPIs (WP getrennte JAZ +
 * #238 Starts/Betriebsstunden, Speicher-Arbitrage), ② Struktur/Verknüpfung
 * (PV-Topologie WR→Module→Speicher+Orphan / Kopplungs-Referenz bei Speicher/Wallbox),
 * ③ Sub-Komponente (E-Auto V2H, BKW integrierter Speicher).
 *
 * Aussicht (⑥) entfällt im Hub (Gernot 2026-06-21): rein zeitliche Differenzierung
 * → lebt in Cockpit/Aussicht. Typ-spezifische IST-Analysen (PV-SOLL/IST je String)
 * kommen aus `komponentenAnalyse.tsx`, nicht aus diesem Daten-Adapter.
 */
import { Activity, Battery, Clock, Droplet, Euro, Flame, Leaf, Power, TrendingUp, Zap } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { fmtCalc } from '../components/ui'
import { formatEnergie, formatEffizienz } from '../lib/einheiten'
import { MONAT_KURZ, PV_MODUL_FARBEN, PV_MODUL_BG, SONSTIGES_KATEGORIE_LABELS } from '../lib'
import { CHART_COLORS, ENERGIE_KATEGORIE, KOMPONENTEN_FARBEN, LADEQUELLEN_FARBEN, ROLLEN_BG, SONSTIGES_ERZEUGER_FARBE } from '../lib/colors'
import { pvVerteiltHerkunft } from '../lib/pvHerkunft'
import { cockpitApi, type PVStringsGesamtlaufzeitResponse } from '../api/cockpit'
import { investitionenApi, type InvestitionMonatsdaten } from '../api/investitionen'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import {
  PV_ANLAGE_KPI, SPEICHER_KPI, WP_KPI, EAUTO_KPI, WALLBOX_KPI, BKW_KPI,
  SONSTIGES_ERZEUGER_KPI, SONSTIGES_VERBRAUCHER_KPI, SONSTIGES_SPEICHER_KPI,
  type KpiStyle, type KomponentenColor,
} from '../lib/komponentenStyle'
import type { KpiStripItem } from '../components/blocks'
import type { VerteilungSegment, WertHerkunft } from '../components/blocks'
import type { VerlaufBar, VerlaufRow } from './KomponentenVerlaufChart'
import type { Investition } from '../types'

/** Datenrollen→bg-Klassen für Aufteilungs-Segmente — SoT in `lib/colors.ts`. */
const SEG = ROLLEN_BG

/** Ein Knoten im Block ② „Struktur" (PV-Topologie): Modul / Speicher unter einem WR. */
export interface TopoItem { label: string; detail?: string }
/** Ein Wechselrichter mit seinen zugeordneten Modulen/Speichern (Block ②, PV voll). */
export interface WrGruppe { label: string; detail?: string; module: TopoItem[]; speicher: TopoItem[] }

/** Block ② Struktur/Verknüpfung — PV = volle Topologie, sonst dünne Referenzzeilen. */
export type KompStruktur =
  | { art: 'topologie'; wr: WrGruppe[]; orphanModule: TopoItem[]; orphanSpeicher: TopoItem[] }
  | { art: 'referenz'; zeilen: { label: string; wert?: string; hinweis?: string }[] }

/** Ein Gerät (oder UI-Aggregat) eines Typs — generisch von der Sicht konsumiert. */
export interface KompGeraet {
  inv: Investition
  label: string
  /** Optionales Badge am Geräte-Selektor (z. B. Sonstiges-Kategorie Erzeuger/
   *  Verbraucher/Speicher) — macht heterogene Geräte gleichen Typs unterscheidbar. */
  selektorBadge?: string
  status: KpiStripItem[]
  aufteilung?: { titel: string; einheit?: string; segmente: VerteilungSegment[] }
  /** Block ① Kennzahlen-Strip (IST-Summary-Karten, numerisch — z. B. Speicher
   *  Ladung/Entladung gesamt, Zyklen/Monat, Verlust). Vor `aufteilung`. */
  kennzahlen?: { titel: string; kpis: KpiStripItem[] }
  /** Block ① Hinweise/Alarme (Speicher-Degradation, Durchsatz-Inkonsistenz …) —
   *  als Alert im Status-Block, direkt unter den D2-KPIs. */
  hinweise?: { ton: 'warning' | 'error'; text: string }[]
  /** Block ① Sekundär-KPIs (numerisch, im Strip unter den 4 D2-KPIs). */
  sekundaer?: { titel: string; kpis: KpiStripItem[] }
  /** Block ② Struktur/Verknüpfung (spezifisch: PV-Topologie / Verknüpfungs-Referenz). */
  struktur?: KompStruktur
  /** Block ③ Sub-Komponente (spezifisch, In-Wirt: E-Auto V2H, BKW-Speicher). */
  subKomponente?: { titel: string; kpis: KpiStripItem[]; hinweis?: string }
  /** Block ④ Verlauf: Zeitreihe (gesamte Historie). `gestapelt=false` = gruppierte
   *  Balken, sonst gestapelt; Bars mit `stapel`-Gruppe stehen paarweise nebeneinander.
   *  `verteilungen` = optionale %-Aufteilungs-Balken (Gesamtzeitraum) unter dem Chart.
   *  `herkunft` = Kennzeichnung am Chart, wenn dessen Werte gerechnet sind (PV je
   *  Modul nach kWp) — je Verteilung separat, weil in derselben Zeile gemessene
   *  und gerechnete Aufteilungen nebeneinander stehen können. */
  verlauf?: {
    bars: VerlaufBar[]; rows: VerlaufRow[]; einheit?: string; gestapelt?: boolean
    herkunft?: WertHerkunft
    verteilungen?: { titel: string; einheit?: string; segmente: VerteilungSegment[]; herkunft?: WertHerkunft }[]
  }
  /** Block ⑤ Vergleich (dünn): Jahressummen einer Leitkennzahl je Jahr. */
  vergleich?: { label: string; einheit: string; farbe: string; jahre: { jahr: number; summe: number }[] }
  /** Block „Wirtschaftlichkeit" — **Ertrags-Zusammensetzung** (generischer Modus
   *  für Typen OHNE Alternativ-Vergleich: PV/Speicher/BKW/Sonstiges). Schlüsselt
   *  das wirtschaftliche Ergebnis in seine Ertragsposten (€) auf: 1 Posten → nur
   *  Kennzahl, ≥2 → zusätzlich €-Aufteilungsbalken. Typen MIT Alternative (WP/
   *  E-Auto/Wallbox) liefern stattdessen einen Registry-Vergleich (`komponentenAnalyse`).
   *  `nichtBewertet` = ehrlicher „nicht bewertbar"-Hinweis statt Fake (Sonstiger
   *  Erzeuger ohne Brennstoffmodell, Konzept Gernot 2026-06-22). */
  wirtschaftlichkeit?: {
    posten: { label: string; euro: number | null | undefined; farbe: string; hinweis?: string }[]
    gesamt?: { label: string; euro: number | null | undefined }
    hinweis?: string
    nichtBewertet?: string
  }
  /** Einstellungen-Block: alle verknüpften Investitionen, deren Parameter +
   *  Sensor-/MQTT-Zuordnungen gezeigt werden (PV = WR+Module+Speicher; sonst [inv]). */
  verknuepfteInvs?: Investition[]
}

/** Jahressummen einer Leitkennzahl aus den Monatsdaten (für Block ⑤ dünn). */
function jahresSummen(
  md: InvestitionMonatsdaten[],
  wert: (vd: Record<string, number>) => number,
): { jahr: number; summe: number }[] {
  const m = new Map<number, number>()
  for (const r of md) m.set(r.jahr, (m.get(r.jahr) ?? 0) + Math.max(0, wert(r.verbrauch_daten) || 0))
  return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([jahr, summe]) => ({ jahr, summe }))
}

/** Monatszeilen aus InvestitionMonatsdaten (chronologisch) — ein Extraktor je
 *  Serie liest den passenden `verbrauch_daten`-Key (gegen Demo verifiziert). */
function rowsAusMd(
  md: InvestitionMonatsdaten[],
  serien: { key: string; wert: (vd: Record<string, number>) => number }[],
): VerlaufRow[] {
  return [...md]
    .sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat))
    .map((m) => {
      const row: VerlaufRow = { name: `${MONAT_KURZ[m.monat]} ${String(m.jahr).slice(2)}` }
      for (const s of serien) row[s.key] = Math.max(0, s.wert(m.verbrauch_daten) || 0)
      return row
    })
}

export interface KompAdapter {
  /** Lädt alle Geräte dieses Typs (Gesamtzeitraum). */
  fetch: (anlageId: number) => Promise<KompGeraet[]>
}

/** KPI-Helfer: Stil-Record (Titel/Icon/Farbe) + Wert/Einheit → KpiStripItem. */
function kpi(stil: KpiStyle, value: string | number, unit?: string): KpiStripItem {
  return { ...stil, value, unit }
}

/** Ad-hoc-KPI-Helfer für Sekundär-/Sub-Blöcke (kein D2-Kanon-Record). */
function k(
  title: string, value: string | number, unit: string | undefined,
  color: KomponentenColor, icon: LucideIcon,
  extra?: { subtitle?: string; formel?: string; berechnung?: string },
): KpiStripItem {
  return { title, value, unit, color, icon, ...extra }
}

/** KPI als **„nicht bewertet"** statt Fake-0 — abgeleitete Kennzahl, deren
 *  Quellgröße fehlt bzw. (Sonstiger Erzeuger/BHKW) ohne Brennstoffmodell nicht
 *  bewertbar ist. Wert `—`, neutrale Farbe, erklärende Zweitzeile. Setzt die
 *  bestehende Regel „abgeleitete Größe nur zeigen, wenn die Quelle vorliegt" für
 *  den 0-Fall fort (Konzept Sonstiger Erzeuger, Gernot 2026-06-22). */
function unbewertet(stil: KpiStyle, hinweis: string): KpiStripItem {
  return { title: stil.title, icon: stil.icon, color: 'gray', value: '—', subtitle: hinweis }
}

/** Energie-KPI über die formatEnergie-SoT (C3/S17): kWh bis < 10.000, dann MWh
 *  mit 2 NK — statt unbedingter kWh→MWh-Umrechnung. `referenzKwh` koppelt
 *  zusammengehörige KPIs einer Sicht an EINE Skala (kein kWh/MWh-Mix im Strip). */
const energie = (kwh: number | null | undefined, referenzKwh?: number) => formatEnergie(kwh, referenzKwh)
const n0 = (v: number | null | undefined) => fmtCalc(v, 0, '—')
const n1 = (v: number | null | undefined) => fmtCalc(v, 1, '—')
const n2 = (v: number | null | undefined) => fmtCalc(v, 2, '—')

/** Zahl aus dem parameter-JSON (`Record<string, unknown>`) defensiv lesen. */
function pnum(p: Record<string, unknown> | undefined, key: string): number | null {
  const v = p?.[key]
  return typeof v === 'number' ? v : null
}

/** Topologie-Zeile eines PV-Moduls.
 *
 *  kWp aus `leistung_kwp_effektiv`, nicht aus der Rohspalte (A26/N106): wer
 *  seine Nennleistung nur im `parameter`-JSON gepflegt hat (#229), stand hier
 *  ohne kWp-Angabe da. */
function pvModItem(m: Investition): TopoItem {
  const teile = [m.leistung_kwp_effektiv != null ? `${n1(m.leistung_kwp_effektiv)} kWp` : null, m.ausrichtung].filter(Boolean)
  return { label: m.bezeichnung, detail: teile.join(' · ') || undefined }
}
function pvSpItem(s: Investition): TopoItem {
  const kap = pnum(s.parameter, 'nutzbare_kapazitaet_kwh') ?? pnum(s.parameter, 'kapazitaet_kwh')
  return { label: s.bezeichnung, detail: kap != null ? `${n1(kap)} kWh` : undefined }
}

/** Block ② PV-System-Topologie: WR → Module/Speicher via `parent_investition_id`
 *  + Orphan-Listen (Modul/Speicher ohne gültige WR-Zuordnung) — wie IST-PVAnlageDashboard.
 *  Nur aktive Investitionen (aktiv=False = wie gelöscht, [[feedback_aktiv_inaktiv_semantik]]). */
function bauePvTopologie(invs: Investition[]): KompStruktur {
  const aktiv = invs.filter((i) => i.aktiv)
  const wrs = aktiv.filter((i) => i.typ === 'wechselrichter')
  const module = aktiv.filter((i) => i.typ === 'pv-module')
  const speicher = aktiv.filter((i) => i.typ === 'speicher')
  const wrIds = new Set(wrs.map((w) => w.id))
  const zugeordnet = (i: Investition) => i.parent_investition_id != null && wrIds.has(i.parent_investition_id)
  return {
    art: 'topologie',
    wr: wrs.map((w) => {
      const maxKw = pnum(w.parameter, 'max_leistung_kw')
      return {
        label: w.bezeichnung,
        detail: maxKw != null ? `${n1(maxKw)} kW` : undefined,
        module: module.filter((m) => m.parent_investition_id === w.id).map(pvModItem),
        speicher: speicher.filter((s) => s.parent_investition_id === w.id).map(pvSpItem),
      }
    }),
    orphanModule: module.filter((m) => !zugeordnet(m)).map(pvModItem),
    orphanSpeicher: speicher.filter((s) => !zugeordnet(s)).map(pvSpItem),
  }
}

/** Kennzeichnung der Modul-Werte in Block ④, wenn sie NICHT gemessen sind
 *  (Rainer/rapahl 2026-07-25): Modulwerte kommen seit A4 aus
 *  `/cockpit/pv-strings-gesamtlaufzeit`, also aus den Pro-String-Sensoren. Wer nur
 *  einen Gesamt-Sensor hat, bekommt dort die nach kWp verteilten Werte — dann
 *  (und nur dann) steht diese Kennzeichnung dran, datengetrieben über
 *  `ist_quelle`. Wortlaut-SoT: `lib/pvHerkunft` (geteilt mit Block ⑤).
 *  `bezug` gilt nur für den Erzeugungs-Stapel — die Verwendung daneben ist
 *  gemessen. */
const PV_MODUL_HERKUNFT: WertHerkunft = pvVerteiltHerkunft('Erzeugung je Modul')

/** Erzeuger, die hinter DEMSELBEN Hauszähler einspeisen, aber keine PV-Module
 *  dieser Karte sind: Balkonkraftwerk und sonstiger Erzeuger (BHKW, `sonstiges`
 *  + Kategorie `erzeuger`, seit v3.45.4 Teil der Bilanz). Sie gehören in den
 *  Erzeugungs-Stapel, weil die Verwendungsseite daneben genau ihre Energie
 *  mitverteilt — sonst stehen zwei Stapel nebeneinander, die nicht zusammenpassen.
 *  Label/Balkenfarbe aus derselben SoT wie die Kategorien-Leiste im Energieprofil
 *  ({@link ENERGIE_KATEGORIE}), Chart-Hex aus der Komponenten-Identität. */
const ERZ_ZUSATZ = [
  {
    key: 'bkw', label: ENERGIE_KATEGORIE.bkw.label, bg: ENERGIE_KATEGORIE.bkw.bg,
    hex: KOMPONENTEN_FARBEN['balkonkraftwerk'].hex,
    wert: (r: AggregierteMonatsdaten) => r.bkw_kwh ?? 0,
  },
  {
    key: 'sonstErz', label: ENERGIE_KATEGORIE.sonstige_erzeuger.label, bg: ENERGIE_KATEGORIE.sonstige_erzeuger.bg,
    hex: SONSTIGES_ERZEUGER_FARBE.hex,
    wert: (r: AggregierteMonatsdaten) => r.sonstige_erzeugung_kwh ?? 0,
  },
] as const

/** PV-Verlauf = pro Jahr zwei Stapel nebeneinander: **Erzeugung** ⟷
 *  **Verwendung** (Direktverbrauch · Speicherladung · Einspeisung). Plus zwei
 *  %-Aufteilungs-Balken (Gesamtzeitraum).
 *
 *  Die Modul-Stapel kommen aus `strings[].jahreswerte[].ist_kwh` — der Achse
 *  Jahr × Modul, die dieser Block braucht (A4/b2). Fehlt die Antwort (alte
 *  Instanz, Fehler), bleibt die kWp-Zerlegung aus der anlagenweiten
 *  `/monatsdaten/aggregiert`-Response als Fallback — dann gekennzeichnet.
 *
 *  **Beide Stapel sind summengleich** (A15/N43): der Erzeugungs-Stapel zeigt
 *  neben den PV-Modulen auch BKW und sonstige Erzeuger ({@link ERZ_ZUSATZ}) —
 *  genau die Zusammensetzung, aus der die Verwendungsseite gerechnet ist
 *  (`erzeugung_hinter_zaehler_kwh`). Vorher zeigte die Erzeugungsseite nur die
 *  Module und die Verwendung daneben die ganze Anlagenbilanz; dass die Differenz
 *  bis A4 nicht auffiel, lag allein daran, dass die kWp-Zerlegung die
 *  BKW-Erzeugung stillschweigend auf die Dachflächen mitverteilt hat. */
function pvVerlauf(
  agg: AggregierteMonatsdaten[],
  module: Investition[],
  pvStrings?: PVStringsGesamtlaufzeitResponse | null,
): NonNullable<KompGeraet['verlauf']> {
  // Not-Fallback-Bezugsgröße: `leistung_kwp_effektiv`, nicht die Rohspalte
  // (A26/N106). Auf der Rohspalte bekam ein nur im `parameter` gepflegtes Modul
  // (#229) hier 0 zugeteilt — und die übrigen Module entsprechend zu viel.
  const totalKwp = module.reduce((s, m) => s + (m.leistung_kwp_effektiv ?? 0), 0)
  type JahrWerte = { erz: number; direkt: number; speicher: number; einsp: number; zusatz: Record<string, number> }
  const jahr = new Map<number, JahrWerte>()
  for (const r of agg) {
    const y = jahr.get(r.jahr) ?? { erz: 0, direkt: 0, speicher: 0, einsp: 0, zusatz: {} }
    // Bezugsgröße der Modul-Zerlegung ist die PV-Anlage OHNE BKW — sonst
    // verteilt der Fallback die BKW-Erzeugung auf die Dachflächen mit und
    // doppelt sie gegen das eigene BKW-Segment.
    y.erz += r.pv_module_kwh ?? r.pv_erzeugung_kwh ?? 0
    // Direktverbrauch kanonisch aus der Response statt lokal aus
    // EV − Speicher-Entladung: der Eigenverbrauch enthält zusätzlich V2H
    // (E-Auto → Haus), das keine Verwendung der Erzeugung dieses Monats ist und
    // den Verwendungs-Stapel über die Erzeugung hinausgehoben hätte.
    y.direkt += r.direktverbrauch_kwh ?? 0
    y.speicher += r.speicher_ladung_kwh ?? 0
    y.einsp += r.einspeisung_kwh ?? 0
    for (const z of ERZ_ZUSATZ) y.zusatz[z.key] = (y.zusatz[z.key] ?? 0) + z.wert(r)
    jahr.set(r.jahr, y)
  }
  // Nur tatsächlich vorhandene Zusatz-Erzeuger bekommen Balken/Segment — eine
  // reine PV-Anlage soll keine toten Legenden-Einträge sehen.
  const zusatzAktiv = ERZ_ZUSATZ.filter((z) => agg.some((r) => z.wert(r) > 0))
  // Gemessene Modulwerte je Jahr, sofern der String-Endpoint sie liefert.
  const gemessen = new Map<number, Map<number, number>>()  // invId → jahr → kWh
  for (const s of pvStrings?.strings ?? []) {
    gemessen.set(s.investition_id, new Map(s.jahreswerte.map((j) => [j.jahr, j.ist_kwh])))
  }
  const hatModulwerte = module.some((m) => gemessen.has(m.id))
  const kwpAnteil = (m: Investition, erz: number) => totalKwp > 0 ? erz * (m.leistung_kwp_effektiv ?? 0) / totalKwp : 0
  const modulWert = (m: Investition, j: number, erz: number) => hatModulwerte
    ? (gemessen.get(m.id)?.get(j) ?? 0)
    : kwpAnteil(m, erz)
  // Kennzeichnung datengetrieben: nur wenn das Backend die Werte als verteilt
  // meldet (oder der Fallback greift), ist hier gerechnet statt gemessen.
  const herkunft: WertHerkunft | undefined = hatModulwerte
    ? (pvStrings?.ist_quelle === 'verteilt' ? PV_MODUL_HERKUNFT : undefined)
    : PV_MODUL_HERKUNFT
  const bars: VerlaufBar[] = [
    ...module.map((m, i) => ({ key: `m${m.id}`, label: m.bezeichnung, farbe: PV_MODUL_FARBEN[i % PV_MODUL_FARBEN.length], stapel: 'erz' })),
    ...zusatzAktiv.map((z) => ({ key: z.key, label: z.label, farbe: z.hex, stapel: 'erz' })),
    { key: 'direkt', label: 'Direktverbrauch', farbe: CHART_COLORS.eigenverbrauch, stapel: 'verw' },
    { key: 'sladung', label: 'Speicherladung', farbe: CHART_COLORS.speicherLadung, stapel: 'verw' },
    { key: 'einsp', label: 'Einspeisung', farbe: CHART_COLORS.einspeisung, stapel: 'verw' },
  ]
  const rows: VerlaufRow[] = [...jahr.keys()].sort((a, b) => a - b).map((j) => {
    const y = jahr.get(j)!
    const row: VerlaufRow = { name: String(j), direkt: Math.round(y.direkt), sladung: Math.round(y.speicher), einsp: Math.round(y.einsp) }
    for (const m of module) row[`m${m.id}`] = Math.round(modulWert(m, j, y.erz))
    for (const z of zusatzAktiv) row[z.key] = Math.round(y.zusatz[z.key] ?? 0)
    return row
  })
  const ges = [...jahr.values()].reduce((a, v) => ({ erz: a.erz + v.erz, direkt: a.direkt + v.direkt, speicher: a.speicher + v.speicher, einsp: a.einsp + v.einsp }), { erz: 0, direkt: 0, speicher: 0, einsp: 0 })
  const gesZusatz = (key: string) => [...jahr.values()].reduce((s, v) => s + (v.zusatz[key] ?? 0), 0)
  const modulSumme = (m: Investition) => hatModulwerte
    ? (pvStrings?.strings.find((s) => s.investition_id === m.id)?.ist_gesamt_kwh ?? 0)
    : kwpAnteil(m, ges.erz)
  return {
    bars, rows, gestapelt: true,
    // Chart-Stapel und Verteilungsbalken speisen sich aus derselben Quelle →
    // beide tragen dieselbe Kennzeichnung (oder eben keine).
    herkunft,
    verteilungen: [
      // Ohne `bezug`: der Balken trägt den Titel schon in der Kopfzeile. Titel
      // folgt dem Inhalt: mit BKW/BHKW sind es nicht mehr nur Module.
      {
        titel: zusatzAktiv.length ? 'Erzeugung nach Quelle' : 'Erzeugung nach Modul',
        herkunft: herkunft && { ...herkunft, bezug: undefined },
        segmente: [
          ...module.map((m, i) => ({ label: m.bezeichnung, wert: modulSumme(m), farbe: PV_MODUL_BG[i % PV_MODUL_BG.length] })),
          ...zusatzAktiv.map((z) => ({ label: z.label, wert: gesZusatz(z.key), farbe: z.bg })),
        ],
      },
      { titel: 'Verwendung der Erzeugung', segmente: [
        { label: 'Direktverbrauch', wert: ges.direkt, farbe: SEG.ev },
        { label: 'Speicherladung', wert: ges.speicher, farbe: SEG.ladung },
        { label: 'Einspeisung', wert: ges.einsp, farbe: SEG.einspeisung },
      ] },
    ],
  }
}

export const KOMPONENTEN_ADAPTER: Record<string, KompAdapter> = {
  // PV-Anlage = anlage-weites UI-Aggregat (cockpit-Übersicht + aggregierte Monate
  // für die EV/Einspeisung-Aufteilung). Genau ein „Gerät".
  'pv-module': {
    async fetch(anlageId) {
      // Vierter paralleler Call (A4/b2): die Pro-Modul-Messwerte für Block ④.
      // Fällt er aus, bleibt der kWp-Fallback in `pvVerlauf` — kein leerer Block.
      const [u, agg, invs, pvStrings] = await Promise.all([
        cockpitApi.getUebersicht(anlageId),
        monatsdatenApi.listAggregiert(anlageId).catch(() => []),
        investitionenApi.list(anlageId).catch(() => [] as Investition[]),
        cockpitApi.getPVStringsGesamtlaufzeit(anlageId).catch(() => null),
      ])
      const ev = agg.reduce((s, m) => s + (m.eigenverbrauch_kwh ?? 0), 0)
      const einsp = agg.reduce((s, m) => s + (m.einspeisung_kwh ?? 0), 0)
      const topo = bauePvTopologie(invs)
      const hatTopo = topo.art === 'topologie' && (topo.wr.length > 0 || topo.orphanModule.length > 0 || topo.orphanSpeicher.length > 0)
      const pvModule = invs.filter((i) => i.aktiv && i.typ === 'pv-module')
      const mv = pvModule.length ? pvVerlauf(agg, pvModule, pvStrings) : null
      return [{
        inv: { id: 0, anlage_id: anlageId, typ: 'pv-module', bezeichnung: 'PV-Anlage', aktiv: true } as Investition,
        label: 'PV-Anlage',
        status: [
          kpi(PV_ANLAGE_KPI.leistung, n1(u.anlagenleistung_kwp), 'kWp'),
          kpi(PV_ANLAGE_KPI.erzeugung, energie(u.pv_erzeugung_kwh).wert, energie(u.pv_erzeugung_kwh).einheit),
          kpi(PV_ANLAGE_KPI.spezErtrag, n0(u.spezifischer_ertrag_kwh_kwp), 'kWh/kWp'),
          kpi(PV_ANLAGE_KPI.eigenverbrauch, n0(u.eigenverbrauch_quote_prozent), '%'),
        ],
        aufteilung: (ev > 0 || einsp > 0) ? {
          titel: 'Verwendung der Erzeugung', segmente: [
            { label: 'Eigenverbrauch', wert: ev, farbe: SEG.ev },
            { label: 'Einspeisung', wert: einsp, farbe: SEG.einspeisung },
          ],
        } : undefined,
        // ④ Verlauf = Erzeugung je Modul ⟷ Verwendung (paarweise Stapel) + %-Aufteilungen.
        verlauf: (agg.length && mv) ? mv : undefined,
        // ⑤ Vergleich = echte IST-Analyse SOLL-IST pro String (komponentenAnalyse-Registry).
        vergleich: undefined,
        // Wirtschaftlichkeit = Ertrags-Zusammensetzung: EV-Ersparnis (vermiedener
        // Netzbezug) + Einspeise-Erlös → Netto-Ertrag.
        wirtschaftlichkeit: (ev > 0 || einsp > 0) ? {
          posten: [
            { label: 'Eigenverbrauchs-Ersparnis', euro: u.ev_ersparnis_euro, farbe: SEG.ev, hinweis: 'vermiedener Netzbezug' },
            { label: 'Einspeise-Erlös', euro: u.einspeise_erloes_euro, farbe: SEG.einspeisung },
          ],
          gesamt: { label: 'Netto-Ertrag', euro: u.netto_ertrag_euro },
          hinweis: 'Netto-Ertrag nach Betriebskosten und USt auf Eigenverbrauch.',
        } : undefined,
        struktur: hatTopo ? topo : undefined,
        // Einstellungen: alle aktiven PV-System-Investitionen (WR/Module/Speicher).
        verknuepfteInvs: invs.filter((i) => i.aktiv && ['wechselrichter', 'pv-module', 'speicher'].includes(i.typ)),
      }]
    },
  },

  speicher: {
    async fetch(anlageId) {
      const [ds, invs] = await Promise.all([
        investitionenApi.getSpeicherDashboard(anlageId),
        investitionenApi.list(anlageId).catch(() => [] as Investition[]),
      ])
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => {
      // η-Alarm färbt die Wirkungsgrad-Kachel rot (IST-getreu, #264).
      const wirkungsgradKpi = kpi(SPEICHER_KPI.wirkungsgrad, n0(z.ist_wirkungsgrad_prozent ?? z.effizienz_prozent), '%')
      // R15-5a: Netzladung-Kosten als reiner AUSWEIS — die Energie läuft über
      // den Hauszähler, die Kosten stecken bereits in den Netzbezug-Kosten der
      // Anlage (kein neuer Kostenposten, sonst Doppelzählung).
      const nlPreis = z.effektiver_ladepreis_cent ?? z.arbitrage_avg_preis_cent
      if (z.eta_degradation_alarm) wirkungsgradKpi.color = 'red'
      // ① Alarme (IST-getreu): Degradation + Durchsatz-Invariante.
      const hinweise: NonNullable<KompGeraet['hinweise']> = []
      if (z.eta_degradation_alarm && z.ist_wirkungsgrad_prozent != null && z.param_wirkungsgrad_prozent != null) {
        hinweise.push({ ton: 'warning', text: `Gemessener Wirkungsgrad (${n1(z.ist_wirkungsgrad_prozent)} %) liegt mehr als 5 Prozentpunkte unter dem Parameter-Wert (${n1(z.param_wirkungsgrad_prozent)} %) — möglicher Hinweis auf Speicher-Degradation. Wert prüfen, ggf. Parameter anpassen.` })
      }
      if (z.durchsatz_inkonsistent) {
        hinweise.push({ ton: 'warning', text: 'Die kumulierte Entladung übersteigt die kumulierte Ladung — über die gesamte Historie physikalisch unmöglich. Bitte die erfassten Lade- und Entlade-Werte prüfen (beim Datenübertrag leicht vertauscht).' })
      }
      // N127 / P4: ohne gepflegte Kapazität stehen Vollzyklen und Zyklen/Monat
      // auf „—" statt auf einer Zahl, die aus 10 kWh Annahme entstand. Der
      // Grund gehört sichtbar daneben, sonst liest sich das „—" wie ein Bug.
      if (z.kapazitaet_fehlt) {
        hinweise.push({ ton: 'warning', text: 'Für diesen Speicher ist keine Kapazität gepflegt — Vollzyklen und Zyklen pro Monat lassen sich daraus nicht berechnen. Kapazität in den Einstellungen unter Investitionen nachtragen.' })
      }
      return {
        inv, label: inv.bezeichnung,
        status: [
          kpi(SPEICHER_KPI.vollzyklen, n0(z.vollzyklen)),
          wirkungsgradKpi,
          kpi(SPEICHER_KPI.durchsatz, energie(z.gesamt_entladung_kwh).wert, energie(z.gesamt_entladung_kwh).einheit),
          kpi(SPEICHER_KPI.ersparnis, n0(z.ersparnis_euro), '€'),
        ],
        hinweise: hinweise.length ? hinweise : undefined,
        // ① Kennzahlen (IST-Summary-Karten): Ladung/Entladung gesamt, Zyklen/Monat, Verlust.
        kennzahlen: {
          titel: 'Kennzahlen', kpis: [
            k('Ladung gesamt', n0(z.gesamt_ladung_kwh), 'kWh', 'blue', Battery),
            k('Entladung gesamt', n0(z.gesamt_entladung_kwh), 'kWh', 'green', Zap),
            k('Zyklen/Monat', n1(z.zyklen_pro_monat), undefined, 'purple', Activity, { formel: 'Vollzyklen ÷ Anzahl Monate' }),
            k('Verlust', n0(z.gesamt_ladung_kwh - z.gesamt_entladung_kwh), 'kWh', 'gray', TrendingUp, { formel: 'Ladung − Entladung' }),
          ],
        },
        // ① Sekundär: Arbitrage (Netzladung) — schlanker Hinweis, Tiefe in #142/B11 (K-O2).
        sekundaer: (z.arbitrage_faehig && z.arbitrage_kwh > 0) ? {
          titel: 'Arbitrage (Netzladung)',
          kpis: [
            k('Netzladung', n0(z.arbitrage_kwh), 'kWh', 'red', Zap),
            k('Ø Ladepreis', n1(nlPreis), 'ct/kWh', 'yellow', Euro),
            k('Netzladung-Kosten', nlPreis != null ? n2((z.arbitrage_kwh * nlPreis) / 100) : '—', '€', 'red', Euro, {
              subtitle: 'in den Netzbezug-Kosten enthalten',
              formel: 'Netzladung × Ø Ladepreis — reiner Ausweis, kein zusätzlicher Kostenposten',
            }),
            k('Arbitrage-Gewinn', n0(z.arbitrage_gewinn_euro), '€', 'green', TrendingUp),
          ],
        } : undefined,
        // ② Verknüpfung (dünn): Zuordnung zu einem Wechselrichter (parent_investition_id).
        // BEWUSST nicht „DC-/AC-gekoppelt": eedc kennt kein Kopplungs-Feld, die
        // Zuordnung sagt nur, ob der Speicher in der Wirtschaftlichkeit als Teil
        // des PV-Systems oder eigenständig geführt wird. Ein AC-Speicher an einem
        // Hybrid-Wechselrichter wäre sonst falsch beschriftet (JayJay, Forum v4.0.0).
        struktur: {
          art: 'referenz',
          zeilen: [inv.parent_investition_id != null
            ? {
              label: 'Zuordnung',
              wert: invs.find((i) => i.id === inv.parent_investition_id)?.bezeichnung ?? '—',
              hinweis: 'Einem Wechselrichter zugeordnet — die Wirtschaftlichkeit wird als Teil des PV-Systems gerechnet.',
            }
            : {
              label: 'Zuordnung',
              wert: 'Eigenständig',
              hinweis: 'Keinem Wechselrichter zugeordnet — eigene Wirtschaftlichkeits-Rechnung. Für AC-gekoppelte Speicher der Normalfall.',
            }],
        } as KompStruktur,
        aufteilung: z.gesamt_ladung_kwh > 0 ? {
          titel: 'Ladung nach Quelle', segmente: [
            { label: 'PV-Ladung', wert: z.gesamt_ladung_kwh - (z.arbitrage_kwh ?? 0), farbe: SEG.pv },
            { label: 'Netz-Ladung', wert: z.arbitrage_kwh ?? 0, farbe: SEG.netz },
          ],
        } : undefined,
        verlauf: md.length ? {
          bars: [
            { key: 'ladung', label: 'Ladung', farbe: CHART_COLORS.speicherLadung },
            { key: 'entladung', label: 'Entladung', farbe: CHART_COLORS.speicherEntladung },
          ],
          rows: rowsAusMd(md, [
            { key: 'ladung', wert: (vd) => vd.ladung_kwh },
            { key: 'entladung', wert: (vd) => vd.entladung_kwh },
          ]),
        } : undefined,
        vergleich: md.length ? {
          label: 'Entladung', einheit: 'kWh', farbe: CHART_COLORS.speicherEntladung,
          jahre: jahresSummen(md, (vd) => vd.entladung_kwh),
        } : undefined,
        // Wirtschaftlichkeit = Ertrags-Zusammensetzung: Eigenverbrauchs-Ersparnis
        // (höhere PV-Nutzung) + Arbitrage-Gewinn (Netzladung billig → teuer), wenn vorhanden.
        // #358: Der erste Posten ist die PV-HÄLFTE (`pv_anteil_euro`), nicht die
        // Gesamt-Ersparnis — sonst steckte die netzgeladene Energie in beiden
        // Posten und die Aufstellung summierte über die tatsächliche Ersparnis
        // hinaus. Σ Posten = `ersparnis_euro`.
        wirtschaftlichkeit: (z.ersparnis_euro ?? 0) > 0 || (z.arbitrage_gewinn_euro ?? 0) > 0 ? {
          posten: [
            { label: 'Eigenverbrauchs-Ersparnis', euro: z.pv_anteil_euro ?? z.ersparnis_euro, farbe: SEG.ev, hinweis: 'erhöhter PV-Eigenverbrauch' },
            ...(z.arbitrage_faehig && (z.arbitrage_gewinn_euro ?? 0) > 0
              ? [{ label: 'Arbitrage-Gewinn', euro: z.arbitrage_gewinn_euro, farbe: SEG.netz, hinweis: 'günstig laden, teuer nutzen' }]
              : []),
          ],
        } : undefined,
      }
      })
    },
  },

  waermepumpe: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getWaermepumpeDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => {
      // ① Sekundär: getrennte JAZ (cop_*) + #238 Starts/Betriebsstunden — nur was gepflegt ist.
      const sek: KpiStripItem[] = []
      if (z.cop_heizen != null) sek.push(k('JAZ Heizen', formatEffizienz(z.cop_heizen).wert, undefined, 'orange', Flame, { formel: 'Heizwärme ÷ Strom Heizen' }))
      if (z.cop_warmwasser != null) sek.push(k('JAZ Warmwasser', formatEffizienz(z.cop_warmwasser).wert, undefined, 'cyan', Droplet, { formel: 'Warmwasser ÷ Strom Warmwasser' }))
      if (z.kompressor_starts_summe_erfasst != null) sek.push(k('Kompressor-Starts', n0(z.kompressor_starts_summe_erfasst), undefined, 'purple', Power, {
        subtitle: z.kompressor_starts_max_tag != null ? `Max/Tag: ${n0(z.kompressor_starts_max_tag)}` : undefined,
        berechnung: z.kompressor_starts_gesamt != null ? `Zählerstand (Lebensdauer): ${n0(z.kompressor_starts_gesamt)}` : undefined,
      }))
      if (z.betriebsstunden_summe_erfasst != null) sek.push(k('Betriebsstunden', n0(z.betriebsstunden_summe_erfasst), 'h', 'blue', Clock, {
        subtitle: z.betriebsstunden_max_tag != null ? `Max/Tag: ${n0(z.betriebsstunden_max_tag)} h` : undefined,
      }))
      if (z.oe_laufzeit_pro_start_h != null) sek.push(k('Ø Laufzeit/Start', n2(z.oe_laufzeit_pro_start_h), 'h', 'gray', Clock, { formel: 'Betriebsstunden ÷ Kompressor-Starts' }))
      if (z.starts_pro_betriebsstunde != null) sek.push(k('Starts/Betriebsstunde', n2(z.starts_pro_betriebsstunde), undefined, 'gray', Activity, { formel: 'Kompressor-Starts ÷ Betriebsstunden' }))
      // Gemeinsame Skalen-Referenz für Wärme+Strom (größerer Wert bestimmt kWh/MWh).
      const wpEnergieRef = Math.max(z.gesamt_waerme_kwh ?? 0, z.gesamt_stromverbrauch_kwh ?? 0)
      return {
        inv, label: inv.bezeichnung,
        status: [
          kpi(WP_KPI.jaz, formatEffizienz(z.durchschnitt_cop).wert),
          // Wärme+Strom an EINER Referenz skaliert (kein kWh/MWh-Mix im Strip, C3).
          kpi(WP_KPI.waerme, energie(z.gesamt_waerme_kwh, wpEnergieRef).wert, energie(z.gesamt_waerme_kwh, wpEnergieRef).einheit),
          kpi(WP_KPI.strom, energie(z.gesamt_stromverbrauch_kwh, wpEnergieRef).wert, energie(z.gesamt_stromverbrauch_kwh, wpEnergieRef).einheit),
          kpi(WP_KPI.ersparnis, n0(z.ersparnis_euro), '€'),
        ],
        sekundaer: sek.length ? { titel: 'Betrieb & getrennte JAZ', kpis: sek } : undefined,
        // ① CO₂-Ersparnis gegenüber fossiler Heizung (IST-getreu, eigene Kennzahl).
        kennzahlen: z.co2_ersparnis_kg != null ? {
          titel: 'Umwelt', kpis: [k('CO₂-Ersparnis', n0(z.co2_ersparnis_kg), 'kg', 'green', Leaf, { subtitle: 'vs. fossile Heizung' })],
        } : undefined,
        aufteilung: (z.gesamt_heizenergie_kwh > 0 || z.gesamt_warmwasser_kwh > 0) ? {
          titel: 'Wärme nach Zweck', segmente: [
            { label: 'Heizung', wert: z.gesamt_heizenergie_kwh, farbe: SEG.heizung },
            { label: 'Warmwasser', wert: z.gesamt_warmwasser_kwh, farbe: SEG.warmwasser },
          ],
        } : undefined,
        verlauf: md.length ? {
          bars: [
            { key: 'heizung', label: 'Heizung', farbe: CHART_COLORS.wpWaerme },
            { key: 'warmwasser', label: 'Warmwasser', farbe: CHART_COLORS.wpWarmwasser },
          ],
          rows: rowsAusMd(md, [
            { key: 'heizung', wert: (vd) => vd.heizenergie_kwh },
            { key: 'warmwasser', wert: (vd) => vd.warmwasser_kwh },
          ]),
        } : undefined,
        vergleich: md.length ? {
          label: 'Wärme', einheit: 'kWh', farbe: CHART_COLORS.wpWaerme,
          jahre: jahresSummen(md, (vd) => (vd.heizenergie_kwh ?? 0) + (vd.warmwasser_kwh ?? 0)),
        } : undefined,
      }
      })
    },
  },

  'e-auto': {
    async fetch(anlageId) {
      const ds = await investitionenApi.getEAutoDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => ({
        inv, label: inv.bezeichnung,
        status: [
          kpi(EAUTO_KPI.gefahren, n0(z.gesamt_km), 'km'),
          kpi(EAUTO_KPI.verbrauch, n1(z.durchschnitt_verbrauch_kwh_100km), 'kWh/100km'),
          kpi(EAUTO_KPI.pvAnteil, n0(z.pv_anteil_heim_prozent), '%'),
          kpi(EAUTO_KPI.ersparnis, n0(z.ersparnis_vs_benzin_euro), '€'),
        ],
        // ① CO₂-Ersparnis vs. Verbrenner (IST-getreu, eigene Kennzahl).
        kennzahlen: z.co2_ersparnis_kg != null ? {
          titel: 'Umwelt', kpis: [k('CO₂-Ersparnis', n0(z.co2_ersparnis_kg), 'kg', 'green', Leaf, { subtitle: 'vs. Verbrenner' })],
        } : undefined,
        aufteilung: z.gesamt_ladung_kwh > 0 ? {
          titel: 'Ladequellen', segmente: [
            { label: 'PV', wert: z.ladung_pv_kwh, farbe: SEG.pv },
            { label: 'Netz', wert: z.ladung_netz_kwh, farbe: SEG.netz },
            { label: 'Extern', wert: z.ladung_extern_kwh, farbe: SEG.extern },
          ],
        } : undefined,
        verlauf: md.length ? {
          bars: [
            { key: 'pv', label: 'PV-Ladung', farbe: LADEQUELLEN_FARBEN.pv },
            { key: 'netz', label: 'Netz-Ladung', farbe: LADEQUELLEN_FARBEN.netz },
          ],
          rows: rowsAusMd(md, [
            { key: 'pv', wert: (vd) => vd.ladung_pv_kwh },
            { key: 'netz', wert: (vd) => vd.ladung_netz_kwh },
          ]),
        } : undefined,
        vergleich: md.length ? {
          label: 'Ladung', einheit: 'kWh', farbe: CHART_COLORS.emobLadung,
          jahre: jahresSummen(md, (vd) => (vd.ladung_pv_kwh ?? 0) + (vd.ladung_netz_kwh ?? 0)),
        } : undefined,
        // ③ Sub-Komponente: V2H (Vehicle-to-Home) — nur wenn entladen wurde.
        subKomponente: (z.v2h_entladung_kwh ?? 0) > 0 ? {
          titel: 'Vehicle-to-Home (V2H)',
          kpis: [
            k('V2H Entladung', n1(z.v2h_entladung_kwh), 'kWh', 'purple', Battery),
            k('V2H Ersparnis', n0(z.v2h_ersparnis_euro), '€', 'green', TrendingUp),
          ],
        } : undefined,
      }))
    },
  },

  wallbox: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getWallboxDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => ({
        inv, label: inv.bezeichnung,
        status: [
          kpi(WALLBOX_KPI.heimladung, energie(z.gesamt_heim_ladung_kwh).wert, energie(z.gesamt_heim_ladung_kwh).einheit),
          kpi(WALLBOX_KPI.pvAnteil, n0(z.pv_anteil_prozent), '%'),
          kpi(WALLBOX_KPI.ladevorgaenge, n0(z.gesamt_ladevorgaenge)),
          kpi(WALLBOX_KPI.ersparnis, n0(z.ersparnis_vs_extern_euro), '€'),
        ],
        aufteilung: z.gesamt_heim_ladung_kwh > 0 ? {
          titel: 'Heimladung nach Quelle', segmente: [
            { label: 'PV', wert: z.ladung_pv_kwh, farbe: SEG.pv },
            { label: 'Netz', wert: z.ladung_netz_kwh, farbe: SEG.netz },
          ],
        } : undefined,
        // ② Verknüpfung (dünn): PV/Netz-Split ist aus E-Auto-Ladedaten abgeleitet (IST-treu);
        //    die eigene Heimladung/Vorgänge-Zeitreihe steht in der Wallbox-IMD.
        struktur: {
          art: 'referenz',
          zeilen: [{ label: 'PV/Netz-Aufteilung', wert: 'aus E-Auto-Ladedaten', hinweis: 'Die PV-/Netz-Aufteilung der Heimladung wird aus den E-Auto-Ladedaten dieser Anlage abgeleitet.' }],
        } as KompStruktur,
        // ④ Verlauf: Heimladung je Monat (PV/Netz-Split nur als Gesamt-Aufteilung, s. ①).
        verlauf: md.length ? {
          bars: [{ key: 'heim', label: 'Heimladung', farbe: CHART_COLORS.emobLadung }],
          rows: rowsAusMd(md, [{ key: 'heim', wert: (vd) => vd.ladung_kwh }]),
        } : undefined,
        vergleich: md.length ? {
          label: 'Heimladung', einheit: 'kWh', farbe: CHART_COLORS.emobLadung,
          jahre: jahresSummen(md, (vd) => vd.ladung_kwh),
        } : undefined,
      }))
    },
  },

  balkonkraftwerk: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getBalkonkraftwerkDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => ({
        inv, label: inv.bezeichnung,
        status: [
          kpi(BKW_KPI.erzeugung, n0(z.gesamt_erzeugung_kwh), 'kWh'),
          kpi(BKW_KPI.eigenverbrauch, n0(z.eigenverbrauch_quote_prozent), '%'),
          kpi(BKW_KPI.ersparnis, n0(z.gesamt_ersparnis_euro), '€'),
          kpi(BKW_KPI.spezErtrag, n0(z.spezifischer_ertrag_kwh_kwp), 'kWh/kWp'),
        ],
        // ① IST-Summary-Karten: CO₂, Eigenverbrauch-Summe, Einspeisung, entgangener
        //    Erlös (Einspeisung × 8 ct/kWh — wie IST, unvergütete BKW-Einspeisung).
        kennzahlen: {
          titel: 'Kennzahlen', kpis: [
            k('CO₂-Ersparnis', n0(z.co2_ersparnis_kg), 'kg', 'green', Leaf, { subtitle: 'Eigenverbrauch × 0,4 kg/kWh' }),
            k('Eigenverbrauch', n0(z.gesamt_eigenverbrauch_kwh), 'kWh', 'green', Zap),
            k('Einspeisung', n0(z.gesamt_einspeisung_kwh), 'kWh', 'orange', TrendingUp, { subtitle: 'unvergütet' }),
            k('Entgangener Erlös', n2(z.gesamt_einspeisung_kwh * 0.08), '€', 'gray', Euro, { formel: 'Einspeisung × 8 ct/kWh' }),
          ],
        },
        aufteilung: z.gesamt_erzeugung_kwh > 0 ? {
          titel: 'Verwendung der Erzeugung', segmente: [
            { label: 'Eigenverbrauch', wert: z.gesamt_eigenverbrauch_kwh, farbe: SEG.ev },
            { label: 'Einspeisung', wert: z.gesamt_einspeisung_kwh, farbe: SEG.einspeisung },
          ],
        } : undefined,
        verlauf: md.length ? {
          bars: [
            { key: 'ev', label: 'Eigenverbrauch', farbe: CHART_COLORS.eigenverbrauch },
            { key: 'einsp', label: 'Einspeisung', farbe: CHART_COLORS.einspeisung },
          ],
          // Einspeisung im Monat = Erzeugung − Eigenverbrauch (kein eigener Key).
          rows: rowsAusMd(md, [
            { key: 'ev', wert: (vd) => vd.eigenverbrauch_kwh },
            { key: 'einsp', wert: (vd) => (vd.pv_erzeugung_kwh ?? 0) - (vd.eigenverbrauch_kwh ?? 0) },
          ]),
        } : undefined,
        vergleich: md.length ? {
          label: 'Erzeugung', einheit: 'kWh', farbe: CHART_COLORS.erzeugung,
          jahre: jahresSummen(md, (vd) => vd.pv_erzeugung_kwh ?? 0),
        } : undefined,
        // Wirtschaftlichkeit = Ertrags-Zusammensetzung: 1 Posten (Eigenverbrauchs-
        // Ersparnis); BKW-Einspeisung ist unvergütet → als Hinweis (entgangener Erlös), kein Posten.
        wirtschaftlichkeit: (z.gesamt_ersparnis_euro ?? 0) > 0 ? {
          posten: [{ label: 'Eigenverbrauchs-Ersparnis', euro: z.gesamt_ersparnis_euro, farbe: SEG.ev, hinweis: 'vermiedener Netzbezug' }],
          hinweis: (z.gesamt_einspeisung_kwh ?? 0) > 0
            ? `Einspeisung unvergütet — entgangener Erlös rechnerisch ${n2(z.gesamt_einspeisung_kwh * 0.08)} € (8 ct/kWh).`
            : undefined,
        } : undefined,
        // ③ Sub-Komponente: integrierter Speicher (Eigenschaft des BKW-Wirts).
        subKomponente: z.hat_speicher ? {
          titel: 'Integrierter Speicher',
          hinweis: z.speicher_kapazitaet_wh ? `Kapazität: ${n0(z.speicher_kapazitaet_wh)} Wh` : undefined,
          kpis: [
            k('Ladung', n1(z.speicher_ladung_kwh), 'kWh', 'purple', Battery),
            k('Entladung', n1(z.speicher_entladung_kwh), 'kWh', 'green', Zap),
            k('Effizienz', n1(z.speicher_effizienz_prozent), '%', 'blue', Activity),
          ],
        } : undefined,
      }))
    },
  },

  sonstiges: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getSonstigesDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => {
        // Kategorie-Badge (Selektor-Differenzierung, SoT-Map R3b S7) + Sonderkosten-Alert (IST-getreu).
        const selektorBadge = SONSTIGES_KATEGORIE_LABELS[z.kategorie] ?? 'Sonstiges'
        const hinweise: KompGeraet['hinweise'] = (z.sonderkosten_euro ?? 0) > 0
          ? [{ ton: 'warning', text: `Sonderkosten (Reparaturen, Wartung): ${n2(z.sonderkosten_euro)} €` }]
          : undefined
        if (z.kategorie === 'verbraucher') {
          return {
            inv, label: inv.bezeichnung, selektorBadge, hinweise,
            status: [
              kpi(SONSTIGES_VERBRAUCHER_KPI.verbrauch, n0(z.gesamt_verbrauch_kwh), 'kWh'),
              kpi(SONSTIGES_VERBRAUCHER_KPI.pvAnteil, n0(z.pv_anteil_prozent), '%'),
              kpi(SONSTIGES_VERBRAUCHER_KPI.netzkosten, n0(z.kosten_netz_euro), '€'),
              kpi(SONSTIGES_VERBRAUCHER_KPI.pvErsparnis, n0(z.ersparnis_pv_euro), '€'),
            ],
            aufteilung: (z.bezug_pv_kwh != null || z.bezug_netz_kwh != null) ? {
              titel: 'Strombezug', segmente: [
                { label: 'PV', wert: z.bezug_pv_kwh, farbe: SEG.pv },
                { label: 'Netz', wert: z.bezug_netz_kwh, farbe: SEG.netz },
              ],
            } : undefined,
            // ④ Verlauf: Strombezug je Monat nach Quelle (PV ⟷ Netz, gestapelt).
            verlauf: md.length ? {
              bars: [
                { key: 'pv', label: 'PV', farbe: LADEQUELLEN_FARBEN.pv },
                { key: 'netz', label: 'Netz', farbe: LADEQUELLEN_FARBEN.netz },
              ],
              rows: rowsAusMd(md, [
                { key: 'pv', wert: (vd) => vd.bezug_pv_kwh },
                { key: 'netz', wert: (vd) => vd.bezug_netz_kwh },
              ]),
            } : undefined,
            vergleich: md.length ? {
              label: 'Verbrauch', einheit: 'kWh', farbe: CHART_COLORS.netzbezug,
              jahre: jahresSummen(md, (vd) => vd.verbrauch_kwh),
            } : undefined,
            // Wirtschaftlichkeit = Ertrags-Zusammensetzung: PV-Ersparnis (PV-Bezug
            // statt Netz) — 1 Posten.
            wirtschaftlichkeit: (z.ersparnis_pv_euro ?? 0) > 0 ? {
              posten: [{ label: 'PV-Ersparnis', euro: z.ersparnis_pv_euro, farbe: SEG.pv, hinweis: 'PV-Bezug statt Netz' }],
            } : undefined,
          }
        }
        if (z.kategorie === 'speicher') {
          return {
            inv, label: inv.bezeichnung, selektorBadge, hinweise,
            status: [
              kpi(SONSTIGES_SPEICHER_KPI.ladung, n0(z.gesamt_ladung_kwh), 'kWh'),
              kpi(SONSTIGES_SPEICHER_KPI.entladung, n0(z.gesamt_entladung_kwh), 'kWh'),
              kpi(SONSTIGES_SPEICHER_KPI.effizienz, n0(z.effizienz_prozent), '%'),
              kpi(SONSTIGES_SPEICHER_KPI.ersparnis, n0(z.ersparnis_euro), '€'),
            ],
            aufteilung: (z.gesamt_ladung_kwh ?? 0) > 0 ? {
              titel: 'Ladung / Entladung', segmente: [
                { label: 'Ladung', wert: z.gesamt_ladung_kwh, farbe: SEG.ladung },
                { label: 'Entladung', wert: z.gesamt_entladung_kwh, farbe: SEG.entladung },
              ],
            } : undefined,
            // ④ Verlauf: Ladung ⟷ Entladung je Monat (wie Haupt-Speicher).
            verlauf: md.length ? {
              bars: [
                { key: 'ladung', label: 'Ladung', farbe: CHART_COLORS.speicherLadung },
                { key: 'entladung', label: 'Entladung', farbe: CHART_COLORS.speicherEntladung },
              ],
              rows: rowsAusMd(md, [
                { key: 'ladung', wert: (vd) => vd.ladung_kwh },
                { key: 'entladung', wert: (vd) => vd.entladung_kwh },
              ]),
            } : undefined,
            vergleich: md.length ? {
              label: 'Entladung', einheit: 'kWh', farbe: CHART_COLORS.speicherEntladung,
              jahre: jahresSummen(md, (vd) => vd.entladung_kwh),
            } : undefined,
            // Wirtschaftlichkeit = Ertrags-Zusammensetzung: Ersparnis durch erhöhten
            // Eigenverbrauch — 1 Posten.
            wirtschaftlichkeit: (z.ersparnis_euro ?? 0) > 0 ? {
              posten: [{ label: 'Eigenverbrauchs-Ersparnis', euro: z.ersparnis_euro, farbe: SEG.ev }],
            } : undefined,
          }
        }
        // Default: Erzeuger. Sonstiger Erzeuger (BHKW/Pellet/Brennstoffzelle) speist
        // hinter den Hauszähler → seine Erzeugung zählt in die Netzpunkt-Bilanz
        // (EV/Autarkie, Backend v3.45.4). Die GERÄTESCHARFE Identität bleibt aber
        // getrennt: ohne Brennstoffmodell sind CO₂-Ersparnis und Wirtschaftlichkeit
        // nicht bewertbar (kein Fake-0), und der EV/Einspeisung-Split wird je Gerät
        // nicht gemessen (Konzept Gernot 2026-06-22, [[feedback_keine_erfundenen_ausnahmeregeln]]).
        const erzEvGemessen = (z.gesamt_eigenverbrauch_kwh ?? 0) > 0 || (z.gesamt_einspeisung_kwh ?? 0) > 0
        return {
          inv, label: inv.bezeichnung, selektorBadge, hinweise,
          status: [
            kpi(SONSTIGES_ERZEUGER_KPI.erzeugung, n0(z.gesamt_erzeugung_kwh), 'kWh'),
            erzEvGemessen
              ? kpi(SONSTIGES_ERZEUGER_KPI.eigenverbrauch, n0(z.eigenverbrauch_quote_prozent), '%')
              : unbewertet(SONSTIGES_ERZEUGER_KPI.eigenverbrauch, 'je Gerät nicht gemessen'),
            unbewertet(SONSTIGES_ERZEUGER_KPI.ersparnis, 'Brennstoffkosten unbekannt'),
            unbewertet(SONSTIGES_ERZEUGER_KPI.co2, 'Brennstoff-CO₂ unbekannt'),
          ],
          // Aufteilung nur, wenn der EV/Einspeisung-Split tatsächlich erfasst ist
          // (sonst zwei 0-Segmente = Fake).
          aufteilung: erzEvGemessen ? {
            titel: 'Verwendung der Erzeugung', segmente: [
              { label: 'Eigenverbrauch', wert: z.gesamt_eigenverbrauch_kwh, farbe: SEG.ev },
              { label: 'Einspeisung', wert: z.gesamt_einspeisung_kwh, farbe: SEG.einspeisung },
            ],
          } : undefined,
          // ④ Verlauf: Erzeugung je Monat (EV/Einspeisung-Split nur als Gesamt-Aufteilung, s. ①).
          // Eigene Identitätsfarbe (Lime) — ein sonstiger Erzeuger/Mini-BHKW ist NICHT PV (Regel A).
          verlauf: md.length ? {
            bars: [{ key: 'erz', label: 'Erzeugung', farbe: SONSTIGES_ERZEUGER_FARBE.hex }],
            rows: rowsAusMd(md, [{ key: 'erz', wert: (vd) => vd.erzeugung_kwh }]),
          } : undefined,
          vergleich: md.length ? {
            label: 'Erzeugung', einheit: 'kWh', farbe: SONSTIGES_ERZEUGER_FARBE.hex,
            jahre: jahresSummen(md, (vd) => vd.erzeugung_kwh),
          } : undefined,
          // Wirtschaftlichkeit ehrlich „nicht bewertet": Brennstoffkosten und
          // Brennstoff-CO₂ eines sonstigen Erzeugers (BHKW/Pellet/Brennstoffzelle)
          // sind ohne Brennstoffmodell nicht bewertbar — kein Fake-Ersparnis.
          wirtschaftlichkeit: {
            posten: [],
            nichtBewertet: 'Brennstoffkosten und -CO₂ eines sonstigen Erzeugers (z. B. BHKW) sind ohne hinterlegtes Brennstoffmodell nicht bewertbar. Die Erzeugung zählt energetisch in die Anlagenbilanz (Eigenverbrauch/Autarkie); eine eigene Wirtschaftlichkeits- oder CO₂-Bewertung wäre an dieser Stelle Spekulation.',
          },
        }
      })
    },
  },
}
