"""N-714 — Portal-Parser: eine 0 in der Exportdatei ist ein Messwert, eine leere Zelle bleibt leer.

Die Datei-Leser für SMA Sunny Portal (`sma_sunny_portal.py`) und Fronius Solar.web (`fronius_solarweb.py`) gaben eine
Monatssumme 0 als «kein Wert» aus (`round(…) or None` bzw. `… if data.get(feld) else None`); evcc tat es für den
PV-Anteil (`… or None`). Gemessen am HEAD `07009197`: SMA- und Fronius-Monat mit PV nur aus `0`-Zellen und Netzbezug 9 kWh
⇒ `pv_erzeugung_kwh=None` (nach dem Apply Checker-ERROR «PV-Erzeugung fehlt», Analyse §K2b).

Der Zeilenparser unterscheidet leer und 0 schon heute: `_parse_float` gibt für leer, `-`, `n/a`, Unlesbares `None`
zurück, für `0`/`0,0` 0.0, und addiert wird nur eine Zahl — der Feld-Schlüssel der Monatssumme ist die Anwesenheit.
`import_parsers.base.monatswert` liest sie (eine Regel, ein Ort). Das Monats-Tor bleibt: ein Monat, dessen Zellen
alle 0 sind, erscheint weiter nicht (`monat_hat_wert_ueber_null`).

Schwesterdateien: test_n707_import_pv_null_ist_messwert.py (Apply: 0,0 wird geschrieben),
test_n711_ziel_geraet_pv_null.py, test_n718_portal_speicher_null.py, test_dashboards_evcc_pool_fallback.py
(evcc-Smoketest mit echter Datei).
"""

from __future__ import annotations

from backend.services.import_parsers.base import monat_hat_wert_ueber_null, monatswert
from backend.services.import_parsers.evcc import EVCCParser
from backend.services.import_parsers.fronius_solarweb import FroniusSolarwebParser
from backend.services.import_parsers.sma_echarger import SMAEChargerParser
from backend.services.import_parsers.sma_sunny_portal import SMASunnyPortalParser


def _monat(ergebnis, jahr, monat):
    treffer = [m for m in ergebnis if (m.jahr, m.monat) == (jahr, monat)]
    assert len(treffer) <= 1
    return treffer[0] if treffer else None


# ── Helfer ────────────────────────────────────────────────────────────────────


def test_helfer_anwesenheit_ist_der_schluessel():
    assert monatswert({"pv": 0.0}, "pv") == 0.0
    assert monatswert({"pv": 0.004}, "pv") == 0.0
    assert monatswert({"netz": 3.0}, "pv") is None
    assert monatswert({}, "pv") is None
    assert monatswert({"a": 1.0, "c": 0.0}, "a", "b", "c") == 1.0
    assert monatswert({"b": 0.0}, "a", "b", "c") == 0.0
    assert monatswert({"x": 1.0}, "a", "b") is None
    assert monat_hat_wert_ueber_null({"pv": 0.0, "netz": 0.1})
    assert not monat_hat_wert_ueber_null({"pv": 0.0, "netz": 0.0})
    assert not monat_hat_wert_ueber_null({})


# ── SMA Sunny Portal ──────────────────────────────────────────────────────────

SMA_KOPF = "Zeitraum;Direktverbrauch [kWh];Netzbezug [kWh];Netzeinspeisung [kWh];Gesamterzeugung [kWh]\n"


def _sma(zeilen: str):
    return SMASunnyPortalParser().parse(SMA_KOPF + zeilen)


def test_sma_a_nur_null_zellen_ist_null():
    m = _monat(_sma("01.12.2025;0;5,0;0;0\n02.12.2025;0,0;4,0;0;0,0\n"), 2025, 12)
    assert m.pv_erzeugung_kwh == 0.0
    assert m.einspeisung_kwh == 0.0
    assert m.eigenverbrauch_kwh == 0.0
    assert m.netzbezug_kwh == 9.0


def test_sma_b_leere_zellen_bleiben_leer():
    m = _monat(_sma("01.11.2025;-;3,0;-;-\n02.11.2025;;2,0;n/a;\n"), 2025, 11)
    assert m.pv_erzeugung_kwh is None
    assert m.einspeisung_kwh is None
    assert m.eigenverbrauch_kwh is None
    assert m.netzbezug_kwh == 5.0


def test_sma_c_gemischt_null_und_leer_ist_null():
    m = _monat(_sma("01.10.2025;1,0;3,0;0;0\n02.10.2025;2,0;2,0;;-\n"), 2025, 10)
    assert m.pv_erzeugung_kwh == 0.0
    assert m.einspeisung_kwh == 0.0
    # Wert und leer: die Summe der Zahlen
    m = _monat(_sma("01.10.2025;1,0;3,0;0;4,5\n02.10.2025;2,0;2,0;;-\n"), 2025, 10)
    assert m.pv_erzeugung_kwh == 4.5


def test_sma_d_spalte_fehlt_ganz():
    csv = "Zeitraum;Direktverbrauch [kWh];Netzbezug [kWh]\n01.12.2025;0;5,0\n02.12.2025;0;4,0\n"
    m = _monat(SMASunnyPortalParser().parse(csv), 2025, 12)
    assert m.pv_erzeugung_kwh is None
    assert m.einspeisung_kwh is None
    assert m.batterie_ladung_kwh is None
    assert m.netzbezug_kwh == 9.0


def test_sma_batterie_null_ist_null():
    csv = ("Zeitraum;Batteriesystem-Ladung [kWh];Batteriesystem-Entladung [kWh];Netzbezug [kWh];Gesamterzeugung [kWh]\n"
           "01.01.2026;0;0;12,0;3,0\n")
    m = _monat(SMASunnyPortalParser().parse(csv), 2026, 1)
    assert (m.batterie_ladung_kwh, m.batterie_entladung_kwh) == (0.0, 0.0)


def test_sma_monats_tor_alles_null_erscheint_nicht():
    """Unverändert seit vor N-714: ein Monat nur aus 0-Zellen steht in keiner Vorschau."""
    ergebnis = _sma("01.08.2025;0;0;0;0\n01.09.2025;-;-;-;-\n01.12.2025;0;5,0;0;0\n")
    assert _monat(ergebnis, 2025, 8) is None
    assert _monat(ergebnis, 2025, 9) is None
    assert _monat(ergebnis, 2025, 12) is not None


def test_sma_e_ennexos_jahresansicht_unveraendert():
    """Werte aus dem Hilfebild `sma-ennexos-energiebilanz.png` — Monate ohne Daten stehen dort als «-»."""
    csv = ("sep=;\nId der Anlage;1\nName der Anlage;Test\n\n"
           "Zeitraum;Direktverbrauch [kWh];Batteriesystem-Entladung [kWh];Netzbezug [kWh];Batteriesystem-Ladung [kWh];"
           "Netzeinspeisung [kWh];Gesamtverbrauch [kWh];Gesamterzeugung [kWh]\n"
           "Jan. 2026;130,22;99,72;431,31;129,93;79,93;651,28;330,11\n"
           "Feb. 2026;167,24;150,24;277,33;193,92;186,68;592,39;545,41\n"
           "März 2026;23,35;20,81;12,29;29,34;74,09;56,28;126,61\n"
           "Apr. 2026;-;-;-;-;-;-;-\nMai 2026;-;-;-;-;-;-;-\n")
    ergebnis = SMASunnyPortalParser().parse(csv)
    assert [(m.jahr, m.monat) for m in ergebnis] == [(2026, 1), (2026, 2), (2026, 3)]
    m = ergebnis[2]
    assert (m.pv_erzeugung_kwh, m.einspeisung_kwh, m.netzbezug_kwh) == (126.61, 74.09, 12.29)
    assert (m.batterie_ladung_kwh, m.batterie_entladung_kwh, m.eigenverbrauch_kwh) == (29.34, 20.81, 23.35)


# ── Fronius Solar.web ─────────────────────────────────────────────────────────

FRONIUS_KOPF = ("Date and time;PV production [Wh];Energy to grid [Wh];Energy from grid [Wh];Consumed directly [Wh]\n"
                "[dd.MM.yyyy];[Wh];[Wh];[Wh];[Wh]\n")


def _fronius(zeilen: str, kopf: str = FRONIUS_KOPF):
    return FroniusSolarwebParser().parse(kopf + zeilen)


def test_fronius_a_nur_null_zellen_ist_null():
    m = _monat(_fronius("01.12.2025;0;0;5000;0\n02.12.2025;0;0;4000;0\n"), 2025, 12)
    assert m.pv_erzeugung_kwh == 0.0
    assert m.einspeisung_kwh == 0.0
    assert m.eigenverbrauch_kwh == 0.0
    assert m.netzbezug_kwh == 9.0


def test_fronius_b_leere_zellen_bleiben_leer():
    m = _monat(_fronius("01.11.2025;;;3000;\n02.11.2025;-;-;2000;-\n"), 2025, 11)
    assert m.pv_erzeugung_kwh is None
    assert m.einspeisung_kwh is None
    assert m.eigenverbrauch_kwh is None
    assert m.netzbezug_kwh == 5.0


def test_fronius_c_gemischt_null_und_leer_ist_null():
    m = _monat(_fronius("01.10.2025;0;0;3000;\n02.10.2025;;;2000;\n"), 2025, 10)
    assert m.pv_erzeugung_kwh == 0.0
    assert m.einspeisung_kwh == 0.0
    # ohne Eigenverbrauch-Zelle abgeleitet: 0 − 0
    assert m.eigenverbrauch_kwh == 0.0


def test_fronius_d_spalte_fehlt_ganz():
    kopf = "Datum und Uhrzeit;Einspeisung [Wh];Netzbezug [Wh]\n[dd.MM.yyyy];[Wh];[Wh]\n"
    m = _monat(_fronius("01.12.2025;0;5000\n", kopf), 2025, 12)
    assert m.pv_erzeugung_kwh is None
    assert m.eigenverbrauch_kwh is None  # keine PV-Zelle ⇒ keine Ableitung
    assert m.wallbox_ladung_kwh is None
    assert m.netzbezug_kwh == 5.0


def test_fronius_eigenverbrauch_null_bleibt_null_und_nulleinspeisung_leitet_ab():
    # Zelle «Consumed directly» 0 ist ein Wert, keine Ableitung darüber
    m = _monat(_fronius("01.06.2025;10000;4000;1000;0\n"), 2025, 6)
    assert m.eigenverbrauch_kwh == 0.0
    # ohne Eigenverbrauch-Zelle, Einspeisung 0 (Nulleinspeisung): Erzeugung − 0
    m = _monat(_fronius("01.06.2025;10000;0;1000;\n"), 2025, 6)
    assert m.einspeisung_kwh == 0.0
    assert m.eigenverbrauch_kwh == 10.0


def test_fronius_wattpilot_null_und_fehlend():
    kopf = ("Datum und Uhrzeit;Energie | GEN24 [Wh];Einspeisung [Wh];Netzbezug [Wh];"
            "Energie vom Netz an Wattpilot [Wh];Energie von Batterie an Wattpilot [Wh];Energie von PV an Wattpilot [Wh]\n")
    m = _monat(_fronius("01.07.2025;15000;9000;1000;0;0;0\n", kopf), 2025, 7)
    assert (m.wallbox_ladung_kwh, m.wallbox_ladung_pv_kwh) == (0.0, 0.0)
    m = _monat(_fronius("01.07.2025;15000;9000;1000;;;\n", kopf), 2025, 7)
    assert (m.wallbox_ladung_kwh, m.wallbox_ladung_pv_kwh) == (None, None)
    m = _monat(_fronius("01.07.2025;15000;9000;1000;2000;;0\n", kopf), 2025, 7)
    assert (m.wallbox_ladung_kwh, m.wallbox_ladung_pv_kwh) == (2.0, 0.0)


def test_fronius_monats_tor_alles_null_erscheint_nicht():
    ergebnis = _fronius("01.08.2025;0;0;0;0\n01.12.2025;0;0;5000;0\n")
    assert _monat(ergebnis, 2025, 8) is None
    assert _monat(ergebnis, 2025, 12) is not None


# ── evcc ──────────────────────────────────────────────────────────────────────

EVCC_KOPF = "Startzeit;Endzeit;Ladepunkt;Fahrzeug;Energie (kWh);Sonne (%)\n"


def test_evcc_a_sonne_null_ist_null():
    csv = EVCC_KOPF + "2026-01-10 18:00:00;2026-01-11 06:00:00;Carport;Auto;20,0;0\n"
    m = _monat(EVCCParser().parse(csv), 2026, 1)
    assert m.wallbox_ladung_kwh == 20.0
    assert m.wallbox_ladung_pv_kwh == 0.0


def test_evcc_b_sonne_leer_bleibt_leer():
    csv = EVCC_KOPF + "2026-01-10 18:00:00;2026-01-11 06:00:00;Carport;Auto;20,0;\n"
    assert _monat(EVCCParser().parse(csv), 2026, 1).wallbox_ladung_pv_kwh is None


def test_evcc_c_gemischt():
    csv = (EVCC_KOPF + "2026-01-10 18:00:00;2026-01-11 06:00:00;Carport;Auto;20,0;0\n"
           "2026-01-12 18:00:00;2026-01-13 06:00:00;Carport;Auto;10,0;\n")
    assert _monat(EVCCParser().parse(csv), 2026, 1).wallbox_ladung_pv_kwh == 0.0


def test_evcc_d_spalte_fehlt_ganz():
    csv = "Startzeit;Endzeit;Ladepunkt;Fahrzeug;Energie (kWh)\n2026-01-10 18:00:00;2026-01-11 06:00:00;Carport;Auto;20,0\n"
    assert _monat(EVCCParser().parse(csv), 2026, 1).wallbox_ladung_pv_kwh is None


# ── SMA eCharger (unverändert: ein Monat ohne Ladung erscheint nicht) ─────────


def test_echarger_monat_ohne_ladung_erscheint_nicht():
    csv = ("Id der Anlage;1\nName der Anlage;T\n\nZeitraum;Zählerstand Ladestation [kWh];Zählerstand Ladestation Zählerstand [kWh]\n"
           "01.09.2025;0;100,0\n02.09.2025;;100,0\n01.10.2025;5,5;105,5\n")
    ergebnis = SMAEChargerParser().parse(csv)
    assert [(m.jahr, m.monat) for m in ergebnis] == [(2025, 10)]
    assert ergebnis[0].wallbox_ladung_kwh == 5.5
