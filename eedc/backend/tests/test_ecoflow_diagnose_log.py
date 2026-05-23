"""Diagnose-Log für EcoFlow-Cloud-Import-Provider.

Hintergrund: Bei `getestet=False`-Providern (PowerOcean, PowerStream) ist die
einzige Brücke zwischen Hersteller-API und unserem INDEX_NAME_MAPPING der
Backend-Log. Wenn die API erfolgreich antwortet, aber kein einziger
gelieferter `indexName` im Mapping vorkommt, hat der Anwender ohne diesen
Log keine Chance zu erkennen, WAS schief läuft — die UI sagt nur „Keine
Monatsdaten gefunden". Dirk-PN 2026-05-22 (#255-Klasse) zeigte das exakt.

Diese Tests sichern:
- `fetch_monthly_data` aggregiert die `indexName`s über alle Monate.
- Sind 0 Treffer im Mapping, aber Namen gesehen → genau EINE WARNING mit
  der Liste der gesehenen + der unbekannten Namen.
- Werden bekannte Namen gemappt → KEINE WARNING (auch wenn unbekannte
  Namen mit dabei sind).
"""

from __future__ import annotations

import logging

import pytest

from backend.services.cloud_import.ecoflow_powerocean import (
    EcoFlowPowerOceanProvider,
)
from backend.services.cloud_import.ecoflow_powerstream import (
    EcoFlowPowerStreamProvider,
)


@pytest.mark.parametrize(
    "provider_cls,modul",
    [
        (EcoFlowPowerOceanProvider, "ecoflow_powerocean"),
        (EcoFlowPowerStreamProvider, "ecoflow_powerstream"),
    ],
)
async def test_warning_bei_unbekannten_indexnames(provider_cls, modul, caplog):
    """API antwortet, aber kein gelieferter indexName ist im Mapping."""
    provider = provider_cls()

    async def fake_block(host, access_key, secret_key, serial_number, begin, end):
        # Realistische Form: was die EcoFlow-API zurückgeben würde — Namen,
        # die wir noch nie gesehen haben.
        return [
            ("Solar Generation Total", 12.3),
            ("Battery in", 4.5),
        ]

    provider._fetch_history_block = fake_block

    logger_name = f"backend.services.cloud_import.{modul}"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        result = await provider.fetch_monthly_data(
            {
                "access_key": "AK", "secret_key": "SK",
                "serial_number": "SN", "region": "eu",
            },
            start_year=2026, start_month=2,
            end_year=2026, end_month=2,
        )

    assert result == []
    warnings = [
        r.message for r in caplog.records
        if r.levelno >= logging.WARNING and r.name == logger_name
    ]
    diagnose = "\n".join(warnings)
    assert "Solar Generation Total" in diagnose
    assert "Battery in" in diagnose
    assert "INDEX_NAME_MAPPING" in diagnose
    assert f"{modul}.py" in diagnose


@pytest.mark.parametrize(
    "provider_cls",
    [EcoFlowPowerOceanProvider, EcoFlowPowerStreamProvider],
)
async def test_keine_warning_wenn_mindestens_ein_name_mappt(provider_cls, caplog):
    """Mischung aus bekannt + unbekannt → Daten kommen durch, keine Warnung."""
    provider = provider_cls()

    async def fake_block(host, access_key, secret_key, serial_number, begin, end):
        # 'Solar Generation' ist im Mapping → liefert PV-Wert; der zweite
        # Name ist unbekannt — soll keine Empty-Warning auslösen.
        return [
            ("Solar Generation", 100.0),
            ("Mystery Field", 7.0),
        ]

    provider._fetch_history_block = fake_block

    with caplog.at_level(logging.WARNING):
        result = await provider.fetch_monthly_data(
            {
                "access_key": "AK", "secret_key": "SK",
                "serial_number": "SN", "region": "eu",
            },
            start_year=2026, start_month=2,
            end_year=2026, end_month=2,
        )

    assert len(result) >= 1
    assert not any(
        "0 verwertbare Monatswerte" in r.message
        for r in caplog.records if r.levelno >= logging.WARNING
    )


@pytest.mark.parametrize(
    "provider_cls",
    [EcoFlowPowerOceanProvider, EcoFlowPowerStreamProvider],
)
async def test_fetch_single_month_liefert_seen_names_tuple(provider_cls):
    """_fetch_single_month gibt (Optional[ParsedMonthData], set[str]) zurück."""
    provider = provider_cls()

    async def fake_block(host, access_key, secret_key, serial_number, begin, end):
        return [("Some Unknown Name", 1.0)]

    provider._fetch_history_block = fake_block
    md, names = await provider._fetch_single_month(
        "https://example.test", "AK", "SK", "SN", 2026, 2,
    )
    # 'Some Unknown Name' mappt nicht → keine ParsedMonthData, aber Namen-Set steht.
    assert md is None
    assert "Some Unknown Name" in names
