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
 * Bewusst NUR die abgenommenen Pflicht-Block-Inhalte (Status + Aufteilung);
 * Verlauf/Vergleich/Aussicht + spezifische Blöcke (②③⑥) docken später an.
 */
import { fmtCalc } from '../components/ui'
import { MONAT_KURZ } from '../lib'
import { CHART_COLORS, LADEQUELLEN_FARBEN } from '../lib/colors'
import { cockpitApi } from '../api/cockpit'
import { investitionenApi, type InvestitionMonatsdaten } from '../api/investitionen'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import {
  PV_ANLAGE_KPI, SPEICHER_KPI, WP_KPI, EAUTO_KPI, WALLBOX_KPI, BKW_KPI,
  SONSTIGES_ERZEUGER_KPI, SONSTIGES_VERBRAUCHER_KPI, SONSTIGES_SPEICHER_KPI,
  type KpiStyle,
} from '../lib/komponentenStyle'
import type { KpiStripItem } from '../components/blocks'
import type { VerteilungSegment } from '../components/blocks'
import type { VerlaufBar, VerlaufRow } from './KomponentenVerlaufChart'
import type { Investition } from '../types'

/** Tailwind-bg-Rollenfarben für die Aufteilungs-Segmente (keine Inline-Hex). */
const SEG = {
  pv: 'bg-green-500', ev: 'bg-green-500', einspeisung: 'bg-blue-400',
  netz: 'bg-red-500', extern: 'bg-gray-400', heizung: 'bg-orange-500',
  warmwasser: 'bg-red-400', entladung: 'bg-green-500', ladung: 'bg-purple-500',
} as const

/** Ein Gerät (oder UI-Aggregat) eines Typs — generisch von der Sicht konsumiert. */
export interface KompGeraet {
  inv: Investition
  label: string
  status: KpiStripItem[]
  aufteilung?: { titel: string; einheit?: string; segmente: VerteilungSegment[] }
  /** Block ④ Verlauf: gestapelter Monatsverlauf (gesamte Historie). */
  verlauf?: { bars: VerlaufBar[]; rows: VerlaufRow[]; einheit?: string }
  /** Block ⑤ Vergleich (dünn): Jahressummen einer Leitkennzahl je Jahr. */
  vergleich?: { label: string; einheit: string; farbe: string; jahre: { jahr: number; summe: number }[] }
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

/** MWh-formatiert (kWh-Eingang), 1 Nachkomma; '—' bei fehlend. */
const mwh = (kwh: number | null | undefined) => fmtCalc(kwh != null ? kwh / 1000 : null, 1, '—')
const n0 = (v: number | null | undefined) => fmtCalc(v, 0, '—')
const n1 = (v: number | null | undefined) => fmtCalc(v, 1, '—')

/** PV-Verlauf aus aggregierten Monaten (EV/Einspeisung), chronologisch. */
function pvVerlaufRows(agg: AggregierteMonatsdaten[]): VerlaufRow[] {
  return [...agg]
    .sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat))
    .map((m) => ({
      name: `${MONAT_KURZ[m.monat]} ${String(m.jahr).slice(2)}`,
      ev: Math.max(0, m.eigenverbrauch_kwh ?? 0),
      einsp: Math.max(0, m.einspeisung_kwh ?? 0),
    }))
}

/** PV-Jahressummen Erzeugung (= EV + Einspeisung) aus aggregierten Monaten. */
function pvJahresSummen(agg: AggregierteMonatsdaten[]): { jahr: number; summe: number }[] {
  const m = new Map<number, number>()
  for (const r of agg) m.set(r.jahr, (m.get(r.jahr) ?? 0) + Math.max(0, (r.eigenverbrauch_kwh ?? 0) + (r.einspeisung_kwh ?? 0)))
  return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([jahr, summe]) => ({ jahr, summe }))
}

export const KOMPONENTEN_ADAPTER: Record<string, KompAdapter> = {
  // PV-Anlage = anlage-weites UI-Aggregat (cockpit-Übersicht + aggregierte Monate
  // für die EV/Einspeisung-Aufteilung). Genau ein „Gerät".
  'pv-module': {
    async fetch(anlageId) {
      const [u, agg] = await Promise.all([
        cockpitApi.getUebersicht(anlageId),
        monatsdatenApi.listAggregiert(anlageId).catch(() => []),
      ])
      const ev = agg.reduce((s, m) => s + (m.eigenverbrauch_kwh ?? 0), 0)
      const einsp = agg.reduce((s, m) => s + (m.einspeisung_kwh ?? 0), 0)
      return [{
        inv: { id: 0, anlage_id: anlageId, typ: 'pv-module', bezeichnung: 'PV-Anlage', aktiv: true } as Investition,
        label: 'PV-Anlage',
        status: [
          kpi(PV_ANLAGE_KPI.leistung, n1(u.anlagenleistung_kwp), 'kWp'),
          kpi(PV_ANLAGE_KPI.erzeugung, mwh(u.pv_erzeugung_kwh), 'MWh'),
          kpi(PV_ANLAGE_KPI.spezErtrag, n0(u.spezifischer_ertrag_kwh_kwp), 'kWh/kWp'),
          kpi(PV_ANLAGE_KPI.eigenverbrauch, n0(u.eigenverbrauch_quote_prozent), '%'),
        ],
        aufteilung: (ev > 0 || einsp > 0) ? {
          titel: 'Verwendung der Erzeugung', segmente: [
            { label: 'Eigenverbrauch', wert: ev, farbe: SEG.ev },
            { label: 'Einspeisung', wert: einsp, farbe: SEG.einspeisung },
          ],
        } : undefined,
        verlauf: agg.length ? {
          bars: [
            { key: 'ev', label: 'Eigenverbrauch', farbe: CHART_COLORS.eigenverbrauch },
            { key: 'einsp', label: 'Einspeisung', farbe: CHART_COLORS.einspeisung },
          ],
          rows: pvVerlaufRows(agg),
        } : undefined,
        vergleich: agg.length ? {
          label: 'Erzeugung', einheit: 'kWh', farbe: CHART_COLORS.erzeugung,
          jahre: pvJahresSummen(agg),
        } : undefined,
      }]
    },
  },

  speicher: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getSpeicherDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => ({
        inv, label: inv.bezeichnung,
        status: [
          kpi(SPEICHER_KPI.vollzyklen, n0(z.vollzyklen)),
          kpi(SPEICHER_KPI.wirkungsgrad, n0(z.ist_wirkungsgrad_prozent ?? z.effizienz_prozent), '%'),
          kpi(SPEICHER_KPI.durchsatz, mwh(z.gesamt_entladung_kwh), 'MWh'),
          kpi(SPEICHER_KPI.ersparnis, n0(z.ersparnis_euro), '€'),
        ],
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
      }))
    },
  },

  waermepumpe: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getWaermepumpeDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z, monatsdaten: md }) => ({
        inv, label: inv.bezeichnung,
        status: [
          kpi(WP_KPI.jaz, n1(z.durchschnitt_cop)),
          kpi(WP_KPI.waerme, mwh(z.gesamt_waerme_kwh), 'MWh'),
          kpi(WP_KPI.strom, mwh(z.gesamt_stromverbrauch_kwh), 'MWh'),
          kpi(WP_KPI.ersparnis, n0(z.ersparnis_euro), '€'),
        ],
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
      }))
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
      }))
    },
  },

  wallbox: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getWallboxDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z }) => ({
        inv, label: inv.bezeichnung,
        status: [
          kpi(WALLBOX_KPI.heimladung, mwh(z.gesamt_heim_ladung_kwh), 'MWh'),
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
      }))
    },
  },

  sonstiges: {
    async fetch(anlageId) {
      const ds = await investitionenApi.getSonstigesDashboard(anlageId)
      return ds.map(({ investition: inv, zusammenfassung: z }) => {
        if (z.kategorie === 'verbraucher') {
          return {
            inv, label: inv.bezeichnung,
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
          }
        }
        if (z.kategorie === 'speicher') {
          return {
            inv, label: inv.bezeichnung,
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
          }
        }
        // Default: Erzeuger
        return {
          inv, label: inv.bezeichnung,
          status: [
            kpi(SONSTIGES_ERZEUGER_KPI.erzeugung, n0(z.gesamt_erzeugung_kwh), 'kWh'),
            kpi(SONSTIGES_ERZEUGER_KPI.eigenverbrauch, n0(z.eigenverbrauch_quote_prozent), '%'),
            kpi(SONSTIGES_ERZEUGER_KPI.ersparnis, n0(z.gesamt_ersparnis_euro), '€'),
            kpi(SONSTIGES_ERZEUGER_KPI.co2, n1((z.co2_ersparnis_kg ?? 0) / 1000), 't'),
          ],
          aufteilung: (z.gesamt_erzeugung_kwh ?? 0) > 0 ? {
            titel: 'Verwendung der Erzeugung', segmente: [
              { label: 'Eigenverbrauch', wert: z.gesamt_eigenverbrauch_kwh, farbe: SEG.ev },
              { label: 'Einspeisung', wert: z.gesamt_einspeisung_kwh, farbe: SEG.einspeisung },
            ],
          } : undefined,
        }
      })
    },
  },
}
