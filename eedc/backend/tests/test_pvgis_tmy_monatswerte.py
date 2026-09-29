"""B6 — PVGIS-TMY liefert wieder Monatswerte statt Nullen.

**Der Befund, gemessen am 29.09.2026.** ``fetch_pvgis_tmy_monat`` las den
Zeitstempel einer TMY-Stunde unter ``hour["time"]``. PVGIS nennt das Feld aber
``time(UTC)`` — an der Live-API v5_3 gegengeprüft (8760 Stunden, Schlüssel
``['time(UTC)', 'T2m', 'RH', 'G(h)', 'Gb(n)', 'Gd(h)', 'IR(h)', 'WS10m',
'WD10m', 'SP']``). Damit griff der Monatsfilter **nie**, und die Funktion gab
für **jeden** Monat an **jedem** Ort ``{globalstrahlung_kwh_m2: 0.0,
sonnenstunden: 0.0}`` zurück. Eingebaut mit ``f6f67b88`` (04.04.2026), seither
unverändert.

**Zwei Folgen, zwei Proben.**

1. *Der Wert selbst.* Wer im laufenden Monat „Wetterdaten abrufen" drückt,
   bekam zwei Nullen — beide Archive antworten für den laufenden Monat
   konstruktiv nicht, also fällt die Kaskade auf TMY. Die Autofill schreibt
   sie, weil ``0.0`` nicht ``None`` ist, und stempelt sie ``manual:form``:
   verriegelt gegen jede spätere Korrektur.
2. *Die tote Rückfallebene.* Ein dict mit zwei Nullen ist **truthy**. Der
   Aufrufer nahm es an, und die vierte Stufe der Kaskade
   (``get_pvgis_tmy_defaults``, statische Mitteleuropa-Werte) war damit toter
   Code — sie war nur über den ``None``-Zweig erreichbar, den es nicht gab.
   Derselbe Riegel, den ``orchestrator.py`` für Bright Sky schon trägt (#386).

**Die Fixture ist eine echte PVGIS-Antwort**, kein Nachbau: zwei ganze Tage
(15.01. und 15.07.) aus dem Abruf für die Koordinaten der Anlage
(50,896149 / 7,533871), Schlüsselnamen und Werte unverändert. Kein Netzabruf im
Test. Die Sollwerte darunter sind aus genau diesem Ausschnitt gerechnet — nicht
aus dem vollen Jahr, sonst prüfte die Probe eine Zahl, die sie nicht vor sich
hat.

Schwesterdatei: ``test_wetter_provider_land_386.py`` — dort der Riegel gegen
einen Bright-Sky-Monat ohne Strahlungstag, hier derselbe Gedanke eine
Kaskadenstufe tiefer.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.wetter.pvgis import (
    fetch_pvgis_tmy_monat,
    get_pvgis_tmy_defaults,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pvgis_tmy_ausschnitt.json"

#: Aus dem Fixture-Ausschnitt gerechnet (G(h)/1000 summiert, Stunde zählt ab
#: 120 W/m² — dieselbe WMO-Schwelle wie die Produktivfunktion).
SOLL_AUSSCHNITT = {1: (1.3, 5.0), 7: (5.2, 12.0)}


def _tmy_antwort(stunden: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"outputs": {"tmy_hourly": stunden}})
    return resp


def _client_mit(stunden: list[dict]):
    """Ein httpx-Client, der genau diese TMY-Stunden zurückgibt."""

    def _factory(*_a, **_kw):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        async def _get(url, params=None):
            return _tmy_antwort(stunden)

        client.get = _get
        return client

    return _factory


def _fixture_stunden() -> list[dict]:
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)["outputs"]["tmy_hourly"]


def _leeren_cache():
    from backend.services.wetter import cache

    cache._cache.clear()


@pytest.fixture(autouse=True)
def _ohne_jitter_und_cache():
    """Kein Zufalls-Sleep vor dem Abruf, kein Übersprechen zwischen Proben."""
    _leeren_cache()
    with patch("backend.services.wetter.pvgis.random.uniform", return_value=0):
        yield
    _leeren_cache()


# ══════════════════════════════════════════════════════════════════════════
# 1 · Der Monatsfilter greift — die echte Antwort trägt `time(UTC)`
# ══════════════════════════════════════════════════════════════════════════


def test_die_fixture_traegt_den_echten_schluesselnamen() -> None:
    """Vorbedingung: ohne sie prüften die Proben darunter einen Nachbau.

    Stünde in der Fixture ``time``, wäre jede Probe hier grün und der Defekt
    trotzdem da — genau die Selbstbestätigung, gegen die eine Fixture aus einer
    echten Antwort gebaut ist.
    """
    stunden = _fixture_stunden()
    assert stunden, "Fixture ist leer"
    assert "time(UTC)" in stunden[0], (
        f"PVGIS nennt das Feld 'time(UTC)'. Die Fixture trägt {list(stunden[0])}."
    )
    assert "time" not in stunden[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("monat", sorted(SOLL_AUSSCHNITT))
async def test_tmy_liefert_monatswerte_groesser_null(monat: int) -> None:
    """Der Kern des Funds: mit dem richtigen Schlüssel greift der Filter."""
    soll_strahlung, soll_stunden = SOLL_AUSSCHNITT[monat]

    with patch("httpx.AsyncClient", new=_client_mit(_fixture_stunden())):
        data = await fetch_pvgis_tmy_monat(50.896149, 7.533871, monat)

    assert data is not None, (
        f"TMY gab für Monat {monat} nichts zurück — die echte Antwort enthält "
        "Stunden dieses Monats."
    )
    assert data["globalstrahlung_kwh_m2"] > 0, (
        f"Monat {monat}: {data} — das ist der Zustand vor B6 (Filter greift nie)."
    )
    assert data["globalstrahlung_kwh_m2"] == pytest.approx(soll_strahlung)
    assert data["sonnenstunden"] == pytest.approx(soll_stunden)


@pytest.mark.asyncio
async def test_der_alte_schluesselname_wird_weiter_gelesen() -> None:
    """PVGIS hat den Namen schon einmal geändert — beide Schreibweisen zählen.

    Das ist keine Vorsichtsmaßnahme ins Blaue: die Annahme „das Feld heißt
    ``time``" war einmal richtig und ist es seit einer Namensänderung nicht
    mehr. Eine Funktion, die nur den heutigen Namen kennt, fällt beim nächsten
    Mal genauso still aus.
    """
    stunden = [
        {"time": s["time(UTC)"], "G(h)": s["G(h)"]} for s in _fixture_stunden()
    ]
    with patch("httpx.AsyncClient", new=_client_mit(stunden)):
        data = await fetch_pvgis_tmy_monat(50.896149, 7.533871, 7)

    assert data is not None
    assert data["globalstrahlung_kwh_m2"] == pytest.approx(SOLL_AUSSCHNITT[7][0])


# ══════════════════════════════════════════════════════════════════════════
# 2 · Ein Monat ohne Strahlung ist kein Ergebnis
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tmy_ohne_strahlung_ist_kein_ergebnis() -> None:
    """Null ist keine Antwort — sonst bleibt die Rückfallebene tot."""
    stunden = [
        {"time(UTC)": s["time(UTC)"], "G(h)": 0.0} for s in _fixture_stunden()
    ]
    with patch("httpx.AsyncClient", new=_client_mit(stunden)):
        data = await fetch_pvgis_tmy_monat(50.896149, 7.533871, 7)

    assert data is None, (
        f"Ein TMY-Monat ohne jede Strahlung kam als {data} zurück. Ein dict mit "
        "zwei Nullen ist truthy — der Aufrufer nimmt es an und bietet dem "
        "Anwender 0,0 kWh/m² an."
    )


@pytest.mark.asyncio
async def test_tmy_mit_null_faellt_auf_die_statischen_defaults() -> None:
    """Die vierte Kaskadenstufe wird erst durch den Riegel erreichbar.

    Gefragt wird ein **vergangener** Monat mit beiden Archiven stumm — genau
    die Lage, in der die Kaskade bis zum Ende laufen muss.
    """
    from backend.services.wetter.orchestrator import get_wetterdaten_multi

    stunden = [
        {"time(UTC)": s["time(UTC)"], "G(h)": 0.0} for s in _fixture_stunden()
    ]
    with patch("httpx.AsyncClient", new=_client_mit(stunden)), patch(
        "backend.services.wetter.open_meteo.fetch_open_meteo_archive",
        AsyncMock(return_value=None),
    ), patch(
        "backend.services.brightsky_service.fetch_brightsky_month",
        AsyncMock(return_value=None),
    ):
        result = await get_wetterdaten_multi(
            50.896149, 7.533871, 2025, 7, provider="auto", land="DE"
        )

    assert result["datenquelle"] == "defaults", (
        f"Kaskade endete bei {result.get('datenquelle')!r} mit "
        f"{result.get('globalstrahlung_kwh_m2')} kWh/m². Solange ein "
        "Null-Ergebnis als Ergebnis gilt, ist `get_pvgis_tmy_defaults` toter Code."
    )
    soll = get_pvgis_tmy_defaults(7, 50.896149)
    assert result["globalstrahlung_kwh_m2"] == soll["globalstrahlung_kwh_m2"]
    assert result["globalstrahlung_kwh_m2"] > 0
