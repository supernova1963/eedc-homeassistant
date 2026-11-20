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
* **Monat:** die Hülle «Monat je Geltungsabschnitt» setzt Anker 0 an diese Zeile (``abschnitte``, ``zuordnung_wechsel/monat.py``),
  auch wenn später ein Wechsel «bleiben» vom richtigen Sensor weiterführt (U3-K4, K3-B5).
* **«Falsch seit» auf der ersten Zeile** (U3-K4, K3-B4): dieselbe Regel ohne Lücke — die Korrektur-Zeile trägt den Nullpunkt
  als ``stand_neu_null`` (ohne ``ansatz``; die Rand-Stände an «Falsch seit», ``korrektur._rand_an_falsch_seit``, entfallen
  dort: HA führt davor keine Zeile), neu gelesen wird ab dem Stand nach der ersten Zeile.

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
    """Je Schlüssel ``(Entität, G)`` einer neuen Statistik, deren erste Zeile ``G`` ab HAs Nullpunkt zählt — für die Hülle
    «Monat je Geltungsabschnitt» (Anker 0 an ``G``):

    * eine nicht aufgehobene Lücken-Zeile mit ``stand_neu_null`` (sie endet am Nullpunkt, ``G`` = ihr ``ab_ts``) unter einer
      Korrektur-Zeile, die die Entität aus Home Assistant nennt (U3-K3);
    * U3-K4 (K3-B4): eine nicht aufgehobene Korrektur-Zeile ohne ``ansatz`` mit ``stand_neu_null`` — «Falsch seit» liegt auf
      der ersten Zeile, ``G`` = ``falsch_seit_ts``.

    Die Entität ist die heutige — oder, U3-K4 (K3-B5), ein späterer angesetzter Wechsel «bleiben» führt von ihr weiter (die
    Hülle setzt den Nullpunkt dann in ihren Abschnitt, ``monat._mit_nullpunkt``)."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR
    from backend.services.zuordnung_wechsel.zeitpunkt import gleiche_quelle, ist_luecken_zeile, quelle_aufgeloest, rand_versatz

    aus: dict[str, tuple[str, datetime]] = {}
    for key, liste in (wechsel or {}).items():
        heute = quelle_aufgeloest(liste, datetime.max - timedelta(days=1))

        def gilt(q) -> bool:
            if not (isinstance(q, dict) and q.get("art") == "ha" and q.get("entity_id")):
                return False
            return gleiche_quelle(q, heute) or any(rand_versatz(w) is not None and gleiche_quelle(w.vorher, q) for w in liste)

        for w in liste:
            if w.aufgehoben_durch is not None or getattr(w, "stand_neu_null", None) is None:
                continue
            if ist_luecken_zeile(w):
                korr = [k for k in liste if k.grund == w.grund and k.aufgehoben_durch is None and not ist_luecken_zeile(k)
                        and k.falsch_seit_ts is not None and k.falsch_seit_ts <= w.falsch_seit_ts and k.ab_ts >= w.ab_ts]
                q = next((k.nachher for k in reversed(korr) if gilt(k.nachher)), None)
                if q is not None:
                    aus[key] = (q["entity_id"], w.ab_ts)
            elif (w.grund == GRUND_KORREKTUR and getattr(w, "ansatz", None) is None and w.falsch_seit_ts is not None
                  and gilt(w.nachher)):
                aus[key] = (w.nachher["entity_id"], w.falsch_seit_ts)
    return aus


__all__ = ["abschnitte", "nullpunkt_der_reihe"]
