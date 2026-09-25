"""Heimlade-Felder — die eine Liste für „Wert oder Quelle" und für „0 ist ein Wert".

SoT der Feldmengen aus dem Konzept Heimladung/Fahrverbrauch (Fassung 7.1, Stufe 1,
Regel 1 und Regel 4). Sie steht hier bei der Feld-Registry, weil beide Fragen **Feldfragen**
sind und von Schichten gestellt werden, die einander nicht importieren dürfen: der
Aufbereitungs-Service (die eine Funktion, ``services/eauto_wirtschaftlichkeit.py``), der
Monatsabschluss (Vorschlag „0 — kein Zuwachs"), der Statistik-Import (eine 0 bleibt stehen)
und der laufende Monat (Quelle zugeordnet?). Eine Liste je Aufrufer wäre die F-56-Klasse.

**Zwei Mengen, weil es zwei Fragen sind:**

* ``HEIMLADE_FELDER`` — *Ist über die Heimladung etwas bekannt?* (Regel 1). Trägt eines dieser
  Felder einen Wert (auch 0) oder, im laufenden Monat, eine Quelle, springt der Fahrverbrauch
  **nicht** ein. Am E-Auto gehört der alte Gesamtwert ``ladung_kwh`` dazu: der
  Zuordnungs-Assistent bis 04.04.2026 bot ihn als „Ladung Gesamt" an, ein MQTT-Topic bildet
  ihn ab, „Aus HA laden" schreibt ihn — er ist eine lebende Quelle (Fable-Runde 6, A1).
* ``HEIMLADE_MENGEN_FELDER`` — *Darf eine 0 vorgeschlagen und stehen gelassen werden?*
  (Regel 4, E1 eng). **Keine PV-Felder:** eine leere PV-Zeile löst die Ableitung des
  PV-Anteils aus der Tagesebene aus (Phase 5, ``services/emob_ladeanteil.py``), eine 0 sperrt
  sie — ein eingefrorener PV-Zähler ergäbe mit Konfidenz 92 eine 0 und damit PV-Anteil 0 %
  statt der Ableitung. Die Wallbox hat **kein** ``ladung_netz_kwh``-Feld in der Registry
  (``registry.py``: ``ladung_kwh``, ``ladung_pv_kwh``, ``ladevorgaenge``) — deshalb steht es
  hier nicht (Fable-Runde 6, C1).
"""

from __future__ import annotations

from typing import Mapping, Optional

#: Regel 1: Felder, deren Wert (auch 0) oder Quelle „über die Heimladung ist etwas bekannt" heißt.
HEIMLADE_FELDER: dict[str, tuple[str, ...]] = {
    "wallbox": ("ladung_kwh", "ladung_pv_kwh"),
    "e-auto": ("ladung_pv_kwh", "ladung_netz_kwh", "ladung_kwh"),
}

#: Regel 4 (E1 eng): Mengenfelder der Heimladung, bei denen eine gemessene 0 ein Wert ist.
HEIMLADE_MENGEN_FELDER: dict[str, tuple[str, ...]] = {
    "wallbox": ("ladung_kwh",),
    "e-auto": ("ladung_netz_kwh", "ladung_kwh"),
}


def ist_heimlade_feld(typ: Optional[str], feld: str) -> bool:
    """Gehört ``feld`` am Gerätetyp ``typ`` zu den Heimlade-Feldern (Regel 1)?"""
    return feld in HEIMLADE_FELDER.get(typ or "", ())


def ist_heimlade_mengen_feld(typ: Optional[str], feld: str) -> bool:
    """Ist ``feld`` am Gerätetyp ``typ`` ein Heimlade-Mengenfeld, bei dem 0 zählt (Regel 4)?"""
    return feld in HEIMLADE_MENGEN_FELDER.get(typ or "", ())


def traegt_heimlade_wert(typ: Optional[str], daten: Optional[Mapping]) -> bool:
    """Trägt diese Monatszeile in einem Heimlade-Feld einen Wert — **auch 0**?

    ``is not None`` statt Wahrheitswert: eine gepflegte 0 ist eine Aussage (CLAUDE.md
    §0-Werte prüfen), und genau sie unterscheidet „Wallbox hat nicht geladen" von
    „über die Heimladung ist nichts bekannt".
    """
    if not daten:
        return False
    return any(daten.get(f) is not None for f in HEIMLADE_FELDER.get(typ or "", ()))
