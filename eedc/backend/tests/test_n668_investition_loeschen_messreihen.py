"""N-668 — eine gelöschte Investition räumt ihre Messreihen; die nächste mit derselben ID beginnt leer.

**Der Defekt (Analyse 10.10.2026).** ``delete_investition`` räumte Mapping, Gateway und Protokoll auf, aber keine
``sensor_snapshots`` (``inv:<id>:<feld>``) und keine Kanäle (``inv:<id>:<feld>``, ``modus:inv:<id>:<betriebsart>``).
SQLite vergibt die ID der zuletzt angelegten Investition nach dem Löschen neu — die neue Investition las die
Zählerstände der gelöschten als ihre eigenen. Diese Datei hält fest: nach dem Löschen keine Zeile mehr unter dem
Präfix, eine Investition mit derselben ID hat keine, die Reihen der Anlage (``basis:*``) und anderer Investitionen
bleiben, und das Protokoll nennt die Zahl (in derselben Sitzung, N-532).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from backend.models.activity_log import ActivityLog
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.tests import factories

T0 = datetime(2026, 6, 10, 0)


async def _reihe(db, anlage_id: int, key: str, *, snapshot: bool = True) -> None:
    k = Kanal(anlage_id=anlage_id, key=key, art="sum", einheit="kWh")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=0, familie="spiegel", statistic_id="sensor.x", offset=0.0))
    db.add(KanalStatistik(kanal_id=k.id, start_ts=0, sum=1.0, state=1.0, familie="spiegel"))
    if snapshot:
        db.add(SensorSnapshot(anlage_id=anlage_id, sensor_key=key, zeitpunkt=T0, wert_kwh=1.0, quelle="ha_statistics"))
    await db.flush()


async def _schluessel(db, praefix: str) -> tuple[list[str], list[str]]:
    snaps = (await db.execute(select(SensorSnapshot.sensor_key).where(
        SensorSnapshot.sensor_key.like(f"{praefix}%")))).scalars().all()
    kanaele = (await db.execute(select(Kanal.key).where(
        (Kanal.key.like(f"{praefix}%")) | (Kanal.key.like(f"modus:{praefix}%"))))).scalars().all()
    return sorted(snaps), sorted(kanaele)


async def test_loeschen_raeumt_die_reihen_und_die_neue_investition_beginnt_leer(db):
    from backend.api.routes.investitionen.crud import delete_investition

    a = await factories.anlage(db)
    andere = await factories.investition(db, anlage_id=a.id, typ="speicher", bezeichnung="Akku")
    wp = await factories.investition(db, anlage_id=a.id, typ="waermepumpe", bezeichnung="WP")
    await _reihe(db, a.id, f"inv:{wp.id}:stromverbrauch_kwh")
    await _reihe(db, a.id, f"modus:inv:{wp.id}:heizen", snapshot=False)
    await _reihe(db, a.id, f"inv:{andere.id}:ladung_kwh")
    await _reihe(db, a.id, "basis:einspeisung")
    await db.commit()
    alte_id = wp.id

    await delete_investition(alte_id, db)
    await db.commit()

    assert await _schluessel(db, f"inv:{alte_id}:") == ([], [])
    # Die Reihen der Anlage und der anderen Investition bleiben, samt ihrer Kanal-Kinder.
    assert await _schluessel(db, f"inv:{andere.id}:") == ([f"inv:{andere.id}:ladung_kwh"],
                                                         [f"inv:{andere.id}:ladung_kwh"])
    assert await _schluessel(db, "basis:") == (["basis:einspeisung"], ["basis:einspeisung"])
    assert (await db.execute(select(func.count()).select_from(KanalStatistik))).scalar_one() == 2
    assert (await db.execute(select(func.count()).select_from(KanalQuelle))).scalar_one() == 2

    neu = await factories.investition(db, anlage_id=a.id, typ="waermepumpe", bezeichnung="WP neu")
    await db.commit()
    assert neu.id == alte_id          # der Fall des Funds: SQLite vergibt die ID wieder
    assert await _schluessel(db, f"inv:{neu.id}:") == ([], [])

    zeile = (await db.execute(select(ActivityLog).where(ActivityLog.aktion == "Komponente gelöscht"))).scalar_one()
    assert (zeile.details_json["snapshots_entfernt"], zeile.details_json["kanaele_entfernt"]) == (1, 2)
