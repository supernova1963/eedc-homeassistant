"""HA-Bauform E4b Teil B: Wandlungsverluste werden geführt und angezeigt; seit N-588 (10.10.2026) bewertet unter dem
Messpunkt-Vertrag — die Bilanz trägt sie weiter (F2), Ersparnis und CO₂ rechnen ohne sie (F1).

Wandlungsverluste = ``max(0, Σ String-Zähler − Anlagenzähler)`` eines Zeitraums (W2-R3, ``pv_verteilung``). Der Weg:
Kanal-Leser (``bilanz_leser.als_monatssumme``) → Monats-Fakten (``ErzeugungFakten.wandlungsverluste_kwh`` samt Bezug,
auch für abgeschlossene Monate, Entscheid B-1) → Cockpit → Monat, Cockpit → Jahr (Σ der Monate), Übersicht
(Gesamtzeitraum für den PV-Hub) und die Monatsreihe ``/monatsdaten/aggregiert``. Prozent = Verluste ÷ Σ Strings × 100
aus dem Layer (``wandlungsverluste_prozent``) — der Client rechnet nichts.

**Bewertung (N-588):** PV und Eigenverbrauch bleiben die Σ der Strings (Bilanz, F2); Ersparnis und CO₂ rechnen mit
dem Eigenverbrauch ohne die Verluste — die Probe ``test_bilanz_traegt_die_verluste_*`` hält das an F13a fest (Strings
630, Anlagenzähler 594, Verluste 36 ⇒ 414 kWh, 124,20 €, 157,32 kg). Bis 10.10.2026 stand hier die Gegenprobe „keine
Bewertung" (Entscheid B2 vom 05.10.); ihr Docstring verlangte, sie beim Bewerten bewusst umzustellen — das ist sie.

Schwesterdateien: ``test_bilanz_zeitraum.py`` (die Regel W2-R3 als reine Funktion), ``test_pv_achse_matrix.py``
(Messung ``fakten:wandlungsverluste`` für F13a/F13b/W2-V), ``test_kanal_bilanz_gleichheit.py`` (Datenstände).
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.ergebnis import falte_zeitraum
from backend.core.berechnungen.pv_verteilung import wandlungsverluste_prozent
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

JUNI, JULI = (2026, 6), (2026, 7)


# ── Layer ───────────────────────────────────────────────────────────────────


def test_prozent_ist_verluste_durch_summe_der_strings():
    assert wandlungsverluste_prozent(36.0, 630.0) == pytest.approx(5.714285714)
    assert wandlungsverluste_prozent(0.0, 630.0) == 0.0


@pytest.mark.parametrize("v, b", [(None, 630.0), (36.0, None), (36.0, 0.0), (None, None)])
def test_prozent_ohne_wert_oder_ohne_bezug_ist_none(v, b):
    assert wandlungsverluste_prozent(v, b) is None


def test_jahr_summiert_die_monate_und_rechnet_den_prozentsatz_ueber_dieselben_monate():
    monate = [
        {"monat": 5, "wandlungsverluste_kwh": 36.0, "wandlungsverluste_bezug_kwh": 630.0},
        {"monat": 6, "wandlungsverluste_kwh": 10.0, "wandlungsverluste_bezug_kwh": 200.0},
        {"monat": 7, "wandlungsverluste_kwh": None, "wandlungsverluste_bezug_kwh": None},
    ]
    j = falte_zeitraum(monate, 2026)
    assert j["wandlungsverluste_kwh"] == pytest.approx(46.0)
    assert j["wandlungsverluste_bezug_kwh"] == pytest.approx(830.0)
    assert j["wandlungsverluste_prozent"] == pytest.approx(46.0 / 830.0 * 100)


def test_jahr_ohne_einen_monat_mit_wert_ist_none():
    j = falte_zeitraum([{"monat": 5}, {"monat": 6, "wandlungsverluste_kwh": None}], 2026)
    assert j["wandlungsverluste_kwh"] is None and j["wandlungsverluste_prozent"] is None


# ── Fakten, Cockpit → Monat, Übersicht, Monatsreihe (HA-Datenstand der PV-Matrix) ───────────────────────


async def _fakt(db, aid, monat, *, tageswerte=False):
    from backend.services.monats_fakten import lade_monats_fakten

    fk = await lade_monats_fakten(db, aid, von=monat, bis=monat, inkl_nur_tageswerte=tageswerte)
    return fk[0] if fk else None


async def _monat(db, aid, monat):
    import backend.api.routes.aktueller_monat as am

    return await am.get_aktueller_monat(anlage_id=aid, jahr=monat[0], monat=monat[1], db=db)


async def test_f13a_fakten_monat_und_uebersicht_nennen_36_kwh():
    """F13a: Süd 12 · West 6 · BKW 3 je Tag gemessen, Anlagenzähler 19,8 ⇒ Juni 630 − 594 = 36,0 kWh (5,71 %).
    Vor dem Abschluss aus dem Tageswert-Rückfall, danach (Aus HA laden) aus den Fakten des gespeicherten Monats
    (B-1: der Kanal-Monat wird auch dann gelesen); der laufende Juli (drei Tage, keine Zeile) direkt aus dem Kanal."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    async with kg.datenstand("pv", "F13a", "HA") as ds:
        with mx._umgebung(ds.svc):
            vor = await _fakt(ds.db, ds.aid, JUNI, tageswerte=True)
            await mx.schreibe_s1_aus_ha_laden(ds.db, ds.aid)
            nach = await _fakt(ds.db, ds.aid, JUNI)
            monat = await _monat(ds.db, ds.aid, JUNI)
            juli = await _monat(ds.db, ds.aid, JULI)
            uebersicht = await get_cockpit_uebersicht(anlage_id=ds.aid, jahr=None, db=ds.db)
            reihe = await list_monatsdaten_aggregiert(anlage_id=ds.aid, jahr=2026, db=ds.db)
    for f in (vor, nach):
        assert f.erzeugung.wandlungsverluste_kwh == pytest.approx(36.0)
        assert f.erzeugung.wandlungsverluste_bezug_kwh == pytest.approx(630.0)
    assert monat.wandlungsverluste_kwh == pytest.approx(36.0)
    assert monat.wandlungsverluste_prozent == pytest.approx(36.0 / 630.0 * 100)
    assert juli.wandlungsverluste_kwh == pytest.approx(3 * 1.2)
    assert juli.wandlungsverluste_prozent == pytest.approx(3.6 / 63.0 * 100)
    # Die Übersicht (Gesamtzeitraum, PV-Hub) kennt die Monate mit Fakt — hier der gespeicherte Juni.
    assert uebersicht.wandlungsverluste_kwh == pytest.approx(36.0)
    assert uebersicht.wandlungsverluste_prozent == pytest.approx(36.0 / 630.0 * 100)
    juni_zeile = next(z for z in reihe if z.monat == 6)
    assert juni_zeile.wandlungsverluste_kwh == pytest.approx(36.0)
    assert juni_zeile.wandlungsverluste_prozent == pytest.approx(36.0 / 630.0 * 100)


async def test_ohne_anlagenzaehler_gibt_es_keinen_wert():
    """F06: alle Einzelzähler, KEIN Anlagenzähler ⇒ ``None`` überall (die Anzeige zeigt keine Zeile)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with kg.datenstand("pv", "F06", "HA") as ds:
        with mx._umgebung(ds.svc):
            await mx.schreibe_s1_aus_ha_laden(ds.db, ds.aid)
            nach = await _fakt(ds.db, ds.aid, JUNI)
            monat = await _monat(ds.db, ds.aid, JUNI)
            uebersicht = await get_cockpit_uebersicht(anlage_id=ds.aid, jahr=None, db=ds.db)
    assert nach.erzeugung.wandlungsverluste_kwh is None
    assert monat.wandlungsverluste_kwh is None and monat.wandlungsverluste_prozent is None
    assert uebersicht.wandlungsverluste_kwh is None and uebersicht.wandlungsverluste_prozent is None


async def test_strings_unter_dem_anlagenzaehler_sind_null_nicht_negativ():
    """F13b: Σ Strings 630 < Anlagenzähler 666 ⇒ 0 (die Untergrenze des Lesers), nie −36."""
    async with kg.datenstand("pv", "F13b", "HA") as ds:
        with mx._umgebung(ds.svc):
            monat = await _monat(ds.db, ds.aid, JUNI)
    assert monat.wandlungsverluste_kwh == 0.0


async def test_ohne_kanal_deckung_liefert_der_bestandspfad_keinen_wert():
    """Standalone ohne Kanäle (Snapshot-Pfad der Matrix, F13a): die Mengen kommen aus dem Bestand — keine Verluste."""
    import shutil
    import tempfile

    verz = tempfile.mkdtemp(prefix="e4b-sa-")
    try:
        engine, db = await mx._neue_db(f"{verz}/sa.db")
        try:
            form = mx.MATRIX_FORMEN["F13a"]
            aid, ids = await mx.seed_anlage(db, form)
            await mx.seed_snapshots(db, form, aid, ids)
            with mx._umgebung(mx._ha_aus()):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI)
                f = await _fakt(db, aid, JUNI, tageswerte=True)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)
    assert f is not None and f.erzeugung.pv_kwh > 0
    assert f.erzeugung.wandlungsverluste_kwh is None


# ── Bewertung (N-588, Vorlage Fassung 2): Bilanz trägt die Verluste, Geld und CO₂ nicht ──────────────


async def test_bilanz_traegt_die_verluste_ersparnis_und_co2_rechnen_ohne_sie():
    """F13a Juni nach dem Abschluss: Verluste 36 > 0, PV = Σ Strings 630, Eigenverbrauch = 630 − Einspeisung (Bilanz,
    F2 — unverändert); die Ersparnis = (EV − 36) × 30 ct und das CO₂ der Übersicht auf derselben Menge (F1, DI-2: eine
    Eingabe). Umgestellt am 10.10.2026 aus der Probe „keine Bewertung" (Entscheid B2), wie ihr Docstring verlangte."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with kg.datenstand("pv", "F13a", "HA") as ds:
        with mx._umgebung(ds.svc):
            await mx.schreibe_s1_aus_ha_laden(ds.db, ds.aid)
            monat = await _monat(ds.db, ds.aid, JUNI)
            uebersicht = await get_cockpit_uebersicht(anlage_id=ds.aid, jahr=None, db=ds.db)
    einspeisung = mx.soll_einspeisung(mx.MATRIX_FORMEN["F13a"], 30)
    assert monat.wandlungsverluste_kwh == pytest.approx(36.0)
    assert monat.pv_erzeugung_kwh == pytest.approx(630.0)
    assert monat.eigenverbrauch_kwh == pytest.approx(630.0 - einspeisung)
    assert monat.eigenverbrauch_ohne_verluste_kwh == pytest.approx(630.0 - einspeisung - 36.0)
    assert monat.verluste_grund is None
    assert monat.ev_ersparnis_euro == pytest.approx(round((630.0 - einspeisung - 36.0) * 0.30, 2), abs=0.01)
    assert uebersicht.eigenverbrauch_kwh == pytest.approx(630.0 - einspeisung, abs=0.05)
    # Bis 10.10.2026 die Haltewerte der Matrix (135,00 € / 171 kg); jetzt das Soll der Vorlage: 124,20 € / 157,32 kg.
    assert uebersicht.ev_ersparnis_euro == pytest.approx(124.2, abs=0.01)
    assert uebersicht.co2_pv_kg == pytest.approx(157.32, abs=0.05)
