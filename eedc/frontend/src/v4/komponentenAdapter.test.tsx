import { describe, it, expect, vi, beforeEach } from 'vitest'

// API-Module mocken — der Adapter normalisiert nur deren Felder.
const getSpeicherDashboard = vi.fn()
const getWaermepumpeDashboard = vi.fn()
const getEAutoDashboard = vi.fn()
const getSonstigesDashboard = vi.fn()
const getUebersicht = vi.fn()
const listAggregiert = vi.fn()

vi.mock('../api/investitionen', () => ({
  investitionenApi: {
    getSpeicherDashboard: (...a: unknown[]) => getSpeicherDashboard(...a),
    getWaermepumpeDashboard: (...a: unknown[]) => getWaermepumpeDashboard(...a),
    getEAutoDashboard: (...a: unknown[]) => getEAutoDashboard(...a),
    getWallboxDashboard: vi.fn(),
    getBalkonkraftwerkDashboard: vi.fn(),
    getSonstigesDashboard: (...a: unknown[]) => getSonstigesDashboard(...a),
  },
}))
vi.mock('../api/cockpit', () => ({ cockpitApi: { getUebersicht: (...a: unknown[]) => getUebersicht(...a) } }))
vi.mock('../api/monatsdaten', () => ({ monatsdatenApi: { listAggregiert: (...a: unknown[]) => listAggregiert(...a) } }))

import { KOMPONENTEN_ADAPTER } from './komponentenAdapter'

const inv = (over = {}) => ({ id: 1, anlage_id: 1, typ: 'x', bezeichnung: 'Gerät A', aktiv: true, ...over })
const titles = (ks: { title: string }[]) => ks.map((k) => k.title)

beforeEach(() => vi.clearAllMocks())

describe('KOMPONENTEN_ADAPTER', () => {
  it('Speicher: D2-KPIs + Ladequellen-Aufteilung (PV/Netz aus Arbitrage)', async () => {
    getSpeicherDashboard.mockResolvedValue([{
      investition: inv({ typ: 'speicher' }),
      zusammenfassung: { vollzyklen: 312, effizienz_prozent: 90, ist_wirkungsgrad_prozent: 92,
        gesamt_entladung_kwh: 4100, gesamt_ladung_kwh: 4500, arbitrage_kwh: 500, ersparnis_euro: 286 },
    }])
    const [g] = await KOMPONENTEN_ADAPTER.speicher.fetch(1)
    expect(titles(g.status)).toEqual(['Vollzyklen', 'Wirkungsgrad η', 'Durchsatz', 'Ersparnis'])
    // bevorzugt ist_wirkungsgrad_prozent (92) vor effizienz_prozent (90)
    expect(g.status[1].value).toBe('92')
    expect(g.aufteilung?.segmente.map((s) => [s.label, s.wert])).toEqual([['PV-Ladung', 4000], ['Netz-Ladung', 500]])
  })

  it('Wärmepumpe: JAZ + Heizung/Warmwasser-Aufteilung', async () => {
    getWaermepumpeDashboard.mockResolvedValue([{
      investition: inv({ typ: 'waermepumpe' }),
      zusammenfassung: { durchschnitt_cop: 3.8, gesamt_waerme_kwh: 12400, gesamt_stromverbrauch_kwh: 3300,
        gesamt_heizenergie_kwh: 9400, gesamt_warmwasser_kwh: 3000, ersparnis_euro: 410 },
    }])
    const [g] = await KOMPONENTEN_ADAPTER.waermepumpe.fetch(1)
    expect(titles(g.status)).toEqual(['JAZ', 'Wärme erzeugt', 'Strom verbraucht', 'Ersparnis vs. Gas'])
    expect(g.aufteilung?.segmente.map((s) => s.label)).toEqual(['Heizung', 'Warmwasser'])
  })

  it('E-Auto: Ø-Verbrauch null → „—" statt 0 (nie 0 erfinden)', async () => {
    getEAutoDashboard.mockResolvedValue([{
      investition: inv({ typ: 'e-auto' }),
      zusammenfassung: { gesamt_km: 14200, durchschnitt_verbrauch_kwh_100km: null, pv_anteil_heim_prozent: 61,
        ersparnis_vs_benzin_euro: 1120, gesamt_ladung_kwh: 1000, ladung_pv_kwh: 600, ladung_netz_kwh: 300, ladung_extern_kwh: 100 },
    }])
    const [g] = await KOMPONENTEN_ADAPTER['e-auto'].fetch(1)
    expect(g.status[1].value).toBe('—')
    expect(g.aufteilung?.segmente.map((s) => s.label)).toEqual(['PV', 'Netz', 'Extern'])
  })

  it('Sonstiges: kategorie wählt die richtige 4er-KPI-Reihe', async () => {
    getSonstigesDashboard.mockResolvedValue([{
      investition: inv({ typ: 'sonstiges' }),
      zusammenfassung: { kategorie: 'verbraucher', beschreibung: 'Pool', gesamt_verbrauch_kwh: 320,
        pv_anteil_prozent: 72, kosten_netz_euro: 40, ersparnis_pv_euro: 96, sonderkosten_euro: 0 },
    }])
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(titles(g.status)).toEqual(['Verbrauch', 'PV-Anteil', 'Netzkosten', 'PV-Ersparnis'])
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
