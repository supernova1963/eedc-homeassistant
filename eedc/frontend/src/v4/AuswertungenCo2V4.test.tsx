/**
 * AuswertungenCo2V4 — Smoke-Test (A.5 Sub 2): die 3 Blöcke rendern, CO₂ trägt die
 * R2-Einheit (formatCo2: kg→t ab ≥1.000), Amortisations-Block ist data-gated.
 * Daten-Hooks/API gestubbt → isoliert auf die Sicht-Komposition.
 * R18-3 (Option B): `basis` kommt als Prop (Dispatcher hält den Jahr-Filter);
 * R18-3c: Amortisation rechnet IMMER auf der Gesamt-Historie und kennzeichnet
 * das bei gesetztem Einzeljahr-Filter sichtbar.
 *
 * ─── N-21 (2026-07-31) ──────────────────────────────────────────────────────
 * Die Sicht rechnet kein CO₂ mehr selbst; die Zahlen kommen aus `basis.co2`
 * (`/cockpit/nachhaltigkeit`, Layer-SoT `berechne_co2_bilanz`). Das Fixture ist
 * bewusst so gewählt, dass die kanonische Zahl (2,05 t) **weit** von der alten
 * Client-Formel entfernt liegt (16.000 kWh Erzeugung × 0,38 = 6,08 t) — jede
 * Zusicherung trägt die **Gegenprobe auf den alten Wert**.
 *
 * Rot gegen `HEAD~1`:
 *   • „zieht die Kopfzahl aus dem Kanon …"           (2,05 t statt 6,08 t)
 *   • „R18-3c: Amortisation bleibt Gesamt-bezogen"   (2,05 von 8,00 statt 6,08)
 *   • „der Jahr-Filter bewegt Block ① …"             (1,50 t statt 4,56 t)
 *   • „B8 bei Ausfall der CO₂-Reihe"                 (Zweig existierte nicht)
 * Die drei `baueCo2Monatsreihe`-Tests prüfen NEUEN Code und zählen deshalb
 * nicht als Beweis — sie sind Aufbereitungs-Wächter (Jahresfilter über alle
 * Serien, Sortierung, kumuliert nicht nachaddiert).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import type { AuswertungBasis } from './useAuswertungBasis'
import type { NachhaltigkeitMonat } from '../api/cockpit'

vi.mock('../hooks', async (importOriginal) => ({
  // R18-2: useApiData (SWR-Sicht-Cache) läuft ECHT — nur Anlage/Achse gemockt.
  ...(await importOriginal<typeof import('../hooks')>()),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useSchmaleAchse: () => false,
}))

const monat2024 = {
  jahr: 2024, monat: 11, pv_erzeugung_kwh: 4000, eigenverbrauch_kwh: 2000,
  einspeisung_kwh: 2000, netzbezug_kwh: 1500, gesamtverbrauch_kwh: 3500,
  direktverbrauch_kwh: 1500, autarkie_prozent: 60, eigenverbrauchsquote_prozent: 50,
}
const monat2025 = {
  jahr: 2025, monat: 5, pv_erzeugung_kwh: 12000, eigenverbrauch_kwh: 6000,
  einspeisung_kwh: 6000, netzbezug_kwh: 3000, gesamtverbrauch_kwh: 9000,
  direktverbrauch_kwh: 4000, autarkie_prozent: 70, eigenverbrauchsquote_prozent: 50,
}

/** Kanonische Reihe: PV + WP + E-Mob, kumuliert vom Backend. */
const co2Monate: NachhaltigkeitMonat[] = [
  {
    jahr: 2024, monat: 11, monat_name: 'November',
    co2_pv_kg: 400, co2_wp_kg: 100, co2_emob_kg: 50,
    co2_gesamt_kg: 550, co2_kumuliert_kg: 550, autarkie_prozent: 60,
  },
  {
    jahr: 2025, monat: 5, monat_name: 'Mai',
    co2_pv_kg: 1200, co2_wp_kg: 200, co2_emob_kg: 100,
    co2_gesamt_kg: 1500, co2_kumuliert_kg: 2050, autarkie_prozent: 70,
  },
]
const CO2_BASIS = { monate: co2Monate, gesamtKg: 2050, loading: false, error: null, refresh: vi.fn() }

const basisMock = {
  daten: [monat2024, monat2025], loading: false, strompreis: null, alleTarife: [],
  jahr: 'alle' as number | 'alle', setJahr: vi.fn(), jahre: [2025, 2024], zeitraumLabel: '2024–2025',
  gefiltert: [monat2024, monat2025],
  stats: { gesamtErzeugung: 16000, anzahlMonate: 2 },
  statsGesamt: { gesamtErzeugung: 16000, anzahlMonate: 2 },
  co2: CO2_BASIS,
}
const basis = () => basisMock as unknown as AuswertungBasis

vi.mock('../api/investitionen', () => ({
  investitionenApi: {
    getCO2Amortisation: vi.fn().mockResolvedValue({
      graue_last_gesamt_kg: 8000,
      posten: [{ investition_id: 1, bezeichnung: 'PV-Anlage', typ: 'pv', quelle: 'default', graue_last_kg: 8000 }],
    }),
  },
}))

import AuswertungenCo2V4, { baueCo2Monatsreihe } from './AuswertungenCo2V4'

describe('AuswertungenCo2V4 (Sub 2)', () => {
  it('rendert die 3 Blöcke; CO₂ in t (R2 ≥1.000 kg→t); Amortisation data-gated', async () => {
    render(<AuswertungenCo2V4 basis={basis()} />)
    // Block ① + ③ sofort; ② erscheint nach getCO2Amortisation (graue Last > 0).
    expect(await screen.findByText('CO₂-Bilanz & Wirkung')).toBeInTheDocument()
    expect(screen.getByText('Berechnungsgrundlage')).toBeInTheDocument()
    expect(await screen.findByText('CO₂-Amortisation')).toBeInTheDocument()
    // 2.050 kg → R2 schaltet auf t (≥1.000) → Einheit „t" im Strip.
    expect(screen.getAllByText('t').length).toBeGreaterThan(0)
  })

  it('N-21: zieht die Kopfzahl aus dem Kanon, nicht aus Erzeugung × 0,38', async () => {
    render(<AuswertungenCo2V4 basis={basis()} />)
    await screen.findByText('CO₂-Bilanz & Wirkung')
    // Σ co2_gesamt_kg = 550 + 1.500 = 2.050 kg → 2,05 t.
    expect(screen.getAllByText('2,05').length).toBeGreaterThan(0)
    // Gegenprobe auf den alten Wert: 16.000 kWh Erzeugung × 0,38 = 6.080 kg.
    // Er lag um Faktor 3 höher, weil er auch die eingespeisten kWh gutschrieb.
    expect(screen.queryByText('6,08')).toBeNull()
  })

  it('N-21: der Jahr-Filter bewegt Block ① auf die Monate DIESES Jahres', async () => {
    Object.assign(basisMock, { jahr: 2025, gefiltert: [monat2025] })
    render(<AuswertungenCo2V4 basis={basis()} />)
    await screen.findByText('CO₂-Bilanz & Wirkung')
    // Nur Mai 2025: 1.500 kg → 1,50 t. Alt wären 12.000 kWh × 0,38 = 4,56 t.
    expect(screen.getAllByText('1,50').length).toBeGreaterThan(0)
    expect(screen.queryByText('4,56')).toBeNull()
    // Ein Monat im Zeitraum — die Ø-Rechnung teilt durch dieselbe Menge, die sie summiert.
    expect(screen.getByText('1 Monate')).toBeInTheDocument()
    cleanup()
    Object.assign(basisMock, { jahr: 'alle', gefiltert: [monat2024, monat2025] })
  })

  it('R18-3c: Amortisation bleibt bei Einzeljahr-Filter Gesamt-bezogen + sichtbar gekennzeichnet', async () => {
    Object.assign(basisMock, { jahr: 2025, gefiltert: [monat2025] })
    render(<AuswertungenCo2V4 basis={basis()} />)
    const amortTitel = await screen.findByText('CO₂-Amortisation')
    fireEvent.click(amortTitel) // Block ② aufklappen (defaultOpen: false)
    // Kennzeichen sichtbar: Jahr-Filter wirkt im Amortisations-Block nicht.
    expect(await screen.findByText(/Jahr-Filter wirkt hier nicht/)).toBeInTheDocument()
    // „Bereits ausgeglichen" rechnet mit der GESAMT-Historie (2,05 t von 8,00 t),
    // nicht mit dem gefilterten Jahr (1,50 t). Die Gesamt-Zahl kommt als
    // `co2_gesamt_kg` aus dem Endpoint — sie wird nicht nachaddiert.
    expect(screen.getByText(/2,05.*von.*8,00/)).toBeInTheDocument()
    cleanup()
    Object.assign(basisMock, { jahr: 'alle', gefiltert: [monat2024, monat2025] })
  })

  it('zeigt bei Basis-Fetch-Fehler den B8-Fehler-Baustein mit Retry statt 0-KPIs (S15)', () => {
    const refresh = vi.fn()
    Object.assign(basisMock, { error: 'Fehler beim Laden der aggregierten Daten', refresh })
    render(<AuswertungenCo2V4 basis={basis()} />)
    expect(screen.getByText('Fehler beim Laden der aggregierten Daten')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }))
    expect(refresh).toHaveBeenCalledTimes(1)
    cleanup()
    Object.assign(basisMock, { error: null, refresh: undefined })
  })

  it('N-21: fällt die CO₂-Reihe aus, zeigt die Sicht B8 statt einer Seite voller Nullen', () => {
    const refresh = vi.fn()
    Object.assign(basisMock, { co2: { ...CO2_BASIS, monate: [], gesamtKg: 0, error: 'CO₂-Reihe nicht erreichbar', refresh } })
    render(<AuswertungenCo2V4 basis={basis()} />)
    expect(screen.getByText('CO₂-Reihe nicht erreichbar')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }))
    expect(refresh).toHaveBeenCalledTimes(1)
    cleanup()
    Object.assign(basisMock, { co2: CO2_BASIS })
  })
})

describe('baueCo2Monatsreihe (Aufbereitungs-Wächter, kein Fix-Beweis)', () => {
  it('filtert das Jahr über die GANZE Zeile — alle Serien, nicht nur die Summe', () => {
    const [p] = baueCo2Monatsreihe(co2Monate, 2025)
    expect(baueCo2Monatsreihe(co2Monate, 2025)).toHaveLength(1)
    // Der halb greifende Jahres-Filter war N-10: die Summe wechselte, die
    // Einzel-Serien blieben auf der Historie stehen.
    expect(p).toMatchObject({ jahr: 2025, monat: 5, co2_einsparung: 1500, co2Pv: 1200, co2Wp: 200, co2Emob: 100 })
  })

  it('sortiert aufsteigend — nur in dieser Reihenfolge ist `kumuliert_co2` monoton', () => {
    const reihe = baueCo2Monatsreihe([co2Monate[1], co2Monate[0]])
    expect(reihe.map((r) => r.name)).toEqual(['Nov 24', 'Mai 25'])
    expect(reihe.map((r) => r.kumuliert_co2)).toEqual([550, 2050])
  })

  it('übernimmt `kumuliert_co2` vom Backend, statt es nachzuaddieren', () => {
    // Backend-Wert bewusst inkonsistent zur Monatssumme gesetzt: würde der Client
    // selbst aufaddieren, stünde hier 550 + 1.500 = 2.050 statt der 9.999.
    const manipuliert = [co2Monate[0], { ...co2Monate[1], co2_kumuliert_kg: 9999 }]
    expect(baueCo2Monatsreihe(manipuliert).map((r) => r.kumuliert_co2)).toEqual([550, 9999])
  })
})
