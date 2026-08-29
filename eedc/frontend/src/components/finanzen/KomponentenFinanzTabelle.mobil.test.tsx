/**
 * Komponenten-Finanzen auf dem Handy — Karten statt Tabelle (N-149).
 *
 * Die mobile Hälfte stand bis zum 2026-08-29 als **Handnachbau** in der Datei
 * und ist jetzt auf den SoT `components/ui/MobilKarte` umgehängt. Diese Datei
 * ist die Gegenprobe dazu: sie hält fest, **was auf der Karte steht**, nicht
 * dass eine Komponente importiert wurde.
 *
 * ⚑ **Warum das der springende Punkt ist.** `check:mobilkarte` beweist nur, dass
 * es EINEN Bauort gibt — er bliebe grün, wenn die Karte ihre Zahlen verlöre.
 * Beim N-274-Bau blieben elf von dreizehn Proben unter dem Sprengsatz grün,
 * weil sie den ausgewiesenen statt den gerechneten Wert prüften. Hier prüfen
 * deshalb beide Richtungen: die Werte **stehen** auf der Karte, und die Karte
 * ist **nicht** die Tabelle (jsdom kennt keine Media-Queries, also stehen beide
 * Render-Pfade im DOM — die Trennung ist an den Klassen abzulesen).
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { KomponentenFinanzTabelle } from './KomponentenFinanzTabelle'
import { aktuellerMonat } from '../../test/factories'
import type { InvestitionFinancialDetail } from '../../api/aktuellerMonat'

const speicher = (over: Partial<InvestitionFinancialDetail> = {}): InvestitionFinancialDetail =>
  ({
    investition_id: 7,
    bezeichnung: 'Hausspeicher',
    typ: 'speicher',
    erloes_euro: 0,
    sonstige_ertraege_euro: 0,
    ersparnis_euro: 41.5,
    betriebskosten_monat_euro: 3.25,
    sonstige_ausgaben_euro: 0,
    ersparnis_label: 'Speicher-Ersparnis',
    formel: null,
    berechnung: null,
    ...over,
  }) as InvestitionFinancialDetail

const zeige = (over = {}) =>
  render(
    <KomponentenFinanzTabelle
      d={aktuellerMonat(2026, 7, {
        einspeise_erloes_euro: 62.4,
        ev_ersparnis_euro: 118.9,
        investitionen_financials: [speicher()],
        ...over,
      })}
    />,
  ).container

/** Der Kartenpfad — `sm:hidden`; die Tabelle daneben ist `hidden sm:block`. */
const karten = (c: HTMLElement) => c.querySelector('div.sm\\:hidden')

describe('Komponenten-Finanzen mobil — die Karten tragen dieselben Zahlen (N-149)', () => {
  it('beide Render-Pfade stehen im DOM — der Inhalt wird nicht weggenommen (M1)', () => {
    const c = zeige()
    expect(karten(c)).not.toBeNull()
    expect(c.querySelector('table')).not.toBeNull()
  })

  it('je Komponente eine Karte mit Kopf, Saldo und den drei Spalten', () => {
    const t = karten(zeige())!.textContent!

    // Kopf + Saldo: 62,40 + 118,90 − 0 = 181,30 für die PV-Zeile
    expect(t).toContain('PV-Anlage')
    expect(t).toContain('181,30 €')

    // Die drei Wertspalten stehen als Labels auf der Karte
    expect(t).toContain('Erträge')
    expect(t).toContain('Einsparung')
    expect(t).toContain('Aufwand')

    // ... und tragen die Zahlen der Tabellenzeile
    expect(t).toContain('62,40')
    expect(t).toContain('118,90')
  })

  it('die zweite Karte trägt die Komponente samt anteiliger Betriebskosten', () => {
    const t = karten(zeige())!.textContent!
    expect(t).toContain('Hausspeicher')
    expect(t).toContain('41,50')
    expect(t).toContain('3,25')
    // Unterzeile aus `hinweis` — sie ging beim Handnachbau leicht verloren
    expect(t).toContain('Betriebskosten anteilig')
  })

  it('die Summenkarte nennt den Gesamtsaldo', () => {
    // 181,30 (PV) + 41,50 − 3,25 (Speicher) = 219,55
    const t = karten(zeige())!.textContent!
    expect(t).toContain('Summe (Saldo)')
    expect(t).toContain('219,55 €')
  })

  it('ein fehlender Wert steht als Strich, nicht als 0,00', () => {
    // Aufwand der PV-Zeile ist 0 ⇒ „—" (die `z.aufwand ? … : '—'`-Regel).
    const t = karten(zeige())!.textContent!
    expect(t).toMatch(/Aufwand—/)
  })
})
