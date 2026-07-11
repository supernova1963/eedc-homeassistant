/**
 * Tabellen-SoT (Regel T) — Verhaltens-Gate.
 *
 * Sichert die drei Aussagen ab, an denen der frühere Versuch gescheitert ist:
 * (T2) Höhenfenster existiert und rechnet mit den gemessenen Maßen,
 * (T3) Kopf UND Fuß kleben — was ohne das Fenster wirkungslos wäre,
 * (T4) beide Scroll-Leisten sind sichtbar (kein `scrollbar-none`).
 * jsdom kann Scrollen nicht simulieren; das Wheel-/Sticky-Verhalten am lebenden
 * Objekt prüft die Playwright-Gegenmessung in Slice T-2.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Table, TableBody, TableCell, TableFoot, TableHead, TableHeader, TableRow } from './Table'
import { fensterHoehe, DECKEL, ZEILE_PX, KOPF_PX, FUSS_PX } from './tabelleMasse'

function bau(props: Parameters<typeof Table>[0] extends infer P ? Partial<P> : never = {}) {
  return render(
    <Table {...props}>
      <TableHead>
        <TableRow><TableHeader>Zeitraum</TableHeader></TableRow>
      </TableHead>
      <TableBody>
        <TableRow><TableCell>Apr 2026</TableCell></TableRow>
      </TableBody>
      <TableFoot>
        <TableRow><TableCell>Σ</TableCell></TableRow>
      </TableFoot>
    </Table>,
  )
}

describe('Tabellen-SoT — Regel T', () => {
  it('T2: Fenster = zeilen × ZEILE + KOPF, gedeckelt auf 70dvh', () => {
    expect(fensterHoehe(12, false)).toBe(`min(${12 * ZEILE_PX + KOPF_PX}px, ${DECKEL})`)
    expect(fensterHoehe(24, false)).toBe(`min(${24 * ZEILE_PX + KOPF_PX}px, ${DECKEL})`)
  })

  it('T2: mitFuss reserviert die Höhe der Summenzeile', () => {
    expect(fensterHoehe(12, true)).toBe(`min(${12 * ZEILE_PX + KOPF_PX + FUSS_PX}px, ${DECKEL})`)
  })

  it('T2: das Fenster landet als max-height auf dem SCROLL-Container (nicht auf einem display:contents-Wrapper)', () => {
    const { container } = bau({ zeilen: 12, mitFuss: true })
    const scroller = container.querySelector('div.overflow-auto') as HTMLElement
    expect(scroller).toBeTruthy()
    expect(scroller.style.maxHeight).toBe(fensterHoehe(12, true))
  })

  it('T3: thead klebt oben, tfoot klebt unten', () => {
    const { container } = bau()
    const thead = container.querySelector('thead')!
    const tfoot = container.querySelector('tfoot')!
    expect(thead.className).toContain('sticky')
    expect(thead.className).toContain('top-0')
    expect(tfoot.className).toContain('sticky')
    expect(tfoot.className).toContain('bottom-0')
  })

  it('T3: der deckende Grund liegt auf den ZELLEN, nicht auf thead/tfoot/tr', () => {
    // Regression: `bg-*` auf <thead> wird im Tabellen-Rendermodell beim Sticky
    // nicht gemalt — die Datenzeilen schienen durch (auf der Dev-Box gesehen,
    // von der alten Zusicherung `className).toMatch(/bg-/)` NICHT gefangen).
    const { container } = bau()
    const thead = container.querySelector('thead')!
    const tfoot = container.querySelector('tfoot')!
    for (const el of [thead, tfoot]) {
      expect(el.className).toMatch(/\[&_th\]:bg-/)
      expect(el.className).toMatch(/\[&_td\]:bg-/)
      expect(el.className).toMatch(/dark:\[&_t[hd]\]:bg-/)
      // kein nackter Grund auf dem Sektions-Element selbst
      expect(el.className).not.toMatch(/(^|\s)bg-/)
    }
  })

  it('T3: die Summenzeilen-Betonung kommt aus der Zentrale, nicht vom Aufrufer', () => {
    const { container } = bau()
    const tfoot = container.querySelector('tfoot')!
    expect(tfoot.className).toContain('font-semibold')
    expect(tfoot.className).toContain('border-t-2')
  })

  it('T4: beide Scroll-Leisten sind sichtbar — kein scrollbar-none am Tabellen-Container', () => {
    const { container } = bau()
    const scroller = container.querySelector('div.overflow-auto') as HTMLElement
    expect(scroller.className).not.toContain('scrollbar-none')
  })

  it('T6: eine Zell-Typo — text-sm + py-0.5, Zahlen nowrap', () => {
    const { container } = bau()
    const td = container.querySelector('td')!
    expect(td.className).toContain('py-0.5')
    expect(td.className).not.toContain('py-1.5')
    expect(td.className).toContain('text-sm')
    expect(td.className).toContain('whitespace-nowrap')
  })

  it('T2: 24 Stunden passen auf FullHD unter den Blockkopf — Gernots Vorgabe (2026-07-10)', () => {
    // Startwerte 24×25 + 21 + 25 = 646 px; die WIRKLICHE Höhe misst Table zur
    // Laufzeit aus dem DOM (zweizeiliger Stunden-Kopf ~44 px → real ~673 px).
    // Unter dem Blockkopf bleiben auf FullHD ~715 px — beides passt hinein.
    expect(fensterHoehe(24, true)).toBe(`min(${24 * ZEILE_PX + KOPF_PX + FUSS_PX}px, ${DECKEL})`)
    expect(24 * ZEILE_PX + KOPF_PX + FUSS_PX + 30).toBeLessThanOrEqual(715) // + Kopf-Reserve
    // 12 Monatszeilen: 350 px — passt sogar auf 720 px Höhe.
    expect(fensterHoehe(12, true)).toBe(`min(${12 * ZEILE_PX + KOPF_PX + FUSS_PX}px, ${DECKEL})`)
  })

  it('variante="tkonto" ist eine Variante der Zentrale, kein Sonderfall daneben', () => {
    const { container } = bau({ variante: 'tkonto' })
    const table = container.querySelector('table')!
    expect(table.getAttribute('data-tabelle-sot')).toBe('tkonto')
    expect(table.className).toContain('table-fixed')
  })

  it('rendert den Inhalt', () => {
    bau()
    expect(screen.getByText('Apr 2026')).toBeInTheDocument()
  })
})
