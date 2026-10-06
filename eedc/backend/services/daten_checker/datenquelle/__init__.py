"""
Daten-Checker — Provenance-Konflikte, Datenquelle-Status & -Drift
(`DatenquelleChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).

Seit 18.09.2026 ein Unterpaket (Vorlage 9 des Refactorings grosser Dateien, reiner Umzug): ``quellen`` · ``tage`` · ``speicher`` · ``klima`` · ``connector`` · ``zeitzone`` · ``ruecksprung`` — je Prüf-Familie eine Mixin-Klasse. Diese Fassade trägt ``DatenquelleChecks`` als Verbund weiter; ``DatenChecker`` (``daten_checker/__init__.py``)
komponiert wie bisher. Die Helfer und Konstanten liegen bei ihren Prüfungen (Patch-Ziel der Tests ist das jeweilige Modul).
"""

from .quellen import QuellenChecks
from .tage import TageChecks
from .speicher import SpeicherChecks
from .klima import KlimaChecks
from .connector import ConnectorChecks
from .zeitzone import ZeitzoneChecks
from .ruecksprung import RuecksprungChecks
from .ha_sprung import HaZaehlersprungChecks


class DatenquelleChecks(
    QuellenChecks,
    TageChecks,
    SpeicherChecks,
    KlimaChecks,
    ConnectorChecks,
    ZeitzoneChecks,
    RuecksprungChecks,
    HaZaehlersprungChecks,
):
    """Prüfungen zu Quellen-Konflikten und HA-LTS-Datenquellen-Pfad."""


__all__ = ["DatenquelleChecks"]
