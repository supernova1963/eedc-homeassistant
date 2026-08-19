"""Einmaliges Nachsenden des Gemeinschaftsdatensatzes nach einem Update.

**Anlass: eedc #387, Schritt 3 (Gernot, 2026-08-19).** Mit v4.0.22 gehen vier
Felder erstmals mit — der PVGIS-Maßstab je Monat und je Jahr, die CO₂-Zahl nach
eedcs Kanon und der gemessene Eigenverbrauch. Der Community-Server stellt seine
Rangliste am **01.09.2026** auf diesen Maßstab um; bis dahin soll er ihn von so
vielen Anlagen wie möglich haben.

**Warum es diesen Lauf überhaupt braucht — am Code gemessen.** Der Datensatz
geht heute an genau zwei Stellen raus: beim **Monatsabschluss**
(``monatsabschluss/wizard.py::_post_save_hintergrund``, nur mit
``community_auto_share``) und über den **Teilen-Knopf**
(``api/routes/community.py``). Es gibt **keinen** Scheduler-Job und keinen
Start-Hook — wer seinen August erst Mitte September abschließt, hätte den
Maßstab am 01.09. also nicht geschickt. Ohne diesen Lauf wäre die Umstellung
auf einer Datenlage gestartet, die es erst Wochen später gibt.

**Was er tut und was ausdrücklich nicht:**

- Er sendet **nur** für Anlagen mit ``community_auto_share`` — die haben dem
  automatischen Teilen nach dem Monatsabschluss bereits zugestimmt, und ein
  Voll-Submit ist genau das, was dort ohnehin passiert. **Keine neue
  Einwilligungsstufe**, und niemand wird erstmals geteilt.
- Er verlangt einen vorhandenen ``community_hash``: nur wer schon einmal
  geteilt hat, wird nachgesendet. Eine Erstanmeldung ist eine bewusste
  Handlung und bleibt es.
- Er läuft **einmal**. Der Marker steht in ``Settings`` unter
  ``community_nachsende_lauf`` und trägt den Schema-Stand — käme später ein
  weiteres Feld dazu, genügt ein neuer Stand, um erneut nachzusenden.
- Alle anderen bekommen **Hinweis und Knopf** statt eines stillen Versands;
  dafür liefert :func:`nachsende_status` die Angaben an die Oberfläche.

⚠ **Fehler sind hier kein Grund zum Abbruch.** Der Community-Server kann
offline sein oder ein Rate-Limit ziehen; dann bleibt der Marker ungesetzt und
der nächste Start versucht es erneut. Ein Start von eedc darf daran nicht
scheitern.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage
from backend.models.settings import Settings

logger = logging.getLogger(__name__)

#: Key im Settings-Store.
NACHSENDE_SETTINGS_KEY = "community_nachsende_lauf"

#: Der Schema-Stand, den dieser Lauf herstellt. Wer ihn ändert, löst einen
#: neuen Lauf aus — bewusst als Zeichenkette und nicht als Versionsnummer:
#: nicht jede Version ändert den Datensatz.
SCHEMA_STAND = "2026-08-soll-co2-eigenverbrauch"


async def _marker(db: AsyncSession) -> Optional[dict]:
    result = await db.execute(
        select(Settings).where(Settings.key == NACHSENDE_SETTINGS_KEY)
    )
    eintrag = result.scalar_one_or_none()
    return eintrag.value if eintrag and isinstance(eintrag.value, dict) else None


async def ist_erledigt(db: AsyncSession) -> bool:
    """Lief der automatische Lauf für den aktuellen Schema-Stand schon?

    ⚠ Prüft ``lauf_erledigt``, **nicht** nur den Stand: seit
    :func:`merke_gesendet` denselben Eintrag auch beim manuellen Teilen
    fortschreibt, würde ein einziger Knopfdruck sonst den automatischen Lauf
    für alle übrigen Anlagen abschalten.
    """
    marker = await _marker(db)
    return bool(
        marker
        and marker.get("stand") == SCHEMA_STAND
        and marker.get("lauf_erledigt")
    )


async def _erledigte_anlagen(db: AsyncSession) -> set[int]:
    """Anlagen, die im aktuellen Schema-Stand bereits gesendet haben.

    Nötig, weil der Hinweis für Anlagen **ohne** Auto-Share sonst stehen bliebe,
    nachdem ihr Besitzer den Knopf gedrückt hat: der globale Marker sagt nur,
    dass der *automatische* Lauf durch ist, nicht wer manuell geteilt hat.
    """
    marker = await _marker(db)
    if not marker or marker.get("stand") != SCHEMA_STAND:
        return set()
    return {int(x) for x in marker.get("anlagen", []) if isinstance(x, (int, str))}


async def merke_gesendet(db: AsyncSession, anlage_id: int) -> None:
    """Hält fest, dass diese Anlage im aktuellen Schema-Stand gesendet hat.

    Wird sowohl vom automatischen Lauf als auch vom Teilen-Knopf aufgerufen —
    beide erzeugen denselben Voll-Submit, also zählt beides gleich.
    """
    result = await db.execute(
        select(Settings).where(Settings.key == NACHSENDE_SETTINGS_KEY)
    )
    vorhanden = result.scalar_one_or_none()
    alt = vorhanden.value if vorhanden and isinstance(vorhanden.value, dict) else {}
    anlagen = set(alt.get("anlagen", [])) if alt.get("stand") == SCHEMA_STAND else set()
    anlagen.add(anlage_id)
    wert = {
        "stand": SCHEMA_STAND,
        "anlagen": sorted(anlagen),
        "lauf_erledigt": bool(alt.get("lauf_erledigt")) if alt.get("stand") == SCHEMA_STAND else False,
    }
    if vorhanden:
        vorhanden.value = wert
    else:
        db.add(Settings(key=NACHSENDE_SETTINGS_KEY, value=wert))
    await db.commit()


async def nachsende_status(db: AsyncSession) -> dict:
    """Was die Oberfläche wissen muss, um Hinweis und Knopf zu zeigen.

    Returns:
        ``{"erledigt": bool, "offen": [{"anlage_id", "anlagenname"}]}`` —
        ``offen`` sind Anlagen, die geteilt haben, aber **nicht** automatisch
        nachsenden. Genau ihnen gehört der Hinweis.
    """
    erledigt = await ist_erledigt(db)
    schon_gesendet = await _erledigte_anlagen(db)
    result = await db.execute(
        select(Anlage).where(
            Anlage.community_hash.isnot(None),
            Anlage.community_auto_share.is_(False),
        )
    )
    offen = [
        {"anlage_id": a.id, "anlagenname": a.anlagenname}
        for a in result.scalars().all()
        if a.id not in schon_gesendet
    ]
    return {"erledigt": erledigt, "offen": offen}


async def fuehre_nachsende_lauf_aus(db: AsyncSession) -> dict:
    """Sendet den Datensatz aller Auto-Share-Anlagen einmalig neu.

    Returns:
        ``{"gesendet": int, "fehlgeschlagen": int, "uebersprungen": bool}``.
        ``uebersprungen`` heißt: für diesen Schema-Stand lief es schon.
    """
    if await ist_erledigt(db):
        return {"gesendet": 0, "fehlgeschlagen": 0, "uebersprungen": True}

    from backend.services.community_service import (
        COMMUNITY_SERVER_URL,
        prepare_community_data,
    )

    result = await db.execute(
        select(Anlage).where(
            Anlage.community_hash.isnot(None),
            Anlage.community_auto_share.is_(True),
        )
    )
    anlagen = list(result.scalars().all())

    gesendet = 0
    fehlgeschlagen = 0
    for anlage in anlagen:
        try:
            daten = await prepare_community_data(db, anlage.id)
            if not daten or not daten.get("monatswerte"):
                continue
            async with httpx.AsyncClient(timeout=20.0) as client:
                antwort = await client.post(
                    f"{COMMUNITY_SERVER_URL}/api/submit", json=daten
                )
            if antwort.status_code == 200:
                gesendet += 1
                await merke_gesendet(db, anlage.id)
                logger.info(
                    "Community-Nachsendung für Anlage %s erfolgreich", anlage.id
                )
            else:
                fehlgeschlagen += 1
                logger.warning(
                    "Community-Nachsendung HTTP %s: %s",
                    antwort.status_code, antwort.text[:200],
                )
        except Exception as e:  # noqa: BLE001 — ein Start darf daran nicht scheitern
            fehlgeschlagen += 1
            logger.warning(
                "Community-Nachsendung für Anlage %s fehlgeschlagen: %s: %s",
                anlage.id, type(e).__name__, e,
            )

    # Der Marker wird nur gesetzt, wenn nichts fehlgeschlagen ist — sonst
    # versucht es der nächste Start erneut. Ein Bestand ohne Auto-Share-Anlagen
    # gilt als erledigt (es gibt nichts zu senden).
    if fehlgeschlagen == 0:
        eintrag = await db.execute(
            select(Settings).where(Settings.key == NACHSENDE_SETTINGS_KEY)
        )
        vorhanden = eintrag.scalar_one_or_none()
        alt = vorhanden.value if vorhanden and isinstance(vorhanden.value, dict) else {}
        anlagen = sorted(set(alt.get("anlagen", []))) if alt.get("stand") == SCHEMA_STAND else []
        wert = {"stand": SCHEMA_STAND, "anlagen": anlagen, "lauf_erledigt": True}
        if vorhanden:
            vorhanden.value = wert
        else:
            db.add(Settings(key=NACHSENDE_SETTINGS_KEY, value=wert))
        await db.commit()

    return {
        "gesendet": gesendet,
        "fehlgeschlagen": fehlgeschlagen,
        "uebersprungen": False,
    }
