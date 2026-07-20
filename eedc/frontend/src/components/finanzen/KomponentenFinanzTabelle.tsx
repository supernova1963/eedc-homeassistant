/**
 * KomponentenFinanzTabelle — Cockpit-Finanzen als Komponenten-Tabelle (G20-1, SoT).
 *
 * Gernot-Entscheid 2026-07-20 (Variante V1, aus Mockups): der frühere Finanz-Teaser
 * (`v4/MonatRahmen.tsx`, halbes T-Konto mit Netzbezug-Ausweis IM Summen-Stapel) wird
 * durch EINE Zeile je Komponente ersetzt — Spalten **Erträge (tatsächlich)**,
 * **Einsparungen (kalkulatorisch)**, **Aufwand (tatsächlich)**, **Saldo**. Die
 * Summenzeile ist die Block-Kopf-Kennzahl (Kopf == sichtbare Summe).
 *
 * Datenquelle = ausschließlich der `/aktueller-monat`-Payload (Monat: kanonische
 * Antwort, Jahr: Σ-12 über `baueJahrAlsMonat`) — KEINE neuen Berechnungen; die
 * kanonische `netto_ertrag_euro`/`gesamtnettoertrag_euro`, HA-Export und das
 * Jahres-PDF bleiben unangetastet (die Tabellen-Summe ist bewusst eine eigene,
 * komponenten-attribuierte Sicht).
 *
 * Zeilen-Modell:
 *  - **PV-Anlage** (aus Anlage-Ebene): Erträge = Einspeise-Erlös · Einsparungen =
 *    Eigenverbrauch-Ersparnis (der gesamte EV; die Speicher-/BKW-Anteile erscheinen
 *    zusätzlich als eigene Komponenten-Beiträge — bewusste Attributions-Sicht).
 *  - je `investitionen_financials`-Zeile: Erträge = Einspeise-Erlös + Sonstige
 *    Erträge · Einsparungen = Ersparnis · Aufwand = Betriebskosten + Sonstige Ausgaben.
 *  - **Anlage — Sonstige Positionen** (nur wenn ≠ 0): Anlage-Ebene-Positionen.
 *
 * Regel T (ui/Table) · Geld-Farb-SoT (GELD_TEXT_CLASS) · Typ-Reihenfolge (compareTyp).
 * Tooltips app-global via `title`-Attribut (`useTouchTitleTooltip`, in App.tsx aktiv):
 * an den Spaltenköpfen die Spalten-Semantik, an den Zeilen die Herleitung
 * (`ersparnis_label` + `formel` + `berechnung`).
 */
import { fmtCalc } from '../ui'
import { Table, TableHead, TableBody, TableFoot } from '../ui/Table'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { GELD_TEXT_CLASS, compareTyp } from '../../lib'
import type { AktuellerMonatResponse, InvestitionFinancialDetail } from '../../api/aktuellerMonat'

const num = (v: number) => fmtCalc(v, 2, '—')
const saldoFarbe = (v: number) => (v >= 0 ? GELD_TEXT_CLASS.netto : GELD_TEXT_CLASS.kosten)

// Spaltenkopf-Tooltips (Gernot 2026-07-20): tatsächlich vs. kalkulatorisch klar machen.
const KOPF_TOOLTIP = {
  ertraege: 'Erträge = tatsächliche Zahlungsflüsse (Einspeise-Erlös, Sonstige Erträge, THG-Quote …).',
  einsparungen: 'Einsparungen = kalkulatorisch — vermiedene Kosten, die NICHT aufs Konto geflossen sind.',
  aufwand: 'Aufwendungen = tatsächliche Ausgaben inkl. anteilig umgelegter Jahres-Betriebskosten.',
  saldo: 'Saldo = Erträge + Einsparungen − Aufwendungen.',
} as const

interface FinanzZeile {
  key: string
  label: string
  typ: string | null
  ertraege: number
  einsparungen: number
  aufwand: number
  /** Herleitung als title-Tooltip (kalkulatorische Zeilen zeigen ihre Formel). */
  tooltip?: string
  /** Kurze Unterzeile am Label, nur wo fürs Verständnis nötig. */
  hinweis?: string
}

function zeilenAus(d: AktuellerMonatResponse): FinanzZeile[] {
  const zeilen: FinanzZeile[] = []

  // PV-Anlage (Anlage-Ebene): Einspeise-Erlös + Eigenverbrauch-Ersparnis.
  const einspeise = d.einspeise_erloes_euro
  const ev = d.ev_ersparnis_euro
  if (einspeise != null || ev != null) {
    zeilen.push({
      key: 'pv-anlage',
      label: 'PV-Anlage',
      typ: 'pv-module',
      ertraege: einspeise ?? 0,
      einsparungen: ev ?? 0,
      aufwand: 0,
      tooltip: 'Erträge: Einspeise-Erlös (Einspeisung × Vergütung). '
        + 'Einsparungen: Eigenverbrauch × Netzbezugspreis (vermiedener Netzbezug).',
    })
  }

  // Speicher-Netzladungs-Kosten (Anlage-Ebene, tatsächliche Ausgabe) fließen in die
  // Aufwand-Spalte der ERSTEN Speicher-Zeile — sie stecken NICHT im Haus-Netzbezug
  // (getrennte Messung), also kein Doppelzählen mit der nachrichtlichen Netzbezug-Zeile.
  let netzladungKosten = d.speicher_ladung_netz_kosten_euro ?? 0

  // Komponenten (investitionen_financials), Typ-Reihenfolge.
  const fins: InvestitionFinancialDetail[] = [...(d.investitionen_financials ?? [])].sort(compareTyp)
  for (const f of fins) {
    const istSpeicher = f.typ === 'speicher'
    const netzladung = istSpeicher ? netzladungKosten : 0
    if (istSpeicher) netzladungKosten = 0  // nur einmal zuordnen
    const ertraege = (f.erloes_euro ?? 0) + (f.sonstige_ertraege_euro ?? 0)
    const einsparungen = f.ersparnis_euro ?? 0
    const aufwand = (f.betriebskosten_monat_euro ?? 0) + (f.sonstige_ausgaben_euro ?? 0) + netzladung
    if (ertraege === 0 && einsparungen === 0 && aufwand === 0) continue
    // Herleitung der kalkulatorischen Einsparung als Tooltip (vorhandene Felder).
    const tooltipTeile: string[] = []
    if (einsparungen !== 0 && f.ersparnis_label) {
      tooltipTeile.push(f.formel ? `${f.ersparnis_label}: ${f.formel}` : f.ersparnis_label)
      if (f.berechnung) tooltipTeile.push(f.berechnung)
    }
    if (netzladung > 0) tooltipTeile.push(`inkl. Netzladung ${fmtCalc(netzladung, 2)} € (${fmtCalc(d.speicher_ladung_netz_kwh ?? 0, 1)} kWh Netz)`)
    const hinweise: string[] = []
    if ((f.betriebskosten_monat_euro ?? 0) > 0) hinweise.push('Betriebskosten anteilig')
    if (netzladung > 0) hinweise.push('inkl. Netzladung')
    zeilen.push({
      key: `inv-${f.investition_id}`,
      label: f.bezeichnung,
      typ: f.typ,
      ertraege,
      einsparungen,
      aufwand,
      tooltip: tooltipTeile.length ? tooltipTeile.join(' — ') : undefined,
      hinweis: hinweise.length ? hinweise.join(' · ') : undefined,
    })
  }

  // Sicherung: kein Speicher-Financial-Zeile vorhanden, aber Netzladungs-Kosten da
  // → eigene Zeile, damit die tatsächliche Ausgabe nicht still verschwindet.
  if (netzladungKosten > 0) {
    zeilen.push({
      key: 'speicher-netzladung',
      label: 'Speicher — Netzladung',
      typ: 'speicher',
      ertraege: 0,
      einsparungen: 0,
      aufwand: netzladungKosten,
      tooltip: `Netzladung ${fmtCalc(netzladungKosten, 2)} € (${fmtCalc(d.speicher_ladung_netz_kwh ?? 0, 1)} kWh Netz × Strompreis)`,
    })
  }

  // Anlage-übergreifende Sonstige Positionen — eigene Zeile, nur wenn ≠ 0.
  const aErt = d.anlage_sonstige_ertraege_euro ?? 0
  const aAus = d.anlage_sonstige_ausgaben_euro ?? 0
  if (aErt !== 0 || aAus !== 0) {
    zeilen.push({
      key: 'anlage-sonstige',
      label: 'Anlage — Sonstige Positionen',
      typ: 'sonstiges',
      ertraege: aErt,
      einsparungen: 0,
      aufwand: aAus,
      tooltip: 'In den Monatsdaten erfasste Sonstige Positionen auf Anlage-Ebene.',
    })
  }

  return zeilen
}

/** Summe je Spalte + Gesamt-Saldo (= Block-Kopf-Kennzahl). */
export function komponentenFinanzSaldo(d: AktuellerMonatResponse): number {
  return zeilenAus(d).reduce((s, z) => s + z.ertraege + z.einsparungen - z.aufwand, 0)
}

export function KomponentenFinanzTabelle({ d, zeitraum = 'monat' }: {
  d: AktuellerMonatResponse
  zeitraum?: 'monat' | 'jahr'
}) {
  const zeilen = zeilenAus(d)
  if (zeilen.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Finanzdaten im Zeitraum.</p>
  }
  const sum = zeilen.reduce(
    (a, z) => ({
      ertraege: a.ertraege + z.ertraege,
      einsparungen: a.einsparungen + z.einsparungen,
      aufwand: a.aufwand + z.aufwand,
    }),
    { ertraege: 0, einsparungen: 0, aufwand: 0 },
  )
  const saldoVon = (z: { ertraege: number; einsparungen: number; aufwand: number }) =>
    z.ertraege + z.einsparungen - z.aufwand
  const gesamtSaldo = saldoVon(sum)

  const zahl = 'text-right tabular-nums'

  return (
    <div className="space-y-2">
      {/* EINE Legende tatsächlich/kalkulatorisch (statt Fußnoten-Markern an Zahlen). */}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Erträge &amp; Aufwand = tatsächliche Zahlungsflüsse · Einsparungen = kalkulatorisch (vermiedene Kosten).
        Details je Zeile/Spalte im Tooltip.
      </p>

      {/* ── Desktop: Tabelle (Regel T) ── */}
      <Table zeilen={12} mitFuss flaeche="karte" className="w-full" aussenClassName="hidden sm:block">
        <TableHead>
          <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
            <th className={KOPF_ZELLE}>Komponente</th>
            <th className={`${KOPF_ZELLE} text-right`} title={KOPF_TOOLTIP.ertraege}>Erträge (€)</th>
            <th className={`${KOPF_ZELLE} text-right`} title={KOPF_TOOLTIP.einsparungen}>Einsparungen (€)</th>
            <th className={`${KOPF_ZELLE} text-right`} title={KOPF_TOOLTIP.aufwand}>Aufwand (€)</th>
            <th className={`${KOPF_ZELLE} text-right`} title={KOPF_TOOLTIP.saldo}>Saldo (€)</th>
          </tr>
        </TableHead>
        <TableBody>
          {zeilen.map((z) => {
            const saldo = saldoVon(z)
            return (
              <tr key={z.key} className="border-b border-gray-100 dark:border-gray-800">
                <td className={`${ZELLE} text-gray-700 dark:text-gray-300`} title={z.tooltip}>
                  {z.label}
                  {z.hinweis && (
                    <span className="block text-xs text-gray-400 dark:text-gray-500">{z.hinweis}</span>
                  )}
                </td>
                <td className={`${ZELLE} ${zahl} text-gray-700 dark:text-gray-300`}>{z.ertraege ? num(z.ertraege) : '—'}</td>
                <td className={`${ZELLE} ${zahl} text-gray-700 dark:text-gray-300`}>{z.einsparungen ? num(z.einsparungen) : '—'}</td>
                <td className={`${ZELLE} ${zahl} text-gray-700 dark:text-gray-300`}>{z.aufwand ? num(z.aufwand) : '—'}</td>
                <td className={`${ZELLE} ${zahl} font-semibold ${saldoFarbe(saldo)}`}>{num(saldo)}</td>
              </tr>
            )
          })}
        </TableBody>
        <TableFoot>
          <tr>
            <td className={`${ZELLE} text-gray-600 dark:text-gray-300 text-xs uppercase tracking-wide`}>Summe</td>
            <td className={`${ZELLE} ${zahl} text-gray-800 dark:text-gray-100`}>{num(sum.ertraege)}</td>
            <td className={`${ZELLE} ${zahl} text-gray-800 dark:text-gray-100`}>{num(sum.einsparungen)}</td>
            <td className={`${ZELLE} ${zahl} text-gray-800 dark:text-gray-100`}>{num(sum.aufwand)}</td>
            <td className={`${ZELLE} ${zahl} font-bold ${saldoFarbe(gesamtSaldo)}`}>{num(gesamtSaldo)}</td>
          </tr>
        </TableFoot>
      </Table>

      {/* ── Mobil: Regel-T-Stapelmuster (wie TKonto) — je Komponente eine Karte ── */}
      <div className="sm:hidden space-y-2">
        {zeilen.map((z) => {
          const saldo = saldoVon(z)
          return (
            <div key={z.key} className="rounded-lg border border-gray-200 dark:border-gray-700 p-2.5" title={z.tooltip}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{z.label}</span>
                <span className={`text-sm font-semibold tabular-nums ${saldoFarbe(saldo)}`}>{num(saldo)} €</span>
              </div>
              {z.hinweis && <span className="block text-xs text-gray-400 dark:text-gray-500">{z.hinweis}</span>}
              <dl className="mt-1.5 grid grid-cols-3 gap-1 text-xs">
                <div><dt className="text-gray-400 dark:text-gray-500">Erträge</dt><dd className="tabular-nums text-gray-700 dark:text-gray-300">{z.ertraege ? num(z.ertraege) : '—'}</dd></div>
                <div><dt className="text-gray-400 dark:text-gray-500">Einsparung</dt><dd className="tabular-nums text-gray-700 dark:text-gray-300">{z.einsparungen ? num(z.einsparungen) : '—'}</dd></div>
                <div><dt className="text-gray-400 dark:text-gray-500">Aufwand</dt><dd className="tabular-nums text-gray-700 dark:text-gray-300">{z.aufwand ? num(z.aufwand) : '—'}</dd></div>
              </dl>
            </div>
          )
        })}
        <div className="rounded-lg border-2 border-gray-300 dark:border-gray-600 p-2.5 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wide text-gray-600 dark:text-gray-300">Summe (Saldo)</span>
          <span className={`text-sm font-bold tabular-nums ${saldoFarbe(gesamtSaldo)}`}>{num(gesamtSaldo)} €</span>
        </div>
      </div>

      {/* ── Nachrichtlich (NICHT verrechnet): Netzbezug + Zählergebühr ── */}
      <div className="text-xs text-gray-400 dark:text-gray-500 space-y-0.5 pt-1">
        {d.netzbezug_kosten_euro != null && (
          <p>
            Nachrichtlich (nicht im Saldo): Netzbezug-Kosten {fmtCalc(d.netzbezug_kosten_euro, 2)} €
            {(d.grundgebuehr_euro ?? 0) > 0 && <> · davon Grundgebühr {fmtCalc(d.grundgebuehr_euro, 2)} €</>}
          </p>
        )}
        {zeitraum === 'jahr' && d.zaehlergebuehr_euro_jahr != null && d.zaehlergebuehr_euro_jahr > 0 && (
          <p>Zählergebühr {fmtCalc(d.zaehlergebuehr_euro_jahr, 2)} €/Jahr (nachrichtlich, nicht im Saldo)</p>
        )}
      </div>
    </div>
  )
}
