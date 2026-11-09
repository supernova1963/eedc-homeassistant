"""N-782: das Genauigkeits-Tracking vergleicht je Quelle einen festen Zeitpunkt — und die eedc-Spalte ist die
Prognose, die eedc an dem Tag gezeigt hat.

Bis 9.11.2026 stand in der eedc-Spalte von *Auswertungen → Prognose* (Block ④) «OpenMeteo-Endwert × heutiger
Skalar-Lernfaktor», rückwirkend für alle Tage, und daneben Solcast mit dem per Satellit nachgeführten Abendwert.
Gemessen (Winterborn, 30 Tage): Tabelle eedc +13 % Bias, die gezeigte Prognose abends +4 %.

Geprüft wird:

1. Day-Ahead: eedc = Σ ``pv_prognose_stundenprofil`` — ein gesetzter Lernfaktor ändert daran nichts.
2. Abend: eedc = ``pv_prognose_eedc_final_kwh``; ohne das Feld ``None`` (nicht 0, nicht OM × irgendwas).
3. Solcast, OpenMeteo und SFML je Zeitpunkt aus ihren Feldern; Ausreißer und Kennzahlen aus dem gewählten Stand.
4. ``_speichere_prognose`` schreibt den eedc-Abendstand bei jedem Lauf neu und friert ihn mit
   ``pv_prognose_final_at`` ein; eine Solcast-Nullreihe wird nicht eingefroren, eine echte Reihe schon.
5. Der Prefetch friert das Solcast-Profil des Tages ein — über das Datum, nicht über ``hourly_kw``.
6. ``eedc_mae_prozent`` ohne Lernfaktor; ohne Day-Ahead-Profile ``(None, 0)``.
7. Das neue Feld steht in beiden Prognose-Feldlisten (Neu-Aggregation rettet es).
8. Päckchen CC: Zeitpunkt «Mittag» — first-write ab 12:00 je Spalte, Lesen und Kennzahlen; die Kaskaden-Reihe des
   Korrektur-Wächters first-write; die neuen Spalten in beiden Feldlisten.
9. Päckchen CC: Quellen-Empfehlung — erst ab 14 Tagen, je Zeitpunkt, SFML nicht.

Schwestern: ``test_genauigkeit_ausreisser_296.py``, ``test_genauigkeit_pv_only.py``,
``test_genauigkeit_wetter_296.py`` (dieselbe Route), ``test_prognose_kanon.py`` (Einfrier-Regel des OM-Endwerts),
``test_n547_lern_soll_nicht_zirkulaer.py`` (Lern-SOLL, Prefetch), ``test_migrations_round_trip.py`` (Spalte),
``test_aggregate_day_prognose_rettung.py`` (Rettungsliste).
"""

from __future__ import annotations

import contextlib
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.tests import factories

HEUTE = date(2026, 11, 9)
GESTERN = HEUTE - timedelta(days=1)


class _Tag(date):
    """Feste Uhr für die Route — sie verankert ihr Fenster an ``date.today()``."""

    @classmethod
    def today(cls):  # noqa: D102
        return HEUTE


def _profil(summe: float, stunde: int = 12) -> list[float]:
    """24 Slots, die ganze Menge in einer Stunde — Σ ist exakt ``summe``."""
    return [0.0] * stunde + [summe] + [0.0] * (23 - stunde)


@pytest.fixture
def uhr(monkeypatch):
    from backend.api.routes import prognosen
    monkeypatch.setattr(prognosen, "date", _Tag)


@pytest.fixture
def lernfaktor_13(monkeypatch):
    """Ein Lernfaktor 1,3 — wirkte er noch, läge eedc um 30 % höher."""
    from backend.api.routes import live_wetter

    async def _faktor(*_a, **_k):
        return 1.3

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _faktor)


@pytest.fixture
def sitzung_ist_testdb(db, monkeypatch):
    """``_speichere_prognose`` öffnet eine eigene Sitzung — hier die Test-Sitzung."""
    @contextlib.asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("backend.core.database.get_session", _session)


async def _route(db, anlage_id, zeitpunkt, ausreisser_ausblenden=False):
    from backend.api.routes.prognosen import get_prognosen_genauigkeit
    return await get_prognosen_genauigkeit(
        anlage_id=anlage_id, tage=30, ausreisser_ausblenden=ausreisser_ausblenden, zeitpunkt=zeitpunkt, db=db,
    )


async def _voller_tag(db, anlage_id, datum=GESTERN, **felder):
    """Ein Tag mit allen vier Day-Ahead-Profilen und allen vier Abendständen — jede Zahl verschieden."""
    werte = dict(
        komponenten_kwh={"pv_1": 40.0},
        # Day-Ahead
        lern_soll_stundenprofil_kwh=_profil(44.0),
        pv_prognose_stundenprofil=_profil(42.0),
        solcast_prognose_stundenprofil=_profil(48.0),
        sfml_prognose_stundenprofil=_profil(41.0),
        # Abend
        pv_prognose_kwh=30.0,
        pv_prognose_final_kwh=36.0,
        pv_prognose_eedc_final_kwh=39.0,
        solcast_prognose_kwh=38.0,
        sfml_prognose_kwh=37.0,
    )
    werte.update(felder)
    db.add(TagesZusammenfassung(anlage_id=anlage_id, datum=datum, **werte))
    await db.flush()


# ── 1–3 · Route ─────────────────────────────────────────────────────────────


async def test_day_ahead_eedc_ist_die_summe_des_profils_und_haengt_an_keinem_lernfaktor(db, uhr, lernfaktor_13):
    a = await factories.anlage(db)
    await _voller_tag(db, a.id)
    r = await _route(db, a.id, "day_ahead")
    tag = r.tage[0]
    assert r.zeitpunkt == "day_ahead"
    assert tag.eedc_kwh == 42.0, "eedc Day-Ahead = Σ pv_prognose_stundenprofil, unberührt vom Lernfaktor 1,3"
    assert tag.openmeteo_kwh == 44.0
    assert tag.solcast_kwh == 48.0
    assert tag.sfml_kwh == 41.0
    # Kennzahlen aus denselben Werten: (42 − 40) ÷ 40 = 5 %.
    assert r.eedc_mae_prozent == 5.0 and r.eedc_mbe_prozent == 5.0
    assert r.solcast_mae_prozent == 20.0 and r.openmeteo_mae_prozent == 10.0


async def test_abend_nimmt_die_eingefrorenen_tageswerte(db, uhr, lernfaktor_13):
    a = await factories.anlage(db)
    await _voller_tag(db, a.id)
    r = await _route(db, a.id, "abend")
    tag = r.tage[0]
    assert r.zeitpunkt == "abend"
    assert tag.eedc_kwh == 39.0
    assert tag.openmeteo_kwh == 36.0, "OpenMeteo abends = pv_prognose_final_kwh (Vorrang vor dem rollenden Wert)"
    assert tag.solcast_kwh == 38.0
    assert tag.sfml_kwh == 37.0
    assert r.eedc_mae_prozent == 2.5


async def test_abend_ohne_eedc_endwert_ist_nicht_erhoben(db, uhr, lernfaktor_13):
    """Tage vor N-782 tragen keinen eedc-Abendstand — ``None``, nicht 0 und nicht OpenMeteo × Faktor."""
    a = await factories.anlage(db)
    await _voller_tag(db, a.id, pv_prognose_eedc_final_kwh=None, pv_prognose_final_kwh=None)
    r = await _route(db, a.id, "abend")
    tag = r.tage[0]
    assert tag.eedc_kwh is None
    assert tag.openmeteo_kwh == 30.0, "ohne Endwert der rollende Wert — die Vorrangregel von §6"
    assert r.eedc_mae_prozent is None and r.eedc_asymmetrie.over_count == 0


async def test_day_ahead_ohne_profile_ist_nicht_erhoben(db, uhr):
    """Ohne gespeichertes Profil steht in Day-Ahead nichts — kein Rückfall auf einen Tageswert. Eine Nullreihe
    (so hat die Live-Sicht bis N-782 ein fehlendes Solcast-Profil eingefroren) zählt ebenfalls als nicht erhoben."""
    a = await factories.anlage(db)
    await _voller_tag(
        db, a.id, pv_prognose_stundenprofil=None, lern_soll_stundenprofil_kwh=None,
        solcast_prognose_stundenprofil=[0.0] * 24, sfml_prognose_stundenprofil=[],
    )
    tag = (await _route(db, a.id, "day_ahead")).tage[0]
    assert (tag.openmeteo_kwh, tag.eedc_kwh, tag.solcast_kwh, tag.sfml_kwh) == (None, None, None, None)
    assert tag.ist_kwh == 40.0


async def test_ausreisser_folgt_dem_gewaehlten_zeitpunkt(db, uhr):
    """Solcast liegt Day-Ahead 60 % daneben, abends 5 % — markiert wird nur im Day-Ahead-Stand."""
    a = await factories.anlage(db)
    await _voller_tag(db, a.id, solcast_prognose_stundenprofil=_profil(64.0), solcast_prognose_kwh=42.0)
    day_ahead = await _route(db, a.id, "day_ahead")
    abend = await _route(db, a.id, "abend")
    assert day_ahead.tage[0].ist_ausreisser is True and day_ahead.anzahl_ausreisser == 1
    assert abend.tage[0].ist_ausreisser is False and abend.anzahl_ausreisser == 0


async def test_ohne_parameter_gilt_day_ahead(db, uhr):
    """Der Standard der Route ist Day-Ahead — auch bei einem Direktaufruf ohne Parameter."""
    from backend.api.routes.prognosen import get_prognosen_genauigkeit

    a = await factories.anlage(db)
    await _voller_tag(db, a.id)
    r = await get_prognosen_genauigkeit(anlage_id=a.id, tage=30, ausreisser_ausblenden=False, db=db)
    assert r.zeitpunkt == "day_ahead" and r.tage[0].eedc_kwh == 42.0


# ── 4 · Schreiber ───────────────────────────────────────────────────────────


async def _zeile(db, anlage_id, datum):
    return (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum == datum,
    ))).scalar_one()


async def test_eedc_abendstand_rollt_mit_und_friert_mit_dem_om_endwert_ein(db, sitzung_ist_testdb):
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    tag = HEUTE
    # Erster Lauf (legt die Zeile an), dann zwei Läufe vor Sonnenuntergang: der Wert rollt mit.
    await lw._speichere_prognose(a.id, tag, 20.0, pv_stundenprofil=_profil(18.0))
    assert (await _zeile(db, a.id, tag)).pv_prognose_eedc_final_kwh == 18.0
    await lw._speichere_prognose(a.id, tag, 21.0, pv_stundenprofil=_profil(19.5))
    zeile = await _zeile(db, a.id, tag)
    assert zeile.pv_prognose_eedc_final_kwh == 19.5 and zeile.pv_prognose_final_at is None
    # Der einfrierende Lauf schreibt noch.
    await lw._speichere_prognose(a.id, tag, 22.0, pv_stundenprofil=_profil(20.5), pv_final_sonne_unter=True)
    zeile = await _zeile(db, a.id, tag)
    assert zeile.pv_prognose_eedc_final_kwh == 20.5 and zeile.pv_prognose_final_at is not None
    # Danach fix — der Day-Ahead-Schnappschuss ebenso (first-write-wins).
    await lw._speichere_prognose(a.id, tag, 30.0, pv_stundenprofil=_profil(28.0), pv_final_sonne_unter=True)
    zeile = await _zeile(db, a.id, tag)
    assert zeile.pv_prognose_eedc_final_kwh == 20.5
    assert zeile.pv_prognose_final_kwh == 22.0
    assert sum(zeile.pv_prognose_stundenprofil) == 18.0


async def test_ohne_korrigierte_reihe_bleibt_der_eedc_abendstand_stehen(db, sitzung_ist_testdb):
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    tag = HEUTE
    await lw._speichere_prognose(a.id, tag, 20.0, pv_stundenprofil=_profil(18.0))
    await lw._speichere_prognose(a.id, tag, 21.0)   # Lauf ohne Reihe (z. B. unvollständiger Fan-out)
    assert (await _zeile(db, a.id, tag)).pv_prognose_eedc_final_kwh == 18.0


async def test_solcast_nullreihe_wird_nicht_eingefroren_echte_reihe_schon(db, sitzung_ist_testdb):
    """Der Solcast-Dienst liefert ohne Heute-Profil 24 × 0,0. Eingefroren hieße das «Solcast sagte 0 kWh voraus»
    — und first-write-wins hielte es den ganzen Tag. Die echte Reihe danach wird der Schnappschuss."""
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    tag = HEUTE
    await lw._speichere_prognose(a.id, tag, 20.0, solcast_kwh=25.0, solcast_stundenprofil=[0.0] * 24)
    assert (await _zeile(db, a.id, tag)).solcast_prognose_stundenprofil is None
    await lw._speichere_prognose(a.id, tag, 20.0, solcast_kwh=25.0, solcast_stundenprofil=_profil(25.0))
    assert sum((await _zeile(db, a.id, tag)).solcast_prognose_stundenprofil) == 25.0
    await lw._speichere_prognose(a.id, tag, 20.0, solcast_kwh=12.0, solcast_stundenprofil=_profil(12.0))
    zeile = await _zeile(db, a.id, tag)
    assert sum(zeile.solcast_prognose_stundenprofil) == 25.0, "first-write-wins bleibt"
    assert zeile.solcast_prognose_kwh == 12.0, "der Tageswert rollt weiter (Abendstand)"


async def test_solcast_nullreihe_beim_anlegen_der_zeile(db, sitzung_ist_testdb):
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    tag = HEUTE
    await lw._speichere_prognose(a.id, tag, 20.0, solcast_kwh=25.0, solcast_stundenprofil=[0.0] * 24)
    zeile = await _zeile(db, a.id, tag)
    assert zeile.solcast_prognose_stundenprofil is None and zeile.solcast_prognose_kwh == 25.0


# ── 5 · Prefetch ────────────────────────────────────────────────────────────


async def test_prefetch_friert_das_solcast_profil_des_tages_ein(db, sitzung_ist_testdb, monkeypatch):
    """Der Prefetch läuft alle 45 min, auch nachts — sein erster Lauf nach Mitternacht ist der Day-Ahead-Stand.
    ⚠ Das Profil kommt über das Datum: um 00:05 kann der Solcast-Cache (bis 2 h) noch das Objekt von 23:30 halten,
    dessen ``hourly_kw`` die Heute-Sicht von **gestern** ist."""
    import backend.services.prefetch_service as pf
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as sc

    a = await factories.anlage(db, latitude=51.0, longitude=11.0)
    await factories.investition(
        db, a.id, "pv-module", leistung_kwp=10.0, ausrichtung="Süd", neigung_grad=30, aktiv=True, parameter={},
    )
    await db.commit()

    async def _nichts(*_a, **_k):
        return None

    for name in ("get_solar_prognose", "get_multi_string_prognose", "fetch_open_meteo_forecast",
                 "_prefetch_live_wetter"):
        monkeypatch.setattr(pf, name, _nichts)
    monkeypatch.setattr(pk, "kanon_tagesprognose", _nichts)

    gestern_sicht = _profil(9.0)
    async def _solcast(_anlage):
        return sc.SolcastForecast(
            daily_kwh=9.0, daily_p10_kwh=7.0, daily_p90_kwh=11.0,
            tomorrow_kwh=33.0, tomorrow_p10_kwh=30.0, tomorrow_p90_kwh=36.0,
            hourly_kw=gestern_sicht,
            stundenprofile={
                GESTERN.isoformat(): sc.TagesStundenprofil(datum=GESTERN, p50=gestern_sicht),
                HEUTE.isoformat(): sc.TagesStundenprofil(datum=HEUTE, p50=_profil(33.0, stunde=13)),
            },
        )

    monkeypatch.setattr(sc, "get_solcast_forecast", _solcast)
    await pf._prefetch_for_anlage(a, db, heute=HEUTE)
    zeile = await _zeile(db, a.id, HEUTE)
    assert zeile.solcast_prognose_stundenprofil == _profil(33.0, stunde=13)


async def test_prefetch_ohne_tagesprofil_friert_nichts_ein(db, sitzung_ist_testdb, monkeypatch):
    import backend.services.prefetch_service as pf
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as sc

    a = await factories.anlage(db, latitude=51.0, longitude=11.0)
    await factories.investition(
        db, a.id, "pv-module", leistung_kwp=10.0, ausrichtung="Süd", neigung_grad=30, aktiv=True, parameter={},
    )
    await db.commit()

    async def _nichts(*_a, **_k):
        return None

    for name in ("get_solar_prognose", "get_multi_string_prognose", "fetch_open_meteo_forecast",
                 "_prefetch_live_wetter"):
        monkeypatch.setattr(pf, name, _nichts)
    monkeypatch.setattr(pk, "kanon_tagesprognose", _nichts)

    async def _solcast(_anlage):
        return sc.SolcastForecast(
            daily_kwh=0.0, daily_p10_kwh=0.0, daily_p90_kwh=0.0,
            tomorrow_kwh=0.0, tomorrow_p10_kwh=0.0, tomorrow_p90_kwh=0.0,
            hourly_kw=[0.0] * 24,
        )

    monkeypatch.setattr(sc, "get_solcast_forecast", _solcast)
    await pf._prefetch_for_anlage(a, db, heute=HEUTE)
    zeile = await _zeile(db, a.id, HEUTE)
    assert zeile.solcast_prognose_stundenprofil is None


# ── 6 · HA-Ampel ────────────────────────────────────────────────────────────


async def test_eedc_mae_ohne_lernfaktor_aus_dem_day_ahead_profil(db, lernfaktor_13):
    from backend.services.prognose_genauigkeit_service import eedc_mae_prozent

    a = await factories.anlage(db)
    for i in range(1, 6):
        await _voller_tag(db, a.id, datum=HEUTE - timedelta(days=i))
    await db.commit()
    assert await eedc_mae_prozent(db, a.id, heute=HEUTE, tage=30) == (5.0, 5)


async def test_eedc_mae_ohne_profile_keine_reihe_keine_schwelle(db, lernfaktor_13):
    from backend.services.prognose_genauigkeit_service import eedc_mae_prozent

    a = await factories.anlage(db)
    for i in range(1, 6):
        await _voller_tag(db, a.id, datum=HEUTE - timedelta(days=i), pv_prognose_stundenprofil=None)
    await db.commit()
    assert await eedc_mae_prozent(db, a.id, heute=HEUTE, tage=30) == (None, 0)


# ── 7 · Feldlisten ──────────────────────────────────────────────────────────


def test_eedc_abendstand_in_beiden_prognose_feldlisten():
    """Ohne Eintrag in ``_PROGNOSE_FELDER_RETTEN`` löschte «Tag neu aggregieren» den Wert still (Delete-and-Recreate)."""
    from backend.api.routes.live_wetter import _TZ_SCHREIBFELDER_PROGNOSE
    from backend.services.energie_profil.aggregator import _PROGNOSE_FELDER_RETTEN

    assert "pv_prognose_eedc_final_kwh" in _PROGNOSE_FELDER_RETTEN
    assert "pv_prognose_eedc_final_kwh" in _TZ_SCHREIBFELDER_PROGNOSE
    assert "pv_prognose_eedc_final_kwh" in TagesZusammenfassung.__table__.columns


# ── 8 · Päckchen CC: Zeitpunkt «Mittag» ─────────────────────────────────────

_MITTAG = {
    "pv_prognose_eedc_mittag_kwh": 41.0,
    "pv_prognose_om_mittag_kwh": 45.0,
    "solcast_mittag_kwh": 39.0,
    "sfml_mittag_kwh": 43.0,
}


def _um(stunde: int, minute: int = 0):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime(2026, 11, 9, stunde, minute, tzinfo=ZoneInfo("Europe/Berlin"))


async def test_mittag_first_write_ab_zwoelf(db, sitzung_ist_testdb):
    """11:59 schreibt nicht, 12:10 schreibt, 13:00 überschreibt nicht — je Spalte, solange sie leer ist."""
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    tag = HEUTE
    await lw._speichere_prognose(a.id, tag, 20.0, mittag_werte=_MITTAG, jetzt=_um(11, 59))
    zeile = await _zeile(db, a.id, tag)
    assert all(getattr(zeile, f) is None for f in _MITTAG), "vor 12:00 kein Mittagsstand"
    await lw._speichere_prognose(
        a.id, tag, 20.0, jetzt=_um(12, 10),
        mittag_werte={**_MITTAG, "sfml_mittag_kwh": None},   # SFML hat im ersten Lauf nichts (Prefetch liest es nicht)
    )
    zeile = await _zeile(db, a.id, tag)
    assert zeile.pv_prognose_eedc_mittag_kwh == 41.0 and zeile.pv_prognose_om_mittag_kwh == 45.0
    assert zeile.solcast_mittag_kwh == 39.0 and zeile.sfml_mittag_kwh is None
    await lw._speichere_prognose(
        a.id, tag, 20.0, jetzt=_um(13, 0),
        mittag_werte={k: v + 10 for k, v in _MITTAG.items()},
    )
    zeile = await _zeile(db, a.id, tag)
    assert zeile.pv_prognose_eedc_mittag_kwh == 41.0, "13:00 überschreibt nicht"
    assert zeile.sfml_mittag_kwh == 53.0, "eine leere Spalte füllt der nächste Lauf (je Spalte first-write)"


async def test_mittag_beim_anlegen_der_zeile(db, sitzung_ist_testdb):
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    await lw._speichere_prognose(a.id, HEUTE, 20.0, mittag_werte=_MITTAG, jetzt=_um(12, 30))
    zeile = await _zeile(db, a.id, HEUTE)
    assert zeile.pv_prognose_eedc_mittag_kwh == 41.0 and zeile.sfml_mittag_kwh == 43.0


async def test_mittag_nimmt_die_mittagsstaende(db, uhr):
    a = await factories.anlage(db)
    await _voller_tag(db, a.id, **_MITTAG)
    r = await _route(db, a.id, "mittag")
    tag = r.tage[0]
    assert r.zeitpunkt == "mittag"
    assert (tag.eedc_kwh, tag.openmeteo_kwh, tag.solcast_kwh, tag.sfml_kwh) == (41.0, 45.0, 39.0, 43.0)
    # Kennzahlen aus demselben Stand: eedc (41 − 40) ÷ 40 = 2,5 %, OpenMeteo 12,5 %, Solcast −2,5 %.
    assert r.eedc_mae_prozent == 2.5 and r.openmeteo_mae_prozent == 12.5 and r.solcast_mbe_prozent == -2.5


async def test_tag_ohne_mittag_ist_nicht_erhoben(db, uhr):
    a = await factories.anlage(db)
    await _voller_tag(db, a.id)
    r = await _route(db, a.id, "mittag")
    tag = r.tage[0]
    assert (tag.eedc_kwh, tag.openmeteo_kwh, tag.solcast_kwh, tag.sfml_kwh) == (None, None, None, None)
    assert r.eedc_mae_prozent is None and r.anzahl_tage == 1


async def test_kaskade_first_write_wie_die_profile(db, sitzung_ist_testdb):
    import backend.api.routes.live_wetter as lw

    a = await factories.anlage(db)
    await lw._speichere_prognose(a.id, HEUTE, 20.0, kaskade_stundenprofil=_profil(22.0))
    await lw._speichere_prognose(a.id, HEUTE, 20.0, kaskade_stundenprofil=_profil(30.0))
    assert sum((await _zeile(db, a.id, HEUTE)).pv_prognose_kaskade_stundenprofil) == 22.0


def test_mittag_und_kaskade_in_beiden_prognose_feldlisten():
    from backend.api.routes.live_wetter import _TZ_SCHREIBFELDER_PROGNOSE
    from backend.services.energie_profil.aggregator import _PROGNOSE_FELDER_RETTEN

    for feld in (*_MITTAG, "pv_prognose_kaskade_stundenprofil"):
        assert feld in _PROGNOSE_FELDER_RETTEN and feld in _TZ_SCHREIBFELDER_PROGNOSE
        assert feld in TagesZusammenfassung.__table__.columns


# ── 9 · Päckchen CC: Quellen-Empfehlung ─────────────────────────────────────


async def test_beste_quelle_erst_ab_14_tagen(db, uhr):
    a = await factories.anlage(db)
    for i in range(1, 14):
        await _voller_tag(db, a.id, datum=HEUTE - timedelta(days=i))
    r = await _route(db, a.id, "day_ahead")
    assert r.beste_quelle is None and r.beste_quelle_mae_prozent is None, "13 Tage reichen nicht"
    await _voller_tag(db, a.id, datum=HEUTE - timedelta(days=14))
    r = await _route(db, a.id, "day_ahead")
    # eedc 5 %, OpenMeteo 10 %, Solcast 20 % — SFML (2,5 %) zählt nicht (Tom-HA-Regel).
    assert r.beste_quelle == "eedc" and r.beste_quelle_mae_prozent == 5.0
    assert r.prognose_quelle == "eedc"


async def test_beste_quelle_folgt_dem_zeitpunkt(db, uhr):
    a = await factories.anlage(db)
    for i in range(1, 15):
        await _voller_tag(db, a.id, datum=HEUTE - timedelta(days=i), **_MITTAG)
    r = await _route(db, a.id, "mittag")
    assert r.beste_quelle == "eedc" and r.beste_quelle_mae_prozent == 2.5
    r = await _route(db, a.id, "abend")
    # Abend: OpenMeteo 36 (10 %), eedc 39 (2,5 %), Solcast 38 (5 %).
    assert r.beste_quelle == "eedc"
