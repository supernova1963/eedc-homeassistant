"""
Die PIN-Mechanik selbst — Ablage, Prüfung, Nachweis, Rückweg.

Der Wächter nebenan (``test_einstellungs_sperre_konformitaet.py``) fragt, *ob* die
Middleware für jede schreibende Route greift. Hier geht es um die Frage darunter: Hält
das Schloss, und lässt es sich wieder öffnen?
"""

from __future__ import annotations

import time

import pytest

from backend.core import sperre as sperre_core

# Das Model muss VOR der ``db``-Fixture importiert sein, sonst fehlt ``settings`` in
# ``Base.metadata`` und die Fixture legt die Tabelle nicht an. ``core/sperre.py``
# importiert es erst in der Funktion (Muster aus ``services/mqtt_broker_settings.py``,
# gegen Zirkelbezüge) — in der Anwendung erledigt das ``models/__init__.py`` lange vor
# ``init_db``, im Test tut es niemand.
from backend.models.settings import Settings  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_ohne_pin_ist_nichts_gesetzt(db):
    assert await sperre_core.ist_gesetzt(db) is False


async def test_pin_wird_niemals_im_klartext_abgelegt(db):
    """Der wichtigste Satz über diese Ablage.

    Die Probe liest den rohen Wert aus der Key-Value-Tabelle und behauptet, dass die
    PIN dort nicht vorkommt — nicht, dass die Funktion „hash" heißt.
    """
    await sperre_core.setze_pin(db, "geheim1234")

    roh = await sperre_core._lade(db, sperre_core.PIN_KEY)
    assert "geheim1234" not in str(roh)
    assert roh["hash"] != "geheim1234"
    assert len(roh["salt"]) == 32


async def test_richtige_pin_oeffnet_falsche_nicht(db):
    await sperre_core.setze_pin(db, "1234")

    assert await sperre_core.pin_stimmt(db, "1234") is True
    assert await sperre_core.pin_stimmt(db, "1235") is False
    assert await sperre_core.pin_stimmt(db, "") is False


async def test_zwei_gleiche_pins_bekommen_verschiedene_hashes(db):
    """Salz je PIN — sonst verrät ein Blick in zwei Installationen die Gleichheit."""
    await sperre_core.setze_pin(db, "1234")
    erster = await sperre_core._lade(db, sperre_core.PIN_KEY)

    await sperre_core.setze_pin(db, "1234")
    zweiter = await sperre_core._lade(db, sperre_core.PIN_KEY)

    assert erster["salt"] != zweiter["salt"]
    assert erster["hash"] != zweiter["hash"]


async def test_nachweis_gilt_und_faelschung_nicht(db):
    await sperre_core.setze_pin(db, "1234")
    nachweis = await sperre_core.erzeuge_nachweis(db)

    assert await sperre_core.nachweis_gueltig(db, nachweis) is True
    assert await sperre_core.nachweis_gueltig(db, None) is False
    assert await sperre_core.nachweis_gueltig(db, "") is False
    assert await sperre_core.nachweis_gueltig(db, "quatsch") is False
    assert await sperre_core.nachweis_gueltig(db, nachweis[:-4] + "aaaa") is False


async def test_abgelaufener_nachweis_gilt_nicht(db, monkeypatch):
    await sperre_core.setze_pin(db, "1234")
    nachweis = await sperre_core.erzeuge_nachweis(db)
    assert await sperre_core.nachweis_gueltig(db, nachweis) is True

    spaeter = time.time() + sperre_core.GUELTIG_SEKUNDEN + 60
    monkeypatch.setattr(sperre_core.time, "time", lambda: spaeter)

    assert await sperre_core.nachweis_gueltig(db, nachweis) is False


async def test_entfernte_pin_macht_wieder_alles_offen(db):
    await sperre_core.setze_pin(db, "1234")
    assert await sperre_core.ist_gesetzt(db) is True

    await sperre_core.entferne_pin(db)
    assert await sperre_core.ist_gesetzt(db) is False
    assert await sperre_core.pin_stimmt(db, "1234") is False


# ── Rückweg ─────────────────────────────────────────────────────────────────


async def test_rueckweg_loescht_die_pin(db, monkeypatch):
    await sperre_core.setze_pin(db, "1234")
    monkeypatch.setenv(sperre_core.RESET_ENV, "1")

    assert await sperre_core.pruefe_ruecksetzung(db) is True
    assert await sperre_core.ist_gesetzt(db) is False


async def test_rueckweg_ohne_anforderung_laesst_die_pin_stehen(db, monkeypatch):
    """Die Gegenprobe — sonst belegt die Probe darüber nur, dass Löschen geht."""
    await sperre_core.setze_pin(db, "1234")
    monkeypatch.delenv(sperre_core.RESET_ENV, raising=False)

    assert await sperre_core.pruefe_ruecksetzung(db) is False
    assert await sperre_core.ist_gesetzt(db) is True
