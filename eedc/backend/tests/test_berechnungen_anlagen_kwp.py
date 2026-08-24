"""Der Nenner-SoT `core/berechnungen/anlagen_kwp.py` (F-58).

Schwesterdatei: `test_bkw_parent_pv_module_n266.py` — sie prüft, *welche*
Erzeuger ihre kWp tragen (BKW-Abtretung an Modul-Kinder, `erzeuger_traeger`),
diese hier die Summe darüber samt Zeitfilter und Fallback.

**Was der Helper entscheidet.** Bis zum 2026-08-24 stand an fünfzehn Stellen
die Frage „durch welche kWp teile ich?" einzeln beantwortet: elf nahmen den
gepflegten `Anlage.leistung_kwp`, vier die Σ der Investitionen. Das ist die
Klasse hinter NoahPaulicks Meldung (simon42 T89667 #188) — sein gepflegter
Wert lag nach einem Anlagen-Split neben der Modulsumme, und der
Doppelerfassungs-Check teilte durch die falsche Zahl.

Zwei Eigenschaften trägt nur die Summe, und beide werden hier geprüft: sie
kennt den **Zeitpunkt** (Anschaffung/Stilllegung) und die **BKW-Abtretung**.
"""

from __future__ import annotations

from datetime import date

from backend.core.berechnungen.anlagen_kwp import anlagen_kwp, summe_erzeuger_kwp
from backend.tests.factories import mach_investition

HEUTE = date(2026, 8, 24)


def _modul(kwp: float, **felder):
    return mach_investition("pv-module", leistung_kwp=kwp, **felder)


def _bkw(kwp: float, **felder):
    return mach_investition("balkonkraftwerk", leistung_kwp=kwp, **felder)


def test_summe_ohne_bkw_zaehlt_nur_module():
    invs = [_modul(10.0), _modul(5.0), _bkw(0.8)]
    assert summe_erzeuger_kwp(invs, HEUTE, mit_bkw=False) == 15.0


def test_summe_mit_bkw_zaehlt_beide():
    invs = [_modul(10.0), _modul(5.0), _bkw(0.8)]
    assert summe_erzeuger_kwp(invs, HEUTE, mit_bkw=True) == 15.8


def test_andere_typen_zaehlen_nie_mit():
    """`Investition.leistung_kwp` ist ein Mehrzweckfeld — beim Speicher steht
    dort kWh, beim Wechselrichter kW (AC). Beides gehört nicht in eine kWp-Σ."""
    invs = [
        _modul(10.0),
        mach_investition("speicher", leistung_kwp=12.8),
        mach_investition("wechselrichter", leistung_kwp=8.0),
    ]
    assert summe_erzeuger_kwp(invs, HEUTE, mit_bkw=True) == 10.0


def test_vor_der_anschaffung_zaehlt_der_erzeuger_nicht():
    invs = [_modul(10.0), _modul(5.0, anschaffungsdatum=date(2026, 9, 1))]
    assert summe_erzeuger_kwp(invs, HEUTE, mit_bkw=False) == 10.0
    assert summe_erzeuger_kwp(invs, date(2026, 9, 1), mit_bkw=False) == 15.0


def test_nach_der_stilllegung_zaehlt_der_erzeuger_nicht():
    invs = [_modul(10.0), _modul(5.0, stilllegungsdatum=date(2026, 6, 30))]
    assert summe_erzeuger_kwp(invs, HEUTE, mit_bkw=False) == 10.0
    assert summe_erzeuger_kwp(invs, date(2026, 6, 30), mit_bkw=False) == 15.0


def test_manuell_deaktivierter_erzeuger_zaehlt_nicht():
    invs = [_modul(10.0), _modul(5.0, aktiv=False)]
    assert summe_erzeuger_kwp(invs, HEUTE, mit_bkw=False) == 10.0


def test_bkw_mit_modul_kindern_zaehlt_nicht_doppelt():
    """N-266: Ein BKW, dessen Modul-Kinder die kWp tragen, hat seine eigene
    abgetreten. Ohne `erzeuger_traeger` stünde die Anlagenleistung doppelt."""
    bkw = _bkw(0.8, id=1)
    kind = _modul(0.8, id=2, parent_investition_id=1)
    assert summe_erzeuger_kwp([bkw, kind], HEUTE, mit_bkw=True) == 0.8


def test_fallback_greift_nur_ohne_gepflegte_erzeuger():
    assert anlagen_kwp([], HEUTE, mit_bkw=True, referenzwert=31.24) == 31.24
    # Sobald EIN Erzeuger gepflegt ist, gewinnt die Summe — auch wenn der
    # Referenzwert größer ist. Das ist der gemeldete Fall in Gegenrichtung:
    # die Summe kennt den Zeitpunkt, der Skalar nicht.
    assert anlagen_kwp([_modul(31.24)], HEUTE, mit_bkw=True, referenzwert=15.62) == 31.24


def test_ohne_referenzwert_und_ohne_erzeuger_ist_es_null():
    """0.0 statt einer erfundenen Zahl — der Aufrufer prüft `<= 0` selbst."""
    assert anlagen_kwp([], HEUTE, mit_bkw=True) == 0.0
    assert anlagen_kwp([], HEUTE, mit_bkw=True, referenzwert=None) == 0.0


def test_alle_erzeuger_stillgelegt_faellt_auf_den_referenzwert():
    """Grenzfall: gepflegte Erzeuger, aber am Stichtag keiner aktiv.

    Die Summe ist dann 0, und der Referenzwert übernimmt. Bewusst so: eine
    Division durch 0 wäre die schlechtere Antwort, und die Stelle, an der ein
    Zeitraum ohne Erzeuger etwas bedeutet, ist der Daten-Checker.
    """
    invs = [_modul(10.0, stilllegungsdatum=date(2020, 1, 1))]
    assert anlagen_kwp(invs, HEUTE, mit_bkw=True, referenzwert=31.24) == 31.24
