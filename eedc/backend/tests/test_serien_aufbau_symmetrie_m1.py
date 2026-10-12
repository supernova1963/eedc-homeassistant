"""Symmetrie-Test M1 (Issue #318): Serien-Selektion des Tagesverlaufs.

Backfill-Pfad (`energie_profil.backfill`) und Live-Chart-Pfad
(`live_tagesverlauf_service`) bauten dieselbe Investitions-Serien-Selektion
zweimal parallel — ohne Symmetrie-Test (S1 umging die Achse). Drift: der
Pool-Dedup (#227, gleiche `leistung_w`-Entity → Wallbox vor E-Auto) lief NUR
im Live-Pfad. Da `aggregate_day` seine `punkte` für den Scheduler aus dem
Live-Pfad und für den Backfill aus dem Backfill-Pfad zieht, konnte derselbe
Tag je Trigger unterschiedliche TEP.komponenten/Peaks erzeugen — gleiche
Aggregator-Asymmetrie-Klasse wie #290/#298.

Fix: gemeinsame Quelle `baue_investitions_serien` (inkl. Pool-Dedup). Diese
Tests pinnen ihr Verhalten + zementieren, dass beide Pfade sie nutzen.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.services.live_sensor_config import baue_investitions_serien


def _inv(inv_id, typ, parameter=None, parent_investition_id=None, bezeichnung="X"):
    return SimpleNamespace(
        id=inv_id, typ=typ, parameter=parameter or {},
        parent_investition_id=parent_investition_id, bezeichnung=bezeichnung,
    )


# ─── Kern-Selektion ─────────────────────────────────────────────────────────

def test_einfache_pv_serie():
    serien, entities = baue_investitions_serien(
        {"3": {"leistung_w": "sensor.pv"}}, {"3": _inv("3", "pv-module")}
    )
    assert [s.key for s in serien] == ["pv_3"]
    assert serien[0].kategorie == "pv"
    assert serien[0].seite == "quelle"
    assert entities == {"pv_3": ["sensor.pv"]}


def test_skip_typ_wechselrichter():
    serien, _ = baue_investitions_serien(
        {"9": {"leistung_w": "sensor.wr"}}, {"9": _inv("9", "wechselrichter")}
    )
    assert serien == []


def test_wp_split_zwei_serien():
    inv = _inv("7", "waermepumpe")
    serien, entities = baue_investitions_serien(
        {"7": {"leistung_heizen_w": "sensor.h", "leistung_warmwasser_w": "sensor.w"}},
        {"7": inv},
    )
    keys = [s.key for s in serien]
    assert keys == ["waermepumpe_7_heizen", "waermepumpe_7_warmwasser"]
    assert {s.suffix for s in serien} == {"heizen", "warmwasser"}
    assert entities["waermepumpe_7_heizen"] == ["sensor.h"]


def test_eauto_parent_skip():
    serien, _ = baue_investitions_serien(
        {"1": {"leistung_w": "sensor.ea"}},
        {"1": _inv("1", "e-auto", parent_investition_id=2)},
    )
    assert serien == []


def test_sonstiges_erzeuger_seite_quelle():
    serien, _ = baue_investitions_serien(
        {"5": {"leistung_w": "sensor.x"}},
        {"5": _inv("5", "sonstiges", parameter={"kategorie": "erzeuger"})},
    )
    assert serien[0].seite == "quelle"


def test_sonstiges_speicher_bidirektional():
    serien, _ = baue_investitions_serien(
        {"5": {"leistung_w": "sensor.x"}},
        {"5": _inv("5", "sonstiges", parameter={"kategorie": "speicher"})},
    )
    assert serien[0].bidirektional is True


# ─── Pool-Dedup (#227) — der M1-Drift, der im Backfill fehlte ────────────────

def test_pool_dedup_wallbox_vor_eauto():
    """Wallbox + E-Auto teilen dieselbe leistung_w-Entity (kein parent-Link):
    nur die Wallbox-Serie überlebt — in BEIDEN Pfaden (jetzt geteilte Quelle)."""
    inv_live = {
        "1": {"leistung_w": "sensor.shared"},  # E-Auto
        "2": {"leistung_w": "sensor.shared"},  # Wallbox
    }
    investitionen = {
        "1": _inv("1", "e-auto"),
        "2": _inv("2", "wallbox"),
    }
    serien, entities = baue_investitions_serien(inv_live, investitionen)
    keys = [s.key for s in serien]
    assert keys == ["wallbox_2"]  # E-Auto dedupliziert
    assert "eauto_1" not in entities
    assert entities["wallbox_2"] == ["sensor.shared"]


def test_wallbox_verdraengt_eauto_auch_bei_getrennten_entities():
    """Getrennte Entities → die Wallbox ist trotzdem die einzige Quelle (#356).

    Bis 2026-08-08 forderte dieser Test hier **beide** Serien („keine Dedup bei
    getrennten Entities") — er beschrieb das Verhalten, nicht eine fachliche
    Absicht. Der Entity-Dedup (#227) greift nur bei geteiltem Sensor, ein
    Fahrzeug mit eigenem Ladeleistungs-Sensor lief deshalb doppelt ins
    `komponenten`-JSON: Anlage 1, 2026-08-06, Zähler 12,00 kWh → `wallbox_2`
    −12,00 **und** `eauto_1` −17,32, beide Sensoren mit Ladung in genau
    denselben fünf Stunden.

    Die Regel ist dieselbe wie auf der Monatsebene
    (`get_emob_heimladung_canonical`): Wallbox vorhanden ⇒ Wallbox ist Quelle.
    """
    inv_live = {
        "1": {"leistung_w": "sensor.ea"},
        "2": {"leistung_w": "sensor.wb"},
    }
    investitionen = {"1": _inv("1", "e-auto"), "2": _inv("2", "wallbox")}
    serien, entities = baue_investitions_serien(inv_live, investitionen)
    assert {s.key for s in serien} == {"wallbox_2"}
    assert "eauto_1" not in entities


def test_eauto_ohne_wallbox_behaelt_seine_serie():
    """Abgrenzung: ohne Wallbox ist das Fahrzeug die Quelle — Steckerlader/
    Schuko, derselbe Zweig wie `get_emob_heimladung_canonical` ohne Heimladung.
    Griffe die Regel auch hier, verlöre diese Anlage ihre Ladung komplett."""
    inv_live = {"1": {"leistung_w": "sensor.ea"}}
    investitionen = {"1": _inv("1", "e-auto")}
    serien, entities = baue_investitions_serien(inv_live, investitionen)
    assert {s.key for s in serien} == {"eauto_1"}
    assert entities["eauto_1"] == ["sensor.ea"]


# ─── Struktureller Wächter: beide Pfade nutzen die geteilte Quelle ──────────

# Der LTS-Serien-Aufbau saß bis 2026-08-01 in `backfill.py`; er liegt jetzt in
# `lts_tagesverlauf.py`, weil auch die Reparatur-Werkbank ihn braucht
# (Forum #89667/72). Der Wächter zeigt auf die Stelle, die die Selektion
# tatsächlich baut — sonst prüfte er eine Datei, die nur noch aufruft.
_LTS_TV = Path(__file__).resolve().parents[1] / "services/energie_profil/lts_tagesverlauf.py"
_LIVE_TV = Path(__file__).resolve().parents[1] / "services/live_tagesverlauf_service.py"
_BACKFILL = Path(__file__).resolve().parents[1] / "services/energie_profil/backfill.py"


def test_beide_pfade_nutzen_geteilte_quelle():
    """Wächter gegen Re-Divergenz: beide Pfade rufen baue_investitions_serien
    und reimplementieren die Selektion nicht inline."""
    for pfad in (_LTS_TV, _LIVE_TV):
        src = pfad.read_text(encoding="utf-8")
        assert "baue_investitions_serien(" in src, f"{pfad.name} nutzt die Quelle nicht"


def test_backfill_baut_keine_eigene_selektion():
    """Der Backfill ruft den LTS-Weg — er darf die Selektion nicht zurückholen."""
    src = _BACKFILL.read_text(encoding="utf-8")
    assert "lade_tagesverlauf_aus_lts" in src
    assert "baue_investitions_serien" not in src


def test_kein_paralleler_pool_dedup_mehr():
    """Der alte Live-spezifische Pool-Dedup (`_serie_priority`) darf nicht
    wieder auftauchen — die Dedup lebt jetzt nur in der geteilten Quelle."""
    for pfad in (_LTS_TV, _LIVE_TV, _BACKFILL):
        src = pfad.read_text(encoding="utf-8")
        assert "_serie_priority" not in src, f"{pfad.name} hat wieder eigenen Pool-Dedup"


# ─── Die Serien-Keys überleben den Rückweg (WK-09 B1) ───────────────────────
#
# `baue_investitions_serien` **erzeugt** die Keys, `_key_to_serie_info` **löst
# sie wieder auf** — dazwischen liegen `TagesEnergieProfil.komponenten` und die
# Route `/energie-profil/{id}/stunden`. Erst der Rückweg macht aus dem Split
# eine Anzeige: Ohne den Suffix im Label hieße im Tag-Stundenverlauf jede der
# beiden Flächen gleich, und ohne die Kategorie `waermepumpe` fiele sie in
# `extraSerien` und läge ZUSÄTZLICH zur WP-Fläche im Stapel.
#
# Gemessen am Schreibpfad (12.09.2026): `aggregate_day` legt bei einer WP mit
# `leistung_heizen_w`/`leistung_warmwasser_w` genau diese zwei Keys in
# `TagesEnergieProfil.komponenten` ab (−2,0 / −1,0 kW), und die Route liefert
# daraus „Winterborn WP Heizen"/„… Warmwasser" plus `waermepumpe_kw = 3,0`.

def test_split_keys_loesen_zurueck_auf_label_und_kategorie():
    from backend.api.routes.energie_profil._shared import _key_to_serie_info

    inv = _inv(7, "waermepumpe", bezeichnung="Winterborn WP")
    serien, _ = baue_investitions_serien(
        {"7": {"leistung_heizen_w": "sensor.h", "leistung_warmwasser_w": "sensor.w"}},
        {"7": inv},
    )
    aufgeloest = [_key_to_serie_info(s.key, {7: inv}) for s in serien]
    assert [i and i["label"] for i in aufgeloest] == [
        "Winterborn WP Heizen", "Winterborn WP Warmwasser",
    ]
    # ⛔ Kategorie bleibt `waermepumpe` — sie ist die Adresse des Stapelplatzes.
    assert {i["kategorie"] for i in aufgeloest} == {"waermepumpe"}
    assert {i["seite"] for i in aufgeloest} == {"senke"}


def test_gerät_ohne_split_behaelt_seinen_blanken_namen():
    """Gegenprobe: ohne Suffix kein Zusatz — sonst hieße jede WP „… Heizen"."""
    from backend.api.routes.energie_profil._shared import _key_to_serie_info

    inv = _inv(7, "waermepumpe", bezeichnung="Winterborn WP")
    info = _key_to_serie_info("waermepumpe_7", {7: inv})
    assert info["label"] == "Winterborn WP"
    assert info["kategorie"] == "waermepumpe"


# ─── N-447: „Nicht dargestellt" gilt für BEIDE Pfade und meint dasselbe ─────
#
# Der Satz *„Nicht dargestellt (kein HA-Leistungssensor): «Gerät»"*
# (`components/live/TagesverlaufChart.tsx`) behauptet zwei Dinge: das Gerät ist
# nicht gezeichnet, **und** der Grund ist eine fehlende Leistungsquelle. Bis
# 12.09.2026 prüfte der HA-Pfad nur `leistung_w` (⇒ die gezeichnete Split-WP
# stand darunter) und der MQTT-Pfad schloss jede Wärmepumpe pauschal aus (⇒ eine
# WP ganz ohne Quelle verschwand wortlos). Jetzt beantwortet EINE Funktion die
# Frage; die Pfade liefern nur ihre Eingänge.

def _ha_uebersprungen(inv_live_map, investitionen) -> list[str]:
    from backend.services.live_sensor_config import (
        LEISTUNGS_FELDER, inv_ids_mit_serie, uebersprungene_investitionen,
    )
    serien, _ = baue_investitions_serien(inv_live_map, investitionen)
    return uebersprungene_investitionen(
        investitionen, inv_ids_mit_serie(serien),
        lambda i: any((inv_live_map.get(i) or {}).get(f) for f in LEISTUNGS_FELDER),
    )


def _mqtt_uebersprungen(available_keys, investitionen, mit_serie) -> list[str]:
    from backend.services.live_sensor_config import (
        LEISTUNGS_FELDER, uebersprungene_investitionen,
    )
    return uebersprungene_investitionen(
        investitionen, mit_serie,
        lambda i: any(f"inv:{i}:{f}" in available_keys for f in LEISTUNGS_FELDER),
    )


def test_gezeichnete_split_wp_steht_nicht_unter_nicht_dargestellt():
    """Der Fund selbst: zwei Flächen im Chart und daneben „fehlt"."""
    inv_live = {"7": {"leistung_heizen_w": "sensor.h", "leistung_warmwasser_w": "sensor.w"}}
    investitionen = {"7": _inv("7", "waermepumpe", bezeichnung="Winterborn WP")}
    serien, _ = baue_investitions_serien(inv_live, investitionen)
    assert len(serien) == 2, "Voraussetzung: sie WIRD gezeichnet"
    assert _ha_uebersprungen(inv_live, investitionen) == []


def test_wp_ganz_ohne_leistungsquelle_wird_genannt():
    """Gegenprobe — sonst belegte die Probe darüber nur, dass die Liste leer ist.
    Sie ist zugleich die MQTT-Hälfte des Funds: dort verschwand dieser Fall."""
    investitionen = {"7": _inv("7", "waermepumpe", bezeichnung="Winterborn WP")}
    assert _ha_uebersprungen({"7": {}}, investitionen) == ["Winterborn WP"]
    assert _mqtt_uebersprungen(set(), investitionen, set()) == ["Winterborn WP"]


def test_beide_pfade_antworten_gleich():
    """Dieselbe Anlage, dieselbe Zuordnungslage, zwei Pfade — eine Antwort.
    Genau diese Symmetrie fehlte: HA meldete die Split-WP, MQTT verschwieg sie."""
    investitionen = {
        "7": _inv("7", "waermepumpe", bezeichnung="Winterborn WP"),
        "8": _inv("8", "wallbox", bezeichnung="Wallbox Garage"),
    }
    # Lage: WP getrennt gemessen (⇒ Serie), Wallbox gar nicht zugeordnet.
    ha = _ha_uebersprungen(
        {"7": {"leistung_heizen_w": "sensor.h", "leistung_warmwasser_w": "sensor.w"}},
        investitionen,
    )
    mqtt = _mqtt_uebersprungen(
        {"inv:7:leistung_heizen_w", "inv:7:leistung_warmwasser_w"},
        investitionen, {"7"},
    )
    assert ha == mqtt == ["Wallbox Garage"]


def test_ein_gemessenes_geraet_ohne_eigene_serie_wird_nicht_als_fehlend_gemeldet():
    """Die Abgrenzung, die den Satz wahr hält: `baue_investitions_serien` lässt
    Geräte auch aus **anderen** Gründen weg als „kein Sensor".

    Drei belegte Fälle, alle mit Leistungssensor: das E-Auto an einer Wallbox
    (die es mitmisst, #356), zwei Investitionen an derselben Entity
    (Pool-Dedup #227) und ein Zähler unter *Sonstiges* (#377, hat keine Seite).
    Keiner von ihnen stand bisher in der Liste — und darf es nicht anfangen.
    """
    # (a) E-Auto mit Parent-Wallbox
    inv_live = {"1": {"leistung_w": "sensor.ea"}}
    investitionen = {"1": _inv("1", "e-auto", parent_investition_id=2, bezeichnung="Zoe")}
    serien, _ = baue_investitions_serien(inv_live, investitionen)
    assert serien == [], "Voraussetzung: keine Serie"
    assert _ha_uebersprungen(inv_live, investitionen) == []

    # (b) Pool-Dedup: beide an derselben Entity, nur die Wallbox überlebt
    inv_live = {"1": {"leistung_w": "sensor.shared"}, "2": {"leistung_w": "sensor.shared"}}
    investitionen = {
        "1": _inv("1", "e-auto", bezeichnung="Zoe"),
        "2": _inv("2", "wallbox", bezeichnung="Wallbox"),
    }
    assert _ha_uebersprungen(inv_live, investitionen) == []

    # (c) Zähler unter Sonstiges (#377)
    inv_live = {"5": {"leistung_w": "sensor.wasser"}}
    investitionen = {
        "5": _inv("5", "sonstiges", parameter={"kategorie": "zaehler"},
                  bezeichnung="Wasserzähler"),
    }
    serien, _ = baue_investitions_serien(inv_live, investitionen)
    assert serien == [], "Voraussetzung: ein Zähler bekommt keine Serie"
    assert _ha_uebersprungen(inv_live, investitionen) == []


def test_getrennte_leistungsfelder_zaehlen_als_leistungsquelle():
    """Die **zweite** Klausel für sich, mit einer Serie, die es nicht gibt.

    ⚑ Befund über die Probe (12.09.2026): Ein Sprengsatz, der
    ``LEISTUNGS_FELDER`` auf ``("leistung_w",)`` kürzt, blieb an allen Proben
    darüber **still** — weil jedes Gerät mit einem Split-Feld ohnehin eine Serie
    bekommt und schon an der ersten Klausel hängen bleibt. Die Regel ist damit
    doppelt gesichert, ihre zweite Hälfte aber ungeprüft. Der Fall, in dem sie
    allein trägt, ist der Pool-Dedup (#227): Teilt eine Split-Wärmepumpe ihre
    Entity mit einem anderen Gerät, verliert eine der beiden ihre Serie — und
    hat trotzdem einen Leistungssensor. Hier steht er nachgestellt.
    """
    from backend.services.live_sensor_config import (
        LEISTUNGS_FELDER, uebersprungene_investitionen,
    )

    investitionen = {"7": _inv("7", "waermepumpe", bezeichnung="Winterborn WP")}
    inv_live = {"7": {"leistung_heizen_w": "sensor.h", "leistung_warmwasser_w": "sensor.w"}}
    ohne_serie: set[str] = set()          # der Serien-Bauer hat sie fallen lassen
    assert uebersprungene_investitionen(
        investitionen, ohne_serie,
        lambda i: any((inv_live.get(i) or {}).get(f) for f in LEISTUNGS_FELDER),
    ) == []
    # Gegenprobe: ohne jede Zuordnung wird dieselbe Lage gemeldet.
    assert uebersprungene_investitionen(
        investitionen, ohne_serie,
        lambda i: any(({}).get(f) for f in LEISTUNGS_FELDER),
    ) == ["Winterborn WP"]
    # ⛔ Und die Feldliste selbst ist der Vertrag — sie steht im Anwendersatz
    # („kein HA-Leistungssensor"), nicht nur im Code.
    # ⭐ `leistung_kuehlen_w` kam am 13.09.2026 dazu (N-439): Seit es eine
    # eigene Verlaufs-Reihe erzeugt, muss es hier stehen — sonst meldete der
    # Satz eine Wärmepumpe als „nicht dargestellt", die gezeichnet wird.
    assert set(LEISTUNGS_FELDER) == {
        "leistung_w", "leistung_heizen_w", "leistung_warmwasser_w",
        "leistung_kuehlen_w",
    }


def test_keine_serie_traegt_die_meldung_auch_ohne_die_zweite_klausel():
    """Die **erste** Klausel für sich — das Spiegelbild der Probe darüber.

    ⚑ Befund über die Proben (12.09.2026, Master): Ein Sprengsatz, der
    ``if inv_id in inv_ids_mit_serie: continue`` **entfernt**, blieb an allen
    übrigen Proben still — weil jedes Gerät mit einer Serie per Konstruktion
    auch eine Leistungsquelle hat und die zweite Klausel es mitfängt. Umgekehrt
    blieb der Sprengsatz an ``LEISTUNGS_FELDER`` still, weil die erste Klausel
    ihn deckte. **Beide Hälften decken sich gegenseitig — und waren damit
    einzeln ungeprüft.** Hier steht die erste allein, mit gestellter zweiter.

    ⭐ **Warum die Klausel trotz der Implikation dasteht:** Der Anwendersatz
    behauptet **zwei** Dinge — das Gerät ist nicht gezeichnet **und** ihm fehlt
    ein Leistungssensor. Die Bedingung prüft beide, statt sich auf eine
    Kopplung zu verlassen, die heute gilt und morgen fallen kann: Sobald
    ``baue_investitions_serien`` eine Serie aus einer anderen Quelle bildet
    (oder ein Feld dazukommt, das ``LEISTUNGS_FELDER`` nicht kennt), trägt die
    erste Klausel allein.
    """
    from backend.services.live_sensor_config import uebersprungene_investitionen

    investitionen = {"7": _inv("7", "waermepumpe", bezeichnung="Winterborn WP")}
    # Serie geliefert, aber „hat Leistungsquelle" sagt nein: nicht melden.
    assert uebersprungene_investitionen(investitionen, {"7"}, lambda _i: False) == []
    # Gegenprobe, gleiche Lage ohne Serie — sonst belegte die Zeile nur, dass
    # die Liste leer sein kann.
    assert uebersprungene_investitionen(investitionen, set(), lambda _i: False) == [
        "Winterborn WP",
    ]


def test_kein_pfad_baut_die_bedingung_selbst():
    """Wächter gegen Re-Divergenz: der Live-Pfad ruft die geteilte Bedingung und
    hält keine eigene Liste mehr (der N-447-Drift, den dieses Paket schließt)."""
    src = _LIVE_TV.read_text(encoding="utf-8")
    assert src.count("uebersprungene_investitionen(") == 2, "beide Pfade rufen sie"
    assert 'if typ != "waermepumpe":' not in src, "die pauschale WP-Ausnahme ist zurück"
    assert "uebersprungen.append(" not in src, "ein Pfad sammelt wieder selbst"


async def test_die_route_reicht_uebersprungen_an_den_chart_durch(db, monkeypatch):
    """T1 (Handgriff 12.10.2026): der Anwendersatz «Nicht dargestellt (kein HA-Leistungssensor): …» erreicht den Client.

    Der Dienst lieferte ``uebersprungen`` seit #109 (v3.10.3), die Route baute ihre Antwort aber nur aus ``serien`` und
    ``punkte``, und ``TagesverlaufResponse`` kannte das Feld nicht — FastAPI hätte es auch beim Durchreichen gestrichen.
    Darum über HTTP mit dem echten Router und ``response_model``; gestellt ist nur der Dienst. Gegenprobe: ohne
    Schlüssel im Dienst ist die Liste leer, nicht fehlend (der Demo-Zweig liefert sie ebenfalls nicht).
    """
    import httpx
    from fastapi import FastAPI

    from backend.api.deps import get_db
    from backend.api.routes import live_dashboard
    from backend.tests import factories

    anlage = await factories.anlage(db, anlagenname="T1")
    await db.commit()
    stand = {"tv": {"serien": [], "punkte": [], "uebersprungen": ["Winterborn WP"]}}

    class _Dienst:
        async def get_tagesverlauf(self, anlage, db):  # noqa: ARG002
            return stand["tv"]

    monkeypatch.setattr(live_dashboard, "get_live_power_service", lambda: _Dienst())
    app = FastAPI()
    app.include_router(live_dashboard.router, prefix="/api/live")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        antwort = await client.get(f"/api/live/{anlage.id}/tagesverlauf")
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["uebersprungen"] == ["Winterborn WP"]

        stand["tv"] = {"serien": [], "punkte": []}
        antwort = await client.get(f"/api/live/{anlage.id}/tagesverlauf")
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["uebersprungen"] == []
