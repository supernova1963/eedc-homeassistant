"""Regressionstest: EcoFlow-History-Blöcke — Fenstergröße UND Überlappung.

Bug-Historie 1 (Dirk-PN 2026-05-22): Beide EcoFlow-Provider zerlegten den
Importzeitraum in Blöcke von exakt 7 Tagen. Die EcoFlow-API verlangt aber
ein Fenster von STRIKT weniger als einer Woche und lehnte ein 7-Tage-Fenster
(z. B. 2026-02-22 00:00:00 → 2026-03-01 00:00:00 = 168 h) ab mit
"API-Fehler: time must be less than one week". Folge: kein einziger Block
ging durch, der Import meldete "Keine Monatsdaten gefunden".

Bug-Historie 2 (Dirk-PN 2026-06-02): Die `…Summary_Week`-API behandelt das
Fenster [beginTime, endTime] TAG-INKLUSIV an beiden Enden. Benachbarte Blöcke
teilten sich ihren Grenztag (`block_start = block_end`) und der letzte Block
reichte bis zum 1. des Folgemonats. Folge: fünf doppelt gezählte Grenztage +
der Folgemonats-Erste leckten in den Monat — Dirks Mai-Import lag ~15–22 %
über den EcoFlow-Webseiten-Werten (PV 979,9 statt 830,85 kWh).

Beide Bugs sitzen in `iter_history_blocks` und gelten für PowerOcean UND
PowerStream (gemeinsamer Helper) — daher hier symmetrisch getestet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.services.cloud_import.ecoflow_powerocean import (
    MAX_BLOCK_DAYS,
    EcoFlowPowerOceanProvider,
    iter_history_blocks,
)
from backend.services.cloud_import.ecoflow_powerstream import (
    EcoFlowPowerStreamProvider,
)


def _covered_dates(blocks: list[tuple[datetime, datetime]]) -> list:
    """Alle (tag-inklusiv) abgedeckten Kalendertage — als Liste, damit eine
    Doppelabdeckung als Duplikat sichtbar bleibt (kein set!)."""
    dates = []
    for begin, end in blocks:
        d = begin.date()
        while d <= end.date():
            dates.append(d)
            d += timedelta(days=1)
    return dates


def test_max_block_days_unter_einer_woche():
    """Die Blockgröße muss kleiner als 7 Tage sein, nicht gleich."""
    assert MAX_BLOCK_DAYS < 7


@pytest.mark.parametrize("year,month", [(2026, 2), (2026, 1), (2025, 12)])
def test_history_bloecke_strikt_unter_einer_woche(year, month):
    """Jeder abgefragte Block ist < 1 Woche.

    (2026, 2) ist Dirks erster gemeldeter Fall: der letzte Block lief früher
    von 2026-02-22 bis 2026-03-01 — genau 7 Tage — und wurde abgelehnt.
    """
    blocks = iter_history_blocks(year, month, now=datetime(2026, 7, 1))
    assert blocks, "kein Block erzeugt"

    eine_woche = timedelta(days=7)
    for begin, end in blocks:
        assert end - begin < eine_woche, (
            f"Block {begin} – {end} ist {end - begin} lang — "
            f"die EcoFlow-API verlangt strikt < 1 Woche"
        )


@pytest.mark.parametrize(
    "year,month,tage_im_monat",
    [(2026, 1, 31), (2026, 2, 28), (2026, 4, 30), (2025, 12, 31)],
)
def test_bloecke_decken_monat_genau_einmal(year, month, tage_im_monat):
    """Kein geteilter Grenztag, kein Leck in den Folgemonat (Dirk-PN 2026-06-02).

    Jeder Tag des Monats muss GENAU EINMAL abgedeckt sein — sonst zählt die
    Block-Summe Energie doppelt (Grenztag) oder schleppt den 1. des
    Folgemonats ein.
    """
    blocks = iter_history_blocks(year, month, now=datetime(2026, 7, 1))
    covered = _covered_dates(blocks)

    erster = datetime(year, month, 1).date()
    erwartet = [erster + timedelta(days=i) for i in range(tage_im_monat)]

    assert covered == erwartet, (
        "Blöcke decken den Monat nicht genau einmal ab — Doppel-Grenztag "
        "oder Folgemonat-Leck (siehe iter_history_blocks)"
    )
    # Explizit: kein Tag doppelt, kein Folgemonats-Tag.
    assert len(covered) == len(set(covered)), "Tag doppelt abgedeckt"


def test_laufender_monat_bis_heute_inklusive_keine_zukunft():
    """Der laufende Monat endet bei „heute" (inkl.), nie in der Zukunft."""
    blocks = iter_history_blocks(2026, 6, now=datetime(2026, 6, 2, 14, 30))
    covered = _covered_dates(blocks)
    assert covered[0] == datetime(2026, 6, 1).date()
    assert covered[-1] == datetime(2026, 6, 2).date()  # heute inkl.
    assert datetime(2026, 6, 3).date() not in covered  # morgen nicht


def test_zukunftsmonat_liefert_keine_bloecke():
    assert iter_history_blocks(2026, 8, now=datetime(2026, 6, 2)) == []


@pytest.mark.parametrize(
    "provider_cls", [EcoFlowPowerOceanProvider, EcoFlowPowerStreamProvider]
)
async def test_blocksumme_zaehlt_keinen_tag_doppelt(provider_cls):
    """End-to-End-Reproduktion von Dirks Mai-Differenz über beide Provider.

    Eine tag-inklusive API wird simuliert: ein Block [begin, end] liefert die
    Summe der Tageswerte aller Tage begin.date()..end.date(). Über die Blöcke
    summiert muss exakt der Monats-Soll herauskommen — mit dem alten,
    überlappenden Zuschnitt käme mehr heraus (Grenztage doppelt + 1. Juni).
    """
    # Reproduzierbare, pro Tag verschiedene Werte; 1. Juni als Folgemonat-Falle.
    per_day = {datetime(2026, 5, d).date(): float(d) for d in range(1, 32)}
    per_day[datetime(2026, 6, 1).date()] = 999.0
    soll = sum(float(d) for d in range(1, 32))  # 496.0

    provider = provider_cls()

    async def spy_block(host, access_key, secret_key, serial_number, begin, end):
        total = 0.0
        d = begin.date()
        while d <= end.date():
            total += per_day.get(d, 0.0)
            d += timedelta(days=1)
        # "Solar Generation" ist in BEIDEN Provider-Mappings auf
        # pv_erzeugung_kwh hinterlegt — daher symmetrie-tauglich.
        return [("Solar Generation", total)]

    # Instanz-Attribut überschreibt die Methode — Aufruf ohne Netzwerk.
    provider._fetch_history_block = spy_block

    month_data, _ = await provider._fetch_single_month(
        "https://example.test", "AK", "SK", "SN", 2026, 5
    )

    assert month_data is not None
    assert month_data.pv_erzeugung_kwh == round(soll, 2), (
        "Block-Summe weicht vom Monats-Soll ab — Grenztag doppelt gezählt "
        "oder 1. Juni eingeschleppt"
    )
