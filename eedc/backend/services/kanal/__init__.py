"""Kanalstatistik (HA-Bauform, Etappe E1): Katalog und Schreiber.

* ``katalog.py``  — die EINE Zuweisung Feld → Kanal-Art/Familie, abgeleitet aus der Registry.
* ``schreiber.py`` — Spiegel (HA), eigene Summe (MQTT), Betriebsart-Mitschrift; parallel zum Bestand.
* ``nachfuellen.py`` — E2: Spiegel aus HAs ganzer Historie nachfüllen (Startlauf, Marke je Anlage), Neu-Laden.
* ``konsistenz.py`` — E2: Spiegel gegen HA prüfen, ab der ersten Abweichung neu spiegeln (Tages-Nachlauf 02:45).
* ``lesen.py`` — E3: die Lese-Schicht — ``zeitraum``/``reihe``/``stunden``/``mittel`` (je als Stapel), jede mit Abdeckung
  (die E2-Lese-Hilfe für Wächter ist darin aufgegangen).
* ``fenster.py`` — E3: Tages- und Monatsfenster so, wie der Bestand sie bildet (an einer Stelle).
* ``quellenwahl.py`` — E3: Kanal oder Bestand je Zeitraum, mit Grund (Bauplan §3b).
* ``monatsraster.py`` — E3: je Monat Δ, Abdeckung und eine Quellenwahl (G7; ohne P8-Überlagerung).
* ``bilanz_adapter.py`` — E4a-1: Tag, Monat und Kalendermonat je Sensor der Bilanz-Gruppe aus Kanälen, in der Datenform der
  heutigen Leser, in zwei Fassungen („wie Bestand" / „wie HA"); noch von niemandem benutzt.
* ``bilanz_quellenwahl.py`` — E4a-1: Kanal oder Bestand je Tag und Monat für alle Eingänge der Bilanz-Gruppe.

Stand E3: wird geschrieben und nachgefüllt; die Lese-Schicht ist vorhanden, aber von keiner Sicht, Route und nicht von den
Monats-Fakten benutzt (Wächter ``test_kanal_lesen_waechter.py``; Umhängen ist E4). Die Familie ``bestand`` bleibt **unbelegt** (Entscheid Gernot 06.10., Bauplan §3b): die bisherigen Stunden- und
Tageszeilen werden nicht in Kanäle umgewandelt; sie bleiben die Quelle für Zeiträume, die die Kanäle nicht voll decken.
"""
