/**
 * LadestandLeiste — der Ladestand eines Fahrzeugs als Balken mit Zielmarke (P-433-2b K1, Blatt §1a: Matheks
 * Verbraucher-Karte #433 «Akku 64 % · Ziel 80 %», vehicle-status-card).
 *
 * SoT-Komponente (Style-Guide Regel 0a): eine Leiste für die Fahrzeugzeile der Wallbox-Karte und die Hauptzahl der
 * Auto-Karte im Hub-Überblick. **Reine Anzeige** — Ladestand und Ziel kommen fertig vom Backend (`LiveFahrzeug.soc`,
 * `ziel_prozent`), hier wird nur auf 0–100 geklemmt und positioniert. Ohne Ziel keine Marke.
 *
 * Farbe = Rolle: die Füllung trägt die Komponenten-Farbe des E-Autos (`KOMPONENTEN_FARBEN['e-auto']`), die Marke ist
 * neutral; keine Ampel nach Ladestand.
 */
import { KOMPONENTEN_FARBEN, fmtZahl } from '../../lib'

export interface LadestandLeisteProps {
  /** Ladestand in % (0–100). */
  soc: number
  /** Ladeziel in % — gesetzt ⇒ Zielmarke mit «Ziel 80 %». */
  ziel?: number | null
}

const klemme = (v: number) => Math.min(100, Math.max(0, v))

export default function LadestandLeiste({ soc, ziel = null }: LadestandLeisteProps) {
  return (
    <div className="space-y-0.5" data-ladestand-leiste>
      <div
        className="relative h-2 rounded-full bg-gray-200 dark:bg-gray-700"
        role="img" aria-label={`Ladestand ${fmtZahl(soc, 0)} %${ziel != null ? `, Ziel ${fmtZahl(ziel, 0)} %` : ''}`}
      >
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${KOMPONENTEN_FARBEN['e-auto'].bg}`}
          style={{ width: `${klemme(soc)}%` }}
          data-ladestand-fuellung
        />
        {ziel != null && (
          <div
            className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-gray-700 dark:bg-gray-200"
            style={{ left: `calc(${klemme(ziel)}% - 1px)` }} /* de-de-allow: CSS-Position, keine Anzeige */
            title={`Ziel ${fmtZahl(ziel, 0)} %`}
            data-zielmarke
          />
        )}
      </div>
      {ziel != null && (
        <div className="text-right text-xs text-gray-500 dark:text-gray-400" data-ziel-text>Ziel {fmtZahl(ziel, 0)} %</div>
      )}
    </div>
  )
}
