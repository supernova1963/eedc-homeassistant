"""Die Schreibpfade sagen, dass sie gerechnet haben (#352).

Vier Einstiegspunkte persistieren eine Zerlegung: der Legacy-PV- und der
Speicher-Verteiler (aus CSV-Backup, Portal-Import und Custom-Import) sowie der
Monatsabschluss, wenn der Anwender den zerlegten Connector-/Cloud-Vorschlag
übernimmt. Vor diesem Paket trugen alle vier dieselbe Provenance wie eine
Gerätemessung — beim CSV-Backup sogar buchstäblich dieselbe
(`manual:csv_backup` / `csv_backup_restore` für echte Pro-Modul-Spalten *und*
für die Verteilung).

Grenze, bewusst und an beiden Enden gleich: bei genau **einem** Empfänger geht
der Gesamtwert unverzerrt dorthin. Das ist eine Messung und bleibt als solche
etikettiert (gleiche Regel wie `ist_verteilt` im Monatsabschluss).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from backend.api.routes.import_export.helpers import (
    _distribute_legacy_battery_to_storages,
    _distribute_legacy_pv_to_modules,
)
from backend.api.routes.monatsdaten import _save_investitionen_monatsdaten
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.services.provenance import (
    ABGELEITET_KAPAZITAET_ANTEIL,
    ABGELEITET_KWP_ANTEIL,
)

_PV_KEY = "verbrauch_daten.pv_erzeugung_kwh"


async def _anlage_mit_modulen(db, kwps: list[float], typ="pv-module") -> tuple[Anlage, list[Investition]]:
    anlage = Anlage(anlagenname="Verteiler", leistung_kwp=sum(kwps) or 1.0)
    db.add(anlage)
    await db.flush()
    invs = []
    for i, kwp in enumerate(kwps):
        inv = Investition(
            anlage_id=anlage.id, typ=typ, bezeichnung=f"Modul {i + 1}",
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=kwp,
            parameter={"kapazitaet_kwh": kwp} if typ == "speicher" else None,
        )
        db.add(inv)
        invs.append(inv)
    await db.flush()
    return anlage, invs


async def _prov(db, inv_id: int, key: str = _PV_KEY) -> dict:
    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv_id
        )
    )).scalar_one()
    return (imd.source_provenance or {}).get(key, {})


async def test_legacy_pv_verteilung_wird_als_gerechnet_gebucht(db):
    _anlage, module = await _anlage_mit_modulen(db, [6.0, 4.0])
    await _distribute_legacy_pv_to_modules(
        db, 1000.0, module, 2026, 5, False,
        source="manual:csv_backup", writer="csv_backup_restore",
    )
    await db.commit()
    for inv in module:
        assert (await _prov(db, inv.id)).get("abgeleitet") == ABGELEITET_KWP_ANTEIL


async def test_ein_einziges_modul_bleibt_messung(db):
    """Gegenprobe zur Grenze: kein Empfänger-Wettbewerb, keine Zerlegung."""
    _anlage, module = await _anlage_mit_modulen(db, [10.0])
    await _distribute_legacy_pv_to_modules(
        db, 1000.0, module, 2026, 5, False,
        source="manual:csv_backup", writer="csv_backup_restore",
    )
    await db.commit()
    assert "abgeleitet" not in (await _prov(db, module[0].id))


async def test_speicher_verteilung_traegt_die_kapazitaets_marke(db):
    _anlage, speicher = await _anlage_mit_modulen(db, [10.0, 5.0], typ="speicher")
    await _distribute_legacy_battery_to_storages(
        db, 600.0, 500.0, speicher, 2026, 5, False,
        source="manual:csv_backup", writer="csv_backup_restore",
    )
    await db.commit()
    for inv in speicher:
        eintrag = await _prov(db, inv.id, "verbrauch_daten.ladung_kwh")
        assert eintrag.get("abgeleitet") == ABGELEITET_KAPAZITAET_ANTEIL


async def test_monatsdaten_pfad_nimmt_die_marke_des_clients(db):
    """Der laufende Pfad: der V4-Monatsabschluss speichert über /monatsdaten."""
    _anlage, module = await _anlage_mit_modulen(db, [6.0, 4.0])
    await db.commit()
    await _save_investitionen_monatsdaten(
        db,
        {
            str(module[0].id): {
                "pv_erzeugung_kwh": 600.0,
                "abgeleitet_felder": {"pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL},
            },
        },
        2026, 5,
    )
    await db.commit()
    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == module[0].id
        )
    )).scalar_one()
    # Der Marker ist Metadatum, kein Messwert — er darf nicht im Nutz-Dict landen.
    assert imd.verbrauch_daten == {"pv_erzeugung_kwh": 600.0}
    assert imd.source_provenance[_PV_KEY]["abgeleitet"] == ABGELEITET_KWP_ANTEIL


async def test_monatsdaten_pfad_verwirft_unbekannte_marke(db):
    """Ein Versionsversatz darf keine Ableitung erfinden, die niemand liest."""
    _anlage, module = await _anlage_mit_modulen(db, [6.0, 4.0])
    await db.commit()
    await _save_investitionen_monatsdaten(
        db,
        {
            str(module[0].id): {
                "pv_erzeugung_kwh": 600.0,
                "abgeleitet_felder": {"pv_erzeugung_kwh": "nach_gefuehl"},
            },
        },
        2026, 5,
    )
    await db.commit()
    assert "abgeleitet" not in (await _prov(db, module[0].id))


async def test_monatsdaten_pfad_aktualisiert_bestehende_zeile(db):
    """Zweiter Speichervorgang auf derselben Zeile — UPDATE-Zweig statt INSERT."""
    _anlage, module = await _anlage_mit_modulen(db, [6.0, 4.0])
    db.add(InvestitionMonatsdaten(
        investition_id=module[0].id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 111.0},
    ))
    await db.commit()
    await _save_investitionen_monatsdaten(
        db,
        {
            str(module[0].id): {
                "pv_erzeugung_kwh": 600.0,
                "abgeleitet_felder": {"pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL},
            },
        },
        2026, 5,
    )
    await db.commit()
    assert (await _prov(db, module[0].id)).get("abgeleitet") == ABGELEITET_KWP_ANTEIL
