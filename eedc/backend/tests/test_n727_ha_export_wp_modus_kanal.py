"""N-727 — HA-Export: WP-Strom je Betriebsart aus derselben Quelle wie die Monats-Fakten (abgeleiteter Kanal, E4d).

**Der Fund.** `ha_export/investition_sensoren.py::_wp_nachtrag` trug den Split der Monate ohne gespeicherte Aufteilung
nur aus der Tagesebene nach (`lade_modus_split_ohne_abschluss` ohne Kanal). Die Monats-Fakten nehmen seit E4d für
Monate, deren WP-Gruppe die Kanäle decken, den abgeleiteten Kanal «Strom je Betriebsart» (`kanal_split_ohne_abschluss`,
`monats_fakten/laden.py::_ergaenze_modus_split_ohne_abschluss`). Form M05 (WP mit Gesamtzähler, Betriebsart als
Etikett, ohne Leistungssensor) — die Tagesebene kennt dort keinen Split, nur der Kanal. Gemessen am HEAD `7fb9b026`
(Abnahme-Matrix-Bausteine, HA-Weg):

| Weg | HA-Sensoren Heizen / Warmwasser | Monats-Fakten / Cockpit → Übersicht |
| --- | --- | --- |
| S2 (Juni per HA-Statistik-Sammelimport) | **0 / 0** | 217,8 / 19,8 |
| S1 (Juni über «Aus HA laden», Abschluss schreibt den Split) | **198 / 18** (der laufende Juli fehlt) | 217,8 / 19,8 |

Soll: der HA-Export trägt dieselben Mengen wie die Übersicht (217,8 / 19,8 = Juni 198/18 + Juli 19,8/1,8).

Schwesterdateien: test_achsen_matrix.py (M05-Zellen `modus_*:uebersicht`), test_kanal_wp_gleichheit.py.
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx


async def _messe(weg: str) -> dict:
    form = am.FORMEN["M05"]
    verz = tempfile.mkdtemp(prefix="eedc-n727-")
    try:
        engine, db = await mx._neue_db(f"{verz}/ha.db")
        svc = am.seed_ha(form)
        try:
            aid, ids = await am.seed_anlage(db, form)
            with am.umgebung(form, svc):
                await mx.fuelle_spiegel(engine, aid, svc)
                await mx.aggregiere_tage(db, form.pvform, aid, am.TAGE_JUNI + am.TAGE_JULI)
                await mx.baue_abgeleitete_nach_tagen(engine, aid)
                if weg == "S1":
                    await am.schreibe_s1_aus_ha_laden(db, form, aid)
                else:
                    await mx.schreibe_s2_sammelimport(db, aid)
                ha = await am.miss_ha_export(db, aid, ids)
                ue = await am.miss_uebersicht(db, aid)
            return {"ha": ha["inv"]["WP"], "uebersicht": ue}
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("weg", ["S2", "S1"])
async def test_ha_sensoren_je_betriebsart_wie_die_uebersicht(weg):
    m = await _messe(weg)
    ha = m["ha"]
    assert ha.get("wp_strom_heizen_modus_kwh") == pytest.approx(217.8), ha
    assert ha.get("wp_strom_warmwasser_modus_kwh") == pytest.approx(19.8), ha
