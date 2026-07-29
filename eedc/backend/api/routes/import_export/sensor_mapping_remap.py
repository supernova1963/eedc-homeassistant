"""
JSON-Import — `sensor_mapping` auf die neu vergebenen Investitions-IDs umschreiben.

**Warum es das braucht.** Beim Import bekommen alle Investitionen neue IDs. Die
Komponenten-Zuordnung hängt an genau diesen IDs, und zwar an zwei Stellen:
`sensor_mapping["investitionen"]["{id}"]` (klassische Struktur, aus der alle
Aufzähl-Leser ihre Zähler holen) und `sensor_mapping["quellen"]` mit den
Feld-IDs `inv_energy_{id}_{feld}` / `inv_live_{id}_{key}` (Datenquellen-Fläche).

Bis Export-Version 1.2 trug die Datei die Quell-IDs nicht — der Import konnte die
Zuordnung deshalb nicht umschreiben und hat sie **verworfen**
(`imported_sensor_mapping["investitionen"] = {}`). Für den Anwender sah das wie
Datenverlust aus: ein Reimport der korrigierten Datei löschte eine vorher
funktionierende Speicher-Zuordnung mit (#353, coolxmad).

Ab Export-Version **1.3** trägt jede Investition ihre Quell-ID (`id`), und dieses
Modul schreibt beide Stellen um. Was sich nicht auflösen lässt (Komponente nicht
mit importiert, Alt-Datei ohne IDs), wird **verworfen statt stehengelassen**:
ein Eintrag unter einer ID, die es nicht mehr gibt, ist für die Aufzähl-Leser
tote Last — und die v4.0.3-Start-Migration würde ihn aus `quellen` sogar in
`investitionen` materialisieren (`datenquellen_mapping_sync._inv_eintrag` legt
den Teilbaum ungeprüft an).

Reine Funktion ohne DB-Zugriff — der Aufrufer ist für `flag_modified` + Commit
zuständig.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.datenquellen_mapping_sync import split_inv

# Feld-ID-Präfixe der Datenquellen-Fläche, die eine Investitions-ID tragen.
INV_PREFIXE = ("inv_energy_", "inv_live_")


@dataclass
class RemapBericht:
    """Was der Remap getan hat — Grundlage der Import-Warnung."""
    uebernommen: int = 0
    verworfen: list[str] = field(default_factory=list)

    @property
    def hat_verworfen(self) -> bool:
        return bool(self.verworfen)


def remap_investitionen_ids(
    mapping: dict, alt_zu_neu: dict[int, int],
) -> RemapBericht:
    """Schreibt `investitionen`-Schlüssel und `quellen`-Feld-IDs um (in-place).

    Args:
        mapping: `sensor_mapping` aus der Import-Datei (wird verändert).
        alt_zu_neu: Quell-ID → neu vergebene ID. Leer bei Export-Version < 1.3.

    Returns:
        Bericht mit Anzahl übernommener Zuordnungen und den verworfenen
        Schlüsseln (Komponenten-ID bzw. Feld-ID), für die Import-Warnung.
    """
    bericht = RemapBericht()
    if not isinstance(mapping, dict):
        return bericht

    _remap_investitionen(mapping, alt_zu_neu, bericht)
    _remap_quellen(mapping, alt_zu_neu, bericht)
    return bericht


def _remap_investitionen(
    mapping: dict, alt_zu_neu: dict[int, int], bericht: RemapBericht,
) -> None:
    investitionen = mapping.get("investitionen")
    if not isinstance(investitionen, dict):
        return

    neu: dict[str, object] = {}
    for alt_key, eintrag in investitionen.items():
        neue_id = _neue_id(alt_key, alt_zu_neu)
        if neue_id is None:
            bericht.verworfen.append(f"Komponente #{alt_key}")
            continue
        neu[str(neue_id)] = eintrag
        bericht.uebernommen += 1
    mapping["investitionen"] = neu


def _remap_quellen(
    mapping: dict, alt_zu_neu: dict[int, int], bericht: RemapBericht,
) -> None:
    quellen = mapping.get("quellen")
    if not isinstance(quellen, dict):
        return

    neu: dict[str, object] = {}
    for field_id, eintrag in quellen.items():
        prefix = next((p for p in INV_PREFIXE if str(field_id).startswith(p)), None)
        if prefix is None:
            neu[field_id] = eintrag  # `basis_*` trägt keine ID
            continue
        alt_id, rest = split_inv(field_id[len(prefix):])
        if alt_id is None:
            neu[field_id] = eintrag  # unbekannte Form: nicht anfassen
            continue
        neue_id = _neue_id(alt_id, alt_zu_neu)
        if neue_id is None:
            bericht.verworfen.append(field_id)
            continue
        neu[f"{prefix}{neue_id}_{rest}"] = eintrag
    mapping["quellen"] = neu


def _neue_id(alt_key: object, alt_zu_neu: dict[int, int]) -> int | None:
    """Schlüssel (str oder int) → neue ID; None, wenn nicht auflösbar."""
    try:
        return alt_zu_neu.get(int(alt_key))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
