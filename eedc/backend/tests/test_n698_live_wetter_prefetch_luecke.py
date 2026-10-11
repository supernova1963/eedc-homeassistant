"""N-698: ein unvollständiger Cache-Eintrag (Prefetch ohne Fan-out) wird nicht verwendet.

⛔ **Der Defekt** (Analyse §C3, nachgemessen im Bau Päckchen E): Seit N-690 cacht
``_lade_forecast_gecached`` einen unvollständigen Multi-String-Fan-out nicht.
Der Prefetch (``prefetch_service._prefetch_live_wetter``, alle 45 min, schreibt
nur bei leerem Schlüssel) füllte diese Lücke mit ``(data, None, False)`` — einem
Abruf OHNE Fan-out. Der nächste Aufruf der Route nahm ihn: ``multi_gti=None`` ⇒
der lokale Pfad rechnet mit der Globalstrahlung statt der Einstrahlung auf die
Module, ``_teilsumme_hinweis`` schweigt (keine Teilsumme), 0 neue Abrufe, bis zu
60 min. Ist der Kanon im Ausfall leer (N-423), zeigt die Kachel genau diesen
Wert. Gemessen an der gestellten Ost/West-Anlage unten: voll **38,8 kWh**,
Teil-Abruf **19,3 kWh mit Hinweis**, nach dem Prefetch **31,0 kWh ohne Hinweis**
(Kachel „Heute 31,0 kWh", kein Hinweis).

**Was jetzt gilt** (dieselbe Regel wie N-690, von der Leseseite): ein Eintrag
mit ``multi_vollstaendig=False`` wird nicht verwendet — die Route holt den
Fan-out selbst; ist er vollständig, überschreibt er den Eintrag, sonst sagt die
Antwort es (N-690-Hinweis). Der Prefetch selbst bleibt unverändert (seine
Markierung ``False`` ist von ``test_multi_string_forecast_robustness_306.py``
gewächtert).

Gestellt: ``httpx.AsyncClient`` (Open-Meteo: Haupt-Abruf ohne GTI, Ost liefert,
West antwortet 429), der Kanon in N-423-Form (Teil-Fan-out ⇒ leer) und die
Nähte aus ``test_n690_live_wetter_teilsumme.py``. Der Cache ist der echte (L1).
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest
from sqlalchemy import select

from backend.api.routes import live_wetter
from backend.api.routes.live_wetter import LiveWetterResponse, get_live_wetter
from backend.models import Anlage, Investition
from backend.services import prefetch_service
from backend.services.wetter import cache as wetter_cache

pytestmark = pytest.mark.asyncio

TAG = "2026-03-10"
GHI = [0.0] * 6 + [300.0] * 12 + [0.0] * 6
GTI = {-90: [0.0] * 6 + [500.0] * 6 + [250.0] * 6 + [0.0] * 6,
       90: [0.0] * 6 + [250.0] * 6 + [500.0] * 6 + [0.0] * 6}


def _om() -> dict:
    times = [f"{TAG}T{h:02d}:00" for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times, "temperature_2m": [12.0] * n, "weather_code": [1] * n,
            "cloud_cover": [30] * n, "precipitation": [0.0] * n, "shortwave_radiation": GHI,
            "sunshine_duration": [0.0] * 6 + [3000.0] * 12 + [0.0] * 6,
        },
        "daily": {"temperature_2m_min": [6.0], "temperature_2m_max": [15.0],
                  "sunrise": [f"{TAG}T06:40"], "sunset": [f"{TAG}T18:10"]},
    }


class _Resp:
    def __init__(self, status: int, body: dict):
        self.status_code, self._body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "http://open-meteo.test")
            raise httpx.HTTPStatusError("gestellt", request=req,
                                        response=httpx.Response(self.status_code, request=req))

    def json(self):
        return self._body


@pytest.fixture
def om(monkeypatch):
    """Open-Meteo gestellt; ``om["west_faellt_aus"]`` steuert den Teil-Ausfall, ``om["abrufe"]`` zählt."""
    stand = {"west_faellt_aus": True, "abrufe": 0}

    class _Client:
        def __init__(self, *a, **k):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):  # noqa: ARG002
            stand["abrufe"] += 1
            p = params or {}
            if p.get("hourly") == "global_tilted_irradiance":
                if p.get("azimuth") == 90 and stand["west_faellt_aus"]:
                    return _Resp(429, {})
                return _Resp(200, {"hourly": {"global_tilted_irradiance": GTI[p.get("azimuth")]}})
            return _Resp(200, _om())

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return stand


@pytest.fixture
def naehte(monkeypatch):
    import backend.services.ha_state_service as hss
    import backend.services.mqtt_inbound_service as mis
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as scs
    import backend.services.verbrauchsprognose_heute as vph
    from backend.services.prognose_kanon import KanonPrognose, KanonTag

    async def _keins(*a, **k):  # noqa: ARG001
        return None

    async def _kanon_leer(*a, **k):  # noqa: ARG001
        tag = KanonTag(datum=TAG, om_kwh=None, eedc_kwh=None, vm_kwh=None, nm_kwh=None, profil=None,
                       om_stundenprofil_kwh=None, om_vollstaendig=False)
        return KanonPrognose(tage=[tag], rest_heute_kwh=None, ist_bisher_kwh=13.2,
                             heute_rollend_kwh=None, skalar_fallback=None)

    async def _wahl(*a, **k):  # noqa: ARG001
        return vph.ProfilWahl()

    class _HA:
        is_available = False

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _keins)
    monkeypatch.setattr(live_wetter, "_speichere_prognose", lambda *a, **k: _keins())
    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon_leer)
    monkeypatch.setattr(vph, "waehle_verbrauchsprofil", _wahl)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _HA())
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(scs, "get_solcast_forecast", _keins)


@pytest.fixture
async def anlage(db):
    a = Anlage(anlagenname="N-698", leistung_kwp=10.0, latitude=48.698, longitude=11.698)
    db.add(a)
    await db.flush()
    for name, azimut in (("Ost", -90), ("West", 90)):
        db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name,
                           anschaffungsdatum=date(2024, 1, 1), leistung_kwp=5.0,
                           neigung_grad=30.0, parameter={"ausrichtung_grad": azimut}))
    await db.flush()
    gruppen = live_wetter._get_pv_orientierungsgruppen(list((await db.execute(
        select(Investition).where(Investition.anlage_id == a.id))).scalars()))
    key = live_wetter.live_wetter_cache_key(a.latitude, a.longitude, gruppen, "auto")
    wetter_cache._cache.pop(key, None)
    yield a, gruppen, key
    wetter_cache._cache.pop(key, None)


async def _route(db, a) -> dict:
    roh = await get_live_wetter(anlage_id=a.id, demo=False, db=db)
    return LiveWetterResponse.model_validate(roh).model_dump(mode="json")


async def test_prefetch_eintrag_ersetzt_den_teilausfall_nicht_still(db, om, naehte, anlage):
    a, gruppen, key = anlage
    teil = await _route(db, a)
    assert teil["pv_prognose_hinweis"] and teil["pv_prognose_kwh"] == pytest.approx(19.3, abs=0.05)
    assert wetter_cache._cache_get(key) is None          # N-690: nicht gecacht

    await prefetch_service._prefetch_live_wetter(a.latitude, a.longitude, gruppen, "auto")
    eintrag = wetter_cache._cache_get(key)
    assert eintrag is not None and eintrag[1] is None and eintrag[2] is False   # (data, None, False)

    om["abrufe"] = 0
    danach = await _route(db, a)
    assert om["abrufe"] == 3, (
        f"Die Route nahm den Prefetch-Eintrag ohne Fan-out ({om['abrufe']} Abrufe) — "
        f"PV {danach['pv_prognose_kwh']} kWh aus der Globalstrahlung, Hinweis "
        f"{danach['pv_prognose_hinweis']!r} (N-698)."
    )
    assert danach["pv_prognose_hinweis"], "Teil-Ausfall nach dem Prefetch ohne Hinweis (N-698)."
    assert danach["pv_prognose_kwh"] == pytest.approx(teil["pv_prognose_kwh"])


async def test_nach_dem_ausfall_ueberschreibt_der_volle_abruf_den_eintrag(db, om, naehte, anlage):
    a, gruppen, key = anlage
    await prefetch_service._prefetch_live_wetter(a.latitude, a.longitude, gruppen, "auto")
    om["west_faellt_aus"] = False

    voll = await _route(db, a)
    assert voll["pv_prognose_hinweis"] is None
    assert voll["pv_prognose_kwh"] == pytest.approx(38.8, abs=0.05)
    eintrag = wetter_cache._cache_get(key)
    assert eintrag is not None and eintrag[2] is True and eintrag[1] is not None

    om["abrufe"] = 0
    await _route(db, a)
    assert om["abrufe"] == 0, "Der vollständige Eintrag wird wieder aus dem Cache bedient."


async def test_vollstaendiger_eintrag_einer_gruppe_wird_weiter_verwendet(db, om, naehte):
    """Gegenfall: der Prefetch-Eintrag einer Ein-Gruppen-Anlage ist vollständig (GTI im Haupt-Abruf)."""
    a = Anlage(anlagenname="N-698 eine Gruppe", leistung_kwp=10.0, latitude=47.698, longitude=10.698)
    db.add(a)
    await db.flush()
    db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
                       neigung_grad=30.0, parameter={"ausrichtung_grad": 0}))
    await db.flush()
    gruppen = live_wetter._get_pv_orientierungsgruppen(list((await db.execute(
        select(Investition).where(Investition.anlage_id == a.id))).scalars()))
    key = live_wetter.live_wetter_cache_key(a.latitude, a.longitude, gruppen, "auto")
    wetter_cache._cache.pop(key, None)
    try:
        await prefetch_service._prefetch_live_wetter(a.latitude, a.longitude, gruppen, "auto")
        assert wetter_cache._cache_get(key)[2] is True
        om["abrufe"] = 0
        await _route(db, a)
        assert om["abrufe"] == 0
    finally:
        wetter_cache._cache.pop(key, None)
