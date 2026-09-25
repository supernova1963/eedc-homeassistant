"""HA-Export — der E-Mob-Pool: IMD-Anreicherung um den abgeleiteten PV-Anteil (F-16) und der Wallbox-Pool-Kontext
(F-17), geteilt von Anlagen- und Investitions-Sensoren und vom MQTT-Publish-Job (`services/ha_mqtt_sync.py`).
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from backend.services.eauto_wirtschaftlichkeit import (
    EmobPoolCtx,
    build_emob_pool_ctx,
    emob_extern_im_monat,
    emob_heimladung_im_monat,
    emob_month_share,
)
from backend.services.emob_ladeanteil import reichere_monatszeilen_an_mit_quoten
from backend.services.emob_heimlade_quellen import laufende_heimlade_quellen
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

_build_emob_pool_ctx = build_emob_pool_ctx

_emob_month_share = emob_month_share

_emob_heimladung_im_monat = emob_heimladung_im_monat

_emob_extern_im_monat = emob_extern_im_monat

async def _reichere_emob_imd_an(
    db: AsyncSession,
    anlage_id: int,
    inv_daten: dict,
    wallbox_ids: set,
) -> dict:
    """Kurzform von ``_reichere_emob_imd_an_mit_quoten`` ohne die Quoten."""
    daten, _quoten = await _reichere_emob_imd_an_mit_quoten(db, anlage_id, inv_daten, wallbox_ids)
    return daten


async def _reichere_emob_imd_an_mit_quoten(
    db: AsyncSession,
    anlage_id: int,
    inv_daten: dict,
    wallbox_ids: set,
) -> tuple[dict, dict]:
    """F-16: die E-Mob-Zeilen mit abgeleitetem PV-Anteil, Schlüssel unverändert.

    Der HA-Export liest ``InvestitionMonatsdaten`` direkt (P10-Restschuld) und
    speist daraus drei Sensor-Gruppen: die anlagenweite E-Auto-Ersparnis, die
    Fahrzeug-Sensoren (darunter ``e_auto_pv_anteil_prozent``) und den
    PHEV-Zweig. Ohne diese Anreicherung meldete HA dauerhaft 0 % PV-Anteil,
    während die Oberfläche denselben Wert abgeleitet zeigt.

    ⚑ **Wertänderung an einem ausgelieferten Sensor** (Entscheid Gernot
    2026-08-08): wer keinen PV-Ladesensor pflegt, bekommt in der
    HA-Langzeitstatistik einen einmaligen Sprung — dasselbe Muster wie beim
    CO₂-Sensor zu v4.0.0. Gehört in die Release-Kommunikation.
    """
    if not inv_daten:
        return inv_daten, {}
    keys = list(inv_daten)
    daten, quoten = await reichere_monatszeilen_an_mit_quoten(
        db,
        anlage_id,
        [
            ((jahr, monat), inv_id in wallbox_ids, inv_daten[(inv_id, jahr, monat)])
            for (inv_id, jahr, monat) in keys
        ],
    )
    # N-555: die Quoten braucht die Schätzung aus dem Fahrverbrauch
    # (`build_emob_pool_ctx(quoten=…)`), sonst hätte sie PV-Anteil 0 %.
    return dict(zip(keys, daten)), quoten

async def _load_emob_pool_ctx(db: AsyncSession, investitionen) -> Optional[_EmobPoolCtx]:
    """Lädt + filtert die Emob-IMD einer Anlage und baut den Pool-Kontext —
    für Aufrufer, die nur die Investitionsliste, aber keine IMD geladen haben
    (z. B. die per-Investition-Sensor-Schleife)."""
    emob = [
        i for i in investitionen
        if i.typ in ("e-auto", "wallbox") and not ist_dienstlich(i)
    ]
    if not emob:
        return None
    by_id = {i.id: i for i in emob}
    res = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_([i.id for i in emob])
        )
    )
    inv_daten: dict = {}
    for md in res.scalars().all():
        inv = by_id.get(md.investition_id)
        if inv and inv.ist_aktiv_im_monat(md.jahr, md.monat):
            inv_daten[(md.investition_id, md.jahr, md.monat)] = md.verbrauch_daten or {}
    wallbox_ids = {i.id for i in emob if i.typ == "wallbox"}
    inv_daten, quoten = await _reichere_emob_imd_an_mit_quoten(
        db, emob[0].anlage_id, inv_daten, wallbox_ids
    )
    wallboxen = [i for i in emob if i.typ == "wallbox"]
    return _build_emob_pool_ctx(
        inv_daten,
        {i.id for i in emob if i.typ == "e-auto"},
        wallbox_ids,
        wallbox_in_betrieb=lambda j, m: any(w.ist_aktiv_im_monat(j, m) for w in wallboxen),
        quoten=quoten,
        quellen_je_monat=await laufende_heimlade_quellen(db, emob[0].anlage_id, emob),
    )
