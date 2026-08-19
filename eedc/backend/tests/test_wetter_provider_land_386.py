"""#386: Bright Sky (DWD) nur dort, wo es auch Daten hat.

Zwei Defekte, zwei unabhängige Mechanismen — die Proben halten sie getrennt,
weil jeder für sich den Melderfall heilt und keiner den anderen ersetzt:

1. **Die Automatik las das gepflegte Land nicht.** Sie entschied allein über
   ``is_in_germany`` — eine Bounding-Box, also ein Rechteck. Salzburg,
   Innsbruck, Linz, Bregenz, Zürich und Basel liegen darin. Wer „Österreich"
   einstellte, bekam trotzdem DWD.
2. **Ein Monat ohne einen einzigen Strahlungstag galt als Ergebnis.**
   ``fetch_brightsky_month`` liefert dann ``{globalstrahlung 0.0,
   tage_mit_daten 0}`` — und ``if data:`` nimmt das an, weil ein nicht-leeres
   dict truthy ist. Der Anwender bekam **0,0 kWh/m²** angeboten, obwohl
   Open-Meteo in der Kette danebenstand.

Gemessen am Melderstandort (Schörfling am Attersee, 47,94112/13,593) gegen die
echten APIs, bevor gebaut wurde: Bright Sky liefert dort die Station
Marktschellenberg (Bayern, 49 km) mit ``solar`` durchgängig ``None``; das AUTO-
Ergebnis war 0,0 statt 206,5 kWh/m².

**Die Gegenrichtung ist Teil der Proben:** ein deutscher Standort mit Station
muss weiter DWD bekommen, und eine Altanlage OHNE gepflegtes Land darf ihre
Quelle nicht verlieren — sonst hätte der Fix die Mehrheit der Installationen
umgestellt, um einer Minderheit zu helfen.
"""

from __future__ import annotations

import pytest

from backend.services.wetter.orchestrator import nutze_brightsky


# (Ort, lat, lon) — alle liegen INNERHALB der Deutschland-Bounding-Box.
# Genau das war der Befund: die Box ist ein Rechteck, keine Grenze.
IN_DER_BOX_ABER_AUSLAND = [
    ("Schörfling am Attersee", 47.94112, 13.593),   # der Melderstandort
    ("Salzburg", 47.81, 13.05),
    ("Innsbruck", 47.27, 11.39),
    ("Linz", 48.31, 14.29),
    ("Bregenz", 47.50, 9.75),
]


@pytest.mark.parametrize("ort,lat,lon", IN_DER_BOX_ABER_AUSLAND)
def test_386_oesterreich_bekommt_kein_brightsky(ort, lat, lon):
    """Gepflegtes Land AT schlägt die Box — auch wo die Koordinaten drin liegen."""
    from backend.services.brightsky_service import is_in_germany

    # Vorbedingung der Probe: ohne sie liefe der Test ins Leere, weil er dann
    # nur bestätigte, was die Box ohnehin schon sagt.
    assert is_in_germany(lat, lon), f"{ort} liegt nicht in der Box — Probe wertlos"

    assert nutze_brightsky(lat, lon, "AT") is False


@pytest.mark.parametrize("land", ["AT", "CH", "IT", "at", " ch "])
def test_386_land_wird_normalisiert(land):
    """Groß/klein und Leerzeichen dürfen die Entscheidung nicht kippen."""
    assert nutze_brightsky(47.38, 8.54, land) is False


def test_386_schweiz_in_der_box_bekommt_kein_brightsky():
    """Zürich und Basel liegen ebenfalls in der Box — #386 trifft nicht nur AT."""
    assert nutze_brightsky(47.38, 8.54, "CH") is False   # Zürich
    assert nutze_brightsky(47.56, 7.59, "CH") is False   # Basel


def test_386_deutschland_behaelt_brightsky():
    """Die Gegenrichtung: der gewollte Fall bleibt unverändert."""
    assert nutze_brightsky(48.14, 11.58, "DE") is True   # München


def test_386_ohne_land_bleibt_es_bei_der_box():
    """``None`` heißt „nicht bekannt", nicht „Ausland".

    Altanlagen ohne gepflegtes Land sind der Normalfall im Bestand. Würde die
    Funktion hier ``False`` liefern, verlöre jede von ihnen die DWD-Quelle —
    ein Fix, der mehr kaputt macht als er heilt.
    """
    assert nutze_brightsky(48.14, 11.58, None) is True     # München, in der Box
    assert nutze_brightsky(48.21, 16.37, None) is False    # Wien, außerhalb


def test_386_ausserhalb_der_box_bleibt_ausserhalb():
    """Wien und Graz lagen schon vorher richtig — das darf nicht kippen."""
    assert nutze_brightsky(48.21, 16.37, "AT") is False   # Wien
    assert nutze_brightsky(47.07, 15.44, "AT") is False   # Graz


@pytest.mark.asyncio
async def test_386_monat_ohne_strahlungstage_faellt_auf_open_meteo(monkeypatch):
    """Der zweite Mechanismus, isoliert: 0 Strahlungstage ⇒ nächster Provider.

    Ohne gepflegtes Land greift die Länderregel NICHT — hier muss allein die
    Abdeckungsprüfung retten. Das ist der Fall des deutschen Randstandorts
    ohne Strahlungsstation in Reichweite.
    """
    from backend.services.wetter import orchestrator

    async def _brightsky_ohne_strahlung(lat, lon, jahr, monat, timeout=60.0):
        # Genau die Form, die die echte API am Melderstandort liefert.
        return {
            "globalstrahlung_kwh_m2": 0.0,
            "sonnenstunden": 0.0,
            "tage_mit_daten": 0,
            "tage_gesamt": 31,
            "durchschnitts_temperatur_c": None,
        }

    async def _open_meteo(lat, lon, jahr, monat):
        return {
            "globalstrahlung_kwh_m2": 206.5,
            "sonnenstunden": 425.0,
            "tage_mit_daten": 31,
            "tage_gesamt": 31,
            "durchschnitts_temperatur_c": 18.0,
        }

    monkeypatch.setattr(
        "backend.services.brightsky_service.fetch_brightsky_month",
        _brightsky_ohne_strahlung,
    )
    monkeypatch.setattr(orchestrator, "fetch_open_meteo_archive", _open_meteo)

    r = await orchestrator.get_wetterdaten_multi(
        latitude=47.94112, longitude=13.593, jahr=2020, monat=7,
        provider="auto", land=None,
    )

    assert r["datenquelle"] == "open-meteo"
    assert r["globalstrahlung_kwh_m2"] == pytest.approx(206.5)
    # Bright Sky wurde versucht — und verworfen, nicht übersprungen.
    assert r["provider_versucht"] == ["brightsky", "open-meteo"]


@pytest.mark.asyncio
async def test_386_brightsky_mit_daten_wird_weiter_genommen(monkeypatch):
    """Gegenrichtung zum Abdeckungs-Check: echte DWD-Daten bleiben erste Wahl."""
    from backend.services.wetter import orchestrator

    async def _brightsky_mit_daten(lat, lon, jahr, monat, timeout=60.0):
        return {
            "globalstrahlung_kwh_m2": 197.0,
            "sonnenstunden": 300.0,
            "tage_mit_daten": 31,
            "tage_gesamt": 31,
            "durchschnitts_temperatur_c": 19.0,
        }

    monkeypatch.setattr(
        "backend.services.brightsky_service.fetch_brightsky_month",
        _brightsky_mit_daten,
    )

    r = await orchestrator.get_wetterdaten_multi(
        latitude=48.14, longitude=11.58, jahr=2020, monat=7,
        provider="auto", land="DE",
    )

    assert r["datenquelle"] == "brightsky"
    assert r["globalstrahlung_kwh_m2"] == pytest.approx(197.0)
    assert r["provider_versucht"] == ["brightsky"]
