"""N-750 (16.10.2026) — Cockpit → Monat liest die Kanal-Gruppen des laufenden Monats auch ohne antwortende HA-Statistik.

Bis dahin hingen die E-Mob-, Sonstiges- und WP-Gruppen (``aktueller_monat/quellen_leser.py``: ``_geraete_aus_kanaelen``,
``_wp_aus_kanaelen``) an ``if not ha_stats`` — antwortete die HA-Statistik beim Öffnen nicht (HA-Neustart, Recorder nicht
bereit), fehlten im laufenden Monat das BHKW im Eigenverbrauch, die Heimladung, die dienstlichen Ladekosten und der
Betriebsart-Strom, während der Jahr-Verlauf daneben denselben Monat richtig nannte (gemessen am HEAD 893af648: M10
Eigenverbrauch 43,2 statt 61,4; M09 dienstliche Ladekosten 0,0 statt 1,8). Seit N-750 hängen sie an der Kanal-Deckung
(ADR-002 P14, wie die Monats-Fakten).

**Die Gegenprobe:** der HA-Datenstand der Achsen-Matrix (Spiegel-Kanäle wie im Produkt, ``messe_ha``), dieselbe Datenbank
einmal mit HA-Dienst, einmal mit ``_ha_aus()`` (HA nicht erreichbar); Soll ist der Jahr-Verlauf desselben Monats bzw. die
Monats-Fakten mit Tageswerten (beide lesen dieselben Kanäle ohne die Bedingung) und — für die Gruppen — Cockpit → Monat mit
HA. Keine neue Matrix-Form; Uhr der Matrix (04.07.2026 00:30, laufender Monat Juli). Werkzeug der Messung:
``~/.claude/plans/ha-bauform-werkzeug/fund-n750-n751/n750_ha_aus.py``.
"""

from __future__ import annotations

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

#: Anzeige-Rundung: der Jahr-Verlauf rundet auf 0,1 kWh/€, Cockpit → Monat nicht.
_TOL = 0.051


async def _quellen(db, aid: int) -> dict:
    import backend.api.routes.aktueller_monat as amr

    r = await amr.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=mx.JULI, db=db)
    return dict(r.quellen)


async def _miss(fid: str, tmp_path) -> tuple[dict, dict]:
    """``(mit_ha, ohne_ha)`` — je ``_sichten_laufend`` derselben Datenbank."""
    form = am.MATRIX_FORMEN[fid]
    engine, db = await mx._neue_db(str(tmp_path / f"{fid}.db"))
    svc = am.seed_ha(form)
    try:
        aid, ids = await am.seed_anlage(db, form)
        with am.umgebung(form, svc):
            await mx.fuelle_spiegel(engine, aid, svc)
            await mx.aggregiere_tage(db, form.pvform, aid, am.TAGE_JUNI + am.TAGE_JULI)
            await mx.baue_abgeleitete_nach_tagen(engine, aid)
            mit = await am._sichten_laufend(db, aid, ids)
        with am.umgebung(form, mx._ha_aus()):
            ohne = await am._sichten_laufend(db, aid, ids)
            ohne["quellen"] = await _quellen(db, aid)
        with am.umgebung(form, svc):
            mit["quellen"] = await _quellen(db, aid)
    finally:
        await db.close()
        await engine.dispose()
    return mit, ohne


def _nahe(ist, soll) -> bool:
    return ist is not None and soll is not None and abs(ist - soll) <= _TOL


async def test_m10_bhkw_zaehlt_ohne_ha(tmp_path):
    """BHKW hinter dem Zähler (Sonstiges-Erzeuger aus der Bilanz-Summe der fünften Quelle) und Sauna (Sonstiges-Gruppe)."""
    mit, ohne = await _miss("M10", tmp_path)
    m, v = ohne["monat"], ohne["verlauf"]
    # Die Quellen-Übersicht nennt die HA-Statistik nur, wenn sie geliefert hat — die Kanal-Gruppen ohne HA sind keine.
    assert ohne["quellen"]["ha_statistics"] is False and mit["quellen"]["ha_statistics"] is True
    assert ohne["quellen"]["tagesebene"] is True
    for feld in ("eigenverbrauch_kwh", "gesamtverbrauch_kwh", "autarkie_prozent", "netto_ertrag_euro", "ev_ersparnis_euro"):
        assert _nahe(m[feld], v[feld]), (feld, m[feld], v[feld])
    assert _nahe(m["sonstiges_erzeugung_kwh"], v["sonstige_erzeugung_kwh"])
    assert m["sonstiges_verbrauch_kwh"] == mit["monat"]["sonstiges_verbrauch_kwh"] == 2.4
    # Cockpit → Jahr (Monatszeile Juli) faltet Cockpit → Monat — derselbe Wert.
    assert ohne["jahr"]["eigenverbrauch_kwh"] == m["eigenverbrauch_kwh"]


async def test_m09_dienstwagen_und_heimladung_ohne_ha(tmp_path):
    mit, ohne = await _miss("M09", tmp_path)
    m, v = ohne["monat"], ohne["verlauf"]
    assert m["dienstliche_ladekosten_euro"] == v["dienstliche_ladekosten_euro"] == 1.8
    assert m["netto_ertrag_euro"] == v["netto_ertrag_euro"] == 10.44
    for feld in ("emob_ladung_kwh", "emob_ladung_pv_kwh", "emob_ladung_netz_kwh"):
        assert m[feld] == mit["monat"][feld] and m[feld] is not None, feld
    assert m["emob_ladung_kwh"] == ohne["fakten_tw"]["emob"]["ladung_kwh"] == 6.0


async def test_m06_betriebsart_strom_ohne_ha(tmp_path):
    mit, ohne = await _miss("M06", tmp_path)
    m, f = ohne["monat"], ohne["fakten_tw"]["wp"]
    for feld in ("wp_modus_strom_heizen_kwh", "wp_modus_strom_kuehlen_kwh", "wp_waerme_kwh", "wp_strom_kwh"):
        assert m[feld] == mit["monat"][feld] and m[feld] is not None, feld
    assert _nahe(m["wp_modus_strom_heizen_kwh"], f["modus_strom_heizen_kwh"])
    assert _nahe(m["wp_modus_strom_kuehlen_kwh"], f["modus_strom_kuehlen_kwh"])


@pytest.mark.parametrize("fid", ["M02", "M07", "M08", "W2-E"])
async def test_weitere_formen_ohne_ha_wie_verlauf(fid, tmp_path):
    """Die übrigen Formen mit Kanal-Gruppen: Bilanz und Ergebnis ohne HA = Jahr-Verlauf; die Gruppen ohne HA = mit HA."""
    mit, ohne = await _miss(fid, tmp_path)
    m, v = ohne["monat"], ohne["verlauf"]
    for feld in ("eigenverbrauch_kwh", "gesamtverbrauch_kwh", "autarkie_prozent", "netto_ertrag_euro"):
        assert _nahe(m[feld], v[feld]), (fid, feld, m[feld], v[feld])
    for feld in ("emob_ladung_kwh", "sonstiges_verbrauch_kwh", "wp_strom_kwh", "wp_waerme_kwh"):
        assert m.get(feld) == mit["monat"].get(feld), (fid, feld)
