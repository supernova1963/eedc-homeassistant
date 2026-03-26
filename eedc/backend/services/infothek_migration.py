"""
Infothek Migration Service

Migriert stamm_*, ansprechpartner_* und wartung_* Felder aus
Investition.parameter in Infothek-Einträge.

Pro Investition mit gefüllten Feldern wird ein verknüpfter
Infothek-Eintrag erstellt. Nach erfolgreicher Übernahme werden
die migrierten Keys aus dem JSON gelöscht.
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.investition import Investition
from backend.models.infothek import InfothekEintrag

logger = logging.getLogger(__name__)

# Mapping: stamm_*-Felder → Infothek-Kategorie und Feld
STAMM_MAPPING = {
    # stamm_* → garantie
    "stamm_hersteller": ("garantie", "hersteller"),
    "stamm_modell": ("garantie", "produkt"),
    "stamm_seriennummer": ("garantie", "garantie_nummer"),
    "stamm_garantie_bis": ("garantie", "garantie_bis"),
    # Typ-spezifische stamm_*
    "stamm_garantie_zyklen": ("garantie", "bedingungen"),
    "stamm_garantie_leistung_prozent": ("garantie", "bedingungen"),
    "stamm_garantie_batterie_km": ("garantie", "bedingungen"),
    "stamm_mastr_id": ("marktstammdatenregister", "mastr_nummer"),
}

FOERDERUNG_MAPPING = {
    "stamm_foerderung_aktenzeichen": ("foerderung", "aktenzeichen"),
    "stamm_foerderung_betrag_euro": ("foerderung", "betrag_euro"),
}

ANSPRECHPARTNER_MAPPING = {
    "ansprechpartner_firma": "firma",
    "ansprechpartner_name": "name",
    "ansprechpartner_telefon": "telefon",
    "ansprechpartner_email": "email",
    "ansprechpartner_ticketsystem": "ticketsystem_url",
    "ansprechpartner_kundennummer": "kundennummer",
    "ansprechpartner_vertragsnummer": None,  # Wird in Notizen übernommen
    "ansprechpartner_notizen": None,  # Wird in Notizen übernommen
}

WARTUNG_MAPPING = {
    "wartung_vertragsnummer": "vertragsnummer",
    "wartung_anbieter": "anbieter",
    "wartung_gueltig_bis": "gueltig_bis",
    "wartung_kuendigungsfrist": "kuendigungsfrist_monate",
    "wartung_leistungsumfang": "leistungsumfang",
}

# Alle migrierbare Keys
ALLE_MIGRIER_KEYS = (
    set(STAMM_MAPPING.keys())
    | set(FOERDERUNG_MAPPING.keys())
    | set(ANSPRECHPARTNER_MAPPING.keys())
    | set(WARTUNG_MAPPING.keys())
    | {"stamm_notizen", "stamm_kennzeichen", "stamm_fahrgestellnummer",
       "stamm_erstzulassung", "stamm_anmeldung_netzbetreiber",
       "stamm_anmeldung_marktstammdaten"}
)


def _hat_migrier_daten(parameter: dict) -> bool:
    """Prüft ob ein parameter-JSON migrierbate Felder enthält."""
    return any(
        parameter.get(key) is not None and parameter.get(key) != ""
        for key in ALLE_MIGRIER_KEYS
    )


def _extrahiere_garantie(parameter: dict, inv: Investition) -> dict | None:
    """Extrahiert Garantie-Daten aus stamm_*-Feldern."""
    result = {}
    for src_key, (kategorie, dest_key) in STAMM_MAPPING.items():
        if kategorie != "garantie":
            continue
        val = parameter.get(src_key)
        if val is not None and val != "":
            # Sonderfälle für bedingungen
            if dest_key == "bedingungen":
                existing = result.get("bedingungen", "")
                label = src_key.replace("stamm_garantie_", "").replace("_", " ").title()
                result["bedingungen"] = f"{existing}{label}: {val}\n".strip()
            else:
                result[dest_key] = val
    return result if result else None


def _extrahiere_ansprechpartner(parameter: dict) -> tuple[dict | None, str]:
    """Extrahiert Ansprechpartner-Daten. Gibt (parameter, notizen) zurück."""
    result = {}
    notizen_parts = []
    for src_key, dest_key in ANSPRECHPARTNER_MAPPING.items():
        val = parameter.get(src_key)
        if val is not None and val != "":
            if dest_key is None:
                label = src_key.replace("ansprechpartner_", "").replace("_", " ").title()
                notizen_parts.append(f"{label}: {val}")
            else:
                result[dest_key] = val
    notizen = "\n".join(notizen_parts) if notizen_parts else ""
    return (result if result else None), notizen


def _extrahiere_wartung(parameter: dict) -> dict | None:
    """Extrahiert Wartungsvertrag-Daten."""
    result = {}
    for src_key, dest_key in WARTUNG_MAPPING.items():
        val = parameter.get(src_key)
        if val is not None and val != "":
            result[dest_key] = val
    return result if result else None


def _extrahiere_foerderung(parameter: dict) -> dict | None:
    """Extrahiert Förderungs-Daten."""
    result = {}
    for src_key, (_, dest_key) in FOERDERUNG_MAPPING.items():
        val = parameter.get(src_key)
        if val is not None and val != "":
            result[dest_key] = val
    return result if result else None


def _extrahiere_mastr(parameter: dict) -> dict | None:
    """Extrahiert MaStR-Daten."""
    mastr_id = parameter.get("stamm_mastr_id")
    if mastr_id:
        return {"mastr_nummer": mastr_id}
    return None


async def check_migration_status(
    db: AsyncSession,
    anlage_id: int,
) -> dict:
    """
    Prüft welche Investitionen migrierbate Stammdaten haben.

    Returns: {investitionen: [{id, bezeichnung, typ, felder: [...]}], total: int}
    """
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    migrierbar = []
    for inv in investitionen:
        if not inv.parameter:
            continue
        if _hat_migrier_daten(inv.parameter):
            felder = [k for k in ALLE_MIGRIER_KEYS if inv.parameter.get(k)]
            migrierbar.append({
                "id": inv.id,
                "bezeichnung": inv.bezeichnung,
                "typ": inv.typ,
                "felder": felder,
            })

    return {"investitionen": migrierbar, "total": len(migrierbar)}


async def migrate_investition(
    db: AsyncSession,
    investition_id: int,
) -> list[dict]:
    """
    Migriert stamm_*-Daten einer Investition in Infothek-Einträge.

    Erstellt pro Kategorie (Garantie, Ansprechpartner, Wartung, Förderung, MaStR)
    einen eigenen Infothek-Eintrag, verknüpft mit der Investition.
    Löscht die migrierten Keys aus dem parameter-JSON.

    Returns: Liste der erstellten Einträge als dicts.
    """
    result = await db.execute(
        select(Investition).where(Investition.id == investition_id)
    )
    inv = result.scalar_one_or_none()
    if not inv or not inv.parameter:
        return []

    if not _hat_migrier_daten(inv.parameter):
        return []

    params = dict(inv.parameter)
    created = []

    # 1. Garantie
    garantie_data = _extrahiere_garantie(params, inv)
    if garantie_data:
        notizen = params.get("stamm_notizen", "")
        eintrag = InfothekEintrag(
            anlage_id=inv.anlage_id,
            bezeichnung=f"Garantie {inv.bezeichnung}",
            kategorie="garantie",
            parameter=garantie_data,
            notizen=notizen or None,
            investition_id=inv.id,
        )
        db.add(eintrag)
        created.append({"kategorie": "garantie", "bezeichnung": eintrag.bezeichnung})

    # 2. Ansprechpartner
    asp_data, asp_notizen = _extrahiere_ansprechpartner(params)
    if asp_data:
        eintrag = InfothekEintrag(
            anlage_id=inv.anlage_id,
            bezeichnung=f"Kontakt {inv.bezeichnung}",
            kategorie="ansprechpartner",
            parameter=asp_data,
            notizen=asp_notizen or None,
            investition_id=inv.id,
        )
        db.add(eintrag)
        created.append({"kategorie": "ansprechpartner", "bezeichnung": eintrag.bezeichnung})

    # 3. Wartungsvertrag
    wartung_data = _extrahiere_wartung(params)
    if wartung_data:
        eintrag = InfothekEintrag(
            anlage_id=inv.anlage_id,
            bezeichnung=f"Wartung {inv.bezeichnung}",
            kategorie="wartungsvertrag",
            parameter=wartung_data,
            investition_id=inv.id,
        )
        db.add(eintrag)
        created.append({"kategorie": "wartungsvertrag", "bezeichnung": eintrag.bezeichnung})

    # 4. Förderung
    foerderung_data = _extrahiere_foerderung(params)
    if foerderung_data:
        eintrag = InfothekEintrag(
            anlage_id=inv.anlage_id,
            bezeichnung=f"Förderung {inv.bezeichnung}",
            kategorie="foerderung",
            parameter=foerderung_data,
            investition_id=inv.id,
        )
        db.add(eintrag)
        created.append({"kategorie": "foerderung", "bezeichnung": eintrag.bezeichnung})

    # 5. Marktstammdatenregister
    mastr_data = _extrahiere_mastr(params)
    if mastr_data:
        eintrag = InfothekEintrag(
            anlage_id=inv.anlage_id,
            bezeichnung=f"MaStR {inv.bezeichnung}",
            kategorie="marktstammdatenregister",
            parameter=mastr_data,
            investition_id=inv.id,
        )
        db.add(eintrag)
        created.append({"kategorie": "marktstammdatenregister", "bezeichnung": eintrag.bezeichnung})

    # Keys aus parameter löschen
    if created:
        for key in ALLE_MIGRIER_KEYS:
            params.pop(key, None)
        inv.parameter = params
        flag_modified(inv, "parameter")
        db.add(inv)
        await db.commit()

        logger.info(
            f"Migration Investition '{inv.bezeichnung}' (ID {inv.id}): "
            f"{len(created)} Einträge erstellt"
        )

    return created
