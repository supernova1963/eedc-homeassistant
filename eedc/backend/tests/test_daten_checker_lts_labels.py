"""
Akzeptanztest: der LTS-Verfügbarkeits-Check nennt Labels, keine Mapping-Keys.

`_check_sensor_mapping_lts` setzte den Detailtext aus rohen Schlüsseln zusammen
(„Basis: einspeisung", „WR Süd: pv_erzeugung_kwh"). Roh-Keys in Anwendertexten
sind Drift ([[feedback_typ_labels_pattern]]); die SoT ist `FELD_LABELS`.

**Nicht Gegenstand dieser Datei — bewusst offen:** ob der Anlagen-Sammelzähler
`basis["pv_gesamt"]` mitgeprüft werden soll. Er wird zwar aus HA-LTS gelesen
(`aktueller_monat._ha_stats_monatswerte` → `pv_erzeugung_kwh`), ist aber der
Notstopfen für Wechselrichter ohne einzeln erfasste Strings; ob er zählt,
entscheidet die dreistufige Präzedenz in `pv_verteilung.resolve_pv_je_modul`
(Aggregat gilt, sobald AUCH NUR EIN aktives Modul keinen eigenen Wert hat).
Das gehört zusammen mit N51/DOK-9 in einen Zug (Backlog §F R4).
        eedc/backend/tests/test_daten_checker_lts_labels.py
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition  # noqa: F401


class _FakeHaStats:
    """HA-LTS-Doppel: alles verfügbar außer den explizit fehlenden IDs."""

    is_available = True

    def __init__(self, fehlend: set[str]):
        self._fehlend = fehlend

    def filter_valid_sensor_ids(self, sids):
        valid = [s for s in sids if s not in self._fehlend]
        missing = [s for s in sids if s in self._fehlend]
        return valid, missing


async def _seed(db: AsyncSession) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="WR Süd",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.flush()
    inv_id = next(
        i.id for i in (await db.execute(select(Investition))).scalars()
        if i.bezeichnung == "WR Süd"
    )
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.eins"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"},
        },
        "investitionen": {
            str(inv_id): {"felder": {
                "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"},
            }},
        },
    }
    await db.commit()
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_detailtext_nennt_labels_statt_roh_keys(db, monkeypatch):
    from backend.services.daten_checker import DatenChecker
    import backend.services.ha_statistics_service as ha_mod

    anlage = await _seed(db)
    monkeypatch.setattr(
        ha_mod, "get_ha_statistics_service",
        lambda: _FakeHaStats({"sensor.eins", "sensor.pv"}),
    )

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    details = " ".join(r.details or "" for r in ergebnisse)
    assert "Basis: Einspeisung" in details, f"Label erwartet, fand: {details!r}"
    # `FELD_LABELS["pv_erzeugung_kwh"]` == „Erzeugung" (Gerätename steht davor).
    assert "WR Süd: Erzeugung" in details, f"Label erwartet, fand: {details!r}"
    assert "Basis: einspeisung" not in details, "Roh-Mapping-Key im Anwendertext"
    assert "pv_erzeugung_kwh" not in details, "Roh-Feldname im Anwendertext"
