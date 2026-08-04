/**
 * GrundlastSollIstKachel — rechte Kachel im „Energie-Bilanz"-Block von
 * Cockpit/Monat + Jahr-Gesamt (eine SoT-Komponente für beide Sichten).
 *
 * R12-1 (Tester rapahl): Der PVGIS-SOLL/IST-Vergleich („Maximum des Erreichbaren")
 * wird durch die verbrauchsnahe **Grundlast** (Nacht-Sockel) ersetzt — absolut
 * (W/kW) + Anteil am Gesamtverbrauch. Median wie der Live-Wert (siehe Backend
 * `core/berechnungen/grundlast.py`).
 *
 * Fallback: liegen keine Stundenprofile vor (`grundlast_kw == null`), bleibt die
 * bisherige PVGIS-SOLL/IST-Anzeige erhalten (Gernot-Entscheid 2026-06-30).
 *
 * Farbe Grundlast = Verbrauchs-Rolle (`energy-consumption`, Regel 0a); der PVGIS-
 * Fallback behält die SOLL/IST-Ampel.
 *
 * R3b S6 (2026-07-05): der präsentationale Kern ist als {@link BilanzKachel}
 * exportiert — EINE Kachel-Klasse (uppercase-Label mit FormelTooltip +
 * rechtsbündiger Hero-Wert + optionaler Balken + Subtitle) für Monat/Jahr UND
 * die Tag-PR-Ampel (TagBilanz), statt Markup-Kopien je Sicht.
 */
import type { ReactNode } from 'react'
import FormelTooltip from '../ui/FormelTooltip'
import { fmtCalc } from '../ui'
import { AMPEL_TEXT_CLASS, AMPEL_BG_CLASS, sollIstStufe } from '../../lib'
import { sollErfuellungProzent, sollFensterText } from '../../lib/sollErfuellung'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

/** Absolut hübsch: < 1 kW → W (wie Live „380 W"), sonst kW. */
function fmtGrundlast(kw: number): string {
  return kw < 1 ? `${fmtCalc(kw * 1000, 0)} W` : `${fmtCalc(kw, 2)} kW`
}

/** Präsentationaler Kachel-Kern (R3b S6) — Wert-Färbung IMMER als Klasse
 *  (`wertClass`, z. B. AMPEL_TEXT_CLASS[stufe]), nie als Inline-Hex (Regel G/A8). */
export function BilanzKachel({
  label, formel, berechnung, ergebnis, wert, wertClass, balken, subtitle, subtitleRechts,
}: {
  label: string
  formel: string
  berechnung?: string
  ergebnis?: string
  wert: string
  wertClass: string
  /** optionaler Fortschritts-Balken (PR-Kachel hat keinen). */
  balken?: { pct: number; bgClass: string }
  subtitle?: ReactNode
  /** Subtitle rechtsbündig (unter dem rechtsbündigen Wert, Tag-PR). */
  subtitleRechts?: boolean
}) {
  return (
    <>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
        <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>
          {label}
        </FormelTooltip>
      </p>
      <div className="flex justify-end">
        <span className={`text-3xl font-bold ${wertClass}`}>{wert}</span>
      </div>
      {balken && (
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-2 mt-2">
          <div className={`h-2 rounded-sm ${balken.bgClass}`} style={{ width: `${Math.min(100, balken.pct)}%` }} />
        </div>
      )}
      {subtitle != null && (
        <p className={`text-xs text-gray-500 dark:text-gray-400 mt-1.5${subtitleRechts ? ' text-right' : ''}`}>
          {subtitle}
        </p>
      )}
    </>
  )
}

export function GrundlastSollIstKachel({ d }: { d: AktuellerMonatResponse }) {
  // R12-1: Grundlast (Nacht-Sockel) — sobald Stundendaten vorliegen.
  if (d.grundlast_kw != null) {
    const anteil = d.grundlast_anteil_prozent
    return (
      <BilanzKachel
        label="Grundlast (Nacht-Sockel)"
        formel="Median der Nacht-Stunden-Leistung (0–5 Uhr)"
        berechnung={d.grundlast_kwh != null ? `≈ ${fmt(d.grundlast_kwh)} kWh Dauerlast im Zeitraum` : undefined}
        ergebnis={anteil != null ? `= ${fmt(anteil, 1)} % vom Gesamtverbrauch` : undefined}
        wert={fmtGrundlast(d.grundlast_kw)}
        wertClass="text-energy-consumption"
        balken={anteil != null ? { pct: anteil, bgClass: 'bg-energy-consumption' } : undefined}
        subtitle={anteil != null
          ? <>
              {fmt(anteil, 1)} % vom Gesamtverbrauch
              {d.grundlast_kwh != null && d.gesamtverbrauch_kwh != null
                ? ` · ${fmt(d.grundlast_kwh)} von ${fmt(d.gesamtverbrauch_kwh)} kWh`
                : ''}
            </>
          : undefined}
      />
    )
  }

  // Fallback: PVGIS-SOLL/IST, wenn keine Stundenprofile vorliegen. Der SOLL-Wert
  // trägt im laufenden Monat nur die abgelaufenen Tage (N-69) — deshalb benennt
  // die Kachel ihr Fenster, sonst läse man die gekürzte kWh-Zahl als Monats-SOLL.
  const sollRoh = sollErfuellungProzent(d)
  const sollPct = sollRoh != null ? Math.round(sollRoh) : null
  const sollFenster = sollFensterText(d)
  if (sollPct == null) {
    return <p className="text-xs text-gray-400 dark:text-gray-500">Keine Grundlast- oder PVGIS-Daten für diesen Zeitraum.</p>
  }
  const stufe = sollIstStufe(sollPct)
  return (
    <BilanzKachel
      label="IST/SOLL (PVGIS)"
      formel="IST ÷ SOLL × 100"
      berechnung={d.pv_erzeugung_kwh != null && d.soll_pv_kwh != null
        ? `${fmt(d.pv_erzeugung_kwh)} ÷ ${fmt(d.soll_pv_kwh)} kWh${sollFenster ? ` (${sollFenster})` : ''}`
        : undefined}
      ergebnis={`= ${fmt(sollPct)} %`}
      wert={`${fmt(sollPct)} %`}
      wertClass={AMPEL_TEXT_CLASS[stufe]}
      balken={{ pct: sollPct, bgClass: AMPEL_BG_CLASS[stufe] }}
      subtitle={<>{fmt(d.pv_erzeugung_kwh)} von {fmt(d.soll_pv_kwh)} kWh{sollFenster ? ` (${sollFenster})` : ''}</>}
    />
  )
}
