"""Sensorwechsel U2 a2 «Ansetzen» (Rechenweg ``opus-berichte/SENSORWECHSEL-U2-RECHENWEG-2026-11-19.md`` F2, F3, F4, F10, F11;
Bauplan Nr. 138, 139, 143, 144). Proben mit Sprengsatz — **über die Routen und den Stundenlauf**, nicht von Hand gesetzt.

**Welt.** Die Lab-Zeilen der a1-Proben (``test_sensorwechsel_u2a1_proben.Lab``: alter Zähler 1 kWh/h, die Stunde vor dem Tausch
ohne Zuwachs, in der Tausch-Stunde +0,6; neuer Zähler erste Zeile 0,7, danach 0,5 kWh/h). Home Assistant (Attrappe) führt eine
Zeile erst, wenn ihre Stunde vorbei ist (``_ha_bis``); eedc läuft je Stunde wie der Lauf «:05» (Reihe, Kanal, danach
``ansatz.offene_ansetzen``), nach Mitternacht der Tagesabschluss. Die Umstellung geht über die Feld-Route mit Grund
«Fortsetzung» (die Uhr der Abfrage auf die Umstellzeit gestellt). Lab-Soll: Stunde 1,3 · Tag 15,3 · Folgetage 12,0 — in
jeder Sicht, bei Umstellung 07:40, 08:20, 10:30 und zwei Tage später.

Schwesterdateien: test_sensorwechsel_u2a1_proben.py (die Leser mit von Hand gesetzten Zeilen), test_sensorwechsel_s4_nachtrag.py
(«Grund nachtragen»), test_sensorwechsel_s3_korrektur.py (der Dienst, dessen Lauf das Ansetzen mitbenutzt).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests.test_sensorwechsel_u2a1_proben import ALT, NEU, Lab, _im_slot, _im_tag

STUNDE = 3600
KEY, FID = "inv:2:ladung_kwh", "inv_energy_2_ladung_kwh"
T1 = datetime(2026, 11, 10, 7)          # die Tausch-Stunde (vergangen, damit keine Sicht die Uhr des Laufs liest)


def _ep(t: datetime) -> int:
    return int(time.mktime(t.timetuple()))


class Welt:
    def __init__(self, db, lab: Lab, svc, a, mids):
        self.db, self.lab, self.svc, self.a, self.mids = db, lab, svc, a, mids
        self.bis = -1                      # HA führt Zeilen mit start_ts ≤ bis

    @property
    def sitzungen(self):
        from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie

        return sitzungen_wie(self.db, None)


async def _welt(db, monkeypatch, lab: Lab, *, alt_entfernt: bool = False) -> Welt:
    """Anlage mit Wallbox (``ladung_kwh`` heute ``sensor.alt``), HA-Attrappe mit beiden Statistiken (Zeilen erst nach ihrer
    Stunde), kein Kanal, keine Reihe — die schreibt der Betrieb."""
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.korrektur as kr
    from backend.services.live_power_service import LivePowerService
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    mids = {ALT: H.sensor(svc, ALT, "kWh", has_sum=True), NEU: H.sensor(svc, NEU, "kWh", has_sum=True)}
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)

    async def kurve(self, anlage, db_, tage_zurueck=0, **_k):
        return {"serien": [], "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)],
                "vortagsrand": [{"zeit": "23:00", "werte": {}}]}
    monkeypatch.setattr(LivePowerService, "get_tagesverlauf", kurve)
    if alt_entfernt:                                  # die Entität verschwindet in der Tausch-Stunde (Lab M1): keine Zeile danach
        lab.alt = {e: v for e, v in lab.alt.items() if e <= lab.e1}
    a = Anlage(anlagenname="Lab", leistung_kwp=10.0, sensor_mapping={
        "basis": {"live": {"netzbezug_w": "sensor.netz_w"}},
        "investitionen": {"2": {"felder": {f: {"strategie": "sensor", "sensor_id": ALT} for f in ("ladung_kwh", "ladung_pv_kwh")}}}})
    db.add(a)
    await db.flush()
    db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2025, 1, 1)))
    await db.commit()
    return Welt(db, lab, svc, a, mids)


def _ha_bis(w: Welt, bis: int) -> None:
    """HA führt die Zeilen beider Sensoren mit ``start_ts ≤ bis``."""
    if bis <= w.bis:
        return
    zeilen = [{"m": w.mids[eid], "t": e, "s": s} for eid, reihe in ((ALT, w.lab.alt), (NEU, w.lab.neu))
              for e, (_z, s) in reihe.items() if w.bis < e <= bis]
    if zeilen:
        with w.svc._engine.begin() as c:
            c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"), zeilen)
    w.bis = bis


async def _umstellen(w: Welt, U: datetime, monkeypatch, *, grund: str = "fortsetzung", falsch_seit=None):
    import backend.services.zuordnung_wechsel.abfrage as ab
    from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

    class Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return U
    monkeypatch.setattr(ab, "datetime", Uhr)
    try:
        for fid in (FID, "inv_energy_2_ladung_pv_kwh"):
            await set_feld_quelle(w.a.id, fid, QuelleSetRequest(quelle="ha_app", entity_id=NEU, grund=grund,
                                                                falsch_seit=falsch_seit), w.db)
            await _laeufe()            # die In-Memory-Datenbank hat eine Verbindung: der Lauf nicht neben der nächsten Route
            _frisch(w)
    finally:
        monkeypatch.setattr(ab, "datetime", datetime)
    await _laeufe()
    _frisch(w)


async def _laeufe() -> None:
    from backend.services.zuordnung_wechsel import korrektur_lauf

    for t in list(korrektur_lauf._AUFGABEN.values()):
        if not t.done():
            await t


def _frisch(w: "Welt") -> None:
    """Der Hintergrund-Lauf schreibt in eigenen Sitzungen — die Sitzung der Probe vergisst ihre geladenen Zeilen."""
    w.db.expunge_all()
    zw.vergiss(w.db)


async def _stunde(w: Welt, h: datetime, *, ansetzen: bool = True) -> None:
    """Der Lauf «:05» um ``h`` (Reihe, Kanal, offene Wechsel), danach um 00:05 der Tagesabschluss des Vortags."""
    from backend.services.energie_profil._helpers import ohne_abruf
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
    from backend.services.sensor_snapshot_service import snapshot_anlage
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen

    _ha_bis(w, _ep(h) - STUNDE)
    a = (await w.db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
    await snapshot_anlage(w.db, a, zeitpunkt=h)
    await w.db.commit()
    await schreibe_kanaele_im_stundenlauf(w.db, a, h)
    await w.db.commit()
    if ansetzen:
        await offene_ansetzen(w.sitzungen, jetzt=h + timedelta(minutes=5))
        await _laeufe()
        _frisch(w)
    zw.vergiss(w.db)
    if h.hour == 0:
        with ohne_abruf({}):                          # kein Netz: Wetter und Börsenpreis bleiben leer
            await aggregate_day(a, h.date() - timedelta(days=1), w.db, source=Source.SCHEDULER)
        await w.db.commit()


async def betrieb(w: Welt, monkeypatch, von: datetime, bis: datetime, U: datetime | None, *, ansetzen: bool = True,
                  **k) -> None:
    """Je Epoch-Stunde der Lauf «:05» (in der doppelten Herbststunde zweimal 02:05, die fehlende Frühjahrsstunde gibt es
    nicht); die Umstellung vor dem Lauf, in dessen Stunde sie fällt."""
    um = U is None
    for e in range(_ep(von), _ep(bis) + 1, STUNDE):
        h = datetime.fromtimestamp(e)
        if not um and _ep(U) < e + 300:
            _ha_bis(w, _ep(U.replace(minute=0, second=0)) - STUNDE)
            await _umstellen(w, U, monkeypatch, **k)
            um = True
        await _stunde(w, h, ansetzen=ansetzen)


async def _wechsel(db) -> ZuordnungWechsel:
    zw.vergiss(db)
    return (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == KEY)
                             .order_by(ZuordnungWechsel.id.desc()))).scalars().first()


async def sichten(w: Welt) -> dict:
    """Stunde, Tag, Folgetag und Monat in jeder Sicht: Kanal (Kalendertag), Tagesansicht und Tagestabelle aus der Reihe,
    Tagesabschluss aus HA-Slots und gespeichert (Rückwärts-Raster), Bereichs-Leser, Monat «Aus HA laden» und laufender Monat."""
    from backend.api.routes import aktueller_monat as am
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services.kanal import lesen, merken
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE, snapshot_tagestabelle
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld
    from backend.services.snapshot.lts_aggregator import lts_tagestabelle, wechsel_kwargs

    db, lab = w.db, w.lab
    zw.vergiss(db)
    merken.invalidiere(w.a.id)
    a = (await db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
    invs = {"2": await db.get(Investition, 2)}
    D = lab.t1.replace(hour=0)
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id, Kanal.key == KEY))).scalar_one()
    out = {"kanal_stunde": None, "kanal_tag": {}}
    st = await lesen.stunden(db, k, lab.e1, lab.e1 + STUNDE)
    out["kanal_stunde"] = next((round(x.change, 3) for x in st.werte if x.change is not None), None)
    for d in (D, D + timedelta(days=1), D + timedelta(days=2)):
        z = await lesen.zeitraum(db, k, _ep(d), _ep(d + timedelta(days=1)))
        out["kanal_tag"][d.date().isoformat()] = None if z.delta is None else round(z.delta, 3)
    tag, h = lab.ab_ts.date(), lab.ab_ts.hour       # der Naht-Slot im Rückwärts-Raster (Slot h endet um Tag + h)
    reihe = await snapshot_tagestabelle(db, a, invs, tag)
    lts = await lts_tagestabelle(a, invs, tag, **await wechsel_kwargs(db, a.id))
    out["reihe_slot"], out["reihe_tag"] = reihe.stunden[h]["wallbox"], reihe.komponenten_kwh.get("wallbox_2")
    out["ha_slot"], out["ha_tag"] = lts.stunden[h]["wallbox"], lts.komponenten_kwh.get("wallbox_2")
    tz = (await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == a.id,
                                                               TagesZusammenfassung.datum == tag))).scalar_one_or_none()
    out["gespeichert_tag"] = None if tz is None else (tz.komponenten_kwh or {}).get("wallbox_2")
    feld = ("wallbox", "ladung_pv_kwh")              # dieselben Sensoren wie ``ladung_kwh`` (die Ausgabe kennt nur die Anteile)
    je = await lade_tageswerte_je_feld(db, a, invs, tag, tag, {feld: TAGESDETAIL_AUSGABE[feld]},
                                       rueckwaerts_tage=frozenset({tag}), kanal_zuerst=False)
    out["bereichs_leser"] = (je.get(tag) or {}).get(TAGESDETAIL_AUSGABE[feld])
    monat = (lab.t1.year, lab.t1.month)
    route = await get_monatswerte(a.id, *monat, db)
    out["monat_aus_ha_laden"] = next((f.differenz for i in route.investitionen for f in i.felder if f.feld == "ladung_kwh"),
                                     None)
    laufend = await am._collect_ha_statistics_data(a, *monat)
    out["monat_laufend"] = (laufend.get("inv_2_ladung_kwh") or laufend.get("inv_2_ladung_pv_kwh") or (None,))[0]
    await db.commit()
    return out


def soll(w: Welt) -> dict:
    lab, bis = w.lab, w.bis
    D = lab.t1.replace(hour=0)
    tag, h = lab.ab_ts.date(), lab.ab_ts.hour

    def bis_jetzt(wo):
        return lambda t: _ep(t) <= bis and wo(t)
    rt = lab.soll(bis_jetzt(_im_tag(tag)))
    return {
        "kanal_stunde": lab.soll(bis_jetzt(lambda t: t == lab.t1)),
        "kanal_tag": {(D + timedelta(days=i)).date().isoformat(): lab.soll(bis_jetzt(
            lambda t, i=i: D + timedelta(days=i) <= t < D + timedelta(days=i + 1))) for i in range(3)},
        "reihe_slot": lab.soll(bis_jetzt(_im_slot(tag, h))), "reihe_tag": rt,
        "ha_slot": lab.soll(bis_jetzt(_im_slot(tag, h))), "ha_tag": rt, "gespeichert_tag": rt, "bereichs_leser": rt,
        "monat_aus_ha_laden": lab.soll(bis_jetzt(lambda t: (t.year, t.month) == (lab.t1.year, lab.t1.month))),
        "monat_laufend": lab.soll(bis_jetzt(lambda t: (t.year, t.month) == (lab.t1.year, lab.t1.month))),
    }


def _vergleich(ist: dict, s: dict) -> dict:
    """Die Sichten, die vom Soll abweichen (Kanal-Tage ohne volle Deckung zählen nicht: ``None``)."""
    falsch = {}
    for k, v in s.items():
        if k == "kanal_tag":
            for d, x in v.items():
                y = ist["kanal_tag"].get(d)
                if y is not None and abs(y - x) > 1e-6:
                    falsch[f"kanal_tag {d}"] = (y, x)
        elif ist[k] is None or abs(ist[k] - v) > 1e-6:
            falsch[k] = (ist[k], v)
    return falsch


def ende(U: datetime, t1: datetime = T1) -> datetime:
    """Bis zum Tagesabschluss des Tags nach dem Tausch, mindestens drei Stunden nach der Umstellung."""
    return max(U.replace(minute=0, second=0) + timedelta(hours=3), t1.replace(hour=0) + timedelta(days=2, hours=1))


TABELLEN = ("kanal_statistik", "kanal_quelle", "sensor_snapshots", "zuordnung_wechsel", "settings", "tages_zusammenfassung",
           "tages_energie_profil")


async def stand_der_tabellen(db) -> dict:
    """Inhalt je Tabelle (ohne Zeilen-Nummern): ändert ein Lauf etwas?"""
    out = {}
    for t in TABELLEN:
        rows = (await db.execute(text(f"SELECT * FROM {t}"))).mappings().all()
        out[t] = sorted(repr(sorted((k, v) for k, v in r.items() if k not in ("id", "erstellt_am", "aktualisiert_am",
                                                                               "updated_at", "created_at"))) for r in rows)
    return out


async def zweiter_aufruf_und_konsistenz(w: Welt, jetzt: datetime) -> tuple[dict, list, int]:
    """Ein zweiter Aufruf des Dienstes (direkt und aus dem Stundenlauf) und der Konsistenzlauf 02:45: was ändert sich?"""
    from backend.services.kanal.konsistenz import konsistenz_anlage
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen, setze_an

    vorher = await stand_der_tabellen(w.db)
    row = await _wechsel(w.db)
    zweiter = await setze_an(w.sitzungen, row.id, jetzt=jetzt)
    await offene_ansetzen(w.sitzungen, jetzt=jetzt)
    await _laeufe()
    erg = await konsistenz_anlage(w.sitzungen, w.a.id, ha_svc=w.svc)
    nachher = await stand_der_tabellen(w.db)
    return ({t: (len(vorher[t]), len(nachher[t])) for t in TABELLEN if vorher[t] != nachher[t]} if not zweiter["angesetzt"]
            else {"zweiter_aufruf": True}), erg.korrigiert, erg.fehler


UMSTELLUNG = {
    "0740": T1 + timedelta(minutes=40),
    "0820": T1 + timedelta(minutes=80),
    "1030": T1 + timedelta(hours=3, minutes=30),
    "zwei_tage": T1 + timedelta(days=2, hours=3, minutes=30),
    "voll_0800": T1 + timedelta(hours=1),                   # genau zur vollen Stunde (``ab_ts_aus``: 08:00 → 08:00)
    "vor_erster_zeile": T1 - timedelta(minutes=20),         # bevor HA eine Zeile des neuen führt: bleibt offen bis 08:05
}


@pytest.mark.parametrize("fall", list(UMSTELLUNG), ids=list(UMSTELLUNG))
async def test_lab_umstellung_jede_sicht_wie_ha(db, monkeypatch, fall):
    """F3 von Ende zu Ende: Feld-Route (Grund «Fortsetzung») ⇒ Zeile ``offen`` ⇒ Stundenlauf setzt an (``beide``, G = T1, Rand
    = letzter Stand des alten / 0, ``ab_ts`` = T1 + 1 h). Danach nennt jede Sicht Stunde 1,3, Tag 15,3, Folgetage 12,0 und den
    Monat wie HA. Ein zweiter Aufruf ändert nichts; der Konsistenzlauf korrigiert 0 Zeilen."""
    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = UMSTELLUNG[fall]
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), ende(U), U)
    row = await _wechsel(db)
    assert (row.ansatz, row.ab_ts, row.stand_neu_null) == ("beide", T1 + timedelta(hours=1), 0.0)
    assert row.stand_alt_ende == pytest.approx(lab.rand("beide")[0])
    ist, s = await sichten(w), soll(w)
    assert _vergleich(ist, s) == {}, (ist, s)
    assert ist["kanal_stunde"] == pytest.approx(1.3) and ist["kanal_tag"][T1.date().isoformat()] == pytest.approx(15.3)
    assert ist["kanal_tag"][(T1 + timedelta(days=1)).date().isoformat()] == pytest.approx(12.0)
    assert await zweiter_aufruf_und_konsistenz(w, ende(U) + timedelta(minutes=10)) == ({}, [], 0)


ZEITEN = {
    "herbst_doppelt": datetime(2026, 10, 25, 2),          # Berlin: «02:00» — ``mktime`` wählt die zweite der doppelten Stunden
                                                          # (die erste: test_sensorwechsel_u2b_proben, Korrekturrunde a-K N5)
    "fruehjahr_davor": datetime(2026, 3, 29, 1),          # Berlin: Tausch 01:00–02:00, die Stunde vor der fehlenden (a-K N5)
    "fruehjahr_fehlt": datetime(2026, 3, 29, 3),          # Berlin: 02:00 fehlt, die Tausch-Stunde ist 03:00
    "mitternacht": datetime(2026, 11, 9, 23),             # der erste Stand des neuen ist 00:00 des Folgetags
    "monatsgrenze": datetime(2026, 10, 31, 23),           # … und des Folgemonats
}


@pytest.mark.parametrize("zeit", list(ZEITEN), ids=list(ZEITEN))
async def test_zeit_proben_umstellung_0740(db, monkeypatch, zeit):
    """Tausch in der doppelten Herbststunde, in der Stunde nach der fehlenden Frühjahrsstunde, über Mitternacht und die
    Monatsgrenze; Umstellung 40 Minuten nach Beginn der Tausch-Stunde. Jede Sicht = HAs Regel (Datei läuft auch mit
    ``TZ=Pacific/Auckland`` und ``TZ=UTC``)."""
    t1 = ZEITEN[zeit]
    lab = Lab(t1)
    w = await _welt(db, monkeypatch, lab)
    U = datetime.fromtimestamp(lab.e1 + 40 * 60)
    await betrieb(w, monkeypatch, datetime.fromtimestamp(lab.e1 - 30 * STUNDE), ende(U, t1), U)
    row = await _wechsel(db)
    assert (row.ansatz, row.ab_ts) == ("beide", lab.ab_ts)
    ist, s = await sichten(w), soll(w)
    vorher = datetime.fromtimestamp(lab.e1 - STUNDE).hour
    umstellung = vorher == t1.hour or (vorher + 1) % 24 != t1.hour        # doppelte bzw. fehlende Stunde in dieser Zone
    assert _vergleich(ist, s) == (DST_GRENZE.get(zeit, {}) if umstellung else {}), (ist, s)
    assert ist["kanal_stunde"] == pytest.approx(1.3)


#: **Benannte Grenze (Bestand, nicht U2):** der Schreiber der Reihe liest den Stand um ``t`` mit ``get_value_at(t)`` aus der
#: Zeile ``t − 1 h`` in Wand-Uhr-Zeit. In der doppelten Herbststunde trifft «02:00» die erste (Sommerzeit-)Stunde — beginnt die
#: Statistik des neuen erst in der zweiten, schreibt eedc um 03:00 keinen Stand (gemessen: ``get_value_at(03:00)`` = None);
#: in der Stunde nach der fehlenden Frühjahrsstunde steht der Stand 03:00 eine Stunde zu spät. Seit der Korrekturrunde a-K (N5)
#: liest das Ansetzen den Rand-Stand epoch-genau aus der Zeile — bei Umstellung am Tag des Tauschs **treffen Tag und Monat
#: das Soll in jeder Sicht**; es bleibt die Verschiebung der Stunde in der Reihe (der Naht-Slot zeigt einen Teil, der Rest steht
#: im Slot daneben). Bei Umstellung nach dem Tag liest der Schreiber die Stände neu (dort bleibt sein Bestand, BERECHNUNGEN
#: Grenze (4)). Kanal, Tagesabschluss aus HA-Slots und Monat treffen das Soll.
DST_GRENZE = {
    "herbst_doppelt": {"reihe_slot": (pytest.approx(0.9), 1.3)},
    "fruehjahr_fehlt": {"reihe_slot": (pytest.approx(0.7), 1.3)},
}


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_vorgeschichte_ist_schnitt_an_der_stunde_der_umstellung(db, monkeypatch, sprengsatz):
    """F2 mit Überlappung (der neue zählt schon einen Tag vorher 0,2 kWh/h): ``schnitt``, G = die volle Stunde der
    Umstellung (10:00), beide Rand-Stände in der Zeile vor G ⇒ jede Sicht = Soll (alt bis 10:00, neu ab 10:00). Sprengsatz:
    ``beide`` bei derselben Saat ⇒ die Stunde des Schnitts zählt die ganze Vorgeschichte des neuen mit."""
    import backend.core.berechnungen.zaehler_naht as zn

    if sprengsatz:
        monkeypatch.setattr(zn, "ueberlappt", lambda *_a: False)
    lab = Lab(T1, vorgeschichte=True, schnitt=T1 + timedelta(hours=3))
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=30)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), ende(U), U)
    row = await _wechsel(db)
    if sprengsatz:                   # ``beide`` mit G = T1 (Beginn der Vorgeschichte): der alte zählt danach nichts mehr
        assert row.ansatz == "beide"
        ist, s = await sichten(w), soll(w)
        assert ist["kanal_tag"][T1.date().isoformat()] == pytest.approx(10.1) and s["kanal_tag"][T1.date().isoformat()] == 13.6
        return
    assert (row.ansatz, row.ab_ts) == ("schnitt", T1 + timedelta(hours=4))
    assert (row.stand_alt_ende, row.stand_neu_null) == pytest.approx(lab.rand("schnitt"))
    ist, s = await sichten(w), soll(w)
    assert _vergleich(ist, s) == {}, (ist, s)
    assert await zweiter_aufruf_und_konsistenz(w, ende(U) + timedelta(minutes=10)) == ({}, [], 0)


async def test_alte_entitaet_vor_dem_stundenende_geloescht(db, monkeypatch):
    """Lab M1: die alte Entität verschwindet in der Tausch-Stunde; HA führt ihren Zuwachs nur bis zum letzten abgeschlossenen
    5-Minuten-Fenster (0,4 von 0,6) und danach keine Zeile. ``stand_alt_ende`` = HAs letzte Stundenzeile (Bauplan Nr. 143
    (1)) ⇒ eedc zeigt dasselbe wie HA: Stunde 0,4 + 0,7 = 1,1, kein Stück ergänzt."""
    lab = Lab(T1)
    s_vor = lab.alt[lab.e1 - STUNDE][1]
    lab.alt = {e: v for e, v in lab.alt.items() if e < lab.e1}
    lab.alt[lab.e1] = (0.4, round(s_vor + 0.4, 6))
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=30)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), ende(U), U)
    row = await _wechsel(db)
    assert (row.ansatz, row.stand_alt_ende) == ("beide", pytest.approx(s_vor + 0.4))
    ist, s = await sichten(w), soll(w)
    assert _vergleich(ist, s) == {}, (ist, s)
    assert ist["kanal_stunde"] == pytest.approx(1.1)


async def test_offene_zeile_spiegel_laesst_aus_und_ha_nicht_erreichbar(db, monkeypatch):
    """Umstellung vor der ersten Zeile des neuen (06:40): die Zeile bleibt ``offen``; der Stundenlauf spiegelt den Schlüssel
    nicht (sonst setzte er die neue Quelle mit dem Versatz 438,0 an, Stunde 0,7 — Sprengsatz des Rechenwegs). HA nicht
    erreichbar ⇒ bleibt offen; danach setzt der Dienst an."""
    from backend.services.zuordnung_wechsel.ansatz import WARTET_HA, WARTET_ZEILE, setze_an

    class Aus:
        is_available = False
    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 - timedelta(minutes=20)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), T1 + timedelta(hours=1), U, ansetzen=False)
    row = await _wechsel(db)
    assert row.ansatz == "offen" and row.ab_ts == T1
    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    assert (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id,
                                                          KanalStatistik.start_ts >= _ep(T1) - STUNDE))).first() is None
    assert [q.statistic_id for q in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars()] \
        == [ALT]
    jetzt = T1 + timedelta(hours=1, minutes=5)
    assert (await setze_an(w.sitzungen, row.id, ha_svc=Aus(), jetzt=jetzt))["lage"] is None or \
        (await _wechsel(db)).ansatz == "offen"
    vorher = await setze_an(w.sitzungen, row.id, jetzt=T1 + timedelta(minutes=50))      # die Zeile 07:00 gibt es noch nicht
    assert (vorher["angesetzt"], vorher["lage"]["wartet"]) == (False, WARTET_ZEILE)
    aus = await setze_an(w.sitzungen, row.id, ha_svc=Aus(), jetzt=jetzt)
    assert (aus["angesetzt"], aus["lage"]["wartet"]) == (False, WARTET_HA)
    an = await setze_an(w.sitzungen, row.id, jetzt=jetzt)
    await _laeufe()
    _frisch(w)
    assert an["angesetzt"] and (await _wechsel(db)).ansatz == "beide"
    await betrieb(w, monkeypatch, T1 + timedelta(hours=2), ende(U), None)
    ist, s = await sichten(w), soll(w)
    assert _vergleich(ist, s) == {}, (ist, s)


async def test_offener_korrektur_lauf_am_schluessel_wartet(db, monkeypatch):
    """Ein Korrektur-Lauf, dessen Füllen am selben Schlüssel aussteht, hält das Ansetzen auf (die Zeile bleibt offen)."""
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel.ansatz import WARTET_LAUF, setze_an

    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(minutes=40)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=3), T1 + timedelta(hours=1), U, ansetzen=False)
    await korrektur_lauf.anlegen(db, "lauf1", w.a.id, KEY, [], fuellen={"erledigt": False})
    await db.commit()
    erg = await setze_an(w.sitzungen, (await _wechsel(db)).id, jetzt=T1 + timedelta(hours=1, minutes=5))
    assert (erg["angesetzt"], erg["lage"]["wartet"]) == (False, WARTET_LAUF)


async def test_ansetzen_aendert_nichts_ausserhalb_von_schluessel_und_zeitraum(db, monkeypatch):
    """Was das Ansetzen anfasst: Kanal des Schlüssels ab G, Reihe des Schlüssels zwischen altem und neuem ``ab_ts``, die
    Wechsel-Zeile, der Zustand des Laufs. Ein anderer Schlüssel und die Zeit davor bleiben Zeile für Zeile, wie sie sind."""
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen

    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=30)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), T1 + timedelta(hours=4), U, ansetzen=False)
    g = _ep(T1)

    async def teile():
        kanal = {key: [tuple(r) for r in (await db.execute(text(
            "SELECT s.start_ts, s.sum, s.state FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id WHERE k.key = :k "
            "AND (k.key != :key OR s.start_ts < :g) ORDER BY 1"), {"k": key, "key": KEY, "g": g})).all()]
                 for key in (KEY, "inv:2:ladung_pv_kwh")}
        alle = [tuple(r) for r in (await db.execute(select(
            SensorSnapshot.sensor_key, SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh).order_by(
            SensorSnapshot.sensor_key, SensorSnapshot.zeitpunkt))).all()]
        reihe = [r for r in alle if r[0] != KEY or r[1] < T1 + timedelta(hours=1)]
        neu = [r for r in alle if r[0] == KEY and T1 + timedelta(hours=1) <= r[1] < T1 + timedelta(hours=4)]
        return kanal, reihe, neu
    vorher = await teile()
    zeilen_pv = (await db.execute(text("SELECT COUNT(*) FROM zuordnung_wechsel WHERE sensor_key != :k"), {"k": KEY})).scalar()
    from backend.models.zuordnung_wechsel import ZuordnungWechsel as Z
    await db.execute(Z.__table__.update().where(Z.sensor_key != KEY).values(ansatz=None))     # nur KEY wird angesetzt
    await db.commit()
    await offene_ansetzen(w.sitzungen, jetzt=T1 + timedelta(hours=4, minutes=5))
    await _laeufe()
    _frisch(w)
    nachher = await teile()
    assert (await _wechsel(db)).ansatz == "beide"
    assert vorher[0]["inv:2:ladung_pv_kwh"] == nachher[0]["inv:2:ladung_pv_kwh"] and vorher[1] == nachher[1]
    assert vorher[0][KEY] == nachher[0][KEY] and len(vorher[1]) > 50
    # Schritt 3: die Stände zwischen neuem und altem ab_ts (08:00 … 10:00) tragen jetzt den neuen Sensor (HAs Summe)
    assert [(t, round(x, 3)) for _k, t, x in nachher[2]] == [
        (T1 + timedelta(hours=h), lab.neu[lab.e1 + (h - 1) * STUNDE][1]) for h in (1, 2, 3)]
    assert zeilen_pv == (await db.execute(text("SELECT COUNT(*) FROM zuordnung_wechsel WHERE sensor_key != :k"),
                                          {"k": KEY})).scalar()


def test_nur_home_assistant_zu_home_assistant():
    """Andere Kombinationen als HA → HA (MQTT → HA, HA → MQTT, über «Keine», gleiche Entität) bekommen keinen Ansatz."""
    from types import SimpleNamespace

    from backend.services.zuordnung_wechsel.ansatz import wird_angesetzt

    def z(vorher, nachher, grund="fortsetzung", aufgehoben=None):
        return SimpleNamespace(vorher=vorher, nachher=nachher, grund=grund, aufgehoben_durch=aufgehoben)
    mq, keine = {"art": "mqtt", "mqtt_key": "x"}, {"art": "keine"}
    qa, qn = {"art": "ha", "entity_id": ALT}, {"art": "ha", "entity_id": NEU}
    assert wird_angesetzt(z(qa, qn))
    assert not any(wird_angesetzt(x) for x in (z(mq, qn), z(qa, mq), z(keine, qn), z(qa, qa), z(qa, qn, "korrektur"),
                                               z(qa, qn, None), z(qa, qn, aufgehoben=3), z(None, qn)))


# ═══ F10 — «Grund nachtragen» mit «bleiben» ═════════════════════════════════════════════════════════════════════════════

async def _wechsel_ohne_grund(w: Welt, U: datetime) -> None:
    """Ein Wechsel aus der Zeit vor der Abfrage (``altbestand``, Grund leer): Zuordnung auf den neuen Sensor, Zeile ohne Grund."""
    from sqlalchemy.orm.attributes import flag_modified

    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    a = (await w.db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
    for f in ("ladung_kwh", "ladung_pv_kwh"):
        a.sensor_mapping["investitionen"]["2"]["felder"][f]["sensor_id"] = NEU
    flag_modified(a, "sensor_mapping")
    for key in (KEY, "inv:2:ladung_pv_kwh"):
        w.db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=U, ab_ts=ab_ts_aus(U),
                                  vorher={"art": "ha", "entity_id": ALT}, nachher={"art": "ha", "entity_id": NEU},
                                  grund=None, herkunft="altbestand"))
    await w.db.commit()
    zw.vergiss(w.db)


async def _nachtragen(w: Welt, grund: str = "fortsetzung", falsch_seit=None) -> dict:
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, grund_nachtragen

    out = {}
    for key in (KEY, "inv:2:ladung_pv_kwh"):
        zw.vergiss(w.db)
        row = (await w.db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == key,
                                                                 ZuordnungWechsel.aufgehoben_durch.is_(None))
                                  .order_by(ZuordnungWechsel.id.desc()))).scalars().first()
        out[key] = await grund_nachtragen(w.a.id, row.id, GrundNachtragRequest(grund=grund, falsch_seit=falsch_seit), w.db)
        await _laeufe()
        _frisch(w)
    return out


async def _kanal_inhalt(db) -> tuple:
    q = [tuple(r) for r in (await db.execute(text(
        'SELECT q.gueltig_ab, q.statistic_id, round(q."offset", 6), q.verworfen_ts FROM kanal_quelle q JOIN kanal k ON '
        "k.id = q.kanal_id WHERE k.key = :k ORDER BY 1"), {"k": KEY})).all()]
    z = [tuple(r) for r in (await db.execute(text(
        "SELECT s.start_ts, s.sum, s.state FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id WHERE k.key = :k "
        "ORDER BY 1"), {"k": KEY})).all()]
    return q, z


@pytest.mark.parametrize("ueberlappung", [False, True], ids=["beide", "schnitt"])
async def test_f10_nachtrag_bleiben(db, monkeypatch, ueberlappung):
    """«Grund nachtragen» → «bleiben» (Fortsetzung) an einem Wechsel ohne Grund: die Zeile ``nachtrag`` wird ``offen`` angelegt
    und gleich angesetzt; Vorgabe für den Schnitt ist die Stunde des verzeichneten Wechsels. Ohne Überlappung (Lab-Zeilen)
    zeigt danach jede Sicht HAs Zahl; mit Überlappung (wie die Produktiv-Kopie) bleibt der Kanal Zeile für Zeile, wie der
    Stundenlauf ihn an der Stunde des Wechsels angesetzt hat, und die Reihe zeigt dieselbe Menge."""
    lab = Lab(T1, vorgeschichte=ueberlappung, schnitt=(T1 + timedelta(hours=3)) if ueberlappung else None)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=47)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), U.replace(minute=0), None)
    await _wechsel_ohne_grund(w, U)
    await betrieb(w, monkeypatch, U.replace(minute=0) + timedelta(hours=1), ende(U), None)
    kanal_vorher = await _kanal_inhalt(db)
    erg = await _nachtragen(w)
    assert all(e["eingetragen"] for e in erg.values())
    row = await _wechsel(db)
    assert (row.herkunft, row.ansatz) == ("nachtrag", "schnitt" if ueberlappung else "beide")
    ist, s = await sichten(w), soll(w)
    assert _vergleich(ist, s) == {}, (ist, s)
    if ueberlappung:
        assert await _kanal_inhalt(db) == kanal_vorher
    assert await zweiter_aufruf_und_konsistenz(w, ende(U) + timedelta(minutes=10)) == ({}, [], 0)


# ═══ F11 — Abgleiche, die den Ansatz nicht brechen dürfen ═══════════════════════════════════════════════════════════════

async def test_f11_abgleiche_aendern_nichts(db, monkeypatch):
    """Nach dem Ansetzen (Umstellung 10:30): «HA-Spiegel jetzt abgleichen» samt Neu-Aggregation des Tages, «Tag neu
    aggregieren», die Tagesansicht mit Self-Healing, der Startlauf des Kanal-Nachfüllens und weitere Stundenläufe — keine
    Sicht ändert ihre Zahl, keine Tabelle des Schlüssels ändert sich (außer der Neu-Aggregation derselben Werte)."""
    from backend.api.routes.energie_profil.repair import spiegel_abgleich_tag_lauf
    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.services.energie_profil._helpers import ohne_abruf
    from backend.services.kanal.nachfuellen import nachfuellen_anlage
    from backend.services.repair_orchestrator import _reparatur_aggregat

    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=30)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), ende(U), U)
    s = soll(w)
    vorher = await sichten(w)
    assert _vergleich(vorher, s) == {}
    kanal, reihe = await _kanal_inhalt(db), await _reihe(db)
    with ohne_abruf({}):
        await spiegel_abgleich_tag_lauf(db, w.a.id, T1.date())
        a = (await db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
        await _reparatur_aggregat(a, T1.date(), db)
    await db.commit()
    await get_tag_detail(anlage_id=w.a.id, datum=T1.date(), db=db)
    await db.commit()
    await nachfuellen_anlage(w.sitzungen, w.a.id, jetzt=ende(U) + timedelta(minutes=5), ha_svc=w.svc)
    _frisch(w)
    assert (await _kanal_inhalt(db), await _reihe(db)) == (kanal, reihe)
    assert _vergleich(await sichten(w), s) == {}


async def _reihe(db) -> list:
    return [tuple(r) for r in (await db.execute(text(
        "SELECT zeitpunkt, wert_kwh FROM sensor_snapshots WHERE sensor_key = :k ORDER BY 1"), {"k": KEY})).all()]


async def test_f11_spaetere_korrektur_hebt_die_zeile_samt_rand_auf(db, monkeypatch):
    """Eine spätere Korrektur («Grund nachtragen»: Fortsetzung → Korrektur) hebt die angesetzte Zeile auf — ihre Rand-Stände
    zählen nicht mehr (keine Naht mit Versatz), es gilt die Korrektur."""
    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=30)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), ende(U), U)
    angesetzt = await _wechsel(db)
    assert angesetzt.ansatz == "beide"
    assert any(zw.rand_versatz(x) is not None for x in (await zw.lade_wechsel(db, w.a.id))[KEY])
    await _nachtragen(w, "korrektur", T1 - timedelta(hours=5))
    zw.vergiss(db)
    zeilen = (await zw.lade_wechsel(db, w.a.id))[KEY]
    alt = next(x for x in zeilen if x.id == angesetzt.id)
    assert alt.aufgehoben_durch is not None and zw.rand_versatz(alt) is None
    assert not any(zw.rand_versatz(x) is not None for x in zeilen)
    assert not any(getattr(n, "versatz", None) for n in await zw.fortsetzungs_naehte(db, w.a.id, KEY))


# ═══ F2 — Höhe der Reihe und Rückfall (Bauplan Nr. 143 (2), Nr. 144) ════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_hoehe_passt_nicht_kein_stand_auf_anderer_hoehe(db, monkeypatch, sprengsatz):
    """Die gespeicherte Reihe des alten liegt 1 000 unter HAs Summe (wie die Produktiv-Kopie 1 906,5): eedc füllt keinen Stand des
    alten aus HA und nimmt als Rand-Stand den letzten gespeicherten — kein Stand auf anderer Höhe kommt dazu; die Reihe zählt
    die Tausch-Stunde dann nur mit dem neuen (0,7; benannt), der Kanal mit beiden (1,3). Sprengsatz «Höhe nicht geprüft» ⇒ HAs
    Stand als Rand ⇒ die Reihe springt um 1 000."""
    from backend.services.zuordnung_wechsel import ansatz as an
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen

    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(minutes=40)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), T1 + timedelta(hours=1), U, ansetzen=False)
    await db.execute(text("UPDATE sensor_snapshots SET wert_kwh = wert_kwh - 1000 WHERE zeitpunkt < :ab"), {"ab": T1 + timedelta(hours=1)})
    from sqlalchemy import delete
    await db.execute(delete(SensorSnapshot).where(SensorSnapshot.zeitpunkt == T1))           # ein fehlender Stand des alten
    await db.commit()
    if sprengsatz:
        echt = an._rand_reihe

        async def ohne_hoehe(db_, la, *a):
            await echt(db_, la, *a)
            if la.hoehe_passt is False:
                la.hoehe_passt = None
                la.stand_alt_ende = lab.alt[lab.e1][1]
                la.staende_neu = (T1, la.staende_neu[1] if la.staende_neu else T1 + timedelta(hours=1))
        monkeypatch.setattr(an, "_rand_reihe", ohne_hoehe)
    n_vorher = len(await _reihe(db))
    await offene_ansetzen(w.sitzungen, jetzt=T1 + timedelta(hours=1, minutes=5))
    await _laeufe()
    _frisch(w)
    row = await _wechsel(db)
    reihe = await _reihe(db)                       # direkt nach dem Ansetzen (die Sichten heilen später selbst, Bestand)
    await betrieb(w, monkeypatch, T1 + timedelta(hours=2), ende(U), None)
    ist = await sichten(w)
    if sprengsatz:
        assert row.stand_alt_ende == pytest.approx(lab.alt[lab.e1][1]) and ist["reihe_tag"] > 999.0
        return
    assert row.ansatz == "beide" and row.stand_alt_ende == pytest.approx(lab.alt[lab.e1 - 2 * STUNDE][1] - 1000.0)
    assert not any(datetime.fromisoformat(str(t)) == T1 for t, _w in reihe)          # der fehlende Stand blieb leer
    assert len(reihe) == n_vorher
    assert min(wert for t, wert in reihe if datetime.fromisoformat(str(t)) < T1) < 0          # die alte Höhe blieb
    assert (ist["kanal_stunde"], ist["ha_slot"]) == (pytest.approx(1.3), pytest.approx(1.3))


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_ha_fuehrt_den_alten_nicht_mehr_rueckfall_nur_aus_has_statistik(db, monkeypatch, sprengsatz):
    """Bauplan Nr. 143 (2): führt HA die Statistik des alten nicht mehr, ist der Rand der letzte bei eedc gespeicherte Stand — nur
    einer aus HAs Statistik, nie ein Live-Wert (hier ein Rückfall-Stand 07:30 mit 438,5). Kanal und Reihe zählen die Tausch-Stunde
    dann nur mit dem neuen — wie HA, das den alten nicht mehr führt. Sprengsatz: jeder gespeicherte Stand ⇒ 438,5."""
    from backend.services.zuordnung_wechsel import ansatz as an
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen

    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(minutes=40)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), T1 + timedelta(hours=1), U, ansetzen=False)
    with w.svc._engine.begin() as c:                       # «Statistik löschen» in HA
        c.execute(text("DELETE FROM statistics WHERE metadata_id = :m"), {"m": w.mids[ALT]})
        c.execute(text("DELETE FROM statistics_meta WHERE id = :m"), {"m": w.mids[ALT]})
    w.svc._meta_cache = {} if hasattr(w.svc, "_meta_cache") else None
    db.add(SensorSnapshot(anlage_id=w.a.id, sensor_key=KEY, zeitpunkt=T1 + timedelta(minutes=30), wert_kwh=438.5,
                          quelle="live_fallback"))
    await db.commit()
    if sprengsatz:
        echt = an._letzter_stand

        async def jeder(*a, **k):
            k["nur_ha"] = False
            return await echt(*a, **k)
        monkeypatch.setattr(an, "_letzter_stand", jeder)
    await offene_ansetzen(w.sitzungen, jetzt=T1 + timedelta(hours=1, minutes=5))
    await _laeufe()
    _frisch(w)
    row = await _wechsel(db)
    alt_07 = lab.alt[lab.e1 - STUNDE][1]
    assert row.ansatz == "beide"
    assert row.stand_alt_ende == pytest.approx(438.5 if sprengsatz else alt_07)


# ═══ M8a — «Alle Monatswerte» und Import-Vorschau ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_m8a_monat_nur_mit_dem_alten_sensor_steht_in_der_liste(db, monkeypatch, sprengsatz):
    """Ein Monat, in dem nur der alte Sensor Werte hat (Oktober; der neue beginnt am 03.11.), steht in «Alle Monatswerte» und in
    der Import-Vorschau — mit dem Wert, den «Aus HA laden» für den Monat nennt. Sprengsatz (HEAD): die Liste fragt nur die
    heutigen Entitäten ⇒ der Monat fehlt."""
    from backend.api.routes.ha_statistics import get_alle_monatswerte, get_import_vorschau, get_monatswerte
    from backend.services.zuordnung_wechsel import monat as mo
    from backend.tests.test_sensorwechsel_u2a1_proben import _lab_welt

    if sprengsatz:
        monkeypatch.setattr(mo, "alle_monatswerte", lambda db_, aid, svc, ids, ab=None: _gleich(svc.get_alle_monatswerte(ids, ab)))
    lab = Lab(datetime(2026, 11, 3, 7), start=datetime(2026, 9, 29))
    a, _svc = await _lab_welt(db, monkeypatch, lab)
    okt = lab.soll(lambda t: (t.year, t.month) == (2026, 10))

    def wert(r):
        return next((f.differenz for i in r.investitionen for f in i.felder if f.feld == "ladung_kwh"), None)
    alle = {(r.jahr, r.monat): wert(r) for r in await get_alle_monatswerte(a.id, None, None, db)}
    vorschau = {(m.jahr, m.monat) for m in (await get_import_vorschau(a.id, db)).monate}
    einzel = wert(await get_monatswerte(a.id, 2026, 10, db))
    if sprengsatz:
        assert (2026, 10) not in alle and (2026, 10) not in vorschau and einzel == pytest.approx(okt)
        return
    assert alle[(2026, 10)] == pytest.approx(okt) == pytest.approx(einzel) and (2026, 10) in vorschau


async def _gleich(x):
    return x


# ═══ P-1 — Korrektur zwischen zwei Sensoren: Rand-Stände an «Falsch seit» ══════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_p1_korrektur_zwischen_zwei_sensoren_mit_rand(db, monkeypatch, sprengsatz):
    """Korrektur beim Wechsel (Feld-Route, «falsch seit» 04:00): bis dahin der alte, danach der richtige Sensor, den HA mit
    Geschichte führt. Die Korrektur-Zeile trägt die Rand-Stände nach der Regel «bleiben» mit Schnitt an «falsch seit − 1 h»
    (``ansatz = schnitt``: gespeicherter Stand des alten um 03:00, Stand des richtigen dort aus HA) ⇒ die Reihe zählt den Tag wie
    der Tagesabschluss aus HA-Slots (die Stunde vor «falsch seit» mit dem richtigen Sensor, wie der Kanal). Sprengsatz: ohne
    Rand-Stände teilt die Naht ⇒ der Reihe fehlt diese Stunde (0,2)."""
    import backend.services.zuordnung_wechsel.korrektur as kr

    if sprengsatz:
        async def ohne(*_a, **_k):
            return None
        monkeypatch.setattr(kr, "_rand_an_falsch_seit", ohne)
    lab = Lab(T1, vorgeschichte=True)
    w = await _welt(db, monkeypatch, lab)
    U, fs = T1 + timedelta(hours=3, minutes=30), T1 - timedelta(hours=3)
    await betrieb(w, monkeypatch, T1 - timedelta(hours=30), ende(U), U, grund="korrektur", falsch_seit=fs)
    zw.vergiss(db)
    korr = [x for x in (await zw.lade_wechsel(db, w.a.id))[KEY] if x.grund == "korrektur" and x.aufgehoben_durch is None]
    assert len(korr) == 1 and korr[0].falsch_seit_ts == fs
    ist = await sichten(w)
    if sprengsatz:
        assert korr[0].ansatz is None and ist["reihe_tag"] == pytest.approx(ist["ha_tag"] - 0.2)
        return
    assert korr[0].ansatz == "schnitt" and zw.korrektur_rand_versatz(korr[0]) is not None
    assert ist["reihe_tag"] == pytest.approx(ist["ha_tag"]) == pytest.approx(ist["bereichs_leser"])
    D = T1.replace(hour=0)
    soll_d = sum(z for e, (z, _s) in lab.alt.items() if D <= datetime.fromtimestamp(e) < fs - timedelta(hours=1)) + \
        sum(z for e, (z, _s) in lab.neu.items() if fs - timedelta(hours=1) <= datetime.fromtimestamp(e) < D + timedelta(days=1))
    assert ist["kanal_tag"][T1.date().isoformat()] == pytest.approx(round(soll_d, 3))


# ═══ Erste und letzte Zeile über WebSocket (Bauplan Nr. 143 (3)) ════════════════════════════════════════════════════════

class _WsAttrappe:
    """Ein WebSocket-Transport über Stundenzeilen ``{start_ts: sum}``: ``statistiken`` fasst zu month/day zusammen wie HA und
    zählt die Aufrufe (Periode, Zahl der gelieferten Zeilen)."""

    def __init__(self, zeilen: dict):
        self.zeilen, self.aufrufe = zeilen, []

    def statistiken(self, sids, von, bis, period="hour", types=None):
        a, b = von.timestamp(), bis.timestamp()
        roh = [(t, s) for t, s in sorted(self.zeilen.items()) if a <= t < b]
        if period in ("day", "month"):
            gruppe = {}
            for t, s in roh:
                d = datetime.fromtimestamp(t)
                k = d.replace(hour=0) if period == "day" else d.replace(day=1, hour=0)
                gruppe.setdefault(_ep(k), s)
            roh = sorted(gruppe.items())
        self.aufrufe.append((period, len(roh)))
        return {sids[0]: [{"start_ts": float(t), "sum": s, "state": s} for t, s in roh]}


def _ws_dienst(monkeypatch, zeilen: dict):
    from contextlib import contextmanager

    from backend.services.ha_statistics_service import HAStatisticsService
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service()
    ws = _WsAttrappe(zeilen)

    @contextmanager
    def ohne():
        yield None
    monkeypatch.setattr(svc, "_verbindung", ohne)
    monkeypatch.setattr(svc, "get_metadata", lambda conn, sid: object())
    monkeypatch.setattr(HAStatisticsService, "_ws", property(lambda self: ws))
    return svc, ws


@pytest.mark.parametrize("sprengsatz", [False, True])
def test_ws_erste_und_letzte_zeile_gestuft(monkeypatch, sprengsatz):
    """Über WebSocket: die erste Zeile gestuft month → day → hour; ``get_stundenzeile_bis`` mit leerem 24-h-Fenster (die letzte
    Zeile liegt 200 Tage zurück) gestuft statt «alles bis t» (Lab M2: 3 Aufrufe statt 5 mit 19 776 Zeilen). Sprengsatz: nur der
    Monat von t ⇒ die Zeile im Vormonat wird nicht gefunden."""
    from backend.services import ha_statistik_rand as hr

    beginn, ende_ = datetime(2026, 1, 15, 5), datetime(2026, 4, 30, 22)
    zeilen = {e: float(i) for i, e in enumerate(range(_ep(beginn), _ep(ende_) + 1, STUNDE))}
    spaeter = _ep(datetime(2026, 11, 16, 13))            # eine Zeile kurz NACH t (12:30): Monat und Tag von t tragen sie —
    zeilen[spaeter] = 9999.0                            # die gesuchte Zeile liegt im Monat davor
    svc, ws = _ws_dienst(monkeypatch, zeilen)
    if sprengsatz:
        monkeypatch.setattr(hr, "_ws_letzte", lambda s, sid, ts: None)
    erste = hr.erste_zeile(svc, "sensor.x", float(_ep(datetime(2026, 11, 1))))
    assert erste["start_ts"] == _ep(beginn) and [p for p, _n in ws.aufrufe] == ["month", "day", "hour"]
    ws.aufrufe.clear()
    t = _ep(datetime(2026, 11, 16, 12, 30))                 # 200 Tage nach der letzten Zeile
    z = svc.get_stundenzeile_bis("sensor.x", float(t))
    if sprengsatz:
        assert z is None
        return
    assert z["start_ts"] == _ep(ende_) and z["sum"] == zeilen[_ep(ende_)]
    assert sum(n for _p, n in ws.aufrufe) < 100 and all(p != "hour" or n <= 25 for p, n in ws.aufrufe)
