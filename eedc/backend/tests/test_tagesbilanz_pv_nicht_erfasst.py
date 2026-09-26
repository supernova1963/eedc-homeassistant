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

import pytest

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


def test_netz_seite_sagt_ebenfalls_nicht_gemessen():
    """Strikers Januar (T89667 #162) — dieselbe Regel, andere Achse.

    Seine Einspeisung kam aus der HA-Historie, PV und Netzbezug hatten dort
    keinen Zähler. Bis 15.08.2026 kannte nur die PV einen Träger; die
    Tageszeile zeigte deshalb „— PV · 106 kWh Einspeisung · **0 kWh
    Netzbezug**", und die 0 war die einzige Zahl der Zeile, hinter der keine
    Messung stand.
    """
    rows = [_row(einspeisung_kw=8.0), _row(einspeisung_kw=8.0)]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.einspeisung_erfasst is True
    assert bilanz.netzbezug_erfasst is False
    assert bilanz.verbrauch_erfasst is False
    # Die Summen selbst bleiben 0.0 — der Layer liefert Zahl **und** Träger,
    # die Anzeige-Entscheidung trifft die Route (wie bei `pv_erfasst`).
    assert bilanz.netzbezug_kwh == 0.0


def test_gemessene_null_bleibt_eine_null_auch_auf_der_netz_seite():
    """Wer einen Tag lang nichts bezieht, hat eine gemessene 0 und behält sie.

    Der Gegen-Fehler zur Regel darüber: ein Träger `netzbezug_sum > 0` würde
    jeden autarken Tag zur Lücke erklären — und autarke Tage sind bei diesen
    Anlagen der Normalfall, nicht die Ausnahme (Striker bezieht im Mai 13,6 kWh
    im ganzen Monat).
    """
    rows = [_row(netzbezug_kw=0.0, verbrauch_kw=0.0), _row(netzbezug_kw=0.0)]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.netzbezug_erfasst is True
    assert bilanz.verbrauch_erfasst is True
    assert bilanz.netzbezug_kwh == 0.0


def test_gemessene_null_bleibt_eine_null():
    """0 kWh gemessen ist ein Wert — kein Fall für die Unterdrückung.

    Genau hier hätte ein Träger ``pv_sum > 0`` denselben Fehler in die andere
    Richtung gemacht: eine Nacht ohne Ertrag verlöre ihren Eigenverbrauch.

    ⚠ **Fixture am 2026-08-22 auf gleiche Abdeckung gezogen (N-92).** Sie trug
    zuvor ``[pv=0 & einspeisung=0, pv=0]`` — also PV über zwei Stunden und
    Einspeisung über eine. Damit hing sie **nebenbei** an der Abdeckungs-Regel
    mit und hätte auf deren Einführung reagiert, obwohl ihr Gegenstand ein ganz
    anderer ist (``pv_erfasst`` gegen ``pv_sum > 0``). Eine Probe soll auf ihr
    eigenes Objekt zeigen; die Teilabdeckung prüft
    ``test_teilabdeckung_unterdrueckt_die_differenz`` unten.
    """
    rows = [_row(pv_kw=0.0, einspeisung_kw=0.0), _row(pv_kw=0.0, einspeisung_kw=0.0)]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.pv_erfasst is True
    assert bilanz.erzeugung_kwh == 0.0
    assert bilanz.eigenverbrauch_kwh == 0.0      # NICHT None
    # Quote bleibt None: der Nenner ist 0, das war schon vorher richtig.
    assert bilanz.ev_quote_prozent is None


def test_eine_einzige_erfasste_stunde_genuegt():
    """Eine additive Teilsumme bleibt richtungssicher — die Differenz nicht.

    ⛔ **Diese Probe behauptete bis 2026-08-22 den Befund N-92 als gewolltes
    Verhalten.** Sie hieß „Teil-Erfassung ist eine Summe, keine Lücke" und
    verlangte ``eigenverbrauch_kwh == 2.0`` aus ``3 − 1``. Beide Werte stammen
    aber aus **verschiedenen Stunden**: die PV aus der ersten, die Einspeisung
    aus der zweiten. Der Satz stimmt für ``erzeugung_kwh`` (eine additive
    Teilsumme, richtungssicher zu niedrig) und ist für ``eigenverbrauch_kwh``
    falsch — das ist eine **Differenz**, und der Modul-Docstring dieser Datei
    sagt zwei Absätze weiter oben selbst, dass eine „Differenz mit fehlendem
    Summanden unterdrückt" wird. Die Probe hat die beiden Formelformen
    verwechselt und den Fund dadurch **grün verteidigt**.

    Was hier geprüft wird, ist deshalb **beides zugleich**: die Teilsumme
    überlebt, die Differenz nicht.
    """
    rows = [_row(pv_kw=3.0), _row(einspeisung_kw=1.0), _row()]

    bilanz = bilanz_aus_stundenrows(rows)

    assert bilanz.pv_erfasst is True
    # Additive Teilsumme: bleibt, „mindestens 3 kWh".
    assert bilanz.erzeugung_kwh == 3.0
    assert bilanz.einspeisung_kwh == 1.0
    # Differenz aus zwei disjunkten Abdeckungen: keine Aussage.
    assert bilanz.eigenverbrauch_kwh is None
    assert bilanz.pv_stunden == 1
    assert bilanz.einspeisung_stunden == 1
    assert bilanz.pv_und_einspeisung_stunden == 0   # genau der Beleg


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


# ───────────────────────────────────────────────────────────────────────────
# N-92 (2026-08-22) und R7 (Zählerlücken wie HA, 26.09.2026)
#
# ⭐ **Umgeschrieben am 26.09.2026, nicht gelockert.** Jede Lage steht jetzt
# ZWEIMAL da — so, wie sie ein Tag **ohne** Regelmarke rechnet (Altbestand,
# ``verworfen=None`` ⇒ N-92 wie bisher: seine Stunden haben die Energie einer
# Lücke verloren, eine Teilabdeckung ist dort ein echter Fehler, E6) und so,
# wie sie ein Tag **mit** Regelmarke rechnet (``verworfen={}`` ⇒ R7: jede
# Stunde trägt, was HA zeigt, die Lückenenergie steht in der Folgestunde; die
# Differenz wird nur noch im Total-Fall oder bei ``verworfen`` unterdrückt —
# wie in HA, G3). Die Werte beider Seiten sind exakt festgehalten.
# ───────────────────────────────────────────────────────────────────────────

ALTBESTAND = None
MARKE = {}


def test_teilabdeckung_altbestand_unterdrueckt_neue_regel_rechnet_wie_ha():
    """PV über alle Stunden, Einspeisung nur über einen Teil (Sensor endet).

    Altbestand: gemessen am 2026-08-22 **vor** N-92: 24 h PV à 2 kW und 18 h
    Einspeisung à 1 kW ergaben ``48 − 18 = 30 kWh``; die Stunden eines solchen
    Tages können die Energie einer Lücke verloren haben ⇒ keine Aussage.

    Neue Regel (P11): Eine Stunde ohne Einspeisungswert ist unter R1 eine
    Stunde, in der HA keine Einspeisung zeigt — die Energie einer Lücke stünde
    in der Folgestunde. EV = 30 wie im HA-Dashboard, kein „—".
    """
    rows = [_row(pv_kw=2.0, einspeisung_kw=1.0) for _ in range(18)]
    rows += [_row(pv_kw=2.0) for _ in range(6)]

    alt = bilanz_aus_stundenrows(rows, verworfen=ALTBESTAND)
    assert (alt.erzeugung_kwh, alt.einspeisung_kwh) == (48.0, 18.0)
    assert alt.eigenverbrauch_kwh is None
    assert alt.ev_quote_prozent is None
    assert (alt.pv_stunden, alt.einspeisung_stunden) == (24, 18)

    neu = bilanz_aus_stundenrows(rows, verworfen=MARKE)
    assert (neu.erzeugung_kwh, neu.einspeisung_kwh) == (48.0, 18.0)
    assert neu.eigenverbrauch_kwh == 30.0
    assert neu.ev_quote_prozent == 62.5


def test_teilabdeckung_mit_verworfen_bleibt_unterdrueckt():
    """R7: ``verworfen`` auf pv oder einspeisung unterdrückt EV und EV-Quote."""
    rows = [_row(pv_kw=2.0, einspeisung_kw=1.0) for _ in range(24)]
    for achse in ("pv", "einspeisung"):
        b = bilanz_aus_stundenrows(rows, verworfen={achse: 31368.0})
        assert b.eigenverbrauch_kwh is None and b.ev_quote_prozent is None
        assert b.erzeugung_kwh == 48.0          # die Menge bleibt


def test_einspeisung_nie_gemessen_ist_in_beiden_regeln_ein_total_fall():
    """Ohne Einspeisungs-Messung ist nicht die ganze Erzeugung Eigenverbrauch.

    ``pv_sum - 0`` behauptete, jede erzeugte Kilowattstunde sei selbst genutzt
    worden. Das ist der **Total-Fall** — er bleibt auch unter R7 unterdrückt.
    """
    rows = [_row(pv_kw=2.0) for _ in range(24)]
    for regel in (ALTBESTAND, MARKE):
        bilanz = bilanz_aus_stundenrows(rows, verworfen=regel)
        assert bilanz.pv_erfasst is True
        assert bilanz.einspeisung_erfasst is False
        assert bilanz.erzeugung_kwh == 48.0
        assert bilanz.eigenverbrauch_kwh is None


def test_autarkie_ohne_netzbezugs_messung_ist_keine_100_prozent():
    """Strikers Januar, eine Kachel weiter (T89667 #162).

    Altbestand: ``Verbrauch − Netzbezug`` mit Verbrauch über 24 h und Netzbezug
    nirgends ⇒ ``netzbezug_sum = 0`` ⇒ **Autarkie 100,0 %** vor N-92.
    Neue Regel: Netzbezug ist ein Total-Fall ⇒ der Gesamtverbrauch nach
    HA-Formel ist nicht bildbar (auch PV fehlt hier) ⇒ Verbrauch „—", Autarkie
    „—". In keiner Regel 100 %.
    """
    rows = [_row(verbrauch_kw=1.0, einspeisung_kw=2.0) for _ in range(24)]

    alt = bilanz_aus_stundenrows(rows, verworfen=ALTBESTAND)
    assert alt.verbrauch_erfasst is True
    assert alt.netzbezug_erfasst is False
    assert alt.gesamtverbrauch_kwh == 24.0
    assert alt.autarkie_prozent is None

    neu = bilanz_aus_stundenrows(rows, verworfen=MARKE)
    assert neu.netzbezug_erfasst is False
    assert neu.verbrauch_erfasst is False
    assert neu.autarkie_prozent is None


def test_autarkie_teilabdeckung_altbestand_unterdrueckt_neue_regel_rechnet():
    """Altbestand: die Autarkie braucht deckungsgleiche Grundlagen.
    Neue Regel: Netzbezug fehlt 4 Stunden (keine Zeile in HA), der Tag rechnet
    nach HA-Formel — Autarkie da."""
    rows = [_row(pv_kw=0.5, verbrauch_kw=1.0, einspeisung_kw=0.0, netzbezug_kw=0.5)
            for _ in range(20)]
    rows += [_row(pv_kw=0.5, verbrauch_kw=1.0, einspeisung_kw=0.0) for _ in range(4)]

    alt = bilanz_aus_stundenrows(rows, verworfen=ALTBESTAND)
    assert alt.netzbezug_erfasst is True          # der alte Träger griffe
    assert alt.autarkie_prozent is None           # N-92 nicht

    neu = bilanz_aus_stundenrows(rows, verworfen=MARKE)
    # GV = 12 PV + 10 Netz − 0 Einsp = 22; Autarkie = (22 − 10) / 22
    assert neu.gesamtverbrauch_kwh == 22.0
    assert neu.autarkie_prozent == pytest.approx(12 / 22 * 100)


def test_autarkie_mit_verworfen_bleibt_unterdrueckt():
    rows = [_row(pv_kw=1.0, einspeisung_kw=0.2, netzbezug_kw=0.3, batterie_kw=0.0)
            for _ in range(24)]
    for achse in ("pv", "netzbezug", "einspeisung", "batterie"):
        b = bilanz_aus_stundenrows(rows, verworfen={achse: 5.0})
        assert b.autarkie_prozent is None, achse
    assert bilanz_aus_stundenrows(rows, verworfen={"wallbox": 1906.5}).autarkie_prozent is not None


def test_volle_abdeckung_rechnet_in_beiden_regeln_gleich():
    """Gegenprobe: der Normalfall darf sich durch keine der Regeln verschieben.

    Enthält bewusst auch eine **gemessene Null** auf beiden Achsen.
    """
    rows = [_row(pv_kw=2.0, verbrauch_kw=1.0, einspeisung_kw=1.0, netzbezug_kw=0.5)
            for _ in range(23)]
    rows += [_row(pv_kw=0.0, verbrauch_kw=1.0, einspeisung_kw=0.0, netzbezug_kw=1.0)]

    for regel in (ALTBESTAND, MARKE):
        bilanz = bilanz_aus_stundenrows(rows, verworfen=regel)
        assert bilanz.eigenverbrauch_kwh == 46.0 - 23.0
        assert bilanz.autarkie_prozent is not None
        assert bilanz.ev_quote_prozent is not None
        assert bilanz.pv_stunden == bilanz.einspeisung_stunden == 24
        assert bilanz.pv_und_einspeisung_stunden == 24


def test_r7_gesamtverbrauch_nach_ha_formel_auch_ohne_stunden_verbrauch():
    """P10: Tagesverbrauch nach HA-Formel mit negativen Stunden; da, obwohl
    jede Stunde R6-``None`` ist (Ein-Achsen-Lücke)."""
    rows = [_row(pv_kw=0.0, netzbezug_kw=4.0, einspeisung_kw=0.0, verbrauch_kw=None)]
    rows += [_row(pv_kw=3.0, netzbezug_kw=0.0, einspeisung_kw=4.0, verbrauch_kw=None,
                  batterie_kw=1.5)]          # Entladung 1,5
    rows += [_row(pv_kw=1.0, netzbezug_kw=0.0, einspeisung_kw=0.0, verbrauch_kw=None,
                  batterie_kw=-2.0)]         # Ladung 2,0
    b = bilanz_aus_stundenrows(rows, verworfen=MARKE)
    # 4 PV + 4 Netz + 1,5 Entl − 4 Einsp − 2 Lad = 3,5
    assert b.gesamtverbrauch_kwh == pytest.approx(3.5)
    assert b.verbrauch_erfasst is True
    assert b.autarkie_prozent == pytest.approx((3.5 - 4.0) / 3.5 * 100)
    # Altbestand: nur Σ der Stundenwerte — hier keiner ⇒ „nicht erfasst"
    assert bilanz_aus_stundenrows(rows, verworfen=ALTBESTAND).verbrauch_erfasst is False


def test_ev_einmal_bei_null_geklemmt_mit_regelmarke():
    """Vorlage §10 (Entscheid Master 26.09.): mehr Einspeisung als PV ist ein
    Widerspruch der Eingänge, keine negative Kennzahl — EV = max(0, ΣPV − ΣEinsp),
    die Quote 0. Der Wert bleibt stehen (nicht None), die Mengen unverändert."""
    rows = [_row(pv_kw=1.0, einspeisung_kw=3.0, netzbezug_kw=0.5),
            _row(pv_kw=0.0, einspeisung_kw=1.0, netzbezug_kw=0.5)]
    b = bilanz_aus_stundenrows(rows, verworfen={})
    assert b.eigenverbrauch_kwh == 0.0
    assert b.ev_quote_prozent == 0.0
    assert b.einspeisung_kwh == 4.0 and b.erzeugung_kwh == 1.0
