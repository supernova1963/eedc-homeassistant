"""«Regel 2» an der verworfenen Zeit (Sensorwechsel, Korrekturrunde U3-K3, Bauplan Nr. 163): beginnt die Statistik des richtigen
Sensors in Home Assistant erst während der verworfenen Zeit — HA führt **davor keine Zeile** —, zählt ihre erste Zeile ab HAs
Nullpunkt, wie HA sie zählt (HAs eigene Summe; keine Schätzung — dieselbe Regel wie Ansatz «beide», ``zaehler_naht.nullpunkt_neu``):

* **Kanal:** der Versatz der richtigen Quelle setzt am Nullpunkt an (``kanal/korrektur._versatz`` mit ``ha_beginnt_bei``).
* **Wann:** HA führt den richtigen Sensor vor seiner ersten Zeile ``h0`` nicht (``kanal/korrektur.ha_beginnt_bei``), kein
  Rand-Stand prüft die Höhe (``korrektur._hoehe_pruefung`` ⇒ ``None``), und die erste Zeile beginnt am Nullpunkt — ihre Summe
  liegt unter der Grenze einer Stunde (``nullpunkt_der_reihe``); nur Mengen-Felder.
* **Lücke:** die Lücke endet an dieser ersten Zeile (``korrektur._luecke``); die Lücken-Zeile trägt HAs Nullpunkt dort
  (``nullpunkt_der_reihe``) als ``stand_neu_null`` — das Merkmal «endet am Nullpunkt einer neuen Statistik». Neu gelesen und
  gespeichert werden die Stände ab dem Stand nach dieser Zeile (``korrektur._erster_neuer_stand``). **Nicht gebaut** (Halt
  H-3 im Bericht U3-K3): der Rand-Stand am Nullpunkt in der Reihe — er verschöbe den Teilwert der Rand-Tage (``rand_1000``:
  Tagesansicht 7,2 → 7,6) und zeigte nach «verwerfen» mit Vorlauf bis zum Self-Healing 0,0 statt «—».
* **Monat:** die Hülle «Monat je Geltungsabschnitt» setzt Anker 0 an diese Zeile (``abschnitte``, ``zuordnung_wechsel/monat.py``).

Wo HA den richtigen Sensor schon vor der verworfenen Zeit führt (Lage «Geschichte»), gilt nichts davon.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

_STUNDE = timedelta(hours=1)


async def nullpunkt_der_reihe(db, anlage_id: int, ha_svc, eid: str, key: str, h0: datetime) -> Optional[float]:
    """HAs Nullpunkt an der ersten Zeile ``h0`` einer neuen Statistik in der Größe der Reihe — für ein Mengen-Feld 0 (HAs Summe
    beginnt bei 0). ``None`` (keine «Regel 2»), wenn die erste Zeile nicht am Nullpunkt beginnt: ihre Summe liegt über dem, was
    eine Anlage in einer Stunde leisten kann (``zaehlerstand_sprung.grenze_unmoeglich``, dieselbe Grenze wie «Zählerstand
    springt») — eine Statistik, die auf einer Höhe beginnt (importiert, «Summe anpassen», gelöschte Geschichte), zählt eedc dort
    nicht ab 0 —, HA führt dort nichts, oder es ist ein Stand-Feld (Gas, Wasser, Öl: nicht gebaut, benannte Grenze)."""
    from backend.core.berechnungen.zaehlerstand_sprung import grenze_unmoeglich
    from backend.services.snapshot.keys import ist_stand_sensor_key
    from backend.services.snapshot.plausibility import schwelle_der_anlage_stunde_kwh
    from backend.services.zuordnung_wechsel.korrektur import ha_abruf

    if ist_stand_sensor_key(key):
        return None
    summe = await ha_abruf(asyncio.to_thread(ha_svc.get_value_at, eid, h0 + _STUNDE))
    if summe is None or summe > grenze_unmoeglich(await schwelle_der_anlage_stunde_kwh(db, anlage_id)):
        return None
    return 0.0


def abschnitte(wechsel: dict) -> dict[str, tuple[str, datetime]]:
    """Je Schlüssel ``(Entität, G)``: eine nicht aufgehobene Lücken-Zeile mit ``stand_neu_null`` (sie endet am Nullpunkt einer
    neuen Statistik, ``G`` = ihr ``ab_ts``), deren Korrektur-Zeile die heutige Entität aus Home Assistant nennt — für die Hülle
    «Monat je Geltungsabschnitt» (Anker 0 an ``G``)."""
    from backend.services.zuordnung_wechsel.zeitpunkt import gleiche_quelle, ist_luecken_zeile, quelle_aufgeloest

    aus: dict[str, tuple[str, datetime]] = {}
    for key, liste in (wechsel or {}).items():
        heute = quelle_aufgeloest(liste, datetime.max - timedelta(days=1))
        if not (isinstance(heute, dict) and heute.get("art") == "ha" and heute.get("entity_id")):
            continue
        for w in liste:
            if not (ist_luecken_zeile(w) and w.aufgehoben_durch is None and getattr(w, "stand_neu_null", None) is not None):
                continue
            korr = [k for k in liste if k.grund == w.grund and k.aufgehoben_durch is None and not ist_luecken_zeile(k)
                    and k.falsch_seit_ts is not None and k.falsch_seit_ts <= w.falsch_seit_ts and k.ab_ts >= w.ab_ts]
            if any(gleiche_quelle(k.nachher, heute) for k in korr):
                aus[key] = (heute["entity_id"], w.ab_ts)
    return aus


__all__ = ["abschnitte", "nullpunkt_der_reihe"]
