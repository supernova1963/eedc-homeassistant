"""Wächter für den abgeleiteten PV-Anteil einer Heimladung (N-141 (c)).

⚠ **Die Vorzeichenkonvention der Fixtures ist Teil der Aussage.** Die Eingänge
stammen aus ``get_hourly_kwh_by_category`` bzw. ``…_lts`` und sind dort
durchweg **positive** Zähler-Deltas — auch die Senken (``wallbox``) und die
Speicherentladung (``entladung_batterie``, siehe ``lts_aggregator.py:180-182``).
Der ``komponenten``-JSON des Tages-Leistungspfads führt Senken dagegen negativ.
Wer diese Proben auf negative Ladung umschriebe, prüfte eine Konvention, die an
dieser Schnittstelle nicht gilt — genau die Klasse, mit der am 2026-08-08 eine
Fixture die Wallbox-Doppelzählung (F-14) ein halbes Jahr lang verdeckt hat.
"""

import pytest

from backend.core.berechnungen.pv_anteil_ladung import (
    REGEL_EINSPEISE_DECKUNG,
    leite_pv_anteil_ab,
)


def _stunde(ladung, netzbezug=0.0, einspeisung=0.0, speicher_entladung=0.0):
    """Eine Ladestunde in der Konvention des Stunden-Aggregators (alles positiv)."""
    return {
        "ladung": ladung,
        "netzbezug": netzbezug,
        "einspeisung": einspeisung,
        "speicher_entladung": speicher_entladung,
    }


class TestKeineAussage:
    """``None`` heißt „keine Aussage" — nie „0 kWh aus PV"."""

    def test_ohne_stunden_keine_aussage(self):
        assert leite_pv_anteil_ab([]) is None

    def test_ohne_ladung_keine_aussage(self):
        # Netzbezug ja, Ladung nein — der Tag sagt über die Heimladung nichts.
        assert leite_pv_anteil_ab([_stunde(0.0, netzbezug=3.0)]) is None

    @pytest.mark.parametrize("fehlt", ["netzbezug", "einspeisung"])
    def test_fehlender_pflicht_eingang_deckt_die_stunde_nicht(self, fehlt):
        """Ein fehlender Eingang darf NICHT als 0 gelesen werden.

        Sonst wäre ``ladung − 0 − 0`` die ganze Ladung und die Stunde fiele
        vollständig der Sonne zu — eine Behauptung aus einer Lücke.
        """
        stunde = _stunde(5.0, netzbezug=5.0, einspeisung=0.0)
        stunde[fehlt] = None
        assert leite_pv_anteil_ab([stunde]) is None

    def test_fehlender_speicher_ist_kein_mangel(self):
        """Eine Anlage ohne Batterie hat hier dauerhaft nichts stehen."""
        ohne_feld = leite_pv_anteil_ab([{"ladung": 4.0, "netzbezug": 0.0, "einspeisung": 2.0}])
        assert ohne_feld is not None
        assert ohne_feld.pv_kwh == 4.0


class TestRegelEinspeiseDeckung:
    """Die drei Lagen, die den Anteil bestimmen."""

    def test_nachtladung_ist_netzstrom(self):
        # Ladung vollständig aus dem Netz gedeckt, keine Einspeisung.
        r = leite_pv_anteil_ab([_stunde(5.0, netzbezug=5.0)])
        assert r.pv_kwh == 0.0
        assert r.netz_kwh == 5.0

    def test_ueberschussladung_ist_pv(self):
        # Kein Netzbezug: die Ladung kann nur aus der Sonne gekommen sein.
        r = leite_pv_anteil_ab([_stunde(5.0, netzbezug=0.0, einspeisung=3.0)])
        assert r.pv_kwh == 5.0
        assert r.netz_kwh == 0.0

    def test_einspeisung_belegt_zusaetzlichen_ueberschuss(self):
        """Gemischte Stunde: Bezug UND Einspeisung stehen nebeneinander.

        Das ist der Regelfall der Stundenmittelung. Ohne die Einspeisung als
        Deckungsbeleg fiele die ganze Stunde ans Netz, obwohl nachweislich
        Überschuss vorhanden war.
        """
        r = leite_pv_anteil_ab([_stunde(3.0, netzbezug=3.0, einspeisung=2.0)])
        assert r.pv_kwh == 2.0
        assert r.netz_kwh == 1.0

    def test_speicherentladung_zaehlt_nicht_als_pv(self):
        """Was der Speicher liefert, ist nicht Direktverbrauch aus der Sonne.

        Bewusst konservativ und mit evcc konsistent (Buffer-SoC). Die Messung
        vom 2026-08-08 hat genau diese Variante als treffsicherste bestätigt.
        """
        r = leite_pv_anteil_ab([_stunde(5.0, netzbezug=0.0, speicher_entladung=5.0)])
        assert r.pv_kwh == 0.0
        assert r.netz_kwh == 5.0

    def test_regel_wird_benannt(self):
        r = leite_pv_anteil_ab([_stunde(1.0, netzbezug=1.0)])
        assert r.regel == REGEL_EINSPEISE_DECKUNG


class TestInvarianten:
    def test_summe_bleibt_die_ladung_der_gedeckten_stunden(self):
        """Die Aufteilung verschiebt, sie wirft nichts weg und erfindet nichts."""
        stunden = [
            _stunde(4.0, netzbezug=4.0),
            _stunde(6.0, netzbezug=0.0, einspeisung=5.0),
            _stunde(3.0, netzbezug=2.0, einspeisung=1.0, speicher_entladung=0.5),
        ]
        r = leite_pv_anteil_ab(stunden)
        assert r.ladung_kwh == pytest.approx(13.0)
        assert r.pv_kwh + r.netz_kwh == pytest.approx(13.0)
        assert r.stunden_gedeckt == 3
        assert r.vollstaendig is True

    def test_teilweise_gedeckt_wird_ausgewiesen_statt_verschwiegen(self):
        """Der TEILWEISE gedeckte Fall ist der eigentliche Prüfstein (P4).

        Eine Stunde ohne Eingänge darf die Summe nicht stillschweigend
        verkleinern — sie muss als Lücke sichtbar bleiben, sonst liest der
        Aufrufer eine Teilsumme als Tageswert.
        """
        stunden = [
            _stunde(4.0, netzbezug=0.0, einspeisung=4.0),
            {"ladung": 6.0, "netzbezug": None, "einspeisung": None},
        ]
        r = leite_pv_anteil_ab(stunden)
        assert r.stunden_gedeckt == 1
        assert r.stunden_mit_ladung == 2
        assert r.vollstaendig is False
        # Nur die gedeckte Stunde ist bewertet — die 6 kWh fehlen bewusst.
        assert r.ladung_kwh == pytest.approx(4.0)

    def test_pv_anteil_liegt_immer_zwischen_null_und_ladung(self):
        """Auch bei widersprüchlichen Eingängen bleibt der Anteil im Rahmen.

        Ein Netzbezug größer als die Ladung (Haushalt zieht mit) oder eine
        Einspeisung größer als die Ladung darf weder negative noch überhöhte
        PV-Anteile erzeugen.
        """
        for stunde in (
            _stunde(2.0, netzbezug=20.0),
            _stunde(2.0, netzbezug=0.0, einspeisung=50.0),
            _stunde(2.0, netzbezug=20.0, einspeisung=50.0, speicher_entladung=10.0),
        ):
            r = leite_pv_anteil_ab([stunde])
            assert 0.0 <= r.pv_kwh <= 2.0
            assert 0.0 <= r.netz_kwh <= 2.0
            assert r.pv_kwh + r.netz_kwh == pytest.approx(2.0)


class TestGemesseneReferenz:
    """Die Regel ist an Gernots Anlage gegen evcc vermessen worden.

    Referenz 2026-08-08: Feb–Aug 2026, 963 kWh Heimladung, evcc 67,9 % PV,
    diese Regel 64,7 % (−3,2 pp). Der Test hält den Charakter fest, den die
    Messung gezeigt hat — die Regel untertreibt eher, als zu schmeicheln.
    """

    def test_regel_untertreibt_gegenueber_der_rein_netzbasierten_variante(self):
        # Dieselben Stunden, einmal mit Speicher/Einspeisungswissen.
        # Rein netzbasiert (ladung − netzbezug) ergäbe hier 5 kWh PV;
        # die Speicherdeckung nimmt davon 3 kWh zurück.
        stunden = [_stunde(5.0, netzbezug=0.0, einspeisung=0.0, speicher_entladung=3.0)]
        r = leite_pv_anteil_ab(stunden)
        naiv_netzbasiert = 5.0 - 0.0
        assert r.pv_kwh < naiv_netzbasiert
        assert r.pv_kwh == 2.0
