"""
Archiv-Nachzug: der eine Tag, der gerade den Wetter-Cutoff passiert hat (N-388).

**Der Defekt.** ``_helpers._get_wetter_ist`` holt die Wetterzeile für Tage
jünger als ``archive_cutoff()`` (heute − 5) vom **Forecast**-Endpunkt, für
ältere vom **Archiv** (ERA5). Das ist Absicht — das Archiv hinkt 2–5 Tage
nach (``a8b2a1e2``, 06.05.2026). ⛔ Nur: **den vorläufigen Wert holt bisher
niemand nach.** ``wetter_backfill_service`` ist ausdrücklich „strikt additiv"
und fasst ``globalstrahlung_wm2`` gar nicht an. Ein Tag, der als vorläufiger
Modellwert aggregiert wurde, behält ihn für immer.

**Wie groß das ist, gemessen** (Anlage 1, 12,3 kWp, 91 Tage 01.06.–30.08.2026,
gegen einen eigenen ERA5-Abruf derselben Koordinaten): Median-Verhältnis
**1,00**, 63 von 91 Tagen innerhalb ±10 % — es ist **kein Bias, sondern ein
Randproblem**. Acht Tage ab Faktor 1,3, zwei davon ab Faktor 2 (19.08. 5,14× ·
18.08. **8,70×**). Und **jeder** Tag mit einer Performance Ratio > 1 liegt in
diesem Schwanz; mit dem Archivwert fällt jeder davon in den plausiblen Bereich
(18.08.: PR 3,35 → 0,36). Für den 18.08. vier Quellen getrennt gemessen:
Forecast ``best_match`` 229 Wh/m² (= bitgleich der DB-Wert, eedc liest also
korrekt) · ``icon_seamless`` 629 · ``ecmwf_ifs025`` 1713 · **Archiv/ERA5 1992**.

**Was daran hängt:** die Performance Ratio (Tag und Monats-Ø) · die Spalte
*Einstrahlung* in *Auswertungen → Tabelle* · die angezeigte GTI-Zahl (N-384) ·
über Bewölkung/Wettercode derselben Zeile das Korrekturprofil · und der
**Doppelerfassungs-Verdacht** des Daten-Checkers (``PR_PLAUSI_SCHWELLE``,
≥ 3 Tage UND ≥ 20 % der Fenstertage). Genau der hat coolxmad fünf Wochen lang
in seine eigenen Stammdaten geschickt, während der Fehler im Wetterwert lag.

**Der Reparaturweg existierte schon und wurde nie angestoßen.** Wird ein Tag
neu aggregiert, **nachdem** er den Cutoff passiert hat, zieht
``_get_wetter_ist`` von selbst das Archiv — Einstrahlung, GTI und PR entstehen
an ihrer **einen** bestehenden Stelle neu. Dieser Dienst stößt genau das an,
für den einen Tag, der die Grenze in der vergangenen Nacht überschritten hat.

----------------------------------------------------------------------------
⛔ Der Vorflug — warum dieser Job nicht einfach ``aggregate_day`` ruft
----------------------------------------------------------------------------
``aggregator.py`` begründet in seinem Preserve-Block ausdrücklich, warum der
Scheduler — anders als die Reparatur-Werkbank — **nicht** gegen
Komponenten-Verlust geschützt ist: *„für historische Tage läuft der Scheduler
nie nach."* Dieser Job macht genau das zum ersten Mal. Die Annahme war also
nicht falsch, sie wird durch ihn ungültig — und der Kommentar dort ist
mitgeändert.

Der messbare Schaden dabei ist eng, aber echt:

* **Energie ist sicher.** Sie kommt aus dem Zählerpfad
  (``sensor_snapshots``, stündlich, **dauerhaft**) bzw. aus HA-LTS, und
  HA löscht Langzeitstatistik nie.
* **Die Stundenkurve** (``TagesEnergieProfil.komponenten``, Peaks) kommt aus
  ``get_tagesverlauf`` = **HA-History**, und die reicht nur so weit wie
  ``purge_keep_days`` (HA-Default 10).
* Ist die Kurve **leer**, steigt ``aggregate_day`` mit ``return None`` aus,
  **bevor** gelöscht wird — der Tag bleibt unangetastet. Das ist sicher, und
  es ist zugleich der Normalfall reiner MQTT-Anlagen (dort greifen die
  synthetischen Slots); deshalb ist eine leere Kurve **kein** Abbruchgrund.
* Ist sie **teilweise** da — Recorder-Grenze mitten im Tag, also
  ``purge_keep_days`` ≈ 6 —, würde ein **verkürzter** Tag einen vollständigen
  ersetzen.

**Deshalb der Vorflug:** deckt die frisch geholte Kurve *weniger* Stunden ab
als die gespeicherte ``stunden_verfuegbar``, wird der Tag übersprungen und das
protokolliert. Gezählt wird mit derselben Bucket-Regel, die der Aggregator zum
Schreiben benutzt (``core.berechnungen.slot_konvention.leistungspfad_slot``) —
ein zweiter Nachbau dieser Regel wäre genau die Klasse, aus der N-382 entstand.

⚑ **Der Vorflug misst nur, er reicht nichts durch.** ``aggregate_day`` holt
seine Kurve anschließend selbst und läuft damit bitgleich den Weg des
regulären Scheduler-Jobs — inklusive ``ermittle_aggregations_quelle``. Der
zweite HA-Abruf ist der Preis dafür und ist klein: der Job
``energie_profil_heute`` macht denselben Abruf 96× am Tag.

⛔ **Ausdrücklich NICHT in diesem Dienst:** an ``PR_PLAUSI_SCHWELLE`` drehen
(wenn die Strahlung an der Quelle stimmt, verschwindet die Falschmeldung von
selbst — eine Schwelle obendrauf wäre der zweite Turm) und den **Altbestand**
heilen. Tage, die vor dem ersten Lauf dieses Dienstes aggregiert wurden,
behalten ihren vorläufigen Wert; das Alarmfenster des Daten-Checkers heilt
sich binnen 31 Tagen von selbst (dann sind höchstens 6 von 31 Fenstertagen
vorläufig ⇒ 19,35 % < 20 %, der Alarm kann aus vorläufigen Werten nicht mehr
entstehen), und für einen einzelnen Alttag gibt es die Reparatur-Werkbank
(*Einstellungen → Daten*, „Mehrere Tage neu aggregieren").
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.slot_konvention import leistungspfad_slot
from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.aggregator import aggregate_day
from backend.services.energie_profil.source import Source
from backend.services.wetter_backfill_service import ARCHIVE_LAG_TAGE

logger = logging.getLogger(__name__)


def archiv_grenztag(heute: Optional[date] = None) -> date:
    """Der eine Tag, der die Archiv-Grenze in der vergangenen Nacht passiert hat.

    ``archive_cutoff(t) = t − ARCHIVE_LAG_TAGE``; ein Tag geht ins Archiv,
    sobald ``datum < cutoff``. Für ``d = heute − (ARCHIVE_LAG_TAGE + 1)`` gilt
    das **heute erstmals** — gestern war ``d ≥ cutoff(gestern)`` und wurde
    noch vom Forecast bedient.

    Abgeleitet aus ``ARCHIVE_LAG_TAGE``, **nicht** als Konstante geschrieben:
    ändert sich der Lag, wandert der Grenztag mit.
    """
    return (heute or date.today()) - timedelta(days=ARCHIVE_LAG_TAGE + 1)


def kurven_stunden(
    punkte: Optional[Sequence[dict]],
    vortagsrand: Optional[Sequence[dict]] = None,
) -> int:
    """Wie viele Stunden-Zeilen der Aggregator aus dieser Kurve schriebe.

    Spiegelt die Bucket-Bildung in ``aggregator.aggregate_day`` über den
    gemeinsamen SoT ``leistungspfad_slot``: Punkt „05:00" → Slot 6, Label 23
    fällt in den Folgetag, und Slot 0 existiert immer, sobald überhaupt ein
    Bucket entsteht (auch ohne Vortagsrand — sonst verlöre die Zeile 0 ihre
    Zähler-, Wetter- und Preiswerte).

    ``0`` bei leerer Kurve — das ist **kein** Vorflug-Abbruch, sondern der
    Normalfall reiner MQTT-Anlagen; siehe Modul-Docstring.
    """
    slots: set[int] = set()
    for p in punkte or []:
        try:
            stunde = int(str(p["zeit"]).split(":")[0])
        except (KeyError, TypeError, ValueError):
            continue
        slot = leistungspfad_slot(stunde)
        if slot is not None:
            slots.add(slot)
    if vortagsrand:
        slots.add(0)
    if slots:
        slots.add(0)
    return len(slots)


async def nachzug_anlage(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
) -> dict:
    """Zieht die Wetterzeile EINER Anlage für ``datum`` aus dem Archiv nach.

    Returns:
        dict mit ``status`` (``ok`` · ``kein_tag`` · ``uebersprungen`` ·
        ``keine_daten`` · ``fehler``) und — beim Überspringen — den beiden
        Stundenzahlen, die dazu geführt haben.
    """
    tz_row = (
        await db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum == datum,
            )
        )
    ).scalar_one_or_none()

    if tz_row is None:
        # Nichts zu verbessern. Einen Tag sechs Tage später erstmals anzulegen
        # wäre neues Verhalten und nicht Gegenstand dieses Funds — dafür gibt
        # es den Vollbackfill und die Reparatur-Werkbank.
        return {"status": "kein_tag"}

    gespeichert = tz_row.stunden_verfuegbar or 0

    # ── Vorflug: würde die Neuaggregation die Stundenkurve verkürzen? ──────
    from backend.services.live_power_service import get_live_power_service

    try:
        tv_data = await get_live_power_service().get_tagesverlauf(
            anlage, db, tage_zurueck=(date.today() - datum).days,
            mit_vortagsrand=True,
        )
    except Exception as e:  # noqa: BLE001 — der Vorflug darf den Job nicht kippen
        logger.warning(
            "Archiv-Nachzug Anlage %s, %s: Vorflug fehlgeschlagen (%s: %s) — übersprungen",
            anlage.id, datum, type(e).__name__, e,
        )
        return {"status": "uebersprungen", "grund": "vorflug_fehler"}

    jetzt = kurven_stunden(tv_data.get("punkte"), tv_data.get("vortagsrand"))
    if jetzt and jetzt < gespeichert:
        logger.warning(
            "Archiv-Nachzug Anlage %s, %s übersprungen: die HA-Historie deckt "
            "nur noch %d von %d Stunden — eine Neuaggregation würde die "
            "Stundenkurve verkürzen.",
            anlage.id, datum, jetzt, gespeichert,
        )
        return {
            "status": "uebersprungen",
            "grund": "kurve_geschrumpft",
            "stunden_jetzt": jetzt,
            "stunden_gespeichert": gespeichert,
        }

    zusammenfassung = await aggregate_day(
        anlage, datum, db, source=Source.SCHEDULER,
    )
    return {
        "status": "ok" if zusammenfassung else "keine_daten",
        "datum": datum.isoformat(),
    }


async def archiv_nachzug_all(heute: Optional[date] = None) -> dict:
    """Scheduler-Job: Grenztag für alle Anlagen aus dem Archiv nachziehen.

    Returns:
        Dict mit Ergebnis je Anlage-ID.
    """
    datum = archiv_grenztag(heute)
    results: dict = {}

    async with get_session() as db:
        anlagen = (await db.execute(select(Anlage))).scalars().all()
        for anlage in anlagen:
            try:
                results[anlage.id] = await nachzug_anlage(anlage, datum, db)
                # Per-Anlage-Commit: SQLite-Writer-Lock kurz freigeben (#291).
                await db.commit()
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Archiv-Nachzug Anlage %s, %s fehlgeschlagen: %s: %s",
                    anlage.id, datum, type(e).__name__, e,
                )
                results[anlage.id] = {"status": "fehler", "error": str(e)}
                await db.rollback()

    return results
