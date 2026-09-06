import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ParkProvider, Parkbar } from '../components/park'
import { FokusKachel } from '../components/blocks/FokusKachel'
import { BlockShell } from '../components/blocks/BlockShell'
import type { Block } from '../components/blocks/types'
import { zaehlerParkIds } from '../components/zaehler/ZaehlerstaendeBlock'
import { top10ParkIds, STAT_PARK_IDS } from '../pages/community/CommunityStatistikenTeile'
import type { Ranking } from '../api/community'
import type { ZaehlerStand } from '../api/zaehlerstaende'

// ── Die VERHALTENS-Hälfte der Park-Doktrin (2026-09-06) ──────────────────────
//
// `check:park-gate` und `check:park-idliste` prüfen den Quelltext: trägt jeder
// Block ein Auto-Hide-Gate, und stimmt jede Gate-Liste mit den Erzeugungsstellen
// überein? Beide können NICHT prüfen, ob die Hülle sich beim Rendern wirklich
// zurücknimmt — genau das steht hier.
//
// ⛔ Beide Hälften gehören zusammen, und getrennt wäre jede von ihnen grün zu
// bekommen, ohne dass die Sache stimmt (dasselbe Argument wie in
// `parkfuss-lade-gate.test.tsx` und `waermepumpeBauartVergleich.test.tsx`):
// Ein Wächter allein sieht Zeichenketten, eine Render-Probe allein sieht nur die
// Stelle, die jemand aufgeschrieben hat.
//
// Diese Datei löst zusammen mit den beiden Wächtern den `check:park-leertest` ab
// (Playwright, 188 s, gegen eine laufende Demo-Box). Er meldete am 2026-09-06
// GRÜN über ein Park-Element, das er nie gesehen hatte: seine Routen-Liste kannte
// eine von sechs Community-Sichten.

const SICHT = 'test-park-huelle'

beforeEach(() => {
  localStorage.clear()
})

function parke(...ids: string[]) {
  localStorage.setItem(SICHT, '')
  localStorage.setItem(
    'eedc-park:' + SICHT,
    JSON.stringify(ids.map((id) => ({ id, titel: id }))),
  )
}

describe('Klasse 3 — die Container-Hülle nimmt sich zurück', () => {
  // Der Fehlertext des abgelösten Leertests nannte sie wörtlich:
  // „leere Container-Hülle (FokusKachel), die sich nicht selbst versteckt".
  function Kachel({ zeige }: { zeige: boolean }) {
    // Das Muster aus `LiveAufEinenBlick`: die Hülle kehrt früh zurück, wenn alle
    // ihre Kinder geparkt sind — sonst bliebe die Karte samt ⤢-Knopf im Bild.
    if (!zeige) return null
    return (
      <FokusKachel titel="Auf einen Blick" zeigeTitel>
        <Parkbar id="live:solar" titel="Solar-Aussicht">
          <p>Solar-Aussicht</p>
        </Parkbar>
      </FokusKachel>
    )
  }

  it('mit Inhalt steht die Kachel im Bild — Gegenprobe zur Regel darunter', () => {
    render(
      <ParkProvider persistKey={SICHT}>
        <Kachel zeige />
      </ParkProvider>,
    )
    expect(screen.getByText('Auf einen Blick')).toBeInTheDocument()
    expect(screen.getByText('Solar-Aussicht')).toBeInTheDocument()
  })

  it('ohne Inhalt bleibt KEINE Hülle stehen — auch nicht der Fokus-Knopf', () => {
    const { container } = render(
      <ParkProvider persistKey={SICHT}>
        <Kachel zeige={false} />
      </ParkProvider>,
    )
    expect(screen.queryByText('Auf einen Blick')).not.toBeInTheDocument()
    // Der ⤢-Knopf ist das, was von einer leeren FokusKachel übrig BLIEBE — er
    // sitzt absolut in der Karte und überlebt jeden leeren Body.
    expect(container.querySelector('button[aria-label*="Fokus / Vollbild"]')).toBeNull()
    expect(container.textContent?.trim()).toBe('')
  })

  it('eine FokusKachel mit geparktem Kind LÄSST die Hülle stehen — der Defekt, den R2 verbietet', () => {
    // Diese Probe belegt, dass die Regel nötig ist: ohne Früh-Return bleibt genau
    // die leere Karte zurück, die der Anwender im Bild sieht.
    parke('live:solar')
    const { container } = render(
      <ParkProvider persistKey={SICHT}>
        <FokusKachel titel="Auf einen Blick" zeigeTitel>
          <Parkbar id="live:solar" titel="Solar-Aussicht">
            <p>Solar-Aussicht</p>
          </Parkbar>
        </FokusKachel>
      </ParkProvider>,
    )
    expect(screen.queryByText('Solar-Aussicht')).not.toBeInTheDocument()
    // …und die Hülle steht trotzdem da. Genau das fängt `check:park-gate` R2.
    expect(screen.getByText('Auf einen Blick')).toBeInTheDocument()
    expect(container.querySelector('button[aria-label*="Fokus / Vollbild"]')).not.toBeNull()
  })
})

describe('Klasse 1 — ein Block ohne Inhalt verschwindet aus der BlockShell', () => {
  const bloecke = (park: (id: string) => boolean): Block[] => {
    const ids = ['el:tabelle']
    return ids.every(park)
      ? []
      : [{ id: 'daten', title: 'Datenblock', render: () => (
          <Parkbar id="el:tabelle" titel="Tabelle"><table><tbody><tr><td>Wert</td></tr></tbody></table></Parkbar>
        ) }]
  }

  it('ungeparkt steht der Block da', () => {
    render(
      <ParkProvider persistKey={SICHT}>
        <BlockShell persistKey={SICHT} bloecke={bloecke(() => false)} />
      </ParkProvider>,
    )
    expect(screen.getByText('Datenblock')).toBeInTheDocument()
  })

  it('sind alle Elemente geparkt, ist der Block weg — nicht leer', () => {
    render(
      <ParkProvider persistKey={SICHT}>
        <BlockShell persistKey={SICHT} bloecke={bloecke(() => true)} />
      </ParkProvider>,
    )
    expect(screen.queryByText('Datenblock')).not.toBeInTheDocument()
  })
})

describe('Klasse 2 — die ID-Liste folgt den Daten (die zwei Befunde vom 2026-09-06)', () => {
  // Beide Funktionen sind an diesem Tag entstanden, weil `check:park-idliste`
  // (Regel L2) je eine FESTE Liste fand, deren zweite ID nur bedingt gerendert
  // wird. Ohne sie blieb der Block leer-aber-sichtbar stehen.

  const stand = (punkte: number): ZaehlerStand => ({
    investition_id: 1, name: 'Gaszähler', art: 'gas', einheit: 'm³',
    stand_anfang: 10, stand_ende: 20, verbrauch: 10,
    verlauf: Array.from({ length: punkte }, (_, i) => ({ datum: `2026-0${i + 1}-01`, stand: i })),
  } as unknown as ZaehlerStand)

  it('ein Zähler OHNE Verlauf nennt nur die Tabellen-ID', () => {
    // Der Defekt: `verlauf.length > 1` ist falsch ⇒ die Verlauf-Parkbar rendert
    // nie ⇒ eine feste Zwei-Element-Liste wird nie vollständig geparkt.
    expect(zaehlerParkIds([stand(1)])).toEqual(['el:zaehlerstaende'])
  })

  it('ein Zähler MIT Verlauf nennt beide', () => {
    expect(zaehlerParkIds([stand(3)])).toEqual(['el:zaehlerstaende', 'el:zaehlerstaende-verlauf'])
  })

  it('ohne Zählerstände gar keine ID — der Block rendert `null`', () => {
    expect(zaehlerParkIds([])).toEqual([])
  })

  const ranking = (eigener: number | null): Ranking => ({
    ranking: [{ rang: 1, spez_ertrag: 1000 }],
    eigener_rang: eigener,
    eigener_wert: eigener ? 900 : null,
  } as unknown as Ranking)

  it('wer NICHT in den Top 10 steht, hat keine „Dein Rang"-ID', () => {
    // Der Normalfall — und bis zum 2026-09-06 der Fall, in dem der Block
    // „Top 10 – Spezifischer Ertrag" leer stehen blieb.
    expect(top10ParkIds(ranking(null))).toEqual(['stat-top10-tabelle'])
  })

  it('wer drinsteht, hat sie', () => {
    expect(top10ParkIds(ranking(4))).toEqual(['stat-top10-tabelle', 'stat-top10-eigener'])
  })

  it('die feste Liste trägt die bedingte ID NICHT mehr', () => {
    // Gegenprobe zur Regel L2: stünde sie wieder drin, wäre der Fund zurück.
    expect([...STAT_PARK_IDS.top10]).toEqual(['stat-top10-tabelle'])
  })
})
