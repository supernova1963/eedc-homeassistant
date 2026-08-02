"""Ein Hinweis, den niemand auflösen kann, muss wenigstens seine Folge nennen.

dietmar1968 hat im Forum (#89667/87) drei Daten-Checker-Hinweise gezeigt, die er
nicht abstellen konnte, und ums **Quittieren** gebeten. Quittieren ist
entschieden ausgeschlossen ([[feedback_daten_checker_kein_akzeptiert]]) — der
vorgesehene Weg ist Bedingung schärfen **oder** Wortlaut ehrlich machen. Für
diese beiden gibt es keine schärfere Bedingung:

* **WP-Tarif** — ob jemand einen Wärmestrom-Tarif *hat*, ist im Datenmodell
  nicht von „noch nicht eingetragen" zu unterscheiden.
* **PVGIS-Systemverluste** — der Befund ist richtig; unklar war, was die
  angebotene Handlung auslöst.

Also muss der Text zwei Dinge leisten: sagen, **was ohne Handlung gilt**, und
sagen, **was sich mit ihr ändert**. Die Tests prüfen bewusst nur kurze,
inhaltstragende Teilzeichenketten — nicht ganze Sätze, sonst ist jede
Umformulierung ein roter Test.

Der Klimaanlagen-Hinweis aus derselben Runde (der einzige echte Fehler) hängt an
der Zusatz-Zähler-Prüfung und steht in
`test_daten_checker_tages_zusatzfelder_dok9.py`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Strompreis
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity


async def _lade(db, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen), selectinload(Anlage.strompreise))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def _anlage_mit_wp(db) -> Anlage:
    anlage = Anlage(
        anlagenname="WP-Tarif", leistung_kwp=10.0,
        installationsdatum=date(2023, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Vitocal",
        anschaffungsdatum=date(2023, 1, 1), aktiv=True,
    ))
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.commit()
    return await _lade(db, anlage.id)


def _wp_hinweise(db, anlage: Anlage) -> list:
    return [
        r for r in DatenChecker(db)._check_strompreise(anlage)
        if "Wärmepumpe" in r.meldung
    ]


async def test_wp_tarif_hinweis_nennt_den_rueckfall_und_entlastet(db):
    """Ohne WP-Tarif rechnet eedc mit dem allgemeinen — das muss dastehen.

    Vorher lautete der Text „Wärmepumpe vorhanden – bei eigenem WP-Tarif
    (Wärmestrom) hier ergänzen": eine Aufforderung ohne Folge und ohne die
    Auskunft, dass Nichtstun beim Einheitstarif richtig ist.
    """
    anlage = await _anlage_mit_wp(db)

    treffer = _wp_hinweise(db, anlage)

    assert len(treffer) == 1
    assert treffer[0].schwere == CheckSeverity.INFO, "eine Warnung wäre Nörgeln"
    details = treffer[0].details or ""
    assert "allgemeinen Arbeitspreis" in details, "der Rückfall muss dastehen"
    assert "muss nichts tun" in details, "Einheitstarif = kein Handlungsbedarf"


async def test_wp_tarif_hinweis_verschwindet_mit_dem_tarif(db):
    """Gegenprobe: wer den Tarif hat und einträgt, wird ihn los."""
    anlage = await _anlage_mit_wp(db)
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.commit()
    db.expunge_all()

    assert _wp_hinweise(db, await _lade(db, anlage.id)) == []


async def test_systemverluste_hinweis_nennt_die_folge_der_handlung(db):
    """„Für den ersten Hinweis bräuchte ich eine Erklärung." (dietmar1968)

    Der Text nannte Befund (PR über 12 Monate) und Handlung („Systemverluste
    reduzieren?"), aber nicht die Folge: das SOLL steigt, deshalb sinken
    Performance Ratio und SOLL-Erfüllung — ohne dass sich ein IST-Wert ändert.
    Ohne diese Zeile ist die Frage nicht zu beantworten.
    """
    anlage = Anlage(
        anlagenname="PR-hoch", leistung_kwp=10.0,
        installationsdatum=date(2023, 1, 1),
        latitude=48.0, longitude=11.0, standort_ort="Musterstadt",
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2023, 1, 1), aktiv=True, leistung_kwp=10.0,
    ))
    await db.commit()
    anlage = await _lade(db, anlage.id)

    prognose = PVGISPrognose(
        anlage_id=anlage.id, latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, system_losses=14.0,
        jahresertrag_kwh=9000.0, spezifischer_ertrag_kwh_kwp=900.0,
    )

    treffer = [
        r for r in DatenChecker(db)._check_stammdaten(anlage, prognose, pr=1.12, pr_count=12)
        if "Systemverluste" in r.meldung
    ]

    assert len(treffer) == 1
    assert treffer[0].schwere == CheckSeverity.INFO
    details = treffer[0].details or ""
    assert "Annahme" in details, "14 % ist keine Messung — das trägt die Erklärung"
    assert "neuen PVGIS-Abruf" in details, "ohne Abruf ändert sich nichts"
    assert "das SOLL steigt" in details, "die Folge der Handlung fehlt sonst"
    assert "IST-Werte bleiben unverändert" in details
    assert "Historie" in details, "der Schritt ist umkehrbar — das nimmt die Angst"


async def test_systemverluste_hinweis_schweigt_bei_normalem_ertrag(db):
    """Gegenprobe: unter der Schwelle sagt der Checker gar nichts."""
    anlage = Anlage(
        anlagenname="PR-normal", leistung_kwp=10.0,
        installationsdatum=date(2023, 1, 1),
        latitude=48.0, longitude=11.0, standort_ort="Musterstadt",
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2023, 1, 1), aktiv=True, leistung_kwp=10.0,
    ))
    await db.commit()
    anlage = await _lade(db, anlage.id)

    prognose = PVGISPrognose(
        anlage_id=anlage.id, latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, system_losses=14.0,
        jahresertrag_kwh=9000.0, spezifischer_ertrag_kwh_kwp=900.0,
    )

    treffer = [
        r for r in DatenChecker(db)._check_stammdaten(anlage, prognose, pr=1.02, pr_count=12)
        if "Systemverluste" in r.meldung
    ]

    assert treffer == []
