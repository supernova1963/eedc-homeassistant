<!-- anker: 41-stammdaten -->
### 4.1 Stammdaten

**Was wird geprüft:** Pflicht-Stammdaten der Anlage (Inbetriebnahme, Leistung), die kWp-Konsistenz zwischen Anlage,
PV-Modulen und Wechselrichtern, optionale Felder für PVGIS und Community-Vergleich (Koordinaten, Ort/PLZ) sowie die
Performance Ratio gegenüber der PVGIS-Prognose, sobald genug Historie vorliegt.

Bei Datumsbefunden unterscheidet eedc **Erzeuger** (PV-Module, Balkonkraftwerk) von allen anderen Geräten: Ein Erzeuger,
der älter ist als die Anlage, deutet auf ein falsches Datum; ein E-Auto oder eine Heizung aus der Zeit davor ist normal
und wird nur als Auskunft genannt.

> **Hinweis:** Ausrichtung und Neigung stehen nicht an der Anlage, sondern je Dachfläche an der PV-Modul-Komponente
> (siehe [HANDBUCH_EINSTELLUNGEN.md §3](HANDBUCH_EINSTELLUNGEN.md#3-komponenten)); der Daten-Checker prüft sie dort.

---
