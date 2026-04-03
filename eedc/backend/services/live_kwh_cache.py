"""
Live kWh Cache - TTL-Caches für Heute/Gestern-kWh und Verbrauchsprofil.

Ausgelagert aus live_power_service.py (Schritt 2 des Refactorings).
Fix: Class-Attribute → Instance-Attribute (bei Singleton kein funktionaler Unterschied,
     aber sauberer und testbar).
"""

from datetime import datetime
from typing import Optional


class LiveKwhCache:
    """Verwaltet TTL-Caches für Live-kWh-Daten pro Anlage."""

    HEUTE_CACHE_TTL = 60  # Sekunden

    # Sentinel: unterscheidet "nicht gecacht" (None) von "gecacht als keine Daten"
    PROFIL_UNAVAILABLE: object = object()

    def __init__(self):
        self._heute: dict[int, tuple[float, dict]] = {}
        self._gestern: dict[int, tuple[str, dict]] = {}
        self._profil: dict[int, tuple[str, object]] = {}

    # ── Heute-kWh (60s TTL — vermeidet HA-History-Flood) ─────────

    def get_heute(self, anlage_id: int) -> Optional[dict]:
        """Gibt gecachte Heute-kWh zurück wenn jünger als 60s."""
        if anlage_id not in self._heute:
            return None
        ts, kwh = self._heute[anlage_id]
        if (datetime.now().timestamp() - ts) < self.HEUTE_CACHE_TTL:
            return kwh
        return None

    def set_heute(self, anlage_id: int, kwh: dict) -> None:
        """Speichert Heute-kWh mit aktuellem Timestamp."""
        self._heute[anlage_id] = (datetime.now().timestamp(), kwh)

    # ── Gestern-kWh (ändert sich nicht mehr nach Mitternacht) ────

    def get_gestern(self, anlage_id: int) -> Optional[dict]:
        """Gibt gecachte Gestern-kWh zurück wenn noch derselbe Tag."""
        if anlage_id not in self._gestern:
            return None
        datum, kwh = self._gestern[anlage_id]
        if datum == datetime.now().strftime("%Y-%m-%d"):
            return kwh
        return None

    def set_gestern(self, anlage_id: int, kwh: dict) -> None:
        """Speichert Gestern-kWh mit heutigem Datum als Cache-Key."""
        self._gestern[anlage_id] = (datetime.now().strftime("%Y-%m-%d"), kwh)

    # ── Profil-Cache (1x täglich) ────────────────────────────────

    def get_profil(self, anlage_id: int):
        """
        Gibt gecachten Wert zurück wenn er von heute ist.
        Returns:
            None: nicht gecacht (Berechnung notwendig)
            PROFIL_UNAVAILABLE: gecacht als "kein Profil verfügbar"
            dict: gecachtes Profil
        """
        if anlage_id not in self._profil:
            return None
        datum, profil = self._profil[anlage_id]
        if datum == datetime.now().strftime("%Y-%m-%d"):
            return profil
        return None

    def set_profil(self, anlage_id: int, profil: Optional[dict]) -> None:
        """Speichert Profil mit heutigem Datum. None wird als Sentinel gespeichert."""
        value = self.PROFIL_UNAVAILABLE if profil is None else profil
        self._profil[anlage_id] = (datetime.now().strftime("%Y-%m-%d"), value)
