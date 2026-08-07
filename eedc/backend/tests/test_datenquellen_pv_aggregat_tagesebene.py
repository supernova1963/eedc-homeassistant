"""Die Zuordnungs-Seite sagt über den PV-Anlagenzähler die Wahrheit (F-7 + Stufe 1).

Forum kaba-kakao (T89667 #109, 2026-08-07): PV-Gesamtzähler bei „Anlage (Basis)"
zugeordnet, die beiden Strings haben **nur** Leistungssensoren. Die Fläche
meldete an den String-Zeilen „Die PV-Erzeugung ist bereits an anderer Stelle
zugeordnet" — also *hier ist nichts zu tun* —, während der Daten-Checker
dieselbe Stelle als Lücke führte.

⚠ **Diese Datei hat am 2026-08-07 mit Stufe 1 ihre Aussage gewechselt.** F-7
hielt fest, dass der Anlagen-Zählerstand die Tagesebene **gar nicht** erreicht;
seither erreicht er sie (`snapshot/keys.py::BASIS_ZAEHLER_FELDER`). Die
Prüfungen bleiben, ihre Richtung dreht sich:

1. **Warnen nur, wo etwas kaputt ist** ([[feedback_user_fehlermeldungen]]).
   Trägt kein Erzeuger einen eigenen Zähler, ist die Anlage vollständig
   versorgt — die Anlagensumme steht in Monat, Tag und Stunde. Kein
   Warndreieck. Gewarnt wird in der **Teilbelegung**: dort schaltet die
   Alles-oder-nichts-Regel (`komponenten_beitraege.basis_beitraege`) das
   Aggregat für Tag und Stunde ab, und die Tagessumme wird still zu niedrig.
2. **Die Herkunft der Gruppen-Deckung zählt.** Deckt nur das Aggregat die
   Gruppe `pv_energie`, sagt der Text, was ein eigener Zähler *zusätzlich*
   brächte — und was er kostet. Deckt umgekehrt eine Komponente sie, bleibt
   „bereits an anderer Stelle zugeordnet" an der Basis-Zeile richtig.
"""

from __future__ import annotations

from backend.services.datenquellen_validierung import (
    finde_aggregat_teilweise_verdraengt,
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
    """Aggregat belegt, KEIN String misst selbst — die Lage aus T89667 #109."""
    return [
        _feld(AGG, "pv_gesamt_kwh", "basis", True),
        _feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", False),
        _feld(WEST_W, "leistung_w", "pv-module", mit_leistung),
        _feld(OST_KWH, "pv_erzeugung_kwh", "pv-module", False),
        _feld(OST_W, "leistung_w", "pv-module", mit_leistung),
    ]


def _halber_umbau() -> list[dict]:
    """Aggregat belegt UND ein String misst selbst — die gefährliche Lage."""
    felder = _stephans_lage()
    for f in felder:
        if f["id"] == WEST_KWH:
            f["belegt"] = True
    return felder


def test_schweigt_wenn_das_aggregat_die_ganze_anlage_traegt():
    """Kein Erzeuger misst selbst ⇒ die Anlagensumme deckt Tag und Stunde
    vollständig ⇒ nichts, worüber zu warnen wäre.

    Das ist die Umkehrung der F-7-Fassung, die hier ein Warndreieck erzeugte:
    solange `basis:pv_gesamt` kein Snapshot-Zähler war, hatte Stephan an
    dieser Stelle wirklich keine Tageswerte."""
    assert finde_aggregat_teilweise_verdraengt(_stephans_lage()) == {}
    assert finde_aggregat_teilweise_verdraengt(_stephans_lage(mit_leistung=False)) == {}


def test_warnt_wenn_ein_einzelner_zaehler_das_aggregat_verdraengt():
    """Ein Erzeuger misst, der andere nicht ⇒ das Aggregat ist für Tag und
    Stunde aus, die Tagessumme trägt nur noch den gemessenen Erzeuger."""
    probleme = finde_aggregat_teilweise_verdraengt(_halber_umbau())

    assert set(probleme) == {AGG}
    p = probleme[AGG]
    assert p["schwere"] == "warning"
    assert p["art"] == "teilweise_verdraengt"
    # Der Text muss die Folge benennen, nicht nur die Lage.
    assert "zu niedrig" in p["text"]
    assert "Integral-Sensor" in p["text"]
    # Und er darf die Monatswerte nicht mit verdächtigen: die sind vollständig.
    assert "Monatswerte sind in beiden Fällen" in p["text"]
    # Benannt werden die Erzeuger, denen der Zähler FEHLT — sie sind der Weg raus.
    assert set(p["wirksame_felder"]) == {OST_KWH}


def test_schweigt_wenn_jede_komponente_ihren_zaehler_hat():
    """Keine Lücke ⇒ Zuständigkeit liegt bei `finde_redundante_aggregate`,
    das dann „wirkungslos" meldet. Nie beide gleichzeitig."""
    felder = [
        _feld(AGG, "pv_gesamt_kwh", "basis", True),
        _feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", True),
        _feld(WEST_W, "leistung_w", "pv-module", True),
    ]

    assert finde_aggregat_teilweise_verdraengt(felder) == {}
    assert AGG in finde_redundante_aggregate(felder)  # die andere Meldung greift


def test_schweigt_ohne_belegtes_aggregat():
    """Ohne Aggregat gibt es nichts zu verdrängen — auch nicht bei Teilbelegung."""
    felder = [
        _feld(AGG, "pv_gesamt_kwh", "basis", False),
        _feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", True),
        _feld(OST_KWH, "pv_erzeugung_kwh", "pv-module", False),
    ]

    assert finde_aggregat_teilweise_verdraengt(felder) == {}


# ─── Gegenseite: der Text an der Komponenten-Zeile ──────────────────────────

def _bedarf_feld(fid, feld, typ, belegt, gruppe):
    return {"id": fid, "feld": feld, "typ": typ, "belegt": belegt,
            "bedarf": "pflicht", "bedarf_gruppe": gruppe, "bedingung_anlage": None}


def test_komponenten_zeile_nennt_gewinn_und_preis():
    """Nur das Aggregat trägt die Gruppe ⇒ der Text sagt BEIDES: dass die
    Anlagensumme auch Tag und Stunde deckt, und dass ein einzelner eigener
    Zähler sie dort abschaltet."""
    felder = [
        _bedarf_feld(AGG, "pv_gesamt_kwh", "basis", True, "pv_energie"),
        _bedarf_feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", False, "pv_energie"),
    ]

    ergebnis = stufe_bedarf_ein(felder, {"pv-module"})

    assert ergebnis[WEST_KWH]["bedarf"] == "inaktiv"
    text = ergebnis[WEST_KWH]["text"]
    # Gewinn: die Aufschlüsselung je Erzeuger.
    assert "je Erzeuger" in text
    # Preis: alles-oder-nichts.
    assert "sobald einer gemessen wird" in text
    # Der alte, hier falsche Satz darf nicht mehr erscheinen.
    assert "bereits an anderer Stelle" not in text
    # Und ebensowenig die F-7-Fassung, die die Tagesebene ganz absprach.
    assert "entstehen nur aus einem eigenen Zähler" not in text


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
