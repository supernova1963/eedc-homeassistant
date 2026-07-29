"""
Akzeptanztest: der Daten-Checker rechnet die Monats-PV über den Read-time-SoT,
nicht als rohe IMD-Summe mit Aggregat-Fallback.

**Warum es diese Datei gibt.** `_get_pv_erzeugung_map` summierte die IMD-Werte
roh, und die beiden Konsumenten (`_calculate_performance_ratio`,
`_check_monatsdaten_plausibilitaet`) fielen bei fehlender Summe auf
`Monatsdaten.pv_erzeugung_kwh` zurück — das globale Entweder-oder, das
`19ae5f73` in Cockpit und HA-Export bereits aufgelöst hatte. In einem Monat mit
**teilweise** gemessenen Strings ging damit eine Teilsumme in die Prüfung.

Die volle Suite blieb nach der Umstellung grün: **kein Test deckte den Fall ab.**
        eedc/backend/tests/test_daten_checker_pv_teilabdeckung.py
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)


async def _seed_zwei_strings(
    db: AsyncSession, *, aggregat: float | None, ost_wert: float | None = None
) -> tuple[Anlage, list[Monatsdaten]]:
    """Zwei Strings (6 + 4 kWp), Mai 2024: Süd misst 500 kWh, Ost je nach Fall."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    for name, kwp in (("Süd", 6.0), ("Ost", 4.0)):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=name, leistung_kwp=kwp,
            anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        ))
    await db.flush()
    invs = {
        i.bezeichnung: i.id
        for i in (await db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id)
        )).scalars()
    }
    db.add(InvestitionMonatsdaten(
        investition_id=invs["Süd"], jahr=2024, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 500.0},
    ))
    if ost_wert is not None:
        db.add(InvestitionMonatsdaten(
            investition_id=invs["Ost"], jahr=2024, monat=5,
            verbrauch_daten={"pv_erzeugung_kwh": ost_wert},
        ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=400.0, netzbezug_kwh=100.0,
        pv_erzeugung_kwh=aggregat,
    ))
    await db.commit()

    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


async def test_teilabdeckung_mit_aggregat_liefert_die_anlagensumme(db):
    """Süd misst 500, Ost nicht, Aggregat 900 → die Karte trägt 900, nicht 500.

    Die 500 sind die Teilsumme. Sie ging vorher in den Performance-Ratio und in
    die SOLL/IST-Abweichung: der Checker meldete einen Ertragseinbruch, den es
    nicht gab — und zwar in genau dem Monat, in dem ein String-Sensor ausfiel.
    """
    anlage, _ = await _seed_zwei_strings(db, aggregat=900.0)

    from backend.services.daten_checker import DatenChecker

    pv_map = await DatenChecker(db)._get_pv_erzeugung_map(anlage)

    assert pv_map.get((2024, 5)) == 900.0, (
        f"Aggregat füllt die Lücke des Ost-Strings, Karte: {pv_map}"
    )


async def test_teilabdeckung_ohne_aggregat_fehlt_in_der_karte(db):
    """Ohne Aggregat bleibt der Monat unauflösbar — kein Eintrag statt Teilsumme (N42)."""
    anlage, _ = await _seed_zwei_strings(db, aggregat=None)

    from backend.services.daten_checker import DatenChecker

    pv_map = await DatenChecker(db)._get_pv_erzeugung_map(anlage)

    assert (2024, 5) not in pv_map, (
        f"Teilsumme darf nicht als Anlagen-PV gelten, Karte: {pv_map}"
    )


async def test_unaufloesbare_pv_meldet_keinen_negativen_hausverbrauch(db):
    """Die Energiebilanz schweigt, wenn die PV des Monats nicht auflösbar ist.

    `pv_erzeugung or 0` machte aus der Lücke eine 0; mit 400 kWh Einspeisung
    ergab die Bilanz −300 kWh Hausverbrauch und einen ERROR über eine Rechnung,
    die schlicht nicht prüfbar ist.
    """
    anlage, monatsdaten = await _seed_zwei_strings(db, aggregat=None)

    from backend.services.daten_checker import DatenChecker

    ergebnisse = await DatenChecker(db)._check_monatsdaten_plausibilitaet(
        anlage, monatsdaten
    )

    negativ = [e for e in ergebnisse if "negativen Hausverbrauch" in (e.meldung or "")]
    assert not negativ, f"Bilanz-Fehlalarm bei unauflösbarer PV: {negativ}"


async def test_vollstaendig_gemessen_bleibt_die_summe_der_messwerte(db):
    """Gegenprobe: messen beide Strings, gilt ihre Summe — auch neben einem Aggregat.

    Das Aggregat (hier bewusst abweichend) darf die Messung nicht überschreiben;
    ohne diese Gegenprobe wäre der Test oben auch mit „immer das Aggregat" grün.
    """
    anlage, _ = await _seed_zwei_strings(db, aggregat=900.0, ost_wert=300.0)

    from backend.services.daten_checker import DatenChecker

    pv_map = await DatenChecker(db)._get_pv_erzeugung_map(anlage)

    assert pv_map.get((2024, 5)) == 800.0, (
        f"Messwerte schlagen das Aggregat (500 + 300), Karte: {pv_map}"
    )


async def test_einzel_endpoint_kennzahlen_unabhaengig_von_der_erfassungsform(db):
    """`GET /monatsdaten/{id}` liefert dieselben Kennzahlen für beide Formen.

    Endpoint-Differenzschnitt (Muster `test_cockpit_finanzen_pv_historie.py`):
    zwei Anlagen mit **identischer Energie**, einmal als Anlagen-Aggregat,
    einmal pro String gemessen. Der Endpoint las bis 2026-07-29
    `md.pv_erzeugung_kwh or 0` — bei Pro-String-Erfassung also **0**, und damit
    Autarkiegrad und Eigenverbrauchsquote der ganzen Antwort daneben.
    """
    from backend.api.routes.monatsdaten import get_monatsdaten

    async def _anlage(name: str, *, gemessen: bool) -> int:
        anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
        db.add(anlage)
        await db.flush()
        pv = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
            leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
        )
        db.add(pv)
        md = Monatsdaten(
            anlage_id=anlage.id, jahr=2024, monat=5,
            einspeisung_kwh=400.0, netzbezug_kwh=100.0,
            pv_erzeugung_kwh=None if gemessen else 800.0,
        )
        db.add(md)
        await db.flush()
        if gemessen:
            db.add(InvestitionMonatsdaten(
                investition_id=pv.id, jahr=2024, monat=5,
                verbrauch_daten={"pv_erzeugung_kwh": 800.0},
            ))
        await db.flush()
        return md.id

    id_aggregat = await _anlage("Aggregat", gemessen=False)
    id_gemessen = await _anlage("Gemessen", gemessen=True)
    await db.commit()

    r_agg = await get_monatsdaten(id_aggregat, db=db)
    r_gem = await get_monatsdaten(id_gemessen, db=db)

    assert r_gem.kennzahlen.autarkiegrad_prozent == r_agg.kennzahlen.autarkiegrad_prozent, (
        "Pro-String-Erfassung rechnete mit PV = 0"
    )
    assert (
        r_gem.kennzahlen.eigenverbrauchsquote_prozent
        == r_agg.kennzahlen.eigenverbrauchsquote_prozent
    )
