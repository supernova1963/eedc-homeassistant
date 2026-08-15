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
  | 'soll_pv_kwh_monat'
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

/**
 * Das SOLL des **ganzen** Monats — die Zahl, die vor N-69 in der Kachel stand.
 *
 * Melder dietmar1968 (T89667 #155, 14.08.2026): *„Deshalb fand ich den
 * Fortschrittsbalken in Bezug auf die gesamte Monatsprognose extrem hilfreich.
 * Leider wurde dies verändert."* N-69 hat den Nenner bewusst auf die
 * abgelaufenen Tage gekürzt (die Quote stimmte vorher nicht) — die **Frage**
 * dahinter ist damit aber nicht falsch geworden, sie hat nur keine Anzeige mehr.
 *
 * Die Zahl kommt **fertig aus derselben Antwort** (`soll_pv_kwh_monat`) und
 * wird hier nicht zurückgerechnet. Rechnerisch ginge das — die Kürzung ist
 * linear (`core/berechnungen/monatsfenster.py::anteilig` = `wert × tage ÷
 * tage_gesamt`) —, aber `soll_pv_kwh` wird **auf eine Stelle gerundet**
 * ausgeliefert, und die Umkehrung multipliziert diesen Rest mit
 * `tage_gesamt ÷ tage`: am 4. August wurde aus 1387,9 so 1388,0, am
 * Monatsersten wäre es das 28- bis 31-Fache des Rundungsrests. Ein
 * zusätzlicher Abruf entsteht dadurch nicht — nur ein Feld mehr in derselben
 * Antwort.
 *
 * `null`, wenn kein SOLL vorliegt (auch im Jahres-Aggregat, das die Größe nicht
 * trägt) — ein „Monat" ist dort nicht definiert.
 */
export function sollMonatGesamtKwh(d: SollQuelle): number | null {
  return d.soll_pv_kwh_monat ?? null
}

/**
 * Erreichter Anteil der **vollen Monatsprognose** in Prozent.
 *
 * Bewusst eine zweite Größe neben {@link sollErfuellungProzent} und keine
 * Ablösung: die eine beantwortet „liefert die Anlage, was sie bis heute
 * liefern sollte?", die andere „wie weit ist der Monat?". Beide tragen in der
 * Anzeige ihr Fenster im Untertitel, sonst stünden zwei Prozentzahlen ohne
 * Unterschied nebeneinander.
 */
export function sollErfuellungMonatProzent(d: SollQuelle): number | null {
  const gesamt = sollMonatGesamtKwh(d)
  if (gesamt == null || gesamt <= 0 || d.pv_erzeugung_kwh == null) return null
  return (d.pv_erzeugung_kwh / gesamt) * 100
}

/**
 * Hat die Monatsprognose-Anzeige etwas zu sagen? **Ein** Gate für zwei
 * Aufrufer — die Kachel selbst und die Park-ID-Liste des Bilanz-Blocks
 * (`v4/bilanzParkIds`). Stünde die Bedingung zweimal da, könnte der Block auf
 * das Parken eines Elements warten, das gar nicht gerendert wird.
 *
 * Nur im **angefangenen** Monat: im abgeschlossenen sind „bis heute" und
 * „ganzer Monat" dieselbe Zahl.
 */
export function zeigeMonatsprognose(d: SollQuelle): boolean {
  return istSollAnteilig(d) && sollErfuellungMonatProzent(d) != null
}

