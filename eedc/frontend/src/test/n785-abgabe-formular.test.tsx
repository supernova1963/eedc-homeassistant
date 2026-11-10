/**
 * **#443 / N-785 — das Monatsabschluss-Formular kennt die Kategorie «Abgabe an Dritte».**
 *
 * Bis 4.2.2 fehlte `SONSTIGES_FELDER.abgabe` im Client: `getFelderFuerSonstiges('abgabe')` lieferte die Liste für
 * ungepflegte Geräte, der Backend-Status filterte sie auf `einspeise_erloes_euro` (Label «Einspeise-Erlös» der
 * Erzeuger-Liste), und der Sensor-Vorschlag zu `abgabe_kwh` wurde verworfen (N-578 B1: ein Vorschlag zu einem nicht
 * gezeichneten Feld wird verworfen) — wer über das Formular abschloss, speicherte die Abgabe nicht.
 *
 * Gerüst (Mocks, `speichere`) aus `n578-wp-gesamtwert.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor, screen } from '@testing-library/react'
import type { Investition } from '../types'
import type { FeldStatus, MonatsabschlussResponse, Vorschlag } from '../api/monatsabschluss'
import type { MonatsdatenSubmitData } from '../components/forms/MonatsdatenForm'

interface Zeile {
  investition_id: number
  verbrauch_daten: Record<string, number>
  abgeleitet_felder?: Record<string, string>
}

const zustand: {
  invs: Investition[]
  /** `null` = der Status-Abruf scheitert (Herkunft F5). */
  status: MonatsabschlussResponse | null
  rows: Zeile[]
} = { invs: [], status: null, rows: [] }

vi.mock('../hooks', () => ({
  useInvestitionen: () => ({ investitionen: zustand.invs, loading: false }),
  useAktuellerStrompreis: () => ({ strompreis: null }),
}))
vi.mock('../api', () => ({
  wetterApi: { getMonatsdaten: () => Promise.reject(new Error('kein Wetter im Test')) },
  monatsabschlussApi: {
    getStatus: () => (zustand.status ? Promise.resolve(zustand.status) : Promise.reject(new Error('Status aus'))),
  },
  investitionenApi: {
    getMonatsdatenByMonth: () => Promise.resolve(zustand.rows.map((r, i) => ({
      id: i + 1, jahr: 2026, monat: 9, einsparung_monat_euro: null, co2_einsparung_kg: null, ...r,
    }))),
  },
}))

const MonatsdatenForm = (await import('../components/forms/MonatsdatenForm')).default

const WP_ID = 12

function feld(
  name: string,
  opt: { vorschlaege?: Array<Partial<Vorschlag>>; wert?: number | null; sensor?: string } = {},
): FeldStatus {
  return {
    feld: name, label: name, einheit: 'kWh', aktueller_wert: opt.wert ?? null, aktueller_text: null,
    quelle: opt.wert != null ? 'manuell' : null,
    vorschlaege: (opt.vorschlaege ?? []).map(v => ({ beschreibung: 'Probe', konfidenz: 50, quelle: 'vormonat', wert: 0, ...v }) as Vorschlag),
    warnungen: [],
    strategie: opt.sensor ? 'sensor' : null,
    sensor_id: opt.sensor ?? null,
    typ: 'number', gruppe: null,
  }
}

function statusMit(typ: string, felder: FeldStatus[]): MonatsabschlussResponse {
  return {
    anlage_id: 1, anlage_name: 'Probe', jahr: 2026, monat: 9, ist_abgeschlossen: false,
    ha_mapping_konfiguriert: false, connector_konfiguriert: false, cloud_import_konfiguriert: false,
    mqtt_inbound_konfiguriert: false, portal_import_vorhanden: false, datenquelle: null,
    // Beim Neuanlegen belegt der Status die Pflichtzähler vor (sonst sperrt V2 das Speichern).
    basis_felder: [
      feld('einspeisung_kwh', { wert: 300, vorschlaege: [{ quelle: 'vormonat', wert: 300, konfidenz: 80 }] }),
      feld('netzbezug_kwh', { wert: 200, vorschlaege: [{ quelle: 'vormonat', wert: 200, konfidenz: 80 }] }),
    ],
    optionale_felder: [],
    investitionen: [{ id: WP_ID, typ, bezeichnung: 'Geraet', felder, sonstige_positionen: [] }],
  } as MonatsabschlussResponse
}

const eingabe = (name: string) => document.querySelector(`input[name="${name}"]`) as HTMLInputElement | null

/** Formular öffnen, warten bis Status + Gerätedaten da sind, optional tippen, speichern. */
async function speichere(opt: {
  bearbeiten: boolean
  tippe?: Record<string, string>
  /** Wird nach dem Laden (vor dem Tippen) mit dem geöffneten Formular gerufen. */
  pruefe?: () => void
}) {
  const onSubmit = vi.fn((_d: MonatsdatenSubmitData) => Promise.resolve())
  render(
    <MonatsdatenForm
      anlageId={1} onSubmit={onSubmit} onCancel={() => {}}
      monatsdaten={opt.bearbeiten ? ({ id: 1, anlage_id: 1, jahr: 2026, monat: 9, einspeisung_kwh: 300, netzbezug_kwh: 200 } as never) : null}
      voreingestellterMonat={{ jahr: 2026, monat: 9 }}
    />,
  )
  if (zustand.status) {
    // Status geladen = Kopf-Ampel steht; die Vorbelegung läuft im selben Durchgang.
    await waitFor(() => expect(document.body.textContent).toMatch(/\d+ fertig/))
  } else {
    // Ohne Status gibt es keine Ampel — dann auf das geladene Gerät warten (die Sektion kann noch zu sein).
    await waitFor(() => expect(screen.queryAllByRole('button', { expanded: false }).length + document.querySelectorAll('input[name^="inv-"]').length).toBeGreaterThan(0))
  }
  // Eingeklappte Sektionen (grün) öffnen, damit alle Eingaben im DOM sind —
  // verschachtelt (Typ → Gerät), also bis keine mehr zu ist. Sonst wäre ein
  // „Feld ist nicht da" auch dann wahr, wenn es nur eingeklappt ist.
  for (let runde = 0; runde < 5; runde++) {
    const zu = screen.queryAllByRole('button', { expanded: false })
    if (zu.length === 0) break
    zu.forEach(knopf => fireEvent.click(knopf))
  }
  expect(screen.queryAllByRole('button', { expanded: false })).toHaveLength(0)
  opt.pruefe?.()
  for (const [name, wert] of Object.entries(opt.tippe ?? {})) {
    const input = await waitFor(() => {
      const el = eingabe(`inv-${WP_ID}-${name}`)
      expect(el).not.toBeNull()
      return el!
    })
    fireEvent.change(input, { target: { value: wert } })
  }
  fireEvent.submit(document.querySelector('form')!)
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  const nutzlast = onSubmit.mock.calls[0][0]
  return (nutzlast.investitionen_daten?.[String(WP_ID)] ?? {}) as Record<string, unknown>
}

const abgabeGeraet: Investition = {
  id: WP_ID, anlage_id: 1, typ: 'sonstiges', bezeichnung: 'Mieterstrom', anschaffungsdatum: '2024-01-01', aktiv: true,
  parameter: { kategorie: 'abgabe' },
}

beforeEach(() => {
  zustand.invs = [abgabeGeraet]
  // Feste Uhr (Wächter «feste Uhr in Proben»): der Monat 9/2026 und die Anschaffung 2024 sollen nicht auf heute wetten.
  vi.setSystemTime(new Date(2026, 9, 15, 12, 0))
})
afterEach(() => { vi.useRealTimers() })

describe('#443 — Abgabe-Gerät im Monatsabschluss', () => {
  it('Sensor an `abgabe_kwh`: das Feld «Abgabe» ist gezeichnet, vorbelegt und wird gesendet', async () => {
    zustand.rows = []
    zustand.status = statusMit('sonstiges', [
      feld('abgabe_kwh', { sensor: 'sensor.mieterstrom', vorschlaege: [{ quelle: 'ha_statistics', wert: 210, konfidenz: 92 }] }),
      feld('einspeise_erloes_euro'),
    ])
    const g = await speichere({
      bearbeiten: false,
      pruefe: () => {
        expect(eingabe(`inv-${WP_ID}-abgabe_kwh`)?.value).toBe('210')
        expect(eingabe(`inv-${WP_ID}-einspeise_erloes_euro`)).not.toBeNull()
      },
    })
    expect(g.abgabe_kwh).toBe(210)
  })

  it('beide Felder mit den Labels der Registry: «Abgabe» und «Erlös» (nicht «Einspeise-Erlös»)', async () => {
    zustand.rows = []
    zustand.status = statusMit('sonstiges', [feld('abgabe_kwh'), feld('einspeise_erloes_euro')])
    await speichere({
      bearbeiten: false,
      tippe: { abgabe_kwh: '190', einspeise_erloes_euro: '12.5' },
      pruefe: () => {
        expect(document.body.textContent).not.toContain('Einspeise-Erlös')
        expect(document.body.textContent).toContain('Erlös')
      },
    })
  })

  it('ohne Status (Fallback auf die Client-Liste): beide Felder gezeichnet, getippte Werte gesendet', async () => {
    zustand.rows = []
    zustand.status = null
    // Bearbeiten: ohne Status belegt niemand die Pflichtzähler vor, der bestehende Monat trägt sie.
    const g = await speichere({ bearbeiten: true, tippe: { abgabe_kwh: '190', einspeise_erloes_euro: '12.5' } })
    expect(g).toMatchObject({ abgabe_kwh: 190, einspeise_erloes_euro: 12.5 })
  })
})
