"""Live-Wetter: der ERFOLGSPFAD wird gefahren — nicht nur seine Abbruchzweige.

⛔ **Der Fehler, gegen den diese Datei steht** (gefunden am 06.09.2026 beim
Release-Smoketest an Gernots Instanz, im Add-on-Log):

    NameError: name 'ind_profil_data' is not defined

`live_wetter.py` las die Variable im **Antwort-Dict des Erfolgspfads**, während
sie mit #395 (`365087e4`, ausgeliefert in **v4.0.40**) nach
`verbrauchsprognose_heute.waehle_verbrauchsprofil` gewandert war. Wirkung: Sobald
der Wetterabruf gelang, starb die Route — bei **jedem** Anwender, unabhängig vom
Verbrauchsprofil (`ind_profil_data` steht in der Bedingung und wird ausgewertet,
bevor `and ist_ind` greift). *Cockpit → Live* hatte damit kein Wetter, keine
Solar-Aussicht und keine Verbrauchsprognose.

⭐ **Warum drei bestehende Proben es nicht fingen — das ist der eigentliche
Befund.** `test_live_wetter_grund.py` fährt ausschließlich Abbruchzweige (keine
Koordinaten · Negativ-Cache · Cache falscher Arität). Keine erreichte je die
Stelle, an der das Antwort-Dict gebaut wird. Und schärfer noch: eine von ihnen
prüft `grund == "abruf_fehlgeschlagen"` — **genau den Rückgabewert, den der
NameError erzeugt**. Der `except Exception` der Route macht aus einem
Programmierfehler eine Netzwerk-Diagnose; eine Probe, die auf diesen Wert
prüft, bleibt grün, weil der Defekt ihr Ergebnis nachbaut.

⛔ **Und die Demo-Box kann es strukturell nicht zeigen:** Der Demo-Zweig hat
seinen eigenen `return` (`live_wetter.py`, „profil_quelle": "demo") und läuft an
der Stelle vorbei. Park-Leertest und chart-audit waren völlig zu Recht grün.

**Dritte Runde derselben Klasse** — nach N-396/#408 (Wrapper-Signatur) und N-344:
*ein Aufrufer, den keine Probe fährt, ist kein Aufrufer, sondern eine Vermutung.*

Deshalb prüft diese Datei genau eine Sache, die keine andere prüft: **die Route
liefert `verfuegbar=True`**, also das vollständig gebaute Antwort-Dict.
"""
from __future__ import annotations

import pytest

from backend.api.routes import live_wetter
from backend.api.routes.live_wetter import get_live_wetter
from backend.models import Anlage

pytestmark = pytest.mark.asyncio


def _wetter_daten() -> dict:
    """Eine plausible Open-Meteo-Antwort — 24 Stunden, alle gelesenen Reihen."""
    times = [f"2026-09-06T{h:02d}:00" for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [15.0] * n,
            "weather_code": [1] * n,
            "cloud_cover": [30] * n,
            "precipitation": [0.0] * n,
            "shortwave_radiation": [0.0] * 6 + [300.0] * 12 + [0.0] * 6,
            "sunshine_duration": [0.0] * 6 + [3000.0] * 12 + [0.0] * 6,
            "global_tilted_irradiance": [0.0] * 6 + [400.0] * 12 + [0.0] * 6,
        },
        "daily": {
            "temperature_2m_min": ["11.0"],
            "temperature_2m_max": ["19.0"],
            "sunrise": ["2026-09-06T06:32"],
            "sunset": ["2026-09-06T19:58"],
        },
    }


async def _anlage(db) -> Anlage:
    anlage = Anlage(
        anlagenname="Erfolgspfad", leistung_kwp=10.0,
        latitude=53.87, longitude=10.68,  # Lübeck — rapahls Standort
    )
    db.add(anlage)
    await db.flush()
    return anlage


async def test_route_liefert_das_antwort_dict_und_stirbt_nicht(db, monkeypatch, caplog):
    """Der Erfolgspfad läuft durch — die Probe, die v4.0.40 gefehlt hat.

    ⚑ Der Cache-Treffer ist der billigste Einstieg in den Erfolgszweig: ein
    gültiges 3er-Tupel überspringt die ganze Fetch-Kette, ohne den Rest der
    Route zu verändern.
    """
    anlage = await _anlage(db)
    monkeypatch.setattr(
        live_wetter, "_cache_get", lambda *a, **k: (_wetter_daten(), None, True),
    )

    res = await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)

    assert res["verfuegbar"] is True, (
        "Die Route ist im Erfolgspfad gestorben. Ihr `except Exception` macht "
        "daraus `grund='abruf_fehlgeschlagen'` und zeigt damit auf den "
        "Wetterdienst — genau so blieb der NameError aus v4.0.40 drei Tage "
        f"unsichtbar. Gelieferter Grund: {res.get('grund')!r}"
    )
    assert res.get("stunden"), "Erfolgspfad ohne Stundenreihe ist keiner."


async def test_profil_quelle_steht_im_antwort_dict(db, monkeypatch):
    """Der Schlüssel selbst — die Stelle, an der die Variable fehlte.

    ⛔ **Gegenprobe-Charakter:** Ohne Verbrauchsprofil ist `ist_ind` False und
    der Wert deshalb `None`. Geprüft wird, dass der **Schlüssel existiert** —
    er entsteht nur, wenn das Dict überhaupt fertig gebaut wurde.
    """
    anlage = await _anlage(db)
    monkeypatch.setattr(
        live_wetter, "_cache_get", lambda *a, **k: (_wetter_daten(), None, True),
    )

    res = await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)

    assert "profil_quelle" in res
    assert "profil_typ" in res


async def test_kein_nameerror_im_log(db, monkeypatch, caplog):
    """Die Log-Zeile aus dem Smoketest darf nicht wiederkommen.

    Sie ist der Beleg, mit dem der Fehler gefunden wurde — und ein
    `except Exception`, der Programmierfehler schluckt, macht sie zur einzigen
    Spur. Solange er so bleibt, prüft diese Probe das Log mit.
    """
    anlage = await _anlage(db)
    monkeypatch.setattr(
        live_wetter, "_cache_get", lambda *a, **k: (_wetter_daten(), None, True),
    )

    with caplog.at_level("WARNING", logger="backend.api.routes.live_wetter"):
        await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)

    assert not any("NameError" in r.message for r in caplog.records), (
        f"NameError im Erfolgspfad: {[r.message for r in caplog.records]}"
    )
