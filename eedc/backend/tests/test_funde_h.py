"""Fund-Päckchen H (23.11.2026) — Proben zu H1 (Werkbank «Werte eines Felds vor einem Zeitpunkt verwerfen»: Quelle bei ``t``
teilen, eine Bedeutung der Marke im Nachfüllen), H2 (Einmal-Lauf: abgeleiteter Heimlade-Kanal ab dem ersten markierten
Stillstand neu) und H3 (Cockpit → Monat ohne Kanal-Deckung: Quote der Tagesebene wie die Monats-Fakten).

Fixtures aus ``test_kanal_nachfuellen.py`` (Datei-DB, HA-Langzeitstatistik im Recorder-Schema). Keine echte Uhr: die Uhr der
Operation steht auf ``JETZT`` der Fixture. Schwesterdateien: ``test_werkbank_verwerfen_kommt_nicht_zurueck.py``,
``test_sensorwechsel_wegb_loeschen_proben.py``, ``test_rf34_emob_heimladung_pool_zweige.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_, delete, func, insert, select

from backend.api.routes.aktueller_monat.aggregation import emob_heimladung_pool
from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo
from backend.models import Investition
from backend.models.anlage import Anlage
from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik
from backend.services.kanal.konsistenz import konsistenz_anlage
from backend.services.kanal.nachfuellen import nachfuellen_anlage, nachfuellen_spiegel
from backend.services.kanal.verwerfen import untergrenze_nach_verworfen
from backend.services.repair_orchestrator import _reset_state_for_tests
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    JETZT,
    ZEIT,
    _ts,
    datei,
    ha,
)

EINSP = "basis:einspeisung"
T = ZEIT + timedelta(days=10)          # frei gewählter Zeitpunkt, mitten in der einzigen Quelle


@pytest.fixture(autouse=True)
def _uhr(monkeypatch):
    _reset_state_for_tests()
    monkeypatch.setattr("backend.services.verwerfen_vor_zeitpunkt.uhr", lambda: JETZT)
    monkeypatch.setattr("backend.services.zuordnung_wechsel.korrektur.ha_eingerichtet", lambda: False)


def _q(ab: int, sid, verworfen=None) -> SimpleNamespace:
    return SimpleNamespace(gueltig_ab=ab, statistic_id=sid, verworfen_ts=verworfen)


def test_h1_eine_bedeutung_der_marke_untergrenze():
    assert untergrenze_nach_verworfen([_q(0, "a"), _q(10, "b")]) is None                     # nichts verworfen
    assert untergrenze_nach_verworfen([_q(0, "a", 5), _q(10, "a")]) == 10                    # Teilung, dieselbe Entity
    assert untergrenze_nach_verworfen([_q(0, "a", 5), _q(10, "b"), _q(20, "a")]) == 10       # A → B → A
    assert untergrenze_nach_verworfen([_q(0, None, 5), _q(10, "b")]) is None                 # Platzhalter von «löschen»
    assert untergrenze_nach_verworfen([_q(0, "a", 5)]) == 2 ** 62                            # keine Quelle danach


async def _quellen(sitzungen, aid: int, key: str) -> tuple[int, list[KanalQuelle]]:
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(and_(Kanal.anlage_id == aid, Kanal.key == key)))).scalar_one()
        return k.id, list((await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                                           .order_by(KanalQuelle.gueltig_ab))).scalars().all())


async def _vor(sitzungen, kanal_id: int, t: int) -> int:
    async with sitzungen() as s:
        return int((await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts < t)))).scalar_one())


async def test_h1_quelle_geteilt_und_die_zeit_vor_t_kommt_nicht_zurueck(ha, datei):
    """Eine Quelle, dieselbe Entity: die Zeilen vor ``t`` gehen, die Quelle ist bei ``t`` geteilt (alte mit Marke, neue
    derselben Entity und desselben ``offset``); Nachfüllen mit und ohne Marke, Konsistenzlauf holen nichts vor ``t``."""
    from backend.services import feld_loeschen

    svc, _ = ha
    sitzungen, _pfad, aid, _gid = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    kid, vorher = await _quellen(sitzungen, aid, EINSP)
    assert [q.statistic_id for q in vorher] == ["sensor.einsp"]
    assert await _vor(sitzungen, kid, _ts(T)) > 0
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        g = await feld_loeschen.loesche_vor(s, a, EINSP, T, auch_abschluss=True, zum_platzhalter=False, jetzt=JETZT,
                                            teilen=True)
    assert g.geteilt == 1 and g.quellen == 1 and g.kanalzeilen > 0
    _kid, qs = await _quellen(sitzungen, aid, EINSP)
    assert [(q.statistic_id, q.gueltig_ab, q.verworfen_ts is not None, q.offset) for q in qs] == [
        ("sensor.einsp", vorher[0].gueltig_ab, True, vorher[0].offset), ("sensor.einsp", _ts(T), False, vorher[0].offset)]
    assert await _vor(sitzungen, kid, _ts(T)) == 0
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert await _vor(sitzungen, kid, _ts(T)) == 0
    async with sitzungen() as s:                                   # schärfste Lage: keine Marke
        await s.execute(delete(KanalNachfuellung).where(KanalNachfuellung.kanal_id == kid))
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert erg.uebersprungen.get("vorgeschichte_verworfen") == 1
    assert await _vor(sitzungen, kid, _ts(T)) == 0
    k = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert k.fehler == 0 and await _vor(sitzungen, kid, _ts(T)) == 0


async def test_h1_operation_ueber_den_orchestrator_stand_feld(ha, datei, monkeypatch):
    """Plan und Ausführen wie die Route (Stand-Feld ohne Bestand-Schlüssel): Vorschau-Sätze, Zählerstände vor ``t`` weg,
    Lauf angelegt (gestartet wird er hier nicht), Protokollzeile «Reparatur: Werte eines Felds vor einem Zeitpunkt
    verwerfen»."""
    from backend.models.activity_log import ActivityLog
    from backend.services.repair_orchestrator import (
        RepairOperationRequest, RepairOperationType, execute, plan,
    )
    from backend.services.zuordnung_wechsel import korrektur_lauf

    gestartet = []
    monkeypatch.setattr(korrektur_lauf, "starten", lambda lauf, **kw: gestartet.append(lauf))
    svc, _ = ha
    sitzungen, _pfad, aid, gid = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    key = f"inv:{gid}:zaehlerstand"
    kid, _ = await _quellen(sitzungen, aid, key)
    req = RepairOperationRequest(anlage_id=aid, operation=RepairOperationType.VERWERFEN_VOR_ZEITPUNKT,
                                 params={"kanal": key, "zeitpunkt": T.strftime("%Y-%m-%dT%H:00")})
    async with sitzungen() as s:
        p = await plan(req, s)
    assert p.warnings[0].startswith("Verworfen werden die Werte von «Gas")
    assert p.warnings[-1] == "Das lässt sich nicht rückgängig machen."
    assert any(x.startswith("Es bleiben: jedes andere Feld, Wetter") for x in p.warnings)
    async with sitzungen() as s:
        res = await execute(p.plan_id, s)
    summary = res.operation_summary
    assert summary["quelle_geteilt"] == 1 and summary["kanalzeilen_geloescht"] > 0
    assert gestartet == [summary["lauf"]]
    assert await _vor(sitzungen, kid, _ts(T)) == 0
    async with sitzungen() as s:
        aktionen = [a for (a,) in (await s.execute(select(ActivityLog.aktion))).all()]
        z = await korrektur_lauf.stand(s, summary["lauf"])
    assert "Reparatur: Werte eines Felds vor einem Zeitpunkt verwerfen" in aktionen
    assert z["art"] == korrektur_lauf.ART_LOESCHEN and z["fuellen"]["ha"] is False


async def test_h1_zeitpunkt_in_der_zukunft_wird_abgelehnt(datei):
    from backend.services import verwerfen_vor_zeitpunkt as vz

    sitzungen, _pfad, aid, gid = datei
    async with sitzungen() as s:
        with pytest.raises(ValueError, match="Zukunft"):
            await vz.lage(s, aid, {"kanal": EINSP, "zeitpunkt": (JETZT + timedelta(hours=2)).strftime("%Y-%m-%dT%H:00")})


async def test_h2_einmal_lauf_verwirft_den_heimlade_kanal_ab_dem_ersten_fenster(datei, monkeypatch):
    from backend.services.migrations import migrate_heimladung_stillstand as h2

    sitzungen, _pfad, aid, _gid = datei
    beginn = _ts(ZEIT)
    async with sitzungen() as s:
        for key in ("abgeleitet:inv:9:ladung_pv_kwh", "abgeleitet:inv:9:modus_strom_heizen_kwh"):
            k = Kanal(anlage_id=aid, key=key, art="sum", einheit="kWh")
            s.add(k)
            await s.flush()
            await s.execute(insert(KanalStatistik), [
                {"kanal_id": k.id, "start_ts": beginn + h * 3600, "sum": float(h), "state": None,
                 "familie": "abgeleitet"} for h in range(72)])
    fenster = [SimpleNamespace(von_ts=beginn + 30 * 3600), SimpleNamespace(von_ts=beginn + 50 * 3600)]

    async def _fenster(db, anlage_id, von, bis, **kw):
        return list(fenster)
    monkeypatch.setattr("backend.services.kanal.stillstand.fenster_im_bereich", _fenster)
    async with sitzungen() as s:
        erg = await h2.heimladung_ab_stillstand_neu(s)
    assert erg == {aid: 42}
    async with sitzungen() as s:
        n = dict((await s.execute(select(Kanal.key, func.count(KanalStatistik.start_ts)).join(
            KanalStatistik, KanalStatistik.kanal_id == Kanal.id).group_by(Kanal.key))).all())
    assert n["abgeleitet:inv:9:ladung_pv_kwh"] == 30 and n["abgeleitet:inv:9:modus_strom_heizen_kwh"] == 72
    fenster.clear()                                                  # ohne Fenster: nichts
    async with sitzungen() as s:
        assert await h2.heimladung_ab_stillstand_neu(s) == {}


_LIVE = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)


def _inv(inv_id: int, typ: str) -> Investition:
    return Investition(id=inv_id, anlage_id=1, typ=typ, bezeichnung=f"{typ} {inv_id}", anschaffungsdatum=date(2024, 1, 1),
                       aktiv=True, parameter={})


@pytest.mark.parametrize("felder,typen", [({"inv_7_ladung_kwh": 100.0}, ("e-auto",)),
                                          ({"inv_5_ladung_kwh": 100.0}, ("e-auto", "wallbox"))])
def test_h3_ohne_kanal_deckung_gilt_die_quote_der_tagesebene(felder, typen):
    invs = [_inv(7 if t == "e-auto" else 5, t) for t in typen]

    def pool(**kw):
        resolved = {k: (v, _LIVE) for k, v in felder.items()}
        p = emob_heimladung_pool(direct_fields=set(), investitionen=invs, jahr=2026, monat=11, resolved=resolved,
                                 ist_aktueller_monat=True, **kw)["emob_entscheid"].pool
        return round(p.pv_kwh, 6), round(p.netz_kwh, 6)

    assert pool() == (0.0, 100.0)                                    # ohne Quote: keine Aussage über PV
    assert pool(tages_quote=0.8) == (80.0, 20.0)                     # wie die Monats-Fakten
    assert pool(tages_quote=0.8, kanal_quote=(True, 0.5)) == (50.0, 50.0)   # Kanal-Deckung gewinnt


@pytest.mark.parametrize("text", ["2026-03-29T03:00", "2026-10-25T02:00", "2026-10-25T03:00", "2026-04-05T02:00"])
def test_h1_zeitpunkt_an_umstellungstagen_ist_wanduhr(text):
    """Der Zeitpunkt ist eine Wanduhr-Angabe der Prozesszone: er kommt als derselbe Text zurück (auch an den Umstellungstagen
    Europas und Neuseelands) und liegt auf einer vollen Stunde."""
    from backend.services.kanal.verwerfen import text_aus_zeitpunkt, zeitpunkt_aus_text

    ts = zeitpunkt_aus_text(text)
    assert ts % 1800 == 0                                                 # volle Stunde (auch in Zonen mit halber Stunde)
    assert zeitpunkt_aus_text(text_aus_zeitpunkt(ts)) == ts               # Hin und zurück dieselbe Sekunde
