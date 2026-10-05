/**
 * Dienstliche Ladekosten — der Hinweis zur Zeile (N-633, 05.10.2026, Wortlaut freigegeben von Gernot).
 *
 * Posten der Ergebnis-Leiter (Stufe 1, −; `core/berechnungen/ergebnis.py::POSTEN`), gebildet in den Monats-Fakten
 * (`EmobFakten.dienstliche_ladekosten_euro`) mit der Formel `core/berechnungen/dienstliche_ladekosten.py`. Die Zeile
 * steht im T-Konto (SOLL) und in der Komponenten-Finanztabelle (Aufwand), jeweils nur, wenn der Betrag ≠ 0 ist.
 *
 * ⚠ Wortgleich mit `DIENSTLICHE_LADEKOSTEN_HINWEIS` im Backend (`core/berechnungen/dienstliche_ladekosten.py`, Monats-
 * und Jahresbericht) — wer den einen Text ändert, ändert den anderen mit (dieselbe Bauform wie #411).
 */
export const DIENSTLICHE_LADEKOSTEN_LABEL = 'Dienstliche Ladekosten'
export const DIENSTLICHE_LADEKOSTEN_HINWEIS =
  'Strom für den Dienstwagen: Netzanteil zum Wallbox-Tarif, PV-Anteil zum Netzbezugspreis. '
  + 'Die Erstattung des Arbeitgebers steht unter den sonstigen Erträgen.'
