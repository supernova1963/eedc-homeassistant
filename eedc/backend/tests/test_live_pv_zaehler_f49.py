"""F-49 (#388, Mathek): die Live-Kachel liest den PV-Zähler, statt zu integrieren.

Standalone:

    eedc/backend/venv/bin/python -m pytest backend/tests/test_live_pv_zaehler_f49.py -q

**Der Befund.** In `get_tages_kwh` lasen `einspeisung` und `netzbezug` ihren
kumulierten kWh-Zähler (Priorität 1), die PV daneben wurde aus dem
Leistungssensor per Trapezregel integriert — `basis.pv_gesamt` kam in der Datei
**null**-mal vor, obwohl es ein Pflichtfeld der Datenquellen-Fläche ist und der
MQTT-Zwilling (`mqtt_energy_history_service._KEY_TO_CATEGORY`) es mit Vorrang
liest. Beim Melder standen so **10,0 kWh** in der Live-Kachel, während sein
eigener HA-Zähler `sensor.energy_solar_generation_daily` zeitgleich **7,65**
zeigte (+31 %). Seine Datenquellen-Seite (Screenshot in #376) zeigt beides:
`PV-Erzeugung Zählerstand (kWh)` zugeordnet, beide Modulgruppen auf „Keine".

**Die Präzedenz, die der Hilfetext zusagt** — und die hier geprüft wird:

1. Erzeuger-Einzelzähler, sobald **einer** misst („sobald einer gemessen wird,
   zählt für Tag und Stunde nur noch, was je Erzeuger gemessen ist"),
2. sonst der **anlagenweite** PV-Zähler („Über den Anlagen-Zählerstand
   abgedeckt — als Summe der ganzen Anlage, auch für Tag und Stunde"),
3. sonst Trapez über den Leistungssensor (das bisherige Verhalten).

Drei Proben: der Sprengsatz (2), die Gegenprobe (1 gewinnt) und die
Positivkontrolle (3 bleibt unverändert, wenn kein Zähler da ist).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services.live_history_service import get_tages_kwh

PV_ZAEHLER = "sensor.energy_solar_generation"
PV_LEISTUNG = "sensor.power_solar_generation"
MODUL_ZAEHLER = "sensor.string_west_energy"


def _anlage(*, mit_basis_zaehler: bool, mit_modul_zaehler: bool = False):
    """Matheks Aufbau: PV am Anlagen-Zähler, Modulgruppen ohne eigenen Sensor."""
    basis_felder: dict = {}
    if mit_basis_zaehler:
        basis_felder["pv_gesamt"] = {"strategie": "sensor", "sensor_id": PV_ZAEHLER}
    investitionen: dict = {}
    if mit_modul_zaehler:
        investitionen["7"] = {
            "felder": {
                "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": MODUL_ZAEHLER}
            }
        }
    # ⚠ Das Live-Format ist `basis.live`, NICHT `basis_live` — der erste
    # Entwurf dieses Fixtures hatte es falsch, und die Positivkontrolle unten
    # hat es gefangen: ohne `live` war der Trapez-Zweig gar nicht bestückt,
    # die beiden anderen Proben hätten also auch grün gemeldet, wenn es den
    # Fallback nie gegeben hätte (`extract_live_config`, live_sensor_config.py).
    basis_felder["live"] = {"pv_gesamt_w": PV_LEISTUNG}
    return SimpleNamespace(
        id=1,
        sensor_mapping={
            "basis": basis_felder,
            "investitionen": investitionen,
        },
    )


def _history(start: datetime):
    """Zähler steht auf 7,65 kWh Tagesdelta; das Trapez ergäbe grob 10."""
    stunden = [(start + timedelta(hours=h), 0.0) for h in range(13)]
    # Leistungsverlauf, dessen Trapez-Integral deutlich über dem Zähler liegt
    leistung = [
        (start + timedelta(hours=h), w)
        for h, w in [(0, 0), (6, 300), (8, 1200), (9, 2100), (10, 3400),
                     (11, 5200), (12, 5200)]
    ]
    zaehler = [
        (start + timedelta(hours=0), 6840.29),
        (start + timedelta(hours=12), 6847.94),   # Δ = 7,65 kWh
    ]
    modul = [
        (start + timedelta(hours=0), 100.0),
        (start + timedelta(hours=12), 103.2),     # Δ = 3,2 kWh
    ]
    del stunden
    return {PV_LEISTUNG: leistung, PV_ZAEHLER: zaehler, MODUL_ZAEHLER: modul}


def _lauf(anlage, history, units):
    """`get_tages_kwh` ohne DB — `inv_types` wird durchgereicht."""
    import asyncio

    async def _inner():
        with patch(
            "backend.services.live_history_service.get_history_normalized",
            return_value=(history, units),
        ):
            return await get_tages_kwh(
                anlage, db=None, tage_zurueck=0,
                inv_types={"7": "pv-module"},
            )

    return asyncio.run(_inner())


def test_anlagen_zaehler_schlaegt_trapez():
    """Der Sprengsatz: mit Basis-Zähler muss der Zählerwert herauskommen."""
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    units = {PV_ZAEHLER: "kWh", PV_LEISTUNG: "W", MODUL_ZAEHLER: "kWh"}
    result = _lauf(_anlage(mit_basis_zaehler=True), _history(start), units)

    assert result.get("pv") == pytest.approx(7.65, abs=0.1), (
        "F-49: Der anlagenweite PV-Zähler ist zugeordnet und muss die Tages-kWh "
        f"liefern (7,65) — die Trapez-Integration der Leistung ergäbe rund 10. "
        f"War: {result.get('pv')!r}"
    )


def test_erzeuger_zaehler_hat_vorrang_vor_anlagen_zaehler():
    """Gegenprobe: misst ein Erzeuger selbst, gilt seine Zahl — nicht die Summe."""
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    units = {PV_ZAEHLER: "kWh", PV_LEISTUNG: "W", MODUL_ZAEHLER: "kWh"}
    result = _lauf(
        _anlage(mit_basis_zaehler=True, mit_modul_zaehler=True),
        _history(start), units,
    )

    assert result.get("pv") == pytest.approx(3.2, abs=0.1), (
        "Die Präzedenz ist umgekehrt zum Anlagen-Zähler: sobald ein Erzeuger "
        "selbst misst, zählt nur noch das Gemessene (so sagt es der Hilfetext "
        f"auf der Datenquellen-Fläche). War: {result.get('pv')!r}"
    )


def test_ohne_zaehler_bleibt_es_beim_trapez():
    """Positivkontrolle: ohne Zähler ändert sich nichts am bisherigen Weg."""
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    units = {PV_LEISTUNG: "W"}
    hist = _history(start)
    result = _lauf(_anlage(mit_basis_zaehler=False), {PV_LEISTUNG: hist[PV_LEISTUNG]}, units)
    assert result, "Ohne Zuordnung liefert die Funktion ein leeres Dict — dann misst der Test nichts."

    assert result.get("pv") is not None and result["pv"] > 7.65, (
        "Ohne zugeordneten Zähler muss der Trapez-Fallback weiter greifen — "
        "sonst prüft der Test nur sich selbst. "
        f"War: {result.get('pv')!r}"
    )
