import { describe, it, expect } from 'vitest'
import { v3RouteZuV4, V3_EINSTELLUNG_ZU_V4_KATEGORIE } from './v3ZuV4Route'
import { EINSTELLUNGEN_KATALOG, EINSTELLUNGEN_KATEGORIEN } from './einstellungenKatalog'

describe('v3RouteZuV4 (V3→V4-Einstellungs-Routen-Map)', () => {
  it('mappt die Daten-Checker-Ziele auf ihren V4-Reiter', () => {
    expect(v3RouteZuV4('/einstellungen/monatsdaten')).toBe('/v4/einstellungen/daten')
    expect(v3RouteZuV4('/einstellungen/energieprofil')).toBe('/v4/einstellungen/daten')
    expect(v3RouteZuV4('/einstellungen/anlage')).toBe('/v4/einstellungen/stammdaten')
    expect(v3RouteZuV4('/einstellungen/strompreise')).toBe('/v4/einstellungen/stammdaten')
    expect(v3RouteZuV4('/einstellungen/solarprognose')).toBe('/v4/einstellungen/stammdaten')
    expect(v3RouteZuV4('/einstellungen/sensor-mapping')).toBe('/v4/einstellungen/integration')
    expect(v3RouteZuV4('/einstellungen/mqtt-inbound')).toBe('/v4/einstellungen/integration')
  })

  it('mappt investitionen auf den datengetriebenen Komponenten-Reiter', () => {
    expect(v3RouteZuV4('/einstellungen/investitionen')).toBe('/v4/einstellungen/komponenten')
  })

  it('normalisiert führenden Slash + Query (Tages-Deep-Link verworfen)', () => {
    expect(v3RouteZuV4('einstellungen/monatsdaten')).toBe('/v4/einstellungen/daten')
    expect(v3RouteZuV4('/einstellungen/energieprofil?datum=2026-06-23')).toBe('/v4/einstellungen/daten')
  })

  it('liefert null für Nicht-Einstellungs-Ziele (Donor ohne V4-Heimat)', () => {
    expect(v3RouteZuV4('/monatsabschluss/1/2026/6')).toBeNull()
    expect(v3RouteZuV4('/live')).toBeNull()
  })

  it('alle Ziel-Kategorien existieren in der Kategorie-Leiste', () => {
    const keys = new Set(EINSTELLUNGEN_KATEGORIEN.map((k) => k.key))
    for (const kategorie of Object.values(V3_EINSTELLUNG_ZU_V4_KATEGORIE)) {
      expect(keys.has(kategorie as never)).toBe(true)
    }
  })

  it('ist konsistent zum Katalog (route→kategorie), kein Drift', () => {
    // Für jede Map-Route, die als route/weitereRouten im Katalog vorkommt, muss die
    // Kategorie mit dem Katalog übereinstimmen. investitionen ist bewusst NICHT im
    // Katalog (datengetriebener Reiter) → ausgenommen.
    for (const [route, kategorie] of Object.entries(V3_EINSTELLUNG_ZU_V4_KATEGORIE)) {
      if (route === 'einstellungen/investitionen') continue
      const eintrag = EINSTELLUNGEN_KATALOG.find(
        (e) => e.route === route || e.weitereRouten?.includes(route),
      )
      if (eintrag) expect(kategorie).toBe(eintrag.kategorie)
    }
  })
})
