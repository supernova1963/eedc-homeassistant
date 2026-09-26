"""
Korrekturprofil-Aggregator.

Berechnet pro Anlage vier Lernfaktor-Profile (siehe
docs/archive/KONZEPT-KORREKTURPROFIL.md):

1. `sonnenstand_wetter` — Faktor pro `(azimut_bin, elevation_bin, wetterklasse)`
2. `stunde` — Faktor pro `(saisonbin, stunde)` (Variante A); trennt saisonale
   Verschattung (belaubt vs. kahl), die die Sonnenstand-Bins wegmitteln
3. `sonnenstand` — Faktor pro `(azimut_bin, elevation_bin)` als Fallback
4. `skalar` — O1+O2-Skalar als letzter Fallback

Datenquelle:
- Tages-Day-Ahead-**Lern-SOLL** `TagesZusammenfassung.lern_soll_stundenprofil_kwh`
  (24 Werte in kWh, vor Sonnenaufgang gefroren) — die rohe, gekappte,
  **unkorrigierte** OpenMeteo-Reihe.

  ⛔ **Hier stand bis 22.09.2026 `pv_prognose_stundenprofil`, und das war der
  Fund N-547.** Jenes Feld trägt die **korrigierte** Kanon-Ausgabe, also das
  Ergebnis genau der Faktoren, die hier gelernt werden. Der Quotient
  Σ IST / Σ SOLL rechnete damit gegen die eigene Ausgabe: aus
  `f_neu = IST / (roh × f_alt)` wird über den gepoolten Mittelwert der
  Fixpunkt von `f ↦ r/f`, also **√r statt r**. Gemessen (V2, 22.09.2026,
  echtes Verhältnis r = 0,85): 0,922 statt 0,850 — **+8,5 % Überschätzung an
  jedem Tag**, sichtbar in `eedc_prognose_heute_kwh`, im HA-Sensor und in der
  Aussicht. Gekappt muss das SOLL sein, weil der Wechselrichter über seiner
  AC-Grenze nichts liefern KANN; ein ungekapptes SOLL würde die physikalische
  Grenze als dauerhaften Prognosefehler in die Faktoren schreiben.
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
    PROFIL_TYP_STUNDE,
    Korrekturprofil,
)
from backend.core.berechnungen.spannen import spanne
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.wetter.solar_position import (
    AZIMUT_BIN_BREITE_DEFAULT,
    ELEVATION_BIN_BREITE_DEFAULT,
    bin_key,
    solar_position_lokal,
)
from backend.services.wetter.utils import WETTERKLASSEN, klassifiziere_stunde
from backend.services.korrekturprofil_lookup import (
    MIN_DATENPUNKTE_SONNENSTAND,
    MIN_DATENPUNKTE_SONNENSTAND_WETTER,
    MIN_STUNDEN_STUNDE_SAISONBIN,
    MIN_TAGE_SKALAR,
    invalidate_cache,
)

logger = logging.getLogger(__name__)


# Pro-Stunde-Filter — analog Stratifizierungs-Endpoint, kein Doppel-Standard
MIN_LEISTUNG_KW = 0.05

# Lookback-Tiefe Default — 2 Jahre passt zum Wetter-Backfill
DEFAULT_LOOKBACK_TAGE = 730

# Clamp-Bereich für Korrekturfaktoren — analog Skalar-Lernfaktor
FAKTOR_CLAMP_MIN = 0.5
FAKTOR_CLAMP_MAX = 1.3

# Saisonbin-Kaskade der stunde-Stufe (Variante A) — analog Skalar-Kaskade:
# Monat (gleicher Kalendermonat alle Jahre) → Quartal → Gesamt (letzte
# 30 Tage rollierend). Schwellen in Tagen pro (Saisonbin, Stunde)-Zelle.
ST_MIN_TAGE_MONAT = 15
ST_MIN_TAGE_QUARTAL = 15
ST_MIN_TAGE_GESAMT = 7
ST_GESAMT_FENSTER_TAGE = 30


# ── N-547: die Übergangsregel ─────────────────────────────────────────────
#
# Die neuen Lern-SOLL-Felder entstehen **ab jetzt** — es gibt keinen Backfill
# (die alten Zeilen tragen die korrigierte Reihe; sie zurückzurechnen wäre
# geraten, nicht gemessen). Ohne weitere Vorkehrung würde der erste nächtliche
# Lauf nach dem Update **alle** Bins mit dem leeren neuen Pool überschreiben:
# das Korrekturprofil einer Anlage wäre über Nacht weg, und die Prognose fiele
# wochenlang auf den Legacy-Skalar zurück.
#
# Deshalb: je Bin bleibt der alte Wert stehen, **bis das reale Gate seiner
# Stufe mit NEUEN Datenpunkten erreicht ist**. Die Gates sind nicht neu
# erfunden, sondern die des Lookups — ein Bin, der sie nicht erreicht, wird
# dort ohnehin übersprungen; ihn vorher zu ersetzen hieße, einen brauchbaren
# Faktor gegen einen zu tauschen, den niemand benutzt.
_GATE_JE_TYP: dict[str, int] = {
    PROFIL_TYP_SONNENSTAND_WETTER: MIN_DATENPUNKTE_SONNENSTAND_WETTER,  # 10 Stunden je Bin
    PROFIL_TYP_SONNENSTAND: MIN_DATENPUNKTE_SONNENSTAND,                # 15 Stunden je Bin
    PROFIL_TYP_STUNDE: MIN_STUNDEN_STUNDE_SAISONBIN,                    # Σ 50 Stunden je Monat
    PROFIL_TYP_SKALAR: MIN_TAGE_SKALAR,                                 # 7 Tage
}

# ⛔ **Ende der Keep-Regel.** Ohne Ende bliebe ein Bin, den die Anlage
# saisonal nie wieder füllt (Dezember-Stunden einer im Januar erweiterten
# Anlage), **für immer** auf seinem zirkulär gelernten Wert — und niemand
# sähe es. Nach einem vollen Jahr hatte jeder Bin seine Saison; danach gilt
# wieder Vollersatz wie vor N-547.
_KEEP_TAGE = 365


def _clamp(faktor: float) -> float:
    return max(FAKTOR_CLAMP_MIN, min(FAKTOR_CLAMP_MAX, faktor))


def _quartal_von_monat(monat: int) -> int:
    return (monat - 1) // 3 + 1


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
    """Day-Ahead-**Lern-SOLL**-Stundenreihen als `{datum: [24 kWh-Werte]}`.

    ⛔ **Nicht `pv_prognose_stundenprofil`** — das ist die korrigierte
    Vorhersage und damit die eigene Ausgabe dieses Aggregators (N-547, s.
    Modul-Docstring). Tage vor der Umstellung tragen `NULL` und fallen hier
    heraus; ihre Bins behalten über `_upsert_profil` ihren alten Faktor, bis
    genug neue Datenpunkte aufgelaufen sind.
    """
    result = await db.execute(
        select(
            TagesZusammenfassung.datum,
            TagesZusammenfassung.lern_soll_stundenprofil_kwh,
            TagesZusammenfassung.lern_soll_kwh,
        ).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum < bis,
                TagesZusammenfassung.lern_soll_stundenprofil_kwh.isnot(None),
            )
        )
    )
    pro_tag: dict[date, list[float]] = {}
    for datum, profil, _ in result.all():
        if isinstance(profil, list) and len(profil) == 24:
            pro_tag[datum] = profil
    return pro_tag


async def _lade_tagesist_skalar(
    db: AsyncSession, anlage_id: int, von: date, bis: date
) -> dict[date, tuple[float, float]]:
    """Pro Tag im Zeitraum: `(ist_kwh, prognose_kwh)` als Skalar-Tagesdaten.

    IST = Summe `pv_kw` über die 24 Stunden des Tages (kW × 1h = kWh).
    SOLL = `lern_soll_kwh` aus TagesZusammenfassung (Σ der Lern-SOLL-Slots).

    ⛔ **Nicht `pv_prognose_kwh`** (N-547). Jenes Feld ist die rohe,
    **ungekappte** OM-Tagessumme — an einer Anlage mit AC-Grenze liegt es
    dauerhaft über dem, was die Anlage liefern kann, und der Skalar lernte
    diesen Deckel als Prognosefehler ein. `lern_soll_kwh` ist dieselbe Reihe
    **gekappt** und damit die Größe, gegen die sich ein IST fair messen lässt.

    Unabhängig von `lern_soll_stundenprofil_kwh` — die Skalar-Stufe braucht
    nur das Tages-SOLL, damit der Live-Pfad auch dann einen
    Korrekturprofil-Faktor hat, wenn Day-Ahead-Stundenreihen noch nicht
    aufgelaufen sind.
    """
    result = await db.execute(
        select(
            TagesZusammenfassung.datum,
            TagesZusammenfassung.lern_soll_kwh,
        ).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum < bis,
                TagesZusammenfassung.lern_soll_kwh.isnot(None),
                TagesZusammenfassung.lern_soll_kwh > 0,
            )
        )
    )
    prog_pro_tag: dict[date, float] = {d: p for d, p in result.all()}
    if not prog_pro_tag:
        return {}

    ist_result = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.pv_kw,
        ).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum.in_(list(prog_pro_tag.keys())),
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


def _monats_summen(datenpunkte: Optional[dict]) -> dict[str, int]:
    """Σ Datenpunkte je Saisonbin aus `{"monat_stunde": n}`.

    Dieselbe Bildung wie im Lookup (`korrekturprofil_lookup:123-125`) — das
    Gate der `stunde`-Stufe greift dort auf den **Monat**, nicht auf die
    einzelne Zelle.
    """
    summen: dict[str, int] = {}
    for key, anzahl in (datenpunkte or {}).items():
        monat = str(key).split("_", 1)[0]
        summen[monat] = summen.get(monat, 0) + int(anzahl or 0)
    return summen


def _mische_flach(
    alt_faktoren: dict, alt_datenpunkte: dict, alt_basis: dict,
    neu_faktoren: dict, neu_datenpunkte: dict, gate: int,
) -> tuple[dict, dict, dict]:
    """Bin-weiser Übergang für die flachen Stufen (`{bin: faktor}`).

    Der neue Wert ersetzt den alten nur, wenn er das Gate **mit neuen
    Datenpunkten** erreicht. Sonst bleibt der alte Wert **samt seiner alten
    Datenpunktzahl** — sie ist es, die den Lookup passieren lässt; nur den
    Faktor zu behalten und die Zählung zu ersetzen hieße, den Bin still
    stillzulegen.
    """
    faktoren: dict = {}
    datenpunkte: dict = {}
    basis: dict = {}
    for k in set(alt_faktoren) | set(neu_faktoren):
        n_neu = int((neu_datenpunkte or {}).get(k, 0) or 0)
        if k in neu_faktoren and n_neu >= gate:
            faktoren[k], datenpunkte[k], basis[k] = neu_faktoren[k], n_neu, "neu"
        elif k in alt_faktoren:
            faktoren[k] = alt_faktoren[k]
            datenpunkte[k] = int((alt_datenpunkte or {}).get(k, 0) or 0)
            # Die Herkunft wird GEERBT, nicht gesetzt: auf einer frisch
            # aufgesetzten Anlage stammt auch der „alte" Wert schon aus dem
            # neuen Lern-SOLL. Fehlt der Eintrag (Zeile von vor N-547), ist
            # „alt" die richtige Antwort.
            basis[k] = (alt_basis or {}).get(k, "alt")
        else:
            faktoren[k], datenpunkte[k], basis[k] = neu_faktoren[k], n_neu, "neu"
    return faktoren, datenpunkte, basis


def _mische_stunde(
    alt_faktoren: dict, alt_datenpunkte: dict, alt_basis: dict,
    neu_faktoren: dict, neu_datenpunkte: dict, gate: int,
) -> tuple[dict, dict, dict]:
    """Übergang der `stunde`-Stufe — Einheit ist der **Saisonbin**.

    Ihr Gate ist Σ über den Monat (`MIN_STUNDEN_STUNDE_SAISONBIN`), und der
    Lookup entscheidet ebenso je Monat. Ein Monat wandert deshalb als Ganzes
    auf das neue Lern-SOLL oder gar nicht — eine Mischung aus alten und neuen
    Zellen **innerhalb** eines Monats wäre ein Profil, das es nie gab.
    """
    neu_summen = _monats_summen(neu_datenpunkte)
    faktoren: dict = {}
    datenpunkte: dict = {}
    basis: dict = {}
    for monat in set(alt_faktoren) | set(neu_faktoren):
        nimm_neu = monat in neu_faktoren and neu_summen.get(monat, 0) >= gate
        quelle_f, quelle_d, marke = (
            (neu_faktoren, neu_datenpunkte, "neu") if nimm_neu
            else (alt_faktoren, alt_datenpunkte, None) if monat in alt_faktoren
            else (neu_faktoren, neu_datenpunkte, "neu")
        )
        zellen = quelle_f.get(monat) or {}
        if not zellen:
            continue
        faktoren[monat] = dict(zellen)
        for stunde in zellen:
            zell_key = f"{monat}_{stunde}"
            datenpunkte[zell_key] = int((quelle_d or {}).get(zell_key, 0) or 0)
            basis[zell_key] = (
                marke if marke is not None
                else (alt_basis or {}).get(zell_key, "alt")
            )
    return faktoren, datenpunkte, basis


async def _upsert_profil(
    db: AsyncSession,
    *,
    anlage_id: int,
    profil_typ: str,
    bin_definition: dict,
    faktoren: dict,
    datenpunkte_pro_bin: dict,
    tage_eingegangen: int,
    heute: date,
    faktor_skalar: Optional[float] = None,
    quelle: str = "openmeteo",
) -> None:
    """Profil-Zeile je Stufe anlegen oder fortschreiben — inkl. Übergangsregel (N-547).

    ⚠ **Der Skalar bekommt `lern_umstellung_am` später als die drei Bin-Stufen**
    (Nachmessung 22.09.2026): sein Aufruf hängt an `raw_skalar is not None`, also
    an der ersten Nacht mit einer `lern_soll_kwh`-Zeile; die Bin-Stufen laufen
    auch mit leerem Pool. Sein 365-Tage-Fenster beginnt dadurch um die Tage
    versetzt, die bis zur ersten Lern-Zeile vergehen — unschädlich, weil das
    7-Tage-Gate lange vorher greift.
    """
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
    neu_angelegt = profil is None
    if profil is None:
        profil = Korrekturprofil(
            anlage_id=anlage_id,
            investition_id=None,
            quelle=quelle,
            profil_typ=profil_typ,
        )
        db.add(profil)

    # N-547: Beginn der Keep-Regel. Eine Bestandszeile bekommt ihn beim ersten
    # Lauf nach dem Update, eine neue Zeile ihren Anlage-Tag — dort gibt es
    # ohnehin nichts zu halten.
    if profil.lern_umstellung_am is None:
        profil.lern_umstellung_am = heute

    keep_aktiv = (
        not neu_angelegt
        and (heute - profil.lern_umstellung_am).days <= _KEEP_TAGE
    )

    lern_basis: dict = {}
    if keep_aktiv:
        gate = _GATE_JE_TYP.get(profil_typ, 0)
        alt_faktoren = profil.faktoren or {}
        alt_datenpunkte = profil.datenpunkte_pro_bin or {}
        alt_basis = profil.lern_basis_pro_bin or {}
        if profil_typ == PROFIL_TYP_SKALAR:
            n_neu = int((datenpunkte_pro_bin or {}).get("value", 0) or 0)
            if faktoren and n_neu >= gate:
                lern_basis = {"value": "neu"}
            elif alt_faktoren:
                # Ü3: beim Skalar gehören `tage_eingegangen` UND
                # `faktor_skalar` zum gehaltenen Wert — der Lookup liest
                # genau diese beiden (`korrekturprofil_lookup:139-140/231`).
                # Ohne sie fiele Stufe 4 aus, und mit ihr die letzte
                # Rückfallebene der ganzen Kaskade.
                faktoren = alt_faktoren
                datenpunkte_pro_bin = alt_datenpunkte
                tage_eingegangen = profil.tage_eingegangen or 0
                faktor_skalar = profil.faktor_skalar
                lern_basis = {"value": alt_basis.get("value", "alt")}
            else:
                lern_basis = {"value": "neu"}
        else:
            mischer = (
                _mische_stunde if profil_typ == PROFIL_TYP_STUNDE else _mische_flach
            )
            faktoren, datenpunkte_pro_bin, lern_basis = mischer(
                alt_faktoren, alt_datenpunkte, alt_basis,
                faktoren, datenpunkte_pro_bin, gate,
            )
            # Die Zeile trägt jetzt Bins aus zwei Pools. `tage_eingegangen` ist
            # für diese Stufen rein informativ (die Gates hängen an
            # `datenpunkte_pro_bin`); der größere der beiden Pools ist die
            # ehrlichste Einzelzahl dafür.
            tage_eingegangen = max(tage_eingegangen, profil.tage_eingegangen or 0)
    else:
        # Kein Keep: alles, was hier steht, ist gegen das neue Lern-SOLL
        # gelernt — bei `stunde` sind die Bin-Schlüssel die Zell-Schlüssel
        # der Datenpunkte, nicht die Monats-Schlüssel der Faktoren.
        lern_basis = {k: "neu" for k in (datenpunkte_pro_bin or {})}

    profil.bin_definition = bin_definition
    profil.faktoren = faktoren
    profil.datenpunkte_pro_bin = datenpunkte_pro_bin
    profil.tage_eingegangen = tage_eingegangen
    profil.faktor_skalar = faktor_skalar
    profil.lern_basis_pro_bin = lern_basis
    profil.aktualisiert_am = datetime.now()


async def aggregiere_korrekturprofil_anlage(
    anlage: Anlage,
    db: AsyncSession,
    *,
    lookback_tage: int = DEFAULT_LOOKBACK_TAGE,
    azimut_breite: int = AZIMUT_BIN_BREITE_DEFAULT,
    elevation_breite: int = ELEVATION_BIN_BREITE_DEFAULT,
    heute: Optional[date] = None,
) -> dict:
    """Aggregiert die vier Korrekturprofil-Stufen für eine Anlage.

    Idempotent: bestehende Profile derselben `(anlage_id, NULL,
    quelle, profil_typ)`-Kombination werden überschrieben.

    `heute` dient als Stichtag für Lookback und Gesamt-Fenster
    (Default: heutiges Datum; injizierbar für deterministische Tests).

    Liefert ein Status-Dict (für Logging und Endpoint-Response).
    """
    if anlage.latitude is None or anlage.longitude is None:
        return {
            "status": "skipped",
            "grund": "Anlage hat keine Koordinaten — Sonnenstand nicht berechenbar",
        }

    if heute is None:
        heute = date.today()
    von = heute - timedelta(days=lookback_tage)

    prog_pro_tag = await _lade_tagesprognose(db, anlage.id, von, heute)

    # Bin-Akkumulatoren
    sw_acc: dict[str, _BinAccumulator] = {}  # sonnenstand_wetter
    s_acc: dict[str, _BinAccumulator] = {}  # sonnenstand only
    tage_genutzt: set[date] = set()

    # stunde-Stufe (Variante A): drei Pool-Granularitäten parallel füllen,
    # die Saisonbin-Kaskade wird nach dem Loop pro Zelle aufgelöst.
    st_monat_acc: dict[tuple[int, int], _BinAccumulator] = {}    # (monat, stunde)
    st_quartal_acc: dict[tuple[int, int], _BinAccumulator] = {}  # (quartal, stunde)
    st_gesamt_acc: dict[int, _BinAccumulator] = {}               # stunde
    st_tage: set[date] = set()
    st_gesamt_von = heute - timedelta(days=ST_GESAMT_FENSTER_TAGE)

    if not prog_pro_tag:
        # Kein Day-Ahead-Snapshot im Zeitraum — die Bin-Stufen bleiben leer,
        # die Skalar-Stufe (Tages-IST/Tages-Prognose) wird trotzdem unten
        # berechnet, damit der Live-Pfad einen Korrekturfaktor hat.
        tep_rows: list = []
    else:
        # Stündliches IST + Wetter für die Tage mit Day-Ahead-Snapshot laden
        tep_result = await db.execute(
            select(
                TagesEnergieProfil.datum,
                TagesEnergieProfil.stunde,
                TagesEnergieProfil.pv_kw,
                TagesEnergieProfil.bewoelkung_prozent,
                TagesEnergieProfil.niederschlag_mm,
                TagesEnergieProfil.wetter_code,
                TagesEnergieProfil.spannen,
            ).where(
                and_(
                    TagesEnergieProfil.anlage_id == anlage.id,
                    TagesEnergieProfil.datum.in_(list(prog_pro_tag.keys())),
                )
            )
        )
        tep_rows = list(tep_result.all())

    for datum, stunde, pv_kw, bw, ns, wc, spannen in tep_rows:
        if pv_kw is None or pv_kw < MIN_LEISTUNG_KW:
            continue
        # Zählerlücken wie HA (§2): eine Stunde, deren PV mehr als eine reale
        # Stunde trägt (Energie einer Lücke), ist keine Stunden-Stichprobe für
        # einen Korrekturfaktor — sie fällt hier aus, bleibt in jeder Summe.
        if spanne(spannen, "pv") > 1:
            continue
        prog_profil = prog_pro_tag.get(datum)
        if not prog_profil:
            continue
        prog = prog_profil[stunde] if 0 <= stunde < 24 else None
        if prog is None or prog < MIN_LEISTUNG_KW:
            continue

        # stunde-Stufe: braucht keinen Sonnenstand — vor dem bin_key-Filter
        # akkumulieren, damit auch Dämmerungs-Slots einfließen (wie Skalar).
        st_monat_acc.setdefault((datum.month, stunde), _BinAccumulator()).add(pv_kw, prog)
        st_quartal_acc.setdefault(
            (_quartal_von_monat(datum.month), stunde), _BinAccumulator()
        ).add(pv_kw, prog)
        if datum >= st_gesamt_von:
            st_gesamt_acc.setdefault(stunde, _BinAccumulator()).add(pv_kw, prog)
        st_tage.add(datum)

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
        heute=heute,
    )

    # ── stunde (Variante A: Saisonbin × Stunde) ───────────────────────────
    # Pro Zelle (monat, stunde) die feinste ausreichend belegte Granularität
    # wählen: Monat → Quartal → Gesamt (rollierend). Der Schlüsselraum bleibt
    # dadurch immer Monat 1-12, der Lookup braucht keine Pool-Logik mehr.
    st_faktoren: dict[str, dict[str, float]] = {}
    st_datenpunkte: dict[str, int] = {}
    for monat in range(1, 13):
        quartal = _quartal_von_monat(monat)
        for h in range(24):
            acc = st_monat_acc.get((monat, h))
            if acc is None or acc.anzahl < ST_MIN_TAGE_MONAT:
                acc = st_quartal_acc.get((quartal, h))
                if acc is None or acc.anzahl < ST_MIN_TAGE_QUARTAL:
                    acc = st_gesamt_acc.get(h)
                    if acc is None or acc.anzahl < ST_MIN_TAGE_GESAMT:
                        continue
            raw = _produktionsgewichtet(acc.sum_ist, acc.sum_prog)
            if raw is None:
                continue
            st_faktoren.setdefault(str(monat), {})[str(h)] = round(_clamp(raw), 3)
            st_datenpunkte[f"{monat}_{h}"] = acc.anzahl

    await _upsert_profil(
        db,
        anlage_id=anlage.id,
        profil_typ=PROFIL_TYP_STUNDE,
        bin_definition={
            "saisonbin": "monat",
            "min_tage_monat": ST_MIN_TAGE_MONAT,
            "min_tage_quartal": ST_MIN_TAGE_QUARTAL,
            "min_tage_gesamt": ST_MIN_TAGE_GESAMT,
            "gesamt_fenster_tage": ST_GESAMT_FENSTER_TAGE,
        },
        faktoren=st_faktoren,
        datenpunkte_pro_bin=st_datenpunkte,
        tage_eingegangen=len(st_tage),
        heute=heute,
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
        heute=heute,
    )

    # ── skalar (O1+O2 auf Tagesebene als letzter Fallback) ────────────────
    # Skalar wird unabhängig von Day-Ahead-Stundenprofilen berechnet —
    # so hat der Live-Pfad ab Tag 1 einen Korrekturfaktor, auch wenn die
    # höheren Stufen erst über Wochen aufgebaut werden.
    tages_skalar = await _lade_tagesist_skalar(db, anlage.id, von, heute)
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
            heute=heute,
            faktor_skalar=skalar_faktor,
        )
    else:
        skalar_faktor = None

    await db.commit()
    invalidate_cache(anlage.id)

    # Falls weder Bins noch Skalar berechenbar waren → Skipped
    if (
        not sw_faktoren
        and not st_faktoren
        and not s_faktoren
        and skalar_faktor is None
    ):
        return {
            "status": "skipped",
            "grund": "Keine Tagesdaten (weder pv_prognose_kwh noch IST verfügbar)",
            "tage_eingegangen": 0,
        }

    # Aussage-Wert für UI: Bin-Tage falls vorhanden, sonst Skalar-Tagesanzahl
    tage_aussagekraft = len(tage_genutzt) if tage_genutzt else n_skalar

    logger.info(
        "Korrekturprofil Anlage %s: %d Tage, %d sonnenstand_wetter-Bins, "
        "%d stunde-Zellen, %d sonnenstand-Bins, Skalar=%s (n=%d)",
        anlage.id,
        tage_aussagekraft,
        len(sw_faktoren),
        len(st_datenpunkte),
        len(s_faktoren),
        skalar_faktor,
        n_skalar,
    )

    return {
        "status": "ok",
        "tage_eingegangen": tage_aussagekraft,
        "bins_sonnenstand_wetter": len(sw_faktoren),
        "bins_stunde": len(st_datenpunkte),
        "bins_sonnenstand": len(s_faktoren),
        "skalar": skalar_faktor,
    }
