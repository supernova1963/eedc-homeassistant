"""N-234: Alle vier PDF-Berichte schreiben Zahlen deutsch — nicht nur einer.

**Der Befund:** Jahresbericht deutsch, Finanzbericht und Anlagendokumentation
englisch — „7.9 Jahre", „12.32 kWp" in einem ausgelieferten Dokument.

**Die Ursache war Erreichbarkeit, nicht Nachlässigkeit.** Die vier Formatierer
lebten als Jinja-Makros *innerhalb* von ``jahresbericht.html``; Jinja vererbt
Makros nicht über ``{% extends %}``. Der Fundtext nannte als Ansatz „es geht um
BENUTZUNG, nicht um Neubau" und verwies auf ``fmt_kwh``/``fmt_euro`` als
vorhandene Helfer — **die gab es als Python-Funktionen nie.** Deshalb steht der
SoT jetzt in ``services/pdf/formatierung.py`` und wird von ``engine.py`` in die
Jinja-Umgebung gehängt: eine Implementierung für Templates *und* Builder.

Die Proben greifen an drei Ebenen an, weil ein Fix auf jeder einzelnen davon
grün sein könnte, ohne zu wirken: die Funktion, der Builder-Context und das
gerenderte HTML.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition
from backend.services.pdf.engine import render_html
from backend.services.pdf.formatierung import (
    fmt_einheit,
    fmt_euro,
    fmt_kwh,
    fmt_pct,
    fmt_zahl,
)


# ── Ebene 1: der SoT selbst ───────────────────────────────────────────────

def test_n234_sot_schreibt_deutsch():
    """Tausenderpunkt und Dezimalkomma — der Dreischritt darf sich nicht selbst
    überschreiben (ein naives doppeltes ``replace`` liefert ``12.345.67``)."""
    assert fmt_zahl(12345.67, 2) == "12.345,67"
    assert fmt_euro(12345.67) == "12.345,67 €"
    assert fmt_kwh(12345) == "12.345 kWh"
    assert fmt_einheit(12.32, "kWp") == "12,32 kWp"
    assert fmt_einheit(7.9, "kWh", decimals=1) == "7,9 kWh"


def test_n234_prozent_traegt_das_leerzeichen_der_regel_0a():
    """Style-Guide Regel 0a: „% mit Leerzeichen"."""
    assert fmt_pct(12.34) == "12,3 %"
    assert fmt_pct(12.34, 2) == "12,34 %"


def test_n234_none_bleibt_der_gedankenstrich():
    """F-43 hängt daran: eine Lücke ist kein Nullwert.

    Ohne diesen Zweig würde ``fmt_kwh(None)`` abstürzen oder „0 kWh" liefern —
    genau die erfundene Null, gegen die F-43 gebaut wurde.
    """
    for f in (fmt_zahl, fmt_euro, fmt_kwh, fmt_pct):
        assert f(None) == "–"
    assert fmt_einheit(None, "kWp") == "–"


# ── Ebene 2 + 3: die Berichte, die vorher englisch schrieben ──────────────

async def _seed(db) -> int:
    anlage = Anlage(anlagenname="N-234", leistung_kwp=12.32,
                    standort_plz="10115", standort_ort="Berlin",
                    latitude=48.1372, longitude=11.5755)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=20000.0, leistung_kwp=12.32,
    ))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_n234_anlagendokumentation_schreibt_die_kwp_deutsch(db):
    """Der namensgebende Fall: „12.32 kWp" darf im HTML nicht mehr vorkommen."""
    from backend.services.pdf.builders.anlagendokumentation import (
        build_anlagendokumentation_context,
    )

    anlage_id = await _seed(db)
    ctx = await build_anlagendokumentation_context(db, anlage_id=anlage_id)
    html = render_html("anlagendokumentation.html", ctx)

    assert "12,32 kWp" in html
    assert "12.32 kWp" not in html


@pytest.mark.asyncio
async def test_n234_koordinaten_behalten_bewusst_den_punkt(db):
    """Die dokumentierte Ausnahme — sie ist eine Entscheidung, keine Lücke.

    Koordinaten sind hier ein Wert zum Weitergeben (Karte, Formular); mit Komma
    ließen sie sich nicht übernehmen. Steht so als Kommentar im Template. Diese
    Probe hält die Ausnahme fest, damit ein späterer Sweep sie nicht für einen
    vergessenen Fall hält und „korrigiert".
    """
    from backend.services.pdf.builders.anlagendokumentation import (
        build_anlagendokumentation_context,
    )

    anlage_id = await _seed(db)
    ctx = await build_anlagendokumentation_context(db, anlage_id=anlage_id)
    html = render_html("anlagendokumentation.html", ctx)

    assert "48.1372" in html


@pytest.mark.asyncio
async def test_n234_jahresbericht_bleibt_unveraendert_deutsch(db):
    """Gegenanker: der Bericht, der es schon richtig machte, darf nicht kippen.

    Die vier Makros sind aus dem Template entfernt und kommen jetzt aus der
    Umgebung. Wäre die Registrierung in ``engine.py`` falsch, stünde hier ein
    Jinja-Fehler oder ein leerer Wert.
    """
    from backend.models import Monatsdaten
    from backend.services.pdf.builders.jahresbericht import (
        build_jahresbericht_context,
    )

    anlage_id = await _seed(db)
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage_id, jahr=2025, monat=m,
                           einspeisung_kwh=1000.0, netzbezug_kwh=300.0))
    await db.commit()

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)
    html = render_html("jahresbericht.html", ctx)

    # 12 × 1000 kWh Einspeisung ⇒ Tausenderpunkt, kein Komma.
    assert "12.000 kWh" in html
    assert "12,000 kWh" not in html
