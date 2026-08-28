# MQTT-Inbound: Universelle Datenbruecke

MQTT-Inbound ermoeglicht es, Live-Leistungsdaten und Zaehlerstaende von **jedem Smarthome-System** an EEDC zu senden. Es wird nur ein MQTT-Broker benoetigt (z.B. Mosquitto).

## Unterstuetzte Systeme

- Home Assistant (Automation oder Node-RED Add-on)
- Node-RED (standalone oder als Add-on)
- ioBroker (JavaScript-Adapter)
- FHEM (MQTT2-Modul)
- openHAB (MQTT Binding)
- Jedes System mit MQTT-Publish-Faehigkeit

## Einrichtung

1. **MQTT-Broker installieren** (z.B. Mosquitto)
2. In EEDC unter *Einstellungen > Einrichtung > MQTT-Inbound*:
   - Broker-Adresse und Port eintragen
   - Optional: Benutzername/Passwort
   - "Speichern & Verbinden" klicken
3. Die generierten Topics im Smarthome-System befuellen

## Topic-Struktur

EEDC generiert die Topics automatisch aus den angelegten Anlagen und Investitionen. Das Format ist:

```
eedc/{anlage_id}_{name}/
├── live/                              # Echtzeit-Leistung (Watt)
│   ├── einspeisung_w                  → 1100
│   ├── netzbezug_w                    → 0
│   └── inv/{inv_id}_{name}/
│       ├── leistung_w                 → 4200
│       └── soc                        → 72       (nur Speicher/E-Auto)
│
└── energy/                            # ZAEHLERSTAENDE (kWh, kumuliert)
    ├── einspeisung_kwh                → 6675.3
    ├── netzbezug_kwh                  → 6424.8
    └── inv/{inv_id}_{name}/
        └── {key}                      → Wert     (siehe Felder-Referenz)
```

### Energy-Felder Referenz (Investitions-Topics)

> ⚠ **Unter `energy/` gehoert der ZAEHLERSTAND, nicht der Monatsverbrauch.** Also der
> fortlaufende Stand, den dein Zaehler oder Wechselrichter anzeigt — eedc bildet die
> Differenzen daraus selbst (Tag, Monat, Jahr).
>
> ⛔ **Ein taeglich oder monatlich zurueckgesetzter Zaehler ist dafuer NICHT geeignet** — also
> ein Feld, das „heute" oder „diesen Monat" meint und dann wieder bei null anfaengt. eedc
> erkennt den Ruecksprung und liefert fuer diesen Zeitraum **keinen Wert**, statt zwei Staende
> voneinander abzuziehen, die zu verschiedenen Zaehlerlaeufen gehoeren.
>
> **Warum nicht einfach hochrechnen?** Technisch ginge es: Die Staende sind stuendlich
> mitgeschrieben, eine Summe daraus traefe auf rund 3 % genau. eedc tut es trotzdem nicht.
> Was zwischen dem letzten Stand und dem Ruecksprung verbraucht wird, taucht in keinem Stand
> mehr auf — der Fehlbetrag geht **immer** in dieselbe Richtung, und im Monatsabschluss wuerde
> aus so einer Zahl per Knopfdruck ein gespeicherter Wert, der aussieht wie eine Messung.
> Genau davor warnt der Daten-Checker schon beim Anlegen: *Zuruecksetzen „nie" (ohne Zyklus)*.
>
> ⭐ **Was du stattdessen tust:** Publiziere den **fortlaufenden** Stand. Bei einem
> `utility_meter` in Home Assistant heisst das Zuruecksetzen auf *„nie"*; kommt der Wert aus
> einer eigenen App, sende den Lebenszaehler statt des Tageswerts. eedc bildet Tag, Monat und
> Jahr daraus selbst — und exakt.
>
> ⛔ **Bis eedc 4.0.32 stimmte dieser Absatz nicht.** Hier stand *„Ein taeglich oder monatlich
> zurueckgesetzter Zaehler funktioniert ebenfalls; eedc erkennt den Ruecksprung"*. Im
> **Tagesfenster** stimmte das, im **Monatsfenster** nur dann, wenn der Ruecksprung zufaellig an
> den Raendern ablesbar war. Ein „…heute"-Zaehler ergab im laufenden Monat einen Wert, der
> aussah wie eine Messung und den Verbrauch **eines** Tages nannte (gemessen: 5,6 statt
> 140 kWh) — *Cockpit → Monat* zeigte ihn an.
>
> **Bis eedc 4.0.29 stand hier „Monatswerte", und das war missverstaendlich.** Wer korrekt
> seinen Zaehlerstand schickte, bekam ihn im Monatsabschluss als Monatsmenge vorgehalten
> („weicht ab": 6675,3 gegen 552,75 kWh) und in *Cockpit → Monat* sogar angezeigt. Seit
> 4.0.30 rechnet eedc die Differenz ueber den Monat. **Du musst nichts umstellen** — der
> Zaehlerstand war und ist das Richtige.
>
> ⭐ **`km_gefahren` und `ladevorgaenge` folgen derselben Regel — seit sie eine eigene
> Zaehlerreihe haben.** Sie tragen keine kWh, und deshalb schrieb eedc fuer sie lange
> gar keine Reihe mit: Ein HA-Anwender bekam seine Monatswerte trotzdem, weil die
> HA-Statistik die Differenz direkt rechnet, ein Standalone-Anwender bekam **nichts** und
> trug von Hand ein — obwohl derselbe Feld-Hinweis ihm den „kumulativen km-Zaehler
> (Auto-Integration/OBD)" als Quelle anbot (Discussion #396). Jetzt schreibt eedc auch
> diese beiden Staende mit. **Schick den Tachostand, nicht die gefahrenen Kilometer.**

Die Felder unter `energy/inv/{id}_{name}/` entsprechen den Monatsdaten-Feldern der jeweiligen Investition. EEDC erkennt alle Felder automatisch — es muss kein Mapping konfiguriert werden.

| Investitionstyp | Key | Einheit | Beschreibung |
|---|---|---|---|
| **PV-Module** | `pv_erzeugung_kwh` | kWh | PV-Erzeugung |
| **Speicher** | `ladung_kwh` | kWh | Batterie-Ladung |
| **Speicher** | `entladung_kwh` | kWh | Batterie-Entladung |
| **Waermepumpe** | `stromverbrauch_kwh` | kWh | Stromverbrauch |
| **Waermepumpe** | `heizenergie_kwh` | kWh | Erzeugte Heizenergie |
| **Waermepumpe** | `warmwasser_kwh` | kWh | Warmwasser-Erzeugung |
| **E-Auto** | `km_gefahren` | km | **Tachostand** (Odometer) — eedc bildet die gefahrenen Kilometer daraus |
| **E-Auto** | `v2h_entladung_kwh` | kWh | Vehicle-to-Home Entladung |
| **Wallbox** | `ladung_kwh` | kWh | Ladung gesamt |
| **Wallbox** | `ladevorgaenge` | Anzahl | **Fortlaufender Zaehler** der Ladevorgaenge — eedc bildet die Anzahl im Monat daraus |
| **BKW** | `pv_erzeugung_kwh` | kWh | BKW-Erzeugung |
| **BKW** | `eigenverbrauch_kwh` | kWh | Eigenverbrauch |
| **BKW** | `speicher_ladung_kwh` | kWh | BKW-Speicher Ladung |
| **BKW** | `speicher_entladung_kwh` | kWh | BKW-Speicher Entladung |
| **Sonstiges** | `erzeugung_kwh` | kWh | Erzeugung (Erzeuger/Speicher) |
| **Sonstiges** | `verbrauch_sonstig_kwh` | kWh | Verbrauch (Verbraucher/Speicher) |

**Nicht per MQTT lieferbar** (werden im Monatsabschluss manuell eingegeben oder berechnet):
- `ladung_pv_kwh` / `ladung_netz_kwh` (PV/Netz-Aufteilung bei Speicher, E-Auto, Wallbox)
- `batterie_ladung_netz_kwh` (Arbitrage-Anteil)
- `ladung_extern_kwh` / `ladung_extern_euro` (externe Ladung E-Auto)
- Wetterdaten (`globalstrahlung`, `sonnenstunden`, `temperatur`)
- `sonderkosten_euro`, `notizen`

### Beispiel

Fuer eine Anlage "Meine PV" (ID 1) mit Speicher "BYD HVS" (ID 3):

```
eedc/1_Meine_PV/live/einspeisung_w          → 1100
eedc/1_Meine_PV/live/inv/3_BYD_HVS/leistung_w → -500
eedc/1_Meine_PV/live/inv/3_BYD_HVS/soc      → 72
eedc/1_Meine_PV/energy/pv_gesamt_kwh         → 627.0
eedc/1_Meine_PV/energy/inv/3_BYD_HVS/ladung_kwh → 128.6
```

**Hinweis:** Die numerische ID am Anfang (`1_`, `3_`) ist die DB-ID. Der Name danach ist optional und dient nur der Lesbarkeit. EEDC extrahiert nur die ID.

## Datenquellen-Prioritaet

MQTT-Inbound hat Konfidenz 91% und liegt zwischen Connector (90%) und HA Statistics (92%):

```
Gespeichert (85%) → Connector (90%) → MQTT-Inbound (91%) → HA Statistics (92%)
```

**Diese Reihenfolge gilt nur fuer den laufenden Monat.** Dort ist sie eine
Live-Vorschau: die frischere Quelle gewinnt, wer HA Statistics hat, sieht deren
Werte statt der MQTT-Werte.

Im **abgeschlossenen** Monat gilt das Gegenteil: gespeicherte Werte sind
authoritativ. Connector und HA-Statistics fuellen dort nur Felder, die noch
leer sind, und ueberschreiben nichts rueckwirkend; MQTT-Inbound wird fuer
vergangene Monate gar nicht erst abgefragt. Ein importierter Monatswert
(Cloud-, Portal- oder CSV-Import) bleibt damit stehen, auch wenn fuer dasselbe
Feld ein HA-Sensor zugeordnet ist — die Zuordnung muss dafuer niemand
entfernen.

**Das ist die Anzeige-Seite.** Beim *Schreiben* gilt eine eigene Hierarchie
(`backend/core/source_priority.py`): Cloud-/Portal-Import und HA-Statistik-
Import liegen dort auf **derselben** Stufe, bei gleicher Stufe gewinnt der
spaetere Schreiber. Ein HA-Statistik-Import mit angehaktem „ueberschreiben"
ersetzt also einen importierten Wert dauerhaft. Nur ein im Formular gepflegter
Wert (Stufe `manual:form`) ist gegen beide geschuetzt.

SoT der Regeln: Anzeige
`backend/core/berechnungen/datenquellen.py::merge_datenquellen`, Schreiben
`backend/services/provenance.py::write_with_provenance`.

## Home Assistant Automation Generator

EEDC enthaelt einen integrierten **HA Automation Generator** unter *Einstellungen → MQTT-Inbound*. Dort kannst du deine HA-Sensoren den EEDC-Topics zuordnen und erhaeltst zwei fertige YAML-Automationen (Live + Energy) zum Kopieren.

1. In EEDC: **Einstellungen → MQTT-Inbound → HA Automation Generator** aufklappen
2. Pro Topic deine HA-Entity eintragen (z.B. `sensor.pv_power`)
3. Intervall waehlen (5s, 10s, 30s oder 60s)
4. Fertiges YAML kopieren und in Home Assistant einfuegen

## Beispiel-Flows (andere Systeme)

Die folgenden Beispiele zeigen die manuelle Konfiguration fuer andere Smarthome-Systeme.

### Home Assistant Automation

```yaml
automation:
  - alias: "EEDC PV-Leistung senden"
    trigger:
      - platform: state
        entity_id: sensor.pv_power
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA_Tripower/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
```

Mehrere Sensoren:

```yaml
automation:
  - alias: "EEDC Live-Daten senden"
    trigger:
      - platform: time_pattern
        seconds: "/5"
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/einspeisung_w"
          payload: "{{ states('sensor.grid_export_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/netzbezug_w"
          payload: "{{ states('sensor.grid_import_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/leistung_w"
          payload: "{{ states('sensor.battery_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/soc"
          payload: "{{ states('sensor.battery_soc') }}"
```

### Node-RED

Einfacher Flow: Sensor-Node → MQTT-Out-Node

```json
[
  {
    "id": "eedc_pv",
    "type": "mqtt out",
    "topic": "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w",
    "broker": "localhost",
    "name": "EEDC PV-Leistung"
  }
]
```

Fuer mehrere Werte einen Function-Node verwenden, der die Sensor-Werte auf die passenden Topics mappt.

### ioBroker (JavaScript-Adapter)

```javascript
// Live-Leistung senden
on('sourceDP.pv_power', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/2_SMA/leistung_w',
        message: String(obj.state.val)
    });
});

// Batterie SoC senden
on('sourceDP.battery_soc', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/3_BYD/soc',
        message: String(obj.state.val)
    });
});

// Netz-Werte senden
on('sourceDP.grid_export', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/einspeisung_w',
        message: String(obj.state.val)
    });
});
```

### FHEM

```perl
# MQTT2-Geraet fuer EEDC anlegen
define eedc_mqtt MQTT2_DEVICE

# PV-Leistung bei Aenderung senden
define eedc_pv notify pv_power:.* {\
  fhem("set mqtt2 publish eedc/1_Meine_PV/live/inv/2_SMA/leistung_w " . ReadingsVal("pv_power","state","0"))\
}
```

### openHAB

```java
rule "EEDC PV-Leistung senden"
when
    Item PV_Power changed
then
    val mqttActions = getActions("mqtt", "mqtt:broker:myBroker")
    mqttActions.publishMQTT("eedc/1_Meine_PV/live/inv/2_SMA/leistung_w", PV_Power.state.toString)
end
```

## Testen

### Kommandozeile (mosquitto_pub)

```bash
# Einzelnen Wert senden
mosquitto_pub -h localhost -t "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w" -m "4200"

# Alle Topics subscriben (Monitoring)
mosquitto_sub -h localhost -t "eedc/#" -v
```

### In EEDC pruefen

1. In der MQTT-Einrichtung unter "Empfangene Werte" auf "Aktualisieren" klicken
2. Im Live-Dashboard pruefen ob die Werte angezeigt werden

## Hinweise

- **Payload-Format:** Nur numerische Werte (z.B. `4200`, `72.5`). Kein JSON.
- **Einheiten:** Live-Topics in **Watt** (nicht kW). Energy-Topics in **kWh**.
- **Batterie:** Positive Werte = Ladung, negative = Entladung
- **Retained Messages:** EEDC publisht beim Speichern Initialwerte (0) als Retained, damit Topics am Broker sichtbar sind.
- **Reconnect:** Bei Verbindungsverlust verbindet sich der Subscriber automatisch nach 10 Sekunden neu.
- **Monatsabschluss:** Energy-Topics erscheinen automatisch als Vorschlaege im Monatsabschluss-Wizard (Konfidenz 91%). Kein zusaetzliches Mapping noetig.
