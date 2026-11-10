"""N-790 (Melder ottokar, simon42 PN T95600): ein Drift-Befund trägt einen Handgriff, der ihn beheben kann.

**Der Fall.** Daten-Checker «Wärmepumpe: 2026-11-02: 123.909,6 → 13,7 kWh» — der Zähler war in Home Assistant längst
korrigiert, «Tag reparieren» mehrfach gedrückt, der Wert blieb. Grund: an einem Kanal-Tag liest der Tag seine Mengen
aus dem HA-Spiegel (``kanal_stunden.komponenten_der_tage``); ``aggregate_day`` schreibt dort keine Mengen
(``mengen_weiche``), und der Spiegel speichert HAs ``sum``/``state`` wörtlich — eine Korrektur in HA erreicht ihn nur
über den Abgleich (``kanal/konsistenz.konsistenz_anlage``). Die Neu-Aggregation allein konnte die Drift nie beheben.

**Der Handgriff.** ``POST /api/energie-profil/{anlage_id}/spiegel-abgleich-tag`` verkettet den Abgleich (dieselbe
Funktion wie die Werkbank-Operation «HA-Spiegel jetzt abgleichen») mit der Neu-Aggregation des Tages. Drift-,
Zählersprung- und Rückgang-Befunde tragen ihn bei einer Anlage mit Spiegel als Aktion ``spiegel_abgleich_tag``
(«Aus Home Assistant neu übernehmen»); ohne Spiegel bleibt «Tag reparieren».

Geprüft: (a) Drift-Zeilen beider Achsen mit/ohne Spiegel · (b) Sprung- und Rückgang-Befund · (c) die Kette: Spiegel
mit veralteter Zeile, HA korrigiert ⇒ Befund mit der neuen Aktion, Route gleicht ab und baut den Tag, erneuter
Drift-Check ohne Befund · (d) ohne Spiegel nur die Neu-Aggregation · (e) HA unerreichbar ⇒ 503, keine Neu-Aggregation
· der Satz ``meldung`` in Anwender-Sprache.

Datenstand für (a)/(c): die Achsen-Matrix wie ``test_s5_e2_checker_kanal_mengen.py`` (Spiegel aus der
Recorder-Statistik, Juni/Juli 2026 Kanal-Tage, «heute» fest). Schwesterdateien: ``test_kanal_abgleich_route.py``,
``test_kanal_konsistenz.py``, ``test_n586_checker_ha_zaehlersprung.py``, ``test_n639_checker_ha_rueckgang.py``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models import Anlage
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests.test_s5_e2_checker_kanal_mengen import (  # noqa: F401 — Fixture `uhr`
    TAG,
    _anlage,
    _ha,
    _komp,
    _tz_setzen,
    heute_fest,
    uhr,
)

AKTION = "spiegel_abgleich_tag"
LABEL = "Aus Home Assistant neu übernehmen"
_KAT = CheckKategorie.DATENQUELLE_DRIFT.value


def _ts(d: date, stunde: int) -> int:
    return int(datetime(d.year, d.month, d.day, stunde).timestamp())


async def _spiegel_veraltet(ds, key: str, ab_ts: int, plus: float) -> None:
    """Der Spiegel trägt ab ``ab_ts`` eine Summe, die HA inzwischen korrigiert hat (HA unverändert = korrigiert)."""
    kid = (await ds.db.execute(select(Kanal.id).where(Kanal.anlage_id == ds.aid, Kanal.key == key))).scalar_one()
    await ds.db.execute(update(KanalStatistik).where(
        KanalStatistik.kanal_id == kid, KanalStatistik.familie == FAMILIE_SPIEGEL, KanalStatistik.start_ts >= ab_ts,
    ).values(sum=KanalStatistik.sum + plus))
    await ds.db.commit()
    from backend.services.kanal import merken

    merken.invalidiere(ds.aid)   # der Schreiber im Produkt tut es selbst (``nachfuellen``/``schreiber``)


async def _ohne_spiegel(ds) -> None:
    """Eine Anlage ohne HA-Spiegel: keine Kanalzeilen, keine Spiegel-Quellen; die Tage neu aggregiert (Bestandstage)."""
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
    await ds.db.execute(delete(KanalQuelle).where(KanalQuelle.kanal_id.in_(ids)))
    await ds.db.commit()
    await kg.neu_aggregieren(ds)


def _sitzungen_von(ds):
    macher = async_sessionmaker(ds.db.bind, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    return sitzungen


async def _drift(ds) -> list:
    a = await _anlage(ds)
    with heute_fest():
        return await DatenChecker(ds.db)._check_datenquelle_drift(a)


# ── (a) Drift-Zeilen beider Achsen ───────────────────────────────────────────


async def test_a_pv_achse_mit_spiegel_traegt_den_handgriff(uhr, monkeypatch):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        ha = await _komp(ds)
        _ha(monkeypatch, ha)
        await _spiegel_veraltet(ds, "inv:1:pv_erzeugung_kwh", _ts(TAG, 12), 10.0)
        erg = await _drift(ds)
    (e,) = [e for e in erg if e.meldung.startswith(TAG.isoformat())]
    assert e.action_kind == AKTION
    assert e.action_label == LABEL
    assert e.action_params == {"anlage_id": ds.aid, "datum": TAG.isoformat()}
    assert "„Aus Home Assistant neu übernehmen“" in e.details
    assert "Hast du in Home Assistant korrigiert, ist das der Weg." in e.details
    assert "Tag reparieren" not in e.details


async def test_a_komponenten_achse_mit_spiegel_traegt_den_handgriff(uhr, monkeypatch):
    """Der Fall des Melders: die Wärmepumpe (Form M05) — der Spiegel ihres Stromzählers trägt einen Sprung, HA nicht."""
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        ha = await _komp(ds)
        _ha(monkeypatch, ha)
        await _spiegel_veraltet(ds, "inv:3:stromverbrauch_kwh", _ts(TAG, 12), 10.0)
        erg = await _drift(ds)
    (e,) = [e for e in erg if "weichen von HA-Statistics ab" in e.meldung]
    assert e.investition_id == 3
    assert e.action_kind == AKTION
    assert e.action_label == LABEL
    assert e.action_params == {"anlage_id": ds.aid, "datum": TAG.isoformat()}
    assert "„Aus Home Assistant neu übernehmen“" in e.details
    assert "Tag reparieren" not in e.details


async def test_a_ohne_spiegel_bleibt_tag_reparieren(uhr, monkeypatch):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _ohne_spiegel(ds)
        komp = await _komp(ds)
        _ha(monkeypatch, komp)
        await _tz_setzen(ds, [TAG], komponenten_kwh={k: v / 2 for k, v in komp[TAG].items()})
        erg = await _drift(ds)
    zeilen = [e for e in erg if e.action_kind]
    assert zeilen, [e.meldung for e in erg]
    assert {e.action_kind for e in zeilen} == {"reaggregate_day"}
    assert {e.action_label for e in zeilen} == {"Tag reparieren"}
    assert any("„Tag reparieren“" in (e.details or "") for e in zeilen)


# ── (b) Zählersprung und Rückgang ────────────────────────────────────────────


async def test_b_zaehlersprung_traegt_den_handgriff(db):
    from backend.services.daten_checker.datenquelle.ha_sprung import HaZaehlersprungChecks
    from backend.tests.test_n586_checker_ha_zaehlersprung import JETZT, _reihe

    a = Anlage(anlagenname="N-790 Sprung", leistung_kwp=8.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key="basis:pv_gesamt", einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    z = _reihe(48, reset_bei=20, rueckkehr_bei=23)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=z[0][0] - 3600, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.pv_gesamt", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=su, familie=FAMILIE_SPIEGEL)
                for ts, st, su in z])
    await db.commit()

    class _Pruefer(HaZaehlersprungChecks):
        def __init__(self, db):
            self.db = db

    (e,) = await _Pruefer(db)._check_ha_zaehlersprung(a, jetzt=JETZT)
    rueckkehr = datetime.fromtimestamp(z[23][0]).date()
    assert e.action_kind == AKTION
    assert e.action_label == LABEL
    assert e.action_params == {"anlage_id": a.id, "datum": rueckkehr.isoformat()}
    assert "„Aus Home Assistant neu übernehmen“" in e.details
    assert "Reparatur-Werkbank" not in e.details
    assert "Wert anpassen" in e.details and "Monatsabschluss neu" in e.details


async def test_b_rueckgang_traegt_den_handgriff(db):
    from backend.tests.test_n639_checker_ha_rueckgang import RUECKGANG_STUNDE, _Pruefer, _anlage as _a, _kanal
    from backend.tests.test_n639_checker_ha_rueckgang import _reihe as _r

    a = await _a(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _r(rueckgaenge={RUECKGANG_STUNDE: 540.0}))
    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert e.action_kind == AKTION
    assert e.action_label == LABEL
    assert e.action_params == {"anlage_id": a.id, "datum": RUECKGANG_STUNDE.date().isoformat()}
    assert "„Aus Home Assistant neu übernehmen“" in e.details
    assert "nächtlichen Abgleich" in e.details and "Monatsabschluss neu" in e.details


# ── (c) die Kette ───────────────────────────────────────────────────────────


async def test_n1_tag_reparieren_allein_behebt_die_drift_nicht(uhr, monkeypatch):
    """Der Befund des Melders, gemessen: an einem Kanal-Tag liest der Tag den Spiegel — die Neu-Aggregation des Tages
    («Tag reparieren», ``reaggregate-tag``) lässt die Drift stehen."""
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        form = kg._form("achsen", "M05")
        await _spiegel_veraltet(ds, "inv:3:stromverbrauch_kwh", _ts(TAG, 12), 10.0)
        with am.umgebung(form, ds.svc):
            vorher = [e.meldung for e in await _drift(ds) if "weichen von HA-Statistics ab" in e.meldung]
            # «Tag reparieren» = ``aggregate_day`` des Tages wie im Produkt (mit Mengen-Weiche); die Matrix reicht die
            # Leistungskurve selbst herein (die Route fände für die Matrix-Form keine).
            await kg.neu_aggregieren(ds, tage=[TAG])
            nachher = [e.meldung for e in await _drift(ds) if "weichen von HA-Statistics ab" in e.meldung]
    assert len(vorher) == 1 and "2026-06-10: 17,2 → 7,2 kWh" in vorher[0], vorher
    assert nachher == vorher


async def test_c_kette_spiegel_veraltet_route_gleicht_ab_und_der_befund_verschwindet(uhr, monkeypatch):
    """Spiegel mit veralteter Zeile, HA korrigiert ⇒ Befund mit der neuen Aktion; die Route übernimmt HAs Statistik
    und baut den Tag; der erneute Drift-Check (echter LTS-Leser gegen dieselbe Recorder-Statistik) ist still."""
    from backend.api.routes.energie_profil.repair import SpiegelAbgleichTagRequest, spiegel_abgleich_tag
    from backend.models.activity_log import ActivityLog

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        form = kg._form("achsen", "M05")
        ab = _ts(TAG, 12)
        await _spiegel_veraltet(ds, "inv:3:stromverbrauch_kwh", ab, 10.0)
        monkeypatch.setattr("backend.core.database.get_session", _sitzungen_von(ds))

        async def _ohne_boerse(*_a, **_k):
            return None              # der Tag-Lauf fragt die Börse (Preis-Rang); kein Netz in Proben

        monkeypatch.setattr("backend.services.strompreis_markt_service.fetch_marktpreise", _ohne_boerse)
        with am.umgebung(form, ds.svc):
            vorher = await _drift(ds)
            (e,) = [e for e in vorher if "weichen von HA-Statistics ab" in e.meldung]
            assert e.action_kind == AKTION and e.action_params["datum"] == TAG.isoformat()

            antwort = await spiegel_abgleich_tag(
                ds.aid, SpiegelAbgleichTagRequest(datum=e.action_params["datum"]), db=ds.db)
            nachher = await _drift(ds)
        eintraege = (await ds.db.execute(select(ActivityLog).where(
            ActivityLog.anlage_id == ds.aid, ActivityLog.kategorie == "ha_statistics"))).scalars().all()

    assert antwort["abgleich"]["hat_spiegel"] is True
    assert [(k["key"], k["ab_ts"]) for k in antwort["abgleich"]["korrigiert"]] == [("inv:3:stromverbrauch_kwh", ab)]
    assert antwort["reaggregation"]["datum"] == TAG.isoformat()
    # Die Matrix-Form hat keinen Leistungssensor: die Neu-Aggregation scheitert wie «Tag reparieren» heute — der Abgleich
    # bleibt, die Antwort sagt es, statt mit 500 zu enden.
    assert antwort["reaggregation"]["status"] == "fehler"
    assert antwort["datum"] == TAG.isoformat()
    assert antwort["meldung"].startswith("Statistik aus Home Assistant neu übernommen, 1 Kanal ab ")
    assert f"den Tag {TAG.strftime('%d.%m.%Y')} konnte eedc nicht neu aufbauen" in antwort["meldung"]
    assert [x.schwere for x in nachher] == ["ok"], [x.meldung for x in nachher]
    assert len(eintraege) == 1 and eintraege[0].erfolg is False
    assert eintraege[0].details == antwort["meldung"]


async def test_c_kette_mit_gelungener_neu_aggregation(uhr, monkeypatch):
    """Dieselbe Kette, die Neu-Aggregation gelingt (``aggregate_day`` des Tages wie im Produkt, mit der Leistungskurve der
    Matrix statt der Route): Satz «Tag … neu aufgebaut», Protokoll erfolgreich, kein Befund mehr."""
    from backend.api.routes.energie_profil import repair

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        form = kg._form("achsen", "M05")
        await _spiegel_veraltet(ds, "inv:3:stromverbrauch_kwh", _ts(TAG, 12), 10.0)
        monkeypatch.setattr("backend.core.database.get_session", _sitzungen_von(ds))
        gerufen: list = []

        async def _tag(anlage_id, datum, mit_resnap=True, db=None):
            gerufen.append(datum)
            await kg.neu_aggregieren(ds, tage=[datum])
            return {"status": "ok", "datum": datum.isoformat()}

        monkeypatch.setattr(repair, "reaggregate_tag", _tag)
        with am.umgebung(form, ds.svc):
            antwort = await repair.spiegel_abgleich_tag(
                ds.aid, repair.SpiegelAbgleichTagRequest(datum=TAG.isoformat()), db=ds.db)
            nachher = await _drift(ds)
    assert gerufen == [TAG]
    assert antwort["reaggregation"]["status"] == "ok"
    assert antwort["meldung"].startswith("Statistik aus Home Assistant neu übernommen, 1 Kanal ab 10.06. 12:00 korrigiert")
    assert antwort["meldung"].endswith(f"Tag {TAG.strftime('%d.%m.%Y')} neu aufgebaut.")
    assert [x.schwere for x in nachher] == ["ok"], [x.meldung for x in nachher]


# ── (d) ohne Spiegel, (e) HA unerreichbar ────────────────────────────────────


async def test_d_ohne_spiegel_nur_die_neu_aggregation(db, monkeypatch):
    from backend.api.routes.energie_profil import repair

    anlage = Anlage(anlagenname="Standalone", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()

    async def _nie(*_a, **_k):
        raise AssertionError("ohne Spiegel darf der Abgleich nicht starten")

    gerufen: list = []

    async def _tag(anlage_id, datum, mit_resnap=True, db=None):
        gerufen.append((anlage_id, datum, mit_resnap))
        return {"status": "ok", "datum": datum.isoformat()}

    monkeypatch.setattr("backend.services.kanal.konsistenz.konsistenz_anlage", _nie)
    monkeypatch.setattr(repair, "reaggregate_tag", _tag)
    antwort = await repair.spiegel_abgleich_tag(
        anlage.id, repair.SpiegelAbgleichTagRequest(datum="2026-11-02"), db=db)
    assert antwort["abgleich"]["hat_spiegel"] is False
    assert gerufen == [(anlage.id, date(2026, 11, 2), True)]
    assert antwort["reaggregation"]["datum"] == "2026-11-02"
    assert "keine Statistik aus Home Assistant" in antwort["meldung"]
    assert "Tag 02.11.2026 neu aufgebaut" in antwort["meldung"]


async def test_e_ha_nicht_erreichbar_ist_503_ohne_neu_aggregation(db, monkeypatch):
    from backend.api.routes.energie_profil import repair
    from backend.services.kanal.konsistenz import KonsistenzErgebnis

    anlage = Anlage(anlagenname="Haus", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    kanal = Kanal(anlage_id=anlage.id, key="basis:netzbezug", art=ART_SUM, einheit="kWh")
    db.add(kanal)
    await db.flush()
    db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=0, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz"))
    await db.flush()

    async def _lauf(_sitzungen, anlage_id, **_k):
        erg = KonsistenzErgebnis(anlage_id)
        erg.zaehle("ha_nicht_erreichbar")
        return erg

    async def _nie(*_a, **_k):
        raise AssertionError("ohne Abgleich keine Neu-Aggregation")

    monkeypatch.setattr("backend.services.kanal.konsistenz.konsistenz_anlage", _lauf)
    monkeypatch.setattr(repair, "reaggregate_tag", _nie)
    with pytest.raises(HTTPException) as e:
        await repair.spiegel_abgleich_tag(anlage.id, repair.SpiegelAbgleichTagRequest(datum="2026-11-02"), db=db)
    assert e.value.status_code == 503


async def test_unbekannte_anlage_ist_404(db):
    from backend.api.routes.energie_profil import repair

    with pytest.raises(HTTPException) as e:
        await repair.spiegel_abgleich_tag(987654, repair.SpiegelAbgleichTagRequest(datum="2026-11-02"), db=db)
    assert e.value.status_code == 404


# ── der Satz ────────────────────────────────────────────────────────────────


def _abgleich(**k) -> dict:
    basis = {"hat_spiegel": True, "korrigiert": [], "gekuerzt": [], "fehler": 0}
    basis.update(k)
    return basis


@pytest.mark.parametrize("abgleich, erwartet", [
    (_abgleich(korrigiert=[{"key": "x", "ab_ts": _ts(date(2026, 11, 2), 7), "zeilen": 3}]),
     "Statistik aus Home Assistant neu übernommen, 1 Kanal ab 02.11. 07:00 korrigiert; Tag 02.11.2026 neu aufgebaut."),
    (_abgleich(korrigiert=[{"key": "x", "ab_ts": _ts(date(2026, 11, 3), 9), "zeilen": 3},
                           {"key": "y", "ab_ts": _ts(date(2026, 11, 2), 7), "zeilen": 1}]),
     "Statistik aus Home Assistant neu übernommen, 2 Kanäle ab 02.11. 07:00 korrigiert; Tag 02.11.2026 neu aufgebaut."),
    (_abgleich(),
     "Statistik aus Home Assistant geprüft — nichts zu korrigieren, Tag 02.11.2026 neu aufgebaut."),
    (_abgleich(gekuerzt=[{"key": "x", "ha_erste_ts": 0, "behalten": 5}]),
     "Statistik aus Home Assistant geprüft — nichts zu korrigieren, Tag 02.11.2026 neu aufgebaut. "
     "Home Assistant hat für 1 Kanal keinen Anfang mehr — ältere Werte bleiben."),
    (_abgleich(fehler=2),
     "Statistik aus Home Assistant geprüft — nichts zu korrigieren, Tag 02.11.2026 neu aufgebaut. "
     "2 Kanäle konnten nicht geprüft werden (Home Assistant unterwegs nicht erreichbar?) — dort wurde nichts "
     "geändert."),
    (_abgleich(hat_spiegel=False),
     "Für diese Anlage übernimmt eedc keine Statistik aus Home Assistant — Tag 02.11.2026 neu aufgebaut."),
])
def test_meldung_in_anwender_sprache(abgleich, erwartet):
    from backend.api.routes.energie_profil.repair import _abgleich_tag_meldung

    assert _abgleich_tag_meldung(abgleich, date(2026, 11, 2)) == erwartet
