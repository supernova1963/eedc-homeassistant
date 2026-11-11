"""Reparatur-Operationen der Daten-Checker-Knöpfe (Etappe E3; Bauplan §4 W-12, §6 E3; Gegenprüfung W1, W2, Ü4, Ü5).

Je Operation (``services/repair_operationen_checker.py``):
* **Plan schreibt nichts** — SQLite-Dump der betroffenen Tabellen vor/nach ``plan()`` bitgleich;
* **Ausführen = Ergebnis der bisherigen Route** (bitgleich) — zwei gleich gesäte Anlagen, die eine über
  ``plan()``/``execute()``, die andere über die Route; die Antworten sind gleich bis auf die Ids;
* **409-Fälle ⇒ Plan «nichts zu tun»** (Feld am Gerät vorgesehen, Monat hat noch eine Zählerzeile), Ausführen wirft
  ``ValueError`` und schreibt nichts;
* ``SPIEGEL_ABGLEICH_TAG``: der Plan ruft Home Assistant nicht (Fake-HA zählt 0 Aufrufe), das Ausführen ist der Lauf der
  Route ``spiegel-abgleich-tag`` ohne eigenen Plan der Neu-Aggregation;
* **W-12:** je Ausführen genau eine Zeile ``repair``, keine Zeile ``ha_statistics`` (Checker-Weg).

Schwesterdateien: ``test_repair_orchestrator.py`` (W-12 der übrigen Operationen), ``test_n790_drift_handgriff.py``
(Spiegel-Route), ``test_349_monat_loeschen_geraetewerte.py``, ``test_n393_wert_in_nicht_gefuehrtem_feld.py``,
``test_n426_temperatur_historie.py`` (die drei Monatsdaten-Routen).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.services.repair_protokoll import NichtsZuTun
from sqlalchemy import select, text

from backend.models import Anlage, Monatsdaten
from backend.models.activity_log import ActivityLog
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.services import repair_operationen_checker as roc
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _reset_state_for_tests,
    execute,
    plan,
)
from backend.tests.test_349_monat_loeschen_geraetewerte import _seed, _verwaister_zustand
from backend.tests.test_n393_wert_in_nicht_gefuehrtem_feld import _anlage_mit
from backend.tests.test_n426_temperatur_historie import _anlage as _temp_anlage

TABELLEN = ("monatsdaten", "investition_monatsdaten", "data_provenance_log", "activity_log", "kanal_statistik",
            "kanal_quelle", "tages_zusammenfassung", "tages_energie_profil")


@pytest.fixture(autouse=True)
def _leer():
    _reset_state_for_tests()


async def _dump(db) -> dict:
    return {t: [tuple(r) for r in (await db.execute(text(f"select * from {t} order by 1"))).all()] for t in TABELLEN}


async def _repair_zeilen(db, kategorie: str = "repair") -> list[ActivityLog]:
    return list((await db.execute(select(ActivityLog).where(ActivityLog.kategorie == kategorie))).scalars().all())


def _req(anlage_id: int, op: RepairOperationType, **params) -> RepairOperationRequest:
    return RepairOperationRequest(anlage_id=anlage_id, operation=op, params=params)


async def _plan_ohne_schreiben(db, req: RepairOperationRequest):
    vorher = await _dump(db)
    p = await plan(req, db)
    assert await _dump(db) == vorher, "der Plan hat geschrieben"
    return p


# ── TEMPERATUR_AUS_MESSUNG (Ü5: ohne Parameter) ──────────────────────────────────────────────────────────────────

async def test_temperatur_plan_ausfuehren_gleich_route(db):
    from backend.api.routes.monatsdaten import temperatur_aus_messung_uebernehmen

    a = await _temp_anlage(db, monate={1: None, 2: None, 3: None}, messreihe={1: 2.0, 2: 3.5})
    b = await _temp_anlage(db, monate={1: None, 2: None, 3: None}, messreihe={1: 2.0, 2: 3.5})
    p = await _plan_ohne_schreiben(db, _req(a.id, RepairOperationType.TEMPERATUR_AUS_MESSUNG))
    assert p.estimated_changes == {"monate_temperatur_gefuellt": 2, "monate_ohne_temperatur": 3}
    assert p.operation_preview["monate"] == ["01/2026", "02/2026"] and p.warnings == []
    r = await execute(p.plan_id, db)
    route = await temperatur_aus_messung_uebernehmen(b.id, db=db)
    assert {**r.operation_summary, "anlage_id": 0} == {**route, "anlage_id": 0}
    assert r.operation_summary["gefuellt"] == 2
    assert len(await _repair_zeilen(db)) == 1

    nochmal = await plan(_req(a.id, RepairOperationType.TEMPERATUR_AUS_MESSUNG), db)
    assert "nichts_zu_tun" in nochmal.operation_preview and nochmal.estimated_changes == {}


# ── FELDWERT_ENTFERNEN (Ü4: 409 ⇒ «nichts zu tun») ────────────────────────────────────────────────────────────

async def test_feldwert_plan_ausfuehren_gleich_route(db):
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    monate = {5: {"warmwasser_kwh": 40.0}, 6: {"warmwasser_kwh": 2.5}}
    a, inv_a = await _anlage_mit(db, typ="waermepumpe", parameter={"wp_art": "luft_luft"}, monate=monate)
    _b, inv_b = await _anlage_mit(db, typ="waermepumpe", parameter={"wp_art": "luft_luft"}, monate=monate)
    p = await _plan_ohne_schreiben(db, _req(a.id, RepairOperationType.FELDWERT_ENTFERNEN,
                                            investition_id=inv_a.id, feld="warmwasser_kwh"))
    assert p.estimated_changes == {"monate_wert_entfernt": 2}
    assert p.operation_preview["monate"] == ["05/2026", "06/2026"] and p.operation_preview["werte"] == [40.0, 2.5]
    assert p.operation_preview["summe"] == 42.5 and p.operation_preview["endgueltig"] is True
    r = await execute(p.plan_id, db)
    route = await delete_feldwert_nicht_gefuehrt(inv_b.id, "warmwasser_kwh", db=db)
    assert {**r.operation_summary, "investition_id": 0} == {**route, "investition_id": 0}
    assert r.operation_summary["entfernt"] == 2 and len(await _repair_zeilen(db)) == 1


async def test_feldwert_am_geraet_vorgesehen_ist_nichts_zu_tun(db):
    a, inv = await _anlage_mit(db, typ="waermepumpe", parameter={"wp_art": "luft_wasser"},
                               monate={5: {"warmwasser_kwh": 40.0}})
    p = await _plan_ohne_schreiben(db, _req(a.id, RepairOperationType.FELDWERT_ENTFERNEN,
                                            investition_id=inv.id, feld="warmwasser_kwh"))
    assert p.estimated_changes == {} and "im Monatsabschluss erreichbar" in p.operation_preview["nichts_zu_tun"]
    vorher = await _dump(db)
    # E5: ein Plan «nichts zu tun» wird nicht ausgeführt (`NichtsZuTun` ⇒ Route 409), keine Protokollzeile.
    with pytest.raises(NichtsZuTun, match="im Monatsabschluss erreichbar"):
        await execute(p.plan_id, db)
    await db.rollback()
    assert {t: v for t, v in (await _dump(db)).items() if t != "activity_log"} == \
        {t: v for t, v in vorher.items() if t != "activity_log"}
    assert await _repair_zeilen(db) == []


async def test_feldwert_fremde_anlage_ist_400(db):
    a, inv = await _anlage_mit(db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
                               monate={5: {"warmwasser_kwh": 40.0}})
    with pytest.raises(ValueError, match="gehört nicht zu Anlage"):
        await plan(_req(a.id + 1000, RepairOperationType.FELDWERT_ENTFERNEN, investition_id=inv.id,
                        feld="warmwasser_kwh"), db)


# ── GERAETEWERTE_LOESCHEN (nur Werkbank; 409 ⇒ «nichts zu tun») ──────────────────────────────────────────────

async def test_geraetewerte_plan_ausfuehren_gleich_route(db):
    from backend.api.routes.monatsdaten import delete_verwaiste_geraetewerte

    a, _inv_a, md_a = await _seed(db)
    b, _inv_b, md_b = await _seed(db)
    await _verwaister_zustand(db, md_a)
    await _verwaister_zustand(db, md_b)
    await db.commit()
    p = await _plan_ohne_schreiben(db, _req(a.id, RepairOperationType.GERAETEWERTE_LOESCHEN, jahr=2024, monat=6))
    assert p.estimated_changes == {"geraetewerte_zeilen_geloescht": 1}
    assert p.operation_preview["komponenten"] == ["Sofar Station 2"] and p.operation_preview["endgueltig"] is True
    r = await execute(p.plan_id, db)
    route = await delete_verwaiste_geraetewerte(b.id, 2024, 6, db=db)
    assert r.operation_summary == route == {"jahr": 2024, "monat": 6, "geloescht": 1, "komponenten": ["Sofar Station 2"]}
    assert len(await _repair_zeilen(db)) == 1


async def test_geraetewerte_mit_zaehlerzeile_ist_nichts_zu_tun(db):
    a, _inv, _md = await _seed(db)
    await db.commit()
    p = await _plan_ohne_schreiben(db, _req(a.id, RepairOperationType.GERAETEWERTE_LOESCHEN, jahr=2024, monat=6))
    assert "hat noch eine Zählerzeile" in p.operation_preview["nichts_zu_tun"]
    with pytest.raises(NichtsZuTun, match="hat noch eine Zählerzeile"):
        await execute(p.plan_id, db)
    assert await _repair_zeilen(db) == []


# ── SPIEGEL_ABGLEICH_TAG (Plan ohne HA; Ausführen = Lauf der Route) ────────────────────────────────────────────

async def _spiegel_anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="Spiegel", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    kanal = Kanal(anlage_id=anlage.id, key="basis:netzbezug", art=ART_SUM, einheit="kWh")
    db.add(kanal)
    await db.flush()
    ab = int(datetime(2026, 11, 1).timestamp())
    db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=ab, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz"))
    db.add_all([KanalStatistik(kanal_id=kanal.id, start_ts=ab + 3600 * i, sum=float(i), state=float(i),
                               familie=FAMILIE_SPIEGEL) for i in range(5)])
    await db.commit()
    return anlage


async def test_spiegel_plan_ruft_home_assistant_nicht(db, monkeypatch):
    """H-E3-1: der Plan liest nur ``kanal``/``kanal_quelle``/``kanal_statistik``."""
    from backend.services import ha_statistics_service

    aufrufe: list = []

    def _fake(*a, **k):
        aufrufe.append((a, k))
        raise AssertionError("der Plan darf Home Assistant nicht fragen")

    monkeypatch.setattr(ha_statistics_service, "get_ha_statistics_service", _fake)
    monkeypatch.setattr("backend.services.kanal.konsistenz.konsistenz_anlage", _fake)
    anlage = await _spiegel_anlage(db)
    p = await _plan_ohne_schreiben(db, _req(anlage.id, RepairOperationType.SPIEGEL_ABGLEICH_TAG, datum="2026-11-01"))
    assert aufrufe == []
    assert p.estimated_changes == {"spiegel_kanaele": 1, "spiegel_abschnitte": 1, "tage_neu_aufgebaut": 1}
    assert p.operation_preview["hat_spiegel"] is True and p.operation_preview["vorbedingung"] is True
    assert p.operation_preview["kanaele"][0]["key"] == "basis:netzbezug"
    assert p.operation_preview["kanaele"][0]["letzte_stunde"].startswith("2026-11-01 04:00")


async def test_spiegel_ausfuehren_ist_der_lauf_der_route_mit_einer_zeile(db, monkeypatch):
    """Ausführen = ``spiegel_abgleich_tag_lauf`` (dieselbe Antwort wie die Route); die Neu-Aggregation läuft ohne eigenen
    Plan (``eigener_lauf=False``) — genau eine Zeile ``repair``, keine Zeile ``ha_statistics`` (W-12)."""
    from backend.api.routes.energie_profil import repair
    from backend.services.kanal.konsistenz import KonsistenzErgebnis

    async def _lauf(_sitzungen, anlage_id, **_k):
        return KonsistenzErgebnis(anlage_id)

    gerufen: list = []

    async def _tag(db_, anlage_id, datum, mit_resnap, *, eigener_lauf=True):
        gerufen.append((anlage_id, datum, mit_resnap, eigener_lauf))
        return {"status": "ok", "datum": datum.isoformat()}

    monkeypatch.setattr("backend.services.kanal.konsistenz.konsistenz_anlage", _lauf)
    monkeypatch.setattr(repair, "tag_neu_aufbauen_antwort", _tag)
    anlage = await _spiegel_anlage(db)
    p = await plan(_req(anlage.id, RepairOperationType.SPIEGEL_ABGLEICH_TAG, datum="2026-11-01"), db)
    r = await execute(p.plan_id, db)
    assert gerufen == [(anlage.id, date(2026, 11, 1), True, False)]
    assert r.operation_summary["meldung"] == "Statistik aus Home Assistant geprüft — nichts zu korrigieren, Tag 01.11.2026 neu aufgebaut."
    assert set(r.operation_summary) == {"anlage_id", "datum", "abgleich", "reaggregation", "meldung"}
    assert len(await _repair_zeilen(db)) == 1 and await _repair_zeilen(db, "ha_statistics") == []

    route = await repair.spiegel_abgleich_tag(anlage.id, repair.SpiegelAbgleichTagRequest(datum="2026-11-01"), db=db)
    assert route == r.operation_summary
    assert gerufen[-1][-1] is True, "die Route behält ihren eigenen Lauf"


async def test_unbekannte_operation_bleibt_valueerror():
    class _Op:
        value = "gibt_es_nicht"

    req = RepairOperationRequest.model_construct(anlage_id=1, operation=_Op(), params={})
    with pytest.raises(ValueError, match="Unbekannte Operation"):
        await roc.plan_operation(req, None)


def test_die_vier_operationen_stehen_im_enum_und_im_protokoll():
    from backend.services.repair_protokoll import OPERATION_LABELS

    werte = {o.value for o in RepairOperationType}
    assert set(roc.OPERATIONEN) <= werte and set(roc.OPERATIONEN) <= set(OPERATION_LABELS)
    assert set(OPERATION_LABELS) == werte - {"solcast_rewrite"}


async def test_monatsdaten_zeilen_bleiben_beim_temperatur_plan_unberuehrt(db):
    a = await _temp_anlage(db, monate={1: None}, messreihe={1: 2.0})
    await plan(_req(a.id, RepairOperationType.TEMPERATUR_AUS_MESSUNG), db)
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalar_one()
    assert md.durchschnittstemperatur is None
