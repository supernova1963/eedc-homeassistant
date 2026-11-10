# Sensor-Referenz: Feldnamen, Einheiten, Anforderungen

> **Erzeugt — nicht von Hand ändern —** Bausteine in `docs/sensor-referenz/`, `scripts/groessen-uebersicht.sh`. Die Tabellen der Eingabefelder (§1–§7) und der Export-Sensoren (§11) kommen aus dem Code; ihre Spalte «Hinweise» bei den Export-Sensoren aus `eedc/backend/tests/groessen_hand.yaml`.

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

## 1. Basis-Felder (Zähler / Netzübergabe)

### Monatserfassung (kWh)

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `einspeisung_kwh` | Einspeisung | kWh | Kumulativ oder Tagessensor | pflicht | Kumulativer kWh-Zähler (oder Tagessensor mit 0:00-Reset) der ins Netz eingespeisten Energie. Immer ≥ 0; bei Zweirichtungszähler nur den Einspeise-Anteil. | Cockpit → Monat · Cockpit → Jahr · Auswertungen → Tabelle · HA-Sensoren | — |
| `netzbezug_kwh` | Netzbezug | kWh | Kumulativ oder Tagessensor | pflicht | Kumulativer kWh-Zähler (oder Tagessensor mit 0:00-Reset) der aus dem Netz bezogenen Energie. Immer ≥ 0; bei Zweirichtungszähler nur den Bezugs-Anteil. | Cockpit → Monat · Cockpit → Jahr · Auswertungen → Tabelle · HA-Sensoren | — |
| `globalstrahlung_kwh_m2` | Globalstrahlung | kWh/m² | kein Sensor — Monatsabschluss | optional | Globalstrahlung im Monat (kWh/m²). eedc holt sie automatisch vom Wetterdienst des Standorts (Bright Sky/DWD in Deutschland, sonst Open-Meteo) — nur in ein leeres Feld; ein selbst eingetragener Wert bleibt stehen. | Cockpit → Aussicht · Auswertungen → Tabelle | — |
| `sonnenstunden` | Sonnenstunden | h | kein Sensor — Monatsabschluss | optional | Sonnenstunden im Monat (h). eedc holt sie automatisch vom Wetterdienst des Standorts (Bright Sky/DWD in Deutschland, sonst Open-Meteo) — nur in ein leeres Feld; ein selbst eingetragener Wert bleibt stehen. | Cockpit → Aussicht · Auswertungen → Tabelle | — |
| `durchschnittstemperatur` | Ø Temperatur | °C | kein Sensor — Monatsabschluss | optional | Monatsdurchschnittstemperatur (°C). „Auto-Fill" holt sie aus den gemessenen Außentemperaturen des Monats, sonst vom Wetterdienst des Standorts — ein selbst eingetragener Wert bleibt stehen und lässt sich jederzeit überschreiben. | Komponenten → Wärmepumpe · Auswertungen → Tabelle | — |
| `netzbezug_durchschnittspreis_cent` | Ø Strompreis | ct/kWh | kein Sensor — Monatsabschluss | optional | Dein abgerechneter Ø-Arbeitspreis dieses Monats (ct/kWh) — er schlägt jede Berechnung. Trägst du nichts ein, rechnet eedc mit dem verbrauchsgewichteten Ø deiner mitgeschriebenen Stundenpreise (Tibber/aWATTar/EPEX) und bei einem Zeittarif (HT/NT) mit dem über deinen Netzbezug gewichteten Tarifpreis. Erst wenn beides fehlt — etwa bei handgetragenen Monatswerten — gilt der Preis aus den Stammdaten. | Cockpit → Monat · Auswertungen → Finanzen | Anlage: `dynamischer_tarif` |
| `einspeise_durchschnittspreis_cent` | Einspeisevergütung (Monat) | ct/kWh | kein Sensor — Monatsabschluss | optional | Vergütungssatz dieses Monats (ct/kWh), z. B. der OeMAG-Marktpreis. Schlägt den Stammwert des Tarifs; ohne Eintrag rechnet der Monat mit dem Stammwert. eedc holt den Satz nicht automatisch ab. | Auswertungen → Finanzen · Auswertungen → Tabelle | Anlage: `variable_einspeisung` |
| `kraftstoffpreis_euro` | Ø Benzinpreis | €/L | kein Sensor — Monatsabschluss | optional | Ø Kraftstoffpreis des Monats (€/L) für den E-Auto-vs-Verbrenner-Vergleich. Wird sonst automatisch aus dem EU Weekly Oil Bulletin geholt. | Komponenten → E-Auto · Cockpit → Jahr | Anlage: `hat_eauto` |
| `gaspreis_cent_kwh` | Ø Gas-/Ölpreis | ct/kWh | kein Sensor — Monatsabschluss | optional | Ø Gas-/Ölpreis des Monats (ct/kWh) für den Wärmepumpe-vs-fossile-Heizung-Vergleich. | Komponenten → Wärmepumpe · Cockpit → Monat | Anlage: `hat_waermepumpe` |
| `sonderkosten_euro` | Sonderkosten | € | kein Sensor — Monatsabschluss | optional | Einmalige Sonderkosten des Monats (€), z. B. Wartung oder Reparatur. Optional. | — Handeingabe im Monatsabschluss, nicht auf der Zuordnungs-Fläche | — |
| `sonderkosten_beschreibung` | Beschreibung | — | kein Sensor — Monatsabschluss | optional | Kurzbeschreibung der Sonderkosten (Freitext). Optional. | — Handeingabe im Monatsabschluss, nicht auf der Zuordnungs-Fläche | — |
| `notizen` | Notizen | — | kein Sensor — Monatsabschluss | optional | Freie Notizen zum Monat (Freitext). Optional. | — Handeingabe im Monatsabschluss, nicht auf der Zuordnungs-Fläche | — |

### Live-Dashboard (W)

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `einspeisung_w` | Einspeisung | W | Momentanwert | optional (netz_live) | Momentane Einspeiseleistung in W — nur für das Live-Dashboard. Alternative: ein einzelner Sensor mit Vorzeichen unter „Netz kombiniert (±)“. | Cockpit → Live · Cockpit → Tag | — |
| `netzbezug_w` | Netzbezug | W | Momentanwert | optional (netz_live) | Momentane Bezugsleistung in W — nur für das Live-Dashboard. Alternative: ein einzelner Sensor mit Vorzeichen unter „Netz kombiniert (±)“. | Cockpit → Live · Cockpit → Tag | — |
| `netz_kombi_w` | Netz kombiniert (±) | W | Momentanwert | optional (netz_live) | EIN Netz-Sensor mit Vorzeichen (+ Bezug / − Einspeisung) statt zweier getrennter; wirkt nur, wenn „Einspeisung (W)“ und „Netzbezug (W)“ auf „keine“ stehen. Zeigt er in die falsche Richtung, dreht ihn das ⇅-Symbol am Wert. Die kWh-Zähler für Einspeisung und Netzbezug bleiben daneben zugeordnet — sie liefern die Mengen. | Cockpit → Live · Cockpit → Tag | — |
| `pv_gesamt_w` | PV gesamt | W | Momentanwert | optional (pv_live) | Momentane PV-Leistung der ganzen Anlage in W. Nur nötig, wenn die PV-Module keine eigenen Leistungs-Sensoren haben — sobald dort einer zugeordnet ist, wird diese Angabe ignoriert. | Cockpit → Live · Cockpit → Tag | — |
| `aussentemperatur_c` | Außentemperatur | °C | Momentanwert | optional | Außentemperatur in °C für Live-Anzeige und Wärmepumpen-Kontext. Optional — fehlt sie, nutzt eedc die Wetterdaten des Standorts. | Cockpit → Live | — |
| `strompreis` | Strompreis (dynamischer Tarif) | ct/kWh | Momentanwert | optional | HA-Sensor mit dem aktuellen Arbeitspreis (Tibber, aWATTar, EPEX-Endpreis). eedc schreibt daraus die Stundenpreise mit und rechnet damit den verbrauchsgewichteten Ø-Bezugspreis des Monats sowie den Ø-Ladepreis der Speicher-Netzladung. Einheit ct/kWh, €/kWh oder €/MWh — eedc rechnet um. Ohne Sensor gilt der Arbeitspreis aus den Stammdaten. | Cockpit → Live | Anlage: `dynamischer_tarif` |

### MQTT-Topic-Mapping (Basis)

Welche MQTT-Topics eedc für die Anlage erwartet — die Live-Topics der Basis-Felder und die drei Zählerstände `pv_gesamt_kwh`, `einspeisung_kwh`, `netzbezug_kwh` —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

## 2. PV-Module / Balkonkraftwerk

Der **Wechselrichter** steht mit in den Tabellen dieses Kapitels (Spalte „Typ"): Er ist kein PV-Erzeuger. Sein Monatsfeld bleibt nur, damit eine bestehende Zuordnung sichtbar und entfernbar ist, sein Live-Feld wertet eedc nicht aus — die Spalte „Sichten" nennt den Grund.

### Monatserfassung

| Typ | Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|---|
| `pv-module` | `pv_erzeugung_kwh` | PV-Erzeugung | kWh | Kumulativ oder Tagessensor | pflicht (pv_energie) | Kumulativer kWh-Zähler (oder Tagessensor) der erzeugten Energie dieses PV-Strings. Immer ≥ 0. Alternativ anteilig per kWp aus dem PV-Gesamt-Sensor verteilt. | Komponenten → PV-Module · Cockpit → Monat · HA-Sensoren | — |
| `balkonkraftwerk` | `pv_erzeugung_kwh` | Erzeugung | kWh | Kumulativ oder Tagessensor | pflicht (pv_energie) | Kumulativer kWh-Zähler (oder Tagessensor) der BKW-Erzeugung vom Wechselrichter. Immer ≥ 0. Sind dem Balkonkraftwerk PV-Module zugeordnet, gilt dieser Wert als deren Gesamtsumme: eigene Modulwerte haben Vorrang, dieser hier füllt die Lücken. | Komponenten → Balkonkraftwerk · Cockpit → Monat | — |
| `balkonkraftwerk` | `eigenverbrauch_kwh` | Eigenverbrauch | kWh | Kumulativ — nur Monatswert, kein Kanal | optional | Direkt im Haushalt verbrauchte BKW-Erzeugung (kWh, kumulativ oder Tagessensor). Optional — leer lassen: eedc leitet den Eigenverbrauch aus der Bilanz am Hauszähler ab. Nur eintragen, wenn für den Monat keine Erzeugung vorliegt. | Komponenten → Balkonkraftwerk · Auswertungen → Finanzen | — |
| `balkonkraftwerk` | `speicher_ladung_kwh` | Speicher Ladung | kWh | kein Sensor — manuell/Import | optional | In den BKW-Akku geladene Energie (kWh). Nur manuell oder per Import — für Sensor-/MQTT-Zuordnung den Akku als eigene Speicher-Investition mit Parent Balkonkraftwerk erfassen. | Cockpit → Monat · Komponenten → Balkonkraftwerk | `hat_speicher` |
| `balkonkraftwerk` | `speicher_entladung_kwh` | Speicher Entladung | kWh | kein Sensor — manuell/Import | optional | Aus dem BKW-Akku entladene Energie (kWh). Nur manuell oder per Import — für Sensor-/MQTT-Zuordnung den Akku als eigene Speicher-Investition mit Parent Balkonkraftwerk erfassen. | Cockpit → Monat · Komponenten → Balkonkraftwerk | `hat_speicher` |
| `wechselrichter` | `pv_erzeugung_kwh` | PV-Erzeugung | kWh | kein Sensor — manuell/Import | optional | ⚠ Nicht mehr verwenden. Die PV-Erzeugung gehört an die PV-Module (oder an das Balkonkraftwerk); der anlagenweite Zähler steht unter Anlage (Basis) als „PV-Erzeugung Zählerstand“. Ein Wert an dieser Stelle wird nicht ausgewertet. Das Feld erscheint nur noch, solange hier eine alte Zuordnung hängt — entferne sie und ordne den Zähler neu zu. | — Der Wechselrichter ist KEIN PV-Erzeuger (Entscheid Gernot 24.08.2026). Das Monatsfeld steht nur noch als `nur_manuell` in der Registry, damit eine BESTEHENDE Zuordnung sichtbar und entfernbar bleibt; `imd_typ_beitrag` hat für diesen Typ bewusst keinen Zweig. Wer den Wert pflegt, sieht ihn nirgends — das ist der gewollte Rückbau, aber die Fläche sagt es heute nicht. | — |

> **Ein Balkonkraftwerk mit Akku: den Akku als eigene Speicher-Investition erfassen.**
> Neu anlegen, Typ *Speicher*, und unter **Gehört zu** das Balkonkraftwerk wählen. Nur so
> hat der Akku Live-Leistung, Ladestand, einen Knoten im Energiefluss und Tages-/
> Stundenwerte — er nutzt dann die normalen Speicher-Felder `ladung_kwh` /
> `entladung_kwh`, und deren Sensoren ordnest du bei dieser Speicher-Investition zu.
>
> Die beiden BKW-eigenen Felder `speicher_ladung_kwh`/`speicher_entladung_kwh` sind der
> **frühere zweite Weg**. Sie bleiben erfassbar — bereits gepflegte Werte bleiben
> sichtbar und im Monatsabschluss wie im CSV-Import änderbar —, kennen aber nur einen
> **Monatswert** und lassen sich deshalb **nicht mehr als Sensor- oder MQTT-Quelle
> zuordnen**. Wer sie gepflegt hat, bekommt im Daten-Checker einen Hinweis mit dem
> Umstellungsweg; es geht dabei nichts verloren.
>
> **`eigenverbrauch_kwh`** bleibt zuordenbar, liefert aber ebenfalls **nur** den
> Monatswert (HA-Langzeitstatistik oder von Hand/per Import). Es ist kein Bilanz-Zähler und
> in der Regel leer zu lassen: eedc leitet den BKW-Eigenverbrauch aus der Bilanz am
> Hauszähler ab (der Anteil des Balkonkraftwerks an der Erzeugung hinter dem Zähler) und
> nimmt einen eingetragenen Wert nur in einem Monat, in dem die Erzeugung fehlt. Dieselbe
> Entity wie bei der Erzeugung hier zuzuordnen bringt deshalb nichts. Wer es per **MQTT**
> publiziert hat: das Topic wurde bis v4.0.4 fälschlich auf den Erzeugungs-Kanal gelegt und
> konnte die „Heute"-PV-Kachel überschreiben; das ist behoben.

> **`pv_erzeugung_kwh` steht für drei verschiedene Größen — je nachdem, wo es auftaucht.** Hier in der
> Monatserfassung ist es die Erzeugung **dieses einen** Moduls. Daneben gibt es den monatlichen
> **PV-Gesamtwert** der Anlage (gleicher Name, Anlagen-Ebene — Grundlage der kWp-Verteilung, wenn kein
> Pro-Modul-Wert existiert) und ein **Auswertungs-Feld** gleichen Namens, das PV-Module **+**
> Balkonkraftwerk zusammenfasst. Der Name bleibt bewusst unverändert, weil er zugleich MQTT-Topic,
> CSV-Spalte und Backup-Feld ist — eine Umbenennung wäre nach außen ein Bruch. Siehe
> [Glossar](GLOSSAR.md#energie--bilanzen).

### Live-Dashboard

| Typ | Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|---|
| `pv-module` | `leistung_w` | Leistung | W | Momentanwert | optional (pv_live) | Momentane Leistung dieses Strings in W. Ohne eigenen Sensor je Modul nutzt eedc „PV gesamt (W)“ der Anlage — sobald hier einer zugeordnet ist, hat er Vorrang. | Cockpit → Live | — |
| `balkonkraftwerk` | `leistung_w` | Leistung | W | Momentanwert | optional (pv_live) | Momentane Leistung des Balkonkraftwerks in W. Sind ihm PV-Module zugeordnet, gilt hier dieselbe Regel wie beim Monatswert: die Module tragen die Leistung, dieser Wert füllt nur noch ihre Lücken — messen alle selbst, wird er nicht mehr gelesen. | Cockpit → Live | — |
| `wechselrichter` | `leistung_w` | Leistung | W | Momentanwert | optional (pv_live) | Momentane AC-Ausgangsleistung des Wechselrichters in W. | — Kein Leser (N-685, gemessen 11.10.2026): Jeder Live-Pfad überspringt den Wechselrichter per `SKIP_TYPEN` vor dem Lesen (`live_komponenten_builder`, `live_tagesverlauf_service`, `live_history_service`, `live_sensor_config`), der Verbrauchsprofil-Pfad liest nur `ERZEUGER_TYPEN`. Die Datenquellen-Fläche zeigt den Wechselrichter seit `00b979c69` (27.04.2026) gar nicht (`mqtt_topic_registry.build_expected_topics` überspringt `SKIP_TYPEN`). Bis dahin stand hier „Cockpit → Live“ — eine Wegbeschreibung, die nie stimmte. | — |

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

Für den **Akku eines Balkonkraftwerks** gibt es hier bewusst kein Topic: er wird als
eigene Speicher-Investition erfasst und publiziert unter deren ID auf
`…/energy/inv/{speicher_id}_{name}/ladung_kwh` bzw. `…/entladung_kwh` (siehe Speicher).

---

## 3. Speicher (Batterie)

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `ladung_kwh` | Ladung — mit `laedt_aus_netz`: «Ladung (gesamt, inkl. Netz)» | kWh | Kumulativ oder Tagessensor | pflicht | Gesamte in den Speicher geladene Energie, Netzladung eingeschlossen (kWh, kumulativer Zähler oder Tagessensor). Immer ≥ 0. Messstelle passend zur Kopplung: bei AC hausseitig hinter dem Batterie-Wechselrichter, bei DC am Batterie-Anschluss. Ladung und Entladung von derselben Seite — sonst enthält der Wirkungsgrad die Wandlung nur in eine Richtung. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren | — |
| `entladung_kwh` | Entladung | kWh | Kumulativ oder Tagessensor | pflicht | Gesamte aus dem Speicher entladene Energie (kWh, kumulativer Zähler oder Tagessensor). Immer ≥ 0. Dieselbe Messstelle wie die Ladung (s. dort) — bei gemischten Seiten misst der Wirkungsgrad die Messstelle statt den Speicher. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren | — |
| `ladung_netz_kwh` | Netzladung | kWh | Kumulativ oder Tagessensor | optional | Anteil der Ladung, der aus dem Netz kam (kWh, kumulativ oder Tagessensor). Optional und muss ≤ Ladung sein. Nur nötig, wenn der Speicher aus dem Netz lädt — bei reiner PV-Ladung leer lassen. | Cockpit → Monat · Komponenten → Speicher | `laedt_aus_netz` |
| `speicher_ladepreis_cent` | Ø Ladepreis | ct/kWh | kein Sensor — manuell/Import | optional | Ø Preis der Netzladung in ct/kWh. Nur bei Arbitrage relevant (gezielt günstig laden) — Backup-/Notladung läuft zum normalen Bezugspreis. Im Monatsabschluss schlägt eedc einen Wert aus Netzladung und mitgeschriebenen Stundenpreisen vor; überschreibbar, etwa mit dem Preis aus der Rechnung. | Komponenten → Speicher · Cockpit → Monat | `arbitrage_faehig` |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | Momentanwert | optional | Momentane Lade-/Entladeleistung in W. Ein vorzeichenbehafteter Sensor genügt (+ laden / − entladen); zeigt er in die falsche Richtung, dreht ihn das ⇅-Symbol am Wert. | Cockpit → Live | — |
| `soc` | Ladestand | % | Momentanwert | optional | Ladestand des Speichers in Prozent (0–100). | Cockpit → Live | — |

**Ladung und Entladung des Tages** sind keine eigenen Registry-Felder: Es sind die Monatsfelder `ladung_kwh`/`entladung_kwh` der Tabelle „Monatserfassung", hier mit einem Tagessensor zugeordnet.

| Feld | Label | Einheit | Sensortyp | Beschreibung | Ausgewertet in |
|------|-------|---------|-----------|-------------|-----------------|
| `ladung_kwh` | Ladung heute | kWh | Tagessensor | Tages-Ladeenergie. Optional — wenn vorhanden, wird für heute-kWh-Anzeige bevorzugt (genauer als Trapez-Integration aus W-Sensor). Wird täglich um 0:00 auf 0 zurückgesetzt. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren |
| `entladung_kwh` | Entladung heute | kWh | Tagessensor | Tages-Entladeenergie. Optional — wie `ladung_kwh`. Wird täglich auf 0 zurückgesetzt. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren |

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

## 4. Wärmepumpe

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `stromverbrauch_kwh` | Stromverbrauch | kWh | Kumulativ oder Tagessensor | pflicht (wp_strom) | Gesamter elektrischer Energieverbrauch der WP (kWh, kumulativ oder Tagessensor). Auch bei getrennter Messung sinnvoll: misst er mehr als Heizen + Warmwasser zusammen (Standby, Steuerung, Umwälzpumpen), gilt sein Wert als Verbrauch des Geräts und die Differenz erscheint als „nicht aufgeteilt“. | Komponenten → Wärmepumpe · Cockpit → Monat · HA-Sensoren | `!getrennte_strommessung` (weich) |
| `strom_heizen_kwh` | Strom Heizen | kWh | Kumulativ oder Tagessensor | pflicht (wp_strom) | Elektrische Energie für den Heizbetrieb (kWh, kumulativ oder Tagessensor). Nur bei getrennter Strommessung. | Komponenten → Wärmepumpe · Cockpit → Tag · Cockpit → Monat | `['getrennte_strommessung', '!brauchwasser']` (weich) |
| `strom_warmwasser_kwh` | Strom Warmwasser | kWh | Kumulativ oder Tagessensor | pflicht (wp_strom) | Elektrische Energie für die Warmwasserbereitung (kWh, kumulativ oder Tagessensor). Nur bei getrennter Strommessung. | Komponenten → Wärmepumpe · Cockpit → Tag · Cockpit → Monat | `['getrennte_strommessung', '!luft_luft']` |
| `heizenergie_kwh` | Heizwärme | kWh | Kumulativ oder Tagessensor | pflicht (wp_waerme) | Abgegebene Heizwärme (thermisch, NICHT Strom!) in kWh, kumulativ oder Tagessensor. Ohne Wärmemengenzähler aus Stromverbrauch × JAZ berechnet. | Komponenten → Wärmepumpe · Cockpit → Monat · Auswertungen → Finanzen | `!brauchwasser` (weich) |
| `warmwasser_kwh` | Warmwasser-Wärme | kWh | Kumulativ oder Tagessensor | optional | Abgegebene Warmwasser-Wärme (thermisch) in kWh, kumulativ oder Tagessensor. Optional — misst EIN Zähler Heizung und Warmwasser zusammen, gehört sein Wert unter „Wärme gesamt“. | Komponenten → Wärmepumpe · Cockpit → Monat | `!luft_luft` |
| `waerme_kwh` | Wärme gesamt | kWh | Kumulativ oder Tagessensor | pflicht (wp_waerme) | Abgegebene Wärme GESAMT (thermisch, NICHT Strom!) in kWh, kumulativ oder Tagessensor — für EINEN Wärmemengenzähler, der Heizung und Warmwasser zusammen misst. Wer getrennte Zähler hat, lässt das Feld leer. Trägt hier ein Wert, gilt er als die Wärme des Geräts; Heizwärme und Warmwasser-Wärme stehen dann nur noch als Aufteilung daneben. | Komponenten → Wärmepumpe · Cockpit → Monat · HA-Sensoren | — |
| `heizstab_strom_kwh` | Strom Zusatzheizung | kWh | Kumulativ oder Tagessensor | optional | Strom, den der Heizstab bzw. die Zusatz- oder Notheizung dieses Geräts verbraucht hat (kWh, kumulativer Zähler). Optional. Gemeint ist ein Heizstab HINTER dem Stromzähler der Wärmepumpe: sein Strom steckt schon im Stromverbrauch und wird nie dazugezählt. eedc zeigt damit neben der Arbeitszahl eine zweite Zahl „AZ ohne Zusatzheizung“ (Heizstab mit Wirkungsgrad 1 aus Wärme und Strom herausgerechnet). Hat der Heizstab einen eigenen Zähler am Hausnetz, gehört er als Sonstiger Verbraucher erfasst, nicht hierher. Liefert das Gerät nur eine Leistung (W), bildet in Home Assistant der Helfer „Integral“ (Riemann-Summe) daraus einen Zähler; ein Tageszähler (Utility Meter mit täglichem Reset) ist kein kumulativer Zähler. | Komponenten → Wärmepumpe · Cockpit → Tag · Cockpit → Monat · Cockpit → Jahr | — |
| `netzbezug_eigener_tarif_kwh` | Netzbezug zum WP-Tarif | kWh | Kumulativ oder Tagessensor | optional | Die Menge, die dein Versorger zum Wärmepumpen-Tarif abrechnet (kWh, kumulativer Zähler). Optional — nur mit eigenem Wärmepumpen-Tarif wirksam. Zählerkaskade (Z1 am Netzanschluss, Z2 für Haus und PV, Wärmepumpe dazwischen): Z1-Bezug minus Z2-Bezug, als Template-Sensor mit state_class „total“ (nicht „total_increasing“). Eigener Zähler, der nicht hinter der PV hängt: derselbe Sensor wie „Stromverbrauch“. eedc rechnet damit die Stromrechnung mit beiden Tarifen und bewertet den PV-Anteil der Wärmepumpe zum Wärmepumpen-Tarif. | Cockpit → Monat · Cockpit → Jahr | — |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `leistung_w` · je Innengerät zusätzlich `leistung_w-<id>` | Leistung gesamt | W | Momentanwert | optional | Momentane elektrische Leistungsaufnahme der Wärmepumpe in W (nicht die abgegebene Wärmeleistung). | Cockpit → Live | — |
| `leistung_heizen_w` | Leistung Heizen | W | Momentanwert | optional | Elektrische Leistungsaufnahme im Heizbetrieb in W. Nur sinnvoll, wenn Heizen und Warmwasser getrennt gemessen werden. | Cockpit → Live · Cockpit → Tag | `!brauchwasser` (weich) |
| `leistung_warmwasser_w` | Leistung Warmwasser | W | Momentanwert | optional | Elektrische Leistungsaufnahme der Warmwasserbereitung in W. Nur sinnvoll bei getrennter Messung. | Cockpit → Live · Cockpit → Tag | `!luft_luft` (weich) |
| `leistung_kuehlen_w` | Leistung Kühlen | W | Momentanwert | optional | Elektrische Leistungsaufnahme im Kühlbetrieb in W. Nur sinnvoll, wenn der Kühlbetrieb getrennt gemessen wird — reine Anzeige: erscheint im Live-Bild und als eigene Fläche im Tagesverlauf, die Mengen kommen aus dem kWh-Zähler. | Cockpit → Live · Cockpit → Tag | `kuehlt` (weich) |
| `warmwasser_temperatur_c` | Warmwasser-Temperatur | °C | Momentanwert | optional | Temperatur im Warmwasserspeicher in °C — reine Anzeige, geht in keine Berechnung ein. | Cockpit → Live · Komponenten → Wärmepumpe · Cockpit → Tag | `!luft_luft` (weich) |
| `vorlauf_temperatur_c` | Vorlauf | °C | Momentanwert | optional | Vorlauftemperatur des Heizkreises in °C — reine Anzeige, geht in keine Berechnung ein. Stündliche Mittelwerte entstehen aus der HA-Langzeitstatistik des Sensors (`state_class: measurement`), über MQTT aus der Mitschrift von eedc ab der Zuordnung (nicht rückwirkend). | Komponenten → Wärmepumpe · Cockpit → Tag | — |
| `ruecklauf_temperatur_c` | Rücklauf | °C | Momentanwert | optional | Rücklauftemperatur des Heizkreises in °C — reine Anzeige, geht in keine Berechnung ein. Stündliche Mittelwerte entstehen aus der HA-Langzeitstatistik des Sensors (`state_class: measurement`), über MQTT aus der Mitschrift von eedc ab der Zuordnung (nicht rückwirkend). | Komponenten → Wärmepumpe · Cockpit → Tag | — |
| `heizstab_leistung_w` | Leistung Zusatzheizung | W | Momentanwert | optional | Momentane elektrische Leistung der Zusatzheizung (Heizstab) in W — reine Anzeige: aus diesem Feld entsteht keine kWh, und es geht in keine Summe ein. Über 0 W steht an der Gerätekarte im Überblick „Zusatzheizung aktiv“. Stündliche Mittelwerte entstehen aus der HA-Langzeitstatistik des Sensors (`state_class: measurement`). | Komponenten → Wärmepumpe | — |
| `betriebsmodus` | Betriebsmodus | — | Zustand | optional | Die `climate`-Entität der Klimaanlage/Wärmepumpe (z. B. `climate.wohnzimmer`) — sie meldet Heizen, Kühlen, Entfeuchten oder Aus. Optional: ohne sie zählt eedc den Stromverbrauch wie bisher als eine Zahl, mit ihr kann es sagen, welcher Teil davon ins Heizen und welcher ins Kühlen ging. Ein Zustand, kein Messwert. Über MQTT (Inbound-Topic, nicht über das Gateway) versteht eedc dieselben Wörter oder einen Zahlencode: 0 Aus · 1 Heizen · 2 Warmwasser · 3 Kühlen · 4 Lüften · 5 Entfeuchten. Leerlauf gibt es nur über Home Assistant. | Cockpit → Live · Komponenten → Wärmepumpe | — |
| `soll_temperatur_c` · je Innengerät zusätzlich `soll_temperatur_c-<id>` | Soll-Temperatur | °C | Momentanwert | optional | Eingestellte Zieltemperatur in °C — reine Anzeige, geht in keine Berechnung ein. | Cockpit → Live | `luft_luft` |
| `ist_temperatur_c` · je Innengerät zusätzlich `ist_temperatur_c-<id>` | Raumtemperatur | °C | Momentanwert | optional | Gemessene Raumtemperatur in °C — reine Anzeige, geht in keine Berechnung ein. | Cockpit → Live | `luft_luft` |

> ⚠️ **`leistung_w` verdrängt `leistung_heizen_w`, `leistung_warmwasser_w` und
> `leistung_kuehlen_w`.** Ist die Gesamtleistung zugeordnet, wertet eedc die drei
> Funktions-Sensoren im Tagesverlauf **nicht** aus — die Wärmepumpe erscheint dort als **eine**
> Fläche. Bleibt `leistung_w` leer, bekommt jeder zugeordnete Funktions-Sensor im Tagesverlauf
> von *Cockpit → Live* eine eigene Fläche mit eigenem Namen (Heizen, Warmwasser, Kühlen). Der
> **Stundenverlauf des Tages** schlüsselt erst ab **zwei** Funktions-Sensoren auf — ein einzelner
> wäre dort die Gerätereihe unter anderem Namen. Beides ist richtig, es ist eine Wahl: Die
> Gesamtleistung ist der vollständige Anlagenwert (und die einzige Quelle des
> Wärmepumpen-Anteils in der Verbrauchsprognose), die getrennten Felder sind die feinere
> Auskunft — die Verbrauchsprognose nimmt `leistung_warmwasser_w` und `leistung_kuehlen_w` aus den
> Tagesprofilen, um diese Anteile nicht mit der Außentemperatur zu skalieren. Details und Folgen: [Handbuch Wärme & Klima §5, Schritt 6](HANDBUCH_WAERME_KLIMA.md#schritt-6--live-werte-optional).
>
> ⚠️ **Kein Ersatz für kWh-Zähler.** Diese Felder sind Momentanleistungen und speisen die
> Mengen nicht — Stromverbrauch, Wärme und alle Arbeitszahlen kommen aus den kWh-Feldern oben.

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

### 4a. Verbrauch je Betriebsart und je Innengerät

> **Bei einer Klimaanlage stehen diese Felder gleich mit da.** An jeder anderen
> Wärmepumpenart findest du sie unter *Einstellungen → Datenquellen* beim Gerät
> hinter **„Weitere Größen erfassen"** — sie sind dort seltener, aber genauso
> zuordenbar. Wer einen getrennten Kühlzähler an seiner
> Luft-Wasser- oder Sole-Wasser-Wärmepumpe hat, trägt ihn dort ein; sobald ein
> Sensor zugeordnet ist, steht das Feld oben bei den anderen.
>
> Alle Felder sind **optional**: kein Sensor, keine Anzeige.

Ein Gerät, das heizt, kühlt, lüftet und entfeuchtet, tut das oft über
**denselben** Zähler. Wer die Anteile getrennt messen kann, trägt sie hier ein —
sie sind **Teilmengen** des Gesamtverbrauchs und werden nie dazuaddiert.

⚠️ **Kühlen, Lüften und Entfeuchten zählen nicht in die Arbeitszahl.** Sie
erzeugen keine Wärme, die sich messen ließe; läge ihr Strom im Nenner, sähe eine
Anlage, die im Sommer kühlt oder viel lüftet, wie eine schlechte Heizung aus.
Für Wirtschaftlichkeit und CO₂ gilt beim Kühlen dasselbe schon länger. Ist der
ganze Verbrauch eines Zeitraums Kühlbetrieb, steht statt der Arbeitszahl der
Grund dafür.

**Lüften und Entfeuchten bekommen eine eigene Zeile in der Aufteilung, sobald du
einen Zähler dafür zugeordnet hast** — vorher stecken sie in „nicht aufgeteilt".
Eine **Kennzahl** bekommen sie bewusst nicht: Es gibt keinen Nutzen, gegen den
man sie rechnen könnte. Misst du zusätzlich ihre *abgegebene Nutzenergie*, steht
sie seit v4.0.45 als eigene **Mengenzeile** daneben — im Komponenten-Hub und im
Wärme/Klima-Block von Cockpit → Monat/Jahr, und nur dann, wenn ein Zähler etwas
gemeldet hat.

**Nutzenergie Heizbetrieb ist die Heizwärme deines Geräts.** Hast du keinen
Wärmemengenzähler am Gerät selbst (Feld *Heizwärme* bzw. *Wärme gesamt*), rechnet
eedc seit v4.0.45 mit ihr: Sie trägt dann die Wärme-Kachel und die Arbeitszahl.
Ist beides gepflegt, gewinnt der Gerätezähler — er misst mehr als eine einzelne
Betriebsart. Bei mehreren Innengeräten werden ihre Werte summiert; ein Wert am
Gerät schlägt die Summe seiner Innengeräte und wird nie dazuaddiert.

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `betriebsart_strom_heizen_kwh` · je Innengerät zusätzlich `betriebsart_strom_heizen_kwh-<id>` | Strom Heizbetrieb | kWh | Kumulativ oder Tagessensor | optional | Betriebsart-Zähler; hat Vorrang vor „Strom Heizen“. Wer getrennt misst, lässt dieses Feld leer. Elektrische Energie, die dieses Gerät im Heizbetrieb verbraucht hat (kWh, kumulativer Zähler oder Tagessensor). **Teilmenge** des Gesamtverbrauchs — eedc addiert sie nie dazu. Liegt dieser Wert vor, hat er Vorrang vor der Aufteilung, die eedc sonst aus dem Betriebsmodus ableitet — und zwar für **alle** Betriebsarten dieses Monats: sobald hier ein Zähler steht, zählt für dieses Gerät nur noch Gemessenes. Eine Betriebsart ohne Zähler erscheint dann unter „nicht aufgeteilt“. In Home Assistant bekommt man ihn mit einem **Utility Meter** (Helfer) auf den Energie-Sensor des Geräts, mit einem Tarif je Betriebsart. ⚠ An Multisplit-Geräten misst kein Innengerät seinen eigenen Anteil: Was dort als Verbrauch erscheint, ist der Anteil des Außengeräts, der dem gerade anfordernden Innengerät zugeschrieben wird. | Komponenten → Wärmepumpe · Cockpit → Tag | `luft_luft` (weich) |
| `betriebsart_strom_kuehlen_kwh` · je Innengerät zusätzlich `betriebsart_strom_kuehlen_kwh-<id>` | Strom Kühlbetrieb | kWh | Kumulativ oder Tagessensor | optional | Elektrische Energie, die dieses Gerät im Kühlbetrieb verbraucht hat (kWh, kumulativer Zähler oder Tagessensor). **Teilmenge** des Gesamtverbrauchs — eedc addiert sie nie dazu. Liegt dieser Wert vor, hat er Vorrang vor der Aufteilung, die eedc sonst aus dem Betriebsmodus ableitet — und zwar für **alle** Betriebsarten dieses Monats: sobald hier ein Zähler steht, zählt für dieses Gerät nur noch Gemessenes. Eine Betriebsart ohne Zähler erscheint dann unter „nicht aufgeteilt“. In Home Assistant bekommt man ihn mit einem **Utility Meter** (Helfer) auf den Energie-Sensor des Geräts, mit einem Tarif je Betriebsart. ⚠ An Multisplit-Geräten misst kein Innengerät seinen eigenen Anteil: Was dort als Verbrauch erscheint, ist der Anteil des Außengeräts, der dem gerade anfordernden Innengerät zugeschrieben wird. | Komponenten → Wärmepumpe · Cockpit → Tag | `kuehlt` (weich) |
| `betriebsart_strom_lueften_kwh` · je Innengerät zusätzlich `betriebsart_strom_lueften_kwh-<id>` | Strom Lüftbetrieb | kWh | Kumulativ oder Tagessensor | optional | Elektrische Energie, die dieses Gerät im Lüftbetrieb verbraucht hat (kWh, kumulativer Zähler oder Tagessensor). **Teilmenge** des Gesamtverbrauchs — eedc addiert sie nie dazu. Liegt dieser Wert vor, hat er Vorrang vor der Aufteilung, die eedc sonst aus dem Betriebsmodus ableitet — und zwar für **alle** Betriebsarten dieses Monats: sobald hier ein Zähler steht, zählt für dieses Gerät nur noch Gemessenes. Eine Betriebsart ohne Zähler erscheint dann unter „nicht aufgeteilt“. In Home Assistant bekommt man ihn mit einem **Utility Meter** (Helfer) auf den Energie-Sensor des Geräts, mit einem Tarif je Betriebsart. ⚠ An Multisplit-Geräten misst kein Innengerät seinen eigenen Anteil: Was dort als Verbrauch erscheint, ist der Anteil des Außengeräts, der dem gerade anfordernden Innengerät zugeschrieben wird. | Komponenten → Wärmepumpe · Cockpit → Tag | `luft_luft` (weich) |
| `betriebsart_strom_entfeuchten_kwh` · je Innengerät zusätzlich `betriebsart_strom_entfeuchten_kwh-<id>` | Strom Entfeuchtungsbetrieb | kWh | Kumulativ oder Tagessensor | optional | Elektrische Energie, die dieses Gerät im Entfeuchtungsbetrieb verbraucht hat (kWh, kumulativer Zähler oder Tagessensor). **Teilmenge** des Gesamtverbrauchs — eedc addiert sie nie dazu. Liegt dieser Wert vor, hat er Vorrang vor der Aufteilung, die eedc sonst aus dem Betriebsmodus ableitet — und zwar für **alle** Betriebsarten dieses Monats: sobald hier ein Zähler steht, zählt für dieses Gerät nur noch Gemessenes. Eine Betriebsart ohne Zähler erscheint dann unter „nicht aufgeteilt“. In Home Assistant bekommt man ihn mit einem **Utility Meter** (Helfer) auf den Energie-Sensor des Geräts, mit einem Tarif je Betriebsart. ⚠ An Multisplit-Geräten misst kein Innengerät seinen eigenen Anteil: Was dort als Verbrauch erscheint, ist der Anteil des Außengeräts, der dem gerade anfordernden Innengerät zugeschrieben wird. | Komponenten → Wärmepumpe · Cockpit → Tag | `luft_luft` (weich) |
| `betriebsart_nutzenergie_heizen_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_heizen_kwh-<id>` | Nutzenergie Heizbetrieb | kWh | Kumulativ oder Tagessensor | optional | Abgegebene Nutzenergie im Heizbetrieb (kWh, kumulativer Zähler oder Tagessensor) — thermisch, NICHT Strom. Beim Kühlen ist das die abgeführte Wärme. Optional; ohne Wärmemengenzähler gibt es diesen Wert nicht, und eedc rechnet ihn nicht herbei. | Komponenten → Wärmepumpe | `luft_luft` (weich) |
| `betriebsart_nutzenergie_kuehlen_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_kuehlen_kwh-<id>` | Nutzenergie Kühlbetrieb | kWh | Kumulativ oder Tagessensor | optional | Abgegebene Nutzenergie im Kühlbetrieb (kWh, kumulativer Zähler oder Tagessensor) — thermisch, NICHT Strom. Beim Kühlen ist das die abgeführte Wärme. Optional; ohne Wärmemengenzähler gibt es diesen Wert nicht, und eedc rechnet ihn nicht herbei. | Komponenten → Wärmepumpe · Cockpit → Monat | `kuehlt` (weich) |
| `betriebsart_nutzenergie_lueften_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_lueften_kwh-<id>` | Nutzenergie Lüftbetrieb | kWh | Kumulativ oder Tagessensor | optional | Abgegebene Nutzenergie im Lüftbetrieb (kWh, kumulativer Zähler oder Tagessensor) — thermisch, NICHT Strom. Beim Kühlen ist das die abgeführte Wärme. Optional; ohne Wärmemengenzähler gibt es diesen Wert nicht, und eedc rechnet ihn nicht herbei. | Komponenten → Wärmepumpe · Cockpit → Monat | `luft_luft` (weich) |
| `betriebsart_nutzenergie_entfeuchten_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_entfeuchten_kwh-<id>` | Nutzenergie Entfeuchtungsbetrieb | kWh | Kumulativ oder Tagessensor | optional | Abgegebene Nutzenergie im Entfeuchtungsbetrieb (kWh, kumulativer Zähler oder Tagessensor) — thermisch, NICHT Strom. Beim Kühlen ist das die abgeführte Wärme. Optional; ohne Wärmemengenzähler gibt es diesen Wert nicht, und eedc rechnet ihn nicht herbei. | Komponenten → Wärmepumpe · Cockpit → Monat | `luft_luft` (weich) |

Soll- und Raumtemperatur je Innengerät (`soll_temperatur_c`, `ist_temperatur_c`) stehen in der Live-Tabelle von §4.

**Kompressor-Starts und Betriebsstunden** sind keine Felder der Feld-Registry: Sie stehen in `KUMULATIVE_COUNTER_FELDER` (`backend/services/snapshot/keys.py`) — Zählwerke ohne Energie-Einheit, die der stündliche Snapshot wie einen Zählerstand erfasst und die nie in die Energie-Bilanz gehen (§9); ihre Beschriftung kommt aus `core/field_definitions/karten.py`.

| Feld | Label | Einheit | Sensortyp | Beschreibung | Ausgewertet in |
|------|-------|---------|-----------|-------------|-----------------|
| `wp_starts_anzahl` | Kompressor-Starts | Anzahl | Counter (Total-Increasing) | **Optional, ab v3.24.0 (#136).** Kumulativer Anzahl-Zähler für Kompressor-Starts der Wärmepumpe. Z. B. aus der lokalen „Nibe Heat Pump"-Integration: `sensor.compressor_number_of_starts_…`. Stündlicher Snapshot-Job erfasst den Counter wie kWh-Zähler; Tagesabschluss berechnet Stunden- und Tages-Differenzen. **Bewusst kein Fallback** aus `leistung_w` oder Compressor-Binary — würde gerade kurze Takte (wo der KPI sticht) systematisch unterzählen. Anzeige: [Cockpit → Tag](HANDBUCH_BEDIENUNG.md#22-tag) (Spalte „WP-Starts", default ausgeblendet) und Wärmepumpe-Komponentensicht ([Bedienung §3.4](HANDBUCH_BEDIENUNG.md#34-wärmepumpe)). | Komponenten → Wärmepumpe · Jahresbericht (PDF) |
| `wp_betriebsstunden` | Betriebsstunden | h | Counter (Total-Increasing) | **Optional, ab v3.34 (#238).** Kumulativer Zähler der Gesamt-Betriebsstunden der WP. Kombiniert mit `wp_starts_anzahl` ergibt sich „Ø Laufzeit pro Start" als Auslegungs-/Verschleiß-Maß. Wird wie ein Counter behandelt — keine Energie-Einheit, keine Aufnahme in die Energie-Bilanz (siehe §9). | Komponenten → Wärmepumpe |

> **`betriebsart_nutzenergie_kuehlen_kwh` ist die Kältemenge — und der einzige
> Zähler, der die *Arbeitszahl Kühlen* möglich macht** (Kältemenge ÷ Kühlstrom).
> Ohne ihn steht dort der Grund statt einer Zahl; geschätzt wird nichts, weil aus
> einem angenommenen Wirkungsgrad genau der Faktor zurückkäme, mit dem gerechnet
> wurde. **Sie heißt bewusst nicht „SEER"** — das ist eine genormte
> Prüfstandsgröße, dies hier ist der Quotient deiner beiden Zähler. Ausführlich:
> [Wärme & Klima §3](HANDBUCH_WAERME_KLIMA.md#3-was-eedc-bewusst-nicht-sagt).

**Mehrere Innengeräte (Multisplit):** Trag sie beim Gerät unter *Innengeräte*
ein (Bezeichnung, z. B. „Büro"). Danach gibt es **jedes** der Felder oben
zusätzlich je Innengerät — der Feld-Key trägt dessen Nummer
(`betriebsart_strom_kuehlen_kwh-3`), das Label den Raumnamen
(„Büro: Strom Kühlbetrieb").

**Vorrang:** Liegt ein Betriebsart-Zähler vor, gilt er — und zwar für **alle**
Betriebsarten dieses Geräts. Die Aufteilung, die eedc sonst aus dem
`betriebsmodus` ableitet, tritt dann zurück; eine Betriebsart ohne Zähler
erscheint unter „nicht aufgeteilt". Steht ein Wert **am Gerät**, schlägt er die
Summe der Innengeräte — beide beschreiben dieselbe Menge, sie werden nie addiert.

> ⚠️ **Was ein Innengerät NICHT misst.** An einem Multisplit hängt **ein**
> Außengerät an mehreren Innengeräten. Was eine Hersteller-App dort als
> Verbrauch eines Innengeräts anzeigt, ist der Anteil des **Außengeräts**,
> zugeschrieben an das gerade **anfordernde** Innengerät — und welches das ist,
> entscheidet die Einschaltreihenfolge. Mitsubishi sagt es selbst:
> *„It is not possible to attribute the output of the outdoor units to specific
> indoor units."* Die belastbare Menge ist ein eigener Zähler am Außengerät.

#### So bekommst du die vier Zähler in Home Assistant

**Weg 1 — Utility Meter (empfohlen, für die kWh-Felder).** Er *zählt* und
übersteht Neustarts; ein Template-Sensor kann das nicht.

1. *Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → **Utility
   Meter***.
2. **Eingangssensor**: der Energie-Sensor deiner Klimaanlage (kWh).
3. **Tarife**: `heizen`, `kuehlen`, `lueften`, `entfeuchten`.
   HA legt daraus je Tarif einen eigenen zählenden Sensor an.
4. Eine Automatisierung schaltet den aktiven Tarif, ausgelöst vom Zustand der
   `climate`-Entität — Aktion **`select.select_option`** auf die
   `select.…`-Entität, die der Utility Meter mit angelegt hat.
5. In eedc unter *Einstellungen → Datenquellen* die vier Tarif-Sensoren den
   vier Feldern zuordnen.

**Weg 2 — Template-Sensor**, für Momentanwerte und Umrechnungen: Leistung je
Betriebsart (`{{ leistung if modus == 'cool' else 0 }}`), Einheiten- und
Vorzeichenkorrekturen, oder das Zusammenfassen mehrerer Entitäten zu einer.

---

## 5. E-Auto

> **Die Wallbox ist die Summe, ein Auto mit eigener Messung trägt seine eigene Heimladung (seit v4.0.51).** Die Heim-Felder `ladung_pv_kwh` („Heim: PV“), `ladung_netz_kwh` („Heim: Netz“) und `ladung_kwh` („Heim: gesamt“) werden **jedem** E-Auto angeboten, auch neben einer Wallbox. Trägt ein Auto dort einen Wert (auch 0) oder — im laufenden Monat — eine zugeordnete Quelle, zählt dieser Wert für dieses Auto; die Wallbox trägt den Rest, und der Rest geht nach Kilometern an die privaten Autos ohne eigene Messung ([Berechnungen, Heimladung je Auto](BERECHNUNGEN.md)). Nur an einem **Dienstwagen neben einer dienstlichen Wallbox** fehlen die Felder: dort ist die dienstliche Wallbox die dienstliche Ladung. Km-, Verbrauchs-, Extern- und V2H-Felder bleiben in jedem Fall am E-Auto. Ist die Summe der Autos größer als die Wallbox, meldet der Daten-Checker es.

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `km_gefahren` | Gefahrene km | km | Zählerstand (kumulativ) | pflicht | Gefahrene Kilometer im Monat — kumulativer km-Zähler (Auto-Integration/OBD) oder Tagessensor, sonst manuell. | Komponenten → E-Auto · Cockpit → Monat · HA-Sensoren | — |
| `km_stand` | Tachostand | km | kein Sensor — manuell/Import | optional | Kilometerstand am Monatsende, wie er im Auto steht. eedc rechnet daraus die gefahrenen Kilometer (Stand dieses Monats minus Stand des Vormonats) und schlägt sie oben vor. Nur für die Handeingabe — ein Kilometerstand-Sensor gehört auf „Gefahrene km“, dort bildet eedc die Differenz selbst. | — Der Tachostand (#407, 8ear) ist `nur_manuell` und steht deshalb nicht auf der Datenquellen-Fläche. Ausgewertet wird die **Differenz** als Vorschlag für `km_gefahren` (`services/vorschlag_service.py`) — und ein Vorschlag ist nach R-A keine Auswertung. Die gefahrenen Kilometer haben ihre Sichten; der Stand selbst erscheint nur in der CSV-Spalte `Tachostand`. | — |
| `verbrauch_kwh` | Verbrauch | kWh | Kumulativ oder Tagessensor | optional | Kumulativer kWh-Zähler des gefahrenen Energieverbrauchs (zählt fortlaufend hoch, Tagessensor geht auch) — der reine Fahrverbrauch, NICHT pro Fahrt und NICHT kWh/100 km. eedc errechnet daraus mit den km die Effizienz. Optional: fehlt der Wert, nähert eedc die kWh/100 km aus der geladenen Energie an (inkl. Ladeverluste). | Komponenten → E-Auto · Cockpit → Monat | — |
| `ladung_pv_kwh` | Heim: PV | kWh | Kumulativ oder Tagessensor | optional | Zu Hause aus PV in dieses Auto geladene Energie (kWh, kumulativ oder Tagessensor). Neben einer Wallbox: Zählt für dieses Auto. Die Wallbox trägt den Rest. Ohne Wert leitet eedc den PV-Anteil ab. | Komponenten → E-Auto · Cockpit → Monat · Cockpit → Jahr | Anlage: `keine_dienstliche_wallbox` |
| `ladung_netz_kwh` | Heim: Netz | kWh | Kumulativ oder Tagessensor | optional | Zu Hause aus dem Netz in dieses Auto geladene Energie (kWh, kumulativ oder Tagessensor). Neben einer Wallbox: Zählt für dieses Auto. Die Wallbox trägt den Rest. | Komponenten → E-Auto · Cockpit → Monat · Auswertungen → Finanzen | Anlage: `keine_dienstliche_wallbox` |
| `ladung_kwh` | Heim: gesamt | kWh | Kumulativ oder Tagessensor | optional | Zu Hause in dieses Auto geladene Energie gesamt (kWh, kumulativ oder Tagessensor) — für einen Zähler am Auto, der PV und Netz nicht trennt. Zählt für dieses Auto. Die Wallbox trägt den Rest. Geteilt wird mit dem PV-Anteil der Wallbox. Mit „Heim: PV“/„Heim: Netz“ leer lassen. | Komponenten → E-Auto · Cockpit → Monat · Cockpit → Jahr | Anlage: `keine_dienstliche_wallbox` |
| `ladung_extern_kwh` | Extern | kWh | Kumulativ — nur Monatswert, kein Kanal | optional | Unterwegs geladene Energie (Autobahn, Arbeit) in kWh. Meist manuell im Monatsabschluss. Optional. | Komponenten → E-Auto · Cockpit → Monat | — |
| `ladung_extern_euro` | Extern Kosten | € | kein Sensor — Monatsabschluss | optional | Kosten der externen Ladung (€). Manuell. Optional. | Komponenten → E-Auto · Cockpit → Jahr | — |
| `v2h_entladung_kwh` | V2H Entladung | kWh | Kumulativ oder Tagessensor — Tagesgröße ohne Kanal | optional | Vehicle-to-Home zurück ins Haus gespeiste Energie (kWh, kumulativ oder Tagessensor). Nur bei V2H-fähigem Fahrzeug. Optional. | Cockpit → Tag · Komponenten → E-Auto · Cockpit → Jahr · HA-Sensoren | `v2h_faehig` |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `leistung_w` | Ladeleistung | W | Momentanwert | optional | Momentane Ladeleistung des Fahrzeugs in W. Lädt das Auto an einer Wallbox mit eigenem Leistungssensor, zählt eedc die Ladeleistung einmal, an der Wallbox; misst das Auto mit eigenem Sensor, steht es darunter. | Cockpit → Live | — |
| `soc` | Ladestand | % | Momentanwert | optional | Ladestand der Fahrzeugbatterie in Prozent (0–100). | Cockpit → Live | — |
| `ladezustand_fahrzeug` | Ladezustand (Fahrzeug) | — | Zustand | optional | Was das Auto selbst meldet: nicht verbunden · verbunden · lädt · lädt DC · fertig · Fehler. Erscheint als Chip an der Auto-Karte, wenn das Auto keiner Wallbox zugeordnet ist (an der Wallbox sagt es deren Chip). Verstanden werden die Kanon-Wörter und die Werte der Smart-Integration (`sensor.smart_ladesanschluss` oder `sensor.smart_ladezustand`). Andere Integrationen über einen Template-Sensor in Home Assistant, der genau diese Wörter liefert (Werte-Tabelle am Feld und im Handbuch). Wird ab der Zuordnung stündlich mitgeschrieben (Karte «Betrieb heute», nicht rückwirkend). | Komponenten → E-Auto | — |
| `reichweite_km` | Reichweite | km | Momentanwert — nur Anzeige | optional | Restreichweite in km. Reine Anzeige. ⚠ evcc meldet sie nur, solange das Auto am Ladepunkt hängt (danach 0 — dann lieber den Sensor der Fahrzeug-Integration). | Komponenten → E-Auto | — |
| `ziel_ladestand_prozent` | Ladeziel | % | Momentanwert — nur Anzeige | optional | Ladeziel des Fahrzeugs in % — die Zielmarke an der Ladestand-Leiste. Reine Anzeige. | Komponenten → E-Auto | — |
| `restzeit_min` | Restzeit | min | Momentanwert — nur Anzeige | optional | Verbleibende Ladezeit laut Fahrzeug in Minuten. Reine Anzeige. | Komponenten → E-Auto | — |
| `zu_hause` | Zu Hause | — | Zustand | optional | Ist das Auto zu Hause? Der `device_tracker` des Fahrzeugs (Zone `home`/`not_home`) — nur die Zone, nie eine Position. Andere Zonennamen versteht eedc nicht (Template-Sensor: zu_hause · unterwegs). Wird ab der Zuordnung stündlich mitgeschrieben (Karte «Betrieb heute», nicht rückwirkend). | Komponenten → E-Auto | — |

> Die fünf Zustands- und Sitzungsfelder (und die neun an der Wallbox, darunter das Textfeld „Fahrzeug am Ladepunkt") sind
> **reine Anzeige**: eedc liest sie live, speichert sie nicht und rechnet nicht mit ihnen (kein Kanal, keine Monatsmenge).
> Keine Einheiten-Umrechnung. Das Gegenstück zum Textfeld der Wallbox ist kein Sensor, sondern das Stammdatum
> **„Kennung in der Steuerung"** am E-Auto (Einstellungen → Investitionen).

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

## 6. Wallbox

> **Die Wallbox ist die Summe aller Ladungen an ihr** — privates Auto, Gast, Dienstwagen. So zählt sie in der Energiebilanz, am Tag, in der Stunde und in ihrer eigenen Anzeige. Mehrere Wallboxen werden summiert (jeder Ladepunkt zählt). Trägt ein Auto eine eigene Heim-Messung (siehe E-Auto), zählt sie für dieses Auto; der **Rest** der Wallbox geht nach Kilometern an die privaten Autos ohne eigene Messung, ohne solche bleibt er nicht zugeordnet (Gast, Verluste: nur Verbrauch, keine Ersparnis) — außer es ist gar kein Fahrzeug angelegt: dann ist die Wallbox selbst das private Auto. Ohne Messung am Auto ist das die bisherige km-anteilige Aufteilung. Ordne den Loadpoint-/Wallbox-Energiesensor hier zu.

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `ladung_kwh` | Ladung gesamt | kWh | Kumulativ oder Tagessensor | pflicht | Gesamte von der Wallbox abgegebene Ladeenergie (kWh, kumulativer Zähler oder Tagessensor). Die Quelle der Heimladung — den Zähler hier zuordnen, nicht am E-Auto. | Komponenten → Wallbox · Cockpit → Monat | — |
| `ladung_pv_kwh` | Ladung PV | kWh | Kumulativ oder Tagessensor | optional | PV-Anteil der Wallbox-Ladung (kWh, kumulativ oder Tagessensor). Optional — manche Wallboxen messen das separat. | Komponenten → Wallbox · Cockpit → Monat | — |
| `ladevorgaenge` | Ladevorgänge | — | Zählerstand (kumulativ) | optional | Anzahl der Ladevorgänge (kumulativer Zähler oder Tagessensor). Optional. | Komponenten → Wallbox | — |
| `netzbezug_eigener_tarif_kwh` | Netzbezug zum Wallbox-Tarif | kWh | Kumulativ oder Tagessensor | optional | Die Menge, die dein Versorger zum Wallbox-Tarif abrechnet (kWh, kumulativer Zähler). Optional — nur mit eigenem Wallbox-Tarif wirksam. Zählerkaskade: Bezug des Zählers am Netzanschluss minus Bezug des Haus-Zählers, als Template-Sensor mit state_class „total“. eedc rechnet damit die Stromrechnung mit beiden Tarifen. | Cockpit → Monat · Cockpit → Jahr | — |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | Momentanwert | optional | Momentane Ladeleistung der Wallbox in W. | Cockpit → Live | — |
| `ladezustand` | Ladezustand | — | Zustand | optional | Was am Ladepunkt gerade geschieht: kein Fahrzeug · verbunden · wartet · lädt · fertig · gesperrt · Fehler — ein Zustand, kein Messwert. Erscheint als Chip an der Wallbox im Überblick und an der Kachel im Energiefluss. Verstanden werden die Kanon-Wörter und die Werte des SMA EV Charger; über MQTT auch die go-eCharger-Codes 0–5. Andere Integrationen über einen Template-Sensor in Home Assistant, der genau diese Wörter liefert (Werte-Tabelle am Feld und im Handbuch). Wird ab der Zuordnung stündlich mitgeschrieben (Karte «Betrieb heute», nicht rückwirkend). | Komponenten → Wallbox · Cockpit → Live | — |
| `lademodus` | Lademodus | — | Zustand — nur Anzeige | optional | Lademodus der Steuerung: aus · PV · Smart · Schnell · Plan · Eco — steht im Chip hinter «Lädt» und «Wartet». Verstanden werden die Kanon-Wörter, evcc (`select.evcc_…_mode`) und der SMA EV Charger; über MQTT auch die go-eCharger-Codes. Eine Angabe der Steuerung, eedc bewertet sie nicht. Andere Integrationen über einen Template-Sensor in Home Assistant, der genau diese Wörter liefert (Werte-Tabelle am Feld und im Handbuch). | Komponenten → Wallbox · Cockpit → Live | — |
| `fahrzeug_am_ladepunkt` | Fahrzeug am Ladepunkt | — | Text — nur Anzeige | optional | Name des Fahrzeugs, das die Steuerung am Ladepunkt erkennt (evcc `select.evcc_…_vehicle_name`, openWB «Angeschlossenes Fahrzeug») — ein Text, kein Messwert. Stimmt er mit der «Kennung in der Steuerung» eines E-Autos überein, nennt die Wallbox-Karte genau dieses Auto, auch bei mehreren Wallboxen. Leer heißt Gast, fehlend heißt nichts: meldet die Steuerung kein Fahrzeug (evcc `null`), während ein Auto verbunden ist oder lädt, zeigt die Karte «Gastfahrzeug». Ein leerer `input_text` in Home Assistant ist von «nicht verfügbar» nicht zu unterscheiden und gilt nicht als Gast. | Komponenten → Wallbox · Cockpit → Live | — |
| `evcc_verbunden` | evcc: Fahrzeug verbunden | — | Zustand — nur Anzeige | optional | Ob ein Fahrzeug am Ladepunkt angesteckt ist (evcc `binary_sensor.evcc_…_connected`, MQTT `connected`). Nur nötig ohne Ladezustand-Sensor: eedc setzt aus «verbunden», «lädt» und «freigegeben» den Ladezustand-Chip zusammen (kein Fahrzeug · verbunden · wartet · lädt); ein zugeordneter Ladezustand geht immer vor. Verstanden werden on/off (Home Assistant) und true/false (evcc über MQTT); über MQTT auch 1/0. | Komponenten → Wallbox · Cockpit → Live | — |
| `evcc_laedt` | evcc: lädt | — | Zustand — nur Anzeige | optional | Ob gerade geladen wird (evcc `binary_sensor.evcc_…_charging`, MQTT `charging`). Nur nötig ohne Ladezustand-Sensor: eedc setzt aus «verbunden», «lädt» und «freigegeben» den Ladezustand-Chip zusammen (kein Fahrzeug · verbunden · wartet · lädt); ein zugeordneter Ladezustand geht immer vor. Verstanden werden on/off (Home Assistant) und true/false (evcc über MQTT); über MQTT auch 1/0. | Komponenten → Wallbox · Cockpit → Live | — |
| `evcc_freigegeben` | evcc: Laden freigegeben | — | Zustand — nur Anzeige | optional | Ob die Steuerung das Laden freigegeben hat (evcc `binary_sensor.evcc_…_enabled`, MQTT `enabled`) — verbunden, aber nicht freigegeben heißt «wartet». Nur nötig ohne Ladezustand-Sensor: eedc setzt aus «verbunden», «lädt» und «freigegeben» den Ladezustand-Chip zusammen (kein Fahrzeug · verbunden · wartet · lädt); ein zugeordneter Ladezustand geht immer vor. Verstanden werden on/off (Home Assistant) und true/false (evcc über MQTT); über MQTT auch 1/0. | Komponenten → Wallbox · Cockpit → Live | — |
| `sitzung_kwh` | Energie dieser Sitzung | kWh | Momentanwert — nur Anzeige | optional | Seit dem Anstecken geladene Energie in kWh (evcc `session_energy`, SMA `energie_ladevorgang`, go-e `wh`). Reine Anzeige im Überblick — keine Monatsmenge, kein Zähler der Bilanz. ⚠ SMA, go-e und evcc über MQTT liefern Wh: eedc rechnet die Einheit hier nicht um — einen kWh-Sensor wählen oder in Home Assistant die Anzeigeeinheit auf kWh stellen (das MQTT-Preset «evcc Ladepunkt» rechnet `sessionEnergy` mit Faktor 0,001 um). | Komponenten → Wallbox | — |
| `sitzung_dauer_s` | Dauer dieser Sitzung | s | Momentanwert — nur Anzeige | optional | Ladedauer der laufenden Sitzung in Sekunden (evcc `charge_duration`, MQTT `chargeDuration`). Reine Anzeige. | Komponenten → Wallbox | — |
| `ladestrom_a` | Ladestrom | A | Momentanwert — nur Anzeige | optional | Ladestrom in A (evcc `charge_current`, go-e `amp`). Reine Anzeige. | Komponenten → Wallbox | — |
| `phasen_aktiv` | Aktive Phasen | — | Momentanwert — nur Anzeige | optional | Anzahl der Phasen, über die gerade geladen wird (evcc `phases_active`, go-e `pnp`). Reine Anzeige. | Komponenten → Wallbox | — |
| `ziel_ladestand_prozent` | Ladeziel | % | Momentanwert — nur Anzeige | optional | Ladeziel der Steuerung in % (evcc `effective_limit_soc`) — die Zielmarke an der Ladestand-Leiste. Reine Anzeige. | Komponenten → Wallbox | — |
| `restzeit_min` | Restzeit | min | Momentanwert — nur Anzeige | optional | Verbleibende Ladezeit in Minuten. Reine Anzeige. ⚠ evcc liefert Sekunden (`charge_remaining_duration`): eedc rechnet nicht um — Sensor in Minuten wählen (das MQTT-Preset «evcc Ladepunkt» rechnet `chargeRemainingDuration` mit Faktor 1/60 um). | Komponenten → Wallbox | — |

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

## 7. Sonstiges (Erzeuger / Verbraucher / Abgabe an Dritte / Speicher / Verbrauchszähler)

### Monatserfassung

| Art | Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|---|
| `erzeuger` | `erzeugung_kwh` | Erzeugung | kWh | Kumulativ oder Tagessensor | optional | Erzeugte Energie (z. B. BHKW, Windrad) in kWh, kumulativer Zähler oder Tagessensor. Zählt wie PV-Strom hinter dem Hauszähler in Eigenverbrauch und Autarkie. | Komponenten → Sonstiges · Cockpit → Monat | — |
| `erzeuger` | `eigenverbrauch_kwh` | Eigenverbrauch | kWh | Kumulativ — nur Monatswert, kein Kanal | optional | Direkt selbst verbrauchter Anteil der Erzeugung (kWh, kumulativ oder Tagessensor). Optional. | Komponenten → Sonstiges · Cockpit → Monat | — |
| `erzeuger` | `einspeisung_kwh` | Einspeisung | kWh | Kumulativ — nur Monatswert, kein Kanal | optional | Ins Netz eingespeister Anteil der Erzeugung (kWh, kumulativ oder Tagessensor). Optional. | Komponenten → Sonstiges · Cockpit → Monat | — |
| `erzeuger` | `einspeise_erloes_euro` | Einspeise-Erlös | € | kein Sensor — Monatsabschluss | optional | Erlös DIESES Erzeugers in € — für einen eigenen Einspeisetarif, den eedc nicht kennen kann (es gibt einen Satz je Anlage). Am besten als kumulativer Helfer-Sensor aus Home Assistant (state_class total_increasing, device_class monetary), dann wird der Wert im Monatsabschluss vorgeschlagen. Wichtig: In den Anlagen-Einspeisezähler gehört nur die Menge, die zum Anlagentarif abgerechnet wird — dieser Betrag kommt zusätzlich dazu. | Auswertungen → Finanzen · Komponenten → Sonstiges | — |
| `verbraucher` | `verbrauch_sonstig_kwh` | Verbrauch | kWh | Kumulativ oder Tagessensor | optional | Verbrauchte Energie (z. B. Sauna, Pool) in kWh, kumulativer Zähler oder Tagessensor. | Cockpit → Monat · Komponenten → Sonstiges | — |
| `verbraucher` | `bezug_pv_kwh` | davon PV | kWh | Kumulativ — nur Monatswert, kein Kanal | optional | PV-gedeckter Anteil des Verbrauchs (kWh, kumulativ oder Tagessensor). Optional. | Cockpit → Monat · Komponenten → Sonstiges | — |
| `verbraucher` | `bezug_netz_kwh` | davon Netz | kWh | Kumulativ — nur Monatswert, kein Kanal | optional | Netz-gedeckter Anteil des Verbrauchs (kWh, kumulativ oder Tagessensor). Optional. | Cockpit → Monat · Komponenten → Sonstiges | — |
| `abgabe` | `abgabe_kwh` | Abgabe | kWh | Kumulativ oder Tagessensor | optional | An Dritte abgegebene Energie (Mieterstrom, Allgemeinstrom, Nachbarhaus) in kWh — Zähler an der Übergabestelle, kumulativ oder Tagessensor. eedc zieht sie vom Eigenverbrauch ab; sie ist weder Eigenverbrauch noch Netz-Einspeisung. | Cockpit → Monat · Cockpit → Jahr | — |
| `abgabe` | `einspeise_erloes_euro` | Erlös | € | kein Sensor — Monatsabschluss | optional | Erlös aus der Abgabe in € (eigener Satz, den eedc nicht kennen kann). Am besten als kumulativer Helfer-Sensor aus Home Assistant; die Abrechnung an die Abnehmer ist nicht Sache von eedc. | Auswertungen → Finanzen · Komponenten → Sonstiges | — |
| `speicher` | `erzeugung_kwh` | Erzeugung/Entladung | kWh | Kumulativ oder Tagessensor | optional | Aus dem Speicher entladene Energie (kWh, kumulativer Zähler oder Tagessensor). | Komponenten → Sonstiges · Cockpit → Monat | — |
| `speicher` | `verbrauch_sonstig_kwh` | Verbrauch/Ladung | kWh | Kumulativ oder Tagessensor | optional | In den Speicher geladene Energie (kWh, kumulativer Zähler oder Tagessensor). | Cockpit → Monat · Komponenten → Sonstiges | — |
| `zaehler` | `zaehlerstand` | Zählerstand | vom Gerät (`zaehler_einheit`) | Zählerstand (kumulativ) | optional | Der abgelesene Zählerstand — die Zahl, die auf dem Zähler steht (Gas, Wasser, Heizöl …). eedc rechnet daraus nur die Differenz zwischen Anfang und Ende des angezeigten Zeitraums; in Energiebilanz, Autarkie, Wirtschaftlichkeit und CO₂ geht der Wert bewusst nicht ein. Aus einem Sensor (stündlich) oder im Monatsabschluss von Hand. | Cockpit → Zählerstände | — |

> ⚠ **Der Zählerstand ist bewusst einheitenlos gespeichert.** Was neben der Zahl
> steht (m³, l, kg, t, kWh), gehört zum **Gerät** (`zaehler_einheit`) und wird
> nur zur Anzeige geholt — eedc rechnet Zählerstände nie um. Genau diese leere
> Einheit ist die Sicherung dagegen, dass ein Gasverbrauch in der Strombilanz
> landet.
>
> **Sensor-Anforderung:** ein monoton steigender Zählerstand
> (`state_class: total_increasing`). Ein Sensor, der den *Verbrauch je Tag*
> liefert und nachts zurückspringt, passt hier **nicht** — eedc bildet die
> Menge aus der Differenz zweier Stände.
>
> **Zählerwechsel:** altes Gerät stilllegen (Stilllegungsdatum setzen, `aktiv`
> **an** lassen) und ein neues anlegen. Details:
> [Handbuch Einstellungen §3.4a](HANDBUCH_EINSTELLUNGEN.md).

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Bedarf | Hinweis | Sichten | Bedingung |
|---|---|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | Momentanwert | optional | Momentane Leistung in W — bei einem Erzeuger positiv als Erzeugung, bei einem Verbraucher als Verbrauch gewertet. | Cockpit → Live | — |

> Ein **Verbrauchszähler** hat kein Live-Feld: Er führt keine Leistung, und eine
> m³-Reihe auf der kW-Achse des Energieflusses wäre eine Einheiten-Verwechslung.
> Sein aktueller Stand steht stattdessen in *Live → Auf einen Blick* unter
> **Zählerstände**.

---

## 8. Solcast PV Forecast (optional, ab v3.16.5)

Solcast als dritte Prognose-Quelle wird über die Datenquellen/Anlagenstammdaten angebunden — zwei alternative Pfade. Wie eedc die Solcast-Werte im Vergleich nutzt, steht im [Handbuch Prognosen §2.3](HANDBUCH_PROGNOSEN.md#23-solcast--optional-dritte-meinung).

### Variante A: HA-Integration (BJReplay)

Setzt die [BJReplay Solcast HA-Integration](https://github.com/BJReplay/ha-solcast-solar) voraus. eedc liest die 7-Tage-Prognose direkt als Sensor-State — kein API-Key in eedc nötig.

**Auto-Discovery (v3.16.10):** Sensoren werden über `/api/states` per Suffix-Pattern gematcht:

| Suffix-Pattern | Bedeutung |
|---|---|
| `_heute` / `_today` | Tagesprognose Heute |
| `_morgen` / `_tomorrow` | Tagesprognose Morgen |
| `_uebermorgen` / `_ubermorgen` / `_tag_3` / `_day_3` | Übermorgen |
| `_tag_4` … `_tag_7` / `_day_4` … `_day_7` | Tag 4–7 |

Filter (v3.16.11): nur Sensoren mit `unit_of_measurement=kWh` und ohne „verbleibend"/„remaining" im Namen — sonst würde z. B. `prognose_verbleibende_leistung_heute` fälschlich als Tagesprognose gematcht.

**Stundenprofil:** Kommt aus dem `DetailedForecast`-Attribut der HA-Sensoren (v3.16.13 — vorher fälschlich `detailedHourly` gesucht, was bei Multi-Dach-Anlagen leer war).

### Variante B: Solcast-API (Free/Paid Key)

Direkter API-Aufruf für Standalone-Nutzer ohne HA-Integration. Konfiguration in den Anlagenstammdaten ([Einstellungen → Stammdaten → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)). L1-Cache (in-memory) und L2-Cache (DB) überleben Neustarts.

### Slot-Konvention

30-Min-Buckets aus Solcast werden per `ceil(bucket_ende)` dem **Backward-Slot** zugeordnet (siehe [BERECHNUNGEN §6b](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation)). Ein Bucket am Tagesübergang `[23:00, 23:30)` heute landet damit korrekt in Slot 0 des Folgetags.

---

## 8a. eedc-PV-Prognose nach HA exportieren (MQTT / HA-Sensoren)

eedc **exportiert** zusätzlich die eigene PV-Prognose als Sensoren (immer die **eedc**-Quelle, nie Solcast/SFML — die liegen via eigene HA-Integration bereits in HA). Alle Werte stammen aus dem **Prognose-Kanon** und sind damit identisch mit der „eedc"-Spalte im Vergleich.

> ⚠ **Hast du Solcast oder SFML als Prognosequelle gewählt, zeigt *Cockpit → Live* andere Zahlen als diese Sensoren — und das ist Absicht.** Der Block auf dem Bildschirm folgt durchgehend **deiner gewählten Quelle**, damit „bisher erzeugt + verbleibend = heute" wieder aufgeht. Diese Sensoren tragen dagegen weiterhin die **eedc-eigene** Prognose, denn die Solcast-/SFML-Werte liegen über deren eigene HA-Integration ohnehin schon in Home Assistant — ein zweiter Export derselben Zahl wäre nur eine zweite Stelle, an der sie driften kann. Mit der Standard-Quelle (eedc) zeigen beide dieselbe Zahl.

Einrichtung: [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export).

Die Sensoren stehen mit Einheit, Formel und Hinweisen in der erzeugten Tabelle [§11 PV-Prognose-Sensoren](#pv-prognose-sensoren-eedc_prognose_).

> ⚠ **Welchen der drei nehme ich?** `…_heute_kwh` beantwortet *was sagt die Vorhersage für
> diesen Tag* — er ist die Zahl, die App, MQTT und Persistenz gemeinsam tragen, und er ändert
> sich nur, wenn OpenMeteo einen neuen Modelllauf liefert. `…_heute_rollend_kwh` beantwortet
> *worauf läuft der Tag tatsächlich hinaus* — er zieht die schon gemessenen Stunden heran und
> reagiert damit auf einen Tag, der besser oder schlechter läuft als vorhergesagt.
> `…_rest_today_kwh` ist der Rest, nachgeführt aus dem gemessenen Vormittag (Attribut
> `nachfuehr_faktor`; `rest_modell_kwh` ist der Rest ohne Nachführung). **Die Differenz
> `…_heute_kwh` − `…_heute_rollend_kwh` ist keine sinnvolle Größe:**
> `…_heute_kwh` enthält für die vergangenen Stunden die *Vorhersage*, nicht die Messung.
>
> **Warum diese Sensoren kein `device_class` tragen.** Sie liefern kWh, sind aber **keine
> Zähler**: eine Tagesprognose springt jeden Tag zurück, und die Summe zweier Prognosen ergibt
> keine sinnvolle Zahl. Home Assistant verlangt für `device_class: energy` genau einen Zähler
> (`state_class` `total`/`total_increasing`) und nimmt Sensoren mit einer anderen Kombination
> **von der Langzeitstatistik aus** — sie zeigen dann einen Wert, ohne dass HA ihn mitschreibt.
> Ohne `device_class` ist `state_class: measurement` zulässig, und HA führt min/mean/max je
> Stunde. Bis v4.0.27 war das falsch gesetzt (gemeldet von rapahl); die Einheit kWh stand und
> steht unverändert am Sensor.

> ⚠ **Wann diese Sensoren „unbekannt" zeigen — und warum das die richtige Antwort ist.**
> eedc holt die Prognose **je Ausrichtung getrennt** (Multi-String-Fan-out): eine Ost- und eine
> Westfläche sind zwei Abrufe, jeder mit eigenem Zwischenspeicher. Fällt einer davon aus —
> Zeitüberschreitung oder Ratenbegrenzung beim Wetterdienst —, liefern die übrigen weiter, und
> die Tagessumme wäre dann **um die fehlende Fläche zu klein**. Statt eine solche Zahl
> auszugeben, lässt eedc den Sensor für diesen Durchgang **leer** (in Home Assistant:
> „unbekannt", s. § *Ein Sensor, der seinen Wert verliert*); beim nächsten Durchgang steht der
> volle Wert wieder da. Betroffen sind `…_heute_kwh`, `…_rest_today_kwh`,
> `…_heute_rollend_kwh` und die Tage +1/+2/+3 samt Stundenprofilen — jeweils nur der Tag,
> dessen Abruf unvollständig war.
>
> **Für Automationen heisst das:** auf `unknown`/`unavailable` prüfen, statt einen Zahlenwert
> vorauszusetzen. Eine Anlage mit nur **einer** Ausrichtung kennt den Fall nicht — dort gibt es
> entweder alles oder nichts. Der gemessene Wert *„PV heute erzeugt"* bleibt in jedem Fall
> stehen: er hängt an keiner Prognose.
>
> Vor v4.0.44 stand hier die zu kleine Zahl, bis der nächste Durchgang sie ersetzte — bei der
> Voreinstellung eine volle Stunde.

> **Hinweis:** Bis v3.45.5 war `eedc_prognose_heute_kwh` „IST bisher + Rest" und wich damit von der App-Anzeige ab. Seit dem Prognose-Kanon trägt der Sensor den **vollen kanonischen Tageswert** (== Anzeige); „Rest heute" ist der reine Rest. Automationen, die auf den alten „IST+Rest"-Wert gebaut haben, sollten auf `…_rest_today_kwh` umgestellt werden, wenn sie den Rest brauchen.

---

## 9. Counter vs. kWh — strikte Trennung

eedc unterscheidet seit v3.24.0 zwei Klassen kumulativer Sensoren:

| Klasse | Beispiele | Verarbeitung |
|---|---|---|
| **kWh-Felder** | `pv_erzeugung_kwh`, `ladung_kwh`, `entladung_kwh`, `stromverbrauch_kwh`, `einspeisung_kwh`, `netzbezug_kwh` | Fließen in die Energie-Bilanz, Performance Ratio, Lernfaktor. Wh→kWh, MWh→kWh werden automatisch konvertiert. |
| **Counter-Felder** (`KUMULATIVE_COUNTER_FELDER`) | `wp_starts_anzahl`, `wp_betriebsstunden` | Reine Zähler — **keine** Energie-Einheit, **keine** Aufnahme in die Energie-Bilanz. Faktor 1.0 statt 0.001 bei unbekannter Einheit im HA-Statistics-Pfad. |

> **Warum getrennt?** Würde ein Counter-Sensor versehentlich als kWh-Feld konsumiert (z. B. weil seine Unit fehlt), würde er die Energie-Bilanz mit physikalisch sinnlosen Werten (z. B. 50 000 „kWh"-Kompressor-Starts) verfälschen. Die strikte Klassen-Trennung ist Voraussetzung für die Roh-Counter-Unterstützung der Nibe-Integration in v3.24.1.

---

## 10. LTS-Verfügbarkeit (HA Long-Term Statistics)

### Welche Sensoren landen in HA-LTS?

HA persistiert nur Sensoren mit gesetztem `state_class` in seiner `statistics_meta`-Tabelle. Sensoren ohne `state_class` haben **keine** LTS-Einträge — sie funktionieren live (`/api/states`), liefern aber **keine** historischen Stundenwerte für:

- Bulk-Import historischer Monate
- Vollbackfill der Tageszusammenfassungen
- Snapshot-basierte Stunden-kWh-Berechnung (siehe [BERECHNUNGEN §6b](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation))

### Filter in der Datenquellen-Zuordnung (HA-Sensor-Picker)

Bei der HA-Sensor-Auswahl zeigt eedc:

- `state_class` ∈ `total_increasing`/`total` → **immer** zugelassen, Unit egal.
- Sensor mit ganzzahligem State **ohne** Metadaten → zugelassen für Roh-Counter (z. B. Nibe Coils).
- **Fallback-Link** „Sensor nicht in der Auswahl? Alle Sensoren ohne Filter anzeigen" lädt on-demand alle `sensor.*`-Entities mit `filter_energy=false`.

### „ohne Statistik"-Badge

Sensoren ohne `state_class` tragen ein amber-farbiges Badge **„ohne Statistik"** im Picker-Dropdown. Tooltip: „Für kWh-Felder ungeeignet, für Counter unproblematisch." Im Backend trägt `HASensorInfo.has_statistics: bool` (= `state_class is not None`) diese Information. Zur Zuordnungszeit meldet die Datenquellen-Fläche das zusätzlich als Feld-Warnung ([Einstellungen §7.6](HANDBUCH_EINSTELLUNGEN.md#76-validierung--probleme-je-feld)).

#### Anleitung zum Nachrüsten

Trägt ein Sensor das Badge — z. B. der Nibe-Counter `sensor.compressor_number_of_starts_…` —, ist der **empfohlene Weg ein Verbrauchszähler-Helfer über die HA-Oberfläche**: **Einstellungen → Geräte & Dienste → Helfer → Verbrauchszähler**, als Eingang den betroffenen Sensor, Zurücksetzen-Zyklus **„nie"** (also **ohne Zyklus**). Der Helfer bringt die Statistik-Attribute mit, sein Name überlebt einen Gerätetausch — in eedc wird anschließend der Helfer zugeordnet. Details und Begründung: [Handbuch Daten-Checker §5.1](HANDBUCH_DATEN_CHECKER.md#51-state_class-probleme-bei-ha-sensoren-beheben).

Wer die YAML ohnehin pflegt, kann den Sensor stattdessen per `customize` klassifizieren:

```yaml
homeassistant:
  customize:
    sensor.compressor_number_of_starts_eb101_ep14_31490:
      state_class: total_increasing
```

Nach **HA-Neustart** landet der Sensor in HA-Long-Term-Statistics und steht damit für Backfill, Per-Tag-Reaggregation und Snapshot-Self-Healing zur Verfügung. Beide Wege gelten ab jetzt — ein neu angelegter Helfer beginnt seine Historie bei null.

> **Wichtig:** Die Korrektur wirkt **ab dem Zeitpunkt** der `state_class`-Aktivierung. HA legt LTS-Werte erst ab diesem Moment an — vorher existieren keine Werte zum Holen, auch keine rückwirkende Reparatur. Bestehende leere Tage bleiben leer; ab Aktivierung wird lückenfrei erfasst.

**Ohne eedc-Neustart.** Liest eedc die Statistik über die WebSocket-Verbindung (kein Zugriff auf die Recorder-Datenbank, etwa eedc als eigener Container oder Home Assistant mit MariaDB), sieht es einen Sensor, dessen Statistik erst nach dem Start von eedc beginnt, ohne Neustart, spätestens nach fünf Minuten — wie beim Lesen aus der Datenbank. eedc holt die Liste der Statistik-Sensoren dafür neu, wenn ein zugeordneter Sensor darin fehlt, höchstens einmal je fünf Minuten.

### Daten-Checker-Kategorie „Datenquellen – HA-Statistics"

Prüft pro Anlage, ob alle in der Datenquellen-Zuordnung verwendeten **kWh-Sensoren** tatsächlich in HA-LTS landen (siehe [Handbuch Daten-Checker §4.9](HANDBUCH_DATEN_CHECKER.md#49-sensor-mapping--ha-statistics)):

| Befund | Bedeutung |
|---|---|
| **OK** | Alle kWh-Sensoren in LTS verfügbar |
| **WARNING** | kWh-Feld zeigt auf LTS-losen Sensor — Monatsabschluss bleibt leer (still kritisch) |
| **WARNING** | Counter-Feld zeigt auf LTS-losen Sensor — Snapshot läuft, aber Korrektur-Werkzeuge in der Energieprofil-Pflege wirken nicht |

Live-Zuordnungen (`leistung_w`, `soc`) werden nicht geprüft — sie lesen `state` direkt und brauchen kein LTS.

---

## 11. Export-Sensoren (eedc → HA)

Die bisherigen Abschnitte beschreiben Sensoren, die eedc **aus HA liest**. Dieser Abschnitt beschreibt die umgekehrte Richtung: berechnete eedc-Werte, die als **HA-Entitäten** bereitgestellt werden — per MQTT Discovery (empfohlen) oder REST. Einrichtung: [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export).

> **Nicht alles muss kommen.** Jeder Sensor dieser Liste lässt sich in eedc **abwählen** — Häkchen weg in der Sensorliste unter [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export), einzeln oder kategorieweise. Bei einer **Neuinstallation** sind alle an; abgewählt wird bewusst, und eedc fragt vorher nach, weil die bisherigen Daten des Sensors in HA und auf dem Broker damit verloren sind. ⭐ **Kommen mit einem Update neue Sensoren dazu, starten sie bei einer bestehenden Installation abgewählt** — sie tragen in der Liste die Markierung **„Neu"**, und du hakst an, was du haben willst (ein Knopf nimmt alle auf einmal). Dabei geht nichts verloren: sie waren nie in Home Assistant. Der Grund für diese Voreinstellung: Ein Sensor, den es nicht gibt, zeichnet nichts auf — und Home Assistant kennt keine Zeitmaschine. Wer einen Wert später braucht, bekäme ihn erst ab dem Einschalten.

> **Zeithorizont:** Sofern nicht anders angegeben, beziehen sich die Werte auf die **Gesamtlaufzeit** (alle erfassten Monate, jeweils ab Anschaffungsdatum der Komponenten). Der laufende Monat fließt erst nach dem Monatsabschluss ein. Einzige Ausnahme: der **Spezifische Ertrag** ist aufs Jahr normiert (siehe unten).

> **Nachkommastellen — gleich für MQTT und REST:** Wie viele Nachkommastellen ein Export-Wert trägt, hängt an seiner **Größenart**, nicht am Export-Weg: Energie und Mengen (kWh, kWh/kWp, km, kg) **ganzzahlig**, Geld auf **2** Stellen, Prozent auf **1**, Leistung (kW) auf **2**, Stunden/Jahre auf **1**, übrige Kennwerte (COP, Zyklen, Rang) auf **2**. **Eine Ausnahme: die PV-Prognose-Sensoren tragen eine Nachkommastelle** — sie nennen eine Tagesmenge (0–60 kWh) und keinen Zählerstand, und ihre Zahlen sollen sich addieren lassen: *Rest heute* plus das bereits Erzeugte ergibt *heute (nachgeführt)*. Auf ganze Zahlen gerundet ging diese Summe sichtbar nicht mehr auf. Ein kleiner, aber echter Wert wird dabei **nie auf 0 gerundet** — er bekommt so viele Stellen wie nötig (höchstens 3), damit aus 0,35 kW keine 0 wird. Sensor-Namen, Einheiten und die Anzahl der Entitäten sind unverändert; die HA-Historie zeigt für zurückliegende Zeitpunkte weiter die alten Werte.
>
> Ab v4.0.6 galt diese Regel zunächst nur für MQTT; der REST-Weg lieferte für dieselbe Größe eine andere Zahl (kWh mit einer Nachkommastelle). **Seit v4.0.7 sagen beide Wege dasselbe.** Wer eedc-Sensoren über die `rest`-Plattform eingebunden hat, sieht dort einmalig kürzere Werte — 39.692,4 kWh wird zu 39.692 kWh. Der Vollzyklen-Sensor geht den umgekehrten Weg (380 → 380,19): er ist eine dimensionslose Kennzahl und trägt jetzt dieselben zwei Stellen wie die Speicher-Anzeige in eedc.

### Anlage-weite Sensoren

| Schlüssel | Name | Einheit | Klassen | Formel | Regel | Hinweise |
|---|---|---|---|---|---|---|
| `pv_erzeugung_gesamt_kwh` | PV Erzeugung Gesamt | kWh | `sensor` · `energy` · `total_increasing` | Σ PV-Erzeugung aller Monate | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | Σ PV-Erzeugung aller erfassten Monate |
| `direktverbrauch_gesamt_kwh` | Direktverbrauch Gesamt | kWh | `sensor` · `energy` · `total_increasing` | Σ Direktverbrauch (PV direkt verbraucht ohne Speicher) | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | PV direkt verbraucht (ohne Speicherumweg) |
| `eigenverbrauch_gesamt_kwh` | Eigenverbrauch Gesamt | kWh | `sensor` · `energy` · `total_increasing` | Σ Eigenverbrauch aller Monate | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | Direktverbrauch + Speicher-Entladung + V2H |
| `einspeisung_gesamt_kwh` | Einspeisung Gesamt | kWh | `sensor` · `energy` · `total_increasing` | Σ Einspeisung aller Monate | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Zählerwerte |
| `netzbezug_gesamt_kwh` | Netzbezug Gesamt | kWh | `sensor` · `energy` · `total_increasing` | Σ Netzbezug aller Monate | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Zählerwerte |
| `gesamtverbrauch_kwh` | Gesamtverbrauch | kWh | `sensor` · `energy` · `total_increasing` | Eigenverbrauch + Netzbezug | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | — |
| `autarkie_prozent` | Autarkie | % | `sensor` · `measurement` | Eigenverbrauch ÷ Gesamtverbrauch × 100 | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | Quoten über die Gesamtlaufzeit — cockpit-gleich, inkl. Erzeuger hinter dem Zähler (siehe Wertsemantik unten) |
| `eigenverbrauch_quote_prozent` | Eigenverbrauchsquote | % | `sensor` · `measurement` | Eigenverbrauch ÷ PV-Erzeugung × 100 | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | Quoten über die Gesamtlaufzeit — cockpit-gleich, inkl. Erzeuger hinter dem Zähler (siehe Wertsemantik unten) |
| `spezifischer_ertrag_kwh_kwp` | Spezifischer Ertrag | kWh/kWp | `sensor` · `measurement` | PV-Erzeugung ÷ Anlagenleistung, aufs Jahr normiert (saisonal gewichtet, wie Cockpit) | [BERECHNUNGEN: Dieselbe Abtretung gilt für die Wirtschaftlichkeit (ab v4.0.19, F-33/#381)](BERECHNUNGEN.md#dieselbe-abtretung-gilt-für-die-wirtschaftlichkeit-ab-v4019-f-33381) | **Aufs Jahr normiert** — siehe Hinweis unten |
| `netto_ertrag_euro` | Netto-Ertrag | € | `sensor` · `monetary` · `total` | Einspeiseerlös + EV-Ersparnis | [BERECHNUNGEN: Die Ergebnis-Leiter — Monat, Jahr und Gesamt aus einer Rechnung (seit 03.10.2026)](BERECHNUNGEN.md#die-ergebnis-leiter--monat-jahr-und-gesamt-aus-einer-rechnung-seit-03102026) | **Einspeiseerlös + EV-Ersparnis + BKW-Ersparnis + Sonstige (Erträge − Ausgaben)** — siehe Wertsemantik unten |
| `einspeise_erloes_euro` | Einspeiseerlös | € | `sensor` · `monetary` · `total` | Einspeisung × Einspeisevergütung | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | Finanz-Bausteine (deckungsgleich mit Cockpit/Berichten) |
| `eigenverbrauch_ersparnis_euro` | Eigenverbrauch-Ersparnis | € | `sensor` · `monetary` · `total` | Eigenverbrauch × Netzbezugspreis | [BERECHNUNGEN: Formeln](BERECHNUNGEN.md#formeln) | Finanz-Bausteine (deckungsgleich mit Cockpit/Berichten) |
| `co2_ersparnis_kg` | CO2 Einsparung | kg | `sensor` · `total_increasing` | PV-Eigenverbrauch + Wärmepumpe + E-Mobilität (vermiedenes CO₂) | [BERECHNUNGEN: Monatliche CO2-Berechnung](BERECHNUNGEN.md#monatliche-co2-berechnung) | **Volle CO₂-Bilanz** (PV-Eigenverbrauch inkl. BKW/sonstige Erzeuger + Wärmepumpe + E-Mobilität) — siehe Wertsemantik unten |
| `eedc_grundlast_kw` | Grundlast | kW | `sensor` · `power` · `measurement` | Median der GEMESSENEN Nacht-Stunden-Leistung (0–5 Uhr) des laufenden Monats aus dem stündlichen Energieprofil — dieselbe Formel und dieselbe Quelle wie die Kachel in Cockpit → Monat. Ohne gemessene Nachtstunden gibt es den Sensor nicht. | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | **Gemessener** Nacht-Sockel des laufenden Monats (Median der Stunden 0–5 Uhr aus dem Energieprofil) — dieselbe Zahl wie die Kachel in *Cockpit → Monat*. ⚠ **Nicht zu verwechseln mit „Grundlast (Prognose)"** in *Cockpit → Live*: die stammt aus dem Verbrauchsprofil und ist ohne eigene Historie ein Standard-Lastprofil. Ohne gemessene Nachtstunden entsteht **kein** Sensor. |
| `investition_gesamt_euro` | Investition Gesamt | € | `sensor` · `monetary` · `total` | Σ Anschaffungskosten aller Investitionen | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Investitions-KPIs — Nenner ist der **Kapitaleinsatz** (siehe Hinweis unten) · **Je Gerät:** Anschaffungskosten des Geräts — mit Attributen `anschaffungsdatum` · `stilllegungsdatum` · `aktiv` · `betriebsjahre` (seit eedc@ha Teil 1). ⚠ Je Gerät exportiert eedc **alle** Investitionen der Anlage, auch stillgelegte; die anlagenweite Summe zählt nur die heute aktiven — das Attribut `aktiv` sagt, welche Geräte darin stecken |
| `jahres_ersparnis_euro` | Jahresersparnis | €/Jahr | `sensor` · `measurement` | Σ Jährliche Einsparungen | [BERECHNUNGEN: 3.6 ROI & Amortisation](BERECHNUNGEN.md#36-roi--amortisation) | Investitions-KPIs — Nenner ist der **Kapitaleinsatz** (siehe Hinweis unten) |
| `roi_prozent` | ROI | % | `sensor` · `measurement` | Jahresersparnis ÷ Investition × 100 | [BERECHNUNGEN: 3.6 ROI & Amortisation](BERECHNUNGEN.md#36-roi--amortisation) | Investitions-KPIs — Nenner ist der **Kapitaleinsatz** (siehe Hinweis unten) |
| `amortisation_jahre` | Amortisation | Jahre | `sensor` · `measurement` | Investition ÷ Jahresersparnis | [BERECHNUNGEN: 3.6 ROI & Amortisation](BERECHNUNGEN.md#36-roi--amortisation) | Investitions-KPIs — Nenner ist der **Kapitaleinsatz** (siehe Hinweis unten) |
| `e_auto_km_gesamt` | Gefahrene km | km | `sensor` · `total_increasing` | Σ Gefahrene Kilometer | [BERECHNUNGEN: Kilometer, V2H und Ladevorgänge des Monats](BERECHNUNGEN.md#kilometer-v2h-und-ladevorgänge-des-monats) | — |
| `e_auto_verbrauch_kwh_100km` | Verbrauch | kWh/100km | `sensor` · `measurement` | Σ Monatswerte (Fahrverbrauch, sonst Heim + Extern) ÷ Σ km × 100 | [BERECHNUNGEN: Heimladung und Fahrverbrauch — zwei verschiedene Mengen (ab N-555)](BERECHNUNGEN.md#heimladung-und-fahrverbrauch--zwei-verschiedene-mengen-ab-n-555) | — |
| `e_auto_pv_anteil_prozent` | PV-Anteil Ladung | % | `sensor` · `measurement` | PV-Heimladung ÷ Heimladung (PV + Netz) × 100 | [BERECHNUNGEN: PV-Anteil der Heimladung: gemessen, sonst abgeleitet (ab 2026-08-08, N-141)](BERECHNUNGEN.md#pv-anteil-der-heimladung-gemessen-sonst-abgeleitet-ab-2026-08-08-n-141) | — |
| `e_auto_ersparnis_vs_benzin_euro` | Ersparnis vs Benzin | € | `sensor` · `monetary` · `total` | Benzinkosten (alternativ) - Stromkosten | [BERECHNUNGEN: E-Mob-Ersparnis im Cockpit](BERECHNUNGEN.md#e-mob-ersparnis-im-cockpit) | — |
| `speicher_zyklen` | Vollzyklen | — | `sensor` · `total_increasing` | Entladung ÷ Kapazität | [BERECHNUNGEN: Vollzyklen — eine Definition für alle Sichten](BERECHNUNGEN.md#vollzyklen--eine-definition-für-alle-sichten) | Speicher-KPIs. `speicher_zyklen` = **Entladung ÷ Brutto-Kapazität** — seit 2026-07-28 dieselbe Definition wie in Komponenten-Hub, Cockpit und PDF ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)). Nicht zu verwechseln mit den „SoC-Hüben" der Energieprofil-Tabelle. |
| `speicher_effizienz_prozent` | Speicher-Effizienz | % | `sensor` · `measurement` | Entladung ÷ Ladung × 100 | [BERECHNUNGEN: Round-Trip-Wirkungsgrad (η) — SoC-korrigiert, nicht roh](BERECHNUNGEN.md#round-trip-wirkungsgrad-η--soc-korrigiert-nicht-roh) | Speicher-KPIs. `speicher_zyklen` = **Entladung ÷ Brutto-Kapazität** — seit 2026-07-28 dieselbe Definition wie in Komponenten-Hub, Cockpit und PDF ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)). Nicht zu verwechseln mit den „SoC-Hüben" der Energieprofil-Tabelle. |
| `letzter_import_jahr` | Letzter Import - Jahr | — | `sensor` · `measurement` · `diagnostic` | Jahr des zuletzt erfassten Monats | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |
| `letzter_import_monat` | Letzter Import - Monat | — | `sensor` · `measurement` · `diagnostic` | Monat des zuletzt erfassten Datensatzes (1-12) | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |
| `letzter_import_monat_name` | Letzter Import - Monatsname | — | `sensor` · `diagnostic` | Monatsname (z.B. 'Dezember 2025') | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |
| `anzahl_monate_erfasst` | Erfasste Monate | — | `sensor` · `total` · `diagnostic` | Anzahl der erfassten Monatsdaten | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |

Zusätzlich erscheinen **pro Komponente** (E-Auto, Wärmepumpe, Speicher, Wallbox …) eigene Sensoren (z. B. `e_auto_pv_anteil_prozent`, `wp_cop_durchschnitt`, `wp_betriebsstunden`). Sie hängen — wie alle eedc-Sensoren — **unter dem einen Gerät deiner Anlage**; der Gerätename steht im Sensornamen (*„Daikin3 ECH₂O COP Durchschnitt"*).

> **E-Auto: `e_auto_verbrauch_kwh_100km` und `e_auto_pv_anteil_prozent`.** Der Verbrauch je 100 km folgt derselben Regel wie die App: je Monat der gemessene Fahrverbrauch (Feld „Verbrauch"), sonst die Ladung (Heim + Extern); über den Zeitraum die **Summe der Monatswerte geteilt durch die Summe der Kilometer** dieser Monate. Das Attribut **`quelle`** sagt `gemessen` (jeder Monat mit Kilometern hat einen Fahrverbrauch) oder `ladung` (Näherung über die Ladung, inkl. Ladeverluste). Bis v4.0.50 war der Sensor meist leer, weil eedc den erfassten Fahrverbrauch beim Start in eine Ladung umbuchte — er erscheint jetzt neu. Der **PV-Anteil** bezieht sich auf die **Heimladung** (PV + Netz), nicht auf „Ladung gesamt" mit Extern.
>
> **E-Auto: `e_auto_ersparnis_vs_benzin_euro`.** Die Ersparnis gegenüber dem Verbrenner zieht die **externen Ladekosten** ab — nach derselben Regel wie der E-Auto-Hub: steht die externe Ladung am Wallbox-Topf und am Auto, zählt das Paar mit den höheren Kosten. Sensor und Hub nennen damit für denselben Zeitraum dieselbe Zahl. ⚠ **Bis v4.0.50 blieb das Laden unterwegs im Sensor unberücksichtigt**: wer externe Ladung pflegt, sieht ihn — und über den E-Auto-Posten `jahres_ersparnis_euro`, `roi_prozent`, `amortisation_jahre` — einmalig sinken bzw. die Amortisation länger werden; in der Langzeitstatistik ist das ein Sprung an einem Tag, es gehen keine Daten verloren.

> ⛔ **Hier stand bis August 2026 „jeweils unter einem eigenen HA-Gerät", und genau so war es mit v4.0.30 auch gebaut.** Zwei Anwender haben innerhalb von 24 Stunden gemeldet, dass das Ergebnis schlechter ist: Bei einer PV-Anlage mit mehreren Modulflächen, Wechselrichter und Speicher entstehen so **etliche HA-Geräte mit je einer einzigen Entität** — zusätzlich zum Gerät der Integration. Seit **v4.0.32** gibt es wieder **ein** Gerät je Anlage.
>
> ⭐ **Für bestehende Installationen ändert sich nichts an den Daten:** `unique_id` und Topic hängen an der Komponente, nicht am Gerät. Home Assistant erkennt dieselben Entitäten wieder und hängt sie lediglich um — `entity_id`, Langzeitstatistik und Automationen bleiben erhalten, der angezeigte Name ebenfalls (HA setzt ihn aus Gerät + Sensor zusammen). ⚠ Die alten, jetzt leeren Geräte entfernt HA beim nächsten Neustart; sonst lassen sie sich einmalig von Hand löschen.

### Steuerungshilfen — die Gruppe für Automationen (neu)

Stufe 1 der Sensorliste sagt, **was ist**. Diese Gruppe sagt, **was jetzt gilt** und **wann es gilt** — die zwei Fragen, die eine Automation stellt. Alle Sensoren hier sind anlagenweit; die Geräte-Stücke stehen weiter unten.

⛔ **Sie sind Vorschläge, keine Anweisungen.** eedc schaltet nichts, ruft keinen Dienst auf und schreibt nichts nach Home Assistant. Es nennt ein Fenster und einen Betrag; was daraus folgt, entscheidest du.

| Schlüssel | Name | Einheit | Klassen | Formel | Regel | Hinweise |
|---|---|---|---|---|---|---|
| `eedc_ueberschuss_heute_kwh` | Überschuss heute | kWh | `sensor` · `energy` · `total` | Σ max(0; Erzeugung − Verbrauch) heute bis jetzt (15-Minuten-Takt); Defizit als Attribut | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Σ des heutigen Überschusses bis jetzt (Erzeugung über Verbrauch). Attribute: `defizit_heute_kwh`, `stand` (bis zu welcher Stunde gerechnet wurde) |
| `eedc_ueberschuss_jetzt_kw` | Überschuss letzte Stunde | kW | `sensor` · `power` · `measurement` | Überschuss der letzten vollständigen Stundenzeile (Stundenmittel); negativ = Defizit | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Überschuss der **letzten vollständigen Stunde**; **negativ = Defizit**. Attribute: `stunde`, `defizit_kw`. ⚠ Das ist ein Stundenmittel und bis zu 15 Minuten alt — einen Live-Überschuss gibt es in eedc als Größe nicht, und ein „ungefährer Live-Wert" wäre in einer Automation die teuerste Sorte Zahl |
| `eedc_speicher_voll_um_ts` | Speicher voll um (Zeitstempel) | — | `sensor` · `timestamp` | Derselbe Zeitpunkt wie der Textsensor 'Speicher voll um' — als ISO-8601-Zeitstempel, damit HA 'in 2 h' anzeigen kann | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Derselbe Zeitpunkt wie der Textsensor `eedc_speicher_voll_um`, nur als ISO-8601-Zeitstempel — damit HA „in 2 h" anzeigen kann. ⚠ **Der alte Sensor bleibt unverändert** („14:00"): sein Textformat ist seit v4.0.27 Vertrag, und ein Umbau bräche jede Automation, die ihn vergleicht. Attribut `quelle` nennt den Partner; `sim_start_stunde`/`sim_start_anteil` nennen die Startannahme der Simulation (s. `eedc_speicher_voll_um`) |
| `eedc_speicher_soc_prozent` | Ladestand | % | `sensor` · `battery` · `measurement` | Kapazitätsgewichteter Ladestand aller Speicher der Anlage; Aufschlüsselung je Speicher als Attribut | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Kapazitätsgewichteter Ladestand aller Speicher. Attribut `je_speicher` schlüsselt nach Gerät auf — **nur die heute laufenden**: ein stillgelegter Speicher steht weiter in der Historie, aber nicht mehr in dieser Aufschlüsselung. Der Ladestand selbst ist davon unberührt |
| `eedc_netzbezug_spitze_heute_kw` | Netzbezugs-Spitze heute | kW | `sensor` · `power` · `measurement` | Höchste gemessene Netzbezugs-Leistung heute; die Stunde mit dem höchsten Stundenmittel als Attribut | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Höchste heute gemessene Netzbezugs-**Leistung**. ⚠ Die Attribute `stunde_max_mittel`/`max_mittel_kw` nennen eine **andere** Größe: die Stunde mit dem höchsten Stunden**mittel**. Eine Uhrzeit zum Leistungs-Peak gibt es in eedc nicht, und sie wird hier auch nicht erfunden |
| `eedc_ueberschuss_prognose_heute_kwh` | Überschuss-Prognose heute | kWh | `sensor` · `measurement` | Σ max(0; PV-Prognose − Verbrauchsprognose) je Stunde heute; Stundenreihen und Überschuss-Blöcke als Attribut | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Σ des für **heute erwarteten** Überschusses. Attribute: `stundenprofil_kwh` und `defizit_stundenprofil_kwh` (je 24 Slots) sowie `fenster` — alle zusammenhängenden Überschuss-Blöcke mit `ab`, `bis`, `stunden`, `min_kw`, `summe_kwh`. ⭐ **Das ist die Größe, die sonst niemand hat:** eine Wallbox kennt das Auto, eine Wärmepumpe kennt sich selbst — den Verbrauchsgang *dieses* Hauses mit Wärmepumpen-Korrektur kennt nur eedc |
| `eedc_arbitrage_vorschlag_kwh` | Arbitrage-Vorschlag | kWh | `sensor` | Empfohlene Netzladung heute — laden in günstigen Stunden, entladen gegen das teuerste Defizit danach; Ersparnis als Attribut | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Empfohlene **Netzladung** des Speichers heute — laden in günstigen Stunden, entladen gegen das teuerste Defizit danach. Attribute: `stunden`, `ersparnis_cent`, `soc_prozent`, `frei_kwh`, `wirkungsgrad_prozent`, `arbitrage_faehig`. ⚠ Er entsteht **nur**, wenn mindestens ein Speicher „lädt aus dem Netz" gesetzt hat **und** sich etwas lohnt — sonst gibt es ihn nicht (eine 0 hieße „geprüft und lohnt nicht", und das ist eine andere Aussage) |
| `eedc_bestes_fenster_ab` | Bestes Fenster ab | — | `sensor` · `timestamp` | Beginn des günstigsten 2-Stunden-Fensters ab jetzt; die Dauern 1/2/3/4 h und das Kostenprofil je kWh als Attribut | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | Beginn des günstigsten **2-Stunden-Fensters** ab jetzt. Attribute `dauer_1h`/`_2h`/`_3h`/`_4h` je mit `ab`, `bis`, `stunden`, `kosten_cent_kwh`, `delta_cent_kwh_vs_jetzt`; dazu `kosten_profil_cent_kwh` und `preis_profil_cent_kwh` (je Slot) und `frist`. ⚠ **Bei einem Festpreis ohne Überschuss gibt es keine günstigste Stunde** — jede kostet gleich viel, und das Fenster beginnt dann schlicht jetzt. Erst der Überschuss macht einen Unterschied; `delta_cent_kwh_vs_jetzt` steht dort auf 0. ⭐ **Warum vier feste Dauern:** Ein Sensor kann keinen Parameter entgegennehmen — eine Dashboard-Karte liest Zustände, sie ruft keine Dienste. Das Kostenprofil ist **mengenneutral** (gilt für eine kWh) und deckt damit „jetzt oder um 14 Uhr" für Waschmaschine, Trockner, Spülmaschine und Auto |
| `eedc_prognose_abweichung_heute_prozent` | Prognose-Abweichung heute | % | `sensor` · `measurement` | (IST bis zur letzten vollen Stunde − Prognose bis dahin) ÷ Prognose × 100 — negativ = weniger erzeugt als vorhergesagt | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | (IST bis zur letzten vollen Stunde − Prognose bis dahin) ÷ Prognose × 100; negativ = weniger erzeugt als vorhergesagt. Attribute: `ist_kwh`, `prognose_kwh`, `bis_stunde`, `mae_30_tage_prozent` |
| `eedc_bezugspreis_jetzt_cent` | Bezugspreis jetzt | ct/kWh | `sensor` · `measurement` | Arbeitspreis der laufenden Stunde: bei Festpreis/Zeitfenster exakt aus dem Tarif, bei dynamischem Tarif (1 + USt) × Börse + abgeleiteter Aufschlag; `preisquelle` sagt, welcher Fall | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Was **du** in der laufenden Stunde je Kilowattstunde zahlst. Bei Festpreis oder Zeitfenstern **exakt** der Arbeitspreis deines Tarifs; bei einem dynamischen Tarif `(1 + USt) × Börsenpreis + Aufschlag`, wobei der Aufschlag **abgeleitet** wird (s. den Kasten „Woher der Preis je Stunde kommt"). Attribute: `preisquelle`, `aufschlag_cent`, `aufschlag_quelle`, `aufschlag_basis`, `ust_prozent`, `tarif`, `gueltig_ab`, `markt` (nur bei Börsenbezug), `stundenprofil_cent` und `stundenprofil_morgen_cent` (je 24 Slots), `waermepumpe_cent` (nur bei **eigenem** WP-Tarif) |
| `eedc_einspeiseverguetung_cent` | Einspeisevergütung | ct/kWh | `sensor` · `measurement` | Vergütung je eingespeister kWh — Stammwert des Tarifs, bei variabler Vergütung der Monatswert | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Vergütung je eingespeister Kilowattstunde. Attribute: `verguetung_quelle` (`vertrag` · `monatswert`), `einspeisung_variabel`. ⚠ Bei variabler Vergütung gibt es den Sensor **nur mit gepflegtem Monatswert** — der Stammwert beschreibt diesen Monat dann ausdrücklich nicht |
| `eedc_eigenverbrauch_wert_cent` | Eigenverbrauch wert | ct/kWh | `sensor` · `measurement` | Bezugspreis − Einspeisevergütung: was eine selbst verbrauchte kWh spart (nur mit vollständigem Bezugspreis) | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Was eine selbst verbrauchte Kilowattstunde **spart**: Bezugspreis − Einspeisevergütung. ⚠ Er entsteht nur mit einem **vollständigen** Bezugspreis; bei einem dynamischen Tarif ohne ableitbaren Aufschlag wäre „nackter Börsenpreis minus Vertragsvergütung" keine Näherung, sondern eine Differenz aus zwei verschiedenen Preisebenen — dann fehlt er, und `eigenverbrauch_wert_grund` am Bezugspreis-Sensor sagt warum |
| `eedc_speicher_strom_kosten_cent` | Speicherstrom kostet | ct/kWh | `sensor` · `measurement` | Einspeisevergütung ÷ Wirkungsgrad — was eine aus dem Speicher entnommene kWh kostet (gemessener oder gepflegter η, nie der Default) | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Was eine aus dem Speicher **entnommene** Kilowattstunde kostet: die entgangene Einspeisevergütung ÷ Wirkungsgrad. Attribute: `wirkungsgrad_prozent`, `wirkungsgrad_quelle` (`gemessen` · `parameter`), `wirkungsgrad_messung`, `je_speicher`, `verguetung_cent`. ⭐ **Nie mit dem Vorgabewert:** gibt es weder einen gemessenen noch einen gepflegten Wirkungsgrad, entsteht der Sensor **nicht**. ⚠ `wirkungsgrad_messung` sagt immer, was die Messung ergeben hat — und jedes Wort verlangt einen anderen Handgriff: `zu-wenig-monate` (noch nicht genug erfasste Monate — das wächst von allein) · **`keine-entladung`** (Monate genug, aber die Entladung deines Speichers ist nicht erfasst — ordne ihr eine Quelle zu oder pflege den Wert; das geht nie von allein weg) · `keine-ladung` (im Fenster wurde gar nicht geladen) · `fenster-zu-kurz` (kurzes Fenster und kein SoC-Sensor) · `nicht-ermittelbar` (der gemessene Quotient ist unmöglich — der Daten-Checker sagt wo) |
| `eedc_speicher_netzladen_kosten_cent` | Netzladen kostet | ct/kWh | `sensor` · `measurement` | Bezugspreis der laufenden Stunde ÷ Wirkungsgrad — nur für Speicher, die aus dem Netz laden dürfen | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Dasselbe für Strom aus dem Netz: Bezugspreis der laufenden Stunde ÷ Wirkungsgrad. Entsteht nur für Speicher mit „lädt aus dem Netz" |
| `eedc_speicher_leer_um_ts` | Speicher leer um | — | `sensor` · `timestamp` | Ende der ersten Stunde nach jetzt, in der der Ladestand in den Leerstand übergeht — Simulation, derselbe Lauf wie bei Speicher voll um | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Wann der Ladestand nach heutiger Simulation **in den Leerstand übergeht** — derselbe Lauf wie „Speicher voll um". Gibt es keinen solchen Übergang, gibt es den Sensor nicht. ⚠ **Der Zeitpunkt kann in der Vergangenheit liegen:** die Simulation startet bei der zuletzt gemessenen Stunde (`sim_start_stunde`/`sim_start_anteil`), nicht bei „jetzt" — hinkt Home Assistant nach, kann der Übergang in diese Lücke fallen, und der Sensor sagt dann, seit wann der Speicher nach dem Modell leer ist |
| `eedc_abregelung_heute_kwh` | Abregelung heute | kWh | `sensor` · `measurement` | Erwarteter Kappungsverlust heute an der Wechselrichter-Grenze — in der Skala der Rohprognose (vor der eedc-Korrektur) | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | Wie viel Erzeugung heute voraussichtlich an der Wechselrichter-Grenze **abgeregelt** wird. Attribute: `skala`, `stundenprofil_kwh`, `rest_heute_kwh`, `grenzen_kw`. ⚠ **In der Skala der Rohprognose** (s. den Hinweis unter der Tabelle). Ohne gepflegte AC-Grenze gibt es ihn nicht — 0 dagegen heißt „heute wird nichts abgeregelt" |

> **An Tagen aus dem HA-Spiegel bzw. den eigenen Zählerständen** (seit S5a) kommen `eedc_ueberschuss_heute_kwh` und
> `eedc_ueberschuss_jetzt_kw` sowie das Stundenmittel von `eedc_netzbezug_spitze_heute_kw` aus denselben Stunden wie
> *Cockpit → Tag* — der Überschuss heute ist dort Σ der Stunden aus dem Spiegel, „letzte Stunde" die letzte Stunde, für
> die Home Assistant schon einen Wert hat. Die Zeitangaben (`seit`, `stunde_von`/`stunde_bis`, `stand`,
> `stunde_max_mittel`) stehen dann im Kalendertag (Stunde „11–12" = 11:00 bis 12:00), wie die Stundenansicht. Die
> Netzbezugs-Spitze selbst (Leistung) bleibt die gemessene Spitze des Tages. Eine Stunde, die Home Assistant mit der
> Menge mehrerer Stunden nachliefert, zählt für „jetzt" nicht (sie ist kein Stundenmittel); ihre Energie steht im
> Überschuss heute.

**Die Schalter (`binary_sensor`) — an, aus oder nicht verfügbar**

| Schlüssel | Name | Einheit | Klassen | Formel | Regel | Hinweise |
|---|---|---|---|---|---|---|
| `eedc_ueberschuss_verfuegbar` | Überschuss verfügbar | — | `binary_sensor` · `power` | AN, wenn der Überschuss der letzten vollen Stunde über 0 liegt | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | **AN:** Die letzte volle Stunde hatte Überschuss **Attribute:** `seit` |
| `eedc_guenstige_stunde` | Günstige Stunde | — | `binary_sensor` | AN, wenn die laufende Stunde unter der Günstig-Schwelle liegt (dieselbe Markierung wie der Börsenpreis-Rang) | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | **AN:** Die laufende Stunde liegt unter der Günstig-Schwelle — **dieselbe** Markierung, die `eedc_preis_rang` trägt **Attribute:** `schwelle_cent`, `preis_cent` |
| `eedc_speicher_voll` | Speicher voll | — | `binary_sensor` | AN, wenn der kapazitätsgewichtete Ladestand der Anlage bei 99 % oder darüber liegt | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | **AN:** Ladestand ≥ 99 % **Attribute:** `soc_prozent`, `schwelle_prozent` |
| `eedc_prognose_auffaellig` | Prognose-Abweichung auffällig | — | `binary_sensor` · `problem` | AN, wenn die Tagesabweichung über dem Doppelten des mittleren Fehlers der letzten 30 Tage liegt — frühestens nach 3 vollen Sonnenstunden | [§ Steuerungshilfen — die Gruppe für Automationen (neu)](#steuerungshilfen--die-gruppe-für-automationen-neu) | **AN:** Die Tagesabweichung liegt über dem **Doppelten** des mittleren Fehlers der letzten 30 Tage — frühestens nach 3 vollen Sonnenstunden **Attribute:** `schwelle_prozent`, `mae_30_tage_prozent`, `mae_tage`, `sonnenstunden_bisher`, ggf. `grund` |
| `eedc_speicher_reicht_bis_mitternacht` | Speicher reicht bis Mitternacht | — | `binary_sensor` | AN, wenn der Ladestand bis Mitternacht nicht in den Leerstand übergeht und über der Schwelle endet — dieselbe Regel, derselbe Lauf | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | **AN:** Der Ladestand geht bis Mitternacht **nicht** in den Leerstand über und endet über der Schwelle — dieselbe Regel und derselbe Simulationslauf wie „Speicher leer um" **Attribute:** `min_soc_prozent`, `min_soc_um`, `end_soc_prozent`, Modell-Angaben |
| `eedc_einspeisung_unerwuenscht` | Einspeisung unerwünscht | — | `binary_sensor` | AN, wenn der Börsenpreis der laufenden Stunde negativ ist UND für dieselbe Stunde PV-Erzeugung erwartet wird (§51 EEG als Slot-Regel) | [BERECHNUNGEN: Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)](BERECHNUNGEN.md#preis--und-speicher-sensoren-des-ha-exports-stufe-3b) | **AN:** Der Börsenpreis der laufenden Stunde ist **negativ** und für dieselbe Stunde wird PV-Erzeugung erwartet (§51 EEG). ⛔ Das ist ein Marktzustand, kein Urteil — was daraus folgt, entscheidest du **Attribute:** `boersenpreis_cent`, `pv_prognose_kwh`, `ueberschuss_prognose_kwh`, `negative_stunden_heute`, `naechste_negative_ab` |

> **Warum „Abregelung heute" in der Skala der Rohprognose steht.** Der Wert ist die Differenz zwischen dem, was deine Module könnten, und dem, was der Wechselrichter durchlässt — und diese Kappung rechnet eedc auf der **ungefilterten** OpenMeteo-Prognose, **bevor** der gelernte Korrekturfaktor deiner Anlage darauf angewendet wird. Das Attribut `skala: openmeteo_roh_vor_korrektur` sagt es ausdrücklich.
>
> ⭐ **Den Verlust mitzukorrigieren wäre falsch, nicht nur ungenau.** Kappung ist `max(0, Leistung − Grenze)` — sie skaliert nicht mit einem Faktor. Eine Anlage, deren Rohprognose die Grenze um 1 kW überschreitet, hat bei einem Korrekturfaktor von 0,8 nicht 0,8 kW Verlust, sondern unter Umständen **gar keinen**: das korrigierte Profil liegt dann komplett unter der Grenze. Eine „korrigierte Abregelung" wäre eine Zahl, die niemand gerechnet hat.
>
> **Was du damit anfangen kannst:** die Größenordnung und die **Uhrzeiten**. `stundenprofil_kwh` zeigt, in welchen Stunden gekappt wird — das sind die Stunden, in denen sich eine verschiebbare Last am meisten lohnt, weil ihr Strom sonst gar nicht erst entsteht. `grenzen_kw` nennt die Grenzen, an denen gekappt wird, `rest_heute_kwh` den noch bevorstehenden Teil.

> **Warum die Ampel „Prognose-Abweichung auffällig" heißt und nicht „Anlage defekt".** eedc sieht Verschattung, Schnee auf den Modulen, einen ausgefallenen Sensor und einen echten Defekt als **dieselbe Zahl**. Ein Urteil wäre eine Behauptung über eine Ursache, die eedc nicht kennt. Die Schwelle ist außerdem **anlagenspezifisch**: Sie hängt am mittleren Fehler *deiner* Anlage der letzten 30 Tage — eine Anlage mit 8 % Streuung schlägt bei 16 % an, eine mit 25 % erst bei 50 %. Ein fester Prozentwert hätte je nach Anlage entweder dauernd oder nie ausgelöst. **Ohne Genauigkeits-Tracking gibt es die Ampel nicht.**

### Was ein `binary_sensor` in eedc ist — und was er nicht kann

Bis September 2026 hat eedc genau **eine** Sorte HA-Entität angelegt: `sensor`. Mit den Steuerungshilfen kommt eine zweite dazu, der `binary_sensor` — er kennt zwei Zustände, `ON` und `OFF`, und keine Einheit, keine Langzeitstatistik über Zahlenwerte.

⚠ **Er kennt kein „unbekannt" — deshalb wird er *nicht verfügbar*.** Verliert ein `binary_sensor` seine Grundlage (der Preis-Abruf fällt aus, das Tagesprofil bricht ab), gibt es keinen dritten Zustand, den eedc schreiben könnte: Home Assistant protokolliert jeden anderen Wert als Fehler. eedc meldet die Entität stattdessen über einen eigenen Verfügbarkeits-Kanal als **nicht verfügbar** (`unavailable` in HA) und schreibt **keinen** Zustand.

⭐ **Warum das wichtiger ist, als es klingt.** Bliebe stattdessen einfach der letzte Zustand stehen, bekäme eine Automation ihn weiter als Wahrheit geliefert — ein ausgefallener Preisabruf ließe `eedc_guenstige_stunde` womöglich dauerhaft auf `ON` stehen, und das Auto lüde zur teuersten Stunde. Ein fehlender Eingang muss sichtbar sein; „nicht verfügbar" ist die einzige Form, die HA dafür kennt.

**Was das für Automationen heißt:** Eine Bedingung `is_state('binary_sensor.eedc_haus_gunstige_stunde', 'on')` (Anlage „Haus" — die Entity-ID trägt deinen Anlagennamen, s. die Automations-Beispiele am Ende von §11) ist bei einem Ausfall von selbst `false` — sie löst nicht mehr fälschlich aus. Wer den Unterschied zwischen „aus" und „keine Daten" ausdrücklich behandeln will, fragt `states(...) == 'unavailable'` ab. Für einen **gewöhnlichen Sensor** gilt das *nicht*: der zeigt bei fehlendem Wert weiterhin „unbekannt" (`unknown`) und bleibt verfügbar — dort ist der leere Wert selbst die Aussage.

### Stufe 3 je Gerät — Fenster mit Betrag

Diese Sensoren entstehen **je Gerät** und nur, wenn eedc alle drei Fragen aus vorhandenen Daten beantworten kann: *wie viel* (die Menge des Geräts), *wogegen* (Preis- bzw. Überschussreihe) und *was kommt heraus* (ein Fenster mit Betrag). Fehlt eine Antwort, fehlt der Sensor.

| Schlüssel | Name | Einheit | Klassen | Formel | Regel | Hinweise |
|---|---|---|---|---|---|---|
| `wp_betriebsmodus` | Betriebsmodus | — | `sensor` | Aktueller Betriebsmodus laut zugeordneter climate-Quelle, über den Kanon normalisiert (Heizen · Warmwasser · Kühlen · Entfeuchten · Lüften · Aus · Unbestimmt); hvac_action verfeinert ihn, wo das Gerät sie liefert: Nennt sie eine Richtung (Heizen/Kühlen/Entfeuchten/Lüften) oder Aus, gilt sie; Leerlauf (idle) behält den eingestellten Modus, weil ein taktendes Gerät seine Betriebsart nicht verliert. Ohne zugeordnete Quelle gibt es den Sensor nicht. | [BERECHNUNGEN: 3.5b Modus-Split: Heizen und Kühlen trennen (#263 K-2)](BERECHNUNGEN.md#35b-modus-split-heizen-und-kühlen-trennen-263-k-2) | — |
| `wp_cop_durchschnitt` | COP Durchschnitt | — | `sensor` · `measurement` | Wärmeenergie ÷ Stromverbrauch | [BERECHNUNGEN: 3.5d Arbeitszahl je Funktion und die Arbeitszahl Kühlen (W-4 · W-5)](BERECHNUNGEN.md#35d-arbeitszahl-je-funktion-und-die-arbeitszahl-kühlen-w-4--w-5) | — |
| `wp_ersparnis_euro` | WP Ersparnis | € | `sensor` · `monetary` · `total` | Kosten alte Heizung - WP-Kosten | [BERECHNUNGEN: WP-Ersparnis im Cockpit — Σ der Gerätezeilen je Monat](BERECHNUNGEN.md#wp-ersparnis-im-cockpit--σ-der-gerätezeilen-je-monat) | — |
| `wp_strom_heizen_modus_kwh` | Strom Heizbetrieb | kWh | `sensor` · `energy` · `total` | Σ Stunden im Heizbetrieb × Stromverbrauch (Teilmenge des Gesamtstroms) | [BERECHNUNGEN: 3.5b Modus-Split: Heizen und Kühlen trennen (#263 K-2)](BERECHNUNGEN.md#35b-modus-split-heizen-und-kühlen-trennen-263-k-2) | — |
| `wp_strom_warmwasser_modus_kwh` | Strom Warmwasserbetrieb | kWh | `sensor` · `energy` · `total` | Σ Stunden im Warmwasserbetrieb × Stromverbrauch (Teilmenge des Gesamtstroms) | [BERECHNUNGEN: 3.5b Modus-Split: Heizen und Kühlen trennen (#263 K-2)](BERECHNUNGEN.md#35b-modus-split-heizen-und-kühlen-trennen-263-k-2) | — |
| `wp_strom_kuehlen_modus_kwh` | Strom Kühlbetrieb | kWh | `sensor` · `energy` · `total` | Σ Stunden im Kühlbetrieb × Stromverbrauch (Teilmenge des Gesamtstroms) | [BERECHNUNGEN: 3.5b Modus-Split: Heizen und Kühlen trennen (#263 K-2)](BERECHNUNGEN.md#35b-modus-split-heizen-und-kühlen-trennen-263-k-2) | — |
| `wp_kompressor_starts` | Kompressor-Starts | — | `sensor` · `total` | Σ erfasste Kompressor-Starts (Laufzeit der WP) | [BERECHNUNGEN: Tageszusammenfassung (TagesZusammenfassung)](BERECHNUNGEN.md#tageszusammenfassung-tageszusammenfassung) | — |
| `wp_betriebsstunden` | Betriebsstunden | h | `sensor` · `duration` · `total` | Σ erfasste Betriebsstunden (Laufzeit der WP) | [BERECHNUNGEN: Tageszusammenfassung (TagesZusammenfassung)](BERECHNUNGEN.md#tageszusammenfassung-tageszusammenfassung) | — |
| `wp_warmwasserbetrieb` | Warmwasserbetrieb | — | `binary_sensor` · `running` | AN, wenn der live gelesene Betriebsmodus (höchstens 60 s alt) 'warmwasser' ist; ohne Modus-Zuordnung kein Sensor | [BERECHNUNGEN: 3.5g Steuerungs-Sensoren der Wärmepumpe (HA-Export E2/P4/P7/P8)](BERECHNUNGEN.md#35g-steuerungs-sensoren-der-wärmepumpe-ha-export-e2p4p7p8) | **AN:** Der live gelesene Betriebsmodus (höchstens 60 s alt) ist *Warmwasser*; ohne Modus-Zuordnung gibt es den Sensor nicht **Attribute:** `modus` |
| `wp_warmwasser_fenster_ab` | Warmwasser-Fenster ab | — | `sensor` · `timestamp` | Beginn des günstigsten 2-Stunden-Fensters heute für den Ø-Warmwasserstrom; Menge, Kosten und Herkunft (gemessen/abgeleitet) als Attribut | [BERECHNUNGEN: 3.5g Steuerungs-Sensoren der Wärmepumpe (HA-Export E2/P4/P7/P8)](BERECHNUNGEN.md#35g-steuerungs-sensoren-der-wärmepumpe-ha-export-e2p4p7p8) | Beginn des günstigsten 2-Stunden-Fensters heute für den **Ø-Warmwasserstrom je Tag** (letzte drei abgeschlossene Monate). Attribute: `bis`, `kosten_cent_kwh`, `kosten_cent`, `ersparnis_cent_vs_jetzt`, `menge_kwh`, **`herkunft`**. ⭐ `herkunft` sagt, woher die Menge stammt: `gemessen` (eigener Warmwasser-Zähler) oder `abgeleitet` (aus dem mitgeschriebenen Betriebsmodus gerechnet). **Beides reicht** — ohne Warmwasser-Zähler gibt es das Fenster trotzdem. Deckt auch den in der Wärmepumpe verbauten **Heizstab**: sein Strom läuft über denselben Zähler |
| `wp_heizfenster_stunden` | Günstige Heizstunden heute | h | `sensor` · `measurement` | Anzahl der Stunden innerhalb der erwarteten Heizzeit, in die sich das Heizprofil günstiger verschieben ließe; erwartetes Heizstrom-Stundenprofil als Attribut | [BERECHNUNGEN: 3.5g Steuerungs-Sensoren der Wärmepumpe (HA-Export E2/P4/P7/P8)](BERECHNUNGEN.md#35g-steuerungs-sensoren-der-wärmepumpe-ha-export-e2p4p7p8) | Anzahl der Stunden innerhalb der erwarteten **Heizzeit**, in die sich das Heizprofil günstiger verschieben ließe. Attribute: `heizstrom_stundenprofil_kwh` (so lang wie die Fenster-Achse, 25 bzw. 48 Slots, aus dem gelernten WP-Profil mit Heizgradtag-Korrektur), `guenstige_heizstunden`, `ersparnis_cent_vs_profil`, `heizzeit_stunden`. ⚠ **Was eedc nicht kennt und nicht erfindet:** Heizkurve, Vorlauftemperatur, Speichervermögen des Gebäudes. Wie weit eine Anhebung trägt, entscheidet deine Wärmepumpen-Regelung — eedc nennt Fenster und Preisvorteil, nicht die Gradzahl |
| `wp_kuehlfenster_ab` | Kühlfenster ab | — | `sensor` · `timestamp` | Beginn des Überschuss-Fensters vor der Stunde der Tageshöchsttemperatur (Vorkühlen); Frist und Überschussmenge als Attribut | [BERECHNUNGEN: 3.5g Steuerungs-Sensoren der Wärmepumpe (HA-Export E2/P4/P7/P8)](BERECHNUNGEN.md#35g-steuerungs-sensoren-der-wärmepumpe-ha-export-e2p4p7p8) | Beginn des günstigsten 2-Stunden-Fensters **vor** der Stunde der Tageshöchsttemperatur (Vorkühlen). Attribute: `bis`, `temperatur_max_um`, `temperatur_max_c`, `ueberschuss_kwh_im_fenster`, `menge_kwh`, `leistung_kuehlen_zugeordnet`. ⚠ **Zwei Bedingungen, beide nötig:** Der Kühlbetrieb muss einen **eigenen Stromzähler** haben (eine Kältemenge oder eine gepflegte Kühl-Leistung reicht nicht), und es muss in den letzten drei Monaten Kühlstrom geflossen sein. Kühlen bleibt dabei **keine Wärme-Achse** — das hier ist Strom-Timing, keine Effizienz-Kennzahl |
| `sonstiges_verbrauch_monat_kwh` | Verbrauch (Monat) | kWh | `sensor` · `energy` · `total` | Stromverbrauch dieses Geräts im laufenden Monat; PV-Anteil und Netzbezug als Attribut | [§ Stufe 3 je Gerät — Fenster mit Betrag](#stufe-3-je-gerät--fenster-mit-betrag) | Stromverbrauch dieses Geräts im **laufenden** Monat. Attribute: `pv_anteil_prozent` (Bezug PV ÷ (Bezug PV + Bezug Netz), dieselbe Definition wie die Kachel «PV-Anteil» im Cockpit; seit 10.11.2026, vorher ÷ Verbrauch), `bezug_pv_kwh`, `bezug_netz_kwh`. ⭐ **Das ist neu und zugleich Stufe 1:** Für Pool, Sauna, Trockner oder einen Heizstab mit eigenem Zähler exportierte eedc bisher **keinen einzigen Energiewert** |
| `sonstiges_fenster_ab` | Bestes Fenster ab | — | `sensor` · `timestamp` | Beginn des günstigsten 2-Stunden-Fensters für den Ø-Tagesverbrauch dieses Geräts | [§ Stufe 3 je Gerät — Fenster mit Betrag](#stufe-3-je-gerät--fenster-mit-betrag) | Günstigstes 2-Stunden-Fenster für den **Ø-Tagesverbrauch** dieses Geräts. Attribute: `bis`, `kosten_cent_kwh`, `menge_kwh`, `ersparnis_cent_vs_jetzt` |

> **Woher der Preis je Stunde kommt.** Der Ausgangspunkt ist **dein Tarif**, nicht die Börse — `preisquelle` sagt in jedem Fenster-Sensor, welcher der vier Fälle vorliegt:
>
> | `preisquelle` | Was drinsteht |
> |---|---|
> | `vertrag` | Der Arbeitspreis deines Tarifs, **exakt**. Für einen Festpreis ist das derselbe Wert in jeder Stunde |
> | `zeitfenster` | Der Preis des Zeitfensters, das die jeweilige Stunde deckt (Hoch-/Niedertarif, §14a) |
> | `boerse_plus_aufschlag` | Dynamischer Tarif: `(1 + USt) × Börsenpreis + Aufschlag`. Der **Aufschlag** ist abgeleitet — s. den nächsten Absatz |
> | `boersenpreis` | Dynamischer Tarif **ohne** ableitbaren Aufschlag: der nackte Börsenpreis als ausdrücklich beschriftete Näherung. Netzentgelte und Abgaben fehlen darin |
>
> ⭐ **Wie eedc den Aufschlag eines dynamischen Tarifs findet — ohne dass du ihn pflegst.** Die Annahme ist einfach: dein Endpreis ist der Börsenpreis plus ein über den Vertrag gleichbleibender Anteil. Diesen Anteil rechnet eedc aus, was ohnehin da ist, in dieser Reihenfolge:
>
> 1. **Aus deiner Abrechnung** — der letzte abgerechnete Monat innerhalb deines aktuellen Tarifs: dein Monats-Durchschnittspreis minus dem (verbrauchsgewichteten) Börsenmittel desselben Monats. Attribut `aufschlag_quelle: abrechnung 2026-08`.
> 2. **Aus gemessenen Stunden** — wenn du einen Strompreis-Sensor zugeordnet hast (Tibber, aWATTar): der mittlere Abstand zwischen gemessenem Endpreis und Börsenpreis der letzten sieben Tage (mindestens 24 Stunden). Attribut `aufschlag_quelle: sensor 7 tage`.
> 3. **Gar nicht** — dann bleibt der nackte Börsenpreis stehen, und `aufschlag_quelle` sagt `keiner`.
>
> **Es gibt kein Feld dafür, das du ausfüllen müsstest.** Trägt dein Vertrag einen Deckel oder eine Staffel, bekommst du einen Durchschnitt — und `aufschlag_basis` sagt, worauf er beruht.
>
> ⚠ **In einer Stunde mit Überschuss sinkt der Preis anteilig:** Wer dort zusätzlich verbraucht, verdrängt Einspeisung und keinen Netzbezug — bei 3 kWh Überschuss kostet die erste kWh nichts. Deshalb liegt ein Fenster mittags oft **vor** dem Preistal in der Nacht. Liegt gar kein Preis vor (kein Tarif hinterlegt), entstehen Fenster **nur innerhalb** der Überschuss-Stunden, und `preisquelle` sagt `keine`.
>
> ⛔ **Bis v4.0.49 stand hier der Börsenpreis für alle** — auch für einen Haushalt mit festem Arbeitspreis, der den Börsenpreis nie zu Gesicht bekommt. Die damalige Begründung („ein fester Aufschlag verschiebt jede Stunde um denselben Betrag und ist deshalb für die Fensterwahl neutral") hält nicht, sobald Überschuss im Spiel ist: der Überschussanteil mindert den Preis **anteilig**, ein Aufschlag verschiebt die Überschuss-Stunden also weniger als die übrigen — und die Reihenfolge der Fenster kann kippen.

> **Wie eedc eine Stunde beschriftet.** Jede Stundenangabe in diesen Sensoren sagt, ob sie einen **Beginn** oder ein **Ende** meint. Das ist nötig, weil eedc in Stunden-*Intervallen* rechnet: Der Slot „14" ist die Stunde von 13:00 bis 14:00 (dieselbe Konvention wie im HA-Energie-Dashboard und bei jedem Stromzähler — ein Zählerstand um 14:00 gehört zur Stunde davor).
>
> | Art | Attribute |
> |---|---|
> | **Beginn** — ab wann etwas gilt | `ab`, `seit`, `stunden`, `stunde_von`, `naechste_negative_ab`, `stunde_max_mittel`, `guenstige_heizstunden` |
> | **Ende** — bis wann gerechnet wurde, wann etwas erreicht ist | `bis`, `stand`, `frist`, `stunde_bis`, `bis_stunde`, alles auf `_um` (`speicher_voll_um`, `min_soc_um`) |
>
> Ein `stundenprofil_*`-Attribut trägt **24 Werte je Tag**, Index 0 ist die Stunde von 23:00 des Vortags bis 00:00 — genau wie `stundenprofil_kwh` der Prognose-Sensoren. Jede dieser Reihen nennt das im Attribut `slot_konvention: backward`.
>
> ⛔ **Bis v4.0.49 lagen fünf dieser Angaben eine Stunde daneben** (vier zu spät, `stand` eine voraus): die Fenster-Achse folgte der Börse, die stundenweise vorwärts beschriftet ist, während alle anderen Reihen rückwärts liegen. Wer eine Automation auf die alten Zeiten gebaut hat, verschiebt sie um eine Stunde.

> **Attribute je Verbrauchs-Sensor: `profil_typ` und `profil_tage`.** eedc führt **zwei** Verbrauchsmodelle, und das bleibt so: die Stundenreihen für heute stammen aus dem 7-Tage-Profil der Live-Kachel, die Speicher-Simulation hinter „Speicher voll um" und der Arbitrage-Vorschlag aus einem gewichteten 8-Wochen-Profil. Sie beantworten verschiedene Fragen. **Jeder Sensor nennt sein Modell** — wer zwei Zahlen verrechnet, sieht damit, ob sie aus derselben Annahme stammen.

### Wann ein Sensor `entity_category: diagnostic` trägt

Home Assistant meint damit *„schreibgeschützte Systemausgaben über den Zustand der Hardware"* (Batteriestand, Signalstärke, Laufzeit, Firmware). eedc hat keine Hardware — das Gegenstück ist der **Zustand der eedc-Instanz und ihrer Datenlage**, nicht der Zustand deiner Anlage:

| Kategorie | Was sie in eedc trägt |
| --- | --- |
| **ohne Kategorie** (Standard) | Alles, was eine Aussage über **die Anlage** macht: Mengen, Geld, CO₂, Kennzahlen, Prognosen, Preise — und auch Stammdaten wie die Investitionssumme. Diese Sensoren gehören aufs Dashboard. |
| **`diagnostic`** | Aussagen über **eedc selbst**: *Letzter Import* (Jahr/Monat/Monatsname) und *Erfasste Monate*. Sie beantworten „hat eedc aktuelle Daten?", nicht „wie läuft die Anlage?". |
| `config` / `system` | eedc exportiert nichts Steuerbares — beide bleiben ungenutzt. |

⚠ **Die Testfrage vor jeder neuen Definition:** *Beschreibt der Wert die Anlage oder eedc?* Die Investitionssumme etwa ist ein Stammdatum der Anlage und deshalb **kein** Diagnose-Wert — auch wenn sie sich nie ändert.

**Neu je Wärmepumpe/Klimaanlage:** `wp_betriebsmodus` — der **aktuelle** Betrieb im Klartext (*Heizen · Kühlen · Entfeuchten · Lüften · Aus · Unbestimmt*), aus der zugeordneten `climate`-Quelle — oder, ohne HA-Quelle, aus dem MQTT-Topic `…/betriebsmodus` (Wort oder Code 0–5) — über den eedc-Kanon normalisiert. Liefert dein Gerät zusätzlich `hvac_action` (den Ist-Betrieb), verfeinert der den eingestellten Modus: Nennt er eine Richtung, hat er Vorrang — steht dort **Leerlauf** (`idle`), bleibt dein eingestellter Modus stehen, denn ein taktendes Gerät verliert seine Betriebsart nicht. **Ohne zugeordnete Quelle gibt es den Sensor nicht** — eedc behauptet keinen Modus, den es nicht kennt.
>
**`wp_ersparnis_euro` und `wp_cop_durchschnitt` je Wärmepumpe (ab 05.09.2026 dieselbe Rechnung wie Hub und Cockpit):** Die Ersparnis kommt aus derselben Layer-Formel wie der Komponenten-Hub — je Monat mit dem Tarif seines Stichtags, mit dem Monats-Gaspreis, mit den fixen Zusatzkosten der Altheizung, und **ohne den Kühlstrom** (Kühlen ersetzt keine Heizung; das Attribut `berechnung` nennt den herausgehaltenen Betrag). Ist die Wärme geschätzt (Strom × JAZ) oder hängt ein zweiter Erzeuger am Wärmezähler, trägt der Sensor den Vorbehalt als Attribut **`vorbehalt`** — dieselben Worte wie unter der Ersparnis im Hub; in *Einstellungen → Integration → MQTT-Export* steht er unter der Berechnung. Die Arbeitszahl kennt dieselben Sperren wie der Hub (geschätzte Wärme, Heizstab-Fremdanteil, zweiter Erzeuger). Für den Strom je Betriebsart gibt es Sensoren für Heizen, Kühlen und Warmwasser; **Lüften und Entfeuchten** haben bewusst keinen — sie sind Mengen ohne Kennzahl (Cockpit und Hub zeigen sie), und eine Automation braucht sie nicht.

**Monate vor deinem ersten Stromtarif (`wp_ersparnis_euro`, `e_auto_ersparnis_vs_benzin_euro`, ab 12.10.2026):** Gilt in einem Monat noch kein Tarif, rechnen beide Sensoren mit der Vorbelegung 30 ct/kWh — derselbe Preis wie im Cockpit und in der Meldung des Daten-Checkers, über MQTT und REST gleich. Bis dahin nahm MQTT dafür den jüngsten Tarif-Eintrag (auch einen Wärmepumpen-, Wallbox- oder künftigen Tarif) und REST den heutigen Tarif; wer solche Monate hat, sieht einmalig einen Sprung in der Langzeitstatistik. Der Handgriff steht beim Daten-Checker: beim ältesten Tarif das „Gültig ab" auf den Beginn der Daten setzen.

**Derselbe Monatspreis für die Anlagen-Sensoren und den gepflegten Ø (ab 12.10.2026):** Auch Jahresersparnis, ROI und Amortisation der Anlage (über die bisherige Wärmepumpen- und E-Auto-Ersparnis) rechnen Monate vor dem ersten Tarif jetzt mit der Vorbelegung 30 ct statt mit dem heutigen Tarif. Und pflegst du im Monatsabschluss einen Ø-Strompreis, aber keinen eigenen Wärmepumpen-Tarif, nimmt `wp_ersparnis_euro` (und die Wärmepumpen-Ersparnis in ROI und Amortisation) diesen Ø — wie Cockpit und Wärmepumpen-Hub — statt des Tarif-Arbeitspreises; mit eigenem Wärmepumpen-Tarif bleibt es bei dessen Preis. Wer solche Monate oder einen gepflegten Ø ohne eigenen Wärmepumpen-Tarif hat, sieht in diesen Sensoren einmalig einen Sprung in der Langzeitstatistik.

**Ein Sensor, der seinen Wert verliert, bleibt nicht stehen (ab 05.09.2026):** Kann eedc einen Wert in einem Lauf nicht mehr bilden — die Arbeitszahl nach einem eingetragenen Fremdanteil, die Ersparnis nach „nichts ersetzt", ein Betriebsart-Sensor nach dem Entfernen seiner Quelle, der Speicher-Wirkungsgrad über 100 % —, setzt eedc den Sensor in Home Assistant auf **unbekannt**, statt den letzten Wert liegen zu lassen. Eine **gesperrte Kennzahl** trägt dabei ihren Grund im Attribut `grund` (dieselben Worte wie im Hub). Die Langzeitstatistik bekommt an dieser Stelle eine Lücke — das ist die richtige Aussage, keine Störung. Bis dahin blieb der letzte publizierte Wert stehen und lief stündlich in die Statistik weiter. Was nie erfasst war, bekommt weiterhin keinen Sensor.

> ⏱ **Aktualisierung im Publish-Takt** (Standard 60 Minuten, einstellbar). Für einen Modus, der in der Praxis saisonal gestellt wird, ist das genug; wer sekundengenau steuern will, liest die `climate`-Entität direkt. Was es **nur** von eedc gibt, ist die über die Stunde stabilisierte, auf den Kanon gebrachte Aussage — und dieselbe Einteilung, nach der eedc den Strom aufteilt.

> **Wertsemantik `netto_ertrag_euro` (ab v4.0):** Der Sensor trägt den kanonischen Netto-Ertrag aus dem Finanz-Aggregat-SoT: **Einspeiseerlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto** (Erträge − Ausgaben aus den Sonstigen Positionen, inklusive der auf **Anlage-Ebene** erfassten Positionen ab v4.0). Der Sensor-Name und die Einheit sind unverändert; nur der **Wert** enthält jetzt die Sonstigen Positionen. Achtung: die frühere Kurzformel „Einspeiseerlös + EV-Ersparnis" (noch als statisches `formel`-Label in der Definition) beschreibt nur zwei der vier Bausteine — maßgeblich ist die Summe in [Berechnungen §3.2](BERECHNUNGEN.md#32-finanzen-cockpit). Der **USt-Eigenverbrauchs-Abzug** (nur bei Regelbesteuerung) ist seit der #326-Inventur ebenfalls enthalten — `ha_export.py` rechnet `netto_ertrag -= ust_eigenverbrauch` über denselben SoT-Helper wie Cockpit und Aussichten. (Bis dahin stand hier das Gegenteil: „bleibt eine Cockpit-Zusatzlogik und ist im Export-Sensor nicht enthalten." Das war der Stand vor v4.0; die Zeile ist beim Fix nicht mitgezogen worden.)
>
> **Ergänzung 2026-07-31 (N-13):** Bei Anlagen mit einem **Dienstwagen** (E-Auto oder Wallbox mit „ausschließlich dienstliches Laden") zieht der Sensor jetzt auch die **dienstlichen Ladekosten** ab — bis dahin tat er das als einzige der drei Sichten nicht und stand damit über der Cockpit-Kachel, auf die er sich bezieht. Für diese Anlagen fällt der Wert einmalig; alle anderen sind unberührt. Formel und Begründung: [Berechnungen §3.10](BERECHNUNGEN.md).
>
> **Damit nennt der Sensor alle vier Abzüge/Bausteine der Cockpit-Kachel** — Einspeiseerlös, EV-Ersparnis, BKW-Ersparnis, Sonstige-Netto, abzüglich Netzbezugskosten, USt-Eigenverbrauch und dienstlicher Ladekosten. Er ist mit ihr deckungsgleich.

> **Wertsemantik `amortisation_jahre` · `roi_prozent` · `jahres_ersparnis_euro` (ab v4.0.12):** Nenner aller drei ist der **Kapitaleinsatz** — relevante Anschaffungskosten **plus** einmalige Ausgaben aus dem Monatsabschluss **minus** einmalige Erträge (Förderung, THG-Quote). Vorher wurde eine einmalige Ausgabe wie eine jährlich wiederkehrende Belastung vom Zähler abgezogen (eine Reparatur verlängerte die Amortisation dauerhaft und wurde jedes Folgejahr schlechter), ein einmaliger Ertrag wurde umgekehrt jedes Prognosejahr gutgeschrieben. Zweite Korrektur an derselben Rechnung: **jeder Ersparnis-Posten wird mit seiner eigenen Laufzeit** hochgerechnet, nicht mit der Monatszahl der Anlage — eine später angeschaffte Komponente wurde im Zähler zeitanteilig verdünnt, während ihre Kosten voll im Nenner standen.
>
> ⚠ **Die drei Sensoren springen dadurch einmalig** (an der Referenzanlage 26,4 → 18,5 Jahre); in der Langzeitstatistik ist das ein Sprung an einem Tag, es gehen keine Daten verloren. **`netto_ertrag_euro` ist unberührt** — die Zeitraum-Bilanz rechnet unverändert. Der ausgeschriebene **Rechenweg** im Attribut nennt seit derselben Version jeden Posten mit seiner Monatszahl und den Betriebskosten-Abzug; vorher wich er um mehrere hundert Euro vom Wert daneben ab. Herleitung: [Berechnungen §3.6](BERECHNUNGEN.md), Begriffe im [Glossar](GLOSSAR.md).

> **Wertsemantik `co2_ersparnis_kg` (ab v4.0, DI-2/DI-2-B):** Der Sensor trägt die **volle CO₂-Bilanz** aus dem kanonischen Helfer `berechne_co2_bilanz` — **PV-Eigenverbrauch** (inkl. der Erzeugung von BKW/sonstigen Erzeugern hinter dem Zähler) **+ Wärmepumpe** (vermiedenes Gas mit η_gas = 0,90 minus WP-Strom-CO₂) **+ E-Mobilität** (vermiedener Benziner minus Netzladung). Damit ist er **exakt deckungsgleich** mit der Cockpit-CO₂-Kachel (früher rechnete der Sensor nur `PV-Eigenverbrauch × Strom-Faktor`). Ein sonstiger Erzeuger (z. B. BHKW) zählt in EV/Autarkie, und sein selbst verbrauchter Strom gilt — wie im Geldwert — als vermiedener Netzstrom (0,38 kg/kWh); seine eigene Emission (etwa das Gas eines BHKW) zieht eedc nicht ab, weil es sie nicht kennt. Herleitung: [Berechnungen §3.8](BERECHNUNGEN.md#38-co2-bilanz).

> **Wertsemantik `autarkie_prozent` / `eigenverbrauch_quote_prozent` (ab v4.0, DI-2-B):** Beide Quoten werden **identisch zum Cockpit** gerechnet und beziehen die **Erzeugung hinter dem Zähler** ein (`erzeugung_hinter_zaehler_kwh` = PV inkl. Balkonkraftwerk + sonstige Erzeuger, die in denselben Hauszähler speisen). Der Nenner der Eigenverbrauchsquote ist diese Gesamt-Erzeugung, nicht „nur PV". Der **spezifische Ertrag** bleibt bewusst eine reine PV-Kennzahl (nur `pv_erzeugung`).

> **Spezifischer Ertrag — warum nicht einfach kWh ÷ kWp?** Der Sensor ist **annualisiert** und damit deckungsgleich mit der Cockpit-Kachel: saisonal gewichtet (PVGIS-Monatsverteilung) und mit der pro Monat tatsächlich aktiven PV-Leistung (Erweiterung/Teil-Rückbau wird korrekt gewichtet). Die naive Division *Gesamterzeugung ÷ heutiges kWp* würde bei 3 Jahren Historie etwa das Dreifache des gewohnten Jahreswerts anzeigen.
>
> **Woher die kWp im Nenner kommt (ab v4.0.2):** aus dem Feld **Leistung (kWp)** der jeweiligen Investition; ist es leer, aus den Detail-Feldern der Komponente (`kwp`/`leistung_kwp`, bei Balkonkraftwerken auch `leistung_wp` × `anzahl`). Vorher zählte nur das Leistungsfeld — bei importierten oder sehr alten Komponenten stand dort nichts, der Nenner war zu klein und der Sensorwert entsprechend **zu hoch**. Wer das betrifft, sieht nach dem Update einen einmaligen Sprung nach unten auf den richtigen Wert; Cockpit-Kachel und Sensor bleiben dabei deckungsgleich.

### PV-Prognose-Sensoren (`eedc_prognose_*`)

Quelle ist **immer die eedc-eigene Prognose** (OpenMeteo × Korrekturprofil) — nie Solcast/SFML, denn deren Werte liegen über die jeweilige HA-Integration ohnehin nativ in HA (kein Doppel-Export, keine Drift).

Die Korrektur erfolgt **pro Stunde** über die Korrekturprofil-Kaskade (Sonnenstand × Wetter → Saison-Stunde → Sonnenstand → Skalar; bei Anlagen ohne gelerntes Profil greift wie bisher der Lernfaktor-Skalar). Der Tagessensor ist dabei stets die Σ seiner korrigierten Stundenwerte — Sensor-State und `stundenprofil_kwh`-Attribut passen exakt zusammen. Dieselbe Berechnung speist die Spalte „eedc" im Prognosen-Vergleich: App-Ansicht und HA-Sensor zeigen denselben Tageswert.

> **Korrektur nur, wenn sie hilft:** war die Korrektur in den letzten 30 Tagen (Day-Ahead) mehr als 2 Prozentpunkte schlechter als die rohe OpenMeteo-Prognose, setzt eedc sie aus und alle Prognose-Sensoren zeigen die rohe Prognose, bis sie wieder hilft. `eedc_prognose_heute_kwh` trägt dazu die Attribute `korrektur_ausgesetzt` (`true`/`false`), `korrektur_mae_30_prozent` (mittlerer Fehler der Korrektur) und `roh_mae_30_prozent` (mittlerer Fehler der rohen Prognose) — beide MAE `null`, solange es keine vergleichbaren Tage gibt. Regel: [Berechnungen, „Korrektur nur, wenn sie hilft"](BERECHNUNGEN.md#korrektur-nur-wenn-sie-hilft).

> **Rest heute, nachgeführt:** `eedc_prognose_rest_today_kwh` und `eedc_prognose_heute_rollend_kwh` folgen ab einem Zehntel der Tagesprognose dem gemessenen Vormittag — eedc vergleicht das bisher Erzeugte mit der Prognose bis zur selben Stunde und skaliert den Rest mit einem gedämpften Faktor (0,4…1,6). Beide tragen das Attribut `nachfuehr_faktor` (1,0 = unverändert), «Rest heute» dazu `rest_modell_kwh` (der Rest ohne Nachführung). Das Stundenprofil an `eedc_prognose_heute_kwh` bleibt die Prognose — Σ der restlichen Slots und «Rest heute» unterscheiden sich um genau diesen Faktor. «Speicher voll um» (`eedc_speicher_voll_um`, `…_ts`) simuliert die Stunden ab dem Start mit denselben nachgeführten Slots. Regel: [Berechnungen §4](BERECHNUNGEN.md#4-prognosen-aussichten), Kasten «Heute nachgeführt».

| Schlüssel | Name | Einheit | Klassen | Formel | Regel | Hinweise |
|---|---|---|---|---|---|---|
| `eedc_prognose_heute_kwh` | PV-Prognose heute | kWh | `sensor` · `measurement` | Kanonische eedc-Tagesprognose (OpenMeteo × Korrekturprofil-Kaskade), == App-Anzeige; Stundenprofil als Attribut | [§ PV-Prognose-Sensoren (eedc_prognose_*)](#pv-prognose-sensoren-eedc_prognose_) | **Kanonische Tagesprognose** (== App-Anzeige): die volle Prognose für den ganzen Tag, **nicht** IST + Rest. Ändert sich, wenn OpenMeteo einen neuen Modelllauf liefert. Trägt das Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 Werte; Slot N = Energie der Stunde N−1 → N). · **PV-Tagesprognose heute** — voller Tageswert (kanonisch, rollt mit OpenMeteo, == Anzeige). |
| `eedc_prognose_heute_rollend_kwh` | PV-Prognose heute (nachgeführt) | kWh | `sensor` · `measurement` | Heute bereits erzeugt + eedc-Prognose der verbleibenden Stunden × Nachführ-Faktor aus dem gemessenen Vormittag — folgt dem IST, anders als die reine Tagesprognose | [BERECHNUNGEN: 4. Prognosen (Aussichten)](BERECHNUNGEN.md#4-prognosen-aussichten) | **Heute (nachgeführt)** — was heute bereits erzeugt wurde **plus** die Prognose der Reststunden, nachgeführt aus dem gemessenen Vormittag (Attribut `nachfuehr_faktor`, 1,0 = unverändert). Folgt dem IST; `…_heute_kwh` folgt dagegen OpenMeteo. Beide stehen bewusst nebeneinander (rapahl-PN 2026-08-23). |
| `eedc_prognose_rest_today_kwh` | PV-Prognose Rest heute | kWh | `sensor` · `measurement` | eedc-Prognose der verbleibenden Stunden heute, laufende Stunde anteilig nach Restminuten (OpenMeteo × Korrekturprofil-Kaskade) × Nachführ-Faktor aus dem gemessenen Vormittag | [§ PV-Prognose-Sensoren (eedc_prognose_*)](#pv-prognose-sensoren-eedc_prognose_) | **Echter Rest**: Prognose der verbleibenden Stunden ab jetzt (ohne IST) — die **laufende Stunde geht anteilig** nach den noch verbleibenden Minuten ein (#339), der Wert sinkt also gleichmäßig statt in Stundensprüngen. Ab einem Zehntel des Tages-SOLL **nachgeführt**: × Faktor aus dem gemessenen Vormittag (IST gegen Prognose bis zur selben Stunde, gedämpft, 0,4…1,6) — Attribute `nachfuehr_faktor` und `rest_modell_kwh` (der Rest ohne Nachführung). Der Steuerungswert für Automationen — „wie viel PV kommt heute noch?" · **Rest heute** — Prognose der verbleibenden Stunden, laufende Stunde anteilig nach Restminuten (#339); aus demselben Kanon → rollt synchron mit „heute". |
| `eedc_prognose_day_plus_1_kwh` | PV-Prognose morgen | kWh | `sensor` · `measurement` | eedc-Tagesprognose morgen = Σ korrigierte Stunden-Slots (OpenMeteo × Korrekturprofil-Kaskade); Stundenprofil als Attribut | [§ PV-Prognose-Sensoren (eedc_prognose_*)](#pv-prognose-sensoren-eedc_prognose_) | Tagesprognose morgen / übermorgen / in 3 Tagen. Trägt jeweils das korrigierte Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 kWh-Werte, Slot-Konvention wie oben) — z. B. für Lade-Planung per Template. Werte ändern sich, wenn OpenMeteo einen neuen Modelllauf liefert (alle paar Stunden) **oder** das gelernte Korrekturprofil aktualisiert wird (nächtlich) — stundenlang unveränderte Werte sind normal. · Attribut `stundenprofil_kwh` = 24 Backward-Slots (kWh); Sensor-State == Σ Slots. |
| `eedc_prognose_day_plus_2_kwh` | PV-Prognose übermorgen | kWh | `sensor` · `measurement` | eedc-Tagesprognose übermorgen = Σ korrigierte Stunden-Slots (OpenMeteo × Korrekturprofil-Kaskade); Stundenprofil als Attribut | [§ PV-Prognose-Sensoren (eedc_prognose_*)](#pv-prognose-sensoren-eedc_prognose_) | Tagesprognose morgen / übermorgen / in 3 Tagen. Trägt jeweils das korrigierte Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 kWh-Werte, Slot-Konvention wie oben) — z. B. für Lade-Planung per Template. Werte ändern sich, wenn OpenMeteo einen neuen Modelllauf liefert (alle paar Stunden) **oder** das gelernte Korrekturprofil aktualisiert wird (nächtlich) — stundenlang unveränderte Werte sind normal. · Attribut `stundenprofil_kwh` = 24 Backward-Slots (kWh); Sensor-State == Σ Slots. |
| `eedc_prognose_day_plus_3_kwh` | PV-Prognose in 3 Tagen | kWh | `sensor` · `measurement` | eedc-Tagesprognose Tag+3 = Σ korrigierte Stunden-Slots (OpenMeteo × Korrekturprofil-Kaskade); Stundenprofil als Attribut | [§ PV-Prognose-Sensoren (eedc_prognose_*)](#pv-prognose-sensoren-eedc_prognose_) | Tagesprognose morgen / übermorgen / in 3 Tagen. Trägt jeweils das korrigierte Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 kWh-Werte, Slot-Konvention wie oben) — z. B. für Lade-Planung per Template. Werte ändern sich, wenn OpenMeteo einen neuen Modelllauf liefert (alle paar Stunden) **oder** das gelernte Korrekturprofil aktualisiert wird (nächtlich) — stundenlang unveränderte Werte sind normal. · Attribut `stundenprofil_kwh` = 24 Backward-Slots (kWh); Sensor-State == Σ Slots. |
| `eedc_prognose_heute_vormittag_kwh` | PV-Prognose heute Vormittag | kWh | `sensor` · `measurement` | eedc-Prognose heute bis Solar Noon (Σ korrigierte Slots vor der astronomischen Tagesmitte; Grenze im Attribut solar_noon) | [BERECHNUNGEN: VM/NM-Split an Solar Noon (v3.22.0)](BERECHNUNGEN.md#vmnm-split-an-solar-noon-v3220) | PV-Prognose je Tageshälfte, für **heute und morgen** (die Abendentscheidung braucht den Folgetag). ⭐ **Die Grenze ist der Sonnenhöchststand**, nicht 13:00 — dieselbe Aufteilung wie in *Cockpit → Aussicht*. Sie reist als Attribut **`solar_noon`** („13:28") mit, damit eine Automation sie lesen kann statt sie zu raten. |
| `eedc_prognose_heute_nachmittag_kwh` | PV-Prognose heute Nachmittag | kWh | `sensor` · `measurement` | eedc-Prognose heute ab Solar Noon (Σ korrigierte Slots nach der astronomischen Tagesmitte; Grenze im Attribut solar_noon) | [BERECHNUNGEN: VM/NM-Split an Solar Noon (v3.22.0)](BERECHNUNGEN.md#vmnm-split-an-solar-noon-v3220) | PV-Prognose je Tageshälfte, für **heute und morgen** (die Abendentscheidung braucht den Folgetag). ⭐ **Die Grenze ist der Sonnenhöchststand**, nicht 13:00 — dieselbe Aufteilung wie in *Cockpit → Aussicht*. Sie reist als Attribut **`solar_noon`** („13:28") mit, damit eine Automation sie lesen kann statt sie zu raten. |
| `eedc_prognose_morgen_vormittag_kwh` | PV-Prognose morgen Vormittag | kWh | `sensor` · `measurement` | eedc-Prognose morgen bis Solar Noon — die Zahl für die Abendentscheidung (Grenze im Attribut solar_noon) | [BERECHNUNGEN: VM/NM-Split an Solar Noon (v3.22.0)](BERECHNUNGEN.md#vmnm-split-an-solar-noon-v3220) | PV-Prognose je Tageshälfte, für **heute und morgen** (die Abendentscheidung braucht den Folgetag). ⭐ **Die Grenze ist der Sonnenhöchststand**, nicht 13:00 — dieselbe Aufteilung wie in *Cockpit → Aussicht*. Sie reist als Attribut **`solar_noon`** („13:28") mit, damit eine Automation sie lesen kann statt sie zu raten. |
| `eedc_prognose_morgen_nachmittag_kwh` | PV-Prognose morgen Nachmittag | kWh | `sensor` · `measurement` | eedc-Prognose morgen ab Solar Noon — die Zahl für die Abendentscheidung (Grenze im Attribut solar_noon) | [BERECHNUNGEN: VM/NM-Split an Solar Noon (v3.22.0)](BERECHNUNGEN.md#vmnm-split-an-solar-noon-v3220) | PV-Prognose je Tageshälfte, für **heute und morgen** (die Abendentscheidung braucht den Folgetag). ⭐ **Die Grenze ist der Sonnenhöchststand**, nicht 13:00 — dieselbe Aufteilung wie in *Cockpit → Aussicht*. Sie reist als Attribut **`solar_noon`** („13:28") mit, damit eine Automation sie lesen kann statt sie zu raten. |
| `eedc_verbrauchsprognose_heute_kwh` | Verbrauchsprognose heute | kWh | `sensor` · `measurement` | Σ des individuellen Stunden-Verbrauchsprofils für heute (Werktag/Wochenende aus der eigenen Historie, Wärmepumpen-Anteil temperaturkorrigiert) — Gesamtverbrauch, dieselbe Zahl wie die Kachel in Cockpit → Live. Ohne eigenes Profil gibt es den Sensor nicht. | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | **Verbrauchsprognose für heute** — dieselbe Zahl wie die Kachel „Verbrauchsprognose" unter *Heute* in *Cockpit → Live*: die Summe des stündlichen Verbrauchsprofils (Werktag oder Wochenende aus der eigenen Historie, Wärmepumpen-Anteil mit dem Tagesmittel der Außentemperatur korrigiert — gemessenes Warmwasser und Kühlen bleiben dabei unverändert). Es ist der **Gesamt**verbrauch (Haus + Batterie + Wärmepumpe + Wallbox + Sonstige), keine Haushalts-Prognose. Attribute `profil_typ`, `profil_tage`, `profil_slots` nennen die Grundlage; **`stundenprofil_kwh`** trägt seit diesem Release die 24 Stundenwerte, aus denen die Summe entsteht, und **`wp_stundenprofil_kwh`** den darin enthaltenen Wärmepumpen-Anteil. ⚠ Der WP-Anteil ist eine **Teilmenge**, kein Summand daneben — wer beide addiert, zählt ihn doppelt. ⚠ **Nur aus einem eigenen Profil:** Solange eedc noch keine Historie hat und die Anzeige das Standard-Lastprofil zeigt, entsteht **kein** Sensor — ein Modellwert darf in keine Automation laufen. |
| `eedc_verbrauchsprognose_morgen_kwh` | Verbrauchsprognose morgen | kWh | `sensor` · `measurement` | Σ des individuellen Stunden-Verbrauchsprofils für morgen: Profil des Wochentags von morgen (Werktag/Wochenende aus der eigenen Historie), Wärmepumpen-Anteil mit der Temperaturvorhersage von morgen (Tagesmittel) korrigiert — Gesamtverbrauch, dieselbe Rechnung wie eedc_verbrauchsprognose_heute_kwh. Ohne eigenes Profil für den Tagestyp von morgen gibt es den Sensor nicht. | [§ Anlage-weite Sensoren](#anlage-weite-sensoren) | **Verbrauchsprognose für morgen** — dieselbe Rechnung wie `eedc_verbrauchsprognose_heute_kwh`, nur für den nächsten Tag: das Profil des **Wochentags von morgen** (am Freitag also das Wochenend-Profil für Samstag) und der Wärmepumpen-Anteil mit dem Tagesmittel der **Temperaturvorhersage von morgen** korrigiert. Gedacht für die Planung über die Nacht — etwa den Speicher zur günstigsten Stunde so zu laden, dass er bis zum nächsten Morgen reicht. Attribute `profil_typ`, `profil_tage`, `profil_slots`, `stundenprofil_kwh` (die Stundenwerte von morgen; so viele, wie die Wettervorhersage für morgen liefert), `wp_stundenprofil_kwh` (der Wärmepumpen-Anteil darin, eine **Teilmenge**) und **`datum`** — der Tag, für den der Wert gilt; nach Mitternacht erkennt eine Automation daran einen noch nicht erneuerten Wert. ⚠ **Nur aus einem eigenen Profil für den Tagestyp von morgen** — gibt es zum Beispiel noch kein Wochenend-Profil, fehlt der Sensor am Freitagabend. ⭐ **Startet nach dem Update abgewählt** (neu mit diesem Release): unter [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export) anhaken, er trägt dort die Markierung „Neu". · **Verbrauchsprognose für morgen** — die Rechnung von `eedc_verbrauchsprognose_heute_kwh` (Live-Kachel, 7-Tage-Profil) für den nächsten Tag: Profil des Wochentags von morgen, Wärmepumpen-Anteil mit dem Tagesmittel der Temperaturvorhersage von morgen korrigiert. Attribute `stundenprofil_kwh`, `wp_stundenprofil_kwh`, `profil_typ`/`profil_tage`/`profil_slots` und `datum`; ein anderes Modell als die Simulation hinter `eedc_speicher_voll_um`. Startet nach dem Update abgewählt — unter *Einstellungen → Integration → MQTT-Export* anhaken. |
| `eedc_speicher_voll_um` | Speicher voll um | — | `sensor` | SoC-Simulation ab aktuellem Speicherstand: Uhrzeit, zu der der Speicher voll ist. PV = eedc-Prognose-Slots ab dem Start × Nachführ-Faktor aus dem gemessenen Vormittag (wie Rest heute). Verbrauchsannahme = gewichtetes 8-Wochen-Profil (Attribute profil_typ, profil_stufe, profil_tage, verbrauch_annahme_kwh) — ein anderes Modell als eedc_verbrauchsprognose_heute_kwh. | [§ PV-Prognose-Sensoren (eedc_prognose_*)](#pv-prognose-sensoren-eedc_prognose_) | Uhrzeit, zu der der Speicher voraussichtlich voll ist (Simulation ab **aktuellem** Ladestand, **mit** dem gepflegten Wirkungsgrad — bei mehreren Speichern dem niedrigsten). Die PV-Stunden ab dem Start folgen wie „Rest heute" dem gemessenen Vormittag (× `nachfuehr_faktor` von `eedc_prognose_rest_today_kwh`). Rechnet mit dem gewichteten **8-Wochen-Verbrauchsprofil** — nicht mit dem 7-Tage-Profil von `eedc_verbrauchsprognose_heute_kwh`; die Attribute `profil_typ` (`gewichtet_8_wochen`), `profil_wochen`, `profil_halbwertszeit_tage`, `profil_stufe`, `profil_tage` und `verbrauch_annahme_kwh` nennen die Annahme (Details in [§8a](#8a-eedc-pv-prognose-nach-ha-exportieren-mqtt--ha-sensoren)). Ohne brauchbare Historie: `profil_typ: kein_profil`, `verbrauch_annahme_kwh: 0`. ⭐ **Startannahme (V1, 22.09.2026):** Die Simulation beginnt bei der zuletzt von HA verdichteten Stunde — und rechnet von ihr nur die **halbe** Stunde, weil der Startwert ein Stunden**mittel** ist und damit die Mitte dieser Stunde beschreibt. Die Attribute `sim_start_stunde` und `sim_start_anteil` (0,5 bzw. 1,0) nennen sie. Bis 4.0.50 startete sie bei der laufenden Uhrzeit und rechnete diese Stunde ganz; der gemeldete Zeitpunkt kann sich dadurch um bis zu eine halbe Stunde verschieben. Das Textformat „HH:MM“ bleibt unverändert. · Uhrzeit „Speicher voll" aus der SoC-Simulation ab aktuellem Speicherstand — **inkl. Ladeverluste**: gerechnet mit dem gepflegten Wirkungsgrad des Speichers. Vorher lief die Rechnung verlustfrei und meldete deshalb zu früh. Die **Verbrauchsannahme** der Simulation ist das gewichtete 8-Wochen-Profil (jüngere Tage zählen stärker, Halbwertszeit 14 Tage; Kaskade gleicher Wochentag → Werktag/Wochenende → alle Tage). Attribute `profil_typ` (`gewichtet_8_wochen`), `profil_wochen`, `profil_halbwertszeit_tage`, `profil_stufe` (welche Kaskadenstufe griff), `profil_tage` und `verbrauch_annahme_kwh` (der Tagesverbrauch, mit dem gerechnet wurde) nennen sie. ⚠ **Ein anderes Modell als `eedc_verbrauchsprognose_heute_kwh`** (7-Tage-Profil der Live-Kachel) — wer beide in einer Automation verrechnet, sieht das an `profil_typ`. Ohne brauchbare Historie rechnet die Simulation **ohne Verbrauch** (`profil_typ: kein_profil`, `verbrauch_annahme_kwh: 0`). |

> **Vormittag/Nachmittag:** die vier Sensoren `eedc_prognose_heute_vormittag_kwh`, `…_heute_nachmittag_kwh`, `…_morgen_vormittag_kwh` und `…_morgen_nachmittag_kwh` teilen den Tag am **Solar Noon**; die Grenze steht im Attribut `solar_noon`. Wer eine andere Grenze braucht, leitet sie per HA-Template aus dem Attribut `stundenprofil_kwh` ab — es hängt an `eedc_prognose_heute_kwh` und an den Tagesprognosen morgen bis in 3 Tagen; Eintrag *N* ist die Energie der Stunde, die um *N* Uhr endet (z. B. `{{ state_attr('sensor.…_day_plus_1_kwh', 'stundenprofil_kwh')[:13] | sum }}` für die Stunden bis 12 Uhr).

### Börsenpreis-Trigger (`eedc_preis_*`)

Grundlage ist der **Day-Ahead-Börsenpreis** (nicht der Anbieter-Endpreis — der variiert je Vertrag/Region, die Kurvenform ist dieselbe). Tag- und Nacht-Fenster werden **solar-basiert getrennt** bewertet (Sonnenauf-/-untergang, wandert saisonal).

**Welcher Tag gemeint ist:** der Kalendertag der **Strommarkt-Zeitzone** (CET/CEST für DE und AT) — Stunde 0 ist die Stunde nach Mitternacht deiner Uhr, unabhängig davon, in welcher Zeitzone der eedc-Container läuft. Bis v4.0 wurde stattdessen ein UTC-Tag abgefragt: Die Stunden 0 und 1 trugen dadurch die Preise des **Folgetages** (in der Winterzeit die Stunde 0), und in einem Container ohne gesetzte Zeitzone lagen alle Stunden um denselben Betrag daneben. An den beiden Umstellungstagen hat das Rang-Profil folgerichtig 23 bzw. 24 Einträge — im Oktober zählt die erste der beiden Zwei-Uhr-Stunden.

**Wann der Wert wechselt:** mit dem MQTT-Versand, und der läuft **an der Uhr** — bei der Voreinstellung (alle 60 Minuten) also zur vollen Stunde, bei kürzeren Abständen im passenden Raster (`:00`, `:15`, `:30`, `:45`). Bis dahin lief der Versand ab dem Startzeitpunkt des Add-ons durch; der neue Preis kam damit um einen Versatz zu spät an, den allein der letzte Neustart bestimmte (gemeldet: `09:12:56` und, nach einem Update, `11:08:02`). Ein Intervall, das nicht auf die Uhr passt (z. B. 90 Minuten), behält seinen freien Takt — dort würde jede Ausrichtung den eingestellten Abstand verändern.

**Günstig-Definition:** Eine Stunde gilt als günstig, wenn ihr Preis unter der **Günstig-Schwelle** liegt — standardmäßig 10 % unter dem Tagesdurchschnitt ohne die 3 teuersten Stunden („optimierter Ø"). Der Prozentsatz ist je Anlage einstellbar ([MQTT-Export-Seite](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export)). Ohne die Schwelle wären die „günstigsten" Stunden rein relativ — erzwungener Verbrauch oder Netzladung in einer kaum billigeren Stunde ergibt keinen Sinn.

**Rang und „günstig" sind zwei verschiedene Aussagen** (ab v4.0.10). Der **Rang** beantwortet „gehört diese Stunde zu den fünf billigsten ihres Fensters?" und ist deshalb bei 5 gedeckelt. **Günstig** beantwortet „liegt sie unter der Schwelle?" und ist es nicht: liegen sieben Nachtstunden unter der Schwelle, meldet der Zähler auch sieben. Bis v4.0.9 zählte er nur die Ränge und war damit ebenfalls bei 5 gedeckelt — als Anzeige stimmig, als **Divisor** in einer Automation zu klein.

**Was 0 % bedeutet:** Der Prozentsatz gibt an, wie weit *unter* dem optimierten Ø eine Stunde liegen muss. Bei **0 %** liegt die Schwelle damit **genau auf dem Ø** — günstig ist dann alles, was unter dem Tagesdurchschnitt (ohne die 3 Peaks) liegt. Die Schwelle ist also nicht abgeschaltet, sie ist nur nicht zusätzlich abgesenkt. (Bis v4.0 stand hier „0 % deaktiviert die Schwelle, dann zählen wieder die 5 günstigsten". Das hat der Code nie getan; der Top-5-Deckel hat den Unterschied verdeckt.)

| Schlüssel | Name | Einheit | Klassen | Formel | Regel | Hinweise |
|---|---|---|---|---|---|---|
| `eedc_preis_rang` | Börsenpreis-Rang | — | `sensor` · `measurement` | Rang der aktuellen Stunde je Tag-/Nacht-Fenster (1=billigste … 5, 99=teuer/Rest); günstig nur unter der Günstig-Schwelle (Standard 10 % unter Ø ohne 3 Peaks, je Anlage einstellbar) | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | Rang der **aktuellen** Stunde: 1–5 = eine der fünf billigsten ihres Fensters **und** unter der Schwelle, 99 = teuer/Rest. Attribute: `rang_profil` (alle 24 Stunden, s. u.), `guenstig_schwelle_cent` und `optimierter_durchschnitt_cent` (beide ct/kWh), `datum` (Kalendertag des Profils) sowie der **Morgen-Satz** `morgen_verfuegbar` · `datum_morgen` · `rang_profil_morgen` · `guenstig_schwelle_cent_morgen` · `optimierter_durchschnitt_cent_morgen` (s. u.). |
| `eedc_preis_guenstige_stunden_anzahl` | Günstige Stunden | — | `sensor` · `measurement` | Anzahl Stunden heute unter der Günstig-Schwelle (je Anlage einstellbar) — ungekappt | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | Anzahl Stunden heute unter der Schwelle (Tag + Nacht) — **ungedeckelt** |
| `eedc_preis_guenstige_stunden_tag` | Günstige Stunden Tag | — | `sensor` · `measurement` | Stunden unter der Günstig-Schwelle im Tag-Fenster (Sonnenauf→-untergang) | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | dieselbe Zahl je Fenster |
| `eedc_preis_guenstige_stunden_nacht` | Günstige Stunden Nacht | — | `sensor` · `measurement` | Stunden unter der Günstig-Schwelle im Nacht-Fenster | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | dieselbe Zahl je Fenster |
| `eedc_preis_aktuell_cent` | Börsenpreis aktuell | ct/kWh | `sensor` · `measurement` | Day-Ahead-Börsenpreis der laufenden Stunde | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | — |
| `eedc_preis_tages_durchschnitt_cent` | Börsenpreis Ø heute | ct/kWh | `sensor` · `measurement` | Ø ALLER heutigen Börsenpreis-Stunden — ohne jeden Ausschluss; NICHT die Bezugsgröße der Günstig-Schwelle | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | Ø **aller** heutigen Preis-Stunden, ohne jeden Ausschluss — was der Strom heute im Mittel kostet. **Nicht** die Bezugsgröße der Günstig-Schwelle |
| `eedc_preis_optimierter_durchschnitt_cent` | Börsenpreis Ø ohne Peaks | ct/kWh | `sensor` · `measurement` | Ø der heutigen Börsenpreise ohne die 3 teuersten Stunden — die Bezugsgröße der Günstig-Schwelle | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | Ø der heutigen Preise **ohne** die 3 teuersten Stunden — die Bezugsgröße der Schwelle |
| `eedc_preis_abstand_prozent` | Börsenpreis-Abstand zum Ø | % | `sensor` · `measurement` | (Preis der laufenden Stunde − Ø ohne Peaks) ÷ \|Ø\| × 100 — negativ = billiger als der Ø | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | Abstand des aktuellen Preises zu diesem Ø. **Negativ = billiger als der Ø**, positiv = teurer. Bezugsgröße ist der Betrag des Ø, damit das Vorzeichen auch bei negativen Börsenpreisen stimmt. |
| `eedc_preis_abstand_cent` | Börsenpreis-Abstand zum Ø (ct) | ct/kWh | `sensor` · `measurement` | Preis der laufenden Stunde − Ø ohne Peaks — negativ = billiger; gegen feste Preisbestandteile unempfindlich | [§ Börsenpreis-Trigger (eedc_preis_*)](#börsenpreis-trigger-eedc_preis_) | **Derselbe Abstand in ct/kWh** — die Größe, die sich auf den eigenen Endpreis übertragen lässt (s. u.). Negativ = billiger. |

> ⚠ **Zwei Durchschnitte, zwei Fragen — nicht verwechseln.** `eedc_preis_tages_durchschnitt_cent`
> sagt, was der Strom heute im Mittel kostet; `eedc_preis_optimierter_durchschnitt_cent` sagt,
> ab wann sich das Laden lohnt. Die Günstig-Schwelle und **beide** Abstands-Größen beziehen
> sich auf den **zweiten**, nie auf den ersten. Wer in einer Automation den Tagesschnitt
> meint, nimmt den ersten (rapahl-PN 2026-08-23).
>
> **Die vier letzten sind für eigene Preis-Regeln da** (v4.0.10, Wunsch aus der Tester-Runde): „nur entladen, wenn der Strom gerade teurer ist als der Tagesschnitt" ist damit eine Bedingung auf `eedc_preis_abstand_prozent > 0` — ohne Template und ohne dass eedc eine Lade-/Entlade-Strategie vorgibt.

> ### Prozent oder Cent? Beide, und sie sagen Verschiedenes
>
> Der **Prozentwert** misst gegen den Ø **dieses Tages**: −50 % heißt „halb so teuer wie der Tagesschnitt". Er ist über Tage hinweg vergleichbar, aber **nicht** auf deinen Endpreis übertragbar.
>
> Der **ct-Wert** ist es. Denn du zahlst nicht den Börsenpreis, sondern Börsenpreis **plus** feste Bestandteile (Netzentgelt, Abgaben, Marge). Dieser Aufschlag verschiebt Stundenpreis **und** Tagesmittel um denselben Betrag — die Differenz bleibt gleich, der Prozentwert nicht. An einem echten Tag (Ø 9,92 ct): die billigste Stunde liegt **−9,93 ct** unter dem Mittel, auf der Börsenkurve wie auf dem Endpreis; in Prozent sind das **−100,1 %** bzw. **−33,2 %**. Eine Prozentzahl, die für beide Welten dasselbe bedeutet, kann es folglich nicht geben.
>
> ⚠ **Was −100 % NICHT heißt:** nicht „billigste Stunde des Tages", sondern **„Preis = 0 ct"**. Der Wert kann unter −100 % fallen — jeder negative Börsenpreis tut das. Wer „ist das eine der besten Stunden?" fragt, nimmt `eedc_preis_rang` (1–5), nicht den Prozentwert.
>
> **Faustregel:** Schwellen für Automationen (`< -5` ct) und alles, was mit deinem Tarif zu tun hat → **ct**. Tagesübergreifende Vergleiche → **Prozent**. „Eine der günstigsten Stunden" → **Rang**.

**Das Rang-Profil als Attribut** trägt je Stunde fünf Angaben: `stunde`, `rang`, `preis_cent`, `unter_schwelle` und `abstand_cent`. `preis_cent`/`unter_schwelle` gibt es ab v4.0.10, `abstand_cent` seit dem ct-Sensor — vorher stand dort nur der Rang, und damit ließ sich in HA weder eine eigene Schwelle noch ein eigenes Zeitfenster auswerten.

> ### Morgen steht daneben, sobald es ihn gibt
>
> Die Day-Ahead-Auktion veröffentlicht die Preise des Folgetages gegen **13 Uhr**. Ab dann tragen
> die Attribute von `eedc_preis_rang` einen **zweiten Satz** für morgen — dieselbe Gestalt wie
> heute, damit eine Automation beide mit demselben Code liest:
>
> | Attribut | Bedeutung |
> |---|---|
> | `morgen_verfuegbar` | `true`/`false` — **immer vorhanden**. Vor der Auktion `false`; du musst also nicht auf ein fehlendes Attribut prüfen |
> | `datum_morgen` | Kalendertag, für den der Morgen-Satz gilt |
> | `rang_profil_morgen` | 24 Stunden in derselben Form wie `rang_profil` |
> | `guenstig_schwelle_cent_morgen` | die Günstig-Schwelle **des Folgetages** |
> | `optimierter_durchschnitt_cent_morgen` | dessen Bezugsgröße |
>
> ⚠ **Jeder Tag hat seine eigene Schwelle**, und das ist Absicht: Day-Ahead ist ein Tagesprodukt.
> Ein gemeinsamer Durchschnitt über 48 Stunden würde an einem teuren Tag *keine* günstige Stunde
> ausweisen und am billigen fast alle. Wer das Morgen-Profil auswertet, nimmt deshalb
> `guenstig_schwelle_cent_morgen` — nicht die von heute.
>
> **Warum `datum` und `datum_morgen` dabeistehen:** ein Profil ohne seinen Kalendertag ist nach
> Mitternacht nicht von einem stehengebliebenen zu unterscheiden. Eine Automation, die dann auf
> „morgen" plant, plant auf gestern.
>
> **Vor 13 Uhr fragt eedc gar nicht an.** Das ist keine Sparmaßnahme, sondern der Marktrhythmus:
> vor der Auktion gibt es die Zahlen nicht.

> **Eigene Kriterien:** Wer eine andere Schwelle bevorzugt, stellt den Prozentsatz auf der Export-Seite um — oder rechnet in HA per Template direkt auf den Attributen (`rang_profil` mit den Stundenpreisen, `optimierter_durchschnitt_cent`). eedc liefert bewusst nur die **Trigger-Werte**; die Lade-/Entlade-Strategie baut jeder selbst in seinen Automationen.

### Drei Vorlagen für den HA-Template-Editor

Der Absatz darüber sagt, dass sich mit `rang_profil` eigene Kriterien rechnen lassen — er sagte
bisher nicht, **wie**. Das hat gefehlt: Wer nur die Sensorliste durchsieht, findet neun
`eedc_preis_*`-Sensoren und darunter **keinen Höchstpreis** und **keine Rang-Preise**, und
schließt daraus, dass eedc sie nicht liefert. Sie sind da — als Attribut, nicht als Sensor.

Die drei Vorlagen lassen sich unverändert in *Entwicklerwerkzeuge → Vorlage* kopieren. Wer eine
davon als Sensor haben will, setzt sie in `configuration.yaml` unter `template: - sensor:` mit
`state: >`. **Sie nehmen eine Anlage namens „Haus" an:** Home Assistant bildet die Entity-ID aus dem
Gerätenamen `eedc - <Anlage>` und dem Anzeigenamen des Sensors („Börsenpreis-Rang", Umlaut ohne
Punkte), also `sensor.eedc_haus_borsenpreis_rang` — an einer Anlage „Winterborn" heißt er
`sensor.eedc_winterborn_borsenpreis_rang`. Setz deinen Anlagennamen ein; welche ID dein Sensor trägt,
zeigt *Einstellungen → Geräte & Dienste → MQTT*, Gerät „eedc - *dein Anlagenname*".

**1) Der Tageshöchstpreis**

```jinja
{%- set p = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil') or [] -%}
{{ (p | map(attribute='preis_cent') | max | round(2)) if p else 'unbekannt' }}
```

Für morgen dasselbe mit `rang_profil_morgen` — aber erst, wenn `morgen_verfuegbar` `true` ist.

**2) Die Ränge mit ihren Preisen**

```jinja
{%- set p = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil') or [] -%}
{%- for s in p | rejectattr('rang','eq',99) | sort(attribute='stunde') %}
{{ '%02d'|format(s.stunde) }}:00 Uhr | Rang {{ s.rang }} | {{ s.preis_cent | round(2) }} ct
{%- endfor -%}
```

> ⚠ **Es kommen bis zu ZEHN Zeilen, nicht fünf — und „Rang 1" kann zweimal vorkommen.**
> Tag- und Nachtfenster werden **getrennt** bewertet (Grenze: Sonnenauf-/-untergang), jedes
> vergibt seine eigenen Ränge 1–5. An einem Tag, an dem die PV-Mittagsdelle die Nachtstunden
> aus der Rangliste drängt, kommen dagegen nur fünf. **Wer auf `rang <= 5` filtert, filtert
> nicht die fünf billigsten Stunden des Tages** — dafür sortiert man nach `preis_cent`.

**3) Die beste Lade-/Entladespanne, über die Tagesgrenze hinweg**

```jinja
{%- set eta = 0.90 -%}
{%- set heute  = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil') or [] -%}
{%- set morgen = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil_morgen') or [] -%}
{%- set r = namespace(reihe=[]) -%}
{%- for s in heute if s.stunde >= now().hour -%}
  {%- set r.reihe = r.reihe + [{'t': s.stunde, 'p': s.preis_cent}] -%}
{%- endfor -%}
{%- for s in morgen -%}
  {%- set r.reihe = r.reihe + [{'t': s.stunde + 24, 'p': s.preis_cent}] -%}
{%- endfor -%}
{%- set b = namespace(spread=0, lade=none, ent=none) -%}
{%- for a in r.reihe -%}
  {%- for z in r.reihe if z.t > a.t -%}
    {%- if (z.p * eta - a.p) > b.spread -%}
      {%- set b.spread = z.p * eta - a.p -%}
      {%- set b.lade = a -%}{%- set b.ent = z -%}
    {%- endif -%}
  {%- endfor -%}
{%- endfor -%}
{%- if b.lade is none -%}
keine lohnende Spanne
{%- else -%}
Laden {{ '%02d'|format(b.lade.t % 24) }}:00{{ ' (morgen)' if b.lade.t >= 24 else '' }} zu {{ b.lade.p | round(2) }} ct | Entladen {{ '%02d'|format(b.ent.t % 24) }}:00{{ ' (morgen)' if b.ent.t >= 24 else '' }} zu {{ b.ent.p | round(2) }} ct | Spanne {{ b.spread | round(2) }} ct/kWh
{%- endif -%}
```

Sie gibt **eine** Zeile aus (rund 90 Zeichen) und ist damit ohne Nacharbeit als Template-Sensor
verwendbar. `eta` ist dein Speicher-Wirkungsgrad — trag deinen eigenen Wert ein.

> **Warum die Spanne *gerichtet* ist:** Entladen kann man nur, was vorher geladen wurde. Ein
> ungerichtetes Tages-Min/Max nennt bei „billig 13 Uhr, teuer 08 Uhr" eine Spanne, die es an
> diesem Tag nicht mehr gibt. Die Vorlage sucht deshalb nur Paare, bei denen die teure Stunde
> **nach** der billigen liegt — und über die Tagesgrenze hinweg, sobald das Morgen-Profil da ist.
>
> **`keine lohnende Spanne`** heißt: Es gibt im bekannten Horizont kein Paar, das nach Abzug der
> Speicherverluste noch etwas übrig lässt. Das ist eine Aussage, kein Fehler — spät am Abend ohne
> Morgen-Profil ist es der Normalfall.

> ⚠ **Der Tag hat nicht immer 24 Stunden.** Am Ende der Sommerzeit fehlt die zweite Zwei-Uhr-
> Stunde, im Frühjahr die Stunde 2 ganz; `rang_profil` hat dann 23 Einträge. Alle drei Vorlagen
> laufen darüber, weil keine auf eine feste Länge prüft — wer eigene baut, prüft es auch nicht.

### Drei Automationen, die auf diesen Sensoren aufsetzen

eedc nennt Fenster, Preise und Mengen — **schalten tust du.** Die drei Beispiele zeigen, wie
eine HA-Automation die Sensoren dieser Gruppe liest. Sie sind vollständig, aber jede enthält
**eine Zeile, die du ersetzen musst:** die Entität deines Geräts (Speicher, Wallbox, Heizstab). Wie
dein Speicher „nicht entladen" oder „aus dem Netz laden" heißt, weiß nur seine Integration —
eedc kennt kein Schaltelement und erfindet keins.

Die YAML-Blöcke sind so geschrieben, dass sie sich unter *Einstellungen → Automationen → Neue
Automation → ⋮ → In YAML bearbeiten* einfügen lassen. **Die Entity-IDs darin gelten für eine Anlage
namens „Haus"** — Home Assistant bildet die ID aus dem Gerätenamen `eedc - <Anlage>` und dem
**Anzeigenamen** des Sensors, nicht aus seinem Schlüssel: aus `eedc_bezugspreis_jetzt_cent` an der
Anlage „Winterborn" wird `sensor.eedc_winterborn_bezugspreis_jetzt`, aus dem Schalter „Speicher
voll" `binary_sensor.eedc_winterborn_speicher_voll`; Umlaute fallen weg (`borsenpreis_rang`,
`gunstige_stunde`). Welche ID dein Sensor trägt, zeigt *Einstellungen → Geräte & Dienste → MQTT*, Gerät „eedc - *dein Anlagenname*". Alle drei nutzen native Bedingungen
(`numeric_state`, `state`) statt Vorlagen, wo Home Assistant das kann; nur das dritte Beispiel
liest eine Stundenreihe und braucht dafür eine Vorlage.

> **Zwei Eigenschaften der Sensoren, auf die sich die Beispiele verlassen.** Erstens: ein
> `binary_sensor` wird bei fehlender Grundlage **nicht verfügbar** — eine Bedingung auf `on` ist
> dann von selbst falsch, die Automation schaltet nichts (s. oben). Zweitens: ein Sensor, den eedc
> nicht bilden kann, **fehlt** — `eedc_speicher_netzladen_kosten_cent` gibt es nur für Speicher mit
> „lädt aus dem Netz", `eedc_abregelung_heute_kwh` nur mit gepflegter Wechselrichter-Grenze.
> Fehlt der Sensor, läuft die Automation ins Leere, ohne Fehler. Prüfe vor dem Bau in
> *Einstellungen → Integration → MQTT-Export*, ob er bei dir entsteht.

**1) Speicher schonen, solange Netzstrom billiger ist als Speicherstrom**

Strom aus dem Speicher kostet die entgangene Einspeisevergütung geteilt durch den Wirkungsgrad
(`eedc_speicher_strom_kosten_cent`, bei der Demo-Anlage 9,8 ct). In einer Stunde, in der der
Bezugspreis darunter liegt — bei einem dynamischen Tarif nachts oder bei negativen Börsenpreisen —
ist es günstiger, den Speicher zu **halten** und den Haushalt aus dem Netz zu versorgen. Die
Automation vergleicht die beiden Sensoren bei jedem neuen Preis und stellt den Speicher auf
„nicht entladen", solange das gilt.

```yaml
alias: "eedc — Speicher schonen bei billigem Netz"
description: >
  Solange der Bezugspreis der laufenden Stunde unter den Kosten einer Speicher-Kilowattstunde
  liegt, wird der Speicher nicht entladen. Beide Zahlen kommen von eedc; die Schalt-Entität
  ist die des Speichers.
mode: single
triggers:
  - trigger: state
    entity_id: sensor.eedc_haus_bezugspreis_jetzt
    note: "eedc publiziert zur vollen Stunde einen neuen Preis — das ist der Takt."
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.eedc_haus_bezugspreis_jetzt
        below: sensor.eedc_haus_speicherstrom_kostet
        note: "Netz billiger als Speicher: halten."
    then:
      - action: select.select_option
        target:
          entity_id: select.speicher_betriebsmodus   # ← Entität deines Speichers
        data:
          option: "Entladung sperren"                # ← Wortlaut deiner Integration
    else:
      - action: select.select_option
        target:
          entity_id: select.speicher_betriebsmodus   # ← Entität deines Speichers
        data:
          option: "Automatik"                        # ← Wortlaut deiner Integration
```

Bei einem **Festpreis** greift der `then`-Zweig praktisch nie (30 ct gegen 9,8 ct) — die
Automation ist dann harmlos, aber nutzlos. Sie ist für dynamische Tarife gedacht; dort trägt
`eedc_bezugspreis_jetzt_cent` den Endpreis inklusive abgeleitetem Aufschlag, nicht den nackten
Börsenpreis (Attribut `preisquelle`).

**2) Aus dem Netz laden, wenn die Kilowattstunde unter deiner Grenze bleibt**

`eedc_speicher_netzladen_kosten_cent` ist der Bezugspreis geteilt durch den Wirkungsgrad — also
das, was eine später *entnommene* Netz-Kilowattstunde wirklich kostet. Die Grenze legst du in
einem Zahlen-Helfer fest (*Einstellungen → Geräte & Dienste → Helfer → Zahl*, hier
`input_number.netzladen_grenze_cent`); so änderst du sie, ohne die Automation anzufassen. Geladen
wird nur, wenn der Speicher nach heutiger Simulation **nicht** bis Mitternacht reicht — sonst
würdest du Netzstrom einlagern, den die PV am Tag ohnehin liefert.

```yaml
alias: "eedc — Netzladen unter Preisgrenze"
description: >
  Startet die Netzladung, wenn eine aus dem Speicher entnommene Netz-Kilowattstunde unter der
  eigenen Grenze kostet und der Speicher heute nicht bis Mitternacht reicht; beendet sie, sobald
  eine der Bedingungen fällt oder der Speicher voll ist.
mode: single
triggers:
  - trigger: state
    entity_id:
      - sensor.eedc_haus_netzladen_kostet
      - binary_sensor.eedc_haus_speicher_reicht_bis_mitternacht
      - binary_sensor.eedc_haus_speicher_voll
    note: "Jeder dieser drei Sensoren kann die Entscheidung kippen."
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.eedc_haus_netzladen_kostet
        below: input_number.netzladen_grenze_cent
      - condition: state
        entity_id: binary_sensor.eedc_haus_speicher_reicht_bis_mitternacht
        state: "off"
        note: "Bei »nicht verfügbar« (keine Simulation möglich) wird nicht geladen."
      - condition: state
        entity_id: binary_sensor.eedc_haus_speicher_voll
        state: "off"
    then:
      - action: switch.turn_on
        target:
          entity_id: switch.speicher_netzladen      # ← Entität deines Speichers
    else:
      - action: switch.turn_off
        target:
          entity_id: switch.speicher_netzladen      # ← Entität deines Speichers
```

Wer stattdessen der **Menge** folgen will, nimmt `eedc_arbitrage_vorschlag_kwh` (empfohlene
Netzladung heute, mit `stunden` als Liste der günstigen Stunden) — er entsteht nur, wenn sich
Laden und späteres Entladen nach Abzug der Verluste lohnt.

**3) Einen Verbraucher in die Abregelung legen**

Was der Wechselrichter an seiner Grenze abregelt, entsteht gar nicht erst. Ein Heizstab, eine
Poolpumpe oder ein Warmwasserboiler läuft in diesen Stunden also mit Strom, der sonst verloren
wäre — billiger als jedes Überschuss-Fenster. `eedc_abregelung_heute_kwh` trägt in
`stundenprofil_kwh` je Stunde die erwartete Kappung (24 Werte, Index 0 = 23–00 Uhr des Vortags,
Index 15 = 14–15 Uhr) und in `rest_heute_kwh`, was heute noch bevorsteht. Eine Stundenreihe
lässt sich nicht nativ lesen — hier ist die Vorlage die richtige Form.

```yaml
alias: "eedc — Heizstab in die Abregelung"
description: >
  Schaltet den Heizstab ein, solange eedc für die laufende Stunde eine Abregelung an der
  Wechselrichter-Grenze erwartet, und danach wieder aus. Die Reihe ist eine Prognose auf der
  Rohvorhersage (Attribut skala) — Größenordnung und Uhrzeiten, keine Messung.
mode: single
triggers:
  - trigger: state
    entity_id: sensor.eedc_haus_abregelung_heute
    note: "Feuert bei jedem Publish, auch wenn sich nur die Attribute ändern."
  - trigger: time_pattern
    minutes: 1
    note: "Zusätzlich zur vollen Stunde, falls der Publish später kommt."
variables:
  kappung_jetzt_kwh: >-
    {% set p = state_attr('sensor.eedc_haus_abregelung_heute', 'stundenprofil_kwh') or [] %}
    {% set i = now().hour + 1 %}
    {{ (p[i] | float(0)) if p | length > i else 0 }}
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.eedc_haus_abregelung_heute
        attribute: rest_heute_kwh
        above: 0.5
        note: "Heute steht überhaupt noch eine nennenswerte Kappung bevor."
      - "{{ kappung_jetzt_kwh > 0.2 }}"
    then:
      - action: switch.turn_on
        target:
          entity_id: switch.heizstab                # ← dein Verbraucher
    else:
      - action: switch.turn_off
        target:
          entity_id: switch.heizstab                # ← dein Verbraucher
```

`now().hour + 1` ist der Index der **laufenden** Stunde: die Reihe ist rückwärts beschriftet
(Index 15 = 14:00–15:00), also liegt 14:37 Uhr in Index 15. Um 23 Uhr gibt es keinen Eintrag
(er wäre Index 24 — die Stunde gehört schon zur Reihe von morgen), die Vorlage liefert dann 0;
für einen PV-Verbraucher ist das kein Verlust. Die Schwellen (0,5 kWh Rest, 0,2 kWh in der Stunde)
sind Beispiele — bei einem 3-kW-Heizstab lohnt eine Stunde mit 0,2 kWh Kappung kaum, bei einer
Poolpumpe mit 0,5 kW schon.

> ⚠ **Was keins der drei Beispiele tut:** einen Live-Wert lesen. `eedc_ueberschuss_jetzt_kw` ist ein
> Stundenmittel und bis zu 15 Minuten alt; wer eine Wallbox nach dem *aktuellen* Überschuss regeln
> will, braucht dafür die Leistungssensoren seines Zählers, nicht eedc. eedc liefert die Planung
> für heute — Fenster, Reihen, Preise —, und die drei Beispiele bleiben in genau diesem Rahmen.

---

## Allgemeine Regeln für Sensoren

### Tagessensoren (Utility Meter)

HA Utility Meter setzen den Zählerstand täglich um 0:00 auf 0 zurück. **Über HA ist das folgenlos:** eedc liest den
reset-bereinigten `sum`-Wert der Langzeitstatistik, ein Tagessensor taugt dort wie ein fortlaufender Zähler.

**Über MQTT Energy Topics nicht als Zählerquelle:** eedc bildet Tag und Monat aus der Differenz zweier Stände; einen
Rücksprung dazwischen erkennt es und liefert dann **keinen Wert** statt einer hochgerechneten Menge (#341, Legende
„Tagessensor"). Für MQTT deshalb den **fortlaufenden Stand** senden (`utility_meter` mit Zurücksetzen „nie").
Ein Feld mit Sensortyp „Tagessensor" (Tageswert-Feld, z. B. Speicher „Ladung heute") erwartet dagegen genau den Tageswert.

### Vorzeichen-Konvention

| Kategorie | Positiv | Negativ |
|-----------|---------|---------|
| PV-Leistung | Erzeugung | — (immer positiv) |
| Einspeisung | Ins Netz | — (immer positiv) |
| Netzbezug | Aus dem Netz | — (immer positiv) |
| Netz-Kombi | Netzbezug | Einspeisung |
| Batterie-Leistung | Ladung (Senke) | Entladung (Quelle) |
| E-Auto V2H | Ladung | Entladung ins Haus |

⚠️ Manche Wechselrichter liefern das Vorzeichen umgekehrt. In der [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) gibt es dafür am signierten Leistungs-Feld das **±**-Symbol (Vorzeichen umkehren, `live_invert`) — quellen-unabhängig direkt am Wert.

### Einheiten-Konvertierung

Live-Leistungssensoren werden automatisch konvertiert: `kW → W`, `MW → W`. Für kWh-Sensoren wird `Wh → kWh` und `MWh → kWh` automatisch skaliert. Counter-Felder (siehe §9) bleiben mit Faktor 1.0 — kein automatisches Wh→kWh, da physikalisch keine Energie.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
