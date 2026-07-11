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
import { Table, TableHead, TableBody } from '../components/ui/Table'
import { ZELLE, KOPF_ZELLE } from '../components/ui/tabelleMasse'
import { VerteilungsBalken } from '../components/blocks'
import { Parkbar } from '../components/park'
import { DATENROLLE, AMPEL_TEXT_CLASS } from '../lib'
import { BilanzKachel } from '../components/blocks/GrundlastSollIstKachel'
import { Delta, VglChip, type GleicheMonatStats } from './MonatBilanz'
// R3b S7/A5: Datenrollen-Icons aus der SoT-Map (eine Datenrolle = ein Icon).
import { DATENROLLEN_ICONS } from '../lib/komponentenStyle'
import type { KpiStripItem } from '../components/blocks'
import type { TagWerte } from '../api/energie_profil'

/** Ø-Werte über die gleichen Wochentage im Fenster (Tag-Pendant zu GleicheMonatStats). */
export type GleicheWochentagStats = GleicheMonatStats

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

/** Energie-Strip: 5 Energie + Netto-Ertrag €. Vortag in der Zweitzeile.
 *  `sollPvKwh` (OM-Tagesprognose × eedc-Lernfaktor, optional) → SOLL-Annotation am
 *  PV-KPI wie im Monat. `netzladung` (tagDetail, optional) → Kosten-Kacheln R15-1. */
export function baueTagKpis(
  t: TagWerte,
  vt: TagWerte | null,
  sollPvKwh?: number | null,
  netzladung?: { kwh?: number | null; preis_cent?: number | null },
): KpiStripItem[] {
  const sollTxt = sollPvKwh != null && sollPvKwh > 0
    ? `SOLL ${fmt(sollPvKwh)} kWh · ${fmt((t.erzeugung / sollPvKwh) * 100)} %` : null
  const spezTxt = t.spezErtrag != null ? `${fmt(t.spezErtrag, 2)} kWh/kWp` : null
  const vtTxt = vt ? `VT: ${fmt(vt.erzeugung)} kWh` : null

  // R15-1: Kosten-Kacheln — nur wenn die Tagesdaten es hergeben. Netzladung-
  // Kosten brauchen den TEP-Tages-Ladepreis (#264); der Tages-Ø-Bezugspreis
  // ist implizit exakt (Backend: kosten = netzbezug × Monats-Finanzzeilen-Preis).
  const kostenKpis: KpiStripItem[] = []
  if (netzladung?.kwh != null && netzladung.kwh > 0 && netzladung.preis_cent != null) {
    const kosten = (netzladung.kwh * netzladung.preis_cent) / 100
    kostenKpis.push({
      title: 'Batterieladung Netz',
      value: fmtCalc(kosten, 2, '—'), unit: '€', color: 'red', icon: DATENROLLEN_ICONS.netzladungKosten,
      subtitle: `${fmt(netzladung.kwh, 1)} kWh · Ø ${fmtCalc(netzladung.preis_cent, 1)} ct/kWh`,
      formel: 'Netzladung × Ø-Ladepreis (Tag)',
      berechnung: `${fmt(netzladung.kwh, 1)} kWh × ${fmtCalc(netzladung.preis_cent, 1)} ct/kWh`,
      ergebnis: `= ${fmtCalc(kosten, 2)} €`,
    })
  }
  if (t.netzbezug > 0 && t.netzbezug_kosten != null) {
    kostenKpis.push({
      title: 'Durchschnittspreis Netz',
      value: fmtCalc((t.netzbezug_kosten / t.netzbezug) * 100, 1, '—'), unit: 'ct/kWh',
      color: 'red', icon: DATENROLLEN_ICONS.netzpreis,
      subtitle: `${fmt(t.netzbezug, 1)} kWh · ${fmtCalc(t.netzbezug_kosten, 2)} €`,
      formel: 'Netzbezug-Kosten ÷ Netzbezug',
    })
  }

  return [
    {
      title: 'PV-Erzeugung', value: fmt(t.erzeugung), unit: 'kWh', color: 'yellow', icon: DATENROLLEN_ICONS.pv,
      subtitle: [sollTxt, spezTxt, vtTxt].filter(Boolean).join(' · ') || undefined,
    },
    {
      title: 'Autarkie', value: fmt(t.autarkie), unit: '%', color: 'green', icon: DATENROLLEN_ICONS.autarkie,
      subtitle: vt ? `VT: ${fmt(vt.autarkie)} %` : undefined,
      formel: 'Eigenverbrauch ÷ Gesamtverbrauch × 100',
      berechnung: t.gesamtverbrauch > 0 ? `${fmt(t.eigenverbrauch)} ÷ ${fmt(t.gesamtverbrauch)} kWh` : undefined,
      ergebnis: t.autarkie != null ? `= ${fmtCalc(t.autarkie, 1)} %` : undefined,
    },
    {
      title: 'Eigenverbrauch', value: fmt(t.eigenverbrauch), unit: 'kWh', color: 'purple', icon: DATENROLLEN_ICONS.eigenverbrauch,
      subtitle: `EV-Quote ${fmt(t.evQuote)} %${vt ? ` · VT: ${fmt(vt.eigenverbrauch)} kWh` : ''}`,
    },
    {
      title: 'Einspeisung', value: fmt(t.einspeisung), unit: 'kWh', color: 'green', icon: DATENROLLEN_ICONS.einspeisung,
      subtitle: vt ? `VT: ${fmt(vt.einspeisung)} kWh` : undefined,
    },
    {
      title: 'Netzbezug', value: fmt(t.netzbezug), unit: 'kWh', color: 'red', icon: DATENROLLEN_ICONS.netzbezug,
      subtitle: vt ? `VT: ${fmt(vt.netzbezug)} kWh` : undefined,
    },
    {
      title: 'Netto-Ertrag', value: fmtCalc(t.netto_ertrag, 2, '—'), unit: '€', color: 'blue', icon: DATENROLLEN_ICONS.nettoErtrag,
      subtitle: 'Einspeise-Erlös + EV-Ersparnis',
      formel: 'Einspeise-Erlös + Eigenverbrauchs-Ersparnis',
      berechnung: `${fmtCalc(t.einspeise_erloes, 2)} + ${fmtCalc(t.ev_ersparnis, 2)} €`,
      ergebnis: `= ${fmtCalc(t.netto_ertrag, 2)} €`,
    },
    ...kostenKpis,
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

// Park-IDs des Tag-Bilanz-Blocks → `./bilanzParkIds` (reines Modul, kein react-refresh-Treffer).

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
      <td className={`${ZELLE} text-right tabular-nums text-gray-400 dark:text-gray-500 hidden sm:table-cell`}>
        {val != null ? fmt(val, dec(row)) : dash}
      </td>
      <td className={`${ZELLE} text-right tabular-nums`}>
        {val != null ? <Delta a={row.ist} b={val} inv={row.inv} besser={besser} /> : dash}
      </td>
    </>
  )

  // PR-Ampel = Tages-Pendant zum Monats-SOLL/IST: PR = Ertrag ÷ (gemessene
  // Einstrahlung × kWp) = IST gegen das physikalische Optimum bei der heutigen
  // Sonne. Selbsttragend (Einstrahlung liegt im Tageswert vor) → kein per-Tag-
  // PVGIS-SOLL/Backfill nötig (Gernot-Entscheid 2026-06-24). R3b S6: EINE
  // Stufen-Quelle → Farbe (AMPEL_TEXT_CLASS-Zwilling, Regel G) + Wort daraus.
  const prPct = t.performance_ratio != null ? t.performance_ratio * 100 : null
  const prStufe = prPct == null ? null
    : prPct >= 80 ? 'gut' as const
    : prPct >= 70 ? 'maessig' as const
    : prPct >= 60 ? 'hoch' as const
    : 'kritisch' as const
  const PR_WORT = { gut: 'sehr gut', maessig: 'solide', hoch: 'mäßig', kritisch: 'auffällig niedrig' } as const
  const strahlungKwh = t.strahlung_summe_wh_m2 != null ? t.strahlung_summe_wh_m2 / 1000 : null

  // Tages-Spitzen (Tag-native) — Peak PV + Temperatur (PR steht prominent oben).
  const spitzen: { label: string; value: string }[] = []
  if (t.peak_pv_kw != null) spitzen.push({ label: 'Peak PV', value: `${fmtCalc(t.peak_pv_kw, 2)} kW` })
  if (t.temperatur_min_c != null && t.temperatur_max_c != null)
    spitzen.push({ label: 'Temperatur', value: `${fmtCalc(t.temperatur_min_c, 1)} / ${fmtCalc(t.temperatur_max_c, 1)} °C` })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* IST / Vortag / Ø-Wochentag-Vergleich — eigene Parkbar (Doktrin). */}
      <Parkbar id="el:bilanz-vergleich" titel="Vergleich (IST/VT/Ø)" className="lg:col-span-2">
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

        {/* Desktop (≥ sm): aligned Tabelle über die Zentrale `ui/Table` (Regel T).
            Mobil zeigt der Block darüber die Kachel-Variante. */}
        <Table aussenClassName="hidden sm:block" flaeche="karte">
            <TableHead>
              <tr className="text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">
                <th className={`${KOPF_ZELLE} text-left`}><span className="sr-only">Kennzahl</span></th>
                <th colSpan={2} className={`${KOPF_ZELLE} text-center`}>IST</th>
                <th colSpan={2} className={`${KOPF_ZELLE} text-center`}>Vortag</th>
                {wtStats && <th colSpan={2} className={`${KOPF_ZELLE} text-center`}>{wtLabel}</th>}
              </tr>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                // Kein eigener `border-b` — der Zeilen-Trenner kommt aus TableBody
                // (`divide-y`, Regel T). Ein zusätzlicher `border-b` kollidiert mit
                // `divide-y` (nullt untere Ränder außer bei Zeile 1) → im Dark-Mode
                // blieb nur unter der 1. Zeile eine sichtbare Linie (gemessen 2026-07-11).
                <tr key={row.label}>
                  <td className={`${ZELLE} text-gray-600 dark:text-gray-400`}>{row.label}</td>
                  <td className={`${ZELLE} text-right font-semibold text-gray-900 dark:text-white tabular-nums`}>
                    {fmt(row.ist, dec(row))}
                  </td>
                  <td className={`${ZELLE} text-left text-gray-500 dark:text-gray-400`}>{row.unit}</td>
                  {vglZellen(row.vt, row, row.besserVt)}
                  {wtStats && vglZellen(row.wt, row, row.besserWt)}
                </tr>
              ))}
            </TableBody>
          </Table>
        {wtStats && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
            Ø aus {wtStats.count} {wochentagName}{wtStats.count !== 1 ? '-Tagen' : '-Tag'} (letzte 90 Tage)
          </p>
        )}
      </Parkbar>

      {/* PR-Ampel + Spitzen + PV-Verteilung — je eigene Parkbar (Doktrin), gestapelt.
          R3b S6: geteilter Kachel-Kern BilanzKachel (GrundlastSollIstKachel-SoT)
          statt Markup-Kopie; Wert-Farbe als AMPEL_TEXT_CLASS-Klasse statt Inline-Hex. */}
      <div className="space-y-4">
        <Parkbar id="el:bilanz-pr" titel="Performance Ratio">
          {prPct != null && prStufe != null ? (
            <BilanzKachel
              label="Performance Ratio"
              formel="Ertrag ÷ (Einstrahlung × kWp)"
              berechnung={strahlungKwh != null ? `bei ${fmt(strahlungKwh, 1)} kWh/m² Einstrahlung` : undefined}
              ergebnis={`= ${fmt(prPct, 0)} %`}
              wert={`${fmt(prPct, 0)} %`}
              wertClass={AMPEL_TEXT_CLASS[prStufe]}
              subtitle={<>{PR_WORT[prStufe]}{strahlungKwh != null ? ` · bei ${fmt(strahlungKwh, 1)} kWh/m²` : ''}</>}
              subtitleRechts
            />
          ) : (
            <>
              <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
                <FormelTooltip formel="Ertrag ÷ (Einstrahlung × kWp)">Performance Ratio</FormelTooltip>
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500">Keine Einstrahlungsdaten für diesen Tag — PR nicht berechenbar.</p>
            </>
          )}
        </Parkbar>

        {spitzen.length > 0 && (
          <Parkbar id="el:bilanz-spitzen" titel="Tages-Spitzen">
            <dl className="space-y-1.5">
              {spitzen.map((s) => (
                <div key={s.label} className="flex justify-between text-sm">
                  <dt className="text-gray-500 dark:text-gray-400">{s.label}</dt>
                  <dd className="tabular-nums text-gray-800 dark:text-gray-200">{s.value}</dd>
                </div>
              ))}
            </dl>
          </Parkbar>
        )}

        {t.eigenverbrauch != null && t.einspeisung != null && t.erzeugung > 0 && (
          <Parkbar id="el:bilanz-verteilung" titel="PV-Verteilung">
            <VerteilungsBalken
              titel="PV-Verteilung"
              segmente={[
                { label: 'Eigenverbr.', wert: t.eigenverbrauch, farbe: DATENROLLE.eigenverbrauch.bg },
                { label: 'Einspeisung', wert: t.einspeisung, farbe: DATENROLLE.einspeisung.bg },
              ]}
            />
          </Parkbar>
        )}
      </div>
    </div>
  )
}
