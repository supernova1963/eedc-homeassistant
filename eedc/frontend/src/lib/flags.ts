/**
 * Build-Feature-Flags (Vite, statisch ersetzt).
 *
 * `IA_V4` schaltet den parallelen IA-v4-Routenbaum (`/v4/…`, eigenes
 * `LayoutV4`) frei — gebaut für die Vorschau gegen die Demo-DB der Dev-Box.
 * Aktivierung über `.env.local` (gitignored): `VITE_IA_V4=true`.
 *
 * WICHTIG (Produktiv-Bitidentität): Vite ersetzt `import.meta.env.VITE_IA_V4`
 * zur Build-Zeit durch ein String-Literal. Ist das Flag nicht gesetzt, wird
 * `IA_V4` zur Konstante `false`. Damit der v4-Code dann auch wirklich aus dem
 * Produktiv-Bundle fällt (keine v4-Chunks), prüft `App.tsx` den `import.meta`-
 * Ausdruck zusätzlich INLINE direkt am `lazy()`-Ternär — cross-module-
 * Const-Folding für Dead-Code-Elimination dynamischer Importe ist nicht
 * garantiert. `IA_V4` hier bleibt der SoT für Komponenten-/Laufzeit-Code.
 */
export const IA_V4 = import.meta.env.VITE_IA_V4 === 'true'

/**
 * `DEMO_DEFAULT` startet datenlose Echtzeit-Sichten (Cockpit/Live) direkt im
 * Demo-Modus + macht den Demo-Schalter sichtbar. Gedacht für die Guest-Box
 * (Tester-Server ohne echte HA-/MQTT-Live-Quelle), gesetzt von
 * `scripts/deploy-guest.sh` (`VITE_DEMO_DEFAULT=true`). Dev-Box/Produktiv lassen
 * es ungesetzt → Live verhält sich wie bisher (Demo nur via `?debug` + Klick).
 */
export const DEMO_DEFAULT = import.meta.env.VITE_DEMO_DEFAULT === 'true'
