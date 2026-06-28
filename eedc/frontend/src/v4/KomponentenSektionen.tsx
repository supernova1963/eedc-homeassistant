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
import { Parkbar, NOOP_PARK, type ParkApi } from '../components/park'
import {
  KOMPONENTEN_IDENTITAET, INVESTITION_TYP_ORDER, SONSTIGES_ERZEUGER_FARBE, ROLLEN_BG,
  SPEICHER_KPI, WP_KPI, EAUTO_KPI, BKW_KPI,
  SONSTIGES_ERZEUGER_KPI, SONSTIGES_VERBRAUCHER_KPI,
} from '../lib'
import type { AktuellerMonatResponse, SonstigesGeraet } from '../api/aktuellerMonat'

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

/** Slug für view-weit eindeutige parkIds (block-/gerät-präfixiert). */
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/gi, '-')

/** Ein parkbares Zusatz-Element unter dem KPI-Strip (Detailliste, Balken, Hinweis). */
interface SektionElement { id: string; titel: string; node: ReactNode }

/** Eine Komponenten-Sektion: KPI-Kacheln (je parkbar via parkId) + parkbare
 *  Zusatz-Elemente. Element-Park-Doktrin (Gernot 2026-06-27): JEDE Anzeige im
 *  Block ist einzeln parkbar (auch Detaillisten/Balken/Hinweise) — der Block
 *  selbst nicht; ist alles geparkt, blendet der Aufrufer den Block aus. */
function Sektion({ kpis, elemente }: { kpis: KpiStripItem[]; elemente?: SektionElement[] }) {
  return (
    <div className="space-y-3">
      {kpis.length > 0 && <KpiStrip kpis={kpis} />}
      {elemente?.map((e) => <Parkbar key={e.id} id={e.id} titel={e.titel}>{e.node}</Parkbar>)}
    </div>
  )
}

/** view-weit eindeutige parkId je Block-KPI (block-präfixiert gegen Kollisionen
 *  über mehrere Komponenten-Blöcke derselben Sicht). */
function mitParkId(prefix: string, kpis: KpiStripItem[]): KpiStripItem[] {
  return kpis.map((k) => ({ ...k, parkId: `kpi:${prefix}-${slug(k.title)}` }))
}

/** Block ausblenden, wenn ALLE seine Element-IDs (KPIs + Zusatz-Elemente) geparkt
 *  sind (Gernot 2026-06-27: leeren Block ausblenden). */
function alleGeparkt(park: ParkApi, kpis: KpiStripItem[], elemente: SektionElement[]): boolean {
  const ids = [...kpis.map((k) => k.parkId).filter((x): x is string => !!x), ...elemente.map((e) => e.id)]
  return ids.length > 0 && ids.every((id) => park.istGeparkt(id))
}

/** Sonder-Darstellung „Sonstiges": je Gerät eine beschriftete Werte-Gruppe
 *  (Gerätebezeichnung + KpiStrip) — je Gerät ein parkbares Element (Gernot
 *  2026-06-26/27). */
function GeraeteSektionen({ prefix, geraete, kpisVon }: {
  prefix: string; geraete: SonstigesGeraet[]; kpisVon: (g: SonstigesGeraet) => KpiStripItem[]
}) {
  return (
    <div className="space-y-4">
      {geraete.map((g) => (
        <Parkbar key={g.bezeichnung} id={`el:${prefix}-${slug(g.bezeichnung)}`} titel={g.bezeichnung}>
          <div className="space-y-2">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{g.bezeichnung}</div>
            <KpiStrip kpis={kpisVon(g)} />
          </div>
        </Parkbar>
      ))}
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

/** Liefert die Blöcke der aktiven Komponenten in kanonischer Reihenfolge.
 *  `periode` steuert nur die period-spezifischen Label/Texte (WP-Counter: Tag vs.
 *  Monat/Jahr); Default 'monat' lässt Cockpit/Monat unverändert. Cockpit/Tag ruft mit
 *  'tag' → gleiche Blöcke, tages-korrekte Beschriftung. Cockpit/Jahr ruft mit 'jahr'
 *  → wie 'monat' (Σ-Slot trägt die Jahressumme, Max/Tag = höchster Einzeltag des Jahres). */
export function baueKomponentenBloecke(d: AktuellerMonatResponse, park: ParkApi = NOOP_PARK, periode: 'monat' | 'tag' | 'jahr' = 'monat'): Block[] {
  const istTag = periode === 'tag'
  const bloecke: Block[] = []

  // Voraussetzungs-Hinweis bei „—" auf Tagesebene (Gernot 2026-06-24): Tooltip,
  // welcher Sensor/welche Zuordnung für den Tageswert fehlt. Nur auf Tag (istTag) —
  // auf Monat/Jahr bedeutet „—" fehlende Monatsdaten (anderer Kontext, eigener Pfad).
  const tagHinweis = (vorhanden: boolean, text: string): string | undefined =>
    istTag && !vorhanden ? text : undefined

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
    const speicherKpis = mitParkId('speicher', kpis)
    const speicherEls: SektionElement[] = []
    if (detail.length > 0) speicherEls.push({ id: 'el:speicher-detail', titel: 'Speicher-Details', node: <DetailListe rows={detail} /> })
    const speicherGeraete = geraeteNamen(d, 'speicher')
    if (speicherGeraete.length > 0) speicherEls.push({ id: 'el:speicher-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={speicherGeraete} /> })
    if (!alleGeparkt(park, speicherKpis, speicherEls)) bloecke.push({
      id: 'k-speicher', title: 'Speicher', ...ident('speicher'), defaultOpen: false,
      summary: `${fmt(d.speicher_ladung_kwh)} kWh geladen · ${fmtCalc(d.speicher_vollzyklen, 1, '—')} Zyklen · ${fmtCalc(d.speicher_wirkungsgrad_prozent, 0, '—')} % η`,
      render: () => <Sektion kpis={speicherKpis} elemente={speicherEls} />,
    })
  }

  // ── Wärmepumpe ──────────────────────────────────────────────────────────
  if (hat(d.wp_strom_kwh) || hat(d.wp_waerme_kwh)) {
    const jaz = hat(d.wp_waerme_kwh) && d.wp_strom_kwh ? d.wp_waerme_kwh! / d.wp_strom_kwh : null
    // Dieselben Felder wie Monat — auf Tag „—" wo der Tagessensor fehlt (Wärme/JAZ
    // nur mit Wärmemengenzähler; Ersparnis € folgt aus Wärme). Kein Weglassen
    // ([[feedback_sensor_ableitbar_nicht_weglassen]]).
    const wmz = 'Tageswert braucht einen Wärmemengenzähler am Gerät (Sensor zuordnen); sonst nur Monatswert.'
    const kpis: KpiStripItem[] = [
      { ...WP_KPI.jaz, value: fmtCalc(jaz, 2, '—'), formel: jaz != null ? 'JAZ = Wärme ÷ Strom' : undefined,
        hinweis: tagHinweis(jaz != null, 'Tages-JAZ = Wärme ÷ Strom — ' + wmz) },
      { ...WP_KPI.waerme, value: fmt(d.wp_waerme_kwh), unit: 'kWh', hinweis: tagHinweis(hat(d.wp_waerme_kwh), wmz) },
      { ...WP_KPI.strom, value: fmt(d.wp_strom_kwh), unit: 'kWh' },
      { ...WP_KPI.ersparnis, value: hat(d.wp_ersparnis_euro) ? `+${fmtCalc(d.wp_ersparnis_euro, 2)}` : '—', unit: '€',
        hinweis: tagHinweis(hat(d.wp_ersparnis_euro), 'Ersparnis folgt aus der Tages-Wärme — ' + wmz) },
    ]
    // #238 Counter (Verschleiß-/Auslegungs-Indikatoren). Monat: Σ Monat prominent,
    // Max/Tag im Untertitel. Tag: Tagessumme prominent, kein Max/Tag (period-korrekt,
    // Gernot 2026-06-23). Für Tag liefert der Aufrufer die Tages-Summe in
    // `wp_starts_summe_monat`/`wp_betriebsstunden_summe_monat` (period-neutraler Slot).
    const startsZeigen = istTag ? (d.wp_starts_summe_monat != null && d.wp_starts_summe_monat > 0)
                                : (d.wp_starts_max_tag != null && d.wp_starts_max_tag > 0)
    if (startsZeigen) kpis.push({
      title: 'Kompressor-Starts', color: 'gray', icon: Power,
      value: d.wp_starts_summe_monat != null ? d.wp_starts_summe_monat.toLocaleString('de-DE') : String(d.wp_starts_max_tag),
      formel: istTag ? 'Kompressor-Starts an diesem Tag' : 'Σ aller Tagessummen im Monat',
      subtitle: istTag ? undefined : `Max/Tag: ${d.wp_starts_max_tag}`,
    })
    const betriebZeigen = istTag ? (d.wp_betriebsstunden_summe_monat != null && d.wp_betriebsstunden_summe_monat > 0)
                                 : (d.wp_betriebsstunden_max_tag != null && d.wp_betriebsstunden_max_tag > 0)
    if (betriebZeigen) kpis.push({
      title: 'Betriebsstunden', color: 'gray', icon: Clock, unit: 'h',
      value: fmtCalc(d.wp_betriebsstunden_summe_monat ?? d.wp_betriebsstunden_max_tag, 1, '—'),
      formel: istTag ? 'Betriebsstunden an diesem Tag' : 'Σ aller Tages-Betriebsstunden im Monat',
      subtitle: istTag ? undefined : `Max/Tag: ${fmt(d.wp_betriebsstunden_max_tag, 1)} h`,
    })
    // Strom-Split Heizung/Warmwasser (#191, nur bei getrennter Strommessung).
    const wpDetail: DetailZeile[] = []
    if (hat(d.wp_strom_heizen_kwh)) wpDetail.push({ label: 'Stromverbrauch · davon Heizung', wert: `${fmt(d.wp_strom_heizen_kwh)} kWh` })
    if (hat(d.wp_strom_warmwasser_kwh)) wpDetail.push({ label: 'Stromverbrauch · davon Warmwasser', wert: `${fmt(d.wp_strom_warmwasser_kwh)} kWh` })
    const wpKpis = mitParkId('wp', kpis)
    // Wärme-Aufteilung Heizung/Warmwasser (VerteilungsBalken, B7) + Strom-Split (Detail)
    // + Geräte-Hinweis — je ein parkbares Element.
    const wpEls: SektionElement[] = []
    if (hat(d.wp_heizung_kwh) || hat(d.wp_warmwasser_kwh)) wpEls.push({
      id: 'el:wp-aufteilung', titel: 'Wärme-Aufteilung',
      node: <VerteilungsBalken segmente={[
        { label: 'Heizung', wert: d.wp_heizung_kwh, farbe: ROLLEN_BG.heizung },
        { label: 'Warmwasser', wert: d.wp_warmwasser_kwh, farbe: ROLLEN_BG.warmwasser },
      ]} />,
    })
    if (wpDetail.length > 0) wpEls.push({ id: 'el:wp-detail', titel: 'Strom-Aufteilung', node: <DetailListe rows={wpDetail} /> })
    const wpGeraete = geraeteNamen(d, 'waermepumpe')
    if (wpGeraete.length > 0) wpEls.push({ id: 'el:wp-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={wpGeraete} /> })
    if (!alleGeparkt(park, wpKpis, wpEls)) bloecke.push({
      id: 'k-waermepumpe', title: KOMPONENTEN_IDENTITAET['waermepumpe'].label, ...ident('waermepumpe'), defaultOpen: false,
      // Summary aus den vorhandenen Werten (Wärme/JAZ wenn da — Monat/Jahr/Tag-mit-WMZ;
      // sonst Strom — Tag ohne WMZ). Period-agnostisch, kein Sonderpfad.
      summary: hat(d.wp_waerme_kwh)
        ? `${jaz != null ? `JAZ ${fmtCalc(jaz, 2)} · ` : ''}${fmt(d.wp_waerme_kwh)} kWh Wärme${hat(d.wp_ersparnis_euro) ? ` · +${fmt(d.wp_ersparnis_euro, 0)} € vs. Gas` : ''}`
        : `${fmt(d.wp_strom_kwh)} kWh Strom${hat(d.wp_starts_summe_monat) ? ` · ${d.wp_starts_summe_monat!.toLocaleString('de-DE')} Starts` : ''}`,
      render: () => <Sektion kpis={wpKpis} elemente={wpEls} />,
    })
  }

  // ── E-Mobilität ─────────────────────────────────────────────────────────
  if (hat(d.emob_ladung_kwh) || hat(d.emob_km)) {
    const pvAnteil = hat(d.emob_ladung_pv_kwh) && d.emob_ladung_kwh
      ? (d.emob_ladung_pv_kwh! / d.emob_ladung_kwh) * 100 : null
    // Dieselben Felder wie Monat. PV-Anteil/Netz-Anteil sind auf Tag mit Sensor
    // erhebbar (tagDetail), km/Verbrauch/extern/V2H/Ersparnis haben keinen Tages-
    // Sensor → „—" wo nicht vorhanden, kein Weglassen ([[feedback_sensor_ableitbar_nicht_weglassen]]).
    const kpis: KpiStripItem[] = [
      { title: 'Ladung gesamt', value: fmt(d.emob_ladung_kwh), unit: 'kWh', color: 'purple', icon: Plug },
      { ...EAUTO_KPI.pvAnteil, value: fmtCalc(pvAnteil, 0, '—'), unit: '%',
        subtitle: hat(d.emob_ladung_pv_kwh) ? `${fmt(d.emob_ladung_pv_kwh)} kWh PV` : undefined,
        hinweis: tagHinweis(pvAnteil != null, 'PV-Ladesensor (ladung_pv) der Wallbox/dem Auto zuordnen.') },
      { ...EAUTO_KPI.gefahren, value: fmt(d.emob_km), unit: 'km',
        hinweis: tagHinweis(hat(d.emob_km), 'Kein Tages-Kilometersensor — Strecke nur im Monatsabschluss erfassbar.') },
      { ...EAUTO_KPI.verbrauch, value: fmtCalc(d.emob_verbrauch_100km, 1, '—'), unit: 'kWh/100km',
        hinweis: tagHinweis(d.emob_verbrauch_100km != null, 'Folgt aus der Tages-Strecke — kein Tages-Sensor.') },
    ]
    // Lade-Herkunft + V2H als Detailzeilen — Netz-Anteil tagesgenau (tagDetail),
    // extern/V2H nur monatlich (→ nur zeigen wenn vorhanden).
    const emobDetail: DetailZeile[] = []
    if (hat(d.emob_ladung_netz_kwh)) emobDetail.push({ label: 'Ladung · Netz-Anteil', wert: `${fmt(d.emob_ladung_netz_kwh)} kWh` })
    if (hat(d.emob_ladung_extern_kwh)) emobDetail.push({ label: 'Ladung · extern', wert: `${fmt(d.emob_ladung_extern_kwh)} kWh` })
    if (hat(d.emob_v2h_kwh)) emobDetail.push({ label: 'V2H-Rückspeisung', wert: `${fmt(d.emob_v2h_kwh)} kWh` })
    const emobKpis = mitParkId('emob', kpis)
    const emobEls: SektionElement[] = []
    if (emobDetail.length > 0) emobEls.push({ id: 'el:emob-detail', titel: 'Lade-Herkunft', node: <DetailListe rows={emobDetail} /> })
    const emobGeraete = geraeteNamen(d, 'e-auto', 'wallbox')
    if (emobGeraete.length > 0) emobEls.push({ id: 'el:emob-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={emobGeraete} /> })
    if (!alleGeparkt(park, emobKpis, emobEls)) bloecke.push({
      id: 'k-emob', title: 'E-Mobilität', ...ident('e-auto'), defaultOpen: false,
      summary: `${fmt(d.emob_ladung_kwh)} kWh geladen${hat(d.emob_km) ? ` · ${fmt(d.emob_km)} km` : ''}${hat(d.emob_ersparnis_euro) ? ` · +${fmt(d.emob_ersparnis_euro, 2)} € vs. Verbrenner` : ''}`,
      render: () => <Sektion kpis={emobKpis} elemente={emobEls} />,
    })
  }

  // ── Balkonkraftwerk ───────────────────────────────────────────────────────
  if (hat(d.bkw_erzeugung_kwh)) {
    const einsp = hat(d.bkw_erzeugung_kwh) && hat(d.bkw_eigenverbrauch_kwh)
      ? d.bkw_erzeugung_kwh! - d.bkw_eigenverbrauch_kwh! : null
    const evQuote = d.bkw_erzeugung_kwh && hat(d.bkw_eigenverbrauch_kwh)
      ? (d.bkw_eigenverbrauch_kwh! / d.bkw_erzeugung_kwh) * 100 : null
    // Erzeugung ist tagesgenau (Stundensumme). Eigenverbrauch/Einspeisung brauchen
    // den EV-Split — BKW hat selten einen eigenen Zähler → „—" wo nicht vorhanden
    // (korrekt, kein Weglassen; Gernot 2026-06-24, [[feedback_sensor_ableitbar_nicht_weglassen]]).
    const bkwHinweis = 'Eigenverbrauch/Einspeisung braucht einen eigenen BKW-Zähler (selten vorhanden).'
    const kpis: KpiStripItem[] = [
      { ...BKW_KPI.erzeugung, value: fmt(d.bkw_erzeugung_kwh), unit: 'kWh' },
      { ...BKW_KPI.eigenverbrauch, value: fmt(d.bkw_eigenverbrauch_kwh), unit: 'kWh',
        subtitle: evQuote != null ? `${fmt(evQuote)} % EV-Quote` : undefined,
        hinweis: tagHinweis(hat(d.bkw_eigenverbrauch_kwh), bkwHinweis) },
      { title: 'Einspeisung', value: fmt(einsp), unit: 'kWh', color: 'green', icon: TrendingUp,
        hinweis: tagHinweis(einsp != null, bkwHinweis) },
    ]
    const bkwKpis = mitParkId('bkw', kpis)
    const bkwEls: SektionElement[] = []
    const bkwGeraete = geraeteNamen(d, 'balkonkraftwerk')
    if (bkwGeraete.length > 0) bkwEls.push({ id: 'el:bkw-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={bkwGeraete} /> })
    if (!alleGeparkt(park, bkwKpis, bkwEls)) bloecke.push({
      id: 'k-bkw', title: 'Balkonkraftwerk', ...ident('balkonkraftwerk'), defaultOpen: false,
      summary: `${fmt(d.bkw_erzeugung_kwh)} kWh erzeugt · in Gesamt-PV enthalten`,
      render: () => <Sektion kpis={bkwKpis} elemente={bkwEls} />,
    })
  }

  // ── Sonstiges (Sonderfall #3c) ────────────────────────────────────────────
  // Heterogen (Erzeuger/Verbraucher) → keine sinnvolle Sammel-Summe. Statt einem
  // generischen „Sonstiges"-Block je Wirkrichtung EIN Block, benannt nach dem/den
  // Sonstiges-Gerät(en) (`investitionen_financials`, nur für die Namen), mit der
  // passenden Art-Variante. Energie bleibt das Wirkrichtungs-Aggregat (homogen
  // innerhalb der Art). Voller Per-Gerät-Deep-Dive → später Komponenten-Achse.
  // Sonder-Darstellung „Sonstiges" (Gernot 2026-06-26): ZWEI feste Blöcke
  // „Sonstiges – Erzeuger" / „Sonstiges – Verbraucher"; INNERHALB je Gerät eine
  // eigene Werte-Zeile mit Bezeichnung (echte Pro-Gerät-Werte, nicht die Summe).
  const sonstigesGeraete = d.sonstiges_geraete ?? []
  const erzeugerGeraete = sonstigesGeraete.filter((g) => g.kategorie === 'erzeuger')
  const verbraucherGeraete = sonstigesGeraete.filter((g) => g.kategorie === 'verbraucher')

  const erzeugerKpis = (g: SonstigesGeraet): KpiStripItem[] => {
    const ks: KpiStripItem[] = [{ ...SONSTIGES_ERZEUGER_KPI.erzeugung, value: fmt(g.erzeugung_kwh), unit: 'kWh' }]
    if (hat(g.eigenverbrauch_kwh)) ks.push({ ...SONSTIGES_ERZEUGER_KPI.eigenverbrauch, value: fmt(g.eigenverbrauch_kwh), unit: 'kWh' })
    if (hat(g.einspeisung_kwh)) ks.push({ title: 'Einspeisung', value: fmt(g.einspeisung_kwh), unit: 'kWh', color: 'green', icon: TrendingUp })
    return ks
  }
  const verbraucherKpis = (g: SonstigesGeraet): KpiStripItem[] => {
    const bezugGesamt = (g.bezug_pv_kwh ?? 0) + (g.bezug_netz_kwh ?? 0)
    const pvAnteil = bezugGesamt > 0 ? ((g.bezug_pv_kwh ?? 0) / bezugGesamt) * 100 : null
    const ks: KpiStripItem[] = [{ ...SONSTIGES_VERBRAUCHER_KPI.verbrauch, value: fmt(g.verbrauch_kwh), unit: 'kWh' }]
    if (pvAnteil != null) ks.push({
      ...SONSTIGES_VERBRAUCHER_KPI.pvAnteil, value: fmtCalc(pvAnteil, 0, '—'), unit: '%',
      subtitle: `${fmt(g.bezug_pv_kwh)} kWh PV · ${fmt(g.bezug_netz_kwh)} kWh Netz`,
    })
    return ks
  }

  // Sonstiges: je Gerät ein parkbares Element; Block aus wenn alle Geräte geparkt.
  const sonstigesAlleGeparkt = (prefix: string, gs: SonstigesGeraet[]) =>
    gs.length > 0 && gs.every((g) => park.istGeparkt(`el:${prefix}-${slug(g.bezeichnung)}`))

  if (erzeugerGeraete.length > 0 && !sonstigesAlleGeparkt('sonstiges-erzeuger', erzeugerGeraete)) {
    const summe = erzeugerGeraete.reduce((a, g) => a + (g.erzeugung_kwh ?? 0), 0)
    bloecke.push({
      // Eigene Identitätsfarbe (Lime) — sonstiger Erzeuger ist NICHT PV (Regel A).
      id: 'k-sonstiges-erzeuger', title: 'Sonstiges – Erzeuger', ...ident('sonstiges'), farbe: SONSTIGES_ERZEUGER_FARBE.text, defaultOpen: false,
      summary: `${fmt(summe)} kWh erzeugt`,
      render: () => <GeraeteSektionen prefix="sonstiges-erzeuger" geraete={erzeugerGeraete} kpisVon={erzeugerKpis} />,
    })
  }

  if (verbraucherGeraete.length > 0 && !sonstigesAlleGeparkt('sonstiges-verbraucher', verbraucherGeraete)) {
    const summe = verbraucherGeraete.reduce((a, g) => a + (g.verbrauch_kwh ?? 0), 0)
    bloecke.push({
      id: 'k-sonstiges-verbraucher', title: 'Sonstiges – Verbraucher', ...ident('sonstiges'), defaultOpen: false,
      summary: `${fmt(summe)} kWh verbraucht`,
      render: () => <GeraeteSektionen prefix="sonstiges-verbraucher" geraete={verbraucherGeraete} kpisVon={verbraucherKpis} />,
    })
  }

  // Default-Reihenfolge = Standard-Investitionstyp-Reihenfolge (`INVESTITION_TYP_ORDER`,
  // SoT) statt Bau-Reihenfolge — d. h. Speicher → Balkonkraftwerk → Wärmepumpe →
  // E-Mobilität → Sonstiges (BKW vor WP). Gilt einheitlich für Monat/Tag/Jahr.
  // Stabil → die zwei Sonstiges-Blöcke (Erzeuger vor Verbraucher) behalten ihre Folge.
  const ID_TYP: Record<string, string> = {
    'k-speicher': 'speicher', 'k-bkw': 'balkonkraftwerk', 'k-waermepumpe': 'waermepumpe',
    'k-emob': 'wallbox', 'k-sonstiges-erzeuger': 'sonstiges', 'k-sonstiges-verbraucher': 'sonstiges',
  }
  const ordnung = (b: Block) => {
    const i = (INVESTITION_TYP_ORDER as readonly string[]).indexOf(ID_TYP[b.id] ?? '')
    return i === -1 ? INVESTITION_TYP_ORDER.length : i
  }
  return [...bloecke].sort((a, b) => ordnung(a) - ordnung(b))
}
