"""Migration `_migrate_pv_erzeugung_aggregat_clear` — kWp-Verteilung-Etappe.

Stellt die Invariante her: `monatsdaten.pv_erzeugung_kwh` ist ein rein
manuelles Aggregat. Geleert wird nur die **Auto-Summe** des alten Form-Pfads —
erkennbar daran, dass der Feldwert der Summe der Pro-Quellen-Werte entspricht
UND jede im Monat aktive PV-Quelle einen eigenen Wert hat (dann ist das Feld
redundant). Alles andere bleibt stehen. Idempotent.

A16/N44: Vorher genügte „irgendeine pv-module/balkonkraftwerk-IMD hat einen
Wert". Wer ein echtes Gesamt-Aggregat pflegt UND ein Balkonkraftwerk mit
eigenem Sensor hat, verlor damit das Aggregat — die Dachflächen standen
anschließend auf `fehlt`. [[project_kwp_verteilung_aggregator]].
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from backend.core.database import _migrate_pv_erzeugung_aggregat_clear


def _engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE monatsdaten ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, anlage_id INTEGER, "
            "jahr INTEGER, monat INTEGER, pv_erzeugung_kwh FLOAT)"
        ))
        conn.execute(text(
            "CREATE TABLE investitionen ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, anlage_id INTEGER, typ VARCHAR(50), "
            "aktiv BOOLEAN DEFAULT 1, anschaffungsdatum DATE, stilllegungsdatum DATE)"
        ))
        conn.execute(text(
            "CREATE TABLE investition_monatsdaten ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, investition_id INTEGER, "
            "jahr INTEGER, monat INTEGER, verbrauch_daten TEXT)"
        ))
    return engine


def _md(conn, md_id, anlage_id, wert, jahr=2026, monat=5):
    conn.execute(
        text("INSERT INTO monatsdaten (id, anlage_id, jahr, monat, pv_erzeugung_kwh) "
             "VALUES (:id,:a,:j,:m,:w)"),
        {"id": md_id, "a": anlage_id, "j": jahr, "m": monat, "w": wert},
    )


def _inv(conn, inv_id, anlage_id, typ, *, aktiv=1, anschaffung=None, stilllegung=None):
    conn.execute(
        text("INSERT INTO investitionen "
             "(id, anlage_id, typ, aktiv, anschaffungsdatum, stilllegungsdatum) "
             "VALUES (:id,:a,:t,:ak,:an,:st)"),
        {"id": inv_id, "a": anlage_id, "t": typ, "ak": aktiv,
         "an": anschaffung, "st": stilllegung},
    )


def _imd(conn, inv_id, daten, jahr=2026, monat=5):
    conn.execute(
        text("INSERT INTO investition_monatsdaten "
             "(investition_id, jahr, monat, verbrauch_daten) VALUES (:i,:j,:m,:v)"),
        {"i": inv_id, "j": jahr, "m": monat, "v": json.dumps(daten)},
    )


def _pv(engine, md_id):
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT pv_erzeugung_kwh FROM monatsdaten WHERE id = :id"), {"id": md_id}
        ).scalar_one()


def _lauf(engine, laeufe=1):
    with engine.begin() as conn:
        for _ in range(laeufe):
            _migrate_pv_erzeugung_aggregat_clear(conn)


def test_leert_echte_auto_summe():
    """Zwei Module, beide gemessen, Feld == Σ (600 + 400) → Signatur der Auto-Summe."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 1000.0)
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "pv-module")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.0})
        _imd(conn, 11, {"pv_erzeugung_kwh": 400.0})
    _lauf(engine)
    assert _pv(engine, 1) is None


def test_a16_echtes_aggregat_plus_bkw_bleibt():
    """Der zerstörte Fall (JayJayX #651): Gesamt-Aggregat fürs Dach + BKW mit
    eigenem Sensor. Vorher leerte der `break` beim ersten BKW-Treffer das Feld
    und die Dachflächen standen auf `fehlt`."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 8000.0)          # gepflegtes Gesamt-Aggregat der Dachanlage
        _inv(conn, 10, 1, "pv-module")   # kein eigener Wert — deshalb das Aggregat
        _inv(conn, 11, 1, "pv-module")
        _inv(conn, 12, 1, "balkonkraftwerk")
        _imd(conn, 12, {"pv_erzeugung_kwh": 300.0})
    _lauf(engine)
    assert _pv(engine, 1) == 8000.0


def test_aggregat_ohne_jeden_pro_modul_wert_bleibt():
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 800.0)
        _inv(conn, 10, 1, "pv-module")
    _lauf(engine)
    assert _pv(engine, 1) == 800.0


def test_imd_ohne_pv_key_zaehlt_nicht_als_wert():
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 500.0)
        _inv(conn, 10, 1, "pv-module")
        _imd(conn, 10, {"ladung_kwh": 5.0})
    _lauf(engine)
    assert _pv(engine, 1) == 500.0


def test_teil_erfassung_bleibt_obwohl_summe_passt():
    """Ein Modul gemessen (600), zweites ohne Wert, Feld = 600. Die Signatur
    passt, die Redundanz nicht: nach dem Leeren stünde der Monat auf `fehlt`,
    weil `resolve_pv_je_modul` ohne Aggregat und ohne vollständige Messung
    nichts liefert."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 600.0)
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "pv-module")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.0})
    _lauf(engine)
    assert _pv(engine, 1) == 600.0


def test_gegenbeispiel_auto_summe_ueber_wechselrichter_bleibt():
    """Die alte Auto-Summe umfasste auch `wechselrichter` und `sonstiges`/Erzeuger.
    Solche Summen werden NICHT geleert: ihre Bestandteile liest kein PV-Pfad,
    das Feld ist damit die einzige Quelle. Stehenlassen ist die sichere
    Richtung — es bleibt korrigierbar, Löschen nicht."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 1000.0)          # = 600 Modul + 400 Wechselrichter
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "wechselrichter")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.0})
        _imd(conn, 11, {"pv_erzeugung_kwh": 400.0})
    _lauf(engine)
    assert _pv(engine, 1) == 1000.0


def test_auto_summe_modul_plus_bkw_wird_geleert():
    """BKW-Werte werden gelesen (`/aggregiert` summiert sie eigenständig) —
    eine Summe aus Modul + BKW ist redundant und darf weg."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 900.0)
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "balkonkraftwerk")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.0})
        _imd(conn, 11, {"erzeugung_kwh": 300.0})   # Legacy-Key des BKW
    _lauf(engine)
    assert _pv(engine, 1) is None


def test_stillgelegtes_modul_blockiert_nicht():
    """Ein im Monat nicht aktives Modul ist keine fehlende Quelle."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 600.0)
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "pv-module", stilllegung="2024-12-31")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.0})
    _lauf(engine)
    assert _pv(engine, 1) is None


def test_rundungstoleranz():
    """0,1er-Rundung beim Speichern darf die Auto-Summe nicht zum Aggregat machen."""
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 1000.0)
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "pv-module")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.05})
        _imd(conn, 11, {"pv_erzeugung_kwh": 400.15})
    _lauf(engine)
    assert _pv(engine, 1) is None


def test_idempotent():
    engine = _engine()
    with engine.begin() as conn:
        _md(conn, 1, 1, 1000.0)          # Auto-Summe → weg
        _md(conn, 2, 1, 8000.0, monat=6)  # echtes Aggregat → bleibt
        _inv(conn, 10, 1, "pv-module")
        _inv(conn, 11, 1, "pv-module")
        _imd(conn, 10, {"pv_erzeugung_kwh": 600.0})
        _imd(conn, 11, {"pv_erzeugung_kwh": 400.0})
    _lauf(engine, laeufe=3)
    assert _pv(engine, 1) is None
    assert _pv(engine, 2) == 8000.0
