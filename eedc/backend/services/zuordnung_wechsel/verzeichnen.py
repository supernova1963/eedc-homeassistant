"""Verzeichnen jeder wirksamen Änderung der Quelle eines Zählerschlüssels (Auftrag Sitzung 1, Teil C).

Ablauf in jedem Schreibweg (``api/routes/datenquellen.py`` Feld-Route und Energie-Vorschläge, Preset ``mqtt_presets.py``,
Gateway-Zeile anlegen/ändern/löschen ``mqtt_gateway.py``): **vor** der ersten Änderung ``momentaufnahme``, **nach** der letzten
(vor dem Commit des Aufrufers) ``verzeichne`` — eine Zeile je Schlüssel, dessen wirksame Quelle sich geändert hat, mit ``grund``
leer (Sitzung 3b: ``fortsetzung``, wenn der Anwender ihn nennt; eine Korrektur legt der Dienst an) und ``herkunft = wechsel``. Nicht verzeichnet werden: eine Änderung an einem Schlüssel **ohne eigene Werte** (Zählerstände
der Reihe oder Kanalzeilen) — auch A → B und → «Keine» (Bauplan §8 Nr. 17: nichts zu schützen; sonst legte B-0 die Vergangenheit
auf eine verworfene Erstwahl fest), die Materialisierung beim Lesen der Fläche (W7, ``_festschreiben`` — wirksam unverändert), die Stilllegung und das Entfernen
von Innengeräten (W9, Geräte-Ende), das Vorzeichen (``/invert`` — keine Quelle). Festlegungen Bauplan §7 Nr. 15.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.models.zuordnung_wechsel import HERKUNFT_WECHSEL, ZuordnungWechsel
from backend.services.zuordnung_wechsel.quelle import aenderungen, lade_wirksame_quellen
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus, merke_neu


async def momentaufnahme(db, anlage) -> dict[str, dict]:
    """Die wirksamen Quellen der Anlage **vor** einer Änderung (Gateway-Zeilen aus dieser Sitzung)."""
    return await lade_wirksame_quellen(db, anlage)


async def verzeichne(db, anlage, vorher: dict[str, dict], *, jetzt: Optional[datetime] = None,
                     gruende: Optional[dict[str, str]] = None, auslassen: Optional[set[str]] = None) -> list[ZuordnungWechsel]:
    """Vergleicht mit dem Stand **nach** der Änderung und legt je geänderten Schlüssel eine Zeile an (``flush``, kein Commit).

    Sitzung 3b: ``gruende`` — Grund je Schlüssel (``fortsetzung``; sonst leer); ``auslassen`` — Schlüssel, deren Zeile der
    Dienst der Korrektur selbst anlegt (``grund = korrektur``, ``abfrage.vollziehe``)."""
    nachher = await lade_wirksame_quellen(db, anlage)
    jetzt = (jetzt or datetime.now()).replace(microsecond=0)
    zeilen: list[ZuordnungWechsel] = []
    for a in await aenderungen(db, anlage, vorher, nachher):
        if not a.eigene_werte or a.sensor_key in (auslassen or ()):
            continue   # §8 Nr. 17
        row = ZuordnungWechsel(
            anlage_id=anlage.id, sensor_key=a.sensor_key, erklaert_ts=jetzt, ab_ts=ab_ts_aus(jetzt),
            vorher=a.vorher, nachher=a.nachher, grund=(gruende or {}).get(a.sensor_key), herkunft=HERKUNFT_WECHSEL,
        )
        db.add(row)
        zeilen.append(row)
    if zeilen:
        await db.flush()
        for row in zeilen:
            merke_neu(db, row)
    return zeilen
