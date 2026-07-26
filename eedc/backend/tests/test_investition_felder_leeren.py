"""Optionale Investitions-Felder müssen sich wieder leeren lassen.

Anlass (JayJay, Forum v4.0.0): Ein AC-Speicher wurde einem Wechselrichter
zugeordnet — und ließ sich danach nicht mehr trennen. Ursache war das Zusammen-
spiel aus Frontend (`undefined` → Schlüssel fällt aus dem JSON) und Backend
(`model_dump(exclude_unset=True)` → weggelassener Schlüssel bleibt unverändert).

Diese Tests pinnen die Backend-Hälfte: ein explizit gesendetes `null` MUSS das
Feld leeren, ein weggelassenes Feld MUSS den Altwert behalten. Beides zusammen
ist der Vertrag, auf den sich das Formular verlässt.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen.crud import (
    InvestitionUpdate,
    update_investition,
)
from backend.models import Anlage, Investition


async def _seed(db) -> tuple[int, int]:
    """Anlage mit Wechselrichter + zugeordnetem Speicher. Gibt (speicher_id, wr_id)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Hybrid-WR",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wr)
    await db.flush()
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="AC-Speicher",
        parent_investition_id=wr.id, anschaffungsdatum=date(2024, 6, 1),
        parameter={"kapazitaet_kwh": 10.0},
    )
    db.add(speicher)
    await db.flush()
    return speicher.id, wr.id


async def test_parent_zuordnung_laesst_sich_loesen(db):
    """`parent_investition_id: null` trennt den Speicher wieder vom Wechselrichter."""
    speicher_id, _ = await _seed(db)
    await db.commit()

    inv = await update_investition(
        investition_id=speicher_id,
        data=InvestitionUpdate(parent_investition_id=None),
        db=db,
    )

    assert inv.parent_investition_id is None


async def test_anschaffungsdatum_laesst_sich_leeren(db):
    speicher_id, _ = await _seed(db)
    await db.commit()

    inv = await update_investition(
        investition_id=speicher_id,
        data=InvestitionUpdate(anschaffungsdatum=None),
        db=db,
    )

    assert inv.anschaffungsdatum is None


async def test_nicht_gesendete_felder_bleiben_unveraendert(db):
    """Die Kehrseite des Vertrags: ein weggelassenes Feld darf nichts anfassen."""
    speicher_id, wr_id = await _seed(db)
    await db.commit()

    inv = await update_investition(
        investition_id=speicher_id,
        data=InvestitionUpdate(bezeichnung="Neuer Name"),
        db=db,
    )

    assert inv.bezeichnung == "Neuer Name"
    assert inv.parent_investition_id == wr_id
    assert inv.anschaffungsdatum == date(2024, 6, 1)
