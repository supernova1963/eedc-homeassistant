# Sensor-Referenz: Feldnamen, Einheiten, Anforderungen

*Referenz für UI-Beschreibungen in der Datenquellen-Zuordnung und im MQTT-Setup.*

> Siehe auch: [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md) — welcher der Wärmepumpen-Zähler unten welche Kennzahl möglich macht, und was ohne ihn passiert.

> **Single Source of Truth:** Die Feld-Hilfetexte (Spalte „Hinweis") werden im Code als `hinweis`-Attribut in `backend/core/field_definitions/registry.py` gepflegt und über `GET /api/monatsdaten/feld-hinweise` an die Datenquellen-Zuordnung ausgeliefert; die Spalte „Sichten" ist dieselbe Liste, die die Zuordnung unter „ausgewertet in" zeigt (`backend/core/feld_auswertungen.py`). Die Tabellen der Eingabefelder (§1–§7) und der Export-Sensoren (§11) sind daraus erzeugt; die Export-Sensoren spiegeln `backend/services/ha_sensors_export.py` bzw. `GET /api/ha/export/definitions`.

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| **Momentan** | Aktueller Messwert zum Zeitpunkt der Abfrage (z.B. aktuelle Leistung in W) |
| **Kumulativ** | Zählerstand der stetig steigt (z.B. Stromzähler in kWh). Delta wird berechnet. |
| **Tagessensor** | Kumulativer Sensor, der täglich um 0:00 auf 0 zurückgesetzt wird (HA Utility Meter). Er hat zwei Rollen. **Als Tageswert-Feld** (Sensortyp „Tagessensor", z. B. Speicher „Ladung heute") ist er der erwartete Typ. **Als Quelle eines Zählerstands** über **rohe MQTT-Stände** ⛔ nicht geeignet: eedc erkennt den Rücksprung und liefert für Tag wie Monat **keinen Wert**, statt zwei Stände abzuziehen, die zu verschiedenen Zählerläufen gehören (#341). Hochgerechnet wird bewusst nicht — der Fehlbetrag ginge immer nach unten und sähe im Monatsabschluss aus wie eine Messung. **Nimm dort den fortlaufenden Stand** (`utility_meter` mit Zurücksetzen „nie"). Über HA ist der Rücksprung folgenlos, dort kommt der reset-bereinigte `sum`-Wert. |
| **Kumulativ oder Tagessensor** | Ein Energiefeld mit eigenem Kanal: über HA genügt beides (eedc liest den reset-bereinigten `sum`-Wert der Langzeitstatistik), über MQTT nur der fortlaufende Stand — siehe „Tagessensor". |
| **Counter** | Kumulativer Anzahl-Zähler (Total-Increasing, kein kWh). Wird strikt von kWh-Feldern getrennt — siehe „Counter vs. kWh" unten. |
| **Bidirektional** | Positiv/negativ kodiert die Richtung (z.B. +Ladung/−Entladung) |
| **`state_class`** | HA-Attribut. `total_increasing`/`total` markieren kumulative Sensoren — von HA in Long-Term Statistics persistiert. Sensoren ohne `state_class` haben **keine** LTS-Einträge → für kWh-Felder ungeeignet (siehe „LTS-Verfügbarkeit"). |
| **`*`** | **Pflichtfeld** — ohne diesen Wert fehlt eine Kernauswertung. In der Zuordnungs-Fläche mit rotem `*`; bleibt es ohne Quelle, steht der Hinweis dort rot und aufgeklappt. |
| **Alternativ-Gruppe** | Zwei Erfassungswege, von denen **einer genügt**. Ist ein Weg belegt, gilt der andere als abgedeckt und wird nicht mehr angemahnt. |

> **Wo ordne ich Sensoren zu?** In v4 unter **Einstellungen → Datenquellen** — jedes Feld bekommt **genau eine** Quelle (HA-Sensor, MQTT-Gateway, MQTT-Inbound oder keine). Details zur Fläche: [Handbuch Einstellungen §7](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung). Voraussetzung ist eine stehende Verbindung ([Integration](HANDBUCH_EINSTELLUNGEN.md#6-integration)).

> **Pflicht, optional, oder hier gar nicht?** Die Fläche stuft jedes Feld ein, damit „keine Quelle" nicht pauschal wie ein Mangel aussieht (SoT: `FELD_BEDARF` in `backend/core/field_definitions.py`):
>
> - **Pflicht** (`*`) — Anlage: Einspeisung + Netzbezug (Zählerstand) und die PV-Erzeugung. Je Gerät das jeweilige Kernfeld: Speicher Ladung/Entladung, Wärmepumpe Strom + abgegebene Wärme (*Heizwärme* **oder** *Wärme gesamt* — eines von beiden genügt), Wallbox Ladung gesamt, E-Auto gefahrene km, PV-Modul/Balkonkraftwerk Erzeugung.
> - **Optional** — alles Übrige, insbesondere **alle Live-Felder (W, %, °C)**: ohne sie bleibt nur das Live-Dashboard leer, Statistik und Wirtschaftlichkeit laufen über die kWh-Zählerstände weiter.
> - **Nicht hier zu erfassen** — das Feld ist durch einen anderen Weg abgedeckt und wird mit Begründung ausgegraut: die drei Alternativ-Gruppen (unten). Die Heimladung am E-Auto (*Heim: PV/Netz/gesamt*) wird seit v4.0.51 auch neben einer Wallbox angeboten: eine Messung am Auto zählt für dieses Auto, die Wallbox trägt den Rest — Pflicht ist sie dort nicht; nur einem Dienstwagen neben einer dienstlichen Wallbox fehlen die Felder (siehe §5).
>
> **Alternativ-Gruppen:**
>
> | Gruppe | Weg A | Weg B |
> |--------|-------|-------|
> | PV-Energie | Anlage `pv_gesamt_kwh` | je PV-Modul/Balkonkraftwerk `pv_erzeugung_kwh` |
> | PV-Leistung | Anlage `pv_gesamt_w` | je Modul `leistung_w` |
> | Netz-Leistung | `netz_kombi_w` (ein Sensor mit Vorzeichen) | `einspeisung_w` + `netzbezug_w` getrennt |
>
> **PV-Energie ist kein reines Entweder-oder:** Einzelwerte haben immer Vorrang, der Gesamtwert füllt
> nur die Lücken der Module **ohne** eigenen Wert (anteilig nach kWp, in der Anzeige gekennzeichnet).
> Beides zusammen ist deshalb der normale Übergangszustand, solange noch nicht jeder String misst.
> **Zielbild:** alle Strings erfassen und `pv_gesamt_kwh` auf „keine" setzen — zusammengefasst
> höchstens je Ausrichtung/Neigung, sonst kippt die Prognose für Anlagen mit mehreren Ausrichtungen.
> Bei den beiden Leistungs-Gruppen gilt das Entweder-oder dagegen strikt: ein einziger Einzelsensor
> macht den Gesamtsensor im Live-Dashboard wirkungslos.
>
> **„Keine Quelle" ist kein Fehler:** Alle kWh-Felder lassen sich im Monatsabschluss auch manuell erfassen. Rot heißt „hier fehlt noch etwas", nie „falsch".

---

