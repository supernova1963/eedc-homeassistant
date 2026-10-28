"""Stunden je Betriebsart einer Wärmepumpe über einen Tag — eine Formel, ein Ort (P-433-2c, Karte «Betrieb heute»).

**Eingang** ist die Betriebsart-Mitschrift (HA-Bauform E1): je Stunde und Kanon-Modus der **Anteil** der Stunde, in
dem das Gerät in diesem Modus stand (0 … 1, Mittelwert-Kanal ``modus:inv:<id>:<modus>``). Die Stunden je Betriebsart
sind die Σ dieser Anteile über die Stunden des Tages — gemessene Zeit, nichts geschätzt.

* **Nur die Betriebsarten** ``heizen · warmwasser · kuehlen · lueften · entfeuchten`` (Kanon ``core/betriebsmodus.py``).
  ``aus`` und ``unbestimmt`` sind kein Betrieb und stehen nicht in der Antwort.
* **Kein Leerlauf** (benannte Grenze): der Kanon verwirft die Aktion ``idle`` beim Schreiben der Mitschrift — eine
  Stunde «Heizen · Leerlauf» zählt als Heizen. Leerlauf-Stunden kann diese Funktion deshalb nicht nennen.
* **Eine gemessene 0 bleibt stehen** (ADR-002/P4): die Mitschrift schreibt je Stunde jeden Modus (0 = gemessen nicht
  in diesem Modus); ein Tag, an dem das Gerät nur ``aus`` war, liefert ``{heizen: 0.0, …}`` — «kein Betrieb» ist eine
  Auskunft. Eine Betriebsart, die in keiner Stunde eine Zeile hat, fehlt.
* **Ohne eine einzige Zeile:** ``None`` — «nicht mitgeschrieben» ist keine 0.

Die Schlüssel von ``anteile_je_stunde`` sind beliebige, je Stunde eindeutige Ganzzahlen (der Leser nimmt den
``start_ts`` der Zeile): so zählen in der Herbst-Doppelstunde beide realen Stunden. Gerundet auf 0,1 h.

Aufrufer: ``api/routes/energie_profil/tag.py::_mit_betrieb_stunden`` (Tag-Detail, je Gerät ``betrieb_stunden``) über
den Tagesleser ``services/energie_profil/kanal_stunden.py::wp_betriebsart_anteile_je_stunde``.

**Typoffen seit P-433-2b K3** (Bauplan K3-6): ``stunden_je_zustand(anteile, werte_mit_stunden)`` ist dieselbe Formel
mit der Werte-Liste als Parameter — die Wärmepumpe ruft sie mit ``BETRIEBSARTEN_MIT_STUNDEN`` (bitgleich), die
E-Mobilität mit ``core/zustands_kanon.WERTE_MIT_STUNDEN[feld]`` (Wallbox ``laedt · verbunden · wartet · fertig``,
E-Auto ``laedt · laedt_dc · verbunden`` und ``zu_hause · unterwegs``). Eingang dort: die Kanäle
``zustand:inv:<id>:<feld>:<wert>`` (Tagesleser ``kanal_stunden.zustand_anteile_je_stunde``), Aufrufer
``tag.py::_mit_emob_betrieb``. Dieselben Regeln: gemessene 0 bleibt, ohne Zeile ``None``, 0,1 h.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from backend.core.betriebsmodus import ENTFEUCHTEN, HEIZEN, KUEHLEN, LUEFTEN, WARMWASSER

#: Die Betriebsarten, deren Stunden gezählt werden — in Lese-Reihenfolge der Karte.
BETRIEBSARTEN_MIT_STUNDEN: tuple[str, ...] = (HEIZEN, WARMWASSER, KUEHLEN, LUEFTEN, ENTFEUCHTEN)


def stunden_je_zustand(
    anteile_je_stunde: Mapping[int, Mapping[str, float]], werte_mit_stunden: Sequence[str],
) -> Optional[dict[str, float]]:
    """``{wert: Stunden}`` (0,1 h) aus den Anteilen je Stunde, nur für ``werte_mit_stunden`` und in deren Reihenfolge —
    ``None`` ohne eine Zeile eines dieser Werte (P-433-2b K3, die Formel von ``stunden_je_betriebsart``)."""
    summe: dict[str, float] = {}
    for anteile in anteile_je_stunde.values():
        for wert, anteil in anteile.items():
            if wert in werte_mit_stunden and anteil is not None:
                summe[wert] = summe.get(wert, 0.0) + float(anteil)
    if not summe:
        return None
    return {w: round(summe[w], 1) for w in werte_mit_stunden if w in summe}


def stunden_je_betriebsart(anteile_je_stunde: Mapping[int, Mapping[str, float]]) -> Optional[dict[str, float]]:
    """``{betriebsart: Stunden}`` (0,1 h) aus den Anteilen je Stunde — ``None`` ohne eine Zeile einer Betriebsart."""
    return stunden_je_zustand(anteile_je_stunde, BETRIEBSARTEN_MIT_STUNDEN)
