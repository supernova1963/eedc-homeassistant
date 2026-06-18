/**
 * MonatRahmen — Sicht-Rahmen-Bausteine der Cockpit/Monat-Sicht (IA v4 E3 Slice 2e,
 * O5/B5/O4).
 *
 * - {@link MonatHeader}: PageHeader (Titel + „läuft"/„abgeschlossen"-Status-Badge
 *   + Quellen-Provenance-Badges aus `feld_quellen`).
 * - {@link finanzTeaserBlock}: Finanz-Teaser-Block — Netto-Ertrag + Aufschlüsselung
 *   + Cross-Link „volle Finanzrechnung →" nach Auswertungen (T-Konto lebt dort, B5/F2-a).
 * - {@link communityBlock}: Community-Vergleich, data-gated (nur wenn Anlagen im
 *   Monat vorhanden, O4).
 */
import { ArrowRight } from 'lucide-react'
import { fmtCalc } from '../components/ui'
import { BLOCK_IDENTITAET } from '../lib'
import type { Block } from '../components/blocks'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { MonatsVergleich } from '../api/community'

const euro = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${fmtCalc(v, 2)} €`)

// Roh-Enum → Label (Roh-Werte gehören nie in die UI, [[feedback_typ_labels_pattern]]).
const QUELLE_LABEL: Record<string, string> = {
  ha_sensor: 'HA', mqtt: 'MQTT', connector: 'Connector',
  scheduler: 'gespeichert', monatsabschluss: 'Abschluss', manuell: 'manuell',
}

function provenanceQuellen(feldQuellen: AktuellerMonatResponse['feld_quellen']): string[] {
  if (!feldQuellen) return []
  const set = new Set<string>()
  for (const info of Object.values(feldQuellen)) {
    if (info?.quelle) set.add(QUELLE_LABEL[info.quelle] ?? info.quelle)
  }
  return [...set]
}

export function MonatHeader({ titel, laufend, d }: {
  titel: string
  laufend: boolean
  d: AktuellerMonatResponse | null
}) {
  const quellen = d ? provenanceQuellen(d.feld_quellen) : []
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{titel}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'läuft' : 'abgeschlossen'}
        </span>
      </div>
      {quellen.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-gray-400 dark:text-gray-500">Quellen:</span>
          {quellen.map((q) => (
            <span key={q} className="text-[10px] leading-tight px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {q}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** Finanz-Teaser (B5): Netto-Ertrag + Aufschlüsselung + Cross-Link nach Auswertungen. */
export function finanzTeaserBlock(d: AktuellerMonatResponse): Block {
  return {
    id: 'finanzen',
    title: 'Finanzen',
    ...BLOCK_IDENTITAET.finanzen,
    summary: `${euro(d.netto_ertrag_euro)} Netto-Ertrag`,
    defaultOpen: false,
    render: () => (
      <div className="space-y-3">
        <dl className="text-sm space-y-1.5">
          <div className="flex justify-between"><dt className="text-gray-500 dark:text-gray-400">Einspeise-Erlös</dt><dd className="tabular-nums text-gray-800 dark:text-gray-200">{euro(d.einspeise_erloes_euro)}</dd></div>
          <div className="flex justify-between"><dt className="text-gray-500 dark:text-gray-400">EV-Ersparnis</dt><dd className="tabular-nums text-gray-800 dark:text-gray-200">{euro(d.ev_ersparnis_euro)}</dd></div>
          <div className="flex justify-between"><dt className="text-gray-500 dark:text-gray-400">Netzbezug-Kosten</dt><dd className="tabular-nums text-gray-800 dark:text-gray-200">{euro(d.netzbezug_kosten_euro != null ? -d.netzbezug_kosten_euro : null)}</dd></div>
          <div className="flex justify-between border-t border-gray-200 dark:border-gray-700 pt-1.5 font-semibold"><dt className="text-gray-700 dark:text-gray-200">Netto-Ertrag</dt><dd className="tabular-nums text-gray-900 dark:text-white">{euro(d.netto_ertrag_euro)}</dd></div>
        </dl>
        <a href="#/v4/auswertungen/tabelle" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          volle Finanzrechnung (T-Konto) <ArrowRight className="h-4 w-4" />
        </a>
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Das vollständige SOLL/HABEN-T-Konto liegt in Auswertungen/Finanzen (zeitraum-parametrisiert).
        </p>
      </div>
    ),
  }
}

/** Community-Block (O4) — nur wenn Anlagen im Monat vorhanden (data-gated). */
export function communityBlock(
  vergleich: MonatsVergleich,
  d: AktuellerMonatResponse,
  monatName: string,
): Block | null {
  if (!vergleich || vergleich.anzahl_anlagen <= 0) return null
  const zeilen: { label: string; du: number | null | undefined; median: number | null | undefined; unit: string }[] = [
    { label: 'Autarkie',       du: d.autarkie_prozent,            median: vergleich.autarkie?.median,     unit: '%' },
    { label: 'Eigenverbrauch', du: d.eigenverbrauch_quote_prozent, median: vergleich.eigenverbrauch?.median, unit: '%' },
    { label: 'Einspeisung',    du: d.einspeisung_kwh,             median: vergleich.einspeisung?.median,   unit: 'kWh' },
    { label: 'Netzbezug',      du: d.netzbezug_kwh,               median: vergleich.netzbezug?.median,     unit: 'kWh' },
  ]
  const fmt = (v: number | null | undefined, unit: string) => (v == null ? '—' : `${fmtCalc(v, unit === '%' ? 1 : 0)} ${unit}`)
  return {
    id: 'community',
    title: 'Community-Vergleich',
    ...BLOCK_IDENTITAET.community,
    summary: `${vergleich.anzahl_anlagen} Anlage${vergleich.anzahl_anlagen !== 1 ? 'n' : ''} im ${monatName}`,
    defaultOpen: false,
    render: () => (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700">
              <th className="py-1.5 font-medium"><span className="sr-only">Kennzahl</span></th>
              <th className="py-1.5 text-right font-medium">Deine Anlage</th>
              <th className="py-1.5 text-right font-medium">Ø Community (Median)</th>
            </tr>
          </thead>
          <tbody>
            {zeilen.map((z) => (
              <tr key={z.label} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                <td className="py-1.5 text-gray-600 dark:text-gray-400">{z.label}</td>
                <td className="py-1.5 text-right tabular-nums font-semibold text-gray-900 dark:text-white">{fmt(z.du, z.unit)}</td>
                <td className="py-1.5 text-right tabular-nums text-gray-500 dark:text-gray-400">{fmt(z.median, z.unit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
  }
}
