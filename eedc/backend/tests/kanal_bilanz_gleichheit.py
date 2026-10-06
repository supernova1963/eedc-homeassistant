"""Baustein der Gleichheitsprobe „Adapter der Bilanz-Gruppe == heutiger Leser" (HA-Bauform E4a, Teil 1, Auftrag
Punkt 4). Die Proben stehen in ``test_kanal_bilanz_gleichheit.py`` (kein ``test``-Präfix hier, dieselbe Regel wie
``kanal_symmetrie.py``).

**Datenstände** je Form beider Abnahme-Matrizen (``pv_achse_matrix`` 23 Formen, ``achsen_matrix`` 10 Formen):

* ``HA`` — HA-Langzeitstatistik im echten Recorder-Schema, Spiegel nachgefüllt (``nachfuellen_spiegel``), Tage
  über den echten ``aggregate_day`` (01.06.–03.07.), wie ``test_kanal_symmetrie.py``.
* ``MQTT`` — eine reine MQTT-Anlage (Zuordnung leer, wie ``test_kanal_bestand_unberuehrt.py``): Rohstände in
  ``mqtt_energy_snapshots``, daraus die eigene Summe (``schreibe_eigene_summe``, Lauf täglich 21:05 und am Ende),
  die Stundenstände in ``sensor_snapshots`` so, wie ``snapshot_anlage`` sie aus denselben Rohständen schreibt (der
  Stand nächst der vollen Stunde), Tage über den echten ``aggregate_day`` ohne HA (Snapshot-Pfad). Die Rohstände
  liegen je Stunde um ``H:59`` und tragen den Stand am Ende der Stunde; ein Zähler ohne Nachtzeilen (F08) meldet in
  den Stunden, in denen er schläft, nichts — wie im HA-Datenstand.

**Was verglichen wird** (je Tag und Monat des Datenstands, Feld für Feld):

* Tag: ``komponenten_kwh`` je Schlüssel, die #406-Marken, die Regelmarke ``verworfen`` und die ``TagesBilanz`` des
  Lesers (Mengen, Gesamtverbrauch, Eigenverbrauch, Quoten, Erfasst-Marken) — Bestand = Tageszeile + Stundenzeilen
  über ``bilanz_aus_stundenrows`` wie ``tage_werte.py``.
* Monat: jedes Feld von ``TagesMonatsSumme`` (``lade_monats_summen_aus_tagen``) außer der E-Mob-Aufteilung.
* Kalendermonat je Sensor (nur HA): jedes Feld von ``SensorMonatswert`` (``get_monatswerte`` mit dem Deckel des
  Aufrufers, ``monatswert_deckel.deckel_je_sensor``).

**Toleranz.** ``komponenten_kwh`` beidseits ``round(v, 2)`` — 0,005 kWh (halbe Stufe, wie im Symmetrie-Wächter).
Bilanz und Monat entstehen beidseits aus auf 3 Stellen gerundeten Stundenwerten — 1e-6. Fassung (b) gegen (a): (b)
rundet keine Stunde; 24 Stunden × 0,0005 = 0,012 kWh je Tag, je Monat × Tage (``TOL_B_TAG``/``TOL_B_MONAT``).
"""

from __future__ import annotations

import shutil
import tempfile
import time as _zeit
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.kanal.bilanz_quellenwahl import bilanz_quellenwahl_monate, bilanz_quellenwahl_tag
from backend.services.kanal.quellenwahl import QUELLE_KANAL
from backend.services.kanal.bilanz_adapter import (
    FASSUNG_WIE_BESTAND,
    FASSUNG_WIE_HA,
    monats_summen_aus_kanaelen,
    sensor_monatswerte_aus_kanaelen,
    tage_aus_kanaelen,
)
from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

TAGE = mx.TAGE_JUNI + mx.TAGE_JULI
MONATE = ((mx.JAHR, mx.JUNI), (mx.JAHR, mx.JULI))
JETZT_TS = int(mx.JETZT.timestamp())

TOL_KOMP = 0.005 + 1e-9
TOL = 1e-6
TOL_B_TAG = 0.012 + 1e-9
TOL_B_MONAT = 0.012 * 31 + 1e-9

BILANZ_FELDER = ("erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh", "speicher_ladung_kwh", "speicher_entladung_kwh",
                 "gesamtverbrauch_kwh", "eigenverbrauch_kwh", "autarkie_prozent", "ev_quote_prozent")
BILANZ_MARKEN = ("pv_erfasst", "einspeisung_erfasst", "netzbezug_erfasst", "verbrauch_erfasst")
MONAT_FELDER = ("einspeisung_kwh", "netzbezug_kwh", "pv_module_kwh", "bkw_kwh", "speicher_ladung_kwh",
                "speicher_entladung_kwh")
MONAT_MARKEN = ("einspeisung_erfasst", "netzbezug_erfasst", "tage", "erster_tag", "letzter_tag")
MONAT_JE_GERAET = ("bkw_gemessen_je_inv", "bkw_je_inv")
#: Felder der Monatssumme, die NICHT zur Bilanz-Gruppe gehören (E-Mob-Aufteilung, U5/E4c) — gezählt, nie verglichen.
MONAT_NICHT_GRUPPE = ("emob_ladung_pv_abgeleitet_kwh", "emob_ladung_netz_abgeleitet_kwh",
                      "emob_ladung_speicher_abgeleitet_kwh")
SENSOR_FELDER = ("start_wert", "end_wert", "differenz", "verworfen_kwh", "nachtrag_kwh", "intervalle")


# ── Datenstände ─────────────────────────────────────────────────────────────


def _form(matrix: str, fid: str):
    return am.FORMEN[fid] if matrix == "achsen" else mx.FORMEN[fid]


def _pvform(matrix: str, form):
    return form.pvform if matrix == "achsen" else form


def _reihen_je_key(matrix: str, form, ids: dict[str, int]) -> dict[str, tuple[Callable, Callable]]:
    """``{sensor_key: (Rate, ohne_Zeile)}`` aller Zähler der Form, ohne Zählersprung (der steht nur in HAs ``sum``)."""
    pf = _pvform(matrix, form)
    basis = am.basis_reihen(form, mit_sprung=False) if matrix == "achsen" else {}
    out: dict[str, tuple[Callable, Callable]] = {}
    for sid, (fn, ohne, key) in mx._reihen(pf).items():
        sk = key if key.startswith("basis:") else f"inv:{ids[key]}:pv_erzeugung_kwh"
        out[sk] = (basis.get(sid, fn), ohne)
    if matrix == "achsen":
        for g in form.geraete:
            for feld, fn in g.felder.items():
                out[f"inv:{ids[g.name]}:{feld}"] = (fn, lambda _t: False)
    return out


def _mqtt_key(sensor_key: str) -> str:
    from backend.services.snapshot.keys import _BASIS_SENSOR_KEYS

    if sensor_key.startswith("basis:"):
        return _BASIS_SENSOR_KEYS[sensor_key]
    _inv, inv_id, feld = sensor_key.split(":", 2)
    return f"inv/{inv_id}/{feld}"


async def _seed_mqtt(db: AsyncSession, matrix: str, form, aid: int, ids: dict[str, int]) -> None:
    mqtt, snaps = [], []
    for sk, (fn, ohne) in _reihen_je_key(matrix, form, ids).items():
        mk, stand, t = _mqtt_key(sk), 1000.0, mx.REIHE_VON
        while t <= mx.REIHE_BIS:
            if not ohne(t - timedelta(hours=1)):
                snaps.append({"anlage_id": aid, "sensor_key": sk, "zeitpunkt": t, "wert_kwh": round(stand, 4),
                              "quelle": "mqtt_inbound"})
            if t < mx.REIHE_BIS:
                stand += fn(t)
                if not ohne(t):
                    mqtt.append({"anlage_id": aid, "energy_key": mk, "timestamp": t + timedelta(minutes=59),
                                 "value_kwh": round(stand, 4)})
            t += timedelta(hours=1)
    await db.execute(insert(MqttEnergySnapshot), mqtt)
    await db.execute(insert(SensorSnapshot), snaps)
    await db.commit()


@dataclass
class Datenstand:
    matrix: str
    fid: str
    art: str            # "HA" | "MQTT"
    db: AsyncSession
    aid: int
    ids: dict[str, int]
    svc: Any = None


@asynccontextmanager
async def datenstand(matrix: str, fid: str, art: str, *, ha_abweichung: Optional[dict] = None):
    """Seed → Kanäle → Tageszeilen; ``yield Datenstand``. Wegwerf-Datei je Lauf. ``ha_abweichung`` (nur PV-Matrix,
    HA): ``{sensor_id: (Rate | None, ohne_Zeile | None)}`` wie ``pv_achse_matrix.seed_ha``."""
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel
    from backend.services.kanal.schreiber import schreibe_eigene_summe

    verz = tempfile.mkdtemp(prefix="eedc-kanal-bilanz-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        try:
            form = _form(matrix, fid)
            pf = _pvform(matrix, form)
            if art == "HA":
                svc = am.seed_ha(form) if matrix == "achsen" else mx.seed_ha(form, abweichung=ha_abweichung)
                aid, ids = await (am.seed_anlage(db, form) if matrix == "achsen" else mx.seed_anlage(db, form))
                umgebung = am.umgebung(form, svc) if matrix == "achsen" else mx._umgebung(svc)
                with umgebung:
                    erg = await nachfuellen_spiegel(sitzungen, aid, jetzt=mx.JETZT, ha_svc=svc)
                    assert erg.fehler == 0 and erg.zeilen > 0
                    await mx.aggregiere_tage(db, pf, aid, TAGE)
            else:
                svc = mx._ha_aus()
                aid, ids = await (am.seed_anlage(db, form) if matrix == "achsen" else mx.seed_anlage(db, form))
                anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
                anlage.sensor_mapping = {"basis": {}, "investitionen": {}}
                flag_modified(anlage, "sensor_mapping")
                await db.commit()
                await _seed_mqtt(db, matrix, form, aid, ids)
                umgebung = am.umgebung(form, svc) if matrix == "achsen" else mx._umgebung(svc)
                with umgebung:
                    laeufe = [mx.REIHE_VON + timedelta(hours=1, minutes=5)]
                    tag = mx.REIHE_VON.date()
                    while tag < mx.REIHE_BIS.date():
                        laeufe.append(datetime.combine(tag, datetime.min.time()) + timedelta(hours=21, minutes=5))
                        tag += timedelta(days=1)
                    laeufe.append(mx.REIHE_BIS + timedelta(minutes=5))
                    for zp in laeufe:
                        await schreibe_eigene_summe(db, anlage, zp)
                        await db.commit()
                    await mx.aggregiere_tage(db, pf, aid, TAGE)
            yield Datenstand(matrix, fid, art, db, aid, ids, svc)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


# ── Bestand (die heutigen Leser) ────────────────────────────────────────────


@dataclass
class BestandTag:
    komponenten_kwh: dict
    pv_marken: dict
    verworfen: Optional[dict]
    bilanz: Any


async def bestand_tage(db: AsyncSession, aid: int) -> dict[date, BestandTag]:
    tz = {z.datum: z for z in (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == aid))).scalars().all()}
    tep: dict[date, list] = {}
    for r in (await db.execute(select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == aid)
                               .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde))).scalars().all():
        tep.setdefault(r.datum, []).append(r)
    out = {}
    for d in sorted(set(tz) | set(tep)):
        z = tz.get(d)
        prov = (z.source_provenance or {}) if z else {}
        marken = {k.split(".", 1)[1]: v["abgeleitet"] for k, v in prov.items()
                  if k.startswith("komponenten_kwh.") and isinstance(v, dict) and v.get("abgeleitet")}
        out[d] = BestandTag(dict((z.komponenten_kwh or {}) if z else {}), marken, z.verworfen if z else None,
                            bilanz_aus_stundenrows(tep.get(d, []), verworfen=z.verworfen if z else None))
    return out


async def bestand_monate(db: AsyncSession, aid: int) -> dict:
    from backend.services.energie_profil.monats_aus_tagen import lade_monats_summen_aus_tagen

    return await lade_monats_summen_aus_tagen(db, aid, von=MONATE[0], bis=MONATE[-1])


async def zaehler_sensoren(db: AsyncSession, aid: int) -> tuple[list[str], dict[str, float]]:
    from backend.services.monatswert_deckel import deckel_je_sensor

    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == aid))).scalars().all()
    m = anlage.sensor_mapping or {}
    sids = [c["sensor_id"] for c in (m.get("basis") or {}).values() if isinstance(c, dict) and c.get("sensor_id")]
    for inv in (m.get("investitionen") or {}).values():
        sids += [c["sensor_id"] for c in ((inv or {}).get("felder") or {}).values()
                 if isinstance(c, dict) and c.get("sensor_id")]
    return list(dict.fromkeys(sids)), deckel_je_sensor(anlage, invs)


# ── Vergleich ───────────────────────────────────────────────────────────────


@dataclass
class Bericht:
    verglichen: Counter = field(default_factory=Counter)     # je Ebene (tag/monat/sensor) Zahl der Feldvergleiche
    abweichungen: list[tuple] = field(default_factory=list)  # (ebene, wann, feld, soll, ist)
    klassen: Counter = field(default_factory=Counter)
    werte: dict = field(default_factory=dict)                 # benannte Ist-Werte (M03-Sprungtage …)
    #: je Tag/Monat die Quellenwahl der Bilanz-Gruppe: ``kanal`` oder ``bestand:<Grund je Kanal>``.
    wahl: dict = field(default_factory=dict)


def _gleich(a, b, tol) -> bool:
    if isinstance(a, dict) or isinstance(b, dict):
        if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b):
            return False
        return all(_gleich(a[k], b[k], tol) for k in a)
    if a is None or b is None or isinstance(a, (bool, str, date)) or isinstance(b, (bool, str, date)):
        return a == b
    return abs(float(a) - float(b)) <= tol


def _vergleiche(b: Bericht, ebene: str, wann, feld: str, soll, ist, tol) -> bool:
    b.verglichen[ebene] += 1
    if _gleich(soll, ist, tol):
        return True
    b.abweichungen.append((ebene, wann, feld, soll, ist))
    return False


def vergleiche_tag(b: Bericht, ebene: str, d: date, soll_komp: dict, soll_marken: dict, soll_verworfen,
                   soll_bilanz, ist, *, tol_komp=TOL_KOMP, tol=TOL, mit_verworfen=True) -> None:
    for k in sorted(set(soll_komp) | set(ist.komponenten_kwh)):
        _vergleiche(b, ebene, d, f"komponenten_kwh.{k}", soll_komp.get(k), ist.komponenten_kwh.get(k), tol_komp)
    _vergleiche(b, ebene, d, "pv_marken", soll_marken, ist.pv_marken, 0)
    if mit_verworfen:
        _vergleiche(b, ebene, d, "verworfen", soll_verworfen, ist.verworfen, 0)
    for f in BILANZ_FELDER:
        _vergleiche(b, ebene, d, f, getattr(soll_bilanz, f), getattr(ist.bilanz, f), tol)
    for f in BILANZ_MARKEN:
        _vergleiche(b, ebene, d, f, getattr(soll_bilanz, f), getattr(ist.bilanz, f), 0)


def vergleiche_monat(b: Bericht, ebene: str, m, soll, ist, *, tol=TOL, mit_belegdichte=True) -> None:
    for f in MONAT_FELDER:
        _vergleiche(b, ebene, m, f, getattr(soll, f), getattr(ist, f), tol)
    for f in MONAT_MARKEN if mit_belegdichte else MONAT_MARKEN[:2]:
        _vergleiche(b, ebene, m, f, getattr(soll, f), getattr(ist, f), 0)
    for f in MONAT_JE_GERAET:
        s, i = getattr(soll, f), getattr(ist, f)
        for k in sorted(set(s) | set(i)):
            _vergleiche(b, ebene, m, f"{f}.{k}", s.get(k), i.get(k), tol)
    for f in MONAT_NICHT_GRUPPE:
        b.klassen["monat_nicht_bilanz_gruppe"] += 1


async def probe(ds: Datenstand) -> tuple[Bericht, Bericht]:
    """(a) gegen den Bestand und (b) gegen (a) — je ein Bericht."""
    db, aid = ds.db, ds.aid
    ba, bb = Bericht(), Bericht()
    bestand = await bestand_tage(db, aid)
    ka = await tage_aus_kanaelen(db, aid, TAGE[0], TAGE[-1], fassung=FASSUNG_WIE_BESTAND, jetzt=JETZT_TS)
    kb = await tage_aus_kanaelen(db, aid, TAGE[0], TAGE[-1], fassung=FASSUNG_WIE_HA, jetzt=JETZT_TS)
    for d in TAGE:
        w = await bilanz_quellenwahl_tag(db, aid, d, jetzt=JETZT_TS)
        bb.wahl[d] = w.quelle if w.quelle == QUELLE_KANAL else "bestand:" + ",".join(
            f"{k}={g}" for k, g in sorted(w.gruende.items()))
        s = bestand.get(d)
        if s is None or d not in ka:
            ba.abweichungen.append(("tag", d, "vorhanden", s is not None, d in ka))
            continue
        vergleiche_tag(ba, "tag", d, s.komponenten_kwh, s.pv_marken, s.verworfen, s.bilanz, ka[d])
        if w.quelle != QUELLE_KANAL:
            bb.klassen["tag_quellenwahl_bestand"] += 1   # Teil 2 nimmt dort den Bestand — (b) gilt nicht
            continue
        if d not in kb:
            bb.abweichungen.append(("tag", d, "vorhanden", True, False))
            continue
        vergleiche_tag(bb, "tag", d, ka[d].komponenten_kwh, ka[d].pv_marken, None, ka[d].bilanz, kb[d],
                       tol_komp=TOL_B_TAG, tol=TOL_B_TAG, mit_verworfen=False)
        bb.klassen["b_ohne_regelmarke"] += 1   # (b) verwirft nichts: `verworfen` ist dort immer {}
    bm = await bestand_monate(db, aid)
    ma = await monats_summen_aus_kanaelen(db, aid, von=MONATE[0], bis=MONATE[-1], fassung=FASSUNG_WIE_BESTAND,
                                          jetzt=JETZT_TS)
    mb = await monats_summen_aus_kanaelen(db, aid, von=MONATE[0], bis=MONATE[-1], fassung=FASSUNG_WIE_HA,
                                          jetzt=JETZT_TS)
    wm = await bilanz_quellenwahl_monate(db, aid, MONATE[0], MONATE[-1], jetzt=JETZT_TS)
    for m in MONATE:
        bb.wahl[m] = wm[m].quelle if wm[m].quelle == QUELLE_KANAL else "bestand:" + ",".join(
            f"{k}={g}" for k, g in sorted(wm[m].gruende.items()))
        if m not in bm or m not in ma or m not in mb:
            ba.abweichungen.append(("monat", m, "vorhanden", m in bm, (m in ma, m in mb)))
            continue
        vergleiche_monat(ba, "monat", m, bm[m], ma[m])
        if wm[m].quelle != QUELLE_KANAL:
            bb.klassen["monat_quellenwahl_bestand"] += 1
            continue
        vergleiche_monat(bb, "monat", m, ma[m], mb[m], tol=TOL_B_MONAT, mit_belegdichte=False)
    if ds.art == "HA":
        sids, deckel = await zaehler_sensoren(db, aid)
        for jahr, monat in MONATE:
            soll = {w.sensor_id: w for w in ds.svc.get_monatswerte(sids, jahr, monat, deckel_je_sensor=deckel).sensoren}
            ia = {w.sensor_id: w for w in (await sensor_monatswerte_aus_kanaelen(
                db, aid, sids, jahr, monat, deckel_je_sensor=deckel, fassung=FASSUNG_WIE_BESTAND,
                jetzt=JETZT_TS)).sensoren}
            ib = {w.sensor_id: w for w in (await sensor_monatswerte_aus_kanaelen(
                db, aid, sids, jahr, monat, deckel_je_sensor=deckel, fassung=FASSUNG_WIE_HA,
                jetzt=JETZT_TS)).sensoren}
            for sid in sorted(set(soll) | set(ia)):
                if sid not in soll or sid not in ia:
                    ba.abweichungen.append(("sensor", (jahr, monat), sid, sid in soll, sid in ia))
                    continue
                for f in SENSOR_FELDER:
                    _vergleiche(ba, "sensor", (jahr, monat), f"{sid}.{f}", getattr(soll[sid], f),
                                getattr(ia[sid], f), 0)
                if sid not in ib:
                    # (b) nennt nur bei voller Abdeckung einen Wert — sonst bleibt der HA-Leser (Teil 2).
                    bb.klassen["sensor_kanal_deckt_nicht"] += 1
                    bb.werte.setdefault("sensor_kanal_deckt_nicht", []).append(((jahr, monat), sid))
                    continue
                for f in ("start_wert", "end_wert", "differenz"):
                    _vergleiche(bb, "sensor", (jahr, monat), f"{sid}.{f}", getattr(ia[sid], f),
                                getattr(ib[sid], f), 0.01 + 1e-9)
                # (b) verwirft nichts und zählt keine Zeilenpaare — benannt, nicht verglichen.
                bb.klassen["b_sensor_ohne_verworfen_nachtrag_intervalle"] += 1
    return ba, bb
