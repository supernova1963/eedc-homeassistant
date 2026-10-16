/**
 * Der Tag-Verlauf (Konzept §8, Bauschnitt 5) — dieselbe Funktion, x = Stunden.
 *
 * ⭐ **Der Gegenstand ist die Umbenennung, nicht eine Rechnung.** Die Stunden
 * verteilt das Backend (`tages_stapel.py`, „die Stunde verteilt den Tag"); der
 * Client benennt die Zeilen nur um und legt die Temperatur der Stundenantwort
 * daneben. Schwesterdateien: `waermeVerlauf.test.ts` (Jahr),
 * `waermeVerlaufMonat.test.ts` (Monat).
 *
 * ⚠ Bewusst NICHT am gerenderten Chart: Recharts zeichnet in jsdom nichts
 * (N-424, Sitzung 193).
 */
import { describe, it, expect } from 'vitest'
import { baueTagWaermeVerlauf } from './TagKomponenten'
import { baueWaermeVerlauf, verlaufRestZeilen, verlaufTitel, zeigtVerlauf } from './waermeVerlauf'
import type { StundenWert, WaermeVerlaufStunde } from '../api/energie_profil'

const zeile = (h: number, over: Partial<WaermeVerlaufStunde> = {}): WaermeVerlaufStunde => ({
  stunde: h,
  wp_strom_kwh: 0.6,
  wp_waerme_kwh: 1.5,
  wp_modus_strom_heizen_kwh: 0.5,
  wp_modus_strom_warmwasser_kwh: 0,
  wp_modus_strom_kuehlen_kwh: 0,
  wp_modus_strom_lueften_kwh: 0,
  wp_modus_strom_entfeuchten_kwh: 0,
  wp_modus_nicht_aufgeteilt_kwh: 0.1,
  wp_modus_strom_bezug_kwh: 0.6,
  wp_modus_abdeckung_h: 0,
  wp_modus_gemessen: true,
  ...over,
})

const stunde = (h: number, temperatur_c: number | null): StundenWert => ({
  stunde: h, pv_kw: null, verbrauch_kw: null, einspeisung_kw: null, netzbezug_kw: null,
  batterie_kw: null, waermepumpe_kw: null, wallbox_kw: null, ueberschuss_kw: null,
  defizit_kw: null, temperatur_c, globalstrahlung_wm2: null, soc_prozent: null,
  komponenten: null, wp_starts_anzahl: null, wp_betriebsstunden: null,
})

describe('Tag-Verlauf — dieselbe Funktion, 24 Stunden', () => {
  it('beschriftet die Slots wie der Stundenverlauf derselben Sicht (Bereich, HA-Bauform S4-E2 A)', () => {
    // Bestandstag (Ende-Raster): Slot 0 = [23, 24) des Vortags, Slot 23 = [22, 23).
    const punkte = baueTagWaermeVerlauf(Array.from({ length: 24 }, (_, h) => zeile(h)), [])
    expect(punkte).toHaveLength(24)
    expect(punkte[0].name).toBe('23–24')
    expect(punkte[23].name).toBe('22–23')
    // WP-Kanal-Tag (Beginn-Raster): Stunde 0 = [0, 1), Stunde 23 = [23, 24).
    const kanal = baueTagWaermeVerlauf(Array.from({ length: 24 }, (_, h) => zeile(h)), [], 'beginn')
    expect([kanal[0].name, kanal[23].name]).toEqual(['0–1', '23–24'])
  })

  it('nimmt die Temperatur aus der Stundenantwort — je Slot, nicht je Position', () => {
    const punkte = baueTagWaermeVerlauf(
      [zeile(5), zeile(6)],
      [stunde(6, -2.5), stunde(5, 1.0)],
    )
    expect(punkte[0].temperatur_c).toBe(1.0)
    expect(punkte[1].temperatur_c).toBe(-2.5)
  })

  it('kennt am Tag keine abgeleitete Wärme — die Linie ist gemessen', () => {
    const v = baueWaermeVerlauf(baueTagWaermeVerlauf([zeile(1), zeile(2)], []))
    expect(v.hatGemesseneWaerme).toBe(true)
    expect(v.rows[0].waerme).toBe(1.5)
  })

  it('summiert die Grundmenge über alle Stunden eines Tages mit Aufteilung', () => {
    // Das Tor ist das Tor des Tages: auch eine Stunde, die nur Rest trägt,
    // zählt mit — sonst verlöre der Stapel seine Summe gegenüber dem Balken.
    const zeilen = [
      zeile(0, { wp_modus_strom_heizen_kwh: 0, wp_modus_nicht_aufgeteilt_kwh: 0.1, wp_modus_strom_bezug_kwh: 0.1 }),
      zeile(1),
    ]
    const v = baueWaermeVerlauf(baueTagWaermeVerlauf(zeilen, []))
    expect(v.hatStapel).toBe(true)
    expect(v.bezugKwh).toBeCloseTo(0.7, 9)
    expect(v.rows[0].rest).toBe(0.1)
  })
})

// ─── Der Funktions-Stapel: eine Familie im Balken, nie zwei (WK-09 B2) ──────
//
// **SOLL §3.3/S2a** (abgenommen Gernot, 12.09.2026): Der Wärme/Klima-Verlauf
// zeigt je Stunde **entweder** den Strom nach Betriebsart (Teilmengen und Rest)
// **oder** nach Funktion (Summanden Heizen · Warmwasser · Übriger Strom) — nie
// beide Stapel zugleich, sonst addierte die Sicht Teilmengen zu Summanden
// (§3.2, der Fehler, an dem schon ein Tester gescheitert ist).
//
// ⭐ **Gemessen am Backend (12.09.2026)**: Ein Funktions-Zähler bekommt dieselbe
// Stundenform wie die Wärmelinie — 12 kWh Heizen in zwei Stunden liegen als
// 6,0/6,0 in Slot 6 und 18, nicht als 24 × 0,5. Diese Proben prüfen den Client:
// dass er die Familien trennt, den Umschalter nur mit Datenlage anbietet und im
// Titel nennt, was gerade im Balken liegt.

/** Eine Stunde mit BEIDEN Familien in der Antwort — die schärfste Lage. */
const zeileMitFunktion = (h: number, over: Partial<WaermeVerlaufStunde> = {}): WaermeVerlaufStunde =>
  zeile(h, {
    wp_funktion_strom_heizen_kwh: 0.4,
    wp_funktion_strom_warmwasser_kwh: 0.1,
    wp_funktion_uebrige_kwh: 0.1,
    ...over,
  })

describe('Wärme/Klima-Verlauf — Betriebsart oder Funktion (S2a)', () => {
  it('gibt es die Sicht „nach Funktion" nur mit Funktions-Zählern', () => {
    const ohne = baueWaermeVerlauf(
      baueTagWaermeVerlauf([zeile(6), zeile(7)], []),
    )
    expect(ohne.hatFunktionsStapel).toBe(false)
    // Und wer sie trotzdem anfordert, bekommt die voreingestellte Sicht —
    // nicht einen leeren Balken.
    const erzwungen = baueWaermeVerlauf(baueTagWaermeVerlauf([zeile(6)], []), 'funktion')
    expect(erzwungen.sicht).toBe('betriebsart')

    const mit = baueWaermeVerlauf(
      baueTagWaermeVerlauf([zeileMitFunktion(6), zeileMitFunktion(7)], []),
    )
    expect(mit.hatFunktionsStapel).toBe(true)
  })

  it('legt NIE beide Familien in denselben Stapel', () => {
    const punkte = baueTagWaermeVerlauf([zeileMitFunktion(6), zeileMitFunktion(7)], [])
    const betriebsart = baueWaermeVerlauf(punkte, 'betriebsart').stapel.map((s) => s.key)
    const funktion = baueWaermeVerlauf(punkte, 'funktion').stapel.map((s) => s.key)
    // Beide Sichten haben etwas zu sagen …
    expect(betriebsart.length).toBeGreaterThan(0)
    expect(funktion.length).toBeGreaterThan(0)
    // … und keine einzige Serie kommt in beiden vor.
    expect(betriebsart.filter((k) => funktion.includes(k))).toEqual([])
    expect(betriebsart).toContain('heizen')
    expect(funktion).toEqual(['f_heizen', 'f_warmwasser', 'f_uebrige'])
  })

  it('trägt in der Funktions-Sicht die Einzelwerte der Stunde', () => {
    const punkte = baueTagWaermeVerlauf([
      zeileMitFunktion(6, { wp_funktion_strom_heizen_kwh: 6.0, wp_funktion_strom_warmwasser_kwh: 0, wp_funktion_uebrige_kwh: 0.1 }),
      zeileMitFunktion(7, { wp_funktion_strom_heizen_kwh: 0, wp_funktion_strom_warmwasser_kwh: 1.0, wp_funktion_uebrige_kwh: 0.1 }),
    ], [])
    const d = baueWaermeVerlauf(punkte, 'funktion')
    expect(d.rows[0].f_heizen).toBe(6)
    expect(d.rows[0].f_warmwasser).toBe(0)
    expect(d.rows[0].f_uebrige).toBe(0.1)
    expect(d.rows[1].f_heizen).toBe(0)
    expect(d.rows[1].f_warmwasser).toBe(1)
    // ⛔ Die Segmente der anderen Familie stehen NICHT in der Zeile.
    expect(d.rows[0].heizen).toBeUndefined()
    expect(d.rows[0].rest).toBeUndefined()
  })

  it('nennt im Titel, welche Größe gerade gestapelt ist (S2)', () => {
    const punkte = baueTagWaermeVerlauf([zeileMitFunktion(6)], [])
    expect(verlaufTitel(baueWaermeVerlauf(punkte, 'betriebsart')))
      .toContain('Strom nach Betriebsart')
    expect(verlaufTitel(baueWaermeVerlauf(punkte, 'funktion')))
      .toContain('Strom nach Funktion')
    // Die Linien bleiben in beiden Sichten — sie sind keine Familie des Stapels.
    for (const sicht of ['betriebsart', 'funktion'] as const) {
      const d = baueWaermeVerlauf(punkte, sicht)
      expect(d.linien.map((l) => l.key)).toContain('waerme')
    }
  })

  it('macht den Verlauf sichtbar, wo NUR die Funktions-Sicht etwas hat (Sprosse F5)', () => {
    // Getrennte Funktions-Zähler, aber kein Betriebsart-Zähler und kein
    // Modus-Signal: ohne diese Regel bliebe genau der Fall unsichtbar, für den
    // die zweite Sicht gebaut wurde (S3).
    const nurFunktion = zeile(6, {
      wp_modus_gemessen: false, wp_modus_abdeckung_h: 0, wp_waerme_kwh: null,
      wp_funktion_strom_heizen_kwh: 0.4,
      wp_funktion_strom_warmwasser_kwh: 0.1,
      wp_funktion_uebrige_kwh: 0.1,
    })
    const punkte = baueTagWaermeVerlauf([nurFunktion], [])
    const d = baueWaermeVerlauf(punkte)
    expect(d.hatStapel).toBe(false)          // Betriebsart hat nichts
    expect(d.hatFunktionsStapel).toBe(true)
    expect(zeigtVerlauf(d, null)).toBe(true)
  })

  it('nennt die Funktions-Menge ohne Stundenzuordnung eigens (P4)', () => {
    expect(verlaufRestZeilen({ funktion: 2.0 }).map((r) => r.label))
      .toEqual(['Strom je Funktion ohne Stundenzuordnung'])
    expect(verlaufRestZeilen({ funktion: 0.01 })).toEqual([])
  })
})
