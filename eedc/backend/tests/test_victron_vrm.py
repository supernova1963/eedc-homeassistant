"""Tests für den Victron VRM Cloud-Import-Provider (#255).

Deckt ab: Provider-Metadaten + Registry-Anbindung, die reine Parsing-Funktion
`_records_to_monthly_data` (inkl. Zeitzonen-Robustheit und ms-/s-Zeitstempel)
sowie die Jahres-Blockung in `fetch_monthly_data`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.cloud_import import get_provider, list_providers
from backend.services.cloud_import.victron_vrm import (
    VictronVRMProvider,
    _records_to_monthly_data,
    _ts_to_year_month,
)


def _month_ts(year: int, month: int, tz_offset_hours: float = 0.0) -> int:
    """Epoch-Sekunden für den Monatsanfang in einer Zeitzone mit Offset."""
    dt = datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(hours=tz_offset_hours)
    return int(dt.timestamp())


# --- Provider-Metadaten + Registry ------------------------------------------

def test_info_metadaten():
    info = VictronVRMProvider().info()
    assert info.id == "victron_vrm"
    assert info.hersteller == "Victron Energy"
    assert info.getestet is False
    feld_ids = {f.id for f in info.credential_fields}
    assert feld_ids == {"access_token", "installation_id"}
    # access_token muss type=password sein — das treibt die Credential-Maskierung.
    token_feld = next(f for f in info.credential_fields if f.id == "access_token")
    assert token_feld.type == "password"


def test_provider_ist_registriert():
    provider = get_provider("victron_vrm")
    assert isinstance(provider, VictronVRMProvider)
    assert "victron_vrm" in {p.id for p in list_providers()}


def test_auth_header_token_schema():
    headers = VictronVRMProvider()._auth_headers("ABC123")
    assert headers == {"X-Authorization": "Token ABC123"}


# --- Zeitstempel-Umrechnung -------------------------------------------------

def test_ts_sekunden_und_millisekunden_gleich():
    sek = _month_ts(2026, 2)
    assert _ts_to_year_month(sek) == (2026, 2)
    assert _ts_to_year_month(sek * 1000) == (2026, 2)  # Millisekunden


def test_ts_zeitzonen_versatz_landet_im_richtigen_monat():
    # VRM-Monatsanfang in UTC+1: "Feb 1 00:00 lokal" = "Jan 31 23:00 UTC".
    # Ohne 15-Tage-Puffer würde der Wert dem Januar zugeschlagen.
    assert _ts_to_year_month(_month_ts(2026, 2, tz_offset_hours=1)) == (2026, 2)
    # Auch bei UTC-12 darf der Wert nicht in den Folgemonat rutschen.
    assert _ts_to_year_month(_month_ts(2026, 2, tz_offset_hours=-12)) == (2026, 2)


# --- _records_to_monthly_data ----------------------------------------------

def test_records_pv_und_netz_werden_gemappt():
    records = {
        "solar_yield": [[_month_ts(2026, 1), 320.0], [_month_ts(2026, 2), 410.5]],
        "grid_history_from": [[_month_ts(2026, 1), 150.0], [_month_ts(2026, 2), 120.0]],
        "grid_history_to": [[_month_ts(2026, 1), 90.0], [_month_ts(2026, 2), 100.0]],
    }
    result = _records_to_monthly_data(records)
    assert [(m.jahr, m.monat) for m in result] == [(2026, 1), (2026, 2)]
    jan = result[0]
    assert jan.pv_erzeugung_kwh == 320.0
    assert jan.netzbezug_kwh == 150.0
    assert jan.einspeisung_kwh == 90.0
    # Eigenverbrauch = PV − Einspeisung, wenn beides vorhanden.
    assert jan.eigenverbrauch_kwh == 230.0


def test_records_eigenverbrauch_fallback_auf_consumption():
    # Ohne PV/Einspeisung wird der gemeldete Gesamtverbrauch verwendet.
    records = {"consumption": [[_month_ts(2026, 3), 540.0]]}
    result = _records_to_monthly_data(records)
    assert len(result) == 1
    assert result[0].eigenverbrauch_kwh == 540.0


def test_records_batterie_wird_gemappt():
    records = {
        "battery_history_charged": [[_month_ts(2026, 1), 200.0]],
        "battery_history_discharged": [[_month_ts(2026, 1), 185.0]],
    }
    result = _records_to_monthly_data(records)
    assert result[0].batterie_ladung_kwh == 200.0
    assert result[0].batterie_entladung_kwh == 185.0


def test_records_unbekannte_attribute_und_nullwerte_ignoriert():
    records = {
        "irgendwas_unbekanntes": [[_month_ts(2026, 1), 999.0]],
        "solar_yield": [[_month_ts(2026, 1), None], [_month_ts(2026, 2), 410.0]],
    }
    result = _records_to_monthly_data(records)
    # Januar hat nur null + unbekannt → kein Eintrag; Februar zählt.
    assert [(m.jahr, m.monat) for m in result] == [(2026, 2)]
    assert result[0].pv_erzeugung_kwh == 410.0


def test_records_leer():
    assert _records_to_monthly_data({}) == []


# --- fetch_monthly_data: Jahres-Blockung ------------------------------------

async def test_fetch_monthly_data_blockt_pro_kalenderjahr():
    provider = VictronVRMProvider()
    erfasste: list[tuple[datetime, datetime]] = []

    async def spy_block(access_token, site_id, block_start, block_end):
        erfasste.append((block_start, block_end))
        return []

    provider._fetch_stats_block = spy_block

    await provider.fetch_monthly_data(
        {"access_token": "T", "installation_id": "1"},
        start_year=2024, start_month=11,
        end_year=2026, end_month=2,
    )

    # Ein Block je Kalenderjahr, geklemmt auf den angefragten Bereich.
    assert [(s.year, s.month, e.year, e.month) for s, e in erfasste] == [
        (2024, 11, 2025, 1),   # Nov–Dez 2024
        (2025, 1, 2026, 1),    # Jan–Dez 2025
        (2026, 1, 2026, 3),    # Jan–Feb 2026
    ]
