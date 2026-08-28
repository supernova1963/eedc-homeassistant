"""N-201, zweite Hälfte: der Drift-Check vergleicht auch alles, was keine PV ist.

**Der Befund.** ``_check_datenquelle_drift`` filterte seine Vergleichsmenge auf
``PV_KOMPONENTEN_PREFIXE`` (``pv_``, ``bkw_``). Wallbox, E-Auto, Wärmepumpe und
Sonstiges wurden damit **nie** gegen HA-Statistics verglichen — obwohl ihre
Werte die Wirtschaftlichkeits- und CO₂-Rechnung tragen. Die Begründung im
Docstring lautete „andere Größen koppeln meistens mit" und war nie gemessen.

**Warum je Komponente und nicht als zweite Summe.** In einer gemeinsamen Summe
gliche ein Plus an der Wärmepumpe ein Minus an der Wallbox aus, und übrig
bliebe eine unauffällige Null. Die PV-Summe ist eine Summe, weil mehrere
Strings dieselbe Sache messen; zwei Geräte tun das nicht.

**Drei Abgrenzungen, jede gegen einen bestehenden Turm** — sie sind hier je
einzeln geprüft:

* ``batterie_*`` bleibt draußen (eigene Prüfung fürs Vorzeichen).
* Ein Key, den nur eine Seite trägt, ist eine **Lücke** und gehört
  ``_check_leere_tage_trotz_zaehler`` (TAGESWERTE_FEHLEN).
* Ein Key, den der LTS-Read gar nicht liefert, ist „nicht gelesen", nie „= 0"
  (#311) — die PV-Achse hält das seit jeher, die zweite Achse ebenso.

Schwesterdateien: ``test_etappe_6_drift_check.py`` (die PV-Achse derselben
Prüfung, inklusive der #311-Fälle), ``test_n201_ladung_pv_ueber_gesamt.py``
(die andere Hälfte desselben Funds) und
``test_daten_checker_leere_tage_trotz_zaehler.py`` (die Lücken-Prüfung, gegen
die hier abgegrenzt wird).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from backend.models.investition import Investition
from backend.services.daten_checker import DatenChecker, CheckKategorie

_KAT = CheckKategorie.DATENQUELLE_DRIFT.value


def _anlage():
    return SimpleNamespace(id=1, sensor_mapping={
        "investitionen": {
            "3": {"felder": {"pv_erzeugung_kwh": {
                "strategie": "sensor", "sensor_id": "sensor.pv"}}},
            "7": {"felder": {"ladung_kwh": {
                "strategie": "sensor", "sensor_id": "sensor.wb"}}},
        },
    })


def _inv(inv_id, typ, bezeichnung=None):
    return Investition(
        id=inv_id, anlage_id=1, typ=typ, parameter={}, aktiv=True,
        bezeichnung=bezeichnung, anschaffungsdatum=None, stilllegungsdatum=None,
    )


def _tz(datum, komponenten):
    return SimpleNamespace(id=1, anlage_id=1, datum=datum,
                           komponenten_kwh=dict(komponenten))


async def _run(tz_list, invs, ha_func):
    db = MagicMock()
    ruf = {"n": 0}

    async def _execute(_stmt):
        ruf["n"] += 1
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=tz_list if ruf["n"] == 1 else invs)
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)
        return result

    db.execute = _execute
    ha_svc = MagicMock()
    ha_svc.is_available = True

    async def _lts(_a, _i, datum):
        return ha_func(datum)

    with patch(
        "backend.services.ha_statistics_service.get_ha_statistics_service",
        return_value=ha_svc,
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        side_effect=_lts,
    ):
        return await DatenChecker(db)._check_datenquelle_drift(_anlage())


#: Feste Daten statt Prozessuhr (N-167) — das 90-Tage-Fenster der Prüfung
#: steckt allein in der DB-Abfrage, und die ist hier ein Double.
_TAGE = [date(2026, 6, 15) - timedelta(days=i) for i in range(5)]


async def test_wallbox_drift_wird_gemeldet_und_beim_namen_genannt():
    """Die PV stimmt, die Wallbox nicht — genau der Fall, der nie auffiel."""
    tz_list = [_tz(d, {"pv_3": 30.0, "wallbox_7": 12.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0, "wallbox_7": 18.0}

    ergebnisse = await _run(
        tz_list, [_inv(3, "pv-module"), _inv(7, "wallbox", "Wallbox Garage")], ha_func,
    )

    treffer = [e for e in ergebnisse if "Wallbox Garage" in e.meldung]
    assert len(treffer) == 1, (
        "Erwartet genau EINEN Eintrag je Komponente, bekommen "
        f"{[e.meldung for e in ergebnisse]}"
    )
    e = treffer[0]
    assert e.kategorie == _KAT
    assert "5 Tag(e)" in e.meldung, e.meldung
    assert e.action_kind == "reaggregate_day"
    assert e.investition_id == 7, "Der Befund gehört an sein Gerät."
    # Die PV-Achse bleibt still — sie stimmt ja.
    assert not any("PV" in x.meldung for x in ergebnisse), [x.meldung for x in ergebnisse]


async def test_ohne_abweichung_meldet_die_ok_zeile_beide_achsen():
    """Gegenrichtung: stimmt alles, steht eine OK-Zeile da — und sie sagt,
    dass mehr als die PV geprüft wurde. Der alte Text behauptete „PV-Tagessumme"
    und deckte die Lücke damit sprachlich zu."""
    tz_list = [_tz(d, {"pv_3": 30.0, "wallbox_7": 12.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0, "wallbox_7": 12.0}

    ergebnisse = await _run(
        tz_list, [_inv(3, "pv-module"), _inv(7, "wallbox", "Wallbox Garage")], ha_func,
    )
    assert len(ergebnisse) == 1 and ergebnisse[0].schwere == "ok", ergebnisse
    assert "Komponente" in ergebnisse[0].details


async def test_batterie_bleibt_der_vorzeichen_pruefung_ueberlassen():
    """`batterie_*` darf hier nie auftauchen — sonst zwei Türme auf einem Fall."""
    tz_list = [_tz(d, {"pv_3": 30.0, "batterie_9": 4.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0, "batterie_9": 14.0}

    ergebnisse = await _run(
        tz_list, [_inv(3, "pv-module"), _inv(9, "speicher", "Hausakku")], ha_func,
    )
    assert len(ergebnisse) == 1 and ergebnisse[0].schwere == "ok", (
        f"Speicher gehört nicht in den Drift-Check: {[e.meldung for e in ergebnisse]}"
    )


async def test_fehlender_wert_auf_einer_seite_ist_eine_luecke_keine_drift():
    """HA liefert die Wallbox, die gespeicherte Zeile nicht → TAGESWERTE_FEHLEN,
    nicht hier. Sonst meldeten zwei Prüfungen denselben Tag."""
    tz_list = [_tz(d, {"pv_3": 30.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0, "wallbox_7": 18.0}

    ergebnisse = await _run(
        tz_list, [_inv(3, "pv-module"), _inv(7, "wallbox", "Wallbox Garage")], ha_func,
    )
    assert len(ergebnisse) == 1 and ergebnisse[0].schwere == "ok", ergebnisse


async def test_nicht_gelesen_ist_nicht_null_auch_auf_der_zweiten_achse():
    """#311 in der zweiten Achse: liefert der LTS-Read den Key gar nicht,
    ist das „nicht gelesen" — und kein −100-%-Phantom mit Reparatur-Knopf."""
    tz_list = [_tz(d, {"pv_3": 30.0, "waermepumpe_5": 22.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0}  # WP-Sensor ohne has_sum

    ergebnisse = await _run(
        tz_list, [_inv(3, "pv-module"), _inv(5, "waermepumpe", "Vitocal")], ha_func,
    )
    assert len(ergebnisse) == 1 and ergebnisse[0].schwere == "ok", ergebnisse
    assert not any(e.action_kind == "reaggregate_day" for e in ergebnisse)


async def test_kleine_abweichung_bleibt_unter_der_schwelle():
    """Dieselben Schwellen wie auf der PV-Achse: ≥ 2 kWh UND ≥ 5 %."""
    tz_list = [_tz(d, {"pv_3": 30.0, "wallbox_7": 40.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0, "wallbox_7": 41.5}  # 1,5 kWh / 3,6 %

    ergebnisse = await _run(
        tz_list, [_inv(3, "pv-module"), _inv(7, "wallbox", "Wallbox Garage")], ha_func,
    )
    assert len(ergebnisse) == 1 and ergebnisse[0].schwere == "ok", ergebnisse


async def test_basiszaehler_zaehlen_mit():
    """Einspeisung und Netzbezug sind keine Komponente — aber sie tragen die
    Bilanz. Sie aus einer Deckungsprüfung auszunehmen wäre genau die
    ungemessene Verengung, aus der N-201 entstanden ist."""
    tz_list = [_tz(d, {"pv_3": 30.0, "netzbezug": 5.0}) for d in _TAGE]
    ha_func = lambda d: {"pv_3": 30.0, "netzbezug": 12.0}

    ergebnisse = await _run(tz_list, [_inv(3, "pv-module")], ha_func)
    treffer = [e for e in ergebnisse if "Netzbezug" in e.meldung]
    assert len(treffer) == 1, [e.meldung for e in ergebnisse]
    assert treffer[0].investition_id is None, "Ein Basiszähler hängt an keinem Gerät."
