"""Sensorwechsel mit Grund, Korrekturrunde 4b-1-K2 (Bauplan «Zu §14» Nr. 109–121) — der Rest nach Weg B, Sitzung B3a.

Geblieben ist die Probe zum Fortschritt eines Laufs, dessen Nachlauf nur noch die Stände speichert (``korrektur_lauf.fuellen_offen``;
der Lauf nach dem Ansetzen eines Wechsels «bleiben» trägt denselben Auftrag). Die Proben der Korrektur über ein Stück, der Lücke
(Nr. 111 F2, Nr. 113, U1, E-K6, N3, N4, Regel `zaehler_naht` an gesperrten Stücken, Grund `luecke_verworfen`) sind mit der Korrektur
und dem Befund ``zaehler_versatz`` entfernt.

Schwesterdateien: test_sensorwechsel_s4k_proben.py, test_sensorwechsel_s4_nachtrag.py.
"""

from __future__ import annotations


def test_nr111_fortschritt_staende_im_lauf_sind_kein_ausstehendes_fuellen():
    """Speichert der Hintergrund-Lauf nur noch die Stände (Kanal-Teil nach dem Commit gelaufen), sagt die Fläche «Korrektur
    läuft …» — nicht «Das Füllen aus Home Assistant steht noch aus …»; das steht erst nach einem gescheiterten Versuch."""
    from backend.services.zuordnung_wechsel.korrektur_lauf import FUELLEN_PRAEFIX, fuellen_offen

    laeuft = {"fuellen": {"erledigt": False, "kanal_erledigt": True}, "fehler": []}
    assert fuellen_offen(laeuft) is False
    assert fuellen_offen({**laeuft, "fehler": [{"tag": None, "grund": FUELLEN_PRAEFIX + "ConnectionError: weg"}]}) is True
    assert fuellen_offen({"fuellen": {"erledigt": False}, "fehler": []}) is True
    assert fuellen_offen({"fuellen": {"erledigt": True, "kanal_erledigt": True}, "fehler": []}) is False
    assert fuellen_offen({"fuellen": None}) is False
