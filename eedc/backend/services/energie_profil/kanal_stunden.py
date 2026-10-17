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

from backend.core.berechnungen.slot_konvention import FORWARD_FELDER, RASTER_BEGINN, bestandszeile_fuer_stundenbeginn

from backend.services.kanal.stunden_adapter import KanalStunden, stunden_aus_kanaelen
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
    return frozenset(a for g in tag.gruppen for a in ACHSEN_JE_GRUPPE.get(g, ()))


def mische_spannen(zeile: Any, kanal_spannen: Optional[dict], achsen: frozenset[str]) -> Optional[dict]:
    """Die Spannen der Kanal-Achsen aus den Kanal-Stunden, die der übrigen Achsen aus der Stundenzeile."""
    out = {a: n for a, n in (getattr(zeile, "spannen", None) or {}).items() if a not in achsen}
    out.update({a: n for a, n in (kanal_spannen or {}).items() if a in achsen})
    return out or None


def mische_stunden(datum: date, zeilen: Sequence[Any], tag: KanalStundentag, ks: KanalStunden) -> list[Mischzeile]:
    """Je Stunde (Beginn) eine Mischzeile — nur Stunden mit einer Stundenzeile oder einem Kanal-Wert. ``zeilen``: die
    Stundenzeilen des Tages UND des Folgetags (Slot 0 trägt die Stunde 23, S4-R-3b); andere Tage stören nicht."""
    je_zeile = {(z.datum, z.stunde): z for z in zeilen}
    felder = sorted(ks.felder - _NICHT_AUS_DEM_ADAPTER)
    achsen = kanal_achsen(tag)
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
) -> dict[date, list]:
    """``tage-werte``/``monat``: je Kanal-Tag der Bilanz (``bilanz_leser.kanal_tage``) die Mischzeilen — der Bereich
    über den Bereichs-Leser (``kanal_stundentage``: EIN Stunden-Stapel je Gruppe, Bauplan §10c L-1), gefragt nur nach
    Bilanz und WP (L-1b → A): diese Sichten lesen aus den Stunden nur die stundengepaarten Größen und den WP-Strom; die
    Felder der Geräte-Gruppe (``wallbox_kw``) kommen hier aus der Stundenzeile und werden nicht gelesen.
    ``zeilen_je_tag``: die Stundenzeilen je Tag, für den letzten Kanal-Tag auch die des Folgetags (S4-R-3b)."""
    tage = sorted(kanal_tage)
    if not tage:
        return {}
    alle = await kanal_stundentage(db, anlage_id, tage[0], tage[-1], gruppen=SICHTEN_GRUPPEN)
    out: dict[date, list] = {}
    for d in tage:
        tag = alle.get(d)
        if tag is not None and tag.gruppen:
            zeilen = [*zeilen_je_tag.get(d, ()), *zeilen_je_tag.get(d + timedelta(days=1), ())]
            out[d] = mische_stunden(d, zeilen, tag, stunden_aus_kanaelen(tag))
    return out


async def sonstiges_der_kanal_tage(db: AsyncSession, anlage_id: int, kanal_tage: Iterable[date]) -> dict[date, dict]:
    """``tage-werte``: je Kanal-Tag der Bilanz, an dem die Sonstiges-Gruppe Wahl ``kanal`` hat, ihre Tages-Δ je
    Ziel-Schlüssel (``komponenten_kwh``-Form) — Sonstiges und Abgabe im Kalendertag wie die Bilanz daneben (HA-Bauform
    S4, Bauplan §10a (4)); über den Bereich, keine Stunden."""
    return await geraete_tageswerte(db, anlage_id, sorted(kanal_tage), gruppe=GRUPPE_SONSTIGES)


def mische_sonstiges(komp_tag: Optional[dict], kanal_werte: Optional[Mapping[str, float]]) -> Optional[dict]:
    """Die Tageszeilen-Komponenten mit den Sonstiges-Schlüsseln aus den Kanälen (Kanal schlägt Tageszeile je
    Schlüssel); ohne Kanal-Werte unverändert."""
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


def detail_aus_kanaelen(detail, delta: Mapping[str, float], invs_by_id: Mapping[str, Any], datum: date,
                        typen: frozenset[str], wallbox_deckt: bool):
    """``TagesDetail`` mit den Ausgabe-Schlüsseln der Gerätetypen ``typen`` aus den Kanal-Δ ``delta`` — dieselbe
    Auswahl wie ``get_tagesdetail_kwh`` (``TAGESDETAIL_AUSGABE``, ``geraetefeld_oder_innengeraete``, E-Auto mit Parent
    bzw. unter einer Wallbox mit Zähler fällt heraus). Ein Schlüssel ohne Kanal-Wert behält den Bestandswert."""
    import dataclasses

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


async def _wp_aus_kanaelen(db: AsyncSession, anlage, invs_by_id, datum: date, wp, e: TagesEingaenge) -> None:
    """Die WP-Tageswerte eines WP-Kanal-Tags: Strom je Gerät, Wärme/Kälte, gemessene Betriebsart, Modus-Split."""
    from backend.core.berechnungen.modus_split import MODUS_STROM_REST, ModusSplit
    from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD, ist_betriebsart_strom_feld

    delta = _tages_delta(wp)
    e.tz_komp = {**(e.tz_komp or {}), **_wp_komponenten(wp, delta)}
    e.detail = detail_aus_kanaelen(e.detail, delta, invs_by_id, datum, frozenset({"waermepumpe"}), False)
    gemessen: dict[str, dict[str, float]] = {}
    for key, wert in delta.items():
        teile = key.split(":", 2)
        if len(teile) == 3 and teile[0] == "inv" and ist_betriebsart_strom_feld(teile[2]):
            gemessen.setdefault(teile[1], {})[teile[2]] = wert
    e.gemessen_je_inv = gemessen
    strom = e.wp_kwh_je_inv
    # Der Modus-Split des Tages aus den abgeleiteten Kanälen «Strom je Betriebsart» (alle erfassten Betriebsarten, Σ der
    # Stunden) und ihrer Abdeckung ``modus_abdeckung_h`` — wie der Kanal-Monat (``kanal_split_ohne_abschluss``); Bezug
    # ist der Kanal-Strom des Geräts.
    je_art = await modus_strom_stunden(db, anlage.id, datum, _abgeleitete_geraete(wp))
    # E-S4-3 H-2a: ein Gerät ohne Zeilen im abgeleiteten Kanal behält den Tages-Split der Stundenzeilen (`e.splits` aus
    # `lade_modus_split_tag`, dieselbe Modus-Spur wie `modus_stunden_mit_rueckfall`); mit Zeilen gewinnt der Kanal.
    mit = _mit_zeilen(je_art)
    splits = {i: sp for i, sp in (e.splits or {}).items() if int(i) not in mit}
    for inv_id, arten in je_art.items():
        if inv_id not in mit:
            continue
        splits[str(inv_id)] = ModusSplit(
            kwh_je_modus={art: _summe_stunden(w) for art, w in arten.items()
                          if art != MODUS_STROM_REST and any(v is not None for v in w)},
            abdeckung_h=float(delta.get(f"abgeleitet:inv:{inv_id}:{MODUS_ABDECKUNG_FELD}") or 0.0),
            bezug_kwh=strom.get(str(inv_id)),
        )
    e.splits = {i: sp for i, sp in splits.items() if not sp.ist_leer}
    e.wp_aus_kanal = True


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


__all__ = [
    "ACHSEN_JE_GRUPPE", "aus_kanal_gruppe", "modus_stunden_mit_rueckfall",
    "Mischzeile", "TagesEingaenge", "detail_aus_kanaelen", "tages_eingaenge", "kanal_achsen", "kanal_stunden", "mische_spannen", "mische_stunden",
    "mische_sonstiges", "modus_stunden_aus_kanaelen", "sonstiges_der_kanal_tage", "stunden_der_kanal_tage",
    "stunden_des_tages", "stundenzeilen_mit_kanaelen",
    "wp_strom_je_stunde", "wp_stundenformen",
]
