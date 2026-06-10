"""Konformitäts-Test für den Berechnungs-Layer (ADR-001).

Erzwingt maschinell: Whitelist-Konstanten und Inline-Σ-Patterns für die
zentralen Aggregat-Felder dürfen nur in `core/berechnungen/` existieren —
sonst entsteht Drift wie der BKW-Doppelzählungs-Bug (2026-05-19, Rainer-PN).

Bei einem neuen Domain-Verstoß bricht der Test mit klarer Fehlermeldung und
verweist auf das Migrations-Pattern.

Test-Strategie: Grep im Backend-Pfad, Whitelist erlaubter Stellen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_ROOT = Path(__file__).resolve().parents[1]  # eedc/backend/


# Erlaubte Stellen für die SoT-Definition.
ALLOWED_PV_PREFIXES_FILES = {
    "core/berechnungen/energie.py",     # SoT-Definition
    "core/berechnungen/__init__.py",     # Re-Export
}

# Erlaubte Stellen, an denen Inline-Patterns historisch gewachsen sind
# und schrittweise migriert werden (siehe project_berechnungs_layer_offen.md).
# Jeder Eintrag hier ist eine Schuld, kein Persil-Schein — bei nächstem
# Touch des betroffenen Codes muss die Stelle migrieren und aus dieser
# Liste verschwinden.
#
# Hinweis: Dies sind die Dateien mit dem **exakten** Pattern `("pv_", "bkw_")`
# oder `startswith("pv_") or ... startswith("bkw_")`. Weitere PV-Aggregations-
# Konsumenten (views.py, live_wetter.py, live_history_service.py,
# live_komponenten_builder.py) nutzen andere Schreibweisen (z.B. nur
# `startswith("pv_")` oder generisches komponenten_kwh-Iteration) und werden
# beim nächsten Touch separat migriert — siehe project_berechnungs_layer_offen.md.
INLINE_PATTERN_GRANDFATHERED: dict[str, str] = {
    # Format: relativer Pfad → Begründung + ungefährer Migrations-Trigger
    # PRIO 1 (prognosen.py + repair.py) wurde 2026-05-23 migriert; die Liste
    # bleibt als Andock-Punkt für zukünftige Schuld erhalten.
}


def _iter_py_files():
    """Alle .py-Dateien unter eedc/backend/, ohne tests/, venv/, __pycache__/."""
    for path in _BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(_BACKEND_ROOT).as_posix()
        if rel.startswith(("tests/", "venv/")):
            continue
        if "__pycache__" in rel:
            continue
        yield path, rel


# Pattern: `("pv_", "bkw_")`-Tuple (mit/ohne Spaces)
_PV_BKW_TUPLE = re.compile(r'''\(\s*["']pv_["']\s*,\s*["']bkw_["']\s*\)''')

# Pattern: Inline `k.startswith("pv_") or k.startswith("bkw_")` und ähnliche
_INLINE_STARTSWITH = re.compile(
    r'''\.startswith\(\s*["']pv_["']\s*\)\s*or\s*\w+\.startswith\(\s*["']bkw_["']\s*\)'''
)

# Pattern: Inline-Einspeise-Erlös `einspeisung… * …verguetung… / 100` statt SoT
# `einspeise_erloes_euro()` (ADR-001, M3). Fängt die ungekürzte Erlös-Formel,
# die den §51-Abzug umgeht. Arbitrage-Spread (`strompreis - verguetung`),
# BKW-unvergütet (`= 0`) und kombinierte Netto-Formeln (`einspeisung *
# einspeise_cent`) matchen bewusst NICHT.
_INLINE_EINSPEISE_ERLOES = re.compile(
    r'''einspeis\w*\s*\*\s*\w*verguetung\w*\s*/\s*100'''
)

# Erlaubte Stellen für die Einspeise-Erlös-SoT (Definition + Re-Export + der
# DB-Lookup-Service, der den Layer-Helper bündelt).
ALLOWED_EINSPEISE_ERLOES_FILES = {
    "core/berechnungen/einspeise_erloes.py",
    "core/berechnungen/__init__.py",
}


def test_pv_bkw_whitelist_tuple_nur_im_layer():
    """Die `("pv_", "bkw_")`-Tuple darf nur in `core/berechnungen/` stehen."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in ALLOWED_PV_PREFIXES_FILES:
            continue
        if rel in INLINE_PATTERN_GRANDFATHERED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _PV_BKW_TUPLE.search(line):
                verstoesse.append((rel, line_no, line.strip()))

    assert not verstoesse, _format_verstoesse_meldung(
        verstoesse,
        regel='`("pv_", "bkw_")`-Tuple außerhalb von core/berechnungen/',
    )


def test_inline_startswith_nur_im_layer_oder_grandfathered():
    """Inline `startswith("pv_") or startswith("bkw_")`-Patterns nur im Layer
    oder in der Grandfathered-Liste."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in ALLOWED_PV_PREFIXES_FILES:
            continue
        if rel in INLINE_PATTERN_GRANDFATHERED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INLINE_STARTSWITH.search(line):
                verstoesse.append((rel, line_no, line.strip()))

    assert not verstoesse, _format_verstoesse_meldung(
        verstoesse,
        regel='Inline `startswith("pv_") or startswith("bkw_")` außerhalb von core/berechnungen/',
    )


def test_inline_einspeise_erloes_nur_im_layer():
    """Die ungekürzte Inline-Erlös-Formel `einspeisung… * …verguetung… / 100`
    darf nur in der Einspeise-Erlös-SoT stehen — sonst umgeht sie den
    §51-Abzug (ADR-001, M3)."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in ALLOWED_EINSPEISE_ERLOES_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INLINE_EINSPEISE_ERLOES.search(line):
                verstoesse.append((rel, line_no, line.strip()))

    assert not verstoesse, _format_verstoesse_meldung(
        verstoesse,
        regel='Inline `einspeisung × verguetung / 100` außerhalb der Einspeise-Erlös-SoT',
    ) + (
        "\n\nSoT-Migration:\n"
        "  from backend.core.berechnungen import einspeise_erloes_euro\n"
        "  erloes = einspeise_erloes_euro(einspeisung_kwh, neg_preis_kwh, verguetung_ct).erloes_euro\n"
        "  # neg_preis_kwh=None wenn keine §51-Negativpreis-Spalte vorliegt "
        "(Projektion/Aggregat)."
    )


def test_grandfathered_dateien_existieren_und_enthalten_pattern():
    """Wenn eine Datei aus der Grandfathered-Liste keine Verstöße mehr enthält,
    muss sie aus der Liste entfernt werden — sonst rotten die Einträge."""
    veraltete: list[str] = []
    for rel, _grund in INLINE_PATTERN_GRANDFATHERED.items():
        path = _BACKEND_ROOT / rel
        if not path.exists():
            veraltete.append(f"{rel} — Datei existiert nicht mehr")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hat_tuple = bool(_PV_BKW_TUPLE.search(text))
        hat_inline = bool(_INLINE_STARTSWITH.search(text))
        if not hat_tuple and not hat_inline:
            veraltete.append(
                f"{rel} — kein Verstoß-Pattern mehr, Eintrag aus "
                f"INLINE_PATTERN_GRANDFATHERED entfernen"
            )

    assert not veraltete, (
        "Veraltete Grandfathered-Einträge in test_berechnungs_layer_konformitaet.py:\n"
        + "\n".join(f"  - {e}" for e in veraltete)
    )


# Pattern: bare `.startswith("pv_")`-Literal (ohne zentralen Prefix-Import).
# Die Live-Keyspace-Konsumenten (live_history_service, live_komponenten_builder)
# legen Erzeuger einheitlich unter `pv_` ab; sie müssen die Prefix-Quelle aus
# `PV_KOMPONENTEN_PREFIXE` beziehen statt das Literal selbst zu führen
# (Slice A des Pre-IA-V4-Sweeps, ADR-001).
_BARE_PV_STARTSWITH = re.compile(r'''\.startswith\(\s*["']pv_["']\s*\)''')

# Live-Keyspace-Module, die nach Slice-A-Migration NUR noch über die zentrale
# Prefix-Liste auf PV-Komponenten prüfen dürfen.
PV_PREFIX_ZENTRALISIERTE_MODULE = (
    "services/live_history_service.py",
    "services/live_komponenten_builder.py",
)


def test_live_keyspace_module_nutzen_zentrale_pv_prefix_liste():
    """Die migrierten Live-Module dürfen kein bare `startswith("pv_")`-Literal
    mehr führen, sondern müssen `PV_KOMPONENTEN_PREFIXE` importieren (Slice A)."""
    verstoesse: list[str] = []
    for rel in PV_PREFIX_ZENTRALISIERTE_MODULE:
        path = _BACKEND_ROOT / rel
        text = path.read_text(encoding="utf-8")
        if "PV_KOMPONENTEN_PREFIXE" not in text:
            verstoesse.append(
                f"{rel}: importiert PV_KOMPONENTEN_PREFIXE nicht mehr"
            )
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _BARE_PV_STARTSWITH.search(line):
                verstoesse.append(
                    f"{rel}:{line_no}: bare startswith(\"pv_\") — "
                    f"über PV_KOMPONENTEN_PREFIXE zentralisieren"
                )

    assert not verstoesse, (
        "Live-Keyspace-PV-Prefix-Zentralisierung verletzt:\n"
        + "\n".join(f"  - {v}" for v in verstoesse)
        + "\n\nMigration:\n"
        "  from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE\n"
        "  any(key.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)"
    )


def _format_verstoesse_meldung(
    verstoesse: list[tuple[str, int, str]], regel: str
) -> str:
    """Verstoß-Meldung mit Migrations-Anleitung."""
    if not verstoesse:
        return ""
    zeilen = [
        f"Berechnungs-Layer-Konformität verletzt ({regel}):",
        "",
    ]
    for rel, line_no, line in verstoesse:
        zeilen.append(f"  {rel}:{line_no}")
        zeilen.append(f"    {line}")
    zeilen.extend([
        "",
        "Migrations-Anleitung:",
        "  from backend.core.berechnungen import PV_KOMPONENTEN_PREFIXE, summe_pv_bkw_kwh",
        "  # statt eigene Whitelist / inline-startswith",
        "",
        "Falls der Code aus historischen Gründen noch nicht migriert ist,",
        "ergänze ihn in INLINE_PATTERN_GRANDFATHERED in diesem Test mit",
        "kurzer Begründung. Siehe `docs/ADR-001-BERECHNUNGS-LAYER.md`.",
    ])
    return "\n".join(zeilen)
