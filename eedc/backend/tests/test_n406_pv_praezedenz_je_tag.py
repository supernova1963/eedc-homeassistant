"""Die Monatspräzedenz auf der Stunden-/Tagesebene (#406, Mathek).

**Der Fall.** Er ordnet um 22:00 seinen String-Zählern Sensoren zu, die in HA
erst ab 21:00 liefern. Ab dem Speichern galt für den ganzen Tag „ein Erzeuger
hat einen eigenen Zähler" ⇒ das Anlagen-Aggregat `basis:pv_gesamt` wurde
verdrängt, und weil der laufende Tag alle 15 Minuten neu gerechnet wird,
rückwirkend bis 00:00. **21 Stunden gemessene PV waren weg.**

**Der größere Schaden ist der gemischte Fall:** String A mit Zähler, String B
ohne. Das Aggregat war verdrängt, die Anlagensumme dauerhaft nur A.

Beides hatte dieselbe Ursache: die Bedingung fragte die **Zuordnung**
(`sensor_mapping`), nicht die **Daten**. Seit #406 fällt die Wahl nach dem Lesen
und **je Tag** — `core/berechnungen/pv_tages_praezedenz.py`.

⛔ **Was diese Datei NICHT prüft:** eine slotweise Wahl. Sie ist bewusst nicht
gebaut (Entscheid Gernot 2026-09-04): der Snapshot-Tagespfad ist EIN
Boundary-Diff über das HA-Tagesfenster, der Stundenpfad 24 Deltas über das
Rückwärtsfenster — eine gemischte Quelle innerhalb eines Tages bräuchte eine
Slot-Maske und ließe beide Fenster auseinanderlaufen. Die Monatsregel wählt
ebenfalls je Periode, nicht je Teilintervall.

Die Doppelzähl-Abgrenzung (#290/#298) steht in
`test_pv_anlagenzaehler_tagesebene_stufe1.py` — sie gilt unverändert weiter und
wird hier an der Bilanz nachgezogen.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.core.berechnungen.pv_tages_praezedenz import (
    QUELLE_AGGREGAT,
    QUELLE_EINZEL,
    QUELLE_KEINE,
    erwartete_erzeuger_ids,
    waehle_pv_quelle,
)
from backend.services.snapshot.aggregator import get_hourly_kwh_by_category
from backend.services.snapshot.komponenten_beitraege import loese_pv_tageswerte_auf

_DATUM = date(2026, 5, 22)


def _inv(inv_id: int, typ: str = "pv-module", kwp: float | None = None, **kw):
    """Attrappe mit der ECHTEN `ist_aktiv_an` des Modells.

    Gebunden statt nachgebaut: ein `lambda: True` verdeckte genau den
    Lebenszyklus-Filter, den `erwartete_erzeuger_ids` braucht.
    """
    from backend.models.investition import Investition

    ns = SimpleNamespace(
        id=inv_id, anlage_id=1, typ=typ, parameter={},
        parent_investition_id=None, leistung_kwp=kwp,
        aktiv=True, anschaffungsdatum=None, stilllegungsdatum=None,
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    ns.ist_aktiv_an = Investition.ist_aktiv_an.__get__(ns)
    return ns


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _mapping(*inv_ids: int) -> dict:
    """Anlagen-Aggregat an der Basis, `inv_ids` mit eigenem PV-Zähler."""
    return {
        "basis": {
            "pv_gesamt": _sensor("sensor.anlage_kwh"),
            "einspeisung": _sensor("sensor.einsp"),
        },
        "investitionen": {
            str(i): {"felder": {"pv_erzeugung_kwh": _sensor(f"sensor.string{i}")}}
            for i in inv_ids
        },
    }


def _db():
    result = MagicMock()
    result.all.return_value = []

    async def _execute(*a, **k):
        return result

    db = MagicMock()
    db.execute = _execute
    return db


def _snapshots(tageswerte: dict[str, float], ab_slot: dict[str, int] | None = None):
    """Linear steigende Zähler; `ab_slot` lässt einen Zähler später einsetzen.

    Backward-Konvention (#144): Slot h ist `snap[h] − snap[h−1]`, die Boundaries
    laufen von Offset −1 (Vortag 23:00) bis 23. `ab_slot[key] = 22` heißt: vor
    Boundary 21 gibt es den Sensor nicht — genau Matheks Wechseltag.
    """
    tag0 = datetime.combine(_DATUM, datetime.min.time())
    ab_slot = ab_slot or {}

    async def fake_get_snapshot(db, anlage_id, sensor_key, sensor_id, zeitpunkt, *a, **k):
        tageswert = tageswerte.get(sensor_key)
        if tageswert is None:
            return None
        o = round((zeitpunkt - tag0).total_seconds() / 3600.0)
        start = ab_slot.get(sensor_key)
        if start is not None and o < start - 1:
            return None
        return max(0.0, min(24.0, o + 1.0)) / 24.0 * tageswert

    return fake_get_snapshot


# ─── Der Layer-SoT: die Wahl selbst ────────────────────────────────────────

def test_wahl_matheks_wechseltag():
    """Zähler zugeordnet, liefern aber erst ab Slot 22 ⇒ das Aggregat trägt."""
    quelle = waehle_pv_quelle(
        erwartete_ids={"1", "2"},
        gedeckte_ids_je_slot={h: (set() if h < 22 else {"1", "2"}) for h in range(24)},
        aggregat_je_slot={h: 1.0 for h in range(24)},
    )
    assert quelle == QUELLE_AGGREGAT


def test_wahl_gemischt_dauerhaft():
    """String B hat NIE einen Zähler ⇒ das Aggregat trägt, nicht die Teilsumme."""
    quelle = waehle_pv_quelle(
        erwartete_ids={"1", "2"},
        gedeckte_ids_je_slot={h: {"1"} for h in range(24)},
        aggregat_je_slot={h: 1.0 for h in range(24)},
    )
    assert quelle == QUELLE_AGGREGAT


def test_wahl_vollstaendig_gemessen_schlaegt_das_aggregat():
    """Der Normalfall — und die Zusicherung „nichts wird schlimmer"."""
    quelle = waehle_pv_quelle(
        erwartete_ids={"1", "2"},
        gedeckte_ids_je_slot={h: {"1", "2"} for h in range(24)},
        aggregat_je_slot={h: 1.0 for h in range(24)},
    )
    assert quelle == QUELLE_EINZEL


def test_wahl_ohne_aggregat_bleibt_bei_den_einzelzaehlern():
    """Ohne Anlagen-Zähler gibt es nichts Besseres als die Teilsumme.

    Die Stelle, an der die neue Regel NICHTS verschlechtert: eine Anlage ohne
    Aggregat verhält sich exakt wie vor #406.
    """
    quelle = waehle_pv_quelle(
        erwartete_ids={"1", "2"},
        gedeckte_ids_je_slot={h: {"1"} for h in range(24)},
        aggregat_je_slot={h: None for h in range(24)},
    )
    assert quelle == QUELLE_EINZEL


def test_wahl_ohne_jede_quelle():
    assert waehle_pv_quelle(
        erwartete_ids={"1"},
        gedeckte_ids_je_slot={h: set() for h in range(24)},
        aggregat_je_slot={h: None for h in range(24)},
    ) == QUELLE_KEINE


def test_stillgelegter_erzeuger_erzwingt_nicht_das_aggregat():
    """Ein am Stichtag stillgelegter String ist keine Lücke.

    Ohne den Lebenszyklus-Filter zählte er als „erwartet, liefert nicht" — und
    die Anlage fiele dauerhaft auf das Aggregat zurück, obwohl der aktive Teil
    vollständig misst.
    """
    tot = _inv(2, stilllegungsdatum=date(2026, 1, 1))
    assert erwartete_erzeuger_ids([_inv(1), tot], _DATUM) == {"1"}


# ─── Stundenpfad: Ende zu Ende durch den Aggregator ────────────────────────

async def test_matheks_tag_hat_keine_leere_stunde():
    """Der gemeldete Schaden: 21 Stunden PV, die es gab, standen auf None."""
    anlage = SimpleNamespace(id=1, sensor_mapping=_mapping(1))
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        _snapshots(
            {"basis:pv_gesamt": 24.0, "inv:1:pv_erzeugung_kwh": 2.0},
            ab_slot={"inv:1:pv_erzeugung_kwh": 22},
        ),
    ):
        hourly = await get_hourly_kwh_by_category(
            _db(), anlage, {"1": _inv(1)}, _DATUM,
        )

    assert all(hourly[h].get("pv") is not None for h in range(24))
    assert sum(hourly[h]["pv"] for h in range(24)) == pytest.approx(24.0)


async def test_gemischter_fall_nimmt_das_aggregat_statt_der_teilsumme():
    """String A misst, String B hat gar keinen Zähler.

    Vor #406 stand hier die Erzeugung von A als Anlagensumme — dauerhaft zu
    klein, und nichts sagte es.
    """
    anlage = SimpleNamespace(id=1, sensor_mapping=_mapping(1))
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        _snapshots({"basis:pv_gesamt": 24.0, "inv:1:pv_erzeugung_kwh": 10.0}),
    ):
        hourly = await get_hourly_kwh_by_category(
            _db(), anlage, {"1": _inv(1), "2": _inv(2)}, _DATUM,
        )

    assert sum(hourly[h].get("pv") or 0.0 for h in range(24)) == pytest.approx(24.0)


async def test_vollstaendig_gemessen_bleibt_bei_den_zaehlern():
    """Gegenprobe zur vorigen: messen ALLE Erzeuger, bleibt alles wie bisher —
    das Aggregat zählt nicht mit, obwohl es zugeordnet ist."""
    anlage = SimpleNamespace(id=1, sensor_mapping=_mapping(1, 2))
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        _snapshots({
            "basis:pv_gesamt": 24.0,
            "inv:1:pv_erzeugung_kwh": 10.0,
            "inv:2:pv_erzeugung_kwh": 8.0,
        }),
    ):
        hourly = await get_hourly_kwh_by_category(
            _db(), anlage, {"1": _inv(1), "2": _inv(2)}, _DATUM,
        )

    assert sum(hourly[h].get("pv") or 0.0 for h in range(24)) == pytest.approx(18.0)


# ─── Tagesebene: die Auflösung je Modul ────────────────────────────────────

def test_tagesebene_loest_das_aggregat_in_die_module_auf():
    """(b) — die Entsprechung der Monatsverteilung.

    Σ der geschriebenen Keys == Aggregat, das gemessene Modul behält seinen
    Wert, und `pv_gesamt` steht **nicht** daneben (#290/#298).
    """
    komponenten = {"einspeisung": 6.0, "pv_gesamt": 24.0, "pv_1": 10.0}
    invs = {"1": _inv(1, kwp=6.0), "2": _inv(2, kwp=2.0)}

    out, marken = loese_pv_tageswerte_auf(komponenten, invs, _DATUM)

    assert "pv_gesamt" not in out
    assert out["pv_1"] == pytest.approx(10.0)     # gemessen, unangetastet
    assert out["pv_2"] == pytest.approx(14.0)     # Rest, kWp-gewichtet (allein)
    assert out["pv_1"] + out["pv_2"] == pytest.approx(24.0)
    assert out["einspeisung"] == 6.0              # fremde Keys unberührt


def test_tagesebene_markiert_den_verteilten_wert_als_abgeleitet():
    """Herkunft: eine Zerlegung ist keine Messung (#352-Marke)."""
    from backend.services.provenance import ABGELEITET_KWP_ANTEIL

    _out, marken = loese_pv_tageswerte_auf(
        {"pv_gesamt": 24.0, "pv_1": 10.0},
        {"1": _inv(1, kwp=6.0), "2": _inv(2, kwp=2.0)},
        _DATUM,
    )
    assert marken == {"pv_2": ABGELEITET_KWP_ANTEIL}


def test_tagesebene_laesst_vollstaendig_gemessene_tage_unveraendert():
    """„Nichts wird schlimmer" auf der Tagesebene — bis auf das Aggregat, das
    dort noch nie stehen durfte."""
    komponenten = {"pv_gesamt": 24.0, "pv_1": 10.0, "pv_2": 8.0}
    invs = {"1": _inv(1, kwp=6.0), "2": _inv(2, kwp=2.0)}

    out, marken = loese_pv_tageswerte_auf(komponenten, invs, _DATUM)

    assert out == {"pv_1": 10.0, "pv_2": 8.0}
    assert marken == {}


def test_balkonkraftwerk_bekommt_seinen_eigenen_praefix():
    """Ein BKW trägt `bkw_<id>`, kein `pv_<id>` — sonst zählte
    `summe_bkw_kwh` es nicht und `summe_pv_anlage_kwh` doppelt."""
    out, _marken = loese_pv_tageswerte_auf(
        {"pv_gesamt": 12.0},
        {"1": _inv(1, kwp=3.0), "2": _inv(2, typ="balkonkraftwerk", kwp=1.0)},
        _DATUM,
    )
    assert set(out) == {"pv_1", "bkw_2"}
    assert out["pv_1"] + out["bkw_2"] == pytest.approx(12.0)
