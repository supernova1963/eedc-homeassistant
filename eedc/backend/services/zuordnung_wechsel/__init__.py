"""Sensorwechsel mit Grund — Zuordnungs-Wechsel je Zählerschlüssel (Bauplan Fassung 2; Sitzungen 1, 3a, 3b und 4).

* ``zeitpunkt.py`` — B-0 «Zuordnung zum Zeitpunkt»: ``quelle_am(wechsel, z)`` (rein), Laden je Sitzung.
* ``anwenden.py`` — B-0 an den Schreibern der Zählerstand-Reihe (Writer, Heilen, Live-Rückfall, LTS-Tag).
* ``quelle.py`` — die wirksame Quelle je Schlüssel samt Gateway-Zeile, «ändert sich die wirksame Quelle?», eigene Werte.
* ``verzeichnen.py`` — eine Zeile je wirksamer Änderung eines Schlüssels mit eigenen Werten (``herkunft = wechsel``).
* ``ueberfuehrung.py`` — Altbestand aus dem Aktivitäts-Protokoll (Start-Migration, idempotent); seit Sitzung 4 die
  Alt-Vermerke ``historie_hinweis`` (bei jedem Start).
* ``raeumen.py`` — Gerät und Innengerät räumen ihre Zeilen.
* ``abfrage.py`` — B-2: die eine Prüf-Funktion aller Wege («wann wird gefragt»), Angaben des Dialogs, Vollzug mit Grund
  (Fortsetzung als Wechsel-Zeile, Korrektur über ``korrektur.py``) — Sitzung 3b.
* ``korrektur.py`` — B-6: die Korrektur als ein Lauf (verwerfen, Kanal umwidmen und füllen, Tage neu bilden), Vorschau = Lauf
  — Sitzung 3a; Aufrufer: die Abfrage und die Werkbank «Werte vor dem Sensorbeginn verwerfen».
* ``korrektur_lauf.py`` — Schritt 4 im Hintergrund: Zustand in ``settings``, Nachlauf (Füllen), stündlicher Anstoß offener
  Läufe, Fortsetzen nach dem Start, Aufräumen.
* ``zaehler_getauscht.py`` — Einstieg «Zähler getauscht (gleiche Quelle)»: Weg nach der Quelle des Kanals zur Stunde des Tauschs.
* ``nachtrag.py`` — «Grund nachtragen» an einem verzeichneten Wechsel (B-7, Sitzung 4): Fortsetzung als Zeile ``nachtrag``,
  Korrektur über ``korrektur.py``; der Befund dazu steht in ``daten_checker/datenquelle/grund_fehlt.py``.

Tabelle: ``models/zuordnung_wechsel.py``. Routen: ``api/routes/datenquellen.py`` (Feld-Route, Prüf-Route), ``mqtt_presets.py``
(Preset), ``sensorwechsel.py`` (Einstieg, Fortschritt, laufende Läufe, «Grund nachtragen»). Noch offen: vor dem Sensorbeginn
(B-9, Sitzung 5); B-8 ist entfallen (Bauplan §12 Nr. 61).
"""
