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
 *
 * ⭐ **Seit 03.10.2026 rechnet diese Datei nicht mehr** (N-356): Quote, Monats-Quote und Fenstertext kommen fertig
 * aus der Antwort (`soll_erfuellung_prozent`, `soll_erfuellung_monat_prozent`, `soll_fenster_text` — Backend-Layer
 * `core/berechnungen/ergebnis.py::soll_erfuellung`, Monat UND Jahr). Bis dahin stand dieselbe Rechnung hier und
 * als „Spiegel" im PDF-Monatsbericht — zwei Bildungsstellen, deren Wächter von Hand mitkopiert waren. Die
 * Funktionen bleiben als **Leser** mit unveränderten Signaturen, damit die Aufrufer (Kacheln, Park-IDs) nicht
 * wissen müssen, woher die Zahl kommt.
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

/** Die Felder, die eine SOLL-Anzeige braucht — Monatszeile oder Jahres-Aggregat. */
export type SollQuelle = Pick<
  AktuellerMonatResponse,
  'soll_pv_kwh' | 'pv_erzeugung_kwh' | 'soll_pv_tage' | 'soll_pv_tage_gesamt'
  | 'soll_pv_kwh_monat' | 'soll_erfuellung_prozent' | 'soll_erfuellung_monat_prozent' | 'soll_fenster_text'
>

/** Deckt das SOLL nur einen Teil des Zeitraums ab? (Der Fenstertext ist genau dann gesetzt.) */
export function istSollAnteilig(d: SollQuelle): boolean {
  return d.soll_fenster_text != null
}

/**
 * SOLL-Erfüllung in Prozent — `null`, wenn kein SOLL vorliegt (auch bei SOLL 0: ein Monat, der noch nicht
 * stattgefunden hat, hat keine Erfüllungsquote). Wert aus der Antwort.
 */
export function sollErfuellungProzent(d: SollQuelle): number | null {
  return d.soll_erfuellung_prozent ?? null
}

/**
 * Das Fenster als Text — `null` bei vollem Zeitraum. Beispiel: `anteilig · 4 von 31 Tagen`; im Jahr summieren sich
 * die Tage über die Monate (`216 von 243 Tagen`). Text aus der Antwort.
 */
export function sollFensterText(d: SollQuelle): string | null {
  return d.soll_fenster_text ?? null
}

/**
 * Das SOLL des **ganzen** Monats — die Zahl, die vor N-69 in der Kachel stand (dietmar1968, T89667 #155). Kommt
 * fertig aus der Antwort (`soll_pv_kwh_monat`) und wird nicht aus `soll_pv_kwh` zurückgerechnet (Rundung × Tage).
 * `null` im Jahres-Aggregat — ein „Monat" ist dort nicht definiert.
 */
export function sollMonatGesamtKwh(d: SollQuelle): number | null {
  return d.soll_pv_kwh_monat ?? null
}

/**
 * Erreichter Anteil der **vollen Monatsprognose** in Prozent — bewusst eine zweite Größe neben
 * {@link sollErfuellungProzent} („liefert die Anlage, was sie bis heute liefern sollte?" vs. „wie weit ist der
 * Monat?"). Wert aus der Antwort.
 */
export function sollErfuellungMonatProzent(d: SollQuelle): number | null {
  return d.soll_erfuellung_monat_prozent ?? null
}

/**
 * Hat die Monatsprognose-Anzeige etwas zu sagen? **Ein** Gate für zwei Aufrufer — die Kachel selbst und die
 * Park-ID-Liste des Bilanz-Blocks (`v4/bilanzParkIds`). Nur im **angefangenen** Monat.
 */
export function zeigeMonatsprognose(d: SollQuelle): boolean {
  return istSollAnteilig(d) && sollErfuellungMonatProzent(d) != null
}
