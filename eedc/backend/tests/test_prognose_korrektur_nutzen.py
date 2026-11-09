"""Päckchen CC3 — Wächter «Korrektur nur, wenn sie hilft» (Konzept §7 M3, Zielmarke Z1).

Geprüft:

1. Layer ``korrektur_aussetzen``: Schwelle (Toleranz 2 Punkte), Hysterese beidseitig (1 Punkt), nie unter 14 Tagen,
   nie ohne beide MAE.
2. Service ``korrektur_nutzen`` mit gestellten Tageszeilen: Kaskade besser ⇒ aktiv; 3 Punkte schlechter über 20 Tage ⇒
   ausgesetzt; 10 Tage ⇒ nie; Tage vor der Spalte lesen ``pv_prognose_stundenprofil`` (Rückfall); der Zustand des
   Vortags trägt die Hysterese; Tagescache.
3. Kanon mit Weiche: Faktor 1,0 auf allen Slots aller Tage, die Kaskade daneben gerechnet; der Prefetch friert
   ``pv_prognose_stundenprofil`` = roh und ``pv_prognose_kaskade_stundenprofil`` = Kaskade ein.
4. HA-Attribute am Sensor «PV-Prognose heute».

Schwestern: ``test_prognose_kanon.py`` (Kanon, Fixture ``_patch``/``_seed``), ``test_prognose_nachfuehrung.py`` (Layer
derselben Nachführung), ``test_genauigkeit_zeitpunkt.py`` (MAE-Rechnung, Kaskaden-Spalte first-write),
``test_n547_lern_soll_nicht_zirkulaer.py`` (Lern-SOLL), ``test_migrations_round_trip.py`` (Spalte).
"""

from __future__ import annotations

import contextlib
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from backend.core.berechnungen.prognose_korrektur_nutzen import (
    KORREKTUR_HYSTERESE_PUNKTE,
    KORREKTUR_MIN_TAGE,
    KORREKTUR_TOLERANZ_PUNKTE,
    KorrekturNutzen,
    korrektur_aussetzen,
)
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.tests import factories
from backend.tests.test_prognose_kanon import _fake_prognose, _patch, _seed  # noqa: F401 — Fixture und Bestand der Kanon-Proben

HEUTE = date(2026, 11, 9)


def _tag_des_fakes() -> date:
    """Der erste Tag der Fake-Prognose (`test_prognose_kanon._fake_prognose`) — der Kanon-Horizont muss dieselben Daten
    tragen; der Fake datiert selbst, diese Datei liest keine Uhr."""
    return date.fromisoformat(_fake_prognose(10.0, 0).tageswerte[0].datum)


# ── 1 · Layer ───────────────────────────────────────────────────────────────


def test_konstanten_sind_die_annahmen_des_auftrags():
    assert (KORREKTUR_TOLERANZ_PUNKTE, KORREKTUR_HYSTERESE_PUNKTE, KORREKTUR_MIN_TAGE) == (2.0, 1.0, 14)


@pytest.mark.parametrize("kaskade, roh, bisher, erwartet", [
    (20.0, 18.0, False, False),   # genau Toleranz: noch nicht schlechter als erlaubt
    (20.1, 18.0, False, True),    # über der Toleranz ⇒ aussetzen
    (19.5, 18.0, True, True),     # im Band (19,0 < x ≤ 20,0): Zustand halten (ausgesetzt)
    (19.5, 18.0, False, False),   # im Band: Zustand halten (aktiv)
    (19.0, 18.0, True, False),    # Toleranz − Hysterese erreicht ⇒ wieder einschalten
    (12.0, 18.0, True, False),    # Korrektur klar besser
])
def test_schwelle_und_hysterese(kaskade, roh, bisher, erwartet):
    assert korrektur_aussetzen(kaskade, roh, bisher_ausgesetzt=bisher, tage=20) is erwartet


def test_nie_unter_min_tagen_und_nie_ohne_beide_mae():
    assert korrektur_aussetzen(40.0, 10.0, bisher_ausgesetzt=True, tage=13) is False
    assert korrektur_aussetzen(None, 10.0, bisher_ausgesetzt=True, tage=30) is False
    assert korrektur_aussetzen(40.0, None, bisher_ausgesetzt=True, tage=30) is False


# ── 2 · Service ─────────────────────────────────────────────────────────────


def _profil(summe: float) -> list[float]:
    return [0.0] * 12 + [summe] + [0.0] * 11


async def _tage(db, anlage_id, n: int, *, kaskade: float, roh: float, spalte: bool = True, ist: float = 40.0):
    for i in range(1, n + 1):
        werte = dict(
            komponenten_kwh={"pv_1": ist},
            lern_soll_stundenprofil_kwh=_profil(roh),
            pv_prognose_stundenprofil=_profil(roh if spalte else kaskade),
        )
        if spalte:
            werte["pv_prognose_kaskade_stundenprofil"] = _profil(kaskade)
        db.add(TagesZusammenfassung(anlage_id=anlage_id, datum=HEUTE - timedelta(days=i), **werte))
    await db.flush()


async def _nutzen(db, anlage_id, heute=HEUTE) -> KorrekturNutzen:
    from backend.services.prognose_korrektur_nutzen import korrektur_nutzen
    return await korrektur_nutzen(db, anlage_id, heute)


async def test_kaskade_besser_bleibt_aktiv(db):
    a = await factories.anlage(db)
    await _tage(db, a.id, 20, kaskade=41.0, roh=44.0)          # 2,5 % gegen 10 %
    n = await _nutzen(db, a.id)
    assert (n.mae_kaskade_prozent, n.mae_roh_prozent, n.tage, n.ausgesetzt) == (2.5, 10.0, 20, False)


async def test_drei_punkte_schlechter_ueber_20_tage_setzt_aus(db):
    a = await factories.anlage(db)
    await _tage(db, a.id, 20, kaskade=43.2, roh=42.0)          # 8 % gegen 5 %
    n = await _nutzen(db, a.id)
    assert (n.mae_kaskade_prozent, n.mae_roh_prozent, n.tage, n.ausgesetzt) == (8.0, 5.0, 20, True)


async def test_zehn_tage_setzen_nie_aus(db):
    a = await factories.anlage(db)
    await _tage(db, a.id, 10, kaskade=60.0, roh=42.0)
    n = await _nutzen(db, a.id)
    assert n.tage == 10 and n.ausgesetzt is False


async def test_tage_vor_der_spalte_lesen_die_gezeigte_reihe(db):
    """Vor Päckchen CC gab es nur ``pv_prognose_stundenprofil`` — bis dahin war es die Kaskade (nie ausgesetzt)."""
    a = await factories.anlage(db)
    await _tage(db, a.id, 20, kaskade=43.2, roh=42.0, spalte=False)
    n = await _nutzen(db, a.id)
    assert n.mae_kaskade_prozent == 8.0 and n.ausgesetzt is True


async def test_ohne_roh_reihe_kein_urteil(db):
    """Die Demo-Kopien tragen kein Lern-SOLL (seit 22.9.2026) — dann gibt es keine gepaarten Tage."""
    a = await factories.anlage(db)
    for i in range(1, 21):
        db.add(TagesZusammenfassung(
            anlage_id=a.id, datum=HEUTE - timedelta(days=i), komponenten_kwh={"pv_1": 40.0},
            pv_prognose_stundenprofil=_profil(60.0),
        ))
    await db.flush()
    n = await _nutzen(db, a.id)
    assert (n.mae_kaskade_prozent, n.mae_roh_prozent, n.tage, n.ausgesetzt) == (None, None, 0, False)


async def test_hysterese_haelt_im_band(db):
    from backend.services import prognose_korrektur_nutzen as pkn

    a = await factories.anlage(db)
    await _tage(db, a.id, 20, kaskade=42.6, roh=42.0)            # 6,5 % gegen 5 %: im Band (6,0 < 6,5 ≤ 7,0)
    pkn._nutzen_cache[a.id] = ((HEUTE - timedelta(days=1)).isoformat(), KorrekturNutzen(9.0, 5.0, 20, True))
    assert (await _nutzen(db, a.id)).ausgesetzt is True, "gestern ausgesetzt ⇒ heute im Band ausgesetzt"
    pkn._nutzen_cache[a.id] = ((HEUTE - timedelta(days=1)).isoformat(), KorrekturNutzen(5.0, 5.0, 20, False))
    assert (await _nutzen(db, a.id)).ausgesetzt is False, "gestern aktiv ⇒ heute im Band aktiv"


async def test_tagescache(db):
    a = await factories.anlage(db)
    await _tage(db, a.id, 20, kaskade=43.2, roh=42.0)
    erst = await _nutzen(db, a.id)
    assert erst.ausgesetzt is True
    # Am selben Tag gilt der gerechnete Stand, auch wenn sich die Zeilen ändern (einmal am Tag gerechnet) …
    from sqlalchemy import delete
    await db.execute(delete(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == a.id))
    await db.flush()
    assert await _nutzen(db, a.id) is erst
    # … am nächsten Tag neu: ohne Zeilen kein Urteil.
    assert (await _nutzen(db, a.id, heute=HEUTE + timedelta(days=1))).ausgesetzt is False


# ── 3 · Kanon mit Weiche ────────────────────────────────────────────────────


@pytest.fixture
def ausgesetzt(monkeypatch):
    """Der Wächter sagt «aussetzen»; die Kaskade läge bei Faktor 1,2 auf jedem Slot."""
    import backend.services.prognose_kanon as pk
    from backend.services import prognose_korrektur_nutzen as pkn

    async def _nutzen_aus(_db, _anlage_id, _heute):
        return KorrekturNutzen(mae_kaskade_prozent=24.0, mae_roh_prozent=21.0, tage=30, ausgesetzt=True)

    async def _faktoren(*_a, **_k):
        return [1.2] * 24

    monkeypatch.setattr(pkn, "korrektur_nutzen", _nutzen_aus)
    monkeypatch.setattr(pk, "korrekturfaktoren_fuer_tag", _faktoren)


async def test_kanon_mit_weiche_faktor_eins_auf_allen_tagen(db, _patch, ausgesetzt):  # noqa: F811
    from backend.services.prognose_kanon import kanon_tagesprognose

    anlage = await _seed(db)
    k = await kanon_tagesprognose(db, anlage, days=4, heute=_tag_des_fakes())
    assert k.korrektur_ausgesetzt is True
    assert k.korrektur_nutzen.mae_kaskade_prozent == 24.0
    for tag in k.tage:
        roh = [round(v, 3) for v in tag.om_stundenprofil_kwh]
        assert [round(v, 3) for v in tag.profil.stunden_kwh] == roh, "ausgesetzt ⇒ die gekappte Rohreihe"
        assert tag.eedc_kwh == pytest.approx(tag.om_kwh, abs=0.15)
        kaskade = tag.kaskade_stundenprofil_kwh
        assert kaskade is not None and sum(kaskade) == pytest.approx(1.2 * sum(tag.profil.stundenprofil_export_kwh), rel=0.01)


async def test_kanon_ohne_weiche_unveraendert(db, _patch, monkeypatch):  # noqa: F811
    """Nicht ausgesetzt ⇒ das Profil IST die Kaskade (dasselbe Objekt), die Kaskaden-Reihe sind seine Export-Slots."""
    import backend.services.prognose_kanon as pk

    async def _faktoren(*_a, **_k):
        return [1.2] * 24

    monkeypatch.setattr(pk, "korrekturfaktoren_fuer_tag", _faktoren)
    anlage = await _seed(db)
    k = await pk.kanon_tagesprognose(db, anlage, days=4, heute=_tag_des_fakes())
    assert k.korrektur_ausgesetzt is False and k.korrektur_nutzen.tage == 0
    for tag in k.tage:
        assert tag.kaskade_stundenprofil_kwh == list(tag.profil.stundenprofil_export_kwh)


@pytest.fixture
def sitzung_ist_testdb(db, monkeypatch):
    @contextlib.asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("backend.core.database.get_session", _session)


async def test_prefetch_friert_roh_und_kaskade_getrennt_ein(db, _patch, ausgesetzt, sitzung_ist_testdb, monkeypatch):  # noqa: F811
    import backend.services.prefetch_service as pf
    import backend.services.solcast_service as sc

    anlage = await _seed(db)
    await db.commit()

    async def _nichts(*_a, **_k):
        return None

    for name in ("get_solar_prognose", "get_multi_string_prognose", "fetch_open_meteo_forecast", "_prefetch_live_wetter"):
        monkeypatch.setattr(pf, name, _nichts)
    monkeypatch.setattr(sc, "get_solcast_forecast", _nichts)
    heute = _tag_des_fakes()
    await pf._prefetch_for_anlage(anlage, db, heute=heute)
    zeile = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == heute,
    ))).scalar_one()
    roh = sum(zeile.lern_soll_stundenprofil_kwh)
    assert sum(zeile.pv_prognose_stundenprofil) == pytest.approx(roh, abs=0.15), "gezeigt = roh"
    assert sum(zeile.pv_prognose_kaskade_stundenprofil) == pytest.approx(1.2 * roh, rel=0.01), "Kaskade daneben"


# ── 4 · HA-Attribute am Sensor «PV-Prognose heute» ──────────────────────────


def test_ha_attribute_am_heute_sensor():
    from backend.api.routes.ha_export.anlage_sensorwerte import _prognose_sensorwert
    from backend.services.ha_sensors_export import PROGNOSE_SENSOREN

    sensor = next(s for s in PROGNOSE_SENSOREN if s.key == "eedc_prognose_heute_kwh")
    prognose = {
        "heute_kwh": 28.5, "stundenprofil_heute": [0.0] * 24,
        "korrektur_nutzen": KorrekturNutzen(mae_kaskade_prozent=24.0, mae_roh_prozent=21.0, tage=30, ausgesetzt=True),
    }
    wert, attr = _prognose_sensorwert(sensor, prognose)
    assert wert == 28.5
    assert attr["korrektur_ausgesetzt"] is True
    assert (attr["korrektur_mae_30_prozent"], attr["roh_mae_30_prozent"]) == (24.0, 21.0)
    assert attr["stundenprofil_kwh"] == [0.0] * 24
    # Ohne Wächter-Stand (älteres Export-Dict, Fake-Kanon) keine Wächter-Attribute.
    _, attr = _prognose_sensorwert(sensor, {"heute_kwh": 28.5})
    assert "korrektur_ausgesetzt" not in attr
