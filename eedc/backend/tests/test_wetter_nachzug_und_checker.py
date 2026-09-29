"""B4b/B4c — die Kategorie trägt ihre Klasse, und der Nachzug zieht die Reihe gerade.

**Was hier geprüft wird** (Paket „Die Wetterreihe geradeziehen", #395 Punkt 1):

* die Daten-Checker-Kategorie ``wetterwert_fehlt`` meldet jetzt **alle drei**
  Wetterwerte — und zusätzlich, wenn eine Reihe aus zwei Quellen zusammengesetzt
  ist. Ihr eigener Kommentar hat das seit N-426 angekündigt: *„Der Name nennt
  die Klasse, nicht das eine Feld … heute trägt die Kategorie nur den ersten,
  weil nur für ihn eine Quelle ohne Netzabruf existiert."*
* die Reparatur-Operation ``WETTER_BACKFILL`` holt alle **abgeschlossenen**
  Monate von der an der Anlage gewählten Quelle.

**Die vier Klauseln des Nachzugs, jede mit ihrem Grund:**

1. *Der laufende Monat bleibt draußen.* ``fetch_brightsky_month`` fragt nur bis
   gestern und setzt ``tage_gesamt`` dann auf den *gestrigen* Tag — die
   Abdeckung läse sich als ~100 %, obwohl der Monat halb ist. Und weil der
   Nachzug überschreibt, stünde die halbe Summe danach fest.
2. *Er ersetzt auch ``manual:form``.* Genau diese Werte sind das Problem: die
   Vormonats-Vorbelegung hat sie gesetzt, ohne dass jemand sie getippt hätte.
   ``benutzer_override=True`` ist der im Code vorgesehene Weg dafür — er behält
   die echte Quelle, statt ``repair`` zu stempeln.
3. *Ein langjähriges Mittel wird nie geschrieben.* Antwortet nur PVGIS-TMY oder
   die statischen Defaults, bleibt der Monat unberührt und wird gezählt. Ein
   Mittel über viele Jahre machte ein schwaches Jahr unsichtbar — genau der
   Fehler, gegen den dieser Nachzug gebaut ist.
4. *Die Vorschau zählt dieselbe Menge, die der Lauf schreibt*, und sagt vorher,
   wie viele Monate **ersetzt** werden.

⭐ **Die vierte Checker-Zeile ist die, die den Bestand überhaupt erreicht.** An
einer echten Anlage nachgemessen (39 Monate): Strahlung und Sonnenstunden
fehlten in **0** Monaten, und **kein einziger** Monat trug ein Anbieter-Label.
Zeile 2 schwieg (Werte sind da), Zeile 3 schwieg (nichts zu vergleichen) — die
Reihe stand weiterhin auf zwei Linealen, das Werkzeug lag bereit, und nichts
sagte es dem Anwender. Zeile 3b schließt genau diese Lage, **ohne zu behaupten,
die Reihe sei gemischt**: sie sagt, dass es sich nicht mehr sagen lässt.

⚠ **Kein Blick auf die echte Uhr (N-167).** Der Stichtag ist eine Konstante und
wird dem Prüfling gestellt. Eine Probe, die `date.today()` liest, wettet auf den
Tag ihres Laufs — und genau hier hinge die ganze Mengenbildung daran: am Ersten
eines Monats um Mitternacht könnten Probe und Prüfling zwei verschiedene
„laufende Monate" meinen, und die Probe wäre ohne Code-Änderung rot.

Schwesterdateien: ``test_wetter_lueckenschluss.py`` (dasselbe Nachziehen als
nächtlicher Job — nur Lücken, kein Überschreiben) ·
``test_wetterreihe_ein_lineal.py`` (welcher Anbieter gefragt wird und welches
Label er hinterlässt) · ``test_n426_temperatur_historie.py`` (die erste Zeile
derselben Checker-Kategorie).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _execute_wetter_backfill,
    _plan_wetter_backfill,
)

KAT = "wetterwert_fehlt"

#: Der Stichtag der Proben — FEST, nicht `date.today()` (N-167). Er liegt in der
#: Vergangenheit, damit die Monate davor für jeden späteren Lauf abgeschlossen
#: bleiben.
HEUTE = date(2026, 6, 15)


class _FestesHeute(date):
    """`date` mit gestelltem `today()` — sonst entscheidet die Uhr des Laufs."""

    @classmethod
    def today(cls) -> date:
        return HEUTE


@pytest.fixture(autouse=True)
def _gestellter_stichtag(monkeypatch):
    """Beide Stellen, die „ist dieser Monat abgeschlossen?" fragen.

    Der Nachzug (`repair_orchestrator`) und die Checker-Zeilen
    (`daten_checker.monatsdaten`) haben keinen Parameter dafür — der Stichtag
    ist dort kein fachlicher Eingang, sondern schlicht „jetzt". Gestellt wird
    er deshalb hier, statt die Produktivsignatur um ein Testargument zu
    erweitern.
    """
    monkeypatch.setattr("backend.services.repair_orchestrator.date", _FestesHeute)
    monkeypatch.setattr("backend.services.daten_checker.monatsdaten.date", _FestesHeute)

BS_GHI, BS_SONNE, BS_TEMP = 170.9, 233.3, 18.7
OM_GHI, OM_SONNE, OM_TEMP = 198.5, 415.0, 19.6


def _vormonat(heute: date) -> tuple[int, int]:
    return (heute.year - 1, 12) if heute.month == 1 else (heute.year, heute.month - 1)


def _antwort(ghi, sonne, temp, tage=31):
    return {
        "globalstrahlung_kwh_m2": ghi, "sonnenstunden": sonne,
        "durchschnitts_temperatur_c": temp,
        "tage_mit_daten": tage, "tage_gesamt": 31,
    }


@pytest.fixture
def brightsky(monkeypatch):
    async def bs(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return _antwort(BS_GHI, BS_SONNE, BS_TEMP)

    async def om(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return _antwort(OM_GHI, OM_SONNE, OM_TEMP)

    monkeypatch.setattr("backend.services.brightsky_service.fetch_brightsky_month", bs)
    monkeypatch.setattr(
        "backend.services.wetter.orchestrator.fetch_open_meteo_archive", om
    )


@pytest.fixture
def nur_tmy(monkeypatch):
    """Kein messendes Archiv antwortet — nur das langjährige Mittel."""

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


async def _anlage(db, monate: list[tuple[int, int]], *, provider="auto",
                  werte: dict | None = None, provenance: dict | None = None) -> Anlage:
    a = Anlage(
        anlagenname="Nachzug", leistung_kwp=10.0,
        latitude=50.896149, longitude=7.533871,
        standort_land="DE", wetter_provider=provider,
    )
    db.add(a)
    await db.flush()
    for jahr, monat in monate:
        db.add(Monatsdaten(
            anlage_id=a.id, jahr=jahr, monat=monat,
            einspeisung_kwh=100.0, netzbezug_kwh=100.0,
            source_provenance=dict(provenance) if provenance else None,
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


def _req(anlage_id):
    return RepairOperationRequest(
        anlage_id=anlage_id, operation=RepairOperationType.WETTER_BACKFILL, params={}
    )


# ══════════════════════════════════════════════════════════════════════════
# 1 · Der Nachzug lässt den laufenden Monat aus
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_nachzug_laesst_den_laufenden_monat_aus(db, brightsky):
    """Ein halber Monat, als ganzer festgeschrieben, ist eine Falschaussage."""
    heute = HEUTE
    a = await _anlage(db, [_vormonat(heute), (heute.year, heute.month)])

    summary = await _execute_wetter_backfill(_req(a.id), db)

    assert summary["monate_gesamt"] == 1, (
        f"Der Nachzug hat {summary['monate_gesamt']} Monate genommen — der "
        "laufende gehört nicht dazu."
    )
    zeilen = await _zeilen(db, a.id)
    laufend = [z for z in zeilen if (z.jahr, z.monat) == (heute.year, heute.month)][0]
    assert laufend.globalstrahlung_kwh_m2 is None
    assert laufend.sonnenstunden is None


@pytest.mark.asyncio
async def test_die_vorschau_zaehlt_dieselbe_menge(db, brightsky):
    """Eine Vorschau, die mehr verspricht als der Lauf tut, ist ein Versprechen."""
    heute = HEUTE
    a = await _anlage(db, [_vormonat(heute), (heute.year, heute.month)])

    estimated, _warnungen, _preview = await _plan_wetter_backfill(_req(a.id), db)
    summary = await _execute_wetter_backfill(_req(a.id), db)

    assert estimated["monate_gesamt"] == summary["monate_gesamt"]


# ══════════════════════════════════════════════════════════════════════════
# 2 · Der Nachzug ersetzt einen `manual:form`-Wert
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_nachzug_ersetzt_einen_manual_form_wert(db, brightsky):
    """Der Stempel steht auf einem Wert, den niemand getippt hat.

    Die Vormonats-Vorbelegung setzte ihn, und ``manual:form`` ist gegen jede
    externe Quelle verriegelt. Ohne ``benutzer_override`` prallte der Nachzug
    genau an den Werten ab, für die es ihn gibt.
    """
    heute = HEUTE
    jahr, monat = _vormonat(heute)
    a = await _anlage(
        db, [(jahr, monat)],
        werte={"globalstrahlung_kwh_m2": 216.8, "sonnenstunden": 159.2},
        provenance={
            "globalstrahlung_kwh_m2": {"source": "manual:form", "writer": "form"},
            "sonnenstunden": {"source": "manual:form", "writer": "form"},
        },
    )

    await _execute_wetter_backfill(_req(a.id), db)

    md = (await _zeilen(db, a.id))[0]
    assert md.sonnenstunden == pytest.approx(BS_SONNE), (
        f"Der Wert steht noch auf {md.sonnenstunden} — der Nachzug ist an "
        "`manual:form` abgeprallt."
    )
    assert md.source_provenance["sonnenstunden"]["source"] == "external:brightsky", (
        "Nach dem Nachzug muss die ECHTE Quelle dastehen, nicht `repair` — "
        "sonst prallte der nächste reguläre Schreiber an Stufe 0 ab."
    )


@pytest.mark.asyncio
async def test_die_vorschau_sagt_vorher_was_ersetzt_wird(db, brightsky):
    heute = HEUTE
    jahr, monat = _vormonat(heute)
    a = await _anlage(
        db, [(jahr, monat)],
        werte={"globalstrahlung_kwh_m2": 216.8, "sonnenstunden": 159.2},
    )

    estimated, warnungen, _preview = await _plan_wetter_backfill(_req(a.id), db)

    assert estimated["monate_mit_werten"] == 1
    assert any("ERSETZT" in w for w in warnungen), warnungen


# ══════════════════════════════════════════════════════════════════════════
# 3 · Ein langjähriges Mittel wird nie geschrieben
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ein_langjaehriges_mittel_wird_nicht_geschrieben(db, nur_tmy):
    """PVGIS-TMY ist die letzte Stufe des MANUELLEN Knopfs, nicht des Nachzugs."""
    heute = HEUTE
    a = await _anlage(db, [_vormonat(heute)])

    summary = await _execute_wetter_backfill(_req(a.id), db)

    md = (await _zeilen(db, a.id))[0]
    assert md.globalstrahlung_kwh_m2 is None, (
        f"TMY-Wert {md.globalstrahlung_kwh_m2} wurde festgeschrieben — ein "
        "Mittel über viele Jahre macht ein schwaches Jahr unsichtbar."
    )
    assert summary["monate_ohne_messende_quelle"] == 1
    assert summary["felder_geschrieben"] == 0


# ══════════════════════════════════════════════════════════════════════════
# 4 · Die Checker-Kategorie trägt alle drei Felder
# ══════════════════════════════════════════════════════════════════════════


async def _befunde(db, anlage_id):
    result = await DatenChecker(db).check_anlage(anlage_id)
    return [e for e in result.ergebnisse if e.kategorie == KAT]


@pytest.mark.asyncio
async def test_checker_meldet_fehlende_strahlungswerte(db):
    """Bis hierher hat kein Checker diese beiden Felder überhaupt gesehen."""
    heute = HEUTE
    a = await _anlage(db, [_vormonat(heute)])

    zeilen = [
        e for e in await _befunde(db, a.id)
        if "Globalstrahlung oder Sonnenstunden" in e.meldung
    ]

    assert zeilen, [e.meldung for e in await _befunde(db, a.id)]
    e = zeilen[0]
    assert "Wetterreihe nachziehen" in e.details
    # ⛔ Kein Inline-Knopf: der Nachzug ERSETZT vorhandene Werte, und die
    # Vorschau muss vorher sagen, wie viele. Die Zeile führt zur Werkbank.
    assert e.action_kind is None, e.action_kind
    assert e.link


@pytest.mark.asyncio
async def test_checker_zaehlt_den_laufenden_monat_nicht_als_luecke(db):
    """Eine Zeile, die eine Lücke nennt, für die es keinen Weg gibt, ist Ballast."""
    heute = HEUTE
    a = await _anlage(db, [(heute.year, heute.month)])

    zeilen = [
        e for e in await _befunde(db, a.id)
        if "Globalstrahlung oder Sonnenstunden" in e.meldung
    ]

    assert not zeilen, [e.meldung for e in zeilen]


@pytest.mark.asyncio
async def test_checker_meldet_eine_gemischte_reihe(db):
    """Zwei Anbieter in einer Reihe — die Zahlen liegen um Faktor 1,6–2,0 auseinander."""
    heute = HEUTE
    jahr, monat = _vormonat(heute)
    a = await _anlage(
        db, [(jahr, monat)], provider="brightsky",
        werte={"globalstrahlung_kwh_m2": OM_GHI, "sonnenstunden": OM_SONNE,
               "durchschnittstemperatur": OM_TEMP},
        provenance={
            "sonnenstunden": {"source": "external:openmeteo", "writer": "x"},
        },
    )

    zeilen = [
        e for e in await _befunde(db, a.id)
        if "andere" in e.meldung
    ]

    assert zeilen, [e.meldung for e in await _befunde(db, a.id)]
    e = zeilen[0]
    assert "1 Monat(e)" in e.meldung
    assert "Open-Meteo" in e.details and "Bright Sky" in e.details
    assert e.action_kind is None, e.action_kind


@pytest.mark.asyncio
async def test_eine_einheitliche_reihe_wird_nicht_gemeldet(db):
    """Gegenrichtung — sonst meldete die Zeile jede Anlage."""
    heute = HEUTE
    jahr, monat = _vormonat(heute)
    a = await _anlage(
        db, [(jahr, monat)], provider="brightsky",
        werte={"globalstrahlung_kwh_m2": BS_GHI, "sonnenstunden": BS_SONNE,
               "durchschnittstemperatur": BS_TEMP},
        provenance={
            "globalstrahlung_kwh_m2": {"source": "external:brightsky", "writer": "x"},
            "sonnenstunden": {"source": "external:brightsky", "writer": "x"},
            "durchschnittstemperatur": {"source": "external:brightsky", "writer": "x"},
        },
    )

    zeilen = [e for e in await _befunde(db, a.id) if "andere" in e.meldung]

    assert not zeilen, [e.meldung for e in zeilen]


@pytest.mark.asyncio
async def test_eine_unbekannte_herkunft_ist_keine_abweichung(db):
    """Altbestand trägt ``manual:form`` — unbekannt, nicht anders.

    ⚠ Die ehrliche Grenze dieser Zeile: sie sieht nur, was in
    ``source_provenance`` steht. Eine Prüfung, die eine fehlende Angabe als
    Abweichung meldete, erzeugte eine Zahl, die niemand nachvollziehen kann.
    """
    heute = HEUTE
    jahr, monat = _vormonat(heute)
    a = await _anlage(
        db, [(jahr, monat)], provider="brightsky",
        werte={"globalstrahlung_kwh_m2": OM_GHI, "sonnenstunden": OM_SONNE,
               "durchschnittstemperatur": OM_TEMP},
        provenance={"sonnenstunden": {"source": "manual:form", "writer": "form"}},
    )

    zeilen = [e for e in await _befunde(db, a.id) if "andere" in e.meldung]

    assert not zeilen, [e.meldung for e in zeilen]


# ══════════════════════════════════════════════════════════════════════════
# 5 · Zeile 3b — die Quelle ist nicht festgehalten
# ══════════════════════════════════════════════════════════════════════════


def _ohne_quelle(befunde) -> list:
    return [e for e in befunde if "keine festgehaltene Wetterquelle" in e.meldung]


@pytest.mark.asyncio
async def test_checker_meldet_werte_ohne_festgehaltene_quelle(db):
    """Der Bestandsfall: Werte da, Herkunft nirgends.

    Das ist die Lage **jeder** Anlage vor dem ersten Nachzug — und bis zu
    dieser Zeile hat niemand sie bemerkt.
    """
    jahr, monat = _vormonat(HEUTE)
    a = await _anlage(
        db, [(jahr, monat)],
        werte={"globalstrahlung_kwh_m2": 192.9, "sonnenstunden": 380.0},
        provenance={
            "globalstrahlung_kwh_m2": {"source": "manual:form", "writer": "form"},
            "sonnenstunden": {"source": "manual:form", "writer": "form"},
        },
    )

    zeilen = _ohne_quelle(await _befunde(db, a.id))

    assert zeilen, [e.meldung for e in await _befunde(db, a.id)]
    e = zeilen[0]
    assert "1 abgeschlossene(r) Monat(e)" in e.meldung
    # ⛔ Die Zeile darf NICHT behaupten, die Reihe sei gemischt — sie weiß es nicht.
    assert "nicht mehr" in e.details and "feststellen" in e.details
    assert "stammen aus einer anderen" not in e.meldung
    # Kein Inline-Knopf: derselbe Lauf ersetzt, was schon dasteht.
    assert e.action_kind is None, e.action_kind
    assert e.link


@pytest.mark.asyncio
async def test_ein_monat_mit_anbieter_label_wird_nicht_gezaehlt(db):
    """Gegenprobe (a): die Zeile verstummt, sobald die Herkunft dasteht.

    Ohne diese Klausel wäre die Zeile ein Dauerbefund — sie meldete auch nach
    dem Nachzug weiter, und niemand könnte sie abstellen.
    """
    jahr, monat = _vormonat(HEUTE)
    a = await _anlage(
        db, [(jahr, monat)], provider="brightsky",
        werte={"globalstrahlung_kwh_m2": BS_GHI, "sonnenstunden": BS_SONNE},
        provenance={
            "globalstrahlung_kwh_m2": {"source": "external:brightsky", "writer": "x"},
            "sonnenstunden": {"source": "external:brightsky", "writer": "x"},
        },
    )

    assert not _ohne_quelle(await _befunde(db, a.id))


@pytest.mark.asyncio
async def test_nur_die_temperatur_ohne_label_zaehlt_nicht(db):
    """Gegenprobe (b): die Ø Temperatur hat legitim keinen Anbieter.

    ⛔ Kommt sie aus der eigenen Messreihe, stempeln sowohl die N-426-Aktion
    als auch der nächtliche Lückenschluss ``manual:form`` — das ist richtig und
    ändert sich nie. Zählte die Zeile sie mit, meldete sie auf **jeder gesunden
    Anlage** dauerhaft etwas, das sich durch nichts abstellen lässt.
    """
    jahr, monat = _vormonat(HEUTE)
    a = await _anlage(
        db, [(jahr, monat)], provider="brightsky",
        werte={"globalstrahlung_kwh_m2": BS_GHI, "sonnenstunden": BS_SONNE,
               "durchschnittstemperatur": BS_TEMP},
        provenance={
            "globalstrahlung_kwh_m2": {"source": "external:brightsky", "writer": "x"},
            "sonnenstunden": {"source": "external:brightsky", "writer": "x"},
            "durchschnittstemperatur": {"source": "manual:form", "writer": "form"},
        },
    )

    assert not _ohne_quelle(await _befunde(db, a.id))


@pytest.mark.asyncio
async def test_zeile_3_und_3b_zaehlen_denselben_monat_nicht_doppelt(db):
    """Zwei Zahlen über dieselben Monate kann niemand zusammenzählen.

    Der Monat trägt ein FREMDES Label an den Sonnenstunden und **gar keins** an
    der Globalstrahlung — er erfüllt damit beide Bedingungen. Gezählt wird er
    genau einmal, und zwar in der Zeile mit der stärkeren Aussage.
    """
    jahr, monat = _vormonat(HEUTE)
    a = await _anlage(
        db, [(jahr, monat)], provider="brightsky",
        werte={"globalstrahlung_kwh_m2": OM_GHI, "sonnenstunden": OM_SONNE},
        provenance={
            "sonnenstunden": {"source": "external:openmeteo", "writer": "x"},
        },
    )

    befunde = await _befunde(db, a.id)
    abweichend = [e for e in befunde if "andere" in e.meldung]

    assert abweichend, [e.meldung for e in befunde]
    assert not _ohne_quelle(befunde), (
        "Derselbe Monat steht in beiden Zeilen — der Anwender liest zwei "
        "Zahlen, die er nicht addieren darf."
    )


@pytest.mark.asyncio
async def test_der_laufende_monat_zaehlt_auch_hier_nicht(db):
    """Dieselbe Grenze wie bei den Nachbarzeilen und beim Nachzug."""
    a = await _anlage(
        db, [(HEUTE.year, HEUTE.month)],
        werte={"globalstrahlung_kwh_m2": 192.9, "sonnenstunden": 380.0},
    )

    assert not _ohne_quelle(await _befunde(db, a.id))


@pytest.mark.asyncio
async def test_ein_monat_ganz_ohne_werte_ist_eine_luecke_keine_quelle(db):
    """Abgrenzung zu Zeile 2: ohne Wert gibt es nichts, dessen Quelle fehlte.

    Sonst meldete eedc denselben Monat zweimal — einmal als Lücke und einmal
    als Wert unbekannter Herkunft.
    """
    jahr, monat = _vormonat(HEUTE)
    a = await _anlage(db, [(jahr, monat)])

    befunde = await _befunde(db, a.id)
    assert [e for e in befunde if "Globalstrahlung oder Sonnenstunden" in e.meldung]
    assert not _ohne_quelle(befunde)
