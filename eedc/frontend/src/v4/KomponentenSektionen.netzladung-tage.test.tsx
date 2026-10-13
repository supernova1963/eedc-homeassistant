/**
 * #427 Punkt 2 (Melder rapahl, 13.10.2026) — die Netzladung im laufenden Monat aus den Tagen, Client-Seite.
 *
 * Das Backend liefert im laufenden Monat ohne Monatsabschluss `speicher_ladung_netz_kwh` als Summe der
 * abgelaufenen Tage und `speicher_ladung_netz_herkunft = 'tageswerte'`
 * (`backend/tests/test_427_netzladung_laufender_monat.py`). Hier wird gepinnt:
 *
 *  1. die Speicher-Zeile „davon aus dem Netz (Arbitrage)" nennt die Herkunft beim Überfahren;
 *  2. der Nebenbefund der Triage — die Wandlungsverluste bewerteten im laufenden Monat mit `netz_kwh ?? 0`
 *     den ganzen Verlust zum Einspeisepreis — ist mitgelöst, sobald die Menge ankommt (der Client rechnet
 *     daran nichts Neues, er bekommt nur die Zahl).
 *
 * Schwester: `KomponentenSektionen.n444.test.tsx` (dieselbe Verlust-Zeile, Fenster-Frage).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { isValidElement } from 'react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { Block } from '../components/blocks'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat } from '../test/factories'
import { NETZLADUNG_AUS_TAGEN } from '../lib'

const d = (over: Partial<AktuellerMonatResponse> = {}) => aktuellerMonat(2026, 7, over)

function renderBlock(bloecke: Block[], id: string) {
  const node = bloecke.find((b) => b.id === id)?.render(false)
  if (!isValidElement(node)) throw new Error(`Block ${id} rendert nicht`)
  return render(node)
}

/** Laufender Monat: Ladung 10 kWh, Entladung 8 kWh ⇒ 2 kWh Verlust; Einspeisung 8 ct, Bezug 32 ct. */
const MONAT = {
  speicher_ladung_kwh: 10, speicher_entladung_kwh: 8, einspeise_preis_cent: 8, netzbezug_preis_cent: 32,
} as Partial<AktuellerMonatResponse>

describe('#427 · Netzladung im laufenden Monat aus den Tagen', () => {
  it('die Speicher-Zeile nennt die Herkunft „aus Tageswerten"', () => {
    renderBlock(baueKomponentenBloecke(d({
      ...MONAT, speicher_ladung_netz_kwh: 3, speicher_ladung_netz_herkunft: 'tageswerte',
    })), 'k-speicher')
    expect(screen.getByText('3 kWh')).toHaveAttribute('title', NETZLADUNG_AUS_TAGEN)
  })

  it('aus der Monatszeile ohne Herkunfts-Hinweis', () => {
    renderBlock(baueKomponentenBloecke(d({ ...MONAT, speicher_ladung_netz_kwh: 3 })), 'k-speicher')
    expect(screen.getByText('3 kWh')).not.toHaveAttribute('title')
  })

  it('Wandlungsverluste: mit der Netzladung aus den Tagen anteilig zum Bezugspreis (Nebenbefund mitgelöst)', () => {
    // Vorher (Menge null ⇒ 0): 2 kWh × 8 ct = 0,16 €. Jetzt: 3 ÷ 10 Netz-Anteil ⇒ 1,4 × 8 ct + 0,6 × 32 ct = 0,30 €.
    renderBlock(baueKomponentenBloecke(d({ ...MONAT, speicher_ladung_netz_kwh: null })), 'k-speicher')
    expect(screen.getByText('−0,16 €')).toBeInTheDocument()
  })

  it('… und mit 3 kWh aus den Tagen', () => {
    renderBlock(baueKomponentenBloecke(d({
      ...MONAT, speicher_ladung_netz_kwh: 3, speicher_ladung_netz_herkunft: 'tageswerte',
    })), 'k-speicher')
    expect(screen.getByText('−0,30 €')).toBeInTheDocument()
  })
})
