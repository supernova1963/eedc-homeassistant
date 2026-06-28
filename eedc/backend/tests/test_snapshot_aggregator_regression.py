"""
Regression-Tests für `get_komponenten_tageskwh` (Snapshot-Variante) nach
dem v3.33.0 Helper-Refactoring (Issue #290).

Der Symmetrie-Test (`test_aggregator_symmetrie.py`) prüft Snapshot vs LTS,
fängt aber nicht ab, wenn das Refactoring beide Pfade gleichermaßen
brechen würde. Diese Tests fixieren das alte (semantisch korrekte) Verhalten
der Snapshot-Variante explizit gegen die in der Drift-Matrix dokumentierten
Erwartungen.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.services.snapshot.aggregator import get_komponenten_tageskwh


def _make_anlage(sensor_mapping: dict):
    return SimpleNamespace(
        id=1, anlagenname="Reg", leistung_kwp=10.0, sensor_mapping=sensor_mapping,
    )


def _make_inv(inv_id, typ, parameter=None, parent_investition_id=None):
    return SimpleNamespace(
        id=inv_id, anlage_id=1, typ=typ,
        parameter=parameter or {},
        parent_investition_id=parent_investition_id,
    )


def _sensor(sid):
    return {"strategie": "sensor", "sensor_id": sid}


def _snap_for_sums(sensor_key_to_tagessumme: dict[str, float], datum: date):
    """Mock `get_snapshot`: snap(0) = 0, snap(Folgetag) = tagessumme."""
    async def fake(db, anlage_id, sensor_key, sensor_id, zeitpunkt, *a, **kw):
        if sensor_key not in sensor_key_to_tagessumme:
            return None
        if zeitpunkt.date() <= datum:
            return 0.0
        return sensor_key_to_tagessumme[sensor_key]
    return fake


@pytest.mark.asyncio
async def test_speicher_nur_ladung_gemappt_liefert_signed_negativ():
    """Spalten-Konvention (Entladung positiv): nur-Ladung → NEGATIV (Senke).
    SoT core.berechnungen.batterie_kw_spalte."""
    sm = {"basis": {}, "investitionen": {
        "5": {"felder": {"ladung_kwh": _sensor("sensor.lade")}},
    }}
    datum = date(2026, 5, 22)
    snaps = {"inv:5:ladung_kwh": 3.5}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"5": _make_inv(5, "speicher")},
            datum=datum,
        )
    assert "batterie_5" in result
    assert abs(result["batterie_5"] - (-3.5)) < 0.001  # Ladung → Senke (negativ)


@pytest.mark.asyncio
async def test_speicher_nur_entladung_gemappt_liefert_signed_positiv():
    """Spalten-Konvention (Entladung positiv): nur-Entladung → POSITIV (Quelle)."""
    sm = {"basis": {}, "investitionen": {
        "5": {"felder": {"entladung_kwh": _sensor("sensor.ent")}},
    }}
    datum = date(2026, 5, 22)
    snaps = {"inv:5:entladung_kwh": 2.1}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"5": _make_inv(5, "speicher")},
            datum=datum,
        )
    assert "batterie_5" in result
    assert abs(result["batterie_5"] - 2.1) < 0.001  # Entladung → Quelle (positiv)


@pytest.mark.asyncio
async def test_wallbox_ladung_pv_netz_im_mapping_werden_ignoriert():
    """Gernot-Bug: vorher addiert, jetzt nur ladung_kwh."""
    sm = {"basis": {}, "investitionen": {
        "2": {"felder": {
            "ladung_kwh": _sensor("sensor.wb"),
            "ladung_pv_kwh": _sensor("sensor.wb_pv"),
            "ladung_netz_kwh": _sensor("sensor.wb_netz"),
        }},
    }}
    datum = date(2026, 5, 22)
    snaps = {
        "inv:2:ladung_kwh": 14.0,
        "inv:2:ladung_pv_kwh": 9.24,  # darf nicht aufaddiert werden
        "inv:2:ladung_netz_kwh": 4.76,  # darf nicht aufaddiert werden
    }
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"2": _make_inv(2, "wallbox")},
            datum=datum,
        )
    assert "wallbox_2" in result
    assert abs(result["wallbox_2"] - 14.0) < 0.001


@pytest.mark.asyncio
async def test_eauto_ohne_ladung_kwh_fallback_auf_verbrauch():
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {
            "verbrauch_kwh": _sensor("sensor.ea_v"),
        }},
    }}
    datum = date(2026, 5, 22)
    snaps = {"inv:1:verbrauch_kwh": 19.2}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"1": _make_inv(1, "e-auto")},
            datum=datum,
        )
    assert "eauto_1" in result
    assert abs(result["eauto_1"] - 19.2) < 0.001


@pytest.mark.asyncio
async def test_eauto_ladung_kwh_gewinnt_ueber_verbrauch():
    """Beide gemappt → primary (ladung_kwh) gewinnt, verbrauch_kwh ignoriert."""
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {
            "ladung_kwh": _sensor("sensor.ea_l"),
            "verbrauch_kwh": _sensor("sensor.ea_v"),
        }},
    }}
    datum = date(2026, 5, 22)
    snaps = {"inv:1:ladung_kwh": 24.0, "inv:1:verbrauch_kwh": 19.2}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"1": _make_inv(1, "e-auto")},
            datum=datum,
        )
    assert abs(result["eauto_1"] - 24.0) < 0.001


@pytest.mark.asyncio
async def test_eauto_mit_parent_wallbox_skipped():
    """Parent gesetzt → kein eauto_X-Eintrag (Wallbox misst es schon)."""
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {"ladung_kwh": _sensor("sensor.ea")}},
    }}
    datum = date(2026, 5, 22)
    snaps = {"inv:1:ladung_kwh": 50.0}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={
                "1": _make_inv(1, "e-auto", parent_investition_id=2),
            },
            datum=datum,
        )
    assert "eauto_1" not in result


@pytest.mark.asyncio
async def test_wp_getrennte_strommessung_summiert_heiz_plus_ww():
    sm = {"basis": {}, "investitionen": {
        "7": {"felder": {
            "strom_heizen_kwh": _sensor("sensor.h"),
            "strom_warmwasser_kwh": _sensor("sensor.ww"),
            "stromverbrauch_kwh": _sensor("sensor.gesamt"),  # ignoriert
        }},
    }}
    datum = date(2026, 5, 22)
    snaps = {
        "inv:7:strom_heizen_kwh": 4.8,
        "inv:7:strom_warmwasser_kwh": 2.4,
        "inv:7:stromverbrauch_kwh": 99.0,  # darf nicht zählen
    }
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={
                "7": _make_inv(7, "waermepumpe",
                               parameter={"getrennte_strommessung": True}),
            },
            datum=datum,
        )
    assert abs(result["waermepumpe_7"] - 7.2) < 0.001


@pytest.mark.asyncio
async def test_wp_thermisch_gemappt_aber_nicht_summiert():
    """detLAN-Bug-Klasse: thermische Felder dürfen NIE in komponenten_kwh."""
    sm = {"basis": {}, "investitionen": {
        "7": {"felder": {
            "stromverbrauch_kwh": _sensor("sensor.strom"),
            "heizenergie_kwh": _sensor("sensor.thermisch_h"),
            "warmwasser_kwh": _sensor("sensor.thermisch_ww"),
        }},
    }}
    datum = date(2026, 5, 22)
    snaps = {
        "inv:7:stromverbrauch_kwh": 9.6,
        "inv:7:heizenergie_kwh": 28.0,
        "inv:7:warmwasser_kwh": 12.0,
    }
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"7": _make_inv(7, "waermepumpe")},
            datum=datum,
        )
    assert abs(result["waermepumpe_7"] - 9.6) < 0.001


@pytest.mark.asyncio
async def test_sonstiges_immer_positiv_unabhaengig_von_kategorie():
    """Snapshot hat schon immer +1 geliefert — egal ob Verbraucher oder Erzeuger."""
    sm = {"basis": {}, "investitionen": {
        "13": {"felder": {"verbrauch_kwh": _sensor("sensor.pool")}},
    }}
    datum = date(2026, 5, 22)
    snaps = {"inv:13:verbrauch_kwh": 4.8}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={
                "13": _make_inv(13, "sonstiges",
                                parameter={"kategorie": "verbraucher"}),
            },
            datum=datum,
        )
    # +4.8, NICHT -4.8
    assert abs(result["sonstige_13"] - 4.8) < 0.001


@pytest.mark.asyncio
async def test_basis_einspeisung_und_netzbezug():
    sm = {"basis": {
        "einspeisung": _sensor("sensor.einsp"),
        "netzbezug": _sensor("sensor.bezug"),
    }, "investitionen": {}}
    datum = date(2026, 5, 22)
    snaps = {"basis:einspeisung": 36.0, "basis:netzbezug": 9.6}
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums(snaps, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={}, datum=datum,
        )
    assert abs(result["einspeisung"] - 36.0) < 0.001
    assert abs(result["netzbezug"] - 9.6) < 0.001


@pytest.mark.asyncio
async def test_kein_eintrag_wenn_delta_none():
    """Sensor gemappt, aber Snapshot liefert None → kein Eintrag im Result."""
    sm = {"basis": {}, "investitionen": {
        "3": {"felder": {"pv_erzeugung_kwh": _sensor("sensor.pv")}},
    }}
    datum = date(2026, 5, 22)
    # snaps leer → fake_get_snapshot liefert None
    with patch("backend.services.snapshot.aggregator.get_snapshot",
               side_effect=_snap_for_sums({}, datum)):
        result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=_make_anlage(sm),
            investitionen_by_id={"3": _make_inv(3, "pv-module")},
            datum=datum,
        )
    assert "pv_3" not in result
