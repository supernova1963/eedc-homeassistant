"""DI-1 — Kennzahlen-Drift-Inventur: WP-CO₂-Ersparnis (gemessen) über EINEN
kanonischen Helper.

Hintergrund (Memory `project_kennzahlen_drift_inventur`, ADR-001): die
CO₂-Ersparnis einer Wärmepumpe aus gemessenen Werten wurde an mehreren
Read-Sites gebaut. Cockpit und Social-Share rechneten korrekt
(`wärme/η_gas × f_gas − strom × f_strom`), der WeasyPrint-Jahresbericht dagegen
nur `wärme × f_gas` — OHNE Wirkungsgrad-Umrechnung und OHNE Abzug des
WP-Strom-CO₂ → die WP-Ersparnis war deutlich überhöht (Demo 2025:
2280,7 → 1567,1 kg, +45 %).

Drei-Punkte-Muster (ADR-001):
  A. Helper-Kontrakt — `co2_wp_ersparnis_kg` als einzige Formel-Stelle.
  B. Statischer Wächter — die Inline-Formel darf nur in `core/calculations.py`
     (dem Helper) stehen.
  C. Cross-Endpoint-Symmetrie — Cockpit == Jahresbericht für dieselbe Anlage.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from backend.core.calculations import (
    CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_STROM_KG_KWH,
    co2_wp_ersparnis_kg,
)
from backend.core.wirtschaftlichkeit_defaults import WP_WIRKUNGSGRAD_GAS_DEFAULT
from backend.models import Anlage, Investition, InvestitionMonatsdaten


# ── A. Helper-Kontrakt ──────────────────────────────────────────────────────

@pytest.mark.parametrize("waerme,strom,erwartet", [
    # Demo-Referenz 2025 (Anlage 1): 11347 kWh Wärme, 2545 kWh Strom
    (11347.0, 2545.0,
     11347.0 / WP_WIRKUNGSGRAD_GAS_DEFAULT * CO2_FAKTOR_GAS_KG_KWH - 2545.0 * CO2_FAKTOR_STROM_KG_KWH),
    # Demo-Referenz 2024: 6405 / 1400
    (6405.0, 1400.0,
     6405.0 / WP_WIRKUNGSGRAD_GAS_DEFAULT * CO2_FAKTOR_GAS_KG_KWH - 1400.0 * CO2_FAKTOR_STROM_KG_KWH),
    (0.0, 0.0, 0.0),          # keine Wärme → 0
    (0.0, 500.0, 0.0),        # WP vorhanden, aber keine gemessene Wärme → 0
])
def test_co2_wp_helper_werte(waerme, strom, erwartet):
    assert co2_wp_ersparnis_kg(waerme, strom) == pytest.approx(erwartet, abs=1e-6)


def test_co2_wp_helper_negativ_bei_schlechter_jaz():
    """Sehr schlechte JAZ (viel Strom, wenig Wärme) → Komponente darf negativ
    werden (die Anzeige-Sites klammern die Gesamt-Bilanz per max(0, …))."""
    # 1000 kWh Wärme, 2000 kWh Strom: 1000/0,9×0,201=223,3 − 2000×0,38=760 → < 0
    assert co2_wp_ersparnis_kg(1000.0, 2000.0) < 0


def test_co2_wp_helper_demo_2025_regressionswert():
    """Fixer Zahlwert als Regressions-Anker (Demo 2025)."""
    assert co2_wp_ersparnis_kg(11347.0, 2545.0) == pytest.approx(1567.06, abs=0.01)


# ── B. Statischer Wächter: Inline-Formel nur im Helper ──────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parents[1]  # eedc/backend/

# Kanonische Inline-Formel = `… / WP_WIRKUNGSGRAD_GAS_DEFAULT … * … CO2_FAKTOR_GAS…`
# in einer Zeile. Genau diese Kombination stand früher im Cockpit/Social und
# gehört jetzt ausschließlich in den Helper.
_INLINE_WP_CO2 = re.compile(
    r'WP_WIRKUNGSGRAD_GAS_DEFAULT.*CO2_FAKTOR_GAS_KG_KWH'
)

# Einzige erlaubte Stelle: der Helper selbst.
_ALLOWED_WP_CO2_FILES = {
    "core/calculations.py",
}


def _iter_py_files():
    for path in _BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(_BACKEND_ROOT).as_posix()
        if rel.startswith(("tests/", "venv/")) or "__pycache__" in rel:
            continue
        yield path, rel


def test_inline_wp_co2_formel_nur_im_helper():
    """Die gemessene WP-CO₂-Formel (`/η_gas × f_gas`) darf nur in
    `core/calculations.py` (dem Helper `co2_wp_ersparnis_kg`) stehen —
    sonst driftet die WP-Ersparnis wieder zwischen den Read-Sites (DI-1)."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in _ALLOWED_WP_CO2_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INLINE_WP_CO2.search(line):
                verstoesse.append((rel, line_no, line.strip()))
    assert not verstoesse, (
        "Inline-WP-CO₂-Formel außerhalb des Helpers `co2_wp_ersparnis_kg` "
        "gefunden — bitte den Helper aus core.calculations importieren "
        f"(ADR-001/DI-1):\n" + "\n".join(f"  {r}:{n}  {t}" for r, n, t in verstoesse)
    )


def test_gas_co2_faktor_nur_im_helper():
    """Der Gas-CO₂-Faktor `CO2_FAKTOR_GAS_KG_KWH` darf nur in
    `core/calculations.py` referenziert werden.

    DI-2-A: Das WP-Dashboard (`investitionen/dashboards.py`) rechnete die
    vermiedene Gas-CO₂ als `wärme × f_gas` — mit dem korrekten Faktor, aber
    OHNE die η_gas-Rückrechnung des Helpers → als 4. WP-CO₂-Read-Site driftete
    es sichtbar gegen die 3 DI-1-Stellen. Der `/η_gas × f_gas`-Wächter oben
    fing diese Variante NICHT (ihr fehlte gerade `WP_WIRKUNGSGRAD_GAS_DEFAULT`).
    Da vermiedenes Gas-CO₂ ausschließlich in `co2_wp_ersparnis_kg` gebildet
    wird, gehört der Faktor selbst nur dorthin (die Alternativkosten-Tabelle in
    `berechne_wärmepumpe_einsparung` liegt in derselben Datei = erlaubt)."""
    verstoesse: list[tuple[str, int, str]] = []
    for path, rel in _iter_py_files():
        if rel in _ALLOWED_WP_CO2_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "CO2_FAKTOR_GAS_KG_KWH" in line:
                verstoesse.append((rel, line_no, line.strip()))
    assert not verstoesse, (
        "`CO2_FAKTOR_GAS_KG_KWH` außerhalb von core/calculations.py gefunden — "
        "die vermiedene Gas-CO₂ gehört in `co2_wp_ersparnis_kg` (ADR-001/DI-2-A):\n"
        + "\n".join(f"  {r}:{n}  {t}" for r, n, t in verstoesse)
    )


# ── C. Cross-Endpoint-Symmetrie: Cockpit == Jahresbericht ───────────────────

async def _seed_wp_anlage(db) -> tuple[int, int]:
    """Anlage mit EINER Wärmepumpe, ein Monat gemessener Daten.
    Wärme = 10000 (Heizung) + 2000 (WW) = 12000 kWh, Strom = 3000 kWh."""
    anlage = Anlage(anlagenname="WP-Symmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Test-WP",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(wp)
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=1,
        verbrauch_daten={
            # kanonischer Wärme-Key (`heizenergie_kwh`) — das WP-Dashboard liest
            # ihn roh, Cockpit/Jahresbericht über `get_wp_heizenergie_kwh`.
            "heizenergie_kwh": 10000, "warmwasser_kwh": 2000,
            "stromverbrauch_kwh": 3000,
        },
    ))
    await db.commit()
    return anlage.id, 2025


async def test_cross_endpoint_wp_co2_symmetrisch(db):
    """Cockpit-Übersicht, Jahresbericht UND WP-Dashboard liefern für dieselbe
    WP-Anlage dieselbe WP-CO₂-Ersparnis (= Helper-Wert). Erwartung:
    12000/0,9×0,201 − 3000×0,38 = 2680 − 1140 = 1540,0 kg.

    DI-2-A: das WP-Dashboard ist die 4. Read-Site — vor dem Fix rechnete es
    `wärme × f_gas − strom × f_strom` OHNE η_gas und wich damit ab."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.investitionen.dashboards import (
        get_waermepumpe_dashboard,
    )
    from backend.services.pdf.builders.jahresbericht import (
        build_jahresbericht_context,
    )

    anlage_id, jahr = await _seed_wp_anlage(db)
    erwartet = co2_wp_ersparnis_kg(12000.0, 3000.0)
    assert erwartet == pytest.approx(1540.0, abs=0.05)

    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=jahr, db=db)
    assert ueb.co2_wp_kg == pytest.approx(round(erwartet, 1), abs=0.05)

    ctx = await build_jahresbericht_context(db, anlage_id, jahr)
    assert ctx["co2"]["wp_kg"] == pytest.approx(erwartet, abs=0.05)

    # WP-Dashboard aggregiert alle Monate der WP (hier genau einer) → Helfer
    # auf denselben Eingaben.
    dash = await get_waermepumpe_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, db=db
    )
    assert len(dash) == 1
    dash_co2 = dash[0].zusammenfassung["co2_ersparnis_kg"]
    assert dash_co2 == pytest.approx(round(erwartet, 1), abs=0.05)

    # Deckungsgleich (der eine Wert, nicht drei Formeln)
    assert ueb.co2_wp_kg == pytest.approx(round(ctx["co2"]["wp_kg"], 1), abs=0.05)
    assert dash_co2 == pytest.approx(ueb.co2_wp_kg, abs=0.05)
