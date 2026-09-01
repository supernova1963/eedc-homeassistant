/**
 * Wortlaut-SoT „worauf das individuelle Verbrauchsprofil beruht" (N-48).
 *
 * Der Satz steht an zwei Stellen — Legende des Wetter-Widgets und
 * Verbrauchs-Tooltip der 3-Tage-Aussicht. Bis 2026-09-01 bauten ihn beide von
 * Hand nach und nannten allein die Tageszahl; das Backend gibt das Profil aber
 * ab zwei Tagen frei, und ein „Tag" entsteht aus einer einzigen gemessenen
 * Stunde. „2 Tage" las sich damit wie die Güte des Profils.
 *
 * Geprüft werden die drei Regelhälften einzeln, weil sie einzeln brechen können:
 * die Abdeckung erscheint · ihre **Folge** erscheint nur bei echter Lücke · eine
 * fehlende Abdeckung wird nicht erfunden.
 */
import { describe, it, expect } from 'vitest'
import { verbrauchsprofilBasis, istIndividuellesProfil, profilKlasseLabel } from './verbrauchsprofilHerkunft'

describe('verbrauchsprofilBasis', () => {
  it('nennt die gemessene Abdeckung neben der Tageszahl', () => {
    const satz = verbrauchsprofilBasis('individuell_werktag', 2, 1)
    expect(satz).toContain('2 Tage')
    expect(satz).toContain('1 von 24 Stunden gemessen')
  })

  it('nennt die FOLGE der Lücke, nicht nur die Zahl', () => {
    // Der eigentliche Punkt von N-48: eine zweite Zahl allein erklärt nichts.
    const satz = verbrauchsprofilBasis('individuell_werktag', 2, 1)
    expect(satz).toContain('die übrigen 23 aus der Standard-Grundlast')
  })

  it('behauptet KEINEN Rückfall, wo alle 24 Stunden gemessen wurden', () => {
    const satz = verbrauchsprofilBasis('individuell_werktag', 7, 24)
    expect(satz).toContain('24 von 24 Stunden gemessen')
    expect(satz).not.toContain('Standard-Grundlast')
    expect(satz).not.toContain('übrigen')
  })

  it('erfindet keine Abdeckung, wenn das Backend keine liefert', () => {
    // Gegen ein älteres Backend kommt `profil_slots` als null — dann bleibt es bei
    // der Tageszahl. Eine erfundene Abdeckung wäre schlimmer als keine.
    const satz = verbrauchsprofilBasis('individuell_werktag', 5, null)
    expect(satz).toBe('Werktag, 5 Tage')
    expect(satz).not.toContain('Stunden')
  })

  it('trennt Werktag und Wochenende', () => {
    expect(verbrauchsprofilBasis('individuell_wochenende', 3, 12)).toContain('Wochenende')
    expect(verbrauchsprofilBasis('individuell_werktag', 3, 12)).toContain('Werktag')
  })

  it('gibt null zurück, wo gar kein individuelles Profil vorliegt', () => {
    // Die Aufrufer setzen dann ihren eigenen BDEW-Text — der Helfer darf ihn nicht
    // vorwegnehmen, weil beide Stellen ihn verschieden formulieren.
    expect(verbrauchsprofilBasis('bdew_h0', null, null)).toBeNull()
    expect(verbrauchsprofilBasis(undefined, 5, 24)).toBeNull()
  })

  it('markiert eine unbekannte Tageszahl, statt sie zu unterschlagen', () => {
    expect(verbrauchsprofilBasis('individuell_werktag', null, 3)).toContain('? Tage')
  })
})

describe('istIndividuellesProfil / profilKlasseLabel', () => {
  it('erkennt beide individuellen Ausprägungen und nur die', () => {
    expect(istIndividuellesProfil('individuell_werktag')).toBe(true)
    expect(istIndividuellesProfil('individuell_wochenende')).toBe(true)
    expect(istIndividuellesProfil('bdew_h0')).toBe(false)
    expect(istIndividuellesProfil(null)).toBe(false)
  })

  it('benennt die Klasse, aus der gemittelt wurde', () => {
    expect(profilKlasseLabel('individuell_wochenende')).toBe('Wochenende')
    expect(profilKlasseLabel('individuell_werktag')).toBe('Werktag')
  })
})
