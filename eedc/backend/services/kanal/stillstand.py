"""Die Fenster-Lesestelle des Erfassungs-Stillstands (N-799, Bauplan Fassung 3, E-8) — die Erfassungs-Stillstände einer
Anlage aus den Bilanz-Zählern des Tagespfads, je Prozess gemerkt.

**Was hier geschieht.** Die Regel steht im Layer (``core/berechnungen/spannen.py::stillstand_fenster``: E-1 mit
Vorbedingung, Grob- und Häufigkeits-Sperre; ``erbt_marke`` für die Nebenachsen, E-2). Diese Datei liest nur die
Eingänge: die Bilanz-Zähler der Anlage (``bilanz_leser.bilanz_stamm`` — jeder Zähler, der an irgendeinem Tag zur Bilanz
gehört; ob er für einen Lauf erfasst ist, sagen seine Zeilen der 30 Tage davor) über die gefragten Monate und
**``RUECKBLICK_TAGE`` (90) davor** (``lesen.deltas_stapel``: HAs ``change`` und die Spanne je Stunde), dazu je markierbarem
Fenster die Zähler der Nebenachsen des Nachtragstags (``bilanz_adapter.zaehler_eintraege``). **Die Regel blickt nur
zurück** (Korrekturrunde S1): das Ergebnis eines Fensters hängt nur von den Zeilen bis zu seiner Nachtragsstunde ab,
höchstens 90 Tage zurück (Häufigkeit 60 Tage über Fenster, deren «erfasst» und Grob-Prüfung weitere 30 Tage
zurückblicken) — jeder Bereich, der einen Tag enthält, nennt für ihn dieselben Fenster (**Treffer = Kaltlauf**), und ein
späteres Fenster oder eine spätere Pause eines Zählers ändert kein früheres. Der Blick nach vorn dient nur dem Finden der
Nachtragsstunde für die Nullzeilen eines Tages (``NACHLAUF_TAGE``).

**Je Monat gemerkt** (wie ``merken.TAGESWAHL`` je Tag): je (Datenbank, Anlage, Monat) die Fenster, deren Nachtragsstunde
in den Monat fällt; fehlende Monate rechnet EIN Lesen je zusammenhängendem Block. Der Speicher hängt an der Invalidierung
von ``merken`` (``melde_speicher``): ein Schreiben in ``kanal_statistik`` ab Tag ``von`` verwirft jeden Monat, dessen
Fenster von Zeilen ab ``von`` abhängen können (Monatsende ≥ ``von``, also nur dieser und spätere Monate); eine Generation der Anlage (Anlage,
Investition, Kanal, Quelle geändert), eine andere MQTT-Schlüsselmenge oder ``VERFALL_S`` verwerfen ebenso. Innerhalb
einer Anfrage zusätzlich der Lade-Kontext. Nichts wird gespeichert (E-8: die Marke entsteht beim Mischen,
``energie_profil/stillstand_marke.py``).

**Benannte Grenzen:** einer länger als der Rückblick (90 Tage) wird abgeschnitten — sein ``k`` hängt dann am Lesebereich
(Treffer ≠ Kaltlauf nur für solche Fenster). Bis zu dieser Länge nennt ein Einzeltag dieselben Nullzeilen wie jeder Bereich
(``NACHLAUF_TAGE``, F3). Die Grob-Sperre blickt 30 Tage zurück: wird ein Zähler erst seit weniger als 30 Tagen grob
erfasst, enthält der Rückblick noch feine Δ, und die Sperre greift noch nicht (Saat L7) — dort hält meist die
Häufigkeits-Sperre; sonst trägt das Fenster die Marke (benannte Grenze am Wechselrand).

Schwesterdateien: ``merken.py`` (die Speicher der Tage), ``lesen.py`` (``deltas_stapel``), ``stunden_leser.py``.
"""

from __future__ import annotations

import dataclasses
import logging
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.spannen import (
    RUECKBLICK_S,
    STILLSTAND_ROLLE_JE_KATEGORIE,
    StillstandFenster,
    ZaehlerReihe,
    achse_der_kategorie,
    erbt_marke,
    stillstand_fenster,
)
from backend.services.kanal import merken
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.lesen import deltas_stapel, kanaele_laden

logger = logging.getLogger(__name__)

#: Rückblick des Lesebereichs in Tagen = wovon das Ergebnis eines Monats abhängt: seine Tage und so viele davor
#: (``spannen.RUECKBLICK_S``: Häufigkeit 60 Tage + «erfasst»/Grob 30 Tage der gezählten Fenster).
RUECKBLICK_TAGE = RUECKBLICK_S // 86400
#: Fenster, die bis zu so viele Tage nach dem gefragten Bereich enden, werden mitgelesen (Nullzeilen am Bereichsende).
#: N-799 F3 (Sitzung 2): so lang wie das längste Fenster, das die Lesestelle unverkürzt findet — Rückblick plus ein
#: Monat (ein Fenster wird im Block seines Nachtragsmonats mit ``RUECKBLICK_TAGE`` davor gerechnet). Damit nennt ein
#: Einzeltag dieselben Nullzeilen wie jeder Bereich, der ihn enthält; bis Sitzung 1 standen hier 7 Tage, und ein
#: Stillstand von mehr als 7 Tagen über eine Monatsgrenze fehlte am Einzeltag. Lesen kostet es nur einmal je Monat
#: (gemerkt), und Monate nach heute sind leer.
NACHLAUF_TAGE = RUECKBLICK_TAGE + 31
#: Die Nebenachsen, die die Marke erben können (E-2).
NEBENACHSEN = ("waermepumpe", "wallbox", "sonstige", "v2h")
#: Einträge des Speichers (Monate über alle Anlagen).
OBERGRENZE = 2000
_STUNDE = 3600


def _monat(tag: date) -> tuple[int, int]:
    return tag.year, tag.month


def _erster(m: tuple[int, int]) -> date:
    return date(m[0], m[1], 1)


def _naechster(m: tuple[int, int]) -> tuple[int, int]:
    return (m[0] + 1, 1) if m[1] == 12 else (m[0], m[1] + 1)


def _letzter(m: tuple[int, int]) -> date:
    return _erster(_naechster(m)) - timedelta(days=1)


def _monate(von: date, bis: date) -> list[tuple[int, int]]:
    out, m = [], _monat(von)
    while m <= _monat(bis):
        out.append(m)
        m = _naechster(m)
    return out


class _MonatsSpeicher:
    """Je (Datenbank, Anlage, Monat) die Fensterliste — Schnittstelle der ``merken``-Speicher (``entferne``, ``leeren``)."""

    def __init__(self) -> None:
        self._d: OrderedDict[tuple, tuple[int, frozenset, float, list]] = OrderedDict()
        self.treffer = 0
        self.fehl = 0

    def __len__(self) -> int:
        return len(self._d)

    def nimm(self, schluessel: tuple, mqtt: frozenset) -> Optional[list]:
        e = self._d.get(schluessel)
        if e is None:
            return None
        gen, m, zeit, wert = e
        if gen != merken.generation(schluessel[1]) or m != mqtt or merken.uhr_s() - zeit >= merken.VERFALL_S:
            del self._d[schluessel]
            return None
        self._d.move_to_end(schluessel)
        return wert

    def lege(self, schluessel: tuple, mqtt: frozenset, wert: list) -> None:
        self._d[schluessel] = (merken.generation(schluessel[1]), mqtt, merken.uhr_s(), wert)
        self._d.move_to_end(schluessel)
        while len(self._d) > OBERGRENZE:
            self._d.popitem(last=False)

    def entferne(self, anlage_id: Any, von: Optional[date], bis: Optional[date]) -> None:
        """Die Monate der Anlage, deren Fenster von Zeilen in ``[von, bis]`` abhängen können — Monat M hängt an
        ``[M − RUECKBLICK_TAGE, Monatsende]`` (nur rückwärts)."""
        rand = timedelta(days=RUECKBLICK_TAGE)
        weg = [k for k in self._d if k[1] == anlage_id
               and (von is None or _letzter(k[2]) >= von) and (bis is None or _erster(k[2]) - rand <= bis)]
        for k in weg:
            del self._d[k]

    def leeren(self) -> None:
        self._d.clear()
        self.treffer = self.fehl = 0


FENSTER = _MonatsSpeicher()
merken.melde_speicher(FENSTER)


def leeren() -> None:
    """Den Speicher leeren (Proben, Werkzeuge)."""
    FENSTER.leeren()


def _ts(tag: date) -> int:
    return tagesfenster(tag)[0]


async def _bilanz_zaehler(db: AsyncSession, stamm, stichtag: date) -> dict[str, tuple[str, Any]]:
    """Zähler-Schlüssel → (Rolle, Kanal): jeder Bilanz-Zähler der Anlage mit Mengen-Kanal (alle Investitionen; erfasst
    ist er, wo er Zeilen hat). Leer, wenn kein Netzbezug-Kanal darunter ist (Vorbedingung E-1, ohne weiteres Lesen).
    ``stichtag`` geht nur in die Wallbox-Regel der Zählerauswahl, die die Bilanz-Zähler nicht berührt."""
    from backend.models.kanal import ART_SUM

    eintraege = await stamm.eintraege(db, lambda _i: True, stichtag)
    rollen = {e.schluessel: STILLSTAND_ROLLE_JE_KATEGORIE[e.kategorie] for e in eintraege
              if e.kategorie in STILLSTAND_ROLLE_JE_KATEGORIE}
    if "netzbezug" not in rollen.values():
        return {}
    kanaele = {key: k for key, k in (await kanaele_laden(db, stamm.anlage.id, rollen)).items() if k.art == ART_SUM}
    if not any(rollen[key] == "netzbezug" for key in kanaele):
        return {}
    return {key: (rollen[key], k) for key, k in kanaele.items()}


async def _reihen(db: AsyncSession, zaehler: dict[str, tuple[str, Any]], von_ts: int,
                  bis_ts: int) -> dict[str, ZaehlerReihe]:
    """Die Zähler als ``ZaehlerReihe`` über ``[von_ts, bis_ts)`` — EIN ``deltas_stapel``."""
    je = await deltas_stapel(db, [k for _r, k in zaehler.values()], von_ts, bis_ts)
    return {key: ZaehlerReihe(zaehler[key][0], tuple(werte)) for key, werte in je.items()}


def _speicher_aktiv(invs: Iterable[Any]):
    """``ts`` → hat die Anlage an diesem Tag einen aktiven Speicher? (Vorbedingung E-1) — Investitionen vom Typ
    ``speicher``. Benannte Grenze (F12): ein Gerät «Sonstiges» der Kategorie Speicher ist kein Bilanz-Speicher (seine
    Mengen laufen nicht über die Batterie-Achse) und zählt hier nicht."""
    speicher = [i for i in invs if getattr(i, "typ", None) == "speicher"]

    def aktiv(ts: int) -> bool:
        tag = datetime.fromtimestamp(ts).date()
        return any(i.ist_aktiv_an(tag) for i in speicher)

    return aktiv


async def _mit_nebenachsen(db: AsyncSession, stamm, fenster: list[StillstandFenster]) -> list[StillstandFenster]:
    """Je markierbarem Fenster die Nebenachsen dazu, deren Zähler (des Nachtragstags) im Fenster ebenfalls stand (E-2)."""
    from backend.services.kanal.bilanz_adapter import zaehler_eintraege

    out = []
    for f in fenster:
        if f.sperre is not None:
            out.append(f)
            continue
        tag = datetime.fromtimestamp(f.nachtrag_ts).date()
        aktiv = {str(i.id): i for i in stamm.invs if i.ist_aktiv_an(tag)}
        achse_je = {e.schluessel: a for e in await zaehler_eintraege(db, stamm.anlage, aktiv, tag)
                    if (a := achse_der_kategorie(e.kategorie)) in NEBENACHSEN}
        kanaele = await kanaele_laden(db, stamm.anlage.id, achse_je) if achse_je else {}
        reihen = await _reihen(db, {key: (achse_je[key], k) for key, k in kanaele.items()},
                               f.von_ts - _STUNDE, f.nachtrag_ts + _STUNDE) if kanaele else {}
        erben = {a for a in NEBENACHSEN if erbt_marke(f, [r for r in reihen.values() if r.rolle == a])}
        out.append(dataclasses.replace(f, achsen=f.achsen | erben) if erben else f)
    return out


async def _block(db: AsyncSession, stamm, zaehler: dict, monate: list[tuple[int, int]],
                 ) -> dict[tuple[int, int], list[StillstandFenster]]:
    """Die Fenster der aufeinanderfolgenden Monate ``monate`` — EIN Lesen über den Block und ``RUECKBLICK_TAGE`` davor
    (nach dem Block nichts: ein Fenster hängt nur an Zeilen bis zu seiner Nachtragsstunde)."""
    erster, letzter = _erster(monate[0]), _letzter(monate[-1])
    reihen = await _reihen(db, zaehler, _ts(erster - timedelta(days=RUECKBLICK_TAGE)), _ts(letzter + timedelta(days=1)))
    alle = stillstand_fenster(reihen, speicher_aktiv=_speicher_aktiv(stamm.invs))
    von_ts, bis_ts = _ts(erster), _ts(letzter + timedelta(days=1))
    im_block = await _mit_nebenachsen(db, stamm, [f for f in alle if von_ts <= f.nachtrag_ts < bis_ts])
    out: dict[tuple[int, int], list[StillstandFenster]] = {m: [] for m in monate}
    for f in im_block:
        out[_monat(datetime.fromtimestamp(f.nachtrag_ts).date())].append(f)
    return out


def _bloecke(monate: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    out: list[list[tuple[int, int]]] = []
    for m in monate:
        if out and _naechster(out[-1][-1]) == m:
            out[-1].append(m)
        else:
            out.append([m])
    return out


async def _fenster_der_monate(db: AsyncSession, anlage_id: int, monate: list[tuple[int, int]]) -> list[StillstandFenster]:
    from backend.services.kanal.bilanz_leser import bilanz_stamm

    stamm = await bilanz_stamm(db, anlage_id)
    zaehler = await _bilanz_zaehler(db, stamm, _letzter(monate[-1]))
    if not zaehler:
        return []
    marke, mqtt = merken.db_marke(db), await merken.mqtt_schluessel(db, anlage_id)
    gefunden: dict[tuple[int, int], list] = {}
    fehl = []
    for m in monate:
        wert = FENSTER.nimm((marke, anlage_id, m), mqtt)
        if wert is None:
            fehl.append(m)
        else:
            gefunden[m] = wert
    FENSTER.treffer += len(monate) - len(fehl)
    FENSTER.fehl += len(fehl)
    for block in _bloecke(fehl):
        stand0 = merken.stand()
        neu = await _block(db, stamm, zaehler, block)
        for m, wert in neu.items():
            gefunden[m] = wert
            if merken.stand() == stand0:
                FENSTER.lege((marke, anlage_id, m), mqtt, wert)
    logger.debug("Stillstand Anlage %s: %d Monate, %d gerechnet", anlage_id, len(monate), len(fehl))
    return [f for m in monate for f in gefunden[m]]


async def fenster_im_bereich(db: AsyncSession, anlage_id: int, von: date, bis: date, *,
                             mit_gesperrten: bool = False) -> list[StillstandFenster]:
    """Die Erfassungs-Stillstände der Anlage, die die Tage ``von`` … ``bis`` (inklusive) berühren — Nullzeilen oder
    Nachtragsstunde im Bereich. Ohne ``mit_gesperrten`` nur die markierbaren (``sperre is None``)."""
    if von > bis:
        return []
    from backend.services.kanal.lade_kontext import gemerkt

    monate = _monate(von, bis + timedelta(days=NACHLAUF_TAGE))
    alle = await gemerkt(db, ("stillstand_fenster", anlage_id, monate[0], monate[-1]),
                         lambda: _fenster_der_monate(db, anlage_id, monate))
    von_ts, bis_ts = _ts(von), _ts(bis + timedelta(days=1))
    return [f for f in alle if f.von_ts < bis_ts and f.nachtrag_ts >= von_ts
            and (mit_gesperrten or f.sperre is None)]


async def tage_mit_fenster_ueber_mitternacht(db: AsyncSession, anlage_id: int, von: date, bis: date) -> set[date]:
    """Die Tage ``von`` … ``bis``, an denen ein vor 00:00 begonnenes markierbares Fenster endet (Nachtragsstunde an D,
    Fensterbeginn vor D) — Kandidaten des Tagesvergleichs (``vergleichstage``, E-8)."""
    return set(await erster_tag_der_fenster_ueber_mitternacht(db, anlage_id, von, bis))


async def erster_tag_der_fenster_ueber_mitternacht(db: AsyncSession, anlage_id: int, von: date,
                                                   bis: date) -> dict[date, date]:
    """Je Nachtragstag D (``von`` … ``bis``) eines vor 00:00 begonnenen markierbaren Fensters der erste Tag, den das
    Fenster berührt (der früheste, wenn mehrere an D enden) — ``vergleichstage`` lässt alle Tage dazwischen aus
    (N-799 S2, Tagesvergleich: ein Drei-Tage-Lauf lässt nicht nur D und D − 1 aus)."""
    out: dict[date, date] = {}
    for f in await fenster_im_bereich(db, anlage_id, von, bis):
        tag = datetime.fromtimestamp(f.nachtrag_ts).date()
        if f.von_ts < _ts(tag) and von <= tag <= bis:
            erster = datetime.fromtimestamp(f.von_ts).date()
            out[tag] = min(erster, out.get(tag, erster))
    return out


__all__ = ["FENSTER", "NACHLAUF_TAGE", "NEBENACHSEN", "RUECKBLICK_TAGE", "fenster_im_bereich", "leeren",
           "erster_tag_der_fenster_ueber_mitternacht", "tage_mit_fenster_ueber_mitternacht"]
