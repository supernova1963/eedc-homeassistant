<!-- anker: 411-geraete-connector-ohne-monatswert -->
### 4.11 Geräte-Connector ohne Monatswert <a name="411-geraete-connector-ohne-monatswert"></a>

> **Variantenhinweis:** Nur relevant, wenn ein **Geräte-Connector** eingerichtet ist. Ohne Connector wird die Kategorie still übersprungen — sie meldet nie etwas, das du nicht auflösen könntest.
>
> ⚠ **Ein Cloud-Import ist kein Geräte-Connector.** Beide stehen unter *Einstellungen → Integration → Import-Assistenten*, sind aber verschiedene Dinge: Der **Geräte-Connector** spricht deinen Wechselrichter **im eigenen Netz** über seine lokale Schnittstelle an; ein **Cloud-Import** (Fronius Solar.web, SolarEdge, Growatt, EcoFlow …) holt Daten vom **Portal des Herstellers**. Wer nur einen Cloud-Import eingerichtet hat, bekommt hier **keinen** Befund.

**Was wird geprüft:** Kann eedc aus den gespeicherten Zählerständen des Connectors für den **laufenden Monat** überhaupt einen Wert bilden? Ein Connector-Wert ist immer die **Differenz zweier Snapshots** — einer muss vor dem Monatsbeginn liegen, einer danach. Fehlt einer davon, liefert der Connector für diesen Monat gar nichts, und das wäre sonst nirgends zu sehen: In der Monatsansicht im Cockpit stünde einfach eine Quelle weniger, ohne Hinweis darauf, dass eine eingerichtete Quelle gerade schweigt.

**Kein Lärm am Monatsersten.** Solange der Connector aktiv liefert, fehlt ihm am 1. eines Monats bis zum ersten Abruf naturgemäß der Snapshot *im* Monat. Dieser Zustand erledigt sich innerhalb eines Tages und wird deshalb nicht gemeldet — der Befund erscheint erst, wenn der jüngste Zählerstand älter als zwei Tage ist (oder es überhaupt erst einen gibt).

> **Abgrenzung:** Liefert der Connector einen Wert, misst er aber nur einen **Teil** des Monats (frisch eingerichtet), ist das kein Befund — dort steht eine Zahl, und sie wird in der Monatsansicht im Cockpit mit ihrem Zeitraum beschriftet: „Connector (28.–30.07.2025)". Siehe [HANDBUCH_BEDIENUNG.md §2.3](HANDBUCH_BEDIENUNG.md#23-monat).

---
