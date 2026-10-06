"""Kosten-Kanäle bei gemessenem Stundenpreis — HAs Kostensensor-Muster als abgeleitete kumulative Kanäle
(HA-Bauform E4e, Bauplan §6 U7, Konzept §1 Nr. 5; Auftrag Punkt 1).

**Was sie sind.** Für eine Anlage mit Preis-Kanal ``basis:strompreis`` (Spiegel ``mean`` je Stunde — nur, wenn der
zugeordnete Preissensor eine HA-Langzeitstatistik hat, E1) führt eedc sechs kumulative Kanäle (Art ``sum``, Familie
``abgeleitet``, Quelle ``kosten_je_stunde``):

==========================================  ======  ===============================================================
Schlüssel                                   Einheit  Zuwachs je Stunde (``core/berechnungen/kosten_stunde.py``)
==========================================  ======  ===============================================================
``abgeleitet:basis:kosten_netzbezug``       €        max(0, Δ Netzbezug) × Stundenpreis / 100 — nur mit Preis
``abgeleitet:basis:netzbezug_bewertet_kwh``  kWh      max(0, Δ Netzbezug) — nur mit Preis (Gewicht des Bezugs-Ø)
``abgeleitet:basis:kosten_ev_vermieden``    €        max(0, Δ PV − Δ Einspeisung) × Stundenpreis / 100 — nur mit Preis
``abgeleitet:basis:ev_bewertet_kwh``        kWh      max(0, Δ PV − Δ Einspeisung) — nur mit Preis (Gewicht des EV-Ø)
``abgeleitet:basis:preis_summe``            ct       der Stundenpreis — nur mit Preis (Zähler des arithmetischen Ø)
``abgeleitet:basis:preis_stunden``          h        1 — nur mit Preis (Nenner des arithmetischen Ø, abgedeckte Stunden)
==========================================  ======  ===============================================================

Ein Zeitraum nennt daraus seinen gewichteten Ø als ``Δ Kosten × 100 ÷ Δ bewertete Menge`` (ct/kWh) — zwei
Index-Zugriffe je Kanal, gleich wie lang (Leser: ``preis_leser.py``). ⚑ **Einheit € (Annahme, Bericht E4e):** wie HAs
Kostensensor (``…_cost`` in EUR, ``has_sum``) und ``SlotKosten.kosten_euro``; der Ø in ct entsteht beim Lesen.

**Die Mengen der Stunde** sind die Bilanz-Gruppe der Stunde nach Weg 2 — DIESELBE Komposition wie Tag und Monat
(``core/berechnungen/bilanz_zeitraum.komponiere_bilanz_zeitraum`` auf den Δ der Stunde; Zählerwahl wie der Tagespfad,
``bilanz_adapter.zaehler_eintraege``, Filter aktiv · Anschaffung · Stilllegung je Tag): Netzbezug und Einspeisung als
Summe ihrer Zähler, die PV als Σ Geräte (der Anlagenzähler füllt nur die Geräte ohne Kanal, W2-R2/R3) samt Erzeugern
hinter dem Zähler (wie ``pv_kw`` der Stundenzeile). Ein Zähler ohne Zeile in einer Stunde trägt dort 0 — seine Menge
steht in seiner nächsten Zeile (HAs Regel; die gebündelte Menge trägt den Preis dieser einen Stunde, die benannte
Näherung A-6 von KONZEPT-FLEX-TARIFE, wie im Bestand).

**Der Preis der Stunde** ist das Stundenmittel des Spiegels mit derselben ``start_ts`` (HAs Periode ``[h, h+1)`` —
Menge und Preis derselben Stunde, ohne die Zeilen-Verschiebung N-387 der Stundentabelle), umgerechnet auf ct/kWh mit
derselben Regel wie die Mitschrift (``energie_profil._helpers._strompreis_faktor``: EUR/kWh × 100, EUR/MWh × 0,1).
Eine Stunde ohne Preiszeile ist nicht bewertet (A-3) — kein Monatsmittel springt ein (P-4).

⛔ **Kein Einspeise-Erlös-Kanal** (Entscheid Master zu E4e): er hätte keinen Leser (Monat und Jahr rechnen den Erlös aus
Δ Einspeisung × Monatssatz − §51) und keinen Neuaufbau bei Tarifänderung — tote, möglicherweise falsche Daten. Der
Katalog führt ihn als „geplant, kein Schreiber"; kommt er, dann mit Leser und Tarif-Neuaufbau in einem Zug.

**Preis-Summe und Preis-Stunden** (Entscheid Fable zu E4e): der arithmetische Ø und die Zahl der Stunden mit Preis sind
ein Δ wie die Kosten — der Leser braucht kein Mittel je Monat (12 Jahre: eine Anweisung statt 142).

**Ohne Preis-Kanal** (kein Preissensor, Sensor ohne Langzeitstatistik, fester Tarif, HT/NT) entsteht kein
Kosten-Kanal — der heutige Leser rechnet (Lesart 1, Bauplan §3b).

**Wann geschrieben wird.** Eine Stunde ``h`` erst, wenn jeder Mengen-Kanal der Bilanz-Zähler des Tages (je
Entweder-oder-Gruppe einer) und der Preis-Kanal eine Zeile bei ``h`` oder später haben — der Spiegel des Laufs muss
sie geschrieben haben. Bleibt der Preis-Kanal stehen (Sensor entfernt, HA lange weg), bleibt der Kosten-Kanal stehen:
der Zeitraum gilt als nicht gedeckt, der heutige Leser rechnet (die sichere Richtung).

**``aufbaubar_ab`` und Beginn** (H-2 aus E4c): ein neuer Kanal beginnt beim ersten Lauf eine Stunde vor dem
Monatsfenster des laufenden Monats, und erst ab einer Stunde, in der jeder Mengen-Kanal einen Vorstand hat — kein
abgeschlossener Monat wird gedeckt, kein Monat aus Nullen. Neuaufbau nach einer Korrektur des Spiegels:
``abgeleitet.verwerfe_ab`` (Konsistenzlauf) verwirft alle ``abgeleitet:``-Kanäle ab ``max(ab_ts, aufbaubar_ab)``.

**Isolation:** gerufen aus ``schreiber.schreibe_kanaele_im_stundenlauf`` im selben SAVEPOINT, NACH Spiegel (auch dem
Preis-Spiegel), eigener Summe und den übrigen abgeleiteten Kanälen.

Schwesterdateien: ``preis_leser.py`` (Leser), ``abgeleitet.py`` (Vorbild), ``modus_strom.py``, ``schreiber.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.bilanz_zeitraum import Eingang, komponiere_bilanz_zeitraum
from backend.core.berechnungen.kosten_stunde import KostenStunde, kosten_der_stunde
from backend.models.kanal import ART_MEAN, ART_SUM, FAMILIE_ABGELEITET, Kanal, KanalQuelle, KanalStatistik

logger = logging.getLogger(__name__)

_STUNDE = 3600
#: ``kanal_quelle.statistic_id`` der Familie ``abgeleitet`` — die Regel, nach der gerechnet ist.
REGEL_KOSTEN = "kosten_je_stunde"
#: Der Preis-Kanal (Spiegel ``mean``, E1).
PREIS_KEY = "basis:strompreis"
EINHEIT_EURO = "€"

KOSTEN_NETZBEZUG_KEY = "abgeleitet:basis:kosten_netzbezug"
NETZBEZUG_BEWERTET_KEY = "abgeleitet:basis:netzbezug_bewertet_kwh"
KOSTEN_EV_KEY = "abgeleitet:basis:kosten_ev_vermieden"
EV_BEWERTET_KEY = "abgeleitet:basis:ev_bewertet_kwh"
PREIS_SUMME_KEY = "abgeleitet:basis:preis_summe"
PREIS_STUNDEN_KEY = "abgeleitet:basis:preis_stunden"

#: Schlüssel → (Einheit, Feld von ``KostenStunde``).
KOSTEN_KANAELE: dict[str, tuple[str, str]] = {
    KOSTEN_NETZBEZUG_KEY: (EINHEIT_EURO, "kosten_netzbezug_euro"),
    NETZBEZUG_BEWERTET_KEY: ("kWh", "netzbezug_bewertet_kwh"),
    KOSTEN_EV_KEY: (EINHEIT_EURO, "kosten_ev_vermieden_euro"),
    EV_BEWERTET_KEY: ("kWh", "ev_bewertet_kwh"),
    PREIS_SUMME_KEY: ("ct", "preis_summe_cent"),
    PREIS_STUNDEN_KEY: ("h", "preis_stunden"),
}

#: Die Kategorien der Bilanz-Zähler, aus denen die Mengen der Stunde komponiert werden.
_KATEGORIEN = frozenset({"netzbezug", "einspeisung", "pv", "erzeugung_sonstiges"})


def _unix(dt: datetime) -> int:
    return int(round(dt.timestamp()))


def preis_faktor(einheit: Optional[str]) -> float:
    """Faktor der Kanal-Einheit (HAs Einheit beim Anlegen) nach ct/kWh — dieselbe Regel wie die Mitschrift der
    Stundenzeile (``energie_profil._helpers._strompreis_faktor``)."""
    from backend.services.energie_profil._helpers import _strompreis_faktor

    return _strompreis_faktor(einheit)


# ── Auswahl je Tag ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _TagesAuswahl:
    eintraege: tuple            # Bilanz-Zähler der Kategorien `_KATEGORIEN` (TabellenEintrag)
    traeger: tuple              # PvTraeger der aktiven Erzeuger


async def _auswahl_je_tag(db: AsyncSession, anlage_id: int, tage: list[date]) -> dict[date, _TagesAuswahl]:
    from backend.services.kanal.bilanz_leser import _stamm, _traeger

    stamm = await _stamm(db, anlage_id)
    out: dict[date, _TagesAuswahl] = {}
    for t in tage:
        eintraege = await stamm.eintraege(db, lambda i, t=t: i.ist_aktiv_an(t), t)
        out[t] = _TagesAuswahl(
            tuple(e for e in eintraege if e.kategorie in _KATEGORIEN),
            tuple(_traeger(stamm.invs, lambda inv, t=t: inv.ist_aktiv_an(t))),
        )
    return out


def _noetig(auswahl: _TagesAuswahl, vorhanden: set[str]) -> Optional[set[str]]:
    """Die Mengen-Kanäle, die eine Stunde dieses Tages braucht: jeder Zähler ohne Gruppe, je Entweder-oder-Gruppe die
    Mitglieder mit Kanal. ``None``, wenn ein Zähler ohne Gruppe keinen Kanal hat oder eine Gruppe keinen — dann ist
    die Stunde nicht rechenbar (der Kosten-Kanal wartet)."""
    noetig: set[str] = set()
    gruppen: dict[str, list[str]] = {}
    for e in auswahl.eintraege:
        if e.gruppe:
            gruppen.setdefault(e.gruppe, []).append(e.schluessel)
        elif e.schluessel in vorhanden:
            noetig.add(e.schluessel)
        else:
            return None
    for mitglieder in gruppen.values():
        mit = [k for k in mitglieder if k in vorhanden]
        if not mit:
            return None
        noetig.update(mit)
    return noetig


def mengen_der_stunde(auswahl: _TagesAuswahl, deltas: dict[str, float]) -> tuple[Optional[float], Optional[float],
                                                                                 Optional[float]]:
    """(Netzbezug, PV inkl. Erzeuger hinter dem Zähler, Einspeisung) einer Stunde aus den Δ ihrer Zähler — Weg 2
    (``komponiere_bilanz_zeitraum``) auf die Stunde. ``deltas``: Kanal-Schlüssel → Δ der Stunde (ohne Zeile: 0)."""
    from backend.services.snapshot.komponenten_beitraege import resolve_either_or_eintraege

    gewaehlt = resolve_either_or_eintraege(
        list(auswahl.eintraege), gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: e.schluessel in deltas,
    )
    from backend.services.kanal.bilanz_leser import _AGGREGAT_KEY

    eingaenge = []
    for e in gewaehlt:
        pv_id = None
        if e.kategorie == "pv" and e.sensor_key != _AGGREGAT_KEY:
            pv_id = int(e.sensor_key.split(":", 2)[1])
        eingaenge.append(Eingang(e.kategorie, e.target_key, e.vorzeichen, deltas.get(e.schluessel), pv_id))
    k = komponiere_bilanz_zeitraum(eingaenge, list(auswahl.traeger))
    if k is None:
        return None, None, None
    pv = None
    if "pv" in k.kat_summe or "erzeugung_sonstiges" in k.kat_summe:
        pv = k.kat_summe.get("pv", 0.0) + k.kat_summe.get("erzeugung_sonstiges", 0.0)
    return k.kat_summe.get("netzbezug"), pv, k.kat_summe.get("einspeisung")


# ── Schreiben ───────────────────────────────────────────────────────────────


async def _preise(db: AsyncSession, kanal: Kanal, von: int, bis_inkl: int) -> dict[int, float]:
    """Stundenmittel des Preis-Kanals ``start_ts ∈ [von, bis_inkl]`` in ct/kWh."""
    faktor = preis_faktor(kanal.einheit)
    zeilen = (await db.execute(select(KanalStatistik.start_ts, KanalStatistik.mean).where(and_(
        KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts >= von, KanalStatistik.start_ts <= bis_inkl,
        KanalStatistik.mean.isnot(None),
    )))).all()
    return {int(ts): float(m) * faktor for ts, m in zeilen}


async def _letzter_preis(db: AsyncSession, kanal: Kanal) -> Optional[int]:
    return (await db.execute(select(KanalStatistik.start_ts).where(and_(
        KanalStatistik.kanal_id == kanal.id, KanalStatistik.mean.isnot(None),
    )).order_by(KanalStatistik.start_ts.desc()).limit(1))).scalar_one_or_none()


async def schreibe_kosten(
    db: AsyncSession, anlage, zeitpunkt: datetime, *, ab_ts: Optional[int] = None,
) -> int:
    """Die Kosten-Kanäle der Anlage bis zur Stunde vor ``zeitpunkt`` fortschreiben.

    Je Kanal ab seiner letzten Zeile (bzw. ``aufbaubar_ab``, wenn verworfen wurde); ein neuer Kanal ab ``ab_ts`` —
    ohne ``ab_ts`` eine Stunde vor dem Monatsfenster des laufenden Monats (H-2). Returns: Zahl der geschriebenen Zeilen.
    """
    from backend.services.kanal.abgeleitet import tag_der_stunde
    from backend.services.kanal.fenster import monatsfenster
    from backend.services.kanal.lesen import kanaele_laden, stunden_stapel
    from backend.services.kanal.schreiber import _zeilen_einfuegen, kanaele_holen, letzte_zeilen

    preis_kanal = (await kanaele_laden(db, anlage.id, [PREIS_KEY])).get(PREIS_KEY)
    if preis_kanal is None or preis_kanal.art != ART_MEAN:
        return 0
    ts_bis = (_unix(zeitpunkt) // _STUNDE) * _STUNDE - _STUNDE

    vorhanden = await kanaele_laden(db, anlage.id, list(KOSTEN_KANAELE))
    letzte = await letzte_zeilen(db, [k.id for k in vorhanden.values()])
    weiter_ab: dict[str, int] = {}
    stand: dict[str, float] = {}
    for key, k in vorhanden.items():
        z = letzte.get(k.id)
        weiter_ab[key] = (z.start_ts + _STUNDE) if z is not None else int(k.aufbaubar_ab or ts_bis)
        stand[key] = float(z.sum) if z is not None and z.sum is not None else 0.0
    if ab_ts is not None:
        neu_ab = int(ab_ts)
    else:
        tag = tag_der_stunde(ts_bis)
        neu_ab = monatsfenster(tag.year, tag.month)[0] - _STUNDE
    offen = [key for key in KOSTEN_KANAELE if key not in vorhanden]
    start = min([*weiter_ab.values(), *([neu_ab] if offen else [])], default=neu_ab)
    if start > ts_bis:
        return 0
    letzter_preis = await _letzter_preis(db, preis_kanal)
    if letzter_preis is None or letzter_preis < start:
        return 0                                          # der Preis-Spiegel ist noch nicht so weit

    tage: list[date] = []
    t, ende_tag = tag_der_stunde(start), tag_der_stunde(ts_bis)
    while t <= ende_tag:
        tage.append(t)
        t += timedelta(days=1)
    auswahl = await _auswahl_je_tag(db, anlage.id, tage)
    schluessel = {e.schluessel for a in auswahl.values() for e in a.eintraege}
    mengen = [k for k in (await kanaele_laden(db, anlage.id, schluessel)).values() if k.art == ART_SUM]
    if not mengen:
        return 0
    je = await stunden_stapel(db, mengen, start, ts_bis + _STUNDE, jetzt=_unix(zeitpunkt) + _STUNDE)
    werte = {key: {w.start_ts: w for w in st.werte} for key, st in je.items()}
    erreicht = {key: max(w) if w else None for key, w in werte.items()}
    preise = await _preise(db, preis_kanal, start, ts_bis)

    neue: dict[str, list[tuple[int, float]]] = {}
    begonnen: dict[str, int] = {}
    h = start
    while h <= ts_bis:
        if h > letzter_preis:
            break
        a = auswahl[tag_der_stunde(h)]
        noetig = _noetig(a, {k for k, e in erreicht.items() if e is not None})
        if noetig is None or any(erreicht[k] < h for k in noetig):
            break                                          # ein Eingang ist noch nicht so weit — später weiter
        mit_vorstand = all(h in werte[k] and werte[k][h].change is not None for k in noetig)
        deltas = {k: (werte[k][h].change or 0.0) if h in werte[k] else 0.0 for k in noetig}
        netz, pv, einsp = mengen_der_stunde(a, deltas)
        stunde: KostenStunde = kosten_der_stunde(
            netzbezug_kwh=netz, pv_kwh=pv, einspeisung_kwh=einsp, preis_cent=preise.get(h),
        )
        for key, (_einheit, feld) in KOSTEN_KANAELE.items():
            ab = weiter_ab.get(key, neu_ab)
            if h < ab or (key not in weiter_ab and key not in begonnen and not mit_vorstand):
                continue
            begonnen.setdefault(key, h)
            stand[key] = stand.get(key, 0.0) + getattr(stunde, feld)
            neue.setdefault(key, []).append((h, stand[key]))
        h += _STUNDE
    if not neue:
        return 0

    kanaele_neu = await kanaele_holen(db, anlage.id, {key: (ART_SUM, KOSTEN_KANAELE[key][0]) for key in neue})
    zeilen: list[dict] = []
    for key, punkte in neue.items():
        kanal = kanaele_neu[key]
        if kanal.aufbaubar_ab is None:
            kanal.aufbaubar_ab = punkte[0][0]
            db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=punkte[0][0], familie=FAMILIE_ABGELEITET,
                               statistic_id=REGEL_KOSTEN, offset=0.0))
        zeilen.extend({"kanal_id": kanal.id, "start_ts": ts, "sum": s, "state": None, "mean": None, "min": None,
                       "max": None, "familie": FAMILIE_ABGELEITET} for ts, s in punkte)
    await db.flush()
    return await _zeilen_einfuegen(db, zeilen)


__all__ = [
    "EINHEIT_EURO", "EV_BEWERTET_KEY", "KOSTEN_EV_KEY", "KOSTEN_KANAELE",
    "KOSTEN_NETZBEZUG_KEY", "NETZBEZUG_BEWERTET_KEY", "PREIS_KEY", "PREIS_STUNDEN_KEY", "PREIS_SUMME_KEY",
    "REGEL_KOSTEN", "mengen_der_stunde",
    "preis_faktor", "schreibe_kosten",
]
