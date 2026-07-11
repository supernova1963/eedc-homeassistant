#!/usr/bin/env node
/**
 * check-buttons.mjs — B15-Button-SoT-Gate (Style-Guide B15, R3b Etappe 2, 2026-07-05).
 *
 * Regel: keine Ad-hoc-`<button>` mit eigenem Styling in v4-Sichten — Aktions-Buttons
 * über `ui/Button` (bzw. `buttonClasses`), Segment-Gruppen über `ui/SegmentControl`,
 * Schalter über `ui/Switch`, Reload über `v4/ReloadButton`.
 *
 * Mechanik: Freeze-Gate wie check-scrollschatten — rohe `<button`-Vorkommen unter
 * `src/v4/**` sind nur in der Allowlist (belegter Bestand, Treffer-Zahl exakt)
 * erlaubt. Neue rohe Buttons (oder +1 in einer Bestandsdatei) blocken; weniger
 * Treffer als erlaubt blocken ebenfalls (dann Allowlist runterzählen = Abbau
 * sichtbar machen). ui/-SoT-Bausteine selbst liegen außerhalb des Scopes.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SCOPE = join(ROOT, 'src', 'v4')

/**
 * Belegter Bestand (R3b Etappe 2, je mit Grund):
 * - ZeitStepper: Player-StepBtn + Titel-Aufklapper + Dropdown-Einträge (eigene
 *   Mikro-Optik des Steppers, kein Aktions-Button)
 * - StatusFusszeile: Fusszeilen-Chips (eigene 24-px-Statuszeilen-Optik)
 * - WerkbankZeitraum: Zeitraum-Schnellwahl-Chips (STEUER_H-Chips mit Einzel-Rahmen,
 *   keine Segment-Gruppe) — 2× (WerkbankZeitraum + VergleichLeisteTag)
 * - Tagesverlauf-/JahrVerlaufChart: Solo-Toggle „Autarkie %" (Einzel-Toggle mit
 *   Farb-Semantik, bewusst kein SegmentControl — S4-Verdict)
 * - Rails (Tages/Monats/Jahres): Rail-Einträge (Listen-Buttons)
 * - KomponentenTypV4: Geräteselektor (Pill-/Tab-Selektor, B3-Territorium — s. Kommentar dort)
 * - CockpitLiveV4: Kachel-Fokus-Button (FokusKachel-IST-Layout, S11-Ausnahme bis Flip)
 *
 * Session 4 (2026-07-11): Gernot hat diese 15 Vorkommen als Fall-3-Mikro-Optik
 * bestätigt und zusätzlich in `check-v4-migration.mjs` (ROH_INFRA) freigegeben.
 * Kein Zähler-Wechsel — der belegte Bestand bleibt hier exakt eingefroren.
 */
const ALLOW = new Map([
  ['src/v4/ZeitStepper.tsx', 3],
  ['src/v4/status/StatusFusszeile.tsx', 3],
  ['src/v4/WerkbankZeitraum.tsx', 2],
  ['src/v4/TagesverlaufChart.tsx', 1],
  ['src/v4/TagesRail.tsx', 1],
  ['src/v4/MonatsRail.tsx', 1],
  ['src/v4/KomponentenTypV4.tsx', 1],
  ['src/v4/JahrVerlaufChart.tsx', 1],
  ['src/v4/JahresRail.tsx', 1],
  ['src/v4/CockpitLiveV4.tsx', 1],
])

function tsxFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...tsxFiles(p))
    else if (name.endsWith('.tsx') && !name.endsWith('.test.tsx')) out.push(p)
  }
  return out
}

let fehler = 0
const gesehen = new Map()

for (const file of tsxFiles(SCOPE)) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  const src = readFileSync(file, 'utf8')
  const treffer = (src.match(/<button\b/g) ?? []).length
  if (treffer > 0) gesehen.set(rel, treffer)
}

for (const [rel, anzahl] of gesehen) {
  const erlaubt = ALLOW.get(rel) ?? 0
  if (anzahl !== erlaubt) {
    fehler++
    console.error(
      `✗ ${rel}: ${anzahl}× rohes <button> (erlaubt: ${erlaubt}) — B15: ui/Button/` +
      `SegmentControl/Switch/ReloadButton nutzen oder (bewusster Bestand) Allowlist anpassen`,
    )
  }
}
for (const [rel, erlaubt] of ALLOW) {
  if (!gesehen.has(rel) && erlaubt > 0) {
    fehler++
    console.error(`✗ Allowlist-Eintrag ohne Treffer: ${rel} (erlaubt ${erlaubt}) — Eintrag entfernen`)
  }
}

if (fehler) {
  console.error(`\ncheck:buttons — ${fehler} Abweichung(en) vom eingefrorenen B15-Bestand.`)
  process.exit(1)
}
console.log(`✓ check:buttons — rohe <button> in src/v4 exakt auf Allowlist-Stand (${[...ALLOW.values()].reduce((a, b) => a + b, 0)} belegte Vorkommen).`)
