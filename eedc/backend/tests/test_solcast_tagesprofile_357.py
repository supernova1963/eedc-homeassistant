"""#357 — Solcast liefert für jeden Prognosetag sein eigenes Stundenprofil.

Ausgangslage bis v4.0.8: Der HA-Pfad las das ``detailedForecast``-Attribut
**nur** vom Heute-Sensor, der API-Pfad verwarf jeden 30-Min-Bucket mit
``slot_date != heute`` — obwohl beide Quellen die übrigen Tage längst
mitliefern (HA: ein Attribut je Tages-Sensor, belegt von rapahl am 30.07.2026;
API: 168 h in einem Abruf). Wer einen anderen Tag ansah, bekam die Kurvenform
von heute, auf die Tagesmenge des Zieltags skaliert.

Gebaut wurde **datengetrieben** (Entscheid Gernot, 2026-08-05): jeder Tag, für
den die Quelle Slots liefert, bekommt ein Profil — kein Sonderfall „morgen",
keine Annahme darüber, ob die Integration für Tag 3–7 etwas liefert.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.services.solcast_service import (
    SolcastForecast,
    TagesStundenprofil,
    _fetch_solcast_api,
    _fetch_solcast_ha_auto,
)

TZ = ZoneInfo("Europe/Berlin")


# ── Datenstruktur ───────────────────────────────────────────────────────────

def _forecast(profile: dict[str, TagesStundenprofil]) -> SolcastForecast:
    return SolcastForecast(
        daily_kwh=0.0, daily_p10_kwh=0.0, daily_p90_kwh=0.0,
        tomorrow_kwh=0.0, tomorrow_p10_kwh=0.0, tomorrow_p90_kwh=0.0,
        stundenprofile=profile,
    )


def test_profil_fuer_liefert_nur_tage_mit_werten():
    """Ein leeres 24er-Raster ist **kein** Profil.

    Sonst würde ein Tag ohne Slots als „echt beantwortet" gelten und die
    Näherungs-Kennzeichnung fiele weg, obwohl 24 Nullen dastehen (P4).
    """
    heute = date.today()
    leer = TagesStundenprofil(datum=heute)
    voll = TagesStundenprofil(datum=heute, p50=[0.0] * 10 + [1.5] * 4 + [0.0] * 10)

    assert _forecast({heute.isoformat(): leer}).profil_fuer(heute) is None
    assert _forecast({heute.isoformat(): voll}).profil_fuer(heute) is voll
    assert _forecast({}).profil_fuer(heute) is None


# ── API-Pfad: 168 h werden nicht mehr auf einen Tag zusammengestrichen ──────

class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, *_args, **_kwargs):
        return _FakeResponse(self._payload)


def _api_bucket(zeitpunkt: datetime, kw: float) -> dict:
    """Ein 30-Min-Bucket der Solcast-API (``period_end``, UTC)."""
    return {
        "period_end": zeitpunkt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "period": "PT30M",
        "pv_estimate": kw,
        "pv_estimate10": kw * 0.8,
        "pv_estimate90": kw * 1.2,
    }


@pytest.mark.asyncio
async def test_api_pfad_traegt_alle_tage_statt_nur_heute(monkeypatch):
    """Der Abruf holt 168 h — bis v4.0.8 landeten davon nur die Heute-Slots
    in der Antwort."""
    import httpx

    from backend.services.wetter import cache as wetter_cache

    heute = date.today()
    morgen = heute + timedelta(days=1)
    # Je Tag zwei Buckets in derselben Stunde (12:00 + 12:30 → Slot 13),
    # damit auch die 30-Min-Summierung geprüft ist.
    buckets = []
    for tag, kw in ((heute, 3.0), (morgen, 1.0)):
        for minute in (30, 60):
            ende = datetime.combine(tag, datetime.min.time(), tzinfo=TZ) + timedelta(
                hours=12, minutes=minute
            )
            buckets.append(_api_bucket(ende, kw))

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _FakeClient({"forecasts": buckets}))
    monkeypatch.setattr(wetter_cache, "_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(wetter_cache, "_cache_set", lambda *_a, **_k: None)
    monkeypatch.setattr("backend.services.solcast_service._cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr("backend.services.solcast_service._cache_set", lambda *_a, **_k: None)
    monkeypatch.setattr("backend.services.solcast_service._error_cache_check", lambda *_a, **_k: False)

    result = await _fetch_solcast_api("key", [{"id": "site-1"}], "free")

    assert result is not None
    morgen_profil = result.profil_fuer(morgen)
    assert morgen_profil is not None, "Morgen hat eigene Buckets — sie dürfen nicht verfallen."
    assert morgen_profil.p50[13] == pytest.approx(1.0), "2 × 1,0 kW × 0,5 h = 1,0 kWh"
    assert result.profil_fuer(heute).p50[13] == pytest.approx(3.0)

    # Die Heute-Sicht bleibt bitgleich das, was sie vorher war.
    assert result.hourly_kw == result.profil_fuer(heute).p50


# ── HA-Pfad: ein Attribut je Tages-Sensor ───────────────────────────────────

def _ha_entry(zeitpunkt: datetime, kw: float) -> dict:
    """Ein 30-Min-Bucket der HA-Integration (``period_start``, lokal)."""
    return {
        "period_start": zeitpunkt.isoformat(),
        "pv_estimate": kw,
        "pv_estimate10": kw * 0.8,
        "pv_estimate90": kw * 1.2,
    }


def _ha_state(entity_id: str, kwh: float, detailed: list[dict]) -> dict:
    return {
        "entity_id": entity_id,
        "state": str(kwh),
        "attributes": {"estimate10": kwh * 0.8, "estimate90": kwh * 1.2, "detailedForecast": detailed},
    }


@pytest.mark.asyncio
async def test_ha_pfad_liest_das_attribut_jedes_tages_sensors(monkeypatch):
    """Die Attribute aller sieben Sensoren liegen aus **einem** Batch-Call vor;
    es fehlte nur die Auswertung. Kein zweiter HA-Abruf."""
    import httpx

    from backend.services import solcast_service

    heute = date.today()
    morgen = heute + timedelta(days=1)

    def _detailed(tag: date, kw: float) -> list[dict]:
        start = datetime.combine(tag, datetime.min.time(), tzinfo=TZ) + timedelta(hours=12)
        return [_ha_entry(start, kw), _ha_entry(start + timedelta(minutes=30), kw)]

    states = [
        _ha_state("sensor.solcast_pv_forecast_prognose_heute", 20.0, _detailed(heute, 4.0)),
        _ha_state("sensor.solcast_pv_forecast_prognose_morgen", 8.0, _detailed(morgen, 1.5)),
    ]

    async def fake_resolve():
        return {
            "heute": "sensor.solcast_pv_forecast_prognose_heute",
            "morgen": "sensor.solcast_pv_forecast_prognose_morgen",
        }

    class _FakeHaService:
        is_available = True
        api_url = "http://ha.local/api"
        token = "t"

    monkeypatch.setattr(solcast_service, "_resolve_solcast_entities", fake_resolve)
    monkeypatch.setattr(solcast_service, "_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(solcast_service, "_cache_set", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service", lambda: _FakeHaService()
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _FakeClient(states))

    result = await _fetch_solcast_ha_auto()

    assert result is not None
    morgen_profil = result.profil_fuer(morgen)
    assert morgen_profil is not None, (
        "Der Morgen-Sensor trägt ein eigenes detailedForecast (rapahl, #357)."
    )
    assert morgen_profil.p50[13] == pytest.approx(1.5)
    assert result.profil_fuer(heute).p50[13] == pytest.approx(4.0)
    assert result.hourly_kw[13] == pytest.approx(4.0), "Heute-Sicht unverändert."


@pytest.mark.asyncio
async def test_ha_pfad_ohne_attribut_liefert_kein_profil(monkeypatch):
    """Kein Rateweg: Trägt ein Tages-Sensor kein Detail-Attribut (Tag 3–7 je
    nach Integration), entsteht für ihn **kein** Profil — die Näherung samt
    Kennzeichnung bleibt dann bestehen."""
    import httpx

    from backend.services import solcast_service

    heute = date.today()
    morgen = heute + timedelta(days=1)
    start = datetime.combine(heute, datetime.min.time(), tzinfo=TZ) + timedelta(hours=12)

    states = [
        _ha_state("sensor.solcast_heute", 20.0, [_ha_entry(start, 4.0)]),
        _ha_state("sensor.solcast_morgen", 8.0, []),
    ]

    async def fake_resolve():
        return {"heute": "sensor.solcast_heute", "morgen": "sensor.solcast_morgen"}

    class _FakeHaService:
        is_available = True
        api_url = "http://ha.local/api"
        token = "t"

    monkeypatch.setattr(solcast_service, "_resolve_solcast_entities", fake_resolve)
    monkeypatch.setattr(solcast_service, "_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(solcast_service, "_cache_set", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service", lambda: _FakeHaService()
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: _FakeClient(states))

    result = await _fetch_solcast_ha_auto()

    assert result is not None
    assert result.profil_fuer(morgen) is None
    assert result.tomorrow_kwh == pytest.approx(8.0), "Die Tagesmenge bleibt erhalten."


# ── Adapter: Profil UND Tageswert gehören zum angefragten Tag ───────────────

def test_adapter_nimmt_profil_und_tageswert_des_angefragten_tages():
    from backend.services.prognose_adapter import solcast_profil

    heute = date.today()
    morgen = heute + timedelta(days=1)
    forecast = SolcastForecast(
        daily_kwh=20.0, daily_p10_kwh=16.0, daily_p90_kwh=24.0,
        tomorrow_kwh=8.0, tomorrow_p10_kwh=6.0, tomorrow_p90_kwh=10.0,
        hourly_kw=[0.0] * 12 + [4.0] + [0.0] * 11,
        hourly_p10_kw=[0.0] * 24,
        hourly_p90_kw=[0.0] * 24,
        tage_voraus=[
            {"datum": heute.isoformat(), "kwh": 20.0, "p10": 16.0, "p90": 24.0},
            {"datum": morgen.isoformat(), "kwh": 8.0, "p10": 6.0, "p90": 10.0},
        ],
        stundenprofile={
            heute.isoformat(): TagesStundenprofil(datum=heute, p50=[0.0] * 12 + [4.0] + [0.0] * 11),
            morgen.isoformat(): TagesStundenprofil(datum=morgen, p50=[0.0] * 14 + [1.5] + [0.0] * 9),
        },
    )

    p_morgen = solcast_profil(forecast, datum=morgen)
    assert p_morgen.slots_kw[14] == pytest.approx(1.5)
    assert p_morgen.slots_kw[12] == pytest.approx(0.0)
    assert p_morgen.tageswert_kwh == pytest.approx(8.0), (
        "Sonst stünde die Kurve von morgen unter der Tagesmenge von heute."
    )

    p_heute = solcast_profil(forecast, datum=heute)
    assert p_heute.slots_kw[12] == pytest.approx(4.0)
    assert p_heute.tageswert_kwh == pytest.approx(20.0)


# ── Prognosen-Vergleich: die Solcast-Spalte trägt keine fremde Form mehr ────

async def _fake_solar_prognose(*_a, **kwargs):
    """OpenMeteo-Ersatz für den Prognose-Kanon — festes Profil, kein Netz.

    Die Kurve belegt bewusst BEIDE Tageshälften (Slots 8…16), denn genau
    daran erkennt der Test unten, dass übermorgen die OM-Verteilung benutzt
    wird und nicht die (nur vormittags belegte) Solcast-Kurve von morgen.
    """
    import backend.services.solar_forecast_service as _sfs

    days = kwargs.get("days", 4)
    heute_ = date.today()
    slots = [0.0] * 24
    for h in range(8, 17):
        slots[h] = 1.0
    tage = [
        _sfs.SolarPrognoseTag(
            datum=(heute_ + timedelta(days=o)).isoformat(),
            pv_ertrag_kwh=sum(slots), gti_kwh_m2=5.0, ghi_kwh_m2=4.0,
            sonnenstunden=9.0, temperatur_max_c=20.0, temperatur_min_c=10.0,
            bewoelkung_prozent=10, niederschlag_mm=0.0, schnee_cm=0.0,
            stunden_kw=list(slots),
        )
        for o in range(days)
    ]
    return _sfs.SolarPrognoseResponse(
        anlage_id=None, kwp_gesamt=kwargs.get("kwp", 10.0),
        neigung=kwargs.get("neigung", 35), ausrichtung=kwargs.get("ausrichtung", 0),
        system_losses_prozent=14.0,
        prognose_zeitraum={"von": tage[0].datum, "bis": tage[-1].datum},
        summe_kwh=sum(t.pv_ertrag_kwh for t in tage),
        durchschnitt_kwh_tag=sum(t.pv_ertrag_kwh for t in tage) / len(tage),
        tageswerte=tage, string_prognosen=None,
        datenquelle="test", abgerufen_am=tage[0].datum,
    )

@pytest.mark.asyncio
async def test_vergleich_tageshaelften_morgen_kommen_aus_solcast(db, monkeypatch):
    """Vormittag/Nachmittag der Solcast-Spalte wurden für morgen aus der
    **OpenMeteo**-Verteilung geschätzt (`prognosen.py`, „VM/NM aus OpenMeteo-
    Verteilung schätzen"). Mit einem eigenen Solcast-Profil ist das nicht mehr
    nötig — und die Zahl ändert sich sichtbar, wenn die beiden Quellen die
    Tageshälften verschieden verteilen.

    Der Fall ohne eigenes Profil (übermorgen) bleibt bei der OM-Schätzung —
    Entscheid Gernot 2026-08-05: lieber geschätzt als gar keine Zahl.
    """
    from datetime import date as _date, timedelta as _td

    import backend.api.routes.prognosen as pr
    import backend.services.solar_forecast_service as sfs
    from backend.models import Anlage, Investition, Monatsdaten

    heute = _date.today()
    morgen = heute + _td(days=1)
    uebermorgen = heute + _td(days=2)

    anlage = Anlage(
        anlagenname="Solcast-VMNM", leistung_kwp=10.0,
        latitude=48.8, longitude=9.2, standort_land="DE", prognose_quelle="solcast",
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1, netzbezug_kwh=100.0))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=10.0,
        neigung_grad=35, anschaffungsdatum=_date(2024, 1, 1),
        parameter={"ausrichtung_grad": 0},
    ))
    await db.flush()

    # Solcast: morgen liegt die Erzeugung KOMPLETT am Vormittag (Slot 8),
    # übermorgen kennt Solcast nur die Tagesmenge.
    forecast = SolcastForecast(
        daily_kwh=20.0, daily_p10_kwh=16.0, daily_p90_kwh=24.0,
        tomorrow_kwh=8.0, tomorrow_p10_kwh=6.0, tomorrow_p90_kwh=10.0,
        hourly_kw=[0.0] * 12 + [20.0] + [0.0] * 11,
        hourly_p10_kw=[0.0] * 24, hourly_p90_kw=[0.0] * 24,
        tage_voraus=[
            {"datum": heute.isoformat(), "kwh": 20.0, "p10": 16.0, "p90": 24.0},
            {"datum": morgen.isoformat(), "kwh": 8.0, "p10": 6.0, "p90": 10.0},
            {"datum": uebermorgen.isoformat(), "kwh": 6.0, "p10": 5.0, "p90": 7.0},
        ],
        stundenprofile={
            heute.isoformat(): TagesStundenprofil(datum=heute, p50=[0.0] * 12 + [20.0] + [0.0] * 11),
            morgen.isoformat(): TagesStundenprofil(datum=morgen, p50=[0.0] * 8 + [8.0] + [0.0] * 15),
        },
    )

    async def fake_solcast(*_a, **_k):
        return forecast

    async def _none(*_a, **_k):
        return None

    monkeypatch.setattr(pr, "get_solcast_forecast", fake_solcast)
    monkeypatch.setattr(pr, "fetch_open_meteo_forecast", _none)

    # N-232: Die OM-Verteilung für übermorgen kommt aus dem Prognose-Kanon, und
    # der ruft `sfs.get_solar_prognose` — bis 11.08.2026 ungemockt, also über
    # das echte Netz. Lokal antwortete Open-Meteo (grün), im CI kam ein Timeout
    # ⇒ keine Verteilung ⇒ `th_uebermorgen is None`. Der Test prüft die
    # Aufteilung, nicht die Wetterdaten: ein festes Profil macht ihn
    # deterministisch UND netzfrei.
    monkeypatch.setattr(sfs, "get_solar_prognose", _fake_solar_prognose)

    vergleich = await pr.get_prognosen_vergleich(anlage.id, db=db)

    th_morgen = vergleich.solcast_tageshaelften[1]
    assert th_morgen is not None
    assert th_morgen.vormittag_kwh == pytest.approx(8.0, abs=0.05), (
        "Solcast legt morgen alles auf Slot 8 — die eigene Kurve, nicht die von OpenMeteo."
    )
    assert th_morgen.nachmittag_kwh == pytest.approx(0.0, abs=0.05)

    # Übermorgen hat kein eigenes Profil → die OpenMeteo-Verteilung bleibt der
    # Weg (Entscheid Gernot: lieber geschätzt als gar keine Zahl). Erkennbar
    # daran, dass die Hälften die Solcast-TAGESMENGE aufteilen (6,0 kWh) und
    # dabei — anders als morgen — beide Hälften belegen.
    th_uebermorgen = vergleich.solcast_tageshaelften[2]
    assert th_uebermorgen is not None
    assert th_uebermorgen.vormittag_kwh + th_uebermorgen.nachmittag_kwh == pytest.approx(6.0, abs=0.1)
    assert th_uebermorgen.nachmittag_kwh > 0.0
