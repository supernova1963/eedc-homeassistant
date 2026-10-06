"""Konsistenzlauf Spiegel ↔ HA — HA-Bauform E2 (Auftrag Punkt 4, Bauplan §4, Gegenprüfung G6).

**Wozu.** Der Spiegel speichert HAs ``sum``/``state`` wörtlich — eine Korrektur in HA erreicht ihn sonst
nie. Zwei Fälle, beide aus HAs Quelltext:

* **„Summe anpassen"** (``recorder_statistics.py::adjust_statistics`` → ``_adjust_sum_statistics``):
  HA verschiebt ``sum`` ab einer Stunde für ALLE Folgezeilen um denselben Betrag.
* **Nachgereichte Stunden** (``compile_missing_statistics``, Importe): HA hat Zeilen, die eedc beim
  Stundenlauf noch nicht sah.

**Wie.** Je Spiegel-Kanal (Art ``sum`` und ``stand``) und Spiegel-Abschnitt (eine Quelle = eine Entity):

* Prüfstelle ``Q(t)``: die letzte gespeicherte Zeile ``≤ t`` ist dieselbe wie HAs letzte Zeile ``≤ t``
  (``start_ts``, ``sum``, ``state`` nach der Einheit des Stundenlaufs) **und** beide zählen gleich viele
  Zeilen von Abschnittsbeginn bis ``t``.
* Hält ``Q`` am letzten gespeicherten Zeitpunkt, ist der Abschnitt gleich (zwei HA-Abfragen).
* Sonst **Halbierung** über die Stunden des Abschnitts: die erste Stunde, an der ``Q`` bricht. Ab dort
  ``nachfuellen.neu_spiegeln`` — nur Spiegelzeilen, Bestand und Mitschrift bleiben stehen; spätere
  Quellen bekommen die Änderung des Abschnittsendes in ihren ``offset`` (jedes Δ nach der Naht wie in HA).

⚠ **Was die Halbierung voraussetzt:** dass die Prüfstelle ab der ersten Abweichung bricht. Sie vergleicht deshalb
neben letzter Zeile und Zeilenzahl die **Vorsumme** (``SUM(sum)``, ``SUM(state)`` ab Abschnittsbeginn): ein Versatz
trifft alle Folgezeilen, eine fehlende Stunde verschiebt jede spätere Zählung, und zwei sich aufhebende
Anpassungen (−x ab t1, +x ab t2) verschieben die Vorsumme ab t1 dauerhaft. **Toleranz relativ 1e-9:** die
Summation in SQL und in Python unterscheidet sich nur im Rundungsrauschen (n·ε ≈ 1e-11 bei 10⁵ Zeilen); eine
Anpassung, deren Wirkung auf die Vorsumme (Betrag × betroffene Stunden) unter 1e-9 der Vorsumme bleibt, findet
sie nicht — bei zehn Jahren eines 25-MWh-Zählers etwa 2 kWh·h. Zwei Abweichungen, die sich in Zahl UND Summen
aufheben, bleiben ungesehen.

⚠ **Schutz:** Liefert HA für einen Abschnitt gar keine Zeile mehr (Entity gelöscht, Statistik bereinigt),
wird nichts nachgezogen — der Lauf übernimmt Korrekturen, er wirft keine Historie weg. Fehlt HA nur der
**Anfang** (``ha_historie_gekuerzt``), wird erst ab HAs erster Zeile verglichen; die älteren Spiegelzeilen
bleiben stehen (Neu-Laden löscht nie unter HAs erster gelieferter Zeile). **HA unterwegs unerreichbar** ⇒ der
Abschnitt bricht als Fehler ab, nichts wird geändert.

Ersetzt nichts am Bestand: der heutige Tages-Nachlauf (``aggregate_yesterday_all``) läuft unverändert.

Schwesterdateien: ``nachfuellen.py``, ``schreiber.py``, ``lesen.py``.
"""

from __future__ import annotations

import asyncio
import bisect
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import and_, select

from backend.models.kanal import ART_STAND, ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal.nachfuellen import Sitzungen, abschnitte, neu_spiegeln

logger = logging.getLogger(__name__)

_STUNDE = 3600


def _gleich(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)), abs(float(b)))


@dataclass
class KonsistenzErgebnis:
    anlage_id: int
    kanaele: int = 0
    abschnitte: int = 0
    gleich: int = 0
    korrigiert: list[dict] = field(default_factory=list)   # {key, ab_ts, zeilen}
    #: HA hält den Anfang eines Abschnitts nicht mehr: {key, ha_erste_ts, behalten} (eigene Klasse, Punkt 2b).
    gekuerzt: list[dict] = field(default_factory=list)
    uebersprungen: dict = field(default_factory=dict)
    fehler: int = 0

    def zaehle(self, grund: str) -> None:
        self.uebersprungen[grund] = self.uebersprungen.get(grund, 0) + 1


class HaNichtErreichbar(RuntimeError):
    """HA antwortet mitten im Lauf nicht mehr (WebSocket-Transport: ``is_available`` falsch, die Leser liefern
    dann ``None``/``{}`` statt zu werfen). Der Lauf ändert dann nichts — der nächste prüft erneut."""


def _pruefe_erreichbar(ha_svc) -> None:
    if not ha_svc.is_available:
        raise HaNichtErreichbar("HA-Langzeitstatistik nicht erreichbar")


async def _pruefe_abschnitt(
    kanal: Kanal, eid: str, zeilen: list[tuple[int, Optional[float], Optional[float]]], ha_svc, faktor: float,
) -> Optional[int]:
    """Erste abweichende Stunde des Abschnitts (``start_ts``) oder ``None`` (gleich). Zwei HA-Abfragen je Prüfstelle.

    Prüfstelle ``Q(t)`` über ``(lo − 1, t]``: Zeilenzahl, **Vorsumme** ``SUM(sum)`` und ``SUM(state)`` (mal
    Einheitenfaktor) und die letzte Zeile ``≤ t``. Die Vorsumme fängt zwei sich aufhebende Anpassungen (−x ab t1,
    +x ab t2): Endwert und Zahl stimmen dann wieder, die Vorsumme ist ab t1 dauerhaft verschoben — die Halbierung
    findet t1, das Neu-Laden ab dort übernimmt auch t2 (Nachmessung E2, Punkt 2a).
    """
    ts_liste = [z[0] for z in zeilen]
    lo, hi = ts_liste[0], ts_liste[-1]
    vor_sum, vor_state, n_sum, n_state = [0.0], [0.0], [0], [0]
    for _ts, su, st in zeilen:
        vor_sum.append(vor_sum[-1] + (float(su) if su is not None else 0.0))
        vor_state.append(vor_state[-1] + (float(st) if st is not None else 0.0))
        n_sum.append(n_sum[-1] + (su is not None))
        n_state.append(n_state[-1] + (st is not None))

    def _mal(v):
        return None if v is None else float(v) * faktor

    async def q(t: int) -> bool:
        kz = await asyncio.to_thread(ha_svc.get_stundenzeilen_kennzahlen, eid, lo - 1, t)
        if kz is None:
            _pruefe_erreichbar(ha_svc)
            raise HaNichtErreichbar(f"HA kennt {eid} nicht mehr")
        i = bisect.bisect_right(ts_liste, t)
        if kz["anzahl"] != i:
            return False
        if i == 0:
            return True
        if not (_gleich(_mal(kz["summe_sum"]), vor_sum[i] if n_sum[i] else None)
                and _gleich(_mal(kz["summe_state"]), vor_state[i] if n_state[i] else None)):
            return False
        ha = await asyncio.to_thread(ha_svc.get_stundenzeile_bis, eid, t)
        if ha is None:
            _pruefe_erreichbar(ha_svc)
        st = zeilen[i - 1]
        return (ha is not None and int(round(ha["start_ts"])) == st[0]
                and _gleich(_mal(ha["sum"]), st[1]) and _gleich(_mal(ha["state"]), st[2]))

    if await q(hi):
        return None
    links, rechts = lo - _STUNDE, hi          # q(links) gilt (nichts gezählt), q(rechts) bricht
    while rechts - links > _STUNDE:
        mitte = links + ((rechts - links) // (2 * _STUNDE)) * _STUNDE
        if await q(mitte):
            links = mitte
        else:
            rechts = mitte
    return rechts


async def konsistenz_anlage(sitzungen: Sitzungen, anlage_id: int, *, ha_svc=None) -> KonsistenzErgebnis:
    """Alle Spiegel-Kanäle einer Anlage gegen HA prüfen und ab der ersten Abweichung neu spiegeln.

    Vier HA-Abfragen je gleichem Abschnitt (Einheit, Kennzahlen des Abschnitts, Prüfstelle am Ende = Kennzahlen
    + letzte Zeile). Wird HA unterwegs unerreichbar, bricht der Abschnitt als Fehler ab, ohne etwas zu ändern.
    """
    from backend.services.ha_statistics_service import get_ha_statistics_service
    from backend.services.kanal.schreiber import _mengen_faktor

    ha_svc = ha_svc or get_ha_statistics_service()
    erg = KonsistenzErgebnis(anlage_id)
    if not ha_svc.is_available:
        erg.zaehle("ha_nicht_erreichbar")
        return erg
    async with sitzungen() as db:
        kanaele = list((await db.execute(select(Kanal).where(and_(
            Kanal.anlage_id == anlage_id, Kanal.art.in_([ART_SUM, ART_STAND]),
        )))).scalars().all())
        quellen = {k.id: list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all())
                   for k in kanaele}
    for kanal in kanaele:
        teile = abschnitte(quellen[kanal.id])
        if not teile:
            continue
        erg.kanaele += 1
        for ab in teile:
            try:
                async with sitzungen() as db:
                    bed = [KanalStatistik.kanal_id == kanal.id, KanalStatistik.familie == FAMILIE_SPIEGEL,
                           KanalStatistik.start_ts >= ab.von]
                    if ab.bis is not None:
                        bed.append(KanalStatistik.start_ts < ab.bis)
                    zeilen = [(int(r[0]), r[1], r[2]) for r in (await db.execute(
                        select(KanalStatistik.start_ts, KanalStatistik.sum, KanalStatistik.state)
                        .where(and_(*bed)).order_by(KanalStatistik.start_ts)
                    )).all()]
                if not zeilen:
                    continue
                erg.abschnitte += 1
                meta_lauf = await asyncio.to_thread(
                    ha_svc.get_stundenzeilen_mehrere, {ab.eid: zeilen[-1][0] - 1}, zeilen[-1][0])
                if ab.eid not in meta_lauf:
                    _pruefe_erreichbar(ha_svc)
                    erg.zaehle("ha_kennt_sensor_nicht")
                    continue
                faktor = 1.0 if kanal.art == ART_STAND else _mengen_faktor(meta_lauf[ab.eid][0])
                if faktor is None:
                    erg.zaehle("ohne_summe")
                    continue
                kz = await asyncio.to_thread(ha_svc.get_stundenzeilen_kennzahlen, ab.eid,
                                             zeilen[0][0] - 1, zeilen[-1][0])
                if kz is None:
                    _pruefe_erreichbar(ha_svc)
                    erg.zaehle("ha_kennt_sensor_nicht")
                    continue
                if not kz["anzahl"]:
                    erg.zaehle("ha_ohne_zeilen")       # Schutz: keine Historie wegwerfen
                    continue
                if kz["erste_ts"] is not None and int(round(kz["erste_ts"])) > zeilen[0][0]:
                    # HA hält den Anfang nicht mehr (z. B. „alte Statistik löschen" nach einem Einheitenwechsel):
                    # verglichen wird erst ab HAs erster Zeile, darunter bleibt der Spiegel stehen.
                    ha_erste = int(round(kz["erste_ts"]))
                    erg.zaehle("ha_historie_gekuerzt")
                    erg.gekuerzt.append({"key": kanal.key, "ha_erste_ts": ha_erste,
                                         "behalten": sum(1 for z in zeilen if z[0] < ha_erste)})
                    zeilen = [z for z in zeilen if z[0] >= ha_erste]
                t0 = await _pruefe_abschnitt(kanal, ab.eid, zeilen, ha_svc, faktor)
                if t0 is None:
                    erg.gleich += 1
                    continue
                n = await neu_spiegeln(sitzungen, kanal.id, t0, ha_svc=ha_svc)
                erg.korrigiert.append({"key": kanal.key, "ab_ts": t0, "zeilen": n})
            except Exception as e:  # noqa: BLE001 — ein Kanal hält die übrigen nicht auf
                erg.fehler += 1
                logger.warning("Kanal-Konsistenzlauf %s (Anlage %s): %s: %s",
                               kanal.key, anlage_id, type(e).__name__, e)
    if erg.korrigiert:
        # HA-Bauform E4c: der abgeleitete Kanal rechnet aus dem Spiegel — ab der ersten korrigierten Stunde neu
        # (nie vor seinem `aufbaubar_ab`); der nächste Stundenlauf schreibt ihn aus dem neuen Spiegel fort.
        from backend.services.kanal.abgeleitet import verwerfe_ab

        async with sitzungen() as db:
            await verwerfe_ab(db, anlage_id, min(int(k["ab_ts"]) for k in erg.korrigiert))
    return erg


async def konsistenz_alle(sitzungen: Sitzungen, *, ha_svc=None) -> list[KonsistenzErgebnis]:
    """Der Tages-Nachlauf (eigener Job, ``scheduler.kanal_konsistenz_job``): alle Anlagen.

    Eine Korrektur oder ein Fehler geht ins Aktivitätsprotokoll, in der Sitzung, die es schreibt (N-532).
    """
    from backend.models.anlage import Anlage
    from backend.services.activity_service import log_activity

    async with sitzungen() as db:
        ids = list((await db.execute(select(Anlage.id).order_by(Anlage.id))).scalars().all())
    out = []
    for aid in ids:
        erg = await konsistenz_anlage(sitzungen, aid, ha_svc=ha_svc)
        out.append(erg)
        if erg.korrigiert or erg.fehler or erg.gekuerzt:
            async with sitzungen() as db:
                await log_activity(
                    kategorie="scheduler",
                    aktion=("Kanalstatistik: Konsistenzlauf unvollständig" if erg.fehler
                            else "Kanalstatistik: Spiegel an HA angeglichen" if erg.korrigiert
                            else "Kanalstatistik: HA hält nicht mehr die ganze Spiegel-Historie"),
                    erfolg=erg.fehler == 0,
                    details=(f"{len(erg.korrigiert)} Abschnitt(e) ab der ersten Abweichung neu gespiegelt"
                             + (f", {len(erg.gekuerzt)} Abschnitt(e) ohne HAs Anfang (älterer Spiegel bleibt)"
                                if erg.gekuerzt else "")
                             + (f", {erg.fehler} Fehler" if erg.fehler else "")),
                    details_json={"korrigiert": erg.korrigiert, "gekuerzt": erg.gekuerzt,
                                  "uebersprungen": erg.uebersprungen},
                    anlage_id=aid, db=db,
                )
    return out
