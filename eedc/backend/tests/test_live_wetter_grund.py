"""Live-Wetter: `grund` bei !verfuegbar — keine schuld-umkehrende Meldung.

rapahl-PN 2026-06-05: Die Live-Wetteransicht zeigte „Keine Wetterdaten verfügbar
— Standort-Koordinaten in den Stammdaten hinterlegen", obwohl die Koordinaten
gesetzt waren (Prognosen liefen). Ursache war ein Backend-Abruf-/Cache-Fehler
(Negativ-Cache, vgl. `5a5158c2`), KEINE fehlende Konfiguration. Der Endpoint
liefert jetzt einen `grund`, damit das Frontend ehrlich unterscheidet
([[feedback_user_fehlermeldungen]]: Backend beobachtbar machen statt Schuld umkehren).
"""

from __future__ import annotations

import pytest

from backend.api.routes import live_wetter
from backend.api.routes.live_wetter import get_live_wetter
from backend.models import Anlage


async def test_grund_keine_koordinaten_wenn_stammdaten_luecke(db):
    """Ohne lat/lon: verfuegbar=False, grund='keine_koordinaten' (echte Lücke)."""
    anlage = Anlage(anlagenname="OhneKoord", leistung_kwp=10.0, latitude=None, longitude=None)
    db.add(anlage)
    await db.flush()

    res = await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)
    assert res["verfuegbar"] is False
    assert res["grund"] == "keine_koordinaten"


async def test_grund_abruf_fehlgeschlagen_bei_negativ_cache(db, monkeypatch):
    """Koordinaten vorhanden, aber Abruf vorher fehlgeschlagen (Negativ-Cache):
    verfuegbar=False, grund='abruf_fehlgeschlagen' — NICHT 'keine_koordinaten'.
    So zeigt das Frontend „vorübergehend gestört" statt Konfigurations-Schuld."""
    anlage = Anlage(anlagenname="MitKoord", leistung_kwp=10.0, latitude=48.1, longitude=11.6)
    db.add(anlage)
    await db.flush()

    # Cache leer, aber Negativ-Cache-Treffer → Abruf-Fehler-Pfad ohne echten HTTP-Call.
    monkeypatch.setattr(live_wetter, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(live_wetter, "_error_cache_check", lambda *a, **k: True)

    res = await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)
    assert res["verfuegbar"] is False
    assert res["grund"] == "abruf_fehlgeschlagen"
