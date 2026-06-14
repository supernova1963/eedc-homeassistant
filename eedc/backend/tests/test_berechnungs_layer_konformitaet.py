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


# Pattern: gas-/öl-Kosten der Altanlage `(waerme / wirkungsgrad) * gaspreis / 100`
# — der drift-anfällige Kern der WP-Alternativkosten-Rechnung („was hätte die
# fossile Heizung gekostet"). Verlangt eine Division durch eine `…wirkungsgrad…`-
# Variable, gefolgt von `* <preis> / 100`; sehr spezifisch (die WP rechnet ihre
# EIGENEN Kosten über JAZ/COP/SCOP, nicht über `wirkungsgrad`).
_INLINE_GAS_KOSTEN_ALTANLAGE = re.compile(
    r'''/\s*[\w\["'\]]*wirkungsgrad[\w\["'\]]*\s*\)\s*\*\s*\w+\s*/\s*100'''
)

# Einzige Heimat der Fragment-Formel: der Helper `gas_kosten_altanlage`. Alle
# vier vormals duplizierten Sites (Aggregat, per-WP-Service, HA-Export-Sensor,
# Aussichten-Forecast) ziehen jetzt auf ihn → das Literal lebt nur noch in
# seinem Funktionsrumpf.
ALLOWED_GAS_KOSTEN_FILES = {
    "core/berechnungen/alternativkosten.py",   # gas_kosten_altanlage (SoT)
    "core/berechnungen/__init__.py",            # Re-Export
}

# Leer — die Schulden sind getilgt. Jede neue Inline-Kopie schlägt im Wächter
# an; eine bewusste Ausnahme müsste hier mit Begründung + Migrations-Trigger
# eingetragen werden (Format: relativer Pfad → Begründung).
GAS_KOSTEN_GRANDFATHERED: dict[str, str] = {}


def test_inline_gas_kosten_altanlage_nur_im_layer():
    """Die Altanlagen-Gaskosten-Formel `(waerme / wirkungsgrad) * preis / 100`
    darf nur in den designierten Helper-Heimaten oder (übergangsweise) in der
    Grandfathered-Liste stehen — sonst driftet die WP-Alternativkosten-Rechnung
    erneut (gleiche Klasse wie die in v3.x deduplizierten Einzel-Kopien)."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in ALLOWED_GAS_KOSTEN_FILES or rel in GAS_KOSTEN_GRANDFATHERED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INLINE_GAS_KOSTEN_ALTANLAGE.search(line):
                verstoesse.append((rel, line_no, line.strip()))

    assert not verstoesse, _format_verstoesse_meldung(
        verstoesse,
        regel='Inline `(waerme / wirkungsgrad) × gaspreis / 100` außerhalb der WP-Alternativkosten-Helfer',
    ) + (
        "\n\nSoT-Migration:\n"
        "  from backend.core.berechnungen import berechne_wp_alternativkosten_ersparnis\n"
        "  # bzw. services.wp_wirtschaftlichkeit.berechne_wp_ersparnis (per-WP).\n"
        "  # Neue Inline-Kopie? In GAS_KOSTEN_GRANDFATHERED mit Begründung eintragen."
    )


def test_gas_kosten_grandfathered_enthalten_pattern_noch():
    """Wenn eine grandfathered Datei das Pattern nicht mehr enthält, muss sie
    aus GAS_KOSTEN_GRANDFATHERED entfernt werden (gegen Eintrags-Rotten)."""
    veraltete: list[str] = []
    for rel in GAS_KOSTEN_GRANDFATHERED:
        path = _BACKEND_ROOT / rel
        if not path.exists():
            veraltete.append(f"{rel} — Datei existiert nicht mehr")
            continue
        text = path.read_text(encoding="utf-8")
        if not _INLINE_GAS_KOSTEN_ALTANLAGE.search(text):
            veraltete.append(
                f"{rel} — kein Gaskosten-Pattern mehr, Eintrag aus "
                f"GAS_KOSTEN_GRANDFATHERED entfernen"
            )
    assert not veraltete, (
        "Veraltete GAS_KOSTEN_GRANDFATHERED-Einträge:\n"
        + "\n".join(f"  - {e}" for e in veraltete)
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


# Pattern: Netzbezugskosten-Formel `… / 100 + …grundpreis` (Schläfer-Block 2).
# Nach der Konsolidierung lebt sie nur noch im Helper `berechne_netzbezug_kosten`.
# Die bare `kWh × ct / 100`-Multiplikation (ohne Grundpreis) bleibt bewusst
# inline und ist hier NICHT gemeint — der `+ …grundpreis`-Teil ist der Marker.
_INLINE_NETZBEZUG_KOSTEN = re.compile(r'''/\s*100\s*\+\s*[\w\["'\].]*grundpreis''')

ALLOWED_NETZBEZUG_KOSTEN_FILES = {
    "core/berechnungen/netzbezug_kosten.py",  # berechne_netzbezug_kosten (SoT)
}


def test_inline_netzbezug_kosten_nur_im_layer():
    """Die Netzbezugskosten-Formel `kWh × preis / 100 + grundpreis` darf nur im
    Helper `berechne_netzbezug_kosten` stehen — sonst driftet der Grundpreis
    erneut über die Finanz-Read-Sites (komponenten/uebersicht/aktueller_monat/
    calculations)."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in ALLOWED_NETZBEZUG_KOSTEN_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INLINE_NETZBEZUG_KOSTEN.search(line):
                verstoesse.append((rel, line_no, line.strip()))

    assert not verstoesse, _format_verstoesse_meldung(
        verstoesse,
        regel='Inline `kWh × preis / 100 + grundpreis` außerhalb von berechne_netzbezug_kosten',
    ) + (
        "\n\nSoT-Migration:\n"
        "  from backend.core.berechnungen import berechne_netzbezug_kosten\n"
        "  netzbezug_kosten = berechne_netzbezug_kosten(kwh, preis_cent, grundpreis_euro)"
    )


# Pattern: Inline-Eigenverbrauchsquote `eigenverbrauch… / (pv|erzeugung)… * 100`
# (Schläfer-Block 3). Nach der Konsolidierung lebt sie nur noch im Helper
# `eigenverbrauchsquote_prozent` (gecappt auf 100 %, Maintainer-Entscheid).
_INLINE_EV_QUOTE = re.compile(
    r'''eigenverbrauch\w*\s*/\s*(?:pv|erzeugung|gesamt_erzeugung)\w*\s*\*\s*100'''
)

# Erlaubt: Helfer-Heimat + dokumentierte Ausnahmen (kW-Live-Sichten +
# energie_profil/views.py = offener IA-V4-Phase-1A-Produktentscheid).
ALLOWED_EV_QUOTE_FILES = {
    "core/berechnungen/kennzahlen.py",            # eigenverbrauchsquote_prozent (SoT)
    "api/routes/live_dashboard.py",                # Live, kW statt kWh
    "services/live_komponenten_builder.py",        # Live, kW statt kWh
    "api/routes/energie_profil/views.py",          # IA-V4-Phase-1A-Produktentscheid
}


def test_inline_eigenverbrauchsquote_nur_im_layer():
    """Die Eigenverbrauchsquote `eigenverbrauch / erzeugung × 100` darf nur im
    Helper `eigenverbrauchsquote_prozent` (gecappt) oder den dokumentierten
    Ausnahmen (kW-Live / views.py) stehen — sonst driftet der 100-%-Cap erneut."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in ALLOWED_EV_QUOTE_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INLINE_EV_QUOTE.search(line):
                verstoesse.append((rel, line_no, line.strip()))

    assert not verstoesse, _format_verstoesse_meldung(
        verstoesse,
        regel='Inline `eigenverbrauch / erzeugung × 100` außerhalb von eigenverbrauchsquote_prozent',
    ) + (
        "\n\nSoT-Migration:\n"
        "  from backend.core.berechnungen import eigenverbrauchsquote_prozent\n"
        "  ev_quote = eigenverbrauchsquote_prozent(eigenverbrauch_kwh, pv_erzeugung_kwh)"
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
