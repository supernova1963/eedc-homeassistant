"""N-697: ein Grenztag ohne GTI wird im nächtlichen Archiv-Nachzug nachgeholt.

⛔ **Der Defekt:** Der 02:20-Job zieht den Grenztag per ``aggregate_day`` neu
(``nachzug_anlage``). Fällt dabei der Wetterabruf ganz oder für eine
Orientierungsgruppe aus, liefert ``_fetch_wetter`` seit N-690 kein GTI —
``aggregate_day`` schreibt den Tag mit ``gti_summe_wh_m2 = None`` und
``performance_ratio = None`` und meldet ``ok`` (Analyse §C5, Probe
``test_n690::test_zwilling_teilausfall_liefert_kein_gti_und_keine_pr``).
Schritt (1) von ``wetter_nachzug_all`` holte nur ``uebersprungen``/
``keine_daten`` nach — weder diesen Tag noch einen ``fehler`` von
``aggregate_day``. Am nächsten Abend ist ein anderer Tag Grenztag, der
Altbestand-Nachzug lief schon: der Tag blieb **dauerhaft** ohne GTI und PR
(*Cockpit → Tag*, *Auswertungen → Tabelle*), und kein Daten-Checker meldet es.

**Was jetzt gilt:** Schritt (1) zieht die Wetterzeile über den schmalen,
strengen Pfad (``wetter_nachziehen_bereich``) nach für
* den Grenztag bei ``uebersprungen``/``keine_daten``/**``fehler``**, und
* jeden gespeicherten Tag der letzten ``GTI_NACHHOL_TAGE`` bis einschließlich
  Grenztag, dem das **GTI fehlt** (nur mit Koordinaten und aktiven PV-Modulen —
  sonst gibt es kein GTI). Scheitert auch dieser Abruf, versucht es die nächste
  Nacht; nach dem Fenster fällt der Tag heraus (kein Dauerlauf).
Solange der Altbestand der Anlage nicht erledigt ist, gilt nur der Grenztag —
die älteren Tage holt Schritt (2) ohnehin.

Gestellt ist nur ``archiv_nachzug._fetch_wetter`` (wie in
``test_388_wetter_altbestand.py``). Schwesterdateien:
``test_388_wetter_altbestand.py``, ``test_archiv_nachzug_wetter.py``,
``test_n690_live_wetter_teilsumme.py``.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil import archiv_nachzug
from backend.services.energie_profil.archiv_nachzug import (
    GTI_NACHHOL_TAGE,
    altbestand_merken,
    archiv_grenztag,
    wetter_nachzug_all,
)
from backend.tests import factories

pytestmark = pytest.mark.asyncio

HEUTE = date(2026, 10, 11)
KWP = 10.0
PV_STUNDEN = range(8, 18)   # 10 h × 1 kW = 10 kWh
GTI_ARCHIV = 600.0          # W/m² je PV-Stunde → 6 000 Wh/m², PR 10 ÷ (6 000 × 10 ÷ 1 000) = 0,167


@pytest.fixture
def job_session(monkeypatch, db):
    @asynccontextmanager
    async def _fake():
        yield db

    monkeypatch.setattr(archiv_nachzug, "get_session", _fake)
    return db


def _archiv(*tage: date) -> dict:
    return {
        tag: {
            h: {
                "temperatur_c": 10.0, "globalstrahlung_wm2": 500.0 if h in PV_STUNDEN else 0.0,
                "gti_wm2": GTI_ARCHIV if h in PV_STUNDEN else 0.0,
                "bewoelkung_prozent": 40.0, "niederschlag_mm": 0.0, "wetter_code": 3,
            }
            for h in range(24)
        }
        for tag in tage
    }


async def _anlage(db, *tage: date, gti: float | None = None, pv: bool = True, altbestand: bool = True):
    """Eine Anlage, deren Tage nach dem Aggregator-Lauf mit ``gti`` (None = ausgefallen) dastehen."""
    anlage = await factories.anlage(db, latitude=49.7, longitude=7.9, leistung_kwp=KWP)
    if pv:
        await factories.investition(
            db, anlage.id, "pv-module", leistung_kwp=KWP, anschaffungsdatum=date(2020, 1, 1),
        )
    for tag in tage:
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=h,
                pv_kw=1.0 if h in PV_STUNDEN else 0.0, verbrauch_kw=0.4,
                globalstrahlung_wm2=20.0,
            ))
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=tag, stunden_verfuegbar=24,
            strahlung_summe_wh_m2=200.0, gti_summe_wh_m2=gti,
            performance_ratio=None if gti is None else 0.5,
        ))
    if altbestand:
        await altbestand_merken(db, anlage.id, {"bis": "x", "am": "x", "tage": 0, "status": "ok"})
    await db.commit()
    return anlage


async def _tz(db, anlage_id, tag) -> TagesZusammenfassung:
    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum == tag,
    ))).scalars().one()
    await db.refresh(tz)
    return tz


def _bereich(f) -> tuple[str, str]:
    _, _, params, *_ = f.await_args.args
    return params["start_date"], params["end_date"]


async def test_grenztag_ok_ohne_gti_wird_in_derselben_nacht_nachgeholt(db, job_session):
    """Der Fall der Analyse: Teil-Ausfall am Grenztag ⇒ `ok`, aber kein GTI und keine PR."""
    grenztag = archiv_grenztag(HEUTE)
    anlage = await _anlage(db, grenztag, gti=None)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(grenztag))) as f:
        erg = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)

    assert f.await_count == 1, (
        "Grenztag mit Status `ok`, aber ohne GTI — Schritt (1) holt ihn nicht nach; "
        "er bliebe dauerhaft ohne GTI und Performance Ratio (N-697)."
    )
    assert _bereich(f) == (grenztag.isoformat(), grenztag.isoformat())
    assert f.await_args.kwargs.get("streng") is True   # der strenge Pfad (N-690)
    assert erg[anlage.id]["grenztag"]["status"] == "ok"
    tz = await _tz(db, anlage.id, grenztag)
    assert tz.gti_summe_wh_m2 == pytest.approx(6000.0)
    assert tz.performance_ratio == pytest.approx(0.167, abs=1e-3)


async def test_fehler_von_aggregate_day_wird_nachgeholt(db, job_session):
    """Brach die Neuaggregation ab, steht der Tag beim vorläufigen Wert — er wird nachgezogen."""
    grenztag = archiv_grenztag(HEUTE)
    anlage = await _anlage(db, grenztag, gti=3000.0)   # vorläufiger Forecast-Wert

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(grenztag))) as f:
        erg = await wetter_nachzug_all({anlage.id: {"status": "fehler", "error": "x"}}, heute=HEUTE)

    assert f.await_count == 1, "Ein `fehler` von aggregate_day wird nicht nachgeholt (N-697)."
    assert erg[anlage.id]["grenztag"]["status"] == "ok"
    assert (await _tz(db, anlage.id, grenztag)).gti_summe_wh_m2 == pytest.approx(6000.0)


async def test_scheitert_der_abruf_versucht_es_die_naechste_nacht(db, job_session):
    """Nacht 1: auch der Nachzug scheitert ⇒ nichts geschrieben. Nacht 2: der Tag ist nicht mehr
    Grenztag, fehlt aber weiter ⇒ wird nachgeholt."""
    grenztag = archiv_grenztag(HEUTE)
    anlage = await _anlage(db, grenztag, gti=None)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(side_effect=RuntimeError("429"))):
        nacht1 = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)
    assert nacht1[anlage.id]["grenztag"]["status"] == "fehler"
    assert (await _tz(db, anlage.id, grenztag)).gti_summe_wh_m2 is None

    morgen = HEUTE + timedelta(days=1)
    assert archiv_grenztag(morgen) != grenztag
    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(grenztag))) as f:
        nacht2 = await wetter_nachzug_all({anlage.id: {"status": "kein_tag"}}, heute=morgen)

    assert f.await_count == 1, "Der Tag von gestern kommt in der nächsten Nacht nicht wieder dran (N-697)."
    assert _bereich(f) == (grenztag.isoformat(), grenztag.isoformat())
    assert nacht2[anlage.id]["grenztag"]["status"] == "ok"
    assert (await _tz(db, anlage.id, grenztag)).gti_summe_wh_m2 == pytest.approx(6000.0)


async def test_das_fenster_endet(db, job_session):
    """Kein Dauerlauf: ein Tag älter als das Fenster wird nicht mehr angefragt."""
    grenztag = archiv_grenztag(HEUTE)
    zu_alt = grenztag - timedelta(days=GTI_NACHHOL_TAGE)
    letzter = grenztag - timedelta(days=GTI_NACHHOL_TAGE - 1)
    anlage = await _anlage(db, zu_alt, letzter, gti=None)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(letzter))) as f:
        await wetter_nachzug_all({anlage.id: {"status": "kein_tag"}}, heute=HEUTE)

    assert f.await_count == 1
    assert _bereich(f) == (letzter.isoformat(), letzter.isoformat())
    assert (await _tz(db, anlage.id, zu_alt)).gti_summe_wh_m2 is None


async def test_ohne_pv_module_gibt_es_kein_gti_und_keinen_abruf(db, job_session):
    """Gegenfall: eine Anlage ohne PV-Module hat nie ein GTI — kein nächtlicher Abruf deswegen."""
    grenztag = archiv_grenztag(HEUTE)
    anlage = await _anlage(db, grenztag, gti=None, pv=False)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock()) as f:
        erg = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)

    assert erg == {} and f.await_count == 0


async def test_vor_dem_altbestand_gilt_nur_der_grenztag(db, job_session):
    """Ohne Altbestand-Marker holt Schritt (2) die älteren Tage — Schritt (1) fragt sie nicht doppelt an."""
    grenztag = archiv_grenztag(HEUTE)
    vorgestern = grenztag - timedelta(days=2)
    anlage = await _anlage(db, vorgestern, gti=None, altbestand=False)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(vorgestern))) as f:
        erg = await wetter_nachzug_all({anlage.id: {"status": "kein_tag"}}, heute=HEUTE)

    assert "grenztag" not in erg[anlage.id]
    assert erg[anlage.id]["altbestand"]["status"] == "ok"
    assert f.await_count == 1
