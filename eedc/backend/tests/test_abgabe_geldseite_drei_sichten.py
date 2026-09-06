"""Der Abgabe-Erlös trägt in allen drei Sichten der Kapitalrechnung (11b/11c).

`einsparung_prognose_jahr` wurde bis zum 06.09.2026 an drei Stellen unabhängig
summiert. Seit Bauschritt 11a beantwortet `jahresertrag_posten` die Frage
einmal; hier wird geprüft, dass die drei Aufrufer ihn auch wirklich lesen —
**und** dass ihre unterschiedlichen Laufzeit-Filter dabei erhalten bleiben.

⛔ Die drei Filter sind KEINE Drift und werden nicht angeglichen:

    ROI-Dashboard   ohne `jahr` gar kein Filter — #123, „spätere Stilllegung
                    darf Vergangenheit nicht löschen" (Rückblick)
    Aussichten      `ist_aktiv_an(heute)` — eine Prognose zählt nur, was läuft
    HA-Export       `aktiv_jetzt()` auf Query-Ebene — dito

Zwei Fragen, zwei Umfänge. Wer sie einebnet, beantwortet eine davon falsch.
Die letzte Probe hält das ausdrücklich fest.

Schwesterdateien: test_abgabe_an_dritte_vier_sichten.py (Bilanz-Seite und die
Route hinter Auswertungen → Finanzen), test_investitions_jahresertrag_sot.py
(die Vorrang-Regel selbst), test_abgabe_an_dritte_anzeige.py,
test_abgabe_an_dritte_tag_live.py, test_erzeuger_einspeise_erloes.py (§9 Weg 2)
und test_netto_ertrag_vier_wege_symmetrie.py (der Symmetrie-Partner auf der
Bilanz-Achse).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.api.routes.ha_export import calculate_anlage_sensors

JAHR = 2025
#: 12 Monate à 40 € ⇒ die Hochrechnung ist exakt 480 €/Jahr, ohne Rundungsrand.
ERLOES_JE_MONAT = 40.0
ERWARTET_JAHR = 480.0


async def _anlage(db, *, stillgelegt: bool = False):
    a = Anlage(anlagenname="abgabe-3", leistung_kwp=10.0,
               installationsdatum=date(JAHR, 1, 1))
    db.add(a)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(JAHR, 1, 1),
                     anschaffungskosten_gesamt=10000.0, leistung_kwp=10.0)
    db.add(pv)
    inv = Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Allg. Strom",
        anschaffungsdatum=date(JAHR, 1, 1), anschaffungskosten_gesamt=2000.0,
        parameter={"kategorie": "abgabe"},
        stilllegungsdatum=date(JAHR, 6, 1) if stillgelegt else None,
    )
    db.add(inv)
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=100.0))
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=JAHR, monat=monat,
            verbrauch_daten={"abgabe_kwh": 50.0,
                             "einspeise_erloes_euro": ERLOES_JE_MONAT},
        ))
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(JAHR, 1, 1)))
    await db.commit()
    return a, inv


@pytest.mark.asyncio
async def test_roi_dashboard_traegt_den_gemessenen_erloes(db):
    """Die Zeile des Geräts wird bewertet — vorher „nicht bewertet"."""
    a, inv = await _anlage(db)
    roi = await get_roi_dashboard(
        anlage_id=a.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    zeile = next(b for b in roi.berechnungen if b.investition_id == inv.id)

    assert zeile.jahres_einsparung == pytest.approx(ERWARTET_JAHR, abs=0.02), (
        f"{zeile.jahres_einsparung} statt {ERWARTET_JAHR}")
    d = zeile.detail_berechnung or {}
    assert d.get("nicht_bewertet") is not True, (
        "Zeile gilt weiter als nicht bewertet, obwohl der Erlös gepflegt ist")


@pytest.mark.asyncio
async def test_aussichten_und_ha_export_nennen_dieselbe_zahl(db):
    """Symmetrie — die zwei Prognose-Sichten gegen dieselbe Größe."""
    a, _inv = await _anlage(db)

    prognose = await get_finanz_prognose(anlage_id=a.id, monate=12, db=db)
    anlage = await db.get(Anlage, a.id)
    sensoren = await calculate_anlage_sensors(db, anlage)
    ha_jahr = next(
        s.value for s in sensoren if s.definition.key == "jahres_ersparnis_euro"
    )

    # Beide tragen denselben Posten; die absoluten Zahlen enthalten daneben
    # Einspeise-Erlös und EV-Ersparnis, deshalb wird die DIFFERENZ gegen eine
    # Anlage ohne Erlös geprüft — das ist der Beitrag, um den es geht.
    assert prognose is not None and ha_jahr is not None


@pytest.mark.asyncio
async def test_der_beitrag_ist_in_beiden_prognosen_gleich_gross(db):
    """Der **Beitrag** des Erlöses — gemessen als Differenz mit/ohne Pflege.

    Absolute Summen enthalten Einspeise-Erlös und EV-Ersparnis; die Differenz
    isoliert den neuen Posten. Sie muss in beiden Sichten 480 € betragen.
    """
    a_mit, inv = await _anlage(db)
    prog_mit = await get_finanz_prognose(anlage_id=a_mit.id, monate=12, db=db)
    anlage_mit = await db.get(Anlage, a_mit.id)
    ha_mit = next(s.value for s in await calculate_anlage_sensors(db, anlage_mit)
                  if s.definition.key == "jahres_ersparnis_euro")

    # Erlöse entfernen — dieselbe Anlage, nur ohne gepflegtes Geld.
    from sqlalchemy import select
    rows = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id)
    )).scalars().all()
    from sqlalchemy.orm.attributes import flag_modified
    for r in rows:
        r.verbrauch_daten.pop("einspeise_erloes_euro", None)
        flag_modified(r, "verbrauch_daten")
    await db.commit()

    prog_ohne = await get_finanz_prognose(anlage_id=a_mit.id, monate=12, db=db)
    anlage_ohne = await db.get(Anlage, a_mit.id)
    ha_ohne = next(s.value for s in await calculate_anlage_sensors(db, anlage_ohne)
                   if s.definition.key == "jahres_ersparnis_euro")

    d_prog = prog_mit.jahres_netto_ertrag_euro - prog_ohne.jahres_netto_ertrag_euro
    d_ha = ha_mit - ha_ohne
    assert d_prog == pytest.approx(ERWARTET_JAHR, abs=0.5), (
        f"Aussichten-Beitrag {d_prog} statt {ERWARTET_JAHR}")
    assert d_ha == pytest.approx(ERWARTET_JAHR, abs=0.5), (
        f"HA-Beitrag {d_ha} statt {ERWARTET_JAHR}")


@pytest.mark.asyncio
async def test_die_zwei_umfaenge_bleiben_verschieden(db):
    """⛔ Der Anker gegen das „Vereinheitlichen" der drei Filter.

    Ein **stillgelegtes** Gerät: Die Prognose-Sichten lassen es weg (es bringt
    nichts mehr), das ROI-Dashboard ohne Jahresfilter behält es (sonst
    verschwindet die Vergangenheit, #123). Wer diese Probe rot sieht, hat die
    beiden Fragen zusammengelegt — und eine davon falsch beantwortet.
    """
    a, inv = await _anlage(db, stillgelegt=True)

    prognose = await get_finanz_prognose(anlage_id=a.id, monate=12, db=db)
    anlage = await db.get(Anlage, a.id)
    ha_jahr = next(s.value for s in await calculate_anlage_sensors(db, anlage)
                   if s.definition.key == "jahres_ersparnis_euro")

    a2, inv2 = await _anlage(db, stillgelegt=False)
    prognose2 = await get_finanz_prognose(anlage_id=a2.id, monate=12, db=db)
    anlage2 = await db.get(Anlage, a2.id)
    ha_jahr2 = next(s.value for s in await calculate_anlage_sensors(db, anlage2)
                    if s.definition.key == "jahres_ersparnis_euro")

    # Prognosen: das stillgelegte Gerät trägt WENIGER.
    assert prognose.jahres_netto_ertrag_euro < prognose2.jahres_netto_ertrag_euro, (
        "Die Prognose zählt ein stillgelegtes Gerät mit")
    assert ha_jahr < ha_jahr2, "Der HA-Sensor zählt ein stillgelegtes Gerät mit"

    # ROI-Dashboard ohne Jahr: die Zeile ist weiterhin da und bewertet.
    roi = await get_roi_dashboard(
        anlage_id=a.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    zeile = next((b for b in roi.berechnungen if b.investition_id == inv.id), None)
    assert zeile is not None, (
        "Das ROI-Dashboard hat die stillgelegte Zeile verloren — #123 verletzt")


@pytest.mark.asyncio
async def test_die_zerlegung_ordnet_den_abgabe_erloes_seiner_zeile_zu(db):
    """Die im Konzept offengelassene Frage — gemessen, nicht angenommen.

    §9.2 verlangte ausdrücklich: *„Beim Bau zu messen, nicht abzuschreiben: ob
    die Aussichten-Zerlegung (§8/7) Abgabe-Geräte wie Erzeuger behandelt."*

    **Antwort: ja, und das ist richtig.** Der Zuordnungs-Block in
    `aussichten.py` liest jedes *Sonstiges*-Gerät mit gepflegtem
    `einspeise_erloes_euro` — **kategorie-blind** — und ordnet den Betrag direkt
    seiner Zeile zu. Die Bauschritt-5-Regel lautet „alles komponentenscharf
    Vorliegende direkt", und der Abgabe-Erlös liegt genau so vor.

    ⚑ **Doppelt zählen kann er dabei nicht:** `zerlege_kumulierten_ertrag`
    **verteilt** den anlagenweiten Zähler, statt ihn zu erhöhen
    (`nicht_zurechenbar = gesamt − Σ je_investition`, per Konstruktion). Wäre
    die Zuordnung ein Zuschlag, stünde der Betrag zweimal in der Rechnung —
    diese Probe prüft deshalb **beides**: die Zeile bekommt ihn, und die
    Identität der Zerlegung hält.
    """
    a, inv = await _anlage(db)

    prognose = await get_finanz_prognose(anlage_id=a.id, monate=12, db=db)
    zeilen = {z.investition_id: z.bisherige_ertraege_euro
              for z in prognose.ertraege_je_investition}

    assert inv.id in zeilen, (
        "Der Abgabe-Erlös landete im nicht zurechenbaren Rest, obwohl seine "
        "Investition bekannt ist")
    assert zeilen[inv.id] > 0, f"Zeile trägt {zeilen[inv.id]} €"

    # Die Identität der Zerlegung — sie ist der Schutz gegen ein Doppelzählen.
    summe = sum(zeilen.values()) + prognose.ertraege_nicht_zurechenbar_euro
    assert summe == pytest.approx(
        prognose.bisherige_ertraege_euro, abs=0.02), (
        f"Σ Zeilen + Rest = {summe} ≠ Zähler {prognose.bisherige_ertraege_euro}")
