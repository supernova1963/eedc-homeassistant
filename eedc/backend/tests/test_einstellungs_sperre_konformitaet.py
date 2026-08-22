"""
Wächter der Einstellungs-Sperre — **jede** schreibende Route ist gesperrt.

**Warum baumweit und nicht Fall für Fall.** Die Sperre entscheidet über die *Methode*,
nicht über eine gepflegte Routenliste. Dieser Test hält genau das fest: Er liest die
Routen aus der OpenAPI der laufenden App — also aus derselben Quelle, aus der auch der
Client sie kennt — und behauptet für jede schreibende Route, dass sie bei gesetzter PIN
mit **423** antwortet. Eine morgen hinzugefügte Route ist damit automatisch abgedeckt,
ohne dass jemand diese Datei anfassen muss.

Wer eine Ausnahme braucht, trägt sie unten ein und begründet sie dort. Das ist der ganze
Sinn der Konstruktion: Eine Ausnahme ist dann eine sichtbare Entscheidung und kein
Vergessen.

Gemessen beim Bau (2026-08-22): 98 schreibende Routen, zwei unabhängige Erhebungen
(OpenAPI und Dekoratoren-Grep) mit demselben Ergebnis.
"""

from __future__ import annotations

import contextlib

import httpx
import pytest

from backend.core import sperre as sperre_core
from backend.main import SPERRE_AUSNAHMEN, SPERRE_METHODEN, app

# ⛔ Die Verben stehen hier EIGENSTÄNDIG und werden bewusst NICHT aus ``main`` bezogen.
# Beim Bau gemessen (2026-08-22): Mit ``SPERRE_METHODEN`` als Quelle war dieser Test
# wertlos — ein Sprengsatz, der ``DELETE`` aus der Sperre nahm, ließ ihn grün, weil er
# dann eben keine DELETE-Route mehr prüfte. Ein Prüfer, der seine Sollmenge vom
# Prüfling bezieht, misst sich selbst.
SCHREIB_VERBEN = {"POST", "PUT", "PATCH", "DELETE"}

pytestmark = pytest.mark.asyncio


# Die einzigen Pfade, die auch bei gesetzter PIN durchgelassen werden.
#
# `/entsperren` muss offen sein, sonst käme niemand mehr herein — die Route *ist* das
# Schloss. `/sperren` ist symmetrisch dazu und ändert serverseitig nichts.
#
# Ausdrücklich NICHT ausgenommen: `/api/sperre/pin` (setzen/ändern) und `DELETE
# /api/sperre/pin` (entfernen). Solange keine PIN gesetzt ist, greift die Sperre gar
# nicht — die erste PIN kann also jeder setzen. Ist eine gesetzt, muss man entsperrt
# sein, um sie zu ändern oder loszuwerden. Genau so soll es sein.
ERWARTETE_AUSNAHMEN = {"/api/sperre/entsperren", "/api/sperre/sperren"}


def _schreib_routen() -> list[tuple[str, str]]:
    spec = app.openapi()
    return sorted(
        (m.upper(), pfad)
        for pfad, ops in spec["paths"].items()
        for m in ops
        if m.upper() in SCHREIB_VERBEN
    )


def _beispiel_pfad(pfad: str) -> str:
    """Platzhalter durch einen Wert ersetzen, den es garantiert nicht gibt.

    Der Wert ist bewusst absurd: Die Anfrage darf den Handler **nie** erreichen. Träfe
    sie einen echten Datensatz und käme die Sperre nicht, hätte der Test Daten gelöscht,
    statt einen Fehler zu melden.
    """
    out, tiefe = [], 0
    for zeichen in pfad:
        if zeichen == "{":
            tiefe += 1
            continue
        if zeichen == "}":
            tiefe -= 1
            out.append("999999999")
            continue
        if tiefe == 0:
            out.append(zeichen)
    return "".join(out)


@pytest.fixture
def gesperrt(monkeypatch):
    """PIN gesetzt, Sitzung nicht entsperrt — ohne Datenbank.

    Die Middleware öffnet sonst eine echte Sitzung. Für die Frage, die dieser Test
    stellt — *entscheidet die Middleware für jede schreibende Route auf gesperrt?* —
    braucht es keine, und eine echte Datenbank würde die Aussage nur verwässern.
    """
    import backend.core.database as db_modul

    @contextlib.asynccontextmanager
    async def _keine_sitzung():
        yield None

    monkeypatch.setattr(db_modul, "async_session_maker", _keine_sitzung)

    async def _gesetzt(_db):
        return True

    async def _ungueltig(_db, _nachweis):
        return False

    monkeypatch.setattr(sperre_core, "ist_gesetzt", _gesetzt)
    monkeypatch.setattr(sperre_core, "nachweis_gueltig", _ungueltig)


async def _ruf(methode: str, pfad: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(methode, pfad, **kwargs)


# ── Der eigentliche Wächter ─────────────────────────────────────────────────


async def test_jede_schreibende_route_ist_gesperrt(gesperrt):
    routen = _schreib_routen()
    assert routen, "Keine schreibenden Routen gefunden — der Prüfer misst das falsche Objekt."

    durchgelassen = []
    for methode, pfad in routen:
        if pfad in ERWARTETE_AUSNAHMEN:
            continue
        antwort = await _ruf(methode, _beispiel_pfad(pfad))
        if antwort.status_code != 423:
            durchgelassen.append(f"{methode} {pfad} → {antwort.status_code}")

    assert not durchgelassen, (
        "Diese schreibenden Routen kommen an der Sperre vorbei:\n  "
        + "\n  ".join(durchgelassen)
    )


async def test_der_pruefer_kann_ueberhaupt_rot_melden(gesperrt, monkeypatch):
    """Gegenprobe: Ohne gesetzte PIN darf **nichts** gesperrt sein.

    Ein Wächter, der nur grün kennt, beweist nichts. Diese Probe dreht die einzige
    Bedingung um und verlangt das Gegenteil — meldete der Test oben auch hier 423,
    prüfte er nicht die Sperre, sondern irgendetwas anderes.
    """
    antwort = await _ruf("POST", "/api/anlagen/", json={})
    assert antwort.status_code == 423

    async def _nicht_gesetzt(_db):
        return False

    monkeypatch.setattr(sperre_core, "ist_gesetzt", _nicht_gesetzt)
    antwort = await _ruf("POST", "/api/anlagen/", json={})
    assert antwort.status_code != 423, (
        "Ohne gesetzte PIN darf die Sperre nicht greifen — sonst bestraft sie jeden, "
        "der sie nie eingeschaltet hat."
    )


async def test_lesende_aufrufe_bleiben_frei(monkeypatch):
    """Ansehen ist nie gesperrt — und zwar, bevor die Sperre irgendetwas nachschlägt.

    ⛔ **Diese Probe hat den CI-Lauf zu v4.0.26 rot gemacht, und das lag an ihr.** Sie rief
    ``GET /api/anlagen/`` auf. Auf dieser Box liegt eine gefüllte Datenbank, auf einem
    frischen Runner nicht — dort endete sie in *no such table: anlagen*, während das
    Produkt einwandfrei war (3502 andere Proben grün). *Ein Test, der die Umgebung
    mitmisst, prüft nicht die Regel, sondern die Box.* Dieselbe Klasse, gegen die
    ``conftest.py`` beim Netz einen Wächter hat.

    Jetzt ohne Datenbank — und dabei **schärfer** als vorher: Die Sperre bekommt eine
    ``ist_gesetzt``-Funktion, die beim Aufruf **explodiert**. Kommt der lesende Aufruf
    trotzdem durch, ist bewiesen, dass die Middleware ihn abzweigt, *bevor* sie eine
    Sitzung öffnet oder irgendetwas nachschlägt. Vorher belegte die Probe nur „nicht 423".
    """

    async def _darf_nicht_aufgerufen_werden(_db):
        raise AssertionError(
            "Die Sperre hat bei einem lesenden Aufruf nachgeschlagen — der frühe "
            "Ausstieg über die Methode greift nicht mehr."
        )

    monkeypatch.setattr(sperre_core, "ist_gesetzt", _darf_nicht_aufgerufen_werden)

    # `/api/health` braucht keine Datenbank — genau deshalb steht hier diese Route.
    antwort = await _ruf("GET", "/api/health")
    assert antwort.status_code == 200
    assert antwort.status_code != 423


async def test_alle_schreib_verben_sind_von_der_sperre_erfasst():
    """Die Sperre darf kein Verb auslassen.

    Zweite Hälfte der Lehre oben: Der Wächter prüft nicht nur *Routen*, sondern auch,
    dass der Produktivcode dieselbe Menge an Verben kennt wie er selbst.
    """
    assert set(SPERRE_METHODEN) == SCHREIB_VERBEN


async def test_ausnahmeliste_ist_die_erwartete():
    """Die Ausnahmen stehen im Produktivcode — dieser Test hält sie fest.

    Wächst die Liste, fällt dieser Test um, und wer sie erweitert hat, muss die
    Begründung oben nachtragen. Genau dafür ist er da.
    """
    assert set(SPERRE_AUSNAHMEN) == ERWARTETE_AUSNAHMEN


async def test_antwort_sagt_dem_client_worum_es_geht(gesperrt):
    """Der Client öffnet den Entsperr-Dialog nur bei genau diesem Fall."""
    antwort = await _ruf("POST", "/api/anlagen/", json={})
    assert antwort.status_code == 423
    rumpf = antwort.json()
    assert rumpf.get("sperre") is True
    assert "PIN" in rumpf.get("detail", "")
