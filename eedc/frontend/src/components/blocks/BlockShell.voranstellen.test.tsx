/**
 * BlockShell `voranstellen` (P-433-2, E-P2-7): eine NEUE Block-ID aus der Liste
 * kommt vorn in eine gespeicherte Reihenfolge statt hinten — sonst stünde der
 * Hub-Block «Überblick» bei Bestandsanwendern unten (die Reihenfolge ist schon
 * beim ersten Besuch persistiert). Ohne die Prop bleibt alles wie bisher.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BlockShell } from './BlockShell'
import type { Block } from './types'

const KEY = 'test-voranstellen'
const LS = `eedc-bloecke:${KEY}`
const block = (id: string): Block => ({ id, title: `Block ${id}`, defaultOpen: true, render: () => <p>Inhalt {id}</p> })
const titel = () => screen.getAllByText(/^Block /).map((e) => e.textContent)

describe('BlockShell voranstellen', () => {
  beforeEach(() => localStorage.clear())

  it('vorbelegter Zustand ohne die neue ID ⇒ sie steht danach vorn (auch persistiert)', () => {
    localStorage.setItem(LS, JSON.stringify({ order: ['b', 'a', 'c'], zu: [] }))
    render(<BlockShell bloecke={[block('neu'), block('a'), block('b'), block('c')]} persistKey={KEY} voranstellen={['neu']} />)
    expect(titel()).toEqual(['Block neu', 'Block b', 'Block a', 'Block c'])
    expect(JSON.parse(localStorage.getItem(LS)!).order).toEqual(['neu', 'b', 'a', 'c'])
  })

  it('ohne Prop: neue ID hinten (Bestandsverhalten)', () => {
    localStorage.setItem(LS, JSON.stringify({ order: ['b', 'a', 'c'], zu: [] }))
    render(<BlockShell bloecke={[block('neu'), block('a'), block('b'), block('c')]} persistKey={KEY} />)
    expect(titel()).toEqual(['Block b', 'Block a', 'Block c', 'Block neu'])
  })

  it('wirkt nur beim ersten Auftauchen: wer den Block danach verschiebt, behält seine Wahl', () => {
    localStorage.setItem(LS, JSON.stringify({ order: ['a', 'neu', 'b'], zu: [] }))
    render(<BlockShell bloecke={[block('neu'), block('a'), block('b')]} persistKey={KEY} voranstellen={['neu']} sortierbar />)
    expect(titel()).toEqual(['Block a', 'Block neu', 'Block b'])
  })

  it('ID taucht erst später auf (zweiter Abruf) ⇒ der Effekt stellt sie ebenfalls vorn an', () => {
    localStorage.setItem(LS, JSON.stringify({ order: ['a', 'b'], zu: [] }))
    const { rerender } = render(<BlockShell bloecke={[block('a'), block('b')]} persistKey={KEY} voranstellen={['neu']} />)
    rerender(<BlockShell bloecke={[block('neu'), block('a'), block('b')]} persistKey={KEY} voranstellen={['neu']} />)
    expect(titel()).toEqual(['Block neu', 'Block a', 'Block b'])
    // Verschieben bleibt möglich und wird gemerkt.
    fireEvent.click(screen.getAllByLabelText('einklappen')[0])
    expect(screen.queryByText('Inhalt neu')).not.toBeInTheDocument()
  })
})
