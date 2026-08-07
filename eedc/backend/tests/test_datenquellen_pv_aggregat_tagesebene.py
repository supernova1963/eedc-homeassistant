"""Die Zuordnungs-Seite sagt über den PV-Anlagenzähler die Wahrheit (F-7).

Forum kaba-kakao (T89667 #109, 2026-08-07): PV-Gesamtzähler bei „Anlage (Basis)"
zugeordnet, die beiden Strings haben **nur** Leistungssensoren. Die Fläche
meldete an den String-Zeilen „Die PV-Erzeugung ist bereits an anderer Stelle
zugeordnet" — also *hier ist nichts zu tun* —, während der Daten-Checker
dieselbe Stelle als Lücke führte. Beides kann nicht stimmen: das Aggregat
versorgt den **Monat** (`resolve_pv_je_modul`), die Tages-/Stundenebene
entsteht ausschließlich aus kumulativen Zählern **je Komponente**.

Zwei Regeln, die hier festgehalten werden:

1. **Warnen nur, wo es auflösbar ist.** Liegt ein Leistungssensor je Erzeuger
   vor, lässt sich daraus in HA ein Integral-Sensor bauen ⇒ Warndreieck mit dem
   Weg. Wer nur einen Summenzähler besitzt, konfiguriert nichts falsch und
   bekommt kein Warndreieck ([[feedback_user_fehlermeldungen]]).
2. **Die Herkunft der Gruppen-Deckung zählt.** Deckt nur das Aggregat die
   Gruppe `pv_energie`, gilt das für den Monat; deckt umgekehrt eine Komponente
   sie, bleibt „bereits an anderer Stelle zugeordnet" an der Basis-Zeile richtig.
"""

from __future__ import annotations

from backend.services.datenquellen_validierung import (
    finde_aggregat_ohne_tageszaehler,
    finde_redundante_aggregate,
    stufe_bedarf_ein,
)

AGG = "basis_energy_pv_gesamt_kwh"
WEST_KWH = "inv_energy_1_pv_erzeugung_kwh"
WEST_W = "inv_live_1_leistung_w"
OST_KWH = "inv_energy_2_pv_erzeugung_kwh"
OST_W = "inv_live_2_leistung_w"


def _feld(fid, feld, typ, belegt):
    return {"id": fid, "feld": feld, "typ": typ, "belegt": belegt}


def _stephans_lage(mit_leistung: bool = True) -> list[dict]:
    return [
        _feld(AGG, "pv_gesamt_kwh", "basis", True),
        _feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", False),
        _feld(WEST_W, "leistung_w", "pv-module", mit_leistung),
        _feld(OST_KWH, "pv_erzeugung_kwh", "pv-module", False),
        _feld(OST_W, "leistung_w", "pv-module", mit_leistung),
    ]


def test_warnt_am_aggregat_wenn_die_strings_nur_leistung_haben():
    probleme = finde_aggregat_ohne_tageszaehler(_stephans_lage())

    assert set(probleme) == {AGG}
    p = probleme[AGG]
    assert p["schwere"] == "warning"
    assert p["art"] == "nur_monat"
    assert "Monatswerte" in p["text"]
    assert "Integral-Sensor" in p["text"]
    # Die auflösenden Felder werden benannt (wie bei `redundant`).
    assert set(p["wirksame_felder"]) == {WEST_W, OST_W}


def test_schweigt_ohne_leistungssensor():
    """Nur ein Summenzähler vorhanden ⇒ nichts, was der Anwender besser machen
    könnte ⇒ kein Warndreieck (der Hinweistext an der Komponente bleibt)."""
    assert finde_aggregat_ohne_tageszaehler(_stephans_lage(mit_leistung=False)) == {}


def test_schweigt_wenn_jede_komponente_ihren_zaehler_hat():
    """Keine Lücke ⇒ Zuständigkeit liegt bei `finde_redundante_aggregate`,
    das dann „wirkungslos" meldet. Nie beide gleichzeitig."""
    felder = [
        _feld(AGG, "pv_gesamt_kwh", "basis", True),
        _feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", True),
        _feld(WEST_W, "leistung_w", "pv-module", True),
    ]

    assert finde_aggregat_ohne_tageszaehler(felder) == {}
    assert AGG in finde_redundante_aggregate(felder)  # die andere Meldung greift


def test_schweigt_ohne_belegtes_aggregat():
    felder = [
        _feld(AGG, "pv_gesamt_kwh", "basis", False),
        _feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", False),
        _feld(WEST_W, "leistung_w", "pv-module", True),
    ]

    assert finde_aggregat_ohne_tageszaehler(felder) == {}


# ─── Gegenseite: der Text an der Komponenten-Zeile ──────────────────────────

def _bedarf_feld(fid, feld, typ, belegt, gruppe):
    return {"id": fid, "feld": feld, "typ": typ, "belegt": belegt,
            "bedarf": "pflicht", "bedarf_gruppe": gruppe, "bedingung_anlage": None}


def test_komponenten_zeile_nennt_die_monats_grenze():
    """Nur das Aggregat trägt die Gruppe ⇒ „für die Monatswerte abgedeckt"."""
    felder = [
        _bedarf_feld(AGG, "pv_gesamt_kwh", "basis", True, "pv_energie"),
        _bedarf_feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", False, "pv_energie"),
    ]

    ergebnis = stufe_bedarf_ein(felder, {"pv-module"})

    assert ergebnis[WEST_KWH]["bedarf"] == "inaktiv"
    text = ergebnis[WEST_KWH]["text"]
    assert "Monatswerte" in text and "Tages- und Stundenwerte" in text
    # Der alte, hier falsche Satz darf nicht mehr erscheinen.
    assert "bereits an anderer Stelle" not in text


def test_basis_zeile_behaelt_den_allgemeinen_satz():
    """Umgekehrte Richtung: die Komponente trägt die Gruppe, das Aggregat ist
    leer — dort ist „bereits an anderer Stelle zugeordnet" die Wahrheit."""
    felder = [
        _bedarf_feld(AGG, "pv_gesamt_kwh", "basis", False, "pv_energie"),
        _bedarf_feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", True, "pv_energie"),
    ]

    ergebnis = stufe_bedarf_ein(felder, {"pv-module"})

    assert ergebnis[AGG]["bedarf"] == "inaktiv"
    assert ergebnis[AGG]["text"] == "Die PV-Erzeugung ist bereits an anderer Stelle zugeordnet."
