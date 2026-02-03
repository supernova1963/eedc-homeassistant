# EEDC - Energie Effizienz Data Center

Home Assistant Add-on zur lokalen Auswertung und Wirtschaftlichkeitsanalyse von PV-Anlagen.

## Features

- **Lokale Datenspeicherung** - Alle Daten bleiben auf deinem Home Assistant
- **PV-Anlagen Verwaltung** - Stammdaten, Leistung, Standort
- **Monatsdaten Erfassung** - Manuell oder CSV-Import
- **Umfassende Auswertungen** - Autarkie, Eigenverbrauch, Wirtschaftlichkeit
- **Investitions-Tracking** - E-Auto, Wärmepumpe, Speicher, Wallbox
- **Home Assistant Integration** - Automatischer Import aus HA Energy Dashboard
- **Dark Mode** - Vollständige Unterstützung

## Installation

### Über Home Assistant Add-on Store

1. Füge dieses Repository zu deinen Add-on Repositories hinzu:
   ```
   https://github.com/supernova1963/eedc-homeassistant
   ```
2. Suche nach "EEDC" im Add-on Store
3. Klicke auf "Installieren"
4. Starte das Add-on

### Manuell (Development)

Siehe [DEVELOPMENT.md](docs/DEVELOPMENT.md)

## Konfiguration

Nach der Installation kannst du in den Add-on Optionen deine Home Assistant Sensoren zuordnen:

```yaml
ha_sensors:
  pv_erzeugung: sensor.fronius_pv_energy_total
  einspeisung: sensor.grid_export_energy
  netzbezug: sensor.grid_import_energy
  batterie_ladung: sensor.battery_charge_energy
  batterie_entladung: sensor.battery_discharge_energy
```

## Screenshots

*Folgen nach MVP Release*

## Roadmap

- [x] Phase 0: Projekt-Setup
- [ ] Phase 1: MVP (Grundfunktionen)
- [ ] Phase 2: Erweiterte Features (HA Integration, Arbitrage, V2H)
- [ ] Phase 3: KI-Insights, PVGIS Integration

## Entwicklung

Siehe [PROJEKTPLAN.md](PROJEKTPLAN.md) für detaillierte Architektur und Roadmap.

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

## Ursprung

Basiert auf dem Konzept der [EEDC-WebApp](https://github.com/supernova1963/eedc-webapp), reimplementiert als lokale Home Assistant Lösung.
