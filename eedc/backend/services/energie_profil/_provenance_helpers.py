"""
Provenance-Hilfsfunktionen für die Energie-Profil-Schreib-Pfade
(Etappe 3d Päckchen 3).

Aggregate-Schreib-Pfade (`aggregate_day`, `backfill_from_statistics`)
löschen pro Tag die alten TagesZusammenfassung-/TagesEnergieProfil-Rows
und schreiben sie neu. Das ist semantisch ein Rebuild aus stündlichen
Snapshots — kein Hierarchie-Konflikt zur Laufzeit, daher reicht
`seed_provenance` ohne Per-Feld-Audit-Log-Spam (24 × 15 Felder pro Tag
würden sonst zu massivem Audit-Log-Wachstum führen).

Wenn ein User später per Repair-Werkbank mit `force_override=True`
einen Wert auf der Aggregat-Row schreibt, gewinnt das gegen jede Auto-
Aggregation (Source `repair`, Stufe 0).
"""

from __future__ import annotations

from typing import Any

from backend.services.provenance import seed_provenance


# Top-Level-Spalten der TagesZusammenfassung, die als JSON-Sub-Key-Träger
# behandelt werden — Per-Sub-Key-Provenance statt Komplett-Marker auf der
# JSON-Spalte.
_TZ_JSON_SUBKEY_COLUMNS = ("komponenten_kwh", "komponenten_starts")
# Skip-Liste der Identifier- und Audit-Spalten.
_TZ_SKIP_COLUMNS = frozenset({
    "id", "anlage_id", "datum", "datenquelle", "stunden_verfuegbar",
    "source_provenance", "source_hash",
    # Stunden-Profile sind interne Caches, keine Aggregat-Werte
    "pv_prognose_stundenprofil", "solcast_prognose_stundenprofil",
})

# TagesEnergieProfil:
_TEP_JSON_SUBKEY_COLUMNS = ("komponenten",)
_TEP_SKIP_COLUMNS = frozenset({
    "id", "anlage_id", "datum", "stunde",
    "source_provenance", "source_hash",
})


def _seed_row(
    row: Any,
    *,
    source: str,
    writer: str,
    skip_columns: frozenset[str],
    json_subkey_columns: tuple[str, ...],
) -> None:
    """Setzt source_provenance auf eine fresh Aggregat-Row.

    Pro Row alle non-None Top-Level-Spalten + alle existierenden Sub-Keys
    der genannten JSON-Spalten unter dem übergebenen Source-Tag.
    """
    fields: list[str] = []
    json_subkeys: dict[str, list[str]] = {}
    for col in row.__table__.columns:
        name = col.name
        if name in skip_columns:
            continue
        val = getattr(row, name, None)
        if val is None:
            continue
        if name in json_subkey_columns:
            if isinstance(val, dict) and val:
                json_subkeys[name] = list(val.keys())
            continue
        fields.append(name)
    if not fields and not json_subkeys:
        return
    seed_provenance(
        row,
        source=source,
        writer=writer,
        fields=fields or None,
        json_subkeys=json_subkeys or None,
    )


def seed_tz_provenance(
    zusammenfassung: Any,
    *,
    writer: str,
    source: str = "auto:monatsabschluss",
) -> None:
    """Setzt source_provenance auf eine fresh TagesZusammenfassung-Row."""
    _seed_row(
        zusammenfassung,
        source=source,
        writer=writer,
        skip_columns=_TZ_SKIP_COLUMNS,
        json_subkey_columns=_TZ_JSON_SUBKEY_COLUMNS,
    )


def seed_tep_provenance(
    profil: Any,
    *,
    writer: str,
    source: str = "auto:monatsabschluss",
) -> None:
    """Setzt source_provenance auf eine fresh TagesEnergieProfil-Row."""
    _seed_row(
        profil,
        source=source,
        writer=writer,
        skip_columns=_TEP_SKIP_COLUMNS,
        json_subkey_columns=_TEP_JSON_SUBKEY_COLUMNS,
    )
