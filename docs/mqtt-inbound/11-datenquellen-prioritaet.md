## Datenquellen-Prioritaet

MQTT-Inbound hat Konfidenz 91% und liegt zwischen Connector (90%) und HA Statistics (92%):

```
Gespeichert (85%) → Connector (90%) → MQTT-Inbound (91%) → HA Statistics (92%)
```

**Diese Reihenfolge gilt nur fuer den laufenden Monat.** Dort ist sie eine
Live-Vorschau: die frischere Quelle gewinnt, wer HA Statistics hat, sieht deren
Werte statt der MQTT-Werte.

Im **abgeschlossenen** Monat gilt das Gegenteil: gespeicherte Werte sind
authoritativ. Connector und HA-Statistics fuellen dort nur Felder, die noch
leer sind, und ueberschreiben nichts rueckwirkend; MQTT-Inbound wird fuer
vergangene Monate gar nicht erst abgefragt. Ein importierter Monatswert
(Cloud-, Portal- oder CSV-Import) bleibt damit stehen, auch wenn fuer dasselbe
Feld ein HA-Sensor zugeordnet ist — die Zuordnung muss dafuer niemand
entfernen.

**Das ist die Anzeige-Seite.** Beim *Schreiben* gilt eine eigene Hierarchie
(`backend/core/source_priority.py`): Cloud-/Portal-Import und HA-Statistik-
Import liegen dort auf **derselben** Stufe, bei gleicher Stufe gewinnt der
spaetere Schreiber. Ein HA-Statistik-Import mit angehaktem „ueberschreiben"
ersetzt also einen importierten Wert dauerhaft. Nur ein im Formular gepflegter
Wert (Stufe `manual:form`) ist gegen beide geschuetzt.

SoT der Regeln: Anzeige
`backend/core/berechnungen/datenquellen.py::merge_datenquellen`, Schreiben
`backend/services/provenance.py::write_with_provenance`.

