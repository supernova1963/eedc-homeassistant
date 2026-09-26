"""Zählerlücken wie HA — Schnitt 2: Schema, Migration, Provenance-Skip, API-Typen.

Vorlage Fassung 7 §3. `TagesEnergieProfil.spannen` (R2, dünn) und
`TagesZusammenfassung.verworfen` (R4 + Regelmarke R9) — beide JSON nullable
mit `none_as_null`, weil NULL (Altbestand) und `{}` (neue Regel, nichts
verworfen) zwei verschiedene Aussagen sind.

Schwesterdateien: test_zaehlerluecken_r3_deckel_spanne.py, test_konformitaet_tz_felder.py.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.api.routes.energie_profil._shared import StundenWertResponse, TagWerteResponse
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._provenance_helpers import (
    seed_tep_provenance,
    seed_tz_provenance,
)


async def test_migration_legt_beide_spalten_an_idempotent_ohne_backfill(tmp_path):
    from backend.core.database import Base, run_migrations
    import backend.models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'m.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE tages_zusammenfassung DROP COLUMN verworfen"))
            await conn.execute(text("ALTER TABLE tages_energie_profil DROP COLUMN spannen"))
            await conn.execute(text(
                "INSERT INTO tages_zusammenfassung (anlage_id, datum, stunden_verfuegbar, "
                "source_provenance, created_at, updated_at) "
                "VALUES (1, '2025-11-01', 24, '{}', '2025-11-01', '2025-11-01')"
            ))
        for _lauf in (1, 2):
            async with engine.begin() as conn:
                await run_migrations(conn)

        async with engine.begin() as conn:
            def _spalten(sync_conn, tabelle):
                return {c["name"] for c in inspect(sync_conn).get_columns(tabelle)}
            assert "verworfen" in await conn.run_sync(_spalten, "tages_zusammenfassung")
            assert "spannen" in await conn.run_sync(_spalten, "tages_energie_profil")
            res = await conn.execute(text(
                "SELECT verworfen FROM tages_zusammenfassung WHERE datum = '2025-11-01'"))
            # Altbestand bleibt NULL — die Regelmarke kommt nur mit Neuaggregation.
            assert res.fetchone() == (None,)
    finally:
        await engine.dispose()


async def test_null_und_leeres_dict_bleiben_unterscheidbar(db):
    jetzt = datetime(2026, 9, 26)
    db.add(TagesZusammenfassung(anlage_id=1, datum=date(2025, 11, 1), verworfen=None,
                                source_provenance={}, created_at=jetzt, updated_at=jetzt))
    db.add(TagesZusammenfassung(anlage_id=1, datum=date(2025, 11, 2), verworfen={},
                                source_provenance={}, created_at=jetzt, updated_at=jetzt))
    db.add(TagesEnergieProfil(anlage_id=1, datum=date(2025, 11, 2), stunde=5,
                              spannen=None, source_provenance={}))
    await db.commit()
    roh = (await db.execute(text(
        "SELECT datum, verworfen FROM tages_zusammenfassung ORDER BY datum"))).all()
    assert roh[0][1] is None           # echtes SQL-NULL, nicht die Zeichenkette 'null'
    assert roh[1][1] == "{}"
    roh_tep = (await db.execute(text("SELECT spannen FROM tages_energie_profil"))).all()
    assert roh_tep[0][0] is None
    tzs = (await db.execute(select(TagesZusammenfassung).order_by(TagesZusammenfassung.datum))).scalars().all()
    assert tzs[0].verworfen is None and tzs[1].verworfen == {}


def test_provenance_ueberspringt_beide_spalten():
    tz = TagesZusammenfassung(anlage_id=1, datum=date(2025, 11, 2),
                              verworfen={"pv": 31368.0}, ueberschuss_kwh=1.0)
    seed_tz_provenance(tz, writer="t", source="external:ha_statistics:daily")
    assert "verworfen" not in (tz.source_provenance or {})
    assert "ueberschuss_kwh" in tz.source_provenance
    tep = TagesEnergieProfil(anlage_id=1, datum=date(2025, 11, 2), stunde=3,
                             spannen={"netzbezug": 2}, netzbezug_kw=1.0)
    seed_tep_provenance(tep, writer="t", source="external:ha_statistics:hourly")
    assert "spannen" not in (tep.source_provenance or {})
    assert "netzbezug_kw" in tep.source_provenance


def test_api_typen_tragen_die_felder():
    assert StundenWertResponse(stunde=4, spannen={"pv": 13}).spannen == {"pv": 13}
    assert StundenWertResponse(stunde=4).spannen is None
    z = TagWerteResponse(datum=date(2025, 11, 5), verworfen={"wallbox": 1906.499})
    assert z.verworfen == {"wallbox": 1906.499}
    assert TagWerteResponse(datum=date(2025, 11, 5)).verworfen is None


async def test_stunden_route_reicht_spannen_durch(db):
    from backend.api.routes.energie_profil.serien import get_stundenwerte
    from backend.models.anlage import Anlage

    jetzt = datetime(2026, 9, 26)
    db.add(Anlage(id=7, anlagenname="A", leistung_kwp=10.0, created_at=jetzt, updated_at=jetzt))
    db.add(TagesEnergieProfil(anlage_id=7, datum=date(2025, 11, 5), stunde=19,
                              pv_kw=118.0, spannen={"pv": 129}, source_provenance={}))
    db.add(TagesEnergieProfil(anlage_id=7, datum=date(2025, 11, 5), stunde=20,
                              pv_kw=1.0, source_provenance={}))
    await db.commit()
    antwort = await get_stundenwerte(anlage_id=7, datum=date(2025, 11, 5), db=db)
    je = {s.stunde: s.spannen for s in antwort.stunden}
    assert je == {19: {"pv": 129}, 20: None}
