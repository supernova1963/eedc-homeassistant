## 5. E-Auto

> **Die Wallbox ist die Summe, ein Auto mit eigener Messung trägt seine eigene Heimladung (seit v4.0.51).** Die Heim-Felder `ladung_pv_kwh` („Heim: PV“), `ladung_netz_kwh` („Heim: Netz“) und `ladung_kwh` („Heim: gesamt“) werden **jedem** E-Auto angeboten, auch neben einer Wallbox. Trägt ein Auto dort einen Wert (auch 0) oder — im laufenden Monat — eine zugeordnete Quelle, zählt dieser Wert für dieses Auto; die Wallbox trägt den Rest, und der Rest geht nach Kilometern an die privaten Autos ohne eigene Messung ([Berechnungen, Heimladung je Auto](BERECHNUNGEN.md)). Nur an einem **Dienstwagen neben einer dienstlichen Wallbox** fehlen die Felder: dort ist die dienstliche Wallbox die dienstliche Ladung. Km-, Verbrauchs-, Extern- und V2H-Felder bleiben in jedem Fall am E-Auto. Ist die Summe der Autos größer als die Wallbox, meldet der Daten-Checker es.

### Monatserfassung

<!-- erzeugt: eingabefelder typ=e-auto liste=monat -->

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=e-auto liste=live -->

> Die fünf Zustands- und Sitzungsfelder (und die neun an der Wallbox, darunter das Textfeld „Fahrzeug am Ladepunkt") sind
> **reine Anzeige**: eedc liest sie live, speichert sie nicht und rechnet nicht mit ihnen (kein Kanal, keine Monatsmenge).
> Keine Einheiten-Umrechnung. Das Gegenstück zum Textfeld der Wallbox ist kein Sensor, sondern das Stammdatum
> **„Kennung in der Steuerung"** am E-Auto (Einstellungen → Investitionen).

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

