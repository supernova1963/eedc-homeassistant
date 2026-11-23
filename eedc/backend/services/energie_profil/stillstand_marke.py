"""Die Marke des Erfassungs-Stillstands an den Mischzeilen eines Kanal-Tags (N-799, Bauplan Fassung 3, E-2/E-3/E-8).

``kanal_stunden.stunden_des_tages`` (``/stunden``) und ``kanal_stunden.stunden_der_kanal_tage`` (``tage-werte``,
``monat``, die Lesestelle ``stunden_der_tage`` aller Stundenleser) hängen hier ein, **je Aufruf** — nicht im gemerkten
Adapter (``merken.ADAPTER`` hält die Adapter-Zeilen, die Mischzeile entsteht je Aufruf neu, und nur sie bekommt die
Marke). Eine eigene Datei, weil ``kanal_stunden.py`` an der Dateilängen-Grenze steht.

**Die Marke** (Fenster aus ``services/kanal/stillstand.py``, nur markierbare): die Nachtragszeile trägt auf den Achsen
des Fensters ``n = k + 1`` (E-2; Nebenachsen nur, wenn sie erben), jede Zeile im Fenster ``n = 0`` (E-3) — die Menge
bleibt, wo HA sie hinschreibt, jede Summe bleibt gleich. ``ueberschuss_kw``/``defizit_kw`` einer markierten Zeile sind
``None`` (E-3): sie wären die Paarung einer Mehr-Stunden-Menge als eine Stunde. Leser, die Stunde gegen Stunde stellen,
lassen die Zeilen über ``spannen.zeile_gebuendelt`` (n ≠ 1) aus.

Nur Zeilen, deren Bilanz aus den Kanälen kommt (``aus_kanal_gruppe(z, "pv_kw")``) — ein Bestandstag trägt keine Marke
(E-9, benannte Grenze G-4).

Die Schreiber des Heimladungs-Anteils (Tageszeile am Kanal-Tag und im Bestandsweg, abgeleiteter Kanal) lesen die
Fenster selbst und fragen die eine Regel ``spannen.stillstand_ohne_ladeanteil`` (Nachtrag G; ``stunden_der_zeile`` hier
bildet die echten Stunden einer Kanal-Stunde).

Schwesterdateien: ``kanal_stunden.py`` (die Mischzeilen), ``services/kanal/stillstand.py`` (die Fenster),
``core/berechnungen/spannen.py`` (die Regel).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.spannen import StillstandFenster, marke_der_stunde

#: Die Felder einer markierten Zeile, die keine Stundenpaarung tragen dürfen (E-3).
_OHNE_PAARUNG = ("ueberschuss_kw", "defizit_kw")


def stunden_der_zeile(datum: date, stunde: int) -> tuple[int, ...]:
    """Die echten Stunden (``start_ts``), die die Zeile ``stunde`` eines Kanal-Tags trägt (Beginn-Raster): eine, am
    Herbst-Umstellungstag für die doppelte Wanduhr-Stunde beide, am Frühjahrs-Umstellungstag für die fehlende keine
    (N-799 F11: ``timestamp()`` einer nicht existenten Wanduhr liefert eine NACHBARstunde — die leere Zeile «2 Uhr» trug
    sonst die Marke von 1 bzw. 3 Uhr, und ein Nachtrag um 3 Uhr stand in zwei Zeilen; wie ``slot_konvention.slot_start_ts``)."""
    wand = datetime(datum.year, datum.month, datum.day, stunde)
    return tuple(sorted({ts for ts in (int(wand.replace(fold=f).timestamp()) for f in (0, 1))
                         if datetime.fromtimestamp(ts) == wand}))


def markiere(datum: date, zeilen: Iterable, fenster: Iterable[StillstandFenster]) -> None:
    """Die Marke an den Mischzeilen eines Tages setzen (an Ort und Stelle; die Mischzeilen entstehen je Aufruf neu)."""
    from backend.services.energie_profil.kanal_stunden import aus_kanal_gruppe

    fenster = list(fenster)
    for z in zeilen:
        if not aus_kanal_gruppe(z, "pv_kw"):
            continue
        marke = marke_der_stunde(fenster, stunden_der_zeile(datum, z.stunde))
        if marke is None:
            continue
        n, achsen = marke
        z.spannen = {**(z.spannen or {}), **{a: n for a in sorted(achsen)}}
        for feld in _OHNE_PAARUNG:
            z.setze_kanal_feld(feld, None)


async def markiere_stillstand(db: AsyncSession, anlage_id: int, je_tag: Mapping[date, list]) -> Mapping[date, list]:
    """Die Mischzeilen ``je_tag`` (Tag → Liste) mit der Marke der Erfassungs-Stillstände der Tage — dieselbe Abbildung
    zurück. Ohne Tag oder ohne Fenster unverändert."""
    from backend.services.energie_profil.kanal_stunden import aus_kanal_gruppe

    tage = [d for d, zeilen in je_tag.items() if any(aus_kanal_gruppe(z, "pv_kw") for z in zeilen)]
    if not tage:        # kein Tag mit Bilanz aus den Kanälen: keine Marke, kein Lesen
        return je_tag
    from backend.services.kanal.stillstand import fenster_im_bereich

    fenster = await fenster_im_bereich(db, anlage_id, min(tage), max(tage))
    if fenster:
        for d, zeilen in je_tag.items():
            markiere(d, zeilen, fenster)
    return je_tag


__all__ = ["markiere", "markiere_stillstand", "stunden_der_zeile"]
