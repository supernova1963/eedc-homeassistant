/**
 * Päckchen Z-Client (9.11.2026): «der Client rechnet nichts» — die Sichten zeigen Backend-Felder.
 *
 * Je umgestellter Stelle zwei Aussagen: (1) die Sicht zeigt den Wert des Feldes, (2) ohne das Feld rechnet sie
 * NICHT selbst nach (Strich bzw. «—»), obwohl beide Operanden in der Antwort stehen. Die Gleichheit Backend = alte
 * Client-Formel ist auf den Demo-Kopien gemessen (Bericht `PAECKCHEN-Z-CLIENT-2026-11-09.md`) und im Backend in
 * `test_z_client_felder.py` an den Layer-Funktionen festgehalten.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat, monatsZeile } from '../test/factories'
import { PrognoseTabelle } from '../pages/auswertung/EnergieprofilPrognose'
import type { TagesPrognose } from '../api/energie_profil'
import { createMonatsZeitreihe } from '../pages/auswertung/types'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}
// Feste Uhr (Wächter N7): die Fixtures tragen Datums-Literale.
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-07-27T12:00:00')) })
afterEach(() => { cleanup(); vi.useRealTimers() })

function block(id: string, over: Partial<AktuellerMonatResponse>) {
  const b = baueKomponentenBloecke(aktuellerMonat(2026, 6, over), NOOP, 'monat').find((x) => x.id === id)
  expect(b, `${id} muss entstehen`).toBeDefined()
  cleanup()
  return render(<>{b!.render(false)}</>)
}

describe('Balkonkraftwerk — Einspeisung und EV-Quote aus dem Backend', () => {
  const BKW = { bkw_erzeugung_kwh: 100, bkw_eigenverbrauch_kwh: 30, hat_balkonkraftwerk: true }

  it('zeigt die Felder der Antwort', () => {
    const { container } = block('k-bkw', { ...BKW, bkw_einspeisung_kwh: 70, bkw_eigenverbrauch_quote_prozent: 30 })
    expect(container.textContent).toMatch(/30 % EV-Quote/)
    expect(container.textContent).toMatch(/Einspeisung\s*70/)
  })

  it('rechnet ohne die Felder nicht selbst nach', () => {
    const { container } = block('k-bkw', BKW)
    expect(container.textContent).not.toMatch(/EV-Quote/)
    expect(container.textContent).not.toMatch(/Einspeisung\s*70/)
  })
})

describe('Sonstiges-Verbraucher — PV-Anteil aus dem Backend', () => {
  const geraet = { bezeichnung: 'Pool', kategorie: 'verbraucher', verbrauch_kwh: 40, bezug_pv_kwh: 10, bezug_netz_kwh: 30 }

  it('zeigt das Feld der Antwort', () => {
    block('k-sonstiges-verbraucher', { sonstiges_geraete: [{ ...geraet, pv_anteil_prozent: 25 }] } as Partial<AktuellerMonatResponse>)
    expect(screen.getByText('25')).toBeInTheDocument()
  })

  it('ohne Feld keine PV-Anteil-Kachel (keine Client-Quote)', () => {
    const { container } = block('k-sonstiges-verbraucher', { sonstiges_geraete: [geraet] } as Partial<AktuellerMonatResponse>)
    expect(container.textContent).not.toMatch(/10 kWh PV/)
  })
})

describe('Energieprofil-Prognose — Netto aus dem Backend', () => {
  const daten = {
    datum: '2026-07-27', stunden: [], pv_summe_kwh: 9, verbrauch_summe_kwh: 1.2, netzbezug_summe_kwh: 0,
    einspeisung_summe_kwh: 9, eigenverbrauch_kwh: 1.2, autarkie_prozent: 100, speicher_kapazitaet_kwh: null,
    verbrauch_basis: 'historisch', pv_quelle: 'eedc', daten_tage: 30, hinweise: [],
  } as unknown as TagesPrognose

  it('zeigt `netto_summe_kwh`', () => {
    const { container } = render(<PrognoseTabelle daten={{ ...daten, netto_summe_kwh: 7.8 }} />)
    expect(container.textContent).toMatch(/7,8/)
  })

  it('rechnet ohne das Feld nicht PV − Verbrauch', () => {
    const { container } = render(<PrognoseTabelle daten={daten} />)
    expect(container.textContent).not.toMatch(/7,8/)
  })
})

describe('Werte-Tabelle — Wallbox-PV-Anteil aus der Antwort', () => {
  it('liest `wallbox_pv_anteil_prozent` und rechnet ohne es nicht', () => {
    const basis = { wallbox_ladung_kwh: 200, wallbox_ladung_pv_kwh: 50 }
    const [mit] = createMonatsZeitreihe([monatsZeile(2026, 5, { ...basis, wallbox_pv_anteil_prozent: 25 })])
    expect(mit.wallbox_pv_anteil).toBe(25)
    expect(mit.eauto_pv_anteil).toBe(25)
    const [ohne] = createMonatsZeitreihe([monatsZeile(2026, 5, basis)])
    expect(ohne.wallbox_pv_anteil).toBeNull()
  })
})
