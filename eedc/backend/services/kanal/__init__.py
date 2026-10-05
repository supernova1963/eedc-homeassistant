"""Kanalstatistik (HA-Bauform, Etappe E1): Katalog und Schreiber.

* ``katalog.py``  — die EINE Zuweisung Feld → Kanal-Art/Familie, abgeleitet aus der Registry.
* ``schreiber.py`` — Spiegel (HA), eigene Summe (MQTT), Betriebsart-Mitschrift; parallel zum Bestand.
* ``nachfuellen.py`` — E2: Spiegel aus HAs ganzer Historie nachfüllen (Startlauf, Marke je Anlage), Neu-Laden.
* ``konsistenz.py`` — E2: Spiegel gegen HA prüfen, ab der ersten Abweichung neu spiegeln (Tages-Nachlauf 02:45).
* ``lesen.py`` — E2: Lese-Hilfe NUR für Wächter und Proben (Kanalwert, Δ) — nicht die Lese-Schicht aus E3.

Stand E2: wird geschrieben und nachgefüllt, von keiner Sicht gelesen. Die Familie ``bestand`` bleibt **unbelegt** (Entscheid Gernot 06.10., Bauplan §3b): die bisherigen Stunden- und
Tageszeilen werden nicht in Kanäle umgewandelt; sie bleiben die Quelle für Zeiträume, die die Kanäle nicht voll decken.
"""
