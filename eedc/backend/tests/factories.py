"""Modell-Factories für den Backend-Testbaum (Etappe E4 / M6).

**Wozu.** Eine Modell-Konstruktion steht heute in 264 von 397 Testdateien
(`Anlage` 253 · `Investition` 220 · `Monatsdaten` 132 · `InvestitionMonatsdaten`
129 · `Strompreis` 50, gemessen 2026-08-23 per AST). Bekommt ein Modell ein
Pflichtfeld, ist das die Fläche, die angefasst werden muss. Diese Datei ist die
eine Stelle, an der ein solcher Umbau die Tests wieder erreicht.

**Zwei Formen, weil der Bestand zwei Muster hat** — reine Konstruktion ohne
Session (`mach_*`) und Anlegen samt `flush` (die kurzen Namen). Wer `commit`
braucht, ruft ihn danach selbst; das bleibt sichtbar im Test.

**Defaults nur für das technisch Nötige, nie für fachliche Werte.** Eine Factory,
die eine kWp, ein Land oder ein Datum erfindet, hält einen Test still grün, der
genau das behaupten wollte. Deshalb trägt `anlage()` einen Namen und eine kWp
(98 % bzw. 96 % aller Konstruktionen setzen sie, kein Test behauptet sie), aber
**kein** `standort_land` — das steuert die Kraftstoffpreis-Herkunft und gehört
in den Test, der es braucht.

Migration ist schleichend: neue Tests nutzen die Factories, alte bei Berührung.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.berechnungen.verbrauch import VerbrauchsKennzahlen
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)
from backend.services.monats_fakten import (
    BkwFakten,
    EegFakten,
    EmobFakten,
    ErzeugungFakten,
    MetaFakten,
    MonatsFakt,
    SonstigesFakten,
    SpeicherFakten,
    TarifFakten,
    WpFakten,
    ZaehlerFakten,
)

__all__ = [
    # §1 Modell-Factories
    "mach_anlage", "anlage",
    "mach_investition", "investition",
    "mach_imd", "imd",
    "mach_monatsdaten", "monatsdaten",
    "strompreis",
    # §2 Szenarien
    "anlage_mit_pv", "mach_anlage_mit_mapping", "anlage_mit_tarif",
    "anlage_mit_modul", "zwei_wechselrichter",
    # §3 Werte-Fakten (kein DB-Modell)
    "mach_kennzahlen", "mach_monats_fakt",
]


# ─────────────────────────────────────────────────────────────────────────────
# §1 Modell-Factories
# ─────────────────────────────────────────────────────────────────────────────

def mach_anlage(**felder: Any) -> Anlage:
    """Eine `Anlage` konstruieren, ohne sie zu speichern."""
    return Anlage(**{"anlagenname": "Test", "leistung_kwp": 10.0, **felder})


async def anlage(db: AsyncSession, **felder: Any) -> Anlage:
    """Eine `Anlage` anlegen und flushen — die `id` steht danach bereit."""
    obj = mach_anlage(**felder)
    db.add(obj)
    await db.flush()
    return obj


def mach_investition(typ: str, **felder: Any) -> Investition:
    """Eine `Investition` konstruieren. `bezeichnung` fällt auf den Typ zurück."""
    return Investition(**{
        "typ": typ,
        "bezeichnung": felder.pop("bezeichnung", typ),
        "anschaffungsdatum": date(2024, 1, 1),
        **felder,
    })


async def investition(
    db: AsyncSession, anlage_id: int, typ: str, **felder: Any
) -> Investition:
    """Eine `Investition` anlegen und flushen."""
    obj = mach_investition(typ, anlage_id=anlage_id, **felder)
    db.add(obj)
    await db.flush()
    return obj


def mach_imd(
    investition_id: int, jahr: int, monat: int, verbrauch_daten: dict, **felder: Any
) -> InvestitionMonatsdaten:
    """`InvestitionMonatsdaten` konstruieren — alle vier Felder sind Pflicht."""
    return InvestitionMonatsdaten(
        investition_id=investition_id, jahr=jahr, monat=monat,
        verbrauch_daten=verbrauch_daten, **felder,
    )


async def imd(
    db: AsyncSession, investition_id: int, jahr: int, monat: int,
    verbrauch_daten: dict, **felder: Any,
) -> InvestitionMonatsdaten:
    """`InvestitionMonatsdaten` anlegen (ohne flush — sie brauchen keine `id`)."""
    obj = mach_imd(investition_id, jahr, monat, verbrauch_daten, **felder)
    db.add(obj)
    return obj


def mach_monatsdaten(anlage_id: int, jahr: int, monat: int, **felder: Any) -> Monatsdaten:
    """`Monatsdaten` konstruieren. Netzbezug und Einspeisung sind 0, nicht geraten."""
    return Monatsdaten(**{
        "anlage_id": anlage_id, "jahr": jahr, "monat": monat,
        "netzbezug_kwh": 0.0, "einspeisung_kwh": 0.0, **felder,
    })


async def monatsdaten(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, **felder: Any
) -> Monatsdaten:
    """`Monatsdaten` anlegen."""
    obj = mach_monatsdaten(anlage_id, jahr, monat, **felder)
    db.add(obj)
    return obj


async def strompreis(
    db: AsyncSession, anlage_id: int, gueltig_ab: date,
    *, netzbezug_arbeitspreis_cent_kwh: float, einspeiseverguetung_cent_kwh: float,
    **felder: Any,
) -> Strompreis:
    """Einen `Strompreis` anlegen. Beide Preise sind Pflicht — sie sind die Aussage."""
    obj = Strompreis(
        anlage_id=anlage_id, gueltig_ab=gueltig_ab,
        netzbezug_arbeitspreis_cent_kwh=netzbezug_arbeitspreis_cent_kwh,
        einspeiseverguetung_cent_kwh=einspeiseverguetung_cent_kwh,
        **felder,
    )
    db.add(obj)
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# §2 Szenarien — mehr als ein Modell, in mehr als einer Datei gebraucht
# ─────────────────────────────────────────────────────────────────────────────

async def anlage_mit_pv(db: AsyncSession, sensor_mapping: dict) -> Anlage:
    """Anlage mit einem PV-Modul (Anschaffung 2020) und dem übergebenen Mapping."""
    a = await anlage(db, sensor_mapping=sensor_mapping)
    await investition(
        db, a.id, "pv-module", bezeichnung="PV", anschaffungsdatum=date(2020, 1, 1)
    )
    return a


def mach_anlage_mit_mapping(anlagenname: str) -> Anlage:
    """Anlage mit vollständigem Sensor-Mapping (Basis + zwei Investitionen).

    Nicht gespeichert — die beiden Nutzer geben sie an Aggregator-Funktionen
    weiter, ohne dass eine `id` vergeben sein müsste.
    """
    return mach_anlage(
        anlagenname=anlagenname,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={
            "basis": {
                "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
                "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
            },
            "investitionen": {
                "3": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
                "7": {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"}}},
            },
        },
    )


async def anlage_mit_tarif(db: AsyncSession, anlagenname: str) -> Anlage:
    """Anlage mit einem Tarif ab 2023: 30 ct Bezug, 8 ct Einspeisung, kein Grundpreis."""
    a = await anlage(db, anlagenname=anlagenname)
    await strompreis(
        db, a.id, date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=0.0,
    )
    return a


async def anlage_mit_modul(
    db: AsyncSession, *, anlagen_kwp: float, spalte: float | None, parameter: dict,
    bezeichnung: str, ausrichtung: str,
) -> Anlage:
    """Anlage mit genau einem PV-Modul, committet und mit geladenen Beziehungen.

    `bezeichnung` und `ausrichtung` sind Parameter und keine Vorgabe: einer der
    beiden Nutzer behauptet die Bezeichnung in der Checker-Meldung
    (`test_daten_checker_modul_details_kwp.py`).
    """
    a = await anlage(db, leistung_kwp=anlagen_kwp)
    await investition(
        db, a.id, "pv-module", bezeichnung=bezeichnung,
        anschaffungsdatum=date(2022, 5, 1), leistung_kwp=spalte,
        ausrichtung=ausrichtung, neigung_grad=30, parameter=parameter,
    )
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == a.id)
    )).scalar_one()


async def zwei_wechselrichter(db: AsyncSession, *, mit_speicher: bool = False) -> dict:
    """Ollis Aufbau: ein Haus, zwei Wechselrichter, je ein PV-String darunter.

    Das ist zugleich der Kanon: `pv-module` MUSS unter einem `wechselrichter`
    hängen (`PARENT_PFLICHT_TYPEN`). Optional hängt je ein Speicher am WR.
    """
    a = await anlage(db, anlagenname="Zwei Sofar", leistung_kwp=8.0)

    ids: dict = {"anlage": a.id}
    for name, kwp in (("Sofar 2200", 5.0), ("Sofar 1100", 3.0)):
        wr = await investition(
            db, a.id, "wechselrichter", bezeichnung=name,
            anschaffungsdatum=date(2023, 1, 1),
        )
        modul = await investition(
            db, a.id, "pv-module", bezeichnung=f"String {name}",
            anschaffungsdatum=date(2023, 1, 1), leistung_kwp=kwp,
            parent_investition_id=wr.id,
        )
        ids[name] = {"wr": wr.id, "modul": modul.id}
        if mit_speicher:
            sp = await investition(
                db, a.id, "speicher", bezeichnung=f"Akku {name}",
                anschaffungsdatum=date(2023, 1, 1), parent_investition_id=wr.id,
                parameter={"kapazitaet_kwh": 5.0},
            )
            ids[name]["speicher"] = sp.id

    await db.commit()
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# §3 Werte-Fakten — kein DB-Modell, aber dieselbe Pflichtfeld-Falle
# ─────────────────────────────────────────────────────────────────────────────
#
# `MonatsFakt` (ADR-002/P10) verlangt **acht** Teil-Fakten als Pflichtargumente.
# Wer nur den Eigenverbrauch behaupten will, baut sonst sieben Null-Objekte von
# Hand — und muss jedes davon anfassen, sobald ein Teil-Fakt dazukommt. Genau
# der Grund, aus dem §1 existiert (E4/M6), nur eine Ebene über den Modellen.
#
# ⚠ Dieselbe Regel wie oben: **keine fachlichen Werte**. Alles ist 0 bzw. leer;
# was ein Test behauptet, setzt er selbst.

def mach_kennzahlen(**felder: Any) -> VerbrauchsKennzahlen:
    """`VerbrauchsKennzahlen` mit allen sieben Pflichtfeldern auf 0.0."""
    return VerbrauchsKennzahlen(**{
        "pv_erzeugung_kwh": 0.0,
        "direktverbrauch_kwh": 0.0,
        "eigenverbrauch_kwh": 0.0,
        "gesamtverbrauch_kwh": 0.0,
        "autarkie_prozent": 0.0,
        "eigenverbrauchsquote_prozent": 0.0,
        "direktverbrauchsquote_prozent": 0.0,
        **felder,
    })


def mach_monats_fakt(jahr: int = 2026, monat: int = 6, **teile: Any) -> MonatsFakt:
    """Ein `MonatsFakt`, in dem nur die übergebenen Teil-Fakten etwas tragen.

    Beispiel::

        fakt = mach_monats_fakt(kennzahlen=mach_kennzahlen(eigenverbrauch_kwh=1000.0))
    """
    return MonatsFakt(**{
        "jahr": jahr,
        "monat": monat,
        "zaehler": ZaehlerFakten(),
        "erzeugung": ErzeugungFakten(),
        "bkw": BkwFakten(),
        "speicher": SpeicherFakten(),
        "emob": EmobFakten(),
        "wp": WpFakten(),
        "sonstiges": SonstigesFakten(),
        "tarif": TarifFakten(),
        "eeg": EegFakten(),
        "kennzahlen": mach_kennzahlen(),
        "meta": MetaFakten(),
        **teile,
    })
