"""Diagnose-Paket v4 bereitstellen — ZIP in die Ablage, Antwort mit Marke und Inhaltsliste (Konzept E9, Bauplan §3.4).

``bereitstellen(anlage_id)`` baut ``eedc_diagnose_<slug>_<JJJJ-MM-TT>.zip`` (``tabellen/<t>.json`` alphabetisch →
``lage.json`` → ``inhalt.json`` zuletzt) in ``….zip.teil``, ersetzt danach atomar, legt den Eintrag in der Ablage ab und
antwortet mit den Paket-Feldern. Wirft der Bau, gibt es keine Datei (G5); ein Teil der Lage oder eine Tabelle, die wirft,
steht in ``inhalt.json`` (das Paket kommt). **Variante A (synchron)** nach S0: Ingress ließ 300 s auf allen vier Wegen durch.

Schreibt nichts in die Datenbank (jeder Lage-Teil in eigener, zurückgerollter Sitzung; Auszug ``mode=ro``).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import httpx
from sqlalchemy import select

from backend.services.diagnose_paket import ablage
from backend.services.diagnose_paket.auszug import AuszugErgebnis, auszug
from backend.services.diagnose_paket.lage import LageErgebnis, baue_lage
from backend.services.diagnose_paket.register import PROFIL_DIAGNOSE

#: Bis zu dieser Dateigröße (Bytes) ist die Mail der Versandweg, darüber der Freigabe-Link (Entscheid Gernot 14.11.: 10 MB).
MAIL_GRENZE_BYTES = 10_000_000
_STUNDENWERTE = ("tages_energie_profil", "kanal_statistik", "sensor_snapshots", "mqtt_energy_snapshots", "mqtt_live_snapshots")


async def ha_info(db) -> dict:
    """Betriebsart und HA-Lage: Add-on (Supervisor), Remote-HA oder ohne HA; Version und Zeitzone aus ``/config`` (lesend).
    Nie die URL oder den Token zurückgeben (aus v3 übernommen)."""
    from backend.core import config
    from backend.services.ha_connection import resolve_ha_connection

    api_url, token, kind = await resolve_ha_connection(db)
    info: dict = {"addon": bool(config.HA_INTEGRATION_AVAILABLE), "kind": kind, "erreichbar": False,
                  "version": None, "zeitzone": None}
    if not (api_url and token):
        return info
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{api_url}/config", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            daten = resp.json() or {}
            info.update(erreichbar=True, version=daten.get("version"), zeitzone=daten.get("time_zone"))
    except Exception:  # noqa: BLE001 — nicht erreichbar ⇒ steht so im Kopf
        pass
    return info


def _sitzungen_standard():
    from backend.core.database import get_session

    return get_session


def _db_pfad_standard() -> str:
    from backend.core.config import settings

    return str(settings.database_path)


async def _anlagenname(sitzungen, anlage_id: int) -> str:
    from backend.models.anlage import Anlage

    async with sitzungen() as db:
        name = (await db.execute(select(Anlage.anlagenname).where(Anlage.id == anlage_id))).first()
        await db.rollback()
    if name is None:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")
    return name[0] or ""


def _zeilen(a: AuszugErgebnis, *tabellen: str) -> int:
    return sum(a.tabellen[t].zeilen for t in tabellen if t in a.tabellen)


def _inhalt_zahlen(a: AuszugErgebnis, lage: LageErgebnis) -> dict:
    """Zähler der Inhaltsliste (Bauplan §3.4) — Zeilen, keine Fach-Rechnung."""
    return {
        "geraete": _zeilen(a, "investitionen"),
        "tarife": _zeilen(a, "strompreise"),
        "zuordnungen": lage.zuordnungen_mit_quelle + _zeilen(a, "mqtt_gateway_mappings"),
        "monatswerte": _zeilen(a, "monatsdaten", "investition_monatsdaten"),
        "tageswerte": _zeilen(a, "tages_zusammenfassung"),
        "stundenwerte": _zeilen(a, *_STUNDENWERTE),
        "notizen": a.notizen,
        "protokollzeilen": _zeilen(a, "activity_log", "data_provenance_log") + len(lage.teile.get("log") or []),
        "protokollzeilen_ohne_anlage": a.aktivitaet_ohne_anlage,
        "befunde": lage.befunde,
    }


def _json_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def _schema_teil(a: AuszugErgebnis, lage: LageErgebnis) -> dict:
    return {**a.schema, "json_unbekannt": {k: sorted(v) for k, v in sorted(a.sammler.json_unbekannt.items())},
            "json_unlesbar": dict(sorted(a.sammler.json_unlesbar.items())),
            "einstellungen_unbekannt": sorted(lage.einstellungen_unbekannt)}


def _baue_zip(teil: Path, db_pfad: str, anlage_id: int, lage: LageErgebnis, kopf_inhalt: dict,
              messung: Optional[dict]) -> tuple[AuszugErgebnis, dict]:
    """Im Thread: Auszug → ``lage.json`` → ``inhalt.json`` (zuletzt, ``vollstaendig``)."""
    t0 = time.monotonic()
    with zipfile.ZipFile(teil, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        a = auszug(db_pfad, anlage_id, zf)
        lage_json = {**lage.teile, "schema": _schema_teil(a, lage)}
        zf.writestr("lage.json", _json_bytes(lage_json))
        inhalt = {**kopf_inhalt,
                  "tabellen": {t: {"zeilen": s.zeilen, "status": s.status, "grund": s.grund}
                               for t, s in sorted(a.tabellen.items())},
                  "lage": {**lage.status, "schema": "ok"}, "ohne_anlagenbezug": a.ohne_anlagenbezug,
                  "log_ausgelassen": lage.log_ausgelassen, "vollstaendig": True}
        zf.writestr("inhalt.json", _json_bytes(inhalt))
    if messung is not None:
        messung["auszug"] = int(round((time.monotonic() - t0) * 1000))
        messung["text_bereinigt"] = dict(a.sammler.text_bereinigt)
    return a, inhalt


def _teilfehler(a: AuszugErgebnis, lage: LageErgebnis) -> list[str]:
    return ([t for t, s in sorted(a.tabellen.items()) if s.status != "ok"]
            + [f"lage.{t}" for t, s in lage.status.items() if s != "ok"])


async def bereitstellen(anlage_id: int, *, db_pfad: Optional[str] = None, sitzungen=None, ha_svc=None,
                        profil: str = PROFIL_DIAGNOSE, jetzt: Optional[datetime] = None,
                        uhr: Callable[[], float] = time.monotonic, messung: Optional[dict] = None) -> dict:
    """Paket der Anlage bauen und ablegen; ``LookupError`` bei unbekannter Anlage. Antwort = Paket-Felder (Bauplan §3.4).

    Nähte: ``db_pfad`` (Standard ``settings.database_path``), ``sitzungen`` (Standard ``get_session``), ``ha_svc``, ``jetzt``,
    ``uhr``, ``messung`` (Dauer je Teil in ms, für ``paket_aus_kopie.py``)."""
    from backend.core.config import APP_VERSION

    if profil != PROFIL_DIAGNOSE:
        raise ValueError(f"Profil {profil!r} gibt es nicht")
    sitzungen = sitzungen or _sitzungen_standard()
    db_pfad = str(db_pfad or _db_pfad_standard())
    jetzt = jetzt or datetime.now()
    name = await _anlagenname(sitzungen, anlage_id)
    async with ablage.sperre(anlage_id):
        lage = await baue_lage(anlage_id, sitzungen=sitzungen, jetzt=jetzt, ha_svc=ha_svc, uhr=uhr, messung=messung)
        verz = ablage.bereit(db_pfad)
        teil = ablage.neue_teil_datei(verz, anlage_id)
        kopf_inhalt = {"format": "eedc-diagnose", "version": 4, "profil": profil, "eedc_version": APP_VERSION,
                       "erzeugt_am": jetzt.astimezone().isoformat(timespec="seconds"), "anlage_id": anlage_id}
        try:
            a, _ = await asyncio.to_thread(_baue_zip, teil, db_pfad, anlage_id, lage, kopf_inhalt, messung)
            ziel = teil.with_suffix("")
            os.replace(teil, ziel)
        except BaseException:
            teil.unlink(missing_ok=True)
            raise
        slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:40] or str(anlage_id)
        dateiname = f"eedc_diagnose_{slug}_{jetzt.strftime('%Y-%m-%d')}.zip"
        groesse = ziel.stat().st_size
        felder = {"dateiname": dateiname, "bytes": groesse, "megabyte": groesse / 1_000_000,
                  "gueltig_s": ablage.GUELTIG_S,
                  "versandweg": "email" if groesse <= MAIL_GRENZE_BYTES else "freigabe_link",
                  "inhalt": _inhalt_zahlen(a, lage), "teilfehler": _teilfehler(a, lage)}
        e = ablage.ersetze(anlage_id, ziel, dateiname, felder)
    return {"marke": e.marke, **felder}
