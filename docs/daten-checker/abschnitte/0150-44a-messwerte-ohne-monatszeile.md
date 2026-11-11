<!-- anker: 44a-messwerte-ohne-monatszeile -->
### 4.4a Monatsdaten – Messwerte ohne Monatszeile <a name="44a-messwerte-ohne-monatszeile"></a>

**Was wird geprüft:** Gibt es Messwerte einzelner Komponenten (PV je Modul, Speicher-Zyklen, Wallbox-Ladung …) für einen
Monat, der selbst nicht erfasst ist?

Ein Monat besteht in eedc aus zwei Teilen: der **Zählerzeile** der Anlage (Einspeisung, Netzbezug …) und den
**Messwerten je Komponente** daneben. Fehlt die Zählerzeile, fehlt der Monat in allen Listen — die Messwerte der
Komponenten wirken aber weiter und weisen einen erneuten Import dieses Monats ab.

> **Vorbeugen:** Der Lösch-Dialog unter *Einstellungen → Daten → Monatsdaten* nennt, wie viele Komponenten-Messwerte an
> einem Monat hängen, und löscht sie zusammen mit der Zählerzeile; hängt ein Zählerstand daran, warnt er davor.

---
