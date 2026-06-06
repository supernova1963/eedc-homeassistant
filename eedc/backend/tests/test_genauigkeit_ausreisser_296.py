"""
Akzeptanztest für Ausreißer-Markierung im Genauigkeits-Tracking (#296 #9).

Gernot-Entscheidung: KEIN stiller Cap. Ausreißer-Tage (eine Quelle > 50 %
daneben) werden markiert, bleiben aber per Default in MAE/MBE. Nur auf
ausdrücklichen Wunsch (ausreisser_ausblenden=True) fliegen sie aus der
Aggregation — der Tag selbst bleibt in der Tagesliste sichtbar.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage  # noqa: F401
from backend.models.tages_energie_profil import TagesZusammenfassung


async def _make_anlage(db: AsyncSession) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _call(anlage_id: int, db: AsyncSession, ausreisser_ausblenden: bool = False):
    from backend.api.routes.prognosen import get_prognosen_genauigkeit
    return await get_prognosen_genauigkeit(
        anlage_id=anlage_id, tage=30,
        ausreisser_ausblenden=ausreisser_ausblenden, db=db,
    )


async def _seed(db, anlage_id, datum, ist, prognose):
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=datum,
        komponenten_kwh={"pv_1": ist},
        pv_prognose_kwh=prognose,
    ))


async def test_ausreisser_markiert_aber_nicht_weggerechnet(db: AsyncSession):
    anlage_id = await _make_anlage(db)
    heute = date.today()
    # 3 normale Tage (Prognose ~ IST) + 1 Ausreißer (Prognose doppelt so hoch)
    await _seed(db, anlage_id, heute - timedelta(days=4), ist=30.0, prognose=31.0)
    await _seed(db, anlage_id, heute - timedelta(days=3), ist=28.0, prognose=27.0)
    await _seed(db, anlage_id, heute - timedelta(days=2), ist=32.0, prognose=33.0)
    await _seed(db, anlage_id, heute - timedelta(days=1), ist=10.0, prognose=25.0)  # +150 %
    await db.flush()

    resp = await _call(anlage_id, db)
    assert resp.anzahl_ausreisser == 1
    assert resp.ausreisser_schwelle_prozent == 50.0
    # Der Ausreißer-Tag bleibt in der Liste (nicht still entfernt)
    assert resp.anzahl_tage == 4
    flags = {e.datum: e.ist_ausreisser for e in resp.tage}
    assert flags[(heute - timedelta(days=1)).isoformat()] is True
    assert flags[(heute - timedelta(days=2)).isoformat()] is False


async def test_ausblenden_aendert_mae(db: AsyncSession):
    anlage_id = await _make_anlage(db)
    heute = date.today()
    await _seed(db, anlage_id, heute - timedelta(days=4), ist=30.0, prognose=31.0)
    await _seed(db, anlage_id, heute - timedelta(days=3), ist=28.0, prognose=27.0)
    await _seed(db, anlage_id, heute - timedelta(days=2), ist=32.0, prognose=33.0)
    await _seed(db, anlage_id, heute - timedelta(days=1), ist=10.0, prognose=25.0)
    await db.flush()

    mit = await _call(anlage_id, db, ausreisser_ausblenden=False)
    ohne = await _call(anlage_id, db, ausreisser_ausblenden=True)
    # MAE sinkt deutlich, wenn der 150-%-Tag ausgeschlossen wird
    assert mit.openmeteo_mae_prozent > ohne.openmeteo_mae_prozent
    # Tagesliste bleibt in beiden Fällen vollständig
    assert mit.anzahl_tage == ohne.anzahl_tage == 4
