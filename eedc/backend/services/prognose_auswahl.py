"""SoT für die Auswahl der aktiven PVGIS-Prognose (Wurzelmuster P5).

**Die Regel:** ``ist_aktiv == True``, Tiebreak ``abgerufen_am DESC``, ``LIMIT 1``.

``ist_aktiv`` ist **Nutzerwille** — ``PUT /api/pvgis/prognose/{id}/aktivieren``
(`api/routes/pvgis.py`) erlaubt bewusst das Aktivieren einer ÄLTEREN Prognose,
etwa wenn ein PVGIS-Neuabruf mit falschen Stammdaten lief. „Die neueste" wäre
eine stumme Übersteuerung dieser Wahl, „irgendeine aktive" ein Zufallswert.

**Warum es diese Datei gibt (A14/A17, Muster P5):** die vier Zeilen standen
23-mal als Kopie im Repo. 17 Kopien waren regelkonform, 6 wichen ab — und die
Abweichungen sahen alle anders aus: zwei ``scalar_one_or_none()`` ohne ``limit``
warfen bei zwei aktiven Prognosen `MultipleResultsFound` → **HTTP 500**
(Daten-Checker, Social-Karte), ein ``JOIN`` ohne ``limit`` **verdoppelte** den
SOLL-PV-Wert im Monatsbericht, drei ``.first()`` ohne ``ORDER BY`` nahmen die
älteste. Eine Regel, die man 23-mal abschreiben muss, wird abweichend
abgeschrieben; ein Helper macht die Abweichung unmöglich statt unwahrscheinlich.

**Das LIMIT ist keine Kosmetik.** Die Invariante „genau eine aktive Prognose je
Anlage" wird seit A17 an der Wurzel gesichert (partieller Unique-Index +
Bestands-Bereinigung, `core/database.py`). Trotzdem führt jeder Lesepfad hier
das ``LIMIT`` mit: auf einer Installation, deren Index-Anlage fehlschlug (der
Migrationspfad ist bewusst nicht blockierend), muss ein Lesepfad einen
deterministischen Wert liefern statt einer Fehlerseite. Robustheit im Lesepfad
ist die Absicherung, der Index die Ursachenbehebung — nicht umgekehrt.

Ort bewusst `services/` und nicht:

* ``models/`` — kein SQLAlchemy-Hybrid, damit async- und sync-Session gleich
  behandelt werden (drei Aufrufformen, eine Regel).
* ``core/berechnungen/`` — dort liegen Formeln, keine Queries (ADR-001).
"""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.models.pvgis_prognose import PVGISMonatsprognose, PVGISPrognose

__all__ = [
    "aktive_prognose_query",
    "lade_aktive_prognose",
    "lade_aktive_prognose_sync",
    "lade_aktive_monatsprognosen",
    "zaehle_aktive_prognosen",
]


def aktive_prognose_query(anlage_id: int) -> Select:
    """Das Statement — für Aufrufer, die selbst ausführen (oder es als Subquery
    brauchen). Wer nur das Objekt will, nimmt `lade_aktive_prognose`."""
    return (
        select(PVGISPrognose)
        .where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv.is_(True),
        )
        .order_by(PVGISPrognose.abgerufen_am.desc())
        .limit(1)
    )


async def lade_aktive_prognose(
    db: AsyncSession, anlage_id: int
) -> PVGISPrognose | None:
    """Die aktive PVGIS-Prognose der Anlage, oder `None`.

    `None` heißt „keine aktive Prognose" — **kein** Fallback auf eine inaktive.
    Wer alle Prognosen deaktiviert hat, will keine SOLL-Werte sehen
    (`test_pv_strings_pvgis_auswahl.py::test_ohne_aktive_prognose_keine_soll_werte`).
    """
    result = await db.execute(aktive_prognose_query(anlage_id))
    return result.scalar_one_or_none()


def lade_aktive_prognose_sync(db: Session, anlage_id: int) -> PVGISPrognose | None:
    """Sync-Variante für Aufrufer mit klassischer `Session` (kein `await`)."""
    return db.execute(aktive_prognose_query(anlage_id)).scalar_one_or_none()


async def lade_aktive_monatsprognosen(
    db: AsyncSession, anlage_id: int, monat: int | None = None
) -> list[PVGISMonatsprognose]:
    """Die normalisierten Monatsprognosen **genau der aktiven** Prognose.

    Bewusst über ``prognose_id == <Subquery>`` und **nicht** per ``JOIN`` auf
    ``ist_aktiv``: ein JOIN liefert die Monatszeilen ALLER aktiven Prognosen,
    und ein ``sum()`` darüber verdoppelt den SOLL-Wert, sobald mehr als eine
    aktiv ist (das war der Monatsbericht-Befund N83). Die Subquery trägt das
    ``LIMIT 1`` in sich, das Ergebnis ist deshalb immer genau eine Prognose.
    """
    stmt = select(PVGISMonatsprognose).where(
        PVGISMonatsprognose.prognose_id.in_(
            select(PVGISPrognose.id)
            .where(
                PVGISPrognose.anlage_id == anlage_id,
                PVGISPrognose.ist_aktiv.is_(True),
            )
            .order_by(PVGISPrognose.abgerufen_am.desc())
            .limit(1)
            .scalar_subquery()
        )
    )
    if monat is not None:
        stmt = stmt.where(PVGISMonatsprognose.monat == monat)
    result = await db.execute(stmt.order_by(PVGISMonatsprognose.monat))
    return list(result.scalars().all())


async def zaehle_aktive_prognosen(db: AsyncSession, anlage_id: int) -> int:
    """Anzahl aktiver Prognosen der Anlage — Diagnose, kein Wertpfad.

    ``> 1`` heißt: die Invariante ist auf dieser Installation verletzt (Index
    fehlt oder Anlage schlug fehl). Die Lesepfade liefern dann trotzdem
    deterministisch die zuletzt abgerufene; diese Funktion macht den Zustand
    *sichtbar*, statt ihn stillschweigend zurechtzubiegen. Bewusst KEINE
    Selbstheilung im Lesepfad ([[feedback_kein_grosser_heiler_knopf]]).
    """
    from sqlalchemy import func

    result = await db.execute(
        select(func.count())
        .select_from(PVGISPrognose)
        .where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv.is_(True),
        )
    )
    return int(result.scalar() or 0)
