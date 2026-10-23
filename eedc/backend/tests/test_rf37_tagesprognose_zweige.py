"""RF-37 — benannte Probe für die Zweige von ``get_tagesprognose``, die kein Golden Master und kein Bestandstest erreicht.

Gemessen im Komplexitäts-Paket, Sitzung C (23.10.2026, Bedingungs-Abdeckung per Import-Hook): der Worktree-GM
``skript-golden-master-energie-profil.py --prognose`` (zwei vergangene Tage je Anlage auf drei DB-Kopien + unbekannte
Anlage) und die 19 Testdateien, die ``tagesprognose`` nennen, lassen zusammen 18 von 96 Bedingungs-Seiten und beide
``except``-Zweige offen. Diese Probe stellt jede davon her:

* 400 ohne Koordinaten (Breite fehlt / Länge fehlt);
* Solcast: Abruf wirft (Hinweis «nicht abrufbar», weiter mit dem Kanon), Solcast ohne Antwort, ohne eigenes Tagesprofil
  mit weniger als 24 bzw. ohne Stundenwerte, heutiges Profil für HEUTE (kein Näherungs-Hinweis);
* OpenMeteo-Rückfall: kein am Zieltag aktiver String, ein Tag ohne Stundenwerte und ein fremder Tag (Schleife läuft
  durch), Lernfaktor gesetzt, Lernfaktor wirft NACH der Summe (die Summe bleibt stehen — der Zustand, den RF-37 mit
  ``_PvStand`` bewahrt), Abruf wirft;
* Speicher mit Stilllegung vor und nach dem Zieltag; PV-Profil kürzer als 24 ohne Verbrauch; Verbrauch 0 ⇒ Autarkie 0.

Die Uhr der Route steht fest (``_Heute``, Fake am Modul-Attribut ``prognose.date`` wie in
``test_rf33_trend_tmy_laufendes_jahr.py``): die Probe liest nie die echte Uhr (Wächter
``test_konformitaet_echte_uhr_in_tests.py``). Kein Netz: Kanon, Solcast, OpenMeteo, Verbrauchsprognose und Lernfaktor
sind an den Patch-Zielen der Bestandstests gefakt.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.routes.energie_profil import prognose as P
from backend.models import Anlage, Investition

HEUTE = date(2030, 6, 14)
MORGEN = HEUTE + timedelta(days=1)
VP = {"stunden_kw": [0.5] * 24, "basis": "wochenmuster", "daten_tage": 14}


class _Heute(date):
    """``date.today()`` der Route — festgenagelt auf den 14.06.2030 (keine echte Uhr in Proben)."""

    @classmethod
    def today(cls):  # noqa: D401
        return cls(2030, 6, 14)


async def _anlage(db, *, lat=48.0, lon=11.0, module=(("Süd", 6.0, "Süd", date(2024, 1, 1)),), speicher=()):
    a = Anlage(anlagenname="RF-37", leistung_kwp=10.0, latitude=lat, longitude=lon)
    db.add(a)
    await db.flush()
    for name, kwp, richtung, ab in module:
        db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=kwp, ausrichtung=richtung,
                           neigung_grad=30, anschaffungsdatum=ab, anschaffungskosten_gesamt=1.0))
    for name, kap, still in speicher:
        db.add(Investition(anlage_id=a.id, typ="speicher", bezeichnung=name, anschaffungsdatum=date(2024, 1, 1),
                           stilllegungsdatum=still, anschaffungskosten_gesamt=1.0,
                           parameter={"kapazitaet_kwh": kap, "wirkungsgrad_prozent": 95}))
    await db.commit()
    return a.id


def _fakes(monkeypatch, *, vp=VP, kanon=None, solcast="aus", gsp=None, lernfaktor=None):
    """Patch-Ziele wie in den Bestandstests; `solcast="aus"` = Solcast nicht gewählt."""
    from backend.api.routes import live_wetter as lw
    from backend.services import prognose_router, solar_forecast_service as sfs, solcast_service
    from backend.services import verbrauch_prognose_service as vps

    monkeypatch.setattr(P, "date", _Heute)

    async def _vp(*a, **k):
        return vp
    monkeypatch.setattr(vps, "get_verbrauch_prognose", _vp)

    async def _kanon(*a, **k):
        return kanon
    monkeypatch.setattr(P, "_pv_stunden_aus_kanon", _kanon)

    monkeypatch.setattr(prognose_router, "resolve_prognose_quelle",
                        lambda anlage: SimpleNamespace(ist_solcast=solcast != "aus"))
    if solcast != "aus":
        async def _sc(_anlage):
            if isinstance(solcast, Exception):
                raise solcast
            return solcast
        monkeypatch.setattr(solcast_service, "get_solcast_forecast", _sc)

    aufrufe: list[float] = []

    async def _gsp(**kw):
        aufrufe.append(round(kw["kwp"], 2))
        if isinstance(gsp, Exception):
            raise gsp
        return gsp(kw) if callable(gsp) else gsp
    monkeypatch.setattr(sfs, "get_solar_prognose", _gsp)

    async def _lf(*a, **k):
        if isinstance(lernfaktor, Exception):
            raise lernfaktor
        return lernfaktor
    monkeypatch.setattr(lw, "_get_lernfaktor", _lf)
    return aufrufe


def _solcast(hourly_kw, profile=None):
    from backend.services.solcast_service import SolcastForecast
    return SolcastForecast(daily_kwh=0.0, daily_p10_kwh=0.0, daily_p90_kwh=0.0, tomorrow_kwh=0.0, tomorrow_p10_kwh=0.0,
                           tomorrow_p90_kwh=0.0, hourly_kw=list(hourly_kw), hourly_p10_kw=[0.0] * 24,
                           hourly_p90_kw=[0.0] * 24, tage_voraus=[], stundenprofile=profile or {}, quelle="solcast_api")


def _tag(datum: date, stunden_kw):
    return SimpleNamespace(datum=datum.isoformat(), stunden_kw=stunden_kw)


KEINE_PV = "keine PV-Prognose"


@pytest.mark.asyncio
@pytest.mark.parametrize("lat,lon", [(None, 11.0), (48.0, None)])
async def test_ohne_koordinaten_400(db, monkeypatch, lat, lon):
    _fakes(monkeypatch)
    aid = await _anlage(db, lat=lat, lon=lon)
    with pytest.raises(HTTPException) as e:
        await P.get_tagesprognose(anlage_id=aid, datum=MORGEN, db=db)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_solcast_wirft_hinweis_und_weiter_mit_dem_kanon(db, monkeypatch):
    _fakes(monkeypatch, solcast=RuntimeError("Solcast 500"), kanon=[1.0] * 24)
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=MORGEN, db=db)
    assert r.pv_quelle == "openmeteo" and r.pv_summe_kwh == pytest.approx(24.0)
    assert len(r.hinweise) == 1 and "Solcast-Prognose war nicht abrufbar" in r.hinweise[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("antwort", [None, "23", "leer"])
async def test_solcast_ohne_verwertbares_profil_faellt_auf_den_kanon(db, monkeypatch, antwort):
    sc = {None: None, "23": _solcast([1.0] * 23), "leer": _solcast([])}[antwort]
    _fakes(monkeypatch, solcast=sc, kanon=[2.0] * 24)
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=MORGEN, db=db)
    assert r.pv_quelle == "openmeteo" and r.pv_summe_kwh == pytest.approx(48.0) and r.hinweise == []


@pytest.mark.asyncio
async def test_solcast_heutiges_profil_fuer_heute_ohne_naeherungs_hinweis(db, monkeypatch):
    _fakes(monkeypatch, solcast=_solcast([0.0] * 8 + [1.5] * 8 + [0.0] * 8), kanon=[9.0] * 24)
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=HEUTE, db=db)
    assert r.pv_quelle == "solcast" and r.pv_summe_kwh == pytest.approx(12.0) and r.hinweise == []


@pytest.mark.asyncio
async def test_rueckfall_ohne_aktiven_string_fragt_nichts_ab(db, monkeypatch):
    aufrufe = _fakes(monkeypatch, gsp=None)
    aid = await _anlage(db, module=(("Süd", 6.0, "Süd", MORGEN + timedelta(days=3)),))
    r = await P.get_tagesprognose(anlage_id=aid, datum=MORGEN, db=db)
    assert aufrufe == [] and r.pv_summe_kwh == 0.0
    assert len(r.hinweise) == 1 and KEINE_PV in r.hinweise[0]


@pytest.mark.asyncio
async def test_rueckfall_fremder_tag_leerer_tag_teilsumme_und_lernfaktor(db, monkeypatch):
    def gsp(kw):
        if kw["ausrichtung"] == 0:   # Süd: nur ein fremder Tag und der Zieltag ohne Stundenwerte
            return SimpleNamespace(tageswerte=[_tag(HEUTE, [1.0] * 24), _tag(MORGEN, [])])
        return SimpleNamespace(tageswerte=[_tag(MORGEN, [0.5] * 24)])
    aufrufe = _fakes(monkeypatch, gsp=gsp, lernfaktor=2.0)
    aid = await _anlage(db, module=(("Süd", 6.0, "Süd", date(2024, 1, 1)), ("West", 4.0, "West", date(2024, 1, 1))))
    r = await P.get_tagesprognose(anlage_id=aid, datum=MORGEN, db=db)
    assert sorted(aufrufe) == [4.0, 6.0]
    assert r.pv_summe_kwh == pytest.approx(24.0), "0,5 kW × 24 h × Lernfaktor 2"
    assert len(r.hinweise) == 1 and "Nur 1 von 2 Dachflächen" in r.hinweise[0]


@pytest.mark.asyncio
async def test_rueckfall_lernfaktor_wirft_die_summe_bleibt_stehen(db, monkeypatch):
    _fakes(monkeypatch, gsp=SimpleNamespace(tageswerte=[_tag(MORGEN, [0.5] * 24)]), lernfaktor=RuntimeError("DB weg"))
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=MORGEN, db=db)
    assert r.pv_summe_kwh == pytest.approx(12.0), "die vor der Ausnahme gesetzte Summe bleibt (Lernfaktor nicht angewandt)"
    assert r.hinweise == [], "das Profil ist vorhanden — kein «keine PV-Prognose»"


@pytest.mark.asyncio
async def test_rueckfall_abruf_wirft(db, monkeypatch):
    _fakes(monkeypatch, gsp=RuntimeError("Open-Meteo 429"))
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=MORGEN, db=db)
    assert r.pv_summe_kwh == 0.0 and len(r.hinweise) == 1 and KEINE_PV in r.hinweise[0]


@pytest.mark.asyncio
async def test_speicher_mit_stilllegung_vor_und_nach_dem_zieltag(db, monkeypatch):
    _fakes(monkeypatch, kanon=[1.0] * 24)
    aid = await _anlage(db, speicher=(("alt", 5.0, MORGEN - timedelta(days=1)), ("bleibt", 7.0, MORGEN + timedelta(days=30)),
                                      ("ohne", 3.0, None)))
    r = await P.get_tagesprognose(anlage_id=aid, datum=MORGEN, db=db)
    assert r.speicher_kapazitaet_kwh == pytest.approx(10.0), "7 + 3 kWh; der am Vortag stillgelegte zählt nicht"


@pytest.mark.asyncio
async def test_ohne_verbrauch_und_kurzem_pv_profil(db, monkeypatch):
    _fakes(monkeypatch, vp=None, kanon=[1.0] * 20)
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=MORGEN, db=db)
    assert len(r.stunden) == 24 and [s.pv_kw for s in r.stunden[20:]] == [0.0] * 4
    assert r.pv_summe_kwh == pytest.approx(20.0) and r.autarkie_prozent is None


@pytest.mark.asyncio
async def test_verbrauch_null_ergibt_autarkie_null(db, monkeypatch):
    _fakes(monkeypatch, vp={"stunden_kw": [0.0] * 24, "basis": "wochenmuster", "daten_tage": 3}, kanon=[1.0] * 24)
    r = await P.get_tagesprognose(anlage_id=await _anlage(db), datum=MORGEN, db=db)
    assert r.verbrauch_summe_kwh == 0.0 and r.autarkie_prozent == 0.0
