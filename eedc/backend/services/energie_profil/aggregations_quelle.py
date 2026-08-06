"""Kann der Tages-Lauf für einen Tag überhaupt etwas holen? — eine Antwort, ein Ort.

``aggregate_day`` braucht **entweder** eine Leistungs-Zuordnung (``sensor_mapping``
``basis.live`` bzw. ``investitionen[*].live``) **oder** MQTT-Energie-Snapshots.
Fehlt beides, steigt der Lauf aus und schreibt nichts — bei HTTP 200 und ohne
Fehler. Genau diese Bedingung muss auch jede Stelle kennen, die dem Anwender
eine Reparatur **anbietet**: ein Knopf, der garantiert nichts holen kann, ist
schlimmer als keiner (P-8, #368).

Bis v4.0.9 lag die Prüfung **zweimal** im Baum — im Aggregator selbst und im
Daten-Checker (``daten_checker.datenquelle``), dort mit dem Kommentar
„dieselbe Bedingung wie im Aggregator, nicht eine zweite". Sie *war* aber eine
zweite: eine wortgleiche Kopie. Mit der Tagesbegründung von Cockpit/Tag wäre
sie die dritte geworden — die Klasse, die diesen Baum schon mehrfach gekostet
hat ([[feedback_aggregations_drift]]). Deshalb hier, mit drei Aufrufern.

Bewusst **kein** Berechnungs-Layer (ADR-001): das ist keine Aggregat-Formel,
sondern eine Vorbedingung mit DB-Zugriff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage


@dataclass(frozen=True)
class AggregationsQuelle:
    """Woraus könnte der Tages-Lauf für den geprüften Tag schöpfen?

    ``live_sensoren`` — eine Leistungs-Zuordnung steht (Basis oder Investition).
    ``mqtt_energie``  — MQTT-Energie-Snapshots liegen im Fenster ab dem Vortag.
    """

    live_sensoren: bool
    mqtt_energie: bool

    @property
    def vorhanden(self) -> bool:
        """Kann der Lauf überhaupt etwas holen?"""
        return self.live_sensoren or self.mqtt_energie


async def ermittle_aggregations_quelle(
    db: AsyncSession,
    anlage: Anlage,
    ab_datum: date,
) -> AggregationsQuelle:
    """Prüft die Vorbedingung von ``aggregate_day`` für ``ab_datum``.

    Die MQTT-Abfrage läuft **nur**, wenn keine Leistungs-Zuordnung steht — so
    kostet der Normalfall (HA-Add-on mit Mapping) keine zusätzliche Query.
    Das Snapshot-Fenster beginnt einen Tag **vor** ``ab_datum``, weil der
    Zähler-Pfad den Anfangsstand des Vortags braucht.
    """
    sensor_mapping = anlage.sensor_mapping or {}

    basis_live = (sensor_mapping.get("basis") or {}).get("live") or {}
    inv_live = any(
        isinstance(v, dict) and v.get("live")
        for v in (sensor_mapping.get("investitionen") or {}).values()
    )
    if basis_live or inv_live:
        return AggregationsQuelle(live_sensoren=True, mqtt_energie=False)

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    cutoff = datetime.combine(ab_datum, datetime.min.time()) - timedelta(days=1)
    treffer = await db.execute(
        select(MqttEnergySnapshot.id).where(
            MqttEnergySnapshot.anlage_id == anlage.id,
            MqttEnergySnapshot.timestamp >= cutoff,
        ).limit(1)
    )
    return AggregationsQuelle(
        live_sensoren=False,
        mqtt_energie=treffer.scalar_one_or_none() is not None,
    )
