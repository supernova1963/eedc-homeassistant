"""
Akzeptanztest N-58 — die Tages-Reparatur sagt, für welche Komponente sie nichts
schreiben konnte.

`POST /reaggregate-tag` antwortete unbedingt mit `{"status": "ok", …}`. Der
Status ist der Transport-Status und heißt nur „durchgelaufen"; ob der Lauf für
eine Komponente etwas geholt hat, stand nirgends. Der Client baute daraus eine
reine PV-Meldung — eine Wärmepumpe ohne geschriebenen Wert war davon nicht
unterscheidbar, solange die PV sich bewegt hatte (Forum simon42 #89667/83,
dietmar1968).

Der Kanon steht schon im Baum: der Bereichs-Pfad wertet `erfolgreich` /
`keine_daten` / `fehlgeschlagen` aus (`baueBereichsMeldung`). Hier dieselbe
Linie je Komponente — Erwartung aus `erwartete_komponenten_keys` (dieselbe Menge
wie im Daten-Checker), Ergebnis aus der `komponenten_kwh` des Laufs selbst.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_reaggregate_tag_komponenten_rueckmeldung.py

Testet:
  1. Alles geschrieben → nichts zu beklagen
  2. Wärmepumpe ohne Wert → sie wird namentlich genannt
  3. Preserve-Lauf (keine frischen Werte) → „nichts geschrieben", trotz Keys
  4. Am Tag inaktive Komponente wird gar nicht erst erwartet (Symmetrie zu N-57)
  5. Der transiente Marker lässt sich am echten ORM-Objekt setzen
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.models.investition import Investition  # noqa: E402
from backend.services.repair_orchestrator import _komponenten_rueckmeldung  # noqa: E402

_SENSOR = {"strategie": "sensor", "sensor_id": "sensor.x"}
_TAG = date.today() - timedelta(days=3)


def _anlage(*, wp_ids=(8,)):
    investitionen = {"7": {"felder": {"pv_erzeugung_kwh": dict(_SENSOR)}}}
    for wp_id in wp_ids:
        investitionen[str(wp_id)] = {"felder": {"stromverbrauch_kwh": dict(_SENSOR)}}
    return SimpleNamespace(
        id=1,
        sensor_mapping={
            "basis": {"einspeisung": dict(_SENSOR)},
            "investitionen": investitionen,
        },
    )


def _inv(inv_id, typ, bezeichnung, **kwargs):
    return Investition(
        id=inv_id, anlage_id=1, typ=typ, parameter={},
        bezeichnung=bezeichnung, parent_investition_id=None, **kwargs,
    )


def _db(invs):
    db = MagicMock()

    async def _execute(_stmt):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=invs)
        result.scalars = MagicMock(return_value=scalars)
        return result

    db.execute = _execute
    return db


def _lauf(komponenten_kwh, *, frisch=True):
    """Das, was `aggregate_day` zurückgibt — Ergebnisseite, keine Ableitung."""
    return SimpleNamespace(komponenten_kwh=komponenten_kwh, komponenten_frisch=frisch)


_INVS = [
    _inv(7, "pv-module", "Dach Süd"),
    _inv(8, "waermepumpe", "Wärmepumpe"),
]


async def test_alles_geschrieben():
    """Jede erwartete Komponente trägt einen Wert → nichts zu beklagen."""
    out = await _komponenten_rueckmeldung(
        _db(_INVS), _anlage(), _TAG,
        _lauf({"einspeisung": 12.0, "pv_7": 30.0, "waermepumpe_8": 6.0}),
    )
    assert out["komponenten_erwartet"] == 3, out
    assert out["komponenten_geschrieben"] == 3, out
    assert out["komponenten_ohne_wert"] == [], out
    assert {k["name"] for k in out["komponenten"]} == {
        "Einspeisung", "Dach Süd", "Wärmepumpe",
    }, out["komponenten"]


async def test_waermepumpe_ohne_wert_wird_genannt():
    """Der Fall, der bisher unsichtbar blieb: PV bewegt sich, die WP nicht.

    0,0 kWh ist ausdrücklich ein GESCHRIEBENER Wert — nicht geschrieben heißt,
    der Lauf hat für den Key gar nichts hinterlassen.
    """
    out = await _komponenten_rueckmeldung(
        _db(_INVS), _anlage(), _TAG,
        _lauf({"einspeisung": 0.0, "pv_7": 30.0}),
    )
    assert out["komponenten_ohne_wert"] == ["Wärmepumpe"], out
    assert out["komponenten_geschrieben"] == 2, out
    wp = [k for k in out["komponenten"] if k["key"] == "waermepumpe_8"][0]
    assert wp["geschrieben"] is False and wp["kwh"] is None, wp
    einsp = [k for k in out["komponenten"] if k["key"] == "einspeisung"][0]
    assert einsp["geschrieben"] is True and einsp["kwh"] == 0.0, einsp


async def test_preserve_lauf_hat_nichts_geschrieben():
    """Preserve-Logik: die alten Werte bleiben stehen, geschrieben wurde nichts.

    Von außen trägt `komponenten_kwh` dieselben Keys wie bei einem echten Lauf —
    ohne den Marker aus dem Lauf meldete die Reparatur hier vollen Erfolg.
    """
    out = await _komponenten_rueckmeldung(
        _db(_INVS), _anlage(), _TAG,
        _lauf({"einspeisung": 12.0, "pv_7": 30.0, "waermepumpe_8": 6.0}, frisch=False),
    )
    assert out["komponenten_geschrieben"] == 0, out
    assert len(out["komponenten_ohne_wert"]) == 3, out


async def test_am_tag_inaktive_komponente_wird_nicht_erwartet():
    """Symmetrie zu N-57: was der Lauf nicht anfasst, wird nicht eingefordert.

    Sonst meldete die Reparatur „für die Klimaanlage nichts geschrieben" für
    eine Komponente, die es an diesem Tag noch gar nicht gab — dieselbe falsche
    Erwartung, nur eine Meldung weiter.
    """
    invs = [
        _inv(7, "pv-module", "Dach Süd"),
        _inv(8, "waermepumpe", "Klimaanlage",
             anschaffungsdatum=date.today() + timedelta(days=1)),
    ]
    out = await _komponenten_rueckmeldung(
        _db(invs), _anlage(), _TAG,
        _lauf({"einspeisung": 12.0, "pv_7": 30.0}),
    )
    assert out["komponenten_erwartet"] == 2, out
    assert out["komponenten_ohne_wert"] == [], out


async def test_marker_am_orm_objekt_setzbar():
    """Der Marker ist transient (nicht gemappt) — das muss am echten Model gehen."""
    from backend.models.tages_energie_profil import TagesZusammenfassung

    tz = TagesZusammenfassung(anlage_id=1, datum=_TAG)
    tz.komponenten_frisch = False
    assert getattr(tz, "komponenten_frisch") is False
    # Default für Aufrufer, die den Marker nicht kennen (Altbestand/Doubles).
    tz2 = TagesZusammenfassung(anlage_id=1, datum=_TAG)
    assert getattr(tz2, "komponenten_frisch", True) is True
