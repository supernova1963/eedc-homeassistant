"""Knopf „HA-Spiegel jetzt abgleichen" (MartyBr, simon42 #429) — die Route ruft den Lauf des Nachtjobs.

Nach einer Korrektur in Home Assistant (Entwicklerwerkzeuge → Statistik → „Wert anpassen") zeigten die
Tages-Kennzahlen bis zum nächsten Konsistenzlauf (02:45) den alten Spiegel. Die Route
``POST /api/energie-profil/{anlage_id}/kanal-abgleich`` ruft dieselbe Funktion wie der Nachtjob
(``kanal/konsistenz.konsistenz_anlage``, über ``konsistenz_alle`` je Anlage), mit ``get_session`` als Sitzungsquelle.

Geprüft: (1) echter Lauf gegen eine verschobene HA-Summe ⇒ Antwort nennt Kanal und erste abweichende Stunde, das
Aktivitätsprotokoll trägt den Lauf in der Sitzung der Route (N-532); ein zweiter Lauf findet nichts mehr.
(2) ohne Spiegel kein HA-Aufruf, ``hat_spiegel: false``. (3) HA nicht erreichbar ⇒ 503. (4) unbekannte Anlage ⇒ 404.

Fixtures wie ``test_kanal_konsistenz.py`` (aus ``test_kanal_nachfuellen.py``).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.api.routes.energie_profil.repair import kanal_abgleich
from backend.models import Anlage
from backend.models.activity_log import ActivityLog
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle
from backend.services.kanal.konsistenz import KonsistenzErgebnis
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.tests.test_kanal_konsistenz import _EINSP_MID, _verschiebe
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    JETZT,
    ZEIT,
    _ts,
    datei,
    ha,
)


@pytest.fixture
def _lauf_auf(monkeypatch):
    """Route auf die Test-Datei-DB und den Test-HA-Dienst lenken (dieselben Nähte wie der Nachtjob)."""
    def setze(sitzungen, svc):
        monkeypatch.setattr("backend.core.database.get_session", sitzungen)
        monkeypatch.setattr(
            "backend.services.ha_statistics_service.get_ha_statistics_service", lambda: svc,
        )
    return setze


async def test_abgleich_uebernimmt_eine_ha_korrektur_und_protokolliert(ha, datei, _lauf_auf):
    svc, _reihen = ha
    sitzungen, _pfad, aid, _gid = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    t = _ts(ZEIT + timedelta(days=27, hours=13))
    _verschiebe(svc, _EINSP_MID, t, -480.0)        # HAs „Summe anpassen"
    _lauf_auf(sitzungen, svc)

    async with sitzungen() as db:
        antwort = await kanal_abgleich(aid, db=db)

    assert antwort["hat_spiegel"] is True
    assert antwort["fehler"] == 0
    assert [(k["key"], k["ab_ts"]) for k in antwort["korrigiert"]] == [("basis:einspeisung", t)]
    assert antwort["abschnitte"] >= 1 and antwort["kanaele"] >= 1
    assert "basis:einspeisung" in antwort["meldung"]
    assert "neu gespiegelt" in antwort["meldung"]

    async with sitzungen() as s:
        eintraege = (await s.execute(
            select(ActivityLog).where(ActivityLog.anlage_id == aid, ActivityLog.kategorie == "ha_statistics")
        )).scalars().all()
    assert [e.aktion for e in eintraege] == ["HA-Spiegel von Hand abgeglichen: an HA angeglichen"]
    assert eintraege[0].erfolg is True

    # Ein zweiter Druck findet nichts mehr — der Lauf ist idempotent wie der Nachtjob.
    async with sitzungen() as db:
        zweit = await kanal_abgleich(aid, db=db)
    assert zweit["korrigiert"] == []
    assert "stimmen mit der HA-Statistik überein" in zweit["meldung"]


async def test_ohne_spiegel_kein_ha_aufruf(db, monkeypatch):
    anlage = Anlage(anlagenname="Standalone", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()

    async def _nie(*_a, **_k):
        raise AssertionError("ohne Spiegel darf der Lauf nicht starten")

    monkeypatch.setattr("backend.services.kanal.konsistenz.konsistenz_anlage", _nie)
    antwort = await kanal_abgleich(anlage.id, db=db)
    assert antwort["hat_spiegel"] is False
    assert antwort["korrigiert"] == []
    assert "keinen HA-Spiegel" in antwort["meldung"]


async def test_ha_nicht_erreichbar_ist_503(db, monkeypatch):
    anlage = Anlage(anlagenname="Haus", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    kanal = Kanal(anlage_id=anlage.id, key="basis:netzbezug", art=ART_SUM, einheit="kWh")
    db.add(kanal)
    await db.flush()
    db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=0, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz"))
    await db.flush()

    gerufen: list[int] = []

    async def _lauf(_sitzungen, anlage_id, **_k):
        gerufen.append(anlage_id)
        erg = KonsistenzErgebnis(anlage_id)
        erg.zaehle("ha_nicht_erreichbar")
        return erg

    monkeypatch.setattr("backend.services.kanal.konsistenz.konsistenz_anlage", _lauf)
    with pytest.raises(HTTPException) as e:
        await kanal_abgleich(anlage.id, db=db)
    assert e.value.status_code == 503
    assert "nicht erreichbar" in e.value.detail
    assert gerufen == [anlage.id]


async def test_unbekannte_anlage_ist_404(db):
    with pytest.raises(HTTPException) as e:
        await kanal_abgleich(987654, db=db)
    assert e.value.status_code == 404
