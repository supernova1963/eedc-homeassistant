"""N-740 — ein Netzfeld wird nur gestempelt, wenn ein Wert geliefert wurde.

**Der Defekt.** Zwei Schreiber stempelten ein Netzfeld der Monatszeile als geliefert, für das nichts geliefert war:
der HA-Statistik-Import legte eine neue Zeile an und bildete die Feldliste der Herkunft nach der **Feld-Auswahl**
(Einspeisung gewählt, aber kein Sensor ⇒ 0 mit ``external:ha_statistics``), der CSV-Backup-Restore machte aus einer
leeren Zelle ``or 0`` eine gestempelte 0 (``manual:csv_backup``; bei einer vorhandenen Zeile überschrieb er den Wert
mit dieser 0). Seit N-734 gilt nur eine 0 **mit** Herkunft als erfasst — der Checker «Einspeisung nicht erfasst», der
genau diese Lage melden soll, schwieg.

**Die Regel:** gestempelt wird, was geliefert wurde — wie der Update-Zweig des HA-Imports (``is not None``) und der
JSON-Restore. Eine neue Zeile behält die NOT-NULL-0 ohne Eintrag («nicht erfasst»).

Schwestern: ``test_n734_netzfeld_ohne_herkunft.py`` (die Regel «erfasst»), ``test_n538_csv_wege_ohne_schutzzaehler.py``
(CSV-Wege), ``test_n737_cloud_import_null_ist_wert.py`` (die Gegenrichtung: gelieferte 0 nicht verlieren).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.ha_statistics_import import _BasisWerte, _importiere_basis
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.monats_fakten import netzfeld_ist_erfasst
from backend.tests import factories

J, M = 2025, 7


async def _anlage(db) -> Anlage:
    a = await factories.anlage(db)
    await factories.strompreis(db, a.id, date(2024, 1, 1),
                               netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0)
    await factories.investition(db, a.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    await db.commit()
    return a


async def _md(db, aid: int) -> Monatsdaten:
    return (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == aid).execution_options(populate_existing=True)
    )).scalar_one()


async def _netz_meldungen(db, aid: int) -> list[str]:
    from backend.services.daten_checker import DatenChecker
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == aid)
    )).scalar_one()
    mds = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalars().all())
    erg = await DatenChecker(db)._check_monatsdaten_plausibilitaet(anlage, mds)
    return [f"{getattr(e.schwere, 'value', e.schwere)}|{e.meldung}" for e in erg if "nicht erfasst" in e.meldung]


def _netz_prov(md: Monatsdaten) -> dict:
    return {k: v.get("source") for k, v in (md.source_provenance or {}).items()
            if k in ("einspeisung_kwh", "netzbezug_kwh")}


# ── HA-Statistik-Import, Neuanlage ──────────────────────────────────────────────────────────────────────────────


async def test_ha_import_neuanlage_stempelt_nur_das_gelieferte_feld(db):
    a = await _anlage(db)
    await _importiere_basis(db, a.id, J, M, _BasisWerte(True, True, None, 250.0, None), False)
    await db.commit()
    md = await _md(db, a.id)

    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (0.0, 250.0)
    assert _netz_prov(md) == {"netzbezug_kwh": "external:ha_statistics"}, "vorher beide gestempelt"
    assert not netzfeld_ist_erfasst(md, "einspeisung_kwh")
    assert await _netz_meldungen(db, a.id) == ["error|07/2025: Einspeisung nicht erfasst"], "vorher []"


async def test_ha_import_neuanlage_gelieferte_null_bleibt_erfasst(db):
    a = await _anlage(db)
    await _importiere_basis(db, a.id, J, M, _BasisWerte(True, True, 0.0, 250.0, None), False)
    await db.commit()
    md = await _md(db, a.id)

    assert _netz_prov(md) == {"einspeisung_kwh": "external:ha_statistics", "netzbezug_kwh": "external:ha_statistics"}
    assert await _netz_meldungen(db, a.id) == []


# ── CSV-Backup-Restore ──────────────────────────────────────────────────────────────────────────────────────────


class _Upload:
    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


async def _csv_restore(db, aid: int, es: str, nb: str = "300") -> Monatsdaten:
    from backend.api.routes.import_export.csv_operations import import_csv
    text = f"Jahr;Monat;Einspeisung_kWh;Netzbezug_kWh\n{J};{M};{es};{nb}\n"
    r = await import_csv(anlage_id=aid, file=_Upload(text), ueberschreiben=True, auto_wetter=False, db=db)
    assert r.erfolg, r.fehler
    await db.commit()
    return await _md(db, aid)


async def test_csv_leere_zelle_bekommt_keinen_stempel(db):
    a = await _anlage(db)
    md = await _csv_restore(db, a.id, "")

    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (0.0, 300.0), "die Spalte ist NOT NULL — 0 bleibt stehen"
    assert _netz_prov(md) == {"netzbezug_kwh": "manual:csv_backup"}, "vorher beide gestempelt"
    assert await _netz_meldungen(db, a.id) == ["error|07/2025: Einspeisung nicht erfasst"]


async def test_csv_null_in_der_zelle_ist_ein_wert(db):
    a = await _anlage(db)
    md = await _csv_restore(db, a.id, "0")

    assert _netz_prov(md) == {"einspeisung_kwh": "manual:csv_backup", "netzbezug_kwh": "manual:csv_backup"}
    assert await _netz_meldungen(db, a.id) == []


async def test_csv_leere_zelle_ueberschreibt_vorhandenen_wert_nicht(db):
    a = await _anlage(db)
    await _csv_restore(db, a.id, "180")
    md = await _csv_restore(db, a.id, "", nb="320")

    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (180.0, 320.0), "vorher wurde die 180 durch eine gestempelte 0 ersetzt"
