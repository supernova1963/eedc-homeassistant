"""N-791 (Melder ottokar, simon42 PN T95600): «Tag reparieren» schreibt die Zählerwerte aus Home Assistant auch dann,
wenn Home Assistant für den Tag keine Leistungskurve mehr hat.

**Der Fall** (Nachstellung ``opus-berichte/NACHSTELLUNG-N791-2026-11-10.md``, Lauf **Lk**). Ein neuer Wärmepumpen-Zähler
beginnt am 2.11. mit einem Erstwert-Sprung (Stand 0,0 → 123.909,6 kWh); der Tageslauf schreibt den Sprung in den Tag
(123.922,2 kWh). Der Anwender korrigiert die Statistik in Home Assistant («Summe anpassen»), der Daten-Checker zeigt die
Drift «123.922,2 → 12,6». Liefert der Verlauf aber keinen Leistungswert mehr (Recorder ohne W-Werte oder gepurgt) und die
Langzeitstatistik keine Leistungskurve, stieg die Werkbank am N-596-Schutz aus («Der Tag bleibt unverändert …») — der Tag
mit dem falschen Gerätewert blieb genau deshalb stehen, weil er einen Gerätewert hatte.

**Die Regel seit N-791** (``hole_tagesverlauf`` d, ``aggregate_day(zaehler_erhalt=True)``, Stufe 3 von
``repair_orchestrator._reparatur_aggregat``): trägt die Zählertabelle des Tages aus der HA-Langzeitstatistik Werte, schreibt
die Werkbank die zählerbasierten Größen neu und lässt den gespeicherten Leistungsverlauf stehen (``komponenten`` je Stunde,
Tages-Peaks). Liefert auch die Zählertabelle nichts (oder nur eedcs eigene Stände), bleibt der Tag wie bisher stehen.

Aufbau nach ``refactoring-werkzeug/n791/nachstellung.py``, eigenständig: eine Anlage mit PV und einer Wärmepumpe, Home
Assistant als Attrappe im echten Recorder-Schema (``ha_lts_helfer``), HA-Spiegel aus derselben Statistik; Wetter, Preise,
Ladestand und Betriebsart ohne Netz. Geprüft: (a) Lk · (a2) Lk mit Leistungszuordnung · (b) N-596 bleibt · (c) der
Nachtlauf bleibt · (d) Lauf L mit Leistungskurve · (e) Drift-Zeilen Bestand/Kanal · (f) Rückmeldung der Routen.
"""

from __future__ import annotations

from backend.tests.werkzeug_befund import befund_op, befund_params
import time as _zeit
from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from backend.core.database import Base
from backend.models import Anlage, Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.source import Source
from backend.tests import ha_lts_helfer as hh

WP_EID = "sensor.n791_wp_strom"
PV_EID = "sensor.n791_pv_erzeugung"
WP_W_EID = "sensor.n791_wp_leistung"
D2 = date(2026, 11, 2)
HEUTE = date(2026, 11, 10)
SPRUNG = 123909.6
SATZ = "Gerätewerte aus der Home-Assistant-Statistik neu geschrieben; der gespeicherte Leistungsverlauf blieb stehen."


def _ts(d: date, h: int) -> int:
    return int(_zeit.mktime(datetime(d.year, d.month, d.day, h).timetuple()))


# ── Reihen (wie die Nachstellung) ────────────────────────────────────────────


def _wp_staende() -> list[tuple[datetime, float]]:
    """(Zeitpunkt des Stands, Stand): 11:00 = 0,0, 12:00 = Sprung, dann +1,6 · 11 × +1,1 (Σ 2.11. ab 12:00 = 13,7)."""
    out = [(datetime(2026, 11, 2, 11), 0.0)]
    stand, t = SPRUNG, datetime(2026, 11, 2, 13)
    out.append((datetime(2026, 11, 2, 12), stand))
    while t <= datetime(2026, 11, 4, 6):
        inc = (1.6 if t.hour == 13 else 1.1) if (t.date() == D2 or t == datetime(2026, 11, 3, 0)) else 1.5
        stand = round(stand + inc, 4)
        out.append((t, stand))
        t += timedelta(hours=1)
    return out


def _pv_staende() -> list[tuple[datetime, float]]:
    out, stand, t = [], 5000.0, datetime(2026, 10, 25, 0)
    while t <= datetime(2026, 11, 4, 6):
        out.append((t, round(stand, 4)))
        stand += 0.6 if 9 <= t.hour < 16 else 0.0
        t += timedelta(hours=1)
    return out


def _seed_ha():
    svc = hh.mach_service(thread_sicher=True)
    pv = hh.sensor(svc, PV_EID, "kWh")
    st = _pv_staende()
    for t, s in st[1:]:   # HA-Zeile start_ts = t − 1 h trägt den Stand bei t
        hh.zeile(svc, pv, t - timedelta(hours=1), state=s, sum_wert=round(s - st[0][1], 4))
    wp = hh.sensor(svc, WP_EID, "kWh")
    summe, vor = 0.0, None
    for t, s in _wp_staende():   # HAs Summe: erster Stand = Basis; jeder Zuwachs zählt — auch der Sprung
        summe += 0.0 if vor is None else s - vor
        vor = s
        hh.zeile(svc, wp, t - timedelta(hours=1), state=s, sum_wert=round(summe, 4))
    return svc


def _korrigiere_ha(svc) -> None:
    """HAs «Summe anpassen»: ``sum`` ab Zeile 2.11. 11:00 (Stand 12:00) um −123.909,6."""
    with svc._engine.begin() as conn:
        mid = conn.execute(text("SELECT id FROM statistics_meta WHERE statistic_id=:s"), {"s": WP_EID}).scalar()
        conn.execute(text("UPDATE statistics SET sum = sum - :k WHERE metadata_id=:m AND start_ts >= :t"),
                     {"k": SPRUNG, "m": mid, "t": _ts(D2, 11)})


def _ha_aus():
    from backend.services.ha_statistics_service import HAStatisticsService

    svc = HAStatisticsService()
    svc._engine = None
    svc._initialized = True
    return svc


def _kurve(*, leer: bool) -> dict:
    """Die Leistungskurve des Verlaufs — ``leer``: das volle Raster ohne einen Leistungswert (N-596)."""
    if leer:
        return {"serien": [], "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)], "vortagsrand": []}
    werte = lambda h: {"pv_gesamt": 0.6 if 9 <= h < 16 else 0.0}  # noqa: E731
    return {"serien": [{"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle", "bidirektional": False}],
            "punkte": [{"zeit": f"{h:02d}:00", "werte": werte(h)} for h in range(24)],
            "vortagsrand": [{"zeit": "23:00", "werte": werte(23)}]}


# ── Lage ─────────────────────────────────────────────────────────────────────


class _Lage:
    """Datenbank, HA-Attrappe und Kurve einer Probe; ``svc``/``kurve_leer`` wechseln während der Probe."""

    def __init__(self, macher, aid: int, ha):
        self.macher, self.aid, self.svc, self.kurve_leer = macher, aid, ha, False

    @asynccontextmanager
    async def sitzungen(self):
        async with self.macher() as s:
            yield s
            await s.commit()

    async def anlage(self, db) -> Anlage:
        return (await db.execute(select(Anlage).options(selectinload(Anlage.investitionen))
                                 .where(Anlage.id == self.aid))).scalar_one()


@contextmanager
def _heute_fest():
    """«Heute» der Drift-Prüfung = 10.11.2026 (Fenster 90 Tage bis gestern) — Muster ``test_s5_e2…heute_fest``."""
    import datetime as _dt
    import sys
    import types

    class _Fest(_dt.date):
        @classmethod
        def today(cls):
            return cls(HEUTE.year, HEUTE.month, HEUTE.day)

    echt = sys.modules["datetime"]
    ersatz = types.ModuleType("datetime")
    ersatz.__dict__.update(echt.__dict__)
    ersatz.date = _Fest
    sys.modules["datetime"] = ersatz
    try:
        yield
    finally:
        sys.modules["datetime"] = echt


def _umgebung(stack: ExitStack, lage: _Lage) -> None:
    import backend.services.ha_statistics_service as hss
    from backend.services.energie_profil._helpers import StrompreisStunden

    class _HaProxy:
        def __getattr__(self, name):
            return getattr(lage.svc, name)

    class _LivePower:
        async def get_tagesverlauf(self, *a, **k):
            return _kurve(leer=lage.kurve_leer)

    stack.enter_context(patch.object(hss, "_ha_statistics_service", _HaProxy()))
    h = "backend.services.energie_profil._helpers."
    stack.enter_context(patch(h + "_get_strompreis_stunden",
                              new=AsyncMock(return_value=StrompreisStunden(sensor={}, boerse={}))))
    for name in ("_get_wetter_ist", "_get_soc_history", "_get_betriebsmodus_history",
                 "_get_zustands_mitschrift_history"):
        stack.enter_context(patch(h + name, new=AsyncMock(return_value={})))
    stack.enter_context(patch("backend.services.live_power_service.get_live_power_service", lambda: _LivePower()))


@asynccontextmanager
async def _lk(tmp_path, *, live: bool = False, quelle_vorhanden: bool = True):
    """Lauf Lk bis vor «Tag reparieren»: HA unkorrigiert → Spiegel + Tageslauf (Sprung im Tag) → HA korrigiert.

    ``live``: die Anlage trägt eine Leistungszuordnung (WP-Leistungssensor ohne Statistik). Ohne sie stellt die
    Nachstellung ``ermittle_aggregations_quelle`` auf «vorhanden» (``quelle_vorhanden``)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/n791.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with macher() as db:
        a = Anlage(anlagenname="Prüfstand N791", leistung_kwp=8.0, standort_plz="10115", standort_land="DE",
                   installationsdatum=date(2025, 1, 1), vollbackfill_durchgefuehrt=True)
        db.add(a)
        await db.flush()
        pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süddach", leistung_kwp=8.0,
                         anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0)
        wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="Brauchwasser-WP",
                         anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0,
                         parameter={"wp_art": "brauchwasser", "effizienz_modus": "gesamt_jaz", "jaz": 3.0})
        db.add_all([pv, wp])
        await db.flush()
        wp_eintrag: dict = {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": WP_EID}}}
        if live:
            wp_eintrag["live"] = {"leistung_w": WP_W_EID}
        a.sensor_mapping = {"investitionen": {
            str(pv.id): {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": PV_EID}}},
            str(wp.id): wp_eintrag,
        }}
        # eedcs eigene Stände (wie der :05-Lauf sie schrieb) — der Snapshot-Rückfall trägt den Sprung.
        for t, s in _wp_staende():
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{wp.id}:stromverbrauch_kwh", zeitpunkt=t,
                                  wert_kwh=s, quelle="ha_statistics"))
        await db.commit()
        aid, wp_id = a.id, wp.id
    lage = _Lage(macher, aid, _seed_ha())
    lage.wp_key = f"waermepumpe_{wp_id}"
    with ExitStack() as st:
        _umgebung(st, lage)
        if quelle_vorhanden and not live:
            st.enter_context(patch(
                "backend.services.energie_profil.aggregations_quelle.ermittle_aggregations_quelle",
                new=AsyncMock(return_value=SimpleNamespace(vorhanden=True, mqtt_energie=False)),
            ))
        from backend.services.kanal import merken
        from backend.services.kanal.nachfuellen import nachfuellen_spiegel

        await nachfuellen_spiegel(lage.sitzungen, aid, jetzt=datetime(2026, 11, 4, 6, 5), ha_svc=lage.svc)
        merken.invalidiere(aid)
        await _tageslauf(lage)
        _korrigiere_ha(lage.svc)
        lage.kurve_leer = True
        try:
            yield lage
        finally:
            merken.invalidiere(aid)
    await engine.dispose()


async def _tageslauf(lage: _Lage, source=Source.SCHEDULER):
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.kanal import merken

    merken.invalidiere(lage.aid)
    async with lage.sitzungen() as db:
        return await aggregate_day(await lage.anlage(db), D2, db, source=source)


async def _tag(lage: _Lage) -> dict:
    """Tageszeile, Stundenzeilen (Leistungsverlauf + WP-Stunden-kWh) und Peaks des 2.11."""
    async with lage.sitzungen() as db:
        z = (await db.execute(select(TagesZusammenfassung).where(and_(
            TagesZusammenfassung.anlage_id == lage.aid, TagesZusammenfassung.datum == D2)))).scalar_one()
        zeilen = (await db.execute(select(TagesEnergieProfil).where(and_(
            TagesEnergieProfil.anlage_id == lage.aid, TagesEnergieProfil.datum == D2))
            .order_by(TagesEnergieProfil.stunde))).scalars().all()
        return {
            "wp": (z.komponenten_kwh or {}).get(lage.wp_key),
            "peak_pv": z.peak_pv_kw,
            "datenquelle": z.datenquelle,
            "leistung": {r.stunde: r.komponenten for r in zeilen if r.komponenten},
            "leistung_herkunft": {r.stunde: {k: v.get("source") for k, v in (r.source_provenance or {}).items()
                                             if k.startswith("komponenten.")} for r in zeilen if r.komponenten},
            "wp_stunden": round(sum(r.waermepumpe_kw or 0.0 for r in zeilen), 3),
        }


async def _werkbank(lage: _Lage):
    """«Tag reparieren» = «Tag neu aggregieren»: Orchestrator REAGGREGATE_DAY plan + execute (mit Resnap)."""
    from backend.services import repair_orchestrator as ro
    from backend.services.kanal import merken

    merken.invalidiere(lage.aid)
    async with lage.sitzungen() as db:
        req = ro.RepairOperationRequest(anlage_id=lage.aid, operation=ro.RepairOperationType.REAGGREGATE_DAY,
                                        params={"datum": D2.isoformat(), "mit_resnap": True})
        p = await ro.plan(req, db)
        try:
            return (await ro.execute(p.plan_id, db)).operation_summary
        except RuntimeError:
            await db.rollback()
            raise


async def _drift_wp(lage: _Lage) -> list[str]:
    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import merken

    merken.invalidiere(lage.aid)
    async with lage.sitzungen() as db:
        a = await lage.anlage(db)
        with _heute_fest():
            erg = await DatenChecker(db)._check_datenquelle_drift(a)
    return [e.meldung for e in erg if "weichen von HA-Statistics ab" in e.meldung]


# ── (a) Lk: Gerätewert aus der Statistik, Leistungsverlauf bleibt ───────────


async def test_a_lk_reparatur_schreibt_zaehlerwerte_und_laesst_den_leistungsverlauf(tmp_path):
    async with _lk(tmp_path) as lage:
        vorher = await _tag(lage)
        assert round(vorher["wp"], 1) == 123922.2, vorher
        assert vorher["leistung"], "der Tageslauf hat einen Leistungsverlauf gespeichert"
        assert len(await _drift_wp(lage)) == 1, "Drift «123.922,2 → 12,6» vor der Reparatur"

        erg = await _werkbank(lage)
        nachher = await _tag(lage)

        assert erg["quelle"] == "zaehler_erhalt"
        assert erg["quelle_text"] == SATZ
        assert round(nachher["wp"], 1) == 12.6
        assert nachher["wp_stunden"] == 12.6, "Σ Stunden = Tag (G1) für den neu geschriebenen Zähler"
        assert nachher["leistung"] == vorher["leistung"], "Leistungsverlauf je Stunde unverändert"
        assert nachher["leistung_herkunft"] == vorher["leistung_herkunft"], "der Verlauf behält seine alte Herkunft"
        assert nachher["peak_pv"] == vorher["peak_pv"] and vorher["peak_pv"], "Peak aus dem gespeicherten Verlauf"
        assert nachher["datenquelle"] == "manuell"
        (wp,) = [k for k in erg["komponenten"] if k["key"] == lage.wp_key]
        assert wp["geschrieben"] and wp["kwh"] == 12.6
        assert await _drift_wp(lage) == [], "Drift-Check ohne Zeile"


async def _plan_ausfuehren(lage: _Lage, operation: str, params: dict) -> dict:
    """E3 (W-11): eine Aktion über die eine Mechanik — Orchestrator ``plan`` + ``execute``."""
    from backend.services import repair_orchestrator as ro
    from backend.services.kanal import merken

    merken.invalidiere(lage.aid)
    async with lage.sitzungen() as db:
        p = await ro.plan(ro.RepairOperationRequest(anlage_id=lage.aid, operation=ro.RepairOperationType(operation),
                                                    params=params), db)
        return (await ro.execute(p.plan_id, db)).operation_summary


async def test_w11_bereich_ueber_plan_und_ausfuehren_behebt_die_drift(tmp_path):
    """W-11 (E3), «Tage neu aufbauen» (``REAGGREGATE_RANGE``) an einem Bestandstag: nach dem Lauf ist die Drift still."""
    async with _lk(tmp_path) as lage:
        assert len(await _drift_wp(lage)) == 1
        await _plan_ausfuehren(lage, "reaggregate_range", {"von": D2.isoformat(), "bis": D2.isoformat()})
        assert await _drift_wp(lage) == [], "Drift-Check ohne Zeile"


async def test_w11_aus_home_assistant_neu_uebernehmen_ueber_plan_und_ausfuehren(tmp_path):
    """W-11 (E3), «Aus Home Assistant neu übernehmen» (``SPIEGEL_ABGLEICH_TAG``) mit den Parametern des Befunds: der Plan
    fragt Home Assistant nicht, der Lauf gleicht den Spiegel ab und baut den Tag — die Drift ist still, genau eine
    Zeile ``repair``."""
    from backend.models.activity_log import ActivityLog
    from backend.services.daten_checker import DatenChecker

    async with _lk(tmp_path) as lage:
        with patch("backend.core.database.get_session", lage.sitzungen):
            async with lage.sitzungen() as db:
                with _heute_fest():
                    erg = await DatenChecker(db)._check_datenquelle_drift(await lage.anlage(db))
            (e,) = [e for e in erg if "weichen von HA-Statistics ab" in e.meldung]
            assert befund_op(e) == "spiegel_abgleich_tag"
            await _plan_ausfuehren(lage, befund_op(e), befund_params(e))
            assert await _drift_wp(lage) == [], "Drift-Check ohne Zeile"
        async with lage.sitzungen() as db:
            zeilen = (await db.execute(select(ActivityLog).where(ActivityLog.kategorie.in_(
                ["repair", "ha_statistics"])))).scalars().all()
        assert [z.kategorie for z in zeilen] == ["repair"]


async def test_a2_lk_mit_leistungszuordnung(tmp_path):
    """Dieselbe Lage an einer Anlage mit Leistungszuordnung (der Weg ohne nachgestellte Aggregationsquelle):
    Leistungssensor ohne Verlauf und ohne Statistik."""
    async with _lk(tmp_path, live=True) as lage:
        vorher = await _tag(lage)
        erg = await _werkbank(lage)
        nachher = await _tag(lage)
    assert erg["quelle"] == "zaehler_erhalt"
    assert round(nachher["wp"], 1) == 12.6
    assert nachher["leistung"] == vorher["leistung"]


# ── (b) N-596 bleibt: ohne Zählertabelle aus HA bleibt der Tag stehen ───────


async def test_b_ohne_zaehlertabelle_bleibt_der_tag_unveraendert(tmp_path):
    """Kein Verlauf, keine Leistungskurve, keine Zählertabelle aus Home Assistant (HA nicht erreichbar) — eedcs eigene
    Stände tragen den Sprung, aber der Snapshot-Rückfall schreibt keinen Tag mit Gerätewerten neu."""
    from backend.services.repair_orchestrator import unveraendert_text

    async with _lk(tmp_path) as lage:
        vorher = await _tag(lage)
        lage.svc = _ha_aus()
        with pytest.raises(RuntimeError) as fehler:
            await _werkbank(lage)
        nachher = await _tag(lage)
    assert "nicht neu geschrieben" in str(fehler.value)
    assert unveraendert_text("ha_nicht_verfuegbar").split(" (")[0] in str(fehler.value)
    assert nachher == vorher


# ── (c) Der Nachtlauf bleibt ─────────────────────────────────────────────────


async def test_c_nachtlauf_ohne_leistungskurve_laesst_den_tag_stehen(tmp_path):
    """``Source`` ≠ ``MANUAL_REPAIR``: N-596 (b) wie bisher — der Tag mit Gerätewerten bleibt stehen."""
    async with _lk(tmp_path) as lage:
        vorher = await _tag(lage)
        assert await _tageslauf(lage) is None
        assert await _tageslauf(lage, source=Source.MONATSABSCHLUSS_BACKFILL) is None
        assert await _tag(lage) == vorher


async def test_c_nachtlauf_mit_leistungskurve_wie_bisher(tmp_path):
    async with _lk(tmp_path) as lage:
        vorher = await _tag(lage)
        lage.kurve_leer = False
        z = await _tageslauf(lage)
        nachher = await _tag(lage)
    assert z is not None
    assert round(nachher["wp"], 1) == 12.6 and nachher["wp_stunden"] == 12.6
    assert nachher["leistung"] == vorher["leistung"]
    assert nachher["datenquelle"] == "scheduler"


# ── (d) Lauf L: mit Leistungskurve weiter «historie» ─────────────────────────


async def test_d_lauf_l_mit_leistungskurve_bleibt_historie(tmp_path):
    async with _lk(tmp_path) as lage:
        lage.kurve_leer = False
        erg = await _werkbank(lage)
        nachher = await _tag(lage)
        drift = await _drift_wp(lage)
    assert erg["quelle"] == "historie"
    assert erg.get("quelle_text") is None
    assert round(nachher["wp"], 1) == 12.6
    assert drift == []


# ── (e) Drift-Zeilen: Bestand-Tag und Kanal-Tag tragen den Handgriff ────────


def _ctx(*, kanal_gruppen: dict, hat_spiegel: bool = True):
    from backend.services.daten_checker.datenquelle.quellen import _DriftKontext
    from backend.services.daten_checker.kategorien import CheckKategorie

    ctx = _DriftKontext(anlage=SimpleNamespace(id=7), kat=CheckKategorie.DATENQUELLE_DRIFT.value, tz_list=[],
                        komp_je_tag={}, alle_invs=[SimpleNamespace(id=18, typ="waermepumpe", bezeichnung="WP")])
    ctx.hat_spiegel = hat_spiegel
    ctx.kanal_gruppen = kanal_gruppen
    ctx.drift_pro_tag = [(D2, 30.0, 20.0)]
    ctx.drift_komponente = {"waermepumpe_18": [(D2, 123922.2, 12.6)]}
    return ctx


def test_e_bestand_tag_traegt_den_handgriff_und_den_bestand_text():
    from backend.services.daten_checker.datenquelle.drift_zeilen import drift_komponentenzeilen, drift_tageszeilen

    ctx = _ctx(kanal_gruppen={})
    (tag,) = drift_tageszeilen(ctx)
    (komp,) = drift_komponentenzeilen(ctx)
    for e in (tag, komp):
        assert befund_op(e) == "spiegel_abgleich_tag"
        assert e.knopf == "Aus Home Assistant neu übernehmen"
        assert "Zählerstatistik" in e.details and "baut Tag und Gerätewerte" in e.details
        assert "ein gespeicherter Leistungsverlauf bleibt stehen" in e.details
        assert "derzeit" not in e.details
    assert tag.details == (
        "Für diesen Tag steht in eedc ein anderer Wert als in Home Assistant. „Aus Home Assistant neu übernehmen“ "
        "holt die Zählerstatistik dieses Tages neu und baut Tag und Gerätewerte; ein gespeicherter Leistungsverlauf "
        "bleibt stehen."
    )


def test_e_kanal_tag_unveraendert():
    from backend.services.daten_checker.datenquelle.drift_zeilen import (
        _TEXT_SPIEGEL_TAG, drift_komponentenzeilen, drift_tageszeilen,
    )

    ctx = _ctx(kanal_gruppen={D2: ("bilanz", "wp")})
    (tag,) = drift_tageszeilen(ctx)
    (komp,) = drift_komponentenzeilen(ctx)
    assert tag.details == _TEXT_SPIEGEL_TAG
    assert "Hast du in Home Assistant korrigiert, ist das der Weg." in komp.details
    assert befund_op(tag) == befund_op(komp) == "spiegel_abgleich_tag"


def test_e_wp_bestand_an_einem_bilanz_kanal_tag():
    """Georgs 2.11.: Bilanz aus den Kanälen, Wärmepumpe Bestand — die Tageszeile (PV) liest den Spiegel, die
    WP-Zeile den Bestand."""
    from backend.services.daten_checker.datenquelle.drift_zeilen import (
        _TEXT_SPIEGEL_TAG, drift_komponentenzeilen, drift_tageszeilen,
    )

    ctx = _ctx(kanal_gruppen={D2: ("bilanz",)})
    (tag,) = drift_tageszeilen(ctx)
    (komp,) = drift_komponentenzeilen(ctx)
    assert tag.details == _TEXT_SPIEGEL_TAG
    assert "ein gespeicherter Leistungsverlauf bleibt stehen" in komp.details


def test_e_ohne_spiegel_bleibt_tag_reparieren():
    from backend.services.daten_checker.datenquelle.drift_zeilen import drift_komponentenzeilen, drift_tageszeilen

    ctx = _ctx(kanal_gruppen={}, hat_spiegel=False)
    (tag,) = drift_tageszeilen(ctx)
    assert befund_op(tag) == "reaggregate_day"
    assert "Tag neu aufbauen" in tag.details  # E4: Text = Knopf-Text des Katalogs


# ── (f) Rückmeldung: Werkbank-Route und «Aus Home Assistant neu übernehmen» ─


async def test_f_route_reaggregate_tag_nennt_die_quelle(tmp_path):
    from backend.api.routes.energie_profil.repair import reaggregate_tag

    async with _lk(tmp_path) as lage:
        async with lage.sitzungen() as db:
            antwort = await reaggregate_tag(lage.aid, datum=D2, mit_resnap=False, db=db)
    assert antwort["quelle"] == "zaehler_erhalt"
    assert antwort["quelle_text"] == SATZ


async def test_f_route_unveraendert_bleibt_fehler(tmp_path):
    from backend.api.routes.energie_profil.repair import reaggregate_tag

    async with _lk(tmp_path) as lage:
        lage.svc = _ha_aus()
        async with lage.sitzungen() as db:
            with pytest.raises(HTTPException) as fehler:
                await reaggregate_tag(lage.aid, datum=D2, mit_resnap=False, db=db)
            await db.rollback()
    assert "nicht neu geschrieben" in fehler.value.detail


def test_f_abgleich_meldung_nennt_den_satz():
    from backend.api.routes.energie_profil.repair import _abgleich_tag_meldung

    abgleich = {"hat_spiegel": True, "korrigiert": [], "gekuerzt": [], "fehler": 0}
    satz = _abgleich_tag_meldung(abgleich, D2, quelle_text=SATZ)
    assert satz == f"Statistik aus Home Assistant geprüft — nichts zu korrigieren, Tag 02.11.2026 neu aufgebaut. {SATZ}"
    assert _abgleich_tag_meldung(abgleich, D2) == (
        "Statistik aus Home Assistant geprüft — nichts zu korrigieren, Tag 02.11.2026 neu aufgebaut.")
