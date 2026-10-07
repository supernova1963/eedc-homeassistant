"""Lade-Kontext je Anfrage — die Kanal-Leser laden je Anfrage einmal (HA-Bauform E4f, Auftrag Punkt 3a).

**Warum.** Eine Seite ruft die Monats-Fakten mehrfach (Cockpit → Jahr: Kopf, Liste, CO₂ und je Monat die Monatssicht),
und jede Fakten-Gruppe (Bilanz · E-Mob/Sonstiges · Wärmepumpe · Preis) liest ihre Monatsreihe selbst: dieselben
Randstände, dieselben Stammdaten, dieselbe Quellenwahl, je Aufruf neu (E4a-2 B7 „+70 ms je Route", E4b B-1
„Doppelladung", E4e „Zeitfenster-Weg 104 Aufrufe"). Der Kontext hält diese Ergebnisse für die Dauer EINER Anfrage.

**Was er hält** (je Sitzung, Schlüssel ohne Uhrzeit-Drift — die Uhr der Leser steht je Anfrage still):

* die Randstände je Kanal und Zeitpunkt (``lesen._randstaende``) — das ist „die Monatsreihe": jede Gruppe, jeder
  Fakten-Aufruf, jedes Fenster (Monat, Kalendermonat, Jahr) liest einen Rand nur einmal, und nur die Kanäle, die eine
  Gruppe braucht. ⚑ Gemessen und verworfen (E4f): die Ränder ALLER Kanäle der Anlage zu Beginn der Anfrage in einer
  Anweisung zu lesen — an der Zwölf-Jahres-Kopie +50 ms je Route mit einem Fakten-Aufruf (es lädt Kanäle, die keine
  Gruppe fragt, z. B. die Betriebsart-Mitschrift), kein Gewinn bei Cockpit → Jahr;
* die geladenen Kanäle (``lesen.kanaele_laden``), die Stammdaten der Leser (``_stamm``: Anlage, Investitionen,
  Zähler je Menge aktiver Investitionen, Verfügbarkeit) und die kleinen Existenzfragen;
* die Quellenwahl je Gruppe und Fenster (``monate_bilanz``, ``geraete_leser._je_zeitraum``, ``wp_leser._je_zeitraum``,
  ``preis_leser.preis_monate``) und die Netzbezugs-Gewichte des Zeitfenster-Tarifs (``preis_leser``).

**Wann er gilt.** Nur innerhalb von ``lese_anfrage()`` — die App setzt ihn für jede GET-Anfrage (``main.py``,
Middleware ``kanal_lade_kontext``). Außerhalb (schreibende Routen, Scheduler, Stundenlauf, Nachfüllen,
Konsistenzlauf, Proben ohne ihn) liest jede Funktion wie bisher. ⛔ **Kein Modul-Cache über Anfragen hinweg:** der
Kontext lebt in der Sitzung der Anfrage und wird mit ihr verworfen; ein Kontext einer früheren Anfrage gilt nie.

**Schreiben leert ihn.** Jede schreibende Anweisung der Sitzung (ORM-Flush, ``commit``, ``rollback``, ein
``execute`` ohne ``SELECT``/``WITH``) verwirft alles Gehaltene, und ein Ergebnis, dessen Berechnung von einem
Schreiben überholt wurde, wird nicht gehalten (Generation). Der Kontext ist damit eine reine Laufzeit-Maßnahme: mit
und ohne ihn liefert jede Funktion dieselben Zahlen (Probe ``test_e4f_lade_kontext.py``).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Optional, TypeVar

from sqlalchemy import event

T = TypeVar("T")

_INFO_SCHLUESSEL = "eedc_kanal_lade_kontext"


class _Anfrage:
    """Eine Anfrage: ihre stehende Uhr (Unix-Sekunden, beim ersten Lesen gesetzt)."""

    __slots__ = ("jetzt",)

    def __init__(self) -> None:
        self.jetzt: Optional[int] = None


_ANFRAGE: ContextVar[Optional[_Anfrage]] = ContextVar("eedc_kanal_lade_anfrage", default=None)


class LadeKontext:
    """Was eine Sitzung in einer Anfrage schon gelesen hat."""

    def __init__(self, anfrage: _Anfrage) -> None:
        self.anfrage = anfrage
        #: ``(kanal_id, zeitpunkt)`` → ``(vor, nach)`` — die Randstände von ``lesen._randstaende``.
        self.rand: dict[tuple[int, int], tuple[Any, Any]] = {}
        #: beliebige Ergebnisse je Schlüssel (``gemerkt``).
        self.werte: dict[Any, Any] = {}
        #: steigt mit jedem Leeren — ein Ergebnis, das während eines Schreibens entstand, wird nicht gehalten.
        self.generation = 0

    def leeren(self) -> None:
        self.rand.clear()
        self.werte.clear()
        self.generation += 1


@contextmanager
def lese_anfrage():
    """Eine lesende Anfrage: innerhalb gilt der Kontext (je Sitzung einer), danach nie wieder."""
    token = _ANFRAGE.set(_Anfrage())
    try:
        yield
    finally:
        _ANFRAGE.reset(token)


def _ist_lesend(stmt: Any) -> bool:
    if getattr(stmt, "is_select", False):
        return True
    if getattr(stmt, "is_dml", False) or getattr(stmt, "is_ddl", False):
        return False
    roh = getattr(stmt, "text", None)
    if isinstance(roh, str):
        kopf = roh.lstrip()[:6].upper()
        return kopf.startswith("SELECT") or kopf.startswith("WITH")
    return False


def _haenge_an(sitzung, k: LadeKontext) -> None:
    def _leeren(*_a, **_k) -> None:
        k.leeren()

    for ereignis in ("after_flush", "after_commit", "after_rollback", "after_soft_rollback"):
        event.listen(sitzung, ereignis, _leeren)

    def _ausfuehren(state) -> None:
        if not _ist_lesend(state.statement):
            k.leeren()

    event.listen(sitzung, "do_orm_execute", _ausfuehren)


def kontext(db) -> Optional[LadeKontext]:
    """Der Kontext dieser Sitzung in der laufenden Anfrage — ``None`` außerhalb von ``lese_anfrage()``."""
    anfrage = _ANFRAGE.get()
    if anfrage is None or db is None:
        return None
    sitzung = getattr(db, "sync_session", db)
    info = getattr(sitzung, "info", None)
    if info is None:
        return None
    k = info.get(_INFO_SCHLUESSEL)
    if k is None:
        k = LadeKontext(anfrage)
        info[_INFO_SCHLUESSEL] = k
        _haenge_an(sitzung, k)
    elif k.anfrage is not anfrage:      # dieselbe Sitzung in einer neuen Anfrage: nichts übernehmen
        k.leeren()
        k.anfrage = anfrage
    return k


def uhr_der_anfrage(echte_uhr: Callable[[], int]) -> int:
    """Innerhalb einer Anfrage steht die Uhr der Leser still (ein Zeitpunkt für alle Gruppen und Aufrufe — sonst
    bekäme jede Gruppe ihre eigene Sekunde und kein Ergebnis wäre wiederverwendbar); außerhalb die echte Uhr."""
    anfrage = _ANFRAGE.get()
    if anfrage is None:
        return echte_uhr()
    if anfrage.jetzt is None:
        anfrage.jetzt = int(echte_uhr())
    return anfrage.jetzt


async def gemerkt(db, schluessel: Any, fabrik: Callable[[], Awaitable[T]]) -> T:
    """``fabrik()`` einmal je Anfrage und Schlüssel; ohne Kontext jedes Mal. ⚠ Der Aufrufer gibt veränderliche
    Ergebnisse (dict, list) als Kopie weiter — gehalten wird das Original."""
    k = kontext(db)
    if k is None:
        return await fabrik()
    if schluessel in k.werte:
        return k.werte[schluessel]
    gen = k.generation
    wert = await fabrik()
    if k.generation == gen:
        k.werte[schluessel] = wert
    return wert


__all__ = ["LadeKontext", "gemerkt", "kontext", "lese_anfrage", "uhr_der_anfrage"]
