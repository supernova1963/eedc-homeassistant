### Live-Mittelwerte: was eedc aus den Live-Topics mitschreibt

Jedes Live-Topic mit einer Zahl ist ein Momentanwert — senden bei jeder Aenderung genuegt (ein Wert gilt bis zur
naechsten Nachricht, wie in Home Assistant). Alle 5 Minuten haelt eedc daraus das **zeitgewichtete Mittel** des
Fensters fest (mit Minimum und Maximum) und bildet je abgeschlossener Stunde **Stundenmittel** — dasselbe, was Home
Assistant aus seinen 5-Minuten-Statistiken macht (seit Standalone-Gleichstand S2). Mitgeschrieben werden die
Live-Topics, deren Spalte „Payload" unter [Topics je Gerätetyp](#topics-je-gerätetyp) „5-Minuten- und Stundenmittel"
nennt (Leistung, Ladestand, Temperatur); den Betriebsmodus schreibt eedc als Anteil je Modus mit (siehe naechster
Abschnitt).

Daraus entstehen ohne Home Assistant u. a. das Temperatur-Diagramm, Ø Vorlauf und Ø Spreizung der Waermepumpe. Der
**Tagesverlauf** in *Cockpit → Live* zeigt ueber MQTT damit 5-Minuten-Mittel statt einzelner Momentanwerte, ab der
ersten Aufzeichnung — ohne Home Assistant auch ohne jede Zuordnung unter *Datenquellen* (reine Inbound-Anlage).

**Add-on mit MQTT-Geraeten (Mischform).** Laeuft eedc mit Home Assistant, liefern aber einzelne oder alle Geraete ihre
Leistung nur ueber diese Topics (kein HA-Sensor zugeordnet), zeichnet der Tagesverlauf auch sie aus den 5-Minuten-
Aufzeichnungen: ohne jede `live`-Zuordnung die ganze Kurve aus MQTT, sonst die Geraete ohne HA-Leistungssensor aus MQTT
neben den Geraeten aus HA — Netz, PV gesamt und Preis bleiben dann bei HA. Ein Geraet mit HA-Sensor bleibt bei HA. Die
Tagesaggregation liest dieselbe Kurve (Geraetewerte je Stunde). Voraussetzung: „Daten ueber MQTT empfangen (Import)" an.

- **Nicht rueckwirkend:** Die Stundenmittel beginnen mit der Zuordnung (dem ersten empfangenen Wert).
- **Broker-Ausfall:** Die Zeit ohne Verbindung bleibt eine Luecke; die Stunde ist das Mittel der uebrigen Minuten.
  Ein Absender, der verstummt, waehrend der Broker laeuft, behaelt seinen letzten Wert.
- **HA-Sensor geht vor:** Ist einem Feld ein HA-Sensor zugeordnet, gilt er — auch ohne Langzeitstatistik (der
  Daten-Checker nennt ihn dann); das MQTT-Topic wird fuer die Stundenmittel nicht gelesen.
- **Strompreis:** `strompreis_ct` zeigt eedc nur im Tagesverlauf; Stundenpreise und Kosten entstehen nur aus einem
  HA-Preissensor.

