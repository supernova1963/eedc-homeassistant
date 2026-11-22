"""Erste und letzte Stundenzeile einer HA-Statistik — die Ränder eines Sensorwechsels (Sensorwechsel U2 a2, Rechenweg F2,
Bauplan Nr. 143 Entscheid (3)).

**SQL** (Recorder-Datei oder externer Recorder): je eine Abfrage über den Index ``(metadata_id, start_ts)`` (Lab M2: < 1 ms).
**WebSocket** (``recorder/statistics_during_period``): HA kennt keinen Befehl «erste Zeile» und keinen «letzte Zeile ≤ t» —
gestuft **month → day → hour** (Lab M2: 3 Aufrufe, ≈ 75 Zeilen statt der ganzen Geschichte). Nie «alles bis t».

``letzte_zeile_bis`` ist der Rückfall von ``HAStatisticsService.get_stundenzeile_bis``, wenn dessen 24-h-Fenster leer ist (dort
der billigste Weg, Lab M2 3–6 ms); ``erste_zeile`` sucht den Beginn einer Statistik (``T1``, die erste Stunde des neuen
Sensors). Beide liefern die Zeile roh wie ``get_stundenzeile_bis`` (``start_ts``, ``state``, ``sum``, ``mean``, ``min``,
``max``) oder ``None`` (HA kennt den Sensor nicht oder führt bis dahin keine Zeile). Ein Transport-Fehler geht an den Aufrufer.
``ws_anker`` ist der WebSocket-Anker der zwei HA-Leser (Fenster-Leiter, danach gestuft; Korrekturrunde WEGB-K).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

_SPALTEN = ("state", "sum", "mean", "min", "max")
#: Untergrenze der gestuften WebSocket-Suche (wie ``HAStatisticsService._ws_zeitraum``: unterhalb jeder HA-Installation).
_ANFANG = datetime(2015, 1, 1)
_TAG = 86400


def _roh(z: dict) -> dict:
    return {"start_ts": float(z["start_ts"]), **{s: z.get(s) for s in _SPALTEN}}


def _stufe(ws, sid: str, von: datetime, bis: datetime, period: str) -> list[float]:
    """Die ``start_ts`` der Zeilen einer Stufe (aufsteigend); ``bis`` inklusiv wie die SQL-Wege."""
    roh = ws.statistiken([sid], von, bis, period, ["sum", "state"])
    return sorted(float(z["start_ts"]) for z in roh.get(sid, []))


def _ws_erste(svc, sid: str, bis_ts: float) -> Optional[dict]:
    ws = svc._ws
    if ws is None:
        return None
    bis = datetime.fromtimestamp(bis_ts) + timedelta(hours=1)
    monate = _stufe(ws, sid, _ANFANG, bis, "month")
    if not monate:
        return None
    m0 = datetime.fromtimestamp(monate[0])
    tage = _stufe(ws, sid, m0, min(bis, (m0 + timedelta(days=32)).replace(day=1)), "day") or [monate[0]]
    t0 = datetime.fromtimestamp(tage[0])
    zeilen = [z for z in svc._ws_zeilen([sid], t0.timestamp(), (t0 + timedelta(days=1)).timestamp(),
                                        types=list(_SPALTEN)).get(sid, []) if z["start_ts"] <= bis_ts]
    return _roh(min(zeilen, key=lambda z: z["start_ts"])) if zeilen else None


def _ws_letzte(svc, sid: str, ts: float) -> Optional[dict]:
    ws = svc._ws
    if ws is None:
        return None
    t = datetime.fromtimestamp(ts)
    monate = [m for m in _stufe(ws, sid, _ANFANG, t + timedelta(hours=1), "month") if m <= ts]
    for m in reversed(monate[-2:]):                    # der Monat von t kann nur Zeilen nach t tragen
        m0 = datetime.fromtimestamp(m)
        tage = [d for d in _stufe(ws, sid, m0, t + timedelta(hours=1), "day") if d <= ts] or [m]
        for d in reversed(tage[-2:]):                  # ebenso der Tag von t
            zeilen = [z for z in svc._ws_zeilen([sid], d, min(ts, d + _TAG), types=list(_SPALTEN)).get(sid, [])
                      if z["start_ts"] <= ts]
            if zeilen:
                return _roh(max(zeilen, key=lambda z: z["start_ts"]))
    return None


def erste_zeile(svc, sensor_id: str, bis_ts: float) -> Optional[dict]:
    """Die erste Stundenzeile von ``sensor_id`` mit ``start_ts ≤ bis_ts`` (roh)."""
    if not svc.is_available:
        return None
    with svc._verbindung() as conn:
        meta = svc.get_metadata(conn, sensor_id)
        if not meta:
            return None
        if conn is None:
            return _ws_erste(svc, sensor_id, bis_ts)
        r = conn.execute(text("SELECT start_ts, state, sum, mean, min, max FROM statistics WHERE metadata_id = :mid "
                              "AND start_ts <= :bis ORDER BY start_ts LIMIT 1"), {"mid": meta.id, "bis": bis_ts}).fetchone()
    return None if r is None else {"start_ts": float(r[0]), **dict(zip(_SPALTEN, r[1:]))}


def letzte_zeile_bis(svc, sensor_id: str, ts: float) -> Optional[dict]:
    """WebSocket-Rückfall von ``get_stundenzeile_bis``: die letzte Stundenzeile mit ``start_ts ≤ ts``, gestuft."""
    return _ws_letzte(svc, sensor_id, ts)


def ws_anker(svc, sensor_ids: list[str], ts: float) -> dict[str, tuple[float, float]]:
    """WebSocket-Anker der zwei HA-Leser (``HAStatisticsService._letzter_sum_vor``, ``_anker_vor_fenster``): je Sensor die letzte
    Zeile mit ``sum`` vor ``ts`` als ``(start_ts, sum)`` roh. Zuerst die Fenster-Leiter 1 · 8 · 32 · 128 · 1 024 Tage (ein
    ``statistics_during_period`` je Stufe für alle offenen Sensoren, Abbruch beim ersten Treffer — wie bisher); bleibt ein Sensor
    dort ohne Zeile, gestuft month → day → hour (``_ws_letzte``), **bevor** ein Leser «Beginn der Statistik» annimmt
    (Korrekturrunde WEGB-K, Nachmessung B2: eine Statistik, die über 1 024 Tage ruhte, zählte sonst ihren Stand als Menge). Ein
    Sensor ohne solche Zeile fehlt im Ergebnis (die Statistik beginnt danach). Mehrkosten nur, wo die Leiter leer bleibt."""
    from backend.services.ha_statistics_service import _WS_ANKER_FENSTER_TAGE

    out: dict[str, tuple[float, float]] = {}
    offen = list(sensor_ids)
    for tage in _WS_ANKER_FENSTER_TAGE:
        if not offen:
            break
        zeilen = svc._ws_zeilen(offen, ts - tage * 86400, ts - 1, types=["sum"])
        for sid in list(offen):
            treffer = [z for z in zeilen.get(sid, []) if z.get("sum") is not None and z["start_ts"] < ts]
            if treffer:
                letzte = max(treffer, key=lambda z: z["start_ts"])
                out[sid] = (float(letzte["start_ts"]), letzte["sum"])
                offen.remove(sid)
    for sid in offen:
        z = _ws_letzte(svc, sid, ts - 1)
        if z is not None and z.get("sum") is not None:
            out[sid] = (float(z["start_ts"]), z["sum"])
    return out


__all__ = ["erste_zeile", "letzte_zeile_bis", "ws_anker"]
