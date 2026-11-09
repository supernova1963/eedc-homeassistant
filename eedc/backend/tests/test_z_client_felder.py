"""Päckchen Z-Client (9.11.2026): Anzeige-Zahlen, die bis dahin der Client rechnete, kommen als Felder aus dem Backend.

Je Feld: (a) die Layer-Funktion trifft die alte Client-Formel **bitgleich** (dieselbe Gleitkomma-Reihenfolge, dieselben
``null``-Regeln) und (b) das Antwortmodell trägt sie als ``computed_field`` aus seinen eigenen Feldern — damit sehen Monat,
Jahr-Kopf (nach der Faltung) und Jahr-Monate dieselbe Zahl wie die Felder daneben. Die Gleichheit auf den Demo-Kopien
(r28, r27, pruef-4018: 0 Abweichungen) steht im Bericht ``opus-berichte/PAECKCHEN-Z-CLIENT-2026-11-09.md``.
"""
from __future__ import annotations

import random

import pytest

from backend.api.routes.aktueller_monat.schemas import SonstigesGeraet
from backend.api.routes.energie_profil._shared import TagDetailResponse, TagesPrognoseResponse
from backend.core.berechnungen.bkw_finanz import bkw_eigenverbrauch_quote_prozent, bkw_einspeisung_kwh
from backend.core.berechnungen.kennzahlen import netto_kwh, spezifischer_ertrag_kwh_kwp
from backend.core.berechnungen.pv_anteil_ladung import bezug_pv_anteil_prozent, pv_anteil_prozent
from backend.core.berechnungen.speicher_wirtschaftlichkeit import netzladung_kosten_euro


# Die alten Client-Formeln, wörtlich (JS-Semantik: `x ?? 0`, `a && b`, `(a / b) * 100`).
def _client_bkw_einsp(erz, ev):
    return erz - ev if erz is not None and ev is not None else None


def _client_bkw_quote(erz, ev):
    return (ev / erz) * 100 if erz and ev is not None else None


def _client_sonstiges(pv, netz):
    ges = (pv if pv is not None else 0) + (netz if netz is not None else 0)
    return ((pv if pv is not None else 0) / ges) * 100 if ges > 0 else None


def _client_netzladung(kwh, preis):
    return (kwh * preis) / 100 if preis is not None else None


def _zahl(rng):
    return rng.choice([None, 0, 0.0, round(rng.uniform(0, 500), rng.choice([1, 2, 3])), rng.uniform(0, 50)])


@pytest.mark.parametrize("saat", range(5))
def test_layer_bitgleich_zur_alten_client_formel(saat):
    rng = random.Random(saat)
    for _ in range(4000):
        a, b = _zahl(rng), _zahl(rng)
        assert bkw_einspeisung_kwh(a, b) == _client_bkw_einsp(a, b)
        assert bkw_eigenverbrauch_quote_prozent(a, b) == _client_bkw_quote(a, b)
        assert bezug_pv_anteil_prozent(a, b) == _client_sonstiges(a, b)
        if a is not None:
            assert netzladung_kosten_euro(a, b) == _client_netzladung(a, b)
        assert netto_kwh(a, b) == (a - b if a is not None and b is not None else None)
        # Wallbox-PV-Anteil der Werte-Tabelle: ungerundet (stellen=None) — die Tabelle rundet und mittelt selbst.
        erwartet = (a / b) * 100 if a is not None and b is not None and b > 0 else None
        assert pv_anteil_prozent(a, b) == erwartet
        # Spezifischer Ertrag: `kwp > 0 ? ist / kwp : …` (PV-Strings Laufzeit, Aussicht).
        assert spezifischer_ertrag_kwh_kwp(a if a is not None else 0.0, b) == (
            (a if a is not None else 0.0) / b if b else None)


def test_netzladung_ohne_preis_bleibt_strich_auch_bei_0_kwh():
    # Anders als die Monats-Kette `berechne_netzladung_kosten` (0 kWh ⇒ 0 €): die Tageskachel zeigt «—» ohne Preis.
    assert netzladung_kosten_euro(0.0, None) is None
    assert netzladung_kosten_euro(0.0, 22.5) == 0.0
    assert netzladung_kosten_euro(None, 22.5) is None


def test_tagdetail_traegt_die_kosten_aus_seinen_feldern():
    d = TagDetailResponse(datum="2026-07-25", speicher_ladung_netz_kwh=2.5, speicher_effektiver_ladepreis_cent=22.5)
    assert d.model_dump()["speicher_ladung_netz_kosten_euro"] == 2.5 * 22.5 / 100
    assert TagDetailResponse(datum="2026-07-25").model_dump()["speicher_ladung_netz_kosten_euro"] is None


def test_tagesprognose_netto_aus_den_gerundeten_summen():
    p = TagesPrognoseResponse(datum="2026-07-27", stunden=[], pv_summe_kwh=9.0, verbrauch_summe_kwh=1.2,
                              pv_quelle="eedc", hinweise=[])
    assert p.model_dump()["netto_summe_kwh"] == 9.0 - 1.2
    ohne = TagesPrognoseResponse(datum="2026-07-27", stunden=[], pv_summe_kwh=9.0, pv_quelle="eedc", hinweise=[])
    assert ohne.model_dump()["netto_summe_kwh"] is None


def test_sonstiges_geraet_pv_anteil_aus_der_zeile():
    g = SonstigesGeraet(bezeichnung="Pool", kategorie="verbraucher", bezug_pv_kwh=10.0, bezug_netz_kwh=30.0)
    assert g.model_dump()["pv_anteil_prozent"] == 25.0
    assert SonstigesGeraet(bezeichnung="PV2", kategorie="erzeuger", erzeugung_kwh=5.0).pv_anteil_prozent is None
