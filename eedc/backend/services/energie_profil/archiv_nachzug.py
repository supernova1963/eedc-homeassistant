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

----------------------------------------------------------------------------
⭐ Nachtrag 05.09.2026 — der Altbestand wird DOCH geheilt, nur anders
----------------------------------------------------------------------------
Der Absatz darüber hielt einen Tag. Gemessen an coolxmad (#353): sein
Daten-Checker meldete am 04.09. weiter Doppelerfassung aus **sieben** August-
Tagen, die alle vor dem ersten Lauf dieses Jobs aggregiert waren — und die
Reparatur-Werkbank kann sie nicht heilen: ``aggregate_day`` braucht die
Stundenkurve aus der HA-Historie, und die reicht nur ``purge_keep_days``
zurück. **Für einen Alttag gibt es damit gar keinen Weg**, und die falsche PR
steht in *Auswertungen → Tabelle* für immer.

Deshalb ein zweiter, schmalerer Pfad: ``wetter_nachziehen_bereich`` schreibt
**nur die Wetterzeile** — die sechs Stunden-Spalten, das Tagesaggregat
(Temperatur, GHI, GTI) und die Performance Ratio über die Layer-Formel
(``core/berechnungen/performance_ratio.py``, dieselbe wie im Aggregator). Er
braucht keine Kurve, keinen Vorflug, keine HA-Historie: Energie bleibt, wie
sie ist. ``wetter_altbestand_nachziehen`` fährt ihn **einmal je Anlage** über
alles Ältere als den Grenztag (bis ``DEFAULT_MAX_TAGE`` zurück, ein
Archiv-Abruf je Orientierungsgruppe) und merkt sich das in ``settings``
(``WETTER_ALTBESTAND_KEY``); ein gescheiterter Abruf setzt keinen Marker und
kommt in der nächsten Nacht wieder. Derselbe Pfad holt den **Grenztag**
nach, wenn der Vorflug oben ihn übersprungen hat — sonst bliebe genau der Tag
vorläufig, den dieser Job heilen soll.

⚠ **Was der schmale Pfad NICHT kann, und warum er trotzdem der Nachzug für
den Bestand ist:** Er kennt die Orientierungsgruppen von **heute**, nicht die
des jeweiligen Tages (ein Zubau verschiebt die GTI-Gewichtung rückwirkend
leicht), und den Sonstiges-Erzeuger-Abzug der PR nimmt er aus dem Tages-
``komponenten_kwh`` statt aus den Stunden. Beides ist der Preis dafür, dass er
ohne Kurve auskommt — und beides ist um Größenordnungen kleiner als der
Faktor 8,7, den er beseitigt.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.slot_konvention import leistungspfad_slot
from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.settings import Settings
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen.performance_ratio import berechne_performance_ratio
from backend.utils.investition_filter import aktiv_jetzt
from backend.services.energie_profil.aggregator import aggregate_day
from backend.services.energie_profil.source import Source
from backend.services.energie_profil._helpers import _fetch_wetter
from backend.services.wetter_backfill_service import (
    ARCHIVE_LAG_TAGE,
    ARCHIVE_URL,
    DEFAULT_MAX_TAGE,
)

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


#: `settings`-Schlüssel des einmaligen Altbestand-Nachzugs:
#: ``{"<anlage_id>": {"bis": "YYYY-MM-DD", "am": "YYYY-MM-DD", "tage": n}}``.
WETTER_ALTBESTAND_KEY = "wetter_altbestand_nachzug"


def _rund(wert, stellen: int):
    return round(wert, stellen) if wert is not None else None


async def _wetterzeile_schreiben(
    anlage: Anlage,
    datum: date,
    stunden: dict[int, dict],
    invs: Sequence[Investition],
    sonstige_erzeuger_ids: set[int],
    db: AsyncSession,
) -> bool:
    """Schreibt die Wetterzeile EINES Tages neu — Stunden, Tagesaggregat, PR.

    Spiegelt exakt die Wetter-Spalten, die ``aggregate_day`` schreibt (Rundung
    inklusive), und lässt jede Energie-Spalte unangetastet. ``False``, wenn der
    Tag keine Zeilen hat — sechs Tage später erstmals einen anzulegen wäre
    neues Verhalten (s. ``nachzug_anlage``).
    """
    rows = list((await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id,
            TagesEnergieProfil.datum == datum,
        )
    )).scalars().all())
    tz = (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == datum,
        )
    )).scalar_one_or_none()
    if not rows and tz is None:
        return False

    temp_values: list[float] = []
    strahlung_summe = 0.0
    gti_summe = 0.0
    pv_ertrag_summe = 0.0
    pv_ertrag_erfasst = False
    for r in rows:
        w = stunden.get(r.stunde)
        if w:
            r.temperatur_c = _rund(w.get("temperatur_c"), 1)
            r.globalstrahlung_wm2 = _rund(w.get("globalstrahlung_wm2"), 0)
            r.bewoelkung_prozent = _rund(w.get("bewoelkung_prozent"), 0)
            r.niederschlag_mm = _rund(w.get("niederschlag_mm"), 2)
            code = w.get("wetter_code")
            r.wetter_code = int(code) if code is not None else None
            if w.get("temperatur_c") is not None:
                temp_values.append(w["temperatur_c"])
            if w.get("globalstrahlung_wm2") is not None:
                strahlung_summe += w["globalstrahlung_wm2"]
            if w.get("gti_wm2") is not None:
                gti_summe += w["gti_wm2"]
        if r.pv_kw is not None:
            pv_ertrag_summe += r.pv_kw
            pv_ertrag_erfasst = True

    if tz is not None:
        tz.temperatur_min_c = round(min(temp_values), 1) if temp_values else None
        tz.temperatur_max_c = round(max(temp_values), 1) if temp_values else None
        tz.strahlung_summe_wh_m2 = round(strahlung_summe, 0) if strahlung_summe > 0 else None
        tz.gti_summe_wh_m2 = round(gti_summe, 0) if gti_summe > 0 else None
        # PR-Zähler wie im Aggregator: PV ohne Sonstiges-Erzeuger (BHKW hat
        # keinen GTI-Bezug). Die Stunden tragen den Abzug nicht mehr — er kommt
        # aus dem Tages-`komponenten_kwh`, s. Modul-Docstring.
        sonstige = 0.0
        for inv_id in sonstige_erzeuger_ids:
            v = (tz.komponenten_kwh or {}).get(f"sonstiges_{inv_id}")
            if v is not None and v > 0:
                sonstige += v
        kwp = anlagen_kwp(invs, datum, mit_bkw=True, referenzwert=anlage.leistung_kwp)
        tz.performance_ratio = berechne_performance_ratio(
            (pv_ertrag_summe - sonstige) if pv_ertrag_erfasst else None, gti_summe, kwp,
        )
    return True


async def wetter_nachziehen_bereich(
    anlage: Anlage,
    db: AsyncSession,
    von: date,
    bis: date,
    *,
    timeout: float = 60.0,
) -> dict:
    """Zieht die Wetterzeile aller gespeicherten Tage in ``[von, bis]`` aus dem
    Archiv nach — ein Abruf je Orientierungsgruppe, kein Aggregator.

    Returns:
        ``status`` (``ok`` · ``kein_tag`` · ``skipped`` · ``fehler``) plus
        ``tage`` (geschrieben) und ``ohne_wetter`` (Tage, für die das Archiv
        nichts lieferte).
    """
    if not anlage.latitude or not anlage.longitude:
        return {"status": "skipped", "grund": "keine Koordinaten"}
    if von > bis:
        return {"status": "kein_tag", "tage": 0}

    tage = sorted({
        d for (d,) in (await db.execute(
            select(TagesZusammenfassung.datum).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            )
        )).all()
    })
    if not tage:
        return {"status": "kein_tag", "tage": 0}

    invs = list((await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )).scalars().all())
    pv_module = [
        i for i in invs if i.typ in ("pv-module", "balkonkraftwerk") and (i.aktiv is None or i.aktiv)
    ]
    sonstige_erzeuger_ids = {
        i.id for i in invs
        if i.typ == "sonstiges" and (i.parameter or {}).get("kategorie") == "erzeuger"
    }

    try:
        je_tag = await _fetch_wetter(
            anlage, ARCHIVE_URL,
            {"start_date": tage[0].isoformat(), "end_date": tage[-1].isoformat()},
            pv_module, timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 — ein Abruf darf den Job nicht kippen
        logger.warning(
            "Wetter-Nachzug Anlage %s (%s–%s): Archiv-Abruf fehlgeschlagen: %s: %s",
            anlage.id, tage[0], tage[-1], type(e).__name__, e,
        )
        return {"status": "fehler", "error": str(e), "tage": 0}

    geschrieben = 0
    ohne_wetter = 0
    for datum in tage:
        stunden = je_tag.get(datum)
        if not stunden:
            ohne_wetter += 1
            continue
        if await _wetterzeile_schreiben(anlage, datum, stunden, invs, sonstige_erzeuger_ids, db):
            geschrieben += 1
    return {
        "status": "ok", "tage": geschrieben, "ohne_wetter": ohne_wetter,
        "von": tage[0].isoformat(), "bis": tage[-1].isoformat(),
    }


async def altbestand_marker(db: AsyncSession) -> dict:
    """``{anlage_id(str): {...}}`` — welche Anlagen ihren Altbestand schon haben."""
    row = (await db.execute(
        select(Settings).where(Settings.key == WETTER_ALTBESTAND_KEY)
    )).scalar_one_or_none()
    return dict(row.value) if row is not None and isinstance(row.value, dict) else {}


async def altbestand_merken(db: AsyncSession, anlage_id: int, eintrag: dict) -> None:
    row = (await db.execute(
        select(Settings).where(Settings.key == WETTER_ALTBESTAND_KEY)
    )).scalar_one_or_none()
    wert = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    wert[str(anlage_id)] = eintrag
    if row is not None:
        row.value = wert
    else:
        db.add(Settings(key=WETTER_ALTBESTAND_KEY, value=wert))


async def wetter_altbestand_nachziehen(
    anlage: Anlage,
    db: AsyncSession,
    bis: date,
    max_tage: int = DEFAULT_MAX_TAGE,
) -> dict:
    """Einmal je Anlage: alle gespeicherten Tage bis ``bis`` (jünger als
    ``max_tage``) aus dem Archiv nachziehen. Der Marker wird vom Aufrufer
    gesetzt — nur bei einem Lauf, der nicht am Abruf gescheitert ist."""
    erster = (await db.execute(
        select(func.min(TagesZusammenfassung.datum)).where(
            TagesZusammenfassung.anlage_id == anlage.id,
        )
    )).scalar_one_or_none()
    if erster is None:
        return {"status": "kein_tag", "tage": 0}
    von = max(erster, bis - timedelta(days=max_tage))
    return await wetter_nachziehen_bereich(anlage, db, von, bis)


async def wetter_nachzug_all(
    ergebnisse: dict,
    heute: Optional[date] = None,
) -> dict:
    """Zweiter Schritt des 02:20-Jobs, NACH ``archiv_nachzug_all``.

    Je Anlage: (1) hat der Vorflug den Grenztag übersprungen oder fand der
    Aggregator keine Daten, wird seine **Wetterzeile** nachgezogen — sonst
    bliebe genau der Tag vorläufig, für den der Job da ist; (2) hat die Anlage
    ihren **Altbestand** noch nicht, wird er einmalig nachgezogen und im
    Marker festgehalten.

    ``ergebnisse`` ist der Rückgabewert von ``archiv_nachzug_all`` — die beiden
    Schritte sind getrennt, damit jener samt seinen Proben unverändert bleibt.
    """
    heute = heute or date.today()
    grenztag = archiv_grenztag(heute)
    out: dict = {}

    async with get_session() as db:
        anlagen = (await db.execute(select(Anlage))).scalars().all()
        marker = await altbestand_marker(db)
        for anlage in anlagen:
            eintrag: dict = {}
            try:
                status = (ergebnisse.get(anlage.id) or {}).get("status")
                if status in ("uebersprungen", "keine_daten"):
                    eintrag["grenztag"] = await wetter_nachziehen_bereich(
                        anlage, db, grenztag, grenztag,
                    )
                if str(anlage.id) not in marker:
                    alt = await wetter_altbestand_nachziehen(
                        anlage, db, bis=grenztag - timedelta(days=1),
                    )
                    eintrag["altbestand"] = alt
                    if alt.get("status") in ("ok", "kein_tag", "skipped"):
                        await altbestand_merken(db, anlage.id, {
                            "bis": (grenztag - timedelta(days=1)).isoformat(),
                            "am": heute.isoformat(),
                            "tage": alt.get("tage", 0),
                            "status": alt["status"],
                        })
                await db.commit()
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Wetter-Nachzug Anlage %s fehlgeschlagen: %s: %s",
                    anlage.id, type(e).__name__, e,
                )
                eintrag["fehler"] = str(e)
                await db.rollback()
            if eintrag:
                out[anlage.id] = eintrag
    return out


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
