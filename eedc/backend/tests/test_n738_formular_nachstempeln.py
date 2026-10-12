"""N-738 — Formular-Neuanlagen seit 09.05.2026 bekommen ihren `manual:form`-Stempel der Netzfelder nach.

**Der Defekt.** Bis N-735 verwarf ``create_monatsdaten`` die geseedete Herkunft (``refresh`` ohne ``flush``, seit
``e527bfe8``). Solche Zeilen stehen mit ``datenquelle IS NULL`` und ohne Eintrag für Einspeisung/Netzbezug da:
ohne Stufe-1-Schutz (HA-Statistik-Import mit Haken ersetzte 180/250 still durch 999/888) und — seit N-734 — mit einer
eingetragenen 0, die als «nicht erfasst» galt (Cockpit leer, Checker-ERROR). N-735 heilte nur Neuanlagen.

**Die Migration** (``services/provenance_migrate.py::migrate_n738_formular_neuanlage_nachstempeln``, einmal über
``_apply_once("n735_formular_neuanlage_nachstempeln")``): je Zeile mit ``datenquelle IS NULL`` und fehlendem
Netzfeld-Eintrag ``manual:form`` — das Formular verlangt beide Netzfelder, der Wert ist der gesendete. **Ausgenommen**
Zeilen des alten Monatsabschluss-Assistenten (Writer ``monatsabschluss_wizard``): er legt Zeilen ebenfalls ohne
``datenquelle`` an, liefert ein leeres Netzfeld aber nicht — eine 0 ohne Eintrag ist dort nicht geliefert.

Schwestern: ``test_n735_formular_neuanlage_provenance.py`` (der Fix für Neuanlagen), ``test_n734_netzfeld_ohne_herkunft.py``.
"""

from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.models import Monatsdaten
from backend.services.provenance import seed_provenance
from backend.services.provenance_migrate import migrate_n738_formular_neuanlage_nachstempeln
from backend.tests.test_n734_netzfeld_ohne_herkunft import J, M, _anlage, _checker, _monat, _netz_meldungen

NETZ = ("einspeisung_kwh", "netzbezug_kwh")


async def _md(db, aid: int) -> Monatsdaten:
    return (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == aid).execution_options(populate_existing=True)
    )).scalar_one()


def _prov(md) -> dict:
    return {k: v.get("source") for k, v in (md.source_provenance or {}).items() if k in NETZ}


async def _f1_zeile(db, aid: int, **werte) -> Monatsdaten:
    """Der Create-Weg vor N-735 nachgestellt: geseedet, dann `refresh` ohne `flush` — die Herkunft ist weg."""
    md = Monatsdaten(anlage_id=aid, jahr=J, monat=M, **werte)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="monatsdaten_form", fields=list(werte))
    await db.refresh(md)
    await db.commit()
    md = await _md(db, aid)
    assert _prov(md) == {}, "Lage wie im Fund"
    return md


async def _ha_import_mit_haken(db, aid: int, es: float, nb: float) -> None:
    from backend.api.routes.ha_statistics_import import _BasisWerte, _importiere_basis
    await _importiere_basis(db, aid, J, M, _BasisWerte(True, True, es, nb, None), True)
    await db.commit()


async def test_03_f1_zeile_nulleinspeiser_wird_nachgestempelt(db, monkeypatch):
    a = await _anlage(db)
    await _f1_zeile(db, a.id, einspeisung_kwh=0.0, netzbezug_kwh=250.0, pv_erzeugung_kwh=300.0)

    zaehler = await migrate_n738_formular_neuanlage_nachstempeln(db)
    md = await _md(db, a.id)

    assert zaehler == {"zeilen": 1, "felder": 2, "wizard_ausgenommen": 0}
    assert _prov(md) == {"einspeisung_kwh": "manual:form", "netzbezug_kwh": "manual:form"}
    res = await _monat(db, monkeypatch, a.id, {})
    assert (res.netzbezug_kwh, res.einspeisung_kwh, res.eigenverbrauch_kwh, round(res.autarkie_prozent, 1)) == (
        250.0, 0.0, 300.0, 54.5), "vorher (250, None, None, None)"
    assert _netz_meldungen(await _checker(db, a.id)) == [], "vorher «Einspeisung nicht erfasst»"


async def test_03b_importzeile_bleibt_unberuehrt(db):
    a = await _anlage(db)
    r = await apply_import(anlage_id=a.id, data=ApplyRequest(monate=[ApplyMonthInput(jahr=J, monat=M, wallbox_ladung_kwh=150.0)]),
                           ueberschreiben=False, datenquelle="portal_import", db=db)
    assert r.erfolg
    await db.commit()

    zaehler = await migrate_n738_formular_neuanlage_nachstempeln(db)

    assert zaehler["zeilen"] == 0
    assert _prov(await _md(db, a.id)) == {}, "Wallbox-Import: 0/0 bleibt «nicht erfasst» (N-734)"


async def test_03c_nachgestempelt_schuetzt_vor_dem_ha_import_mit_haken(db):
    a = await _anlage(db)
    await _f1_zeile(db, a.id, einspeisung_kwh=180.0, netzbezug_kwh=250.0)
    await migrate_n738_formular_neuanlage_nachstempeln(db)

    await _ha_import_mit_haken(db, a.id, 999.0, 888.0)
    md = await _md(db, a.id)

    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (180.0, 250.0), "vorher still ersetzt: (999, 888)"
    assert _prov(md) == {"einspeisung_kwh": "manual:form", "netzbezug_kwh": "manual:form"}


async def test_altzeile_legacy_bleibt_unberuehrt(db):
    a = await _anlage(db)
    md = Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=0.0, netzbezug_kwh=0.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="legacy:unknown", writer="initial_migration", fields=list(NETZ))
    await db.commit()

    zaehler = await migrate_n738_formular_neuanlage_nachstempeln(db)

    assert zaehler["zeilen"] == 0
    assert _prov(await _md(db, a.id)) == {"einspeisung_kwh": "legacy:unknown", "netzbezug_kwh": "legacy:unknown"}


async def test_nur_das_fehlende_feld_wird_gestempelt(db):
    a = await _anlage(db)
    md = await _f1_zeile(db, a.id, einspeisung_kwh=0.0, netzbezug_kwh=250.0)
    seed_provenance(md, source="external:ha_statistics", writer="ha_statistics_import", fields=["netzbezug_kwh"])
    await db.commit()

    await migrate_n738_formular_neuanlage_nachstempeln(db)

    assert _prov(await _md(db, a.id)) == {"einspeisung_kwh": "manual:form", "netzbezug_kwh": "external:ha_statistics"}


async def test_zeile_des_monatsabschluss_assistenten_bleibt_unberuehrt(db):
    """Der alte Assistent liefert ein leer gelassenes Netzfeld nicht — seine 0 ohne Eintrag ist keine eingetragene 0."""
    from backend.api.routes.monatsabschluss.wizard import MonatsabschlussInput, save_monatsabschluss

    a = await _anlage(db)
    await save_monatsabschluss(a.id, J, M, MonatsabschlussInput(netzbezug_kwh=250.0, investitionen=[]), BackgroundTasks(), db)
    await db.commit()
    md = await _md(db, a.id)
    assert (md.datenquelle, _prov(md)) == (None, {"netzbezug_kwh": "manual:form"}), "Lage wie gemessen"

    zaehler = await migrate_n738_formular_neuanlage_nachstempeln(db)

    assert zaehler == {"zeilen": 0, "felder": 0, "wizard_ausgenommen": 1}
    assert _prov(await _md(db, a.id)) == {"netzbezug_kwh": "manual:form"}
    assert _netz_meldungen(await _checker(db, a.id)) == ["error|07/2025: Einspeisung nicht erfasst"]


async def test_zweiter_lauf_stempelt_nichts(db):
    a = await _anlage(db)
    await _f1_zeile(db, a.id, einspeisung_kwh=0.0, netzbezug_kwh=250.0)

    erster = await migrate_n738_formular_neuanlage_nachstempeln(db)
    zweiter = await migrate_n738_formular_neuanlage_nachstempeln(db)

    assert erster["zeilen"] == 1
    assert zweiter == {"zeilen": 0, "felder": 0, "wizard_ausgenommen": 0}


async def test_der_start_faehrt_die_migration_einmal(db, monkeypatch):
    """`_run_data_migrations` trägt sie unter ihrem Namen — nach der Initial-Provenance (die sonst F1-Zeilen als Altzeilen
    sähe; hier als schon gelaufen markiert, wie auf jeder Bestandsinstallation)."""
    from backend.core import database

    a = await _anlage(db)
    await _f1_zeile(db, a.id, einspeisung_kwh=0.0, netzbezug_kwh=250.0)
    await db.execute(text("CREATE TABLE IF NOT EXISTS migrations (name VARCHAR(100) PRIMARY KEY, applied_at TEXT NOT NULL)"))
    await db.execute(text("INSERT INTO migrations VALUES ('etappe_3d_p3_initial_provenance_legacy_unknown', 'x')"))
    await db.commit()
    monkeypatch.setattr(database, "async_session_maker",
                        async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False))

    await database._run_data_migrations()

    assert _prov(await _md(db, a.id)) == {"einspeisung_kwh": "manual:form", "netzbezug_kwh": "manual:form"}
    namen = {r[0] for r in (await db.execute(text("SELECT name FROM migrations"))).all()}
    assert "n735_formular_neuanlage_nachstempeln" in namen
