import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { TagWerte } from '../../api/energie_profil'
import type { WerteZeile } from './zeile'
import {
  WERTE_METRIKEN, WERTE_GRUPPEN, METRIK_BY_KEY, getMonatWert, getTagWert,
  metrikenFuer, brauchtWaermeTag, monatsZeile, tagesZeile, richteMonateAus,
  vergleichLookup, gepaarteVergleichsZeilen, vergleichsAggregatBasis,
  aggregiere, bewerteDelta, exportWerteCsv, fmtWert, alsAngezeigt, angezeigtesDelta,
} from './index'

// exportToCSV löst im echten Code einen Download aus — fürs Schema-Testen mocken.
vi.mock('../../utils/export', () => ({ exportToCSV: vi.fn() }))
import { exportToCSV } from '../../utils/export'

function mz(monat: number, jahr: number, over: Partial<MonatsZeitreihe> = {}): MonatsZeitreihe {
  return {
    name: `${monat}/${jahr}`, jahr, monat,
    erzeugung: 100, eigenverbrauch: 60, einspeisung: 40, netzbezug: 30,
    gesamtverbrauch: 90, direktverbrauch: 50,
    autarkie: 70, evQuote: 60, spezErtrag: 80,
    globalstrahlung: null, sonnenstunden: null,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_waerme: null, wp_strom: null, wp_cop: null, wp_cop_grund: null,
    wp_strom_heizen: null, wp_strom_warmwasser: null,
    wp_waerme_heizen: null, wp_waerme_warmwasser: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    wallbox_ladung: null, wallbox_pv_ladung: null, wallbox_pv_anteil: null,
    sonstiges_erzeugung: null, sonstiges_verbrauch: null,
    erzeuger_erloes: 0,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, ust_eigenverbrauch: 0, netzbezug_preis_cent: null, co2_einsparung: 25,
    ...over,
  }
}

function tw(datum: string, over: Partial<TagWerte> = {}): TagWerte {
  return {
    datum, stunden_verfuegbar: 24, datenquelle: 'ha_sensor',
    erzeugung: 30, eigenverbrauch: 18, einspeisung: 12, netzbezug: 6,
    pv_anlage: 24, bkw: 6,
    gesamtverbrauch: 24, direktverbrauch: 15,
    autarkie: 75, evQuote: 60, spezErtrag: 3,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null, speicher_effizienz_quelle: null,
    speicher_vollzyklen: null,
    wp_strom: null,
    sonstiges_erzeugung: null, sonstiges_verbrauch: null,
    einspeise_erloes: 1, ev_ersparnis: 2, netzbezug_kosten: 1.5,
    netto_ertrag: 3, netto_bilanz: 1.5, co2_einsparung: 11.4,
    ueberschuss_kwh: 8, defizit_kwh: 2, peak_pv_kw: 6.2,
    peak_netzbezug_kw: 1.1, peak_einspeisung_kw: 4.0, grundlast_kw: 0.38,
    performance_ratio: 0.85, batterie_vollzyklen: 0.4,
    temperatur_min_c: 10, temperatur_max_c: 22,
    strahlung_summe_wh_m2: 5000, gti_summe_wh_m2: null, boersenpreis_avg_cent: 9.5,
    boersenpreis_min_cent: -1, negative_preis_stunden: 1,
    einspeisung_neg_preis_kwh: 0,
    ...over,
  }
}

describe('W1-Registry', () => {
  it('hat 72 Metriken (55 Monat, 51 Tag, davon 34 beides), jede mit gültiger Gruppe + granular', () => {
    // 37 seit 05.09.2026: `abgabe_dritte` (Konzept §9.2, dritter Weg der Verwendung).
    // 72 seit 28.10.2026 (Tabellen-Spalten E-Mobilität, Wärme/Klima, Speicher, Wetter): +23 Spalten.
    // 34 beides seit 29.10.2026: WP-Wärme, Kälte, Strom Kühlen/Lüften/Entfeuchten/nicht aufgeteilt und Zusatzheizung
    // auch je Tag.
    expect(WERTE_METRIKEN).toHaveLength(72)
    expect(WERTE_METRIKEN.filter((m) => m.granular.length === 2)).toHaveLength(34)
    for (const m of WERTE_METRIKEN) {
      expect(WERTE_GRUPPEN).toContain(m.gruppe)
      expect(m.granular.length).toBeGreaterThan(0)
    }
  })
  it('METRIK_BY_KEY findet per key', () => {
    expect(METRIK_BY_KEY['autarkie'].aggregation).toBe('avg')
    expect(METRIK_BY_KEY['erzeugung'].aggregation).toBe('sum')
  })
  it('getMonatWert liest Property bzw. null', () => {
    const r = mz(5, 2025, { erzeugung: 412 })
    expect(getMonatWert(r, 'erzeugung')).toBe(412)
    expect(getMonatWert(r, 'speicher_ladung')).toBeNull()
  })
  it('getTagWert liest Property bzw. null', () => {
    const r = tw('2026-05-10', { erzeugung: 41 })
    expect(getTagWert(r, 'erzeugung')).toBe(41)
    expect(getTagWert(r, 'peak_pv_kw')).toBe(6.2)
    expect(getTagWert(r, 'speicher_ladung')).toBeNull()
  })
})

describe('metrikenFuer (Granularität)', () => {
  it('Monat = 55 Registry-Metriken, kein Tag-natives Feld', () => {
    const m = metrikenFuer('monat')
    expect(m).toHaveLength(55)
    expect(m.find((x) => x.key === 'peak_pv_kw')).toBeUndefined()
    expect(m.find((x) => x.key === 'wp_waerme')).toBeDefined()
    // Vollständigkeits-Spalten (Gernot 2026-06-26): verfügbare Felder als wählbare Spalten.
    expect(m.find((x) => x.key === 'globalstrahlung')).toBeDefined()
    expect(m.find((x) => x.key === 'wallbox_pv_anteil')).toBeDefined()
    expect(m.find((x) => x.key === 'netzbezug_preis_cent')).toBeDefined()
  })
  it('Tag = ohne JAZ/Wärme je Funktion/Wallbox-PV-Anteil, mit E-Auto-Fahrt, WP-Tagesreihe und Tag-nativen', () => {
    const keys = metrikenFuer('tag').map((x) => x.key)
    expect(keys).toHaveLength(51)
    expect(keys).toContain('peak_pv_kw')
    expect(keys).toContain('ueberschuss_kwh')
    expect(keys).toContain('erzeugung')
    // Grundlast je Nacht (OB73-gif, #395) — tag-nativ, denn der Monat hat
    // seinen eigenen Median über ALLE Nachtstunden und nicht den Durchschnitt
    // der Tageswerte. Wäre sie versehentlich MONAT_TAG, stünde in der
    // Monatstabelle eine Spalte ohne Wert.
    expect(keys).toContain('grundlast_kw')
    expect(metrikenFuer('monat').map((x) => x.key)).not.toContain('grundlast_kw')
    // Ein Median lässt sich nicht summieren — sonst stünde unter der Spalte
    // eine Zahl, die keine Grundlast ist.
    expect(METRIK_BY_KEY['grundlast_kw'].aggregation).toBe('none')
    // Seit 28.10.2026 (Tabellen-Spalten): km, Fahrverbrauch, Wallbox-Ladung, V2H und Ladevorgänge haben einen
    // gebündelten Tages-Leser; Arbeitszahlen und der gemessene PV-Anteil des Tages nicht (nur Cockpit → Tag).
    expect(keys).toContain('eauto_km')
    for (const k of ['eauto_fahrverbrauch', 'wallbox_ladung', 'v2h_entladung', 'ladevorgaenge', 'wp_starts',
      'wp_betriebszeit_min', 'speicher_vollzyklen', 'temperatur_min_c', 'boersenpreis_min_cent', 'abgabe_dritte']) {
      expect(keys).toContain(k)
    }
    for (const k of ['wp_cop', 'wp_jaz_heizen', 'wp_jaz_warmwasser', 'wp_jaz_kuehlen', 'wallbox_pv_anteil',
      'wallbox_pv_ladung', 'eauto_kwh_100km', 'wp_waerme_heizen', 'wp_waerme_warmwasser',
      'wp_strom_heizen', 'wp_strom_warmwasser']) {
      expect(keys).not.toContain(k)
    }
  })
  it('WP-Tagesreihe (29.10.2026): genau sieben Spalten tragen `tagMitWaerme`, alle Monat + Tag', () => {
    const waerme = WERTE_METRIKEN.filter((m) => m.tagMitWaerme).map((m) => m.key)
    expect(waerme.sort()).toEqual(['wp_heizstab', 'wp_kaelte', 'wp_strom_entfeuchten', 'wp_strom_kuehlen',
      'wp_strom_lueften', 'wp_strom_nicht_aufgeteilt', 'wp_waerme'])
    for (const k of waerme) expect(METRIK_BY_KEY[k].granular).toEqual(['monat', 'tag'])
    expect(brauchtWaermeTag(['erzeugung', 'wp_strom', 'wp_starts'])).toBe(false)
    expect(brauchtWaermeTag(['erzeugung', 'wp_kaelte'])).toBe(true)
    expect(brauchtWaermeTag(['wp_heizstab'])).toBe(true)
    expect(brauchtWaermeTag([])).toBe(false)
  })
})

describe('Tabellen-Spalten 28.10.2026 (E-Mobilität, Wärme/Klima, Speicher, Wetter)', () => {
  it('neue Spalten sind nie vorgewählt', () => {
    const neu = ['eauto_fahrverbrauch', 'eauto_kwh_100km', 'emob_extern_kwh', 'emob_extern_euro', 'v2h_entladung',
      'ladevorgaenge', 'dienstliche_ladekosten', 'wp_jaz_heizen', 'wp_jaz_warmwasser', 'wp_jaz_kuehlen',
      'wp_strom_kuehlen', 'wp_strom_lueften', 'wp_strom_entfeuchten', 'wp_strom_nicht_aufgeteilt', 'wp_kaelte',
      'wp_heizstab', 'wp_starts', 'wp_betriebszeit_min', 'speicher_netzladung', 'speicher_vollzyklen',
      'temperatur_avg_c', 'temperatur_min_c', 'boersenpreis_min_cent']
    for (const k of neu) expect(METRIK_BY_KEY[k]?.defaultVisible, k).toBe(false)
  })
  it('Vollzyklen der Entladung tragen einen anderen Namen als die SoC-Hübe', () => {
    expect(METRIK_BY_KEY['speicher_vollzyklen'].label).not.toBe(METRIK_BY_KEY['batterie_vollzyklen'].label)
  })
  it('Arbeitszahlen je Funktion werden im Fuß nicht gemittelt, die Betriebszeit ist in ganzen Minuten', () => {
    for (const k of ['wp_jaz_heizen', 'wp_jaz_warmwasser', 'wp_jaz_kuehlen']) {
      expect(METRIK_BY_KEY[k].aggregation).toBe('none')
    }
    expect(METRIK_BY_KEY['wp_betriebszeit_min'].unit).toBe('min')
    expect(METRIK_BY_KEY['wp_betriebszeit_min'].decimals).toBe(0)
  })
  it('getMonatWert reicht E-Mob- und WP-Felder der Zeile durch', () => {
    const r = mz(7, 2026, { eauto_fahrverbrauch: 210.4, eauto_kwh_100km: 17.5, wp_jaz_heizen: 4.2, wp_strom_kuehlen: 31,
      speicher_netzladung: 12, temperatur_avg_c: 18.3, dienstliche_ladekosten: 9.5 })
    expect(getMonatWert(r, 'eauto_fahrverbrauch')).toBe(210.4)
    expect(getMonatWert(r, 'eauto_kwh_100km')).toBe(17.5)
    expect(getMonatWert(r, 'wp_jaz_heizen')).toBe(4.2)
    expect(getMonatWert(r, 'wp_strom_kuehlen')).toBe(31)
    expect(getMonatWert(r, 'speicher_netzladung')).toBe(12)
    expect(getMonatWert(r, 'temperatur_avg_c')).toBe(18.3)
    expect(getMonatWert(r, 'dienstliche_ladekosten')).toBe(9.5)
  })
  it('getTagWert reicht die Tagesfelder durch; Abgabe an Dritte liest `sonstiges_abgabe`', () => {
    const r = tw('2026-06-10', { wallbox_ladung: 11.2, eauto_km: 42, eauto_fahrverbrauch: 7.5, ladevorgaenge: 2,
      wp_starts: 7, wp_betriebszeit_min: 192, sonstiges_abgabe: 3.4, speicher_vollzyklen: 0.8, temperatur_min_c: 4.1 })
    expect(getTagWert(r, 'wallbox_ladung')).toBe(11.2)
    expect(getTagWert(r, 'eauto_km')).toBe(42)
    expect(getTagWert(r, 'eauto_fahrverbrauch')).toBe(7.5)
    expect(getTagWert(r, 'ladevorgaenge')).toBe(2)
    expect(getTagWert(r, 'wp_starts')).toBe(7)
    expect(getTagWert(r, 'wp_betriebszeit_min')).toBe(192)
    expect(getTagWert(r, 'abgabe_dritte')).toBe(3.4)
    expect(getTagWert(r, 'speicher_vollzyklen')).toBe(0.8)
    expect(getTagWert(r, 'temperatur_min_c')).toBe(4.1)
  })
  it('null bleibt null (Anzeige „—"), eine 0 bleibt 0', () => {
    const r = tw('2026-06-10', { wallbox_ladung: null, ladevorgaenge: 0 })
    expect(getTagWert(r, 'wallbox_ladung')).toBeNull()
    expect(getTagWert(r, 'eauto_km')).toBeNull()
    expect(getTagWert(r, 'ladevorgaenge')).toBe(0)
    expect(getMonatWert(mz(7, 2026, { wp_jaz_kuehlen: null }), 'wp_jaz_kuehlen')).toBeNull()
    expect(fmtWert(getTagWert(r, 'wallbox_ladung'), METRIK_BY_KEY['wallbox_ladung'].decimals)).toBe('—')
    expect(fmtWert(getTagWert(r, 'ladevorgaenge'), METRIK_BY_KEY['ladevorgaenge'].decimals)).toBe('0')
  })
  it('Fuß kWh/100 km = Σ (Quote × km) ÷ Σ km der Monate mit Quote — wie der Layer (Σ Menge ÷ Σ km)', () => {
    // Juni: 180 kWh auf 1000 km (18,0), Juli: 340 kWh auf 2000 km (17,0), August: 500 km ohne Energiemenge (keine Quote).
    const rows = [
      monatsZeile(mz(6, 2026, { eauto_km: 1000, eauto_kwh_100km: 18 })),
      monatsZeile(mz(7, 2026, { eauto_km: 2000, eauto_kwh_100km: 17 })),
      monatsZeile(mz(8, 2026, { eauto_km: 500, eauto_kwh_100km: null })),
    ]
    const fuss = aggregiere(rows, [METRIK_BY_KEY['eauto_kwh_100km']])['eauto_kwh_100km']
    expect(fuss).toBeCloseTo((180 + 340) / 3000 * 100, 9)
  })
})

describe('zeile-Normalisierung', () => {
  it('monatsZeile: Label/sortKey/vergleichKey (Jahr UND Monat)', () => {
    const z = monatsZeile(mz(5, 2025, { erzeugung: 123 }))
    expect(z.vergleichKey).toBe(202505)
    expect(z.sortKey).toBe(2025 * 100 + 5)
    expect(z.wert('erzeugung')).toBe(123)
  })
  it('monatsZeile: derselbe Monat verschiedener Jahre kollidiert NICHT (PN 90204)', () => {
    expect(monatsZeile(mz(12, 2025)).vergleichKey)
      .not.toBe(monatsZeile(mz(12, 2024)).vergleichKey)
  })
  it('tagesZeile: vergleichKey = volles Datum, sortKey aufsteigend', () => {
    const z = tagesZeile(tw('2026-05-10', { erzeugung: 41 }))
    expect(z.vergleichKey).toBe(20260510)
    expect(z.id).toBe('2026-05-10')
    expect(z.wert('erzeugung')).toBe(41)
    expect(z.wert('peak_pv_kw')).toBe(6.2)
    expect(tagesZeile(tw('2026-05-11')).sortKey).toBeGreaterThan(z.sortKey)
    // gleicher Tag-im-Monat, anderer Monat → eigener Schlüssel
    expect(tagesZeile(tw('2026-04-10')).vergleichKey).not.toBe(z.vergleichKey)
  })
})

describe('Vergleichs-Auflösung (PN 90204 — mehrjähriger Zeitraum)', () => {
  // „Alle Jahre": Primär 2024–2026, Vergleichsfenster 2023–2025. Vor dem Fix
  // behielt der Lookup je Monatsnummer die LETZTE Zeile ⇒ Dez 2025 verglich sich
  // mit Dez 2025 (Δ 0,0 %), Dez 2024 ebenfalls mit Dez 2025.
  const prim = [
    monatsZeile(mz(12, 2024, { erzeugung: 227.9 })),
    monatsZeile(mz(12, 2025, { erzeugung: 432.7 })),
    monatsZeile(mz(12, 2026, { erzeugung: 500 })),
  ]
  const vergleichsFenster = richteMonateAus([
    monatsZeile(mz(12, 2024, { erzeugung: 227.9 })),
    monatsZeile(mz(12, 2025, { erzeugung: 432.7 })),
  ])!

  it('jede Zeile findet ihr ECHTES Vorjahr, nicht den jüngsten Jahrgang', () => {
    const lookup = vergleichLookup(vergleichsFenster)
    expect(lookup.get(prim[1].vergleichKey)!.wert('erzeugung')).toBe(227.9) // Dez 2025 ← Dez 2024
    expect(lookup.get(prim[2].vergleichKey)!.wert('erzeugung')).toBe(432.7) // Dez 2026 ← Dez 2025
  })

  it('kein Vorjahr vorhanden ⇒ kein Treffer (Anzeige „—", kein 0-%-Vergleich)', () => {
    const lookup = vergleichLookup(vergleichsFenster)
    expect(lookup.get(prim[0].vergleichKey)).toBeUndefined() // Dez 2023 gibt es nicht
  })

  it('gepaarteVergleichsZeilen: nur die Zeilen mit echtem Gegenstück', () => {
    const paare = gepaarteVergleichsZeilen(prim, vergleichsFenster)
    // 3 Primärzeilen, aber nur 2 haben ein Vorjahr.
    expect(paare.map((z) => z.wert('erzeugung'))).toEqual([227.9, 432.7])
  })

  it('Summenzeile: kein Vergleich, solange nicht jede Zeile ein Gegenstück hat', () => {
    // 3 angezeigte Zeilen, 2 gepaart → der Fuß dürfte sonst 3 Monate gegen 2 stellen.
    expect(vergleichsAggregatBasis(prim, vergleichsFenster)).toBeNull()
    // Vollständig gepaart → Basis vorhanden.
    expect(vergleichsAggregatBasis(prim.slice(1), vergleichsFenster)).toHaveLength(2)
  })

  it('richteMonateAus(null) bleibt null (kein Vergleich)', () => {
    expect(richteMonateAus(null)).toBeNull()
  })
})

describe('aggregiere', () => {
  const metriken = metrikenFuer('monat')
  const rows = [monatsZeile(mz(1, 2025, { erzeugung: 100, autarkie: 60 })), monatsZeile(mz(2, 2025, { erzeugung: 200, autarkie: 80 }))]
  it('summiert sum-Metriken', () => {
    expect(aggregiere(rows, metriken)['erzeugung']).toBe(300)
  })
  it('mittelt avg-Metriken', () => {
    expect(aggregiere(rows, metriken)['autarkie']).toBe(70)
  })
  it('liefert null für leere Spalte (alle null)', () => {
    expect(aggregiere(rows, metriken)['speicher_ladung']).toBeNull()
  })
  it('aggregiert Tageszeilen (Σ Überschuss)', () => {
    const tage = [tagesZeile(tw('2026-05-10', { ueberschuss_kwh: 8 })), tagesZeile(tw('2026-05-11', { ueberschuss_kwh: 5 }))]
    expect(aggregiere(tage, metrikenFuer('tag'))['ueberschuss_kwh']).toBe(13)
  })
})

describe('bewerteDelta', () => {
  it('höher-besser: Anstieg gut, Rückgang schlecht', () => {
    expect(bewerteDelta(120, 100, true)).toBe('gut')
    expect(bewerteDelta(80, 100, true)).toBe('schlecht')
  })
  it('niedriger-besser: Anstieg schlecht', () => {
    expect(bewerteDelta(120, 100, false)).toBe('schlecht')
    expect(bewerteDelta(80, 100, false)).toBe('gut')
  })
  it('neutral bei undefined, Gleichstand oder null', () => {
    expect(bewerteDelta(120, 100, undefined)).toBe('neutral')
    expect(bewerteDelta(100, 100, true)).toBe('neutral')
    expect(bewerteDelta(null, 100, true)).toBe('neutral')
  })
})

describe('alsAngezeigt (T89667 #162)', () => {
  it('liefert genau die Zahl, die fmtWert als Text zeigt', () => {
    for (const [v, d] of [[11.71, 0], [0.29, 0], [0.45, 0], [16.045, 2], [-3.7, 0]] as const) {
      expect(fmtWert(alsAngezeigt(v, d), d)).toBe(fmtWert(v, d))
    }
  })
  it('rundet über den Betrag — die Anzeige tut es auch', () => {
    // `toLocaleString` rundet „halfExpand" (−0,5 → „−1"), `Math.round` zur +∞
    // hin (−0,5 → −0). Ohne die Betrags-Rundung wiche die Δ-Spalte bei
    // negativen Finanz-Werten um eine Einheit von ihrer eigenen Anzeige ab.
    expect(alsAngezeigt(-0.5, 0)).toBe(-1)
    expect(alsAngezeigt(-2.5, 0)).toBe(-3)
    expect(alsAngezeigt(0.5, 0)).toBe(1)
  })
})

describe('exportWerteCsv (Schema)', () => {
  beforeEach(() => vi.mocked(exportToCSV).mockClear())
  const rows = [monatsZeile(mz(1, 2025)), monatsZeile(mz(2, 2025))]
  const metriken = [METRIK_BY_KEY['erzeugung'], METRIK_BY_KEY['autarkie']]

  it('ohne Vergleich: Zeitraum + eine Spalte je Metrik + Agg-Zeile', () => {
    exportWerteCsv({ rows, vorjahrRows: null, jahrLabel: 2025, vergleichLabel: null, metriken, einheitLabel: 'Monate', dateiname: 'x.csv' })
    const [headers, out, name] = vi.mocked(exportToCSV).mock.calls[0]
    expect(headers[0]).toBe('Zeitraum')
    expect(headers).toContain('PV-Erzeugung (kWh)')
    expect(name).toBe('x.csv')
    // letzte Zeile = Aggregat („2 Monate")
    expect(out[out.length - 1][0]).toBe('2 Monate')
  })

  it('Tages-Export nutzt Einheit „Tage"', () => {
    const tage = [tagesZeile(tw('2026-05-10')), tagesZeile(tw('2026-05-11'))]
    exportWerteCsv({ rows: tage, vorjahrRows: null, jahrLabel: 'Mai', vergleichLabel: null, metriken, einheitLabel: 'Tage', dateiname: 't.csv' })
    const [, out] = vi.mocked(exportToCSV).mock.calls[0]
    expect(out[out.length - 1][0]).toBe('2 Tage')
  })

  it('mit Vergleich: drei Spalten je Metrik inkl. Δ-Header', () => {
    exportWerteCsv({ rows, vorjahrRows: richteMonateAus([monatsZeile(mz(1, 2024)), monatsZeile(mz(2, 2024))]), jahrLabel: 2025, vergleichLabel: 2024, metriken, einheitLabel: 'Monate', dateiname: 'x.csv' })
    const [headers] = vi.mocked(exportToCSV).mock.calls[0]
    expect(headers).toContain('PV-Erzeugung (kWh) 2025')
    expect(headers).toContain('PV-Erzeugung (kWh) 2024')
    expect(headers).toContain('Δ vs. 2024')
  })

  // PN 90204: Export und Tabelle teilen sich EINE Vergleichs-Auflösung. Der Export
  // muss deshalb über mehrere Jahrgänge dieselben Vorjahreswerte tragen wie die
  // Tabelle — und dort, wo es kein Vorjahr gibt, eine leere Zelle statt eines
  // gespiegelten Werts.
  it('mehrjährig: jede Zeile exportiert ihr echtes Vorjahr, fehlendes Vorjahr bleibt leer', () => {
    const mehrjaehrig = [
      monatsZeile(mz(12, 2024, { erzeugung: 227.9 })),
      monatsZeile(mz(12, 2025, { erzeugung: 432.7 })),
    ]
    exportWerteCsv({
      rows: mehrjaehrig,
      vorjahrRows: richteMonateAus([
        monatsZeile(mz(12, 2024, { erzeugung: 227.9 })),
        monatsZeile(mz(12, 2025, { erzeugung: 432.7 })),
      ]),
      jahrLabel: 'Aktuell', vergleichLabel: 'Vorjahr',
      metriken: [METRIK_BY_KEY['erzeugung']], einheitLabel: 'Monate', dateiname: 'x.csv',
    })
    const [, out] = vi.mocked(exportToCSV).mock.calls[0]
    // [Label, aktuell, Vergleich, Δ]
    expect(out[0].slice(1)).toEqual([227.9, '', ''])       // Dez 2024 hat kein Vorjahr
    expect(out[1].slice(1)).toEqual([432.7, 227.9, 204.8]) // Dez 2025 ← Dez 2024
    // Summenzeile: „aktuell" bleibt die Spaltensumme, der Vergleich bleibt leer —
    // nur eine der beiden Zeilen ist gepaart.
    expect(out[2]).toEqual(['2 Monate', 660.6, '', ''])
  })

  // C3/S20 (R3b): Rundung vor Export — Float-Artefakte (0.4−0.1 =
  // 0.30000000000000004) dürfen NICHT in der Exportdatei landen (max. 4 NK).
  it('S20: Δ-Werte ohne Float-Artefakte (max. 4 NK)', () => {
    exportWerteCsv({
      rows: [monatsZeile(mz(1, 2025, { erzeugung: 0.4 }))],
      vorjahrRows: richteMonateAus([monatsZeile(mz(1, 2024, { erzeugung: 0.1 }))]),
      jahrLabel: 2025, vergleichLabel: 2024,
      metriken: [METRIK_BY_KEY['erzeugung']], einheitLabel: 'Monate', dateiname: 'x.csv',
    })
    const [, out] = vi.mocked(exportToCSV).mock.calls[0]
    // Zeile 0: [Label, 0.4, 0.1, Δ] — Δ exakt 0.3, nicht 0.30000000000000004.
    expect(out[0][3]).toBe(0.3)
    for (const zelle of out.flat()) {
      if (typeof zelle === 'number') expect(String(zelle)).toMatch(/^-?\d+(\.\d{1,4})?$/)
    }
  })
})

describe('Sonstiges-Spalten (Melder rapahl, 2026-08-14)', () => {
  const keys = ['sonstiges_erzeugung', 'sonstiges_verbrauch']

  it('stehen in Tages- UND Monatstabelle zur Wahl, aber nie ungefragt', () => {
    for (const key of keys) {
      const m = METRIK_BY_KEY[key]
      expect(m.granular).toEqual(['monat', 'tag'])
      // Rainers Wort war „Spaltenauswahlmöglichkeit" — eine neue Pflichtspalte
      // änderte vertraute Anzeigen ungefragt.
      expect(m.defaultVisible).toBe(false)
      expect(m.gruppe).toBe('sonstiges')
      // Die Einheit steht im Namen (Kopfzeile „… (kWh)"), damit #377
      // (Gas/Öl/Wasser in m³/l) eigene Spalten daneben bekommt statt diese zu
      // übernehmen.
      expect(m.unit).toBe('kWh')
    }
    expect(metrikenFuer('monat').filter((m) => keys.includes(m.key))).toHaveLength(2)
    expect(metrikenFuer('tag').filter((m) => keys.includes(m.key))).toHaveLength(2)
  })

  it('werden aus beiden Granularitäts-Zeilen gelesen', () => {
    expect(getMonatWert(mz(5, 2026, { sonstiges_verbrauch: 45 }), 'sonstiges_verbrauch')).toBe(45)
    expect(getTagWert(tw('2026-05-10', { sonstiges_erzeugung: 1.94 }), 'sonstiges_erzeugung')).toBe(1.94)
    // Kein Gerät ⇒ kein Wert, keine 0.
    expect(getTagWert(tw('2026-05-10'), 'sonstiges_verbrauch')).toBeNull()
  })
})

describe('angezeigtesDelta — der Prozentwert kommt aus den ANGEZEIGTEN Zahlen (N-253)', () => {
  it('sieht die Gleichheit, die auf dem Schirm steht: 151,4 gegen 150,6 bei 0 Stellen', () => {
    // Beide Zahlen stehen als „151" da. Aus den Rohwerten gerechnet stand daneben
    // „▲ 1 %" — ein Badge, das seinen zwei Nachbarn widerspricht.
    const d = angezeigtesDelta(151.4, 150.6, 0)
    expect(d).not.toBeNull()
    expect(d!.pfeil).toBe('=')
    expect(d!.pct).toBe(0)
    expect(d!.diff).toBe(0)
  })

  it('meldet die Änderung, die auf dem Schirm steht: 250,00 gegen 249,50 bei 2 Stellen', () => {
    // Die Gegenrichtung: sichtbar verschiedene Beträge, aber der Rohwert-Prozentsatz
    // rundete auf „0 %" — eine behauptete Nulländerung.
    const d = angezeigtesDelta(250.0, 249.5, 2)
    expect(d!.pfeil).toBe('▲')
    expect(d!.diff).toBeCloseTo(0.5, 10)
    expect(d!.pct).toBeCloseTo(0.2004, 3)
  })

  it('rechnet nicht gegen eine angezeigte Null', () => {
    // 0,4 kWh steht bei 0 Stellen als „0" da — ein Prozentwert relativ dazu
    // hätte keine sichtbare Grundlage.
    expect(angezeigtesDelta(0.6, 0.4, 0)).toBeNull()
    // Mit einer Stelle trägt dieselbe Bezugsgröße sehr wohl.
    expect(angezeigtesDelta(0.6, 0.4, 1)!.pfeil).toBe('▲')
  })

  it('rundet über den Betrag — negative Bezugsgrößen kippen nicht um eine Einheit', () => {
    // Dieselbe Begründung wie bei `alsAngezeigt`: toLocaleString rundet
    // „halfExpand", Math.round zur +∞ hin.
    const d = angezeigtesDelta(-12.5, -12.5, 0)
    expect(d!.pfeil).toBe('=')
  })

  it('unterscheidet die Richtung erst, wenn die Anzeige sie hergibt', () => {
    expect(angezeigtesDelta(100.4, 100.0, 0)!.pfeil).toBe('=')
    expect(angezeigtesDelta(100.6, 100.0, 0)!.pfeil).toBe('▲')
    expect(angezeigtesDelta(99.4, 100.0, 0)!.pfeil).toBe('▼')
  })
})


describe('aggregiere gewichtet (A-1: kein arithmetisches Mittel über Preise)', () => {
  const zeile = (werte: Record<string, number | null>) =>
    ({ wert: (k: string) => werte[k] ?? null }) as unknown as WerteZeile
  const preis = METRIK_BY_KEY['netzbezug_preis_cent']

  it('Ø Netzpreis ist über den Netzbezug gewichtet — 20 ct × 300 kWh und 40 ct × 100 kWh ⇒ 25 ct, nicht 30', () => {
    const rows = [zeile({ netzbezug: 300, netzbezug_preis_cent: 20 }), zeile({ netzbezug: 100, netzbezug_preis_cent: 40 })]
    expect(preis.aggregation).toBe('gewichtet')
    expect(aggregiere(rows, [preis])['netzbezug_preis_cent']).toBeCloseTo(25, 6)
  })

  it('Zeilen ohne Gewicht oder ohne Preis zählen nicht; ohne jede Menge kein Ø (null, nicht 0)', () => {
    const rows = [zeile({ netzbezug: 0, netzbezug_preis_cent: 99 }), zeile({ netzbezug: null, netzbezug_preis_cent: 50 }), zeile({ netzbezug: 10, netzbezug_preis_cent: null })]
    expect(aggregiere(rows, [preis])['netzbezug_preis_cent']).toBeNull()
  })
})
