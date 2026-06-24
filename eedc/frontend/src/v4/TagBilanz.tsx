/**
 * TagBilanz — KPI-Strip-Bauer + Energie-Bilanz-Block der Cockpit/Tag-Sicht
 * (IA-V4 Muster A, Tag = Variante von Monat mit Tages-Granularität).
 *
 * Spiegelt {@link MonatBilanz} 1:1 auf Tagesebene:
 * - {@link baueTagKpis}: Energie-Strip (5 Energie-Cards + Netto-Ertrag €),
 *   Vortag in der Zweitzeile.
 * - {@link TagBilanz}: IST / Vortag / Ø-gleicher-Wochentag-Vergleichstabelle +
 *   Tages-Spitzen (Peak-PV / PR / Temperatur) + PV-Verteilungs-Balken.
 *
 * Quelle = der Tages-Werte-SoT `getTageWerte` (`TagWerte`), identisch zum Monat
 * (KPI/Bilanz aus dem Tages-SoT, NICHT aus Stunden summiert). Vergleichs-Chips
 * (Delta/VglChip) aus `MonatBilanz` wiederverwendet (eine SoT-Komponente).
 * Ø-Wochentag = client-seitiges Mittel vorab-aggregierter Tageswerte (wie Monat
 * `glMonStats`), keine Roh-Daten-Aggregation.
 */
import { fmtCalc } from '../components/ui'
import FormelTooltip from '../components/ui/FormelTooltip'
import { VerteilungsBalken } from '../components/blocks'
import { DATENROLLE, AMPEL_SKALA } from '../lib'
import { Delta, VglChip, type GleicheMonatStats } from './MonatBilanz'
import { Sun, Activity, Zap, ArrowUpFromLine, Plug, Euro } from 'lucide-react'
import type { KpiStripItem } from '../components/blocks'
import type { TagWerte } from '../api/energie_profil'

/** Ø-Werte über die gleichen Wochentage im Fenster (Tag-Pendant zu GleicheMonatStats). */
export type GleicheWochentagStats = GleicheMonatStats

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

/** Energie-Strip: 5 Energie + Netto-Ertrag €. Vortag in der Zweitzeile.
 *  `sollPvKwh` (OM-Tagesprognose × eedc-Lernfaktor, optional) → SOLL-Annotation am
 *  PV-KPI wie im Monat. */
export function baueTagKpis(t: TagWerte, vt: TagWerte | null, sollPvKwh?: number | null): KpiStripItem[] {
  const sollTxt = sollPvKwh != null && sollPvKwh > 0
    ? `SOLL ${fmt(sollPvKwh)} kWh · ${Math.round((t.erzeugung / sollPvKwh) * 100)} %` : null
  const spezTxt = t.spezErtrag != null ? `${fmt(t.spezErtrag, 2)} kWh/kWp` : null
  const vtTxt = vt ? `VT: ${fmt(vt.erzeugung)} kWh` : null
  return [
    {
      title: 'PV-Erzeugung', value: fmt(t.erzeugung), unit: 'kWh', color: 'yellow', icon: Sun,
      subtitle: [sollTxt, spezTxt, vtTxt].filter(Boolean).join(' · ') || undefined,
    },
    {
      title: 'Autarkie', value: fmt(t.autarkie), unit: '%', color: 'green', icon: Activity,
      subtitle: vt ? `VT: ${fmt(vt.autarkie)} %` : undefined,
      formel: 'Eigenverbrauch ÷ Gesamtverbrauch × 100',
      berechnung: t.gesamtverbrauch > 0 ? `${fmt(t.eigenverbrauch)} ÷ ${fmt(t.gesamtverbrauch)} kWh` : undefined,
      ergebnis: t.autarkie != null ? `= ${fmtCalc(t.autarkie, 1)} %` : undefined,
    },
    {
      title: 'Eigenverbrauch', value: fmt(t.eigenverbrauch), unit: 'kWh', color: 'purple', icon: Zap,
      subtitle: `EV-Quote ${fmt(t.evQuote)} %${vt ? ` · VT: ${fmt(vt.eigenverbrauch)} kWh` : ''}`,
    },
    {
      title: 'Einspeisung', value: fmt(t.einspeisung), unit: 'kWh', color: 'green', icon: ArrowUpFromLine,
      subtitle: vt ? `VT: ${fmt(vt.einspeisung)} kWh` : undefined,
    },
    {
      title: 'Netzbezug', value: fmt(t.netzbezug), unit: 'kWh', color: 'red', icon: Plug,
      subtitle: vt ? `VT: ${fmt(vt.netzbezug)} kWh` : undefined,
    },
    {
      title: 'Netto-Ertrag', value: fmtCalc(t.netto_ertrag, 2, '—'), unit: '€', color: 'blue', icon: Euro,
      subtitle: 'Einspeise-Erlös + EV-Ersparnis',
      formel: 'Einspeise-Erlös + Eigenverbrauchs-Ersparnis',
      berechnung: `${fmtCalc(t.einspeise_erloes, 2)} + ${fmtCalc(t.ev_ersparnis, 2)} €`,
      ergebnis: `= ${fmtCalc(t.netto_ertrag, 2)} €`,
    },
  ]
}

interface BilanzRow {
  label: string
  ist: number | null | undefined
  vt: number | null | undefined
  wt: number | null
  unit: string
  inv?: boolean
  besserVt?: boolean
  besserWt?: boolean
}

export function TagBilanz({
  t, vt, wtStats, wochentagName,
}: {
  t: TagWerte
  vt: TagWerte | null
  wtStats: GleicheWochentagStats | null
  wochentagName: string
}) {
  // Eigenverbrauch-Färbung folgt der Autarkie-Richtung (EV ÷ Gesamtverbrauch), nicht
  // dem absoluten EV-Wert (analog Monat #337).
  const evBesser = (vglAutarkie: number | null | undefined): boolean | undefined =>
    t.autarkie != null && vglAutarkie != null ? t.autarkie >= vglAutarkie : undefined
  const rows: BilanzRow[] = [
    { label: 'PV-Erzeugung',    ist: t.erzeugung,      vt: vt?.erzeugung,      wt: wtStats?.pv ?? null,       unit: 'kWh' },
    { label: 'Eigenverbrauch',  ist: t.eigenverbrauch, vt: vt?.eigenverbrauch, wt: wtStats?.ev ?? null,       unit: 'kWh',
      besserVt: evBesser(vt?.autarkie), besserWt: evBesser(wtStats?.autarkie) },
    { label: 'Direktverbrauch', ist: t.direktverbrauch, vt: vt?.direktverbrauch, wt: wtStats?.direkt ?? null, unit: 'kWh' },
    { label: 'Einspeisung',     ist: t.einspeisung,    vt: vt?.einspeisung,    wt: wtStats?.einsp ?? null,    unit: 'kWh' },
    { label: 'Netzbezug',       ist: t.netzbezug,      vt: vt?.netzbezug,      wt: wtStats?.netz ?? null,     unit: 'kWh', inv: true },
    { label: 'Gesamtverbrauch', ist: t.gesamtverbrauch, vt: vt?.gesamtverbrauch, wt: wtStats?.gesamt ?? null, unit: 'kWh', inv: true },
    { label: 'Autarkie',        ist: t.autarkie,       vt: vt?.autarkie,       wt: wtStats?.autarkie ?? null, unit: '%'   },
  ]

  const dash = <span className="text-gray-300 dark:text-gray-600">—</span>
  const dec = (row: BilanzRow) => (row.unit === '%' ? 1 : 0)
  const wtLabel = `Ø ${wochentagName}`

  const vglZellen = (val: number | null | undefined, row: BilanzRow, besser?: boolean) => (
    <>
      <td className="py-1.5 pl-3 text-right tabular-nums text-gray-400 dark:text-gray-500 hidden sm:table-cell">
        {val != null ? fmt(val, dec(row)) : dash}
      </td>
      <td className="py-1.5 pr-1 text-right tabular-nums">
        {val != null ? <Delta a={row.ist} b={val} inv={row.inv} besser={besser} /> : dash}
      </td>
    </>
  )

  // PR-Ampel = Tages-Pendant zum Monats-SOLL/IST: PR = Ertrag ÷ (gemessene
  // Einstrahlung × kWp) = IST gegen das physikalische Optimum bei der heutigen
  // Sonne. Selbsttragend (Einstrahlung liegt im Tageswert vor) → kein per-Tag-
  // PVGIS-SOLL/Backfill nötig (Gernot-Entscheid 2026-06-24). Ampelfarbe aus SoT.
  const prPct = t.performance_ratio != null ? t.performance_ratio * 100 : null
  const prColor = prPct == null ? undefined
    : prPct >= 80 ? AMPEL_SKALA.gut
    : prPct >= 70 ? AMPEL_SKALA.maessig
    : prPct >= 60 ? AMPEL_SKALA.hoch
    : AMPEL_SKALA.kritisch
  const prWort = prPct == null ? null
    : prPct >= 80 ? 'sehr gut'
    : prPct >= 70 ? 'solide'
    : prPct >= 60 ? 'mäßig'
    : 'auffällig niedrig'
  const strahlungKwh = t.strahlung_summe_wh_m2 != null ? t.strahlung_summe_wh_m2 / 1000 : null

  // Tages-Spitzen (Tag-native) — Peak PV + Temperatur (PR steht prominent oben).
  const spitzen: { label: string; value: string }[] = []
  if (t.peak_pv_kw != null) spitzen.push({ label: 'Peak PV', value: `${fmtCalc(t.peak_pv_kw, 2)} kW` })
  if (t.temperatur_min_c != null && t.temperatur_max_c != null)
    spitzen.push({ label: 'Temperatur', value: `${fmtCalc(t.temperatur_min_c, 1)} / ${fmtCalc(t.temperatur_max_c, 1)} °C` })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* IST / Vortag / Ø-Wochentag-Vergleich */}
      <div className="lg:col-span-2">
        {/* Mobil (< sm): gestapelte Karten + Vergleichs-Chips. */}
        <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700/50">
          {rows.map((row) => (
            <div key={row.label} className="py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-gray-600 dark:text-gray-400 truncate">{row.label}</span>
                <span className="shrink-0 text-sm font-semibold tabular-nums text-gray-900 dark:text-white">
                  {fmt(row.ist, dec(row))} <span className="text-xs font-normal text-gray-500 dark:text-gray-400">{row.unit}</span>
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                <VglChip prefix="VT" lang="Vortag" ist={row.ist} val={row.vt} unit={row.unit} dec={dec(row)} inv={row.inv} besser={row.besserVt} />
                {wtStats && <VglChip prefix={wtLabel} lang={wtLabel} ist={row.ist} val={row.wt} unit={row.unit} dec={dec(row)} inv={row.inv} besser={row.besserWt} />}
              </div>
            </div>
          ))}
        </div>

        {/* Desktop (≥ sm): aligned Tabelle. */}
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
                <th className="text-left pb-1.5 font-medium"><span className="sr-only">Kennzahl</span></th>
                <th colSpan={2} className="text-center pb-1.5 font-medium">IST</th>
                <th colSpan={2} className="text-center pb-1.5 font-medium">Vortag</th>
                {wtStats && <th colSpan={2} className="text-center pb-1.5 font-medium">{wtLabel}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className="border-b border-gray-100 dark:border-gray-700/50 last:border-0">
                  <td className="py-1.5 text-gray-600 dark:text-gray-400">{row.label}</td>
                  <td className="py-1.5 pl-3 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                    {fmt(row.ist, dec(row))}
                  </td>
                  <td className="py-1.5 pr-1 text-left text-gray-500 dark:text-gray-400">{row.unit}</td>
                  {vglZellen(row.vt, row, row.besserVt)}
                  {wtStats && vglZellen(row.wt, row, row.besserWt)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {wtStats && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
            Ø aus {wtStats.count} {wochentagName}{wtStats.count !== 1 ? '-Tagen' : '-Tag'} (letzte 90 Tage)
          </p>
        )}
      </div>

      {/* PR-Ampel (prominent, Tages-Ersatz für Monats-SOLL/IST) + Spitzen + PV-Verteilung */}
      <div className="space-y-4">
        <div>
          <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
            <FormelTooltip
              formel="Ertrag ÷ (Einstrahlung × kWp)"
              berechnung={strahlungKwh != null ? `bei ${fmt(strahlungKwh, 1)} kWh/m² Einstrahlung` : undefined}
              ergebnis={prPct != null ? `= ${fmt(prPct, 0)} %` : undefined}
            >
              Performance Ratio
            </FormelTooltip>
          </p>
          {prPct != null ? (
            <>
              <div className="flex justify-end">
                <span className="text-4xl font-bold" style={{ color: prColor }}>{fmt(prPct, 0)} %</span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 text-right">
                {prWort}{strahlungKwh != null ? ` · bei ${fmt(strahlungKwh, 1)} kWh/m²` : ''}
              </p>
            </>
          ) : (
            <p className="text-xs text-gray-400 dark:text-gray-500">Keine Einstrahlungsdaten für diesen Tag — PR nicht berechenbar.</p>
          )}
        </div>

        {spitzen.length > 0 && (
          <dl className="space-y-1.5">
            {spitzen.map((s) => (
              <div key={s.label} className="flex justify-between text-sm">
                <dt className="text-gray-500 dark:text-gray-400">{s.label}</dt>
                <dd className="tabular-nums text-gray-800 dark:text-gray-200">{s.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {t.eigenverbrauch != null && t.einspeisung != null && t.erzeugung > 0 && (
          <VerteilungsBalken
            titel="PV-Verteilung"
            segmente={[
              { label: 'Eigenverbr.', wert: t.eigenverbrauch, farbe: DATENROLLE.eigenverbrauch.bg },
              { label: 'Einspeisung', wert: t.einspeisung, farbe: DATENROLLE.einspeisung.bg },
            ]}
          />
        )}
      </div>
    </div>
  )
}
