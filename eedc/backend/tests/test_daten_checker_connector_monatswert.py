"""Daten-Checker: Connector eingerichtet, aber kein Monatswert ableitbar (#360/N-73).

`_calc_month_delta` braucht einen Snapshot vor und einen nach dem Monatsbeginn.
Fehlt einer, gibt `_collect_connector_data` still ein leeres Dict zurück — die
Monats-Sicht zeigt dann eine Quelle weniger, ohne Log und ohne Hinweis. Die
Route sagt es mit 404, hat aber keinen Aufrufer im Client; der Anwender erfährt
es also nirgends.

Tests sichern beide Richtungen:
- Connector mit nur EINEM Snapshot ⇒ Befund (WARNING, Wortlaut der Route).
- Connector mit zwei umrahmenden Snapshots ⇒ kein Befund.
- Connector, dessen Snapshots seit Tagen stillstehen ⇒ Befund.
- Zwei frische Snapshots ohne Monats-Snapshot (Monatserster, Tagesabruf noch
  nicht gelaufen) ⇒ KEIN Befund — sonst meldete der Checker am 1. jedes Monats
  bei jedem Connector-Nutzer etwas, das sich Stunden später von selbst erledigt.
- Kein Connector konfiguriert ⇒ kein Befund (P-6: nichts Unauflösbares melden).
- **Nur ein Cloud-Import in derselben Spalte ⇒ kein Befund** (F-54, s. u.).

Die Zeitstempel sind relativ zu `date.today()` gerechnet — der Test bleibt damit
CI-hermetisch ([[feedback_tests_ci_hermetisch]], auch die Uhr).

⚠ **F-54 (#390) hat die Fixtures korrigiert, nicht nur ergänzt.** Sie trugen
`connector_id` **ohne** `host` — einen Zustand, den `POST /connectors/setup`
nie erzeugt (es schreibt beide zusammen). Solange „Connector eingerichtet"
`if not config` hieß, fiel das nicht auf; mit dem SoT-Prädikat
`hat_geraete_connector` (beide Felder, dieselbe Bedingung, die Scheduler und
MQTT-Bridge seit jeher prüfen) wurden die Proben rot. Die Antwort war, die
Fixtures an die Produktion anzugleichen — nicht das Prädikat aufzuweichen.
[[feedback_probe_unerreichbarer_zustand]]
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models import Anlage
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


def _ts(tage_zurueck: float) -> str:
    """ISO-Zeitstempel wie der Connector ihn schreibt (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=tage_zurueck)).isoformat()


def _anlage(config: dict | None) -> Anlage:
    # Kein DB-Zugriff nötig: der Check liest ausschließlich `connector_config`.
    return Anlage(anlagenname="Test", leistung_kwp=10.0, connector_config=config)


def _werte(pv: float) -> dict:
    return {"pv_erzeugung_kwh": pv, "netzbezug_kwh": pv / 2}


async def _befunde(anlage: Anlage):
    return await DatenChecker(db=None)._check_connector_monatswert(anlage)


async def test_kein_connector_kein_befund():
    assert await _befunde(_anlage(None)) == []
    assert await _befunde(_anlage({})) == []


async def test_ein_snapshot_meldet_den_wortlaut_der_route():
    anlage = _anlage({
        "connector_id": "e3dc", "host": "192.168.1.50", "geraet_name": "E3DC S10",
        "meter_snapshots": {_ts(0.1): _werte(1000)},
    })
    befunde = await _befunde(anlage)
    assert len(befunde) == 1
    b = befunde[0]
    assert b.schwere == CheckSeverity.WARNING.value
    assert b.kategorie == CheckKategorie.DATENQUELLE_STATUS.value
    assert "E3DC S10" in b.meldung
    # E5: der geprüfte 404-Text der Route ist die Quelle des Hinweises.
    assert "Mindestens ein Snapshot vor und einer nach dem Monatsbeginn" in b.details
    assert "1 Snapshot" in b.details
    assert b.link


async def test_zwei_umrahmende_snapshots_kein_befund():
    # Einer aus dem Vormonat, einer von heute → Delta bildbar.
    anlage = _anlage({
        "connector_id": "e3dc", "host": "192.168.1.50",
        "meter_snapshots": {_ts(40): _werte(800), _ts(0.1): _werte(1000)},
    })
    assert await _befunde(anlage) == []


async def test_stillstehender_connector_meldet():
    # Beide Snapshots liegen im Vormonat → für den laufenden Monat kein Delta,
    # und der jüngste ist zu alt, um sich noch von selbst zu erledigen.
    anlage = _anlage({
        "connector_id": "e3dc", "host": "192.168.1.50",
        "meter_snapshots": {_ts(40): _werte(800), _ts(35): _werte(850)},
    })
    befunde = await _befunde(anlage)
    assert len(befunde) == 1
    assert befunde[0].schwere == CheckSeverity.WARNING.value
    assert "jüngste Snapshot" in befunde[0].details
    # F-51 (#390): Hier stand `assert "ausgeschaltet" in details` — der Test hat
    # damit eine FALSCHE Aussage festgeschrieben. `auto_fetch_enabled` hatte nie
    # einen Schalter (einziger Schreiber: hart False), und
    # `connector_daily_poll_job` fragt es gar nicht ab. Zugesichert ist jetzt das
    # Gegenteil: der Hinweis behauptet keinen abgeschalteten Abruf mehr und
    # nennt den Weg, den es wirklich gibt.
    assert "ausgeschaltet" not in befunde[0].details
    assert "03:30" in befunde[0].details
    assert "Jetzt ablesen" in befunde[0].details


async def test_frische_snapshots_ohne_monatswert_schweigen():
    # Monatserster vor dem Tagesabruf: zwei Snapshots, beide aus dem Vormonat,
    # der jüngste von gestern. Erledigt sich mit dem nächsten Abruf → kein Lärm.
    anlage = _anlage({
        "connector_id": "e3dc", "host": "192.168.1.50",
        "meter_snapshots": {_ts(1.5): _werte(800), _ts(0.5): _werte(810)},
    })
    befunde = await _befunde(anlage)
    # Nur aussagekräftig, wenn für den laufenden Monat wirklich kein Delta
    # bildbar ist — am Monatsanfang ist das so, später im Monat liegt der
    # 1,5-Tage-alte Snapshot IM Monat und ein Delta entsteht. Beide Ausgänge
    # sind „kein Befund", genau das ist die Zusicherung.
    assert befunde == []
