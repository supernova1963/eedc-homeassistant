"""Fund-Päckchen G (23.11.2026) — Proben je Punkt.

G1: Wetter und Börsenpreis eines Tages bleiben wie gespeichert, wenn der Abruf beim Neu-Aggregieren nichts liefert; liefert
er einen Wert, gewinnt der (je Feld, je Stunde). Harness: der echte ``aggregate_day`` mit den Attrappen der N-595-Proben.
G2: Befund «Summe beginnt neu, Stand läuft weiter» (``ha_zaehlerstand_springt``). G3: Heimladungs-Anteil ohne Bündelstunde.

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


@pytest.mark.asyncio
async def test_g3_nachtragsstunde_eines_stillstands_traegt_keinen_anteil(db):
    from datetime import datetime as dt

    from backend.core.berechnungen.spannen import StillstandFenster
    from backend.services.energie_profil.kanal_stunden import ladeanteil_der_kanal_stunden
    from backend.services.energie_profil.stillstand_marke import kanal_stunden_mit_marke

    ks = _ks_stillstand()
    vorher = ladeanteil_der_kanal_stunden(ks)
    assert vorher is not None and vorher.pv_kwh > 0 and vorher.stunden_gedeckt == 1   # ohne Marke: als eine Stunde bewertet
    fenster = [StillstandFenster(von_ts=int(dt(2026, 11, 12, 6).timestamp()), nachtrag_ts=int(dt(2026, 11, 12, 17).timestamp()),
                                 k=11, achsen=frozenset({"pv", "netzbezug", "einspeisung", "wallbox"}))]
    with patch("backend.services.kanal.stillstand.fenster_im_bereich", new=AsyncMock(return_value=fenster)):
        markiert = await kanal_stunden_mit_marke(db, 1, ks.datum, ks)
    assert markiert.zeilen[17].spannen["wallbox"] == 12 and markiert.zeilen[10].spannen["wallbox"] == 0
    assert ks.zeilen[17].spannen is None                      # die gemerkten Adapter-Zeilen bleiben unberührt
    assert ladeanteil_der_kanal_stunden(markiert) is None      # keine gedeckte Ladestunde ⇒ keine Aussage (nicht 0 kWh PV)
    with patch("backend.services.kanal.stillstand.fenster_im_bereich", new=AsyncMock(return_value=[])):
        assert await kanal_stunden_mit_marke(db, 1, ks.datum, ks) is ks
