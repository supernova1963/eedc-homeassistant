"""Zwei Quellen, eine Anlage: jede Einfuhr schreibt ihr eigenes Gerät (F-22, #349).

OliS2811 hat zwei Sofar-Wechselrichter, die Solarman als **zwei getrennte
Stationen** führt — in eedc ist das **eine** Anlage (ein Standort, ein
Hausanschluss; `models/anlage.py`, `ERLAUBTE_PARENT_TYPEN`). Der Apply-Endpunkt
kannte bis F-22 nur den anlagenweiten Weg, und der hat beide Ausgänge verdorben:

* **ohne** „überschreiben" wurde die **ganze Monatszeile** übersprungen, sobald
  die erste Station den Monat angelegt hatte (`data_import.py`, `continue` **vor**
  dem Geräte-Schreibweg) — die zweite Station war schlicht nicht importierbar;
* **mit** „überschreiben" wurde der Ertrag der zweiten Station nach kWp auf
  **alle** Stränge verteilt und die Hauszähler-Werte der ersten ersetzt — eine
  falsche Zahl ohne jede Warnung.

`test_ohne_ziel_verschluckt_der_monats_skip_die_zweite_quelle` hält das alte
Verhalten als **Gegenprobe** fest: Es ist derselbe Code, der ohne Ziel weiter
läuft, und es ist genau das, was Olli gemeldet hat. Fiele diese Zusicherung weg,
wäre der Fix nicht mehr belegt, sondern nur behauptet.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.api.routes.data_import import (
    ApplyMonthInput,
    ApplyRequest,
    apply_import,
)
from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.tests import factories


async def _zwei_wechselrichter(db, *, mit_speicher: bool = False) -> dict:
    """Ollis Aufbau: ein Haus, zwei WR, je ein PV-String (optional je Speicher)."""
    return await factories.zwei_wechselrichter(db, mit_speicher=mit_speicher)


def _monat(**werte) -> ApplyMonthInput:
    return ApplyMonthInput(jahr=2025, monat=6, **werte)


async def _pv_je_modul(db, ids) -> dict[str, float | None]:
    """Gemessener PV-Wert je String, nach Wechselrichter benannt."""
    ergebnis: dict[str, float | None] = {}
    for name in ("Sofar 2200", "Sofar 1100"):
        row = (await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == ids[name]["modul"],
                InvestitionMonatsdaten.jahr == 2025,
                InvestitionMonatsdaten.monat == 6,
            )
        )).scalar_one_or_none()
        ergebnis[name] = (
            None if row is None else (row.verbrauch_daten or {}).get("pv_erzeugung_kwh")
        )
    return ergebnis


# ─── Der Kernfall ────────────────────────────────────────────────────────────


async def test_zweite_quelle_schreibt_ihr_eigenes_geraet(db):
    """Beide Stationen liefern denselben Monat — beide Stränge tragen danach
    ihren eigenen gemessenen Wert, keiner den des anderen."""
    ids = await _zwei_wechselrichter(db)

    for name, kwh in (("Sofar 2200", 1000.0), ("Sofar 1100", 600.0)):
        antwort = await apply_import(
            anlage_id=ids["anlage"],
            data=ApplyRequest(
                monate=[_monat(pv_erzeugung_kwh=kwh)],
                ziel_investition_id=ids[name]["wr"],
            ),
            ueberschreiben=False,          # bewusst AUS — genau Ollis Lage
            datenquelle="cloud_import",
            db=db,
        )
        assert antwort.erfolg, antwort.fehler
        assert antwort.importiert == 1
        assert antwort.uebersprungen == 0

    assert await _pv_je_modul(db, ids) == {"Sofar 2200": 1000.0, "Sofar 1100": 600.0}


async def test_ohne_ziel_verschluckt_der_monats_skip_die_zweite_quelle(db):
    """**Gegenprobe.** Ohne Ziel gilt weiter der anlagenweite Weg: die zweite
    Einfuhr fällt am Monats-Skip aus, ihr Strang bleibt leer — und mit
    „überschreiben" bekäme er den Ertrag der ANDEREN Station anteilig
    zugeschrieben. Beides ist der gemeldete Fehler; er lebt hier als Beleg
    weiter, damit der Fix oben nicht nur behauptet ist."""
    ids = await _zwei_wechselrichter(db)

    erste = await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(monate=[_monat(pv_erzeugung_kwh=1000.0)]),
        ueberschreiben=False, datenquelle="cloud_import", db=db,
    )
    assert erste.importiert == 1

    zweite = await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(monate=[_monat(pv_erzeugung_kwh=600.0)]),
        ueberschreiben=False, datenquelle="cloud_import", db=db,
    )
    assert zweite.importiert == 0
    assert zweite.uebersprungen == 1

    # Die 1000 kWh der ERSTEN Station stehen nach kWp verteilt auf beiden
    # Strängen (625/375) — kein Strang trägt seine eigene Messung.
    werte = await _pv_je_modul(db, ids)
    assert werte == {"Sofar 2200": 625.0, "Sofar 1100": 375.0}


# ─── Die Hauszähler-Größen ───────────────────────────────────────────────────


async def test_hauszaehler_werte_kommen_in_die_monatszeile(db):
    """Einspeisung und Netzbezug gehören dem Haus — und werden übernommen.

    ⚠ **Dieser Test stand bis 2026-08-12 auf dem Kopf** (`..._bleiben_unberuehrt`,
    Zusicherung `md is None`). Er zementierte die Annahme, ein Wert aus EINER von
    zwei Stationen sei eine P7-Teilsumme. Das gilt für die **Erzeugung** — die
    misst der Wechselrichter selbst — und für den **Speicherumsatz**, nicht aber
    für Einspeisung und Netzbezug: die misst kein Wechselrichter, er bekommt sie
    vom Smartmeter am Hausanschluss. Zwei Geräte an einem Anschluss melden
    **denselben** Wert, nicht zwei Teile davon (Gernot, 12.08.).

    Die Folge der falschen Annahme war ein Anwender ohne Monatsabschluss: Import
    lief durch, Modulwerte kamen an, die Zählerzeile entstand nie (#349).
    """
    ids = await _zwei_wechselrichter(db)

    antwort = await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(
            monate=[_monat(
                pv_erzeugung_kwh=1000.0,
                einspeisung_kwh=700.0,
                netzbezug_kwh=400.0,
                eigenverbrauch_kwh=300.0,
            )],
            ziel_investition_id=ids["Sofar 2200"]["wr"],
        ),
        ueberschreiben=True, datenquelle="cloud_import", db=db,
    )

    md = (await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == ids["anlage"],
            Monatsdaten.jahr == 2025, Monatsdaten.monat == 6,
        )
    )).scalar_one_or_none()
    assert md is not None, "Der Stationsimport hat keine Monatszeile angelegt."
    assert md.einspeisung_kwh == 700.0
    assert md.netzbezug_kwh == 400.0

    # Das PV-Aggregat bleibt dagegen leer: DAS wäre die Teilsumme, die P7
    # verbietet — die Erzeugung steht gemessen an den Modulen.
    assert not md.pv_erzeugung_kwh, (
        "Die Stations-Erzeugung wurde als Anlagen-Aggregat geschrieben (P7)."
    )

    # Und der Import sagt, was mit den Größen des Hauses geschehen ist.
    assert any(
        "Hausanschluss" in w and "nicht" in w.lower() for w in antwort.warnungen
    ), antwort.warnungen


async def test_speicher_am_ziel_bekommt_die_batteriewerte(db):
    """Was unter dem Wechselrichter hängt, gehört zu ihm — der Speicher am
    ANDEREN Wechselrichter bleibt leer."""
    ids = await _zwei_wechselrichter(db, mit_speicher=True)

    await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(
            monate=[_monat(
                pv_erzeugung_kwh=1000.0,
                batterie_ladung_kwh=300.0,
                batterie_entladung_kwh=250.0,
            )],
            ziel_investition_id=ids["Sofar 2200"]["wr"],
        ),
        ueberschreiben=False, datenquelle="cloud_import", db=db,
    )

    async def _bat(inv_id):
        row = (await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv_id,
                InvestitionMonatsdaten.jahr == 2025,
                InvestitionMonatsdaten.monat == 6,
            )
        )).scalar_one_or_none()
        return None if row is None else row.verbrauch_daten

    assert await _bat(ids["Sofar 2200"]["speicher"]) == {
        "ladung_kwh": 300.0, "entladung_kwh": 250.0,
    }
    assert await _bat(ids["Sofar 1100"]["speicher"]) is None


# ─── Was das Ziel sein darf ──────────────────────────────────────────────────


async def test_fremde_investition_wird_abgewiesen(db):
    ids = await _zwei_wechselrichter(db)
    with pytest.raises(HTTPException) as exc:
        await apply_import(
            anlage_id=ids["anlage"],
            data=ApplyRequest(
                monate=[_monat(pv_erzeugung_kwh=1.0)],
                ziel_investition_id=999_999,
            ),
            ueberschreiben=False, datenquelle="cloud_import", db=db,
        )
    assert exc.value.status_code == 404


async def test_falscher_typ_nennt_den_richtigen(db):
    """Ein PV-Modul ist kein Ziel — Ziel ist das Gerät, UNTER dem die Module
    hängen. Die Meldung sagt das, statt nur „ungültig" zu melden."""
    ids = await _zwei_wechselrichter(db)
    with pytest.raises(HTTPException) as exc:
        await apply_import(
            anlage_id=ids["anlage"],
            data=ApplyRequest(
                monate=[_monat(pv_erzeugung_kwh=1.0)],
                ziel_investition_id=ids["Sofar 2200"]["modul"],
            ),
            ueberschreiben=False, datenquelle="cloud_import", db=db,
        )
    assert exc.value.status_code == 400
    assert "Wechselrichter" in exc.value.detail


async def test_wechselrichter_ohne_module_sagt_was_zu_tun_ist(db):
    """Am Wechselrichter selbst wird die Erzeugung NICHT geführt — der
    Monats-Fakten-SoT liest nur `pv-module`. Statt still an eine Stelle zu
    schreiben, die niemand liest, verlangt der Import die Module."""
    anlage = Anlage(anlagenname="Nackter WR", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Sofar solo",
        anschaffungsdatum=date(2023, 1, 1),
    )
    db.add(wr)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await apply_import(
            anlage_id=anlage.id,
            data=ApplyRequest(
                monate=[_monat(pv_erzeugung_kwh=1.0)],
                ziel_investition_id=wr.id,
            ),
            ueberschreiben=False, datenquelle="cloud_import", db=db,
        )
    assert exc.value.status_code == 400
    assert "keine PV-Module" in exc.value.detail


async def test_balkonkraftwerk_traegt_seine_erzeugung_selbst(db):
    """Ein BKW **ohne** Modul-Kinder ist sein eigener Empfänger.

    Seit N-266 darf ein `pv-module` unter einem Balkonkraftwerk hängen; die
    Bedingung in `loese_ziel` (`if not pv_module`) trennt die beiden Fälle
    weiterhin richtig. Mit Kindern schreibt der Import an die Kinder — das prüft
    `test_bkw_parent_pv_module_n266.py`.
    """
    anlage = Anlage(anlagenname="Mit BKW", leistung_kwp=0.8)
    db.add(anlage)
    await db.flush()
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=0.8,
    )
    db.add(bkw)
    await db.commit()

    antwort = await apply_import(
        anlage_id=anlage.id,
        data=ApplyRequest(
            monate=[_monat(pv_erzeugung_kwh=90.0)],
            ziel_investition_id=bkw.id,
        ),
        ueberschreiben=False, datenquelle="cloud_import", db=db,
    )
    assert antwort.erfolg, antwort.fehler

    row = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == bkw.id,
        )
    )).scalar_one()
    assert row.verbrauch_daten["pv_erzeugung_kwh"] == 90.0
