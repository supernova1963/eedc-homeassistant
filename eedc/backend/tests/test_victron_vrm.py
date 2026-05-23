"""Tests für den Victron VRM Cloud-Import-Provider (#255).

Deckt ab:
- Provider-Metadaten (Felder, Pflicht/Optional, Registrierung)
- Auth-Header-Konvention (`x-authorization: Token <token>`, klein)
- `_records_to_monthly_data` mit der echten VRM-Energiefluss-Matrix
  (kingcap1-Log 2026-05-22: Gb, Pc, Pb, Bc, Pg, Bg, Gc, kwh)
- Sentinel-Handling (`False`-Serien überspringen, ms/s-Zeitstempel,
  Zeitzonen-Robustheit am Monatsgrenze)
- Discovery-Flow (Auto-Pick einzelne Anlage, explizite ID, Mehrfach-Fehler)
- 24-Monats-Block-Chunking (VRM-API-Limit für interval=months)
- WARNING bei API-Antwort aber 0 verwertbaren Treffern (Mapping-Lücke).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from backend.services.cloud_import import get_provider, list_providers
from backend.services.cloud_import.victron_vrm import (
    BEKANNTE_CODES,
    FELD_AUS_CODES,
    MAX_MONTHS_PER_CALL,
    VictronVRMProvider,
    _advance_months,
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
    by_id = {f.id: f for f in info.credential_fields}
    assert set(by_id) == {"access_token", "installation_id"}
    # access_token: Pflicht + Password (treibt die Credential-Maskierung).
    assert by_id["access_token"].type == "password"
    assert by_id["access_token"].required is True
    # installation_id: optional, wird per Discovery aufgelöst.
    assert by_id["installation_id"].required is False


def test_provider_ist_registriert():
    provider = get_provider("victron_vrm")
    assert isinstance(provider, VictronVRMProvider)
    assert "victron_vrm" in {p.id for p in list_providers()}


def test_auth_header_klein_geschrieben_token_schema():
    # VRM-Doku schreibt `x-authorization` klein. `Bearer` ist zum 2026-06-01
    # deprecated — `Token` ist Pflicht.
    headers = VictronVRMProvider()._auth_headers("ABC123")
    assert headers == {"x-authorization": "Token ABC123"}


# --- VRM-Matrix-Konstanten --------------------------------------------------

def test_alle_matrix_codes_sind_bekannt():
    matrix_codes = {c for codes in FELD_AUS_CODES.values() for c in codes}
    # kingcap1-Verifizierung 2026-05-22: alle 7 Matrix-Zellen + `kwh`.
    assert matrix_codes == {"Pc", "Pg", "Pb", "Gc", "Gb", "Bc", "Bg"}
    assert "kwh" in BEKANNTE_CODES  # Aggregat-Marker bewusst ignoriert.


# --- Zeitstempel-Umrechnung -------------------------------------------------

def test_ts_sekunden_und_millisekunden_gleich():
    sek = _month_ts(2026, 2)
    assert _ts_to_year_month(sek) == (2026, 2)
    assert _ts_to_year_month(sek * 1000) == (2026, 2)


def test_ts_zeitzonen_versatz_landet_im_richtigen_monat():
    # VRM-Monatsanfang in UTC+1 = "Jan 31 23:00 UTC". Ohne 15-Tage-Puffer
    # würde der Wert dem Januar zugeschlagen.
    assert _ts_to_year_month(_month_ts(2026, 2, tz_offset_hours=1)) == (2026, 2)
    assert _ts_to_year_month(_month_ts(2026, 2, tz_offset_hours=-12)) == (2026, 2)


# --- _records_to_monthly_data (Energiefluss-Matrix) -------------------------

def test_records_pv_aus_drei_matrix_zellen_summiert():
    # Pc=200, Pg=80, Pb=50 → pv_erzeugung = 330 kWh.
    records = {
        "Pc": [[_month_ts(2026, 3), 200.0]],
        "Pg": [[_month_ts(2026, 3), 80.0]],
        "Pb": [[_month_ts(2026, 3), 50.0]],
    }
    result, unbekannte = _records_to_monthly_data(records)
    assert len(result) == 1
    assert result[0].pv_erzeugung_kwh == 330.0
    assert result[0].einspeisung_kwh == 80.0  # nur Pg (Bg fehlt)
    assert unbekannte == []


def test_records_netzbezug_einspeisung_batterie_korrekt():
    # Vollbild: alle 7 Matrix-Zellen + `kwh`-Aggregat.
    records = {
        "Pc": [[_month_ts(2026, 1), 150.0]],
        "Pg": [[_month_ts(2026, 1), 80.0]],
        "Pb": [[_month_ts(2026, 1), 60.0]],
        "Gc": [[_month_ts(2026, 1), 100.0]],
        "Gb": [[_month_ts(2026, 1), 20.0]],
        "Bc": [[_month_ts(2026, 1), 55.0]],
        "Bg": [[_month_ts(2026, 1), 10.0]],
        "kwh": [[_month_ts(2026, 1), 999.0]],  # bewusst ignoriert
    }
    result, unbekannte = _records_to_monthly_data(records)
    assert unbekannte == []
    md = result[0]
    assert md.pv_erzeugung_kwh == 290.0           # 150+80+60
    assert md.einspeisung_kwh == 90.0             # 80+10
    assert md.netzbezug_kwh == 120.0              # 100+20
    assert md.batterie_ladung_kwh == 80.0         # 60+20
    assert md.batterie_entladung_kwh == 65.0      # 55+10
    assert md.eigenverbrauch_kwh == 305.0         # 150+55+100


def test_records_false_serie_wird_uebersprungen():
    # VRM liefert False für Attribute ohne Daten im Zeitraum — keine Exception.
    records = {
        "Pc": [[_month_ts(2026, 4), 100.0]],
        "Bc": False,
        "Bg": False,
    }
    result, _ = _records_to_monthly_data(records)
    assert len(result) == 1
    assert result[0].pv_erzeugung_kwh == 100.0
    assert result[0].batterie_entladung_kwh is None


def test_records_unbekannte_keys_werden_gemeldet():
    records = {
        "Pc": [[_month_ts(2026, 5), 120.0]],
        "irgendwas_neues_von_vrm": [[_month_ts(2026, 5), 99.0]],
        "noch_was": [[_month_ts(2026, 5), 88.0]],
    }
    result, unbekannte = _records_to_monthly_data(records)
    assert result and result[0].pv_erzeugung_kwh == 120.0
    assert sorted(unbekannte) == ["irgendwas_neues_von_vrm", "noch_was"]


def test_records_nur_unbekannte_keys_liefert_leeres_ergebnis():
    records = {"foo": [[_month_ts(2026, 5), 99.0]]}
    result, unbekannte = _records_to_monthly_data(records)
    assert result == []
    assert unbekannte == ["foo"]


def test_records_leer():
    assert _records_to_monthly_data({}) == ([], [])


# --- Discovery: _resolve_site ----------------------------------------------

class _AsyncReturning:
    """Mini-Helfer: async-callable, der konstanten Wert zurückgibt."""
    def __init__(self, value):
        self.value = value
    async def __call__(self, *args, **kwargs):
        return self.value


async def test_resolve_site_auto_pick_bei_einer_anlage():
    provider = VictronVRMProvider()
    provider._get_user_id = _AsyncReturning(42)
    provider._list_installations = _AsyncReturning(
        [{"idSite": 100, "name": "Mein Haus"}]
    )
    id_site, name, anlagen = await provider._resolve_site(None, "T", "")
    assert (id_site, name) == (100, "Mein Haus")
    assert len(anlagen) == 1


async def test_resolve_site_explizite_id_match():
    provider = VictronVRMProvider()
    provider._get_user_id = _AsyncReturning(42)
    provider._list_installations = _AsyncReturning([
        {"idSite": 100, "name": "Haus"},
        {"idSite": 200, "name": "Hütte"},
    ])
    id_site, name, _ = await provider._resolve_site(None, "T", "200")
    assert (id_site, name) == (200, "Hütte")


async def test_resolve_site_explizite_id_nicht_im_account():
    provider = VictronVRMProvider()
    provider._get_user_id = _AsyncReturning(42)
    provider._list_installations = _AsyncReturning([
        {"idSite": 100, "name": "Haus"},
    ])
    with pytest.raises(ValueError, match="999"):
        await provider._resolve_site(None, "T", "999")


async def test_resolve_site_mehrere_anlagen_ohne_id_fehler():
    provider = VictronVRMProvider()
    provider._get_user_id = _AsyncReturning(42)
    provider._list_installations = _AsyncReturning([
        {"idSite": 100, "name": "Haus"},
        {"idSite": 200, "name": "Hütte"},
    ])
    with pytest.raises(ValueError, match="2 Anlagen"):
        await provider._resolve_site(None, "T", "")


async def test_resolve_site_token_abgelehnt():
    provider = VictronVRMProvider()
    provider._get_user_id = _AsyncReturning(None)
    with pytest.raises(ValueError, match="Access Token"):
        await provider._resolve_site(None, "T", "")


async def test_resolve_site_keine_anlagen_im_account():
    provider = VictronVRMProvider()
    provider._get_user_id = _AsyncReturning(42)
    provider._list_installations = _AsyncReturning([])
    with pytest.raises(ValueError, match="Keine Anlagen"):
        await provider._resolve_site(None, "T", "")


# --- fetch_monthly_data: 24-Monats-Blockung + Empty-Warning -----------------

async def test_fetch_monthly_data_chunkt_in_24_monatsfenstern():
    provider = VictronVRMProvider()
    provider._resolve_site = _AsyncReturning((183075, "Test", [{"idSite": 183075}]))

    erfasste: list[tuple[datetime, datetime]] = []

    async def spy_block(client, access_token, id_site, block_start, block_end):
        erfasste.append((block_start, block_end))
        return [], [], []

    provider._fetch_stats_block = spy_block

    # 36 Monate (2024-01 bis 2026-12) → 2 Blöcke à max. 24 + 12 Monate.
    await provider.fetch_monthly_data(
        {"access_token": "T"},
        start_year=2024, start_month=1,
        end_year=2026, end_month=12,
    )

    assert [(s.year, s.month, e.year, e.month) for s, e in erfasste] == [
        (2024, 1, 2026, 1),
        (2026, 1, 2027, 1),
    ]


async def test_fetch_monthly_data_kurzer_zeitraum_ein_call():
    # Typischer Anwender mit <24 Monaten → genau ein Call.
    provider = VictronVRMProvider()
    provider._resolve_site = _AsyncReturning((1, "Test", [{"idSite": 1}]))
    calls = []

    async def spy_block(client, access_token, id_site, block_start, block_end):
        calls.append((block_start, block_end))
        return [], [], []

    provider._fetch_stats_block = spy_block
    await provider.fetch_monthly_data(
        {"access_token": "T"}, 2026, 1, 2026, 2,
    )
    assert len(calls) == 1


async def test_fetch_monthly_data_warnt_bei_unbekannten_keys(caplog):
    provider = VictronVRMProvider()
    provider._resolve_site = _AsyncReturning((1, "Test", [{"idSite": 1}]))

    async def fake_block(client, access_token, id_site, block_start, block_end):
        # API antwortet, aber Keys sind keine bekannte VRM-Matrix.
        return [], ["weird_attr_1", "weird_attr_2"], ["weird_attr_1", "weird_attr_2"]

    provider._fetch_stats_block = fake_block

    with caplog.at_level(logging.WARNING, logger="backend.services.cloud_import.victron_vrm"):
        result = await provider.fetch_monthly_data(
            {"access_token": "T"}, 2026, 1, 2026, 2,
        )
    assert result == []
    diagnose = "\n".join(r.message for r in caplog.records)
    assert "weird_attr_1" in diagnose and "weird_attr_2" in diagnose
    assert "FELD_AUS_CODES" in diagnose


async def test_fetch_monthly_data_keine_warnung_bei_treffern(caplog):
    # Wenn Daten zurückkommen, KEINE Warnung — auch wenn unbekannte Keys dabei sind.
    provider = VictronVRMProvider()
    provider._resolve_site = _AsyncReturning((1, "Test", [{"idSite": 1}]))

    from backend.services.import_parsers.base import ParsedMonthData

    async def fake_block(client, access_token, id_site, block_start, block_end):
        return (
            [ParsedMonthData(jahr=2026, monat=1, pv_erzeugung_kwh=100.0)],
            ["Pc", "weird_attr"],
            ["weird_attr"],
        )

    provider._fetch_stats_block = fake_block

    with caplog.at_level(logging.WARNING, logger="backend.services.cloud_import.victron_vrm"):
        result = await provider.fetch_monthly_data(
            {"access_token": "T"}, 2026, 1, 2026, 1,
        )
    assert len(result) == 1
    assert not any(
        "0 verwertbare Monatswerte" in r.message for r in caplog.records
    )


# --- _advance_months --------------------------------------------------------

def test_advance_months_normal_und_jahreswechsel():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _advance_months(base, 1) == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert _advance_months(base, 11) == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert _advance_months(base, 12) == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert _advance_months(base, 24) == datetime(2028, 1, 1, tzinfo=timezone.utc)


def test_advance_months_jahreswechsel_mit_offset():
    # Juni 2024 + 24 Monate = Juni 2026.
    base = datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert _advance_months(base, MAX_MONTHS_PER_CALL) == datetime(2026, 6, 1, tzinfo=timezone.utc)
