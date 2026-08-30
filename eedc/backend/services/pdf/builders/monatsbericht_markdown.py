"""Markdown-Fassung des Monatsberichts — **derselbe Context**, andere Form.

Wer den Bericht posten will, kopiert Text; wer ihn ablegen will, lädt das PDF.
Beide Wege gehen durch ``builders/monatsbericht.py`` und lesen dieselben
``Abschnitt``/``Zeile``-Objekte.

⛔ **Dieses Modul rechnet nicht und formatiert keine Zahl.** Es setzt fertige
Zeichenketten in Markdown-Tabellen. Der Grund steht im Kopf des Builders:
**N-7** war die eigene Netto-Ertrag-Kurzformel einer zweiten Textvorlage, und
sie ist mit dieser Vorlage verschwunden statt behoben zu werden. Ein zweiter
Renderer mit eigener Rechnung wäre ihre Wiederauferstehung — diesmal in einem
Text, der im Forum landet.

Die Probe dazu:
``test_monatsbericht.py::test_beide_formate_nennen_dieselben_zahlen``.
"""
from __future__ import annotations

from typing import Any

#: Zeichen, die in einer Markdown-Tabellenzelle die Spalte sprengen.
def _zelle(text: str) -> str:
    """``|`` in einer Zelle beendet die Spalte — es wird maskiert, nicht entfernt.

    Betroffen sind reale Werte: Gerätebezeichnungen kommen aus der Eingabe des
    Anwenders. Ein entferntes Zeichen wäre eine stille Änderung seiner Daten.
    """
    return (text or "").replace("|", "\\|").replace("\n", " ")


def render_monatsbericht_markdown(context: dict[str, Any]) -> str:
    """Der Bericht als Markdown-Text (UTF-8, keine HTML-Fragmente)."""
    anlage = context["anlage"]
    zeitraum = context["zeitraum"]

    kopf = f"Monatsbericht {zeitraum['label']}"
    if anlage["name"]:
        kopf += f" — {anlage['name']}"

    aus: list[str] = [f"# {kopf}", ""]

    if context["mit_identitaet"] and anlage["standort"]:
        aus.append(f"**Standort:** {anlage['standort']}  ")
    aus.append(f"**Anlagenleistung:** {anlage['leistung_kwp']}  ")
    aus.append(f"**Erzeugt am:** {context['erzeugt_am']}")
    aus.append("")

    # Die Hinweise stehen VOR den Zahlen — sie sagen, was eine Zahl nicht
    # enthält (ADR-002/P4). Unter der Tabelle würden sie beim Kopieren
    # abgeschnitten, und dann behauptet der Text mehr, als gemessen wurde.
    if context["hinweise"]:
        aus.append("> **Hinweise zu den Werten**")
        for h in context["hinweise"]:
            aus.append(f"> - {h}")
        aus.append("")

    if context["leer"]:
        aus.append(
            "_Für diesen Monat liegen zu den gewählten Themen keine Werte vor._"
        )
        aus.append("")
    else:
        for abschnitt in context["abschnitte"]:
            aus.append(f"## {abschnitt.titel}")
            aus.append("")
            aus.append("| | |")
            aus.append("| --- | --- |")
            for zeile in abschnitt.zeilen:
                wert = _zelle(zeile.wert)
                if zeile.hinweis:
                    wert = f"{wert} _{_zelle(zeile.hinweis)}_" if wert else f"_{_zelle(zeile.hinweis)}_"
                aus.append(f"| {_zelle(zeile.label)} | {wert} |")
            aus.append("")
            if abschnitt.hinweis:
                aus.append(f"_{_zelle(abschnitt.hinweis)}_")
                aus.append("")

    # Was der Park-Schalter weggelassen hat, steht IM Text. Der Zustand lebt im
    # Browser des Erzeugers — wer den Bericht später liest, kann sonst nicht
    # wissen, dass etwas fehlt.
    if context["weggelassen"]:
        aus.append(
            "_Weggelassen (in der Monatsansicht geparkt): "
            + ", ".join(_zelle(t) for t in context["weggelassen"])
            + "._"
        )
        aus.append("")

    aus.append("---")
    aus.append("")
    aus.append("Erstellt mit eedc — github.com/supernova1963/eedc-homeassistant")
    aus.append("")
    return "\n".join(aus)
