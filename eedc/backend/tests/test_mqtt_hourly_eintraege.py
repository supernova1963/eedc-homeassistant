"""Unit-Tests für die MQTT-/Standalone-Normalisierung (#317).

Vor #317 hängten die beiden Snapshot-Hourly-Konsumenten ihre MQTT-Einträge mit
`fallback_gruppe=None` an — ein E-Auto, das via MQTT BEIDE Gesamt-Zähler
publiziert (`ladung_kwh` UND `verbrauch_kwh`, evcc-Bridge), wurde in der
Stunden-Bilanz doppelt gezählt (gleiche #298-Klasse, MQTT-Pfad). Der geteilte
Helfer `mqtt_hourly_eintraege` routet inv-Keys jetzt durch dieselbe
Whitelist + Either-Or + parent-Skip-Normalisierung wie der HA-Pfad.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.snapshot.komponenten_beitraege import (
    investition_beitraege,
    mqtt_hourly_eintraege,
    resolve_either_or_eintraege,
)


def _inv(inv_id, typ, parameter=None, parent_investition_id=None):
    return SimpleNamespace(
        id=inv_id,
        typ=typ,
        parameter=parameter or {},
        parent_investition_id=parent_investition_id,
    )


def _gruppe(e):
    return e[2]  # (sensor_key, kategorie, fallback_gruppe)


# ─── ist_verfuegbar-Parametrisierung (Kern des #317-Fix) ────────────────────

def test_ist_verfuegbar_ersetzt_sensor_mapping_check():
    """investition_beitraege akzeptiert ein quellen-agnostisches Prädikat —
    ohne sensor_mapping-Dict, nur 'Feld vorhanden'."""
    inv = _inv(1, "e-auto")
    vorhanden = {"ladung_kwh", "verbrauch_kwh"}
    b = investition_beitraege(inv, {}, ist_verfuegbar=lambda f: f in vorhanden)
    # N-555: Auswahl nach Quelle — die Ladung, nicht zusätzlich der Fahrverbrauch.
    assert [x.feld for x in b] == ["ladung_kwh"]


# ─── mqtt_hourly_eintraege ──────────────────────────────────────────────────

def test_eauto_doppelmapping_bekommt_either_or_gruppe():
    """#317-Kern: E-Auto mit ladung_kwh UND verbrauch_kwh per MQTT → es zählt
    genau EIN Eintrag (keine Doppelzählung).

    N-555: nicht mehr über eine Either-Or-Gruppe nach Tagesdaten, sondern über
    die Auswahl nach Quelle — die Ladung geht vor, der Fahrverbrauch wird nicht
    Kandidat (Konzept Regel 6). Die Substanz (#317: kein Doppelzählen per MQTT)
    bleibt.
    """
    inv = _inv(1, "e-auto")
    sks = ["inv:1:ladung_kwh", "inv:1:verbrauch_kwh"]
    eintraege = mqtt_hourly_eintraege(sks, {"1": inv}, {})
    assert [e[0] for e in eintraege] == ["inv:1:ladung_kwh"]


def test_eauto_doppelmapping_resolve_nimmt_nur_einen():
    """End-to-end: nach resolve_either_or_eintraege bleibt genau ein Eintrag —
    kein Doppelzählen mehr (mit Tagesdaten für beide)."""
    inv = _inv(1, "e-auto")
    sks = ["inv:1:ladung_kwh", "inv:1:verbrauch_kwh"]
    eintraege = mqtt_hourly_eintraege(sks, {"1": inv}, {})
    resolved = resolve_either_or_eintraege(
        eintraege, gruppe_fn=_gruppe, hat_tagesdaten_fn=lambda e: True
    )
    assert len(resolved) == 1
    assert resolved[0][0] == "inv:1:ladung_kwh"  # primär gewinnt


def test_eauto_parent_skip_auch_per_mqtt():
    """E-Auto mit parent-Wallbox wird auch im MQTT-Pfad übersprungen (vorher
    roh gezählt → Doppelzählung mit Wallbox-Ladung)."""
    inv = _inv(1, "e-auto", parent_investition_id=2)
    eintraege = mqtt_hourly_eintraege(["inv:1:ladung_kwh"], {"1": inv}, {})
    assert eintraege == []


def test_wallbox_nur_ladung_kwh_per_mqtt():
    """Whitelist greift auch per MQTT: ladung_pv_kwh fällt raus."""
    inv = _inv(2, "wallbox")
    sks = ["inv:2:ladung_kwh", "inv:2:ladung_pv_kwh"]
    eintraege = mqtt_hourly_eintraege(sks, {"2": inv}, {})
    assert [e[0] for e in eintraege] == ["inv:2:ladung_kwh"]
    assert eintraege[0][2] is None  # kein Either-Or für Wallbox


def test_basis_keys_ohne_gruppe():
    """Basis-Einspeisung/Netzbezug: korrekte Kategorie, keine Either-Or-Gruppe."""
    eintraege = mqtt_hourly_eintraege(
        ["basis:einspeisung", "basis:netzbezug"], {}, {}
    )
    by_key = {e[0]: e for e in eintraege}
    assert by_key["basis:einspeisung"][1] == "einspeisung"
    assert by_key["basis:netzbezug"][1] == "netzbezug"
    assert all(e[2] is None for e in eintraege)


def test_unbekannte_investition_uebersprungen():
    """inv-Key ohne passende Investition → kein Crash, kein Eintrag."""
    eintraege = mqtt_hourly_eintraege(["inv:999:ladung_kwh"], {}, {})
    assert eintraege == []


def test_mehrere_invs_unabhaengig():
    """Verschiedene Investitionen behalten getrennte Either-Or-Gruppen."""
    ea1 = _inv(1, "e-auto")
    ea2 = _inv(3, "e-auto")
    sks = [
        "inv:1:ladung_kwh", "inv:1:verbrauch_kwh",
        "inv:3:ladung_kwh", "inv:3:verbrauch_kwh",
    ]
    eintraege = mqtt_hourly_eintraege(sks, {"1": ea1, "3": ea2}, {})
    # N-555: je E-Auto genau ein Eintrag (Auswahl nach Quelle, je Auto getrennt).
    assert sorted(e[0] for e in eintraege) == ["inv:1:ladung_kwh", "inv:3:ladung_kwh"]


# ─── N-529: Reihenfolge haengt nicht am Hash-Seed ────────────────────────────

_N529_SNIPPET = """
import json, sys
from types import SimpleNamespace
from backend.services.snapshot.komponenten_beitraege import mqtt_hourly_eintraege
inv = lambda i, typ: SimpleNamespace(id=i, typ=typ, parameter={}, parent_investition_id=None)
sks = [
    "basis:pv_gesamt", "basis:einspeisung", "basis:netzbezug",
    "inv:7:ladung_kwh", "inv:7:verbrauch_kwh", "inv:3:stromverbrauch_kwh", "inv:3:strom_heizen_kwh",
    "inv:3:strom_warmwasser_kwh",
]
print(json.dumps(mqtt_hourly_eintraege(sks, {"7": inv(7, "e-auto"), "3": inv(3, "waermepumpe")}, {})))
"""


def test_n529_reihenfolge_unabhaengig_vom_hash_seed():
    """N-529: `basis_felder` war ein `set` und wurde direkt durchlaufen — Python
    randomisiert String-Hashes je Prozess, die Reaggregate-Vorschau stand nach jedem
    Neustart in anderer Zeilenfolge. Gemessen wird deshalb ÜBER Prozessgrenzen: fünf
    Interpreter mit verschiedenem PYTHONHASHSEED müssen dieselbe Liste liefern, und die
    drei Basis-Eintraege (`BASIS_ZAEHLER_FELDER`) stehen sortiert. Gegenprobe am alten
    Code (18.09.2026): fuenf Seeds lieferten vier verschiedene Folgen."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    eedc = Path(__file__).resolve().parents[2]
    ergebnisse = []
    for seed in ("1", "2", "3", "4", "5"):
        r = subprocess.run(
            [sys.executable, "-c", _N529_SNIPPET],
            cwd=eedc, capture_output=True, text=True, timeout=120,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert r.returncode == 0, r.stderr[-800:]
        ergebnisse.append(json.loads(r.stdout))
    assert all(e == ergebnisse[0] for e in ergebnisse[1:]), ergebnisse
    basis = [sk for sk, _kat, _grp in ergebnisse[0] if sk.startswith("basis:")]
    assert basis == sorted(basis), basis
    assert len(basis) == 3, basis

