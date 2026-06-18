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
 * Der Index-Redirect (`/` → `/live`) bleibt in `App.tsx` inline (Sonderfall
 * der `index`-Route). `REAL_ROUTE_PATHS` muss mit den echten `<Route>`-Pfaden
 * in `App.tsx` synchron gehalten werden (der Test schlägt sonst sichtbar an).
 */

export interface RedirectEntry {
  /** Alt-Pfad (ohne führenden Slash — wie als `<Route path>` notiert). */
  from: string
  /** Ziel-Pfad (mit führendem Slash — wie an `<Navigate to>` übergeben). */
  to: string
}

export const LEGACY_REDIRECTS: RedirectEntry[] = [
  // — Bestands-Redirects aus früheren Umbauten —
  { from: 'cockpit/aktueller-monat', to: '/cockpit/monatsberichte' },
  { from: 'einstellungen/monatsabschluss', to: '/einstellungen/monatsdaten' },
  { from: 'einstellungen/datenerfassung', to: '/einstellungen/monatsdaten' },
  { from: 'einstellungen/demo', to: '/einstellungen/import' },
  { from: 'einstellungen/ha-import', to: '/einstellungen/monatsdaten' },
  { from: 'einstellungen/pvgis', to: '/einstellungen/solarprognose' },
  // Ziel auf den Default-Sub-Tab gezogen (war `/community`), um eine Kette
  // über den neuen `community`-Basis-Redirect (s. u.) zu vermeiden.
  { from: 'auswertungen/community', to: '/community/uebersicht' },
  { from: 'dashboard', to: '/cockpit' },
  { from: 'anlagen', to: '/einstellungen/anlage' },
  { from: 'monatsdaten', to: '/einstellungen/monatsdaten' },
  { from: 'strompreise', to: '/einstellungen/strompreise' },
  { from: 'investitionen', to: '/einstellungen/investitionen' },
  // Direkt auf den Default-Sub-Tab (war `/auswertungen` → wäre jetzt Kette).
  { from: 'auswertung', to: '/auswertungen/energie' },
  { from: 'roi', to: '/auswertungen/roi' },
  { from: 'e-auto', to: '/cockpit/e-auto' },
  { from: 'waermepumpe', to: '/cockpit/waermepumpe' },
  { from: 'speicher', to: '/cockpit/speicher' },
  { from: 'wallbox', to: '/cockpit/wallbox' },
  { from: 'balkonkraftwerk', to: '/cockpit/balkonkraftwerk' },
  { from: 'sonstiges', to: '/cockpit/sonstiges' },
  { from: 'import', to: '/einstellungen/import' },
  { from: 'settings', to: '/einstellungen/allgemein' },
  // — B1 (E1-P3): Sektions-Basis → Default-Sub-Tab (URL-getriebene Sub-Nav) —
  { from: 'auswertungen', to: '/auswertungen/energie' },
  { from: 'aussichten', to: '/aussichten/kurzfristig' },
  { from: 'community', to: '/community/uebersicht' },
]

/**
 * Inventar aller echten (nicht-Redirect-)Routen-Pfade — `:param`-Segmente
 * wie in `App.tsx`. Genutzt vom Redirect-Test zur 404-Prüfung der Ziele.
 */
export const REAL_ROUTE_PATHS: string[] = [
  // Cockpit
  'cockpit',
  'cockpit/pv-anlage',
  'cockpit/e-auto',
  'cockpit/waermepumpe',
  'cockpit/speicher',
  'cockpit/wallbox',
  'cockpit/balkonkraftwerk',
  'cockpit/monatsberichte',
  'cockpit/sonstiges',
  // Live
  'live',
  // Auswertungen (B1: Sub-Tabs route-getrieben)
  'auswertungen/:tab',
  'auswertungen/roi',
  'auswertungen/prognose',
  'auswertungen/export',
  // Aussichten + Community (B1)
  'aussichten/:tab',
  'community/:tab',
  // Hilfe
  'hilfe',
  // Einstellungen — Stammdaten
  'einstellungen/anlage',
  'einstellungen/strompreise',
  'einstellungen/investitionen',
  'einstellungen/infothek',
  'einstellungen/solarprognose',
  // Einstellungen — Daten
  'einstellungen/monatsdaten',
  'monatsabschluss/:anlageId',
  'monatsabschluss/:anlageId/:jahr/:monat',
  'einstellungen/energieprofil',
  'einstellungen/daten-checker',
  'einstellungen/einrichtung',
  'einstellungen/import',
  'einstellungen/portal-import',
  'einstellungen/cloud-import',
  'einstellungen/custom-import',
  'einstellungen/connector',
  'einstellungen/mqtt-inbound',
  // Einstellungen — Home Assistant
  'einstellungen/sensor-mapping',
  'einstellungen/ha-statistik-import',
  'einstellungen/ha-export',
  // Einstellungen — System
  'einstellungen/backup',
  'einstellungen/allgemein',
  'einstellungen/protokolle',
  // Einstellungen — Community
  'einstellungen/community',
  // Dev-only
  'dev/design-preview',
  // IA-v4-Vorschau (flag-gated hinter VITE_IA_V4; eigenes LayoutV4)
  'v4',
  'v4/cockpit',
  'v4/cockpit/:zeit',
  'v4/auswertungen',
  'v4/auswertungen/tabelle',
  'v4/komponenten',
  'v4/community',
  'v4/hilfe',
  'v4/einstellungen',
]
