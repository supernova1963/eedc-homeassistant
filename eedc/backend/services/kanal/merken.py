"""Merken der Kanal-Stundentage je Prozess (HA-Bauform S5, Etappe E-S5-1c; Bauplan S5 §10d **S5-R7a–d**, Entscheid H-1 → A).

**Warum.** Die Ganz-Historie-Sichten (Speicher-Sizing, -Potenzial, -Dashboard, aktueller Monat, HA-Export) rechnen je Aufruf
jeden Kanal-Tag der Anlage neu — am Produkt-Maß (716 Kanal-Tage) 1,4–4,8 s je Aufruf. Ein abgeschlossener Tag ändert sich
nur, wenn etwas geschrieben wird, wovon er abhängt; also wird sein Preis je Prozess **einmal** gezahlt.

**Was gemerkt wird — drei Speicher, Stufe 1 (R7a, Entscheid H-1 → A; der dritte seit E-S5-4):**

* ``ADAPTER`` — je (Anlage, Tag, gefragte Gruppen) der Gruppensatz (Gruppen mit Wahl ``kanal``) und die Adapter-Zeilen
  ``KanalStunden`` (``stunden_adapter.stunden_aus_kanaelen``); gerufen aus ``energie_profil/kanal_stunden.py::
  stunden_der_kanal_tage``. Die Mischzeile entsteht je Aufruf neu aus der Stundenzeile — darum keine Invalidierung beim
  Schreiben der Stundenzeilen.
* ``TAGESWAHL`` — je (Anlage, Tag) der ``KanalTag`` der Bilanz bzw. «kein Kanal-Tag»; gerufen aus
  ``bilanz_leser.kanal_tage``.
* ``GERAETE`` (HA-Bauform S5, E-S5-4, Bauplan §10j 1, Nachmessung E3 M-1 → B) — je (Anlage, Tag, Geräte-Gruppe) die
  Tageswerte der Gruppe in ``komponenten_kwh``-Form (Ziel-Schlüssel, Vorzeichen der Beitragsschicht) bzw. «Gruppe ohne
  Wahl ``kanal``»: Wärmepumpe (Σ der Stunden, ``kanal_stunden.wp_komponenten_der_kanal_tage``), E-Mobilität und
  Sonstiges (Tages-Δ, ``stunden_leser.geraete_tageswerte``); gerufen aus ``kanal_stunden.geraete_tageswerte_gemerkt``.
  Seit S5b tragen die Tageszeilen diese Schlüssel an Kanal-Tagen nicht mehr — jeder Leser von ``komponenten_kwh``
  (Daten-Checker, *Energieprofil → Monat*, Tagesliste, Wärme-Verlauf, Modus-Split) fragt sie dort aus den Kanälen.

Der Bereichs-Leser ``stunden_leser.kanal_stundentage`` bleibt unverändert und merkt nicht (sein ``KanalStundentag`` hielte
132 kB je Tag statt 34 kB, gemessen E-S5-1c H-1); ohne Merken bleiben ``wp_werte_der_kanal_tage`` (Wärme-Achsen je
Gerät) und der Einzeltag ``/stunden``.

**Nur abgeschlossene Tage** (R7a): Tag D, wenn ``tagesfenster(D)[1] ≤ lesen.soll_ende(jetzt)`` — gleichbedeutend mit
``jetzt ≥ D+1 00:00 + SCHREIBVERZUG_S``, dieselbe Funktion wie die Lese-Schicht, keine zweite Uhrregel. Der laufende Tag
und der Vortag bis ``SCHREIBVERZUG_S`` nach Mitternacht werden nie gemerkt (und nie aus dem Speicher gelesen).

**Invalidierung (R7c) — Generation je Anlage, alle Speicher gemeinsam:** jeder Eintrag trägt die Generation seiner
Anlage; ein Unterschied ist ein Fehltreffer. Hochgezählt bzw. entfernt wird

(i) an den fünf Schreibstellen von ``kanal_statistik`` (Wächter ``SCHREIBER_KANAL_STATISTIK`` in
    ``test_kanal_lesen_waechter.py``): ``invalidiere(anlage, von=Tag)`` entfernt die Tage ab ``von`` (``bis``), ohne Tag die
    ganze Anlage. Ein Schreiben bei ``ts`` trifft ab dem Tag des vorigen Stands (``tag_des_vorstands``) — der Stand davor
    bestimmt Spanne, Abdeckung und Lückentag der Tage dazwischen;
(ii) zentral am Sitzungsereignis ``after_flush`` (an ``sqlalchemy.orm.Session``, also an der Session-Fabrik und an jeder
     anderen Sitzung des Prozesses): neue, geänderte, gelöschte ``Anlage``/``Investition``/``Kanal``/``KanalQuelle`` ⇒
     Generation ihrer Anlage (nicht bestimmbar ⇒ alle Anlagen);
(iii) die MQTT-Schlüsselmenge (``snapshot.reader.mqtt_zaehler_keys``) liegt im Eintrag und wird je Aufruf verglichen.

Weil ein Leser einer anderen Sitzung zwischen Schreiben und ``commit`` noch den alten Stand liest, wird jede
Invalidierung mit Sitzung beim ``commit`` dieser Sitzung **noch einmal** angewandt, und ein Ergebnis, während dessen
Berechnung invalidiert wurde, wird nicht abgelegt (``stand``).

**Grenzen (R7d):** LRU je Speicher über alle Anlagen, ``OBERGRENZE_TAGE`` (3 000) Einträge — eine Sicht über mehr Tage
verdrängt sich selbst und gewinnt nichts; ``GERAETE`` hält ``OBERGRENZE_GERAETE`` (9 000) Einträge über Anlagen **und** Gruppen (bis
zu drei je Tag ⇒ 3 000 Tage); Verfall ``VERFALL_S`` (24 h); Zähler
Treffer/Fehltage (eine DEBUG-Zeile je Aufruf). Kein Thread, kein asyncio-Task, nichts Persistentes (Konzept: keine
gefalteten Mengen speichern). Ein Prozess hat einen Speicher; bei mehreren Workern je Prozess einer — kohärent über
(i)–(iii) und den Verfall, solange alle Schreiber im selben Prozess laufen (``run.sh`` startet einen uvicorn ohne
``--workers``). Die Datenbank gehört zum Schlüssel (``_db_marke``: je Engine eine Marke), damit Prozesse mit mehreren
Datenbanken (Proben, Werkzeuge) nichts vermischen.
"""

from __future__ import annotations

import itertools
import logging
import time
from collections import OrderedDict
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Hashable, Iterable, Optional

logger = logging.getLogger(__name__)

#: R7d: Einträge je Speicher (Entscheid O-1 E-S5-1c: 3 000 statt 1 000 — gemessen ≈ 30,8 kB je Tag Adapter-Zeilen, ≈ 2 kB
#: Tageswahl ⇒ im Vollzustand ≤ 92 MB + ≤ 6 MB; deckt am Produkt ≈ 8 Jahre Kanal-Tage). Fragt eine Sicht mehr Tage ab, als ein
#: Speicher hält, verdrängt sie sich selbst (LRU) und gewinnt nichts — benannte Grenze.
OBERGRENZE_TAGE = 3000
#: R7d für ``GERAETE`` (HA-Bauform S5, E-S5-4 Nachzug 1, ⛔ H-2 → B): je Tag bis zu drei Einträge (Wärmepumpe, E-Mobilität,
#: Sonstiges) ⇒ 9 000 Einträge halten 3 000 Tage wie die beiden anderen Speicher; gemessen ≈ 630 B je Eintrag ⇒ im Vollzustand
#: ≈ 5,7 MB. Mit 3 000 Einträgen verdrängte sich der WP-Bereich einer langen Historie selbst (Kanal-Kopie, 4 301 Kanal-Tage).
OBERGRENZE_GERAETE = 9000
#: R7d: Verfall eines Eintrags in Sekunden.
VERFALL_S = 24 * 3600

_INFO_OFFEN = "eedc_kanal_merken_offen"
_INFO_MARKE = "_eedc_kanal_merken_marke"
#: Ein abgelegtes «kein Wert» (Tag ohne Kanal-Gruppe bzw. kein Kanal-Tag) — wird gemerkt, aber nicht ausgegeben.
_KEIN = object()
_ALLE = "alle"
_marken = itertools.count(1)


def uhr_s() -> float:
    """Die Uhr des Verfalls (monoton; eine Stelle, damit Proben sie stellen)."""
    return time.monotonic()


class _Zustand:
    """Generation je Anlage, eine für alle, und der Stand (steigt mit jeder Invalidierung)."""

    def __init__(self) -> None:
        self.gen: dict[int, int] = {}
        self.gen_alle = 0
        self.stand = 0


_Z = _Zustand()


def generation(anlage_id: int) -> int:
    return _Z.gen.get(anlage_id, 0) + _Z.gen_alle


def stand() -> int:
    """Steigt mit jeder Invalidierung — ein Ergebnis, während dessen Berechnung er stieg, wird nicht abgelegt."""
    return _Z.stand


class _Eintrag:
    __slots__ = ("wert", "gen", "mqtt", "zeit")

    def __init__(self, wert: Any, gen: int, mqtt: frozenset, zeit: float) -> None:
        self.wert, self.gen, self.mqtt, self.zeit = wert, gen, mqtt, zeit


class Speicher:
    """Ein LRU-Speicher je Tag: Schlüssel ``(Datenbank, Anlage, Tag, Rest)``."""

    def __init__(self, name: str, obergrenze: Optional[Callable[[], int]] = None) -> None:
        self.name = name
        #: Die Zahl der Einträge, ab der verdrängt wird — eine Funktion, damit Proben die Modul-Konstante stellen können.
        self._obergrenze = obergrenze or (lambda: OBERGRENZE_TAGE)
        self._d: OrderedDict[tuple, _Eintrag] = OrderedDict()
        self.treffer = 0
        self.fehltage = 0

    def __len__(self) -> int:
        return len(self._d)

    def nimm(self, schluessel: tuple, mqtt: frozenset) -> tuple[bool, Any]:
        e = self._d.get(schluessel)
        if e is None:
            return False, None
        if e.gen != generation(schluessel[1]) or e.mqtt != mqtt or uhr_s() - e.zeit >= VERFALL_S:
            del self._d[schluessel]
            return False, None
        self._d.move_to_end(schluessel)
        return True, e.wert

    def lege(self, schluessel: tuple, wert: Any, mqtt: frozenset) -> None:
        self._d[schluessel] = _Eintrag(wert, generation(schluessel[1]), mqtt, uhr_s())
        self._d.move_to_end(schluessel)
        while len(self._d) > self._obergrenze():
            self._d.popitem(last=False)

    def entferne(self, anlage_id: int, von: Optional[date], bis: Optional[date]) -> None:
        weg = [k for k in self._d if k[1] == anlage_id and (von is None or k[2] >= von) and (bis is None or k[2] <= bis)]
        for k in weg:
            del self._d[k]

    def leeren(self) -> None:
        self._d.clear()
        self.treffer = self.fehltage = 0


ADAPTER = Speicher("adapter_zeilen")
TAGESWAHL = Speicher("tageswahl")
#: HA-Bauform S5, E-S5-4 (§10j 1): die Tageswerte der Geräte-Gruppen je (Anlage, Tag, Gruppe) — dieselbe Generation,
#: Invalidierung und derselbe Verfall wie die beiden anderen Speicher; Obergrenze ``OBERGRENZE_GERAETE`` (drei Gruppen je Tag).
GERAETE = Speicher("geraete_tageswerte", obergrenze=lambda: OBERGRENZE_GERAETE)
SPEICHER = (ADAPTER, TAGESWAHL, GERAETE)


def leeren() -> None:
    """Alle Speicher leeren (Proben, Werkzeuge) — die Generationen bleiben."""
    for s in SPEICHER:
        s.leeren()


# ── Invalidierung ───────────────────────────────────────────────────────────


def _anwenden(anlage_id: Any, von: Optional[date], bis: Optional[date]) -> None:
    if anlage_id == _ALLE:
        _Z.gen_alle += 1
    elif von is None and bis is None:
        _Z.gen[anlage_id] = _Z.gen.get(anlage_id, 0) + 1
    else:
        for s in SPEICHER:
            s.entferne(anlage_id, von, bis)
    _Z.stand += 1


def invalidiere(anlage_id: Optional[int], von: Optional[date] = None, bis: Optional[date] = None, *, db=None) -> None:
    """R7c (i): die gemerkten Tage einer Anlage verwerfen (alle Speicher) — ``von``/``bis`` (je inklusive) der betroffene Tagesbereich,
    ohne beide die ganze Anlage (Generation); ``anlage_id`` ``None``: alle Anlagen. Mit ``db`` (der schreibenden Sitzung)
    wird dieselbe Invalidierung beim ``commit`` dieser Sitzung noch einmal angewandt (ein Leser einer anderen Sitzung
    kann bis dahin den alten Stand gemerkt haben)."""
    ziel = _ALLE if anlage_id is None else int(anlage_id)
    _anwenden(ziel, von, bis)
    if db is not None:
        sitzung = getattr(db, "sync_session", db)
        sitzung.info.setdefault(_INFO_OFFEN, []).append((ziel, von, bis))


async def tag_des_vorstands(db, kanal_ids: Iterable[int], ab_ts: int) -> dict[int, date]:
    """Je Anlage der Kanäle ``kanal_ids`` der früheste Tag, den ein Schreiben ab ``ab_ts`` trifft: der Tag des letzten
    Stands vor ``ab_ts`` (je Kanal), ohne Stand davor der Tag von ``ab_ts``."""
    from sqlalchemy import text

    ids = sorted({int(k) for k in kanal_ids})
    if not ids:
        return {}
    marken = ",".join(str(i) for i in ids)
    res = await db.execute(text(
        "SELECT k.anlage_id, MIN(COALESCE((SELECT MAX(s.start_ts) FROM kanal_statistik s WHERE s.kanal_id = k.id "
        f"AND s.start_ts < :t), :t)) FROM kanal k WHERE k.id IN ({marken}) GROUP BY k.anlage_id"), {"t": int(ab_ts)})
    return {int(a): datetime.fromtimestamp(int(ts)).date() for a, ts in res.all()}


async def anlage_der_kanaele(db, kanal_ids: Iterable[int]) -> set[int]:
    """Die Anlagen der Kanäle ``kanal_ids`` (für Schreibstellen, die nur die Kanäle kennen)."""
    from sqlalchemy import select

    from backend.models.kanal import Kanal

    ids = sorted({int(k) for k in kanal_ids})
    if not ids:
        return set()
    return {int(a) for (a,) in (await db.execute(select(Kanal.anlage_id).where(Kanal.id.in_(ids)).distinct())).all()}


# ── R7c (ii): Sitzungsereignisse ────────────────────────────────────────────


_KLASSEN: Optional[tuple] = None


def _klassen() -> tuple:
    global _KLASSEN
    if _KLASSEN is None:
        from backend.models.anlage import Anlage
        from backend.models.investition import Investition
        from backend.models.kanal import Kanal, KanalQuelle

        _KLASSEN = (Anlage, Investition, Kanal, KanalQuelle)
    return _KLASSEN


def _anlage_der_instanz(sitzung, obj) -> Any:
    """Die Anlage einer geflushten Instanz — ``_ALLE``, wenn sie nicht bestimmbar ist."""
    anlage, investition, kanal, quelle = _klassen()
    if isinstance(obj, anlage):
        return obj.id if obj.id is not None else _ALLE
    if isinstance(obj, (investition, kanal)):
        return obj.anlage_id if obj.anlage_id is not None else _ALLE
    if isinstance(obj, quelle) and obj.kanal_id is not None:
        from sqlalchemy.orm.util import identity_key

        # nur die Identitätskarte, keine Abfrage im Ereignis
        k = sitzung.identity_map.get(identity_key(kanal, obj.kanal_id))
        return k.anlage_id if k is not None and k.anlage_id is not None else _ALLE
    return _ALLE


def _betroffene(sitzung) -> set:
    klassen = _klassen()
    out: set = set()
    for obj in itertools.chain(sitzung.new, sitzung.deleted):
        if isinstance(obj, klassen):
            out.add(_anlage_der_instanz(sitzung, obj))
    for obj in sitzung.dirty:
        if isinstance(obj, klassen) and sitzung.is_modified(obj, include_collections=False):
            out.add(_anlage_der_instanz(sitzung, obj))
    return out


def _nach_flush(sitzung, _flush_context) -> None:
    for ziel in _betroffene(sitzung):
        _anwenden(ziel, None, None)
        sitzung.info.setdefault(_INFO_OFFEN, []).append((ziel, None, None))


def _nach_commit(sitzung) -> None:
    for ziel, von, bis in sitzung.info.pop(_INFO_OFFEN, ()):
        _anwenden(ziel, von, bis)


def _nach_rollback(sitzung) -> None:
    sitzung.info.pop(_INFO_OFFEN, None)


_ANGEMELDET = False


def anmelden() -> None:
    """R7c (ii) an ``sqlalchemy.orm.Session`` (jede Sitzung des Prozesses, auch die der Session-Fabrik
    ``core.database.async_session_maker``) — einmal je Prozess."""
    global _ANGEMELDET
    if _ANGEMELDET:
        return
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    event.listen(Session, "after_flush", _nach_flush)
    event.listen(Session, "after_commit", _nach_commit)
    event.listen(Session, "after_rollback", _nach_rollback)
    _ANGEMELDET = True


def abmelden() -> None:
    """Gegenstück zu ``anmelden`` (Proben)."""
    global _ANGEMELDET
    if not _ANGEMELDET:
        return
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    event.remove(Session, "after_flush", _nach_flush)
    event.remove(Session, "after_commit", _nach_commit)
    event.remove(Session, "after_rollback", _nach_rollback)
    _ANGEMELDET = False


# ── Lesen über den Speicher ─────────────────────────────────────────────────


def abgeschlossen(tag: date, jetzt: int) -> bool:
    """R7a: Tag ``tag`` ist abgeschlossen, wenn sein Fenster vor dem Soll-Ende der Lese-Schicht endet
    (``tagesfenster(tag)[1] ≤ soll_ende(jetzt)`` ⇔ ``jetzt ≥ tag+1 00:00 + SCHREIBVERZUG_S``)."""
    from backend.services.kanal.fenster import tagesfenster
    from backend.services.kanal.lesen import soll_ende

    return tagesfenster(tag)[1] <= soll_ende(jetzt)


def _db_marke(db) -> int:
    """Eine Marke je Datenbank-Engine (Proben öffnen viele Datenbanken in einem Prozess)."""
    sitzung = getattr(db, "sync_session", db)
    bind = sitzung.get_bind()
    engine = getattr(bind, "engine", bind)
    marke = engine.__dict__.get(_INFO_MARKE)
    if marke is None:
        marke = next(_marken)
        engine.__dict__[_INFO_MARKE] = marke
    return marke


async def mqtt_schluessel(db, anlage_id: int) -> frozenset:
    """R7c (iii): die MQTT-Schlüsselmenge der Anlage (``mqtt_zaehler_keys``, jede Historie) — im Lade-Kontext einmal je
    Anfrage."""
    from backend.services.kanal.lade_kontext import gemerkt
    from backend.services.snapshot.reader import mqtt_zaehler_keys

    async def _frage() -> frozenset:
        return frozenset(await mqtt_zaehler_keys(db, anlage_id))

    return await gemerkt(db, ("merken_mqtt_schluessel", anlage_id), _frage)


async def je_tag(db, speicher: Speicher, anlage_id: int, tage: Iterable[date], rest: Hashable, jetzt: int,
                 laden: Callable[[list[date]], Awaitable[dict[date, Any]]]) -> dict[date, Any]:
    """Je Tag aus ``tage`` der Wert — abgeschlossene Tage aus dem Speicher; die Fehltage über EINEN Aufruf
    ``laden(fehltage)`` (``{tag: wert}``, ein fehlender Tag = kein Wert), abgeschlossene davon merken. Ausgabe in der
    Ordnung von ``tage``, nur Tage mit Wert."""
    tage = list(tage)
    if not tage:
        return {}
    marke, mqtt, stand0 = _db_marke(db), await mqtt_schluessel(db, anlage_id), stand()
    gefunden: dict[date, Any] = {}
    fehl: list[date] = []
    for d in tage:
        ok, wert = speicher.nimm((marke, anlage_id, d, rest), mqtt) if abgeschlossen(d, jetzt) else (False, None)
        if ok:
            gefunden[d] = wert
        else:
            fehl.append(d)
    if fehl:
        neu = await laden(fehl)
        ablegen = stand() == stand0
        for d in fehl:
            gefunden[d] = neu.get(d, _KEIN)
            if ablegen and abgeschlossen(d, jetzt):
                speicher.lege((marke, anlage_id, d, rest), gefunden[d], mqtt)
    speicher.treffer += len(tage) - len(fehl)
    speicher.fehltage += len(fehl)
    logger.debug("Merken %s Anlage %s: %d Treffer / %d Fehltage", speicher.name, anlage_id, len(tage) - len(fehl), len(fehl))
    return {d: gefunden[d] for d in tage if gefunden[d] is not _KEIN}


__all__ = [
    "ADAPTER", "GERAETE", "OBERGRENZE_GERAETE", "OBERGRENZE_TAGE", "SPEICHER", "Speicher", "TAGESWAHL", "VERFALL_S", "abgeschlossen", "abmelden",
    "anlage_der_kanaele", "anmelden", "generation", "invalidiere", "je_tag", "leeren", "mqtt_schluessel", "stand",
    "tag_des_vorstands",
]
