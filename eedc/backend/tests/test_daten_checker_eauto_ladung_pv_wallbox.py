"""F-64 — der Checker fordert `ladung_pv_kwh` am E-Auto nur OHNE Wallbox.

Schwesterdatei: ``test_daten_checker_tages_zusatzfelder_dok9.py``. Sie haelt
dieselbe Regel in der anderen Haelfte des Daten-Checkers fest
(``daten_checker/energieprofil.py``), diese hier in ``stammdaten.py``.

**Der Anlass.** gruaGit (GitHub Discussion #396, 24.08.2026) meldete: Der
Daten-Checker sagt „VW ID.3 (e-auto): Ladung PV fehlt in 8 Monat(en)", waehrend
der Komponenten-Hub fuer dieselben Monate PV-Anteile ausweist. Er hat eine
go-e-Wallbox — sie steht in seinem Bild eine Zeile darueber mit gruenem Haken.

**Die Regel, die fehlte.** ``core/field_definitions.py`` gibt dem E-Auto-Feld
``ladung_pv_kwh`` die Bedingung ``"bedingung_anlage": "keine_wallbox"``, mit
ausdruecklicher Begruendung: *existiert eine Wallbox-Investition, ist SIE die
kanonische Quelle der Heimladung — dann nicht zusaetzlich am E-Auto erfassen
(sonst Dual-Daten / Doppelzaehlung)*. Das **Formular blendet das Feld deshalb
aus**; der Checker in ``stammdaten.py`` forderte es trotzdem ein.

**Die Folge war eine Sackgasse, kein Schoenheitsfehler:** Die Meldung traegt
einen „Beheben"-Knopf, der in ein Formular fuehrt, in dem es dieses Feld nicht
gibt. Wer den Wert trotzdem beschafft und eintraegt, erzeugt genau die
Doppelzaehlung, die die Bedingung verhindern soll. Abstellbar war die Meldung
fuer niemanden mit Wallbox **und** E-Auto.

**Dass es ein Versehen war und keine Absicht,** zeigt der zweite Checker:
``energieprofil.py`` traegt die Bedingung bereits ausformuliert
(``if inv.typ == "e-auto" and (hat_wallbox or ist_dienstlich(inv)): continue``)
und nennt sie im Kommentar beim Namen. Der Fix kopiert diese Regel, er erfindet
sie nicht.

⚠ **Der Dienstwagen war bereits gedeckt** (``ist_dienstlich``, dieselbe
Methode) — es fehlte ausschliesslich die Wallbox-Haelfte. Beide Richtungen
stehen unten als Probe, damit der Fix die eine nicht auf Kosten der anderen
herstellt.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.tests import factories

#: Festes Datum statt der echten Uhr — eine Probe, die `date.today()` liest,
#: waere von der Laufzeit abhaengig. Die Monate liegen bewusst in der
#: Vergangenheit, damit `_erwartete_monate` sie erwartet.
JAHR = 2026
MONATE = (1, 2, 3)


async def _anlage_mit(db, *, mit_wallbox: bool, dienstlich: bool = False) -> Anlage:
    """Anlage mit E-Auto (ohne `ladung_pv_kwh`) und optional einer Wallbox."""
    anlage = await factories.anlage(db, standort_land="DE")

    for monat in MONATE:
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=monat))

    eauto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="VW ID.3",
        anschaffungsdatum=date(JAHR - 1, 1, 1),
        anschaffungskosten_alternativ=30000.0,
        parameter=(
            {"ist_dienstlich": True} if dienstlich
            else {"jahresfahrleistung_km": 15000, "verbrauch_kwh_100km": 17.0}
        ),
    )
    db.add(eauto)
    await db.flush()

    # Die Ladung selbst ist gepflegt — nur der PV-Anteil fehlt, genau wie bei
    # gruaGit (seine kWh-Spalte am Fahrzeug steht in allen Monaten auf 0,0,
    # weil die Ladung an der Wallbox gefuehrt wird).
    for monat in MONATE:
        db.add(InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=JAHR, monat=monat,
            verbrauch_daten={"ladung_kwh": 200.0},
        ))

    if mit_wallbox:
        wb = Investition(
            anlage_id=anlage.id, typ="wallbox", bezeichnung="go-e Charger",
            anschaffungsdatum=date(JAHR - 1, 1, 1),
            parameter={"max_ladeleistung_kw": 11.0},
        )
        db.add(wb)
        await db.flush()
        for monat in MONATE:
            db.add(InvestitionMonatsdaten(
                investition_id=wb.id, jahr=JAHR, monat=monat,
                verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0},
            ))

    await db.commit()
    return anlage


async def _ladung_pv_meldungen(db, anlage: Anlage) -> list[str]:
    """Alle Meldungen des Investitions-Checks, die „Ladung PV" einfordern."""
    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    ergebnisse = DatenChecker(db)._check_investitionen(geladen, monatsdaten)
    return [e.meldung for e in ergebnisse if "Ladung PV fehlt" in e.meldung]


async def test_mit_wallbox_wird_ladung_pv_am_eauto_nicht_eingefordert(db):
    """gruaGits Fall: Wallbox vorhanden ⇒ das Feld ist verdraengt, keine Meldung."""
    anlage = await _anlage_mit(db, mit_wallbox=True)

    meldungen = await _ladung_pv_meldungen(db, anlage)

    assert meldungen == [], (
        "Der Checker fordert `ladung_pv_kwh` am E-Auto ein, obwohl eine Wallbox "
        "existiert — das Formular blendet das Feld dort aus "
        "(`bedingung_anlage: keine_wallbox`). Der Anwender bekommt eine Meldung, "
        f"die er nicht abstellen kann: {meldungen}"
    )


async def test_ohne_wallbox_wird_ladung_pv_weiterhin_eingefordert(db):
    """Gegenprobe — ohne Wallbox ist das Feld sichtbar und der Hinweis richtig.

    Ohne sie koennte der Fix die Pruefung ersatzlos streichen und beide Proben
    waeren gruen.
    """
    anlage = await _anlage_mit(db, mit_wallbox=False)

    meldungen = await _ladung_pv_meldungen(db, anlage)

    assert len(meldungen) == 1, (
        f"Ohne Wallbox gehoert der Hinweis weiterhin gemeldet, bekam aber: {meldungen}"
    )
    assert f"{len(MONATE)} Monat(en)" in meldungen[0]


async def test_dienstwagen_bleibt_ausgenommen(db):
    """Die zweite, bereits vorhandene Haelfte derselben Regel bleibt stehen."""
    anlage = await _anlage_mit(db, mit_wallbox=False, dienstlich=True)

    assert await _ladung_pv_meldungen(db, anlage) == []
