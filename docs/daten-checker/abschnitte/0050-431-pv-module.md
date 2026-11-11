<!-- anker: 431-pv-module -->
#### 4.3.1 PV-Module

Je PV-Modul (String) prüft eedc Leistung in kWp und Ausrichtung/Neigung. Die PV-Erzeugung prüft eedc **anlagenweit**:
ein einzelner Gesamtwert der Anlage deckt alle Strings ab — er füllt die Lücken der Module ohne eigenen Wert, verteilt
nach kWp. Je Monat gibt es deshalb vier Zustände: jedes Modul gemessen (vollständig), Gesamtwert verteilt (geschätzt,
kein Mangel), nur ein Teil der Strings und kein Gesamtwert (unvollständig), gar keine PV-Quelle (fehlt).

**Nicht die Reparatur-Werkbank dafür nehmen.** «Tag neu aggregieren» und «Mehrere Tage neu aggregieren» bauen das
stündliche Energieprofil neu — sie schreiben weder den Gesamtwert noch die Monatswerte je Modul. Fehlende
Monatswerte füllen der Statistik-Import (*Einstellungen → Integration → Statistik-Import*) und der Monatsabschluss.
