# eedc und Home Assistant rechnen mit verschiedenen Zeitzonen

## Was eedc sieht
eedc und Home Assistant liegen zeitlich auseinander — jede Abweichung zählt, auch eine halbe Stunde. Verglichen wird der
aktuelle Abstand zur Weltzeit, nicht der Name der Zeitzone. Die Details nennen die Zeitzone von Home Assistant und den
Abstand. Rund um Mitternacht landen Stundenwerte dadurch im falschen Tag — betroffen sind alle Tageswerte: Tagesansicht
im Cockpit, Energieprofil, Tagesabschlüsse.

## Lösungsweg
1. Als Add-on: am Befund **«Zum Neustart»** klicken — die [Protokolle](eedc:/einstellungen/system?block=protokolle)
   öffnen sich; dort **«Neustart»** klicken. eedc übernimmt die Zeitzone beim Start von Home Assistant.
2. Standalone (eigener Container): dort die Umgebungsvariable `TZ` auf die Zeitzone von Home Assistant setzen, die die
   Details nennen (in `docker-compose.yml` unter `environment`), und den Container neu starten.
3. Bereits gespeicherte Tage ändern sich dadurch nicht. Sie lassen sich danach in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) mit «Mehrere Tage neu aggregieren» neu
   berechnen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
eedc rechnet weiter mit seiner eigenen Zeit: Stunden rund um Mitternacht werden weiter dem falschen Tag zugeordnet, auch in
allen neuen Tagen.
