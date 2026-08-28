"""N-341 — ein zurueckgesetzter Zaehler bekommt KEINE Monatsmenge.

**Der Befund.** Ein Zaehler-Ruecksprung hinterlaesst zwei Spuren, und der
Monats-Pfad prueft bis zum 28.08.2026 nur eine davon: die negative
Randdifferenz. Der Tages-Pfad rief seit dem 26.08. beide und begruendete Weg 2
in seinem eigenen Docstring — *„Werden beide Raender eines Tagesreset-Zaehlers
vor dem Reset abgetastet, ist d positiv, plausibel und still falsch."*
**Ueber einen Monat ist genau das der Normalfall.**

**Gemessen, nicht vermutet** (28.08.2026): ein „…heute"-Zaehler, 14 Tage mit
realistischem Haushaltsprofil, laufender Monat ⇒ `mqtt_monats_deltas` lieferte
**5,6 kWh**, wahr waren **140,0**. Und es blieb nicht bei einem Vorschlag:
`aktueller_monat.py` ZEIGT diesen Wert in *Cockpit → Monat*.

⛔ **Und eedc rechnet auch nichts hoch — Entscheid Gernot, 28.08.2026.** Die
Menge liesse sich aus der mitgeschriebenen Standreihe summieren; das war gebaut
und gemessen (140,2 gegen 144,8 wahre, also 3,1 % Abschlag) und ist bewusst
wieder entfernt worden:

    „Es geht weniger um die Unterstuetzung des Zaehlers mit Tages-Reset, als um
     Datenqualitaetssicherung. Ich moechte die Einschraenkung bestehen lassen —
     auch wenn sie mit diesem Bau theoretisch aufhebbar waere."

Das deckt sich mit dem, was das Produkt dem Anwender ohnehin rät: Der
Daten-Checker empfiehlt an vier Stellen ausdruecklich *Zuruecksetzen „nie"
(ohne Zyklus)*, und `soll-waerme-klima.md` §3.1 haelt denselben Satz fuer den
Tages-Pfad fest. **Diese Proben halten den Entscheid fest, nicht eine
Implementierung** — wer hochrechnen will, entscheidet zuerst ihn um.

**Schwesterdatei:** `test_n341_checker_zaehler_ruecksprung.py` — dort steht die
andere Haelfte desselben Falls: Diese Datei prueft, dass eedc **keine Zahl**
liefert; jene, dass der Anwender **erfaehrt, warum**. Getrennt, weil die eine
den Rechenpfad misst und die andere den Daten-Checker; zusammen ergeben sie
erst die vollstaendige Antwort auf N-341.

⚠ **Feste Daten, kein gleitendes Fenster** (Lehre vom 28.08.2026): `bis` ist
ein Parameter, die Proben ruehren die Prozessuhr nicht an — sonst waeren sie in
drei Zeitzonen drei verschiedene Proben.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.migrations.migrate_datenquellen_materialisieren import (
    materialisiere_datenquellen,
)
from backend.services.mqtt_energy_history_service import mqtt_monats_deltas
from backend.services.snapshot.keys import (
    _mqtt_key_to_sensor_key,
    extract_quellen_energy,
)
from backend.services.snapshot.reader import zaehler_faellt_im_fenster
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import factories as f

JAHR, MONAT = 2026, 6
VON = datetime(JAHR, MONAT, 1)
#: Fester Messzeitpunkt im LAUFENDEN Monat — der Schadensfall.
BIS_LAUFEND = datetime(JAHR, MONAT, 15, 14, 0)

KEY = "netzbezug_kwh"

#: Netzbezug eines Haushalts je Stunde 00..23, kWh. Kein Rechteckprofil — ob
#: ein Ruecksprung auffaellt, haengt daran, WANN verbraucht wird.
PROFIL = [0.25, 0.20, 0.18, 0.18, 0.20, 0.30, 0.55, 0.70, 0.60, 0.40, 0.30,
          0.25, 0.30, 0.28, 0.25, 0.30, 0.45, 0.75, 0.95, 0.90, 0.70, 0.55,
          0.45, 0.35]
TAGESMENGE = sum(PROFIL)


async def _anlage(db, name: str):
    anlage = await f.anlage(db, anlagenname=name)
    await db.commit()
    await materialisiere_datenquellen(db)
    await db.commit()
    await db.refresh(anlage)
    return anlage


async def _schreibe(db, anlage, punkte: list[tuple[datetime, float]]) -> None:
    """Der ECHTE Weg zu den Staenden — Cache-Zeilen plus Produktions-Writer.

    Wer die `sensor_snapshots` von Hand hinschreibt, prueft seine eigene
    Annahme darueber, wie sie entstehen (Lehre aus N-328/W-5).
    """
    for ts, wert in punkte:
        db.add(MqttEnergySnapshot(
            anlage_id=anlage.id, timestamp=ts, energy_key=KEY, value_kwh=wert,
        ))
    await db.commit()
    for ts, _ in punkte:
        await snapshot_anlage(db, anlage, zeitpunkt=ts)
    await db.commit()


def _tagesreset_reihe(bis_tag: int, bis_stunde: int = 24) -> tuple[list, float]:
    """Ein „…heute"-Zaehler: stuendlich abgetastet, um Mitternacht auf 0."""
    punkte: list[tuple[datetime, float]] = []
    wahr = 0.0
    for tag in range(1, bis_tag + 1):
        stunden = bis_stunde if tag == bis_tag else 24
        stand = 0.0
        for h in range(stunden):
            punkte.append((datetime(JAHR, MONAT, tag, h), round(stand, 3)))
            stand += PROFIL[h]
        wahr += stand
    return punkte, wahr


async def _mengen(db, anlage, bis=None) -> dict[str, float]:
    return await mqtt_monats_deltas(
        db, anlage.id, JAHR, MONAT, [KEY],
        quellen_energy=extract_quellen_energy(anlage), bis=bis,
    )


# ─────────────────────────────────────────────────────────────────────────
# 1 — Der gemeldete Schaden: positiv, plausibel, falsch
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_laufender_monat_liefert_keinen_wert_statt_eines_falschen(db):
    """5,6 statt 140 kWh — das war der Wert, den Cockpit → Monat anzeigte.

    Beide Raender liegen vor einem Reset, die Randdifferenz ist deshalb
    positiv und plausibel: der Tagesstand des 15. Juni. **Eine Monatsmenge
    unterhalb einer Tagesmenge**, ohne dass irgendetwas sie als verdaechtig
    ausgewiesen haette.
    """
    anlage = await _anlage(db, "Reset laufend")
    punkte, wahr = _tagesreset_reihe(bis_tag=15, bis_stunde=15)
    await _schreibe(db, anlage, punkte)

    mengen = await _mengen(db, anlage, bis=BIS_LAUFEND)

    assert KEY not in mengen, (
        "ein zurueckgesetzter Zaehler darf keine Monatsmenge liefern — vorher "
        f"kamen hier {sum(PROFIL[:15]):.1f} kWh statt {wahr:.1f}"
    )
    # Der Detektor hat den Ruecksprung wirklich gesehen; das Fehlen kommt
    # nicht daher, dass gar keine Staende da waeren.
    assert await zaehler_faellt_im_fenster(
        db, anlage.id, _mqtt_key_to_sensor_key(KEY), VON, BIS_LAUFEND, 0.0,
        round(sum(PROFIL[:15]), 3),
    ) is True


@pytest.mark.asyncio
async def test_die_reihe_gaebe_die_menge_her_und_eedc_rechnet_sie_trotzdem_nicht(db):
    """**Der Entscheid, nicht die Technik** (Gernot, 28.08.2026).

    Hier liegen 30 vollstaendige Tage stuendlich mitgeschrieben vor — eine
    Summe ueber die Reihe waere ohne Weiteres moeglich und lag als Bau vor
    (gemessen: 3,1 % unter dem wahren Wert). eedc liefert **nichts**, weil ein
    Monatswert mit systematischem Abschlag, den der Anwender per Knopfdruck in
    seinen Abschluss uebernimmt, der Empfehlung des eigenen Daten-Checkers
    widerspricht: *Zuruecksetzen „nie" (ohne Zyklus)*.

    ⛔ Diese Probe wird rot, sobald jemand die Hochrechnung einbaut — und das
    ist ihr Zweck. Der Entscheid gehoert Gernot, nicht dieser Datei.
    """
    anlage = await _anlage(db, "Reihe vollstaendig")
    punkte, wahr = _tagesreset_reihe(bis_tag=30)
    punkte.append((datetime(JAHR, MONAT + 1, 1), 0.0))
    await _schreibe(db, anlage, punkte)

    mengen = await _mengen(db, anlage)

    assert wahr > 300, "die Fixture muss eine nennenswerte Menge enthalten"
    assert KEY not in mengen


# ─────────────────────────────────────────────────────────────────────────
# 2 — Die Gegenrichtung: der Fix darf NICHT jeden treffen
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fortlaufender_zaehler_behaelt_seine_randdifferenz(db):
    """Ohne Ruecksprung aendert sich nichts — und das ist der wichtigere Teil.

    Eine Reset-Erkennung, die zu weit greift, nimmt **jedem** MQTT-Anwender
    seinen Monatsvorschlag. Die Randdifferenz bleibt exakt, was sie war.
    """
    anlage = await _anlage(db, "Fortlaufend")
    punkte = []
    stand = 1000.0
    for tag in range(1, 16):
        for h in range(24):
            punkte.append((datetime(JAHR, MONAT, tag, h), round(stand, 3)))
            stand += PROFIL[h]
    await _schreibe(db, anlage, punkte)

    mengen = await _mengen(db, anlage, bis=BIS_LAUFEND)

    erwartet = round(14 * TAGESMENGE + sum(PROFIL[:14]), 1)
    assert mengen[KEY] == pytest.approx(erwartet, abs=0.2)


# ─────────────────────────────────────────────────────────────────────────
# 3 — Die Blindstelle des alten Detektors
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ruecksprung_faellt_auch_auf_wenn_er_nicht_an_den_raendern_steht(db):
    """Der Detektor prueft die **Folge**, nicht ihre Extremwerte.

    ⚠ **Bis zum 28.08.2026 verglich `zaehler_faellt_im_fenster` nur ``MIN``
    und ``MAX`` gegen die Raender** — obwohl er Monotonie-Pruefung hiess. Das
    ist blind, sobald der Startstand zufaellig das Minimum und der Endstand das
    Maximum ist: Genau hier beginnt das Fenster kurz nach einem Reset und endet
    kurz vor dem naechsten. Kein Zwischenstand liegt ausserhalb, und die Reihe
    ist trotzdem dreizehnmal auf null gefallen.

    **Real trifft das Cockpit → Monat**, wenn der Anwender es am Monatsletzten
    spaetabends aufruft. Gemessen am selben Bestand: Extremwert-Pruefung
    ``False``, echte Monotonie-Pruefung ``True``.
    """
    anlage = await _anlage(db, "Blindstelle")
    punkte, _ = _tagesreset_reihe(bis_tag=14)
    await _schreibe(db, anlage, punkte)

    sk = _mqtt_key_to_sensor_key(KEY)
    # Das Fenster endet auf dem TAGESHOECHSTSTAND des letzten Tages — damit ist
    # der Endstand zugleich das Maximum der ganzen Reihe, und der Startstand
    # (kurz nach einem Reset) ihr Minimum.
    bis = datetime(JAHR, MONAT, 14, 23, 0)
    startstand, endstand = 0.0, round(sum(PROFIL[:23]), 3)

    # Die alte Extremwert-Pruefung sieht hier nichts — beide Schranken halten,
    # obwohl die Reihe dreizehnmal gefallen ist.
    zwischen = [wert for ts, wert in punkte if VON < ts < bis]
    assert max(zwischen) <= endstand + 0.01
    assert min(zwischen) >= startstand - 0.01

    # … die Folge-Pruefung sieht den Sturz.
    assert await zaehler_faellt_im_fenster(
        db, anlage.id, sk, VON, bis, startstand, endstand,
    ) is True
    assert KEY not in await _mengen(db, anlage, bis=bis)
