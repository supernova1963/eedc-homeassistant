/**
 * Der Achsen-Standard aller Charts — bis E6 ohne Test (M9).
 *
 * `lib/chartAchse.ts` ist die EINE Wahrheit für Recharts-Achsen (D7-5 / detLAN
 * R7 / R9-Nacharbeit). Gemessen am 2026-08-24: keine der 159 Testdateien
 * importierte das Modul — obwohl `check:charts` seine Einhaltung erzwingt.
 * Der Wächter prüft, ob die Aufrufer ihn benutzen; **was er liefert**, stand
 * nirgends.
 *
 * Die Zusagen hier sind mehrfach hart erarbeitete Entscheide:
 *
 * * **45° einheitlich, mobil wie Desktop** (D11-10, detLAN R11 + Gernot
 *   2026-06-29) — und **nie 90°-Quer** (R9, detLAN).
 * * **Y-Tick-Zahlen bleiben waagerecht**, die Breite kommt aus der Zentrale
 *   (D18-3, detlan #210) — nie der Recharts-Default von 60 px.
 * * **Die Einheit steht waagerecht über dem obersten Tick**, horizontal an
 *   dessen Kante ausgerichtet (Gernot 2026-06-30) — nicht in der Achsenmitte.
 */
import { describe, it, expect } from 'vitest'
import { isValidElement } from 'react'
import {
  ACHSEN_MARGIN_TOP,
  ACHSEN_TICK,
  ACHSEN_Y_BREITE,
  achsenEinheit,
  achsenTick,
  xAchse,
  yAchse,
} from './chartAchse'

describe('achsenTick', () => {
  it('formatiert de-DE: Tausenderpunkt', () => {
    expect(achsenTick(2800)).toBe('2.800')
  })

  it('formatiert de-DE: Komma-Dezimale', () => {
    expect(achsenTick(4.5)).toBe('4,5')
  })

  it('laesst kleine Zahlen unveraendert', () => {
    expect(achsenTick(100)).toBe('100')
  })

  it('reicht Text unveraendert durch', () => {
    expect(achsenTick('Jan')).toBe('Jan')
  })

  it('faengt NaN und Infinity ab, statt sie anzuzeigen', () => {
    expect(achsenTick(NaN)).toBe('NaN')
    expect(achsenTick(Infinity)).toBe('Infinity')
  })

  it('liefert bei null/undefined eine leere Zeichenkette', () => {
    expect(achsenTick(null as unknown as number)).toBe('')
    expect(achsenTick(undefined as unknown as number)).toBe('')
  })
})

describe('xAchse', () => {
  it('dreht EINHEITLICH um −45°, mobil wie Desktop (D11-10)', () => {
    expect(xAchse(true).angle).toBe(-45)
    expect(xAchse(false).angle).toBe(-45)
    expect(xAchse()).toEqual(xAchse(true))
  })

  it('dreht NIE ins Quer-Format (R9, detLAN)', () => {
    expect(Math.abs(xAchse(true).angle ?? 0)).not.toBe(90)
  })

  it('duennt enge Reihen aus statt sie zu ueberlappen', () => {
    expect(xAchse(false).interval).toBe('preserveStartEnd')
  })

  it('traegt die zentrale Tick-Groesse und einen Endanker fuer die Drehung', () => {
    expect(xAchse(false).tick).toBe(ACHSEN_TICK)
    expect(xAchse(false).textAnchor).toBe('end')
  })

  it('reserviert Hoehe fuer die gedrehten Labels', () => {
    expect(xAchse(false).height).toBeGreaterThan(0)
  })
})

describe('yAchse', () => {
  it('setzt die Breite aus der Zentrale — nie den Recharts-Default 60', () => {
    expect(yAchse(false).width).toBe(ACHSEN_Y_BREITE)
    expect(yAchse(false).width).not.toBe(60)
  })

  it('laesst eine betragsabhaengige Uebersteuerung zu', () => {
    expect(yAchse(false, 52).width).toBe(52)
  })

  it('dreht Y-Tick-Zahlen NIE — auch mobil nicht (R9)', () => {
    expect(yAchse(true)).not.toHaveProperty('angle')
    expect(yAchse(true).width).toBe(ACHSEN_Y_BREITE)
  })

  it('benutzt dieselbe Tick-Groesse wie die X-Achse', () => {
    expect(yAchse(false).tick).toBe(xAchse(false).tick)
    expect(ACHSEN_TICK.fontSize).toBe(10)
  })
})

describe('achsenEinheit', () => {
  const box = { x: 30, y: 20, width: 48, height: 200 }

  it('steht als waagerechte Beschriftung OBEN', () => {
    expect(achsenEinheit('kWh').position).toBe('top')
    expect(achsenEinheit('kWh').value).toBe('kWh')
  })

  it('rendert ein <text>-Element ohne jede Drehung', () => {
    const el = achsenEinheit('kWh').content({ viewBox: box })
    expect(isValidElement(el)).toBe(true)
    expect(el.type).toBe('text')
    expect(el.props).not.toHaveProperty('transform')
  })

  it('linke Achse: rechtsbuendig an der rechten Box-Kante', () => {
    // Die Zahlen der linken Achse stehen rechtsbuendig an der Achslinie —
    // die Einheit muss dieselbe Kante treffen (Gernot 2026-06-30).
    const el = achsenEinheit('kWh', 'links').content({ viewBox: box })
    expect(el.props.x).toBe(box.x + box.width)
    expect(el.props.textAnchor).toBe('end')
  })

  it('rechte Achse: linksbuendig an der linken Box-Kante', () => {
    const el = achsenEinheit('°C', 'rechts').content({ viewBox: box })
    expect(el.props.x).toBe(box.x)
    expect(el.props.textAnchor).toBe('start')
  })

  it('liegt UEBER dem obersten Tick, nicht darauf', () => {
    const el = achsenEinheit('kWh').content({ viewBox: box })
    expect(el.props.y).toBeLessThan(box.y)
  })

  it('der reservierte Rand traegt die Einheit', () => {
    const el = achsenEinheit('kWh').content({ viewBox: box })
    expect(box.y - (el.props.y as number)).toBeLessThanOrEqual(ACHSEN_MARGIN_TOP)
  })

  it('faerbt ueber Tailwind-Utilities, nie per Inline-Hex (Regel 0a)', () => {
    const el = achsenEinheit('kWh').content({ viewBox: box })
    expect(el.props.className).toContain('dark:')
    expect(JSON.stringify(el.props)).not.toMatch(/#[0-9a-fA-F]{3,6}/)
  })

  it('haelt eine fehlende viewBox aus', () => {
    const el = achsenEinheit('kWh').content({})
    expect(el.props.x).toBe(0)
  })
})
