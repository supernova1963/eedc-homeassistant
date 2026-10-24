/**
 * Datenquellen-Zuordnung — die anderen Typen bleiben, wie sie sind (P-433-2 S2, Reichweite E3).
 *
 * Variante C (#431) bündelt die Felder einer **Wärmepumpe** nach Betriebsart. Für jeden anderen
 * Typ bleiben die Abschnitte nach Einheit (kWh · W · Sonstige) und «Weitere Größen erfassen»
 * unverändert. Diese Probe hält das fest: die ganze Fläche mit Basis, zwei Speichern, Wallbox und
 * E-Auto, alle Blöcke und alle «Weitere Größen»-Schalter aufgeklappt, als HTML gegen eine Datei —
 * **erzeugt am Code vor E3** (HEAD `0edd0cfb`), danach gleich.
 *
 * Wer die Fläche für diese Typen absichtlich ändert, schreibt die Datei neu und schickt den Diff mit:
 *
 *     cd eedc/frontend && EEDC_DQ_SNAPSHOT=schreiben npx vitest run src/components/live/DatenquellenZuordnung.andere-typen.test.tsx
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import DatenquellenZuordnung from './DatenquellenZuordnung'

const SNAPSHOT = join(process.cwd(), 'src', 'test', 'datenquellen-andere-typen.snapshot.html')
const SCHREIBEN = process.env.EEDC_DQ_SNAPSHOT === 'schreiben'

vi.mock('../../api/datenquellen', () => {
  let n = 0
  const feld = (gid: string, feld: string, label: string, einheit: string, extra: Record<string, unknown> = {}) => ({
    id: `${gid}_${feld}_${n++}`, feld, typ: gid.startsWith('inv') ? 'x' : 'basis',
    label, einheit, kategorie: einheit === 'kWh' ? 'energy' : 'live',
    hinweis: `Hinweis zu ${label}`, standard_topic: `eedc/1/${gid}/${feld}`,
    quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null, ausgewertet_in: [],
    ...extra,
  })
  const ha = (entity: string, wert: number) => ({ quelle: 'ha_app', ha_entity: entity, ha_name: `Name ${entity}`, wert })
  const gruppen = [
    { id: 'basis', titel: 'Anlage (Basis)', typ: 'basis', felder: [
      feld('basis', 'einspeisung_kwh', 'Einspeisung Zählerstand', 'kWh', { ...ha('sensor.einsp', 1234.5678), bedarf: 'pflicht' }),
      feld('basis', 'netzbezug_kwh', 'Netzbezug Zählerstand', 'kWh', { bedarf: 'pflicht' }),
      feld('basis', 'netz_kombi_w', 'Netz kombiniert (±)', 'W', { ...ha('sensor.netz', -250), invertieren: true }),
      feld('basis', 'aussentemperatur_c', 'Außentemperatur', '°C'),
    ] },
    { id: 'inv:3', titel: 'BYD HVS', typ: 'speicher', felder: [
      feld('inv3', 'ladung_kwh', 'Ladung', 'kWh', { ...ha('sensor.lad', 10), ausgewertet_in: ['Cockpit → Monat'] }),
      feld('inv3', 'entladung_kwh', 'Entladung', 'kWh', { bedarf: 'pflicht' }),
      feld('inv3', 'ladung_netz_kwh', 'Ladung aus Netz', 'kWh', { erweitert: true }),
      feld('inv3', 'leistung_w', 'Leistung', 'W', { quelle: 'mqtt_inbound_standard' }),
      feld('inv3', 'soc', 'Ladestand', '%', { quelle: 'mqtt_gateway', gateway_topic: 'fremd/soc', wert: 55 }),
    ] },
    { id: 'inv:8', titel: 'Zweitspeicher', typ: 'speicher', felder: [
      feld('inv8', 'ladung_kwh', 'Ladung', 'kWh', { probleme: [{ art: 'einheit', schwere: 'error', text: 'Einheit passt nicht' }] }),
      feld('inv8', 'soc', 'Ladestand', '%'),
    ] },
    { id: 'inv:6', titel: 'go-eCharger', typ: 'wallbox', felder: [
      feld('inv6', 'ladung_kwh', 'Ladung', 'kWh', { bedarf: 'inaktiv', bedarf_text: 'Wird über das E-Auto erfasst' }),
      feld('inv6', 'leistung_w', 'Leistung', 'W', ha('sensor.wb', 7400)),
      feld('inv6', 'ladevorgaenge', 'Ladevorgänge', '', { erweitert: true }),
    ] },
    { id: 'inv:4', titel: 'VW ID.4', typ: 'e-auto', felder: [
      feld('inv4', 'km_gefahren', 'Gefahrene km', 'km'),
      feld('inv4', 'soc', 'Ladestand', '%', ha('sensor.id4', 80)),
    ] },
  ]
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        anlage_id: 1, gruppen, verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' }, historie_hinweis: null,
      })),
      setQuelle: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
      setInvert: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

describe('P-433-2 S2 — Zuordnung anderer Typen unverändert', () => {
  it('rendert Basis, Speicher, Wallbox und E-Auto wie vor Variante C', async () => {
    localStorage.clear()
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    // Jedes Gerät aufklappen (bei mehreren Geräten je Typ sind sie zugeklappt) …
    for (const t of [/BYD HVS/, /Zweitspeicher/]) fireEvent.click(screen.getAllByRole('button', { name: t })[0])
    // … und jede «Weitere Größen erfassen»-Stufe.
    for (const b of screen.getAllByRole('button', { name: /Weitere Größen erfassen/ })) fireEvent.click(b)
    const html = container.innerHTML
    expect(html).toContain('Ladung aus Netz')
    expect(html).toContain('Ladevorgänge')
    if (SCHREIBEN || !existsSync(SNAPSHOT)) {
      writeFileSync(SNAPSHOT, html + '\n')
      if (!SCHREIBEN) throw new Error(`Snapshot fehlte und wurde geschrieben: ${SNAPSHOT} — Lauf wiederholen`)
    }
    expect(html + '\n').toBe(readFileSync(SNAPSHOT, 'utf8'))
  })
})
