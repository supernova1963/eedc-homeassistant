"""Die CO₂-Komposition aus einem Monats-Fakt — der F-47-Fix selbst (M9).

``services/monats_co2.py`` ist die eine Stelle, an der die Eingaben der
CO₂-Bilanz aus einem ``MonatsFakt`` zusammengestellt werden. Sie ist mit F-47
(2026-08-19) entstanden, weil der Community-Server die Zahl vorher selbst
gerechnet hat — ohne Wärmepumpe und E-Mobilität, rund 22 % zu niedrig.

**Das Modul stand bis heute in keinem Test** (AST-Messung 2026-08-24: 0
Importe im Testbaum). Der Fix, der eine 22-%-Abweichung geheilt hat, war damit
selbst ungedeckt.

⚠ Diese Datei prüft die **Komposition**, nicht die Formel. Die Formel gehört
``berechne_co2_bilanz`` (ADR-001/DI-2) und wird dort geprüft. Hier steht, dass
die richtigen Größen an den richtigen Parametern ankommen — genau das war der
Defekt.
"""

import pytest

from backend.core.calculations import (
    CO2_FAKTOR_BENZIN_KG_LITER,
    CO2_FAKTOR_STROM_KG_KWH,
    berechne_co2_bilanz,
)
from backend.services.monats_co2 import co2_bilanz_aus_fakt
from backend.services.monats_fakten import (
    EmobFakten,
    ErzeugungFakten,
    WpFakten,
    ZaehlerFakten,
)
from backend.tests.factories import mach_kennzahlen, mach_monats_fakt

#: Kurzform für die Factory — jede Probe setzt nur, was sie behauptet (E4/E5).
fakt = mach_monats_fakt


def kennzahlen(eigenverbrauch_kwh: float):
    """Nur der Eigenverbrauch traegt hier — alles andere bleibt 0 (Factory)."""
    return mach_kennzahlen(eigenverbrauch_kwh=eigenverbrauch_kwh)


class TestEigenverbrauchIstDieQuelle:
    """Der Kern von F-47: der Eigenverbrauch wird GELESEN, nicht nachgebaut."""

    def test_pv_anteil_kommt_aus_den_kennzahlen(self):
        bilanz = co2_bilanz_aus_fakt(
            fakt(kennzahlen=kennzahlen(1000.0)), eauto_parameter={}
        )
        assert bilanz.co2_pv_kg == pytest.approx(1000.0 * CO2_FAKTOR_STROM_KG_KWH)

    def test_erzeugung_minus_einspeisung_wird_NICHT_nachgebaut(self):
        """Die Zählerzeile darf die Zahl nicht bewegen.

        Genau dieser Nachbau war der Fehler auf dem Community-Server. Der
        Fakt trägt hier eine Erzeugung/Einspeisung, die zu einem *anderen*
        Eigenverbrauch führen würde — die Bilanz muss sie ignorieren.
        """
        bilanz = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(1000.0),
                erzeugung=ErzeugungFakten(pv_kwh=9999.0, hinter_zaehler_kwh=9999.0),
                zaehler=ZaehlerFakten(einspeisung_kwh=1.0, netzbezug_kwh=1.0),
            ),
            eauto_parameter={},
        )
        assert bilanz.co2_pv_kg == pytest.approx(1000.0 * CO2_FAKTOR_STROM_KG_KWH)


class TestWaermepumpeKommtAn:
    """Die WP fehlte auf dem Server ganz — sie ist der grösste Einzelposten."""

    def test_waerme_und_strom_erreichen_die_bilanz(self):
        ohne = co2_bilanz_aus_fakt(
            fakt(kennzahlen=kennzahlen(0.0)), eauto_parameter={}
        )
        mit = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                wp=WpFakten(waerme_kwh=4000.0, strom_kwh=1000.0),
            ),
            eauto_parameter={},
        )
        assert ohne.co2_wp_kg == 0.0
        assert mit.co2_wp_kg > 0.0
        assert mit.co2_gesamt_kg > ohne.co2_gesamt_kg

    def test_kuehlstrom_wird_getrennt_uebergeben(self):
        """#263 K-2: Kühlen ersetzt keine Heizung.

        Derselbe Strom einmal als Heizstrom und einmal als Kühlstrom muss zu
        verschiedenen WP-Anteilen führen — sonst ist der Parameter nicht
        durchgereicht.
        """
        gemeinsam = dict(kennzahlen=kennzahlen(0.0))
        heizend = co2_bilanz_aus_fakt(
            fakt(**gemeinsam, wp=WpFakten(waerme_kwh=4000.0, strom_kwh=1000.0)),
            eauto_parameter={},
        )
        kuehlend = co2_bilanz_aus_fakt(
            fakt(
                **gemeinsam,
                wp=WpFakten(
                    waerme_kwh=4000.0,
                    strom_kwh=1000.0,
                    modus_strom_kuehlen_kwh=400.0,
                ),
            ),
            eauto_parameter={},
        )
        assert kuehlend.co2_wp_kg != heizend.co2_wp_kg


class TestEmobilitaetKommtAn:
    """km, Netzladung und der Vergleichs-Verbrenner — je Fahrzeug gepflegt."""

    def test_ohne_eauto_ist_der_emob_anteil_null(self):
        bilanz = co2_bilanz_aus_fakt(
            fakt(kennzahlen=kennzahlen(0.0)), eauto_parameter={}
        )
        assert bilanz.co2_emob_kg == 0.0

    def test_benzinmenge_folgt_dem_gepflegten_vergleichsverbrauch(self):
        """Der Verbrenner-Vergleich ist FAHRZEUGSACHE, kein Modellwert."""
        sparsam = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(km=1000.0, km_je_fahrzeug={7: 1000.0}),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 5.0}},
        )
        durstig = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(km=1000.0, km_je_fahrzeug={7: 1000.0}),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 10.0}},
        )
        assert durstig.co2_emob_kg > sparsam.co2_emob_kg

    def test_zwei_fahrzeuge_werden_km_GEWICHTET(self):
        """G20-2: nicht last-write-wins, sondern nach gefahrenen km.

        900 km à 5 l + 100 km à 15 l ⇒ gewichtet 6 l/100 km. Ein
        last-write-wins-Aufrufer käme auf 15 (bzw. 5) und läge weit daneben.
        """
        gewichtet = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(km=1000.0, km_je_fahrzeug={1: 900.0, 2: 100.0}),
            ),
            eauto_parameter={
                1: {"vergleich_verbrauch_l_100km": 5.0},
                2: {"vergleich_verbrauch_l_100km": 15.0},
            },
        )
        erwartet = berechne_co2_bilanz(
            eigenverbrauch_kwh=0.0,
            emob_km=1000.0,
            emob_netz_ladung_kwh=0.0,
            benzin_verbrauch_liter=1000.0 / 100 * 6.0,
        )
        assert gewichtet.co2_emob_kg == pytest.approx(erwartet.co2_emob_kg)

    def test_netzladung_mindert_die_ersparnis(self):
        rein_pv = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(km=1000.0, km_je_fahrzeug={7: 1000.0}),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 8.0}},
        )
        mit_netz = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(
                    km=1000.0, km_je_fahrzeug={7: 1000.0}, ladung_netz_kwh=200.0
                ),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 8.0}},
        )
        assert mit_netz.co2_emob_kg < rein_pv.co2_emob_kg


class TestPlugInHybrid:
    """#331: real getankte Liter mindern die vermiedene Emission."""

    def test_bev_ohne_eigenen_verbrauch_bewegt_nichts(self):
        bev = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(
                    km=1000.0,
                    km_je_fahrzeug={7: 1000.0},
                    fahrverbrauch_je_fahrzeug={7: 180.0},
                ),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 8.0}},
        )
        ohne_fahrverbrauch = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(0.0),
                emob=EmobFakten(km=1000.0, km_je_fahrzeug={7: 1000.0}),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 8.0}},
        )
        assert bev.co2_emob_kg == pytest.approx(ohne_fahrverbrauch.co2_emob_kg)

    def test_phev_mit_gepflegtem_eigenverbrauch_mindert_die_ersparnis(self):
        gemeinsam = dict(
            kennzahlen=kennzahlen(0.0),
            emob=EmobFakten(
                km=1000.0,
                km_je_fahrzeug={7: 1000.0},
                fahrverbrauch_je_fahrzeug={7: 100.0},
            ),
        )
        bev = co2_bilanz_aus_fakt(
            fakt(**gemeinsam),
            eauto_parameter={
                7: {"vergleich_verbrauch_l_100km": 8.0, "verbrauch_kwh_100km": 20.0}
            },
        )
        phev = co2_bilanz_aus_fakt(
            fakt(**gemeinsam),
            eauto_parameter={
                7: {
                    "vergleich_verbrauch_l_100km": 8.0,
                    "verbrauch_kwh_100km": 20.0,
                    "eigener_verbrauch_l_100km": 6.0,
                }
            },
        )
        assert phev.co2_emob_kg < bev.co2_emob_kg
        # 100 kWh bei 20 kWh/100 km ⇒ 500 elektrische km ⇒ 500 km Verbrenner
        # ⇒ 500/100 × 6 l = 30 l × 2,37 kg
        assert bev.co2_emob_kg - phev.co2_emob_kg == pytest.approx(
            30.0 * CO2_FAKTOR_BENZIN_KG_LITER
        )


class TestGesamtsumme:
    """Alle drei Anteile landen in der Summe — das war die 22-%-Lücke."""

    def test_summe_traegt_pv_wp_und_emob(self):
        bilanz = co2_bilanz_aus_fakt(
            fakt(
                kennzahlen=kennzahlen(2000.0),
                wp=WpFakten(waerme_kwh=6000.0, strom_kwh=1500.0),
                emob=EmobFakten(
                    km=12000.0, km_je_fahrzeug={7: 12000.0}, ladung_netz_kwh=500.0
                ),
            ),
            eauto_parameter={7: {"vergleich_verbrauch_l_100km": 7.0}},
        )
        assert bilanz.co2_pv_kg > 0
        assert bilanz.co2_wp_kg > 0
        assert bilanz.co2_emob_kg > 0
        assert bilanz.co2_gesamt_kg == pytest.approx(
            bilanz.co2_pv_kg
            + max(0.0, bilanz.co2_wp_kg)
            + max(0.0, bilanz.co2_emob_kg)
        )
