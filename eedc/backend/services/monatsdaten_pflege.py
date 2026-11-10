"""
Monatsdaten-Pflege — drei Handgriffe auf Monatswerte, je eine Funktion für Route und Reparatur-Operation.

Etappe E3 des Vorhabens «Daten-Checker: ein Handgriff je Befund» (Konzept §3.1 R6, Bauplan §3.1, Gegenprüfung W1): die
Logik stand inline in drei Routen von ``api/routes/monatsdaten.py``. Sie ist hier **wörtlich** herausgeschnitten, damit die
Routen und die Operationen der Reparatur-Werkbank (``services/repair_operationen_checker.py``) dieselbe Funktion rufen —
eine Wahrheit, keine Doppelung. Die Antworten der Routen sind bitgleich (Probe E3.1).

* ``geraetewerte_loeschen`` — Gerätewerte eines Monats **ohne** Zählerzeile löschen (#349; Route
  ``DELETE /api/monatsdaten/geraetewerte/{anlage_id}/{jahr}/{monat}``).
* ``feldwert_entfernen`` — gespeicherten Wert aus einem Feld entfernen, das das Gerät nicht führt (N-393; Route
  ``DELETE /api/monatsdaten/investition/{investition_id}/feld/{feld}``).
* ``temperatur_aus_messung`` — leere Ø-Temperaturen aus der eigenen Messreihe füllen (N-426-Nachtrag; Route
  ``POST /api/monatsdaten/anlage/{anlage_id}/temperatur-aus-messung``).

Fehlerfälle als Ausnahmen statt HTTP: ``PflegeNichtGefunden`` (Route: 404 mit ``not_found``-Wortlaut) und
``PflegeKonflikt`` (Route: 409 mit dem Text der Ausnahme — der Fall gehört auf einen anderen Weg). Die Reparatur-Operation
nimmt den Konflikt im **Plan** vorweg («nichts zu tun», Gegenprüfung Ü4). Jede Funktion schreibt und committet wie bisher
die Route; die Prüf-Funktionen ``*_lage`` lesen nur (für den Plan).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import basis_feld_key, groesse_gibt_es_am_geraet
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.mitteltemperatur import lade_monatsmittel_temperatur
from backend.services.provenance import write_with_provenance

#: Writer der manuellen Monatspflege (wie ``api/routes/monatsdaten._MANUAL_WRITER``, das von hier liest).
MANUAL_WRITER = "monatsdaten_form"


class PflegeNichtGefunden(LookupError):
    """Gegenstand fehlt — die Route antwortet 404 mit ``not_found(entity, id)``."""

    def __init__(self, entity: str, id_: int):
        super().__init__(f"{entity} {id_} nicht gefunden")
        self.entity = entity
        self.id = id_


class PflegeKonflikt(Exception):
    """Der Fall gehört auf einen anderen Weg — die Route antwortet 409 mit diesem Text."""


# ─── Gerätewerte ohne Zählerzeile (#349) ──────────────────────────────────────────────────────────────────────────

def _konflikt_zaehlerzeile(jahr: int, monat: int) -> PflegeKonflikt:
    return PflegeKonflikt(
        f"Der Monat {monat:02d}/{jahr} hat noch eine Zählerzeile. "
        "Bitte über „Monatsdaten löschen“ entfernen — dort lassen sich "
        "die Gerätewerte in einem Zug mitlöschen."
    )


async def _zaehlerzeile(db: AsyncSession, anlage_id: int, jahr: int, monat: int) -> Optional[Monatsdaten]:
    return (await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )).scalar_one_or_none()


async def geraetewerte_lage(db: AsyncSession, anlage_id: int, jahr: int, monat: int) -> list[dict]:
    """Nur lesend (Plan): die Gerätewerte des Monats je Komponente; ``PflegeKonflikt``, wenn die Zählerzeile steht."""
    from backend.services.monat_loeschen import beschreibe_geraetewerte_des_monats

    if await _zaehlerzeile(db, anlage_id, jahr, monat) is not None:
        raise _konflikt_zaehlerzeile(jahr, monat)
    return await beschreibe_geraetewerte_des_monats(db, anlage_id, jahr, monat)


async def geraetewerte_loeschen(db: AsyncSession, anlage_id: int, jahr: int, monat: int) -> dict:
    """Löscht die Gerätewerte eines Monats **ohne** Zählerzeile (#349).

    Der Gegenstand ist ein Monat, der in keiner Liste mehr auftaucht: seine
    `Monatsdaten`-Zeile ist gelöscht, die Messwerte je Komponente stehen noch.
    Genau dieser Rest weist einen erneuten Import ab — und weil der Monat
    nirgends erscheint, gibt es keine Zeile, über die man ihn aufräumen könnte.

    ⚠ Bewusst eng: Existiert die Zählerzeile noch, passiert **nichts**
    (``PflegeKonflikt``) — dann ist der Monat normal sichtbar und gehört über den
    Lösch-Dialog behandelt, der beides zusammen anbietet. Ein zweiter Weg zum
    selben Ziel wäre genau die Drift, aus der dieser Befund entstanden ist.
    """
    if await _zaehlerzeile(db, anlage_id, jahr, monat) is not None:
        raise _konflikt_zaehlerzeile(jahr, monat)

    from backend.services.monat_loeschen import (
        _geraetewerte_des_monats,
        beschreibe_geraetewerte_des_monats,
    )
    from backend.services.provenance import log_delete

    beschreibung = await beschreibe_geraetewerte_des_monats(db, anlage_id, jahr, monat)
    zeilen = await _geraetewerte_des_monats(db, anlage_id, jahr, monat)

    for imd in zeilen:
        log_delete(
            db, imd,
            source="manual:form",
            writer=MANUAL_WRITER,
            decision_reason=(
                f"verwaiste Gerätewerte {jahr}-{monat:02d} gelöscht (#349) — "
                "keine Monatsdaten-Zeile vorhanden"
            ),
        )
        await db.delete(imd)

    await db.commit()
    return {
        "jahr": jahr, "monat": monat,
        "geloescht": len(zeilen),
        "komponenten": [k["bezeichnung"] for k in beschreibung],
    }


# ─── Wert in einem nicht geführten Feld (N-393) ──────────────────────────────────────────────────────────────────

@dataclass
class FeldwertLage:
    """Nur lesend (Plan): das Gerät und die Monate, die einen Wert in ``feld`` tragen."""
    inv: Investition
    monate: list[dict]


async def _investition_ohne_feld(db: AsyncSession, investition_id: int, feld: str) -> Investition:
    inv = (await db.execute(
        select(Investition).where(Investition.id == investition_id)
    )).scalar_one_or_none()
    if inv is None:
        raise PflegeNichtGefunden("Investition", investition_id)

    basis = basis_feld_key(feld)
    if groesse_gibt_es_am_geraet(inv.typ, basis, inv.parameter or {}):
        raise PflegeKonflikt(
            f"Das Feld „{feld}“ ist an diesem Gerät vorgesehen und im "
            "Monatsabschluss erreichbar — bitte dort leeren."
        )
    return inv


async def feldwert_lage(db: AsyncSession, investition_id: int, feld: str) -> FeldwertLage:
    """Nur lesend (Plan): wie ``feldwert_entfernen``, ohne zu schreiben — die Monate mit Wert und der Wert."""
    inv = await _investition_ohne_feld(db, investition_id, feld)
    zeilen = (await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id == investition_id)
        .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )).scalars().all()
    monate = [{"jahr": imd.jahr, "monat": imd.monat, "wert": (imd.verbrauch_daten or {})[feld]}
              for imd in zeilen if feld in (imd.verbrauch_daten or {})]
    return FeldwertLage(inv=inv, monate=monate)


async def feldwert_entfernen(db: AsyncSession, investition_id: int, feld: str) -> dict:
    """Entfernt einen gespeicherten Wert aus einem Feld, das das Gerät nicht führt (N-393).

    Der Gegenstand ist ein Wert, an den der Anwender nicht mehr herankommt: Das
    Feld hat eine harte Bedingung (`INVESTITION_FELDER[...]["bedingung"]`), die
    am Gerät nicht mehr erfüllt ist — der Monatsabschluss zeigt es nicht, ein
    erneuter Abschluss merged je Sub-Key und lässt den Altwert stehen. Der
    Daten-Checker meldet den Zustand (`_check_werte_in_nicht_gefuehrten_feldern`).
    Entfernt wird der Wert in **allen** Monaten dieses Geräts, in denen die
    Größe nicht existiert — je Monat ein Audit-Eintrag
    (`remove_json_subkey_with_provenance`).

    ⚠ Bewusst eng, wie ``geraetewerte_loeschen`` (#349): Führt das Gerät das
    Feld, passiert **nichts** (``PflegeKonflikt``) — dann ist es im
    Monatsabschluss erreichbar und gehört dort geleert.
    """
    inv = await _investition_ohne_feld(db, investition_id, feld)

    from backend.services.provenance import remove_json_subkey_with_provenance

    zeilen = (await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id == investition_id)
        .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )).scalars().all()

    entfernt: list[dict] = []
    for imd in zeilen:
        if feld not in (imd.verbrauch_daten or {}):
            continue
        alter_wert = await remove_json_subkey_with_provenance(
            db, imd, "verbrauch_daten", feld,
            source="manual:form", writer=MANUAL_WRITER,
            decision_reason=(
                f"Wert in nicht geführtem Feld entfernt (N-393) — "
                f"{inv.typ} führt „{feld}“ nach seinen Einstellungen nicht"
            ),
        )
        entfernt.append({"jahr": imd.jahr, "monat": imd.monat, "wert": alter_wert})

    await db.commit()
    return {
        "investition_id": investition_id,
        "feld": feld,
        "entfernt": len(entfernt),
        "monate": entfernt,
    }


# ─── Ø-Temperatur aus der eigenen Messreihe (N-426-Nachtrag) ─────────────────────────────────────────────────────

@dataclass
class TemperaturLage:
    """Nur lesend (Plan): die Monate ohne Ø-Temperatur und die Werte, die die Messreihe für sie hat."""
    leer: list[Monatsdaten]
    erreichbar: list[dict]


async def temperatur_lage(db: AsyncSession, anlage_id: int) -> TemperaturLage:
    """Nur lesend: welche leeren Monate die Messreihe erreicht (dieselbe Auswahl wie ``temperatur_aus_messung``)."""
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one_or_none()
    if anlage is None:
        raise PflegeNichtGefunden("Anlage", anlage_id)

    messreihe = await lade_monatsmittel_temperatur(db, anlage_id)

    zeilen = list((await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id,
               Monatsdaten.durchschnittstemperatur.is_(None))
        .order_by(Monatsdaten.jahr, Monatsdaten.monat)
    )).scalars().all())
    erreichbar = [{"md": md, "jahr": md.jahr, "monat": md.monat, "wert": float(messreihe[(md.jahr, md.monat)])}
                  for md in zeilen if messreihe.get((md.jahr, md.monat)) is not None]
    return TemperaturLage(leer=zeilen, erreichbar=erreichbar)


async def temperatur_aus_messung(db: AsyncSession, anlage_id: int) -> dict:
    """Füllt leere Ø-Temperaturen aus der eigenen Messreihe (N-426-Nachtrag).

    Der Gegenstand ist eine **Historie**, die niemand mehr von Hand aufmacht:
    Zwischen dem IA-V4-Flip (25.07.2026) und WK-03 (13.09.2026) gab es keinen
    Wetter-Auto-Fill; jeder in dieser Zeit abgeschlossene Monat trägt in
    ``Monatsdaten.durchschnittstemperatur`` ``NULL``. Der zurückgebaute
    Auto-Fill wirkt nur nach vorn — für die Vergangenheit gibt es diesen Weg.

    ⛔ **Nur Lücken, nie ein gepflegter Wert (P3b).** Geschrieben wird
    ausschließlich, wo das Feld ``None`` ist; alles andere bleibt unberührt.
    Der Schreibweg ist ``write_with_provenance``, jeder gesetzte Wert steht
    damit im Audit-Log.

    ⚠ **Quelle ``manual:form``, und das ist bewusst so** — wie beim
    Nachbar-Knopf ``feldwert_entfernen`` (N-393). Es ist eine **vom Anwender
    ausgelöste** Aktion (SOURCE_LABELS: *„User-Eingabe oder User-bestätigte
    Aktion"*), und derselbe Wert, den er sich im Monatsformular per Auto-Fill
    holt und speichert, landet ebenfalls als ``manual:form`` in der Zeile. Zwei
    Labels für denselben Wert, je nachdem welchen Knopf jemand gedrückt hat,
    wären die Drift — auch wenn der Knopf seit E3 über die Reparatur-Werkbank
    läuft: es gibt nichts zu durchbrechen, das Feld ist leer.

    ⛔ **Nur, was die Messreihe hergibt, und kein Netzabruf.**
    ``lade_monatsmittel_temperatur`` **ohne** ``gepflegt_je_monat`` ist Stufe 1
    (Stundenmittel) und Stufe 2 (Tages-Min/Max) der Vorrangkette — ein
    Provider-Abruf je Monat ist bewusst **kein** Teil dieser Aktion
    ([[feedback_kein_grosser_heiler_knopf]]).

    ⭐ **Idempotent.** Ein zweiter Lauf findet nichts mehr — die Monate, die er
    gefüllt hat, sind nicht mehr leer.
    """
    lage = await temperatur_lage(db, anlage_id)

    gefuellt: list[dict] = []
    for e in lage.erreichbar:
        ergebnis = await write_with_provenance(
            db, e["md"], "durchschnittstemperatur", e["wert"],
            source="manual:form", writer=MANUAL_WRITER,
        )
        if ergebnis.applied:
            gefuellt.append(
                {"jahr": e["jahr"], "monat": e["monat"], "wert": e["wert"]}
            )

    await db.commit()
    return {
        "anlage_id": anlage_id,
        "gefuellt": len(gefuellt),
        "offen": len(lage.leer) - len(gefuellt),
        "monate": gefuellt,
    }
