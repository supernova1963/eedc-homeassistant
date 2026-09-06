import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Users } from 'lucide-react'
import EmptyState from './EmptyState'

// SoT „Leere Sichten erklären sich" (v4.0.4): eine Sicht ohne Daten nennt den GRUND, statt
// stumm leer zu bleiben.
//
// ⛔ Diese Datei prüfte bis zum 2026-09-06 zusätzlich das DOM-Merkmal `data-leer-erklaert`
// (N-318) — den Vertrag mit `check:park-leertest`. Beide sind entfallen: der Prüfer ist
// durch `check:park-gate` + `check:park-idliste` ersetzt, das Merkmal damit ein Vertrag
// ohne Gegenpartei (Entscheid Gernot). **Die Doktrin selbst ist geblieben** und wird hier
// weiter gemessen — an dem, was der Anwender sieht, statt an einem Attribut für einen
// Prüfer, den es nicht mehr gibt.
describe('EmptyState (SoT „Leere Sichten erklären sich", v4.0.4)', () => {
  it('zeigt Titel und Grund — die leere Sicht erklärt sich', () => {
    render(<EmptyState icon={Users} title="Noch keine Anlage" description="Lege zuerst eine an." />)
    expect(screen.getByText('Noch keine Anlage')).toBeInTheDocument()
    expect(screen.getByText('Lege zuerst eine an.')).toBeInTheDocument()
  })
})
