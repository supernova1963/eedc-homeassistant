<!-- anker: 44-monatsdaten--vollstaendigkeit -->
### 4.4 Monatsdaten – Vollständigkeit <a name="44-monatsdaten--vollstaendigkeit"></a>

**Was wird geprüft:** Welche Monate zwischen der **Inbetriebnahme der Anlage** und dem Vormonat sind erfasst? Ist keine
Inbetriebnahme gepflegt, gilt das älteste Anschaffungsdatum deiner **Erzeuger** (PV-Module, Balkonkraftwerk), zuletzt der
erste vorhandene Monat. ⚠ Andere Komponenten ziehen den Bereich **nicht** zurück: Ein E-Auto von 2017 an einer Anlage von
2022 fordert keine Zählerwerte ab 2017 — eine Monatszeile ist eine Aussage über die Anlage, nicht über ein einzelnes
Gerät. Ob eine Komponente in einem Monat *mitrechnet*, entscheidet weiterhin ihr eigenes Anschaffungs- bzw.
Stilllegungsdatum. Der laufende Monat wird ausgeklammert, weil er noch nicht abgeschlossen ist. Das Ergebnis fließt
zusätzlich in den Fortschrittsbalken «Monatsdaten-Abdeckung» oben ein.

> **Warum ein fehlender Monat ein Fehler ist und keine Warnung.** Einspeisung und Netzbezug sind die Basis, auf der eedc
> überhaupt eine Bilanz bildet. Ohne sie weiß eedc nicht, woher der Strom eines Geräts kam — **und rechnet trotzdem**:
> Der Direktverbrauch entsteht als *Erzeugung minus Einspeisung minus Speicherladung*, und eine fehlende Einspeisung
> liest diese Rechnung als **0**. Dann gilt die ganze Erzeugung als Eigenverbrauch und wird mit dem **Netzpreis** statt
> der Einspeisevergütung bewertet. An einem echten Monat nachgerechnet: **622 € statt 282 €**, bei einem Gesamtverbrauch
> von 1.838 statt 520 kWh. Die Zahl wäre also nicht ungenau, sondern systematisch zu gut — deshalb ist eine Lücke hier
> kein Schönheitsfehler.
>
> **Hinweis zur Abdeckung:** Der Prozentwert oben bezieht sich auf erwartete Monate, nicht auf Datenfelder *innerhalb*
> eines Monats. Ein zu 100 % abgedeckter Stand kann trotzdem unvollständige Pflichtfelder enthalten — das prüft §4.5.

---
