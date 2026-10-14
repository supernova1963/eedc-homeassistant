"""RF-27 Fall-Probe: die Zweige von `/monatsdaten/aggregiert`, die keine Testdatei der Linie erreicht.

Schwestern: `test_aggregiert_monats_fakten.py` (Zeilenmenge, Schicht), `test_377_zaehlerstaende.py` (Zählerstand als
Bestandsgröße), `test_wetter_monatstemperatur_n426.py` (Vorrangkette der Monatstemperatur).

F1 Zählerstand am Monatsende (#377) je Zähler-Gerät, gerundet auf 3 Stellen; ein Monat ohne Stand trägt `None` (nicht `{}`).
F2 Monatsmittel der Außentemperatur über zwei Jahre (`jahr=None`): der gepflegte Wert füllt die Lücke auch im ersten Jahr.
F3 Gepflegte Monats-Ø-Preise (Flex-Bezug, variable Einspeisevergütung #392) stehen in der Zeile; ohne Zeile `None`.
F4 Legacy-Hinweis F-31: Altwert PV, aktives Modul mit gemessener 0 ⇒ Hinweis, aber Ziel vorhanden.
F5 Legacy-Hinweis: Altwert nur in der Speicher-Entladung, kein Speicher ⇒ Hinweis ohne Ziel.
F6 USt-Anteil nur für Monate der Grundgesamtheit (Regelbesteuerung; Monat ohne Zählerzeile trägt 0,0).
"""
from __future__ import annotations

from datetime import date

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


async def _anlage(db) -> Anlage:
    a = Anlage(anlagenname="RF-27", leistung_kwp=10.0, standort_land="DE")
    db.add(a)
    await db.flush()
    return a


async def test_f1_zaehlerstand_am_monatsende(db):
    a = await _anlage(db)
    gas = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Gaszähler", anschaffungsdatum=date(2025, 1, 1),
                      parameter={"kategorie": "zaehler", "zaehler_art": "gas"})
    db.add(gas)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=5, einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=6, einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(InvestitionMonatsdaten(investition_id=gas.id, jahr=2025, monat=5, verbrauch_daten={"zaehlerstand": 1234.56789}))
    await db.commit()

    zeilen = {z.monat: z for z in await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=2025, db=db)}

    assert zeilen[5].zaehler_stand == {str(gas.id): 1234.568}
    assert zeilen[6].zaehler_stand is None


async def test_f2_gepflegte_temperatur_ueber_zwei_jahre(db):
    a = await _anlage(db)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2024, monat=3, einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       durchschnittstemperatur=4.5))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=3, einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       durchschnittstemperatur=6.5))
    await db.commit()

    zeilen = {(z.jahr, z.monat): z for z in await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=None, db=db)}

    assert zeilen[(2024, 3)].durchschnittstemperatur_c == 4.5
    assert zeilen[(2025, 3)].durchschnittstemperatur_c == 6.5


async def test_f3_gepflegte_monatspreise_stehen_in_der_zeile(db):
    a = await _anlage(db)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=4, einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       netzbezug_durchschnittspreis_cent=27.5, einspeise_durchschnittspreis_cent=6.4))
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2025, 1, 1))
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2025, monat=5, verbrauch_daten={"stromverbrauch_kwh": 80.0}))
    await db.commit()

    zeilen = {z.monat: z for z in await list_monatsdaten_aggregiert(
        anlage_id=a.id, jahr=2025, inkl_ohne_zaehlerzeile=True, db=db)}

    assert zeilen[4].netzbezug_durchschnittspreis_cent == 27.5
    assert zeilen[4].einspeise_durchschnittspreis_cent == 6.4
    assert zeilen[5].id is None and zeilen[5].anlage_id == a.id
    assert zeilen[5].netzbezug_durchschnittspreis_cent is None
    assert zeilen[5].einspeise_durchschnittspreis_cent is None


async def test_f4_legacy_pv_mit_aktivem_ziel(db):
    """F-31: Altwert im Anlagen-Aggregat, ein aktives PV-Modul mit gemessener 0 ⇒ Hinweis „öffnen und speichern", nicht „kein Ziel"."""
    a = await _anlage(db)
    modul = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", anschaffungsdatum=date(2025, 1, 1),
                        leistung_kwp=5.0)
    db.add(modul)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=7, einspeisung_kwh=100.0, netzbezug_kwh=50.0, pv_erzeugung_kwh=400.0))
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2025, monat=7, verbrauch_daten={"pv_erzeugung_kwh": 0.0}))
    await db.commit()

    z = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=2025, db=db))[0]

    assert z.hat_legacy_daten is True
    assert z.legacy_ohne_ziel is False


async def test_f5_legacy_speicher_nur_entladung_ohne_ziel(db):
    """Altwert nur in `batterie_entladung_kwh`, kein Speicher im Monat ⇒ Hinweis mit Grund „kein Ziel"."""
    a = await _anlage(db)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=8, einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       batterie_ladung_kwh=0.0, batterie_entladung_kwh=30.0))
    await db.commit()

    z = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=2025, db=db))[0]

    assert z.hat_legacy_daten is True
    assert z.legacy_ohne_ziel is True


async def test_f6_ust_nur_in_der_grundgesamtheit(db):
    """Regelbesteuerung: der Monat ohne Zählerzeile (nur mit dem Flag geliefert) trägt keinen USt-Anteil (G1/E9)."""
    a = Anlage(anlagenname="RF-27 USt", leistung_kwp=10.0, standort_land="DE",
               steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0)
    db.add(a)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", anschaffungsdatum=date(2024, 1, 1),
                     leistung_kwp=10.0, anschaffungskosten_gesamt=20000.0, betriebskosten_jahr=200.0)
    db.add(pv)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=5, einspeisung_kwh=300.0, netzbezug_kwh=100.0))
    for monat in (5, 7):
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()

    zeilen = {z.monat: z for z in await list_monatsdaten_aggregiert(
        anlage_id=a.id, jahr=2026, inkl_ohne_zaehlerzeile=True, db=db)}

    assert zeilen[5].ust_eigenverbrauch_euro > 0
    assert zeilen[7].id is None
    assert zeilen[7].ust_eigenverbrauch_euro == 0.0
