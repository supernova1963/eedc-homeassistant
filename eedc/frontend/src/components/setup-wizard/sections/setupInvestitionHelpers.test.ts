import { describe, it, expect } from 'vitest'
import { AUSRICHTUNG_OPTIONEN as WIZARD_LISTE } from './setupInvestitionHelpers'
import { AUSRICHTUNG_OPTIONEN as FORMULAR_LISTE } from '../../forms/sections/investitionFormHelpers'

// N-174 (2026-08-16): Für dieselbe Frage — „wohin zeigt das Modul?" — gab es im
// Baum DREI Listen: die geteilte des Formulars (9 Optionen, für PV-Modul UND
// Balkonkraftwerk), eine wortgleiche Kopie im Wizard und eine dort auf 6
// reduzierte fürs BKW. Nordost, Nord und Nordwest fehlten also genau dann, wenn
// man sein Balkonkraftwerk im Setup anlegte — beim späteren Bearbeiten waren
// sie da. Eine Datenrolle, eine SoT (Regel 0a).

describe('Ausrichtungs-Optionen — eine Liste für Wizard und Formular', () => {
  it('der Wizard nutzt exakt die Liste des Formulars', () => {
    expect(WIZARD_LISTE).toBe(FORMULAR_LISTE)
  })

  it('enthält auch die Nord-Richtungen — sie fehlten dem BKW im Setup', () => {
    const werte = FORMULAR_LISTE.map((o) => ('value' in o ? o.value : ''))
    expect(werte).toContain('Nordost')
    expect(werte).toContain('Nord')
    expect(werte).toContain('Nordwest')
    expect(werte).toHaveLength(9)
  })
})
