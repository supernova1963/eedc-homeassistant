"""Modus-Split beim Monatsabschluss festschreiben (#263 K-2, S3 — Entscheid E-A/E-I).

**Warum persistiert und nicht bei jedem Lesen gerechnet** (Entscheid E-A): Das
ist die **ADR-002/P8-Klasse**. Eine on-the-fly gerechnete Wärme schriebe bei
jeder JAZ-Korrektur die **gesamte Historie** um — genau der Fehler, den P8 für
Tarife abgeschafft hat („ein Wert trägt den Stichtag seines Monats").
Persistiert trägt jeder Monat den damals gültigen Faktor.

⚠ **Derselbe Satz, umgedreht, ist der Preis:** eine *korrigierte* JAZ heilt
alte Monate **nicht**. Das gehört in den Anwender-Text, nicht ins
Kleingedruckte.

---

**Warum hier nichts überschrieben werden kann.** Geschrieben wird mit der
Quelle ``auto:monatsabschluss`` = ``SourcePriority.AUTO_AGGREGATION`` (3).
``MANUAL`` ist 1, ``EXTERNAL_AUTHORITATIVE`` (Cloud-Import, HA-Statistics) ist
2 — beide **schlagen** diesen Schreiber. Damit gilt *„gemessen schlägt
abgeleitet"* (Konzept §3.4, Präzedenz ADR-002/P7 bei der PV) **per
Konstruktion**: wer einen Wärmemengenzähler zuordnet oder die Heizwärme von
Hand pflegt, behält seinen Wert. Es braucht dafür keine Sonderregel in dieser
Datei — und deshalb steht hier auch keine.

**Die zwei Teilmengen und die Abdeckung** haben diesen Wettbewerb gar nicht:
ihre Feldnamen sind neu (``MODUS_SPLIT_FELDER``, Entscheid E-G) und es gibt
keinen zweiten Schreiber darauf.

---

**Die Invariante ist der Schutz, nicht die Normierung.** ``Σ Teilmengen >
Gesamtwert`` ⇒ für dieses Gerät wird **gar nichts** geschrieben, und die alten
Werte werden entfernt. Nicht gekappt: eine stille Kappung machte aus einem
Widerspruch eine plausibel aussehende Zahl. Auslöser sind zwei reale Fälle —
die Achse-2-Drift zwischen Leistungs- und Zählerpfad (#356, bei der Wallbox
einmal Faktor ≈ 2) und der schlicht kleiner von Hand gepflegte Monatswert.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen import (
    ModusSplit,
    abgeleitete_heizwaerme_kwh,
    teilmengen_passen,
)
from backend.core.betriebsmodus import (
    MODUS_ABDECKUNG_FELD,
    MODUS_SPLIT_FELDER,
    MODUS_STROM_FELD,
)
from backend.core.field_definitions import get_wp_strom_kwh
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.energie_profil.modus_split_monat import lade_modus_split_monat
from backend.services.provenance import (
    ABGELEITET_JAZ_MODUS,
    write_json_subkey_with_provenance,
)

logger = logging.getLogger(__name__)

_WRITER = "modus_split"
_QUELLE = "auto:monatsabschluss"


@dataclass
class ModusSplitSchreibErgebnis:
    """Was der Schritt getan hat — für Log und Diagnose, nicht für den Anwender."""

    geschrieben: int = 0
    #: Geräte, bei denen die Teilmengen-Invariante verletzt war. Sie bekommen
    #: keinen Split; der Daten-Checker macht daraus einen Hinweis.
    widerspruch: list[int] = field(default_factory=list)
    #: Geräte, für die eine Heizwärme abgeleitet wurde (gepflegte Effizienz).
    waerme_abgeleitet: int = 0


async def schreibe_modus_split_monat(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> ModusSplitSchreibErgebnis:
    """Schreibt Teilmengen, Abdeckung und ggf. die abgeleitete Wärme in die IMD-Zeile.

    Idempotent: derselbe Monat zweimal ergibt dieselben Werte (der
    Provenance-Helfer erkennt den No-Op am identischen Wert).

    Kein Commit — der Aufrufer entscheidet über die Transaktionsgrenze.
    """
    ergebnis = ModusSplitSchreibErgebnis()
    splits = await lade_modus_split_monat(db, anlage_id, jahr, monat)
    if not splits:
        return ergebnis

    inv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "waermepumpe",
        )
    )
    investitionen = {str(inv.id): inv for inv in inv_result.scalars().all()}

    for inv_id_str, split in splits.items():
        inv = investitionen.get(inv_id_str)
        if inv is None:
            # Modus-Spur ohne Gerät: die Investition wurde nach der Messung
            # gelöscht. Nichts zu schreiben, kein Fehler.
            continue

        imd = await _lade_imd(db, int(inv_id_str), jahr, monat)
        if imd is None:
            # Ohne Monatszeile gibt es keinen Gesamtwert, von dem die
            # Teilmenge eine Teilmenge wäre. Der Split entsteht beim nächsten
            # Abschluss, sobald die Zeile existiert.
            continue

        daten = imd.verbrauch_daten or {}
        gesamt = get_wp_strom_kwh(daten, inv.parameter)
        if not teilmengen_passen(split, gesamt if gesamt > 0 else None):
            ergebnis.widerspruch.append(inv.id)
            await _entferne_split(db, imd)
            logger.info(
                "Modus-Split %s/%02d Investition %s verworfen: "
                "Teilmengen %.1f kWh > Gesamt %.1f kWh",
                jahr, monat, inv.id, split.aufgeteilt_kwh, gesamt,
            )
            continue

        await _schreibe_split(db, imd, split)
        ergebnis.geschrieben += 1

        if await _schreibe_abgeleitete_waerme(db, imd, split, inv.parameter):
            ergebnis.waerme_abgeleitet += 1

    return ergebnis


async def _lade_imd(
    db: AsyncSession, investition_id: int, jahr: int, monat: int
) -> Optional[InvestitionMonatsdaten]:
    result = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == investition_id,
            InvestitionMonatsdaten.jahr == jahr,
            InvestitionMonatsdaten.monat == monat,
        )
    )
    return result.scalar_one_or_none()


async def _schreibe_split(
    db: AsyncSession, imd: InvestitionMonatsdaten, split: ModusSplit
) -> None:
    """Die zwei Teilmengen + die Abdeckung, je als eigener Sub-Key."""
    for modus, feld in MODUS_STROM_FELD.items():
        await write_json_subkey_with_provenance(
            db, imd, "verbrauch_daten", feld,
            round(split.teilmenge_kwh(modus), 2),
            source=_QUELLE, writer=_WRITER,
        )
    await write_json_subkey_with_provenance(
        db, imd, "verbrauch_daten", MODUS_ABDECKUNG_FELD,
        round(split.abdeckung_h, 1),
        source=_QUELLE, writer=_WRITER,
    )


async def _schreibe_abgeleitete_waerme(
    db: AsyncSession,
    imd: InvestitionMonatsdaten,
    split: ModusSplit,
    parameter: Optional[dict],
) -> bool:
    """``heizenergie_kwh`` aus Heizstrom × gepflegter Effizienz (Konzept §3.4).

    ``False``, wenn nichts abgeleitet wurde — keine gepflegte Effizienz, kein
    Heizbetrieb, oder ein höherwertiger Wert steht schon da (Messung). Der
    letzte Fall braucht hier **keine** Prüfung: die Quellen-Hierarchie
    entscheidet ihn (s. Modul-Kopf), und ``WriteResult.applied`` sagt danach,
    was passiert ist.
    """
    from backend.core.betriebsmodus import HEIZEN

    strom_heizen = split.teilmenge_kwh(HEIZEN)
    if strom_heizen <= 0:
        return False
    waerme = abgeleitete_heizwaerme_kwh(strom_heizen, parameter)
    if waerme is None:
        return False
    res = await write_json_subkey_with_provenance(
        db, imd, "verbrauch_daten", "heizenergie_kwh", round(waerme, 1),
        source=_QUELLE, writer=_WRITER,
        abgeleitet=ABGELEITET_JAZ_MODUS,
    )
    return res.applied


async def _entferne_split(db: AsyncSession, imd: InvestitionMonatsdaten) -> None:
    """Räumt einen früher geschriebenen Split weg (Invariante verletzt).

    **Ohne diesen Rückbau bliebe ein Widerspruch stehen**: wer den Monatswert
    nachträglich kleiner pflegt, hätte sonst weiterhin die alte, zu große
    Aufteilung daneben. Angefasst werden ausschließlich die drei eigenen Felder
    — ``heizenergie_kwh`` bleibt unberührt, weil es auch gemessen sein kann und
    diese Funktion die Herkunft nicht kennt.
    """
    daten = imd.verbrauch_daten or {}
    entfernt = [f for f in MODUS_SPLIT_FELDER if f in daten]
    if not entfernt:
        return
    neu = {k: v for k, v in daten.items() if k not in MODUS_SPLIT_FELDER}
    imd.verbrauch_daten = neu
    flag_modified(imd, "verbrauch_daten")
    provenance = dict(imd.source_provenance or {})
    for feld in entfernt:
        provenance.pop(f"verbrauch_daten.{feld}", None)
    imd.source_provenance = provenance
    flag_modified(imd, "source_provenance")
