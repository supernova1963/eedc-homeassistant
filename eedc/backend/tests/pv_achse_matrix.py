"""Abnahme-Matrix der PV-Achse — Seed, Schreibwege, Messfunktionen, Soll-Regel.

Die Proben dazu stehen in ``test_pv_achse_matrix.py``; dieses Modul ist ihr Baustein
(kein ``test``-Präfix, damit pytest hier nichts einsammelt — dieselbe Regel wie in
``ha_lts_helfer.py``).

**Warum es diese Matrix gibt (Auftrag Fable-Master 04.10.2026).** Fixes auf der PV-Achse
kamen als neue Funde zurück, weil ihre Proben einen Zustand säten, den es im Betrieb
nicht gibt: N-587 prüfte den laufenden Monat ohne Tageszeilen (⇒ N-624), N-534 fütterte
einen Feldnamen, den das Backend nie sendet (⇒ N-622). Diese Matrix baut für jede
Zuordnungsform den **produktiven Datenstand** auf und misst ihn über die **produktiven
Einstiege** — nichts, was im HA-Betrieb vorhanden ist, wird gestubbt:

* HA-Langzeitstatistik im echten Recorder-Schema (``ha_lts_helfer``), echter
  ``HAStatisticsService`` — eingehängt über das Singleton, das ALLE Leser rufen
  (``ha_statistics_service._ha_statistics_service``), statt Import für Import.
* Tageszeilen über den echten ``aggregate_day`` für jeden Tag (``Source.SCHEDULER``, die
  Leistungskurve wird vorgereicht wie im Vollbackfill — sie trägt Spitzenwerte, keine kWh).
* Ein **abgeschlossener** Monat (Juni 2026) und der **laufende** (Juli 2026, drei Tage).
  Der Juni entsteht je Schreibweg über die echte Route:
  S1 „Aus HA laden" (``GET /ha-statistics/monatswerte`` → Formular-Nutzlast →
  ``create_monatsdaten`` → Nachlauf), S2 HA-Statistik-Sammelimport
  (``import_ha_statistics``), S3 Handeingabe ohne HA (Standalone: Zählerstände aus
  ``sensor_snapshots``, Tage über den Snapshot-Pfad, ``create_monatsdaten`` mit den
  abgelesenen Werten).

**Gestubbt wird nur, was im Betrieb von außen kommt:** der Börsenpreis (aWATTar, Netz)
im Tageslauf. Die Anlage hat keine Koordinaten — Wetter fällt damit von selbst weg.

**Die Uhr** ist gestellt: ``JETZT`` = 04.07.2026 00:30. ``get_aktueller_monat`` liest
``datetime.now()`` seines Pakets — gestellt wie in ``test_n587_pv_strings_vor_anlagenzaehler.py``
(Unterklasse mit fester ``now()``); die Jahresroute bekommt ihr ``heute`` als Parameter
(``services/jahres_aggregat.py::baue_jahr``), der HA-Export sein ``jetzt``. Juni/Juli
liegen in Berlin, UTC und Auckland ohne Zeitumstellung.

**Das Soll steht hier als Regel, nicht als Messwert** (``soll_tag`` · ``soll_monat``) —
Variante B (Handbuch Einstellungen §7.6, BERECHNUNGEN §1): der Anlagenzähler umfasst alle
PV-Quellen, Quellen mit eigenem Wert gewinnen, der Rest ``max(0, …)`` geht nach kWp auf die
Lücken. Am Tag zusätzlich E4 (BKW-Key trägt den Rest seiner Kinder, Vorlage Zählerlücken
§5) und Bauplan N-623 Fassung 2 (gemessene Erzeuger behalten im Aggregat-Fall ihren
Tageswert). Im Monat zusätzlich N-266/E4 Stufe 2 (das BKW ist Aggregat seiner Kinder,
``services/pv_monatswerte.py``) und die Abtretung je Monat (ADR-002/P11).
"""

from __future__ import annotations

import time as _zeit
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.core.database import Base
from backend.models import Anlage, Investition, Strompreis
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests import ha_lts_helfer

# ── Zeitraum ────────────────────────────────────────────────────────────────

D0 = date(2024, 1, 1)
JAHR = 2026
JUNI = 6
JULI = 7
#: Die gestellte Uhr — der Juli läuft, drei Tage sind vorbei, der vierte hat begonnen.
JETZT = datetime(2026, 7, 4, 0, 30)
TAGE_JUNI = tuple(date(JAHR, JUNI, d) for d in range(1, 31))
TAGE_JULI = tuple(date(JAHR, JULI, d) for d in range(1, 4))
#: Erste und (exklusiv) letzte Stunde der Zählerreihen. 18:00 am Vortag: die Reihe hat
#: einen Anker vor dem Monat (R10), produziert aber am 31.05. nichts mehr.
REIHE_VON = datetime(2026, 5, 31, 18)
REIHE_BIS = datetime(2026, 7, 4, 0)
#: Die Sonne scheint 10:00–16:00 (sechs Stunden) — die Rate einer Quelle ist ihre
#: Energie je Produktionsstunde; nachts fließt nur Netzbezug.
PROD_STUNDEN = range(10, 16)
NETZ_NACHT = 0.4

KIND_AB_F10 = date(2026, 7, 2)


def tagesmenge(rate: float) -> float:
    return rate * len(PROD_STUNDEN)


# ── Zuordnungsformen ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Geraet:
    """Ein PV-Erzeuger der Anlage. ``rate`` ist die physikalische Erzeugung je
    Produktionsstunde; ``zaehler`` sagt, ob ihm ein eigener kWh-Zähler zugeordnet ist."""

    name: str
    typ: str
    kwp: float
    rate: float
    zaehler: bool = False
    parent: Optional[str] = None
    ab: date = D0
    #: F12: die Nennleistung steht nur als ``leistung_wp × anzahl`` im Parameter-JSON.
    kwp_als_wp: bool = False
    #: F08: der Zähler (Wechselrichter) schläft nachts — keine Zeilen 21:00–05:00.
    nachtluecke: bool = False

    @property
    def sensor_id(self) -> str:
        return "sensor.pv_" + {"Süd": "sued", "West": "west", "Balkon": "balkon",
                               "Kind 1": "kind1", "Kind 2": "kind2"}[self.name]


@dataclass(frozen=True)
class Form:
    fid: str
    titel: str
    geraete: tuple[Geraet, ...]
    #: Rate des Anlagen-PV-Zählers je Produktionsstunde; ``None`` = keiner zugeordnet.
    gesamt: Optional[float]
    einsp_rate: float = 1.0
    anlage_kwp: float = 10.8

    def geraet(self, name: str) -> Geraet:
        return next(g for g in self.geraete if g.name == name)


def _sued(z=False):
    return Geraet("Süd", "pv-module", 6.0, 2.0, z)


def _west(z=False):
    return Geraet("West", "pv-module", 4.0, 1.0, z)


def _bkw(z=False, nacht=False, wp=False):
    return Geraet("Balkon", "balkonkraftwerk", 0.8, 0.5, z, nachtluecke=nacht, kwp_als_wp=wp)


def _kinder(z1=False, z2=False, ab=D0):
    # Ungleiche kWp (0,3 / 0,5) — ein Teilungsfehler nach Köpfen statt nach kWp fällt auf.
    return (Geraet("Kind 1", "pv-module", 0.3, 0.2, z1, parent="Balkon", ab=ab),
            Geraet("Kind 2", "pv-module", 0.5, 0.3, z2, parent="Balkon", ab=ab))


FORMEN: dict[str, Form] = {f.fid: f for f in (
    Form("F01", "nur Gesamtzähler", (_sued(), _west(), _bkw()), 3.5),
    Form("F02", "Gesamt + alle drei Einzelzähler", (_sued(True), _west(True), _bkw(True)), 3.5),
    Form("F03", "Gesamt + BKW-Zähler, Strings ohne", (_sued(), _west(), _bkw(True)), 3.5),
    Form("F04", "Gesamt + Süd mit, West ohne, BKW ohne", (_sued(True), _west(), _bkw()), 3.5),
    Form("F05", "Gesamt + Strings mit, BKW ohne", (_sued(True), _west(True), _bkw()), 3.5),
    Form("F06", "ohne Gesamt, alle Einzelzähler", (_sued(True), _west(True), _bkw(True)), None),
    Form("F07", "ohne Gesamt, West ohne Zähler (Lücke ohne Anlagenwert)", (_sued(True), _west(), _bkw(True)), None),
    Form("F08a", "wie F02, BKW-Zähler ohne Nachtzeilen", (_sued(True), _west(True), _bkw(True, nacht=True)), 3.5),
    Form("F08b", "wie F03, BKW-Zähler ohne Nachtzeilen", (_sued(), _west(), _bkw(True, nacht=True)), 3.5),
    Form("F09a-G", "BKW-Zähler + Kinder ohne Sensor, Gesamt, Strings ohne",
         (_sued(), _west(), _bkw(True), *_kinder()), 3.5),
    Form("F09b-G", "BKW-Zähler + Kind 1 mit Sensor, Gesamt, Strings ohne",
         (_sued(), _west(), _bkw(True), *_kinder(z1=True)), 3.5),
    Form("F09c-G", "BKW-Zähler + beide Kinder mit Sensor, Gesamt, Strings ohne",
         (_sued(), _west(), _bkw(True), *_kinder(True, True)), 3.5),
    Form("F09a-oG", "BKW-Zähler + Kinder ohne Sensor, ohne Gesamt, Strings mit",
         (_sued(True), _west(True), _bkw(True), *_kinder()), None),
    Form("F09b-oG", "BKW-Zähler + Kind 1 mit Sensor, ohne Gesamt, Strings mit",
         (_sued(True), _west(True), _bkw(True), *_kinder(z1=True)), None),
    Form("F09c-oG", "BKW-Zähler + beide Kinder mit Sensor, ohne Gesamt, Strings mit",
         (_sued(True), _west(True), _bkw(True), *_kinder(True, True)), None),
    Form("F10", "Gesamt + alle drei Einzelzähler, BKW-Kinder ohne Sensor ab 02.07. (späte Kinder)",
         (_sued(True), _west(True), _bkw(True), *_kinder(ab=KIND_AB_F10)), 3.5),
    Form("F11", "reine BKW-Anlage, BKW-Zähler + Gesamt", (_bkw(True),), 0.5, einsp_rate=0.2, anlage_kwp=0.8),
    Form("F12", "wie F04, BKW-kWp nur leistung_wp × anzahl", (_sued(True), _west(), _bkw(wp=True)), 3.5),
    Form("F13a", "volle Deckung, Σ Einzel 21 > Gesamt 19,8", (_sued(True), _west(True), _bkw(True)), 3.3),
    Form("F13b", "volle Deckung, Σ Einzel 21 < Gesamt 22,2", (_sued(True), _west(True), _bkw(True)), 3.7),
    Form("F14", "ohne BKW: Gesamt + Süd mit, West ohne", (_sued(True), _west()), 3.0, anlage_kwp=10.0),
    Form("F15", "Kontrollform: zwei Strings, beide gemessen, kein Gesamt", (_sued(True), _west(True)), None,
         anlage_kwp=10.0),
    # N-626 (Gegenprüfung, Zusatzform): wie F07 ohne Balkonkraftwerk — ohne die Teilsumme in
    # `pv_module_kwh` blieben Tabelle leer und ROI 0.
    Form("F16", "ohne Gesamt, ohne BKW: Süd mit Zähler, West ohne (Lücke ohne Anlagenwert)",
         (_sued(True), _west()), None, anlage_kwp=10.0),
)}


# ── Soll aus der Regel ──────────────────────────────────────────────────────


def _aktiv(g: Geraet, tag: date) -> bool:
    return g.ab <= tag


def _kinder_von(form: Form, bkw: Geraet, tag: date) -> list[Geraet]:
    return [k for k in form.geraete if k.parent == bkw.name and _aktiv(k, tag)]


def _kwp_anteile(rest: float, luecken: list[Geraet]) -> dict[str, float]:
    kwp = sum(g.kwp for g in luecken)
    return {g.name: (rest * g.kwp / kwp if kwp else 0.0) for g in luecken}


@dataclass
class Soll:
    """Soll einer Sicht: PV-Summe und Wert je Gerät (Name → kWh). ``ohne_key``: Geräte,
    die in dieser Sicht keinen eigenen Eintrag tragen dürfen (oder 0)."""

    summe: float
    je_geraet: dict[str, float] = field(default_factory=dict)
    ohne_key: frozenset[str] = frozenset()
    vollstaendig: bool = True


def soll_tag(form: Form, tag: date) -> Soll:
    """Der gespeicherte Tag nach der Regel (Bauplan N-623 Fassung 2 + E4 + Variante B).

    Träger sind die Module ohne Elternteil und jedes Balkonkraftwerk; ein Kind mit eigenem
    Zähler trägt seinen Wert, ein Kind ohne Zähler unter einem gemessenen BKW ist keine
    Lücke und trägt keinen Key (E4, P16). Das BKW trägt den Rest nach seinen gemessenen
    Kindern. Alle Träger gemessen ⇒ Einzel-Fall (Σ Einzel). Sonst mit Anlagenzähler:
    gemessene behalten ihren Wert, die Lücken teilen ``max(0, G − Σ gemessen)`` nach kWp.
    Ohne Anlagenzähler bleibt die Lücke ohne Key.
    """
    je: dict[str, float] = {}
    ohne: set[str] = set()
    gemessen = 0.0
    luecken: list[Geraet] = []
    for g in form.geraete:
        if not _aktiv(g, tag) or g.parent is not None:
            continue
        if g.typ == "balkonkraftwerk" and g.zaehler:
            kinder = _kinder_von(form, g, tag)
            k_gem = 0.0
            for k in kinder:
                if k.zaehler:
                    je[k.name] = tagesmenge(k.rate)
                    k_gem += je[k.name]
                else:
                    ohne.add(k.name)
            je[g.name] = tagesmenge(g.rate) - k_gem
            gemessen += tagesmenge(g.rate)
        elif g.zaehler:
            je[g.name] = tagesmenge(g.rate)
            gemessen += je[g.name]
        else:
            luecken.append(g)
    if not luecken:
        return Soll(gemessen, je, frozenset(ohne))
    if form.gesamt is None:
        return Soll(gemessen, je, frozenset(ohne | {g.name for g in luecken}), vollstaendig=False)
    g_tag = tagesmenge(form.gesamt)
    je.update(_kwp_anteile(max(0.0, g_tag - gemessen), luecken))
    return Soll(max(g_tag, gemessen), je, frozenset(ohne))


def soll_monat(form: Form, tage: tuple[date, ...], *, mit_anlagenwert: bool = True) -> Soll:
    """Ein Monat nach der Regel (Variante B, N-266/E4 Stufe 2, Abtretung je Monat).

    Ein BKW, dessen Kinder im Monat aktiv sind, tritt ab: sein Wert ist das Aggregat seiner
    Kinder (gemessene Kinder behalten, die übrigen teilen den Rest nach kWp), das BKW selbst
    trägt keinen Eintrag. Danach Stufe 3: der Anlagenwert füllt nur, was die eigenen Werte
    nicht erklären, nach kWp auf Module UND Balkonkraftwerke ohne eigenen Wert.
    ``mit_anlagenwert=False``: der Monat kennt den Anlagenzähler nicht (Lücke ⇒ Teilsumme).
    """
    n = len(tage)
    letzter = tage[-1]
    je: dict[str, float] = {}
    ohne: set[str] = set()
    gemessen = 0.0
    luecken: list[Geraet] = []
    for g in form.geraete:
        if not _aktiv(g, letzter) or g.parent is not None:
            continue
        menge = tagesmenge(g.rate) * n
        if g.typ == "balkonkraftwerk":
            kinder = _kinder_von(form, g, letzter)
            if kinder and g.zaehler:
                ohne.add(g.name)                         # abgetreten (P11, je Monat)
                k_gem = {k.name: tagesmenge(k.rate) * n for k in kinder if k.zaehler}
                k_luecken = [k for k in kinder if not k.zaehler]
                je.update(k_gem)
                je.update(_kwp_anteile(max(0.0, menge - sum(k_gem.values())), k_luecken))
                gemessen += menge
                continue
        if g.zaehler:
            je[g.name] = menge
            gemessen += menge
        else:
            luecken.append(g)
    if not luecken:
        return Soll(gemessen, je, frozenset(ohne))
    if form.gesamt is None or not mit_anlagenwert:
        return Soll(gemessen, je, frozenset(ohne | {g.name for g in luecken}), vollstaendig=False)
    g_monat = tagesmenge(form.gesamt) * n
    je.update(_kwp_anteile(max(0.0, g_monat - gemessen), luecken))
    return Soll(max(g_monat, gemessen), je, frozenset(ohne))


def soll_einspeisung(form: Form, n_tage: int) -> float:
    return tagesmenge(form.einsp_rate) * n_tage


def soll_netzbezug(n_tage: int) -> float:
    return NETZ_NACHT * (24 - len(PROD_STUNDEN)) * n_tage


# ── Seed ────────────────────────────────────────────────────────────────────


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _reihen(form: Form) -> dict[str, tuple]:
    """``{sensor_id: (rate_fn, ohne_zeile_fn, sensor_key_fn)}`` aller Zähler der Form."""

    def prod(rate):
        return lambda t: rate if t.hour in PROD_STUNDEN else 0.0

    def nie(_t):
        return False

    reihen = {
        "sensor.einsp": (prod(form.einsp_rate), nie, "basis:einspeisung"),
        "sensor.netz": ((lambda t: 0.0 if t.hour in PROD_STUNDEN else NETZ_NACHT), nie, "basis:netzbezug"),
    }
    if form.gesamt is not None:
        reihen["sensor.pv_gesamt"] = (prod(form.gesamt), nie, "basis:pv_gesamt")
    for g in form.geraete:
        if g.zaehler:
            reihen[g.sensor_id] = (
                prod(g.rate),
                (lambda t: t.hour >= 21 or t.hour <= 5) if g.nachtluecke else nie,
                g.name,  # wird nach dem Anlegen durch `inv:<id>:pv_erzeugung_kwh` ersetzt
            )
    return reihen


async def seed_anlage(db: AsyncSession, form: Form) -> tuple[int, dict[str, int]]:
    """Anlage, Tarif, Investitionen und Sensor-Zuordnung der Form."""
    a = Anlage(anlagenname=f"Matrix {form.fid}", leistung_kwp=form.anlage_kwp, installationsdatum=D0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=D0,
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    ids: dict[str, int] = {}
    for g in form.geraete:
        kw: dict[str, Any] = dict(
            anlage_id=a.id, typ=g.typ, bezeichnung=g.name, anschaffungsdatum=g.ab,
            anschaffungskosten_gesamt=1000.0,
            parent_investition_id=ids.get(g.parent) if g.parent else None,
        )
        if g.kwp_als_wp:
            kw["parameter"] = {"leistung_wp": int(round(g.kwp * 500)), "anzahl": 2}
        else:
            kw["leistung_kwp"] = g.kwp
        inv = Investition(**kw)
        db.add(inv)
        await db.flush()
        ids[g.name] = inv.id
    basis = {"einspeisung": _s("sensor.einsp"), "netzbezug": _s("sensor.netz")}
    if form.gesamt is not None:
        basis["pv_gesamt"] = _s("sensor.pv_gesamt")
    a.sensor_mapping = {
        "basis": basis,
        "investitionen": {str(ids[g.name]): {"felder": {"pv_erzeugung_kwh": _s(g.sensor_id)}}
                          for g in form.geraete if g.zaehler},
    }
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return a.id, ids


def seed_ha(form: Form, *, abweichung: Optional[dict] = None):
    """Die HA-Langzeitstatistik der Form: eine Zeile je Stunde und Zähler.

    Recorder-Konvention: ``start_ts = t`` trägt den Stand am Ende der Stunde ``t``.
    ``abweichung``: ``{sensor_id: (rate_fn | None, ohne_fn | None)}`` ersetzt Rate bzw.
    fehlende Zeilen einzelner Zähler (Bündel, Abriss, Sprung, Zähler ohne Nachtzeilen) —
    für Einzelproben, die Matrix selbst ruft ohne.
    """
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    for sid, (rate_fn, ohne_fn, _key) in _reihen(form).items():
        rate_neu, ohne_neu = (abweichung or {}).get(sid, (None, None))
        rate_fn, ohne_fn = rate_neu or rate_fn, ohne_neu or ohne_fn
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True)
        stand = 1000.0
        zeilen = []
        t = REIHE_VON
        while t < REIHE_BIS:
            stand += rate_fn(t)
            if not ohne_fn(t):
                zeilen.append({"m": mid, "t": _zeit.mktime(t.timetuple()), "w": round(stand, 4)})
            t += timedelta(hours=1)
        with svc._engine.begin() as conn:
            conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                              "VALUES (:m, :t, :w, :w)"), zeilen)
    return svc


async def seed_snapshots(db: AsyncSession, form: Form, anlage_id: int, ids: dict[str, int]) -> None:
    """Standalone: die stündlichen Zählerstände in ``sensor_snapshots`` (Stand zur vollen Stunde).

    So schreibt der Snapshot-Job sie im Standalone-Betrieb (Quelle ``mqtt_inbound``); der
    Tageslauf liest sie über ``snapshot_tagestabelle``. Ein Zähler ohne Nachtzeilen hat auch
    hier keinen Stand für die Stunden, in denen er schläft.
    """
    from sqlalchemy import insert

    zeilen = []
    for _sid, (rate_fn, ohne_fn, key) in _reihen(form).items():
        sk = key if key.startswith("basis:") else f"inv:{ids[key]}:pv_erzeugung_kwh"
        stand = 1000.0
        t = REIHE_VON
        while t <= REIHE_BIS:
            if not ohne_fn(t - timedelta(hours=1)):
                zeilen.append({"anlage_id": anlage_id, "sensor_key": sk, "zeitpunkt": t,
                               "wert_kwh": round(stand, 4), "quelle": "mqtt_inbound"})
            stand += rate_fn(t)
            t += timedelta(hours=1)
    await db.execute(insert(SensorSnapshot), zeilen)
    await db.commit()


def _kurve(form: Form) -> dict:
    """Die Stunden-Leistungskurve für ``prefetched_tagesverlauf`` (Vollbackfill-Form).

    Hat die Form einen Anlagen-PV-Zähler, trägt die Kurve die Serie ``pv_gesamt`` — dieselbe,
    die ``lts_tagesverlauf``/``live_tagesverlauf_service`` aus einem Gesamtleistungs-Sensor
    bauen, wenn kein Erzeuger eine eigene Leistungs-Serie hat (``live_tagesverlauf_service.py:398-410``).
    Ohne Anlagenzähler trägt sie keine PV-Serie (nur Zählerstände, keine Leistungssensoren).
    Im HA-Betrieb bestimmt die Kurve nur Spitzenwerte; ohne HA-Stunden summiert
    ``summiere_live_komponenten`` sie zusätzlich in ``komponenten_kwh`` — liefert die
    Zählertabelle die PV-Achse, fällt diese Summe seit N-625 wieder heraus.
    """
    serien, werte = [], (lambda h: {})
    if form.gesamt is not None:
        serien = [{"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle", "bidirektional": False}]
        werte = lambda h: {"pv_gesamt": form.gesamt if h in PROD_STUNDEN else 0.0}  # noqa: E731
    return {"serien": serien, "punkte": [{"zeit": f"{h:02d}:00", "werte": werte(h)} for h in range(24)],
            "vortagsrand": [{"zeit": "23:00", "werte": werte(23)}]}


class _FesteUhr(datetime):
    """``datetime`` mit stehender ``now()`` (Muster ``test_n587_pv_strings_vor_anlagenzaehler.py``)."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102 — Verhalten steht im Klassen-Docstring
        return JETZT


def _ha_aus():
    """Ein ``HAStatisticsService`` ohne Datenbank und ohne WebSocket — „kein HA"."""
    from backend.services.ha_statistics_service import HAStatisticsService

    svc = HAStatisticsService()
    svc._engine = None
    svc._initialized = True
    return svc


def _umgebung(svc) -> ExitStack:
    """HA-Dienst (Singleton), gestellte Uhr, Börsenpreis ohne Netz."""
    import backend.api.routes.aktueller_monat as am
    import backend.services.ha_statistics_service as hss
    from backend.services.energie_profil._helpers import StrompreisStunden

    st = ExitStack()
    st.enter_context(patch.object(hss, "_ha_statistics_service", svc))
    st.enter_context(patch.object(am, "datetime", _FesteUhr))
    st.enter_context(patch(
        "backend.services.energie_profil._helpers._get_strompreis_stunden",
        new=AsyncMock(return_value=StrompreisStunden(sensor={}, boerse={})),
    ))
    return st


def _engine(pfad: str):
    """Datei-SQLite ohne ``fsync`` je Commit — eine Wegwerf-Datenbank braucht keine
    Absturzsicherheit, und 33 Tagesläufe mit je einem Commit kosteten sonst die Hälfte der Zeit."""
    from sqlalchemy import event

    engine = create_async_engine(f"sqlite+aiosqlite:///{pfad}", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _schnell(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA synchronous=OFF")
        cur.execute("PRAGMA journal_mode=MEMORY")
        cur.close()

    return engine


async def _neue_db(pfad: str):
    """Eine Datei-Datenbank (sie wird für S2 kopiert) mit dem Schema des Produkts."""
    engine = _engine(pfad)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()


async def _oeffne_db(pfad: str):
    engine = _engine(pfad)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()


async def aggregiere_tage(db: AsyncSession, form: Form, anlage_id: int, tage) -> None:
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    for tag in tage:
        await aggregate_day(anlage, tag, db, source=Source.SCHEDULER, prefetched_tagesverlauf=_kurve(form))
        await db.commit()


# ── Schreibwege des abgeschlossenen Monats ──────────────────────────────────


async def schreibe_s1_aus_ha_laden(db: AsyncSession, anlage_id: int) -> dict:
    """S1: „Aus HA laden" → Formular-Nutzlast → ``create_monatsdaten`` → Nachlauf.

    Die Nutzlast bildet ``MonatsdatenForm.tsx::handleSubmit`` (:828-975) nach: die sichtbare
    Zeile „PV-Gesamtzähler aus Home Assistant" übernimmt ``basis["pv_erzeugung_kwh"]``
    (:237), die Gerätefelder die Werte aus ``investitionen[].felder`` (:851-917), jedes mit
    ``geprueft_gegen: {}``. Der Nachlauf (``_nachlauf_planen`` → ``_post_save_hintergrund``)
    läuft im Betrieb nach der Antwort in eigener Sitzung; hier wird sein Rechenteil
    (``run_post_monatsabschluss_aggregation``) in derselben Datenbank gerufen.
    """
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten

    antwort = await get_monatswerte(anlage_id, JAHR, JUNI, db)
    basis = {b.feld: b.differenz for b in antwort.basis}
    nutzlast: dict[str, Any] = {
        "anlage_id": anlage_id, "jahr": JAHR, "monat": JUNI,
        "einspeisung_kwh": basis["einspeisung_kwh"], "netzbezug_kwh": basis["netzbezug_kwh"],
        "geprueft_gegen": {},
    }
    if basis.get("pv_erzeugung_kwh") is not None:
        nutzlast["pv_erzeugung_kwh"] = basis["pv_erzeugung_kwh"]
    inv = {str(i.investition_id): {**{f.feld: f.differenz for f in i.felder}, "geprueft_gegen": {}}
           for i in antwort.investitionen}
    if inv:
        nutzlast["investitionen_daten"] = inv
    await create_monatsdaten(MonatsdatenCreate.model_validate(nutzlast), None, db)
    await _nachlauf(db, anlage_id)
    return nutzlast


async def schreibe_s2_sammelimport(db: AsyncSession, anlage_id: int) -> dict:
    """S2: HA-Statistik-Sammelimport des Juni, alle Felder (``import_ha_statistics``)."""
    from backend.api.routes.ha_statistics import ImportRequest, MonatFeldAuswahl, import_ha_statistics

    r = await import_ha_statistics(anlage_id, ImportRequest(monate=[MonatFeldAuswahl(jahr=JAHR, monat=JUNI)]), db)
    await db.commit()
    return {"erfolg": r.erfolg, "importiert": r.importiert, "fehler": list(r.fehler)}


async def schreibe_s3_von_hand(db: AsyncSession, form: Form, anlage_id: int, ids: dict[str, int]) -> dict:
    """S3: Standalone-Monatsabschluss von Hand — die abgelesenen Zählerstände.

    Der Anwender trägt ein, was seine Zähler zeigen: Einspeisung, Netzbezug, den
    Anlagenzähler (falls die Anlage einen hat) und je Gerät mit eigenem Zähler dessen
    Monatsmenge. Geräte ohne Zähler bleiben leer — wie im Formular.
    """
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten

    n = len(TAGE_JUNI)
    nutzlast: dict[str, Any] = {
        "anlage_id": anlage_id, "jahr": JAHR, "monat": JUNI,
        "einspeisung_kwh": soll_einspeisung(form, n), "netzbezug_kwh": soll_netzbezug(n),
        "geprueft_gegen": {},
    }
    if form.gesamt is not None:
        nutzlast["pv_erzeugung_kwh"] = tagesmenge(form.gesamt) * n
    inv = {str(ids[g.name]): {"pv_erzeugung_kwh": tagesmenge(g.rate) * n, "geprueft_gegen": {}}
           for g in form.geraete if g.zaehler}
    if inv:
        nutzlast["investitionen_daten"] = inv
    await create_monatsdaten(MonatsdatenCreate.model_validate(nutzlast), None, db)
    await _nachlauf(db, anlage_id)
    return nutzlast


async def _nachlauf(db: AsyncSession, anlage_id: int) -> None:
    from backend.services.monatsabschluss_aggregator import run_post_monatsabschluss_aggregation

    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    await run_post_monatsabschluss_aggregation(anlage, JAHR, JUNI, db)
    await db.commit()


# ── Messfunktionen je Sicht ─────────────────────────────────────────────────
#
# Jede liefert ein flaches Dict mit Zahlen (oder None) — die Proben vergleichen nur Zahlen.


def _r(x) -> Optional[float]:
    return None if x is None else round(float(x), 4)


def _namen(ids: dict[str, int]) -> dict[str, str]:
    return {str(v): k for k, v in ids.items()}


async def miss_tage(db: AsyncSession, anlage_id: int, ids: dict[str, int], tage) -> dict:
    """Tag: gespeicherte Tageszeile (``komponenten_kwh``, Stundenachse) und Cockpit → Tag
    (``GET /energie-profil/{id}/tage-werte`` = ``baue_tage_werte``)."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    rev = _namen(ids)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    tw = {z.datum: z for z in await baue_tage_werte(db, anlage, tage[0], tage[-1])}
    out = {}
    for tag in tage:
        tz = (await db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum == tag))).scalar_one_or_none()
        teps = (await db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage_id, TagesEnergieProfil.datum == tag))).scalars().all()
        keys = {}
        for k, v in ((tz.komponenten_kwh or {}) if tz else {}).items():
            pre, _, i = str(k).rpartition("_")
            if pre in ("pv", "bkw") and i in rev and isinstance(v, (int, float)):
                keys[rev[i]] = keys.get(rev[i], 0.0) + float(v)
        z = tw.get(tag)
        out[tag.isoformat()] = {
            "tz_vorhanden": tz is not None,
            "keys": {k: _r(v) for k, v in keys.items()},
            "summe_keys": _r(sum(keys.values())),
            "stunden_pv": _r(sum(r.pv_kw or 0.0 for r in teps)),
            "tw_erzeugung": _r(getattr(z, "erzeugung", None)) if z else None,
            # Cockpit → Tag teilt die Erzeugung in „PV-Anlage" und „Balkonkraftwerk" (Σ der Tages-Keys).
            "tw_pv_anlage": _r(getattr(z, "pv_anlage", None)) if z else None,
            "tw_bkw": _r(getattr(z, "bkw", None)) if z else None,
            "tw_erzeuger": {rev.get(k, k): _r(v) for k, v in ((getattr(z, "erzeuger_kwh", None) or {}) if z else {}).items()},
            "tw_eigenverbrauch": _r(getattr(z, "eigenverbrauch", None)) if z else None,
            "tw_einspeisung": _r(getattr(z, "einspeisung", None)) if z else None,
            "tw_netzbezug": _r(getattr(z, "netzbezug", None)) if z else None,
            "tw_autarkie": _r(getattr(z, "autarkie", None)) if z else None,
        }
    return out


async def miss_cockpit_monat(db: AsyncSession, anlage_id: int, monat: int) -> dict:
    """Cockpit → Monat (``get_aktueller_monat``)."""
    import backend.api.routes.aktueller_monat as am

    r = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=monat, db=db)
    return {"pv": _r(r.pv_erzeugung_kwh), "bkw": _r(r.bkw_erzeugung_kwh), "ev": _r(r.eigenverbrauch_kwh),
            "bkw_ersparnis": _r(getattr(r, "bkw_ersparnis_euro", None)),
            # Geld-Sichten (Auftrag Achsen-Matrix 2, F13a/N-588): gemessen, nicht bewertet.
            "ev_ersparnis": _r(getattr(r, "ev_ersparnis_euro", None)),
            "einsp": _r(r.einspeisung_kwh), "netz": _r(r.netzbezug_kwh), "autarkie": _r(r.autarkie_prozent),
            "pv_quelle": ((r.feld_quellen or {}).get("pv_erzeugung_kwh") or {}).get("quelle")
            if isinstance((r.feld_quellen or {}).get("pv_erzeugung_kwh"), dict)
            else getattr((r.feld_quellen or {}).get("pv_erzeugung_kwh"), "quelle", None)}


async def miss_fakten(db: AsyncSession, anlage_id: int, ids: dict[str, int], monat: int, *,
                      tageswerte: bool = False) -> Optional[dict]:
    """Monats-Fakten (``lade_monats_fakten``) — ``tageswerte``: mit Tageswert-Rückfall."""
    from backend.services.monats_fakten import lade_monats_fakten

    rev = _namen(ids)
    fk = await lade_monats_fakten(db, anlage_id, von=(JAHR, monat), bis=(JAHR, monat),
                                  inkl_nur_tageswerte=tageswerte)
    if not fk:
        return None
    e, b = fk[0].erzeugung, fk[0].bkw
    je = {rev.get(str(i), str(i)): _r(w.pv_erzeugung_kwh) for i, w in e.pv_je_modul.items()}
    for i, v in b.erzeugung_je_investition.items():
        je[rev.get(str(i), str(i))] = _r((je.get(rev.get(str(i), str(i))) or 0.0) + v)
    return {"pv": _r(e.pv_kwh), "pv_module": _r(e.pv_module_kwh), "bkw": _r(e.bkw_kwh),
            "bkw_anteil": _r(e.bkw_aus_anlagenwert_kwh), "vollstaendig": e.pv_vollstaendig,
            "je_geraet": je, "ev": _r(fk[0].kennzahlen.eigenverbrauch_kwh)}


async def miss_aggregiert(db: AsyncSession, anlage_id: int, monat: int, *, voll: bool) -> Optional[dict]:
    """Auswertungen → Tabelle (``voll=False``) bzw. Cockpit → Jahr → Verlauf (``voll=True``:
    ``inkl_ohne_zaehlerzeile`` + ``inkl_nur_tageswerte``, ``CockpitJahrV4.tsx:119-123``)."""
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    zeilen = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=JAHR, inkl_ohne_zaehlerzeile=voll,
                                               inkl_nur_tageswerte=voll, db=db)
    z = next((z for z in zeilen if z.monat == monat), None)
    if z is None:
        return None
    return {"pv": _r(z.pv_erzeugung_kwh), "pv_module": _r(z.pv_module_kwh), "bkw": _r(z.bkw_kwh),
            "bkw_anteil": _r(z.bkw_aus_anlagenwert_kwh), "ev": _r(z.eigenverbrauch_kwh),
            "einsp": _r(z.einspeisung_kwh), "netz": _r(z.netzbezug_kwh), "autarkie": _r(z.autarkie_prozent),
            "direkt": _r(z.direktverbrauch_kwh), "speicher_ladung": _r(getattr(z, "speicher_ladung_kwh", None)),
            "ev_ersparnis": _r(getattr(z, "ev_ersparnis_euro", None)),
            "sonstige": _r(getattr(z, "sonstige_erzeugung_kwh", None)),
            # Cockpit → Jahr → Verlauf stapelt `pvAnlage = pv_module_kwh` und `bkw = bkw_kwh`
            # (`JahrVerlaufChart.tsx::baueJahrChartDaten`, :70-71).
            "segmente": _r((z.pv_module_kwh or 0.0) + (z.bkw_kwh or 0.0))}


async def miss_jahr(db: AsyncSession, anlage_id: int) -> dict:
    """Cockpit → Jahr (Route ``get_cockpit_jahr`` = ``baue_jahr``, Uhr als ``heute``)."""
    from backend.services.jahres_aggregat import baue_jahr

    j = await baue_jahr(db, anlage_id, JAHR, heute=JETZT.date())
    monate = {m["monat"]: m for m in j["monate"]}
    kopf = j["kopf"] if isinstance(j["kopf"], dict) else j["kopf"].model_dump()
    return {"monate": {m: {"pv": _r(d.get("pv_erzeugung_kwh")), "ev": _r(d.get("eigenverbrauch_kwh")),
                           "autarkie": _r(d.get("autarkie_prozent")), "einsp": _r(d.get("einspeisung_kwh")),
                           "netz": _r(d.get("netzbezug_kwh"))} for m, d in monate.items()},
            "kopf_pv": _r(kopf.get("pv_erzeugung_kwh"))}


async def miss_uebersicht(db: AsyncSession, anlage_id: int) -> dict:
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    u = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=JAHR, db=db)
    return {"pv": _r(u.pv_erzeugung_kwh), "ev": _r(u.eigenverbrauch_kwh), "autarkie": _r(u.autarkie_prozent),
            "einsp": _r(getattr(u, "einspeisung_kwh", None)), "netz": _r(getattr(u, "netzbezug_kwh", None)),
            "spez": _r(u.spezifischer_ertrag_kwh_kwp), "bkw": _r(u.bkw_erzeugung_kwh),
            "ev_ersparnis": _r(getattr(u, "ev_ersparnis_euro", None)), "co2": _r(getattr(u, "co2_pv_kg", None))}


async def miss_pv_strings(db: AsyncSession, anlage_id: int, ids: dict[str, int]) -> dict:
    """Komponenten → PV-Strings: Jahr 2026 (Monat Juni je Gerät) und Gesamtlaufzeit."""
    from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit

    rev = _namen(ids)
    j = await get_pv_strings(anlage_id=anlage_id, jahr=JAHR, db=db)
    g = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    juni = {}
    for s in j.strings:
        mw = next((m for m in s.monatswerte if m.monat == JUNI), None)
        juni[rev.get(str(s.investition_id), s.bezeichnung)] = _r(mw.ist_kwh if mw else None)
    return {
        "jahr_je_geraet": {rev.get(str(s.investition_id), s.bezeichnung): _r(s.ist_jahr_kwh) for s in j.strings},
        "juni_je_geraet": juni,
        "jahr_summe": _r(j.ist_gesamt_kwh),
        "gesamt_je_geraet": {rev.get(str(s.investition_id), s.bezeichnung): _r(s.ist_gesamt_kwh) for s in g.strings},
        "gesamt_jahreswerte": {rev.get(str(s.investition_id), s.bezeichnung):
                               {str(jw.jahr): _r(jw.ist_kwh) for jw in s.jahreswerte} for s in g.strings},
        "gesamt_summe": _r(g.ist_gesamt_kwh),
    }


def komponenten_verlauf(aggregiert: list[dict], module: list[dict], pv_strings: Optional[dict]) -> dict:
    """Komponenten → PV-Anlage → Verlauf, die zwei Stapel je Jahr — Nachbildung von
    ``frontend/src/v4/komponentenAdapter.tsx::pvVerlauf`` (:269-345), unverändert bis auf die
    Anzeige-Rundung (``Math.round`` je Segment), die hier entfällt.

    * Erzeugung = Σ Module (``strings[].jahreswerte[].ist_kwh``, sobald der String-Endpoint
      für irgendein Modul Werte liefert; sonst ``pv_module_kwh`` nach kWp, :312-316) +
      ``bkw_kwh`` + ``sonstige_erzeugung_kwh`` (``ERZ_ZUSATZ``, :247-258).
    * Verwendung = ``direktverbrauch_kwh`` + ``speicher_ladung_kwh`` + ``einspeisung_kwh`` (:283-290).

    ``module`` = die aktiven ``pv-module`` der Anlage (:388), mit ``id`` und ``kwp``.
    """
    gemessen: dict[int, dict[int, float]] = {}
    for s in (pv_strings or {}).get("strings", []):
        gemessen[s["investition_id"]] = {jw["jahr"]: jw["ist_kwh"] for jw in s["jahreswerte"]}
    hat_modulwerte = any(m["id"] in gemessen for m in module)
    total_kwp = sum(m["kwp"] or 0.0 for m in module)
    jahre: dict[int, dict[str, float]] = {}
    for r in aggregiert:
        y = jahre.setdefault(r["jahr"], {"erz": 0.0, "verw": 0.0, "zusatz": 0.0})
        y["erz"] += r["pv_module_kwh"] if r["pv_module_kwh"] is not None else (r["pv_erzeugung_kwh"] or 0.0)
        y["verw"] += (r["direktverbrauch_kwh"] or 0.0) + (r["speicher_ladung_kwh"] or 0.0) + (r["einspeisung_kwh"] or 0.0)
        y["zusatz"] += (r["bkw_kwh"] or 0.0) + (r["sonstige_erzeugung_kwh"] or 0.0)
    out = {}
    for j, y in jahre.items():
        if hat_modulwerte:
            module_summe = sum(gemessen.get(m["id"], {}).get(j, 0.0) for m in module)
        else:
            module_summe = sum(y["erz"] * (m["kwp"] or 0.0) / total_kwp for m in module) if total_kwp else 0.0
        out[j] = {"erzeugung": _r(module_summe + y["zusatz"]), "verwendung": _r(y["verw"])}
    return out


async def miss_komponenten_verlauf(db: AsyncSession, anlage_id: int) -> dict:
    from backend.api.routes.cockpit.pv_strings import get_pv_strings_gesamtlaufzeit
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.core.investition_kennwerte import get_erzeuger_kwp

    agg = [z.model_dump() for z in await list_monatsdaten_aggregiert(
        anlage_id=anlage_id, jahr=None, inkl_ohne_zaehlerzeile=False, inkl_nur_tageswerte=False, db=db)]
    strings = (await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)).model_dump()
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()
    module = [{"id": i.id, "kwp": get_erzeuger_kwp(i)} for i in invs if i.aktiv and i.typ == "pv-module"]
    return komponenten_verlauf(agg, module, strings).get(JAHR, {"erzeugung": None, "verwendung": None})


async def miss_pdf(db: AsyncSession, anlage_id: int, ids: dict[str, int]) -> dict:
    """Jahresbericht-PDF-Kontext 2026: Monatstabelle (Juni) und String-Vergleich je Gerät."""
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    rev_bez = {k: k for k in ids}
    ctx = await build_jahresbericht_context(db, anlage_id, JAHR)
    juni = next((z for z in ctx.get("monats_zeilen") or [] if z.get("monat") == JUNI), {})
    sv = {rev_bez.get(s["bezeichnung"], s["bezeichnung"]): _r(s.get("ist_kwh")) for s in ctx.get("string_vergleiche") or []}
    return {"pv": _r(juni.get("pv_erzeugung_kwh")), "ev": _r(juni.get("eigenverbrauch_kwh")),
            "ev_ersparnis": _r(juni.get("ev_ersparnis_euro")),
            "autarkie": _r(juni.get("autarkie_prozent")), "string_je_geraet": sv,
            "string_summe": _r(sum(v for v in sv.values() if v is not None)) if sv else None}


async def miss_ha_export(db: AsyncSession, anlage_id: int) -> dict:
    from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors

    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    werte = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=JETZT)}
    return {"pv": _r(werte.get("pv_erzeugung_gesamt_kwh")), "ev": _r(werte.get("eigenverbrauch_gesamt_kwh")),
            "autarkie": _r(werte.get("autarkie_prozent")), "spez": _r(werte.get("spezifischer_ertrag_kwh_kwp")),
            "ev_ersparnis": _r(werte.get("eigenverbrauch_ersparnis_euro")), "co2": _r(werte.get("co2_ersparnis_kg"))}


async def miss_community(db: AsyncSession, anlage_id: int) -> dict:
    from backend.services.community_service import prepare_community_data

    c = await prepare_community_data(db, anlage_id) or {}
    mw = next((m for m in c.get("monatswerte") or [] if m.get("jahr") == JAHR and m.get("monat") == JUNI), {})
    return {"pv": _r(mw.get("ertrag_kwh")), "bkw": _r(mw.get("bkw_erzeugung_kwh")),
            "ev": _r(mw.get("eigenverbrauch_kwh")), "autarkie": _r(mw.get("autarkie_prozent")),
            "co2": _r(mw.get("co2_vermieden_kg"))}


async def miss_checker(db: AsyncSession, anlage_id: int) -> dict:
    from backend.services.daten_checker._helpers import _CheckHelpers

    class _Helfer(_CheckHelpers):
        def __init__(self, db):
            self.db = db

    anlage = (await db.execute(select(Anlage).options(selectinload(Anlage.investitionen))
                               .where(Anlage.id == anlage_id))).scalar_one()
    return {"pv": _r((await _Helfer(db)._get_pv_erzeugung_map(anlage)).get((JAHR, JUNI)))}


async def miss_vorschau(db: AsyncSession, anlage_id: int) -> dict:
    """Import-Vorschau: was eedc für den Juni lokal führt (``vorhandene_werte``)."""
    from backend.api.routes.ha_statistics import get_import_vorschau

    v = await get_import_vorschau(anlage_id, db)
    m = next((m for m in v.monate if m.jahr == JAHR and m.monat == JUNI), None)
    if m is None:
        return {"pv": None, "aktion": None}
    lokal = (m.vorhandene_werte or {}).get("PV Erzeugung Gesamt")
    return {"pv": _r(lokal), "aktion": m.aktion, "grund": m.grund,
            "ha_pv": _r((m.ha_werte or {}).get("PV Erzeugung Gesamt"))}


# ── Eine Form messen ────────────────────────────────────────────────────────


@dataclass
class Messung:
    """Alle Zahlen einer Form, je Datenstand (``HA`` · ``SA``) und Schreibweg (``S1``–``S3``)."""

    form: Form
    tage: dict[str, dict] = field(default_factory=dict)
    laufend: dict[str, dict] = field(default_factory=dict)
    vor: dict[str, dict] = field(default_factory=dict)
    nach: dict[str, dict] = field(default_factory=dict)
    nutzlast: dict[str, dict] = field(default_factory=dict)


async def _sichten_laufend(db, aid, ids) -> dict:
    return {
        "tage": await miss_tage(db, aid, ids, TAGE_JULI),
        "monat": await miss_cockpit_monat(db, aid, JULI),
        "jahr": (await miss_jahr(db, aid))["monate"].get(JULI),
        "verlauf": await miss_aggregiert(db, aid, JULI, voll=True),
    }


async def _sichten_vor(db, aid, ids) -> dict:
    return {
        "monat": await miss_cockpit_monat(db, aid, JUNI),
        "verlauf": await miss_aggregiert(db, aid, JUNI, voll=True),
        "fakten_tw": await miss_fakten(db, aid, ids, JUNI, tageswerte=True),
    }


async def _sichten_nach(db, aid, ids, *, mit_ha: bool) -> dict:
    jahr = await miss_jahr(db, aid)
    out = {
        "monat": await miss_cockpit_monat(db, aid, JUNI),
        "fakten": await miss_fakten(db, aid, ids, JUNI),
        "uebersicht": await miss_uebersicht(db, aid),
        "jahr": jahr["monate"].get(JUNI),
        "jahr_kopf": jahr["kopf_pv"],
        "tabelle": await miss_aggregiert(db, aid, JUNI, voll=False),
        "verlauf": await miss_aggregiert(db, aid, JUNI, voll=True),
        "pv_strings": await miss_pv_strings(db, aid, ids),
        "komp_verlauf": await miss_komponenten_verlauf(db, aid),
        "pdf": await miss_pdf(db, aid, ids),
        "ha_export": await miss_ha_export(db, aid),
        "community": await miss_community(db, aid),
        "checker": await miss_checker(db, aid),
    }
    if mit_ha:
        out["vorschau"] = await miss_vorschau(db, aid)
    return out


async def messe_ha(form: Form, m: Messung) -> None:
    """Datenstand HA: Seed + Tage einmal; der Stand vor dem Abschluss wird kopiert, damit S1
    und S2 auf bitgleichen Datenbanken schreiben."""
    import shutil
    import tempfile

    verz = tempfile.mkdtemp(prefix="eedc-pv-matrix-")
    try:
        basis = f"{verz}/ha.db"
        engine, db = await _neue_db(basis)
        svc = seed_ha(form)
        try:
            aid, ids = await seed_anlage(db, form)
            with _umgebung(svc):
                await aggregiere_tage(db, form, aid, TAGE_JUNI + TAGE_JULI)
                m.tage["HA"] = await miss_tage(db, aid, ids, TAGE_JUNI + TAGE_JULI)
                m.laufend["HA"] = await _sichten_laufend(db, aid, ids)
        finally:
            await db.close()
            await engine.dispose()
        for weg in ("S1", "S2"):
            pfad = f"{verz}/{weg}.db"
            shutil.copyfile(basis, pfad)
            engine, db = await _oeffne_db(pfad)
            try:
                with _umgebung(svc):
                    m.vor[weg] = await _sichten_vor(db, aid, ids)
                    if weg == "S1":
                        m.nutzlast[weg] = await schreibe_s1_aus_ha_laden(db, aid)
                    else:
                        m.nutzlast[weg] = await schreibe_s2_sammelimport(db, aid)
                    m.nach[weg] = await _sichten_nach(db, aid, ids, mit_ha=True)
            finally:
                await db.close()
                await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def messe_sa(form: Form, m: Messung) -> None:
    """Datenstand „Leistungs-Zuordnung ohne HA-Stunden": kein HA, Zählerstände in
    ``sensor_snapshots`` (Snapshot-Pfad), die Kurve trägt bei einem Anlagenzähler die
    Gesamtleistung (``_kurve``); S3 von Hand. Das ist NICHT jede Standalone-Anlage — eine reine
    MQTT-Anlage ohne ``live``-Zuordnung hat keine PV-Serie in der Kurve (Bauplan PV-Achse T2)."""
    import shutil
    import tempfile

    verz = tempfile.mkdtemp(prefix="eedc-pv-matrix-")
    try:
        engine, db = await _neue_db(f"{verz}/sa.db")
        try:
            aid, ids = await seed_anlage(db, form)
            await seed_snapshots(db, form, aid, ids)
            with _umgebung(_ha_aus()):
                await aggregiere_tage(db, form, aid, TAGE_JUNI + TAGE_JULI)
                m.tage["SA"] = await miss_tage(db, aid, ids, TAGE_JUNI + TAGE_JULI)
                m.laufend["SA"] = await _sichten_laufend(db, aid, ids)
                m.vor["S3"] = await _sichten_vor(db, aid, ids)
                m.nutzlast["S3"] = await schreibe_s3_von_hand(db, form, aid, ids)
                m.nach["S3"] = await _sichten_nach(db, aid, ids, mit_ha=False)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def messe_form(form: Form) -> Messung:
    """Beide Datenstände einer Form (Werkzeug für Auswertungen außerhalb der Proben)."""
    m = Messung(form)
    await messe_ha(form, m)
    await messe_sa(form, m)
    return m
