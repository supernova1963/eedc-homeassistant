"""Eine Tagesbilanz ohne erfasste PV behauptet keine Zahl (P4-Regel).

Auslöser: Forum kaba-kakao (2026-08-07, T89667 #109). Seine Anlage hat den
PV-Zähler als **Anlagen-Aggregat** zugeordnet — das versorgte damals den Monat,
nicht die Tagesebene (dort zählte nur ein kumulativer Zähler **je Erzeuger**).
Die Tagessicht zeigte daraufhin:

    PV-Erzeugung   0 kWh        ← nicht gemessen, nicht „nichts erzeugt"
    Einspeisung   25 kWh        ← gemessen
    Eigenverbrauch −25 kWh      ← 0 − 25, physikalisch unmöglich
    Performance Ratio 0 %       ← „auffällig niedrig"
    Peak PV     5,01 kW         ← aus dem Leistungssensor, also da

Regel-SoT: ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` — eine additive Teilsumme
darf 0 bleiben (richtungssicher), eine **Differenz mit fehlendem Summanden**
wird unterdrückt, weil die Richtung des Fehlers unbekannt ist.

⚠ **Der Auslöser selbst ist seit Stufe 1 (2026-08-07) behoben** — der
Anlagen-Zählerstand erreicht die Tagesebene
(``snapshot/keys.py::BASIS_ZAEHLER_FELDER``), Stephan bekommt seine PV. Diese
Regel bleibt trotzdem, und zwar als Netz für alle Lagen, in denen gar kein
kumulativer PV-Zähler existiert: nur Leistungssensoren, ausgefallener Zähler,
Lücke im Snapshot. Ein behobener Auslöser macht eine Invariante nicht
überflüssig.

Die schärfste Probe hier ist ``test_gemessene_null_bleibt_eine_null``: der
Träger ist ``pv_erfasst`` und **nicht** ``pv_sum > 0``. Eine Anlage, die nachts
(oder im Schnee) 0 kWh erzeugt, hat einen gültigen Messwert — würde sie
mitunterdrückt, wäre die Lücken-Regel selbst eine neue Falschaussage.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows


def _row(**kw):
    """Stunden-Row-Stub; nicht gesetzte Felder sind ``None`` (= nicht erfasst)."""
    basis = dict(
        pv_kw=None, verbrauch_kw=None, einspeisung_kw=None,
        netzbezug_kw=None, batterie_kw=None, waermepumpe_kw=None,
    )
    basis.update(kw)
    return SimpleNamespace(**basis)


def test_kein_negativer_eigenverbrauch_ohne_erfasste_pv():
    """Stephans Lage: Einspeisung gemessen, PV nirgends erfasst."""
    rows = [_row(einspeisung_kw=12.5), _row(einspeisung_kw=12.5)]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.pv_erfasst is False
    assert bilanz.einspeisung_kwh == 25.0        # gemessen, bleibt stehen
    assert bilanz.eigenverbrauch_kwh is None     # vorher: -25.0
    assert bilanz.ev_quote_prozent is None


def test_gemessene_null_bleibt_eine_null():
    """0 kWh gemessen ist ein Wert — kein Fall für die Unterdrückung.

    Genau hier hätte ein Träger ``pv_sum > 0`` denselben Fehler in die andere
    Richtung gemacht: eine Nacht ohne Ertrag verlöre ihren Eigenverbrauch.
    """
    rows = [_row(pv_kw=0.0, einspeisung_kw=0.0), _row(pv_kw=0.0)]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.pv_erfasst is True
    assert bilanz.erzeugung_kwh == 0.0
    assert bilanz.eigenverbrauch_kwh == 0.0      # NICHT None
    # Quote bleibt None: der Nenner ist 0, das war schon vorher richtig.
    assert bilanz.ev_quote_prozent is None


def test_eine_einzige_erfasste_stunde_genuegt():
    """Teil-Erfassung ist eine Summe, keine Lücke — sie bleibt richtungssicher.

    Der Tag trägt 3 kWh PV in einer Stunde; die übrigen Stunden sind NULL.
    Das Ergebnis ist eine (zu niedrige) Teilsumme, aber kein unmöglicher Wert.
    """
    rows = [_row(pv_kw=3.0), _row(einspeisung_kw=1.0), _row()]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.pv_erfasst is True
    assert bilanz.erzeugung_kwh == 3.0
    assert bilanz.eigenverbrauch_kwh == 2.0


def test_erfasste_pv_rechnet_unveraendert():
    """Regression: der Normalfall darf sich durch die Regel nicht verschieben."""
    rows = [
        _row(pv_kw=5.0, verbrauch_kw=2.0, einspeisung_kw=3.0, netzbezug_kw=0.0),
        _row(pv_kw=1.0, verbrauch_kw=2.0, einspeisung_kw=0.0, netzbezug_kw=1.0),
    ]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.pv_erfasst is True
    assert bilanz.erzeugung_kwh == 6.0
    assert bilanz.einspeisung_kwh == 3.0
    assert bilanz.eigenverbrauch_kwh == 3.0
    assert bilanz.ev_quote_prozent == 50.0
