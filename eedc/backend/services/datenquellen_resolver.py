"""
Datenquellen-V4 — gemeinsamer Feld→Quelle-Resolver (B8).

Eine Implementierung der effektiven-Quelle-Auflösung, genutzt von
- der einmaligen B8-1-Materialisierung (`migrations/migrate_datenquellen_materialisieren.py`)
- der lazy B8-2-Auflösung beim `/felder`-Aufruf (`api/routes/datenquellen.py`)

So bleibt die HA-Entity-Erkennung an EINER Stelle ([[feedback_aggregations_drift]]).

Quelle-Auflösung je NOCH NICHT explizit zugeordnetem Feld (Gernots 3-Stufen-Regel,
2026-07-16). Grundeinstellung bleibt wie bisher Inbound; „keine" ist nur das
ehrliche Ergebnis eines stummen Inbound-Topics:

1. HA-Sensor in `sensor_mapping` zugeordnet → HA  (keine Inhaltsprüfung — manuell erfasst)
2. sonst Gateway-Mapping (ziel_key match)      → Gateway (keine Inhaltsprüfung — manuell erfasst)
3. sonst Inbound-Topic liefert einen Wert      → Inbound; sonst → keine
"""

from __future__ import annotations

from typing import Optional

from backend.services.snapshot.keys import _energy_field_id_to_sensor_key

# Quelle-Wire-Werte (stabil; = Konstanten in api/routes/datenquellen.py).
QUELLE_HA_APP = "ha_app"
QUELLE_HA_CONNECTOR = "ha_connector"
QUELLE_GATEWAY = "mqtt_gateway"
QUELLE_INBOUND = "mqtt_inbound_standard"
QUELLE_KEINE = "keine"


def topic_suffix(topic: str) -> Optional[str]:
    """`eedc/{aid}_{slug}/{suffix}` → suffix (= Gateway-ziel_key nach C2a-Fix)."""
    parts = topic.split("/", 2)
    return parts[2] if len(parts) == 3 else None


def ha_entity_fuer_feld(
    field_id: str, mapping: dict,
    basis_live: dict, inv_live_map: dict,
) -> Optional[str]:
    """Effektive HA-Entity eines Feldes DIREKT aus `sensor_mapping`.

    Live-Felder aus den extrahierten Live-Maps; Energie-/sonstige Felder direkt
    aus `basis[feld].sensor_id` bzw. `investitionen[id].felder[feld].sensor_id`
    (kein kumulativ-Filter → deckt auch Nicht-Zähler wie `ladevorgaenge`).
    """
    if field_id.startswith("basis_live_"):
        return basis_live.get(field_id[len("basis_live_"):]) or None
    if field_id.startswith("inv_live_"):
        inv_id, sep, key = field_id[len("inv_live_"):].partition("_")
        if not sep:
            return None
        return inv_live_map.get(inv_id, {}).get(key) or None
    if field_id.startswith("basis_energy_"):
        sk = _energy_field_id_to_sensor_key(field_id)  # z. B. "basis:einspeisung"
        if not sk or not sk.startswith("basis:"):
            return None
        feld = sk.split(":", 1)[1]
        cfg = (mapping.get("basis") or {}).get(feld)
        if isinstance(cfg, dict) and cfg.get("strategie") == "sensor":
            return cfg.get("sensor_id") or None
        return None
    if field_id.startswith("basis_preis_"):
        # Preis-Felder liegen im selben Eintrags-Shape unter `basis` wie die
        # Energie-Felder, nur ohne Snapshot-Key — deshalb direkt statt über
        # `_energy_field_id_to_sensor_key`.
        from backend.services.datenquellen_mapping_sync import BASIS_PREIS_FELD

        feld = BASIS_PREIS_FELD.get(field_id[len("basis_preis_"):])
        if not feld:
            return None
        cfg = (mapping.get("basis") or {}).get(feld)
        if isinstance(cfg, dict) and cfg.get("strategie") == "sensor":
            return cfg.get("sensor_id") or None
        return None
    if field_id.startswith("inv_energy_"):
        inv_id, sep, feld = field_id[len("inv_energy_"):].partition("_")
        if not sep or not feld:
            return None
        inv = (mapping.get("investitionen") or {}).get(inv_id) or {}
        cfg = (inv.get("felder") or {}).get(feld)
        if isinstance(cfg, dict) and cfg.get("strategie") == "sensor":
            return cfg.get("sensor_id") or None
        return None
    return None


def resolve_effektive_quelle(
    field_id: str,
    standard_topic: str,
    mapping: dict,
    basis_live: dict,
    inv_live_map: dict,
    gw_by_zielkey: dict,
    ha_kind: str,
    inbound_hat_wert: bool,
):
    """3-Stufen-Auflösung (B8-2) für ein Feld OHNE expliziten `quellen`-Eintrag.

    Args:
        gw_by_zielkey: {ziel_key: MqttGatewayMapping} — nur AKTIVE Gateway-Zeilen.
        ha_kind: Transport der aktiven HA-Verbindung ("ha_app"/"ha_connector").
        inbound_hat_wert: ob der Inbound-Cache für dieses Feld einen Wert führt.

    Returns:
        (display_quelle, persist_entry, gw_row_deaktivieren)
        - display_quelle: die in der Fläche anzuzeigende Quelle (inkl. "keine").
        - persist_entry: dict zum additiven Festschreiben in `quellen[field_id]`
          bei POSITIVER Evidenz (HA/Gateway/Inbound-mit-Wert) — oder None, wenn
          NICHTS persistiert werden soll (stummes Inbound = „keine" nur anzeigen,
          bei jedem Aufruf neu bewertbar → self-healing, kein auto-keine-Ballast).
        - gw_row_deaktivieren: paralleles Gateway-Mapping, das bei HA-Wahl gemäß
          §2h deaktiviert (nicht gelöscht) werden soll — oder None.
    """
    ha_entity = ha_entity_fuer_feld(field_id, mapping, basis_live, inv_live_map)
    suffix = topic_suffix(standard_topic)
    gw_row = gw_by_zielkey.get(suffix) if suffix else None

    # Stufe 1: HA-Sensor zugeordnet (keine Inhaltsprüfung — manuell erfasst).
    if ha_entity:
        return ha_kind, {"quelle": ha_kind, "entity_id": ha_entity}, gw_row

    # Stufe 2: Gateway-Topic vorhanden (keine Inhaltsprüfung — manuell erfasst).
    if gw_row is not None:
        return QUELLE_GATEWAY, {"quelle": QUELLE_GATEWAY, "mapping_id": gw_row.id}, None

    # Stufe 3: Inbound nur bei tatsächlichem Wert; sonst „keine" (nicht persistiert).
    if inbound_hat_wert:
        return QUELLE_INBOUND, {"quelle": QUELLE_INBOUND}, None
    return QUELLE_KEINE, None, None


# ─── Erwartet eedc ein Standard-Inbound-Topic? (F-50, #389) ──────────────

# Quellen, die den Wert NICHT über das Standard-Inbound-Topic liefern.
# Gateway fehlt hier bewusst — s. `erwartet_inbound_topic`.
QUELLEN_OHNE_INBOUND_TOPIC = frozenset({
    QUELLE_KEINE, QUELLE_HA_APP, QUELLE_HA_CONNECTOR,
})


def feld_id_aus_match_key(match_key) -> str:
    """Stabile Feld-Kennung aus dem `match_key` der Topic-Registry.

    Spiegel von `api/routes/datenquellen.py::_feld_id` — hier, damit der
    Daten-Checker die Kennung bilden kann, ohne aus einem Route-Modul zu
    importieren. Beide Seiten müssen dieselbe Zeichenkette erzeugen, sonst
    trifft die Quellen-Abfrage ins Leere.
    """
    return "_".join(str(x) for x in match_key)


def erwartet_inbound_topic(quellen: dict, field_id: str) -> bool:
    """Erwartet eedc für dieses Feld einen Wert auf dem Standard-Inbound-Topic?

    **Nein**, sobald der Anwender eine andere Quelle GEWÄHLT hat — „Keine"
    oder einen HA-Sensor. Beides meldete der MQTT-Topic-Abdeckungs-Check
    bis v4.0.22 als „erwartet, nie empfangen" bzw. „veraltet" (#389, gruaGit):
    ein Hinweis auf ein Topic, auf das niemand publizieren soll.

    **Ein persistierter Eintrag ist immer eine bewusste Wahl.** Die
    3-Stufen-Auflösung schreibt bei stummem Inbound NICHTS fort
    (`resolve_effektive_quelle` liefert dort `persist_entry=None`) — genau
    der Fall, für den der Check gebaut wurde (#134), bleibt damit drin.
    Ohne Eintrag gilt wie bisher: Topic wird erwartet.

    **Gateway bleibt ebenfalls drin.** Der Gateway-Service re-publisht auf
    das EEDC-Inbound-Topic (`mqtt_gateway_service.py`), und der Slug-Teil im
    Subscriber-Regex ist optional — der Wert landet im selben Cache unter
    demselben Schlüssel. Ein stummes Gateway-Mapping ist deshalb eine echte
    Lücke und keine Fehlmeldung.

    Args:
        quellen: `anlage.sensor_mapping["quellen"]` (Feld-ID → Eintrag).
        field_id: Kennung aus `feld_id_aus_match_key`.
    """
    eintrag = quellen.get(field_id)
    if not isinstance(eintrag, dict):
        return True
    return eintrag.get("quelle") not in QUELLEN_OHNE_INBOUND_TOPIC
