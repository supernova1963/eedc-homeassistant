"""
Akzeptanztest: Daten-Checker respektiert `stilllegungsdatum` in der
kWp-Σ und im Sensor-Mapping-Vollständigkeits-Check (#608 MartyBr).

Hintergrund: Bei einer String-Verlegung zwischen Wechselrichtern wird der
alte String stillgelegt (Stilllegungsdatum gesetzt, `aktiv` bleibt True
für historische Auswertungen). Beim großen `ist_aktiv_im_monat`-Sweep
v3.29.0 (#236) hatten zwei Daten-Checker-Pfade die Filterung nicht
übernommen: kWp-Summe addierte den stillgelegten String mit, und der
Sensor-Mapping-Check bemängelte fehlende Entität an einer Komponente,
die gar keine Daten mehr liefern soll.
        eedc/backend/tests/test_daten_checker_stilllegung.py
"""

from __future__ import annotations

from datetime import date, timedelta


from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage, Investition, Strompreis,
)


async def _seed(db: AsyncSession, total_kwp: float) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=total_kwp)
    db.add(anlage)
    await db.flush()
    return anlage


def _add_module(
    db: AsyncSession, anlage_id: int, bezeichnung: str, kwp: float,
    anschaffungsdatum: date,
    stilllegungsdatum: date | None = None,
    aktiv: bool = True,
):
    inv = Investition(
        anlage_id=anlage_id, typ="pv-module", bezeichnung=bezeichnung,
        leistung_kwp=kwp, anschaffungsdatum=anschaffungsdatum,
        stilllegungsdatum=stilllegungsdatum, aktiv=aktiv,
    )
    db.add(inv)
    return inv


async def test_kwp_summe_ignoriert_stillgelegten_string(db):
    """MartyBr-Befund: Σ aktiver kWp inkludierte stillgelegten Ost-String.
    Nach Fix: nur Module ohne (oder mit zukünftigem) Stilllegungsdatum zählen.
    """
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Vor 1 Jahr verlegt: Ost-String wurde von WR-A zu WR-B verlegt.
    # Alter Eintrag stillgelegt, neuer aktiv. Anlagenleistung 16 kWp =
    # 6 (Süd) + 4 (West) + 6 (Ost neu).  Ohne Filter würde der Checker
    # 21.8 kWp errechnen (inkl. 5.8 alter Ost) und ein Mismatch melden.
    anlage = await _seed(db, total_kwp=16.0)
    gestern = date.today() - timedelta(days=365)
    _add_module(db, anlage.id, "Süd", 6.0, anschaffungsdatum=date(2024, 1, 1))
    _add_module(db, anlage.id, "West", 4.0, anschaffungsdatum=date(2024, 1, 1))
    _add_module(
        db, anlage.id, "Ost (alt, verlegt)", 5.8,
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=gestern,
    )
    _add_module(db, anlage.id, "Ost (neu)", 6.0, anschaffungsdatum=gestern)
    await db.commit()

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()

    checker = DatenChecker(db)
    ergebnisse = checker._check_stammdaten(anlage)

    # OK-Meldung muss die Summe der drei aktiven Module zeigen (16.0 kWp,
    # 3 Modul-Gruppen) — ohne den stillgelegten Ost-Eintrag.
    ok_meldungen = [r for r in ergebnisse if "PV-Module:" in r.meldung]
    assert len(ok_meldungen) == 1, f"Erwarte 1 PV-Modul-Σ-Meldung, fand {len(ok_meldungen)}"
    msg = ok_meldungen[0].meldung
    assert "16.0 kWp" in msg, f"Σ aktiver kWp sollte 16.0 sein (ohne stillgelegten String), war: {msg}"
    assert "3 Modul-Gruppen" in msg, f"3 aktive Module erwartet, war: {msg}"

    # Kein Mismatch-WARNING
    warnings = [r for r in ergebnisse if "stimmt nicht" in r.meldung]
    assert len(warnings) == 0, (
        f"Kein kWp-Mismatch erwartet (Σ aktiv == Anlagenleistung), "
        f"fand: {[w.meldung for w in warnings]}"
    )


async def test_sensor_mapping_check_ignoriert_stillgelegten_string(db):
    """MartyBr-Befund: stillgelegter String wurde im Sensor-Mapping-
    Vollständigkeits-Check bemängelt, obwohl keine Sensor-Zuordnung
    mehr sinnvoll ist."""
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = await _seed(db, total_kwp=10.0)
    gestern = date.today() - timedelta(days=30)
    # Aktiver Süd mit gemapptem Sensor
    _add_module(db, anlage.id, "Süd", 10.0, anschaffungsdatum=date(2024, 1, 1))
    # Stillgelegter Ost ohne Sensor — soll NICHT bemängelt werden
    _add_module(
        db, anlage.id, "Ost (alt)", 5.0,
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=gestern,
    )
    await db.flush()
    # Sensor-Mapping für die aktive Süd-Investition:
    sued_id = next(i.id for i in (await db.execute(select(Investition))).scalars() if i.bezeichnung == "Süd")
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einspeisung"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netzbezug"},
        },
        "investitionen": {
            str(sued_id): {
                "felder": {
                    "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.sued_kwh"},
                },
            },
        },
    }
    await db.commit()

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()

    checker = DatenChecker(db)
    ergebnisse = checker._check_energieprofil_abdeckung(anlage)

    # Erwartung: OK-Meldung „Alle 1 aktive Komponenten haben kWh-Zähler
    # gemappt" — der stillgelegte Ost-String wird gar nicht erst geprüft.
    ok = [r for r in ergebnisse if "aktiven Komponenten haben kWh-Zähler gemappt" in r.meldung]
    assert len(ok) == 1, (
        f"Erwarte 1 OK-Meldung für vollständige Abdeckung, fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )
    assert "Alle 1" in ok[0].meldung, (
        f"Erwarte Zählung '1' (nur Süd ist aktiv), war: {ok[0].meldung}"
    )

    # Kein WARNING zu fehlender Komponenten-Abdeckung
    warnings = [r for r in ergebnisse if "ohne vollständige kWh-Zähler-Abdeckung" in r.meldung]
    assert len(warnings) == 0, (
        f"Stillgelegter String darf nicht bemängelt werden, fand:\n"
        + "\n".join(f"  {w.meldung}: {w.details}" for w in warnings)
    )


async def test_zukuenftig_stillgelegt_zaehlt_weiterhin(db):
    """Wenn das Stilllegungsdatum in der Zukunft liegt (geplante Verlegung),
    zählt das Modul heute noch als aktiv — kein vorzeitiger Ausschluss."""
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = await _seed(db, total_kwp=10.0)
    morgen = date.today() + timedelta(days=30)
    _add_module(db, anlage.id, "Süd", 6.0, anschaffungsdatum=date(2024, 1, 1))
    _add_module(
        db, anlage.id, "Geplant abgeschaltet", 4.0,
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=morgen,
    )
    await db.commit()

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()

    checker = DatenChecker(db)
    ergebnisse = checker._check_stammdaten(anlage)
    ok = [r for r in ergebnisse if "PV-Module:" in r.meldung]
    assert len(ok) == 1
    assert "10.0 kWp" in ok[0].meldung
    assert "2 Modul-Gruppen" in ok[0].meldung


async def test_check_investitionen_ignoriert_stillgelegte_stammdaten(db):
    """Stamm-Daten-Checks (kWp/Ausrichtung/Kosten fehlt) sollen nicht mehr
    am stillgelegten Eintrag nörgeln — der Anwender hat die Komponente
    abgehakt und braucht keine Vervollständigung."""
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = await _seed(db, total_kwp=10.0)
    gestern = date.today() - timedelta(days=30)
    # Aktiv und vollständig
    _add_module(db, anlage.id, "Süd", 10.0, anschaffungsdatum=date(2024, 1, 1))
    # Stillgelegt mit fehlender kWp + Ausrichtung — soll nicht mehr meckern
    unvoll = Investition(
        anlage_id=anlage.id, typ="pv-module",
        bezeichnung="Ost (alt, lückenhaft)",
        leistung_kwp=None,
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=gestern,
        aktiv=True,
    )
    db.add(unvoll)
    await db.commit()

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()

    checker = DatenChecker(db)
    ergebnisse = checker._check_investitionen(anlage, monatsdaten=[])
    nag = [r for r in ergebnisse if "Ost (alt" in r.meldung]
    assert nag == [], (
        f"Stamm-Daten-Hinweise zum stillgelegten Ost-Modul erwartet wären leer, "
        f"fand: {[r.meldung for r in nag]}"
    )


async def test_spezialtarif_nag_verschwindet_bei_stillgelegter_wp(db):
    """Wenn die einzige WP stillgelegt ist, soll der Checker nicht mehr
    den fehlenden WP-Spezialtarif anmahnen — die Komponente bezieht
    keinen Strom mehr."""
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = await _seed(db, total_kwp=10.0)
    gestern = date.today() - timedelta(days=30)
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="WP (außer Betrieb)",
        anschaffungsdatum=date(2023, 1, 1),
        stilllegungsdatum=gestern,
        aktiv=True,
    )
    db.add(wp)
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.commit()

    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen), selectinload(Anlage.strompreise))
        .where(Anlage.id == anlage.id)
    )).scalar_one()

    checker = DatenChecker(db)
    ergebnisse = checker._check_strompreise(anlage)
    wp_nag = [r for r in ergebnisse if "Wärmepumpe" in r.meldung or "wärmepumpe" in r.meldung.lower()]
    assert wp_nag == [], (
        f"Kein WP-Spezialtarif-Hinweis für stillgelegte WP erwartet, "
        f"fand: {[r.meldung for r in wp_nag]}"
    )


async def test_pv_erzeugung_map_filtert_post_stilllegung_imds(db):
    """Historische IMDs vor Stilllegung zählen mit, post-Stilllegung-IMDs
    werden ignoriert — sonst werden Werte des stillgelegten Moduls als
    aktuelle PV-Erzeugung gezählt."""
    from backend.services.daten_checker import DatenChecker
    from backend.models import InvestitionMonatsdaten
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = await _seed(db, total_kwp=10.0)
    _add_module(db, anlage.id, "Süd", 10.0,
                anschaffungsdatum=date(2024, 1, 1),
                stilllegungsdatum=date(2024, 6, 30))
    await db.flush()
    sued_id = (await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalar_one().id
    # Innerhalb Lebensspanne: zählt
    db.add(InvestitionMonatsdaten(
        investition_id=sued_id, jahr=2024, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 500.0},
    ))
    # Nach Stilllegung: zählt NICHT (Datenartefakt, manuell falsch erfasst)
    db.add(InvestitionMonatsdaten(
        investition_id=sued_id, jahr=2024, monat=8,
        verbrauch_daten={"pv_erzeugung_kwh": 600.0},
    ))
    await db.commit()

    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()

    checker = DatenChecker(db)
    pv_map = checker._get_pv_erzeugung_map(anlage)
    assert pv_map.get((2024, 5)) == 500.0, f"Mai-IMD soll zählen, Karte: {pv_map}"
    assert (2024, 8) not in pv_map, f"August-IMD nach Stilllegung darf nicht zählen, Karte: {pv_map}"
