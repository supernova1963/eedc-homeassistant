"""Fund-Päckchen C (22.11.2026) — Repo-Tests.

**C2 (N-814): «Aus Home Assistant neu übernehmen» an der E-Mobilität.** Der Abgleich (``kanal/konsistenz.konsistenz_anlage``)
verwirft die abgeleiteten Kanäle (PV-Anteil der Heimladung) ab der ersten korrigierten Stunde; bis zum nächsten Stundenlauf
deckten die Kanäle die E-Mob-Gruppe ab dort nicht, die Gruppe fiel auf die Tageszeile zurück, die an Kanal-Tagen keine
E-Mob-Werte trägt — gemessen am HEAD ``9e0b2bd71`` (``golden-master/funde-c-2026-11-22/test_mess_c2.py``): nach «Summe
anpassen» in HA und dem Knopf Wallbox 28.10. «—», Monat 36,96 statt 72,6; dasselbe am E-Auto und an der Wallbox nach einer
Korrektur an PV (aus deren Stunden der Anteil rechnet). Seit C2 ziehen die Knöpfe die abgeleiteten Kanäle sofort nach
(``konsistenz.abgeleitete_nachziehen``).

Welt: ``test_sensorwechsel_wegb_loeschen_proben`` (HA-Attrappe, stehende Uhr, echte Stundenläufe). Der Oktober der Wallbox
zeigt in dieser Welt HA − 1,32 (Weltrand am 26.10., benannte Grenze dort, ``_pruefe_soll``).

Schwesterdateien: test_funde_b.py (B2: «Summe anpassen» an der ersten Stunde, jetzt auch an der Wallbox festgeschrieben),
test_kanal_abgeleitet.py (Konsistenzlauf verwirft den abgeleiteten Kanal), test_kanal_konsistenz.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

import backend.tests.test_sensorwechsel_wegb_loeschen_proben as P
from backend.tests.test_sensorwechsel_wegb_loeschen_proben import stehende_uhr  # noqa: F401 — Fixture

TAGE = [date(2026, 10, 27), date(2026, 10, 28)]


def _tag(d: date) -> tuple[datetime, datetime]:
    return datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())


async def _welt_mit_sprung(db, monkeypatch, an: str, *, eauto: bool = False):
    """PV Feld, PV-Kontrolle und Ladezähler über HA; am Sensor ``an`` springt die Summe am 27.10. 12:00 um +2 000 kWh;
    Betrieb bis 29.10. 03:00; danach in HA «Summe anpassen» (−2 000 ab der Stunde)."""
    v = P.ep(P.START) - 5 * P.STUNDE
    sprung = P.ep(datetime(2026, 10, 27, 12))
    raten = {P.ALT: 0.6, P.PVC: 2.0, P.WB: 1.32}
    serien = {eid: (v, (lambda e, r=r, s=(eid == an): r + 2000.0 if s and e == sprung else r)) for eid, r in raten.items()}
    if eauto:
        monkeypatch.setitem(P.FELDER, "wb", ("2", "ladung_kwh", "inv:2:ladung_kwh", "eauto_2"))
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=False)
    if eauto:
        await db.execute(text("update investitionen set typ = 'e-auto' where id = 2"))
        await db.commit()
        P.frisch(w)
    monkeypatch.setattr("backend.core.database.get_session", w.sitzungen)   # der Abgleich öffnet eigene Sitzungen

    async def _ohne_boerse(*_a, **_k):
        return None              # der Tag-Lauf fragt die Börse; kein Netz in Proben
    monkeypatch.setattr("backend.services.strompreis_markt_service.fetch_marktpreise", _ohne_boerse)
    ende = datetime(2026, 10, 29, 3)
    await P.betrieb_bis(w, P.START, ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    vorher = await P.sichten(w, "wb", TAGE, (2026, 10))
    with w.svc._engine.begin() as c:
        c.execute(text("UPDATE statistics SET sum = sum - 2000.0 WHERE metadata_id = :m AND start_ts >= :t"),
                  {"m": w.mids[an], "t": sprung})
    return w, vorher


async def _knopf(w, datum: str = "2026-10-27"):
    from backend.services.repair_orchestrator import RepairOperationRequest, RepairOperationType, execute, plan

    p = await plan(RepairOperationRequest(anlage_id=w.a.id, operation=RepairOperationType("spiegel_abgleich_tag"),
                                          params={"datum": datum}), w.db)
    r = await execute(p.plan_id, w.db)
    await w.db.commit()                  # wie ``get_db`` nach der Route
    assert r.operation_summary.get("fehlgeschlagen", 0) == 0, r.operation_summary
    P.frisch(w)


@pytest.mark.parametrize("eauto", [False, True], ids=["wallbox", "e_auto"])
async def test_c2_nach_dem_knopf_zeigen_tag_und_monat_der_e_mobilitaet_home_assistant(db, monkeypatch, stehende_uhr,  # noqa: F811
                                                                                      eauto):
    w, _vorher = await _welt_mit_sprung(db, monkeypatch, P.WB, eauto=eauto)
    await _knopf(w)
    s = await P.sichten(w, "wb", TAGE, (2026, 10))
    ha = {d: w.ha_summe(P.WB, *_tag(d)) for d in TAGE}
    assert s["tage"] == ha == {TAGE[0]: 31.68, TAGE[1]: 31.68}          # am HEAD: 28.10. «—»
    ha_okt = w.ha_summe(P.WB, datetime(2026, 10, 1), datetime(2026, 11, 1))
    assert s["aus_ha_laden"] == ha_okt
    assert s["monatssicht"] == P.r3(ha_okt - 1.32) == 72.6              # am HEAD: 36,96 (Weltrand 26.10.: − 1,32)


async def test_c2_korrektur_an_pv_laesst_die_wallbox_stehen(db, monkeypatch, stehende_uhr):  # noqa: F811
    """Der PV-Anteil der Heimladung rechnet aus den Stunden von PV und Netz — eine Korrektur an PV verwarf ihn ebenso; die
    Wallbox (selbst unberührt) zeigte danach am 28.10. «—». Jetzt bleibt sie, wie sie war."""
    w, vorher = await _welt_mit_sprung(db, monkeypatch, P.ALT)
    await _knopf(w)
    nachher = await P.sichten(w, "wb", TAGE, (2026, 10))
    assert (nachher["tage"], nachher["monatssicht"]) == (vorher["tage"], vorher["monatssicht"]) \
        == ({TAGE[0]: 31.68, TAGE[1]: 31.68}, 72.6)
    pv = await P.sichten(w, "pv", TAGE, (2026, 10))
    assert pv["tage"] == {d: w.ha_summe(P.ALT, *_tag(d)) for d in TAGE}


async def test_c2_abgeleitete_nachziehen_schreibt_bis_zur_letzten_abgeschlossenen_stunde(db, monkeypatch, stehende_uhr):  # noqa: F811
    """Nach dem Abgleich trägt der abgeleitete Kanal wieder jede Stunde bis zur letzten abgeschlossenen (29.10. 02:00), wie
    nach einem Stundenlauf — am HEAD endete er an der Stunde vor der Korrektur (27.10. 11:00)."""
    w, _vorher = await _welt_mit_sprung(db, monkeypatch, P.WB)
    await _knopf(w)
    letzte = (await w.db.execute(text(
        "select max(s.start_ts) from kanal_statistik s join kanal k on k.id = s.kanal_id "
        "where k.anlage_id = :a and k.key = 'abgeleitet:inv:2:ladung_pv_kwh'"), {"a": w.a.id})).scalar_one()
    assert datetime.fromtimestamp(letzte) == datetime(2026, 10, 29, 2)
