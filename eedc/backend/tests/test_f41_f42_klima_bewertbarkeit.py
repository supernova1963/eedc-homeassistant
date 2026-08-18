"""F-41 + F-42: Bewertbarkeit hängt an der Pflege, Messbarkeit an der Bauart.

Zwei gemeldete Fehler, ein gemeinsamer Grund — **eine Frage wurde am falschen
Objekt gestellt**.

**F-41** (#383, azywietz-web, 18.08.2026): Der Daten-Checker leitete *drei*
Hinweise aus *einem* Prädikat ab, der **Bauart** (`ist_luft_luft_waermepumpe`).
Seit v4.0.18 gibt es dafür ein Feld — `alter_energietraeger = "nichts"` —, und
die Rechnung respektiert es an sieben Stellen. Der Checker nicht. Folge an
beiden Enden:

* **Falsch-positiv:** jede Wärmepumpe im **Neubau** bekam zwei INFO, die sie
  nicht auflösen konnte — obwohl das Investitionsformular ausdrücklich zu
  „Nichts ersetzt (Neubau)" rät.
* **Falsch-negativ:** eine Klimaanlage, mit der jemand **tatsächlich heizt**,
  bekam sie nie zu sehen, obwohl ihre Ersparnis genau daran hängt.

Die dritte Meldung (WARNING „Alternativkosten fehlen") gehört an **keine** der
beiden Achsen: `anschaffungskosten_alternativ` fragt nach der vermiedenen
*Investition* und speist über `core/berechnungen/investitionskosten.py` die
USt-Bemessungsgrundlage und die Amortisation. Ein Neubau ersetzt keine Heizung,
hat aber trotzdem keinen Gaskessel gekauft. Sie gilt jetzt für **jede**
Wärmepumpe und sagt, dass 0 eine gültige Antwort ist.

**F-42**: Dieselbe Klimaanlage (4.375 kWh Strom, kein Wärmemengenzähler,
„nichts ersetzt") zeigte im Komponenten-Hub **vier Nullen** — JAZ 0,00 ·
Stromkosten 0,00 € · Gas/Öl 0,00 € · Ersparnis 0,00 € —, während dieselbe
Anlage in *Cockpit → Jahr* „—" und in *Auswertungen → ROI* „nicht bewertet"
sagte. Das ist die **N-258-Klasse** („nicht bewertet heißt keine Zahl"), die
v4.0.17 an der ROI-Tabelle behoben hat und die im Hub stehengeblieben war — und
eine seit dem 16.05.2026 nicht eingelöste Zusage an alex_s9027 (Forum T77723
#550), die JAZ-Kachel bleibe „sauber leer".

Der Schnitt in einem Satz: **Summieren darf 0 sein, Anzeigen nicht.**

Konzept: `docs/KONZEPT-263-klima-split.md` §7 E-C (F-41) und §7 E-D (F-42).
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen import ERSETZT_NICHTS
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis


# ============================================================================
# F-42 — der Layer-SoT
# ============================================================================

def test_f42_stromkosten_stehen_auch_ohne_vergleich():
    """*Strom × Preis* hat mit der ersetzten Heizung nichts zu tun.

    Der ausgelieferte Fehler: **beide** Frühausstiege gaben `wp_kosten_euro = 0`
    zurück — der eine, wenn keine Wärme gemessen ist, der andere, wenn nichts
    ersetzt wurde. Im Hub stand daraus „Stromkosten 0,00 €" neben 4.375 kWh
    Verbrauch.
    """
    ohne_waerme = berechne_wp_ersparnis(
        wp_waerme_kwh=0, wp_strom_kwh=4375, wp_strompreis_cent=30,
        wp_parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 12},
    )
    assert ohne_waerme.wp_kosten_euro == pytest.approx(1312.5)
    assert ohne_waerme.bewertbar is False

    ersetzt_nichts = berechne_wp_ersparnis(
        wp_waerme_kwh=1000, wp_strom_kwh=250, wp_strompreis_cent=30,
        wp_parameter={"alter_energietraeger": ERSETZT_NICHTS},
    )
    assert ersetzt_nichts.wp_kosten_euro == pytest.approx(75.0)
    assert ersetzt_nichts.bewertbar is False


def test_f42_die_vergleichsgroessen_bleiben_null_und_summieren_sich_zu_null():
    """Die Kehrseite: `wp_kosten_euro` wird echt, die Ersparnis bleibt 0.

    Wer über Geräte oder Monate **aufaddiert** (`aktueller_monat`,
    `cockpit/uebersicht`, `cockpit/komponenten`), soll weiterhin ohne
    None-Behandlung auskommen. Deshalb sitzt die Unterscheidung in einem Flag
    und nicht in `Optional`-Zahlenfeldern.
    """
    r = berechne_wp_ersparnis(
        wp_waerme_kwh=1000, wp_strom_kwh=250, wp_strompreis_cent=30,
        wp_parameter={"alter_energietraeger": ERSETZT_NICHTS},
    )
    assert r.ersparnis_euro == 0
    assert r.alte_heizung_kosten_euro == 0


def test_f42_normalfall_bleibt_bewertbar():
    """Negativprobe — sonst prüfte der Test nur, dass nichts mehr rechnet."""
    r = berechne_wp_ersparnis(
        wp_waerme_kwh=1000, wp_strom_kwh=250, wp_strompreis_cent=30,
        wp_parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 12},
    )
    assert r.bewertbar is True
    assert r.ersparnis_euro > 0
    assert r.alte_heizung_kosten_euro > 0
    assert r.wp_kosten_euro == pytest.approx(75.0)


def test_f42_ersparnis_ist_die_differenz_und_bleibt_es():
    """Warum die Route die Differenz nicht selbst nachbauen darf.

    `dashboards.py` rechnete die Ersparnis als `Σ alte_heizung − Σ wp_kosten`
    nach, statt `Σ ersparnis_euro` zu nehmen. Solange der Frühausstieg auch die
    Stromkosten auf 0 setzte, waren beide Wege zahlengleich; seit
    `wp_kosten_euro` echt ist, ergäbe die Differenz für eine Klimaanlage
    **−1.312 €**.

    Der Test hält beide Hälften fest: Bei bewertbaren Wärmepumpen sind die Wege
    identisch (der Helper ist linear), bei nicht bewertbaren gehen sie
    auseinander. Dass die Route diesen Unterschied heute **nicht** zeigt, liegt
    an der `bewertbar`-Sperre — siehe die Routen-Sektion unten.
    """
    bewertbar = berechne_wp_ersparnis(
        wp_waerme_kwh=1000, wp_strom_kwh=250, wp_strompreis_cent=30,
        wp_parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 12},
    )
    assert bewertbar.ersparnis_euro == pytest.approx(
        bewertbar.alte_heizung_kosten_euro - bewertbar.wp_kosten_euro
    )

    nicht_bewertbar = berechne_wp_ersparnis(
        wp_waerme_kwh=0, wp_strom_kwh=4375, wp_strompreis_cent=30,
        wp_parameter={"alter_energietraeger": ERSETZT_NICHTS},
    )
    differenz = (
        nicht_bewertbar.alte_heizung_kosten_euro - nicht_bewertbar.wp_kosten_euro
    )
    assert differenz < 0, "die nachgebaute Differenz wäre negativ …"
    assert nicht_bewertbar.ersparnis_euro == 0, "… der SoT sagt korrekt 0"


# ============================================================================
# F-41 — der Daten-Checker
# ============================================================================

async def _anlage_mit_wp(db, *, parameter: dict, alternativkosten=None):
    """Legt eine Anlage mit genau einer Wärmepumpe an — echter Checker-Weg.

    Bewusst über die DB und `DatenChecker._check_investitionen`, nicht über
    einen Stub: F-41 saß in der **Verdrahtung** zwischen Feld und Hinweis, und
    ein Stub prüft genau die nicht.
    """
    from datetime import date

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.models import Anlage, Investition, Monatsdaten

    anlage = Anlage(
        anlagenname="F41", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Testgerät",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
        anschaffungskosten_alternativ=alternativkosten, parameter=parameter,
    ))
    await db.commit()

    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return geladen, monatsdaten


async def _meldungen(db, *, parameter: dict, alternativkosten=None):
    """{meldung: details} der Stammdaten-Prüfung für genau diese Wärmepumpe."""
    from backend.services.daten_checker import DatenChecker

    anlage, monatsdaten = await _anlage_mit_wp(
        db, parameter=parameter, alternativkosten=alternativkosten
    )
    checker = DatenChecker(db)
    return {e.meldung: (e.details or "") for e in checker._check_investitionen(anlage, monatsdaten)}


def _hat(meldungen, text: str) -> bool:
    return any(text in m for m in meldungen)


HEIZT = {"wp_art": "luft_wasser", "jaz": 3.5}
KLIMA = {"wp_art": "luft_luft", "jaz": 3.5}
NICHTS = {"alter_energietraeger": ERSETZT_NICHTS}


@pytest.mark.parametrize("bauart", [HEIZT, KLIMA], ids=["luft_wasser", "luft_luft"])
async def test_f41_wer_nichts_ersetzt_bekommt_die_zwei_info_nicht(db, bauart):
    """Der Falsch-positiv — und er trifft **beide** Bauarten gleich.

    Das ist der Kern von F-41: Für diese Frage ist die Bauart irrelevant.
    """
    meldungen = await _meldungen(
        db, parameter={**bauart, **NICHTS}, alternativkosten=0
    )
    assert not _hat(meldungen, "Alter Energiepreis nicht gesetzt")
    assert not _hat(meldungen, "Heizwärmebedarf nicht gesetzt")


@pytest.mark.parametrize("bauart", [HEIZT, KLIMA], ids=["luft_wasser", "luft_luft"])
async def test_f41_wer_eine_heizung_ersetzt_bekommt_sie_sehr_wohl(db, bauart):
    """Der Falsch-negativ — die heizende Klimaanlage war bisher stumm gestellt.

    Ohne diese Hälfte hätte ein Fix „alles unterdrücken" ebenfalls grün gemeldet.
    """
    meldungen = await _meldungen(
        db, parameter={**bauart, "alter_energietraeger": "gas"}, alternativkosten=0
    )
    assert _hat(meldungen, "Alter Energiepreis nicht gesetzt")
    assert _hat(meldungen, "Heizwärmebedarf nicht gesetzt")


async def test_f41_altbestand_ohne_gepflegtes_feld_bleibt_unveraendert(db):
    """Kein stiller Datenwechsel: `None` heißt **nicht** „nichts ersetzt".

    Bestandsgeräte tragen den alten Default `gas`; eine fehlende Angabe darf
    eine bisher ausgewiesene Ersparnis nicht abschalten (SoT-Docstring von
    `ersetzt_keine_heizung`). Für eine **Klimaanlage** heißt das ausdrücklich:
    Sie bekommt die zwei Hinweise ab jetzt **neu** — dann aber auflösbar. Das
    ist die sichtbare Folge, die im WAS-IST-NEU steht.
    """
    meldungen = await _meldungen(db, parameter=dict(KLIMA), alternativkosten=0)
    assert _hat(meldungen, "Alter Energiepreis nicht gesetzt")
    assert _hat(meldungen, "Heizwärmebedarf nicht gesetzt")


@pytest.mark.parametrize(
    "parameter", [HEIZT, KLIMA, {**KLIMA, **NICHTS}, {**HEIZT, **NICHTS}],
    ids=["heizt", "klima", "klima_nichts", "heizt_nichts"],
)
async def test_f41_die_warning_haengt_an_keiner_der_beiden_achsen(db, parameter):
    """Die vermiedene **Investition** ist eine dritte Frage.

    `anschaffungskosten_alternativ` speist USt-Bemessungsgrundlage und
    Amortisation; `alter_energietraeger` kommt in `investitionskosten.py`
    0-mal vor. Die Warnung gilt deshalb für jede Wärmepumpe — unabhängig von
    Bauart und Pflege.
    """
    meldungen = await _meldungen(db, parameter=dict(parameter))
    assert _hat(meldungen, "Alternativkosten (Gas-/Ölheizung) fehlen")


@pytest.mark.parametrize("betrag", [0, 4500.0], ids=["null_euro", "echter_betrag"])
async def test_f41_die_warning_ist_mit_einer_null_aufloesbar(db, betrag):
    """Sie war es immer (`is None`) — sie hat es nur nicht gesagt.

    Der Defekt war die **Beschriftung**, nicht die Unauflösbarkeit.
    """
    meldungen = await _meldungen(db, parameter=dict(KLIMA), alternativkosten=betrag)
    assert not _hat(meldungen, "Alternativkosten (Gas-/Ölheizung) fehlen")


async def test_f41_der_warnungstext_nennt_den_weg_heraus(db):
    """Der eigentliche Fix der WARNING: 0 steht als gültige Antwort im Text.

    Ohne diesen Prüfer wäre F-41 formal „gebaut" und der Anwender läse
    weiterhin eine Forderung ohne Ausweg.
    """
    meldungen = await _meldungen(db, parameter=dict(KLIMA))
    details = next(
        d for m, d in meldungen.items() if "Alternativkosten (Gas-/Ölheizung) fehlen" in m
    )
    assert "0" in details and "Neubau" in details


# ============================================================================
# F-42 — die Route
# ============================================================================
#
# ⚑ Diese Sektion ist entstanden, weil der dritte Sprengsatz STUMM war: Die
# Ersparnis an der Route wieder als `Σ alte_heizung − Σ wp_kosten` nachzubauen,
# ließ 135 Proben grün — obwohl der Hub damit **−1.312 €** angezeigt hätte.
# Der Layer-Test darüber prüft die Formel, nicht ihre Verwendung. Dieselbe
# Lehre wie bei F-34 (Sitzung 60): **ein Routen-Sprengsatz gehört dazu.**

async def _wp_dashboard(db, *, parameter: dict, monate: int = 12,
                        strom_kwh: float = 300.0, waerme_kwh: float | None = None):
    """Fährt `GET /investitionen/dashboard/waermepumpe/{id}` gegen eine Anlage."""
    from datetime import date

    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard
    from backend.models import Anlage, Investition, InvestitionMonatsdaten

    anlage = Anlage(
        anlagenname="F42", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Testgerät",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
        parameter=parameter,
    )
    db.add(wp)
    await db.flush()
    for monat in range(1, monate + 1):
        daten = {"stromverbrauch_kwh": strom_kwh}
        if waerme_kwh is not None:
            daten["heizenergie_kwh"] = waerme_kwh
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=monat, verbrauch_daten=daten,
        ))
    await db.commit()

    # `strompreis_cent` explizit setzen: der Default ist ein `Query`-Objekt, das
    # beim Direktaufruf nicht von FastAPI aufgelöst wird. Ein fester Preis macht
    # die Erwartungen unten außerdem nachrechenbar.
    dashboards = await get_waermepumpe_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0, db=db,
    )
    assert len(dashboards) == 1
    return dashboards[0].zusammenfassung


async def test_f42_route_klimaanlage_zeigt_stromkosten_und_sonst_nichts(db):
    """Der gemeldete Fall, an der Route: vier Nullen wurden zu einer Zahl.

    Gemessen an der Testinstanz (:8202): 4.375 kWh Strom, kein
    Wärmemengenzähler, „nichts ersetzt" ⇒ *Komponenten → Wärme/Klima* zeigte
    `JAZ 0,00` · `Stromkosten 0,00 €` · `Gas/Öl 0,00 €` · `Ersparnis 0,00 €`.
    """
    z = await _wp_dashboard(
        db, parameter={"wp_art": "luft_luft", "alter_energietraeger": ERSETZT_NICHTS},
    )

    assert z["wp_kosten_euro"] > 0, "die einzige Zahl, die hier gilt"
    assert z["durchschnitt_cop"] is None, "JAZ ohne gemessene Wärme ist keine 0"
    assert z["alte_heizung_kosten_euro"] is None
    assert z["ersparnis_euro"] is None
    assert z["co2_ersparnis_kg"] is None


async def test_f42_route_ersparnis_wird_nie_negativ(db):
    """Der Prüfer, den Sprengsatz C gebraucht hätte — und die Lehre daraus.

    Er misst nicht „ist die Zahl richtig", sondern „kann sie überhaupt
    entstehen": Eine Ersparnis, die aus 0 € Gaskosten minus echten Stromkosten
    hervorgeht, ist ein Vorzeichenfehler, kein Rundungsunterschied.

    ⚑ **Gemessen beim Bau:** Der Schutz sind **zwei** Hälften, und keine trägt
    allein. „Differenz statt SoT-Summe" blieb stumm, weil die `bewertbar`-Sperre
    den Wert ohnehin auf `None` zieht; rot wird erst die Kombination aus beidem.
    Genau dafür steht dieser Test hier statt eines Formel-Vergleichs — er prüft
    das **Ergebnis**, nicht den Weg, und fängt deshalb jede der beiden
    Rücknahmen.
    """
    z = await _wp_dashboard(
        db, parameter={"wp_art": "luft_luft", "alter_energietraeger": ERSETZT_NICHTS},
        strom_kwh=364.6,
    )
    assert z["ersparnis_euro"] is None or z["ersparnis_euro"] >= 0


async def test_f42_route_normalfall_traegt_weiterhin_alle_zahlen(db):
    """Negativprobe — ohne sie wäre „alles null" ebenfalls grün.

    Zusätzlich der Beleg, dass `Σ ersparnis_euro` und die frühere Differenz bei
    bewertbaren Wärmepumpen zahlengleich sind: Der Helper ist linear, die
    Umstellung an der Route bewegt **keine** bestehende Zahl.
    """
    z = await _wp_dashboard(
        db, parameter={"wp_art": "luft_wasser", "alter_energietraeger": "gas",
                       "alter_preis_cent_kwh": 12},
        waerme_kwh=1000.0,
    )

    assert z["durchschnitt_cop"] is not None and z["durchschnitt_cop"] > 0
    assert z["wp_kosten_euro"] > 0
    assert z["alte_heizung_kosten_euro"] > 0
    assert z["ersparnis_euro"] == pytest.approx(
        z["alte_heizung_kosten_euro"] - z["wp_kosten_euro"], abs=0.02
    ), "bei bewertbaren WP sind beide Wege identisch — sonst wäre es eine Regression"


async def test_f42_route_wp_ohne_ersatz_aber_mit_waerme(db):
    """Der Zwischenfall: gemessene Wärme, aber nichts ersetzt.

    Die JAZ ist hier eine **echte** Kennzahl und muss stehen bleiben — nur der
    Geld-Vergleich entfällt. Ohne diesen Test wäre ein Fix, der bei „nichts
    ersetzt" pauschal alles auf `None` setzt, nicht zu unterscheiden.
    """
    z = await _wp_dashboard(
        db, parameter={"wp_art": "luft_luft", "alter_energietraeger": ERSETZT_NICHTS},
        waerme_kwh=900.0,
    )

    assert z["durchschnitt_cop"] == pytest.approx(3.0), "Wärme ÷ Strom, gemessen"
    assert z["wp_kosten_euro"] > 0
    assert z["ersparnis_euro"] is None
    assert z["co2_ersparnis_kg"] is None
