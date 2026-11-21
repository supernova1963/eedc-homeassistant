"""Sensorwechsel — Korrekturrunde U3-K3 (Bauplan Nr. 163, Nachmessung ``opus-berichte/SENSORWECHSEL-U3K2-NACHMESSUNG-…``
K2-B1 … K2-B6) — Proben mit Sprengsatz, Teil A «Zähler getauscht» über MQTT und Befund «Zählerstand springt (MQTT)».

* **A1 (K2-B1)** die Vergleichsleistung zählt Schritte nicht mit, die selbst Höhenwechsel sind (``rohstand_rand._hoehenwechsel_alle``):
  ein zweiter kurzer Nullstand binnen 24 h bleibt ein Höhenwechsel — Tag 14,2 bzw. 14,3 je Tag bzw. 14,1 in einer Stunde in
  Kanal, Reihe und Tagesansicht, der zweite Befund nennt die Zeit der Rückkehr; dieselbe Regel ohne Grenze der Anlage.
* **A2 (K2-B2, K2-B3)** eine Regel, drei Ergebnisse (``rohstand_rand.einordnung_der_stunde``): eindeutig · Einzelschritt (ein
  Schritt nach oben trägt mindestens 90 % des Zuwachses der Stunde — eintragbar auf das Wort des Anwenders, der Satz nennt die
  Menge, die dann nicht zählt) · kein Sprung. Der Dialog fragt den Befund nicht mehr; der Arm «Sprung» des Befunds nennt eine
  Stunde mit Rohständen nur bei eindeutig oder Einzelschritt (reifer Zähler + 22-kW-Ladung: kein Befund). Ein bestehender Eintrag
  gilt am Einzelschritt als Höhenwechsel (Nachtrag «bleiben»). Benannte Grenze: zwei vergleichbare Schritte in einer Stunde.
* **A3 (K2-B5)** der Arm «Sprung» über der Grenze gilt auch ohne Bezug im neuen Abschnitt: nach dem ersten Eintrag bleibt der
  zweite Befund eines Fremdstands über zwei Stunden stehen; die erste gewöhnliche Stunde eines neuen Abschnitts ist keiner.
* **A4 (K2-B4)** «Dieser Tausch ist schon eingetragen.» vor «kein Sprung zu sehen».
* **A5 (K2-B6, überlebende Mutanten Z06/Z09)** zwei MQTT-Zähler werden nicht verwechselt; «Getauscht am» des Befunds an einem
  Rückgang ist der Rohstand des Rückgangs.

Welt wie die Nachmessung (``nm-u3k2/test_nm_k2_mqtt*.py``): Netzbezug 0,6 kWh je Stunde ab 5 000 (Tag 14,4), Ereignis 08.06.2026
10:20, echter Stundenlauf. Zeitpunkte im Juni (fern jeder Umstellung); die Datei liest keine Uhr und läuft auch mit
``TZ=Pacific/Auckland`` und ``TZ=UTC``. Schwesterdateien: test_sensorwechsel_u3k2_proben.py, test_sensorwechsel_u3k_proben.py,
test_sensorwechsel_u3b_proben.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import insert, select

from backend.core.berechnungen import rohstand_rand as rr
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.core.berechnungen import zaehlerstand_sprung as zs
from backend.tests import factories
from backend.tests.test_sensorwechsel_u3b_proben import (  # noqa: F401 — Saat, Leser, Schlüssel der U3b-Proben
    MK, NETZ, NETZ_FID, Kanal, KanalQuelle, KanalStatistik, MqttEnergySnapshot, Saat, _anlage_frisch, _nachtrag_bleiben,
    _wechsel_topic, _wechsel_zeilen, betrieb, kanal_tag, reihe_tag, tagesansicht, zw,
)

R = 0.6
B0 = 5000.0
ST = datetime(2026, 6, 5)
EN = datetime(2026, 6, 11)
T = datetime(2026, 6, 8, 10, 20)
TAG = T.date()
TAGE = [TAG, TAG + timedelta(days=1)]


def w(t: datetime, rate: float = R, basis: float = B0, start: datetime = ST) -> float:
    return round(basis + rate * (t.timestamp() - start.timestamp()) / 3600, 6)


async def _anlage(db, kwp: float = 10.0):
    a = await factories.anlage(db, anlagenname="U3K3", leistung_kwp=kwp, sensor_mapping={"basis": {}, "investitionen": {}})
    await db.commit()
    return a


async def _vorlauf(db, aid: int, stand, tage: int):
    """Kanal-Geschichte ``tage`` Tage vor ``ST`` (Stundenzeilen der Mitschrift, wie der Stundenlauf sie schriebe)."""
    k = Kanal(anlage_id=aid, key=NETZ, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    e0 = int((ST - timedelta(days=tage)).timestamp())
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=e0, familie="mitschrift", statistic_id=MK, offset=0.0))
    zeilen, e, summe, vorher = [], e0, 0.0, stand(datetime.fromtimestamp(e0 - 300))
    while e < ST.timestamp():
        st = stand(datetime.fromtimestamp(e + 3300))
        summe += st - vorher
        zeilen.append({"kanal_id": k.id, "start_ts": e, "state": round(st, 6), "sum": round(summe, 6), "familie": "mitschrift"})
        vorher, e = st, e + 3600
    await db.execute(insert(KanalStatistik), zeilen)
    await db.commit()


async def _befund(db, aid: int) -> list:
    from backend.services.daten_checker import DatenChecker

    zw.vergiss(db)
    return await DatenChecker(db)._check_mqtt_zaehlerstand_springt(await _anlage_frisch(db, aid))


async def _dialog(db, aid: int, zeit: datetime, *, eintragen: bool = False) -> dict:
    from backend.api.routes import sensorwechsel as sw

    zw.vergiss(db)
    req = sw.ZaehlerGetauschtRequest(getauscht_am=zeit)
    return await (sw.zaehler_getauscht if eintragen else sw.pruefe_zaehler_getauscht)(aid, NETZ_FID, req, db)


async def _drei(db, aid: int, tage=TAGE) -> list:
    return [[await kanal_tag(db, aid, d) for d in tage], [await reihe_tag(db, aid, d) for d in tage],
            await tagesansicht(db, aid, tage)]


async def _knopf_bis_leer(db, aid: int, n: int = 4) -> list[str]:
    """Wie der Anwender: so oft der Befund eine Stunde nennt, den Knopf «Zähler getauscht» drücken und eintragen. Returns: die
    Zeiten «Getauscht am» der Befunde in Folge."""
    zeiten = []
    for _ in range(n):
        b = await _befund(db, aid)
        if not b:
            break
        zeit = datetime.fromisoformat(b[0].werte["getauscht"])
        zeiten.append(b[0].werte["getauscht"])
        assert (await _dialog(db, aid, zeit, eintragen=True))["eingetragen"] is True
    return zeiten


def _alt_vergleich(roh, grenze_kw):
    """Sprengsatz A1: die Vergleichsleistung wie bis U3-K2 — jeder Schritt nach oben der 24 h davor, auch ein Höhenwechsel."""
    out = [False] * len(roh)
    for i in range(1, len(roh)):
        a, b = roh[i - 1], roh[i]
        g = max((rr.leistung(y[1] - x[1], (y[0] - x[0]).total_seconds()) for x, y in zip(roh[:i - 1], roh[1:i])
                 if y[0] >= a[0] - rr.BEZUG and y[1] > x[1] and y[0] > x[0]), default=0.0)
        out[i] = rr.hoehenwechsel(b[1] - a[1], rr.seit_dem_letzten_anderen(roh, i), g, grenze_kw)
    return out


# ═══ A1 — zweiter kurzer Nullstand binnen 24 Stunden ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_vergleich_mit_hoehenwechseln"])
@pytest.mark.parametrize("zweite,soll,rueckkehr", [
    (datetime(2026, 6, 8, 15, 20), [14.2, 14.4], "2026-06-08T15:25"),
    (datetime(2026, 6, 9, 9, 20), [14.3, 14.3], "2026-06-09T09:25"),
    (datetime(2026, 6, 8, 10, 40), [14.1, 14.4], None),
], ids=["gleicher_tag", "23h_spaeter", "gleiche_stunde"])
async def test_a1_zweiter_nullstand_binnen_24h(db, monkeypatch, zweite, soll, rueckkehr, sprengsatz):
    """Das Gerät meldet um 10:20 und noch einmal binnen 24 h je fünf Minuten 0 (20 Tage Vorlauf). Nach den Einträgen über den Knopf
    des Befunds zählen Kanal, Reihe und Tagesansicht je Tag 14,4 minus die Minuten zwischen den Rand-Ständen; der zweite Befund
    nennt die Rückkehr (in derselben Stunde nennt ein Befund die Spanne beider). Sprengsatz: die Vergleichsleistung mit der
    Rückkehr des ersten Ereignisses ⇒ das zweite ist kein Höhenwechsel, der Tag bleibt bei 5 000 kWh."""
    if sprengsatz:
        monkeypatch.setattr(rr, "_hoehenwechsel_alle", _alt_vergleich)

    def stand(t):
        return 0.0 if (T <= t < T + timedelta(minutes=5) or zweite <= t < zweite + timedelta(minutes=5)) else w(t)
    aid = (await _anlage(db)).id
    await _vorlauf(db, aid, w, 20)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    zeiten = await _knopf_bis_leer(db, aid)
    k, r, t = await _drei(db, aid)
    if sprengsatz:
        assert max(x for x in k if x is not None) > 1000.0
        return
    assert k == r == t == soll
    assert zeiten[0] == ("2026-06-08T10:25" if rueckkehr else "2026-06-08T10:45")
    if rueckkehr:
        assert zeiten[1] == rueckkehr
    assert await _befund(db, aid) == []


def test_a1_regel_ohne_grenze_dieselbe():
    """Ohne Grenze der Anlage (andere Einheit als kWh): zwei kurze Nullstände im Abstand von fünf Stunden — beide Rückkehren
    sind Höhenwechsel. Mit der Vergleichsleistung bis U3-K2 wäre es die zweite nicht."""
    h1, h2 = datetime(2026, 6, 8, 10), datetime(2026, 6, 8, 15)

    def f(t):
        return 0.0 if (h1 + timedelta(minutes=20) <= t < h1 + timedelta(minutes=25)
                       or h2 + timedelta(minutes=20) <= t < h2 + timedelta(minutes=25)) else 800.0 + 0.05 * (t - h1).total_seconds() / 3600
    roh, t = [], h1 - timedelta(hours=24)
    while t < h2 + timedelta(hours=1):
        roh.append((t, round(f(t), 6)))
        t += timedelta(minutes=5)
    for grenze in (None, 100.0):
        assert [roh[i][0].minute for i in rr.hoehenwechsel_der_stunde(roh, h2, grenze)] == [20, 25]
        a, b = rr.sprung_der_stunde(roh, h2, grenze)
        assert (a[0], b[0]) == (h2 + timedelta(minutes=15), h2 + timedelta(minutes=25))
    alt = _alt_vergleich(roh, None)
    assert [roh[i][0].minute for i in range(len(roh)) if alt[i] and h2 <= roh[i][0]] == [20]


# ═══ A2 — eine Regel: eindeutig · Einzelschritt · kein Sprung ═════════════════════════════════════════════════════════

def _stunde(schritte: list[float], beginn=datetime(2026, 6, 8, 10)) -> list:
    """Ein Tag gleichmäßiger Schritte von 0,05 davor, dann die Schritte der Stunde (je fünf Minuten)."""
    roh, t, s = [], beginn - timedelta(hours=24), 1000.0
    while t < beginn:
        s += 0.05
        roh.append((t, round(s, 6)))
        t += timedelta(minutes=5)
    for d in schritte:                  # der erste Schritt endet um 10:00 (Paar 09:55 → 10:00)
        s += d
        roh.append((t, round(s, 6)))
        t += timedelta(minutes=5)
    return roh


@pytest.mark.parametrize("schritte,abgehoben", [
    ([0.0, 0.0, 0.0, 9.0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1], True),     # 9,0 von 9,8 = 92 %
    ([0.0, 0.0, 0.0, 9.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0], True),    # 90,02 %
    ([0.0, 0.0, 0.0, 8.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.1], False),    # 89 %
    ([0.0] * 11 + [0.6], True),                        # ein einziger Schritt, 12 × die 0,05 davor
    ([0.0] * 11 + [0.3], False),                       # U3-K4: 6 × die 0,05 davor hebt sich nicht ab (K3-B3)
    ([1.8333] * 12, False),                                                   # Ladung über die Stunde
    ([0.0, 0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 7.9, 0.0, 0.0, 0.0, 0.0], False),    # zwei vergleichbare Schritte
], ids=["92_prozent", "90_02_prozent", "89_prozent", "ein_schritt", "ein_schritt_ohne_abstand", "ladung", "zwei_schritte"])
def test_a2_abgehoben_rein(schritte, abgehoben):
    """U3-K4 (Bauplan Nr. 166, neue Fassung von ``test_a2_einordnung_rein``): «hebt sich ab» zeigt nur (Hinweis und Befund) —
    ≥ 90 % der Stunde und mehr als das Zehnfache des größten gewöhnlichen Schritts der 24 h davor."""
    roh = _stunde(schritte)
    g = rr.abgehobener_schritt_der_stunde(roh, datetime(2026, 6, 8, 10), 100.0)
    assert (g is not None) is abgehoben
    if abgehoben:
        assert rr.menge_des_schritts((roh[g - 1], roh[g])) == pytest.approx(max(schritte))


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_befund_ohne_rohstand_regel"])
async def test_a2_reifer_zaehler_ladung_kein_befund(db, monkeypatch, sprengsatz):
    """Reifer Zähler (400 Tage, 1,2 kWh am Tag), am 08.06. von 10 bis 13 Uhr eine Ladung mit 22 kW: kein Befund (die Rohstände
    zeigen zwölf gleiche Schritte je Stunde), Tag 67,05 in allen drei Lesern. U3-K4 (Bauplan Nr. 166, neue Erwartung — bis U3-K3
    lehnte der Dialog ab): der Dialog ist eintragbar und sagt «Einen Sprung sieht eedc an dieser Zeit nicht.». Sprengsatz: der
    Befund ohne die Regel der Rohstände ⇒ drei Fehlalarme (10, 11, 12 Uhr)."""
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        async def immer(*_a, **_k):
            return True
        monkeypatch.setattr(ms, "_bestaetigt", immer)
    r, l0 = 0.05, datetime(2026, 6, 8, 10)

    def stand(t):
        b = w(min(t, l0), rate=r, start=ST - timedelta(days=400))
        if t > l0:
            b += 22.0 * min((t - l0).total_seconds(), 3 * 3600) / 3600 + r * max(0.0, (t - l0).total_seconds() - 3 * 3600) / 3600
        return round(b, 6)
    aid = (await _anlage(db)).id
    await _vorlauf(db, aid, stand, 400)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    befunde = await _befund(db, aid)
    if sprengsatz:
        assert [e.werte["stunde"][-5:] for e in befunde] == ["10:00", "11:00", "12:00"]
        return
    assert befunde == []
    p = await _dialog(db, aid, T)
    assert (p["weg"], p["eintragen"]) == ("fortsetzung", True)
    assert p["saetze"][1] == "Einen Sprung sieht eedc an dieser Zeit nicht."
    assert await _drei(db, aid, [TAG]) == [[67.05], [67.05], [67.05]]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_hebt_sich_nie_ab"])
async def test_a2_tausch_nach_pause_eintragbar_mit_satz(db, monkeypatch, sprengsatz):
    """Junger Zähler, Publisher 2 h stumm, um 10:20 meldet ein neues Gerät +90 (Leistung 45 kW über die stille Zeit — kein
    Höhenwechsel): kein Befund; der Dialog trägt auf das Wort des Anwenders ein und nennt die stille Zeit und die Menge, die dann
    nicht zählt, dazu (U3-K4, Bauplan Nr. 166) den Hinweis «Ob das ein Tausch ist …»; danach Tag 13,2 in Kanal, Reihe und
    Tagesansicht. Sprengsatz: der Schritt höbe sich nie ab ⇒ der Hinweis «Einen Sprung sieht eedc …» (eintragbar bleibt er)."""
    if sprengsatz:
        monkeypatch.setattr(rr, "abgehoben", lambda *_a, **_k: False)

    def stand(t):
        if T - timedelta(hours=2) <= t < T:
            return w(T - timedelta(hours=2))
        return w(t) + (90.0 if t >= T else 0.0)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    assert await _befund(db, aid) == []
    p = await _dialog(db, aid, T)
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T10:20:00")
    assert p["saetze"][0] == ("Der Zählerstand steht von 08.06.2026 08:20 bis 08.06.2026 10:20 Uhr still und ändert sich dann "
                              "von 5.048,20 auf 5.139,40 kWh. Trägst du den Tausch ein, zählt eedc diese 91,20 kWh nicht.")
    if sprengsatz:
        assert p["saetze"][1] == "Einen Sprung sieht eedc an dieser Zeit nicht."
        return
    assert p["saetze"][1] == "Ob das ein Tausch ist oder eine gezählte Menge, erkennt eedc nicht."
    assert (await _dialog(db, aid, T, eintragen=True))["eingetragen"] is True
    assert await _drei(db, aid, [TAG]) == [[13.2], [13.2], [13.2]]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_naechsten_anderen"])
async def test_a2_neues_geraet_erst_null_zweiter_eintrag(db, monkeypatch, sprengsatz):
    """Neues Gerät meldet ab 10:20 drei Stunden 0, ab 13:20 seinen Stand 300: der Anwender trägt zuerst 10:20 ein (Höhenwechsel
    nach Leistung), dann 13:20 (der nächste andere Stand nach drei Stunden 0) — Tag 12,55. Sprengsatz: ohne den nächsten anderen
    Stand (R2) ⇒ kein zweiter Eintrag (Sitzung 5: «noch nicht gemeldet»), der Tag bleibt nicht 12,55."""
    if sprengsatz:
        async def keiner(*_a, **_k):
            return None
        from backend.services.zuordnung_wechsel import rohstand
        monkeypatch.setattr(rohstand, "naechster_anderer_um", keiner)
    t2 = T + timedelta(hours=3)

    def stand(t):
        if t < T:
            return w(t)
        return 0.0 if t < t2 else round(300.0 + R * (t - t2).total_seconds() / 3600, 6)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    assert (await _dialog(db, aid, T, eintragen=True))["eingetragen"] is True
    p = await _dialog(db, aid, t2)
    if sprengsatz:                          # Sitzung 5: ohne anderen Stand trägt der Dialog nicht ein
        assert (await _dialog(db, aid, t2, eintragen=True))["eingetragen"] is False
        assert (await _drei(db, aid, [TAG]))[0] != [12.55]
        return
    assert p["saetze"][0].startswith("Der Zählerstand steht von 08.06.2026 10:20 bis 08.06.2026 13:20 Uhr still und ändert "
                                     "sich dann von 0,00 auf 300,00 kWh.")  # U3-K4: zwei Nachkommastellen
    assert (await _dialog(db, aid, t2, eintragen=True))["eingetragen"] is True
    assert await _drei(db, aid, [TAG]) == [[12.55], [12.55], [12.55]]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_hinweis"])
async def test_a2_bestehender_wechsel_bleiben_am_einzelschritt(db, monkeypatch, sprengsatz):
    """Ein Wechsel des Topics um 10:22 ohne Grund (der neue Publisher meldet ab 10:20 +90 nach 2 h Stille), um 11:10 «bleiben»
    nachgetragen. U3-K4 (Bauplan Nr. 166 R3, neue Erwartung — U3-K3 nahm den Einzelschritt als Rand, 13,2): «bleiben» nimmt die
    zwei Stände um 10:22, der Schritt 10:15 → 10:20 zählt (104,35 — der Auftrag nannte 104,4; die fünf Minuten zwischen den
    Rand-Ständen 10:20/10:25 zählen nicht, wie «bleiben» Takt 5: 14,35); die Prüf-Antwort nennt ihn (``SATZ_BLEIBEN_SCHRITT``).
    Danach «Zähler getauscht» um 10:20 — gemessen, ob der zweite Eintrag geht. Sprengsatz: ohne den Hinweis."""
    from backend.core.zahlenformat import fmt_zahl
    from backend.services.zuordnung_wechsel import rohstand

    if sprengsatz:
        async def nichts(*_a, **_k):
            return None
        monkeypatch.setattr(rohstand, "satz_bleiben_schritt", nichts)

    def stand(t):
        if T - timedelta(hours=2) <= t < T:
            return w(T - timedelta(hours=2))
        return w(t) + (90.0 if t >= T else 0.0)
    aid = (await _anlage(db)).id
    u = T + timedelta(minutes=2)
    satz = []

    async def pruefen_und_bleiben(db_, aid_):
        from backend.services.zuordnung_wechsel import nachtrag as nt

        zw.vergiss(db_)
        row = (await _wechsel_zeilen(db_, aid_))[0]
        satz.append(nt.antwort(await nt.lage(db_, await _anlage_frisch(db_, aid_), row.id), "Netzbezug")["bleiben_satz"])
        await _nachtrag_bleiben(db_, aid_)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN, handlungen=[(u, _wechsel_topic(u, None)),
                                                                       (T + timedelta(minutes=50), pruefen_und_bleiben)]))
    alt, neu = w(T - timedelta(hours=2)), w(T) + 90.0
    hinweis = rohstand.SATZ_BLEIBEN_SCHRITT.format(zeit="08.06.2026 10:20", alt=fmt_zahl(alt, 2), neu=fmt_zahl(neu, 2),
                                                   menge=fmt_zahl(neu - alt, 2), einheit="kWh")
    assert (hinweis in satz[0]) is not sprengsatz
    assert await _drei(db, aid, [TAG]) == [[104.35], [104.35], [104.35]]   # die fünf Minuten 10:20–10:25 liegen in der Naht
    if sprengsatz:
        return
    # Gemessen (Bericht U3-K4, Halt H-2): der zweite Eintrag geht NICHT — «Dieser Tausch ist schon eingetragen.», weil die
    # Zeile «bleiben» dasselbe ``ab_ts`` (11:00) trägt wie ein Tausch um 10:20 (``zaehler_getauscht._schon``).
    p = await _dialog(db, aid, T)
    assert (p["weg"], p["eintragen"], p["saetze"]) == ("fortsetzung", False, ["Dieser Tausch ist schon eingetragen."])


async def test_a2_zwei_vergleichbare_schritte_benannte_grenze(db):
    """Ein Sprung in zwei Schritten (+8,0 um 10:20, +7,9 um 10:40) an einem reifen Zähler — kein Befund; U3-K4 (Bauplan
    Nr. 166, neue Erwartung — bis U3-K3 abgelehnt, die benannte Grenze entfällt): der Dialog ist an beiden Zeiten eintragbar und
    sagt «Einen Sprung sieht eedc an dieser Zeit nicht.»; ohne Eintrag zählt der Tag beide Schritte (17,34)."""
    r = 0.06

    def stand(t):
        return w(t, rate=r, start=ST - timedelta(days=400)) + (8.0 if t >= T else 0.0) + (7.9 if t >= T + timedelta(minutes=20) else 0.0)
    aid = (await _anlage(db)).id
    await _vorlauf(db, aid, stand, 400)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    assert await _befund(db, aid) == []
    for zeit in (T, T + timedelta(minutes=20)):
        p = await _dialog(db, aid, zeit)
        assert p["weg"] == "fortsetzung" and p["getauscht_am"] == zeit.isoformat()
        assert p["saetze"][1] == "Einen Sprung sieht eedc an dieser Zeit nicht."
    assert (await _drei(db, aid, [TAG]))[0] == [17.34]


# ═══ A3 — Arm über der Grenze auch ohne Bezug ═════════════════════════════════════════════════════════════════════════

async def test_a3_zweiter_befund_bleibt_nach_dem_ersten_eintrag(db):
    """Ein Fremdstand 777 von 10:50 bis 11:10 (20 Tage Vorlauf): zwei Befunde (Neubeginn 10:50, Sprung 11:10). Nach dem ersten
    Eintrag beginnt an der Stunde ein neuer Abschnitt ohne Bezug — der Befund 11:10 bleibt (die Menge liegt über der Grenze);
    nach beiden Einträgen Tag 14,15."""
    def stand(t):
        return 777.0 if T + timedelta(minutes=30) <= t < T + timedelta(minutes=50) else w(t)
    aid = (await _anlage(db)).id
    await _vorlauf(db, aid, w, 20)
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    vor = [(e.werte["art"], e.werte["getauscht"]) for e in await _befund(db, aid)]
    assert vor == [("neubeginn", "2026-06-08T10:50"), ("sprung", "2026-06-08T11:10")]
    assert (await _dialog(db, aid, T + timedelta(minutes=30), eintragen=True))["eingetragen"] is True
    nach = [(e.werte["art"], e.werte["getauscht"]) for e in await _befund(db, aid)]
    assert nach == [("sprung", "2026-06-08T11:10")]
    assert await _knopf_bis_leer(db, aid) == ["2026-06-08T11:10"]
    assert await _drei(db, aid, [TAG]) == [[14.15], [14.15], [14.15]]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_bezug_still"])
def test_a3_kern_ueber_der_grenze_ohne_bezug(monkeypatch, sprengsatz):
    """Kern: ein Abschnitt beginnt um 10 Uhr; die Zeile 11 Uhr zählt 4 273 kWh (über der Grenze 100) — ein Sprung ohne Maß. Die
    erste gewöhnliche Stunde eines neuen Abschnitts (0,6 kWh) ist keiner. Sprengsatz: ohne Bezug still (bis U3-K2)."""
    if sprengsatz:
        monkeypatch.setattr(zs, "grenze_der_zeile", lambda grenze, z0, z1: float("inf"))
    h = int(datetime(2026, 6, 8, 10).timestamp())
    sprung = [(h, 777.0, 0.0), (h + 3600, 5050.35, 4273.35), (h + 7200, 5050.95, 4273.95)]
    erg = zs.finde_standspruenge(sprung, grenze=100.0)
    assert [(x.art, x.start_ts, x.mass) for x in erg] == ([] if sprengsatz else [(zs.SPRUNG, h + 3600, 0.0)])
    gewoehnlich = [(h, 5000.0, 0.0), (h + 3600, 5000.6, 0.6), (h + 7200, 5001.2, 1.2)]
    assert zs.finde_standspruenge(gewoehnlich, grenze=100.0) == []


# ═══ A4 — «schon eingetragen» vor «kein Sprung» ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_schon"])
async def test_a4_schon_eingetragen_geht_vor(db, monkeypatch, sprengsatz):
    """Eingetragen für 10:18 (um 10:23, Sitzung 5: erst wenn ein anderer Stand gespeichert ist); die Rohstände zeigen keinen
    Sprung. Das zweite
    Öffnen zur selben Zeit sagt «Dieser Tausch ist schon eingetragen.». Sprengsatz: ohne die Sperre ⇒ ein zweiter Eintrag
    angeboten (U3-K4: die Ablehnung «kein Sprung» gibt es nicht mehr)."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    if sprengsatz:
        monkeypatch.setattr(zg, "_schon", lambda wechsel, ab: False)
    t = T - timedelta(minutes=2)

    async def eintrag(db, aid):
        assert (await _dialog(db, aid, t, eintragen=True))["eingetragen"] is True
    aid = (await _anlage(db)).id
    # Sitzung 5 (Bauplan Nr. 168): eingetragen wird erst, wenn ein anderer Stand gespeichert ist — hier nach dem Stand 10:20
    await betrieb(db, aid, Saat(w, start=ST, ende=EN, handlungen=[(T + timedelta(minutes=3), eintrag)]))
    p = await _dialog(db, aid, t)
    if sprengsatz:
        assert p["eintragen"] is True
        return
    assert p["eintragen"] is False
    assert p["saetze"] == ["Dieser Tausch ist schon eingetragen."]


# ═══ A5 — überlebende Mutanten der Nachmessung (Z06, Z09) ═════════════════════════════════════════════════════════════

ESP, ESP_MK = "basis:einspeisung", "einspeisung_kwh"
T0 = datetime(2025, 5, 1)


async def _welt_roh(db, kwp: float, zaehler: list) -> int:
    """MQTT-Kanäle «Eigene Summe» ``(key, mqtt_key, f)`` mit Stundenzeilen über 400 Tage und Rohständen der letzten zwei Tage
    (ohne Stundenlauf)."""
    a = await _anlage(db, kwp)
    ende = datetime(2026, 6, 9, 6)
    beginn = datetime(2026, 6, 9) - timedelta(days=400)
    for key, mk, f in zaehler:
        k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art="sum")
        db.add(k)
        await db.flush()
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(beginn.timestamp()), familie="mitschrift", statistic_id=mk, offset=0.0))
        zeilen, e, summe, vorher = [], int(beginn.timestamp()), 0.0, f(beginn)
        while e < ende.timestamp():
            st = f(datetime.fromtimestamp(e + 3300))
            summe += st - vorher
            zeilen.append({"kanal_id": k.id, "start_ts": e, "state": round(st, 6), "sum": round(summe, 6), "familie": "mitschrift"})
            vorher, e = st, e + 3600
        await db.execute(insert(KanalStatistik), zeilen)
        roh, t = [], datetime(2026, 6, 7)
        while t < ende:
            roh.append({"anlage_id": a.id, "timestamp": t, "energy_key": mk, "value_kwh": round(f(t), 6)})
            t += timedelta(minutes=5)
        await db.execute(insert(MqttEnergySnapshot), roh)
    await db.commit()
    return a.id


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_schluessel_vertauscht"])
async def test_a5_zwei_mqtt_zaehler_nicht_verwechselt(db, monkeypatch, sprengsatz):
    """Zwei reife MQTT-Zähler (200 kWp, Grenze 300): der Netzbezug springt um 10:20 um +20 kWh (ein Einzelschritt), die Einspeisung
    zählt in derselben Stunde 22 kW gleichmäßig (kein Sprung). Der Kern nennt beide Stunden; der Befund bleibt nur am Netzbezug,
    mit der Zeit seines Schritts. Sprengsatz: die Regel der Rohstände liest für jeden Fund den Schlüssel des Netzbezugs ⇒ die
    Ladung der Einspeisung bleibt als Befund stehen."""
    from backend.services.zuordnung_wechsel import rohstand

    if sprengsatz:
        echt, echt_ab = rohstand.sprung_um, rohstand.abgehoben_in_der_stunde

        async def falsch(db_, aid_, _mk, t, **k):
            return await echt(db_, aid_, MK, t, **k)

        async def falsch_ab(db_, aid_, _mk, t, **k):          # U3-K4: der Befund liest auch «hebt sich ab» je Schlüssel
            return await echt_ab(db_, aid_, MK, t, **k)
        monkeypatch.setattr(rohstand, "sprung_um", falsch)
        monkeypatch.setattr(rohstand, "abgehoben_in_der_stunde", falsch_ab)
    l0 = datetime(2026, 6, 8, 10)

    def netz(t):
        return 1000.0 + 1.5 / 24 * (t - T0).total_seconds() / 3600 + (20.0 if t >= T else 0.0)

    def esp(t):
        b = 2000.0 + 1.2 / 24 * (min(t, l0) - T0).total_seconds() / 3600
        return b + (22.0 * min((t - l0).total_seconds(), 3600) / 3600 if t > l0 else 0.0)
    aid = await _welt_roh(db, 200.0, [(NETZ, MK, netz), (ESP, ESP_MK, esp)])
    erg = [(e.werte["feld"], e.werte["stunde"], e.werte["getauscht"]) for e in await _befund(db, aid)]
    if sprengsatz:
        assert ("basis:einspeisung", "2026-06-08T10:00", "2026-06-08T10:20") in erg
        return
    assert erg == [("basis:netzbezug", "2026-06-08T10:00", "2026-06-08T10:20")]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_spanne"])
async def test_a5_getauscht_am_eines_rueckgangs(db, monkeypatch, sprengsatz):
    """Ein Zähler mit Stand nur zur vollen Stunde fällt um 10:20 um 4 % (neuer Zähler etwas unter dem alten): Arm «Rückgang»,
    «Getauscht am» ist der Rohstand des Rückgangs (10:20, die Spanne R1) — nicht der Beginn der Stunde. Sprengsatz (U3-K4): ohne
    die Spanne ⇒ 10:00."""
    if sprengsatz:
        monkeypatch.setattr(rr, "sprung_der_stunde", lambda *_a, **_k: None)

    def f(t):
        g = t.replace(minute=0, second=0)
        b = 5000.0 + 0.5 * (g - T0).total_seconds() / 3600
        return round(0.96 * b if t >= T else b, 6)
    aid = await _welt_roh(db, 10.0, [(NETZ, MK, f)])
    erg = [(e.werte["art"], e.werte["stunde"], e.werte["getauscht"]) for e in await _befund(db, aid)]
    assert erg == [("rueckgang", "2026-06-08T10:00", "2026-06-08T10:00" if sprengsatz else "2026-06-08T10:20")]



# ═══ Teil B — Ränder der verworfenen Zeit («Bisherige Werte verwerfen») ═══════════════════════════════════════════════
#
# Welt der Saat ``test_daten_checker_zaehler_versatz`` (Wallbox-Ladezähler ``sensor.pv_ladung`` = A, 0,5 kWh je Stunde, Kanal
# «Spiegel» über den ganzen Juni): der richtige Sensor C ist eine **neue** Statistik in Home Assistant — ihre erste Zeile 12.06.
# 23:00 zählt 0,4 kWh ab HAs Nullpunkt, danach 0,5 kWh je Stunde. «Bisherige Werte verwerfen» mit «Falsch seit» 10.06. 00:00.

from backend.tests import test_daten_checker_zaehler_versatz as zv  # noqa: E402
from backend.tests.test_daten_checker_zaehler_versatz import ha  # noqa: E402,F401 — Fixture

QA_B = {"art": "ha", "entity_id": zv.SENSOR}
QC_B = {"art": "ha", "entity_id": "sensor.c"}
FS_B = datetime(2026, 6, 10)
H0_B = datetime(2026, 6, 12, 23)
AB_B = datetime(2026, 6, 13, 1)
JETZT_B = datetime(2026, 6, 13, 0, 20)


def _c_neu(svc, erste: datetime = H0_B, ende: datetime = datetime(2026, 6, 14)):
    """``sensor.c`` als neue Statistik ab ``erste`` (Summe ab 0: erste Zeile 0,4, dann 0,5 je Stunde)."""
    from sqlalchemy import text

    from backend.tests import ha_lts_helfer as h

    mid = h.sensor(svc, "sensor.c", "kWh", has_sum=True)
    zeilen, s, t = [], 0.0, erste
    while t < ende:
        s = round(s + (0.4 if t == erste else 0.5), 6)
        zeilen.append({"m": mid, "t": int(t.timestamp()), "w": s})
        t += timedelta(hours=1)
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"), zeilen)


async def _verwerfen(db, svc, monkeypatch, falsch_seit=FS_B):
    """Die Saat bis 13.06. 00:00 (Reihe und Kanal von A), dann «verwerfen» A → C um 00:20; Füllen und Stände wie der Lauf."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    staende = [(zv.T0 + timedelta(hours=h), zv._ha(h)) for h in range(12 * 24 + 1)]
    a, wb, key = await zv._anlage(db, staende=staende)
    from sqlalchemy import delete

    from backend.models.kanal import KanalStatistik
    await db.execute(delete(KanalStatistik).where(KanalStatistik.start_ts >= int(datetime(2026, 6, 13).timestamp())))
    await db.commit()
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=falsch_seit, ab=AB_B, vorher=QA_B, nachher=QC_B,
                    erklaert=JETZT_B)
    la = await kr.lage(db, au, ha_svc=svc)
    erg = await kr.fuehre_aus(db, au, ha_svc=svc, jetzt=JETZT_B)
    await db.commit()
    s = await kr.nach_dem_commit(erg, ha_svc=svc, sitzungen=kr.sitzungen_wie(db, get_session), starten=False)
    if s.get("staende_offen"):
        await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), s["lauf"])
    zw.vergiss(db)
    return a, wb, key, la


async def _kanal(db, key, von: datetime, bis: datetime):
    from backend.models.kanal import Kanal
    from backend.services.kanal import lesen, merken

    merken.invalidiere(None)
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()
    z = await lesen.zeitraum(db, k, int(von.timestamp()), int(bis.timestamp()))
    return None if z.delta is None else round(z.delta, 3), None if z.teil_delta is None else round(z.teil_delta, 3), z.grund


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_versatz_an_der_ersten_zeile"])
async def test_b1_regel2_kanal_zaehlt_die_erste_zeile_ab_has_nullpunkt(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """Mit Vorlauf (der Kanal trägt A bis 09.06.): die erste Zeile von C (12.06. 23:00) zählt im Kanal 0,4 kWh wie HA — der Versatz
    setzt an HAs Nullpunkt an (``kanal/korrektur._versatz`` mit ``ha_beginnt_bei``); die Lücke endet an dieser Zeile, ihre Zeile
    trägt den Nullpunkt (``stand_neu_null`` = 0), die Stände liest der Lauf ab 13.06. 00:00 neu. Sprengsatz: ohne «Regel 2» ⇒ 0,0
    (die erste Zeile ohne Zuwachs, U3-K2-Nachmessung Abschnitt C)."""
    from backend.services.kanal import korrektur as kk

    _c_neu(ha)
    if sprengsatz:
        async def nie(*_a, **_k):
            return False
        monkeypatch.setattr(kk, "ha_beginnt_bei", nie)
    a, _wb, key, la = await _verwerfen(db, ha, monkeypatch)
    stunde = await _kanal(db, key, H0_B, H0_B + timedelta(hours=1))
    if sprengsatz:
        assert stunde[:2] == (None, 0.0)
        return
    assert stunde == (None, 0.4, "feiner_als_spanne")          # Teilwert über die Spanne seit dem Stand vor der Zeit
    assert (la.luecke, la.nullpunkt, la.staende_neu) == ((FS_B, H0_B), 0.0, (H0_B + timedelta(hours=1), AB_B))
    zeilen = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == a.id)
                               .order_by(ZuordnungWechsel.id))).scalars().all()
    luecke = [z for z in zeilen if z.nachher is None]
    assert [(z.falsch_seit_ts, z.ab_ts, z.stand_neu_null) for z in luecke] == [(FS_B, H0_B, 0.0)]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_anker_null"])
async def test_b1_regel2_monat_aus_ha_mit_anker_null(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """«Aus HA laden» bzw. Monatsabschluss lesen den Juni von C über die Hülle «Monat je Geltungsabschnitt»: Anker 0 an der ersten
    Zeile (``nullpunkt.abschnitte``, ``monat._nullpunkt_teile``) ⇒ 0,4 + 0,5 × 24 = 12,4 kWh wie HA. Sprengsatz: ohne die
    Hülle ⇒ der HA-Leser ankert an der ersten Zeile, 12,0."""
    from backend.services.zuordnung_wechsel import monat, nullpunkt

    _c_neu(ha)
    a, _wb, _key, _la = await _verwerfen(db, ha, monkeypatch)
    if sprengsatz:
        monkeypatch.setattr(nullpunkt, "abschnitte", lambda wechsel: {})
    antwort = ha.get_monatswerte(["sensor.c"], 2026, 6)
    zw.vergiss(db)
    (aus,) = await monat.monatswerte_je_abschnitt(db, a.id, [antwort], [(2026, 6)])
    wert = next(w for w in aus.sensoren if w.sensor_id == "sensor.c")
    assert round(wert.differenz, 3) == (12.0 if sprengsatz else 12.4)


def test_b1_nullpunkt_teile_nur_im_monat_der_ersten_zeile():
    from backend.services.zuordnung_wechsel.monat import _nullpunkt_teile, unix

    g = datetime(2026, 6, 12, 23)
    juni, juli = (unix(datetime(2026, 6, 1)), unix(datetime(2026, 7, 1))), (unix(datetime(2026, 7, 1)), unix(datetime(2026, 8, 1)))
    assert _nullpunkt_teile("sensor.c", g, *juni) == [("sensor.c", unix(g), juni[1], True)]
    assert _nullpunkt_teile("sensor.c", g, *juli) == []


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_eine_stunde_davor"])
async def test_b2_linker_rand_die_stunde_vor_falsch_seit_bleibt(db, ha, monkeypatch, sprengsatz):  # noqa: F811
    """«Falsch seit» 10.06. 00:00 auf einer vollen Stunde mitten in der Quelle A: die Kanalzeile 09.06. 23:00 (die Stunde davor,
    HA führt sie für A) bleibt — der 09.06. zählt im Kanal 12,0 statt 11,5 (``korrektur.kanal_beginn``). Sprengsatz: wie bis
    U3-K2 eine Stunde davor ⇒ 11,5."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    _c_neu(ha)
    if sprengsatz:
        async def alt(_db, a, _ha_svc=None):
            return kr._kanal_beginn(a)
        monkeypatch.setattr(kr, "kanal_beginn", alt)
    _a, _wb, key, _la = await _verwerfen(db, ha, monkeypatch)
    tag = await _kanal(db, key, datetime(2026, 6, 9), datetime(2026, 6, 10))
    assert tag == ((None, 11.5, "feiner_als_spanne") if sprengsatz else (12.0, None, None))


async def test_b2_linker_rand_gegenproben(db, ha):  # noqa: F811
    """Die Stunde vor «Falsch seit» bleibt nur, wo Home Assistant für sie keine Zeile des richtigen Sensors führt und an ihr keine
    Quelle des Kanals beginnt: an einer Quellgrenze (4b-1-K h4: die falsche wurde zu «Falsch seit» zugeordnet), wo HA den
    richtigen Sensor dort führt (U2 a2, P-1: die Stunde zählt mit ihm) und ohne Home Assistant bleibt es eine Stunde davor."""
    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle
    from backend.services.zuordnung_wechsel import korrektur as kr

    _c_neu(ha)
    a, _wb, key = await zv._anlage(db, staende=[])
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(FS_B.timestamp()) - 3600, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.x", offset=0.0))
    await db.commit()

    def auftrag(fs):
        return kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=fs, ab=AB_B, vorher=QA_B, nachher=QC_B)
    ts = int(FS_B.timestamp())
    assert await kr.kanal_beginn(db, auftrag(FS_B), ha) == ts - 3600                         # Quellgrenze
    assert await kr.kanal_beginn(db, auftrag(FS_B + timedelta(days=1)), ha) == ts + 86400     # die Stunde davor bleibt
    assert await kr.kanal_beginn(db, auftrag(FS_B + timedelta(days=1)), None) == ts + 86400 - 3600   # ohne HA
    spaet = datetime(2026, 6, 13, 3)                                                          # C führt 02:00 schon
    assert await kr.kanal_beginn(db, auftrag(spaet), ha) == int(spaet.timestamp()) - 3600


async def test_b1_saetze_und_auskunft_nach_dem_lauf(db, ha, monkeypatch):  # noqa: F811
    """Die Vorschau nennt für Lücke und erste Zeile dieselbe Zeit (C und F), die Tage nach den Rändern des Kanals (er trägt davor
    Werte), und die Auskunft «Zählerstände – Zeit verworfen» sagt, dass die Stundenwerte ab der ersten Stunde des richtigen
    Sensors zählen."""
    from backend.services.daten_checker.datenquelle import verworfen as vw
    from backend.services.zuordnung_wechsel import korrektur as kr

    _c_neu(ha)
    a, _wb, key, la = await _verwerfen(db, ha, monkeypatch)
    saetze = kr.saetze(la)
    assert ("Vom 10.06.2026 00:00 bis 12.06.2026 23:00 Uhr füllt nichts die verworfenen Zählerstände wieder auf: Home "
            "Assistant führt den richtigen Sensor erst ab dann.") in " ".join(saetze)
    assert kr.SATZ_STAENDE_AB_KANAL.format(zeit="12.06.2026 23:00") in saetze
    # die Wallbox-Tage sind keine Kanal-Tage der Bilanz: dort liest die Tagesansicht die Reihe (ungemessen ab dem Stand 09.06.
    # 23:00 bis zum ersten neu gelesenen Stand 13.06. 00:00) — gemessen: 10.–12.06. «—», 13.06. ein Teilwert
    assert "Die Tagesansicht zeigt vom 10.06.2026 bis 12.06.2026 keinen Wert und am 13.06.2026 nur den Teil außerhalb dieser Zeit." in saetze
    sicht = await zv._tagesansicht(db, a, _wb, range(9, 14))
    assert sicht[9] == 12.0 and {sicht[10], sicht[11], sicht[12]} == {"luecke_verworfen"} and isinstance(sicht[13], float)
    zw.vergiss(db)
    (v,) = await vw.verworfene_zeiten(db, a.id)
    lage = await vw.lage_der_zeit(db, await zv_anlage(db, a.id), v)
    assert lage.grund == vw.GRUND_KANAL_ERSTE and lage.tage_ohne == [datetime(2026, 6, d).date() for d in (10, 11, 12)]


async def zv_anlage(db, aid):
    from backend.models.anlage import Anlage

    return (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()


def test_b_satz_bis_zum_ende_der_laufenden_stunde():
    """Satz B: endet die Zeit erst mit der laufenden Stunde (Dialog), sagt die Vorschau das statt «bis jetzt» (die Zeit reicht
    bis zur nächsten vollen Stunde) — weiter ohne einen Zeitpunkt nach jetzt (Lab-K W5)."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    assert kr.SATZ_LUECKE.replace("Vom {von} bis {bis} Uhr", kr.SATZ_BIS_JETZT).startswith(
        "Vom {von} Uhr bis zum Ende der laufenden Stunde füllt nichts")


async def test_b1_keine_regel2_wenn_ein_rand_die_hoehe_prueft(db, ha, monkeypatch):  # noqa: F811
    """Eigener Entscheid E-7 (U3-K3): prüft ein gespeicherter Stand der richtigen Quelle nach der Zeit die Höhe (hier: die Reihe
    trägt ab 13.06. 01:00 schon Stände von C) und passt, beginnt ihre Statistik dort nicht nachweislich am Nullpunkt — keine
    «Regel 2»: die Lücke reicht wie bisher bis zum ersten Stand aus HA (13.06. 00:00), kein Nullpunkt an der Lücken-Zeile."""
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.zuordnung_wechsel import korrektur as kr

    _c_neu(ha)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    staende = [(zv.T0 + timedelta(hours=h), zv._ha(h)) for h in range(12 * 24 + 1)]
    a, _wb, key = await zv._anlage(db, staende=staende)
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=datetime(2026, 6, 13, h), wert_kwh=0.4 + 0.5 * h,
                               quelle="ha_statistics") for h in (1, 2)])
    await db.commit()
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=FS_B, ab=AB_B, vorher=QA_B, nachher=QC_B, erklaert=JETZT_B)
    la = await kr.lage(db, au, ha_svc=ha)
    assert (la.luecke, la.nullpunkt) == ((FS_B, datetime(2026, 6, 13)), None)
