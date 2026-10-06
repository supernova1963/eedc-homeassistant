"""Abgeleitete Kanäle — der PV-Anteil der Heimladung je Gerät als kumulativer Kanal (HA-Bauform E4c, Bauplan §2).

**Was er ist.** ``abgeleitet:inv:<id>:ladung_pv_kwh`` (Art ``sum``, Familie ``abgeleitet``) führt je Wallbox bzw.
E-Auto ohne gemessene Aufteilung die Summe der PV-Teile seiner Ladung, Stunde für Stunde. Ein Zeitraum (Tag, Monat,
Kalendermonat) nennt damit seine Aufteilung als EIN Δ wie jeder andere Kanal — derselbe Monat mit und ohne Abschluss
liest dieselbe Zahl (N-631, Bauplan §7: „eine Aufteilung für Monat mit und ohne Abschluss").

**Die Regel der Stunde ist die heutige** (``core/berechnungen/pv_anteil_ladung.pv_der_stunde``, Einspeise-Deckung
N-569, Konzept Wallbox/E-Auto Phase 5) — gerufen, nicht nachgebaut. Je Stunde ``h``:

* ``L(h)`` = Σ Δ der Ladezähler auf der Wallbox-Achse — dieselbe Auswahl wie der Tagespfad
  (``bilanz_adapter.zaehler_eintraege``: Wallbox-Regel N-196, Heimlade-Kaskade des E-Autos N-555, Aktiv-Filter des
  Tages). Das ist dieselbe Größe wie ``wallbox_kw`` im Aggregator (alle Geräte der Achse, auch die mit eigener Messung).
* ``pv(h) = pv_der_stunde(L, Netzbezug, Einspeisung)`` aus den Δ der Basis-Zähler derselben Stunde.
* Je Gerät ``i`` der Achse ohne gemessene Aufteilung: ``Δ abgeleitet_i(h) = max(0, L_i(h)) × pv(h) / L(h)``.

**Gemessene Aufteilung hat Vorrang** (Rahmenbedingung 1): ein Gerät mit zugeordnetem ``ladung_pv_kwh`` oder
``ladung_netz_kwh`` (HA-Sensor oder MQTT, ``snapshot/keys.feld_hat_zaehler``) bekommt keinen abgeleiteten Kanal; seine
Ladung zählt trotzdem in ``L(h)`` (sie konkurriert um denselben Überschuss).

⚑ **Eine Stunde ohne Aussage** (``pv_der_stunde`` → ``None``: kein Netzbezugs- oder Einspeisezähler in der Stunde; oder
ein Eingang trägt mehr als eine Stunde — Zeile fehlt, Spanne > 1 h; oder erste Zeile eines Eingangs ohne Vorstand)
trägt **keinen PV-Teil** — der Kanal schreibt die Stunde mit unverändertem Stand (Grenze, Entscheid Master H-1:
so belassen). Wer den Anteil eines Zeitraums als
``Δ abgeleitet / Δ Ladung`` liest, zählt ihre Ladung damit zum Netz. Der Bestand ließ eine solche Stunde ganz aus (sie
zählte weder bei PV noch bei Netz, die Quote galt nur über die gedeckten Stunden). Benannte Abweichung (Bericht E4c).

**``aufbaubar_ab`` und Rückwirkung.** Ein neuer abgeleiteter Kanal beginnt beim ersten Lauf mit dem LAUFENDEN Monat
(H-2, Entscheid Master 06.10.2026: eine Stunde vor dem Monatsfenster, ab der ersten Stunde, in der jeder Eingang eine
Zeile mit Vorstand hat); ``aufbaubar_ab`` ist diese Stunde. Kein abgeschlossener Monat wird gedeckt. Ein Neuaufbau (``verwerfe_ab`` nach einer Korrektur
des Spiegels im Konsistenzlauf) ändert keine Zeile davor (Bauplan §2, W2). Rückwirkend über den laufenden Monat hinaus baut
der Stundenlauf NICHT — Rahmenbedingung 5 der Phase 5 („keine rückwirkende Neuberechnung"). ``ab_ts`` setzt die
erste Stunde eines NEUEN Kanals ausdrücklich (Matrix-Seed: „das Produkt lief seit Beginn der Reihe").

**Isolation:** gerufen aus ``schreiber.schreibe_kanaele_im_stundenlauf`` im selben SAVEPOINT wie Spiegel und eigene
Summe, NACH ihnen (die Eingänge der Stunde müssen geschrieben sein).

Schwesterdateien: ``schreiber.py``, ``geraete_leser.py`` (Leser der E-Mob-Gruppe), ``lesen.py``, ``modus_strom.py``
(der zweite abgeleitete Kanal, E4d — ``verwerfe_ab`` hier verwirft beide).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.pv_anteil_ladung import REGEL_EINSPEISE_DECKUNG, pv_der_stunde
from backend.core.berechnungen.spannen import achse_der_kategorie
from backend.models.kanal import ART_SUM, FAMILIE_ABGELEITET, Kanal, KanalQuelle, KanalStatistik

logger = logging.getLogger(__name__)

_STUNDE = 3600
#: Die Felder einer gemessenen Aufteilung (Vorrang vor der Ableitung).
AUFTEILUNG_FELDER: tuple[str, ...] = ("ladung_pv_kwh", "ladung_netz_kwh")
#: Typen, deren Ladung auf der Wallbox-Achse liegen kann.
EMOB_TYPEN: tuple[str, ...] = ("wallbox", "e-auto")
#: Die Achse der Heimladung (``spannen.achse_der_kategorie``).
ACHSE_LADUNG = "wallbox"


def abgeleitet_key(inv_id: int | str) -> str:
    """Schlüssel des abgeleiteten PV-Anteils eines Geräts: ``abgeleitet:inv:<id>:ladung_pv_kwh``."""
    return f"abgeleitet:inv:{inv_id}:ladung_pv_kwh"


def _unix(dt: datetime) -> int:
    return int(round(dt.timestamp()))


def tag_der_stunde(start_ts: int) -> date:
    """Der Tag, in dessen Tagesfenster ``[Vortag 23:00, 23:00)`` (``fenster.tagesfenster``) die Stunde liegt."""
    return (datetime.fromtimestamp(start_ts) + timedelta(hours=1)).date()


# ── Auswahl je Tag ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LadeAuswahl:
    """Die Eingänge der Ableitung an EINEM Tag."""

    #: inv_id → Kanal-Schlüssel seiner Ladezähler auf der Wallbox-Achse.
    ladung: dict[int, tuple[str, ...]]
    netzbezug: tuple[str, ...]
    einspeisung: tuple[str, ...]
    #: Die Geräte der Achse OHNE gemessene Aufteilung — sie bekommen einen abgeleiteten Kanal.
    abzuleiten: frozenset[int]

    @property
    def eingaenge(self) -> set[str]:
        return {k for ks in self.ladung.values() for k in ks} | set(self.netzbezug) | set(self.einspeisung)


async def verfuegbarkeit(db: AsyncSession, anlage) -> Any:
    """``(inv, feld) -> bool``: trägt das Feld einen kumulativen Zähler (HA-Sensor oder MQTT) — die eine Antwort
    ``snapshot/keys.feld_hat_zaehler`` (N-328), mit jeder MQTT-Historie (``seit=None``)."""
    from backend.services.snapshot.keys import extract_quellen_energy, feld_hat_zaehler
    from backend.services.snapshot.reader import mqtt_zaehler_keys

    quellen_energy = extract_quellen_energy(anlage)
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)
    inv_map = ((anlage.sensor_mapping or {}).get("investitionen") or {})

    def _hat(inv, feld: str) -> bool:
        cfg = ((inv_map.get(str(inv.id)) or {}).get("felder") or {}).get(feld)
        return feld_hat_zaehler(cfg, f"inv:{inv.id}:{feld}", quellen_energy, mqtt_keys)

    return _hat


async def lade_auswahl(db: AsyncSession, anlage, invs: list, tag: date, hat_feld) -> LadeAuswahl:
    """Die Ladezähler, Netzbezug und Einspeisung des Tages — Auswahl des Tagespfads (``zaehler_eintraege``)."""
    from backend.services.kanal.bilanz_adapter import zaehler_eintraege

    aktiv = {str(i.id): i for i in invs if i.ist_aktiv_an(tag)}
    eintraege = await zaehler_eintraege(db, anlage, aktiv, tag)
    ladung: dict[int, list[str]] = {}
    netz, einsp = [], []
    for e in eintraege:
        if e.kategorie == "netzbezug":
            netz.append(e.schluessel)
        elif e.kategorie == "einspeisung":
            einsp.append(e.schluessel)
        elif achse_der_kategorie(e.kategorie) == ACHSE_LADUNG and e.sensor_key.startswith("inv:"):
            ladung.setdefault(int(e.sensor_key.split(":", 2)[1]), []).append(e.schluessel)
    abzuleiten = frozenset(
        inv_id for inv_id in ladung
        if not any(hat_feld(aktiv[str(inv_id)], f) for f in AUFTEILUNG_FELDER)
    )
    return LadeAuswahl({k: tuple(v) for k, v in ladung.items()}, tuple(netz), tuple(einsp), abzuleiten)


# ── Die Rechnung einer Stunde (rein) ────────────────────────────────────────


def stunde_ableiten(
    ladung_je_inv: dict[int, Optional[float]], netzbezug: Optional[float], einspeisung: Optional[float],
    abzuleiten: frozenset[int],
) -> dict[int, float]:
    """Δ des PV-Teils je abzuleitendem Gerät in EINER Stunde. ``None`` in einem Eingang heißt „ohne Aussage" (Stunde
    gebündelt oder ohne Zeile) — dann trägt kein Gerät einen PV-Teil (0)."""
    if any(v is None for v in ladung_je_inv.values()):
        return {i: 0.0 for i in abzuleiten}
    gesamt = sum(ladung_je_inv.values())
    pv = pv_der_stunde(gesamt, netzbezug, einspeisung)
    if pv is None or gesamt <= 0:
        return {i: 0.0 for i in abzuleiten}
    anteil = pv / gesamt
    return {i: max(0.0, ladung_je_inv.get(i) or 0.0) * anteil for i in abzuleiten}


# ── Schreiben ───────────────────────────────────────────────────────────────


def _aenderung(werte: dict[int, Any], h: int) -> Optional[float]:
    """Δ eines Eingangs in der Stunde ``h`` — nur bei genau einer Stunde Spanne, sonst ``None`` (ohne Aussage)."""
    w = werte.get(h)
    if w is None or w.change is None or w.spanne != _STUNDE:
        return None
    return w.change


async def schreibe_abgeleitete(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, invs: Optional[list] = None, ab_ts: Optional[int] = None,
) -> int:
    """Die abgeleiteten Kanäle der Anlage bis zur Stunde vor ``zeitpunkt`` fortschreiben.

    Je Gerät ab seiner letzten Zeile (bzw. ``aufbaubar_ab``, wenn verworfen wurde); ein neues Gerät ab ``ab_ts``,
    ohne ``ab_ts`` nur die eben abgeschlossene Stunde. Geschrieben wird je Stunde nur, solange JEDER Eingang des
    Tages eine Zeile zu dieser Stunde oder später hat (der Spiegel muss sie geschrieben haben).

    Returns: Zahl der geschriebenen Zeilen.
    """
    from backend.models.investition import Investition
    from backend.services.kanal.lesen import kanaele_laden, stunden_stapel
    from backend.services.kanal.schreiber import _zeilen_einfuegen, kanaele_holen, letzte_zeilen

    if invs is None:
        invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all())
    emob = [i for i in invs if getattr(i, "typ", None) in EMOB_TYPEN]
    if not emob:
        return 0
    # Die letzte Stunde, die geschrieben werden darf: die eben abgeschlossene (Stundenbeginn in absoluter Zeit — HAs
    # Zeilen liegen auf vollen UTC-Stunden; der Lauf kommt um :05).
    ts_bis = (_unix(zeitpunkt) // _STUNDE) * _STUNDE - _STUNDE

    vorhanden = {k.key: k for k in (await db.execute(select(Kanal).where(and_(
        Kanal.anlage_id == anlage.id, Kanal.key.in_([abgeleitet_key(i.id) for i in emob]),
    )))).scalars().all()}
    letzte = await letzte_zeilen(db, [k.id for k in vorhanden.values()])
    weiter_ab: dict[int, int] = {}                       # inv_id → erste noch nicht geschriebene Stunde
    stand: dict[int, float] = {}
    for i in emob:
        k = vorhanden.get(abgeleitet_key(i.id))
        if k is None:
            continue
        z = letzte.get(k.id)
        weiter_ab[i.id] = (z.start_ts + _STUNDE) if z is not None else int(k.aufbaubar_ab or ts_bis)
        stand[i.id] = float(z.sum) if z is not None and z.sum is not None else 0.0
    # H-2 (Entscheid Master 06.10.2026): ein NEUER Kanal beginnt beim ersten Lauf mit dem laufenden Monat — eine Stunde
    # vor dem Monatsfenster (`fenster.monatsfenster`, ab Vortag 23:00), damit Tagesfenster-Monat UND Kalendermonat
    # (Cockpit → Monat) einen Stand vor ihrem Anfang haben. Kein abgeschlossener Monat wird gedeckt (der Kanal beginnt in
    # ihm erst nach seinem Anfang). Geschrieben wird ab der ersten Stunde, in der jeder Eingang eine Zeile MIT Vorstand
    # hat — fehlt dem Spiegel die Monatsgeschichte noch, beginnt der Kanal später und deckt den Monat nicht.
    if ab_ts is not None:
        neu_ab = int(ab_ts)
    else:
        from backend.services.kanal.fenster import monatsfenster

        tag = tag_der_stunde(ts_bis)
        neu_ab = monatsfenster(tag.year, tag.month)[0] - _STUNDE
    start = min([*weiter_ab.values(), neu_ab])
    if start > ts_bis:
        return 0

    hat_feld = await verfuegbarkeit(db, anlage)
    auswahl: dict[date, LadeAuswahl] = {}
    tag, ende_tag = tag_der_stunde(start), tag_der_stunde(ts_bis)
    while tag <= ende_tag:
        auswahl[tag] = await lade_auswahl(db, anlage, invs, tag, hat_feld)
        tag += timedelta(days=1)
    if not any(a.abzuleiten for a in auswahl.values()):
        return 0
    eingaenge = set().union(*(a.eingaenge for a in auswahl.values() if a.abzuleiten))
    kanaele = await kanaele_laden(db, anlage.id, eingaenge)
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    if not mengen:
        return 0
    je = await stunden_stapel(db, mengen, start, ts_bis + _STUNDE, jetzt=_unix(zeitpunkt) + _STUNDE)
    werte = {key: {w.start_ts: w for w in st.werte} for key, st in je.items()}
    # Bis wohin jeder Eingang geschrieben ist (seine letzte Zeile im Fenster; ohne Zeile: nichts).
    erreicht = {key: max(w) if w else None for key, w in werte.items()}

    neue: dict[int, list[tuple[int, float]]] = {}
    h = start
    while h <= ts_bis:
        a = auswahl[tag_der_stunde(h)]
        if a.abzuleiten:
            noetig = a.eingaenge
            if not noetig <= set(werte) or any(erreicht[k] is None or erreicht[k] < h for k in noetig):
                break                                     # ein Eingang ist noch nicht so weit — später weiter
            ladung = {i: _summe_oder_none([_aenderung(werte[k], h) for k in ks]) for i, ks in a.ladung.items()}
            netz = _summe_oder_none([_aenderung(werte[k], h) for k in a.netzbezug])
            einsp = _summe_oder_none([_aenderung(werte[k], h) for k in a.einspeisung])
            mit_vorstand = all(_aenderung(werte[k], h) is not None for k in noetig)
            for inv_id, delta in stunde_ableiten(ladung, netz, einsp, a.abzuleiten).items():
                ab = weiter_ab.get(inv_id, neu_ab)
                if h < ab or (inv_id not in weiter_ab and not mit_vorstand):
                    continue
                weiter_ab.setdefault(inv_id, h)
                stand[inv_id] = stand.get(inv_id, 0.0) + delta
                neue.setdefault(inv_id, []).append((h, stand[inv_id]))
        h += _STUNDE
    if not neue:
        return 0

    gewuenscht = {abgeleitet_key(i): (ART_SUM, "kWh") for i in neue}
    kanaele_neu = await kanaele_holen(db, anlage.id, gewuenscht)
    zeilen: list[dict] = []
    for inv_id, punkte in neue.items():
        kanal = kanaele_neu[abgeleitet_key(inv_id)]
        if kanal.aufbaubar_ab is None:
            kanal.aufbaubar_ab = punkte[0][0]
            db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=punkte[0][0], familie=FAMILIE_ABGELEITET,
                               statistic_id=REGEL_EINSPEISE_DECKUNG, offset=0.0))
        zeilen.extend({"kanal_id": kanal.id, "start_ts": ts, "sum": s, "state": None, "mean": None, "min": None,
                       "max": None, "familie": FAMILIE_ABGELEITET} for ts, s in punkte)
    await db.flush()
    return await _zeilen_einfuegen(db, zeilen)


def _summe_oder_none(werte: list[Optional[float]]) -> Optional[float]:
    if not werte or any(v is None for v in werte):
        return None
    return sum(werte)


async def verwerfe_ab(db: AsyncSession, anlage_id: int, ab_ts: int) -> int:
    """Neuaufbau: die Zeilen der abgeleiteten Kanäle ab ``max(ab_ts, aufbaubar_ab)`` löschen — der nächste Stundenlauf
    schreibt sie aus dem korrigierten Spiegel neu. Eine Zeile vor ``aufbaubar_ab`` gibt es nicht; eine davor bleibt
    ohnehin stehen (Bauplan §2). Returns: Zahl der gelöschten Zeilen."""
    kanaele = (await db.execute(select(Kanal).where(and_(
        # HA-Bauform E4d: ALLE abgeleiteten Kanäle der Anlage — der PV-Anteil der Heimladung und der Strom je
        # Betriebsart der Wärmepumpe (``modus_strom.py``) rechnen beide aus dem Spiegel; seit E4e auch die
        # Kosten-Kanäle der Anlage (``abgeleitet:basis:…``, ``kosten.py``).
        Kanal.anlage_id == anlage_id, Kanal.key.like("abgeleitet:%"),
    )))).scalars().all()
    n = 0
    for k in kanaele:
        grenze = max(int(ab_ts), int(k.aufbaubar_ab or ab_ts))
        res = await db.execute(delete(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= grenze,
        )))
        n += res.rowcount or 0
    return n


__all__ = [
    "ACHSE_LADUNG", "AUFTEILUNG_FELDER", "EMOB_TYPEN", "LadeAuswahl", "abgeleitet_key", "lade_auswahl", "schreibe_abgeleitete", "stunde_ableiten", "tag_der_stunde", "verfuegbarkeit", "verwerfe_ab",
]
