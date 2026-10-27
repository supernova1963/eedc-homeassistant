"""Kanon der Zustandsfelder der E-Mobilität — tabellengetrieben, ein Modul (P-433-2b K1, Bauplan E1, E-K1-1).

**Warum es diese Datei gibt.** Bis K1 kannte eedc genau ein Zustandsfeld: den Betriebsmodus einer Wärmepumpe
(`core/betriebsmodus.py`). Mit K1 kommen vier dazu — Wallbox ``ladezustand`` und ``lademodus``, E-Auto
``ladezustand_fahrzeug`` und ``zu_hause``. Sie bekommen **dieselbe Bauform** wie der Betriebsmodus (fester Kanon,
Werte-Tabelle am Feld, Normalisierer, Klartext, Daten-Checker-Hinweis bei fremdem Wert, Konzept #433 E12), aber
**eine Tabelle je Feld** statt eines Moduls je Feld. ``core/betriebsmodus.py`` bleibt unberührt (kein Umzug, Bauplan
E-K1-1): er trägt Eigenheiten, die hier keine Rolle spielen (``hvac_action``, ``unbestimmt``, Innengeräte).

**Leitsatz (Blatt §0 Nr. 7, K-1): Registry-Feld = Vertrag, Integration = Quelle, DB = nur Zuordnung.** Ein Zustand
wird gelesen, wenn eine Sicht ihn braucht, und nicht gespeichert.

⛔ **Zustand nur gemessen (K-2, Blatt P9).** Hier gibt es keinen Zustand aus der Leistung und keine Schwelle. Ein
unbekannter Rohwert wird **nicht** geraten: er ergibt ``None`` (kein Chip), und der Daten-Checker nennt ihn
(`daten_checker/emob.py::_check_emob_zustand_wert`). Anders als beim Betriebsmodus gibt es kein ``unbestimmt`` —
ein Ladezustand, den eedc nicht versteht, verteilt keinen Strom, er wird schlicht nicht angezeigt.

**Werte-Tabelle (P7, nur Belegtes):** die Kanon-Wörter selbst (Weg B: Template-Sensor in Home Assistant) und die an
echten Anlagen belegten Rohwerte — SMA EV Charger (`smaev`), evcc (`evcc_intg`, Lademodus), Smart #1
(`smarthashtag`), go-eCharger (`car`/`lmo` als Zahlencode, nur über MQTT wie die Modus-Codes, HA-Bauform §9 H1 = A)
und die Zone eines HA-``device_tracker`` (``home``/``not_home``). Quelle: Erhebung 26.10.2026 Teil A/B2/D. Weitere
Integrationen stehen als Hinweis im Handbuch, nicht hier (keine gepflegte Synonym-Liste, Entscheid 24.10.2026).

⚠ **evcc-Ladezustand aus drei Binär-Sensoren** (connected/charging/enabled, Blatt P4, Bauplan K-9) ist in K1 **nicht**
gebaut: die Zuordnungsform der Live-Felder trägt je Feld genau eine Entität (``investitionen[id].live[key] = entity``,
`api/routes/sensor_mapping.py::InvestitionFelder.live`). Bis dahin gilt für evcc Weg B (Template-Sensor auf den Kanon).
"""

from __future__ import annotations

from typing import Final, Optional

# ── Die Felder ───────────────────────────────────────────────────────────────

LADEZUSTAND: Final[str] = "ladezustand"
LADEMODUS: Final[str] = "lademodus"
LADEZUSTAND_FAHRZEUG: Final[str] = "ladezustand_fahrzeug"
ZU_HAUSE: Final[str] = "zu_hause"

# ── Kanon-Werte (die Reihenfolge ist die Lese-Reihenfolge der Werte-Tabelle) ──

#: Wallbox: was am Ladepunkt geschieht.
KEIN_FAHRZEUG: Final[str] = "kein_fahrzeug"
VERBUNDEN: Final[str] = "verbunden"
WARTET: Final[str] = "wartet"
LAEDT: Final[str] = "laedt"
FERTIG: Final[str] = "fertig"
GESPERRT: Final[str] = "gesperrt"
FEHLER: Final[str] = "fehler"
#: E-Auto: was das Fahrzeug selbst meldet.
NICHT_VERBUNDEN: Final[str] = "nicht_verbunden"
LAEDT_DC: Final[str] = "laedt_dc"
#: Standort als Zone (nie eine Position).
UNTERWEGS: Final[str] = "unterwegs"

KANON: Final[dict[str, tuple[str, ...]]] = {
    LADEZUSTAND: (KEIN_FAHRZEUG, VERBUNDEN, WARTET, LAEDT, FERTIG, GESPERRT, FEHLER),
    LADEMODUS: ("aus", "pv", "smart", "schnell", "plan", "eco"),
    LADEZUSTAND_FAHRZEUG: (NICHT_VERBUNDEN, VERBUNDEN, LAEDT, LAEDT_DC, FERTIG, FEHLER),
    ZU_HAUSE: (ZU_HAUSE, UNTERWEGS),
}

#: Die Felder dieses Kanons — der Datenquellen-Fläche und dem Leser bekannt.
ZUSTANDS_FELDER: Final[frozenset[str]] = frozenset(KANON)

#: Kanon → Klartext je Feld. Der Client führt keine zweite Tabelle ([[feedback_typ_labels_pattern]]).
LABEL: Final[dict[str, dict[str, str]]] = {
    LADEZUSTAND: {
        KEIN_FAHRZEUG: "Kein Fahrzeug", VERBUNDEN: "Verbunden", WARTET: "Wartet", LAEDT: "Lädt",
        FERTIG: "Fertig", GESPERRT: "Gesperrt", FEHLER: "Fehler",
    },
    LADEMODUS: {"aus": "Aus", "pv": "PV", "smart": "Smart", "schnell": "Schnell", "plan": "Plan", "eco": "Eco"},
    LADEZUSTAND_FAHRZEUG: {
        NICHT_VERBUNDEN: "Nicht verbunden", VERBUNDEN: "Verbunden", LAEDT: "Lädt", LAEDT_DC: "Lädt DC",
        FERTIG: "Fertig", FEHLER: "Fehler",
    },
    ZU_HAUSE: {ZU_HAUSE: "Zu Hause", UNTERWEGS: "Unterwegs"},
}

# ── Die Werte-Tabellen: Rohwert (klein, getrimmt) → Kanon ─────────────────────
#
# Die Kanon-Wörter selbst stehen nicht hier, sie gelten an jedem Feld (`_tabelle`). Die Zahlencodes stehen getrennt
# (`_CODES`): sie gelten nur über MQTT (``codes=True``), wie beim Betriebsmodus — eine Ziffer aus einem HA-Sensor
# ist ein Hersteller-Rohcode, den eedc nicht kennt (Easee «3» ist «lädt», go-e «3» ist «wartet»).

_ROH: Final[dict[str, dict[str, str]]] = {
    LADEZUSTAND: {
        # SMA EV Charger (`smaev`, `sensor.wallbox_status_ladevorgang`, Erhebung A2)
        "not_connected": KEIN_FAHRZEUG,
        "sleep_mode": VERBUNDEN,
        "active_mode": LAEDT,
        "station_locked": GESPERRT,
        "station_fault": FEHLER,
    },
    LADEMODUS: {
        # evcc (`select.evcc_<ladepunkt>_mode`, Erhebung A1/D1): off · pv · minpv · now · smart
        "off": "aus",
        "minpv": "smart",
        "now": "schnell",
        # SMA EV Charger: Drehschalter und Betriebsart des Ladevorgangs (Erhebung A2)
        "smart_charging": "pv",
        "boost_charging": "schnell",
        "charge_stop": "aus",
    },
    LADEZUSTAND_FAHRZEUG: {
        # Smart #1 (`smarthashtag`): `sensor.smart_ladesanschluss` (Erhebung A3)
        "not_connected": NICHT_VERBUNDEN,
        "plugged_not_charging": VERBUNDEN,
        "dc_connected": LAEDT_DC,
        # … und `sensor.smart_ladezustand` (14 Werte, Erhebung A3; ohne Aussage siehe `_OHNE_AUSSAGE`)
        "charging": LAEDT,
        "dc_charging": LAEDT_DC,
        "plugged_in": VERBUNDEN,
        "waiting_for_charging": VERBUNDEN,
        "complete": FERTIG,
        "fully_charged": FERTIG,
        "finished_fully_charged": FERTIG,
        "finished_not_full": FERTIG,
        "target_reached": FERTIG,
        "error": FEHLER,
    },
    ZU_HAUSE: {
        # Zone eines HA-`device_tracker` — nur «home» ist zu Hause; eine benannte Zone ist kein belegter Wert.
        "home": ZU_HAUSE,
        "not_home": UNTERWEGS,
    },
}

#: Zahlencodes (nur MQTT, ``codes=True``): go-eCharger `car` und `lmo` (Erhebung B2.1).
_CODES: Final[dict[str, dict[str, str]]] = {
    LADEZUSTAND: {"0": FEHLER, "1": KEIN_FAHRZEUG, "2": LAEDT, "3": WARTET, "4": FERTIG, "5": FEHLER},
    LADEMODUS: {"3": "schnell", "4": "eco", "5": "plan"},
}

#: Rohwerte, die eedc **kennt**, die aber keinen Zustand aussagen (Smart `not_charging` — angesteckt oder nicht?,
#: `default`, `invalid`). Sie ergeben ``None`` wie ein fehlender Wert, aber keinen Checker-Hinweis.
_OHNE_AUSSAGE: Final[dict[str, frozenset[str]]] = {
    LADEZUSTAND_FAHRZEUG: frozenset({"not_charging", "default", "invalid"}),
}

#: States, die Home Assistant für «gerade nichts zu sagen» benutzt — kein Zustand, kein unbekannter Wert.
_KEIN_ZUSTAND: Final[frozenset[str]] = frozenset({"unknown", "unavailable", "none", ""})


def _aufbereitet(roh: object, codes: bool) -> str:
    """Klein, getrimmt; über MQTT wird «2.0» zu «2» (dieselbe Regel wie die Modus-Codes)."""
    text = str(roh).strip().lower()
    if codes:
        try:
            zahl = float(text)
        except ValueError:
            return text
        if zahl.is_integer():
            return str(int(zahl))
    return text


def _tabelle(feld: str, codes: bool) -> dict[str, str]:
    tab = {k: k for k in KANON.get(feld, ())}
    tab.update(_ROH.get(feld, {}))
    if codes:
        tab.update(_CODES.get(feld, {}))
    return tab


def normalisiere(feld: str, roh: Optional[object], *, codes: bool = False) -> Optional[str]:
    """Roher State (HA) oder Payload (MQTT) → Kanon-Wert dieses Felds, sonst ``None``.

    ``None`` heißt «kein Zustand, den eedc anzeigen kann»: kein Wert, ``unknown``/``unavailable``, ein bekannter
    Wert ohne Aussage oder ein fremder Wert. Groß-/Kleinschreibung und Randleerzeichen sind egal.
    """
    if roh is None or feld not in KANON:
        return None
    text = _aufbereitet(roh, codes)
    if text in _KEIN_ZUSTAND:
        return None
    return _tabelle(feld, codes).get(text)


def ist_bekannter_wert(feld: str, roh: Optional[object], *, codes: bool = False) -> bool:
    """Steht dieser Rohwert in der Werte-Tabelle des Felds (oder unter «bekannt, ohne Aussage»)?

    ``None`` und die Nicht-Zustände sind **kein** Wert und damit auch kein unbekannter — der Daten-Checker fragt sie
    gar nicht erst (`_check_emob_zustand_wert`). Die Zahlencodes zählen nur mit ``codes=True``.
    """
    if roh is None or feld not in KANON:
        return False
    text = _aufbereitet(roh, codes)
    return text in _tabelle(feld, codes) or text in _OHNE_AUSSAGE.get(feld, frozenset())


def ist_kein_zustand(roh: Optional[object]) -> bool:
    """``None``, leer, ``unknown``, ``unavailable`` — «nicht hingesehen», keine Frage an den Checker."""
    return roh is None or str(roh).strip().lower() in _KEIN_ZUSTAND


def label(feld: str, kanon: Optional[str]) -> Optional[str]:
    """Kanon-Wert → Klartext, ``None`` ohne Wert."""
    if kanon is None:
        return None
    return LABEL.get(feld, {}).get(kanon)


def klartext_roh(feld: str, roh: Optional[object], *, codes: bool = False) -> Optional[str]:
    """Rohwert → Klartext für die Zuordnungs-Fläche (F-53-Muster: kommt etwas an, und versteht eedc es?)."""
    return label(feld, normalisiere(feld, roh, codes=codes))


def werte_je_kanon(feld: str, *, codes: bool = False) -> list[dict]:
    """Die Werte-Tabelle eines Felds, gruppiert nach Kanon-Wert — Form wie `betriebsmodus_werte_je_betriebsart`.

    Returns:
        ``[{"kanon": "laedt", "label": "Lädt", "werte": ["laedt", "active_mode", …]}, …]`` in Kanon-Reihenfolge; das
        Kanon-Wort steht je Gruppe zuerst (es ist die Schreibweise für Weg B), die Zahlencodes nur mit ``codes``.
    """
    if feld not in KANON:
        return []
    gruppen: dict[str, list[str]] = {k: [k] for k in KANON[feld]}
    for roh, kanon in _ROH.get(feld, {}).items():
        gruppen[kanon].append(roh)
    if codes:
        for roh, kanon in _CODES.get(feld, {}).items():
            gruppen[kanon].append(roh)
    return [{"kanon": k, "label": LABEL[feld][k], "werte": werte} for k, werte in gruppen.items()]


def werte_klartext(feld: str, *, codes: bool = False) -> str:
    """Die Werte-Tabelle als ein Satz für Meldungstexte (Daten-Checker): «Lädt (laedt, active_mode) · …»."""
    return " · ".join(f"{g['label']} ({', '.join(g['werte'])})" for g in werte_je_kanon(feld, codes=codes))
