#!/usr/bin/env node
/**
 * check-datenquellen-aufloesung.mjs — Wächter der B7-Auflösung (Datenquellen-V4 §2g).
 *
 * Die beiden Alt-Wizards `SensorMappingWizard` (`sensor-mapping`) und
 * `MqttInboundSetup` (`mqtt-inbound`) sind in die feld-zentrische Datenquellen-Fläche
 * aufgelöst: in V4 führt JEDER Einstieg auf `v4/einstellungen/datenquellen`. Die
 * Wizard-Dateien und ihre V3-Routen bleiben bis zum Flip bestehen (PLAN-IA-V4-RESTWEG)
 * — genau darum kann die Drift zurückkommen, wenn ein neuer V4-Einstieg wieder den
 * Alt-Wizard öffnet. Der Wächter friert den erreichten Zustand ein.
 *
 * Drei Regeln (Muster: check-parkbar = Allowlist-Tripwire):
 *   1. IMPORT — die beiden Wizard-Module dürfen nur noch aus der V3-Route (`App.tsx`)
 *      importiert werden. Ein Import irgendwo sonst (v4/, components/, pages/) heißt:
 *      der Wizard ist wieder eine V4-Fläche → Verstoß.
 *   2. OVERLAY — `oeffneWizard('sensor-mapping'|'mqtt-inbound')` bzw. ein
 *      Registry-/`offen=`-Eintrag mit diesen Keys: die Keys sind aus der `WizardKey`-
 *      Union entfernt; tsc fängt das zwar, der Wächter benennt aber den Grund.
 *   3. ROUTEN-STRINGS — `einstellungen/sensor-mapping` / `einstellungen/mqtt-inbound`
 *      nur noch in Dateien, die sie legitim führen (V3-Route, Routen-Manifest,
 *      V3→V4-Map, Katalog-`weitereRouten`, V3-Fallback-Links). Neue Fundstellen
 *      erzwingen die bewusste Frage „ist das ein V4-Einstieg?".
 *
 * Grenze (bewusst): Regel 3 ist datei-, nicht zeilengenau — sie fängt den neuen
 * Einstieg an einer neuen Stelle, nicht eine zweite Zeile in einer Datei, die den
 * String ohnehin führen darf. Das ist die real aufgetretene Drift-Klasse.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Die aufgelösten Alt-Wizards: Modulname → Wizard-/Routen-Schlüssel. */
const ALT_WIZARDS = [
  { modul: 'SensorMappingWizard', key: 'sensor-mapping' },
  { modul: 'MqttInboundSetup', key: 'mqtt-inbound' },
]

/** Regel 1: einzige Datei, die die Wizard-Module importieren darf (V3-Route). */
const IMPORT_ERLAUBT = new Set(['src/App.tsx'])

/** Regel 3: Dateien, die die Alt-Routen legitim führen. */
const ROUTE_ERLAUBT = new Set([
  'src/App.tsx',                                  // V3-Route (bleibt bis Flip)
  'src/routes/routeManifest.ts',                  // Routen-Inventur
  'src/config/v3ZuV4Route.ts',                    // V3→V4-Map: zeigt auf die Fläche
  'src/config/v3ZuV4Route.test.ts',
  'src/config/einstellungenKatalog.tsx',          // weitereRouten der Fläche
  'src/config/einstellungenKatalog.test.ts',
  'src/components/layout/SubTabs.tsx',            // V3-Navigation (nur im V3-Layout)
  'src/components/layout/TopNavigation.tsx',      // V3-Navigation (nur im V3-Layout)
  'src/pages/Einrichtung.tsx',                    // V3-Karten (nur: 'v3')
  'src/pages/HAStatistikImport.tsx',              // V3-Fallback-Link
  // B7-5 (2026-07-18, HA-Export): „Verbindung bearbeiten" ist flag-gegatet —
  // V4 → /v4/einstellungen/integration (Broker-Pflegeort der Integration-Kategorie,
  // NICHT der Alt-Wizard), V3-Fallback-Literal nur im flag-off-Build (harter
  // /v4-Link wäre dort tote Route). Legitime V3-Stelle, kein neuer V4-Einstieg.
  'src/pages/HAExportSettingsTeile.tsx',
  'src/pages/SensorMappingWizard.tsx',            // Selbst-Navigation (V3-intern)
  'src/pages/DatenerfassungGuide.tsx',            // V3-Leiche (nirgends gerendert)
  'src/components/prognose/PrognoseVergleichTeile.tsx', // V3-Link, V4 via v3RouteZuV4
  // D2 (2026-07-18): Setup-Abschluss „Sensor- & Topic-Pflege" — V3-Fallback-
  // Literal, unter IA_V4 biegt v3RouteZuV4 auf /v4/einstellungen/datenquellen um.
  'src/components/setup-wizard/steps/CompleteStep.tsx',
])

function files(dir) {
  const out = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...files(p))
    else if (/\.tsx?$/.test(n)) out.push(p)
  }
  return out
}

const verstoesse = []
const zeileVon = (src, i) => src.slice(0, i).split('\n').length

for (const f of files(SRC)) {
  const rel = f.replace(ROOT + '/', '')
  const src = readFileSync(f, 'utf8')

  for (const { modul, key } of ALT_WIZARDS) {
    // Regel 1 — Import des Wizard-Moduls.
    const reImport = new RegExp(`import\\s*\\(?\\s*['"][^'"]*/${modul}['"]|from\\s*['"][^'"]*/${modul}['"]`, 'g')
    let m
    while ((m = reImport.exec(src))) {
      if (!IMPORT_ERLAUBT.has(rel)) {
        verstoesse.push({ rel, zeile: zeileVon(src, m.index), regel: 1, text: `importiert \`${modul}\`` })
      }
    }

    // Regel 2 — Wizard-Overlay-Schlüssel.
    const reKey = new RegExp(`oeffneWizard\\(\\s*['"]${key}['"]|offen=["']${key}["']`, 'g')
    while ((m = reKey.exec(src))) {
      verstoesse.push({ rel, zeile: zeileVon(src, m.index), regel: 2, text: `öffnet den Alt-Wizard \`${key}\` im Overlay` })
    }

    // Regel 3 — Alt-Route als String.
    const reRoute = new RegExp(`einstellungen/${key}`, 'g')
    while ((m = reRoute.exec(src))) {
      if (!ROUTE_ERLAUBT.has(rel)) {
        verstoesse.push({ rel, zeile: zeileVon(src, m.index), regel: 3, text: `referenziert \`einstellungen/${key}\`` })
      }
    }
  }
}

if (verstoesse.length > 0) {
  console.error('\ncheck:datenquellen-aufloesung — Alt-Wizard-Referenz(en) außerhalb der erlaubten Stellen:\n')
  for (const v of verstoesse) console.error(`  ✗ ${v.rel}:${v.zeile} → ${v.text} (Regel ${v.regel})`)
  console.error(
    '\nB7 (Datenquellen-V4 §2g): `sensor-mapping` + `mqtt-inbound` sind in die\n' +
    'Datenquellen-Fläche aufgelöst — in V4 führt jeder Einstieg auf\n' +
    '`/v4/einstellungen/datenquellen`.\n' +
    '  • Neuer V4-Einstieg? → auf die Fläche navigieren, nicht den Alt-Wizard öffnen.\n' +
    '  • Legitime V3-Stelle (Route/Fallback/Manifest)? → Datei in die Allowlist\n' +
    '    dieses Wächters aufnehmen (bewusste Entscheidung).\n',
  )
  process.exit(1)
}

console.log('\ncheck:datenquellen-aufloesung — keine Alt-Wizard-Referenz außerhalb der erlaubten V3-Stellen.')
console.log(`✅ B7: ${ALT_WIZARDS.map(w => w.key).join(' + ')} bleiben aufgelöst (V4-Einstiege → Datenquellen-Fläche).`)
