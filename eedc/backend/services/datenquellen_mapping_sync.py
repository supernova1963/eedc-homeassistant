"""
Datenquellen-V4 — Quellen-Wahl in die klassische `sensor_mapping`-Struktur schreiben.

Gegenrichtung zu `migrations/migrate_datenquellen_materialisieren.py` (B8-1:
`basis`/`investitionen` → `quellen`) und Zwilling von
`datenquellen_wizard_sync.py` (V3-Wizard → V4-Stores). Zusammen bilden die drei
EINE Schreib-Schicht für zwei Oberflächen ([[feedback_bypass_kombi_schreib_schicht]]).

**Warum es sie braucht.** `quellen` wirkt bei allen Lesern nur als
*Read-Through*: `resolve_energy_snapshot_eid`/`resolve_energy_ha_eid` TAUSCHEN
die Entity eines Feldes, das der Aufrufer bereits aufgezählt hat. Die
Aufzählung selbst kommt überall aus `basis[feld]`/`investitionen[id].felder[feld]`
(Aggregator, LTS-Aggregator, Reaggregator, `ha_statistics`, Monatsabschluss-
Vorschläge, Daten-Checker) bzw. `basis["live"]`/`investitionen[id]["live"]`
(Tagesverlauf, Live-History, Energieprofil). Ein Feld, das NUR in `quellen`
steht, existiert für diese Stellen nicht — es wird nie aufgezählt, also auch nie
getauscht. Genau das traf Neuinstallationen ab v4.0.0: die Datenquellen-Fläche
zeigte den Sensor samt Live-Wert, der Daten-Checker meldete „Kein Basis-Zähler
für: Einspeisung, Netzbezug" und Cockpit/Tag/Monat blieben leer
(Forum simon42 #89667, Beiträge 36–41, Algie + CHI3fx117, 2026-07-28/29).

Der Fix schreibt bei jeder Quellen-Wahl beides: den Store (Herkunft des Wertes)
UND die klassische Struktur (welches Feld überhaupt einen HA-Sensor hat). Das
heilt alle Leser auf einen Schlag, statt ~18 Aufzählstellen einzeln
quellen-fähig zu machen ([[feedback_aggregations_drift]]).

Regeln:

- **HA-Quelle** (`ha_app`/`ha_connector`) mit `entity_id` → Energie-Feld bekommt
  `{"strategie": "sensor", "sensor_id": entity}`, Live-Feld den Eintrag in der
  `live`-Map. Bitgleich zu dem, was der V3-Wizard geschrieben hätte.
- **Jede andere Quelle** (Gateway, Inbound, `keine`) → ein vorhandener
  HA-Sensor-Eintrag wird geräumt (`{"strategie": "keine"}` bzw. Key raus). Das
  ist nicht bloß Kosmetik: bliebe er stehen, würde die B8-2-Auflösung beim
  nächsten `/felder`-Aufruf über Stufe 1 („HA-Sensor zugeordnet") wieder auf HA
  springen und die Wahl des Anwenders zurückdrehen.
- **Unbekannte Feld-IDs** ändern nichts (`False`) — die Fläche kennt Felder ohne
  Mapping-Gegenstück (z. B. `basis_energy_*` außerhalb der drei Basis-Zähler).
"""

from __future__ import annotations

from typing import Optional

# Basis-Energy-Feld-IDs → `basis`-Schlüssel des klassischen Mappings.
# `basis_energy_pv_gesamt_kwh` ist bewusst dabei, obwohl es KEIN Snapshot-
# Gegenstück hat (`snapshot/keys.py::_energy_field_id_to_sensor_key` liefert
# dafür None): `ha_statistics` und `aktueller_monat` lesen `basis["pv_gesamt"]`
# als Anlagen-Aggregat für den Monatsabschluss.
BASIS_ENERGY_FELD: dict[str, str] = {
    "pv_gesamt_kwh": "pv_gesamt",
    "einspeisung_kwh": "einspeisung",
    "netzbezug_kwh": "netzbezug",
}

# Basis-Preis-Feld-IDs → `basis`-Schlüssel. Getrennt von BASIS_ENERGY_FELD,
# weil diese Felder keine Zähler sind (kein Snapshot, kein MQTT-Topic, kein
# LTS-Summen-Check) — s. `BASIS_PREIS_FELDER` in field_definitions.py.
BASIS_PREIS_FELD: dict[str, str] = {
    "strompreis": "strompreis",
}

QUELLEN_HA = ("ha_app", "ha_connector")


def split_inv(rest: str) -> tuple[Optional[str], Optional[str]]:
    """`{inv_id}_{feld}` → (inv_id, feld); identisch zu `datenquellen_resolver`.

    Öffentlich, weil der JSON-Import dieselbe Zerlegung braucht, um die
    `quellen`-Feld-IDs auf die neu vergebenen Investitions-IDs umzuschreiben
    (`import_export/sensor_mapping_remap.py`, #353). Eine vierte Kopie der
    Prefix-Zerlegung wäre genau die Drift, gegen die dieses Modul gebaut ist.
    """
    inv_id, sep, feld = rest.partition("_")
    if not sep or not inv_id.isdigit() or not feld:
        return None, None
    return inv_id, feld


def uebernehme_quelle_ins_mapping(
    mapping: dict, field_id: str, quelle: str, entity_id: Optional[str],
) -> bool:
    """Schreibt die Quellen-Wahl EINES Feldes in `basis`/`investitionen`.

    Args:
        mapping: `anlage.sensor_mapping` (wird in-place verändert).
        field_id: Feld-Kennung der Fläche (`basis_energy_*`, `basis_live_*`,
            `basis_preis_*`, `inv_energy_{id}_{feld}`, `inv_live_{id}_{key}`).
        quelle: Wire-Wert der gewählten Quelle.
        entity_id: HA-Entity — nur bei HA-Quellen gesetzt.

    Returns:
        True, wenn `mapping` verändert wurde. Der Aufrufer ist für
        `flag_modified` + `commit` zuständig.
    """
    if not isinstance(mapping, dict) or not isinstance(field_id, str):
        return False

    ist_ha = quelle in QUELLEN_HA and bool(entity_id)

    if field_id.startswith("basis_energy_"):
        feld = BASIS_ENERGY_FELD.get(field_id[len("basis_energy_"):])
        if feld is None:
            return False
        basis = _teilbaum(mapping, "basis", anlegen=ist_ha)
        if basis is None:
            return False
        return _setze_energie(basis, feld, ist_ha, entity_id)

    if field_id.startswith("basis_live_"):
        basis = _teilbaum(mapping, "basis", anlegen=ist_ha)
        if basis is None:
            return False
        live = _teilbaum(basis, "live", anlegen=ist_ha)
        if live is None:
            return False
        return _setze_live(live, field_id[len("basis_live_"):], ist_ha, entity_id)

    # Preis-Felder (`BASIS_PREIS_FELDER`) liegen wie die Energie-Felder direkt
    # unter `basis`, teilen aber deren MQTT-Maschinerie NICHT: sie werden nur
    # als HA-Sensor gelesen. Derselbe Eintrags-Shape (`strategie`/`sensor_id`),
    # damit `energie_profil/_helpers.py` sie unverändert findet — der Slot ist
    # die Rückkehr des v3-Wizard-Feldes, kein neues Format.
    if field_id.startswith("basis_preis_"):
        feld = BASIS_PREIS_FELD.get(field_id[len("basis_preis_"):])
        if feld is None:
            return False
        basis = _teilbaum(mapping, "basis", anlegen=ist_ha)
        if basis is None:
            return False
        return _setze_energie(basis, feld, ist_ha, entity_id)

    if field_id.startswith("inv_energy_"):
        inv_id, feld = split_inv(field_id[len("inv_energy_"):])
        if inv_id is None:
            return False
        inv = _inv_eintrag(mapping, inv_id, anlegen=ist_ha)
        if inv is None:
            return False
        felder = _teilbaum(inv, "felder", anlegen=ist_ha)
        if felder is None:
            return False
        return _setze_energie(felder, feld, ist_ha, entity_id)

    if field_id.startswith("inv_live_"):
        inv_id, key = split_inv(field_id[len("inv_live_"):])
        if inv_id is None:
            return False
        inv = _inv_eintrag(mapping, inv_id, anlegen=ist_ha)
        if inv is None:
            return False
        live = _teilbaum(inv, "live", anlegen=ist_ha)
        if live is None:
            return False
        return _setze_live(live, key, ist_ha, entity_id)

    return False


def _teilbaum(container: dict, key: str, *, anlegen: bool) -> Optional[dict]:
    """Dict-Teilbaum holen; legt ihn nur an, wenn wirklich etwas zu setzen ist —
    eine Nicht-HA-Wahl darf kein leeres `{"basis": {}}` hinterlassen."""
    wert = container.get(key)
    if isinstance(wert, dict):
        return wert
    if not anlegen:
        return None
    wert = {}
    container[key] = wert
    return wert


def _inv_eintrag(mapping: dict, inv_id: str, *, anlegen: bool) -> Optional[dict]:
    """`investitionen[inv_id]`-Teilbaum; legt ihn nur bei HA-Zuordnung an."""
    investitionen = _teilbaum(mapping, "investitionen", anlegen=anlegen)
    if investitionen is None:
        return None
    return _teilbaum(investitionen, inv_id, anlegen=anlegen)


def _setze_energie(
    container: dict, feld: str, ist_ha: bool, entity_id: Optional[str],
) -> bool:
    """Energie-Feld: `{"strategie": "sensor", "sensor_id": …}` bzw. räumen."""
    vorher = container.get(feld)
    if ist_ha:
        neu = {"strategie": "sensor", "sensor_id": entity_id}
        # Zusatz-Parameter eines bestehenden Eintrags (z. B. Zähler-Parameter
        # aus dem V3-Wizard) überleben den Sensor-Wechsel.
        if isinstance(vorher, dict) and vorher.get("parameter") is not None:
            neu["parameter"] = vorher["parameter"]
        if vorher == neu:
            return False
        container[feld] = neu
        return True
    # Nicht-HA: einen vorhandenen Sensor-Eintrag entwerten, sonst nichts anlegen.
    if not isinstance(vorher, dict) or vorher.get("strategie") != "sensor":
        return False
    container[feld] = {"strategie": "keine"}
    return True


def _setze_live(live: dict, key: str, ist_ha: bool, entity_id: Optional[str]) -> bool:
    """Live-Feld: Eintrag in der `live`-Map setzen bzw. entfernen."""
    if ist_ha:
        if live.get(key) == entity_id:
            return False
        live[key] = entity_id
        return True
    if not live.get(key):
        return False
    live.pop(key, None)
    return True
