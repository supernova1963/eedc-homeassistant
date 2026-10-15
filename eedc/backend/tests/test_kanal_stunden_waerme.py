"""Wärme je Stunde an einem WP-Kanal-Tag (HA-Bauform S3, Nachbau E-S3-2; Bauplan §10c H-1 → A).

Die Wärme-Sichten (``waerme-verlauf-stunden``, ``waerme-verteilung?sicht=tag``) verteilen weiter den **Balken** (den
WP-Block von ``tag-detail``) über eine gemessene Stundenform (``tages_stapel``). An einem Tag, dessen WP-Gruppe die
Kanäle decken, ist nur die **Quelle der Form** getauscht (``kanal_stunden.wp_stundenformen``/``wp_strom_je_stunde``):
HAs ``change`` je Zähler, Modus-Stunden aus ``abgeleitet:inv:<id>:modus_strom_<art>_kwh``, die Zählerspalte aus dem
Adapter. Geprüft an den Achsen-Formen M05 (Gesamtstrom + Wärmezähler, Betriebsart-Etikett) und M06 (getrennte
Strommessung + Klima mit Betriebsart-Zählern), HA, 15.06.2026, Uhr gestellt:

* **Σ Stunden = Balken** je Segment (Betriebsart, Funktion, Wärme an M05);
* **wo Balken = Kanal-Tag, ist die Stunde das ``change``** (Wärme, Funktions-Strom, Betriebsart-Strom, Zählerspalte);
* **Gegenprobe:** eine verschobene Kanal-Zeile verschiebt die Stunden, der Balken (und Σ) bleibt — die Form kommt aus
  dem Kanal;
* die Modus-Stunden aus den abgeleiteten Kanälen (rein und an M05).

Bekannt und nicht Gegenstand (am HEAD gleich, gemessen): an M06 trägt der Balken ``wp_waerme_kwh`` 23,4 kWh, die Linie
21,6 — die Nutzenergie Heizen des Klimageräts (1,8) steht im Balken, nicht in der Wärme-Linie.

Schwesterdateien: test_waerme_verlauf_stunden.py (die Verteilung auf Bestandstagen), test_kanal_stunden_sichten.py.
"""

from __future__ import annotations

from datetime import date
import pytest
from sqlalchemy import select, update

from backend.models.kanal import Kanal, KanalStatistik
from backend.services.energie_profil.kanal_stunden import modus_stunden_aus_kanaelen, wp_stundenformen
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.stunden_adapter import stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import kanal_stundentag
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg

TAG = date(2026, 6, 15)
H = 3600


async def _sichten(ds, fid):
    from backend.api.routes.energie_profil.views import get_tag_detail, get_waerme_verlauf_stunden

    with am.umgebung(am.FORMEN[fid], ds.svc):
        return await get_tag_detail(ds.aid, TAG, ds.db), await get_waerme_verlauf_stunden(ds.aid, TAG, ds.db)


def _summe(v, feld):
    return sum(getattr(s, feld) or 0.0 for s in v.stunden)


def test_modus_stunden_aus_den_abgeleiteten_kanaelen():
    werte = {7: {"heizen": (0.3, None) + (0.0,) * 22, "rest": (0.1,) + (None,) * 23}}
    m = modus_stunden_aus_kanaelen(werte)["7"]
    assert [(s.stunde, s.modus, s.kwh) for s in m] == [(0, "heizen", 0.3), (0, None, 0.1)] + [
        (h, "heizen", 0.0) for h in range(2, 24)]


async def test_m06_summe_gleich_balken_und_stunde_gleich_change():
    async with kg.datenstand("achsen", "M06", "HA") as ds:
        tag = await kanal_stundentag(ds.db, ds.aid, TAG, jetzt=kg.JETZT_TS)
        wp = tag.gruppen["wp"]
        td, v = await _sichten(ds, "M06")
        klima, hw = ds.ids["Klima"], ds.ids["WP HW"]
    for feld in ("wp_modus_strom_heizen_kwh", "wp_modus_strom_kuehlen_kwh", "wp_modus_nicht_aufgeteilt_kwh",
                 "wp_modus_strom_bezug_kwh"):
        assert _summe(v, feld) == pytest.approx(getattr(td, feld), abs=1e-6), feld
    assert _summe(v, "wp_funktion_strom_heizen_kwh") == pytest.approx(td.wp_strom_heizen_kwh, abs=1e-6)
    adapter = stunden_aus_kanaelen(tag).zeilen
    for h, s in enumerate(v.stunden):
        assert s.wp_modus_strom_heizen_kwh == pytest.approx(wp.mengen[f"inv:{klima}:betriebsart_strom_heizen_kwh"][h])
        assert s.wp_funktion_strom_heizen_kwh == pytest.approx(wp.mengen[f"inv:{hw}:strom_heizen_kwh"][h])
        assert s.wp_strom_kwh == pytest.approx(adapter[h].waermepumpe_kw)


async def test_m05_waerme_summe_gleich_balken_und_stunde_gleich_change_und_modus_aus_kanaelen():
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        tag = await kanal_stundentag(ds.db, ds.aid, TAG, jetzt=kg.JETZT_TS)
        wp_id = ds.ids["WP"]
        td, v = await _sichten(ds, "M05")
        with am.umgebung(am.FORMEN["M05"], ds.svc):
            from backend.models.anlage import Anlage

            anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
            _formen, modus = await wp_stundenformen(ds.db, anlage, TAG, {})
    assert _summe(v, "wp_waerme_kwh") == pytest.approx(td.wp_waerme_kwh, abs=1e-6)
    waerme = tag.gruppen["wp"].mengen[f"inv:{wp_id}:waerme_kwh"]
    assert [s.wp_waerme_kwh for s in v.stunden] == pytest.approx(list(waerme))
    heizen = tag.gruppen["wp"].mengen[f"abgeleitet:inv:{wp_id}:modus_strom_heizen_kwh"]
    aus_kanal = {s.stunde: s.kwh for s in modus[str(wp_id)] if s.modus == "heizen"}
    assert [aus_kanal[h] for h in range(24)] == pytest.approx(list(heizen))


async def _verschiebe_kanal(ds, key: str, h: int, kwh: float) -> None:
    """Die Zeile der Stunde ``h`` (Slot h ⇐ start_ts = Beginn von [h−1, h)) trägt ``kwh`` mehr — die Folgestunde
    entsprechend weniger (Σ des Tages bleibt)."""
    kid = (await ds.db.execute(select(Kanal.id).where(Kanal.anlage_id == ds.aid, Kanal.key == key))).scalar_one()
    ts = tagesfenster(TAG)[0] + h * H
    await ds.db.execute(update(KanalStatistik).where(KanalStatistik.kanal_id == kid, KanalStatistik.start_ts == ts)
                        .values(sum=KanalStatistik.sum + kwh, state=KanalStatistik.state + kwh))
    await ds.db.commit()


async def test_gegenprobe_die_form_kommt_aus_dem_kanal():
    """Eine Kanal-Zeile um 0,9 kWh verschoben (Slot 5 mehr, Slot 6 weniger): die Stunden folgen dem Kanal, der Balken
    und Σ bleiben. Mit der alten Quelle (25 Stände) bewegte sich keine Stunde. Ebenso die Zählerspalte (Strom-Kanal,
    0,3 kWh): sie ist das ``change`` des Adapters, nicht die Stundenzeile."""
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp_id = ds.ids["WP"]
        td_vorher, _v = await _sichten(ds, "M05")
        await _verschiebe_kanal(ds, f"inv:{wp_id}:waerme_kwh", 5, 0.9)
        await _verschiebe_kanal(ds, f"inv:{wp_id}:stromverbrauch_kwh", 5, 0.3)
        td, kanal = await _sichten(ds, "M05")
    assert td.wp_waerme_kwh == td_vorher.wp_waerme_kwh
    assert (kanal.stunden[5].wp_strom_kwh, kanal.stunden[6].wp_strom_kwh) == pytest.approx((0.6, 0.0))
    assert kanal.stunden[5].wp_waerme_kwh == pytest.approx(1.8) and kanal.stunden[6].wp_waerme_kwh == pytest.approx(0.0)
    assert _summe(kanal, "wp_waerme_kwh") == pytest.approx(td.wp_waerme_kwh, abs=1e-6)


async def test_verteilung_des_tages_folgt_der_kanal_form_und_haelt_den_tag():
    """``waerme-verteilung?sicht=tag`` an M06: die Funktions-Summanden je Stunde sind das ``change`` von
    ``strom_heizen_kwh``; eine verschobene Kanal-Zeile verschiebt die Stunden, das Segment des Tages bleibt."""
    from backend.api.routes.energie_profil.views import get_waerme_verteilung

    async def _verteilung(ds):
        with am.umgebung(am.FORMEN["M06"], ds.svc):
            return await get_waerme_verteilung(ds.aid, "tag", None, None, TAG, ds.db)

    async with kg.datenstand("achsen", "M06", "HA") as ds:
        hw = ds.ids["WP HW"]
        vorher = await _verteilung(ds)
        await _verschiebe_kanal(ds, f"inv:{hw}:strom_heizen_kwh", 5, 0.25)
        nachher = await _verteilung(ds)
    seg = f"{hw}:heizen"
    tag_vorher = {s.schluessel: s.kwh for s in vorher.segmente}
    assert {s.schluessel: s.kwh for s in nachher.segmente} == tag_vorher
    assert [p.kwh_je_segment.get(seg, 0.0) for p in vorher.perioden] == pytest.approx([0.25] * 24)
    stunden = [p.kwh_je_segment.get(seg, 0.0) for p in nachher.perioden]
    assert (stunden[5], stunden[6]) == pytest.approx((0.5, 0.0))
    assert sum(stunden) == pytest.approx(tag_vorher[seg])
