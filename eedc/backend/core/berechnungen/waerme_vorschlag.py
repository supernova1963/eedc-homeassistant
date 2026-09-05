"""Die Strom-Basis eines Wärme-Vorschlags — welcher Strom darf mit der JAZ multipliziert werden?

**Regel (SOLL Wärme/Klima §6, Präzisierung F2–F5 vom 05.09.2026):** Eine
*abgeleitete* Wärme — ``Strom × gepflegte JAZ`` — ist als **Schätzung** zulässig,
trägt die Marke ``jaz_vorschlag`` und ist nie Kennzahl-Basis (§4.2/2). **Und sie
entsteht nur aus dem Strom derselben Funktion** (§1: dasselbe Gerät, dieselbe
Funktion, derselbe Zeitraum):

* **Heizwärme** aus dem **Heizstrom** — gemessen je Betriebsart (F4,
  ``betriebsart_strom_heizen_kwh``), sonst aus der getrennten Messung (F5,
  ``strom_heizen_kwh``), sonst aus dem **Gesamt**strom (F2) — aber nur, wenn am
  Gerät **kein Strom einer anderen Funktion belegt** ist. Steht in der Zeile ein
  Kühl-, Lüft- oder Entfeucht-Strom, eine Kältemenge oder ein getrennter
  Warmwasser-Strom, ist der Gesamtstrom nicht der Heizstrom — dann gibt es
  **keinen** Vorschlag, statt eines falschen.
* **Warmwasser-Wärme** nur aus dem **Warmwasser-Strom** (F5,
  ``strom_warmwasser_kwh``). Ohne getrennte Strommessung gibt es keinen
  Warmwasser-Vorschlag: die Menge steckt dann im Heizwärme-Vorschlag (die
  Gesamtwärme landet unter „Heizwärme", N-391).

**Was das repariert — gemessen am Code vom 05.09.2026 (Paket B1):**

1. **Doppelzählung an F2.** Ohne getrennte Strommessung schlug der Dienst für
   *beide* Wärmefelder ``stromverbrauch_kwh × JAZ`` vor; „Lücken füllen" übernahm
   beide, die Gesamtwärme stand doppelt in der Zeile.
2. **Kühlstrom als Heizwärme.** An dietmar1968s Klimaanlage (99 % Kühlbetrieb,
   Betriebsart-Zähler zugeordnet) rechnete der Dienst ``E_gesamt × 3,5`` — 254 kWh
   Kühlstrom wurden 889 kWh „Warmwasser" (T89667 #295). Mit F4 rechnet er jetzt
   mit dem gemessenen **Heizstrom** (im Juni: 0).
3. **Die Herkunft ging verloren.** Der übernommene Vorschlag stand als
   ``manual:form`` ohne Marke in der Zeile; jede Lesestelle hielt ihn für eine
   Messung, und die Arbeitszahl gab die gepflegte JAZ zurück. Die Marke
   (``REGEL_JAZ_VORSCHLAG``) reist jetzt mit dem Vorschlag.

⚠ **Die Bauart entscheidet hier nichts** (R1, ADR-002/P13): ob der Gesamtstrom
der Heizstrom ist, sagt die **Beleglage der Zeile**, nicht ``wp_art``. Eine
Luft-Wasser-Wärmepumpe mit Kühlzähler fällt unter dieselbe Regel wie eine
Klimaanlage; eine Klimaanlage ohne jede Kühl-Spur bekommt den Vorschlag aus dem
Gesamtstrom wie jede andere — und sagt dazu, dass er eine Schätzung ist.

Rein und ohne DB: der Aufrufer (``vorschlag_service``) reicht die ``verbrauch_daten``
des Monats und die Parameter des Geräts herein.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.berechnungen.betriebsart_gemessen import (
    betriebsart_nutzenergie_kwh,
    betriebsart_strom_kwh,
    hat_gemessene_betriebsart,
)
from backend.core.betriebsmodus import HEIZEN, KUEHLEN

#: Die beiden Wärmefelder, für die es einen Vorschlag geben kann.
WAERME_FELDER: tuple[str, str] = ("heizenergie_kwh", "warmwasser_kwh")


@dataclass(frozen=True)
class WaermeVorschlagBasis:
    """Der Strom, der mit der JAZ multipliziert werden darf — und woher er kommt."""
    strom_kwh: float
    #: Anzeigetext der Basis („Strom Heizbetrieb" · „Strom Heizen" · „Strom" · „Strom Warmwasser").
    label: str
    #: Sprosse der Ausstattungs-Leiter (SOLL §6), aus der die Basis stammt.
    sprosse: str


def _zahl(wert) -> Optional[float]:
    if wert is None or isinstance(wert, bool):
        return None
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def gesamtstrom_ist_heizstrom(daten: Optional[dict]) -> bool:
    """Darf ``stromverbrauch_kwh`` als Heizstrom gelten? — nur ohne fremde Spur.

    Belegt ein anderer Funktions-Strom die Zeile (gemessene Betriebsart Kühlen ·
    Lüften · Entfeuchten, eine gemessene Kältemenge oder ein getrennter
    Warmwasser-Strom), enthält der Gesamtstrom Kilowattstunden, die keine Wärme
    erzeugt haben (oder Warmwasser statt Heizung). Dann wäre ``E_gesamt × JAZ``
    keine Schätzung, sondern eine Erfindung.
    """
    d = daten or {}
    if hat_gemessene_betriebsart(d):
        return False
    if betriebsart_nutzenergie_kwh(d, KUEHLEN) is not None:
        return False
    if _zahl(d.get("strom_warmwasser_kwh")) is not None:
        return False
    return True


def strom_basis_fuer_waerme_vorschlag(
    feld: str, daten: Optional[dict], params: Optional[dict],
) -> Optional[WaermeVorschlagBasis]:
    """Die Strom-Basis für ``feld`` (``heizenergie_kwh`` | ``warmwasser_kwh``) — oder ``None``.

    ``None`` heißt: **kein Vorschlag**. Nicht 0, nicht der Gesamtstrom mit einer
    Warnung — nichts. Ein fehlender Vorschlag kostet den Anwender eine Eingabe;
    ein falscher kostet ihn eine Ersparnis, die es nicht gab, und eine
    Arbeitszahl, die nichts misst.
    """
    d = daten or {}
    p = params or {}
    getrennt = bool(p.get("getrennte_strommessung"))

    if feld == "heizenergie_kwh":
        heiz = betriebsart_strom_kwh(d, HEIZEN)
        if heiz is not None:
            return WaermeVorschlagBasis(heiz, "Strom Heizbetrieb", "F4")
        if getrennt:
            sh = _zahl(d.get("strom_heizen_kwh"))
            return WaermeVorschlagBasis(sh, "Strom Heizen", "F5") if sh is not None else None
        ges = _zahl(d.get("stromverbrauch_kwh"))
        if ges is None or not gesamtstrom_ist_heizstrom(d):
            return None
        return WaermeVorschlagBasis(ges, "Strom", "F2")

    if feld == "warmwasser_kwh":
        if not getrennt:
            return None
        sw = _zahl(d.get("strom_warmwasser_kwh"))
        return WaermeVorschlagBasis(sw, "Strom Warmwasser", "F5") if sw is not None else None

    return None
