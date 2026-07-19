"""
Monats-Lücken — Backend-Spiegel von ``frontend/src/lib/monatsLuecken.ts``.

Die EINE Vollständigkeits-Ableitung für „welcher Monat ist offen": derselbe
Bereich ([Anschaffungs-Anker … Vormonat(heute)]), dieselbe Lücken-Logik wie im
Frontend. Zweck: der Endpoint ``GET /monatsabschluss/naechster`` und die
Frontend-Tabellen-Färbung (`monatsLuecken.ts`) müssen DECKUNGSGLEICH sein —
sonst driftet die Status-Fusszeile („alle abgeschlossen") gegen den
Monatsdaten-Block („nächster offener: Jan 2026") auseinander
([[feedback_aggregations_drift]], §7-Invariante „eine Quelle").

Der alte Endpoint sprang naiv auf „letzter Monat + 1" und war damit blind für
Binnen-Lücken (ein fehlender Monat mitten in der Historie).

„Erwarteter Bereich" = [Anschaffungs-Anker … letzter vergangener Monat]:
- Start = frühestes Investitions-``anschaffungsdatum`` (Anschaffungsdatum ist die
  limitierende Grenze für ALLE Auswertungen — [[feedback_anschaffungsdatum_grenze]]),
  Fallback Anlage-Installationsdatum, dann früheste vorhandene Datenzeile.
- Ende = Vormonat von heute (der laufende Monat ist noch nicht abgeschlossen).
Ein Monat OHNE Datenzeile in diesem Bereich gilt als „offen/fehlt".

Rein (keine DB, keine Zeit): identisch testbar gegen die Frontend-Ableitung.
"""

from __future__ import annotations

from datetime import date

# (jahr, monat) — 1-basierter Monat, wie im Frontend.
MonatRef = tuple[int, int]


def monat_index(jahr: int, monat: int) -> int:
    """Fortlaufender Monatsindex (jahr*12 + monat-1) für Vergleich/Iteration."""
    return jahr * 12 + (monat - 1)


def aus_monat_index(idx: int) -> MonatRef:
    """Umkehrung von :func:`monat_index`."""
    return (idx // 12, (idx % 12) + 1)


def ermittle_start_anker(
    anschaffungsdaten: list[date | None],
    anlage_installationsdatum: date | None,
    vorhandene: set[MonatRef],
) -> MonatRef | None:
    """
    Bereichs-Start (Anschaffungs-Anker). Reihenfolge: frühestes Investitions-
    ``anschaffungsdatum`` → Anlage-Installationsdatum → früheste vorhandene
    Datenzeile. ``None``, wenn keine Quelle greift.
    """
    daten = [d for d in anschaffungsdaten if d is not None]
    fruehestes = min(daten) if daten else anlage_installationsdatum
    if fruehestes is not None:
        return (fruehestes.year, fruehestes.month)
    if vorhandene:
        return aus_monat_index(min(monat_index(j, m) for j, m in vorhandene))
    return None


def ermittle_fehlende_monate(
    vorhandene: set[MonatRef],
    start: MonatRef | None,
    heute: MonatRef,
) -> list[MonatRef]:
    """
    Alle im erwarteten Bereich fehlenden Monate, chronologisch AUFSTEIGEND.
    Bereich = [start … Vormonat(heute)]. Ohne Start (kein Anker) → leer.
    """
    if start is None:
        return []
    vorhanden_set = {monat_index(j, m) for j, m in vorhandene}
    start_idx = monat_index(*start)
    # Ende = letzter VOLLSTÄNDIG vergangener Monat = Vormonat(heute).
    ende_idx = monat_index(*heute) - 1
    return [
        aus_monat_index(i)
        for i in range(start_idx, ende_idx + 1)
        if i not in vorhanden_set
    ]


def naechster_offener_monat(
    vorhandene: set[MonatRef],
    start: MonatRef | None,
    heute: MonatRef,
) -> MonatRef | None:
    """
    Frühester offener (fehlender) Monat aus derselben Ableitung wie die
    Tabellen-Färbung — oder ``None``, wenn der Bereich lückenlos ist.
    """
    fehlend = ermittle_fehlende_monate(vorhandene, start, heute)
    return fehlend[0] if fehlend else None


def naechster_offener_monat_fuer(
    vorhandene: set[MonatRef],
    anschaffungsdaten: list[date | None],
    anlage_installationsdatum: date | None,
    heute: date,
) -> MonatRef | None:
    """
    Bequemer Voll-Aufruf: Anker ermitteln → frühesten offenen Monat liefern.
    ``heute`` als ``date`` (nur Jahr/Monat werden genutzt).
    """
    start = ermittle_start_anker(anschaffungsdaten, anlage_installationsdatum, vorhandene)
    return naechster_offener_monat(vorhandene, start, (heute.year, heute.month))
