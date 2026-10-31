"""Leser des Felds «Netzbezug zum WP-/Wallbox-Tarif» aus seinem Kanal (N-770/N-771 E3, Bauplan §2c: F9 = A, F10).

**Stunden-N gibt es nur im Kanal des Felds** (Entscheid Gernot 31.10.2026, F9 = A): das Feld
``netzbezug_eigener_tarif_kwh`` steht in ``KUMULATIVE_ZAEHLER_FELDER`` der Wärmepumpe und der Wallbox, bekommt auf HA den
Spiegel mit der ganzen Historie der Entity (``nachfuellen.py``) und auf MQTT die eigene Summe; der Kanal heißt
``inv:<id>:netzbezug_eigener_tarif_kwh`` (``sum``, kWh). Die Stundentabelle ``TagesEnergieProfil`` trägt das Feld nicht,
und dieser Leser schreibt nichts.

Drei Fragen, eine Stelle:

* ``netzanteil_des_monats`` — die Stunden eines Kalendermonats je Verwendung (``waermepumpe`` · ``wallbox``), Σ über die
  Geräte. **Nur**, wenn JEDES im Monat aktive Gerät der Verwendung, das einen Kanal des Felds hat, den Kalendermonat voll
  deckt (``lesen.zeitraum_stapel``, Abdeckungsregel (a)/(b)/(c); die Stunden aus ``lesen.stunden_stapel``). Ein Gerät ohne Kanal zählt nicht mit: seine Menge liegt, wenn
  überhaupt, nur als Monatswert vor (Hand, CSV) — benannte Grenze F9 «Monatswert teilt den Tag nicht». Ob der Monat den
  Netzbezug zum Komponenten-Tarif überhaupt ansetzt (eigener Tarif, F3, Klemme F7), entscheiden die Monats-Fakten
  (``monats_fakten.komponenten_anteile``); dieser Leser liefert nur die Stunden.
* ``beginn_je_geraet`` — die erste Zeile je Kanal des Felds. Der Kalendermonat, in dem sie liegt, ist der
  **Zuordnungsmonat** (F10): der Kanal hat dort keinen Stand vor dem Monatsbeginn (``lesen.py`` Regel (a),
  ``beginnt_nach_von``), sein Monatswert ist eine Teilmenge ⇒ der Monat gilt als nicht gemessen
  (``monats_fakten/laden.py``). Weil das Nachfüllen die HA-Historie holt, beginnt der Kanal nur dort, wo die Entity
  selbst beginnt.
* ``zellen_der_stunden`` — dieselben Stunden je (Wochentag, Uhrstunde) des Beginns: die Gewichte, mit denen ein
  Zeitfenster-Tarif (HT/NT) über N bzw. über (Netzbezug − N) gewichtet wird (F6, ``strompreis_aggregator``).
* ``zuordnungsmonate_der_wallboxen`` / ``mit_zuordnungsauskunft`` (N-771 Rest 1, E6) — der Zuordnungsmonat je Wallbox
  und die Auskunft an ihrer Zeile (``reader.ZeileImZuordnungsmonat``): im Zuordnungsmonat ist das Feld auch an der
  E-Mob-Zeile nicht die Netzladung (F11 greift nicht, die bisherige Regel gilt) — dieselbe F10-Regel wie die
  Stromrechnung, je Gerät. Gebunden an die Zeile wird die Auskunft dort, wo die Wallbox-Zeilen geladen werden
  (``monats_fakten/laden.py``, ``emob_kontext.py``, *Cockpit → Monat* laufender Monat).

Schwesterdateien: ``lesen.py`` (Lese-Schicht), ``fenster.py`` (Monatsfenster), ``preis_leser.py`` (Netzbezug-Zellen).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_SUM, KanalStatistik

MonatsSchluessel = tuple[int, int]

#: Das Registry-Feld (ein Name an WP und Wallbox, ``imd_monatsaggregat.NETZBEZUG_EIGENER_TARIF_FELD``).
FELD = "netzbezug_eigener_tarif_kwh"
#: Verwendung des Komponenten-Tarifs → Investitionstyp.
TYP_JE_VERWENDUNG: dict[str, str] = {"waermepumpe": "waermepumpe", "wallbox": "wallbox"}


def kanal_key(inv_id: int) -> str:
    """Der Kanal des Felds einer Investition."""
    return f"inv:{inv_id}:{FELD}"


@dataclass(frozen=True)
class NetzanteilStunden:
    """Der gemessene Netzbezug zum Komponenten-Tarif einer Verwendung in einem Kalendermonat, je Stunde."""

    verwendung: str
    #: ``start_ts → kWh`` der Stunde ``[start_ts, start_ts + 1 h)`` — Σ der ``change`` der Geräte (HAs Lesart).
    werte: dict[int, float]

    @property
    def summe_kwh(self) -> float:
        return sum(self.werte.values())


async def _geraete_mit_kanal(db: AsyncSession, anlage_id: int):
    """``[(investition, kanal)]`` der Wärmepumpen und Wallboxen mit Kanal des Felds — je Anfrage einmal."""
    from backend.services.kanal.lade_kontext import gemerkt

    async def _laden():
        from backend.models.investition import Investition
        from backend.services.kanal.lesen import kanaele_laden

        invs = list((await db.execute(select(Investition).where(and_(
            Investition.anlage_id == anlage_id, Investition.typ.in_(tuple(TYP_JE_VERWENDUNG.values())),
        )))).scalars().all())
        if not invs:
            return []
        kanaele = await kanaele_laden(db, anlage_id, [kanal_key(i.id) for i in invs])
        return [(i, kanaele[kanal_key(i.id)]) for i in invs
                if kanal_key(i.id) in kanaele and kanaele[kanal_key(i.id)].art == ART_SUM]

    return list(await gemerkt(db, ("netzanteil_geraete", anlage_id), _laden))


async def hat_netzanteil_kanaele(db: AsyncSession, anlage_id: int) -> bool:
    """Hat die Anlage überhaupt einen Kanal des Felds? (Vorfilter, im Lade-Kontext einmal je Anfrage)"""
    return bool(await _geraete_mit_kanal(db, anlage_id))


async def netzanteil_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, *, jetzt: Optional[int] = None,
) -> dict[str, NetzanteilStunden]:
    """Je Verwendung die Stunden des Kalendermonats — nur Verwendungen, deren Geräte mit Kanal ihn ALLE voll decken.

    ``{}`` ohne Kanal des Felds (ohne weitere Abfrage nach dem Vorfilter). Im Lade-Kontext einmal je Monat und Uhr."""
    from backend.services.kanal.lade_kontext import gemerkt
    from backend.services.kanal.lesen import _jetzt

    jetzt = _jetzt(jetzt)
    geraete = await _geraete_mit_kanal(db, anlage_id)
    if not geraete:
        return {}

    async def _rechnen() -> dict[str, NetzanteilStunden]:
        from backend.services.kanal.fenster import monatsfenster
        from backend.services.kanal.lesen import soll_ende, stunden_stapel, zeitraum_stapel

        von, bis = monatsfenster(jahr, monat)
        if von >= soll_ende(jetzt):
            return {}
        aktiv = [(i, k) for i, k in geraete if i.ist_aktiv_im_monat(jahr, monat)]
        if not aktiv:
            return {}
        # Die Abdeckung nach der EINEN Regel der Lese-Schicht (`zeitraum`: (a) Stand vor dem Monat, (b) Ende erreicht,
        # (c) keine Randspanne länger als der Monat) — dieselbe, mit der die WP-Gruppe ihre Quelle wählt; die Stunden
        # selbst aus `stunden_stapel`. Nur `stunden` allein ließe eine Lücke über den Monatsbeginn (Regel (c)) durch.
        deckung = await zeitraum_stapel(db, [k for _i, k in aktiv], von, bis, jetzt=jetzt)
        gedeckt = [(i, k) for i, k in aktiv if deckung[k.key].voll]
        st = await stunden_stapel(db, [k for _i, k in gedeckt], von, bis, jetzt=jetzt) if gedeckt else {}
        out: dict[str, NetzanteilStunden] = {}
        for verwendung, typ in TYP_JE_VERWENDUNG.items():
            je_typ = [(i, k) for i, k in aktiv if i.typ == typ]
            if not je_typ or not all(deckung[k.key].voll for _i, k in je_typ):
                continue
            werte: dict[int, float] = {}
            for _i, k in je_typ:
                for w in st[k.key].werte:
                    if w.change is not None:
                        werte[w.start_ts] = werte.get(w.start_ts, 0.0) + w.change
            out[verwendung] = NetzanteilStunden(verwendung, werte)
        return out

    return dict(await gemerkt(db, ("netzanteil_monat", anlage_id, jahr, monat, jetzt), _rechnen))


async def beginn_je_geraet(db: AsyncSession, anlage_id: int, inv_ids: Iterable[int]) -> dict[int, int]:
    """F10: ``investition_id → start_ts`` der ersten Zeile seines Kanals des Felds (EINE Anweisung). Ohne Kanal fehlt
    die Investition."""
    ids = set(inv_ids)
    kanal_je_inv = {i.id: k for i, k in await _geraete_mit_kanal(db, anlage_id) if i.id in ids}
    if not kanal_je_inv:
        return {}
    inv_je_kanal = {k.id: inv_id for inv_id, k in kanal_je_inv.items()}
    zeilen = (await db.execute(
        select(KanalStatistik.kanal_id, func.min(KanalStatistik.start_ts))
        .where(and_(KanalStatistik.kanal_id.in_(list(inv_je_kanal)), KanalStatistik.sum.is_not(None)))
        .group_by(KanalStatistik.kanal_id)
    )).all()
    return {inv_je_kanal[kid]: int(ts) for kid, ts in zeilen if ts is not None}


async def zuordnungsmonate_der_wallboxen(
    db: AsyncSession, anlage_id: int, wallbox_zeilen: Iterable[tuple[int, Optional[Mapping]]],
) -> dict[int, MonatsSchluessel]:
    """N-771 Rest 1 (E6): ``wallbox_id → Zuordnungsmonat`` des Felds (der Kalendermonat, in dem sein Kanal beginnt, F10)
    — **eine Abfrage nur, wenn eine Zeile das Feld trägt** (sonst ``{}`` ohne SQL; ohne Feld bitgleich). Im Lade-Kontext
    über ``gemerkt`` je Anfrage einmal. ``wallbox_zeilen``: ``(investition_id, verbrauch_daten)`` der Wallbox-Zeilen,
    die der Aufrufer geladen hat."""
    from backend.services.kanal.lade_kontext import gemerkt

    ids = sorted({int(i) for i, d in wallbox_zeilen if d and d.get(FELD) is not None})
    if not ids:
        return {}

    async def _laden() -> dict[int, MonatsSchluessel]:
        return {i: monat_der_stunde(ts) for i, ts in (await beginn_je_geraet(db, anlage_id, ids)).items()}

    return dict(await gemerkt(db, ("netzanteil_zuordnungsmonate", anlage_id, tuple(ids)), _laden))


def mit_zuordnungsauskunft(
    daten: Mapping, inv_id: int, schluessel: MonatsSchluessel, zuordnung: Mapping[int, MonatsSchluessel],
):
    """N-771 Rest 1: die Zeile mit der Auskunft «Zuordnungsmonat» (``reader.ZeileImZuordnungsmonat``, eine Kopie), wenn
    ``schluessel`` der Zuordnungsmonat dieser Wallbox ist und die Zeile das Feld trägt — sonst die Zeile selbst. Die EINE
    Stelle, die die Auskunft an eine Zeile bindet; ``reader.netzladung_des_zaehlers`` liest sie (F10-Regel je Gerät)."""
    from backend.core.field_definitions.reader import ZeileImZuordnungsmonat

    if daten and daten.get(FELD) is not None and zuordnung.get(int(inv_id)) == tuple(schluessel):
        return ZeileImZuordnungsmonat(daten)
    return daten


def monat_der_stunde(start_ts: int) -> MonatsSchluessel:
    """Der Kalendermonat, in dem die Stunde ``start_ts`` beginnt (Prozesszone, wie ``fenster.kalendertag_der_stunde``)."""
    d = datetime.fromtimestamp(start_ts)
    return d.year, d.month


def zellen_der_stunden(werte: Mapping[int, float]) -> list[tuple[int, int, float]]:
    """Die Stunden je (Wochentag, Uhrstunde ihres Beginns) zusammengefasst — die Form der Netzbezug-Zellen
    (``preis_leser.netzbezug_zellen_des_monats``; ``wochentag`` wie ``datetime.weekday()``). Nicht geklemmt: ein Zähler
    des Felds ist monoton, und die Netto-Gewichtung (Netzbezug − N) braucht die ungeklemmte Menge."""
    zellen: dict[tuple[int, int], float] = {}
    for ts, kwh in werte.items():
        d = datetime.fromtimestamp(ts)
        zellen[(d.weekday(), d.hour)] = zellen.get((d.weekday(), d.hour), 0.0) + kwh
    return [(w, h, kwh) for (w, h), kwh in sorted(zellen.items())]


__all__ = [
    "FELD", "NetzanteilStunden", "TYP_JE_VERWENDUNG", "beginn_je_geraet", "hat_netzanteil_kanaele", "kanal_key",
    "mit_zuordnungsauskunft", "monat_der_stunde", "netzanteil_des_monats", "zellen_der_stunden",
    "zuordnungsmonate_der_wallboxen",
]
