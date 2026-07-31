"""Daten-Checker meldet Monate mit Daten, für die kein Tarif hinterlegt ist.

Fehlerbild aus dem Forum (simon42 #89667/60, Algie): 36 Monate aus der
HA-Statistik importiert, danach den Strompreis angelegt — dessen Formular
schlug „heute" als Gültigkeitsbeginn vor. Alle importierten Monate fielen damit
hinter den Tarif und rechneten still mit der Vorbelegung von 30 ct/kWh, während
Einstellungen → Strompreise einen gepflegten Tarif zeigte.

Die Lücken-Prüfung gab es bereits, sie hing aber vollständig an
`if anlage.installationsdatum:` — und das Feld ist nullable, bei frischen
Installationen also regelmäßig leer. Gemessen wird jetzt an den vorhandenen
Monatsdaten ([[feedback_keine_regel_behaupten_ohne_code_beleg]]: eine Prüfung,
die im Normalfall übersprungen wird, deckt nichts ab).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Monatsdaten, Strompreis
from backend.services.daten_checker import DatenChecker


async def _lade(db, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen), selectinload(Anlage.strompreise))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def _anlage(db, *, installationsdatum: date | None) -> int:
    anlage = Anlage(
        anlagenname="TarifLuecke", leistung_kwp=10.0,
        installationsdatum=installationsdatum,
    )
    db.add(anlage)
    await db.flush()
    return anlage.id


def _luecken_meldungen(ergebnisse) -> list[str]:
    return [r.meldung for r in ergebnisse if "vor dem ersten Tarif" in r.meldung]


@pytest.mark.asyncio
async def test_importierte_monate_ohne_tarif_werden_gemeldet(db):
    """Der Kernfall — und zwar OHNE Inbetriebnahme-Datum."""
    anlage_id = await _anlage(db, installationsdatum=None)
    for monat in (4, 5, 6):
        db.add(Monatsdaten(
            anlage_id=anlage_id, jahr=2026, monat=monat,
            einspeisung_kwh=100.0, netzbezug_kwh=200.0,
        ))
    db.add(Strompreis(
        anlage_id=anlage_id, gueltig_ab=date(2026, 7, 30),
        netzbezug_arbeitspreis_cent_kwh=28.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.flush()

    checker = DatenChecker(db)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )).scalars().all())
    ergebnisse = checker._check_strompreise(await _lade(db, anlage_id), monatsdaten)

    meldungen = _luecken_meldungen(ergebnisse)
    assert len(meldungen) == 1
    assert "3 Monat(e)" in meldungen[0]
    treffer = next(r for r in ergebnisse if "vor dem ersten Tarif" in r.meldung)
    assert "30 ct/kWh" in (treffer.details or "")
    assert treffer.link == "/einstellungen/strompreise"


@pytest.mark.asyncio
async def test_tarif_ab_monatsmitte_deckt_den_laufenden_monat_nicht(db):
    """Stichtag ist der Monatserste — ein Tarif ab dem 15. gilt erst ab dem
    Folgemonat, der laufende Monat rechnet noch mit der Vorbelegung."""
    anlage_id = await _anlage(db, installationsdatum=None)
    db.add(Monatsdaten(
        anlage_id=anlage_id, jahr=2026, monat=7,
        einspeisung_kwh=10.0, netzbezug_kwh=20.0,
    ))
    db.add(Strompreis(
        anlage_id=anlage_id, gueltig_ab=date(2026, 7, 15),
        netzbezug_arbeitspreis_cent_kwh=28.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.flush()

    checker = DatenChecker(db)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )).scalars().all())
    ergebnisse = checker._check_strompreise(await _lade(db, anlage_id), monatsdaten)

    assert len(_luecken_meldungen(ergebnisse)) == 1


@pytest.mark.asyncio
async def test_rueckdatierter_tarif_meldet_nichts(db):
    """Gegenprobe: deckt der Tarif die Daten ab, bleibt der Checker still —
    sonst wäre die Meldung nicht abstellbar ([[feedback_daten_checker_kein_akzeptiert]])."""
    anlage_id = await _anlage(db, installationsdatum=date(2026, 4, 1))
    for monat in (4, 5, 6):
        db.add(Monatsdaten(
            anlage_id=anlage_id, jahr=2026, monat=monat,
            einspeisung_kwh=100.0, netzbezug_kwh=200.0,
        ))
    db.add(Strompreis(
        anlage_id=anlage_id, gueltig_ab=date(2026, 4, 1),
        netzbezug_arbeitspreis_cent_kwh=28.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.flush()

    checker = DatenChecker(db)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )).scalars().all())
    ergebnisse = checker._check_strompreise(await _lade(db, anlage_id), monatsdaten)

    assert _luecken_meldungen(ergebnisse) == []
    assert [r.meldung for r in ergebnisse if "Strompreis-Lücke" in r.meldung] == []
