---
name: WP-Temperaturkorrektur für Verbrauchsprognose
description: Offener Punkt - Wärmepumpen-Verbrauch im Live-Dashboard temperaturabhängig skalieren
type: project
---

Verbrauchsprognose im Live-Dashboard könnte bei Anlagen mit Wärmepumpe verbessert werden, indem der WP-Anteil im stündlichen Verbrauchsprofil mit der Forecast-Temperatur skaliert wird (kälterer Tag → höherer WP-Verbrauch).

**Why:** Das individuelle Verbrauchsprofil (14-Tage-Mittel, Werktag/Wochenende getrennt) ist für Haushalte ohne WP bereits ~85-90% genau. Bei WP-Anlagen verfälschen Temperatursprünge das Profil aber merklich, weil der WP-Anteil stark schwankt.

**How to apply:** Erst umsetzen, nachdem die GTI-basierte PV-Prognose (Phase 1-3, implementiert 2026-03-20) in der Praxis validiert ist. Ansatz: Wenn eine WP als Investition konfiguriert ist, den WP-Anteil im Profil mit `max(0.3, (15 - forecast_temp) / (15 - referenz_temp))` skalieren.
