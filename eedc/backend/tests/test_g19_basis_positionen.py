"""G19-1: Sonstige Erträge & Ausgaben auf Anlage-Ebene (Basis-Positionen).

Basis-`Monatsdaten.sonstige_positionen` wirken GENAU wie die IMD-Positionen —
gleiche Helper-Familie (`utils/sonstige_positionen`), gleiche Summen in allen
Anlage-Ebene-Finanz-Read-Sites (Monatsbericht/T-Konto, Komponenten-Zeitreihe,
Cockpit-Übersicht), einmalige Faltung (R15-5-Muster: Ausweis + Summe, kein
zweiter Kostenposten). Alt-`sonderkosten_euro` wird per Start-Migration als
Ausgabe-Position „… (migriert)" materialisiert; die Legacy-Spalten bleiben
lesbar ([[feedback_legacy_felder]]).

Lehren: [[feedback_aggregator_symmetrie]], [[feedback_aggregations_drift]].
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from backend.core.database import _migrate_monatsdaten_sonderkosten_zu_positionen
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.utils.sonstige_positionen import (
    berechne_md_sonstige_summen,
    get_md_sonstige_positionen,
)


# ── A. Helfer-Kontrakt (Basis-Ebene) ────────────────────────────────────────

def test_get_md_sonstige_positionen_json_hat_vorrang():
    md = SimpleNamespace(
        sonstige_positionen=[{"bezeichnung": "Guthaben", "betrag": 80.0, "typ": "ertrag"}],
        sonderkosten_euro=999.0, sonderkosten_beschreibung="wird ignoriert",
    )
    assert get_md_sonstige_positionen(md) == [
        {"bezeichnung": "Guthaben", "betrag": 80.0, "typ": "ertrag"}
    ]


def test_get_md_sonstige_positionen_legacy_fallback():
    """Spalten-Legacy → eine Ausgabe-Position, exakt wie der IMD-Fallback."""
    md = SimpleNamespace(
        sonstige_positionen=None,
        sonderkosten_euro=150.0, sonderkosten_beschreibung="Reparatur",
    )
    assert get_md_sonstige_positionen(md) == [
        {"bezeichnung": "Reparatur", "betrag": 150.0, "typ": "ausgabe"}
    ]
    # Leere Liste = bewusst geleert → Legacy wird NICHT wiederbelebt.
    md_geleert = SimpleNamespace(
        sonstige_positionen=[], sonderkosten_euro=150.0, sonderkosten_beschreibung="x",
    )
    assert get_md_sonstige_positionen(md_geleert) == []
    assert get_md_sonstige_positionen(None) == []


def test_berechne_md_sonstige_summen_beide_richtungen():
    """Positions-Mechanik deckt BEIDE Zahlungsrichtungen (Gernot 2026-07-17):
    Abschlag=Ausgabe · Einspeise-Abschlag=Ertrag · Guthaben-Auszahlung=Ertrag ·
    Nachzahlung=Ausgabe."""
    md = SimpleNamespace(sonstige_positionen=[
        {"bezeichnung": "Abschlag Versorger", "betrag": 90.0, "typ": "ausgabe"},
        {"bezeichnung": "Einspeise-Abschlag", "betrag": 40.0, "typ": "ertrag"},
        {"bezeichnung": "Guthaben Jahresabrechnung", "betrag": 120.0, "typ": "ertrag"},
        {"bezeichnung": "Nachzahlung", "betrag": 30.0, "typ": "ausgabe"},
    ])
    summen = berechne_md_sonstige_summen(md)
    assert summen == {"ertraege_euro": 160.0, "ausgaben_euro": 120.0, "netto_euro": 40.0}


# ── B. Start-Migration (additiv, idempotent) ────────────────────────────────

def _mig_db():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE monatsdaten ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, anlage_id INTEGER, "
            "jahr INTEGER, monat INTEGER, sonderkosten_euro FLOAT, "
            "sonderkosten_beschreibung VARCHAR(500), sonstige_positionen JSON)"
        ))
        conn.execute(text(
            "INSERT INTO monatsdaten (id, anlage_id, jahr, monat, sonderkosten_euro, "
            "sonderkosten_beschreibung, sonstige_positionen) VALUES "
            # 1: Legacy mit Beschreibung → migriert
            "(1, 1, 2026, 3, 120.0, 'WR-Wartung', NULL), "
            # 2: Legacy ohne Beschreibung → Default-Bezeichnung
            "(2, 1, 2026, 4, 55.5, NULL, NULL), "
            # 3: kein Legacy-Wert → bleibt NULL
            "(3, 1, 2026, 5, NULL, NULL, NULL), "
            # 4: 0-Legacy → bleibt NULL (0 war nie eine echte Sonderkosten-Angabe)
            "(4, 1, 2026, 6, 0.0, 'leer', NULL), "
            # 5: JSON existiert schon → wird NICHT überschrieben
            "(5, 1, 2026, 7, 99.0, 'alt', '[{\"bezeichnung\": \"neu\", \"betrag\": 1.0, \"typ\": \"ertrag\"}]')"
        ))
    return engine


def test_migration_materialisiert_legacy_sonderkosten():
    engine = _mig_db()
    with engine.begin() as conn:
        _migrate_monatsdaten_sonderkosten_zu_positionen(conn)
    with engine.connect() as conn:
        rows = {r[0]: r[1] for r in conn.execute(
            text("SELECT id, sonstige_positionen FROM monatsdaten")).fetchall()}
    assert json.loads(rows[1]) == [
        {"bezeichnung": "WR-Wartung (migriert)", "betrag": 120.0, "typ": "ausgabe"}]
    assert json.loads(rows[2]) == [
        {"bezeichnung": "Sonderkosten (migriert)", "betrag": 55.5, "typ": "ausgabe"}]
    assert rows[3] is None
    assert rows[4] is None
    assert json.loads(rows[5]) == [{"bezeichnung": "neu", "betrag": 1.0, "typ": "ertrag"}]
    # Legacy-Spalten bleiben unangetastet lesbar.
    with engine.connect() as conn:
        legacy = conn.execute(text(
            "SELECT sonderkosten_euro FROM monatsdaten WHERE id = 1")).scalar()
    assert legacy == 120.0


def test_migration_idempotent():
    engine = _mig_db()
    with engine.begin() as conn:
        _migrate_monatsdaten_sonderkosten_zu_positionen(conn)
    with engine.begin() as conn:
        _migrate_monatsdaten_sonderkosten_zu_positionen(conn)  # zweiter Lauf = No-Op
    with engine.connect() as conn:
        row1 = conn.execute(text(
            "SELECT sonstige_positionen FROM monatsdaten WHERE id = 1")).scalar()
    assert json.loads(row1) == [
        {"bezeichnung": "WR-Wartung (migriert)", "betrag": 120.0, "typ": "ausgabe"}]


def test_migration_uebersteht_korrupte_legacy_werte():
    """Boot-Härtung: SQLite ist dynamisch typisiert und wertet TEXT > 0 als wahr —
    korrupte String-Werte in `sonderkosten_euro` erreichen die Migration. Sie läuft
    im ungeschützten Boot-Pfad (run_migrations) und darf NICHT werfen
    (Add-on-Restart-Schleife, v3.45.8-Klasse): Komma-Strings werden gerettet,
    Unrettbares wird übersprungen und bleibt via Legacy-Fallback lesbar."""
    engine = _mig_db()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO monatsdaten (id, anlage_id, jahr, monat, sonderkosten_euro, "
            "sonderkosten_beschreibung, sonstige_positionen) VALUES "
            "(6, 1, 2026, 8, '150,00', 'Komma-String', NULL), "
            "(7, 1, 2026, 9, 'kaputt', 'Unrettbar', NULL)"
        ))
    with engine.begin() as conn:
        _migrate_monatsdaten_sonderkosten_zu_positionen(conn)  # darf nicht werfen
    with engine.connect() as conn:
        rows = {r[0]: r[1] for r in conn.execute(text(
            "SELECT id, sonstige_positionen FROM monatsdaten WHERE id IN (6, 7)"
        )).fetchall()}
    assert json.loads(rows[6]) == [
        {"bezeichnung": "Komma-String (migriert)", "betrag": 150.0, "typ": "ausgabe"}]
    assert rows[7] is None  # übersprungen statt Boot-Abbruch


# ── C. Read-Site-Symmetrie: Basis wirkt wie IMD, genau EINMAL ───────────────

async def _komp_monat(db, anlage_id, jahr, monat):
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    komp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=None, db=db)
    return next((m for m in komp.monatswerte if m.jahr == jahr and m.monat == monat), None)


async def test_basis_positionen_symmetrisch_und_ohne_doppelzaehlung(db):
    """Mischfall IMD-Ertrag (200) + Basis-Ausgabe (30) + Basis-Ertrag (120):
    Monatsbericht und Komponenten-Zeitreihe liefern identische Totals, die
    Basis steckt GENAU EINMAL drin und wird separat als anlage_* ausgewiesen."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="G19Sym", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=4,
        verbrauch_daten={"sonstige_positionen": [
            {"bezeichnung": "THG", "betrag": 200.0, "typ": "ertrag"},
        ]},
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        einspeisung_kwh=500, netzbezug_kwh=200,
        sonstige_positionen=[
            {"bezeichnung": "Nachzahlung", "betrag": 30.0, "typ": "ausgabe"},
            {"bezeichnung": "Guthaben-Auszahlung", "betrag": 120.0, "typ": "ertrag"},
        ],
    ))
    await db.commit()

    am = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=4, db=db)
    km = await _komp_monat(db, anlage.id, 2026, 4)

    # Totals = IMD + Basis, genau einmal (R15-5: kein zweiter Posten).
    assert am.sonstige_ertraege_euro == 320.0
    assert am.sonstige_ausgaben_euro == 30.0
    assert am.sonstige_netto_euro == 290.0
    # Ausweis der Basis-Anteile für die T-Konto-Zeile „Anlage — Sonstige …".
    assert am.anlage_sonstige_ertraege_euro == 120.0
    assert am.anlage_sonstige_ausgaben_euro == 30.0

    assert km is not None
    assert km.sonstige_ertraege_euro == am.sonstige_ertraege_euro
    assert km.sonstige_ausgaben_euro == am.sonstige_ausgaben_euro
    assert km.sonstige_netto_euro == am.sonstige_netto_euro
    assert km.anlage_sonstige_ertraege_euro == 120.0
    assert km.anlage_sonstige_ausgaben_euro == 30.0


async def test_basis_positionen_ohne_investitionen_erscheinen(db):
    """Anlage OHNE Investitionen: Basis-Positionen erscheinen trotzdem in der
    Komponenten-Zeitreihe (der frühere Early-Return hätte sie verschluckt —
    #310-Klasse)."""
    anlage = Anlage(anlagenname="G19Leer", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=5,
        einspeisung_kwh=100, netzbezug_kwh=50,
        sonstige_positionen=[
            {"bezeichnung": "Einspeise-Abschlag", "betrag": 45.0, "typ": "ertrag"},
        ],
    ))
    await db.commit()

    km = await _komp_monat(db, anlage.id, 2026, 5)
    assert km is not None, "Basis-Monat muss eine Zeile erzeugen"
    assert km.sonstige_ertraege_euro == 45.0
    assert km.anlage_sonstige_ertraege_euro == 45.0


async def test_basis_positionen_in_cockpit_uebersicht(db):
    """Cockpit-Übersicht (#326-Pfad): Basis-Netto fließt in sonstige_netto_euro."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    anlage = Anlage(anlagenname="G19Ueb", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        einspeisung_kwh=400, netzbezug_kwh=100,
        sonstige_positionen=[
            {"bezeichnung": "Guthaben", "betrag": 75.0, "typ": "ertrag"},
            {"bezeichnung": "Nachzahlung", "betrag": 25.0, "typ": "ausgabe"},
        ],
    ))
    await db.commit()

    ueb = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    assert ueb.sonstige_netto_euro == 50.0


async def test_basis_legacy_spalten_zaehlen_via_fallback(db):
    """Alt-Zeile (nur sonderkosten_euro-Spalte, Migration noch nicht gelaufen —
    z. B. frisch restauriertes Alt-Backup): Lese-Fallback zählt sie als Ausgabe."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="G19Legacy", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=2,
        einspeisung_kwh=100, netzbezug_kwh=300,
        sonderkosten_euro=88.0, sonderkosten_beschreibung="Zählertausch",
        sonstige_positionen=None,
    ))
    await db.commit()

    am = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=2, db=db)
    assert am.anlage_sonstige_ausgaben_euro == 88.0
    assert am.sonstige_ausgaben_euro == 88.0


# ── D. API-Roundtrip (Create/Update-Schemas, Filter- und Löschsignal) ───────

async def test_api_create_und_update_roundtrip(db):
    from backend.api.routes.monatsdaten import (
        MonatsdatenCreate, MonatsdatenUpdate,
        create_monatsdaten, update_monatsdaten,
    )

    anlage = Anlage(anlagenname="G19Api", leistung_kwp=10.0)
    db.add(anlage)
    await db.commit()

    created = await create_monatsdaten(MonatsdatenCreate(
        anlage_id=anlage.id, jahr=2026, monat=6,
        einspeisung_kwh=100, netzbezug_kwh=50,
        sonstige_positionen=[
            {"bezeichnung": "Guthaben", "betrag": 60.0, "typ": "ertrag"},
            {"bezeichnung": "   ", "betrag": 5.0, "typ": "ausgabe"},  # ungültig → gefiltert
            {"bezeichnung": "Garantiefall", "betrag": 0.0, "typ": "ausgabe"},  # 0 € legitim (#286)
        ],
    ), db=db)
    assert created.sonstige_positionen == [
        {"bezeichnung": "Guthaben", "betrag": 60.0, "typ": "ertrag"},
        {"bezeichnung": "Garantiefall", "betrag": 0.0, "typ": "ausgabe"},
    ]

    # Leeren per Update: [] muss persistiert werden (Löschsignal, #286-Regel).
    updated = await update_monatsdaten(created.id, MonatsdatenUpdate(
        sonstige_positionen=[],
    ), db=db)
    assert updated.sonstige_positionen == []


# ── E. K3 (R19-3): Grundgebühr-Ausweis + Zählergebühr-Tarif-Feld ────────────

async def test_k3_grundgebuehr_und_zaehlergebuehr_im_monatsbericht(db):
    """Monatsbericht weist die Grundgebühr des Monats (steckt in
    netzbezug_kosten) und die Jahres-Zählergebühr vom Tarif aus — beides
    reiner Ausweis, netzbezug_kosten bleibt Arbeitspreis + Grundpreis."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.models.strompreis import Strompreis

    anlage = Anlage(anlagenname="G19K3", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id,
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=12.5,
        zaehlergebuehr_euro_jahr=48.0,
        gueltig_ab=date(2020, 1, 1),
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        einspeisung_kwh=100, netzbezug_kwh=200,
    ))
    await db.commit()

    am = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=4, db=db)
    assert am.grundgebuehr_euro == 12.5
    assert am.zaehlergebuehr_euro_jahr == 48.0
    # Kosten unverändert: 200 kWh × 30 ct + 12,50 € Grundpreis = 72,50 €
    assert am.netzbezug_kosten_euro == 72.5


async def test_k3_zaehlergebuehr_tarif_roundtrip(db):
    """Tarif-CRUD: Zählergebühr wird gespeichert und im Response geliefert."""
    from backend.api.routes.strompreise import StrompreisCreate, create_strompreis

    anlage = Anlage(anlagenname="G19K3Tarif", leistung_kwp=10.0)
    db.add(anlage)
    await db.commit()

    created = await create_strompreis(StrompreisCreate(
        anlage_id=anlage.id,
        netzbezug_arbeitspreis_cent_kwh=32.0,
        einspeiseverguetung_cent_kwh=8.2,
        grundpreis_euro_monat=10.0,
        zaehlergebuehr_euro_jahr=36.0,
        gueltig_ab=date(2026, 1, 1),
    ), db=db)
    assert created.zaehlergebuehr_euro_jahr == 36.0
