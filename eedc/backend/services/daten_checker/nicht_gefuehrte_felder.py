"""Hilfen der N-393-Regel «Wert in einem Feld, das das Gerät nicht führt» (`MonatsdatenChecks._check_werte_in_nicht_gefuehrten_feldern`).

Ausgelagert mit N-789 (#443, 10.11.2026), damit `monatsdaten.py` nicht über die Dateilängen-Baseline wächst: die
Kandidaten-Liste je Typ (für *Sonstiges* jedes dem Helfer bekannte Feld) und der Meldungstext für ein totes Feld an
einem *Sonstiges*-Gerät. Ob ein Feld tot ist, entscheidet weiter allein `groesse_gibt_es_am_geraet`.
"""
from typing import Optional

from backend.core.field_definitions import (
    INVESTITION_FELDER,
    SONSTIGES_ABGABE_LABEL,
    SONSTIGES_FELDER_BEKANNT,
    SONSTIGES_KATEGORIE_LABEL,
    SONSTIGES_VERBRAUCH_FELDER,
    ist_abgabe_kategorie,
    ist_gepflegte_sonstiges_kategorie,
)

#: Die Hauptgrößen eines früheren Erzeugers oder Verbrauchers — nur an ihnen steht am Abgabe-Gerät das Angebot
#: «in „Abgabe (kWh)“ nachtragen». Teilgrößen (Eigenverbrauch, Einspeisung, PV-/Netz-Bezug) sind Teile davon; ein
#: zweites Angebot an ihnen nennte dasselbe Ziel ein zweites Mal (Master-Entscheid N-789).
_ABGABE_HAUPTGROESSEN: frozenset[str] = frozenset({"erzeugung_kwh", *SONSTIGES_VERBRAUCH_FELDER})


def label_je_feld_nicht_gefuehrt(typ: str, param: dict) -> dict[str, str]:
    """Die Kandidaten der N-393-Regel mit ihrem Label: ``{feld: label}``.

    Für die Listen-Typen nur Felder mit harter ``bedingung`` (alle anderen spart
    die Lesetür ohnehin aus, die Vorprüfung hält den Lauf kurz). Für *Sonstiges*
    (Dict je Kategorie, N-789) jedes dem Helfer bekannte Feld
    (``_sonstiges_label_je_feld``), sobald die Kategorie gepflegt ist — ohne
    gepflegte Kategorie liest der Monat alles.
    """
    felder = INVESTITION_FELDER.get(typ)
    if typ == "sonstiges" and isinstance(felder, dict):
        if not ist_gepflegte_sonstiges_kategorie((param or {}).get("kategorie")):
            return {}
        return _sonstiges_label_je_feld(felder)
    if not isinstance(felder, list):
        return {}
    return {
        f["feld"]: f.get("label", f["feld"])
        for f in felder
        if isinstance(f, dict) and f.get("bedingung")
    }


def _sonstiges_label_je_feld(felder: dict) -> dict[str, str]:
    """Jedes Feld, das der Helfer für *Sonstiges* kennt (``SONSTIGES_FELDER_BEKANNT``), mit Label: das des ersten
    Treffers in den Kategorie-Listen; ein Legacy-Alias der Ersatzgruppe (``verbrauch_kwh``) trägt das Label seines
    kanonischen Geschwisters (``SONSTIGES_VERBRAUCH_FELDER[0]``), sonst steht der Feldschlüssel selbst — ein totes
    Feld wird auch ohne Registry-Label gemeldet."""
    label_je_feld: dict[str, str] = {}
    for liste in felder.values():
        for f in liste:
            label_je_feld.setdefault(f["feld"], f.get("label", f["feld"]))
    kanonisch = SONSTIGES_VERBRAUCH_FELDER[0]
    for feld in SONSTIGES_FELDER_BEKANNT - label_je_feld.keys():
        if feld in SONSTIGES_VERBRAUCH_FELDER and kanonisch in label_je_feld:
            label_je_feld[feld] = label_je_feld[kanonisch]
        else:
            label_je_feld[feld] = feld
    return label_je_feld


def text_sonstiges_totes_feld(
    name: str, feld: str, label: str, anzahl: int, monate_str: str, kategorie: Optional[str],
) -> tuple[str, str]:
    """Meldung und Details für ein totes Feld an einem *Sonstiges*-Gerät (N-789, #443).

    Das Kategorie-Label kommt aus ``SONSTIGES_KATEGORIE_LABEL`` (Anwender-Sprache, nie der Registry-Schlüssel). Bei
    «Abgabe an Dritte» steht an einer Hauptgröße (``_ABGABE_HAUPTGROESSEN``) das Angebot «in Abgabe (kWh)
    nachtragen», sonst der allgemeine Ausweg — ein Angebot, kein Urteil.
    """
    kategorie_label = SONSTIGES_KATEGORIE_LABEL.get(kategorie or "", kategorie)
    meldung = (
        f"{name}: {label} in {anzahl} Monat(en) gespeichert — ein Gerät der "
        f"Kategorie «{kategorie_label}» führt das Feld nicht"
    )
    if ist_abgabe_kategorie(kategorie) and feld in _ABGABE_HAUPTGROESSEN:
        ausweg = (
            f"Stammt er aus der Zeit vor der Umstellung auf „{SONSTIGES_ABGABE_LABEL}“, "
            "trage die Menge im Monatsabschluss in „Abgabe (kWh)“ ein "
            "und entferne den alten Wert mit „Wert entfernen“."
        )
    else:
        ausweg = (
            "Stimmt die Kategorie, entferne den Wert mit „Wert entfernen“. Soll er "
            "weiter zählen, stelle die Kategorie zurück — dann liest eedc das Feld wieder."
        )
    details = (
        f"{monate_str}. Der Wert zählt in keiner Bilanz. {ausweg} "
        "eedc löscht und verschiebt nichts von allein."
    )
    return meldung, details
