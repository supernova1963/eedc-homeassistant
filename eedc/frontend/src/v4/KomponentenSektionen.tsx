/**
 * KomponentenSektionen — Komponenten-Detailblöcke der Cockpit/Monat-Sicht
 * (IA v4 E3 Slice 2d, B6 + B7).
 *
 * Pro AKTIVER Komponente (Speicher/WP/E-Mob/BKW/Sonstiges) ein eingeklappter
 * Block mit Status-KPI-Strip (D2-Kanon) + Summary-Zeile + Komponenten-Identitäts-
 * Farbe. Schlank wie in der IA-v4-Vorschau (`KOMP_STATUS`/`COCKPIT_DETAIL`), die
 * Kennzahlen aber verhaltensgleich zum Donor `MonatsabschlussView`. Wärmepumpe
 * trägt zusätzlich `VerteilungsBalken` Heizung/Warmwasser (B7-Revision: Donut → Balken).
 *
 * Quelle: `AktuellerMonatResponse` (alle Komponenten-Felder bereits vorhanden).
 * Aktiv-Gating: ein Block erscheint nur, wenn die Komponente im Monat Daten hat.
 */
import type { ReactNode } from 'react'
import { Battery, TrendingUp, Plug } from 'lucide-react'
import { fmtCalc } from '../components/ui'
import { KpiStrip, VerteilungsBalken, type Block, type KpiStripItem } from '../components/blocks'
import {
  KOMPONENTEN_IDENTITAET,
  SPEICHER_KPI, WP_KPI, EAUTO_KPI, BKW_KPI,
  SONSTIGES_ERZEUGER_KPI, SONSTIGES_VERBRAUCHER_KPI,
} from '../lib'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')
const hat = (v: number | null | undefined) => v != null

/** Sektions-Kopf-Identität (Icon + Farbe) aus dem SoT — #3b'. */
const ident = (typ: string) => {
  const i = KOMPONENTEN_IDENTITAET[typ]
  return { icon: i.icon, farbe: i.farbe }
}

function Sektion({ kpis, extra }: { kpis: KpiStripItem[]; extra?: ReactNode }) {
  return (
    <div className="space-y-3">
      <KpiStrip kpis={kpis} />
      {extra}
    </div>
  )
}

/** Liefert die Blöcke der aktiven Komponenten in kanonischer Reihenfolge. */
export function baueKomponentenBloecke(d: AktuellerMonatResponse): Block[] {
  const bloecke: Block[] = []

  // ── Speicher ────────────────────────────────────────────────────────────
  if (hat(d.speicher_ladung_kwh) || hat(d.speicher_entladung_kwh) || hat(d.speicher_kapazitaet_kwh)) {
    // Ladung/Entladung haben kein D2-Status-Pendant → bleiben (Teaser-Metrik);
    // Wirkungsgrad/Vollzyklen ziehen Icon/Farbe/Titel aus dem D2-Kanon.
    const kpis: KpiStripItem[] = [
      { title: 'Ladung', value: fmt(d.speicher_ladung_kwh), unit: 'kWh', color: 'blue', icon: Battery },
      { title: 'Entladung', value: fmt(d.speicher_entladung_kwh), unit: 'kWh', color: 'green', icon: Battery },
      { ...SPEICHER_KPI.wirkungsgrad, value: fmtCalc(d.speicher_wirkungsgrad_prozent, 1, '—'), unit: '%',
        subtitle: d.speicher_soc_drift_signifikant ? 'SoC-Drift — Monats-η ausgeblendet' : undefined },
      { ...SPEICHER_KPI.vollzyklen, value: fmtCalc(d.speicher_vollzyklen, 2, '—'),
        subtitle: hat(d.speicher_kapazitaet_kwh) ? `Kapazität ${fmt(d.speicher_kapazitaet_kwh)} kWh` : undefined },
    ]
    bloecke.push({
      id: 'k-speicher', title: 'Speicher', ...ident('speicher'), defaultOpen: false,
      summary: `${fmt(d.speicher_ladung_kwh)} kWh geladen · ${fmtCalc(d.speicher_vollzyklen, 1, '—')} Zyklen · ${fmtCalc(d.speicher_wirkungsgrad_prozent, 0, '—')} % η`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  // ── Wärmepumpe ──────────────────────────────────────────────────────────
  if (hat(d.wp_strom_kwh) || hat(d.wp_waerme_kwh)) {
    const jaz = hat(d.wp_waerme_kwh) && d.wp_strom_kwh ? d.wp_waerme_kwh! / d.wp_strom_kwh : null
    const kpis: KpiStripItem[] = [
      { ...WP_KPI.jaz, value: fmtCalc(jaz, 2, '—'), formel: 'JAZ = Wärme ÷ Strom' },
      { ...WP_KPI.waerme, value: fmt(d.wp_waerme_kwh), unit: 'kWh' },
      { ...WP_KPI.strom, value: fmt(d.wp_strom_kwh), unit: 'kWh' },
      { ...WP_KPI.ersparnis, value: hat(d.wp_ersparnis_euro) ? `+${fmtCalc(d.wp_ersparnis_euro, 2)}` : '—', unit: '€' },
    ]
    bloecke.push({
      id: 'k-waermepumpe', title: KOMPONENTEN_IDENTITAET['waermepumpe'].label, ...ident('waermepumpe'), defaultOpen: false,
      summary: `${jaz != null ? `JAZ ${fmtCalc(jaz, 2)} · ` : ''}${fmt(d.wp_waerme_kwh)} kWh Wärme${hat(d.wp_ersparnis_euro) ? ` · +${fmt(d.wp_ersparnis_euro, 0)} € vs. Gas` : ''}`,
      // Heizung/Warmwasser-Aufteilung als VerteilungsBalken (B7-Revision: Donut → Balken).
      render: () => <Sektion kpis={kpis} extra={
        <VerteilungsBalken segmente={[
          { label: 'Heizung', wert: d.wp_heizung_kwh, farbe: 'bg-red-500' },
          { label: 'Warmwasser', wert: d.wp_warmwasser_kwh, farbe: 'bg-blue-500' },
        ]} />
      } />,
    })
  }

  // ── E-Mobilität ─────────────────────────────────────────────────────────
  if (hat(d.emob_ladung_kwh) || hat(d.emob_km)) {
    const pvAnteil = hat(d.emob_ladung_pv_kwh) && d.emob_ladung_kwh
      ? (d.emob_ladung_pv_kwh! / d.emob_ladung_kwh) * 100 : null
    // „Ladung gesamt" ohne D2-Pendant → bleibt; Rest aus dem D2-Kanon (E-Auto).
    const kpis: KpiStripItem[] = [
      { title: 'Ladung gesamt', value: fmt(d.emob_ladung_kwh), unit: 'kWh', color: 'purple', icon: Plug },
      { ...EAUTO_KPI.pvAnteil, value: fmtCalc(pvAnteil, 0, '—'), unit: '%',
        subtitle: hat(d.emob_ladung_pv_kwh) ? `${fmt(d.emob_ladung_pv_kwh)} kWh PV` : undefined },
      { ...EAUTO_KPI.gefahren, value: fmt(d.emob_km), unit: 'km' },
      { ...EAUTO_KPI.verbrauch, value: fmtCalc(d.emob_verbrauch_100km, 1, '—'), unit: 'kWh/100km' },
    ]
    bloecke.push({
      id: 'k-emob', title: 'E-Mobilität', ...ident('e-auto'), defaultOpen: false,
      summary: `${fmt(d.emob_ladung_kwh)} kWh geladen · ${fmt(d.emob_km)} km${hat(d.emob_ersparnis_euro) ? ` · +${fmt(d.emob_ersparnis_euro, 2)} € vs. Verbrenner` : ''}`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  // ── Balkonkraftwerk ───────────────────────────────────────────────────────
  if (hat(d.bkw_erzeugung_kwh)) {
    const einsp = hat(d.bkw_erzeugung_kwh) && hat(d.bkw_eigenverbrauch_kwh)
      ? d.bkw_erzeugung_kwh! - d.bkw_eigenverbrauch_kwh! : null
    const evQuote = d.bkw_erzeugung_kwh && hat(d.bkw_eigenverbrauch_kwh)
      ? (d.bkw_eigenverbrauch_kwh! / d.bkw_erzeugung_kwh) * 100 : null
    // Einspeisung ohne D2-Pendant → bleibt; Erzeugung/Eigenverbrauch aus D2 (BKW).
    const kpis: KpiStripItem[] = [
      { ...BKW_KPI.erzeugung, value: fmt(d.bkw_erzeugung_kwh), unit: 'kWh' },
      { ...BKW_KPI.eigenverbrauch, value: fmt(d.bkw_eigenverbrauch_kwh), unit: 'kWh',
        subtitle: evQuote != null ? `${evQuote.toFixed(0)} % EV-Quote` : undefined },
      { title: 'Einspeisung', value: fmt(einsp), unit: 'kWh', color: 'green', icon: TrendingUp },
    ]
    bloecke.push({
      id: 'k-bkw', title: 'Balkonkraftwerk', ...ident('balkonkraftwerk'), defaultOpen: false,
      summary: `${fmt(d.bkw_erzeugung_kwh)} kWh erzeugt · in Gesamt-PV enthalten`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  // ── Sonstiges (Sonderfall #3c) ────────────────────────────────────────────
  // Heterogen (Erzeuger/Verbraucher) → keine sinnvolle Sammel-Summe. Statt einem
  // generischen „Sonstiges"-Block je Wirkrichtung EIN Block, benannt nach dem/den
  // Sonstiges-Gerät(en) (`investitionen_financials`, nur für die Namen), mit der
  // passenden Art-Variante. Energie bleibt das Wirkrichtungs-Aggregat (homogen
  // innerhalb der Art). Voller Per-Gerät-Deep-Dive → später Komponenten-Achse.
  // Mehrere Geräte → Namen kommasepariert (bewusste Vereinfachung im Teaser).
  const sonstigesNamen = (d.investitionen_financials ?? [])
    .filter((f) => f.typ === 'sonstiges')
    .map((f) => f.bezeichnung)
    .filter(Boolean)
  const sonstigesTitel = sonstigesNamen.length ? sonstigesNamen.join(', ') : 'Sonstiges'

  if (hat(d.sonstiges_erzeugung_kwh)) {
    const kpis: KpiStripItem[] = [
      { ...SONSTIGES_ERZEUGER_KPI.erzeugung, value: fmt(d.sonstiges_erzeugung_kwh), unit: 'kWh' },
    ]
    if (hat(d.sonstiges_eigenverbrauch_kwh)) kpis.push({ ...SONSTIGES_ERZEUGER_KPI.eigenverbrauch, value: fmt(d.sonstiges_eigenverbrauch_kwh), unit: 'kWh' })
    if (hat(d.sonstiges_einspeisung_kwh)) kpis.push({ title: 'Einspeisung', value: fmt(d.sonstiges_einspeisung_kwh), unit: 'kWh', color: 'green', icon: TrendingUp })
    bloecke.push({
      id: 'k-sonstiges-erzeuger', title: sonstigesTitel, ...ident('sonstiges'), defaultOpen: false,
      summary: `${fmt(d.sonstiges_erzeugung_kwh)} kWh erzeugt`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  if (hat(d.sonstiges_verbrauch_kwh)) {
    const bezugGesamt = (d.sonstiges_bezug_pv_kwh ?? 0) + (d.sonstiges_bezug_netz_kwh ?? 0)
    const pvAnteil = bezugGesamt > 0 ? ((d.sonstiges_bezug_pv_kwh ?? 0) / bezugGesamt) * 100 : null
    const kpis: KpiStripItem[] = [
      { ...SONSTIGES_VERBRAUCHER_KPI.verbrauch, value: fmt(d.sonstiges_verbrauch_kwh), unit: 'kWh' },
    ]
    if (pvAnteil != null) kpis.push({
      ...SONSTIGES_VERBRAUCHER_KPI.pvAnteil, value: fmtCalc(pvAnteil, 0, '—'), unit: '%',
      subtitle: `${fmt(d.sonstiges_bezug_pv_kwh)} kWh PV · ${fmt(d.sonstiges_bezug_netz_kwh)} kWh Netz`,
    })
    bloecke.push({
      id: 'k-sonstiges-verbraucher', title: sonstigesTitel, ...ident('sonstiges'), defaultOpen: false,
      summary: `${fmt(d.sonstiges_verbrauch_kwh)} kWh verbraucht`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  return bloecke
}
