"""Sensorwechsel — Korrekturrunde U3-K4 (Bauplan Nr. 164/165, Nachmessung ``opus-berichte/SENSORWECHSEL-U3K3-NACHMESSUNG-…``
K3-B1 … K3-B7) — Proben mit Sprengsatz.

* **P1–P3 in der Fassung von Bauplan Nr. 166** (Entscheid Gernot 20.11.2026: bei MQTT entscheidet der Anwender; die Erkennung
  zeigt, sie entscheidet nicht): der Dialog «Zähler getauscht» nimmt ohne Höhenwechsel den nächsten anderen Stand
  (``rohstand.naechster_anderer_um``), trägt ein und sagt per Hinweis, ob sich der Schritt abhebt (``rohstand_rand.abgehoben``:
  ≥ 90 % der Stunde und mehr als das Zehnfache des größten gewöhnlichen Schritts der 24 Stunden davor); der Befund
  «Zählerstand springt (MQTT)» nennt eine Stunde bei Höhenwechsel oder abgehobenem Schritt, dort mit dem Wortlaut, dass eedc
  Tausch und gezählte Menge nicht unterscheidet; «Bisherige Werte bleiben» nimmt ohne Höhenwechsel die zwei Stände um den
  Zeitpunkt (nachgetragen = sofort) und nennt einen Schritt der Stunde, der sich abhebt.
* **P8** Proben für die überlebenden Mutanten N03, N04, N13, N14.

Die Proben P4–P6 und N07, N10, N11, N17 («Regel 2», Nullpunkt, Sätze und Auskunft der verworfenen Zeit) sind mit der Korrektur
entfernt (Weg B, Sitzung B3a). Welten wie U3-K3 (``test_sensorwechsel_u3k3_proben``: Netzbezug 0,6 kWh je Stunde ab 5 000,
Ereignis 08.06.2026 10:20). Zeitpunkte im Juni; die Datei liest keine Uhr und läuft
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
from backend.tests.test_sensorwechsel_u3b_proben import (  # noqa: F401
    NETZ, Saat, _anlage_frisch, _wechsel_topic, _wechsel_zeilen, betrieb, kanal_stunde, zw,
)
from backend.tests.test_sensorwechsel_u3k3_proben import (  # noqa: F401
    EN, R, ST, T, TAGE, _anlage, _befund, _dialog, _drei, _vorlauf, w,
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
