"""Daten-Checker — Zeitzone: Abweichung zwischen der Zone des Add-ons und der von Home Assistant (`ZEITZONE_ABWEICHUNG`).
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
)
from backend.services.daten_checker.ziele import ziel_block
from backend.core.zahlenformat import fmt_zahl

logger = logging.getLogger(__name__)


def _lokaler_utc_offset() -> Optional[timedelta]:
    """UTC-Offset der Systemzeit, in der eedc `date.today()` auswertet.

    Eigene Funktion, weil genau das im Test gesetzt werden muss: die Alternative
    wäre, im Test die Prozess-Zeitzone umzuschalten (`time.tzset()`), was den
    gesamten Testlauf beeinflusst. Eine Stelle, ein Vertrag.
    """
    return datetime.now().astimezone().utcoffset()

def _offset_text(offset: timedelta) -> str:
    """`timedelta` → „UTC+2“ / „UTC-3:30“ (halbe Stunden kommen vor)."""
    minuten = int(offset.total_seconds() // 60)
    vz = "+" if minuten >= 0 else "-"
    minuten = abs(minuten)
    return (
        f"UTC{vz}{minuten // 60}"
        if minuten % 60 == 0
        else f"UTC{vz}{minuten // 60}:{minuten % 60:02d}"
    )


class ZeitzoneChecks:
    """Prüfung der Zeitzone gegen Home Assistant."""

    async def _check_zeitzone_ha(self, anlage: Anlage) -> list[CheckErgebnis]:
        """N-161: läuft eedc in derselben Zeitzone wie Home Assistant?

        Verglichen wird der **aktuelle UTC-Offset**, nicht der Zonenname —
        Wien, Zürich und Amsterdam teilen sich Berlins Offset, und ein
        Namensvergleich meldete dort einen Fehler, den es nicht gibt.

        Der Check **schweigt**, wenn keine HA-Verbindung besteht, HA nicht
        antwortet oder seine Zone unbekannt ist: ein Hinweis, den niemand
        auflösen kann, ist genau die P-6-Klasse. Die HA-Verbindung kommt aus
        `resolve_ha_connection` und deckt damit **beide** Modi ab (Supervisor
        und Remote-Token) — die N-156-Falle („liest nur den Supervisor-Token“)
        entsteht hier gar nicht erst.

        **Was er nicht kann:** bereits schief gespeicherte Tageszeilen erkennen
        oder heilen. Er misst den Zustand von jetzt.
        """
        from backend.services.ha_connection import resolve_ha_connection, HA_APP

        kat = CheckKategorie.ZEITZONE_ABWEICHUNG.value
        api_url, token, kind = await resolve_ha_connection(self.db)
        if not api_url or not token:
            return []

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{api_url}/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                ha_zone = (resp.json() or {}).get("time_zone")
        except Exception as e:
            logger.debug(f"Zeitzonen-Check: HA-Konfiguration nicht lesbar: {e}")
            return []

        if not ha_zone:
            return []
        try:
            ha_offset = datetime.now(ZoneInfo(str(ha_zone))).utcoffset()
        except Exception:
            logger.debug(f"Zeitzonen-Check: unbekannte HA-Zeitzone {ha_zone!r}")
            return []

        eigen_offset = _lokaler_utc_offset()
        if ha_offset is None or eigen_offset is None or ha_offset == eigen_offset:
            return []

        stunden = (eigen_offset - ha_offset).total_seconds() / 3600
        betrag = abs(stunden)
        betrag_text = (
            f"{int(betrag)} Stunde" if betrag == 1
            else f"{int(betrag)} Stunden" if betrag == int(betrag)
            else f"{fmt_zahl(betrag, 1)} Stunden"
        )
        richtung = "vor" if stunden > 0 else "hinter"

        if kind == HA_APP:
            weg = (
                "Das Add-on übernimmt die Zeitzone beim Start von Home Assistant. "
                "Starte das Add-on einmal neu, damit es die aktuelle Einstellung "
                "übernimmt."
            )
        else:
            weg = (
                "eedc läuft in einem eigenen Container. Setze dort die "
                f"Umgebungsvariable TZ={ha_zone} (in docker-compose.yml unter "
                "environment) und starte den Container neu."
            )

        return [CheckErgebnis(
            kategorie=kat,
            schwere=CheckSeverity.WARNING.value, code="zeitzone_abweichung",
            meldung=(
                f"eedc und Home Assistant rechnen mit verschiedenen Zeitzonen "
                f"({betrag_text} Unterschied)"
            ),
            details=(
                f"Home Assistant steht auf {ha_zone} ({_offset_text(ha_offset)}), "
                f"eedc läuft {betrag_text} {richtung} dieser Zeit "
                f"({_offset_text(eigen_offset)}). Rund um Mitternacht werden "
                "Stundenwerte dadurch dem falschen Tag zugeordnet. "
                f"{weg} Bereits gespeicherte Tage ändern sich davon nicht — "
                "die lassen sich anschließend in der Reparatur-Werkbank neu "
                "berechnen."
            ),
            ziel=ziel_block("system", "protokolle") if kind == HA_APP else None,
        )]
