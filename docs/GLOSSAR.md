
# EEDC Glossar & Support

**Version 3.6** | Stand: März 2026

> Dieses Glossar ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil I: Installation](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md)

---

## Glossar

| Begriff | Bedeutung |
|---------|-----------|
| **Autarkie** | Grad der Unabhängigkeit vom Stromnetz: Eigenverbrauch / Gesamtverbrauch × 100 % |
| **Eigenverbrauch** | Selbst genutzter PV-Strom (Direktverbrauch + Speicher-Entladung + V2H) |
| **Direktverbrauch** | Sofort verbrauchter PV-Strom ohne Umweg über den Speicher |
| **Einspeisung** | Ins Netz abgegebener PV-Überschuss |
| **Netzbezug** | Aus dem Netz bezogener Strom |
| **kWp** | Kilowatt Peak – Nennleistung der PV-Anlage unter Standardtestbedingungen |
| **kWh** | Kilowattstunde – Energiemenge |
| **ROI** | Return on Investment – Kapitalrendite; in EEDC als Jahres-% oder kumulierter Fortschritt |
| **COP** | Coefficient of Performance – momentane Effizienz der Wärmepumpe (Wärme / Strom) |
| **SCOP** | Seasonal COP – saisonale Effizienz vom EU-Energielabel, standortunabhängig |
| **JAZ** | Jahresarbeitszahl – gemessene Effizienz der Wärmepumpe am eigenen Standort über ein Jahr |
| **V2H** | Vehicle-to-Home – E-Auto speist Strom ins Haus zurück |
| **Arbitrage** | Speicher-Strategie: Bei günstigem Netzstrom laden, bei teuerem Strom entladen |
| **PVGIS** | Photovoltaic Geographical Information System – EU-Dienst für standortbezogene PV-Ertragsprognosen |
| **TMY** | Typical Meteorological Year – statistisches Durchschnittswetterjahr als Prognosebasis |
| **Performance Ratio** | Verhältnis IST-Ertrag zu theoretisch möglichem Ertrag; Qualitätskennzahl der Anlage |
| **MaStR** | Marktstammdatenregister – amtliches Register aller Energieerzeugungsanlagen in Deutschland |
| **BKW** | Balkonkraftwerk – kleine steckfertige PV-Anlage (auch: Balkonkraftwerk, Steckersolaranlage) |
| **MQTT** | Message Queuing Telemetry Transport – schlankes Protokoll für IoT- und Smarthome-Kommunikation |
| **MQTT-Inbound** | EEDC-Funktion zum Empfang von Echtzeitdaten aus beliebigen Smarthome-Systemen via MQTT |
| **MQTT-Gateway** | EEDC-Funktion zum Übersetzen eigener Geräte-Topics (Shelly, OpenDTU, Tasmota …) auf EEDC-Felder |
| **Sensor-Mapping** | Zuordnung von Home-Assistant-Sensoren zu EEDC-Feldern im Wizard |
| **SFML** | Solar Forecast ML – KI-basierte Ertragsprognose eines externen Dienstes; wird in EEDC als zweite Linie neben der eigenen Prognose angezeigt |
| **ICON-CH2** | MeteoSwiss-Wettermodell mit 2 km Auflösung; empfohlen für alpine Standorte (CH, AT, Südtirol) |
| **ICON-D2** | DWD-Wettermodell mit 2,2 km Auflösung; hochauflösend für Deutschland |
| **ECMWF IFS** | Globales Wettermodell des Europäischen Zentrums für mittelfristige Wettervorhersage |
| **Infothek** | Optionales EEDC-Modul zur Verwaltung von Verträgen, Zählern, Kontakten und Dokumenten |
| **Monatsabschluss** | Monatliche Datenerfassung via geführtem Wizard mit automatischen Vorschlägen aus mehreren Quellen |
| **Connector** | Geräte-Modul in EEDC für direkten API-Abruf von Wechselrichtern, Speichern und Ladesäulen |
| **Community-Hash** | Anonymer Identifier für die Community-Benchmark-Funktion; kein Rückschluss auf Person oder Adresse |

---

## Support

Bei Fragen oder Problemen:

1. **GitHub Issues**: [github.com/supernova1963/eedc-homeassistant/issues](https://github.com/supernova1963/eedc-homeassistant/issues)
2. **Protokolle-Seite** (Einstellungen → System → Protokolle): Debug-Modus aktivieren, Logs kopieren, in Issue einfügen
3. **Dokumentation**: [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/)

---

*Letzte Aktualisierung: März 2026*
