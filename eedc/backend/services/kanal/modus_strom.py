"""Abgeleiteter Kanal „Strom je Betriebsart" der Wärmepumpe (HA-Bauform E4d, Bauplan §8a, Auftrag Punkt 1).

**Was er ist.** Je Wärmepumpe mit Betriebsart-Mitschrift (``modus:inv:<id>:<betriebsart>``, HA-Bauform E1: Anteil der
Stunde je Kanon-Modus) und OHNE gemessene Betriebsart-Zähler führt eedc kumulative Kanäle (Art ``sum``, Familie
``abgeleitet``):

* ``abgeleitet:inv:<id>:modus_strom_<betriebsart>_kwh`` für Heizen · Warmwasser · Kühlen (die Teilmengen, die der
  Monatsabschluss speichert, ``MODUS_STROM_FELD``) und Lüften · Entfeuchten (erfasst, nicht bewertet — Konzept
  Wärme/Klima §5.4; kein Leser faltet sie, im Monat stehen sie wie bisher im Rest, D11);
* ``abgeleitet:inv:<id>:modus_strom_rest_kwh`` — der Strom ohne Betriebsart-Aussage (keine Mitschrift, ``aus``/
  ``unbestimmt``, Zählerlücke): Σ aller sechs = Strom des Geräts;
* ``abgeleitet:inv:<id>:modus_abdeckung_h`` — Stunden mit Signal (Art ``sum``, Einheit ``h``): ein Zeitraum nennt seine
  Abdeckung als Δ wie jede Menge (``modus_abdeckung_h`` der Monatszeile, Konzept §8.1). ⚑ Vorschlag des Auftrags
  „``stand`` oder ``sum``" — ``sum``: die Abdeckung ist additiv über die Zeit (ein Monat = Σ seiner Stunden), genau wie
  ``summiere_modus_split`` sie über Tage addiert; ein ``stand`` hätte keinen Reset- oder Rücksprung-Sinn.

**Die Regel der Stunde steht im Layer** (``core/berechnungen/modus_split.modus_strom_der_stunde``), gerufen, nicht
nachgebaut. Die Menge der Stunde ist die K3-Menge aus den Δ der Strom-Kanäle des Geräts (Gesamtzähler · getrennte
Strommessung) — EINE Vorrangkette, ``core/field_definitions/wp_strom.py::wp_strom_aufteilung`` auf die Stunde
angewandt. **Gemessene Betriebsart-Zähler haben Vorrang (K2, ganz oder gar nicht):** ein Gerät mit zugeordnetem
``betriebsart_strom_*`` (Gerätefeld oder Innengerät, ``snapshot/keys.feld_hat_zaehler``) bekommt keinen abgeleiteten
Kanal — seine Aufteilung sind die Spiegel dieser Zähler.

**Wann geschrieben wird.** Eine Stunde ``h`` erst, wenn jeder Strom-Kanal des Geräts eine Zeile bei ``h`` oder später
hat UND die Mitschrift des Geräts ``h`` erreicht hat (eine Zeile bei ``h`` oder später) — eine fehlende Mitschrift-Zeile
VOR dem letzten Stand heißt „nicht hingesehen" (Rest), am Ende heißt sie „noch nicht geschrieben" (warten). Hört die
Mitschrift auf (Zuordnung entfernt, HA lange weg), bleibt der Kanal stehen: der Zeitraum gilt dann für die WP-Gruppe als
nicht gedeckt, und der heutige Leser rechnet (Lesart 1, Bauplan §3b) — die sichere Richtung. Zwei Einstiege, beide
idempotent ab der letzten Zeile: der Stundenlauf nach Spiegel und eigener Summe (``schreiber.schreibe_kanaele_im_
stundenlauf``) und die Mitschrift nach ihrem Schreiben (``schreiber.schreibe_betriebsart_mitschrift_sicher``) — die
Mitschrift kommt aus der Tagesaggregation (alle 15 Minuten), also oft NACH dem :05-Lauf.

**``aufbaubar_ab`` und Beginn.** Ein neuer Kanal beginnt beim ersten Lauf mit dem laufenden Monat (H-2 aus E4c: eine
Stunde vor dem Monatsfenster), frühestens eine Stunde vor der ersten Mitschrift-Zeile des Geräts (diese Ankerstunde
trägt keine Aussage, nur den Stand vor dem ersten gedeckten Zeitraum) und erst ab einer Stunde, in der jeder
Strom-Kanal einen Vorstand hat. Kein abgeschlossener Monat wird gedeckt; die Vergangenheit vor der Mitschrift kennt der
Kanal nicht (sie bleibt beim Bestand, ``modus_split_monat.py``). Neuaufbau: ``abgeleitet.verwerfe_ab`` (Konsistenzlauf)
löscht ab ``max(ab_ts, aufbaubar_ab)``; der nächste Lauf schreibt neu.

Schwesterdateien: ``abgeleitet.py`` (PV-Anteil der Heimladung, Vorbild), ``wp_leser.py`` (Leser der WP-Gruppe),
``schreiber.py``, ``lesen.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.modus_split import (
    MODUS_STROM_ERFASST,
    MODUS_STROM_REST,
    modus_strom_der_stunde,
)
from backend.core.betriebsmodus import BETRIEBSART_STROM_FELD, BETRIEBSMODUS_KANON, MODUS_ABDECKUNG_FELD
from backend.core.field_definitions import FEINE_STROM_FELDER, basis_feld_key, wp_strom_aufteilung
from backend.core.field_definitions.wp_strom import WP_GESAMT_STROM_FELDER
from backend.models.kanal import ART_SUM, FAMILIE_ABGELEITET, Kanal, KanalQuelle, KanalStatistik

logger = logging.getLogger(__name__)

_STUNDE = 3600
#: ``kanal_quelle.statistic_id`` der Familie ``abgeleitet`` — die Regel, nach der er gerechnet ist.
REGEL_MODUS_ANTEIL = "modus_anteil_je_stunde"
#: Die Strom-Felder, aus denen K3 die Menge der Stunde wählt (Gesamt · Summanden). Betriebsart-Zähler gehören nicht
#: dazu — mit ihnen gibt es keinen abgeleiteten Kanal (K2).
STROM_FELDER: tuple[str, ...] = tuple(WP_GESAMT_STROM_FELDER) + tuple(FEINE_STROM_FELDER)


def modus_strom_key(inv_id: int | str, modus: str) -> str:
    """``abgeleitet:inv:<id>:modus_strom_<modus>_kwh`` — ``modus`` ∈ MODUS_STROM_ERFASST oder ``rest``."""
    return f"abgeleitet:inv:{inv_id}:modus_strom_{modus}_kwh"


def abdeckung_key(inv_id: int | str) -> str:
    """``abgeleitet:inv:<id>:modus_abdeckung_h`` — Stunden mit Betriebsart-Signal."""
    return f"abgeleitet:inv:{inv_id}:{MODUS_ABDECKUNG_FELD}"


def alle_keys(inv_id: int | str) -> list[str]:
    return [modus_strom_key(inv_id, m) for m in (*MODUS_STROM_ERFASST, MODUS_STROM_REST)] + [abdeckung_key(inv_id)]


def _unix(dt: datetime) -> int:
    return int(round(dt.timestamp()))


# ── Auswahl ─────────────────────────────────────────────────────────────────


def hat_gemessene_betriebsart_zaehler(inv, inv_map: dict, hat_feld) -> bool:
    """Trägt das Gerät einen gemessenen Betriebsart-Stromzähler (Gerätefeld oder Innengerät)? — dann K2: kein
    abgeleiteter Kanal."""
    felder = ((inv_map.get(str(inv.id)) or {}).get("felder") or {})
    basis = set(BETRIEBSART_STROM_FELD.values())
    kandidaten = {f for f in felder if basis_feld_key(f) in basis} | basis
    return any(hat_feld(inv, f) for f in kandidaten)


def strom_felder_des_geraets(inv, hat_feld) -> list[str]:
    """Die Strom-Felder des Geräts mit Zähler, aus denen K3 die Stunde wählt."""
    return [f for f in STROM_FELDER if hat_feld(inv, f)]


async def mitschrift_kanaele(db: AsyncSession, anlage_id: int, inv_ids) -> dict[int, list[Kanal]]:
    """Je Gerät die Mitschrift-Kanäle ``modus:inv:<id>:<modus>`` (E1), die es gibt."""
    from backend.services.kanal.katalog import modus_kanal_key

    keys = {modus_kanal_key(i, m): int(i) for i in inv_ids for m in BETRIEBSMODUS_KANON}
    if not keys:
        return {}
    out: dict[int, list[Kanal]] = {}
    for k in (await db.execute(select(Kanal).where(and_(
        Kanal.anlage_id == anlage_id, Kanal.key.in_(list(keys)),
    )))).scalars().all():
        out.setdefault(keys[k.key], []).append(k)
    return out


async def abzuleitende_geraete(db: AsyncSession, anlage, invs: list, hat_feld) -> dict[int, list[str]]:
    """``{inv_id: [Strom-Felder]}`` der Wärmepumpen, die einen abgeleiteten Kanal bekommen: Mitschrift vorhanden, kein
    gemessener Betriebsart-Zähler, mindestens ein Strom-Zähler."""
    wps = [i for i in invs if getattr(i, "typ", None) == "waermepumpe"]
    if not wps:
        return {}
    mit = await mitschrift_kanaele(db, anlage.id, [i.id for i in wps])
    inv_map = ((anlage.sensor_mapping or {}).get("investitionen") or {})
    out: dict[int, list[str]] = {}
    for i in wps:
        if i.id not in mit or hat_gemessene_betriebsart_zaehler(i, inv_map, hat_feld):
            continue
        felder = strom_felder_des_geraets(i, hat_feld)
        if felder:
            out[i.id] = felder
    return out


# ── Die Menge einer Stunde ──────────────────────────────────────────────────


def menge_der_stunde(zeilen: dict, parameter: Optional[dict]) -> tuple[float, bool]:
    """Die Strom-Menge eines Geräts in EINER Stunde und ob sie genau diese Stunde trägt.

    ``zeilen``: ``{kanal_key: Stundenwert | None}`` der Strom-Kanäle des Geräts bei ``h``. Trägt jeder Kanal eine
    Zeile mit Vorstand und Spanne 1 h, ist die Menge die K3-Menge der Stunde — ``wp_strom_aufteilung`` auf die Δ
    angewandt (EINE Vorrangkette, nicht nachgebaut). Sonst (Zählerlücke) trägt die Stunde keine Betriebsart-Aussage
    (``eindeutig`` False ⇒ Rest), und ihre Menge folgt aus den vorhandenen Zeilen. ⚠ Fehlt dabei die Zeile eines
    **Gesamt**-Zählers, ist die Menge 0: seine Energie steht in seiner nächsten Zeile (wie in HA), und die Summanden
    dieser Stunde dürfen sie nicht vorwegnehmen — sonst zählte K3 Regel 3 (Summanden) die Stunde und Regel 1 (Gesamt)
    sie mit der nächsten Zeile noch einmal.
    """
    daten = {k.rsplit(":", 1)[1]: z.change for k, z in zeilen.items() if z is not None and z.change is not None}
    eindeutig = len(daten) == len(zeilen) and all(z.spanne == _STUNDE for z in zeilen.values() if z is not None)
    if not daten:
        return 0.0, eindeutig
    if not eindeutig and any(k.rsplit(":", 1)[1] in WP_GESAMT_STROM_FELDER and (z is None or z.change is None)
                             for k, z in zeilen.items()):
        return 0.0, False
    return float(wp_strom_aufteilung(daten, parameter).menge_kwh), eindeutig


# ── Schreiben ───────────────────────────────────────────────────────────────


async def _mitschrift_anteile(db: AsyncSession, kanaele: list[Kanal], von: int, bis: int) -> dict[int, dict[str, float]]:
    """``{start_ts: {modus: anteil}}`` der Mitschrift in ``[von, bis]``."""
    if not kanaele:
        return {}
    modus_je_kid = {k.id: k.key.rsplit(":", 1)[1] for k in kanaele}
    out: dict[int, dict[str, float]] = {}
    for kid, ts, mean in (await db.execute(
        select(KanalStatistik.kanal_id, KanalStatistik.start_ts, KanalStatistik.mean).where(and_(
            KanalStatistik.kanal_id.in_(list(modus_je_kid)),
            KanalStatistik.start_ts >= von, KanalStatistik.start_ts <= bis,
        ))
    )).all():
        if mean is not None:
            out.setdefault(int(ts), {})[modus_je_kid[kid]] = float(mean)
    return out


async def schreibe_modus_strom(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, invs: Optional[list] = None, ab_ts: Optional[int] = None,
) -> int:
    """Die abgeleiteten Kanäle „Strom je Betriebsart" der Anlage bis zur Stunde vor ``zeitpunkt`` fortschreiben.

    Je Gerät ab seiner letzten Zeile (bzw. ``aufbaubar_ab`` nach einem Verwerfen); ein neues Gerät ab ``ab_ts`` bzw.
    dem laufenden Monat (Modul-Kopf). Returns: Zahl der geschriebenen Zeilen.
    """
    from backend.models.investition import Investition
    from backend.services.kanal.abgeleitet import verfuegbarkeit
    from backend.services.kanal.fenster import monatsfenster
    from backend.services.kanal.abgeleitet import tag_der_stunde
    from backend.services.kanal.lesen import kanaele_laden, stunden_stapel
    from backend.services.kanal.schreiber import _zeilen_einfuegen, kanaele_holen, letzte_zeilen

    if invs is None:
        invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all())
    if not any(getattr(i, "typ", None) == "waermepumpe" for i in invs):
        return 0
    hat_feld = await verfuegbarkeit(db, anlage)
    geraete = await abzuleitende_geraete(db, anlage, invs, hat_feld)
    if not geraete:
        return 0
    inv_by_id = {i.id: i for i in invs}
    ts_bis = (_unix(zeitpunkt) // _STUNDE) * _STUNDE - _STUNDE
    if ab_ts is not None:
        neu_ab = int(ab_ts)
    else:
        tag = tag_der_stunde(ts_bis)
        neu_ab = monatsfenster(tag.year, tag.month)[0] - _STUNDE

    # Stand je Gerät: die Kanäle, die es schon gibt, und ihre letzten Zeilen (alle Kanäle eines Geräts schreiben
    # dieselben Stunden; maßgeblich ist der Abdeckungs-Kanal).
    vorhanden = {k.key: k for k in (await db.execute(select(Kanal).where(and_(
        Kanal.anlage_id == anlage.id, Kanal.key.in_([k for i in geraete for k in alle_keys(i)]),
    )))).scalars().all()}
    letzte = await letzte_zeilen(db, [k.id for k in vorhanden.values()])
    mit = await mitschrift_kanaele(db, anlage.id, list(geraete))
    mit_letzte = await letzte_zeilen(db, [k.id for ks in mit.values() for k in ks])
    weiter_ab: dict[int, int] = {}
    staende: dict[int, dict[str, float]] = {}
    erste_mitschrift: dict[int, Optional[int]] = {}
    mitschrift_bis: dict[int, Optional[int]] = {}
    for inv_id in geraete:
        ts_mit = [mit_letzte[k.id].start_ts for k in mit.get(inv_id, []) if k.id in mit_letzte]
        mitschrift_bis[inv_id] = max(ts_mit) if ts_mit else None
        ka = vorhanden.get(abdeckung_key(inv_id))
        if ka is not None and (ka.id in letzte or ka.aufbaubar_ab is not None):
            z = letzte.get(ka.id)
            weiter_ab[inv_id] = (z.start_ts + _STUNDE) if z is not None else int(ka.aufbaubar_ab)
            staende[inv_id] = {
                key: (float(letzte[vorhanden[key].id].sum) if key in vorhanden and vorhanden[key].id in letzte
                      and letzte[vorhanden[key].id].sum is not None else 0.0)
                for key in alle_keys(inv_id)
            }
    # Die erste Mitschrift-Zeile je NEUEM Gerät (ein Index-Schritt je Kanal).
    for inv_id in geraete:
        if inv_id in weiter_ab:
            continue
        erste = None
        for k in mit.get(inv_id, []):
            z = (await db.execute(select(KanalStatistik.start_ts).where(KanalStatistik.kanal_id == k.id)
                                  .order_by(KanalStatistik.start_ts.asc()).limit(1))).scalar()
            if z is not None and (erste is None or z < erste):
                erste = int(z)
        erste_mitschrift[inv_id] = erste
    start_je: dict[int, int] = {}
    for inv_id in geraete:
        if inv_id in weiter_ab:
            start_je[inv_id] = weiter_ab[inv_id]
        elif erste_mitschrift.get(inv_id) is not None:
            start_je[inv_id] = max(neu_ab, erste_mitschrift[inv_id] - _STUNDE)
    # Nur Geräte, deren Mitschrift ihre nächste Stunde schon erreicht hat — sonst gibt es nichts zu schreiben (der
    # Regelfall zwischen zwei Mitschrift-Läufen; spart die Stunden-Abfrage der Strom-Kanäle).
    start_je = {i: ab for i, ab in start_je.items() if mitschrift_bis.get(i) is not None and mitschrift_bis[i] >= ab}
    if not start_je:
        return 0
    start = min(start_je.values())
    if start > ts_bis:
        return 0

    strom_keys = {i: [f"inv:{i}:{f}" for f in felder] for i, felder in geraete.items()}
    kanaele = await kanaele_laden(db, anlage.id, {k for ks in strom_keys.values() for k in ks})
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    if not mengen:
        return 0
    je = await stunden_stapel(db, mengen, start, ts_bis + _STUNDE, jetzt=_unix(zeitpunkt) + _STUNDE)
    werte = {key: {w.start_ts: w for w in st.werte} for key, st in je.items()}
    erreicht = {key: (max(w) if w else None) for key, w in werte.items()}

    neue: dict[int, list[tuple[int, dict[str, float]]]] = {}
    for inv_id, ab in sorted(start_je.items()):
        keys = [k for k in strom_keys[inv_id] if k in werte]
        if not keys:
            continue
        inv = inv_by_id[inv_id]
        anteile = await _mitschrift_anteile(db, mit.get(inv_id, []), ab, ts_bis)
        stand = dict(staende.get(inv_id) or {k: 0.0 for k in alle_keys(inv_id)})
        begonnen = inv_id in weiter_ab
        h = ab
        while h <= ts_bis:
            if any(erreicht[k] is None or erreicht[k] < h for k in keys):
                break                                   # ein Strom-Kanal ist noch nicht so weit — später weiter
            if mitschrift_bis[inv_id] is None or mitschrift_bis[inv_id] < h:
                break                                   # die Mitschrift ist noch nicht so weit
            zeilen = {k: werte[k].get(h) for k in keys}
            if not begonnen and not all(z is not None and z.change is not None for z in zeilen.values()):
                h += _STUNDE                            # ein neuer Kanal beginnt erst mit Vorstand
                continue
            begonnen = True
            menge, eindeutig = menge_der_stunde(zeilen, inv.parameter)
            a = anteile.get(h)
            je_modus, rest = modus_strom_der_stunde(menge, a, stunde_eindeutig=eindeutig)
            for m, v in je_modus.items():
                stand[modus_strom_key(inv_id, m)] += v
            stand[modus_strom_key(inv_id, MODUS_STROM_REST)] += rest
            if a and sum(a.values()) > 0:
                stand[abdeckung_key(inv_id)] += 1.0
            neue.setdefault(inv_id, []).append((h, dict(stand)))
            h += _STUNDE
    if not neue:
        return 0

    gewuenscht = {key: (ART_SUM, "h" if key.endswith(MODUS_ABDECKUNG_FELD) else "kWh")
                  for i in neue for key in alle_keys(i)}
    kanaele_neu = await kanaele_holen(db, anlage.id, gewuenscht)
    zeilen_db: list[dict] = []
    for inv_id, punkte in neue.items():
        for key in alle_keys(inv_id):
            kanal = kanaele_neu[key]
            if kanal.aufbaubar_ab is None:
                kanal.aufbaubar_ab = punkte[0][0]
                db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=punkte[0][0], familie=FAMILIE_ABGELEITET,
                                   statistic_id=REGEL_MODUS_ANTEIL, offset=0.0))
            zeilen_db.extend({"kanal_id": kanal.id, "start_ts": ts, "sum": st[key], "state": None, "mean": None,
                              "min": None, "max": None, "familie": FAMILIE_ABGELEITET} for ts, st in punkte)
    await db.flush()
    return await _zeilen_einfuegen(db, zeilen_db)


__all__ = [
    "REGEL_MODUS_ANTEIL", "STROM_FELDER", "abdeckung_key", "abzuleitende_geraete", "alle_keys",
    "hat_gemessene_betriebsart_zaehler", "mitschrift_kanaele", "modus_strom_key", "schreibe_modus_strom",
    "strom_felder_des_geraets",
]
