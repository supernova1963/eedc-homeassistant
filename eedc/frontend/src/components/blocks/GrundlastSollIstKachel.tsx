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
 */
import FormelTooltip from '../ui/FormelTooltip'
import { fmtCalc } from '../ui'
import { AMPEL_TEXT_CLASS, AMPEL_BG_CLASS, sollIstStufe } from '../../lib'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

/** Absolut hübsch: < 1 kW → W (wie Live „380 W"), sonst kW. */
function fmtGrundlast(kw: number): string {
  return kw < 1 ? `${fmtCalc(kw * 1000, 0)} W` : `${fmtCalc(kw, 2)} kW`
}

export function GrundlastSollIstKachel({ d }: { d: AktuellerMonatResponse }) {
  // R12-1: Grundlast (Nacht-Sockel) — sobald Stundendaten vorliegen.
  if (d.grundlast_kw != null) {
    const anteil = d.grundlast_anteil_prozent
    return (
      <>
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
          <FormelTooltip
            formel="Median der Nacht-Stunden-Leistung (0–5 Uhr)"
            berechnung={d.grundlast_kwh != null ? `≈ ${fmt(d.grundlast_kwh)} kWh Dauerlast im Zeitraum` : undefined}
            ergebnis={anteil != null ? `= ${fmt(anteil, 1)} % vom Gesamtverbrauch` : undefined}
          >
            Grundlast (Nacht-Sockel)
          </FormelTooltip>
        </p>
        <div className="flex justify-end">
          <span className="text-3xl font-bold text-energy-consumption">{fmtGrundlast(d.grundlast_kw)}</span>
        </div>
        {anteil != null && (
          <>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-2 mt-2">
              <div className="h-2 rounded-sm bg-energy-consumption" style={{ width: `${Math.min(100, anteil)}%` }} />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
              {fmt(anteil, 1)} % vom Gesamtverbrauch
              {d.grundlast_kwh != null && d.gesamtverbrauch_kwh != null
                ? ` · ${fmt(d.grundlast_kwh)} von ${fmt(d.gesamtverbrauch_kwh)} kWh`
                : ''}
            </p>
          </>
        )}
      </>
    )
  }

  // Fallback: PVGIS-SOLL/IST (unverändert), wenn keine Stundenprofile vorliegen.
  const sollPct = d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && d.soll_pv_kwh > 0
    ? Math.round((d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100)
    : null
  if (sollPct == null) {
    return <p className="text-xs text-gray-400 dark:text-gray-500">Keine Grundlast- oder PVGIS-Daten für diesen Zeitraum.</p>
  }
  return (
    <>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
        <FormelTooltip
          formel="IST ÷ SOLL × 100"
          berechnung={d.pv_erzeugung_kwh != null && d.soll_pv_kwh != null ? `${fmt(d.pv_erzeugung_kwh)} ÷ ${fmt(d.soll_pv_kwh)} kWh` : undefined}
          ergebnis={`= ${fmt(sollPct)} %`}
        >
          IST/SOLL (PVGIS)
        </FormelTooltip>
      </p>
      <div className="flex justify-end">
        <span className={`text-3xl font-bold ${AMPEL_TEXT_CLASS[sollIstStufe(sollPct)]}`}>{fmt(sollPct)} %</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-2 mt-2">
        <div
          className={`h-2 rounded-sm ${AMPEL_BG_CLASS[sollIstStufe(sollPct)]}`}
          style={{ width: `${Math.min(100, sollPct)}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
        {fmt(d.pv_erzeugung_kwh)} von {fmt(d.soll_pv_kwh)} kWh
      </p>
    </>
  )
}
