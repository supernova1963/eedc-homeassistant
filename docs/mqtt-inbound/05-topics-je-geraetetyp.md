### Topics je Gerätetyp

Je Gerätetyp eine Tabelle der Energie-Topics (`energy/`, Zählerstände) und eine der Live-Topics (`live/`), erzeugt aus
der Erwartungsliste von eedc (`services/mqtt_topic_registry.py` — dieselbe Liste, die der Block **MQTT-Topics** am Ende
der Datenquellen-Fläche zum Kopieren zeigt) und der Feld-Registry. Jedes Feld steht genau einmal, auch eines ohne Topic.
`{anlage_id}` und `{inv_id}` sind die Datenbank-IDs, `{name}` dient nur der Lesbarkeit (siehe [Beispiel](#beispiel)).

- **Payload** sagt, was eedc auf dem Topic erwartet und was es daraus macht. Bei einem Zustand steht das Wort, das eedc
  intern führt, vorn; in Klammern die übrigen Werte, die eedc als dasselbe versteht (Herstellerwörter und Zahlencodes —
  die Codes gelten nur über MQTT).
- **Bedingung** nennt den Geräte-Parameter, an dem das Feld hängt; „(weich)" heißt: an dieser Bauart untypisch, aber
  möglich. Ein Live-Feld, dessen Bedingung am Gerät nicht gilt, erwartet eedc dort nicht (außer bei „weich");
  Energie-Topics erwartet es unabhängig von der Bedingung.
- „wird angenommen, aber von keiner Sicht gelesen": eedc nimmt den Wert entgegen, aber heute verarbeitet ihn kein
  Teil von eedc (keine Zählerreihe, keine Kachel). Soll er zählen, trag ihn im Monatsabschluss ein.
- Was ein Feld bedeutet, sagt die Spalte „Hinweis" der [Sensor-Referenz](SENSOR-REFERENZ.md) — dieselbe Registry.

#### Anlage (Basis)

Energie-Topics:

<!-- erzeugt: mqtt-topics ebene=basis liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics ebene=basis liste=live -->

Den Strompreis nimmt eedc als `live/strompreis_ct` (ct/kWh) entgegen und zeigt ihn nur im Tagesverlauf (siehe
[Live-Mittelwerte](#live-mittelwerte-was-eedc-aus-den-live-topics-mitschreibt)); die Erwartungsliste nennt dieses Topic nicht.

#### PV-Module

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=pv-module liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=pv-module liste=live -->

#### Balkonkraftwerk

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=balkonkraftwerk liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=balkonkraftwerk liste=live -->

#### Speicher

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=speicher liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=speicher liste=live -->

#### Wärmepumpe

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=waermepumpe liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=waermepumpe liste=live -->

Felder mit „je Innengerät" erwartet eedc an einer Klimaanlage mit Innengeräten zusätzlich einmal je Innengerät; die
konkreten Topics mit der Nummer des Innengeräts zeigt der Block **MQTT-Topics** am Ende der Datenquellen-Fläche.

#### E-Auto

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=e-auto liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=e-auto liste=live -->

Heimladung am Auto: entweder `ladung_pv_kwh` und `ladung_netz_kwh` oder `ladung_kwh` (gesamt, für einen Zähler, der PV
und Netz nicht trennt — dann die beiden anderen leer lassen). Neben einer Wallbox zählt der Wert für dieses Auto, die
Wallbox trägt den Rest.

#### Wallbox

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=wallbox liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=wallbox liste=live -->

#### Sonstiges

Die Spalte „Art" ist die Kategorie des Geräts. Ohne gepflegte Kategorie erwartet eedc die Felder von Verbraucher,
Erzeuger und Speicher.

Energie-Topics:

<!-- erzeugt: mqtt-topics typ=sonstiges liste=energy -->

Live-Topics:

<!-- erzeugt: mqtt-topics typ=sonstiges liste=live -->

#### Wechselrichter

Wechselrichter haben keine eigenen Topics: ihre Werte gehören zu den PV-Modulen und Speichern, denen sie zugeordnet sind
(`SKIP_TYPEN` in `services/mqtt_topic_registry.py`).

