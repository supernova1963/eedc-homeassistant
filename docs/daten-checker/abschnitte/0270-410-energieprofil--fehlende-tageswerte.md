<!-- anker: 410-energieprofil--fehlende-tageswerte -->
### 4.10 Energieprofil – fehlende Tageswerte <a name="410-energieprofil--fehlende-tageswerte"></a>

> **Variantenhinweis:** Nur im **HA Add-on** (bzw. Docker mit HA-Recorder-Zugriff). Im Standalone-Betrieb fehlt die unabhängige Referenz, gegen die eedc prüfen könnte — die Kategorie wird dann still übersprungen.

**Was wird geprüft:** Gibt es in den letzten 90 Tagen Tage, an denen ein Zähler zugeordnet ist und die **HA-Langzeitstatistik einen Wert liefert**, die gespeicherte Tageszeile aber leer oder 0 ist? Das ist der typische Fall nach einer nachträglich korrigierten Zuordnung: die Zuordnung steht heute, aber für die Tage davor hat nie ein Aggregator-Lauf stattgefunden. Die Zähler-Abdeckung (§4.6) meldet dort völlig zu Recht „OK" — der Zähler *ist* ja zugeordnet.

**Nur Zeiträume, in denen die Komponente auch gelaufen ist.** Die Prüfung fordert für jeden Tag genau das ein, was der Reparatur-Lauf an diesem Tag auch schreiben darf: Komponenten, die an dem Tag noch nicht angeschafft, bereits stillgelegt oder auf *inaktiv* gesetzt waren, tauchen für diesen Zeitraum nicht auf. Die Anlagen-Grenze wirkt genauso: vor dem Inbetriebnahme-Datum wird nichts eingefordert.

**Kein Knopf ohne Deckung.** Braucht der Tages-Lauf für diese Anlage etwas, das nicht da ist — eine Leistungs-Zuordnung (W) bzw. MQTT-Energie —, dann erscheint der Befund weiterhin, aber **ohne** Reparatur-Knopf; er springt stattdessen mit «Sensor zuordnen» auf das Feld, das zuerst zuzuordnen ist, und Einzeltag-Zeilen entfallen.

**Tage aus dem HA-Spiegel** bzw. den eigenen Zählerständen vergleicht die Prüfung mit den Mengen, die die Tagesansicht im Cockpit dort zeigt (PV, Netz und Speicher aus dem Spiegel) — eine leere gespeicherte Tageszeile ist an einem solchen Tag kein Befund; Wärmepumpe, Wallbox und Sonstiges ohne Kanal prüft sie wie bisher.

**Reichweite:** Die Tagesreparatur heilt Tages- und Stundenwerte, **nicht** die Monatswerte. Für abgeschlossene Monate danach *Einstellungen → Integration → Statistik-Import*.

> **Abgrenzung:** PV-Werte auf einer *bestehenden* Tageszeile gehören der Drift-Prüfung (§4.17) — kein zweiter Turm über denselben Sachverhalt. Der Speicher-Netto-Wert (`batterie_*`) bleibt hier außen vor, er darf legitim ~0 sein.

---
