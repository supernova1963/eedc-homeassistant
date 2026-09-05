"""B3 — Matrix-Durchgang Komponenten-Hub (SOLL Wärme/Klima §3.2a × §6 F1–F12), 05.09.2026.

Je Sprosse EIN Gerät mit genau der Datenlage der Sprosse, dann der Hub
(`get_waermepumpe_dashboard`) und daneben Cockpit → Monat (`get_aktueller_monat`).
Drei Fragen je Zelle (SOLL §8): erscheint die Größe? steht sonst der **Grund**
daneben (S3)? stimmt sie mit der Nachbarsicht überein (S1, P10/P12)?

**Was die Messung gefunden hat (IST §11):**

* **H-1** Die Hub-Ersparnis las den Strom aus der Rohspalte `stromverbrauch_kwh`.
  Bei getrennter Strommessung (F5/F7) ist sie leer — WP-Kosten 0 €, Ersparnis =
  volle Alt-Kosten (F7: 480 € statt 180 €). Nachbarsichten rechnen mit
  `get_wp_strom_kwh`. Dritte Runde der W-15-Klasse.
* **H-1b** Monatstabelle und Monats-/Saisonvergleich lasen dieselbe Rohspalte im
  Client. Jetzt trägt `jaz_je_monat` den Strom nach dem SoT.
* **H-2** Abgeleitete Wärme (F2b) stand als nackte Zahl neben gemessenen; Ersparnis
  und CO₂ ohne Kennzeichnung (§3.3 Hub-Zeile, §6 Präzisierung 05.09.). Jetzt:
  `waerme_herkunft` und `ersparnis_vorbehalt` aus dem Layer — der Vorbehalt gilt
  auch im bivalenten Fall F12 (Entscheid Gernot 05.09.).
* **N-114** Der BKW-Route-Parameter `einspeiseverguetung_cent` wurde nie gelesen.

Die Symmetrie Hub ≡ Cockpit über alle Sprossen ist der Wächter gegen die nächste
Runde derselben Klasse: Wer eine Sicht allein umbaut, sieht hier Rot.

Schwesterdateien: test_soll_waerme_klima_simulation_anlagen.py (A1–A8, dieselbe
Bauform), test_waerme_vorschlag_b1.py (Sprossen im Vorschlagsdienst),
test_b2_daten_checker_registry.py (Paket 2 derselben Reihe).
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDWAERME,
    HERKUNFT_GEMESSEN,
    VORBEHALT_ABGELEITET,
    VORBEHALT_FREMDWAERME,
    ersparnis_vorbehalt,
    waerme_herkunft,
)
from backend.models import Anlage, Investition  # noqa: F401
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

JAHR, MONAT = 2025, 7
ABGELEITET = {"abgeleitet": "jaz_vorschlag", "source": "auto:jaz_vorschlag"}


async def _anlage(db, name: str) -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    return a


async def _geraet(db, anlage, parameter: dict, daten: dict | None, provenance: dict | None = None):
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    if daten is not None:
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=JAHR, monat=MONAT, verbrauch_daten=daten,
            source_provenance=provenance or {},
        ))
    return inv


async def _hub(db, anlage_id) -> dict:
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard
    return (await get_waermepumpe_dashboard(anlage_id, strompreis_cent=30.0, db=db))[0].zusammenfassung


async def _monat(db, anlage_id):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    return await get_aktueller_monat(anlage_id, jahr=JAHR, monat=MONAT, db=db)


# Gas 12 ct/kWh, η 0,9 (Default) → Alt-Kosten = Q / 0,9 × 0,12; Strom 30 ct.
LW = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "jaz": 3.5,
      "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12.0}
LL = {"wp_art": "luft_luft", "effizienz_modus": "gesamt_jaz", "jaz": 3.5}

SPROSSEN: dict[str, tuple[dict, dict | None, dict | None]] = {
    # Sprosse: (parameter, monatsdaten, provenance)
    "F1_nur_leistung": (LW, None, None),
    "F2_gesamtstrom": (LW, {"stromverbrauch_kwh": 1000.0}, None),
    "F2b_gesamtstrom_plus_schaetzung": (
        LW, {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 3500.0},
        {"verbrauch_daten.heizenergie_kwh": ABGELEITET}),
    "F3_modus_split_abgeleitet": (
        LL, {"stromverbrauch_kwh": 1000.0, "modus_abdeckung_h": 700.0,
             "modus_strom_heizen_kwh": 600.0, "modus_strom_kuehlen_kwh": 250.0}, None),
    "F4_betriebsart_zaehler": (
        LL, {"stromverbrauch_kwh": 1000.0, "betriebsart_strom_heizen_kwh": 700.0,
             "betriebsart_strom_kuehlen_kwh": 250.0}, None),
    "F5_getrennte_stroeme": (
        {**LW, "getrennte_strommessung": True},
        {"strom_heizen_kwh": 750.0, "strom_warmwasser_kwh": 250.0}, None),
    "F6_wmz_gesamt": (LW, {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 3500.0}, None),
    "F7_wmz_je_funktion": (
        {**LW, "getrennte_strommessung": True},
        {"strom_heizen_kwh": 750.0, "strom_warmwasser_kwh": 250.0,
         "heizenergie_kwh": 3000.0, "warmwasser_kwh": 600.0}, None),
    "F8_kaeltemenge": (
        LW, {"stromverbrauch_kwh": 1300.0, "heizenergie_kwh": 3000.0,
             "betriebsart_strom_heizen_kwh": 1000.0, "betriebsart_strom_kuehlen_kwh": 300.0,
             "betriebsart_nutzenergie_kuehlen_kwh": 900.0}, None),
    "F10_heizstab_in_wp": (LW, {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 1800.0}, None),
    "F11_fremdstrom": (
        {**LW, "abgrenzung": "fremdstrom"},
        {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 3500.0}, None),
    "F12_bivalent": (
        {**LW, "abgrenzung": "fremdwaerme"},
        {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 3500.0}, None),
}

#: Hub-Schlüssel → Cockpit-Attribut. Dieselbe Größe, zwei Sichten, EIN Wert (S1).
#: `None` im Hub heißt „Schlüssel fehlt" und muss im Cockpit `None` sein.
SYMMETRIE = {
    "gesamt_stromverbrauch_kwh": "wp_strom_kwh",
    "durchschnitt_cop": "wp_jaz",
    "durchschnitt_cop_grund": "wp_jaz_grund",
    "durchschnitt_cop_hinweis": "wp_jaz_hinweis",
    "waerme_abgeleitet": "wp_waerme_abgeleitet",
    "gesamt_strom_heizen_kwh": "wp_strom_heizen_kwh",
    "gesamt_strom_warmwasser_kwh": "wp_strom_warmwasser_kwh",
    "jaz_heizen": "wp_jaz_heizen",
    "jaz_warmwasser": "wp_jaz_warmwasser",
    "jaz_kuehlen": "wp_jaz_kuehlen",
    "modus_strom_heizen_kwh": "wp_modus_strom_heizen_kwh",
    "modus_strom_kuehlen_kwh": "wp_modus_strom_kuehlen_kwh",
    "modus_strom_warmwasser_kwh": "wp_modus_strom_warmwasser_kwh",
    "modus_strom_lueften_kwh": "wp_modus_strom_lueften_kwh",
    "modus_strom_entfeuchten_kwh": "wp_modus_strom_entfeuchten_kwh",
    "modus_nicht_aufgeteilt_kwh": "wp_modus_nicht_aufgeteilt_kwh",
    "modus_abdeckung_h": "wp_modus_abdeckung_h",
    "modus_strom_bezug_kwh": "wp_modus_strom_bezug_kwh",
    "modus_gemessen": "wp_modus_gemessen",
}


def _wert(x):
    return round(x, 1) if isinstance(x, float) else x


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse", list(SPROSSEN))
async def test_hub_und_cockpit_nennen_dieselbe_zahl_und_denselben_grund(db, sprosse):
    """S1/P10/P12 über alle Sprossen — Mengen, Kennzahlen UND Gründe."""
    parameter, daten, prov = SPROSSEN[sprosse]
    a = await _anlage(db, sprosse)
    await _geraet(db, a, parameter, daten, prov)
    await db.commit()

    z = await _hub(db, a.id)
    m = await _monat(db, a.id)
    abweichungen = []
    for hub_key, cockpit_attr in SYMMETRIE.items():
        h = z.get(hub_key)
        c = getattr(m, cockpit_attr)
        # Der Hub liefert für „keine Monatsdaten" 0, das Cockpit None; und eine
        # gemessene Menge 0.0 ist im Cockpit `None`, wo das Gerät die Größe nicht
        # hat. Verglichen wird, wo eine der Sichten etwas behauptet.
        if h in (None, 0, 0.0) and c in (None, 0, 0.0):
            continue
        if _wert(h) != _wert(c):
            abweichungen.append(f"{hub_key}: Hub {h!r} ≠ Cockpit {c!r}")
    assert not abweichungen, (
        f"[{sprosse}] Dieselbe Anlage, zwei Aussagen (W-15-Klasse):\n  " + "\n  ".join(abweichungen)
    )
    # Wärme: Hub summiert, Cockpit nennt Heizung/Warmwasser getrennt.
    waerme_c = (m.wp_heizung_kwh or 0) + (m.wp_warmwasser_kwh or 0)
    assert _wert(z["gesamt_waerme_kwh"]) == _wert(waerme_c), f"[{sprosse}] Wärme Hub ≠ Cockpit"


@pytest.mark.asyncio
async def test_h1_ersparnis_rechnet_mit_dem_getrennt_gemessenen_strom(db):
    """F7: 3.600 kWh Wärme, 1.000 kWh Strom in zwei Zählern.

    Alt-Kosten 3600 / 0,9 × 0,12 = 480 €, WP-Kosten 1000 × 0,30 = 300 € ⇒ 180 €.
    Vor B3: WP-Kosten 0 € (Rohspalte leer), Ersparnis 480 €.
    """
    a = await _anlage(db, "H-1 F7")
    await _geraet(db, a, *SPROSSEN["F7_wmz_je_funktion"])
    await db.commit()
    z = await _hub(db, a.id)
    assert z["wp_kosten_euro"] == pytest.approx(300.0), (
        "WP-Kosten müssen aus `get_wp_strom_kwh` kommen — die Rohspalte "
        f"`stromverbrauch_kwh` ist bei getrennter Messung leer. Gefunden: {z['wp_kosten_euro']}"
    )
    assert z["alte_heizung_kosten_euro"] == pytest.approx(480.0)
    assert z["ersparnis_euro"] == pytest.approx(180.0), (
        f"Ersparnis = 480 − 300; vor B3 stand hier 480 (Kosten 0). Gefunden: {z['ersparnis_euro']}"
    )


@pytest.mark.asyncio
async def test_h1_ohne_waerme_bleiben_die_stromkosten_eine_zahl(db):
    """F5: getrennte Ströme, keine Wärme — Kosten 300 €, kein Vergleich (F-42)."""
    a = await _anlage(db, "H-1 F5")
    await _geraet(db, a, *SPROSSEN["F5_getrennte_stroeme"])
    await db.commit()
    z = await _hub(db, a.id)
    assert z["wp_kosten_euro"] == pytest.approx(300.0)
    assert z["ersparnis_euro"] is None and z["alte_heizung_kosten_euro"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse, erwartet", [
    ("F5_getrennte_stroeme", 1000.0),
    ("F7_wmz_je_funktion", 1000.0),
    ("F8_kaeltemenge", 1300.0),
    ("F2_gesamtstrom", 1000.0),
])
async def test_h1b_die_monats_zeitreihe_traegt_den_strom_nach_dem_sot(db, sprosse, erwartet):
    """`jaz_je_monat[].strom_kwh` — die eine Quelle für Tabelle und Vergleich im Client."""
    a = await _anlage(db, f"H-1b {sprosse}")
    await _geraet(db, a, *SPROSSEN[sprosse])
    await db.commit()
    z = await _hub(db, a.id)
    zeile = z["jaz_je_monat"][0]
    assert zeile["jahr"] == JAHR and zeile["monat"] == MONAT
    assert zeile["strom_kwh"] == pytest.approx(erwartet), zeile


@pytest.mark.asyncio
async def test_h2_abgeleitete_waerme_traegt_herkunft_und_vorbehalt(db):
    """F2b: der häufigste Fall — Gesamtstrom plus angenommener Vorschlag."""
    a = await _anlage(db, "H-2 F2b")
    await _geraet(db, a, *SPROSSEN["F2b_gesamtstrom_plus_schaetzung"])
    await db.commit()
    z = await _hub(db, a.id)
    assert z["waerme_abgeleitet"] is True
    assert z["waerme_herkunft"] == "geschätzt: Strom × JAZ 3,5", z["waerme_herkunft"]
    assert z["ersparnis_vorbehalt"] == VORBEHALT_ABGELEITET
    # Die Zahlen bleiben — es ist eine zulässige Schätzung (§6), keine Sperre.
    assert z["ersparnis_euro"] is not None and z["co2_ersparnis_kg"] is not None


@pytest.mark.asyncio
async def test_h2_gemessene_waerme_ohne_vorbehalt(db):
    a = await _anlage(db, "H-2 F6")
    await _geraet(db, a, *SPROSSEN["F6_wmz_gesamt"])
    await db.commit()
    z = await _hub(db, a.id)
    assert z["waerme_herkunft"] == HERKUNFT_GEMESSEN
    assert z["ersparnis_vorbehalt"] is None


@pytest.mark.asyncio
async def test_f12_bivalent_sperrt_die_kennzahl_und_behaelt_die_ersparnis_mit_vorbehalt(db):
    """F12 (Entscheid Gernot 05.09.): Zahl bleibt, Vorbehalt dazu — kein Total-Fall."""
    a = await _anlage(db, "F12")
    await _geraet(db, a, *SPROSSEN["F12_bivalent"])
    await db.commit()
    z = await _hub(db, a.id)
    assert z["durchschnitt_cop"] is None and z["durchschnitt_cop_grund"] == GRUND_FREMDWAERME
    assert z["ersparnis_euro"] == pytest.approx(466.67 - 300.0, abs=0.01)
    assert z["ersparnis_vorbehalt"] == VORBEHALT_FREMDWAERME


def test_layer_vorbehalt_kennt_beide_faelle_und_ihre_kombination():
    assert ersparnis_vorbehalt(waerme_abgeleitet=False, abgrenzung=None) is None
    assert ersparnis_vorbehalt(waerme_abgeleitet=False, abgrenzung="fremdstrom") is None, (
        "Fremdstrom macht E zu groß — die Ersparnis ist dann zu KLEIN und ehrlich (F11)"
    )
    assert ersparnis_vorbehalt(waerme_abgeleitet=True, abgrenzung=None) == VORBEHALT_ABGELEITET
    assert ersparnis_vorbehalt(waerme_abgeleitet=False, abgrenzung="fremdwaerme") == VORBEHALT_FREMDWAERME
    beide = ersparnis_vorbehalt(waerme_abgeleitet=True, abgrenzung="fremdwaerme")
    assert VORBEHALT_ABGELEITET in beide and VORBEHALT_FREMDWAERME in beide


def test_layer_herkunft_nennt_den_faktor_deutsch():
    assert waerme_herkunft(False, None) == HERKUNFT_GEMESSEN
    assert waerme_herkunft(True, 3.5) == "geschätzt: Strom × JAZ 3,5"
    assert waerme_herkunft(True, None) == "geschätzt: Strom × gepflegte JAZ"


def test_n114_die_bkw_route_bietet_keinen_verguetungssatz_mehr_an():
    """N-114: ein Query-Parameter, den die Route nie las (BKW-Einspeisung ist unvergütet)."""
    from backend.api.routes.investitionen.dashboards import get_balkonkraftwerk_dashboard
    params = inspect.signature(get_balkonkraftwerk_dashboard).parameters
    assert "einspeiseverguetung_cent" not in params, list(params)
