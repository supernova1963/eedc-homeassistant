# eedc Datenquellen-Konsolidierung: Connector → MQTT

> **Status:** Konzept für den Umbau der Geräte-Connector-Anbindung auf die MQTT-Topic-Ebene — Ziel ist die Reduktion *aller* Live-/Tages-Datenquellen auf **zwei**: HA-Sensor-Zuordnung und MQTT-Topics. Maintainer-getrieben, ausgelöst durch einen konkreten Tester-Befund.
>
> **Eingangsperspektive:** Ein Standalone-/MQTT-Tester (EcoFlow + Node-RED) hat einen Geräte-Connector eingerichtet — die Kachel zeigt **„konfiguriert"** und wirbt mit **„Automatische Zählerstandserfassung"** — und erwartet daraufhin automatische Monatswerte. Geliefert wird das nicht: „Heute" bleibt 0,0 kWh, keine Monatsdaten. Die Diagnose deckte auf, dass die Connector-Anbindung **architektonisch halb fertig** ist (siehe Ist-Zustand). Der Fall ist kein Einzelfall, sondern die sichtbare Spitze einer unfertigen Architektur-Etappe.
>
> **Verwandte Dokumente:** [ARCHITEKTUR.md](ARCHITEKTUR.md) · [KONZEPT-IA-V4.md](KONZEPT-IA-V4.md) (paralleler großer Schnitt) · Memory `feedback_aggregations_drift`, `feedback_bypass_kombi_schreib_schicht`.

---

## Leitprinzip: Zwei Datenquellen statt drei

| Quelle | Wofür | Status |
|---|---|---|
| **HA-Sensor-Zuordnung** | HA-Betrieb: Live + LTS-Statistik | etabliert |
| **MQTT-Topics** | Standalone/MQTT: Node-RED, ioBroker, FHEM, openHAB — und **Connectoren** | Ziel |
| ~~Geräte-Connector (eigener Pfad)~~ | ~~lokale Geräte per REST~~ | **auflösen → in MQTT überführen** |

**Begründung (Maintainer):** Ein herstellerspezifischer Connector liefert nur in Ausnahmefällen *alle* Daten einer Anlage. Vollständige Abdeckung bräuchte sehr viele Spezial-Connectoren (PV, WP, BKW, E-Auto, Smart Meter …). Die MQTT-Topic-Ebene ist die richtige universelle Schnittstelle: Der Connector wird **eine Quelle unter vielen** auf einem uniformen `eedc/{id}/energy/…`-Namespace. Der Nutzer mischt pro Topic — Connector liefert PV, Node-RED die WP, ioBroker das E-Auto —, ohne dass downstream herstellerspezifische Energie-Logik nötig ist. Genau diese Komposition macht die Flut an Spezial-Connectoren überflüssig.

**Bewusst in Kauf genommener Tradeoff:** Standalone funktioniert dann **nicht mehr ohne MQTT-Broker**. Das ist faktisch **bereits heute so** für den Connector-Pfad (siehe Ist-Zustand) — der Umbau macht die Bedingung nur explizit, sie ist nicht neu.

---

## Ist-Zustand: Die Architektur ist halb gebaut, nicht ungebaut

Die „Connectoren schreiben in MQTT"-Idee **existiert bereits im Code**. Die Bridge startet automatisch beim Boot (`main.py:281–334`), lädt alle Anlagen mit `connector_config` als Targets und pollt sie. Sie ist an **drei Stellen unfertig**:

### Lücke 1 — Energie-Hälfte fehlt komplett *(der eigentliche Bug)*
`connector_mqtt_bridge.py` ruft nur `read_live()` und publisht **ausschließlich Live-Leistung in Watt** (`pv_gesamt_w`, `einspeisung_w`, …, Zeilen 191–205). Diese landen über die Topic-Regex `…/live/…` nur im **Live-Cache** (`_live`). Der Connector *hat* `read_meters()` → kumulative kWh-Zählerstände (`base.py:30`, `MeterSnapshot`), aber **niemand bridged sie nach `energy/*_kwh`**.

Folge: Die gesamte Energie-/„Heute"-/Aggregations-Pipeline (`get_tages_kwh` → `_compute_deltas` → `get_energy_data` → `_energy`-Cache) wird **nur von `energy/*_kwh`-Topics** gespeist und bekommt vom Connector nichts. „Heute" = 0, kein Tagesverlauf, keine Monatsdaten-Quelle.

> Seit dem Architekturwechsel **v3.19.0** („kWh aus Zähler-Snapshots statt Leistungs-Integration") wird Live-Watt auch **nicht mehr** zu kWh integriert. Die Bridge wurde dabei nie nachgezogen — die Energie-Hälfte ist die direkte Schuld dieses Wechsels.

### Lücke 2 — Investitions-Zuordnung fehlt
`main.py:320`: `inv_id=None,  # TODO: Investition-Zuordnung aus Config`. Alles kollabiert auf Anlagen-Basis-Topics; pro-Gerät/pro-String-Mapping ist nie verdrahtet worden.

### Lücke 3 — Manueller Zähler-Pfad als Insel
`read_meters()` hat genau **einen** Aufrufer: den manuellen Button „Zählerstand manuell vom Gerät ablesen" (`connector.py:290`), der in den JSON-Blob `connector_config.meter_snapshots` schreibt — **außerhalb** der MQTT-Pipeline. Ein dritter Datenweg, genau die Art Sonderpfad, die die Zwei-Quellen-Architektur abschaffen soll.

**Warum nie fertig?** Git-Historie: ein einziger Feature-Commit `82f94f33 „Connector → MQTT Bridge + Live-Daten Info in UI"`. Inkrementeller Wurf, der die Live-Hälfte auslieferte; der Energie-Follow-up kam nie. Der `TODO`-Kommentar bestätigt: bekannt unvollständig, keine bewusste Gegenentscheidung.

---

## Ziel-Architektur

```
Geräte-Connector (REST)                         MQTT-Broker            eedc
┌────────────────────┐                          ┌──────────┐          ┌─────────────────┐
│ read_live()  (W)   │ ── eedc/{id}/live/…  ──→ │          │ ──────→  │ _live  (Cache)  │ → Live-Dashboard
│ read_meters() (kWh)│ ── eedc/{id}/energy/… ─→ │  Inbound │ ──────→  │ _energy (Cache) │ → MqttEnergySnapshot
└────────────────────┘                          │  Pipeline│          │   (5-min Job)   │ → aggregate_day
   (Bridge = Publisher)                          └──────────┘          └─────────────────┘ → Tagesverlauf
Node-RED / ioBroker / FHEM ── eedc/{id}/energy/… ─┘ (gleicher Namespace)                    → Monatsabschluss → Monatsdaten
```

Der Connector wird zum reinen MQTT-Publisher. **Downstream ändert sich nichts** — Snapshot, Delta-Berechnung, Aggregation, Monatsabschluss konsumieren den `_energy`-Cache unverändert, egal welche Quelle ihn füllt.

---

## Umbau in drei Schritten

> **Reihenfolge-Hinweis:** Schritt 1 und 2 sind **gekoppelt** — die Energie-Schleife darf nur per-String publishen (Schritt 2), nie anlagenweites `pv_gesamt_kwh` (Fallback-Falle, s. o.). Praktisch zuerst die `inv_id`-Zuordnung (Schritt 2), dann die Energie-Schleife (Schritt 1) darauf aufsetzen.

### Schritt 1 — Energie-Schleife in der Bridge *(release-relevanter Kern, setzt Schritt 2 voraus)*
Zweite, langsamere Poll-Schleife (z. B. 5 min, passend zum bestehenden `MqttEnergySnapshot`-Job): `read_meters()` → publish **per-String** auf `eedc/{id}/energy/inv/{inv_id}/…`. Nur non-None-Felder publishen (analog `_publish_live`). `read_meters()` ist derselbe HTTP-Call-Typ wie `read_live()` (Shelly: aiohttp-GET) — billig. `MeterSnapshot` ist bereits kumulativ in kWh = exakt, was Snapshot + Delta + Monatsabschluss erwarten.

> **Detail-Entscheidung Key-Mapping — per-String ist kanonisch, NICHT `pv_gesamt_kwh`:** Die Bridge publisht pro Gerät/String auf `energy/inv/{inv_id}/pv_erzeugung_kwh`, was `_compute_deltas` via `_MQTT_FIELD_TO_LIVE_KEY` → `pv_{id}` übersetzt und der **v3.34.5-Fix** auf Kategorie `pv` summiert — **ohne** erzwungene Verteilung. Das anlagenweite `pv_gesamt_kwh` ist **Fallback-only**: es greift nur, wenn keine Einzelstring-Werte kommen, und zwingt die Aggregation in die **fixe gewichtete kWp-Verteilung** mit ihrer bekannten Folgeproblem-Klasse (siehe Memory `project_kwp_verteilung_aggregator`). → Die Bridge darf `pv_gesamt_kwh` **nicht** als Default produzieren; per-Investition ist Pflicht. Damit ist **Schritt 2 (inv-Zuordnung) Voraussetzung für Schritt 1**, nicht optionaler Nachzügler.

### Schritt 2 — Investitions-Zuordnung (`inv_id`)
TODO `main.py:320` verdrahten: `connector_config` um eine Investitions-Zuordnung erweitern, `ConnectorTarget.inv_id` füllen, pro-Gerät-Topics publishen (`…/energy/inv/{inv_id}/…`). Damit landet PV/Batterie/Wallbox in den richtigen Komponenten-Slots statt pauschal auf Anlagenebene.

### Schritt 3 — Manuellen Insel-Pfad auflösen
`connector.py:290` (manueller `read_meters()` → `meter_snapshots`-JSON) entweder pensionieren oder ebenfalls über MQTT routen. Erst danach ist die Zwei-Quellen-Architektur **echt** — kein Connector-Datenweg mehr außerhalb von MQTT.

---

## Phasen-Einordnung: zwischen Phase B und C umsetzbar? — **Nein.**

**Frage:** Lässt sich der volle Umbau (1+2+3) im Fenster zwischen Phase B (v3.34.2, released 2026-05-29) und Phase C (v3.35.0, hourly `_categorize_counter` E-Auto-Doppelmapping, frühestens 2026-06-03) einschieben?

**Bewertung — vier Gründe dagegen:**

1. **Er fasst denselben Schreibpfad an, den Phase B/C gerade stabilisiert.** Neue `energy/*_kwh`-Topics fließen in `MqttEnergySnapshot` → `aggregate_day` → Monatsdaten — exakt die Pipeline, die Phase B hardened und Phase C weiter umbaut. Eine **neue Energie-Quelle mitten im Tester-Zyklus** injiziert Rauschen, das von Phase-B-Regressionen nicht zu unterscheiden ist, und **trübt das Signal** der Phase-C-Vorbedingung (≥5 Tage ohne refactor-bezogenen Regress).

2. **Es ist ein mehrteiliges Feature, kein Hotfix.** Es braucht einen **eigenen** Tester-Zyklus. Zwei offene Refactor-Zyklen zu überlappen verletzt die sequenzielle Disziplin (`feedback_release_bundling`, `feedback_bypass_kombi_schreib_schicht`: nicht zwei Umbauten auf derselben Schreib-Schicht parallel).

3. **Phase C liegt im selben Code-Nachbarschaft.** Connector-Energie läuft durch `_compute_deltas`/`_categorize_counter`-nahe Logik — genau das, was Phase C anfasst. Beides gleichzeitig koppelt zwei Refactors, die zur Wahrung der Root-Cause-Klarheit nacheinander laufen müssen.

4. **Das Fenster ist zu klein.** 2026-06-01 → frühestens 2026-06-03 = ~2 Tage. Ein voller Umbau plus eigene Validierung passt nicht hinein; ihn hineinzuzwingen würde entweder die Qualität hetzen oder Phase C verschieben — beides unerwünscht.

> Hinweis: Auch ein auf **Schritt 1 reduzierter** Einschub wäre **kein** sauberer Zwischen-B-und-C-Kandidat — er berührt denselben Aggregator-Schreibpfad und gilt damit für die Signal-Argumentation (1.) genauso.

**Empfehlung:**

| Jetzt (zwischen B und C, unbedenklich) | Nach Phase C (eigene Etappe) |
|---|---|
| Dieses Konzept-Doc (reine Doku, kein Pipeline-Risiko) | **Schritt 1+2+3 als v3.36.0** (Phase C bleibt v3.35.0) |
| Diagnose-Absicherung bei Dirk (`/mqtt/values`, `energy`-Kategorie) | Eigener Tester-Zyklus |
| Kurzfristiger Workaround für Dirk (kWh via Node-RED publishen) | — |

→ **Phase-Reihenfolge: B (fertig) → C (v3.35.0) → Connector-MQTT-Umbau (v3.36.0).** Der Umbau wird **nicht** zwischen B und C geschoben.

---

## Kurzfristig für Dirk (vor dem Umbau)

1. **Diagnose:** Bitte um die Monitor-Werte (`/mqtt/values`, Kategorie `energy`). Leer → die Connector-Lücke ist die vollständige Erklärung. Liefert kWh → Diagnose verfeinern.
2. **Workaround:** Solange der Connector keine kWh nach MQTT schreibt, kann Node-RED `eedc/{id}/energy/pv_gesamt_kwh` (kumulativ) selbst publishen — dann zieht „Heute" + Monatsabschluss sofort an.
3. **Erwartungs-Klärung:** Die Kachel-Formulierung „Automatische Zählerstandserfassung" ist solange ein Halb-Versprechen, bis Schritt 1 steht — Wortlaut ggf. übergangsweise entschärfen.

---

## Offene Punkte / Risiken

- **Konflikt-Surface:** Bridge *und* Node-RED können beide auf dieselben Topics schreiben (z. B. `pv_gesamt_w`). Last-Writer-Wins-Flackern im Live-Fluss — kosmetisch, aber bei Schritt 2/3 mitdenken (Zwei-Quellen-Kollision, `feedback_bypass_kombi_schreib_schicht`).
- **Counter-Resets / negative Deltas:** `_compute_deltas` behandelt das bereits (`delta < 0 → end_val`). Connector-kWh durchlaufen denselben Pfad — kein Sonderfall nötig.
- **Connector-Vollständigkeit:** Nicht jeder Connector implementiert alle `MeterSnapshot`-Felder (alle `Optional`). Nur Vorhandenes publishen; Lücken füllt der Nutzer per zusätzlicher MQTT-Quelle — genau der Architektur-Vorteil.
- **`read_meters()`-Robustheit:** Periodisches Pollen erhöht die Last auf Geräte-APIs; konservatives Intervall (5 min) + Fehler-Toleranz (analog `_poll_all`).
