"""ROI-Dashboard: Eine Split-Klimaanlage bekommt keine erfundene Heizungs-Ersparnis (N-87).

Befund: `get_roi_dashboard` behandelte **jede** `waermepumpe` als Ersatz einer
Gasheizung. Fehlte der Wärmebedarf, füllten ihn zwei Default-Schichten auf
(`PARAM_WAERMEPUMPE_DEFAULTS` in `investitionen/crud.py`, ein zweites Mal in
`calculations.berechne_waermepumpe_einsparung`): 12.000 kWh Heizwärme +
3.000 kWh Warmwasser. Daraus wurden rund **1.100 €/Jahr** und **2.210 kg CO₂**
Ersparnis gegen eine Gasheizung, die es bei einer Klimaanlage nie gab — und die
Beträge liefen zusätzlich in die Anlagen-Summen (`gesamt_jahres_einsparung`,
`gesamt_roi_prozent`, `gesamt_amortisation_jahre`, `gesamt_co2_einsparung_kg`).

Alle GEMESSENEN Pfade liefern für dasselbe Gerät 0 — `wp_wirtschaftlichkeit`,
`co2_wp_ersparnis_kg`, `aussichten`, JAZ/COP im Cockpit haben denselben
`wp_waerme_kwh <= 0`-Wächter. Diese Route war die einzige, die konstruiert hat.

Der wichtigste Test hier ist `…_obwohl_parameter_gepflegt_sind`: das
Investitionsformular hat die Defaults **vorbelegt und mitgespeichert**, deshalb
tragen Bestands-Klimaanlagen die 12.000/3.000 real in `parameter`. Ein Fix, der
nur auf „kein Wert gepflegt" prüft, würde diesen Bestand nicht heilen.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition


# Die Vorbelegung, die das Formular bis v4.0.6 mitgespeichert hat.
GEPFLEGTE_PHANTOM_PARAMS = {
    "heizwaermebedarf_kwh": 12000,
    "warmwasserbedarf_kwh": 3000,
    "jaz": 3.5,
    "effizienz_modus": "gesamt_jaz",
    "alter_energietraeger": "gas",
    "alter_preis_cent_kwh": 12,
    "pv_anteil_prozent": 30,
}


async def _seed_wp(db, *, wp_art: str | None, parameter: dict | None = None) -> int:
    """Anlage mit genau einer Wärmepumpe des gegebenen Subtyps."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    params = dict(parameter if parameter is not None else GEPFLEGTE_PHANTOM_PARAMS)
    if wp_art is not None:
        params["wp_art"] = wp_art
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Test-WP",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=8000.0,
        parameter=params,
    ))
    await db.flush()
    return anlage.id


def _wp_zeile(result):
    return next(b for b in result.berechnungen if b.investition_typ == "waermepumpe")


async def _roi(db, anlage_id):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )


# ============================================================================
# Der Fehler selbst
# ============================================================================


async def test_klimaanlage_bekommt_keine_ersparnis_obwohl_parameter_gepflegt_sind(db):
    """Der Bestandsfall: die Phantomwerte stehen in `parameter` — trotzdem 0.

    Genau hier hätte ein Fix der Bauart „nur nichts erfinden, wenn nichts
    gepflegt ist" versagt.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    result = await _roi(db, anlage_id)

    zeile = _wp_zeile(result)
    assert zeile.jahres_einsparung == 0
    assert zeile.co2_einsparung_kg is None
    assert zeile.roi_prozent is None
    assert zeile.amortisation_jahre is None


async def test_klimaanlage_sagt_warum_statt_still_null_zu_liefern(db):
    """`nicht_bewertet` unterscheidet den FEHLENDEN Wert von einer Null-Ersparnis."""
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung["nicht_bewertet"] is True
    hinweis = zeile.detail_berechnung["hinweis"]
    assert "Klimaanlage" in hinweis
    # Der Text nennt die Bedingung, unter der es doch ginge — und verspricht nichts.
    assert "Heizung" in hinweis


async def test_klimaanlage_bleibt_als_zeile_sichtbar(db):
    """Nicht bewertet heißt nicht unsichtbar: Kosten zählen weiter (wie beim WR)."""
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    result = await _roi(db, anlage_id)

    zeile = _wp_zeile(result)
    assert zeile.anschaffungskosten == pytest.approx(8000.0)
    assert result.gesamt_investition == pytest.approx(8000.0)


async def test_anlagen_summen_tragen_den_phantomwert_nicht_mehr(db):
    """Die Kopfzahlen der ROI-Sicht waren mitbetroffen, nicht nur die Zeile."""
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    result = await _roi(db, anlage_id)

    assert result.gesamt_jahres_einsparung == 0
    assert result.gesamt_co2_einsparung_kg == 0
    # Ohne Ersparnis gibt es keinen Break-Even — und keine erfundene Kurve.
    assert result.gesamt_roi_prozent is None
    assert result.gesamt_amortisation_jahre is None
    assert result.gesamt_amortisation_jahr is None


# ============================================================================
# Regressionsschutz: klassische Wärmepumpen dürfen sich NICHT bewegen
# ============================================================================


async def test_klassische_waermepumpe_rechnet_unveraendert(db):
    """Luft-Wasser-WP: die bisherigen Zahlen bleiben exakt stehen.

    Die Werte sind die des Default-Satzes (15.000 kWh / JAZ 3,5 / 30 % PV /
    Gas 12 ct) — sie belegen, dass der Klima-Zweig die klassische WP nicht
    streift.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_wasser")
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.jahres_einsparung > 0
    assert zeile.co2_einsparung_kg == pytest.approx(2210.0)
    assert zeile.detail_berechnung.get("nicht_bewertet") is not True


async def test_waermepumpe_ohne_wp_art_gilt_als_klassisch(db):
    """Legacy-Bestand ohne `wp_art` darf die Wärme-Erwartung nicht verlieren.

    Gleiche Festlegung wie im SoT-Helper `ist_luft_luft_waermepumpe`: eine
    fehlende Angabe schaltet die Bewertung NICHT stillschweigend ab.
    """
    anlage_id = await _seed_wp(db, wp_art=None)
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.jahres_einsparung > 0
    assert zeile.detail_berechnung.get("nicht_bewertet") is not True


async def test_klimaanlage_ohne_gepflegte_parameter_erfindet_auch_nichts(db):
    """Der zweite Weg in denselben Fehler: leeres `parameter`-Dict.

    Ohne den Fix griffen hier die Defaults in `crud.py` UND die zweite
    Default-Schicht in `berechne_waermepumpe_einsparung`.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_luft", parameter={})
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.jahres_einsparung == 0
    assert zeile.co2_einsparung_kg is None
    assert zeile.detail_berechnung["nicht_bewertet"] is True
