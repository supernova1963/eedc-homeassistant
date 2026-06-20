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
import { Battery, TrendingUp, Plug, Power, Clock } from 'lucide-react'
import { fmtCalc } from '../components/ui'
import FormelTooltip from '../components/ui/FormelTooltip'
import QuelleBadge from '../components/ui/QuelleBadge'
import { KpiStrip, VerteilungsBalken, GeraeteHinweis, type Block, type KpiStripItem } from '../components/blocks'
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

/** Aktive Geräte-Namen eines oder mehrerer Typen (für den „aggregiert aus …"-Hinweis). */
function geraeteNamen(d: AktuellerMonatResponse, ...typen: string[]): string[] {
  return typen.flatMap((t) => d.komponenten_geraete?.[t] ?? [])
}

function Sektion({ kpis, extra, geraete }: { kpis: KpiStripItem[]; extra?: ReactNode; geraete?: string[] }) {
  return (
    <div className="space-y-3">
      <KpiStrip kpis={kpis} />
      {extra}
      {geraete && <GeraeteHinweis namen={geraete} />}
    </div>
  )
}

/** Detail-/Vergleichszeilen unter dem Status-Strip (periodensinnvolle IST-Werte,
 *  E-Gegencheck). Dieselbe dl-Bildsprache wie der Finanz-Teaser. */
type DetailZeile = { label: ReactNode; wert: ReactNode; akzent?: string }

function DetailListe({ rows }: { rows: DetailZeile[] }) {
  if (rows.length === 0) return null
  return (
    <dl className="text-sm space-y-1.5">
      {rows.map((r, i) => (
        <div key={i} className="flex justify-between gap-3">
          <dt className="text-gray-500 dark:text-gray-400">{r.label}</dt>
          <dd className={`tabular-nums ${r.akzent ?? 'text-gray-800 dark:text-gray-200'}`}>{r.wert}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Speicher-Wirkungsverluste in € (Opportunitätskosten des Roundtrip-Verlusts) —
 *  verhaltensgleich `MonatsabschlussView`. Null, wenn kein Verlust oder kein Preis. */
function speicherWirkungsverluste(d: AktuellerMonatResponse) {
  if (d.speicher_ladung_kwh == null || d.speicher_entladung_kwh == null) return null
  if (d.speicher_ladung_kwh <= d.speicher_entladung_kwh) return null
  if (d.einspeise_preis_cent == null && d.netzbezug_preis_cent == null) return null
  const verlust_kwh = d.speicher_ladung_kwh - d.speicher_entladung_kwh
  const netz_kwh = d.speicher_ladung_netz_kwh ?? 0
  const anteil_netz = d.speicher_ladung_kwh > 0 ? Math.min(1, netz_kwh / d.speicher_ladung_kwh) : 0
  const anteil_pv = 1 - anteil_netz
  const eins_p = d.einspeise_preis_cent ?? 0
  const bez_p = d.netzbezug_durchschnittspreis_cent ?? d.netzbezug_preis_cent ?? 0
  const euro = (verlust_kwh * anteil_pv * eins_p) / 100 + (verlust_kwh * anteil_netz * bez_p) / 100
  const teile: string[] = []
  if (anteil_pv > 0 && eins_p > 0) teile.push(`${fmt(verlust_kwh * anteil_pv, 1)} kWh × ${fmtCalc(eins_p, 2)} ct (entg. Einspeisung)`)
  if (anteil_netz > 0 && bez_p > 0) teile.push(`${fmt(verlust_kwh * anteil_netz, 1)} kWh × ${fmtCalc(bez_p, 2)} ct (Netzbezug)`)
  return { euro, teile }
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
    // Periodensinnvolle Detailzeilen (E-Gegencheck): Netzladung/Ladepreis/Bilanz/
    // Wirkungsverluste — alles als Tag/Monat/Jahr aggregierbar.
    const detail: DetailZeile[] = []
    if (hat(d.speicher_ladung_netz_kwh)) detail.push({ label: 'Netzladung (Arbitrage)', wert: `${fmt(d.speicher_ladung_netz_kwh)} kWh` })
    if (hat(d.speicher_effektiver_ladepreis_cent)) detail.push({
      label: 'Effektiver Ladepreis (Netz)',
      wert: (
        <span className="inline-flex items-center gap-2">
          {fmtCalc(d.speicher_effektiver_ladepreis_cent, 1)} ct/kWh
          {d.speicher_effektiver_ladepreis_quelle && <QuelleBadge quelle={d.speicher_effektiver_ladepreis_quelle} kind="ladepreis" />}
        </span>
      ),
    })
    if (hat(d.speicher_ladung_kwh) && hat(d.speicher_entladung_kwh)) {
      const bilanz = d.speicher_entladung_kwh! - d.speicher_ladung_kwh!
      detail.push({
        label: 'Bilanz (Entladung − Ladung)',
        wert: `${bilanz >= 0 ? '+' : ''}${fmt(bilanz, 1)} kWh`,
        akzent: bilanz >= 0 ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400',
      })
    }
    const wv = speicherWirkungsverluste(d)
    if (wv) detail.push({
      label: (
        <FormelTooltip
          formel="Verlust × (PV-Anteil × Einspeisepreis + Netz-Anteil × Bezugspreis)"
          berechnung={wv.teile.join(' + ')}
          ergebnis={`= ${fmtCalc(wv.euro, 2)} €`}
        >
          Wirkungsverluste (Opportunitätskosten)
        </FormelTooltip>
      ),
      wert: `−${fmtCalc(wv.euro, 2)} €`,
      akzent: 'text-amber-600 dark:text-amber-400',
    })
    bloecke.push({
      id: 'k-speicher', title: 'Speicher', ...ident('speicher'), defaultOpen: false,
      summary: `${fmt(d.speicher_ladung_kwh)} kWh geladen · ${fmtCalc(d.speicher_vollzyklen, 1, '—')} Zyklen · ${fmtCalc(d.speicher_wirkungsgrad_prozent, 0, '—')} % η`,
      render: () => <Sektion kpis={kpis} extra={<DetailListe rows={detail} />} geraete={geraeteNamen(d, 'speicher')} />,
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
    // #238 Counter (Verschleiß-/Auslegungs-Indikatoren): Σ Monat prominent, Max/Tag
    // im Untertitel — verhaltensgleich MonatsabschlussView. Period-aggregierbar (E).
    if (d.wp_starts_max_tag != null && d.wp_starts_max_tag > 0) kpis.push({
      title: 'Kompressor-Starts', color: 'gray', icon: Power,
      value: d.wp_starts_summe_monat != null ? d.wp_starts_summe_monat.toLocaleString('de-DE') : String(d.wp_starts_max_tag),
      formel: 'Σ aller Tagessummen im Monat', subtitle: `Max/Tag: ${d.wp_starts_max_tag}`,
    })
    if (d.wp_betriebsstunden_max_tag != null && d.wp_betriebsstunden_max_tag > 0) kpis.push({
      title: 'Betriebsstunden', color: 'gray', icon: Clock, unit: 'h',
      value: fmtCalc(d.wp_betriebsstunden_summe_monat ?? d.wp_betriebsstunden_max_tag, 1, '—'),
      formel: 'Σ aller Tages-Betriebsstunden im Monat', subtitle: `Max/Tag: ${fmt(d.wp_betriebsstunden_max_tag, 1)} h`,
    })
    // Strom-Split Heizung/Warmwasser (#191, nur bei getrennter Strommessung).
    const wpDetail: DetailZeile[] = []
    if (hat(d.wp_strom_heizen_kwh)) wpDetail.push({ label: 'Stromverbrauch · davon Heizung', wert: `${fmt(d.wp_strom_heizen_kwh)} kWh` })
    if (hat(d.wp_strom_warmwasser_kwh)) wpDetail.push({ label: 'Stromverbrauch · davon Warmwasser', wert: `${fmt(d.wp_strom_warmwasser_kwh)} kWh` })
    bloecke.push({
      id: 'k-waermepumpe', title: KOMPONENTEN_IDENTITAET['waermepumpe'].label, ...ident('waermepumpe'), defaultOpen: false,
      summary: `${jaz != null ? `JAZ ${fmtCalc(jaz, 2)} · ` : ''}${fmt(d.wp_waerme_kwh)} kWh Wärme${hat(d.wp_ersparnis_euro) ? ` · +${fmt(d.wp_ersparnis_euro, 0)} € vs. Gas` : ''}`,
      // Wärme-Aufteilung Heizung/Warmwasser als VerteilungsBalken (B7-Revision), darunter
      // der Strom-Split als Detailzeilen (E-Gegencheck).
      render: () => <Sektion kpis={kpis} extra={
        <>
          <VerteilungsBalken segmente={[
            { label: 'Heizung', wert: d.wp_heizung_kwh, farbe: 'bg-red-500' },
            { label: 'Warmwasser', wert: d.wp_warmwasser_kwh, farbe: 'bg-blue-500' },
          ]} />
          <DetailListe rows={wpDetail} />
        </>
      } geraete={geraeteNamen(d, 'waermepumpe')} />,
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
    // Lade-Herkunft + V2H als Detailzeilen (E-Gegencheck) — period-aggregierbar.
    const emobDetail: DetailZeile[] = []
    if (hat(d.emob_ladung_netz_kwh)) emobDetail.push({ label: 'Ladung · Netz-Anteil', wert: `${fmt(d.emob_ladung_netz_kwh)} kWh` })
    if (hat(d.emob_ladung_extern_kwh)) emobDetail.push({ label: 'Ladung · extern', wert: `${fmt(d.emob_ladung_extern_kwh)} kWh` })
    if (hat(d.emob_v2h_kwh)) emobDetail.push({ label: 'V2H-Rückspeisung', wert: `${fmt(d.emob_v2h_kwh)} kWh` })
    bloecke.push({
      id: 'k-emob', title: 'E-Mobilität', ...ident('e-auto'), defaultOpen: false,
      summary: `${fmt(d.emob_ladung_kwh)} kWh geladen · ${fmt(d.emob_km)} km${hat(d.emob_ersparnis_euro) ? ` · +${fmt(d.emob_ersparnis_euro, 2)} € vs. Verbrenner` : ''}`,
      render: () => <Sektion kpis={kpis} extra={<DetailListe rows={emobDetail} />} geraete={geraeteNamen(d, 'e-auto', 'wallbox')} />,
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
      render: () => <Sektion kpis={kpis} geraete={geraeteNamen(d, 'balkonkraftwerk')} />,
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
