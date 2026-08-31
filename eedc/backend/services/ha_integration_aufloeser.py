"""Zugehörigkeit und Rolle einer HA-Entität — über die Integration, nicht über ihren Namen.

**Warum es diese Datei gibt.** eedc hat SFML und Solcast bis zum 31.08.2026 an
ihren **Entity-IDs** erkannt: eine Liste von Präfixen und eine Liste von
Suffixen, beide abgeschrieben von **einer einzigen Instanz** (Gernots) und
durchgehend deutschsprachig. Wessen Entitäten anders heißen, bekam
stillschweigend keine oder halbe Werte — gemeldet von **Burkard** (GitHub #401,
30.08.2026), dessen sechs SFML-Entities ``sensor.none_*`` heißen und durch
Präfix **und** Suffix fielen; er half sich mit sechs Template-Sensoren, die
seine Werte unter den gesuchten Namen spiegeln.

**Warum die Entity-ID dafür nie taugen konnte.** Sie entsteht in Home Assistant
**beim Anlegen** aus *Bereich · Gerät · Entität* — Zusammensetzung und
**Reihenfolge** wählt der Anwender (Einstellungsdialog „Format der Entitäts-ID
für neue Entitäten"), und mit HA 2026.4 wird der Entitätsname direkt editierbar.
Es gibt **keine Anordnung, gegen die Präfix und Suffix beide robust sind**:
steht etwas davor, bricht der Präfix; steht etwas dahinter, der Suffix. Die ID
ist ein Schnappschuss vom Anlagetag und wandert nie mit.

**Was die Plattform stattdessen anbietet** (Regel 7, eine Ebene über dem Code:
*bevor man eine Erkennung baut, prüft man, ob die Plattform sie anbietet*):

* **Menge** — ``integration_entities('<domain>')`` im Template-Renderer nennt
  **alle** Entitäten einer Integration, auch die präfixlosen. An Gernots
  Instanz gemessen (31.08.2026): 53 für ``solar_forecast_ml``, 24 für
  ``solcast_solar``, inklusive ``sensor.prognose_heute`` und ``sensor.zuhause``.
* **Rolle** — die ``unique_id`` aus der Entity-Registry. Sie wird vom
  Integrationscode vergeben, ist sprachunabhängig und ändert sich nicht, wenn
  jemand die Entität umbenennt. Über Templates ist sie **nicht** erreichbar
  (getestet); dafür gibt es den WebSocket-Befehl
  ``config/entity_registry/list``.

**Die Kaskade — kein Ersatz, ein Vorrang.** Für die **Rolle** drei Stufen, in
dieser Reihenfolge, und sie gelten **je Rolle**, nicht je Lauf:

1. ``unique_id``-Kern (sprachunabhängig, umbenennungsfest)
2. **Anzeigename** (``friendly_name``) gegen deutsche und englische Kerne
3. **altes Entity-ID-Muster** (Suffix) — bleibt als letzter Rückfall stehen

Die **Menge** kommt aus ``integration_entities``; ist sie nicht zu holen (alte
HA-Version, Template-Endpunkt gesperrt, Netzfehler), fällt sie auf die alte
Präfix-Liste zurück. ⛔ **Nichts davon wird gelöscht.** Der Bau darf bei
niemandem etwas verschlechtern, auch nicht bei einer HA-Version, die eine Stufe
nicht liefert — wessen Sensoren heute gefunden werden, merkt nichts.

Aufrufer (drei, absichtlich über **einen** Auflöser):
``services/prognose_discovery.py`` (SFML **und** Solcast) und
``services/solcast_service.py`` (die zweite, eigene Solcast-Erkennung).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Menge und Registry ändern sich quasi nie — eine Integration wird einmal
# eingerichtet. Der TTL hier ist bewusst länger als der Discovery-Cache davor:
# er schützt HA vor einem Registry-Dump je Live-Aufruf, nicht vor Veralten.
_MENGE_TTL = 900.0   # 15 min
_REGISTRY_TTL = 900.0
# ⚠ Ein Fehlschlag wird KURZ gemerkt, nicht gar nicht: ohne negativen Cache
# versuchte jede Live-Abfrage (alle paar Sekunden) einen neuen WebSocket-
# Handshake gegen eine HA, die ihn gerade nicht beantwortet — bei einem
# Netz-Timeout zehn Sekunden lang. Fünf Minuten sind kurz genug, dass eine
# wieder erreichbare HA zeitnah wirkt.
_FEHLSCHLAG_TTL = 300.0

_menge_cache: dict[str, tuple[float, Optional[set[str]]]] = {}
_registry_cache: tuple[float, Optional[dict[str, str]]] = (0.0, None)

_TEMPLATE_TIMEOUT = 10.0
_WS_TIMEOUT = 10.0


@dataclass
class RollenTreffer:
    """Eine Rolle und die Entität, die sie trägt — samt der Stufe, die sie fand."""

    entity_id: str
    rolle: str
    stufe: str  # "unique_id" | "name" | "muster"
    item: dict  # roher Eintrag aus /api/states (State + Attribute)


@dataclass
class AufloesungsErgebnis:
    """Was die Auflösung gefunden hat — und auf welchem Weg."""

    treffer: dict[str, RollenTreffer] = field(default_factory=dict)
    menge_quelle: str = "praefix"  # "integration_entities" | "praefix"
    rolle_quelle: str = "muster"   # "unique_id" | "name" | "muster" (die BESTE benutzte)
    anzahl_entities: int = 0
    fehler: Optional[str] = None


def _normalisiere(text: str) -> str:
    """„Prognose (heute Rest)" → „prognose_heute_rest" — vergleichbar machen.

    Anzeigenamen tragen Klammern, Akzente, Ø und Bindestriche; die Kerne unten
    sind reiner Kleinbuchstaben-Schnodder. Ohne diese Normalisierung müsste
    jeder Kern in jeder Schreibweise dastehen.
    """
    t = (text or "").lower()
    t = t.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    t = re.sub(r"[^a-z0-9]+", "_", t)
    return t.strip("_")


async def integration_entity_ids(domain: str) -> Optional[set[str]]:
    """Alle Entitäten einer Integration — ``None``, wenn HA es nicht liefert.

    Nutzt ``integration_entities()`` über ``POST /api/template`` mit demselben
    Token, den eedc ohnehin benutzt (kein neuer Zugriffsweg). ``None`` heißt
    ausdrücklich **„nicht beantwortbar"**, nicht „leer": der Aufrufer fällt dann
    auf die Präfix-Liste zurück, statt eine leere Menge als Befund zu nehmen.
    """
    now = time.monotonic()
    zwischen = _menge_cache.get(domain)
    if zwischen:
        ttl = _MENGE_TTL if zwischen[1] is not None else _FEHLSCHLAG_TTL
        if (now - zwischen[0]) < ttl:
            return zwischen[1]

    ergebnis: Optional[set[str]] = None
    try:
        from backend.services.ha_state_service import get_ha_state_service

        ha_svc = get_ha_state_service()
        if not ha_svc.is_available:
            return None

        import httpx

        async with httpx.AsyncClient() as client:
            antwort = await client.post(
                f"{ha_svc.api_url}/template",
                headers={"Authorization": f"Bearer {ha_svc.token}"},
                json={"template": "{{ integration_entities('%s') | join('\\n') }}" % domain},
                timeout=_TEMPLATE_TIMEOUT,
            )
        if getattr(antwort, "status_code", None) == 200:
            roh = (antwort.text or "").strip()
            # Eine Integration ohne Entitäten liefert eine leere Zeichenkette.
            # Das ist eine ANTWORT (Menge leer), keine Nicht-Antwort — dann gibt
            # es die Integration hier schlicht nicht.
            ergebnis = {z.strip() for z in roh.splitlines() if z.strip()}
    except Exception as e:  # noqa: BLE001 — Netz/HA-Version/Endpunkt gesperrt
        logger.debug("integration_entities(%s) nicht verfügbar: %s: %s",
                     domain, type(e).__name__, e)
        ergebnis = None

    _menge_cache[domain] = (now, ergebnis)
    return ergebnis


async def entity_registry_unique_ids() -> Optional[dict[str, str]]:
    """``entity_id → unique_id`` aus der Entity-Registry — ``None`` bei Ausfall.

    Nur über WebSocket erreichbar (``config/entity_registry/list``); die
    REST-API kennt die Registry nicht, und Templates kommen nicht an die
    ``unique_id`` heran — beides gemessen am 31.08.2026.

    Die Verbindung wird **nicht gehalten**: anders als der Snapshot-Job
    (``ha_statistics_ws.py``, Abfrage alle fünf Minuten) fragt diese Stelle
    höchstens alle 15 Minuten, und ein gehaltener Socket wäre teurer als der
    Handshake.
    """
    global _registry_cache
    now = time.monotonic()
    if _registry_cache[0]:
        ttl = _REGISTRY_TTL if _registry_cache[1] is not None else _FEHLSCHLAG_TTL
        if (now - _registry_cache[0]) < ttl:
            return _registry_cache[1]

    ergebnis: Optional[dict[str, str]] = None
    ws = None
    try:
        from backend.services.ha_state_service import get_ha_state_service

        ha_svc = get_ha_state_service()
        if not ha_svc.is_available:
            return None

        import websockets

        from backend.services.ha_statistics_ws import HAStatisticsWebsocket

        # Die Adress-Umrechnung steht dort und wird nicht nachgebaut: sie kennt
        # beide Formen (Supervisor `http://supervisor/core/api` und die
        # Remote-URL mit `/api`-Suffix) und ist dort gewächtert.
        ws_url = HAStatisticsWebsocket._ws_adresse(ha_svc.api_url)

        ws = await asyncio.wait_for(
            websockets.connect(ws_url, open_timeout=_WS_TIMEOUT, close_timeout=5,
                               max_size=32 * 1024 * 1024),
            timeout=_WS_TIMEOUT,
        )
        hallo = json.loads(await asyncio.wait_for(ws.recv(), timeout=_WS_TIMEOUT))
        if hallo.get("type") != "auth_required":
            raise RuntimeError(f"unerwartete Begrüßung: {hallo.get('type')}")
        await ws.send(json.dumps({"type": "auth", "access_token": ha_svc.token}))
        quittung = json.loads(await asyncio.wait_for(ws.recv(), timeout=_WS_TIMEOUT))
        if quittung.get("type") != "auth_ok":
            raise RuntimeError("Token abgelehnt")

        await ws.send(json.dumps({"id": 1, "type": "config/entity_registry/list"}))
        while True:
            nachricht = json.loads(await asyncio.wait_for(ws.recv(), timeout=_WS_TIMEOUT))
            if nachricht.get("id") != 1:
                continue
            if not nachricht.get("success"):
                raise RuntimeError(
                    (nachricht.get("error") or {}).get("message", "abgelehnt")
                )
            ergebnis = {
                e["entity_id"]: e.get("unique_id") or ""
                for e in (nachricht.get("result") or [])
                if e.get("entity_id")
            }
            break
    except Exception as e:  # noqa: BLE001 — Netz/Token/HA-Version
        logger.debug("Entity-Registry nicht lesbar: %s: %s", type(e).__name__, e)
        ergebnis = None
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 — beim Aufräumen ist jeder Fehler egal
                pass

    _registry_cache = (now, ergebnis)
    return ergebnis


def invalidate_cache() -> None:
    """Menge und Registry vergessen — für Tests und nach einem Quellenwechsel."""
    global _registry_cache
    _menge_cache.clear()
    _registry_cache = (0.0, None)


async def loese_integration_auf(
    *,
    domain: str,
    praefixe: list[str],
    unique_kerne: dict[str, str],
    namens_kerne: dict[str, str],
    muster: list[tuple[str, str]],
    states: list[dict],
) -> AufloesungsErgebnis:
    """Ordnet die Entitäten einer Integration ihren Rollen zu — vierstufig.

    Args:
        domain: HA-Integrationsdomäne, z. B. ``solar_forecast_ml``.
        praefixe: die alte Entity-ID-Präfix-Liste — Rückfall für die **Menge**.
        unique_kerne: ``unique_id``-Kern → Rolle (Stufe 1).
        namens_kerne: normalisierter Namenskern → Rolle (Stufe 2).
        muster: ``(entity_id-Suffix, Rolle)`` in Prioritätsreihenfolge (Stufe 3).
        states: die rohe ``/api/states``-Antwort — der Aufrufer holt sie ohnehin.

    Die Stufen gelten **je Rolle**, nicht je Lauf: eine Rolle, die Stufe 1 nicht
    findet, darf Stufe 2 oder 3 finden. Eine Rolle, die Stufe 1 gefunden hat,
    wird von den späteren Stufen nicht mehr überschrieben.
    """
    menge = await integration_entity_ids(domain)
    if menge is not None:
        gehoert_dazu = menge.__contains__
        menge_quelle = "integration_entities"
    else:
        def gehoert_dazu(eid: str) -> bool:
            return any(eid.startswith(p) for p in praefixe)
        menge_quelle = "praefix"

    eigene = [it for it in states if gehoert_dazu(it.get("entity_id", ""))]

    treffer: dict[str, RollenTreffer] = {}

    # ── Stufe 1: unique_id ───────────────────────────────────────────────────
    # Der Kern ist die Rollen-Kennung, NICHT der Config-Entry-Präfix davor: SFML
    # schreibt `<entry-id>_ml_expected_daily_production`, Solcast schreibt
    # `total_kwh_forecast_today` ganz ohne Präfix (beides am 31.08. gemessen).
    # `endswith` deckt beide Formen ab; längster Kern zuerst, damit ein kurzer
    # keinen langen wegschnappt.
    registry = await entity_registry_unique_ids() if unique_kerne else None
    if registry:
        kerne_sortiert = sorted(unique_kerne.items(), key=lambda kv: -len(kv[0]))
        for item in eigene:
            eid = item.get("entity_id", "")
            uid = (registry.get(eid) or "").lower()
            if not uid:
                continue
            for kern, rolle in kerne_sortiert:
                if uid.endswith(kern) and rolle not in treffer:
                    treffer[rolle] = RollenTreffer(eid, rolle, "unique_id", item)
                    break

    # ── Stufe 2: Anzeigename ─────────────────────────────────────────────────
    # Deutsche UND englische Kerne, gegen den normalisierten `friendly_name`.
    # Sie greift dort, wo die Registry nicht lesbar ist (alte HA-Version, WS
    # gesperrt), die Integration ihre Namen aber unverändert vergibt.
    if namens_kerne:
        namen_sortiert = sorted(namens_kerne.items(), key=lambda kv: -len(kv[0]))
        for item in eigene:
            name = _normalisiere(
                ((item.get("attributes") or {}).get("friendly_name")) or ""
            )
            if not name:
                continue
            for kern, rolle in namen_sortiert:
                # Nur Gleichheit oder ein VORANGESTELLTER Zusatz („Solar
                # Forecast ML Prognose heute"). Ein NACHgestellter Zusatz wird
                # bewusst nicht akzeptiert: „Prognose heute Rest" würde sonst
                # auf den Kern „prognose_heute" fallen und die falsche Rolle
                # besetzen — genau die Verwechslung, die die Suffix-Liste im
                # alten Verfahren nur über ihre Sortierung vermied.
                if name == kern or name.endswith("_" + kern):
                    # Erster passender Kern gewinnt — eine Entität trägt EINE
                    # Rolle. Ist sie schon besetzt (Stufe 1 war schneller),
                    # bleibt diese Entität ohne Rolle, statt in die nächste
                    # zu rutschen.
                    if rolle not in treffer:
                        treffer[rolle] = RollenTreffer(
                            item.get("entity_id", ""), rolle, "name", item
                        )
                    break

    # ── Stufe 3: das alte Entity-ID-Muster ───────────────────────────────────
    # ⛔ Bleibt ausdrücklich stehen. Wer heute gefunden wird, wird auch morgen
    # gefunden — auch wenn Stufe 1 und 2 auf seiner HA-Version nicht antworten.
    for item in eigene:
        eid_lower = item.get("entity_id", "").lower()
        for suffix, rolle in muster:
            if eid_lower.endswith(suffix):
                # Wie bisher: nur das ERSTE passende Muster je Entität. Die
                # Liste ist danach sortiert (`prognose_heute_rest` vor
                # `prognose_heute`); eine Entität in eine spätere Rolle
                # rutschen zu lassen, wäre eine neue Zuordnung, kein Rückfall.
                if rolle not in treffer:
                    treffer[rolle] = RollenTreffer(
                        item.get("entity_id", ""), rolle, "muster", item
                    )
                break

    stufen = {t.stufe for t in treffer.values()}
    beste = ("unique_id" if "unique_id" in stufen
             else "name" if "name" in stufen else "muster")

    return AufloesungsErgebnis(
        treffer=treffer,
        menge_quelle=menge_quelle,
        rolle_quelle=beste,
        anzahl_entities=len(eigene),
    )
