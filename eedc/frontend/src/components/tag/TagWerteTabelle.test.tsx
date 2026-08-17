/**
 * Stundenwerte-Tabelle — der Hausverbrauch ist eine Differenz.
 *
 * Befund (PN Rainer 89905, gefunden an coolxmads Screenshot): in den Stunden 0–7
 * stand **PV „—"**, Batterie 0,27 kW, Netzbezug 0,01 kW — und **Hausverbrauch 0,00**,
 * während die Nachbarspalte „Gesamtverbrauch" für dieselbe Stunde „—" zeigte. Zwei
 * verwandte Spalten, zwei Antworten auf denselben fehlenden Wert.
 *
 * Ursache war `(s.verbrauch_kw ?? 0)`: das Backend liefert `verbrauch_kw` bewusst als
 * `null`, solange die Bilanz nicht vollständig ist (`snapshot/aggregator.py`), der
 * Client machte daraus eine 0. Regel jetzt: Differenz ⇒ unterdrücken
 * (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3).
 */
import { describe, it, expect } from 'vitest'
import { berechneHausverbrauch, alsAnzeigewert } from './TagWerteTabelle'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

const stunde = (over: Partial<StundenWert> = {}): StundenWert => ({
  stunde: 3,
  pv_kw: null, verbrauch_kw: null, einspeisung_kw: null, netzbezug_kw: null,
  batterie_kw: null, waermepumpe_kw: null, wallbox_kw: null,
  ueberschuss_kw: null, defizit_kw: null,
  temperatur_c: null, globalstrahlung_wm2: null, soc_prozent: null,
  komponenten: null, wp_starts_anzahl: null, wp_betriebsstunden: null,
  ...over,
})

const KEINE_EXTRA: SerieInfo[] = []
const POOL: SerieInfo[] = [
  { key: 'pool_9', label: 'Poolpumpe', typ: 'sonstiges', kategorie: 'sonstige', seite: 'senke' },
]

describe('berechneHausverbrauch — Lücke statt Nullwert', () => {
  it('rechnet bei vollständiger Stunde wie bisher', () => {
    const s = stunde({ verbrauch_kw: 2.5, waermepumpe_kw: 0.8, wallbox_kw: 0.2 })
    expect(berechneHausverbrauch(s, KEINE_EXTRA)).toBe(1.5)
  })

  it('unterdrückt den Wert, wenn der Gesamtverbrauch fehlt — genau Rainers Fall', () => {
    // Netz und Batterie messen weiter, die PV nicht ⇒ Backend liefert `verbrauch_kw: null`.
    const s = stunde({ verbrauch_kw: null, batterie_kw: 0.27, netzbezug_kw: 0.01 })
    expect(berechneHausverbrauch(s, KEINE_EXTRA)).toBeNull()
  })

  it('unterdrückt auch dann, wenn Wärmepumpe und Wallbox gemessen haben', () => {
    // Vorher: max(0, 0 − 1,2 − 3,4) = 0 ⇒ die Tabelle schrieb „0,00" neben ein „—".
    const s = stunde({ verbrauch_kw: null, waermepumpe_kw: 1.2, wallbox_kw: 3.4 })
    expect(berechneHausverbrauch(s, KEINE_EXTRA)).toBeNull()
  })

  it('behält eine gemessene 0 als 0 — sie ist eine Aussage, keine Lücke', () => {
    const s = stunde({ verbrauch_kw: 0, waermepumpe_kw: 0, wallbox_kw: 0 })
    expect(berechneHausverbrauch(s, KEINE_EXTRA)).toBe(0)
  })

  it('behandelt eine fehlende Wärmepumpe weiter als 0 — sonst verstummte jede Anlage ohne WP', () => {
    const s = stunde({ verbrauch_kw: 2.0, waermepumpe_kw: null, wallbox_kw: null })
    expect(berechneHausverbrauch(s, KEINE_EXTRA)).toBe(2.0)
  })

  it('zieht sonstige Senken weiterhin ab', () => {
    const s = stunde({ verbrauch_kw: 3.0, komponenten: { pool_9: -0.5 } })
    expect(berechneHausverbrauch(s, POOL)).toBe(2.5)
  })

  it('bleibt bei negativer Differenz auf 0 geklemmt', () => {
    const s = stunde({ verbrauch_kw: 1.0, waermepumpe_kw: 2.0 })
    expect(berechneHausverbrauch(s, KEINE_EXTRA)).toBe(0)
  })
})

/**
 * N-261 — die Tabelle zeigt Verbrauch, nicht die Diagramm-Konvention.
 *
 * `TagesEnergieProfil.komponenten` trägt für jede Senke ein Minus, weil der
 * Live-Tagesverlauf ein Butterfly-Diagramm ist (Quellen oben, Senken unten).
 * In der Stundentabelle behauptet dasselbe Minus „so viel wurde nicht
 * verbraucht" — rapahl sah seinen Heizstab mit Σ −5,59 kWh.
 */
describe('alsAnzeigewert (N-261: Butterfly-Vorzeichen abstreifen)', () => {
  it('macht aus der negativen Senke einen Verbrauch', () => {
    expect(alsAnzeigewert(-3.14, 'senke')).toBe(3.14)
    expect(alsAnzeigewert(-5.59, 'senke')).toBe(5.59)
  })

  it('lässt eine bereits positive Senke unverändert', () => {
    // Der Zähler-Pfad liefert von Bauart positiv (`max(0.0, delta)`). Nach dem
    // Umhängen auf ihn darf hier nichts kippen.
    expect(alsAnzeigewert(3.0, 'senke')).toBe(3.0)
  })

  it('lässt Quellen unangetastet — auch eine negative', () => {
    // Kein blindes Math.abs: Eine negative Quelle wäre ein Datenfehler und soll
    // sichtbar bleiben, statt als Erzeugung durchzugehen.
    expect(alsAnzeigewert(4.03, 'quelle')).toBe(4.03)
    expect(alsAnzeigewert(-0.5, 'quelle')).toBe(-0.5)
  })

  it('lässt bidirektionale Serien ihr Vorzeichen — dort IST es die Aussage', () => {
    expect(alsAnzeigewert(-2.34, 'bidirektional')).toBe(-2.34)
    expect(alsAnzeigewert(1.26, 'bidirektional')).toBe(1.26)
  })

  it('macht aus einer Lücke keine 0', () => {
    expect(alsAnzeigewert(null, 'senke')).toBeNull()
    expect(alsAnzeigewert(undefined, 'senke')).toBeNull()
  })

  it('rührt die Hausverbrauchs-Rechnung NICHT an', () => {
    // Die Trennlinie des Pakets: `berechneHausverbrauch` liest die Rohwerte und
    // braucht das Minus. Würde es dieselbe Aufbereitung sehen, zöge es den
    // Sonstiges-Verbraucher zweimal ab (0,8 statt 1,3).
    const s = stunde({ verbrauch_kw: 2.0, komponenten: { pool_9: -0.5 } })
    expect(berechneHausverbrauch(s, POOL)).toBe(1.5)
  })
})
