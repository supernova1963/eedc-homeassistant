"""Der Kraftstoffpreis-Nachlauf: Takt, Startlauf und der Ausstieg vor dem Download.

**Auslöser: Discussion #394 (gruaGit, 2026-08-23).** Ihm wurde geantwortet,
eedc trage jeden Monat ohne Preis von selbst nach — er sah nach und fand für
Juni 2026 ein leeres Feld im Monatsabschluss unter *Vergleichspreise*.
Gemessen war die Automatik da, aber:

1. Sie lief **wöchentlich** (`day_of_week="tue"`) — als einziger Wochen-Takt
   unter sechzehn Jobs. Eine Monatszeile, die zwischen zwei Dienstagen
   entsteht (Monatsabschluss, Import, Erst-Einrichtung), blieb bis zu sieben
   Tage ohne Marktpreis.
2. Ein **verpasster** Lauf wurde nie nachgeholt — Cron hat keine
   Misfire-Recovery, und beim Wochen-Takt kostete ein Update um 06:00 eine
   ganze Woche.
3. Beide Backfills luden die **4,25 MB** große History-XLSX, bevor sie
   überhaupt nachsahen, ob eine Zeile offen ist. Beim Wochen-Takt war das egal;
   beim Tages-Takt wäre es an fast allen Tagen ein Download für nichts.

Diese Proben halten alle drei fest. Sie prüfen den **Takt**, nicht die Uhrzeit
des Feuerns — der Zonen-Fall aus `test_scheduler_publish_takt.py` bleibt damit
außen vor.
"""

from __future__ import annotations

import inspect

import pytest

from backend.services import scheduler as scheduler_modul
from backend.services import kraftstoff_preis_service as kps


def test_takt_ist_taeglich_nicht_woechentlich():
    """Der Job darf an keinen Wochentag mehr gebunden sein.

    Gegen die Quelle geprüft, nicht gegen eine laufende Instanz: den Scheduler
    zu starten hieße APScheduler und einen Event-Loop mitzuziehen, und der
    Trigger steht als Literal in `start()`.
    """
    quelle = inspect.getsource(scheduler_modul.EEDCScheduler.start)
    block = quelle.split('id="kraftstoffpreis"')[0]
    # Der letzte Trigger vor der id-Zeile gehört zum Kraftstoffpreis-Job.
    letzter_trigger = block.rsplit("CronTrigger(", 1)[1].split(")")[0]
    assert "day_of_week" not in letzter_trigger, (
        f"Kraftstoffpreis-Job hängt wieder an einem Wochentag: {letzter_trigger!r} "
        "— #394: eine Monatszeile wartet dann bis zu sieben Tage auf ihren Preis."
    )
    assert "hour=" in letzter_trigger


def test_startlauf_existiert_und_ruft_den_job():
    """Der verpasste Lauf wird beim Start nachgeholt."""
    assert hasattr(scheduler_modul, "kraftstoffpreis_startup_recovery")
    quelle = inspect.getsource(scheduler_modul.kraftstoffpreis_startup_recovery)
    assert "kraftstoffpreis_job()" in quelle


def test_startlauf_ist_in_main_verdrahtet():
    """Eine Funktion, die niemand ruft, ist kein Nachlauf.

    Genau diese Klasse hatte die Etappe E1 mehrfach gefunden: ein Prüfer, der
    grün meldet, ohne je gerufen worden zu sein.
    """
    from pathlib import Path

    main_py = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "kraftstoffpreis_startup_recovery" in main_py
    assert "asyncio.create_task(kraftstoffpreis_startup_recovery())" in main_py


class _DownloadZaehler:
    """Trefferzähler statt Behauptung — ohne ihn beweist ein grüner Lauf nichts."""

    def __init__(self) -> None:
        self.aufrufe = 0

    async def __call__(self, *_a, **_kw):
        self.aufrufe += 1
        return None


@pytest.fixture
def download_zaehler(monkeypatch):
    zaehler = _DownloadZaehler()
    monkeypatch.setattr(kps, "_download_xlsx", zaehler)
    # Cache leeren, sonst antwortet der Service ohne Download und die Probe
    # misst nichts.
    monkeypatch.setattr(kps, "_cache", {})
    monkeypatch.setattr(kps, "_cache_timestamp", None)
    return zaehler


async def test_monats_backfill_laedt_nichts_ohne_offene_zeile(db, download_zaehler):
    from backend.models import Anlage

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="AT")
    db.add(anlage)
    await db.flush()

    ergebnis = await kps.backfill_monatsdaten_kraftstoffpreise(anlage.id, "AT", db)

    assert download_zaehler.aufrufe == 0, (
        "Ohne offene Monatszeile wurde die 4,25-MB-XLSX geladen — beim "
        "Tages-Takt ist das ein Download pro Tag für nichts."
    )
    assert ergebnis["aktualisiert"] == 0


async def test_tages_backfill_laedt_nichts_ohne_offene_zeile(db, download_zaehler):
    from backend.models import Anlage

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.flush()

    ergebnis = await kps.backfill_kraftstoffpreise(anlage.id, "DE", db)

    assert download_zaehler.aufrufe == 0
    assert ergebnis["aktualisiert"] == 0


async def test_offene_monatszeile_loest_den_download_aus(db, download_zaehler):
    """Die Gegenrichtung: mit offener Zeile MUSS geladen werden.

    Ohne diese Probe wäre der Ausstieg oben auch dann grün, wenn er immer
    aussteigt — der Ausstieg selbst wäre dann der Fehler.
    """
    from backend.models import Anlage
    from backend.models.monatsdaten import Monatsdaten

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="AT")
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=6,
        einspeisung_kwh=100.0, netzbezug_kwh=50.0,
        kraftstoffpreis_euro=None,
    ))
    await db.flush()

    await kps.backfill_monatsdaten_kraftstoffpreise(anlage.id, "AT", db)

    assert download_zaehler.aufrufe == 1
