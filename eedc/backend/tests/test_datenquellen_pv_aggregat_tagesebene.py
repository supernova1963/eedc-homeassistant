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
2. **Die Herkunft der Gruppen-Deckung zählt.** Deckt nur das Aggregat die
   Gruppe `pv_energie`, sagt der Text, was ein eigener Zähler *zusätzlich*
   brächte. Deckt umgekehrt eine Komponente sie, bleibt „bereits an anderer
   Stelle zugeordnet" an der Basis-Zeile richtig.

⛔ **Und mit #406 dreht sie sich ein ZWEITES Mal.** Bis dahin stand hier:
„Gewarnt wird in der **Teilbelegung**: dort schaltet die Alles-oder-nichts-Regel
das Aggregat für Tag und Stunde ab, und die Tagessumme wird still zu niedrig."
Diese Warnung (`finde_aggregat_teilweise_verdraengt`) ist **ersatzlos entfernt**,
und mit ihr die vier Proben, die sie prüften — die Bilanz ist damit 6 → 3.

**Warum ersatzlos:** Der Zustand tritt nicht mehr ein. Die Präzedenz je Tag
(`core/berechnungen/pv_tages_praezedenz.py`) lässt das Aggregat die Bilanz
tragen, sobald die Einzelzähler sie nicht vollständig tragen. Und die Warnung
hat den Fall, für den sie gebaut war, ohnehin verfehlt: Mathek (#406) hat ALLEN
Strings einen Zähler zugeordnet — keine Teilbelegung, kein Warndreieck, und der
Tag verlor trotzdem 21 Stunden PV.

⭐ Was an ihre Stelle tritt, ist eine Probe in der **Gegenrichtung**
(`test_teilbelegung_erzeugt_kein_warndreieck_mehr`): Die Falschmeldung darf
nicht zurückkehren.
"""

from __future__ import annotations

from backend.services.datenquellen_validierung import (
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


def test_teilbelegung_erzeugt_kein_warndreieck_mehr():
    """Die Gegenrichtung zur entfernten Warnung (#406).

    Aggregat belegt UND ein String misst selbst — die Lage, für die es bis #406
    ein Warndreieck gab. Sie ist kein Defekt mehr: die Anlagensumme trägt die
    Bilanz. Bliebe hier ein Problem stehen, wäre es eine Falschmeldung.

    ⚠ Geprüft wird `finde_redundante_aggregate` — die einzige verbliebene
    Aggregat-Prüfung. Sie meldet die ANDERE Lage (jede Komponente misst ⇒ das
    Aggregat ist wirkungslos) und muss hier schweigen.
    """
    assert finde_redundante_aggregate(_halber_umbau()) == {}


def test_redundantes_aggregat_wird_weiter_gemeldet():
    """Gegenprobe: messen ALLE Erzeuger selbst, ist das Aggregat wirkungslos —
    diese Meldung bleibt, sie hing nie an der Verdrängung."""
    felder = _stephans_lage()
    for f in felder:
        if f["id"] in (WEST_KWH, OST_KWH):
            f["belegt"] = True
    assert set(finde_redundante_aggregate(felder)) == {AGG}


def _bedarf_feld(fid, feld, typ, belegt, gruppe):
    return {"id": fid, "feld": feld, "typ": typ, "belegt": belegt,
            "bedarf": "pflicht", "bedarf_gruppe": gruppe, "bedingung_anlage": None}


def test_komponenten_zeile_nennt_den_gewinn_ohne_drohung():
    """Nur das Aggregat trägt die Gruppe ⇒ der Text sagt, was ein eigener
    Zähler bringt — und **nicht** mehr, dass dann alle einen brauchen.

    ⛔ Hieß bis #406 `test_komponenten_zeile_nennt_gewinn_und_preis`. Der
    „Preis" war die Alles-oder-nichts-Regel, also eine Anleitung in genau die
    Falle, in die Mathek gelaufen ist. Er existiert nicht mehr."""
    felder = [
        _bedarf_feld(AGG, "pv_gesamt_kwh", "basis", True, "pv_energie"),
        _bedarf_feld(WEST_KWH, "pv_erzeugung_kwh", "pv-module", False, "pv_energie"),
    ]

    ergebnis = stufe_bedarf_ein(felder, {"pv-module"})

    assert ergebnis[WEST_KWH]["bedarf"] == "inaktiv"
    text = ergebnis[WEST_KWH]["text"]
    # Gewinn: die Aufschlüsselung je Erzeuger.
    assert "je Erzeuger" in text
    # Und der Satz sagt, was ohne eigenen Zähler geschieht — abgeleitet statt
    # gemessen, aber die Anlagensumme stimmt.
    assert "nach kWp" in text
    assert "Anlagensumme selbst stimmt" in text
    # ⛔ Die Drohung der alten Regel darf nicht zurückkehren.
    assert "sobald einer gemessen wird" not in text
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
    # ⚑ Bis 2026-08-30 stand hier ein Zeichenvergleich auf den ganzen Satz. Der
    # Text hat seither einen Zusatz („— hier ist nichts einzutragen"), weil ein
    # reiner Zustandssatz neben einem Schalter als Aufforderung gelesen wurde
    # (rapahl, PN 91806). Die Zusicherung ist deshalb auf ihre AUSSAGE
    # umgestellt, nicht gestrichen: die Basis-Zeile bekommt den ALLGEMEINEN
    # Satz — und ausdrücklich nicht den Komponenten-Text aus dem Nachbartest.
    text = ergebnis[AGG]["text"]
    assert "bereits an anderer Stelle zugeordnet" in text
    assert "je Erzeuger" not in text
    assert "sobald einer gemessen wird" not in text
