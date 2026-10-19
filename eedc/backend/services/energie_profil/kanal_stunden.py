"""Die Stunden eines Kanal-Tags für die Sichten — Mischzeilen aus Kanal-Stundentag und Stundenzeile
(HA-Bauform S3, Etappe E-S3-2; Bauplan §3 «Umhängen», §4 S3-R1/S3-R5/S3-R6).

**Der eine Tages-Leser der Stunden-Sichten** (``BENANNTE_TAGESLESER`` in ``test_kanal_lesen_waechter.py``): ``/stunden``,
``tage-werte`` (die stundengepaarten Größen) und ``monat`` (Heatmap, Profil, Spitzen, stundengepaarte Größen) holen die
Stunden eines Kanal-Tags hier — keine Route ruft ``services/kanal/stunden_leser.py`` oder ``stunden_adapter.py`` selbst.

**Je Gruppe, nicht je Tag halb/halb (S3-R1):** die Felder der Gruppen mit Wahl ``kanal`` (``KanalStunden.felder``:
``pv_kw · verbrauch_kw · einspeisung_kw · netzbezug_kw · batterie_kw · ueberschuss_kw · defizit_kw`` der Bilanz,
``waermepumpe_kw`` der WP, ``wallbox_kw`` der E-Mob) kommen aus dem Adapter (HAs ``change`` je Stunde, Komposition W2 je
Stunde); jedes andere Feld liest die Mischzeile aus der Stundenzeile ``TagesEnergieProfil`` — SoC, Wetter, Preise,
Zählwerke **und ``komponenten``** (der Leistungspfad, S3-R6/H-1 A).

**Nach Bahnen (S4-R-3b, seit E-S4-1).** Die Stunde ``h`` eines Kanal-Tags ist ihr Beginn (``[h, h+1)``), die
Stundenzeile beschriftet ihre Backward-Bahnen mit dem Ende. Die Mischzeile holt deshalb die **Backward-Bahnen**
(``komponenten``, Wetter, ``wp_starts_anzahl``, ``wp_betriebsstunden``, ``betriebsmodus_je_wp``, nicht gemischte
``*_kw``) aus der Bestandszeile ``slot_konvention.bestandszeile_fuer_stundenbeginn(D, h)`` — ``(D, h+1)``, für ``h = 23``
die Zeile 0 des Folgetags (der Aufrufer lädt einen Tag mehr, kein zweiter Abruf) — und die **Forward-Bahnen**
(``slot_konvention.FORWARD_FELDER``: SoC, SoC je Speicher, Preise) zeilengleich aus ``(D, h)``. ``spannen``: die Achsen
der Kanal-Gruppen aus den Kanal-Stunden (``spanne > 3600`` ⇒ ``{achse: n}``, dieselbe Form wie die Spalte), die übrigen
Achsen aus der herangezogenen Bestandszeile. Jede Mischzeile trägt ``raster = "beginn"`` — ``forward_werte_je_backward_
zeile`` paart sie zeilengleich.

**Welche Stunden es gibt:** eine Stunde mit einer der beiden Stundenzeilen oder mit einem Kanal-Wert. Fehlen beide (Tag
älter als die 730-Tage-Aufbewahrung, Bauplan §1 Nr. 4), trägt die Mischzeile die Kanal-Mengen, die übrigen Felder sind
leer; eine Stunde ohne Zeile in allen dreien ist keine Zeile (keine 0, S3-R2).

Schwesterdateien: ``services/kanal/stunden_leser.py`` (der Kanal-Stundentag), ``services/kanal/stunden_adapter.py``
(die Zeilenform), ``services/kanal/bilanz_leser.py`` (``kanal_tage``, ``mische_bilanz``).
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.energie import (
    SONSTIGES_KOMPONENTEN_PREFIX, WAERMEPUMPE_KOMPONENTEN_PREFIXE, WALLBOX_KOMPONENTEN_PREFIXE,
)
from backend.core.berechnungen.slot_konvention import FORWARD_FELDER, RASTER_BEGINN, bestandszeile_fuer_stundenbeginn

from backend.services.kanal.stunden_adapter import FELDER_JE_GRUPPE, KanalStunden, stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import (
    GRUPPE_BILANZ,
    GRUPPE_EMOB,
    GRUPPE_SONSTIGES,
    GRUPPE_WP,
    KanalStundentag,
    geraete_tageswerte,
    kanal_stundentag,
    kanal_stundentage,
    modus_strom_stunden,
)

#: Die Achsen der ``spannen``-Spalte je Gruppe (``core/berechnungen/spannen.py::ACHSEN``).
ACHSEN_JE_GRUPPE: dict[str, tuple[str, ...]] = {
    GRUPPE_BILANZ: ("pv", "einspeisung", "netzbezug", "batterie"),
    GRUPPE_WP: ("waermepumpe",),
    GRUPPE_EMOB: ("wallbox",),
    GRUPPE_SONSTIGES: ("sonstige",),
}
#: Felder des Adapters, die die Mischzeile NICHT aus ihm nimmt: ``komponenten`` bleibt der Leistungspfad (H-1 A),
#: ``spannen`` wird je Achse gemischt.
_NICHT_AUS_DEM_ADAPTER = frozenset({"komponenten", "spannen"})
#: Die Gruppen, deren Stunden ``tage-werte`` und ``monat`` lesen (L-1b → A): Bilanz und WP-Strom.
SICHTEN_GRUPPEN = (GRUPPE_BILANZ, GRUPPE_WP)


class Mischzeile:
    """Eine Stunde eines Kanal-Tags (Beginn-Raster): die Kanal-Felder aus dem Adapter, die Forward-Bahnen aus der
    Stundenzeile derselben Stunde ``(D, h)``, jedes andere Attribut aus der Bestandszeile, die die Stunde trägt
    (``bestandszeile_fuer_stundenbeginn``) — fehlt die jeweilige Zeile, ``None``."""

    __slots__ = ("datum", "stunde", "spannen", "raster", "_kanal", "_zeile", "_vorwaerts")

    def __init__(self, datum: date, stunde: int, kanal: dict, zeile: Any, spannen: Optional[dict],
                 vorwaerts: Any = None):
        self.datum = datum
        self.stunde = stunde
        self.spannen = spannen
        self.raster = RASTER_BEGINN
        self._kanal = kanal
        self._zeile = zeile
        self._vorwaerts = vorwaerts

    def __getattr__(self, name: str):
        kanal = object.__getattribute__(self, "_kanal")
        if name in kanal:
            return kanal[name]
        if name in FORWARD_FELDER:
            return getattr(object.__getattribute__(self, "_vorwaerts"), name, None)
        return getattr(object.__getattribute__(self, "_zeile"), name, None)


def aus_kanal_gruppe(zeile: Any, feld: str) -> bool:
    """Trägt die Zeile ``feld`` aus einer Kanal-Gruppe (Mischzeile, Gruppe mit Wahl ``kanal``)? Dann ist ein leerer Wert
    eine Stunde ohne Kanal-Zeile — ihre Menge steht nach HAs Lückenregel in der Folgestunde (S3-R2) — und kein Anlass für
    einen Rückfall auf den Leistungspfad (E-S4-3 H-2b, ``serien.geraete_spalte_kw`` #263 nur bei Wahl ``bestand``)."""
    return isinstance(zeile, Mischzeile) and feld in object.__getattribute__(zeile, "_kanal")


def kanal_achsen(tag: KanalStundentag) -> frozenset[str]:
    """Die ``spannen``-Achsen der Gruppen mit Wahl ``kanal``."""
    return achsen_der_gruppen(tag.gruppen)


def achsen_der_gruppen(gruppen: Iterable[str]) -> frozenset[str]:
    """Die ``spannen``-Achsen eines Gruppensatzes (die Gruppen mit Wahl ``kanal``)."""
    return frozenset(a for g in gruppen for a in ACHSEN_JE_GRUPPE.get(g, ()))


def mische_spannen(zeile: Any, kanal_spannen: Optional[dict], achsen: frozenset[str]) -> Optional[dict]:
    """Die Spannen der Kanal-Achsen aus den Kanal-Stunden, die der übrigen Achsen aus der Stundenzeile."""
    out = {a: n for a, n in (getattr(zeile, "spannen", None) or {}).items() if a not in achsen}
    out.update({a: n for a, n in (kanal_spannen or {}).items() if a in achsen})
    return out or None


def mische_stunden(datum: date, zeilen: Sequence[Any], tag: KanalStundentag, ks: KanalStunden) -> list[Mischzeile]:
    """Je Stunde (Beginn) eine Mischzeile — nur Stunden mit einer Stundenzeile oder einem Kanal-Wert. ``zeilen``: die
    Stundenzeilen des Tages UND des Folgetags (Slot 0 trägt die Stunde 23, S4-R-3b); andere Tage stören nicht."""
    return _mische(datum, zeilen, kanal_achsen(tag), ks)


def _mische(datum: date, zeilen: Sequence[Any], achsen: frozenset[str], ks: KanalStunden) -> list[Mischzeile]:
    """``mische_stunden`` mit den Achsen des Gruppensatzes (``achsen_der_gruppen``) statt des Kanal-Stundentags."""
    je_zeile = {(z.datum, z.stunde): z for z in zeilen}
    felder = sorted(ks.felder - _NICHT_AUS_DEM_ADAPTER)
    out: list[Mischzeile] = []
    for k in ks.zeilen:
        zeile = je_zeile.get(bestandszeile_fuer_stundenbeginn(datum, k.stunde))
        vorwaerts = je_zeile.get((datum, k.stunde))
        kanal = {f: getattr(k, f) for f in felder}
        if zeile is None and vorwaerts is None and all(v is None for v in kanal.values()):
            continue
        out.append(Mischzeile(datum, k.stunde, kanal, zeile, mische_spannen(zeile, k.spannen, achsen), vorwaerts))
    return out


async def kanal_stunden(
    db: AsyncSession, anlage_id: int, datum: date,
) -> Optional[tuple[KanalStundentag, KanalStunden]]:
    """Der Kanal-Stundentag und seine Zeilen — ``None``, wenn keine Gruppe des Tages Wahl ``kanal`` hat."""
    tag = await kanal_stundentag(db, anlage_id, datum)
    if not tag.gruppen:
        return None
    return tag, stunden_aus_kanaelen(tag)


async def stunden_des_tages(db: AsyncSession, anlage_id: int, datum: date, zeilen: Sequence[Any]) -> list:
    """``/stunden``: die Mischzeilen eines Tages mit Kanal-Gruppe, sonst die Stundenzeilen des Tages unverändert.
    ``zeilen``: die Stundenzeilen des Tages und des Folgetags (S4-R-3b), aufsteigend."""
    k = await kanal_stunden(db, anlage_id, datum)
    if k is None:
        return [z for z in zeilen if z.datum == datum]
    return mische_stunden(datum, zeilen, *k)


async def stunden_der_kanal_tage(
    db: AsyncSession, anlage_id: int, kanal_tage: Iterable[date], zeilen_je_tag: Mapping[date, Sequence[Any]],
    *, gruppen: Sequence[str] = SICHTEN_GRUPPEN,
) -> dict[date, list]:
    """``tage-werte``/``monat``: je Kanal-Tag der Bilanz (``bilanz_leser.kanal_tage``) die Mischzeilen — der Bereich
    über den Bereichs-Leser (``kanal_stundentage``: EIN Stunden-Stapel je Gruppe, Bauplan §10c L-1), gefragt nur nach
    Bilanz und WP (L-1b → A): diese Sichten lesen aus den Stunden nur die stundengepaarten Größen und den WP-Strom; die
    Felder der Geräte-Gruppe (``wallbox_kw``) kommen hier aus der Stundenzeile und werden nicht gelesen.
    ``zeilen_je_tag``: die Stundenzeilen je Tag, für den letzten Kanal-Tag auch die des Folgetags (S4-R-3b).
    ``gruppen``: die gefragten Gruppen — ``stunden_der_tage`` (S5-R1) fragt nach den Gruppen seines Lade-Hinweises.

    **Gemerkt je Prozess** (HA-Bauform S5 E-S5-1c, S5-R7): die Adapter-Zeilen je abgeschlossenem Tag
    (``adapter_der_tage``); die Mischzeile entsteht je Aufruf neu aus der Stundenzeile."""
    tage = sorted(kanal_tage)
    if not tage:
        return {}
    out: dict[date, list] = {}
    for d, (gruppensatz, ks) in (await adapter_der_tage(db, anlage_id, tage, gruppen)).items():
        zeilen = [*zeilen_je_tag.get(d, ()), *zeilen_je_tag.get(d + timedelta(days=1), ())]
        out[d] = _mische(d, zeilen, achsen_der_gruppen(gruppensatz), ks)
    return out


async def adapter_der_tage(db: AsyncSession, anlage_id: int, tage: Sequence[date],
                           gruppen: Sequence[str]) -> dict[date, tuple[frozenset[str], KanalStunden]]:
    """Je Tag aus ``tage`` mit einer Gruppe mit Wahl ``kanal``: der Gruppensatz und die Adapter-Zeilen
    (``stunden_aus_kanaelen``) — abgeschlossene Tage aus dem Speicher je Prozess (``kanal/merken.py``, S5-R7a/b), die
    Fehltage über EINEN Aufruf des Bereichs-Lesers ``kanal_stundentage`` (EIN Stunden-Stapel je Gruppe, wie bisher)."""
    from backend.services.kanal import merken
    from backend.services.kanal.bilanz_leser import uhr

    async def _laden(fehl: list[date]) -> dict[date, tuple[frozenset[str], KanalStunden]]:
        alle = await kanal_stundentage(db, anlage_id, fehl[0], fehl[-1], gruppen=gruppen)
        return {d: (frozenset(t.gruppen), stunden_aus_kanaelen(t)) for d in fehl
                if (t := alle.get(d)) is not None and t.gruppen}

    return await merken.je_tag(db, merken.ADAPTER, anlage_id, tage, frozenset(gruppen), uhr(), _laden)


async def sonstiges_der_kanal_tage(db: AsyncSession, anlage_id: int, kanal_tage: Iterable[date]) -> dict[date, dict]:
    """``tage-werte``: je Kanal-Tag der Bilanz, an dem die Sonstiges-Gruppe Wahl ``kanal`` hat, ihre Tages-Δ je
    Ziel-Schlüssel (``komponenten_kwh``-Form) — Sonstiges und Abgabe im Kalendertag wie die Bilanz daneben (HA-Bauform
    S4, Bauplan §10a (4)); über den Bereich, keine Stunden."""
    return await geraete_tageswerte(db, anlage_id, sorted(kanal_tage), gruppe=GRUPPE_SONSTIGES)


def mische_sonstiges(komp_tag: Optional[dict], kanal_werte: Optional[Mapping[str, float]]) -> Optional[dict]:
    """Die Tageszeilen-Komponenten mit den Geräte-Schlüsseln aus den Kanälen (Sonstiges seit S4, seit S5b auch
    E-Mobilität und Wärmepumpe — ``komponenten_der_tage``; Kanal schlägt Tageszeile je Schlüssel); ohne Kanal-Werte
    unverändert."""
    if not kanal_werte:
        return komp_tag
    return {**(komp_tag or {}), **kanal_werte}


def stundenzeilen_mit_kanaelen(zeilen: Sequence[Any], kanal_stunden_je_tag: Mapping[date, list]) -> list:
    """Die Stundenzeilen eines Zeitraums, an jedem Kanal-Tag durch dessen Mischzeilen ersetzt — sortiert nach Tag und
    Stunde wie die Abfrage. Ohne Kanal-Tag dieselbe Liste."""
    if not kanal_stunden_je_tag:
        return list(zeilen)
    bestand = [z for z in zeilen if z.datum not in kanal_stunden_je_tag]
    alle = bestand + [m for ms in kanal_stunden_je_tag.values() for m in ms]
    return sorted(alle, key=lambda z: (z.datum, z.stunde))


# ── Die eine Ladefunktion der Stundenleser (HA-Bauform S5, Etappe E-S5-1; Bauplan S5 §3 (A), §4 S5-R1) ──────────────
#
# Jeder Leser, der Stundenmengen braucht (Speicher-Simulation, Ladepreis, Ladeblöcke, Verbrauchs-/Korrekturprofil,
# Preis-Aggregator, Grundlast, Prognose-IST, Wochenmuster …), holt seine Stundenzeilen hier statt mit einem eigenen
# `select(TagesEnergieProfil)`: an einem Kanal-Tag der Bilanz die Mischzeilen (Kanal-Mengen + Bahnen der Stundenzeile,
# S4-R-3b), an jedem anderen Tag die Stundenzeile unverändert. Damit rechnet jede Kennzahl an einem Kanal-Tag mit
# denselben Stunden wie *Cockpit → Tag* (`tage-werte`), und an einem Bestandstag bekommt der Leser dieselbe Zeile wie
# vorher (Proben `test_s5_stunden_der_tage.py`, Golden Master mess3/skala3).

#: Lade-Hinweis ``felder``: die Gruppe, deren Kanäle ein Feld der Mischzeile füllen. Die Bilanz ist immer dabei — sie
#: macht den Kanal-Tag (``bilanz_leser.kanal_tage``) und trägt die übrigen Mengen-Felder.
_GRUPPE_DES_FELDS = {"waermepumpe_kw": GRUPPE_WP, "wallbox_kw": GRUPPE_EMOB}
#: Ohne Lade-Hinweis: jede Gruppe mit Stundenfeldern (``stunden_adapter.FELDER_JE_GRUPPE``; Sonstiges hat keins).
_STUNDEN_GRUPPEN = (GRUPPE_BILANZ, GRUPPE_WP, GRUPPE_EMOB)
#: Spalten jeder Projektion: Ordnung, Paarung (``created_at`` — Bestandsgrenze N-387) und ``spannen`` (Zählerlücken, §2;
#: ``mische_spannen``).
_IMMER = ("datum", "stunde", "created_at", "spannen")


def gruppen_des_hinweises(felder: Optional[Iterable[str]]) -> tuple[str, ...]:
    """Die Gruppen, nach denen ``stunden_der_tage`` den Bereichs-Leser fragt (S5-R1, Lade-Hinweis)."""
    if felder is None:
        return _STUNDEN_GRUPPEN
    return (GRUPPE_BILANZ, *sorted({_GRUPPE_DES_FELDS[f] for f in felder if f in _GRUPPE_DES_FELDS}))


async def _stundenzeilen(db: AsyncSession, anlage_id: int, von: Optional[date], bis: Optional[date],
                         felder: Optional[Iterable[str]]) -> list:
    """Die Stundenzeilen ``von`` … ``bis`` + Folgetag, nach Tag und Stunde — ohne Hinweis volle Zeilen, mit Hinweis die
    Spalten-Projektion (``_IMMER`` + ``felder``; volle Zeilen deserialisierten je Zeile zwei JSON-Spalten, #333)."""
    from sqlalchemy import select

    from backend.models.tages_energie_profil import TagesEnergieProfil as TEP

    if felder is None:
        q = select(TEP)
    else:
        q = select(*(getattr(TEP, s) for s in (*_IMMER, *sorted(set(felder) - set(_IMMER)))))
    q = q.where(TEP.anlage_id == anlage_id)
    if von is not None:
        q = q.where(TEP.datum >= von)
    if bis is not None:
        q = q.where(TEP.datum <= bis + timedelta(days=1))
    res = await db.execute(q.order_by(TEP.datum, TEP.stunde))
    return list(res.scalars().all()) if felder is None else list(res.all())


async def _kanal_tage_ab_erstem_stand(db: AsyncSession, anlage_id: int, von: date, bis: date) -> dict:
    """``bilanz_leser.kanal_tage(von, bis)`` — aber erst ab dem Tag vor der ersten Kanalzeile der Anlage (davor kann kein Tag
    aus den Kanälen kommen), ohne jede Kanalzeile gar nicht gefragt. Dieselben Tage, ohne die Bestands-Historie Tag für Tag
    durchzuprüfen (Laufzeit, gemessen E-S5-1: zwölf Jahre ohne Kanal ≈ 0,3 s je Aufruf); im Lade-Kontext einmal je Anfrage."""
    from datetime import datetime

    from sqlalchemy import text

    from backend.services.kanal.bilanz_leser import kanal_tage
    from backend.services.kanal.lade_kontext import gemerkt

    async def _frage():
        return (await db.execute(text(
            "SELECT MIN((SELECT MIN(s.start_ts) FROM kanal_statistik s WHERE s.kanal_id = k.id)) "
            "FROM kanal k WHERE k.anlage_id = :a"), {"a": anlage_id})).scalar()

    ts = await gemerkt(db, ("erster_kanal_ts", anlage_id), _frage)
    if ts is None:
        return {}
    von = max(von, datetime.fromtimestamp(int(ts)).date() - timedelta(days=1))
    return await kanal_tage(db, anlage_id, von, bis) if von <= bis else {}


# ── Mitternachtsbündel in den Kanal-Stunden — Kandidaten-Tage ohne Mischzeilen (HA-Bauform S5, E-S5-1b, §10b H-3/H-4) ──
#
# Ob eine Mischzeile eines Kanal-Tags ein Mitternachtsbündel trägt, entscheiden die Spannen ihrer Kanal-Stunden
# (``stunden_adapter._spannen_der_stunde``: die Einträge mit ``achse_der_kategorie == achse``, ``lesen.stunden_stapel``:
# Spanne = Abstand zum vorigen Stand). Eine Kanal-Stunde ``h`` von D trägt Energie von vor dem Fensterbeginn (D-1 23:00,
# ``zeile_traegt_vortagsenergie``) nur, wenn der vorige Stand davor liegt — dann hat der Kanal im Fenster
# ``[D-1 23:00, D 00:00)`` keine Zeile und in D eine. Das ist eine Frage an die Stände, ohne Komposition: der Tagesvergleich
# (``vergleichstage``) rechnet die Mischzeilen nur an den Tagen, an denen sie zutrifft.


async def kanaele_der_achse(db: AsyncSession, anlage_id: int, von: date, bis: date, achse: str) -> set[str]:
    """Die Kanal-Schlüssel, deren Spannen die Achse ``achse`` einer Mischzeile tragen können: die Zähler mit
    ``achse_der_kategorie(kategorie) == achse`` — Bilanz-Achsen aus dem Bilanz-Stamm (``bilanz_leser._stamm``, dieselben
    Einträge wie ``tage_bilanz``), Geräte-Achsen aus allen Zählern des Tages (``bilanz_adapter.zaehler_eintraege``, wie
    ``stunden_leser._tageszaehler``) — über jede Menge aktiver Investitionen ``von`` … ``bis`` (eine Obermenge je Tag)."""
    from backend.core.berechnungen.spannen import achse_der_kategorie
    from backend.services.kanal.bilanz_adapter import BILANZ_ACHSEN, zaehler_eintraege
    from backend.services.kanal.bilanz_leser import _stamm

    stamm = await _stamm(db, anlage_id)
    stichtage = {von} | {t for i in stamm.invs for t in (i.anschaffungsdatum,
                         i.stilllegungsdatum + timedelta(days=1) if i.stilllegungsdatum else None)
                         if t is not None and von < t <= bis}
    out: set[str] = set()
    for t in sorted(stichtage):
        aktiv = (lambda inv, t=t: inv.ist_aktiv_an(t))
        if achse in BILANZ_ACHSEN:
            eintraege = await stamm.eintraege(db, aktiv, t)
        else:
            eintraege = await zaehler_eintraege(db, stamm.anlage, {str(i.id): i for i in stamm.invs if aktiv(i)}, t)
        out |= {e.schluessel for e in eintraege if achse_der_kategorie(e.kategorie) == achse}
    return out


_LUECKE_SQL = """
WITH k(kid) AS (SELECT value FROM json_each(:kanaele)), g(j, fb, t, tn) AS (
    SELECT key, json_extract(value, '$[0]'), json_extract(value, '$[1]'), json_extract(value, '$[2]') FROM json_each(:tage)
)
SELECT DISTINCT g.j FROM k CROSS JOIN g
WHERE NOT EXISTS (SELECT 1 FROM kanal_statistik s WHERE s.kanal_id = k.kid AND s.start_ts >= g.fb AND s.start_ts < g.t
                  AND s.sum IS NOT NULL)
  AND EXISTS (SELECT 1 FROM kanal_statistik s WHERE s.kanal_id = k.kid AND s.start_ts >= g.t AND s.start_ts < g.tn
              AND s.sum IS NOT NULL)
"""


async def tage_mit_kanal_luecke_ueber_mitternacht(db: AsyncSession, anlage_id: int, von: date, bis: date,
                                                  achse: str) -> set[date]:
    """Die Tage ``von`` … ``bis``, an denen ein Mengen-Kanal der Achse (``kanaele_der_achse``) im Fenster
    ``[D-1 23:00, D 00:00)`` keine Zeile und in D eine hat — die notwendige Bedingung dafür, dass eine Kanal-Stunde von D
    ein Mitternachtsbündel trägt (Block oben). Eine Anweisung, keine Komposition; Obermenge, entschieden wird an den
    Mischzeilen."""
    import json
    from datetime import datetime, time

    from sqlalchemy import select, text

    from backend.models.kanal import ART_SUM, Kanal

    if von > bis:
        return set()
    keys = await kanaele_der_achse(db, anlage_id, von, bis, achse)
    if not keys:
        return set()
    kids = [k for (k,) in (await db.execute(select(Kanal.id).where(
        Kanal.anlage_id == anlage_id, Kanal.art == ART_SUM, Kanal.key.in_(keys)))).all()]
    if not kids:
        return set()
    tage = [von + timedelta(days=i) for i in range((bis - von).days + 1)]
    grenzen = [[int(datetime.combine(d - timedelta(days=1), time(23, 0)).timestamp()),
                int(datetime.combine(d, time(0, 0)).timestamp()),
                int(datetime.combine(d + timedelta(days=1), time(0, 0)).timestamp())] for d in tage]
    res = await db.execute(text(_LUECKE_SQL), {"kanaele": json.dumps(kids), "tage": json.dumps(grenzen)})
    return {tage[int(j)] for (j,) in res.all()}


async def stunden_der_tage(
    db: AsyncSession, anlage_id: int, von: Optional[date], bis: Optional[date], *,
    felder: Optional[Iterable[str]] = None,
) -> list:
    """Die Stundenzeilen ``von`` … ``bis`` (beide inklusive) in Tag/Stunde-Ordnung — **die Lesestelle der Stundenleser**
    (HA-Bauform S5, Bauplan §4 **S5-R1**).

    An jedem **Kanal-Tag der Bilanz** (Quellenwahl je Tag wie ``bilanz_leser.kanal_tage``, dieselbe Wahl wie
    ``tage-werte``) stehen statt der Stundenzeilen die Mischzeilen des Tages (``mische_stunden``: Kanal-Mengen der
    gefragten Gruppen, Backward-Bahnen aus der Bestandszeile ``(D, h+1)``, Forward-Bahnen zeilengleich — **S4-R-3b**; die
    Zeilen des Folgetags holt die Funktion selbst); an jedem anderen Tag die Stundenzeile unverändert. Der Bereich läuft
    über den Bereichs-Leser (``kanal_stundentage``: EIN Stunden-Stapel je Gruppe) — dieselbe Mischung wie ``tage-werte``
    und ``monat`` (``stunden_der_kanal_tage`` + ``stundenzeilen_mit_kanaelen``, keine zweite Mischlogik).

    **Paarung:** jede Mischzeile trägt ``raster = "beginn"`` — wer Menge und Forward-Bahn verrechnet
    (``slot_konvention.forward_werte_je_backward_zeile``), paart sie damit zeilengleich; die Bestandszeile paart weiter
    mit der Vorzeile (N-387). Das **Raster-Attribut übernimmt die Paarung**, der Leser schaltet nichts selbst um.

    ``felder`` ist ein **Lade-Hinweis, kein Filter**: welche Attribute der Leser liest. Er bestimmt die gefragten
    Kanal-Gruppen (Bilanz immer; ``waermepumpe_kw`` ⇒ WP, ``wallbox_kw`` ⇒ E-Mob) und lädt die Stundenzeilen als
    Spalten-Projektion (``datum``, ``stunde``, ``created_at``, ``spannen`` + ``felder``); ohne Hinweis volle Zeilen und
    alle Stunden-Gruppen. Ein Feld außerhalb des Hinweises liest auf der Zeile ``None``.

    ``von``/``bis`` ``None``: der Bereich der Stundenzeilen (erste bzw. letzte Zeile) — ein Kanal-Tag außerhalb davon
    gehört nicht zur Antwort.

    **Im Lade-Kontext einer Anfrage einmal je Bereich und Lade-Hinweis** (``lade_kontext.gemerkt``, E-S5-1b): die
    Preis-Leser fragen je Tag einer Sicht denselben Monat (``ev_preis_zeitfenster_cent``, ``wirksamer_arbeitspreis_cent``
    aus ``baue_finanz_zeile``) — gehalten wird die Liste, ausgegeben eine Kopie; Schreiben leert den Kontext."""
    from backend.services.kanal.bilanz_leser import uhr
    from backend.services.kanal.lade_kontext import gemerkt

    felder = None if felder is None else tuple(felder)
    zeilen = await gemerkt(db, ("stunden_der_tage", anlage_id, von, bis, felder, uhr()),
                           lambda: _stunden_der_tage(db, anlage_id, von, bis, felder))
    return list(zeilen)


async def _stunden_der_tage(db: AsyncSession, anlage_id: int, von: Optional[date], bis: Optional[date],
                            felder: Optional[tuple[str, ...]]) -> list:
    """``stunden_der_tage`` ohne Lade-Kontext."""
    from collections import defaultdict

    alle = await _stundenzeilen(db, anlage_id, von, bis, felder)
    if von is None or bis is None:
        if not alle:
            return []
        von = alle[0].datum if von is None else von
        bis = alle[-1].datum if bis is None else bis
    zeilen = [z for z in alle if z.datum <= bis]
    kanal = await _kanal_tage_ab_erstem_stand(db, anlage_id, von, bis)
    if not kanal:
        return zeilen
    je_tag: dict[date, list] = defaultdict(list)
    for z in alle:
        je_tag[z.datum].append(z)
    return stundenzeilen_mit_kanaelen(zeilen, await stunden_der_kanal_tage(
        db, anlage_id, kanal, je_tag, gruppen=gruppen_des_hinweises(felder)))


# ── Tagesmengen der Tageszeile an Kanal-Tagen (S5 §3 (A) 11–15, 26): dieselbe Mischung wie `tage-werte` ────────────


async def _bilanz_gemischt(db: AsyncSession, anlage_id: int, von: date, bis: date,
                           komponenten_je_tag: Mapping[date, Optional[dict]]) -> dict[date, dict]:
    """Je Kanal-Tag der Bilanz ``von`` … ``bis``: ``komponenten_kwh`` mit den Bilanz-Schlüsseln aus ``kanal_tage`` (B-3,
    ``mische_komponenten`` — die Stelle von ``tage_werte._tagesbilanz``)."""
    from backend.services.kanal.bilanz_leser import bilanz_ziele, mische_komponenten

    kanal = await _kanal_tage_ab_erstem_stand(db, anlage_id, von, bis)
    if not kanal:
        return {}
    ziele = await bilanz_ziele(db, anlage_id, kanal)
    return {d: _MitZielen(mische_komponenten(komponenten_je_tag.get(d), k, ziele[d]), frozenset(ziele[d]))
            for d, k in kanal.items()}


class _MitZielen(dict):
    """Die gemischten Tageskomponenten eines Kanal-Tags samt den Ziel-Schlüsseln der Bilanz (``bilanz_ziele``) — die
    Schlüssel, die die Bilanz-Komposition trägt (``ist_bilanz_schluessel``)."""

    def __init__(self, werte: dict, ziele: frozenset):
        super().__init__(werte)
        self.ziele = ziele


async def pv_ist_je_tag(db: AsyncSession, anlage_id: int, tageszeilen: Sequence[Any]) -> dict[date, Optional[float]]:
    """**PV-IST je Tag — die eine Stelle der Prognose-Leser** (S5 §3 (A) 11–15: Prognose-Genauigkeit des HA-Exports,
    *Prognosen → Genauigkeit*, Lernfaktor). ``Σ PV/BKW`` (``summe_pv_bkw_kwh``) über ``komponenten_kwh`` des Tages — an
    einem Kanal-Tag der Bilanz gemischt wie ``tage-werte`` (PV-Träger aus ``kanal_tage``, B-3), sonst die Tageszeile.
    ``None``: kein Kanal-Tag und die Tageszeile trägt keine Komponenten. ``tageszeilen``: ``TagesZusammenfassung``-Zeilen
    (``datum``, ``komponenten_kwh``); die Prognose-Felder liest der Aufrufer weiter aus ihnen."""
    from backend.core.berechnungen import summe_pv_bkw_kwh

    if not tageszeilen:
        return {}
    komp = {z.datum: z.komponenten_kwh for z in tageszeilen}
    gemischt = await _bilanz_gemischt(db, anlage_id, min(komp), max(komp), komp)
    return {d: (summe_pv_bkw_kwh(gemischt[d]) if d in gemischt else (summe_pv_bkw_kwh(k) if k else None))
            for d, k in komp.items()}


async def verworfen_der_tage(db: AsyncSession, anlage_id: int, von: Optional[date], bis: Optional[date], *,
                             kanal: Optional[Iterable[date]] = None, leere_marken: bool = False) -> dict[date, dict]:
    """Die Regelmarke ``verworfen`` je Tag ``von`` … ``bis`` (nur Tage mit Marke) wie ``tage-werte``: an einem Kanal-Tag der
    Bilanz ohne die Bilanz-Achsen (``mische_verworfen`` — der Kanal verwirft nichts), sonst die Tageszeile. ``kanal``:
    die Kanal-Tage, wenn der Aufrufer sie schon kennt (sonst ``bilanz_leser.kanal_tage``; ``()`` = ungemischt).

    ``leere_marken`` (HA-Bauform S5, E-S5-2): auch die leere Marke ``{}`` zählt als Marke — die Tage, die nach der neuen
    Regel gerechnet sind (R9, ``verworfen IS NOT NULL``), nicht nur die mit verworfener Menge. Der Daten-Checker
    «Einspeisung über Erzeugung» prüft genau diese Tage."""
    from sqlalchemy import select

    from backend.models.tages_energie_profil import TagesZusammenfassung as TZ
    from backend.services.kanal.bilanz_leser import mische_verworfen

    q = select(TZ.datum, TZ.verworfen).where(TZ.anlage_id == anlage_id, TZ.verworfen.isnot(None))
    if von is not None:
        q = q.where(TZ.datum >= von)
    if bis is not None:
        q = q.where(TZ.datum <= bis)
    marken = {d: v for d, v in (await db.execute(q)).all() if leere_marken or v}
    if not marken:
        return {}
    if kanal is None:
        kanal = await _kanal_tage_ab_erstem_stand(db, anlage_id, min(marken), max(marken))
    kanal = set(kanal)
    return {d: (mische_verworfen(v) if d in kanal else v) for d, v in marken.items()}


#: Die Gruppen, deren ``komponenten_kwh``-Schlüssel ``komponenten_der_tage`` an einem Kanal-Tag aus den Kanälen mischt
#: (HA-Bauform S5, E-S5-3, Bauplan §10h 6). Die Bilanz mischt immer — sie macht den Kanal-Tag.
KOMPONENTEN_GRUPPEN = (GRUPPE_BILANZ, GRUPPE_SONSTIGES, GRUPPE_EMOB, GRUPPE_WP)

#: Die ``komponenten_kwh``-Präfixe je Geräte-Gruppe (``core/berechnungen/energie.py``) — für den Lade-Hinweis
#: ``gruppen_der_schluessel`` (E-S5-3 Nachzug M-1).
_PRAEFIXE_JE_GRUPPE = {GRUPPE_SONSTIGES: (SONSTIGES_KOMPONENTEN_PREFIX,), GRUPPE_EMOB: WALLBOX_KOMPONENTEN_PREFIXE,
                       GRUPPE_WP: WAERMEPUMPE_KOMPONENTEN_PREFIXE}


def gruppen_der_schluessel(schluessel: Iterable[str]) -> tuple[str, ...]:
    """Der Lade-Hinweis ``gruppen`` für ``komponenten_der_tage`` aus den ``komponenten_kwh``-Schlüsseln, die ein Leser
    liest (HA-Bauform S5b, E-S5-3 Nachzug M-1): die Bilanz (sie mischt immer) und jede Geräte-Gruppe, deren Präfix
    unter den Schlüsseln vorkommt. Eine Gruppe, deren Schlüssel der Leser nicht liest, lädt er nicht; eine, deren
    Schlüssel er liest, muss er mischen — an einem Kanal-Tag trägt die Tageszeile sie seit S5b nicht mehr."""
    s = tuple(schluessel)
    return (GRUPPE_BILANZ,) + tuple(g for g, p in _PRAEFIXE_JE_GRUPPE.items() if any(str(k).startswith(p) for k in s))


async def komponenten_der_tage(db: AsyncSession, anlage_id: int, von: date, bis: date,
                               komponenten_je_tag: Optional[Mapping[date, Optional[dict]]] = None,
                               *, gruppen: Sequence[str] = KOMPONENTEN_GRUPPEN,
                               ) -> dict[date, Optional[dict]]:
    """``komponenten_kwh`` je Tag ``von`` … ``bis`` — **die eine Mischung der Tageskomponenten** (HA-Bauform S5, E-S5-3,
    Bauplan §10h 6): an einem Kanal-Tag der Bilanz die Bilanz-Schlüssel aus ``kanal_tage`` (B-3) und je Geräte-Gruppe
    mit Wahl ``kanal`` (Sonstiges, E-Mobilität, Wärmepumpe — ihre eigene Tageswahl) deren Schlüssel aus den Kanälen — ein
    Schlüssel, den die Bilanz-Komposition trägt (Sonstiges-Erzeuger hinter dem Anlagenzähler), bleibt der der Komposition
    (``_ohne_bilanz``, Entscheid Gernot 19.10. H-2 → B)
    (``geraete_komponenten_der_kanal_tage``, «Kanal schlägt Tageszeile je Schlüssel»; ein Schlüssel ohne Kanal-Wert behält
    den Wert der Tageszeile, wie N-757 — außer bei der E-Mobilität: ihr gehört der ganze Präfix ``wallbox_*``/``eauto_*``,
    ``_ohne_emob``); sonst die Tageszeile. Ein Kanal-Tag ohne Tageszeile steht mit seinen
    Kanal-Schlüsseln drin. Seit S5b schreibt ``aggregate_day`` diese Schlüssel an Kanal-Tagen nicht mehr
    (``mengen_weiche``) — jeder Leser von ``komponenten_kwh`` mischt deshalb hier.

    ``gruppen``: ein **Lade-Hinweis** wie bei ``stunden_der_tage`` — die Geräte-Gruppen, deren Schlüssel der Aufrufer
    liest (``tage-werte`` liest nur Bilanz und Sonstiges; ohne Hinweis alle). V2H hat keinen Kanal und bleibt die
    Tageszeile.

    ``komponenten_je_tag`` ``None`` (HA-Bauform S5, E-S5-2): die Lesestelle lädt die Tageszeilen ``von`` … ``bis``
    selbst (jede Zeile, auch ohne Komponenten — ``None``), der Aufrufer liest keine Mengen-Spalte (Wächter S5-R6)."""
    if komponenten_je_tag is None:
        komponenten_je_tag = await _komponenten_der_tageszeilen(db, anlage_id, von, bis)
    out = dict(komponenten_je_tag)
    gemischt = await _bilanz_gemischt(db, anlage_id, von, bis, komponenten_je_tag)
    if gemischt:
        geraete, emob = await geraete_komponenten_der_kanal_tage(db, anlage_id, sorted(gemischt), gruppen)
        out.update({d: mische_sonstiges(dict(_ohne_emob(k) if d in emob else k), _ohne_bilanz(geraete.get(d), k.ziele))
                    for d, k in gemischt.items()})
    return out


def _ohne_bilanz(werte: Optional[Mapping[str, float]], ziele: frozenset) -> Optional[dict]:
    """Die Geräte-Schlüssel ohne die, die die Bilanz-Komposition selbst trägt (HA-Bauform S5b, E-S5-3, Entscheid Gernot
    19.10.2026 H-2 → B): ein Sonstiges-Erzeuger hinter dem Anlagenzähler (`sonstige_<id>` unter den Bilanz-Zielen) kommt
    aus der Komposition — «PV gesamt = alle Quellen», dieselbe Zahl wie *Cockpit → Tag* (`tages_eingaenge`); die
    Sonstiges-Gruppe liefert nur, was die Komposition nicht trägt (Verbraucher, Erzeuger ohne Anlagenzähler). Eine
    Vorrangregel: auf den Mess-Kopien und in den Matrizen ändert sie heute kein Ergebnis (GM unverändert; am W2-Ausfalltag
    tragen Komposition, Tagesliste und tag-detail dieselbe Zahl, die Sonstiges-Gruppe liefert dort keinen Wert)."""
    from backend.services.kanal.bilanz_leser import ist_bilanz_schluessel

    if not werte:
        return werte
    return {k: v for k, v in werte.items() if not ist_bilanz_schluessel(k, ziele)}


def _ohne_emob(komp: Optional[dict]) -> Optional[dict]:
    """Die Tageskomponenten ohne die Schlüssel der E-Mob-Gruppe (``wallbox_*``/``eauto_*``, Bauplan S5 §10h 1). Hat die
    E-Mob-Gruppe Wahl ``kanal``, gehört ihr der ganze Präfix: ein Schlüssel, den der Kanal nicht liefert, ist dort keine
    Lücke, sondern die Wallbox-Regel (N-555 — ein E-Auto, dessen Ladung die Wallbox zählt, steht nicht noch einmal da,
    wie in *Cockpit → Tag*, ``detail_aus_kanaelen``)."""
    from backend.core.berechnungen.energie import WALLBOX_KOMPONENTEN_PREFIXE

    if not komp:
        return komp
    return {k: v for k, v in komp.items() if not str(k).startswith(WALLBOX_KOMPONENTEN_PREFIXE)}


async def geraete_komponenten_der_kanal_tage(db: AsyncSession, anlage_id: int, tage: Sequence[date],
                                             gruppen: Sequence[str] = KOMPONENTEN_GRUPPEN,
                                             ) -> tuple[dict[date, dict], set[date]]:
    """Je Tag aus ``tage`` die ``komponenten_kwh``-Schlüssel der Geräte-Gruppen ``gruppen`` mit Wahl ``kanal`` aus den
    Kanälen (Ziel-Schlüssel, Vorzeichen der Beitragsschicht): Sonstiges und E-Mobilität über ``geraete_tageswerte``
    (Tages-Δ, keine Stunden — wie ``tage-werte`` seit S4), die Wärmepumpe über ``wp_komponenten_der_kanal_tage`` (Σ der
    Stunden — dieselben Werte, die *Cockpit → Tag* über ``tages_eingaenge`` liest). Je Gruppe ein Bereichs-Leser.
    Rückgabe ``(werte_je_tag, emob_tage)`` — die Tage mit E-Mob-Wahl ``kanal`` (ihnen gehört der Präfix, ``_ohne_emob``)."""
    out: dict[date, dict] = {}
    emob: set[date] = set()
    if not tage:
        return out, emob
    tage = sorted(tage)
    if GRUPPE_SONSTIGES in gruppen:
        for d, w in (await sonstiges_der_kanal_tage(db, anlage_id, tage)).items():
            out.setdefault(d, {}).update(w)
    if GRUPPE_EMOB in gruppen:
        for d, w in (await geraete_tageswerte(db, anlage_id, tage, gruppe=GRUPPE_EMOB)).items():
            out.setdefault(d, {}).update(w)
            emob.add(d)
    if GRUPPE_WP in gruppen:
        gefragt = set(tage)
        for d, w in (await wp_komponenten_der_kanal_tage(db, anlage_id, tage[0], tage[-1])).items():
            if d in gefragt:
                out.setdefault(d, {}).update(w)
    return out, emob


async def _komponenten_der_tageszeilen(db: AsyncSession, anlage_id: int, von: date, bis: date) -> dict[date, Optional[dict]]:
    """``{datum: komponenten_kwh}`` jeder Tageszeile ``von`` … ``bis`` (Reihenfolge der Abfrage, nach Tag)."""
    from sqlalchemy import select

    from backend.models.tages_energie_profil import TagesZusammenfassung as TZ

    res = await db.execute(select(TZ.datum, TZ.komponenten_kwh).where(
        TZ.anlage_id == anlage_id, TZ.datum >= von, TZ.datum <= bis).order_by(TZ.datum))
    return dict(res.all())


async def kanal_gruppen_der_tage(db: AsyncSession, anlage_id: int, von: date, bis: date) -> dict[date, tuple[str, ...]]:
    """Je Tag ``von`` … ``bis`` die Gruppen mit Wahl ``kanal`` (Bilanz, WP, E-Mob, Sonstiges) — EIN Bereichs-Leser
    (``kanal_stundentage``, dieselbe Wahl je Tag und Gruppe wie ``kanal_stundentag``). Tage ohne Kanal-Gruppe fehlen.
    Für die Werkbank-Vorschau (HA-Bauform S5, Bauplan §7, E-S5-2): sie nennt, welche Gruppen eines Tages ihre Mengen aus
    dem HA-Spiegel bzw. den eigenen Zählerständen lesen."""
    from backend.services.kanal.stunden_leser import kanal_stundentage

    ordnung = (GRUPPE_BILANZ, GRUPPE_WP, GRUPPE_EMOB, GRUPPE_SONSTIGES)
    tage = await kanal_stundentage(db, anlage_id, von, bis, gruppen=ordnung)
    return {d: tuple(g for g in ordnung if g in t.gruppen) for d, t in sorted(tage.items()) if t.gruppen}


# ── Wärme je Stunde (E-S3-2 Nachbau, Bauplan §10c H-1 → A): an einem WP-Kanal-Tag nur die QUELLE der Form ─────────
#
# Die Wärme-Sichten verteilen den Tag (den Balken, `tag-detail`) über eine gemessene Stundenform
# (`core/berechnungen/tages_stapel.py`, Σ Stunden = Balken per Konstruktion). An einem Tag, dessen WP-Gruppe die Kanäle
# decken, kommt die Form aus dem Kanal-Stundentag statt aus den 25 Ständen (`snapshot/stunden_leser.lade_stundenformen`):
# je Zähler `inv:<id>:<feld>` HAs `change`; die Modus-Stunden eines Geräts mit abgeleitetem Kanal aus
# `abgeleitet:inv:<id>:modus_strom_<art>_kwh` statt aus dem Leistungspfad; die Zählerspalte `wp_strom_kwh` aus dem
# Adapter. Stimmt der Balken mit dem Kanal-Tag überein (der HA-Normalfall), ist die Stunde genau das `change`. Ein
# Zähler ohne Kanal und ein Gerät ohne abgeleiteten Kanal behalten ihre heutige Form; jede Regel der Verteilung
# (Zweig 1/2, «nicht aufgeteilt», Bezug, Kälte, Restform) bleibt, wie sie ist — nur auf der getauschten Form.
# HA-Bauform S4 (E-S4-1, S4-R-3b): an einem WP-Kanal-Tag liegen alle Stunden auf dem Beginn — die Kanal-Formen ohnehin,
# eine Snapshot-Form eines Zählers ohne Kanal wird über `bestandszeile_fuer_stundenbeginn` umgelegt, die Modus-Stunden
# kommen nur aus den abgeleiteten Kanälen; die Tagesmengen dazu liefert `tages_eingaenge` (Σ Stunden ≡ Tag).

_ABGELEITET = re.compile(r"^abgeleitet:inv:(\d+):modus_strom_")


def _abgeleitete_geraete(wp) -> list[int]:
    """Die Geräte der WP-Gruppe mit abgeleitetem Kanal «Strom je Betriebsart» (E4d)."""
    return sorted({int(m.group(1)) for k in wp.mengen if (m := _ABGELEITET.match(k))})


def modus_stunden_aus_kanaelen(je_art: Mapping[int, Mapping[str, Sequence[Optional[float]]]]) -> dict[str, list]:
    """Je Gerät die Modus-Stunden (``ModusStunde`` je Stunde und Betriebsart) aus den abgeleiteten Kanälen: die Menge
    ist das ``change`` des Kanals, der Modus seine Betriebsart; der Rest hat keinen Modus (``None``, wie eine Stunde
    ohne Signal). Eine Stunde ohne Zeile trägt nichts."""
    from backend.core.berechnungen import ModusStunde
    from backend.core.berechnungen.modus_split import MODUS_STROM_REST

    out: dict[str, list] = {}
    for inv_id, arten in je_art.items():
        out[str(inv_id)] = [
            ModusStunde(kwh=werte[h], modus=None if art == MODUS_STROM_REST else art, stunde=h)
            for h in range(24) for art, werte in arten.items() if werte[h] is not None
        ]
    return out


def _mit_zeilen(je_art: Mapping[int, Mapping[str, Sequence[Optional[float]]]]) -> set[int]:
    """Die Geräte, deren abgeleitete Modus-Kanäle am Tag mindestens eine Zeile haben."""
    return {inv_id for inv_id, arten in je_art.items() if any(v is not None for w in arten.values() for v in w)}


async def modus_stunden_mit_rueckfall(db: AsyncSession, anlage_id: int, datum: date, wp) -> dict[str, list]:
    """Die Modus-Stunden eines WP-Kanal-Tags je Gerät — **die eine Weiche** (HA-Bauform S4 E-S4-3, Entscheid Master H-2a):
    hat der abgeleitete Kanal «Strom je Betriebsart» eines Geräts am Tag Zeilen, gewinnt er (wie seit E4d); sonst — ein Tag
    aus gespeicherten Ständen ohne Betriebsart-Mitschrift (Nachbau 2), HA-Spiegel vor der Mitschrift — die Modus-Spur der
    Stundenzeilen (``lade_modus_stunden_tag``), eine Backward-Bahn wie ``komponenten`` (S3-R6): Stunde ``h`` (Beginn) aus
    der Bestandszeile ``bestandszeile_fuer_stundenbeginn(D, h)`` (Stunde 23 aus Slot 0 des Folgetags, S4-R-3b)."""
    from backend.services.energie_profil.modus_split_monat import lade_modus_stunden_tag

    je_art = await modus_strom_stunden(db, anlage_id, datum, _abgeleitete_geraete(wp))
    kanal = {inv: arten for inv, arten in je_art.items() if inv in _mit_zeilen(je_art)}
    out = modus_stunden_aus_kanaelen(kanal)
    tep = {datum: (await lade_modus_stunden_tag(db, anlage_id, datum))[0],
           datum + timedelta(days=1): (await lade_modus_stunden_tag(db, anlage_id, datum + timedelta(days=1)))[0]}
    for inv in set(tep[datum]) | set(tep[datum + timedelta(days=1)]):
        if inv in out:
            continue
        reihe = []
        for h in range(24):
            tag, slot = bestandszeile_fuer_stundenbeginn(datum, h)
            reihe += [dataclasses.replace(m, stunde=h) for m in tep[tag].get(inv, ()) if m.stunde == slot]
        if reihe:
            out[inv] = reihe
    return out


async def _stundenformen_im_beginn_raster(db: AsyncSession, anlage, datum: date, zaehler: list) -> dict[str, list]:
    """Die Snapshot-Stundenformen (Backward-Slots) eines Zählers ohne Kanal auf das Beginn-Raster eines WP-Kanal-Tags
    gelegt — Stunde ``h`` aus ``slot_konvention.bestandszeile_fuer_stundenbeginn(D, h)`` (Stunde 23 aus Slot 0 des
    Folgetags), die eine Umrechnung (S4-R-3b)."""
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    if not zaehler:
        return {}
    je_tag = {datum: await lade_stundenformen(db, anlage, datum, zaehler),
              datum + timedelta(days=1): await lade_stundenformen(db, anlage, datum + timedelta(days=1), zaehler)}
    out: dict[str, list] = {}
    for key in set(je_tag[datum]) | set(je_tag[datum + timedelta(days=1)]):
        reihe = []
        for h in range(24):
            tag, slot = bestandszeile_fuer_stundenbeginn(datum, h)
            werte = je_tag[tag].get(key)
            reihe.append(werte[slot] if werte is not None else None)
        out[key] = reihe
    return out


async def wp_stundenformen(db: AsyncSession, anlage, datum: date, zaehler: Mapping[str, tuple]) -> tuple[dict, dict]:
    """``(formen_je_key, modus_stunden_je_inv)`` der Wärme-Sichten eines Tages — an einem WP-Kanal-Tag aus den
    Kanälen, sonst wie bisher (``lade_stundenformen``, ``lade_modus_stunden_tag``). ``zaehler``: ``{key: (key,
    sensor_id)}`` wie die Routen ihn bauen."""
    from backend.services.energie_profil.modus_split_monat import lade_modus_stunden_tag
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    wp = (await kanal_stundentag(db, anlage.id, datum)).gruppen.get(GRUPPE_WP)
    kanal = {k: list(m) for k, m in wp.mengen.items() if k in zaehler} if wp is not None else {}
    rest = [z for k, z in zaehler.items() if k not in kanal]
    formen = (await lade_stundenformen(db, anlage, datum, rest) if wp is None
              else await _stundenformen_im_beginn_raster(db, anlage, datum, rest))
    formen.update(kanal)
    if wp is not None:
        # HA-Bauform S4 (S4-R-3b): an einem WP-Kanal-Tag liegen die Stunden auf dem Beginn — die Modus-Stunden aus den
        # abgeleiteten Kanälen, ohne deren Zeilen (keine Betriebsart-Mitschrift, E-S4-3 H-2a) aus der Modus-Spur der
        # Stundenzeilen auf das Beginn-Raster gelegt: `modus_stunden_mit_rueckfall`.
        return formen, await modus_stunden_mit_rueckfall(db, anlage.id, datum, wp)
    modus, _ = await lade_modus_stunden_tag(db, anlage.id, datum)
    return formen, modus


# ── Tageswerte der Geräte an einem Kanal-Tag (HA-Bauform S4 E-S4-1, Bauplan §10a (1)/(2)) ──────────────────────────
#
# `tag-detail` und die beiden Wärme-Sichten lesen dieselben Tages-Eingänge: die Tageszeile (`komponenten_kwh`, ihr
# Fenster), die Tagesdetail-Werte (`get_tagesdetail_kwh`), die gemessenen Betriebsart-Zähler und den Modus-Split des
# Tages. An einem **Kanal-Tag** (Bilanz-Wahl `kanal`) stehen die Snapshot-Teilmengen im Fenster ihres Bezugs, dem
# Kalendertag (N-444 folgt dem Bezug); hat die WP- bzw. E-Mob-Gruppe am Tag Wahl `kanal` (ihre eigene Tageswahl, wie
# die Stundenform der Wärme-Sichten), kommen ihre Tageswerte aus dem
# Kanal-Stundentag (Σ der Stunden ≡ Tages-Δ, S3-R4) — dieselbe Auswahl wie der Tagespfad (Ausgabe-Tabelle
# `TAGESDETAIL_AUSGABE`, Gerätefeld oder Innengeräte, Wallbox-Regel N-555), nur die Menge ist HAs `change`. Bestandstage
# lesen unverändert. Eine Funktion für alle drei Sichten: `tages_eingaenge`.


@dataclass
class TagesEingaenge:
    """Die Tages-Eingänge der Geräte-Sichten eines Tages (``tages_eingaenge``)."""

    #: ``komponenten_kwh`` der Tageszeile; an einem Kanal-Tag die Bilanz-Schlüssel aus den Kanälen (E4a-2), an einem
    #: WP-Kanal-Tag auch die ``waermepumpe_<id>``-Schlüssel.
    tz_komp: Optional[dict]
    #: Fenster der Tageszeile (``tageszeile_ist_rueckwaerts``) — für Bestandstage.
    rueckwaerts: bool
    #: ``snapshot.aggregator.TagesDetail``.
    detail: Any
    gemessen_je_inv: dict
    splits: dict
    kanal_tag: bool = False
    #: Die WP-Gruppe des Tages kommt aus den Kanälen (Stunden im Beginn-Raster).
    wp_aus_kanal: bool = False
    emob_aus_kanal: bool = False

    @property
    def wp_kwh_je_inv(self) -> dict[str, float]:
        from backend.core.berechnungen import waermepumpe_kwh_je_investition

        return waermepumpe_kwh_je_investition(self.tz_komp or {})


def _summe_stunden(werte) -> float:
    return sum(v for v in werte if v is not None)


def _tages_delta(gs) -> dict[str, float]:
    """Je Kanal der Gruppe das Tages-Δ als Σ seiner Stunden (S3-R4: Σ Stunden ≡ Tag)."""
    return {k: sum(v for v in m if v is not None) for k, m in gs.mengen.items() if any(v is not None for v in m)}


def kanal_werte_je_inv(delta: Mapping[str, float], invs_by_id: Mapping[str, Any], datum: date, typen: frozenset[str],
                       wallbox_deckt: bool) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, dict[str, float]]]]:
    """Die Ausgabe-Schlüssel der Gerätetypen ``typen`` je Gerät aus den Kanal-Δ ``delta`` — ``({out: {inv_id: kWh}},
    {out: {inv_id: {feld: kWh}}})``, dieselbe Auswahl wie ``get_tagesdetail_kwh`` (``TAGESDETAIL_AUSGABE``,
    ``geraetefeld_oder_innengeraete``, E-Auto mit Parent bzw. unter einer Wallbox mit Zähler fällt heraus). Die eine Stelle
    für ``detail_aus_kanaelen`` (Tages-Sichten) und ``wp_werte_der_kanal_tage`` (Wärme-Verlauf, N-757)."""
    from backend.core.berechnungen.betriebsart_gemessen import geraetefeld_oder_innengeraete
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.keys import innengeraet_felder

    neu: dict[str, dict[str, float]] = {}
    felder_neu: dict[str, dict[str, dict[str, float]]] = {}
    for inv_id, inv in invs_by_id.items():
        typ = getattr(inv, "typ", None)
        if typ not in typen or not inv.ist_aktiv_an(datum):
            continue
        if typ == "e-auto" and (getattr(inv, "parent_investition_id", None) is not None or wallbox_deckt):
            continue
        praefix = f"inv:{inv_id}:"
        kandidaten = {k[len(praefix):] for k in delta if k.startswith(praefix)}
        for (t, feld), out in TAGESDETAIL_AUSGABE.items():
            if t != typ:
                continue
            werte_geraet = {k: delta[praefix + k] for k in (feld, *innengeraet_felder(feld, kandidaten))
                            if praefix + k in delta}
            d = geraetefeld_oder_innengeraete(werte_geraet, feld)
            if d is None:
                continue
            neu.setdefault(out, {})[inv_id] = neu.get(out, {}).get(inv_id, 0.0) + d
            felder_neu.setdefault(out, {}).setdefault(inv_id, {}).update(werte_geraet)
    return neu, felder_neu


def detail_aus_kanaelen(detail, delta: Mapping[str, float], invs_by_id: Mapping[str, Any], datum: date,
                        typen: frozenset[str], wallbox_deckt: bool):
    """``TagesDetail`` mit den Ausgabe-Schlüsseln der Gerätetypen ``typen`` aus den Kanal-Δ ``delta``
    (``kanal_werte_je_inv``). Ein Schlüssel ohne Kanal-Wert behält den Bestandswert."""
    import dataclasses

    neu, felder_neu = kanal_werte_je_inv(delta, invs_by_id, datum, typen, wallbox_deckt)
    if not neu:
        return detail
    werte = {**detail.werte, **{out: sum(v.values()) for out, v in neu.items()}}
    return dataclasses.replace(
        detail, werte=werte, werte_je_inv={**detail.werte_je_inv, **neu},
        felder_je_inv={**detail.felder_je_inv, **felder_neu},
        grund_je_feld={k: g for k, g in detail.grund_je_feld.items() if k not in werte},
    )


def _wp_komponenten(wp, delta: Mapping[str, float]) -> dict[str, float]:
    """Die ``waermepumpe_<id>``-Schlüssel der Tageszeile aus den Zählern der WP-Gruppe (Vorzeichen der Beitragsschicht)."""
    out: dict[str, float] = {}
    for e in wp.eintraege:
        if e.schluessel in delta:
            out[e.target_key] = out.get(e.target_key, 0.0) + e.vorzeichen * delta[e.schluessel]
    return out


async def wp_komponenten_der_kanal_tage(db: AsyncSession, anlage_id: int, von: date, bis: date) -> dict[date, dict[str, float]]:
    """Je Tag ``von`` … ``bis``, an dem die WP-Gruppe Wahl ``kanal`` hat, die ``waermepumpe_<id>``-Schlüssel der Tageszeile
    aus dem Kanal-Stundentag (Σ der Stunden, Vorzeichen der Beitragsschicht) — dieselben Werte, die ``tages_eingaenge``
    an einem WP-Kanal-Tag in ``tz_komp`` legt (``_wp_komponenten``). H-4 (HA-Bauform S4-Nachlauf): der Wärme-Verlauf
    (``waerme_verlauf._zaehlerstrom_je_tag``) liest damit denselben Tagesstrom wie *Cockpit → Tag*. Ein Bereichs-Leser
    (``kanal_stundentage``, nur die WP-Gruppe).

    **Im Lade-Kontext einer Anfrage einmal je Bereich** (``lade_kontext.gemerkt``, wie ``stunden_der_tage``; E-S5-3
    Nachzug M-1): ein Bereich, den ein in derselben Anfrage schon gelesener umfasst, wird aus diesem geschnitten statt
    neu gelesen — der Daten-Checker fragt über die Modus-Split-Regeln die WP-Tage zweier fast gleicher Bereiche
    (``lade_modus_split_je_monat``), ein Bereichs-Leser je Tag kostet ~2 ms. Der Wert eines Tages hängt nicht vom
    Bereich ab (je Tag dieselbe Wahl und dieselben Stunden); ausgegeben wird eine Kopie, Schreiben leert den Kontext."""
    from backend.services.kanal.bilanz_leser import uhr
    from backend.services.kanal.lade_kontext import gemerkt

    jetzt = uhr()
    gelesen = await gemerkt(db, ("wp_komponenten_bereiche", anlage_id, jetzt), _neue_liste)
    a, b = next(((a, b) for a, b in gelesen if a <= von and bis <= b), (von, bis))
    werte = await gemerkt(db, ("wp_komponenten_der_kanal_tage", anlage_id, a, b, jetzt),
                          lambda: _wp_komponenten_des_bereichs(db, anlage_id, a, b))
    if (a, b) not in gelesen:
        gelesen.append((a, b))
    return {d: dict(w) for d, w in werte.items() if von <= d <= bis}


async def _neue_liste() -> list:
    return []


async def _wp_komponenten_des_bereichs(db: AsyncSession, anlage_id: int, von: date,
                                       bis: date) -> dict[date, dict[str, float]]:
    """``wp_komponenten_der_kanal_tage`` ohne Lade-Kontext."""
    from backend.services.kanal.stunden_leser import kanal_stundentage

    tage = await kanal_stundentage(db, anlage_id, von, bis, gruppen=(GRUPPE_WP,))
    return {d: _wp_komponenten(t.gruppen[GRUPPE_WP], _tages_delta(t.gruppen[GRUPPE_WP]))
            for d, t in tage.items() if GRUPPE_WP in t.gruppen}


async def wp_werte_der_kanal_tage(db: AsyncSession, anlage_id: int, invs_by_id: Mapping[str, Any], von: date,
                                  bis: date) -> dict[date, dict[str, dict[str, float]]]:
    """Je Tag ``von`` … ``bis``, an dem die WP-Gruppe Wahl ``kanal`` hat, die WP-Ausgabe-Schlüssel je Gerät aus dem
    Kanal-Stundentag (``{datum: {out: {inv_id: kWh}}}``, Form des Bereichs-Lesers ``lade_tageswerte_je_geraet``) —
    dieselben Werte, die ``tages_eingaenge`` an einem WP-Kanal-Tag über ``detail_aus_kanaelen`` legt. N-757: Wärme, Kälte
    und Funktions-Achsen des Wärme-Verlaufs und der Wärme-Verteilung wie *Cockpit → Tag*. Ein Bereichs-Leser."""
    from backend.services.kanal.stunden_leser import kanal_stundentage

    tage = await kanal_stundentage(db, anlage_id, von, bis, gruppen=(GRUPPE_WP,))
    return {d: kanal_werte_je_inv(_tages_delta(t.gruppen[GRUPPE_WP]), invs_by_id, d, frozenset({"waermepumpe"}), False)[0]
            for d, t in tage.items() if GRUPPE_WP in t.gruppen}


def _gemessen_aus_delta(delta: Mapping[str, float]) -> dict[str, dict[str, float]]:
    """Die gemessenen Betriebsart-Zähler je Gerät (``{inv_id: {feld: kWh}}``) aus den Tages-Δ der WP-Gruppe."""
    from backend.core.betriebsmodus import ist_betriebsart_strom_feld

    gemessen: dict[str, dict[str, float]] = {}
    for key, wert in delta.items():
        teile = key.split(":", 2)
        if len(teile) == 3 and teile[0] == "inv" and ist_betriebsart_strom_feld(teile[2]):
            gemessen.setdefault(teile[1], {})[teile[2]] = wert
    return gemessen


def _kanal_splits(je_art, delta: Mapping[str, float], strom: Mapping[str, float]) -> dict:
    """Der Modus-Split je Gerät MIT Zeilen im abgeleiteten Kanal «Strom je Betriebsart» (``{inv_id_str: ModusSplit}``,
    auch leere): Σ der Stunden je erfasster Betriebsart, Abdeckung ``modus_abdeckung_h`` aus den Tages-Δ, Bezug der
    Kanal-Strom des Geräts — wie der Kanal-Monat (``kanal_split_ohne_abschluss``). Ein Gerät ohne Zeilen fehlt (sein
    Split bleibt der der Stundenzeilen, E-S4-3 H-2a)."""
    from backend.core.berechnungen.modus_split import MODUS_STROM_REST, ModusSplit
    from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD

    mit = _mit_zeilen(je_art)
    return {
        str(inv_id): ModusSplit(
            kwh_je_modus={art: _summe_stunden(w) for art, w in arten.items()
                          if art != MODUS_STROM_REST and any(v is not None for v in w)},
            abdeckung_h=float(delta.get(f"abgeleitet:inv:{inv_id}:{MODUS_ABDECKUNG_FELD}") or 0.0),
            bezug_kwh=strom.get(str(inv_id)),
        )
        for inv_id, arten in je_art.items() if inv_id in mit
    }


def splits_mit_kanal(splits_der_stundenzeilen: Optional[Mapping], kanal: Mapping) -> dict:
    """Die Splits eines WP-Kanal-Tags: ein Gerät mit Zeilen im abgeleiteten Kanal aus dem Kanal (``kanal``, auch ein
    leerer Split verdrängt den der Stundenzeilen), jedes andere aus den Stundenzeilen; leere Splits fallen (P4)."""
    splits = {i: sp for i, sp in (splits_der_stundenzeilen or {}).items() if i not in kanal}
    splits.update(kanal)
    return {i: sp for i, sp in splits.items() if not sp.ist_leer}


async def _wp_aus_kanaelen(db: AsyncSession, anlage, invs_by_id, datum: date, wp, e: TagesEingaenge) -> None:
    """Die WP-Tageswerte eines WP-Kanal-Tags: Strom je Gerät, Wärme/Kälte, gemessene Betriebsart, Modus-Split."""
    delta = _tages_delta(wp)
    e.tz_komp = {**(e.tz_komp or {}), **_wp_komponenten(wp, delta)}
    e.detail = detail_aus_kanaelen(e.detail, delta, invs_by_id, datum, frozenset({"waermepumpe"}), False)
    e.gemessen_je_inv = _gemessen_aus_delta(delta)
    # Der Modus-Split des Tages aus den abgeleiteten Kanälen «Strom je Betriebsart» (alle erfassten Betriebsarten, Σ der
    # Stunden) und ihrer Abdeckung ``modus_abdeckung_h`` — wie der Kanal-Monat (``kanal_split_ohne_abschluss``); Bezug
    # ist der Kanal-Strom des Geräts.
    je_art = await modus_strom_stunden(db, anlage.id, datum, _abgeleitete_geraete(wp))
    # E-S4-3 H-2a: ein Gerät ohne Zeilen im abgeleiteten Kanal behält den Tages-Split der Stundenzeilen (`e.splits` aus
    # `lade_modus_split_tag`, dieselbe Modus-Spur wie `modus_stunden_mit_rueckfall`); mit Zeilen gewinnt der Kanal.
    e.splits = splits_mit_kanal(e.splits, _kanal_splits(je_art, delta, e.wp_kwh_je_inv))
    e.wp_aus_kanal = True


@dataclass(frozen=True)
class WpModusTag:
    """Betriebsart-Eingänge eines WP-Kanal-Tags für die Wärme-Sichten über einen Bereich (``wp_modus_der_kanal_tage``)."""

    #: Die gemessenen Betriebsart-Zähler je Gerät aus den Kanälen (Kalendertag) — ersetzt die Zählerstände des Tages.
    gemessen_je_inv: dict
    #: Die Splits der Geräte mit Zeilen im abgeleiteten Kanal (``_kanal_splits``, auch leere) — ``splits_mit_kanal``.
    splits: dict


async def wp_modus_der_kanal_tage(db: AsyncSession, anlage_id: int, von: date, bis: date,
                                  strom_je_tag: Mapping[date, Mapping[str, float]]) -> dict[date, WpModusTag]:
    """**W-3 (HA-Bauform S5, S4 §10j, S5-R7):** je Tag ``von`` … ``bis``, an dem die WP-Gruppe Wahl ``kanal`` hat,
    Betriebsart-Strom und Modus-Split wie *Cockpit → Tag* (``tages_eingaenge`` → ``_wp_aus_kanaelen``): die gemessenen
    Betriebsart-Zähler aus den Tages-Δ der WP-Gruppe, der Split aus den abgeleiteten Kanälen «Strom je Betriebsart»
    (``modus_strom_stunden``, dieselbe Quelle wie der Kanal-Monat N-755 und die Stundenform
    ``modus_stunden_mit_rueckfall``); ``strom_je_tag``: der WP-Strom je Gerät des Tages (Bezug, Kanal-Strom an einem
    WP-Kanal-Tag). Der Wärme-Verlauf (``waerme_verlauf.lade_waerme_verlauf*``) nimmt sie an diesen Tagen statt der
    Zählerstände und der Modus-Spur der Stundenzeilen — Rückfall auf die Modus-Spur nur für ein Gerät ohne Zeile im
    abgeleiteten Kanal (H-2a). Ein Bereichs-Leser für die WP-Gruppe, je WP-Kanal-Tag mit abgeleitetem Kanal eine
    Anweisung für die Modus-Stunden."""
    from backend.services.kanal.stunden_leser import kanal_stundentage

    out: dict[date, WpModusTag] = {}
    for d, t in sorted((await kanal_stundentage(db, anlage_id, von, bis, gruppen=(GRUPPE_WP,))).items()):
        wp = t.gruppen.get(GRUPPE_WP)
        if wp is None:
            continue
        delta = _tages_delta(wp)
        geraete = _abgeleitete_geraete(wp)
        je_art = await modus_strom_stunden(db, anlage_id, d, geraete) if geraete else {}
        out[d] = WpModusTag(gemessen_je_inv=_gemessen_aus_delta(delta),
                            splits=_kanal_splits(je_art, delta, strom_je_tag.get(d) or {}))
    return out


async def tages_eingaenge(db: AsyncSession, anlage, invs_by_id: Mapping[str, Any], datum: date) -> TagesEingaenge:
    """Die Tages-Eingänge von ``tag-detail``, ``waerme-verlauf-stunden`` und ``waerme-verteilung?sicht=tag`` — die EINE
    Umschaltstelle Bestand ↔ Kanal dieser Sichten (HA-Bauform S4 E-S4-1, Bauplan §8: «Umschaltstelle = ein Aufruf»)."""
    from sqlalchemy import select

    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services.energie_profil import lade_modus_split_tag
    from backend.services.kanal.bilanz_leser import bilanz_ziele, kanal_tage, mische_komponenten
    from backend.services.snapshot.aggregator import get_betriebsart_strom_tageswerte, get_tagesdetail_kwh
    from backend.services.snapshot.boundary_range import tageszeile_ist_rueckwaerts
    from backend.services.snapshot.komponenten_beitraege import wallbox_deckt_ladung_ab

    # N-434/N-435: die Tageszeile zuerst — ihre Herkunft bestimmt an Bestandstagen das Fenster der WP-Zähler.
    tz_zeile = (await db.execute(
        select(TagesZusammenfassung.komponenten_kwh, TagesZusammenfassung.source_provenance,
               TagesZusammenfassung.verworfen).where(
            TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == datum,
        ))).one_or_none()
    tz_komp = tz_zeile[0] if tz_zeile else None
    kanal = (await kanal_tage(db, anlage.id, datum, datum)).get(datum)
    if kanal is not None:
        tz_komp = mische_komponenten(tz_komp, kanal, (await bilanz_ziele(db, anlage.id, [datum]))[datum])
    rueckwaerts = tageszeile_ist_rueckwaerts(tz_zeile[1] if tz_zeile else None, tz_zeile[2] if tz_zeile else None)
    kanal_tag = kanal is not None
    e = TagesEingaenge(
        tz_komp=tz_komp, rueckwaerts=rueckwaerts,
        detail=await get_tagesdetail_kwh(db, anlage, invs_by_id, datum, tageszeile_rueckwaerts=rueckwaerts,
                                         kanal_tag=kanal_tag),
        gemessen_je_inv=await get_betriebsart_strom_tageswerte(db, anlage, invs_by_id, datum, rueckwaerts=rueckwaerts,
                                                               kanal_tag=kanal_tag),
        splits=await lade_modus_split_tag(db, anlage.id, datum), kanal_tag=kanal_tag,
    )
    # Die Geräte-Gruppen folgen IHRER Tageswahl (wie `wp_stundenformen`/`wp_strom_je_stunde`), nicht der der Bilanz.
    gruppen = (await kanal_stundentag(db, anlage.id, datum)).gruppen
    if GRUPPE_WP in gruppen:
        await _wp_aus_kanaelen(db, anlage, invs_by_id, datum, gruppen[GRUPPE_WP], e)
    if GRUPPE_EMOB in gruppen:
        delta = _tages_delta(gruppen[GRUPPE_EMOB])
        deckt = wallbox_deckt_ladung_ab(invs_by_id.values(), anlage.sensor_mapping,
                                        ist_verfuegbar=lambda i, f: f"inv:{i.id}:{f}" in delta, datum=datum)
        e.detail = detail_aus_kanaelen(e.detail, delta, invs_by_id, datum, frozenset({"wallbox", "e-auto"}), deckt)
        e.emob_aus_kanal = True
    return e


async def wp_strom_je_stunde(db: AsyncSession, anlage_id: int, datum: date) -> dict[int, Optional[float]]:
    """Die Zählerspalte des Wärme-Verlaufs je Slot: an einem WP-Kanal-Tag ``waermepumpe_kw`` des Adapters (Σ
    ``change`` der WP-Strom-Zähler), sonst die Stundenzeile."""
    from sqlalchemy import select

    from backend.models.tages_energie_profil import TagesEnergieProfil

    tag = await kanal_stundentag(db, anlage_id, datum)
    if GRUPPE_WP in tag.gruppen:
        return {z.stunde: z.waermepumpe_kw for z in stunden_aus_kanaelen(tag).zeilen}
    return {r.stunde: r.waermepumpe_kw for r in (await db.execute(
        select(TagesEnergieProfil.stunde, TagesEnergieProfil.waermepumpe_kw).where(
            TagesEnergieProfil.anlage_id == anlage_id, TagesEnergieProfil.datum == datum,
        ))).all()}


# ── Tageskennzahlen und Tagesmengen aus den Kanal-Stunden (HA-Bauform S5, E-S5-3, Bauplan §10h 1/§4 S5-R2) ─────────
#
# Seit S5b schreibt `aggregate_day` an einem Kanal-Tag keine gefalteten Mengen mehr (`mengen_weiche`). Die Kennzahlen,
# die aus Mengen abgeleitet sind und in der Tageszeile BLEIBEN (Konzept §4.5 «Kennzahlen bleiben»: Performance Ratio,
# Einspeisung bei negativem Börsenpreis, PV-/Netz-/Speicher-Anteil der Heimladung), rechnet der Schreiber an einem
# Kanal-Tag aus den Kanal-Stunden — je Kennzahl EINE Stelle hier, dieselbe Layer-Formel wie im Bestand
# (`berechne_performance_ratio`, `stunde_aus_bilanzwerten`/`leite_pv_anteil_ab`). Die Kanal-Stunden liegen im
# Beginn-Raster (S4-R-3b): Stunde `h` = `[h, h+1)` paart direkt mit dem Börsenpreis `boerse[h]` derselben Stunde, ohne
# die Vortag-23-Verschiebung des Backward-Slots. Benannt: die Kennzahl ist ein Stand zum Schreibzeitpunkt; ändert sich der
# Spiegel später, heilt sie die nächste Neu-Aggregation (wie bisher).


def pv_ertrag_der_kanal_stunden(tag: KanalStundentag, ks: KanalStunden) -> Optional[float]:
    """Der PR-Zähler eines Kanal-Tags: Σ ``pv_kw`` der Kanal-Stunden (``ks`` = ``stunden_aus_kanaelen(tag)``, die Werte der
    Mischzeilen: PV + Erzeuger hinter dem Zähler) abzüglich des Sonstiges-Erzeugers derselben Stunde aus ihrer
    Bilanz-Komposition (Kategorie ``erzeugung_sonstiges`` — kein GTI-Bezug), wie ``aggregator.verrechne_stunde`` im
    Bestand. ``None`` ohne eine Stunde mit PV (keine Aussage, P4)."""
    if tag.bilanz is None:
        return None
    summe, erfasst = 0.0, False
    for z, k in zip(ks.zeilen, tag.bilanz.kompositionen):
        if z.pv_kw is None:
            continue
        summe += z.pv_kw - ((k.kat_summe.get("erzeugung_sonstiges") or 0.0) if k is not None else 0.0)
        erfasst = True
    return summe if erfasst else None


def performance_ratio_des_kanal_tags(tag: KanalStundentag, ks: KanalStunden, gti_summe_wh_m2: Optional[float],
                                     kwp: Optional[float]) -> Optional[float]:
    """**Performance Ratio eines Kanal-Tags** — die Stelle für ``aggregate_day`` und den Archiv-Nachzug: der Ertrag aus den
    Kanal-Stunden (``pv_ertrag_der_kanal_stunden``), die Einstrahlung (GTI) und die kWp wie im Bestand, die Formel
    ``berechne_performance_ratio``."""
    from backend.core.berechnungen.performance_ratio import berechne_performance_ratio

    return berechne_performance_ratio(pv_ertrag_der_kanal_stunden(tag, ks), gti_summe_wh_m2, kwp)


def einspeisung_neg_preis_der_kanal_stunden(ks: KanalStunden, boerse: Mapping[int, Optional[float]]) -> Optional[float]:
    """§51 EEG an einem Kanal-Tag: Σ ``einspeisung_kw`` der Kanal-Stunden ``h`` mit negativem Börsenpreis ``boerse[h]``
    (Beginn-Raster — Stunde und Preis beschreiben dasselbe Intervall, keine Verschiebung). Form der Tageszeile wie
    ``aggregator.tages_kennzahlen``: drei Stellen, ``None`` ohne Menge."""
    summe = 0.0
    for z in ks.zeilen:
        bp = boerse.get(z.stunde)
        if bp is not None and bp < 0 and z.einspeisung_kw is not None and z.einspeisung_kw > 0:
            summe += z.einspeisung_kw
    return round(summe, 3) if summe > 0 else None


def ladeanteil_der_kanal_stunden(ks: KanalStunden):
    """Der PV-/Netz-/Speicher-Anteil der Heimladung eines Kanal-Tags (N-141 Weg c, N-569) aus den Kanal-Stunden — je
    Stunde ``stunde_aus_bilanzwerten`` (Ladung ``wallbox_kw``, Netz, Einspeisung, Speicher-Spalte), mit der Bündel-Regel
    von ``aggregator.verrechne_stunde`` (trägt Ladung, PV oder Netzbezug mehr als eine reale Stunde, geht die Stunde als
    «nicht gedeckt» ein), dann ``leite_pv_anteil_ab``."""
    from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab, stunde_aus_bilanzwerten
    from backend.core.berechnungen.spannen import spanne

    stunden = []
    for z in ks.zeilen:
        gebuendelt = any(spanne(z.spannen, a) > 1 for a in ("wallbox", "pv", "netzbezug"))
        stunden.append(stunde_aus_bilanzwerten(
            ladung=z.wallbox_kw,
            netzbezug=None if gebuendelt else z.netzbezug_kw,
            einspeisung=None if gebuendelt else z.einspeisung_kw,
            batterie_spalte=z.batterie_kw,
        ))
    return leite_pv_anteil_ab(stunden)


#: Die Felder, die ``tagesbilanz.bilanz_aus_stundenrows`` liest (Überschuss/Defizit aus ``pv_kw``/``verbrauch_kw``).
UEBERSCHUSS_FELDER = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw")


def _ueberschuss_defizit(zeilen: Sequence[Any], tageszeilen_form: bool) -> tuple[Optional[float], Optional[float]]:
    """Überschuss und Defizit eines Kanal-Tags aus seinen Mischzeilen (``bilanz_aus_stundenrows``, Σ max(0, PV − Verbrauch)
    je Stunde) — ``(None, None)`` ohne PV oder Verbrauch (wie ``tage-werte``). ``tageszeilen_form``: wie ``aggregate_day``
    sie in die Tageszeile schrieb (zwei Stellen, 0 ⇒ ``None``, ``aggregator.nur_positiv``)."""
    from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows

    b = bilanz_aus_stundenrows(zeilen)
    if not (b.pv_erfasst and b.verbrauch_erfasst):
        return None, None
    if not tageszeilen_form:
        return b.ueberschuss_kwh, b.defizit_kwh
    return tuple(round(v, 2) if v > 0 else None for v in (b.ueberschuss_kwh, b.defizit_kwh))


async def ueberschuss_defizit_der_tage(
    db: AsyncSession, anlage_id: int, von: date, bis: date, *, felder: Sequence[str] = UEBERSCHUSS_FELDER,
    tageszeilen_form: bool = False,
) -> dict[date, tuple[Optional[float], Optional[float]]]:
    """**Überschuss und Defizit je Tag — die Lesestelle** (HA-Bauform S5, E-S5-3; Verallgemeinerung von
    ``anlage_steuerung._ueberschuss_heute`` aus E-S5-2): an einem Kanal-Tag der Bilanz aus seinen Mischzeilen
    (``stunden_der_tage``, dieselbe Layer-Funktion wie *Cockpit → Tag*), an jedem anderen Tag die Tageszeile
    (``TagesZusammenfassung.ueberschuss_kwh``/``defizit_kwh``). Seit S5b schreibt ``aggregate_day`` die beiden Spalten an
    Kanal-Tagen nicht mehr — Monats-Rollup, Tagesliste und HA-Export lesen hier.

    ``felder``: Lade-Hinweis für ``stunden_der_tage`` (mindestens ``UEBERSCHUSS_FELDER``) — ein Aufrufer, der die Stunden
    des Tages schon mit einem anderen Hinweis geladen hat, gibt seinen mit und liest sie aus dem Lade-Kontext.
    ``tageszeilen_form``: Kanal-Tage in der Form der Tageszeile (zwei Stellen, 0 ⇒ ``None``); sonst ungerundet."""
    from collections import defaultdict

    from sqlalchemy import select

    from backend.core.berechnungen.slot_konvention import ist_beginn_raster
    from backend.models.tages_energie_profil import TagesZusammenfassung as TZ

    kanal: dict[date, list] = defaultdict(list)
    for z in await stunden_der_tage(db, anlage_id, von, bis, felder=felder):
        if ist_beginn_raster(z):
            kanal[z.datum].append(z)
    res = await db.execute(select(TZ.datum, TZ.ueberschuss_kwh, TZ.defizit_kwh).where(
        TZ.anlage_id == anlage_id, TZ.datum >= von, TZ.datum <= bis))
    out = {d: (u, df) for d, u, df in res.all() if d not in kanal}
    out.update({d: _ueberschuss_defizit(zs, tageszeilen_form) for d, zs in kanal.items()})
    return out


__all__ = [
    "ACHSEN_JE_GRUPPE", "FELDER_JE_GRUPPE", "GRUPPE_BILANZ", "GRUPPE_EMOB", "GRUPPE_SONSTIGES", "GRUPPE_WP", "aus_kanal_gruppe", "modus_stunden_mit_rueckfall",
    "Mischzeile", "TagesEingaenge", "detail_aus_kanaelen", "tages_eingaenge", "kanal_achsen", "kanal_stunden", "mische_spannen", "mische_stunden",
    "achsen_der_gruppen", "adapter_der_tage", "mische_sonstiges", "modus_stunden_aus_kanaelen", "sonstiges_der_kanal_tage", "stunden_der_kanal_tage",
    "wp_komponenten_der_kanal_tage", "kanal_werte_je_inv", "wp_werte_der_kanal_tage",
    "stunden_des_tages", "stundenzeilen_mit_kanaelen", "stunden_der_tage", "gruppen_des_hinweises",
    "pv_ist_je_tag", "komponenten_der_tage", "verworfen_der_tage", "kanal_gruppen_der_tage",
    "WpModusTag", "splits_mit_kanal", "wp_modus_der_kanal_tage",
    "KOMPONENTEN_GRUPPEN", "gruppen_der_schluessel", "geraete_komponenten_der_kanal_tage", "pv_ertrag_der_kanal_stunden",
    "performance_ratio_des_kanal_tags", "einspeisung_neg_preis_der_kanal_stunden", "ladeanteil_der_kanal_stunden",
    "UEBERSCHUSS_FELDER", "ueberschuss_defizit_der_tage",
    "kanaele_der_achse", "tage_mit_kanal_luecke_ueber_mitternacht",
    "wp_strom_je_stunde", "wp_stundenformen",
]
