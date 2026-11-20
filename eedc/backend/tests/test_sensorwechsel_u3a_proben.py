"""Sensorwechsel U3 Lauf a «Auskunft» (Rechenweg ``opus-berichte/SENSORWECHSEL-U3-RECHENWEG-2026-11-19.md`` G1, G2, G3, G8;
Bauplan Nr. 150) — Proben mit Sprengsatz.

* **G1** ``zaehler_zeit_verworfen``: je nicht aufgehobener Lücke eine Auskunft; Lage «wie Zählerlücke» (Tag der Menge) bzw.
  «keine Differenz» (Höhenwechsel, «Höhe ungeprüft», Kanal führt die Zeit als verworfen); ``erfassung_stillstand`` lässt eine
  Stelle aus, die allein eine verworfene Zeit eines Bilanz-Zählers erklärt (ein Befund je Ursache).
* **G2** ``monatswert_ueberholt``: nur an berührten Monaten, gespeichert, voller Wert aus dem Kanal, Abweichung ≥ 1 kWh, nicht
  bei «gespeicherten behalten».
* **G3** ``SATZ_TAG_FEST`` nur mit Tag und Wert, wenn die Tageszeile den Schlüssel trägt.
* **G8** Rest fremder Stände: Vorgabe «Falsch seit» auf den passenden Schritt in den 24 Stunden davor; Lage «Rest» am
  Versatz-Befund. Soll je 14.06. 61,0 (statt 3 059,5 / 119,5 bzw. «—»).

Saat wie der Befund ``zaehler_versatz`` (Wallbox «Ladung PV», 100 + 0,5 kWh je Stunde ab 01.06.2026, keine Zeitumstellung im
Juni); keine Probe liest die Uhr (die Datei läuft auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``).
Schwesterdateien: test_sensorwechsel_s4b1_stueck.py (Korrektur über das Stück), test_daten_checker_zaehler_versatz.py (Befund
und Saat), test_sensorwechsel_u2c_proben.py, test_n799_s3_befund.py (``erfassung_stillstand``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_daten_checker_zaehler_versatz as v
from backend.tests.test_daten_checker_zaehler_versatz import ha, ohne_ha  # noqa: F401 — Fixtures
from backend.tests.test_sensorwechsel_s4b1_stueck import _stueck, _tagesansicht, eingerichtet  # noqa: F401

SPRUNG = v.T0 + timedelta(hours=v.SPRUNG_H)        # 10.06. 01:00
RUECK = v.T0 + timedelta(hours=v.RUECK_H)          # 14.06. 19:00
FREMD_AB = SPRUNG - timedelta(hours=3)             # 09.06. 22:00 — die fremden Stände beginnen drei Stunden früher
QA = {"art": "ha", "entity_id": v.SENSOR}
QX = {"art": "ha", "entity_id": "sensor.fremd_x"}


def _f8_reihe(versatz: float):
    return [(v.T0 + timedelta(hours=h), v._ha(h) + (versatz if v.SPRUNG_H - 3 <= h < v.RUECK_H else 0.0))
            for h in range(29 * 24)]


async def _wechsel(db, aid, key, ab, vorher, nachher, **kw):
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=ab, ab_ts=ab, vorher=vorher, nachher=nachher,
                            herkunft=kw.pop("herkunft", "altbestand"), **kw))


async def _laeufe():
    from backend.services.zuordnung_wechsel import korrektur_lauf

    for t in list(korrektur_lauf._AUFGABEN.values()):
        await t


async def _anlage_der(db, aid):
    from backend.models.anlage import Anlage
    from sqlalchemy.orm import selectinload

    zw.vergiss(db)
    return (await db.execute(select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == aid))).scalar_one()


async def _verworfen(db, aid):
    from backend.services.daten_checker import DatenChecker

    return await DatenChecker(db)._check_zaehler_zeit_verworfen(await _anlage_der(db, aid))


# ═══ G8 — Rest fremder Stände (Regel, rein) ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("versatz", [3000.0, -60.0, -3000.0], ids=["oben", "unten", "frueher_fremd"])
def test_g8_rest_schritt_findet_den_beginn_der_fremden_staende(versatz):
    from backend.core.berechnungen.zaehler_versatz import rest_schritt

    s = rest_schritt(_f8_reihe(versatz), SPRUNG, RUECK)
    assert s is not None and s.bis == FREMD_AB and s.delta_kwh == pytest.approx(versatz + 0.5)


def test_g8_rest_schritt_grenzen():
    """Sprengsatz «Suchfenster 0» ⇒ kein Schritt; ohne Schritt am Ende, mit gleichsinnigem oder unähnlichem Schritt ⇒ keiner."""
    from backend.core.berechnungen.zaehler_versatz import rest_schritt

    assert rest_schritt(_f8_reihe(3000.0), SPRUNG, RUECK, fenster_stunden=0) is None
    assert rest_schritt(v._reihe(sprung=None), SPRUNG, RUECK) is None                        # gar kein Schritt
    halb = [(t, w + (1500.0 if FREMD_AB <= t < SPRUNG else 0.0) + (3000.0 if SPRUNG <= t < RUECK else 0.0))
            for t, w in v._reihe(sprung=None)]
    assert rest_schritt(halb, SPRUNG, RUECK) is None                                          # 1 500 passt nicht zu −4 500
    gleichsinnig = [(t, w + (3000.0 if t >= FREMD_AB else 0.0) + (3000.0 if t >= RUECK else 0.0)) for t, w in v._reihe(sprung=None)]
    assert rest_schritt(gleichsinnig, SPRUNG, RUECK) is None                                  # zweimal nach oben: kein Rest
    assert rest_schritt(_f8_reihe(3000.0), SPRUNG + timedelta(days=2), RUECK) is None         # Schritt älter als 24 h


# ═══ G8 — Vorgabe «Falsch seit» im Nachtrag ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_fenster_0"])
@pytest.mark.parametrize("versatz,alt", [(3000.0, None), (-60.0, 119.5), (-3000.0, 3059.5)],
                         ids=["f8_oben", "f8_unten", "u2_staende_frueher_fremd"])
async def test_g8_vorgabe_falsch_seit_am_frueheren_schritt(db, ohne_ha, monkeypatch, versatz, alt, sprengsatz):  # noqa: F811
    """A → X am Sprung, X → A am Rückgang (ohne Grund); die Reihe trägt X schon drei Stunden vorher. «Grund nachtragen →
    Korrektur» mit der Vorgabe ⇒ 14.06. 61,0 (Rechenweg G8, gerechnet); mit Suchfenster 0 das alte Soll."""
    import backend.core.berechnungen.zaehler_versatz as zv
    from backend.api.routes import sensorwechsel as sw

    if sprengsatz:
        echt = zv.rest_schritt
        monkeypatch.setattr(zv, "rest_schritt", lambda st, f, e, fenster_stunden=0: echt(st, f, e, 0))
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, staende=_f8_reihe(versatz), spiegel=False)
    aid, wid = a.id, wb.id
    await _wechsel(db, aid, key, SPRUNG, QA, QX)
    await _wechsel(db, aid, key, RUECK, QX, QA)
    await db.commit()
    rid = (await db.execute(select(ZuordnungWechsel.id).where(ZuordnungWechsel.ab_ts == RUECK))).scalar_one()
    p = await sw.pruefe_grund_nachtragen(aid, rid, sw.GrundNachtragRequest(), db)
    vorgabe = datetime.fromisoformat(p["vorgabe_falsch_seit"])
    assert vorgabe == (SPRUNG if sprengsatz else FREMD_AB)
    assert ("schon am 09.06.2026 22:00 Uhr" in p["wechsel_satz"]) is not sprengsatz
    await sw.grund_nachtragen(aid, rid, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=vorgabe), db)
    await _laeufe()
    tag14 = (await _tagesansicht(db, a, wid))[14]
    assert tag14 == (alt if sprengsatz else 61.0)


# ═══ G8 — Lage «Rest» am Versatz-Befund (bestehende Lücke) ════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_rest"])
async def test_g8_rest_am_versatz_befund_und_grund_nachtragen(db, ohne_ha, monkeypatch, sprengsatz):  # noqa: F811
    """Die Korrektur mit der alten Vorgabe (am Sprung) ließ drei Stunden fremder Stände stehen; der Versatz-Befund nennt sie
    als Rest dieser Korrektur, «Grund nachtragen» über das Stück verwirft sie ⇒ 14.06. 61,0, kein Befund mehr."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import stueck

    if sprengsatz:
        async def _keiner(*_a, **_k):
            return None
        monkeypatch.setattr(stueck, "rest_vor", _keiner)
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, staende=_f8_reihe(3000.0), spiegel=False)
    aid, wid = a.id, wb.id
    await _wechsel(db, aid, key, SPRUNG, QA, QX)
    await _wechsel(db, aid, key, RUECK, QX, QA)
    await db.commit()
    rid = (await db.execute(select(ZuordnungWechsel.id).where(ZuordnungWechsel.ab_ts == RUECK))).scalar_one()
    await sw.grund_nachtragen(aid, rid, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=SPRUNG), db)
    await _laeufe()
    zw.vergiss(db)
    (e,) = await v._pruefe(db, a)
    if sprengsatz:
        assert e.werte["lage"] == "ohne_home_assistant" and "Rest einer früheren Korrektur" not in e.details
        return
    assert (e.werte["lage"], e.werte["lage_korrektur"], e.werte["rest_luecke"]) == (
        "rest", "ohne_home_assistant", ["2026-06-10T01:00", "2026-06-14T19:00"])
    assert ("Diese Zählerstände sind der Rest einer früheren Korrektur: sie hat die Zeit vom 10.06.2026 01:00 bis 14.06.2026 "
            "19:00 Uhr verworfen, die Stände des anderen Sensors begannen aber schon am 09.06.2026 22:00 Uhr.") in e.details
    assert e.ziel is not None and e.schwere == "warning"
    await _stueck(db, aid, key, sprung=e.werte["sprung"], rueck=e.werte["rueckgang"])
    assert (await _tagesansicht(db, a, wid))[14] == 61.0
    zw.vergiss(db)
    assert await v._pruefe(db, a) == []


# ═══ G1 — Auskunft «Zählerstände verworfen» ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_ist_luecke"])
async def test_g1_p1_ohne_ha_wie_zaehlerluecke_mit_tag(db, ohne_ha, monkeypatch, sprengsatz):  # noqa: F811
    """Versetztes Stück ohne Home Assistant über «Grund nachtragen» korrigiert (``p1_ohne_ha``) ⇒ eine Zeile, Lage
    Zählerlücke, Tag der Menge 14.06., 11.–13.06. ohne Wert. Sprengsatz: ``ist_luecke`` weggelassen ⇒ keine Zeile."""
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    await _stueck(db, a.id, key)
    if sprengsatz:
        monkeypatch.setattr(zw, "ist_luecke", lambda w: False)
    erg = await _verworfen(db, a.id)
    if sprengsatz:
        assert erg == []
        return
    (e,) = erg
    w = e.werte
    assert (e.code, e.schwere, e.knopf, e.investition_id) == ("zaehler_zeit_verworfen", "info", "Was gilt", wb.id)
    assert (w["lage"], w["tag"], w["von"], w["bis"]) == ("zaehlerluecke", "2026-06-14", "2026-06-10T01:00", "2026-06-14T19:00")
    assert w["tage_ohne_wert"] == ["2026-06-11", "2026-06-12", "2026-06-13"] and w["monate"] == ["2026-06"]
    assert e.meldung == "Ladepunkt – Ladung PV: Zählerstände vom 10.06.2026 01:00 bis 14.06.2026 19:00 Uhr verworfen"
    assert e.details == (
        "Für diese Zeit hat eedc bei einer Korrektur die Zählerstände dieses Felds verworfen, und nichts füllt sie wieder auf — "
        "auch nicht aus Home Assistant; das bleibt so. Davor, in dieser Zeit und danach gilt dieselbe Quelle, und dazwischen ist "
        "kein Zählertausch eingetragen: eedc rechnet über diese Zeit wie über jede Zählerlücke. Die Menge der ganzen Zeit steht "
        "am 14.06.2026 und zählt dort in Tag, Monat und Jahr. Die Tagesansicht zeigt vom 11.06.2026 bis 13.06.2026 für dieses "
        "Feld keinen Wert und am 10.06.2026 nur den Teil außerhalb dieser Zeit.")


async def _luecken_zeilen(db, aid, key, *, ansatz=None):
    """Was der Korrektur-Dienst für eine Korrektur ohne Füllen schreibt: die Korrektur-Zeile und die Lücken-Zeile."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    await _wechsel(db, aid, key, RUECK, QA, QA, grund=GRUND_KORREKTUR, falsch_seit_ts=SPRUNG, herkunft="wechsel")
    await _wechsel(db, aid, key, RUECK, QA, None, grund=GRUND_KORREKTUR, falsch_seit_ts=SPRUNG, herkunft="wechsel",
                   ansatz=ansatz)
    await db.commit()


async def test_g1_hoehe_ungeprueft_keine_differenz(db, ohne_ha, monkeypatch):  # noqa: F811
    from backend.models.zuordnung_wechsel import ANSATZ_HOEHE_UNGEPRUEFT

    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db, spiegel=False)
    await _luecken_zeilen(db, a.id, key, ansatz=ANSATZ_HOEHE_UNGEPRUEFT)
    (e,) = await _verworfen(db, a.id)
    assert (e.werte["lage"], e.werte["grund"], e.werte["tag"]) == ("keine_differenz", "hoehe_ungeprueft", None)
    assert ("Home Assistant führt den richtigen Sensor erst ab dem Ende dieser Zeit; ob seine Zählerstände auf der Höhe der "
            "gespeicherten davor liegen, lässt sich nicht prüfen. eedc bildet über diese Zeit keine Differenz zweier "
            "Zählerstände; die Menge dieser Zeit fehlt in Tag, Monat und Jahr.") in e.details


async def test_g1_kanal_fuehrt_die_zeit_als_verworfen_keine_differenz_und_monat_gespeichert(db, ohne_ha, monkeypatch):  # noqa: F811
    """Eigener Entscheid U3 a: führt der Kanal die Zeit als verworfen (Stundenwerte zählen dort 0, danach ohne Zuwachs), nennt
    die Auskunft «keine Differenz», auch wenn die Reihe wie eine Zählerlücke rechnen würde; ein gespeicherter Monat steht.
    U3 b (P-1): hier ein Spiegel ohne Brücke; setzt ein MQTT-Kanal ohne Höhenwechsel mit der Menge der Zeit an, sagt die
    Auskunft «wie eine Zählerlücke» (``test_sensorwechsel_u3b_proben.py::test_g7_p1_auskunft_zeit_verworfen_wie_zaehlerluecke``)."""
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle
    from backend.models.monatsdaten import Monatsdaten

    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db, spiegel=False)
    await _luecken_zeilen(db, a.id, key)
    k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(SPRUNG.timestamp()), familie=FAMILIE_SPIEGEL, statistic_id=v.SENSOR,
                       offset=0.0, verworfen_ts=int(RUECK.timestamp())))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=0.0))
    await db.commit()
    (e,) = await _verworfen(db, a.id)
    assert (e.werte["lage"], e.werte["grund"], e.werte["monate_gespeichert"]) == ("keine_differenz", "kanal", ["2026-06"])
    assert e.details.endswith("Für 06/2026 ist ein Monatswert gespeichert; er bleibt, wie er ist.")


async def test_g1_aufgehobene_luecke_ist_keine_zeile(db, ohne_ha, monkeypatch):  # noqa: F811
    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db, spiegel=False)
    await _luecken_zeilen(db, a.id, key)
    for row in (await db.execute(select(ZuordnungWechsel))).scalars().all():
        row.aufgehoben_durch = 999
    await db.commit()
    assert await _verworfen(db, a.id) == []


# ═══ G1 — Abgrenzung zu «Stunden ohne Stundenwerte» ═══════════════════════════════════════════════════════════════════

def _tag(von, bis, **mengen):
    from backend.services.daten_checker.erfassung_stillstand import _Stelle, _Tag

    zeile = SimpleNamespace(spannen={a: n for a, n in mengen.pop("spannen", {}).items()}, **mengen)
    return _Tag(bis.date(), None, [_Stelle(von, bis, False, zeile)])


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_abgrenzung"])
async def test_g1_stillstand_laesst_die_verworfene_zeit_aus(monkeypatch, sprengsatz):
    """Topic «verwerfen» (Rechenweg-Saat): Lücke Netzbezug 08.11. 00:00 – 10.11. 11:00, die Stelle «8.11. 0 Uhr bis 10.11.
    12 Uhr» trägt nur den Netzbezug nach ⇒ fällt aus. Trägt die Stelle auch die Einspeisung nach oder liegt sie außerhalb,
    bleibt sie. Sprengsatz: ohne Abgrenzung bleibt der Tag (der unwahre Satz «Tag und Monat zählen die Menge vollständig»)."""
    import backend.services.daten_checker.datenquelle.verworfen as vw
    from backend.services.daten_checker import erfassung_stillstand as es

    lv, lb = datetime(2026, 11, 8), datetime(2026, 11, 10, 11)

    async def _zeiten(_db, _anlage):
        return [] if sprengsatz else [("netzbezug", lv, lb)]
    monkeypatch.setattr(vw, "achsen_der_verworfenen_zeiten", _zeiten)
    nur_netz = _tag(lv, lb + timedelta(hours=1), netzbezug_kw=0.5, einspeisung_kw=0.2, spannen={"netzbezug": 60})
    mit_einsp = _tag(lv, lb + timedelta(hours=1), netzbezug_kw=0.5, einspeisung_kw=3.0,
                     spannen={"netzbezug": 60, "einspeisung": 60})
    ausserhalb = _tag(lv - timedelta(days=3), lv - timedelta(days=2), netzbezug_kw=4.0, spannen={"netzbezug": 6})
    aus = await es._ohne_verworfene_zeit(None, SimpleNamespace(id=1), [nur_netz, mit_einsp, ausserhalb])
    assert aus == ([nur_netz, mit_einsp, ausserhalb] if sprengsatz else [mit_einsp, ausserhalb])


def test_g1_stelle_erklaert_rand_eine_stunde():
    from backend.services.daten_checker.datenquelle.verworfen import stelle_erklaert

    v_ = [("netzbezug", datetime(2026, 11, 8), datetime(2026, 11, 10, 11))]
    assert stelle_erklaert(datetime(2026, 11, 7, 23), datetime(2026, 11, 10, 12), {"netzbezug"}, v_)
    assert not stelle_erklaert(datetime(2026, 11, 7, 22), datetime(2026, 11, 10, 12), {"netzbezug"}, v_)
    assert not stelle_erklaert(datetime(2026, 11, 8), datetime(2026, 11, 10, 13), {"netzbezug"}, v_)
    assert not stelle_erklaert(datetime(2026, 11, 8), datetime(2026, 11, 10, 12), set(), v_)


# ═══ G2 — «Gespeicherter Monatswert passt nicht mehr» ════════════════════════════════════════════════════════════════

NETZ = "basis:netzbezug"
JUNI = datetime(2026, 6, 1)


async def _g2_saat(db, *, gespeichert: float, grund: str = "fortsetzung", behalten=None, bis_tage: int = 32):
    """Netzbezug-Kanal (Spiegel) 0,5 kWh je Stunde ⇒ Juni 360,0 kWh; Monatszeile Juni mit ``gespeichert``; ein Wechsel am
    10.06. 10:00 mit ``grund``."""
    from backend.models.anlage import Anlage
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.models.monatsdaten import Monatsdaten

    a = Anlage(anlagenname="G2", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key=NETZ, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    t0 = int(JUNI.timestamp())
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=t0 - 2 * 3600, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=t0 + 3600 * h, sum=0.5 * (h + 1), state=0.5 * (h + 1),
                               familie=FAMILIE_SPIEGEL) for h in range(-2, bis_tage * 24)])
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=gespeichert,
                       source_provenance={"netzbezug_kwh": {"source": "manual"}},
                       geprueft_gegen={"netzbezug_kwh": behalten} if behalten else {}))
    t = datetime(2026, 6, 10, 10)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=NETZ, erklaert_ts=t, ab_ts=t, vorher={"art": "ha", "entity_id": "sensor.alt"},
                            nachher={"art": "ha", "entity_id": "sensor.netz"}, grund=grund, herkunft="wechsel"))
    await db.commit()
    return a


async def _ueberholt(db, a):
    from backend.services.daten_checker import DatenChecker

    zw.vergiss(db)
    return await DatenChecker(db)._check_monatswert_ueberholt(a, heute=date(2026, 7, 15))


async def test_g2_abweichung_eine_zeile_mit_monat_oeffnen(db):
    (e,) = await _ueberholt(db, await _g2_saat(db, gespeichert=365.0))
    assert (e.code, e.schwere, e.knopf) == ("monatswert_ueberholt", "warning", "Monat öffnen")
    assert (e.ziel.params, e.werte["abweichung_kwh"], e.werte["anlass"]) == (
        {"erfassen": "2026-06", "feld": "netzbezug_kwh"}, -5.0, "fortsetzung")
    assert e.meldung == "Netzbezug: gespeicherter Monatswert 06/2026 passt nicht mehr zur Quelle"
    assert e.details == ("Gespeichert sind 365,0 kWh. Seit dem Wechsel der Quelle am 10.06.2026 ergibt die Quelle für diesen "
                         "Monat 360,0 kWh. Alles, was eedc für diesen Monat zeigt, rechnet mit dem gespeicherten Wert; er "
                         "bleibt, bis du ihn änderst.")


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_toleranz_0"])
async def test_g2_rundung_unter_einer_kwh_ist_keine_zeile(db, monkeypatch, sprengsatz):
    """Produktiv-Kopie im Monat des Wechsels: 242,9 gespeichert gegen 242,871 — kein Unterschied. Sprengsatz Toleranz 0 ⇒ Zeile."""
    import backend.core.berechnungen.monatswert_vergleich as mv

    if sprengsatz:
        monkeypatch.setattr(mv, "MONATSWERT_TOLERANZ_KWH", 0.0)
        monkeypatch.setattr(mv.monatswert_weicht_ab, "__defaults__", (0.0,))
    erg = await _ueberholt(db, await _g2_saat(db, gespeichert=360.029))
    assert len(erg) == (1 if sprengsatz else 0)


@pytest.mark.parametrize("fall", ["ohne_grund", "behalten", "nicht_voll"])
async def test_g2_keine_zeile(db, fall):
    """Ein Wechsel ohne Grund berührt nichts; «gespeicherten behalten» mit genau diesem Wert; ohne volle Deckung des Monats."""
    kw = {"ohne_grund": {"grund": None}, "behalten": {"behalten": {"sensor": 360.0, "wert": 365.0}},
          "nicht_voll": {"bis_tage": 20}}[fall]
    assert await _ueberholt(db, await _g2_saat(db, gespeichert=365.0, **kw)) == []


async def test_g2_korrektur_beruehrt_ihr_intervall():
    from backend.services.daten_checker.datenquelle.monatswert import beruehrte_monate

    w = zw.Wechsel("basis:netzbezug", datetime(2026, 6, 1), QA, QA, "korrektur", datetime(2026, 4, 20), None,
                   datetime(2026, 6, 2, 8), 1)
    assert sorted(beruehrte_monate([w], date(2026, 7, 1))) == [(2026, 4), (2026, 5)]       # endet am 01.06. 00:00
    assert sorted(beruehrte_monate([w], date(2026, 5, 3))) == [(2026, 4)]                  # nur abgeschlossene Monate


# ═══ G3 — SATZ_TAG_FEST nur mit Tag und Wert ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("traegt", [True, False], ids=["tageszeile_traegt_den_schluessel", "ohne"])
async def test_g3_tag_fest_nur_mit_tag_und_wert(db, monkeypatch, traegt):
    """Tausch 12.06. 10:20 (vor dem laufenden Tag): trägt die Tageszeile des 12.06. den Schlüssel des Felds, nennt die Antwort
    Tag und Wert; sonst entfällt der Satz (Bauplan «Zu §14» Nr. 95 (4))."""
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db, spiegel=False, feld="ladung_kwh")
    ziele = await vq.bestand_ziele(db, a, key)
    assert ziele.tz_keys                                              # Wallbox «Ladung gesamt» steht in der Tageszeile
    tag = date(2026, 6, 12)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=tag,
                                komponenten_kwh={sorted(ziele.tz_keys)[0] if traegt else "andere_1": 7.25}))
    await db.commit()
    la = zg.Lage(key, zg.WEG_FORTSETZUNG, QA, datetime(2026, 6, 12, 10, 20), vor_heute=True,
                 tag_fest=await zg.tag_fest(db, a, key, datetime(2026, 6, 12, 11)))
    saetze = zg.saetze(la)
    if traegt:
        assert la.tag_fest == (tag, 7.25)
        assert saetze[-1] == ("Für den 12.06.2026 hat eedc schon einen festen Tageswert dieses Felds gespeichert (7,25 kWh); "
                              "er bleibt, wie er ist, und kann den Unterschied weiter enthalten.")
    else:
        assert la.tag_fest is None and not any("festen Tageswert" in s for s in saetze)
