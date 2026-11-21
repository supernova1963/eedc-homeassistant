"""Sensorwechsel mit Grund, Korrekturrunde 3a-K — Proben der tragenden Stellen (Bauplan §10 Nr. 32–38).

Je Probe ein Sprengsatz im selben Test (der Prüfling mit einem bewusst falschen Baustein muss rot werden). Feste Zeit
(``ZEIT``/``JETZT`` aus ``test_kanal_nachfuellen``), keine Uhr. Lagen und Helfer aus ``test_sensorwechsel_s3_korrektur``
(A-B-A an ``basis:einspeisung``: richtig ``sensor.einsp``, falsch ``sensor.falsch`` ab F, zurück ab AB; MQTT an
``basis:netzbezug``).

Äquivalente Mutanten (benannt, nicht beprobt):

* ``vergiss`` allein bzw. ``merke_neu`` allein weg (Schritt 1): ``vergiss`` erzwingt ein Neuladen der Wechsel aus der
  Datenbank (die Zeile ist geflusht), ``merke_neu`` hängt sie in die geladene Liste — eins von beiden genügt; beide weg
  ist beprobt (``test_merker_*``).
* ``fuehre_aus`` ohne die Bedingung «nur mit Home Assistant» bei ``tage``: ``lage`` bildet ohne Home Assistant keine
  Tage-Liste (beprobt) — die zweite Sicherung ändert nichts, solange die erste steht.
* ``_wie_vorher`` ohne Zählung: die Zahl steht nur im Zustand ``behalten``.

Schwesterdateien: test_sensorwechsel_s3_korrektur.py, test_werkbank_verwerfen_vor_quellbeginn.py,
test_kanal_verworfen_bewusst_leer.py.
"""

from __future__ import annotations

import dataclasses
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_, delete, func, insert, select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import ART_SUM, FAMILIE_ABGELEITET, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.models.zuordnung_wechsel import GRUND_KORREKTUR, ZuordnungWechsel
from backend.services import verwerfen_vor_quellbeginn as vq
from backend.services.kanal import korrektur as kk
from backend.services.kanal import lesen, merken
from backend.services.kanal.lesen import GRUND_VERWORFEN
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.services.snapshot.keys import _sensor_key_to_mqtt_key
from backend.services.zuordnung_wechsel import korrektur as kr
from backend.services.zuordnung_wechsel import korrektur_lauf as kl
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    ZEIT,
    _ts,
    datei,
    ha,
)
from backend.tests.test_sensorwechsel_s3_korrektur import (
    AB,
    EINSP,
    F,
    H0,
    LAUF_JETZT,
    MAB,
    MF,
    NETZ,
    _aba,
    _auftrag,
    _falscher_sensor,
    _korrigieren,
    _mqtt_auftrag,
    _mqtt_lage,
    _mqtt_stundenlauf,
    _staende,
    _zr,
)
from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _kanal, _quellen, _stundenlauf, _zuordnung

H = 3600


async def _anlage(s, aid) -> Anlage:
    return (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()


async def _snapshots(sitzungen, aid, key, zeiten, werte=None) -> None:
    async with sitzungen() as s:
        await s.execute(insert(SensorSnapshot), [
            {"anlage_id": aid, "sensor_key": key, "zeitpunkt": z, "wert_kwh": (werte or {}).get(z, 1.0 + i), "quelle": "probe"}
            for i, z in enumerate(zeiten)])


async def _zeitpunkte(sitzungen, aid, key, quelle: str = "probe") -> set:
    """Die Zeitpunkte der Stände mit dieser Quelle — seit 4b-1-K2 (Bauplan «Zu §14» Nr. 111) liest die Korrektur die Stände der
    gefüllten Zeit aus Home Assistant neu und speichert sie (``ha_statistics``); verworfen ist, was als ``probe`` fehlt."""
    async with sitzungen() as s:
        return set((await s.execute(select(SensorSnapshot.zeitpunkt).where(and_(
            SensorSnapshot.anlage_id == aid, SensorSnapshot.sensor_key == key, SensorSnapshot.quelle == quelle)))).scalars().all())


def _staende_mutant(art: str):
    """Sprengsätze für das Verwerfen der Zählerstände (Schritt 2)."""
    async def verwerfe(db, a, ab):
        if art == "nichts":
            return 0, 0
        unten = (SensorSnapshot.zeitpunkt > a.falsch_seit) if art == "f_exklusiv" else (SensorSnapshot.zeitpunkt >= a.falsch_seit)
        oben = (SensorSnapshot.zeitpunkt <= ab) if art == "ab_inklusiv" else (SensorSnapshot.zeitpunkt < ab)
        n = (await db.execute(delete(SensorSnapshot).where(and_(
            SensorSnapshot.anlage_id == a.anlage_id, SensorSnapshot.sensor_key == a.sensor_key, unten, oben)))).rowcount
        return int(n or 0), 0
    return verwerfe


# ── Zählerstände: [falsch_seit, ab) — beide Grenzen ─────────────────────────


@pytest.mark.parametrize("sprengsatz", [None, "nichts", "f_exklusiv", "ab_inklusiv"])
async def test_zaehlerstaende_im_intervall_verworfen_grenzen(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    zeiten = [F - timedelta(hours=1), F, AB - timedelta(hours=1), AB, AB + timedelta(hours=1)]
    # die Stände ab AB stammen aus der richtigen Quelle — auf HAs Höhe (U1-K (d): gefüllt wird nur auf geprüfter Höhe)
    await _snapshots(sitzungen, aid, EINSP, zeiten, {z: svc.get_value_at("sensor.einsp", z) for z in zeiten[3:]})
    if sprengsatz:
        monkeypatch.setattr(kr, "_verwerfe_staende", _staende_mutant(sprengsatz))
    erg = await _korrigieren(sitzungen, _auftrag(aid), svc)
    soll = {F - timedelta(hours=1), AB, AB + timedelta(hours=1)}
    assert (await _zeitpunkte(sitzungen, aid, EINSP) == soll) is (sprengsatz is None)
    if sprengsatz is None:      # Nr. 111: der Lauf liest die verworfenen Stände aus Home Assistant neu und speichert sie
        monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
        import backend.services.ha_statistics_service as hss
        monkeypatch.setattr(hss, "_ha_statistics_service", svc)
        await kl.tage_neu_bilden(sitzungen, erg["lauf"])
        assert {F, AB - timedelta(hours=1)} <= await _zeitpunkte(sitzungen, aid, EINSP, "ha_statistics")


@pytest.mark.parametrize("sprengsatz", [None, "ab_inklusiv"])
async def test_mqtt_rohstaende_grenze_ab_bleibt(ha, datei, monkeypatch, sprengsatz):
    svc, sitzungen, aid, k = await _mqtt_lage(ha, datei, monkeypatch)
    mk = _sensor_key_to_mqtt_key(NETZ)
    async with sitzungen() as s:
        s.add(MqttEnergySnapshot(anlage_id=aid, energy_key=mk, timestamp=MAB, value_kwh=300.0))
    if sprengsatz:
        echt = kr._verwerfe_staende

        async def mutant(db, a, ab):
            return await echt(db, a, ab + timedelta(seconds=1))      # «<= ab»
        monkeypatch.setattr(kr, "_verwerfe_staende", mutant)
    await _korrigieren(sitzungen, _mqtt_auftrag(aid), None, jetzt=MAB + timedelta(minutes=5))
    async with sitzungen() as s:
        zeiten = set((await s.execute(select(MqttEnergySnapshot.timestamp).where(and_(
            MqttEnergySnapshot.anlage_id == aid, MqttEnergySnapshot.energy_key == mk)))).scalars().all())
    assert not [z for z in zeiten if MF <= z < MAB]
    assert MF - timedelta(minutes=15) in zeiten
    assert (MAB in zeiten) is (sprengsatz is None)


# ── Tage-Liste (§7 Nr. 10, §10 Nr. 35) ─────────────────────────────────────


async def _tagzeilen_seed(sitzungen, aid):
    """F.date()−1 (vor dem Intervall), F.date(), F.date()+1 (Herkunft Kanal-Tag), F.date()+2 (ohne den Schlüssel),
    AB.date() (Fenster schneidet [F, AB)), AB.date()+1 (danach)."""
    from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

    d = F.date()
    tage = {
        d - timedelta(days=1): ({"einspeisung": 1.0}, None),
        d: ({"einspeisung": 2.0}, None),
        d + timedelta(days=1): ({"einspeisung": 3.0}, {"komponenten_kwh.einspeisung": {"source": TZ_QUELLE_KANAL}}),
        d + timedelta(days=2): ({"netzbezug": 4.0}, None),
        AB.date(): ({"einspeisung": 5.0}, None),
        AB.date() + timedelta(days=1): ({"einspeisung": 6.0}, None),
    }
    async with sitzungen() as s:
        for tag, (komp, prov) in tage.items():
            s.add(TagesZusammenfassung(anlage_id=aid, datum=tag, komponenten_kwh=komp, source_provenance=prov))
    return [d, d + timedelta(days=1), AB.date()]


@pytest.mark.parametrize("sprengsatz", [None, "umgekehrt", "ohne_untergrenze", "herkunft", "ohne_ha"])
async def test_tage_liste_kriterium_grenzen_ohne_herkunft(datei, monkeypatch, sprengsatz):
    sitzungen, _p, aid, _g = datei
    soll = await _tagzeilen_seed(sitzungen, aid)
    if sprengsatz == "umgekehrt":
        echt = vq.tz_keys_der_zeile
        monkeypatch.setattr(vq, "tz_keys_der_zeile", lambda row, z: [] if echt(row, z) else ["x"])
    elif sprengsatz == "ohne_untergrenze":
        echt_z = vq._tz_zeilen

        async def ohne(db, anlage_id, bis_tag, ziele, von_tag=None):
            return await echt_z(db, anlage_id, bis_tag, ziele, None)
        monkeypatch.setattr(vq, "_tz_zeilen", ohne)
    elif sprengsatz == "herkunft":                         # die Liste von 3a: Herkunft «Kanal-Tag» ausgelassen
        from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

        async def mit_filter(db, a, ziele):
            bis = kl_tag(a.ab - timedelta(hours=1))
            out = []
            for row in await vq._tz_zeilen(db, a.anlage_id, bis, ziele, kl_tag(a.falsch_seit)):
                prov = row.source_provenance or {}
                if any((prov.get(f"komponenten_kwh.{x}") or {}).get("source") != TZ_QUELLE_KANAL
                       for x in vq.tz_keys_der_zeile(row, ziele)):
                    out.append(row.datum)
            return sorted(out)
        monkeypatch.setattr(kr, "tage_neu_bilden_liste", mit_filter)
    elif sprengsatz == "ohne_ha":                          # «Tage auch ohne Home Assistant»
        echt_l = kr.lage

        async def lage_immer(db, a, *, ha_svc=None):
            la = await echt_l(db, a, ha_svc=ha_svc)
            la.tage_neu = await kr.tage_neu_bilden_liste(db, a, la.ziele)
            return la
        monkeypatch.setattr(kr, "lage", lage_immer)
    a = _auftrag(aid)
    async with sitzungen() as s:
        mit = await kr.lage(s, a, ha_svc=SimpleNamespace(is_available=True, get_stundenzeilen_kennzahlen=_GANZE_GESCHICHTE))
        ohne = await kr.lage(s, a, ha_svc=None)
    gut = mit.tage_neu == soll and kr.vorschau_daten(ohne)["tage_neu"] == [] and not ohne.tage_neu
    assert gut is (sprengsatz is None), (mit.tage_neu, ohne.tage_neu)


def _GANZE_GESCHICHTE(*_a):
    """Attrappe: HA führt den richtigen Sensor seit jeher (keine Lücke, Sitzung 4b-1 ``korrektur._luecke``)."""
    return {"anzahl": 1, "erste_ts": 0}


def kl_tag(dt: datetime) -> date:
    from backend.services.kanal.abgeleitet import tag_der_stunde

    return tag_der_stunde(int(dt.timestamp()))


async def test_tage_liste_findet_einen_schon_neu_gebildeten_tag_wieder(datei):
    """§10 Nr. 35: nach einem Lauf trägt der Tag die Herkunft «Kanal-Tag» — eine zweite Korrektur desselben Felds findet ihn."""
    sitzungen, _p, aid, _g = datei
    soll = await _tagzeilen_seed(sitzungen, aid)
    async with sitzungen() as s:
        for row in (await s.execute(select(TagesZusammenfassung))).scalars().all():
            from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

            row.source_provenance = {f"komponenten_kwh.{x}": {"source": TZ_QUELLE_KANAL} for x in row.komponenten_kwh}
    async with sitzungen() as s:
        assert (await kr.lage(s, _auftrag(aid), ha_svc=SimpleNamespace(is_available=True, get_stundenzeilen_kennzahlen=_GANZE_GESCHICHTE))).tage_neu == soll


# ── Bestand: nur Tage, deren Fenster ganz im Intervall liegt (von_tag) ──────


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_bestand_untergrenze_von_tag(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    d = F.date()                          # Fenster [d−1 23:00, d 23:00) beginnt vor F ⇒ bleibt
    async with sitzungen() as s:
        for tag in (d, d + timedelta(days=1)):
            s.add(TagesZusammenfassung(anlage_id=aid, datum=tag, komponenten_kwh={"einspeisung": 9.0, "netzbezug": 1.0}))
    if sprengsatz:
        echt = vq.leere_bestand

        async def ohne_von(db, anlage_id, ziele, bis_tag, abschluss, von_tag=None):
            return await echt(db, anlage_id, ziele, bis_tag, abschluss, None)
        monkeypatch.setattr(vq, "leere_bestand", ohne_von)
    await _korrigieren(sitzungen, _auftrag(aid), None)
    async with sitzungen() as s:
        rows = {r.datum: r.komponenten_kwh for r in (await s.execute(select(TagesZusammenfassung))).scalars().all()}
    assert "einspeisung" not in rows[d + timedelta(days=1)] and rows[d + timedelta(days=1)]["netzbezug"] == 1.0
    assert ("einspeisung" in rows[d]) is (not sprengsatz)


# ── Wechsel-Zeile: aufgehoben_durch und sein Fenster ───────────────────────


def _ersetzte_mutant(art: str):
    async def ersetzte(db, a, f):
        bed = [ZuordnungWechsel.anlage_id == a.anlage_id, ZuordnungWechsel.sensor_key == a.sensor_key,
               ZuordnungWechsel.aufgehoben_durch.is_(None),
               ZuordnungWechsel.ab_ts <= (a.ab if art == "ohne_stunde" else a.ab + timedelta(hours=1))]
        if art != "ohne_untergrenze":
            bed.append(ZuordnungWechsel.ab_ts >= f)
        alte = (await db.execute(select(ZuordnungWechsel).where(and_(*bed)))).scalars().all()
        if art == "keine":
            return []
        return [w for w in alte if (art == "grund_egal" or w.grund != GRUND_KORREKTUR)
                and (art == "nachher_egal" or (w.nachher or {}) == (a.nachher or {}))]
    return ersetzte


async def _wechsel_ohne_max(db, a, jetzt, lauf, w0):
    """Sprengsatz: ``ab`` der neuen Zeile ist das angegebene, nicht das spätere der aufgehobenen."""
    from backend.services.zuordnung_wechsel.zeitpunkt import merke_neu, vergiss

    f = kr._beginn(a, w0)
    ersetzt = await kr._ersetzte(db, a, f)
    row = ZuordnungWechsel(anlage_id=a.anlage_id, sensor_key=a.sensor_key, erklaert_ts=jetzt, ab_ts=a.ab, vorher=a.vorher,
                           nachher=a.nachher, grund=GRUND_KORREKTUR, falsch_seit_ts=f, herkunft=a.herkunft, lauf=lauf)
    db.add(row)
    await db.flush()
    for w in ersetzt:
        w.aufgehoben_durch = row.id
    vergiss(db, a.anlage_id)
    merke_neu(db, row)
    return row


@pytest.mark.parametrize("sprengsatz", [None, "keine", "ohne_stunde", "nachher_egal", "grund_egal", "ohne_untergrenze",
                                        "ab_ohne_max"])
async def test_aufgehoben_durch_fenster_und_ab(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    gleich = {"art": "ha", "entity_id": "sensor.einsp"}
    zeilen = {  # name: (ab_ts, nachher, grund)
        "eine_stunde_danach": (AB + timedelta(hours=1), gleich, None),
        "anderes_nachher": (AB, {"art": "ha", "entity_id": "sensor.anders"}, None),
        "fruehere_korrektur": (AB, gleich, GRUND_KORREKTUR),
        "zwei_stunden_danach": (AB + timedelta(hours=2), gleich, None),
        "vor_f": (F - timedelta(hours=1), gleich, None),
    }
    ids = {}
    async with sitzungen() as s:
        for name, (ab_ts, nachher, grund) in zeilen.items():
            w = ZuordnungWechsel(anlage_id=aid, sensor_key=EINSP, erklaert_ts=ab_ts, ab_ts=ab_ts, vorher=None,
                                 nachher=nachher, grund=grund, falsch_seit_ts=F if grund else None, herkunft="wechsel")
            s.add(w)
            await s.flush()
            ids[name] = w.id
    await _snapshots(sitzungen, aid, EINSP, [AB])           # zwischen AB und dem späteren ab_ts: wird mit verworfen
    if sprengsatz == "ab_ohne_max":
        monkeypatch.setattr(kr, "_wechsel_zeile", _wechsel_ohne_max)
    elif sprengsatz:
        monkeypatch.setattr(kr, "_ersetzte", _ersetzte_mutant(sprengsatz))
    s_ = await _korrigieren(sitzungen, _auftrag(aid), svc)
    async with sitzungen() as s:
        rows = {w.id: w for w in (await s.execute(select(ZuordnungWechsel))).scalars().all()}
    neu = rows[s_["wechsel_id"]]
    aufgehoben = {name for name, i in ids.items() if rows[i].aufgehoben_durch == neu.id}
    gut = (aufgehoben == {"eine_stunde_danach"} and neu.ab_ts == AB + timedelta(hours=1)
           and AB not in await _zeitpunkte(sitzungen, aid, EINSP))
    assert gut is (sprengsatz is None), (aufgehoben, neu.ab_ts)


# ── Kanal: Fortsetzung nach ab (MQTT, Zeilen nach ab schon geschrieben) ─────


async def _mqtt_mit_zeilen_nach_ab(ha, datei, monkeypatch):
    svc, sitzungen, aid, k = await _mqtt_lage(ha, datei, monkeypatch)
    await _staende(sitzungen, aid, MAB, MAB + timedelta(hours=4), 300.0, 0.5)
    await _mqtt_stundenlauf(sitzungen, aid, MAB + timedelta(hours=1), MAB + timedelta(hours=4), monkeypatch, svc)
    async with sitzungen() as s:
        assert (await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(MAB))))).scalar_one() >= 3
    return svc, sitzungen, aid, k


async def _kanalwert(sitzungen, kanal_id, ts) -> float:
    async with sitzungen() as s:
        z = (await s.execute(select(KanalStatistik).where(and_(KanalStatistik.kanal_id == kanal_id,
                                                               KanalStatistik.start_ts == ts)))).scalar_one()
        off = (await s.execute(select(KanalQuelle.offset).where(and_(
            KanalQuelle.kanal_id == kanal_id, KanalQuelle.gueltig_ab <= ts)).order_by(KanalQuelle.gueltig_ab.desc())
            .limit(1))).scalar_one()
    return float(z.sum) + float(off)


@pytest.mark.parametrize("sprengsatz", [None, "aus", "ohne_bruecke"])
async def test_fortsetzung_nach_ab_mit_zeilen_danach(ha, datei, monkeypatch, sprengsatz):
    svc, sitzungen, aid, k = await _mqtt_mit_zeilen_nach_ab(ha, datei, monkeypatch)
    if sprengsatz == "aus":
        async def nichts(*a, **kw):
            return None
        monkeypatch.setattr(kk, "_fortsetzung_nach_ab", nichts)
    elif sprengsatz == "ohne_bruecke":
        echt = kk._fortsetzung_nach_ab

        async def ohne(db, kanal, ab, leer_bis, ref, o_ref, *rest):      # U3 b: ``bruecke`` (G7 (b)) geht mit
            return await echt(db, kanal, ab, leer_bis, None, 0.0, *rest)
        monkeypatch.setattr(kk, "_fortsetzung_nach_ab", ohne)
    await _korrigieren(sitzungen, _mqtt_auftrag(aid), None, jetzt=MAB + timedelta(hours=4, minutes=5))
    async with sitzungen() as s:
        erste = (await s.execute(select(func.min(KanalStatistik.start_ts)).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(MAB))))).scalar_one()
        letzte_vor = (await s.execute(select(func.max(KanalStatistik.start_ts)).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts < _ts(MF))))).scalar_one()
    erste_dt = datetime.fromtimestamp(erste)
    voll = (await _zr(sitzungen, k, erste_dt + timedelta(hours=1), erste_dt + timedelta(hours=3))).voll
    bruecke = abs(await _kanalwert(sitzungen, k.id, erste) - await _kanalwert(sitzungen, k.id, letzte_vor)) < 1e-6
    assert (voll and bruecke) is (sprengsatz is None), (voll, bruecke)


# ── Kanal: R2-Referenz mit dem Versatz ihres Abschnitts, Rückfall auf h0, spätere andere Quellen ──


async def _aba_mit_offset(ha, datei, offset=100.0):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    async with sitzungen() as s:
        q = (await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id).order_by(KanalQuelle.gueltig_ab)
                             .limit(1))).scalar_one()
        q.offset = offset
    return svc, reihen, sitzungen, aid, k


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_r2_referenz_traegt_den_versatz_ihres_abschnitts(ha, datei, monkeypatch, sprengsatz):
    """Kanalwert an H0 − Kanalwert am letzten Stand vor F = Zuwachs von A in HA (die Stände setzen fort)."""
    svc, reihen, sitzungen, aid, k = await _aba_mit_offset(ha, datei)
    if sprengsatz:
        async def ohne_versatz(db, kanal, w0):
            z = (await db.execute(select(KanalStatistik.start_ts, KanalStatistik.sum).where(and_(
                KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts < w0)).order_by(
                KanalStatistik.start_ts.desc()).limit(1))).one()
            return int(z[0]), float(z[1])
        monkeypatch.setattr(kk, "_referenz", ohne_versatz)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    a = reihen["sensor.einsp"]
    vor = _ts(F - timedelta(hours=1))
    sprung = await _kanalwert(sitzungen, k.id, _ts(H0)) - await _kanalwert(sitzungen, k.id, vor)
    assert (abs(sprung - (a[_ts(H0)]["sum"] - a[vor]["sum"])) < 1e-6) is (not sprengsatz)


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_r2_rueckfall_auf_h0_ohne_ha_wert_am_referenz_zeitpunkt(ha, datei, monkeypatch, sprengsatz):
    """HA führt A am letzten Stand vor F nicht mehr ⇒ Versatz an H0: die erste Stunde zählt 0."""
    from sqlalchemy import text

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    vor = _ts(F - timedelta(hours=1))
    with svc._engine.begin() as c:
        mid = c.execute(text("SELECT id FROM statistics_meta WHERE statistic_id = 'sensor.einsp'")).scalar_one()
        c.execute(text("DELETE FROM statistics WHERE metadata_id = :m AND start_ts = :t"), {"m": mid, "t": vor})
    if sprengsatz:
        echt = kk._ha_wert

        async def ohne_rueckfall(ha_svc, kanal, eid, ts):
            return await echt(ha_svc, kanal, eid, ts) if ts == vor else None
        monkeypatch.setattr(kk, "_ha_wert", ohne_rueckfall)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    sprung = await _kanalwert(sitzungen, k.id, _ts(H0)) - await _kanalwert(sitzungen, k.id, vor)
    assert (abs(sprung) < 1e-6) is (not sprengsatz), sprung


async def _abac(ha, datei):
    """A-B-A wie ``_aba``, danach ab AB + 6 h eine andere Entität C (der Stundenlauf legt sie mit einem Versatz an)."""
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    mid = ha_lts_helfer.sensor(svc, "sensor.c", "kWh")
    t, wert = AB, 70.0
    while t < AB + timedelta(hours=12):
        wert += 0.5
        ha_lts_helfer.zeile(svc, mid, t, state=wert, sum_wert=wert)
        t += timedelta(hours=1)
    await _stundenlauf(sitzungen, aid, svc, AB + timedelta(hours=6))
    await _zuordnung(sitzungen, aid, einspeisung="sensor.c")
    await _stundenlauf(sitzungen, aid, svc, AB + timedelta(hours=10))
    qs = await _quellen(sitzungen, k.id)
    assert [q.statistic_id for q in qs] == ["sensor.einsp", "sensor.falsch", "sensor.einsp", "sensor.c"]
    return svc, reihen, sitzungen, aid, k, qs[-1].gueltig_ab


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_spaetere_andere_quelle_rueckt_mit(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k, c0 = await _abac(ha, datei)
    von, bis = datetime.fromtimestamp(c0 - H), datetime.fromtimestamp(c0 + 2 * H)
    vorher = (await _zr(sitzungen, k, von, bis)).delta
    if sprengsatz:
        async def ohne_verschiebung(db, kanal, lage, ab, h0, versatz, ref, richtig, jetzt_ts, *rest):
            spaeter = kk._spaetere_richtige(list(lage.quellen), ab, richtig)
            fest = {q.gueltig_ab: q.offset for q in lage.quellen if q.gueltig_ab > (spaeter[-1].gueltig_ab if spaeter else ab)}
            n = await echt_umschreiben(db, kanal, lage, ab, h0, versatz, ref, richtig, jetzt_ts, *rest)
            for q in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id))).scalars().all():
                if q.gueltig_ab in fest:
                    q.offset = fest[q.gueltig_ab]
            await db.flush()
            return n
        echt_umschreiben = kk._quellen_umschreiben
        monkeypatch.setattr(kk, "_quellen_umschreiben", ohne_verschiebung)
    await _korrigieren(sitzungen, _auftrag(aid), svc, jetzt=AB + timedelta(hours=10, minutes=5))
    nachher = (await _zr(sitzungen, k, von, bis)).delta
    assert vorher is not None and nachher is not None
    assert (abs(nachher - vorher) < 1e-6) is (not sprengsatz), (vorher, nachher)


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_zweite_korrektur_findet_im_kanal_nichts_trotz_spaeterer_fremder_quelle(ha, datei, monkeypatch, sprengsatz):
    """``_schneidet``: ein Abschnitt ganz nach ``ab`` (C) gehört nicht zum Intervall — nach der ersten Korrektur ist im Kanal
    nichts mehr zu tun (die Werkbank sagt «nichts zu verwerfen»), ein zweiter Lauf ändert keine Quelle."""
    svc, reihen, sitzungen, aid, k, c0 = await _abac(ha, datei)
    jetzt = AB + timedelta(hours=10, minutes=5)
    await _korrigieren(sitzungen, _auftrag(aid), svc, jetzt=jetzt)
    vorher = [(q.gueltig_ab, q.statistic_id, q.offset, q.verworfen_ts) for q in await _quellen(sitzungen, k.id)]
    if sprengsatz:
        monkeypatch.setattr(kk, "_schneidet", lambda a, f, ab: True)
    async with sitzungen() as s:
        nichts = (await kr.lage(s, _auftrag(aid), ha_svc=svc)).nichts_zu_tun
    s_ = await _korrigieren(sitzungen, _auftrag(aid), svc, jetzt=jetzt)
    nachher = [(q.gueltig_ab, q.statistic_id, q.offset, q.verworfen_ts) for q in await _quellen(sitzungen, k.id)]
    assert nachher == vorher and s_["kanalzeilen_geloescht"] == 0
    assert nichts is (not sprengsatz)


# ── Kanal: nur falsche Abschnitte, Teil im Intervall, Beginn des falschen Teils ─


@pytest.mark.parametrize("sprengsatz", [None, "auch_richtige", "w0_gleich_f"])
async def test_nur_falsche_abschnitte_und_w0(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    f = F - timedelta(days=2)                     # A ist dort richtig
    async with sitzungen() as s:
        vor = {r.start_ts: r.sum for r in (await s.execute(select(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(f), KanalStatistik.start_ts < _ts(F))))).scalars()}
    if sprengsatz == "auch_richtige":
        monkeypatch.setattr(kk, "ist_richtig", lambda q, richtig: False)
    elif sprengsatz == "w0_gleich_f":
        echt = kk.kanal_lage

        async def lage_f(db, anlage_id, key, f_, ab, richtig):
            la = await echt(db, anlage_id, key, f_, ab, richtig)
            return dataclasses.replace(la, w0=f_) if la.w0 is not None else la
        monkeypatch.setattr(kk, "kanal_lage", lage_f)
    await _korrigieren(sitzungen, _auftrag(aid, f=f), svc)
    async with sitzungen() as s:
        nach = {r.start_ts: r.sum for r in (await s.execute(select(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(f), KanalStatistik.start_ts < _ts(F))))).scalars()}
    qs = [(q.gueltig_ab, q.statistic_id, q.verworfen_ts is not None) for q in await _quellen(sitzungen, k.id)]
    gut = nach == vor and len(vor) == 48 and qs == [(_ts(ZEIT), "sensor.einsp", False), (_ts(F), "sensor.falsch", True),
                                                    (_ts(H0), "sensor.einsp", False)]
    assert gut is (sprengsatz is None), qs


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_teil_des_falschen_abschnitts_vor_falsch_seit_bleibt(ha, datei, monkeypatch, sprengsatz):
    """``falsch_seit`` mitten im falschen Abschnitt: dessen Zeilen davor bleiben (``_teil``). U3-K3 (B2, Bauplan Nr. 163, neue
    Erwartung): auch die Zeile ``f − 1 h`` bleibt — Home Assistant führt dort keine Zeile des richtigen Sensors (seine Lücke
    beginnt an F), die Stunde zählt der bis dahin geltende (``korrektur.kanal_beginn``); bis U3-K2 (U1 Punkt 4) fiel sie weg."""
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    f = F + timedelta(days=1)
    if sprengsatz:
        monkeypatch.setattr(kk, "_teil", lambda a, f_, ab: (a.von, ab if a.bis is None else min(ab, a.bis)))
    async with sitzungen() as s:
        bed = and_(KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(F), KanalStatistik.start_ts < _ts(f) - 3600)
        vor = (await s.execute(select(func.count()).select_from(KanalStatistik).where(bed))).scalar_one()
        rand = and_(KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts == _ts(f) - 3600)
        rand_vor = (await s.execute(select(func.count()).select_from(KanalStatistik).where(rand))).scalar_one()
    await _korrigieren(sitzungen, _auftrag(aid, f=f), svc)
    async with sitzungen() as s:
        nach = (await s.execute(select(func.count()).select_from(KanalStatistik).where(bed))).scalar_one()
        rand_nach = (await s.execute(select(func.count()).select_from(KanalStatistik).where(rand))).scalar_one()
    assert vor == 23 and (nach == vor) is (not sprengsatz)
    assert (rand_vor, rand_nach) == (1, 0 if sprengsatz else 1)       # Sprengsatz: der ganze Abschnitt fällt, auch f − 1 h


# ── Füllen bis zum Soll-Ende (bis_ts), auch ohne Spiegelzeile danach ───────


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_fuellen_mit_bis_ts(ha, datei, monkeypatch, sprengsatz):
    from backend.services.kanal import nachfuellen

    svc, reihen = ha
    sitzungen, _p, aid, _g = datei
    _falscher_sensor(svc)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=F, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.falsch")
    await _stundenlauf(sitzungen, aid, svc, AB)           # danach kein Stundenlauf mehr: nach AB keine Zeile
    await _zuordnung(sitzungen, aid, einspeisung="sensor.einsp")
    k = await _kanal(sitzungen, aid, EINSP)
    if sprengsatz:
        echt = nachfuellen.neu_spiegeln

        async def ohne_bis(sitzungen_, kanal_id, ab_ts, *, ha_svc, block_stunden=nachfuellen.BLOCK_STUNDEN, bis_ts=None):
            return await echt(sitzungen_, kanal_id, ab_ts, ha_svc=ha_svc, block_stunden=block_stunden)
        monkeypatch.setattr(nachfuellen, "neu_spiegeln", ohne_bis)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    async with sitzungen() as s:
        n = (await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(H0), KanalStatistik.start_ts < _ts(AB))))).scalar_one()
    assert (n == (_ts(AB) - _ts(H0)) // H) is (not sprengsatz), n


# ── Merker (Schritt 5) und die Wechsel-Merkliste der Sitzung ───────────────


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_merker_der_anlage_verworfen(datei, monkeypatch, sprengsatz):
    """Ein Feld ohne Kanal (nur Zählerstände): einzig Schritt 5 verwirft die gemerkten Tage der Anlage."""
    sitzungen, _p, aid, _g = datei
    key = "basis:pv_gesamt"
    await _snapshots(sitzungen, aid, key, [F, F + timedelta(hours=1)])
    if sprengsatz:
        monkeypatch.setattr(merken, "invalidiere", lambda *a, **kw: None)
    vorher = merken.generation(aid)
    s_ = await _korrigieren(sitzungen, _auftrag(aid, key=key), None)
    assert s_["zaehlerstaende_geloescht"] == 2
    assert (merken.generation(aid) > vorher) is (not sprengsatz)


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_merkliste_der_sitzung_kennt_die_neue_zeile(ha, datei, monkeypatch, sprengsatz):
    from backend.services.zuordnung_wechsel import zeitpunkt

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    if sprengsatz:
        monkeypatch.setattr(zeitpunkt, "vergiss", lambda db, anlage_id=None: None)
        monkeypatch.setattr(zeitpunkt, "merke_neu", lambda db, row: None)
    async with sitzungen() as s:
        await zeitpunkt.lade_wechsel(s, aid)                     # die Sitzung hat die (leere) Liste gemerkt
        await kr.fuehre_aus(s, _auftrag(aid), ha_svc=None, jetzt=LAUF_JETZT)
        antwort = zeitpunkt.quelle_am((await zeitpunkt.lade_wechsel(s, aid)).get(EINSP), F + timedelta(hours=5))
    # Ohne Home Assistant füllt nichts: seit 4b-1 gilt dort die Lücken-Zeile (jünger) — die Quelle ist unbekannt.
    assert (antwort is zeitpunkt.UNBEKANNT) is (not sprengsatz), antwort


# ── Leser: «gilt hier» und die Grenze bis ──────────────────────────────────


@pytest.mark.parametrize("sprengsatz", [None, "hier_ignoriert", "grenze_inklusiv"])
async def test_leser_verworfen_gilt_hier_und_grenze(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    if sprengsatz == "hier_ignoriert":
        monkeypatch.setattr(lesen, "_beruehrt_verworfen",
                            lambda f, von, bis, *_: f is not None and f.verworfen_ab is not None and f.verworfen_ab < bis)
    elif sprengsatz == "grenze_inklusiv":
        monkeypatch.setattr(lesen, "_beruehrt_verworfen", lambda f, von, bis, *_: f is not None and (
            f.verworfen_hier or (f.verworfen_ab is not None and f.verworfen_ab <= bis)))
    drin = await _zr(sitzungen, k, F + timedelta(days=1), H0 + timedelta(hours=30))      # beginnt im verworfenen Teil
    davor = await _zr(sitzungen, k, F - timedelta(hours=2), F)
    assert (drin.grund == GRUND_VERWORFEN and davor.voll) is (sprengsatz is None), (drin.grund, davor.grund)


# ── BewusstLeer: die erste Zeile je Abschnitt (Lader) ──────────────────────


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_bewusst_leer_lader_traegt_die_erste_zeile_je_abschnitt(ha, datei, monkeypatch, sprengsatz):
    """Eine Zeile IM verworfenen Abschnitt (der Kanal hat seine erste Zeile woanders) ⇒ nicht bewusst leer."""
    from backend.services.kanal import bilanz_adapter

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    z = _ts(F + timedelta(days=1))
    async with sitzungen() as s:
        s.add(KanalStatistik(kanal_id=k.id, start_ts=z, sum=1.0, state=1.0, familie="spiegel"))
    if sprengsatz:                                     # Lader ohne erste Zeile je Abschnitt (3-Tupel wie vor 3a)
        echt = bilanz_adapter._erste_im_abschnitt
        monkeypatch.setattr(bilanz_adapter, "_erste_im_abschnitt", lambda a, erste: echt(tuple(a[:3]), erste))
    merken.leeren()
    async with sitzungen() as s:
        bl = await bilanz_adapter.bewusst_leer(s, aid)
    assert bl.leer(EINSP, z + H, z + 20 * H) is sprengsatz


# ── Vorschau = Lauf (Zählerstände bis zum wirksamen ab, Tage) ──────────────


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_vorschau_zahlen_gleich_lauf(ha, datei, monkeypatch, sprengsatz):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    gleich = {"art": "ha", "entity_id": "sensor.einsp"}
    async with sitzungen() as s:
        s.add(ZuordnungWechsel(anlage_id=aid, sensor_key=EINSP, erklaert_ts=AB + timedelta(hours=1),
                               ab_ts=AB + timedelta(hours=1), vorher=None, nachher=gleich, herkunft="wechsel"))
    await _snapshots(sitzungen, aid, EINSP, [F + timedelta(hours=h) for h in range(0, (_ts(AB) - _ts(F)) // H + 2)])
    seed = await _tagzeilen_seed(sitzungen, aid)
    if sprengsatz:
        monkeypatch.setattr(kr, "wirksames_ab", lambda db, a, w0: _async(a.ab))
    a = _auftrag(aid)
    async with sitzungen() as s:
        la = await kr.lage(s, a, ha_svc=svc)
        v = kr.vorschau_daten(la)
    s_ = await _korrigieren(sitzungen, a, svc)
    async with sitzungen() as s:
        st = await kl.stand(s, s_["lauf"])
    assert v["tage_neu"] == st["tage"] == [d.isoformat() for d in seed]
    assert (v["zaehlerstaende"] == s_["zaehlerstaende_geloescht"]) is (not sprengsatz), (v["zaehlerstaende"], s_)


async def _async(wert):
    return wert


# ── Abhängige abgeleitete Kanäle (§10 Nr. 34) ──────────────────────────────


async def _invs(sitzungen, aid) -> dict[str, int]:
    async with sitzungen() as s:
        out = {}
        for typ, param in (("wallbox", None), ("e-auto", None), ("waermepumpe", None), ("speicher", None),
                           ("pv-module", None)):
            i = Investition(anlage_id=aid, typ=typ, bezeichnung=typ, parameter=param)
            s.add(i)
            await s.flush()
            out[typ] = i.id
    return out


async def test_abhaengige_abgeleitete_je_feld(datei):
    """Die Tabelle der Abhängigkeit (Bauplan §10 Nr. 34) — und welche Kanal-Schlüssel zu einer Familie gehören."""
    sitzungen, _p, aid, gas = datei
    ids = await _invs(sitzungen, aid)
    wb, ea, wp, sp, pv = (ids[t] for t in ("wallbox", "e-auto", "waermepumpe", "speicher", "pv-module"))
    erwartet = {
        "basis:einspeisung": {kk.PV_ANTEIL, kk.KOSTEN}, "basis:netzbezug": {kk.PV_ANTEIL, kk.KOSTEN},
        "basis:pv_gesamt": {kk.KOSTEN}, "basis:strompreis": {kk.KOSTEN},
        f"inv:{wb}:ladung_kwh": {kk.PV_ANTEIL}, f"inv:{ea}:ladung_pv_kwh": {kk.PV_ANTEIL},
        f"inv:{wp}:stromverbrauch_kwh": {f"{kk.MODUS_STROM}{wp}"}, f"inv:{wp}:strom_heizen_kwh": {f"{kk.MODUS_STROM}{wp}"},
        f"inv:{sp}:ladung_kwh": set(), f"inv:{pv}:pv_erzeugung_kwh": {kk.KOSTEN},
        f"inv:{wb}:ladung_pv_kwh": None, f"inv:{gas}:zaehlerstand": None, "inv:9999:ladung_kwh": None,
        "basis:gaszaehler": None, "zustand:inv:1:x": None,
    }
    async with sitzungen() as s:
        ist = {key: await kk.abhaengige_abgeleitete(s, aid, key) for key in erwartet}
    assert {k: (set(v) if v is not None else None) for k, v in ist.items()} == erwartet
    f = frozenset({kk.PV_ANTEIL, f"{kk.MODUS_STROM}{wp}"})
    assert kk.gehoert_zu(f, f"abgeleitet:inv:{wb}:ladung_pv_kwh")
    assert kk.gehoert_zu(f, f"abgeleitet:inv:{wp}:modus_strom_heizen_kwh")
    assert not kk.gehoert_zu(f, "abgeleitet:basis:kosten_netzbezug")
    assert not kk.gehoert_zu(f, f"abgeleitet:inv:{wp + 1}:modus_strom_heizen_kwh")
    assert not kk.gehoert_zu(frozenset(), f"abgeleitet:inv:{wb}:ladung_pv_kwh")
    assert kk.gehoert_zu(None, "abgeleitet:irgendwas")


async def _fremder_abgeleiteter_kanal(sitzungen, aid, wp_id) -> int:
    """Ein abgeleiteter Kanal, der NICHT von der Einspeisung abhängt (Strom je Betriebsart einer Wärmepumpe)."""
    from backend.services.kanal.modus_strom import modus_strom_key

    async with sitzungen() as s:
        kanal = Kanal(anlage_id=aid, key=modus_strom_key(wp_id, "heizen"), art=ART_SUM, einheit="kWh", aufbaubar_ab=_ts(ZEIT))
        s.add(kanal)
        await s.flush()
        s.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=_ts(ZEIT), familie=FAMILIE_ABGELEITET, statistic_id="probe", offset=0.0))
        await s.execute(insert(KanalStatistik), [
            {"kanal_id": kanal.id, "start_ts": _ts(ZEIT) + h * H, "sum": 0.1 * h, "familie": FAMILIE_ABGELEITET}
            for h in range((_ts(AB) - _ts(ZEIT)) // H + 2)])
        return kanal.id


async def _zeilen_von(sitzungen, kanal_ids) -> dict:
    async with sitzungen() as s:
        return {(r.kanal_id, r.start_ts): r.sum for r in (await s.execute(select(KanalStatistik).where(
            KanalStatistik.kanal_id.in_(list(kanal_ids))))).scalars().all()}


async def _kosten_ids(sitzungen, aid) -> list[int]:
    async with sitzungen() as s:
        return list((await s.execute(select(Kanal.id).where(and_(Kanal.anlage_id == aid,
                                                                  Kanal.key.like("abgeleitet:basis:%"))))).scalars().all())


@pytest.mark.parametrize("sprengsatz", [None, "nicht_nachgeschrieben", "alle", "nicht_verworfen"])
async def test_abhaengige_kanaele_verworfen_und_im_selben_lauf_nachgeschrieben(ha, datei, monkeypatch, sprengsatz):
    """Korrektur an der Einspeisung: die Kosten-Kanäle (abhängig) sind danach vollständig und gleich einem Neuaufbau aus dem
    korrigierten Spiegel; der Strom je Betriebsart (nicht abhängig) bleibt Zeile für Zeile, wie er war."""
    from backend.services.kanal.kosten import schreibe_kosten

    svc, reihen = ha
    sitzungen, _p, aid, _g = datei
    pv = ha_lts_helfer.sensor(svc, "sensor.pv", "kWh")
    wert = 0.0
    for h in range(40 * 24):                           # PV: die vermiedenen Kosten hängen an PV − Einspeisung
        wert += 4.0
        ha_lts_helfer.zeile(svc, pv, ZEIT + timedelta(hours=h), state=wert, sum_wert=wert)
    await _zuordnung(sitzungen, aid, pv_gesamt="sensor.pv")
    svc_, reihen_, sitzungen, aid, k = await _aba(ha, datei)
    async with sitzungen() as s:
        await schreibe_kosten(s, await _anlage(s, aid), LAUF_JETZT, ab_ts=_ts(ZEIT))
    async with sitzungen() as s:
        w = Investition(anlage_id=aid, typ="waermepumpe", bezeichnung="WP")
        s.add(w)
        await s.flush()
        wp = w.id
    fremd = await _fremder_abgeleiteter_kanal(sitzungen, aid, wp)
    kosten = await _kosten_ids(sitzungen, aid)
    fremd_vor = await _zeilen_von(sitzungen, [fremd])
    kosten_vor = await _zeilen_von(sitzungen, kosten)
    assert kosten and fremd_vor
    if sprengsatz == "nicht_nachgeschrieben":
        async def nichts(*a, **kw):
            return 0
        monkeypatch.setattr(kk, "schreibe_abgeleitete_nach", nichts)
    elif sprengsatz == "alle":
        async def alle(db, anlage_id, key):
            return None
        monkeypatch.setattr(kk, "abhaengige_abgeleitete", alle)
    elif sprengsatz == "nicht_verworfen":
        async def keins(db, anlage_id, ab_ts, *, nur=None):
            return 0
        monkeypatch.setattr("backend.services.kanal.abgeleitet.verwerfe_ab", keins)
    s_ = await _korrigieren(sitzungen, _auftrag(aid), svc)
    kosten_nach = await _zeilen_von(sitzungen, kosten)
    # Neuaufbau aus dem korrigierten Spiegel als Vergleich (alle Kosten-Zeilen weg, ab ZEIT neu)
    async with sitzungen() as s:
        await s.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(kosten)))
        await schreibe_kosten(s, await _anlage(s, aid), LAUF_JETZT, ab_ts=_ts(ZEIT))
    kosten_neu = await _zeilen_von(sitzungen, kosten)
    gleich = set(kosten_nach) == set(kosten_neu) and all(
        abs((kosten_nach[x] or 0) - (kosten_neu[x] or 0)) < 1e-9 for x in kosten_neu)
    gut = (gleich and await _zeilen_von(sitzungen, [fremd]) == fremd_vor and kosten_nach != kosten_vor
           and s_["abgeleitet_verworfen"] > 0)
    assert gut is (sprengsatz is None), (gleich, s_["abgeleitet_verworfen"], s_.get("abgeleitet_neu"))


# ── Tage neu bilden: Wetter und Börsenpreis bleiben, kein Abruf, Performance Ratio aus ihnen (§10 Nr. 32) ──


TAG = date(2026, 3, 20)                      # vor dem Kanal (Bestandstag)
STUNDE_VORHER = {h: {"temperatur_c": 5.0 + h / 10, "globalstrahlung_wm2": float(10 * h), "bewoelkung_prozent": 50.0,
                     "niederschlag_mm": 0.0 if h % 2 else None, "wetter_code": 3,
                     "boersenpreis_cent": (None if h == 5 else (-1.5 if h in (11, 12) else 8.25))} for h in range(24)}
TAG_VORHER = {"temperatur_min_c": 4.9, "temperatur_max_c": 7.4, "strahlung_summe_wh_m2": 2760.0,
              "gti_summe_wh_m2": 800.0, "boersenpreis_avg_cent": 7.0, "boersenpreis_min_cent": None,
              "negative_preis_stunden": 2}


async def _tag_mit_wetter(sitzungen, aid):
    async with sitzungen() as s:
        a = await _anlage(s, aid)
        a.latitude, a.longitude = 51.0, 7.0
        s.add(TagesZusammenfassung(anlage_id=aid, datum=TAG, komponenten_kwh={"einspeisung": 5.0}, performance_ratio=0.5,
                                   einspeisung_neg_preis_kwh=9.9, **TAG_VORHER))
        for h, w in STUNDE_VORHER.items():
            s.add(TagesEnergieProfil(anlage_id=aid, datum=TAG, stunde=h, pv_kw=1.0, einspeisung_kw=0.4, **w))


def _neubau_wie_aggregator(abrufe: dict):
    """Fake von ``_reparatur_aggregat``: holt Wetter und Preise über dieselben Helfer wie der Aggregator, schreibt die Zeilen
    neu (PV 0,5 kW in 16 Stunden = 8 kWh) — ohne Schalter mit dem, was der Abruf liefert."""
    async def neubau(anlage, tag, db):
        from backend.services import live_tagesverlauf_service
        from backend.services.energie_profil import _helpers

        # wie ``hole_tagesverlauf`` → ``get_tagesverlauf`` (Börsenpreis-Rückfall der Kurve) und ``lade_stammdaten``
        abrufe["kurve_boerse"] = await live_tagesverlauf_service._boersenpreis_ha(anlage, datetime.combine(tag, datetime.min.time()))
        wetter = await _helpers._get_wetter_ist(anlage, tag)
        preise = await _helpers._get_strompreis_stunden(anlage, {}, tag)
        await db.execute(delete(TagesEnergieProfil).where(TagesEnergieProfil.datum == tag))
        await db.execute(delete(TagesZusammenfassung).where(TagesZusammenfassung.datum == tag))
        for h in range(24):
            w = wetter.get(h, {})
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=h, pv_kw=0.5 if h < 16 else None,
                                      temperatur_c=w.get("temperatur_c"), globalstrahlung_wm2=w.get("globalstrahlung_wm2"),
                                      bewoelkung_prozent=w.get("bewoelkung_prozent"), niederschlag_mm=w.get("niederschlag_mm"),
                                      wetter_code=w.get("wetter_code"), boersenpreis_cent=preise.boerse.get(h)))
        werte = [v for v in preise.boerse.values() if v is not None]
        tz = TagesZusammenfassung(anlage_id=anlage.id, datum=tag, komponenten_kwh={"einspeisung": 6.0},
                                  temperatur_min_c=min((w["temperatur_c"] for w in wetter.values()), default=None),
                                  boersenpreis_min_cent=min(werte) if werte else None, gti_summe_wh_m2=None)
        db.add(tz)
        abrufe["boerse_gesehen"] = dict(preise.boerse)
        return tz, "lts"
    return neubau


@pytest.mark.parametrize("sprengsatz", [None, "abruf_an", "nichts_zurueck", "nur_leere_fuellen", "pr_alt"])
async def test_tage_neu_bilden_wetter_und_preis_wie_vorher_ohne_abruf(datei, monkeypatch, sprengsatz):
    from backend.services import repair_orchestrator, strompreis_markt_service
    from backend.services.energie_profil import _helpers

    sitzungen, _p, aid, _g = datei
    await _tag_mit_wetter(sitzungen, aid)
    abrufe = {"wetter": 0, "boerse": 0}

    async def wetter_abruf(anlage, url, base_params, pv_module=None, timeout=15.0, *, streng=False):
        abrufe["wetter"] += 1
        return {TAG: {h: {"temperatur_c": 99.0, "globalstrahlung_wm2": 999.0, "bewoelkung_prozent": 1.0,
                          "niederschlag_mm": 9.0, "wetter_code": 99, "gti_wm2": 50.0} for h in range(24)}}

    async def boerse_abruf(datum, markt="DE"):
        abrufe["boerse"] += 1
        return {h: -5.0 for h in range(24)}

    monkeypatch.setattr(_helpers, "_fetch_wetter", wetter_abruf)
    monkeypatch.setattr(strompreis_markt_service, "fetch_marktpreise", boerse_abruf)
    monkeypatch.setattr(repair_orchestrator, "_reparatur_aggregat", _neubau_wie_aggregator(abrufe))
    if sprengsatz in ("abruf_an", "nur_leere_fuellen"):
        monkeypatch.setattr(_helpers, "ohne_abruf", lambda boerse: nullcontext())
    if sprengsatz == "nichts_zurueck":
        async def nichts(*a, **kw):
            return 0
        monkeypatch.setattr(kl, "_wetter_und_preis_wie_vorher", nichts)
    elif sprengsatz == "nur_leere_fuellen":                # die Regel von 3a: nur was der Abruf nicht lieferte
        def nur_leere(row, alt, spalten):
            for x in spalten:
                if getattr(row, x) is None and alt.get(x) is not None:
                    setattr(row, x, alt[x])
            return 0
        monkeypatch.setattr(kl, "_wie_vorher", nur_leere)
    elif sprengsatz == "pr_alt":
        async def keine_pr(*a, **kw):
            return None
        monkeypatch.setattr(kl, "_performance_ratio", keine_pr)
    async with sitzungen() as s:
        await kl.anlegen(s, "wetter", aid, EINSP, [TAG])
    z = await kl.tage_neu_bilden(sitzungen, "wetter")
    async with sitzungen() as s:
        tz = (await s.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.datum == TAG))).scalar_one()
        std = {r.stunde: {x: getattr(r, x) for x in kl.STUNDE_ABRUF} for r in (await s.execute(
            select(TagesEnergieProfil).where(TagesEnergieProfil.datum == TAG))).scalars().all()}
    assert z["status"] == kl.FERTIG and not z["fehler"] and tz.komponenten_kwh == {"einspeisung": 6.0}
    kein_abruf = abrufe["wetter"] == 0 and abrufe["boerse"] == 0
    wie_vorher = std == STUNDE_VORHER and {x: getattr(tz, x) for x in kl.TAG_ABRUF} == TAG_VORHER
    pr_neu = tz.performance_ratio is not None and abs(tz.performance_ratio - 8.0 / (800.0 * 10.0 / 1000)) < 1e-9
    erwartet = {None: (True, True, True), "abruf_an": (False, True, True), "nichts_zurueck": (True, False, False),
                "nur_leere_fuellen": (False, False, True), "pr_alt": (True, True, False)}[sprengsatz]
    assert (kein_abruf, wie_vorher, pr_neu) == erwartet, (abrufe, tz.performance_ratio)
    if sprengsatz is None:
        # der Aggregator sah die gespeicherten Börsenpreise der Stunden (für die Einspeisung bei negativem Preis)
        gespeichert = {h: w["boersenpreis_cent"] for h, w in STUNDE_VORHER.items() if w["boersenpreis_cent"] is not None}
        assert abrufe["boerse_gesehen"] == gespeichert and abrufe["kurve_boerse"] == gespeichert


async def test_ohne_abruf_gilt_nur_im_block(datei):
    """Der Schalter gilt nur im Block (Normalbetrieb unverändert) — danach ruft der Helfer wieder ab."""
    from backend.services.energie_profil import _helpers

    with _helpers.ohne_abruf({TAG: {3: 1.5}}):
        assert _helpers._GESPEICHERTE_BOERSE.get() == {TAG: {3: 1.5}}
    assert _helpers._GESPEICHERTE_BOERSE.get() is None


# ── Wortlaute der Vorschau mit und ohne Home Assistant (§10 Nr. 37) ────────


def _lage(mit_ha: bool, tage=(), abschluss=frozenset(), abschluss_tage=(), staende=3, nicht=None) -> kr.Lage:
    b = vq.BestandZaehlung(abschluss_tage=set(abschluss_tage))
    return kr.Lage(auftrag=None, label="", kanal=None, zaehlerstaende=staende, rohstaende=0, bestand=b, ziele=None,
                   abschluss=frozenset(abschluss), tage_neu=list(tage), mit_ha=mit_ha, nicht_startbar=nicht)


def test_saetze_mit_und_ohne_home_assistant():
    monate = frozenset((2024, 11 + i) if i < 2 else (2025, i - 1) for i in range(8))
    tage = [date(2024, 11, 3), date(2025, 6, 1)]
    mit = kr.saetze(_lage(True, tage=tage, abschluss=monate))
    assert mit == [
        "Zählerstände dieses Felds im Zeitraum werden verworfen (3).",
        "2 Tage werden im Hintergrund neu gebildet: alle Zähler dieser Tage werden neu aus Home Assistant gelesen; "
        "Wetter und Börsenpreis bleiben.",
        "Bei älteren Tagen kommt die Leistung je Stunde danach aus der Langzeitstatistik von Home Assistant (Stundenmittel), "
        "nicht mehr aus dem damaligen Verlauf.",
        "Abgeschlossene Monate 11/2024, 06/2025: die gespeicherten Monatswerte bleiben aus dem bisherigen Sensor; was eedc "
        "im Monat aus den Tagen rechnet, folgt den neu gebildeten Tagen.",
        "Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung von Home Assistant.",
    ]
    ohne = kr.saetze(_lage(False, abschluss=monate, abschluss_tage=[date(2024, 11 + i, 2) for i in range(2)]
                           + [date(2025, m, 2) for m in range(1, 7)]))
    assert ohne == [
        "Zählerstände dieses Felds im Zeitraum werden verworfen (3).",
        "Ohne Home Assistant werden die Werte nur verworfen — kein Tag wird neu gebildet.",
        "Abgeschlossene Monate 11/2024 bis 06/2025: die gespeicherten Monatswerte bleiben aus dem bisherigen Sensor.",
        "Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung der eedc-Datenbank.",
    ]
    assert kr.saetze(_lage(True, staende=0)) == [
        "Kein Tag muss neu gebildet werden; der Wert dieses Felds kommt danach aus dem richtigen Sensor.",
        "Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung von Home Assistant.",
    ]
    assert kr.saetze(_lage(False, nicht="x")) == ["x"]
    assert not [x for x in mit + ohne if "abgerufen" in x or "…" in x]


async def test_werkbank_vorschau_mit_home_assistant_ohne_saetze_vom_stehenbleiben(ha, datei, monkeypatch):
    from backend.services.kanal.verwerfen import text_aus_zeitpunkt

    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: False)
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _tagzeilen_seed(sitzungen, aid)
    params = {"kanal": EINSP, "zeitpunkt": text_aus_zeitpunkt((await _quellen(sitzungen, k.id))[-1].gueltig_ab)}
    async with sitzungen() as s:
        _g, mit, _v = await vq.plan_vorschau(s, aid, params, ha_svc=svc)
        _g, ohne, _v = await vq.plan_vorschau(s, aid, params, ha_svc=None)
    text_mit, text_ohne = " ".join(mit), " ".join(ohne)
    for falsch in ("bleiben im Bestand unberührt", "Wetter, Prognose, Preise", "Quellen bleiben als Herkunft",
                   "Kein Rückweg", "aus den gespeicherten Zählerständen zurück", "Sicherung der eedc-Datenbank"):
        assert falsch not in text_mit, falsch
    assert "Tage werden im Hintergrund neu gebildet" in text_mit and "Sicherung von Home Assistant" in text_mit
    assert "Wo Home Assistant für den jüngsten Sensor keine Geschichte führt" in text_mit
    for falsch in ("neu gebildet:", "Sicherung von Home Assistant", "aus den gespeicherten Zählerständen zurück"):
        assert falsch not in text_ohne, falsch
    assert "Sicherung der eedc-Datenbank" in text_ohne and "Quellen bleiben als Herkunft" in text_ohne
