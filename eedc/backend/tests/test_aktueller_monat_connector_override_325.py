"""
Regressionstest #325 (detlefh68): Connector überschreibt gespeicherte
Monatswerte für ABGESCHLOSSENE Monate nicht.

Symptom: Monatsbericht für einen abgeschlossenen Mai zeigte Einspeisung 0,
obwohl die Monatsdaten-Tabelle (= `Monatsdaten.einspeisung_kwh` direkt) 1.411
enthielt. Ursache: in `get_aktueller_monat` lief `resolved.update(connector)`
bedingungslos NACH `resolved.update(saved)` — ein Connector ohne separate
Einspeisungs-Messung (z. B. Sungrow) lieferte 0 und überschrieb damit den
gespeicherten Wert. Die #118-Schutzlogik (für vergangene Monate ist
*gespeichert* authoritativ) galt nur für HA-Stats, nicht für den Connector.

Fix: Connector für vergangene/abgeschlossene Monate ebenfalls nur als
`setdefault`-Fallback, nicht als Override.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Monatsdaten, Strompreis


async def _seed(db: AsyncSession, *, jahr: int, monat: int, einspeisung: float) -> int:
    anlage = Anlage(anlagenname="Test325", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=jahr, monat=monat,
        netzbezug_kwh=8.0, einspeisung_kwh=einspeisung,
    ))
    await db.commit()
    return anlage.id


async def test_connector_ueberschreibt_gespeicherte_einspeisung_im_abgeschlossenen_monat_nicht(
    db: AsyncSession, monkeypatch
):
    """Vergangener Monat: gespeicherte Einspeisung (1411) bleibt, obwohl der
    Connector 0 liefert (#325)."""
    import backend.api.routes.aktueller_monat as am

    # Abgeschlossener Monat (sicher in der Vergangenheit relativ zu jedem Lauf).
    jahr, monat = 2024, 4
    anlage_id = await _seed(db, jahr=jahr, monat=monat, einspeisung=1411.0)

    # Connector liefert eine Einspeisung von 0 (kein separater Einspeise-Zähler).
    async def _fake_connector(anlage, j, m):
        return {
            "einspeisung_kwh": (0.0, am.DatenquelleInfo(quelle="local_connector", konfidenz=90)),
        }

    # Kein HA im Test.
    async def _fake_ha_stats(anlage, j, m):
        return {}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    result = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=jahr, monat=monat, db=db)

    assert result.einspeisung_kwh == 1411.0, (
        f"Gespeicherte Einspeisung wurde vom Connector überschrieben "
        f"(war {result.einspeisung_kwh}, erwartet 1411) — Regression #325"
    )
