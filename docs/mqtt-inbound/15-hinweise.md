## Hinweise

- **Payload-Format:** Zahlen (z.B. `4200`, `72.5`), kein JSON. Ausnahmen: die Zustands- und Textfelder (Spalte „Payload" unter [Topics je Gerätetyp](#topics-je-gerätetyp), darunter `betriebsmodus` mit Wort oder Code) und die [Themen](#themen-je-geraet-ab-der-naechsten-version).
- **Einheiten:** Leistung in **Watt** (nicht kW), Energie in **kWh** — die Einheit jedes Topics steht in der Spalte „Einheit" unter [Topics je Gerätetyp](#topics-je-gerätetyp).
- **Batterie:** Positive Werte = Ladung, negative = Entladung
- **Retained Messages:** EEDC publisht beim Speichern Initialwerte (0) als Retained, damit Topics am Broker sichtbar sind — nicht auf `betriebsmodus`: dort hiesse `0` „Aus".
- **Reconnect:** Bei Verbindungsverlust verbindet sich der Subscriber automatisch nach 10 Sekunden neu.
- **Monatsabschluss:** Energy-Topics erscheinen automatisch als Vorschlaege im Monatsabschluss-Wizard (Konfidenz 91%). Kein zusaetzliches Mapping noetig.
