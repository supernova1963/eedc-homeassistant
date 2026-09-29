"""B7 — kein abgeschlossener Monat kann ohne Wetterwerte bleiben.

**Warum es diesen Job gibt.** Er ist die Bedingung, unter der das Paket „Die
Wetterreihe geradeziehen" freigegeben wurde: *„nur wenn sichergestellt ist,
dass zukünftig kein Monat ohne diese Daten entstehen kann."* Ohne ihn wäre B2
(keine Vormonats-Vorbelegung mehr für Wetterfelder) ein Rückschritt: heute
steht ein **falscher** Wert im Feld, danach stünde **keiner** darin, solange
niemand den Knopf drückt. Die beiden sind eine Stufe, kein Paar.

**Vier Klauseln, jede mit ihrem Grund:**

1. *Der laufende Monat bleibt draußen.* ``fetch_brightsky_month`` fragt nur bis
   gestern und setzt ``tage_gesamt`` dann auf den gestrigen Tag — die Abdeckung
   läse sich als ~100 %, obwohl der Monat halb ist.
2. *Nur Lücken, nie überschreiben.* Das Umlegen einer ganzen Reihe bleibt die
   vom Anwender **angeordnete** Aktion in der Reparatur-Werkbank. Ein
   Hintergrundjob ändert keinen vorhandenen Wert.
3. *Erst DB, dann Netz.* Ohne Lücke kein einziger Abruf — im Normalbetrieb ist
   der Job ein SELECT pro Nacht. Das ist zugleich die Idempotenz-Probe: der
   zweite Lauf findet nichts mehr.
4. *Ein langjähriges Mittel wird nie automatisch geschrieben.* Liefert kein
   messendes Archiv, **bleibt die Lücke** — und der Daten-Checker nennt sie.
   Ein PVGIS-TMY-Wert machte ein schwaches Jahr unsichtbar, also genau den
   Fehler, gegen den dieses Paket gebaut ist.

⭐ **Die Reichweite der Zusage, ehrlich benannt:** „kein Monat ohne Daten" gilt,
solange ein messendes Archiv den Ort erreicht. An 8 DACH-Orten gemessen (Juli
2025): 8 von 8 mit Abdeckung 100 %. Für den Rest ist die Lücke **sichtbar statt
still**, und das ist der Unterschied zu heute.

⚠ **Kein Blick auf die echte Uhr (N-167).** Der Stichtag ist hier eine
Konstante und wird dem Prüfling übergeben — `schliesse_wetter_luecken` nimmt
ihn als Parameter, genau dafür. Eine Probe, die `date.today()` liest, wettet
auf den Tag ihres Laufs; die Suite läuft in drei Zeitzonen, und der Wechsel auf
den Ersten eines Monats verschiebt die ganze Mengenbildung.

Schwesterdateien: ``test_wetter_nachzug_und_checker.py`` (die ANGEORDNETE
Variante desselben Nachzugs, mit Vorschau und Überschreiben) ·
``test_wetterreihe_ein_lineal.py`` (welcher Anbieter gefragt wird) ·
``test_wetterfelder_ohne_historienschaetzung.py`` (warum die Lücke überhaupt
entsteht) · ``test_n426_temperatur_historie.py`` (die Ø-Temperatur allein).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.services.wetter.luecken import (
    monate_mit_luecke,
    schliesse_wetter_luecken,
)

BS_GHI, BS_SONNE, BS_TEMP = 170.9, 233.3, 18.7

#: Der Stichtag der Proben — FEST, nicht `date.today()` (N-167). Er liegt in
#: der Vergangenheit, damit die Monate davor für jeden späteren Lauf
#: abgeschlossen bleiben.
HEUTE = date(2026, 6, 15)


def _drei_vormonate(heute: date) -> list[tuple[int, int]]:
    """Die drei Monate VOR dem laufenden — absteigend aufgebaut, aufsteigend zurück."""
    out: list[tuple[int, int]] = []
    jahr, monat = heute.year, heute.month
    for _ in range(3):
        monat -= 1
        if monat == 0:
            jahr, monat = jahr - 1, 12
        out.append((jahr, monat))
    return sorted(out)


@pytest.fixture
def archiv(monkeypatch):
    """Bright Sky antwortet; die Zahl der Abrufe ist zählbar."""
    abrufe: list[tuple[int, int]] = []

    async def bs(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        abrufe.append((jahr, monat))
        return {
            "globalstrahlung_kwh_m2": BS_GHI, "sonnenstunden": BS_SONNE,
            "durchschnitts_temperatur_c": BS_TEMP,
            "tage_mit_daten": 31, "tage_gesamt": 31,
        }

    monkeypatch.setattr("backend.services.brightsky_service.fetch_brightsky_month", bs)
    return abrufe


@pytest.fixture
def nur_tmy(monkeypatch):
    async def leer(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return None

    async def tmy(latitude, longitude, monat, **kw):  # noqa: ARG001
        return {"globalstrahlung_kwh_m2": 89.9, "sonnenstunden": 232.0}

    monkeypatch.setattr("backend.services.brightsky_service.fetch_brightsky_month", leer)
    monkeypatch.setattr(
        "backend.services.wetter.orchestrator.fetch_open_meteo_archive", leer
    )
    monkeypatch.setattr(
        "backend.services.wetter.orchestrator.fetch_pvgis_tmy_monat", tmy
    )


async def _anlage(db, monate: list[tuple[int, int]], werte: dict | None = None) -> Anlage:
    a = Anlage(
        anlagenname="Lücken", leistung_kwp=10.0,
        latitude=50.896149, longitude=7.533871,
        standort_land="DE", wetter_provider="auto",
    )
    db.add(a)
    await db.flush()
    for jahr, monat in monate:
        db.add(Monatsdaten(
            anlage_id=a.id, jahr=jahr, monat=monat,
            einspeisung_kwh=100.0, netzbezug_kwh=100.0,
            **(werte or {}),
        ))
    await db.flush()
    await db.commit()
    return a


async def _zeilen(db, anlage_id) -> list[Monatsdaten]:
    return list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr, Monatsdaten.monat)
    )).scalars().all())


# ══════════════════════════════════════════════════════════════════════════
# 1 · Drei leere Monate werden gefüllt — und der zweite Lauf fragt niemanden
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_drei_leere_monate_werden_gefuellt(db, archiv):
    """Die Gegenprobe aus der Vorlage, Schritt 1."""
    heute = HEUTE
    a = await _anlage(db, _drei_vormonate(heute))

    ergebnis = await schliesse_wetter_luecken(db, a, HEUTE)
    await db.commit()

    assert ergebnis.monate_gefuellt == 3, ergebnis
    for md in await _zeilen(db, a.id):
        assert md.globalstrahlung_kwh_m2 == pytest.approx(BS_GHI)
        assert md.sonnenstunden == pytest.approx(BS_SONNE)
        assert md.durchschnittstemperatur == pytest.approx(BS_TEMP)
        assert md.source_provenance["sonnenstunden"]["source"] == "external:brightsky"


@pytest.mark.asyncio
async def test_der_zweite_lauf_fragt_niemanden(db, archiv):
    """Erst DB, dann Netz — ohne Lücke kein einziger Abruf.

    Das ist nicht nur Sparsamkeit: ein Job, der jede Nacht jeden Monat neu
    abfragt, wäre bei 39 Monaten 39 Anfragen pro Anlage und Nacht — und der
    Jitter davor macht daraus Stunden.
    """
    heute = HEUTE
    a = await _anlage(db, _drei_vormonate(heute))

    await schliesse_wetter_luecken(db, a, HEUTE)
    await db.commit()
    abrufe_erster_lauf = len(archiv)
    archiv.clear()

    zweiter = await schliesse_wetter_luecken(db, a, HEUTE)

    assert abrufe_erster_lauf == 3
    assert zweiter.monate_mit_luecke == 0, zweiter
    assert zweiter.abrufe == 0
    assert archiv == [], f"Der zweite Lauf hat {len(archiv)} Mal gefragt"


# ══════════════════════════════════════════════════════════════════════════
# 2 · Der laufende Monat bleibt draußen
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lueckenschluss_laesst_den_laufenden_monat_aus(db, archiv):
    heute = HEUTE
    a = await _anlage(db, _drei_vormonate(heute) + [(heute.year, heute.month)])

    ergebnis = await schliesse_wetter_luecken(db, a, HEUTE)
    await db.commit()

    assert ergebnis.monate_mit_luecke == 3, (
        f"{ergebnis.monate_mit_luecke} Monate in der Lückenmenge — der laufende "
        "gehört nicht dazu: die Archive liefern ihn noch nicht vollständig."
    )
    laufend = [
        md for md in await _zeilen(db, a.id)
        if (md.jahr, md.monat) == (heute.year, heute.month)
    ][0]
    assert laufend.globalstrahlung_kwh_m2 is None
    assert archiv == [] or (heute.year, heute.month) not in archiv


@pytest.mark.asyncio
async def test_die_menge_ist_ohne_netz_bestimmbar(db):
    """`monate_mit_luecke` ist die Vorprüfung — sie fragt keinen Anbieter."""
    heute = HEUTE
    a = await _anlage(db, _drei_vormonate(heute))

    offen = await monate_mit_luecke(db, a.id, HEUTE)

    assert len(offen) == 3


# ══════════════════════════════════════════════════════════════════════════
# 3 · Was dasteht, bleibt stehen
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lueckenschluss_aendert_nichts_vorhandenes(db, archiv):
    """Ein von Hand gesetzter Wert bleibt unverändert — auch ein „falscher".

    ⛔ Der Hintergrundjob ist kein Heiler-Knopf. Wer seine Reihe umlegen will,
    ordnet das in der Reparatur-Werkbank an und sieht vorher, was ersetzt wird.
    """
    heute = HEUTE
    jahr, monat = _drei_vormonate(heute)[-1]
    a = await _anlage(
        db, [(jahr, monat)],
        werte={"globalstrahlung_kwh_m2": 216.8, "sonnenstunden": 159.2},
    )

    ergebnis = await schliesse_wetter_luecken(db, a, HEUTE)
    await db.commit()

    md = (await _zeilen(db, a.id))[0]
    assert md.globalstrahlung_kwh_m2 == pytest.approx(216.8)
    assert md.sonnenstunden == pytest.approx(159.2)
    # Die LÜCKE desselben Monats wird trotzdem geschlossen — genau das ist der
    # Unterschied zwischen „nur Lücken" und „gar nichts".
    assert md.durchschnittstemperatur == pytest.approx(BS_TEMP)
    assert ergebnis.felder_gefuellt == 1


# ══════════════════════════════════════════════════════════════════════════
# 4 · Ein langjähriges Mittel wird nie automatisch geschrieben
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_kein_tmy_wert_im_hintergrund(db, nur_tmy):
    """Die Lücke bleibt sichtbar, statt mit einem Durchschnitt zugedeckt zu werden."""
    heute = HEUTE
    a = await _anlage(db, _drei_vormonate(heute))

    ergebnis = await schliesse_wetter_luecken(db, a, HEUTE)
    await db.commit()

    for md in await _zeilen(db, a.id):
        assert md.globalstrahlung_kwh_m2 is None, (
            f"TMY-Wert {md.globalstrahlung_kwh_m2} wurde im Hintergrund "
            "festgeschrieben — ein Mittel über viele Jahre macht ein schwaches "
            "Jahr unsichtbar."
        )
    assert ergebnis.felder_gefuellt == 0
    assert len(ergebnis.ohne_messende_quelle) == 3


@pytest.mark.asyncio
async def test_der_job_ist_taeglich_registriert():
    """Nicht am Monatswechsel — dort liefert kein Archiv den eben zu Ende gegangenen Monat.

    Der vorhandene Monats-Job läuft am 1. um 00:01, eine Minute nach Monatsende;
    Open-Meteo hinkt 2–5 Tage nach (N-388). Eine Probe darauf, weil genau diese
    Wahl die Zusage trägt und ein späterer Umbau sie still kippen könnte.
    """
    import inspect

    from backend.services import scheduler as sched

    quelle = inspect.getsource(sched.EEDCScheduler.start)
    assert 'id="wetter_luecken"' in quelle
    block = quelle.split('wetter_luecken_job,')[1].split(')')[0]
    assert "CronTrigger(hour=" in block and "day=" not in block, block
