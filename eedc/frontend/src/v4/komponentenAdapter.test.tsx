import { describe, it, expect, vi, beforeEach } from 'vitest'

// API-Module mocken — der Adapter normalisiert nur deren Felder.
const getSpeicherDashboard = vi.fn()
const getWaermepumpeDashboard = vi.fn()
const getEAutoDashboard = vi.fn()
const getWallboxDashboard = vi.fn()
const getBalkonkraftwerkDashboard = vi.fn()
const getSonstigesDashboard = vi.fn()
const list = vi.fn()
const getUebersicht = vi.fn()
const listAggregiert = vi.fn()

vi.mock('../api/investitionen', () => ({
  investitionenApi: {
    getSpeicherDashboard: (...a: unknown[]) => getSpeicherDashboard(...a),
    getWaermepumpeDashboard: (...a: unknown[]) => getWaermepumpeDashboard(...a),
    getEAutoDashboard: (...a: unknown[]) => getEAutoDashboard(...a),
    getWallboxDashboard: (...a: unknown[]) => getWallboxDashboard(...a),
    getBalkonkraftwerkDashboard: (...a: unknown[]) => getBalkonkraftwerkDashboard(...a),
    getSonstigesDashboard: (...a: unknown[]) => getSonstigesDashboard(...a),
    list: (...a: unknown[]) => list(...a),
  },
}))
vi.mock('../api/cockpit', () => ({ cockpitApi: { getUebersicht: (...a: unknown[]) => getUebersicht(...a) } }))
vi.mock('../api/monatsdaten', () => ({ monatsdatenApi: { listAggregiert: (...a: unknown[]) => listAggregiert(...a) } }))

import { KOMPONENTEN_ADAPTER } from './komponentenAdapter'

const inv = (over = {}) => ({ id: 1, anlage_id: 1, typ: 'x', bezeichnung: 'Gerät A', aktiv: true, ...over })
const titles = (ks: { title: string }[]) => ks.map((k) => k.title)

beforeEach(() => { vi.clearAllMocks(); list.mockResolvedValue([]); listAggregiert.mockResolvedValue([]) })

describe('KOMPONENTEN_ADAPTER', () => {
  it('Speicher: D2-KPIs + Ladequellen-Aufteilung (PV/Netz aus Arbitrage) + Verlauf', async () => {
    getSpeicherDashboard.mockResolvedValue([{
      investition: inv({ typ: 'speicher' }),
      zusammenfassung: { vollzyklen: 312, effizienz_prozent: 90, ist_wirkungsgrad_prozent: 92,
        gesamt_entladung_kwh: 4100, gesamt_ladung_kwh: 4500, arbitrage_kwh: 500, ersparnis_euro: 286 },
      monatsdaten: [
        { jahr: 2025, monat: 11, verbrauch_daten: { ladung_kwh: 100, entladung_kwh: 90 } },
        { jahr: 2025, monat: 10, verbrauch_daten: { ladung_kwh: 80, entladung_kwh: 70 } },
      ],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.speicher.fetch(1)
    expect(titles(g.status)).toEqual(['Vollzyklen', 'Wirkungsgrad η', 'Durchsatz', 'Ersparnis'])
    // bevorzugt ist_wirkungsgrad_prozent (92) vor effizienz_prozent (90)
    expect(g.status[1].value).toBe('92')
    expect(g.aufteilung?.segmente.map((s) => [s.label, s.wert])).toEqual([['PV-Ladung', 4000], ['Netz-Ladung', 500]])
    // Verlauf chronologisch sortiert (Okt vor Nov), Keys ladung/entladung
    expect(g.verlauf?.bars.map((b) => b.key)).toEqual(['ladung', 'entladung'])
    expect(g.verlauf?.rows.map((r) => [r.name, r.ladung])).toEqual([['Okt 25', 80], ['Nov 25', 100]])
    // Vergleich: Jahressumme Entladung (90 + 70 = 160 in 2025)
    expect(g.vergleich?.label).toBe('Entladung')
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2025, summe: 160 }])
  })

  it('Speicher ① Kennzahlen-Strip + Degradations-/Durchsatz-Alarm + η-Alarm-Farbe', async () => {
    getSpeicherDashboard.mockResolvedValue([{
      investition: inv({ typ: 'speicher' }),
      zusammenfassung: { vollzyklen: 312, effizienz_prozent: 80, ist_wirkungsgrad_prozent: 80,
        param_wirkungsgrad_prozent: 90, eta_degradation_alarm: true, durchsatz_inkonsistent: true,
        gesamt_entladung_kwh: 4100, gesamt_ladung_kwh: 4500, zyklen_pro_monat: 26, arbitrage_kwh: 0, ersparnis_euro: 286 },
      monatsdaten: [{ jahr: 2025, monat: 11, verbrauch_daten: { ladung_kwh: 100, entladung_kwh: 90 } }],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.speicher.fetch(1)
    // η-Kachel rot bei Degradations-Alarm
    expect(g.status[1].color).toBe('red')
    // Kennzahlen-Strip: Ladung/Entladung gesamt, Zyklen/Monat, Verlust (4500−4100=400)
    expect(titles(g.kennzahlen!.kpis)).toEqual(['Ladung gesamt', 'Entladung gesamt', 'Zyklen/Monat', 'Verlust'])
    expect(g.kennzahlen!.kpis[3].value).toBe('400')
    // Zwei Alarme (Degradation + Durchsatz-Invariante)
    expect(g.hinweise).toHaveLength(2)
    expect(g.hinweise!.every((h) => h.ton === 'warning')).toBe(true)
  })

  it('Vergleich: Jahressummen über mehrere Jahre, chronologisch', async () => {
    getSpeicherDashboard.mockResolvedValue([{
      investition: inv({ typ: 'speicher' }),
      zusammenfassung: { vollzyklen: 1, effizienz_prozent: 90, gesamt_entladung_kwh: 0, gesamt_ladung_kwh: 0, arbitrage_kwh: 0, ersparnis_euro: 0 },
      monatsdaten: [
        { jahr: 2024, monat: 6, verbrauch_daten: { ladung_kwh: 10, entladung_kwh: 50 } },
        { jahr: 2025, monat: 1, verbrauch_daten: { ladung_kwh: 10, entladung_kwh: 30 } },
        { jahr: 2025, monat: 2, verbrauch_daten: { ladung_kwh: 10, entladung_kwh: 40 } },
      ],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.speicher.fetch(1)
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2024, summe: 50 }, { jahr: 2025, summe: 70 }])
  })

  it('Wärmepumpe: JAZ + Heizung/Warmwasser-Aufteilung', async () => {
    getWaermepumpeDashboard.mockResolvedValue([{
      investition: inv({ typ: 'waermepumpe' }),
      zusammenfassung: { durchschnitt_cop: 3.8, gesamt_waerme_kwh: 12400, gesamt_stromverbrauch_kwh: 3300,
        gesamt_heizenergie_kwh: 9400, gesamt_warmwasser_kwh: 3000, ersparnis_euro: 410, co2_ersparnis_kg: 2100 },
      monatsdaten: [{ jahr: 2025, monat: 11, verbrauch_daten: { heizenergie_kwh: 800, warmwasser_kwh: 200 } }],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.waermepumpe.fetch(1)
    expect(titles(g.status)).toEqual(['JAZ', 'Wärme erzeugt', 'Strom verbraucht', 'Ersparnis vs. Gas'])
    expect(g.aufteilung?.segmente.map((s) => s.label)).toEqual(['Heizung', 'Warmwasser'])
    // CO₂-Ersparnis als eigene Kennzahl (IST-getreu)
    expect(titles(g.kennzahlen!.kpis)).toEqual(['CO₂-Ersparnis'])
    expect(g.kennzahlen!.kpis[0].value).toBe('2.100')
  })

  it('E-Auto: Ø-Verbrauch null → „—" statt 0 (nie 0 erfinden)', async () => {
    getEAutoDashboard.mockResolvedValue([{
      investition: inv({ typ: 'e-auto' }),
      zusammenfassung: { gesamt_km: 14200, durchschnitt_verbrauch_kwh_100km: null, pv_anteil_heim_prozent: 61,
        ersparnis_vs_benzin_euro: 1120, gesamt_ladung_kwh: 1000, ladung_pv_kwh: 600, ladung_netz_kwh: 300, ladung_extern_kwh: 100,
        co2_ersparnis_kg: 1850 },
      monatsdaten: [{ jahr: 2025, monat: 11, verbrauch_daten: { ladung_pv_kwh: 60, ladung_netz_kwh: 30 } }],
    }])
    const [g] = await KOMPONENTEN_ADAPTER['e-auto'].fetch(1)
    expect(g.status[1].value).toBe('—')
    expect(g.aufteilung?.segmente.map((s) => s.label)).toEqual(['PV', 'Netz', 'Extern'])
    expect(titles(g.kennzahlen!.kpis)).toEqual(['CO₂-Ersparnis'])
  })

  it('Sonstiges: kategorie wählt die richtige 4er-KPI-Reihe', async () => {
    getSonstigesDashboard.mockResolvedValue([{
      investition: inv({ typ: 'sonstiges' }),
      zusammenfassung: { kategorie: 'verbraucher', beschreibung: 'Pool', gesamt_verbrauch_kwh: 320,
        pv_anteil_prozent: 72, kosten_netz_euro: 40, ersparnis_pv_euro: 96, sonderkosten_euro: 0 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(titles(g.status)).toEqual(['Verbrauch', 'PV-Anteil', 'Netzkosten', 'PV-Ersparnis'])
    // Kategorie-Badge am Selektor; kein Sonderkosten-Alert bei 0
    expect(g.selektorBadge).toBe('Verbraucher')
    expect(g.hinweise).toBeUndefined()
  })

  it('Sonstiges: Sonderkosten>0 → Warn-Hinweis; Erzeuger-Badge', async () => {
    getSonstigesDashboard.mockResolvedValue([{
      investition: inv({ typ: 'sonstiges' }),
      zusammenfassung: { kategorie: 'erzeuger', beschreibung: 'BHKW', gesamt_erzeugung_kwh: 500,
        eigenverbrauch_quote_prozent: 80, gesamt_ersparnis_euro: 120, co2_ersparnis_kg: 200, sonderkosten_euro: 75 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.selektorBadge).toBe('Erzeuger')
    expect(g.hinweise).toHaveLength(1)
    expect(g.hinweise![0].text).toContain('Sonderkosten')
  })

  it('PV-Anlage: cockpit-Übersicht + EV/Einspeisung-Summe aus aggregierten Monaten', async () => {
    getUebersicht.mockResolvedValue({ anlagenleistung_kwp: 9.8, pv_erzeugung_kwh: 38200,
      spezifischer_ertrag_kwh_kwp: 1040, eigenverbrauch_quote_prozent: 54 })
    listAggregiert.mockResolvedValue([
      { eigenverbrauch_kwh: 100, einspeisung_kwh: 200 }, { eigenverbrauch_kwh: 150, einspeisung_kwh: 50 },
    ])
    const [g] = await KOMPONENTEN_ADAPTER['pv-module'].fetch(1)
    expect(titles(g.status)).toEqual(['Anlagenleistung', 'Gesamterzeugung', 'Spez. Ertrag', 'Eigenverbrauch'])
    expect(g.aufteilung?.segmente.map((s) => [s.label, s.wert])).toEqual([['Eigenverbrauch', 250], ['Einspeisung', 250]])
  })
})

describe('KOMPONENTEN_ADAPTER — spezifische Blöcke (Inc. 3b)', () => {
  it('PV ② Topologie: WR→Module/Speicher via parent + Orphan, nur aktiv', async () => {
    getUebersicht.mockResolvedValue({ anlagenleistung_kwp: 10 })
    list.mockResolvedValue([
      inv({ id: 10, typ: 'wechselrichter', bezeichnung: 'WR Süd', parameter: { max_leistung_kw: 8 } }),
      inv({ id: 11, typ: 'pv-module', bezeichnung: 'Dach Süd', parent_investition_id: 10, leistung_kwp: 6, ausrichtung: 'Süd' }),
      inv({ id: 12, typ: 'speicher', bezeichnung: 'DC-Speicher', parent_investition_id: 10, parameter: { kapazitaet_kwh: 10 } }),
      inv({ id: 13, typ: 'pv-module', bezeichnung: 'Garage (verwaist)' }), // ohne parent → Orphan
      inv({ id: 14, typ: 'pv-module', bezeichnung: 'inaktiv', parent_investition_id: 10, aktiv: false }), // raus
    ])
    const [g] = await KOMPONENTEN_ADAPTER['pv-module'].fetch(1)
    expect(g.struktur?.art).toBe('topologie')
    if (g.struktur?.art !== 'topologie') throw new Error('topologie erwartet')
    expect(g.struktur.wr).toHaveLength(1)
    expect(g.struktur.wr[0].label).toBe('WR Süd')
    expect(g.struktur.wr[0].detail).toBe('8,0 kW')
    expect(g.struktur.wr[0].module.map((m) => m.label)).toEqual(['Dach Süd'])
    expect(g.struktur.wr[0].speicher.map((s) => s.label)).toEqual(['DC-Speicher'])
    expect(g.struktur.orphanModule.map((m) => m.label)).toEqual(['Garage (verwaist)']) // inaktiv NICHT dabei
    // PV: verknüpfte Investitionen für den Einstellungen-Block (aktiv, ohne inaktiv)
    expect(g.verknuepfteInvs?.map((i) => i.id).sort()).toEqual([10, 11, 12, 13])
  })

  it('Speicher ① Arbitrage-Sekundär (nur wenn fähig+Netzladung) + ② Kopplungs-Referenz', async () => {
    getSpeicherDashboard.mockResolvedValue([{
      investition: inv({ id: 5, typ: 'speicher', parent_investition_id: 10 }),
      zusammenfassung: { vollzyklen: 100, effizienz_prozent: 90, gesamt_entladung_kwh: 1000, gesamt_ladung_kwh: 1000,
        ersparnis_euro: 100, arbitrage_faehig: true, arbitrage_kwh: 200, arbitrage_avg_preis_cent: 12, arbitrage_gewinn_euro: 30 },
      monatsdaten: [],
    }])
    list.mockResolvedValue([inv({ id: 10, typ: 'wechselrichter', bezeichnung: 'WR Nord' })])
    const [g] = await KOMPONENTEN_ADAPTER.speicher.fetch(1)
    expect(g.sekundaer?.titel).toBe('Arbitrage (Netzladung)')
    expect(titles(g.sekundaer!.kpis)).toEqual(['Netzladung', 'Ø Ladepreis', 'Anteil an Ladung', 'Arbitrage-Gewinn'])
    expect(g.struktur?.art).toBe('referenz')
    if (g.struktur?.art !== 'referenz') throw new Error('referenz erwartet')
    expect(g.struktur.zeilen[0].hinweis).toContain('WR Nord')
  })

  it('Speicher: keine Arbitrage-Sekundär wenn nicht fähig', async () => {
    getSpeicherDashboard.mockResolvedValue([{
      investition: inv({ id: 5, typ: 'speicher' }),
      zusammenfassung: { vollzyklen: 100, effizienz_prozent: 90, gesamt_entladung_kwh: 1000, gesamt_ladung_kwh: 1000,
        ersparnis_euro: 100, arbitrage_faehig: false, arbitrage_kwh: 0, arbitrage_gewinn_euro: 0 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.speicher.fetch(1)
    expect(g.sekundaer).toBeUndefined()
    expect(g.struktur?.art).toBe('referenz') // eigenständig
  })

  it('WP ① Sekundär: getrennte JAZ + #238 nur wenn gepflegt', async () => {
    getWaermepumpeDashboard.mockResolvedValue([{
      investition: inv({ typ: 'waermepumpe' }),
      zusammenfassung: { durchschnitt_cop: 3.8, gesamt_waerme_kwh: 100, gesamt_stromverbrauch_kwh: 30,
        gesamt_heizenergie_kwh: 80, gesamt_warmwasser_kwh: 20, ersparnis_euro: 100,
        cop_heizen: 4.1, cop_warmwasser: 2.9, kompressor_starts_summe_erfasst: 1234, kompressor_starts_gesamt: 5678,
        betriebsstunden_summe_erfasst: 900, oe_laufzeit_pro_start_h: 0.73 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.waermepumpe.fetch(1)
    expect(titles(g.sekundaer!.kpis)).toEqual(['JAZ Heizen', 'JAZ Warmwasser', 'Kompressor-Starts', 'Betriebsstunden', 'Ø Laufzeit/Start'])
    // starts_pro_betriebsstunde fehlt → KPI nicht da
    expect(titles(g.sekundaer!.kpis)).not.toContain('Starts/Betriebsstunde')
  })

  it('WP: keine Sekundär ohne getrennte/238-Daten', async () => {
    getWaermepumpeDashboard.mockResolvedValue([{
      investition: inv({ typ: 'waermepumpe' }),
      zusammenfassung: { durchschnitt_cop: 3.8, gesamt_waerme_kwh: 100, gesamt_stromverbrauch_kwh: 30,
        gesamt_heizenergie_kwh: 80, gesamt_warmwasser_kwh: 20, ersparnis_euro: 100 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.waermepumpe.fetch(1)
    expect(g.sekundaer).toBeUndefined()
  })

  it('E-Auto ③ V2H nur wenn entladen', async () => {
    getEAutoDashboard.mockResolvedValue([{
      investition: inv({ typ: 'e-auto' }),
      zusammenfassung: { gesamt_km: 100, durchschnitt_verbrauch_kwh_100km: 18, pv_anteil_heim_prozent: 50,
        ersparnis_vs_benzin_euro: 100, gesamt_ladung_kwh: 100, ladung_pv_kwh: 50, ladung_netz_kwh: 50, ladung_extern_kwh: 0,
        v2h_entladung_kwh: 120, v2h_ersparnis_euro: 36 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER['e-auto'].fetch(1)
    expect(g.subKomponente?.titel).toBe('Vehicle-to-Home (V2H)')
    expect(titles(g.subKomponente!.kpis)).toEqual(['V2H Entladung', 'V2H Ersparnis'])
  })

  it('BKW ③ integrierter Speicher nur wenn hat_speicher', async () => {
    getBalkonkraftwerkDashboard.mockResolvedValue([{
      investition: inv({ typ: 'balkonkraftwerk' }),
      zusammenfassung: { gesamt_erzeugung_kwh: 800, gesamt_eigenverbrauch_kwh: 600, gesamt_einspeisung_kwh: 200,
        eigenverbrauch_quote_prozent: 75, spezifischer_ertrag_kwh_kwp: 900, gesamt_ersparnis_euro: 200,
        hat_speicher: true, speicher_kapazitaet_wh: 2048, speicher_ladung_kwh: 120, speicher_entladung_kwh: 100, speicher_effizienz_prozent: 83 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.balkonkraftwerk.fetch(1)
    expect(g.subKomponente?.titel).toBe('Integrierter Speicher')
    expect(g.subKomponente?.hinweis).toContain('2.048 Wh')
    expect(titles(g.subKomponente!.kpis)).toEqual(['Ladung', 'Entladung', 'Effizienz'])
  })

  it('Wallbox ② PV/Netz-Aufteilungs-Referenz (aus E-Auto-Ladedaten)', async () => {
    getWallboxDashboard.mockResolvedValue([{
      investition: inv({ typ: 'wallbox' }),
      zusammenfassung: { gesamt_heim_ladung_kwh: 500, ladung_pv_kwh: 300, ladung_netz_kwh: 200, pv_anteil_prozent: 60,
        gesamt_ladevorgaenge: 40, ersparnis_vs_extern_euro: 120 },
      monatsdaten: [],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.wallbox.fetch(1)
    expect(g.struktur?.art).toBe('referenz')
    if (g.struktur?.art !== 'referenz') throw new Error('referenz erwartet')
    expect(g.struktur.zeilen[0].label).toBe('PV/Netz-Aufteilung')
  })

  it('Wallbox ④/⑤ aus eigener IMD (Heimladung je Monat / Jahr)', async () => {
    getWallboxDashboard.mockResolvedValue([{
      investition: inv({ typ: 'wallbox' }),
      zusammenfassung: { gesamt_heim_ladung_kwh: 500, ladung_pv_kwh: 300, ladung_netz_kwh: 200, pv_anteil_prozent: 60,
        gesamt_ladevorgaenge: 40, ersparnis_vs_extern_euro: 120 },
      monatsdaten: [
        { jahr: 2025, monat: 1, verbrauch_daten: { ladung_kwh: 100 } },
        { jahr: 2025, monat: 2, verbrauch_daten: { ladung_kwh: 80 } },
      ],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.wallbox.fetch(1)
    expect(g.verlauf?.bars.map((b) => b.key)).toEqual(['heim'])
    expect(g.verlauf?.rows).toHaveLength(2)
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2025, summe: 180 }])
  })

  it('Sonstiges-Erzeuger ④/⑤ aus IMD (Erzeugung je Monat / Jahr)', async () => {
    getSonstigesDashboard.mockResolvedValue([{
      investition: inv({ typ: 'sonstiges' }),
      zusammenfassung: { kategorie: 'erzeuger', gesamt_erzeugung_kwh: 300, gesamt_eigenverbrauch_kwh: 200,
        gesamt_einspeisung_kwh: 100, eigenverbrauch_quote_prozent: 67, gesamt_ersparnis_euro: 90, co2_ersparnis_kg: 150 },
      monatsdaten: [
        { jahr: 2025, monat: 1, verbrauch_daten: { erzeugung_kwh: 120 } },
        { jahr: 2025, monat: 2, verbrauch_daten: { erzeugung_kwh: 80 } },
      ],
    }])
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.bars.map((b) => b.key)).toEqual(['erz'])
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2025, summe: 200 }])
  })
})
