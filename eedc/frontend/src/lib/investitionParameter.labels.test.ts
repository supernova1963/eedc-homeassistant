/**
 * Kosmetik Lab rc13 (K-3): die eine Label-Quelle der Parameter (`PARAMETER_LABELS`), gelesen vom Hub-Block
 * «Einstellungen» (`v4/KomponentenTypV4.tsx::paramFelder`).
 *
 * Die Vollständigkeits-Probe baut die Schlüssel aus den Exporten `PARAM_*` selbst (ohne `*_DEFAULTS`) — keine getippte
 * Liste: eine neue Konstante oder ein neuer Schlüssel ohne Label meldet sich hier (und beim Compiler, `labelsFuer`).
 */
import { describe, it, expect } from 'vitest'
import * as IP from './investitionParameter'
import {
  PARAMETER_LABELS, PARAM_WALLBOX, PARAM_WAERMEPUMPE, parameterAnzeigeName, parameterLabel, parameterWertLabel,
} from './investitionParameter'

const paramKonstanten = Object.entries(IP).filter(
  ([name, wert]) => /^PARAM_[A-Z_]+$/.test(name) && !name.endsWith('_DEFAULTS') && typeof wert === 'object',
) as [string, Record<string, string>][]

describe('PARAMETER_LABELS — Vollständigkeit aus den Konstanten', () => {
  it('es gibt Konstanten (die Probe greift überhaupt)', () => {
    expect(paramKonstanten.length).toBeGreaterThanOrEqual(8)
  })

  it.each(paramKonstanten)('%s: jede Konstante steht in der Label-Quelle, jeder Schlüssel hat ein Label', (_name, param) => {
    const eintraege = Object.entries(PARAMETER_LABELS).filter(([, e]) => e.param === param)
    expect(eintraege).toHaveLength(1)
    const [typ, eintrag] = eintraege[0]
    for (const key of Object.values(param)) {
      expect(eintrag.labels[key], `${typ}.${key}`).toBeTruthy()
      expect(parameterLabel(typ, key)).toBe(eintrag.labels[key])
    }
  })

  it('Enum-Klartexte nur an Schlüsseln, die die Konstante kennt', () => {
    for (const [typ, e] of Object.entries(PARAMETER_LABELS)) {
      for (const key of Object.keys(e.werte)) expect(Object.values(e.param), `${typ}.${key}`).toContain(key)
    }
  })
})

describe('PARAMETER_LABELS — Beispiele', () => {
  it('Wallbox: Formular-Wortlaut mit Einheit statt «max ladeleistung kw»', () => {
    expect(parameterAnzeigeName('wallbox', PARAM_WALLBOX.MAX_LADELEISTUNG_KW)).toBe('Max. Ladeleistung (kW)')
    expect(parameterAnzeigeName('wallbox', PARAM_WALLBOX.OBERFLAECHE_URL)).toBe('Adresse der Hersteller-Oberfläche')
    expect(parameterAnzeigeName('e-auto', 'batteriekapazitaet_kwh')).toBe('Batteriekapazität (kWh)')
  })

  it('Wärmepumpe: Enum-Werte mit Klartext aus den vorhandenen Listen; ohne Liste roh', () => {
    expect(parameterAnzeigeName('waermepumpe', PARAM_WAERMEPUMPE.WP_ART)).toBe('Wärmepumpenart')
    expect(parameterWertLabel('waermepumpe', PARAM_WAERMEPUMPE.WP_ART, 'luft_wasser')).toBe('Luft/Wasser')
    expect(parameterWertLabel('waermepumpe', PARAM_WAERMEPUMPE.ALTER_ENERGIETRAEGER, 'oel')).toBe('Heizöl')
    expect(parameterWertLabel('waermepumpe', PARAM_WAERMEPUMPE.VORLAUFTEMPERATUR, '35')).toBe('35 °C (Fußbodenheizung)')
    expect(parameterWertLabel('waermepumpe', PARAM_WAERMEPUMPE.KUEHLUNG_ART, 'passiv')).toContain('Passiv')
    // Benannte Grenze: `abgrenzung` hat seine Liste im Formular (N-349-Anker) — der Wert bleibt roh.
    expect(parameterWertLabel('waermepumpe', PARAM_WAERMEPUMPE.ABGRENZUNG, 'fremdstrom')).toBeNull()
    // Ein unbekannter Wert bleibt roh.
    expect(parameterWertLabel('waermepumpe', PARAM_WAERMEPUMPE.WP_ART, 'xyz')).toBeNull()
  })

  it('ohne Label: die heutige Ableitung (unbekannter Schlüssel, unbekannter Typ)', () => {
    expect(parameterAnzeigeName('wallbox', 'neues_feld_kw')).toBe('neues feld kw')
    expect(parameterAnzeigeName('pv-system', 'irgendwas_x')).toBe('irgendwas x')
    expect(parameterLabel('wallbox', 'neues_feld_kw')).toBeNull()
  })
})
