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
"""

from __future__ import annotations

from typing import Mapping, Optional

from backend.core.betriebsmodus import ENTFEUCHTEN, HEIZEN, KUEHLEN, LUEFTEN, WARMWASSER

#: Die Betriebsarten, deren Stunden gezählt werden — in Lese-Reihenfolge der Karte.
BETRIEBSARTEN_MIT_STUNDEN: tuple[str, ...] = (HEIZEN, WARMWASSER, KUEHLEN, LUEFTEN, ENTFEUCHTEN)


def stunden_je_betriebsart(anteile_je_stunde: Mapping[int, Mapping[str, float]]) -> Optional[dict[str, float]]:
    """``{betriebsart: Stunden}`` (0,1 h) aus den Anteilen je Stunde — ``None`` ohne eine Zeile einer Betriebsart."""
    summe: dict[str, float] = {}
    for anteile in anteile_je_stunde.values():
        for modus, anteil in anteile.items():
            if modus in BETRIEBSARTEN_MIT_STUNDEN and anteil is not None:
                summe[modus] = summe.get(modus, 0.0) + float(anteil)
    if not summe:
        return None
    return {m: round(summe[m], 1) for m in BETRIEBSARTEN_MIT_STUNDEN if m in summe}
