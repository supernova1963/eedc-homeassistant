"""F-33 / #381 — ein Balkonkraftwerk mit Kindern ist EIN System, keine drei Zeilen.

**Der gemeldete Schaden** (azywietz-web, 2026-08-17): Bei der Hierarchie
`BKW → PV-Module + Speicher` — seit v4.0.5 (Speicher) bzw. N-266/v4.0.18
(Module) eine erlaubte Struktur laut `ERLAUBTE_PARENT_TYPEN` — bekam jede
Ebene ihre eigene ROI-Zeile, und die Detailübersicht addierte sie. Alle drei
Beträge stammen aus **derselben** Energie: gemessen 606 €/Jahr, angezeigt
1.079 €/Jahr, Amortisation 1,9 statt 3,3 Jahre.

**Die Ursache** saß in `_gruppiere_investitionen`: dort war ausschließlich
`wechselrichter` ein Systemkopf. Die Sperre gegen Doppelzählung lag allein auf
der **Erzeugungs**seite (`pv_module_kwh` schließt die BKW-Erzeugung aus) — die
neue Struktur lief an der **Struktur**seite daran vorbei.

Die Tests hier prüfen beide Richtungen: dass die Hierarchie zusammenfällt,
**und** dass ein BKW ohne Kinder unverändert bleibt (die Abtretungs-Doktrin aus
`get_bkw_kwp`/`abgetretene_bkw_ids` gilt nur bei tatsächlich hängenden Kindern).
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen.crud import (
    _gruppiere_investitionen,
    get_roi_dashboard,
)
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


class _StubInv:
    """Minimaler Stub — der Gruppierer liest nur typ/id/parent."""

    def __init__(self, id: int, typ: str, parent_investition_id: int | None = None):
        self.id = id
        self.typ = typ
        self.parent_investition_id = parent_investition_id


# ============================================================================
# Gruppierer — die Struktur
# ============================================================================


def test_bkw_mit_modul_und_speicher_ist_ein_system():
    """Der gemeldete Fall: BKW + Modul-Kind + Speicher-Kind → EIN System."""
    bkw = _StubInv(4, "balkonkraftwerk")
    pv = _StubInv(8, "pv-module", parent_investition_id=4)
    sp = _StubInv(3, "speicher", parent_investition_id=4)

    pv_systeme, standalone, orphan = _gruppiere_investitionen([bkw, pv, sp])

    assert list(pv_systeme) == [4]
    assert pv_systeme[4]["wr"] is bkw
    assert pv_systeme[4]["pv_module"] == [pv]
    assert pv_systeme[4]["speicher"] == [sp]
    # Vor dem Fix: bkw + sp in `standalone`, pv in `orphan` — drei Zeilen.
    assert standalone == []
    assert orphan == []


def test_bkw_nur_mit_speicher_kind_ist_system():
    """Seit v4.0.5 möglich und ebenso betroffen: BKW + Speicher, ohne Module."""
    bkw = _StubInv(4, "balkonkraftwerk")
    sp = _StubInv(3, "speicher", parent_investition_id=4)

    pv_systeme, standalone, orphan = _gruppiere_investitionen([bkw, sp])

    assert list(pv_systeme) == [4]
    assert pv_systeme[4]["speicher"] == [sp]
    assert pv_systeme[4]["pv_module"] == []
    assert standalone == []


def test_bkw_ohne_kinder_bleibt_standalone():
    """Die Gegenrichtung — ohne Kinder ändert sich nichts (bitgleich)."""
    bkw = _StubInv(4, "balkonkraftwerk")

    pv_systeme, standalone, orphan = _gruppiere_investitionen([bkw])

    assert pv_systeme == {}
    assert standalone == [bkw]
    assert orphan == []


def test_modul_am_bkw_ist_kein_orphan_mehr():
    """Das Modul-Kind trug die Aufforderung „(ohne WR) - bitte zuordnen".

    Der Nutzer HATTE zugeordnet — nur eben an ein BKW. Eine Falschauskunft,
    nicht nur eine falsche Zahl.
    """
    bkw = _StubInv(4, "balkonkraftwerk")
    pv = _StubInv(8, "pv-module", parent_investition_id=4)

    pv_systeme, _standalone, orphan = _gruppiere_investitionen([bkw, pv])

    assert orphan == []
    assert pv_systeme[4]["pv_module"] == [pv]


def test_zwei_pass_auch_fuer_bkw_kopf():
    """Kind VOR dem BKW in der Liste wird trotzdem zugeordnet."""
    pv = _StubInv(8, "pv-module", parent_investition_id=4)
    bkw = _StubInv(4, "balkonkraftwerk")

    pv_systeme, _standalone, orphan = _gruppiere_investitionen([pv, bkw])

    assert pv_systeme[4]["pv_module"] == [pv]
    assert orphan == []


def test_wr_bleibt_kopf_neben_einem_bkw_system():
    """Beide Kopf-Arten nebeneinander stören sich nicht."""
    wr = _StubInv(1, "wechselrichter")
    dach = _StubInv(2, "pv-module", parent_investition_id=1)
    bkw = _StubInv(4, "balkonkraftwerk")
    balkon = _StubInv(8, "pv-module", parent_investition_id=4)

    pv_systeme, standalone, orphan = _gruppiere_investitionen([wr, dach, bkw, balkon])

    assert sorted(pv_systeme) == [1, 4]
    assert pv_systeme[1]["pv_module"] == [dach]
    assert pv_systeme[4]["pv_module"] == [balkon]
    assert standalone == []
    assert orphan == []


# ============================================================================
# Route — die Zahl, um die es dem Melder ging
# ============================================================================


async def _anlage_mit_bkw_hierarchie(db):
    """Der Aufbau aus #381: BKW „Toni" mit Modul-Kind und Speicher-Kind."""
    anlage = Anlage(anlagenname="Toni-Test", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=50.0))

    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Toni",
        anschaffungsdatum=date(2026, 3, 19), anschaffungskosten_gesamt=735.0,
        parameter={"leistung_wp": 500, "anzahl": 4},
    )
    db.add(bkw)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Toni PV-Module",
        parent_investition_id=bkw.id, leistung_kwp=2.0,
        anschaffungsdatum=date(2026, 3, 19), anschaffungskosten_gesamt=716.0,
    )
    sp = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher Toni",
        parent_investition_id=bkw.id, leistung_kwp=2.7,
        anschaffungsdatum=date(2026, 3, 19), anschaffungskosten_gesamt=554.0,
        parameter={"kapazitaet_kwh": 2.7},
    )
    db.add_all([pv, sp])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 200.0},
    ))
    await db.flush()
    return anlage, bkw, pv, sp


async def test_route_liefert_eine_zeile_statt_drei(db):
    """Die Detailübersicht zeigt EINE Zeile für die Hierarchie."""
    anlage, bkw, pv, sp = await _anlage_mit_bkw_hierarchie(db)

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=31.95, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )

    ids = {b.investition_id for b in result.berechnungen}
    # Vor dem Fix: alle drei IDs als eigene Zeile.
    assert pv.id not in ids
    assert sp.id not in ids
    assert bkw.id in ids

    zeile = next(b for b in result.berechnungen if b.investition_id == bkw.id)
    # Der Kopf-Typ, nicht "pv-system" — sonst trüge ein Balkonkraftwerk
    # Sonnen-Icon und fremden Namen (Regel 0a).
    assert zeile.investition_typ == "balkonkraftwerk"
    assert zeile.investition_bezeichnung == "Toni"
    # Alle drei Positionen stecken in den Kosten der einen Zeile.
    assert zeile.anschaffungskosten == 735.0 + 716.0 + 554.0
    komponenten_ids = {k.investition_id for k in (zeile.komponenten or [])}
    assert komponenten_ids == {bkw.id, pv.id, sp.id}


async def test_summe_zaehlt_die_energie_nur_einmal(db):
    """Kernzusicherung: die Gesamt-Einsparung addiert die Ebenen nicht mehr.

    Die Zeilen-Summe MUSS der Gesamtzahl entsprechen — vor dem Fix lagen
    zwischen beiden die doppelt gezählten Beträge.
    """
    anlage, bkw, pv, sp = await _anlage_mit_bkw_hierarchie(db)

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=31.95, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )

    zeilen_summe = sum(
        b.jahres_einsparung for b in result.berechnungen
        if b.jahres_einsparung is not None
    )
    assert abs(zeilen_summe - result.gesamt_jahres_einsparung) < 0.01

    # Und der abgetretene Kopf steuert nichts Eigenes mehr bei: die
    # Pauschalformel (0,9 kWh/Wp × 80 %) darf neben der GEMESSENEN
    # Modul-Erzeugung nicht mehr auftauchen.
    zeile = next(b for b in result.berechnungen if b.investition_id == bkw.id)
    kopf = next(k for k in (zeile.komponenten or []) if k.investition_id == bkw.id)
    assert kopf.einsparung is None
    assert "zugeordneten PV-Module" in kopf.detail["hinweis"]


async def test_bkw_ohne_kinder_behaelt_seine_zeile(db):
    """Gegenprobe an der Route: ohne Kinder bleibt alles, wie es war."""
    anlage = Anlage(anlagenname="Solo-BKW", leistung_kwp=0.8)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=50.0))
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Solo",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=800.0,
        parameter={"leistung_wp": 800},
    )
    db.add(bkw)
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    zeile = next(b for b in result.berechnungen if b.investition_id == bkw.id)
    assert zeile.investition_typ == "balkonkraftwerk"
    assert zeile.komponenten is None
    # 800 Wp × 0,9 = 720 kWh, davon 80 % Eigenverbrauch × 30 ct = 172,80 €
    # plus Einspeise-Erlös 144 kWh × 8 ct = 11,52 €.
    assert abs(zeile.jahres_einsparung - (172.80 + 11.52)) < 0.01
