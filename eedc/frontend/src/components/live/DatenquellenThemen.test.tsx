/**
 * Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.5/§1.7) — Block «Themen» in den Datenquellen und der Themen-Picker.
 *
 * Block: nur an Geräten mit «Überblick» (Wallbox ja, Speicher nein), Hinweiszeile wörtlich, Anlegen, Umbenennen
 * (Enter), Pfeile, Entfernen mit Rückfrage (nur mit Einträgen), amber bei Quelle ohne Wert, Position vor «Weitere Größen
 * erfassen». Picker mit `alle`: Abruf mit `alle`, Deckel 200 samt Zeile «‹n› weitere», Suche grenzt ein, keine
 * Einheiten-Warnung und kein Takt-Check, Domain an der Zeile.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import DatenquellenThemen, { THEMEN_HINWEIS } from './DatenquellenThemen'
import DatenquellenHaPicker, { ALLE_DECKEL } from './DatenquellenHaPicker'
import { datenquellenApi, type DatenquelleGruppe, type ThemaGruppe } from '../../api/datenquellen'

const eintrag = (id: string, label: string, quelle: string, wert: string | null = null) => ({
  id, label, feld_id: `inv_thema_4_${id}`, quelle, ha_entity: quelle === 'ha_app' ? 'lock.carport' : null,
  ha_name: null, gateway_topic: null, standard_topic: `eedc/1_A/live/inv/4_Carport/thema_${id}`,
  wert_text: wert, einheit: '', wert_zeit: null,
})
const THEMEN: ThemaGruppe[] = [
  { id: 't1', name: 'Fahrzeugzustand', eintraege: [eintrag('e2', 'Türen', 'ha_app', 'locked'), eintrag('e3', 'Reifen', 'mqtt_inbound_standard')] },
  { id: 't4', name: 'Leer', eintraege: [] },
]

vi.mock('../../api/datenquellen', () => {
  const feld = (gid: string, feld: string, label: string, erweitert = false) => ({
    id: `${gid}_${feld}`, feld, typ: 'x', label, einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: `eedc/1/${gid}/${feld}`,
    quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [], erweitert,
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null, ausgewertet_in: [],
  })
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        anlage_id: 1,
        gruppen: [
          { id: 'basis', titel: 'Anlage / Zähler', typ: 'basis', felder: [feld('basis', 'netzbezug_w', 'Netzbezug')] },
          { id: 'inv:3', titel: 'Akku', typ: 'speicher', felder: [feld('inv3', 'leistung_w', 'Leistung')], themen: [] },
          { id: 'inv:4', titel: 'Carport', typ: 'wallbox', themen: [],
            felder: [feld('inv4', 'leistung_w', 'Leistung'), feld('inv4', 'ladestrom_a', 'Ladestrom', true)] },
        ],
        verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
        historie_hinweis: null,
      })),
      setQuelle: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
      haSensoren: vi.fn(),
      themaAnlegen: vi.fn(),
      themaAendern: vi.fn(),
      themaEntfernen: vi.fn(),
      eintragAnlegen: vi.fn(),
      eintragAendern: vi.fn(),
      eintragEntfernen: vi.fn(),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

const GRUPPE: DatenquelleGruppe = { id: 'inv:4', titel: 'Carport', typ: 'wallbox', felder: [], themen: THEMEN }
const VERF = { ha: true, mqtt: true, ha_quelle: 'ha_app' }

function block(gruppe: DatenquelleGruppe = GRUPPE) {
  const onNeuLaden = vi.fn()
  const r = render(<DatenquellenThemen anlageId={1} gruppe={gruppe} verfuegbarkeit={VERF} onNeuLaden={onNeuLaden} />)
  return { ...r, onNeuLaden }
}

describe('Themen-Kacheln TH-E1 — Block «Themen»', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('steht nur an Geräten mit «Überblick», vor «Weitere Größen erfassen», mit der Hinweiszeile', async () => {
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    await waitFor(() => expect(container.querySelectorAll('[data-themen-block]').length).toBe(1))
    const wallbox = container.querySelector('[data-themen-block]')!
    expect(wallbox.querySelector('[data-themen-hinweis]')!.textContent).toBe(THEMEN_HINWEIS)
    // Position: der Block steht vor dem Klapp-Knopf «Weitere Größen erfassen» desselben Geräts.
    const weitere = screen.getByText(/Weitere Größen erfassen/)
    expect(wallbox.compareDocumentPosition(weitere) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('Hinweis wörtlich (Gernot 1.11.2026)', () => {
    expect(THEMEN_HINWEIS).toBe(
      'Jedes Thema ist eine Kachel im Schaubild: die ersten zwei Einträge mit Wert stehen im Bild, alle im Tooltip und '
      + 'in der Karte «Themen» — die Reihenfolge stellst du mit den Pfeilen ein. Angezeigt wird, was Home Assistant '
      + 'liefert (z. B. locked); für Klartext einen Template-Helfer zuordnen.',
    )
  })

  it('rendert nichts an einem Typ ohne «Überblick»', () => {
    const { container } = block({ ...GRUPPE, typ: 'speicher' })
    expect(container.innerHTML).toBe('')
  })

  it('Wert grün, Quelle ohne Wert amber', () => {
    const { container } = block()
    const [tueren, reifen] = Array.from(container.querySelectorAll('[data-themen-eintrag]'))
    expect(within(tueren as HTMLElement).getByText('locked').className).toMatch(/green/)
    const wert = (reifen as HTMLElement).querySelector('[data-themen-wert]')!
    expect(wert.textContent).toBe('–')
    expect(wert.className).toMatch(/amber/)
  })

  it('+ Thema und + Eintrag rufen die Routen und übernehmen die Antwort', async () => {
    vi.mocked(datenquellenApi.themaAnlegen).mockResolvedValue({ investition_id: 4, themen: [...THEMEN, { id: 't5', name: 'Thema 3', eintraege: [] }] })
    vi.mocked(datenquellenApi.eintragAnlegen).mockResolvedValue({ investition_id: 4, themen: THEMEN })
    block()
    fireEvent.click(screen.getByRole('button', { name: /^Thema$/ }))
    await waitFor(() => expect(screen.getByDisplayValue('Thema 3')).toBeTruthy())
    expect(datenquellenApi.themaAnlegen).toHaveBeenCalledWith(1, 4)
    await act(async () => { fireEvent.click(screen.getAllByRole('button', { name: /^Eintrag$/ })[0]) })
    expect(datenquellenApi.eintragAnlegen).toHaveBeenCalledWith(1, 4, 't1')
  })

  it('Umbenennen mit Enter, Pfeile verschieben', async () => {
    vi.mocked(datenquellenApi.themaAendern).mockResolvedValue({ investition_id: 4, themen: THEMEN })
    block()
    const name = screen.getByDisplayValue('Fahrzeugzustand')
    fireEvent.change(name, { target: { value: 'Zustand' } })
    fireEvent.keyDown(name, { key: 'Enter' })
    fireEvent.blur(name)
    await waitFor(() => expect(datenquellenApi.themaAendern).toHaveBeenCalledWith(1, 4, 't1', { name: 'Zustand' }))
    await act(async () => { fireEvent.click(screen.getAllByRole('button', { name: 'Thema nach unten' })[0]) })
    expect(datenquellenApi.themaAendern).toHaveBeenCalledWith(1, 4, 't1', { position: 1 })
    expect((screen.getAllByRole('button', { name: 'Thema nach oben' })[0] as HTMLButtonElement).disabled).toBe(true)
  })

  it('Entfernen mit Einträgen fragt zurück, ohne Einträge direkt', async () => {
    vi.mocked(datenquellenApi.themaEntfernen).mockResolvedValue({ investition_id: 4, themen: [THEMEN[0]] })
    block()
    const knoepfe = screen.getAllByRole('button', { name: /Thema entfernen/ })
    fireEvent.click(knoepfe[1])  // «Leer» ohne Einträge
    expect(datenquellenApi.themaEntfernen).toHaveBeenCalledWith(1, 4, 't4')
    vi.mocked(datenquellenApi.themaEntfernen).mockClear()
    fireEvent.click(screen.getAllByRole('button', { name: /Thema entfernen/ })[0])
    expect(datenquellenApi.themaEntfernen).not.toHaveBeenCalled()
    expect(await screen.findByText(/mit 2 Einträgen und ihren Zuordnungen entfernen/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Entfernen' }))
    await waitFor(() => expect(datenquellenApi.themaEntfernen).toHaveBeenCalledWith(1, 4, 't1'))
  })

  it('H2: Eintrag umbenennen, verschieben, entfernen nennen das Gerät (Nachlauf 4.2.0)', async () => {
    vi.mocked(datenquellenApi.eintragAendern).mockResolvedValue({ investition_id: 4, themen: THEMEN })
    vi.mocked(datenquellenApi.eintragEntfernen).mockResolvedValue({ investition_id: 4, themen: THEMEN })
    const { container } = block()
    const tueren = container.querySelectorAll('[data-themen-eintrag]')[0] as HTMLElement
    const label = within(tueren).getByDisplayValue('Türen')
    fireEvent.change(label, { target: { value: 'Türschloss' } })
    fireEvent.keyDown(label, { key: 'Enter' })
    fireEvent.blur(label)
    await waitFor(() => expect(datenquellenApi.eintragAendern).toHaveBeenCalledWith(1, 4, 't1', 'e2', { label: 'Türschloss' }))
    await act(async () => { fireEvent.click(within(tueren).getByRole('button', { name: 'Eintrag nach unten' })) })
    expect(datenquellenApi.eintragAendern).toHaveBeenCalledWith(1, 4, 't1', 'e2', { position: 1 })
    await act(async () => { fireEvent.click(within(tueren).getByRole('button', { name: 'Eintrag entfernen' })) })
    expect(datenquellenApi.eintragEntfernen).toHaveBeenCalledWith(1, 4, 't1', 'e2')
  })

  it('Keine setzt die Quelle über die Feld-Route und lädt neu', async () => {
    const { container, onNeuLaden } = block()
    const reifen = container.querySelectorAll('[data-themen-eintrag]')[1] as HTMLElement
    fireEvent.click(within(reifen).getByRole('button', { name: 'Keine' }))
    expect(datenquellenApi.setQuelle).toHaveBeenCalledWith(1, 'inv_thema_4_e3', 'keine', undefined, undefined)
    await waitFor(() => expect(onNeuLaden).toHaveBeenCalled())
  })
})

describe('Themen-Kacheln TH-E1 — Picker mit `alle`', () => {
  beforeEach(() => vi.clearAllMocks())

  const sensoren = (n: number) => Array.from({ length: n }, (_, i) => ({
    entity_id: `lock.tuer_${String(i).padStart(3, '0')}`, friendly_name: `Tür ${i}`, unit: i === 0 ? 'kWh' : null,
    device_class: null, state: 'locked', domain: 'lock',
  }))

  it('fragt mit `alle`, deckelt bei 200, Suche grenzt ein, Domain an der Zeile, keine Warnung', async () => {
    vi.mocked(datenquellenApi.haSensoren).mockResolvedValue({
      verfuegbar: true, quelle: 'ha_app', sensoren: sensoren(230), fehler: null, integrationen: [], vorschlaege: [], warnungen: {},
    })
    const onSpeichern = vi.fn()
    render(<DatenquellenHaPicker isOpen alle anlageId={1} feldLabel="Türen" feldEinheit="W" initialEntity={null}
      onClose={() => {}} onSpeichern={onSpeichern} />)
    await screen.findByText('lock.tuer_000')
    expect(datenquellenApi.haSensoren).toHaveBeenCalledWith(1, undefined, undefined, true)
    expect(screen.getAllByText(/^lock\.tuer_/).length).toBe(ALLE_DECKEL)
    expect(screen.getByText('30 weitere — über die Suche eingrenzen')).toBeTruthy()
    expect(screen.queryByText(/passt nicht zu/)).toBeNull()
    expect(screen.getByText(/^lock · Tür 0/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('HA-Sensor suchen'), { target: { value: 'tuer_229' } })
    expect(screen.getAllByText(/^lock\.tuer_/).length).toBe(1)
    expect(screen.queryByText(/weitere — über die Suche/)).toBeNull()
    fireEvent.click(screen.getByText('lock.tuer_229'))
    expect(onSpeichern).toHaveBeenCalledWith('lock.tuer_229')
    expect(datenquellenApi.taktCheck).not.toHaveBeenCalled()
  })
})

describe('Nachlauf 4.2.0 H2 — Themen-Routen tragen `?investition_id=`', () => {
  it('alle fünf Routen an einem Thema nennen das Gerät als Query', async () => {
    const { api } = await vi.importActual<typeof import('../../api/client')>('../../api/client')
    const echt = (await vi.importActual<typeof import('../../api/datenquellen')>('../../api/datenquellen')).datenquellenApi
    const patch = vi.spyOn(api, 'patch').mockResolvedValue({})
    const del = vi.spyOn(api, 'delete').mockResolvedValue({})
    const post = vi.spyOn(api, 'post').mockResolvedValue({})
    try {
      await echt.themaAendern(1, 7, 't1', { name: 'x' })
      await echt.themaEntfernen(1, 7, 't1')
      await echt.eintragAnlegen(1, 7, 't1', 'Türen')
      await echt.eintragAendern(1, 7, 't1', 'e2', { position: 0 })
      await echt.eintragEntfernen(1, 7, 't1', 'e2')
      expect(patch.mock.calls.map((c) => c[0])).toEqual([
        '/datenquellen/1/themen/t1?investition_id=7', '/datenquellen/1/themen/t1/eintraege/e2?investition_id=7',
      ])
      expect(del.mock.calls.map((c) => c[0])).toEqual([
        '/datenquellen/1/themen/t1?investition_id=7', '/datenquellen/1/themen/t1/eintraege/e2?investition_id=7',
      ])
      expect(post.mock.calls).toEqual([['/datenquellen/1/themen/t1/eintraege?investition_id=7', { label: 'Türen' }]])
    } finally {
      patch.mockRestore()
      del.mockRestore()
      post.mockRestore()
    }
  })
})
