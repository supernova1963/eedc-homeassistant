<!-- anker: 412-zeitzone--abweichung-zu-home-assistant -->
### 4.12 Zeitzone – Abweichung zu Home Assistant <a name="412-zeitzone--abweichung-zu-home-assistant"></a>

> **Variantenhinweis:** Nur relevant, wenn eine Verbindung zu Home Assistant besteht — als Add-on oder per Zugriffstoken. Ohne HA-Verbindung wird die Kategorie still übersprungen: Es gäbe nichts zu vergleichen und nichts zu tun.

**Was wird geprüft:** Rechnen eedc und Home Assistant mit derselben Uhrzeit? Verglichen wird der **aktuelle UTC-Abstand** beider Systeme, nicht der Name der Zeitzone — Wien, Zürich und Amsterdam gehen genauso wie Berlin, und dort wäre eine Meldung falsch.

**Warum das zählt:** Läuft eedc in einem Container ohne gesetzte Zeitzone, arbeitet er auf UTC. Der Tag endet dann für eedc um 22:00 Ortszeit, und die letzten Stunden werden dem Folgetag zugerechnet. Betroffen sind alle Tageswerte — die Tagesansicht im Cockpit, das Energieprofil, die Tagesabschlüsse. Wie die Zeitzone im Standalone-Container gesetzt wird, steht in [HANDBUCH_INSTALLATION.md §2](HANDBUCH_INSTALLATION.md#2-installation).

**Was der Befund nicht leistet:** Er beschreibt den Zustand von **jetzt**. Bereits gespeicherte Tage werden dadurch nicht korrigiert — die lassen sich nach dem Neustart in der Reparatur-Werkbank (*Einstellungen → Daten → Energieprofil-Pflege*) neu berechnen.

---
