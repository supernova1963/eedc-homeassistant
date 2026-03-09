# Forum-Beiträge v2.8.2 – Cloud-Import Provider

Erstellt: 2026-03-09

## Status

| Forum | Typ | Status |
|---|---|---|
| Photovoltaikforum – Monitoring & Systemanbindung | Hauptbeitrag (neu) | NEU SCHREIBEN (alter Thread gelöscht) |
| Photovoltaikforum – Balkonkraftwerke | Kurzversion BKW | offen |
| Photovoltaikforum – Sungrow Logger/Kommunikation | Herstellerspezifisch | offen |
| Photovoltaikforum – Fronius Datenkommunikation | Herstellerspezifisch | offen |
| Photovoltaikforum – Simulationssoftware/Wirtschaftlichkeit | Feature-Fokus | offen |
| HA Community – Energy Thread | Update (Antwort) | offen |
| community-smarthome.com | Update (Antwort) | offen |
| community.simon42.com | Update (Antwort) | offen |

---

## 1. Photovoltaikforum – Monitoring & Systemanbindung (NEU – Ersatz für gelöschten Thread)

**Titel:** EEDC – Open-Source PV-Auswertung mit Cloud-Import für 11 Hersteller (Tester gesucht)
**Tags:** monitoring, cloud-import, open-source, pv-auswertung, wirtschaftlichkeit, roi
**Hinweis:** Ersetzt den gelöschten Ursprungsthread (Mod-Fehler beim Zusammenlegen)

Hallo zusammen,

ich entwickle **EEDC** (Energie Effizienz Data Center) – ein kostenloses Open-Source-Tool für **PV-Langzeitauswertung und Wirtschaftlichkeitsberechnung**. Läuft standalone per Docker oder als Home-Assistant-Add-on. Alle Daten bleiben lokal, kein Account, kein Abo.

(Mein ursprünglicher Thread wurde beim Zusammenlegen leider versehentlich gelöscht – daher hier nochmal von vorn.)

### Was kann EEDC?

- **ROI-Dashboard** mit Amortisationskurve und Renditeberechnung
- **SOLL-IST-Vergleich** mit PVGIS-Prognose (standortgenau)
- **Autarkie- und Eigenverbrauchsquote** (monatlich + kumuliert)
- **Finanzübersicht** – Einsparung, Einspeisevergütung, Amortisation
- **Community-Benchmark** – anonymer Vergleich mit anderen Anlagen auf [energy.raunet.eu](https://energy.raunet.eu)
- **Wetterprognose** – DWD, Open-Meteo, PVGIS
- **PDF-Berichte, CSV/JSON-Export**

Unterstützt: **Wechselrichter, PV-Module, Batteriespeicher, Wallbox, E-Auto, Wärmepumpe** – alles als Investitions-Komponenten mit eigener ROI-Berechnung.

### Wie kommen die Daten rein?

EEDC bietet 5 Wege zur Datenerfassung – vom vollautomatisch bis manuell:

**1. Cloud-Import (NEU in v2.8)** – Monatsdaten direkt aus der Hersteller-Cloud:

| Hersteller | Cloud-Plattform | Zugangsdaten |
|---|---|---|
| SolarEdge | Monitoring Portal | API Key + Site ID |
| Fronius | Solar.web | Access Key + PV-System-ID |
| Huawei | FusionSolar | Northbound API Account |
| Growatt | ShineServer | Benutzername + Passwort |
| Sungrow | iSolarCloud | E-Mail + Passwort |
| Deye / Solarman | Solarman Smart | App ID + Secret |
| Viessmann | GridBox | E-Mail + Passwort |
| EcoFlow | Developer API | Access Key + Secret Key |
| Anker SOLIX | Anker Cloud | E-Mail + Passwort |
| Hoymiles | S-Miles Cloud | E-Mail + Passwort |

4-Schritt-Wizard: Verbinden → Zeitraum wählen → Vorschau → Import. Credentials werden pro Anlage gespeichert.

**2. Custom-Import** – Beliebige CSV/JSON-Dateien mit Feld-Mapping importieren. Auto-Erkennung von Spalten, Einheit wählbar (Wh/kWh/MWh), Mapping als Template speicherbar.

**3. Portal-Import (CSV-Upload)** – Automatische Erkennung von Exporten aus:
- SMA Sunny Portal, SMA eCharger, EVCC, Fronius Solarweb

**4. Geräte-Connectors** – Direkte Abfrage über das lokale Netzwerk:
- SMA ennexOS, SMA WebConnect, Fronius Solar API, go-eCharger, Shelly 3EM, OpenDTU, Kostal Plenticore, sonnenBatterie, Tasmota SML

**5. Home Assistant** – HA-Sensor-History-Import, MQTT-Export, dynamischer Tarif aus HA-Sensor (Tibber, aWATTar)

**6. Manuell** – Monatsabschluss-Wizard mit Quellenanzeige und Vorschlägen

### Installation

**Docker (standalone):**
```
docker-compose up -d
```
→ http://localhost:8099

**Home Assistant Add-on:** Repo `https://github.com/supernova1963/eedc-homeassistant` in HACS einbinden → Add-on installieren → starten.

Einrichtung: Kurzer Assistent (Anlage anlegen, Strompreise eintragen) – dauert ca. 2-3 Minuten, alle Werte sind nachträglich änderbar.

### Tester gesucht!

Die **11 Cloud-Import-Provider** sind alle implementiert, aber **noch nicht mit echten Geräten getestet**. Die Implementierung basiert auf offizieller API-Doku und Community-Projekten, aber in der Praxis können Feldnamen oder Datenformate abweichen.

Wer einen der genannten Wechselrichter/Speicher hat und 10 Minuten investieren mag: EEDC installieren → Cloud-Import → Hersteller wählen → testen. **Rückmeldung über Fehler ist genauso wertvoll wie Erfolgsmeldungen.**

### Links

- GitHub: https://github.com/supernova1963/eedc
- Doku: https://supernova1963.github.io/eedc-homeassistant/
- Community-Benchmark: https://energy.raunet.eu

---

## 2. Photovoltaikforum – Balkonkraftwerke (PV-Anlage ohne EEG)

**Titel:** BKW-Daten automatisch auswerten – Cloud-Import für Hoymiles, Anker SOLIX & EcoFlow (Tester gesucht)
**Tags:** balkonkraftwerk, hoymiles, anker-solix, ecoflow, monitoring, cloud-import

Hallo,

ich entwickle **EEDC** – ein kostenloses Open-Source-Tool zur PV-Auswertung und Wirtschaftlichkeitsberechnung ([Thread im Monitoring-Forum](Link zum Hauptbeitrag)). Läuft via Docker oder als Home-Assistant-Add-on, alle Daten bleiben lokal.

Seit v2.8 kann EEDC eure Monatsdaten direkt aus der Hersteller-Cloud importieren. Für **Balkonkraftwerke** werden unterstützt:

| Hersteller | Cloud | Zugangsdaten | Was wird importiert |
|---|---|---|---|
| **Hoymiles** (HMS/HM/HMT) | S-Miles Cloud | E-Mail + Passwort | PV-Erzeugung, Einspeisung, Eigenverbrauch |
| **Anker SOLIX** (Solarbank/MI80) | Anker Cloud | E-Mail + Passwort | PV-Erzeugung, Einspeisung, Eigenverbrauch, Batterie |
| **EcoFlow PowerStream** | Developer API | Access Key + Secret Key | PV-Erzeugung, Einspeisung, Batterie (Delta) |

Bei Anker werden dieselben Zugangsdaten wie in der App verwendet, seit App v3.10 werden parallele Logins unterstützt. Für EcoFlow braucht man einen Developer-Account (developer-eu.ecoflow.com, Freischaltung kann bis zu 1 Woche dauern).

**Das Problem:** Alle drei Provider sind noch **ungetestet mit echten Geräten**. Die APIs sind implementiert, aber ich brauche Rückmeldung ob die Daten in der Praxis korrekt ankommen.

**So geht's:** EEDC installieren → kurzer Einrichtungs-Assistent (Anlage + Strompreise, ca. 2-3 Min.) → Daten → Cloud-Import → Hersteller wählen → testen.

Wer ein BKW mit Hoymiles, Anker oder EcoFlow hat und 10 Minuten investieren mag – ich freue mich über jede Rückmeldung, auch wenn etwas nicht klappt.

GitHub: https://github.com/supernova1963/eedc

---

## 3. Photovoltaikforum – Sungrow Logger/Kommunikation

**Titel:** iSolarCloud-Daten automatisch in EEDC importieren – Tester gesucht
**Tags:** isolarcloud, datenimport, monitoring, cloud-api, open-source

Hallo,

das Open-Source-Tool **EEDC** (PV-Analyse + Wirtschaftlichkeitsberechnung) kann seit v2.8 Monatsdaten direkt aus der **iSolarCloud** importieren – PV-Erzeugung, Einspeisung, Netzbezug, Batterie und Eigenverbrauch.

Funktioniert mit SG-Serie (String-WR) und SH-Serie (Hybrid-WR). Zugangsdaten: dieselben wie in der iSolarCloud App (E-Mail + Passwort). EU-Server wird unterstützt.

**So geht's:** EEDC installieren (Docker oder HA-Add-on) → kurzer Einrichtungs-Assistent (Anlage + Strompreise, ca. 2-3 Min.) → Daten → Cloud-Import → "Sungrow iSolarCloud" wählen → testen.

Der Provider ist noch **ungetestet**. Wer eine Sungrow-Anlage hat und kurz testen mag: über Rückmeldung (positiv oder negativ) würde ich mich freuen.

GitHub: https://github.com/supernova1963/eedc | Mehr Info: [Thread im Monitoring-Forum](Link zum Hauptbeitrag)

---

## 4. Photovoltaikforum – Fronius Datenkommunikation

**Titel:** Fronius Solar.web-Daten automatisch in EEDC importieren – Tester gesucht
**Tags:** solar.web, datenimport, monitoring, cloud-api, open-source

Hallo,

**EEDC** (Open-Source PV-Analyse) kann seit v2.8 Monatsdaten direkt aus **Fronius Solar.web** importieren – PV-Erzeugung, Einspeisung, Netzbezug, Eigenverbrauch.

Voraussetzung: Solar.web Access Key (unter solar.web → Einstellungen → Zugangsschlüssel generieren) und die PV-System-ID.

**So geht's:** EEDC installieren (Docker oder HA-Add-on) → kurzer Einrichtungs-Assistent (Anlage + Strompreise, ca. 2-3 Min.) → Daten → Cloud-Import → "Fronius Solar.web" wählen → testen.

Der Provider ist noch **ungetestet mit echten Geräten**. Wer einen Fronius-Wechselrichter mit Solar.web hat – kurzes Testen und Rückmeldung wäre super.

GitHub: https://github.com/supernova1963/eedc | Mehr Info: [Thread im Monitoring-Forum](Link zum Hauptbeitrag)

---

## 5. Photovoltaikforum – Simulationssoftware / Wirtschaftlichkeitsberechnung

**Titel:** EEDC – Open-Source PV-Wirtschaftlichkeitsberechnung mit automatischem Cloud-Import
**Tags:** wirtschaftlichkeit, roi, amortisation, pv-auswertung, open-source, autarkie

Hallo,

ich möchte **EEDC** (Energie Effizienz Data Center) hier vorstellen – ein kostenloses Open-Source-Tool für PV-Wirtschaftlichkeitsberechnung und Langzeit-Auswertung. Einige kennen es vielleicht aus meinem [früheren Thread](https://www.photovoltaikforum.com/thread/256959-ben%C3%B6tige-unterst%C3%BCtzung-und-tester-f%C3%BCr-eine-elektronische-energiedatensammlung-f%C3%BC/), inzwischen ist es bei v2.8.2.

**Was kann es?**
- ROI-Dashboard mit Amortisationskurve
- SOLL-IST-Vergleich mit PVGIS-Prognose
- Autarkie- und Eigenverbrauchsquote
- Monatliche Wirtschaftlichkeitsübersicht
- Community-Benchmark (anonymer Vergleich mit anderen Anlagen)

**Wie kommen die Daten rein?**
- **Cloud-Import** für 11 Hersteller (SolarEdge, Fronius, Huawei, Growatt, Sungrow, Deye, Viessmann, EcoFlow, Anker SOLIX, Hoymiles) – automatisch Monatsdaten aus der Hersteller-Cloud
- **CSV/JSON Custom-Import** mit Feld-Mapping für beliebige Datenquellen
- **Portal-Import** für SMA Sunny Portal, EVCC, Fronius Solarweb
- **Home Assistant** Integration (HA-Sensor-History + MQTT Export)
- **Manuelle Eingabe** über Monatsabschluss-Wizard

Läuft standalone (Docker) oder als HA-Add-on. Alle Daten lokal, kein Account nötig.

**Tester gesucht:** Die Cloud-Import-Provider sind alle noch ungetestet. Wer Lust hat, kurz seinen Hersteller zu testen – ich freue mich über jede Rückmeldung.

GitHub: https://github.com/supernova1963/eedc
Doku: https://supernova1963.github.io/eedc-homeassistant/

---

## 6. Home Assistant Community – Energy Thread (Update/Antwort)

**Thread:** https://community.home-assistant.io/t/eedc-energie-effizienz-data-center/986594

## v2.8.2 Update – Cloud Import for 11 Manufacturers (Testers Needed!)

Big update: EEDC now supports **automatic cloud import** from 11 manufacturer cloud platforms. No more manual data entry or CSV exports – EEDC fetches your monthly energy data (PV generation, feed-in, grid consumption, battery, self-consumption) directly from your inverter's cloud.

### Supported Manufacturers

**Rooftop Systems:**
| Manufacturer | Cloud Platform | Credentials |
|---|---|---|
| SolarEdge | Monitoring Portal | API Key + Site ID |
| Fronius | Solar.web | Access Key + PV-System-ID |
| Huawei | FusionSolar | Northbound API Account |
| Growatt | ShineServer | Username + Password |
| Sungrow | iSolarCloud | Email + Password |
| Deye / Solarman | Solarman Smart | App ID + Secret |
| Viessmann | GridBox | Email + Password |
| EcoFlow | Developer API | Access Key + Secret Key |

**Balcony Solar (Balkonkraftwerke):**
| Manufacturer | Cloud Platform | Credentials |
|---|---|---|
| EcoFlow PowerStream | Developer API | Access Key + Secret Key |
| Anker SOLIX (Solarbank/MI80) | Anker Cloud | Email + Password |
| Hoymiles (HMS/HM/HMT) | S-Miles Cloud | Email + Password |

### How it works

1. Run the setup wizard (create your system, enter electricity prices – takes ~2-3 minutes, values can be adjusted later)
2. Go to **Data → Cloud Import** → select your manufacturer
3. Enter your credentials (same as your manufacturer's app/portal)
4. Test connection → fetch data → done

All data stays **local on your machine**.

### Testers needed!

All 11 providers are implemented but **untested with real devices**. The API integrations are based on official documentation and community projects, but field names and data formats may differ in practice.

If you have any of the above systems and can spare 10 minutes: install EEDC, try the cloud import for your manufacturer, and let me know if the connection works and the data looks correct. Feedback on errors is just as valuable!

Also new: **Custom Import** for arbitrary CSV/JSON files with field mapping – useful if your manufacturer isn't listed yet.

GitHub: https://github.com/supernova1963/eedc-homeassistant

---

## 7. community-smarthome.com (Update/Antwort)

**Thread:** https://community-smarthome.com/t/eedc-energie-effizienz-data-center/10057/12

**Update: v2.8.2 – Cloud-Import für 11 Hersteller**

Kurzes Update: EEDC hat seit dem letzten Post einiges dazubekommen. Das größte neue Feature ist der **automatische Cloud-Import** – EEDC holt sich eure Monatsdaten (PV-Erzeugung, Einspeisung, Netzbezug, Batterie, Eigenverbrauch) direkt aus der Hersteller-Cloud. Kein manuelles Eintippen mehr.

**Unterstützte Hersteller:**
- **Dachanlagen:** SolarEdge, Fronius, Huawei FusionSolar, Growatt, Sungrow, Deye/Solarman, Viessmann GridBox, EcoFlow PowerOcean
- **Balkonkraftwerke:** EcoFlow PowerStream, Anker SOLIX, Hoymiles S-Miles Cloud

Dazu gibt's einen **Custom-Import** für beliebige CSV/JSON-Dateien mit Feld-Mapping, falls euer Hersteller nicht dabei ist.

**Tester gesucht:** Alle 11 Provider sind implementiert, aber noch mit keinem echten Gerät getestet. Wenn ihr einen der genannten Wechselrichter habt und 10 Minuten Zeit: EEDC installieren (Docker oder HA-Add-on) → Einrichtungs-Assistent durchlaufen (ca. 2-3 Min.) → Daten → Cloud-Import → testen. Rückmeldung – egal ob positiv oder negativ – hilft enorm.

Weiterhin gilt: **Alles lokal – keine Cloud, keine Registrierung, alle Daten bleiben bei euch.** Die Cloud-APIs werden nur zum Abrufen eurer eigenen Daten genutzt, EEDC hat keinen eigenen Server.

GitHub: https://github.com/supernova1963/eedc-homeassistant

---

## 8. community.simon42.com (Update/Antwort)

**Thread:** https://community.simon42.com/t/eedc-energie-effizienz-data-center/77723

**Update: v2.8.2 – Automatischer Cloud-Import**

Hallo zusammen,

seit dem letzten Update hier hat sich einiges getan. EEDC ist inzwischen bei v2.8.2 – die Kinderkrankheiten aus der Beta-Phase sind behoben, und es gibt ein großes neues Feature:

**Cloud-Import für 11 Hersteller** – EEDC holt eure Monatsdaten automatisch aus der Hersteller-Cloud:
- **Dachanlagen:** SolarEdge, Fronius, Huawei, Growatt, Sungrow, Deye/Solarman, Viessmann GridBox, EcoFlow
- **Balkonkraftwerke:** EcoFlow PowerStream, Anker SOLIX, Hoymiles (HMS/HM/HMT)

Ihr gebt einfach eure App-Zugangsdaten ein (dieselben wie bei eurem Hersteller), testet die Verbindung, und EEDC zieht sich die historischen Daten. Für Hersteller die nicht dabei sind gibt's einen **Custom-Import** für CSV/JSON mit Feld-Mapping.

Außerdem neu seit v2.0.3: Monatsabschluss-Wizard, dynamischer Tarif, 9 Geräte-Connectors (SMA, Fronius, go-eCharger, Shelly 3EM, OpenDTU u.a.) und der Community-Vergleich funktioniert jetzt stabil.

**Tester gesucht:** Die 11 Cloud-Import-Provider sind alle noch ungetestet mit echten Geräten. Wenn jemand einen der genannten Wechselrichter hat – ich freue mich über Rückmeldung ob die Daten korrekt ankommen. Installation ist unverändert über HACS oder Docker möglich.

@rapahl falls du noch dabei bist – würde mich interessieren wie es bei dir läuft :slightly_smiling_face:

GitHub: https://github.com/supernova1963/eedc-homeassistant
