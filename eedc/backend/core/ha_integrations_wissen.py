"""Kuratierte Integrations-Wissensbasis für den HA-Sensor-Picker (#343 Baustein A, D2).

EINE SoT: Integration × Investitionstyp × eedc-Feld → Entity-ID-Muster + Hinweis.
Zweck ist ASSISTENZ, nie Automatik — die Auswahl trifft IMMER der Nutzer
(Auto-Erkennung scheitert an evcc↔E-Auto, WR↔Smartmeter; Memory
project_sensor_zuordnungs_assistenz). „Gefunden" wird eine Integration rein über
Entity-ID-Muster auf der /states-Liste — funktioniert damit über Supervisor UND
Remote-LL-Token, ohne Registry-/Supervisor-API.

Inhalt bewusst klein und nur mit BELEGTEM Wissen (evcc: verifiziert an realer
HA-Instanz, 2026-07); weitere Integrationen zunächst nur mit Erkennung +
generischem Hinweis. Die Basis wächst kuratiert mit Tester-Wissen.

`warnungen` sind Anti-Empfehlungen: Muster, deren Sensoren sich nur sprunghaft
aktualisieren (z. B. am Session-Ende) — der Auslöser von #343 (28,6-kW-Nadel im
Live-Tagesverlauf bei korrekter Einheit UND state_class).
"""
from __future__ import annotations

from fnmatch import fnmatch


# ─── Wissensbasis (kuratierte Daten, kein Verhalten) ─────────────────────────

WISSENSBASIS: list[dict] = [
    {
        "integration": "evcc",
        "label": "evcc",
        # P-433-2b K1: der Lademodus ist ein `select` — ohne ihn in der Erkennung fände der Picker ihn nicht.
        # P-433-2b K2b (Option A): connected/charging/enabled sind `binary_sensor` (Erhebung A1 :15–17).
        "erkennung": ["sensor.evcc_*", "select.evcc_*", "binary_sensor.evcc_*"],
        "typen": {
            "wallbox": {
                "felder": {
                    "ladung_kwh": {
                        "muster": ["sensor.evcc_*charged_energy*"],
                        "hinweis": "Ladepunkt-Zähler — aktualisiert live während der Ladung, richtig für die Gesamtladung.",
                    },
                    "ladung_pv_kwh": {
                        "muster": ["sensor.evcc_*solar*"],
                        "hinweis": "PV-Anteil der Ladung — einen kWh-Sensor wählen (kein %-Wert).",
                    },
                    # P-433-2b K1 (K-8, belegt an der Produktiv-HA 26.10.2026, Erhebung A1). Der Ladezustand aus
                    # connected/charging/enabled seit K2b über Option A (drei Rollen-Felder, `core/zustands_kanon.py`).
                    "evcc_verbunden": {
                        "muster": ["binary_sensor.evcc_*_connected"],
                        "hinweis": "Fahrzeug angesteckt (on/off) — nur nötig ohne Ladezustand-Sensor; zusammen mit «lädt» und «freigegeben» ergibt sich der Ladezustand-Chip.",
                    },
                    "evcc_laedt": {
                        "muster": ["binary_sensor.evcc_*_charging"],
                        "hinweis": "Lädt gerade (on/off) — Teil von Option A (Ladezustand aus drei Binär-Sensoren).",
                    },
                    "evcc_freigegeben": {
                        "muster": ["binary_sensor.evcc_*_enabled"],
                        "hinweis": "Laden freigegeben (on/off) — verbunden, aber nicht freigegeben ergibt «wartet».",
                    },
                    "lademodus": {
                        "muster": ["select.evcc_*_mode"],
                        "hinweis": "Lademodus des Ladepunkts (off · pv · minpv · now · smart).",
                    },
                    # P-433-2b K2a (Bauplan K2 E1, Erhebung :19): das erkannte Fahrzeug als `select` — Option `null` =
                    # kein bzw. unbekanntes Fahrzeug (Gast, wenn verbunden).
                    "fahrzeug_am_ladepunkt": {
                        "muster": ["select.evcc_*_vehicle_name"],
                        "hinweis": "Erkanntes Fahrzeug am Ladepunkt — der Name muss der «Kennung in der Steuerung» am E-Auto entsprechen; «null» heißt kein bzw. unbekanntes Fahrzeug.",
                    },
                    "sitzung_kwh": {
                        "muster": ["sensor.evcc_*_session_energy"],
                        "hinweis": "Energie der laufenden Sitzung.",
                    },
                    "sitzung_dauer_s": {
                        "muster": ["sensor.evcc_*_charge_duration"],
                        "hinweis": "Ladedauer der Sitzung in Sekunden.",
                    },
                    "ladestrom_a": {
                        "muster": ["sensor.evcc_*_charge_current"],
                        "hinweis": "Ladestrom gesamt in A.",
                    },
                    "phasen_aktiv": {
                        "muster": ["sensor.evcc_*_phases_active"],
                        "hinweis": "Phasen in Verwendung.",
                    },
                    "ziel_ladestand_prozent": {
                        "muster": ["sensor.evcc_*_effective_limit_soc"],
                        "hinweis": "Wirksames Ladelimit in %.",
                    },
                    "restzeit_min": {
                        "muster": ["sensor.evcc_*_charge_remaining_duration"],
                        "hinweis": "Laderestzeit — evcc meldet Sekunden: in Home Assistant die Anzeigeeinheit des Sensors auf Minuten stellen.",
                    },
                },
            },
            "e-auto": {
                "felder": {
                    "km_gefahren": {
                        "muster": ["sensor.evcc_*odometer*"],
                        "hinweis": "Kilometerstand des Fahrzeugs (kumulativ).",
                    },
                    "reichweite_km": {
                        "muster": ["sensor.evcc_*_vehicle_range"],
                        "hinweis": "Reichweite — evcc meldet sie nur, solange das Auto am Ladepunkt hängt.",
                    },
                },
            },
        },
        "warnungen": [
            {
                "muster": ["sensor.evcc_*stat_total*"],
                "text": "Dieser evcc-Statistik-Sensor springt erst am Session-Ende — Live-/Tageskurven zeigen dann Nadeln. Für Monatssummen ok. (#343)",
            },
        ],
    },
    # P-433-2b K1 (K-8): SMA EV Charger über die HACS-Integration `smaev` (belegt an der Produktiv-HA, Erhebung A2).
    # Die Entitäts-IDs folgen dem Gerätenamen und der HA-Sprache — erkannt wird über die Sensor-Bezeichnung.
    {
        "integration": "smaev",
        "label": "SMA EV Charger",
        "erkennung": [
            "sensor.*_status_ladevorgang", "select.*_betriebsart_des_ladevorgangs",
            "sensor.*_schalterstellung_drehschalter", "sensor.*_energie_ladevorgang",
        ],
        "typen": {
            "wallbox": {
                "felder": {
                    "ladezustand": {
                        "muster": ["sensor.*_status_ladevorgang"],
                        "hinweis": "Status des Ladevorgangs (not_connected · sleep_mode · active_mode · station_locked · station_fault).",
                    },
                    "lademodus": {
                        "muster": ["sensor.*_schalterstellung_drehschalter", "select.*_betriebsart_des_ladevorgangs"],
                        "hinweis": "Drehschalter (smart_charging · boost_charging) oder Betriebsart (boost_charging · charge_stop).",
                    },
                    "sitzung_kwh": {
                        "muster": ["sensor.*_energie_ladevorgang"],
                        "hinweis": "Energie des Ladevorgangs — der Sensor meldet Wh: in Home Assistant die Anzeigeeinheit auf kWh stellen.",
                    },
                },
            },
        },
        "warnungen": [],
    },
    # P-433-2b K1 (K-8): Smart #1/#3/#5 über die HACS-Integration `smarthashtag` (belegt, Erhebung A3).
    {
        "integration": "smarthashtag",
        "label": "Smart",
        "erkennung": [
            "sensor.smart_ladezustand*", "sensor.smart_ladesanschluss*", "sensor.smart_reichweite*",
            "sensor.smart_ladeziel*", "device_tracker.smart_*",
        ],
        "typen": {
            "e-auto": {
                "felder": {
                    "ladezustand_fahrzeug": {
                        "muster": ["sensor.smart_ladesanschluss*", "sensor.smart_ladezustand*"],
                        "hinweis": "Ladeanschluss (verbunden · lädt · DC) oder Ladezustand des Fahrzeugs.",
                    },
                    "reichweite_km": {
                        "muster": ["sensor.smart_reichweite"],
                        "hinweis": "Aktuelle Reichweite (nicht «bei voller Ladung»).",
                    },
                    "ziel_ladestand_prozent": {
                        "muster": ["sensor.smart_ladeziel*"],
                        "hinweis": "Ladeziel des Fahrzeugs in %.",
                    },
                    "zu_hause": {
                        "muster": ["device_tracker.smart_*"],
                        "hinweis": "Standort als Zone (home · not_home).",
                    },
                },
            },
        },
        "warnungen": [],
    },
    # P-433-2b K1 (K-8): go-eCharger (HACS marq24/ha-goecharger-api2) — API-Schlüssel belegt (Erhebung B2.1); die
    # Entitäts-IDs tragen die Seriennummer, deshalb ein Muster auf den Schlüssel.
    {
        "integration": "go_echarger",
        "label": "go-eCharger",
        "erkennung": ["sensor.go_echarger*", "sensor.go_e_*", "sensor.goe_*"],
        "typen": {
            "wallbox": {
                "felder": {
                    "ladezustand": {
                        "muster": ["sensor.go*_car*"],
                        "hinweis": "Fahrzeugstatus `car` — die Codes 0–5 versteht eedc über MQTT; liefert der Sensor in Home Assistant Text, einen Template-Sensor auf die eedc-Wörter bauen.",
                    },
                    "sitzung_kwh": {
                        "muster": ["sensor.go*_wh*"],
                        "hinweis": "Energie seit dem Anstecken (`wh`) — meldet Wh: in Home Assistant die Anzeigeeinheit auf kWh stellen.",
                    },
                    "ladestrom_a": {
                        "muster": ["sensor.go*_amp*"],
                        "hinweis": "Ladestrom (`amp`).",
                    },
                    "phasen_aktiv": {
                        "muster": ["sensor.go*_pnp*"],
                        "hinweis": "Anzahl der Phasen (`pnp`).",
                    },
                },
            },
        },
        "warnungen": [],
    },
    {
        "integration": "openwb",
        "label": "openWB",
        "erkennung": ["sensor.openwb*"],
        "typen": {},
        "warnungen": [],
    },
    {
        "integration": "keba",
        "label": "Keba",
        "erkennung": ["sensor.keba*"],
        "typen": {},
        "warnungen": [],
    },
    {
        "integration": "myenergi_zappi",
        "label": "myenergi Zappi",
        "erkennung": ["sensor.zappi*", "sensor.myenergi*"],
        "typen": {},
        "warnungen": [],
    },
]

# Generischer Hinweis für erkannte Integrationen ohne Feld-Muster.
NUR_ERKANNT_HINWEIS = "Integration erkannt — wähle unten den passenden kWh-Zähler dieses Geräts."


# ─── Auswertung ──────────────────────────────────────────────────────────────

def _passt(entity_id: str, muster: list[str]) -> bool:
    e = entity_id.lower()
    return any(fnmatch(e, m.lower()) for m in muster)


def analysiere_vorschlaege(
    entity_ids: list[str],
    feld: str | None = None,
    inv_typ: str | None = None,
) -> dict:
    """Vorschläge + Warnungen für den Picker.

    Returns:
        {
          "integrationen": ["evcc", …],                # erkannte Labels
          "vorschlaege": [{integration, label, entity_id, hinweis}],  # für DIESES Feld
          "warnungen": {entity_id: text},              # Anti-Empfehlungen (alle Felder)
        }
    """
    integrationen: list[str] = []
    vorschlaege: list[dict] = []
    warnungen: dict[str, str] = {}

    for wissen in WISSENSBASIS:
        erkannt = [e for e in entity_ids if _passt(e, wissen["erkennung"])]
        if not erkannt:
            continue
        integrationen.append(wissen["label"])

        # Anti-Empfehlungen gelten unabhängig vom Ziel-Feld (Auswahl-Warnung).
        for w in wissen.get("warnungen", []):
            for e in erkannt:
                if _passt(e, w["muster"]):
                    warnungen.setdefault(e, w["text"])

        # Feld-Vorschläge nur, wenn Typ+Feld bekannt und kuratiert.
        feld_wissen = (
            wissen.get("typen", {}).get(inv_typ or "", {}).get("felder", {}).get(feld or "")
        )
        if feld_wissen:
            for e in erkannt:
                if _passt(e, feld_wissen["muster"]):
                    vorschlaege.append({
                        "integration": wissen["integration"],
                        "label": wissen["label"],
                        "entity_id": e,
                        "hinweis": feld_wissen["hinweis"],
                    })

    # Explizites Feld-Wissen schlägt die generische Anti-Empfehlung: evcc
    # `stat_total_solar*` ist trotz Session-Takt die richtige Quelle für
    # `ladung_pv_kwh` (Monats-Semantik) — die Warnung entfällt für Vorschläge
    # DIESES Feldes.
    for v in vorschlaege:
        warnungen.pop(v["entity_id"], None)

    return {
        "integrationen": integrationen,
        "vorschlaege": vorschlaege,
        "warnungen": warnungen,
    }
