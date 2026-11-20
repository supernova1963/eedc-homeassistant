"""Sensorwechsel — Korrekturrunde U3-K (Nachmessung ``opus-berichte/SENSORWECHSEL-U3-NACHMESSUNG-2026-11-20.md`` B1–B8, Bauplan
Nr. 158/159) — Proben mit Sprengsatz.

* **B1** «Zähler getauscht» über MQTT mit mehreren Höhenwechseln in einer Stunde: die Rand-Stände sind der letzte Stand vor
  dem ersten und der erste nach dem letzten Höhenwechsel (``rohstand_rand.sprung_der_stunde``) — 11,917 · 11,875 · 11,917 in
  Kanal, Reihe und Tagesansicht, nachgetragen und im Stundenlauf; eine negative Menge der Naht wird abgelehnt, nie geschrieben.
* **B2** «Zählerstand springt» (HA und MQTT): der Arm «Sprung» meldet nur bei reifem Bezug oder über der Grenze «mehr, als eine
  Anlage in einer Stunde leisten kann» — die fünf Gegenfälle der Nachmessung schweigen, die Lab-Sprünge melden weiter.
* **B7** Höhenwechsel nach Leistung: eine gewöhnliche Ladung nach Standby und eine Nachholmenge nach Stille sind keiner.
* **B3** «kurz tiefer und zurück» nur bis 10 %; **B4** Arm «Zwischenstand» (kurz 0 oder ein fremder Stand in der Stunde).
* **B5** ``monatswert_ueberholt`` nur bis zum Monat des Eintrags (``zuordnung_wechsel.eingetragen_ts``).
* **B6** fehlende Proben: Verdrahtung der Stillstand-Abgrenzung, Rest-Schritt «jüngster», MQTT-Stand-Kanal.

Zeitpunkte im Juni (fern jeder Umstellung); die Datei liest keine Uhr und läuft auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``.
Schwesterdateien: test_sensorwechsel_u3b_proben.py (Saat, Leser), test_sensorwechsel_u2c_proben.py (Kern HA),
test_sensorwechsel_u3a_proben.py (G1/G2/G8), test_n799_s3_befund.py (Stillstand).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from backend.core.berechnungen import zaehlerstand_sprung as zs
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.tests.test_sensorwechsel_u3b_proben import (  # noqa: F401 — Saat, Leser und Anlage der U3b-Proben
    BASIS, E, K0, KE, NETZ, RATE, TAG_E, Saat, _anlage, _g4, _g4_anlage, _kanal_zeilen, _wechsel_zeilen, betrieb, getauscht,
    kanal_stunde, kanal_tag, reihe_tag, tagesansicht, zw,
)

FRUEH = datetime(2026, 5, 19)              # 20 Tage Vorlauf vor dem Ereignis (der Zähler ist nicht «jung»)
TAGE = [TAG_E, TAG_E + timedelta(days=1)]


def w(t: datetime, rate: float = RATE) -> float:
    return round(BASIS + rate * (t.timestamp() - FRUEH.timestamp()) / 3600, 6)


async def _alle(db, aid, tage=TAGE):
    return ([await kanal_tag(db, aid, d) for d in tage], [await reihe_tag(db, aid, d) for d in tage],
            await tagesansicht(db, aid, tage))


async def _pruefe(db, aid, zeit):
    from backend.api.routes import sensorwechsel as sw

    return await sw.pruefe_zaehler_getauscht(aid, "basis_energy_netzbezug_kwh", sw.ZaehlerGetauschtRequest(getauscht_am=zeit), db)


def _null_5min(t):
    return 0.0 if E <= t < E + timedelta(minutes=5) else w(t)


def _fremd_10min(t):
    return 300.0 if E <= t < E + timedelta(minutes=10) else w(t)


def _null_dann_300(t):
    if t < E:
        return w(t)
    return 0.0 if t < E + timedelta(minutes=5) else 300.0 + w(t) - w(E)


def _einzelpaar(roh, stunde, grenze_kw=None):
    """Sprengsatz B1: wie U3 b — ein einziges Paar, das mit dem größten Betrag."""
    from backend.core.berechnungen import rohstand_rand as rr

    idx = rr.hoehenwechsel_der_stunde(roh, stunde, grenze_kw)
    if not idx:
        return None
    i = max(idx, key=lambda j: abs(roh[j][1] - roh[j - 1][1]))
    return roh[i - 1], roh[i]


# ═══ B1 — zwei Höhenwechsel in einer Stunde ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_einzelpaar"])
@pytest.mark.parametrize("stand,soll,zeit", [(_null_5min, 11.917, "10:25"), (_fremd_10min, 11.875, "10:30"),
                                              (_null_dann_300, 11.917, "10:25")],
                         ids=["null_5min", "fremd_10min", "null_dann_300"])
async def test_b1_spanne_der_hoehenwechsel_kanal_reihe_tagesansicht(db, monkeypatch, stand, soll, zeit, sprengsatz):
    from backend.core.berechnungen import rohstand_rand
    from backend.services.zuordnung_wechsel import rohstand

    if sprengsatz:
        monkeypatch.setattr(rohstand, "sprung_der_stunde", _einzelpaar)
        monkeypatch.setattr(rohstand_rand, "sprung_der_stunde", _einzelpaar)
    aid = (await _anlage(db)).id
    antw = await betrieb(db, aid, Saat(stand, start=FRUEH, spaet=[getauscht(E)]))
    p = antw[0]["pruefen"]
    k, r, t = await _alle(db, aid)
    if sprengsatz:
        assert k[0] != pytest.approx(soll, abs=0.001)
        return
    assert p["weg"] == "fortsetzung" and p["getauscht_am"] == f"2026-06-08T{zeit}:00"
    assert (k[0], r[0], t[0]) == (pytest.approx(soll, abs=0.001),) * 3
    assert (k[1], r[1], t[1]) == (pytest.approx(12.0),) * 3


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_spanne_im_stundenlauf"])
async def test_b1_stundenlauf_teilt_an_der_spanne(db, monkeypatch, sprengsatz):
    """Eingetragen um 10:42, bevor der Stundenlauf die Stunde schreibt: der Lauf teilt am ersten Stand nach dem letzten
    Höhenwechsel (10:30) und beendet die alte Periode am letzten Stand vor dem ersten (10:15) — die fremden Stände dazwischen
    zählen nicht. Sprengsatz: Rand wie U3 b (letzter Stand vor 10:30 = 300) ⇒ die alte Periode zählt den fremden Stand."""
    from backend.services.zuordnung_wechsel import rohstand

    if sprengsatz:
        monkeypatch.setattr(rohstand, "rand_der_naht", rohstand.rand_um)
    t = E + timedelta(minutes=22)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_fremd_10min, start=FRUEH, handlungen=[(t, getauscht(E))]))
    k, r, ta = await _alle(db, aid)
    if sprengsatz:
        assert k[0] != pytest.approx(11.875, abs=0.001)
        return
    w_ = (await _wechsel_zeilen(db, aid))[0]
    assert w_.erklaert_ts == E + timedelta(minutes=10) and w_.stand_alt_ende == pytest.approx(w(E - timedelta(minutes=5)))
    assert (k[0], r[0], ta[0]) == (pytest.approx(11.875, abs=0.001),) * 3


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_ablehnung"])
async def test_b1_negative_menge_wird_abgelehnt(db, monkeypatch, sprengsatz):
    """Ergäbe ein Eintrag eine negative Stunde (hier mit dem Einzelpaar von U3 b nachgestellt), lehnt die Prüfung ab: kein
    Eintrag, der Satz nennt die Zahl und den Weg. Sprengsatz: ohne die Ablehnung in der Prüfung ⇒ «Eintragen» angeboten (der
    Nachtrag selbst schreibt die negative Stunde trotzdem nicht: ``naht.nachtrag_fortsetzung`` wirft)."""
    from backend.services.zuordnung_wechsel import rohstand
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    from fastapi import HTTPException

    monkeypatch.setattr(rohstand, "sprung_der_stunde", _einzelpaar)
    if sprengsatz:
        monkeypatch.setattr(zg, "WEG_NEGATIV", zg.WEG_FORTSETZUNG)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_null_5min, start=FRUEH))
    vorher = await kanal_tag(db, aid, TAG_E)
    p = await _pruefe(db, aid, E)
    if sprengsatz:
        assert p["eintragen"] is True
        with pytest.raises(HTTPException):                   # der Nachtrag wirft, die Route rollt zurück (422)
            await getauscht(E)(db, aid)
    else:
        assert (await getauscht(E)(db, aid))["eintragen"]["eingetragen"] is False
    assert await _wechsel_zeilen(db, aid) == [] and await kanal_tag(db, aid, TAG_E) == pytest.approx(vorher)
    if sprengsatz:
        return
    assert p["weg"] == "negative_menge" and p["eintragen"] is False
    assert p["saetze"] == ["Nach einem Eintrag um 08.06.2026 10:25 Uhr zählte die Stunde ab 08.06.2026 10:00 Uhr -5.244,71 kWh "
                           "— weniger als nichts. Die Zählerstände dieser Stunde passen nicht zu einem Tausch um diese Zeit, "
                           "eedc trägt nichts ein. Wähle unter „Getauscht am“ die Zeit, zu der der Stand springt; der "
                           "Daten-Checker nennt sie unter „Zählerstand springt (MQTT)“."]


def test_b1_regel_spanne_rein():
    """Die Auswahl unter mehreren Höhenwechseln (B6, Mutant N21): erster und letzter, nicht der größte."""
    from backend.core.berechnungen.rohstand_rand import sprung_der_stunde

    t0 = datetime(2026, 6, 8, 9)
    roh = [(t0 + timedelta(minutes=5 * i), 100.0 + 0.04 * i) for i in range(16)]       # bis 10:15
    roh += [(datetime(2026, 6, 8, 10, 20), 300.0), (datetime(2026, 6, 8, 10, 25), 300.0),
            (datetime(2026, 6, 8, 10, 30), 100.7), (datetime(2026, 6, 8, 10, 35), 100.74)]
    a, b = sprung_der_stunde(roh, datetime(2026, 6, 8, 10), 100.0)
    assert (a[0], b[0]) == (datetime(2026, 6, 8, 10, 15), datetime(2026, 6, 8, 10, 30))
    assert sprung_der_stunde(roh, datetime(2026, 6, 8, 9), 100.0) is None


async def test_b1_nachtrag_schreibt_nie_eine_negative_stunde(db):
    from backend.services.kanal.naht import nachtrag_fortsetzung

    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(lambda t: w(t), start=datetime(2026, 6, 8), ende=datetime(2026, 6, 8, 12)))
    kid = (await db.execute(text("SELECT id FROM kanal WHERE key = :k"), {"k": NETZ})).scalar_one()
    with pytest.raises(ValueError):
        await nachtrag_fortsetzung(db, kid, int(datetime(2026, 6, 8, 10).timestamp()), rand=(0.0, 9999.0))


# ═══ B2 — «Zählerstand springt» nur bei reifem Bezug oder über der Grenze ═════════════════════════════════════════════

def _reihe(beginn, ende, rate, start=100.0):
    z, stand, summe, t = [], start, 0.0, beginn
    while t < ende:
        r = rate(t)
        if r is not None:
            stand += r
            summe += r
            z.append((int(t.timestamp()), round(stand, 6), round(summe, 6)))
        t += timedelta(hours=1)
    return list({ts: (ts, st, su) for ts, st, su in z}.values())


#: Die fünf Gegenfälle der Nachmessung (``nm-u3/kern_gegenfaelle.py``): gewöhnlicher Betrieb nach Wochen mit Standby.
GEGENFAELLE = {
    "wallbox": lambda: _reihe(datetime(2026, 9, 1), datetime(2026, 10, 12),
                              lambda t: 11.0 if datetime(2026, 10, 10, 18) <= t < datetime(2026, 10, 10, 22) else 0.005),
    "klima": lambda: _reihe(datetime(2025, 10, 15), datetime(2026, 5, 22),
                            lambda t: 1.2 if t >= datetime(2026, 5, 20, 12) and 12 <= t.hour < 18 else 0.003),
    "waermepumpe": lambda: _reihe(datetime(2026, 6, 1), datetime(2026, 10, 12),
                                  lambda t: 2.5 if t >= datetime(2026, 10, 10, 5) else 0.008),
    "pv_schnee": lambda: _reihe(datetime(2026, 12, 1), datetime(2026, 12, 24),
                                lambda t: (4.0 if t >= datetime(2026, 12, 22) else 0.02) if 9 <= t.hour < 15 else 0.0),
    "steckdose": lambda: _reihe(datetime(2026, 9, 1), datetime(2026, 9, 23),
                                lambda t: 0.9 if t == datetime(2026, 9, 21, 10) else 0.001),
}


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_b2"])
@pytest.mark.parametrize("fall", sorted(GEGENFAELLE))
def test_b2_gegenfaelle_still(monkeypatch, fall, sprengsatz):
    if sprengsatz:                                   # die Regel vor U3-K: jeder Bezug mit 14 Tagen gilt als reif
        monkeypatch.setattr(zs, "reif", lambda n, g, e, t: n >= zs.BEZUG_MIN_TAGE)
    funde = zs.finde_standspruenge(GEGENFAELLE[fall](), grenze=zs.MENGE_UNMOEGLICH_MIN)
    assert (len(funde) > 0) == sprengsatz


@pytest.mark.parametrize("tag_kwh", [6.85, 24.0, 160.0])
def test_b2_lab_spruenge_melden_weiter(tag_kwh):
    """Lab +2 001 (Rechenweg F12) an einem Zähler mit 40 Tagen: über der Grenze (b); Neubeginn bei 300 (Arm unverändert)."""
    beginn, tausch = datetime(2026, 10, 8), datetime(2026, 11, 17, 10)
    z = _reihe(beginn, tausch + timedelta(hours=30), lambda t: tag_kwh / 24 + (2001.0 if t == tausch else 0.0))
    (f,) = zs.finde_standspruenge(z, grenze=zs.MENGE_UNMOEGLICH_MIN)
    assert f.art == zs.SPRUNG and f.start_ts == int(tausch.timestamp())


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_reif_min_tag_0"])
def test_b2_reif_braucht_ein_jahr_und_einen_tag_ab_1_kwh(monkeypatch, sprengsatz):
    """(a): +40 kWh (unter der Grenze) meldet nur, wenn der Abschnitt ein Jahr zurückreicht und der größte Tag ≥ 1 kWh zählt."""
    if sprengsatz:
        monkeypatch.setattr(zs, "REIF_MIN_TAG", 0.0)
    tausch = datetime(2026, 11, 17, 10)

    def mit(rate, tage):
        return _reihe(tausch - timedelta(days=tage), tausch + timedelta(hours=3), lambda t: rate + (40.0 if t == tausch else 0.0))
    assert [f.art for f in zs.finde_standspruenge(mit(2.0 / 24, 400), grenze=100.0)] == [zs.SPRUNG]   # reif
    assert zs.finde_standspruenge(mit(2.0 / 24, 300), grenze=100.0) == []                               # kein Jahr
    assert (zs.finde_standspruenge(mit(0.5 / 24, 400), grenze=100.0) != []) == sprengsatz               # Tag 0,5 kWh


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_grenze_je_zeile"])
def test_b2_zeile_nach_zaehlerluecke_traegt_die_grenze_ihrer_stunden(monkeypatch, sprengsatz):
    """Produktiv-Kopie, PV 05.11.2025 18:00: nach 129 Stunden ohne Zeile führt HA 134,3 kWh in einer Zeile (die Menge der
    Lücke) — kein Sprung. Die Grenze gilt je Stunde der Zeile (wie ``schwelle_pv_einspeisung_stunde_kwh(…, spanne)``)."""
    if sprengsatz:
        monkeypatch.setattr(zs, "grenze_der_zeile", lambda g, z0, z1: g)
    beginn, luecke = datetime(2025, 10, 31), datetime(2025, 10, 31, 9)
    z = _reihe(beginn, luecke + timedelta(hours=1), lambda t: 0.12)
    nach = int((luecke + timedelta(hours=129)).timestamp())
    z.append((nach, z[-1][1] + 134.312, z[-1][2] + 134.312))
    assert (zs.finde_standspruenge(z, grenze=100.0) != []) == sprengsatz


async def _ha_anlage(db, zeilen, *, kwp=10.0, art="sum", einheit="kWh", key="basis:netzbezug"):
    from backend.models.anlage import Anlage
    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik

    a = Anlage(anlagenname="U3K", leistung_kwp=kwp)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key=key, einheit=einheit, art=art)
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=zeilen[0][0], familie=FAMILIE_SPIEGEL, statistic_id="sensor.x", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=su, familie=FAMILIE_SPIEGEL) for ts, st, su in zeilen])
    await db.commit()
    return a


async def _ha_befund(db, a):
    from backend.services.daten_checker.datenquelle.standsprung import ZaehlerstandSpringtChecks

    class _P(ZaehlerstandSpringtChecks):
        def __init__(self, d):
            self.db = d
    return await _P(db)._check_ha_zaehlerstand_springt(a)


@pytest.mark.parametrize("plus,kwp,art,einheit,soll", [
    (2001.0, 10.0, "sum", "kWh", 1), (120.0, 100.0, "sum", "kWh", 0), (200.0, 100.0, "sum", "kWh", 1),
    (2001.0, 10.0, "stand", "m³", 0)], ids=["lab_2001", "unter_1_5_kwp", "ueber_1_5_kwp", "gas_ohne_grenze"])
async def test_b2_erzeuger_ha_grenze_der_anlage(db, plus, kwp, art, einheit, soll):
    """Junger Abschnitt (40 Tage, 0,2 kWh je Stunde — Maß über 10): Grenze max(100, 1,5 × kWp) aus der Anlage; ein
    Stand-Zähler in m³ hat keine."""
    tausch = datetime(2026, 11, 17, 10)
    z = _reihe(datetime(2026, 10, 8), tausch + timedelta(hours=3), lambda t: 0.2 + (plus if t == tausch else 0.0))
    a = await _ha_anlage(db, z, kwp=kwp, art=art, einheit=einheit)
    assert len(await _ha_befund(db, a)) == soll


async def test_b2_erzeuger_ha_wallbox_nach_standby_still(db):
    a = await _ha_anlage(db, GEGENFAELLE["wallbox"]())
    assert await _ha_befund(db, a) == []


# ═══ B7 + B2 am Dialog — Höhenwechsel nach Leistung ═══════════════════════════════════════════════════════════════════

def test_b7_regel_leistung():
    from backend.core.berechnungen.rohstand_rand import hoehenwechsel

    fuenf = 300.0
    assert hoehenwechsel(-0.5, fuenf, 0.0, 100.0)                       # Rückgang immer
    assert not hoehenwechsel(1.833, fuenf, 0.006, 100.0)                # 22 kW nach Standby: unter 100 kW
    assert hoehenwechsel(9.0, fuenf, 0.5, 100.0)                        # 108 kW
    assert not hoehenwechsel(9.0, fuenf, 11.0, 100.0)                   # 10 × 11 kW davor
    assert hoehenwechsel(1.5, fuenf, 0.0, None)                         # ohne Grenze (andere Einheit): über 1 …
    assert not hoehenwechsel(0.9, fuenf, 0.0, None)                     # … sonst nicht


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_schritt_statt_leistung"])
async def test_b7_ladung_nach_standby_ist_kein_hoehenwechsel(db, monkeypatch, sprengsatz):
    """Wallbox über MQTT, 20 Tage Standby 5 W, dann 22 kW: G4 schweigt, und «Zähler getauscht» um 18:05 lehnt ab — vorher
    strich der Eintrag 1,833 kWh echten Verbrauch (66,105 → 64,272). Sprengsatz: die Regel von U3 b (Schritt über 1 kWh)."""
    from backend.core.berechnungen import rohstand_rand

    if sprengsatz:
        monkeypatch.setattr(rohstand_rand, "hoehenwechsel",
                            lambda d, s, g, gr: d < -0.01 or d > max(10 * g * s / 3600, 1.0))
    l0 = datetime(2026, 6, 8, 18)

    def stand(t):
        b = BASIS + 0.005 * (min(t, l0).timestamp() - FRUEH.timestamp()) / 3600
        if t > l0:
            b += 22.0 * min((t - l0).total_seconds(), 3 * 3600) / 3600
        return round(b, 6)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=FRUEH))
    vorher = await kanal_tag(db, aid, TAG_E)
    assert await _g4(db, await _a(db, aid)) == []
    antw = await getauscht(l0 + timedelta(minutes=5))(db, aid)
    if sprengsatz:
        assert antw["eintragen"]["eingetragen"] is True and await kanal_tag(db, aid, TAG_E) < vorher - 1.0
        return
    assert antw["pruefen"]["weg"] == "kein_sprung" and antw["eintragen"]["eingetragen"] is False
    assert antw["pruefen"]["saetze"][0].endswith("Einen kleinen Sprung nach oben, der wie Verbrauch aussieht, kann eedc nicht "
                                                 "von Verbrauch unterscheiden; er zählt als Menge dieser Stunde.")
    assert await kanal_tag(db, aid, TAG_E) == pytest.approx(vorher)


@pytest.mark.parametrize("stumm_h,weg", [(3, "kein_sprung"), (30, "kein_sprung")])
async def test_b7_nachholmenge_nach_stille(db, stumm_h, weg):
    """Publisher stumm, der Scheduler wiederholt den letzten Stand; um 10:20 kommt der wahre Stand. 3 h: 1,5 kWh — kein
    Höhenwechsel. Nach 30 h sind es 15 kWh; U3-K2 (P-2): die Leistung gilt über die Zeit seit dem letzten anderen Stand (0,5 kW,
    nicht 180 kW in fünf Minuten) — auch das ist kein Höhenwechsel (bis U3-K benannte Grenze; Probe der Regel in
    ``test_sensorwechsel_u3k2_proben.py``)."""
    def stand(t):
        return w(E - timedelta(hours=stumm_h)) if E - timedelta(hours=stumm_h) <= t < E else w(t)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=FRUEH))
    assert (await _pruefe(db, aid, E))["weg"] == weg


async def _a(db, aid):
    from backend.models.anlage import Anlage

    return (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()


# ═══ B3 / B4 — «kurz tiefer und zurück» nur bis 10 %, Arm «Zwischenstand» ═════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ausnahme_ohne_10_prozent"])
async def test_b3_halber_stand_eine_stunde_meldet_beide_stunden(db, monkeypatch, sprengsatz):
    """Ein anderes Gerät sendet eine Stunde lang den halben Stand (Tag 5 257,1 statt 12): G4 nennt den Neubeginn und den
    Sprung. Sprengsatz: die Ausnahme von U3 b (jedes Fallen und Zurück) ⇒ G4 schweigt."""
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        def alt(z):
            aus = set()
            for i in range(1, len(z) - 1):
                if z[i][1] < z[i - 1][1] <= z[i + 1][1]:
                    aus |= {int(z[i][0]), int(z[i + 1][0])}
            return aus
        monkeypatch.setattr(ms, "_kurz_tiefer", alt)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(lambda t: 0.5 * w(t) if E <= t < E + timedelta(hours=1) else w(t), start=FRUEH))
    arten = sorted(e.werte["art"] for e in await _g4(db, await _a(db, aid)))
    assert arten == ([] if sprengsatz else ["neubeginn", "sprung"])


def test_b3_fuenf_prozent_bleibt_ausnahme():
    from backend.services.daten_checker.datenquelle.mqtt_standsprung import _kurz_tiefer

    z = [(1, 100.0, 0.0), (2, 95.0, -5.0), (3, 100.5, 0.5), (4, 101.0, 1.0)]
    assert _kurz_tiefer(z) == {2, 3}
    assert _kurz_tiefer([(1, 100.0, 0.0), (2, 89.0, 89.0), (3, 100.5, 100.5)]) == set()


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_arm"])
@pytest.mark.parametrize("stand,soll,zeit", [(_null_5min, 11.917, "10:25"), (_fremd_10min, 11.875, "10:30")],
                         ids=["null_5min", "fremd_10min"])
async def test_b4_zwischenstand_befund_und_handgriff(db, monkeypatch, stand, soll, zeit, sprengsatz):
    """Kurz 0 bzw. kurz ein fremder Stand in der Stunde: Kanal und Tagesansicht zählen den ganzen Stand (5 029,1), die Reihe 12.
    G4 nennt die Stunde (Arm «Zwischenstand», eigener Satz); der Knopf öffnet «Zähler getauscht» mit der Zeit der Rückkehr, der
    Eintrag macht den Tag 11,917 bzw. 11,875 in Kanal, Reihe und Tagesansicht, der Befund verschwindet. Sprengsatz: ohne Arm."""
    from backend.core.berechnungen import zaehlerstand_sprung as kern
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        echt = kern.finde_standspruenge
        monkeypatch.setattr(ms, "finde_standspruenge", lambda z, **kw: echt(z, **{**kw, "zwischenstand": False}))
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=FRUEH))
    g4 = await _g4(db, await _a(db, aid))
    if sprengsatz:
        assert g4 == []
        return
    (e,) = g4
    assert e.werte["art"] == "zwischenstand" and e.werte["getauscht"] == f"2026-06-08T{zeit}"
    assert e.meldung == f"Anlage · Netzbezug: Zählerstand springt am 08.06.2026 um {zeit} Uhr"
    assert e.details.startswith("In dieser Stunde zeigt der Zählerstand kurz eine andere Höhe (etwa 0 oder den Stand eines "
                                "anderen Geräts) und steht danach wieder bei ")
    assert ms.SATZ_WARUM_ZWISCHENSTAND in e.details and ms.SATZ_WARUM not in e.details
    await getauscht(datetime.fromisoformat(e.werte["getauscht"]))(db, aid)
    k, r, t = await _alle(db, aid)
    assert (k[0], r[0], t[0]) == (pytest.approx(soll, abs=0.001),) * 3
    assert await _g4(db, await _a(db, aid)) == []


def test_b4_tageszaehler_und_gleiche_summe_kein_zwischenstand():
    """Abgrenzung: ein Tageszähler fällt in der Stunde seines Neubeginns (Δ Stand < 0); Δ sum = Δ state ist gewöhnlicher Betrieb;
    unter einem Stand von 1 kWh kein Arm."""
    assert not zs._zwischenstand((1, 12.0, 100.0), (2, 0.5, 100.5))
    assert not zs._zwischenstand((1, 12.0, 100.0), (2, 12.5, 100.5))
    assert not zs._zwischenstand((1, 0.5, 100.0), (2, 0.6, 100.7))
    assert zs._zwischenstand((1, 5000.0, 100.0), (2, 5000.5, 5100.5))


async def test_b4_tageszaehler_stummer_publisher_kein_befund(db):
    """Halt-Prüfung B4: Tagesreset über MQTT mit stummem Publisher über Mitternacht — kein Arm «Zwischenstand»."""
    def stand(t):
        if datetime(2026, 6, 8, 20) <= t < datetime(2026, 6, 9, 14):
            t = datetime(2026, 6, 8, 20)
        return round(RATE * (t - datetime.combine(t.date(), datetime.min.time())).total_seconds() / 3600, 6)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=FRUEH))
    assert await _g4(db, await _a(db, aid)) == []


# ═══ B5 — «Gespeicherter Monatswert passt nicht mehr» nur bis zum Monat des Eintrags ═══════════════════════════════════

async def _b5_saat(db, eingetragen):
    from backend.models.anlage import Anlage
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.models.monatsdaten import Monatsdaten

    a = Anlage(anlagenname="B5", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key=NETZ, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    t0 = int(datetime(2026, 6, 1).timestamp())
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=t0 - 2 * 3600, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=t0 + 3600 * h, sum=0.5 * (h + 1), state=0.5 * (h + 1),
                               familie=FAMILIE_SPIEGEL) for h in range(-2, 32 * 24)])
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=365.0,
                       source_provenance={"netzbezug_kwh": {"source": "manual"}}))
    t = datetime(2026, 5, 10, 10)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=NETZ, erklaert_ts=t, ab_ts=t, vorher={"art": "ha", "entity_id": "sensor.alt"},
                            nachher={"art": "ha", "entity_id": "sensor.netz"}, grund="fortsetzung", herkunft="wechsel",
                            eingetragen_ts=eingetragen))
    await db.commit()
    if eingetragen is None:                      # Bestandszeile vor U3-K (die Vorgabe der Spalte setzt sonst «jetzt»)
        await db.execute(text("UPDATE zuordnung_wechsel SET eingetragen_ts = NULL"))
        await db.commit()
    return a


@pytest.mark.parametrize("eingetragen,soll", [(datetime(2026, 5, 10, 10, 3), 0), (datetime(2026, 6, 15, 9), 1), (None, 1)],
                         ids=["eintrag_im_mai_juni_unberuehrt", "eintrag_im_juni_beruehrt", "sprengsatz_ohne_zeitpunkt"])
async def test_b5_nur_monate_bis_zum_eintrag(db, eingetragen, soll):
    """Wechsel «bleiben» am 10.05.; Juni gespeichert 365,0 gegen 360,0 aus der Quelle. Eingetragen im Mai: den Juni hat der
    Anwender schon mit dem Wechsel gespeichert — kein Befund. Eingetragen im Juni (Nachtrag): Befund wie bisher. Ohne Zeitpunkt
    (Bestandszeile, zugleich der Sprengsatz «Regel vor U3-K»): jeder spätere Monat."""
    from backend.services.daten_checker import DatenChecker

    a = await _b5_saat(db, eingetragen)
    zw.vergiss(db)
    assert len(await DatenChecker(db)._check_monatswert_ueberholt(a, heute=date(2026, 7, 15))) == soll


async def test_b5_eintrag_traegt_seinen_zeitpunkt(db):
    """Jede neue Wechsel-Zeile trägt ``eingetragen_ts`` (Vorgabe der Spalte); ``lade_wechsel`` reicht ihn weiter."""
    a = await _b5_saat(db, None)
    t = datetime(2026, 6, 20, 10)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=NETZ, erklaert_ts=t, ab_ts=t, vorher=None, nachher=None,
                            grund="fortsetzung", herkunft="wechsel"))
    await db.commit()
    zw.vergiss(db)
    zeilen = (await zw.lade_wechsel(db, a.id))[NETZ]
    assert [z.eingetragen_ts is not None for z in zeilen] == [False, True]


# ═══ B6 — fehlende Proben ═════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [None, "ohne_aufruf", "achsen_leer"])
async def test_b6_stillstand_laesst_eine_verworfene_zeit_aus_ueber_den_checker(monkeypatch, sprengsatz):
    """Verdrahtung (Mutanten N13/N25 der Nachmessung): Stillstand 20.06. 10–13 Uhr an Netzbezug, Einspeisung und PV; eine
    verworfene Zeit an allen drei Zählern über diese Stunden erklärt die Stelle — der Befund nennt den Tag nicht (OK-Zeile).
    Sprengsätze: der Aufruf in ``_check_erfassung_stillstand`` fehlt bzw. die Achsen-Abbildung liefert nichts ⇒ der Tag bleibt."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker import erfassung_stillstand as es
    from backend.services.daten_checker.datenquelle import verworfen as vw
    from backend.services.kanal import bilanz_leser, merken
    from backend.tests import kanal_bilanz_gleichheit as kg
    from backend.tests.test_n799_stillstand_lesestelle import _einfrieren, _fein

    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    if sprengsatz == "ohne_aufruf":
        async def durch(_db, _a, tage):
            return tage
        monkeypatch.setattr(es, "_ohne_verworfene_zeit", durch)
    elif sprengsatz == "achsen_leer":
        async def leer(_db, _a):
            return []
        monkeypatch.setattr(vw, "achsen_der_verworfenen_zeiten", leer)
    merken.leeren()
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3)
        von, bis = datetime(2026, 6, 20, 10), datetime(2026, 6, 20, 13)
        for key in ("basis:netzbezug", "basis:einspeisung", "basis:pv_gesamt"):
            ds.db.add(ZuordnungWechsel(anlage_id=ds.aid, sensor_key=key, erklaert_ts=bis, ab_ts=bis, vorher=None, nachher=None,
                                       grund="korrektur", falsch_seit_ts=von, herkunft="nachtrag"))
        await ds.db.commit()
        zw.vergiss(ds.db)
        from sqlalchemy.orm import selectinload

        from backend.models.anlage import Anlage

        anlage = (await ds.db.execute(select(Anlage).options(selectinload(Anlage.investitionen))       # wie check_anlage
                                      .where(Anlage.id == ds.aid))).scalar_one()
        (e,) = await DatenChecker(ds.db)._check_erfassung_stillstand(anlage, heute=date(2026, 6, 30))
    merken.leeren()
    if sprengsatz:
        assert e.schwere.value == "info" and "20.06.2026" in e.details
    else:
        assert e.schwere.value == "ok"


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_aeltester"])
def test_b6_rest_schritt_nimmt_den_juengsten(monkeypatch, sprengsatz):
    """Zwei passende Schritte in den 24 Stunden vor «Falsch seit» (+3 000 um 02:00 und um 07:00 dazwischen zurück): die
    Vorgabe ist der jüngste (Mutant N12). Sprengsatz: der älteste."""
    from backend.core.berechnungen import zaehler_versatz as zv
    from backend.tests import test_daten_checker_zaehler_versatz as v

    if sprengsatz:
        monkeypatch.setattr(zv, "max", min, raising=False)
    sprung = v.T0 + timedelta(hours=v.SPRUNG_H)
    rueck = v.T0 + timedelta(hours=v.RUECK_H)
    h_alt, h_alt_ende, h_jung = v.SPRUNG_H - 8, v.SPRUNG_H - 6, v.SPRUNG_H - 3
    reihe = [(v.T0 + timedelta(hours=h), v._ha(h) + (3000.0 if (h_alt <= h < h_alt_ende or h_jung <= h < v.RUECK_H) else 0.0))
             for h in range(29 * 24)]
    s = zv.rest_schritt(reihe, sprung, rueck)
    assert s is not None
    assert s.bis == v.T0 + timedelta(hours=h_alt if sprengsatz else h_jung)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_rueckgang_am_stand"])
async def test_b6_mqtt_stand_kanal_zaehlt_den_stand_ohne_rueckgang_arm(db, monkeypatch, sprengsatz):
    """MQTT-Stand-Kanal (Gas, m³; Mutant N23): ein Sprung des Stands nennt G4 mit Δ Stand, nur mit reifem Bezug (ein Jahr, kein
    (b) für m³); ein fallender Stand nicht (den nennt ``zaehlerstand_reihe_bruch``). Sprengsatz: Arm «Rückgang» am Stand."""
    from backend.core.berechnungen import zaehlerstand_sprung as kern
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms
    from backend.tests import factories

    if sprengsatz:
        echt = kern.finde_standspruenge
        monkeypatch.setattr(ms, "finde_standspruenge", lambda z, **kw: echt(z, **{**kw, "rueckgang": True}))
    tausch, fall = datetime(2026, 6, 17, 10), datetime(2026, 6, 18, 10)

    def rate(t):
        return 0.1 + (40.0 if t == tausch else 0.0) - (5.0 if t == fall else 0.0)
    z = _reihe(datetime(2025, 5, 1), datetime(2026, 6, 19), rate, start=1000.0)
    a = await factories.anlage(db, anlagenname="U3K-Gas", sensor_mapping={"basis": {}, "investitionen": {}})
    k = Kanal(anlage_id=a.id, key="inv:9:zaehlerstand", einheit="m³", art="stand")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=z[0][0], familie="mitschrift", statistic_id="gas_m3", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=None, familie="mitschrift") for ts, st, _su in z])
    await db.commit()
    arten = sorted(e.werte["art"] for e in await _g4(db, a))
    assert arten == (["rueckgang", "sprung"] if sprengsatz else ["sprung"])


# ═══ Aus der Nachmessung Lab-K (LK-B1 … LK-B7, Bauplan Nr. 160) ═══════════════════════════════════════════════════════

LK_KEY = "inv:2:ladung_kwh"
LK_T0 = datetime(2026, 10, 1)


def _lk_t(h, m, tag=10):
    return datetime(2026, 11, tag, h, m)


def _lk_ha(eid):
    return {"quelle": "ha_app", "entity_id": eid}


async def _lk_altbestand(db, quellen, eintraege, *, staende=(datetime(2026, 11, 9, 12),)):
    """Altbestand vor der Überführung: Kanal-Quellen ``(ab, Entität | None = MQTT)``, Stände der Reihe, Protokoll-Einträge
    ``(Zeit, vorher, nachher)`` (vorher leer = klassische Zuordnung). Danach ``ueberfuehre``; die Zeilen als (vorher, nachher)."""
    from backend.models.activity_log import ActivityLog
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre

    a = Anlage(anlagenname="Altbestand", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    k = Kanal(anlage_id=a.id, key=LK_KEY, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    for ab, eid in quellen:
        fam = "spiegel" if eid else "mitschrift"
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(ab.timestamp()), familie=fam, statistic_id=eid, offset=0.0))
        db.add(KanalStatistik(kanal_id=k.id, start_ts=int(ab.timestamp()), sum=1.0, familie=fam))
    for t in staende:
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key=LK_KEY, zeitpunkt=t, wert_kwh=10.0, quelle="ha_statistics"))
    for ts, v, n in eintraege:
        db.add(ActivityLog(timestamp=ts, kategorie="sensor_mapping", aktion="Datenquelle zugeordnet", anlage_id=a.id,
                           details_json={"field_id": "inv_energy_2_ladung_kwh", "vorher": v, "nachher": n}))
    await db.flush()
    await ueberfuehre(db)
    rows = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == a.id)
                             .order_by(ZuordnungWechsel.erklaert_ts))).scalars().all()

    def q(x):
        return None if x is None else (x.get("entity_id") or x.get("mqtt_key") or x.get("art"))
    return [(q(r.vorher), q(r.nachher)) for r in rows]


LK_B1 = {
    "k1_ha_zu_mqtt": ([(LK_T0, "sensor.a"), (_lk_t(10, 0), None)], [(_lk_t(10, 20), None, {"quelle": "mqtt", "topic": "wb/e"})],
                      [("sensor.a", "inv/2/ladung_kwh")]),
    "k2_fehlgriff_b_dann_c": ([(LK_T0, "sensor.a"), (_lk_t(10, 0), "sensor.c")],
                              [(_lk_t(10, 10), None, _lk_ha("sensor.b")), (_lk_t(10, 20), _lk_ha("sensor.b"), _lk_ha("sensor.c"))],
                              [("sensor.a", "sensor.b"), ("sensor.b", "sensor.c")]),
    "k3_zuordnung_entfernt": ([(LK_T0, "sensor.a")], [(_lk_t(10, 20), None, None)], [("sensor.a", "inv/2/ladung_kwh")]),
    "k9_fehlgriff_und_zurueck": ([(LK_T0, "sensor.a")],
                                 [(_lk_t(10, 10), None, _lk_ha("sensor.b")), (_lk_t(10, 20), _lk_ha("sensor.b"), _lk_ha("sensor.a"))],
                                 [("sensor.a", "sensor.b"), ("sensor.b", "sensor.a")]),
}


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_teil1_auch_mit_staenden"])
@pytest.mark.parametrize("fall", sorted(LK_B1))
async def test_lk_b1_echte_wechsel_im_altbestand(db, monkeypatch, fall, sprengsatz):
    """LK-B1: liegen vor der Stunde Stände der Reihe, gilt die am Kanal aufgelöste Vor-Quelle — Teil 1 aus Lab-K F2 verwarf
    sonst K1/K3 ganz und ließ von K2/K9 nur die zweite Zeile. Sprengsatz: Teil 1 wie in Lab-K (ohne die Bedingung)."""
    from backend.services.zuordnung_wechsel import ueberfuehrung as ue

    if sprengsatz:
        async def nie(*_a):
            return False
        monkeypatch.setattr(ue, "_staende_davor", nie)
    quellen, eintraege, soll = LK_B1[fall]
    zeilen = await _lk_altbestand(db, quellen, eintraege)
    assert (zeilen == soll) != sprengsatz


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_jede_quelle_zeigt_den_wechsel"])
async def test_lk_b6_n05_teil1_ohne_staende_prueft_den_spiegel(db, monkeypatch, sprengsatz):
    """N05: ohne Stände davor gilt Teil 1 — die erste Quellzeile ab Stunde − 1 h muss der Spiegel der neuen Entität sein. Hier
    ist es ``sensor.c`` (nicht B) ⇒ keine Zeile. Sprengsatz: jede Quellzeile «zeigt» den Wechsel ⇒ eine Zeile A → B."""
    from backend.services.zuordnung_wechsel import ueberfuehrung as ue

    if sprengsatz:
        monkeypatch.setattr(ue, "_kanal_zeigt_wechsel", lambda *_a: True)
    zeilen = await _lk_altbestand(db, [(LK_T0, "sensor.a"), (_lk_t(10, 0), "sensor.c")],
                                  [(_lk_t(10, 20), None, _lk_ha("sensor.b"))], staende=())
    assert zeilen == ([("sensor.a", "sensor.b")] if sprengsatz else [])


def _w9_ep(t):
    return int(time.mktime(t.timetuple()))


async def _w9_welt(db, monkeypatch, *, key="inv:1:pv_erzeugung_kwh", kurzzeit=None, versatz_sum=0.0):
    """W9-Welt (Nachmessung Lab-K, ``test_nm_labk_w.py``): Reihe mit vollen Stunden-Ständen = HAs Stand und einem
    Unterstunden-Stand um 23:55 vor «Falsch seit» 20.09. 00:00; HA führt Stundenzeilen und — ``kurzzeit`` = [(Zeitpunkt,
    Abstand zum Stand um 23:55)] — Kurzzeitzeilen. ``versatz_sum``: ``sum`` liegt um diesen Betrag neben ``state`` (Stand-Feld)."""
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.korrektur as kr
    from backend.models.anlage import Anlage
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    mid = H.sensor(svc, "sensor.richtig", "kWh", has_sum=True)
    t0, f = datetime(2026, 9, 18), datetime(2026, 9, 20)
    s, zeilen, stand_um = 100.0, [], {}
    for h in range(96):
        t = t0 + timedelta(hours=h)
        stand_um[t] = s
        s = round(s + 0.5, 6)
        zeilen.append({"m": mid, "t": _w9_ep(t), "st": s, "su": s + versatz_sum})
    s2355 = round(stand_um[f - timedelta(hours=1)] + 0.5 * 11 / 12, 6)
    with svc._engine.begin() as c:
        c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :st, :su)"), zeilen)
        for zp, plus in kurzzeit or ():
            st = s2355 + plus
            c.execute(text("INSERT INTO statistics_short_term (metadata_id, start_ts, state, sum) VALUES (:m, :t, :st, :su)"),
                      {"m": mid, "t": _w9_ep(zp - timedelta(minutes=5)), "st": st, "su": st + versatz_sum})
    a = Anlage(anlagenname="W9", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    for t, v in stand_um.items():
        if t >= t0 + timedelta(hours=1):
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=t, wert_kwh=v, quelle="ha_statistics"))
    db.add(SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=f - timedelta(minutes=5), wert_kwh=s2355, quelle="ha_statistics"))
    await db.commit()
    q = {"art": "ha", "entity_id": "sensor.richtig"}
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=f, ab=f + timedelta(days=1), vorher=q, nachher=q, stueck=True)
    return au, svc, s2355


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_rueckgriff"])
async def test_lk_b2_unterstunden_rand_ohne_kurzzeit_ist_fuellbar(db, monkeypatch, sprengsatz):
    """LK-B2: der Rand-Stand 23:55 ist älter als HAs Kurzzeitstatistik ⇒ geprüft wird der Stand zur vollen Stunde davor gegen
    HAs Stundenzeile — das Stück ist füllbar (wie an 7311ad345). Sprengsatz: ohne Rückgriff (Lab-K) ⇒ nicht füllbar."""
    from backend.services.zuordnung_wechsel import stueck

    if sprengsatz:
        async def wie_labk(db_, a, rand, *_a):
            return rand
        monkeypatch.setattr(stueck, "_pruefbarer_rand", wie_labk)
    au, svc, _ = await _w9_welt(db, monkeypatch)
    assert await stueck.ist_fuellbar(db, au, svc) is not sprengsatz


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_toleranz_60"])
async def test_lk_b6_n14_kurzzeit_nur_die_zeile_des_stands(db, monkeypatch, sprengsatz):
    """N14: HA führt eine Kurzzeitzeile 15 Minuten neben dem Rand-Stand mit anderem Wert, die des Stands nicht — mit 3 Minuten
    Toleranz ist der Stand nicht prüfbar (Rückgriff auf die volle Stunde: füllbar); mit 60 Minuten träfe die fremde Zeile."""
    from backend.services.zuordnung_wechsel import stueck

    au, svc, _ = await _w9_welt(db, monkeypatch, kurzzeit=[(datetime(2026, 9, 19, 23, 40), 7.0)])
    if sprengsatz:
        echt = svc.get_value_at
        monkeypatch.setattr(svc, "get_value_at", lambda eid, z, tol=120, *a, **k: echt(eid, z, 60 if tol == 3 else tol, *a, **k))
    assert await stueck.ist_fuellbar(db, au, svc) is not sprengsatz


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_als_menge"])
async def test_lk_b6_n15_stand_feld_liest_den_stand(db, monkeypatch, sprengsatz):
    """N15: ein Stand-Feld (Gas, ``zaehlerstand``) liest am Unterstunden-Rand ``state``, nicht ``sum`` (hier 50 daneben) — der
    Rand passt. Sprengsatz: als Menge gelesen ⇒ passt nicht."""
    import backend.services.snapshot.keys as keys
    from backend.services.zuordnung_wechsel import stueck

    au, svc, _ = await _w9_welt(db, monkeypatch, key="inv:9:zaehlerstand", versatz_sum=50.0,
                                kurzzeit=[(datetime(2026, 9, 19, 23, 55), 0.0)])
    if sprengsatz:
        monkeypatch.setattr(keys, "ist_stand_sensor_key", lambda _k: False)
    assert await stueck.ist_fuellbar(db, au, svc) is not sprengsatz


async def _f5_welt(db, monkeypatch, vorige: dict):
    """F5-Welt (Nachmessung Lab-K, ``test_nm_labk_f5.py``): PV-Feld heute ``sensor.neu`` (HA ab 19.11. 23:00), dazu
    ``sensor.fremd`` und ``sensor.alt`` seit 08.10.; eine vorige Wechsel-Zeile ``sensor.alt`` → ``sensor.neu`` (``vorige``)."""
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.korrektur as kr
    from backend.models.anlage import Anlage
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    ende = datetime(2026, 11, 20, 1)
    for eid, ab, rate in (("sensor.fremd", datetime(2026, 10, 8), 1.08), ("sensor.neu", datetime(2026, 11, 19, 23), 0.36),
                          ("sensor.alt", datetime(2026, 10, 8), 0.6)):
        mid, s, z = H.sensor(svc, eid, "kWh", has_sum=True), 0.0, []
        for e in range(_w9_ep(ab), _w9_ep(ende) + 1, 3600):
            s = round(s + rate, 6)
            z.append({"m": mid, "t": e, "s": s})
        with svc._engine.begin() as c:
            c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"), z)
    a = Anlage(anlagenname="F5", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {
        "1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.neu"}}}}})
    db.add(a)
    await db.flush()
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key="inv:1:pv_erzeugung_kwh", herkunft="wechsel",
                            vorher={"art": "ha", "entity_id": "sensor.alt"}, nachher={"art": "ha", "entity_id": "sensor.neu"},
                            **vorige))
    await db.commit()
    zw.vergiss(db)
    return a, svc


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_vorgabe_ungeklemmt"])
async def test_lk_b3_voriger_wechsel_in_derselben_stunde(db, monkeypatch, sprengsatz):
    """LK-B3: der vorige Wechsel (01:10, ab 02:00) lässt nur die Stunde 02:00 zu — die Vorgabe liegt dort (nicht 01:00), kein
    Wahlfeld (keine Grenzen), der Satz nennt die Stunde ohne Hinweis auf das Feld; eine andere Stunde lehnt der Satz «kann hier
    nur … sein» ab (kein «zwischen X und X»). Sprengsatz: die Vorgabe ohne Klemme ⇒ 01:00."""
    from backend.services.zuordnung_wechsel import ansatz, bleiben
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    if sprengsatz:
        monkeypatch.setattr(ansatz, "_stunde", lambda t: datetime(2000, 1, 1) if t == datetime(2026, 11, 20, 2) else
                            t.replace(minute=0, second=0, microsecond=0))
    a, svc = await _f5_welt(db, monkeypatch, dict(erklaert_ts=datetime(2026, 11, 20, 1, 10), ab_ts=datetime(2026, 11, 20, 2),
                                                  grund="fortsetzung", ansatz="beide", stand_alt_ende=1.0, stand_neu_null=0.0))
    jetzt = datetime(2026, 11, 20, 1, 27)
    kw = dict(ab_ts=ab_ts_aus(jetzt), erklaert_ts=jetzt, jetzt=jetzt, ha_svc=svc)
    q = ({"art": "ha", "entity_id": "sensor.neu"}, {"art": "ha", "entity_id": "sensor.fremd"})
    b = await bleiben.angaben(db, a.id, "inv:1:pv_erzeugung_kwh", *q, **kw)
    if sprengsatz:
        assert b["zaehlt_ab"] == "2026-11-20T01:00:00"
        return
    assert (b["zaehlt_ab"], b["zaehlt_ab_vorgabe"], b["zaehlt_ab_frueheste"], b["zaehlt_ab_spaeteste"]) == (
        "2026-11-20T02:00:00", None, None, None)
    assert any(s.endswith("eedc zählt sensor.neu bis 20.11.2026 02:00 Uhr und sensor.fremd ab 20.11.2026 02:00 Uhr.")
               for s in b["saetze"]), b["saetze"]
    with pytest.raises(bleiben.ZaehltAbAbgelehnt, match="kann hier nur 20.11.2026 02:00 Uhr sein"):
        await bleiben.angaben(db, a.id, "inv:1:pv_erzeugung_kwh", *q, zaehlt_ab=datetime(2026, 11, 20, 1), **kw)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_vorher_runden"])
async def test_lk_b5_mwh_stand_erst_umrechnen_dann_runden(monkeypatch, sprengsatz):
    """LK-B5: Kurzzeit-Stand 5,1851667 MWh ⇒ 5 185,167 kWh (vorher 5 185,0). Sprengsatz: ``roh`` ignoriert (auf drei Stellen)."""
    from backend.services.kanal.angaben import _stand_kurzzeit
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    mid = H.sensor(svc, "sensor.mwh", "MWh", has_sum=True)
    jetzt = datetime(2026, 11, 20, 1, 27)
    with svc._engine.begin() as c:
        c.execute(text("INSERT INTO statistics_short_term (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"),
                  {"m": mid, "t": _w9_ep(jetzt - timedelta(minutes=15)), "s": 5.1851667})
    if sprengsatz:
        echt = svc.get_value_at
        monkeypatch.setattr(svc, "get_value_at", lambda *a, roh=False, **k: echt(*a, **k))
    assert _stand_kurzzeit(svc, "sensor.mwh", "sum", jetzt) == (5185.0 if sprengsatz else 5185.167)


def test_lk_b7_w3_wortlaut():
    from backend.services.zuordnung_wechsel.bleiben import SATZ_BEIDE_NUR_NEU

    assert SATZ_BEIDE_NUR_NEU.format(alt="A", neu="B", g="20.11.2026 00:00") == (
        "eedc rechnet wie Home Assistant mit beiden Sensoren: A bis zu seinem letzten Wert, B ab seinem ersten. Für die Stunde "
        "ab 20.11.2026 00:00 Uhr führt Home Assistant von A keinen Wert — sie zählt nur B. Zwischen den Zählerständen der zwei "
        "Sensoren rechnet eedc keine Menge.")


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_immer"])
async def test_lk_b6_n03_nachlauf_aus_dem_auftrag_schreibt_abgeleitete_immer(monkeypatch, sprengsatz):
    """N03: holt der Lauf den Nachlauf des Ansetzens aus dem Auftrag nach (Neustart), schreibt er die abhängigen abgeleiteten
    Kanäle bis jetzt fort (``abgeleitet_immer``). Sprengsatz: der Auftrag ohne die Angabe ⇒ «nur nach verworfenen Zeilen»."""
    import backend.services.kanal.korrektur as kk
    from backend.services.zuordnung_wechsel.korrektur import nachlauf_aus_auftrag

    gesehen = {}

    async def schreibe(_s, _a, _kk, _z, *, immer=False):
        gesehen["immer"] = immer
        return 0
    monkeypatch.setattr(kk, "schreibe_abgeleitete_nach", schreibe)
    f = {"key": LK_KEY, "jetzt": "2026-11-04T00:05:00", "bis_ts": 0, **({} if sprengsatz else {"abgeleitet_immer": True})}
    await nachlauf_aus_auftrag(None, 1, f)
    assert gesehen["immer"] is not sprengsatz


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_auftrag_ohne_immer"])
async def test_lk_b6_n04_auftrag_des_ansetzens_traegt_abgeleitet_immer(db, monkeypatch, sprengsatz):
    """N04: das Ansetzen legt den Nachlauf mit ``abgeleitet_immer`` in den Lauf-Zustand (Tausch-Stunde 23:00, Umstellung 23:24,
    Stundenlauf 00:05). Sprengsatz: der Auftrag trägt es nicht."""
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.tests import test_sensorwechsel_labk_proben as lk

    echt = korrektur_lauf.anlegen
    auftraege = []

    async def merke(db_, lauf, aid, key, tage, fuellen=None, art=None):
        if fuellen is not None and sprengsatz:
            fuellen = {k: v for k, v in fuellen.items() if k != "abgeleitet_immer"}
        auftraege.append(fuellen)
        return await echt(db_, lauf, aid, key, tage, fuellen=fuellen, art=art)
    monkeypatch.setattr(korrektur_lauf, "anlegen", merke)
    ab0 = lk._ep(lk.START) - 5 * lk.STUNDE
    serien = {lk.ALT: (ab0, lambda e: 1.2 if e < lk.E1 else (0.4 if e == lk.E1 else None)),
              lk.NEU: (lk.E1, lambda e: 0.8 if e == lk.E1 else 1.2), lk.PVC: (ab0, lambda e: 2.0)}
    w = await lk._welt(db, monkeypatch, serien, {"wb": lk.ALT, "pvk": lk.PVC})
    await lk._betrieb(w, lk.START, lk.T1)
    await lk._umstellen(w, monkeypatch, lk.T1 + timedelta(minutes=24), "wb", lk.NEU, grund="fortsetzung")
    w.ha_bis(lk.E1)
    await lk._lauf(w, lk.T1 + timedelta(hours=1))
    mit = [f for f in auftraege if f is not None]
    assert mit and all(bool(f.get("abgeleitet_immer")) is not sprengsatz for f in mit)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ab_ts_statt_falsch_seit"])
async def test_lk_b6_n11_untergrenze_einer_korrektur_ist_falsch_seit(db, monkeypatch, sprengsatz):
    """N11: ist der vorige Wechsel eine Korrektur, beginnt der Bereich von «Der neue Sensor zählt ab» an ihrem «Falsch seit»
    (19.11. 20:00), nicht an ihrem ``ab_ts`` (20.11. 00:00). Sprengsatz: die Untergrenze aus ``ab_ts``."""
    from backend.services.zuordnung_wechsel import ansatz, bleiben
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    if sprengsatz:
        monkeypatch.setattr(ansatz, "_vorige_grenze", lambda alle, row, erklaert: datetime(2026, 11, 20, 0))
    a, svc = await _f5_welt(db, monkeypatch, dict(erklaert_ts=datetime(2026, 11, 19, 23, 24), ab_ts=datetime(2026, 11, 20, 0),
                                                  grund="korrektur", ansatz="schnitt",
                                                  falsch_seit_ts=datetime(2026, 11, 19, 20)))
    jetzt = datetime(2026, 11, 20, 1, 27)
    b = await bleiben.angaben(db, a.id, "inv:1:pv_erzeugung_kwh", {"art": "ha", "entity_id": "sensor.neu"},
                              {"art": "ha", "entity_id": "sensor.fremd"}, ab_ts=ab_ts_aus(jetzt), erklaert_ts=jetzt, jetzt=jetzt,
                              ha_svc=svc)
    assert b["zaehlt_ab_frueheste"] == ("2026-11-20T00:00:00" if sprengsatz else "2026-11-19T20:00:00")
