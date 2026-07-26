"""Daten-Checker PV-Erzeugung: 3-stufige Quellen-Klassifikation pro Monat.

gemessen=OK · über Aggregat verteilt=INFO · Teil-Lücke=WARNING · gar keine
PV-Quelle=ERROR (Konvention Gernot 2026-06-06). Ersetzt die frühere Pro-Modul-
„fehlt"-WARNING — ein Gesamtwert deckt jetzt alle Strings ab.
[[project_kwp_verteilung_aggregator]].
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.daten_checker import CheckSeverity, DatenChecker


async def _seed(db, *, aggregat=None, pro_modul=None) -> Anlage:
    """2 PV-Strings (6+4 kWp), 1 Monat (05/2026). `aggregat` = Gesamtwert,
    `pro_modul` = {bezeichnung: kWh}."""
    anlage = Anlage(anlagenname="PV-Check", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       pv_erzeugung_kwh=aggregat))
    sued = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0)
    ost = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0)
    db.add_all([sued, ost])
    await db.flush()
    for inv, name in ((sued, "Süd"), (ost, "Ost")):
        if pro_modul and name in pro_modul:
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id, jahr=2026, monat=5,
                verbrauch_daten={"pv_erzeugung_kwh": pro_modul[name]},
            ))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(
            selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten),
            selectinload(Anlage.monatsdaten),
        )
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def _pv_ergebnisse(db, anlage):
    checker = DatenChecker(db)
    md_list = list(anlage.monatsdaten)
    return checker._check_pv_erzeugung(anlage, md_list)


async def test_alle_gemessen_ist_ok(db):
    anlage = await _seed(db, pro_modul={"Süd": 600.0, "Ost": 400.0})
    res = await _pv_ergebnisse(db, anlage)
    assert any(r.schwere == CheckSeverity.OK and "vollständig" in r.meldung for r in res), res


async def test_aggregat_verteilt_ist_info(db):
    anlage = await _seed(db, aggregat=1000.0)
    res = await _pv_ergebnisse(db, anlage)
    info = [r for r in res if r.schwere == CheckSeverity.INFO]
    assert any("kWp-Anteil geschätzt" in r.meldung for r in info), res
    # KEIN ERROR/WARNING, weil das Aggregat alle Strings abdeckt
    assert not any(r.schwere in (CheckSeverity.ERROR, CheckSeverity.WARNING) for r in res), res


async def test_keine_quelle_ist_error(db):
    anlage = await _seed(db, aggregat=None)
    res = await _pv_ergebnisse(db, anlage)
    assert any(r.schwere == CheckSeverity.ERROR and "fehlt" in r.meldung for r in res), res


async def test_keine_quelle_nennt_den_reparaturweg(db):
    """A16/N44: Der Zustand kann auch aus der früheren Start-Migration stammen
    (PV-Gesamtwert bei Anlagen mit BKW-Sensor mitgeleert). Der Befund muss
    deshalb den Weg zurück nennen, nicht nur den Zustand — aufgewertet im
    bestehenden Check statt als zweiter Check daneben."""
    anlage = await _seed(db, aggregat=None)
    fehlt = next(r for r in await _pv_ergebnisse(db, anlage)
                 if r.schwere == CheckSeverity.ERROR and "fehlt" in r.meldung)
    assert "HA-Statistik" in (fehlt.details or "")
    assert "Monatsabschluss" in (fehlt.details or "")
    # Ohne zugeordneten Sensor gibt es keinen automatischen Weg — das muss
    # dastehen, statt eine Reparatur zu versprechen, die es nicht gibt.
    assert "von Hand" in (fehlt.details or "")


async def test_teil_luecke_ohne_aggregat_ist_warning(db):
    anlage = await _seed(db, aggregat=None, pro_modul={"Süd": 600.0})
    res = await _pv_ergebnisse(db, anlage)
    assert any(r.schwere == CheckSeverity.WARNING and "unvollständig" in r.meldung for r in res), res
    assert not any(r.schwere == CheckSeverity.ERROR for r in res), res
