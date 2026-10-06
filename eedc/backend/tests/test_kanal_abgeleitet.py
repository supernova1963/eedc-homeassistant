"""Proben abgeleiteter Kanal „PV-Anteil der Heimladung" (HA-Bauform E4c, Auftrag Punkt 1; ``services/kanal/abgeleitet.py``).

Gegen die HA-Langzeitstatistik im echten Recorder-Schema (``ha_lts_helfer``), über den echten Spiegel-Schreiber: der
abgeleitete Kanal ``abgeleitet:inv:<id>:ladung_pv_kwh`` schreibt je Stunde ``Δ Ladung × pv_der_stunde / L`` fort — die
heutige Stundenregel (Einspeise-Deckung), gerufen, nicht nachgebaut. Gemessene Aufteilung hat Vorrang; die Wallbox-Regel
der Auswahl gilt wie im Tagespfad; eine Stunde ohne Aussage trägt keinen PV-Teil; ``aufbaubar_ab`` und Neuaufbau.

Die Zeit steht fest (``ZEIT``) — keine Probe liest die Uhr.

Schwesterdateien: test_kanal_spiegel.py (Schreiber der Eingänge), test_kanal_geraete_leser.py (Leser der E-Mob- und
Sonstiges-Gruppe), test_emob_pv_anteil.py (die Stundenregel des Bestands).
"""

from __future__ import annotations

import time as _zeit
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab, pv_der_stunde
from backend.models.kanal import FAMILIE_ABGELEITET, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal.abgeleitet import abgeleitet_key, schreibe_abgeleitete, stunde_ableiten, verwerfe_ab
from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf, schreibe_spiegel
from backend.tests import factories, ha_lts_helfer

ZEIT = datetime(2026, 6, 10, 0)
STUNDEN = 12


def _ts(dt: datetime) -> int:
    return int(_zeit.mktime(dt.timetuple()))


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


# ── Reine Funktion ──────────────────────────────────────────────────────────


def test_pv_der_stunde_ist_die_regel_des_bestands():
    """Dieselbe Zahl wie die Tagesfaltung ``leite_pv_anteil_ab`` für eine Stunde (Einspeise-Deckung N-569)."""
    for ladung, netz, einsp in ((1.0, 0.0, 1.0), (2.0, 2.0, 0.0), (4.0, 1.0, 0.0), (3.0, 2.5, 1.0), (1.0, 3.0, 0.2)):
        tag = leite_pv_anteil_ab([{"ladung": ladung, "netzbezug": netz, "einspeisung": einsp,
                                   "speicher_entladung": None}])
        assert pv_der_stunde(ladung, netz, einsp) == pytest.approx(tag.pv_kwh, abs=1e-3)
    assert pv_der_stunde(0.0, 0.0, 1.0) is None          # keine Ladung
    assert pv_der_stunde(1.0, None, 1.0) is None         # Netzbezug nicht erhoben


def test_stunde_ableiten_teilt_den_pv_teil_nach_der_ladung_der_geraete():
    # Zwei Geräte laden 1 und 3 kWh, Netzbezug 1, keine Einspeisung: PV = 3 von 4 ⇒ Anteil 0,75.
    out = stunde_ableiten({1: 1.0, 2: 3.0}, 1.0, 0.0, frozenset({1, 2}))
    assert out == {1: pytest.approx(0.75), 2: pytest.approx(2.25)}
    # Ein Gerät mit gemessener Aufteilung (2) zählt in L, bekommt aber keinen Kanal.
    assert stunde_ableiten({1: 1.0, 2: 3.0}, 1.0, 0.0, frozenset({1})) == {1: pytest.approx(0.75)}
    # Ohne Aussage (Netzbezug fehlt, ein Ladezähler ohne Zeile) ⇒ kein PV-Teil.
    assert stunde_ableiten({1: 1.0}, None, 0.0, frozenset({1})) == {1: 0.0}
    assert stunde_ableiten({1: 1.0, 2: None}, 0.0, 1.0, frozenset({1})) == {1: 0.0}
    # Keine Ladung ⇒ 0.
    assert stunde_ableiten({1: 0.0}, 0.0, 1.0, frozenset({1})) == {1: 0.0}


# ── Mit Spiegel ─────────────────────────────────────────────────────────────


def _reihe(svc, sid, rate_fn, *, start=500.0, luecken=()):
    mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True)
    wert = start
    for h in range(-3, STUNDEN + 6):
        t = ZEIT + timedelta(hours=h)
        wert += rate_fn(t)
        if h in luecken:
            continue
        ha_lts_helfer.zeile(svc, mid, t, state=wert, sum_wert=wert)


def _ladung(t):        # Wallbox lädt 2 kWh je Stunde zwischen 02:00 und 06:00
    return 2.0 if 2 <= t.hour < 6 else 0.0


def _netz(t):          # 02:00 und 03:00 vollständig aus dem Netz, 04:00/05:00 zur Hälfte
    return 2.0 if 2 <= t.hour < 4 else (1.0 if 4 <= t.hour < 6 else 0.0)


def _einsp(t):         # 04:00/05:00 dazu 0,2 eingespeist (Unschärfe der Stunde, Einspeise-Deckung)
    return 0.2 if 4 <= t.hour < 6 else 0.0


@pytest.fixture
def ha():
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    _reihe(svc, "sensor.einsp", _einsp)
    _reihe(svc, "sensor.netz", _netz)
    _reihe(svc, "sensor.wb", _ladung)
    _reihe(svc, "sensor.wb_pv", lambda t: 0.5 * _ladung(t))
    _reihe(svc, "sensor.auto", _ladung)
    return svc


async def _anlage(db, *, auto=False, wb_pv=False):
    a = await factories.anlage(db, sensor_mapping={
        "basis": {"einspeisung": _s("sensor.einsp"), "netzbezug": _s("sensor.netz")}, "investitionen": {}})
    wb = await factories.investition(db, typ="wallbox", anlage_id=a.id)
    m = dict(a.sensor_mapping)
    felder = {"ladung_kwh": _s("sensor.wb")}
    if wb_pv:
        felder["ladung_pv_kwh"] = _s("sensor.wb_pv")
    inv = {str(wb.id): {"felder": felder}}
    ea = None
    if auto:
        ea = await factories.investition(db, typ="e-auto", anlage_id=a.id)
        inv[str(ea.id)] = {"felder": {"ladung_kwh": _s("sensor.auto")}}
    m["investitionen"] = inv
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return a, wb, ea


async def _laeufe(db, anlage, svc, stunden, *, ab_ts=None):
    for h in stunden:
        t = ZEIT + timedelta(hours=h)
        await schreibe_spiegel(db, anlage, t, ha_svc=svc)
        await schreibe_abgeleitete(db, anlage, t, ab_ts=ab_ts)
        await db.commit()


async def _abgeleitet(db, anlage_id, inv_id) -> tuple[Kanal | None, dict[int, float]]:
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id,
                                              Kanal.key == abgeleitet_key(inv_id)))).scalar_one_or_none()
    if k is None:
        return None, {}
    rows = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()
    return k, {r.start_ts: r.sum for r in rows}


async def test_stunden_regel_schreibt_den_pv_teil_kumulativ(db, ha):
    """02:00/03:00 aus dem Netz (PV 0); 04:00/05:00 Netzbezug 1, Einspeisung 0,2 ⇒ PV = min(2, (2 − 1) + 0,2) = 1,2.
    Der Kanal beginnt mit der ersten Stunde, deren Eingänge eine Zeile MIT Vorstand haben (der Spiegel beginnt beim
    ersten Lauf mit 00:00 ohne Vorstand ⇒ 01:00), danach je Lauf fortgeschrieben — Summe 2,4 nach 06:00."""
    a, wb, _ = await _anlage(db)
    # Der Spiegel braucht einen Stand vor der ersten Stunde (Vorlauf 00:00–02:00); die Ableitung beginnt beim ersten
    # Lauf mit der eben abgeschlossenen Stunde.
    await _laeufe(db, a, ha, range(1, 8))
    k, z = await _abgeleitet(db, a.id, wb.id)
    assert k is not None and k.aufbaubar_ab == _ts(ZEIT + timedelta(hours=1))
    assert z[_ts(ZEIT + timedelta(hours=3))] == pytest.approx(0.0)
    assert z[_ts(ZEIT + timedelta(hours=4))] == pytest.approx(1.2)
    assert z[_ts(ZEIT + timedelta(hours=6))] == pytest.approx(2.4)
    q = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()
    assert [(x.familie, x.gueltig_ab) for x in q] == [(FAMILIE_ABGELEITET, _ts(ZEIT + timedelta(hours=1)))]


async def test_ab_ts_setzt_den_fruehesten_anfang_eines_neuen_kanals(db, ha):
    """``ab_ts`` ist die früheste Stunde; geschrieben wird ab der ersten mit Vorstand aller Eingänge (01:00)."""
    a, wb, _ = await _anlage(db)
    await _laeufe(db, a, ha, [1, 7], ab_ts=_ts(ZEIT - timedelta(hours=1)))
    k, z = await _abgeleitet(db, a.id, wb.id)
    assert k.aufbaubar_ab == _ts(ZEIT + timedelta(hours=1))
    assert sorted(z) == [_ts(ZEIT + timedelta(hours=h)) for h in range(1, 7)]
    assert z[max(z)] == pytest.approx(2.4)


async def test_gemessene_aufteilung_hat_vorrang(db, ha):
    """Eine Wallbox mit zugeordnetem ``ladung_pv_kwh`` bekommt keinen abgeleiteten Kanal (Rahmenbedingung 1)."""
    a, wb, _ = await _anlage(db, wb_pv=True)
    await _laeufe(db, a, ha, range(1, 8))
    k, _z = await _abgeleitet(db, a.id, wb.id)
    assert k is None


async def test_wallbox_regel_das_auto_neben_der_wallbox_traegt_keinen_kanal(db, ha):
    """Neben einer Wallbox mit Ladezähler zählen die Heimlade-Felder des Autos am Tag nicht (N-196) — die Ableitung
    nimmt dieselbe Auswahl: nur die Wallbox, ihre Ladung allein in L (sonst halbierte die doppelte Ladung den Anteil)."""
    a, wb, ea = await _anlage(db, auto=True)
    await _laeufe(db, a, ha, range(1, 8))
    _k, z = await _abgeleitet(db, a.id, wb.id)
    assert z[max(z)] == pytest.approx(2.4)
    k_auto, _ = await _abgeleitet(db, a.id, ea.id)
    assert k_auto is None


async def test_stunde_ohne_aussage_traegt_keinen_pv_teil(db):
    """Fehlt dem Netzbezug die Zeile 04:00 (seine Menge steht in 05:00, Spanne 2 h), sind 04:00 UND 05:00 ohne Aussage
    — der Stand bleibt, die Ladung dieser Stunden zählt nicht als PV (benannte Abweichung zum Bestand)."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    _reihe(svc, "sensor.einsp", _einsp)
    _reihe(svc, "sensor.netz", _netz, luecken=(4,))
    _reihe(svc, "sensor.wb", _ladung)
    _reihe(svc, "sensor.wb_pv", lambda t: 0.0)
    _reihe(svc, "sensor.auto", lambda t: 0.0)
    a, wb, _ = await _anlage(db)
    await _laeufe(db, a, svc, range(1, 8))
    _k, z = await _abgeleitet(db, a.id, wb.id)
    assert z[_ts(ZEIT + timedelta(hours=5))] == pytest.approx(0.0)
    assert z[_ts(ZEIT + timedelta(hours=6))] == pytest.approx(0.0)      # 06:00 lädt nicht mehr


async def test_verwerfen_und_neuaufbau_aendern_nichts_vor_aufbaubar_ab(db, ha):
    a, wb, _ = await _anlage(db)
    await _laeufe(db, a, ha, [1], ab_ts=_ts(ZEIT + timedelta(hours=2)))
    await _laeufe(db, a, ha, range(2, 8))
    k, vorher = await _abgeleitet(db, a.id, wb.id)
    assert k.aufbaubar_ab == _ts(ZEIT + timedelta(hours=1)) == min(vorher)   # ab_ts lag hinter dem Lauf ⇒ kein Kanal
    n = await verwerfe_ab(db, a.id, _ts(ZEIT - timedelta(hours=5)))      # vor aufbaubar_ab: Grenze ist aufbaubar_ab
    await db.commit()
    assert n == len(vorher)
    await _laeufe(db, a, ha, [7])
    _k, nachher = await _abgeleitet(db, a.id, wb.id)
    assert nachher == pytest.approx(vorher)


async def test_stundenlauf_schreibt_den_abgeleiteten_kanal_nach_dem_spiegel(db, ha):
    from unittest.mock import patch

    import backend.services.ha_statistics_service as hss

    a, wb, _ = await _anlage(db)
    with patch.object(hss, "_ha_statistics_service", ha):
        for h in range(1, 8):
            assert await schreibe_kanaele_im_stundenlauf(db, a, ZEIT + timedelta(hours=h)) is not None
            await db.commit()
    _k, z = await _abgeleitet(db, a.id, wb.id)
    assert z[max(z)] == pytest.approx(2.4)


async def test_konsistenzlauf_verwirft_den_abgeleiteten_kanal_ab_der_korrektur(db, ha):
    """Korrigiert der Konsistenzlauf den Spiegel ab einer Stunde, verwirft er den abgeleiteten Kanal ab derselben
    Stunde (nie davor) — der nächste Stundenlauf schreibt ihn aus dem neuen Spiegel."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, patch

    from backend.services.kanal import konsistenz

    a, wb, _ = await _anlage(db)
    await _laeufe(db, a, ha, range(1, 8))
    _k, vorher = await _abgeleitet(db, a.id, wb.id)
    t0 = _ts(ZEIT + timedelta(hours=4))

    @asynccontextmanager
    async def sitzungen():
        yield db
        await db.commit()

    with patch.object(konsistenz, "_pruefe_abschnitt", new=AsyncMock(return_value=t0)), \
            patch.object(konsistenz, "neu_spiegeln", new=AsyncMock(return_value=1)):
        erg = await konsistenz.konsistenz_anlage(sitzungen, a.id, ha_svc=ha)
    assert erg.korrigiert
    _k, nachher = await _abgeleitet(db, a.id, wb.id)
    assert sorted(nachher) == sorted(t for t in vorher if t < t0)
    await _laeufe(db, a, ha, [7])
    _k, wieder = await _abgeleitet(db, a.id, wb.id)
    assert wieder == pytest.approx(vorher)


async def test_update_mitten_im_monat_der_kanal_beginnt_mit_dem_laufenden_monat():
    """H-2 (Entscheid Master 06.10.2026): ein Update am 04.07. (Spiegel nachgefüllt, noch kein abgeleiteter Kanal) — der
    erste Lauf baut den Kanal ab Beginn des laufenden Monats (eine Stunde vor dem Monatsfenster: 30.06. 22:00).
    Cockpit → Monat nennt den Juli mit der Aufteilung aus dem Kanal (9,0 kWh Sonne), der Juni bleibt beim Bestand."""
    from sqlalchemy import delete

    from backend.models.anlage import Anlage
    from backend.services.kanal.geraete_leser import geraete_monate
    from backend.services.kanal.quellenwahl import QUELLE_BESTAND
    from backend.tests import achsen_matrix as am
    from backend.tests import kanal_bilanz_gleichheit as kg
    from backend.tests import pv_achse_matrix as mx

    form = am.MATRIX_FORMEN["M02"]
    async with kg.datenstand("achsen", "M02", "HA") as ds:
        alt = [k.id for k in (await ds.db.execute(select(Kanal).where(
            Kanal.anlage_id == ds.aid, Kanal.key.like("abgeleitet:%")))).scalars().all()]
        assert alt                                                 # der Seed hatte ihn — „vor dem Update" ohne
        for tab in (KanalStatistik, KanalQuelle):
            await ds.db.execute(delete(tab).where(tab.kanal_id.in_(alt)))
        await ds.db.execute(delete(Kanal).where(Kanal.id.in_(alt)))
        await ds.db.commit()
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        with am.umgebung(form, ds.svc):
            assert await schreibe_abgeleitete(ds.db, anlage, mx.JETZT) > 0
            await ds.db.commit()
            k, z = await _abgeleitet(ds.db, ds.aid, ds.ids["Wallbox"])
            g = await geraete_monate(ds.db, ds.aid, von=(2026, 6), bis=(2026, 7))
            juli = await am.miss_cockpit_monat(ds.db, ds.aid, ds.ids, 7)
    assert k.aufbaubar_ab == _ts(datetime(2026, 6, 30, 22)) == min(z)
    assert g[(2026, 7)].emob.kanal and g[(2026, 7)].emob.quote == pytest.approx(1.0)
    assert g[(2026, 6)].emob.wahl.quelle == QUELLE_BESTAND        # kein abgeschlossener Monat aus dem Kanal
    assert juli["emob_ladung_pv_kwh"] == pytest.approx(9.0)
    assert not juli.get("emob_ladung_netz_kwh")
