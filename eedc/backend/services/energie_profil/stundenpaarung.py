"""Kennzeichen der stundengepaarten Tagesspalten (N-799, Bauplan Fassung 3, E-5/E-11) — für die Tageszeile.

Direktverbrauch, Überschuss und Defizit entstehen je Stunde aus PV und Verbrauch (``tagesbilanz.bilanz_aus_stundenrows``).
Trägt eine Zeile die Mengen mehrerer Stunden (Erfassungs-Stillstand, Lücke), rechnet der Layer ihren Beitrag aus den
Zähler-Mengen des Fensters (``PAARUNG_FENSTER``) oder nennt den Tag nicht rechenbar (``PAARUNG_NICHT_RECHENBAR``). Diese
Datei macht daraus die Felder der Tageszeile: das Kennzeichen, die Stunden des Fensters in Worten (der **Grund**, den der
Client neben die Zahl bzw. statt des «—» stellt) und die Mindest-Netzladung. Sie rechnet keine Energie — nur Uhrzeiten.

Schwesterdateien: ``core/berechnungen/tagesbilanz.py`` (die Rechnung und das Kennzeichen),
``services/energie_profil/tage_werte.py`` (die Tageszeile), ``services/energie_profil/stillstand_marke.py`` (die Marke).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from backend.core.berechnungen.slot_konvention import RASTER_BEGINN, slot_start_ts
from backend.core.berechnungen.tagesbilanz import (
    PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR, URSACHE_SALDIERT, URSACHE_UNGLEICH,
)

_STUNDE_S = 3600

#: Anwender-Text (Client zeigt ihn unter der Tabelle bzw. in der Herkunftszeile, mit dem Link auf den Daten-Checker).
GRUND_FENSTER = ("Für die Stunden {zeitraum} gab es keine Stundenwerte — Überschuss, Defizit und Direktverbrauch "
                 "sind dort aus den Zählerständen gerechnet.")
#: «nicht rechenbar», ungleiche Spannen (Korrekturrunde S2, F13 c): nicht «keine Stundenwerte» — einzelne Zähler hatten sie.
GRUND_NICHT_RECHENBAR = ("Für die Stunden {zeitraum} haben nur einzelne Zähler Stundenwerte geliefert, die übrigen haben "
                         "ihre Menge erst danach nachgetragen — die Mengen gehören nicht zu denselben Stunden. Überschuss, "
                         "Defizit und Direktverbrauch lassen sich für diesen Tag nicht bestimmen.")
#: «nicht rechenbar», Speicher nur als Saldo (Bestandstag): Ladung und Entladung lassen sich nicht trennen.
GRUND_SALDIERT = ("Für die Stunden {zeitraum} gab es keine Stundenwerte, und der Speicher ist für diesen Tag nur als Saldo "
                  "von Ladung und Entladung gespeichert — Überschuss, Defizit und Direktverbrauch lassen sich für diesen "
                  "Tag nicht bestimmen.")


def _zeilen_start_ts(tag: date, stunde: int, raster: Optional[str]) -> Optional[int]:
    """``start_ts`` der echten Stunde, die eine Zeile trägt: Mischzeile (Beginn-Raster) ``[stunde, stunde+1)`` — am
    Herbst-Umstellungstag die spätere der doppelten Wanduhr-Stunde (dort steht ein Nachtrag); Bestandszeile ``slot``."""
    if raster == RASTER_BEGINN:
        return int(datetime(tag.year, tag.month, tag.day, stunde, fold=1).timestamp())
    return slot_start_ts(tag, stunde)


def zeitraeume(tag: date, paarung_zeilen) -> list[tuple[datetime, datetime]]:
    """Die Fenster der gekennzeichneten Zeilen als ``(von, bis)`` in Ortszeit (``bis`` = Ende der Nachtragsstunde)."""
    out = []
    for stunde, n, raster, *_art in paarung_zeilen:
        if stunde is None:
            continue
        start = _zeilen_start_ts(tag, int(stunde), raster)
        if start is None:
            continue
        ende = start + _STUNDE_S
        out.append((datetime.fromtimestamp(ende - max(1, int(n)) * _STUNDE_S), datetime.fromtimestamp(ende)))
    # Überlappende Fenster (Zähler mit verschiedenen Spannen an einem «nicht rechenbaren» Tag) als ein Zeitraum nennen.
    zusammen: list[tuple[datetime, datetime]] = []
    for von, bis in sorted(out):
        if zusammen and von <= zusammen[-1][1]:
            zusammen[-1] = (zusammen[-1][0], max(bis, zusammen[-1][1]))
        else:
            zusammen.append((von, bis))
    return zusammen


def _uhr(t: datetime) -> str:
    return f"{t.hour}" if t.minute == 0 else f"{t.hour}:{t.minute:02d}"


def zeitraum_text(tag: date, von: datetime, bis: datetime) -> str:
    """«von 6 bis 18 Uhr» innerhalb des Tages (``bis`` darf Mitternacht des Folgetags sein, dann «24 Uhr»), sonst
    «vom 31.10. 10 Uhr bis 5.11. 19 Uhr»."""
    bis_am_tag = bis.date() == tag or (bis.date() > tag and bis.hour == 0 and bis.minute == 0
                                       and (bis.date() - tag).days == 1)
    if von.date() == tag and bis_am_tag:
        ende = "24" if bis.date() != tag else _uhr(bis)
        return f"von {_uhr(von)} bis {ende} Uhr"
    return f"vom {von.day}.{von.month}. {_uhr(von)} Uhr bis {bis.day}.{bis.month}. {_uhr(bis)} Uhr"


def grund_satz(tag: date, bilanz: Any) -> Optional[str]:
    """Der Grund der drei Tagesspalten — ``None`` bei voll gepaartem Tag."""
    paarung = getattr(bilanz, "stundenpaarung", None)
    if paarung not in (PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR):
        return None
    teile = [zeitraum_text(tag, von, bis) for von, bis in zeitraeume(tag, getattr(bilanz, "paarung_zeilen", ()))]
    zeitraum = " und ".join(teile) if teile else "dieses Tages"
    if paarung == PAARUNG_FENSTER:
        return GRUND_FENSTER.format(zeitraum=zeitraum)
    arten = {z[3] for z in getattr(bilanz, "paarung_zeilen", ()) if len(z) > 3}
    if URSACHE_SALDIERT in arten and URSACHE_UNGLEICH not in arten:
        return GRUND_SALDIERT.format(zeitraum=zeitraum)
    return GRUND_NICHT_RECHENBAR.format(zeitraum=zeitraum)


def felder_der_tageszeile(tag: date, bilanz: Any) -> dict:
    """Die Felder der Tageszeile (``TagWerteResponse``): ``stundenpaarung`` (``None`` = jede Stunde gepaart),
    ``stundenpaarung_grund`` und ``mindest_netzladung_kwh``."""
    paarung = getattr(bilanz, "stundenpaarung", None)
    mindest = getattr(bilanz, "mindest_netzladung_kwh", None)
    return {
        "stundenpaarung": paarung if paarung in (PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR) else None,
        "stundenpaarung_grund": grund_satz(tag, bilanz),
        "mindest_netzladung_kwh": round(mindest, 3) if mindest is not None else None,
    }


def paarung_rechenbar(bilanz: Any) -> bool:
    """Tragen Direktverbrauch, Überschuss und Defizit der Bilanz eine Aussage? (nicht ``PAARUNG_NICHT_RECHENBAR``)"""
    return getattr(bilanz, "stundenpaarung", None) != PAARUNG_NICHT_RECHENBAR


__all__ = ["GRUND_FENSTER", "GRUND_NICHT_RECHENBAR", "GRUND_SALDIERT", "felder_der_tageszeile", "grund_satz", "paarung_rechenbar",
           "zeitraeume", "zeitraum_text"]
