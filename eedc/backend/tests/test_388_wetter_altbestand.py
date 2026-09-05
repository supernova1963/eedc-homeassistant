"""N-388, Nachtrag — der Altbestand der Einstrahlung wird geheilt, ohne den Tag neu zu bauen.

Der Nachzug vom 04.09. (``archiv_nachzug_all``) aggregiert nächtlich den EINEN
Tag neu, der die Archiv-Grenze passiert. Alles, was davor aggregiert war, behielt
den vorläufigen Forecast-Wert — und ließ sich auch nicht heilen: ``aggregate_day``
braucht die Stundenkurve aus der HA-Historie, und die reicht nur ``purge_keep_days``
zurück. Gemessen an coolxmad (#353): sieben August-Tage hielten seinen
Doppelerfassungs-Verdacht am Leben, für die es keinen Reparaturweg gab.

**Was hier gewächtert wird:**

1. Der schmale Pfad schreibt **nur die Wetterzeile** — Stunden-Spalten, Tages-
   aggregat, PR — und lässt jede Energie-Spalte, wie sie ist.
2. Die PR entsteht über **dieselbe Formel** wie im Aggregator (Layer-SoT
   ``core/berechnungen/performance_ratio.py``) — nicht über eine zweite.
3. Der Altbestand läuft **einmal je Anlage** (Marker in ``settings``); ein am
   Abruf gescheiterter Lauf setzt keinen Marker und kommt wieder.
4. Ein vom Vorflug **übersprungener Grenztag** wird per Wetterzeile nachgeholt —
   sonst bliebe genau der Tag vorläufig, für den der Job da ist.
5. Tage **innerhalb** der Archiv-Grenze bleiben unangetastet.

Schwesterdateien: test_archiv_nachzug_wetter.py (der Grenztag-Nachzug per
Neu-Aggregation samt Vorflug, dessen Lücke dieser Pfad schließt).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.core.berechnungen.performance_ratio import berechne_performance_ratio
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil import archiv_nachzug
from backend.services.energie_profil.archiv_nachzug import (
    WETTER_ALTBESTAND_KEY,
    altbestand_marker,
    archiv_grenztag,
    wetter_altbestand_nachziehen,
    wetter_nachzug_all,
)
from backend.tests import factories

_BACKEND = Path(__file__).resolve().parents[1]
HEUTE = date(2026, 9, 4)
KWP = 10.0
PV_STUNDEN = range(8, 18)  # 10 h × 1 kW = 10 kWh
GTI_ARCHIV = 600.0          # W/m² je PV-Stunde → 6.000 Wh/m² am Tag
GHI_ARCHIV = 500.0


@pytest.fixture
def job_session(monkeypatch, db):
    @asynccontextmanager
    async def _fake():
        yield db

    monkeypatch.setattr(archiv_nachzug, "get_session", _fake)
    return db


def _archiv(*tage: date) -> dict:
    """Die Archiv-Antwort: je Tag 24 Stunden, GTI nur in den PV-Stunden."""
    return {
        tag: {
            h: {
                "temperatur_c": 10.0 + h / 10, "globalstrahlung_wm2": GHI_ARCHIV if h in PV_STUNDEN else 0.0,
                "gti_wm2": GTI_ARCHIV if h in PV_STUNDEN else 0.0,
                "bewoelkung_prozent": 40.0, "niederschlag_mm": 0.0, "wetter_code": 3,
            }
            for h in range(24)
        }
        for tag in tage
    }


async def _anlage_mit_tagen(db, *tage: date, sonstiges_erzeuger_kwh: float | None = None):
    """Eine Anlage, deren Tage mit dem VORLÄUFIGEN Wert aggregiert sind (GHI 20, kein GTI)."""
    anlage = await factories.anlage(db, latitude=49.7, longitude=7.9, leistung_kwp=KWP)
    await factories.investition(
        db, anlage.id, "pv-module", leistung_kwp=KWP, anschaffungsdatum=date(2020, 1, 1),
    )
    sonst = None
    if sonstiges_erzeuger_kwh is not None:
        sonst = await factories.investition(
            db, anlage.id, "sonstiges", parameter={"kategorie": "erzeuger"},
            anschaffungsdatum=date(2020, 1, 1),
        )
    for tag in tage:
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=h,
                pv_kw=1.0 if h in PV_STUNDEN else 0.0, verbrauch_kw=0.4,
                globalstrahlung_wm2=20.0, bewoelkung_prozent=90.0, wetter_code=61,
            ))
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=tag, stunden_verfuegbar=24,
            strahlung_summe_wh_m2=200.0, gti_summe_wh_m2=None, performance_ratio=3.35,
            komponenten_kwh=(
                {f"sonstiges_{sonst.id}": sonstiges_erzeuger_kwh} if sonst else None
            ),
        ))
    await db.commit()
    return anlage


async def _tz(db, anlage_id, tag):
    return (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum == tag,
    ))).scalars().one()


async def _stunde(db, anlage_id, tag, h):
    return (await db.execute(select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage_id, TagesEnergieProfil.datum == tag,
        TagesEnergieProfil.stunde == h,
    ))).scalars().one()


# ── 2: eine Formel ───────────────────────────────────────────────────────────

def test_pr_formel_und_ihre_luecken():
    assert berechne_performance_ratio(10.0, 6000.0, 10.0) == pytest.approx(0.167)
    assert berechne_performance_ratio(None, 6000.0, 10.0) is None   # keine PV-Stunde gemessen
    assert berechne_performance_ratio(10.0, 0.0, 10.0) is None      # keine Einstrahlung
    assert berechne_performance_ratio(10.0, 6000.0, 0.0) is None    # keine kWp


def test_der_aggregator_rechnet_die_pr_nicht_mehr_selbst():
    quelle = (_BACKEND / "services" / "energie_profil" / "aggregator.py").read_text(encoding="utf-8")
    assert "berechne_performance_ratio(" in quelle
    assert "theoretisch_kwh" not in quelle, "die Formel steht ein zweites Mal im Aggregator"


# ── 1: nur die Wetterzeile ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_altbestand_berichtigt_wetter_und_pr_und_laesst_energie_stehen(db):
    d1, d2 = date(2026, 8, 18), date(2026, 8, 19)
    anlage = await _anlage_mit_tagen(db, d1, d2)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(d1, d2))) as f:
        erg = await wetter_altbestand_nachziehen(anlage, db, bis=date(2026, 8, 28))
        await db.commit()

    assert erg["status"] == "ok" and erg["tage"] == 2
    # EIN Abruf für den ganzen Bereich, nicht einer je Tag.
    assert f.await_count == 1
    _, url, params, *_ = f.await_args.args
    assert "archive" in url and params == {"start_date": "2026-08-18", "end_date": "2026-08-19"}

    for tag in (d1, d2):
        tz = await _tz(db, anlage.id, tag)
        assert tz.gti_summe_wh_m2 == pytest.approx(6000.0)
        assert tz.strahlung_summe_wh_m2 == pytest.approx(5000.0)
        assert tz.performance_ratio == pytest.approx(0.167)   # 10 kWh ÷ (6.000 × 10 ÷ 1000)
        assert tz.temperatur_min_c == pytest.approx(10.0) and tz.temperatur_max_c == pytest.approx(12.3)
        mittag = await _stunde(db, anlage.id, tag, 12)
        assert mittag.globalstrahlung_wm2 == GHI_ARCHIV
        assert mittag.bewoelkung_prozent == 40.0 and mittag.wetter_code == 3
        # Energie unangetastet.
        assert mittag.pv_kw == 1.0 and mittag.verbrauch_kw == 0.4
        assert tz.stunden_verfuegbar == 24


@pytest.mark.asyncio
async def test_sonstiges_erzeuger_wird_aus_dem_pr_zaehler_genommen(db):
    d1 = date(2026, 8, 18)
    anlage = await _anlage_mit_tagen(db, d1, sonstiges_erzeuger_kwh=3.0)
    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(d1))):
        await wetter_altbestand_nachziehen(anlage, db, bis=date(2026, 8, 28))
        await db.commit()
    tz = await _tz(db, anlage.id, d1)
    # (10 − 3) kWh ÷ 60 kWh theoretisch — wie im Aggregator ohne BHKW-Anteil.
    assert tz.performance_ratio == pytest.approx(0.117)


@pytest.mark.asyncio
async def test_tag_ohne_archivwert_bleibt_wie_er_ist(db):
    d1, d2 = date(2026, 8, 18), date(2026, 8, 19)
    anlage = await _anlage_mit_tagen(db, d1, d2)
    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(d1))):
        erg = await wetter_altbestand_nachziehen(anlage, db, bis=date(2026, 8, 28))
        await db.commit()
    assert erg["tage"] == 1 and erg["ohne_wetter"] == 1
    tz = await _tz(db, anlage.id, d2)
    assert tz.performance_ratio == 3.35 and tz.gti_summe_wh_m2 is None


@pytest.mark.asyncio
async def test_gescheiterter_abruf_meldet_fehler_und_schreibt_nichts(db):
    d1 = date(2026, 8, 18)
    anlage = await _anlage_mit_tagen(db, d1)
    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(side_effect=RuntimeError("503"))):
        erg = await wetter_altbestand_nachziehen(anlage, db, bis=date(2026, 8, 28))
    assert erg["status"] == "fehler"
    tz = await _tz(db, anlage.id, d1)
    assert tz.performance_ratio == 3.35


# ── 3 + 4 + 5: der Job-Schritt ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_altbestand_laeuft_einmal_je_anlage(db, job_session):
    grenztag = archiv_grenztag(HEUTE)
    alt = date(2026, 8, 18)
    drinnen = grenztag + timedelta(days=1)
    anlage = await _anlage_mit_tagen(db, alt, drinnen)

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(alt))) as f:
        erst = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)
        zweit = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)

    assert erst[anlage.id]["altbestand"]["status"] == "ok"
    assert erst[anlage.id]["altbestand"]["tage"] == 1
    assert zweit == {}, "zweite Nacht: Marker steht, nichts läuft"
    assert f.await_count == 1
    # Der Bereich endet VOR dem Grenztag — der gehört dem Aggregator-Schritt.
    _, _, params, *_ = f.await_args.args
    assert params["end_date"] == alt.isoformat()

    marker = await altbestand_marker(db)
    assert marker[str(anlage.id)]["bis"] == (grenztag - timedelta(days=1)).isoformat()
    assert marker[str(anlage.id)]["tage"] == 1

    # Der Tag innerhalb der Grenze ist unangetastet (5).
    tz = await _tz(db, anlage.id, drinnen)
    assert tz.performance_ratio == 3.35 and tz.gti_summe_wh_m2 is None


@pytest.mark.asyncio
async def test_gescheiterter_altbestand_setzt_keinen_marker(db, job_session):
    anlage = await _anlage_mit_tagen(db, date(2026, 8, 18))
    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(side_effect=RuntimeError("503"))):
        erg = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)
    assert erg[anlage.id]["altbestand"]["status"] == "fehler"
    assert str(anlage.id) not in await altbestand_marker(db)
    assert WETTER_ALTBESTAND_KEY  # der Schlüssel existiert und ist benannt


@pytest.mark.asyncio
async def test_uebersprungener_grenztag_wird_per_wetterzeile_nachgeholt(db, job_session):
    grenztag = archiv_grenztag(HEUTE)
    anlage = await _anlage_mit_tagen(db, grenztag)
    # Altbestand schon erledigt — nur der Grenztag steht an.
    await archiv_nachzug.altbestand_merken(db, anlage.id, {"bis": "x", "am": "x", "tage": 0, "status": "ok"})
    await db.commit()

    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock(return_value=_archiv(grenztag))) as f:
        erg = await wetter_nachzug_all(
            {anlage.id: {"status": "uebersprungen", "grund": "kurve_geschrumpft"}}, heute=HEUTE,
        )

    assert erg[anlage.id]["grenztag"]["status"] == "ok"
    _, _, params, *_ = f.await_args.args
    assert params == {"start_date": grenztag.isoformat(), "end_date": grenztag.isoformat()}
    tz = await _tz(db, anlage.id, grenztag)
    assert tz.performance_ratio == pytest.approx(0.167)


@pytest.mark.asyncio
async def test_gelungener_grenztag_wird_nicht_doppelt_geholt(db, job_session):
    grenztag = archiv_grenztag(HEUTE)
    anlage = await _anlage_mit_tagen(db, grenztag)
    await archiv_nachzug.altbestand_merken(db, anlage.id, {"bis": "x", "am": "x", "tage": 0, "status": "ok"})
    await db.commit()
    with patch.object(archiv_nachzug, "_fetch_wetter", new=AsyncMock()) as f:
        erg = await wetter_nachzug_all({anlage.id: {"status": "ok"}}, heute=HEUTE)
    assert erg == {} and f.await_count == 0
