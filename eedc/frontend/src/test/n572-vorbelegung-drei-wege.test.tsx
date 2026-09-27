/**
 * **N-572 — Das Formular schreibt keinen Default mehr als gepflegten Wert.**
 *
 * Drei Parameter werden von ihren Lesern nach ihrer **Anwesenheit** ausgewertet:
 * „leer" bedeutet dort etwas anderes als der Release-Default. Solange das
 * Formular sie vorbelegte (`paramStr(val, DEFAULT)` behandelt `''` wie fehlend),
 * machte jedes Anlegen und jedes Bearbeiten+Speichern aus „nicht gepflegt" eine
 * gepflegte Zahl — auch unmittelbar nachdem der Anwender das Feld geleert hatte.
 * Familie: F-71 (Leeren möglich) → N-571 (Leeren sicher) → N-572 (Leeren bleibt).
 *
 * ⭐ **Verhalten statt String-Scan.** Der Wächter ruft `getInitialParamData`
 * direkt und rendert das Feld; eine Suche nach `paramStr(…, PARAM_…)` im
 * Quelltext wäre bei der ersten mehrzeiligen Umformatierung blind (dieselbe
 * Klasse wie die mehrzeiligen `.get(`-Aufrufe der N-571-Gegenprüfung). Der
 * Rendertest fängt zusätzlich ein `value={x || '60'}` im JSX.
 *
 * ⚠ **Wer hier einen Key ergänzt, begründet ihn am Leser** (Spalte `warum`):
 * aufgenommen wird nur, wessen Leser „fehlt"/„leer" anders behandelt als den
 * Default. Die übrigen Vorbelegungen des Formulars sind wirkungsgleich, weil
 * ihr Leser denselben SoT-Default selbst einsetzt (Vorlage N-572 §1).
 *
 * Unten stehen die Formular-Roundtrip-Proben (a)–(f) der Vorlage §3/4 gegen die
 * Submit-Nutzlast von `InvestitionForm`. Die Nutzlast ist der gespeicherte
 * Zustand: `PUT /investitionen/{id}` setzt `parameter` als Ganzes
 * (`crud.py::update_investition`, `setattr` ohne Merge, kein Validator auf dem
 * Feld in `investitionen/schemas.py`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { getInitialParamData } from '../components/forms/sections/investitionFormHelpers'
import { InvestitionTypFelder } from '../components/forms/sections/InvestitionTypFelder'
import InvestitionForm from '../components/forms/InvestitionForm'
import type { Investition, InvestitionTyp } from '../types'

vi.mock('../api/investitionen', () => ({
  investitionenApi: { list: vi.fn(() => Promise.resolve([])) },
}))

interface DreiWegeKey {
  typ: InvestitionTyp
  key: string
  /** Sichtbares Label des Felds (so findet es der Anwender). */
  feld: string
  /** Eingeklappte Sektion (`variant="erweitert"`), die erst geöffnet werden muss. */
  sektion: RegExp | null
  /** Warum „leer" hier eine Aussage ist — am Leser begründet. */
  warum: string
}

const DREI_WEGE_KEYS: DreiWegeKey[] = [
  {
    typ: 'e-auto',
    key: 'pv_ladeanteil_prozent',
    feld: 'PV-Ladeanteil (%)',
    sektion: null,
    warum: 'N-188-Kaskade `roi_standalone.py`: gepflegt (auch 0) → gemessener IST-Anteil → 60 %. '
      + 'Eine vorbelegte 60 verdrängt den gemessenen Anteil für immer.',
  },
  {
    typ: 'e-auto',
    key: 'benzinpreis_euro',
    feld: 'Benzinpreis (€/L)',
    sektion: /Vergleich & Betrieb/,
    warum: 'ROI-Kaskade `resolve_eauto_benzinpreis`: Parameter → Kraftstoffpreis der Monatsdaten '
      + '(EU Oil Bulletin) → 1,65 €. Ein vorbelegter Preis friert den Marktpreis ein.',
  },
  {
    typ: 'waermepumpe',
    key: 'pv_anteil_prozent',
    feld: 'PV-Anteil (%)',
    sektion: /Vergleich mit alter Heizung/,
    warum: 'Drei Wege `finanz_prognose.py::_gepflegter_pv_anteil` (N-277/N-354): Key fehlt = 30 %, '
      + '`\'\'` = zurückgenommen (fällt aus dem Prognose-Mittel), Zahl = Wert. Vorbelegt machte das '
      + 'nächste Speichern aus „zurückgenommen" wieder eine gepflegte 30.',
  },
]

describe('N-572 — getInitialParamData belegt die Drei-Wege-Keys nicht vor', () => {
  for (const { typ, key, warum } of DREI_WEGE_KEYS) {
    describe(`${typ} · ${key}`, () => {
      it('hat eine Begründung am Leser', () => {
        expect(warum.length).toBeGreaterThan(40)
      })

      it('Anlegen ({}): Key ist vorhanden und leer', () => {
        const result = getInitialParamData(typ, {})
        // Gegenrichtung: ein umbenannter oder gewanderter Key fiele sonst still
        // durch — `result[key]` wäre `undefined` und sähe wie „leer" aus.
        expect(key in result).toBe(true)
        expect(result[key]).toBe('')
      })

      it("geleert gespeichert ({key: ''}): bleibt leer", () => {
        expect(getInitialParamData(typ, { [key]: '' })[key]).toBe('')
      })

      it('gepflegt ({key: 42}): bleibt der Wert', () => {
        expect(getInitialParamData(typ, { [key]: 42 })[key]).toBe('42')
      })
    })
  }
})

describe('N-572 — das gerenderte Feld zeigt beim Anlegen nichts vor', () => {
  const noop = () => {}

  for (const { typ, key, feld, sektion } of DREI_WEGE_KEYS) {
    it(`${typ} · ${feld} ist leer`, () => {
      render(
        <InvestitionTypFelder
          typ={typ}
          paramData={getInitialParamData(typ, {})}
          onInputChange={noop}
          setParam={noop}
          zeige={() => undefined}
          markTouched={noop}
          setFeldRef={() => () => {}}
        />,
      )
      // Eingeklappte Sektionen sind nicht im DOM — ohne den Klick fände die
      // Probe nichts und wäre durch eine falsche Beschriftung grün zu bekommen.
      if (sektion) fireEvent.click(screen.getByRole('button', { name: sektion }))
      const input = screen.getByLabelText(feld) as HTMLInputElement
      expect(input.name).toBe(`param_${key}`)
      expect(input.value).toBe('')
    })
  }
})

// ── Formular-Roundtrip-Proben (a)–(f), Vorlage §3/4 ────────────────────────

/** Speichern auslösen und das an onSubmit übergebene `parameter`-JSON zurückgeben. */
async function speichern(onSubmit: ReturnType<typeof vi.fn>): Promise<Record<string, unknown>> {
  fireEvent.submit(document.querySelector('form')!)
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  const nutzlast = onSubmit.mock.calls[0][0] as Record<string, unknown>
  return (nutzlast.parameter ?? {}) as Record<string, unknown>
}

function eAuto(parameter: Record<string, unknown>): Investition {
  return {
    id: 11, anlage_id: 1, typ: 'e-auto', bezeichnung: 'Smart',
    anschaffungsdatum: '2024-03-01', aktiv: true, parameter,
  }
}

function waermepumpe(parameter: Record<string, unknown>): Investition {
  return {
    id: 12, anlage_id: 1, typ: 'waermepumpe', bezeichnung: 'WP',
    anschaffungsdatum: '2024-03-01', aktiv: true,
    parameter: { wp_art: 'luft_wasser', effizienz_modus: 'gesamt_jaz', jaz: 3.5, ...parameter },
  }
}

function oeffnen(typ: InvestitionTyp, investition: Investition | undefined, onSubmit: ReturnType<typeof vi.fn>) {
  render(
    <InvestitionForm anlageId={1} typ={typ} investition={investition} onSubmit={onSubmit} onCancel={() => {}} />,
  )
}

function feldWert(label: string, sektion: RegExp | null = null): string {
  if (sektion) fireEvent.click(screen.getByRole('button', { name: sektion }))
  return (screen.getByLabelText(label) as HTMLInputElement).value
}

/** Anlegen: Bezeichnung + Anschaffungsdatum setzen (Pflichtfelder). */
async function pflichtfelderAnlegen(bezeichnung: string) {
  fireEvent.change(screen.getByLabelText(/Bezeichnung/i), { target: { value: bezeichnung } })
  fireEvent.click(screen.getByLabelText('Anschaffungsdatum'))
  fireEvent.click(await screen.findByRole('button', { name: '15' }))
}

describe('N-572 — Formular-Roundtrip (Vorlage §3/4)', () => {
  beforeEach(() => vi.clearAllMocks())

  it("(a) E-Auto mit pv_ladeanteil_prozent='' öffnen ⇒ Feld leer ⇒ speichern ⇒ bleibt ''", async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    oeffnen('e-auto', eAuto({ pv_ladeanteil_prozent: '' }), onSubmit)
    expect(feldWert('PV-Ladeanteil (%)')).toBe('')
    const parameter = await speichern(onSubmit)
    expect('pv_ladeanteil_prozent' in parameter).toBe(true)
    expect(parameter.pv_ladeanteil_prozent).toBe('')
  })

  it('(b) E-Auto mit gespeicherter 60 öffnen ⇒ Feld zeigt 60 ⇒ speichern ⇒ 60 bleibt', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    oeffnen('e-auto', eAuto({ pv_ladeanteil_prozent: 60 }), onSubmit)
    expect(feldWert('PV-Ladeanteil (%)')).toBe('60')
    const parameter = await speichern(onSubmit)
    expect(parameter.pv_ladeanteil_prozent).toBe(60)
  })

  it('(c) E-Auto NEU anlegen, Felder leer lassen ⇒ weder pv_ladeanteil_prozent noch benzinpreis_euro im JSON', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    oeffnen('e-auto', undefined, onSubmit)
    expect(feldWert('PV-Ladeanteil (%)')).toBe('')
    await pflichtfelderAnlegen('Neues E-Auto')
    const parameter = await speichern(onSubmit)
    expect('pv_ladeanteil_prozent' in parameter).toBe(false)
    expect('benzinpreis_euro' in parameter).toBe(false)
    // Gegenprobe: das Formular hat überhaupt ein Parameter-JSON gesendet —
    // sonst wäre „Key fehlt" trivial wahr.
    expect(parameter.verbrauch_kwh_100km).toBe(18)
  })

  it("(d) WP: '' bleibt '' — und eine WP OHNE den Key bleibt ohne Key (Zustand 1 ≠ 2)", async () => {
    const onSubmitLeer = vi.fn(() => Promise.resolve())
    oeffnen('waermepumpe', waermepumpe({ pv_anteil_prozent: '' }), onSubmitLeer)
    expect(feldWert('PV-Anteil (%)', /Vergleich mit alter Heizung/)).toBe('')
    const leer = await speichern(onSubmitLeer)
    expect('pv_anteil_prozent' in leer).toBe(true)
    expect(leer.pv_anteil_prozent).toBe('')
  })

  it('(d) WP OHNE pv_anteil_prozent öffnen und speichern ⇒ Key bleibt abwesend (nie gepflegt = 30 %)', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    oeffnen('waermepumpe', waermepumpe({}), onSubmit)
    expect(feldWert('PV-Anteil (%)', /Vergleich mit alter Heizung/)).toBe('')
    const parameter = await speichern(onSubmit)
    expect('pv_anteil_prozent' in parameter).toBe(false)
    expect(parameter.jaz).toBe(3.5)
  })

  it('(d) WP NEU anlegen ⇒ pv_anteil_prozent fehlt im JSON', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    oeffnen('waermepumpe', undefined, onSubmit)
    await pflichtfelderAnlegen('Neue WP')
    const parameter = await speichern(onSubmit)
    expect('pv_anteil_prozent' in parameter).toBe(false)
  })

  it("(e) Benzinpreis: '' bleibt '' · 1,65 bleibt 1,65", async () => {
    const onSubmitLeer = vi.fn(() => Promise.resolve())
    const { unmount } = render(
      <InvestitionForm anlageId={1} typ="e-auto" investition={eAuto({ benzinpreis_euro: '' })}
        onSubmit={onSubmitLeer} onCancel={() => {}} />,
    )
    expect(feldWert('Benzinpreis (€/L)', /Vergleich & Betrieb/)).toBe('')
    const leer = await speichern(onSubmitLeer)
    expect('benzinpreis_euro' in leer).toBe(true)
    expect(leer.benzinpreis_euro).toBe('')
    unmount()

    const onSubmitWert = vi.fn(() => Promise.resolve())
    oeffnen('e-auto', eAuto({ benzinpreis_euro: 1.65 }), onSubmitWert)
    expect(feldWert('Benzinpreis (€/L)', /Vergleich & Betrieb/)).toBe('1.65')
    const wert = await speichern(onSubmitWert)
    expect(wert.benzinpreis_euro).toBe(1.65)
  })

  it('(f) E-Auto OHNE die Keys (Wizard/API) öffnen, nichts eintragen, speichern ⇒ Keys bleiben abwesend', async () => {
    // Der Übergang, der bis N-572 kaputt war: das Feld zeigte 60 bzw. 1,65,
    // und das erste Speichern schrieb sie als gepflegte Werte. Er hängt am
    // `key in investition.parameter`-Zweig von `InvestitionForm` (F-71): ein
    // leeres Feld wird nur dort zu `''`, wo der Key schon existierte.
    const onSubmit = vi.fn(() => Promise.resolve())
    oeffnen('e-auto', eAuto({ verbrauch_kwh_100km: 17, sensor_mapping_hinweis: 'wizard' }), onSubmit)
    expect(feldWert('PV-Ladeanteil (%)')).toBe('')
    const parameter = await speichern(onSubmit)
    expect('pv_ladeanteil_prozent' in parameter).toBe(false)
    expect('benzinpreis_euro' in parameter).toBe(false)
    // Gegenprobe: der Merge hat die übrigen Keys getragen.
    expect(parameter.verbrauch_kwh_100km).toBe(17)
    expect(parameter.sensor_mapping_hinweis).toBe('wizard')
  })
})
