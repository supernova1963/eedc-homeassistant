"""Sensorwechsel — Korrekturrunde U3-K4 (Bauplan Nr. 164/165, Nachmessung ``opus-berichte/SENSORWECHSEL-U3K3-NACHMESSUNG-…``
K3-B1 … K3-B7) — Proben mit Sprengsatz.

* **P1–P3 in der Fassung von Bauplan Nr. 166** (Entscheid Gernot 20.11.2026: bei MQTT entscheidet der Anwender; die Erkennung
  zeigt, sie entscheidet nicht): der Dialog «Zähler getauscht» nimmt ohne Höhenwechsel den nächsten anderen Stand
  (``rohstand.naechster_anderer_um``), trägt ein und sagt per Hinweis, ob sich der Schritt abhebt (``rohstand_rand.abgehoben``:
  ≥ 90 % der Stunde und mehr als das Zehnfache des größten gewöhnlichen Schritts der 24 Stunden davor); der Befund
  «Zählerstand springt (MQTT)» nennt eine Stunde bei Höhenwechsel oder abgehobenem Schritt, dort mit dem Wortlaut, dass eedc
  Tausch und gezählte Menge nicht unterscheidet; «Bisherige Werte bleiben» nimmt ohne Höhenwechsel die zwei Stände um den
  Zeitpunkt (nachgetragen = sofort) und nennt einen Schritt der Stunde, der sich abhebt.
* **P4 (K3-B4)** «Falsch seit» auf der ersten Zeile einer neuen Statistik ist «Regel 2» ohne Lücke.
* **P5 (K3-B5)** der Nullpunkt bleibt im Monat, wenn später ein Wechsel «bleiben» vom richtigen Sensor weiterführt.
* **P6 (K3-B7)** Sätze: Vorschau-Tage wie die Auskunft, Auskunft-Zeit bis zur ersten zählenden Stunde, zwei Nachkommastellen.
* **P8** Proben für die überlebenden Mutanten N03, N04, N07, N10, N11 (= P4), N13, N14, N17 (= P5).

Welten wie U3-K3 (``test_sensorwechsel_u3k3_proben``: Netzbezug 0,6 kWh je Stunde ab 5 000, Ereignis 08.06.2026 10:20; Teil B
die Wallbox-Welt mit ``sensor.c`` als neuer Statistik ab 12.06. 23:00). Zeitpunkte im Juni; die Datei liest keine Uhr und läuft
auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``. Schwesterdateien: test_sensorwechsel_u3k3_proben.py,
test_sensorwechsel_u3k2_proben.py, test_sensorwechsel_u3k_proben.py, test_sensorwechsel_u3b_proben.py.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from backend.core.berechnungen import rohstand_rand as rr
from backend.core.berechnungen import zaehlerstand_sprung as zs
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.tests import test_daten_checker_zaehler_versatz as zv
from backend.tests.test_daten_checker_zaehler_versatz import ha  # noqa: F401 — Fixture
from backend.tests.test_sensorwechsel_u3b_proben import (  # noqa: F401
    NETZ, Saat, _anlage_frisch, _wechsel_topic, _wechsel_zeilen, betrieb, kanal_stunde, zw,
)
from backend.tests.test_sensorwechsel_u3k3_proben import (  # noqa: F401
    AB_B, EN, FS_B, H0_B, JETZT_B, QA_B, QC_B, R, ST, T, TAGE, _anlage, _befund, _dialog, _drei, _kanal, _vorlauf, w,
)

H10 = T.replace(minute=0)


def _reihe(schritte_davor: list[tuple[timedelta, float]], schritte: list[float], grund: float = 0.05,
           beginn: datetime = datetime(2026, 6, 8, 10)) -> list:
    """Rohstände je fünf Minuten: zwei Tage gewöhnliche Schritte ``grund``, dazu einzelne Schritte ``(Abstand vor beginn, Menge)``,
    dann die Schritte der Stunde ab ``beginn`` (der erste endet um ``beginn``)."""
    extra = {beginn - d: m for d, m in schritte_davor}
    roh, t, s = [], beginn - timedelta(hours=48), 1000.0
    while t < beginn:
        s += extra.get(t, grund)
        roh.append((t, round(s, 6)))
        t += timedelta(minutes=5)
    for d in schritte:
        s += d
        roh.append((t, round(s, 6)))
        t += timedelta(minutes=5)
    return roh


# ═══ P1 — Bauplan Nr. 166: der Dialog nimmt den nächsten anderen Stand und zeigt, ob sich der Schritt abhebt ═══════════════

UNKLAR = "Ob das ein Tausch ist oder eine gezählte Menge, erkennt eedc nicht."
KEIN = "Einen Sprung sieht eedc an dieser Zeit nicht."


@pytest.mark.parametrize("davor,schritte,abgehoben", [
    ([], [0.0] * 11 + [0.6], True),                          # 12 × die 0,05 davor
    ([], [0.0] * 11 + [0.4], False),                         # 8 × — hebt sich nicht ab
    ([(timedelta(hours=23), 2.0)], [0.0] * 11 + [9.0], False),  # 2,0 vor 23 h: 4,5 ×
    ([(timedelta(hours=25), 2.0)], [0.0] * 11 + [9.0], True),   # 2,0 vor 25 h liegt außerhalb der 24 h
    ([(timedelta(hours=5), 0.5)], [0.0] * 11 + [3.0], False),  # das Größte zählt (0,5: 6 ×), nicht das Kleinste
], ids=["zwoelffach", "achtfach", "groesser_davor_23h", "groesser_davor_25h", "maximum_nicht_minimum"])
def test_p1_hebt_sich_ab_rein(davor, schritte, abgehoben):
    """«Hebt sich ab» (nur Hinweis und Befund): die Menge des Schritts gegen die größte gewöhnliche Menge der 24 Stunden davor
    (``BEZUG``) — das 24-Stunden-Fenster und das Maximum halten ``groesser_davor_25h`` und ``maximum_nicht_minimum``."""
    roh = _reihe(davor, schritte)
    g = rr.abgehobener_schritt_der_stunde(roh, datetime(2026, 6, 8, 10), 100.0)
    assert (g is not None) is abgehoben
    if abgehoben:
        assert rr.menge_des_schritts((roh[g - 1], roh[g])) == pytest.approx(max(schritte))


def test_p1_hebt_sich_ab_ohne_schritt_davor():
    """Ohne Schritt nach oben in den 24 Stunden davor (Stille) hebt sich jeder Schritt ab."""
    roh = [(datetime(2026, 6, 8, 9) + timedelta(minutes=5 * i), 1000.0) for i in range(12)] + [(datetime(2026, 6, 8, 10), 1000.3)]
    assert rr.hebt_sich_ab(roh, len(roh) - 1, [False] * len(roh)) is True


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_hebt_sich_immer_ab"])
@pytest.mark.parametrize("takt,am,tag", [(60, "2026-06-08T11:00:00", 13.8), (30, "2026-06-08T10:30:00", 14.1),
                                         (15, "2026-06-08T10:30:00", 14.25)])
async def test_p1_takt_gewoehnlicher_betrieb_eintragbar_mit_hinweis(db, monkeypatch, takt, am, tag, sprengsatz):
    """Junger Zähler (0,6 kWh je Stunde), Publisher alle 60/30/15 Minuten, gewöhnlicher Betrieb, «Getauscht am» 10:20: der Dialog
    nimmt den nächsten anderen Stand, nennt die stille Zeit und die Menge und sagt «Einen Sprung sieht eedc an dieser Zeit
    nicht.»; eingetragen zählt der Tag diese Menge nicht (13,8 · 14,1 · 14,25). Sprengsatz: jeder Schritt höbe sich ab ⇒ der
    Hinweis «Ob das ein Tausch ist …»."""
    if sprengsatz:
        monkeypatch.setattr(rr, "abgehoben", lambda *_a, **_k: True)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(w, start=ST, ende=EN, takt=takt))
    assert await _befund(db, aid) == []
    p = await _dialog(db, aid, T)
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, am)
    assert p["saetze"][0].startswith("Der Zählerstand steht von ")
    assert p["saetze"][1] == (UNKLAR if sprengsatz else KEIN)
    if sprengsatz:
        return
    assert (await _dialog(db, aid, T, eintragen=True))["eingetragen"] is True
    k, r, t = await _drei(db, aid)
    assert k[0] == r[0] == t[0] == tag


async def test_p1_takt60_satz_wortlaut(db):
    """Takt 60, «Getauscht am» 10:20: der Satz wörtlich (Stände und Menge mit zwei Nachkommastellen)."""
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(w, start=ST, ende=EN, takt=60))
    p = await _dialog(db, aid, T)
    assert p["saetze"][:2] == ["Der Zählerstand steht von 08.06.2026 10:00 bis 08.06.2026 11:00 Uhr still und ändert sich dann "
                               "von 5.049,20 auf 5.049,80 kWh. Trägst du den Tausch ein, zählt eedc diese 0,60 kWh nicht.", KEIN]


@pytest.mark.parametrize("plus,befund", [(2000.0, True), (90.0, False)])
async def test_p1_takt60_echter_tausch(db, plus, befund):
    """Publisher stündlich, Tausch um 10:20 mit +2 000 bzw. +90 kWh (sichtbar im Rohstand um 11:00): der Dialog zur wahren Zeit
    10:20 trägt am Schritt 11:00 ein — ein Eintrag, Tag 13,8, der Befund (nur bei +2 000) ist danach weg."""
    def stand(t):
        return w(t) + (plus if t >= T else 0.0)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN, takt=60))
    b = await _befund(db, aid)
    assert [(x.werte["stunde"], x.werte["getauscht"]) for x in b] == ([("2026-06-08T11:00", "2026-06-08T11:00")] if befund else [])
    p = await _dialog(db, aid, T)
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T11:00:00")
    if befund:                              # Sitzung 5 (K4-B2): der andere Stand liegt am Höhenwechsel — R1, ohne Hinweis
        assert p["saetze"][0].startswith("eedc trägt den Tausch am 08.06.2026 11:00 Uhr ein") and UNKLAR not in p["saetze"]
    else:
        assert p["saetze"][1] == UNKLAR
    assert (await _dialog(db, aid, T, eintragen=True))["eingetragen"] is True
    k, r, t = await _drei(db, aid)
    assert k[0] == r[0] == t[0] == 13.8
    assert await _befund(db, aid) == []
    assert len(await _wechsel_zeilen(db, aid)) == 1


async def test_p1_ganzzahliger_stand(db):
    """Ein ganzzahliger Stand (+1 alle 100 Minuten), «Getauscht am» 11:30: eintragbar am nächsten anderen Stand (13:00) mit
    «Einen Sprung sieht eedc an dieser Zeit nicht.»; eingetragen zählt der Tag 1 kWh weniger (14,0 → 13,0)."""
    def stand(t):
        return float(math.floor(w(t)))
    aid = (await _anlage(db)).id
    await _vorlauf(db, aid, stand, 20)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    zeit = datetime(2026, 6, 8, 11, 30)
    p = await _dialog(db, aid, zeit)
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T13:00:00")
    assert p["saetze"][1] == KEIN
    vorher = await _drei(db, aid)
    assert (await _dialog(db, aid, zeit, eintragen=True))["eingetragen"] is True
    assert (await _drei(db, aid))[0][0] == pytest.approx(vorher[0][0] - 1.0)


async def test_p1_zwei_rohstaende_der_stunde(db):
    """Eine Stunde mit nur zwei Rohständen (10:55 meldet nach einer Stunde ohne Änderung): 0,55 kWh in fünf Minuten, das Elffache
    des gewöhnlichen Schritts — Hinweis «Ob das ein Tausch ist …», eingetragen Tag 13,85."""
    def stand(t):
        if H10 <= t < H10 + timedelta(minutes=55):
            return w(H10)
        return w(t)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    p = await _dialog(db, aid, datetime(2026, 6, 8, 10, 30))
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T10:55:00")
    assert p["saetze"][1] == UNKLAR
    assert (await _dialog(db, aid, datetime(2026, 6, 8, 10, 55), eintragen=True))["eingetragen"] is True
    k, r, t = await _drei(db, aid)
    assert k[0] == r[0] == t[0] == 13.85


# ``test_p1_noch_kein_anderer_stand_stundenlauf`` (U3-K4) ersetzt Sitzung 5 durch
# ``test_sensorwechsel_s5_proben.test_a1_noch_nicht_gemeldet_traegt_nicht_ein`` (Bauplan Nr. 168: kein Eintrag ohne neuen Stand).


# ═══ P2 — Befund am abgehobenen Schritt mit ehrlichem Wortlaut ════════════════════════════════════════════════════════

def _reif_ladung(r: float = 0.05):
    l0 = datetime(2026, 6, 8, 10)

    def stand(t):
        b = w(min(t, l0), rate=r, start=ST - timedelta(days=400))
        if t > l0:
            b += 22.0 * min((t - l0).total_seconds(), 3 * 3600) / 3600 + r * max(0.0, (t - l0).total_seconds() - 3 * 3600) / 3600
        return round(b, 6)
    return stand


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_alter_wortlaut"])
async def test_p2_befund_am_einzelschritt(db, monkeypatch, sprengsatz):
    """K3-B2: reifer Zähler (400 Tage, 1,2 kWh am Tag), 22-kW-Ladung 10–13 Uhr, Publisher stündlich: der Befund nennt 11:00 mit dem
    Wortlaut des abgehobenen Schritts — Stände und Menge mit zwei Nachkommastellen, «eedc erkennt den Unterschied nicht», «War es
    gezählte Menge, stimmt der Wert». 12:00 und 13:00 heben sich gegen die 22 kWh um 11:00 nicht ab (Halt H-1 im Bericht: der
    Auftrag erwartete drei Befunde). Der Dialog nennt Zeit, Stände und Menge mit dem Hinweis «Ob das ein Tausch ist …».
    Sprengsatz: der Befund mit dem Wortlaut des eindeutigen Sprungs."""
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        monkeypatch.setattr(ms, "SATZ_WARUM_EINZELSCHRITT", ms.SATZ_WARUM)
    stand = _reif_ladung()
    aid = (await _anlage(db)).id
    await _vorlauf(db, aid, stand, 400)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN, takt=60))
    befunde = await _befund(db, aid)
    assert [(b.werte["stunde"], b.werte["art"], b.werte["getauscht"]) for b in befunde] == [
        ("2026-06-08T11:00", "sprung", "2026-06-08T11:00")]
    d = befunde[0].details
    assert d.startswith(ms.SATZ_SPRUNG_EINZELSCHRITT.format(uhr="11:00", vorher="5.484,10", nachher="5.506,10", menge="22,00",
                                                           einheit="kWh"))
    if sprengsatz:
        assert "eedc erkennt den Unterschied nicht" not in d
        return
    assert "eedc erkennt den Unterschied nicht" in d and "War es gezählte Menge, stimmt der Wert" in d
    assert ms.SATZ_WARUM not in d
    p = await _dialog(db, aid, H10 + timedelta(hours=1))
    assert (p["weg"], p["eintragen"]) == ("fortsetzung", True)
    assert p["saetze"][:2] == ["Der Zählerstand steht von 08.06.2026 10:00 bis 08.06.2026 11:00 Uhr still und ändert sich dann "
                               "von 5.484,10 auf 5.506,10 kWh. Trägst du den Tausch ein, zählt eedc diese 22,00 kWh nicht.", UNKLAR]


async def test_p2_eindeutiger_sprung_alter_wortlaut(db):
    """Ein eindeutiger Höhenwechsel (+2 000 kWh, Publisher alle fünf Minuten) behält den Wortlaut des Sprungs und im Dialog
    ``SATZ_FORTSETZUNG_ROH`` ohne Hinweis."""
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    def stand(t):
        return w(t) + (2000.0 if t >= T else 0.0)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    (b,) = await _befund(db, aid)
    assert ms.SATZ_WARUM in b.details and "eedc erkennt den Unterschied nicht" not in b.details
    p = await _dialog(db, aid, T)
    assert p["saetze"][0].startswith("eedc trägt den Tausch am 08.06.2026 10:20 Uhr ein: dort springt der Zählerstand")
    assert UNKLAR not in p["saetze"] and KEIN not in p["saetze"]


# ═══ P3 — «bleiben» nimmt ohne Höhenwechsel die zwei Stände um den Zeitpunkt (R3) ════════════════════════════════════════

def _bleiben_stand(welt: str):
    def stand(t):
        if welt == "ganzzahl":
            return float(math.floor(w(t) + 0.5))     # +1 um 10:30
        if welt == "takt15_last":                    # 10:30–10:45 6 kWh, sonst 0,6 kWh je Stunde
            return w(t) + 6.0 * min(max((t - (H10 + timedelta(minutes=30))).total_seconds(), 0.0), 900.0) / 900.0
        return w(t)
    return stand


@pytest.mark.parametrize("welt,takt,soll", [("takt60", 60, 14.4), ("ganzzahl", 5, 15.0), ("takt15_last", 15, 20.4),
                                             ("takt5", 5, 14.35)],
                         ids=["takt60-sofort", "ganzzahl-sofort", "takt15_last-sofort", "takt5-sofort"])
async def test_p3_bleiben_ohne_hoehenwechsel_nachtrag_gleich_sofort(db, monkeypatch, welt, takt, soll):
    """K3-B1, R3: Topic-Wechsel um 10:22, dasselbe Gerät zählt weiter; «bleiben» sofort — der Tag zählt 14,4 · 15,0 · 20,4 ·
    14,35. Der Weg «um 11:10 nachgetragen» und sein Sprengsatz (der Schritt der Stunde als Rand des Nachtrags) sind mit «Grund
    nachtragen» entfernt (Weg B, Sitzung B2); der Testname bleibt."""
    u = T + timedelta(minutes=2)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_bleiben_stand(welt), start=ST, ende=EN, takt=takt,
                                handlungen=[(u, _wechsel_topic(u, "fortsetzung"))]))
    k, r, t = await _drei(db, aid)
    assert k[0] == r[0] == t[0] == soll


# ═══ P4/P5 — «Regel 2» (Teil-B-Welt der U3-K3-Proben) ══════════════════════════════════════════════════════════════════

async def _verwerfen(db, svc, monkeypatch, falsch_seit=FS_B):
    from backend.tests.test_sensorwechsel_u3k3_proben import _verwerfen as v

    return await v(db, svc, monkeypatch, falsch_seit=falsch_seit)


def _c_neu(svc, erste_menge: float = 0.4, erste: datetime = H0_B, eid: str = "sensor.c", ende: datetime = datetime(2026, 6, 14)):
    """``eid`` als neue Statistik ab ``erste`` (Summe ab 0: erste Zeile ``erste_menge``, dann 0,5 je Stunde)."""
    from sqlalchemy import text

    from backend.tests import ha_lts_helfer as h

    mid = h.sensor(svc, eid, "kWh", has_sum=True)
    zeilen, s, t = [], 0.0, erste
    while t < ende:
        s = round(s + (erste_menge if t == erste else 0.5), 6)
        zeilen.append({"m": mid, "t": int(t.timestamp()), "w": s})
        t += timedelta(hours=1)
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"), zeilen)


async def _juni(db, svc, aid: int, eid: str) -> float:
    from backend.services.zuordnung_wechsel import monat

    zw.vergiss(db)
    (aus,) = await monat.monatswerte_je_abschnitt(db, aid, [svc.get_monatswerte([eid], 2026, 6)], [(2026, 6)])
    return round(next(x for x in aus.sensoren if x.sensor_id == eid).differenz, 3)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_falsch_seit_vor_der_ersten_zeile"])
async def test_p4_falsch_seit_auf_der_ersten_zeile(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """K3-B4 (Mutant N11): «Falsch seit» 12.06. 23:00 = die erste Zeile von C. «Regel 2» ohne Lücke: Kanal-Stunde 23 Uhr 0,4 wie
    HA, die Korrektur-Zeile trägt den Nullpunkt (keine Lücken-Zeile), die Stände liest der Lauf ab 13.06. 00:00 neu, der Juni
    aus HA über die Hülle 12,4 (0,4 + 24 × 0,5), die Vorschau nennt weder Lücke noch Handgriff. Sprengsatz: «Regel 2» nur, wenn
    «Falsch seit» vor der ersten Zeile liegt (U3-K3) ⇒ Lücke 23:00–00:00, Stunde 0,0."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    _c_neu(ha)
    if sprengsatz:
        echt = kr._luecke

        async def streng(db_, a, w0, ab, ha_svc):
            luecke, null = await echt(db_, a, w0, ab, ha_svc)
            if luecke is None and null is not None:
                return (kr._beginn(a, w0), kr._beginn(a, w0) + timedelta(hours=1)), None
            return luecke, null
        monkeypatch.setattr(kr, "_luecke", streng)
    a, _wb, key, la = await _verwerfen(db, ha, monkeypatch, falsch_seit=H0_B)
    stunde = await _kanal(db, key, H0_B, H0_B + timedelta(hours=1))
    if sprengsatz:
        assert la.luecke == (H0_B, H0_B + timedelta(hours=1)) and stunde == (0.0, None, None)
        return
    assert (la.luecke, la.nullpunkt, la.staende_neu) == (None, 0.0, (H0_B + timedelta(hours=1), AB_B))
    assert stunde == (0.4, None, None)
    zeilen = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == a.id)
                               .order_by(ZuordnungWechsel.id))).scalars().all()
    assert [(z.falsch_seit_ts, z.nachher, z.ansatz, z.stand_neu_null) for z in zeilen] == [(H0_B, QC_B, None, 0.0)]
    s = " ".join(kr.saetze(la))
    assert "füllt nichts" not in s and "setze «Falsch seit»" not in s
    assert await _juni(db, ha, a.id, "sensor.c") == 12.4


async def _bleiben_c_nach_d(db, aid: int, key: str):
    """Ein angesetzter Wechsel «bleiben» C → D (Schnitt an 13.06. 04:00): die Hülle liest den Juni je Abschnitt."""
    from backend.models.zuordnung_wechsel import ANSATZ_SCHNITT, GRUND_FORTSETZUNG

    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=datetime(2026, 6, 13, 4, 20),
                            ab_ts=datetime(2026, 6, 13, 5), vorher=QC_B, nachher={"art": "ha", "entity_id": "sensor.d"},
                            grund=GRUND_FORTSETZUNG, herkunft="wechsel", ansatz=ANSATZ_SCHNITT, stand_alt_ende=2.4,
                            stand_neu_null=0.8))
    await db.commit()


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_nullpunkt_im_abschnitt"])
async def test_p5_nullpunkt_bleibt_neben_spaeterem_bleiben(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """K3-B5 (Mutant N17): nach «verwerfen» mit «Regel 2» (C ab 12.06. 23:00) führt ein Wechsel «bleiben» von C nach D weiter: der
    Juni aus HA zählt C ab seiner ersten Zeile mit Anker 0 (0,4 + 4 × 0,5) und D ab dem Schnitt — wie ohne den späteren Wechsel um
    die erste Stunde von C. Sprengsatz: der Abschnitt von C ohne Nullpunkt (U3-K3) ⇒ 0,4 weniger."""
    from backend.services.zuordnung_wechsel import monat

    if sprengsatz:
        monkeypatch.setattr(monat, "_mit_nullpunkt", lambda teile, _null: teile)
    _c_neu(ha)
    _c_neu(ha, erste_menge=0.3, erste=datetime(2026, 6, 13, 2), eid="sensor.d")
    a, _wb, key, _la = await _verwerfen(db, ha, monkeypatch)
    await _bleiben_c_nach_d(db, a.id, key)
    d_teil = round(ha.get_fensterwerte([("sensor.d", monat._unix(datetime(2026, 6, 13, 4)),
                                         monat._unix(datetime(2026, 7, 1)), False)])[0].differenz, 3)
    # Weg B (B1): die Regel «Anfangsstand 0» deckt den Nullpunkt allgemein — der Sprengsatz zeigt dieselbe Zahl (bis B1: −0,4)
    assert await _juni(db, ha, a.id, "sensor.d") == round(2.4 + d_teil, 3)


# ═══ P6 — Sätze ═══════════════════════════════════════════════════════════════════════════════════════════════════════

def test_p6_satz_staende_ab():
    """K3-B7 Nr. 1: der Satz nennt, ab wann eedc neu liest — nicht, ab wann HA den Sensor führt."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    assert kr.SATZ_STAENDE_AB.format(zeit="13.06.2026 00:00") == (
        "Ab 13.06.2026 00:00 Uhr liest eedc die Zählerstände des richtigen Sensors neu und speichert sie.")


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_vorschau_bis_zum_ende_der_luecke"])
async def test_p6_vorschau_tage_mit_der_grenze_der_auskunft(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """K3-B7 Nr. 2 (``erste_101``): die erste Zeile von C liegt über der Grenze (150 kWh) — keine «Regel 2», die Lücke endet
    13.06. 00:00, der Kanal setzt C ab 12.06. 23:00 an. Die Vorschau teilt die Tage an derselben Kanal-Grenze, die die Auskunft
    danach im Kanal liest (``raender_der_verworfenen_zeit``: 12.06. 23:00) — der 12.06. ist dort ein Rand-Tag. Sprengsatz: die
    Vorschau bis zum Ende der Lücke (U3-K3) ⇒ 13.06. 00:00."""
    from backend.services.kanal import korrektur as kk
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import stueck

    grenzen = []
    echt_tage = stueck.tage_im_kanal

    async def merke(db_, anlage, key, von, bis, **kw):
        grenzen.append(bis)
        return await echt_tage(db_, anlage, key, von, bis, **kw)
    monkeypatch.setattr(stueck, "tage_im_kanal", merke)
    if sprengsatz:
        echt = kr._tage

        async def ohne_ha(db_, anlage, a, k, la, ha_svc=None):
            return await echt(db_, anlage, a, k, la, None)
        monkeypatch.setattr(kr, "_tage", ohne_ha)
    _c_neu(ha, erste_menge=150.0)
    a, _wb, key, la = await _verwerfen(db, ha, monkeypatch)
    assert (la.luecke, la.nullpunkt, la.kanal_traegt) == ((FS_B, datetime(2026, 6, 13)), None, True)
    r = await kk.raender_der_verworfenen_zeit(db, a.id, key, int(FS_B.timestamp()), int(datetime(2026, 6, 13).timestamp()))
    assert datetime.fromtimestamp(r[1]) == H0_B
    assert grenzen[0] == (datetime(2026, 6, 13) if sprengsatz else H0_B)


@pytest.mark.parametrize("zaehlt", [True, False])
async def test_p6_auskunft_zeit_bis_zur_ersten_zaehlenden_stunde(db, ha, monkeypatch, zaehlt):  # noqa: F811
    """K3-B7 Nr. 3 (``vorlauf_2344``): zählt die erste Kanal-Zeile des richtigen Sensors schon vor dem Ende der Zeit (der
    Stundenlauf übernahm sie), nennt die Auskunft die Zeit bis dorthin — «zählen in dieser Zeit nichts» bleibt wahr; zählt sie
    nicht, bleibt das Ende der Zeit (Mutant N13: der Grund nach Lage)."""
    from backend.services.daten_checker.datenquelle import verworfen as vw
    from backend.services.kanal import korrektur as kk

    _c_neu(ha, erste_menge=150.0)
    a, _wb, _key, _la = await _verwerfen(db, ha, monkeypatch)
    echt = kk.raender_der_verworfenen_zeit

    async def raender(*args, **kw):
        r = await echt(*args, **kw)
        return None if r is None else (r[0], r[1], zaehlt)
    monkeypatch.setattr(kk, "raender_der_verworfenen_zeit", raender)
    zw.vergiss(db)
    (v,) = await vw.verworfene_zeiten(db, a.id)
    lage = await vw.lage_der_zeit(db, await _anlage_frisch(db, a.id), v)
    meldung, details = vw.texte("Ladepunkt", lage)
    if zaehlt:
        assert lage.grund == vw.GRUND_KANAL_ERSTE and meldung.endswith("bis 12.06.2026 23:00 Uhr verworfen")
    else:
        assert lage.grund == vw.GRUND_KANAL and meldung.endswith("bis 13.06.2026 00:00 Uhr verworfen")
        assert vw.SATZ_GRUND[vw.GRUND_KANAL] in details


# ═══ P8 — überlebende Mutanten der Nachmessung U3-K3 ═══════════════════════════════════════════════════════════════════

def _ladung_davor(abstand: timedelta) -> list:
    """Standby 0,05 je fünf Minuten, eine Stunde Ladung mit 1,25 je fünf Minuten (15 kW) ``abstand`` vor 10:00, dann um 10:05
    +10 kWh in fünf Minuten (120 kW, über der Grenze 100 kW)."""
    beginn = datetime(2026, 6, 8, 10)
    ladung = {beginn - abstand + timedelta(minutes=5 * i) for i in range(12)}
    roh, t, s = [], beginn - timedelta(hours=48), 1000.0
    while t <= beginn + timedelta(minutes=30):
        s += 10.0 if t == beginn + timedelta(minutes=5) else (1.25 if t in ladung else 0.05)
        roh.append((t, round(s, 6)))
        t += timedelta(minutes=5)
    return roh


@pytest.mark.parametrize("abstand,sprung", [(timedelta(hours=10), False), (timedelta(hours=30), True)],
                         ids=["ladung_vor_10h", "ladung_vor_30h"])
def test_p8_n03_n04_vergleichsleistung_gleitendes_maximum_in_24h(abstand, sprung):
    """N03/N04: die Vergleichsleistung eines Schritts ist das **Maximum** der gewöhnlichen Leistungen der **24 Stunden** davor.
    Ladung vor 10 h (15 kW): 120 kW ist nicht das Zehnfache ⇒ kein Höhenwechsel (R1); die 10 kWh heben sich gegen 1,25 nicht ab
    (mit dem Minimum, 0,6 kW, wäre es ein Höhenwechsel). Ladung vor 30 h liegt außerhalb ⇒ Höhenwechsel (ohne Fenster keiner)."""
    roh = _ladung_davor(abstand)
    stunde = datetime(2026, 6, 8, 10)
    assert (rr.sprung_der_stunde(roh, stunde, 100.0) is not None) is sprung
    if not sprung:
        assert rr.abgehobener_schritt_der_stunde(roh, stunde, 100.0) is None


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_stand_feld"])
async def test_p8_n07_regel2_nie_am_stand_feld(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """N07: «Regel 2» gilt nur für Mengen-Felder — an einem Stand-Feld (Gas, Wasser) zählte Anker 0 den ganzen Zählerstand der
    ersten Zeile als Menge des Monats. Sprengsatz: das Feld gilt als Mengen-Feld ⇒ Nullpunkt 0."""
    from backend.core.field_definitions import STAND_FELDER
    from backend.services.snapshot import keys
    from backend.services.zuordnung_wechsel import nullpunkt

    if sprengsatz:
        monkeypatch.setattr(keys, "ist_stand_sensor_key", lambda _k: False)
    _c_neu(ha)
    a = await _anlage(db)
    feld = sorted(STAND_FELDER)[0]
    null = await nullpunkt.nullpunkt_der_reihe(db, a.id, ha, "sensor.c", f"basis:{feld}", H0_B)
    assert null == (0.0 if sprengsatz else None)


def _w(**kw):
    from backend.services.zuordnung_wechsel.zeitpunkt import Wechsel

    basis = dict(sensor_key="k", ab_ts=H0_B, vorher=QA_B, nachher=None, grund="korrektur", falsch_seit_ts=FS_B, erklaert_ts=None,
                 aufgehoben_durch=None, id=2)
    basis.update(kw)
    return Wechsel(**{k: v for k, v in basis.items() if k in Wechsel.__dataclass_fields__})


@pytest.mark.parametrize("aufgehoben", [None, 7])
def test_p8_n10_aufgehobene_luecken_zeile_traegt_keinen_nullpunkt(aufgehoben):
    """N10: nur eine nicht aufgehobene Lücken-Zeile trägt den Nullpunkt in die Hülle des Monats."""
    from backend.services.zuordnung_wechsel import nullpunkt

    korr = _w(id=1, ab_ts=AB_B, nachher=QC_B)
    luecke = _w(stand_neu_null=0.0, aufgehoben_durch=aufgehoben)
    assert nullpunkt.abschnitte({"k": [korr, luecke]}) == ({} if aufgehoben else {"k": ("sensor.c", H0_B)})


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_summe_gleich_stand"])
def test_p8_n14_arm_ohne_bezug_nur_wenn_summe_und_stand_gleich(monkeypatch, sprengsatz):
    """N14: ohne Bezug meldet der Arm «Sprung» über der Grenze nur, wenn Summe und Stand denselben Zuwachs zeigen — springt nur
    die Summe (HA hat sie angepasst, der Zählerstand läuft gewöhnlich), ist es kein Sprung des Zählers. Sprengsatz: ohne die
    Bedingung ⇒ ein Befund."""
    if sprengsatz:
        monkeypatch.setattr(zs, "_gleich", lambda *_a: True)
    t0 = int(datetime(2026, 6, 8).timestamp())
    zeilen = [(t0, 50.0, 0.0), (t0 + 3600, 50.6, 0.6), (t0 + 7200, 51.2, 150.6)]
    funde = zs.finde_standspruenge(zeilen, grenze=100.0)
    assert len(funde) == (1 if sprengsatz else 0)
