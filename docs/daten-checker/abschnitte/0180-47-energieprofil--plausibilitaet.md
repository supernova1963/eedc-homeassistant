<!-- anker: 47-energieprofil--plausibilitaet -->
### 4.7 Energieprofil – Plausibilität <a name="47-energieprofil--plausibilitaet"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten gleich — sie liest nur die bereits gespeicherten
> Stundenwerte des Energieprofils.

**Was wird geprüft:** Enthalten die Tagesprofile der letzten 30 Tage Stundenwerte, die physikalisch unmöglich sind?
Konkret: PV oder Einspeisung einer Stunde größer als die Anlagenleistung × 1,5. Das tritt typisch nach einem Neustart
während des Tages auf, wenn ein verzerrter Zählerstand gespeichert wurde. Dazu kommen zwei Tagesprüfungen: Tage mit mehr
Einspeisung als Erzeugung plus Speicher-Entladung (Toleranz 0,5 kWh) und Tage mit einem Nachtrag nach eingefrorenem
Zähler.

**Schwelle:** Anlagen-kWp × 1,5. Eine Aufdach-PV-Anlage erzeugt selbst bei optimalem Sonnenstand nicht mehr als etwa
1500 W je kWp — Werte darüber sind Rechen- oder Messfehler, keine Naturereignisse.

**Die Schwelle wächst mit der Zeit, in der sich der Zählerstand nicht geändert hat:** Trägt eine Stunde die Energie einer
Lücke in Home Assistant (in der Stundentabelle beschriftet „enthält n Stunden“) oder den Nachtrag nach Stunden mit
unverändertem Stand, gilt kWp × 1,5 × Stunden seit der letzten Änderung (höchstens 24 Stunden) — sonst würde jeder echte
Nachtrag als unmöglicher Wert gemeldet. Dieselbe Regel entscheidet beim Rechnen der Tage, ob eine Menge verworfen wird.

> **Tage aus der Langzeitstatistik von Home Assistant.** Die Prüfung auf unmögliche Stundenwerte schaut nur auf Tage aus
> eigenen Stundenwerten; der Verdacht auf PV-Doppelerfassung ([§4.18](#418-pv-doppelerfassung)) zählt für den
> spezifischen Tagesertrag auch Tage aus der Langzeitstatistik (die PV wie in der Tagesansicht im Cockpit), nur die
> Performance Ratio bleibt die der gespeicherten Tageszeile. An
> einem Tag, dessen Mengen aus der Langzeitstatistik kommen, ist eine hohe Stunde die Zahl von Home Assistant, wie im
> Energie-Dashboard; ein Sprung mit dem typischen Muster (Sensor fällt kurz auf 0 und kehrt zurück) meldet
> [§4.8b](#48b-zaehlerstaende--sprung-in-home-assistant). **Ein reiner Sprung ohne dieses Muster** bekommt an einem
> solchen Tag **keinen** Befund: prüfe ihn in Home Assistant unter *Entwicklerwerkzeuge → Statistik* und berichtige ihn
> dort.

> **Ältere Tage** (über 30 Tage) prüft die Stundenwert-Prüfung nicht — die beiden Tagesprüfungen (Einspeisung über
> Erzeugung, Nachtrag) sehen alle gespeicherten Tage: dort stehen meist schon berichtigte Werte, und für den aktuellen
> Lernfaktor zählen sie nicht mehr. Wer ältere Tage trotzdem reparieren will, nutzt in der Reparatur-Werkbank
> «Mehrere Tage neu aggregieren» über den entsprechenden Bereich — das reicht so weit zurück wie die Langzeitstatistik
> von Home Assistant.

---
