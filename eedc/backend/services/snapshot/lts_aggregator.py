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
from datetime import date, datetime, timedelta
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
    wechsel: Optional[dict] = None,
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
       im PV-Aggregat-Fall die Träger-Auflösung (N-623: gemessene Erzeuger
       behalten ihren Tageswert, die übrigen teilen den Rest nach kWp,
       `pv_tages_praezedenz.loese_aggregat_tag_auf`). **E4**: der BKW-Key
       trägt Σ seines Rests (je Slot ≥ 0 geklemmt).

    ``zusatz_schluessel`` (N-555 Stufe 3, Konzept 7.2 Anhang D, D-6): weitere
    HA-Entities — die Heimlade-Zähler je Auto —, die **im selben Lesezugriff**
    mitgelesen und roh in ``TagesTabelle.zusatz_slots`` zurückgegeben werden. Die
    Rechnung der Tabelle sieht sie nicht (sie bekommt nur die Slots ihrer Einträge);
    ohne Zusatz ist alles bitgleich wie vorher.

    ``wechsel`` (Sensorwechsel mit Grund, B-0 «Zuordnung zum Zeitpunkt»; ``aggregate_day`` über
    ``wechsel_kwargs``): je Slot liest ein Zähler die Entität der Quelle, die zum Stand des Slots galt
    (``zuordnung_wechsel.anwenden.entitaet_je_slot``) — jeder Slot ist das Delta EINER Entität, ein Slot
    misst nie über eine Naht. Galt in einem Slot eine Quelle außerhalb von HA (MQTT, «keine», unbekannt)
    oder führt HA die frühere Entität nicht, liest der Tag nicht aus HA (``None`` ⇒ Snapshot-Pfad, dessen
    Reihe B-0 schützt). Ohne Wechsel bitgleich wie vorher.

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
    plan = _slot_plan(eintraege, wechsel, datum)
    if plan is None:
        return None
    zusatz = [z for z in dict.fromkeys(zusatz_schluessel or ()) if z not in eigene]
    # Sensorwechsel S2 (§8 Nr. 22 b): auch die Heimlade-Zähler je Auto lesen je Slot die Entität zum Stand.
    zplan = _zusatz_plan(anlage, investitionen_by_id, datum, zusatz, wechsel) if (wechsel and zusatz) else {}
    zusatz = [z for z in zusatz if zplan.get(z, {}) is not None]
    frueher = {eid for je_slot in (*plan.values(), *(p for p in zplan.values() if p)) for eid in je_slot.values()}
    dazu, null_ab = _naht_plan(eintraege, zusatz, anlage, investitionen_by_id, wechsel, datum) if wechsel else ({}, frozenset())
    sensor_ids = sorted(eigene | set(zusatz) | frueher | {eid for p in dazu.values() for eid in p.values()})
    reihen = await asyncio.to_thread(ha_svc.get_hourly_slots_for_day, sensor_ids, datum, *((null_ab,) if null_ab else ()))
    # Korrekturrunde Lab-K (F4): jede Ersetzung liest die Slots, wie HA sie führt — nie eine schon ersetzte Reihe. Ist die
    # frühere Entität eines Zählers die heutige eines anderen (Lab: P1b irrtümlich auf p3_alt, der frühere Sensor der
    # Wallbox), las die Wallbox sonst die Geschichte des PV-Felds (25.10. 9,0 statt 27,0).
    orig = dict(reihen)
    if plan and not _plan_anwenden(reihen, plan, orig=orig):
        return None
    _plan_anwenden(reihen, {z: p for z, p in zplan.items() if p and (z in reihen or set(p.values()) & set(reihen))},
                   streng=False, orig=orig)
    _dazu_anwenden(reihen, dazu, orig=orig)
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


#: Slots eines Tages im Backward-Raster (``SensorSlotReihe.slots`` 0..23; Slot h endet mit dem Stand um ``datum`` + h Stunden).
_SLOTS = range(24)


def _slot_plan(eintraege: list[TabellenEintrag], wechsel: Optional[dict], datum: date) -> Optional[dict]:
    """B-0 je Zähler: ``{heutige Entität: {slot: frühere Entität}}``; ``None`` ⇒ der Tag liest nicht aus HA."""
    from backend.services.zuordnung_wechsel.anwenden import entitaet_je_slot

    plan: dict[str, dict[int, str]] = {}
    je_entitaet: dict[str, dict[int, str]] = {}
    for e in eintraege:
        je_slot = entitaet_je_slot((wechsel or {}).get(e.sensor_key), e.schluessel, datum, _SLOTS)
        if je_slot is None:
            return None
        # Lab-K F4: zwei Zähler mit derselben heutigen Entität, aber verschiedener Geschichte am Tag — die Tabelle führt je
        # Entität eine Reihe; der Tag liest dann nicht aus HA (wie bei einer Quelle außerhalb von HA).
        if je_entitaet.setdefault(e.schluessel, je_slot) != je_slot:
            return None
        if je_slot:
            plan[e.schluessel] = je_slot
    return plan


def _plan_anwenden(reihen: dict, plan: dict[str, dict[int, str]], *, streng: bool = True,
                   orig: Optional[dict] = None) -> bool:
    """Setzt je Slot das Delta der früheren Entität in die Reihe der heutigen (in-place). ``False`` ⇒ HA führt eine
    frühere Entität nicht (dann bleibt der Tag beim Snapshot-Pfad). ``streng=False`` (Heimlade-Zähler, §8 Nr. 22 b): ein
    Slot einer früheren Entität, die HA nicht führt, fällt weg — nie das Delta der heutigen Entität für ihn. ``orig``
    (Lab-K F4): die Reihen, wie HA sie führt — gelesen wird nur aus ihnen, geschrieben in ``reihen``."""
    quelle = reihen if orig is None else orig
    for eid, je_slot in plan.items():
        if streng and any(alt not in quelle for alt in set(je_slot.values())):
            return False
        reihe = quelle.get(eid) or quelle[next(alt for alt in je_slot.values() if alt in quelle)]
        slots = dict(quelle[eid].slots) if eid in quelle else {}
        for h, alt in je_slot.items():
            if alt in quelle and h in quelle[alt].slots:
                slots[h] = quelle[alt].slots[h]
            else:
                slots.pop(h, None)
        reihen[eid] = reihe._replace(slots=slots)
    return True


def _naht_je_slot(liste, datum: date) -> tuple[dict[int, str], set[str]]:
    """U2 a1 (F6): ein angesetzter Wechsel «bleiben» **ohne Überlappung** (``ansatz = beide``, ``zeitpunkt.rand_versatz``)
    am Tag: ``{Naht-Slot: alte Entität}`` (der Slot mit dem Stand um ``ab_ts`` zählt den alten Sensor dazu) und die neue
    Entität (ihre erste Zeile zählt ab 0, wenn HA davor keine führt — ``get_hourly_slots_for_day(anker_null=…)``). Mit
    Überlappung (``schnitt``) gilt am Naht-Slot allein die neue Entität mit ihrem Anker (``_slot_plan``)."""
    from backend.models.zuordnung_wechsel import ANSATZ_BEIDE
    from backend.services.zuordnung_wechsel.zeitpunkt import rand_versatz

    null = datetime.combine(datum, datetime.min.time())
    dazu: dict[int, str] = {}
    neue: set[str] = set()
    for w in liste or ():
        if w.ansatz != ANSATZ_BEIDE or rand_versatz(w) is None:
            continue
        alt, neu = (w.vorher or {}).get("entity_id"), (w.nachher or {}).get("entity_id")
        h = next((h for h in _SLOTS if null + timedelta(hours=h) == w.ab_ts), None)
        if h is None or not alt or not neu:
            continue
        dazu[h] = alt
        neue.add(neu)
    return dazu, neue


def _naht_plan(eintraege: list[TabellenEintrag], zusatz: list[str], anlage, investitionen_by_id: dict, wechsel: dict,
               datum: date) -> tuple[dict[str, dict[int, str]], frozenset]:
    """``_naht_je_slot`` je Zähler des Tages (eigene und Heimlade-Zähler): ``{heutige Entität: {Naht-Slot: alte Entität}}``
    und die Entitäten mit Anker 0. Ohne angesetzten Wechsel leer — der Lesezugriff bleibt wörtlich der alte."""
    from backend.services.emob_ladebloecke_speicher import HEIM_GESAMT_FELD, fahrzeug_zaehler_lts

    schluessel = [(e.schluessel, e.sensor_key) for e in eintraege]
    if zusatz:
        inv_je_eid = fahrzeug_zaehler_lts(anlage, investitionen_by_id, datum)
        schluessel += [(eid, f"inv:{inv_je_eid[eid]}:{HEIM_GESAMT_FELD}") for eid in zusatz if eid in inv_je_eid]
    dazu: dict[str, dict[int, str]] = {}
    null_ab: set[str] = set()
    for eid, key in schluessel:
        je_slot, neue = _naht_je_slot(wechsel.get(key), datum)
        if je_slot:
            dazu[eid] = je_slot
            null_ab |= neue
    return dazu, frozenset(null_ab)


def _dazu_anwenden(reihen: dict, dazu: dict[str, dict[int, str]], *, orig: Optional[dict] = None) -> None:
    """U2 a1 (F6): am Naht-Slot zum Slot der neuen Entität den der alten (in-place) — die Stunde des Wechsels zählt beide
    Sensoren wie HA (``ha_statistics_service.StundenSlot``; die Summe über ``zaehler_naht.slot_beider``). Führt HA die alte
    im Fenster nicht, zählt nur die neue."""
    from backend.core.berechnungen.zaehler_naht import slot_beider
    from backend.services.ha_statistics_service import StundenSlot

    for eid, je_slot in dazu.items():
        if eid not in reihen:
            continue
        slots = dict(reihen[eid].slots)
        for h, alt in je_slot.items():
            quelle = reihen if orig is None else orig            # Lab-K F4: der alte Sensor, wie HA ihn führt
            alt_slot = quelle[alt].slots.get(h) if alt in quelle else None
            if alt_slot is None:
                continue
            neu = slots.get(h)
            slots[h] = alt_slot if neu is None else StundenSlot(*slot_beider(neu.delta, neu.n, alt_slot.delta, alt_slot.n))
        reihen[eid] = reihen[eid]._replace(slots=slots)


def _zusatz_plan(anlage, investitionen_by_id: dict, datum: date, zusatz: list[str],
                 wechsel: dict) -> dict[str, Optional[dict[int, str]]]:
    """B-0 für die Heimlade-Zähler je Auto (``zusatz_schluessel`` = heutige Entitäten): ``{Entität: {slot: frühere
    Entität}}``; ``None`` ⇒ in einem Slot galt eine Quelle außerhalb von HA — der Zähler wird an diesem Tag nicht gelesen."""
    from backend.services.emob_ladebloecke_speicher import HEIM_GESAMT_FELD, fahrzeug_zaehler_lts
    from backend.services.zuordnung_wechsel.anwenden import entitaet_je_slot

    inv_je_eid = fahrzeug_zaehler_lts(anlage, investitionen_by_id, datum)
    return {eid: entitaet_je_slot(wechsel.get(f"inv:{inv_je_eid[eid]}:{HEIM_GESAMT_FELD}"), eid, datum, _SLOTS)
            for eid in zusatz if eid in inv_je_eid}


async def wechsel_kwargs(db: AsyncSession, anlage_id: int) -> dict:
    """``{"wechsel": …}`` für ``lts_tagestabelle``, wenn die Anlage verzeichnete Wechsel hat — sonst ``{}`` (der Aufruf bleibt
    dann wörtlich der alte; Proben, die die Tabelle ersetzen, sehen kein neues Argument)."""
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    wechsel = await lade_wechsel(db, anlage_id)
    return {"wechsel": wechsel} if wechsel else {}


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
    tabelle = await lts_tagestabelle(anlage, investitionen_by_id, datum, **await wechsel_kwargs(db, anlage.id))
    return tabelle.stunden if tabelle is not None else {}


async def get_komponenten_tageskwh_lts(
    anlage,
    investitionen_by_id: dict,
    datum: date,
    *,
    marken_out: Optional[dict[str, str]] = None,
    wechsel: Optional[dict] = None,
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

    ``wechsel`` (Sensorwechsel S2, §8 Nr. 22 c): die verzeichneten Wechsel der Anlage (``wechsel_kwargs``) — der Tag liest
    je Slot die Entität zum Stand wie ``aggregate_day`` (B-0); die Aufrufer (Tag-Status, Daten-Checker) reichen sie durch.
    """
    tabelle = await lts_tagestabelle(anlage, investitionen_by_id, datum, **({"wechsel": wechsel} if wechsel else {}))
    if tabelle is None:
        return {}
    if marken_out is not None:
        marken_out.update(tabelle.pv_marken)
    return dict(tabelle.komponenten_kwh)
