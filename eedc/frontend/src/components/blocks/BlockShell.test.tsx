import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BlockShell } from './BlockShell'
import type { Block } from './types'

// IA-V4 E3 Slice 1: das aus dem Skelett promovierte universelle Block-Modell.
// Geprüft werden die strukturkritischen Invarianten: Einklappen, Fokus/Vollbild,
// ↑↓-Reihenfolge und die localStorage-Persistenz pro Sicht.

function bloecke(): Block[] {
  return [
    { id: 'a', title: 'Block A', defaultOpen: true, render: () => <p>Inhalt A</p> },
    { id: 'b', title: 'Block B', defaultOpen: true, render: () => <p>Inhalt B</p> },
    { id: 'c', title: 'Block C', defaultOpen: true, render: () => <p>Inhalt C</p> },
  ]
}

const KEY = 'test-sicht'

describe('BlockShell', () => {
  beforeEach(() => localStorage.clear())

  it('rendert alle Blöcke und ihren Inhalt (offen)', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Block A')).toBeInTheDocument()
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    expect(screen.getByText('Inhalt C')).toBeInTheDocument()
  })

  it('klappt einen Block ein (Inhalt verschwindet)', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    fireEvent.click(screen.getAllByLabelText('einklappen')[0])
    // Erstes Toggle betrifft Block A (erster „einklappen"-Button).
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    // Andere Blöcke bleiben offen.
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
  })

  it('Reset-Button erscheint bei Abweichung und stellt den Default wieder her', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.queryByText('zurücksetzen')).not.toBeInTheDocument() // Default → kein Button
    fireEvent.click(screen.getAllByLabelText('einklappen')[0])         // A einklappen → weicht ab
    expect(screen.getByText('zurücksetzen')).toBeInTheDocument()
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('zurücksetzen'))
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()          // wieder offen
    expect(screen.queryByText('zurücksetzen')).not.toBeInTheDocument() // wieder Default
  })

  it('zeigt im Fokus nur den gewählten Block + Zurück', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    const fokusButtons = screen.getAllByLabelText('Fokus / Vollbild')
    fireEvent.click(fokusButtons[1]) // Block B
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    expect(screen.getByText('Zurück')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Zurück'))
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
  })

  it('verschiebt einen Block per ↑↓ (nur wenn sortierbar)', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    const titelVorher = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titelVorher).toEqual(['Block A', 'Block B', 'Block C'])
    // Block B nach oben.
    const hoch = screen.getAllByLabelText('nach oben')
    fireEvent.click(hoch[1])
    const titelNachher = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titelNachher).toEqual(['Block B', 'Block A', 'Block C'])
  })

  it('ohne sortierbar gibt es keine ↑↓-Buttons', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.queryByLabelText('nach oben')).not.toBeInTheDocument()
  })

  // ── Lücken-Tag-Härtung (detLAN-Vollbild-Bug 2026-06-30) ──

  it('Vollbild übersteht das Verschwinden des fokussierten Blocks (kein Rücksprung)', () => {
    const { rerender } = render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    fireEvent.click(screen.getAllByLabelText('Fokus / Vollbild')[1]) // Block B in Vollbild
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    // Navigation auf Lücken-Tag: nur Block A bleibt übrig.
    rerender(<BlockShell bloecke={[bloecke()[0]]} persistKey={KEY} />)
    // Vollbild bleibt OFFEN (kein Standard-Rücksprung): „Zurück" + keine-Daten-Hinweis,
    // und der Standard-Block A wird NICHT als Liste gezeigt.
    expect(screen.getByText('Zurück')).toBeInTheDocument()
    expect(screen.getByText(/keine Daten vor/)).toBeInTheDocument()
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    // Zurück auf einen Daten-Tag: Block B rendert wieder im Vollbild.
    rerender(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
  })

  it('behält die Reihenfolge, wenn Blöcke kurz verschwinden und zurückkommen', () => {
    const { rerender } = render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    fireEvent.click(screen.getAllByLabelText('nach oben')[2]) // C über B → [a, c, b]
    rerender(<BlockShell bloecke={[bloecke()[0]]} persistKey={KEY} sortierbar />) // Lücken-Tag: nur A
    rerender(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)       // zurück: voll
    const titel = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titel).toEqual(['Block A', 'Block C', 'Block B'])
  })

  it('R13-1 (Rainer #101): verschiebt den SICHTBAREN Nachbarn, wenn `order` absente IDs enthält', () => {
    const vier = (): Block[] => [
      { id: 'a', title: 'Block A', defaultOpen: true, render: () => <p>A</p> },
      { id: 'b', title: 'Block B', defaultOpen: true, render: () => <p>B</p> },
      { id: 'c', title: 'Block C', defaultOpen: true, render: () => <p>C</p> },
      { id: 'd', title: 'Block D', defaultOpen: true, render: () => <p>D</p> }, // „E-Mobilität": nur an manchen Tagen
    ]
    const { rerender } = render(<BlockShell bloecke={vier()} persistKey={KEY} sortierbar />)
    // C fällt weg (Komponente an diesem Tag ohne Daten) → order behält [a,b,c,d],
    // sichtbar bleibt [a,b,d]. Damit order.length(4) > ordered.length(3) = der Bug-Fall.
    rerender(<BlockShell bloecke={[vier()[0], vier()[1], vier()[3]]} persistKey={KEY} sortierbar />)
    expect(screen.getAllByText(/^Block [ABD]$/).map((e) => e.textContent)).toEqual(['Block A', 'Block B', 'Block D'])
    // D (sichtbarer Index 2) nach oben → muss mit dem sichtbaren Nachbarn B tauschen,
    // NICHT das absente C anfassen. Vor dem Fix wechselten stattdessen b/c unsichtbar.
    fireEvent.click(screen.getAllByLabelText('nach oben')[2])
    expect(screen.getAllByText(/^Block [ABD]$/).map((e) => e.textContent)).toEqual(['Block A', 'Block D', 'Block B'])
    // Persistierte Order: C bleibt an seiner Stelle, nur B↔D getauscht.
    expect(JSON.parse(localStorage.getItem('eedc-bloecke:' + KEY)!).order).toEqual(['a', 'd', 'c', 'b'])
  })

  it('Persistenz bleibt heil über einen Remount auf einem Lücken-Tag', () => {
    const { unmount } = render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    fireEvent.click(screen.getAllByLabelText('nach oben')[2]) // C über B → order [a, c, b]
    unmount()
    // Remount auf reduziertem Stand (nur Block A) — darf die gespeicherte
    // Reihenfolge [a,c,b] NICHT auf [a] schrumpfen (das war der Bug).
    const r2 = render(<BlockShell bloecke={[bloecke()[0]]} persistKey={KEY} sortierbar />)
    r2.unmount()
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    const titel = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titel).toEqual(['Block A', 'Block C', 'Block B'])
    expect(JSON.parse(localStorage.getItem('eedc-bloecke:' + KEY)!).order).toEqual(['a', 'c', 'b'])
  })

  it('persistiert Klappzustand + Reihenfolge pro Sicht in localStorage', () => {
    const { unmount } = render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    // Block A einklappen + Block C nach oben.
    fireEvent.click(screen.getAllByLabelText('einklappen')[0])
    fireEvent.click(screen.getAllByLabelText('nach oben')[2]) // C über B

    const gespeichert = JSON.parse(localStorage.getItem('eedc-bloecke:' + KEY)!)
    expect(gespeichert.zu).toContain('a')
    expect(gespeichert.order).toEqual(['a', 'c', 'b'])

    // Neu mounten: Zustand wird aus localStorage rekonstruiert.
    unmount()
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument() // A bleibt zu
    const titel = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titel).toEqual(['Block A', 'Block C', 'Block B'])
  })
})

// ── FD: Fokus-Deep-Link (`#/<sicht>?fokus=<block-id>`) ────────────────────────
// ⚠ Die Proben setzen `window.location.hash` — NICHT `renderMitProvidern({ route })`.
// Der füllt nur `MemoryRouter.initialEntries` und lässt `window.location` unberührt;
// der Hook liest aber den echten Hash (unter `HashRouter` steht die Query dort).

describe('BlockShell — Fokus-Deep-Link (FD-1/FD-5)', () => {
  const URSPRUNG = window.location.hash
  beforeEach(() => { localStorage.clear(); window.location.hash = '' })
  afterEach(() => { window.location.hash = URSPRUNG })

  it('?fokus=b öffnet Block B als Deep-Link-Ansicht — ohne Zurück, ohne Unterzeile', () => {
    window.location.hash = '#/x?fokus=b'
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(screen.queryByText('Fokus / Vollbild')).not.toBeInTheDocument()
  })

  it('ohne ?fokus= bleibt alles wie bisher (lokaler Fokus-State)', () => {
    window.location.hash = '#/x'
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    fireEvent.click(screen.getAllByLabelText('Fokus / Vollbild')[1])
    expect(screen.getByText('Zurück')).toBeInTheDocument()
    // Der Deep-Link schreibt die Adresse NICHT — ⤢ ändert den Hash nicht.
    expect(window.location.hash).toBe('#/x')
  })

  it('?fokus=gibtesnicht ⇒ Hinweis-Overlay OHNE den Schließen-Satz (FD-5 Fall 1)', () => {
    window.location.hash = '#/x?fokus=gibtesnicht'
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} fokusKopf={<p>Zeitraum-Nav</p>} />)
    expect(screen.getByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
    expect(screen.getByText(/nicht für diesen Zeitraum/)).toBeInTheDocument()
    // Kein Ausweg, kein Bestandssatz aus dem normalen Lücken-Tag-Zweig.
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(screen.queryByText(/schließe die Vollansicht/)).not.toBeInTheDocument()
    // Die Sicht dahinter bleibt verdeckt — kein Leerbild, kein normaler Block-Stack.
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    // Die Zeitraum-Nav läuft mit (FD-5 Fall 2: weiterblättern bis Daten da sind).
    expect(screen.getByText('Zeitraum-Nav')).toBeInTheDocument()
  })

  it('Nachzügler: der Block kommt mit dem ZWEITEN Abruf und wird im selben Render fokussiert', () => {
    // Der reale Fall: `co2` auf Cockpit/Jahr, `bilanz` an einem Lücken-Tag. Ein
    // `useState`-Initialisierer hätte hier für immer den Hinweis stehen lassen.
    window.location.hash = '#/x?fokus=c'
    const { rerender } = render(<BlockShell bloecke={[bloecke()[0]]} persistKey={KEY} />)
    expect(screen.getByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
    rerender(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt C')).toBeInTheDocument()
    expect(screen.queryByText(/gibt es in dieser Sicht nicht/)).not.toBeInTheDocument()
  })

  it('… und verschwindet der Block wieder, steht der Hinweis statt des Bestandssatzes', () => {
    window.location.hash = '#/x?fokus=c'
    const { rerender } = render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt C')).toBeInTheDocument()
    rerender(<BlockShell bloecke={[bloecke()[0]]} persistKey={KEY} />)
    expect(screen.getByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
    expect(screen.queryByText(/keine Daten vor/)).not.toBeInTheDocument()
  })

  it('?ansicht=tabelle startet in der Tabellen-Ablesung (CT-5)', () => {
    window.location.hash = '#/x?fokus=b&ansicht=tabelle'
    const mitTabelle: Block[] = [
      { id: 'b', title: 'Block B', defaultOpen: true, render: () => <p>Chart B</p>, renderTabelle: () => <p>Tabelle B</p> },
    ]
    render(<BlockShell bloecke={mitTabelle} persistKey={KEY} />)
    expect(screen.getByText('Tabelle B')).toBeInTheDocument()
    expect(screen.queryByText('Chart B')).not.toBeInTheDocument()
  })

  it('ohne ansicht-Param startet der Deep-Link beim Chart', () => {
    window.location.hash = '#/x?fokus=b'
    const mitTabelle: Block[] = [
      { id: 'b', title: 'Block B', defaultOpen: true, render: () => <p>Chart B</p>, renderTabelle: () => <p>Tabelle B</p> },
    ]
    render(<BlockShell bloecke={mitTabelle} persistKey={KEY} />)
    expect(screen.getByText('Chart B')).toBeInTheDocument()
  })
})
