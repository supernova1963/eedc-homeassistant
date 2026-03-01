# EEDC - Energie Effizienz Data Center

Lokale PV-Anlagen Auswertung und Wirtschaftlichkeitsanalyse als Home Assistant Add-on.

**Alle Daten bleiben lokal auf deinem Server** - keine Cloud-Abhängigkeit.

## Features

### Cockpit & Dashboards
- **Modernisiertes Cockpit** mit Hero-Leiste, Energie-Fluss-Diagramm, Ring-Gauges und Sparklines
- **8 spezialisierte Dashboards** (PV-Anlage, Speicher, E-Auto, Wärmepumpe, Wallbox, BKW, ...)
- **Amortisations-Fortschrittsbalken** pro Komponente
- **Social-Media-Textvorlage** - Kopierfertige Monatsübersicht (Kompakt/Ausführlich)

### Auswertungen
- **6 Analyse-Tabs**: Energie, PV-Anlage, Komponenten, Finanzen, CO2, Investitionen
- **SOLL-IST Vergleich** gegen PVGIS-Prognosen
- **ROI-Dashboard** mit Amortisationskurve
- **CSV/JSON/PDF Export**

### Aussichten (Prognosen)
- **Kurzfristig:** 7-Tage Wetterprognose mit PV-Erzeugung
- **Langfristig:** 12-Monats-Prognose mit PVGIS-Daten
- **Trend-Analyse:** Degradationsberechnung und saisonale Muster
- **Finanzen:** Amortisations-Fortschritt und Break-Even-Prognose

### Community-Vergleich
- Anonymer Benchmark mit anderen PV-Anlagen
- Radar-Chart, regionale Choropleth-Karte
- Gamification mit Achievements

### Home Assistant Integration
- **Sensor-Mapping-Wizard** - HA-Sensoren den EEDC-Feldern zuordnen
- **Monatsabschluss-Wizard** - Geführte Datenerfassung mit automatischen Vorschlägen
- **HA-Statistik Import** - Historische Monatswerte aus HA-Langzeitstatistik
- **MQTT Discovery** - Native HA-Sensoren mit berechneten KPIs

### Unterstützte Komponenten
PV-Anlage, Speicher (AC/DC), E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk, Sonstiges

## Erste Schritte

1. Add-on installieren und starten
2. Über die Sidebar "eedc" öffnen
3. Anlage mit Standort und kWp anlegen
4. Investitionen (Komponenten) hinzufügen
5. Monatsdaten erfassen (manuell, CSV-Import oder HA-Statistik)

## Dokumentation

Die vollständige Dokumentation ist auf der Website verfügbar:

**[supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/)**

## Support

Issues und Feature-Requests:
[github.com/supernova1963/eedc-homeassistant/issues](https://github.com/supernova1963/eedc-homeassistant/issues)
