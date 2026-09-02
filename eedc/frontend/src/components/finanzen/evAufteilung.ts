/**
 * evAufteilung — wie sich die Eigenverbrauchs-Ersparnis auf die Komponenten verteilt (SoT).
 *
 * **Warum es diese Datei gibt.** `ev_ersparnis_euro` bewertet den **Bilanz**-
 * Eigenverbrauch der ganzen Anlage. Einzelne Komponenten bekommen daneben eine
 * eigene Zeile (Balkonkraftwerk · Speicher · Wallbox-PV-Ladung) — ihre kWh
 * stecken aber bereits in dieser Summe. Wer beides addiert, zählt dieselbe
 * Kilowattstunde zweimal (#223, und die Klasse aus v4.0.20: 55,9 ct für
 * dieselbe kWh).
 *
 * Das T-Konto zog den Anteil seit jeher ab, die Komponenten-Finanztabelle nicht
 * — **gemeldet von rilmor-mhrs (#402):** *Cockpit → Monat → Finanzen* nannte für
 * die PV-Anlage 267,87 €, das T-Konto 143,51 €. Die Differenz war auf den Cent
 * die Summe seiner drei Komponentenzeilen (BKW 16,53 + Speicher 10,92 + Victron
 * 96,91 = 124,36). Beide Sichten hängen an **derselben** Antwort; sie dürfen
 * sich nicht widersprechen, und die Regel steht deshalb ab jetzt **einmal**.
 *
 * ⛔ **Der sonstige Erzeuger steht bewusst NICHT in dieser Liste** — nicht weil
 * er dazugehören würde, sondern weil er gar keine eigene Ersparnis-Zeile mehr
 * hat: eedc bewertet den Nutzen eines Erzeugers unter *Sonstiges* nicht selbst
 * (N-131, Entscheid 2026-09-01; sein Ertrag wird am Gerät gepflegt). Sein
 * Eigenverbrauch bleibt damit vollständig in der anlagenweiten Zeile — genau
 * das, was deren Formel schon sagt („Eigenverbrauch aus Sonstiges ist hier
 * nicht bewertet"). Käme je wieder eine Gerätezeile dazu, gehörte sie **hier**
 * hinein, sonst entstünde die Doppelzählung an einer neuen Stelle.
 */
import type { AktuellerMonatResponse, InvestitionFinancialDetail } from '../../api/aktuellerMonat'

/**
 * Der Teil von `ev_ersparnis_euro`, der bereits als eigene Komponentenzeile
 * ausgewiesen wird — Balkonkraftwerk, Speicher, PV-Ladung der Wallbox.
 */
export function evInKomponentenzeilen(fins: InvestitionFinancialDetail[]): number {
  return fins
    .filter(inv =>
      inv.typ === 'balkonkraftwerk'
      || inv.typ === 'speicher'
      || (inv.typ === 'wallbox' && inv.ersparnis_label === 'PV-Ladung-Ersparnis')
    )
    .reduce((s, inv) => s + (inv.ersparnis_euro ?? 0), 0)
}

/**
 * Die Eigenverbrauchs-Ersparnis, die der PV-Anlage **allein** zusteht:
 * anlagenweite Ersparnis minus dem, was die Komponentenzeilen schon tragen.
 *
 * Ohne Per-Investition-Daten (`investitionen_financials` leer) gibt es keine
 * Komponentenzeilen — dann ist der volle Betrag der PV-Anteil, und der Aufrufer
 * beschriftet die Zeile entsprechend.
 */
export function pvEigenverbrauchRestEuro(d: AktuellerMonatResponse): number {
  const fins = d.investitionen_financials ?? []
  return Math.max(0, (d.ev_ersparnis_euro ?? 0) - evInKomponentenzeilen(fins))
}
