#!/usr/bin/env node
/**
 * check-b8.mjs — B8-Zustände-Gate (Style-Guide B8, R3b S15-Slice, 2026-07-05).
 *
 * Regel: Sicht-/Block-Erst-Loads laden als Skeleton in Zielform (ui/Skeleton,
 * blocks/BlockStackSkeleton), Fehler laufen über ui/FehlerZustand, Onboarding-
 * Leerzustände über v4/OnboardingLeer (EmptyState-SoT mit CTA). LoadingSpinner
 * bleibt legitim für Inline-/Klein-Kontexte (Suspense-/Chunk-Fallbacks in
 * Modals, Klein-Widgets, Button-loading) — s. B8-Abgrenzungssatz im Style-Guide.
 *
 * Mechanik: Freeze-Gate wie check-buttons (Verify-Verdict S15: Kontext-Regex ist
 * die FALSCHE Architektur — mehrzeilige Ternary-Slots und Hand-Spinner entgehen
 * jedem return-Grep). Vier Zähler pro .tsx unter `src/v4/**` (ohne Tests),
 * Abweichung in BEIDE Richtungen blockt (Abbau = Allowlist runterzählen):
 *   Z1 `<LoadingSpinner`  — Restbestand: nur der Suspense-Chunk-Fallback im
 *      EinstellungenModalHost (Modal fester Breite, Wizard-Form vor Load unbekannt).
 *   Z2 `animate-spin`     — Hand-Spinner; Restbestand: CockpitLiveV4 (S11-IST-
 *      Ausnahme bis Flip, wie in check-buttons).
 *   Z3 Fehlertext-Zeile (`text-red-500` + dynamischer `{…}`-Slot) — Bestand 0;
 *      statisches Wert-Level-Signal-Rot (A3, z. B. Co2V4 „(Größe fehlt)") matcht
 *      bewusst NICHT.
 *   Z4 nackte Leer-Card (`<Card><p …>Noch keine/Keine …`) — eingefrorener
 *      Klasse-(c)-Bestand (Blätter-Lücken/Sektions-Hinweise ohne CTA, bewusst
 *      klein; Onboarding-Fälle laufen über OnboardingLeer).
 *
 * Bekanntes Restrisiko (Verdict): ein neuer Hand-Spinner ohne animate-spin
 * (CSS-Keyframe, Loader2-Direktimport) entginge Z1+Z2 — akzeptiert wie bei
 * check-buttons.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SCOPE = join(ROOT, 'src', 'v4')

const ZAEHLER = [
  {
    name: 'Z1 LoadingSpinner',
    zaehle: (src) => (src.match(/<LoadingSpinner\b/g) ?? []).length,
    allow: new Map([
      // Suspense-Fallback für lazy Wizard-Chunks im Modal — Code-Split-Laden,
      // kein Datenladen; Skeleton würde eine falsche Struktur vortäuschen.
      ['src/v4/EinstellungenModalHost.tsx', 1],
    ]),
    hinweis: 'B8: Sicht-/Block-Erst-Load → Skeleton (ui/Skeleton, BlockStackSkeleton); LoadingSpinner nur Inline-/Klein-Kontext (Allowlist)',
  },
  {
    name: 'Z2 Hand-Spinner (animate-spin)',
    zaehle: (src) => (src.match(/animate-spin/g) ?? []).length,
    allow: new Map([
      // S11-IST-Ausnahme bis Flip (A.3-Layout-Übernahme; Angleichung am R6-Flip
      // gebündelt — Präzedenz check-buttons.mjs CockpitLiveV4-Eintrag).
      ['src/v4/CockpitLiveV4.tsx', 1],
    ]),
    hinweis: 'B8/B15: kein Hand-Spinner — ui/Button loading bzw. Skeleton nutzen',
  },
  {
    name: 'Z3 nackter Fehlertext',
    // Zeile mit text-red-500 UND dynamischem Slot ({error}/{err}/{fehler}/{text})
    // = Seiten-/Sektions-Fehlerzustand an der SoT vorbei. Statische Wert-Level-
    // Hinweise (A3-Signal-Rot) matchen nicht.
    zaehle: (src) => src.split('\n').filter((z) =>
      /text-red-500/.test(z) && /\{(error|err|fehler|text)\}/.test(z)).length,
    allow: new Map(),
    hinweis: 'B8: Fehlerzustand über ui/FehlerZustand (IST-Text durchreichen, Retry wo möglich)',
  },
  {
    name: 'Z4 nackte Leer-Card',
    zaehle: (src) => src.split('\n').filter((z) =>
      /<Card><p [^>]*>(Noch keine|Keine )/.test(z)).length,
    allow: new Map([
      // Klasse (c) — bewusst kleine Cards (Verdicts VERIFIKATION-S15):
      // Blätter-Lücke Tag (T2/D12-1: großes Panel = Layout-Sprung) · Aussicht
      // „Keine Prognose verfügbar" · Community-Sektions-Hinweise (Benchmark
      // ohne Daten; Onboarding-CTA wäre hier falsch — Teilen-CTA hat CommunityV4).
      ['src/v4/CockpitTagV4.tsx', 1],
      ['src/v4/CockpitAussichtV4.tsx', 1],
      ['src/v4/CommunityUebersichtV4.tsx', 1],
      ['src/v4/CommunityStatistikenV4.tsx', 1],
      ['src/v4/CommunityTrendsV4.tsx', 1],
      ['src/v4/CommunityRegionalV4.tsx', 1],
      ['src/v4/CommunityPVErtragV4.tsx', 1],
      ['src/v4/CommunityKomponentenV4.tsx', 1],
    ]),
    hinweis: 'B8: Onboarding-Leerzustand über v4/OnboardingLeer (EmptyState + CTA); kleine Card nur Klasse (c) per Allowlist',
  },
]

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
const dateien = tsxFiles(SCOPE).map((f) => ({
  rel: relative(ROOT, f).replaceAll('\\', '/'),
  src: readFileSync(f, 'utf8'),
}))

for (const z of ZAEHLER) {
  const gesehen = new Map()
  for (const { rel, src } of dateien) {
    const n = z.zaehle(src)
    if (n > 0) gesehen.set(rel, n)
  }
  for (const [rel, anzahl] of gesehen) {
    const erlaubt = z.allow.get(rel) ?? 0
    if (anzahl !== erlaubt) {
      fehler++
      console.error(`✗ [${z.name}] ${rel}: ${anzahl}× (erlaubt: ${erlaubt}) — ${z.hinweis}`)
    }
  }
  for (const [rel, erlaubt] of z.allow) {
    if (!gesehen.has(rel) && erlaubt > 0) {
      fehler++
      console.error(`✗ [${z.name}] Allowlist-Eintrag ohne Treffer: ${rel} (erlaubt ${erlaubt}) — Eintrag entfernen`)
    }
  }
}

if (fehler) {
  console.error(`\ncheck:b8 — ${fehler} Abweichung(en) vom eingefrorenen B8-Bestand.`)
  process.exit(1)
}
const summe = ZAEHLER.reduce((a, z) => a + [...z.allow.values()].reduce((x, y) => x + y, 0), 0)
console.log(`✓ check:b8 — Lade-/Fehler-/Leer-Zustände in src/v4 exakt auf Allowlist-Stand (${summe} belegte Vorkommen).`)
