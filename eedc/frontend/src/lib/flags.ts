/**
 * Build-Feature-Flags (Vite, statisch ersetzt).
 *
 * `DEMO_DEFAULT` ist das einzig verbliebene Flag (der frühere `IA_V4`-Vorschau-
 * Schalter ist mit dem v4.0.0-Flip entfallen — IA-V4 ist jetzt die kanonische
 * und einzige Oberfläche).
 */

/**
 * `DEMO_DEFAULT` startet datenlose Echtzeit-Sichten (Cockpit/Live) direkt im
 * Demo-Modus + macht den Demo-Schalter sichtbar. Gedacht für Builds ohne echte
 * HA-/MQTT-Live-Quelle: die **Dev-Box** (Rebuild immer mit `VITE_DEMO_DEFAULT=true`)
 * und `npm run check:park-leertest`, der ohne das Flag keine Live-Sichten prüfen
 * kann. Produktiv bleibt es ungesetzt → Live verhält sich wie bisher (Demo nur via
 * `?debug` + Klick). Der frühere Setzer `scripts/deploy-guest.sh` ist mit der
 * Stilllegung der Guest-Box (2026-07) entfallen.
 */
export const DEMO_DEFAULT = import.meta.env.VITE_DEMO_DEFAULT === 'true'
