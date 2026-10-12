"""N-730 — der Wetter-Nachzug aus dem Archiv gewichtet das GTI mit den Modulen, die AM TAG in Betrieb waren.

`services/energie_profil/archiv_nachzug.py::wetter_nachziehen_bereich` holte das Archiv-Wetter für den ganzen Bereich mit
ALLEN aktiven Modulen (Filter nur `aktiv`), `aggregate_day` dagegen mit den am Tag aktiven (`aktiv_am_tag`, Audit §6.4).
Bei einem Zubau mit anderer Ausrichtung ging dessen GTI damit in die Tage VOR seiner Anschaffung ein (kWp-gewichtet), der
kWp-Nenner der Performance Ratio aber nicht (`anlagen_kwp(…, datum)`) — die PR stand verschoben.

Wetter-Mock (kein Abruf nach außen): Open-Meteo antwortet je Azimut — Süd 1 000 W/m², West 500 W/m² in der Mittagsstunde.
Süd 6 kWp seit 2020, West 4 kWp ab 10.06.2026. Am 01.06. zählt nur Süd: GTI 1 000 Wh/m², PR 4,8 kWh ÷ (1 kWh/m² × 6 kWp)
= 0,80. Am HEAD `7fb9b026` gemessen: GTI 800 (0,6 × 1 000 + 0,4 × 500), PR 1,00 (+25 %).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

MITTAG = 12
GTI_JE_AZIMUT = {0: 1000.0, 90: 500.0}


class _Antwort:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _OpenMeteoMock:
    """Ersetzt `httpx.AsyncClient`: GTI je Azimut, die Stundenreihe über den angefragten Bereich."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        params = params or {}
        von = date.fromisoformat(params["start_date"])
        bis = date.fromisoformat(params["end_date"])
        zeiten = []
        d = von
        while d <= bis:
            zeiten += [f"{d.isoformat()}T{h:02d}:00" for h in range(24)]
            d = date.fromordinal(d.toordinal() + 1)
        n = len(zeiten)
        hourly = {"time": zeiten}
        variablen = params.get("hourly", "").split(",")
        if "temperature_2m" in variablen:
            hourly.update({
                "temperature_2m": [15.0] * n, "shortwave_radiation": [0.0] * n, "cloud_cover": [50.0] * n,
                "precipitation": [0.0] * n, "weather_code": [3] * n,
            })
        if "global_tilted_irradiance" in variablen:
            gti = GTI_JE_AZIMUT[int(params["azimuth"])]
            hourly["global_tilted_irradiance"] = [gti if int(t[11:13]) == MITTAG else 0.0 for t in zeiten]
        return _Antwort({"hourly": hourly})


async def _anlage(db) -> Anlage:
    a = Anlage(anlagenname="N730", leistung_kwp=10.0, latitude=49.7, longitude=7.9)
    db.add(a)
    await db.flush()
    db.add_all([
        Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0,
                    anschaffungsdatum=date(2020, 1, 1), parameter={"ausrichtung_grad": 0, "neigung_grad": 30}),
        Investition(anlage_id=a.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0,
                    anschaffungsdatum=date(2026, 6, 10), parameter={"ausrichtung_grad": 90, "neigung_grad": 30}),
    ])
    for tag in (date(2026, 6, 1), date(2026, 6, 15)):
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=tag, stunden_verfuegbar=24, komponenten_kwh={}))
        for h in range(24):
            db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag, stunde=h, pv_kw=(4.8 if h == MITTAG else 0.0)))
    await db.commit()
    return a


async def _tz(db, anlage_id, tag):
    return (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum == tag))).scalars().one()


@pytest.mark.asyncio
async def test_zubau_mit_anderer_ausrichtung_zaehlt_erst_ab_seiner_anschaffung(db):
    from backend.services.energie_profil.archiv_nachzug import wetter_nachziehen_bereich

    a = await _anlage(db)
    with patch("httpx.AsyncClient", new=_OpenMeteoMock):
        erg = await wetter_nachziehen_bereich(a, db, date(2026, 6, 1), date(2026, 6, 15))
    await db.commit()
    assert erg["status"] == "ok" and erg["tage"] == 2

    vor = await _tz(db, a.id, date(2026, 6, 1))
    assert vor.gti_summe_wh_m2 == pytest.approx(1000.0)        # nur Süd (am HEAD: 800)
    assert vor.performance_ratio == pytest.approx(0.80, abs=0.005)

    nach = await _tz(db, a.id, date(2026, 6, 15))
    assert nach.gti_summe_wh_m2 == pytest.approx(800.0)        # Süd + West kWp-gewichtet
    assert nach.performance_ratio == pytest.approx(4.8 / (0.8 * 10.0), abs=0.005)
