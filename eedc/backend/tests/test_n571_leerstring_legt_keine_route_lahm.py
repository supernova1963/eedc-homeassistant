"""N-571 — Ein geleertes Zahlen-Parameterfeld legt keine Route mehr lahm (Wächter).

**Der Defekt:** Das Investitions-Formular speichert ein beim Bearbeiten geleertes
Parameter-Feld als ``""`` (F-71-Vertrag, `InvestitionForm.tsx`), und die
Formular-**Vorbelegung** (`paramStr(x, DEFAULT)`) macht fast jedes Zahlenfeld nach
dem ersten Speichern zu einem vorhandenen — also leerbaren — Schlüssel. Rohe
Leser (``params.get(KEY, DEFAULT)``) bekamen das ``""`` und rechneten damit:
TypeError/ValueError ⇒ HTTP 500 der ganzen Sicht. Gemessen (27.09.2026) in
Auswertungen → ROI (E-Auto- **und** Speicher-/WP-Zweig), Cockpit → Aussicht
(`finanz_zerlegung` — ohne jedes Gate, jede Anlage mit Speicher) und
Komponenten → Speicher. Fix: `utils/investition_value.param_zahl`.

**Bauform des Wächters (Gegenprüfung Fassung 2, drei Lehren):**

1. **Feldquelle sind ALLE Keys der PARAM_*-Registry** — es gibt keine Typinfo,
   und die DEFAULTS-Maps sind unvollständig (Wechselrichter/PV-Module haben gar
   keine). Text- und Bool-Felder fahren als ``""`` mit und wächtern so die
   truthy-Annahmen gleich mit. Ein NEUES Registry-Feld wird automatisch geprüft
   (Wächter, keine Regression).
2. **Je (Typ, Feld) eine EINZELPROBE** auf einer Basis, die die Rechenzweige
   ÖFFNET (v2h_faehig/arbitrage_faehig=True, je `effizienz_modus`, WP-Bedarf
   abseits der Vorbelegung). Ein „alle Felder auf ''"-Szenario schaltete über
   die Bool-Gates genau die Zweige ab, die es prüfen soll, und meldete grün
   über nie ausgeführte Leser — die Park-Leertest-Klasse.
3. **Zweite Runde mit ``None``**: explizites ``null`` im parameter-JSON ist im
   Bestand belegt (N-459) und passiert ein ``.get(KEY, DEFAULT)`` ebenso.

Dazu benannte Regressionen: die vier ursprünglich gemessenen E-Auto-Felder, der
Gegenanker „gepflegte Werte ⇒ Zahlen unverändert", die F-15/N-188-Probe
„``pv_ladeanteil_prozent = 0`` ist ein WERT (Prognose 0 %, kein Default)" und
die N-277-Bauform-Probe (Drei-Wege-Semantik des WP-PV-Anteils). Die
Registry-Kopplung Formular↔Backend prüft `test_formular_keys_stehen_in_der_registry`.

**Ehrliche Grenze:** `dashboard_speicher.py` rechnet den Wirkungsgrad-Leser nur
bei vorhandenem η-IST (`eta_ist is not None`); diese Probe stellt kein η-IST
nach — der Leser selbst ist über `param_zahl` gedeckt und läuft in ROI und
Aussichten mit denselben Werten. `get_finanz_prognose` fährt nur die Felder,
die sie liest (Speicher-Preise/-Wirkungsgrad, WP-PV-Anteil), nicht die ganze
Registry — die liest sie auch nicht.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from backend.api.routes.aussichten.finanzen import get_finanz_prognose
from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
from backend.api.routes.investitionen.dashboard_speicher import get_speicher_dashboard
from backend.api.routes.investitionen.roi import get_roi_dashboard
from backend.core import investition_parameter as reg
from backend.models import Anlage, Investition
from backend.utils.investition_value import param_zahl

BACKEND = Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# Basen je Typ — gepflegte Werte, die die Rechenzweige ÖFFNEN (Lehre 2).
# ─────────────────────────────────────────────────────────────────────────────

BASIS_E_AUTO = {
    "batteriekapazitaet_kwh": 62,
    "verbrauch_kwh_100km": 18,
    "jahresfahrleistung_km": 15000,
    "pv_ladeanteil_prozent": 60,
    "vergleich_verbrauch_l_100km": 7.5,
    "eigener_verbrauch_l_100km": 6.0,        # öffnet den PHEV-Zweig (#331)
    "elektrischer_fahranteil_prozent": 80,
    "benzinpreis_euro": 1.70,
    "v2h_faehig": True,                       # öffnet den V2H-Zweig
    "v2h_entladeleistung_kw": 10,
    "v2h_entlade_preis_cent": 25,
    "v2h_entladung_kwh_jahr": 500,
    "ist_dienstlich": False,
    "alternativ_kosten_euro": 0,
}

BASIS_SPEICHER = {
    "kapazitaet_kwh": 10,
    "nutzbare_kapazitaet_kwh": 9,
    "max_ladeleistung_kw": 5,
    "max_entladeleistung_kw": 5,
    "wirkungsgrad_prozent": 95,
    "laedt_aus_netz": True,
    "arbitrage_faehig": True,                 # öffnet den Arbitrage-Preis-Zweig
    "lade_durchschnittspreis_cent": 12,
    "entlade_vermiedener_preis_cent": 35,
    "kopplung": "ac",
}

# Bedarf bewusst ABSEITS der Vorbelegung 12.000/3.000 — sonst sperrt
# `_wp_nicht_bewertbar` („nur Vorbelegung") den ganzen Rechenzweig.
_BASIS_WP = {
    "leistung_kw": 8,
    "heizwaermebedarf_kwh": 11000,
    "warmwasserbedarf_kwh": 2500,
    "waermebedarf_kwh": 13500,
    "alter_energietraeger": "gas",
    "alter_preis_cent_kwh": 12,
    "alternativ_zusatzkosten_jahr": 200,
    "jaz": 3.8,
    "cop_heizung": 4.2,
    "cop_warmwasser": 3.1,
    "scop_heizung": 4.5,
    "scop_warmwasser": 3.3,
    "vorlauftemperatur": 35,
    "pv_anteil_prozent": 30,
}

BASIS_WALLBOX = {"max_ladeleistung_kw": 11}
BASIS_SONSTIGES = {"kategorie": "verbraucher", "beschreibung": "Probe"}


async def _roi(db, anlage_id):
    return await get_roi_dashboard(
        anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )


async def _eauto(db, anlage_id):
    return await get_eauto_dashboard(anlage_id, strompreis_cent=None, db=db)


async def _speicher(db, anlage_id):
    return await get_speicher_dashboard(
        anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None, db=db,
    )


async def _prognose(db, anlage_id):
    return await get_finanz_prognose(anlage_id, monate=12, db=db)


async def _anlage_mit(db, typ: str, params: dict) -> tuple[Anlage, Investition]:
    anlage = Anlage(anlagenname="N571", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung=f"N571-{typ}",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0, leistung_kwp=10.0 if typ == "pv-module" else None,
        parameter=dict(params),
    )
    db.add(inv)
    await db.flush()
    return anlage, inv


async def _probe_je_feld(db, typ, basis, keys, routen):
    """Je Feld zwei Runden ("" und None) über alle genannten Routen."""
    anlage, inv = await _anlage_mit(db, typ, basis)
    for feld in keys:
        for kaputt in ("", None):
            inv.parameter = {**basis, feld: kaputt}
            await db.flush()
            for route in routen:
                try:
                    await route(db, anlage.id)
                except Exception as e:  # noqa: BLE001 — genau das ist der Wächter
                    pytest.fail(
                        f"{typ}: Feld {feld!r} = {kaputt!r} beendet "
                        f"{route.__name__} mit {type(e).__name__}: {e}"
                    )


# ─────────────────────────────────────────────────────────────────────────────
# Der Wächter — je Typ ALLE Registry-Keys (Lehre 1).
# ─────────────────────────────────────────────────────────────────────────────


async def test_e_auto_kein_feld_legt_eine_route_lahm(db):
    await _probe_je_feld(
        db, "e-auto", BASIS_E_AUTO, reg.PARAM_E_AUTO.values(), [_roi, _eauto],
    )


async def test_speicher_kein_feld_legt_eine_route_lahm(db):
    await _probe_je_feld(
        db, "speicher", BASIS_SPEICHER, reg.PARAM_SPEICHER.values(),
        [_roi, _speicher],
    )


async def test_speicher_aussichten_kein_feld_legt_die_prognose_lahm(db):
    """Der Fall OHNE jedes Gate: `finanz_zerlegung` summiert über alle Speicher."""
    await _probe_je_feld(
        db, "speicher", BASIS_SPEICHER,
        [reg.PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
         reg.PARAM_SPEICHER["LADE_DURCHSCHNITTSPREIS_CENT"]],
        [_prognose],
    )


@pytest.mark.parametrize("modus", ["gesamt_jaz", "scop", "getrennte_cops"])
async def test_waermepumpe_kein_feld_legt_eine_route_lahm(db, modus):
    basis = {**_BASIS_WP, "effizienz_modus": modus}
    await _probe_je_feld(
        db, "waermepumpe", basis, reg.PARAM_WAERMEPUMPE.values(), [_roi],
    )


async def test_waermepumpe_aussichten_pv_anteil(db):
    basis = {**_BASIS_WP, "effizienz_modus": "gesamt_jaz"}
    await _probe_je_feld(
        db, "waermepumpe", basis,
        [reg.PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"]], [_prognose],
    )


async def test_uebrige_typen_kein_feld_legt_die_roi_route_lahm(db):
    for typ, param_map, basis in [
        ("wallbox", reg.PARAM_WALLBOX, BASIS_WALLBOX),
        ("wechselrichter", reg.PARAM_WECHSELRICHTER, {}),
        ("pv-module", reg.PARAM_PV_MODULE, {}),
        ("balkonkraftwerk", reg.PARAM_BALKONKRAFTWERK,
         dict(reg.PARAM_BALKONKRAFTWERK_DEFAULTS)),
        ("sonstiges", reg.PARAM_SONSTIGES, BASIS_SONSTIGES),
    ]:
        await _probe_je_feld(db, typ, basis, param_map.values(), [_roi])


# ─────────────────────────────────────────────────────────────────────────────
# Benannte Regressionen und Semantik-Proben.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("feld", [
    "verbrauch_kwh_100km",        # calculations.py:370 — der gemessene TypeError
    "pv_ladeanteil_prozent",      # calculations.py:371
    "vergleich_verbrauch_l_100km",  # calculations.py:379
    "jahresfahrleistung_km",      # phev_anteil.py:93
])
async def test_regression_die_vier_gemessenen_felder(db, feld):
    """Die Wegwerf-Probe vom 27.09. als fester Bestand: leer ⇒ Route läuft."""
    anlage, inv = await _anlage_mit(db, "e-auto", {**BASIS_E_AUTO, feld: ""})
    result = await _roi(db, anlage.id)
    assert result is not None


async def test_gegenanker_gepflegte_werte_bleiben_unveraendert(db):
    """param_zahl ändert an gepflegten Werten NICHTS — gleiche Zahl wie vorher."""
    anlage, inv = await _anlage_mit(db, "e-auto", BASIS_E_AUTO)
    result = await _roi(db, anlage.id)
    b = next(x for x in result.berechnungen if x.investition_id == inv.id)
    # 15.000 km × 18 kWh/100 km = 2.700 kWh — der Hinweis trägt die GEPFLEGTE
    # Fahrleistung unverändert (int, nicht „15000.0"): die GM-Schutzklausel
    # von param_zahl (int bleibt int).
    assert "15000 km/Jahr" in b.detail_berechnung["hinweis"]
    assert b.jahres_einsparung > 0


async def test_f15_pv_ladeanteil_null_ist_ein_wert(db):
    """0 ist eine AUSSAGE (F-15/N-188): kein Rückfall auf IST oder Default 60."""
    anlage, inv = await _anlage_mit(
        db, "e-auto", {**BASIS_E_AUTO, "pv_ladeanteil_prozent": 0},
    )
    mit_null = await _roi(db, anlage.id)
    inv.parameter = {**BASIS_E_AUTO, "pv_ladeanteil_prozent": 60}
    await db.flush()
    mit_sechzig = await _roi(db, anlage.id)
    e0 = next(x for x in mit_null.berechnungen if x.investition_id == inv.id)
    e60 = next(x for x in mit_sechzig.berechnungen if x.investition_id == inv.id)
    # 0 % PV-Ladung ⇒ voller Netzstrompreis ⇒ geringere Ersparnis als bei 60 %.
    assert e0.jahres_einsparung < e60.jahres_einsparung


def test_n277_drei_wege_bauform_des_wp_pv_anteils():
    """Die Ausnahme-Bauform (N-277/N-354): fehlend ⇒ Default, ""/None ⇒ None.

    `_gepflegter_pv_anteil` ist eine in `get_finanz_prognose` eingebettete
    Funktion; die Probe prüft die Bauform selbst (identischer Ausdruck) und
    ein Quelltext-Anker hält fest, dass die Stelle sie trägt.
    """
    key = reg.PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"]
    default = reg.PARAM_WAERMEPUMPE_DEFAULTS["pv_anteil_prozent"]

    def lese(params):
        return default if key not in params else param_zahl(params, key)

    assert lese({}) == default                      # nie gepflegt ⇒ Default 30
    assert lese({key: ""}) is None                  # geleert ⇒ fällt aus dem Mittel
    assert lese({key: None}) is None                # genullt (N-459) ⇒ ebenso
    assert lese({key: 0}) == 0                      # 0 bleibt Wert (F-15)
    assert lese({key: 40}) == 40

    quelle = (BACKEND / "api/routes/aussichten/finanz_prognose.py").read_text()
    assert re.search(
        r'if PARAM_WAERMEPUMPE\["PV_ANTEIL_PROZENT"\] not in params', quelle,
    ), "finanz_prognose.py trägt die Drei-Wege-Bauform (N-277) nicht mehr"


def test_param_zahl_semantik():
    """Der Helfer selbst: alle Gestalten von „nicht gepflegt", 0 bleibt, int bleibt."""
    assert param_zahl(None, "x", 5) == 5
    assert param_zahl({}, "x", 5) == 5
    assert param_zahl({"x": None}, "x", 5) == 5
    assert param_zahl({"x": ""}, "x", 5) == 5
    assert param_zahl({"x": "abc"}, "x", 5) == 5
    assert param_zahl({"x": True}, "x", 5) == 5      # bool ist kein Zahlwert
    assert param_zahl({"x": 0}, "x", 5) == 0         # F-15: 0 ist ein Wert
    assert param_zahl({"x": "0"}, "x", 5) == 0.0
    assert param_zahl({"x": 15000}, "x") == 15000    # int bleibt int (GM-Schutz)
    assert isinstance(param_zahl({"x": 15000}, "x"), int)
    assert param_zahl({"x": "3.5"}, "x") == 3.5
    assert param_zahl({"x": 2.5}, "x") == 2.5


def test_formular_keys_stehen_in_der_registry():
    """Jedes Formular-Parameterfeld (`paramStr(params.<key>`) steht in einer
    PARAM_*-Map — sonst prüft der Wächter oben ein NEUES Feld nicht mit."""
    helpers = (
        BACKEND.parent / "frontend/src/components/forms/sections/investitionFormHelpers.ts"
    ).read_text()
    formular_keys = set(re.findall(r"paramStr\(params\.(\w+)", helpers))
    registry_keys = set()
    for name in dir(reg):
        wert = getattr(reg, name)
        if name.startswith("PARAM_") and isinstance(wert, dict) and not name.endswith("_DEFAULTS"):
            registry_keys |= set(wert.values())
    fehlend = formular_keys - registry_keys
    assert not fehlend, (
        f"Formularfelder ohne Registry-Eintrag (der N-571-Wächter sieht sie nicht): {sorted(fehlend)}"
    )
