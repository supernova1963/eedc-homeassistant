"""Die Ø-Monatstemperatur der Wetter-Route folgt der Vorrangkette (**N-426**).

**Was hier auf dem Spiel steht.** Das Monatsformular hat einen Knopf „Auto-Fill",
der `GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}` ruft. Bis v4.0.44 füllte
er zwei von drei Wetterfeldern; die Ø-Temperatur blieb leer, während der
Feld-Hinweis wörtlich versprach, sie werde „automatisch von Open-Meteo geholt".
Der Entscheid vom 11.09.2026 lautet: das Feld wird wieder gefüllt — aber aus
**derselben Vorrangkette**, mit der die Temperaturlinie des Wärme/Klima-Verlaufs
rechnet, und das Archiv ist nur ihre letzte Stufe.

**Die Kette, und warum sie so herum steht:**

1. **Stundenmittel** (`TagesEnergieProfil.temperatur_c`) — die eigene Messung am
   Standort der Anlage.
2. **Tages-Min/Max** (`TagesZusammenfassung`) — die Näherung `(min+max)/2`, für
   Tage ohne Stundenzeilen. Sie überlebt länger als Stufe 1: die Löschfrist bis
   4.3.1 beschnitt nur `TagesEnergieProfil` (seit Nachtrag G keine Löschfrist mehr).
3. **Open-Meteo / Bright Sky** — das Archiv einer Wetterstation in der Nähe.

⛔ **Was NICHT in der Kette steht, obwohl der Dienst es könnte:** die dritte
Stufe von `lade_monatsmittel_temperatur`, der gepflegte
`Monatsdaten.durchschnittstemperatur`. Das ist genau das Feld, das diese Antwort
füllen soll — gäbe die Route sie mit, bestätigte das Auto-Fill dem Anwender
seinen eigenen Wert als „gemessen". `test_gepflegter_monatswert_fliesst_nicht_
zurueck` hält das fest.

⚠ **Jede Klausel steht hier einzeln**, weil sie sich decken können: an einer
echten Anlage tragen Stufe 1 und Stufe 2 meist dieselben Tage (in
`devbox-r27-demo.db` alle 187), und dann entscheidet die Vorrangfrage nie. Nur
eine gestellte Fixture, in der die Stufen **verschiedene** Zahlen liefern, misst
sie wirklich.

Schwesterdateien: ``test_mitteltemperatur.py`` (der Dienst hinter Stufe 1+2 und
die Abgrenzung zu den Heizgradtagen — der eigentliche Symmetriepartner) und
``test_wetter_provider_land_386.py`` (dieselbe Route, andere Frage: welcher
Provider die Strahlung liefern darf).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.wetter import get_wetter_monat
from backend.models import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.mitteltemperatur import lade_monatsmittel_temperatur

#: Was der Wetterdienst im Test liefert. Bewusst eine Zahl, die keiner der
#: gemessenen Fixture-Werte trifft — sonst wäre nicht unterscheidbar, welche
#: Stufe geantwortet hat.
ARCHIV_TEMPERATUR = 9.9

#: Die gemessenen Fixture-Werte, ebenfalls paarweise verschieden.
STUNDEN_MITTEL = 5.0
MINMAX_MITTEL = 1.0


async def _anlage(db, land: str = "AT") -> Anlage:
    """Anlage mit Koordinaten. ``AT`` hält Bright Sky aus der Kette (#386) —
    die Probe will genau EINEN Archiv-Provider messen, nicht die Auswahl."""
    a = Anlage(
        anlagenname="N426",
        leistung_kwp=10.0,
        installationsdatum=date(2024, 1, 1),
        latitude=47.94112,
        longitude=13.593,
        standort_land=land,
    )
    db.add(a)
    await db.flush()
    return a


async def _stunden(db, anlage_id: int, tag: date, temps: list[float]) -> None:
    for h, t in enumerate(temps):
        db.add(TagesEnergieProfil(anlage_id=anlage_id, datum=tag, stunde=h, temperatur_c=t))


async def _minmax(db, anlage_id: int, tag: date, tmin: float, tmax: float) -> None:
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=tag, temperatur_min_c=tmin, temperatur_max_c=tmax,
    ))


@pytest.fixture
def archiv(monkeypatch):
    """Open-Meteo antwortet mit {ARCHIV_TEMPERATUR}, ohne Netz.

    Angesetzt wird an `fetch_open_meteo_archive` — der UNTERSTEN Ebene. Damit
    laufen Orchestrator und Route echt; ein Mock der Route-Ebene hätte genau
    die Vorrang-Entscheidung wegmokiert, um die es geht.
    """
    async def fake(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return {
            "globalstrahlung_kwh_m2": 100.0,
            "sonnenstunden": 120.0,
            "durchschnitts_temperatur_c": ARCHIV_TEMPERATUR,
            "tage_mit_daten": 31,
            "tage_gesamt": 31,
        }

    monkeypatch.setattr("backend.services.wetter.orchestrator.fetch_open_meteo_archive", fake)
    return fake


@pytest.fixture
def kein_archiv(monkeypatch):
    """Kein Wetterdienst antwortet — für den PVGIS-/Defaults-Weg.

    ⚠ Bright Sky steht auch bei ``provider="open-meteo"`` als zweiter in der
    Kette und muss mit weggenommen werden; sonst versucht der Lauf einen
    echten DNS-Zugriff, den die conftest blockt und namentlich protokolliert.
    Es wird an `brightsky_service` angesetzt, weil der Orchestrator die
    Funktion erst im Aufruf importiert.
    """
    async def leer(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return None

    async def kein_pvgis(latitude, longitude, monat, **kw):  # noqa: ARG001
        return None

    monkeypatch.setattr("backend.services.wetter.orchestrator.fetch_open_meteo_archive", leer)
    monkeypatch.setattr("backend.services.wetter.orchestrator.fetch_pvgis_tmy_monat", kein_pvgis)
    monkeypatch.setattr("backend.services.brightsky_service.fetch_brightsky_month", leer)


async def _hole(db, anlage_id: int, jahr: int = 2025, monat: int = 1):
    """Die Route, direkt gerufen — Einzelwerte aus IHRER Antwort."""
    return await get_wetter_monat(
        anlage_id=anlage_id, jahr=jahr, monat=monat, provider="open-meteo", db=db,
    )


# ── Klausel 1: Stufe 1 schlägt das Archiv ───────────────────────────────────

@pytest.mark.asyncio
async def test_stundenmittel_schlaegt_das_archiv(db, archiv):
    """Die eigene Stundenmessung gewinnt gegen Open-Meteo."""
    a = await _anlage(db)
    # Vier Stundenwerte, Mittel exakt 5,0.
    await _stunden(db, a.id, date(2025, 1, 15), [4.0, 4.0, 6.0, 6.0])
    await db.commit()

    antwort = await _hole(db, a.id)

    assert antwort.durchschnittstemperatur_c == pytest.approx(STUNDEN_MITTEL)
    assert antwort.temperatur_herkunft == "messung"
    # Gegenprobe, dass die Fixture überhaupt greifen KONNTE: die Strahlung
    # kommt weiter vom Archiv — nur die Temperatur wurde ersetzt.
    assert antwort.datenquelle == "open-meteo"
    assert antwort.globalstrahlung_kwh_m2 == pytest.approx(100.0)


# ── Klausel 2: Stufe 2 schlägt das Archiv ───────────────────────────────────

@pytest.mark.asyncio
async def test_min_max_naeherung_schlaegt_das_archiv(db, archiv):
    """Ohne Stundenzeilen trägt die Tages-Näherung — immer noch vor dem Archiv.

    Der Fall älterer Monate: `TagesEnergieProfil` ist nach zwei Jahren weg,
    `TagesZusammenfassung` nie.
    """
    a = await _anlage(db)
    await _minmax(db, a.id, date(2025, 1, 15), -1.0, 3.0)   # (−1 + 3) / 2 = 1,0
    await db.commit()

    antwort = await _hole(db, a.id)

    assert antwort.durchschnittstemperatur_c == pytest.approx(MINMAX_MITTEL)
    assert antwort.temperatur_herkunft == "messung"


# ── Klausel 3: Stufe 1 schlägt Stufe 2 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_stundenmittel_schlaegt_die_min_max_naeherung(db, archiv):
    """Beide Messstufen am selben Tag: das echte Mittel gewinnt.

    Diese Klausel deckt sich an einer echten Anlage fast immer mit Klausel 1
    (dieselben Tage tragen beides) — sie braucht die gestellte Fixture, in der
    die zwei Stufen auseinanderlaufen.
    """
    a = await _anlage(db)
    tag = date(2025, 1, 15)
    await _stunden(db, a.id, tag, [4.0, 4.0, 6.0, 6.0])     # 5,0
    await _minmax(db, a.id, tag, -1.0, 3.0)                 # 1,0 — darf nicht gewinnen
    await db.commit()

    antwort = await _hole(db, a.id)

    assert antwort.durchschnittstemperatur_c == pytest.approx(STUNDEN_MITTEL)
    assert antwort.durchschnittstemperatur_c != pytest.approx(MINMAX_MITTEL)
    assert antwort.temperatur_herkunft == "messung"


# ── Klausel 4: ohne Messung antwortet das Archiv ────────────────────────────

@pytest.mark.asyncio
async def test_ohne_messreihe_antwortet_das_archiv(db, archiv):
    """Die letzte Stufe — und sie sagt es auch (`temperatur_herkunft`)."""
    a = await _anlage(db)
    await db.commit()

    antwort = await _hole(db, a.id)

    assert antwort.durchschnittstemperatur_c == pytest.approx(ARCHIV_TEMPERATUR)
    assert antwort.temperatur_herkunft == "open-meteo"


# ── Klausel 5: die dritte Stufe fließt NICHT zurück ─────────────────────────

@pytest.mark.asyncio
async def test_gepflegter_monatswert_fliesst_nicht_zurueck(db, archiv):
    """`Monatsdaten.durchschnittstemperatur` ist kein Eingang dieser Antwort.

    Sonst füllte das Auto-Fill das Feld aus sich selbst und meldete den
    getippten Wert als „messung" zurück.
    """
    a = await _anlage(db)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=1, durchschnittstemperatur=42.0))
    await db.commit()

    antwort = await _hole(db, a.id)

    assert antwort.durchschnittstemperatur_c != pytest.approx(42.0)
    assert antwort.durchschnittstemperatur_c == pytest.approx(ARCHIV_TEMPERATUR)
    assert antwort.temperatur_herkunft == "open-meteo"


# ── Klausel 6: die Route fragt genau IHREN Monat ────────────────────────────

@pytest.mark.asyncio
async def test_nur_der_angefragte_monat_zaehlt(db, archiv):
    """Eine Messreihe im Februar darf die Januar-Antwort nicht tragen."""
    a = await _anlage(db)
    await _stunden(db, a.id, date(2025, 2, 15), [4.0, 4.0, 6.0, 6.0])   # Februar
    await db.commit()

    januar = await _hole(db, a.id, jahr=2025, monat=1)
    februar = await _hole(db, a.id, jahr=2025, monat=2)

    assert januar.durchschnittstemperatur_c == pytest.approx(ARCHIV_TEMPERATUR)
    assert januar.temperatur_herkunft == "open-meteo"
    # Gegenrichtung: im Februar SELBST muss die Messung gewinnen, sonst
    # bewiese die Probe nur, dass gar nichts gefunden wird.
    assert februar.durchschnittstemperatur_c == pytest.approx(STUNDEN_MITTEL)
    assert februar.temperatur_herkunft == "messung"


# ── Klausel 7: keine Herkunft ohne Wert ─────────────────────────────────────

@pytest.mark.asyncio
async def test_ohne_temperatur_keine_herkunft(db, kein_archiv):
    """Fällt die Route auf statische Defaults durch, gibt es keine Temperatur —
    und dann darf auch keine Herkunft behauptet werden.

    Der Fall ist nicht konstruiert: der PVGIS-/Defaults-Zweig führt gar keine
    Temperatur, und für den LAUFENDEN Monat ist er der einzige Weg.
    """
    a = await _anlage(db)
    await db.commit()

    antwort = await _hole(db, a.id)

    assert antwort.datenquelle == "defaults"
    assert antwort.durchschnittstemperatur_c is None
    assert antwort.temperatur_herkunft is None


@pytest.mark.asyncio
async def test_archiv_ohne_temperaturspalte_behauptet_keine_herkunft(db, monkeypatch):
    """Der Provider liefert Strahlung, aber keine Temperatur — beides bleibt leer.

    ⚠ **Diese Klausel gibt es, weil ein Sprengsatz still blieb** (13.09.2026):
    Der Test darüber geht den Defaults-Weg, und dort wird die Herkunft gar
    nicht erst angefasst. Die Bedingung in `_mit_temperatur_herkunft` war damit
    ungedeckt. Der Fall ist echt — `fetch_open_meteo_archive` liefert
    `durchschnitts_temperatur_c = None`, wenn kein einziger Tag des Monats
    einen `temperature_2m_mean` trägt.
    """
    async def nur_strahlung(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return {
            "globalstrahlung_kwh_m2": 100.0,
            "sonnenstunden": 120.0,
            "durchschnitts_temperatur_c": None,
            "tage_mit_daten": 31,
            "tage_gesamt": 31,
        }

    monkeypatch.setattr(
        "backend.services.wetter.orchestrator.fetch_open_meteo_archive", nur_strahlung
    )
    a = await _anlage(db)
    await db.commit()

    antwort = await _hole(db, a.id)

    # Vorbedingung: der Provider hat sehr wohl geantwortet — sonst prüfte die
    # Klausel bloß den Defaults-Weg noch einmal.
    assert antwort.datenquelle == "open-meteo"
    assert antwort.globalstrahlung_kwh_m2 == pytest.approx(100.0)
    assert antwort.durchschnittstemperatur_c is None
    assert antwort.temperatur_herkunft is None


# ── Klausel 8: das Fenster gilt für BEIDE Eingänge des Dienstes ─────────────

@pytest.mark.asyncio
async def test_fenster_filtert_auch_die_gepflegten_monatswerte(db):
    """`von`/`bis` grenzen Tagesreihe **und** Stufe 3 ein.

    Ein Fenster, das nur die halbe Funktion beträfe, wäre eine Falle für den
    nächsten Aufrufer: er fragte einen Monat an und bekäme fremde zurück.
    """
    a = await _anlage(db)
    await db.commit()

    ergebnis = await lade_monatsmittel_temperatur(
        db,
        a.id,
        gepflegt_je_monat={(2025, 1): 3.0, (2025, 7): 20.0},
        von=date(2025, 1, 1),
        bis=date(2025, 1, 31),
    )

    assert ergebnis == {(2025, 1): 3.0}


@pytest.mark.asyncio
async def test_fenster_filtert_auch_die_tagesreihe(db):
    """`von`/`bis` erreichen die Tagesreihe — nicht nur die gepflegten Werte.

    ⚠ **Diese Klausel gibt es, weil ein Sprengsatz still blieb** (13.09.2026):
    Nimmt man der ROUTE ihr Fenster weg, bleibt ihre Antwort trotzdem richtig —
    sie greift mit `.get((jahr, monat))` ohnehin nur ihren einen Monat heraus.
    Über die Route ist das Fenster also gar nicht zu widerlegen; die Wirkung
    liegt am Dienst, und hier steht sie.
    """
    a = await _anlage(db)
    await _stunden(db, a.id, date(2025, 1, 15), [4.0, 4.0, 6.0, 6.0])   # 5,0
    await _stunden(db, a.id, date(2025, 7, 15), [19.0, 21.0])           # 20,0
    await db.commit()

    nur_januar = await lade_monatsmittel_temperatur(
        db, a.id, von=date(2025, 1, 1), bis=date(2025, 1, 31),
    )

    assert nur_januar == {(2025, 1): 5.0}


@pytest.mark.asyncio
async def test_ohne_fenster_bleibt_die_ganze_historie(db):
    """Die Gegenrichtung — der Bestandsaufrufer hat kein Fenster und darf
    dadurch nichts verlieren (`routes/monatsdaten.py`)."""
    a = await _anlage(db)
    await _stunden(db, a.id, date(2025, 1, 15), [4.0, 4.0, 6.0, 6.0])
    await _stunden(db, a.id, date(2025, 7, 15), [19.0, 21.0])
    await db.commit()

    ergebnis = await lade_monatsmittel_temperatur(db, a.id)

    assert ergebnis == {(2025, 1): 5.0, (2025, 7): 20.0}


# ── Klausel 9: die Route liest nur IHREN Monat aus der Datenbank ────────────

@pytest.mark.asyncio
async def test_route_laedt_nur_die_tage_ihres_monats(db, archiv, monkeypatch):
    """Ein Auto-Fill-Klick zieht nicht die halbe Historie durch den Speicher.

    ⚠ **Was diese Probe ist und was nicht.** Sie misst *Aufwand*, nicht
    *Ergebnis* — und sie steht hier, weil das Ergebnis das Fenster nicht
    beweisen kann (siehe `test_fenster_filtert_auch_die_tagesreihe`). Gemessen
    wird die WIRKUNG, nicht das Argument: wie viele Tage die Kette wirklich
    geladen hat. Ohne Fenster wären es bei einer Anlage mit drei Jahren
    Stundenwerten über tausend Tage statt der 28–31 des Monats.
    """
    a = await _anlage(db)
    for monat in (1, 2, 3):
        await _stunden(db, a.id, date(2025, monat, 15), [4.0, 6.0])
    await db.commit()

    import backend.services.mitteltemperatur as mt

    geladen: list[int] = []
    echt = mt.lade_tagesmittel_temperatur

    async def spion(*args, **kw):
        ergebnis = await echt(*args, **kw)
        geladen.append(len(ergebnis))
        return ergebnis

    monkeypatch.setattr(mt, "lade_tagesmittel_temperatur", spion)

    antwort = await _hole(db, a.id, jahr=2025, monat=2)

    # Vorbedingung: die Probe hätte sonst nichts zu sehen.
    assert geladen, "die Route hat die Kette gar nicht gerufen"
    assert geladen == [1], f"drei Monate liegen da, geladen wurden {geladen[0]} Tage"
    assert antwort.temperatur_herkunft == "messung"
