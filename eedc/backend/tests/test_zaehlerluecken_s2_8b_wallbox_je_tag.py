"""S2-8b (Mitnahme aus N-555 Stufe 2, Bau „Zählerlücken wie HA"): der LTS-Tagesverlauf
entscheidet „Wallbox in Betrieb" **je Tag**, nicht einmal für die ganze Range.

Konzept Heimladung Regel 0: „im betrachteten Monat oder Tag". Eine Wallbox,
die am 10.05. angeschafft wurde, verdrängt die E-Auto-Serie ab dem 10.05. —
davor lädt das Auto (eigener Leistungssensor) und seine Kurve gehört in den
Tagesverlauf. Bis 26.09.2026 lief die Auswahl ohne ``tag`` über die ganze
Range: die E-Auto-Serie fehlte auch an den Tagen vor der Anschaffung.

Schwesterdateien: test_serien_aufbau_symmetrie_m1.py (die geteilte Auswahl
``baue_investitions_serien`` samt „Wallbox verdrängt E-Auto"),
test_reparatur_lts_reichweite.py (derselbe Leser ``lade_tagesverlauf_aus_lts``).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from backend.models import Anlage, Investition
from backend.services.energie_profil.lts_tagesverlauf import lade_tagesverlauf_aus_lts

VOR, AB = date(2026, 5, 9), date(2026, 5, 10)


class _Ha:
    is_available = True

    def get_hourly_sensor_data(self, eids, von, bis):
        tage = {}
        d = von
        from datetime import timedelta
        while d <= bis:
            tage[d.isoformat()] = {h: 2000.0 for h in range(24)}
            d += timedelta(days=1)
        return {eid: {k: dict(v) for k, v in tage.items()} for eid in eids}


@pytest.mark.asyncio
async def test_wallbox_verdraengt_das_auto_erst_ab_ihrer_anschaffung(db):
    a = Anlage(anlagenname="S2-8b", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    auto = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                       anschaffungsdatum=date(2025, 1, 1))
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=AB)
    db.add_all([auto, wb])
    await db.flush()
    a.sensor_mapping = {"basis": {}, "investitionen": {
        str(auto.id): {"live": {"leistung_w": "sensor.auto_w"}},
        str(wb.id): {"live": {"leistung_w": "sensor.wb_w"}},
    }}
    await db.commit()

    with patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=_Ha()):
        erg = await lade_tagesverlauf_aus_lts(db, a, VOR, AB)

    assert erg.tage, erg.grund
    keys = {d: {s["key"] for s in erg.tage[d]["serien"]} for d in (VOR, AB)}
    assert keys[VOR] == {f"eauto_{auto.id}"}          # vor der Anschaffung: das Auto
    assert keys[AB] == {f"wallbox_{wb.id}"}           # ab der Anschaffung: die Wallbox
    werte_vor = {k for p in erg.tage[VOR]["punkte"] for k in p["werte"]}
    assert f"eauto_{auto.id}" in werte_vor            # die Kurve des Autos ist da
