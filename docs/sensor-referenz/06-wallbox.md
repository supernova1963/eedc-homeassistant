## 6. Wallbox

> **Die Wallbox ist die Summe aller Ladungen an ihr** — privates Auto, Gast, Dienstwagen. So zählt sie in der Energiebilanz, am Tag, in der Stunde und in ihrer eigenen Anzeige. Mehrere Wallboxen werden summiert (jeder Ladepunkt zählt). Trägt ein Auto eine eigene Heim-Messung (siehe E-Auto), zählt sie für dieses Auto; der **Rest** der Wallbox geht nach Kilometern an die privaten Autos ohne eigene Messung, ohne solche bleibt er nicht zugeordnet (Gast, Verluste: nur Verbrauch, keine Ersparnis) — außer es ist gar kein Fahrzeug angelegt: dann ist die Wallbox selbst das private Auto. Ohne Messung am Auto ist das die bisherige km-anteilige Aufteilung. Ordne den Loadpoint-/Wallbox-Energiesensor hier zu.

### Monatserfassung

<!-- erzeugt: eingabefelder typ=wallbox liste=monat -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `ladung_kwh`: Gesamte von der Wallbox abgegebene Ladeenergie im Monat. evcc über MQTT: das Gateway-Preset „evcc Ladepunkt" legt `chargeTotalImport` (kWh-Zählerstand, nur mit Lademeter) unter `energy/` ab ([MQTT-Inbound](MQTT_INBOUND.md)). *Preset ab der nächsten Version.*

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=wallbox liste=live -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `ladezustand`: `kein_fahrzeug` · `verbunden` · `wartet` · `laedt` · `fertig` · `gesperrt` · `fehler`; SMA `smaev`-Werte, über MQTT die go-e-Codes 0–5 ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)). Chip im Überblick und an der Energiefluss-Kachel; **stündlich mitgeschrieben** (Karte „Betrieb heute" mit „Ladevorgänge heute", ab Zuordnung; ohne Ladezustand aus den drei evcc-Feldern verschränkt). *Ab der nächsten Version.*
> - `fahrzeug_am_ladepunkt`: Fahrzeugname der Steuerung (evcc `select.…_vehicle_name`, openWB). Treffer mit der „Kennung in der Steuerung" eines E-Autos ⇒ genau dieses Auto; leer bei angestecktem Fahrzeug ⇒ „Gastfahrzeug"; fremder Name ⇒ „Fahrzeug der Steuerung unbekannt" + Daten-Checker ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)). Kein Kanon, keine Werte-Tabelle. *Ab der nächsten Version.*
> - `sitzung_kwh`: Seit dem Anstecken geladen. ⚠ SMA/go-e/evcc-MQTT liefern Wh — eedc rechnet nicht um (das Gateway-Preset „evcc Ladepunkt" setzt Faktor 0,001, [MQTT-Inbound](MQTT_INBOUND.md)). *Ab der nächsten Version.*
> - `evcc_verbunden`: `an` · `aus` (HA `binary_sensor.evcc_…_connected` on/off, MQTT `connected` true/false, über MQTT auch 1/0). Nur nötig ohne Ladezustand-Sensor: mit „evcc: lädt" und „evcc: Laden freigegeben" setzt eedc den Ladezustand zusammen; ein gemessener Ladezustand geht vor ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)). *Ab der nächsten Version.*
> - `ziel_ladestand_prozent`: Ladelimit der Steuerung (evcc `effective_limit_soc`). *Ab der nächsten Version.*
> - `restzeit_min`: ⚠ evcc meldet Sekunden — Anzeigeeinheit in HA auf Minuten stellen (das Gateway-Preset „evcc Ladepunkt" setzt Faktor 1/60). *Ab der nächsten Version.*
> - `lademodus`: `aus` · `pv` · `smart` · `schnell` · `plan` · `eco`; evcc `select.…_mode`, SMA. *Ab der nächsten Version.*
> - `evcc_laedt`: `an` · `aus` (HA `binary_sensor.evcc_…_charging`, MQTT `charging`). Teil von Option A — ohne dieses Feld nie „Lädt". *Ab der nächsten Version.*
> - `evcc_freigegeben`: `an` · `aus` (HA `binary_sensor.evcc_…_enabled`, MQTT `enabled`). Verbunden, aber nicht freigegeben ⇒ „Wartet"; ohne dieses Feld nie „Wartet". *Ab der nächsten Version.*

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

## 6a. Themen (frei gewählte Entitäten) — Wärmepumpe, Wallbox, E-Auto

*Seit der nächsten Version.* Kein eedc-Feld: ein **Themen-Eintrag** zeigt den Zustand einer Entität, die du selbst wählst,
wie Home Assistant ihn liefert — jede Domain, keine Einheit vorgeschrieben, keine Rechnung, keine Mitschrift
([Handbuch Einstellungen §7.11](HANDBUCH_EINSTELLUNGEN.md#711-themen-frei-gewählte-entitäten)).

| Weg | Form | Hinweis |
|-----|------|---------|
| HA-Sensor | jede Entität mit Zustand (`lock.…`, `binary_sensor.…`, `sensor.…`, `device_tracker.…`) | Wert = State, Einheit = `unit_of_measurement`; für Klartext einen Template-Helfer zuordnen |
| MQTT-Inbound | `eedc/{id}_{name}/live/inv/{id}_{name}/thema_e{n}` | Text, am besten `retained` ([MQTT-Inbound](MQTT_INBOUND.md)) |
| MQTT-Gateway | Fremd-Topic → `…/thema_e{n}` | als Text weitergereicht, ohne Faktor |

---

