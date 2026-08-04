"""P5-Invariante: „genau eine aktive PVGIS-Prognose je Anlage" (A17).

Der Sweep `docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md` §6 fand 23 Lesestellen
derselben Auswahlregel, 6 davon abweichend — und **eine Wurzel**: es gab keinen
Unique-Constraint, und der JSON-Backup-Import konnte den verletzten Zustand
erzeugen (`ist_aktiv=pvgis_data.get("ist_aktiv", True)` ohne vorherige
Deaktivierung). Aus einer Ursache wurden drei verschiedene Symptome:

* **HTTP 500** im Daten-Checker (`scalar_one_or_none()` ohne `limit`) — N84
* **HTTP 500** in der Social-Karte (dito) — N85
* **verdoppelter SOLL-PV** im Monatsbericht (`JOIN` ohne `limit`, `sum()`) — N83

**Rückbau 2026-07-31 (Paket B):** der N85-Einsprungpunkt ist entfallen —
`cockpit/social.py` ist gelöscht (die Oberfläche dazu gibt es seit dem
IA-V4-Flip nicht mehr). Die Datei prüft die Lesepfade seither über **vier**
statt fünf Einsprungpunkte; N85 selbst bleibt hier als Herkunft der Regel
stehen, denn er hat sie mit ausgelöst. ADR-002/P5 trägt die Zahl mit.

Diese Datei prüft drei Ebenen:

1. **Die Wurzel** — der partielle Unique-Index lässt den Zustand nicht mehr
   entstehen, und die Schreibpfade (neu abrufen · ältere aktivieren) laufen
   trotz Index fehlerfrei.
2. **Der Import** — ein Backup mit mehreren/keinen aktiven Prognosen landet
   deterministisch mit genau einer aktiven, und der Nutzer erfährt es.
3. **Die Lesepfade** — auf einer Installation, deren Index fehlt (die Anlage ist
   bewusst nicht blockierend), darf kein Lesepfad werfen oder verdoppeln. Dafür
   wird der Index in diesen Tests gezielt gelöscht: „nicht auslösbar" ist kein
   Ersatz für „robust", solange Bestands-Datenbanken ohne Index existieren
   können.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select, text

from backend.core.berechnungen import monatsfenster
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import (
    INDEX_EINE_AKTIVE_PROGNOSE,
    PVGISMonatsprognose,
    PVGISPrognose,
)

# Die ÄLTERE Prognose ist die vom Nutzer aktivierte — genau der Fall, den
# „die neueste" still übersteuern würde.
# Das SOLL-Fenster ist seit N-69 ein Parameter von `_load_soll_pv` (im laufenden
# Monat trägt es nur die abgelaufenen Tage). Diese Datei prüft **P5** — welche
# Prognose gelesen wird —, nicht die Kürzung: sie übergibt deshalb bewusst ein
# volles Fenster, fest verdrahtet statt aus `date.today()` abgeleitet.
VOLLER_MONAT = monatsfenster(2026, 5, heute=date(2026, 6, 1))

AKTIV_ALT_JAHR = 9_600.0
NEU_JAHR = 19_200.0
MONAT = 5


def _monatswerte(jahressumme: float) -> list[dict]:
    return [
        {"monat": m, "e_m": jahressumme / 12, "h_m": 100.0, "sd_m": 10.0}
        for m in range(1, 13)
    ]


async def _index_loeschen(db) -> None:
    """Stellt eine Bestands-DB ohne den Invarianten-Index nach.

    Nur so lässt sich „mehrere aktive Prognosen" überhaupt herstellen — und genau
    dieser Zustand ist der, gegen den die Lesepfade robust sein müssen.
    """
    await db.execute(text(f"DROP INDEX IF EXISTS {INDEX_EINE_AKTIVE_PROGNOSE}"))


async def _seed(db, *, zwei_aktive: bool) -> int:
    """10-kWp-Anlage, IST in Mai 2026, zwei Prognosen (alt aktiv, neu je nach Flag)."""
    anlage = Anlage(anlagenname="P5-Invariante", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=MONAT,
        einspeisung_kwh=300.0, netzbezug_kwh=200.0,
    ))
    modul = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
    )
    db.add(modul)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=modul.id, jahr=2026, monat=MONAT,
        verbrauch_daten={"pv_erzeugung_kwh": 800.0},
    ))

    gemeinsam = dict(
        anlage_id=anlage.id, latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, gesamt_leistung_kwp=10.0,
    )
    for jahr_kwh, abgerufen, aktiv in (
        (AKTIV_ALT_JAHR, datetime(2024, 3, 1, 12, 0), True),
        (NEU_JAHR, datetime(2026, 2, 1, 12, 0), zwei_aktive),
    ):
        prognose = PVGISPrognose(
            **gemeinsam, abgerufen_am=abgerufen,
            jahresertrag_kwh=jahr_kwh, spezifischer_ertrag_kwh_kwp=jahr_kwh / 10.0,
            monatswerte=_monatswerte(jahr_kwh), ist_aktiv=aktiv,
        )
        db.add(prognose)
        await db.flush()
        # Normalisierte Monatszeilen — der Monatsbericht liest sie, nicht das JSON.
        db.add(PVGISMonatsprognose(
            prognose_id=prognose.id, monat=MONAT,
            ertrag_kwh=jahr_kwh / 12, einstrahlung_kwh_m2=100.0,
        ))
    await db.commit()
    return anlage.id


# ============================================================================
# 1. Die Wurzel — der Index
# ============================================================================


async def test_index_verbietet_zwei_aktive_prognosen(db):
    """Der partielle Unique-Index lässt den Zustand nicht mehr entstehen."""
    from sqlalchemy.exc import IntegrityError

    anlage_id = await _seed(db, zwei_aktive=False)
    neu = (await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.jahresertrag_kwh == NEU_JAHR,
        )
    )).scalar_one()

    neu.ist_aktiv = True
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_index_erlaubt_beliebig_viele_inaktive(db):
    """Die Regel gilt nur für aktive Zeilen — die Historie bleibt unbeschränkt.

    Gegenprobe zur Wahl „partieller Index" statt `UniqueConstraint(anlage_id,
    ist_aktiv)`: letzterer würde auch zwei INAKTIVE verbieten und damit das
    Archiv kaputt machen, aus dem der Nutzer eine ältere reaktiviert.
    """
    anlage_id = await _seed(db, zwei_aktive=False)
    for p in (await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )).scalars().all():
        p.ist_aktiv = False
    await db.flush()

    assert (await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv.is_(False),
        )
    )).scalars().all().__len__() == 2


async def test_aeltere_prognose_aktivieren_funktioniert_trotz_index(db):
    """Der Kernfall des Features darf nicht am Index scheitern.

    `PUT /api/pvgis/prognose/{id}/aktivieren` aktiviert bewusst eine ältere
    Prognose — also eine mit KLEINERER id. Ohne das explizite Flush zwischen
    Deaktivieren und Aktivieren sortiert die Unit of Work die UPDATEs nach id und
    erzeugt für einen Moment zwei aktive Zeilen: IntegrityError bei einer völlig
    korrekten Nutzeraktion.
    """
    from backend.api.routes.pvgis import aktiviere_prognose

    anlage_id = await _seed(db, zwei_aktive=False)
    prognosen = list((await db.execute(
        select(PVGISPrognose)
        .where(PVGISPrognose.anlage_id == anlage_id)
        .order_by(PVGISPrognose.id)
    )).scalars().all())
    alt, neu = prognosen[0], prognosen[1]

    # Erst die neuere aktivieren (größere id) …
    await aktiviere_prognose(prognose_id=neu.id, db=db)
    await db.refresh(alt)
    await db.refresh(neu)
    assert (alt.ist_aktiv, neu.ist_aktiv) == (False, True)

    # … dann zurück auf die ältere (kleinere id) — der kritische Fall.
    await aktiviere_prognose(prognose_id=alt.id, db=db)
    await db.refresh(alt)
    await db.refresh(neu)
    assert (alt.ist_aktiv, neu.ist_aktiv) == (True, False)


async def test_bestands_bereinigung_deaktiviert_statt_zu_loeschen(db):
    """Die Start-Migration stellt die Invariante her, ohne Daten zu entfernen.

    Erwartung: die zuletzt abgerufene bleibt aktiv (dieselbe Zeile, die der
    Auswahl-SoT liest), die übrige wird `ist_aktiv = 0` — und ist damit weiter
    vorhanden und reaktivierbar (A16/N44: Migrationen löschen nicht).
    """
    from backend.core.database import (
        _migrate_pvgis_eine_aktive_prognose,
        _migrate_pvgis_index_eine_aktive,
    )

    await _index_loeschen(db)
    anlage_id = await _seed(db, zwei_aktive=True)

    conn = await db.connection()
    await conn.run_sync(_migrate_pvgis_eine_aktive_prognose)
    await conn.run_sync(_migrate_pvgis_index_eine_aktive)

    alle = list((await db.execute(
        select(PVGISPrognose)
        .where(PVGISPrognose.anlage_id == anlage_id)
        .order_by(PVGISPrognose.abgerufen_am)
    )).scalars().all())
    assert len(alle) == 2, "Die Migration hat gelöscht — sie darf nur deaktivieren."
    assert [p.ist_aktiv for p in alle] == [False, True], (
        "Aktiv bleiben muss die ZULETZT abgerufene — dieselbe Wahl wie im Auswahl-SoT."
    )

    # Idempotent: zweiter Durchlauf ändert nichts mehr.
    await conn.run_sync(_migrate_pvgis_eine_aktive_prognose)
    for p in alle:
        await db.refresh(p)
    assert [p.ist_aktiv for p in alle] == [False, True]


# ============================================================================
# 2. Der Import
# ============================================================================


def _backup(*, aktiv_flags: list[bool | None]) -> dict:
    """Minimales JSON-Backup mit N PVGIS-Prognosen; `None` = Feld fehlt."""
    prognosen = []
    for i, flag in enumerate(aktiv_flags):
        eintrag = {
            "latitude": 48.0, "longitude": 11.0,
            "neigung_grad": 30.0, "ausrichtung_grad": 0.0,
            "jahresertrag_kwh": 1000.0 * (i + 1),
            "spezifischer_ertrag_kwh_kwp": 100.0 * (i + 1),
            "abgerufen_am": f"202{i}-01-01T12:00:00",
            "monatswerte": _monatswerte(1000.0 * (i + 1)),
        }
        if flag is not None:
            eintrag["ist_aktiv"] = flag
        prognosen.append(eintrag)
    return {
        "export_version": "1.2",
        "anlage": {"anlagenname": "Restore-Test", "leistung_kwp": 10.0},
        "pvgis_prognosen": prognosen,
    }


async def _importieren(db, backup: dict):
    """Ruft den JSON-Import direkt auf (kein Upload-Roundtrip)."""
    import json as _json
    from io import BytesIO

    from fastapi import UploadFile

    from backend.api.routes.import_export.json_operations import import_json

    datei = UploadFile(
        filename="backup.json",
        file=BytesIO(_json.dumps(backup).encode("utf-8")),
    )
    return await import_json(file=datei, ueberschreiben=False, db=db)


@pytest.mark.parametrize("flags", [
    [True, True],          # Backup markiert BEIDE als aktiv (widersprüchlich)
    [None, None],          # Feld fehlt ganz — das war der Default-True-Fall
    [True, True, True],
])
async def test_import_erzeugt_genau_eine_aktive(db, flags):
    """Egal wie das Backup aussieht: danach ist genau eine Prognose aktiv."""
    ergebnis = await _importieren(db, _backup(aktiv_flags=flags))
    assert ergebnis.erfolg is True

    aktive = list((await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.ist_aktiv.is_(True))
    )).scalars().all())
    assert len(aktive) == 1
    # Die zuletzt abgerufene gewinnt — dieselbe Regel wie überall sonst.
    assert aktive[0].jahresertrag_kwh == pytest.approx(1000.0 * len(flags))
    # Nichts geht verloren: die übrigen bleiben als inaktive Historie.
    alle = list((await db.execute(select(PVGISPrognose))).scalars().all())
    assert len(alle) == len(flags)


async def test_import_sagt_es_wenn_er_normalisiert(db):
    """Stilles Zurechtbiegen wäre dasselbe Schweigen wie stilles Übernehmen."""
    ergebnis = await _importieren(db, _backup(aktiv_flags=[True, True]))
    assert any("aktiv" in w.lower() for w in ergebnis.warnungen), (
        f"Keine Warnung über die Normalisierung: {ergebnis.warnungen}"
    )


async def test_import_respektiert_eine_bewusst_aktivierte_aeltere(db):
    """Sagt das Backup eindeutig „die ältere ist aktiv", bleibt es dabei.

    Der Import darf den Nutzerwillen nicht durch „die neueste" ersetzen — das
    wäre genau die stumme Übersteuerung, gegen die P5 formuliert ist.
    """
    ergebnis = await _importieren(db, _backup(aktiv_flags=[True, False]))
    assert ergebnis.erfolg is True
    aktive = list((await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.ist_aktiv.is_(True))
    )).scalars().all())
    assert len(aktive) == 1
    assert aktive[0].jahresertrag_kwh == pytest.approx(1000.0)
    assert not any("aktiv" in w.lower() for w in ergebnis.warnungen), (
        "Ein eindeutiges Backup braucht keine Normalisierungs-Warnung."
    )


async def test_import_uebernimmt_abgerufen_am(db):
    """Ohne `abgerufen_am` wäre die Historie nach einem Restore ununterscheidbar
    und der Tiebreak `abgerufen_am DESC` beliebig."""
    await _importieren(db, _backup(aktiv_flags=[False, True]))
    alle = list((await db.execute(
        select(PVGISPrognose).order_by(PVGISPrognose.jahresertrag_kwh)
    )).scalars().all())
    assert [p.abgerufen_am.year for p in alle] == [2020, 2021]


# ============================================================================
# 3. Die Lesepfade — robust auch ohne Index
# ============================================================================


async def test_daten_checker_wirft_keinen_500_bei_zwei_aktiven(db):
    """N84: vorher `MultipleResultsFound` → HTTP 500 auf der ganzen Checker-Seite."""
    from backend.services.daten_checker import DatenChecker

    await _index_loeschen(db)
    anlage_id = await _seed(db, zwei_aktive=True)

    ergebnis = await DatenChecker(db).check_anlage(anlage_id)
    assert ergebnis.anlage_id == anlage_id
    assert ergebnis.ergebnisse, "Der Checker liefert keine Befunde mehr."


async def test_monatsbericht_soll_pv_wird_nicht_verdoppelt(db):
    """N83: der `JOIN` ohne `limit` summierte über ALLE aktiven Prognosen.

    Bei zwei aktiven Prognosen ist der erwartete Wert der Monatswert **einer**
    Prognose, und zwar der zuletzt abgerufenen (Tiebreak) — nicht die Summe.
    Vorher kamen hier 2.400 kWh statt 1.600 kWh: der Monatsbericht zeigte einen
    SOLL-Wert, den die Anlage nie erreichen konnte, und die SOLL/IST-Abweichung
    sowie die Grundlast-SOLL-Kachel rechneten damit weiter.
    """
    from backend.api.routes.aktueller_monat import _load_soll_pv

    await _index_loeschen(db)
    anlage_id = await _seed(db, zwei_aktive=True)

    soll = await _load_soll_pv(anlage_id, 2026, MONAT, db, VOLLER_MONAT)
    erwartet = round(NEU_JAHR / 12, 1)
    verdoppelt = round((AKTIV_ALT_JAHR + NEU_JAHR) / 12, 1)
    assert soll == pytest.approx(erwartet, abs=0.2), (
        f"SOLL-PV ist {soll}, erwartet {erwartet} "
        f"(Summe beider aktiven wäre {verdoppelt})."
    )
    assert soll != pytest.approx(verdoppelt, abs=0.2)


async def test_mehrere_aktive_liefern_deterministisch_die_zuletzt_abgerufene(db):
    """Kein Zufallswert: bei verletzter Invariante gewinnt `abgerufen_am DESC`."""
    from backend.services.prognose_auswahl import (
        lade_aktive_prognose,
        zaehle_aktive_prognosen,
    )

    await _index_loeschen(db)
    anlage_id = await _seed(db, zwei_aktive=True)

    assert await zaehle_aktive_prognosen(db, anlage_id) == 2
    for _ in range(3):
        gewaehlt = await lade_aktive_prognose(db, anlage_id)
        assert gewaehlt is not None
        assert gewaehlt.jahresertrag_kwh == pytest.approx(NEU_JAHR)


async def test_aeltere_aktive_gewinnt_ueber_die_neuere_inaktive(db):
    """Der Regelfall: `ist_aktiv` schlägt „neueste", in allen Lesepfaden.

    Hier über zwei unabhängige Pfade geprüft (Monatsbericht-SOLL und
    Cockpit-String-Sicht), damit nicht ein Pfad allein die Regel belegt.
    """
    from backend.api.routes.aktueller_monat import _load_soll_pv
    from backend.api.routes.cockpit.pv_strings import get_pv_strings

    anlage_id = await _seed(db, zwei_aktive=False)

    soll = await _load_soll_pv(anlage_id, 2026, MONAT, db, VOLLER_MONAT)
    assert soll == pytest.approx(round(AKTIV_ALT_JAHR / 12, 1), abs=0.2)

    strings = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert strings.prognose_gesamt_kwh == pytest.approx(AKTIV_ALT_JAHR / 12, abs=0.5)
