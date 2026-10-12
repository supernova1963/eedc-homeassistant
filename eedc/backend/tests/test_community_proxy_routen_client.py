"""Jeder Community-Pfad, den der Client anfragt, hat eine Proxy-Route (N-743, 12.10.2026).

Anlass: «JAZ nach Bauart» (v4.0.41, 06.09.2026) rief
``/community/components/waermepumpe/by-art`` — der Proxy in
``api/routes/community.py`` hatte die Route nie. Die Anfrage landete im
SPA-Catchall (``main.py``), kam als ``index.html`` mit 200 zurück,
``response.json()`` warf, ``CommunityKomponentenTeile`` schluckte den Fehler,
und der Block fehlte stumm — in der Demo und im Komponententest (Daten direkt
eingespeist) war er sichtbar. ``routen_baseline.txt`` wacht nur über die
Routen, die es gibt, nicht über die, die der Client erwartet.

Diese Datei hält beide Seiten gegeneinander: alle ``'/community/…'``-Pfade in
``frontend/src/api/community.ts`` (Pfadparameter ``${…}`` ⇒ ``{x}``) gegen alle
Routen des Proxy-Routers (``{name}`` ⇒ ``{x}``). Am HEAD ``ff9c4b9e`` fehlte
genau ``by-art``. Die HTTP-Methode gleicht die Probe bewusst nicht ab (Auftrag:
Pfade); eine falsche Methode antwortet 405, nicht stumm mit HTML.

Schwesterdateien: ``test_community_autarkie_speicher_294.py``, ``test_routen_baseline.py`` (Proxy-Routen und ihre Baseline).
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from backend.api.routes import community as community_routes

CLIENT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "community.ts"


def _client_pfade() -> set[str]:
    text = CLIENT.read_text(encoding="utf-8")
    roh = re.findall(r"'(/community/[^'?]*)", text) + re.findall(r"`(/community/[^`?]*)", text)
    return {re.sub(r"\$\{[^}]*\}", "{x}", p) for p in roh}


def _proxy_pfade() -> set[str]:
    return {re.sub(r"\{[^}]*\}", "{x}", r.path) for r in community_routes.router.routes}


def test_jeder_client_pfad_hat_eine_proxy_route():
    client = _client_pfade()
    # Eine Probe, deren Regex nichts mehr findet, waere still gruen: am HEAD
    # stehen 19 verschiedene Pfade im Client.
    assert len(client) >= 15, f"Client-Pfade nicht gefunden ({len(client)}) — Regex oder Datei veraendert?"
    fehlend = sorted(client - _proxy_pfade())
    assert fehlend == [], f"Client fragt Pfade an, die der Proxy nicht kennt: {fehlend}"


async def test_by_art_reicht_die_server_antwort_durch(monkeypatch):
    angefragt: list[str] = []
    antwort_json = {"arten": [{"wp_art": "luft_wasser", "label": "Luft-Wasser", "anzahl": 34, "durchschnitt_jaz": 3.94}]}

    def antwort(request: httpx.Request) -> httpx.Response:
        angefragt.append(request.url.path)
        return httpx.Response(200, json=antwort_json)

    echter_client = community_routes.community_client
    monkeypatch.setattr(
        community_routes, "community_client",
        lambda timeout, **kw: echter_client(timeout, transport=httpx.MockTransport(antwort), **kw),
    )

    ergebnis = await community_routes.get_waermepumpe_by_art()

    assert angefragt == ["/api/components/waermepumpe/by-art"]
    assert ergebnis == antwort_json
