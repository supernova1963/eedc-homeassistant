#!/usr/bin/env node
/**
 * check-tabellen.mjs — B2-Tabellen-Gate (Style-Guide B2, R3b Etappe 2, 2026-07-05).
 *
 * Zwei grep-bare B2-Regeln:
 *  1. Spalten-Header-Farbe = `text-gray-500 dark:text-gray-400` — die gedrehte
 *     (hellere) Paarung `text-gray-400 dark:text-gray-500` auf einer Header-`<tr`
 *     ist der S13-Drift und blockt.
 *  2. Einheit im Header in RUNDEN Klammern `Name (Einheit)` — eckige Einheiten-
 *     Klammern (`[kWh]`, `[{einheit}]` …) in `<th`-Zeilen blocken.
 *
 * Scope: src/v4/** + von V4 konsumierte geteilte Tabellen-Dateien + IASkeleton
 * (Preview-SoT, Konvergenz-Prinzip — war der Drift-Ursprung von S13).
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

const GETEILTE_SOT = [
  // Paket CT: die generische Chart-Tabellen-Ablesung ist B2-pflichtig wie jede Tabelle.
  'src/components/ui/ChartDatenTabelle.tsx',
  'src/components/werte/WerteTabelle.tsx',
  // Pfad-Bug behoben 2026-07-10: stand als `components/werte/TagWerteTabelle.tsx`
  // in der Liste, liegt aber unter `components/tag/` ⇒ der Wächter hat die Datei
  // nie geprüft (grün ohne Deckung).
  'src/components/tag/TagWerteTabelle.tsx',
  'src/components/aussicht/AussichtTeile.tsx',
  'src/components/balkonkraftwerk/BkwJahresvergleich.tsx',
  'src/components/balkonkraftwerk/BkwCharts.tsx',
  'src/components/eauto/EAutoJahresvergleich.tsx',
  'src/components/speicher/SpeicherJahresbilanz.tsx',
  'src/components/preview/IASkeleton.tsx',
]

/** Dokumentierte Ausnahmen: Pfad → erlaubte Treffer-Zahl je Regel-Schlüssel. */
const ALLOW = new Map([
  // TagWerteTabelle (V3-Ära-Vorlage) trägt den Muted-Header noch — Angleichung
  // kommt mit den V3-Paketen (Allowlist = Rest-Bestand sichtbar).
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

const dateien = [
  ...tsxFiles(join(ROOT, 'src', 'v4')),
  ...GETEILTE_SOT.map((r) => join(ROOT, r)).filter((p) => existsSync(p)),
]

let fehler = 0
for (const file of dateien) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  const zeilen = readFileSync(file, 'utf8').split('\n')
  const erlaubt = ALLOW.get(rel) ?? 0
  let treffer = 0
  zeilen.forEach((z, i) => {
    if (/<tr\b[^>]*className="[^"]*text-gray-400 dark:text-gray-500/.test(z)) {
      treffer++
      if (treffer > erlaubt) {
        fehler++
        console.error(`✗ ${rel}:${i + 1} — Header-Farbe gedreht (text-gray-400 dark:text-gray-500) — B2: text-gray-500 dark:text-gray-400`)
      }
    }
    if (/<th\b/.test(z) && /\[\s*(?:\{?\s*einheit\s*\}?|kWh|kW|%|€|ct)\s*\]/.test(z)) {
      fehler++
      console.error(`✗ ${rel}:${i + 1} — Einheit in eckigen Klammern im Header — B2: Format „Name (Einheit)"`)
    }
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// Regel T (Tabellen-SoT, `docs/drafts/KONZEPT-TABELLEN-SOT.md`, abgenommen 2026-07-10)
//
// T1: kein rohes `<table>` außerhalb der Zentrale `components/ui/Table.tsx`.
// T7: keine eigene Scroll-/Sticky-/Höhen-Mechanik an Tabellen — die Zentrale
//     macht Fenster (T2), sticky Kopf/Fuß (T3) und sichtbare Leisten (T4).
//
// Die SoT hatte NULL Nutzer bei 52 rohen `<table>` — ohne Wächter ist eine
// Zentrale nur ein Vorschlag. Deshalb: harte Regel + schrumpfende Migrations-
// liste. Jeder Slice (T-2 … T-6) streicht Einträge; die Liste ist der Rest-
// Bestand und darf NIE wachsen.
// ─────────────────────────────────────────────────────────────────────────────

/** Dauerhafte Ausnahmen (§4 des Konzepts) — jede mit Begründung im Code. */
const T_ALLOWLIST = new Set([
  'src/components/ui/Table.tsx', // die Zentrale selbst
  'src/pages/aussichten/KorrekturprofilHeatmapCard.tsx', // Heatmap-Matrix, keine Datensatz-Semantik
  'src/components/preview/IASkeleton.tsx', // Design-Attrappe, nicht Teil der App
  'src/pages/Hilfe.tsx', // statische Info-/Layout-Tabelle
  'src/components/ui/MarkdownDoc.tsx', // Markdown-Render-Tabelle (aus Hilfe.tsx extrahiert, D2)
  // Gernot 2026-07-10: T-Konto bleibt Sonderfall, KEINE Zentralisierung planen.
  // Es ist kein Tabellenraster, sondern ein Layout aus vier Tabellen (Desktop mit
  // unsichtbarer Trenn-Spalte, drei `table-fixed`-Teiltabellen mit <colgroup>,
  // Summen über Border-Zeilen, eigene Mobile-Variante).
  'src/components/finanzen/TKonto.tsx',
])

/** Zeilen-Marker für EINZELNE Tabellen in sonst migrierten Dateien:
 *  `{ /* tabelle-allow: Begründung *\/ }` unmittelbar über dem rohen `<table`.
 *  Nötig, weil der Wächter dateibasiert ist (z. B. Kennzahlen-Mini-Tabellen
 *  neben echten Datentabellen in derselben Datei). */
const ZEILEN_MARKER = /tabelle-allow:/

/** NOCH NICHT MIGRIERT — schrumpft mit jedem Slice. Darf nie wachsen. */
const T_MIGRATION_OFFEN = new Set([
  // ✅ Slice T-2 erledigt 2026-07-10: WerteTabelle + TagWerteTabelle auf ui/Table.
  // ✅ Slice T-3 erledigt 2026-07-10: Bilanzen (Tag/Monat/Jahr) + MonatRahmen +
  //    KomponentenMonatsTabelle + KomponentenVergleich auf ui/Table.
  // Slice T-4 ✅ 2026-07-10: RoiAnalyse · PvStringsTeile · PrognoseVsIstTeile ·
  //   AussichtTeile · EnergieprofilPrognose · PrognoseVergleichTeile (4 Datentabellen
  //   auf ui/Table; die 3-Zeilen-Stratifizierungs-Mini-Tabelle bleibt roh mit
  //   `tabelle-allow`-Marker, §6b.8). TKonto = dauerhafter Sonderfall (T_ALLOWLIST).
  // ✅ Slice T-5 erledigt 2026-07-10: Community (Komponenten×2/PVErtrag/Regional/
  //   Statistiken) + Chart-Familien-Monatstabellen (Bkw/EAuto/WP/PVStringVergleich/
  //   Speicher-Jahresbilanz+VerlaufCharts) auf ui/Table.
  // Slice T-6: V3 / Wizards / Settings — ziehen mit Donor→V4 nach
  'src/components/energieprofil/EnergieprofilTageTabelle.tsx', 'src/components/energieprofil/ReaggregatePreviewModal.tsx',
  'src/components/repair/RepairWorkbench.tsx',
  'src/pages/aussichten/KurzfristTab.tsx',
  'src/pages/auswertung/InvestitionenTab.tsx',
  'src/pages/CloudImportWizard.tsx', 'src/pages/CustomImportWizard.tsx', 'src/pages/DataImportWizard.tsx',
  'src/pages/HAStatistikImport.tsx', 'src/pages/MonatsdatenTeile.tsx',
  'src/pages/ProtokolleTeile.tsx', 'src/pages/PVGISSettingsTeile.tsx',
])

const alleTsx = tsxFiles(join(ROOT, 'src'))
let tFehler = 0
let restBestand = 0

/** Rohe `<table`-Zeilen einer Datei, die KEINEN `tabelle-allow`-Marker in den
 *  drei Zeilen darüber tragen. */
function ungedeckteTabellen(inhalt) {
  const zeilen = inhalt.split('\n')
  const treffer = []
  zeilen.forEach((z, i) => {
    if (!/<table(?![A-Za-z])/.test(z)) return
    const kontext = zeilen.slice(Math.max(0, i - 3), i + 1).join('\n')
    if (ZEILEN_MARKER.test(kontext)) return
    treffer.push(i + 1)
  })
  return treffer
}

/** Zeilen-Bereiche [start,end] (0-basiert, inklusiv) roher `<table`-Blöcke MIT
 *  `tabelle-allow`-Marker. Ihre Zellen sind vom T6-Typo-Gate ausgenommen: eine
 *  allow-markierte Roh-Tabelle liegt bewusst NEBEN der SoT (eigene Dichte, z. B.
 *  eine text-xs-Kennzahlen-Mini-Tabelle), das Höhenfenster rechnet nicht mit ihr.
 *  Ohne diese Ausnahme würde eine solche Zelle mit eigenem `py-*` T6 auslösen,
 *  sobald die Datei sonst migriert ist (2026-07-10, PrognoseVergleichTeile). */
function allowMarkierteBereiche(inhalt) {
  const zeilen = inhalt.split('\n')
  const bereiche = []
  zeilen.forEach((z, i) => {
    if (!/<table(?![A-Za-z])/.test(z)) return
    const kontext = zeilen.slice(Math.max(0, i - 3), i + 1).join('\n')
    if (!ZEILEN_MARKER.test(kontext)) return
    let ende = zeilen.length - 1
    for (let j = i; j < zeilen.length; j++) { if (/<\/table>/.test(zeilen[j])) { ende = j; break } }
    bereiche.push([i, ende])
  })
  return bereiche
}

for (const file of alleTsx) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  if (T_ALLOWLIST.has(rel)) continue
  const inhalt = readFileSync(file, 'utf8')
  const offen = ungedeckteTabellen(inhalt)
  if (offen.length === 0) continue

  if (T_MIGRATION_OFFEN.has(rel)) { restBestand++; continue }
  tFehler++
  console.error(`✗ ${rel}:${offen.join(',')} — rohes <table> (T1). Zentrale components/ui/Table.tsx nutzen, oder `
    + `{/* tabelle-allow: Begründung */} darüber setzen.`)
}

// ── T6: eine Zell-Typo ───────────────────────────────────────────────────────
// Das Höhenfenster (T2) rechnet mit EINER Zeilenhöhe. Eine einzige Zelle mit
// eigenem `py-*`/`text-*` macht die ganze Zeile höher — dann passen 24 Stunden
// nicht mehr auf FullHD (2026-07-10: `px-3 py-1.5` ohne `text-sm` ⇒ 37 statt
// 29 px ⇒ Inhalt 954 statt 750 px). Deshalb: in migrierten Dateien dürfen
// `<td>`/`<th>` ihre Typo NUR aus ZELLE/KOPF_ZELLE beziehen.
// Trifft BEIDE Schreibweisen: className="…" und className={`…`} — die zweite
// war zuerst vergessen und hat eine 37-px-Zelle durchgelassen (2026-07-10).
// Verboten ist, was die ZEILENHÖHE ändert: eigenes vertikales Padding und jede
// Schrift GRÖSSER als die SoT-Zelle (text-sm/20px). `text-xs` bleibt erlaubt —
// kleinere Schrift (Δ-Spalten, Einheiten) hebt die Zeile nicht an.
const TYPO_VERBOTEN = /<t[hd]\b[^>]*className=(?:"|\{`)[^"`]*(?:\bpy-[\d.]|\btext-(?:base|lg|xl|2xl)\b)/

for (const file of alleTsx) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  if (T_ALLOWLIST.has(rel) || T_MIGRATION_OFFEN.has(rel)) continue
  const inhalt = readFileSync(file, 'utf8')
  const zeilen = inhalt.split('\n')
  if (!zeilen.some((z) => /<Table\b/.test(z))) continue // nur migrierte Tabellen-Dateien
  const ausgenommen = allowMarkierteBereiche(inhalt)
  zeilen.forEach((z, i) => {
    if (ausgenommen.some(([a, b]) => i >= a && i <= b)) return // allow-markierte Roh-Tabelle: eigene Typo
    if (TYPO_VERBOTEN.test(z)) {
      tFehler++
      console.error(`✗ ${rel}:${i + 1} — Zelle mit eigener Typo (T6). Padding/Schrift nur über ZELLE/KOPF_ZELLE `
        + `aus components/ui/tabelleMasse.ts — sonst stimmt das Höhenfenster nicht.`)
    }
  })
}

// Rückwärts-Gate: Einträge, die nicht mehr existieren oder kein <table> mehr haben,
// müssen aus der Liste raus — sonst verrottet sie und deckt neue Verstöße zu.
for (const rel of T_MIGRATION_OFFEN) {
  const p = join(ROOT, rel)
  if (!existsSync(p) || ungedeckteTabellen(readFileSync(p, 'utf8')).length === 0) {
    tFehler++
    console.error(`✗ ${rel} — steht in T_MIGRATION_OFFEN, hat aber kein rohes <table> mehr. Eintrag streichen.`)
  }
}

if (fehler || tFehler) {
  console.error(`\ncheck:tabellen — ${fehler} B2-Verstoß/Verstöße, ${tFehler} Regel-T-Verstoß/Verstöße.`)
  process.exit(1)
}
console.log('✅ B2: Tabellen-Header in Kanon-Farbe (gray-500/400) und rundem Einheiten-Klammer-Format.')
console.log(`✅ T1: kein rohes <table> außerhalb der Zentrale (${restBestand} Dateien noch in der Migrationsliste).`)
