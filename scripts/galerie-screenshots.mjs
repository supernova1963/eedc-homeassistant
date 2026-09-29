#!/usr/bin/env node
/**
 * Screenshot-Galerie (Issue #364) — wiederholbarer Lauf statt Handarbeit.
 * ============================================================================
 *
 * Erzeugt die Bilder unter `website/src/assets/screenshots/` neu: je Ansicht
 * ein Paar `<name>.webp` (hell) und `<name>-dark.webp` (dunkel). Die Namen sind
 * **Vertrag** — `website/src/content/docs/features.mdx`, `installation.mdx` und
 * `galerie.mdx` importieren sie direkt; ein umbenanntes Bild bricht den
 * Website-Build.
 *
 * ⭐ Der Wert dieses Skripts ist der WIEDERHOLBARE LAUF, nicht die Bilder von
 * heute. Vor jedem größeren Release einmal fahren, dann zeigt die Galerie den
 * ausgelieferten Stand statt den von vor einem Jahr.
 *
 * **Format WebP** (seit 29.09.2026, vorher PNG): derselbe Bildinhalt bei rund
 * einem Fuenftel der Dateigroesse — der Ordner ist Repo-Gewicht, das bei jedem
 * Galerie-Lauf neu geschrieben wird. Playwright liefert nur PNG/JPEG, die
 * Umwandlung macht `sharp` (schon im Baum, s. oben). Die Galerie betrifft
 * ausschliesslich die Website: kein aktives Dokument unter `docs/` bindet diese
 * Bilder ein, `release.sh` spiegelt nur `eedc/backend/` und `eedc/frontend/` in
 * den Standalone, und das Add-on-Image traegt die Website nicht.
 *
 * ---------------------------------------------------------------------------
 * 1. Box aufsetzen (einmal je Lauf)
 * ---------------------------------------------------------------------------
 *
 *   # a) Demo-Datenbank als KOPIE — nie die Produktiv-DB, nie eine echte Anlage
 *   cp <eine Demo-DB> /tmp/galerie.db
 *
 *   # b) Frontend MIT Demo-Flag bauen (siehe §2 — ohne das Flag ist Cockpit/Live leer)
 *   cd eedc/frontend && VITE_DEMO_DEFAULT=true npm run build
 *
 *   # c) Box auf einem eigenen Port, Scheduler aus (Port 8200 gehoert anderen Sitzungen)
 *   cd eedc && setsid env DATABASE_URL="sqlite+aiosqlite:////tmp/galerie.db" \
 *     EEDC_DISABLE_SCHEDULER=true backend/venv/bin/python \
 *     -m uvicorn backend.main:app --host 127.0.0.1 --port 8201 &
 *   curl -s http://localhost:8201/api/health      # muss die erwartete Version melden
 *
 *   # d) Lauf
 *   node scripts/galerie-screenshots.mjs
 *
 *   # e) ⛔ Danach das Bundle OHNE Demo-Flag zurueckbauen — sonst bleibt ein
 *   #    Demo-Build im Baum stehen, den andere Sitzungen aus `dist/` bedienen
 *   cd eedc/frontend && npm run build
 *
 * ---------------------------------------------------------------------------
 * 2. Warum der Demo-Modus noetig ist
 * ---------------------------------------------------------------------------
 *
 * Cockpit → Live liest eine ECHTZEIT-Quelle (HA/MQTT). Eine Galerie-Box hat
 * keine; ohne Demo-Modus zeigt der Energiefluss durchgehend „0 W" und ist als
 * Bild wertlos. `GET /api/live/{id}?demo=true`
 * (`backend/api/routes/live_dashboard.py::_generate_demo_data`) liefert
 * stattdessen eine ideale Galerie-Anlage: sechs PV-Strings ueber drei
 * Ausrichtungen, zwei Wallboxen, Waermepumpe, Speicher, Poolpumpe, Sauna.
 * Den Parameter haengt der CLIENT an — und zwar nur, wenn das Bundle mit
 * `VITE_DEMO_DEFAULT=true` gebaut ist (`frontend/src/lib/flags.ts`).
 * Dasselbe Flag liefert auch die Community-Sichten aus Fixtures
 * (`frontend/src/api/communityDemo.ts`), die der Community-Server fuer eine
 * unbekannte Demo-Anlage sonst nicht beantworten koennte.
 *
 * ---------------------------------------------------------------------------
 * 3. Hell/Dunkel — der Weg und warum dieser
 * ---------------------------------------------------------------------------
 *
 * Gesetzt wird `colorScheme` am Browser-Kontext (= `prefers-color-scheme`),
 * NICHT der Theme-Schalter und NICHT `localStorage['eedc-theme']`.
 *
 *   * `ThemeProvider` startet auf `'system'` und spiegelt die Medienabfrage in
 *     `html.dark` (`frontend/src/context/ThemeContext.tsx:47-54`) — ein frischer
 *     Kontext folgt also ohne jeden Handgriff.
 *   * Die **Deep-Link-Ansicht** (`?fokus=…`) erzwingt `'system'` und ignoriert
 *     `localStorage` (ebenda, Z. 26-31 + 39). Ein ueber den Schalter gesetztes
 *     Theme wuerde dort NICHT wirken — `colorScheme` ist der einzige Weg, der
 *     fuer ALLE Ansichten dieser Liste gilt.
 *   * Kein Klickpfad, kein Wissen ueber die Schalter-Position: der Lauf bleibt
 *     stabil, wenn die Kopfzeile umgebaut wird.
 *
 * Nach jedem Laden prueft das Skript `html.dark` gegen die Erwartung und bricht
 * ab, wenn es nicht passt — ein Bild im falschen Modus faellt sonst erst beim
 * Betrachten auf.
 *
 * ---------------------------------------------------------------------------
 * 4. Umgebung
 * ---------------------------------------------------------------------------
 *
 *   EEDC_BASE   Basis-URL der Galerie-Box       (Vorgabe http://localhost:8201)
 *   OUT         Zielverzeichnis der Bilder      (Vorgabe website/src/assets/screenshots)
 *   ANLAGE      Name der Anlage in der Auswahl  (Vorgabe „Demo-Anlage")
 *   NUR         Kommaliste von Ansichts-Namen   (Vorgabe: alle)
 *   CHROME      Pfad zum Chromium               (Vorgabe: Playwright-Cache)
 *
 * ---------------------------------------------------------------------------
 * 5. Bekannte Grenze: die Gruppenkacheln (gemessen 28.09.2026)
 * ---------------------------------------------------------------------------
 *
 * Der Energiefluss buendelt Gleichartiges („Ost (2)", „Laden (2)") erst, wenn
 * seine KARTE schmaler als `DESKTOP_AB_PX = 500` ist
 * (`frontend/src/components/live/energieFlussLayout.ts:184`, ausgewertet in
 * `waehleStufen`). Gemessen mit der Demo-Anlage (6 PV + 6 Verbraucher):
 *
 *   Fenster 1600 … 600 px  → Karte 1152 … 566 px → KEINE Gruppen
 *   Fenster 520 px         → Karte  486 px       → Ost/Sued/West + Laden
 *
 * Deshalb tragen die beiden Gruppen-Ansichten unten ein schmales Fenster —
 * und `cockpit_main` (Desktop) zeigt die sechs Strings einzeln. Das ist keine
 * Wahl des Skripts, sondern der gemessene Stand des Layouts.
 */
import { createRequire } from 'node:module'
import { mkdirSync, statSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HIER = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HIER, '..')
const require = createRequire(resolve(REPO, 'eedc/frontend/package.json'))
const { chromium } = require('playwright-core')
// ⭐ KEINE neue Abhaengigkeit: `sharp` liegt bereits im Baum, weil Astro es fuer
// die Bildoptimierung der Website nutzt (`website/node_modules/sharp`, 0.34.5).
// Aufgeloest wird es deshalb ueber die package.json der Website — dasselbe
// Muster wie `playwright-core` ueber die des Frontends, eine Zeile darueber.
const requireWeb = createRequire(resolve(REPO, 'website/package.json'))
const sharp = requireWeb('sharp')

const CHROME = process.env.CHROME || '/home/gernot/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'
const BASE = (process.env.EEDC_BASE || 'http://localhost:8201').replace(/\/$/, '')
const OUT = process.env.OUT || resolve(REPO, 'website/src/assets/screenshots')
const ANLAGE = process.env.ANLAGE || 'Demo-Anlage'
const NUR = (process.env.NUR || '').split(',').map(s => s.trim()).filter(Boolean)

/** Standard-Fenster der Galerie (Desktop). */
const FENSTER = { width: 1400, height: 1000 }
/** Obergrenze fuer `hoehe: 'auto'` — darueber wird abgeschnitten statt ein
 *  7000 px hohes Bild zu erzeugen, das niemand ansieht (und das die
 *  Dateigroesse der Galerie sprengt). */
const MAX_HOEHE = 2400
/** WebP-Qualitaet. 88 ist gemessen der Punkt, an dem die Schrift in den
 *  Kacheln und die duennen Chart-Linien unverändert lesbar bleiben, der Ordner
 *  aber auf rund ein Fuenftel faellt (7,22 MB PNG → s. Bericht). Screenshots
 *  sind Anschauungsbilder, keine Messbilder — verlustbehaftet ist hier richtig. */
const WEBP_QUALITAET = 88

// ───────────────────────────────────────────────────────────────────────────
// Die Ansichtsliste — EINE Konstante, hier wird gepflegt.
//
//   name     Dateiname ohne Endung (`-dark` haengt das Skript an). VERTRAG.
//   route    Hash-Route hinter der Basis-URL.
//   fenster  Abweichendes Fenster (Vorgabe FENSTER).
//   hoehe    'auto' = Fenster auf den Inhalt wachsen lassen (bis MAX_HOEHE).
//   bg       Hintergrund-Variante des Energieflusses ('default' = Tech, 'haus' …).
//   klick    CSS-Selektor, der nach dem Laden angeklickt wird (fehlt er ⇒ ROT).
//   wegklicken  Selektoren, die weggeklickt werden, WENN es sie gibt (Hinweis-
//            banner nach einer Aenderung). Fehlen ist in Ordnung — sonst waere
//            der zweite Lauf auf derselben Datenbank rot.
//   fokus    Titel eines Blocks: dessen ⤢ wird gedrueckt (Fokus-/Vollbild).
//   ziel     CSS-Selektor: nur dieses Element ablichten (sonst das Fenster).
//   pflicht  Text, der im Bild stehen MUSS — sonst meldet der Lauf rot.
//   demo     true: die Sicht MUSS den Demo-Modus gezogen haben (`?demo=true`).
//            Fängt den teuersten Bedienfehler ab — mit einem Bundle OHNE
//            `VITE_DEMO_DEFAULT` rendert Cockpit/Live sauber, aber ueberall
//            „0 W", und `pflicht` merkt davon nichts (selbst passiert 28.09.).
// ───────────────────────────────────────────────────────────────────────────
const ANSICHTEN = [
  {
    name: 'cockpit_main',
    demo: true,
    route: '#/cockpit/live',
    bg: 'default',
    hoehe: 'auto',
    pflicht: ['Energiefluss', 'Stromnetz'],
    titel: 'Cockpit → Live mit dem Energiefluss (Variante „Tech")',
  },
  {
    name: 'cockpit_live_haus',
    demo: true,
    route: '#/cockpit/live',
    bg: 'haus',
    ziel: '[data-park-id="live:energiefluss"]',
    pflicht: ['Energiefluss'],
    titel: 'Derselbe Energiefluss vor der Variante „Haus"',
  },
  {
    name: 'cockpit_live_gruppenliste',
    // §5: Gruppenkacheln gibt es erst unter 500 px Kartenbreite.
    // Fensterhoehe GEMESSEN, nicht geraten (28.09.): das Overlay hat keine
    // Mindesthoehe (bei 320/360/420/560 px fuellt es jeweils das Fenster), und
    // sein Inhalt endet bei 262 px — Kopfzeile 80 + Liste 182. 290 px lassen
    // etwas Luft, ohne das halbe Bild weiss zu machen. Groessere Gruppen gaebe
    // es nicht: an `/api/live/1?demo=true` gemessen hat die Demo-Anlage nur
    // Zweiergruppen (3 x 2 PV-Ausrichtungen, 2 Wallboxen).
    demo: true,
    route: '#/cockpit/live',
    fenster: { width: 520, height: 290 },
    bg: 'default',
    klick: '[data-gruppe]',
    pflicht: ['Summe:'],
    titel: 'Gruppenkachel angetippt: die Liste mit Balken',
  },
  {
    name: 'cockpit_monat',
    route: '#/cockpit/monat',
    hoehe: 'auto',
    pflicht: ['Autarkie'],
    titel: 'Cockpit → Monat',
  },
  {
    name: 'cockpit_jahr',
    route: '#/cockpit/jahr',
    hoehe: 'auto',
    pflicht: ['Autarkie'],
    titel: 'Cockpit → Jahr',
  },
  {
    name: 'komponenten_speicher',
    route: '#/komponenten/speicher',
    hoehe: 'auto',
    pflicht: ['Speicher'],
    titel: 'Komponenten → Speicher',
  },
  {
    name: 'auswertungen_roi',
    route: '#/auswertungen/roi',
    hoehe: 'auto',
    pflicht: ['Amortisation'],
    titel: 'Auswertungen → ROI',
  },
  {
    name: 'aussichten_langfristig',
    route: '#/cockpit/aussicht',
    // Der Dateiname ist Vertrag (features.mdx) und meint die LANGFRIST-Sicht —
    // die Seite startet auf „Kurzfristig", also einmal umschalten. Nebeneffekt:
    // die Kurzfrist-Sicht zeigt auf einer Galerie-Box den Hinweis „fuer die
    // Verbrauchsprognose fehlt noch die Historie" (sie braucht 3 Tage
    // Energieprofil, die eine frische Demo-Box nicht hat).
    klick: 'button:has-text("Langfristig")',
    hoehe: 'auto',
    pflicht: ['Langfristig'],
    titel: 'Cockpit → Aussicht, Langfrist-Prognose',
  },
  {
    name: 'community_uebersicht',
    route: '#/community/uebersicht',
    hoehe: 'auto',
    pflicht: ['Community'],
    titel: 'Community → Übersicht',
  },
  {
    name: 'block_fokus',
    route: '#/cockpit/monat',
    fokus: 'Verlauf',
    pflicht: ['Fokus / Vollbild'],
    titel: 'Ein Block im Fokus-/Vollbild-Modus',
  },
  {
    name: 'einstellungen_datenquellen',
    route: '#/einstellungen/datenquellen',
    // Das Banner „Zuordnung geaendert — die bisherigen Werte bleiben" ist ein
    // voruebergehender Zustand nach einer Umstellung; der Anwender quittiert
    // ihn mit „Verstanden". Fuer die Galerie zaehlt der Dauerzustand.
    // ⚠ Die Quittung geht an den Server — deshalb NUR auf einer Demo-DB-KOPIE
    //   fahren (steht so im Kopf). Beim zweiten Lauf ist der Knopf weg; genau
    //   dafuer ist `wegklicken` und nicht `klick` gewaehlt.
    //
    // Dasselbe fuer „auf keine setzen": die Demo-DB traegt drei redundante
    // Aggregat-Zuordnungen (PV gesamt W · PV gesamt kWh · Netz kombiniert W),
    // die die Flaeche als „Wirkungslos: … Auf ,keine' setzen" meldet. Das ist
    // eine UNAUFGERAEUMTE ZUORDNUNG, kein Defekt — und die App bietet den
    // Handgriff selbst an.
    // ⛔ Vorher am Code geprueft (28.09.), dass dabei nichts Tragendes faellt:
    //   Der Knopf rendert AUSSCHLIESSLICH bei `p.art === 'redundant'`
    //   (`DatenquellenZuordnung.tsx:415`) und setzt nur die Quelle SEINER Zeile
    //   auf „keine". `redundant` vergibt das Backend nur, wenn das Aggregat
    //   wirklich ignoriert wird (`services/datenquellen_validierung.py::
    //   finde_redundante_aggregate`): PV-Live sobald eine Komponente
    //   `leistung_w` liefert, PV-Monat erst wenn JEDE aktive PV-Quelle ihren
    //   eigenen kWh-Wert hat (sonst fuellt das Aggregat Luecken), Netz-Kombi
    //   nur wenn Einspeisung UND Netzbezug einzeln zugeordnet sind. Die beiden
    //   benachbarten Kategorien `gesamtleistung_verdraengt` und
    //   `bkw_fuellt_luecken` sind im Code AUSDRUECKLICH nicht `redundant`,
    //   eben damit dieser Knopf dort NICHT erscheint (`api/datenquellen.ts`).
    wegklicken: [
      'button:has-text("Verstanden")',
      'button:has-text("auf keine setzen")',
    ],
    hoehe: 'auto',
    pflicht: ['Datenquellen'],
    titel: 'Einstellungen → Datenquellen',
  },
  {
    name: 'deeplink_karte',
    // FD-1 (docs/KONZEPT-FOKUS-DEEPLINK.md): so sieht der Block als
    // Webseiten-Karte in einem HA-Dashboard aus — schmales Fenster, kein
    // Zurueck, kein ⤢. Das Theme folgt hier zwingend dem System (§3).
    demo: true,
    route: '#/cockpit/live?fokus=live:energiefluss',
    fenster: { width: 520, height: 420 },
    bg: 'default',
    pflicht: ['Energiefluss'],
    titel: 'Fokus-Deep-Link als Webseiten-Karte (520 × 420)',
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Motiv „Dieselbe Anlage, drei Breiten" — die Kaskade, die ein einzelnes
  // Bild nicht zeigen kann.
  //
  // ⭐ Die drei Breiten sind ein MESSERGEBNIS, kein Richtwert. Gemessen am
  // 29.09.2026 ueber den Deep-Link, `[data-gruppe]` im DOM gezaehlt; die
  // Umschaltpunkte sind auf 1 px eingekreist:
  //
  //   Fenster ≥ 524 px (Karte ≥ 490)  → 0 Gruppen, 15 Knoten   ← alle einzeln
  //   Fenster 397 … 523 (Karte 363…489) → 4 Gruppen, 11 Knoten ← teilweise
  //   Fenster ≤ 396 px (Karte ≤ 362)  → 5 Gruppen, 10 Knoten   ← voll
  //
  // Gewaehlt sind drei Breiten mit Abstand zu beiden Kanten, damit ein
  // Rendering-Pixel das Motiv nicht kippt: 900 (376 px ueber der Kante),
  // 460 (63 bzw. 64 px Abstand nach beiden Seiten), 360 (36 px unter der
  // Kante, zugleich die klassische Handy-Breite).
  //
  // Die HOEHEN sind ebenfalls gerechnet, nicht geraten: die Zeichenflaeche
  // traegt je Breite ein anderes Seitenverhaeltnis (viewBox 618×380 · 450×380 ·
  // 360×380). Fenster = Kopfzeile + Breite/Seitenverhaeltnis + Rand, sonst
  // liegt der Fluss in weissen Baendern statt den Rahmen zu fuellen.
  //
  // ⛔ Der Deep-Link ist Absicht: er liefert den Block OHNE Kopfzeile und
  // Seitenleiste. Eine volle Seite bei 360 px waere eine lange Handy-Seite,
  // auf der man den Fluss erst suchen muesste — die drei Bilder waeren nicht
  // mehr vergleichbar.
  {
    name: 'breiten_gross',
    demo: true,
    route: '#/cockpit/live?fokus=live:energiefluss',
    fenster: { width: 900, height: 630 },
    bg: 'default',
    pflicht: ['Energiefluss', 'Poolpumpe', 'Sauna'],
    titel: 'Drei Breiten ① 900 px — jedes Gerät einzeln',
  },
  {
    name: 'breiten_mittel',
    demo: true,
    route: '#/cockpit/live?fokus=live:energiefluss',
    fenster: { width: 460, height: 462 },
    bg: 'default',
    // Die Gruppenkacheln tragen die Anzahl im Namen — „Ost (2)" steht also im
    // Text, sobald zusammengefasst wurde. Genau das soll das Bild zeigen.
    pflicht: ['Ost (2)', 'Laden (2)', 'Poolpumpe'],
    titel: 'Drei Breiten ② 460 px — Gleichartiges zusammengefasst',
  },
  {
    name: 'breiten_schmal',
    demo: true,
    route: '#/cockpit/live?fokus=live:energiefluss',
    fenster: { width: 360, height: 449 },
    bg: 'default',
    // Auf der letzten Stufe wandern auch Poolpumpe und Sauna in eine Kachel —
    // „Poolpumpe" darf hier also gerade NICHT mehr einzeln stehen.
    pflicht: ['Ost (2)', 'Laden (2)', 'Sonstige (2)'],
    titel: 'Drei Breiten ③ 360 px — auch die Verbraucher gebündelt',
  },
]

// ───────────────────────────────────────────────────────────────────────────

/** Wartet, bis sich Textmenge und Chart-Zahl ueber mehrere Takte nicht mehr
 *  aendern und kein Skeleton mehr im DOM steht — ein KRITERIUM statt einer
 *  Frist (dieselbe Lehre wie `check:chart-audit`, N-330: eine Wartezeit ist
 *  eine Wette auf die langsamste Maschine). */
async function ruhe(page, minStabil = 3, maxMs = 30000) {
  let stabil = 0
  let zuletzt = -1
  for (let v = 0; v < maxMs; v += 250) {
    await page.waitForTimeout(250)
    const { n, laedt } = await page.evaluate(() => ({
      n: document.body.innerText.length + document.querySelectorAll('.recharts-wrapper').length * 1000,
      laedt: !!document.querySelector('.animate-pulse, [role="status"]'),
    }))
    if (laedt) { stabil = 0; zuletzt = -1; continue }
    if (n === zuletzt) { if (++stabil >= minStabil) return } else { stabil = 0; zuletzt = n }
  }
}

/** Alle eingeklappten Bloecke oeffnen — ein zugeklappter Block ist kein Bild. */
async function alleAufklappen(page) {
  for (let i = 0; i < 6; i++) {
    const zu = await page.$$('button[aria-label="aufklappen"]')
    if (!zu.length) break
    for (const b of zu) { try { await b.click({ timeout: 500 }) } catch { /* verdeckt */ } }
    await ruhe(page, 1)
  }
  await ruhe(page)
}

/**
 * Den Demo-Umschalter in der Statuszeile ausblenden.
 *
 * ⚠ Das ist der einzige Eingriff des Skripts in die DARSTELLUNG (alles andere
 * sind Klicks, die auch ein Anwender macht), und er macht
 * das Bild ehrlicher, nicht schoener: der Knopf ist eine **Dev-Affordanz**, die
 * nur unter `?debug` oder in einem `VITE_DEMO_DEFAULT`-Build erscheint
 * (`frontend/src/v4/status/StatusFusszeile.tsx`, `isDebug`). Ein Anwender sieht
 * ihn im ausgelieferten Add-on NIE. Er waere im Bild also ein Artefakt der
 * Galerie-Box und keine Eigenschaft des Produkts.
 * ⛔ Nur `display:none` — der Demo-MODUS bleibt an, sonst zeigt Live „0 W".
 */
async function devAffordanzVerbergen(page) {
  await page.addStyleTag({
    content: 'button[title="Demo-Daten (Dev-Affordance) global ein/aus"]{display:none !important}',
  }).catch(() => { /* Seite schon fort */ })
}

/**
 * Jeden Scroll-Container an den Anfang setzen.
 *
 * Pflicht VOR dem Bild: `alleAufklappen` und `scrollIntoViewIfNeeded` rollen
 * den inneren Container weiter, und wenn der Inhalt hoeher bleibt als
 * MAX_HOEHE, bleibt er dort stehen — das Bild beginnt dann mitten in einem
 * Chart statt an der Kopfzeile (gemessen an Komponenten → Speicher, 28.09.).
 */
async function nachObenRollen(page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0)
    for (const e of document.querySelectorAll('*')) if (e.scrollTop) e.scrollTop = 0
  })
}

async function anlageWaehlen(page, name) {
  const btn = await page.$('button[aria-haspopup="listbox"]')
  if (!btn) return false
  const ist = (await btn.textContent() || '').trim()
  if (ist.includes(name)) return true
  await btn.click()
  await page.waitForTimeout(400)
  const opt = await page.$(`[role="option"]:has-text("${name}")`)
  if (!opt) return false
  await opt.click()
  await ruhe(page)
  return true
}

/** Hintergrund-Variante des Energieflusses setzen (Auswahlfeld im Kopf des
 *  Blocks, `EnergieFluss.tsx` — Werte aus `BG_VARIANTS`). */
async function hintergrundWaehlen(page, variante) {
  const sel = await page.$('select[title="Hintergrund wählen"]')
  if (!sel) return false
  await sel.selectOption(variante)
  await ruhe(page, 2)
  return true
}

/** Fenster auf den Inhalt wachsen lassen. Die App scrollt NICHT im Dokument,
 *  sondern in einem inneren Container (`lg:overflow-auto`) — `fullPage: true`
 *  liefert deshalb immer nur das Fenster (gemessen: scrollHeight des
 *  Dokuments == Fensterhoehe auf jeder Sicht). Also wird das Fenster
 *  vergroessert, bis der Container nicht mehr ueberlaeuft. */
async function hoeheAnpassen(page, breite, maxHoehe) {
  for (let runde = 0; runde < 4; runde++) {
    const fehlt = await page.evaluate(() => {
      let max = 0
      for (const e of document.querySelectorAll('*')) {
        if (e.clientHeight > 200 && e.scrollHeight > e.clientHeight + 4) {
          max = Math.max(max, e.scrollHeight - e.clientHeight)
        }
      }
      return max
    })
    if (fehlt <= 4) return page.viewportSize().height
    const neu = Math.min(maxHoehe, page.viewportSize().height + fehlt + 8)
    if (neu === page.viewportSize().height) return neu
    await page.setViewportSize({ width: breite, height: neu })
    await ruhe(page, 2)
  }
  return page.viewportSize().height
}

async function lauf() {
  mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ executablePath: CHROME, headless: true })
  const liste = NUR.length ? ANSICHTEN.filter(a => NUR.includes(a.name)) : ANSICHTEN
  if (NUR.length && liste.length !== NUR.length) {
    const fehlt = NUR.filter(n => !ANSICHTEN.some(a => a.name === n))
    throw new Error(`Unbekannte Ansicht(en) in NUR: ${fehlt.join(', ')}`)
  }
  let rot = 0
  const zeilen = []

  for (const modus of ['hell', 'dunkel']) {
    const suffix = modus === 'dunkel' ? '-dark' : ''
    for (const a of liste) {
      const fenster = a.fenster || FENSTER
      // Frischer Kontext je Bild: kein localStorage-Erbe (Theme, gewaehlte
      // Anlage, Hintergrund-Variante, Park-Zustand) aus dem Bild davor.
      const ctx = await browser.newContext({
        viewport: { ...fenster },
        colorScheme: modus === 'dunkel' ? 'dark' : 'light',
        deviceScaleFactor: 1,
        // Haelt Chart-Einlauf-Animationen still, damit kein Bild einen halb
        // gezeichneten Chart erwischt.
        reducedMotion: 'reduce',
      })

      // ⛔ …und macht damit einen Nebeneffekt noetig, der KEINE Schoenung ist,
      // sondern die Rueckname eines Artefakts dieses Werkzeugs:
      // `detectLiteDefault()` in `EnergieFluss.tsx` schaltet den Energiefluss
      // auf „Lite" (weniger Animationen, keine Fluss-Partikel, kein Leuchten),
      // sobald `prefers-reduced-motion: reduce` gilt — also genau wegen der
      // Zeile darueber. Ohne diese Vorbelegung zeigt JEDES Fluss-Bild der
      // Galerie einen Zustand, den ein Besucher ohne
      // Bewegungsreduzierungs-Einstellung nie sieht (gemessen 29.09.2026:
      // Probeaufnahme ohne `reduce` = „Effekte" mit Partikeln, mit `reduce`
      // = „Lite" ohne). Dieselbe Klasse wie der ausgeblendete Demo-Umschalter.
      // Der Anwender kann hier ohnehin selbst umschalten; `'0'` ist der Wert,
      // den ein Desktop-Browser ohne diese Einstellung von sich aus waehlt.
      await ctx.addInitScript(() => {
        try { localStorage.setItem('eedc-energiefluss-lite', '0') } catch { /* privater Modus */ }
      })

      const page = await ctx.newPage()
      const fehler = []
      let demoGesehen = false
      page.on('console', m => { if (m.type() === 'error') fehler.push(`console: ${m.text().slice(0, 140)}`) })
      page.on('response', r => {
        if (r.url().includes('/api/live/') && r.url().includes('demo=true') && r.status() === 200) demoGesehen = true
        if (r.status() >= 400 && r.url().includes('/api/')) fehler.push(`http ${r.status()} ${r.url().replace(BASE, '')}`)
      })

      try {
        await page.goto(`${BASE}/${a.route}`, { waitUntil: 'networkidle', timeout: 45000 })
        await ruhe(page)

        if (!a.route.includes('fokus=')) {
          if (!await anlageWaehlen(page, ANLAGE)) fehler.push(`Anlage „${ANLAGE}" nicht waehlbar`)
          await page.goto('about:blank')
          await page.goto(`${BASE}/${a.route}`, { waitUntil: 'networkidle', timeout: 45000 })
          await ruhe(page)
          await alleAufklappen(page)
        }

        // §3: der Modus muss am DOM ankommen, sonst ist das Bild wertlos.
        const istDunkel = await page.evaluate(() => document.documentElement.classList.contains('dark'))
        if (istDunkel !== (modus === 'dunkel')) {
          fehler.push(`Theme falsch: html.dark=${istDunkel}, erwartet ${modus === 'dunkel'}`)
        }

        if (a.bg && !await hintergrundWaehlen(page, a.bg)) fehler.push(`Hintergrund „${a.bg}" nicht setzbar`)

        // Aufraeumen in Runden. Zwei gemessene Gruende fuer die Runden
        // (28.09., beide beim ersten Versuch aufgelaufen):
        //  1. Die Zeilenliste baut sich nach jedem „auf keine setzen" neu auf;
        //     ein zweiter Klick auf den alten Knoten laeuft ins Leere, es blieb
        //     einer von drei Hinweisen stehen.
        //  2. Das Aufraeumen ERZEUGT das Banner „Zuordnung geaendert" neu —
        //     ein vorher geklicktes „Verstanden" waere also wieder da.
        // Deshalb: klicken, neu laden, erneut klicken, bis nichts mehr greift.
        // Das Neuladen nimmt zugleich den Zwischenzustand weg (eine eben
        // geleerte Zeile zeigt bis zum Neuaufbau rot „keine Quelle", obwohl
        // die Antwort danach `probleme: []` und `bedarf: inaktiv` meldet).
        if ((a.wegklicken || []).length) {
          for (let runde = 0; runde < 4; runde++) {
            let geklickt = 0
            for (const sel of a.wegklicken) {
              for (let i = 0; i < 10; i++) {
                const weg = await page.$(sel)
                if (!weg) break
                try { await weg.click({ timeout: 2000 }) } catch { break }
                geklickt++
                await ruhe(page, 2)
              }
            }
            if (!geklickt) break
            await page.goto('about:blank')
            await page.goto(`${BASE}/${a.route}`, { waitUntil: 'networkidle', timeout: 45000 })
            await ruhe(page)
            await alleAufklappen(page)
          }
        }

        if (a.klick) {
          const el = await page.$(a.klick)
          if (!el) fehler.push(`Klickziel fehlt: ${a.klick}`)
          else {
            try { await el.scrollIntoViewIfNeeded() } catch { /* SVG */ }
            await el.click()
            await ruhe(page, 2)
          }
        }

        // Ein Klick kann eine ANDERE Bloecke-Liste bringen (Aussicht:
        // Kurzfristig ⇄ Langfristig) — die neuen kommen zugeklappt.
        if (a.klick && !a.fokus && !a.route.includes('fokus=')) await alleAufklappen(page)

        if (a.fokus) {
          // Die ⤢-Knoepfe der BlockShell heissen ALLE „Fokus / Vollbild" — der
          // Block wird deshalb ueber seinen Titel gesucht, nicht ueber Position.
          const block = page.locator('section').filter({ hasText: a.fokus }).first()
          const knopf = block.locator('button[aria-label="Fokus / Vollbild"]').first()
          if (await knopf.count() === 0) fehler.push(`Block „${a.fokus}" ohne ⤢`)
          else { await knopf.click(); await ruhe(page, 2) }
        }

        // ⛔ Die Hoehe erst JETZT — nach allen Klicks. Vorher gemessen, waere
        // sie die Hoehe der Sicht VOR dem Klick (Aussicht/Kurzfristig ist
        // dreimal so hoch wie Langfristig ⇒ 1200 px Leerraum im Bild).
        if (a.hoehe === 'auto') await hoeheAnpassen(page, fenster.width, MAX_HOEHE)

        await devAffordanzVerbergen(page)
        await nachObenRollen(page)
        await ruhe(page, 2)

        const text = await page.evaluate(() => document.body.innerText)
        for (const p of (a.pflicht || [])) if (!text.includes(p)) fehler.push(`Text fehlt: „${p}"`)
        if (/NaN|undefined kWh|Infinity/.test(text)) fehler.push('NaN/undefined im Text')
        if (a.demo && !demoGesehen) {
          fehler.push('KEIN Demo-Modus — Bundle ohne VITE_DEMO_DEFAULT gebaut? Das Bild zeigt nur „0 W".')
        }

        // Playwright kann nur PNG/JPEG — das Bild kommt deshalb als Puffer
        // zurueck und geht durch `sharp` nach WebP (§6).
        const pfad = `${OUT}/${a.name}${suffix}.webp`
        let roh
        if (a.ziel) {
          const el = await page.$(a.ziel)
          if (!el) { fehler.push(`Zielelement fehlt: ${a.ziel}`); roh = await page.screenshot() }
          else roh = await el.screenshot()
        } else {
          roh = await page.screenshot()
        }
        await sharp(roh).webp({ quality: WEBP_QUALITAET }).toFile(pfad)
        const kb = Math.round(statSync(pfad).size / 1024)
        const gr = page.viewportSize()
        const ok = fehler.length === 0
        if (!ok) rot++
        zeilen.push(`${ok ? 'OK ' : 'ROT'} ${a.name}${suffix}  ${gr.width}x${gr.height}  ${kb} kB`)
        console.log(`${ok ? '  OK ' : '  ROT'} ${a.name}${suffix}  (${gr.width}x${gr.height}, ${kb} kB)`)
        for (const f of fehler.slice(0, 5)) console.log(`       ! ${f}`)
      } catch (e) {
        rot++
        zeilen.push(`ROT ${a.name}${suffix}  ${e.message}`)
        console.log(`  ROT ${a.name}${suffix}  ${e.message}`)
      } finally {
        await ctx.close()
      }
    }
  }

  await browser.close()
  console.log(`\n=== ${zeilen.length} Bilder nach ${OUT} · rot: ${rot}`)
  process.exit(rot ? 1 : 0)
}

await lauf()
