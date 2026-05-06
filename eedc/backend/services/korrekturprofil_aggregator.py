"""
Korrekturprofil-Aggregator.

Berechnet pro Anlage drei Lernfaktor-Profile (siehe
docs/KONZEPT-KORREKTURPROFIL.md):

1. `sonnenstand_wetter` — Faktor pro `(azimut_bin, elevation_bin, wetterklasse)`
2. `sonnenstand` — Faktor pro `(azimut_bin, elevation_bin)` als Fallback
3. `skalar` — O1+O2-Skalar als letzter Fallback

Datenquelle:
- Tages-Day-Ahead-Snapshot `TagesZusammenfassung.pv_prognose_stundenprofil`
  (24 Werte in kWh, vor Sonnenaufgang gefroren)
- Stündliches IST `TagesEnergieProfil.pv_kw` (Stundenmittel in kW, numerisch
  = kWh pro Stunden-Slot)
- Stündliches Wetter `TagesEnergieProfil.bewoelkung_prozent / niederschlag_mm
  / wetter_code` (Päckchen 1 + Backfill)

Filter pro Stunde:
- `pv_kw >= MIN_LEISTUNG_KW` und `prognose_kwh >= MIN_LEISTUNG_KW`
  (Nacht/Mess-Schwelle)
- Sonnenstand-Elevation > 0 (sonst nicht-klassifizierbar)
- Wetterklasse vorhanden für `sonnenstand_wetter`-Stufe
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.korrekturprofil import (
    PROFIL_TYP_SKALAR,
    PROFIL_TYP_SONNENSTAND,
    PROFIL_TYP_SONNENSTAND_WETTER,
    Korrekturprofil,
)
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.wetter.solar_position import (
    AZIMUT_BIN_BREITE_DEFAULT,
    ELEVATION_BIN_BREITE_DEFAULT,
    bin_key,
    solar_position_lokal,
)
from backend.services.wetter.utils import WETTERKLASSEN, klassifiziere_stunde
from backend.services.korrekturprofil_lookup import invalidate_cache

logger = logging.getLogger(__name__)


# Pro-Stunde-Filter — analog Stratifizierungs-Endpoint, kein Doppel-Standard
MIN_LEISTUNG_KW = 0.05

# Lookback-Tiefe Default — 2 Jahre passt zum Wetter-Backfill
DEFAULT_LOOKBACK_TAGE = 730

# Clamp-Bereich für Korrekturfaktoren — analog Skalar-Lernfaktor
FAKTOR_CLAMP_MIN = 0.5
FAKTOR_CLAMP_MAX = 1.3


def _clamp(faktor: float) -> float:
    return max(FAKTOR_CLAMP_MIN, min(FAKTOR_CLAMP_MAX, faktor))


def _produktionsgewichtet(sum_ist: float, sum_prog: float) -> Optional[float]:
    """Σ(IST) / Σ(Prognose) mit Stabilitäts-Schwelle.

    Liefert `None` wenn Σ(Prognose) zu gering ist, damit Bins ohne
    nennenswerte Prognose nicht durch Mini-Quotienten verzerrt werden.
    """
    if sum_prog < 1.0:  # 1 kWh Mindest-Summe pro Bin
        return None
    return sum_ist / sum_prog


# ── Tages-Quotient für Skalar-Aggregator ──────────────────────────────────

def _aggregate_skalar_o12(
    daten: list[tuple[date, float, float]],
    heute: date,
) -> tuple[Optional[float], int]:
    """O1+O2 — identische Formel wie live_wetter._aggregiere_o12, aber
    eigenständig, damit der Aggregator-Job keine API-Route importiert.

    Eingabe: Liste `(datum, ist_kwh, prog_kwh)` pro Tag.
    """
    if not daten:
        return None, 0

    O1_RECENCY_DAYS = 30
    O1_RECENCY_BOOST = 1.30
    O2_TRIM_PCT = 0.10

    quotienten: list[tuple[float, float]] = []
    for d_, ist, prog in daten:
        if prog <= 0:
            continue
        q = ist / prog
        days_ago = (heute - d_).days
        recency = O1_RECENCY_BOOST if days_ago < O1_RECENCY_DAYS else 1.0
        quotienten.append((q, prog * recency))

    if not quotienten:
        return None, 0

    quotienten.sort(key=lambda x: x[0])
    n = len(quotienten)
    n_trim = int(n * O2_TRIM_PCT)
    if n_trim > 0:
        quotienten = quotienten[n_trim : n - n_trim]

    if not quotienten:
        return None, 0

    sum_qw = sum(q * w for q, w in quotienten)
    sum_w = sum(w for _, w in quotienten)
    if sum_w <= 0:
        return None, len(quotienten)
    return sum_qw / sum_w, len(quotienten)


# ── Hauptaggregator ────────────────────────────────────────────────────────

class _BinAccumulator:
    """Stündliche Akkumulation pro Bin-Key."""

    __slots__ = ("sum_ist", "sum_prog", "anzahl")

    def __init__(self) -> None:
        self.sum_ist = 0.0
        self.sum_prog = 0.0
        self.anzahl = 0

    def add(self, ist: float, prog: float) -> None:
        self.sum_ist += ist
        self.sum_prog += prog
        self.anzahl += 1


async def _lade_tagesprognose(
    db: AsyncSession, anlage_id: int, von: date, bis: date
) -> dict[date, list[float]]:
    """Day-Ahead-Stundenprofile als `{datum: [24 kWh-Werte]}`."""
    result = await db.execute(
        select(
            TagesZusammenfassung.datum,
            TagesZusammenfassung.pv_prognose_stundenprofil,
            TagesZusammenfassung.pv_prognose_kwh,
        ).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum < bis,
                TagesZusammenfassung.pv_prognose_stundenprofil.isnot(None),
            )
        )
    )
    pro_tag: dict[date, list[float]] = {}
    for datum, profil, _ in result.all():
        if isinstance(profil, list) and len(profil) == 24:
            pro_tag[datum] = profil
    return pro_tag


async def _lade_tagesist_skalar(
    db: AsyncSession, anlage_id: int, datum_set: list[date]
) -> dict[date, tuple[float, float]]:
    """Pro Tag: `(ist_kwh, prognose_kwh)` als Skalar-Tagesdaten.

    IST = Summe `pv_kw` über die 24 Stunden des Tages (kW × 1h = kWh).
    Prognose = `pv_prognose_kwh` aus TagesZusammenfassung.
    """
    if not datum_set:
        return {}
    result = await db.execute(
        select(
            TagesZusammenfassung.datum,
            TagesZusammenfassung.pv_prognose_kwh,
        ).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum.in_(datum_set),
                TagesZusammenfassung.pv_prognose_kwh.isnot(None),
                TagesZusammenfassung.pv_prognose_kwh > 0,
            )
        )
    )
    prog_pro_tag: dict[date, float] = {d: p for d, p in result.all()}

    # IST aus TagesEnergieProfil aufsummieren
    ist_result = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.pv_kw,
        ).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum.in_(datum_set),
                TagesEnergieProfil.pv_kw.isnot(None),
            )
        )
    )
    ist_pro_tag: dict[date, float] = {}
    for datum, pv_kw in ist_result.all():
        if pv_kw is not None and pv_kw > 0:
            ist_pro_tag[datum] = ist_pro_tag.get(datum, 0.0) + pv_kw

    return {
        datum: (ist_pro_tag[datum], prog_pro_tag[datum])
        for datum in prog_pro_tag
        if datum in ist_pro_tag
    }


async def _upsert_profil(
    db: AsyncSession,
    *,
    anlage_id: int,
    profil_typ: str,
    bin_definition: dict,
    faktoren: dict,
    datenpunkte_pro_bin: dict,
    tage_eingegangen: int,
    faktor_skalar: Optional[float] = None,
    quelle: str = "openmeteo",
) -> None:
    result = await db.execute(
        select(Korrekturprofil).where(
            and_(
                Korrekturprofil.anlage_id == anlage_id,
                Korrekturprofil.investition_id.is_(None),
                Korrekturprofil.quelle == quelle,
                Korrekturprofil.profil_typ == profil_typ,
            )
        )
    )
    profil = result.scalar_one_or_none()
    if profil is None:
        profil = Korrekturprofil(
            anlage_id=anlage_id,
            investition_id=None,
            quelle=quelle,
            profil_typ=profil_typ,
        )
        db.add(profil)
    profil.bin_definition = bin_definition
    profil.faktoren = faktoren
    profil.datenpunkte_pro_bin = datenpunkte_pro_bin
    profil.tage_eingegangen = tage_eingegangen
    profil.faktor_skalar = faktor_skalar
    profil.aktualisiert_am = datetime.now()


async def aggregiere_korrekturprofil_anlage(
    anlage: Anlage,
    db: AsyncSession,
    *,
    lookback_tage: int = DEFAULT_LOOKBACK_TAGE,
    azimut_breite: int = AZIMUT_BIN_BREITE_DEFAULT,
    elevation_breite: int = ELEVATION_BIN_BREITE_DEFAULT,
) -> dict:
    """Aggregiert die drei Korrekturprofil-Stufen für eine Anlage.

    Idempotent: bestehende Profile derselben `(anlage_id, NULL,
    quelle, profil_typ)`-Kombination werden überschrieben.

    Liefert ein Status-Dict (für Logging und Endpoint-Response).
    """
    if anlage.latitude is None or anlage.longitude is None:
        return {
            "status": "skipped",
            "grund": "Anlage hat keine Koordinaten — Sonnenstand nicht berechenbar",
        }

    heute = date.today()
    von = heute - timedelta(days=lookback_tage)

    prog_pro_tag = await _lade_tagesprognose(db, anlage.id, von, heute)
    if not prog_pro_tag:
        return {
            "status": "skipped",
            "grund": "Keine Day-Ahead-Snapshots im Zeitraum",
            "tage_eingegangen": 0,
        }

    # Stündliches IST + Wetter laden
    tep_result = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.pv_kw,
            TagesEnergieProfil.bewoelkung_prozent,
            TagesEnergieProfil.niederschlag_mm,
            TagesEnergieProfil.wetter_code,
        ).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum.in_(list(prog_pro_tag.keys())),
            )
        )
    )

    # Bin-Akkumulatoren
    sw_acc: dict[str, _BinAccumulator] = {}  # sonnenstand_wetter
    s_acc: dict[str, _BinAccumulator] = {}  # sonnenstand only
    tage_genutzt: set[date] = set()

    for datum, stunde, pv_kw, bw, ns, wc in tep_result.all():
        if pv_kw is None or pv_kw < MIN_LEISTUNG_KW:
            continue
        prog_profil = prog_pro_tag.get(datum)
        if not prog_profil:
            continue
        prog = prog_profil[stunde] if 0 <= stunde < 24 else None
        if prog is None or prog < MIN_LEISTUNG_KW:
            continue

        sp = solar_position_lokal(anlage.latitude, anlage.longitude, datum, stunde)
        bk = bin_key(sp.azimut, sp.elevation, azimut_breite, elevation_breite)
        if bk is None:
            continue  # Sonne unter Horizont — keine sinnvolle Korrektur

        # sonnenstand-only: immer akkumulieren
        s_acc.setdefault(bk, _BinAccumulator()).add(pv_kw, prog)

        # sonnenstand_wetter: nur wenn Klassifikation gelingt
        klasse = klassifiziere_stunde(bw, ns, wc)
        if klasse is not None:
            kombi_key = f"{bk}_{klasse}"
            sw_acc.setdefault(kombi_key, _BinAccumulator()).add(pv_kw, prog)

        tage_genutzt.add(datum)

    # ── sonnenstand_wetter ────────────────────────────────────────────────
    sw_faktoren: dict[str, float] = {}
    sw_datenpunkte: dict[str, int] = {}
    for k, acc in sw_acc.items():
        raw = _produktionsgewichtet(acc.sum_ist, acc.sum_prog)
        if raw is None:
            continue
        sw_faktoren[k] = round(_clamp(raw), 3)
        sw_datenpunkte[k] = acc.anzahl

    await _upsert_profil(
        db,
        anlage_id=anlage.id,
        profil_typ=PROFIL_TYP_SONNENSTAND_WETTER,
        bin_definition={
            "azimut_aufloesung": azimut_breite,
            "elevation_aufloesung": elevation_breite,
            "wetterklassen": list(WETTERKLASSEN),
        },
        faktoren=sw_faktoren,
        datenpunkte_pro_bin=sw_datenpunkte,
        tage_eingegangen=len(tage_genutzt),
    )

    # ── sonnenstand (Fallback) ────────────────────────────────────────────
    s_faktoren: dict[str, float] = {}
    s_datenpunkte: dict[str, int] = {}
    for k, acc in s_acc.items():
        raw = _produktionsgewichtet(acc.sum_ist, acc.sum_prog)
        if raw is None:
            continue
        s_faktoren[k] = round(_clamp(raw), 3)
        s_datenpunkte[k] = acc.anzahl

    await _upsert_profil(
        db,
        anlage_id=anlage.id,
        profil_typ=PROFIL_TYP_SONNENSTAND,
        bin_definition={
            "azimut_aufloesung": azimut_breite,
            "elevation_aufloesung": elevation_breite,
        },
        faktoren=s_faktoren,
        datenpunkte_pro_bin=s_datenpunkte,
        tage_eingegangen=len(tage_genutzt),
    )

    # ── skalar (O1+O2 auf Tagesebene als letzter Fallback) ────────────────
    tages_skalar = await _lade_tagesist_skalar(db, anlage.id, list(prog_pro_tag.keys()))
    daten = [(d, ist, prog) for d, (ist, prog) in tages_skalar.items()]
    raw_skalar, n_skalar = _aggregate_skalar_o12(daten, heute)
    if raw_skalar is not None:
        skalar_faktor = round(_clamp(raw_skalar), 3)
        await _upsert_profil(
            db,
            anlage_id=anlage.id,
            profil_typ=PROFIL_TYP_SKALAR,
            bin_definition={"variante": "o12"},
            faktoren={"value": skalar_faktor},
            datenpunkte_pro_bin={"value": n_skalar},
            tage_eingegangen=n_skalar,
            faktor_skalar=skalar_faktor,
        )
    else:
        skalar_faktor = None

    await db.commit()
    invalidate_cache(anlage.id)

    logger.info(
        "Korrekturprofil Anlage %s: %d Tage, %d sonnenstand_wetter-Bins, "
        "%d sonnenstand-Bins, Skalar=%s",
        anlage.id,
        len(tage_genutzt),
        len(sw_faktoren),
        len(s_faktoren),
        skalar_faktor,
    )

    return {
        "status": "ok",
        "tage_eingegangen": len(tage_genutzt),
        "bins_sonnenstand_wetter": len(sw_faktoren),
        "bins_sonnenstand": len(s_faktoren),
        "skalar": skalar_faktor,
    }
