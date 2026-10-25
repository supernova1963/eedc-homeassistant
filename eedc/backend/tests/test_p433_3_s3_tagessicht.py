"""P-433-3 Sitzung 3 (#432) — Tagessicht Wärme/Klima: Stundenleser für Mittelwerte, Temperaturen je Gerät und Stunde,
Wärme-Stapel nach Funktion mit Rest, Herleitung je Funktion, Ø Vorlauf/Spreizung, Geräte-Regel «AZ ohne Zusatzheizung»
Tag == Monat (S3-8) und Rundung Zähler/Nenner (S3-9).

Bauplan ``~/.claude/plans/bauplan-p433-3-temperaturen-heizstab-tagessicht.md`` §3 S3 (B5, B7, B9, B11, B12; G3, G4, G5).
Fixtures: Wärme A (nur Summanden ⇒ Rest 0) · B (Gesamt + Summanden ⇒ Rest > 0) · C (zwei Geräte gemischt ⇒ Σ = Linie
je Slot); Temperaturen an einem Bestandstag (Ende-Raster, Umlegung) und einem WP-Kanal-Tag (Beginn-Raster).

Schwesterdateien: ``test_waerme_verlauf_stunden.py`` (Verlauf), ``test_kanal_lesen.py`` (Lese-Schicht),
``test_p433_3_s2_heizstab_zusatzheizung.py`` (Ausweis-Zahl), ``test_kanal_lesen_waechter.py`` (Mittelwert-Leser-Wächter).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.modus_split import ModusStunde
from backend.core.berechnungen.temperatur_tagesmittel import (
    BETRIEB_AUS_MODUS,
    BETRIEB_AUS_STROM,
    temperatur_tagesmittel,
)
from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_GERAETE_OHNE_ZUSATZHEIZUNG,
    zaehlt_fuer_geraete_regel,
)
from backend.core.betriebsmodus import AUS, HEIZEN, UNBESTIMMT, WARMWASSER
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.kanal import ART_MEAN, ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._provenance_helpers import seed_tz_provenance
from backend.services.kanal.lesen import (
    GRUND_BEGINNT_NACH_VON,
    GRUND_KEINE_ZEILE,
    stundenmittel_stapel,
)
from backend.services.snapshot.boundary_range import TZ_QUELLE_LTS

DATUM = date(2026, 1, 15)
T0 = datetime.combine(DATUM, datetime.min.time())
H = 3600
JETZT = 4_102_444_800


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


# ═══ S3-1 Der Stundenleser für Mittelwerte ═══════════════════════════════════

async def _kanal(db, aid: int, key: str, art: str, zeilen, *, einheit: str = "°C") -> Kanal:
    """``zeilen``: ``[(start_ts, mean, min, max)]`` bei ``mean``, ``[(start_ts, sum)]`` bei ``sum``."""
    k = Kanal(anlage_id=aid, key=key, art=art, einheit=einheit)
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=zeilen[0][0] if zeilen else 0, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.q", offset=0.0))
    reihen = []
    for z in zeilen:
        if art == ART_MEAN:
            reihen.append({"kanal_id": k.id, "start_ts": z[0], "sum": None, "state": None, "mean": z[1],
                           "min": z[2], "max": z[3], "familie": FAMILIE_SPIEGEL})
        else:
            reihen.append({"kanal_id": k.id, "start_ts": z[0], "sum": z[1], "state": None, "mean": None,
                           "min": None, "max": None, "familie": FAMILIE_SPIEGEL})
    if reihen:
        await db.execute(insert(KanalStatistik), reihen)
    await db.flush()
    return k


async def _leere_anlage(db, name="S3") -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_stundenmittel_je_stunde_ohne_interpolation(db):
    a = await _leere_anlage(db)
    von = _ts(T0)
    zeilen = [(von + h * H, 30.0 + h, 29.0 + h, 31.0 + h) for h in range(24) if h != 7]   # Stunde 7 fehlt
    k = await _kanal(db, a.id, "inv:1:vorlauf_temperatur_c", ART_MEAN, [(von - H, 29.0, 28.0, 30.0), *zeilen])
    sm = (await stundenmittel_stapel(db, [k], von, von + 24 * H, jetzt=JETZT))[k.key]
    assert sm.einheit == "°C"
    assert sm.stunden == 23 and sm.fehlende_stunden == 1
    assert von + 7 * H not in sm.werte, "eine Lücke bleibt eine Lücke — kein Vortragen, keine Interpolation"
    assert sm.werte[von + 8 * H] == (38.0, 37.0, 39.0)
    assert sm.voll and sm.grund is None
    assert sm.gedeckt_von == von and sm.gedeckt_bis == von + 24 * H


@pytest.mark.asyncio
async def test_stundenmittel_abdeckung_und_arten(db):
    a = await _leere_anlage(db)
    von = _ts(T0)
    k_spaet = await _kanal(db, a.id, "inv:1:ruecklauf_temperatur_c", ART_MEAN, [(von + 5 * H, 25.0, 25.0, 25.0)])
    k_leer = await _kanal(db, a.id, "inv:1:warmwasser_temperatur_c", ART_MEAN, [])
    res = await stundenmittel_stapel(db, [k_spaet, k_leer], von, von + 24 * H, jetzt=JETZT)
    assert res[k_spaet.key].grund == GRUND_BEGINNT_NACH_VON and res[k_spaet.key].werte == {von + 5 * H: (25.0, 25.0, 25.0)}
    assert res[k_leer.key].grund == GRUND_KEINE_ZEILE and res[k_leer.key].stunden == 0
    k_sum = await _kanal(db, a.id, "inv:1:stromverbrauch_kwh", ART_SUM, [(von, 1.0)], einheit="kWh")
    with pytest.raises(ValueError):
        await stundenmittel_stapel(db, [k_sum], von, von + H, jetzt=JETZT)
    assert await stundenmittel_stapel(db, [], von, von + H, jetzt=JETZT) == {}


@pytest.mark.asyncio
async def test_stundenmittel_eine_anweisung_fuer_viele_kanaele(db):
    from backend.tests.test_kanal_lesen import _Zaehler

    a = await _leere_anlage(db)
    von = _ts(T0)
    kn = [await _kanal(db, a.id, f"inv:{i}:vorlauf_temperatur_c", ART_MEAN,
                       [(von + h * H, 30.0, 30.0, 30.0) for h in range(24)]) for i in range(5)]
    with _Zaehler(db) as z:
        res = await stundenmittel_stapel(db, kn, von, von + 24 * H, jetzt=JETZT)
    assert z.n == 1 and all(r.stunden == 24 for r in res.values())


@pytest.mark.asyncio
async def test_kosten_preise_lesen_ueber_den_stundenleser(db):
    """W6: dieselben Preise wie der frühere rohe Leser ``start_ts ∈ [von, bis_inkl]`` (EUR/kWh × 100)."""
    from backend.services.kanal.kosten import _preise

    a = await _leere_anlage(db)
    von = _ts(T0)
    k = await _kanal(db, a.id, "basis:strompreis", ART_MEAN,
                     [(von + h * H, 0.30 + h / 100, 0.30, 0.40) for h in range(6) if h != 2], einheit="EUR/kWh")
    preise = await _preise(db, k, von, von + 4 * H, jetzt=JETZT)
    assert preise == {von + h * H: pytest.approx((0.30 + h / 100) * 100) for h in (0, 1, 3, 4)}


# ═══ Layer: Ø Vorlauf / Ø Spreizung über die Betriebsstunden ═════════════════

def test_tagesmittel_ueber_modus_stunden():
    vorlauf = [20.0] * 24
    ruecklauf = [20.0] * 24
    for h in (6, 7, 8):
        vorlauf[h], ruecklauf[h] = 34.0 + (h - 6), 29.0 + (h - 6)          # 34/35/36 → 29/30/31
    modus = [ModusStunde(kwh=0.5, modus=HEIZEN, stunde=6), ModusStunde(kwh=0.4, modus=WARMWASSER, stunde=7),
             ModusStunde(kwh=0.3, modus=HEIZEN, stunde=8), ModusStunde(kwh=0.1, modus=AUS, stunde=9),
             ModusStunde(kwh=0.1, modus=UNBESTIMMT, stunde=10), ModusStunde(kwh=0.0, modus=HEIZEN, stunde=11)]
    m = temperatur_tagesmittel(vorlauf, ruecklauf, modus_stunden=modus, strom_kwh=[1.0] * 24)
    assert m.betrieb_aus == BETRIEB_AUS_MODUS
    assert m.betriebsstunden == 3 and m.spreizung_stunden == 3
    assert m.vorlauf_c == pytest.approx(35.0) and m.spreizung_k == pytest.approx(5.0)


def test_tagesmittel_ohne_modus_ueber_strom_ueber_dem_minimum():
    vorlauf = [None] * 24
    ruecklauf = [None] * 24
    strom = [0.05] * 24
    for h, v in ((2, 40.0), (3, 42.0), (14, 38.0)):
        vorlauf[h], ruecklauf[h], strom[h] = v, v - 6.0, 1.2
    vorlauf[20] = 25.0                     # Stillstand: Strom am Minimum ⇒ keine Betriebsstunde
    m = temperatur_tagesmittel(vorlauf, ruecklauf, strom_kwh=strom)
    assert m.betrieb_aus == BETRIEB_AUS_STROM
    assert m.betriebsstunden == 3 and m.vorlauf_c == pytest.approx(40.0) and m.spreizung_k == pytest.approx(6.0)


def test_tagesmittel_ohne_grundlage_keine_zahl():
    m = temperatur_tagesmittel([30.0] * 24, [25.0] * 24)
    assert (m.vorlauf_c, m.spreizung_k, m.betriebsstunden, m.betrieb_aus) == (None, None, 0, None)
    gleich = temperatur_tagesmittel([30.0] * 24, [25.0] * 24, strom_kwh=[0.8] * 24)
    assert gleich.vorlauf_c is None and gleich.betriebsstunden == 0, "überall gleicher Strom: keine Betriebsstunde"
    ohne_ruecklauf = temperatur_tagesmittel([30.0] * 24, [None] * 24, strom_kwh=[0.0] * 23 + [1.0])
    assert ohne_ruecklauf.vorlauf_c == 30.0 and ohne_ruecklauf.spreizung_k is None


# ═══ S3-2/S3-3 Temperaturen je Gerät und Stunde ══════════════════════════════

async def _anlage_mit_temperaturen(db, *, mit_strom: bool = True, zweite: bool = False):
    """WP «Nibe» mit Vorlauf/Rücklauf/Warmwasser-Kanälen; Bestandstag (keine WP-Kanal-Gruppe). Strom aus Snapshots:
    Betrieb in den Slots 6, 7 (Ende-Raster) — dort Vorlauf 34/36, Rücklauf 29/30."""
    a = await _leere_anlage(db, "S3 Temperaturen")
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="Nibe", anschaffungsdatum=date(2025, 1, 1),
                     anschaffungskosten_gesamt=15000.0, parameter={"wp_art": "sole_wasser"})
    db.add(wp)
    await db.flush()
    von = _ts(T0)
    # Mittelwert-Zeilen im Beginn-Raster [H, H+1): ab Vortag 23:00 bis D 23:00.
    vor, rueck, ww = [], [], []
    for h in range(-1, 24):
        ts = von + h * H
        if h == 12:
            continue                            # eine fehlende Stunde: Lücke, keine Interpolation
        v = 34.0 if h == 5 else (36.0 if h == 6 else 22.0 + h / 10)
        r = 29.0 if h == 5 else (30.0 if h == 6 else 21.0)
        vor.append((ts, v, v - 0.5, v + 0.5))
        rueck.append((ts, r, r, r))
        ww.append((ts, 48.0, 47.0, 49.0))
    await _kanal(db, a.id, f"inv:{wp.id}:vorlauf_temperatur_c", ART_MEAN, vor)
    await _kanal(db, a.id, f"inv:{wp.id}:ruecklauf_temperatur_c", ART_MEAN, rueck)
    await _kanal(db, a.id, f"inv:{wp.id}:warmwasser_temperatur_c", ART_MEAN, ww)
    felder = {}
    live = {"vorlauf_temperatur_c": "sensor.vl", "ruecklauf_temperatur_c": "sensor.rl",
            "warmwasser_temperatur_c": "sensor.ww"}
    if mit_strom:
        stand = 100.0
        for k in range(-1, 25):
            if k >= 0:
                stand += 1.0 if k in (6, 7) else 0.05
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{wp.id}:stromverbrauch_kwh",
                                  zeitpunkt=T0 + timedelta(hours=k), wert_kwh=stand, quelle="ha_statistics"))
        felder["stromverbrauch_kwh"] = {"strategie": "sensor", "sensor_id": "sensor.wp_strom"}
    mapping = {"investitionen": {str(wp.id): {"felder": felder, "live": live}}}
    wp2 = None
    if zweite:
        wp2 = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="Zweite (MQTT)",
                          anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=5000.0,
                          parameter={"wp_art": "luft_wasser"})
        db.add(wp2)
        await db.flush()
        mapping["investitionen"][str(wp2.id)] = {"felder": {}, "live": {"vorlauf_temperatur_c": "sensor.vl2"}}
    a.sensor_mapping = mapping
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return a, wp, wp2


async def _temperaturen(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_waerme_temperaturen_stunden

    return await get_waerme_temperaturen_stunden(anlage_id, DATUM, db)


@pytest.mark.asyncio
async def test_bestandstag_ende_raster_mit_umlegung(db):
    """B12: an einem Bestandstag trägt Slot h die Stunde [h−1, h) — Slot 0 die Zeile Vortag 23:00, Slot 6 die Zeile
    05:00. Sprengsatz-Ziel «Umlegung weg» ⇒ Slot 6 trüge 36 °C (die Zeile 06:00) statt 34 °C."""
    a, wp, _ = await _anlage_mit_temperaturen(db)
    t = await _temperaturen(db, a.id)
    assert t.raster == "ende"
    g = t.geraete[0]
    assert (g.investition_id, g.bezeichnung) == (wp.id, "Nibe")
    s = {x.stunde: x for x in g.stunden}
    assert len(g.stunden) == 24
    assert s[0].vorlauf_c == pytest.approx(21.9), "Slot 0 = Zeile Vortag 23:00 (22 − 0,1)"
    assert (s[6].vorlauf_c, s[6].ruecklauf_c) == (34.0, 29.0)
    assert (s[7].vorlauf_c, s[7].ruecklauf_c) == (36.0, 30.0)
    assert s[6].warmwasser_c == 48.0
    assert (s[6].spreizung_k, s[7].spreizung_k, s[13].spreizung_k) == (5.0, 6.0, None), "Spreizung aus dem Layer"
    assert s[13].vorlauf_c is None and s[13].ruecklauf_c is None, "fehlende Zeile 12:00 ⇒ Slot 13 leer"
    assert g.abdeckung_h == 23, "Interpolation hätte 24 Stunden"


@pytest.mark.asyncio
async def test_kopf_aus_dem_layer_ueber_die_betriebsstunden(db):
    """Ø Vorlauf/Ø Spreizung über die Slots 6/7 (Strom über dem Minimum, kein Modus-Signal): (34 + 36)/2 = 35,
    Spreizung (5 + 6)/2 = 5,5 K — nicht das Mittel über 24 Stunden."""
    a, _wp, _ = await _anlage_mit_temperaturen(db)
    g = (await _temperaturen(db, a.id)).geraete[0]
    assert g.betrieb_aus == BETRIEB_AUS_STROM
    assert g.betriebsstunden == 2
    assert g.vorlauf_mittel_c == 35.0 and g.spreizung_mittel_k == 5.5


@pytest.mark.asyncio
async def test_ohne_strom_kein_kopf_und_ohne_kanal_genannt(db):
    a, _wp, wp2 = await _anlage_mit_temperaturen(db, mit_strom=False, zweite=True)
    t = await _temperaturen(db, a.id)
    g = t.geraete[0]
    assert g.abdeckung_h == 23 and g.vorlauf_mittel_c is None and g.betriebsstunden == 0 and g.betrieb_aus is None
    assert [(o.investition_id, o.bezeichnung, o.felder) for o in t.ohne_kanal] == [
        (wp2.id, "Zweite (MQTT)", ["vorlauf_temperatur_c"])]
    assert [x.investition_id for x in t.geraete] == [g.investition_id], "ein Gerät ohne Kanal hat keine Stunden"


@pytest.mark.asyncio
async def test_kanal_tag_beginn_raster_ohne_umlegung(db, monkeypatch):
    """An einem WP-Kanal-Tag liegt Stunde h auf [h, h+1) — die Zeile 05:00 in Stunde 5, keine Vortagszeile."""
    from types import SimpleNamespace

    from backend.services.energie_profil import kanal_stunden
    from backend.services.kanal.stunden_leser import GRUPPE_WP

    a, wp, _ = await _anlage_mit_temperaturen(db, mit_strom=False)

    async def _wp_kanal_tag(_db, _aid, _datum, **_k):
        return SimpleNamespace(gruppen={GRUPPE_WP: object()})

    monkeypatch.setattr(kanal_stunden, "kanal_stundentag", _wp_kanal_tag)
    invs = {str(wp.id): wp}
    tag = await kanal_stunden.wp_temperaturen_je_stunde(db, a, invs, DATUM)
    assert tag.raster == "beginn"
    r = tag.geraete[0].reihen
    assert (r["vorlauf_c"][5], r["vorlauf_c"][6], r["ruecklauf_c"][5]) == (34.0, 36.0, 29.0)
    assert r["vorlauf_c"][0] == pytest.approx(22.0), "Stunde 0 = Zeile 00:00, nicht die des Vortags"
    assert r["vorlauf_c"][12] is None and tag.geraete[0].abdeckung_h == 23


@pytest.mark.asyncio
async def test_stillgelegtes_geraet_und_andere_typen_fehlen(db):
    a, wp, _ = await _anlage_mit_temperaturen(db, mit_strom=False)
    wp.stilllegungsdatum = date(2025, 12, 31)
    await db.commit()
    t = await _temperaturen(db, a.id)
    assert t.geraete == [] and t.ohne_kanal == []


# ═══ S3-4 Wärme-Stapel mit Rest ══════════════════════════════════════════════

def _reihe(sprunge: dict[int, float]) -> list[float]:
    """Zuwachs je Slot (Index k = 0..24), Rest 0."""
    return [sprunge.get(k, 0.0) for k in range(25)]


async def _anlage_waerme(db, geraete: list[dict]):
    """Je Gerät ``{feld: {slot: kWh}}`` — Snapshots im Backward-Raster wie im HA-Hauptpfad (LTS), Tageszeile mit dem
    Strom. Jedes Gerät bekommt einen Stromzähler (1 kWh in den Slots mit Wärme, sonst 0,1)."""
    a = await _leere_anlage(db, "S3 Wärme")
    mapping: dict = {"investitionen": {}}
    komp = {}
    invs = []
    for n, felder in enumerate(geraete):
        wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung=f"WP {n + 1}",
                         anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=10000.0,
                         parameter={"wp_art": "luft_wasser"})
        db.add(wp)
        await db.flush()
        invs.append(wp)
        slots = {k for f in felder.values() for k in f}
        felder = {**felder, "stromverbrauch_kwh": {k: (1.0 if k in slots else 0.1) for k in range(25)}}
        cfg = {}
        for feld, sprunge in felder.items():
            cfg[feld] = {"strategie": "sensor", "sensor_id": f"sensor.{feld}_{n}"}
            stand, inc = 100.0, _reihe(sprunge)
            for k in range(-1, 25):
                if k >= 0:
                    stand += inc[k]
                db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{wp.id}:{feld}",
                                      zeitpunkt=T0 + timedelta(hours=k), wert_kwh=stand, quelle="ha_statistics"))
        mapping["investitionen"][str(wp.id)] = {"felder": cfg}
        komp[f"waermepumpe_{wp.id}"] = round(sum(_reihe(felder["stromverbrauch_kwh"])[:24]), 3)
    a.sensor_mapping = mapping
    flag_modified(a, "sensor_mapping")
    tz = TagesZusammenfassung(anlage_id=a.id, datum=DATUM, komponenten_kwh=komp)
    seed_tz_provenance(tz, writer="test", source=TZ_QUELLE_LTS)
    db.add(tz)
    for h in range(24):
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=DATUM, stunde=h, waermepumpe_kw=0.1))
    await db.commit()
    return a, invs


async def _verlauf(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_waerme_verlauf_stunden

    return await get_waerme_verlauf_stunden(anlage_id, DATUM, db)


def _summe_ist_linie(v):
    for s in v.stunden:
        if s.wp_waerme_kwh is None:
            assert s.wp_waerme_heizen_kwh is None and s.wp_waerme_uebrige_kwh is None
            continue
        stapel = s.wp_waerme_heizen_kwh + s.wp_waerme_warmwasser_kwh + s.wp_waerme_uebrige_kwh
        assert stapel == pytest.approx(s.wp_waerme_kwh, abs=1e-9), s.stunde
        assert s.wp_waerme_uebrige_kwh >= 0


@pytest.mark.asyncio
async def test_fixture_a_nur_summanden_rest_null(db):
    a, _ = await _anlage_waerme(db, [{"heizenergie_kwh": {6: 4.0, 18: 2.0}, "warmwasser_kwh": {7: 1.5}}])
    v = await _verlauf(db, a.id)
    assert v.waerme_funktions_stapel_verfuegbar is True
    s6, s7 = v.stunden[6], v.stunden[7]
    assert (s6.wp_waerme_heizen_kwh, s6.wp_waerme_warmwasser_kwh, s6.wp_waerme_uebrige_kwh) == (4.0, 0.0, 0.0)
    assert (s7.wp_waerme_heizen_kwh, s7.wp_waerme_warmwasser_kwh, s7.wp_waerme_uebrige_kwh) == (0.0, 1.5, 0.0)
    assert all(s.wp_waerme_uebrige_kwh == 0.0 for s in v.stunden)
    _summe_ist_linie(v)


@pytest.mark.asyncio
async def test_fixture_b_gesamt_und_summanden_rest_groesser_null(db):
    """D1: der gemeinsame Wärmemengenzähler gewinnt — seine Wärme ist nicht je Funktion gemessen (Rest), auch wenn das
    Gerät zusätzlich Summanden trägt. Die Höhe bleibt die Linie. Sprengsatz-Ziel «Summanden nur der Achsen-Geräte»: ohne
    `nur_geraete` würde dieses Fixture Rest 1,0 statt 5,0 zeigen (Nachmessung 25.10.2026); die Klemme `max(0, …)` ist
    per Konstruktion nur Rundungsschutz und kein Sprengsatz-Ziel."""
    a, _ = await _anlage_waerme(db, [{"waerme_kwh": {6: 5.0, 7: 1.0}, "heizenergie_kwh": {6: 4.0},
                                      "warmwasser_kwh": {7: 1.0}}])
    v = await _verlauf(db, a.id)
    s6 = v.stunden[6]
    assert s6.wp_waerme_kwh == 5.0
    assert s6.wp_waerme_uebrige_kwh == 5.0 and s6.wp_waerme_heizen_kwh == 0.0
    _summe_ist_linie(v)


@pytest.mark.asyncio
async def test_fixture_c_zwei_geraete_gemischt(db):
    a, _ = await _anlage_waerme(db, [
        {"heizenergie_kwh": {6: 4.0}, "warmwasser_kwh": {7: 1.0}},     # Summanden
        {"waerme_kwh": {6: 3.0, 9: 2.0}},                              # nur Gesamt
    ])
    v = await _verlauf(db, a.id)
    s6, s9 = v.stunden[6], v.stunden[9]
    assert (s6.wp_waerme_kwh, s6.wp_waerme_heizen_kwh, s6.wp_waerme_uebrige_kwh) == (7.0, 4.0, 3.0)
    assert (s9.wp_waerme_kwh, s9.wp_waerme_heizen_kwh, s9.wp_waerme_uebrige_kwh) == (2.0, 0.0, 2.0)
    _summe_ist_linie(v)


@pytest.mark.asyncio
async def test_nur_gesamtzaehler_kein_waerme_stapel_und_strom_unberuehrt(db):
    a, _ = await _anlage_waerme(db, [{"waerme_kwh": {6: 3.0}}])
    v = await _verlauf(db, a.id)
    assert v.waerme_funktions_stapel_verfuegbar is False
    assert all(s.wp_waerme_heizen_kwh is None and s.wp_waerme_uebrige_kwh is None for s in v.stunden)
    assert v.stunden[6].wp_waerme_kwh == 3.0


# ═══ S3-5 Herleitung je Funktion ═════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tag_detail_zaehler_und_nenner_je_funktion(db):
    """Heizen 12 kWh Wärme ÷ 3 kWh Strom Heizen = 4,0 — Zähler und Nenner aus demselben Layer-Objekt."""
    from backend.api.routes.energie_profil.views import get_tag_detail

    a, (wp,) = await _anlage_waerme(db, [{"heizenergie_kwh": {6: 8.0, 18: 4.0}, "warmwasser_kwh": {7: 2.0},
                                          "strom_heizen_kwh": {6: 2.0, 18: 1.0}, "strom_warmwasser_kwh": {7: 1.0}}])
    wp.parameter = {**wp.parameter, "getrennte_strommessung": True}
    flag_modified(wp, "parameter")
    await db.commit()
    t = await get_tag_detail(a.id, DATUM, db)
    assert t.wp_jaz_heizen == pytest.approx(4.0)
    assert (t.wp_jaz_heizen_zaehler_kwh, t.wp_jaz_heizen_nenner_kwh) == (pytest.approx(12.0), pytest.approx(3.0))
    assert (t.wp_jaz_warmwasser_zaehler_kwh, t.wp_jaz_warmwasser_nenner_kwh) == (pytest.approx(2.0), pytest.approx(1.0))
    assert t.wp_jaz_kuehlen is None and t.wp_jaz_kuehlen_zaehler_kwh is None and t.wp_jaz_kuehlen_nenner_kwh is None


# ═══ S3-8 Geräte-Regel Tag == Monat ══════════════════════════════════════════

def test_layer_kriterium():
    assert zaehlt_fuer_geraete_regel(3.0, 0.0)
    assert not zaehlt_fuer_geraete_regel(3.0, 3.0), "nur Kühlstrom ⇒ steht nicht im Nenner"
    assert not zaehlt_fuer_geraete_regel(None)
    assert zaehlt_fuer_geraete_regel(3.0, 2.5)


async def _tag_wp_mit_heizstab_und_klima(db, *, klima_kuehlt: bool, klima_waerme: float | None = None):
    from backend.tests.test_bs6_kaelte_je_tag import STROM_K
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import _tag_lage
    from backend.tests.test_bs6_kaelte_je_tag import _tageszaehler

    a = await _tag_lage(db, heizstab=0.4)
    klima = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="Klima",
                        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1000.0,
                        parameter={"wp_art": "luft_luft"})
    db.add(klima)
    await db.flush()
    _tageszaehler(db, a, klima, "stromverbrauch_kwh", 3.0)
    if klima_kuehlt:
        _tageszaehler(db, a, klima, STROM_K, 3.0)
    if klima_waerme is not None:
        _tageszaehler(db, a, klima, "waerme_kwh", klima_waerme)
    tz = (await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == a.id))).scalars().one()
    tz.komponenten_kwh = {**tz.komponenten_kwh, f"waermepumpe_{klima.id}": 3.0}
    flag_modified(tz, "komponenten_kwh")
    a.sensor_mapping = dict(a.sensor_mapping)
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_tag_klima_nur_kuehlstrom_zaehlt_nicht_fuer_die_geraete_regel(db):
    """S3-8: ein Gerät, dessen Strom nach dem Kühl-/Lüft-Abzug 0 ist, steht nicht im Nenner — sein fehlender
    Heizstab-Zähler sperrt die Zahl nicht mehr. Gemessen an einer Klima MIT Wärmezähler (sonst macht sie die Hauptzahl
    zur Schranke, s. nächste Probe): vor S3-8 «nicht alle Geräte melden Zusatzheizung», jetzt (26,5 − 0,4)/(6 − 0,4)."""
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import _tag

    t = await _tag(db, (await _tag_wp_mit_heizstab_und_klima(db, klima_kuehlt=True, klima_waerme=0.5)).id)
    assert t.wp_heizstab_kwh == pytest.approx(0.4)
    assert t.wp_jaz_ohne_zusatzheizung_grund is None
    assert t.wp_jaz_ohne_zusatzheizung == pytest.approx((26.5 - 0.4) / (6.0 - 0.4))


@pytest.mark.asyncio
async def test_klima_ohne_waermezaehler_tag_und_monat_derselbe_grund(db):
    """Die übliche Klima (nur Kühlstrom, kein Wärmezähler) macht in Tag UND Monat die Hauptzahl zur Schranke (E1b) —
    beide nennen deshalb denselben Satz statt einer Ausweis-Zahl (benannte Grenze, Bericht S3 Halt H2)."""
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import _tag
    from backend.tests.test_r2_je_funktion import _monat

    t = await _tag(db, (await _tag_wp_mit_heizstab_und_klima(db, klima_kuehlt=True)).id)
    m = await _monat(db, (await _monat_wp_mit_heizstab_und_klima(db, klima_kuehlt=True)).id)
    assert t.wp_jaz_ist_schranke and m.wp_jaz_ist_schranke
    assert t.wp_jaz_ohne_zusatzheizung is None and m.wp_jaz_ohne_zusatzheizung is None
    assert t.wp_jaz_ohne_zusatzheizung_grund == m.wp_jaz_ohne_zusatzheizung_grund == "Klima: Strom ohne Wärmemessung enthalten"


@pytest.mark.asyncio
async def test_tag_klima_mit_heizstrom_ohne_zaehler_sperrt(db):
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import _tag

    t = await _tag(db, (await _tag_wp_mit_heizstab_und_klima(db, klima_kuehlt=False, klima_waerme=0.5)).id)
    assert t.wp_heizstab_kwh == pytest.approx(0.4)
    assert t.wp_jaz_ohne_zusatzheizung is None
    assert t.wp_jaz_ohne_zusatzheizung_grund == GRUND_GERAETE_OHNE_ZUSATZHEIZUNG


async def _monat_wp_mit_heizstab_und_klima(db, *, klima_kuehlt: bool, klima_waerme: float | None = None):
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import (
        FELD, HEIZSTAB_MONAT, MONAT_OHNE, _lage,
    )
    from backend.tests.test_r2_je_funktion import _geraet

    a, _inv = await _lage(db, {**MONAT_OHNE, FELD: HEIZSTAB_MONAT}, name="P433-3 S3-8 Monat")
    daten = {"stromverbrauch_kwh": 300.0}
    if klima_kuehlt:
        daten["betriebsart_strom_kuehlen_kwh"] = 300.0
    if klima_waerme is not None:
        daten["waerme_kwh"] = klima_waerme
    await _geraet(db, a, "Klima", {"wp_art": "luft_luft"}, daten)
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_monat_klima_mit_heizstrom_ohne_zaehler_sperrt(db):
    from backend.tests.test_r2_je_funktion import _monat

    m = await _monat(db, (await _monat_wp_mit_heizstab_und_klima(db, klima_kuehlt=False)).id)
    assert m.wp_jaz_ohne_zusatzheizung is None and m.wp_jaz_ohne_zusatzheizung_grund


# ═══ S3-9 Rundung Zähler/Nenner ══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hub_liefert_zaehler_und_nenner_ungerundet(db):
    """Wie der Tag (`wp_jaz_zaehler_kwh`, `wp_jaz_ohne_zusatzheizung_zaehler_kwh` = Layer-Wert): 2600,04 − 40 ⇒
    2560,04, nicht 2560,0. Die Formatierung (eine Stelle) gehört dem Client."""
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import FELD, _hub, _lage

    a, _inv = await _lage(db, {"stromverbrauch_kwh": 600.03, "waerme_kwh": 2600.04, FELD: 40.0},
                          name="P433-3 S3-9 Hub")
    z = (await _hub(db, a.id))["zusammenfassung"]
    assert z["jaz_ohne_zusatzheizung_zaehler_kwh"] == pytest.approx(2560.04)
    assert z["jaz_ohne_zusatzheizung_nenner_kwh"] == pytest.approx(560.03)
