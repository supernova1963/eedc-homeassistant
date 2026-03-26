# ioBroker Forum Post – MQTT Tag

**Titel:** [MQTT] EEDC – Kostenlose PV-Analyse per MQTT an ioBroker anbinden – Tester & Mitdenker gesucht!

---

Hallo zusammen,

ich möchte euch mein Open-Source-Projekt **EEDC** (Energie Effizienz Data Center) vorstellen und suche **ioBroker-Nutzer, die Lust haben, die MQTT-Anbindung zu testen und mitzugestalten**.

## Was ist EEDC?

EEDC ist eine **kostenlose, lokal laufende PV-Analyse-Software** als Docker-Container – komplett ohne Cloud-Zwang. Ursprünglich als Home Assistant Add-on entstanden, läuft EEDC seit Version 3.0 auch **vollständig standalone** – perfekt also für ioBroker-Nutzer.

**Was EEDC von reinen Monitoring-Tools unterscheidet:**
- **Echte Wirtschaftlichkeitsanalyse** – ROI pro Komponente, Amortisationskurve, Alternativkosten-Vergleich (z.B. Wärmepumpe vs. Gasheizung)
- **Komponenten-Tracking** – Nicht nur PV, sondern auch Speicher, Wärmepumpe, E-Auto, Wallbox, Balkonkraftwerk
- **GTI-basierte Ertragsprognose** – Prognose auf Basis der Global Tilted Irradiance für eure exakte Modulausrichtung
- **Community-Benchmark** – Anonymer Vergleich mit anderen Anlagen (optional, eigener Server)
- **Live-Dashboard** – Animiertes Energiefluss-Diagramm mit Echtzeit-Leistungswerten
- **Steuerliche Behandlung** – Kleinunternehmerregelung, USt auf Eigenverbrauch (DE/AT/CH)
- **Alles lokal** – SQLite-Datenbank, keine Accounts, keine Abos

**GitHub:** https://github.com/supernova1963/eedc
**Website:** https://supernova1963.github.io/eedc-homeassistant/
**Community-Server:** https://energy.raunet.eu

## Standalone-Installation (2 Minuten)

```bash
git clone https://github.com/supernova1963/eedc.git
cd eedc
docker compose up -d
```
→ Erreichbar unter http://localhost:8099

Läuft auf **amd64 und arm64** (Raspberry Pi 4+).

## Wie funktioniert die MQTT-Anbindung?

EEDC hat einen eingebauten **MQTT-Inbound-Service**, der als universelle Datenbrücke für beliebige Smarthome-Systeme dient. Die Idee:

### Prinzip
```
ioBroker → MQTT-Broker (Mosquitto) → EEDC MQTT-Inbound → Live-Dashboard + Auswertungen
```

### EEDC lauscht auf standardisierte Topics:
```
eedc/{AnlageID}_{Name}/live/einspeisung_w        → Einspeisung (W)
eedc/{AnlageID}_{Name}/live/netzbezug_w          → Netzbezug (W)
eedc/{AnlageID}_{Name}/live/pv_gesamt_w          → PV-Gesamtleistung (W)
eedc/{AnlageID}_{Name}/live/batterie_ladung_w    → Batterie Ladung (W)
eedc/{AnlageID}_{Name}/live/batterie_entladung_w → Batterie Entladung (W)
eedc/{AnlageID}_{Name}/live/inv/{ID}_{Name}/leistung_w → Wechselrichter-Leistung (W)
eedc/{AnlageID}_{Name}/live/inv/{ID}_{Name}/soc        → Batterie SoC (%)
eedc/{AnlageID}_{Name}/energy/einspeisung_kwh    → Zählerstand Einspeisung (kWh)
eedc/{AnlageID}_{Name}/energy/netzbezug_kwh      → Zählerstand Netzbezug (kWh)
```

### MQTT-Gateway (Topic-Übersetzer)

Zusätzlich gibt es ein **MQTT-Gateway**, das externe Topics automatisch in EEDC-Topics übersetzt. Damit müsst ihr eure bestehenden MQTT-Topics nicht ändern:

```
Quell-Topic (z.B. ioBroker):     smartmeter/0/power
    ↓ Transformation (Faktor, Offset, Invertierung, JSON-Extraktion)
Ziel-Topic (EEDC):               eedc/1_Meine_PV/live/netzbezug_w
```

Das Gateway unterstützt:
- **Plain-Werte** (einfache Zahl)
- **JSON-Payloads** mit Pfad-Extraktion (z.B. `power.total` aus `{"power": {"total": 1234}}`)
- **JSON-Arrays** mit Index (z.B. Index 11 aus `[10, 11, 1234.5, ...]`)
- **Mathematische Transformation** – Faktor × Wert + Offset, optional Invertierung

### Fertige Geräte-Presets

Für einige Geräte gibt es bereits vorkonfigurierte Presets:
- **Shelly 3EM / Pro 3EM** – Netz-Gesamtleistung
- **Shelly Plus 1PM/2PM** – JSON-Payload (Gen2 API)
- **OpenDTU** (Hoymiles/TSUN) – PV-Wechselrichter
- **Tasmota SML** (IR-Lesekopf) – OBIS-Codes für Smartmeter
- **go-e Charger** – Wallbox-Ladeleistung

## Was EEDC alles kann (Kurzüberblick)

| Bereich | Features |
|---------|----------|
| **Live-Dashboard** | Animiertes Energiefluss-Diagramm, Gauges, Heute/Gestern kWh, 24h-Verlauf, Wetter-Widget |
| **Cockpit** | Übersicht mit Autarkie, Eigenverbrauch, Finanzen, CO2 – pro Komponente aufgeschlüsselt |
| **Auswertungen** | 6 Tabs: Energie, PV-Anlage, Komponenten, Finanzen, CO2, Investitionen |
| **Prognosen** | 7-Tage GTI-Prognose, Langfrist (PVGIS), Trend-Analyse, Degradation, Finanz-Aussichten |
| **Community** | Anonymer Benchmark mit Radar-Chart, Ranking, Achievements, Regionalkarte |
| **Datenquellen** | HA-Statistik, MQTT, Cloud-Import (SolarEdge, Fronius, Huawei, Growatt, Deye), Device-Connectors (SMA, Fronius, Shelly, OpenDTU, Kostal, sonnenBatterie), CSV-Import, manuelle Eingabe |

## Wo ich eure Hilfe brauche

Die MQTT-Anbindung funktioniert grundsätzlich – sie ist aber bisher primär mit Home Assistant und Node-RED getestet. **Für ioBroker fehlt mir die Praxis-Erfahrung:**

### 1. ioBroker-Adapter-Empfehlungen
- Welchen MQTT-Adapter nutzt ihr? (`mqtt.0`, `mqtt-client.0`, ...?)
- Wie publiziert ihr Datenpunkte am besten nach MQTT?

### 2. Typische ioBroker-Topic-Strukturen
- Wie sehen eure MQTT-Topics typischerweise aus, wenn ihr z.B. einen Shelly 3EM, SMA-Wechselrichter oder Smartmeter über ioBroker → MQTT bereitstellt?
- Nutzt ihr eher `mqtt.0/devicename/...` oder eigene Topic-Strukturen?

### 3. Tester gesucht!
- Wer hat Lust, die MQTT-Anbindung mit seinem ioBroker-Setup zu testen?
- Idealerweise mit einer PV-Anlage und einem MQTT-Broker (Mosquitto)
- Ich würde dann gerne ein **ioBroker-Preset** für das MQTT-Gateway bauen, damit die Einrichtung für andere ioBroker-Nutzer möglichst einfach wird

### 4. Blockly/JavaScript-Vorlage
- Wäre es sinnvoll, ein fertiges Blockly-Script oder JavaScript bereitzustellen, das die ioBroker-Datenpunkte automatisch auf die EEDC-Topics mappt?
- Oder ist der Weg über den MQTT-Adapter + EEDC-Gateway besser?

## MQTT-Konfiguration in EEDC

Die Einrichtung in EEDC ist über die Web-Oberfläche möglich:

1. **Einstellungen → MQTT-Inbound** → Broker-Daten eingeben (Host, Port, User, Passwort)
2. **Verbindung testen** → Zeigt an, ob der Broker erreichbar ist
3. **Gateway-Mappings anlegen** → Eure ioBroker-Topics auf EEDC-Topics mappen
4. **Topic-Monitor** → Zeigt empfangene Nachrichten in Echtzeit an (zum Debuggen)

Alternativ per Umgebungsvariablen im Docker:
```yaml
environment:
  - MQTT_ENABLED=true
  - MQTT_HOST=192.168.1.100    # Euer Mosquitto
  - MQTT_PORT=1883
  - MQTT_USER=eedc
  - MQTT_PASSWORD=geheim
```

## Zusammenfassung

| | |
|---|---|
| **Was** | Kostenlose PV-Analyse mit Live-Dashboard, Wirtschaftlichkeit, Prognosen, Community-Vergleich |
| **Wie** | Docker-Container, lokal, kein Cloud-Zwang |
| **Daten rein** | MQTT (universell), Cloud-Imports, Device-Connectors, CSV, manuell |
| **Gesucht** | ioBroker-Tester für die MQTT-Anbindung + Feedback zur Topic-Struktur |

Ich freue mich über jedes Feedback – egal ob Fragen, Vorschläge oder Kritik. Das Projekt ist Open Source (MIT-Lizenz) und lebt von der Community.

Danke fürs Lesen! 🙂

---

*Links:*
- GitHub (Standalone): https://github.com/supernova1963/eedc
- Website & Doku: https://supernova1963.github.io/eedc-homeassistant/
- Community-Benchmark: https://energy.raunet.eu
