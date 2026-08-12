"""#349 — ein gelöschter Monat lässt seine Gerätewerte stehen (OliS2811).

**Der gemeldete Ablauf:** Alle Monate eines Jahres gelöscht, danach neu
importiert — der Import lief durch und schrieb **nichts**, mit der Meldung
„6 Felder wurden durch manuell gepflegte Werte geschützt".

**Gemessen war die Ursache dreiteilig:**

1. ``delete_monatsdaten`` löscht nur die ``Monatsdaten``-Zeile. Die Messwerte je
   Komponente (``InvestitionMonatsdaten``) blieben stehen — **kein** Pfad im
   Baum hat sie je entfernt. Sichtbar sind sie danach nicht, denn die
   Monatslisten hängen an der gelöschten Zeile.
2. Der Re-Import prallt an ihnen ab: ohne „Überschreiben" wird jeder belegte
   Sub-Key übersprungen; mit „Überschreiben" gewinnt er gegen einen früheren
   Import, **nicht** gegen einen von Hand gepflegten Wert (``manual:*`` steht
   per Hierarchie über jedem Maschinen-Schreiber, FrodoVDR #251).
3. Der angebotene Ausweg zeigte ins Leere: der Reset der Reparatur-Werkbank
   scannte nur ``external:cloud_import:*`` — ein Label, das **kein**
   Produktivpfad je vergibt (der Apply-Pfad stempelt ``external:portal_import``).

Diese Proben halten alle drei fest, jede mit ihrer Gegenprobe.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten


async def _seed(db, *, provenance: str = "manual:form", wert: float = 900.0):
    anlage = Anlage(
        anlagenname="Zwei Stationen", leistung_kwp=10.0, standort_plz="10115",
        latitude=48.0, longitude=11.0, installationsdatum=date(2024, 1, 1),
    )
    db.add(anlage)
    await db.flush()

    inv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Sofar Station 2",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
        anschaffungskosten_gesamt=10000.0,
    )
    db.add(inv)
    await db.flush()

    md = Monatsdaten(anlage_id=anlage.id, jahr=2024, monat=6, pv_erzeugung_kwh=wert)
    db.add(md)
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2024, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": wert},
        source_provenance={
            "verbrauch_daten.pv_erzeugung_kwh": {
                "source": provenance, "writer": "test",
                "written_at": "2024-07-01T00:00:00",
            }
        },
    ))
    await db.flush()
    return anlage, inv, md


async def _anlage_wie_der_checker(db, anlage_id: int) -> Anlage:
    """Die Anlage so laden, wie der Daten-Checker sie lädt.

    Er zieht `investitionen` → `monatsdaten` eager (``selectinload``); die
    Prüfung liest genau diese Relationen. Ein Test, der sie lazy anfasst, misst
    ein anderes Objekt als der Betrieb — und scheitert im Async-Lauf.
    """
    from sqlalchemy.orm import selectinload

    res = await db.execute(
        select(Anlage)
        .where(Anlage.id == anlage_id)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
    )
    return res.scalar_one()


async def _verwaister_zustand(db, md: Monatsdaten) -> None:
    """Stellt „Gerätewerte ohne Zählerzeile" her — OHNE den Lösch-Weg.

    ⚠ Seit dem 12.08. löscht ``delete_monatsdaten`` den Monat **ganz**, taugt
    als Setup für diesen Zustand also nicht mehr. Er entsteht in der Praxis
    weiterhin: der **HA-Statistik-Import** legt die ``Monatsdaten``-Zeile nur
    an, wenn Einspeisung oder Netzbezug mitimportiert werden
    (``ha_statistics.py``) — wer nur Erzeuger-Sensoren zugeordnet hat, bekommt
    genau das hier. Deshalb wird die Zeile direkt entfernt statt über eine
    Route, die diesen Zustand nicht mehr erzeugt.
    """
    await db.delete(md)
    await db.flush()


async def _geraetezeilen(db, inv_id: int) -> list[InvestitionMonatsdaten]:
    res = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv_id
        )
    )
    return list(res.scalars().all())


# ─── 1. Löschen nimmt den ganzen Monat ───────────────────────────────────────


@pytest.mark.asyncio
async def test_loeschen_nimmt_den_ganzen_monat(db):
    """Ein Monat wird ganz gelöscht — Zählerzeile UND Werte je Gerät.

    ⚠ **Bis zum 2026-08-12 war das teilbar** (`mit_geraetewerten`, Vorgabe
    `False`), und zwei Tests hielten das fest: `..._laesst_die_geraetewerte_stehen`
    („die Vorgabe bleibt vorsichtig") und `..._mit_zusage_nimmt_die_geraetewerte_mit`.
    Die Schonung war gut gemeint — gemessene Gerätewerte sind oft die teureren
    Daten —, hat aber genau den Zustand erzeugt, den #349 zutage förderte: einen
    Monat, der in keiner Liste steht und trotzdem jeden Import abweist.

    **Warum die Teilung fachlich nicht trägt** (Gernot, 12.08.): Einspeisung und
    Netzbezug sind Pflichtfelder des Monatsabschlusses. Eine Hälfte zu löschen
    und die andere stehen zu lassen ergibt keinen Zustand, den eine Sicht
    darstellen könnte — der Monat ist danach weder da noch weg.
    """
    from backend.api.routes.monatsdaten import delete_monatsdaten

    anlage, inv, md = await _seed(db)
    await delete_monatsdaten(md.id, db=db)

    assert await _geraetezeilen(db, inv.id) == [], (
        "Gerätewerte blieben stehen — genau der Zustand aus #349."
    )
    rest_md = (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all()
    assert rest_md == []


@pytest.mark.asyncio
async def test_loeschen_greift_nicht_auf_fremde_anlagen_ueber(db):
    """Der Join ist der Punkt: `InvestitionMonatsdaten` trägt keine `anlage_id`.

    Ohne ihn würde der Monat einer Anlage die Gerätewerte aller anderen
    mitreißen — ein Datenverlust, den niemand bemerkt hätte.
    """
    from backend.api.routes.monatsdaten import delete_monatsdaten

    anlage_a, inv_a, md_a = await _seed(db)
    anlage_b, inv_b, md_b = await _seed(db, wert=555.0)

    await delete_monatsdaten(md_a.id, db=db)

    assert await _geraetezeilen(db, inv_a.id) == []
    assert len(await _geraetezeilen(db, inv_b.id)) == 1, (
        "Gerätewerte einer fremden Anlage wurden mitgelöscht"
    )


@pytest.mark.asyncio
async def test_dialog_erfaehrt_was_dranhaengt(db):
    """Der Lösch-Dialog fragt vorher — sonst wäre die Zusage blind."""
    from backend.api.routes.monatsdaten import get_geraetewerte_des_monats

    anlage, inv, md = await _seed(db)
    antwort = await get_geraetewerte_des_monats(md.id, db=db)

    assert antwort["anzahl"] == 1
    assert antwort["komponenten"][0]["bezeichnung"] == "Sofar Station 2"
    assert "pv_erzeugung_kwh" in antwort["komponenten"][0]["felder"]


# ─── 2. Der Rest ist auflösbar, auch wenn die Zeile schon weg ist ────────────


@pytest.mark.asyncio
async def test_verwaiste_geraetewerte_lassen_sich_entfernen(db):
    """Ollis Zustand: Zeile weg, Messwerte da — und bis jetzt kein Weg dahin."""
    from backend.api.routes.monatsdaten import delete_verwaiste_geraetewerte

    anlage, inv, md = await _seed(db)
    await _verwaister_zustand(db, md)               # der Zustand des Melders
    assert len(await _geraetezeilen(db, inv.id)) == 1

    antwort = await delete_verwaiste_geraetewerte(anlage.id, 2024, 6, db=db)

    assert antwort["geloescht"] == 1
    assert antwort["komponenten"] == ["Sofar Station 2"]
    assert await _geraetezeilen(db, inv.id) == []


@pytest.mark.asyncio
async def test_verwaisten_weg_gibt_es_nur_ohne_zaehlerzeile(db):
    """Zwei Wege zum selben Ziel wären genau die Drift, aus der das entstand.

    Existiert die Zeile noch, gehört der Monat in den Lösch-Dialog — der bietet
    beides zusammen an.
    """
    from fastapi import HTTPException
    from backend.api.routes.monatsdaten import delete_verwaiste_geraetewerte

    anlage, inv, md = await _seed(db)

    with pytest.raises(HTTPException) as fehler:
        await delete_verwaiste_geraetewerte(anlage.id, 2024, 6, db=db)

    assert fehler.value.status_code == 409
    assert len(await _geraetezeilen(db, inv.id)) == 1


@pytest.mark.asyncio
async def test_daten_checker_meldet_den_verwaisten_rest(db):
    """Ohne diese Meldung bliebe der Rest unsichtbar — er steht in keiner Liste."""
    from backend.api.routes.monatsdaten import delete_monatsdaten
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.kategorien import CheckKategorie

    anlage, inv, md = await _seed(db)
    await _verwaister_zustand(db, md)

    geladen = await _anlage_wie_der_checker(db, anlage.id)
    ergebnisse = DatenChecker(db)._check_geraetewerte_ohne_monatszeile(geladen, [])

    treffer = [
        e for e in ergebnisse
        if e.kategorie == CheckKategorie.GERAETEWERTE_OHNE_MONATSZEILE
    ]
    assert len(treffer) == 1, f"kein Befund: {ergebnisse}"
    assert "06/2024" in treffer[0].meldung
    # Ohne Reparatur-Weg wäre es ein Hinweis, den niemand auflösen kann (P-6).
    assert treffer[0].action_kind == "geraetewerte_loeschen"
    assert treffer[0].action_params == {"anlage_id": anlage.id, "jahr": 2024, "monat": 6}

    # Der Link führt in das Formular GENAU dieses Monats (12.08.). Vorher zeigte
    # er auf die Monatsdaten-Liste — dort steht der Monat zwar als offene Zeile,
    # der Anwender musste ihn aber selbst finden.
    assert treffer[0].link == "/einstellungen/daten?erfassen=2024-06", treffer[0].link

    # Und die Meldung behauptet die Ursache NICHT mehr: derselbe Zustand
    # entsteht auch durch einen HA-Import ohne Zähler-Sensoren, nicht nur durch
    # Löschen. Eine erfundene Ursache schickt den Anwender in die Irre.
    assert "gelöscht" not in treffer[0].details, treffer[0].details
    # Nachtragen ist der Regelfall — das muss vor dem Entfernen stehen.
    assert treffer[0].details.index("nach") < treffer[0].details.index("entferne")


@pytest.mark.asyncio
async def test_checker_schweigt_wenn_der_monat_noch_existiert(db):
    """Gegenprobe: ein normaler Monat ist kein Befund."""
    from backend.services.daten_checker import DatenChecker

    anlage, inv, md = await _seed(db)
    geladen = await _anlage_wie_der_checker(db, anlage.id)

    ergebnisse = DatenChecker(db)._check_geraetewerte_ohne_monatszeile(geladen, [md])
    assert ergebnisse == []


# ─── 3. Der Reset findet, was der Import wirklich schreibt ───────────────────


@pytest.mark.asyncio
async def test_reset_findet_die_werte_des_import_pfads(db):
    """`external:portal_import` ist das Label, das der Apply-Pfad vergibt.

    Vorher scannte der Reset nur `external:cloud_import:*` — ein Label, das
    **kein** Produktivpfad je setzt. Die Operation fand damit strukturell nie
    etwas, während die Import-Meldung ausdrücklich auf sie verwies.
    """
    from backend.services.repair_orchestrator import _scan_cloud_provenance

    anlage, inv, md = await _seed(db, provenance="external:portal_import")

    treffer = await _scan_cloud_provenance(db, anlage.id, None)
    assert len(treffer) == 1, "Reset findet die eigenen Import-Werte nicht"


@pytest.mark.asyncio
async def test_reset_laesst_handgepflegte_werte_in_ruhe(db):
    """Gegenprobe: der Reset ist für Import-Werte da, nicht für Handarbeit."""
    from backend.services.repair_orchestrator import _scan_cloud_provenance

    anlage, inv, md = await _seed(db, provenance="manual:form")

    assert await _scan_cloud_provenance(db, anlage.id, None) == []


@pytest.mark.asyncio
async def test_anbieter_filter_greift_nicht_auf_das_sammel_label_durch(db):
    """„Nur Fronius zurücksetzen" darf keine Deye-Werte löschen.

    `external:portal_import` trägt keinen Anbieter im Label — bei gesetztem
    Filter bleibt es deshalb außen vor, statt stillschweigend mitzugehen.
    """
    from backend.services.repair_orchestrator import _scan_cloud_provenance

    anlage, inv, md = await _seed(db, provenance="external:portal_import")

    assert await _scan_cloud_provenance(db, anlage.id, ["fronius_solarweb"]) == []
    assert len(await _scan_cloud_provenance(db, anlage.id, None)) == 1
