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
        "erkennung": ["sensor.evcc_*"],
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
                },
            },
            "e-auto": {
                "felder": {
                    "km_gefahren": {
                        "muster": ["sensor.evcc_*odometer*"],
                        "hinweis": "Kilometerstand des Fahrzeugs (kumulativ).",
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
    # Nur-Erkennung (Feld-Muster noch unbelegt — Basis wächst kuratiert):
    {
        "integration": "go_echarger",
        "label": "go-eCharger",
        "erkennung": ["sensor.go_echarger*", "sensor.go_e_*", "sensor.goe_*"],
        "typen": {},
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
