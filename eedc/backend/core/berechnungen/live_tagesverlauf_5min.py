"""5-Minuten-Aggregat-Helfer für die Live-Tagesverlauf-Kurve (Berechnungs-Layer, ADR-001).

Reine, DB-freie Umrechnung der `statistics_short_term`-Bausteine in
Leistungs-Punkte für die Butterfly-Kurve. Die DB-Roh-Abfrage (Boundary →
5-Min-kWh-Delta bzw. `mean`) liegt in
`ha_statistics_service.get_short_term_5min_for_day`; **hier** lebt nur die
deterministische Konvertierung — so ist sie ohne HA-DB unit-testbar.

Hintergrund (Live-Tagesverlauf-HA-LTS-Konsistenz, #135-Folge): die Kurve soll
im Add-on-Modus aus derselben SoT-Familie wie die Heute-kWh-Kacheln
(`safe_get_tages_kwh`) kommen. Für einen kWh-Zähler gilt dann exakt
``Σ Kurven-Slot-Energie == Tages-Zähler-Delta``, weil jede 5-Min-Slot-Leistung
aus genau dem Zähler-Delta dieses Intervalls rekonstruiert wird.

Punkte werden am **Slot-Beginn** ``t`` emittiert (Intervall ``[t, t+5min)``).
Das 10-Min-Slot-Raster der Kurve (`h_start <= p < h_end`) fängt damit pro
10-Min-Fenster genau die zwei 5-Min-Punkte ein; deren Mittel ist die korrekte
10-Min-Leistung, und ``Mittel * 10/60 h == ΔkWh₁ + ΔkWh₂``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# 5-Min-Slot. kWh über 5 Min → mittlere Leistung in W:
#   P[W] = ΔkWh / (5/60 h) * 1000 = ΔkWh * 12000.
SLOT_MINUTEN = 5
_KWH_PRO_SLOT_ZU_W = 1000.0 / (SLOT_MINUTEN / 60.0)  # = 12000.0


def counter_deltas_zu_leistung(
    kwh_deltas: dict[datetime, Optional[float]],
) -> list[tuple[datetime, float]]:
    """5-Min-kWh-Deltas eines Zählers → Leistungs-Punkte (W) am Slot-Beginn.

    ``P[W] = ΔkWh * 12000`` (mittlere Leistung über das 5-Min-Intervall).

    Negative oder ``None``-Deltas (Counter-Reset / Recompile-Lücke / fehlende
    Boundary) werden **übersprungen** — der Slot fällt damit auf die
    Nachbar-Mittelung bzw. (wenn die ganze Serie leer bleibt) auf den
    History-Pfad zurück. `sum` ist HAs reset-bereinigte Lifetime-Summe, daher
    sollte ein negatives Delta nur bei Recompile-Artefakten auftreten
    ([[feedback_ha_statistics_aggregation]] — Tagesreset-Falle).
    """
    punkte: list[tuple[datetime, float]] = []
    for t, delta in sorted(kwh_deltas.items()):
        if delta is None or delta < 0:
            continue
        punkte.append((t, delta * _KWH_PRO_SLOT_ZU_W))
    return punkte


def means_zu_leistung(
    means: dict[datetime, Optional[float]],
    faktor_w: float,
) -> list[tuple[datetime, float]]:
    """`statistics_short_term.mean`-Werte eines Power-Sensors → W-Punkte am Slot-Beginn.

    Der Mean steht in der Statistics-Einheit (`unit_of_measurement` aus
    `statistics_meta`, i. d. R. W/kW); der Aufrufer löst den `UNIT_TO_W`-Faktor
    auf (SoT in `live_sensor_config`) und reicht ihn als `faktor_w` herein —
    so bleibt dieser Layer dependency-frei. Unbekannte Einheiten → Faktor 1.0.
    """
    return [(t, v * faktor_w) for t, v in sorted(means.items()) if v is not None]


# ── Grober-Zähler-Fallback (Tagesverlauf-Kurvenform) ─────────────────────
#
# Hintergrund: `counter_deltas_zu_leistung` ist korrekt, SOLANGE der
# Energie-Zähler ≥ alle 5 min meldet — dann ist jeder Slot genau ein
# Zähler-Delta. Meldet der Zähler SELTENER (cloud-gepollte WR, grobe
# kWh-Auflösung), bucht HA den ganzen aufgelaufenen Zuwachs in den EINEN
# 5-Min-Slot, in dem der neue Stand ankommt → Nadel-Spike (ΔkWh über z. B.
# 30 min geteilt durch 5 min ⇒ ~6× überhöht), dazwischen Null. Das Haushalt-
# Residuum spiegelt jede Nadel → der Nutzer sieht „symmetrische Abweichungen"
# und „13 kW vom Dach bei 11 kWp" (Forum mameier1234, #680).
#
# Lösung (mit Maintainer abgestimmt): Energie-Sensor bleibt ÜBERALL primär.
# NUR die Kurven-FORM einer Stunde fällt auf den Live-Leistungssensor zurück,
# wenn der Zähler in dieser Stunde nachweislich zu grob ist (Phantom-Null-Slot:
# Zähler ≈ 0, aber Live > 0). Die Stunden-ENERGIE bleibt = Σ Zähler-Delta
# (telescoping = HA-LTS-Stundenwert) → die Live-Form wird je Stunde darauf
# normiert. Damit kann die (über die Zeit unzuverlässige) Live-Leistung die
# Energie NICHT verfälschen — sie liefert nur die relative Form, deren Σ jede
# Stunde wieder auf den Zähler gepinnt wird. Tages-/Stunden-/LTS-Summen
# bleiben unangetastet (#135-Deckung erhalten).

# „Live = 0"-Schwelle (Sensor-Rauschen) für den Phantom-Null-Vergleich.
LIVE_EPSILON_W = 50.0
# ~0 W: ein Slot gilt als „kein Zähler-Update" unterhalb dieser Leistung.
_NULL_SLOT_W = 1.0
# Ab so vielen verdächtigen Slots/Stunde gilt der Zähler als zu grob.
# Über-Auslösung ist energieseitig harmlos (Σ bleibt gepinnt), Unter-Auslösung
# ließe Nadeln stehen → bewusst sensibel (2 statt z. B. 6).
COARSE_MIN_SUSPECT_SLOTS = 2


def _floor_5min(ts: datetime) -> datetime:
    """Schnappt einen Zeitstempel auf den 5-Min-Slot-Beginn (:00, :05, …)."""
    return ts.replace(minute=(ts.minute // SLOT_MINUTEN) * SLOT_MINUTEN,
                      second=0, microsecond=0)


def kurven_leistung_mit_live_fallback(
    kwh_deltas: dict[datetime, Optional[float]],
    live_punkte_w: Optional[list[tuple[datetime, float]]],
) -> tuple[list[tuple[datetime, float]], list[datetime]]:
    """Zähler-getriebene 5-Min-Leistungspunkte mit stundenweisem Live-Fallback.

    Default-Verhalten = identisch zu ``counter_deltas_zu_leistung``: feine
    Zähler-Stunden liefern unverändert ``ΔkWh × 12000`` je Slot.

    Eine Stunde gilt als „grob" (Zähler-Takt > Slot), wenn sie mindestens
    ``COARSE_MIN_SUSPECT_SLOTS`` verdächtige Slots hat:
      - mit Live-Sensor: Zähler ≈ 0, aber Live > ``LIVE_EPSILON_W``
        (Phantom-Null = „noch nicht gemeldet", kein echtes Produktionsloch);
      - ohne Live-Sensor: Zähler-≈-0-Slot in einer Stunde, die überhaupt
        Produktion hatte (≥ 1 Slot mit Zähler-Update) — reine Lücken-Heuristik.

    Für grobe Stunden wird die **Stunden-Energie** (= Σ Zähler-Delta dieser
    Stunde, exakt) auf die **Live-Form** verteilt (bzw. als Plateau, wenn keine
    Live-Form vorliegt). Vorzeichen bleibt positiv (Betrag) — die Richtung
    kommt wie bei ``counter_deltas_zu_leistung`` nachgelagert aus ``seite`` /
    Netz-Logik.

    Returns:
        ``(punkte, grobe_stunden)`` — Punkte am 5-Min-Slot-Beginn; grobe_stunden
        (Stunden-Beginn) nur für Diagnose/Logging.
    """
    # 1. Zähler-5-Min-Leistung (positiv) je Slot — wie counter_deltas_zu_leistung.
    counter_w: dict[datetime, float] = {}
    for t, delta in kwh_deltas.items():
        if delta is None or delta < 0:
            continue
        counter_w[t] = delta * _KWH_PRO_SLOT_ZU_W

    if not counter_w:
        return [], []

    # 2. Live-Leistung (Betrag) je 5-Min-Slot mitteln.
    live_w_slot: dict[datetime, float] = {}
    if live_punkte_w:
        eimer: dict[datetime, list[float]] = {}
        for ts, w in live_punkte_w:
            eimer.setdefault(_floor_5min(ts), []).append(abs(w))
        live_w_slot = {s: sum(v) / len(v) for s, v in eimer.items()}
    hat_live = bool(live_w_slot)

    # 3. Slots nach Stunde gruppieren.
    stunden: dict[datetime, list[datetime]] = {}
    for t in counter_w:
        stunden.setdefault(t.replace(minute=0, second=0, microsecond=0), []).append(t)

    punkte: list[tuple[datetime, float]] = []
    grobe_stunden: list[datetime] = []

    for h, slots in stunden.items():
        slots.sort()
        null_slots = [s for s in slots if counter_w[s] < _NULL_SLOT_W]
        update_slots = [s for s in slots if counter_w[s] >= _NULL_SLOT_W]

        if hat_live:
            verdaechtig = sum(
                1 for s in null_slots if live_w_slot.get(s, 0.0) > LIVE_EPSILON_W
            )
        else:
            # Ohne Live: Zähler-Lücken in einer Stunde mit Produktion.
            verdaechtig = len(null_slots) if update_slots else 0

        if verdaechtig < COARSE_MIN_SUSPECT_SLOTS:
            # Feine Stunde → unveränderter Zähler-Pfad (kein Regress).
            for s in slots:
                punkte.append((s, counter_w[s]))
            continue

        # Grobe Stunde → Live-Form, Σ auf Zähler-Stundenenergie normiert.
        grobe_stunden.append(h)
        stunden_energie_kwh = sum(counter_w[s] for s in slots) / _KWH_PRO_SLOT_ZU_W
        live_summe = sum(live_w_slot.get(s, 0.0) for s in slots) if hat_live else 0.0

        if live_summe > 0:
            # P[s] = live[s] × Stundenenergie / Live-Stundenenergie.
            faktor = stunden_energie_kwh * _KWH_PRO_SLOT_ZU_W / live_summe
            for s in slots:
                punkte.append((s, live_w_slot.get(s, 0.0) * faktor))
        else:
            # Keine Live-Form → Plateau (gleichmäßig über die vorhandenen Slots).
            plateau_w = stunden_energie_kwh * _KWH_PRO_SLOT_ZU_W / len(slots)
            for s in slots:
                punkte.append((s, plateau_w))

    punkte.sort()
    return punkte, sorted(grobe_stunden)
