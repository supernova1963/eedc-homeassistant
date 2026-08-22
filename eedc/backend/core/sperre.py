"""
Einstellungs-Sperre — eine optionale PIN vor allen schreibenden API-Aufrufen.

**Was sie ist und was sie ausdrücklich nicht ist.** Sie ist ein *Schloss*, kein
Berechtigungssystem: eedc kennt keine Benutzer, keine Rollen und kein Login, und das
soll auch so bleiben (Gernot 2026-08-22). Es gibt genau einen Schlüssel, und wer ihn
hat, darf alles. Die Sperre unterscheidet nicht, *wer* davorsitzt — nur, *ob* diese
Browser-Sitzung schon einmal entsperrt hat.

**Warum überhaupt.** Zwei Melder auf derselben Fläche: #393 möchte eedc für
Nicht-Administratoren in der Home-Assistant-Seitenleiste sichtbar machen (Wandtablets),
#391 möchte, dass Familie und Besucher die Auswertungen ansehen, aber nichts verstellen.
Das ist ein **Bedienwunsch**, keine Gefahrenabwehr — eine Add-on-Oberfläche ist in Home
Assistant nach der Anmeldung offen, und es ist nicht Aufgabe von eedc, das zu ändern.

**Warum nicht über die Benutzerkennung.** Der Supervisor reicht ``X-Remote-User-Id`` und
Geschwister ans Add-on durch (an 2026.07.5 nachgelesen, gegen Fälschung gefiltert). Damit
ließe sich eine Liste „wer darf ändern" bauen — verworfen, aus zwei Gründen: Sie *wäre*
das Berechtigungssystem, das es nicht geben soll, und sie funktioniert **nur** als
HA-Add-on. Im Standalone-Betrieb spricht der Browser eedc direkt an, ohne Supervisor
dazwischen, also ohne diese Header; ein HA-Token ändert daran nichts, der zeigt in die
Gegenrichtung (eedc → HA). Eine Sperre, die eine der beiden Betriebsarten nicht kennt,
verstößt gegen Standalone-First.

**Nicht aktiviert heißt: nichts ändert sich.** Ohne gesetzte PIN greift die Middleware
nicht ein — niemand wird für einen Schutz bestraft, den er nicht braucht.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Key-Value-Schlüssel in der bestehenden ``settings``-Tabelle. Bewusst dort und nicht
# als neue Spalte: die Tabelle existiert (``models/settings.py``), damit braucht die
# Sperre **keine Migration**.
PIN_KEY = "einstellungen_pin"
SECRET_KEY = "sperre_secret"

# Der Nachweis wird als Header geschickt, nicht als Cookie. Unter HA-Ingress liegt die
# Anwendung auf einem verschachtelten Pfad (``/api/hassio_ingress/<token>/``) und teilt
# die Domain mit Home Assistant; ein Cookie müsste dort über Pfad und SameSite genau
# richtig gesetzt sein, um weder zu fehlen noch fremde Anfragen zu begleiten. Ein
# eigener Header hat diese Semantik nicht.
HEADER = "X-EEDC-Entsperrt"

# Der Nachweis lebt ohnehin nur bis zum Schließen des Browsers (der Client legt ihn in
# ``sessionStorage`` ab). Die Frist hier ist die zweite Hälfte davon: sie begrenzt einen
# Nachweis, der die Sitzung überdauert hat, weil ihn jemand herauskopiert hat.
GUELTIG_SEKUNDEN = 12 * 60 * 60

MIN_LAENGE = 4

# PBKDF2 ist hier ausreichend und überall verfügbar. Es geht um eine PIN gegen
# Mitbewohner, nicht um einen Passwort-Tresor.
_ITERATIONEN = 200_000


# =============================================================================
# Ablage
# =============================================================================


async def _lade(db: AsyncSession, key: str) -> Optional[dict]:
    from backend.models.settings import Settings as SettingsModel

    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()
    return row.value if row and row.value else None


async def _speichere(db: AsyncSession, key: str, wert: Optional[dict]) -> None:
    from backend.models.settings import Settings as SettingsModel

    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()
    if wert is None:
        if row is not None:
            await db.delete(row)
        return
    if row is None:
        db.add(SettingsModel(key=key, value=wert))
    else:
        row.value = wert


async def _secret(db: AsyncSession) -> str:
    """Signatur-Geheimnis, beim ersten Gebrauch erzeugt.

    Es wird **nicht** beim Entfernen der PIN gelöscht: Wer die PIN neu setzt, soll nicht
    versehentlich alte Nachweise wieder gültig machen — dasselbe Geheimnis weiterzuführen
    ist hier das Konservative, weil die Nachweise ohnehin an ``iat`` gebunden sind.
    """
    vorhanden = await _lade(db, SECRET_KEY)
    if vorhanden and vorhanden.get("wert"):
        return vorhanden["wert"]
    neu = secrets.token_hex(32)
    await _speichere(db, SECRET_KEY, {"wert": neu})
    await db.commit()
    return neu


# =============================================================================
# PIN
# =============================================================================


def _hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), bytes.fromhex(salt), _ITERATIONEN
    ).hex()


async def ist_gesetzt(db: AsyncSession) -> bool:
    eintrag = await _lade(db, PIN_KEY)
    return bool(eintrag and eintrag.get("hash"))


async def setze_pin(db: AsyncSession, pin: str) -> None:
    """Setzt oder ändert die PIN. Der Klartext wird nirgends abgelegt."""
    salt = secrets.token_hex(16)
    await _speichere(
        db,
        PIN_KEY,
        {"salt": salt, "hash": _hash(pin, salt), "gesetzt_am": int(time.time())},
    )
    await db.commit()


async def entferne_pin(db: AsyncSession) -> None:
    await _speichere(db, PIN_KEY, None)
    await db.commit()


async def pin_stimmt(db: AsyncSession, pin: str) -> bool:
    eintrag = await _lade(db, PIN_KEY)
    if not eintrag or not eintrag.get("hash"):
        return False
    return hmac.compare_digest(_hash(pin, eintrag["salt"]), eintrag["hash"])


# =============================================================================
# Nachweis
# =============================================================================


def _signiere(secret: str, iat: int) -> str:
    return hmac.new(
        secret.encode("utf-8"), str(iat).encode("utf-8"), hashlib.sha256
    ).hexdigest()


async def erzeuge_nachweis(db: AsyncSession) -> str:
    iat = int(time.time())
    secret = await _secret(db)
    roh = f"{iat}.{_signiere(secret, iat)}"
    return base64.urlsafe_b64encode(roh.encode("utf-8")).decode("ascii")


async def nachweis_gueltig(db: AsyncSession, nachweis: Optional[str]) -> bool:
    if not nachweis:
        return False
    try:
        roh = base64.urlsafe_b64decode(nachweis.encode("ascii")).decode("utf-8")
        iat_text, signatur = roh.split(".", 1)
        iat = int(iat_text)
    except Exception:
        return False
    if abs(int(time.time()) - iat) > GUELTIG_SEKUNDEN:
        return False
    secret = await _secret(db)
    return hmac.compare_digest(_signiere(secret, iat), signatur)


# =============================================================================
# Rückweg
# =============================================================================

# Der Rückweg verlangt Zugriff auf die Maschine — im Add-on die Add-on-Konfiguration,
# im Standalone-Betrieb die Umgebung. Ausdrücklich **keine** öffentlich dokumentierte
# Reset-Adresse: Wer die PIN umgehen möchte, gehört per Annahme zum Haushalt und fände
# eine solche Adresse mit derselben Suche wie der Eigentümer. Ein Knopf neben der Sperre
# wäre noch direkter.
RESET_ENV = "EEDC_PIN_RESET"


async def pruefe_ruecksetzung(db: AsyncSession) -> bool:
    """Beim Start aufgerufen. Löscht die PIN, wenn der Rückweg angefordert wurde."""
    if os.environ.get(RESET_ENV, "").strip().lower() not in ("1", "true", "yes"):
        return False
    if not await ist_gesetzt(db):
        logger.info("PIN-Rücksetzung angefordert — es war keine PIN gesetzt.")
        return False
    await entferne_pin(db)
    logger.warning(
        "Die Einstellungs-PIN wurde über %s zurückgesetzt. "
        "Bitte die Option wieder abschalten, sonst bleibt eedc bei jedem Start offen.",
        RESET_ENV,
    )
    return True
