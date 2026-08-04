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
import { ArrowRight, CalendarClock } from 'lucide-react'
import { ReloadButton } from './ReloadButton'
import { fmtCalc } from '../components/ui'
import { Table, TableHead, TableBody } from '../components/ui/Table'
import { ZELLE, KOPF_ZELLE } from '../components/ui/tabelleMasse'
import { KomponentenFinanzTabelle, komponentenFinanzSaldo } from '../components/finanzen/KomponentenFinanzTabelle'
import { BLOCK_IDENTITAET, VERGLEICH_BADGE, LAUFEND_ZUSTAND } from '../lib'
import type { Block } from '../components/blocks'
import { Parkbar, NOOP_PARK, type ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { MonatsVergleich } from '../api/community'
import { provenanzQuellen, ProvenanzQuellenZeile } from './ProvenanzQuellen'

const euro = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${fmtCalc(v, 2)} €`)

export function MonatHeader({ titel, laufend, d, onReload, reloading, zeigeAbschlussLink }: {
  titel: string
  laufend: boolean
  d: AktuellerMonatResponse | null
  /** C1: Aktualisieren-Aktion (nur laufender Monat); fehlt → Button entfällt. */
  onReload?: () => void
  reloading?: boolean
  /** C2: „Abschluss starten"-Cross-Link zeigen (laufend + offene Vergangenheits-Monate). */
  zeigeAbschlussLink?: boolean
}) {
  // #360: der Connector nennt seinen Zeitraum. Deckt sein Delta den Monat nicht
  // ab dem Ersten ab, misst der Wert nur ein Bruchstück (coolxmad #353: 51,3 statt
  // 996 kWh) — er steht seit `2cc1dfa2` keinem gespeicherten Wert mehr im Weg,
  // stand aber weiter unbeschriftet da. Der Monatskontext kommt aus der Antwort,
  // die Tage rechnet der Client (kein zweites Backend-Feld dafür).
  const monat = d ? { start: new Date(d.jahr, d.monat - 1, 1), tage: new Date(d.jahr, d.monat, 0).getDate() } : undefined
  const quellen = d ? provenanzQuellen(d.feld_quellen, monat) : []
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{titel}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? LAUFEND_ZUSTAND.badge
            : 'bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'läuft' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {/* C1: Aktualisieren — nur im laufenden Monat (IST-Parität MonatsabschlussView). */}
        {laufend && onReload && <ReloadButton onClick={onReload} loading={!!reloading} />}
        {/* C2: Cross-Link zu Einstellungen/Daten (Abschluss) statt Inline-Wizard (B5/SPEC). */}
        {laufend && zeigeAbschlussLink && (
          <a
            href="#/einstellungen/daten"
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
          >
            <CalendarClock className="h-3.5 w-3.5" />
            Abschluss starten
          </a>
        )}
        <ProvenanzQuellenZeile quellen={quellen} />
      </div>
    </div>
  )
}

/** Finanz-Teaser (B5 → G20-1): Komponenten-Finanz-Tabelle + Cross-Link nach
 *  Auswertungen. Kopf-Kennzahl = Tabellen-Saldo (Kopf == sichtbare Summe). Die
 *  ct/kWh-Tarif-Zeile ist eine ANNOTATION zur Bilanz und parkt MIT ihr (Gernot
 *  2026-07-09). Sind alle geparkt → kein Block (`null`). */
export function finanzTeaserBlock(d: AktuellerMonatResponse, park: ParkApi = NOOP_PARK, zeitraum: 'monat' | 'jahr' = 'monat'): Block | null {
  const hatTarif = d.netzbezug_durchschnittspreis_cent != null || d.netzbezug_preis_cent != null || d.einspeise_preis_cent != null
  const ids = ['el:finanzen-bilanz', 'el:finanzen-link']
  if (ids.every((id) => park.istGeparkt(id))) return null
  // G20-1: Kopf-Kennzahl = der Tabellen-Saldo (nicht die kanonische netto_ertrag —
  // die Tabelle ist eine komponenten-attribuierte Sicht; Kopf == sichtbare Summe).
  const saldo = komponentenFinanzSaldo(d)
  return {
    id: 'finanzen',
    title: 'Finanzen',
    ...BLOCK_IDENTITAET.finanzen,
    summary: `${euro(saldo)} Saldo`,
    defaultOpen: false,
    render: () => (
      <div className="space-y-3">
        {/* G20-1: Komponenten-Finanz-Tabelle (1 Zeile je Komponente, Spalten
            Erträge/Einsparungen/Aufwand/Saldo) + Tarif-Info in EINER Parkbar. */}
        <Parkbar id="el:finanzen-bilanz" titel="Finanz-Bilanz">
          <KomponentenFinanzTabelle d={d} zeitraum={zeitraum} />
          {/* C3: Tarif-Info-Zeile (Begleit-Info zur Bilanz, IST-Parität). */}
          {hatTarif && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500 mt-2">
              {/* E4 (R3b, Regel-0a-STUFE-3-AUSNAHME, Gernot 2026-07-05): der flexible
                  Ø-Netzbezugspreis wird bewusst BLAU hervorgehoben (Hinweis „dynamischer
                  Tarif aktiv"), obwohl die Strompreis-Rolle Purple ist — dokumentierte
                  Ausnahme (Style-Guide-Ausnahmen-Liste); Zwilling in finanzen/TKonto.tsx. */}
              {d.netzbezug_durchschnittspreis_cent != null
                ? <span>Netzbezug Ø <span className="text-blue-500 dark:text-blue-400 font-medium">{fmtCalc(d.netzbezug_durchschnittspreis_cent, 2)} ct/kWh</span> (flex)</span>
                : d.netzbezug_preis_cent != null && <span>Netzbezug {fmtCalc(d.netzbezug_preis_cent, 2)} ct/kWh</span>}
              {d.einspeise_preis_cent != null && <span>Einspeisung {fmtCalc(d.einspeise_preis_cent, 2)} ct/kWh</span>}
            </div>
          )}
        </Parkbar>
        <Parkbar id="el:finanzen-link" titel="Cross-Link Finanzrechnung">
          <div className="space-y-3">
            <a href="#/auswertungen/finanzen" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
              volle Finanzrechnung (T-Konto) <ArrowRight className="h-4 w-4" />
            </a>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Das vollständige SOLL/HABEN-T-Konto liegt in Auswertungen/Finanzen (zeitraum-parametrisiert).
            </p>
          </div>
        </Parkbar>
      </div>
    ),
  }
}

/** Community-Block (O4) — nur wenn Anlagen im Monat vorhanden (data-gated). */
export function communityBlock(
  vergleich: MonatsVergleich,
  d: AktuellerMonatResponse,
  monatName: string,
  jahr: number,
): Block | null {
  if (!vergleich || vergleich.anzahl_anlagen <= 0) return null
  const anlagenWort = `${vergleich.anzahl_anlagen} Anlage${vergleich.anzahl_anlagen !== 1 ? 'n' : ''}`
  // Spez.-Ertrag-Abweichung zum Community-Median — periodenkorrekt (Monats-Median),
  // gleiche Basis wie der Vergleich (anlage.leistung_kwp). KEIN periodenfalscher Rang;
  // ein echter periodenbezogener Rang ist als eedc-community-Erweiterung getrackt (#338).
  const eigenSpez = d.spez_ertrag
  const medianSpez = vergleich.spez_ertrag?.median
  const vz = (v: number) => (v > 0 ? '+' : '')
  const spezText =
    eigenSpez != null && medianSpez != null && medianSpez > 0
      ? ` · spez. Ertrag ${fmtCalc(eigenSpez, 0)} kWh/kWp (${vz(eigenSpez - medianSpez)}${fmtCalc(eigenSpez - medianSpez, 0)} / ${vz(((eigenSpez - medianSpez) / medianSpez) * 100)}${fmtCalc(((eigenSpez - medianSpez) / medianSpez) * 100, 0)} % vs. Median)`
      : ''
  // inv = „niedriger ist besser" (nur Netzbezug); steuert das ▲▼-Vergleichs-Badge (A2, wie IST).
  // B2/S14 (R3b E2): transponierte Tabelle → Einheit genau EINMAL je Zeile am
  // Zeilen-Label „Kennzahl (Einheit)", nicht in jeder Wertzelle (`unit` bleibt
  // für die Dezimal-Logik erhalten).
  const zeilen: { label: string; du: number | null | undefined; median: number | null | undefined; unit: string; inv?: boolean }[] = [
    { label: 'Autarkie (%)',        du: d.autarkie_prozent,            median: vergleich.autarkie?.median,     unit: '%' },
    { label: 'Eigenverbrauch (%)',  du: d.eigenverbrauch_quote_prozent, median: vergleich.eigenverbrauch?.median, unit: '%' },
    { label: 'Einspeisung (kWh)',   du: d.einspeisung_kwh,             median: vergleich.einspeisung?.median,   unit: 'kWh' },
    { label: 'Netzbezug (kWh)',     du: d.netzbezug_kwh,               median: vergleich.netzbezug?.median,     unit: 'kWh', inv: true },
  ]
  const fmt = (v: number | null | undefined, unit: string) => (v == null ? '—' : fmtCalc(v, unit === '%' ? 1 : 0))
  return {
    id: 'community',
    title: 'Community-Vergleich',
    ...BLOCK_IDENTITAET.community,
    summary: `${anlagenWort} im ${monatName}${spezText}`,
    defaultOpen: false,
    render: () => (
      <Parkbar id="el:community-tabelle" titel="Community-Vergleich">
      <Table flaeche="karte">
          <TableHead>
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              <th className={`${KOPF_ZELLE} text-left`}><span className="sr-only">Kennzahl</span></th>
              <th className={`${KOPF_ZELLE} text-right`}>Deine Anlage</th>
              <th className={`${KOPF_ZELLE} text-right`}>Ø Community (Median)</th>
              <th className={`${KOPF_ZELLE} text-right`}><span className="sr-only">Vergleich</span></th>
            </tr>
          </TableHead>
          <TableBody>
            {zeilen.map((z) => (
              <tr key={z.label} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                <td className={`${ZELLE} text-gray-600 dark:text-gray-400`}>{z.label}</td>
                <td className={`${ZELLE} text-right tabular-nums font-semibold text-gray-900 dark:text-white`}>{fmt(z.du, z.unit)}</td>
                <td className={`${ZELLE} text-right tabular-nums text-gray-500 dark:text-gray-400`}>{fmt(z.median, z.unit)}</td>
                <td className={`${ZELLE} text-right`}>
                  {z.du != null && z.median != null && (() => {
                    const better = z.inv ? z.du <= z.median : z.du >= z.median
                    return (
                      <span className={`text-xs font-medium px-1 py-0.5 rounded-full ${
                        better ? VERGLEICH_BADGE.besser : VERGLEICH_BADGE.schlechter
                      }`}>
                        {better ? '▲' : '▼'}
                      </span>
                    )
                  })()}
                </td>
              </tr>
            ))}
          </TableBody>
        </Table>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
          Basis: {anlagenWort} · {monatName} {jahr}
        </p>
      </Parkbar>
    ),
  }
}
