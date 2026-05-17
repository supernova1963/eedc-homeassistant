"""
Akzeptanztest Etappe A (Issue #264): `laedt_aus_netz` als Erfassungs-Schalter.

Deckt zwei Schichten ab:
  1. Field-Resolver (`get_felder_fuer_investition`) — `ladung_netz_kwh`
     ist sichtbar wenn `laedt_aus_netz=true` ODER `arbitrage_faehig=true`
     (Implikation), ansonsten nicht.
  2. Backfill-Migration (`_migrate_speicher_laedt_aus_netz_backfill`) —
     setzt `laedt_aus_netz=true` für Bestands-Speicher mit
     `arbitrage_faehig=true`. Idempotent. Speicher ohne Arbitrage und
     andere Typen bleiben unangetastet.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_speicher_laedt_aus_netz.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.core.database import _migrate_speicher_laedt_aus_netz_backfill  # noqa: E402
from backend.core.field_definitions import get_felder_fuer_investition  # noqa: E402


# ----------------------------------------------------------------------------
# Field-Resolver
# ----------------------------------------------------------------------------

def _feldnamen(typ: str, params: dict) -> set[str]:
    return {f["feld"] for f in get_felder_fuer_investition(typ, params)}


def test_resolver_ohne_flag_blendet_netzladung_aus() -> None:
    felder = _feldnamen("speicher", {"kapazitaet_kwh": 10})
    assert "ladung_netz_kwh" not in felder, (
        "ohne laedt_aus_netz/arbitrage_faehig darf das Feld nicht erscheinen"
    )
    assert "speicher_ladepreis_cent" not in felder
    assert "ladung_kwh" in felder
    assert "entladung_kwh" in felder


def test_resolver_laedt_aus_netz_zeigt_nur_netzladung() -> None:
    felder = _feldnamen("speicher", {"laedt_aus_netz": True})
    assert "ladung_netz_kwh" in felder
    # Ladepreis bleibt arbitrage-only
    assert "speicher_ladepreis_cent" not in felder


def test_resolver_arbitrage_impliziert_netzladung() -> None:
    # arbitrage_faehig=true muss ladung_netz_kwh sichtbar machen, auch wenn
    # laedt_aus_netz nicht explizit gesetzt ist (Implikation).
    felder = _feldnamen("speicher", {"arbitrage_faehig": True})
    assert "ladung_netz_kwh" in felder
    assert "speicher_ladepreis_cent" in felder


def test_resolver_arbitrage_und_laedt_aus_netz() -> None:
    felder = _feldnamen("speicher", {"arbitrage_faehig": True, "laedt_aus_netz": True})
    assert "ladung_netz_kwh" in felder
    assert "speicher_ladepreis_cent" in felder


# ----------------------------------------------------------------------------
# Backfill-Migration
# ----------------------------------------------------------------------------

def _seed_db():
    """In-Memory SQLite mit Minimal-`investitionen`-Tabelle und Fixtures."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE investitionen ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "typ VARCHAR(50) NOT NULL, "
            "parameter TEXT"
            ")"
        ))
        fixtures = [
            ("speicher", {"kapazitaet_kwh": 10, "arbitrage_faehig": True}),
            ("speicher", {"kapazitaet_kwh": 5, "arbitrage_faehig": False}),
            ("speicher", {"kapazitaet_kwh": 8, "arbitrage_faehig": True, "laedt_aus_netz": True}),
            ("speicher", None),  # parameter NULL
            ("e-auto", {"arbitrage_faehig": True}),  # falscher Typ — nicht anfassen
        ]
        for typ, params in fixtures:
            conn.execute(
                text("INSERT INTO investitionen (typ, parameter) VALUES (:typ, :p)"),
                {"typ": typ, "p": json.dumps(params) if params is not None else None},
            )
    return engine


def _load_params(engine, inv_id: int) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT parameter FROM investitionen WHERE id = :id"), {"id": inv_id}
        ).fetchone()
    if row is None or row[0] is None:
        return None
    return json.loads(row[0])


def test_migration_setzt_flag_bei_arbitrage() -> None:
    engine = _seed_db()
    with engine.begin() as conn:
        _migrate_speicher_laedt_aus_netz_backfill(conn)

    assert _load_params(engine, 1) == {
        "kapazitaet_kwh": 10, "arbitrage_faehig": True, "laedt_aus_netz": True
    }


def test_migration_laesst_nicht_arbitrage_speicher_in_ruhe() -> None:
    engine = _seed_db()
    with engine.begin() as conn:
        _migrate_speicher_laedt_aus_netz_backfill(conn)

    params = _load_params(engine, 2)
    assert params == {"kapazitaet_kwh": 5, "arbitrage_faehig": False}
    assert "laedt_aus_netz" not in params


def test_migration_ist_idempotent() -> None:
    engine = _seed_db()
    with engine.begin() as conn:
        _migrate_speicher_laedt_aus_netz_backfill(conn)
        # Zweiter Lauf darf nichts kaputt machen.
        _migrate_speicher_laedt_aus_netz_backfill(conn)

    # Bereits gesetzter Flag bleibt — keine Verdopplung.
    assert _load_params(engine, 3) == {
        "kapazitaet_kwh": 8, "arbitrage_faehig": True, "laedt_aus_netz": True
    }


def test_migration_ignoriert_null_parameter_und_andere_typen() -> None:
    engine = _seed_db()
    with engine.begin() as conn:
        _migrate_speicher_laedt_aus_netz_backfill(conn)

    assert _load_params(engine, 4) is None  # NULL bleibt NULL
    eauto = _load_params(engine, 5)
    assert eauto == {"arbitrage_faehig": True}  # e-auto bleibt unverändert


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

ALLE_TESTS = [
    test_resolver_ohne_flag_blendet_netzladung_aus,
    test_resolver_laedt_aus_netz_zeigt_nur_netzladung,
    test_resolver_arbitrage_impliziert_netzladung,
    test_resolver_arbitrage_und_laedt_aus_netz,
    test_migration_setzt_flag_bei_arbitrage,
    test_migration_laesst_nicht_arbitrage_speicher_in_ruhe,
    test_migration_ist_idempotent,
    test_migration_ignoriert_null_parameter_und_andere_typen,
]


def main() -> int:
    fehler = 0
    for fn in ALLE_TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            fehler += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    if fehler:
        print(f"\n{fehler} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(ALLE_TESTS)} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
