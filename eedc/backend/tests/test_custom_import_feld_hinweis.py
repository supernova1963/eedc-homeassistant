"""Custom-Import: die Zielfeld-Auswahl trägt den Erklärtext des Feldes mit.

Schwesterdateien: `test_custom_import_preview_inv_werte.py` (#222 — die *Vorschau*
zeigt die Investitions-Spalten) und `test_custom_import_einheit_non_energy.py`
(die Einheit eines nicht-energetischen Feldes). Gegenstand hier ist allein die
**Zuordnungs-Auswahl** in Schritt 2, also das, was der Anwender liest, *bevor* er
zuordnet.

## Der Fall

`_build_investition_felder` baute die Auswahl-Option bis zum 01.09.2026 aus
`label` + Einheit, sonst nichts. Der `hinweis` aus dem Felddefinitions-SoT — der
bei jedem Energiefeld sagt, ob eine **elektrische** oder eine **thermische**
Größe erwartet wird — blieb im Backend liegen.

Folge, real eingetreten: Ein Melder (dietmar1968, simon42 T89667 #283) ordnete
eine Umgebungswärme-Spalte seines Wärmepumpen-Exports auf ein Wärmemengen-Feld
zu. Die Option sagte nur „WP: <Gerät> – Warmwasser (kWh)"; dass dort die
*abgegebene* Wärme erwartet wird, stand ausschließlich in einem Hinweis, den
diese Fläche nie anzeigte. Der falsche Wert stand danach in jeder Sicht, die ihn
liest — inklusive einer Arbeitszahl unter 1.

⚠ Die zweite Hälfte der Antwort ist ein **schärferes Label** und steht in
`test_thermische_felder_benennen_ihre_groesse.py`. Beide Hälften sind nötig: das
Label wirkt in *jeder* Fläche, der Hinweis erklärt *hier* auch die Felder, deren
Größe sich nicht in zwei Wörtern sagen lässt.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.api.routes.custom_import.analyze import _build_investition_felder


def _wp(**parameter) -> SimpleNamespace:
    """Minimal-Investition — `_build_investition_felder` liest nur diese vier."""
    return SimpleNamespace(
        id=42,
        typ="waermepumpe",
        bezeichnung="Nibe F1255",
        parameter=parameter,
    )


def test_zielfeld_option_traegt_den_hinweis():
    """Der Erklärtext aus dem SoT erreicht die Auswahl."""
    felder = {f["id"]: f for f in _build_investition_felder([_wp()])}
    ww = felder["inv:42:warmwasser_kwh"]

    assert ww["hinweis"], "Zielfeld ohne Hinweis — der Anwender liest nur das Label."
    assert "thermisch" in ww["hinweis"].lower(), (
        f"Der Hinweis nennt die Größe nicht: {ww['hinweis']!r}"
    )


def test_der_hinweis_unterscheidet_elektrisch_von_thermisch():
    """Diskriminierung, nicht nur Anwesenheit.

    Ein Hinweis, der bei **beiden** Feldern dasselbe sagt, wäre wertlos — genau
    der Fall, gegen den diese Datei gebaut ist. Die Probe wäre trotzdem grün,
    wenn sie nur „ist gesetzt" prüfte.
    """
    felder = {
        f["id"]: f
        for f in _build_investition_felder([_wp(getrennte_strommessung=True)])
    }
    thermisch = felder["inv:42:warmwasser_kwh"]["hinweis"].lower()
    elektrisch = felder["inv:42:strom_warmwasser_kwh"]["hinweis"].lower()

    assert "thermisch" in thermisch and "thermisch" not in elektrisch
    assert "elektrisch" in elektrisch and "elektrisch" not in thermisch


def test_feld_ohne_hinweis_liefert_none_statt_zu_fehlen():
    """Der Schlüssel ist immer da — der Client prüft auf Inhalt, nicht auf Existenz.

    Fehlte er bei manchen Feldern ganz, müsste jede Lesestelle zwei Fälle
    unterscheiden. `None` ist die eine Form für „kein Hinweis".
    """
    for feld in _build_investition_felder([_wp()]):
        assert "hinweis" in feld, f"{feld['id']} führt den Schlüssel nicht"
        assert feld["hinweis"] is None or isinstance(feld["hinweis"], str)


def test_label_und_hinweis_sind_zwei_verschiedene_aussagen():
    """Das Label bleibt kurz, der Hinweis erklärt — keiner ersetzt den anderen.

    Hielte das Label bereits den vollen Hinweistext, wäre die Auswahlliste
    unlesbar; wäre der Hinweis eine Kopie des Labels, hätte er keinen Wert.
    """
    ww = next(
        f for f in _build_investition_felder([_wp()])
        if f["id"] == "inv:42:warmwasser_kwh"
    )
    assert "Warmwasser-Wärme" in ww["label"], (
        "Das Label muss die Größe selbst tragen (s. Schwesterdatei)."
    )
    assert ww["hinweis"] != ww["label"]
    assert len(ww["hinweis"]) > len(ww["label"])
