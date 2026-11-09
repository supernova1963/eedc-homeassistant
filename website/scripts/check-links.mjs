// check-links.mjs — Wächter über die gebaute Website (läuft als `postbuild` nach `npm run build`, lokal und in CI)
//
// Liest dist/**/*.html und prüft jeden href:
//   (a) ROT:  Verweis auf eine Markdown-Datei (kein absoluter URL, Pfadteil endet auf .md) — die Quelle
//             docs/*.md verweist GitHub-tauglich auf DATEI.md; scripts/remark-doku-links.mjs schreibt das beim
//             Build um. Steht danach noch ein .md-href im HTML, führt er auf der Website ins Leere.
//   (b) ROT:  interner Seitenlink /eedc-homeassistant/<pfad>/ ohne dist/<pfad>/index.html (oder Datei dist/<pfad>).
//   (c) ROT:  Anker-Links auf interne Seiten, deren Ziel-HTML weder id="…" noch name="…" mit dem Anker trägt —
//             der Anker-Teil eines Quellverweises nennt eine Überschrift, die es (so) nicht mehr gibt (Päckchen X6).
// Exit 1 bei (a), (b) oder (c), mit Liste (Datei → href, höchstens 50 Zeilen). Nur node:fs/node:path.
// `--anker` listet jede Fundstelle von (c) vollständig: Quellseite → href → fehlender Anker
//   (`node scripts/check-links.mjs --anker` nach einem Build).
import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join, relative, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = '/eedc-homeassistant';
const WEBSITE = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(WEBSITE, 'dist');
const MAX_ZEILEN = 50;
const ANKER_LISTE = process.argv.includes('--anker');

if (!existsSync(DIST)) {
  console.error(`✗ check-links: ${DIST} fehlt — erst bauen`);
  process.exit(1);
}

function htmlDateien(verz) {
  const aus = [];
  for (const eintrag of readdirSync(verz, { withFileTypes: true })) {
    const pfad = join(verz, eintrag.name);
    if (eintrag.isDirectory()) aus.push(...htmlDateien(pfad));
    else if (eintrag.name.endsWith('.html')) aus.push(pfad);
  }
  return aus;
}

function entities(s) {
  return s
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function dekodiert(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

const ABSOLUT = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

// Seiten-Pfad (relativ zu dist, ohne Anker) → Datei im dist oder null
function zielDatei(pfad) {
  const p = dekodiert(pfad).replace(/^\/+/, '');
  if (p === '') return join(DIST, 'index.html');
  const direkt = join(DIST, p);
  if (!p.endsWith('/') && existsSync(direkt) && statSync(direkt).isFile()) return direkt;
  const index = join(DIST, p.replace(/\/+$/, ''), 'index.html');
  return existsSync(index) ? index : null;
}

const idCache = new Map();
function idsVon(datei) {
  if (!idCache.has(datei)) {
    const html = readFileSync(datei, 'utf8');
    const ids = new Set();
    for (const m of html.matchAll(/\s(?:id|name)="([^"]*)"/g)) ids.add(entities(m[1]));
    idCache.set(datei, ids);
  }
  return idCache.get(datei);
}

const rotMd = [];
const rotSeite = [];
let ankerLinks = 0;
let ankerLinksQuer = 0; // davon auf eine andere Seite
const ankerFehlt = new Map();
const ankerFehltStellen = []; // (c) je Fundstelle: Quellseite → href → fehlender Anker
let ankerFehltSumme = 0;
let ankerFehltQuer = 0;

const dateien = htmlDateien(DIST).sort();
for (const datei of dateien) {
  const html = readFileSync(datei, 'utf8');
  const rel = relative(DIST, datei).split(sep).join('/');
  for (const m of html.matchAll(/\shref="([^"]*)"/g)) {
    const href = entities(m[1]);
    if (ABSOLUT.test(href)) continue;
    const cut = href.search(/[#?]/);
    const pfad = cut === -1 ? href : href.slice(0, cut);
    const anker = href.includes('#') ? href.slice(href.indexOf('#') + 1) : '';

    // (a) Markdown-Datei als Ziel
    if (/\.md$/i.test(pfad)) {
      rotMd.push(`${rel} → ${href}`);
      continue;
    }

    // Ziel-Datei bestimmen: interner Seitenlink unter BASE oder reiner Anker auf derselben Seite
    let ziel = null;
    if (pfad === '') {
      ziel = datei;
    } else if (pfad === BASE || pfad.startsWith(`${BASE}/`)) {
      ziel = zielDatei(pfad.slice(BASE.length));
      if (!ziel) {
        rotSeite.push(`${rel} → ${href}`);
        continue;
      }
    } else {
      continue; // weder BASE noch Anker (z. B. relative Bild-Pfade) — nicht Gegenstand dieses Wächters
    }

    // (c) Anker zählen
    if (anker !== '' && ziel.endsWith('.html')) {
      const quer = ziel !== datei;
      ankerLinks += 1;
      if (quer) ankerLinksQuer += 1;
      if (!idsVon(ziel).has(dekodiert(anker))) {
        ankerFehltSumme += 1;
        if (quer) ankerFehltQuer += 1;
        const schluessel = `${relative(DIST, ziel).split(sep).join('/')}#${dekodiert(anker)}`;
        ankerFehlt.set(schluessel, (ankerFehlt.get(schluessel) ?? 0) + 1);
        ankerFehltStellen.push(`${rel} → ${href} → #${dekodiert(anker)}`);
      }
    }
  }
}

const anteil = ankerLinks ? ((100 * ankerFehltSumme) / ankerLinks).toFixed(1) : '0.0';
console.log(`check-links: ${dateien.length} HTML-Seiten geprüft`);
console.log(`  (a) .md-Verweise:        ${rotMd.length}`);
console.log(`  (b) tote Seitenlinks:    ${rotSeite.length}`);
console.log(`  (c) Anker ohne Ziel-ID:  ${ankerFehltSumme} von ${ankerLinks} Anker-Links (${anteil} %)`);
console.log(`      davon seitenübergreifend: ${ankerFehltQuer} von ${ankerLinksQuer}`);
if (ankerFehlt.size) {
  const top = [...ankerFehlt.entries()].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0])).slice(0, 10);
  for (const [ziel, n] of top) console.log(`      ${String(n).padStart(4)}  ${ziel}`);
}
if (ANKER_LISTE) {
  console.log(`  --anker: ${ankerFehltStellen.length} Fundstellen (Quellseite → href → fehlender Anker)`);
  for (const zeile of ankerFehltStellen) console.log(`    ${zeile}`);
}

const rot = [
  ...rotMd.map((z) => `(a) ${z}`),
  ...rotSeite.map((z) => `(b) ${z}`),
  ...ankerFehltStellen.map((z) => `(c) ${z}`),
];
if (rot.length) {
  console.error(
    `✗ check-links rot: ${rotMd.length} .md-Verweise, ${rotSeite.length} tote Seitenlinks, ` +
      `${ankerFehltSumme} Anker ohne Ziel`,
  );
  for (const zeile of rot.slice(0, MAX_ZEILEN)) console.error(`  ${zeile}`);
  if (rot.length > MAX_ZEILEN) console.error(`  … und ${rot.length - MAX_ZEILEN} weitere`);
  process.exit(1);
}
console.log('✓ check-links grün');
