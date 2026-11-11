<!-- anker: 48-mqtt-topic-abdeckung -->
### 4.8 MQTT-Topic-Abdeckung <a name="48-mqtt-topic-abdeckung"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten — aber **nur**, wenn der Empfang über MQTT
> eingeschaltet ist (*Einstellungen → Integration → MQTT-Broker-Verbindung*, Schalter «Daten über MQTT empfangen
> (Import)»). Ohne eingeschalteten Empfang erscheint die Kategorie gar nicht — nicht „OK“, nicht „leer“ —, damit
> Anwender ohne MQTT sie nicht sehen.

**Was wird geprüft:** Kommen die MQTT-Topics, die eedc aus der Datenquellen-Zuordnung erwartet, tatsächlich an? Die
Erwartung entsteht in eedc; der Absender (eine Automation in Home Assistant, ioBroker, Node-RED) ist fest verdrahtet.
Vergisst dort jemand ein neues Feld oder zieht nach einem neuen Import die Nummer eines Geräts nicht nach, laufen
Erwartung und Wirklichkeit auseinander — diese Kategorie macht das sichtbar.

**Schwellwerte für „veraltet“:**

| Topic-Kategorie | Maximales Alter |
|----------------|-----------------|
| Live-Topics (sensorgetrieben) | 2 Minuten |
| Energie-Topics (alle 5 Minuten plus Puffer) | 10 Minuten |

**Welche Topics eedc erwartet.** Gemeldet wird nur, was auch über MQTT kommen soll: Felder, deren Quelle auf **«Keine»**
oder einen **Sensor aus Home Assistant** gespeichert ist, tauchen nicht auf. Es zählt die **gespeicherte** Wahl — zeigt die
Datenquellen-Fläche «Keine» nur an, weil nichts ankommt, zählt das nicht; einmal «Keine» anklicken speichert die Wahl.
Felder über ein **MQTT-Gateway** zählen mit, deren Werte laufen durch denselben Weg. Erwartet wird nur, was es am Gerät
gibt, und davon nur, was am Gerät Pflicht ist oder was du über MQTT zugeordnet hast:

- **Pflicht** heißt dasselbe wie in der Datenquellen-Zuordnung (rot markierte Felder): die Zählerstände Einspeisung,
  Netzbezug und PV gesamt, am Speicher Ladung und Entladung, an der Wärmepumpe der Strom und — außer an einer
  Split-Klimaanlage — die Wärmemenge, am E-Auto die Kilometer, an der Wallbox die Ladung.
- **Optionale Felder** — Live-Leistungen, Ladestand, Netzladung, Betriebsart-Felder an einer Luft-Wasser-Wärmepumpe —
  erwartet eedc nur, wenn du ihnen MQTT oder ein Gateway als Quelle zugeordnet hast (eine Luft-Wasser-Wärmepumpe ohne
  Zuordnungen erwartet damit drei Topics statt siebzehn).
- Die V2H-Entladung nur an einem E-Auto mit „V2H-fähig“, die Netzladung nur an einem Speicher mit «Lädt aus dem Netz
  (z. B. Backup-/Notladung)», der Strom für Heizen und Warmwasser nur an einer Wärmepumpe mit getrennter Strommessung.
- **Neben einer Wallbox mit Ladezähler** erwartet eedc am E-Auto keine Lade- und Verbrauchsfelder (die Wallbox trägt die
  Ladung); Kilometer bleiben erwartet, Ladestand und V2H-Entladung, wenn du sie über MQTT zugeordnet hast.
- Bei **zwei Wegen zu einer Größe** (PV gesamt oder Zähler je Modul, Wärme gesamt oder Heizwärme) erwartet eedc beide,
  solange keiner zugeordnet ist, und nach der Zuordnung des einen nur noch diesen.
- Publizierst du auf ein Topic, ohne das Feld zuzuordnen, übernimmt die Datenquellen-Fläche die Zuordnung beim nächsten
  Öffnen, sobald Werte ankommen — erst dann gilt das Feld hier als zugeordnet.

Wie ein Topic eingerichtet wird, steht im Handbuch Einstellungen,
[§7.5 Ein MQTT-Topic zuordnen](HANDBUCH_EINSTELLUNGEN.md#75-ein-mqtt-topic-zuordnen).

---
