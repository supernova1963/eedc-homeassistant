"""SoT-Helper für Investitions-Kennwerte (`core/investition_kennwerte.py`).

Gesichert wird hier, was ADR-002/P3-a zusichert und was der Kennwert-Sweep zu
#229 an Varianten gefunden hat:

1. alle Prioritätsstufen von `get_pv_kwp` und `get_bkw_kwp` — eine fehlende
   Stufe fällt still auf 0 und zieht das Modul aus jeder Σ heraus (N52/N66);
2. `get_bkw_kwp ⊇ get_pv_kwp` — ein BKW, das versehentlich wie ein PV-Modul
   gepflegt wurde, darf nicht auf 0 fallen;
3. der `anzahl`-Lese-Default 1 gegen die Formular-Vorbelegung 2;
4. der Typ-Dispatcher — ohne ihn schreibt jede Read-Site wieder ihre eigene
   `if typ == "balkonkraftwerk"`-Fallunterscheidung (acht erhobene Varianten);
5. die 0-Semantik (N-C): Spalte 0 heißt bei der kWp „nicht gepflegt", und
   `get_pv_kwp` und `get_inv_value` müssen darin übereinstimmen;
6. dass `services/pv_orientation.get_pv_kwp` ein Re-Export ist und keine Kopie.
"""

from __future__ import annotations

from backend.core.investition_kennwerte import (
    ANZAHL_LESE_DEFAULT,
    get_bkw_kwp,
    get_erzeuger_kwp,
    get_pv_kwp,
)
from backend.core.investition_parameter import PARAM_BALKONKRAFTWERK_DEFAULTS
from backend.models import Investition
from backend.utils.investition_value import get_inv_value


def _pv(**kwargs) -> Investition:
    return Investition(typ="pv-module", bezeichnung="Modul", **kwargs)


def _bkw(**kwargs) -> Investition:
    return Investition(typ="balkonkraftwerk", bezeichnung="Balkon", **kwargs)


# ---------------------------------------------------------------- get_pv_kwp

def test_pv_stufe_1_spalte_gewinnt():
    inv = _pv(leistung_kwp=10.0, parameter={"kwp": 99.0, "leistung_kwp": 98.0})
    assert get_pv_kwp(inv) == 10.0


def test_pv_stufe_2_legacy_key_kwp():
    inv = _pv(leistung_kwp=None, parameter={"kwp": 8.4})
    assert get_pv_kwp(inv) == 8.4


def test_pv_stufe_3_kanonischer_key_leistung_kwp():
    inv = _pv(leistung_kwp=None, parameter={"leistung_kwp": 7.5})
    assert get_pv_kwp(inv) == 7.5


def test_pv_stufe_2_vor_stufe_3():
    """Reihenfolge unverändert gegenüber dem Umzug aus `pv_orientation.py`."""
    inv = _pv(leistung_kwp=None, parameter={"kwp": 8.4, "leistung_kwp": 7.5})
    assert get_pv_kwp(inv) == 8.4


def test_pv_stufe_4_nichts_gepflegt_ist_null():
    assert get_pv_kwp(_pv(leistung_kwp=None, parameter={})) == 0.0
    assert get_pv_kwp(_pv(leistung_kwp=None, parameter=None)) == 0.0


def test_pv_unbrauchbarer_wert_faellt_weiter_durch():
    inv = _pv(leistung_kwp=None, parameter={"kwp": "keine Zahl", "leistung_kwp": 7.5})
    assert get_pv_kwp(inv) == 7.5


# --------------------------------------------------------------- get_bkw_kwp

def test_bkw_stufe_1_spalte_gewinnt():
    inv = _bkw(leistung_kwp=0.8, parameter={"leistung_wp": 400, "anzahl": 4})
    assert get_bkw_kwp(inv) == 0.8


def test_bkw_stufe_2_legacy_key_kwp():
    inv = _bkw(leistung_kwp=None, parameter={"kwp": 0.6})
    assert get_bkw_kwp(inv) == 0.6


def test_bkw_stufe_3_kanonischer_key_leistung_kwp():
    inv = _bkw(leistung_kwp=None, parameter={"leistung_kwp": 0.6})
    assert get_bkw_kwp(inv) == 0.6


def test_bkw_stufe_4_leistung_wp_mal_anzahl():
    inv = _bkw(leistung_kwp=None, parameter={"leistung_wp": 400, "anzahl": 2})
    assert get_bkw_kwp(inv) == 0.8


def test_bkw_stufe_5_nichts_gepflegt_ist_null():
    assert get_bkw_kwp(_bkw(leistung_kwp=None, parameter={})) == 0.0
    assert get_bkw_kwp(_bkw(leistung_kwp=None, parameter={"anzahl": 4})) == 0.0
    assert get_bkw_kwp(_bkw(leistung_kwp=None, parameter=None)) == 0.0


def test_bkw_kwp_stufe_geht_der_wp_stufe_vor():
    """`get_bkw_kwp ⊇ get_pv_kwp`: ein wie ein PV-Modul gepflegtes BKW.

    Ohne diese Reihenfolge liefert der Helper für dieses Objekt 0 — genau der
    Verlust, den `aussichten.py` sich mit `get_pv_kwp` auf BKW eingehandelt hat,
    nur umgekehrt.
    """
    inv = _bkw(leistung_kwp=None, parameter={"kwp": 0.6, "leistung_wp": 400})
    assert get_bkw_kwp(inv) == 0.6


def test_bkw_ist_superset_von_pv():
    for parameter in ({"kwp": 0.6}, {"leistung_kwp": 0.6}, {}):
        inv = _bkw(leistung_kwp=None, parameter=dict(parameter))
        assert get_bkw_kwp(inv) >= get_pv_kwp(inv)


def test_bkw_anzahl_default_ist_eins_nicht_die_formular_vorbelegung():
    """Ungepflegte `anzahl` ⇒ 1 — sonst wird still die doppelte Leistung
    ausgewiesen (und damit der halbe spezifische Ertrag)."""
    assert ANZAHL_LESE_DEFAULT == 1
    assert PARAM_BALKONKRAFTWERK_DEFAULTS["anzahl"] == 2  # Vorbelegung, kein Lese-Default
    inv = _bkw(leistung_kwp=None, parameter={"leistung_wp": 800})
    assert get_bkw_kwp(inv) == 0.8


def test_bkw_anzahl_null_zaehlt_als_ungepflegt():
    inv = _bkw(leistung_kwp=None, parameter={"leistung_wp": 800, "anzahl": 0})
    assert get_bkw_kwp(inv) == 0.8


def test_bkw_leistung_wp_null_wirft_nicht():
    """N-H: `leistung_wp: null` warf in einer der Kopien einen TypeError."""
    inv = _bkw(leistung_kwp=None, parameter={"leistung_wp": None, "anzahl": 2})
    assert get_bkw_kwp(inv) == 0.0


# ----------------------------------------------------------- get_erzeuger_kwp

def test_dispatcher_bkw_nutzt_die_bkw_formel():
    inv = _bkw(leistung_kwp=None, parameter={"leistung_wp": 400, "anzahl": 2})
    assert get_erzeuger_kwp(inv) == 0.8
    assert get_pv_kwp(inv) == 0.0  # der Grund, warum es den Dispatcher gibt


def test_dispatcher_pv_modul_nutzt_die_pv_formel():
    inv = _pv(leistung_kwp=None, parameter={"kwp": 8.4, "leistung_wp": 400})
    assert get_erzeuger_kwp(inv) == 8.4


def test_dispatcher_fremder_typ_faellt_auf_pv_pfad():
    inv = Investition(typ="wechselrichter", bezeichnung="WR", leistung_kwp=10.0)
    assert get_erzeuger_kwp(inv) == 10.0


def test_dispatcher_ohne_typ_faellt_auf_pv_pfad():
    class Ohne:
        leistung_kwp = 5.0
        parameter: dict = {}

    assert get_erzeuger_kwp(Ohne()) == 5.0


# ------------------------------------------------------------- 0-Semantik N-C

def test_spalte_null_gilt_als_ungepflegt_und_faellt_durch():
    """Eine Nennleistung von exakt 0 ist kein Messwert, sondern „nicht
    gepflegt" — der parameter-Fallback muss greifen."""
    inv = _pv(leistung_kwp=0.0, parameter={"leistung_kwp": 8.4})
    assert get_pv_kwp(inv) == 8.4


def test_beide_sot_helper_haben_dieselbe_null_semantik():
    """N-C: vorher lieferten sie für dieselbe Investition 8.4 bzw. 0.0."""
    inv = _pv(leistung_kwp=0.0, parameter={"leistung_kwp": 8.4})
    assert get_inv_value(inv, "leistung_kwp") == get_pv_kwp(inv) == 8.4


def test_null_ohne_parameter_bleibt_null():
    inv = _pv(leistung_kwp=0.0, parameter={})
    assert get_pv_kwp(inv) == 0.0
    assert get_inv_value(inv, "leistung_kwp") == 0.0


def test_get_inv_value_spalte_hat_weiter_vorrang():
    """Die 0-Ausnahme darf den Spalten-Vorrang nicht aufweichen (#229)."""
    inv = _pv(leistung_kwp=12.0, parameter={"leistung_kwp": 99.0})
    assert get_inv_value(inv, "leistung_kwp") == 12.0


def test_get_inv_value_bleibt_generisch_is_not_none():
    """Für nicht spalten-gemappte Felder ändert sich nichts."""
    inv = Investition(typ="speicher", bezeichnung="Bat", parameter={"kapazitaet_kwh": 10.0})
    assert get_inv_value(inv, "kapazitaet_kwh") == 10.0


# ------------------------------------------------------------------ Re-Export

def test_pv_orientation_re_exportiert_dieselbe_funktion():
    """Genau EINE Implementierung — keine Kopie neben dem Original."""
    from backend.services import pv_orientation

    assert pv_orientation.get_pv_kwp is get_pv_kwp
