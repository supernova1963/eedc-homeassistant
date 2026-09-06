/**
 * AuswertungenFinanzenV4 — Smoke-Test (A.5 Sub 3): die 3 Blöcke rendern, Geld in €
 * (R1 fmtZahl/formatGeld), T-Konto erbt das Filter-Jahr (R5: KEIN eigener Jahr-<select>).
 * Daten-Hooks/API gestubbt → isoliert auf die Sicht-Komposition.
 * R18-3 (Option B): `basis` kommt als Prop (Jahr-Filter in der Dispatcher-
 * Steuerleiste — die Sicht selbst hat KEINEN Jahr-Select mehr); R18-3b: bei
 * „Alle Jahre" kennzeichnet das T-Konto sichtbar, dass es das neueste Jahr zeigt.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import type { AuswertungBasis } from './useAuswertungBasis'

vi.mock('../hooks', async (importOriginal) => ({
  // R18-2: useApiData (SWR-Sicht-Cache) läuft ECHT — nur Anlage/Achse gemockt.
  ...(await importOriginal<typeof import('../hooks')>()),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useSchmaleAchse: () => false,
}))

const basisMock = {
  loading: false, jahr: 2025 as number | 'alle', setJahr: vi.fn(), jahre: [2025],
  zeitraumLabel: '2025',
  strompreis: { netzbezug_arbeitspreis_cent_kwh: 30, einspeiseverguetung_cent_kwh: 8, grundpreis_euro_monat: 10 },
  alleTarife: [], daten: [{ jahr: 2025, monat: 5 }],
  gefiltert: [{
    jahr: 2025, monat: 5, pv_erzeugung_kwh: 12000, eigenverbrauch_kwh: 6000,
    einspeisung_kwh: 6000, netzbezug_kwh: 3000, gesamtverbrauch_kwh: 9000,
    direktverbrauch_kwh: 4000, autarkie_prozent: 70, eigenverbrauchsquote_prozent: 50,
  }],
  stats: { anzahlMonate: 1, gesamtEinspeisung: 6000, gesamtEigenverbrauch: 6000, gesamtNetzbezug: 3000 },
  statsGesamt: { anzahlMonate: 1, gesamtEinspeisung: 6000, gesamtEigenverbrauch: 6000, gesamtNetzbezug: 3000 },
}
const basis = () => basisMock as unknown as AuswertungBasis

vi.mock('../api/cockpit', () => ({ cockpitApi: { getKomponentenZeitreihe: vi.fn().mockResolvedValue({ monatswerte: [] }) } }))
vi.mock('../api/aktuellerMonat', () => ({ aktuellerMonatApi: { getData: vi.fn().mockResolvedValue(null) } }))
vi.mock('../api/import', () => ({ importApi: { getPdfZipExportUrl: () => '/api/export.zip' } }))

import AuswertungenFinanzenV4 from './AuswertungenFinanzenV4'

describe('AuswertungenFinanzenV4 (Sub 3)', () => {
  it('rendert die 3 Blöcke; Einspeiseerlös in € (R1); KEIN Jahr-Select in der Sicht (R5/R18-3)', async () => {
    render(<AuswertungenFinanzenV4 basis={basis()} />)
    expect(await screen.findByText('Finanz-Übersicht')).toBeInTheDocument()
    expect(screen.getByText('SOLL/HABEN-T-Konto')).toBeInTheDocument()
    expect(screen.getByText('Berichte & Dokumente')).toBeInTheDocument()
    // 6.000 kWh × 8 ct = 480 € Einspeiseerlös → € sichtbar.
    expect(screen.getAllByText('€').length).toBeGreaterThan(0)
    // R5 + R18-3: der EINE Jahr-Select sitzt im Dispatcher — hier keiner.
    expect(screen.queryByLabelText('Jahr filtern')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Jahr wählen')).not.toBeInTheDocument()
  })

  it('R18-3b: bei „Alle Jahre" kennzeichnet das T-Konto sichtbar das gezeigte Jahr', async () => {
    Object.assign(basisMock, { jahr: 'alle' })
    render(<AuswertungenFinanzenV4 basis={basis()} />)
    expect(await screen.findByText(/das T-Konto bildet einen Monat oder ein Jahr ab und zeigt das Jahr 2025/)).toBeInTheDocument()
    cleanup()
    Object.assign(basisMock, { jahr: 2025 })
  })

  // ── #402 (rilmor-mhrs, 06.09.2026): die zwei Ertragswege werden auseinander-
  //    gehalten — und der dritte wird genannt, statt still zu fehlen ──
  //
  // Sein Fall: zwei Geräte mit EIGENEM Vergütungssatz (Allgemeinstrom,
  // Victron-EG) tragen zusammen 372,51 € gepflegten Erlös. Vor §9.2/E1 stand
  // der im T-Konto und in KEINER Kachel darüber („nicht mehr in den Grafen").
  //
  // Die beiden Kacheln behandeln ihn ABSICHTLICH verschieden, und genau das
  // prüft diese Probe:
  //   · **Einspeiseerlös** = Anlagenzähler × dem EINEN Satz der Anlage. Ein
  //     eigener Satz ist per Definition ein anderer (§8/9) ⇒ er bleibt
  //     DRAUSSEN, und die Kachel sagt das.
  //   · **Netto-Ertrag (PV)** = was die Anlage einbringt. Die Abgabe ist
  //     derselbe PV-Strom auf dem dritten Weg ⇒ er ist DRIN (fünfter Summand,
  //     wie in Cockpit → Jahr, HA-Sensor, PDF und Aussichten), und die Kachel
  //     sagt auch das.
  //
  // ⚠ Der Tooltip hängt am WERT, nicht am Kacheltitel (`KPICard.tsx:91`) —
  // eine Probe, die den Titel hovert, öffnet nichts und misst am Gegenstand
  // vorbei (N-365 hat genau diese Fassung schon einmal produziert).
  const finanzBasis = (erzeugerErloes: number) => ({
    ...basisMock,
    gefiltert: [{
      ...basisMock.gefiltert[0],
      einspeise_erloes_euro: 480, einspeise_nicht_verguetet_euro: 0,
      ev_ersparnis_euro: 300, bkw_ersparnis_euro: 0, ust_eigenverbrauch_euro: 0,
      netzbezug_kosten_euro: 200,
      // Der Vertrag der Route: `netto_ertrag_euro` ENTHÄLT den Erlös seit E1
      // (`monatsdaten.py` reicht ihn in `berechne_finanz_aggregat`).
      netto_ertrag_euro: 780 + erzeugerErloes,
      netto_bilanz_euro: 580 + erzeugerErloes,
      erzeuger_erloes_euro: erzeugerErloes,
    }],
  }) as unknown as AuswertungBasis

  /** Öffnet den Formel-Tooltip der Kachel mit diesem Titel und liefert den Text. */
  const tooltipTextVon = (titel: string) => {
    const karte = screen.getByText(titel).closest('div')?.parentElement
    const trigger = karte?.querySelector('.cursor-help')
    if (!trigger) throw new Error(`Kein Formel-Tooltip an der Kachel „${titel}"`)
    fireEvent.mouseEnter(trigger)
    return document.body.textContent ?? ''
  }

  it('#402: Einspeiseerlös grenzt den eigenen Vergütungssatz AUS — und die Zahl bleibt der Anlagenzähler', async () => {
    render(<AuswertungenFinanzenV4 basis={finanzBasis(372.51)} />)
    await screen.findByText('Finanz-Übersicht')

    expect(tooltipTextVon('Einspeiseerlös')).toContain('ohne Erzeuger mit eigenem Vergütungssatz')
    // ⭐ Der Kern: 480 €, NICHT 852,51 €. Sonst wäre die Formel daneben
    // („Einspeisung × Einspeisevergütung") eine falsche Aussage.
    expect(document.body.textContent).toContain('480')
    expect(document.body.textContent).not.toContain('852,51')
  })

  it('#402/E1: Netto-Ertrag (PV) SCHLIESST den dritten Weg ein und nennt ihn', async () => {
    render(<AuswertungenFinanzenV4 basis={finanzBasis(372.51)} />)
    await screen.findByText('Finanz-Übersicht')

    const text = tooltipTextVon('Netto-Ertrag (PV)')
    expect(text).toContain('Abgabe an Dritte')
    expect(text).toContain('372,51')
    // Die alte Abgrenzung darf an DIESER Kachel nicht mehr stehen — sie hat
    // die Abweichung zu Cockpit → Jahr festgeschrieben, statt sie zu heilen.
    expect(text).not.toContain('ohne Erzeuger mit eigenem Vergütungssatz')
  })

  it('#402: ohne solche Erzeuger bleibt beides weg (kein Posten, den es nicht gibt)', async () => {
    render(<AuswertungenFinanzenV4 basis={finanzBasis(0)} />)
    await screen.findByText('Finanz-Übersicht')
    expect(tooltipTextVon('Einspeiseerlös')).not.toContain('eigenem Vergütungssatz')
    cleanup()

    render(<AuswertungenFinanzenV4 basis={finanzBasis(0)} />)
    await screen.findByText('Finanz-Übersicht')
    expect(tooltipTextVon('Netto-Ertrag (PV)')).not.toContain('Abgabe an Dritte')
  })

  it('zeigt bei Basis-Fetch-Fehler den B8-Fehler-Baustein mit Retry statt 0-KPIs (S15)', () => {
    const refresh = vi.fn()
    Object.assign(basisMock, { error: 'Fehler beim Laden der aggregierten Daten', refresh })
    render(<AuswertungenFinanzenV4 basis={basis()} />)
    expect(screen.getByText('Fehler beim Laden der aggregierten Daten')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }))
    expect(refresh).toHaveBeenCalledTimes(1)
    cleanup()
    Object.assign(basisMock, { error: null, refresh: undefined })
  })
})
