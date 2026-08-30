"""Eine Quelle für alle Prognosezahlen des Live-Blocks (Entscheid Gernot, 2026-08-30).

Anlass: zwei Melder am selben Tag, aus entgegengesetzter Richtung.
* **Burkard** (Issue #401): Bei SFML als Quelle standen „heute erwartet 28,7 kWh",
  „verbleibend 9,0" und „IST 6,9" nebeneinander — 6,9 + 9,0 ergibt nicht 28,7.
* **rapahl** (PN 91821): Bei ihm (eedc-Quelle) standen 23,5 kWh erzeugt gegen
  eine Kopfzahl von 17,6 kWh und 1,7 kWh Rest.

Schwesterdateien: test_prognose_kanon.py, test_prognose_kanon_wettermodell_a30.py,
test_live_wetter_grund.py.

Ursache in beiden Fällen: `pv_prognose_aktiv` folgte der gewählten Quelle, `rest`
und `rollend` kamen aber immer aus dem Kanon — der laut eigenem Docstring IMMER
eedc rechnet. Drei Zahlen aus zwei Rechenwegen addieren sich nicht.
"""
from datetime import datetime

import pytest

from backend.services.prognose_kanon import rest_aus_slots, vm_nm_split


def _slots(von=7, bis=20, wert=2.0):
    s = [0.0] * 24
    for h in range(von, bis):
        s[h] = wert
    return s


class TestRestAusSlots:
    def test_laufende_stunde_zaehlt_anteilig(self):
        """Der Rest sinkt gleichmäßig, nicht in Stundensprüngen (#339).

        ⛔ Sprengsatz-Anker: Fällt der `frac`-Term weg, liefern 12:00 und 12:30
        DENSELBEN Wert — genau der Sprung, gegen den #339 gebaut wurde.
        """
        slots = _slots()
        voll = rest_aus_slots(slots, datetime(2026, 8, 30, 12, 0))
        halb = rest_aus_slots(slots, datetime(2026, 8, 30, 12, 30))
        assert voll is not None and halb is not None
        assert halb < voll, "ohne anteilige Stunde springt der Rest nur stündlich"
        # 12:00: Slots 13..19 = 7 × 2,0 ; 12:30: halbe laufende Stunde weniger
        assert voll == pytest.approx(14.0)
        assert halb == pytest.approx(13.0)

    def test_ohne_profil_kein_rest(self):
        """Keine Stundenwerte ⇒ None, nicht 0.

        Eine 0 wäre die Behauptung „heute kommt nichts mehr"; richtig ist
        „unbekannt". Genau darauf beruht die Entscheidung, für eine Quelle ohne
        Stundenprofil gar keinen Rest zu zeigen.
        """
        assert rest_aus_slots([], datetime(2026, 8, 30, 12, 0)) is None
        assert rest_aus_slots(None, datetime(2026, 8, 30, 12, 0)) is None

    def test_nach_sonnenuntergang_null(self):
        assert rest_aus_slots(_slots(), datetime(2026, 8, 30, 23, 30)) == pytest.approx(0.0)

    def test_fremde_slots_ergeben_fremden_rest(self):
        """DER Kern: dieselbe Formel auf ANDEREN Slots ergibt eine andere Zahl.

        Das ist die Eigenschaft, auf der der ganze Fix beruht — der Kanon wird
        nicht umgebaut (»Solcast/SFML sind eigene Pfade« ist seine
        Entwurfsentscheidung), es wird SEINE Formel auf FREMDE Slots angewandt.
        """
        jetzt = datetime(2026, 8, 30, 12, 0)
        eedc = rest_aus_slots(_slots(wert=2.0), jetzt)
        sfml = rest_aus_slots(_slots(wert=3.0), jetzt)
        assert eedc != sfml
        assert sfml == pytest.approx(eedc * 1.5)


class TestVmNmSplitOeffentlich:
    def test_split_summiert_auf_die_tagesmenge(self):
        """VM + NM = Σ Slots — der Split verliert und erfindet nichts."""
        slots = _slots()
        vm, nm = vm_nm_split(slots, "2026-08-30", 10.68)
        assert vm is not None and nm is not None
        assert vm + nm == pytest.approx(sum(slots), abs=0.15)

    def test_ohne_laengengrad_kein_split(self):
        """Ohne Solar Noon keine Hälften — statt einer geratenen 12-Uhr-Grenze."""
        assert vm_nm_split(_slots(), "2026-08-30", None) == (None, None)

    def test_fremde_slots_ergeben_fremde_haelften(self):
        """Auch VM/NM folgen der gewählten Quelle, nicht dem Kanon."""
        vm_a, nm_a = vm_nm_split(_slots(wert=2.0), "2026-08-30", 10.68)
        vm_b, nm_b = vm_nm_split(_slots(wert=3.0), "2026-08-30", 10.68)
        assert (vm_a, nm_a) != (vm_b, nm_b)
