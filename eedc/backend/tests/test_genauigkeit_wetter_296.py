"""
Akzeptanztest für Wettersymbole an Vergangenheitstagen im Genauigkeits-
Tracking (#296 #2).

Die TagesZusammenfassung trägt keinen WMO-Code; er liegt nur stündlich im
TagesEnergieProfil. Der Genauigkeits-Endpoint aggregiert pro Tag ein
repräsentatives Symbol (mittlere Bewölkung + Tagessumme Niederschlag + Code der
Mittagsstunde) über denselben SoT-Helper wie der Forecast-Pfad.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests import factories


async def _make_anlage(db: AsyncSession) -> int:
    return (await factories.anlage(db)).id


async def _call(anlage_id: int, db: AsyncSession):
    from backend.api.routes.prognosen import get_prognosen_genauigkeit
    return await get_prognosen_genauigkeit(anlage_id=anlage_id, tage=30, db=db)


async def test_wettersymbol_aus_stundenprofil(db: AsyncSession):
    anlage_id = await _make_anlage(db)
    gestern = date.today() - timedelta(days=1)
    # Tageszusammenfassung mit IST + Prognose + Temp
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=gestern,
        komponenten_kwh={"pv_1": 30.0},
        pv_prognose_kwh=32.0,
        temperatur_max_c=18.4,
    ))
    # Stundenprofil: klarer Tag → niedrige Bewölkung, kein Niederschlag
    for h in range(8, 18):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=gestern, stunde=h,
            bewoelkung_prozent=10.0, niederschlag_mm=0.0, wetter_code=0,
        ))
    await db.flush()

    resp = await _call(anlage_id, db)
    eintrag = next(e for e in resp.tage if e.datum == gestern.isoformat())
    assert eintrag.wetter_symbol == "sunny"  # <20 % Bewölkung
    assert eintrag.temperatur_max_c == 18  # gerundet


async def test_wettersymbol_regentag(db: AsyncSession):
    anlage_id = await _make_anlage(db)
    gestern = date.today() - timedelta(days=1)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=gestern,
        komponenten_kwh={"pv_1": 12.0}, pv_prognose_kwh=20.0,
    ))
    for h in range(8, 18):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=gestern, stunde=h,
            bewoelkung_prozent=95.0, niederschlag_mm=1.2, wetter_code=61,  # Regen
        ))
    await db.flush()

    resp = await _call(anlage_id, db)
    eintrag = next(e for e in resp.tage if e.datum == gestern.isoformat())
    assert eintrag.wetter_symbol == "rainy"


async def test_kein_stundenprofil_kein_symbol(db: AsyncSession):
    anlage_id = await _make_anlage(db)
    gestern = date.today() - timedelta(days=1)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=gestern,
        komponenten_kwh={"pv_1": 12.0}, pv_prognose_kwh=20.0,
    ))
    await db.flush()

    resp = await _call(anlage_id, db)
    eintrag = next(e for e in resp.tage if e.datum == gestern.isoformat())
    assert eintrag.wetter_symbol is None
