/**
 * Ableitungslogik Erfassungs-Zustände (Monatsabschluss-V4 §4) — deckt die
 * Vorrang-Hierarchie manuell > gemessen > geschätzt > leer ab (P3b) sowie
 * R1/R2-Prefill und den „weicht ab"-Sonderfall.
 */
import { describe, it, expect } from 'vitest'
import type { FeldStatus, Vorschlag } from '../api/monatsabschluss'
import { ermittleZustand, prefillWert, besterVorschlag, istGemesseneQuelle, rollupZustand, zaehleAmpel } from './erfassungZustand'

function feld(partial: Partial<FeldStatus>): FeldStatus {
  return {
    feld: 'einspeisung_kwh', label: 'Einspeisung', einheit: 'kWh',
    aktueller_wert: null, aktueller_text: null, quelle: null,
    vorschlaege: [], warnungen: [], strategie: null, sensor_id: null,
    typ: 'number', gruppe: 'zaehler', ...partial,
  }
}
function vorschlag(wert: number, quelle: Vorschlag['quelle'], konfidenz: number): Vorschlag {
  return { wert, quelle, konfidenz, beschreibung: '' }
}

describe('istGemesseneQuelle', () => {
  it('Sensor/Import/Connector + manuell = gemessen; Historie/Berechnung = nicht', () => {
    expect(istGemesseneQuelle('ha_statistics')).toBe(true)
    expect(istGemesseneQuelle('local_connector')).toBe(true)
    expect(istGemesseneQuelle('manuell')).toBe(true)
    expect(istGemesseneQuelle('manual')).toBe(true)
    expect(istGemesseneQuelle('vorjahr')).toBe(false)
    expect(istGemesseneQuelle('durchschnitt')).toBe(false)
    expect(istGemesseneQuelle(null)).toBe(false)
  })
})

describe('besterVorschlag = höchste Konfidenz', () => {
  it('wählt den Kandidaten mit der höchsten Konfidenz', () => {
    const best = besterVorschlag([vorschlag(100, 'vorjahr', 60), vorschlag(120, 'ha_statistics', 92)])
    expect(best?.wert).toBe(120)
  })
  it('leere Liste → null', () => {
    expect(besterVorschlag([])).toBeNull()
    expect(prefillWert(feld({}))).toBeNull()
  })
})

describe('ermittleZustand', () => {
  it('leeres Feld ohne Vorschlag → fehlt', () => {
    expect(ermittleZustand('', feld({})).zustand).toBe('fehlt')
  })

  it('gespeicherter Wert (form == gespeichert) → gemessen mit dessen Quelle', () => {
    const r = ermittleZustand('1318.13', feld({ aktueller_wert: 1318.13, quelle: 'portal_import' }))
    expect(r.zustand).toBe('gemessen')
    expect(r.quelle).toBe('portal_import')
  })

  it('manuell gespeicherter Wert → geprüft (von Hand = bewusste Bestätigung)', () => {
    const r = ermittleZustand('9.43', feld({ aktueller_wert: 9.43, quelle: 'manuell' }))
    expect(r.zustand).toBe('geprueft')
    expect(r.quelle).toBe('manuell')
  })

  it('R1 frisch: Prefill == gemessener Vorschlag → gemessen', () => {
    const r = ermittleZustand('120', feld({ vorschlaege: [vorschlag(120, 'ha_statistics', 92)] }))
    expect(r.zustand).toBe('gemessen')
    expect(r.quelle).toBe('ha_statistics')
  })

  it('R1 frisch: Prefill == geschätzter Vorschlag → geschaetzt', () => {
    const r = ermittleZustand('95', feld({ vorschlaege: [vorschlag(95, 'vorjahr', 60)] }))
    expect(r.zustand).toBe('geschaetzt')
    expect(r.quelle).toBe('vorjahr')
  })

  it('vom Nutzer eingetippt (≠ gespeichert, ≠ Vorschlag) → geprüft', () => {
    const r = ermittleZustand('500', feld({ aktueller_wert: 1318.13, quelle: 'portal_import', vorschlaege: [vorschlag(1318.13, 'portal_import', 90)] }))
    expect(r.zustand).toBe('geprueft')
    expect(r.quelle).toBe('manuell')
  })

  it('bestätigte Schätzung (✓ passt) → geprüft', () => {
    const f = feld({ vorschlaege: [vorschlag(95, 'vorjahr', 60)] })
    expect(ermittleZustand('95', f, false).zustand).toBe('geschaetzt')
    expect(ermittleZustand('95', f, true).zustand).toBe('geprueft')
  })

  it('leeres Feld: erwartet (Zähler/Sensor) → offen, sonst → optional', () => {
    expect(ermittleZustand('', feld({ gruppe: 'zaehler' })).zustand).toBe('fehlt')
    expect(ermittleZustand('', feld({ gruppe: null, sensor_id: 'sensor.x' })).zustand).toBe('fehlt')
    expect(ermittleZustand('', feld({ gruppe: null, sensor_id: null, vorschlaege: [] })).zustand).toBe('optional')
  })

  it('weicht ab: gespeicherter Wert + abweichender gemessener Vorschlag, form noch == gespeichert', () => {
    const r = ermittleZustand('9.43', feld({
      aktueller_wert: 9.43, quelle: 'manuell',
      vorschlaege: [vorschlag(9.80, 'ha_statistics', 92)],
    }))
    expect(r.zustand).toBe('weicht_ab')
    expect(r.weichtAb).toEqual({ sensorWert: 9.80, gespeichert: 9.43 })
  })

  it('kein „weicht ab", wenn der abweichende Vorschlag nur geschätzt ist', () => {
    const r = ermittleZustand('9.43', feld({
      aktueller_wert: 9.43, quelle: 'manuell',
      vorschlaege: [vorschlag(11.0, 'vorjahr', 60)],
    }))
    expect(r.zustand).toBe('geprueft') // gespeicherter manueller Wert bleibt (geprüft)
  })

  it('weicht ab entfällt, sobald der Nutzer den Sensorwert übernommen hat (form == Sensor)', () => {
    const r = ermittleZustand('9.80', feld({
      aktueller_wert: 9.43, quelle: 'manuell',
      vorschlaege: [vorschlag(9.80, 'ha_statistics', 92)],
    }))
    expect(r.zustand).toBe('gemessen')
    expect(r.quelle).toBe('ha_statistics')
  })
})

describe('rollupZustand (§6.7 schlechtester Zustand)', () => {
  it('leere Gruppe → gemessen (grün, klappt zu)', () => {
    expect(rollupZustand([])).toBe('gemessen')
  })
  it('alle gemessen → gemessen', () => {
    expect(rollupZustand(['gemessen', 'gemessen'])).toBe('gemessen')
  })
  it('ein offener Wert schlägt alles', () => {
    expect(rollupZustand(['gemessen', 'geschaetzt', 'weicht_ab', 'fehlt'])).toBe('fehlt')
  })
  it('weicht_ab schlägt geschätzt/gemessen', () => {
    expect(rollupZustand(['gemessen', 'geschaetzt', 'weicht_ab'])).toBe('weicht_ab')
  })
  it('geschätzt schlägt gemessen', () => {
    expect(rollupZustand(['gemessen', 'geschaetzt'])).toBe('geschaetzt')
  })
  it('optional wird ignoriert; nur optional/leer → gemessen (grün, klappt zu)', () => {
    expect(rollupZustand(['gemessen', 'optional'])).toBe('gemessen')
    expect(rollupZustand(['optional', 'optional'])).toBe('gemessen')
    expect(rollupZustand(['geprueft', 'optional'])).toBe('geprueft')
  })
})

describe('zaehleAmpel (§6.2)', () => {
  it('fertig = gemessen+geprüft, prüfen = geschätzt+weicht_ab, offen = fehlt, optional zählt nicht', () => {
    const z = zaehleAmpel(['gemessen', 'geprueft', 'geschaetzt', 'weicht_ab', 'fehlt', 'optional'])
    expect(z).toEqual({ fertig: 2, pruefen: 2, offen: 1 })
  })
})
