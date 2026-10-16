"""GitHub #429 (jedema1805, 16.10.2026) — Daten-Checker «Zählerstände – Rückgang in Home Assistant»: ein Rückgang in den
Spiegel-Zeilen eines Sensors, der nicht mehr die jüngste Quelle seines Kanals ist (Sensortausch), zählt weiter (eedc liest
die Zeilen), aber die Meldung nennt ihn «(Vorgänger-Sensor, zugeordnet bis TT.MM.JJJJ)» und den Weg über die Werkbank
«Werte vor dem Sensorbeginn verwerfen». Fixture wie ``test_n639_checker_ha_rueckgang.py``."""

from __future__ import annotations

from datetime import datetime

from backend.models.kanal import FAMILIE_SPIEGEL
from backend.tests.test_n639_checker_ha_rueckgang import RUECKGANG_STUNDE, T0, _anlage, _kanal, _Pruefer, _reihe, _ts

TAUSCH = datetime(2025, 6, 10, 0)     # neuer Sensor ab 10.06.2025 — der Rückgang (05.06.) liegt beim alten
SATZ = "„Werte vor dem Sensorbeginn verwerfen“ seine Werte vor dem Beginn des neuen Sensors"


async def test_rueckgang_beim_vorgaenger_sensor_wird_gekennzeichnet(db):
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", None, _reihe(rueckgaenge={RUECKGANG_STUNDE: 540.0}), quellen=[
        (_ts(T0) - 3600, FAMILIE_SPIEGEL, "sensor.netz_alt", 0.0),
        (_ts(TAUSCH), FAMILIE_SPIEGEL, "sensor.netz_neu", 0.0),
    ])
    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert ("sensor.netz_alt (Vorgänger-Sensor, zugeordnet bis 10.06.2025) am 05.06.2025: −540,0 kWh (Stunde ab 14:00)"
            in e.details)
    assert SATZ in e.details and "Energieprofil-Pflege" in e.details
    assert e.meldung.startswith("1 Tag(e)")       # kein Filter — die Zeile zählt weiter


async def test_rueckgang_beim_aktuellen_sensor_ohne_kennzeichen(db):
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", None, _reihe(rueckgaenge={RUECKGANG_STUNDE: 540.0}), quellen=[
        (_ts(T0) - 3600, FAMILIE_SPIEGEL, "sensor.netz_alt", 0.0),
        (_ts(datetime(2025, 6, 1)), FAMILIE_SPIEGEL, "sensor.netz_neu", 0.0),
    ])
    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert "sensor.netz_neu am 05.06.2025: −540,0 kWh" in e.details
    assert "Vorgänger-Sensor" not in e.details and SATZ not in e.details
