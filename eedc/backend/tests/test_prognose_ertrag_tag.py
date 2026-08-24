"""Die Tages-Ertragsformel der Aussichten — bis E6 ohne jede Testberührung (M9).

``berechne_pv_ertrag_tag`` ist die Formel, die die Aussichten- und
Prognose-Endpoints je Vorhersagetag anwenden. Sie stand in keinem Test, weder
namentlich noch über ihr Modul (AST-Messung 2026-08-24: 0 Testdateien).

Was hier festgehalten wird, ist die Formel selbst — Basisrechnung,
Temperaturkorrektur mit ihrer 25-°C-Schwelle, die Null-Fälle und die Rundung.
"""

import pytest

from backend.services.prognose_service import (
    TEMP_COEFFICIENT,
    berechne_pv_ertrag_tag,
)
from backend.services.pv_orientation import DEFAULT_SYSTEM_LOSSES


class TestBasisformel:
    """PV_kwh = Globalstrahlung × kWp × (1 − Systemverluste)."""

    def test_ohne_temperatur_gilt_die_reine_basisformel(self):
        ertrag = berechne_pv_ertrag_tag(
            globalstrahlung_kwh_m2=5.0, anlagenleistung_kwp=10.0
        )
        assert ertrag == round(5.0 * 10.0 * (1 - DEFAULT_SYSTEM_LOSSES), 2)

    def test_systemverluste_sind_ueberschreibbar(self):
        assert berechne_pv_ertrag_tag(
            globalstrahlung_kwh_m2=4.0,
            anlagenleistung_kwp=5.0,
            system_losses=0.0,
        ) == 20.0

    def test_ertrag_skaliert_linear_mit_der_kwp(self):
        einfach = berechne_pv_ertrag_tag(3.0, 5.0, system_losses=0.0)
        doppelt = berechne_pv_ertrag_tag(3.0, 10.0, system_losses=0.0)
        assert doppelt == pytest.approx(2 * einfach)

    def test_ergebnis_ist_auf_zwei_stellen_gerundet(self):
        # 1.234 × 1 × (1 − 0) = 1.234 → 1.23
        assert berechne_pv_ertrag_tag(1.234, 1.0, system_losses=0.0) == 1.23


class TestTemperaturkorrektur:
    """Module werden bei Hitze ineffizienter — Schwelle ist 25 °C."""

    def test_bis_einschliesslich_25_grad_keine_korrektur(self):
        ohne = berechne_pv_ertrag_tag(5.0, 10.0, system_losses=0.0)
        assert berechne_pv_ertrag_tag(
            5.0, 10.0, temperatur_max_c=25.0, system_losses=0.0
        ) == ohne
        assert berechne_pv_ertrag_tag(
            5.0, 10.0, temperatur_max_c=-10.0, system_losses=0.0
        ) == ohne

    def test_der_koeffizient_ist_0_004_pro_kelvin(self):
        """Der Zahlenwert steht HIER, nicht als Import.

        Erst gegen ``TEMP_COEFFICIENT`` gerechnet — das war eine Tautologie:
        ein verdoppelter Koeffizient liess die Probe gruen. Gemessen beim Bau.
        """
        assert TEMP_COEFFICIENT == 0.004
        # 35 °C ⇒ 10 K über der Schwelle ⇒ 10 × 0,004 = 4 % Verlust
        assert berechne_pv_ertrag_tag(
            5.0, 10.0, temperatur_max_c=35.0, system_losses=0.0
        ) == 48.0

    def test_ein_grad_ueber_der_schwelle_greift_schon(self):
        """Pinnt die Schwelle SELBST — nicht nur, dass es irgendwo warm mindert.

        Ohne diesen Fall bleibt die Probe gruen, wenn jemand die Schwelle von
        25 auf 30 °C verschiebt: alle uebrigen Faelle liegen entweder auf 25
        oder deutlich darueber. Genau so ist es beim Bau dieser Datei passiert.
        """
        ohne = berechne_pv_ertrag_tag(5.0, 10.0, system_losses=0.0)
        bei_26 = berechne_pv_ertrag_tag(
            5.0, 10.0, temperatur_max_c=26.0, system_losses=0.0
        )
        assert bei_26 < ohne
        assert bei_26 == 49.8      # 50 × (1 − 1 × 0,004)

    def test_je_heisser_desto_weniger(self):
        werte = [
            berechne_pv_ertrag_tag(5.0, 10.0, temperatur_max_c=t, system_losses=0.0)
            for t in (26.0, 30.0, 40.0)
        ]
        assert werte[0] > werte[1] > werte[2]

    def test_temperatur_none_verhaelt_sich_wie_keine_angabe(self):
        assert berechne_pv_ertrag_tag(
            5.0, 10.0, temperatur_max_c=None, system_losses=0.0
        ) == berechne_pv_ertrag_tag(5.0, 10.0, system_losses=0.0)


class TestNullFaelle:
    """Was nichts einbringt, bringt 0.0 — nie ``None`` und nie negativ."""

    @pytest.mark.parametrize("strahlung", [None, 0.0, -1.5])
    def test_ohne_strahlung_null(self, strahlung):
        assert berechne_pv_ertrag_tag(strahlung, 10.0) == 0.0

    def test_ohne_anlagenleistung_null(self):
        assert berechne_pv_ertrag_tag(5.0, 0.0) == 0.0

    def test_ergebnis_wird_nie_negativ(self):
        # Systemverluste > 1 ergäben rechnerisch einen negativen Ertrag
        assert berechne_pv_ertrag_tag(5.0, 10.0, system_losses=1.5) == 0.0
