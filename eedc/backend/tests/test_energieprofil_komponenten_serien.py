"""
Akzeptanztest für den Endpoint `GET /energie-profil/{anlage_id}/komponenten-serien`.

Hintergrund: Die Energieprofil-Tagestabelle bietet pro Komponente eine eigene
Diagnose-Spalte (Roadmap #110, Rainer-PN 2026-05-19). Die Spalten brauchen
echte Investitions-Labels statt Roh-Keys — der Endpoint löst alle im Zeitraum
vorkommenden `komponenten_kwh`-Keys über den Shared-Helper `_key_to_serie_info`
zu `SerieInfo` auf.

Geprüft:
  1. Investitions-Keys werden zu Label/Kategorie/Seite aufgelöst
  2. Virtuelle Keys (haushalt) werden aufgelöst
  3. Keys ohne passende Investition werden verworfen (kein Crash)
  4. Nur Keys aus dem angefragten Zeitraum landen im Ergebnis
  5. Unbekannte Anlage → 404
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition, TagesZusammenfassung


async def _call(anlage_id: int, von: date, bis: date, db: AsyncSession):
    from backend.api.routes.energie_profil.views import get_komponenten_serien
    return await get_komponenten_serien(anlage_id=anlage_id, von=von, bis=bis, db=db)


async def _seed(db: AsyncSession) -> int:
    """Anlage mit drei Investitionen + zwei Tageszusammenfassungen."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="PV Dach")
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW Süd")
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP Keller")
    db.add_all([pv, bkw, wp])
    await db.flush()

    # Tag im Zeitraum: vier Komponenten-Keys, einer ohne Investition (pv_999).
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=date(2026, 5, 10),
        komponenten_kwh={
            f"pv_{pv.id}": 20.0,
            f"bkw_{bkw.id}": 5.0,
            f"waermepumpe_{wp.id}": -8.0,
            "haushalt": -12.0,
            "pv_999": 1.0,
        },
    ))
    # Tag außerhalb des Zeitraums mit einem nur hier vorkommenden Key.
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=date(2026, 4, 1),
        komponenten_kwh={f"pv_{pv.id}": 15.0, "netz": 3.0},
    ))
    await db.commit()
    return anlage.id


async def test_keys_werden_zu_serieninfo_aufgeloest(db):
    """Investitions- und virtuelle Keys bekommen Label, Kategorie und Seite."""
    anlage_id = await _seed(db)

    serien = await _call(anlage_id, date(2026, 5, 1), date(2026, 5, 31), db)
    by_key = {s.key: s for s in serien}

    # pv_999 hat keine Investition → verworfen, kein Crash.
    assert "pv_999" not in by_key

    pv = next(s for s in serien if s.kategorie == "pv" and s.key.startswith("pv_"))
    assert pv.label == "PV Dach"
    assert pv.seite == "quelle"

    bkw = next(s for s in serien if s.kategorie == "bkw")
    assert bkw.label == "BKW Süd"
    assert bkw.seite == "quelle"

    wp = next(s for s in serien if s.kategorie == "waermepumpe")
    assert wp.label == "WP Keller"
    assert wp.seite == "senke"

    haushalt = by_key["haushalt"]
    assert haushalt.label == "Haushalt"
    assert haushalt.typ == "virtual"


async def test_nur_keys_aus_zeitraum(db):
    """Der `netz`-Key existiert nur am 1.4. → bei Mai-Abfrage nicht enthalten."""
    anlage_id = await _seed(db)

    mai = await _call(anlage_id, date(2026, 5, 1), date(2026, 5, 31), db)
    assert all(s.key != "netz" for s in mai)

    april = await _call(anlage_id, date(2026, 4, 1), date(2026, 4, 30), db)
    assert any(s.key == "netz" for s in april)


async def test_unbekannte_anlage_404(db):
    """Nicht existierende Anlage liefert 404 statt leerer Liste."""
    with pytest.raises(HTTPException) as exc:
        await _call(99999, date(2026, 5, 1), date(2026, 5, 31), db)
    assert exc.value.status_code == 404
