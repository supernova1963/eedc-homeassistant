"""Kanal vor Reihe, feldweise — die Feld-Auskunft der Tagesleser (Sensorwechsel mit Grund, Bauplan B-5, S-7; Sitzung 2).

**Was sie beantwortet.** Für einen Zählerschlüssel (``inv:<id>:<feld>``, auch eine Innengerät-Kopie ``…-<n>``) und das
Fenster, in dem die Zählerstand-Reihe ihn an einem Tag lesen würde: das **Δ seines eigenen Kanals** über genau dieses
Fenster — aber nur, wenn der Kanal das Fenster **voll** deckt (``lesen.Zeitraum.voll``, die eine Abdeckungsregel der
Lese-Schicht) und ein Mengen-Kanal (Art ``sum``) ist. Sonst keine Antwort, und der Leser bleibt bei der Reihe.

**Warum.** Die Reihe (``sensor_snapshots``) trägt, was HA zur Lesezeit sagte, mit der damals zugeordneten Entität; der
HA-Spiegel (``kanal_statistik``) trägt HAs Summe je Quelle mit Versatz über jeden Quellwechsel (``kanal_quelle``). An einer
Naht oder in einem fremden Abschnitt der Reihe (Produktiv, Wallbox «Ladung PV», 1.7.–10.8.2026: 15 Tage) liegt der Spiegel
richtig. Die Gruppen-Regel der Quellenwahl (``geraete_leser.waehle_gruppe``: fehlt EINEM Feld der Kanal, liest die ganze
Gruppe die Reihe) bleibt für Bilanz und Summen; die Tagesansicht liest jedes Feld für sich aus seinem Kanal, wenn der
Kanal es trägt — gemischt je **(Gerät, Feld, Innengerät-Kopie)**, die Summe des Ausgabe-Schlüssels danach.

**Dasselbe Fenster wie die Reihe.** Der Aufrufer reicht das Fenster, in dem er die Reihe an diesem Tag liest
(``boundary_range.tagesfenster_fuer`` mit denselben Argumenten) — am Bestandstag rückwärts ``[Vortag 23:00, 23:00)``, am
Kanal-Tag der Kalendertag. Eine Nachtladung 23–24 Uhr wandert damit nicht zwischen den Tagen (Messblatt §10 M2).

**Die Marke folgt der Quelle des Werts** (Bauplan §9 Nr. 24). ``voll`` heißt nur: über keinen Rand reicht eine Spanne, die
größer ist als das Fenster — nicht, dass der Kanal das Fenster bis zum Ende trägt (Kanal mit einem Stand je Tag: Fenster
``[Vortag 23:00, 23:00)``, gedeckt bis 00:00). Der Leser bildet die Abdeckungs-Marke deshalb aus ``gedeckt_von``/
``gedeckt_bis`` des Zeitraums nach derselben Regel wie bei der Reihe (``aggregator._kanal_rand_menge``). Ein Leser **ohne**
Marke (Bereichs-Leser, ``kanal_feldwerte_je_fenster``) nimmt den Kanal nur bei echter Deckung des Fensters (Entscheid H-K4 (a)).

Leser: ``snapshot/aggregator.get_tagesdetail_kwh`` (*Cockpit → Tag*, Wärme-Verlauf Stunden, Wärme-Verteilung Tag) ·
``snapshot/bereichs_leser.lade_tageswerte_je_geraet(kanal_zuerst=True)`` (Speicher-Netzladung der Monats-Fakten,
``monats_fakten/netzladung_tage.py``) · die Wirkungs-Prüfung des Befunds ``zaehler_versatz``
(``daten_checker/datenquelle/versatz.py``, ``feld_aus_kanal_am_tag``). Wächter «Reihen-Leser»
(``tests/test_reihen_leser_waechter.py``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Iterable, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_SUM

if TYPE_CHECKING:
    from backend.services.kanal.lesen import Zeitraum


def _ts(zeit: datetime) -> int:
    """Wanduhr (Prozesszone) als Unix-Sekunden — wie ``fenster._mitternacht``."""
    return int(round(zeit.timestamp()))


async def _mengen_kanaele(db: AsyncSession, anlage_id: int, keys: Iterable[str]) -> list:
    from backend.services.kanal.lesen import kanaele_laden

    return [k for k in (await kanaele_laden(db, anlage_id, keys)).values() if k.art == ART_SUM]


async def kanal_feldzeitraeume(db: AsyncSession, anlage_id: int, keys: Iterable[str], von: datetime,
                               bis: datetime) -> dict[str, "Zeitraum"]:
    """Je Schlüssel der Kanal-``Zeitraum`` über ``[von, bis)`` (Wanduhr der Reihe) — nur Schlüssel mit Mengen-Kanal und
    voller Auflösung (``voll``); ein Schlüssel ohne Antwort fehlt (der Leser nimmt dann die Reihe). Der Zeitraum trägt
    neben dem Δ ``gedeckt_von``/``gedeckt_bis``: ``voll`` ist eine **Auflösungsregel** (die Spanne über jeden Rand ist
    nicht größer als das Fenster), keine Deckung — der Leser bildet die Abdeckungs-Marke daraus wie bei der Reihe
    (Bauplan §9 Nr. 24). Eine Anweisung für die Kanäle, eine für die Randstände (im Lade-Kontext gemerkt)."""
    from backend.services.kanal.bilanz_leser import uhr
    from backend.services.kanal.lesen import zeitraum_stapel

    kanaele = await _mengen_kanaele(db, anlage_id, keys)
    if not kanaele:
        return {}
    zr = await zeitraum_stapel(db, kanaele, _ts(von), _ts(bis), jetzt=uhr())
    return {key: z for key, z in zr.items() if z.voll and z.delta is not None}


async def kanal_feldwerte(db: AsyncSession, anlage_id: int, keys: Iterable[str], von: datetime,
                          bis: datetime) -> dict[str, float]:
    """``kanal_feldzeitraeume``, nur das Δ je Schlüssel."""
    return {key: z.delta for key, z in (await kanal_feldzeitraeume(db, anlage_id, keys, von, bis)).items()}


def _deckt(z) -> bool:
    """Der Kanal deckt das Fenster wirklich: voll aufgelöst UND vom Fensterbeginn bis zum Fensterende gedeckt."""
    return z.voll and z.delta is not None and z.gedeckt_von <= z.von and z.gedeckt_bis >= z.bis


async def kanal_feldwerte_je_fenster(
    db: AsyncSession, anlage_id: int, keys: Iterable[str], fenster_je_tag: Mapping[date, tuple[datetime, datetime]],
) -> dict[str, dict[date, float]]:
    """Für einen Bereich: je Schlüssel und Tag das Kanal-Δ über das Fenster des Tages — **nur bei echter Deckung**
    (``gedeckt_von ≤ von`` und ``gedeckt_bis ≥ bis``), nicht schon bei ``voll``. Grund (Bauplan §9, Entscheid H-K4 (a)): der
    Bereichs-Leser kann keine Abdeckungs-Marke tragen; ein «voller» Kanal mit einem Stand je Tag lieferte sonst die Menge des
    Vortags ohne Hinweis (``kanal.db``, 183 Tage). Ohne Deckung gilt die Reihe. EINE Anweisung für alle Randstände
    (``lesen.zeitraeume_stapel``)."""
    from backend.services.kanal.bilanz_leser import uhr
    from backend.services.kanal.lesen import zeitraeume_stapel

    kanaele = await _mengen_kanaele(db, anlage_id, keys)
    if not kanaele or not fenster_je_tag:
        return {}
    tage: Sequence[date] = list(fenster_je_tag)
    fenster = [(_ts(fenster_je_tag[t][0]), _ts(fenster_je_tag[t][1])) for t in tage]
    out: dict[str, dict[date, float]] = {}
    for key, liste in (await zeitraeume_stapel(db, kanaele, fenster, jetzt=uhr())).items():
        werte = {t: z.delta for t, z in zip(tage, liste) if _deckt(z)}
        if werte:
            out[key] = werte
    return out


async def feld_aus_kanal_am_tag(db: AsyncSession, anlage, typ: Optional[str], key: str, datum: date) -> bool:
    """Liest die Tagesansicht den Tageswert von ``key`` am Tag ``datum`` aus dem Kanal statt aus der Reihe? — dieselbe
    Auskunft wie ``get_tagesdetail_kwh`` (Fenster wie ``tages_eingaenge``: Kanal-Tag der Bilanz ⇒ Kalendertag, sonst
    ``tagesfenster_fuer`` mit dem Fenster der Tageszeile). Für die Wirkungs-Prüfung des Befunds ``zaehler_versatz``."""
    from backend.services.kanal.bilanz_leser import kanal_tage
    from backend.services.snapshot.boundary_range import tagesfenster_fuer, tageszeile_des_tages_ist_rueckwaerts

    kanal_tag = (await kanal_tage(db, anlage.id, datum, datum)).get(datum) is not None
    rng = tagesfenster_fuer(typ, datum, tageszeile_rueckwaerts=await tageszeile_des_tages_ist_rueckwaerts(
        db, anlage.id, datum), kanal_tag=kanal_tag)
    a, b = rng.boundary_offsets[0], rng.boundary_offsets[-1]
    return key in await kanal_feldwerte(db, anlage.id, [key], rng.boundary_at(a), rng.boundary_at(b))


__all__ = ["feld_aus_kanal_am_tag", "kanal_feldwerte", "kanal_feldwerte_je_fenster", "kanal_feldzeitraeume"]
