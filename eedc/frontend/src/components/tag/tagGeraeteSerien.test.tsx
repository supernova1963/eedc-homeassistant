import { describe, it, expect } from 'vitest'
import { baueChartSerien } from './TagVerlaufChart'
import { angeboteneSpalten, erfassteSenken } from './TagWerteTabelle'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

// ─── Wärmepumpe und Wallbox erscheinen nur, wenn es sie gibt ────────────────
//
// **Melder: JayJayX (simon42 T89667 #307 / #309, 08.09.2026).** Wörtlich: *„ich
// besitze aktuell weder Wärmepumpe noch Wallbox, diese tauchen aber trotzdem
// immer in den Statistiken auf"* — und auf die Rückfrage nach dem Ort: *„In
// Cockpit/Tag/Stundenverlauf werden mir Wallbox und Wärmepumpe angezeigt und
// laufen parallel zum Hausverbrauch."*
//
// **Warum ausgerechnet diese beiden.** Jedes andere Gerät reist als `extraSerien`
// an, und die füllt das Backend nur für Komponenten, die am Tag etwas beigetragen
// haben. `waermepumpe_kw`/`wallbox_kw` sind die zwei **dedizierten** Felder ohne
// solche Deklaration: im Chart standen sie unbedingt im Stapel, in der Tabelle
// unbedingt als Spalte (`defaultVisible: true`).
//
// ⭐ **Das Vorbild lag im Baum:** Cockpit → Live filtert seine Verbrauchs-
// kategorien seit jeher auf `vorhandeneKategorien` (`WetterWidget`). Die
// Tages-Sicht stellte dieselbe Frage nicht — obwohl `erfassteSenken` sie seit
// N-95 direkt daneben beantwortet, bis hierher aber nur für den Hausverbrauch
// gelesen wurde.
//
// ⚑ **Warum reine Funktionen und kein gerendertes DOM** (gemessen 09.09.2026):
// Recharts zeichnet in jsdom nichts (`ResponsiveContainer` hat dort Breite 0),
// eine Probe „Legendeneintrag fehlt" wäre also grün, ohne je etwas gemessen zu
// haben — und bliebe grün, wenn die Serie zurückkäme. Die Stundenwerte-Tabelle
// lässt sich in dieser Umgebung überhaupt nicht rendern, auch unverändert nicht;
// deshalb prüfen die bestehenden Proben dieser Fläche ausschließlich reine
// Funktionen, und diese hier tut es genauso.
//
// ⛔ **Was hier NICHT geprüft wird, weil es kein Fehler ist:** dass eine
// abgewählte Legenden-Serie nach einem Rerender zurückkommt. Die Flüchtigkeit
// des Legenden-Toggles ist Style-Guide B7 und eine belegte Entscheidung
// (Gernot, 08.07.2026, „KEINE C4-Persistenz") — sie bleibt.

const stunde = (over: Partial<StundenWert> = {}): StundenWert => ({
  stunde: 12,
  pv_kw: 4.2, verbrauch_kw: 1.4, einspeisung_kw: 2.8, netzbezug_kw: 0,
  batterie_kw: 0, waermepumpe_kw: null, wallbox_kw: null,
  ueberschuss_kw: null, defizit_kw: null,
  temperatur_c: null, globalstrahlung_wm2: null, soc_prozent: null,
  komponenten: null, wp_starts_anzahl: null, wp_betriebsstunden: null,
  ...over,
})

/** JayJayX: PV und Hausverbrauch, sonst nichts. */
const TAG_OHNE_GERAETE = [stunde({ stunde: 11 }), stunde({ stunde: 12 })]

/** Dieselbe Anlage, aber mit beiden Geräten am Zähler. */
const TAG_MIT_GERAETEN = [
  stunde({ stunde: 11, waermepumpe_kw: 0.6, wallbox_kw: 0 }),
  stunde({ stunde: 12, waermepumpe_kw: 0.9, wallbox_kw: 3.1 }),
]

const KEINE_EXTRA: SerieInfo[] = []

function serien(daten: StundenWert[]) {
  return baueChartSerien({
    pvAufgeschluesselt: false,
    zeigePvRest: false,
    erzeugerSerien: [],
    extraErzeuger: [],
    extraVerbraucher: KEINE_EXTRA,
    senkenErfasst: erfassteSenken(daten, KEINE_EXTRA),
  }).map(s => s.dataKey)
}

function spalten(daten: StundenWert[]) {
  return angeboteneSpalten(erfassteSenken(daten, KEINE_EXTRA)).map(c => c.key)
}

describe('Stundenverlauf — Gerätesenken ohne Gerät', () => {
  it('stapelt weder Wärmepumpe noch Wallbox, wenn der Tag keine kennt', () => {
    expect(serien(TAG_OHNE_GERAETE)).not.toContain('wp')
    expect(serien(TAG_OHNE_GERAETE)).not.toContain('wb')
  })

  it('stapelt beide, sobald der Tag Werte trägt — die Gegenprobe', () => {
    // Ohne sie belegte die Probe darüber nur, dass irgendetwas fehlt.
    expect(serien(TAG_MIT_GERAETEN)).toContain('wp')
    expect(serien(TAG_MIT_GERAETEN)).toContain('wb')
  })

  it('lässt die übrigen Serien unberührt', () => {
    // Der Fix darf nur die zwei Gerätesenken betreffen — Bilanzgrößen bleiben.
    for (const key of ['pv', 'bat_pos', 'bat_neg', 'netz_pos', 'netz_neg', 'hausverbrauch'])
      expect(serien(TAG_OHNE_GERAETE)).toContain(key)
  })

  it('unterscheidet die Messlücke vom fehlenden Gerät', () => {
    // Eine einzelne Stunde ohne Wert ist eine Lücke, kein fehlendes Gerät —
    // dieselbe Trennung, die `erfassteSenken` für den Hausverbrauch zieht.
    const tag = [stunde({ stunde: 11, waermepumpe_kw: null }), stunde({ stunde: 12, waermepumpe_kw: 0.9 })]
    expect(serien(tag)).toContain('wp')
  })

  it('zählt eine gemessene 0 als vorhanden', () => {
    // Eine Wallbox, die den ganzen Tag nicht geladen hat, gibt es trotzdem —
    // „kein Key heißt None, nicht 0" (`core/berechnungen/energie.py`).
    const tag = [stunde({ stunde: 11, wallbox_kw: 0 }), stunde({ stunde: 12, wallbox_kw: 0 })]
    expect(serien(tag)).toContain('wb')
  })
})

describe('Stundenwerte-Tabelle — Gerätespalten ohne Gerät', () => {
  it('bietet die Spalten nicht an, wenn der Tag keine kennt', () => {
    expect(spalten(TAG_OHNE_GERAETE)).not.toContain('waermepumpe_kw')
    expect(spalten(TAG_OHNE_GERAETE)).not.toContain('wallbox_kw')
  })

  it('bietet sie an, sobald der Tag Werte trägt — die Gegenprobe', () => {
    expect(spalten(TAG_MIT_GERAETEN)).toContain('waermepumpe_kw')
    expect(spalten(TAG_MIT_GERAETEN)).toContain('wallbox_kw')
  })

  it('lässt alle übrigen Spalten stehen', () => {
    const ohne = spalten(TAG_OHNE_GERAETE)
    const mit = spalten(TAG_MIT_GERAETEN)
    expect(mit.length - ohne.length).toBe(2)
    for (const key of ['pv_kw', 'verbrauch_kw', 'hausverbrauch', 'netzbezug_kw'])
      expect(ohne).toContain(key)
  })
})
