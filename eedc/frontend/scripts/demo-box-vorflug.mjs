/**
 * demo-box-vorflug.mjs — die EINE Voraussetzungs-Prüfung der beiden Laufzeit-Gates.
 *
 * `park-leertest` und `chart-audit` messen beide gegen eine laufende Box mit einem
 * `VITE_DEMO_DEFAULT=true`-Bundle. Fehlt eine der beiden Hälften, messen sie **weniger,
 * als sie zu messen meinen** — und meldeten das bis 2026-08-27 verschieden:
 *
 *   • `park-leertest` brach ab (Vorflug, N-318).
 *   • `chart-audit` hatte **keinen** Vorflug. Am 27.08. gegen die reale Nicht-Demo-Box
 *     auf :8200 gemessen: **37 Charts, Exit 0, „16 Sichten geprueft"** — gegen die
 *     Demo-Box waren es am selben Tag **44**. Sieben Charts weniger, und die
 *     Schlussmeldung beziffert die Deckung, klingt also nach Messung.
 *
 * ⛔ Das Runbook behauptete, chart-audit habe „dieselbe Behandlung bekommen". Am
 * Verhalten widerlegt — aber **nicht am Exit-Code**: die `geprueftGesamt === 0`-Schwelle
 * gibt es dort seit N-318 und sie liefert korrekt Exit 1 (am 27.08. gegen eine tote Box
 * gemessen). Was fehlte, war die Stufe **davor**: „die Box ist die falsche" ist etwas
 * anderes als „die Box ist leer", und nur der zweite Fall war abgedeckt.
 *
 * ⭐ Deshalb steht die Prüfung HIER und nicht zweimal: eine Zusicherung, die zwei
 * Skripte je selbst formulieren, ist genau die Drift, die dieser Fund war. Wer eine
 * dritte Laufzeit-Prüfung baut, ruft diese Funktion — und erbt beide Ursachen-Texte.
 *
 * Merkmal ist der Demo-Schalter der Statusfußzeile; er rendert nur unter `isDebug`
 * (= `VITE_DEMO_DEFAULT`, oder `?debug`, das diese Läufe nicht setzen). An allen vier
 * Kombinationen gemessen (23.08., beim Bau des park-leertest-Vorflugs):
 *   • `dist` ohne das Flag     → Schalter fehlt (gemessen)
 *   • Box ohne Demo-Datenbank  → Einrichtungs-Assistent statt v4-Sicht, Schalter fehlt
 *   • beides in Ordnung        → Schalter da und aktiv
 * ⚠ Er unterscheidet die beiden Ursachen NICHT — die Meldung nennt deshalb beide, statt
 * eine zu behaupten. Eine erste Fassung behauptete „dist ohne Flag" und lag bei der
 * leeren Box daneben; die Gegenprobe hat es gezeigt.
 */

const DEMO_SCHALTER = 'button[title="Demo-Daten (Dev-Affordance) global ein/aus"]'

/**
 * Bricht den Lauf ab, wenn die Box nicht das ist, wogegen gemessen werden soll.
 *
 * @param {import('playwright-core').Browser} browser  offener Browser (wird bei Abbruch geschlossen)
 * @param {string} base      Basis-URL der Box ($EEDC_BASE)
 * @param {string} werkzeug  Name des aufrufenden Gates — steht in der Meldung
 */
export async function pruefeDemoBox(browser, base, werkzeug) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } })
  const seite = await ctx.newPage()
  let erreichbar = true
  try {
    await seite.goto(base + '/', { waitUntil: 'networkidle', timeout: 20000 })
  } catch {
    // Nicht erreichbar ist ebenfalls eine verletzte Voraussetzung — und zwar die,
    // die man am schnellsten selbst behebt. Sie darf nicht als „Schalter fehlt"
    // durchgehen, sonst schickt die Meldung in die falsche Richtung.
    erreichbar = false
  }
  let demo = { da: false, an: false }
  if (erreichbar) {
    await seite.waitForTimeout(2000)
    demo = await seite.evaluate((sel) => {
      const b = document.querySelector(sel)
      return { da: !!b, an: b?.getAttribute('aria-pressed') === 'true' }
    }, DEMO_SCHALTER)
  }
  await ctx.close()

  if (erreichbar && demo.da && demo.an) return

  await browser.close()
  console.error(`${werkzeug} — VORAUSSETZUNG VERLETZT: diese Box zeigt keine v4-Sicht mit`)
  console.error('Daten. Dieser Lauf würde weniger messen, als er zu messen meint, und darf')
  if (!erreichbar) {
    console.error(`deshalb nicht grün melden. Die Box unter ${base} war nicht erreichbar.`)
  } else {
    console.error('deshalb nicht grün melden. Zwei mögliche Ursachen, beide sind zu prüfen:')
    console.error('  1. `dist` ohne Demo-Flag →  VITE_DEMO_DEFAULT=true npm run build')
    console.error('  2. Box ohne Demo-Datenbank → DATABASE_URL=…/devbox-r27-demo.db (Runbook)')
    console.error(`  Gemessen: Demo-Schalter vorhanden=${demo.da}, aktiv=${demo.an}`)
  }
  process.exit(1)
}
