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
    """Nächster Feuerzeitpunkt nach ``jetzt`` — die Größe, um die es geht."""
    return trigger.get_next_fire_time(None, jetzt.replace(tzinfo=TZ))


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
    lauf = _naechster_lauf(publish_takt_trigger(60), gemeldeter_wechsel)

    assert lauf.hour == gemeldeter_wechsel.hour + 1
    assert lauf.minute == 0
    assert lauf.second == 5


def test_der_takt_haengt_nicht_mehr_am_startzeitpunkt():
    """Zwei verschiedene Boots ergeben denselben Takt — vorher der Kern des Fehlers."""
    trigger = publish_takt_trigger(60)

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
