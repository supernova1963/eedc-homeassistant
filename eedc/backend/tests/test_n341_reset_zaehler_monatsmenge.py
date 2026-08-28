"""N-341 — ein zurueckgesetzter Zaehler bekommt seine Menge, statt sie zu erfinden.

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

⭐ **Der Fix endet nicht bei „keine Zahl".** Die Standreihe ist stuendlich
mitgeschrieben — aus ihr laesst sich die Menge summieren. Das ist die Antwort
auf die Zusage, die `MQTT_INBOUND.md` dem Anwender gibt (*„Ein taeglich oder
monatlich zurueckgesetzter Zaehler funktioniert ebenfalls"*), und es ist der
Unterschied zwischen „eedc kann das" und „eedc sagt nichts dazu".

⚠ **Die Grenze wird mitgeprueft, nicht nur mitgeteilt.** Was zwischen der
letzten Abtastung und dem Ruecksprung verbraucht wird, fehlt — rund 3 % bei
stuendlicher Abtastung, immer in dieselbe Richtung. Deshalb traegt jede Menge
ihren `weg`, und der Monatsabschluss sagt ihn dem Anwender ins Gesicht, bevor
er die Zahl uebernimmt.

⚠ **Feste Daten, kein gleitendes Fenster** (Lehre vom 28.08.2026): `bis` ist
ein Parameter, die Proben ruehren die Prozessuhr nicht an — sonst waeren sie in
drei Zeitzonen drei verschiedene Proben.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.api.routes.monatsabschluss.views import (
    KONFIDENZ_MQTT_RANDDIFFERENZ,
    KONFIDENZ_MQTT_REIHENSUMME,
    _mqtt_vorschlag,
)
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.migrations.migrate_datenquellen_materialisieren import (
    materialisiere_datenquellen,
)
from backend.services.mqtt_energy_history_service import (
    MonatsMenge,
    mqtt_monats_deltas,
)
from backend.services.snapshot.aggregator import _tageswert_aus_raendern
from backend.services.snapshot.keys import (
    _mqtt_key_to_sensor_key,
    extract_quellen_energy,
)
from backend.services.snapshot.reader import (
    WEG_RANDDIFFERENZ,
    WEG_REIHENSUMME,
    delta_mit_weg,
)
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import factories as f

JAHR, MONAT = 2026, 6
VON = datetime(JAHR, MONAT, 1)
#: Fester Messzeitpunkt im LAUFENDEN Monat — der Schadensfall.
BIS_LAUFEND = datetime(JAHR, MONAT, 15, 14, 0)
BIS_ABGESCHLOSSEN = datetime(JAHR, MONAT + 1, 1)

KEY = "netzbezug_kwh"

#: Netzbezug eines Haushalts je Stunde 00..23, kWh. Kein Rechteckprofil — der
#: Abtastfehler des Sigma-Wegs haengt daran, WANN verbraucht wird.
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
    """Ein „…heute"-Zaehler: stuendlich abgetastet, um Mitternacht auf 0.

    Returns:
        ``(punkte, wahre_menge)`` — die Punkte liegen auf :00, wie der
        stuendliche Snapshot-Job sie schreibt.
    """
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


# ─────────────────────────────────────────────────────────────────────────
# 1 — Der gemeldete Schaden: positiv, plausibel, falsch
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_laufender_monat_liefert_die_menge_statt_des_tagesrests(db):
    """5,6 statt 140 kWh — das war der Wert, den Cockpit → Monat anzeigte."""
    anlage = await _anlage(db, "Reset laufend")
    punkte, wahr = _tagesreset_reihe(bis_tag=15, bis_stunde=15)
    await _schreibe(db, anlage, punkte)

    mengen = await mqtt_monats_deltas(
        db, anlage.id, JAHR, MONAT, [KEY],
        quellen_energy=extract_quellen_energy(anlage), bis=BIS_LAUFEND,
    )
    menge = mengen[KEY]

    # Der alte Weg haette hier den Tagesstand des 15. geliefert — eine Zahl,
    # die kleiner ist als ein einziger Tag.
    assert menge.wert > TAGESMENGE, (
        "eine Monatsmenge darf nie unter einer Tagesmenge liegen — genau das "
        "war der Befund"
    )
    assert menge.weg == WEG_REIHENSUMME
    # Die Groessenordnung stimmt, der systematische Abschlag ist benannt.
    assert 0.90 * wahr <= menge.wert <= wahr, (
        f"{menge.wert} liegt nicht im erwarteten Band um {wahr:.1f} kWh"
    )


@pytest.mark.asyncio
async def test_abgeschlossener_monat_bekommt_ueberhaupt_eine_auskunft(db):
    """Die mildere Haelfte: vorher fiel der Wert still heraus (`menge > 0`)."""
    anlage = await _anlage(db, "Reset abgeschlossen")
    punkte, wahr = _tagesreset_reihe(bis_tag=30)
    # Der erste Stand des Folgemonats schliesst das Fenster.
    punkte.append((BIS_ABGESCHLOSSEN, 0.0))
    await _schreibe(db, anlage, punkte)

    mengen = await mqtt_monats_deltas(
        db, anlage.id, JAHR, MONAT, [KEY],
        quellen_energy=extract_quellen_energy(anlage),
    )

    assert KEY in mengen, "vorher lieferte der abgeschlossene Monat gar nichts"
    assert mengen[KEY].weg == WEG_REIHENSUMME
    assert 0.90 * wahr <= mengen[KEY].wert <= wahr


@pytest.mark.asyncio
async def test_der_stand_direkt_nach_dem_ruecksprung_zaehlt_mit(db):
    """Der erste Stand NACH einem Ruecksprung ist selbst ein Zuwachs.

    ⚠ **Diese Probe kam nach einer bestandenen Gegenprobe dazu, die nichts
    bewiesen hat.** Die Proben oben tasten stuendlich ab; direkt nach einem
    Mitternachts-Reset steht dort fast nichts, und der Zweig
    ``summe += max(0.0, stand)`` addiert eine Groesse nahe null. Ein
    Sprengsatz, der ihn entfernte, blieb deshalb **gruen** — der Zweig war
    ungeprueft. *Ein gruener Lauf beweist nur dann etwas, wenn der Pruefer rot
    melden kann.*

    Hier sendet der Publisher alle sechs Stunden statt stuendlich — ein realer
    Fall, MQTT-Intervalle sind Sache des Absenders. Der erste Stand des Tages
    traegt dann bereits ein Viertel Tagesverbrauch, und ob er mitgezaehlt wird,
    entscheidet ueber rund 13 % der Monatsmenge.
    """
    anlage = await _anlage(db, "Reset grob abgetastet")
    stunden = (6, 12, 18, 23)
    punkte: list[tuple[datetime, float]] = [(VON, 0.0)]
    fenster_wahr = 0.0
    erster_stand_je_tag = 0.0
    for tag in range(1, 15):
        for h in stunden:
            punkte.append((datetime(JAHR, MONAT, tag, h), round(sum(PROFIL[:h]), 3)))
        # Das Fenster endet am 14. um 23:00 — der Rest jenes Tages liegt ausserhalb.
        fenster_wahr += sum(PROFIL) if tag < 14 else sum(PROFIL[:23])
    erster_stand_je_tag = sum(PROFIL[:6])
    await _schreibe(db, anlage, punkte)

    mengen = await mqtt_monats_deltas(
        db, anlage.id, JAHR, MONAT, [KEY],
        quellen_energy=extract_quellen_energy(anlage),
        bis=datetime(JAHR, MONAT, 14, 23, 0),
    )
    menge = mengen[KEY]
    assert menge.weg == WEG_REIHENSUMME

    # Ohne den Ruecksprung-Zweig fehlte je Tageswechsel der erste Stand des
    # neuen Tages — dreizehnmal ein Viertel Tagesverbrauch.
    ohne_zweig = menge.wert - 13 * erster_stand_je_tag
    assert menge.wert > ohne_zweig + 10, (
        "der Stand direkt nach dem Ruecksprung traegt hier zweistellig — "
        "faellt er weg, muss die Probe das sehen"
    )
    assert 0.90 * fenster_wahr <= menge.wert <= fenster_wahr


# ─────────────────────────────────────────────────────────────────────────
# 2 — Die Gegenrichtung: der Fix darf NICHT jeden treffen
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fortlaufender_zaehler_bleibt_bei_der_randdifferenz(db):
    """Ohne Ruecksprung aendert sich nichts — und das ist der wichtigere Teil.

    Ein Fix, der auch den ungestoerten Zaehler auf die Reihensumme umstellt,
    haette JEDEN MQTT-Anwender getroffen und ihm rund 3 % abgezogen.
    """
    anlage = await _anlage(db, "Fortlaufend")
    punkte = []
    stand = 1000.0
    for tag in range(1, 16):
        for h in range(24):
            punkte.append((datetime(JAHR, MONAT, tag, h), round(stand, 3)))
            stand += PROFIL[h]
    await _schreibe(db, anlage, punkte)

    mengen = await mqtt_monats_deltas(
        db, anlage.id, JAHR, MONAT, [KEY],
        quellen_energy=extract_quellen_energy(anlage), bis=BIS_LAUFEND,
    )

    assert mengen[KEY].weg == WEG_RANDDIFFERENZ
    # Exakt die Randdifferenz: Stand um 14:00 am 15. minus Stand am 01. 00:00.
    erwartet = round(14 * TAGESMENGE + sum(PROFIL[:14]), 1)
    assert mengen[KEY].wert == pytest.approx(erwartet, abs=0.2)


@pytest.mark.asyncio
async def test_ruecksprung_ohne_zwischenstaende_sagt_nichts(db):
    """Kein Stand zwischen den Raendern ⇒ keine Aussage, keine Null.

    Ohne Zwischenstaende gibt es nichts zu summieren, was die Randdifferenz
    nicht schon wuesste — und die ist hier zwei unzusammenhaengende
    Zaehlerlaeufe weit. Eine 0 waere eine Behauptung (ADR-002/P4).
    """
    anlage = await _anlage(db, "Nur Raender")
    await _schreibe(db, anlage, [
        (VON, 900.0),
        (BIS_LAUFEND, 5.6),          # Zaehlertausch/Reset, nichts dazwischen
    ])

    menge, weg = await delta_mit_weg(
        db, anlage.id, _mqtt_key_to_sensor_key(KEY), None, VON, BIS_LAUFEND,
        quellen_energy=extract_quellen_energy(anlage),
    )

    assert menge is None and weg is None


# ─────────────────────────────────────────────────────────────────────────
# 3 — Die Abgrenzung zum Tages-Pfad, und warum sie bleibt
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_der_tag_lehnt_weiter_ab_waehrend_der_monat_summiert(db):
    """Monat summiert, Tag lehnt ab — **derselbe Zaehler, dieselben Staende.**

    ⭐ **Diese Probe haelt eine Entscheidung fest, nicht eine Implementierung.**
    Beim Bau von N-341 lag es nahe, den Tages-Pfad gleich mitzuziehen: dieselbe
    Erkennung, dieselbe Reihe, eine Zeile mehr. Vier Proben in
    `test_soll_waerme_klima_achse3_aufloesung.py` haben widersprochen — und sie
    hatten recht. `soll-waerme-klima.md` §3.1 sagt: *„Ein Zaehler mit
    Tages-Reset wird erkannt und abgelehnt, statt still falsche Werte zu
    erzeugen."*

    **Warum die beiden Faelle verschieden sind:** Der Monatspfad zeigte einen
    FALSCHEN Wert — dort ist die Summe die Reparatur. Der Tages-Pfad lehnt
    bereits ab, und er fuehrt ueber `get_betriebsart_strom_tageswerte` auf die
    Waerme/Klima-Flaeche, wo eine Betriebsart-**Teilmenge** mit 3 % Abschlag
    gegen eine exakte Gesamtmenge staende (Kanon-Regel K1).

    ⛔ Wer den Tag umstellen will, entscheidet zuerst §3.1 um. Diese Probe wird
    dann rot — und das ist ihr Zweck.
    """
    anlage = await _anlage(db, "Abgrenzung Tag/Monat")
    punkte, _ = _tagesreset_reihe(bis_tag=4)
    await _schreibe(db, anlage, punkte)
    sk = _mqtt_key_to_sensor_key(KEY)

    tageswert = await _tageswert_aus_raendern(
        db, anlage.id, sk,
        0.0, 0.0,                     # beide Raender liegen auf einem Reset
        datetime(JAHR, MONAT, 3), datetime(JAHR, MONAT, 4), date(JAHR, MONAT, 3),
    )
    monatsmenge, weg = await delta_mit_weg(
        db, anlage.id, sk, None, VON, datetime(JAHR, MONAT, 4),
        quellen_energy=extract_quellen_energy(anlage),
    )

    assert tageswert is None, "der Tag lehnt einen Tagesreset-Zaehler ab (§3.1)"
    assert monatsmenge is not None and weg == WEG_REIHENSUMME


# ─────────────────────────────────────────────────────────────────────────
# 4 — Der Anwender erfaehrt es, bevor er die Zahl uebernimmt
# ─────────────────────────────────────────────────────────────────────────

def test_vorschlag_nennt_den_weg_und_stuft_die_konfidenz():
    """Ein uebernommener Wert mit stillem Abschlag waere derselbe Fehler."""
    summiert = _mqtt_vorschlag(MonatsMenge(wert=140.0, weg=WEG_REIHENSUMME))
    exakt = _mqtt_vorschlag(MonatsMenge(wert=140.0, weg=WEG_RANDDIFFERENZ))

    assert summiert.konfidenz == KONFIDENZ_MQTT_REIHENSUMME
    assert exakt.konfidenz == KONFIDENZ_MQTT_RANDDIFFERENZ
    assert summiert.konfidenz < exakt.konfidenz
    assert "zurückgesetzt" in summiert.beschreibung
    assert "zu niedrig" in summiert.beschreibung
    # Die alte Beschriftung behauptete eine Differenz — bei der Summe waere das
    # schlicht unwahr.
    assert "Differenz" not in summiert.beschreibung
    assert "Differenz" in exakt.beschreibung
