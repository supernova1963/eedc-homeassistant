/**
 * Zählerlücken wie HA — die Tagessicht im Client (Vorlage Fassung 7, §2, Schnitt 9).
 *
 * Fehlt in Home Assistant eine Stundenzeile, steht die Energie der Lücke in der
 * ersten Stunde danach — eedc legt genau das ab und schreibt die Spanne in
 * `StundenWert.spannen`. Der Client
 *
 *  - beschriftet eine solche Zeile in Tabelle und Chart („enthält n Stunden"),
 *  - nimmt die Σ-Zeile „Gesamtverbrauch" vom Server (HA-Formel, R7), weil
 *    Stunden mit verschiedenen Spannen keinen Stundenverbrauch tragen (R6),
 *  - zeigt den Hinweis „Verfügbare Energie" (N-94) **nur noch**, wenn der Tag
 *    etwas verworfen hat (R4) — eine fehlende Stunde allein macht die Summe
 *    nicht mehr zu niedrig,
 *  - sagt in der Reparatur-Rückmeldung, wie viel der neuen PV aus einer Lücke
 *    stammt,
 *  - nimmt in der Tages-Komponenten-Sicht den Zählerpfad vor dem
 *    Leistungspfad (BKW, Sonstiges).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  TagWerteTabelle, spanneDerZeile, summeVerbrauchTag, verworfenHerkunft,
} from './TagWerteTabelle'
import { baueChartDaten, stundenTooltipLabel } from './TagVerlaufChart'
import { baueTagesMeldung } from '../../pages/datenCheckerMeldungen'
import { baueTagAlsMonat } from '../../v4/TagKomponenten'
import { tagWerte } from '../../test/factories'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

const stunde = (h: number, over: Partial<StundenWert> = {}): StundenWert => ({
  stunde: h,
  pv_kw: null, verbrauch_kw: null, einspeisung_kw: null, netzbezug_kw: null,
  batterie_kw: null, waermepumpe_kw: null, wallbox_kw: null,
  ueberschuss_kw: null, defizit_kw: null,
  temperatur_c: null, globalstrahlung_wm2: null, soc_prozent: null,
  komponenten: null, wp_starts_anzahl: null, wp_betriebsstunden: null,
  ...over,
})

describe('spanneDerZeile — wie viele reale Stunden trägt die Zeile?', () => {
  it('1 ohne Spanne (die Zeile trägt ihre Stunde)', () => {
    expect(spanneDerZeile(stunde(3))).toBe(1)
    expect(spanneDerZeile(undefined)).toBe(1)
  })
  it('die größte Spanne über die Achsen', () => {
    expect(spanneDerZeile(stunde(3, { spannen: { pv: 3, netzbezug: 2 } }))).toBe(3)
  })
})

describe('summeVerbrauchTag — die Σ-Zeile ist der Tageswert vom Server (R7)', () => {
  it('Server-Wert gewinnt über die Stundensumme', () => {
    expect(summeVerbrauchTag(4.0, 12.5)).toBe(12.5)
  })
  it('Server sagt „nicht bildbar" ⇒ „—"', () => {
    expect(summeVerbrauchTag(4.0, null)).toBeNull()
  })
  it('ohne Tageswert bleibt die Stundensumme', () => {
    expect(summeVerbrauchTag(4.0, undefined)).toBe(4.0)
  })
})

describe('verworfenHerkunft — Hinweis N-94 nur bei verworfener Menge', () => {
  it('schweigt ohne verworfen und bei leerem {}', () => {
    expect(verworfenHerkunft(undefined)).toBeUndefined()
    expect(verworfenHerkunft(null)).toBeUndefined()
    expect(verworfenHerkunft({})).toBeUndefined()
  })
  it('schweigt bei einer Achse, die nicht in „Verfügbare Energie" eingeht', () => {
    expect(verworfenHerkunft({ wallbox: 1906.5, einspeisung: 33 })).toBeUndefined()
  })
  it('nennt verworfene PV (Lab 24.05.2026: SMA 37 kWh)', () => {
    const h = verworfenHerkunft({ pv: 37, einspeisung: 33 })
    expect(h).toBeDefined()
    expect(JSON.stringify(h)).toContain('PV 37,0 kWh')
  })
})

describe('TagWerteTabelle — gerendert', () => {
  // Ein-Achsen-Lücke (Lab 06.11.2025): Netzbezug trägt in Stunde 10 neun Stunden,
  // PV und Einspeisung eine ⇒ R6: kein Stundenverbrauch in dieser Zeile; der
  // Tag hat trotzdem einen Gesamtverbrauch nach HA-Formel.
  const daten: StundenWert[] = [
    stunde(9, { pv_kw: 1.0, netzbezug_kw: 0.2, einspeisung_kw: 0.1, verbrauch_kw: 1.1 }),
    stunde(10, { pv_kw: 1.5, netzbezug_kw: 4.0, einspeisung_kw: 0.2, verbrauch_kw: null, spannen: { netzbezug: 9 } }),
    // Stunde 11 fehlt ganz — früher löste das den N-94-Hinweis aus.
    stunde(12, { pv_kw: 2.0, netzbezug_kw: 0.1, einspeisung_kw: 0.4, verbrauch_kw: 1.7 }),
  ]
  // ⚠ `erzeugerSerien` stabil übergeben: der Default `= []` erzeugt je Render ein
  // neues Array, der Spalten-Effekt setzt daraufhin State — Endlosschleife,
  // sobald der Aufrufer die Prop weglässt (Nebenfund, CockpitTagV4 übergibt sie).
  const KEINE: SerieInfo[] = []

  it('Σ „Gesamtverbrauch" = Server-Tageswert, nicht die Stundensumme', () => {
    render(<TagWerteTabelle daten={daten} extraSerien={KEINE} erzeugerSerien={KEINE} datum="2025-11-06" gesamtverbrauchTag={9.6} verworfen={{}} />)
    expect(screen.getAllByText('9,60')).toHaveLength(1)
    // Die Stundensumme wäre 2,80. Sie steht jetzt nur noch EINMAL da — in der
    // Spalte „Hausverbrauch" (1,10 + 1,70), nicht mehr unter „Gesamtverbrauch".
    expect(screen.getAllByText('2,80')).toHaveLength(1)
  })

  it('Gegenprobe: ohne Server-Tageswert trägt die Σ-Zeile die Stundensumme', () => {
    render(<TagWerteTabelle daten={daten} extraSerien={KEINE} erzeugerSerien={KEINE} datum="2025-11-06" verworfen={{}} />)
    expect(screen.queryByText('9,60')).toBeNull()
    expect(screen.getAllByText('2,80')).toHaveLength(2)
  })

  it('beschriftet die gebündelte Zeile mit ihrer Spanne', () => {
    render(<TagWerteTabelle daten={daten} extraSerien={KEINE} erzeugerSerien={KEINE} datum="2025-11-06" gesamtverbrauchTag={9.6} verworfen={{}} />)
    expect(screen.getByText(/enthält 9 h/)).toBeInTheDocument()
    expect(screen.getAllByText(/enthält/)).toHaveLength(1)
  })

  it('kein Hinweis „Verfügbare Energie" bei fehlender Stunde, solange nichts verworfen ist', () => {
    render(<TagWerteTabelle daten={daten} extraSerien={KEINE} erzeugerSerien={KEINE} datum="2025-11-06" gesamtverbrauchTag={9.6} verworfen={{}} />)
    expect(screen.queryByText(/unplausible Zählermenge/)).toBeNull()
    expect(screen.queryByText(/nicht jede Stunde/i)).toBeNull()
  })

  it('Hinweis erscheint bei verworfener PV', () => {
    render(<TagWerteTabelle daten={daten} extraSerien={KEINE} erzeugerSerien={KEINE} datum="2025-11-06" gesamtverbrauchTag={9.6} verworfen={{ pv: 37 }} />)
    expect(screen.getAllByText(/unplausible Zählermenge/).length).toBeGreaterThan(0)
  })
})

describe('Tagesverlauf-Chart — gebündelter Balken ist beschriftet', () => {
  const daten: StundenWert[] = [
    stunde(3, { pv_kw: 0, netzbezug_kw: 1.0, einspeisung_kw: 0, spannen: { netzbezug: 2 } }),
    stunde(4, { pv_kw: 0, netzbezug_kw: 0.4, einspeisung_kw: 0 }),
  ]
  const punkte = baueChartDaten({
    daten, extraErzeuger: [], extraVerbraucher: [], erzeugerSerien: [],
    pvAufgeschluesselt: false, zeigePvRest: false,
  })

  it('der Tooltip nennt die Spanne des gebündelten Balkens', () => {
    expect(stundenTooltipLabel('3:00', punkte)).toBe('3:00 · enthält 2 Stunden (Lücke in Home Assistant)')
  })
  it('eine gewöhnliche Stunde bleibt „h:00"', () => {
    expect(stundenTooltipLabel('4:00', punkte)).toBe('4:00')
  })
  it('die Achse bleibt „h:00" (keine lange Beschriftung am Tick)', () => {
    expect(punkte[3].stunde).toBe('3:00')
  })
})

describe('Reparatur-Rückmeldung — Δ „aus einer Lücke"', () => {
  it('nennt den Anteil aus einer Lücke', () => {
    const m = baueTagesMeldung({ pv_kwh_alt: 10, pv_kwh_neu: 28, pv_kwh_aus_luecke: 18 }, '2025-11-05')
    expect(m.text).toContain('PV 10,0 → 28,0 kWh (davon 18,0 kWh aus einer Lücke in Home Assistant)')
  })
  it('schweigt ohne Lücken-Anteil (auch bei älterem Backend)', () => {
    expect(baueTagesMeldung({ pv_kwh_alt: 10, pv_kwh_neu: 28, pv_kwh_aus_luecke: 0 }, '2025-11-05').text)
      .not.toContain('Lücke')
    expect(baueTagesMeldung({ pv_kwh_alt: 10, pv_kwh_neu: 28 }, '2025-11-05').text).not.toContain('Lücke')
  })
})

describe('Tages-Komponenten — Zählerpfad vor Leistungspfad (§2)', () => {
  const BKW: SerieInfo[] = [{ key: 'bkw_7', label: 'Balkon', typ: 'balkonkraftwerk', kategorie: 'pv', seite: 'quelle' }]
  const stundenBkw = [stunde(12, { komponenten: { bkw_7: 1.2 } })]

  it('BKW aus dem Tageswert (Zählerpfad), wenn der Server ihn hat', () => {
    const d = baueTagAlsMonat(tagWerte('2025-11-06', { bkw: 3.4 }), stundenBkw, BKW)
    expect(d.bkw_erzeugung_kwh).toBe(3.4)
  })
  it('Rückfall auf die Stunden, wenn der Tageswert leer ist', () => {
    const d = baueTagAlsMonat(tagWerte('2025-11-06', { bkw: 0 }), stundenBkw, BKW)
    expect(d.bkw_erzeugung_kwh).toBe(1.2)
  })
  it('Sonstiges aus dem Tageswert', () => {
    const d = baueTagAlsMonat(
      tagWerte('2025-11-06', { sonstiges_erzeugung: 5.5, sonstiges_verbrauch: 2.0 }), [], [],
    )
    expect(d.sonstiges_erzeugung_kwh).toBe(5.5)
    expect(d.sonstiges_verbrauch_kwh).toBe(2.0)
  })
})
