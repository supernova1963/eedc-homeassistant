/**
 * Cockpit/Monat — die Rail sieht dieselben Monate wie die Sicht (Melder
 * kaba-kakao, Forum T89667/98).
 *
 * Gemeldete Lage: die Sicht zeigt „Jul 2026 · abgeschlossen" mit vollen Werten,
 * die Rail daneben führt als **einzigen** Eintrag „Aug · läuft". Ursache war
 * nicht fehlende Historie, sondern zwei Quellen für eine Auswahl:
 *
 *   Rail   ← `energieProfilApi.getVerfuegbareMonate` = GROUP BY über
 *            `TagesZusammenfassung`, also die reine **Tagesebene**
 *   Sicht  ← `monatsdatenApi.listAggregiert` = **Monats-Fakten**
 *
 * Wer eedc über Monatsabschlüsse oder Import pflegt (der Standalone-Kernfall,
 * und bei ihm zusätzlich: Standalone-Container ohne HA-LTS-Zugriff, also gar
 * keine Tagesebene), bekam damit eine Rail mit genau einem Eintrag — dem
 * laufenden Monat, den der Client bedingungslos nachschiebt. Der angezeigte
 * Monat fehlte in seiner eigenen Auswahlliste.
 *
 * Cockpit → **Jahr** wurde von derselben Klasse mit N-68 + N-121 geheilt
 * (`CockpitJahrVerlaufLuecke.test.tsx`); die Monats-Rail blieb zurück. Diese
 * Datei ist zugleich der **erste** Test, der `CockpitMonatV4` überhaupt mountet
 * — genau deshalb konnte der Fehler so lange leben.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen } from '@testing-library/react'

/** Systemzeit: 5. August 2026 — der laufende Monat ist August. */
const HEUTE = new Date(2026, 7, 5, 12, 0, 0)

/** Seine Lage: Monatsdaten seit 2021 importiert, jüngster Abschluss Juli 2026. */
const IMPORTIERT: Array<[number, number, number]> = [
  [2026, 7, 1097],
  [2026, 6, 1240],
  [2025, 12, 310],
]

const zeile = (jahr: number, monat: number, pv: number) =>
  monatsZeile(jahr, monat, {
    pv_erzeugung_kwh: pv, eigenverbrauch_kwh: pv / 2, direktverbrauch_kwh: pv / 4,
    einspeisung_kwh: pv / 2, netzbezug_kwh: 50, gesamtverbrauch_kwh: pv / 2 + 50,
    autarkie_prozent: 80, netzbezug_preis_cent: 40,
  })

const ALLE = IMPORTIERT.map(([j, m, pv]) => zeile(j, m, pv))

/** Verhält sich wie die Route: die Flags erweitern die Grundgesamtheit, sie
 *  verändern hier keine Werte. Ignorierte der Mock sie, wäre der Test
 *  grün-falsch — er würde die Umstellung gar nicht bemerken. */
const listAggregiert = vi.fn(
  (_id: number, _jahr?: number, _opts?: { inklOhneZaehlerzeile?: boolean; inklNurTageswerte?: boolean }) =>
    Promise.resolve(ALLE),
)

/** ⚠ Der Kern der Fixture: **leer**. Er hat keine einzige TagesZusammenfassung
 *  (Standalone-Container, kein HA-LTS-Zugriff, Import legt keine Tagesebene an). */
const getVerfuegbareMonate = vi.fn(() => Promise.resolve([] as Array<{ jahr: number; monat: number; tage: number }>))

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: {
    listAggregiert: (...a: [number, number?, { inklOhneZaehlerzeile?: boolean; inklNurTageswerte?: boolean }?]) =>
      listAggregiert(...a),
  },
}))
vi.mock('../api/energie_profil', () => ({
  energieProfilApi: {
    getVerfuegbareMonate: () => getVerfuegbareMonate(),
    getTageWerte: vi.fn(() => Promise.resolve([])),
    getMonat: vi.fn(() => Promise.resolve(null)),
  },
}))
vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: {
    getData: (_id: number, jahr: number, monat: number) => Promise.resolve(
      aktuellerMonat(jahr, monat, {
        anlage_name: 'Demo', monat_name: String(monat),
        netzbezug_preis_cent: 40, einspeise_preis_cent: 8.2,
        pv_erzeugung_kwh: 1097, einspeisung_kwh: 500, netzbezug_kwh: 50,
        eigenverbrauch_kwh: 550, direktverbrauch_kwh: 250,
        gesamtverbrauch_kwh: 600, autarkie_prozent: 80, eigenverbrauch_quote_prozent: 50,
      }),
    ),
  },
}))

import CockpitMonatV4 from './CockpitMonatV4'
import { renderMitProvidern, stubMatchMedia } from '../test/render'
import { aktuellerMonat, monatsZeile } from '../test/factories'

function renderView() {
  return renderMitProvidern(<CockpitMonatV4 anlageId={1} />, { route: '/v4/cockpit/monat' })
}

describe('Cockpit/Monat — Rail und Sicht teilen die Grundgesamtheit (T89667/98)', () => {
  beforeEach(() => {
    localStorage.clear()
    listAggregiert.mockClear()
    getVerfuegbareMonate.mockClear()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(HEUTE)
    stubMatchMedia()
  })
  afterEach(() => { vi.useRealTimers() })

  it('fragt die volle Grundgesamtheit ausdrücklich mit an', async () => {
    renderView()
    await screen.findByTitle('Aug 2026 — laufender Monat')
    // Beide Flags, wie Cockpit → Jahr seit N-68/N-121. `inklOhneZaehlerzeile`
    // allein reicht nicht: ein Monat, dessen einzige Spur die Tagesebene ist,
    // braucht zusätzlich `inklNurTageswerte`.
    expect(listAggregiert).toHaveBeenCalledWith(1, undefined, {
      inklOhneZaehlerzeile: true,
      inklNurTageswerte: true,
    })
  })

  it('der importierte Monat steht in der Rail, obwohl es keine Tagesebene gibt', async () => {
    renderView()
    // Das ist der gemeldete Fehler: bis v4.0.9 stand hier NUR „Aug · läuft",
    // während die Sicht daneben den Juli mit 1.097 kWh darstellte.
    expect(await screen.findAllByTitle('Jul 2026: 1.097 kWh')).not.toHaveLength(0)
    expect(await screen.findAllByTitle('Jun 2026: 1.240 kWh')).not.toHaveLength(0)
    expect(await screen.findAllByTitle('Dez 2025: 310 kWh')).not.toHaveLength(0)
  })

  it('der laufende Monat bleibt erhalten und behält seine „läuft"-Marke', async () => {
    // Gegenprobe zur Erweiterung: der synthetisch nachgeschobene Eintrag darf
    // durch die neue Quelle weder verschwinden noch doppelt erscheinen.
    renderView()
    const laufend = await screen.findAllByTitle('Aug 2026 — laufender Monat')
    expect(laufend).not.toHaveLength(0)
    expect(screen.queryAllByTitle('Aug 2026: 0 kWh')).toHaveLength(0)
  })

  it('REGRESSION: ein Monat, den NUR die Tagesebene kennt, bleibt in der Rail', async () => {
    // Die Vereinigung darf nicht in die andere Richtung kippen: wer seine Daten
    // ausschließlich über die Tagesebene hat (HA-Add-on ohne Monatsabschluss),
    // muss seine Monate weiterhin sehen. Deshalb Vereinigung statt Ersetzung.
    getVerfuegbareMonate.mockReturnValueOnce(
      Promise.resolve([{ jahr: 2026, monat: 5, tage: 31 }]),
    )
    renderView()
    expect(await screen.findAllByTitle('Mai 2026: 0 kWh')).not.toHaveLength(0)
  })
})
