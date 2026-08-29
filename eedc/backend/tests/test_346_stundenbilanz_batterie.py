"""N-346 — der Stundenverbrauch ist eine Differenz, und ihr Batterie-Subtrahend
darf nicht fehlen (Melder OB73-gif, Issue #395).

Der Befund: ``verbrauch = PV + Netzbezug − Einspeisung − Batterie-Netto`` wurde
gebildet, sobald PV, Netzbezug und Einspeisung vorlagen — die **vierte** Größe
durfte über ``(batt_netto or 0.0)`` still fehlen. Bei einer Anlage mit Speicher
ist der Stundenverbrauch dann nachts der reine Netzbezug. Trägt der Speicher die
Nacht, steht dort fast nichts; je weniger er trägt, desto höher wird die Zahl.

Die Zahlen in ``test_melderfall_*`` sind **die des Melders**: er sah seine
Grundlast über den August von 0 W auf 300 W steigen, während die Live-Prognose
daneben 340 W nannte.

⚠ Die Aktiv-Proben benutzen echte ``Investition``-Objekte statt ``SimpleNamespace``
— ein Double mit eigener Aktiv-Logik wäre die zweite Definition von
``ist_aktiv_an`` (die Begründung steht seit N-64 in
``test_etappe_6_drift_check.py``).

Schwesterdateien: ``test_daten_checker_speicher_zaehler_richtungen.py`` (die
andere Hälfte desselben Fundes — dort die Erklärung an den Anwender),
``test_lts_aggregator_konsistenz.py`` und ``test_grundlast.py`` (die Kennzahl,
an der der Melder es gesehen hat).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.core.berechnungen.stundenbilanz import (
    berechne_batterie_netto_kwh,
    erwartet_batterie_beitrag,
    stunden_verbrauch_kwh,
)
from backend.models.investition import Investition
from backend.services.snapshot.lts_aggregator import get_hourly_kwh_by_category_lts


# ── Der Layer selbst ────────────────────────────────────────────────────────

def test_ohne_speicher_unveraendert():
    """Eine Anlage ohne Speicher rechnet exakt wie vorher — auch mit `None`."""
    assert stunden_verbrauch_kwh(
        pv_kwh=0.0, netzbezug_kwh=0.4, einspeisung_kwh=0.0,
        batterie_netto_kwh=None, batterie_erwartet=False,
    ) == pytest.approx(0.4)


def test_mit_speicher_ohne_batteriewert_ist_unbekannt():
    """Der Kern von N-346: fehlt die vierte Größe, ist das Ergebnis None."""
    assert stunden_verbrauch_kwh(
        pv_kwh=0.0, netzbezug_kwh=0.01, einspeisung_kwh=0.0,
        batterie_netto_kwh=None, batterie_erwartet=True,
    ) is None


def test_melderfall_die_beiden_zahlen_stehen_nebeneinander():
    """Dieselbe Nachtstunde, einmal ohne und einmal mit Batterie-Beitrag.

    0,01 kWh sind die **10 W**, die der Melder sah; 0,34 kWh die **340 W**, die
    die Live-Prognose daneben nannte. Der Unterschied ist genau die Entladung.
    """
    ohne = stunden_verbrauch_kwh(
        pv_kwh=0.0, netzbezug_kwh=0.01, einspeisung_kwh=0.0,
        batterie_netto_kwh=None, batterie_erwartet=False,
    )
    mit = stunden_verbrauch_kwh(
        pv_kwh=0.0, netzbezug_kwh=0.01, einspeisung_kwh=0.0,
        batterie_netto_kwh=-0.33, batterie_erwartet=True,
    )
    assert ohne == pytest.approx(0.01)
    assert mit == pytest.approx(0.34)


def test_negative_bilanz_bleibt_auf_null_geklemmt():
    """Der `max(0, …)`-Schritt bleibt — er ist nicht der Wächter, aber er gilt."""
    assert stunden_verbrauch_kwh(
        pv_kwh=1.0, netzbezug_kwh=0.0, einspeisung_kwh=2.0,
        batterie_netto_kwh=0.0, batterie_erwartet=True,
    ) == 0.0


def test_halbe_richtung_ist_keine_netto_ladung():
    """Nur der Ladezähler zugeordnet → nachts wäre die Entladung dauerhaft 0."""
    assert berechne_batterie_netto_kwh(
        ladung_kwh=0.0, entladung_kwh=None, erwartet=True,
    ) is None
    assert berechne_batterie_netto_kwh(
        ladung_kwh=None, entladung_kwh=0.4, erwartet=True,
    ) is None
    assert berechne_batterie_netto_kwh(
        ladung_kwh=0.5, entladung_kwh=0.1, erwartet=True,
    ) == pytest.approx(0.4)


def test_ohne_erwartung_bleibt_die_alte_regel():
    """Kein aktiver Speicher: ein noch liefernder Zähler wird weiter abgezogen."""
    assert berechne_batterie_netto_kwh(
        ladung_kwh=0.5, entladung_kwh=None, erwartet=False,
    ) == pytest.approx(0.5)
    assert berechne_batterie_netto_kwh(
        ladung_kwh=None, entladung_kwh=None, erwartet=False,
    ) is None


# ── Wer fordert einen Batterie-Beitrag ein — und wer nicht ──────────────────

def _speicher(**kw) -> Investition:
    daten = dict(id=7, anlage_id=1, typ="speicher", bezeichnung="Hausakku", aktiv=True)
    daten.update(kw)
    return Investition(**daten)


TAG = date(2026, 8, 20)


def test_aktiver_speicher_wird_erwartet():
    assert erwartet_batterie_beitrag([_speicher()], TAG) is True


def test_noch_nicht_angeschaffter_speicher_wird_nicht_erwartet():
    """Anschaffung nach dem Tag — sonst fordert eedc einen Zähler für einen
    Speicher ein, den es an diesem Tag noch nicht gab (N-64/N-313-Klasse)."""
    inv = _speicher(anschaffungsdatum=date(2026, 9, 1))
    assert erwartet_batterie_beitrag([inv], TAG) is False


def test_stillgelegter_speicher_wird_nicht_erwartet():
    inv = _speicher(stilllegungsdatum=date(2026, 7, 31))
    assert erwartet_batterie_beitrag([inv], TAG) is False


def test_auf_inaktiv_gesetzter_speicher_wird_nicht_erwartet():
    assert erwartet_batterie_beitrag([_speicher(aktiv=False)], TAG) is False


def test_andere_typen_fordern_nichts_ein():
    wp = Investition(id=8, anlage_id=1, typ="waermepumpe", bezeichnung="WP", aktiv=True)
    assert erwartet_batterie_beitrag([wp], TAG) is False


# ── Durch den echten LTS-Aggregator ─────────────────────────────────────────

def _anlage(sensor_mapping: dict):
    return SimpleNamespace(
        id=1, anlagenname="Melderfall", leistung_kwp=10.0,
        sensor_mapping=sensor_mapping,
    )


def _mock_ha(deltas: dict[str, dict[int, float]]) -> MagicMock:
    svc = MagicMock()
    svc.is_available = True
    svc.get_hourly_kwh_deltas_for_day.side_effect = lambda ids, _d: {
        eid: deltas[eid] for eid in ids if eid in deltas
    }
    return svc


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


NACHT = 3  # eine Stunde ohne PV


def _deltas(wert_je_sensor: dict[str, float]) -> dict[str, dict[int, float]]:
    """Nur die Nachtstunde trägt Werte; alle übrigen Stunden sind 0."""
    return {
        eid: {h: (wert if h == NACHT else 0.0) for h in range(24)}
        for eid, wert in wert_je_sensor.items()
    }


@pytest.mark.asyncio
async def test_lts_speicher_ohne_entladezaehler_liefert_keinen_verbrauch():
    """Der Melderfall, durch den echten Aggregator: Speicher da, Entladung nicht
    zugeordnet → die Stunde ist unbekannt statt „10 W"."""
    sm = {
        "basis": {
            "einspeisung": _sensor("sensor.einsp"),
            "netzbezug": _sensor("sensor.bez"),
            "pv_gesamt": _sensor("sensor.pv"),
        },
        "investitionen": {
            "7": {"felder": {"ladung_kwh": _sensor("sensor.lade")}},
        },
    }
    deltas = _deltas({
        "sensor.pv": 0.0, "sensor.einsp": 0.0,
        "sensor.bez": 0.01, "sensor.lade": 0.0,
    })
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=_mock_ha(deltas),
    ):
        result = await get_hourly_kwh_by_category_lts(
            None, _anlage(sm), {"7": _speicher()}, TAG,
        )
    assert result[NACHT]["verbrauch"] is None


@pytest.mark.asyncio
async def test_lts_speicher_mit_beiden_zaehlern_rechnet_die_entladung_mit():
    """Gegenprobe: mit beiden Richtungen steht dort die volle Nachtlast."""
    sm = {
        "basis": {
            "einspeisung": _sensor("sensor.einsp"),
            "netzbezug": _sensor("sensor.bez"),
            "pv_gesamt": _sensor("sensor.pv"),
        },
        "investitionen": {
            "7": {"felder": {
                "ladung_kwh": _sensor("sensor.lade"),
                "entladung_kwh": _sensor("sensor.entlade"),
            }},
        },
    }
    deltas = _deltas({
        "sensor.pv": 0.0, "sensor.einsp": 0.0, "sensor.bez": 0.01,
        "sensor.lade": 0.0, "sensor.entlade": 0.33,
    })
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=_mock_ha(deltas),
    ):
        result = await get_hourly_kwh_by_category_lts(
            None, _anlage(sm), {"7": _speicher()}, TAG,
        )
    assert result[NACHT]["verbrauch"] == pytest.approx(0.34)


@pytest.mark.asyncio
async def test_lts_anlage_ohne_speicher_bleibt_unveraendert():
    """Negativprobe: ohne Speicher-Investition wird nichts unterdrückt."""
    sm = {
        "basis": {
            "einspeisung": _sensor("sensor.einsp"),
            "netzbezug": _sensor("sensor.bez"),
            "pv_gesamt": _sensor("sensor.pv"),
        },
        "investitionen": {},
    }
    deltas = _deltas({
        "sensor.pv": 0.0, "sensor.einsp": 0.0, "sensor.bez": 0.4,
    })
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=_mock_ha(deltas),
    ):
        result = await get_hourly_kwh_by_category_lts(
            None, _anlage(sm), {}, TAG,
        )
    assert result[NACHT]["verbrauch"] == pytest.approx(0.4)
