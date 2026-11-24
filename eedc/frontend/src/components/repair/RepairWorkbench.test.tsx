/**
 * Reparatur-Werkbank — Knopf „HA-Spiegel jetzt abgleichen" (MartyBr, simon42 #429) und die Operation
 * „Werte vor dem Sensorbeginn verwerfen" (HA-Bauform S3, E-S3-5: Auswahl, Vorbelegung, Plan-Parameter, Vorschau-Sätze
 * aus dem Backend) und „Werte eines Felds vor einem Zeitpunkt verwerfen" (Fund-Päckchen H, H1: alle Felder, Zeitpunkt nicht
 * in der Zukunft, Vorschau-Sätze und Ablehnung aus dem Backend).
 *
 * Nach einer Korrektur in Home Assistant zeigten die Tages-Kennzahlen bis zum Nachtlauf (02:45) den alten
 * HA-Spiegel. Der Werkbank-Eintrag ruft den Lauf von Hand und zeigt die Ergebniszeile aus der Antwort
 * (`meldung`, Backend-Text — der Client rechnet nichts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { KanalAbgleichErgebnis, KanalAuswahlEintrag, PlanResponse } from '../../api/repair'
import { REPARATUR_AENDERUNG_LABELS } from '../../lib/constants'

const kanalAbgleich = vi.fn()
const kanalAuswahl = vi.fn()
const planFn = vi.fn()
const executeFn = vi.fn()

vi.mock('../../api/repair', async (importOriginal) => {
  const echt = await importOriginal<typeof import('../../api/repair')>()
  return {
    ...echt,
    repairApi: {
      ...echt.repairApi,
      listPlans: vi.fn(() => Promise.resolve({ plans: [] })),
      kanalAbgleich: (...args: unknown[]) => kanalAbgleich(...args),
      kanalAuswahl: (...args: unknown[]) => kanalAuswahl(...args),
      plan: (...args: unknown[]) => planFn(...args),
      execute: (...args: unknown[]) => executeFn(...args),
    },
  }
})

import RepairWorkbench from './RepairWorkbench'
import { renderMitProvidern, stubMatchMedia } from '../../test/render'

const antwort = (over: Partial<KanalAbgleichErgebnis> = {}): KanalAbgleichErgebnis => ({
  anlage_id: 7, hat_spiegel: true, kanaele: 3, abschnitte: 3, gleich: 2,
  korrigiert: [{ key: 'basis:einspeisung', ab_ts: 1_760_000_000, zeilen: 12 }],
  gekuerzt: [], uebersprungen: {}, fehler: 0,
  meldung: '1 von 3 Abschnitt(en) wichen von der HA-Statistik ab und wurden ab der ersten Abweichung neu gespiegelt: basis:einspeisung ab 09.10.2025 10:00 (12 Stundenzeile(n)).',
  ...over,
})

function waehleAbgleich() {
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'kanal_abgleich_direkt' } })
}

describe('RepairWorkbench — HA-Spiegel jetzt abgleichen (#429)', () => {
  beforeEach(() => {
    kanalAbgleich.mockReset()
    stubMatchMedia()
  })

  it('bietet den Eintrag an, erklärt ihn in einem Satz und zeigt die Ergebniszeile', async () => {
    kanalAbgleich.mockResolvedValue(antwort())
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleAbgleich()
    expect(screen.getByText(/Nach einer Korrektur in Home Assistant/)).toBeInTheDocument()
    // Kein Plan-Knopf: direkter Pfad wie das Löschen.
    expect(screen.queryByRole('button', { name: /Plan erstellen/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /HA-Spiegel jetzt abgleichen/ }))
    await waitFor(() => expect(kanalAbgleich).toHaveBeenCalledWith(7))
    expect(await screen.findByText(/neu gespiegelt: basis:einspeisung/)).toBeInTheDocument()
  })

  it('ohne HA-Spiegel steht die Antwort des Backends da, kein Fehler', async () => {
    kanalAbgleich.mockResolvedValue(antwort({
      hat_spiegel: false, kanaele: 0, abschnitte: 0, gleich: 0, korrigiert: [],
      meldung: 'Für diese Anlage führt eedc keinen HA-Spiegel — ohne Zähler aus der Home-Assistant-Statistik gibt es nichts abzugleichen.',
    }))
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleAbgleich()
    fireEvent.click(screen.getByRole('button', { name: /HA-Spiegel jetzt abgleichen/ }))
    expect(await screen.findByText(/keinen HA-Spiegel/)).toBeInTheDocument()
  })

  it('HA nicht erreichbar: der Grund aus der 503-Antwort steht als Fehler da', async () => {
    kanalAbgleich.mockRejectedValue(new Error('Home Assistant ist nicht erreichbar — der Abgleich braucht die HA-Langzeitstatistik.'))
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleAbgleich()
    fireEvent.click(screen.getByRole('button', { name: /HA-Spiegel jetzt abgleichen/ }))
    expect(await screen.findByText(/nicht erreichbar/)).toBeInTheDocument()
  })
})


const auswahl = (): KanalAuswahlEintrag[] => [
  {
    key: 'inv:6:pv_erzeugung_kwh', label: 'Süddach · Erzeugung', investition_id: 6, typ: 'pv-module',
    quellen: [
      { gueltig_ab: '2025-01-01T00:00', familie: 'spiegel', statistic_id: 'sensor.pv_alt', verworfen_am: null },
      { gueltig_ab: '2026-04-21T00:00', familie: 'spiegel', statistic_id: 'sensor.pv_neu', verworfen_am: null },
    ],
    vorbelegung: '2026-04-21T00:00',
  },
  {
    key: 'basis:einspeisung', label: 'Anlage · Einspeisung', investition_id: null, typ: null,
    quellen: [
      { gueltig_ab: '2025-01-01T00:00', familie: 'spiegel', statistic_id: 'sensor.einsp_alt', verworfen_am: null },
      { gueltig_ab: '2026-05-03T14:00', familie: 'spiegel', statistic_id: 'sensor.einsp_neu', verworfen_am: null },
    ],
    vorbelegung: '2026-05-03T14:00',
  },
]

const planAntwort = (): PlanResponse => ({
  expires_in_seconds: 3600,
  plan: {
    plan_id: 'p1', anlage_id: 7, operation: 'verwerfen_vor_quellbeginn',
    operation_params: { kanal: 'basis:einspeisung', zeitpunkt: '2026-05-03T14:00' },
    created_at: '2026-10-15T10:00:00Z', expires_at: '2026-10-15T11:00:00Z',
    estimated_changes: { kanalzeilen: 1912, bestand_tage: 80, abschluss_monate: 2 },
    diff_preview: [], diff_total_count: 0,
    warnings: ['alter Sensor sensor.einsp_alt von 01.01.2025 00:00 bis 03.05.2026 14:00: 1.912 Stunden im Kanal.'],
    operation_preview: {},
  },
})

function waehleVerwerfen() {
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'verwerfen_vor_quellbeginn' } })
}

describe('RepairWorkbench — Werte vor dem Sensorbeginn verwerfen (E-S3-5)', () => {
  beforeEach(() => {
    kanalAuswahl.mockReset()
    planFn.mockReset()
    stubMatchMedia()
  })

  it('listet die Felder mit Sensortausch (Anlage zuerst), belegt den Zeitpunkt vor und schickt kanal + zeitpunkt', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahl() })
    planFn.mockResolvedValue(planAntwort())
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfen()
    await waitFor(() => expect(kanalAuswahl).toHaveBeenCalledWith(7, false))
    const feld = await screen.findByRole('combobox', { name: 'Feld' })
    const optionen = Array.from((feld as HTMLSelectElement).options).map((o) => o.textContent)
    expect(optionen).toEqual(['Feld mit Sensortausch wählen', 'Anlage · Einspeisung', 'Süddach · Erzeugung'])

    fireEvent.change(feld, { target: { value: 'basis:einspeisung' } })
    expect(screen.getByText('sensor.einsp_neu')).toBeInTheDocument()
    expect((screen.getByRole('combobox', { name: 'Uhrzeit' }) as HTMLSelectElement).value).toBe('14')

    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    await waitFor(() => expect(planFn).toHaveBeenCalled())
    expect(planFn.mock.calls[0][0]).toEqual({
      anlage_id: 7, operation: 'verwerfen_vor_quellbeginn',
      params: { kanal: 'basis:einspeisung', zeitpunkt: '2026-05-03T14:00' },
    })
    // Die Sätze der Vorschau kommen vom Backend — der Client rechnet nichts.
    expect(await screen.findByText(/1\.912 Stunden im Kanal/)).toBeInTheDocument()
  })

  it('ohne Feld kein Plan — die Werkbank sagt, was fehlt', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahl() })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfen()
    await screen.findByRole('combobox', { name: 'Feld' })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText(/Bitte ein Feld mit Sensortausch/)).toBeInTheDocument()
    expect(planFn).not.toHaveBeenCalled()
  })

  it('ohne Sensortausch steht der Grund da', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: [] })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfen()
    expect(await screen.findByText(/Kein Feld dieser Anlage hat einen Sensortausch/)).toBeInTheDocument()
  })
})


const auswahlAlle = (): KanalAuswahlEintrag[] => [
  {
    key: 'inv:1:km_gefahren', label: 'Smart #1 · Gefahrene km', investition_id: 1, typ: 'e-auto',
    quellen: [{ gueltig_ab: '2024-11-01T00:00', familie: 'spiegel', statistic_id: 'sensor.smart_km', verworfen_am: null }],
    vorbelegung: '2024-11-01T00:00',
  },
  {
    key: 'basis:einspeisung', label: 'Anlage · Einspeisung', investition_id: null, typ: null,
    quellen: [{ gueltig_ab: '2024-11-01T00:00', familie: 'spiegel', statistic_id: 'sensor.einsp', verworfen_am: null }],
    vorbelegung: '2024-11-01T00:00',
  },
]

// Wortlaute der Vorschau wörtlich aus der Messung an der Produktiv-Kopie (`services/verwerfen_vor_zeitpunkt.klartext`,
// `golden-master/funde-h-2026-11-23/aus/t2-prod-km.json`, Teil 3: `teil3/op-km-0600-h1.json`) — vom Backend, der Client zeigt sie nur.
const SAETZE_ZEIT = [
  'Verworfen werden die Werte von «Smart #1 · Gefahrene km» (inv:1:km_gefahren) vor 10.05.2025 06:00. Danach verhält sich das Feld, als wäre seine Quelle erst ab diesem Zeitpunkt zugeordnet.',
  'Gelöscht werden nur Daten dieses Felds vor dem Zeitpunkt: 2.536 Stundenzeilen des Kanals (31.10.2024 … 17.02.2025); 2.536 Zählerstände.',
  'Den Tag des Zeitpunkts (10.05.2025) bildet eedc für alle Felder neu — aus der Statistik von Home Assistant bzw. den gespeicherten Zählerständen; Werte anderer Felder können sich an diesem Tag ändern.',
  'Gespeichert bleiben: Wetter, Börsen- und Kraftstoffpreise, Prognosen und die gespeicherten Monatswerte. An den übrigen neu gebildeten Tagen ändert der Neu-Aufbau an den anderen Feldern nur, was dort auch «Tag neu aggregieren» ändern würde.',
  'Für 10/2024 bis 05/2025 sind Monatswerte gespeichert. Sie bleiben, wie sie sind.',
  'Soll ein Monat zu den verbliebenen Werten passen, ändere ihn unter Einstellungen → «Daten» → «Monatsdaten» von Hand.',
  'Home Assistant behält seine Statistik. eedc holt die Zeit vor dem Zeitpunkt für dieses Feld nicht wieder — auch nicht mit «Aus Home Assistant neu übernehmen» oder «Tag neu aggregieren».',
  'Danach bildet eedc die betroffenen Tage im Hintergrund neu.',
  'Das lässt sich nicht rückgängig machen.',
]

const planAntwortZeit = (): PlanResponse => ({
  expires_in_seconds: 3600,
  plan: {
    plan_id: 'p2', anlage_id: 7, operation: 'verwerfen_vor_zeitpunkt',
    operation_params: { kanal: 'inv:1:km_gefahren', zeitpunkt: '2025-05-10T06:00' },
    created_at: '2026-11-23T10:00:00Z', expires_at: '2026-11-23T11:00:00Z',
    estimated_changes: { kanalzeilen: 2536, zaehlerstaende: 2536, mqtt_rohwerte: 0, tage_mit_werten: 110, monate_gespeichert: 8 },
    diff_preview: [], diff_total_count: 0,
    warnings: SAETZE_ZEIT,
    operation_preview: {},
  },
})

function waehleVerwerfenZeit() {
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'verwerfen_vor_zeitpunkt' } })
}

describe('RepairWorkbench — Werte eines Felds vor einem Zeitpunkt verwerfen (Fund-Päckchen H, H1)', () => {
  beforeEach(() => {
    kanalAuswahl.mockReset()
    planFn.mockReset()
    stubMatchMedia()
  })

  it('steht in der Werkbank, listet alle Felder (alle=true) und schickt kanal + zeitpunkt', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahlAlle() })
    planFn.mockResolvedValue(planAntwortZeit())
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    const opOptionen = Array.from((screen.getAllByRole('combobox')[0] as HTMLSelectElement).options).map((o) => o.textContent)
    expect(opOptionen).toContain('Werte eines Felds vor einem Zeitpunkt verwerfen')
    waehleVerwerfenZeit()
    await waitFor(() => expect(kanalAuswahl).toHaveBeenCalledWith(7, true))
    const feld = await screen.findByRole('combobox', { name: 'Feld' })
    const optionen = Array.from((feld as HTMLSelectElement).options).map((o) => o.textContent)
    expect(optionen).toEqual(['Feld wählen', 'Anlage · Einspeisung', 'Smart #1 · Gefahrene km'])

    fireEvent.change(feld, { target: { value: 'inv:1:km_gefahren' } })
    expect(screen.getByText('sensor.smart_km')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Uhrzeit' }), { target: { value: '06' } })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    await waitFor(() => expect(planFn).toHaveBeenCalled())
    expect(planFn.mock.calls[0][0]).toEqual({
      anlage_id: 7, operation: 'verwerfen_vor_zeitpunkt',
      params: { kanal: 'inv:1:km_gefahren', zeitpunkt: '2024-11-01T06:00' },
    })
    for (const satz of SAETZE_ZEIT) expect(await screen.findByText(satz)).toBeInTheDocument()
    // Der Knopf, den der Lösungsweg nennt (kein Diff ⇒ «Operation ausführen»).
    expect(screen.getByRole('button', { name: /Operation ausführen/ })).toBeInTheDocument()
  })

  it('eine geteilte Quelle: der Vermerk sagt, dass die Werte dieser Quelle verworfen sind', async () => {
    const geteilt: KanalAuswahlEintrag = {
      ...auswahlAlle()[0],
      quellen: [
        { gueltig_ab: '2024-11-01T00:00', familie: 'spiegel', statistic_id: 'sensor.smart_km', verworfen_am: '2026-11-23T10:00' },
        { gueltig_ab: '2025-05-10T06:00', familie: 'spiegel', statistic_id: 'sensor.smart_km', verworfen_am: null },
      ],
      vorbelegung: '2025-05-10T06:00',
    }
    kanalAuswahl.mockResolvedValue({ kanaele: [geteilt] })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfenZeit()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Feld' }), { target: { value: 'inv:1:km_gefahren' } })
    expect(screen.getByText(/Werte dieser Quelle verworfen am/)).toBeInTheDocument()
    expect(screen.queryByText(/Werte davor verworfen/)).toBeNull()
  })

  it('ohne Feld kein Plan', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahlAlle() })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfenZeit()
    await screen.findByRole('combobox', { name: 'Feld' })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText('Bitte ein Feld und den Zeitpunkt wählen.')).toBeInTheDocument()
    expect(planFn).not.toHaveBeenCalled()
  })

  it('ein Zeitpunkt in der Zukunft geht nicht zum Backend', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: [{ ...auswahlAlle()[0], vorbelegung: '2099-01-01T05:00' }] })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfenZeit()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Feld' }), { target: { value: 'inv:1:km_gefahren' } })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText(/Der Zeitpunkt liegt in der Zukunft/)).toBeInTheDocument()
    expect(planFn).not.toHaveBeenCalled()
  })

  it('eine nicht freigegebene Lage: der Satz des Backends steht als Fehler da', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahlAlle() })
    planFn.mockRejectedValue(new Error('Für dieses Feld ist das Verwerfen hier nicht möglich: an 1 Tag (01.11.2024) schriebe jeder Neu-Aufbau des Tages den Wert dieses Felds wieder aus der Statistik von Home Assistant.'))
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfenZeit()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Feld' }), { target: { value: 'basis:einspeisung' } })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText(/das Verwerfen hier nicht möglich/)).toBeInTheDocument()
  })
})


// Regel 0 (`lib/constants.ts::REPARATUR_AENDERUNG_LABELS`): kein roher Schlüssel in Vorschau, Ergebnis und Verlauf. Die Schlüssel
// sind die der Messung an der Produktiv-Kopie (`verwerfen_vor_zeitpunkt.geschaetzt` bzw. die Ganzzahlen von `fuehre_aus`,
// `repair_protokoll.mengen`; `golden-master/funde-h-2026-11-23/aus/t2-prod-km.json`).
const ERGEBNIS_ZEIT: Record<string, number> = {
  kanalzeilen_geloescht: 2536, quellen_markiert: 1, quelle_geteilt: 1, zaehlerstaende_geloescht: 2536,
  mqtt_rohwerte_geloescht: 0, wechsel_geloescht: 0, abgeleitet_verworfen: 0, stundenzeilen_geleert: 0,
  tageszeilen_geleert: 0, felder_geleert: 0, tage_neu: 1,
}

describe('RepairWorkbench — Chips von „Werte eines Felds vor einem Zeitpunkt verwerfen" (Regel 0)', () => {
  beforeEach(() => {
    kanalAuswahl.mockReset()
    planFn.mockReset()
    executeFn.mockReset()
    stubMatchMedia()
  })

  it('jeder Schlüssel der Vorschau und des Ergebnisses hat eine Bezeichnung', () => {
    const schluessel = [...Object.keys(planAntwortZeit().plan.estimated_changes), ...Object.keys(ERGEBNIS_ZEIT)]
    expect(schluessel.filter((k) => !(k in REPARATUR_AENDERUNG_LABELS))).toEqual([])
  })

  it('Vorschau und Ergebnis zeigen die Bezeichnungen, keinen rohen Schlüssel', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahlAlle() })
    planFn.mockResolvedValue(planAntwortZeit())
    executeFn.mockResolvedValue({
      plan_id: 'p2', anlage_id: 7, operation: 'verwerfen_vor_zeitpunkt', executed_at: '2026-11-23T10:05:00Z',
      actual_changes: ERGEBNIS_ZEIT, audit_log_ids: [], operation_summary: {},
    })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfenZeit()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Feld' }), { target: { value: 'inv:1:km_gefahren' } })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText('Zählerstände vor dem Zeitpunkt')).toBeInTheDocument()
    expect(screen.getByText('Monate mit gespeichertem Monatswert (bleiben)')).toBeInTheDocument()
    for (const k of Object.keys(planAntwortZeit().plan.estimated_changes)) expect(screen.queryByText(k)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Operation ausführen/ }))
    const banner = await screen.findByText(/Werte eines Felds vor einem Zeitpunkt verwerfen ausgeführt:/)
    expect(banner.textContent).toContain('2536 Zählerstände gelöscht')
    expect(banner.textContent).toContain('1 Quelle geteilt')
    expect(banner.textContent).toContain('1 Tag wird neu gebildet')
    expect(banner.textContent).toContain('0 Audit-Log-Einträge')
    for (const k of Object.keys(ERGEBNIS_ZEIT)) expect(banner.textContent).not.toContain(k)
  })

  // Lab-Probe rc49 (24.11.2026): «1 Zählerstände vor dem Zeitpunkt», «1 Quellen markiert», «1 Tage werden neu gebildet»,
  // «0 Audit-Log-Eintrage». Beim Zähler 1 steht die Einzahl, sonst die Mehrzahl.
  it('Einzahl beim Zähler 1, Mehrzahl sonst — in Vorschau und Banner', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahlAlle() })
    const antwort = planAntwortZeit()
    antwort.plan.estimated_changes = { kanalzeilen: 2, zaehlerstaende: 1, mqtt_rohwerte: 18, tage_mit_werten: 1,
      monate_gespeichert: 1 }
    planFn.mockResolvedValue(antwort)
    executeFn.mockResolvedValue({
      plan_id: 'p3', anlage_id: 7, operation: 'verwerfen_vor_zeitpunkt', executed_at: '2026-11-24T03:55:00Z',
      actual_changes: { ...ERGEBNIS_ZEIT, kanalzeilen_geloescht: 2, zaehlerstaende_geloescht: 1, mqtt_rohwerte_geloescht: 18 },
      audit_log_ids: [5], operation_summary: {},
    })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfenZeit()
    fireEvent.change(await screen.findByRole('combobox', { name: 'Feld' }), { target: { value: 'inv:1:km_gefahren' } })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText('Zählerstand vor dem Zeitpunkt')).toBeInTheDocument()
    expect(screen.getByText('Kanalzeilen vor dem Zeitpunkt')).toBeInTheDocument()
    expect(screen.getByText('Tag mit Werten des Feldes')).toBeInTheDocument()
    expect(screen.getByText('Monat mit gespeichertem Monatswert (bleibt)')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Operation ausführen/ }))
    const banner = await screen.findByText(/Werte eines Felds vor einem Zeitpunkt verwerfen ausgeführt:/)
    for (const teil of ['2 Kanalzeilen gelöscht', '1 Quelle markiert', '1 Quelle geteilt', '1 Zählerstand gelöscht',
      '18 MQTT-Rohwerte gelöscht', '0 Sensorwechsel aufgehoben', '0 abgeleitete Stundenwerte neu zu bilden',
      '0 Stundenzeilen geleert', '0 Tageszeilen geleert', '0 Werte geleert', '1 Tag wird neu gebildet',
      '1 Audit-Log-Eintrag.']) {
      expect(banner.textContent).toContain(teil)
    }
    expect(banner.textContent).not.toMatch(/\b1 (Zählerstände|Quellen|Tage)\b|Eintrage/)
  })
})
