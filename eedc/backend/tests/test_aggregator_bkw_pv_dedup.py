"""Akzeptanztest: BKW-Doppelzählung in komponenten_kwh (Rainer-PN 2026-05-19).

Bug: TV_SERIE_CONFIG["balkonkraftwerk"]["kategorie"] = "pv" lässt den
Live-Tagesverlauf-Service BKW-Energie unter Key `pv_<inv_id>` akkumulieren.
Der Boundary-Aggregator (LTS/Snapshot) nutzt dagegen `bkw_<inv_id>`. Ohne
Dedup-Schutz bleiben beide Keys nebeneinander in `komponenten_kwh`, und alle
Konsumenten mit Prefix-Whitelist `("pv_", "bkw_")` (prognosen.py-IST,
daten_checker._summe_pv_bkw_kwh, energie_profil/repair._pv_tagessumme)
zählen das BKW doppelt.

Bei einer Anlage mit ~1,5 kWh BKW-Ertrag/Tag entsteht so systematisch
~+1,5 kWh IST-Aufschlag — bei Rainer ~+5-8 % Bias gegenüber Solcast.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.daten_checker import _summe_pv_bkw_kwh
from backend.services.energie_profil.aggregator import aggregate_day


async def _seed_anlage_pv_und_bkw(db) -> tuple[Anlage, int, int]:
    """Anlage mit einem PV-Modul und einem BKW + minimalem Sensor-Mapping."""
    anlage = Anlage(anlagenname="Rainer-Test", leistung_kwp=7.0)
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="String West",
    )
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW Terasse",
    )
    db.add_all([pv, bkw])
    await db.flush()

    anlage.sensor_mapping = {
        "basis": {
            "live": {"pv_gesamt_w": "sensor.x"},  # nicht-leer → has_inv-Pfad
        },
        "investitionen": {
            str(pv.id): {
                "live": {"leistung_w": "sensor.pv_w"},
                "felder": {
                    "pv_erzeugung_kwh": {
                        "strategie": "sensor", "sensor_id": "sensor.pv_kwh",
                    },
                },
            },
            str(bkw.id): {
                "live": {"leistung_w": "sensor.bkw_w"},
                "felder": {
                    "pv_erzeugung_kwh": {
                        "strategie": "sensor", "sensor_id": "sensor.bkw_kwh",
                    },
                },
            },
        },
    }
    await db.commit()
    return anlage, pv.id, bkw.id


async def test_bkw_doppelzaehlung_in_komponenten_kwh_verhindert(db):
    """Live-Σ-Riemann unter `pv_<bkw_id>` darf nicht neben Boundary
    `bkw_<bkw_id>` überleben."""
    anlage, pv_id, bkw_id = await _seed_anlage_pv_und_bkw(db)
    datum = date(2026, 5, 18)

    # Live-Tagesverlauf-Service liefert pro Stunde Leistungs-Werte unter
    # Live-Service-Keys: pv_<pv_id> für PV-Modul, pv_<bkw_id> für BKW (BUG:
    # TV_SERIE_CONFIG mappt balkonkraftwerk auch auf Kategorie "pv").
    tv_data = {
        "serien": [
            {"key": f"pv_{pv_id}", "kategorie": "pv"},
            {"key": f"pv_{bkw_id}", "kategorie": "pv"},
        ],
        "punkte": [
            {"zeit": f"{h:02d}:00", "werte": {
                f"pv_{pv_id}": 3.0 if 8 <= h <= 18 else 0.0,
                f"pv_{bkw_id}": 0.5 if 13 <= h <= 16 else 0.0,
            }} for h in range(24)
        ],
    }
    live_service = MagicMock()
    live_service.get_tagesverlauf = AsyncMock(return_value=tv_data)

    # Boundary (HA-LTS) liefert getrennte Keys: pv_<pv_id> und bkw_<bkw_id>.
    # Der bkw-Key überschreibt aber NICHT den pv_<bkw_id>-Live-Key — der Fix
    # in aggregator.py muss diesen verwaisten pv_<bkw_id> droppen.
    boundary = {f"pv_{pv_id}": 30.0, f"bkw_{bkw_id}": 1.8}

    with (
        patch(
            "backend.services.live_power_service.get_live_power_service",
            return_value=live_service,
        ),
        patch(
            "backend.services.energie_profil._helpers._tage_zurueck",
            return_value=1,
        ),
        patch(
            "backend.services.energie_profil._helpers._get_wetter_ist",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "backend.services.energie_profil._helpers._get_soc_history",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "backend.services.energie_profil._helpers._get_strompreis_stunden",
            new=AsyncMock(return_value=type("SP", (), {
                "sensor": {}, "boerse": {},
            })()),
        ),
        patch(
            "backend.services.energie_profil._helpers._get_tagespeaks_aus_ha_lts",
            new=AsyncMock(return_value=type("P", (), {
                "pv": None, "netzbezug": None, "einspeisung": None,
            })()),
        ),
        patch(
            "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
            new=AsyncMock(return_value={h: {"pv": 1.0} for h in range(8, 19)}),
        ),
        patch(
            "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
            new=AsyncMock(return_value=boundary),
        ),
        patch(
            "backend.services.sensor_snapshot_service.get_hourly_kwh_by_category",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "backend.services.sensor_snapshot_service.get_hourly_counter_sum_by_feld",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
            new=AsyncMock(return_value={}),
        ),
    ):
        result = await aggregate_day(anlage, datum, db, datenquelle="manuell")
        await db.commit()

    assert result is not None, "Aggregator muss bei vorhandenen Daten eine TZ liefern"

    tz = (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == datum,
        )
    )).scalar_one()

    kk = tz.komponenten_kwh or {}

    # Kernassertion: pv_<bkw_id> (Live-Σ) muss gedroppt sein, weil
    # bkw_<bkw_id> (Boundary) vorhanden ist.
    assert f"pv_{bkw_id}" not in kk, (
        f"pv_{bkw_id} (Live-Σ vom BKW) hätte gedroppt sein müssen, "
        f"weil bkw_{bkw_id} vom Boundary-Pfad existiert. komponenten_kwh={kk}"
    )

    # Echte PV bleibt unangetastet
    assert kk.get(f"pv_{pv_id}") == 30.0, (
        f"pv_{pv_id} (echtes PV-Modul) muss Boundary-Wert 30.0 haben, "
        f"bekommen: {kk.get(f'pv_{pv_id}')}"
    )

    # BKW-Boundary bleibt
    assert kk.get(f"bkw_{bkw_id}") == 1.8, (
        f"bkw_{bkw_id} muss Boundary-Wert 1.8 haben, "
        f"bekommen: {kk.get(f'bkw_{bkw_id}')}"
    )

    # Konsumenten-Sicht: Σ PV+BKW = 31.8 (nicht 33.6 wie pre-Fix)
    summe = _summe_pv_bkw_kwh(kk)
    assert summe == 31.8, (
        f"_summe_pv_bkw_kwh muss 31.8 sein (30.0 PV + 1.8 BKW), bekommen: {summe}. "
        f"Wäre 33.6 → BKW würde immer noch doppelt zählen."
    )


async def test_kein_drop_wenn_kein_boundary_bkw_key(db):
    """Wenn der Boundary-Pfad für BKW NICHTS liefert (z.B. HA-LTS leer),
    bleibt der Live-Σ-Wert unter pv_<bkw_id> erhalten — sonst verlieren
    wir die einzige Datenspur für den Tag. Defensiv: Drop nur bei
    Co-Existenz beider Keys."""
    anlage, pv_id, bkw_id = await _seed_anlage_pv_und_bkw(db)
    datum = date(2026, 5, 18)

    tv_data = {
        "serien": [
            {"key": f"pv_{pv_id}", "kategorie": "pv"},
            {"key": f"pv_{bkw_id}", "kategorie": "pv"},
        ],
        "punkte": [
            {"zeit": f"{h:02d}:00", "werte": {
                f"pv_{pv_id}": 3.0 if 8 <= h <= 18 else 0.0,
                f"pv_{bkw_id}": 0.5 if 13 <= h <= 16 else 0.0,
            }} for h in range(24)
        ],
    }
    live_service = MagicMock()
    live_service.get_tagesverlauf = AsyncMock(return_value=tv_data)

    # Boundary liefert NUR pv_<pv_id>, kein bkw-Key
    boundary = {f"pv_{pv_id}": 30.0}

    with (
        patch(
            "backend.services.live_power_service.get_live_power_service",
            return_value=live_service,
        ),
        patch("backend.services.energie_profil._helpers._tage_zurueck", return_value=1),
        patch("backend.services.energie_profil._helpers._get_wetter_ist",
              new=AsyncMock(return_value={})),
        patch("backend.services.energie_profil._helpers._get_soc_history",
              new=AsyncMock(return_value={})),
        patch("backend.services.energie_profil._helpers._get_strompreis_stunden",
              new=AsyncMock(return_value=type("SP", (), {"sensor": {}, "boerse": {}})())),
        patch("backend.services.energie_profil._helpers._get_tagespeaks_aus_ha_lts",
              new=AsyncMock(return_value=type("P", (), {
                  "pv": None, "netzbezug": None, "einspeisung": None,
              })())),
        patch("backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
              new=AsyncMock(return_value={})),
        patch("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
              new=AsyncMock(return_value=boundary)),
        patch("backend.services.sensor_snapshot_service.get_hourly_kwh_by_category",
              new=AsyncMock(return_value={})),
        patch("backend.services.sensor_snapshot_service.get_hourly_counter_sum_by_feld",
              new=AsyncMock(return_value={})),
        patch("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
              new=AsyncMock(return_value={})),
    ):
        await aggregate_day(anlage, datum, db, datenquelle="manuell")
        await db.commit()

    tz = (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == datum,
        )
    )).scalar_one()

    kk = tz.komponenten_kwh or {}
    # Live-Σ-Wert bleibt — keine Datenverlust-Falle
    assert f"pv_{bkw_id}" in kk, (
        f"Bei fehlendem Boundary-BKW-Key darf der Live-Σ-Eintrag NICHT gedroppt "
        f"werden — sonst verlieren wir die einzige Datenspur. komponenten_kwh={kk}"
    )
