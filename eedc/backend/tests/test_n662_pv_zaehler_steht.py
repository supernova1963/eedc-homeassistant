"""N-662 — Daten-Checker „PV – Zähler steht": die Ursache negativer Autarkie benennen, ohne richtige Datenlagen zu melden.

**Der Fall (Register N-662).** Ein Anlagenzähler stand still, die Einspeisung lief weiter ⇒ Cockpit → Tag rechnete
PV 0, Einspeisung 3,5, Netzbezug 3,6 ⇒ Autarkie −3500 %. Entschieden (Gernot, Master 10.10.2026): die Anzeige bleibt,
der Checker nennt die Ursache — in der engen Fassung: nur der Anlagenzähler, wenn er steht, während die Einspeisung
bzw. die Strings wachsen. Je Probe ein Einzelwert (Anzahl Befunde, Investition, Kategorie):

* stehender Anlagenzähler bei wachsender Einspeisung ⇒ 1 Meldung;
* stehender Anlagenzähler bei wachsenden Strings, ohne Einspeisung (Nulleinspeiser) ⇒ 1 Meldung;
* stehender String, während der andere erzeugt ⇒ keine (Option C zurückgenommen — Teilbeschattung, Teilschnee);
* Nulleinspeisung (Einspeisung 0, PV wächst) ⇒ keine — der Einspeisezähler hat keine Regel;
* Winter mit PV 0 und einem Speicher, der ins Netz entlädt ⇒ keine (Abzug der Entladung);
* Speicher ohne Entladungs-Kanal ⇒ keine (die Einspeisung ist dann nicht zu erklären — keine Aussage);
* Schnee auf beiden Strings, der Netzbezug läuft ⇒ keine;
* normaler Stand ⇒ keine.

Datenstand: Kanäle mit Stundenzeilen im Schema des Produkts (``kanal`` · ``kanal_quelle`` · ``kanal_statistik``), die
Uhr der Kanal-Leser gestellt (``bilanz_leser.uhr``) wie in der PV-Matrix.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity
from backend.tests import factories

JETZT = datetime(2026, 1, 20, 12, 0)
#: Die Reihen beginnen vor dem Prüffenster (31 Tage) und enden an der gestellten Uhr.
VON = datetime(2025, 12, 10, 0)
STAND_AB = datetime(2026, 1, 15, 0)          # ab hier steht der „kaputte" Zähler


def _tag(h: int) -> bool:
    return 10 <= h < 16


Rate = Callable[[datetime], float]


async def _kanal(db, anlage_id: int, key: str, rate: Rate, *, entitaet: str) -> None:
    k = Kanal(anlage_id=anlage_id, key=key, art="sum", einheit="kWh")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=0, familie="spiegel", statistic_id=entitaet, offset=0.0))
    stand, t, zeilen = 1000.0, VON, []
    while t < JETZT:
        stand += rate(t)
        zeilen.append(KanalStatistik(kanal_id=k.id, start_ts=int(t.timestamp()), sum=round(stand, 4),
                                     state=round(stand, 4), familie="spiegel"))
        t += timedelta(hours=1)
    db.add_all(zeilen)
    await db.flush()


def _pv(kwh_je_h: float, *, steht_ab: Optional[datetime] = None) -> Rate:
    return lambda t: 0.0 if (steht_ab is not None and t >= steht_ab) or not _tag(t.hour) else kwh_je_h


def _konstant(kwh_je_h: float) -> Rate:
    return lambda _t: kwh_je_h


def _null(_t) -> float:
    return 0.0


async def _befunde(db, monkeypatch, anlage_id: int):
    from backend.services.daten_checker import DatenChecker

    monkeypatch.setattr("backend.services.kanal.bilanz_leser.uhr", lambda: int(JETZT.timestamp()))
    await db.commit()
    anlage = (await db.execute(select(Anlage).options(selectinload(Anlage.investitionen))
                               .where(Anlage.id == anlage_id))).scalar_one()
    return await DatenChecker(db)._check_pv_zaehler_steht(anlage)


async def test_stehender_anlagenzaehler_bei_wachsender_einspeisung(db, monkeypatch):
    a = await factories.anlage(db)
    await _kanal(db, a.id, "basis:pv_gesamt", _pv(0.5, steht_ab=STAND_AB), entitaet="sensor.pv_gesamt")
    await _kanal(db, a.id, "basis:einspeisung", lambda t: 0.3 if _tag(t.hour) else 0.0, entitaet="sensor.einsp")

    befunde = await _befunde(db, monkeypatch, a.id)

    assert [(b.kategorie, b.schwere, b.investition_id) for b in befunde] == [
        (CheckKategorie.PV_ZAEHLER_STEHT.value, CheckSeverity.WARNING, None)]
    assert "15.01.2026" in befunde[0].meldung and "sensor.pv_gesamt" in befunde[0].meldung


async def test_stehender_anlagenzaehler_bei_wachsenden_strings_auch_ohne_einspeisung(db, monkeypatch):
    """Nulleinspeiser mit Anlagenzähler: keine Einspeisung, aber die Strings erzeugen — er misst sie mit."""
    a = await factories.anlage(db)
    sued = await factories.investition(db, a.id, "pv-module", bezeichnung="Süd", leistung_kwp=6.0)
    await _kanal(db, a.id, f"inv:{sued.id}:pv_erzeugung_kwh", _pv(0.4), entitaet="sensor.sued")
    await _kanal(db, a.id, "basis:pv_gesamt", _pv(0.38, steht_ab=STAND_AB), entitaet="sensor.pv_gesamt")
    await _kanal(db, a.id, "basis:einspeisung", _null, entitaet="sensor.einsp")

    befunde = await _befunde(db, monkeypatch, a.id)

    assert [(b.kategorie, b.investition_id) for b in befunde] == [(CheckKategorie.PV_ZAEHLER_STEHT.value, None)]


async def test_stehender_string_ist_keine_regel(db, monkeypatch):
    """Option C zurückgenommen (Master 10.10.2026): ein String steht, der andere erzeugt — Teilbeschattung oder
    Teilschnee sind richtige Datenlagen."""
    a = await factories.anlage(db)
    sued = await factories.investition(db, a.id, "pv-module", bezeichnung="Süd", leistung_kwp=6.0)
    west = await factories.investition(db, a.id, "pv-module", bezeichnung="West", leistung_kwp=4.0)
    await _kanal(db, a.id, f"inv:{sued.id}:pv_erzeugung_kwh", _pv(0.4), entitaet="sensor.sued")
    await _kanal(db, a.id, f"inv:{west.id}:pv_erzeugung_kwh", _pv(0.3, steht_ab=STAND_AB), entitaet="sensor.west")
    await _kanal(db, a.id, "basis:einspeisung", lambda t: 0.2 if _tag(t.hour) else 0.0, entitaet="sensor.einsp")

    assert await _befunde(db, monkeypatch, a.id) == []


async def test_nulleinspeisung_meldet_nichts(db, monkeypatch):
    a = await factories.anlage(db)
    await _kanal(db, a.id, "basis:pv_gesamt", _pv(0.2), entitaet="sensor.pv_gesamt")
    await _kanal(db, a.id, "basis:einspeisung", _null, entitaet="sensor.einsp")
    await _kanal(db, a.id, "basis:netzbezug", _konstant(0.4), entitaet="sensor.netz")

    assert await _befunde(db, monkeypatch, a.id) == []


@pytest.mark.parametrize("mit_entladungs_kanal", [True, False])
async def test_winter_speicher_entlaedt_ins_netz_meldet_nichts(db, monkeypatch, mit_entladungs_kanal):
    """PV 0 über das ganze Fenster, der Speicher speist nachts ins Netz (2,4 kWh je Tag, Entladung 3,6)."""
    a = await factories.anlage(db)
    sp = await factories.investition(db, a.id, "speicher", bezeichnung="Akku")
    await _kanal(db, a.id, "basis:pv_gesamt", _null, entitaet="sensor.pv_gesamt")
    await _kanal(db, a.id, "basis:einspeisung", lambda t: 0.4 if t.hour < 6 else 0.0, entitaet="sensor.einsp")
    if mit_entladungs_kanal:
        await _kanal(db, a.id, f"inv:{sp.id}:entladung_kwh", lambda t: 0.6 if t.hour < 6 else 0.0,
                     entitaet="sensor.akku_entladung")

    assert await _befunde(db, monkeypatch, a.id) == []


async def test_schnee_auf_allen_strings_meldet_nichts(db, monkeypatch):
    a = await factories.anlage(db)
    sued = await factories.investition(db, a.id, "pv-module", bezeichnung="Süd", leistung_kwp=6.0)
    west = await factories.investition(db, a.id, "pv-module", bezeichnung="West", leistung_kwp=4.0)
    for inv, rate in ((sued, 0.4), (west, 0.3)):
        await _kanal(db, a.id, f"inv:{inv.id}:pv_erzeugung_kwh", _pv(rate, steht_ab=STAND_AB),
                     entitaet=f"sensor.{inv.bezeichnung.lower()}")
    await _kanal(db, a.id, "basis:pv_gesamt", _pv(0.7, steht_ab=STAND_AB), entitaet="sensor.pv_gesamt")
    await _kanal(db, a.id, "basis:netzbezug", _konstant(0.5), entitaet="sensor.netz")
    await _kanal(db, a.id, "basis:einspeisung", _pv(0.1, steht_ab=STAND_AB), entitaet="sensor.einsp")

    assert await _befunde(db, monkeypatch, a.id) == []


async def test_normaler_stand_meldet_nichts(db, monkeypatch):
    a = await factories.anlage(db)
    sued = await factories.investition(db, a.id, "pv-module", bezeichnung="Süd", leistung_kwp=6.0)
    await _kanal(db, a.id, f"inv:{sued.id}:pv_erzeugung_kwh", _pv(0.4), entitaet="sensor.sued")
    await _kanal(db, a.id, "basis:pv_gesamt", _pv(0.38), entitaet="sensor.pv_gesamt")
    await _kanal(db, a.id, "basis:einspeisung", lambda t: 0.2 if _tag(t.hour) else 0.0, entitaet="sensor.einsp")

    assert await _befunde(db, monkeypatch, a.id) == []


