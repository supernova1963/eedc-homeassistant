"""Quellenwahl und Lückentag der Kanal-Leser (HA-Bauform E4a-2, Bestätigung B-4, Auftrag Punkt 4) — reine Funktion
``bilanz_leser.waehle_und_komponiere`` mit gebauten Lese-Ergebnissen (``lesen.Zeitraum``).

Schwesterdateien: test_kanal_bilanz_gleichheit.py (dieselben Leser an den Matrix-Datenständen), test_bilanz_zeitraum.py
(die Komposition im Layer), test_kanal_quellenwahl.py."""

from __future__ import annotations

from backend.services.kanal.bilanz_leser import waehle_und_komponiere
from backend.services.kanal.lesen import GRUND_ENDET_VOR_BIS, GRUND_FEINER_ALS_SPANNE, Zeitraum
from backend.services.kanal.quellenwahl import QUELLE_BESTAND, QUELLE_KANAL
from backend.services.snapshot.tages_tabelle import TabellenEintrag


def _z(key, delta=None, *, grund=None, teil=None, laufend=False):
    voll = grund is None
    return Zeitraum(key=key, art="sum", einheit="kWh", von=0, bis=86400, delta=delta if voll else None,
                    teil_delta=None if voll else teil, gedeckt_von=0, gedeckt_bis=86400, rand_spanne=3600,
                    voll=voll, grund=grund, laufend=laufend)


A = TabellenEintrag("inv:3:erzeugung_kwh", "erzeugung_sonstiges", "g3", "inv:3:erzeugung_kwh", "sonstige_3", 1)
B = TabellenEintrag("inv:3:verbrauch_sonstig_kwh", "erzeugung_sonstiges", "g3", "inv:3:verbrauch_sonstig_kwh",
                    "sonstige_3", 1)
E = TabellenEintrag("basis:einspeisung", "einspeisung", None, "basis:einspeisung", "einspeisung", 1)


def test_r4_die_gruppe_ist_gedeckt_wenn_ein_kanal_deckt_und_nimmt_den_ersten_mit_deckung():
    k = waehle_und_komponiere([E, A, B], {E.schluessel: _z(E.schluessel, 5.0),
                                         A.schluessel: _z(A.schluessel, grund=GRUND_FEINER_ALS_SPANNE, teil=1.0,
                                                          laufend=True),
                                         B.schluessel: _z(B.schluessel, 6.24)}, [], lueckentag=False)
    assert k.wahl.quelle == QUELLE_KANAL
    assert k.komposition.komponenten == {"einspeisung": 5.0, "sonstige_3": 6.24}


def test_ohne_deckung_eines_zaehlers_ausserhalb_einer_gruppe_nimmt_der_zeitraum_den_bestand():
    k = waehle_und_komponiere([E, A], {E.schluessel: _z(E.schluessel, grund=GRUND_ENDET_VOR_BIS, teil=2.0),
                                       A.schluessel: _z(A.schluessel, 6.0)}, [], lueckentag=True)
    assert (k.wahl.quelle, k.wahl.gruende, k.komposition) == (QUELLE_BESTAND, {E.schluessel: GRUND_ENDET_VOR_BIS}, None)


def test_lueckentag_nur_am_beendeten_tag_und_nur_bei_der_spanne():
    erg = {E.schluessel: _z(E.schluessel, grund=GRUND_FEINER_ALS_SPANNE, teil=12.0)}
    assert waehle_und_komponiere([E], erg, [], lueckentag=True).komposition.komponenten == {"einspeisung": 12.0}
    assert waehle_und_komponiere([E], erg, [], lueckentag=False).wahl.quelle == QUELLE_BESTAND   # Monat
    laufend = {E.schluessel: _z(E.schluessel, grund=GRUND_FEINER_ALS_SPANNE, teil=12.0, laufend=True)}
    assert waehle_und_komponiere([E], laufend, [], lueckentag=True).wahl.quelle == QUELLE_BESTAND
