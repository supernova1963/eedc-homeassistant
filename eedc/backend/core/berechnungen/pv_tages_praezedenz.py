"""Welche PV-Quelle trägt einen Tag — die Einzelzähler oder das Aggregat? (#406)

**Die Entsprechung der Monatspräzedenz auf der Tages-/Stundenebene.** Im Monat
löst ``pv_verteilung.resolve_pv_je_modul`` auf: ein Modul mit eigenem Wert
gewinnt immer, das Aggregat füllt nur die **Lücken** der übrigen. Auf der
Tages-/Stundenebene galt bis 2026-09-04 das Gegenteil — ``basis:pv_gesamt``
wurde **verdrängt**, sobald irgendein Erzeuger einen eigenen Zähler *zugeordnet*
hatte (Stufe 1 zu F-7, 2026-08-07).

**Warum die alte Regel fiel (Melder: Mathek, #406).** Sie fragte die
**Konfiguration** (``pv_je_investition_belegt`` auf dem ``sensor_mapping``),
nicht die **Daten**. Zwei Lagen brechen daran:

* **Der Wechseltag.** Wer um 22:00 String-Zähler zuordnet, die in HA erst ab
  21:00 liefern, verliert ab dem Speichern das Aggregat für den ganzen Tag —
  und weil der laufende Tag alle 15 Minuten neu gerechnet wird, rückwirkend bis
  00:00. 21 Stunden gemessene PV waren weg.
* **Der gemischte Fall.** String A mit Zähler, String B ohne: das Aggregat ist
  verdrängt, ``pv_kw`` ist nur noch A. **Die Anlagensumme ist dauerhaft zu
  klein** — nicht bloß die Aufschlüsselung fehlt.

Die Falle war am 07.08. bekannt und wurde bewusst mit einer **Warnung**
beantwortet (``datenquellen_validierung.finde_aggregat_teilweise_verdraengt``):
*„Er macht es schlechter, indem er dem Rat folgt."* #406 belegt, dass die
Warnung nicht reicht — und Matheks Lage löst sie nicht einmal aus, weil er
**allen** Strings einen Zähler gegeben hat und es gar keine Teilbelegung gibt.

**Die Wahl fällt je TAG, nicht je Slot** (Entscheid Gernot, 2026-09-04). Der
Monat wählt je Periode, nicht je Teilintervall; die Übertragung auf den Tag ist
„je Tag und je Modul". Slotweise Mischung hätte zwei Quellen in EINEM Tag —
und der Snapshot-Tagespfad ist **ein** Boundary-Diff über das HA-Tagesfenster
(``get_komponenten_tageskwh``), der Stundenpfad 24 Deltas über das
Rückwärtsfenster. Bei einheitlicher Tageswahl behalten beide exakt die
Konsistenz, die sie heute haben; es braucht keine Slot-Maske.

⛔ **Was diese Regel NICHT ändert: das Aggregat wird nie neben seine eigenen
Summanden gebucht.** ``komponenten_kwh`` hat einen flachen Keyspace und
``summe_pv_bkw_kwh`` summiert **alles** mit Präfix ``pv_``/``bkw_``. Stünde
``pv_gesamt`` neben ``pv_7``, wäre das die Doppelzähl-Klasse aus #290/#298.
Deshalb: Das Aggregat wird entweder als **Summe** verwendet (Stundenebene) oder
in seine **Bestandteile aufgelöst** (Tagesebene, über ``resolve_pv_je_modul``) —
nie zusätzlich gebucht. Der Unterschied zur alten Regel ist *auflösen* statt
*verdrängen*, nicht *addieren*.

**Der Preis, ausdrücklich benannt:** Fällt der Zähler eines Erzeugers für EINE
Stunde aus, fällt der ganze Tag auf das Aggregat zurück, obwohl 23 Stunden
gemessen waren. Das ist kein Verlust — das Aggregat misst dieselbe Anlage —,
aber es ist gröber als eine slotweise Wahl. Bewusst so gewählt.

Architektur-Anker: ADR-001 (``core/berechnungen``); dieses Modul kennt keine
Sessions, keine Sensoren und kein ``sensor_mapping`` — es bekommt Zahlen.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Sequence

from backend.core.berechnungen.anlagen_kwp import BKW_TYP, PV_MODUL_TYP
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger

# Welche Quelle trägt den Tag.
QUELLE_EINZEL = "einzel"
QUELLE_AGGREGAT = "aggregat"
QUELLE_KEINE = "keine"


def erwartete_erzeuger_ids(
    investitionen: Sequence[Any],
    stichtag: date,
) -> set[str]:
    """Die Erzeuger, die an ``stichtag`` einen eigenen PV-Wert tragen KÖNNTEN.

    Grundgesamtheit der Vollständigkeitsfrage: Wer hier steht und **keinen**
    Tageswert liefert, ist eine Lücke — und eine Lücke wählt das Aggregat.

    ``erzeuger_traeger`` läuft **nach** dem Aktiv-Filter (N-266): ein
    Balkonkraftwerk mit ``pv-module``-Kindern hat seine Erzeugungsgrößen an die
    Kinder abgetreten und ist selbst kein Träger mehr. Dieselbe Menge wie in
    ``anlagen_kwp.summe_erzeuger_kwp(mit_bkw=True)`` — Zähler und Nenner der
    Vollständigkeitsfrage müssen dieselbe Grundgesamtheit haben.

    IDs kommen als ``str`` zurück, weil die Aggregatoren ihre Sensor-Keys in
    dieser Form führen (``inv:<id>:<feld>``).
    """
    aktive = [
        inv for inv in (investitionen or ())
        if getattr(inv, "typ", None) in (PV_MODUL_TYP, BKW_TYP)
        and inv.ist_aktiv_an(stichtag)
    ]
    return {str(inv.id) for inv in erzeuger_traeger(aktive)}


def einzel_deckt_den_tag(
    *,
    erwartete_ids: set[str],
    gedeckte_ids_je_slot: dict[int, set[str]],
    aggregat_je_slot: dict[int, Optional[float]],
) -> bool:
    """Tragen die Einzelzähler den **ganzen** Tag?

    Wahr, wenn in **jedem** Slot mit überhaupt einer PV-Angabe alle erwarteten
    Erzeuger ein Delta geliefert haben. Ein Slot ohne jede Angabe (weder
    Aggregat noch Einzelzähler — typisch die Nachtstunden einer Anlage ohne
    Aggregat) stellt keine Frage und wird übergangen.

    ⚠ **Ein Erzeuger ohne jeden Zähler ist damit dauerhaft eine Lücke** — genau
    der gemischte Fall, der die Anlagensumme zu klein machte.

    Leere ``erwartete_ids`` (keine Erzeuger-Investition gepflegt) ⇒ ``False``:
    „niemand trägt" ist keine Deckung, und die Wahl fällt dann über das
    Vorhandensein der Daten (s. ``waehle_pv_quelle``).
    """
    if not erwartete_ids:
        return False
    for h, gedeckte in gedeckte_ids_je_slot.items():
        hat_angabe = gedeckte or aggregat_je_slot.get(h) is not None
        if hat_angabe and not erwartete_ids <= gedeckte:
            return False
    return True


def waehle_pv_quelle(
    *,
    erwartete_ids: set[str],
    gedeckte_ids_je_slot: dict[int, set[str]],
    aggregat_je_slot: dict[int, Optional[float]],
) -> str:
    """Welche Quelle trägt den Tag — ``einzel``, ``aggregat`` oder ``keine``?

    Präzedenz (die Monatsregel auf Tagesebene):

    1. Alle erwarteten Erzeuger liefern über den ganzen Tag → **einzel**.
    2. Sonst, und das Aggregat liefert → **aggregat**.
    3. Sonst, und irgendein Einzelzähler liefert → **einzel** (Teilsumme; so
       verhält sich der Baum auch heute schon, wenn gar kein Aggregat
       zugeordnet ist — ohne Aggregat gibt es nichts Besseres).
    4. Sonst → **keine**.

    Regel 3 ist die Stelle, an der nichts schlechter wird als heute: eine
    Anlage ohne Aggregat bekommt weiterhin ihre gemessenen Erzeuger.

    Der **Tagespfad** ruft dieselbe Funktion mit einem einzigen Pseudo-Slot
    (``{0: …}``) — eine zweite Formel für dieselbe Frage wäre die F-56-Klasse.
    """
    einzel_hat_daten = any(gedeckte for gedeckte in gedeckte_ids_je_slot.values())
    aggregat_hat_daten = any(v is not None for v in aggregat_je_slot.values())

    if einzel_hat_daten and einzel_deckt_den_tag(
        erwartete_ids=erwartete_ids,
        gedeckte_ids_je_slot=gedeckte_ids_je_slot,
        aggregat_je_slot=aggregat_je_slot,
    ):
        return QUELLE_EINZEL
    if aggregat_hat_daten:
        return QUELLE_AGGREGAT
    if einzel_hat_daten:
        return QUELLE_EINZEL
    return QUELLE_KEINE
