"""Sensorwechsel — Korrekturrunde U3-K2 (Bauplan Nr. 161, offene Punkte P-2 und P-3 aus ``opus-berichte/SENSORWECHSEL-U3K-…``) —
Proben mit Sprengsatz.

* **P-2** Höhenwechsel nach Leistung über die Zeit **seit der Stand zuletzt anders war** (``rohstand_rand.seit_dem_letzten_anderen``):
  eine Nachholmenge nach 1 h, 3 h, 30 h Stille ist kein Höhenwechsel (0,5 kW statt 6 · 18 · 180 kW in fünf Minuten); ein echter
  Tausch nach einer Pause von 2 h (+2 000 kWh) bleibt einer; ein gewöhnlicher Schritt behält seine fünf Minuten.
* **P-3** eine Entscheidung, zwei Verbraucher: nennt der Befund «Zählerstand springt (MQTT)» die Stunde (Kern
  ``zaehlerstand_sprung.finde_standspruenge``), nimmt der Dialog «Zähler getauscht» den größten Schritt nach oben der Stunde als
  Höhenwechsel an (``rohstand_rand.sprung_der_stunde(…, benannt=True)``, ``rohstand.stunde_benannt``) — ein reifer Zähler mit
  kleinem Tageszuwachs, Schritt unter der Grenze; der Befund nennt die Zeit des Schritts. Wo kein Befund die Stunde nennt (Ladung
  nach Standby, Nachholmenge), bleibt die Ablehnung.

Zeitpunkte im Juni (fern jeder Umstellung; die Stundenzeilen des Jahres davor über die Epoche); die Datei liest keine Uhr und läuft
auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``. Schwesterdateien: test_sensorwechsel_u3k_proben.py (B1–B7), test_sensorwechsel_u3b_proben.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import insert, select, text

from backend.core.berechnungen import rohstand_rand as rr
from backend.tests.test_sensorwechsel_u3b_proben import MK, NETZ, NETZ_FID, zw  # noqa: F401 — Schlüssel, Merkliste

T = datetime(2026, 6, 17, 10, 20)        # der Schritt (erster Rohstand danach)
T0 = datetime(2025, 5, 1)


def _fuenf(beginn: datetime, ende: datetime, f) -> list[rr.Roh]:
    out, t = [], beginn
    while t < ende:
        out.append((t, round(f(t), 6)))
        t += timedelta(minutes=5)
    return out


# ═══ P-2 — die Leistung über die Zeit seit dem letzten anderen Stand ═════════════════════════════════════════════════

def _stumm(n_h: float, schritt_kwh: float | None = None):
    """0,5 kWh je Stunde; ``n_h`` Stunden vor ``T`` stumm (der Scheduler wiederholt den Stand); um ``T`` der wahre Stand bzw.
    ``schritt_kwh`` über dem stummen Stand."""
    def w(x):
        return 5000.0 + 0.5 * (x - datetime(2026, 6, 15)).total_seconds() / 3600
    stumm_ab = T - timedelta(hours=n_h)

    def f(t):
        if stumm_ab <= t < T:
            return w(stumm_ab)
        if t >= T and schritt_kwh is not None:
            return w(stumm_ab) + schritt_kwh + (w(t) - w(T))
        return w(t)
    return _fuenf(T - timedelta(hours=24), T + timedelta(hours=1), f)


def test_p2_regel_seit_dem_letzten_anderen():
    roh = _stumm(3)
    i = next(j for j, (t, _w) in enumerate(roh) if t == T)
    assert rr.seit_dem_letzten_anderen(roh, i) == pytest.approx(3 * 3600)
    assert rr.seit_dem_letzten_anderen(roh, i + 1) == pytest.approx(300)          # gewöhnlicher Schritt: fünf Minuten
    nur_ein = [(T - timedelta(minutes=5), 1.0), (T, 2.0)]
    assert rr.seit_dem_letzten_anderen(nur_ein, 1) == pytest.approx(300)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_fuenf_minuten"])
@pytest.mark.parametrize("stumm_h,schritt", [(1, 15.0), (3, 15.0), (30, None)], ids=["1h_15kwh", "3h_15kwh", "30h_nachhol"])
def test_p2_nachholmenge_ist_kein_hoehenwechsel(monkeypatch, stumm_h, schritt, sprengsatz):
    """15 kWh nach 1 h bzw. 3 h Stille (15 · 5 kW) und die Nachholmenge nach 30 h (15 kWh; die gelesenen 24 h ⇒ 0,62 kW) sind kein
    Höhenwechsel. Sprengsatz: die Zeit zwischen den zwei Rohständen (U3-K) ⇒ 180 kW, Höhenwechsel."""
    if sprengsatz:
        monkeypatch.setattr(rr, "seit_dem_letzten_anderen", lambda roh, i: (roh[i][0] - roh[i - 1][0]).total_seconds())
    roh = _stumm(stumm_h, schritt)
    assert (rr.sprung_der_stunde(roh, T.replace(minute=0), 100.0) is not None) == sprengsatz


def test_p2_tausch_nach_pause_bleibt_hoehenwechsel():
    """Ein echter Tausch nach 2 h Pause (+2 000 kWh: 1 000 kW über die Grenze 100) bleibt ein Höhenwechsel, der Rand ist der Schritt."""
    roh = _stumm(2, 2000.0)
    a, b = rr.sprung_der_stunde(roh, T.replace(minute=0), 100.0)
    assert (a[0], b[0]) == (T - timedelta(minutes=5), T)


# ═══ P-3 — Befund und Dialog: eine Entscheidung ══════════════════════════════════════════════════════════════════════

def _lage(name: str):
    """(Stand-Funktion, Tage Geschichte, kWp)."""
    if name == "reif_200kwp":          # 1,5 kWh am Tag, 200 kWp (Grenze 300 kW); +20 kWh in fünf Minuten = 240 kW
        return (lambda t: 1000.0 + 1.5 / 24 * (t - T0).total_seconds() / 3600 + (20.0 if t >= T else 0.0)), 400, 200.0
    if name == "reif_stufig":          # 1,2 kWh am Tag, Stand nur zur vollen Stunde; +15 kWh nach 20 Minuten Stand = 45 kW
        def f(t):
            g = t.replace(minute=0, second=0) if t < T else t
            return 1000.0 + 1.2 / 24 * (g - T0).total_seconds() / 3600 + (15.0 if t >= T else 0.0)
        return f, 400, 10.0
    if name == "wallbox_22kw":         # 20 Tage Standby 5 W, dann 22 kW ab 18:00 (Gegenfall B7)
        l0 = datetime(2026, 6, 17, 18)

        def f(t):
            b = 5000.0 + 0.005 * (min(t, l0) - datetime(2026, 5, 28)).total_seconds() / 3600
            return b + (22.0 * min((t - l0).total_seconds(), 3 * 3600) / 3600 if t > l0 else 0.0)
        return f, 20, 10.0
    # nachhol_30h: 0,5 kWh je Stunde, Publisher 30 h stumm, um T der wahre Stand (Gegenfall P-2)
    def w(x):
        return 5000.0 + 0.5 * (x - datetime(2026, 5, 28)).total_seconds() / 3600
    return (lambda t: w(T - timedelta(hours=30)) if T - timedelta(hours=30) <= t < T else w(t)), 20, 10.0


async def _welt(db, name: str):
    """MQTT-Kanal «Eigene Summe» mit Stundenzeilen über die Geschichte (Stand am Ende der Stunde = letzter Rohstand der Stunde)
    und Rohstände im 5-Minuten-Raster der letzten zwei Tage; Netzbezug über Standard-Inbound."""
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.tests import factories

    f, tage, kwp = _lage(name)
    a = await factories.anlage(db, anlagenname="U3K2", leistung_kwp=kwp, sensor_mapping={"basis": {}, "investitionen": {}})
    k = Kanal(anlage_id=a.id, key=NETZ, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    ende = datetime(2026, 6, 18, 6)
    beginn = datetime(2026, 6, 18) - timedelta(days=tage)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(beginn.timestamp()), familie="mitschrift", statistic_id=MK, offset=0.0))
    zeilen, e, summe, vorher = [], int(beginn.timestamp()), 0.0, f(beginn)
    while e < ende.timestamp():                       # über die Epoche (eine Umstellung im Jahr davor zählt richtig)
        st = f(datetime.fromtimestamp(e + 3300))
        summe += st - vorher
        zeilen.append({"kanal_id": k.id, "start_ts": e, "state": round(st, 6), "sum": round(summe, 6), "familie": "mitschrift"})
        vorher, e = st, e + 3600
    await db.execute(insert(KanalStatistik), zeilen)
    await db.execute(insert(MqttEnergySnapshot), [{"anlage_id": a.id, "timestamp": t, "energy_key": MK, "value_kwh": w}
                                                  for t, w in _fuenf(datetime(2026, 6, 16), ende, f)])
    await db.commit()
    return a, k.id


async def _befund(db, a):
    from backend.services.daten_checker import DatenChecker

    zw.vergiss(db)
    return await DatenChecker(db)._check_mqtt_zaehlerstand_springt(a)


async def _dialog(db, aid: int, zeit: datetime, *, eintragen: bool = False) -> dict:
    from backend.api.routes import sensorwechsel as sw

    zw.vergiss(db)
    req = sw.ZaehlerGetauschtRequest(getauscht_am=zeit)
    return await (sw.zaehler_getauscht if eintragen else sw.pruefe_zaehler_getauscht)(aid, NETZ_FID, req, db)


async def _kanal_tag(db, kid: int, d: datetime) -> float:
    from backend.models.kanal import Kanal
    from backend.services.kanal import lesen, merken

    merken.invalidiere(None)
    k = (await db.execute(select(Kanal).where(Kanal.id == kid))).scalar_one()
    z = await lesen.zeitraum(db, k, int(d.timestamp()), int((d + timedelta(days=1)).timestamp()))
    return round(z.delta, 3)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_groessten_schritt"])
@pytest.mark.parametrize("name,schritt", [("reif_200kwp", 20.0), ("reif_stufig", 15.0)])
async def test_p3_befund_und_dialog_eine_entscheidung(db, monkeypatch, name, schritt, sprengsatz):
    """Der Befund nennt die Stunde 10:00 (reifer Bezug, Maß über 10) und die Zeit des Schritts 10:20; der Dialog nimmt ihn an und
    trägt ein; danach zählt der Tag den Schritt nicht mehr, und der Befund ist weg. Sprengsatz: der Dialog wie U3-K (nur die
    Leistung) ⇒ der Befund nennt den Beginn der Stunde, der Dialog lehnt ab."""
    if sprengsatz:
        monkeypatch.setattr(rr, "groesster_schritt_der_stunde", lambda roh, stunde: None)
    a, kid = await _welt(db, name)
    (e,) = await _befund(db, a)
    assert e.werte["art"] == "sprung" and e.werte["stunde"] == "2026-06-17T10:00"
    tag = datetime(2026, 6, 17)
    vorher = await _kanal_tag(db, kid, tag)
    p = await _dialog(db, a.id, datetime.fromisoformat(e.werte["getauscht"]))
    if sprengsatz:
        assert e.werte["getauscht"] == "2026-06-17T10:00" and p["weg"] == "kein_sprung" and p["eintragen"] is False
        return
    assert e.werte["getauscht"] == "2026-06-17T10:20" and e.ziel.params["getauscht"] == "2026-06-17T10:20"
    assert p["weg"] == "fortsetzung" and p["eintragen"] is True and p["getauscht_am"] == "2026-06-17T10:20:00"
    # eine andere Stunde desselben Zählers nennt der Befund nicht — dort bleibt die Ablehnung
    assert (await _dialog(db, a.id, datetime(2026, 6, 17, 14, 20)))["weg"] == "kein_sprung"
    r = await _dialog(db, a.id, T, eintragen=True)
    assert r["eingetragen"] is True
    w = (await db.execute(text("SELECT stand_alt_ende, stand_neu_null FROM zuordnung_wechsel"))).one()
    # die Rand-Stände sind der Schritt (dazu, was zwischen dem letzten alten und dem ersten neuen Stand gezählt wurde: höchstens
    # 20 Minuten Verbrauch) — und genau diesen Unterschied zählt der Tag danach nicht mehr
    assert w[1] - w[0] == pytest.approx(schritt, abs=0.02)
    assert await _kanal_tag(db, kid, tag) == pytest.approx(vorher - (w[1] - w[0]), abs=0.001)
    assert await _befund(db, a) == []


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_jede_stunde_benannt"])
@pytest.mark.parametrize("name,zeit", [("wallbox_22kw", datetime(2026, 6, 17, 18, 5)), ("nachhol_30h", T)])
async def test_p3_ohne_befund_bleibt_die_ablehnung(db, monkeypatch, name, zeit, sprengsatz):
    """Ladung nach Standby (B7) und Nachholmenge nach 30 h Stille (P-2): kein Befund, der Dialog lehnt ab. Sprengsatz: jede Stunde
    gälte als vom Befund genannt ⇒ der Dialog nähme den größten Schritt und strich echten Verbrauch."""
    from backend.services.zuordnung_wechsel import rohstand

    if sprengsatz:
        async def immer(*_a, **_k):
            return True
        monkeypatch.setattr(rohstand, "stunde_benannt", immer)
    a, _kid = await _welt(db, name)
    assert await _befund(db, a) == []
    p = await _dialog(db, a.id, zeit)
    assert (p["weg"], p["eintragen"]) == (("fortsetzung", True) if sprengsatz else ("kein_sprung", False))
