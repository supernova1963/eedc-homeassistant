"""Kanal-Schreiber — parallel zum Bestand (HA-Bauform E1, Bauplan §4; Auftrag E1 Punkt 4).

Drei Roh-Familien; seit HA-Bauform E4c dazu abgeleitete Kanäle, die der Stundenlauf nach ihnen fortschreibt
(``abgeleitet.py``: PV-Anteil der Heimladung je Gerät; seit E4d ``modus_strom.py``: Strom der Wärmepumpe je Betriebsart,
den auch die Mitschrift nach ihrem Schreiben fortschreibt; seit E4e ``kosten.py``: Kosten-Kanäle bei Stundenpreis):

* **Spiegel (HA)** — je zugeordnetem Zähler (``snapshot/writer._build_counter_map``, dieselbe
  Auswahl wie der Bestand, inklusive Stilllegung und ``quellen``-Read-Through) die Stundenzeilen der
  HA-Langzeitstatistik **seit der letzten geschriebenen Stunde**: ``sum`` und ``state`` wörtlich,
  ``start_ts`` wie HA. Kein Deckel, keine Lückenfüllung. Einzige Umrechnung ist die Einheit, die der
  heutige Leser schon anwendet: ``HAStatisticsService._value_at_wert`` rechnet eine Menge mit
  ``_ENERGY_UNIT_TO_KWH`` nach kWh und lässt einen Stand unverändert (F-58).
* **Spiegel ``mean`` (HA)** — je zugeordnetem Live-/Preis-Feld (``live_sensor_config.extract_live_config``
  + ``extract_quellen_live``, Preis über ``_helpers.strompreis_sensor_id``), dessen Sensor eine
  Langzeitstatistik hat: ``mean``/``min``/``max`` **wörtlich**, ``start_ts`` = HAs Stundenbeginn (HAs
  Periode ``[h, h+1)``, keine Verschiebung, keine eigene Mittelung). ``kanal.einheit`` = HAs Einheit beim
  Anlegen; meldet der Sensor später eine andere, wird **nicht** geschrieben und einmal je Kanal und Tag
  geloggt. **Keine Umrechnung** — die Normierung auf die Registry-Einheit ist Sache des Lesers (E3); die
  Regel „unbekannte Einheit ÷ 1000" aus ``get_hourly_sensor_data`` gilt hier ausdrücklich nicht.
  Mittelwerte von HA-Sensoren OHNE Langzeitstatistik bekommen keine Zeile (Daten-Checker «Sensor ohne
  Langzeitstatistik»).
* **Mitschrift ``mean`` (MQTT, HA-Bauform §9, Standalone-Gleichstand S2)** — je Mittelwert-Feld ohne HA-Zuordnung
  (``_mean_mitschrift_zuordnung``, G1) aus den 5-Minuten-Snapshots des Inbound (``mqtt_live_snapshots``: Fenster-Mittel
  aus dem Integrator, ``min``/``max``): je abgeschlossener Stunde ``mean`` längengewichtet, ``min``/``max`` Extrema
  (``mittel_je_stunde``), Kanal-Einheit = Registry-Einheit, ``statistic_id`` = MQTT-Schlüssel
  (``mqtt_live_statistic_id``). Erster Lauf nur die abgeschlossene Stunde, nicht rückwirkend (E2/E-SG-7).
* **Eigene Summe (MQTT/ohne HA)** — aus den Rohständen in ``mqtt_energy_snapshots`` mit HAs Regel
  (``core/berechnungen/ha_summe.py``). Der heutige Deckel (R3) bleibt hier als **Schreibfilter**:
  dieselbe Schwelle (``plausibility.schwelle_pv_einspeisung_stunde_kwh`` ×
  ``spannen.deckel_fenster_stunden``) und derselbe Cap (``plausibility.cap_pv_einspeisung_stunde``)
  wie der Tagespfad, auf denselben Achsen (``spannen.ACHSEN_MIT_DECKEL``). Eine verworfene Stunde
  trägt den neuen Stand, aber keinen Zuwachs.
* **Mitschrift Betriebsart** — „Anteil der Stunde je Betriebsart" aus dem, was die
  Tagesaggregation ohnehin liest (``energie_profil/_helpers._get_betriebsmodus_history``). Die Quelle
  liegt nur dort vor, deshalb wird dort mitgeschrieben (``aggregator.aggregate_day``). Eine
  geschriebene Stunde wird nie überschrieben oder geleert. Seit HA-Bauform §9 (Standalone-Gleichstand S1)
  zusätzlich für Wärmepumpen ohne HA-Modus aus den 5-Minuten-Snapshots des MQTT-Inbound
  (``_betriebsart_mitschrift_mqtt`` im Stundenlauf, ``statistic_id`` = MQTT-Schlüssel); beide Wege rufen
  denselben Kern ``_schreibe_betriebsart_anteile`` (E-SG-6). Die Stunde aus den 5-Minuten-Zeilen verdichtet
  ``modus_anteile_je_stunde`` längengewichtet mit derselben Gewichtung wie die Mittelwerte (``fenster_gewicht``,
  Standalone-Gleichstand S3 — eine Mittelungsregel im MQTT-Pfad).

**Isolation vom Bestand.** Beide Einstiege (``schreibe_kanaele_im_stundenlauf``,
``schreibe_betriebsart_mitschrift_sicher``) laufen NACH dem heutigen Schreiben in derselben Sitzung,
in einem eigenen SAVEPOINT (``begin_nested``): Ein Fehler rollt nur den neuen Teil zurück, wird
geloggt und als Aktivität in DERSELBEN Sitzung vermerkt (N-532) — kein zweiter Schreiber.

**Gebündelt.** Je Lauf und Anlage: Kanäle, letzte Zeilen und Quellen in je einem Statement, die
HA-Zeilen aller Zähler in einer Abfrage und einem Thread-Sprung, alle neuen Zeilen in einem INSERT
(gemessen im Bericht E1: ohne Bündelung verdreifachte der neue Teil den Stundenlauf).

**Stand E1: wird geschrieben, von keiner Sicht gelesen.**
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select, union_all
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.ha_summe import PeriodenSumme, ha_summe_der_periode
from backend.core.berechnungen.slot_konvention import slot_start_ts
from backend.core.berechnungen.spannen import (
    ACHSEN_MIT_DECKEL,
    DECKEL_FENSTER_MAX_STUNDEN,
    achse_der_kategorie,
    deckel_fenster_stunden,
)
from backend.core.betriebsmodus import BETRIEBSMODUS_KANON
from backend.core.field_definitions import basis_feld_key, einheit_fuer
from backend.models.kanal import (
    ART_MEAN,
    ART_STAND,
    ART_SUM,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.kanal import merken
from backend.services.kanal.katalog import (
    ist_mean_kanal,
    ist_tagesgroesse_ohne_kanal,
    modus_kanal_key,
    zaehler_art,
)

logger = logging.getLogger(__name__)

#: Einheit der Betriebsart-Mitschrift: Bruchteil der Stunde, 0 … 1.
EINHEIT_ANTEIL = "Anteil"
#: Rohstände aus MQTT liegen höchstens so lange vor (``mqtt_energy_history_service``, Retention).
MQTT_ROHSTAND_TAGE = 31
_STUNDE = 3600
_TOL = 1e-9
#: Fenster, in dem die letzte Zeile eines Kanals im Regelfall liegt (ein Statement für alle).
_NAH_STUNDEN = 48


def _unix(dt: datetime) -> int:
    """Lokale naive Zeit → Unix-Sekunden (wie ``ha_statistics_service._unix``), als ganze Sekunde."""
    return int(round(dt.timestamp()))


# ── Kanal-Grundoperationen (gebündelt) ──────────────────────────────────────


@dataclass
class _KanalStand:
    kanal: Kanal
    letzte: Optional[KanalStatistik]
    quelle: Optional[KanalQuelle]


async def kanaele_holen(
    db: AsyncSession, anlage_id: int, gewuenscht: dict[str, tuple[str, str]],
) -> dict[str, Kanal]:
    """Kanäle ``{key: (art, einheit)}`` holen und fehlende anlegen (idempotent über ``(anlage_id, key)``)."""
    if not gewuenscht:
        return {}
    da = {k.key: k for k in (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key.in_(list(gewuenscht))))
    )).scalars().all()}
    neu = [Kanal(anlage_id=anlage_id, key=key, art=art, einheit=einheit or "")
           for key, (art, einheit) in gewuenscht.items() if key not in da]
    if neu:
        db.add_all(neu)
        await db.flush()
        da.update({k.key: k for k in neu})
    return da


async def letzte_zeilen(db: AsyncSession, kanal_ids: list[int], *, nah_ab: Optional[int] = None) -> dict[int, KanalStatistik]:
    """Je Kanal die Zeile mit dem größten ``start_ts``.

    Regelfall in EINEM Statement über das Fenster ``start_ts >= nah_ab`` (Index-Bereich je Kanal);
    nur Kanäle ohne Zeile darin fragen einzeln nach (``ORDER BY start_ts DESC LIMIT 1``, ein
    Index-Schritt) — nie ein Durchlauf über die ganze Historie.
    """
    out: dict[int, KanalStatistik] = {}
    if not kanal_ids:
        return out
    if nah_ab is not None:
        for z in (await db.execute(
            select(KanalStatistik).where(and_(KanalStatistik.kanal_id.in_(kanal_ids),
                                              KanalStatistik.start_ts >= nah_ab))
        )).scalars().all():
            if z.kanal_id not in out or z.start_ts > out[z.kanal_id].start_ts:
                out[z.kanal_id] = z
    rest = [k for k in kanal_ids if k not in out]
    if rest:
        teile = [select(KanalStatistik.kanal_id, KanalStatistik.start_ts)
                 .where(KanalStatistik.kanal_id == k).order_by(KanalStatistik.start_ts.desc()).limit(1)
                 .subquery().select() for k in rest]
        paare = (await db.execute(union_all(*teile) if len(teile) > 1 else teile[0])).all()
        if paare:
            bed = [and_(KanalStatistik.kanal_id == k, KanalStatistik.start_ts == ts) for k, ts in paare]
            for z in (await db.execute(select(KanalStatistik).where(or_(*bed)))).scalars().all():
                out[z.kanal_id] = z
    return out


async def aktuelle_quellen(db: AsyncSession, kanal_ids: list[int]) -> dict[int, KanalQuelle]:
    """Je Kanal die Quelle mit dem größten ``gueltig_ab`` (die Tabelle ist klein: ein Eintrag je Tausch)."""
    out: dict[int, KanalQuelle] = {}
    if not kanal_ids:
        return out
    for q in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id.in_(kanal_ids)))).scalars().all():
        if q.kanal_id not in out or q.gueltig_ab > out[q.kanal_id].gueltig_ab:
            out[q.kanal_id] = q
    return out


async def _staende(db: AsyncSession, anlage_id: int, gewuenscht: dict[str, tuple[str, str]],
                   nah_ab: Optional[int]) -> dict[str, _KanalStand]:
    kanaele = await kanaele_holen(db, anlage_id, gewuenscht)
    ids = [k.id for k in kanaele.values()]
    letzte = await letzte_zeilen(db, ids, nah_ab=nah_ab)
    quellen = await aktuelle_quellen(db, ids)
    return {key: _KanalStand(k, letzte.get(k.id), quellen.get(k.id)) for key, k in kanaele.items()}


def _wertspalte(art: str) -> str:
    """Die Spalte, die ein Kanal dieser Art fortschreibt — und auf die sich ``offset`` bezieht.

    Bei ``sum`` ist ``sum + offset`` der Kanalwert. Bei ``stand`` ist der Stand immer ``state`` roh (die
    Zahl auf dem Zähler, F-58); ``offset`` dient dort nur der Differenz über eine Quellgrenze, nie als
    Kanalwert."""
    return "state" if art == ART_STAND else "sum"


def _kanal_wert(zeile: Optional[KanalStatistik], quelle: Optional[KanalQuelle], art: str) -> Optional[float]:
    """Wert des Kanals in seiner letzten Zeile: Rohwert + ``offset`` der geltenden Quelle."""
    if zeile is None:
        return None
    roh = getattr(zeile, _wertspalte(art))
    if roh is None:
        return None
    return float(roh) + (float(quelle.offset) if quelle is not None else 0.0)


async def _zeilen_einfuegen(db: AsyncSession, zeilen: list[dict]) -> int:
    """Einfügen ohne Überschreiben (``ON CONFLICT DO NOTHING`` auf ``(kanal_id, start_ts)``)."""
    if not zeilen:
        return 0
    # `executemany` (eine Anweisung, viele Parametersätze) statt eines VALUES-Blocks: kein
    # Variablen-Limit, und SQLAlchemy baut die Anweisung nur einmal.
    # Über die Verbindung der Sitzung (dieselbe Transaktion, derselbe SAVEPOINT): nur deren
    # Ergebnis trägt bei `executemany` die Zahl der wirklich eingefügten Zeilen.
    conn = await db.connection()
    res = await conn.execute(
        sqlite_insert(KanalStatistik).on_conflict_do_nothing(index_elements=["kanal_id", "start_ts"]),
        zeilen,
    )
    if res.rowcount:
        # HA-Bauform S5 E-S5-1c (S5-R7c i): gemerkte Kanal-Tage ab dem Tag des vorigen Stands verwerfen.
        ab_ts = min(int(z["start_ts"]) for z in zeilen)
        for anlage_id, von in (await merken.tag_des_vorstands(db, {z["kanal_id"] for z in zeilen}, ab_ts)).items():
            merken.invalidiere(anlage_id, von=von, db=db)
    return res.rowcount


def _zeile(kanal_id: int, start_ts: int, familie: str, *, sum=None, state=None, mean=None) -> dict:
    return {"kanal_id": kanal_id, "start_ts": start_ts, "sum": sum, "state": state,
            "mean": mean, "min": None, "max": None, "familie": familie}


# ── Gemeinsamer Kontext eines Laufs ─────────────────────────────────────────


@dataclass
class _Kontext:
    anlage: Any
    zeitpunkt: datetime
    counter_map: dict[str, str]
    invs: dict[str, Any]
    stillgelegt: frozenset[str] = frozenset()


async def _kontext(db: AsyncSession, anlage, zeitpunkt: datetime) -> _Kontext:
    from backend.models.investition import Investition
    from backend.services.snapshot.writer import _build_counter_map, _stillgelegte_inv_ids

    invs = {str(i.id): i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()}
    still = await _stillgelegte_inv_ids(db, anlage.id)
    return _Kontext(anlage, zeitpunkt, _build_counter_map(anlage, still), invs, frozenset(still))


def _art_und_einheit(sensor_key: str, invs: dict[str, Any]) -> tuple[Optional[str], str]:
    inv = invs.get(sensor_key.split(":")[1]) if sensor_key.startswith("inv:") else None
    art = zaehler_art(sensor_key, getattr(inv, "typ", None))
    if art == ART_SUM:
        return art, "kWh"
    if art == ART_STAND:
        return art, einheit_fuer(basis_feld_key(sensor_key.rpartition(":")[2]), inv)
    return art, ""


def _tagesgroesse(sensor_key: str, invs: dict[str, Any]) -> bool:
    """Katalog-Klasse „Tagesgröße ohne Kanal" (#110, V2H): kein Kanal ist hier Absicht, keine Lücke im Katalog."""
    inv = invs.get(sensor_key.split(":")[1]) if sensor_key.startswith("inv:") else None
    return ist_tagesgroesse_ohne_kanal(sensor_key, getattr(inv, "typ", None))


# ── Spiegel (HA) ────────────────────────────────────────────────────────────


def _mengen_faktor(meta) -> Optional[float]:
    """Einheiten-Faktor einer Menge — dieselbe Regel wie ``HAStatisticsService._value_at_wert``.

    ``None``: der heutige Leser liefert für diesen Sensor nichts (Leistungssensor ohne ``sum`` und
    ohne Energie-Einheit, #200) — dann spiegelt der Kanal ihn auch nicht.
    """
    from backend.services.ha_statistics_service import _ENERGY_UNIT_TO_KWH

    if not meta.has_sum and (not meta.unit or meta.unit not in _ENERGY_UNIT_TO_KWH):
        return None
    return _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0


def _mal(wert, faktor: float) -> Optional[float]:
    if wert is None:
        return None
    return float(wert) * faktor if faktor != 1.0 else float(wert)


async def _spiegel(db: AsyncSession, k: _Kontext, ha_svc) -> int:
    ts_bis = _unix(k.zeitpunkt - timedelta(hours=1))
    gewuenscht: dict[str, tuple[str, str]] = {}
    for sensor_key in k.counter_map:
        art, einheit = _art_und_einheit(sensor_key, k.invs)
        if art is None:
            if not _tagesgroesse(sensor_key, k.invs):   # #110: bewusst ohne Kanal — still
                logger.warning("Kanal-Spiegel: %s hat keine Kanal-Art im Katalog — übersprungen", sensor_key)
            continue
        gewuenscht[sensor_key] = (art, einheit)
    if not gewuenscht:
        return 0
    # ⭐ **Nur die Kanäle, die es schon gibt** (Lab-Durchlauf 4.1.3-rc1, 07.10.2026). Ein fehlender Kanal entsteht
    # erst unten, wenn HA für seinen Sensor eine Zeile liefert — wie in `_mean_spiegel` und wie es
    # `nachfuellen_spiegel(nur_vorhandene=True)` voraussetzt. Bis dahin legte `_staende` (über `kanaele_holen`)
    # jeden zugeordneten Zähler sofort an, auch ohne Langzeitstatistik: zurück blieb ein leerer Kanal ohne
    # `kanal_quelle`, der Anstoß fand ihn ohne Marke, fragte HA ein zweites Mal und protokollierte das Nachfüllen
    # ein zweites Mal (gemessen an Anlage 4 im Lab). Probe:
    # `test_kanal_nachfuellen.py::test_sensor_ohne_statistik_startlauf_stundenlauf_anstoss_legt_keinen_kanal_an`.
    da = {kn.key: kn for kn in (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == k.anlage.id, Kanal.key.in_(list(gewuenscht))))
    )).scalars().all()}
    ids = [kn.id for kn in da.values()]
    letzte = await letzte_zeilen(db, ids, nah_ab=ts_bis - _NAH_STUNDEN * _STUNDE)
    quellen = await aktuelle_quellen(db, ids)
    staende: dict[str, _KanalStand] = {
        key: _KanalStand(kn, letzte.get(kn.id), quellen.get(kn.id)) for key, kn in da.items()
    }

    # Erster Lauf eines Kanals: nur die eben abgeschlossene Stunde — kein Nachfüllen (E2).
    ts_nach: dict[str, int] = {
        key: (staende[key].letzte.start_ts if key in staende and staende[key].letzte is not None else ts_bis - 1)
        for key in gewuenscht
    }
    je_entity: dict[str, float] = {}
    for key, ab in ts_nach.items():
        if ab < ts_bis:
            eid = k.counter_map[key]
            je_entity[eid] = min(ab, je_entity.get(eid, ab))
    if not je_entity:
        return 0
    gelesen = await asyncio.to_thread(ha_svc.get_stundenzeilen_mehrere, je_entity, ts_bis)

    neue_zeilen: list[dict] = []
    for key in gewuenscht:
        eid = k.counter_map[key]
        if eid not in gelesen:
            continue
        meta, roh = gelesen[eid]
        roh = [z for z in roh if z["start_ts"] > ts_nach[key]]
        if not roh:
            continue
        st = staende.get(key)
        art = st.kanal.art if st is not None else gewuenscht[key][0]
        faktor = 1.0 if art == ART_STAND else _mengen_faktor(meta)   # ein Stand wird nie umgerechnet (F-58)
        if faktor is None:
            continue
        if st is None:
            st = _KanalStand((await kanaele_holen(db, k.anlage.id, {key: gewuenscht[key]}))[key], None, None)
            staende[key] = st
        zeilen = [_zeile(st.kanal.id, int(round(z["start_ts"])), FAMILIE_SPIEGEL,
                         sum=_mal(z["sum"], faktor), state=_mal(z["state"], faktor)) for z in roh]
        if st.quelle is None or st.quelle.familie != FAMILIE_SPIEGEL or st.quelle.statistic_id != eid:
            await _neue_spiegel_quelle(db, ha_svc, st, eid, zeilen, faktor)
        neue_zeilen.extend(zeilen)
    return await _zeilen_einfuegen(db, neue_zeilen)


async def _neue_spiegel_quelle(db, ha_svc, st: _KanalStand, eid: str, zeilen: list[dict], faktor: float) -> None:
    """Sensortausch (oder erster Eintrag): ``offset`` so, dass ``Wert + offset`` stetig weiterläuft.

    Anker ist die Zeile des NEUEN Sensors zur letzten Kanal-Stunde (oder davor). Ohne Anker beginnt
    eine Menge (``sum``) bei 0 — die erste Stunde zählt mit ihrem Zuwachs —, ein Stand ohne Δ.

    **Leseregel ``stand`` (Nachmessung E1, 06.10.):** Der Stand ist immer ``state`` roh — die Zahl auf
    dem Zähler (F-58). ``offset`` dient bei ``stand`` nur der Differenz über eine Quellgrenze, nie als
    Kanalwert.

    Anker ist die Zeile des NEUEN Sensors zur letzten Kanal-Stunde (oder davor) — dann trägt die
    erste neue Stunde den eigenen Zuwachs des neuen Sensors. Ohne Anker beginnt er ohne Zuwachs.
    """
    art = st.kanal.art
    spalte = _wertspalte(art)
    offset = 0.0
    bisher = _kanal_wert(st.letzte, st.quelle, art)
    if bisher is not None:
        anker = await asyncio.to_thread(ha_svc.get_stundenzeile_bis, eid, st.letzte.start_ts)
        anker_wert = _mal(anker.get(spalte), faktor) if anker is not None else None
        if anker_wert is None:
            # Ohne Ankerzeile (fabrikneuer Sensor): HAs Summe beginnt bei 0, die erste Zeile trägt
            # schon den Zuwachs ihrer Stunde — wie im MQTT-Pfad (`offset = bisher`). Beim Stand gibt
            # es keinen Nullpunkt; die erste Stunde bleibt dort ohne Δ.
            anker_wert = 0.0 if art == ART_SUM else zeilen[0][spalte]
        if anker_wert is not None:
            offset = bisher - anker_wert
    db.add(KanalQuelle(kanal_id=st.kanal.id, gueltig_ab=zeilen[0]["start_ts"], familie=FAMILIE_SPIEGEL,
                       statistic_id=eid, offset=offset))
    await db.flush()


async def schreibe_spiegel(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, ha_svc=None, kontext: Optional[_Kontext] = None,
) -> int:
    """Spiegel aller zugeordneten Zähler bis zur Stunde vor ``zeitpunkt`` (HA ``start_ts``)."""
    from backend.services.ha_statistics_service import get_ha_statistics_service

    ha_svc = ha_svc or get_ha_statistics_service()
    if not ha_svc.is_available:
        return 0
    k = kontext or await _kontext(db, anlage, zeitpunkt)
    n = await _spiegel(db, k, ha_svc) if k.counter_map else 0
    return n + await _mean_spiegel(db, k, ha_svc)


# ── Spiegel mean (HA) ───────────────────────────────────────────────────────

#: Einmal je Kanal und Tag: ``(anlage_id, key) → Tag der letzten Warnung`` (kein Log-Spam stündlich).
_EINHEIT_GEWARNT: dict[tuple[int, str], date] = {}


def _mean_zuordnung(k: _Kontext) -> dict[str, str]:
    """``{kanal_key: entity_id}`` der zugeordneten Mittelwert-Felder — die Leseart des Live-Pfads.

    Grundlage ``extract_live_config`` (``basis.live``, ``investitionen[*].live`` ohne Zustandsfelder,
    Legacy ``live_sensors``); eine ``quellen``-Zuordnung (C2a) auf HA ersetzt die Entität, eine auf
    MQTT oder „keine" nimmt das Feld aus dem HA-Lesen (wie ``live_power_service._apply_quellen_overrides``
    bzw. ``snapshot/keys.resolve_energy_ha_eid``). Preis: ``_helpers.strompreis_sensor_id``.
    Stillgelegte Geräte fallen heraus wie beim Zähler-Spiegel.
    """
    from backend.services.energie_profil._helpers import strompreis_sensor_id
    from backend.services.live_sensor_config import extract_live_config, extract_quellen_live
    from backend.services.snapshot.keys import QUELLE_HA_ENERGY

    basis_live, inv_live_map, _bi, _ii = extract_live_config(k.anlage)
    quellen_basis, quellen_inv, _ha = extract_quellen_live(k.anlage)
    out: dict[str, str] = {f"basis:{key}": eid for key, eid in basis_live.items() if eid}
    for inv_id, live in inv_live_map.items():
        out.update({f"inv:{inv_id}:{key}": eid for key, eid in live.items() if eid})

    def _ueberschreiben(sk: str, tup) -> None:
        quelle, eid = tup[0], tup[1]
        if quelle in QUELLE_HA_ENERGY and eid:
            out[sk] = eid
        else:
            out.pop(sk, None)

    for key, tup in quellen_basis.items():
        _ueberschreiben(f"basis:{key}", tup)
    for inv_id, keys in quellen_inv.items():
        for key, tup in keys.items():
            _ueberschreiben(f"inv:{inv_id}:{key}", tup)
    preis = strompreis_sensor_id(k.anlage.sensor_mapping)
    if preis:
        out["basis:strompreis"] = preis

    def _gilt(sk: str) -> bool:
        if sk.startswith("inv:"):
            inv_id = sk.split(":")[1]
            if inv_id in k.stillgelegt:
                return False
            return ist_mean_kanal(sk, getattr(k.invs.get(inv_id), "typ", None))
        return ist_mean_kanal(sk, None)

    return {sk: eid for sk, eid in out.items() if _gilt(sk)}


async def _mean_spiegel(db: AsyncSession, k: _Kontext, ha_svc) -> int:
    zuordnung = _mean_zuordnung(k)
    if not zuordnung:
        return 0
    ts_bis = _unix(k.zeitpunkt - timedelta(hours=1))
    da = {kn.key: kn for kn in (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == k.anlage.id, Kanal.key.in_(list(zuordnung))))
    )).scalars().all()}
    ids = [kn.id for kn in da.values()]
    letzte = await letzte_zeilen(db, ids, nah_ab=ts_bis - _NAH_STUNDEN * _STUNDE)
    quellen = await aktuelle_quellen(db, ids)
    # Erster Lauf eines Kanals: nur die eben abgeschlossene Stunde — kein Nachfüllen (E2).
    ts_nach = {sk: (letzte[da[sk].id].start_ts if sk in da and da[sk].id in letzte else ts_bis - 1)
               for sk in zuordnung}
    je_entity: dict[str, float] = {}
    for sk, ab in ts_nach.items():
        if ab < ts_bis:
            eid = zuordnung[sk]
            je_entity[eid] = min(ab, je_entity.get(eid, ab))
    if not je_entity:
        return 0
    gelesen = await asyncio.to_thread(ha_svc.get_stundenzeilen_mehrere, je_entity, ts_bis)

    zeilen: list[dict] = []
    tag = k.zeitpunkt.date()
    for sk, eid in sorted(zuordnung.items()):
        if eid not in gelesen:
            continue                      # keine Langzeitstatistik ⇒ kein Spiegel (eine HA-Entität sperrt die MQTT-Mitschrift, G1)
        meta, roh = gelesen[eid]
        roh = [z for z in roh if z["start_ts"] > ts_nach[sk] and z["mean"] is not None]
        if not roh:
            continue
        einheit = meta.unit or ""
        kanal = da.get(sk)
        if kanal is None:
            kanal = Kanal(anlage_id=k.anlage.id, key=sk, art=ART_MEAN, einheit=einheit)
            db.add(kanal)
            await db.flush()
            da[sk] = kanal
        elif kanal.einheit != einheit:
            schl = (k.anlage.id, sk)
            if _EINHEIT_GEWARNT.get(schl) != tag:
                _EINHEIT_GEWARNT[schl] = tag
                logger.warning(
                    "Kanal-Spiegel mean %s: Sensor %s meldet „%s“, der Kanal führt „%s“ — nicht "
                    "geschrieben (keine Umrechnung im Schreiber)", sk, eid, einheit, kanal.einheit,
                )
            continue
        q = quellen.get(kanal.id)
        start = int(round(roh[0]["start_ts"]))
        if q is None or q.familie != FAMILIE_SPIEGEL or q.statistic_id != eid:
            db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=start, familie=FAMILIE_SPIEGEL,
                               statistic_id=eid, offset=0.0))
        zeilen.extend(
            {"kanal_id": kanal.id, "start_ts": int(round(z["start_ts"])), "sum": None, "state": None,
             "mean": float(z["mean"]), "min": None if z["min"] is None else float(z["min"]),
             "max": None if z["max"] is None else float(z["max"]), "familie": FAMILIE_SPIEGEL}
            for z in roh
        )
    if zeilen:
        await db.flush()
    return await _zeilen_einfuegen(db, zeilen)


# ── Mittelwert-Mitschrift (MQTT, HA-Bauform §9, Standalone-Gleichstand S2) ───

#: Länge eines Snapshot-Fensters (``mqtt_live_history_service``, ``IntervalTrigger(minutes=5)``) — die Obergrenze des
#: Gewichts einer 5-Minuten-Zeile: eine Lücke davor (Broker weg, Neustart) zählt nicht als gemessene Zeit.
_SNAPSHOT_FENSTER = 300


def fenster_gewicht(ts: int, vorher: Optional[int]) -> float:
    """Gewicht einer 5-Minuten-Zeile in ihrer Stunde — **die eine Mittelungsregel des MQTT-Pfads** (Standalone-Gleichstand S3).

    Gerufen von ``mittel_je_stunde`` (Mittelwerte, je Key) und ``modus_anteile_je_stunde`` (Betriebsart-Anteile, je
    Gerät). Gewicht = Abstand ``ts − vorher`` zur vorigen Zeile derselben Reihe als Anteil eines Snapshot-Fensters,
    höchstens 1 (``_SNAPSHOT_FENSTER``): eine Lücke davor (Broker weg, Neustart) zählt nicht als gemessene Zeit, die
    Stunde ist das Mittel der vorhandenen Zeilen (E-SG-9). Ohne Vorgänger 1. ``≤ 0`` (zwei Zeilen in derselben
    Sekunde) ⇒ die Zeile zählt nicht. Bei regelmäßigem Takt ist jedes Gewicht genau ``1.0`` — das gewichtete Mittel
    ist dann das einfache, auch im letzten Bit (``1.0 · x`` und ``Σ 1.0`` sind exakt).
    """
    if vorher is None:
        return 1.0
    return min(_SNAPSHOT_FENSTER, ts - vorher) / _SNAPSHOT_FENSTER


def mqtt_live_statistic_id(kanal_key: str) -> str:
    """``kanal_quelle.statistic_id`` einer MQTT-Live-Mitschrift — der MQTT-Schlüssel nach dem Topic-Pfad
    (``inv:7:vorlauf_temperatur_c`` → ``mqtt:inv/7/vorlauf_temperatur_c``, ``basis:netzbezug_w`` → ``mqtt:netzbezug_w``;
    E-SG-4). Dieselbe Form wie ``mqtt_modus_statistic_id``."""
    teile = kanal_key.split(":")
    return "mqtt:" + "/".join(teile[1:] if teile[0] == "basis" else teile)


def _mitschrift_feld(sk: str, k: _Kontext) -> Optional[tuple[Optional[str], str, Optional[str], Optional[dict]]]:
    """Snapshot-Key → ``(inv_id | None, feld, typ, parameter)``; ``None`` für einen Key ohne Gerät oder mit
    stillgelegtem Gerät (Gerät aktiv, G1 (4) — dieselbe Grenze wie ``_mean_zuordnung``)."""
    teile = sk.split(":")
    if teile[0] == "basis" and len(teile) == 2:
        return None, teile[1], None, None
    if teile[0] != "inv" or len(teile) != 3:
        return None            # Modus-Zeile (``inv:<id>:betriebsmodus:<modus>``) oder fremd
    inv = k.invs.get(teile[1])
    if inv is None or teile[1] in k.stillgelegt:
        return None
    parameter = getattr(inv, "parameter", None)
    return teile[1], teile[2], getattr(inv, "typ", None), parameter if isinstance(parameter, dict) else None


def _mean_mitschrift_zuordnung(k: _Kontext, keys) -> dict[str, str]:
    """``{kanal_key: Registry-Einheit}`` der Snapshot-Keys, die eine Mitschrift-Zeile bekommen (G1, Zähler-Regel):

    (1) der Key hat Zeilen (der Aufrufer reicht nur solche) — «Wert entscheidet»; (2) er liegt **nicht** in
    ``_mean_zuordnung(k)`` — jede HA-Entität in ``live``/``quellen``-HA macht ihn zum HA-Feld, auch ohne
    Langzeitstatistik (dort bleibt die Checker-INFO; nie zwei Familien im Kanal); (3) seine ``quellen``-Wahl ist keine
    andere als Inbound/Gateway (HA oder «keine» schließen aus — dieselbe Regel wie ``mqtt_modus_geraete``); (4) das Gerät
    ist aktiv. Dazu muss er ein Mittelwert-Feld sein (``mittelwert_live_keys``: kein Preis, kein Modus).
    """
    from backend.services.kanal.katalog import mittelwert_live_keys
    from backend.services.live_sensor_config import extract_quellen_live
    from backend.services.snapshot.keys import QUELLE_MQTT_ENERGY

    ha_felder = set(_mean_zuordnung(k))
    quellen_basis, quellen_inv, _ha = extract_quellen_live(k.anlage)
    out: dict[str, str] = {}
    for sk in sorted(keys):
        feld = _mitschrift_feld(sk, k) if sk not in ha_felder else None
        if feld is None:
            continue
        inv_id, key, typ, parameter = feld
        wahl = (quellen_basis if inv_id is None else quellen_inv.get(inv_id) or {}).get(key)
        if wahl is not None and wahl[0] not in QUELLE_MQTT_ENERGY:
            continue
        einheit = mittelwert_live_keys(typ, parameter).get(key)
        if einheit is not None:
            out[sk] = einheit
    return out


async def _mittel_snapshot_keys(db: AsyncSession, anlage_id: int, *, von: int, bis: int) -> list[str]:
    """Die Snapshot-Keys mit Zeilen in ``[von, bis)`` (nur Zeilen mit ``ts_unix``; Modus-Zeilen fallen später heraus)."""
    from backend.models.mqtt_live_snapshot import MqttLiveSnapshot

    return list((await db.execute(
        select(MqttLiveSnapshot.component_key).where(and_(
            MqttLiveSnapshot.anlage_id == anlage_id,
            MqttLiveSnapshot.ts_unix.is_not(None),
            MqttLiveSnapshot.ts_unix >= von, MqttLiveSnapshot.ts_unix < bis,
        )).distinct()
    )).scalars().all())


async def _mittel_snapshot_zeilen(db: AsyncSession, anlage_id: int, keys: list[str], *, von: int,
                                  bis: int) -> dict[str, list[tuple[int, float, Optional[float], Optional[float]]]]:
    """Die 5-Minuten-Zeilen ``{key: [(ts_unix, mittel, min, max)]}`` in ``[von, bis)``, nach Zeit."""
    from backend.models.mqtt_live_snapshot import MqttLiveSnapshot

    out: dict[str, list[tuple[int, float, Optional[float], Optional[float]]]] = {}
    for key, ts, wert, lo, hi in (await db.execute(
        select(MqttLiveSnapshot.component_key, MqttLiveSnapshot.ts_unix, MqttLiveSnapshot.value_w,
               MqttLiveSnapshot.min, MqttLiveSnapshot.max).where(and_(
            MqttLiveSnapshot.anlage_id == anlage_id,
            MqttLiveSnapshot.component_key.in_(keys),
            MqttLiveSnapshot.ts_unix.is_not(None),
            MqttLiveSnapshot.ts_unix >= von, MqttLiveSnapshot.ts_unix < bis,
        )).order_by(MqttLiveSnapshot.ts_unix)
    )).all():
        out.setdefault(key, []).append((int(ts), float(wert), lo, hi))
    return out


def mittel_je_stunde(zeilen) -> list[tuple[int, float, float, float]]:
    """5-Minuten-Zeilen eines Keys → ``[(start_ts, mean, min, max)]`` je Stunde (rein, HA-Bauform §9, E-SG-8).

    Stunde = die lokale volle Stunde über ``_stunden_start_ts`` aus ``ts_unix`` (mit ``fold``: Herbst zwei Stunden) —
    dieselbe Regel wie Modus-Mitschrift und eigene Summe; eine Zeile gehört zur Stunde ihres Abschlusses.
    **Längengewichtet** über die ``ts_unix``-Differenzen mit ``fenster_gewicht`` (derselben Regel wie die
    Betriebsart-Anteile): Abstand zur vorigen Zeile, höchstens ein Snapshot-Fenster, ohne Vorgänger ein Fenster — eine
    Lücke (Broker weg, Neustart) zählt nicht als gemessene Zeit, die Stunde ist das Mittel der vorhandenen Zeilen
    (E-SG-9). ``min``/``max`` = Extrema der Fenster (ohne Spalte: das Fenster-Mittel). Eine Stunde ohne Zeilen fehlt.
    """
    je_stunde: dict[int, list[float]] = {}     # start_ts → [Σ Gewicht·Mittel, Σ Gewicht, min, max]
    vorher: Optional[int] = None
    for ts, mittel, lo, hi in sorted(zeilen, key=lambda z: z[0]):
        gewicht = fenster_gewicht(ts, vorher)
        vorher = ts
        if gewicht <= 0:
            continue                          # zwei Zeilen in derselben Sekunde: die erste zählt
        lo = mittel if lo is None else float(lo)
        hi = mittel if hi is None else float(hi)
        stunde = _stunden_start_ts(datetime.fromtimestamp(ts))
        acc = je_stunde.get(stunde)
        if acc is None:
            je_stunde[stunde] = [gewicht * mittel, gewicht, lo, hi]
        else:
            acc[0] += gewicht * mittel
            acc[1] += gewicht
            acc[2] = min(acc[2], lo)
            acc[3] = max(acc[3], hi)
    return [(stunde, acc[0] / acc[1], acc[2], acc[3]) for stunde, acc in sorted(je_stunde.items())]


def _mitschrift_ab(st: Optional[_KanalStand], sid: str, bis: int) -> int:
    """Erste Stunde, die die Mitschrift für diesen Kanal schreiben darf: nach der letzten Zeile des Kanals; bei neuer
    Quelle (kein Kanal, Spiegel davor, anderer Schlüssel) nur die eben abgeschlossene Stunde (E2, nicht rückwirkend)."""
    neu = st is None or st.quelle is None or st.quelle.familie != FAMILIE_MITSCHRIFT or st.quelle.statistic_id != sid
    letzte = st.letzte.start_ts + _STUNDE if st is not None and st.letzte is not None else None
    ab = bis - _STUNDE if neu or letzte is None else max(letzte, bis - _NAH_STUNDEN * _STUNDE)
    return max(ab, letzte) if letzte is not None else ab


async def _mean_mitschrift_zeilen(db: AsyncSession, k: _Kontext, st: Optional[_KanalStand], sk: str, einheit: str,
                                  stunden: list[tuple[int, float, float, float]]) -> list[dict]:
    """Kanal (Registry-Einheit) und Quelle (``mitschrift``/MQTT-Schlüssel, Offset 0) — dann die Zeilen der Stunden."""
    sid = mqtt_live_statistic_id(sk)
    if st is None:
        kanal = (await kanaele_holen(db, k.anlage.id, {sk: (ART_MEAN, einheit)}))[sk]
        st = _KanalStand(kanal, None, None)
    elif st.kanal.einheit != einheit:
        schl = (k.anlage.id, sk)
        if _EINHEIT_GEWARNT.get(schl) != k.zeitpunkt.date():
            _EINHEIT_GEWARNT[schl] = k.zeitpunkt.date()
            logger.warning("Kanal-Mitschrift mean %s: die Registry führt „%s“, der Kanal „%s“ — nicht geschrieben "
                           "(keine Umrechnung im Schreiber)", sk, einheit, st.kanal.einheit)
        return []
    if st.quelle is None or st.quelle.familie != FAMILIE_MITSCHRIFT or st.quelle.statistic_id != sid:
        # Quellenwechsel wie «Eigene Summe»: die neue Quelle gilt ab ihrer ersten Stunde.
        db.add(KanalQuelle(kanal_id=st.kanal.id, gueltig_ab=stunden[0][0], familie=FAMILIE_MITSCHRIFT,
                           statistic_id=sid, offset=0.0))
        await db.flush()
    return [{"kanal_id": st.kanal.id, "start_ts": start, "sum": None, "state": None, "mean": mittel,
             "min": lo, "max": hi, "familie": FAMILIE_MITSCHRIFT} for start, mittel, lo, hi in stunden]


async def _mean_mitschrift(db: AsyncSession, k: _Kontext) -> int:
    """Phase des Stundenlaufs: Mittelwert-Mitschrift aus den 5-Minuten-Snapshots des MQTT-Inbound (HA-Bauform §9, S2-2).

    Zuordnung (G1) · 5-Minuten-Zeilen lesen · Stunde verdichten (``mittel_je_stunde``) · Zeilen bauen. Nur
    abgeschlossene Stunden (``bis`` = Beginn der laufenden), eine schon geschriebene Stunde nie neu (``ON CONFLICT DO
    NOTHING``). Unabhängig davon, ob HA erreichbar ist — der Spiegel davor fragt HA, diese Phase nicht.
    """
    bis = _stunden_start_ts(k.zeitpunkt)
    auswahl = _mean_mitschrift_zuordnung(k, await _mittel_snapshot_keys(db, k.anlage.id, von=bis - _STUNDE, bis=bis))
    if not auswahl:
        return 0
    da = {kn.key: kn for kn in (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == k.anlage.id, Kanal.key.in_(list(auswahl))))
    )).scalars().all()}
    ids = [kn.id for kn in da.values()]
    letzte = await letzte_zeilen(db, ids, nah_ab=bis - _NAH_STUNDEN * _STUNDE)
    quellen = await aktuelle_quellen(db, ids)
    staende = {sk: _KanalStand(kn, letzte.get(kn.id), quellen.get(kn.id)) for sk, kn in da.items()}
    ab_je = {sk: _mitschrift_ab(staende.get(sk), mqtt_live_statistic_id(sk), bis) for sk in auswahl}
    offen = [sk for sk, ab in ab_je.items() if ab < bis]
    if not offen:
        return 0
    roh = await _mittel_snapshot_zeilen(db, k.anlage.id, offen, von=min(ab_je[sk] for sk in offen) - _SNAPSHOT_FENSTER,
                                        bis=bis)
    zeilen: list[dict] = []
    for sk in offen:
        stunden = [z for z in mittel_je_stunde(roh.get(sk, ())) if ab_je[sk] <= z[0] and z[0] + _STUNDE <= bis]
        if stunden:
            zeilen.extend(await _mean_mitschrift_zeilen(db, k, staende.get(sk), sk, auswahl[sk], stunden))
    return await _zeilen_einfuegen(db, zeilen)


async def schreibe_mean_mitschrift(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, kontext: Optional[_Kontext] = None,
) -> int:
    """Die Mittelwert-Mitschrift aus MQTT für eine Anlage (Einstieg für Proben; im Betrieb ruft der Stundenlauf die Phase)."""
    return await _mean_mitschrift(db, kontext or await _kontext(db, anlage, zeitpunkt))


# ── Eigene Summe (MQTT-Rohstände) ───────────────────────────────────────────


def _stunde_von(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _stunden_start_ts(zeit: datetime) -> int:
    """``start_ts`` der lokalen vollen Stunde, die ``zeit`` enthält — **die eine Stundenregel der MQTT-Familien**.

    Gerufen von der eigenen Summe (Rohstände) und der Betriebsart-Mitschrift aus MQTT (HA-Bauform §9), damit Strom und
    Modus derselben Stunde denselben ``start_ts`` tragen — keine zweite Rechnung ``ts − ts % 3600``. ``fold`` bleibt
    erhalten (``replace``), eine aus Unix-Sekunden gebildete Zeit (``datetime.fromtimestamp``) trennt deshalb die
    Herbst-Doppelstunde.
    """
    return _unix(_stunde_von(zeit))


def _deckel_achse(inv, feld: str) -> bool:
    """Liegt das Feld auf einer gedeckelten Achse? Zuordnung wie Tagespfad und Monatswert:
    ``_categorize_counter`` → ``achse_der_kategorie`` ∈ ``ACHSEN_MIT_DECKEL``."""
    from backend.services.snapshot.keys import _categorize_counter

    kat = _categorize_counter(feld, getattr(inv, "typ", None) if inv is not None else None,
                              getattr(inv, "parameter", None) if inv is not None else None)
    return achse_der_kategorie(kat) in ACHSEN_MIT_DECKEL


async def _laufbeginn(db: AsyncSession, kanal_id: int, letzte: KanalStatistik) -> int:
    """``start_ts`` der ersten Zeile im letzten Lauf unveränderter Summe (R3 Nachträge II: das
    Deckel-Fenster ist die Zeit seit der letzten Änderung). Gesucht wird nur so weit zurück, wie das
    Fenster reicht (``DECKEL_FENSTER_MAX_STUNDEN``) — darüber hinaus ist das Fenster ohnehin voll."""
    grenze = letzte.start_ts - DECKEL_FENSTER_MAX_STUNDEN * _STUNDE
    geaendert = (await db.execute(
        select(KanalStatistik.start_ts).where(and_(
            KanalStatistik.kanal_id == kanal_id,
            KanalStatistik.start_ts >= grenze,
            func.abs(KanalStatistik.sum - letzte.sum) > _TOL,
        )).order_by(KanalStatistik.start_ts.desc()).limit(1)
    )).scalar_one_or_none()
    erste = (await db.execute(
        select(func.min(KanalStatistik.start_ts)).where(and_(
            KanalStatistik.kanal_id == kanal_id,
            KanalStatistik.start_ts > (geaendert if geaendert is not None else grenze - 1),
        ))
    )).scalar_one_or_none()
    return erste if erste is not None else letzte.start_ts


async def _eigene_summe_zeilen(
    db: AsyncSession, k: _Kontext, st: _KanalStand, sensor_key: str, mqtt_key: str,
    staende: list[tuple[datetime, float]],
) -> list[dict]:
    from backend.services.snapshot.plausibility import (
        cap_pv_einspeisung_stunde,
        schwelle_pv_einspeisung_stunde_kwh,
    )

    art, kanal = st.kanal.art, st.kanal
    je_stunde: dict[datetime, list[float]] = {}
    for ts, wert in staende:
        je_stunde.setdefault(_stunde_von(ts), []).append(wert)

    neue_quelle = st.quelle is None or st.quelle.familie != FAMILIE_MITSCHRIFT or st.quelle.statistic_id != mqtt_key
    letzte = st.letzte if not neue_quelle else None
    vorher: Optional[PeriodenSumme] = None
    if letzte is not None and letzte.state is not None:
        vorher = PeriodenSumme(sum=float(letzte.sum or 0.0), state=float(letzte.state))
    letzter_ts = letzte.start_ts if letzte is not None else None
    feld = basis_feld_key(sensor_key.rpartition(":")[2])
    inv = k.invs.get(sensor_key.split(":")[1]) if sensor_key.startswith("inv:") else None
    gedeckelt = art == ART_SUM and _deckel_achse(inv, feld)
    lauf_ab = (await _laufbeginn(db, kanal.id, letzte)) if (gedeckelt and letzte is not None and letzte.sum is not None) else None

    zeilen: list[dict] = []
    for stunde in sorted(je_stunde):
        start_ts = _stunden_start_ts(stunde)
        werte = je_stunde[stunde]
        if art == ART_STAND:
            gueltig = [float(w) for w in werte if w is not None and float(w) >= 0]
            if gueltig:
                zeilen.append(_zeile(kanal.id, start_ts, FAMILIE_MITSCHRIFT, state=gueltig[-1]))
            continue
        ergebnis = ha_summe_der_periode(vorher, werte)
        if ergebnis is None:
            continue
        basis_summe = vorher.sum if vorher is not None else 0.0
        if gedeckelt:
            n = max(1, (start_ts - letzter_ts) // _STUNDE) if letzter_ts is not None else 1
            seit = ((start_ts - lauf_ab) // _STUNDE) if lauf_ab is not None else n
            # Die kWp der ANLAGE, wie der Tagespfad (`tages_tabelle.py`; der Monats-Deckel `monatswert_deckel.py`
            # ist seit HA-Bauform S5 E-S5-4 gestrichen) — keine Investitions-Nennleistung (P3-a betrifft sie nicht).
            anlage = k.anlage
            schwelle = schwelle_pv_einspeisung_stunde_kwh(getattr(anlage, "leistung_kwp", None),
                                                          spanne=deckel_fenster_stunden(n, seit))
            if schwelle is not None and cap_pv_einspeisung_stunde(
                ergebnis.sum - basis_summe, schwelle, anlage_id=k.anlage.id, datum=stunde.date(),
                stunde=stunde.hour, kategorie=f"kanal:{sensor_key}",
            ) is None:
                # Schreibfilter (R3): der Stand läuft weiter, der Zuwachs zählt nicht.
                ergebnis = PeriodenSumme(sum=basis_summe, state=ergebnis.state)
            if lauf_ab is None or abs(ergebnis.sum - basis_summe) > _TOL:
                lauf_ab = start_ts
        zeilen.append(_zeile(kanal.id, start_ts, FAMILIE_MITSCHRIFT, sum=ergebnis.sum, state=ergebnis.state))
        vorher, letzter_ts = ergebnis, start_ts

    if zeilen and neue_quelle:
        offset = 0.0
        bisher = _kanal_wert(st.letzte, st.quelle, art)
        erster = zeilen[0][_wertspalte(art)]
        if bisher is not None and erster is not None:
            # Die erste Stunde der neuen Quelle setzt am Kanal-Stand an: bei `sum` ist ihr Zuwachs
            # ab dem Nullpunkt schon in `erster`, beim Stand ist die Stunde ohne Δ.
            offset = bisher if art == ART_SUM else bisher - erster
        db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=zeilen[0]["start_ts"], familie=FAMILIE_MITSCHRIFT,
                           statistic_id=mqtt_key, offset=offset))
        await db.flush()
    return zeilen


async def _eigene_summe(db: AsyncSession, k: _Kontext) -> int:
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.snapshot.keys import (
        QUELLE_HA_ENERGY,
        QUELLE_KEINE_ENERGY,
        _mqtt_key_to_sensor_key,
        extract_quellen_energy,
    )

    bis = _stunde_von(k.zeitpunkt)
    keys = (await db.execute(
        select(MqttEnergySnapshot.energy_key).where(and_(
            MqttEnergySnapshot.anlage_id == k.anlage.id,
            MqttEnergySnapshot.timestamp >= bis - timedelta(hours=1),
            MqttEnergySnapshot.timestamp < bis,
        )).distinct()
    )).scalars().all()
    if not keys:
        return 0
    quellen_energy = extract_quellen_energy(k.anlage)
    auswahl: dict[str, str] = {}          # sensor_key → mqtt_key
    gewuenscht: dict[str, tuple[str, str]] = {}
    for mqtt_key in sorted(keys):
        sensor_key = _mqtt_key_to_sensor_key(mqtt_key)
        if not sensor_key or sensor_key in k.counter_map:
            continue
        zuord = quellen_energy.get(sensor_key)
        if zuord and (zuord[0] in QUELLE_HA_ENERGY or zuord[0] == QUELLE_KEINE_ENERGY):
            continue
        art, einheit = _art_und_einheit(sensor_key, k.invs)
        if art is None:
            if not _tagesgroesse(sensor_key, k.invs):   # #110: bewusst ohne Kanal — still
                logger.warning("Kanal eigene Summe: %s hat keine Kanal-Art im Katalog — übersprungen", sensor_key)
            continue
        auswahl[sensor_key] = mqtt_key
        gewuenscht[sensor_key] = (art, einheit)
    if not auswahl:
        return 0
    staende_kanal = await _staende(db, k.anlage.id, gewuenscht, _unix(bis) - _NAH_STUNDEN * _STUNDE)

    def _von(st: _KanalStand) -> datetime:
        v = (datetime.fromtimestamp(st.letzte.start_ts + _STUNDE) if st.letzte is not None
             else bis - timedelta(hours=1))   # erster Lauf: nur die eben abgeschlossene Stunde
        return max(v, bis - timedelta(days=MQTT_ROHSTAND_TAGE))

    von_je = {sk: _von(st) for sk, st in staende_kanal.items()}
    offen = {sk: v for sk, v in von_je.items() if v < bis}
    if not offen:
        return 0
    roh: dict[str, list[tuple[datetime, float]]] = {}
    for ek, ts, wert in (await db.execute(
        select(MqttEnergySnapshot.energy_key, MqttEnergySnapshot.timestamp, MqttEnergySnapshot.value_kwh)
        .where(and_(
            MqttEnergySnapshot.anlage_id == k.anlage.id,
            MqttEnergySnapshot.energy_key.in_([auswahl[sk] for sk in offen]),
            MqttEnergySnapshot.timestamp >= min(offen.values()),
            MqttEnergySnapshot.timestamp < bis,
        )).order_by(MqttEnergySnapshot.timestamp)
    )).all():
        roh.setdefault(ek, []).append((ts, wert))

    neue_zeilen: list[dict] = []
    for sensor_key, von in offen.items():
        mk = auswahl[sensor_key]
        staende = [(ts, w) for ts, w in roh.get(mk, ()) if ts >= von]
        if staende:
            neue_zeilen.extend(await _eigene_summe_zeilen(
                db, k, staende_kanal[sensor_key], sensor_key, mk, staende))
    return await _zeilen_einfuegen(db, neue_zeilen)


async def schreibe_eigene_summe(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, kontext: Optional[_Kontext] = None,
) -> int:
    """Eigene Summe aller MQTT-Zähler der Anlage bis zur Stunde vor ``zeitpunkt``.

    Auswahl wie der MQTT-Schritt des Bestands (``snapshot_anlage`` Schritt 2): MQTT-Schlüssel der
    letzten Stunde, übersetzt mit ``_mqtt_key_to_sensor_key``; ein per ``quellen`` HA- oder
    „keine"-zugeordnetes Feld schreibt MQTT nicht (C2b). Zusätzlich: ein Feld, das der Spiegel
    führt (``_build_counter_map``), bekommt keine zweite Familie aus MQTT.
    """
    return await _eigene_summe(db, kontext or await _kontext(db, anlage, zeitpunkt))


# ── Mitschrift Betriebsart ──────────────────────────────────────────────────


async def schreibe_betriebsart_mitschrift(
    db: AsyncSession, anlage, datum: date, modus_je_stunde, *, jetzt: Optional[datetime] = None,
) -> int:
    """„Anteil der Stunde je Betriebsart" je Wärmepumpe und abgeschlossener Stunde des Tages.

    ``modus_je_stunde`` ist das Ergebnis von ``_get_betriebsmodus_history``; es trägt die Anteile
    als ``.anteile`` (``{slot: {inv_id: {modus: anteil}}}``) und die Entität je Gerät als
    ``.entitaeten``. Ohne beides (z. B. eine ersetzte Probe, ein leerer Verlauf) schreibt die Funktion
    nichts.

    Slot ``h`` beschreibt ``[h-1, h)`` (BACKWARD, N-382); sein ``start_ts`` kommt aus der einen Umrechnung
    ``slot_start_ts`` (Frühjahrs-Slot ohne reale Stunde ⇒ keine Zeile). Geschrieben wird nur ein Slot, dessen Ende
    vor ``jetzt`` liegt — die Fortschreibung des letzten Zustands über eine laufende Stunde wäre eine
    Behauptung über die Zukunft und würde, einmal geschrieben, nie mehr korrigiert.
    Je Slot und Gerät entsteht eine Zeile in JEDEM Kanon-Modus (0 = gemessen nicht in diesem Modus);
    ein Slot ohne Signal bleibt in allen Modi leer („nicht hingesehen", nicht „aus").
    """
    anteile = getattr(modus_je_stunde, "anteile", None)
    entitaeten = getattr(modus_je_stunde, "entitaeten", None) or {}
    if not anteile:
        return 0
    jetzt_ts = _unix(jetzt or datetime.now())
    je_geraet: dict[int, list[tuple[int, dict]]] = {}
    for h, geraete in anteile.items():
        # Die EINE Umrechnung Slot → start_ts (`slot_konvention.slot_start_ts`, Umkehrung von
        # `lts_boundary_index`; HA-Bauform E2, B2). Frühjahr: die Wanduhr des Slots gibt es nicht ⇒ der Slot
        # beschreibt keine reale Zeit (seine „Anteile" wären nur der fortgeschriebene Zustand eines
        # leeren Fensters) und bekommt keine Zeile. Herbst: die SPÄTERE der beiden 02:00.
        # ⛔ Hier stand `_unix(tag0 + timedelta(hours=h - 1))` (fold=0): am 29.03. bekamen Slot 2 und 3
        # denselben Zeitstempel, `slots.sort()` verglich dann zwei dicts und warf — die ganze Tages-
        # Mitschrift rollte zurück.
        start_ts = slot_start_ts(datum, int(h))
        if start_ts is None or start_ts + _STUNDE > jetzt_ts:
            continue
        for inv_id, je_modus in geraete.items():
            je_geraet.setdefault(int(inv_id), []).append((start_ts, je_modus))
    return await _schreibe_betriebsart_anteile(db, anlage, je_geraet, entitaeten, jetzt_ts=jetzt_ts)


async def _schreibe_betriebsart_anteile(
    db: AsyncSession, anlage, je_geraet: dict[int, list[tuple[int, dict]]], entitaeten: dict, *, jetzt_ts: int,
) -> int:
    """Der **Kern** der Betriebsart-Mitschrift — Stunden als Unix-``start_ts``, gleich für HA und MQTT (E-SG-6).

    ``je_geraet`` ``{inv_id: [(start_ts, {modus: anteil})]}``, ``entitaeten`` ``{inv_id: statistic_id}`` der
    Quelle (HA: die `climate`-Entität; MQTT: ``mqtt_modus_statistic_id``). Geschrieben wird nur eine Stunde, deren
    Ende spätestens ``jetzt_ts`` liegt; je Stunde und Gerät eine Zeile in JEDEM Kanon-Modus (0 = gemessen nicht in
    diesem Modus); eine schon geschriebene Stunde wird nie überschrieben (``schon`` + ``ON CONFLICT DO NOTHING``).
    Die Hüllen: ``schreibe_betriebsart_mitschrift`` (HA, Slot-Form des Tages) und ``_betriebsart_mitschrift_mqtt``.
    """
    # Die Hülle des HA-Pfads filtert schon selbst (Reihenfolge der Kanal-Anlage bleibt byte-gleich); hier für jede Hülle.
    je_geraet = {
        inv_id: [(ts, je_modus) for ts, je_modus in slots if ts + _STUNDE <= jetzt_ts]
        for inv_id, slots in je_geraet.items()
    }
    je_geraet = {inv_id: slots for inv_id, slots in je_geraet.items() if slots}
    if not je_geraet:
        return 0
    gewuenscht = {modus_kanal_key(i, m): (ART_MEAN, EINHEIT_ANTEIL) for i in je_geraet for m in BETRIEBSMODUS_KANON}
    kanaele = await kanaele_holen(db, anlage.id, gewuenscht)
    ids = [k.id for k in kanaele.values()]
    quellen = await aktuelle_quellen(db, ids)
    alle_ts = [ts for slots in je_geraet.values() for ts, _ in slots]
    # Der Lauf „heute" kommt alle 15 Minuten: schon geschriebene Slots gar nicht erst anbieten
    # (das ON CONFLICT unten bliebe die Sicherung, aber jede Wiederholung kostete ein INSERT je Zeile).
    schon = set((await db.execute(
        select(KanalStatistik.kanal_id, KanalStatistik.start_ts).where(and_(
            KanalStatistik.kanal_id.in_(ids),
            KanalStatistik.start_ts >= min(alle_ts), KanalStatistik.start_ts <= max(alle_ts),
        ))
    )).all())
    zeilen: list[dict] = []
    for inv_id, slots in sorted(je_geraet.items()):
        slots.sort(key=lambda z: z[0])        # start_ts ist je Slot eindeutig (slot_start_ts)
        entity = entitaeten.get(inv_id)
        for modus in BETRIEBSMODUS_KANON:
            kanal = kanaele[modus_kanal_key(inv_id, modus)]
            q = quellen.get(kanal.id)
            if q is None or (q.statistic_id != entity and slots[0][0] > q.gueltig_ab):
                db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=slots[0][0], familie=FAMILIE_MITSCHRIFT,
                                   statistic_id=entity, offset=0.0))
            zeilen.extend(_zeile(kanal.id, ts, FAMILIE_MITSCHRIFT, mean=float(je_modus.get(modus, 0.0)))
                          for ts, je_modus in slots if (kanal.id, ts) not in schon)
    await db.flush()
    return await _zeilen_einfuegen(db, zeilen)


# ── Mitschrift Betriebsart aus MQTT (HA-Bauform §9, Standalone-Gleichstand S1) ──


def mqtt_modus_statistic_id(inv_id: int | str) -> str:
    """``kanal_quelle.statistic_id`` der MQTT-Modus-Mitschrift — der MQTT-Schlüssel des Geräts (E-SG-4/E-SG-6)."""
    return mqtt_live_statistic_id(f"inv:{inv_id}:betriebsmodus")


#: ``component_key`` der Modus-Zeilen in ``mqtt_live_snapshots`` (``inv:<id>:betriebsmodus:<modus>``).
_MODUS_SNAPSHOT_MUSTER = "inv:%:betriebsmodus:%"


def _mqtt_modus_wps(k: _Kontext) -> set[int]:
    """Die Wärmepumpen dieses Laufs, deren Modus aus MQTT kommt — nicht stillgelegt, ohne HA-Modus (eine Regel mit Live)."""
    from backend.services.betriebsmodus_live import mqtt_modus_geraete

    wps = {int(i) for i, inv in k.invs.items()
           if getattr(inv, "typ", None) == "waermepumpe" and i not in k.stillgelegt}
    return mqtt_modus_geraete(k.anlage, wps) if wps else set()


async def _modus_snapshot_zeilen(db: AsyncSession, anlage_id: int, geraete: set[int], *, von: int, bis: int) -> list:
    """Die Modus-Zeilen ``[ts_unix, component_key, anteil]`` der Geräte in ``[von, bis)`` — nur Zeilen mit ``ts_unix``."""
    from backend.models.mqtt_live_snapshot import MqttLiveSnapshot

    rows = (await db.execute(
        select(MqttLiveSnapshot.ts_unix, MqttLiveSnapshot.component_key, MqttLiveSnapshot.value_w).where(and_(
            MqttLiveSnapshot.anlage_id == anlage_id,
            MqttLiveSnapshot.ts_unix.is_not(None),
            MqttLiveSnapshot.ts_unix >= von, MqttLiveSnapshot.ts_unix < bis,
            MqttLiveSnapshot.component_key.like(_MODUS_SNAPSHOT_MUSTER),
        ))
    )).all()
    return [r for r in rows if _modus_zeile_geraet(r[1]) in geraete]


def _modus_zeile_geraet(component_key: str) -> Optional[int]:
    teile = component_key.split(":")
    return int(teile[1]) if len(teile) == 4 and teile[1].isdigit() else None


def modus_anteile_je_stunde(zeilen) -> dict[int, list[tuple[int, dict[str, float]]]]:
    """5-Minuten-Zeilen → ``{inv_id: [(start_ts, {modus: anteil})]}`` je Stunde (rein, E-SG-8).

    Stunde = die lokale volle Stunde über ``_stunden_start_ts`` — dieselbe Regel wie die eigene Summe des MQTT-Stroms;
    gebildet aus ``ts_unix`` über ``datetime.fromtimestamp`` (mit ``fold``), nie aus der naiven ``timestamp``-Spalte
    (Herbst: zwei verschiedene ``start_ts``).
    Anteil je Modus = **längengewichtetes** Mittel über die Fenster der Stunde, die das Gerät gemeldet hat (Fenster =
    eine ``ts_unix``), Gewicht aus ``fenster_gewicht`` über die Fensterfolge des Geräts — dieselbe Regel wie die
    Mittelwerte (``mittel_je_stunde``, Standalone-Gleichstand S3; bis dahin das einfache Mittel, bei regelmäßigem Takt
    gleich). Ein Modus ohne Zeile in einem Fenster zählt dort 0. Fenster ohne Zeile (kein Zustand, Broker weg,
    Neustart) zählen nicht — die Stunde ist das Mittel der vorhandenen Zeilen (E-SG-9).
    """
    fenster: dict[int, dict[int, dict[str, float]]] = {}       # inv_id → ts_unix → {modus: anteil}
    for ts, key, anteil in zeilen:
        inv_id = _modus_zeile_geraet(key)
        if inv_id is None:
            continue
        fenster.setdefault(inv_id, {}).setdefault(int(ts), {})[key.rpartition(":")[2]] = float(anteil)
    out: dict[int, list[tuple[int, dict[str, float]]]] = {}
    for inv_id, je_ts in fenster.items():
        je_stunde: dict[int, tuple[list[float], dict[str, float]]] = {}   # start_ts → ([Σ Gewicht], {modus: Σ Gewicht·Anteil})
        vorher: Optional[int] = None
        for ts in sorted(je_ts):
            gewicht = fenster_gewicht(ts, vorher)
            vorher = ts
            gesamt, summe = je_stunde.setdefault(_stunden_start_ts(datetime.fromtimestamp(ts)), ([0.0], {}))
            gesamt[0] += gewicht
            for modus, anteil in je_ts[ts].items():
                summe[modus] = summe.get(modus, 0.0) + gewicht * anteil
        out[inv_id] = [(stunde, {m: v / gesamt[0] for m, v in summe.items()})
                       for stunde, (gesamt, summe) in sorted(je_stunde.items())]
    return out


async def _betriebsart_mitschrift_mqtt(db: AsyncSession, k: _Kontext) -> int:
    """Phase des Stundenlaufs: Betriebsart-Mitschrift der MQTT-Wärmepumpen aus den 5-Minuten-Snapshots.

    Nur abgeschlossene Stunden (``bis`` = Beginn der laufenden), nur Zeilen der letzten ``_NAH_STUNDEN`` (die
    ``schon``-Sicherung des Kerns macht Wiederholungen billig), ``statistic_id`` = MQTT-Schlüssel. Danach baut
    ``modus_strom`` im selben Lauf den abgeleiteten Kanal «Strom je Betriebsart» daraus.
    """
    geraete = _mqtt_modus_wps(k)
    if not geraete:
        return 0
    bis = _stunden_start_ts(k.zeitpunkt)          # Beginn der laufenden Stunde — dieselbe Regel wie die Zeilen
    zeilen = await _modus_snapshot_zeilen(db, k.anlage.id, geraete, von=bis - _NAH_STUNDEN * _STUNDE, bis=bis)
    je_geraet = modus_anteile_je_stunde(zeilen)
    if not je_geraet:
        return 0
    entitaeten = {inv_id: mqtt_modus_statistic_id(inv_id) for inv_id in je_geraet}
    return await _schreibe_betriebsart_anteile(db, k.anlage, je_geraet, entitaeten, jetzt_ts=bis)


async def schreibe_betriebsart_mitschrift_mqtt(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, kontext: Optional[_Kontext] = None,
) -> int:
    """Die Betriebsart-Mitschrift aus MQTT für eine Anlage (Einstieg für Proben; im Betrieb ruft der Stundenlauf die Phase)."""
    return await _betriebsart_mitschrift_mqtt(db, kontext or await _kontext(db, anlage, zeitpunkt))


# ── Einstiege mit Isolation ─────────────────────────────────────────────────


async def _fehler_vermerken(db: AsyncSession, anlage_id: int, was: str, e: Exception) -> None:
    from backend.services.activity_service import log_activity

    logger.warning("Kanalstatistik (%s) für Anlage %s nicht geschrieben: %s: %s",
                   was, anlage_id, type(e).__name__, e)
    await log_activity(
        kategorie="scheduler",
        aktion="Kanalstatistik nicht geschrieben",
        erfolg=False,
        details=f"{was}: {type(e).__name__}: {e}",
        anlage_id=anlage_id,
        db=db,
    )


async def schreibe_kanaele_im_stundenlauf(db: AsyncSession, anlage, zeitpunkt: datetime) -> Optional[int]:
    """Der Einstieg des Stundenlaufs :05 — NACH ``snapshot_anlage``, in derselben Sitzung.

    Returns:
        Anzahl geschriebener Kanal-Zeilen, ``None`` bei Fehler (zurückgerollt, vermerkt).
    """
    anlage_id = anlage.id
    try:
        async with db.begin_nested():
            k = await _kontext(db, anlage, zeitpunkt)
            n = await schreibe_spiegel(db, anlage, zeitpunkt, kontext=k)
            # HA-Bauform §9 (Standalone-Gleichstand S2): Mittelwert-Mitschrift aus den MQTT-5-Minuten-Snapshots — NACH
            # dem Spiegel (der die HA-Felder führt; sie bleiben ausgeschlossen, G1) und ohne HA (der Spiegel kehrt ohne
            # HA vorher zurück, diese Phase nicht).
            n += await _mean_mitschrift(db, k)
            n += await schreibe_eigene_summe(db, anlage, zeitpunkt, kontext=k)
            # HA-Bauform E4c: der abgeleitete PV-Anteil der Heimladung — NACH den Roh-Familien, aus deren Zeilen er
            # die Stunde rechnet (``abgeleitet.py``).
            from backend.services.kanal.abgeleitet import schreibe_abgeleitete

            n += await schreibe_abgeleitete(db, anlage, zeitpunkt, invs=list(k.invs.values()))
            # HA-Bauform §9 (Standalone-Gleichstand S1): Betriebsart-Mitschrift der MQTT-Wärmepumpen aus den
            # 5-Minuten-Snapshots — VOR «Strom je Betriebsart», der sie im selben Lauf liest.
            n += await _betriebsart_mitschrift_mqtt(db, k)
            # HA-Bauform E4d: Strom je Betriebsart der Wärmepumpe — NACH Spiegel und eigener Summe (die Strom-Kanäle
            # der Stunde) und aus der Mitschrift, soweit sie schon geschrieben ist (``modus_strom.py``).
            from backend.services.kanal.modus_strom import schreibe_modus_strom

            n += await schreibe_modus_strom(db, anlage, zeitpunkt, invs=list(k.invs.values()))
            # HA-Bauform E4e: die Kosten-Kanäle bei Stundenpreis — NACH dem Preis-Spiegel und den Mengen der Stunde
            # (``kosten.py``); ohne Preis-Kanal schreibt er nichts.
            from backend.services.kanal.kosten import schreibe_kosten

            n += await schreibe_kosten(db, anlage, zeitpunkt)
        return n
    except Exception as e:  # noqa: BLE001 — der Bestand darf vom neuen Teil nichts merken
        await _fehler_vermerken(db, anlage_id, "Stundenlauf", e)
        return None


async def schreibe_betriebsart_mitschrift_sicher(
    db: AsyncSession, anlage, datum: date, modus_je_stunde,
) -> Optional[int]:
    """Der Einstieg der Tagesaggregation — NACH dem Schreiben der Stunden- und Tageszeilen."""
    if not getattr(modus_je_stunde, "anteile", None):
        return 0
    anlage_id = anlage.id
    try:
        async with db.begin_nested():
            n = await schreibe_betriebsart_mitschrift(db, anlage, datum, modus_je_stunde)
    except Exception as e:  # noqa: BLE001
        await _fehler_vermerken(db, anlage_id, f"Betriebsart-Mitschrift {datum}", e)
        return None
    # HA-Bauform E4d: die Mitschrift kommt aus der Tagesaggregation (alle 15 Minuten), oft NACH dem :05-Lauf — der
    # abgeleitete Kanal „Strom je Betriebsart" schreibt deshalb auch hier fort (idempotent ab seiner letzten Zeile).
    # Eigener SAVEPOINT: ein Fehler darin nimmt der Mitschrift nichts.
    try:
        async with db.begin_nested():
            from backend.services.kanal.modus_strom import schreibe_modus_strom

            n += await schreibe_modus_strom(db, anlage, datetime.now())
    except Exception as e:  # noqa: BLE001
        await _fehler_vermerken(db, anlage_id, f"Strom je Betriebsart {datum}", e)
    return n
