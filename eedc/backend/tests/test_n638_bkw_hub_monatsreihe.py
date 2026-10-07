"""N-638 — *Komponenten → Balkonkraftwerk* ④ Verlauf / ⑤ Vergleich lesen die bewertete Monatsreihe.

Bis 4.1.3 lasen beide Blöcke die rohen ``verbrauch_daten``: die Erzeugung unter ``erzeugung_kwh`` (das BKW trägt
``pv_erzeugung_kwh`` — Spalte immer 0), Eigenverbrauch und Einspeisung nur aus Handpflege. Wer nur die Erzeugung
zuordnete (das Pflichtfeld), sah ein leeres Diagramm; wer „Eigenverbrauch = Erzeugung" pflegte (Melder rapahl,
N-636), sah 100 % Eigenverbrauch neben der anteiligen Kopfzahl darüber.

Jetzt liefert die Route je Monat dieselbe Rechnung wie die Kopfzahlen (``monatsreihe``). Diese Proben halten fest:
Σ Monatsreihe = Kopfzahl, der Eigenverbrauch kommt aus ``bkw_eigenverbrauch_anteil`` (ADR-001-SoT), „nicht bewertbar"
ist ``None`` und nicht 0 (ADR-002/P4). Die Abnahme-Matrix der PV-Achse prüft dieselbe Sicht über alle Zuordnungsformen
(``test_pv_achse_matrix.py``, I4, Sichten ``bkw_hub:*``); hier stehen die Fälle, die die Matrix nicht sät — Monat ohne
Zählerzeile, Datenlücke ohne Erzeugung, gemessene Einspeisung im Altbestand, mehrere Monate.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_balkonkraftwerk import get_balkonkraftwerk_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

ANSCHAFFUNG = date(2024, 1, 1)


async def _anlage(db, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=0.0))
    return anlage


async def _bkw(db, anlage, name="Balkon", **parameter) -> Investition:
    inv = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung=name, leistung_kwp=0.8,
                      anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=800.0, parameter=parameter or None)
    db.add(inv)
    await db.flush()
    return inv


def _summen_wie_kopf(karte) -> None:
    """Σ Monatsreihe = Kopfzahlen derselben Antwort (Kopf rundet auf 0,1 kWh)."""
    z, r = karte.zusammenfassung, karte.monatsreihe
    assert round(sum(m.erzeugung_kwh for m in r), 1) == z["gesamt_erzeugung_kwh"]
    assert round(sum(m.eigenverbrauch_kwh or 0.0 for m in r), 1) == z["gesamt_eigenverbrauch_kwh"]


@pytest.mark.asyncio
async def test_eigenverbrauch_gleich_erzeugung_gepflegt_zeigt_den_anteil_nicht_100_prozent(db):
    """Melder rapahl: dieselbe Entity auf Erzeugung UND Eigenverbrauch (45,1 / 45,1) neben einer Dachanlage.

    eedc liest den Eigenverbrauch nur, wenn die Erzeugung fehlt (``bkw_finanz.py``) — der Hub-Verlauf zeigte ihn
    trotzdem roh (100 % Eigenverbrauch). Jetzt der Anteil an der Hausbilanz, wie die Kopfzahl::

        Dach 854,9 + BKW 45,1 = 900 kWh hinter dem Zähler, Einspeisung 400 ⇒ Eigenverbrauch 500 kWh
        BKW-Anteil 45,1 / 900 = 5,011 % ⇒ 25,06 kWh, Einspeisung 45,1 − 25,06 = 20,04 kWh
    """
    anlage = await _anlage(db, "rapahl")
    dach = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=9.0,
                       anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=12000.0)
    db.add(dach)
    await db.flush()
    bkw = await _bkw(db, anlage)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=9, einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=dach.id, jahr=2026, monat=9,
                                  verbrauch_daten={"pv_erzeugung_kwh": 854.9}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=9,
                                  verbrauch_daten={"pv_erzeugung_kwh": 45.1, "eigenverbrauch_kwh": 45.1}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert (m.jahr, m.monat) == (2026, 9)
    assert m.erzeugung_kwh == pytest.approx(45.1)
    assert m.eigenverbrauch_quelle == "anteilig"
    assert m.eigenverbrauch_kwh == pytest.approx(500.0 * 45.1 / 900.0)
    assert m.einspeisung_quelle == "abgeleitet"
    assert m.einspeisung_kwh == pytest.approx(45.1 - 500.0 * 45.1 / 900.0)
    _summen_wie_kopf(karte)


@pytest.mark.asyncio
async def test_nur_erzeugung_zugeordnet_ist_nicht_mehr_leer(db):
    """Das Pflichtfeld allein (BAU-N636-RALFZ.md, Messung 2: Hub 0 / 0 / 0) — jetzt Erzeugung, Eigenverbrauch
    und Einspeisung aus derselben Rechnung wie der Kopf (BKW allein hinter dem Zähler ⇒ Anteil 100 %)."""
    anlage = await _anlage(db, "nur Erzeugung")
    bkw = await _bkw(db, anlage)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6, einspeisung_kwh=15.1, netzbezug_kwh=80.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 45.1}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert m.erzeugung_kwh == pytest.approx(45.1)
    assert m.eigenverbrauch_kwh == pytest.approx(30.0)
    assert m.einspeisung_kwh == pytest.approx(15.1)
    _summen_wie_kopf(karte)


@pytest.mark.asyncio
async def test_ohne_zaehlerzeile_nicht_bewertbar_ist_none_nicht_null(db):
    """P4: ohne Hausbilanz ist der Eigenverbrauch unbekannt — ``None``, und die Einspeisung als sein Rest ebenso
    (sonst stünde die ganze Erzeugung als Einspeisung da). Die Erzeugung bleibt gemessen stehen."""
    anlage = await _anlage(db, "Mieter-BKW")
    bkw = await _bkw(db, anlage)
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 60.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert m.erzeugung_kwh == pytest.approx(60.0)
    assert m.eigenverbrauch_quelle == "nicht_bewertbar"
    assert m.eigenverbrauch_kwh is None
    assert m.einspeisung_kwh is None and m.einspeisung_quelle is None
    assert karte.zusammenfassung["monate_nicht_bewertbar"] == 1
    _summen_wie_kopf(karte)


@pytest.mark.asyncio
async def test_datenluecke_ohne_erzeugung_traegt_den_gemessenen_eigenverbrauch(db):
    """Der Ersatzträger aus ``bkw_finanz.py``: fehlt die Erzeugung, trägt der gemessene Eigenverbrauch."""
    anlage = await _anlage(db, "Datenlücke")
    bkw = await _bkw(db, anlage)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=300.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"eigenverbrauch_kwh": 20.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert m.erzeugung_kwh == 0.0
    assert (m.eigenverbrauch_kwh, m.eigenverbrauch_quelle) == (pytest.approx(20.0), "gemessen")
    assert (m.einspeisung_kwh, m.einspeisung_quelle) == (0.0, "abgeleitet")
    _summen_wie_kopf(karte)


@pytest.mark.asyncio
async def test_gemessene_einspeisung_und_speicherfelder_unveraendert(db):
    """Altbestand/Import: eine gespeicherte ``einspeisung_kwh`` der BKW-Zeile gilt als gemessen; die BKW-eigenen
    Speicherfelder (``nur_manuell``) gehen unverändert durch."""
    anlage = await _anlage(db, "Altbestand")
    bkw = await _bkw(db, anlage, hat_speicher=True)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6, einspeisung_kwh=10.0, netzbezug_kwh=80.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6, verbrauch_daten={
        "pv_erzeugung_kwh": 40.0, "einspeisung_kwh": 12.5,
        "speicher_ladung_kwh": 4.2, "speicher_entladung_kwh": 3.9}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert (m.einspeisung_kwh, m.einspeisung_quelle) == (12.5, "gemessen")
    assert (m.speicher_ladung_kwh, m.speicher_entladung_kwh) == (4.2, 3.9)
    _summen_wie_kopf(karte)


@pytest.mark.asyncio
async def test_mehrere_monate_summe_gleich_kopf_und_je_monat_eigene_bilanz(db):
    """Drei Monate, je eine eigene Hausbilanz — die Reihe ist chronologisch, je Monat eigener Anteil, Σ = Kopf."""
    anlage = await _anlage(db, "drei Monate")
    bkw = await _bkw(db, anlage)
    for monat, erz, einsp in ((4, 33.5, 10.0), (5, 45.1, 20.0), (6, 52.3, 30.3)):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat, einspeisung_kwh=einsp, netzbezug_kwh=90.0))
        db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": erz}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    assert [(m.monat, m.erzeugung_kwh) for m in karte.monatsreihe] == [(4, 33.5), (5, 45.1), (6, 52.3)]
    assert [round(m.eigenverbrauch_kwh, 4) for m in karte.monatsreihe] == [23.5, 25.1, 22.0]
    _summen_wie_kopf(karte)
