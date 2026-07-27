/**
 * PV-Modul-Formular: Querprüfung „Anzahl × Wp ↔ eingetragene kWp" (R22-2a).
 *
 * Anlass (PN 89782, Rainer): die Rechenprobe „Berechnete Leistung: X kWp" stand
 * unverbunden neben dem kWp-Feld. Wer sich vertippte, merkte es erst am
 * Daten-Checker — und dort nur als anlagenweite Summe ohne Bezug zum String.
 *
 * Die Warnung ist bewusst weich: Modul-Details sind optional, die kWp bleibt
 * der SoT. Sie darf deshalb weder das Speichern blockieren noch erscheinen,
 * solange nur eines der beiden Detail-Felder gefüllt ist.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { PvModulFelder } from './PvModulFelder'

const noop = () => {}

/** Rendert und gibt den Text der Sektion zurück — die Rechenprobe steht als
 *  ein Satz mit interpolierten Zahlen, also in mehreren Text-Nodes.
 *  `aufklappen`: die Sektion ist „erweitert" und startet zu; nur bei
 *  Abweichung soll sie von selbst offen sein (das prüft der erste Test). */
function zeige(params: Record<string, string>, leistungKwp?: string, aufklappen = true): string {
  const { container } = render(
    <PvModulFelder
      paramData={params}
      onInputChange={noop}
      setParam={noop}
      zeige={() => undefined}
      markTouched={noop}
      setFeldRef={() => () => {}}
      leistungKwp={leistungKwp}
    />,
  )
  const kopf = screen.getByRole('button', { name: /Modul-Details/ })
  if (aufklappen && kopf.getAttribute('aria-expanded') === 'false') fireEvent.click(kopf)
  return container.textContent ?? ''
}

describe('PvModulFelder — Rechenprobe gegen die eingetragene Leistung', () => {
  it('meldet die Abweichung mit beiden Zahlen', () => {
    // ohne Aufklappen: die Sektion muss bei Abweichung von selbst offen sein
    const text = zeige({ anzahl_module: '18', modul_leistung_wp: '400' }, '4', false)

    expect(text).toMatch(/Berechnete Leistung: 7,20 kWp/)
    expect(text).toMatch(/weicht von der eingetragenen Leistung \(4,00 kWp\) ab/)
  })

  it('stimmige Werte ⇒ nur der neutrale Hinweis, keine Warnung', () => {
    const text = zeige({ anzahl_module: '9', modul_leistung_wp: '400' }, '3.6')

    expect(text).toMatch(/Berechnete Leistung: 3,60 kWp/)
    expect(text).not.toMatch(/weicht von/)
  })

  it('Rundungsdifferenz unter 0,1 kWp bleibt still (dieselbe Toleranz wie der Checker)', () => {
    const text = zeige({ anzahl_module: '9', modul_leistung_wp: '405' }, '3.6')

    expect(text).not.toMatch(/weicht von/)
  })

  it('ohne eingetragene Leistung keine Warnung (Neuanlage tippt erst die Details)', () => {
    const text = zeige({ anzahl_module: '18', modul_leistung_wp: '400' }, '')

    expect(text).toMatch(/Berechnete Leistung: 7,20 kWp/)
    expect(text).not.toMatch(/weicht von/)
  })

  it('halb gepflegte Details ⇒ gar keine Rechenprobe', () => {
    const text = zeige({ anzahl_module: '18', modul_leistung_wp: '' }, '4')

    expect(text).not.toMatch(/Berechnete Leistung/)
  })
})
