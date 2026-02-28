"""
Utility-Funktionen für sonstige_positionen (strukturierte Erträge/Ausgaben).

Ersetzt die flachen sonderkosten_euro + sonderkosten_notiz Felder in
InvestitionMonatsdaten.verbrauch_daten durch ein strukturiertes Array.

Datenformat:
    {
        "sonstige_positionen": [
            {"bezeichnung": "THG-Quote", "betrag": 200.00, "typ": "ertrag"},
            {"bezeichnung": "Reparatur", "betrag": 150.00, "typ": "ausgabe"}
        ]
    }

Backward-kompatibel mit Legacy:
    {"sonderkosten_euro": 150.0, "sonderkosten_notiz": "Reparatur"}
"""

from typing import Any


def get_sonstige_positionen(verbrauch_daten: dict[str, Any] | None) -> list[dict]:
    """
    Liest sonstige_positionen aus verbrauch_daten.
    Legacy-Fallback: sonderkosten_euro/sonderkosten_notiz → einzelne Ausgabe-Position.
    Ändert das Input-Dict nicht (read-only).
    """
    if not verbrauch_daten:
        return []

    # Neues Format hat Vorrang
    if "sonstige_positionen" in verbrauch_daten:
        return verbrauch_daten["sonstige_positionen"] or []

    # Legacy-Format: on-the-fly konvertieren
    legacy_euro = verbrauch_daten.get("sonderkosten_euro")
    legacy_notiz = verbrauch_daten.get("sonderkosten_notiz", "")

    if legacy_euro is not None and legacy_euro > 0:
        return [{
            "bezeichnung": legacy_notiz or "Sonderkosten (migriert)",
            "betrag": float(legacy_euro),
            "typ": "ausgabe"
        }]

    return []


def berechne_sonstige_summen(verbrauch_daten: dict[str, Any] | None) -> dict:
    """
    Berechnet Aufschlüsselung: ertraege_euro, ausgaben_euro, netto_euro.
    netto_euro ist positiv wenn Erträge > Ausgaben.
    """
    positionen = get_sonstige_positionen(verbrauch_daten)
    ertraege = sum(
        p.get("betrag", 0) or 0
        for p in positionen
        if p.get("typ") == "ertrag"
    )
    ausgaben = sum(
        p.get("betrag", 0) or 0
        for p in positionen
        if p.get("typ") == "ausgabe"
    )
    return {
        "ertraege_euro": round(ertraege, 2),
        "ausgaben_euro": round(ausgaben, 2),
        "netto_euro": round(ertraege - ausgaben, 2),
    }


def berechne_sonstige_netto(verbrauch_daten: dict[str, Any] | None) -> float:
    """Shorthand: gibt ertraege - ausgaben zurück."""
    return berechne_sonstige_summen(verbrauch_daten)["netto_euro"]
