/**
 * Route-Manifest — Single Source of Truth für die Bestands-Redirects der App
 * und das Inventar der echten Routen.
 *
 * Konsumenten:
 *  - `App.tsx` rendert `LEGACY_REDIRECTS` als `<Navigate replace>`-Routen.
 *  - Der Redirect-Auto-Test (`src/routes/redirects.test.tsx`, E1-P3) prüft
 *    darüber: jeder Alt-Pfad landet ohne 404 auf einer echten Route, keine
 *    Redirect-Ketten. Fundament für den vollständigen Redirect-Test in 3.8.
 *
 * IA-V4-Flip (v4.0.0): die V4-Oberfläche ist prefix-frei kanonisch (Redirect-
 * Mechanik „Option B" — der frühere `/v4`-Präfix ist gefallen). Die Alt-Welt
 * (V3-Seiten + `/v4`-Vorschau-Pfade) existiert nicht mehr → alle Redirects zeigen
 * auf die prefix-freien V4-Heimaten. **Gerätepfade wechseln die Achse** (Cockpit-
 * Geräte-Dashboards → Komponenten-Hub); die Einstellungs-Alt-Routen werden
 * re-kategorisiert (Zuordnung = die frühere `config/v3ZuV4Route`-Tabelle).
 *
 * Der Index-Redirect (`/` → `/cockpit/live`) bleibt in `App.tsx` inline (Sonderfall
 * der `index`-Route), ebenso die Splat-Fänger für gelöschte dynamische Alt-Sektionen
 * (`aussichten/*`, `monatsabschluss/*`) und die `/v4/*`-Stray-Bookmark-Versicherung.
 * `REAL_ROUTE_PATHS` muss mit den echten `<Route>`-Pfaden in `App.tsx` synchron
 * gehalten werden (der Test schlägt sonst sichtbar an).
 */

export interface RedirectEntry {
  /** Alt-Pfad (ohne führenden Slash — wie als `<Route path>` notiert). */
  from: string
  /** Ziel-Pfad (mit führendem Slash — wie an `<Navigate to>` übergeben). */
  to: string
}

export const LEGACY_REDIRECTS: RedirectEntry[] = [
  // — Alt-Sektions-Basen (frühere Umbauten + V3-Top-Level) → V4-Heimaten —
  { from: 'dashboard', to: '/cockpit/live' },
  { from: 'live', to: '/cockpit/live' },
  { from: 'auswertung', to: '/auswertungen/finanzen' },
  { from: 'auswertungen', to: '/auswertungen/finanzen' },
  { from: 'roi', to: '/auswertungen/roi' },
  { from: 'aussichten', to: '/cockpit/aussicht' },
  { from: 'community', to: '/community/uebersicht' },
  { from: 'auswertungen/community', to: '/community/uebersicht' },
  { from: 'settings', to: '/einstellungen/system' },
  { from: 'anlagen', to: '/einstellungen/stammdaten' },
  { from: 'strompreise', to: '/einstellungen/stammdaten' },
  { from: 'monatsdaten', to: '/einstellungen/daten' },
  { from: 'investitionen', to: '/einstellungen/komponenten' },
  { from: 'import', to: '/einstellungen/integration' },

  // — Geräte wechseln die Achse: Cockpit-Geräte-Dashboards → Komponenten-Hub —
  { from: 'cockpit/pv-anlage', to: '/komponenten/pv-anlage' },
  { from: 'cockpit/e-auto', to: '/komponenten/e-auto' },
  { from: 'cockpit/waermepumpe', to: '/komponenten/waermepumpe' },
  { from: 'cockpit/speicher', to: '/komponenten/speicher' },
  { from: 'cockpit/wallbox', to: '/komponenten/wallbox' },
  { from: 'cockpit/balkonkraftwerk', to: '/komponenten/bkw' },
  { from: 'cockpit/sonstiges', to: '/komponenten/sonstiges' },
  { from: 'cockpit/monatsberichte', to: '/cockpit/monat' },
  { from: 'cockpit/aktueller-monat', to: '/cockpit/monat' },
  // nackte Geräte-Kürzel (Alt-Bestand)
  { from: 'e-auto', to: '/komponenten/e-auto' },
  { from: 'waermepumpe', to: '/komponenten/waermepumpe' },
  { from: 'speicher', to: '/komponenten/speicher' },
  { from: 'wallbox', to: '/komponenten/wallbox' },
  { from: 'balkonkraftwerk', to: '/komponenten/bkw' },
  { from: 'sonstiges', to: '/komponenten/sonstiges' },

  // — Alt-Einstellungs-Routen → V4-Kategorien (Re-Kategorisierung, ex-v3ZuV4Route) —
  // Stammdaten
  { from: 'einstellungen/anlage', to: '/einstellungen/stammdaten' },
  { from: 'einstellungen/strompreise', to: '/einstellungen/stammdaten' },
  { from: 'einstellungen/solarprognose', to: '/einstellungen/stammdaten' },
  { from: 'einstellungen/pvgis', to: '/einstellungen/stammdaten' },
  { from: 'einstellungen/community', to: '/einstellungen/stammdaten' },
  // Komponenten (datengetriebener Reiter)
  { from: 'einstellungen/investitionen', to: '/einstellungen/komponenten' },
  // Daten
  { from: 'einstellungen/monatsdaten', to: '/einstellungen/daten' },
  { from: 'einstellungen/monatsabschluss', to: '/einstellungen/daten' },
  { from: 'einstellungen/datenerfassung', to: '/einstellungen/daten' },
  { from: 'einstellungen/ha-import', to: '/einstellungen/daten' },
  { from: 'einstellungen/energieprofil', to: '/einstellungen/daten' },
  { from: 'einstellungen/daten-checker', to: '/einstellungen/daten' },
  { from: 'einstellungen/einrichtung', to: '/einstellungen/daten' },
  { from: 'einstellungen/demo', to: '/einstellungen/daten' },
  // Integration
  { from: 'einstellungen/import', to: '/einstellungen/integration' },
  { from: 'einstellungen/portal-import', to: '/einstellungen/integration' },
  { from: 'einstellungen/cloud-import', to: '/einstellungen/integration' },
  { from: 'einstellungen/custom-import', to: '/einstellungen/integration' },
  { from: 'einstellungen/connector', to: '/einstellungen/integration' },
  { from: 'einstellungen/ha-statistik-import', to: '/einstellungen/integration' },
  { from: 'einstellungen/ha-export', to: '/einstellungen/integration' },
  // Datenquellen (Alt-Wizards in die feld-zentrische Fläche aufgelöst)
  { from: 'einstellungen/sensor-mapping', to: '/einstellungen/datenquellen' },
  { from: 'einstellungen/mqtt-inbound', to: '/einstellungen/datenquellen' },
  // System
  { from: 'einstellungen/backup', to: '/einstellungen/system' },
  { from: 'einstellungen/allgemein', to: '/einstellungen/system' },
  { from: 'einstellungen/protokolle', to: '/einstellungen/system' },
]

/**
 * Inventar aller echten (nicht-Redirect-)Routen-Pfade — `:param`-Segmente
 * wie in `App.tsx`. Genutzt vom Redirect-Test zur 404-Prüfung der Ziele.
 *
 * IA-V4-Flip: die V4-Achsen sind prefix-frei kanonisch (kein `/v4` mehr). Die
 * Sub-Ebenen sind route-getrieben (`:zeit`/`:typ`/`:sub`/`:kategorie`); die
 * Dispatcher normalisieren unbekannte Sub-Werte selbst auf ihren Default.
 */
export const REAL_ROUTE_PATHS: string[] = [
  // Cockpit (Zeit-Achse: live·tag·monat·jahr·aussicht)
  'cockpit',
  'cockpit/:zeit',
  // Komponenten (Was-Achse: pv-anlage·speicher·bkw·waermepumpe·wallbox·e-auto·sonstiges)
  'komponenten',
  'komponenten/:typ',
  // Auswertungen (Wie-Achse: finanzen·roi·prognose·co2·tabelle)
  'auswertungen',
  'auswertungen/:sub',
  // Community (uebersicht·pv-ertrag·komponenten·regional·trends·statistiken)
  'community',
  'community/:sub',
  // Hilfe
  'hilfe',
  // Einstellungen (Kategorien: stammdaten·komponenten·infothek·daten·integration·datenquellen·system)
  'einstellungen',
  'einstellungen/:kategorie',
  // Dev-only
  'dev/design-preview',
]
