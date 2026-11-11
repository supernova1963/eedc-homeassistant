"""Daten-Checker — Connector: stiller Connector und fehlender Monatswert (letzter Abruf, jüngster Snapshot).
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

from datetime import datetime, timedelta, timezone
from typing import Optional
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
)
from backend.services.daten_checker.ziele import ziel_block


def _letzter_abruf_satz(config: dict) -> str:
    """„, zuletzt am TT.MM.JJJJ" — oder leer, wenn kein Datum vorliegt.

    `last_fetch` setzt der Setup-Pfad und jeder Abruf (`fetch_service`). Ein
    unlesbarer oder fehlender Wert darf den Hinweis nicht kaputtmachen: dann
    bleibt der Satz ohne Datum stehen, statt ein falsches zu nennen.
    """
    roh = config.get("last_fetch")
    if not roh:
        return ""
    try:
        ts = datetime.fromisoformat(str(roh).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return ""
    return f", zuletzt am {ts.strftime('%d.%m.%Y')}"

def _juengster_snapshot(snapshots: dict) -> Optional[datetime]:
    """Zeitstempel des jüngsten Snapshots (naiv, wie `_calc_month_delta`)."""
    neuster: Optional[datetime] = None
    for ts_str in snapshots:
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
        if neuster is None or ts > neuster:
            neuster = ts
    return neuster


class ConnectorChecks:
    """Prüfung eines Connectors, der keinen Monatswert mehr liefert."""

    # Ein Connector, der lange nichts mehr geliefert hat, kann für den laufenden
    # Monat kein Delta bilden — nach diesen Tagen gilt das nicht mehr als
    # „gleich behoben". Kürzer wäre Rauschen: am Monatsersten fehlt der Snapshot
    # IM Monat noch bei jedem aktiven Connector, bis der Tagesabruf gelaufen ist.
    CONNECTOR_STILL_TAGE = 2

    async def _check_connector_monatswert(self, anlage: Anlage) -> list[CheckErgebnis]:
        """#360/N-73: Connector eingerichtet, aber für den laufenden Monat ist
        kein Wert ableitbar — und niemand sagt es.

        Das Connector-Delta ist die Differenz zweier Zähler-Snapshots. Fehlt
        einer davon, liefert `_calc_month_delta` `None`, `_collect_connector_data`
        gibt ein leeres Dict zurück, und die Monats-Sicht zeigt einfach eine
        Quelle weniger — ohne Log, ohne Hinweis, ohne Response-Feld. Die Route
        `GET /connector/monatswerte/…` sagt es zwar mit 404, hat aber keinen
        Aufrufer im Client; der Anwender erfährt es also nirgends.

        Zuständigkeitsgrenze (P4-Konzept §4): die Sicht beantwortet „worauf
        beruht diese Zahl" — hier steht gar keine Zahl, es gibt nichts zu
        beschriften. Der Checker beantwortet „was musst du nachtragen", und dazu
        gibt es einen Weg (Abruf anstoßen bzw. einschalten). Der Wortlaut ist
        der geprüfte 404-Text der Route, nicht neu erfunden (E5).

        Kein Connector konfiguriert ⇒ kein Befund — sonst meldete der Checker
        jedem HA-Nutzer etwas Unauflösbares.

        F-54 (#390): „Kein Connector konfiguriert" hieß hier bis v4.0.22
        `if not config` — und traf damit genau die P-6-Falle, vor der der Satz
        darüber warnt. `Anlage.connector_config` trägt auch die
        Cloud-Import-Quellen; wer nur einen Cloud-Import angelegt hat, bekam
        „Connector „Connector" liefert für MM/JJJJ keinen Wert" für ein Gerät,
        das er nie eingerichtet hat — mitsamt einem Weg („Jetzt ablesen"), der
        bei ihm mit „Unbekannter Connector: None" endete. Gemeldet von gruaGit
        (Discussion #390, 19./20.08., vier Bilder gesehen), an einer
        Wegwerf-Instanz über den echten Schreibpfad reproduziert.
        """
        from datetime import date
        from backend.api.routes.connector import _calc_month_delta
        from backend.services.connectors.fetch_service import hat_geraete_connector

        config = anlage.connector_config
        if not hat_geraete_connector(config):
            return []

        snapshots = config.get("meter_snapshots") or {}
        heute = date.today()
        if _calc_month_delta(snapshots, heute.year, heute.month):
            return []

        # Frisch genug, um sich selbst zu heilen? Dann schweigen. Snapshot-
        # Zeitstempel sind UTC-naiv (Schreibpfad `connector.py`, Lesepfad
        # `_calc_month_delta`) — die Gegenwart muss es hier genauso sein.
        juengster = _juengster_snapshot(snapshots)
        jetzt = datetime.now(timezone.utc).replace(tzinfo=None)
        if (
            len(snapshots) >= 2
            and juengster is not None
            and (jetzt - juengster) < timedelta(days=self.CONNECTOR_STILL_TAGE)
        ):
            return []

        geraet = config.get("geraet_name") or config.get("connector_id") or "Connector"
        if len(snapshots) < 2:
            bestand = (
                f"Gespeichert ist bisher {len(snapshots)} Snapshot"
                f"{'s' if len(snapshots) != 1 else ''}."
            )
        else:
            bestand = (
                "Der jüngste Snapshot ist vom "
                f"{juengster.strftime('%d.%m.%Y') if juengster else 'unbekannten Datum'}."
            )
        # F-51 (#390): Hier stand bis v4.0.22 „Der tägliche Abruf ist
        # ausgeschaltet" — und das war unwahr. Der Satz hing an
        # `auto_fetch_enabled`, das an genau EINER Stelle geschrieben wird
        # (`routes/connector.py`, hart auf False) und keinen Schalter hat;
        # `connector_daily_poll_job` fragt es gar nicht ab und läuft täglich
        # um 03:30 für jede Anlage mit Connector. Der Hinweis behauptete also
        # eine Ursache, die es nicht gibt, und nannte ein Mittel, das es nicht
        # gibt — dieselbe Klasse wie F-27/F-30.
        weg = (
            f"Der tägliche Abruf läuft um 03:30 Uhr{_letzter_abruf_satz(config)}. "
            "Kommt trotzdem kein Snapshot dazu, lies den Zähler im Geräte-Connector "
            "mit „Jetzt ablesen“ von Hand ab; scheitert der Abruf, steht der "
            "Grund dort und im Aktivitätsprotokoll."
        )
        return [CheckErgebnis(
            kategorie=CheckKategorie.DATENQUELLE_STATUS.value,
            schwere=CheckSeverity.WARNING.value, code="connector_monatswert_fehlt",
            meldung=(
                f"Connector „{geraet}“ liefert für "
                f"{heute.month:02d}/{heute.year} keinen Wert"
            ),
            details=(
                f"Nicht genügend Snapshots für {heute.month:02d}/{heute.year}. "
                "Nötig sind zwei verschiedene Snapshots: der erste vor dem "
                "Monat oder im Monat, der zweite im Monat oder danach. "
                f"{bestand} {weg}"
            ),
            ziel=ziel_block("integration", "import-buendel", wizard="connector"),
        )]
