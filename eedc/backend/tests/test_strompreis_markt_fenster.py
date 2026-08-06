"""Börsenpreise: ein Tag ist der Tag der Marktzone, nicht der UTC-Tag (F-6).

`fetch_marktpreise` bildete das Abfragefenster in UTC, ordnete die Antwort aber
über die **lokale** Uhr zu. In Mitteleuropa fehlten dadurch die Stunden 0 und 1
des angefragten Tages (im Winter die Stunde 0); an ihrer Stelle standen die
Preise des **Folgetages**. Das Ergebnis hatte 24 Einträge und sah vollständig
aus. Betroffen war alles, was auf dieser Reihe steht: die HA-Export-Sensoren
(Rang, Günstig-Zählung, aktueller Preis, Abstand zum Ø), das Preis-Overlay im
Live-Tagesverlauf und die persistierte Spalte `TagesEnergieProfil.boersenpreis_cent`.

⚠ **Woher die Antwortform stammt** ([[feedback_fixture_fremde_api_braucht_quelle]],
Lehre aus F-4/#349): Sie ist am 2026-08-06 gegen die echte Schnittstelle
gemessen — `GET https://api.awattar.de/v1/marketdata?start=…&end=…` antwortet
mit den Feldern der obersten Ebene `object` · `data` · `url` und je Slot
`start_timestamp` · `end_timestamp` · `marketprice` (EUR/MWh) · `unit`. Der
Mock unten ist deshalb **kein festes 24-Stunden-dict**, sondern beantwortet das
tatsächlich gesendete Fenster wie der echte Server: Er liefert genau die Slots,
die in `[start, end)` liegen. Nur so schlägt eine falsche Fensterbildung im
Test überhaupt durch — ein dict-Mock hätte den Fehler nie gezeigt, und genau
daran sind die Bestandstests vorbeigelaufen (`test_ha_export_preis_150.py`
liefert `{h: … for h in range(24)}`).

**Hermetik** ([[feedback_tests_ci_hermetisch]] — „auch die Uhr"): Eine Probe
stellt die **Prozess**-Zeitzone um. Das Ergebnis darf sich dadurch nicht
ändern; vor F-6 tat es das (die Schlüssel waren dann UTC-Stunden).
"""

from __future__ import annotations

import os
import time as _time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend.services import strompreis_markt_service as smp

BERLIN = ZoneInfo("Europe/Berlin")


# ── Mock: antwortet auf das gesendete Fenster wie der echte Server ──────────

def _preis_eur_mwh(dt_berlin: datetime) -> float:
    """Eindeutiger Preis je Slot: Tag im Hunderter, Stunde in der Einerstelle.

    06.08. 00:00 → 600.0 EUR/MWh → 60.0 ct/kWh
    07.08. 00:00 → 700.0 EUR/MWh → 70.0 ct/kWh

    Damit sagt jeder Wert im Ergebnis, aus welchem **Tag** und welcher **Stunde**
    er stammt — ein vom Folgetag eingeschleppter Preis ist sofort sichtbar.
    """
    return float(dt_berlin.day * 100 + dt_berlin.hour)


def erwartet_ct(tag: int, stunde: int) -> float:
    """Der ct/kWh-Wert, den `_preis_eur_mwh` für (Tag, Stunde) erzeugt."""
    return round((tag * 100 + stunde) / 10, 2)


@pytest.fixture(autouse=True)
def _cache_leeren():
    """Der Modul-Cache ist global — sonst verkleben die Proben einander."""
    smp._cache.clear()
    smp._error_cache.clear()
    yield
    smp._cache.clear()
    smp._error_cache.clear()


@pytest.fixture
def awattar(monkeypatch):
    """aWATTar-Doppel: liefert alle Stundenslots im angefragten Fenster.

    Merkt sich zusätzlich die gesendeten `start`/`end`-Parameter, damit eine
    Probe das Fenster selbst prüfen kann.
    """
    gesendet: dict[str, datetime] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        start_ms = int(request.url.params["start"])
        end_ms = int(request.url.params["end"])
        gesendet["start"] = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        gesendet["end"] = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)

        slots = []
        t = gesendet["start"]
        while t < gesendet["end"]:
            lokal = t.astimezone(BERLIN)
            slots.append({
                "start_timestamp": int(t.timestamp() * 1000),
                "end_timestamp": int((t + timedelta(hours=1)).timestamp() * 1000),
                "marketprice": _preis_eur_mwh(lokal),
                "unit": "Eur/MWh",
            })
            t += timedelta(hours=1)
        return httpx.Response(200, json={"object": "list", "data": slots, "url": "/de/v1/marketdata"})

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(smp.httpx, "AsyncClient", _Client)
    return gesendet


# ── Proben ──────────────────────────────────────────────────────────────────

async def test_fenster_laeuft_von_lokaler_mitternacht_bis_lokaler_mitternacht(awattar):
    """Der angefragte Zeitraum ist der Tag der Marktzone, nicht der UTC-Tag."""
    await smp.fetch_marktpreise(date(2026, 8, 6), markt="DE")

    assert awattar["start"].astimezone(BERLIN) == datetime(2026, 8, 6, 0, 0, tzinfo=BERLIN)
    assert awattar["end"].astimezone(BERLIN) == datetime(2026, 8, 7, 0, 0, tzinfo=BERLIN)


async def test_stunde_null_traegt_den_preis_dieses_tages(awattar):
    """Die Nachtstunden gehören dem angefragten Tag — nicht dem Folgetag.

    Der Kern von F-6: vorher standen auf 0 und 1 die Preise des 07.08.
    """
    preise = await smp.fetch_marktpreise(date(2026, 8, 6), markt="DE")

    assert preise[0] == erwartet_ct(6, 0)
    assert preise[1] == erwartet_ct(6, 1)
    # Und kein einziger Wert stammt aus einem anderen Tag.
    assert all(p == erwartet_ct(6, h) for h, p in preise.items())
    assert sorted(preise) == list(range(24))


async def test_prozesszone_aendert_das_ergebnis_nicht(awattar):
    """Ein Container ohne `TZ` (Docker-Default UTC) bekommt dieselben Schlüssel.

    Vorher trug der Schlüssel dort die UTC-Stunde — der HA-Export hielt ihn
    gegen die Berliner Stunde und lag zwei Stunden daneben.
    """
    alt = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "UTC"
        _time.tzset()
        preise = await smp.fetch_marktpreise(date(2026, 8, 6), markt="DE")
    finally:
        if alt is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = alt
        _time.tzset()

    assert preise[0] == erwartet_ct(6, 0)
    assert preise[12] == erwartet_ct(6, 12)


async def test_zeitumstellung_fruehjahr_hat_23_stunden(awattar):
    """Am 29.03.2026 fehlt die Stunde 2 — 23 Einträge sind hier richtig."""
    preise = await smp.fetch_marktpreise(date(2026, 3, 29), markt="DE")

    assert 2 not in preise
    assert len(preise) == 23
    assert preise[1] == erwartet_ct(29, 1)
    assert preise[3] == erwartet_ct(29, 3)


async def test_zeitumstellung_herbst_behaelt_die_erste_stunde_zwei(awattar):
    """Am 25.10.2026 gibt es die Stunde 2 zweimal; die erste gewinnt.

    Ein `dict[int, float]` kann die doppelte Stunde nicht abbilden. Die Wahl
    ist getroffen und benannt, statt sie dem Zufall der Iterationsreihenfolge
    zu überlassen — vorher überschrieb die zweite die erste still.
    """
    preise = await smp.fetch_marktpreise(date(2026, 10, 25), markt="DE")

    assert len(preise) == 24
    # Beide realen Stunden tragen denselben erzeugten Preis (Tag 25, Stunde 2),
    # entscheidend ist, dass der Tag nicht überläuft und 23 vorhanden bleibt.
    assert preise[2] == erwartet_ct(25, 2)
    assert preise[23] == erwartet_ct(25, 23)
    assert all(h in preise for h in range(24))


async def test_at_nutzt_die_oesterreichische_marktzone(awattar):
    """AT bekommt Europe/Vienna — gleicher Offset, aber nicht geerbt."""
    preise = await smp.fetch_marktpreise(date(2026, 8, 6), markt="AT")

    assert awattar["start"].astimezone(BERLIN) == datetime(2026, 8, 6, 0, 0, tzinfo=BERLIN)
    assert preise[0] == erwartet_ct(6, 0)
    assert smp._markt_tz("AT") == ZoneInfo("Europe/Vienna")


# ── Die zweite Hälfte von F-6: der HA-Export fragte den falschen Tag ab ─────
#
# `berechne_preis_export` nahm den **Tag** aus der Prozesszone (`date.today()`)
# und die **Stunde** hart aus Europe/Berlin. Auf einem UTC-Container fallen die
# beiden zwischen 00:00 und 02:00 Ortszeit auseinander: eedc fragte die Preise
# von gestern ab und suchte darin die Stunde 0 von heute.

async def test_export_fragt_den_tag_der_marktzone_ab(monkeypatch):
    """00:30 Berlin auf einem UTC-Container: abgefragt wird der Berliner Tag.

    Uhr **und** Prozesszone werden gestellt — sonst prüft die Probe nur, ob sie
    zufällig zwischen 00:00 und 02:00 läuft, und wäre 22 von 24 Stunden grün.

    ⚠ **Gestellt wird die Uhr seit #335 in `preis_tag`**, nicht mehr in
    `ha_export_preis`: Beschaffung und Bewertung eines Preistages liegen dort,
    seit der Live-Preis-Chart dieselbe Quelle nutzt. Geprüft wird weiterhin der
    **Export**-Pfad von außen — die Zuständigkeit ist gewandert, die Zusicherung
    nicht.
    """
    from backend.models.anlage import Anlage
    from backend.services import ha_export_preis as hep
    from backend.services import preis_tag as pt

    jetzt_utc = datetime(2026, 8, 6, 22, 30, tzinfo=timezone.utc)  # = 07.08. 00:30 Berlin

    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt_utc.astimezone(tz) if tz else jetzt_utc.replace(tzinfo=None)

    class _Kalender(date):
        @classmethod
        def today(cls):
            # Was `date.today()` auf einem UTC-Container liefert: noch der 06.
            return date(2026, 8, 6)

    gefragt: list[date] = []

    async def _fake_fetch(datum, markt="DE", timeout=15.0):
        gefragt.append(datum)
        return {h: 10.0 + h for h in range(24)}

    monkeypatch.setattr(pt, "datetime", _Uhr)
    monkeypatch.setattr(pt, "date", _Kalender)
    monkeypatch.setattr(smp, "fetch_marktpreise", _fake_fetch)

    anlage = Anlage(anlagenname="TZ-Test", leistung_kwp=10.0,
                    latitude=48.8, longitude=9.2, standort_land="DE")
    # `db` wird auf diesem Weg nicht berührt — es gibt Preise, der
    # DB-Fallback `persistierte_preise` ist unerreichbar. Wäre er es doch,
    # scheiterte die Probe laut statt still grün zu bleiben.
    ergebnis = await hep.berechne_preis_export(None, anlage)

    assert gefragt == [date(2026, 8, 7)], "der Berliner Tag, nicht der UTC-Tag"
    # Und die bewertete Stunde ist die Berliner Stunde 0 desselben Tages.
    assert ergebnis is not None
    assert ergebnis["preis_aktuell_cent"] == 10.0
