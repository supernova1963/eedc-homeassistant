import { describe, it, expect } from 'vitest'
import {
  EINSTELLUNGEN_KATALOG, EINSTELLUNGEN_KATEGORIEN, alleAbgedecktenRouten,
  eintraegeDerKategorie, sucheEintraege,
} from './einstellungenKatalog'

// Routen-Inventur (Akzeptanzkriterium §7): jede IST-`/einstellungen/*`-Route aus
// App.tsx muss von einem Katalog-Eintrag abgedeckt sein — keine verlorene Funktion.
// `einstellungen/investitionen` fehlt bewusst im STATISCHEN Katalog: die Geräte-
// Verwaltung ist der datengetriebene Reiter „Komponenten" (P8, Gernot 2026-07-02) —
// ein Block pro Investitionstyp, zur Laufzeit aus investitionenApi, ohne Katalog-Eintrag.
const IST_ROUTEN = [
  'einstellungen/anlage', 'einstellungen/strompreise',
  'einstellungen/infothek', 'einstellungen/solarprognose', 'einstellungen/monatsdaten',
  'einstellungen/energieprofil', 'einstellungen/daten-checker', 'einstellungen/einrichtung',
  'einstellungen/import', 'einstellungen/portal-import', 'einstellungen/cloud-import',
  'einstellungen/custom-import', 'einstellungen/connector', 'einstellungen/mqtt-inbound',
  'einstellungen/sensor-mapping', 'einstellungen/ha-statistik-import', 'einstellungen/ha-export',
  'einstellungen/backup', 'einstellungen/allgemein', 'einstellungen/protokolle',
  'einstellungen/community',
]

describe('einstellungenKatalog (Routen-Inventur + Struktur)', () => {
  it('deckt jede IST-einstellungen-Route mit einem Katalog-Eintrag ab', () => {
    const abgedeckt = new Set(alleAbgedecktenRouten())
    const fehlend = IST_ROUTEN.filter((r) => !abgedeckt.has(r))
    expect(fehlend).toEqual([])
  })

  it('jeder Eintrag hat eine gültige Kategorie', () => {
    const keys = new Set(EINSTELLUNGEN_KATEGORIEN.map((k) => k.key))
    for (const e of EINSTELLUNGEN_KATALOG) expect(keys.has(e.kategorie)).toBe(true)
  })

  it('jede Kategorie hat mindestens einen Eintrag (außer datengetriebene „Komponenten")', () => {
    for (const k of EINSTELLUNGEN_KATEGORIEN) {
      // „komponenten" ist datengetrieben (Blöcke pro Investitionstyp zur Laufzeit,
      // s. EinstellungenV4) → bewusst KEINE statischen Katalog-Einträge.
      if (k.key === 'komponenten') {
        expect(eintraegeDerKategorie(k.key).length).toBe(0)
        continue
      }
      expect(eintraegeDerKategorie(k.key).length).toBeGreaterThan(0)
    }
  })

  it('Eintrags-IDs sind eindeutig', () => {
    const ids = EINSTELLUNGEN_KATALOG.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('globale Suche matcht Name und Schlagworte, leer ⇒ nichts', () => {
    expect(sucheEintraege('anlage').some((e) => e.id === 'anlage')).toBe(true)
    expect(sucheEintraege('mqtt').length).toBeGreaterThan(0)
    expect(sucheEintraege('')).toEqual([])
  })
})
