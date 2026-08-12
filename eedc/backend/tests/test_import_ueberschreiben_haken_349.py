"""Der Überschreiben-Haken tut, was er sagt — und sagt vorher, was er kostet.

**Der Befund** (Gernot, 2026-08-12): „Bestehende Monate überschreiben" ersetzte
keine manuell gepflegten Werte. Der Import lief durch und meldete hinterher
„6 Felder durch manuell gepflegte Werte geschützt" — eedc tat also etwas
anderes, als der Anwender angeordnet hatte. Betroffen war jeder, der Werte
einmal von Hand korrigiert hatte und danach neu importieren wollte; bei
OliS2811 (#349) war es der Grund, warum er Monate löschen musste, um überhaupt
importieren zu können.

**Die Herkunft der Regel:** Die Hierarchie entstand, damit **Handarbeit
durchkommt** (FrodoVDR #251: „nach dem Speichern ist das Feld wieder leer"),
nicht damit Importe abprallen. Dass ein CSV-Import als `manual:csv_import`
durchkam und ein Cloud-Import mit demselben Klick nicht, war zusätzlich
inkonsistent — derselbe Anwender, dieselbe Absicht, zwei Ergebnisse.

**Was den Schutz ersetzt:** eine Ansage VOR dem Klick (`zaehle_manuelle_werte`).
Ohne sie wäre aus einer Bevormundung ein stiller Datenverlust geworden.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.import_writer import zaehle_manuelle_werte
from backend.services.provenance import write_with_provenance


async def _anlage_mit_monat(db, *, jahr=2024, monat=6) -> tuple[Anlage, Investition, Monatsdaten]:
    anlage = Anlage(
        anlagenname="Handarbeit", leistung_kwp=10.0, standort_plz="10115",
        latitude=48.0, longitude=11.0, installationsdatum=date(2023, 1, 1),
    )
    db.add(anlage)
    await db.flush()

    inv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="String Süd",
        anschaffungsdatum=date(2023, 1, 1), leistung_kwp=10.0,
    )
    db.add(inv)
    await db.flush()

    md = Monatsdaten(
        anlage_id=anlage.id, jahr=jahr, monat=monat,
        einspeisung_kwh=700.0, netzbezug_kwh=400.0,
    )
    db.add(md)
    await db.flush()
    return anlage, inv, md


def _manuell(quelle: str = "manual:form") -> dict:
    return {"source": quelle, "writer": "alice", "written_at": "2024-07-01T00:00:00"}


# ═══════════════════════════════════════════════════════════════════════════
# Die Ansage: was würde der Haken kosten?
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zaehler_findet_nichts_ohne_handarbeit(db):
    anlage, inv, md = await _anlage_mit_monat(db)
    bestand = await zaehle_manuelle_werte(db, anlage.id, [(2024, 6)])
    assert not bestand.betroffen
    assert (bestand.monate, bestand.felder) == (0, 0)


@pytest.mark.asyncio
async def test_zaehler_findet_beide_ebenen(db):
    """Der Anwender unterscheidet Zählerzeile und Gerätewerte nicht — für ihn
    ist es „mein Monat". Der Zähler darf das auch nicht."""
    anlage, inv, md = await _anlage_mit_monat(db)
    md.source_provenance = {"einspeisung_kwh": _manuell()}
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2024, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 900.0},
        source_provenance={"verbrauch_daten.pv_erzeugung_kwh": _manuell()},
    ))
    await db.flush()

    bestand = await zaehle_manuelle_werte(db, anlage.id, [(2024, 6)])
    assert bestand.felder == 2
    assert bestand.monate == 1
    assert any("einspeisung_kwh" in b for b in bestand.beispiele)
    assert any("pv_erzeugung_kwh" in b for b in bestand.beispiele)


@pytest.mark.asyncio
async def test_zaehler_ignoriert_maschinen_quellen(db):
    """Ein Import-Wert ist keine Handarbeit — sonst warnte eedc vor sich selbst."""
    anlage, inv, md = await _anlage_mit_monat(db)
    md.source_provenance = {"einspeisung_kwh": _manuell("external:portal_import")}
    await db.flush()

    bestand = await zaehle_manuelle_werte(db, anlage.id, [(2024, 6)])
    assert not bestand.betroffen


@pytest.mark.asyncio
async def test_zaehler_bleibt_bei_den_gefragten_monaten(db):
    """Nur die Monate, die der Import anfassen würde — nicht die ganze Anlage."""
    anlage, inv, md = await _anlage_mit_monat(db, monat=6)
    md.source_provenance = {"einspeisung_kwh": _manuell()}
    await db.flush()

    assert (await zaehle_manuelle_werte(db, anlage.id, [(2024, 7)])).felder == 0
    assert (await zaehle_manuelle_werte(db, anlage.id, [(2024, 6)])).felder == 1


@pytest.mark.asyncio
async def test_zaehler_ohne_perioden_fragt_die_db_nicht(db):
    anlage, inv, md = await _anlage_mit_monat(db)
    assert not (await zaehle_manuelle_werte(db, anlage.id, [])).betroffen


@pytest.mark.asyncio
async def test_endpunkt_liefert_die_zahl(db):
    from backend.api.routes.data_import import get_manuelle_werte

    anlage, inv, md = await _anlage_mit_monat(db)
    md.source_provenance = {"netzbezug_kwh": _manuell()}
    await db.flush()

    antwort = await get_manuelle_werte(anlage.id, perioden="2024-06", db=db)
    assert antwort.betroffen and antwort.felder == 1


@pytest.mark.asyncio
async def test_endpunkt_weist_kaputte_perioden_ab(db):
    """Ein stiller 0-Wert wäre hier gefährlich: der Wizard läse „nichts
    betroffen" und ließe den Haken ohne Warnung wirken."""
    from backend.api.routes.data_import import get_manuelle_werte

    anlage, inv, md = await _anlage_mit_monat(db)
    for kaputt in ("2024-13", "Juni", "2024"):
        with pytest.raises(HTTPException) as fehler:
            await get_manuelle_werte(anlage.id, perioden=kaputt, db=db)
        assert fehler.value.status_code == 400, kaputt


# ═══════════════════════════════════════════════════════════════════════════
# Der Durchbruch selbst
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_haken_ersetzt_handarbeit_und_behaelt_die_herkunft(db):
    """Der Kern: der Import gewinnt — und der Wert trägt danach die Quelle des
    Imports, nicht `repair`.

    Stünde dort `repair` (Stufe 0), prallte der **nächste** reguläre Import ab
    und die Falle wäre nur verschoben.
    """
    anlage, inv, md = await _anlage_mit_monat(db)
    md.source_provenance = {"einspeisung_kwh": _manuell()}
    await db.flush()

    res = await write_with_provenance(
        db, md, "einspeisung_kwh", 1234.0,
        source="external:portal_import", writer="portal_apply:cloud_import",
        benutzer_override=True,
    )
    await db.flush()

    assert res.applied
    assert md.einspeisung_kwh == 1234.0
    assert md.source_provenance["einspeisung_kwh"]["source"] == "external:portal_import"


@pytest.mark.asyncio
async def test_ohne_haken_bleibt_handarbeit_unangetastet(db):
    """Die Gegenprobe zu FrodoVDR #251 — fiele sie, wäre die Hierarchie
    abgeschafft statt präzisiert."""
    anlage, inv, md = await _anlage_mit_monat(db)
    md.source_provenance = {"einspeisung_kwh": _manuell()}
    await db.flush()

    res = await write_with_provenance(
        db, md, "einspeisung_kwh", 1234.0,
        source="external:portal_import", writer="portal_apply:cloud_import",
    )
    await db.flush()

    assert not res.applied
    assert res.decision == "rejected_lower_priority"
    assert md.einspeisung_kwh == 700.0


@pytest.mark.asyncio
async def test_ein_zweiter_import_kommt_danach_normal_durch(db):
    """Die eigentliche Zusicherung hinter „Herkunft behalten": nach dem
    Durchbruch ist der Wert ein gewöhnlicher Import-Wert."""
    anlage, inv, md = await _anlage_mit_monat(db)
    md.source_provenance = {"einspeisung_kwh": _manuell()}
    await db.flush()

    await write_with_provenance(
        db, md, "einspeisung_kwh", 1234.0,
        source="external:portal_import", writer="portal_apply:cloud_import",
        benutzer_override=True,
    )
    await db.flush()

    # Zweiter Lauf OHNE Haken — muss durchkommen.
    res = await write_with_provenance(
        db, md, "einspeisung_kwh", 1500.0,
        source="external:portal_import", writer="portal_apply:cloud_import",
    )
    await db.flush()

    assert res.applied, "Der nächste reguläre Import prallt ab — Falle verschoben."
    assert md.einspeisung_kwh == 1500.0


@pytest.mark.asyncio
async def test_der_import_pfad_ende_zu_ende(db):
    """Ollis Ablauf: Wert von Hand korrigiert, danach mit Haken neu importiert."""
    from backend.api.routes.data_import import (
        ApplyMonthInput,
        ApplyRequest,
        apply_import,
    )

    anlage, inv, md = await _anlage_mit_monat(db)
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2024, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 900.0},
        source_provenance={"verbrauch_daten.pv_erzeugung_kwh": _manuell()},
    ))
    await db.commit()

    antwort = await apply_import(
        anlage_id=anlage.id,
        data=ApplyRequest(monate=[ApplyMonthInput(
            jahr=2024, monat=6, pv_erzeugung_kwh=1234.0,
            einspeisung_kwh=800.0, netzbezug_kwh=450.0,
        )]),
        ueberschreiben=True, datenquelle="cloud_import", db=db,
    )
    await db.commit()

    assert antwort.erfolg
    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )).scalar_one()
    assert imd.verbrauch_daten["pv_erzeugung_kwh"] == 1234.0, (
        "Der angeordnete Import prallte an der Handarbeit ab — Ollis Symptom."
    )
