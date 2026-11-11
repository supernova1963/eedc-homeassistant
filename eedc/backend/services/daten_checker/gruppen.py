"""
Daten-Checker — Gruppenbau nach dem Prüflauf (Etappe E5 des Vorhabens «Daten-Checker: ein Handgriff je Befund», Konzept §6 V2).

Gleiche Befunde eines Codes (Katalog `handgriffe.GRUPPEN`, je Gerät bzw. Feld getrennt) zeigt die Oberfläche als **eine**
Zeile «7 Monate fehlen: 01/2026 · 02/2026 · …»; jedes Glied bleibt ein Befund mit eigenem Handgriff (Zählung unverändert,
`zusammenfassung` zählt jedes Glied). Hier entsteht nur die Beschriftung (`CheckErgebnis.gruppe`): Titel mit der Zahl
(Glieder + `werte.weitere` — die Befunde über der Anzeige-Grenze des Erzeugers, früher eine eigene Restzeile), Glied aus
dem Datum bzw. Monat des Befunds. Keine neue Rechnung, keine Zahl, die der Erzeuger nicht schon hat; der Client gruppiert
nach `gruppe.schluessel` und rechnet nichts.

Eine Gruppe entsteht ab zwei Gliedern oder wenn der Erzeuger Befunde über seiner Grenze weggelassen hat.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .handgriffe import GRUPPEN, GruppenVorlage
from .kategorien import CheckErgebnis, Gruppe


def _glied(e: CheckErgebnis, art: str) -> Optional[str]:
    """``datum`` ⇒ «02.11.2026» aus ``werte.datum``; ``monat`` ⇒ «01/2026» aus ``ziel.params.erfassen``."""
    if art == "datum":
        d = (e.werte or {}).get("datum")
        return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if isinstance(d, str) and len(d) == 10 else None
    m = (e.ziel.params.get("erfassen") if e.ziel else None)
    return f"{m[5:7]}/{m[:4]}" if isinstance(m, str) and len(m) == 7 else None


def _trenner(e: CheckErgebnis, vorlage: GruppenVorlage) -> tuple:
    werte = []
    for je in vorlage.je:
        werte.append(e.investition_id if je == "investition_id" else (e.ziel.params.get(je) if e.ziel else None))
    return tuple(werte)


def gruppen_bilden(ergebnisse: list[CheckErgebnis]) -> None:
    """Setzt ``gruppe`` an den Gliedern jeder Gruppe (in place; Reihenfolge der Befunde bleibt)."""
    gruppen: dict[tuple, list[CheckErgebnis]] = defaultdict(list)
    for e in ergebnisse:
        vorlage = GRUPPEN.get(e.code or "")
        if vorlage is not None and _glied(e, vorlage.glied) is not None:
            gruppen[(getattr(e.kategorie, "value", e.kategorie), e.code, _trenner(e, vorlage))].append(e)
    for (kategorie, code, trenner), glieder in gruppen.items():
        weitere = max(int((g.werte or {}).get("weitere") or 0) for g in glieder)
        if len(glieder) < 2 and weitere == 0:
            continue
        vorlage = GRUPPEN[code]
        schluessel = ":".join([kategorie, code, *(str(t) for t in trenner)])
        titel = vorlage.titel.format(n=len(glieder) + weitere)
        for g in glieder:
            g.gruppe = Gruppe(schluessel=schluessel, titel=titel, glied=_glied(g, vorlage.glied), weitere=weitere,
                              details=vorlage.details)
