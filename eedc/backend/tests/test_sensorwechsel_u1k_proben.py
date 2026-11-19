"""Sensorwechsel, Korrekturrunde U1-K (Bauplan Nr. 141; Nachmessung `opus-berichte/SENSORWECHSEL-U1-NACHMESSUNG-2026-11-19.md`).

Saat des Befunds ``zaehler_versatz`` (``test_daten_checker_zaehler_versatz``): wahrer Zähler 100 + 0,5 kWh je Stunde = 12,0 kWh je
Tag, Stück um 80 kWh versetzt vom 10.06. 01:00 bis zum Rückgang 14.06. 19:00. Wie jede Zählerlücke: 0,5 · — · — · — · 59,5.

* **F1 (b)** Home Assistant beim Füllen nicht mehr eingerichtet ⇒ Lage «ohne Home Assistant»: Lücken-Zeile, der Lauf endet.
* **F4 (e)** Eine wiederholte Korrektur über einen Teil kürzt die ältere Lücke nur um diesen Teil — der Rest heilt nicht.
* **F5/F6 (d)** Füllen aus Home Assistant nur auf geprüfter Höhe, auch an der gewöhnlichen Korrektur (Dialog, Nachtrag, Werkbank).
* **S2 (f)** Der Befund fragt dieselbe Regel wie die Leser (Zählertausch zwischen den Ständen davor und danach).
* **S3 (f)** Stück mit später HA-Geschichte: Vorschau = Lauf (Lücke bis zum Beginn der Geschichte, Tag der Menge).
* **S4 (f)** Dialog «bis jetzt»: die Vorschau nennt den Tag der Menge und nicht den End-Tag als Teilwert-Tag.
* **OM3 (g)** Home Assistant nach dem Lesen nicht erreichbar ⇒ der Auftrag bleibt offen (keine dauerhafte Lücke).

F3 (Zählertausch im Intervall) steht in ``test_sensorwechsel_s4b1_stueck.py``, OM2 in ``test_sensorwechsel_u1_proben.py``. Jede
Probe hat einen Sprengsatz. Keine Probe liest die Uhr (die Suite fährt auch in ``Pacific/Auckland`` und ``UTC``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_daten_checker_zaehler_versatz as v
from backend.tests.test_daten_checker_zaehler_versatz import ha, ohne_ha  # noqa: F401 — Fixtures
from backend.tests.test_sensorwechsel_s4b1_stueck import (  # noqa: F401 — Fixture
    LUECKE, QA, RUECK, SPRUNG, ZAEHLERLUECKE, _body, _mengen, _stueck, _tagesansicht, eingerichtet,
)

QX = {"art": "ha", "entity_id": "sensor.x"}
JETZT = datetime(2026, 7, 1, 12)
ZWOELF = datetime(2026, 6, 12)


def _ha_mit(monkeypatch, plus: float = 0.0, ab_h: int = 0, loch=()):
    """HA erreichbar mit der Statistik von SENSOR: ``_ha(i) + plus`` für die Stände ``i ≥ ab_h`` außer ``loch``."""
    import backend.services.ha_statistics_service as hss
    from backend.tests import ha_lts_helfer as h

    svc = h.mach_service(thread_sicher=True)
    mid = h.sensor(svc, v.SENSOR, "kWh", has_sum=True)
    t0 = int(v.T0.timestamp()) - 3600
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                     [{"m": mid, "t": t0 + 3600 * i, "w": v._ha(i) + plus} for i in range(29 * 24)
                      if i >= ab_h and i not in loch])
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    return svc


async def _lauf(db, s: dict) -> None:
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    if s.get("staende_offen") or s.get("fuellen_offen") or s.get("tage_neu"):
        await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), s["lauf"])


async def _korrektur(db, au, svc) -> dict:
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr

    erg = await kr.fuehre_aus(db, au, ha_svc=svc, jetzt=JETZT)
    await db.commit()
    s = await kr.nach_dem_commit(erg, ha_svc=svc, sitzungen=kr.sitzungen_wie(db, get_session), starten=False)
    await _lauf(db, s)
    return s


async def _luecken(db) -> list[tuple[datetime, datetime]]:
    zeilen = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.falsch_seit_ts))).scalars().all()
    return [(w.falsch_seit_ts, w.ab_ts) for w in zeilen if zw.ist_luecke(w)]


# ═══ F1 (b): Home Assistant beim Füllen nicht mehr eingerichtet ═════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_f1_ha_nicht_mehr_eingerichtet_lauf_endet_wie_zaehlerluecke(db, ha, eingerichtet, monkeypatch, sprengsatz):  # noqa: F811
    """Füllbar eingetragen (mit Home Assistant), dann wird die Verbindung entfernt, bevor der Lauf liest: die Lage «ohne Home
    Assistant» — Lücken-Zeile, der Lauf endet (``fertig``), Regel der Zählerlücke: 0,5 · — · — · — · 59,5, 84,0, 336,0.
    Sprengsatz: «nicht eingerichtet» wirft wie in U1 ⇒ der Lauf bleibt offen, 2,0."""
    import backend.services.ha_statistics_service as hss
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.tests.pv_achse_matrix import _ha_aus

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    monkeypatch.setattr(korrektur_lauf, "starten", lambda *x, **k: None)
    r = await _stueck(db, a.id, key)
    lauf = r["korrektur"][0]["lauf"]
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: False)
    monkeypatch.setattr(hss, "_ha_statistics_service", _ha_aus())
    if sprengsatz:
        echt = kr.fuelle_staende

        async def wirft(sitzungen, anlage_id, auftrag, *, ha_svc=None):
            if (ha_svc or kr.ha_dienst(None)) is None:
                raise kr.KorrekturNichtStartbar("Home Assistant ist nicht eingerichtet")
            return await echt(sitzungen, anlage_id, auftrag, ha_svc=ha_svc)
        monkeypatch.setattr(kr, "fuelle_staende", wirft)
    await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), lauf)
    z = await korrektur_lauf.stand(db, lauf)
    sicht = await _tagesansicht(db, a, wb.id)
    if sprengsatz:
        assert z["status"] == "laeuft" and sicht == LUECKE
        return
    assert z["status"] == "fertig" and z["fuellen"]["erledigt"]
    assert await _luecken(db) == [(SPRUNG, RUECK)]
    assert sicht == ZAEHLERLUECKE
    assert await _mengen(db, a.id, key) == (pytest.approx(84.0), pytest.approx(336.0))


# ═══ F4 (e): wiederholte Korrektur über einen Teil ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_f4_wiederholte_korrektur_ueber_einen_teil_behaelt_den_rest(db, eingerichtet, monkeypatch, sprengsatz):
    """HAs Summe 1 906,5 höher (nicht füllbar): erst die Korrektur über das ganze Stück, dann dieselbe über [11.06., 12.06.) — sie
    nimmt die Zeile der ersten wieder, kürzt deren Lücke aber nur um ihren Teil: die Reste [10.06. 01:00, 11.06.) und
    [12.06., 14.06. 19:00) bleiben Lücken (nicht heilen), 0,5 · — · — · — · 59,5. Sprengsatz: gekürzt um das Intervall der
    wiederverwendeten Zeile (wie U1) ⇒ der Rest heilt aus HAs verschobener Summe, 10.06. 1 918,5."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    svc = _ha_mit(monkeypatch, plus=1906.5)
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    if sprengsatz:
        echt = kr._luecken_zeile
        monkeypatch.setattr(kr, "_luecken_zeile", lambda db_, a_, row, lu, lauf, intervall=None: echt(db_, a_, row, lu, lauf))
    for f, ab in ((SPRUNG, RUECK), (datetime(2026, 6, 11), ZWOELF)):
        await _korrektur(db, kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=f, ab=ab, vorher=QA, nachher=QA, stueck=True),
                         svc)
    sicht = await _tagesansicht(db, a, wb.id)
    if sprengsatz:
        assert 1918.5 in sicht.values()
        return
    assert await _luecken(db) == [(SPRUNG, datetime(2026, 6, 11)), (datetime(2026, 6, 11), ZWOELF), (ZWOELF, RUECK)]
    assert sicht == ZAEHLERLUECKE
    assert await _mengen(db, a.id, key) == (pytest.approx(84.0), pytest.approx(336.0))


# ═══ F5 / F6 (d): Füllen nur auf geprüfter Höhe ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
@pytest.mark.parametrize("fall", ["f5_rueckkehr", "f6_ab_spaeter", "gleiche_hoehe_ab_spaeter"])
async def test_f5_f6_gewoehnliche_korrektur_fuellt_nur_auf_gepruefter_hoehe(db, eingerichtet, monkeypatch, fall, sprengsatz):
    """Verzeichnet A → X am Sprung und X → A am Rückgang, Korrektur «richtig A» über [Sprung, Rückgang) (der Weg von Dialog und
    Nachtrag, nicht das Stück). F5: HAs Summe von A liegt 1 906,5 über den gespeicherten Ständen ⇒ eedc füllt nicht, Regel der
    Zählerlücke: 0,5 · — · — · — · 59,5, nie 1 918,5. F6: dazu führt HA A erst ab 12.06. ⇒ ebenso, nie 1 942,0. Gegenprobe:
    gleiche Höhe, HA ab 12.06. ⇒ gefüllt ab 12.06., 12.06. 35,5 (die Menge seit 10.06. 00:00), 84,0 / 336,0. Vorschau = Lauf.
    Sprengsatz: keine Höhen-Prüfung (wie U1) ⇒ 1 918,5 bzw. 1 942,0."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    plus, ab_h = {"f5_rueckkehr": (1906.5, 0), "f6_ab_spaeter": (1906.5, 11 * 24), "gleiche_hoehe_ab_spaeter": (0.0, 11 * 24)}[fall]
    svc = _ha_mit(monkeypatch, plus=plus, ab_h=ab_h)
    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        async def immer(*_a, **_k):
            return True
        monkeypatch.setattr(kr, "_hoehe_passt", immer)
    a, wb, key = await v._anlage(db, spiegel=False)
    for ab, vorher, nachher in ((SPRUNG, QA, QX), (RUECK, QX, QA)):
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=ab, ab_ts=ab, vorher=vorher, nachher=nachher,
                                grund=None, herkunft="altbestand"))
    await db.commit()
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QX, nachher=QA)
    la = await kr.lage(db, au, ha_svc=svc)
    await _korrektur(db, au, svc)
    sicht = await _tagesansicht(db, a, wb.id)
    if sprengsatz and plus:
        assert {1918.5, 1942.0} & set(sicht.values())
        return
    assert la.luecke == ((SPRUNG, ZWOELF) if fall == "gleiche_hoehe_ab_spaeter" else (SPRUNG, RUECK)) and la.zaehlerluecke
    assert await _luecken(db) == [la.luecke]                                           # Vorschau = Lauf
    if fall == "gleiche_hoehe_ab_spaeter":
        assert kr.SATZ_STAENDE_AB.format(zeit="12.06.2026 00:00") in kr.saetze(la)
        assert sicht == {9: 12.0, 10: 0.5, 11: None, 12: 35.5, 13: 12.0, 14: 12.0, 15: 12.0}
    else:
        assert la.staende_neu is None and kr.SATZ_KEIN_TAG not in kr.saetze(la)        # die Vorschau sagt: nichts neu gelesen
        assert sicht == ZAEHLERLUECKE
    assert await _mengen(db, a.id, key) == (pytest.approx(84.0), pytest.approx(336.0))


# ═══ S2: der Befund fragt dieselbe Regel wie die Leser ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_s2_befund_nennt_den_zaehlertausch_wenn_die_sicht_keine_differenz_bildet(db, ohne_ha, monkeypatch, sprengsatz):  # noqa: F811
    """Ohne Home Assistant; vor dem Sprung fünf Stunden ohne Stand, «Zähler getauscht» A → A drei Stunden vor dem Sprung: zwischen
    dem letzten Stand davor und dem ersten danach liegt ein Zählertausch. Der Befund sagt das (nicht «wie über jede
    Zählerlücke»), die Sicht danach zeigt 14.06. 2,0. Sprengsatz: der Befund fragt die Regel nicht (wie U1) ⇒ «Zählerlücke»."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG
    from backend.services.daten_checker.datenquelle import versatz as vs

    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        async def nie(*_a, **_k):
            return False
        monkeypatch.setattr(vs.ZaehlerVersatzChecks, "_versatz_tausch", nie)
    reihe = [(z, w) for z, w in v._reihe() if not (SPRUNG - timedelta(hours=5) <= z < SPRUNG)]
    a, wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    t = SPRUNG - timedelta(hours=3)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=t, ab_ts=t, vorher=QA, nachher=QA,
                            grund=GRUND_FORTSETZUNG, herkunft="wechsel"))
    await db.commit()
    (e,) = await v._pruefe(db, a)
    tausch = vs._SATZ_LAGE_TAUSCH[vs.GRUND_OHNE_HA]
    if sprengsatz:
        assert tausch not in e.details and "wie über jede Zählerlücke" in e.details
        return
    assert e.werte["lage"] == vs.GRUND_OHNE_HA and tausch in e.details and "Zählerlücke" not in e.details
    await _stueck(db, a.id, key, sprung=e.werte["sprung"], rueck=e.werte["rueckgang"])
    assert (await _tagesansicht(db, a, wb.id))[14] == 2.0


# ═══ S3: Stück mit später HA-Geschichte — Vorschau = Lauf ════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_s3_stueck_mit_spaeter_ha_geschichte_vorschau_gleich_lauf(db, eingerichtet, monkeypatch, sprengsatz):
    """HA führt A auf der Höhe der Reihe, im Stück aber erst ab dem Stand 12.06. 00:00: die Vorschau nennt die Lücke
    [10.06. 01:00, 12.06.), den Tag der Menge (12.06.) und «Ab 12.06.2026 00:00 Uhr …» — wie der Lauf: Lücken-Zeile über
    dieselbe Zeit, 12.06. 35,5, danach 12,0. Sprengsatz: das Stück gilt als ganz gefüllt (wie U1) ⇒ Vorschau ≠ Lauf."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur as kr

    svc = _ha_mit(monkeypatch, loch=range(v.SPRUNG_H, 11 * 24))
    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        echt = kr._luecke

        async def ganz(db_, a_, w0, ab, ha_svc):
            return None if a_.stueck else await echt(db_, a_, w0, ab, ha_svc)
        monkeypatch.setattr(kr, "_luecke", ganz)
    a, wb, key = await v._anlage(db, spiegel=False)
    k = (await sw.pruefe_stueck(a.id, _body(key), db))["korrektur"]
    await _stueck(db, a.id, key)
    vorschau = None if k["luecke"] is None else (datetime.fromisoformat(k["luecke"]["von"]), datetime.fromisoformat(k["luecke"]["bis"]))
    assert svc is not None
    if sprengsatz:
        assert vorschau is None and await _luecken(db) == [(SPRUNG, ZWOELF)]           # Vorschau ≠ Lauf
        return
    assert vorschau == (SPRUNG, ZWOELF) and await _luecken(db) == [vorschau]
    assert (k["luecke"]["tag_der_menge"], k["luecke"]["tage_ohne_wert"], k["luecke"]["tage_teilwert"]) == (
        "2026-06-12", ["2026-06-11"], ["2026-06-10"])
    assert kr.SATZ_STAENDE_AB.format(zeit="12.06.2026 00:00") in k["saetze"] and kr.SATZ_KEIN_TAG not in k["saetze"]
    assert await _tagesansicht(db, a, wb.id) == {9: 12.0, 10: 0.5, 11: None, 12: 35.5, 13: 12.0, 14: 12.0, 15: 12.0}


# ═══ S4: Dialog «bis jetzt» — Tag der Menge ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_s4_dialog_bis_jetzt_vorschau_nennt_den_tag_der_menge(db, ohne_ha, monkeypatch, sprengsatz):  # noqa: F811
    """Die Zeit endet am Wechsel, danach noch kein Stand (Dialog: ``ab`` = nächste volle Stunde): die Vorschau nennt als Tag der
    Menge den 14.06. (den Tag des ersten Stands, den eedc um ``ab`` schreibt), ohne Wert 11.–13.06., Teilwert nur 10.06. — wie
    die Sicht, sobald der Stand da ist. Sprengsatz: ohne Stand danach kein Tag der Menge (wie U1) ⇒ 14.06. als Teilwert-Tag."""
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import stueck as st
    from backend.models.sensor_snapshot import SensorSnapshot

    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        echt = st.tragtag_der_luecke

        async def ohne_stand(db_, anlage, key, bis):
            return None if await st._rand_ab(db_, anlage.id, key, bis) is None else await echt(db_, anlage, key, bis)
        monkeypatch.setattr(st, "tragtag_der_luecke", ohne_stand)
    a, wb, key = await v._anlage(db, staende=v._reihe(stunden=v.RUECK_H), spiegel=False)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=SPRUNG, ab_ts=SPRUNG, vorher=QA, nachher=QX,
                            grund=None, herkunft="altbestand"))
    await db.commit()
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QX, nachher=QA)
    la = await kr.lage(db, au, ha_svc=None)
    tage = (la.zaehlerluecke_tag, la.luecke_tage, la.luecke_rand)
    if sprengsatz:
        assert tage[0] is None and date(2026, 6, 14) in tage[2]
        return
    assert tage == (date(2026, 6, 14), [date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 13)], [date(2026, 6, 10)])
    assert kr.vorschau_daten(la)["luecke"]["tag_der_menge"] == "2026-06-14"
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=RUECK - timedelta(minutes=20))
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=v.T0 + timedelta(hours=h), wert_kwh=v._ha(h),
                               quelle="ha_statistics") for h in range(v.RUECK_H, 29 * 24)])
    await db.commit()
    assert await _tagesansicht(db, a, wb.id) == ZAEHLERLUECKE                          # Vorschau = Sicht


# ═══ OM3 (g): nach dem Lesen nicht erreichbar ═══════════════════════════════════════════════════════════════════════════

class _WegNachDemErstenBlick:
    """Ein HA-Dienst, der beim ersten Blick erreichbar ist und danach nicht mehr (mittendrin weg): liest nichts."""

    def __init__(self, echt):
        self._echt, self._blicke = echt, 0

    @property
    def is_available(self) -> bool:
        self._blicke += 1
        return self._blicke == 1

    def get_value_at(self, *_a, **_k):
        return None

    def __getattr__(self, name):
        return getattr(self._echt, name)


async def test_om3_ha_nach_dem_lesen_nicht_erreichbar_haelt_den_auftrag_offen(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Mutante OM3 der Nachmessung: ist Home Assistant nach dem Lesen nicht mehr erreichbar, wirft ``fuelle_staende`` — der
    Auftrag bleibt offen, keine Lücken-Zeile (eine «HA führt nichts»-Lücke wäre endgültig). Ohne die Prüfung nach dem Lesen
    schriebe es die Lücke."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    monkeypatch.setattr(korrektur_lauf, "starten", lambda *x, **k: None)
    await _stueck(db, a.id, key)
    auftrag = {"key": key, "von": SPRUNG.isoformat(), "bis": (SPRUNG + timedelta(hours=6)).isoformat()}
    with pytest.raises(kr.KorrekturNichtStartbar):
        await kr.fuelle_staende(kr.sitzungen_wie(db, get_session), a.id, auftrag, ha_svc=_WegNachDemErstenBlick(ha))
    assert await _luecken(db) == []
