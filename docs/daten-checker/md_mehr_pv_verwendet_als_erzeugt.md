# Mehr PV verwendet als erzeugt?

## Was eedc sieht
Einspeisung plus die aus PV geladene Speichermenge ist für den Monat größer als die Erzeugung. Beides kommt aus derselben
Erzeugung — zusammen kann es nicht mehr sein, als die Anlage geliefert hat. Bewusst als Frage: die häufigste Ursache ist
kein Messfehler. Kleine Abweichungen (bis 2 % der Erzeugung, mindestens 5 kWh) bleiben still.

## Lösungsweg
1. Wird der Speicher auch aus dem Netz geladen (Arbitrage, Notladung)? Dann unter
   *Einstellungen → Komponenten → Speicher* «Lädt aus dem Netz (z. B. Backup-/Notladung)» setzen und am Befund
   **«Monat öffnen»** beim Speicher die «Netzladung» eintragen. Dann stimmt die Energie, nur die Zuordnung fehlte.
2. Sonst im geöffneten Monat die Erzeugung prüfen: ist sie zu niedrig erfasst, etwa weil ein String-Sensor ausgesetzt
   hat? Berichtigen und speichern.
3. Sind Einspeisung und Netzbezug vertauscht, steht für den Monat meist zusätzlich der Befund „Einspeisung größer als
   PV-Erzeugung“ — dann dort weitermachen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
eedc korrigiert nichts selbst; der Monat rechnet mit den erfassten Werten.
