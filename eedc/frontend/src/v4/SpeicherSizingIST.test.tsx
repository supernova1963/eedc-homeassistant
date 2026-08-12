/**
 * Der Simulator muss seine Zahl **einordnen**, nicht nur anzeigen.
 *
 * Zwei Dinge sind hier gegen konkrete Fehlgriffe geprüft und nicht gegen die
 * Theorie: (1) der Methoden-Hinweis ist Pflicht — ein Regler ohne ihn verspricht
 * eine Vorhersage; (2) die Antwort muss „rechnet sich nicht" auch **sagen**,
 * sonst liest sich eine positive Euro-Zahl wie eine Kaufempfehlung, obwohl die
 * Amortisation länger dauert als der Speicher lebt (an der Referenzanlage:
 * 49 €/Jahr für 2.000 € Zukauf).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SpeicherSizingIST } from './SpeicherSizingIST'
import { investitionenApi, type SizingPunkt, type SpeicherSizingResponse } from '../api/investitionen'

vi.mock('../components/park', () => ({
  Parkbar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  usePark: () => ({ istGeparkt: () => false }),
}))

/** Die gemessene Kurve der Referenzanlage (355 Tage, Basis 8,3 kWh). */
const PUNKT = (teil: Partial<SizingPunkt>): SizingPunkt => ({
  faktor: 1, kapazitaet_kwh: 8.3,
  einspeisung_kwh: 8183.9, netzbezug_kwh: 1575.3, eigenverbrauch_kwh: 3000,
  delta_netzbezug_kwh: 0, delta_einspeisung_kwh: 0,
  nutzen_euro_jahr: 0, mehrkosten_euro: 0, amortisation_jahre: null,
  ...teil,
})

const ANTWORT = (teil: Partial<SpeicherSizingResponse> = {}): SpeicherSizingResponse => ({
  kurve: [
    PUNKT({ faktor: 0.5, kapazitaet_kwh: 4.2, delta_netzbezug_kwh: 589, delta_einspeisung_kwh: 681.5, nutzen_euro_jahr: -156 }),
    PUNKT({}),
    PUNKT({ faktor: 1.5, kapazitaet_kwh: 12.5, delta_netzbezug_kwh: -184.9, delta_einspeisung_kwh: -215.6, nutzen_euro_jahr: 49, mehrkosten_euro: 2100, amortisation_jahre: 43 }),
  ],
  basis_kapazitaet_kwh: 8.3,
  basis_roundtrip_prozent: 86.7,
  basis_kalibriert: true,
  kalibrierung_paare_laden: 435,
  kalibrierung_paare_entladen: 103,
  kalibrierung_stunden_verworfen: 2705,
  gepflegte_kapazitaet_kwh: 12.1,
  gepflegter_wirkungsgrad_prozent: 95,
  soc_nutzung: {
    soc_p5: 0, soc_median: 53.1, soc_p95: 100,
    tages_max_median: 100, tage_bis_voll: 247, tage_bis_leer: 159,
    tage_mit_soc: 361, median_je_speicher: {}, laedt_planmaessig_voll: true,
  },
  tage_mit_daten: 365,
  tage_simuliert: 355,
  historie_reicht: true,
  min_tage_fuer_aussage: 180,
  von: '2025-08-01',
  bis: '2026-07-31',
  anzahl_speicher: 1,
  bezug_preis_cent: 35,
  einspeise_verg_cent: 8,
  richtpreis_eur_je_kwh: 500,
  ...teil,
})

describe('SpeicherSizingIST', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('startet auf der heutigen Kapazität als Bezugspunkt', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT())

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/der Bezugspunkt/i)).toBeInTheDocument())
    expect(screen.getByText(/100 % von heute/)).toBeInTheDocument()
  })

  it('sagt bei zu langer Amortisation ausdrücklich, dass es sich nicht rechnet', async () => {
    // Der real gemessene Fall: +50 % Kapazität bringen 49 €/Jahr bei 2.100 €.
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT())

    render(<SpeicherSizingIST anlageId={1} />)
    await waitFor(() => expect(screen.getByRole('slider')).toBeInTheDocument())
    fireEvent.change(screen.getByRole('slider'), { target: { value: '2' } })

    await waitFor(() => expect(screen.getByText(/rechnet sich nicht/i)).toBeInTheDocument())
    // Und die Gegenseite steht daneben, statt verschwiegen zu werden.
    expect(screen.getByText(/weniger Einspeisung/)).toBeInTheDocument()
  })

  it('zeigt den Methoden-Hinweis immer — er ist keine Option', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT())

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/keine Vorhersage/i)).toBeInTheDocument())
    expect(screen.getByText(/eingespielt/i)).toBeInTheDocument()
  })

  it('weist gepflegte statt gemessener Basis als Unsicherheit aus', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT({
      basis_kalibriert: false, basis_kapazitaet_kwh: 12.1, basis_roundtrip_prozent: 95,
      kalibrierung_paare_laden: null, kalibrierung_paare_entladen: null,
    }))

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/gepflegten Geräte-Parameter/i)).toBeInTheDocument())
    expect(screen.getByText(/zu günstig/i)).toBeInTheDocument()
  })

  it('nennt die gemessene Basis, ohne sie als Gerätemangel zu verkaufen', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT())

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/kein Gerätemangel/i)).toBeInTheDocument())
  })

  it('meldet zu kurze Historie, ohne die Kurve zu verstecken', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT({
      historie_reicht: false, tage_simuliert: 30,
    }))

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/Belastbar wird die/i)).toBeInTheDocument())
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })

  it('unterscheidet „keine Bezugsgröße" von „kein Nutzen"', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT({ kurve: [] }))

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/fehlt die Bezugsgröße/i)).toBeInTheDocument())
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })

  it('erklärt die Lücke als Ladeverlust, wenn die Anlage voll lädt (N-238)', async () => {
    // Die Referenzanlage: 247 von 361 Tagen bis 100 %, gepflegt 12,1 / gemessen 8,3.
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT())

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/Ladeverluste/)).toBeInTheDocument())
    expect(screen.getByText(/247 von 361 Tagen/)).toBeInTheDocument()
    expect(screen.getByText(/gepflegte Kapazität ist damit richtig/)).toBeInTheDocument()
  })

  it('erklärt die Lücke als Ladestrategie, wenn nie voll geladen wird (N-238)', async () => {
    // Gernots Einwand: es gibt Anwender, die bewusst nicht auf 100 % laden.
    // Dann ist die kleinere Zahl kein Verlust — und eine „Korrektur" wäre falsch.
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT({
      soc_nutzung: {
        soc_p5: 12, soc_median: 45, soc_p95: 78,
        tages_max_median: 80, tage_bis_voll: 0, tage_bis_leer: 3,
        tage_mit_soc: 200, median_je_speicher: {}, laedt_planmaessig_voll: false,
      },
    }))

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/planmäßig nicht voll/)).toBeInTheDocument())
    expect(screen.getByText(/Ihre eigene Ladestrategie/)).toBeInTheDocument()
    expect(screen.queryByText(/Ladeverluste/)).not.toBeInTheDocument()
  })

  it('zeigt gepflegte und gemessene Kapazität nebeneinander', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT())

    render(<SpeicherSizingIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText('Gepflegt (nutzbar)')).toBeInTheDocument())
    expect(screen.getByText('12,1 kWh')).toBeInTheDocument()
    expect(screen.getByText('Im Alltag bewegt')).toBeInTheDocument()
    // „8,3 kWh" steht auch im Befund-Satz — hier zählt die Zeile der Definitionsliste.
    expect(screen.getAllByText('8,3 kWh').length).toBeGreaterThan(0)
    expect(screen.getByText('Genutzter Ladestand')).toBeInTheDocument()
    expect(screen.getByText('0 – 100 %')).toBeInTheDocument()
  })

  it('meldet die Park-IDs erst, wenn wirklich etwas zu zeigen ist', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherSizing').mockResolvedValue(ANTWORT({ kurve: [] }))
    const melde = vi.fn()

    render(<SpeicherSizingIST anlageId={1} melde={melde} />)

    await waitFor(() => expect(melde).toHaveBeenCalled())
    expect(melde).toHaveBeenLastCalledWith([])
  })
})
