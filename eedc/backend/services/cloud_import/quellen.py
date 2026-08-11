"""Gespeicherte Cloud-Quellen einer Anlage — mehrere statt einer (N-229, #349).

Bis v4.0.11 lag unter `Anlage.connector_config["cloud_import"]` **ein** Objekt
`{provider_id, credentials}`. Wer zwei Wechselrichter mit je eigener
Hersteller-„Station" betreibt (Solarman führt sie so), konnte deshalb nur eine
davon speichern — die zweite verdrängte die erste bei jedem Speichern.

Jetzt steht dort eine **Liste**. Der Altbestand wird beim **Lesen** normalisiert,
nicht per Start-Migration: eine Migration müsste jede Installation anfassen, um
etwas zu erreichen, das der Leser ohnehin kann ([[feedback_migration_startup_kein_http]]).
Geschrieben wird ausschließlich die neue Form.

**Identität einer Quelle ist (Provider, Ziel-Investition)**, nicht eine laufende
Nummer. Das hat zwei erwünschte Folgen: dieselbe Station zweimal zu speichern
ersetzt sie, statt sie zu verdoppeln — und es kann je Provider nur **eine**
Quelle *ohne* Ziel geben, denn „ohne Ziel" heißt „diese Quelle beschreibt die
ganze Anlage", und davon gibt es genau eine.
"""

from __future__ import annotations

from typing import Any, Optional

CONFIG_KEY = "cloud_import"

# Schlüsselteil für eine Quelle ohne Ziel-Investition.
_OHNE_ZIEL = "anlage"


def quellen_schluessel(provider_id: str, ziel_investition_id: Optional[int]) -> str:
    """Stabile Identität einer Quelle — siehe Modul-Docstring."""
    ziel = _OHNE_ZIEL if ziel_investition_id is None else str(ziel_investition_id)
    return f"{provider_id}:{ziel}"


def _normalisiere(eintrag: dict) -> Optional[dict]:
    """Einen rohen Eintrag auf die kanonische Form bringen; None = unbrauchbar."""
    provider_id = (eintrag or {}).get("provider_id")
    if not provider_id:
        return None
    ziel = eintrag.get("ziel_investition_id")
    # JSON kennt keine ints in Objekt-Schlüsseln; aus Alt-Backups kann eine
    # Zeichenkette kommen. `is not None` statt Wahrheitswert — 0 ist keine
    # gültige ID, aber die Prüfung gehört zum Typ, nicht zum Wert.
    if isinstance(ziel, str):
        ziel = int(ziel) if ziel.strip().lstrip("-").isdigit() else None
    return {
        "provider_id": provider_id,
        "credentials": eintrag.get("credentials") or {},
        "ziel_investition_id": ziel,
        "bezeichnung": eintrag.get("bezeichnung") or None,
        "schluessel": quellen_schluessel(provider_id, ziel),
    }


def lade_quellen(connector_config: Optional[dict]) -> list[dict]:
    """Alle gespeicherten Quellen einer Anlage, Altbestand eingeschlossen.

    Gibt eine Liste kanonischer Einträge zurück (leer, wenn nichts gespeichert
    ist). Die alte Ein-Objekt-Form wird als **eine** Quelle ohne Ziel gelesen —
    das ist ihre bisherige Bedeutung: sie beschreibt die ganze Anlage.
    """
    roh: Any = (connector_config or {}).get(CONFIG_KEY)
    if not roh:
        return []
    eintraege = roh if isinstance(roh, list) else [roh]
    quellen = [q for q in (_normalisiere(e) for e in eintraege if isinstance(e, dict)) if q]

    # Doppelte Schlüssel können nur aus von Hand bearbeiteter Konfiguration oder
    # einem Alt-Backup kommen. Der letzte gewinnt — dieselbe Regel wie beim
    # Speichern, damit Lesen und Schreiben nicht auseinanderlaufen.
    nach_schluessel: dict[str, dict] = {}
    for q in quellen:
        nach_schluessel[q["schluessel"]] = q
    return list(nach_schluessel.values())


def setze_quelle(
    connector_config: Optional[dict],
    *,
    provider_id: str,
    credentials: dict,
    ziel_investition_id: Optional[int] = None,
    bezeichnung: Optional[str] = None,
) -> dict:
    """Eine Quelle anlegen oder ersetzen; gibt die neue `connector_config` zurück.

    Die Reihenfolge bleibt erhalten (ersetzen an Ort und Stelle), damit die
    Anzeige nicht bei jedem Speichern springt.
    """
    config = dict(connector_config or {})
    quellen = lade_quellen(config)
    neu = _normalisiere({
        "provider_id": provider_id,
        "credentials": credentials,
        "ziel_investition_id": ziel_investition_id,
        "bezeichnung": bezeichnung,
    })
    if neu is None:
        raise ValueError("provider_id fehlt")

    ersetzt = False
    for i, q in enumerate(quellen):
        if q["schluessel"] == neu["schluessel"]:
            quellen[i] = neu
            ersetzt = True
            break
    if not ersetzt:
        quellen.append(neu)

    config[CONFIG_KEY] = [_ohne_schluessel(q) for q in quellen]
    return config


def entferne_quelle(
    connector_config: Optional[dict], schluessel: Optional[str] = None
) -> tuple[dict, int]:
    """Eine Quelle (oder alle) entfernen.

    `schluessel=None` entfernt **alle** — das ist das bisherige Verhalten von
    `DELETE /credentials/{anlage_id}` und bleibt die Bedeutung ohne Parameter.

    Returns:
        (neue connector_config, Anzahl entfernter Quellen)
    """
    config = dict(connector_config or {})
    quellen = lade_quellen(config)
    if not quellen:
        config.pop(CONFIG_KEY, None)
        return config, 0

    if schluessel is None:
        config.pop(CONFIG_KEY, None)
        return config, len(quellen)

    bleibt = [q for q in quellen if q["schluessel"] != schluessel]
    entfernt = len(quellen) - len(bleibt)
    if bleibt:
        config[CONFIG_KEY] = [_ohne_schluessel(q) for q in bleibt]
    else:
        config.pop(CONFIG_KEY, None)
    return config, entfernt


def _ohne_schluessel(quelle: dict) -> dict:
    """Der Schlüssel ist abgeleitet — er wird nicht mitgespeichert, sonst gäbe es
    zwei Wahrheiten, sobald sich die Ableitungsregel ändert."""
    return {k: v for k, v in quelle.items() if k != "schluessel"}
