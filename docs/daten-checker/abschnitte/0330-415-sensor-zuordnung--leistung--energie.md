<!-- anker: 415-sensor-zuordnung--leistung--energie -->
### 4.15 Sensor-Zuordnung – Leistung ↔ Energie verwechselt <a name="415-sensor-zuordnung--leistung--energie"></a>

**Was wird geprüft:** Steht in jedem Feld ein Sensor der passenden Art — ein **Leistungssensor** (W/kW) dort, wo eedc eine Momentanleistung erwartet, und ein **kWh-Zähler** dort, wo es eine Energiemenge erwartet? Verglichen wird die in Home Assistant hinterlegte Einheit, nicht der Wert.

**Warum das zählt:** Die beiden Größen sehen im Sensor-Namen oft gleich aus und bedeuten Verschiedenes. Ein Zählerstand in einem Leistungs-Feld wird als Momentanleistung gelesen — aus 7.130 kWh werden 7.130 W, und der live berechnete Restverbrauch klemmt auf 0. Umgekehrt lässt sich aus einem Leistungssensor die Energie nur schätzen.

> **Nur diese eine Verwechslung wird gemeldet.** Ladestand (%), Temperatur (°C), Preis (ct/kWh) und Kilometer bleiben ungeprüft: Dort sind mehrere Einheiten legitim, und eine Meldung wäre öfter falsch als richtig. **Ohne HA-Verbindung** wird die Kategorie still übersprungen — die Einheit kommt aus Home Assistant.

---
