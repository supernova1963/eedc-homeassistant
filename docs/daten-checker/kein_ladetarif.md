# Kein eigener Ladetarif

## Was eedc sieht
Ein E-Auto oder eine Wallbox ist aktiv, aber es gibt keinen Tarif mit der Verwendung «Wallbox (Spezialtarif)». eedc
rechnet die Ladung deshalb mit dem allgemeinen Tarif. Ob du einen eigenen Ladetarif hast, kann eedc nicht von „noch
nicht eingetragen“ unterscheiden — deshalb sagt die Zeile, womit gerechnet wird.

## Lösungsweg
1. Ohne eigenen Ladetarif: nichts zu tun — die Rechnung stimmt bereits.
2. Mit eigenem Ladetarif: unter [Strompreise](eedc:/einstellungen/stammdaten?block=strompreise) **«Neuer Tarif»**,
   Verwendung «Wallbox (Spezialtarif)», Preise und «Gültig ab» eintragen, **«Anlegen»**. Hängen Wärmepumpe und Wallbox
   an einem Zähler: Verwendung «Wärmepumpe und Wallbox (gemeinsamer Zähler)».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach Schritt 2 ist die Zeile verschwunden; ohne Ladetarif
   bleibt sie als Auskunft stehen.

## Was ohne Handlung gilt
Die Ladung wird zum allgemeinen Arbeitspreis bewertet — ohne eigenen Ladetarif ist das richtig.
