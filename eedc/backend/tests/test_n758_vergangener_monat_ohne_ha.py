"""N-758 (17.10.2026, Konzept R-11/E6) — Cockpit → Monat nennt einen VERGANGENEN Monat ohne Abschluss auch ohne antwortende
HA-Statistik, wenn die Kanäle der Bilanz-Gruppe ihn voll decken.

Bis dahin sammelte die Route die fünfte Quelle (Tagesebene, N-472) nur im laufenden Monat, und den Kanal-Ersatz der
Bilanz-Gruppe gab es nur auf dem HA-Weg (``quellen_leser._ha_statistik_aus_kanaelen_mit_marke``: ``if not ha_stats``) —
ohne HA (Standalone, HA nicht erreichbar) blieb der vergangene Juni leer, während Monats-Fakten und Jahr-Verlauf ihn aus
denselben Kanälen trugen (PV-Matrix W2-SA-VOR, «Soll unklar» ``_U_SA_VOR`` beider Matrizen). Seit N-758 gilt für diesen
Monat die Wahl der Monats-Fakten (``_summen_der_tagesebene``: ``kanal_monate`` nennt ihn ⇒ ``lade_monats_summen``), die
Geräte-/WP-Gruppen folgen wie N-750. Der Kanal-Ersatz je HA-Sensor wäre ohne HA falsch gewesen: er kennt nur die Bilanz-
Gruppe, die String-/BKW-Sensoren fehlen — gemessen F13a 594 statt 630 (Bericht ``opus-berichte/FUND-N758.md``).

Uhr der Matrix (04.07.2026 00:30): Juni vorbei ohne Abschluss, Juli läuft, Mai ohne Kanal-Deckung (Reihe ab 31.05. 18:00).
Werkzeug der Messung: ``~/.claude/plans/ha-bauform-werkzeug/fund-n758/``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import insert

from datetime import date

from backend.models.monatsdaten import Monatsdaten
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

_MAI_31 = date(mx.JAHR, 5, 31)
_TOL = 0.051   # Anzeige-Rundung des Jahr-Verlaufs (0,1)
_BILANZ = ("pv", "einsp", "netz", "ev", "autarkie")


def _nahe(a, b) -> bool:
    return a is not None and b is not None and abs(a - b) <= _TOL


async def _quellen(db, aid: int, monat: int) -> dict:
    import backend.api.routes.aktueller_monat as amr

    r = await amr.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=monat, db=db)
    return dict(r.quellen)


async def _sa(fid: str, tmp_path):
    """SA-Datenstand der PV-Matrix (Zuordnung mit HA-Sensoren, HA antwortet nicht, Eigene Summe aus den Stundenständen)."""
    form = mx.MATRIX_FORMEN[fid]
    engine, db = await mx._neue_db(str(tmp_path / f"{fid}.db"))
    aid, ids = await mx.seed_anlage(db, form)
    await mx.seed_snapshots(db, form, aid, ids)
    with mx._umgebung(mx._ha_aus()):
        await mx.fuelle_eigene_summe(engine, aid)
        # Der 31.05. als Tageszeile (Reihe ab 18:00): der Mai hat eine Tagesspur, aber keine volle Kanal-Deckung.
        await mx.aggregiere_tage(db, form, aid, (_MAI_31,) + mx.TAGE_JUNI + mx.TAGE_JULI)
        await mx.baue_abgeleitete_nach_tagen(engine, aid)
    return engine, db, aid, ids


async def _sichten(db, aid, ids, monat=mx.JUNI) -> dict:
    return {"monat": await mx.miss_cockpit_monat(db, aid, monat),
            "verlauf": await mx.miss_aggregiert(db, aid, monat, voll=True),
            "fakten_tw": await mx.miss_fakten(db, aid, ids, monat, tageswerte=True),
            "jahr": (await mx.miss_jahr(db, aid))["monate"].get(monat),
            "quellen": await _quellen(db, aid, monat)}


def _wie_verlauf(s: dict) -> None:
    m, v, j = s["monat"], s["verlauf"], s["jahr"]
    for g in _BILANZ:
        assert _nahe(m[g], v[g]), (g, m[g], v[g])
        assert j[g] == m[g], (g, j[g], m[g])          # Cockpit → Jahr faltet Cockpit → Monat
    assert m["pv"] == s["fakten_tw"]["pv"] and m["ev"] == s["fakten_tw"]["ev"]
    assert m["pv_quelle"] == "tagesebene"
    assert s["quellen"]["tagesebene"] is True and s["quellen"]["ha_statistics"] is False


@pytest.mark.parametrize("fid", ["W2-V", "W2-L", "F13a", "W2-B"])
async def test_sa_vergangener_monat_aus_den_kanaelen(fid, tmp_path):
    """I2/I3/I5/I6 der Matrix: PV, Netz, Eigenverbrauch, Autarkie = Monats-Fakten = Jahr-Verlauf (F13a/W2-B: Strings UND
    Anlagenzähler gemessen — die Komposition der Fakten, nicht der Anlagenzähler allein)."""
    engine, db, aid, ids = await _sa(fid, tmp_path)
    try:
        with mx._umgebung(mx._ha_aus()):
            s = await _sichten(db, aid, ids)
            mai = await mx.miss_cockpit_monat(db, aid, 5)
            mai_quellen = await _quellen(db, aid, 5)
            mai_tw = await mx.miss_fakten(db, aid, ids, 5, tageswerte=True)
    finally:
        await db.close()
        await engine.dispose()
    _wie_verlauf(s)
    # Gegenprobe: der Mai ist nicht voll gedeckt (Reihe ab 31.05. 18:00) — er bleibt leer, obwohl der 31.05. eine
    # Tageszeile hat (eine Teilmenge der Tage wäre die «stille Untertreibung» von N-472; Antwort: der Abschluss).
    assert mai_tw is not None                                           # die Tagesspur gibt es (Netz am Abend)
    assert mai["pv"] is None and mai["einsp"] is None and mai["netz"] is None
    assert mai_quellen["tagesebene"] is False


async def test_reine_mqtt_anlage_ohne_zuordnung(tmp_path):
    """Standalone ohne HA-Sensoren (Zuordnung leer, Eigene Summe aus MQTT): dieselbe Wahl wie die Monats-Fakten."""
    async with kg.datenstand("pv", "F01", "MQTT", eigene_summe_aus="sensor_snapshots") as ds:
        with mx._umgebung(mx._ha_aus()):
            s = await _sichten(ds.db, ds.aid, ds.ids)
    _wie_verlauf(s)
    assert s["monat"]["pv"] == 630.0


async def test_ha_seed_ha_nicht_erreichbar_wie_mit_ha(tmp_path):
    """HA-Datenstand (Spiegel), dieselbe Datenbank mit HA und mit HA aus: dieselben Bilanzzahlen."""
    async with kg.datenstand("pv", "W2-B7", "HA") as ds:
        with mx._umgebung(ds.svc):
            mit = await mx.miss_cockpit_monat(ds.db, ds.aid, mx.JUNI)
        with mx._umgebung(mx._ha_aus()):
            s = await _sichten(ds.db, ds.aid, ds.ids)
    _wie_verlauf(s)
    for g in _BILANZ:
        assert s["monat"][g] == mit[g], (g, s["monat"][g], mit[g])


async def test_laufender_monat_unveraendert_und_teilzeitraum(tmp_path):
    """Laufender Monat (Juli): weiter die fünfte Quelle. Juni: dieselbe Marke — die Felder der Tagesebene sind
    Teilzeitraum-Felder (#361, ``teilzeitraum_felder``), sperren also die Aggregation der Gerätewerte nicht."""
    import backend.api.routes.aktueller_monat as amr

    engine, db, aid, ids = await _sa("F13a", tmp_path)
    try:
        with mx._umgebung(mx._ha_aus()):
            juli = await _sichten(db, aid, ids, mx.JULI)
            out = {}
            for monat in (mx.JUNI, mx.JULI):
                k = await amr._kopf_des_monats(db, aid, mx.JAHR, monat)
                out[monat] = await amr._quellen_des_monats(
                    db, k["anlage"], aid, k["investitionen"], mx.JAHR, monat, k["ist_aktueller_monat"], None)
    finally:
        await db.close()
        await engine.dispose()
    assert juli["quellen"]["tagesebene"] is True and juli["monat"]["pv_quelle"] == "tagesebene"
    assert juli["monat"]["pv"] == juli["fakten_tw"]["pv"]
    for monat in (mx.JUNI, mx.JULI):
        te = set(out[monat]["tagesebene"])
        assert {"pv_erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh"} <= te
        gewonnen = {f for f, (_w, q) in out[monat]["resolved"].items() if q.quelle == "tagesebene" and f in te}
        assert gewonnen and gewonnen <= out[monat]["teilzeitraum"], (monat, gewonnen - out[monat]["teilzeitraum"])


async def test_gespeicherter_teilabschluss_gewinnt(tmp_path):
    """P8: ein gespeicherter Teil-Abschluss des Juni (nur Netzwerte) gewinnt für seine Felder; die übrigen füllt die
    fünfte Quelle (sie füllt nur, verdrängt nie)."""
    engine, db, aid, ids = await _sa("W2-V", tmp_path)
    try:
        await db.execute(insert(Monatsdaten).values(anlage_id=aid, jahr=mx.JAHR, monat=mx.JUNI,
                                                    einspeisung_kwh=111.0, netzbezug_kwh=222.0))
        await db.commit()
        with mx._umgebung(mx._ha_aus()):
            m = await mx.miss_cockpit_monat(db, aid, mx.JUNI)
            fk = await mx.miss_fakten(db, aid, ids, mx.JUNI, tageswerte=True)
    finally:
        await db.close()
        await engine.dispose()
    assert m["einsp"] == 111.0 and m["netz"] == 222.0
    assert m["pv"] == fk["pv"] == 466.56 and m["pv_quelle"] == "tagesebene"
