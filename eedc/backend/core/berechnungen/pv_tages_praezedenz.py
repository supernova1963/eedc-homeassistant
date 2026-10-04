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

**Der Aggregat-Tag löst auf Träger-Ebene auf (N-623, Bauplan Fassung 2,
04.10.2026).** Trägt der Anlagenzähler den Tag, behält ein Erzeuger mit eigenem
Zähler seinen **Tageswert** — die Summe aller seiner brauchbaren Slots, die in
keine Stunde geht (die Stundenachse bleibt die Aggregat-Summe). Gemessen ist er,
wenn kein Slot verworfen wurde und seine unsichere Energie höchstens
``DAEMMERUNGSREST_ANTEIL`` des Tages ist (``gemessene_tageswerte``); die übrigen
Träger teilen den Rest nach kWp, und Σ der Träger ist immer das Aggregat
(``loese_aggregat_tag_auf``). Bis dahin verwarf die Tagesebene die Messung und gab
jedem den kWp-Anteil — ein Balkonkraftwerk mit eigenem Zähler stand mit 1,56 statt
3,0 kWh im Tag.

Architektur-Anker: ADR-001 (``core/berechnungen``); dieses Modul kennt keine
Sessions, keine Sensoren und kein ``sensor_mapping`` — es bekommt Zahlen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Collection, Optional, Sequence

from backend.core.berechnungen.anlagen_kwp import BKW_TYP, PV_MODUL_TYP
from backend.core.berechnungen.erzeuger_traeger import (
    abgetretene_bkw_ids,
    erzeuger_traeger,
)
from backend.core.berechnungen.pv_verteilung import (
    QUELLE_VERTEILT,
    PvModul,
    resolve_pv_je_modul,
)
from backend.core.investition_kennwerte import get_erzeuger_kwp

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


# ── Aggregat-Tag: gemessene Erzeuger behalten ihren Tageswert (N-623) ──────────

#: Wie viel unsichere Energie ein Erzeuger am Tag tragen darf und trotzdem als
#: **gemessen** gilt — Anteil am Anlagen-Tageswert (Bauplan N-623 Fassung 2,
#: Regel 2 b). Technischer Grund: eine Stunde ohne eigenen Slot, in der die
#: Anlage erzeugt hat, kann eigene Erzeugung enthalten, die der Zähler am Tag
#: nicht nachliefert; ein Bündel-Slot (n > 1) kann Energie von vor dem Tag
#: tragen. Nachtstunden und der Dämmerungsrest sollen nicht zählen. 1 % ist eine
#: **Setzung** aus der Nachstellung (kleinster Wert ohne Rückfalltage); an einer
#: echten Anlage mit schlafendem Zähler nachmessen, sobald erreichbar.
DAEMMERUNGSREST_ANTEIL = 0.01


def gemessene_tageswerte(
    *,
    aggregat_kwh: float,
    aggregat_je_stunde: dict[int, float],
    eigen_kwh: dict[str, float],
    eigen_stunden: dict[str, Collection[int]],
    eigen_buendel_kwh: dict[str, float],
    gesperrt: Collection[str],
) -> dict[str, float]:
    """Welche Erzeuger sind am Aggregat-Tag **gemessen** — und mit welchem Wert?

    Args:
        aggregat_kwh: der Anlagen-Tageswert (Σ der verwendeten Aggregat-Slots).
        aggregat_je_stunde: ``{h: kWh}`` der verwendeten Aggregat-Slots.
        eigen_kwh: ``{inv_id: Tageswert}`` — Σ aller brauchbaren Slots des
            eigenen Zählers (beim Balkonkraftwerk mit Kindern der Rest je Slot, E4).
        eigen_stunden: ``{inv_id: Stunden mit eigenem Slot}``.
        eigen_buendel_kwh: ``{inv_id: Energie der eigenen Bündel-Slots (n > 1)}``.
        gesperrt: inv_ids mit einem verworfenen Slot (R3, R4) oder einem
            Tagesreset — am Tag ohne Aussage.

    Gemessen ist ein Erzeuger, wenn er nicht gesperrt ist und seine **unsichere
    Energie** — Anlagen-Energie der Stunden ohne eigenen Slot plus eigene
    Bündel-Energie — höchstens ``DAEMMERUNGSREST_ANTEIL × aggregat_kwh`` ist.

    ⛔ Kein Stundenabgleich mit dem Aggregat: fehlt dem Anlagenzähler eine Zeile,
    steht ihre Energie im nächsten Slot (R1); den eigenen Wert der Stunde
    wegzulassen machte die Messung zu klein (Gegenprüfung W2). Und keine Deckung
    „jede Aggregat-Stunde": ein Zähler ohne Nachtzeilen wäre sonst nie gemessen (W1).
    """
    grenze = DAEMMERUNGSREST_ANTEIL * aggregat_kwh
    out: dict[str, float] = {}
    for inv_id, wert in eigen_kwh.items():
        if inv_id in gesperrt:
            continue
        stunden = eigen_stunden.get(inv_id) or ()
        unsicher = sum(v for h, v in aggregat_je_stunde.items() if h not in stunden)
        unsicher += eigen_buendel_kwh.get(inv_id, 0.0)
        if unsicher > grenze + 1e-9:
            continue
        out[inv_id] = wert
    return out


@dataclass(frozen=True)
class AggregatTagAufloesung:
    """Ergebnis von ``loese_aggregat_tag_auf``.

    ``werte``: ``{inv_id: kWh}`` je Träger mit Tages-Key (Σ == Aggregat).
    ``verteilt``: inv_ids, deren Wert eine kWp-Zerlegung ist (Marke ``kwp_anteil``).
    ``faktor``: der gemeinsame Abgleich-Faktor (Regel 4), sonst ``None``.
    """

    werte: dict[int, float]
    verteilt: frozenset
    faktor: Optional[float] = None


def loese_aggregat_tag_auf(
    *,
    aggregat_kwh: float,
    gemessen: dict[str, float],
    mit_zaehler: Collection[str],
    investitionen: Sequence[Any],
    datum: date,
) -> AggregatTagAufloesung:
    """Der Aggregat-Tag auf **Träger-Ebene** (Bauplan N-623 Fassung 2, Regeln 3–5).

    Bekommt nur Zahlen und entscheidet nicht noch einmal über die Quelle — die
    Wahl „Aggregat trägt den Tag" ist gefallen (``waehle_pv_quelle``).

    * **Träger.** Jeder gemessene Erzeuger mit seinem Wert (auch ein abgetretenes
      Balkonkraftwerk mit seinem Rest, E4). Ein Kind ohne eigenen Zähler unter
      einem gemessenen Balkonkraftwerk ist keine Lücke und bekommt keinen Key
      (E4, P16 — der BKW-Rest deckt es). Alle übrigen am Tag aktiven Träger sind
      **Lücken** und teilen den Rest nach kWp (``resolve_pv_je_modul``). Ohne
      Erzeuger kein Key.
    * **Abgleich statt Rückfall (Regel 4).** Übersteigt Σ gemessen das Aggregat,
      oder gibt es keine Lücke und Σ gemessen ≠ Aggregat, werden die gemessenen
      Werte mit ``Aggregat / Σ gemessen`` skaliert, Lücken bekommen 0. Grund: die
      Invariante Σ Keys == Σ Stunden verlangt Σ == Aggregat; ein Rückfall auf kWp
      verwürfe alle Messungen und spränge an der Grenze, der gemeinsame Faktor
      lässt ihr Verhältnis stehen und ist an der Grenze 1. Σ gemessen = 0 ohne
      Lücke ⇒ alle nach kWp wie bisher.
    * **Marken (Regel 5).** ``verteilt`` nur für Lücken; gemessene und
      abgeglichene Werte sind keine Zerlegung.

    ``gemessen``/``mit_zaehler`` tragen inv_ids als ``str`` (Sensor-Key-Form).
    """
    erzeuger = [i for i in investitionen if getattr(i, "typ", None) in (PV_MODUL_TYP, BKW_TYP)]
    am_tag = [i for i in erzeuger if i.ist_aktiv_an(datum)]
    aktiv = {i.id for i in am_tag}
    abgetreten = abgetretene_bkw_ids(am_tag)

    module: list[PvModul] = []
    for inv in erzeuger:
        sid = str(inv.id)
        eigen = gemessen.get(sid)
        if eigen is not None:                      # gemessen: immer Träger (auch BKW-Rest, E4)
            module.append(PvModul(inv.id, get_erzeuger_kwp(inv), float(eigen)))
            continue
        if inv.id not in aktiv:
            continue
        if inv.typ == BKW_TYP and inv.id in abgetreten:
            continue                               # Träger sind die Kinder
        parent = getattr(inv, "parent_investition_id", None)
        if (inv.typ == PV_MODUL_TYP and parent in abgetreten
                and str(parent) in gemessen and sid not in mit_zaehler):
            continue                               # vom BKW-Rest gedeckt (E4): keine Zerlegung
        module.append(PvModul(inv.id, get_erzeuger_kwp(inv), None))

    if not module:
        return AggregatTagAufloesung({}, frozenset())
    summe_eigen = sum(m.eigen_kwh for m in module if m.eigen_kwh is not None)
    luecken = [m for m in module if m.eigen_kwh is None]
    hat_gemessen = len(luecken) < len(module)
    if hat_gemessen and (summe_eigen > aggregat_kwh or (not luecken and summe_eigen != aggregat_kwh)):
        if summe_eigen > 0:
            faktor = aggregat_kwh / summe_eigen
            return AggregatTagAufloesung(
                {m.inv_id: (m.eigen_kwh * faktor if m.eigen_kwh is not None else 0.0) for m in module},
                frozenset(m.inv_id for m in luecken),
                faktor,
            )
        module = [replace(m, eigen_kwh=None) for m in module]   # Σ gemessen = 0: alle nach kWp wie bisher
    aufgeloest = resolve_pv_je_modul(aggregat_kwh=aggregat_kwh, module=module)
    return AggregatTagAufloesung(
        {i: w.pv_erzeugung_kwh for i, w in aufgeloest.items()},
        frozenset(i for i, w in aufgeloest.items() if w.quelle == QUELLE_VERTEILT),
    )
