# Geräte-Connector liefert für den laufenden Monat keinen Wert

## Was eedc sieht
Ein Connector-Wert ist immer die Differenz zweier verschiedener gespeicherter Zählerstände — der erste vor dem Monat oder
im Monat, der zweite im Monat oder danach. Für den laufenden Monat fehlt der zweite: Entweder gibt es bisher erst einen
Zählerstand, oder der jüngste ist mindestens zwei Tage alt, weil der tägliche Abruf nichts Neues bringt. Die Details nennen den Bestand und wann der Abruf zuletzt lief. In
der Monatsansicht im Cockpit fehlt der Connector dann als Quelle, ohne dass es sonst jemand sagt.

## Lösungsweg
1. Am Befund **«Zum Connector»** klicken — der Assistent «Geräte-Connector» öffnet sich.
2. Prüfen, ob das Gerät im Netz erreichbar ist und die Zugangsdaten noch gelten, dann mit **«Jetzt ablesen»** den Zähler
   von Hand ablesen. Scheitert der Abruf, steht der Grund dort und im Aktivitätsprotokoll unter
   [Protokolle](eedc:/einstellungen/system?block=protokolle), Reiter «Aktivitäten».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — sobald für den Monat ein zweiter, davon verschiedener
   Zählerstand vorliegt, ist die Zeile verschwunden.

## Was ohne Handlung gilt
Der tägliche Abruf läuft bei jedem eingerichteten Connector um 3:30 Uhr weiter, er lässt sich weder ein- noch ausschalten;
kommt ein neuer Zählerstand dazu, verschwindet der Befund von selbst. Bis dahin rechnet der Monat ohne den Connector.
