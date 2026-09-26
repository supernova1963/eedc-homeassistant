"""HA-Export — der E-Mob-Pool-Kontext (F-16/F-17, seit N-555 Stufe 2 über `services/emob_kontext.py`),
geteilt von Anlagen- und Investitions-Sensoren und vom MQTT-Publish-Job (`services/ha_mqtt_sync.py`).
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from backend.services.eauto_wirtschaftlichkeit import (
    EmobPoolCtx,
    emob_extern_im_monat,
    emob_heimladung_im_monat,
    emob_month_share,
)
from backend.services.emob_kontext import lade_emob_kontext
from backend.models.investition import InvestitionMonatsdaten
from backend.core.investition_parameter import ist_dienstlich


# =============================================================================
# Hilfsfunktionen für Berechnungen
# =============================================================================

# F-17: Pool-Kontext + Monats-Share liegen seit 2026-08-08 im Layer-SoT
# (`services/eauto_wirtschaftlichkeit`). Sie standen hier privat — und waren
# damit für `aussichten/finanzen.py` unerreichbar, das als einzige der fünf E-Mob-Sichten
# gar keine Pool-Attribution hatte. Die Namen bleiben lokal gebunden, damit die
# Aufrufstellen unverändert lesbar sind.
_EmobPoolCtx = EmobPoolCtx

_emob_month_share = emob_month_share

_emob_heimladung_im_monat = emob_heimladung_im_monat

_emob_extern_im_monat = emob_extern_im_monat

async def _load_emob_pool_ctx(db: AsyncSession, investitionen) -> Optional[_EmobPoolCtx]:
    """Lädt die E-Mob-IMD einer Anlage und baut den Pool-Kontext —
    für Aufrufer, die nur die Investitionsliste, aber keine IMD geladen haben
    (z. B. die per-Investition-Sensor-Schleife).

    N-555 Stufe 2: über den einen Kontext (`services/emob_kontext.py`) — mit Dienstwagen,
    dienstlicher Wallbox, Herkunft von „Heim: gesamt" und den Quellen des laufenden Monats.
    Bis 26.09.2026 stand hier ein eigener Nachbau nur über die privaten Zeilen; mit ihm
    liegen die Anreicherungs-Helfer ``_reichere_emob_imd_an[_mit_quoten]`` nicht mehr hier.
    ⚑ **Wertänderung an einem ausgelieferten Sensor** (Entscheid Gernot 2026-08-08, F-16):
    wer keinen PV-Ladesensor pflegt, bekommt den abgeleiteten PV-Anteil — seit damals so.
    """
    emob = [i for i in investitionen if i.typ in ("e-auto", "wallbox")]
    if not any(not ist_dienstlich(i) for i in emob):
        return None
    res = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_([i.id for i in emob])
        )
    )
    kontext = await lade_emob_kontext(db, emob[0].anlage_id, emob, res.scalars().all())
    return kontext.ctx
