"""PV je Monat über den SoT — der Ladepfad, an dem zwei Sichten vorbeiliefen.

`ha_export.py` und `cockpit/uebersicht.py` bildeten je eine **rohe IMD-Summe**
und schalteten über ein globales Flag zwischen ihr und dem Anlagen-Aggregat um
(`use_inv_pv = bool(pv_by_ym)` bzw. `pv_erzeugung_inv > 0`, dann
`.get(key, 0.0)`). Daraus folgten zwei Fehler, die beide hier festgehalten sind:

**(a) Historie verloren.** Sobald IRGENDEIN Monat IMD-Werte hatte, lieferte
`.get(key, 0.0)` für alle anderen Monate **0** — auch dort, wo ein Aggregat
vorlag. Eine Anlage, die mitten in der Historie auf Pro-String-Messung
umgestellt hat, verlor ihre gesamte Vorgeschichte in Finanzen und spezifischem
Ertrag. Das ist derselbe Anwendungsfall, für den das Aggregat überhaupt
existiert.

**(b) Teilsumme statt Messung + Lückenfüllung.** In einem Monat mit nur
teilweise gemessenen Strings ging die rohe Teilsumme ein, statt die Lücke aus
dem Aggregat zu füllen.

Beide Sichten laden jetzt über `services/pv_monatswerte.py`; die Präzedenz
selbst steht in `core/berechnungen/pv_verteilung.py`.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import PV_QUELLE_GEMESSEN, PV_QUELLE_VERTEILT
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.pv_monatswerte import lade_pv_je_monat, pv_summe_je_monat


async def _anlage_umgestellt_mitten_in_der_historie(db):
    """Zwei Strings. 2025-01 nur Aggregat, 2025-02 gemischt, 2025-03 voll gemessen."""
    anlage = Anlage(anlagenname="Umstellung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    sued = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0,
    )
    ost = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0,
    )
    db.add_all([sued, ost])
    await db.flush()

    # Anlagen-Aggregat für alle drei Monate gepflegt (manuell/importiert).
    for monat, gesamt in ((1, 1000.0), (2, 1000.0), (3, 1000.0)):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            einspeisung_kwh=0.0, netzbezug_kwh=0.0, pv_erzeugung_kwh=gesamt,
        ))

    # Februar: nur Süd misst. März: beide messen.
    db.add(InvestitionMonatsdaten(
        investition_id=sued.id, jahr=2025, monat=2,
        verbrauch_daten={"pv_erzeugung_kwh": 700.0},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=sued.id, jahr=2025, monat=3,
        verbrauch_daten={"pv_erzeugung_kwh": 650.0},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ost.id, jahr=2025, monat=3,
        verbrauch_daten={"pv_erzeugung_kwh": 350.0},
    ))
    await db.commit()
    return anlage.id, [sued, ost]


@pytest.mark.asyncio
async def test_monate_vor_der_umstellung_behalten_ihre_erzeugung(db):
    """(a) Der Januar hat nur ein Aggregat — er darf nicht auf 0 fallen."""
    anlage_id, module = await _anlage_umgestellt_mitten_in_der_historie(db)

    summen = pv_summe_je_monat(await lade_pv_je_monat(db, anlage_id, module))

    assert summen[(2025, 1)] == pytest.approx(1000.0), (
        "Monat ohne IMD-Zeilen fiel vorher auf 0, sobald ein anderer Monat welche hatte"
    )


@pytest.mark.asyncio
async def test_gemischter_monat_behaelt_die_messung_und_fuellt_die_luecke(db):
    """(b) Februar: Süd misst 700, Ost nicht ⇒ 700 + Rest 300, nicht 700 allein."""
    anlage_id, module = await _anlage_umgestellt_mitten_in_der_historie(db)
    sued, ost = module

    monate = await lade_pv_je_monat(db, anlage_id, module)
    feb = monate[(2025, 2)]

    assert feb[sued.id].pv_erzeugung_kwh == pytest.approx(700.0)
    assert feb[sued.id].quelle == PV_QUELLE_GEMESSEN
    assert feb[ost.id].pv_erzeugung_kwh == pytest.approx(300.0)
    assert feb[ost.id].quelle == PV_QUELLE_VERTEILT

    summen = pv_summe_je_monat(monate)
    assert summen[(2025, 2)] == pytest.approx(1000.0), "rohe Teilsumme statt Aggregat"


@pytest.mark.asyncio
async def test_voll_gemessener_monat_ignoriert_das_aggregat(db):
    """März: beide messen ⇒ 650 + 350, das Aggregat bleibt außen vor."""
    anlage_id, module = await _anlage_umgestellt_mitten_in_der_historie(db)

    summen = pv_summe_je_monat(await lade_pv_je_monat(db, anlage_id, module))

    assert summen[(2025, 3)] == pytest.approx(1000.0)
    monate = await lade_pv_je_monat(db, anlage_id, module)
    assert all(w.quelle == PV_QUELLE_GEMESSEN for w in monate[(2025, 3)].values())


@pytest.mark.asyncio
async def test_teilmessung_ohne_aggregat_ist_unvollstaendig_nicht_null(db):
    """Ohne Aggregat bleibt der Monat `None` — keine Teilsumme als Erzeugung."""
    anlage = Anlage(anlagenname="Ausfall", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    sued = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0,
    )
    ost = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0,
    )
    db.add_all([sued, ost])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=sued.id, jahr=2025, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 700.0},
    ))
    await db.commit()

    monate = await lade_pv_je_monat(db, anlage.id, [sued, ost])
    summen = pv_summe_je_monat(monate)

    assert summen[(2025, 5)] is None, "Teilsumme darf nicht als Anlagenerzeugung gelten"
    assert monate[(2025, 5)][sued.id].pv_erzeugung_kwh == pytest.approx(700.0), (
        "der Messwert bleibt trotzdem sichtbar"
    )


@pytest.mark.asyncio
async def test_module_zaehlen_nur_in_ihren_aktiven_monaten(db):
    """#236: ein später angeschaffter String bekommt keinen Aggregat-Anteil."""
    anlage = Anlage(anlagenname="Zubau", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    alt = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Alt",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0,
    )
    neu = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Neu",
        anschaffungsdatum=date(2025, 6, 1), leistung_kwp=4.0,
    )
    db.add_all([alt, neu])
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=3,
        einspeisung_kwh=0.0, netzbezug_kwh=0.0, pv_erzeugung_kwh=900.0,
    ))
    await db.commit()

    maerz = (await lade_pv_je_monat(db, anlage.id, [alt, neu]))[(2025, 3)]

    assert set(maerz) == {alt.id}
    assert maerz[alt.id].pv_erzeugung_kwh == pytest.approx(900.0)
