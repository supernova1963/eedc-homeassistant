"""Tagesprognose, Rückfallpfad: ein Erzeuger, der am Zieltag noch nicht angeschafft ist, zählt nicht mit.

``api/routes/energie_profil/prognose.py::get_tagesprognose`` fällt auf einen eigenen OpenMeteo-Abruf je
Orientierungsgruppe zurück, wenn der Kanon nichts liefert. Dieser Pfad prüfte bis 04.10.2026 nur die
Stilllegung, nicht die Anschaffung (Klassen-Abschluss „Selektor vor Zeitfilter", D1 #29): ein String mit
Anschaffung nach dem Zieltag ging schon mit seiner kWp in die Prognose ein. Jetzt ``ist_aktiv_an(datum)``
wie der Kanon. Gemessen über den Einstieg mit gestellter Wetterprognose: Gruppen 6 + 4 kWp → 6 kWp.

Schwesterdateien: test_n614_selektor_nach_zeitfilter_co2_kanon.py (Zeitfilter vor dem Selektor im Kanon),
test_wurzelmuster_p1_orientierung.py (Orientierungsgruppen der Prognose).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import Anlage, Investition

# Fester Zieltag: die Route bekommt ihn übergeben; ihre eigene Uhr bestimmt nur, wie viele Tage der
# (hier gestellte) Wetterabruf umfasst — die echte Uhr gehört nicht in die Probe.
ZIEL = date(2030, 6, 15)


async def _kwp_je_gruppe(db, west_ab: date | None) -> list[float]:
    from backend.api.routes.energie_profil import prognose as P

    ziel = ZIEL
    a = Anlage(anlagenname="Rückfall", leistung_kwp=10.0, latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0, ausrichtung="Süd",
                       neigung_grad=30, anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1.0))
    if west_ab is not None:
        db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0, ausrichtung="West",
                           neigung_grad=30, anschaffungsdatum=west_ab, anschaffungskosten_gesamt=1.0))
    await db.commit()
    aufrufe: list[float] = []

    async def _wetter(**kw):
        aufrufe.append(round(kw["kwp"], 2))
        return SimpleNamespace(tageswerte=[SimpleNamespace(datum=ziel.isoformat(), stunden_kw=[0.1] * 24)])

    with patch.object(P, "_pv_stunden_aus_kanon", new=AsyncMock(return_value=None)), \
         patch("backend.services.solar_forecast_service.get_solar_prognose", new=_wetter), \
         patch("backend.services.verbrauch_prognose_service.get_verbrauch_prognose", new=AsyncMock(return_value=None)):
        await P.get_tagesprognose(anlage_id=a.id, datum=ziel, db=db)
    return sorted(aufrufe)


@pytest.mark.asyncio
async def test_kuenftiger_string_zaehlt_nicht(db):
    assert await _kwp_je_gruppe(db, ZIEL + timedelta(days=5)) == [6.0]


@pytest.mark.asyncio
async def test_am_zieltag_vorhandener_string_zaehlt(db):
    """Gegenprobe: angeschafft vor dem Zieltag ⇒ zwei Gruppen wie bisher."""
    assert await _kwp_je_gruppe(db, ZIEL - timedelta(days=4)) == [4.0, 6.0]
