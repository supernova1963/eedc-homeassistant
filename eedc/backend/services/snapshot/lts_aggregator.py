"""
HA-LTS-basierte Variante von `get_hourly_kwh_by_category` (Etappe 4 v3.31.0).

Liest Stunden-kWh-Deltas direkt aus HA-Statistics-LTS (`statistics`-Tabelle)
und liefert dieselbe Output-Form wie `services.snapshot.aggregator.
get_hourly_kwh_by_category` — damit der Aufrufer (`services.energie_profil.
aggregator.aggregate_day`) nur den Datenherkunft-Switch braucht, nicht
die nachgelagerte Verarbeitung anpassen.

Unterschied zur Snapshot-Variante:
  - Quelle: HA-LTS-Statistics direkt (kein sensor_snapshots-Zwischenschritt)
  - Schreib-Provenance: `external:ha_statistics:hourly` (Caller setzt das)
  - Konsistent mit `external:ha_statistics:daily` für TagesZusammenfassung
    (Caller summiert die Stunden-Deltas für Daily, beide aus derselben Quelle)
  - Standalone-Modus (MQTT) wird NICHT bedient — dafür bleibt die
    Snapshot-Variante (`get_hourly_kwh_by_category`) als Fallback

Konzept-Doc: `docs/archive/KONZEPT-ETAPPE-4-HA-LTS-SOT.md`.

⭐ **Seit „Zählerlücken wie HA" (Vorlage Fassung 7, R2–R5) ein Pfad für Stunde
und Tag.** `lts_tagestabelle` liest HA **einmal** je Tag über die Slot-Tabelle
(`ha_statistics_service.get_hourly_slots_for_day`) und leitet daraus beides ab:
die Stundenachsen (mit Spanne je Achse) **und** `komponenten_kwh` als Σ der in
den Stunden verwendeten Gerätewerte. Σ Stunden == `komponenten_kwh` gilt damit
per Konstruktion für PV+BKW, Wärmepumpe, Wallbox+E-Auto, Batterie, Einspeisung
und Netzbezug. `get_hourly_kwh_by_category_lts` und `get_komponenten_tageskwh_lts`
bleiben als dünne Wrapper für ihre Aufrufer stehen.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.ha_statistics_service import get_ha_statistics_service
from backend.services.snapshot.keys import (
    _categorize_counter,
    extract_quellen_energy,
    resolve_energy_ha_eid,
)
from backend.services.snapshot.komponenten_beitraege import (
    basis_beitraege,
    investition_beitraege,
    wallbox_deckt_ladung_ab,
)
from backend.services.snapshot.tages_tabelle import (
    TabellenEintrag,
    TagesTabelle,
    baue_tagestabelle,
)

#: Rückwärtskompatibler Name (Proben, Aufrufer): dieselbe Tabelle.
LtsTagesTabelle = TagesTabelle

logger = logging.getLogger(__name__)


def _lts_eintraege(anlage, investitionen_by_id: dict, datum: date) -> list[TabellenEintrag]:
    """Die zugeordneten Zähler des Tages — **eine** Auswahl für Stunde und Tag.

    Die Feld-Auswahl (Whitelist · Either-Or · Parent-Skip · K3 · Wallbox-Regel)
    kommt aus der Beitragsschicht (`basis_beitraege`/`investition_beitraege`),
    die Kategorie aus `_categorize_counter`. Bis zum Umbau gab es dafür zwei
    Listen (`*_hourly_eintraege` für die Stunde, `*_beitraege` für den Tag) —
    dieselbe Auswahl, zweimal gelesen; die Stunde ließ Felder ohne Kategorie
    weg (vor E3 die Betriebsart-Zähler), der Tag nicht.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through (HA-only-Pfad)
    out: list[TabellenEintrag] = []

    basis = sensor_mapping.get("basis", {}) or {}
    for b in basis_beitraege(sensor_mapping):
        cfg = basis.get(b.feld)
        if not isinstance(cfg, dict) or not cfg.get("sensor_id"):
            continue
        eid, behalten = resolve_energy_ha_eid(quellen_energy, f"basis:{b.feld}", cfg["sensor_id"])
        kat = _categorize_counter(b.feld, None, None)
        if behalten and eid and kat:
            out.append(TabellenEintrag(eid, kat, b.fallback_gruppe, f"basis:{b.feld}",
                                   b.target_key, b.vorzeichen))

    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    # N-196/N-555 (Konzept Regel 6): strukturelle Wallbox-Regel, einmal je Lauf.
    _wb_deckt = wallbox_deckt_ladung_ab(
        investitionen_by_id.values(), sensor_mapping, datum=datum,
    )
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        felder = inv_data.get("felder", {}) or {}
        for b in investition_beitraege(inv, inv_data, wallbox_deckt_ladung=_wb_deckt):
            cfg = felder.get(b.feld)
            if not isinstance(cfg, dict) or not cfg.get("sensor_id"):
                continue
            eid, behalten = resolve_energy_ha_eid(
                quellen_energy, f"inv:{inv_id_str}:{b.feld}", cfg["sensor_id"],
            )
            kat = _categorize_counter(b.feld, getattr(inv, "typ", None), getattr(inv, "parameter", None))
            if not (behalten and eid):
                continue
            if not kat:
                logger.warning(
                    "Anlage %s, %s: Feld %s (inv %s) hat keine Energiefluss-Kategorie "
                    "— zählt weder in der Stunde noch im Tag",
                    anlage.id, datum, b.feld, inv_id_str,
                )
                continue
            out.append(TabellenEintrag(eid, kat, b.fallback_gruppe, f"inv:{inv_id_str}:{b.feld}",
                                   b.target_key, b.vorzeichen))
    return out


async def lts_tagestabelle(
    anlage,
    investitionen_by_id: dict,
    datum: date,
    *,
    zusatz_schluessel: Iterable[str] = (),
) -> Optional[TagesTabelle]:
    """Stunden **und** Tag eines Tages aus der HA-Slot-Tabelle (R2–R5).

    Ablauf (Vorlage Fassung 7):

    1. Eine Auswahl der Zähler (`_lts_eintraege`), ein HA-Lesezugriff
       (`get_hourly_slots_for_day`, im Thread — der Recorder ist synchron).
    Die Schritte 2–7 rechnet `tages_tabelle.baue_tagestabelle` — dieselbe
    Funktion wie im Snapshot-Pfad (Standalone), keine zweite Fassung.

    2. Either-Or je Tag (`resolve_either_or_eintraege`): je Gruppe der erste
       Zähler mit mindestens einem belegten Slot.
    3. Je Sensor-Slot: **R4** negatives Delta ⇒ verworfen (Betrag nach
       ``verworfen[achse]``); **R3** auf pv/einspeisung Deckel
       ``kwp × 1,5 × n`` je Sensor-Slot.
    4. PV-Präzedenz je Tag (`waehle_pv_quelle`), BKW-Rest je Slot
       (`bkw_restwerte`) — unverändert.
    5. **R3** Deckel auf die Achsensumme der Stunde (pv inkl. Sonstiges-
       Erzeuger, einspeisung) mit der Achsen-Spanne; fällt die Summe, fallen
       alle Sensor-Slots dieser Stunde — auch aus `komponenten_kwh`.
    6. Achsen-Spanne = max n der verwendeten Sensor-Slots, gespeichert nur für
       n > 1. **R6**: Verbrauch nur bei gleicher Spanne von pv/netzbezug/
       einspeisung; Batterie mit anderer Spanne ⇒ `None`, fehlend ⇒ 0.
    7. **R5b** `komponenten_kwh` = Σ der verwendeten Gerätewerte je Ziel-Key;
       nur im PV-Aggregat-Fall `loese_pv_tageswerte_auf`. **E4**: im
       Einzelfall trägt der BKW-Key Σ seines Rests (je Slot ≥ 0 geklemmt).

    ``zusatz_schluessel`` (N-555 Stufe 3, Konzept 7.2 Anhang D, D-6): weitere
    HA-Entities — die Heimlade-Zähler je Auto —, die **im selben Lesezugriff**
    mitgelesen und roh in ``TagesTabelle.zusatz_slots`` zurückgegeben werden. Die
    Rechnung der Tabelle sieht sie nicht (sie bekommt nur die Slots ihrer Einträge);
    ohne Zusatz ist alles bitgleich wie vorher.

    Returns:
        ``None``, wenn HA nicht erreichbar ist, kein Zähler zugeordnet ist oder
        HA für keinen davon eine Zeile im Fenster hat — der Aufrufer fällt
        dann auf den Snapshot-Pfad zurück.
    """
    ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        return None
    eintraege = _lts_eintraege(anlage, investitionen_by_id, datum)
    if not eintraege:
        return None

    eigene = {e.schluessel for e in eintraege}
    zusatz = [z for z in dict.fromkeys(zusatz_schluessel or ()) if z not in eigene]
    sensor_ids = sorted(eigene | set(zusatz))
    reihen = await asyncio.to_thread(ha_svc.get_hourly_slots_for_day, sensor_ids, datum)
    # Nur die eigenen Zähler entscheiden, ob HA den Tag trägt — ein Zusatz-Zähler
    # allein darf den Rückfall auf den Snapshot-Pfad nicht verhindern.
    if not reihen or not any(eid in eigene for eid in reihen):
        return None

    tabelle = baue_tagestabelle(
        anlage, investitionen_by_id, datum, eintraege,
        {
            eid: {h: (slot.delta, slot.n) for h, slot in reihe.slots.items()}
            for eid, reihe in reihen.items()
            if eid in eigene
        },
    )
    tabelle.zusatz_slots = {
        eid: {h: (slot.delta, slot.n) for h, slot in reihen[eid].slots.items()}
        for eid in zusatz if eid in reihen
    }
    return tabelle


async def get_hourly_kwh_by_category_lts(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[int, dict[str, Optional[float]]]:
    """Stündliche kWh je Energiefluss-Kategorie aus HA-LTS — Wrapper über
    `lts_tagestabelle` (Format wie `snapshot.aggregator.get_hourly_kwh_by_category`,
    dazu ``spannen`` je Stunde). ``{}``, wenn HA nichts liefert — der Aufrufer
    fällt dann auf den Snapshot-Pfad zurück."""
    tabelle = await lts_tagestabelle(anlage, investitionen_by_id, datum)
    return tabelle.stunden if tabelle is not None else {}


async def get_komponenten_tageskwh_lts(
    anlage,
    investitionen_by_id: dict,
    datum: date,
    *,
    marken_out: Optional[dict[str, str]] = None,
) -> dict[str, float]:
    """Tages-kWh je Komponente aus HA-LTS — **dünner Wrapper** über
    `lts_tagestabelle` (R5, W3: fünf Aufrufer — Tag-Status, drei Daten-Checker,
    Migration).

    Key-Konvention unverändert (`einspeisung` · `netzbezug` · `pv_<id>` ·
    `bkw_<id>` · `batterie_<id>` (Entladung − Ladung) · `waermepumpe_<id>` ·
    `wallbox_<id>` · `eauto_<id>` · `sonstige_<id>`).

    ⭐ Seit „Zählerlücken wie HA" ist der Wert Σ der in den **Stunden
    verwendeten** Gerätewerte desselben Laufs: inklusive der Energie einer
    Lücke (sie steht im nächsten belegten Slot), ohne verworfene Mengen (R3/R4),
    BKW-Key = Σ Rest (E4). Σ Hourly == Daily damit exakt statt nur „aus
    derselben Quelle". Investitionen ohne Wert erscheinen nicht im Dict.
    """
    tabelle = await lts_tagestabelle(anlage, investitionen_by_id, datum)
    if tabelle is None:
        return {}
    if marken_out is not None:
        marken_out.update(tabelle.pv_marken)
    return dict(tabelle.komponenten_kwh)
