"""Die Stunden eines Kanal-Tags für die Sichten — Mischzeilen aus Kanal-Stundentag und Stundenzeile
(HA-Bauform S3, Etappe E-S3-2; Bauplan §3 «Umhängen», §4 S3-R1/S3-R5/S3-R6).

**Der eine Tages-Leser der Stunden-Sichten** (``BENANNTE_TAGESLESER`` in ``test_kanal_lesen_waechter.py``): ``/stunden``,
``tage-werte`` (die stundengepaarten Größen) und ``monat`` (Heatmap, Profil, Spitzen, stundengepaarte Größen) holen die
Stunden eines Kanal-Tags hier — keine Route ruft ``services/kanal/stunden_leser.py`` oder ``stunden_adapter.py`` selbst.

**Je Gruppe, nicht je Tag halb/halb (S3-R1):** die Felder der Gruppen mit Wahl ``kanal`` (``KanalStunden.felder``:
``pv_kw · verbrauch_kw · einspeisung_kw · netzbezug_kw · batterie_kw · ueberschuss_kw · defizit_kw`` der Bilanz,
``waermepumpe_kw`` der WP, ``wallbox_kw`` der E-Mob) kommen aus dem Adapter (HAs ``change`` je Stunde, Komposition W2 je
Stunde); jedes andere Feld liest die Mischzeile aus der Stundenzeile ``TagesEnergieProfil`` derselben Stunde — SoC,
Wetter, Preise, Zählwerke **und ``komponenten``** (der Leistungspfad, S3-R6/H-1 A). ``spannen``: die Achsen der
Kanal-Gruppen aus den Kanal-Stunden (``spanne > 3600`` ⇒ ``{achse: n}``, dieselbe Form wie die Spalte), die übrigen
Achsen aus der Stundenzeile.

**Welche Stunden es gibt:** eine Stunde mit Stundenzeile oder mit einem Kanal-Wert. Fehlt die Stundenzeile (Tag älter
als die 730-Tage-Aufbewahrung, Bauplan §1 Nr. 4), trägt die Mischzeile die Kanal-Mengen, die übrigen Felder sind leer;
eine Stunde ohne Zeile in beiden ist keine Zeile (keine 0, S3-R2).

Schwesterdateien: ``services/kanal/stunden_leser.py`` (der Kanal-Stundentag), ``services/kanal/stunden_adapter.py``
(die Zeilenform), ``services/kanal/bilanz_leser.py`` (``kanal_tage``, ``mische_bilanz``).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.kanal.stunden_adapter import KanalStunden, stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import (
    GRUPPE_BILANZ,
    GRUPPE_EMOB,
    GRUPPE_SONSTIGES,
    GRUPPE_WP,
    KanalStundentag,
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
    """Eine Stunde eines Kanal-Tags: die Kanal-Felder aus dem Adapter, jedes andere Attribut aus der Stundenzeile
    (fehlt sie, ``None``)."""

    __slots__ = ("datum", "stunde", "spannen", "_kanal", "_zeile")

    def __init__(self, datum: date, stunde: int, kanal: dict, zeile: Any, spannen: Optional[dict]):
        self.datum = datum
        self.stunde = stunde
        self.spannen = spannen
        self._kanal = kanal
        self._zeile = zeile

    def __getattr__(self, name: str):
        kanal = object.__getattribute__(self, "_kanal")
        if name in kanal:
            return kanal[name]
        return getattr(object.__getattribute__(self, "_zeile"), name, None)


def kanal_achsen(tag: KanalStundentag) -> frozenset[str]:
    """Die ``spannen``-Achsen der Gruppen mit Wahl ``kanal``."""
    return frozenset(a for g in tag.gruppen for a in ACHSEN_JE_GRUPPE.get(g, ()))


def mische_spannen(zeile: Any, kanal_spannen: Optional[dict], achsen: frozenset[str]) -> Optional[dict]:
    """Die Spannen der Kanal-Achsen aus den Kanal-Stunden, die der übrigen Achsen aus der Stundenzeile."""
    out = {a: n for a, n in (getattr(zeile, "spannen", None) or {}).items() if a not in achsen}
    out.update({a: n for a, n in (kanal_spannen or {}).items() if a in achsen})
    return out or None


def mische_stunden(datum: date, zeilen: Sequence[Any], tag: KanalStundentag, ks: KanalStunden) -> list[Mischzeile]:
    """Je Slot eine Mischzeile — nur Slots mit Stundenzeile oder mit einem Kanal-Wert."""
    je_stunde = {z.stunde: z for z in zeilen}
    felder = sorted(ks.felder - _NICHT_AUS_DEM_ADAPTER)
    achsen = kanal_achsen(tag)
    out: list[Mischzeile] = []
    for k in ks.zeilen:
        zeile = je_stunde.get(k.stunde)
        kanal = {f: getattr(k, f) for f in felder}
        if zeile is None and all(v is None for v in kanal.values()):
            continue
        out.append(Mischzeile(datum, k.stunde, kanal, zeile, mische_spannen(zeile, k.spannen, achsen)))
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
    """``/stunden``: die Mischzeilen eines Tages mit Kanal-Gruppe, sonst die Stundenzeilen unverändert."""
    k = await kanal_stunden(db, anlage_id, datum)
    return list(zeilen) if k is None else mische_stunden(datum, zeilen, *k)


async def stunden_der_kanal_tage(
    db: AsyncSession, anlage_id: int, kanal_tage: Iterable[date], zeilen_je_tag: Mapping[date, Sequence[Any]],
) -> dict[date, list]:
    """``tage-werte``/``monat``: je Kanal-Tag der Bilanz (``bilanz_leser.kanal_tage``) die Mischzeilen — der Bereich
    über den Bereichs-Leser (``kanal_stundentage``: EIN Stunden-Stapel je Gruppe, Bauplan §10c L-1), gefragt nur nach
    Bilanz und WP (L-1b → A): diese Sichten lesen aus den Stunden nur die stundengepaarten Größen und den WP-Strom; die
    Felder der Geräte-Gruppe (``wallbox_kw``) kommen hier aus der Stundenzeile und werden nicht gelesen."""
    tage = sorted(kanal_tage)
    if not tage:
        return {}
    alle = await kanal_stundentage(db, anlage_id, tage[0], tage[-1], gruppen=SICHTEN_GRUPPEN)
    out: dict[date, list] = {}
    for d in tage:
        tag = alle.get(d)
        if tag is not None and tag.gruppen:
            out[d] = mische_stunden(d, zeilen_je_tag.get(d, ()), tag, stunden_aus_kanaelen(tag))
    return out


def stundenzeilen_mit_kanaelen(zeilen: Sequence[Any], kanal_stunden_je_tag: Mapping[date, list]) -> list:
    """Die Stundenzeilen eines Zeitraums, an jedem Kanal-Tag durch dessen Mischzeilen ersetzt — sortiert nach Tag und
    Stunde wie die Abfrage. Ohne Kanal-Tag dieselbe Liste."""
    if not kanal_stunden_je_tag:
        return list(zeilen)
    bestand = [z for z in zeilen if z.datum not in kanal_stunden_je_tag]
    alle = bestand + [m for ms in kanal_stunden_je_tag.values() for m in ms]
    return sorted(alle, key=lambda z: (z.datum, z.stunde))


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


async def wp_stundenformen(db: AsyncSession, anlage, datum: date, zaehler: Mapping[str, tuple]) -> tuple[dict, dict]:
    """``(formen_je_key, modus_stunden_je_inv)`` der Wärme-Sichten eines Tages — an einem WP-Kanal-Tag aus den
    Kanälen, sonst wie bisher (``lade_stundenformen``, ``lade_modus_stunden_tag``). ``zaehler``: ``{key: (key,
    sensor_id)}`` wie die Routen ihn bauen."""
    from backend.services.energie_profil.modus_split_monat import lade_modus_stunden_tag
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    wp = (await kanal_stundentag(db, anlage.id, datum)).gruppen.get(GRUPPE_WP)
    kanal = {k: list(m) for k, m in wp.mengen.items() if k in zaehler} if wp is not None else {}
    formen = await lade_stundenformen(db, anlage, datum, [z for k, z in zaehler.items() if k not in kanal])
    formen.update(kanal)
    modus, _ = await lade_modus_stunden_tag(db, anlage.id, datum)
    if wp is not None:
        modus = {**modus, **modus_stunden_aus_kanaelen(
            await modus_strom_stunden(db, anlage.id, datum, _abgeleitete_geraete(wp)))}
    return formen, modus


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


__all__ = [
    "ACHSEN_JE_GRUPPE", "Mischzeile", "kanal_achsen", "kanal_stunden", "mische_spannen", "mische_stunden",
    "modus_stunden_aus_kanaelen", "stunden_der_kanal_tage", "stunden_des_tages", "stundenzeilen_mit_kanaelen",
    "wp_strom_je_stunde", "wp_stundenformen",
]
