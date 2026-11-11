<!-- anker: 421-batterie-vorzeichen-historie -->
### 4.21 Batterie-Vorzeichen in der Historie <a name="421-batterie-vorzeichen-historie"></a>

**Was wird geprüft:** Tragen gespeicherte Tage die Batterie-Richtung noch **verkehrt herum**?

**Warum das zählt:** Ältere eedc-Versionen schrieben das Batterie-Netto bei der Tagesberechnung in umgekehrter Richtung. Der Fehler steht in bereits gespeicherten Tagen, bis sie neu berechnet werden. **Die Live-Ansicht ist nicht betroffen** — sie hat einen eigenen Weg. Betroffen sind Energieprofil und Tages-Historie.

Erkannt wird das am **Datensignal**, nicht am Datum: Der gespeicherte Tageswert wird gegen einen frischen Abruf verglichen. Zeigen beide in entgegengesetzte Richtungen, ist der Tag mit der alten Logik gerechnet. Eine Zeile nennt alle Tage samt Zeitraum und baut sie in Fenstern von höchstens 31 Tagen neu auf; die Zeile «n Tage mit vertauschtem Batterie-Vorzeichen» bietet daneben jeden Tag einzeln an.

> **Liest eedc deine Anlage aus der Statistik von Home Assistant,** kommt das Speicher-Netto an solchen Tagen von dort (wie in der Tagesansicht im Cockpit); ein vertauschtes Vorzeichen der alten gespeicherten Tageszeile wird dann nicht mehr gemeldet.
>
> **Eine reine Betrags-Abweichung wird hier bewusst nicht gemeldet** — nur die vertauschte Richtung. Gleiche Richtung mit anderem Betrag ist ein eigenes Thema und kein Vorzeichenfehler.

---
