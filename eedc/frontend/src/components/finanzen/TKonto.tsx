/**
 * TKonto — anlage-weites SOLL/HABEN-T-Konto (SoT).
 *
 * Verhaltensgleich ausgelagert aus `pages/MonatsabschlussView.tsx` → von der
 * IST-Monatsabschluss-Sicht UND der v4-Auswertung „Finanzen" geteilt (eine
 * Code-Wahrheit). Eingabe ist EIN `AktuellerMonatResponse`-Period-Shape: im
 * Monat die kanonische Monats-Antwort, im Jahr die Σ-12-Aggregation
 * (`baueJahrAlsMonat`). Vorjahr-Δ kommt aus `d.vorjahr` (Monat: Vorjahres-Monat;
 * Jahr: null → kein Δ). `sonderkosten` = Fallback-Aggregat, wenn keine
 * Per-Investition-Financials vorliegen.
 */
import React from 'react'
import { FormelTooltip, fmtCalc } from '../ui'
import { TYP_TEXT_CLASS } from '../../lib'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'

const fmt = (v: number | null | undefined, d = 1) => fmtCalc(v, d, '—')

function Δ({ a, b, inv = false }: { a: number | null | undefined; b: number | null | undefined; inv?: boolean }) {
  if (a == null || b == null || b === 0) return null
  const pct = ((a - b) / Math.abs(b)) * 100
  const positive = inv ? pct <= 0 : pct >= 0
  return (
    <span className={`text-xs font-medium px-1 py-0.5 rounded ${
      positive
        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
    }`}>
      {pct >= 0 ? '▲' : '▼'} {Math.abs(pct).toFixed(0)} %
    </span>
  )
}

export function TKonto({ d, sonderkosten = null }: { d: AktuellerMonatResponse; sonderkosten?: number | null }) {
  const vj = d.vorjahr
  const netzPreis = d.netzbezug_durchschnittspreis_cent ?? d.netzbezug_preis_cent

  // ── T-Konto Datenstruktur ──────────────────────────────
  type TKontoPosten = {
    label: string
    wert: number
    vjWert?: number | null
    formel?: string
    berechnung?: string
    ergebnis?: string
    color: string
  }

  // Farbe je Investitionstyp
  // Identitätsfarbe je Typ aus der Kanon-SoT (TYP_TEXT_CLASS, Regel A) —
  // keine zweite Typ→Farbmap mehr (war gedriftet: e-auto/wallbox lila, WP orange).
  const typColor = (typ: string) => TYP_TEXT_CLASS[typ] ?? 'text-gray-500'

  const fins = d.investitionen_financials ?? []
  const hasPerInv = fins.length > 0

  // Welche Komponenten-Ersparnisse stecken in ev_ersparnis (BKW, Speicher, Wallbox-PV-Ladung).
  // Backend rechnet ev_ersparnis = eigenverbrauch_kwh × netzbezug_preis, wobei eigenverbrauch
  // den Direktverbrauch (= PV − Einspeisung − Batterie-Ladung) inkl. Wallbox-PV-Ladung umfasst.
  // Werden BKW/Speicher/Wallbox-PV-Ladung separat im T-Konto ausgewiesen, muss ihr Anteil
  // hier abgezogen werden, sonst Doppelzählung im Σ Haben (Issue #223).
  const evInErsparnis = hasPerInv
    ? fins
        .filter(inv =>
          inv.typ === 'balkonkraftwerk'
          || inv.typ === 'speicher'
          || (inv.typ === 'wallbox' && inv.ersparnis_label === 'PV-Ladung-Ersparnis')
        )
        .reduce((s, inv) => s + (inv.ersparnis_euro ?? 0), 0)
    : 0
  const pvEvResidual = Math.max(0, (d.ev_ersparnis_euro ?? 0) - evInErsparnis)

  const preisBez = d.netzbezug_durchschnittspreis_cent != null ? 'Ø-Preis flex' : 'Netzbezugspreis'

  const habenPosten: TKontoPosten[] = [
    // ── Einspeise-Erlöse (immer) ──
    {
      label: 'Einspeise-Erlöse',
      wert: d.einspeise_erloes_euro ?? 0,
      vjWert: vj?.einspeise_erloes_euro,
      color: 'text-green-600 dark:text-green-400',
      formel: 'Einspeisung × Einspeisevergütung',
      berechnung: d.einspeisung_kwh != null && d.einspeise_preis_cent != null
        ? `${fmt(d.einspeisung_kwh, 1)} kWh × ${fmtCalc(d.einspeise_preis_cent, 2)} ct/kWh`
        : undefined,
      ergebnis: `= ${fmtCalc(d.einspeise_erloes_euro, 2)} €`,
    },
    // ── PV-Eigenverbrauch ──
    // Mit per-Inv-Daten: Residual (ohne BKW/Speicher die separat gezeigt werden)
    // Ohne per-Inv-Daten: Gesamtwert inkl. VJ-Vergleich
    ...(hasPerInv && pvEvResidual > 0 ? [{
      label: 'PV-Eigenverbrauch-Ersparnis',
      wert: pvEvResidual,
      vjWert: undefined as number | null | undefined,
      color: 'text-blue-600 dark:text-blue-400',
      formel: `PV-Eigenverbrauch × ${preisBez}`,
      berechnung: d.eigenverbrauch_kwh != null && netzPreis != null
        ? `${fmt(d.eigenverbrauch_kwh - evInErsparnis / (netzPreis / 100), 1)} kWh × ${fmtCalc(netzPreis, 2)} ct/kWh`
        : undefined,
      ergebnis: `= ${fmtCalc(pvEvResidual, 2)} €`,
    } as TKontoPosten] : !hasPerInv ? [{
      label: 'Eigenverbrauch-Ersparnis',
      wert: d.ev_ersparnis_euro ?? 0,
      vjWert: vj?.ev_ersparnis_euro,
      color: 'text-blue-600 dark:text-blue-400',
      formel: `Eigenverbrauch × ${preisBez}`,
      berechnung: d.eigenverbrauch_kwh != null && netzPreis != null
        ? `${fmt(d.eigenverbrauch_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct/kWh`
        : undefined,
      ergebnis: `= ${fmtCalc(d.ev_ersparnis_euro, 2)} €`,
    } as TKontoPosten] : []),
    // ── Per-Investition: BKW, Speicher, WP, eMob, Sonstiges ──
    ...fins.flatMap((inv): TKontoPosten[] => {
      const rows: TKontoPosten[] = []
      if (inv.erloes_euro != null && inv.erloes_euro > 0) {
        rows.push({
          label: `${inv.bezeichnung} — Einspeisung`,
          wert: inv.erloes_euro,
          color: 'text-green-600 dark:text-green-400',
          formel: 'Einspeisung × Einspeisevergütung',
          ergebnis: `= ${fmtCalc(inv.erloes_euro, 2)} €`,
        })
      }
      if (inv.ersparnis_euro != null) {
        rows.push({
          label: `${inv.bezeichnung} — ${inv.ersparnis_label || 'Ersparnis'}`,
          wert: inv.ersparnis_euro,
          color: typColor(inv.typ),
          formel: inv.formel ?? undefined,
          berechnung: inv.berechnung ?? undefined,
          ergebnis: `= ${fmtCalc(inv.ersparnis_euro, 2)} €`,
        })
      }
      if ((inv.sonstige_ertraege_euro ?? 0) > 0) {
        rows.push({
          label: `${inv.bezeichnung} — Sonstige Erträge`,
          wert: inv.sonstige_ertraege_euro,
          color: 'text-green-600 dark:text-green-400',
          formel: 'Erfasst im Monatsabschluss als Position vom Typ "Ertrag"',
          ergebnis: `= ${fmtCalc(inv.sonstige_ertraege_euro, 2)} €`,
        })
      }
      return rows
    }),
    // Fallback-Aggregat ohne per-Inv-Daten: sonst weichen
    // T-Konto-Summe und Monatsergebnis auseinander.
    ...(!hasPerInv && (d.sonstige_ertraege_euro ?? 0) > 0 ? [{
      label: 'Sonstige Erträge',
      wert: d.sonstige_ertraege_euro,
      color: 'text-green-600 dark:text-green-400',
    } as TKontoPosten] : []),
    // ── Fallback: WP/eMob-Aggregate wenn kein per-Inv-Daten ──
    ...(!hasPerInv && d.wp_ersparnis_euro != null ? [{
      label: 'WP-Ersparnis vs. Gas',
      wert: d.wp_ersparnis_euro,
      color: typColor('waermepumpe'),
      formel: '(Wärme ÷ 0,9 × Gaspreis) − Strom × WP-Strompreis',
      berechnung: d.wp_waerme_kwh != null && d.wp_strom_kwh != null
        ? `${fmt(d.wp_waerme_kwh, 1)} kWh / 0,9 × 10 ct − ${fmt(d.wp_strom_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct`
        : undefined,
      ergebnis: `= ${fmtCalc(d.wp_ersparnis_euro, 2)} €`,
    } as TKontoPosten] : []),
    ...(!hasPerInv && d.emob_ersparnis_euro != null ? [{
      label: 'eMob-Ersparnis vs. Verbrenner',
      wert: d.emob_ersparnis_euro,
      color: 'text-purple-500',
      formel: '(km × 7 L/100km × 1,80 €/L) − Netzladung × Strompreis',
      berechnung: d.emob_km != null ? [
        `${fmt(d.emob_km, 0)} km × 7/100 × 1,80 €`,
        d.emob_ladung_netz_kwh != null
          ? `− ${fmt(d.emob_ladung_netz_kwh, 1)} kWh Netz × ${fmtCalc(netzPreis, 2)} ct`
          : `− ${fmt(d.emob_ladung_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct`,
        d.emob_ladung_pv_kwh != null ? `(PV ${fmt(d.emob_ladung_pv_kwh, 1)} kWh kostenlos)` : null,
      ].filter(Boolean).join('\n') : undefined,
      ergebnis: `= ${fmtCalc(d.emob_ersparnis_euro, 2)} €`,
    } as TKontoPosten] : []),
  ]

  const sollPosten: TKontoPosten[] = [
    {
      label: 'Netzbezug-Kosten',
      wert: d.netzbezug_kosten_euro ?? 0,
      vjWert: vj?.netzbezug_kosten_euro,
      color: 'text-red-500',
      formel: 'Netzbezug × Arbeitspreis + Grundpreis',
      berechnung: d.netzbezug_kwh != null && netzPreis != null ? [
        `${fmt(d.netzbezug_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct/kWh + Grundpreis`,
        d.netzbezug_durchschnittspreis_cent != null ? '(flex. Tarif, Monatsdurchschnitt)' : null,
      ].filter(Boolean).join('\n') : undefined,
      ergebnis: `= ${fmtCalc(d.netzbezug_kosten_euro, 2)} €`,
    },
    // ── Betriebskosten: per Investition wenn Daten da, sonst Aggregat ──
    ...(hasPerInv
      ? fins
          .filter(inv => inv.betriebskosten_monat_euro > 0)
          .map(inv => ({
            label: `${inv.bezeichnung} — Betriebskosten`,
            wert: inv.betriebskosten_monat_euro,
            color: 'text-amber-600',
            formel: 'Betriebskosten/Jahr ÷ 12',
            ergebnis: `= ${fmtCalc(inv.betriebskosten_monat_euro, 2)} €`,
          } as TKontoPosten))
      : (d.betriebskosten_anteilig_euro ?? 0) > 0 ? [{
          label: 'Betriebskosten (anteilig)',
          wert: d.betriebskosten_anteilig_euro!,
          color: 'text-amber-600',
          formel: 'Σ (Betriebskosten/Jahr ÷ 12) aller aktiven Investitionen',
          ergebnis: `= ${fmtCalc(d.betriebskosten_anteilig_euro, 2)} €`,
        } as TKontoPosten] : []
    ),
    // ── Per-Investition: Sonstige Ausgaben (Reparaturen, THG-Quote als Ausgabe etc.) ──
    ...(hasPerInv
      ? fins
          .filter(inv => (inv.sonstige_ausgaben_euro ?? 0) > 0)
          .map(inv => ({
            label: `${inv.bezeichnung} — Sonstige Ausgaben`,
            wert: inv.sonstige_ausgaben_euro,
            color: 'text-red-500',
            formel: 'Erfasst im Monatsabschluss als Position vom Typ "Ausgabe"',
            ergebnis: `= ${fmtCalc(inv.sonstige_ausgaben_euro, 2)} €`,
          } as TKontoPosten))
      // Fallback ohne per-Inv-Daten: Aggregat aus cockpit/komponenten
      : (sonderkosten ?? 0) > 0 ? [{
          label: 'Sonderkosten',
          wert: sonderkosten!,
          color: 'text-red-500',
        } as TKontoPosten] : []
    ),
  ]

  // Summen aus tatsächlich angezeigten Zeilen berechnen
  const rawSoll  = sollPosten.reduce((s, p) => s + p.wert, 0)
  const rawHaben = habenPosten.reduce((s, p) => s + p.wert, 0)
  const nettoT   = rawHaben - rawSoll   // T-Konto-Gewinn aus Zeilen
  const gewinnSeite = nettoT >= 0 ? 'soll' : 'haben'
  const sumSoll  = rawSoll  + Math.max(0,  nettoT)
  const sumHaben = rawHaben + Math.max(0, -nettoT)



  // VJ-Summen
  const vjSumSoll  = vj?.netzbezug_kosten_euro != null ? (vj.netzbezug_kosten_euro + Math.max(0, vj.gesamtnettoertrag_euro ?? 0)) : null
  const vjSumHaben = vj?.einspeise_erloes_euro != null ? ((vj.einspeise_erloes_euro ?? 0) + (vj.ev_ersparnis_euro ?? 0) + Math.max(0, -(vj.gesamtnettoertrag_euro ?? 0))) : null

  return (
    <div className="mt-3">
      <div className="rounded-xl border border-gray-200 dark:border-gray-700">

        {/* Eine einzige Tabelle: 9 Spalten = 4 SOLL + 1 Trennlinie + 4 HABEN */}
        {(() => {
          const maxRows = Math.max(
            sollPosten.length + 1 + (gewinnSeite === 'soll' ? 1 : 0),
            habenPosten.length + 1 + (gewinnSeite === 'haben' ? 1 : 0),
          )
          // SOLL-Zeilen: Posten + Leerzeile + ggf. Gewinn
          const sollRows: (TKontoPosten | null | 'empty' | 'ergebnis')[] = [
            ...sollPosten,
            'empty',
            ...(gewinnSeite === 'soll' ? ['ergebnis' as const] : []),
          ]
          const habenRows: (TKontoPosten | null | 'empty' | 'ergebnis')[] = [
            ...habenPosten,
            'empty',
            ...(gewinnSeite === 'haben' ? ['ergebnis' as const] : []),
          ]
          // Auf gleiche Länge auffüllen
          while (sollRows.length < maxRows) sollRows.push(null)
          while (habenRows.length < maxRows) habenRows.push(null)

          const tdDiv = 'w-0 p-0 border-l border-gray-200 dark:border-gray-700'

          const renderCell = (item: TKontoPosten | null | 'empty' | 'ergebnis', seite: 'soll' | 'haben') => {
            if (item === null) return <><td /><td /><td /><td /></>
            if (item === 'empty') return <><td className="py-1" colSpan={4} /></>
            if (item === 'ergebnis') {
              const isGewinn = seite === 'soll'
              return <>
                <td className="py-2 pl-4 pr-2 font-bold text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-600">
                  {isGewinn ? 'Gewinn' : 'Verlust'}
                </td>
                <td className={`py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold border-b border-gray-200 dark:border-gray-600 ${isGewinn ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {fmtCalc(Math.abs(nettoT), 2)} €
                </td>
                <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-600">
                  {vj?.gesamtnettoertrag_euro != null ? `VJ: ${fmtCalc(vj.gesamtnettoertrag_euro, 2)} €` : ''}
                </td>
                <td className="py-2 pr-4 text-right whitespace-nowrap border-b border-gray-200 dark:border-gray-600">
                  {vj?.gesamtnettoertrag_euro != null ? <Δ a={nettoT} b={vj.gesamtnettoertrag_euro} /> : null}
                </td>
              </>
            }
            // Normaler Posten
            return <>
              <td className="py-2 pl-4 pr-2 text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700/50">
                {item.formel
                  ? <FormelTooltip formel={item.formel} berechnung={item.berechnung} ergebnis={item.ergebnis}>{item.label}</FormelTooltip>
                  : item.label}
              </td>
              <td className={`py-2 pr-3 text-right tabular-nums whitespace-nowrap font-semibold border-b border-gray-100 dark:border-gray-700/50 ${item.color}`}>
                {fmtCalc(item.wert, 2)} €
              </td>
              <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700/50">
                {item.vjWert != null ? `VJ: ${fmtCalc(item.vjWert, 2)} €` : ''}
              </td>
              <td className="py-2 pr-4 text-right whitespace-nowrap border-b border-gray-100 dark:border-gray-700/50">
                {item.vjWert != null ? <Δ a={item.wert} b={item.vjWert} inv={seite === 'soll'} /> : null}
              </td>
            </>
          }

          const thSoll = "px-4 py-2 text-left text-xs font-bold text-red-700 dark:text-red-400 uppercase tracking-wider bg-red-50 dark:bg-red-900/20"
          const thHaben = "px-4 py-2 text-left text-xs font-bold text-green-700 dark:text-green-400 uppercase tracking-wider bg-green-50 dark:bg-green-900/20"
          const sumRow = "bg-gray-100 dark:bg-gray-700/60 border-t-2 border-gray-300 dark:border-gray-600"

          return (
            <>
              {/* ── Desktop: SOLL | HABEN nebeneinander ── */}
              <table className="hidden sm:table w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-600">
                    <th colSpan={4} className={thSoll}>SOLL — Kosten</th>
                    <th className="w-0 p-0 border-l border-gray-200 dark:border-gray-700" aria-hidden="true" />
                    <th colSpan={4} className={thHaben}>HABEN — Erlöse + Einsparungen</th>
                  </tr>
                </thead>
                <tbody>
                  {sollRows.map((s, i) => (
                    <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors">
                      {renderCell(s, 'soll')}
                      <td className={tdDiv} />
                      {renderCell(habenRows[i], 'haben')}
                    </tr>
                  ))}
                  <tr className={sumRow}>
                    <td className="py-2 pl-4 pr-2 text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Σ Soll</td>
                    <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold text-gray-900 dark:text-white">{fmtCalc(sumSoll, 2)} €</td>
                    <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">{vjSumSoll != null ? `VJ: ${fmtCalc(vjSumSoll, 2)} €` : ''}</td>
                    <td className="py-2 pr-4 text-right whitespace-nowrap">{vjSumSoll != null ? <Δ a={sumSoll} b={vjSumSoll} inv /> : null}</td>
                    <td className={tdDiv} />
                    <td className="py-2 pl-4 pr-2 text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Σ Haben</td>
                    <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold text-gray-900 dark:text-white">{fmtCalc(sumHaben, 2)} €</td>
                    <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">{vjSumHaben != null ? `VJ: ${fmtCalc(vjSumHaben, 2)} €` : ''}</td>
                    <td className="py-2 pr-4 text-right whitespace-nowrap">{vjSumHaben != null ? <Δ a={sumHaben} b={vjSumHaben} /> : null}</td>
                  </tr>
                </tbody>
              </table>

              {/* ── Mobile: Gewinn-und-Verlust-Rechnung (kompaktes 2-Spalten-Layout) ── */}
              <div className="sm:hidden">
                {(() => {
                  // Mobile-Renderer: Label links, Wert + VJ + Badge gestapelt rechts.
                  // Spart Breite gegenüber 4-Spalten-Layout, hält Inhalt im Card-Rahmen.
                  const mobileRow = (
                    label: React.ReactNode,
                    wert: number | null | undefined,
                    vjWert: number | null | undefined,
                    color: string,
                    bold: boolean,
                    inv: boolean,
                    rowClass = '',
                  ) => (
                    <tr className={rowClass || 'hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors'}>
                      <td className={`py-2 pl-2 pr-2 text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700/50 ${bold ? 'text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider' : ''}`}>
                        {label}
                      </td>
                      <td className="py-2 pr-2 text-right border-b border-gray-100 dark:border-gray-700/50 align-top">
                        <div className={`tabular-nums whitespace-nowrap ${bold ? 'font-bold text-gray-900 dark:text-white' : `font-semibold ${color}`}`}>
                          {fmtCalc(wert ?? 0, 2)} €
                        </div>
                        {vjWert != null && (
                          <div className="flex items-center gap-1 justify-end mt-0.5 text-[11px] text-gray-400 dark:text-gray-500 tabular-nums whitespace-nowrap">
                            <span>VJ: {fmtCalc(vjWert, 2)} €</span>
                            <Δ a={wert} b={vjWert} inv={inv} />
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                  return <>
                    {/* Kosten */}
                    <table className="w-full text-sm table-fixed">
                      <colgroup>
                        <col className="w-1/2" />
                        <col className="w-1/2" />
                      </colgroup>
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-600">
                          <th colSpan={2} className={thSoll}>Kosten</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sollPosten.map((s, i) => (
                          <React.Fragment key={i}>
                            {mobileRow(
                              s.formel
                                ? <FormelTooltip formel={s.formel} berechnung={s.berechnung} ergebnis={s.ergebnis}>{s.label}</FormelTooltip>
                                : s.label,
                              s.wert, s.vjWert, s.color, false, true,
                            )}
                          </React.Fragment>
                        ))}
                        {mobileRow('Summe Kosten', rawSoll, vj?.netzbezug_kosten_euro, '', true, true, sumRow)}
                      </tbody>
                    </table>
                    {/* Erlöse + Einsparungen */}
                    <table className="w-full text-sm table-fixed border-t-2 border-gray-300 dark:border-gray-600">
                      <colgroup>
                        <col className="w-1/2" />
                        <col className="w-1/2" />
                      </colgroup>
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-600">
                          <th colSpan={2} className={thHaben}>Erlöse + Einsparungen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {habenPosten.map((h, i) => (
                          <React.Fragment key={i}>
                            {mobileRow(
                              h.formel
                                ? <FormelTooltip formel={h.formel} berechnung={h.berechnung} ergebnis={h.ergebnis}>{h.label}</FormelTooltip>
                                : h.label,
                              h.wert, h.vjWert, h.color, false, false,
                            )}
                          </React.Fragment>
                        ))}
                        {mobileRow(
                          'Summe Erträge',
                          rawHaben,
                          (vj?.einspeise_erloes_euro != null || vj?.ev_ersparnis_euro != null)
                            ? (vj.einspeise_erloes_euro ?? 0) + (vj.ev_ersparnis_euro ?? 0)
                            : null,
                          '', true, false, sumRow,
                        )}
                      </tbody>
                    </table>
                    {/* Netto-Ergebnis */}
                    <table className="w-full text-sm table-fixed border-t-2 border-gray-400 dark:border-gray-500">
                      <colgroup>
                        <col className="w-1/2" />
                        <col className="w-1/2" />
                      </colgroup>
                      <tbody>
                        <tr className="bg-gray-100 dark:bg-gray-700/60">
                          <td className="py-2 pl-2 pr-2 text-sm font-bold text-gray-900 dark:text-white uppercase tracking-wider">
                            {nettoT >= 0 ? 'Gewinn' : 'Verlust'}
                          </td>
                          <td className="py-2 pr-2 text-right align-top">
                            <div className={`tabular-nums whitespace-nowrap font-bold ${nettoT >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                              {fmtCalc(Math.abs(nettoT), 2)} €
                            </div>
                            {vj?.gesamtnettoertrag_euro != null && (
                              <div className="flex items-center gap-1 justify-end mt-0.5 text-[11px] text-gray-400 dark:text-gray-500 tabular-nums whitespace-nowrap">
                                <span>VJ: {fmtCalc(vj.gesamtnettoertrag_euro, 2)} €</span>
                                <Δ a={nettoT} b={vj.gesamtnettoertrag_euro} />
                              </div>
                            )}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </>
                })()}
              </div>
            </>
          )
        })()}
      </div>

      {/* Tarif-Info */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500 px-1">
        {d.netzbezug_durchschnittspreis_cent != null
          ? <span>Netzbezug Ø <span className="text-blue-500 font-medium">{fmtCalc(d.netzbezug_durchschnittspreis_cent, 2)} ct/kWh</span> (flex)</span>
          : d.netzbezug_preis_cent != null && <span>Netzbezug {fmtCalc(d.netzbezug_preis_cent, 2)} ct/kWh</span>
        }
        {d.einspeise_preis_cent != null && <span>Einspeisung {fmtCalc(d.einspeise_preis_cent, 2)} ct/kWh</span>}
      </div>
    </div>
  )

}
