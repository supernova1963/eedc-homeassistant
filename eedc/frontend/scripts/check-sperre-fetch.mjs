#!/usr/bin/env node
/**
 * check-sperre-fetch.mjs — kein schreibender `fetch` an der Einstellungs-Sperre vorbei.
 *
 * Die Sperre (2026-08-22, #391/#393) hängt an zwei Stellen: `api/client.ts` für die
 * gewöhnlichen Aufrufe und `api/fetchApi.ts` für alles, was `fetch` direkt braucht
 * (FormData-Uploads, eigene Abbruch-Signale). Ein roher `fetch` mit einem schreibenden
 * Verb daneben umgeht beide — er schickt keinen Entsperr-Nachweis mit und behandelt
 * keinen 423.
 *
 * Beim Bau waren es **22 solche Aufrufe in sechs Dateien**; sie sind auf `fetchApi`
 * umgestellt. Dieser Wächter hält den Zustand fest, statt darauf zu vertrauen, dass es
 * dem Nächsten auffällt.
 *
 * Nicht gemeldet werden lesende `fetch`-Aufrufe (Hilfe-Dateien, Downloads) und
 * Methoden, die zufällig `fetch` heißen (`async fetch(anlageId)` in Adaptern) — die
 * Sperre betrifft nur Schreibendes.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SCOPE = join(ROOT, 'src')

// Die beiden SoT-Dateien dürfen `fetch` roh aufrufen — sie *sind* die Behandlung.
const ERLAUBT = new Set(['src/api/client.ts', 'src/api/fetchApi.ts'])

const SCHREIB_VERB = /method:\s*['"`](POST|PUT|PATCH|DELETE)['"`]/i
// `fetch(` ohne vorangehendes Wortzeichen oder Punkt — schließt `fetchApi(` und
// `this.fetch(` aus, trifft aber `await fetch(` und `= fetch(`.
const ROHER_AUFRUF = /(?<![\w.])fetch\s*\(/

// ⚠ Eine DEFINITION ist kein Aufruf. Beim Bau lief dieser Wächter in genau diese
// Falle: `api/connector.ts` hat eine Methode, die `fetch` heißt (`async fetch(anlageId)`),
// und der Aufruf in ihrem Rumpf trägt `method: 'POST'` — der Prüfer meldete die
// Signatur. Ein Prüfer, der Deklaration und Aufruf nicht unterscheidet, meldet die
// falsche Zeile und wird deshalb irgendwann abgeschaltet statt befolgt.
const DEKLARATION = /(?:^|[^\w.])(?:async\s+|function\s+|\*\s*)?fetch\s*\([^)]*\)\s*(?::[^{]*)?\{\s*$/

function quellDateien(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...quellDateien(p))
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

let fehler = 0
for (const file of quellDateien(SCOPE)) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  if (ERLAUBT.has(rel)) continue

  const zeilen = readFileSync(file, 'utf8').split('\n')
  zeilen.forEach((zeile, i) => {
    if (/^\s*(\*|\/\/|\{\/\*)/.test(zeile)) return
    if (!ROHER_AUFRUF.test(zeile)) return
    if (DEKLARATION.test(zeile)) return

    // Das Verb steht oft erst in den Folgezeilen des Options-Objekts.
    const fenster = zeilen.slice(i, i + 8).join('\n')
    if (!SCHREIB_VERB.test(fenster)) return

    fehler++
    console.error(
      `✗ ${rel}:${i + 1} — schreibender fetch an der Einstellungs-Sperre vorbei. ` +
        `Bitte fetchApi() aus api/fetchApi.ts verwenden.`,
    )
  })
}

if (fehler) {
  console.error(`\ncheck:sperre-fetch — ${fehler} roher schreibender fetch-Aufruf.`)
  process.exit(1)
}
console.log('✅ Sperre: jeder schreibende fetch läuft über client.ts oder fetchApi.ts.')
