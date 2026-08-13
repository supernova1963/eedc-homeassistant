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

„Erwarteter Bereich" = [Anlagen-Anker … letzter vergangener Monat]:
- Start = Anlage-Installationsdatum, Fallback ältestes Anschaffungsdatum der
  **Erzeuger**, dann früheste vorhandene Datenzeile (seit 2026-08-13, s.
  :func:`ermittle_start_anker`). Die Monatszeile ist eine Aussage über die
  Anlage — welche Investition in welchem Monat *zählt*, entscheidet weiterhin
  ``ist_aktiv_im_zeitraum`` ([[feedback_anschaffungsdatum_grenze]]).
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
    anlage_installationsdatum: date | None,
    erzeuger_anschaffungsdaten: list[date | None],
    vorhandene: set[MonatRef],
) -> MonatRef | None:
    """
    Bereichs-Start für die **Basisdaten** (Anlagenzeile: Einspeisung/Netzbezug).
    Reihenfolge: Anlage-Installationsdatum → ältestes Anschaffungsdatum der
    **Erzeuger** → früheste vorhandene Datenzeile. ``None``, wenn keine Quelle
    greift.

    **Die Reihenfolge stand bis 2026-08-13 andersherum**, und der Anker nahm das
    früheste Anschaffungsdatum **aller** Investitionen. Eine Monatszeile ist aber
    eine Aussage über die *Anlage*, nicht über ein Gerät: Ein E-Auto von 2017
    begründet keine Einspeisungszeile von 2017. Genau das ist zweimal passiert —
    fridolin22 (Forum T77723 #773) sah Basisdaten ab 2017 gefordert und hat sein
    Auto auf 2026 umdatiert, um die Forderung loszuwerden; damit war die echte
    Anschaffungshistorie des Fahrzeugs verloren. van (PN, 13.08.) traf dieselbe
    Klasse mit „Nächster offener: Sep 2016".

    ⚠ **Das ist KEINE Lockerung der Anschaffungsdatum-Grenze**
    ([[feedback_anschaffungsdatum_grenze]]). Welche Investition in welchem Monat
    *zählt*, entscheidet unverändert ``Investition.ist_aktiv_im_zeitraum``
    (``aktiv`` · ``anschaffungsdatum`` · ``stilllegungsdatum``) — hier geht es
    allein um den **Erwartungsrahmen**: welcher Monat überhaupt abgefragt wird.

    ``erzeuger_anschaffungsdaten`` filtert der **Aufrufer** (Typen in
    ``PV_ERZEUGER_TYPEN``); dieses Modul bleibt rein und modellfrei, damit es
    identisch gegen die Frontend-Ableitung testbar bleibt.
    """
    if anlage_installationsdatum is not None:
        return (anlage_installationsdatum.year, anlage_installationsdatum.month)
    daten = [d for d in erzeuger_anschaffungsdaten if d is not None]
    if daten:
        fruehestes = min(daten)
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
    erzeuger_anschaffungsdaten: list[date | None],
    anlage_installationsdatum: date | None,
    heute: date,
) -> MonatRef | None:
    """
    Bequemer Voll-Aufruf: Anker ermitteln → frühesten offenen Monat liefern.
    ``heute`` als ``date`` (nur Jahr/Monat werden genutzt).

    ``erzeuger_anschaffungsdaten`` filtert der Aufrufer auf ``PV_ERZEUGER_TYPEN``.
    """
    start = ermittle_start_anker(anlage_installationsdatum, erzeuger_anschaffungsdaten, vorhandene)
    return naechster_offener_monat(vorhandene, start, (heute.year, heute.month))
