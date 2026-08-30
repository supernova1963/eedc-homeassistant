#!/usr/bin/env node
/**
 * check-spiegel-backend.mjs — Backend↔Client-Spiegel-Gate (2026-08-30).
 *
 * **Warum es diesen Prüfer gibt.** Zwei Vokabulare stehen im Repo **zweimal**:
 * einmal in Python, einmal in TypeScript. Verbunden waren sie nur durch einen
 * Kommentar („Spiegel von …") — kein Test, und keiner der übrigen `check:*`
 * schaut über die Sprachgrenze (`check-label-maps` deckt ausschließlich
 * Frontend-interne SoT-Maps ab). Gefunden beim Bau des fünften
 * Monatsbericht-Themas: Wer eine dieser Listen nur auf **einer** Seite
 * erweitert, bekommt entweder
 *   - einen Schalter, der still nichts tut (das Backend filtert unbekannte
 *     Schlüssel kommentarlos weg), oder
 *   - ein Thema, das der Anwender nie zu sehen bekommt.
 * Beides ohne Fehlermeldung, in beiden Richtungen.
 *
 * Geprüft werden die **Schlüssel** (Reihenfolge inklusive, denn sie ist bei den
 * Themen die Reihenfolge im Dokument) und, wo beide Seiten Labels führen, die
 * **Labels**.
 *
 * ⛔ Bewusst regex-basiert statt per Import: Der Prüfer soll ohne laufendes
 * Python und ohne Bundling arbeiten — wie alle anderen `check:*` auch.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const REPO = join(ROOT, '..', '..')

/** Liest eine Datei; wirft mit klarem Text, wenn der Pfad nicht (mehr) stimmt. */
function lies(pfad) {
  try {
    return readFileSync(pfad, 'utf8')
  } catch {
    throw new Error(`Datei nicht gefunden: ${pfad} — Spiegel-Prüfer zeigt ins Leere`)
  }
}

/** Inhalt zwischen Start-Marke und der ersten schließenden Klammer am Zeilenanfang. */
function block(text, start, ende) {
  const i = text.indexOf(start)
  if (i < 0) return null
  const j = text.indexOf(ende, i)
  if (j < 0) return null
  return text.slice(i, j)
}

const fehler = []

// ── Spiegel 1: die Themenschalter des Monatsberichts ────────────────────────
{
  const py = lies(join(REPO, 'eedc/backend/services/pdf/builders/monatsbericht.py'))
  const ts = lies(join(ROOT, 'src/components/DokumentationsDialog.tsx'))

  const pyRoh = block(py, 'THEMEN: tuple[str, ...] = (', ')')
  const tsRoh = block(ts, 'const MONATSBERICHT_THEMEN = [', ']')
  if (!pyRoh || !tsRoh) {
    fehler.push('THEMEN: eine der beiden Listen ist nicht mehr auffindbar (umbenannt?)')
  } else {
    const pyKeys = [...pyRoh.matchAll(/"([a-z0-9_]+)"/g)].map(m => m[1])
    const tsKeys = [...tsRoh.matchAll(/key:\s*'([a-z0-9_]+)'/g)].map(m => m[1])
    if (pyKeys.join(',') !== tsKeys.join(',')) {
      fehler.push(
        `THEMEN weichen ab:\n    Backend: ${pyKeys.join(' · ')}\n    Client:  ${tsKeys.join(' · ')}`,
      )
    }
    // Labels: Backend THEMA_LABELS gegen die Client-Labels.
    const pyLabelBlock = block(py, 'THEMA_LABELS: dict[str, str] = {', '}')
    const pyLabels = new Map(
      [...(pyLabelBlock || '').matchAll(/"([a-z0-9_]+)":\s*"([^"]+)"/g)].map(m => [m[1], m[2]]),
    )
    const tsLabels = new Map(
      [...tsRoh.matchAll(/key:\s*'([a-z0-9_]+)',\s*label:\s*'([^']+)'/g)].map(m => [m[1], m[2]]),
    )
    for (const [k, v] of tsLabels) {
      if (pyLabels.has(k) && pyLabels.get(k) !== v) {
        fehler.push(`THEMA_LABELS['${k}']: Backend „${pyLabels.get(k)}" ≠ Client „${v}"`)
      }
    }
  }
}

// ── Spiegel 2: die Energie-Kategorien der Monatsauswertung ──────────────────
{
  const py = lies(join(REPO, 'eedc/backend/api/routes/energie_profil/views.py'))
  const ts = lies(join(ROOT, 'src/lib/colors.ts'))

  const pyRoh = block(py, 'ENERGIE_KATEGORIEN: dict[str, tuple[str, str, str]] = {', '\n}')
  const tsRoh = block(ts, 'export const ENERGIE_KATEGORIE: Record<', '\n}')
  if (!pyRoh || !tsRoh) {
    fehler.push('ENERGIE_KATEGORIE(N): eine der beiden Maps ist nicht mehr auffindbar')
  } else {
    // Die Hex-Werte der Komponenten-Identität — der Client führt in der
    // Kategorie-Map nur Tailwind-Klassen und verweist auf diese Konstanten.
    // Ein PDF braucht den Ton selbst; ohne diese Auflösung wäre die Farbe der
    // einzige Teil des Spiegels, den niemand prüft (und genau dort standen beim
    // ersten Bau drei erfundene Töne).
    const hexVon = new Map(
      [...ts.matchAll(/^\s*'?([a-z-]+)'?:\s*\{\s*hex:\s*'(#[0-9a-f]{6})'/gm)]
        .map(m => [m[1], m[2]]),
    )
    const sonstigerErzeuger = ts.match(
      /SONSTIGES_ERZEUGER_FARBE\s*=\s*\{\s*hex:\s*'(#[0-9a-f]{6})'/,
    )
    if (sonstigerErzeuger) hexVon.set('__sonstiger_erzeuger__', sonstigerErzeuger[1])
    // `bg-slate-500` u. ä. stehen als Klasse ohne Hex — dafür die Tailwind-Töne,
    // die die Client-Map direkt als Klasse setzt.
    const TAILWIND = { 'bg-slate-500': '#64748b' }

    /** Farbe, die der CLIENT für eine Kategorie zeigt — über seinen eigenen Verweis. */
    function clientHex(eintrag) {
      const m = eintrag.match(/bg:\s*(?:KOMPONENTEN_FARBEN\['([a-z-]+)'\]|(SONSTIGES_ERZEUGER_FARBE))\.bg/)
      if (m && m[1]) return hexVon.get(m[1]) || null
      if (m && m[2]) return hexVon.get('__sonstiger_erzeuger__') || null
      const klasse = eintrag.match(/bg:\s*'([a-z0-9-]+)'/)
      if (klasse) return TAILWIND[klasse[1]] || null
      return null
    }

    const pyMap = new Map(
      [...pyRoh.matchAll(/"([a-z_]+)":\s*\("([^"]+)",\s*"([a-z]+)",\s*"(#[0-9a-f]{6})"\)/g)]
        .map(m => [m[1], { label: m[2], gruppe: m[3], hex: m[4] }]),
    )
    const tsMap = new Map(
      [...tsRoh.matchAll(/^\s{2}([a-z_]+):\s*\{([\s\S]*?)\},?$/gm)]
        .map(m => {
          const inhalt = m[2]
          const label = inhalt.match(/label:\s*'([^']+)'/)
          const gruppe = inhalt.match(/gruppe:\s*'([a-z]+)'/)
          return [m[1], {
            label: label ? label[1] : null,
            gruppe: gruppe ? gruppe[1] : null,
            hex: clientHex(inhalt),
          }]
        }),
    )
    const nurPy = [...pyMap.keys()].filter(k => !tsMap.has(k))
    const nurTs = [...tsMap.keys()].filter(k => !pyMap.has(k))
    if (nurPy.length) fehler.push(`ENERGIE_KATEGORIEN nur im Backend: ${nurPy.join(' · ')}`)
    if (nurTs.length) fehler.push(`ENERGIE_KATEGORIE nur im Client: ${nurTs.join(' · ')}`)
    for (const [k, v] of pyMap) {
      const t = tsMap.get(k)
      if (!t) continue
      if (t.label !== v.label) fehler.push(`Kategorie '${k}': Label Backend „${v.label}" ≠ Client „${t.label}"`)
      if (t.gruppe !== v.gruppe) fehler.push(`Kategorie '${k}': Gruppe Backend „${v.gruppe}" ≠ Client „${t.gruppe}"`)
      if (t.hex === null) {
        fehler.push(`Kategorie '${k}': Client-Farbe nicht auflösbar — der Verweis in `
          + `ENERGIE_KATEGORIE passt nicht mehr zum Muster des Prüfers`)
      } else if (t.hex !== v.hex) {
        fehler.push(`Kategorie '${k}': Farbe Backend ${v.hex} ≠ Client ${t.hex} `
          + `(Regel 0a — eine Datenrolle, eine Farbe)`)
      }
    }
    if (pyMap.size === 0 || tsMap.size === 0) {
      fehler.push('ENERGIE_KATEGORIE(N): eine Seite wurde als LEER gelesen — das Muster passt nicht mehr')
    }
  }
}

if (fehler.length) {
  console.error(`check:spiegel-backend — ${fehler.length} Abweichung(en):\n`)
  fehler.forEach(f => console.error(`  ✗ ${f}`))
  console.error('\n  Beide Seiten pflegen, nicht eine. Die Spiegel stehen bewusst doppelt')
  console.error('  (Python rendert PDF/Markdown, TypeScript rendert den Bildschirm).')
  process.exit(1)
}
console.log('check:spiegel-backend — 0 Abweichungen (THEMEN · ENERGIE_KATEGORIE inkl. Farbe)')
