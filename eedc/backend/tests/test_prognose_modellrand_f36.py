"""F-36 — ein am Modellrand abgeschnittener Tag darf den vollständigen nicht verdrängen.

**Der gemeldete Schaden** (Gernot, 2026-08-18, seine eigene Anlage): *Cockpit → Live*
zeigte für den Folgetag **0,3 kWh** und eine Temperatur von „—" — eingerahmt von
12,4 kWh davor und 62,6 kWh danach. An der Quelle gemessen (direkter Abruf mit
``models=icon_d2``, 48 h): der letzte GTI- **und** Temperaturwert stand auf
``2026-08-19T08:00``, danach ``None``. 15 Stunden fehlten, darunter der gesamte
Ertragszeitraum. Das war keine Wetterlage, das war der Modellhorizont.

**Die Ursache** saß im Merge der Kaskade. Er lautete sinngemäß „Primary hat
Vorrang, Fallback füllt auf" und war als ``if tag.datum not in primary_dates``
umgesetzt — er prüfte, **OB** ein Primary-Tag existiert, nicht **ob er
vollständig ist**. Der vollständige best_match-Tag lag daneben und wurde
verworfen.

⚑ **Die Lücke war seit dem 2026-07-28 bekannt und wurde umgangen statt
geschlossen:** der Docstring von ``wetter/cache.snapshot_days`` beschreibt sie
wörtlich. Die damalige Antwort war, das Abruf-Fenster auf den Modellhorizont zu
begrenzen — das beseitigt die *ganz leeren* Tage jenseits davon, den
*angeschnittenen* Tag am Rand lässt es stehen. Diese Tests decken genau ihn.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from backend.models import Anlage, Investition
from backend.services import solar_forecast_service as sfs
from backend.services.solar_forecast_service import (
    _gti_abdeckung_je_tag,
    get_solar_prognose,
)
from backend.services.wetter import cache as wetter_cache


# ---------------------------------------------------------------------------
# HTTP-Schicht: das Primärmodell bricht am LETZTEN Tag um 08:00 ab
# ---------------------------------------------------------------------------


def _payload(params: dict, *, abschneiden_ab: int | None) -> dict:
    """GTI-Antwort ab heute. Primary doppelter Pegel, damit die Quelle ablesbar ist.

    ``abschneiden_ab``: ab dieser Stunde trägt der LETZTE Tag ``None`` — so
    verhält sich ICON-D2 am Ende seines 48-h-Fensters.
    """
    tage = int(params.get("forecast_days", 1))
    ist_primary = bool(params.get("models"))
    pegel = 200.0 if ist_primary else 100.0
    heute = date.today()
    daten = [(heute + timedelta(days=t)).isoformat() for t in range(tage)]

    zeiten, gti, ghi, temp = [], [], [], []
    schnee, wolken, regen, code = [], [], [], []
    for idx, datum in enumerate(daten):
        letzter_tag = idx == tage - 1
        for h in range(24):
            weg = (
                ist_primary
                and abschneiden_ab is not None
                and letzter_tag
                and h > abschneiden_ab
            )
            zeiten.append(f"{datum}T{h:02d}:00")
            gti.append(None if weg else (pegel if 8 <= h <= 16 else 0.0))
            ghi.append(None if weg else (pegel * 0.8 if 8 <= h <= 16 else 0.0))
            temp.append(None if weg else 18.0)
            schnee.append(None if weg else 0.0)
            wolken.append(None if weg else 20.0)
            regen.append(None if weg else 0.0)
            code.append(None if weg else 1)

    return {
        "hourly": {
            "time": zeiten,
            "global_tilted_irradiance": gti,
            "shortwave_radiation": ghi,
            "temperature_2m": temp,
            "snowfall": schnee,
            "cloud_cover": wolken,
            "precipitation": regen,
            "weather_code": code,
        },
        "daily": {
            "time": daten,
            "shortwave_radiation_sum": [10.0] * tage,
            "sunshine_duration": [36000.0] * tage,
            "temperature_2m_max": [24.0] * tage,
            "temperature_2m_min": [12.0] * tage,
            "precipitation_sum": [0.0] * tage,
            "snowfall_sum": [0.0] * tage,
            "weather_code": [1] * tage,
        },
    }


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, aufrufe: list, abschneiden_ab: int | None):
        self._aufrufe = aufrufe
        self._ab = abschneiden_ab

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        params = params or {}
        self._aufrufe.append(params)
        return _FakeResponse(_payload(params, abschneiden_ab=self._ab))


class _HttpxShim:
    def __init__(self, client):
        self.AsyncClient = client

    def __getattr__(self, name):
        return getattr(httpx, name)


@pytest.fixture
def _caches_leer():
    from backend.services.korrekturprofil_lookup import _cache as korrektur_cache

    def _leeren():
        wetter_cache._cache.clear()
        wetter_cache._error_cache.clear()
        korrektur_cache.clear()

    _leeren()
    yield
    _leeren()


@pytest.fixture
def modellrand(monkeypatch, _caches_leer):
    """Primärmodell endet am letzten Tag um 08:00 — der gemessene Fall."""
    aufrufe: list[dict] = []
    monkeypatch.setattr(sfs, "httpx", _HttpxShim(_FakeClient(aufrufe, 8)))
    return aufrufe


@pytest.fixture
def vollstaendig(monkeypatch, _caches_leer):
    """Gegenrichtung: kein Modell schneidet ab."""
    aufrufe: list[dict] = []
    monkeypatch.setattr(sfs, "httpx", _HttpxShim(_FakeClient(aufrufe, None)))
    return aufrufe


# ---------------------------------------------------------------------------
# Die Abdeckungs-Messung
# ---------------------------------------------------------------------------


def test_abdeckung_zaehlt_stunden_mit_wert():
    """Nachts ist GTI 0.0 und damit VORHANDEN — gezählt wird der Wert, nicht der Ertrag."""
    daten = _payload({"forecast_days": 2, "models": "icon_d2"}, abschneiden_ab=8)
    abdeckung = _gti_abdeckung_je_tag(daten)
    tage = sorted(abdeckung)
    assert abdeckung[tage[0]] == 24     # voller Tag
    assert abdeckung[tage[1]] == 9      # 00:00 … 08:00
    assert 0 < abdeckung[tage[1]] < 24  # angeschnitten, nicht leer


def test_abdeckung_ohne_daten_ist_leer():
    assert _gti_abdeckung_je_tag(None) == {}
    assert _gti_abdeckung_je_tag({}) == {}


def test_vollstaendiger_tag_hat_24():
    daten = _payload({"forecast_days": 3, "models": None}, abschneiden_ab=None)
    assert set(_gti_abdeckung_je_tag(daten).values()) == {24}


# ---------------------------------------------------------------------------
# Der Merge — die Zahl, um die es ging
# ---------------------------------------------------------------------------


async def _prognose(wetter_modell: str, days: int):
    return await get_solar_prognose(
        latitude=48.8, longitude=9.2, kwp=10.0, neigung=35, ausrichtung=0,
        days=days, wetter_modell=wetter_modell, skip_jitter=True,
    )


async def test_angeschnittener_randtag_faellt_auf_best_match(modellrand):
    """Der gemeldete Fall: kein Tag kollabiert auf ~0."""
    prognose = await _prognose("icon_d2", days=4)
    werte = [t.pv_ertrag_kwh for t in prognose.tageswerte]

    assert all(w > 0 for w in werte), werte
    # Tag 0 trägt icon_d2 (doppelter Pegel), Tag 1 ist am Modellrand
    # abgeschnitten und fällt deshalb auf best_match — wie Tag 2 und 3.
    assert werte[0] > werte[1], werte
    assert werte[1] == werte[2] == werte[3], werte
    assert prognose.tageswerte[0].datenquelle == "icon_d2"
    assert prognose.tageswerte[1].datenquelle == "best_match"


async def test_randtag_traegt_wieder_seine_tageswerte(modellrand):
    """Nicht nur der Ertrag: Temperatur und Nachmittag waren `null`."""
    prognose = await _prognose("icon_d2", days=4)
    morgen = prognose.tageswerte[1]

    assert morgen.temperatur_max_c is not None
    assert morgen.temperatur_min_c is not None
    assert morgen.pv_ertrag_nachmittags_kwh is not None
    assert morgen.pv_ertrag_nachmittags_kwh > 0


async def test_vollstaendiges_modell_behaelt_den_vorrang(vollstaendig):
    """Gegenrichtung — ohne Abschnitt bleibt alles wie bisher.

    Bei GLEICHER Abdeckung gewinnt das gewählte Modell; sonst hätte der Fix
    jedem Nutzer stillschweigend die Modellwahl genommen.
    """
    prognose = await _prognose("icon_d2", days=4)
    werte = [t.pv_ertrag_kwh for t in prognose.tageswerte]

    assert prognose.tageswerte[0].datenquelle == "icon_d2"
    assert prognose.tageswerte[1].datenquelle == "icon_d2"
    assert werte[0] == werte[1] > werte[2] == werte[3], werte


async def test_auto_bleibt_unberuehrt(vollstaendig):
    """Die Kontrollprobe aus A30: `auto` kennt gar keine Kaskade."""
    prognose = await _prognose("auto", days=4)
    assert all(t.datenquelle == "best_match" for t in prognose.tageswerte)
    assert all(t.pv_ertrag_kwh > 0 for t in prognose.tageswerte)


async def test_quellenangabe_nennt_beide(modellrand):
    """Die Kopfzeile darf kein Modell behaupten, das nicht jeden Tag trägt."""
    prognose = await _prognose("icon_d2", days=4)
    assert "ICON-D2" in prognose.datenquelle
    assert "Open-Meteo" in prognose.datenquelle


# ---------------------------------------------------------------------------
# Der Zweig OHNE Kaskade — days <= max_days
# ---------------------------------------------------------------------------


async def test_ein_abruf_zweig_holt_den_fallback_nach(modellrand):
    """`days == max_days`: der letzte Tag liegt genau auf dem Modellrand.

    Hier greift die Kaskade gar nicht (ein Abruf reicht ja), und ohne
    Nachholen bliebe der Fix an dieser Stelle blind — dieselbe Sorte halbe
    Reparatur, die den Befund überhaupt hervorgebracht hat.
    """
    prognose = await _prognose("icon_d2", days=2)
    werte = [t.pv_ertrag_kwh for t in prognose.tageswerte]

    assert len(werte) == 2
    assert all(w > 0 for w in werte), werte
    assert prognose.tageswerte[1].datenquelle == "best_match"


async def test_ein_abruf_zweig_ohne_abschnitt_ruft_nur_einmal(vollstaendig):
    """Der zusätzliche Abruf entsteht NUR im Bedarfsfall."""
    await _prognose("icon_d2", days=2)
    modelle = [a.get("models") for a in vollstaendig]

    assert modelle == ["icon_d2"], vollstaendig
