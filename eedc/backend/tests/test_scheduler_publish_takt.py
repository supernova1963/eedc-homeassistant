"""Der MQTT-Auto-Publish taktet an der Uhr, nicht am Start des Add-ons (F-29).

**Der gemeldete Fall (rapahl, PN 2026-08-11):** Der Sensor „Börsenpreis aktuell"
wechselte in seinem HA-Verlauf um **09:12:56** und — nach einem Update-Neustart —
um **11:08:02**, jeweils auf den *richtigen* Wert der laufenden Stunde. Der Wert
stimmte also, die Zeit nicht: der ``IntervalTrigger`` lief ab dem Boot-Zeitpunkt
durch, und bei der Voreinstellung von 60 Minuten bestimmte allein der letzte
Neustart, wie lange nach dem Stundenwechsel der neue Preis in HA ankam.

Die Tests rechnen deshalb mit genau diesen beiden Zeitpunkten als Referenz.
"""

from datetime import datetime, timedelta

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.services.scheduler import publish_takt_trigger

try:  # APScheduler rechnet mit tz-aware Zeiten
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Berlin")
except ImportError:  # pragma: no cover
    TZ = None


def _naechster_lauf(trigger, jetzt: datetime) -> datetime:
    """Nächster Feuerzeitpunkt nach ``jetzt``, **in der Zone des Triggers**.

    ⚠ **Zwei Zonen, und sie dürfen nicht vermischt werden** (Lehre v4.0.14):
    Ein ``CronTrigger`` ohne eigenes ``timezone``-Argument rechnet in der Zone
    des **Prozesses**. Die Dev-Box läuft auf Europe/Berlin, der CI-Runner auf
    UTC — derselbe, korrekte Feuerzeitpunkt heißt dort einmal 10:00:05 und
    einmal 08:00:05.

    Wer das **Raster** prüft (liegt der Lauf auf einer vollen Stunde, auf
    Minute 0/15/30/45?), muss in genau dieser Zone bleiben — das Raster ist
    eine Eigenschaft des Triggers. Wer dagegen prüft, ob der Lauf die
    **Folgestunde des Melders** trifft, rechnet über ``_in_melder_zone`` nach
    Europe/Berlin zurück; dort sind rapahls Zeitpunkte notiert.
    """
    return trigger.get_next_fire_time(None, jetzt.replace(tzinfo=TZ))


def _in_melder_zone(lauf: datetime) -> datetime:
    """Feuerzeitpunkt in der Zone, in der die gemeldeten Zeiten notiert sind.

    08:00:05 UTC **ist** 10:00:05 Berlin — die Umrechnung ändert nichts am
    Verhalten, sie stellt nur die Vergleichbarkeit mit dem Screenshot her.
    """
    return lauf.astimezone(TZ) if (lauf is not None and TZ is not None) else lauf


def _versatz_zu_berlin_ist_voll_stuendig(zeitpunkt: datetime) -> bool:
    """Liegt die volle Stunde der Prozess-Zone auch in Berlin auf Minute 0?

    ⚠ **Die Grenze der beiden Melder-Tests, ausgeschrieben statt verschwiegen.**
    Der Trigger richtet sich an der **lokalen** Uhr aus — das ist die Absicht.
    In einer Zone mit halbstündigem Versatz (Asia/Kolkata +5:30) feuert er
    lokal zur vollen Stunde und damit in Berlin um :30. Der Lauf ist dann
    korrekt, die Erwartung „Minute 0 in Berliner Sicht" aber unzutreffend —
    der Test kann dort über den gemeldeten Fall nichts aussagen und sagt das,
    statt grün zu behaupten oder rot zu lügen. Für die realen Umgebungen
    (Dev-Box Europe/Berlin, CI UTC, Add-on meist UTC) greift er.
    """
    hier = zeitpunkt.replace(tzinfo=None).astimezone()
    versatz = hier.utcoffset() - zeitpunkt.replace(tzinfo=TZ).utcoffset()
    return versatz.total_seconds() % 3600 == 0


@pytest.mark.parametrize(
    "gemeldeter_wechsel",
    [
        datetime(2026, 8, 11, 9, 12, 56),   # sein erster Screenshot, 11,08 ct
        datetime(2026, 8, 11, 11, 8, 2),    # sein zweiter, 0,95 ct — anderer Boot
    ],
)
def test_stundentakt_faellt_auf_die_volle_stunde(gemeldeter_wechsel):
    """Bei der Voreinstellung (60 Min) liegt der nächste Lauf zur vollen Stunde.

    Das ist der eigentliche Fix: Egal wann das Add-on gestartet wurde, der
    nächste Publish nach einem seiner beiden gemeldeten Zeitpunkte liegt auf
    ``:00:05`` der Folgestunde — nicht 12 bzw. 8 Minuten daneben.
    """
    if not _versatz_zu_berlin_ist_voll_stuendig(gemeldeter_wechsel):
        pytest.skip(
            "Prozess-Zone hat keinen vollstündigen Versatz zu Europe/Berlin — "
            "die volle Stunde des Triggers liegt dort nicht auf Berliner Minute 0"
        )
    lauf = _in_melder_zone(_naechster_lauf(publish_takt_trigger(60), gemeldeter_wechsel))

    assert lauf.hour == gemeldeter_wechsel.hour + 1
    assert lauf.minute == 0
    assert lauf.second == 5


def test_der_takt_haengt_nicht_mehr_am_startzeitpunkt():
    """Zwei verschiedene Boots ergeben denselben Takt — vorher der Kern des Fehlers.

    Dieselbe Zonen-Voraussetzung wie oben: bei halbstündigem Versatz fallen die
    beiden Berliner Zeitpunkte 9:12 und 9:47 in **verschiedene** lokale Stunden
    (12:42 und 13:17 in Kolkata), und dann sind zwei Läufe zu Recht verschieden.
    """
    trigger = publish_takt_trigger(60)
    if not _versatz_zu_berlin_ist_voll_stuendig(datetime(2026, 8, 11, 9, 12, 56)):
        pytest.skip("Prozess-Zone hat keinen vollstündigen Versatz zu Europe/Berlin")

    aus_boot_a = _naechster_lauf(trigger, datetime(2026, 8, 11, 9, 12, 56))
    aus_boot_b = _naechster_lauf(trigger, datetime(2026, 8, 11, 9, 47, 3))

    assert aus_boot_a == aus_boot_b


@pytest.mark.parametrize(
    "interval,erwartete_minuten",
    [
        (5, {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        (15, {0, 15, 30, 45}),
        (30, {0, 30}),
    ],
)
def test_teiler_einer_stunde_rasten_in_die_uhr_ein(interval, erwartete_minuten):
    """Wer häufiger publiziert, trifft trotzdem die volle Stunde mit."""
    trigger = publish_takt_trigger(interval)
    assert isinstance(trigger, CronTrigger)

    jetzt = datetime(2026, 8, 11, 9, 12, 56)
    getroffen = set()
    for _ in range(12):
        lauf = _naechster_lauf(trigger, jetzt).replace(tzinfo=None)
        getroffen.add(lauf.minute)
        # eine Sekunde weiter, sonst liefert der Trigger denselben Punkt erneut
        jetzt = lauf + timedelta(seconds=1)

    assert getroffen <= erwartete_minuten
    assert 0 in getroffen, "die volle Stunde muss im Raster liegen"


@pytest.mark.parametrize("interval", [120, 240, 720, 1440])
def test_volle_stundenschritte_liegen_auf_der_vollen_stunde(interval):
    """Auch die groben Intervalle richten sich am Tag aus statt am Boot."""
    lauf = _naechster_lauf(publish_takt_trigger(interval), datetime(2026, 8, 11, 9, 12, 56))

    assert lauf.minute == 0
    assert lauf.second == 5
    assert lauf.hour % (interval // 60) == 0


@pytest.mark.parametrize("interval", [25, 90, 100])
def test_krumme_intervalle_behalten_das_bisherige_verhalten(interval):
    """Was nicht in die Uhr passt, wird nicht zurechtgebogen.

    Ein Intervall wie 90 Minuten hat keinen Rasterpunkt, der sich stündlich
    wiederholt — dort wäre jede Ausrichtung eine stille Änderung des
    eingestellten Abstands.
    """
    assert isinstance(publish_takt_trigger(interval), IntervalTrigger)
