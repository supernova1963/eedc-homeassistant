"""
Akzeptanztest #240 NongJoWo: Plausibilitäts-Check „>3× Vorjahr" darf den
Inbetriebnahme-Monat nicht als Vergleichsbasis nutzen — sonst meldet er
nach jeder ersten vollen Jahresrunde fälschlich „3× Vorjahr".
"""

from __future__ import annotations

import traceback
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.daten_checker import DatenChecker, CheckKategorie


async def _reload_anlage(session, anlage_id):
    result = await session.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one()
    monatsdaten = list((await session.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


async def test_keine_3x_warnung_bei_inbetriebnahme_im_vorjahresmonat(db):
    """NongJoWo: Anlage seit Ende März 2022 → 50 kWh im März 2022 (Bruchteil),
    261 kWh im März 2023 (voller Monat). Heuristik darf das nicht als 3×
    Vorjahresabweichung melden.
    """
    anlage = Anlage(
        anlagenname="TestAnlage",
        leistung_kwp=10.0,
        installationsdatum=date(2022, 3, 28),
    )
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2022, 3, 28), leistung_kwp=10.0,
    )
    db.add(pv)

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2022, monat=3,
        einspeisung_kwh=60.0, netzbezug_kwh=100.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=3,
        einspeisung_kwh=261.0, netzbezug_kwh=300.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    checker = DatenChecker(db)
    ergebnisse = checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)

    vj_warnungen = [
        e for e in ergebnisse
        if e.kategorie == CheckKategorie.MONATSDATEN_PLAUSIBILITAET
        and "3×" in (e.meldung or "")
    ]
    assert len(vj_warnungen) == 0, (
        f"Keine 3×-Vorjahr-Warnung erwartet (Inbetriebnahme im "
        f"Vorjahresmonat), bekam: {[e.meldung for e in vj_warnungen]}"
    )


async def test_3x_warnung_bleibt_bei_normalem_vorjahresmonat(db):
    """Kontrolle: Wenn der Vorjahresmonat ein voller Monat ist (Anlage
    schon zwei Jahre älter), soll die Warnung weiterhin kommen.
    """
    anlage = Anlage(
        anlagenname="TestAnlage",
        leistung_kwp=10.0,
        installationsdatum=date(2020, 1, 15),
    )
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 15), leistung_kwp=10.0,
    )
    db.add(pv)

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2022, monat=3,
        einspeisung_kwh=60.0, netzbezug_kwh=100.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=3,
        einspeisung_kwh=261.0, netzbezug_kwh=300.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    checker = DatenChecker(db)
    ergebnisse = checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)

    vj_warnungen = [
        e for e in ergebnisse
        if "3×" in (e.meldung or "") and "Einspeisung" in (e.meldung or "")
    ]
    assert len(vj_warnungen) == 1, (
        f"Erwartet: genau 1 Einspeisung-3×-Warnung, bekam "
        f"{len(vj_warnungen)}: {[e.meldung for e in vj_warnungen]}"
    )


_ASYNC_TESTS = [
    test_keine_3x_warnung_bei_inbetriebnahme_im_vorjahresmonat,
    test_3x_warnung_bleibt_bei_normalem_vorjahresmonat,
]


async def _main() -> int:
    failures = 0
    for fn in _ASYNC_TESTS:
        try:
            await fn()
            print(f"OK   {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
            traceback.print_exc()
        except Exception as e:
            failures += 1
            print(f"ERR  {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    total = len(_ASYNC_TESTS)
    if failures:
        print(f"\n{failures}/{total} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {total} Tests grün.")
    return 0

