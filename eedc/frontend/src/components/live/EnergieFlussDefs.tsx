/**
 * EnergieFlussDefs — die SVG-Filter der Energiefluss-Kachel, EINMAL definiert
 * (P-433-2, Nacharbeit S1).
 *
 * `EnergieFlussKachel` verweist auf `url(#ef-icon-glow)` (Icon-Schein, nur im
 * Effekt-Modus) und `url(#ef-card-shadow)` (Schlagschatten, nur ohne Lite).
 * Jede Fläche, die die Kachel zeichnet, rendert diese Filter in ihre `<defs>`:
 * der Energiefluss über `EnergieFlussBackground`, der Hub-Block «Überblick»
 * über `UeberblickSchaubild`. Werte 1:1 aus dem Energiefluss übernommen
 * (Lite: No-Op-Filter ohne Blur, Performance).
 *
 * Gibt ein Fragment zurück — der Aufrufer stellt die `<defs>`.
 */
import { ENERGIEFLUSS_KACHEL_SCHATTEN } from '../../lib'

export default function EnergieFlussDefs({ lite }: { lite: boolean }) {
  if (lite) {
    return (
      <>
        <filter id="ef-icon-glow"><feOffset dx="0" dy="0" /></filter>
        <filter id="ef-card-shadow"><feOffset dx="0" dy="0" /></filter>
      </>
    )
  }
  return (
    <>
      {/* Glow-Filter für Icons */}
      <filter id="ef-icon-glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur in="SourceGraphic" stdDeviation="3" />
      </filter>

      {/* Schatten für Knoten-Karten */}
      <filter id="ef-card-shadow" x="-10%" y="-10%" width="130%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor={ENERGIEFLUSS_KACHEL_SCHATTEN} floodOpacity="0.15" />
      </filter>
    </>
  )
}
