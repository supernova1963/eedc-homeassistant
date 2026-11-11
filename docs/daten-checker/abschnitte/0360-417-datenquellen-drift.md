<!-- anker: 417-datenquellen-drift -->
### 4.17 Datenquellen-Drift zu Home Assistant <a name="417-datenquellen-drift"></a>

> **Variantenhinweis:** Nur mit HA-Verbindung. Ohne sie gibt es keine Vergleichsseite, die Kategorie wird still übersprungen.

**Was wird geprüft:** Stimmt das, was eedc für die letzten 90 Tage gespeichert hat, noch mit dem überein, was Home Assistant für denselben Tag ausweist? Geprüft werden **zwei Achsen**: die **PV-Tagessumme** über alle PV-Module und Balkonkraftwerke, und **jede andere zugeordnete Komponente einzeln** — Wallbox, E-Auto, Wärmepumpe, Sonstiges, dazu Einspeisung und Netzbezug. Gemeldet wird ein Tag ab **mindestens 2 kWh und mindestens 5 %** Unterschied — beide Schwellen zusammen, damit Rundungs-Unterschiede still bleiben.

**Warum das zählt:** eedc hat seine Tageswerte über die Zeit aus verschiedenen Quellen aufgebaut. Ältere Tage können auf einem Stand stehen, den ein heutiger Abruf anders beantwortet. Diese Werte tragen nicht nur die Energiebilanz, sondern auch Wirtschaftlichkeit und CO₂ — eine Abweichung an der Wallbox kostet genauso wie eine an der PV. Die Kategorie startet zugeklappt, weil Drift ein Hinweis ist.

> **Warum PV als Summe und alles andere je Gerät.** Mehrere Strings messen dieselbe Sache; ihre Summe ist die Zahl, die du kennst. Zwei **Geräte** messen nicht dieselbe Sache: In einer gemeinsamen Summe würde ein Plus an der Wärmepumpe ein Minus an der Wallbox ausgleichen, und übrig bliebe eine unauffällige Null.

> **Liest eedc deine Anlage aus der Statistik von Home Assistant,** nimmt es PV, Einspeisung, Netzbezug und Speicher an solchen Tagen direkt von dort — die eedc-Seite des Vergleichs *ist* dann die Zahl von Home Assistant, und eine Abweichung der alten gespeicherten Tageszeile wird nicht mehr gemeldet (die Tagesansicht im Cockpit zeigt sie ohnehin nicht). Wallbox, E-Auto, Wärmepumpe und sonstige Geräte kommen an einem solchen Tag ebenfalls von dort, wenn sie zugeordnet sind; nur ein Gerät ohne solchen Wert liest die Prüfung aus der gespeicherten Tageszeile. Ein bloßes Neuberechnen des Tages ändert daran nichts — deshalb trägt die Zeile an einer solchen Anlage **«Aus Home Assistant neu übernehmen»** (zuerst der Abgleich mit Home Assistant, dann der Tag); ohne diese Verbindung heißt der Knopf **«Tag neu aufbauen»**. Massen-Reparaturen gibt es bewusst nur in der Reparatur-Werkbank, damit sie aktiv gewählt werden.
>
> **Nach einer Korrektur in Home Assistant** (etwa unter *Entwicklerwerkzeuge → Statistik*) trägt eedc bis zum nächtlichen Abgleich um 02:45 noch den alten Stand. So lange bleibt der Drift-Eintrag stehen; danach verschwindet er von selbst. Ob der Abgleich gelaufen ist, steht unter *Einstellungen → System → Protokolle* (Reiter **Aktivitäten**, Kategorie **„Scheduler-Jobs"**): eine Zeile je Nacht und Anlage, auch wenn nichts abweicht. Sofort geht es mit **«Aus Home Assistant neu übernehmen»** an der Zeile.
>
> **Verglichen wird nur, was Home Assistant für den Tag auch liefern konnte.** Ein Zähler ohne Summen-Spalte (§4.9) taucht hier nicht als Lücke auf — sonst meldete der Vergleich Phantom-Drift und böte einen Knopf an, der korrekte Werte mit 0 überschreibt.
>
> **Und je Gerät nur, was auf beiden Seiten einen Wert hat.** Liefert Home Assistant für ein Gerät einen Wert und die gespeicherte Tageszeile nicht, ist das eine **Lücke** und gehört §4.10 *Energieprofil – fehlende Tageswerte*. Die PV-Tagessumme vergleicht die Prüfung dagegen, sobald eine der beiden Seiten mehr als 0 kWh trägt. Der **Speicher** steht in keiner der beiden Achsen: Sein Tages-Netto darf legitim ~0 sein, und sein Vorzeichen hat mit §4.21 *Batterie-Vorzeichen in der Historie* eine eigene Prüfung.
>
> **Höchstens 20 PV-Tage, und je Tag nur, was an diesem Tag in Betrieb war.** Die PV-Tage stehen nach der Größe der Abweichung; die 20 größten erscheinen als Glieder der Zeile «n Tage weichen von Home Assistant ab», die Zeile nennt die Gesamtzahl. Die Home-Assistant-Seite liest an jedem Tag nur die Sensoren der Komponenten, die an diesem Tag in Betrieb waren (Anschaffung, Stilllegung, „aktiv") — ein später angeschafftes oder stillgelegtes Modul erzeugt so keine Abweichung, die kein Knopf auflösen könnte.

---
