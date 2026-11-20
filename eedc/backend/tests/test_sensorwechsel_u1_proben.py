"""Sensorwechsel U1 «Verwerfen abschließen» (Bauplan Nr. 133 Zielbild Punkt 4, Nr. 135 U1, Nr. 136; Halt H-K2-1 Option A Nr. 127).

Saat des Befunds ``zaehler_versatz`` (``test_daten_checker_zaehler_versatz``): wahrer Zähler 100 + 0,5 kWh je Stunde = 12,0 kWh je
Tag, Stück um 80 kWh versetzt vom 10.06. 01:00 bis zum Rückgang 14.06. 19:00.

* **Punkt 1 — leere Zeit wie Zählerlücke, in allen Lagen (P1, P3):** eine verworfene, nicht gefüllte Zeit bekommt immer eine
  Lücken-Zeile (nicht heilen, nicht füllen); gilt am letzten Stand davor dieselbe Quelle wie am ersten Stand danach und liegt
  keine Fortsetzung dazwischen (``zeitpunkt.ohne_hoehenwechsel``), sind ihre Ränder keine Nähte: 0,5 · — · — · — · 59,5,
  9.–16.06. 84,0, Juni 336,0 — ohne Home Assistant, mit verschobener HA-Summe (nie 1 918,5), Lauf offen und HA führt danach
  nichts, MQTT. Sonst (P2: Wechsel A → C, 1 000 → 7 000) Nähte: 2,0, nie 6 059,5.
* **Punkt 3 — leer bleibt nur die Zeit, für die HA nichts führt (P5):** C in HA erst ab 12.06. 00:00 ⇒ 13. und 14.06. je 12,0.
* Die reine Regel: ``ohne_hoehenwechsel``, ``quelle_aufgeloest``, ``gesperrte_stuecke(ausgenommen=…)``.

Jede neue Regel hat eine Probe mit Sprengsatz. Keine Probe liest die Uhr; die Zeitpunkte liegen im Juni (die Suite fährt auch in
``Pacific/Auckland`` und ``UTC``). Schwesterdateien: test_sensorwechsel_s4b1_stueck.py, test_sensorwechsel_s4b1k2_proben.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_daten_checker_zaehler_versatz as v
from backend.tests.test_daten_checker_zaehler_versatz import ha, ohne_ha  # noqa: F401 — Fixtures
from backend.tests.test_sensorwechsel_s4b1_stueck import (  # noqa: F401 — Fixture
    LUECKE, QA, RUECK, SPRUNG, ZAEHLERLUECKE, _mengen, _stueck, _tagesansicht, eingerichtet,
)

QC = {"art": "ha", "entity_id": "sensor.c"}
MQ = {"art": "mqtt", "mqtt_key": "inv/1/ladung_pv_kwh", "topic": "eedc/wallbox"}
JETZT = datetime(2026, 7, 1, 12)


# ═══ Die Regel (rein) ══════════════════════════════════════════════════════════════════════════════════════════════════

def _w(ab, vorher, nachher, grund=None, falsch_seit=None, i=1, aufgehoben=None):
    return zw.Wechsel("k", ab, vorher, nachher, grund, falsch_seit, aufgehoben, None, i)


L = (SPRUNG, RUECK)


def test_ohne_hoehenwechsel_dieselbe_quelle_davor_und_danach():
    k = _w(RUECK, QA, QA, "korrektur", SPRUNG, 1)
    luecke = _w(RUECK, QA, None, "korrektur", SPRUNG, 2)
    vor, nach = SPRUNG - timedelta(hours=1), RUECK
    assert zw.quelle_aufgeloest([k, luecke], vor) == QA          # vorher der Korrektur-Zeile (die Lücken-Zeile zählt nicht)
    assert zw.quelle_aufgeloest([k, luecke], nach) == QA         # «heute» ⇒ nachher des jüngsten Wechsels bis nach
    assert zw.quelle_aufgeloest([k, luecke], SPRUNG + timedelta(hours=5)) is None      # in der Lücke: unbekannt
    assert zw.erklaerte_quelle([k, luecke], SPRUNG + timedelta(hours=5)) == QA         # … erklärt ist dort A
    assert zw.ohne_hoehenwechsel([k, luecke], vor, nach, L)
    assert zw.gesperrte_stuecke([k, luecke], ausgenommen=frozenset({L})) == []
    assert zw.naehte_der_fortsetzung([k, luecke], ausgenommen=frozenset({L})) == []
    assert zw.naehte_der_fortsetzung([k, luecke]) == [SPRUNG, RUECK]
    assert zw.verworfene_stuecke([k, luecke]) == [L]


def test_ohne_hoehenwechsel_nein_bei_anderer_unbekannter_quelle_fortsetzung_oder_ohne_stand():
    vor, nach = SPRUNG - timedelta(hours=1), RUECK
    andere = [_w(SPRUNG, QC, QA, None, None, 1), _w(RUECK, QA, QA, "korrektur", SPRUNG, 2)]
    assert not zw.ohne_hoehenwechsel(andere, vor, nach, L)                               # davor C, danach A
    unbekannt = [_w(RUECK, None, QA, "korrektur", SPRUNG, 1)]
    assert not zw.ohne_hoehenwechsel(unbekannt, vor, nach, L)                            # davor unbekannt
    mit_naht = [_w(RUECK, QA, QA, "korrektur", SPRUNG, 1), _w(RUECK, QA, QA, "fortsetzung", None, 2)]
    assert not zw.ohne_hoehenwechsel(mit_naht, vor, nach, L)                             # Fortsetzung an R (vor < ab ≤ nach)
    assert not zw.ohne_hoehenwechsel(mit_naht[:1], None, nach, L)                        # kein Stand davor
    mqtt = [_w(RUECK, MQ, MQ, "korrektur", SPRUNG, 1)]
    assert zw.ist_luecke(mqtt[0]) and zw.ohne_hoehenwechsel(mqtt, vor, nach, L)          # MQTT: dieselbe Beschreibung


def test_u1k_zaehlertausch_derselben_quelle_auch_aufgehoben():
    """U1-K (c) (ii): ein Zählertausch derselben Quelle (A → A) zwischen den Ständen ist ein Höhenwechsel, auch von der
    Korrektur aufgehoben; eine aufgehobene Fortsetzung nur einer anderen Quelle (X → X) nicht. Genau am letzten Stand davor
    (``ab_ts = vor``: der Stand dort ist schon der neue Zähler) liegt der Tausch nicht dazwischen (Mutante OM2: ``vor <= ab_ts``)."""
    vor, nach = SPRUNG - timedelta(hours=1), RUECK
    k = _w(RUECK, QA, QA, "korrektur", SPRUNG, 1)
    t = SPRUNG + timedelta(hours=30)
    assert not zw.ohne_hoehenwechsel([k, _w(t, QA, QA, "fortsetzung", None, 2, aufgehoben=1)], vor, nach, L)
    a_c = _w(SPRUNG, QA, QC, None, None, 3, aufgehoben=1)              # A → C am Sprung, «Zähler getauscht» während C galt
    assert zw.ohne_hoehenwechsel([k, a_c, _w(t, QC, QC, "fortsetzung", None, 2, aufgehoben=1)], vor, nach, L)
    assert zw.ohne_hoehenwechsel([k, _w(vor, QA, QA, "fortsetzung", None, 2)], vor, nach, L)
    assert not zw.ohne_hoehenwechsel([k, _w(vor + timedelta(minutes=1), QA, QA, "fortsetzung", None, 2)], vor, nach, L)


def test_u1k_erklaerte_quelle_der_leeren_zeit_muss_dieselbe_sein():
    """U1-K (c) (i), Nr. 113: der Rest einer MQTT-Korrektur, die eine spätere Korrektur teilweise aufgehoben hat, behält die für
    ihn erklärte Quelle (MQTT) — davor und danach A ⇒ Höhenwechsel. Die spätere Korrektur deckt ihren Teil selbst."""
    mq_korr = _w(RUECK, QA, MQ, "korrektur", SPRUNG, 1, aufgehoben=2)
    spaeter = _w(datetime(2026, 6, 20), MQ, QA, "korrektur", datetime(2026, 6, 12), 2)
    rest = _w(datetime(2026, 6, 12), QA, None, "korrektur", SPRUNG, 3)
    zeilen = [mq_korr, spaeter, rest]
    assert zw.erklaerte_quelle(zeilen, SPRUNG + timedelta(hours=2)) == MQ
    assert zw.erklaerte_quelle(zeilen, datetime(2026, 6, 13)) == QA
    assert not zw.ohne_hoehenwechsel(zeilen, SPRUNG - timedelta(hours=1), datetime(2026, 6, 12), (SPRUNG, datetime(2026, 6, 12)))
    # ohne erklärte Quelle (Zeile unbekannt) keine Zählerlücke
    assert zw.erklaerte_quelle([rest], SPRUNG + timedelta(hours=2)) is None


# ═══ P1 / P3: vier Lagen, dieselbe Quelle davor und danach ═════════════════════════════════════════════════════════════

async def _lage_ohne_ha(db, monkeypatch, request):
    request.getfixturevalue("ohne_ha")
    a, wb, key = await v._anlage(db, spiegel=False)
    await _stueck(db, a.id, key)
    return a, wb, key


async def _lage_ha_verschoben(db, monkeypatch, request):
    request.getfixturevalue("eingerichtet")
    v._ha_verschoben(monkeypatch, 1906.5)
    a, wb, key = await v._anlage(db, spiegel=False)
    await _stueck(db, a.id, key)
    return a, wb, key


async def _lage_lauf_nichts(db, monkeypatch, request):
    """Füllbar eingetragen, der Lauf startet erst, als Home Assistant für die Zeit nichts mehr führt."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    request.getfixturevalue("eingerichtet")
    svc = request.getfixturevalue("ha")
    a, wb, key = await v._anlage(db, spiegel=False)
    monkeypatch.setattr(korrektur_lauf, "starten", lambda *x, **k: None)
    r = await _stueck(db, a.id, key)
    monkeypatch.setattr(svc, "get_value_at", lambda *_a, **_k: None)
    await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), r["korrektur"][0]["lauf"])
    return a, wb, key


async def _lage_mqtt(db, monkeypatch, request):
    """Eine MQTT-Korrektur über das Stück mit derselben Quelle davor und danach (``vorher`` = ``nachher``)."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    request.getfixturevalue("ohne_ha")
    a, wb, key = await v._anlage(db, spiegel=False, quelle="mqtt_inbound")
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=MQ, nachher=MQ)
    la = await kr.lage(db, au, ha_svc=None)
    assert la.luecke == (SPRUNG, RUECK)
    request.node.vorschau_zaehlerluecke = la.zaehlerluecke          # Vorschau = Lauf (die Probe prüft es)
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=JETZT)
    await db.commit()
    return a, wb, key


LAGEN = {"ohne_ha": _lage_ohne_ha, "ha_verschoben": _lage_ha_verschoben, "lauf_nichts": _lage_lauf_nichts, "mqtt": _lage_mqtt}


@pytest.mark.parametrize("sprengsatz", [False, True])
@pytest.mark.parametrize("lage", list(LAGEN))
async def test_p1_vier_lagen_wie_jede_zaehlerluecke(db, monkeypatch, request, lage, sprengsatz):
    """P1/P3: in jeder Lage 0,5 · — · — · — · 59,5 (Zeitraum 84,0, Juni 336,0), keine Naht, kein Stand im Stück geheilt, die
    Zeit trägt eine Lücke. Sprengsatz: Höhen-Prüfung aus (jede Lücke sperrt) ⇒ 2,0 / 26,5."""
    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        monkeypatch.setattr(zw, "ohne_hoehenwechsel", lambda *_a, **_k: False)
    a, wb, key = await LAGEN[lage](db, monkeypatch, request)
    zw.vergiss(db)
    luecken = [w for w in (await db.execute(select(ZuordnungWechsel))).scalars().all() if zw.ist_luecke(w)]
    assert [(w.falsch_seit_ts, w.ab_ts) for w in luecken] == [(SPRUNG, RUECK)]
    sicht = await _tagesansicht(db, a, wb.id)
    assert 1918.5 not in sicht.values() and 6059.5 not in sicht.values()
    if sprengsatz:
        assert sicht == LUECKE
        return
    assert await zw.fortsetzungs_naehte(db, a.id, key) == []
    assert getattr(request.node, "vorschau_zaehlerluecke", True)
    assert sicht == ZAEHLERLUECKE
    assert await _mengen(db, a.id, key) == (pytest.approx(84.0), pytest.approx(336.0))
    assert await db.scalar(select(func.count()).select_from(SensorSnapshot).where(
        SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK)) == 0


# ═══ P2: verschiedene Höhen ═════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mit_ha", [False, True])
async def test_p2_verschiedene_hoehen_nie_6059(db, monkeypatch, request, mit_ha):
    """Wechsel A → C am «Rückgang» (1 000 → 7 000), «Korrektur» mit «Falsch seit» am Sprung, C ohne Geschichte: davor A, danach
    C — ein Höhenwechsel; die Ränder sind Nähte: 0,5 · — · — · — · 2,0, nie 6 059,5 (bzw. 6 012,0 vorher)."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    svc = None
    if mit_ha:
        request.getfixturevalue("eingerichtet")
        svc = request.getfixturevalue("ha")
    else:
        request.getfixturevalue("ohne_ha")
    reihe = [(v.T0 + timedelta(hours=h), (7000.0 if h >= v.RUECK_H else 1000.0) + 0.5 * h) for h in range(29 * 24)]
    a, wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QC)
    la = await kr.lage(db, au, ha_svc=svc)
    assert la.luecke == (SPRUNG, RUECK) and not la.zaehlerluecke
    assert any(s.startswith("Vom 10.06.2026 01:00 bis 14.06.2026 19:00 Uhr füllt nichts") and "nicht erkennbar" in s
               for s in kr.saetze(la))
    await kr.fuehre_aus(db, au, ha_svc=svc, jetzt=JETZT)
    await db.commit()
    sicht = await _tagesansicht(db, a, wb.id)
    assert sicht == LUECKE and 6059.5 not in sicht.values()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, a.id, key) == [SPRUNG, RUECK]


# ═══ P5: Home Assistant führt den richtigen Sensor erst ab 12.06. ════════════════════════════════════════════════════════

def _ha_c_ab(svc, ab_h: int):
    """``sensor.c`` (= A + 500) in HA erst ab der Stunde ``ab_h`` (Zeile ``ab_h − 1`` trägt den Stand um ``ab_h``)."""
    from sqlalchemy import text

    from backend.tests import ha_lts_helfer as h

    mid = h.sensor(svc, "sensor.c", "kWh", has_sum=True)
    t0 = int(v.T0.timestamp()) - 3600
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                     [{"m": mid, "t": t0 + 3600 * i, "w": v._ha(i) + 500.0} for i in range(ab_h, 29 * 24)])


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_p5_geschichte_ab_zwoelften_nur_die_zeit_davor_bleibt_leer(db, ha, eingerichtet, monkeypatch, sprengsatz):  # noqa: F811
    """Wechsel A → C am Rückgang (C = A + 500), C in HA erst ab 12.06. 00:00; «Korrektur» mit «Falsch seit» am Sprung: Lücke nur
    [10.06. 01:00, 12.06. 00:00), ab dort liest der Lauf die Stände neu und speichert sie (Vorschau = Lauf). 13. und 14.06. je
    12,0, nie 0,0; 12.06. der Teil ab 00:00 (11,5). Sprengsatz: die Lücke reicht bis ``ab`` (wie bis 4b-1-K2)."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    v._kanal_tage(monkeypatch, {})
    ab12 = datetime(2026, 6, 12)
    _ha_c_ab(ha, 11 * 24)
    reihe = [(v.T0 + timedelta(hours=h), v._ha(h) + (500.0 if h >= v.RUECK_H else (80.0 if h >= v.SPRUNG_H else 0.0)))
             for h in range(29 * 24)]
    a, wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=RUECK, ab_ts=RUECK, vorher=QA, nachher=QC,
                            grund=None, herkunft="altbestand"))
    await db.commit()
    if sprengsatz:
        echt = kr._luecke

        async def bis_ab(db_, a_, w0, ab, svc):
            lu, null = await echt(db_, a_, w0, ab, svc)                       # U3-K3: (Lücke, Nullpunkt)
            return (None, None) if lu is None else ((lu[0], ab), null)
        monkeypatch.setattr(kr, "_luecke", bis_ab)
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QC)
    la = await kr.lage(db, au, ha_svc=ha)
    if not sprengsatz:
        assert (la.luecke, la.staende_neu, la.zaehlerluecke) == ((SPRUNG, ab12), (ab12, RUECK), False)
        assert kr.SATZ_STAENDE_AB.format(zeit="12.06.2026 00:00") in kr.saetze(la)
    erg = await kr.fuehre_aus(db, au, ha_svc=ha, jetzt=JETZT)
    await db.commit()
    s = await kr.nach_dem_commit(erg, ha_svc=ha, sitzungen=kr.sitzungen_wie(db, get_session), starten=False)
    if s.get("staende_offen"):
        await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), s["lauf"])
    sicht = await _tagesansicht(db, a, wb.id)
    if sprengsatz:
        assert (sicht[13], sicht[14]) != (12.0, 12.0)
        return
    assert await db.scalar(select(func.count()).select_from(SensorSnapshot).where(
        SensorSnapshot.zeitpunkt >= ab12, SensorSnapshot.zeitpunkt < RUECK)) == (RUECK - ab12) // timedelta(hours=1)
    assert sicht == {9: 12.0, 10: 0.5, 11: None, 12: 11.5, 13: 12.0, 14: 12.0, 15: 12.0}
    assert 0.0 not in sicht.values()


# ═══ Benannte Grenzen der Vorrunde neu geprüft (4b-1-K2: (4) und (6)) ══════════════════════════════════════════════════

async def test_grenze_6_zaehlerluecke_ohne_ha_spaeter_mit_ha_heilt_nicht(db, ohne_ha, monkeypatch):  # noqa: F811
    """Vorrunde Grenze (6): eine Zählerlücke, ohne Home Assistant eingetragen, wurde nach dem Verbinden mit Home Assistant aus
    der Quelle geheilt — auf welcher Höhe, prüfte niemand. Seit U1 steht die Lücken-Zeile in jeder Lage: mit Home Assistant
    (Summe 1 906,5 höher) heilt nichts, es bleibt 0,5 · — · — · — · 59,5."""
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    await _stueck(db, a.id, key)
    v._ha_verschoben(monkeypatch, 1906.5)
    sicht = await _tagesansicht(db, a, wb.id)
    assert sicht == ZAEHLERLUECKE
    assert await db.scalar(select(func.count()).select_from(SensorSnapshot).where(
        SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK)) == 0


@pytest.mark.parametrize("mit_ha", [False, True])
async def test_grenze_4_alte_fuellbare_korrektur_ohne_staende(db, monkeypatch, request, mit_ha):
    """Vorrunde Grenze (4): eine füllbare Korrektur von vor 4b-1-K2 (Korrektur-Zeile mit HA-Entität, Stände verworfen, kein
    Auftrag, keine Lücken-Zeile). Ohne Home Assistant bildet die Tagesansicht die Differenz über das Stück — dieselbe Quelle
    davor und danach, also die Regel der Zählerlücke (59,5); mit Home Assistant heilt «Zuordnung zum Zeitpunkt» die Ränder aus
    der richtigen Quelle auf derselben Höhe (12,0 an jedem Tag)."""
    v._kanal_tage(monkeypatch, {})
    request.getfixturevalue("ha" if mit_ha else "ohne_ha")
    a, wb, key = await v._anlage(db, spiegel=False)
    await db.execute(SensorSnapshot.__table__.delete().where(SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK))
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=RUECK, ab_ts=RUECK, vorher=QA, nachher=QA,
                            grund="korrektur", falsch_seit_ts=SPRUNG, herkunft="nachtrag"))
    await db.commit()
    sicht = await _tagesansicht(db, a, wb.id)
    assert sicht == ({d: 12.0 for d in ZAEHLERLUECKE} if mit_ha else ZAEHLERLUECKE)


async def test_dialog_bis_jetzt_ohne_stand_danach_vorschau_gleich_lauf(db, ohne_ha, monkeypatch):  # noqa: F811
    """Die Zeit endet am Wechsel und danach steht noch kein Stand (Dialog: ``ab`` = nächste volle Stunde). Davor galt A
    (verzeichneter Wechsel A → X am Sprung), richtig ist A: die Vorschau nennt die Zählerlücke — sie zählt den ersten Stand,
    den eedc ab ``ab`` schreibt (dort gilt A). Bis er da ist, bildet kein Leser eine Differenz; danach steht die Menge am Tag
    des ersten Stands (14.06. 59,5) — Vorschau = Lauf."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    QX = {"art": "ha", "entity_id": "sensor.x"}
    a, wb, key = await v._anlage(db, staende=v._reihe(stunden=v.RUECK_H), spiegel=False)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=SPRUNG, ab_ts=SPRUNG, vorher=QA, nachher=QX,
                            grund=None, herkunft="altbestand"))
    await db.commit()
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QX, nachher=QA)
    la = await kr.lage(db, au, ha_svc=None)
    assert la.luecke == (SPRUNG, RUECK) and la.zaehlerluecke
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=RUECK - timedelta(minutes=20))
    await db.commit()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, a.id, key) == [SPRUNG, RUECK]          # noch kein Stand danach
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=v.T0 + timedelta(hours=h), wert_kwh=v._ha(h),
                               quelle="ha_statistics") for h in range(v.RUECK_H, 29 * 24)])
    await db.commit()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, a.id, key) == []
    assert await _tagesansicht(db, a, wb.id) == ZAEHLERLUECKE
