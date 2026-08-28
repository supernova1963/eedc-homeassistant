import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueTagAlsMonat } from './TagKomponenten'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { TagDetail } from '../api/energie_profil'
import { tagWerte } from '../test/factories'

/**
 * **Der Tag nennt seine Geräte** — SOLL Wärme/Klima §3.3/**S3**.
 *
 * *„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt warum."*
 *
 * ## Was hier schiefging und warum es unsichtbar blieb
 *
 * Der `GeraeteHinweis` („Aggregiert aus: …") hängt an `komponenten_geraete` und
 * erscheint ab **zwei** Geräten. Monat und Jahr füllten das Feld, der Tag als
 * einzige der drei Sichten **gar nicht** — `baueTagAlsMonat` reichte es nicht
 * durch, und die Tages-Route lieferte es nicht.
 *
 * ⭐ **Ein fehlender Hinweis sieht nicht aus wie eine Lücke.** Er sieht aus wie
 * die Aussage „hier steckt genau ein Gerät drin". Genau so hat es
 * **dietmar1968** gelesen (Forum T89667 #221/#226/#237): Er betreibt eine
 * Luft-Wasser-Wärmepumpe **und** eine Split-Klimaanlage; beide sind
 * `typ="waermepumpe"` und zählen deshalb in denselben Tagesbalken. Er verglich
 * diesen Balken mit dem Zähler **einer** der beiden Anlagen und schrieb:
 * *„Er vermengt vermutlich die Anlagen miteinander. Anders kann ich es mir
 * nicht erklären."* — Er hatte recht, und niemand hatte es ihm gesagt.
 *
 * ⚠ **Nicht geprüft wird hier, ob die Mengen getrennt werden — sie werden es
 * bewusst nicht** (SOLL §5: Mengen dürfen nebeneinander stehen, nur eine
 * gemeinsame *Kennzahl* nicht). Die Kennzahl-Sperre liegt im Backend
 * (`GRUND_BAUARTEN_GEMISCHT`, `test_soll_waerme_klima_simulation_anlagen.py`
 * §A8); hier steht ausschließlich die **Auskunft**.
 */

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const ZWEI_GERAETE = { waermepumpe: ['Bosch Wärmepumpe', 'Bosch Klimaanlage'] }

/** Ein Tag mit WP-Strom — sonst entsteht der Block gar nicht. */
function tagMit(detail: Partial<TagDetail> | null) {
  return baueTagAlsMonat(
    tagWerte('2026-08-27', { wp_strom: 11.0 }),
    [], [], detail as TagDetail | null,
  )
}

describe('Tagessicht — die Geräte hinter der Summe', () => {
  it('reicht komponenten_geraete aus dem Tages-Endpoint durch', () => {
    const d = tagMit({ komponenten_geraete: ZWEI_GERAETE })
    expect(d.komponenten_geraete).toEqual(ZWEI_GERAETE)
  })

  it('nennt beide Geräte im Block, statt eine Summe unkommentiert zu zeigen', () => {
    const d = tagMit({ komponenten_geraete: ZWEI_GERAETE })
    const block = baueKomponentenBloecke(d, NOOP, 'tag')
      .find((b) => b.id === 'k-waermepumpe')
    expect(block, 'Wärme/Klima-Block muss am Tag entstehen').toBeDefined()
    render(<>{block!.render(false)}</>)

    // Der Hinweis ist eine EINZELNE Zeile mit beiden Namen — deshalb über den
    // gemeinsamen Text gesucht und nicht über zwei Einzeltreffer, die auch
    // aus zwei getrennten Blöcken stammen könnten.
    const zeile = screen.getByText(/Aggregiert aus/)
    expect(zeile.textContent).toContain('Bosch Wärmepumpe')
    expect(zeile.textContent).toContain('Bosch Klimaanlage')
  })

  it('schweigt bei EINEM Gerät — der Hinweis ist keine Dauer-Dekoration', () => {
    // ⛔ Die Gegenprobe zur Probe darüber. Ohne sie wäre nicht gezeigt, dass
    // die Zeile etwas *aussagt*: Ein Hinweis, der immer steht, trägt keine
    // Information. `GeraeteHinweis` rendert ab zwei Namen (minAnzahl = 2).
    const d = tagMit({ komponenten_geraete: { waermepumpe: ['Bosch Wärmepumpe'] } })
    const block = baueKomponentenBloecke(d, NOOP, 'tag')
      .find((b) => b.id === 'k-waermepumpe')
    render(<>{block!.render(false)}</>)

    expect(screen.queryByText(/Aggregiert aus/)).toBeNull()
  })

  it('bleibt ohne Tagesdetail heil — ein leeres Feld ist kein Absturz', () => {
    // Die Tages-Route liefert `tagDetail` nur, wenn die snapshot-teuren Werte
    // erhoben werden konnten. Der Adapter muss den Fall tragen, ohne dass der
    // Block verschwindet oder wirft.
    const d = tagMit(null)
    expect(d.komponenten_geraete).toEqual({})
    expect(() => baueKomponentenBloecke(d, NOOP, 'tag')).not.toThrow()
  })
})
