"""#395, zweite Runde (OB73-gif) — die Verbrauchsprognose des Tages verlässt eedc.

*„Kannst Du die Prognose des Tagesverbrauchs auch über MQTT ausgeben? Haus und
Gesamtverbrauch."* — Der Sensor trägt die **eine** Zahl, die *Cockpit → Live*
unter „Heute" als *Verbrauchsprognose* zeigt. Das ist der **Gesamt**verbrauch;
eine Haushalts-Prognose gibt es in eedc nicht, und ein Sensor darf keine Zahl
tragen, die nirgends angezeigt wird.

**Was hier gewächtert wird:**

1. **Eine Profilwahl, nicht zwei.** Die Route und der Export holen Werktag/
   Wochenende, Wärmepumpen-Profil und Referenztemperatur aus derselben
   Funktion — sonst stünde neben der Kachel bald ein Sensor mit einer anderen
   Zahl (die Klasse von N-332).
2. **Kein Sensor aus dem Standardprofil.** Ohne individuelles Profil zeigt die
   Anzeige BDEW H0 und sagt es dazu; ein Sensor kann das nicht — also gibt es
   ihn dann nicht.
3. **Jeder Prognose-Schlüssel hat einen Leser in der Route.** Eine Definition
   ohne Wert-Zuweisung wäre ein Sensor, der in HA erscheint und nie einen
   Zustand bekommt.

Schwesterdateien: test_395_export_haelften_grundlast.py (erste Runde derselben
Wunschliste — VM/NM und Grundlast, mit der N-332-Regel, die hier weitergilt),
test_live_wetter_verbrauchsprofil.py (die Formel, deren Summe der Sensor trägt).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.services.ha_sensors_export import PROGNOSE_SENSOREN, SensorCategory
from backend.services.verbrauchsprognose_heute import (
    ProfilWahl,
    summe_verbrauchsprofil_kwh,
    verbrauchsprognose_heute,
    waehle_verbrauchsprofil,
)
from backend.tests import factories

_BACKEND = Path(__file__).resolve().parents[1]
#: Ein Mittwoch — die Profilwahl hängt am Wochentag, die Probe darf nicht auf
#: den Tag ihres Laufs wetten (N-167).
_MITTWOCH = datetime(2026, 6, 17, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))
_SAMSTAG = datetime(2026, 6, 20, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))


def _forecast(temps: list[float]) -> tuple:
    times = [f"2026-06-17T{h:02d}:00" for h in range(24)]
    return ({"hourly": {"time": times, "temperature_2m": temps}}, None, True)


# ── Die Definition ───────────────────────────────────────────────────────────

def test_sensor_ist_definiert_und_kein_zaehler():
    defs = {s.key: s for s in PROGNOSE_SENSOREN}
    s = defs["eedc_verbrauchsprognose_heute_kwh"]
    assert s.unit == "kWh"
    assert s.category == SensorCategory.PROGNOSE
    assert s.state_class == "measurement"
    # F-63: `energy` + `measurement` schließt HA von der Langzeitstatistik aus.
    assert s.device_class is None
    assert "Gesamt" in s.formel


def test_jeder_prognose_schluessel_hat_einen_leser_in_der_route():
    """Wächter: eine Definition ohne Wert-Zuweisung wäre ein Sensor ohne Zustand."""
    quelle = (_BACKEND / "api" / "routes" / "ha_export.py").read_text(encoding="utf-8")
    fehlend = [
        s.key for s in PROGNOSE_SENSOREN
        if not re.search(rf'sensor\.key == "{re.escape(s.key)}"', quelle)
    ]
    assert not fehlend, f"Prognose-Sensoren ohne Leser in ha_export.py: {fehlend}"


# ── Eine Profilwahl ──────────────────────────────────────────────────────────

def test_die_route_baut_die_profilwahl_nicht_selbst_nach():
    """Die Zeichenfolge, an der die Wahl erkennbar ist, steht genau EINMAL im Baum —
    im Dienst. Taucht sie in der Route wieder auf, gibt es zwei Fassungen."""
    treffer = []
    for pfad in (_BACKEND / "api").rglob("*.py"):
        if 'profil_typ = "individuell_werktag"' in pfad.read_text(encoding="utf-8"):
            treffer.append(str(pfad.relative_to(_BACKEND)))
    assert treffer == [], f"Profilwahl ein zweites Mal gebaut in: {treffer}"


@pytest.mark.asyncio
async def test_profilwahl_folgt_dem_wochentag(db):
    anlage = await factories.anlage(db)
    daten = {
        "werktag": {h: 0.5 for h in range(24)}, "tage_werktag": 5, "slots_werktag": 24,
        "wochenende": {h: 0.8 for h in range(24)}, "tage_wochenende": 2, "slots_wochenende": 20,
        "wp_werktag": {h: 0.1 for h in range(24)}, "referenz_temp_c": 12.0,
    }
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc:
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=daten)
        werktag = await waehle_verbrauchsprofil(anlage, db, _MITTWOCH)
        wochenende = await waehle_verbrauchsprofil(anlage, db, _SAMSTAG)

    assert werktag.profil_typ == "individuell_werktag" and werktag.profil_tage == 5
    assert werktag.wp_profil == daten["wp_werktag"] and werktag.referenz_temp_c == 12.0
    assert wochenende.profil_typ == "individuell_wochenende" and wochenende.profil_slots == 20
    # Am Wochenende gibt es kein WP-Wochenend-Profil in den Daten → None, nicht das Werktags-Profil.
    assert wochenende.wp_profil is None


@pytest.mark.asyncio
async def test_ohne_historie_gibt_es_keine_wahl_und_keinen_sensor(db):
    anlage = await factories.anlage(db, latitude=51.0, longitude=11.0)
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=_forecast([15.0] * 24)),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=None)
        wahl = await waehle_verbrauchsprofil(anlage, db, _MITTWOCH)
        ergebnis = await verbrauchsprognose_heute(anlage, db, now=_MITTWOCH)

    assert wahl == ProfilWahl() and not wahl.ist_individuell
    # N-332: das Standardprofil wäre eine Annahme im Gewand einer Messung.
    assert ergebnis is None


# ── Die Zahl ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summe_ist_die_zahl_der_kachel(db):
    """Individuelles Profil 0,5 kW × 24 h = 12,0 kWh — wie die Kachel summiert."""
    anlage = await factories.anlage(db, latitude=51.0, longitude=11.0)
    daten = {"werktag": {h: 0.5 for h in range(24)}, "tage_werktag": 7, "slots_werktag": 24}
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=_forecast([15.0] * 24)),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=daten)
        ergebnis = await verbrauchsprognose_heute(anlage, db, now=_MITTWOCH)

    assert ergebnis is not None
    assert ergebnis.summe_kwh == pytest.approx(12.0)
    assert ergebnis.profil_typ == "individuell_werktag"
    assert ergebnis.profil_tage == 7 and ergebnis.profil_slots == 24


@pytest.mark.asyncio
async def test_waermepumpe_wird_wie_in_der_anzeige_temperaturkorrigiert(db):
    """Der Sensor rechnet mit demselben Forecast wie die Kachel — die WP-Korrektur
    (Heizgradtage) ist Teil der Zahl, nicht ein Unterschied zu ihr."""
    anlage = await factories.anlage(db, latitude=51.0, longitude=11.0)
    daten = {
        "werktag": {h: 1.0 for h in range(24)}, "tage_werktag": 7, "slots_werktag": 24,
        "wp_werktag": {h: 0.5 for h in range(24)}, "referenz_temp_c": 5.0,
    }
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=_forecast([0.0] * 24)),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=daten)
        kalt = await verbrauchsprognose_heute(anlage, db, now=_MITTWOCH)

    # Referenz 5 °C, Forecast 0 °C, Heizgrenze 15: Faktor 15/10 = 1,5 auf den WP-Anteil.
    # Haus 0,5 + WP 0,5 × 1,5 = 1,25 kW × 24 h = 30 kWh — mehr als die 24 kWh des Profils.
    assert kalt is not None
    assert kalt.summe_kwh == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_ohne_forecast_kein_sensor(db):
    """Negativ-Cache-Treffer (Forecast gerade nicht erreichbar): die Anzeige zeigt in
    dieser Lage nichts — der Sensor auch nicht, statt ohne Korrektur zu rechnen."""
    anlage = await factories.anlage(db, latitude=51.0, longitude=11.0)
    daten = {"werktag": {h: 0.5 for h in range(24)}, "tage_werktag": 7, "slots_werktag": 24}
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=None),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=daten)
        assert await verbrauchsprognose_heute(anlage, db, now=_MITTWOCH) is None


def test_summe_rundet_wie_die_kachel():
    assert summe_verbrauchsprofil_kwh([{"verbrauch_kw": 0.333}] * 3) == 1.0
    assert summe_verbrauchsprofil_kwh([{"verbrauch_kw": None}, {"verbrauch_kw": 2.0}]) == 2.0
