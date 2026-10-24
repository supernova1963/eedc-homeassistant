/**
 * Bauschnitt 7 — der Hinweis „Gesamtleistung verdrängt die Aufteilung" auf der
 * Zuordnungs-Fläche (Konzept Wärme/Klima §4 Tag ③, §5 Position 1).
 *
 * Zwei Dinge hält diese Datei fest, und beide sind an einer Messung gelernt:
 *
 * ⛔ **Die Zeile darf KEINEN „auf keine setzen"-Knopf tragen.** Den rendert die
 * Fläche für `art: 'redundant'`, und sein Handler leert **das Feld der Zeile** —
 * der Hinweis hängt aber am *verdrängten* Feld, der Knopf würde also die
 * Aufteilung löschen statt der Gesamtleistung (Gegenprüfung 12.09.2026).
 *
 * ⭐ **`info` ist blau und trägt das Info-Symbol**, beides aus der Stil-SoT: Es
 * liegt kein Fehler vor. Amber steht auf dieser Fläche für Zuordnungs-Probleme.
 *
 * P-433-2 S2 (Variante C): «Leistung gesamt» steht im Block «Gerät gesamt», «Leistung Heizen» im
 * Block «Heizen» — der Hinweis hängt weiter am verdrängten Feld, also im Block Heizen.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'

// ⚠ `vi.mock` wird an den Dateianfang gehoben — eine gewöhnliche Konstante ist
// in der Fabrik noch nicht initialisiert (gemessen: „Cannot access 'HINWEIS'
// before initialization"). `vi.hoisted` ist der vorgesehene Weg; so steht der
// Satz trotzdem nur EINMAL, statt in Fixture und Erwartung zu driften.
const { HINWEIS } = vi.hoisted(() => ({
  // Spiegel von `backend/services/datenquellen_validierung._GESAMTLEISTUNG_TEXT`.
  // ⭐ „Leistung Kühlen“ steht seit dem 13.09.2026 mit im Satz (N-439): Seit das
  // Feld eine eigene Verlaufs-Fläche erzeugt, wird auch es von der
  // Gesamtleistung verdrängt — ein Hinweis an zwei von drei gleich behandelten
  // Feldern wäre die Lücke, gegen die SOLL §3.3/S3 steht.
  HINWEIS:
    'Solange „Leistung gesamt“ zugeordnet ist, wertet eedc „Leistung Heizen“, '
    + '„Leistung Warmwasser“ und „Leistung Kühlen“ im Verlauf nicht aus.',
}))

vi.mock('../../api/datenquellen', () => {
  const gesamt = {
    id: 'inv_live_7_leistung_w', feld: 'leistung_w', typ: 'waermepumpe',
    label: 'Leistung gesamt', einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: '', quelle: 'ha_app', gateway_topic: null,
    ha_entity: 'sensor.wp_gesamt', ha_name: 'WP gesamt',
    invertieren: false, wert: 800, wert_zeit: null, probleme: [], betriebsart: 'geraet',
  }
  const heizen = {
    id: 'inv_live_7_leistung_heizen_w', feld: 'leistung_heizen_w', typ: 'waermepumpe',
    label: 'Leistung Heizen', einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: '', quelle: 'ha_app', gateway_topic: null,
    ha_entity: 'sensor.wp_heizen', ha_name: 'WP Heizen',
    invertieren: false, wert: 600, wert_zeit: null, betriebsart: 'heizen',
    probleme: [{
      art: 'gesamtleistung_verdraengt', schwere: 'info', grund: 'gesamtleistung',
      wirksame_felder: ['inv_live_7_leistung_w'], text: HINWEIS,
    }],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        // ⚠ Die Fläche liest `g.titel`, nicht `label` — mit dem falschen
        // Schlüssel rendert nur der Gruppenkopf, und kein Feld erscheint
        // (gemessen 12.09.2026 am DOM dieser Probe).
        gruppen: [{ id: 'inv:7', titel: 'Wärmepumpe', typ: 'waermepumpe', felder: [gesamt, heizen] }],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
      })),
      setQuelle: vi.fn(() => Promise.resolve()),
      setInvert: vi.fn(() => Promise.resolve()),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

// ⚠ Der Satz steht in einem `<span>`, das auch den Knopf-Slot trägt — ein
// **exakter** Matcher findet ihn deshalb nicht („text is broken up by multiple
// elements", gemessen). Die Hausform dieser Fläche ist ein Regex auf einem
// Teilstück (`DatenquellenBedarf.test.tsx`, `…erweiterung.test.tsx`); ein
// eigener Funktions-Matcher war mein Umweg und hat auch nicht getroffen.
const hinweisKnoten = () => screen.findByText(/wertet eedc .Leistung Heizen./)

/**
 * ⚠ **Der Geräte-Block ist zugeklappt** — `defaultOpen: istBasis`
 * (`DatenquellenZuordnung.tsx`), und eine Wärmepumpe ist kein Basis-Block.
 * Gemessen: ohne Klick trägt das DOM 466 Zeichen, nämlich Gruppenkopf und
 * „1 Gerät" — **kein Feld und keinen Hinweis**. Die Schwesterproben dieser
 * Fläche kommen ohne Klick aus, weil sie `typ: 'basis'` fahren; das war die
 * Falle. Erst aufklappen, dann prüfen.
 */
async function oeffneWpBlock() {
  render(<DatenquellenZuordnung />)
  // Die Block-Hülle bietet dafür einen eigenen Schalter — verlässlicher als ein
  // Klick auf den Titel, dessen Trefferfläche eine Annahme wäre.
  fireEvent.click(await screen.findByText(/alle aufklappen/))
}

describe('Bauschnitt 7 — Hinweis an der verdrängten Zuordnung', () => {
  it('zeigt den Satz am Feld „Leistung Heizen"', async () => {
    await oeffneWpBlock()
    expect(await hinweisKnoten()).toBeInTheDocument()
  })

  it('steht im Block «Heizen» (Variante C), die Gesamtleistung im Block «Gerät gesamt»', async () => {
    await oeffneWpBlock()
    const knoten = await hinweisKnoten()
    expect(knoten.closest('[data-betriebsart]')?.getAttribute('data-betriebsart')).toBe('heizen')
    expect(screen.getByText('Leistung gesamt (W)').closest('[data-betriebsart]')?.getAttribute('data-betriebsart')).toBe('geraet')
  })

  it('DER KERN: keine Schaltfläche, die das falsche Feld leeren würde', async () => {
    await oeffneWpBlock()
    await hinweisKnoten()

    expect(screen.queryByRole('button', { name: /auf keine setzen/i })).toBeNull()
  })

  it('trägt den Info-Ton, nicht die Warnfarbe', async () => {
    await oeffneWpBlock()
    const zeile = (await hinweisKnoten()).closest('div')

    expect(zeile?.className).toContain('text-blue-500')
    expect(zeile?.className).not.toContain('amber')
  })

  it('… und das Info-SYMBOL, nicht das Warndreieck', async () => {
    // ⚑ **Diese Probe fehlte, und ein Sprengsatz hat es gezeigt:** Der Tausch
    // des Symbols gegen `AlertTriangle` ließ alle drei Proben grün — ein
    // blauer Text unter einem Warndreieck wäre die halbe Übernahme der SoT
    // (Regel 0a verlangt Ton UND Symbol).
    await oeffneWpBlock()
    const zeile = (await hinweisKnoten()).closest('div')

    expect(zeile?.querySelector('svg.lucide-info')).not.toBeNull()
    expect(zeile?.querySelector('svg.lucide-triangle-alert, svg.lucide-alert-triangle')).toBeNull()
  })
})
