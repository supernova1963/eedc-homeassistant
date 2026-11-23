"""Fund-Päckchen G (23.11.2026) — Proben je Punkt.

G1: Wetter und Börsenpreis eines Tages bleiben wie gespeichert, wenn der Abruf beim Neu-Aggregieren nichts liefert; liefert
er einen Wert, gewinnt der (je Feld, je Stunde). Harness: der echte ``aggregate_day`` mit den Attrappen der N-595-Proben.
G2: Befund «Summe beginnt neu, Stand läuft weiter» (``ha_zaehlerstand_springt``). G3: Heimladungs-Anteil ohne Bündelstunde.
NG1 (Nachtrag G): dieselbe Regel an allen Schreibern — Kanal-Tag, Bestandsweg (auch an den Umstellungstagen der
Laufzeitzone), abgeleiteter Kanal (Harness von test_kanal_abgeleitet.py).

Schwesterdateien: test_funde_f.py, test_n595_neu_aggregieren_rettet_stundenwerte.py (P9: Börse bleibt bei leerem Abruf),
test_konformitaet_tep_felder.py (Klasse (d)), test_sensorwechsel_u2c_proben.py (``ha_zaehlerstand_springt``).
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.tests.test_n595_neu_aggregieren_rettet_stundenwerte import TAG, _aufbau, _lauf, _umgebung

_TZ_ABRUF = ("temperatur_min_c", "temperatur_max_c", "strahlung_summe_wh_m2", "gti_summe_wh_m2",
             "boersenpreis_avg_cent", "boersenpreis_min_cent", "negative_preis_stunden")
_TEP_ABRUF = ("temperatur_c", "globalstrahlung_wm2", "bewoelkung_prozent", "niederschlag_mm", "wetter_code",
              "boersenpreis_cent")


def _wetter(temp: float, ghi: float = 100.0, gti: float | None = 150.0) -> dict:
    return {h: {"temperatur_c": temp + h, "globalstrahlung_wm2": ghi, "gti_wm2": gti, "bewoelkung_prozent": 40.0,
                "niederschlag_mm": 0.1, "wetter_code": 3} for h in range(24)}


@contextmanager
def _abruf(wetter: dict, boerse: dict):
    with _umgebung(boerse=boerse), patch("backend.services.energie_profil._helpers._get_wetter_ist",
                                         new=AsyncMock(return_value=wetter)):
        yield


async def _stand(db, anlage):
    zeilen = await _lauf(db, anlage)
    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == TAG))).scalar_one()
    return ({h: {k: getattr(z, k) for k in _TEP_ABRUF} for h, z in zeilen.items()},
            {k: getattr(tz, k) for k in _TZ_ABRUF})


@pytest.mark.asyncio
async def test_g1_leerer_abruf_laesst_wetter_und_boerse_stehen(db):
    anlage, _, _ = await _aufbau(db)
    boerse = {h: (-1.0 if h == 12 else 5.0) for h in range(24)}
    with _abruf(_wetter(10.0), boerse):
        std_1, tz_1 = await _stand(db, anlage)
    assert tz_1["temperatur_max_c"] is not None and tz_1["gti_summe_wh_m2"] and tz_1["negative_preis_stunden"] == 1, tz_1
    assert std_1[12]["boersenpreis_cent"] == -1.0 and std_1[13]["temperatur_c"] == 23.0, std_1

    with _abruf({}, {}):                                   # ohne Netz: beide Abrufe leer
        std_2, tz_2 = await _stand(db, anlage)
    assert std_2 == std_1
    assert tz_2 == tz_1


@pytest.mark.asyncio
async def test_g1_abruf_gewinnt_wo_er_liefert_je_feld(db):
    anlage, _, _ = await _aufbau(db)
    with _abruf(_wetter(10.0), {h: 5.0 for h in range(24)}):
        std_1, tz_1 = await _stand(db, anlage)

    # Neuer Abruf: Temperatur neu, GTI fehlt (Teil-Fan-out), Börse nur für Stunde 12.
    with _abruf(_wetter(20.0, gti=None), {12: 7.0}):
        std_2, tz_2 = await _stand(db, anlage)
    assert std_2[13]["temperatur_c"] == 33.0                   # Abruf gewinnt
    assert std_2[12]["boersenpreis_cent"] == 7.0               # Abruf gewinnt
    assert std_2[13]["boersenpreis_cent"] == 5.0               # nichts geliefert ⇒ gespeichert
    assert tz_2["gti_summe_wh_m2"] == tz_1["gti_summe_wh_m2"]  # keine Stunde mit GTI ⇒ gespeicherte Tagessumme
    assert tz_2["temperatur_max_c"] != tz_1["temperatur_max_c"]


# ═══════════════════════════════════════════════════════════════════════════
#  G2 — «Summe beginnt neu, Stand läuft weiter» (Befund ha_zaehlerstand_springt)
# ═══════════════════════════════════════════════════════════════════════════

def _km_zeilen():
    """Wie die Produktiv-Kopie: Lücke 17.02. 06:00 → 10.05. 06:00, danach beginnt die Summe bei 0, der Stand läuft weiter."""
    from datetime import datetime as dt
    t = lambda *a: int(dt(*a).timestamp())  # noqa: E731
    return [(t(2025, 2, 17, 5), 10152.0, 2140.0), (t(2025, 2, 17, 6), 10152.0, 2140.0),
            (t(2025, 5, 10, 6), 12057.0, 0.0), (t(2025, 5, 10, 9), 12062.0, 5.0), (t(2025, 5, 10, 21), 12076.0, 19.0)]


def test_g2_kern_summe_neu_stand_laeuft_weiter():
    from backend.core.berechnungen.zaehlerstand_sprung import SUMME_NEU, finde_summe_neu

    funde = finde_summe_neu(_km_zeilen())
    assert [(f.art, f.menge, f.stand_vorher, f.stand_nachher) for f in funde] == [(SUMME_NEU, 1905.0, 10152.0, 12057.0)]
    # Monats-Reset eines Zählers (Ladevorgänge): der Stand fällt, die Summe bleibt — kein Fall.
    assert finde_summe_neu([(0, 22.0, 80.0), (3600, 0.0, 80.0), (7200, 1.0, 81.0)]) == []
    # Gewöhnlicher Betrieb: Δ sum = Δ state.
    assert finde_summe_neu([(0, 100.0, 50.0), (3600, 120.0, 70.0)]) == []


def test_g2_befund_nennt_tag_und_beide_zahlen_nur_am_km_feld():
    from backend.services.daten_checker.datenquelle.standsprung import _zeile, finde

    def sql_zeilen(kid, key):
        return [(kid, key, "stand", "km", 0, "sensor.km", ts, st, su) for ts, st, su in _km_zeilen()]

    funde = finde(sql_zeilen(3, "inv:1:km_gefahren") + sql_zeilen(6, "inv:2:ladevorgaenge"))
    assert [(f.key, f.summe_neu, f.tag_stand, f.tag_summe) for f in funde] == [("inv:1:km_gefahren", True, 1924.0, 19.0)]
    text = _zeile(funde[0], {"inv:1:km_gefahren": "Smart · Gefahrene km"})
    assert "am 10.05.2025, Stunde ab 06:00: am Tag Stand +1.924 km, Summe der Statistik +19 km" in text, text


# ═══════════════════════════════════════════════════════════════════════════
#  G3 — Heimladung an einer gebündelten Stunde (Grenze G-5 des Bauplans N-799)
# ═══════════════════════════════════════════════════════════════════════════

def _ks_stillstand():
    """Ein Kanal-Tag wie der 12.11.2026 der Produktiv-Kopie: Stillstand 06–16 Uhr, Nachtrag 17 Uhr mit der ganzen Ladung."""
    from datetime import date as d
    from types import SimpleNamespace

    from backend.services.kanal.stunden_adapter import KanalStunden

    def zeile(h, ladung=0.0, netz=0.0, einsp=0.0):
        return SimpleNamespace(stunde=h, wallbox_kw=ladung, netzbezug_kw=netz, einspeisung_kw=einsp, batterie_kw=0.0,
                               spannen=None)
    zeilen = tuple(zeile(h) for h in range(17)) + (zeile(17, ladung=24.195, netz=9.4, einsp=8.3),) + tuple(
        zeile(h) for h in range(18, 24))
    return KanalStunden(datum=d(2026, 11, 12), zeilen=zeilen, felder=frozenset({"wallbox_kw"}), klemm_stunden=())


def _fenster_1211():
    from datetime import datetime as dt

    from backend.core.berechnungen.spannen import StillstandFenster

    return (StillstandFenster(von_ts=int(dt(2026, 11, 12, 6).timestamp()), nachtrag_ts=int(dt(2026, 11, 12, 17).timestamp()),
                              k=11, achsen=frozenset({"pv", "netzbezug", "einspeisung", "wallbox"})),)


def test_g3_nachtragsstunde_eines_stillstands_traegt_keinen_anteil():
    """Schreiber der Tageszeile am Kanal-Tag: die Nachtragsstunde (Marke über ``Weiche.kanal_stunde_ohne_ladeanteil``) geht
    wie jede Bündel-Stunde als «nicht gedeckt» ein; trägt der Tag keine gedeckte Ladestunde, bleibt der Anteil leer."""
    from backend.services.energie_profil.kanal_stunden import ladeanteil_der_kanal_stunden
    from backend.services.energie_profil.mengen_weiche import KEINE_WEICHE, Weiche

    ks = _ks_stillstand()
    vorher = ladeanteil_der_kanal_stunden(ks, ohne_anteil=KEINE_WEICHE.kanal_stunde_ohne_ladeanteil)
    assert vorher is not None and vorher.pv_kwh > 0 and vorher.stunden_gedeckt == 1   # ohne Marke: als eine Stunde bewertet
    assert ladeanteil_der_kanal_stunden(ks) == vorher
    weiche = Weiche(stillstand=_fenster_1211(), datum=ks.datum)
    assert weiche.kanal_stunde_ohne_ladeanteil(17) and weiche.kanal_stunde_ohne_ladeanteil(10)
    assert not weiche.kanal_stunde_ohne_ladeanteil(18) and not weiche.kanal_stunde_ohne_ladeanteil(5)
    assert ladeanteil_der_kanal_stunden(ks, ohne_anteil=weiche.kanal_stunde_ohne_ladeanteil) is None   # keine Aussage
    assert ks.zeilen[17].spannen is None                      # die gemerkten Adapter-Zeilen bleiben unberührt


# ═══════════════════════════════════════════════════════════════════════════
#  Nachtrag G (NG1) — dieselbe Regel an allen Schreibern des Heimladungs-Anteils
# ═══════════════════════════════════════════════════════════════════════════

def test_ng1_die_eine_regel():
    """``spannen.stillstand_ohne_ladeanteil``: Nachtragsstunde und Nullstunden ja, Stunden außerhalb nein; ein gesperrtes
    Fenster (nur Befund) und eine Marke nur auf Achsen ohne Ladeanteil (Speicher, Einspeisung) nein."""
    import dataclasses

    from backend.core.berechnungen.spannen import stillstand_ohne_ladeanteil

    (f,) = _fenster_1211()
    assert stillstand_ohne_ladeanteil([f], (f.nachtrag_ts,)) and stillstand_ohne_ladeanteil([f], (f.von_ts + 3600,))
    assert not stillstand_ohne_ladeanteil([f], (f.nachtrag_ts + 3600,)) and not stillstand_ohne_ladeanteil([f], (f.von_ts - 3600,))
    assert not stillstand_ohne_ladeanteil([dataclasses.replace(f, sperre="grob")], (f.nachtrag_ts,))
    assert not stillstand_ohne_ladeanteil([dataclasses.replace(f, achsen=frozenset({"batterie", "einspeisung"}))],
                                          (f.nachtrag_ts,))
    assert not stillstand_ohne_ladeanteil([], (f.nachtrag_ts,))


def _umstellungstage(jahr: int = 2026):
    """Die Tage des Jahres mit 23 bzw. 25 echten Stunden in der Zeitzone des Laufs (Berlin: 29.03./25.10.; Auckland:
    05.04./27.09.; UTC: keine)."""
    from datetime import date as d, datetime as dt, timedelta as td

    out = {}
    tag = d(jahr, 1, 1)
    while tag.year == jahr:
        n = round((dt.combine(tag + td(days=1), dt.min.time()).timestamp()
                   - dt.combine(tag, dt.min.time()).timestamp()) / 3600)
        if n != 24:
            out[tag + td(days=1)] = n       # Bestandstag D trägt [D−1 23:00, D 23:00): die Umstellung liegt an D − 1 … D
            out[tag] = n
        tag += td(days=1)
    return out


def test_ng1_echte_stunden_der_bestandsslots_jeden_tag():
    """Bestandsweg: die Slots 0 … 23 eines Tages tragen zusammen genau die echten Stunden [Vortag 23:00, 23:00), jede
    einmal — an jedem Tag des Jahres, auch an den Umstellungstagen der Laufzeitzone (Herbst: ein Slot trägt beide Zeilen
    der doppelten Wanduhr; Frühjahr: ein Slot trägt keine)."""
    from datetime import date as d, datetime as dt, timedelta as td

    from backend.core.berechnungen.slot_konvention import echte_stunden_des_slots

    tag = d(2026, 1, 1)
    while tag.year == 2026:
        slots = [echte_stunden_des_slots(tag, s) for s in range(24)]
        alle = [ts for st in slots for ts in st]
        von = int(dt.combine(tag - td(days=1), dt.min.time()).replace(hour=23).timestamp())
        bis = int(dt.combine(tag, dt.min.time()).replace(hour=23).timestamp())
        assert alle == list(range(von, bis, 3600)), tag
        assert sorted(len(st) for st in slots) == sorted([1] * 24 if len(alle) == 24 else
                                                         ([0] + [1] * 23 if len(alle) == 23 else [2] + [1] * 23)), tag
        tag += td(days=1)
    assert echte_stunden_des_slots(d(2026, 7, 2), 18) == (int(dt(2026, 7, 2, 17).timestamp()),)


def _verrechne_tag(weiche, datum, ladung_slot: int):
    """Die Stunden-Schleife des Aggregators (``verrechne_stunde``, Bestandsweg) über einen Tag: Ladung nur im Slot
    ``ladung_slot`` (24,195 kWh, Netz 9,4, Einspeisung 8,3), sonst 0 — wie der 12.11.2026 ohne PV-Ladezähler."""
    from types import SimpleNamespace

    from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab
    from backend.services.energie_profil.aggregator import (
        StundenKontext, TagesAkkumulator, Wetterstunde, Zaehlerstunde, verrechne_stunde,
    )

    kontext = StundenKontext(anlage=None, datum=datum, netz_keys=set(), pv_keys=set(), sonderschluessel=set(),
                             kwh_pro_stunde={}, kwh_source_label="", wetter_stunden={}, soc_stunden={}, soc_je_stunde={},
                             betriebsmodus_je_stunde={}, strompreis_stunden=SimpleNamespace(sensor={}, boerse={}),
                             wp_starts_pro_stunde={}, wp_betriebsstunden_pro_stunde={}, weiche=weiche)
    akku = TagesAkkumulator()
    for h in range(24):
        laedt = h == ladung_slot
        z = Zaehlerstunde(pv_kw=10.0 if laedt else 0.0, sonstige_erz_kw=None, einspeisung_kw=8.3 if laedt else 0.0,
                          netzbezug_kw=9.4 if laedt else 0.0, verbrauch_kw=None, waermepumpe_kw=None,
                          wallbox_kw=24.195 if laedt else 0.0, batterie_kw=0.0)
        verrechne_stunde(h, z, Wetterstunde(None, None, None, None, None, None), kontext, akku)
    return leite_pv_anteil_ab(akku.lade_stunden)


def test_ng1_bestandsweg_nachtragsstunde_traegt_keinen_anteil():
    """(ii) ``aggregator.verrechne_stunde``: der Backward-Slot 18 trägt die Stunde ab 17:00 — mit der Marke des Stillstands
    keine gedeckte Ladestunde, der Anteil bleibt leer (keine Aussage, nicht 0 kWh PV); ohne Weiche wie bisher."""
    from datetime import date as d

    from backend.services.energie_profil.mengen_weiche import KEINE_WEICHE, Weiche

    tag = d(2026, 11, 12)
    ohne = _verrechne_tag(KEINE_WEICHE, tag, 18)
    assert ohne is not None and ohne.pv_kwh > 0 and ohne.stunden_gedeckt == 1
    weiche = Weiche(stillstand=_fenster_1211(), datum=tag)
    assert [s for s in range(24) if weiche.slot_ohne_ladeanteil(s)] == list(range(7, 19))   # 06:00 … 17:00
    assert _verrechne_tag(weiche, tag, 18) is None
    assert _verrechne_tag(weiche, tag, 19) == ohne               # die Stunde danach ist eine gewöhnliche


def test_ng1_bestandsweg_an_den_umstellungstagen():
    """(ii) an den Umstellungstagen der Laufzeitzone: eine Nachtragsstunde an der doppelten Wanduhr (Herbst, zweite
    Zeile) bzw. die erste Stunde nach der fehlenden (Frühjahr) markiert genau den Slot, der sie trägt."""
    from datetime import date as d, datetime as dt

    from backend.core.berechnungen.slot_konvention import echte_stunden_des_slots
    from backend.core.berechnungen.spannen import StillstandFenster
    from backend.services.energie_profil.mengen_weiche import Weiche

    for tag in _umstellungstage():
        slots = [echte_stunden_des_slots(tag, s) for s in range(24)]
        for s, stunden in enumerate(slots):
            for ts in stunden:                                      # Nachtrag an jeder echten Stunde des Tages
                f = StillstandFenster(von_ts=ts - 2 * 3600, nachtrag_ts=ts, k=2, achsen=frozenset({"wallbox"}))
                w = Weiche(stillstand=(f,), datum=tag)
                assert w.slot_ohne_ladeanteil(s), (tag, s, dt.fromtimestamp(ts))
                treffer = [x for x in range(24) if w.slot_ohne_ladeanteil(x)]
                assert all(any(f.von_ts <= t <= f.nachtrag_ts for t in slots[x]) for x in treffer), (tag, s, treffer)
    assert d(2026, 1, 1) not in _umstellungstage()


# (i) — der abgeleitete Kanal (Harness der E4c-Proben)
from backend.tests.test_kanal_abgeleitet import ZEIT, _abgeleitet, _anlage, _laeufe, _ts, ha  # noqa: E402,F401


@pytest.mark.asyncio
async def test_ng1_abgeleiteter_kanal_nachtragsstunde_ohne_pv_teil(db, ha):  # noqa: F811
    """(i) ``kanal/abgeleitet.schreibe_abgeleitete``: ohne Stillstand PV 1,2 je Stunde 04:00/05:00 (Summe 2,4); trägt 04:00
    die Marke (Nachtrag eines Stillstands 02:00–03:00), schreibt der Kanal dort keinen PV-Teil — der Stand bleibt, die
    Ladung zählt im Anteil zum Netz (die Regel einer Stunde ohne Aussage im Kanal)."""
    from datetime import timedelta as td

    from backend.core.berechnungen.spannen import StillstandFenster

    f = StillstandFenster(von_ts=_ts(ZEIT + td(hours=2)), nachtrag_ts=_ts(ZEIT + td(hours=4)), k=2,
                          achsen=frozenset({"netzbezug", "wallbox"}))
    a, wb, _ = await _anlage(db)
    with patch("backend.services.kanal.stillstand.fenster_im_bereich", new=AsyncMock(return_value=[f])):
        await _laeufe(db, a, ha, range(1, 8))
    _k, z = await _abgeleitet(db, a.id, wb.id)
    assert z[_ts(ZEIT + td(hours=4))] == pytest.approx(0.0)       # 04:00: Nachtragsstunde ohne PV-Teil
    assert z[_ts(ZEIT + td(hours=5))] == pytest.approx(1.2)       # 05:00 wie ohne Stillstand
    assert z[_ts(ZEIT + td(hours=6))] == pytest.approx(1.2)


# ═══════════════════════════════════════════════════════════════════════════
#  Nachtrag G (NG3) — keine Löschfrist für die Stundenzeilen
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ng3_nachtlauf_loescht_keine_alten_stundenzeilen(db):
    """Gernot 23.11.2026: Werte aus Quellen ohne Historie werden nicht still gelöscht. Nach dem Vortags-Lauf
    (``aggregate_yesterday_all``) stehen Stundenzeilen, die älter als 730 Tage sind, noch da (bis 4.3.1 gelöscht)."""
    from contextlib import asynccontextmanager
    from datetime import date as d, timedelta as td

    from sqlalchemy import func

    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.energie_profil import scheduler_jobs
    from backend.tests import factories

    fest = d(2026, 11, 23)

    class _FesterTag(d):      # der Lauf liest ``date.today()`` — die Probe stellt ihn fest (keine echte Uhr)
        @classmethod
        def today(cls):
            return cls(fest.year, fest.month, fest.day)

    a = await factories.anlage(db)
    alt = fest - td(days=900)
    db.add_all([TagesEnergieProfil(anlage_id=a.id, datum=alt, stunde=h, temperatur_c=5.0, betriebsmodus_je_wp=None)
                for h in range(24)])
    await db.commit()

    @asynccontextmanager
    async def _sitzung():
        yield db

    with patch.object(scheduler_jobs, "get_session", _sitzung), patch.object(scheduler_jobs, "date", _FesterTag), \
            patch.object(scheduler_jobs, "aggregate_day", new=AsyncMock(return_value=None)):
        erg = await scheduler_jobs.aggregate_yesterday_all()
    assert erg[a.id]["status"] == "keine_daten"
    n = (await db.execute(select(func.count()).select_from(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == a.id, TagesEnergieProfil.datum == alt))).scalar()
    assert n == 24
