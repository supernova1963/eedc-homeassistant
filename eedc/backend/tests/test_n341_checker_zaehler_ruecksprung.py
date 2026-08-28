"""Der Daten-Checker sagt, warum ein Feld leer bleibt (N-341).

**Der Anlass.** eedc lehnt einen Zaehler mit Tages- oder Monats-Reset als
Mengenquelle ab — die Differenz zweier Staende, zwischen denen der Zaehler neu
begonnen hat, ist keine Menge. Bis zum 28.08.2026 entstand daraus im
Monatsfenster sogar eine *falsche* Zahl; seither entsteht **keine**.

⚠ **Fuer den Anwender sehen beide Zustaende gleich aus:** ein leeres Feld. Der
Rat, den er braeuchte, steht im Produkt — aber an der falschen Stelle seines
Lebenslaufs: Der Daten-Checker nennt ihn beim **Anlegen** eines Helfers
(*Zuruecksetzen „nie" (ohne Zyklus)*, `sensoren.py`). Wer den Sensor bereits
zugeordnet hat, liest ihn nie. **Dieselbe Klasse wie W-18**: ein erkannter
Zustand, der ausschliesslich als Logzeile existierte.

**Schwesterdatei:** `test_n341_reset_zaehler_wird_abgelehnt.py` — sie prueft die
andere Haelfte: dass eedc fuer so einen Zaehler gar keine Menge bildet (und auch
keine hochrechnet). Ohne diese Datei hier waere das eine stille Leerstelle.

⚠ **Feste Uhr ueber die Naht.** Der Check bekommt seinen Endzeitpunkt als
Parameter; die Proben ruehren `datetime.now()` nicht an (N-167, Waechter
`test_konformitaet_echte_uhr_in_tests.py`). Die Staende liegen relativ zu
diesem festen Zeitpunkt — damit ist die Probe in jeder Zeitzone dieselbe.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity
from backend.services.migrations.migrate_datenquellen_materialisieren import (
    materialisiere_datenquellen,
)
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import factories as f

#: Fester Endzeitpunkt des Prueffensters — keine Prozessuhr.
JETZT = datetime(2026, 6, 20, 12, 0)
KAT = CheckKategorie.ZAEHLER_RUECKSPRUNG.value


async def _anlage_mit_reihe(db, name: str, *, reset: bool, key: str = "netzbezug_kwh"):
    """14 Tage stuendliche Staende vor `JETZT` — mit oder ohne Mitternachts-Reset."""
    anlage = await f.anlage(db, anlagenname=name)
    await db.commit()
    await materialisiere_datenquellen(db)
    await db.commit()
    await db.refresh(anlage)

    punkte: list[tuple[datetime, float]] = []
    laufend = 1000.0
    for tag_rueck in range(14, 0, -1):
        tag = (JETZT - timedelta(days=tag_rueck)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        heute = 0.0
        for h in range(24):
            punkte.append((tag + timedelta(hours=h),
                           round(heute if reset else laufend, 3)))
            heute += 0.4
            laufend += 0.4

    for ts, wert in punkte:
        db.add(MqttEnergySnapshot(
            anlage_id=anlage.id, timestamp=ts, energy_key=key, value_kwh=wert,
        ))
    await db.commit()
    for ts, _ in punkte:
        await snapshot_anlage(db, anlage, zeitpunkt=ts)
    await db.commit()
    return anlage


async def _befunde(db, anlage) -> list:
    checker = DatenChecker(db)
    return await checker._check_zaehler_ruecksprung(anlage, jetzt=JETZT)


# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_zaehler_wird_gemeldet_mit_beleg(db):
    """Der Anwender erfaehrt, WAS ist, WAS folgt und WAS er tun kann."""
    anlage = await _anlage_mit_reihe(db, "Reset", reset=True)

    befunde = await _befunde(db, anlage)

    assert len(befunde) == 1
    b = befunde[0]
    assert b.kategorie == KAT
    assert b.schwere == CheckSeverity.WARNING
    # Was ist — mit Beleg, nicht als Behauptung.
    assert "zurückgesetzt" in b.meldung
    assert "→" in b.details, "der Beleg nennt beide Staende"
    # Was folgt.
    assert "keine" in b.meldung and "Monatsmenge" in b.meldung
    # Was zu tun ist — und zwar an der QUELLE, nicht in eedc.
    assert "fortlaufenden Stand" in b.details
    assert "nie" in b.details
    # ⛔ Kein Reparatur-Knopf: eedc kann den Ruecksprung nicht heilen.
    assert b.action_kind is None


@pytest.mark.asyncio
async def test_fortlaufender_zaehler_wird_nicht_gemeldet(db):
    """Die Gegenprobe, ohne die der Befund nichts wert waere.

    Ein Pruefer, der bei jeder Anlage anschlaegt, ist kein Pruefer. Dieselbe
    Reihe, dieselbe Menge, nur ohne Mitternachts-Reset.
    """
    anlage = await _anlage_mit_reihe(db, "Fortlaufend", reset=False)

    assert await _befunde(db, anlage) == []


@pytest.mark.asyncio
async def test_ohne_mqtt_reihen_schweigt_der_check(db):
    """Eine Anlage ohne MQTT-Staende ist kein Befund, sondern eine Anlage."""
    anlage = await f.anlage(db, anlagenname="Ohne MQTT")
    await db.commit()

    assert await _befunde(db, anlage) == []


@pytest.mark.asyncio
async def test_der_befund_haengt_am_pruef_fenster_nicht_an_der_uhr(db):
    """Ein Ruecksprung, der aus dem Fenster gelaufen ist, wird nicht gemeldet.

    ⭐ **Kein Dauer-Noergeln** ([[feedback_daten_checker_kein_akzeptiert]]):
    Wer seinen Publisher umgestellt hat, soll die Meldung wieder loswerden —
    ohne Quittier-Knopf, allein dadurch, dass die Reihe wieder monoton ist.
    Hier laeuft dieselbe Anlage gegen einen Endzeitpunkt weit hinter der
    Reihe: die alten Ruecksprünge liegen ausserhalb, und der Check schweigt.
    """
    anlage = await _anlage_mit_reihe(db, "Alt", reset=True)

    checker = DatenChecker(db)
    spaeter = await checker._check_zaehler_ruecksprung(
        anlage, jetzt=JETZT + timedelta(days=120),
    )

    assert spaeter == []


def test_der_check_haengt_am_echten_einstieg():
    """Ein Befund, den `check_anlage` nie ruft, existiert fuer niemanden.

    ⚠ **Das ist die Backend-Haelfte von F-21** (10.08.): Dort stand eine
    fertige Kategorie samt Reparatur-Knopf in keiner der beiden Frontend-Listen
    und war unerreichbar. Die Frontend-Haelfte waechtert
    `datenCheckerKategorien.test.ts` seither ueber ALLE Kategorien.

    ⛔ **Warum als Quelltext-Probe und nicht ueber `check_anlage`:** Der echte
    Einstieg liest die Uhr (`datetime.now()`), die Fixture liegt auf einem
    festen Datum — eine Probe darueber waere am Folgetag eine andere Probe
    (N-167). Hier zaehlt allein, DASS der Aufruf steht.
    """
    from pathlib import Path

    quelle = Path("backend/services/daten_checker/__init__.py").read_text(
        encoding="utf-8"
    )
    assert "self._check_zaehler_ruecksprung(anlage)" in quelle, (
        "der Check wird in check_anlage nicht gerufen — der Befund waere "
        "unerreichbar (F-21-Klasse)"
    )
