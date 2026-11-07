## 1. Basis-Felder (Zähler / Netzübergabe)

### Monatserfassung (kWh)

<!-- erzeugt: eingabefelder typ=basis liste=monat -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `einspeisung_kwh`: Ins Netz eingespeiste Energie. Muss immer ≥ 0 sein. Bei Zweirichtungszähler: nur der Einspeiseanteil.
> - `netzbezug_kwh`: Aus dem Netz bezogene Energie. Muss immer ≥ 0 sein. Bei Zweirichtungszähler: nur der Bezugsanteil.
> - `globalstrahlung_kwh_m2`: Globalstrahlung im Monat. Der Auto-Fill im Monatsabschluss holt sie von Open-Meteo bzw. Bright Sky — **nur in ein leeres Feld**.
> - `sonnenstunden`: Sonnenstunden im Monat. Der Auto-Fill im Monatsabschluss holt sie von Open-Meteo bzw. Bright Sky — **nur in ein leeres Feld**.
> - `durchschnittstemperatur`: Monatsdurchschnitt. Der Auto-Fill im Monatsabschluss holt ihn zuerst aus den **gemessenen Außentemperaturen** des Monats (Stundenwerte, sonst Tages-Min/Max), sonst von Open-Meteo — und nur in ein leeres Feld.

### Live-Dashboard (W)

<!-- erzeugt: eingabefelder typ=basis liste=live -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `pv_gesamt_w`: Gesamte aktuelle PV-Leistung. Nur nötig wenn keine individuellen PV-Komponenten-Sensoren konfiguriert sind.
> - `netz_kombi_w`: Alternative zu getrennt `einspeisung_w`/`netzbezug_w`. Positiv = Netzbezug, negativ = Einspeisung. Nur verwenden, wenn keine getrennten Leistungssensoren vorhanden sind. Zugeordnete kWh-Zählerstände (`einspeisung_kwh`/`netzbezug_kwh`) daneben sind richtig — sie liefern die Tagesmengen, der Kombi-Sensor die Leistung.
> - `strompreis`: **Optional, ab v3.16.0.** Aktueller Strompreis aus Tibber, aWATTar, EPEX oder eigenem Template-Sensor. Akzeptierte Einheiten: `ct/kWh`, `EUR/kWh`, `EUR/MWh` (×0.1 → ct/kWh), `Cent`, `€`. Wird im Live-Tagesverlauf als gepunktete Linie auf sekundärer Y-Achse gezeigt. Ohne eigenen Sensor lädt eedc automatisch den EPEX-Börsenpreis (DE/AT) via aWATTar API als Fallback.

### MQTT-Topic-Mapping (Basis)

Welche MQTT-Topics eedc für die Anlage erwartet — die Live-Topics der Basis-Felder und die drei Zählerstände `pv_gesamt_kwh`, `einspeisung_kwh`, `netzbezug_kwh` —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

