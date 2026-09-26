"""Zählerlücken wie HA — R3: der Plausibilitäts-Deckel wächst mit der Spanne.

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7, R3 / Schnitt 1.
Ein Slot, der n reale Stunden trägt (HA hat n−1 Stundenzeilen nicht
geschrieben), darf n Stunden Erzeugung enthalten — der Deckel ist
``kwp × 1,5 × n``. Ohne den Faktor würfe der Deckel genau die Lücken-Energie
weg, die der Umbau zurückholt.

Schwesterdateien: test_pv_spike_cap.py, test_zaehlerluecken_schema.py.
"""
from backend.services.snapshot.plausibility import (
    SPIKE_FAKTOR_STUNDE,
    schwelle_pv_einspeisung_stunde_kwh,
)


def test_schwelle_ohne_spanne_unveraendert():
    assert schwelle_pv_einspeisung_stunde_kwh(10.0) == 10.0 * SPIKE_FAKTOR_STUNDE
    assert schwelle_pv_einspeisung_stunde_kwh(10.0, spanne=1) == 15.0


def test_schwelle_waechst_mit_der_spanne():
    assert schwelle_pv_einspeisung_stunde_kwh(10.0, spanne=3) == 45.0
    # Lab-Lücke November 2025: n = 129 ⇒ benannte Grenze ~1,9 MWh (Ü5)
    assert schwelle_pv_einspeisung_stunde_kwh(10.0, spanne=129) == 1935.0


def test_schwelle_ohne_kwp_bleibt_none_auch_mit_spanne():
    assert schwelle_pv_einspeisung_stunde_kwh(None, spanne=5) is None
    assert schwelle_pv_einspeisung_stunde_kwh(0, spanne=5) is None


def test_ungueltige_spanne_zaehlt_als_eins():
    assert schwelle_pv_einspeisung_stunde_kwh(10.0, spanne=0) == 15.0
    assert schwelle_pv_einspeisung_stunde_kwh(10.0, spanne=None) == 15.0
