/**
 * KomponentenSektionen — Komponenten-Detailblöcke der Cockpit/Monat-Sicht
 * (IA v4 E3 Slice 2d, B6 + B7).
 *
 * Pro AKTIVER Komponente (Speicher/WP/E-Mob/BKW/Sonstiges) ein eingeklappter
 * Block mit Status-KPI-Strip (D2-Kanon) + Summary-Zeile + Komponenten-Identitäts-
 * Farbe. Schlank wie in der IA-v4-Vorschau (`KOMP_STATUS`/`COCKPIT_DETAIL`), die
 * Kennzahlen aber verhaltensgleich zum Donor `MonatsabschlussView`. Wärmepumpe
 * trägt zusätzlich einen Aufteilungs-Donut Heizung/Warmwasser (B7).
 *
 * Quelle: `AktuellerMonatResponse` (alle Komponenten-Felder bereits vorhanden).
 * Aktiv-Gating: ein Block erscheint nur, wenn die Komponente im Monat Daten hat.
 */
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import { Battery, Flame, Car, Sun, Wrench, Activity, Zap, TrendingUp, Euro, Home, Plug, Snowflake } from 'lucide-react'
import { fmtCalc, ChartTooltip } from '../components/ui'
import { KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { EXTRA_SERIEN_FARBEN } from '../lib'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')
const hat = (v: number | null | undefined) => v != null

/** Aufteilungs-Donut (B7) — z. B. WP Heizung/Warmwasser, Lade-Mix. */
export function AufteilungDonut({ daten }: { daten: { name: string; value: number }[] }) {
  const gesamt = daten.reduce((s, d) => s + d.value, 0)
  if (gesamt <= 0) return null
  return (
    <div className="h-44">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={daten} dataKey="value" nameKey="name" innerRadius={40} outerRadius={64} paddingAngle={2}>
            {daten.map((_, i) => <Cell key={i} fill={EXTRA_SERIEN_FARBEN[i % EXTRA_SERIEN_FARBEN.length]} />)}
          </Pie>
          <Tooltip content={<ChartTooltip unit=" kWh" decimals={0} />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

function Sektion({ kpis, donut }: { kpis: KpiStripItem[]; donut?: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <KpiStrip kpis={kpis} />
      {donut}
    </div>
  )
}

/** Liefert die Blöcke der aktiven Komponenten in kanonischer Reihenfolge. */
export function baueKomponentenBloecke(d: AktuellerMonatResponse): Block[] {
  const bloecke: Block[] = []

  // ── Speicher ────────────────────────────────────────────────────────────
  if (hat(d.speicher_ladung_kwh) || hat(d.speicher_entladung_kwh) || hat(d.speicher_kapazitaet_kwh)) {
    const kpis: KpiStripItem[] = [
      { title: 'Ladung', value: fmt(d.speicher_ladung_kwh), unit: 'kWh', color: 'blue', icon: Battery },
      { title: 'Entladung', value: fmt(d.speicher_entladung_kwh), unit: 'kWh', color: 'green', icon: Battery },
      { title: 'Effizienz η', value: fmtCalc(d.speicher_wirkungsgrad_prozent, 1, '—'), unit: '%', color: 'cyan', icon: Activity },
      { title: 'Vollzyklen', value: fmtCalc(d.speicher_vollzyklen, 2, '—'), color: 'blue', icon: TrendingUp,
        subtitle: hat(d.speicher_kapazitaet_kwh) ? `Kapazität ${fmt(d.speicher_kapazitaet_kwh)} kWh` : undefined },
    ]
    bloecke.push({
      id: 'k-speicher', title: 'Speicher', icon: Battery, farbe: 'text-green-500', defaultOpen: false,
      summary: `${fmt(d.speicher_ladung_kwh)} kWh geladen · ${fmtCalc(d.speicher_vollzyklen, 1, '—')} Zyklen · ${fmtCalc(d.speicher_wirkungsgrad_prozent, 0, '—')} % η`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  // ── Wärmepumpe ──────────────────────────────────────────────────────────
  if (hat(d.wp_strom_kwh) || hat(d.wp_waerme_kwh)) {
    const jaz = hat(d.wp_waerme_kwh) && d.wp_strom_kwh ? d.wp_waerme_kwh! / d.wp_strom_kwh : null
    const kpis: KpiStripItem[] = [
      { title: 'JAZ', value: fmtCalc(jaz, 2, '—'), color: 'green', icon: TrendingUp, formel: 'JAZ = Wärme ÷ Strom' },
      { title: 'Wärme erzeugt', value: fmt(d.wp_waerme_kwh), unit: 'kWh', color: 'orange', icon: Flame },
      { title: 'Strom verbraucht', value: fmt(d.wp_strom_kwh), unit: 'kWh', color: 'yellow', icon: Zap },
      { title: 'Ersparnis vs. Gas', value: hat(d.wp_ersparnis_euro) ? `+${fmtCalc(d.wp_ersparnis_euro, 2)}` : '—', unit: '€', color: 'green', icon: Euro },
    ]
    const donutDaten = [
      { name: 'Heizung', value: d.wp_heizung_kwh ?? 0 },
      { name: 'Warmwasser', value: d.wp_warmwasser_kwh ?? 0 },
    ]
    const hatSplit = (d.wp_heizung_kwh ?? 0) + (d.wp_warmwasser_kwh ?? 0) > 0
    bloecke.push({
      id: 'k-waermepumpe', title: 'Wärmepumpe', icon: Flame, farbe: 'text-orange-500', defaultOpen: false,
      summary: `${jaz != null ? `JAZ ${fmtCalc(jaz, 2)} · ` : ''}${fmt(d.wp_waerme_kwh)} kWh Wärme${hat(d.wp_ersparnis_euro) ? ` · +${fmt(d.wp_ersparnis_euro, 0)} € vs. Gas` : ''}`,
      render: () => <Sektion kpis={kpis} donut={hatSplit ? <AufteilungDonut daten={donutDaten} /> : undefined} />,
    })
  }

  // ── E-Mobilität ─────────────────────────────────────────────────────────
  if (hat(d.emob_ladung_kwh) || hat(d.emob_km)) {
    const pvAnteil = hat(d.emob_ladung_pv_kwh) && d.emob_ladung_kwh
      ? (d.emob_ladung_pv_kwh! / d.emob_ladung_kwh) * 100 : null
    const kpis: KpiStripItem[] = [
      { title: 'Ladung gesamt', value: fmt(d.emob_ladung_kwh), unit: 'kWh', color: 'purple', icon: Plug },
      { title: 'PV-Anteil', value: fmtCalc(pvAnteil, 0, '—'), unit: '%', color: 'green', icon: Sun,
        subtitle: hat(d.emob_ladung_pv_kwh) ? `${fmt(d.emob_ladung_pv_kwh)} kWh PV` : undefined },
      { title: 'Kilometer', value: fmt(d.emob_km), unit: 'km', color: 'blue', icon: Car },
      { title: 'Verbrauch', value: fmtCalc(d.emob_verbrauch_100km, 1, '—'), unit: 'kWh/100km', color: 'yellow', icon: Zap },
    ]
    bloecke.push({
      id: 'k-emob', title: 'E-Mobilität', icon: Car, farbe: 'text-purple-500', defaultOpen: false,
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
    const kpis: KpiStripItem[] = [
      { title: 'Erzeugung', value: fmt(d.bkw_erzeugung_kwh), unit: 'kWh', color: 'yellow', icon: Sun },
      { title: 'Eigenverbrauch', value: fmt(d.bkw_eigenverbrauch_kwh), unit: 'kWh', color: 'purple', icon: Home,
        subtitle: evQuote != null ? `${evQuote.toFixed(0)} % EV-Quote` : undefined },
      { title: 'Einspeisung', value: fmt(einsp), unit: 'kWh', color: 'green', icon: TrendingUp },
    ]
    bloecke.push({
      id: 'k-bkw', title: 'Balkonkraftwerk', icon: Sun, farbe: 'text-yellow-400', defaultOpen: false,
      summary: `${fmt(d.bkw_erzeugung_kwh)} kWh erzeugt${evQuote != null ? ` · ${evQuote.toFixed(0)} % EV` : ''}`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  // ── Sonstiges ─────────────────────────────────────────────────────────────
  if (hat(d.sonstiges_erzeugung_kwh) || hat(d.sonstiges_verbrauch_kwh)) {
    const kpis: KpiStripItem[] = []
    if (hat(d.sonstiges_erzeugung_kwh)) kpis.push({ title: 'Erzeugung', value: fmt(d.sonstiges_erzeugung_kwh), unit: 'kWh', color: 'green', icon: Zap })
    if (hat(d.sonstiges_eigenverbrauch_kwh)) kpis.push({ title: 'Eigenverbrauch', value: fmt(d.sonstiges_eigenverbrauch_kwh), unit: 'kWh', color: 'purple', icon: Home })
    if (hat(d.sonstiges_einspeisung_kwh)) kpis.push({ title: 'Einspeisung', value: fmt(d.sonstiges_einspeisung_kwh), unit: 'kWh', color: 'green', icon: TrendingUp })
    if (hat(d.sonstiges_verbrauch_kwh)) kpis.push({ title: 'Verbrauch', value: fmt(d.sonstiges_verbrauch_kwh), unit: 'kWh', color: 'red', icon: Snowflake })
    bloecke.push({
      id: 'k-sonstiges', title: 'Sonstiges', icon: Wrench, farbe: 'text-gray-500', defaultOpen: false,
      summary: hat(d.sonstiges_erzeugung_kwh) ? `${fmt(d.sonstiges_erzeugung_kwh)} kWh erzeugt` : `${fmt(d.sonstiges_verbrauch_kwh)} kWh verbraucht`,
      render: () => <Sektion kpis={kpis} />,
    })
  }

  return bloecke
}
