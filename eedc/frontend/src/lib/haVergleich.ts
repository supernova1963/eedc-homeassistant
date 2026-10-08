/**
 * N-534 (Frank85, T89667 #349): die Vergleichszeilen des Dialogs „Aus HA laden".
 *
 * Das Backend liefert die Basis-Zählerfelder unter ihrem Datenbanknamen
 * (`einspeisung_kwh`, `netzbezug_kwh` seit v2.5.3, `MAPPING_KEY_TO_DB_FELD`).
 * Der Dialog suchte bis zum 19.09.2026 `einspeisung` und `netzbezug`, fand nie
 * etwas und zeigte bei jedem Anwender „–". Deshalb: eine Zeile je geliefertem
 * Feld, der lokale Wert über denselben Datenbanknamen aus der Monatsdaten-Zeile.
 *
 * N-622 (04.10.2026): den PV-Gesamtzähler lieferte das Backend bis dahin als
 * `pv_gesamt` — sein lokaler Wert stand im Dialog immer als „–", und die
 * Formular-Vorbelegung (`pv_erzeugung_kwh`) blieb leer. Seitdem kommt er als
 * `pv_erzeugung_kwh`; die Proben füttern die Form, die die Route wirklich sendet
 * (`test/ha-monatswerte-n622.fixture.json`, Backend-Gegenstück
 * `test_n622_ha_monatswerte_pv_gesamtzaehler.py`).
 */

export interface HaBasisFeld {
  feld: string
  /** Anzeigename aus dem Backend (`feld_label`); die Formular-Vorbelegung kommt ohne aus. */
  label?: string
  wert: number | null
}

export interface HaBasisZeile {
  feld: string
  label: string
  vorhanden: number | null
  haWert: number | null
}

export function haBasisZeilen(
  basis: HaBasisFeld[],
  vorhandene: Record<string, unknown> | null | undefined,
): HaBasisZeile[] {
  return basis.map((b) => {
    const v = vorhandene ? vorhandene[b.feld] : undefined
    return {
      feld: b.feld,
      label: b.label ?? b.feld,
      vorhanden: typeof v === 'number' ? v : null,
      haWert: b.wert ?? null,
    }
  })
}

/** Der HA-Wert eines Basisfelds für die Formular-Vorbelegung — leer, wenn nicht geliefert. */
export function haBasisWert(basis: HaBasisFeld[] | undefined | null, feld: string): string {
  const found = basis?.find((b) => b.feld === feld)
  return found?.wert !== null && found?.wert !== undefined ? found.wert.toString() : ''
}

/**
 * N-639 (Frank85, 08.10.2026): die Felder, für die Home Assistant im Monat einen NEGATIVEN Wert liefert — die Summe
 * des Sensors ist in der Langzeitstatistik gefallen (Anpassung nach unten). eedc rechnet wie das HA-Energie-Dashboard
 * und übernimmt den Rückgang; der Vergleichsdialog nennt die Felder und den Weg (Daten-Checker „Zählerstände – Rückgang
 * in Home Assistant", `daten_checker/datenquelle/ha_rueckgang.py`). Komponentenfelder mit Gerätenamen davor.
 */
export function haNegativeFelder(werte: {
  basis: HaBasisFeld[]
  investitionen: { bezeichnung: string; felder: HaBasisFeld[] }[]
}): string[] {
  const negativ = (f: HaBasisFeld) => typeof f.wert === 'number' && f.wert < 0
  return [
    ...werte.basis.filter(negativ).map((f) => f.label ?? f.feld),
    ...werte.investitionen.flatMap((inv) =>
      inv.felder.filter(negativ).map((f) => `${inv.bezeichnung}: ${f.label ?? f.feld}`),
    ),
  ]
}

/** Der Hinweis im Vergleichsdialog — Kurzform der Daten-Checker-Meldung (N-639). */
export const HA_RUECKGANG_HINWEIS =
  'Home Assistant liefert hier einen negativen Wert: Die Summe des Sensors ist in der Langzeitstatistik von Home ' +
  'Assistant in diesem Monat gefallen, statt zu steigen — meist nach einer Anpassung nach unten. Korrigieren kannst ' +
  'du das in Home Assistant unter Entwicklerwerkzeuge → Statistik → beim Sensor „Wert anpassen“; eedc gleicht die ' +
  'korrigierte Statistik nachts von selbst ab, danach lädst du den Monat neu. Tag und Stunde nennt der Daten-Checker ' +
  '(„Zählerstände – Rückgang in Home Assistant“).'
