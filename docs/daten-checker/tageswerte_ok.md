# Keine reparierbaren Tages-Lücken

## Was eedc sieht
In den letzten 90 Tagen trägt jeder Tag mit zugeordnetem Zähler einen Wert. Oder es gibt leere Tage, aber Home Assistant hat
für sie ebenfalls nichts — die Zeile sagt dann «Keine reparierbaren Tages-Lücken gefunden». Solche Lücken sind keine
Fehlfunktion: eedc reicht nur so weit zurück wie Home Assistant selbst.

## Lösungsweg
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

## Was ohne Handlung gilt
Tage, für die auch Home Assistant nichts hat, bleiben leer; sie lassen sich nicht mehr füllen.
