"""Regression-Tests für die PV-Kategorie-Aggregation im MQTT-Heute-Pfad.

Hintergrund (Dirk-PN 2026-05-31): Im Standalone-/MQTT-Modus liefern
manche Nutzer PV nur pro Wechselrichter (`inv/<id>/pv_erzeugung_kwh`). `_compute_deltas`
übersetzte diese zu Komponenten-Keys `pv_<id>`, summierte sie aber — anders als der
HA-Pfad (live_history_service.py:372-383) — nicht auf die Kategorie `pv`. Folge:
„Heute"-PV-Kachel zeigte 0,0 kWh und der daraus abgeleitete Eigen-/Hausverbrauch
(live_power_service._calc_tages_ev_hv) blieb leer, obwohl die Daten ankamen.

⛔ **Die Vorrang-Probe hat am 01.09.2026 ihre Aussage behalten und ihren Wortlaut
verloren** (N-172). Sie hieß `test_basis_topic_hat_vorrang_keine_doppelzaehlung`
und behauptete bei gleichzeitig vorhandenem Basis-Topic `pv == 20` (nur Basis).
Das war **nur wahr, weil der Defekt da war**: Der MQTT-Pfad gab dem
anlagenweiten Zähler Vorrang und kehrte damit die Kaskade um, die der HA-Zwilling
(F-49) baut, die der Snapshot-Layer über `pv_je_investition_belegt` stellt und
die das Handbuch dem Anwender zusagt (*„Sobald EIN Erzeuger einen eigenen
kWh-Zähler bekommt, zählt für Tag und Stunde nur noch, was je Erzeuger gemessen
ist"*). **Ihr Gegenstand — nie Basis PLUS Komponenten — war und bleibt richtig**
und wird unten schärfer geprüft als vorher: gegen beide falschen Ausgänge.
"""

from backend.services.mqtt_energy_history_service import _compute_deltas


def test_pro_wr_pv_wird_auf_kategorie_pv_summiert():
    """Mehrere Wechselrichter-Topics → Kategorie `pv` = Summe der Deltas."""
    end = {"inv/7/pv_erzeugung_kwh": 100.0, "inv/8/pv_erzeugung_kwh": 50.0}
    start = {"inv/7/pv_erzeugung_kwh": 90.0, "inv/8/pv_erzeugung_kwh": 45.0}
    inv_types = {"7": "wechselrichter", "8": "wechselrichter"}

    result = _compute_deltas(end, start, inv_types)

    # Komponenten-Keys bleiben für Tooltips erhalten …
    assert result["pv_7"] == 10.0
    assert result["pv_8"] == 5.0
    # … und werden zusätzlich auf die Kategorie aggregiert.
    assert result["pv"] == 15.0


def test_gemessene_einzelwerte_schlagen_das_anlagen_topic():
    """Beides da → die je Erzeuger GEMESSENEN Werte gelten, und zwar allein.

    Die Zusage aus dem Handbuch, wörtlich: „Entweder die Anlagensumme oder die
    Einzelwerte — nie beides." Geprüft werden deshalb **alle drei** möglichen
    Ausgänge, nicht nur der gewünschte:

    * 30,0 wäre die Doppelzählung (Basis + Komponenten) — der Fehler, gegen den
      die Vorgängerfassung dieser Probe gebaut war,
    * 20,0 wäre das Basis-Delta und damit die umgekehrte Kaskade (N-172),
    * 10,0 ist die Komponentensumme — dieselbe Reihenfolge wie im HA-Pfad (F-49).
    """
    end = {"pv_gesamt_kwh": 200.0, "inv/7/pv_erzeugung_kwh": 100.0}
    start = {"pv_gesamt_kwh": 180.0, "inv/7/pv_erzeugung_kwh": 90.0}
    inv_types = {"7": "wechselrichter"}

    result = _compute_deltas(end, start, inv_types)

    assert result["pv"] == 10.0
    assert result["pv"] != 30.0, "Basis + Komponenten wären die Doppelzählung"
    assert result["pv"] != 20.0, "das Basis-Delta wäre die umgekehrte Kaskade"
    assert result["pv_7"] == 10.0


def test_ohne_einzelwerte_traegt_das_anlagen_topic():
    """Die zweite Stufe der Kaskade — sonst hätte der Fix die Basis entwertet.

    Ohne diese Gegenprobe wäre nicht belegt, dass das Anlagen-Topic überhaupt
    noch etwas tut: Eine Reihenfolge, die die erste Stufe immer nimmt, sähe im
    Test oben genauso aus.
    """
    end = {"pv_gesamt_kwh": 200.0}
    start = {"pv_gesamt_kwh": 180.0}

    result = _compute_deltas(end, start, None)

    assert result["pv"] == 20.0


def test_balkonkraftwerk_zaehlt_in_pv():
    """BKW liefert ebenfalls `pv_erzeugung_kwh` → Kategorie `pv`."""
    end = {"inv/3/pv_erzeugung_kwh": 12.5}
    start = {"inv/3/pv_erzeugung_kwh": 10.0}
    inv_types = {"3": "balkonkraftwerk"}

    result = _compute_deltas(end, start, inv_types)

    assert result["pv"] == 2.5


def test_speicher_komponenten_leaken_nicht_in_pv():
    """Batterie-Lade-/Entlade-Komponenten dürfen die PV-Kategorie nicht aufblähen."""
    end = {
        "inv/7/pv_erzeugung_kwh": 100.0,
        "inv/5/ladung_kwh": 30.0,
        "inv/5/entladung_kwh": 20.0,
    }
    start = {
        "inv/7/pv_erzeugung_kwh": 90.0,
        "inv/5/ladung_kwh": 25.0,
        "inv/5/entladung_kwh": 18.0,
    }
    inv_types = {"7": "wechselrichter", "5": "speicher"}

    result = _compute_deltas(end, start, inv_types)

    assert result["pv"] == 10.0  # nur PV, keine Batterie-Beiträge
    assert result["batterie_5_ladung"] == 5.0
    assert result["batterie_5_entladung"] == 2.0


def test_kein_pv_kein_pv_key():
    """Ohne jegliche PV-Daten bleibt die Kategorie `pv` ungesetzt (kein 0,0-Artefakt)."""
    end = {"netzbezug_kwh": 50.0, "einspeisung_kwh": 30.0}
    start = {"netzbezug_kwh": 48.0, "einspeisung_kwh": 29.0}

    result = _compute_deltas(end, start, None)

    assert "pv" not in result
    assert result["netzbezug"] == 2.0
    assert result["einspeisung"] == 1.0
