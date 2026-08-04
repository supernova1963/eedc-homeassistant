"""
Der Plausibilitäts-Check „>3× Vorjahr" und seine drei Ausnahmen.

1. #240 NongJoWo: der Inbetriebnahme-Monat taugt nicht als Vergleichsbasis —
   sonst meldet die Prüfung nach jeder ersten vollen Jahresrunde fälschlich.
2. #362 kingcap1: ein Erzeuger-Zubau erklärt den Einspeise-Sprung.
3. N-75: ein Verbraucher-Zubau erklärt den Netzbezugs-Sprung (das Gegenstück
   zu 2., seitenrein — jede Seite bekommt nur die Ausnahme ihrer Ursache).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.daten_checker import DatenChecker, CheckKategorie


async def _reload_anlage(session, anlage_id):
    result = await session.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one()
    monatsdaten = list((await session.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


async def test_keine_3x_warnung_bei_inbetriebnahme_im_vorjahresmonat(db):
    """NongJoWo: Anlage seit Ende März 2022 → 50 kWh im März 2022 (Bruchteil),
    261 kWh im März 2023 (voller Monat). Heuristik darf das nicht als 3×
    Vorjahresabweichung melden.
    """
    anlage = Anlage(
        anlagenname="TestAnlage",
        leistung_kwp=10.0,
        installationsdatum=date(2022, 3, 28),
    )
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2022, 3, 28), leistung_kwp=10.0,
    )
    db.add(pv)

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2022, monat=3,
        einspeisung_kwh=60.0, netzbezug_kwh=100.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=3,
        einspeisung_kwh=261.0, netzbezug_kwh=300.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    checker = DatenChecker(db)
    ergebnisse = await checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)

    vj_warnungen = [
        e for e in ergebnisse
        if e.kategorie == CheckKategorie.MONATSDATEN_PLAUSIBILITAET
        and "3×" in (e.meldung or "")
    ]
    assert len(vj_warnungen) == 0, (
        f"Keine 3×-Vorjahr-Warnung erwartet (Inbetriebnahme im "
        f"Vorjahresmonat), bekam: {[e.meldung for e in vj_warnungen]}"
    )


async def test_3x_warnung_bleibt_bei_normalem_vorjahresmonat(db):
    """Kontrolle: Wenn der Vorjahresmonat ein voller Monat ist (Anlage
    schon zwei Jahre älter), soll die Warnung weiterhin kommen.
    """
    anlage = Anlage(
        anlagenname="TestAnlage",
        leistung_kwp=10.0,
        installationsdatum=date(2020, 1, 15),
    )
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 15), leistung_kwp=10.0,
    )
    db.add(pv)

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2022, monat=3,
        einspeisung_kwh=60.0, netzbezug_kwh=100.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=3,
        einspeisung_kwh=261.0, netzbezug_kwh=300.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    checker = DatenChecker(db)
    ergebnisse = await checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)

    vj_warnungen = [
        e for e in ergebnisse
        if "3×" in (e.meldung or "") and "Einspeisung" in (e.meldung or "")
    ]
    assert len(vj_warnungen) == 1, (
        f"Erwartet: genau 1 Einspeisung-3×-Warnung, bekam "
        f"{len(vj_warnungen)}: {[e.meldung for e in vj_warnungen]}"
    )


async def test_kein_3x_alarm_wenn_die_anlage_zwischenzeitlich_ausgebaut_wurde(db):
    """#362 kingcap1: Anlage 2023 mit 3 kWp gestartet, 2024 auf 12 kWp
    ausgebaut. Die Einspeisung steigt dadurch um das Vierfache — das ist der
    Ausbau, keine Anomalie. Die Schwelle wächst mit der installierten Leistung
    mit (3× → 12×), die Warnung bleibt aus."""
    anlage = Anlage(
        anlagenname="AusbauAnlage",
        leistung_kwp=12.0,
        installationsdatum=date(2023, 1, 10),
    )
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Erste Stufe",
        anschaffungsdatum=date(2023, 1, 10), leistung_kwp=3.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Ausbau 2024",
        anschaffungsdatum=date(2024, 3, 1), leistung_kwp=9.0,
    ))

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=5,
        einspeisung_kwh=61.0, netzbezug_kwh=100.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=888.0, netzbezug_kwh=110.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    checker = DatenChecker(db)
    ergebnisse = await checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)

    vj_warnungen = [
        e for e in ergebnisse
        if "Vorjahr" in (e.meldung or "") and "Einspeisung" in (e.meldung or "")
    ]
    assert len(vj_warnungen) == 0, (
        f"Ausbau von 3 auf 12 kWp erklärt den Sprung — keine Warnung erwartet, "
        f"bekam: {[e.meldung for e in vj_warnungen]}"
    )


async def test_netzbezug_warnung_bleibt_trotz_ausbau(db):
    """Gegenprobe zu #362: Der Ausbau entschuldigt nur die Einspeisung. Der
    Netzbezug sinkt mit mehr PV — springt er trotzdem, ist das unabhängig vom
    Zubau auffällig und muss gemeldet werden."""
    anlage = Anlage(
        anlagenname="AusbauNetzbezug",
        leistung_kwp=12.0,
        installationsdatum=date(2023, 1, 10),
    )
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Erste Stufe",
        anschaffungsdatum=date(2023, 1, 10), leistung_kwp=3.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Ausbau 2024",
        anschaffungsdatum=date(2024, 3, 1), leistung_kwp=9.0,
    ))

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=5,
        einspeisung_kwh=61.0, netzbezug_kwh=100.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=888.0, netzbezug_kwh=900.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    checker = DatenChecker(db)
    ergebnisse = await checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)

    meldungen = [e.meldung or "" for e in ergebnisse if "Vorjahr" in (e.meldung or "")]
    assert any("Netzbezug" in m for m in meldungen), (
        f"Netzbezug-Warnung fehlt trotz 9× Sprung: {meldungen}"
    )
    assert not any("Einspeisung" in m for m in meldungen), (
        f"Einspeisung darf bei Ausbau nicht melden: {meldungen}"
    )


async def _anlage_mit_wp(db, *, wp_ab: date, netzbezug_2024: float = 900.0):
    """Grundaufbau für die Verbraucher-Zubau-Fälle: PV seit 2020, ein
    Vorjahresmonat (05/2023) und ein Prüfmonat (05/2024) mit Netzbezugs-Sprung.
    """
    anlage = Anlage(
        anlagenname="WpZubau",
        leistung_kwp=10.0,
        installationsdatum=date(2020, 1, 15),
    )
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 15), leistung_kwp=10.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=wp_ab,
    ))

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=5,
        einspeisung_kwh=400.0, netzbezug_kwh=250.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=410.0, netzbezug_kwh=netzbezug_2024,
    ))
    await db.commit()
    return await _reload_anlage(db, anlage.id)


async def _vorjahr_meldungen(db, anlage, monatsdaten) -> list[str]:
    checker = DatenChecker(db)
    ergebnisse = await checker._check_monatsdaten_plausibilitaet(anlage, monatsdaten)
    return [e.meldung or "" for e in ergebnisse if "Vorjahr" in (e.meldung or "")]


async def test_kein_netzbezug_alarm_nach_waermepumpen_einbau(db):
    """N-75: Die WP kam im September 2023 dazu — im Mai 2023 gab es sie noch
    nicht, im Mai 2024 heizt sie. Der verdreifachte Netzbezug ist damit
    strukturell erklärt; eine WARNING wäre ein Befund, den der Anwender nicht
    auflösen kann.
    """
    anlage, monatsdaten = await _anlage_mit_wp(db, wp_ab=date(2023, 9, 1))

    meldungen = await _vorjahr_meldungen(db, anlage, monatsdaten)
    assert not any("Netzbezug" in m for m in meldungen), (
        f"WP-Zubau erklärt den Netzbezugs-Sprung — keine Warnung erwartet, "
        f"bekam: {meldungen}"
    )


async def test_netzbezug_alarm_bleibt_ohne_zubau(db):
    """Gegenprobe: dieselbe Anlage, aber die WP stand schon 2022. Dann erklärt
    nichts den Sprung und die Warnung muss kommen.
    """
    anlage, monatsdaten = await _anlage_mit_wp(db, wp_ab=date(2022, 3, 1))

    meldungen = await _vorjahr_meldungen(db, anlage, monatsdaten)
    assert any("Netzbezug" in m for m in meldungen), (
        f"Ohne Zubau muss der Netzbezugs-Sprung gemeldet werden: {meldungen}"
    )


async def test_verbraucher_zubau_entschuldigt_die_einspeisung_nicht(db):
    """Die Ausnahme ist seitenrein: ein neuer Verbraucher erklärt den
    Netzbezug, nicht die Einspeisung. Springt die trotzdem, bleibt die Meldung.
    """
    anlage = Anlage(
        anlagenname="WpUndEinspeisung",
        leistung_kwp=10.0,
        installationsdatum=date(2020, 1, 15),
    )
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 15), leistung_kwp=10.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2023, 9, 1),
    ))

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=5,
        einspeisung_kwh=100.0, netzbezug_kwh=250.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=900.0, netzbezug_kwh=900.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    meldungen = await _vorjahr_meldungen(db, anlage, monatsdaten)
    assert any("Einspeisung" in m for m in meldungen), (
        f"Der Wallbox-Zubau erklärt die Einspeisung nicht: {meldungen}"
    )
    assert not any("Netzbezug" in m for m in meldungen), (
        f"Den Netzbezug erklärt er sehr wohl: {meldungen}"
    )


async def test_austausch_ist_kein_zubau(db):
    """Alte WP stillgelegt, neue angeschafft: die Anzahl bleibt gleich, also
    ist der Sprung nicht erklärt und die Warnung bleibt.
    """
    anlage = Anlage(
        anlagenname="WpAustausch",
        leistung_kwp=10.0,
        installationsdatum=date(2020, 1, 15),
    )
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 15), leistung_kwp=10.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP alt",
        anschaffungsdatum=date(2021, 1, 1), stilllegungsdatum=date(2023, 8, 31),
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP neu",
        anschaffungsdatum=date(2023, 9, 1),
    ))

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2023, monat=5,
        einspeisung_kwh=400.0, netzbezug_kwh=250.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=410.0, netzbezug_kwh=900.0,
    ))
    await db.commit()

    anlage, monatsdaten = await _reload_anlage(db, anlage.id)
    meldungen = await _vorjahr_meldungen(db, anlage, monatsdaten)
    assert any("Netzbezug" in m for m in meldungen), (
        f"Ein Austausch ist kein Zubau — die Warnung muss bleiben: {meldungen}"
    )


async def test_sonstiges_zaehlt_nur_als_verbraucher(db):
    """`sonstiges` kann beides sein. Ein neues BHKW (Kategorie „erzeuger")
    erklärt keinen Netzbezugs-Sprung, ein neuer Pool (Kategorie
    „verbraucher") schon.
    """
    async def _lauf(kategorie: str) -> list[str]:
        anlage = Anlage(
            anlagenname=f"Sonstiges-{kategorie}",
            leistung_kwp=10.0,
            installationsdatum=date(2020, 1, 15),
        )
        db.add(anlage)
        await db.flush()

        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
            anschaffungsdatum=date(2020, 1, 15), leistung_kwp=10.0,
        ))
        db.add(Investition(
            anlage_id=anlage.id, typ="sonstiges", bezeichnung="Neuzugang",
            anschaffungsdatum=date(2023, 9, 1), parameter={"kategorie": kategorie},
        ))

        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2023, monat=5,
            einspeisung_kwh=400.0, netzbezug_kwh=250.0,
        ))
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2024, monat=5,
            einspeisung_kwh=410.0, netzbezug_kwh=900.0,
        ))
        await db.commit()

        anlage, monatsdaten = await _reload_anlage(db, anlage.id)
        return await _vorjahr_meldungen(db, anlage, monatsdaten)

    erzeuger_meldungen = await _lauf("erzeuger")
    assert any("Netzbezug" in m for m in erzeuger_meldungen), (
        f"Ein Erzeuger unter Sonstiges erklärt keinen Netzbezugs-Sprung: "
        f"{erzeuger_meldungen}"
    )

    verbraucher_meldungen = await _lauf("verbraucher")
    assert not any("Netzbezug" in m for m in verbraucher_meldungen), (
        f"Ein Verbraucher unter Sonstiges erklärt ihn: {verbraucher_meldungen}"
    )

