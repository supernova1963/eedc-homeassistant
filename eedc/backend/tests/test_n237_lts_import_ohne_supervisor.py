"""N-237 — die Langzeitstatistik hängt an der Verbindung, nicht am Add-on.

Der `ha_statistics`-Router war bis 2026-08-11 im selben ``if
HA_INTEGRATION_AVAILABLE``-Block gemountet wie die echten Supervisor-Routen. Für
einen Container mit Long-Lived-Token existierten seine Endpunkte damit **gar
nicht** — die Anfrage fiel auf den SPA-Fallback (HTTP 200 mit HTML, siehe
`reference_ha_only_features_gate`), und die Oberfläche blendete den
Statistik-Import ohnehin aus. Dabei liest der Dienst darunter per Recorder-DB
**oder** WebSocket und prüft seine Erreichbarkeit an jedem Endpunkt selbst.

Ausgerechnet die Werte, die *Cockpit → Monat* und der Monatsabschluss seit N-156
lesen, waren so nicht **rückwirkend** zu holen.

⚠ Diese Proben laufen ohne Supervisor-Token — das ist der Normalfall im Testlauf
und genau die Konstellation des Melders.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def test_kein_supervisor_token_im_testlauf():
    """Vorbedingung der beiden Proben — sonst prüfen sie den falschen Fall.

    Ohne diese Zeile wäre ein grüner Lauf mit gesetztem `SUPERVISOR_TOKEN`
    aussagelos: dann wäre die Route auch vor dem Fix erreichbar gewesen.
    """
    assert not os.environ.get("SUPERVISOR_TOKEN")


def test_lts_route_ist_ohne_supervisor_gemountet():
    """Der Kern: die Route existiert, statt im SPA-Fallback zu verschwinden.

    Geprüft wird an der Registrierung (nicht am Antwort-Code), weil ein
    HTML-Fallback ebenfalls 200 liefert — genau daran ist der Fall am 21.06.
    schon einmal stundenlang vorbeidiagnostiziert worden.
    """
    pfade = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/ha-statistics/status" in pfade, (
        "LTS-Status-Route fehlt ohne Supervisor — "
        f"vorhandene ha-statistics-Routen: {sorted(p for p in pfade if 'ha-stat' in p)}"
    )


def test_supervisor_routen_bleiben_gesperrt():
    """Gegenprobe: was den Supervisor wirklich braucht, wird NICHT mitgeöffnet.

    Ohne diese Probe wäre „Route ist da" auch dann grün, wenn jemand den ganzen
    Block aufgemacht hätte.
    """
    pfade = {r.path for r in app.routes if hasattr(r, "path")}
    assert not [p for p in pfade if p.startswith("/api/ha-import")]
    assert not [p for p in pfade if p.startswith("/api/sensor-mapping")]


def test_lts_status_antwortet_sachlich_statt_mit_fehler():
    """Ohne erreichbare HA muss die Route ruhig „nein" sagen, nicht 500.

    Eine gemountete Route, die im Standalone in einen Serverfehler läuft, wäre
    schlechter als die alte Sperre.
    """
    with TestClient(app) as client:
        antwort = client.get("/api/ha-statistics/status")

    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    assert "verfuegbar" in daten or "available" in daten, daten


@pytest.mark.asyncio
async def test_settings_trennen_addon_von_verbindung():
    """Zwei Fragen, zwei Felder — der Client hängt sein Gate daran.

    `ha_integration_available` bleibt die Add-on-Frage; `ha_verbunden` ist neu
    und beantwortet „ist irgendeine HA erreichbar?". Fehlt das Feld, fällt der
    Client stillschweigend auf die Add-on-Antwort zurück — und dann wäre der
    Statistik-Import für Token-Nutzer weiterhin unsichtbar.
    """
    from backend.main import get_settings

    daten = await get_settings()

    assert daten["ha_integration_available"] is False
    assert "ha_verbunden" in daten
