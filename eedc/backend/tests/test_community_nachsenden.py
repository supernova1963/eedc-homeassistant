"""Der einmalige Nachsende-Lauf (#387 Schritt 3) und sein Marker.

**Warum es diesen Lauf gibt.** `prepare_community_data` hat baumweit genau zwei
Aufrufer: den Monatsabschluss-Hook und den Teilen-Knopf. Es gibt **keinen**
Scheduler-Job und keinen Start-Hook — wer seinen August erst Mitte September
abschließt, hätte den neuen Maßstab am 01.09. nicht geschickt.

**Warum der Marker zwei Dinge trennen muss.** Er trägt einen Schema-Stand *und*
die Liste der Anlagen, die bereits gesendet haben. Der erste Entwurf hatte nur
den Stand — und weil `merke_gesendet` denselben Eintrag auch beim **manuellen**
Teilen fortschreibt, hätte ein einziger Knopfdruck den automatischen Lauf für
alle übrigen Anlagen abgeschaltet. Der vorletzte Test hält genau das fest.
"""

from __future__ import annotations

import pytest

from backend.models import Anlage
from backend.services import community_nachsenden as nl


async def _anlage(db, *, auto: bool, hash_: str | None = "abc") -> Anlage:
    a = Anlage(anlagenname=f"A-{auto}-{hash_}", leistung_kwp=10.0,
               community_hash=hash_, community_auto_share=auto)
    db.add(a)
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_ohne_auto_share_steht_die_anlage_im_hinweis(db):
    """Wer nicht automatisch teilt, bekommt Hinweis und Knopf — keinen Versand."""
    a = await _anlage(db, auto=False)

    status = await nl.nachsende_status(db)

    assert [o["anlage_id"] for o in status["offen"]] == [a.id]


@pytest.mark.asyncio
async def test_ohne_geteilten_datensatz_kein_hinweis(db):
    """Wer noch nie geteilt hat, wird nicht angesprochen — Erstteilen ist eine
    bewusste Handlung und bleibt es."""
    await _anlage(db, auto=False, hash_=None)

    status = await nl.nachsende_status(db)

    assert status["offen"] == []


@pytest.mark.asyncio
async def test_manuelles_teilen_nimmt_die_anlage_aus_dem_hinweis(db):
    """Nach dem Knopfdruck verschwindet der Hinweis — sonst bliebe er ewig."""
    a = await _anlage(db, auto=False)

    await nl.merke_gesendet(db, a.id)
    status = await nl.nachsende_status(db)

    assert status["offen"] == []


@pytest.mark.asyncio
async def test_manuelles_teilen_schaltet_den_automatischen_lauf_nicht_ab(db):
    """Der Fehler, den der erste Entwurf hatte.

    `merke_gesendet` schreibt denselben Settings-Eintrag wie der Lauf. Prüfte
    `ist_erledigt` nur den Schema-Stand, hätte ein einziger manueller Knopfdruck
    den automatischen Lauf für **alle** übrigen Anlagen übersprungen.
    """
    a = await _anlage(db, auto=False)

    await nl.merke_gesendet(db, a.id)

    assert await nl.ist_erledigt(db) is False, (
        "Ein manuelles Teilen ist nicht der automatische Lauf — sonst gehen die "
        "Auto-Share-Anlagen leer aus."
    )


@pytest.mark.asyncio
async def test_lauf_ohne_auto_share_anlagen_ist_sofort_erledigt(db):
    """Kein Auto-Share im Bestand: nichts zu senden, Marker trotzdem gesetzt.

    Sonst liefe der Versuch bei jedem Start erneut an.
    """
    await _anlage(db, auto=False)

    ergebnis = await nl.fuehre_nachsende_lauf_aus(db)

    assert ergebnis == {"gesendet": 0, "fehlgeschlagen": 0, "uebersprungen": False}
    assert await nl.ist_erledigt(db) is True

    zweiter = await nl.fuehre_nachsende_lauf_aus(db)
    assert zweiter["uebersprungen"] is True
