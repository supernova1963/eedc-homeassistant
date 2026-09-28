/**
 * **N-578 — der WP-Gesamtstrom friert nicht mehr ein (#416, Rainer).**
 *
 * Die Kette aus dem Herkunftsbericht (`opus-berichte/N578-HERKUNFT.md`, Proben
 * F1–F6): Der Monatsabschluss-Status führt `stromverbrauch_kwh` bei getrennter
 * Messung **weich** (belegt ⇒ geführt, cf3b0a16), das Formular blendete es **hart**
 * aus. Die Status-Vorbelegung legte den Summen-Vorschlag trotzdem in den
 * unsichtbaren Formularschlüssel; die Auto-Summe beim Speichern fragt genau
 * diesen Schlüssel (`!hasValue`) und fiel aus, gesendet wurde er nie — der
 * gespeicherte Gesamtwert blieb auf dem Stand des ersten Speicherns stehen.
 *
 * Die Bausteine, die diese Datei festhält:
 *   **B1** — vorbelegt wird nur, was das Formular für das Gerät zeichnet;
 *   **B2a** — die Auto-Summe trägt `summe_achsen` (#352-Kanal), und ein so
 *     markierter Wert wird beim Laden NICHT als Handpflege übernommen
 *     (die Laderoute liefert `abgeleitet_felder` je Zeile);
 *   **B2b** — ein gepflegter (unmarkierter) Gesamtwert oder ein zugeordneter
 *     Gesamt-Sensor macht das Feld sichtbar; Leeren = eedc rechnet wieder;
 *   **H2 (Master-Entscheid)** — mit Gesamt-Sensor unterbleibt die Auto-Summe,
 *     und der Summen-Vorschlag `berechnung` wird nicht vorbelegt.
 *
 * Die Nutzlast ist das Argument von `onSubmit` — das, was `POST/PUT
 * /monatsdaten` bekommt und je Sub-Key in die Zeile mergt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor, screen } from '@testing-library/react'
import type { Investition } from '../types'
import type { FeldStatus, MonatsabschlussResponse, Vorschlag } from '../api/monatsabschluss'
import type { MonatsdatenSubmitData } from '../components/forms/MonatsdatenForm'
import { ABGELEITET_SUMME_ACHSEN } from '../lib/fieldDefinitions'

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

const WP_ID = 7
const GESAMT = `inv-${WP_ID}-stromverbrauch_kwh`
const MARKE = { stromverbrauch_kwh: ABGELEITET_SUMME_ACHSEN }

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

const waermepumpe: Investition = {
  id: WP_ID, anlage_id: 1, typ: 'waermepumpe', bezeichnung: 'Geraet', anschaffungsdatum: '2024-01-01', aktiv: true,
  parameter: { wp_art: 'luft_wasser', getrennte_strommessung: true },
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
    // Ohne Status gibt es keine Ampel — dann auf die geladene Achse warten.
    await waitFor(() => expect(eingabe(`inv-${WP_ID}-strom_heizen_kwh`)).not.toBeNull())
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
  // Gegenprobe gegen eine blinde Abwesenheit: die Achse des Geräts ist sichtbar.
  if (zustand.invs[0]?.typ === 'waermepumpe' && zustand.invs[0].parameter?.getrennte_strommessung) {
    expect(eingabe(`inv-${WP_ID}-strom_heizen_kwh`)).not.toBeNull()
  }
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

const ACHSEN_H1_WW31 = { strom_heizen_kwh: 1, strom_warmwasser_kwh: 31, heizenergie_kwh: 10, warmwasser_kwh: 100 }

/** Der Status für einen gespeicherten Monat mit Gesamtwert (P1 der Herkunft). */
function wpStatus(gesamt: { wert?: number | null; vorschlaege?: Array<Partial<Vorschlag>>; sensor?: string }, h: number | null, ww: number) {
  return statusMit('waermepumpe', [
    feld('stromverbrauch_kwh', gesamt),
    feld('strom_heizen_kwh', { wert: h }),
    feld('strom_warmwasser_kwh', { wert: ww }),
    feld('heizenergie_kwh', { wert: 10 }),
    feld('warmwasser_kwh', { wert: 100 }),
  ])
}
const SUMMEN_VORSCHLAG = { quelle: 'berechnung' as const, wert: 32, konfidenz: 95 }

beforeEach(() => { zustand.invs = [waermepumpe] })

describe('N-578 B2a — ein markierter Gesamtwert ist keine Handpflege: die Auto-Summe rechnet bei jedem Speichern', () => {
  it('F1 Folgespeicherung: markierte 20 werden nicht geladen, das Feld bleibt verborgen, gesendet wird 32 mit Marke', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ...ACHSEN_H1_WW31, stromverbrauch_kwh: 20 }, abgeleitet_felder: MARKE }]
    zustand.status = wpStatus({ wert: 20, vorschlaege: [SUMMEN_VORSCHLAG] }, 1, 31)
    const wp = await speichere({ bearbeiten: true, pruefe: () => expect(eingabe(GESAMT)).toBeNull() })
    expect(wp.stromverbrauch_kwh).toBe(32)
    expect(wp.abgeleitet_felder).toEqual(MARKE)
  })

  it('F2 Rainers Fall: Warmwasser 31 → 40 getippt ⇒ Gesamt 41, nicht der Stand des ersten Speicherns', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ...ACHSEN_H1_WW31, stromverbrauch_kwh: 20 }, abgeleitet_felder: MARKE }]
    zustand.status = wpStatus({ wert: 20, vorschlaege: [SUMMEN_VORSCHLAG] }, 1, 31)
    const wp = await speichere({ bearbeiten: true, tippe: { strom_warmwasser_kwh: '40' } })
    expect(wp.strom_warmwasser_kwh).toBe(40)
    expect(wp.stromverbrauch_kwh).toBe(41)
    expect(wp.abgeleitet_felder).toEqual(MARKE)
  })

  it('F6 nur ein Vormonats-Vorschlag (150) am verborgenen Feld: er landet nirgends, die Summe gilt', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { strom_warmwasser_kwh: 31, heizenergie_kwh: 10, warmwasser_kwh: 100, stromverbrauch_kwh: 20 }, abgeleitet_felder: MARKE }]
    zustand.status = wpStatus({ wert: 20, vorschlaege: [{ quelle: 'vormonat', wert: 150, konfidenz: 80 }] }, null, 31)
    const wp = await speichere({ bearbeiten: true })
    expect(wp.stromverbrauch_kwh).toBe(31)
    expect(wp.abgeleitet_felder).toEqual(MARKE)
  })

  it('F5 ohne Status: die Marke kommt mit der Laderoute — die Summe läuft trotzdem', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ...ACHSEN_H1_WW31, stromverbrauch_kwh: 20 }, abgeleitet_felder: MARKE }]
    zustand.status = null
    const wp = await speichere({ bearbeiten: true, pruefe: () => expect(eingabe(GESAMT)).toBeNull() })
    expect(wp.stromverbrauch_kwh).toBe(32)
    expect(wp.abgeleitet_felder).toEqual(MARKE)
  })

  it('F3 Erstspeicherung (Status führt das Feld nicht): die Summe trägt die Marke', async () => {
    zustand.rows = []
    zustand.status = statusMit('waermepumpe', [
      feld('strom_heizen_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 1, konfidenz: 92 }] }),
      feld('strom_warmwasser_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 10, konfidenz: 92 }] }),
    ])
    const wp = await speichere({ bearbeiten: false })
    expect(wp.strom_heizen_kwh).toBe(1)
    expect(wp.stromverbrauch_kwh).toBe(11)
    expect(wp.abgeleitet_felder).toEqual(MARKE)
  })
})

describe('N-578 B2b — ein gepflegter Gesamtwert steht sichtbar im Formular, Leeren gibt die Rechnung zurück', () => {
  it('unmarkierter Wert (Altbestand = handgepflegt) erscheint sichtbar mit Wert und Hinweis — und bleibt, wie er ist', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ...ACHSEN_H1_WW31, stromverbrauch_kwh: 50 } }]
    zustand.status = wpStatus({ wert: 50, vorschlaege: [SUMMEN_VORSCHLAG] }, 1, 31)
    const wp = await speichere({
      bearbeiten: true,
      pruefe: () => {
        expect(eingabe(GESAMT)?.value).toBe('50')
        expect(document.body.textContent).toContain('Leer lassen: eedc rechnet Strom Heizen + Strom Warmwasser')
      },
    })
    expect(wp.stromverbrauch_kwh).toBe(50)
    expect(wp.abgeleitet_felder).toBeUndefined()
  })

  it('auch ohne Status: der unmarkierte Wert ist sichtbar (die Entscheidung fällt beim Laden)', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ...ACHSEN_H1_WW31, stromverbrauch_kwh: 50 } }]
    zustand.status = null
    const wp = await speichere({ bearbeiten: true, pruefe: () => expect(eingabe(GESAMT)?.value).toBe('50') })
    expect(wp.stromverbrauch_kwh).toBe(50)
  })

  it('Leeren + Speichern = Reparatur: aus der gepflegten 50 wird wieder die Summe 32 mit Marke', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ...ACHSEN_H1_WW31, stromverbrauch_kwh: 50 } }]
    zustand.status = wpStatus({ wert: 50, vorschlaege: [SUMMEN_VORSCHLAG] }, 1, 31)
    const wp = await speichere({ bearbeiten: true, tippe: { stromverbrauch_kwh: '' } })
    expect(wp.stromverbrauch_kwh).toBe(32)
    expect(wp.abgeleitet_felder).toEqual(MARKE)
  })
})

describe('N-578 H2 — mit zugeordnetem Gesamt-Sensor misst der Sensor, nicht die Summe', () => {
  it('Sensor zugeordnet, HA-Vorschlag 45: Feld sichtbar und vorbelegt, gesendet wird 45 — keine Summe, keine Marke', async () => {
    zustand.rows = []
    zustand.status = statusMit('waermepumpe', [
      feld('stromverbrauch_kwh', { sensor: 'sensor.wp_gesamt', vorschlaege: [{ quelle: 'ha_statistics', wert: 45, konfidenz: 92 }] }),
      feld('strom_heizen_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 10, konfidenz: 92 }] }),
      feld('strom_warmwasser_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 20, konfidenz: 92 }] }),
    ])
    const wp = await speichere({ bearbeiten: false, pruefe: () => expect(eingabe(GESAMT)?.value).toBe('45') })
    expect(wp.stromverbrauch_kwh).toBe(45)
    expect(wp.abgeleitet_felder).toBeUndefined()
  })

  it('Sensor zugeordnet, noch kein Messwert (laufender Monat): die Auto-Summe unterbleibt — nichts gesendet', async () => {
    zustand.rows = []
    zustand.status = statusMit('waermepumpe', [
      feld('stromverbrauch_kwh', { sensor: 'sensor.wp_gesamt' }),
      feld('strom_heizen_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 10, konfidenz: 92 }] }),
      feld('strom_warmwasser_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 20, konfidenz: 92 }] }),
    ])
    const wp = await speichere({ bearbeiten: false, pruefe: () => expect(eingabe(GESAMT)?.value).toBe('') })
    expect(wp.strom_heizen_kwh).toBe(10)
    expect('stromverbrauch_kwh' in wp).toBe(false)
    expect(wp.abgeleitet_felder).toBeUndefined()
  })

  it('der Summen-Vorschlag `berechnung` (95) wird übersprungen — vorbelegt wird der Messwert (92)', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: ACHSEN_H1_WW31 }]
    zustand.status = wpStatus({ sensor: 'sensor.wp_gesamt', vorschlaege: [SUMMEN_VORSCHLAG, { quelle: 'ha_statistics', wert: 45, konfidenz: 92 }] }, 1, 31)
    const wp = await speichere({ bearbeiten: true, pruefe: () => expect(eingabe(GESAMT)?.value).toBe('45') })
    expect(wp.stromverbrauch_kwh).toBe(45)
  })

  it('… und ist er der einzige Vorschlag, bleibt das Feld leer (kein unmarkierter Summenwert)', async () => {
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: ACHSEN_H1_WW31 }]
    zustand.status = wpStatus({ sensor: 'sensor.wp_gesamt', vorschlaege: [SUMMEN_VORSCHLAG] }, 1, 31)
    const wp = await speichere({ bearbeiten: true, pruefe: () => expect(eingabe(GESAMT)?.value).toBe('') })
    expect('stromverbrauch_kwh' in wp).toBe(false)
  })
})

describe('N-578 — Gegenrichtungen', () => {
  it('ohne getrennte Messung ist der Gesamtwert das Eingabefeld — auch eine alte Summe wird geladen, keine neue Summe, keine Marke', async () => {
    // Die Marke stammt aus der Zeit mit getrennter Messung; nach dem Ausschalten
    // ist der Wert die Menge, mit der eedc rechnet — er gehört ins Feld.
    zustand.invs = [{ ...waermepumpe, parameter: { wp_art: 'luft_wasser' } }]
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { stromverbrauch_kwh: 20, heizenergie_kwh: 10, warmwasser_kwh: 100 }, abgeleitet_felder: MARKE }]
    zustand.status = statusMit('waermepumpe', [
      feld('stromverbrauch_kwh', { wert: 20, vorschlaege: [{ quelle: 'vormonat', wert: 30, konfidenz: 80 }] }),
      feld('heizenergie_kwh', { wert: 10 }), feld('warmwasser_kwh', { wert: 100 }),
    ])
    const wp = await speichere({ bearbeiten: true })
    expect(wp.stromverbrauch_kwh).toBe(20)
    expect(wp.abgeleitet_felder).toBeUndefined()
  })

  it('B1 generisch: am Speicher füllt der Vorschlag das sichtbare Feld „Netzladung" wie bisher', async () => {
    zustand.invs = [{ id: WP_ID, anlage_id: 1, typ: 'speicher', bezeichnung: 'Geraet', anschaffungsdatum: '2024-01-01', aktiv: true, parameter: { laedt_aus_netz: true } }]
    zustand.rows = [{ investition_id: WP_ID, verbrauch_daten: { ladung_kwh: 100, entladung_kwh: 90 } }]
    zustand.status = statusMit('speicher', [
      feld('ladung_kwh', { wert: 100 }), feld('entladung_kwh', { wert: 90 }),
      feld('ladung_netz_kwh', { vorschlaege: [{ quelle: 'ha_statistics', wert: 12, konfidenz: 92 }] }),
    ])
    const sp = await speichere({ bearbeiten: true })
    expect(sp).toMatchObject({ ladung_kwh: 100, entladung_kwh: 90, ladung_netz_kwh: 12 })
  })
})
