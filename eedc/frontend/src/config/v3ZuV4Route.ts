/**
 * V3→V4-Einstellungs-Routen-Map.
 *
 * Die IA-V4-Einstellungen **re-kategorisieren** die IST-Seiten: die alten
 * `einstellungen/<seite>`-Routen werden zu `v4/einstellungen/<kategorie>`-Reitern
 * (z. B. `monatsdaten`/`energieprofil`/`daten-checker` → **daten**; `anlage`/
 * `strompreise`/`solarprognose` → **stammdaten**; `sensor-mapping`/`mqtt-inbound` →
 * **integration**; `investitionen` → **komponenten**). Ein reiner Präfix (`/v4` davor)
 * reicht darum NICHT — es braucht diese Zuordnung.
 *
 * Nutzung: geteilte `pages/*Teile.tsx`, die dynamische V3-Ziele verlinken (z. B. die
 * „Beheben"-Links des Daten-Checkers, `CheckErgebnis.link`), biegen unter `/v4` über
 * {@link v3RouteZuV4} auf den passenden V4-Reiter um (mit {@link useV4Basis} gegatet).
 *
 * **SoT-Abgleich:** die Kategorie-Zuordnung spiegelt `EINSTELLUNGEN_KATALOG`
 * (`route`→`kategorie`); ein Konsistenz-Test (`v3ZuV4Route.test.ts`) sichert gegen
 * Drift. `investitionen` ist bewusst NICHT im Katalog (datengetriebener Komponenten-
 * Reiter) → hier als Sonderfall. **Nicht-Einstellungs-Ziele** (z. B.
 * `/monatsabschluss/…`, CSV-`/import`) haben keine V4-Heimat → `null` (Donor, Flip).
 */

/** V3-Einstellungs-Route (ohne führenden `/`, ohne Query) → V4-Einstellungs-Kategorie. */
const V3_EINSTELLUNG_ZU_V4_KATEGORIE: Record<string, string> = {
  // Stammdaten
  'einstellungen/community': 'stammdaten',
  'einstellungen/anlage': 'stammdaten',
  'einstellungen/strompreise': 'stammdaten',
  'einstellungen/solarprognose': 'stammdaten',
  // Komponenten (datengetriebener Reiter — nicht im Katalog)
  'einstellungen/investitionen': 'komponenten',
  // Infothek
  'einstellungen/infothek': 'infothek',
  // Daten
  'einstellungen/monatsdaten': 'daten',
  'einstellungen/energieprofil': 'daten',
  'einstellungen/daten-checker': 'daten',
  'einstellungen/einrichtung': 'daten',
  // Integration
  'einstellungen/ha-statistik-import': 'integration',
  'einstellungen/ha-export': 'integration',
  'einstellungen/portal-import': 'integration',
  'einstellungen/import': 'integration',
  // Datenquellen (B7): die beiden Alt-Wizards sind in die feld-zentrische Fläche
  // aufgelöst — ihre V3-Routen landen dort, nicht mehr auf „Integration".
  'einstellungen/datenquellen': 'datenquellen',
  'einstellungen/sensor-mapping': 'datenquellen',
  'einstellungen/mqtt-inbound': 'datenquellen',
  // System
  'einstellungen/allgemein': 'system',
  'einstellungen/backup': 'system',
  'einstellungen/protokolle': 'system',
}

export { V3_EINSTELLUNG_ZU_V4_KATEGORIE }

/**
 * V3-Einstellungs-Link (mit/ohne führenden `/`, optional mit Query) → V4-Kategorie-
 * Route `/v4/einstellungen/<kategorie>`. `null`, wenn kein Einstellungs-Ziel mit
 * V4-Heimat (z. B. `/monatsabschluss/…` = Donor). Der Query wird verworfen (die
 * V4-Reiter kennen keine Tages-Deep-Links).
 */
export function v3RouteZuV4(v3link: string): string | null {
  const clean = v3link.replace(/^\/+/, '').split('?')[0]
  const kategorie = V3_EINSTELLUNG_ZU_V4_KATEGORIE[clean]
  return kategorie ? `/v4/einstellungen/${kategorie}` : null
}
