"""W-11 Kein Knopf ohne Wirkung (Etappe E3, Bauplan §4; Konzept §3.1 R3/R7; Gegenprüfung Sprengsatz S2).

**Regel.** Ein Aktion-Knopf steht nur dort, wo ein Test beweist, dass der Befund nach dem Lauf verschwindet oder sich
ändert — über die eine Mechanik (``plan`` → ``execute``) mit den Parametern, die der Befund trägt. An Kanal-Tagen liefert
der Erzeuger kein ``REAGGREGATE_*`` (die Neu-Aggregation schreibt dort keine Mengen): mit HA-Spiegel «Aus Home Assistant
neu übernehmen», ohne Spiegel kein Knopf (Kanal-Lage-Weiche R7).

**Abdeckung je Operation × Lage** (``WIRKUNG``): jede Operation, die ein Erzeuger unter ``services/daten_checker/``
als Aktion setzt (AST), hat mindestens einen Wirkungs-Beleg; jeder Beleg ist ein Test, der existiert. Eine Operation ohne
Beleg ist rot. Die Lagen: Bestandstag (der Tag liest Tages-/Stundenzeilen) · Kanal-Tag mit Spiegel · Kanal-Tag ohne
Spiegel · «Monat» (Operationen auf Monatszeilen, ohne Tageslage).

Schwesterdateien: ``test_repair_operationen_checker.py``, ``test_n790_drift_handgriff.py``,
``test_n791_reparatur_zaehler_ohne_leistungskurve.py``, ``test_daten_checker_texte.py`` (W-4),
``test_s5_e2_checker_kanal_mengen.py`` (Datenstand und Uhr der E5.4-Szenarien je Aktions-Code).
"""
from __future__ import annotations

from backend.tests.werkzeug_befund import befund_op, befund_params
import ast
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest

from backend.services.daten_checker.kategorien import AKTION_SPIEGEL_ABGLEICH_TAG
from backend.tests.test_s5_e2_checker_kanal_mengen import uhr  # noqa: F401 — Fixture `uhr` (E5.4-Szenarien)
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _reset_state_for_tests,
    execute,
    plan,
)

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"

#: Operation → [(Lage, Beleg «datei::test»)]. Ein Beleg führt den Knopf über plan → execute aus und prüft den Befund danach.
WIRKUNG: dict[str, list[tuple[str, str]]] = {
    "reaggregate_day": [
        ("Bestandstag", "test_n791_reparatur_zaehler_ohne_leistungskurve.py::test_a_lk_reparatur_schreibt_zaehlerwerte_und_laesst_den_leistungsverlauf"),
        ("Kanal-Tag mit Spiegel (S2: Abgleich statt Tag)", "test_n790_drift_handgriff.py::test_a_komponenten_achse_mit_spiegel_traegt_den_handgriff"),
    ],
    "reaggregate_range": [
        ("Bestandstag", "test_n791_reparatur_zaehler_ohne_leistungskurve.py::test_w11_bereich_ueber_plan_und_ausfuehren_behebt_die_drift"),
        ("Kanal-Tag mit Spiegel", "test_daten_checker_handgriff_wirkt.py::test_s2_kanal_tag_mit_spiegel_bekommt_den_abgleich"),
        ("Kanal-Tag ohne Spiegel", "test_daten_checker_handgriff_wirkt.py::test_s2_kanal_tag_ohne_spiegel_ohne_knopf"),
        ("Bestand + Kanal gemischt", "test_daten_checker_handgriff_wirkt.py::test_s2_bereich_nur_ueber_bestandstage"),
    ],
    AKTION_SPIEGEL_ABGLEICH_TAG: [
        ("Kanal-Tag mit Spiegel", "test_n790_drift_handgriff.py::test_c_kette_ueber_plan_und_ausfuehren"),
        ("Bestandstag mit Spiegel", "test_n791_reparatur_zaehler_ohne_leistungskurve.py::test_w11_aus_home_assistant_neu_uebernehmen_ueber_plan_und_ausfuehren"),
    ],
    "kraftstoffpreis_backfill": [
        ("Monat", "test_daten_checker_vergleichspreis_fehlt.py::test_w11_benzinpreise_nachtragen_ueber_plan_und_ausfuehren"),
    ],
    "wetter_backfill": [
        ("Monat", "test_wetter_nachzug_und_checker.py::test_w11_wetterreihe_nachziehen_ueber_plan_und_ausfuehren"),
    ],
    "temperatur_aus_messung": [
        ("Monat", "test_daten_checker_handgriff_wirkt.py::test_temperatur_aus_messung_wirkt"),
    ],
    "feldwert_entfernen": [
        ("Monat", "test_daten_checker_handgriff_wirkt.py::test_wert_entfernen_wirkt"),
    ],
}


#: E5.4 (Bauplan §1, Nachmessung E3 Punkt 5): **je Aktions-Code** ein Szenario — der Befund entsteht, seine Aktion läuft
#: über ``plan`` → ``execute`` mit den Parametern des Befunds, ein erneuter Check zeigt ihn nicht mehr oder anders.
#: Code → Beleg «datei::test». Ein Aktions-Code des Katalogs ohne Eintrag ist rot (H-E5-3: benennen, nicht ausnehmen).
WIRKUNG_JE_CODE: dict[str, str] = {
    "drift_komponente": "test_n790_drift_handgriff.py::test_c_kette_ueber_plan_und_ausfuehren",
    "vergleichspreis_fehlt": "test_daten_checker_vergleichspreis_fehlt.py::test_w11_benzinpreise_nachtragen_ueber_plan_und_ausfuehren",
    "wetterreihe_nachziehen": "test_wetter_nachzug_und_checker.py::test_w11_wetterreihe_nachziehen_ueber_plan_und_ausfuehren",
    "temperatur_aus_messung_moeglich": "test_daten_checker_handgriff_wirkt.py::test_temperatur_aus_messung_wirkt",
    "feldwert_nicht_gefuehrt": "test_daten_checker_handgriff_wirkt.py::test_wert_entfernen_wirkt",
    # E5.4 — Szenarien auf der Achsen-Matrix (``kg.datenstand``), Abschnitt «je Aktions-Code» unten.
    "ha_zaehler_rueckgang": "test_daten_checker_handgriff_wirkt.py::test_w11_ha_zaehler_rueckgang_wirkt",
    "ha_zaehlersprung": "test_daten_checker_handgriff_wirkt.py::test_w11_ha_zaehlersprung_wirkt",
    "drift_tag": "test_daten_checker_handgriff_wirkt.py::test_w11_drift_tag_wirkt",
    "datenquelle_aggregate_aeltere_quelle": "test_daten_checker_handgriff_wirkt.py::test_w11_aeltere_quelle_wirkt",
    "batterie_vorzeichen_tage": "test_daten_checker_handgriff_wirkt.py::test_w11_batterie_vorzeichen_tage_wirkt",
    "batterie_vorzeichen_tag": "test_daten_checker_handgriff_wirkt.py::test_w11_batterie_vorzeichen_tag_wirkt",
    "soc_nur_ein_speicher_tage": "test_daten_checker_handgriff_wirkt.py::test_w11_soc_nur_ein_speicher_wirkt",
    "tageswerte_fehlen_tage": "test_daten_checker_handgriff_wirkt.py::test_w11_tageswerte_fehlen_tage_wirkt",
    "tageswerte_fehlen_tag": "test_daten_checker_handgriff_wirkt.py::test_w11_tageswerte_fehlen_tag_wirkt",
    "emob_doppelzaehlung_tage": "test_daten_checker_handgriff_wirkt.py::test_w11_emob_doppelzaehlung_wirkt",
    "tage_vor_umbau_ohne_regelmarke": "test_daten_checker_handgriff_wirkt.py::test_w11_tage_vor_umbau_wirkt",
    "einspeisung_groesser_erzeugung_tage": "test_daten_checker_handgriff_wirkt.py::test_w11_einspeisung_ueber_erzeugung_wirkt",
    "counter_spike_tag": "test_daten_checker_handgriff_wirkt.py::test_w11_counter_spike_wirkt",
}


def _aktions_codes() -> set[str]:
    from backend.services.daten_checker.handgriffe import AKTION, HANDGRIFFE

    return {c for c, h in HANDGRIFFE.items() if h.klasse == AKTION}


def test_w11_je_aktions_code_ein_wirkungs_beleg():
    """E5.4: jeder Aktions-Code des Katalogs (18) hat einen Wirkungs-Test; jeder Beleg existiert."""
    codes = _aktions_codes()
    assert len(codes) == 18
    fehlt = sorted(codes - set(WIRKUNG_JE_CODE))
    assert not fehlt, f"Aktions-Code ohne Wirkungs-Test je Code (W-11, H-E5-3): {fehlt}"
    assert not set(WIRKUNG_JE_CODE) - codes, f"verwaiste Einträge: {sorted(set(WIRKUNG_JE_CODE) - codes)}"
    for code, beleg in WIRKUNG_JE_CODE.items():
        datei, funktion = beleg.split("::")
        assert funktion in _testfunktionen(datei), f"{code}: Beleg {beleg} fehlt"


def test_w11_je_code_hat_zaehne(monkeypatch):
    """Sprengsatz: ein Aktions-Code ohne Beleg ⇒ rot."""
    monkeypatch.delitem(WIRKUNG_JE_CODE, "vergleichspreis_fehlt")
    with pytest.raises(AssertionError, match="ohne Wirkungs-Test je Code"):
        test_w11_je_aktions_code_ein_wirkungs_beleg()


def _aktionen_der_erzeuger() -> set[str]:
    """Jede Operation, die ein Erzeuger als ``Aktion("<op>", …)`` setzt, und die Spiegel-Aktion (``aktion_spiegel_…``)."""
    ops: set[str] = set()
    for p in (BACKEND / "services" / "daten_checker").rglob("*.py"):
        baum = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(baum):
            if not isinstance(n, ast.Call):
                continue
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name == "Aktion" and n.args and isinstance(n.args[0], ast.Constant):
                ops.add(n.args[0].value)
            if name == "aktion_spiegel_abgleich_tag":
                ops.add(AKTION_SPIEGEL_ABGLEICH_TAG)
    return ops


def _testfunktionen(datei: str) -> set[str]:
    baum = ast.parse((TESTS / datei).read_text(encoding="utf-8"))
    return {n.name for n in baum.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_jede_aktion_hat_einen_wirkungs_beleg():
    ops = _aktionen_der_erzeuger()
    assert ops, "keine Aktion gefunden — AST-Suche kaputt?"
    fehlt = sorted(ops - set(WIRKUNG))
    assert not fehlt, f"Aktion ohne Wirkungs-Beleg (W-11, Halt H-10): {fehlt}"
    assert not set(WIRKUNG) - ops, f"verwaiste Einträge: {sorted(set(WIRKUNG) - ops)}"
    for op, belege in WIRKUNG.items():
        assert belege, op
        for _lage, beleg in belege:
            datei, funktion = beleg.split("::")
            assert funktion in _testfunktionen(datei), f"{op}: Beleg {beleg} fehlt"


def test_jede_aktion_ist_eine_operation_des_orchestrators():
    werte = {o.value for o in RepairOperationType}
    assert _aktionen_der_erzeuger() <= werte


def test_der_waechter_hat_zaehne(monkeypatch):
    """Sprengsatz: eine Operation ohne Beleg ⇒ rot."""
    monkeypatch.delitem(WIRKUNG, "wetter_backfill")
    with pytest.raises(AssertionError, match="ohne Wirkungs-Beleg"):
        test_jede_aktion_hat_einen_wirkungs_beleg()


# ── S2: Kanal-Lage-Weiche (Nr 63 «Einspeisung über Erzeugung»; Muster für alle Bereichs-Zeilen) ────────────────────

TAGE = [date(2026, 6, d) for d in (8, 9, 10)]


async def _weiche(monkeypatch, *, kanal: set, spiegel: int):
    from backend.services.daten_checker import DatenChecker

    async def _kanal(self, _anlage, tage):
        return {d: object() for d in tage if d in kanal}

    async def _spiegel(_db, _aid):
        return spiegel

    monkeypatch.setattr(DatenChecker, "_bilanz_kanal_tage", _kanal)
    monkeypatch.setattr("backend.services.kanal.konsistenz.spiegel_quellen_anzahl", _spiegel)

    class _A:
        id = 7

    return await DatenChecker(None)._weiche_bereich(_A(), TAGE)


async def test_s2_bestandstage_bekommen_tage_neu_aufbauen(monkeypatch):
    a = await _weiche(monkeypatch, kanal=set(), spiegel=3)
    assert (a.operation, a.params) == ("reaggregate_range", {"von": "2026-06-08", "bis": "2026-06-10"})


async def test_s2_bereich_nur_ueber_bestandstage(monkeypatch):
    a = await _weiche(monkeypatch, kanal={date(2026, 6, 10)}, spiegel=3)
    assert (a.operation, a.params) == ("reaggregate_range", {"von": "2026-06-08", "bis": "2026-06-09"})


async def test_s2_kanal_tag_mit_spiegel_bekommt_den_abgleich(monkeypatch):
    a = await _weiche(monkeypatch, kanal=set(TAGE), spiegel=3)
    assert (a.operation, a.params) == (AKTION_SPIEGEL_ABGLEICH_TAG, {"datum": "2026-06-10"})
    assert not a.operation.startswith("reaggregate")


async def test_s2_kanal_tag_ohne_spiegel_ohne_knopf(monkeypatch):
    assert await _weiche(monkeypatch, kanal=set(TAGE), spiegel=0) is None


# ── Monats-Operationen: der Befund verschwindet nach dem Lauf ─────────────────────────────────────────────────────

@pytest.fixture
def _leer():
    _reset_state_for_tests()


async def _ausfuehren(db, anlage_id: int, e) -> None:
    p = await plan(RepairOperationRequest(anlage_id=anlage_id, operation=RepairOperationType(befund_op(e)),
                                          params=befund_params(e)), db)
    assert "nichts_zu_tun" not in p.operation_preview, p.operation_preview
    await execute(p.plan_id, db)


async def test_temperatur_aus_messung_wirkt(db, _leer):
    from backend.tests.test_n426_temperatur_historie import _anlage, _befunde

    a = await _anlage(db, monate={1: None, 2: None}, messreihe={1: 2.0, 2: 3.5})
    (e,) = await _befunde(db, a.id)
    assert befund_op(e) == "temperatur_aus_messung"
    await _ausfuehren(db, a.id, e)
    assert [(x.schwere, x.code) for x in await _befunde(db, a.id)] == [("ok", "temperatur_ok")]


async def test_wert_entfernen_wirkt(db, _leer):
    from backend.tests.test_n393_wert_in_nicht_gefuehrtem_feld import _anlage_mit, _befunde

    a, klima = await _anlage_mit(db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
                                 monate={5: {"warmwasser_kwh": 10.0}, 6: {"warmwasser_kwh": 889.0}})
    (e,) = _befunde(db, klima)
    assert befund_op(e) == "feldwert_entfernen"
    await _ausfuehren(db, a.id, e)
    _, nachher = await _anlage_mit_neu_geladen(db, klima.id)
    assert _befunde(db, nachher) == []


async def _anlage_mit_neu_geladen(db, inv_id: int):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.models import Investition

    db.expire_all()
    inv = (await db.execute(select(Investition).options(selectinload(Investition.monatsdaten))
                            .where(Investition.id == inv_id))).scalar_one()
    return None, inv


# ── E5.4: je Aktions-Code ein Szenario (Achsen-Matrix, Bauplan §1) ───────────────────────────────────────────────────
#
# Datenstand ``kg.datenstand("achsen", <Form>, "HA")``: HA-Langzeitstatistik im echten Recorder-Schema, Spiegel daraus,
# Juni/Juli 2026, «heute» fest (``heute_fest``, Uhr der Kanal-Leser ``uhr``). **Bestandstag** = derselbe Stand ohne Spiegel
# (``_ohne_spiegel``: die Tage lesen Tages-/Stundenzeilen; ``REAGGREGATE_*`` schreibt sie aus der HA-Statistik neu).
# **Kanal-Tag mit Spiegel** = der Spiegel trägt, was HA (korrigiert) nicht mehr trägt. Je Probe: Defekt in eedcs Zeilen
# setzen → Befund mit diesem Code und Aktion → ``plan`` → ``execute`` mit den Parametern des Befunds → erneut prüfen.
# Umgebung, keine Attrappe der Operation: eine Leistungszuordnung am Netz (``ermittle_aggregations_quelle`` echt), die
# Leistungskurve der Matrix als Verlauf (``mx._kurve``), Börse und ``get_session`` auf die Wegwerf-Datenbank.

E54_TAG = date(2026, 6, 10)
E54_TAG2 = date(2026, 6, 11)


@asynccontextmanager
async def _e54_lage(fid: str, monkeypatch, *, spiegel: bool):
    from backend.tests import achsen_matrix as am
    from backend.tests import kanal_bilanz_gleichheit as kg
    from backend.tests import pv_achse_matrix as mx
    from backend.tests.test_n790_drift_handgriff import _ohne_spiegel, _sitzungen_von

    _reset_state_for_tests()
    async with kg.datenstand("achsen", fid, "HA") as ds:
        if not spiegel:
            await _ohne_spiegel(ds)
        form = kg._form("achsen", fid)
        a = await _e54_anlage(ds)
        a.sensor_mapping = {**a.sensor_mapping, "basis": {**(a.sensor_mapping.get("basis") or {}),
                                                          "live": {"netzbezug_w": "sensor.e54_netz_w"}}}
        await ds.db.commit()

        class _Verlauf:
            async def get_tagesverlauf(self, *_a, **_k):
                return mx._kurve(form.pvform)

        async def _ohne_boerse(*_a, **_k):
            return None

        monkeypatch.setattr("backend.core.database.get_session", _sitzungen_von(ds))
        monkeypatch.setattr("backend.services.strompreis_markt_service.fetch_marktpreise", _ohne_boerse)
        monkeypatch.setattr("backend.services.live_power_service.get_live_power_service", lambda: _Verlauf())
        with am.umgebung(form, ds.svc):
            yield ds


async def _e54_anlage(ds):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.models import Anlage

    ds.db.expire_all()
    return (await ds.db.execute(select(Anlage).options(selectinload(Anlage.investitionen))
                                .where(Anlage.id == ds.aid))).scalar_one()


async def _e54_pruefe(ds, pruefung: str, **kw) -> list:
    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import merken
    from backend.tests.test_s5_e2_checker_kanal_mengen import heute_fest

    merken.invalidiere(ds.aid)
    a = await _e54_anlage(ds)
    with heute_fest():
        return await getattr(DatenChecker(ds.db), pruefung)(a, **kw)


async def _e54_wirkung(ds, pruefung: str, code: str, op: str, params: dict, **kw) -> list[str]:
    """Befund ``code`` entsteht mit Aktion ``op``/``params``; die Aktion läuft über ``plan`` → ``execute``; zurück
    kommen die Codes des erneuten Prüflaufs."""
    vorher = await _e54_pruefe(ds, pruefung, **kw)
    (e,) = [x for x in vorher if x.code == code]
    assert (befund_op(e), befund_params(e)) == (op, params), (befund_op(e), befund_params(e))
    p = await plan(RepairOperationRequest(anlage_id=ds.aid, operation=RepairOperationType(befund_op(e)),
                                          params=befund_params(e)), ds.db)
    assert "nichts_zu_tun" not in p.operation_preview, p.operation_preview
    r = await execute(p.plan_id, ds.db)
    assert r.operation_summary.get("fehlgeschlagen", 0) == 0, r.operation_summary
    return [x.code for x in await _e54_pruefe(ds, pruefung, **kw)]


async def _e54_tz(ds, datum: date):
    from sqlalchemy import select

    from backend.models.tages_energie_profil import TagesZusammenfassung

    return (await ds.db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == datum))).scalar_one()


async def _e54_tep_setzen(ds, datum: date, stunde=None, **werte) -> None:
    from sqlalchemy import update

    from backend.models.tages_energie_profil import TagesEnergieProfil as T

    bed = [T.anlage_id == ds.aid, T.datum == datum] + ([T.stunde == stunde] if stunde is not None else [])
    await ds.db.execute(update(T).where(*bed).values(**werte))
    await ds.db.commit()


def _e54_spiegel_ts(datum: date, stunde: int) -> int:
    from datetime import datetime

    return int(datetime(datum.year, datum.month, datum.day, stunde).timestamp())


# Kanal-Tag mit Spiegel: «Aus Home Assistant neu übernehmen» (SPIEGEL_ABGLEICH_TAG) ────────────────────────────────


async def test_w11_ha_zaehler_rueckgang_wirkt(uhr, monkeypatch):
    """Der Spiegel trägt ab 10.06. 12:00 eine um 540 kWh gefallene Summe, HA (korrigiert) nicht ⇒ Rückgang; der Abgleich
    übernimmt HAs Statistik ⇒ kein Befund."""
    from backend.tests.test_n790_drift_handgriff import _spiegel_veraltet

    async with _e54_lage("M01", monkeypatch, spiegel=True) as ds:
        await _spiegel_veraltet(ds, "basis:netzbezug", _e54_spiegel_ts(E54_TAG, 12), -540.0)
        nachher = await _e54_wirkung(ds, "_check_ha_rueckgang", "ha_zaehler_rueckgang", AKTION_SPIEGEL_ABGLEICH_TAG,
                                     {"datum": E54_TAG.isoformat()})
    assert nachher == []


async def test_w11_ha_zaehlersprung_wirkt(uhr, monkeypatch):
    """Der Spiegel trägt das N-586-Muster (Stand 12:00 auf 0, 13:00 zurück, ``sum`` + alter Stand), HA nach «Wert
    anpassen» nicht ⇒ Zählersprung; der Abgleich übernimmt HAs Statistik ⇒ kein Befund."""
    from sqlalchemy import select, update

    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalStatistik
    from backend.tests import pv_achse_matrix as mx
    from backend.tests.test_n790_drift_handgriff import _spiegel_veraltet

    async with _e54_lage("M01", monkeypatch, spiegel=True) as ds:
        kid = (await ds.db.execute(select(Kanal.id).where(Kanal.anlage_id == ds.aid,
                                                          Kanal.key == "basis:netzbezug"))).scalar_one()
        zeile = [KanalStatistik.kanal_id == kid, KanalStatistik.familie == FAMILIE_SPIEGEL,
                 KanalStatistik.start_ts == _e54_spiegel_ts(E54_TAG, 12)]
        stand = (await ds.db.execute(select(KanalStatistik.state).where(*zeile))).scalar_one()
        await ds.db.execute(update(KanalStatistik).where(*zeile).values(state=0.0))
        await ds.db.commit()
        await _spiegel_veraltet(ds, "basis:netzbezug", _e54_spiegel_ts(E54_TAG, 13), stand)
        nachher = await _e54_wirkung(ds, "_check_ha_zaehlersprung", "ha_zaehlersprung", AKTION_SPIEGEL_ABGLEICH_TAG,
                                     {"datum": E54_TAG.isoformat()}, jetzt=mx.JETZT)
    assert nachher == []


async def test_w11_drift_tag_wirkt(uhr, monkeypatch):
    """PV-Tageszeile der Drift (erste Achse): der PV-Spiegel trägt ab 10.06. 12:00 +10 kWh, HA nicht ⇒ «PV … → HA …»;
    der Abgleich übernimmt HAs Statistik ⇒ «Keine signifikanten Abweichungen»."""
    from backend.tests.test_n790_drift_handgriff import _spiegel_veraltet

    async with _e54_lage("M01", monkeypatch, spiegel=True) as ds:
        await _spiegel_veraltet(ds, "inv:1:pv_erzeugung_kwh", _e54_spiegel_ts(E54_TAG, 12), 10.0)
        nachher = await _e54_wirkung(ds, "_check_datenquelle_drift", "drift_tag", AKTION_SPIEGEL_ABGLEICH_TAG,
                                     {"datum": E54_TAG.isoformat()})
    assert nachher == ["drift_ok"]


# Bestandstag: «Tag(e) neu aufbauen» (REAGGREGATE_DAY / REAGGREGATE_RANGE) ─────────────────────────────────────────


async def test_w11_aeltere_quelle_wirkt(uhr, monkeypatch):
    """Die jüngste Tageszeile (03.07.) trägt eine ältere Herkunft ⇒ «Aggregate aus älterer Quelle» mit dem jüngsten
    31-Tage-Fenster; neu aufgebaut trägt sie die HA-Statistik ⇒ OK-Zeile."""
    async with _e54_lage("M01", monkeypatch, spiegel=False) as ds:
        tz = await _e54_tz(ds, date(2026, 7, 3))
        tz.source_provenance = {k: {**v, "source": "auto:monatsabschluss"} for k, v in tz.source_provenance.items()}
        await ds.db.commit()
        nachher = await _e54_wirkung(ds, "_check_datenquelle_status", "datenquelle_aggregate_aeltere_quelle",
                                     "reaggregate_range", {"von": "2026-06-03", "bis": "2026-07-03"})
    assert nachher == ["datenquelle_ha_lts_ok"]


async def _e54_batterie_vertauschen(ds, tage) -> None:
    for d in tage:
        tz = await _e54_tz(ds, d)
        tz.komponenten_kwh = {k: (-v if k.startswith("batterie_") else v) for k, v in tz.komponenten_kwh.items()}
    await ds.db.commit()


async def test_w11_batterie_vorzeichen_tage_wirkt(uhr, monkeypatch):
    async with _e54_lage("M02", monkeypatch, spiegel=False) as ds:
        await _e54_batterie_vertauschen(ds, (E54_TAG, E54_TAG2))
        nachher = await _e54_wirkung(ds, "_check_batterie_vorzeichen_historie", "batterie_vorzeichen_tage",
                                     "reaggregate_range", {"von": E54_TAG.isoformat(), "bis": E54_TAG2.isoformat()})
    assert nachher == ["batterie_vorzeichen_ok"]


async def test_w11_batterie_vorzeichen_tag_wirkt(uhr, monkeypatch):
    async with _e54_lage("M02", monkeypatch, spiegel=False) as ds:
        await _e54_batterie_vertauschen(ds, (E54_TAG,))
        nachher = await _e54_wirkung(ds, "_check_batterie_vorzeichen_historie", "batterie_vorzeichen_tag",
                                     "reaggregate_day", {"datum": E54_TAG.isoformat()})
    assert nachher == ["batterie_vorzeichen_ok"]


async def test_w11_soc_nur_ein_speicher_wirkt(uhr, monkeypatch):
    """Zwei Speicher mit eigenem Ladestands-Sensor (Mittelwerte in der HA-Statistik); die Stunden des 10.06. tragen nur
    den Anlagen-Ladestand (alte Signatur) ⇒ Befund; neu aufgebaut tragen sie die Aufschlüsselung ⇒ OK-Zeile."""
    import time as _zeit
    from datetime import datetime, timedelta

    from sqlalchemy import select, text

    from backend.models.tages_energie_profil import TagesEnergieProfil as T
    from backend.tests import ha_lts_helfer as hh

    async with _e54_lage("M04", monkeypatch, spiegel=False) as ds:
        a = await _e54_anlage(ds)
        invs = dict(a.sensor_mapping.get("investitionen") or {})
        speicher = sorted(i.id for i in a.investitionen if i.typ == "speicher")
        for soc, sid in zip((30.0, 70.0), speicher):
            eintrag = dict(invs.get(str(sid)) or {})
            eintrag["live"] = {**(eintrag.get("live") or {}), "soc": f"sensor.e54_soc_{sid}"}
            invs[str(sid)] = eintrag
            mid = hh.sensor(ds.svc, f"sensor.e54_soc_{sid}", "%", has_sum=False)
            t = datetime(2026, 6, 9)
            with ds.svc._engine.begin() as conn:
                while t < datetime(2026, 6, 12):
                    conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, mean, min, max) "
                                      "VALUES (:m, :t, :w, :w, :w)"), {"m": mid, "t": _zeit.mktime(t.timetuple()), "w": soc})
                    t += timedelta(hours=1)
        a.sensor_mapping = {**a.sensor_mapping, "investitionen": invs}
        await ds.db.commit()
        await _e54_tep_setzen(ds, E54_TAG, soc_prozent=50.0, soc_je_speicher=None)
        nachher = await _e54_wirkung(ds, "_check_soc_nur_ein_speicher", "soc_nur_ein_speicher_tage",
                                     "reaggregate_range", {"von": E54_TAG.isoformat(), "bis": E54_TAG.isoformat()})
        je_speicher = (await ds.db.execute(select(T.soc_je_speicher).where(
            T.anlage_id == ds.aid, T.datum == E54_TAG, T.stunde == 12))).scalar_one()
    assert nachher == ["soc_ok"]
    assert je_speicher == {str(speicher[0]): 30.0, str(speicher[1]): 70.0}


async def _e54_tage_loeschen(ds, tage) -> None:
    from sqlalchemy import delete, update

    from backend.models import Anlage
    from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

    # Inbetriebnahme 01.06.: davor hat eedc keinen Anspruch auf Tageswerte (der Matrix-Stand beginnt 31.05. 18:00).
    await ds.db.execute(update(Anlage).where(Anlage.id == ds.aid).values(installationsdatum=date(2026, 6, 1)))
    for m in (TagesEnergieProfil, TagesZusammenfassung):
        await ds.db.execute(delete(m).where(m.anlage_id == ds.aid, m.datum.in_(tuple(tage))))
    await ds.db.commit()


async def test_w11_tageswerte_fehlen_tage_wirkt(uhr, monkeypatch):
    async with _e54_lage("M01", monkeypatch, spiegel=False) as ds:
        await _e54_tage_loeschen(ds, (E54_TAG, E54_TAG2))
        nachher = await _e54_wirkung(ds, "_check_leere_tage_trotz_zaehler", "tageswerte_fehlen_tage",
                                     "reaggregate_range", {"von": E54_TAG.isoformat(), "bis": E54_TAG2.isoformat()})
    assert nachher == ["tageswerte_ok"]


async def test_w11_tageswerte_fehlen_tag_wirkt(uhr, monkeypatch):
    async with _e54_lage("M01", monkeypatch, spiegel=False) as ds:
        await _e54_tage_loeschen(ds, (E54_TAG,))
        nachher = await _e54_wirkung(ds, "_check_leere_tage_trotz_zaehler", "tageswerte_fehlen_tag",
                                     "reaggregate_day", {"datum": E54_TAG.isoformat()})
    assert nachher == ["tageswerte_ok"]


async def test_w11_emob_doppelzaehlung_wirkt(uhr, monkeypatch):
    """Wallbox + E-Auto (M08): die Tageszeile des 10.06. trägt die Ladung auch am E-Auto (vor F-14 geschrieben) ⇒
    Befund; neu aufgebaut gilt die Wallbox-Regel ⇒ OK-Zeile."""
    async with _e54_lage("M08", monkeypatch, spiegel=False) as ds:
        a = await _e54_anlage(ds)
        (eauto,) = [i.id for i in a.investitionen if i.typ == "e-auto"]
        tz = await _e54_tz(ds, E54_TAG)
        (wb,) = [v for k, v in tz.komponenten_kwh.items() if k.startswith("wallbox_")]
        tz.komponenten_kwh = {**tz.komponenten_kwh, f"eauto_{eauto}": wb}
        await ds.db.commit()
        nachher = await _e54_wirkung(ds, "_check_emob_doppelzaehlung_tage", "emob_doppelzaehlung_tage",
                                     "reaggregate_range", {"von": E54_TAG.isoformat(), "bis": E54_TAG.isoformat()})
    assert nachher == ["emob_doppelzaehlung_ok"]


async def test_w11_tage_vor_umbau_wirkt(uhr, monkeypatch):
    """Der 10.06. ohne Regelmarke (vor «Zählerlücken wie HA» gerechnet) ⇒ Befund; neu aufgebaut trägt er sie ⇒ still."""
    async with _e54_lage("M01", monkeypatch, spiegel=False) as ds:
        tz = await _e54_tz(ds, E54_TAG)
        assert tz.verworfen is not None
        tz.verworfen = None
        await ds.db.commit()
        nachher = await _e54_wirkung(ds, "_check_bestandstage_ohne_regelmarke", "tage_vor_umbau_ohne_regelmarke",
                                     "reaggregate_range", {"von": E54_TAG.isoformat(), "bis": E54_TAG.isoformat()})
    assert nachher == []


async def test_w11_einspeisung_ueber_erzeugung_wirkt(uhr, monkeypatch):
    """Die Stunde 03:00 des 10.06. trägt 40 kWh Einspeisung ohne Erzeugung ⇒ Befund; neu aufgebaut aus der HA-Statistik
    ⇒ still."""
    async with _e54_lage("M01", monkeypatch, spiegel=False) as ds:
        await _e54_tep_setzen(ds, E54_TAG, 3, einspeisung_kw=40.0)
        nachher = await _e54_wirkung(ds, "_check_einspeisung_ueber_erzeugung", "einspeisung_groesser_erzeugung_tage",
                                     "reaggregate_range", {"von": E54_TAG.isoformat(), "bis": E54_TAG.isoformat()})
    assert nachher == []


async def test_w11_counter_spike_wirkt(uhr, monkeypatch):
    """Die Stunde 12:00 des 10.06. trägt 400 kW Einspeisung (Counter-Spike) ⇒ Befund; neu aufgebaut ⇒ OK-Zeile."""
    async with _e54_lage("M01", monkeypatch, spiegel=False) as ds:
        await _e54_tep_setzen(ds, E54_TAG, 12, einspeisung_kw=400.0)
        nachher = await _e54_wirkung(ds, "_check_energieprofil_plausibilitaet", "counter_spike_tag",
                                     "reaggregate_day", {"datum": E54_TAG.isoformat()})
    assert nachher == ["counter_spikes_ok"]
