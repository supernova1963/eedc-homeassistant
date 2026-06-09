"""Tests #150 Slice B — eedc-Börsenpreis-Rang-Export nach HA.

Rang je Tag-/Nacht-Fenster (1–5 günstigste, 99 Rest) + günstige-Stunden-Anzahl.
Reine Rang-Logik + solar-basiertes Fenster isoliert, Verdrahtung mit gemockten
Preis-/Wetter-Quellen.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.preis_rang import (
    GUENSTIG_TOP_N,
    RANG_TEUER,
    berechne_preis_rang,
)
from backend.services.solar_forecast_service import sonnenauf_unter_stunde
from backend.models import Anlage, Investition, Monatsdaten


# ── Rang-Logik (rein) ───────────────────────────────────────────────────────

def test_rang_billigste_ist_eins_rest_99():
    preise = {h: float(p) for h, p in enumerate([30, 10, 20, 5, 40, 50, 15, 25])}
    erg = berechne_preis_rang(preise, tag_stunden=set(range(8)), nacht_stunden=set(), aktuelle_stunde=3)
    assert erg.rang_profil[3] == 1          # 5 ct = billigste
    assert erg.rang_profil[1] == 2          # 10 ct
    assert erg.rang_profil[6] == 3          # 15 ct
    assert sorted(r for r in erg.rang_profil.values() if r <= GUENSTIG_TOP_N) == [1, 2, 3, 4, 5]
    assert erg.rang_profil[5] == RANG_TEUER  # 50 ct = teuerste → 99
    assert erg.rang_aktuell == 1
    assert erg.guenstige_stunden_anzahl == 5


def test_rang_tag_und_nacht_getrennt():
    preise = {h: (5.0 if h < 6 else 30.0) for h in range(24)}
    tag = set(range(6, 21))
    nacht = set(range(24)) - tag
    erg = berechne_preis_rang(preise, tag_stunden=tag, nacht_stunden=nacht, aktuelle_stunde=10)
    # Im Tag-Fenster werden 5 Stunden trotz hoher Absolutpreise zu 1..5.
    tag_raenge = sorted(erg.rang_profil[h] for h in tag)
    assert tag_raenge[:5] == [1, 2, 3, 4, 5]
    assert erg.guenstige_stunden_anzahl == 10   # je Fenster 5 günstige


def test_rang_kleines_fenster_alle_guenstig():
    preise = {0: 8.0, 1: 9.0, 2: 7.0}
    erg = berechne_preis_rang(preise, tag_stunden=set(), nacht_stunden={0, 1, 2}, aktuelle_stunde=2)
    assert erg.rang_profil == {2: 1, 0: 2, 1: 3}
    assert erg.rang_aktuell == 1
    assert erg.guenstige_stunden_anzahl == 3


def test_rang_aktuelle_stunde_ohne_preis_ist_none():
    erg = berechne_preis_rang({0: 5.0}, tag_stunden={0}, nacht_stunden=set(), aktuelle_stunde=14)
    assert erg.rang_aktuell is None


# ── Solar-basiertes Tag/Nacht-Fenster ───────────────────────────────────────

def test_sonnenfenster_sommer_laenger_als_winter():
    sa_s, su_s = sonnenauf_unter_stunde("2026-06-21", 48.8, 9.2)
    sa_w, su_w = sonnenauf_unter_stunde("2026-12-21", 48.8, 9.2)
    assert (su_s - sa_s) > (su_w - sa_w)
    assert (su_s - sa_s) > 14            # Sommer > 14 h Tageslicht
    assert (su_w - sa_w) < 10            # Winter < 10 h Tageslicht
    assert 0 <= sa_s <= 12 <= su_s <= 24


# ── Verdrahtung: calculate_anlage_sensors mit gemockten Quellen ─────────────

@pytest.fixture
def _patch_preis(monkeypatch):
    import backend.services.strompreis_markt_service as smp

    async def fake_marktpreise(datum, markt="DE", timeout=15.0):
        # billigste Stunden früh (2 ct), teuer am Abend
        return {h: 2.0 + (h % 6) * 3.0 for h in range(24)}

    monkeypatch.setattr(smp, "fetch_marktpreise", fake_marktpreise)


async def _seed_anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="Preis-Test", leistung_kwp=10.0,
                    latitude=48.8, longitude=9.2, standort_land="DE")
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    await db.flush()
    return anlage


async def test_preis_sensoren_erscheinen(db, _patch_preis):
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    assert "eedc_preis_rang" in by_key
    assert by_key["eedc_preis_guenstige_stunden_anzahl"].value >= 1
    # Rang-Profil reist als Attribut mit.
    profil = by_key["eedc_preis_rang"].zusatz_attribute["rang_profil"]
    assert profil and all("stunde" in e and "rang" in e for e in profil)
