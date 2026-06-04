"""
Kanonische Stunden-Slot-Konvention für PV-Prognosequellen (Issue #144, #297).

**Backward-Konvention (#144):**
    Slot ``h`` = Energie im Intervall ``[h-1, h)``.
    Slot 0  = Energie ``[Vortag 23:00, Heute 00:00)``
    Slot 23 = Energie ``[Heute 22:00, Heute 23:00)``

Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber).

Dieses Modul ist die **Single Source of Truth** dafür, wie die verschiedenen
Prognosequellen ihre Roh-Zeitmarker auf Backward-Slots abbilden. Die IST-Seite
(Snapshot-Diffs) lebt bewusst in ``services/snapshot/boundary_range.py``
(``BoundaryRange.for_hourly_slots`` → Slot ``h = snap[h] − snap[h-1]``); beide
müssen dasselbe Slot-Raster liefern (Symmetrie-Test
``tests/test_slot_konvention_quellen.py``).

----------------------------------------------------------------------------
⚠️  OpenMeteo wird NICHT verschoben — und das ist KEIN Bug (Issue #297).
----------------------------------------------------------------------------
OpenMeteos stündliche Strahlungsvariablen (``global_tilted_irradiance``,
``shortwave_radiation``, …) sind in der Default-Form ein **Mittel der
vorangehenden Stunde**: der Wert am Zeitstempel ``T`` deckt das Intervall
``[T-1, T)`` ab (empirisch verifiziert 2026-06-04: bei Sonnenaufgang 04:46
ist der Wert@05:00 = 0 und erst der Wert@06:00 > 0; Trapez-Rekonstruktion
gegen die ``*_instant``-Variante bestätigt das). Damit IST der OpenMeteo-Wert
am Index ``h`` bereits der Backward-Slot ``h`` — ``openmeteo_preceding_hour_slot``
ist deshalb die **Identität**.

Ein naiver „+1-Shift" auf OpenMeteo (wie in #297 zunächst vermutet) würde die
Quelle eine Stunde zu spät einsortieren und genau den Versatz ERZEUGEN, den er
zu beheben vorgibt. Wer hier etwas verschiebt, verletzt den Symmetrie-Test.

Solcast dagegen liefert periodenbeginnende Buckets (HA-Sensor: ``period_start``)
bzw. periodenendende Marker (API: ``period_end``) und MUSS auf das Stunden-Ende
gerundet werden — siehe ``backward_slot_aus_period_start`` /
``backward_slot_aus_period_end``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def openmeteo_preceding_hour_slot(stunde: int) -> int:
    """OpenMeteo preceding-hour-Wert@``stunde`` = Intervall ``[stunde-1, stunde)``.

    Das IST schon der Backward-Slot ``stunde`` → Identität, **kein Shift**.
    Existiert als benannte Funktion, damit der „kein Shift"-Vertrag im Code
    sichtbar und im Symmetrie-Test prüfbar ist (Issue #297).
    """
    return stunde


def backward_slot_aus_period_start(period_start: datetime) -> tuple[date, int]:
    """Backward-Slot für ein **periodenbeginnendes** Bucket ``[period_start, …)``.

    Für Buckets von höchstens einer Stunde Länge (Solcast HA-Sensor: 30-Min)
    liegt das Intervall-Ende in der nächsten vollen Stunde → Slot =
    ``floor(period_start) + 1h``.

      ``period_start = N:00`` → Bucket ``[N:00, N:30)`` → Slot ``N+1``
      ``period_start = N:30`` → Bucket ``[N:30, N+1:00)`` → Slot ``N+1``

    Am Tagesübergang (``period_start = 23:xx``) wandert der Slot korrekt in
    Slot 0 des Folgetags — ``slot_date`` nimmt das mit.
    """
    marker = period_start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return marker.date(), marker.hour


def backward_slot_aus_period_end(period_end: datetime) -> tuple[date, int]:
    """Backward-Slot für einen **periodenendenden** Marker (Solcast API).

      ``period_end = N:00`` → Bucket ``[…, N:00)``   → Slot ``N``
      ``period_end = N:30`` → Bucket ``[…, N:30)``   → Slot ``N+1`` (aufgerundet)

    Ein Marker exakt auf der vollen Stunde markiert das Ende des Slots dieser
    Stunde; alles dazwischen rundet auf die nächste volle Stunde auf.
    """
    if period_end.minute == 0 and period_end.second == 0 and period_end.microsecond == 0:
        marker = period_end
    else:
        marker = period_end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return marker.date(), marker.hour
