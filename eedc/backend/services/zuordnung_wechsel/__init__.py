"""Sensorwechsel mit Grund — Zuordnungs-Wechsel je Zählerschlüssel (Bauplan Fassung 2; Sitzungen 1, 3a, 3b und 4).

* ``zeitpunkt.py`` — B-0 «Zuordnung zum Zeitpunkt»: ``quelle_am(wechsel, z)`` (rein), Laden je Sitzung.
* ``anwenden.py`` — B-0 an den Schreibern der Zählerstand-Reihe (Writer, Heilen, Live-Rückfall, LTS-Tag).
* ``quelle.py`` — die wirksame Quelle je Schlüssel samt Gateway-Zeile, «ändert sich die wirksame Quelle?», eigene Werte.
* ``verzeichnen.py`` — eine Zeile je wirksamer Änderung eines Schlüssels mit eigenen Werten (``herkunft = wechsel``).
* ``raeumen.py`` — Gerät und Innengerät räumen ihre Zeilen.
* ``abfrage.py`` — B-2: die eine Prüf-Funktion aller Wege («wann wird gefragt»), Angaben des Dialogs, Vollzug mit Grund
  (Fortsetzung als Wechsel-Zeile, «löschen» über ``services/feld_loeschen.py``) — Sitzung 3b, Weg B.
* ``ansatz.py``, ``bleiben.py``, ``rohstand.py``, ``monat.py`` — «Bisherige Werte bleiben»: Ansetzen mit Rand-Ständen, Sätze des
  Dialogs, MQTT-Rohstände, Monat je Geltungsabschnitt.
* ``korrektur.py`` — Bausteine des Nachlaufs (Home Assistant erreichbar?, Tage neu bilden, Kanal füllen, Stände speichern).
* ``korrektur_lauf.py`` — Schritt 4 im Hintergrund: Zustand in ``settings``, Nachlauf (Füllen), stündlicher Anstoß offener
  Läufe, Fortsetzen nach dem Start, Aufräumen.
* ``zaehler_getauscht.py`` — Einstieg «Zähler getauscht (gleiche Quelle)»: Weg nach der Quelle des Kanals zur Stunde des Tauschs.
* ``nachtrag.py`` — Rest nach Weg B: Quellen in Anwender-Sprache, Feld-Kennung, «ist ein Quellenwechsel».

Tabelle: ``models/zuordnung_wechsel.py``. Routen: ``api/routes/datenquellen.py`` (Feld-Route, Prüf-Route), ``mqtt_presets.py``
(Preset), ``sensorwechsel.py`` (Einstieg «Zähler getauscht», Fortschritt, laufende Läufe, wartende Wechsel). Seit Weg B entfernt:
«Grund nachtragen» und die Überführung des Altbestands (Sitzung B2), die Korrektur («verwerfen» mit «Falsch seit», Lücken-Zeilen,
Korrektur am versetzten Abschnitt, Sitzung B3a).
"""
