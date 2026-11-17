"""Sensorwechsel mit Grund, Sitzung 2 — B-5 «Kanal vor Reihe, feldweise» (Bauplan Fassung 2 §2 B-5, §7 Nr. 11/12).

**Regel:** je (Gerät, Feld, Innengerät-Kopie) gilt das Δ des eigenen Kanals über das Fenster, in dem die Reihe an diesem Tag
gelesen würde (``tagesfenster_fuer`` mit denselben Argumenten), wenn der Kanal es voll trägt; sonst die Reihe. Gemischt je
Gerät und Feld, die Summe des Ausgabe-Schlüssels danach. Dieselbe Feld-Auskunft trägt die Wirkungs-Prüfung des Befunds
``zaehler_versatz``; «Kanal zuerst» gilt auch für die Speicher-Netzladung der Monats-Fakten (``netzladung_tage.py``).

Proben mit Sprengsatz im selben Test: zwei Geräte ⇒ Summe beider (Sprengsatz: die Ausgabe-Summe aus den Kanälen allein —
``detail_aus_kanaelen`` — verliert das Gerät ohne Kanal) · fremder Abschnitt der Reihe ⇒ Kanal (Sprengsatz: Feld-Auskunft
leer ⇒ die Reihe) · Ladung 23–24 Uhr an einem Bestandstag ohne Bilanz-Kanal ⇒ bleibt beim Folgetag (Sprengsatz: Kalendertag) ·
Kanal nicht voll ⇒ Reihe · Netzladung mit Naht ⇒ Kanal (Sprengsatz ohne ``kanal_zuerst``) · ``zaehler_versatz`` schweigt, wo
der Kanal die Rand-Tage trägt (Sprengsatz: Feld-Auskunft leer ⇒ Befund). Zeiten im Juni (auch ``TZ=Pacific/Auckland``/``UTC``).
Korrekturrunde (Bauplan §9 Nr. 24, K-3): die Abdeckungs-Marke folgt der Quelle des Werts (HA-Lücke über dem Fensterende, ein
Stand je Tag; Sprengsatz «Marke nur aus Reihen-Feldern») · nur Mengen-Kanäle · Kanal erst nach der Zuordnungs-Prüfung · das
Fenster der Versatz-Wirkung (Typ, Tageszeile rückwärts, Kanal-Tag) — je mit Gegenprobe.

Schwesterdateien: test_sensorwechsel_s2_naht.py (B-3, B-4), test_reihen_leser_waechter.py, test_daten_checker_zaehler_versatz.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.tests.test_daten_checker_zaehler_versatz import JETZT, _pruefe, ha  # noqa: F401 — Fixture ``ha``
from backend.tests.test_daten_checker_zaehler_versatz import _anlage as _versatz_anlage

D = date(2026, 6, 10)
TAG0 = datetime(2026, 6, 10, 0)
VON, BIS = TAG0 - timedelta(days=3), TAG0 + timedelta(days=3)
FREMD_AB = TAG0 + timedelta(hours=12)              # fremder Abschnitt der Reihe von Gerät 2: +100 kWh
FREMD = 100.0


def _stunden(von: datetime, bis: datetime) -> list[datetime]:
    out, t = [], von
    while t <= bis:
        out.append(t)
        t += timedelta(hours=1)
    return out


def _stand(t: datetime, je_h: float, basis: float = 500.0) -> float:
    return round(basis + (t - VON).total_seconds() / 3600 * je_h, 6)


async def _anlage(db, geraete: dict[int, str], feld: str = "ladung_pv_kwh") -> Anlage:
    a = Anlage(anlagenname="Kanal vor Reihe", leistung_kwp=10.0, sensor_mapping={"investitionen": {
        str(i): {"felder": {feld: {"strategie": "sensor", "sensor_id": f"sensor.{feld}_{i}"}}} for i in geraete}})
    db.add(a)
    await db.flush()
    for i, typ in geraete.items():
        db.add(Investition(id=i, anlage_id=a.id, typ=typ, bezeichnung=f"G{i}", anschaffungsdatum=date(2025, 1, 1)))
    await db.flush()
    return a


async def _reihe(db, aid: int, key: str, stand) -> None:
    db.add_all([SensorSnapshot(anlage_id=aid, sensor_key=key, zeitpunkt=t, wert_kwh=stand(t), quelle="ha_statistics")
                for t in _stunden(VON, BIS)])
    await db.flush()


async def _kanal(db, aid: int, key: str, stand, *, bis: datetime = BIS) -> None:
    """Spiegel: Zeile ``start_ts = H`` trägt den Stand am Ende der Stunde (H + 1 h)."""
    k = Kanal(anlage_id=aid, key=key, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    ab = int((VON - timedelta(hours=1)).timestamp())
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie=FAMILIE_SPIEGEL, statistic_id=key, offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=int((t - timedelta(hours=1)).timestamp()), sum=stand(t),
                               state=stand(t), familie=FAMILIE_SPIEGEL) for t in _stunden(VON, bis)])
    await db.flush()


async def _detail(db, a, datum: date = D):
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    invs = {str(i.id): i for i in (await db.execute(
        __import__("sqlalchemy").select(Investition).where(Investition.anlage_id == a.id))).scalars()}
    return await get_tagesdetail_kwh(db, a, invs, datum, tageszeile_rueckwaerts=True), invs


def _feld_leer(monkeypatch):
    """Sprengsatz: die Feld-Auskunft antwortet nie (= Gruppen-Regel wie vor B-5, die Reihe gilt)."""
    import backend.services.kanal.feld_leser as fl

    async def nichts(*_a, **_k):
        return {}
    monkeypatch.setattr(fl, "kanal_feldwerte", nichts)
    monkeypatch.setattr(fl, "kanal_feldzeitraeume", nichts)
    monkeypatch.setattr(fl, "kanal_feldwerte_je_fenster", nichts)


async def test_zwei_geraete_summe_beider_und_fremder_abschnitt(db, monkeypatch):
    from backend.services.energie_profil.kanal_stunden import detail_aus_kanaelen

    a = await _anlage(db, {2: "wallbox", 3: "wallbox"})
    richtig = lambda t: _stand(t, 1.0)                                            # noqa: E731
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", lambda t: richtig(t) + (FREMD if t >= FREMD_AB else 0.0))
    await _kanal(db, a.id, "inv:2:ladung_pv_kwh", richtig)
    await _reihe(db, a.id, "inv:3:ladung_pv_kwh", lambda t: _stand(t, 2.0))      # Gerät 3 ohne Kanal
    det, invs = await _detail(db, a)
    assert det.werte_je_inv["emob_ladung_pv_kwh"] == {"2": pytest.approx(24.0), "3": pytest.approx(48.0)}
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(72.0)
    # Sprengsatz 1: die Ausgabe-Summe nur aus den Kanälen (die Form von `detail_aus_kanaelen`) verliert Gerät 3
    nur_kanal = detail_aus_kanaelen(det, {"inv:2:ladung_pv_kwh": 24.0}, invs, D, frozenset({"wallbox"}), False)
    assert nur_kanal.werte["emob_ladung_pv_kwh"] == pytest.approx(24.0)
    # Sprengsatz 2: ohne Feld-Auskunft liest Gerät 2 die Reihe mit dem fremden Abschnitt
    _feld_leer(monkeypatch)
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(24.0 + FREMD + 48.0)


async def test_ladung_23_bis_24_uhr_bleibt_im_fenster_der_reihe(db):
    """Bestandstag ohne Bilanz-Kanal (§7 Nr. 11): das Fenster der Wallbox ist rückwärts [Vortag 23:00, 23:00) — eine
    Ladung 23–24 Uhr gehört zum Folgetag, im Kanal wie in der Reihe."""
    from backend.services.kanal.feld_leser import kanal_feldwerte

    nacht = TAG0 + timedelta(days=1)                                            # Stand nach der Ladung 23–24 Uhr

    def stand(t):
        return _stand(t, 0.0) + (5.0 if t >= nacht else 0.0)
    a = await _anlage(db, {2: "wallbox"})
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", stand)
    await _kanal(db, a.id, "inv:2:ladung_pv_kwh", stand)
    tag, _ = await _detail(db, a, D)
    folgetag, _ = await _detail(db, a, D + timedelta(days=1))
    assert (tag.werte["emob_ladung_pv_kwh"], folgetag.werte["emob_ladung_pv_kwh"]) == (pytest.approx(0.0), pytest.approx(5.0))
    # Sprengsatz: über den Kalendertag gelesen, wanderte die Ladung auf den Tag davor
    kalender = await kanal_feldwerte(db, a.id, ["inv:2:ladung_pv_kwh"], TAG0, TAG0 + timedelta(days=1))
    assert kalender["inv:2:ladung_pv_kwh"] == pytest.approx(5.0)


async def test_kanal_nicht_voll_dann_die_reihe(db):
    a = await _anlage(db, {2: "wallbox"})
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", lambda t: _stand(t, 1.0) + (FREMD if t >= FREMD_AB else 0.0))
    await _kanal(db, a.id, "inv:2:ladung_pv_kwh", lambda t: _stand(t, 1.0), bis=TAG0 + timedelta(hours=20))
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(24.0 + FREMD)        # Kanal endet vor dem Fenster-Ende


async def test_innengeraet_kopie_je_kopie(db, monkeypatch):
    """Je Innengerät-Kopie entscheidet die Feld-Auskunft für sich: Kopie -1 aus dem Kanal, Kopie -2 aus der Reihe."""
    a = await _anlage(db, {2: "waermepumpe"}, feld="betriebsart_nutzenergie_kuehlen_kwh-1")
    m = dict(a.sensor_mapping)
    m["investitionen"]["2"]["felder"]["betriebsart_nutzenergie_kuehlen_kwh-2"] = {"strategie": "sensor", "sensor_id": "s.k2"}
    a.sensor_mapping = m
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(a, "sensor_mapping")
    k1, k2 = "inv:2:betriebsart_nutzenergie_kuehlen_kwh-1", "inv:2:betriebsart_nutzenergie_kuehlen_kwh-2"
    await _reihe(db, a.id, k1, lambda t: _stand(t, 1.0) + (FREMD if t >= FREMD_AB else 0.0))
    await _kanal(db, a.id, k1, lambda t: _stand(t, 1.0))
    await _reihe(db, a.id, k2, lambda t: _stand(t, 0.5))
    det, _ = await _detail(db, a)
    assert det.felder_je_inv["wp_kaelte_kwh"]["2"] == {
        "betriebsart_nutzenergie_kuehlen_kwh-1": pytest.approx(24.0), "betriebsart_nutzenergie_kuehlen_kwh-2": pytest.approx(12.0)}
    _feld_leer(monkeypatch)
    det, _ = await _detail(db, a)
    assert det.werte["wp_kaelte_kwh"] == pytest.approx(24.0 + FREMD + 12.0)


async def test_netzladung_monats_fakten_kanal_zuerst(db, monkeypatch):
    """§7 Nr. 12: eine Naht in der Reihe der Speicher-Netzladung (+50 kWh über einen Tag) zählt mit «Kanal zuerst» nicht."""
    from backend.services.monats_fakten.netzladung_tage import speicher_netzladung_aus_tagen

    a = await _anlage(db, {5: "speicher"}, feld="ladung_netz_kwh")
    key = "inv:5:ladung_netz_kwh"
    global VON, BIS
    von, bis = VON, BIS
    VON, BIS = datetime(2026, 5, 31, 22), datetime(2026, 7, 1, 1)
    try:
        sprung = (datetime(2026, 6, 5, 12), datetime(2026, 6, 6, 11))
        await _reihe(db, a.id, key, lambda t: _stand(t, 0.1) + (50.0 if sprung[0] <= t < sprung[1] else 0.0))
        await _kanal(db, a.id, key, lambda t: _stand(t, 0.1))
    finally:
        VON, BIS = von, bis
    speicher = [await db.get(Investition, 5)]
    assert await speicher_netzladung_aus_tagen(db, a, speicher, 2026, 6, date(2026, 6, 30)) == pytest.approx(29 * 2.4)
    _feld_leer(monkeypatch)
    assert await speicher_netzladung_aus_tagen(db, a, speicher, 2026, 6, date(2026, 6, 30)) == pytest.approx(
        29 * 2.4 + 50.0 - 2.4)                                                   # 5.6. +50, 6.6. «zurückgesprungen» fehlt


async def test_versatz_schweigt_wo_der_eigene_kanal_den_tag_traegt(db, ha, monkeypatch):  # noqa: F811
    """Die Wirkungs-Prüfung des Befunds läuft auf dieselbe Feld-Auskunft: der Spiegel der Probe trägt die Rand-Tage ⇒ die
    Tagesansicht zeigt dort den Kanal ⇒ kein Befund. Sprengsatz: ohne Feld-Auskunft der Befund wie vor B-5."""
    import backend.services.energie_profil.kanal_stunden as ks

    async def keine_gruppe(*_a):
        return frozenset()                    # die E-Mob-Gruppe liest an den Rand-Tagen die Reihe (Gruppe «bestand»)
    monkeypatch.setattr(ks, "kanal_schluessel_des_tages", keine_gruppe)
    a, *_ = await _versatz_anlage(db)
    assert await _pruefe(db, a) == []
    _feld_leer(monkeypatch)
    assert [e.code for e in await _pruefe(db, a)] == ["zaehler_versatz"]


# ═══ Bauplan §9 Nr. 24: die Abdeckungs-Marke folgt der Quelle des Werts ═════════════════════════════════════════════

async def _reihe_staende(db, aid: int, key: str, staende: dict[datetime, float]) -> None:
    db.add_all([SensorSnapshot(anlage_id=aid, sensor_key=key, zeitpunkt=t, wert_kwh=w, quelle="ha_statistics")
                for t, w in staende.items()])
    await db.flush()


async def _kanal_staende(db, aid: int, key: str, staende: dict[datetime, float]) -> None:
    """Spiegel aus Ständen: je Stand ``t`` die Zeile ``start_ts = t − 1 h`` (sie trägt den Stand am Ende der Stunde)."""
    k = Kanal(anlage_id=aid, key=key, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int((min(staende) - timedelta(hours=1)).timestamp()),
                       familie=FAMILIE_SPIEGEL, statistic_id=key, offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=int((t - timedelta(hours=1)).timestamp()), sum=w, state=w,
                               familie=FAMILIE_SPIEGEL) for t, w in staende.items()])
    await db.flush()


def _marke_nur_aus_der_reihe(monkeypatch):
    """Sprengsatz: die Marke entsteht nur aus Feldern, die die Reihe lesen (Stand des Baus vor der Korrekturrunde)."""
    import backend.services.snapshot.aggregator as ag

    monkeypatch.setattr(ag, "_kanal_rand_menge", lambda z: ag.TagesRandMenge(
        wert_kwh=z.delta, seit=datetime.fromtimestamp(z.von), bis=datetime.fromtimestamp(z.bis),
        ab_tagesbeginn=True, bis_tagesende=True))


async def test_marke_folgt_dem_kanal_ha_luecke_ueber_dem_fensterende(db, monkeypatch):
    """Stundenstände, HA-Lücke 20 Uhr – Folgetag 02 Uhr in Reihe und Kanal: der Kanal ist «voll» (Spanne 7 h ≤ Fenster),
    trägt das Fenster [Vortag 23:00, 23:00) aber nur bis 19:00 — Wert 20,0 kWh mit ``abdeckung_bis`` 19:00 wie die Reihe."""
    a = await _anlage(db, {2: "wallbox"})
    key = "inv:2:ladung_pv_kwh"
    luecke = (TAG0 + timedelta(hours=19), TAG0 + timedelta(days=1, hours=2))
    staende = {t: _stand(t, 1.0) for t in _stunden(VON, BIS) if not luecke[0] < t < luecke[1]}
    await _reihe_staende(db, a.id, key, staende)
    await _kanal_staende(db, a.id, key, staende)
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(20.0)
    assert (det.abdeckung_von, det.abdeckung_bis) == (None, TAG0 + timedelta(hours=19))
    # die Reihe sagt dasselbe (Feld-Auskunft leer ⇒ Reihe)
    with monkeypatch.context() as m:
        _feld_leer(m)
        reihe, _ = await _detail(db, a)
    assert (reihe.werte["emob_ladung_pv_kwh"], reihe.abdeckung_bis) == (pytest.approx(20.0), TAG0 + timedelta(hours=19))
    # Sprengsatz: die Marke nur aus Reihen-Feldern ⇒ der Kanal-Wert steht ohne Marke
    _marke_nur_aus_der_reihe(monkeypatch)
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(20.0) and det.abdeckung_bis is None


async def test_marke_folgt_dem_kanal_ein_stand_je_tag(db, monkeypatch):
    """Die Fenster-Tage von ``kanal.db`` (S0 M-E): ein Stand je Tag (00:00) in Reihe und Kanal — Kanal «voll» (24 h ≤ 24 h),
    der Wert reicht bis 00:00 ⇒ «gemessen bis 00:00 Uhr» wie die Reihe (vor B-5)."""
    a = await _anlage(db, {2: "wallbox"})
    key = "inv:2:ladung_pv_kwh"
    staende = {TAG0 + timedelta(days=i): _stand(TAG0 + timedelta(days=i), 1.0) for i in (-2, -1, 0, 1, 2)}
    await _reihe_staende(db, a.id, key, staende)
    await _kanal_staende(db, a.id, key, staende)
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(24.0)
    assert (det.abdeckung_von, det.abdeckung_bis) == (None, TAG0)
    with monkeypatch.context() as m:
        _feld_leer(m)
        reihe, _ = await _detail(db, a)
    assert (reihe.werte["emob_ladung_pv_kwh"], reihe.abdeckung_bis) == (pytest.approx(24.0), TAG0)
    _marke_nur_aus_der_reihe(monkeypatch)
    assert (await _detail(db, a))[0].abdeckung_bis is None


async def test_marke_gegenprobe_kanal_traegt_bis_zum_fensterende(db):
    """Gegenprobe: trägt der Kanal das Fenster bis zum Ende, entsteht keine Marke — obwohl die Reihe dort eine Lücke hat
    (dann stünde an der Reihe «gemessen bis 19:00»)."""
    a = await _anlage(db, {2: "wallbox"})
    key = "inv:2:ladung_pv_kwh"
    alle = {t: _stand(t, 1.0) for t in _stunden(VON, BIS)}
    await _reihe_staende(db, a.id, key, {t: w for t, w in alle.items() if not TAG0 + timedelta(hours=19) < t < BIS})
    await _kanal_staende(db, a.id, key, alle)
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(24.0)
    assert (det.abdeckung_von, det.abdeckung_bis) == (None, None)


# ═══ K-3, B-5: Kanal-Art, Zuordnung zuerst, das Fenster der Versatz-Wirkung ═══════════════════════════════════════

async def test_feld_auskunft_nur_mengen_kanaele(db):
    """Ein Stand-Kanal (Art ``stand``, HA-Spalte ``state``) ist keine Menge — die Feld-Auskunft antwortet nicht, der Leser
    bleibt bei der Reihe. Gegenprobe: derselbe Kanal als Mengen-Kanal antwortet."""
    from backend.models.kanal import ART_STAND
    from backend.services.kanal.feld_leser import kanal_feldwerte

    a = await _anlage(db, {2: "wallbox"})
    key = "inv:2:ladung_pv_kwh"
    await _kanal(db, a.id, key, lambda t: _stand(t, 1.0))
    k = (await db.execute(__import__("sqlalchemy").select(Kanal).where(Kanal.key == key))).scalar_one()
    assert (await kanal_feldwerte(db, a.id, [key], TAG0, TAG0 + timedelta(days=1)))[key] == pytest.approx(24.0)
    k.art = ART_STAND
    await db.flush()
    assert await kanal_feldwerte(db, a.id, [key], TAG0, TAG0 + timedelta(days=1)) == {}


async def test_kanal_erst_nach_der_zuordnungs_pruefung(db):
    """Ein Feld ohne Zuordnung bleibt «nicht zugeordnet», auch wenn ein Kanal mit seinem Schlüssel Zeilen trägt (z. B. nach
    dem Lösen der Zuordnung). Gegenprobe: zugeordnet ⇒ der Kanal-Wert steht."""
    from backend.core.tageswert_grund import GRUND_NICHT_ZUGEORDNET
    from sqlalchemy.orm.attributes import flag_modified

    a = await _anlage(db, {2: "wallbox"}, feld="ladung_netz_kwh")
    await _kanal(db, a.id, "inv:2:ladung_pv_kwh", lambda t: _stand(t, 1.0))
    det, _ = await _detail(db, a)
    assert "emob_ladung_pv_kwh" not in det.werte
    assert det.grund_je_feld["emob_ladung_pv_kwh"] == GRUND_NICHT_ZUGEORDNET
    m = dict(a.sensor_mapping)
    m["investitionen"]["2"]["felder"]["ladung_pv_kwh"] = {"strategie": "sensor", "sensor_id": "sensor.pv"}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    det, _ = await _detail(db, a)
    assert det.werte["emob_ladung_pv_kwh"] == pytest.approx(24.0)


async def _kanal_ab_mitternacht(db, typ: str):
    """Kanal ab der Zeile 23:00 des Vortags (Stand 00:00): trägt den Kalendertag D, nicht das Rückwärtsfenster
    [Vortag 23:00, 23:00) — die Probe unterscheidet die beiden Fenster."""
    a = await _anlage(db, {2: typ}, feld="stromverbrauch_kwh" if typ == "waermepumpe" else "ladung_pv_kwh")
    key = f"inv:2:{'stromverbrauch_kwh' if typ == 'waermepumpe' else 'ladung_pv_kwh'}"
    await _kanal_staende(db, a.id, key, {t: _stand(t, 1.0) for t in _stunden(TAG0, BIS)})
    return a, key


def _bestandstag(monkeypatch):
    import backend.services.kanal.bilanz_leser as bl

    async def keine(*_a, **_k):
        return {}
    monkeypatch.setattr(bl, "kanal_tage", keine)


async def test_versatz_fenster_typ_entscheidet(db, monkeypatch):
    """Wallbox am Bestandstag: Fenster rückwärts ⇒ der Kanal (ab 00:00) trägt es nicht. Gegenprobe im selben Test: ohne Typ
    (Kalendertag) trüge er es — ein Fenster ohne den Typ des Geräts gäbe die falsche Antwort."""
    from backend.services.kanal.feld_leser import feld_aus_kanal_am_tag

    _bestandstag(monkeypatch)
    a, key = await _kanal_ab_mitternacht(db, "wallbox")
    assert await feld_aus_kanal_am_tag(db, a, "wallbox", key, D) is False
    assert await feld_aus_kanal_am_tag(db, a, None, key, D) is True


async def test_versatz_fenster_tageszeile_rueckwaerts(db, monkeypatch):
    """Wärmepumpe (Fenster «bedingt»): trägt die Tageszeile die Regelmarke, liest der Tag rückwärts ⇒ der Kanal ab 00:00 trägt
    ihn nicht. Gegenprobe: ohne Tageszeile (Kalendertag) trägt er ihn."""
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services.kanal.feld_leser import feld_aus_kanal_am_tag

    _bestandstag(monkeypatch)
    a, key = await _kanal_ab_mitternacht(db, "waermepumpe")
    assert await feld_aus_kanal_am_tag(db, a, "waermepumpe", key, D) is True
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D, verworfen={}))
    await db.flush()
    assert await feld_aus_kanal_am_tag(db, a, "waermepumpe", key, D) is False


async def test_versatz_fenster_kanal_tag(db, monkeypatch):
    """An einem Kanal-Tag der Bilanz liest jeder Typ den Kalendertag ⇒ der Kanal ab 00:00 trägt den Tag der Wallbox.
    Gegenprobe: derselbe Tag als Bestandstag ⇒ rückwärts ⇒ nicht."""
    import backend.services.kanal.bilanz_leser as bl
    from backend.services.kanal.feld_leser import feld_aus_kanal_am_tag

    a, key = await _kanal_ab_mitternacht(db, "wallbox")
    with monkeypatch.context() as m:
        _bestandstag(m)
        assert await feld_aus_kanal_am_tag(db, a, "wallbox", key, D) is False

    async def kanal_tag(_db, _aid, von, bis, **_k):
        return {D: object()} if von <= D <= bis else {}
    monkeypatch.setattr(bl, "kanal_tage", kanal_tag)
    assert await feld_aus_kanal_am_tag(db, a, "wallbox", key, D) is True


async def test_bereichs_leser_kanal_nur_bei_echter_deckung(db, monkeypatch):
    """Entscheid H-K4 (a): der Bereichs-Leser kann keine Marke tragen — er nimmt den Kanal nur, wenn er das Fenster vom Beginn bis
    zum Ende deckt. Ein Stand je Tag (00:00) in Reihe und Kanal, Fenster rückwärts [Vortag 23:00, 23:00): der Kanal ist «voll»,
    deckt aber nur bis 00:00 ⇒ die Reihe gilt (ohne Rand-Rückfall: kein Wert). Sprengsatz: Kanal schon bei ``voll`` ⇒ die
    Vortagsmenge 24,0 ohne Hinweis. Gegenprobe: stündlicher Kanal (deckt) ⇒ Kanal-Wert."""
    import backend.services.kanal.feld_leser as fl
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld

    felder = {("speicher", "ladung_netz_kwh"): TAGESDETAIL_AUSGABE[("speicher", "ladung_netz_kwh")]}
    out = felder[("speicher", "ladung_netz_kwh")]

    async def tag(a):
        invs = {"5": await db.get(Investition, 5)}
        return (await lade_tageswerte_je_feld(db, a, invs, D, D, felder, rueckwaerts_tage={D}, kanal_zuerst=True)).get(D, {})

    a = await _anlage(db, {5: "speicher"}, feld="ladung_netz_kwh")
    staende = {TAG0 + timedelta(days=i): _stand(TAG0 + timedelta(days=i), 1.0) for i in (-2, -1, 0, 1, 2)}
    await _reihe_staende(db, a.id, "inv:5:ladung_netz_kwh", staende)
    await _kanal_staende(db, a.id, "inv:5:ladung_netz_kwh", staende)
    assert out not in await tag(a)
    with monkeypatch.context() as m:
        m.setattr(fl, "_deckt", lambda z: z.voll and z.delta is not None)          # Sprengsatz: «voll» genügt
        assert (await tag(a))[out] == pytest.approx(24.0)
    b = await _anlage(db, {6: "speicher"}, feld="ladung_netz_kwh")
    await _kanal(db, b.id, "inv:6:ladung_netz_kwh", lambda t: _stand(t, 0.1))
    invs = {"6": await db.get(Investition, 6)}
    w = await lade_tageswerte_je_feld(db, b, invs, D, D, felder, rueckwaerts_tage={D}, kanal_zuerst=True)
    assert w[D][out] == pytest.approx(2.4)
