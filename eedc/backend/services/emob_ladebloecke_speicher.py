"""Ladeblöcke ablegen und lesen — N-555 Stufe 3 (Konzept 7.2 Regel 9, Anhang D).

Die Rechnung steht in ``emob_ladebloecke.py`` (rein). Hier:

* **Welche Zähler** (D-5): eine private Wallbox mit Ladezähler in Betrieb **und** ein E-Auto mit
  Quelle an „Heim: gesamt" (``ladung_kwh``) — auch ein einzelnes Auto. Ohne Wallbox-Zähler greift
  Stufe 3 nicht („Wo es nicht greift"). Dienstwagen gehören dazu: ihr Sprung begrenzt den Block
  des Vorgängers (Regel 9 Punkt 2, „irgendeines Autos"), und ihre gemessene Ladung ist nach
  Regel 3 die dienstliche.
* **Der Hook** (S3-3): ``aktualisiere_ladebloecke_des_tages`` läuft in ``aggregate_day`` direkt
  nach ``lade_zaehler_und_counter``. Die Wallbox-Stunden von D kommen aus der ``TagesTabelle``
  des Tages, die Fahrzeug-Slots aus demselben HA-Lesezugriff (``zusatz_slots``, D-6), die
  Stunden von D−1 aus den gespeicherten ``TagesEnergieProfil``-Zeilen, der vorige Sprung aus
  den gespeicherten Blöcken. Kein zweiter HA-Zugriff.
* **Der Leser** (S3-4) steht in ``energie_profil/monats_aus_tagen.py::emob_je_auto``.

**Idempotenz (P9):** je Tag werden die Blöcke ersetzt, deren Sprung an D liegt
(``ende`` ∈ [D 00:00, D 23:00]). Benannte Reihenfolge-Abhängigkeit (D-6): wird D neu gerechnet,
nachdem D+1 schon Blöcke hat, bleibt D+1 bei seiner damaligen Restmenge der gemeinsamen Stunde —
das ändert Anteil und Monatsverteilung, nie die Menge.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import batterie_kw_spalte
from backend.core.berechnungen.spannen import spanne
from backend.models.emob_ladeblock import EmobLadeblock
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.emob_ladebloecke import (
    REGEL_SPRUNG_RUECKWAERTS,
    BlockStunde,
    FahrzeugSprung,
    Ladeblock,
    WallboxStunde,
    bilde_ladebloecke,
    anteile_der_stunde,
    stunden_beginn,
)

logger = logging.getLogger(__name__)

#: Quelle-Marke je Pfad (``emob_ladebloecke.quelle``).
QUELLE_HA = "ha_statistics"
QUELLE_SNAPSHOT = "snapshot"

#: Das Feld „Heim: gesamt" am E-Auto (Regel 8, E5: der bestehende Schlüssel).
HEIM_GESAMT_FELD = "ladung_kwh"


def _eautos(invs_by_id: dict) -> list:
    return [i for i in invs_by_id.values() if getattr(i, "typ", None) == "e-auto"]


def fahrzeug_zaehler_lts(anlage, invs_by_id: dict, datum: date) -> dict[str, int]:
    """HA-Pfad: ``{entity_id: inv_id}`` der Heimlade-Zähler je Auto — leer ohne Wallbox-Zähler."""
    from backend.services.snapshot.keys import extract_quellen_energy, resolve_energy_ha_eid
    from backend.services.snapshot.komponenten_beitraege import (
        _is_sensor_mapping,
        wallbox_deckt_ladung_ab,
    )

    mapping = anlage.sensor_mapping or {}
    if not wallbox_deckt_ladung_ab(invs_by_id.values(), mapping, datum=datum):
        return {}
    quellen_energy = extract_quellen_energy(anlage)
    inv_map = mapping.get("investitionen") or {}
    out: dict[str, int] = {}
    for inv in _eautos(invs_by_id):
        cfg = ((inv_map.get(str(inv.id)) or {}).get("felder") or {}).get(HEIM_GESAMT_FELD)
        if not _is_sensor_mapping(cfg):
            continue
        eid, behalten = resolve_energy_ha_eid(
            quellen_energy, f"inv:{inv.id}:{HEIM_GESAMT_FELD}", cfg.get("sensor_id"),
        )
        if behalten and eid:
            out[eid] = inv.id
    return out


async def fahrzeug_zaehler_snapshot(
    db: AsyncSession, anlage, invs_by_id: dict, datum: date,
) -> dict[str, tuple[int, Optional[str]]]:
    """Snapshot-Pfad: ``{sensor_key: (inv_id, entity_id)}`` — HA-Sensor **oder** MQTT."""
    from backend.services.snapshot.keys import extract_quellen_energy, feld_hat_zaehler
    from backend.services.snapshot.komponenten_beitraege import wallbox_deckt_ladung_ab
    from backend.services.snapshot.reader import mqtt_zaehler_keys

    mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)
    inv_map = mapping.get("investitionen") or {}

    def _cfg(inv, feld):
        return ((inv_map.get(str(inv.id)) or {}).get("felder") or {}).get(feld)

    if not wallbox_deckt_ladung_ab(
        invs_by_id.values(), mapping,
        ist_verfuegbar=lambda inv, feld: feld_hat_zaehler(
            _cfg(inv, feld), f"inv:{inv.id}:{feld}", quellen_energy, mqtt_keys,
        ),
        datum=datum,
    ):
        return {}
    out: dict[str, tuple[int, Optional[str]]] = {}
    for inv in _eautos(invs_by_id):
        sk = f"inv:{inv.id}:{HEIM_GESAMT_FELD}"
        cfg = _cfg(inv, HEIM_GESAMT_FELD)
        if feld_hat_zaehler(cfg, sk, quellen_energy, mqtt_keys):
            out[sk] = (inv.id, cfg.get("sensor_id") if isinstance(cfg, dict) else None)
    return out


def _stunde(beginn: datetime, *, ladung, netzbezug, einspeisung, batterie_spalte,
            spannen) -> WallboxStunde:
    gebuendelt = any(spanne(spannen, a) > 1 for a in ("wallbox", "pv", "netzbezug"))
    pv_anteil, speicher_anteil = anteile_der_stunde(
        ladung=ladung, netzbezug=netzbezug, einspeisung=einspeisung,
        batterie_spalte=batterie_spalte, gebuendelt=gebuendelt,
    )
    return WallboxStunde(
        beginn=beginn,
        kwh=float(ladung),
        n=spanne(spannen, "wallbox"),
        pv_anteil=pv_anteil,
        speicher_anteil=speicher_anteil,
    )


def wallbox_stunden_aus_tabelle(datum: date, stunden: dict) -> list[WallboxStunde]:
    """Die Wallbox-Stunden von D aus der Tagestabelle (Achse ``wallbox``, R2-Spannen)."""
    out: list[WallboxStunde] = []
    for h, s in sorted((stunden or {}).items()):
        ladung = s.get("wallbox")
        if ladung is None or ladung <= 0:
            continue
        out.append(_stunde(
            stunden_beginn(datum, h), ladung=ladung, netzbezug=s.get("netzbezug"),
            einspeisung=s.get("einspeisung"),
            batterie_spalte=batterie_kw_spalte(s.get("batterie_netto")),
            spannen=s.get("spannen"),
        ))
    return out


async def wallbox_stunden_gespeichert(
    db: AsyncSession, anlage_id: int, datum: date,
) -> list[WallboxStunde]:
    """Die Wallbox-Stunden eines gespeicherten Tages (``TagesEnergieProfil``, Spalten-Konvention)."""
    rows = (await db.execute(
        select(TagesEnergieProfil).where(and_(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == datum,
        ))
    )).scalars().all()
    out: list[WallboxStunde] = []
    for r in sorted(rows, key=lambda r: r.stunde):
        if r.wallbox_kw is None or r.wallbox_kw <= 0:
            continue
        out.append(_stunde(
            stunden_beginn(datum, r.stunde), ladung=r.wallbox_kw, netzbezug=r.netzbezug_kw,
            einspeisung=r.einspeisung_kw, batterie_spalte=r.batterie_kw, spannen=r.spannen,
        ))
    return out


def ladeblock_aus_zeile(z: EmobLadeblock) -> Ladeblock:
    """Eine gespeicherte Zeile zurück in einen ``Ladeblock``."""
    stunden = tuple(
        BlockStunde(
            beginn=datetime.fromisoformat(s["beginn"]),
            kwh=float(s["kwh"]),
            n=int(s.get("n") or 1),
            pv_anteil=s.get("pv_anteil"),
            speicher_anteil=s.get("speicher_anteil"),
        )
        for s in (z.stunden or [])
    )
    return Ladeblock(
        inv_id=z.investition_id, beginn=z.beginn, ende=z.ende, kwh=z.kwh, pv_kwh=z.pv_kwh,
        stunden=stunden, stunden_gedeckt=z.stunden_gedeckt, luecke=bool(z.luecke),
        speicher_kwh=z.speicher_kwh,
    )


def _tagesgrenzen(datum: date) -> tuple[datetime, datetime]:
    """``ende`` der Sprünge von D liegt in [D 00:00, D 23:00] (Slot 0…23)."""
    d0 = datetime(datum.year, datum.month, datum.day)
    return d0, d0 + timedelta(hours=23)


async def aktualisiere_ladebloecke_des_tages(
    db: AsyncSession,
    anlage,
    datum: date,
    invs_by_id: dict,
    tages_tabelle,
    kwh_source_label: str,
) -> Optional[list[Ladeblock]]:
    """Der Stufe-3-Hook (S3-3): Blöcke der Sprünge an D bilden und ersetzen.

    Returns:
        Die geschriebenen Blöcke, ``None``, wenn Stufe 3 für die Anlage an D nicht greift.
    """
    if tages_tabelle is None:
        return None
    ist_lts = kwh_source_label == "external:ha_statistics:hourly"
    if ist_lts:
        inv_je_schluessel = fahrzeug_zaehler_lts(anlage, invs_by_id, datum)
    else:
        inv_je_schluessel = {
            k: v[0] for k, v in (await fahrzeug_zaehler_snapshot(db, anlage, invs_by_id, datum)).items()
        }
    von, bis = _tagesgrenzen(datum)
    alte = delete(EmobLadeblock).where(and_(
        EmobLadeblock.anlage_id == anlage.id,
        EmobLadeblock.ende >= von,
        EmobLadeblock.ende <= bis,
    ))
    if not inv_je_schluessel:
        await db.execute(alte)
        return None

    spruenge: list[FahrzeugSprung] = []
    for schluessel, slots in (tages_tabelle.zusatz_slots or {}).items():
        inv_id = inv_je_schluessel.get(schluessel)
        if inv_id is None:
            continue
        for h, (delta, _n) in slots.items():
            if 0 <= h <= 23 and round(delta, 3) > 0:  # R4: ein Rücksprung ist kein Sprung
                spruenge.append(FahrzeugSprung(inv_id, stunden_beginn(datum, h), round(delta, 3)))

    # Fenster: Stunden von D−1 (gespeichert) und D (Tabelle); der vorige Sprung und die schon
    # vergebene Energie aus den gespeicherten Blöcken, deren Sprung davor liegt.
    fenster_beginn = stunden_beginn(datum - timedelta(days=1), 0)
    stunden = [
        *await wallbox_stunden_gespeichert(db, anlage.id, datum - timedelta(days=1)),
        *wallbox_stunden_aus_tabelle(datum, tages_tabelle.stunden),
    ]
    frueher = (await db.execute(
        select(EmobLadeblock).where(and_(
            EmobLadeblock.anlage_id == anlage.id,
            EmobLadeblock.ende > fenster_beginn,
            EmobLadeblock.ende < von,
        ))
    )).scalars().all()
    schon_genommen: dict[datetime, float] = {}
    for z in frueher:
        for s in ladeblock_aus_zeile(z).stunden:
            schon_genommen[s.beginn] = schon_genommen.get(s.beginn, 0.0) + s.kwh
    voriger = max((z.ende for z in frueher), default=None)
    voriger_sprung = voriger - timedelta(hours=1) if voriger is not None else fenster_beginn

    bloecke = bilde_ladebloecke(
        stunden, spruenge, schon_genommen=schon_genommen, voriger_sprung=voriger_sprung,
    )
    await db.execute(alte)
    quelle = QUELLE_HA if ist_lts else QUELLE_SNAPSHOT
    for b in bloecke:
        db.add(EmobLadeblock(
            anlage_id=anlage.id,
            investition_id=b.inv_id,
            beginn=b.beginn,
            ende=b.ende,
            kwh=b.kwh,
            pv_kwh=b.pv_kwh,
            netz_kwh=None if b.netz_kwh is None else round(b.netz_kwh, 3),
            stunden=[
                {"beginn": s.beginn.isoformat(), "kwh": round(s.kwh, 4), "n": s.n,
                 "pv_anteil": None if s.pv_anteil is None else round(s.pv_anteil, 4),
                 "speicher_anteil": None if s.speicher_anteil is None else round(s.speicher_anteil, 4)}
                for s in b.stunden
            ],
            stunden_gedeckt=b.stunden_gedeckt,
            luecke=b.luecke,
            speicher_kwh=b.speicher_kwh,
            regel=REGEL_SPRUNG_RUECKWAERTS,
            quelle=quelle,
        ))
    await db.flush()
    return bloecke
