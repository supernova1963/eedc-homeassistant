/**
 * Build-Feature-Flags (Vite, statisch ersetzt).
 *
 * `DEMO_DEFAULT` ist das einzig verbliebene Flag (der frühere `IA_V4`-Vorschau-
 * Schalter ist mit dem v4.0.0-Flip entfallen — IA-V4 ist jetzt die kanonische
 * und einzige Oberfläche).
 */

/**
 * `DEMO_DEFAULT` startet datenlose Echtzeit-Sichten (Cockpit/Live) direkt im
 * Demo-Modus + macht den Demo-Schalter sichtbar. Gedacht für die Guest-Box
 * (Tester-Server ohne echte HA-/MQTT-Live-Quelle), gesetzt von
 * `scripts/deploy-guest.sh` (`VITE_DEMO_DEFAULT=true`). Dev-Box/Produktiv lassen
 * es ungesetzt → Live verhält sich wie bisher (Demo nur via `?debug` + Klick).
 */
export const DEMO_DEFAULT = import.meta.env.VITE_DEMO_DEFAULT === 'true'
