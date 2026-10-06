"""Zweite Abnahme-Matrix (Netz · Speicher · Wärmepumpe · E-Mobilität · Sonstiges · Preis) — Baustein.

Die Proben stehen in ``test_achsen_matrix.py``; dieses Modul ist ihr Baustein (kein ``test``-Präfix,
dieselbe Regel wie in ``ha_lts_helfer.py`` und ``pv_achse_matrix.py``).

**Warum es diese Matrix gibt (Auftrag Fable-Master 05.10.2026, ``plans/auftrag-achsen-matrix-2.md``).**
Vor dem Umbau der Datenbasis („HA-Bauform", S1 + S2) hält sie Zelle für Zelle fest, welche Zahl jede
Sicht HEUTE für die Größen nennt, die nicht PV sind. Der Umbau tauscht nur Eingangsfelder; wird danach
eine grüne Zelle rot, war es der Umbau.

**Produktiver Datenstand — dieselbe Bauform wie die PV-Matrix** (``pv_achse_matrix.py``, deren Seed,
Umgebung, Tageslauf und Sammelimport hier wiederverwendet werden): HA-Langzeitstatistik im Recorder-
Schema (``ha_lts_helfer``), echter ``HAStatisticsService``, Tageszeilen über den echten ``aggregate_day``,
der abgeschlossene Juni über die echten Schreibwege S1 („Aus HA laden" → Formular-Nutzlast →
``create_monatsdaten``), S2 (HA-Statistik-Sammelimport), S3 (Handeingabe ohne HA, Snapshot-Pfad).
Jede Form trägt eine PV-Seite aus der PV-Matrix, deren Zellen dort über alle fünf Wege grün sind
(``F14``: Gesamtzähler + Süd gemessen, West ohne Zähler; ``F03`` für die Form mit Balkonkraftwerk).

**Was von außen kommt und wie es gesät wird.**

* Ein **Preissensor** (Flex-Tarif) ist in HA ein Messwert: die Recorder-Statistik trägt ihn als
  Stunden-``mean`` (``get_hourly_mean_for_day``) — gesät mit ``ha_lts_helfer.zeile(mean=…)``.
  Der Börsenpreis (aWATTar, Netz) bleibt gestubbt (leer), wie in der PV-Matrix.
* Ein **Betriebsart-Etikett** (``climate``-Zustand) hat in HA keine Langzeitstatistik; eedc liest es
  aus dem Zustands-Verlauf (``ha_state_service.get_zustand_history``, ``_get_betriebsmodus_history``).
  Der vorhandene Helfer reichte dafür nicht — ``ha_lts_helfer.ZustandsVerlauf`` (neu, additiv) stellt
  einen ``HAStateService`` mit genau diesem Verlauf bereit. Dieselbe Attrappe macht HA für den
  Preissensor „erreichbar" (``_get_strompreis_stunden`` fragt ``get_ha_state_service().is_available``).
  Sie wird NUR in Formen mit Preissensor oder Etikett eingehängt; die übrigen laufen wie die PV-Matrix.

**Die Uhr** ist die der PV-Matrix: ``JETZT`` = 04.07.2026 00:30 (Juli läuft, drei Tage vorbei).
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
import time as _zeit
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, patch

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition, Strompreis
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests import ha_lts_helfer
from backend.tests import pv_achse_matrix as mx

JAHR, JUNI, JULI, JETZT = mx.JAHR, mx.JUNI, mx.JULI, mx.JETZT
TAGE_JUNI, TAGE_JULI = mx.TAGE_JUNI, mx.TAGE_JULI
PROD = mx.PROD_STUNDEN          # 10–15 Uhr (sechs Stunden)
NETZ_NACHT = mx.NETZ_NACHT      # 0,4 kWh je Stunde außerhalb der Sonne

RateFn = Callable[[datetime], float]


# ── Stundenraten ────────────────────────────────────────────────────────────


def stunden(rate: float, von: int, bis: int) -> RateFn:
    """``rate`` kWh je Stunde in den Stunden ``von`` … ``bis − 1`` (Stunde t = Intervall [t, t+1))."""
    return lambda t: rate if von <= t.hour < bis else 0.0


def immer(rate: float) -> RateFn:
    return lambda _t: rate


def null(_t) -> float:
    return 0.0


def summe(*fns: RateFn) -> RateFn:
    return lambda t: sum(f(t) for f in fns)


def menge(fn: RateFn, tage) -> float:
    """Σ der Rate über die Stunden der Tage (Stunde t gehört dem Tag von t)."""
    return round(sum(fn(datetime.combine(d, datetime.min.time()) + timedelta(hours=h))
                     for d in tage for h in range(24)), 6)


def netz_basis(t: datetime) -> float:
    return 0.0 if t.hour in PROD else NETZ_NACHT


def einsp_basis(t: datetime) -> float:
    return 1.0 if t.hour in PROD else 0.0


# ── Formen ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Geraet:
    """Eine Investition, die nicht PV ist. ``felder``: ``{feld: Rate}`` der zugeordneten Zähler.
    ``live``: der ``live``-Block der Zuordnung (Betriebsart-Etikett)."""

    name: str
    typ: str
    felder: dict
    parameter: Optional[dict] = None
    parent: Optional[str] = None          # Name eines Geräts derselben Form oder des PV-Balkonkraftwerks
    live: Optional[dict] = None
    #: S3: was der Anwender von Hand einträgt (``None`` = die Monatsmenge der Zähler).
    hand: Optional[dict] = None
    #: HA-Bauform E4a-2 (Form W2-E): ``{feld: ohne_Zeile(t)}`` — Stunden, für die der Zähler keine Zeile hat (HA und
    #: Standalone); die Menge steht in der nächsten Zeile.
    ohne: dict = field(default_factory=dict, compare=False)

    def sid(self, feld: str) -> str:
        return f"sensor.{self.name.lower().replace(' ', '_').replace('-', '_')}_{feld}"


@dataclass(frozen=True)
class Form:
    fid: str
    titel: str
    groessen: tuple[str, ...]
    ausp: tuple[str, ...]                 # Ausprägungen des Auftrags (N1 … T3)
    pv: str = "F14"                       # PV-Seite: eine Form der PV-Matrix
    geraete: tuple[Geraet, ...] = ()
    netz: RateFn = netz_basis
    einsp: RateFn = einsp_basis
    #: Abweichende Statistik-Reihe (Zählersprung) je Sensor: ``{sensor_id: Rate}`` — gilt für HA und SA.
    sprung: dict = field(default_factory=dict)
    tarif: str = "fix"                    # fix · flex_sensor · flex_gepflegt
    #: Preis je Stunde in ct/kWh (Preissensor), ``None`` = kein Sensor.
    preis: Optional[Callable[[int], float]] = None
    gepflegt_cent: Optional[float] = None
    #: Betriebsart-Verlauf ``{entity: [(zeitpunkt, roher_zustand)]}``.
    zustaende: dict = field(default_factory=dict)

    @property
    def pvform(self) -> mx.Form:
        return mx.MATRIX_FORMEN[self.pv]

    @property
    def w2(self) -> bool:
        return self.fid.startswith("W2-")

    @property
    def ha_zustand(self) -> bool:
        return bool(self.zustaende) or self.preis is not None

    def geraet(self, name: str) -> Geraet:
        return next(g for g in self.geraete if g.name == name)

    def typ(self, typ: str) -> list[Geraet]:
        return [g for g in self.geraete if g.typ == typ]


#: Preis des Flex-Sensors: 50 ct von 11 bis 14 Uhr, sonst 25 ct. Bezug fließt nur außerhalb der
#: Sonne (10–15 Uhr) — der bezugsgewichtete Ø ist 25 ct, der arithmetische 29,17 ct; um eine Stunde
#: verschoben bleibt beides gleich (die Ränder liegen in bezugsfreien Stunden).
def preis_flex(h: int) -> float:
    return 50.0 if 11 <= h < 15 else 25.0


STAMM_CENT = 30.0
EINSP_CENT = 8.0
GEPFLEGT_CENT = 33.0


def _zustand_ww(tage) -> list:
    """Wärmepumpen-Etikett: Heizen, je Tag 06:00–08:00 Warmwasser (zwei Stunden)."""
    pts = [(datetime(2026, 5, 30, 0, 0), "heat")]
    for d in tage:
        pts.append((datetime.combine(d, datetime.min.time()) + timedelta(hours=6), "warmwasser"))
        pts.append((datetime.combine(d, datetime.min.time()) + timedelta(hours=8), "heat"))
    return pts


#: Netzbezug mit Netzladung des Akkus (02–04 Uhr, 0,5 kWh je Stunde zusätzlich).
def _netz_mit_netzladung(t):
    return netz_basis(t) + (0.5 if 2 <= t.hour < 4 else 0.0)


def _sprung(basis: RateFn, wann: tuple[datetime, ...], kwh: float, *, nacht_still: bool = True) -> RateFn:
    """Zählersprung N3: in der Stunde ``wann`` springt ``sum`` um ``kwh``; davor eine Nacht ohne Zuwachs
    (die Basis liefert nachts ohnehin 0)."""
    sprung = set(wann)
    return lambda t: basis(t) + (kwh if t in sprung else 0.0)


#: Der Sprung: je ein Tag im Juni und im Juli, in der ersten Ertragsstunde nach der Nacht.
SPRUNG_ZEITEN = (datetime(2026, 6, 15, 10), datetime(2026, 7, 2, 10))
#: Größe: über dem Tagesdeckel, unter dem Monatsdeckel (gemessen, Bericht Etappe 2).
SPRUNG_KWH = 250.0


FORMEN: dict[str, Form] = {f.fid: f for f in (
    Form("M01", "Kontrollform: PV, Bezug + Einspeisung, fester Tarif", ("netz", "preis"), ("N1", "T1")),
    Form("M02", "Netzbezug flach (gemessene 0), ein Speicher, Wallbox allein", ("netz", "speicher", "emob", "preis"),
         ("N2", "P1", "E1", "T1"),
         geraete=(
             Geraet("Akku", "speicher", {"ladung_kwh": stunden(0.5, 10, 16), "entladung_kwh": stunden(0.4, 18, 23)},
                    parameter={"kapazitaet_kwh": 10.0}),
             Geraet("Wallbox", "wallbox", {"ladung_kwh": stunden(1.0, 11, 14)}),
         ),
         netz=null),
    Form("M03", "Zählersprung auf Einspeisung und PV-Gesamtzähler", ("netz", "preis"), ("N3", "T1"),
         sprung={"sensor.einsp": _sprung(einsp_basis, SPRUNG_ZEITEN, SPRUNG_KWH),
                 "sensor.pv_gesamt": _sprung(lambda t: 3.0 if t.hour in PROD else 0.0, SPRUNG_ZEITEN, SPRUNG_KWH)}),
    Form("M04", "zwei Speicher, einer mit Netzladung, Flex-Tarif mit Preissensor", ("netz", "speicher", "preis"),
         ("P2", "P3", "T2"),
         geraete=(
             Geraet("Akku A", "speicher", {
                 "ladung_kwh": summe(stunden(0.5, 10, 16), stunden(0.5, 2, 4)),
                 "entladung_kwh": stunden(0.4, 18, 23),
                 "ladung_netz_kwh": stunden(0.5, 2, 4)}, parameter={"kapazitaet_kwh": 10.0}),
             Geraet("Akku B", "speicher", {"ladung_kwh": stunden(0.25, 10, 16), "entladung_kwh": stunden(0.25, 19, 23)},
                    parameter={"kapazitaet_kwh": 5.0}),
         ),
         netz=_netz_mit_netzladung, tarif="flex_sensor", preis=preis_flex),
    Form("M05", "Wärmepumpe: Gesamtstrom + Wärmezähler, Betriebsart als Etikett (Heizen/Warmwasser)",
         ("netz", "wp", "preis"), ("W1", "T1"),
         geraete=(
             Geraet("WP", "waermepumpe", {"stromverbrauch_kwh": immer(0.3), "waerme_kwh": immer(0.9)},
                    parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0},
                    live={"betriebsmodus": "climate.wp"}),
         ),
         zustaende={"climate.wp": _zustand_ww(TAGE_JUNI + TAGE_JULI)}),
    Form("M06", "zwei Geräte: getrennte Strommessung Heizen/Warmwasser + Klima mit Betriebsart-Zählern",
         ("netz", "wp", "preis"), ("W2", "W3", "W4", "T1"),
         geraete=(
             Geraet("WP HW", "waermepumpe", {
                 "strom_heizen_kwh": immer(0.25), "strom_warmwasser_kwh": immer(0.05),
                 "heizenergie_kwh": immer(0.75), "warmwasser_kwh": immer(0.15)},
                 parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0,
                            "getrennte_strommessung": True}),
             Geraet("Klima", "waermepumpe", {
                 "betriebsart_strom_heizen_kwh": stunden(0.1, 0, 6),
                 "betriebsart_strom_kuehlen_kwh": stunden(0.2, 11, 17),
                 "betriebsart_nutzenergie_heizen_kwh": stunden(0.3, 0, 6),
                 "betriebsart_nutzenergie_kuehlen_kwh": stunden(0.6, 11, 17)},
                 parameter={"wp_art": "luft_luft", "alter_energietraeger": "strom", "alter_preis_cent_kwh": 30.0}),
         )),
    Form("M07", "Wärmepumpe ohne Betrieb (Strom 0, Wärme 0 gemessen) + Sonstiges mit Alt- und Neuname",
         ("netz", "wp", "sonstiges", "preis"), ("W5", "S3", "T1"),
         geraete=(
             Geraet("WP still", "waermepumpe", {"stromverbrauch_kwh": null, "waerme_kwh": null},
                    parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0}),
             Geraet("Pool", "sonstiges", {"verbrauch_sonstig_kwh": immer(0.1), "verbrauch_kwh": immer(0.15)},
                    parameter={"kategorie": "verbraucher"}),
         )),
    Form("M08", "Wallbox + E-Auto (Wallbox-Regel), Flex-Tarif mit gepflegtem Monats-Ø", ("netz", "emob", "preis"),
         ("E2", "T3"),
         geraete=(
             Geraet("Wallbox", "wallbox", {"ladung_kwh": stunden(1.0, 11, 14)}),
             Geraet("E-Auto", "e-auto", {"ladung_kwh": stunden(1.0, 11, 14)}),
         ),
         tarif="flex_gepflegt", preis=preis_flex, gepflegt_cent=GEPFLEGT_CENT),
    Form("M09", "E-Auto ohne Wallbox mit PV-/Netz-Ladung + Dienstwagen", ("netz", "emob", "preis"),
         ("E3", "E4", "T1"),
         geraete=(
             Geraet("Privat", "e-auto", {"ladung_pv_kwh": stunden(0.5, 12, 14), "ladung_netz_kwh": stunden(0.5, 20, 22)}),
             Geraet("Dienst", "e-auto", {"ladung_pv_kwh": stunden(0.5, 13, 15), "ladung_netz_kwh": stunden(0.5, 21, 23)},
                    parameter={"ist_dienstlich": True}),
         )),
    Form("M10", "Akku am Balkonkraftwerk + Sonstiges-Erzeuger hinter dem Zähler + Sonstiges-Verbraucher",
         ("netz", "speicher", "sonstiges", "preis"), ("P4", "S1", "S2", "T1"), pv="F03",
         geraete=(
             Geraet("BKW-Akku", "speicher", {"ladung_kwh": stunden(0.2, 10, 16), "entladung_kwh": stunden(0.15, 18, 22)},
                    parameter={"kapazitaet_kwh": 2.0}, parent="Balkon"),
             Geraet("BHKW", "sonstiges", {"erzeugung_kwh": immer(0.25)}, parameter={"kategorie": "erzeuger"}),
             Geraet("Sauna", "sonstiges", {"verbrauch_sonstig_kwh": stunden(0.2, 18, 22)},
                    parameter={"kategorie": "verbraucher"}),
         )),
)}


# ── Neue Form nach Weg 2 (HA-Bauform E4a-2, Auftrag Punkt 6) ────────────────
#
# Vorlage ``probe-weg2/neue_formen.py`` (Form E). Ein Sonstiges-Erzeuger (BHKW) mit zwei Zählern EINER Ersatzgruppe
# (``sonstiges_feld_reihenfolge('erzeuger')``: ``erzeugung_kwh`` vor ``verbrauch_sonstig_kwh``): A 0,25 kWh je Stunde,
# B 0,26 (zweites Messgerät, +4 %). A hat für die 24 Stunden des Tagesfensters 10.06. keine Zeile; seine Menge steht in
# der Folgezeile. Steht NICHT in ``FORMEN`` (andere Proben iterieren sie), sondern in ``FORMEN_W2``.

E_AUSFALL = (datetime(2026, 6, 9, 23), datetime(2026, 6, 10, 23))

FORMEN_W2: dict[str, Form] = {f.fid: f for f in (
    Form("W2-E", "Sonstiges-Erzeuger mit zwei Zählern einer Ersatzgruppe, A ohne Zeilen im Tagesfenster 10.06.",
         ("netz", "sonstiges"), ("S1",), pv="F14",
         geraete=(Geraet("BHKW", "sonstiges", {"erzeugung_kwh": immer(0.25), "verbrauch_sonstig_kwh": immer(0.26)},
                         parameter={"kategorie": "erzeuger"},
                         ohne={"erzeugung_kwh": lambda t: E_AUSFALL[0] <= t < E_AUSFALL[1]}),)),
)}

#: Alle Formen der Abnahme-Matrix.
MATRIX_FORMEN: dict[str, Form] = {**FORMEN, **FORMEN_W2}


def w2_menge(fn: RateFn, ohne: Optional[Callable], tage) -> float:
    """Weg 2 als Soll: Δ eines Zählers über die Tagesfenster ``tage`` (``[Vortag 23:00, 23:00)``) wie die Lese-Schicht
    — Stand vor dem Ende minus Stand vor dem Anfang; fehlende Zeilen tragen nichts, ihre Menge steht in der nächsten
    vorhandenen (Lückentag wie HA). Unabhängig vom Produktcode."""
    von = datetime.combine(tage[0], datetime.min.time()) - timedelta(hours=1)
    bis = datetime.combine(tage[-1], datetime.min.time()) + timedelta(hours=23)
    stand, vor_von, vor_bis, t = 0.0, None, None, mx.REIHE_VON
    while t < mx.REIHE_BIS:
        stand += fn(t)
        if not (ohne and ohne(t)):
            if t + timedelta(hours=1) <= von:
                vor_von = stand
            if t + timedelta(hours=1) <= bis:
                vor_bis = stand
        t += timedelta(hours=1)
    return round((vor_bis or 0.0) - (vor_von or 0.0), 6)


# ── Seed ────────────────────────────────────────────────────────────────────


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def basis_reihen(form: Form, *, mit_sprung: bool = True) -> dict[str, RateFn]:
    """Die Raten der Basis- und PV-Zähler dieser Form. Der Zählersprung (N3) steht nur in HAs
    ``sum`` (Fall N-586, ``mit_sprung``); die Standalone-Zählerstände und die Handeingabe tragen ihn nicht."""
    pf = form.pvform
    r: dict[str, RateFn] = {"sensor.einsp": form.einsp, "sensor.netz": form.netz}
    for sid, (fn, _ohne, _key) in mx._reihen(pf).items():
        if sid not in ("sensor.einsp", "sensor.netz"):
            r[sid] = fn
    if mit_sprung:
        r.update(form.sprung)
    return r


async def seed_anlage(db: AsyncSession, form: Form) -> tuple[int, dict[str, int]]:
    """PV-Seite über ``pv_achse_matrix.seed_anlage``, dazu Tarif, Geräte und deren Zuordnung."""
    aid, ids = await mx.seed_anlage(db, form.pvform)
    tarif = (await db.execute(select(Strompreis).where(Strompreis.anlage_id == aid))).scalar_one()
    if form.tarif != "fix":
        tarif.vertragsart = "dynamisch"
    for g in form.geraete:
        kw: dict[str, Any] = dict(anlage_id=aid, typ=g.typ, bezeichnung=g.name, anschaffungsdatum=mx.D0,
                                  anschaffungskosten_gesamt=1000.0,
                                  parent_investition_id=ids.get(g.parent) if g.parent else None)
        if g.parameter:
            kw["parameter"] = dict(g.parameter)
        inv = Investition(**kw)
        db.add(inv)
        await db.flush()
        ids[g.name] = inv.id
    a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    m = dict(a.sensor_mapping)
    inv_map = dict(m.get("investitionen") or {})
    for g in form.geraete:
        eintrag: dict[str, Any] = {"felder": {f: _s(g.sid(f)) for f in g.felder}}
        if g.live:
            eintrag["live"] = dict(g.live)
        inv_map[str(ids[g.name])] = eintrag
    m["investitionen"] = inv_map
    if form.preis is not None:
        m["basis"] = {**m["basis"], "strompreis": _s("sensor.strompreis")}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return aid, ids


def seed_ha(form: Form):
    """Die HA-Langzeitstatistik: Basis- und PV-Zähler (``pv_achse_matrix.seed_ha`` mit den Raten dieser
    Form), Gerätezähler, Preissensor als Stunden-``mean``."""
    abw = {sid: (fn, None) for sid, fn in basis_reihen(form).items()}
    svc = mx.seed_ha(form.pvform, abweichung=abw)
    for g in form.geraete:
        for feld, fn in g.felder.items():
            _zaehler_reihe(svc, g.sid(feld), fn, g.ohne.get(feld))
    if form.preis is not None:
        mid = ha_lts_helfer.sensor(svc, "sensor.strompreis", "ct/kWh", has_sum=False)
        zeilen, t = [], mx.REIHE_VON
        while t < mx.REIHE_BIS:
            zeilen.append({"m": mid, "t": _zeit.mktime(t.timetuple()), "w": form.preis(t.hour)})
            t += timedelta(hours=1)
        with svc._engine.begin() as conn:
            conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, mean, min, max) "
                              "VALUES (:m, :t, :w, :w, :w)"), zeilen)
    return svc


def _zaehler_reihe(svc, sid: str, fn: RateFn, ohne: Optional[Callable] = None) -> None:
    mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True)
    stand, zeilen, t = 500.0, [], mx.REIHE_VON
    while t < mx.REIHE_BIS:
        stand += fn(t)
        if ohne is not None and ohne(t):
            t += timedelta(hours=1)
            continue
        zeilen.append({"m": mid, "t": _zeit.mktime(t.timetuple()), "w": round(stand, 4)})
        t += timedelta(hours=1)
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                     zeilen)


async def seed_snapshots(db: AsyncSession, form: Form, aid: int, ids: dict[str, int]) -> None:
    """Standalone: stündliche Zählerstände in ``sensor_snapshots`` (wie ``pv_achse_matrix.seed_snapshots``)."""
    reihen: dict[str, RateFn] = {}
    for sid, (fn, _ohne, key) in mx._reihen(form.pvform).items():
        sk = key if key.startswith("basis:") else f"inv:{ids[key]}:pv_erzeugung_kwh"
        reihen[sk] = basis_reihen(form, mit_sprung=False).get(sid, fn)
    ohne_je: dict[str, Callable] = {}
    for g in form.geraete:
        for feld, fn in g.felder.items():
            reihen[f"inv:{ids[g.name]}:{feld}"] = fn
            if feld in g.ohne:
                ohne_je[f"inv:{ids[g.name]}:{feld}"] = g.ohne[feld]
    zeilen = []
    for sk, fn in reihen.items():
        stand, t = 1000.0, mx.REIHE_VON
        while t <= mx.REIHE_BIS:
            if sk in ohne_je and ohne_je[sk](t - timedelta(hours=1)):   # E4a-2 (W2-E): keine Zeile
                stand += fn(t)
                t += timedelta(hours=1)
                continue
            zeilen.append({"anlage_id": aid, "sensor_key": sk, "zeitpunkt": t, "wert_kwh": round(stand, 4),
                           "quelle": "mqtt_inbound"})
            stand += fn(t)
            t += timedelta(hours=1)
    await db.execute(insert(SensorSnapshot), zeilen)
    await db.commit()


def umgebung(form: Form, svc) -> ExitStack:
    """Wie ``pv_achse_matrix._umgebung`` — bei Preissensor ohne den Stub des Stundenpreises (der echte
    ``_get_strompreis_stunden`` liest den Sensor aus der Statistik, die Börse bleibt leer) und mit der
    Zustands-Attrappe, wo die Form ein Etikett oder einen Preissensor trägt."""
    import backend.api.routes.aktueller_monat as am
    import backend.services.ha_statistics_service as hss

    st = ExitStack()
    st.enter_context(patch.object(hss, "_ha_statistics_service", svc))
    st.enter_context(patch.object(am, "datetime", mx._FesteUhr))
    # E4a-2: die Uhr der Kanal-Leser ist dieselbe gestellte Uhr.
    st.enter_context(patch("backend.services.kanal.bilanz_leser.uhr", lambda: int(mx.JETZT.timestamp())))
    if form.preis is None or not svc.is_available:
        from backend.services.energie_profil._helpers import StrompreisStunden
        st.enter_context(patch(
            "backend.services.energie_profil._helpers._get_strompreis_stunden",
            new=AsyncMock(return_value=StrompreisStunden(sensor={}, boerse={})),
        ))
    else:
        st.enter_context(patch("backend.services.strompreis_markt_service.get_strompreis_stunden",
                               new=AsyncMock(return_value={})))
    if form.ha_zustand and svc.is_available:
        z = ha_lts_helfer.ZustandsVerlauf(form.zustaende)
        st.enter_context(patch("backend.services.ha_state_service.get_ha_state_service", lambda: z))
    return st


# ── Schreibwege ─────────────────────────────────────────────────────────────


async def schreibe_s1_aus_ha_laden(db: AsyncSession, form: Form, aid: int) -> dict:
    """S1 — wie ``pv_achse_matrix.schreibe_s1_aus_ha_laden``; beim gepflegten Flex-Tarif trägt der
    Anwender den Monats-Ø dazu ein (Formularfeld „Ø Strompreis", ``MonatsdatenForm.tsx:954``)."""
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten

    antwort = await get_monatswerte(aid, JAHR, JUNI, db)
    basis = {b.feld: b.differenz for b in antwort.basis}
    nutzlast: dict[str, Any] = {"anlage_id": aid, "jahr": JAHR, "monat": JUNI,
                                "einspeisung_kwh": basis["einspeisung_kwh"], "netzbezug_kwh": basis["netzbezug_kwh"],
                                "geprueft_gegen": {}}
    if basis.get("pv_erzeugung_kwh") is not None:
        nutzlast["pv_erzeugung_kwh"] = basis["pv_erzeugung_kwh"]
    if form.gepflegt_cent is not None:
        nutzlast["netzbezug_durchschnittspreis_cent"] = form.gepflegt_cent
    inv = {str(i.investition_id): {**{f.feld: f.differenz for f in i.felder}, "geprueft_gegen": {}}
           for i in antwort.investitionen}
    if inv:
        nutzlast["investitionen_daten"] = inv
    await create_monatsdaten(MonatsdatenCreate.model_validate(nutzlast), None, db)
    await mx._nachlauf(db, aid)
    return nutzlast


async def schreibe_s3_von_hand(db: AsyncSession, form: Form, aid: int, ids: dict[str, int]) -> dict:
    """S3 — Standalone-Monatsabschluss von Hand: die Monatsmengen, die die Zähler zeigen."""
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten

    pf = form.pvform
    r = basis_reihen(form, mit_sprung=False)
    nutzlast: dict[str, Any] = {"anlage_id": aid, "jahr": JAHR, "monat": JUNI,
                                "einspeisung_kwh": menge(r["sensor.einsp"], TAGE_JUNI),
                                "netzbezug_kwh": menge(r["sensor.netz"], TAGE_JUNI), "geprueft_gegen": {}}
    if pf.gesamt is not None:
        nutzlast["pv_erzeugung_kwh"] = menge(r["sensor.pv_gesamt"], TAGE_JUNI)
    if form.gepflegt_cent is not None:
        nutzlast["netzbezug_durchschnittspreis_cent"] = form.gepflegt_cent
    inv = {str(ids[g.name]): {"pv_erzeugung_kwh": mx.tagesmenge(g.rate) * 30, "geprueft_gegen": {}}
           for g in pf.geraete if g.zaehler}
    for g in form.geraete:
        werte = dict(g.hand) if g.hand is not None else {f: menge(fn, TAGE_JUNI) for f, fn in g.felder.items()}
        inv[str(ids[g.name])] = {**werte, "geprueft_gegen": {}}
    if inv:
        nutzlast["investitionen_daten"] = inv
    await create_monatsdaten(MonatsdatenCreate.model_validate(nutzlast), None, db)
    await mx._nachlauf(db, aid)
    return nutzlast


# ── Messfunktionen ──────────────────────────────────────────────────────────
#
# Jede liefert ein flaches Dict aus Zahlen (oder None, bool, kurzen Texten) — die Proben vergleichen
# nur diese. Was eine Sicht für ein Gerät führt, steht unter dem Gerätenamen.


def _r(x) -> Any:
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, float)):
        return round(float(x), 4)
    return None


def _flach(d: Any, *, tiefe: int = 0, praefix: str = "") -> dict:
    """Ein Modell/Dict/Dataclass als flaches ``{schlüssel: zahl}`` (Listen und tiefe Strukturen fallen weg)."""
    if dataclasses.is_dataclass(d) and not isinstance(d, type):
        d = {f.name: getattr(d, f.name) for f in dataclasses.fields(d)}
    elif hasattr(d, "model_dump"):
        d = d.model_dump(mode="json")
    out: dict = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        if isinstance(v, (int, float, bool)) or v is None or (isinstance(v, str) and len(v) <= 60):
            out[praefix + str(k)] = _r(v)
        elif tiefe > 0 and (isinstance(v, dict) or dataclasses.is_dataclass(v) or hasattr(v, "model_dump")):
            out.update(_flach(v, tiefe=tiefe - 1, praefix=f"{praefix}{k}."))
    return out


def _namen(ids: dict[str, int]) -> dict[str, str]:
    return {str(v): k for k, v in ids.items()}


def _schluessel_namen(d: Optional[dict], ids: dict[str, int]) -> dict:
    """``{"waermepumpe_7": 1.2}`` → ``{"waermepumpe:WP": 1.2}``; Basis-Keys bleiben."""
    rev = _namen(ids)
    out = {}
    for k, v in (d or {}).items():
        pre, _, i = str(k).rpartition("_")
        if pre and i in rev:
            out[f"{pre}:{rev[i]}"] = _r(v)
        else:
            out[str(k)] = _r(v) if not isinstance(v, (dict, list)) else None
    return out


async def miss_tage(db, aid: int, ids: dict, tage) -> dict:
    """Tag: Tageszeile (``komponenten_kwh``), Stundenachsen (Σ der Spalten und je Gerät aus ``komponenten``,
    Etikett-Stunden je Gerät, Preis-Stunden) und Cockpit → Tag (``baue_tage_werte``)."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    rev = _namen(ids)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    tw = {z.datum: z for z in await baue_tage_werte(db, anlage, tage[0], tage[-1])}
    out = {}
    for tag in tage:
        tz = (await db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == aid, TagesZusammenfassung.datum == tag))).scalar_one_or_none()
        teps = (await db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == aid, TagesEnergieProfil.datum == tag))).scalars().all()
        spalten = {}
        for sp in ("pv_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "waermepumpe_kw", "wallbox_kw",
                   "verbrauch_kw"):
            werte = [getattr(r, sp) for r in teps if getattr(r, sp) is not None]
            spalten[sp] = _r(sum(werte)) if werte else None
        komp: dict = {}
        modus: dict = {}
        preis = {}
        for r in teps:
            for k, v in (r.komponenten or {}).items():
                if isinstance(v, (int, float)):
                    n = _schluessel_namen({k: v}, ids)
                    for kk, vv in n.items():
                        komp[kk] = round((komp.get(kk) or 0.0) + vv, 4)
            for i, mo in (r.betriebsmodus_je_wp or {}).items():
                modus.setdefault(rev.get(str(i), str(i)), {})[r.stunde] = mo
            if r.strompreis_cent is not None:
                preis[r.stunde] = r.strompreis_cent
        z = tw.get(tag)
        out[tag.isoformat()] = {
            "tz": tz is not None,
            "keys": _schluessel_namen(tz.komponenten_kwh if tz else {}, ids),
            "spalten": spalten,
            "stunden_komp": komp,
            "modus": {k: {str(h): m for h, m in v.items()} for k, v in modus.items()},
            "preis_stunden": {str(h): p for h, p in preis.items()},
            "netz_je_stunde": {str(r.stunde): _r(r.netzbezug_kw) for r in teps},
            "tw": _flach(z) if z else {},
            "tw_erzeuger": _schluessel_namen(getattr(z, "erzeuger_kwh", None), ids) if z else {},
        }
    return out


async def miss_tag_detail(db, aid: int, ids: dict, tage) -> dict:
    """Cockpit → Tag, Detailblock (``get_tag_detail``) — WP-Split/Wärme, Speicher-Netzladung, E-Mob-Anteil."""
    from backend.api.routes.energie_profil.tag import get_tag_detail

    out = {}
    for tag in tage:
        try:
            d = await get_tag_detail(anlage_id=aid, datum=tag, db=db)
        except Exception as e:  # noqa: BLE001 — eine Sicht, die abbricht, ist eine Messung
            out[tag.isoformat()] = {"fehler": f"{type(e).__name__}: {e}"[:200]}
            continue
        out[tag.isoformat()] = _flach(d, tiefe=1)
    return out


async def miss_cockpit_monat(db, aid: int, ids: dict, monat: int) -> dict:
    import backend.api.routes.aktueller_monat as am

    r = await am.get_aktueller_monat(anlage_id=aid, jahr=JAHR, monat=monat, db=db)
    d = _flach(r)
    rev = _namen(ids)
    d["wp_geraete"] = {rev.get(str(g.get("investition_id")), str(g.get("investition_id"))): _flach(g)
                       for g in (r.model_dump(mode="json").get("wp_geraete") or [])}
    d["sonstiges_geraete"] = {g.get("bezeichnung"): _flach(g) for g in (r.model_dump(mode="json").get("sonstiges_geraete") or [])}
    d["fin"] = {f.bezeichnung: _flach(f) for f in r.investitionen_financials}
    d["feld_quellen"] = {k: (v.quelle if hasattr(v, "quelle") else (v or {}).get("quelle"))
                         for k, v in (r.feld_quellen or {}).items()}
    d["fehlende_posten"] = list(r.fehlende_posten or [])
    d["datenlage_gruende"] = sorted((r.datenlage_gruende or {}).keys())
    return d


async def miss_fakten(db, aid: int, ids: dict, monat: int, *, tageswerte: bool = False) -> Optional[dict]:
    from backend.services.monats_fakten import lade_monats_fakten

    rev = _namen(ids)
    fk = await lade_monats_fakten(db, aid, von=(JAHR, monat), bis=(JAHR, monat), inkl_nur_tageswerte=tageswerte)
    if not fk:
        return None
    f = fk[0]
    out = {}
    for gruppe in ("zaehler", "erzeugung", "speicher", "emob", "wp", "sonstiges", "tarif", "kennzahlen", "bkw"):
        out[gruppe] = _flach(getattr(f, gruppe))
    out["meta"] = {"hat_zaehlerzeile": f.meta.hat_zaehlerzeile, "tageswert_gruppen": sorted(f.meta.tageswert_gruppen),
                   "typen_mit_zeile": sorted(f.meta.typen_mit_zeile)}
    out["wp_je_geraet"] = {rev.get(str(i), str(i)): _flach(g) for i, g in (f.wp.je_geraet or {}).items()}
    out["sonstiges_je_geraet"] = {rev.get(str(i), str(i)): _flach(g) for i, g in (f.sonstiges.je_geraet or {}).items()}
    out["emob_je_auto"] = {rev.get(str(i), str(i)): _flach(g) for i, g in (f.emob.je_auto or {}).items()}
    out["emob_wallbox_summe"] = _flach(f.emob.wallbox_summe)
    out["emob_eauto_summe"] = _flach(f.emob.eauto_summe)
    return out


async def miss_aggregiert(db, aid: int, monat: int, *, voll: bool) -> Optional[dict]:
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    zeilen = await list_monatsdaten_aggregiert(anlage_id=aid, jahr=JAHR, inkl_ohne_zaehlerzeile=voll,
                                               inkl_nur_tageswerte=voll, db=db)
    z = next((z for z in zeilen if z.monat == monat), None)
    return _flach(z) if z is not None else None


async def miss_jahr(db, aid: int) -> dict:
    from backend.services.jahres_aggregat import baue_jahr

    j = await baue_jahr(db, aid, JAHR, heute=JETZT.date())
    kopf = j["kopf"] if isinstance(j["kopf"], dict) else j["kopf"].model_dump()
    return {"monate": {str(m["monat"]): _flach(m) for m in j["monate"]}, "kopf": _flach(kopf)}


async def miss_uebersicht(db, aid: int) -> dict:
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    return _flach(await get_cockpit_uebersicht(anlage_id=aid, jahr=JAHR, db=db))


async def miss_zeitreihe(db, aid: int, monat: int) -> dict:
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe

    kz = await get_komponenten_zeitreihe(anlage_id=aid, jahr=JAHR, db=db)
    kd = kz if isinstance(kz, dict) else kz.model_dump(mode="json")
    mw = next((w for w in kd.get("monatswerte", []) if w.get("monat") == monat and w.get("jahr") == JAHR), None)
    return _flach(mw) if mw else {}


async def miss_dashboards(db, aid: int, ids: dict, form: Form) -> dict:
    """Komponenten-Dashboards (Speicher, Wärmepumpe, Wallbox, E-Auto): je Gerät die Zusammenfassung und
    der Juni aus den Monatswerten."""
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
    from backend.api.routes.investitionen.dashboard_speicher import get_speicher_dashboard
    from backend.api.routes.investitionen.dashboard_waermepumpe import get_waermepumpe_dashboard
    from backend.api.routes.investitionen.dashboard_wallbox import get_wallbox_dashboard

    rev = _namen(ids)
    wege = {"speicher": get_speicher_dashboard, "waermepumpe": get_waermepumpe_dashboard,
            "wallbox": get_wallbox_dashboard, "e-auto": get_eauto_dashboard}
    out: dict = {}
    for typ, fn in wege.items():
        if not form.typ(typ):
            continue
        try:
            kw = {"anlage_id": aid, "strompreis_cent": None, "db": db}
            if typ == "speicher":
                kw["einspeiseverguetung_cent"] = None
            res = await fn(**kw)
        except Exception as e:  # noqa: BLE001
            out[typ] = {"fehler": f"{type(e).__name__}: {e}"[:200]}
            continue
        liste = res if isinstance(res, list) else [res]
        je = {}
        for d in liste:
            dd = d if isinstance(d, dict) else d.model_dump(mode="json")
            inv = dd.get("investition") or {}
            name = rev.get(str(inv.get("id")), inv.get("bezeichnung") or "?")
            juni = next((m for m in dd.get("monatsdaten") or [] if m.get("jahr") == JAHR and m.get("monat") == JUNI), None)
            je[name] = {"zusammenfassung": _flach(dd.get("zusammenfassung") or {}),
                        "juni": _flach((juni or {}).get("verbrauch_daten") or juni or {})}
        out[typ] = je
    return out


async def miss_ha_export(db, aid: int, ids: dict) -> dict:
    from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
    from backend.api.routes.ha_export.investition_sensoren import calculate_investition_sensors
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage

    rev = _namen(ids)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    out = {"anlage": {s.definition.key: _r(s.value) for s in
                      await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=JETZT)}}
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == aid))).scalars().all()
    strompreis = (await lade_tarife_fuer_anlage(db, aid))["allgemein"]
    emob_ctx = await _load_emob_pool_ctx(db, invs)
    je = {}
    for inv in invs:
        if inv.typ in ("pv-module", "balkonkraftwerk"):
            continue
        sens = await calculate_investition_sensors(db, inv, strompreis, emob_ctx, {})
        je[rev.get(str(inv.id), str(inv.id))] = {s.definition.key: _r(s.value) for s in sens}
    out["inv"] = je
    return out


async def miss_community(db, aid: int) -> dict:
    from backend.services.community_service import prepare_community_data

    c = await prepare_community_data(db, aid) or {}
    mw = next((m for m in c.get("monatswerte") or [] if m.get("jahr") == JAHR and m.get("monat") == JUNI), {})
    return {"monat": _flach(mw), "kopf": _flach({k: v for k, v in c.items() if k != "monatswerte"})}


async def miss_pdf(db, aid: int) -> dict:
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    ctx = await build_jahresbericht_context(db, aid, JAHR)
    juni = next((z for z in ctx.get("monats_zeilen") or [] if z.get("monat") == JUNI), {})
    return {"juni": _flach(juni), "kopf": _flach({k: v for k, v in ctx.items()
                                                    if not isinstance(v, (list, tuple))}, tiefe=1)}


async def miss_aussichten(db, aid: int) -> dict:
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose

    try:
        r = await get_finanz_prognose(anlage_id=aid, monate=12, db=db)
    except Exception as e:  # noqa: BLE001
        return {"fehler": f"{type(e).__name__}: {e}"[:200]}
    return _flach(r, tiefe=1)


async def miss_preis(db, aid: int) -> dict:
    """Preis-Aggregat (``lade_preis_aggregate_je_monat``) und Komponenten-Lookup (``monats_strompreis_lookup``)."""
    from backend.api.routes.strompreise import monats_strompreis_lookup
    from backend.services.strompreis_aggregator import lade_preis_aggregate_je_monat

    pm = await lade_preis_aggregate_je_monat(db, aid)
    out = {}
    for monat in (JUNI, JULI):
        a = pm.hole(JAHR, monat)
        out[str(monat)] = _flach(a) if a is not None else None
    lk = {}
    for verw in ("allgemein", "wallbox", "waermepumpe"):
        try:
            w = await monats_strompreis_lookup(db, aid, verw, [(JAHR, JUNI), (JAHR, JULI)], STAMM_CENT)
            lk[verw] = {str(m): _r(v) for (_j, m), v in w.items()}
        except Exception as e:  # noqa: BLE001
            lk[verw] = {"fehler": f"{type(e).__name__}: {e}"[:200]}
    out["lookup"] = lk
    return out


# ── Eine Form messen ────────────────────────────────────────────────────────


@dataclass
class Messung:
    form: Form
    tage: dict[str, dict] = field(default_factory=dict)
    laufend: dict[str, dict] = field(default_factory=dict)
    vor: dict[str, dict] = field(default_factory=dict)
    nach: dict[str, dict] = field(default_factory=dict)
    nutzlast: dict[str, dict] = field(default_factory=dict)
    ids: dict[str, int] = field(default_factory=dict)


async def _sichten_laufend(db, aid, ids) -> dict:
    return {"tage": await miss_tage(db, aid, ids, TAGE_JULI),
            "tag_detail": await miss_tag_detail(db, aid, ids, TAGE_JULI),
            "monat": await miss_cockpit_monat(db, aid, ids, JULI),
            "jahr": (await miss_jahr(db, aid))["monate"].get(str(JULI)),
            "verlauf": await miss_aggregiert(db, aid, JULI, voll=True),
            "fakten_tw": await miss_fakten(db, aid, ids, JULI, tageswerte=True)}


async def _sichten_vor(db, aid, ids) -> dict:
    return {"monat": await miss_cockpit_monat(db, aid, ids, JUNI),
            "verlauf": await miss_aggregiert(db, aid, JUNI, voll=True),
            "fakten_tw": await miss_fakten(db, aid, ids, JUNI, tageswerte=True)}


async def _sichten_nach(db, aid, ids, form) -> dict:
    jahr = await miss_jahr(db, aid)
    return {"monat": await miss_cockpit_monat(db, aid, ids, JUNI),
            "fakten": await miss_fakten(db, aid, ids, JUNI),
            "uebersicht": await miss_uebersicht(db, aid),
            "jahr": jahr["monate"].get(str(JUNI)),
            "jahr_kopf": jahr["kopf"],
            "tabelle": await miss_aggregiert(db, aid, JUNI, voll=False),
            "zeitreihe": await miss_zeitreihe(db, aid, JUNI),
            "dashboards": await miss_dashboards(db, aid, ids, form),
            "ha_export": await miss_ha_export(db, aid, ids),
            "community": await miss_community(db, aid),
            "pdf": await miss_pdf(db, aid),
            "aussichten": await miss_aussichten(db, aid),
            "preis": await miss_preis(db, aid)}


async def messe_ha(form: Form, m: Messung) -> None:
    verz = tempfile.mkdtemp(prefix="eedc-achsen-matrix-")
    try:
        basis = f"{verz}/ha.db"
        engine, db = await mx._neue_db(basis)
        svc = seed_ha(form)
        try:
            aid, ids = await seed_anlage(db, form)
            m.ids = ids
            with umgebung(form, svc):
                await mx.fuelle_spiegel(engine, aid, svc)   # E4a-2, B-1: Spiegel wie im Produkt mit HA
                await mx.aggregiere_tage(db, form.pvform, aid, TAGE_JUNI + TAGE_JULI)
                m.tage["HA"] = await miss_tage(db, aid, ids, TAGE_JUNI + TAGE_JULI)
                m.laufend["HA"] = await _sichten_laufend(db, aid, ids)
        finally:
            await db.close()
            await engine.dispose()
        for weg in ("S1", "S2"):
            pfad = f"{verz}/{weg}.db"
            shutil.copyfile(basis, pfad)
            engine, db = await mx._oeffne_db(pfad)
            try:
                with umgebung(form, svc):
                    m.vor[weg] = await _sichten_vor(db, aid, ids)
                    if weg == "S1":
                        m.nutzlast[weg] = await schreibe_s1_aus_ha_laden(db, form, aid)
                    else:
                        m.nutzlast[weg] = await mx.schreibe_s2_sammelimport(db, aid)
                    m.nach[weg] = await _sichten_nach(db, aid, ids, form)
            finally:
                await db.close()
                await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def messe_sa(form: Form, m: Messung) -> None:
    verz = tempfile.mkdtemp(prefix="eedc-achsen-matrix-")
    try:
        engine, db = await mx._neue_db(f"{verz}/sa.db")
        try:
            aid, ids = await seed_anlage(db, form)
            m.ids = ids
            await seed_snapshots(db, form, aid, ids)
            with umgebung(form, mx._ha_aus()):
                await mx.aggregiere_tage(db, form.pvform, aid, TAGE_JUNI + TAGE_JULI)
                m.tage["SA"] = await miss_tage(db, aid, ids, TAGE_JUNI + TAGE_JULI)
                m.laufend["SA"] = await _sichten_laufend(db, aid, ids)
                m.vor["S3"] = await _sichten_vor(db, aid, ids)
                m.nutzlast["S3"] = await schreibe_s3_von_hand(db, form, aid, ids)
                m.nach["S3"] = await _sichten_nach(db, aid, ids, form)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def messe_form(form: Form) -> Messung:
    m = Messung(form)
    await messe_ha(form, m)
    await messe_sa(form, m)
    return m
