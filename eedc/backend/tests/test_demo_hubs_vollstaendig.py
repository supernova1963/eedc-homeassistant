"""Demo-Modus: jeder Hub mit Block «Überblick» ist vollständig gefüllt (Galerie-Auftrag 1.11.2026, Gernot).

Die öffentliche Galerie zeigt die Hubs Wärmepumpe, Wallbox und E-Auto aus ``GET /api/live/{id}?demo=true``
(`live_dashboard._generate_demo_data` + `_demo_auf_anlage`). Was eine Kachel oder Karte zeigt, muss die Demo deshalb
liefern — sonst fehlt es im Bild, ohne dass ein Lauf rot wird. Diese Probe hält je Hub-Typ die Quellen fest, die aus der
**Live-Antwort** kommen:

* Themen-Kacheln und Karte «Themen» — feste Demo-Themen je Gerätetyp (`_DEMO_THEMEN`), Form `LiveThema`;
* Wärmepumpe — Leistung, Modus, Vorlauf/Rücklauf/Spreizung, Warmwasser, Zusatzheizung, Strom heute;
* Wallbox — Zustand + Lademodus, Sitzung, Ladestrom, Phasen, Fahrzeug mit Ladestand, Ziel, Reichweite, Kilometerstand;
* E-Auto — Ladestand, Reichweite, Kilometerstand und **Standort** (`zu_hause`, wie `_fahrzeug_emob`).

**Nicht hier:** «Betrieb heute», «Gefahren heute», «Fahrverbrauch heute», «Wärme heute», die Kopfzahl «PV-Anteil heute»
— sie kommen aus dem Tag-Detail (`/api/energie-profil/{id}/tag-detail`), das keinen Demo-Schalter kennt.

Alle Proben gehen durch das Response-Modell (`LiveDashboardResponse`): FastAPI verwirft Undeklariertes still.
Keine Probe liest die Uhr: der Wartungstermin wird gegen den `zeitpunkt` derselben Demo-Antwort gemessen.

Schwesterdateien: test_demo_bestand_sonstiges_verbraucher.py (Demo-Bestand), test_341_live_merkmale.py (Demo-IDs der
Anlage), test_themen_live.py (echter Themen-Pfad).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.api.routes import live_dashboard
from backend.api.routes.live_dashboard import LiveDashboardResponse, get_live_data
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import UEBERBLICK_TYPEN


def _demo() -> dict:
    return LiveDashboardResponse(**live_dashboard._generate_demo_data(1, "Demo")).model_dump()


def _themen_je_geraet(daten: dict) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for t in daten["themen"]:
        out.setdefault(t["investition_id"], []).append(t)
    return out


# ── Themen ────────────────────────────────────────────────────────────────────

def test_demo_themen_fest_je_geraetetyp():
    """WP (Slot 5) zwei Themen, Wallbox (Slot 6) eins, E-Auto (Slot 4) zwei — Namen und Labels wie im Auftrag."""
    je = _themen_je_geraet(_demo())
    namen = {inv: [(t["name"], [e["label"] for e in t["eintraege"]]) for t in ts] for inv, ts in je.items()}
    assert namen == {
        5: [("Anlagenstatus", ["Verdichter", "Störung", "Betriebsstunden"]), ("Service", ["Nächste Wartung"])],
        6: [("Ladepunkt", ["Phasen", "Stromstärke", "Freigabe"])],
        4: [("Fahrzeugzustand", ["Türen", "Reifen vorne links", "Fenster"]),
            ("Klima", ["Innentemperatur", "Vorklimatisierung"])],
    }


def test_demo_themen_form_wie_der_echte_pfad():
    """Jeder Eintrag hat einen Wert, Quelle «ha», eine Kennung `sensor.demo_…` und einen ISO-Zeitpunkt; IDs je Gerät
    eindeutig in der Store-Form `t<n>`/`e<n>`."""
    for inv, themen in _themen_je_geraet(_demo()).items():
        ids = [t["id"] for t in themen] + [e["id"] for t in themen for e in t["eintraege"]]
        assert len(ids) == len(set(ids)), inv
        for t in themen:
            assert t["id"].startswith("t") and t["eintraege"]
            for e in t["eintraege"]:
                assert e["id"].startswith("e") and e["wert"], e
                assert e["quelle"] == "ha" and e["kennung"].startswith("sensor.demo_"), e
                datetime.fromisoformat(e["zeitpunkt"])


def test_demo_themen_werte_roh_wie_der_ha_state():
    """Rohwerte wie HA (Punkt als Dezimaltrenner, Einheit getrennt); der Wartungstermin ist ein Zeitstempel in 40 Tagen."""
    werte = {e["label"]: e for t in _demo()["themen"] for e in t["eintraege"]}
    assert (werte["Reifen vorne links"]["wert"], werte["Reifen vorne links"]["einheit"]) == ("259.5", "kPa")
    assert (werte["Betriebsstunden"]["wert"], werte["Betriebsstunden"]["einheit"]) == ("4812", "h")
    assert (werte["Innentemperatur"]["wert"], werte["Innentemperatur"]["einheit"]) == ("21.5", "°C")
    assert werte["Türen"]["wert"] == "locked" and werte["Freigabe"]["wert"] == "on"
    wartung = werte["Nächste Wartung"]
    assert wartung["device_class"] == "timestamp"
    abstand = datetime.fromisoformat(wartung["wert"]) - datetime.fromisoformat(wartung["zeitpunkt"])
    assert timedelta(days=39) < abstand < timedelta(days=41)


# ── Route: Themen auf die Geräte der Anlage, jeder Hub-Typ gefüllt ─────────────

async def _anlage(db):
    anlage = Anlage(anlagenname="Demo-Hubs", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    invs = {}
    for typ, name in (("e-auto", "Auto 1"), ("waermepumpe", "WP 1"), ("wallbox", "WB 1"),
                      ("e-auto", "Auto 2"), ("waermepumpe", "WP 2")):
        inv = Investition(anlage_id=anlage.id, typ=typ, bezeichnung=name, aktiv=True)
        db.add(inv)
        await db.flush()
        invs[name] = inv.id
    return anlage, invs


async def test_route_jeder_hub_typ_hat_themen_am_ersten_geraet(db):
    """Die Themen hängen am ersten Gerät jedes Hub-Typs der Anlage (n-ter Demo-Knoten = n-te Investition)."""
    anlage, invs = await _anlage(db)
    daten = LiveDashboardResponse.model_validate(await get_live_data(anlage.id, demo=True, db=db)).model_dump()
    je = _themen_je_geraet(daten)
    assert set(je) == {invs["WP 1"], invs["WB 1"], invs["Auto 1"]}
    typ_von = {invs["WP 1"]: "waermepumpe", invs["WB 1"]: "wallbox", invs["Auto 1"]: "e-auto"}
    assert {typ_von[i] for i in je} == set(UEBERBLICK_TYPEN), "jeder Typ mit «Überblick» trägt Demo-Themen"


async def test_route_jeder_hub_typ_hat_seine_kachel_quellen(db):
    """Je Hub-Typ die Live-Quellen der Kacheln und Karten — gegen das Response-Modell, auf den IDs der Anlage."""
    anlage, invs = await _anlage(db)
    daten = LiveDashboardResponse.model_validate(await get_live_data(anlage.id, demo=True, db=db)).model_dump()
    k = {x["key"]: x for x in daten["komponenten"]}

    wp = k[f"waermepumpe_{invs['WP 1']}"]
    assert wp["verbrauch_kw"] is not None and wp["betriebsmodus"] and wp["betriebsmodus_label"]
    for feld in ("vorlauf_c", "ruecklauf_c", "spreizung_k", "warmwasser_c", "heizstab_w"):
        assert wp[feld] is not None, feld
    assert daten["warmwasser_temperatur_c"] is not None
    assert daten["heute_kwh_pro_komponente"][f"waermepumpe_{invs['WP 1']}"] > 0

    wb = k[f"wallbox_{invs['WB 1']}"]
    assert wb["ladezustand_label"] and wb["lademodus_label"]
    assert wb["sitzung"]["kwh"] and wb["sitzung"]["dauer_s"] and wb["ladestrom_a"] and wb["phasen_aktiv"]
    (auto,) = wb["fahrzeuge"]
    assert auto["investition_id"] == invs["Auto 1"]
    for feld in ("soc", "reichweite_km", "ziel_prozent", "km_stand"):
        assert auto[feld] is not None, feld
    assert daten["heute_kwh_pro_komponente"][f"wallbox_{invs['WB 1']}"] > 0

    # E-Auto: Ladestand (Gauge), Reichweite, Kilometerstand und Standort an beiden Demo-Autos.
    autos = {f["investition_id"]: f for x in daten["komponenten"] for f in (x.get("fahrzeuge") or ())}
    assert autos[invs["Auto 1"]]["zu_hause"] is True
    assert all(f["zu_hause"] is True for f in autos.values())
    assert {g["key"] for g in daten["gauges"]} >= {f"soc_{invs['Auto 1']}"}
    assert k[f"eauto_{invs['Auto 1']}"]["parent_key"] == f"wallbox_{invs['WB 1']}"
