"""Cockpit → Monat rechnet die Ergebnis-Leiter — Proben P2 · P5 · P12 · N-602 (Paket „Ergebnisgrößen", 03.10.2026).

* **P2 (N-601):** bei Regelbesteuerung nannte Cockpit → Monat 212,00 € Netto-Ertrag, die Übersicht für denselben
  Monat 206,30 € (USt auf den Eigenverbrauch 5,70 €). Fixture aus ``test_netto_ertrag_vier_wege_symmetrie``.
* **P5 (E5):** ein Vorjahresmonat ohne Stromrechnung hat kein Ergebnis — bis dahin zählte sie als 0. ⚠ Ein
  Vorjahresmonat **mit** Zählerzeile hat immer einen Netzbezug (``Monatsdaten.netzbezug_kwh`` ist NOT NULL,
  ``models/monatsdaten.py:49``); ohne Zählerzeile gibt es gar keinen Vorjahresvergleich. Die erreichbare Form des
  Defekts ist der Monat mit **0 kWh**: dort fehlte die Stromrechnung (``netz > 0``), und ``or 0`` machte daraus ein
  Ergebnis ohne Grundpreis — das Vorjahr wich vom selben Monat in Cockpit → Monat ab. Die None-Regel selbst prüft
  ``test_ergebnis_leiter.py`` (Layer) — eine Probe mit einem produktiv unerreichbaren Zustand gibt es hier bewusst nicht.
* **P12 (§3.4):** Satz-Rückfälle — Jahr ohne Abschluss ⇒ Vorjahres-Satz; ohne beides ⇒ kein USt-Anteil, aber ein
  Satz, der es sagt; Jahr ohne PV ⇒ Satz 0.
* **N-602:** die Betriebskosten der Kachel tragen nur im Monat aktive Komponenten (Probe des Fundtags, wörtlich).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.ust_satz import ust_satz_des_jahres
from backend.tests.test_netto_ertrag_vier_wege_symmetrie import _anlage_mit_regelbesteuerung


@pytest.mark.asyncio
async def test_p2_monat_zieht_die_ust_ab_wie_die_uebersicht(db):
    anlage_id = await _anlage_mit_regelbesteuerung(db)
    monat = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=6, db=db)
    uebersicht = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    assert monat.ust_eigenverbrauch_euro == pytest.approx(5.7, abs=0.005)
    assert monat.netto_ertrag_euro == pytest.approx(206.3, abs=0.005)
    assert monat.netto_ertrag_euro == pytest.approx(uebersicht.netto_ertrag_euro, abs=0.01)
    # Herleitung nennt den Posten und den Satz (P4).
    namen = [w.name for w in monat.ergebnis_herleitung.netto_ertrag.eingesetzte_werte]
    assert "USt auf Eigenverbrauch" in namen
    assert "Grundlage Jun 2026" in (monat.ust_herleitung or "")
    # Ergebnis = 206,30 − 30,00 Stromrechnung (100 kWh × 0,30, kein Grundpreis) = 176,30.
    assert monat.ergebnis_euro == pytest.approx(176.3, abs=0.005)


async def _anlage_vj(db, *, netzbezug_vj):
    anlage = Anlage(anlagenname="VJ-E5", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=13.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    for jahr, netz in ((2025, netzbezug_vj), (2026, 100.0)):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=6, einspeisung_kwh=400.0, netzbezug_kwh=netz))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=jahr, monat=6,
                                      verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_p5_vorjahr_mit_netzbezug_null_traegt_den_grundpreis(db):
    """Eine gemessene 0 ist ein Wert: die Stromrechnung ist dann der Grundpreis — wie im laufenden Monat."""
    anlage_id = await _anlage_vj(db, netzbezug_vj=0.0)
    vj = (await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=6, db=db)).vorjahr
    monat_vj = await get_aktueller_monat(anlage_id=anlage_id, jahr=2025, monat=6, db=db)
    assert vj.get("netzbezug_kosten_euro") == pytest.approx(13.0)
    assert vj.get("ergebnis_euro") == pytest.approx(monat_vj.ergebnis_euro, abs=0.005)
    assert vj.get("ergebnis_vor_betriebskosten_euro") == pytest.approx(
        monat_vj.ergebnis_vor_betriebskosten_euro, abs=0.005)


@pytest.mark.asyncio
async def test_n602_betriebskosten_nur_im_monat_aktiver_komponenten(db):
    """Probe des Fundtags (03.10.): PV 120 €/J seit 2024, E-Auto 600 €/J ab 14.08.2026, angezeigt September 2025."""
    anlage = Anlage(anlagenname="N-602", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1), betriebskosten_jahr=120.0)
    auto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto", parameter={},
                       anschaffungsdatum=date(2026, 8, 14), betriebskosten_jahr=600.0)
    db.add_all([pv, auto])
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=9, einspeisung_kwh=300.0, netzbezug_kwh=150.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=9,
                                  verbrauch_daten={"pv_erzeugung_kwh": 800.0}))
    await db.commit()

    d = await get_aktueller_monat(anlage_id=anlage.id, jahr=2025, monat=9, db=db)
    assert d.betriebskosten_anteilig_euro == pytest.approx(10.0)
    assert d.betriebskosten_anteilig_anzahl == 1
    assert d.betriebskosten_anteilig_jahr_euro == pytest.approx(120.0)
    # Kachel == T-Konto: dieselbe Filtermenge (#402).
    assert [(f.bezeichnung, f.betriebskosten_monat_euro) for f in d.investitionen_financials] == [("Dach", 10.0)]


async def _regel_anlage(db, *, pv_anschaffung=date(2024, 1, 1)):
    anlage = Anlage(anlagenname="P12", leistung_kwp=10.0,
                    steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=pv_anschaffung, anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    return anlage, pv


@pytest.mark.asyncio
async def test_p12_jahr_ohne_abschluss_nimmt_den_vorjahres_satz(db):
    anlage, pv = await _regel_anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6, einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()
    await db.refresh(anlage, ["investitionen"])
    fakten = await lade_monats_fakten(db, anlage.id, von=(2025, 1), bis=(2026, 12))
    satz = ust_satz_des_jahres(anlage, anlage.investitionen, fakten, 2026)
    assert satz.grundlage_jahr == 2025
    assert satz.euro_je_kwh == pytest.approx(5.7 / 600, rel=1e-9)
    assert "für 2026 gibt es noch keinen Abschluss" in satz.herleitung()


@pytest.mark.asyncio
async def test_p12_ohne_jeden_abschluss_kein_ust_anteil_aber_ein_grund(db):
    # PV erst ab 2027 ⇒ in 2025 und 2026 kein Monat mit aktivem Erzeuger.
    anlage, _pv = await _regel_anlage(db, pv_anschaffung=date(2027, 1, 1))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=300.0))
    await db.commit()
    d = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=6, db=db)
    assert d.ust_eigenverbrauch_euro is None
    assert "nicht ermittelbar" in (d.ust_herleitung or "")
    assert "USt auf Eigenverbrauch" in d.fehlende_posten


@pytest.mark.asyncio
async def test_p12_jahr_ohne_pv_hat_satz_null(db):
    anlage, pv = await _regel_anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=1, einspeisung_kwh=0.0, netzbezug_kwh=500.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=1, verbrauch_daten={"pv_erzeugung_kwh": 0.0}))
    await db.commit()
    await db.refresh(anlage, ["investitionen"])
    fakten = await lade_monats_fakten(db, anlage.id, von=(2025, 1), bis=(2026, 12))
    satz = ust_satz_des_jahres(anlage, anlage.investitionen, fakten, 2026)
    assert satz.grundlage_jahr == 2026
    assert satz.euro_je_kwh == 0.0
