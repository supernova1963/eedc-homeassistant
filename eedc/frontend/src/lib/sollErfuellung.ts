/**
 * SOLL-Erfüllung (PVGIS) — EIN Zugriffsweg auf „wie viel Prozent des SOLL sind
 * erreicht?" und auf das Fenster, über das die Zahl gilt (Regel 0a).
 *
 * Hintergrund (N-69, gemessen an Gernots Anlage am 2026-08-04): das Backend
 * lieferte für den laufenden Monat das **volle** Monats-SOLL, daneben stand ein
 * angefangener Ertrag. Cockpit → Monat zeigte am 4. August „19 %", die
 * Jahres-Kachel „104 %" — dieselbe Anlage kam über die abgeschlossenen Monate
 * auf 119 %. Seit dem Entscheid vom 2026-08-04 kürzt das Backend den **Nenner**
 * auf die abgelaufenen Tage (`core/berechnungen/monatsfenster.py`) und legt das
 * Fenster als `soll_pv_tage` / `soll_pv_tage_gesamt` daneben.
 *
 * Folge für die Anzeige: die Prozentzahl stimmt jetzt von selbst, aber die
 * **kWh-Zahl** ist im laufenden Monat kein Monats-SOLL mehr. Wer sie ohne das
 * Fenster hinschreibt, behauptet ein zu niedriges SOLL — deshalb liegt der Text
 * hier und nicht viermal inline (die N-138-Klasse).
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

/** Die Felder, die eine SOLL-Anzeige braucht — Monatszeile oder Jahres-Aggregat. */
export type SollQuelle = Pick<
  AktuellerMonatResponse,
  'soll_pv_kwh' | 'pv_erzeugung_kwh' | 'soll_pv_tage' | 'soll_pv_tage_gesamt'
>

/** Deckt das SOLL nur einen Teil des Zeitraums ab? */
export function istSollAnteilig(d: SollQuelle): boolean {
  return (
    d.soll_pv_tage != null &&
    d.soll_pv_tage_gesamt != null &&
    d.soll_pv_tage < d.soll_pv_tage_gesamt
  )
}

/**
 * SOLL-Erfüllung in Prozent — `null`, wenn kein SOLL vorliegt.
 *
 * Ein SOLL von 0 (Monat in der Zukunft: null abgelaufene Tage) ergibt bewusst
 * `null` statt einer Division: eine Erfüllungsquote für einen Monat, der noch
 * nicht stattgefunden hat, gibt es nicht.
 */
export function sollErfuellungProzent(d: SollQuelle): number | null {
  if (d.soll_pv_kwh == null || d.pv_erzeugung_kwh == null || d.soll_pv_kwh <= 0) return null
  return (d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100
}

/**
 * Das Fenster als Text — `null` bei vollem Zeitraum (dann ist nichts zu sagen).
 *
 * Beispiel: `anteilig · 4 von 31 Tagen`. Im Jahres-Aggregat summieren sich die
 * Tage über die Monate (`216 von 243 Tagen`), weil die SOLL-Summe genauso
 * entsteht.
 */
export function sollFensterText(d: SollQuelle): string | null {
  if (!istSollAnteilig(d)) return null
  return `anteilig · ${d.soll_pv_tage} von ${d.soll_pv_tage_gesamt} Tagen`
}
