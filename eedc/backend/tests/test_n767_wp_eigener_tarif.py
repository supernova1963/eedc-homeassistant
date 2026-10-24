"""N-767 (24.10.2026) — eigener Wärmepumpen-Tarif: benannte Grenze + Daten-Checker-INFO, keine Zahl geändert.

Mit einem Tarif ``verwendung = waermepumpe``, dessen Arbeitspreis vom allgemeinen abweicht, ist die Anlagensumme
je PV-kWh in der WP um (Haushaltstarif − WP-Tarif) verschoben; eedc kennt den PV-Anteil der WP nicht. Der Checker
nennt die Obergrenze: WP-Strom der letzten 12 abgeschlossenen Monate (Monats-Fakten) × Differenz.

Proben: still ohne WP-Tarif · still bei WP-Tarif == allgemein · still ohne WP-Strom · INFO mit richtigem Betrag bei
Differenz (zwei Tarife, WP-Monate innerhalb UND außerhalb des Fensters). Prüfdatum fest (keine echte Uhr).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.strompreis import Strompreis
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie

_HEUTE = date(2026, 10, 24)
_KAT = CheckKategorie.WP_EIGENER_TARIF.value

#: Zwölf abgeschlossene Monate vor Oktober 2026: 10/2025 … 09/2026.
_FENSTER = [(2025, m) for m in (10, 11, 12)] + [(2026, m) for m in range(1, 10)]


async def _anlage(db, *, wp_cent: float | None, allgemein_cent: float = 30.0, wp_strom: float = 100.0):
    anlage = Anlage(anlagenname="N767", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=allgemein_cent, einspeiseverguetung_cent_kwh=8.0))
    if wp_cent is not None:
        db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=wp_cent, einspeiseverguetung_cent_kwh=0.0))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2024, 1, 1), parameter={"wp_art": "luft_wasser"})
    db.add(wp)
    await db.flush()
    # Im Fenster je Monat `wp_strom`; davor (09/2025) und im laufenden Monat (10/2026) je 500 kWh, die NICHT zählen.
    for jahr, monat in [(2025, 9), *_FENSTER, (2026, 10)]:
        strom = wp_strom if (jahr, monat) in _FENSTER else 500.0
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=monat, netzbezug_kwh=200.0, einspeisung_kwh=300.0))
        db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=jahr, monat=monat,
                                      verbrauch_daten={"stromverbrauch_kwh": strom}))
    await db.commit()
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.strompreise)).where(Anlage.id == anlage.id)
    )).scalar_one()


async def _pruefe(db, anlage):
    return await DatenChecker(db)._check_wp_eigener_tarif(anlage, heute=_HEUTE)


async def test_still_ohne_wp_tarif(db):
    assert await _pruefe(db, await _anlage(db, wp_cent=None)) == []


async def test_still_bei_wp_tarif_gleich_allgemein(db):
    assert await _pruefe(db, await _anlage(db, wp_cent=30.0)) == []


async def test_still_ohne_wp_strom(db):
    """Grenzfall: Tarif weicht ab, aber im Fenster ist kein WP-Strom gemessen (die 500 kWh außerhalb zählen nicht)."""
    assert await _pruefe(db, await _anlage(db, wp_cent=22.0, wp_strom=0.0)) == []


async def test_info_mit_obergrenze_aus_fenster_und_differenz(db):
    """12 × 100 kWh × (30 − 22) ct = 96 € — die Monate außerhalb des Fensters (2 × 500 kWh) zählen nicht."""
    ergebnisse = await _pruefe(db, await _anlage(db, wp_cent=22.0))

    assert len(ergebnisse) == 1, [e.meldung for e in ergebnisse]
    e = ergebnisse[0]
    assert (e.kategorie, e.schwere, e.link, e.action_kind) == (_KAT, "info", None, None)
    assert "22,00 ct gegen 30,00 ct" in e.meldung
    assert "bis zu 96 €" in e.meldung
    assert "1.200 kWh" in e.details and "8,00 ct" in e.details
    assert "PV-Anteil" in e.details and "Haushaltstarif" in e.details


async def test_teurerer_wp_tarif_meldet_den_betrag_der_differenz(db):
    """Das Vorzeichen hängt am Messpunkt — gemeldet wird der Betrag der Abweichung."""
    ergebnisse = await _pruefe(db, await _anlage(db, wp_cent=35.0))
    assert len(ergebnisse) == 1 and "bis zu 60 €" in ergebnisse[0].meldung


async def test_abgelaufener_wp_tarif_ist_still(db):
    """Gilt der WP-Tarif am Stichtag nicht mehr, rechnet eedc die WP zum Haushaltstarif — nichts zu melden."""
    anlage = await _anlage(db, wp_cent=22.0)
    wp_tarif = next(t for t in anlage.strompreise if t.verwendung == "waermepumpe")
    wp_tarif.gueltig_bis = date(2026, 6, 30)
    await db.commit()
    assert await _pruefe(db, anlage) == []
