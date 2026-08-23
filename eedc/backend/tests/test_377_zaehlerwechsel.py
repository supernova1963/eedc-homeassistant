"""#377 — der Zählerwechsel, an echten Zeilen gemessen (Probe 9 aus §7).

**Gernots Kanon (20.08.2026):** Neuer Zähler ⇒ **altes Gerät stilllegen, neues
anlegen.** Kein Reset-Erkennungscode, keine geglättete Kurve — zwei Geräte, zwei
Stände, zwei Verläufe.

Diese Probe steht in einer eigenen Datei, weil sie eine **Datenbank** braucht:
Die Fensterlogik von `lade_zaehlerstaende` ist ohne echte Snapshot-Zeilen nicht
ehrlich prüfbar. Eine Fixture, die sich den Zustand nur ausdenkt, schützt am
Ende die Falschaussage ([[feedback_probe_unerreichbarer_zustand]]) — die Zeilen
unten haben deshalb genau die Form, die der Snapshot-Job schreibt:
`sensor_key = inv:<id>:zaehlerstand`, ein Wert je Stunde.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.zaehlerstaende import lade_zaehlerstaende, sensor_key_fuer
from backend.tests import factories


async def _anlage(db) -> Anlage:
    return await factories.anlage(db, anlagenname="Testanlage")


async def _zaehler(db, anlage, name, *, angeschafft, stillgelegt=None, aktiv=True):
    inv = Investition(
        anlage_id=anlage.id,
        typ="sonstiges",
        bezeichnung=name,
        anschaffungsdatum=angeschafft,
        stilllegungsdatum=stillgelegt,
        aktiv=aktiv,
        parameter={"kategorie": "zaehler", "zaehler_art": "gas", "zaehler_einheit": "m³"},
    )
    db.add(inv)
    await db.flush()
    return inv


async def _stand(db, anlage, inv, tag: date, wert: float):
    db.add(SensorSnapshot(
        anlage_id=anlage.id,
        sensor_key=sensor_key_fuer(inv.id),
        zeitpunkt=datetime.combine(tag, datetime.min.time()),
        wert_kwh=wert,
        quelle="ha_statistics",
    ))


@pytest.mark.asyncio
async def test_zaehlerwechsel_summe_beider_differenzen(db):
    """**Der Kern:** Über den Wechsel hinweg ist der Verbrauch die Summe beider.

    Alter Zähler 1.000 → 1.200 (200 m³), neuer Zähler 0 → 50 (50 m³).
    Erwartet: 250 m³ — und **keine negative Zahl**, obwohl der Stand von 1.200
    auf 0 zurückspringt. Genau dafür gibt es zwei Geräte statt einer
    Reset-Erkennung.
    """
    a = await _anlage(db)
    alt = await _zaehler(
        db, a, "Gaszähler alt",
        angeschafft=date(2024, 1, 1), stillgelegt=date(2026, 6, 15),
    )
    neu = await _zaehler(db, a, "Gaszähler neu", angeschafft=date(2026, 6, 15))
    await _stand(db, a, alt, date(2026, 1, 1), 1000.0)
    await _stand(db, a, alt, date(2026, 6, 15), 1200.0)
    await _stand(db, a, neu, date(2026, 6, 15), 0.0)
    await _stand(db, a, neu, date(2026, 12, 31), 50.0)
    await db.commit()

    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 1, 1), datetime(2026, 12, 31, 23, 59, 59),
        nur_aktive=False,
    )
    je_name = {f.name: f for f in fenster}
    assert je_name["Gaszähler alt"].differenz == pytest.approx(200.0)
    assert je_name["Gaszähler neu"].differenz == pytest.approx(50.0)
    gesamt = sum(f.differenz for f in fenster if f.differenz is not None)
    assert gesamt == pytest.approx(250.0)
    assert all((f.differenz or 0) >= 0 for f in fenster), (
        "Kein Rücksprung darf als negativer Verbrauch durchschlagen."
    )


@pytest.mark.asyncio
async def test_gegenprobe_aktiv_false_loescht_die_historie(db):
    """⛔ **Der Fallstrick aus §4** — und warum er in die Anleitung gehört.

    Wer den alten Zähler *deaktiviert* statt stillzulegen, verliert seine
    Ablesungen aus **jeder** Sicht: `aktiv=False` heißt laut Datenmodell „wie
    gelöscht, auch nicht historisch". Diese Probe hält den Unterschied fest,
    damit niemand den bequemeren Schalter für gleichwertig hält.
    """
    a = await _anlage(db)
    tot = await _zaehler(
        db, a, "Gaszähler deaktiviert",
        angeschafft=date(2024, 1, 1), aktiv=False,
    )
    await _stand(db, a, tot, date(2026, 1, 1), 1000.0)
    await _stand(db, a, tot, date(2026, 6, 1), 1200.0)
    await db.commit()

    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 1, 1), datetime(2026, 12, 31), nur_aktive=True,
    )
    assert fenster == [], (
        "aktiv=False blendet das Gerät überall aus — die 200 m³ sind weg."
    )


@pytest.mark.asyncio
async def test_stillgelegter_zaehler_bleibt_historisch_sichtbar(db):
    """Die Gegenrichtung: Stilllegen bewahrt, was gemessen wurde.

    Ohne diese Probe wäre die Probe darüber auch dann grün, wenn `nur_aktive`
    schlicht **alles** ausblendete.
    """
    a = await _anlage(db)
    alt = await _zaehler(
        db, a, "Gaszähler alt",
        angeschafft=date(2024, 1, 1), stillgelegt=date(2026, 6, 15),
    )
    await _stand(db, a, alt, date(2026, 1, 1), 1000.0)
    await _stand(db, a, alt, date(2026, 6, 15), 1200.0)
    await db.commit()

    # Historisches Fenster: das Gerät war darin aktiv ⇒ sichtbar.
    hist = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 1, 1), datetime(2026, 6, 30), nur_aktive=True,
    )
    assert [f.name for f in hist] == ["Gaszähler alt"]
    assert hist[0].differenz == pytest.approx(200.0)

    # Laufendes Fenster nach der Stilllegung ⇒ nicht mehr in der Liste.
    aktuell = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 9, 1), datetime(2026, 9, 30), nur_aktive=True,
    )
    assert aktuell == []


@pytest.mark.asyncio
async def test_unvollstaendiges_fenster_sagt_es(db):
    """ADR-002/P4 an der konkreten Zahl.

    Beginnt die Aufzeichnung **im** Fenster, deckt die Differenz nicht den
    ganzen Zeitraum ab. Sie wird trotzdem geliefert — aber mit dem Vermerk,
    statt eine zu kleine Zahl kommentarlos hinzustellen.
    """
    a = await _anlage(db)
    inv = await _zaehler(db, a, "Wasserzähler", angeschafft=date(2026, 1, 1))
    await _stand(db, a, inv, date(2026, 6, 10), 800.0)
    await _stand(db, a, inv, date(2026, 6, 30), 830.0)
    await db.commit()

    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 6, 1), datetime(2026, 6, 30, 23, 59, 59),
    )
    assert fenster[0].differenz == pytest.approx(30.0)
    assert fenster[0].anfang_vollstaendig is False

    # Gegenprobe: liegt ein Stand VOR dem Fenster, gilt er fort und das
    # Fenster ist vollständig.
    await _stand(db, a, inv, date(2026, 5, 31), 795.0)
    await db.commit()
    fenster2 = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 6, 1), datetime(2026, 6, 30, 23, 59, 59),
    )
    assert fenster2[0].anfang_vollstaendig is True
    assert fenster2[0].differenz == pytest.approx(35.0)


@pytest.mark.asyncio
async def test_stand_genau_zum_fensterbeginn_ist_vollstaendig(db):
    """Grenzfall, **an der Dev-Box aufgefallen** — nicht am Schreibtisch.

    Der erste Snapshot lag auf dem 01.08. um 00:00, das Monatsfenster beginnt
    ebenfalls dort. Mit einem strikten `<` galt das Fenster als unvollständig,
    obwohl der Wert genau an seiner Kante gemessen wurde — die Anzeige hätte
    „Teilwert" behauptet, wo nichts fehlte.
    """
    a = await _anlage(db)
    inv = await _zaehler(db, a, "Gaszähler", angeschafft=date(2024, 1, 1))
    await _stand(db, a, inv, date(2026, 8, 1), 12000.0)
    await _stand(db, a, inv, date(2026, 8, 21), 12074.0)
    await db.commit()

    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59),
    )
    assert fenster[0].anfang_vollstaendig is True
    assert fenster[0].stand_anfang == pytest.approx(12000.0)
    assert fenster[0].differenz == pytest.approx(74.0)


@pytest.mark.asyncio
async def test_fehlender_stand_ist_kein_nullverbrauch(db):
    """Ein Zähler ohne jede Messung liefert `None`, nicht 0.

    Er verschwindet auch nicht aus der Liste: „für diesen Zeitraum liegt nichts
    vor" ist eine andere Aussage als „es gibt keinen Zähler".
    """
    a = await _anlage(db)
    await _zaehler(db, a, "Ölzähler", angeschafft=date(2026, 1, 1))
    await db.commit()

    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 6, 1), datetime(2026, 6, 30),
    )
    assert len(fenster) == 1
    assert fenster[0].differenz is None
    assert fenster[0].stand_ende is None


@pytest.mark.asyncio
async def test_zwei_zaehler_werden_nie_summiert(db):
    """Bestandsgröße: Zwei Gaszähler mit 12.345 und 8.900 ergeben nicht 21.245.

    Die Funktion liefert **je Gerät** — das ist keine Bequemlichkeit, sondern
    die Größenart. Diese Probe hält fest, dass nirgends eine Anlagensumme
    entsteht.
    """
    a = await _anlage(db)
    g1 = await _zaehler(db, a, "Gas Haus", angeschafft=date(2024, 1, 1))
    g2 = await _zaehler(db, a, "Gas Werkstatt", angeschafft=date(2024, 1, 1))
    await _stand(db, a, g1, date(2026, 6, 1), 12345.0)
    await _stand(db, a, g2, date(2026, 6, 1), 8900.0)
    await db.commit()

    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 6, 1), datetime(2026, 6, 30),
    )
    staende = sorted(f.stand_ende for f in fenster)
    assert staende == [8900.0, 12345.0]
    assert 21245.0 not in staende
