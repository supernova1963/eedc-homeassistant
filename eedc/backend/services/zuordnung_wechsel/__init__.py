"""Sensorwechsel mit Grund — Zuordnungs-Wechsel je Zählerschlüssel (Bauplan Fassung 2, Sitzung 1 «Verzeichnen und schützen»).

* ``zeitpunkt.py`` — B-0 «Zuordnung zum Zeitpunkt»: ``quelle_am(wechsel, z)`` (rein), Laden je Sitzung.
* ``anwenden.py`` — B-0 an den Schreibern der Zählerstand-Reihe (Writer, Heilen, Live-Rückfall, LTS-Tag).
* ``quelle.py`` — die wirksame Quelle je Schlüssel samt Gateway-Zeile, Prüf-Funktion «ändert sich die wirksame Quelle?».
* ``verzeichnen.py`` — eine Zeile je wirksamer Änderung (``herkunft = wechsel``, Grund leer).
* ``ueberfuehrung.py`` — Altbestand aus dem Aktivitäts-Protokoll (Start-Migration, idempotent).
* ``raeumen.py`` — Gerät und Innengerät räumen ihre Zeilen.

Tabelle: ``models/zuordnung_wechsel.py``. Nach außen ändert Sitzung 1 nichts Sichtbares: der Dialog (B-2), die Leser
(B-3/B-5), die Korrektur (B-6) und die Befunde (B-7/B-8) folgen in den Sitzungen 2–4.
"""
