"""
Demo-Fixture für die Anlagenpass-Mockups.

Komplett ausgedachte „Musteranlage Sonnenhof" — kein Personenbezug,
keine DB. Wird von den drei Layout-Varianten gemeinsam verwendet,
damit Rainer auf Issue #121 nur über die Optik entscheidet.
"""
from __future__ import annotations

from datetime import date


def musteranlage() -> dict:
    return {
        "name": "Musteranlage Sonnenhof",
        "leistung_kwp": 11.40,
        "installationsdatum": date(2022, 5, 14),
        "mastr_id": "SEE000000123456",
        "standort_strasse": "Sonnenweg 12",
        "standort_plz": "63075",
        "standort_ort": "Musterstadt",
        "standort_land": "Deutschland",
        "ausrichtung": "Süd / Ost-West",
        "anlagenarten": [
            "PV-Anlage 11,4 kWp",
            "Batteriespeicher 10 kWh",
            "Wärmepumpe (Luft/Wasser)",
            "Wallbox 11 kW",
            "Balkonkraftwerk 600 W",
        ],
    }


def investitionen_demo() -> list[dict]:
    return [
        {
            "typ": "pv-module",
            "bezeichnung": "PV-String Süd (Hauptdach)",
            "anschaffungsdatum": date(2022, 5, 14),
            "leistung_kwp": 8.40,
            "ausrichtung": "Süd",
            "neigung_grad": 35,
            "modulanzahl": 21,
            "modul_typ": "Trina Vertex S 400 W",
            "wechselrichter": "SMA Tripower 8.0",
            "beschreibung_public": (
                "Hauptdach südseitig, 21 Module mit je 400 Wp. "
                "Wechselrichter im Hausanschlussraum, Verschattung "
                "morgens durch Nachbarschornstein bis ca. 8 Uhr."
            ),
        },
        {
            "typ": "speicher",
            "bezeichnung": "Hausspeicher Keller",
            "anschaffungsdatum": date(2022, 5, 14),
            "kapazitaet_kwh": 10.0,
            "modul_typ": "BYD HVS 10.2",
            "wechselrichter": "SMA Sunny Boy Storage 5.0",
            "beschreibung_public": (
                "Hochvolt-Speicher im Heizungsraum, gekoppelt an SMA "
                "Energy Manager. Notstromfähig (umschaltbar auf "
                "1-phasige Inselversorgung)."
            ),
        },
        {
            "typ": "waermepumpe",
            "bezeichnung": "Luft/Wasser-Wärmepumpe",
            "anschaffungsdatum": date(2023, 9, 1),
            "leistung_kwp": 9.0,
            "modul_typ": "Vaillant aroTHERM plus VWL 105/6",
            "beschreibung_public": (
                "Bivalentes System mit 200-l-Pufferspeicher und "
                "300-l-Brauchwasserspeicher. Flächenheizung im EG, "
                "Heizkörper im OG. Vorlauftemperatur max. 50 °C."
            ),
        },
    ]
