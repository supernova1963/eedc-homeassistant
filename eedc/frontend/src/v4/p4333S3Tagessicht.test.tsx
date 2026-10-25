/**
 * P-433-3 Sitzung 3 (#432) — Tagessicht Wärme/Klima im Client: «AZ heute», Herleitung je Funktion, Wärme-Stapel nach
 * Funktion neben dem Strom-Stapel, Temperatur-Diagramm je Gerät (Hülle `WaermeVerlaufChart`), «Zahlen je Gerät» erst
 * ab zwei Geräten, eine Herleitungs-Formatierung für Tag und Hub (S3-9).
 *
 * Der Client rechnet nichts: Stundenmittel, Spreizung, Ø Vorlauf/Ø Spreizung, Rest-Segment, Zähler/Nenner kommen aus
 * dem Backend (Proben `test_p433_3_s3_tagessicht.py`). Hier wird geprüft, dass sie ankommen und richtig benannt stehen.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { baueKomponentenBloecke } from './KomponentenSektionen'
import { baueTagAlsMonat, baueTagWaermeVerlauf } from './TagKomponenten'
import { baueWaermeVerlauf, verlaufTitel } from './waermeVerlauf'
import { baueTemperaturDiagramm, geraeteMitTemperaturen, temperaturKopf } from './waermeTemperaturen'
import { herleitungMengen, wpFunktionsGruppen } from './wpFunktionsGruppen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { TagDetail, WaermeTemperaturGeraet, WaermeTemperaturStunden, WaermeVerlaufStunde } from '../api/energie_profil'
import { aktuellerMonat, tagWerte } from '../test/factories'
import { CHART_COLORS } from '../lib'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}
const d = (over: Partial<AktuellerMonatResponse>) => aktuellerMonat(2026, 10, over)
const TAG: Partial<AktuellerMonatResponse> = {
  wp_strom_kwh: 6, wp_waerme_kwh: 26, wp_jaz: 4.33, wp_jaz_zaehler_kwh: 26, wp_jaz_nenner_kwh: 6,
}

function wpBlock(over: Partial<AktuellerMonatResponse>, periode: 'tag' | 'monat' = 'tag',
  temperaturen?: WaermeTemperaturStunden | null) {
  return baueKomponentenBloecke(d(over), NOOP, periode, null, null, null, null, temperaturen)
    .find((b) => b.id === 'k-waermepumpe')
}

// ── S3-6 «AZ heute» ─────────────────────────────────────────────────────────

describe('KPI «AZ heute» nur am Tag', () => {
  it('Tag: «AZ heute», Kopfzeile ebenso; Monat: «JAZ»', () => {
    const tag = wpBlock(TAG)!
    render(<>{tag.render(false)}</>)
    expect(screen.getByText('AZ heute')).toBeInTheDocument()
    expect(screen.queryByText('JAZ')).toBeNull()
    expect(tag.summary).toMatch(/^AZ heute 4,33 · /)
    const monat = wpBlock(TAG, 'monat')!
    expect(monat.summary).toMatch(/^JAZ 4,33 · /)
  })
})

// ── S3-5/S3-6 Herleitung je Funktion ────────────────────────────────────────

describe('Herleitung je Funktion in «Je Funktion»', () => {
  const MIT_FUNKTION: Partial<AktuellerMonatResponse> = {
    ...TAG, wp_strom_heizen_kwh: 3, wp_heizung_kwh: 12, wp_jaz_heizen: 4,
    wp_jaz_heizen_zaehler_kwh: 12, wp_jaz_heizen_nenner_kwh: 3,
    wp_strom_warmwasser_kwh: 1, wp_warmwasser_kwh: 2, wp_jaz_warmwasser: 2,
    wp_jaz_warmwasser_zaehler_kwh: 2, wp_jaz_warmwasser_nenner_kwh: 1,
    wp_modus_strom_kuehlen_kwh: 2, wp_kaelte_kwh: 7, wp_jaz_kuehlen: 3.5,
    wp_jaz_kuehlen_zaehler_kwh: 7, wp_jaz_kuehlen_nenner_kwh: 2,
  }

  it('je Arbeitszahl Zähler ÷ Nenner des Layers — Kühlen mit «Kälte»', () => {
    const fg = wpFunktionsGruppen(d(MIT_FUNKTION))
    const az = (f: string) => fg.gruppen.find((g) => g.funktion === f)!.zeilen.find((z) => z.art === 'arbeitszahl')!
    expect(az('heizen')).toMatchObject({ herleitung: '12,0 kWh Wärme ÷ 3,0 kWh Strom' })
    expect(az('warmwasser')).toMatchObject({ herleitung: '2,0 kWh Wärme ÷ 1,0 kWh Strom' })
    expect(az('kuehlen')).toMatchObject({ herleitung: '7,0 kWh Kälte ÷ 2,0 kWh Strom' })
  })

  it('gerendert als title der Zahl; ohne Zähler/Nenner (Monat) keine Herleitung', () => {
    render(<>{wpBlock(MIT_FUNKTION)!.render(false)}</>)
    expect(screen.getByText('4,00').getAttribute('title')).toBe('12,0 kWh Wärme ÷ 3,0 kWh Strom')
    const ohne = wpFunktionsGruppen(d({ ...MIT_FUNKTION, wp_jaz_heizen_zaehler_kwh: null, wp_jaz_heizen_nenner_kwh: null }))
    expect(ohne.gruppen[0].zeilen.find((z) => z.art === 'arbeitszahl')).not.toHaveProperty('herleitung', expect.any(String))
  })

  it('baueTagAlsMonat reicht Zähler/Nenner je Funktion der Tagesantwort durch', () => {
    const t = baueTagAlsMonat(tagWerte('2026-10-24', { wp_strom: 6 }), [], [], {
      wp_jaz_heizen: 4, wp_jaz_heizen_zaehler_kwh: 12, wp_jaz_heizen_nenner_kwh: 3,
      wp_jaz_kuehlen_zaehler_kwh: 7, wp_jaz_kuehlen_nenner_kwh: 2,
    } as TagDetail)
    expect([t.wp_jaz_heizen_zaehler_kwh, t.wp_jaz_heizen_nenner_kwh, t.wp_jaz_kuehlen_zaehler_kwh]).toEqual([12, 3, 7])
  })
})

// ── S3-9 eine Herleitung für Tag und Hub ────────────────────────────────────

describe('S3-9: Herleitung Tag und Hub zeichengleich', () => {
  it('ungerundete Mengen ⇒ eine Nachkommastelle, beide Sichten dieselbe Funktion', () => {
    expect(herleitungMengen(2560.04, 560.03)).toBe('2.560,0 kWh Wärme ÷ 560,0 kWh Strom')
    expect(herleitungMengen(25.6, 5.6)).toBe('25,6 kWh Wärme ÷ 5,6 kWh Strom')
    expect(herleitungMengen(null, 5.6)).toBeNull()
  })
})

// ── S3-4/S3-6 Wärme-Stapel nach Funktion ────────────────────────────────────

const stunde = (h: number, over: Partial<WaermeVerlaufStunde>): WaermeVerlaufStunde => ({
  stunde: h, wp_strom_kwh: 1, wp_waerme_kwh: null, wp_modus_strom_heizen_kwh: null, wp_modus_strom_warmwasser_kwh: null,
  wp_modus_strom_kuehlen_kwh: null, wp_modus_strom_lueften_kwh: null, wp_modus_strom_entfeuchten_kwh: null,
  wp_modus_nicht_aufgeteilt_kwh: null, wp_modus_strom_bezug_kwh: null, wp_modus_abdeckung_h: null,
  wp_modus_gemessen: null, ...over,
})
const FUNKTIONS_STUNDEN = [
  stunde(6, { wp_waerme_kwh: 7, wp_funktion_strom_heizen_kwh: 1, wp_funktion_strom_warmwasser_kwh: 0, wp_funktion_uebrige_kwh: 0,
    wp_waerme_heizen_kwh: 4, wp_waerme_warmwasser_kwh: 0, wp_waerme_uebrige_kwh: 3 }),
  stunde(7, { wp_waerme_kwh: 1, wp_funktion_strom_heizen_kwh: 0, wp_funktion_strom_warmwasser_kwh: 1, wp_funktion_uebrige_kwh: 0,
    wp_waerme_heizen_kwh: 0, wp_waerme_warmwasser_kwh: 1, wp_waerme_uebrige_kwh: 0 }),
]

describe('Wärme nach Funktion als Stapel neben dem Strom', () => {
  const punkte = baueTagWaermeVerlauf(FUNKTIONS_STUNDEN, [], 'beginn')

  it('Sicht «nach Funktion»: Wärme-Gruppe neben dem Strom, keine Wärme-Linie, Farben der Funktionen', () => {
    const v = baueWaermeVerlauf(punkte, 'funktion')
    expect(v.waermeGestapelt).toBe(true)
    const w = v.stapel.filter((s) => s.gruppe === 'waerme')
    expect(w.map((s) => s.label)).toEqual(['Wärme Heizen', 'Wärme Warmwasser', 'Wärme nicht je Funktion gemessen'])
    expect(w[0].farbe).toBe(CHART_COLORS.wpWaerme)
    expect(v.stapel.filter((s) => !s.gruppe).map((s) => s.key)).toEqual(['f_heizen', 'f_warmwasser', 'f_uebrige'])
    expect(v.linien.map((l) => l.key)).not.toContain('waerme')
    expect(v.rows[0]).toMatchObject({ w_heizen: 4, w_warmwasser: 0, w_uebrige: 3 })
    expect(verlaufTitel(v)).toBe('Verlauf · Strom und Wärme nach Funktion')
  })

  it('Sicht «nach Betriebsart» und Tage ohne Wärme-Stapel: Linie wie bisher', () => {
    const b = baueWaermeVerlauf(punkte, 'betriebsart')
    expect(b.waermeGestapelt).toBe(false)
    expect(b.stapel.some((s) => s.gruppe === 'waerme')).toBe(false)
    expect(b.linien.map((l) => l.key)).toContain('waerme')
    const ohne = baueTagWaermeVerlauf(FUNKTIONS_STUNDEN.map((s) => ({
      ...s, wp_waerme_heizen_kwh: null, wp_waerme_warmwasser_kwh: null, wp_waerme_uebrige_kwh: null,
    })), [], 'beginn')
    const f = baueWaermeVerlauf(ohne, 'funktion')
    expect(f.waermeGestapelt).toBe(false)
    expect(f.linien.map((l) => l.key)).toContain('waerme')
    expect(verlaufTitel(f)).toBe('Verlauf · Strom nach Funktion und gemessene Wärme')
  })
})

// ── S3-6 Temperatur-Diagramm ────────────────────────────────────────────────

function geraet(id: number, name: string, over: Partial<WaermeTemperaturGeraet> = {}): WaermeTemperaturGeraet {
  return {
    investition_id: id, bezeichnung: name, abdeckung_h: 3, betriebsstunden: 2,
    vorlauf_mittel_c: 35, spreizung_mittel_k: 5.5, betrieb_aus: 'strom',
    stunden: Array.from({ length: 24 }, (_, h) => ({
      stunde: h,
      vorlauf_c: h === 6 ? 34 : h === 7 ? 36 : h === 8 ? 30.2 : null,
      ruecklauf_c: h === 6 ? 29 : h === 7 ? 30 : null,
      warmwasser_c: h === 6 || h === 8 ? 48 : null,
      spreizung_k: h === 6 ? 5 : h === 7 ? 6 : null,
    })),
    ...over,
  }
}

describe('Temperatur-Diagramm (reine Funktion)', () => {
  it('Linien Vorlauf/Rücklauf/Warmwasser, Spreizung als Fläche [Rücklauf, Vorlauf], Lücken bleiben', () => {
    const dia = baueTemperaturDiagramm(geraet(1, 'Nibe'), 'ende')
    expect(dia.linien.map((l) => [l.key, l.farbe])).toEqual([
      ['vorlauf', CHART_COLORS.vorlauf], ['ruecklauf', CHART_COLORS.ruecklauf], ['warmwasser', CHART_COLORS.wpWarmwasser]])
    expect(dia.flaechen).toEqual([{ key: 'spreizung', label: 'Spreizung', farbe: CHART_COLORS.spreizung }])
    expect(dia.rows[6]).toMatchObject({ name: '5–6', vorlauf: 34, ruecklauf: 29, spreizung: [29, 34] })
    expect(dia.rows[8]).toMatchObject({ vorlauf: 30.2, ruecklauf: null, spreizung: null })
    expect(dia.rows[12]).toMatchObject({ vorlauf: null, warmwasser: null })
    expect(baueTemperaturDiagramm(geraet(1, 'Nibe'), 'beginn').rows[6].name).toBe('6–7')
  })

  it('Legende mit den Werten der letzten Stunde, Kopf aus dem Layer', () => {
    const dia = baueTemperaturDiagramm(geraet(1, 'Nibe'))
    expect(dia.legendeZusatz).toEqual({ Vorlauf: '30,2 °C', Rücklauf: '30,0 °C', Warmwasser: '48,0 °C', Spreizung: '6,0 K' })
    expect(dia.kopf).toBe('Ø Vorlauf 35,0 °C · Ø Spreizung 5,5 K (2 Betriebsstunden)')
    expect(temperaturKopf(geraet(1, 'x', { vorlauf_mittel_c: null }))).toBeNull()
    expect(temperaturKopf(geraet(1, 'x', { spreizung_mittel_k: null, betriebsstunden: 1 })))
      .toBe('Ø Vorlauf 35,0 °C (1 Betriebsstunde)')
  })
})

describe('Element «Temperaturen» im Wärme/Klima-Block', () => {
  const T1: WaermeTemperaturStunden = { raster: 'ende', geraete: [geraet(1, 'Nibe')], ohne_kanal: [] }

  it('am Tag mit Temperatur-Stunden: Element mit Kopf, ein Gerät ⇒ ohne Umschalter', () => {
    render(<>{wpBlock(TAG, 'tag', T1)!.render(false)}</>)
    expect(screen.getByText('Temperaturen · Nibe')).toBeInTheDocument()
    expect(screen.getByText('Ø Vorlauf 35,0 °C · Ø Spreizung 5,5 K (2 Betriebsstunden)')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Wärmepumpe wählen' })).toBeNull()
  })

  it('zwei Geräte ⇒ Umschalter; der Kopf folgt der Wahl', () => {
    const t: WaermeTemperaturStunden = {
      raster: 'ende', ohne_kanal: [{ investition_id: 3, bezeichnung: 'Split (MQTT)', felder: ['vorlauf_temperatur_c'] }],
      geraete: [geraet(1, 'Nibe'), geraet(2, 'Daikin', { vorlauf_mittel_c: 41.2, spreizung_mittel_k: null, betriebsstunden: 4 })],
    }
    render(<>{wpBlock(TAG, 'tag', t)!.render(false)}</>)
    expect(screen.getByRole('group', { name: 'Wärmepumpe wählen' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Daikin' }))
    expect(screen.getByText('Ø Vorlauf 41,2 °C (4 Betriebsstunden)')).toBeInTheDocument()
    expect(screen.getByText('Split (MQTT)')).toBeInTheDocument()
  })

  it('ohne Temperatur-Stunden, im Monat und ohne Antwort kein Element', () => {
    const leer: WaermeTemperaturStunden = { raster: 'ende', geraete: [geraet(1, 'Nibe', { abdeckung_h: 0 })], ohne_kanal: [] }
    expect(geraeteMitTemperaturen(leer)).toEqual([])
    for (const [over, periode, t] of [[TAG, 'tag', leer], [TAG, 'monat', T1], [TAG, 'tag', null]] as const) {
      const { unmount } = render(<>{wpBlock(over, periode, t)!.render(false)}</>)
      expect(screen.queryByText(/^Temperaturen/)).toBeNull()
      unmount()
    }
  })
})
