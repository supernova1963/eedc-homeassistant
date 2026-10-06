"""Leser der Bilanz-Gruppe aus Kanälen — Weg 2 (HA-Bauform E4a-2, Bauplan §6b; Auftrag Punkt 2).

**Die eine Fassade, über die Sichten die Kanäle der Bilanz-Gruppe lesen** (Netz, PV/Balkonkraftwerk samt
Anlagenzähler, Speicher Ladung/Entladung, Erzeuger hinter dem Zähler). Je Zeitraum (Tag, Monat):

1. die Zähler, die der Tagespfad für die Gruppe nähme (``bilanz_adapter.zaehler_eintraege`` → ``bilanz_eintraege``,
   Filter aktiv · Anschaffung · Stilllegung je Zeitraum); sie hängen nur an der Menge der aktiven Investitionen und
   werden je Menge EINMAL gebildet (eine Anlage mit vier Anschaffungen hat fünf Mengen, nicht 4 400 Tage);
2. je Kanal Δ und Abdeckung über ``lesen.reihe_stapel`` — EINE Anweisung für alle Zeiträume;
3. die EINE Quellenwahl (§3b) mit Entweder-oder (W2-R4, Bestätigung B-4): eine Ersatzgruppe ist gedeckt, wenn ein
   Kanal der Gruppe den Zeitraum voll deckt; jeder übrige Zähler muss selbst voll decken. ``kanal`` ⇒ die Komposition
   ``core/berechnungen/bilanz_zeitraum.komponiere_bilanz_zeitraum`` (W2-R1…R5); ``bestand`` ⇒ der Aufrufer rechnet
   den Zeitraum mit dem heutigen Leser (Lesart 1).

**Kein Deckel, kein Rücksprung-Verwurf** (R-5, HA-Teil): das Δ ist der Spiegel, wie HA ihn führt. Für Nicht-HA-
Quellen ist der Kanal die eigene Summe — dort wirkt der Deckel schon als Schreibfilter (``schreiber.py``).

**Lückentag wie HA** (Auftrag Punkt 4, Gegenprüfung „Übersehen" T4): an einem BEENDETEN Tag zählt ein Kanal, dessen
Rand in einer Spanne > Tag liegt (``feiner_als_spanne``), als gedeckt, mit ``teil_delta`` — der erste Tag nach einer
Randlücke trägt die Lückenmenge; ein Tag ganz in der Lücke trägt 0 — mit Wahl ``kanal``, nicht „ohne Wert" (die
Formulierung „ohne Punkt" der Gegenprüfung T4 galt dem Tageskanal von Weg 1) —, wie das HA-Energie-Dashboard. Regel (c) der Lese-Schicht
bleibt für Monate und den laufenden Tag.

Rückgabeformen: je Tag ``bilanz_adapter.KanalTag`` (Fassung ``weg2``), je Monat ``monats_aus_tagen.TagesMonatsSumme``
(über dieselbe Faltung ``falte_monat``); dazu die Fassaden ``lade_monats_summen`` (Kanal-Monate + Bestand-Monate,
E-Mob-Aufteilung aus dem Bestand, Entscheid D2), ``kanal_tage`` (nur Kanal-Tage) und ``monatswerte_mit_kanaelen``
(Kalendermonat je Sensor, B-2).
"""

from __future__ import annotations

import dataclasses
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.anlagen_kwp import BKW_TYP, PV_MODUL_TYP
from backend.core.berechnungen.bilanz_zeitraum import BilanzZeitraum, Eingang, komponiere_bilanz_zeitraum
from backend.core.berechnungen.pv_verteilung import PvTraeger
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import ART_SUM
from backend.services.energie_profil.monats_aus_tagen import (
    MonatsSchluessel,
    TagesMonatsSumme,
    TagesZeile,
    falte_monat,
)
from backend.services.kanal.bilanz_adapter import (
    BILANZ_ACHSEN,
    KanalTag,
    bilanz_eintraege,
    zaehler_eintraege,
)
from backend.services.kanal.fenster import (
    kalendermonatsfenster,
    monate,
    monatsgrenzen,
    tagesfenster,
)
from backend.services.kanal.lesen import (
    GRUND_FEINER_ALS_SPANNE,
    GRUND_KEIN_KANAL,
    Zeitraum,
    kanaele_laden,
    reihe_stapel,
    soll_ende,
)
from backend.services.kanal.quellenwahl import QUELLE_BESTAND, QUELLE_KANAL, Quellenwahl
from backend.services.snapshot.keys import PV_AGGREGAT_BASIS_FELD
from backend.services.snapshot.komponenten_beitraege import resolve_either_or_eintraege

FASSUNG_WEG2 = "weg2"
_AGGREGAT_KEY = f"basis:{PV_AGGREGAT_BASIS_FELD}"
_STUNDE = 3600


# ── Stammdaten und Zähler je Menge aktiver Investitionen ────────────────────


@dataclass
class _Stamm:
    anlage: Any
    invs: list
    _cache: dict

    async def eintraege(self, db: AsyncSession, aktiv, stichtag: date) -> list:
        """Die Bilanz-Zähler bei der Menge ``aktiv`` (Prädikat je Investition) — je Menge einmal gebildet. Die
        Auswahl hängt außer an der Menge nur an der Wallbox-Regel (E-Mob, nicht Teil der Gruppe)."""
        menge = frozenset(i.id for i in self.invs if aktiv(i))
        if menge not in self._cache:
            invs_by_id = {str(i.id): i for i in self.invs if i.id in menge}
            self._cache[menge] = bilanz_eintraege(await zaehler_eintraege(db, self.anlage, invs_by_id, stichtag))
        return self._cache[menge]


async def _stamm(db: AsyncSession, anlage_id: int) -> _Stamm:
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all())
    return _Stamm(anlage, invs, {})


def _traeger(invs: Iterable, aktiv) -> list[PvTraeger]:
    from backend.services.pv_monatswerte import _kwp_gewicht

    return [PvTraeger(i.id, i.typ, float(_kwp_gewicht(i) or 0.0), getattr(i, "parent_investition_id", None))
            for i in invs if getattr(i, "typ", None) in (PV_MODUL_TYP, BKW_TYP) and aktiv(i)]


# ── Quellenwahl und Komposition je Zeitraum ─────────────────────────────────


@dataclass(frozen=True)
class KanalZeitraum:
    """Ein Zeitraum aus den Kanälen: die Wahl, bei ``kanal`` die Komposition."""

    wahl: Quellenwahl
    komposition: Optional[BilanzZeitraum]


def _gedeckt(z: Optional[Zeitraum], lueckentag: bool) -> tuple[bool, Optional[float]]:
    if z is None:
        return False, None
    if z.voll:
        return True, z.delta
    if lueckentag and z.grund == GRUND_FEINER_ALS_SPANNE and not z.laufend and z.teil_delta is not None:
        return True, z.teil_delta
    return False, None


def waehle_und_komponiere(
    eintraege: Sequence, ergebnisse: dict[str, Zeitraum], traeger: Sequence[PvTraeger], *, lueckentag: bool,
) -> KanalZeitraum:
    """Die Quellenwahl der Gruppe (B-4) und — bei ``kanal`` — W2 auf den Δ. Reine Funktion."""
    if not eintraege:
        return KanalZeitraum(Quellenwahl(QUELLE_BESTAND, {"": "keine_eingaenge"}, {}), None)
    deltas: dict[str, Optional[float]] = {}
    for e in eintraege:
        ok, d = _gedeckt(ergebnisse.get(e.schluessel), lueckentag)
        deltas[e.schluessel] = d if ok else None
    gruende: dict[str, str] = {}
    gruppen: dict[str, list] = {}
    for e in eintraege:
        if e.gruppe:
            gruppen.setdefault(e.gruppe, []).append(e)
        elif deltas.get(e.schluessel) is None:
            z = ergebnisse.get(e.schluessel)
            gruende[e.schluessel] = GRUND_KEIN_KANAL if z is None else (z.grund or "nicht_voll")
    for mitglieder in gruppen.values():
        if not any(deltas.get(e.schluessel) is not None for e in mitglieder):
            z = ergebnisse.get(mitglieder[0].schluessel)
            gruende[mitglieder[0].schluessel] = GRUND_KEIN_KANAL if z is None else (z.grund or "nicht_voll")
    vorhanden = {e.schluessel: ergebnisse[e.schluessel] for e in eintraege if e.schluessel in ergebnisse}
    if gruende:
        return KanalZeitraum(Quellenwahl(QUELLE_BESTAND, gruende, vorhanden), None)
    gewaehlt = resolve_either_or_eintraege(
        eintraege, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: deltas.get(e.schluessel) is not None,
    )
    eingaenge = []
    for e in gewaehlt:
        pv_id = None
        if e.kategorie == "pv" and e.sensor_key != _AGGREGAT_KEY:
            pv_id = int(e.sensor_key.split(":", 2)[1])
        eingaenge.append(Eingang(e.kategorie, e.target_key, e.vorzeichen, deltas.get(e.schluessel), pv_id))
    return KanalZeitraum(Quellenwahl(QUELLE_KANAL, {}, vorhanden), komponiere_bilanz_zeitraum(eingaenge, traeger))


async def _ergebnisse(db, anlage_id: int, keys: set[str], grenzen: list[int], jetzt: int) -> dict[str, list]:
    kanaele = await kanaele_laden(db, anlage_id, keys)
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    if not mengen or len(grenzen) < 2:
        return {}
    return await reihe_stapel(db, mengen, grenzen, jetzt=jetzt)


def _tage(von: date, bis: date) -> list[date]:
    out, d = [], von
    while d <= bis:
        out.append(d)
        d += timedelta(days=1)
    return out


def uhr() -> int:
    """Die Uhr der Leser (Unix-Sekunden) — EINE Stelle, damit Proben mit gestellter Uhr (Matrizen) sie stellen."""
    return int(_time.time())


def _jetzt(jetzt: Optional[int]) -> int:
    return uhr() if jetzt is None else int(jetzt)


async def tage_bilanz(
    db: AsyncSession, anlage_id: int, von: date, bis: date, *, jetzt: Optional[int] = None,
) -> dict[date, KanalZeitraum]:
    """Je Tag ``von`` … ``bis`` mit fälliger Stunde die Wahl und (bei ``kanal``) die Komposition."""
    jetzt = _jetzt(jetzt)
    se = soll_ende(jetzt)
    tage = [t for t in _tage(von, bis) if tagesfenster(t)[0] < se]
    if not tage:
        return {}
    stamm = await _stamm(db, anlage_id)
    je_tag = {t: await stamm.eintraege(db, lambda i, t=t: i.ist_aktiv_an(t), t) for t in tage}
    keys = {e.schluessel for lst in je_tag.values() for e in lst}
    grenzen = [tagesfenster(t)[0] for t in tage] + [tagesfenster(tage[-1])[1]]
    # Tage sind aufeinanderfolgend — die Grenzen stoßen lückenlos aneinander; an einem Umstellungstag bleibt das so.
    je = await _ergebnisse(db, anlage_id, keys, grenzen, jetzt)
    out: dict[date, KanalZeitraum] = {}
    for i, t in enumerate(tage):
        ergebnisse = {k: liste[i] for k, liste in je.items()}
        out[t] = waehle_und_komponiere(je_tag[t], ergebnisse, _traeger(stamm.invs, lambda inv, t=t: inv.ist_aktiv_an(t)),
                                       lueckentag=True)
    return out


def _letzter_tag(jahr: int, monat: int) -> date:
    return (date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)) - timedelta(days=1)


async def monate_bilanz(
    db: AsyncSession, anlage_id: int, von: MonatsSchluessel, bis: MonatsSchluessel, *, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, KanalZeitraum]:
    """Je Monat (``fenster.monatsfenster`` — die Grenze von ``lade_monats_summen_aus_tagen``) mit fälliger Stunde EIN
    Δ je Kanal und EINE Komposition. Der laufende Monat reicht bis zum letzten geschriebenen Stand."""
    jetzt = _jetzt(jetzt)
    se = soll_ende(jetzt)
    liste = monate(von, bis)
    if not liste:
        return {}
    grenzen = monatsgrenzen(von, bis)
    faellig = [(j, m) for i, (j, m) in enumerate(liste) if grenzen[i] < se]
    if not faellig:
        return {}
    stamm = await _stamm(db, anlage_id)
    je_monat = {(j, m): await stamm.eintraege(db, lambda inv, j=j, m=m: inv.ist_aktiv_im_monat(j, m),
                                              _letzter_tag(j, m)) for j, m in faellig}
    keys = {e.schluessel for lst in je_monat.values() for e in lst}
    je = await _ergebnisse(db, anlage_id, keys, grenzen, jetzt)
    out: dict[MonatsSchluessel, KanalZeitraum] = {}
    for i, (j, m) in enumerate(liste):
        if (j, m) not in je_monat:
            continue
        ergebnisse = {k: lst[i] for k, lst in je.items()}
        out[(j, m)] = waehle_und_komponiere(
            je_monat[(j, m)], ergebnisse, _traeger(stamm.invs, lambda inv, j=j, m=m: inv.ist_aktiv_im_monat(j, m)),
            lueckentag=False)
    return out


# ── Rückgabeformen ──────────────────────────────────────────────────────────


def als_kanaltag(datum: date, k: BilanzZeitraum) -> KanalTag:
    return KanalTag(
        datum=datum, fassung=FASSUNG_WEG2, komponenten_kwh={kk: round(v, 2) for kk, v in k.komponenten.items()},
        pv_marken=dict(k.marken), verworfen={}, bilanz=k.bilanz, stunden=0,
        wandlungsverluste_kwh=k.pv.wandlungsverluste_kwh if k.pv else None,
    )


def als_monatssumme(jahr: int, monat: int, k: BilanzZeitraum, *, jetzt: int) -> TagesMonatsSumme:
    """Der Monat in der Datenform von ``lade_monats_summen_aus_tagen`` — über DIESELBE Faltung (eine Pseudo-Zeile);
    ``tage``/``erster_tag``/``letzter_tag`` sind die Tage des Monats mit fälliger Stunde (der Kanal deckt sie voll),
    ``stunden`` 0 (keine Stundenzeile)."""
    d0 = date(jahr, monat, 1)
    prov = {f"komponenten_kwh.{kk}": {"abgeleitet": v} for kk, v in k.marken.items()}
    s = falte_monat(stunden_tage=[(d0, k.bilanz, 0)],
                    tageszeilen=[TagesZeile(datum=d0, komponenten_kwh=k.komponenten, source_provenance=prov)])
    se = soll_ende(jetzt)
    tage = [t for t in _tage(d0, _letzter_tag(jahr, monat)) if tagesfenster(t)[0] < se]
    # E4c: die Sonstiges-Erzeuger der Komposition — in der Bilanz-Gruppe stehen nur Erzeuger hinter dem Zähler
    # (Kategorie `erzeugung_sonstiges`), ihr Ziel ist `sonstige_<id>`.
    erzeuger = {kk[len("sonstige_"):]: v for kk, v in k.komponenten.items() if kk.startswith("sonstige_")}
    return dataclasses.replace(s, tage=len(tage), stunden=0, erster_tag=tage[0] if tage else None,
                               letzter_tag=tage[-1] if tage else None, sonstige_erzeuger_je_inv=erzeuger,
                               wandlungsverluste_kwh=k.pv.wandlungsverluste_kwh if k.pv else None,
                               wandlungsverluste_bezug_kwh=(k.pv.geraete_kwh if k.pv and k.pv.wandlungsverluste_kwh
                                                            is not None else None))


# ── Fassaden für die Sichten ────────────────────────────────────────────────

#: Felder der Monatssumme, die NICHT zur Bilanz-Gruppe gehören (E-Mob-Aufteilung) — bleiben aus dem Bestand (D2). Seit
#: E4c nehmen die Monats-Fakten für einen Monat, dessen E-Mob-Gruppe die Kanäle decken, den Anteil des abgeleiteten
#: Kanals (`kanal/geraete_leser.py`); diese Felder tragen dann nur noch „davon aus dem Speicher" (Ausweis).
_NICHT_GRUPPE = ("emob_ladung_pv_abgeleitet_kwh", "emob_ladung_netz_abgeleitet_kwh",
                 "emob_ladung_speicher_abgeleitet_kwh")


async def _erster_kanal_monat(db: AsyncSession, anlage_id: int) -> Optional[MonatsSchluessel]:
    ts = (await db.execute(text(
        "SELECT MIN((SELECT MIN(s.start_ts) FROM kanal_statistik s WHERE s.kanal_id = k.id)) "
        "FROM kanal k WHERE k.anlage_id = :a"), {"a": anlage_id})).scalar()
    if ts is None:
        return None
    d = datetime.fromtimestamp(int(ts)).date()
    return d.year, d.month


async def hat_anlagenzaehler_kanal(db: AsyncSession, anlage_id: int) -> bool:
    """Hat die Anlage einen Kanal für den Anlagen-PV-Zähler (``basis:pv_gesamt``)? — die Vorfrage der
    Wandlungsverluste (HA-Bauform E4b, B-1): ohne ihn sind sie ``None``, und niemand muss die Kanal-Monate laden."""
    from backend.models.kanal import Kanal

    return (await db.execute(select(Kanal.id).where(
        Kanal.anlage_id == anlage_id, Kanal.key == _AGGREGAT_KEY,
    ).limit(1))).scalar_one_or_none() is not None


async def kanal_monate(
    db: AsyncSession, anlage_id: int, *, von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, TagesMonatsSumme]:
    """Die Monate im Fenster, für die die Bilanz-Gruppe aus den Kanälen kommt (Wahl ``kanal``), als Monatssumme.
    Offenes ``von``: ab dem ersten Kanal-Stand der Anlage; offenes ``bis``: bis zum laufenden Monat."""
    jetzt = _jetzt(jetzt)
    if von is None:
        von = await _erster_kanal_monat(db, anlage_id)
        if von is None:
            return {}
    if bis is None:
        d = datetime.fromtimestamp(jetzt).date()
        bis = (d.year, d.month)
    if von > bis:
        return {}
    out = {}
    for (j, m), kz in (await monate_bilanz(db, anlage_id, von, bis, jetzt=jetzt)).items():
        if kz.wahl.quelle == QUELLE_KANAL and kz.komposition is not None:
            out[(j, m)] = als_monatssumme(j, m, kz.komposition, jetzt=jetzt)
    return out


async def lade_monats_summen(
    db: AsyncSession, anlage_id: int, *, von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None, stunden_nur_fuer: Optional[set[MonatsSchluessel]] = None,
    jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, TagesMonatsSumme]:
    """``lade_monats_summen_aus_tagen`` mit der Quellenwahl je Monat (E4a-2, Umschaltstelle Monat): Monate mit Wahl
    ``kanal`` aus den Kanälen (W2), die übrigen unverändert aus der Tagesebene (Lesart 1). Die E-Mob-Aufteilung eines
    Kanal-Monats kommt aus dem Bestand (D2); die Stunden des Bestands werden für Kanal-Monate nicht geladen."""
    from backend.services.energie_profil.monats_aus_tagen import lade_monats_summen_aus_tagen

    kanal = await kanal_monate(db, anlage_id, von=von, bis=bis, jetzt=jetzt)
    if stunden_nur_fuer is None and kanal:
        # Alle Monate des Bestands außer den Kanal-Monaten — ohne Fenster: die Monate mit Tageszeilen.
        stunden_nur_fuer = await _bestand_monate(db, anlage_id, von, bis)
    if stunden_nur_fuer is not None:
        stunden_nur_fuer = set(stunden_nur_fuer) - set(kanal)
    bestand = await lade_monats_summen_aus_tagen(db, anlage_id, von=von, bis=bis, stunden_nur_fuer=stunden_nur_fuer)
    out = dict(bestand)
    for m, k in kanal.items():
        b = bestand.get(m)
        out[m] = dataclasses.replace(k, **{f: getattr(b, f) for f in _NICHT_GRUPPE}) if b is not None else k
    return out


async def _bestand_monate(db, anlage_id, von, bis) -> set[MonatsSchluessel]:
    from backend.models.tages_energie_profil import TagesZusammenfassung

    q = select(TagesZusammenfassung.datum).where(TagesZusammenfassung.anlage_id == anlage_id)
    out = {(d.year, d.month) for (d,) in (await db.execute(q)).all()}
    return {m for m in out if (von is None or m >= von) and (bis is None or m <= bis)}


async def kanal_tage(
    db: AsyncSession, anlage_id: int, von: date, bis: date, *, jetzt: Optional[int] = None,
) -> dict[date, KanalTag]:
    """Die Tage ``von`` … ``bis``, deren Bilanz-Gruppe aus den Kanälen kommt (Wahl ``kanal``) — Umschaltstelle der
    Tages-Leser. Ein Tag mit Wahl ``bestand`` fehlt: der Leser rechnet ihn aus Tages- und Stundenzeilen."""
    return {t: als_kanaltag(t, kz.komposition)
            for t, kz in (await tage_bilanz(db, anlage_id, von, bis, jetzt=jetzt)).items()
            if kz.wahl.quelle == QUELLE_KANAL and kz.komposition is not None}


#: Die ``komponenten_kwh``-Schlüssel, die an einem Kanal-Tag aus dem Kanal kommen (B-3): die PV-Träger und jedes
#: Ziel eines Bilanz-Zählers. Alle übrigen Schlüssel der Tageszeile bleiben.
def ist_bilanz_schluessel(key: str, ziele: set[str]) -> bool:
    k = str(key)
    if k in ziele or k == PV_AGGREGAT_BASIS_FELD:
        return True
    from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE

    for p in PV_KOMPONENTEN_PREFIXE:
        if k.startswith(p) and k[len(p):].isdigit():
            return True
    return False


async def bilanz_ziele(db: AsyncSession, anlage_id: int, tage: Iterable[date]) -> dict[date, set[str]]:
    """Je Tag die Ziel-Schlüssel der Bilanz-Zähler (für das Mischen der Tageszeile, B-3)."""
    stamm = await _stamm(db, anlage_id)
    return {t: {e.target_key for e in await stamm.eintraege(db, lambda i, t=t: i.ist_aktiv_an(t), t)} for t in tage}


def mische_komponenten(tageszeile: Optional[dict], kanal: KanalTag, ziele: set[str]) -> dict:
    """B-3: die Bilanz-Schlüssel aus dem Kanal-Tag, alle übrigen aus der Tageszeile."""
    out = {k: v for k, v in (tageszeile or {}).items() if not ist_bilanz_schluessel(k, ziele)}
    out.update(kanal.komponenten_kwh)
    return out


def mische_verworfen(verworfen: Optional[dict]) -> dict:
    """Die Regelmarke eines Kanal-Tags: was die Tageszeile auf den Bilanz-Achsen verworfen hat, gilt nicht mehr (der
    Kanal verwirft nichts); Befunde anderer Achsen bleiben."""
    return {k: v for k, v in (verworfen or {}).items() if k not in BILANZ_ACHSEN}


def mische_bilanz(kanal, stunden):
    """B-3/D4: Mengen, Gesamtverbrauch, Eigenverbrauch und Quoten aus dem Kanal-Tag; die stundengepaarten Größen
    (Direktverbrauch, Überschuss, Defizit), der WP-Strom und die Zahl der Stunden aus den Stundenzeilen."""
    return dataclasses.replace(
        kanal, direktverbrauch_kwh=stunden.direktverbrauch_kwh, ueberschuss_kwh=stunden.ueberschuss_kwh,
        defizit_kwh=stunden.defizit_kwh, wp_strom_kwh=stunden.wp_strom_kwh, stunden=stunden.stunden,
        # E4d: mit dem WP-Strom seine Marke „gemessen" (eine gemessene 0 ist erfasst, Bauplan §8a).
        wp_erfasst=getattr(stunden, "wp_erfasst", False),
    )


# ── Kalendermonat je Sensor (B-2) ───────────────────────────────────────────


async def _bilanz_sensoren(stamm: _Stamm, aktiv, stichtag: date, cache: dict) -> dict[str, str]:
    """``{HA-Entity: Kanal-Schlüssel}`` der Bilanz-Zähler (HA-Auswahl) bei der Menge ``aktiv`` (Prädikat je
    Investition) — je Menge einmal gebildet. Der Stichtag geht nur in die Wallbox-Regel (nicht Teil der Gruppe)."""
    from backend.services.snapshot.lts_aggregator import _lts_eintraege

    menge = frozenset(i.id for i in stamm.invs if aktiv(i))
    if menge not in cache:
        invs_by_id = {str(i.id): i for i in stamm.invs if i.id in menge}
        cache[menge] = {e.schluessel: e.sensor_key
                        for e in bilanz_eintraege(_lts_eintraege(stamm.anlage, invs_by_id, stichtag))}
    return cache[menge]


async def kanal_kalendermonate(
    db: AsyncSession, anlage_id: int, monate_liste: Sequence[MonatsSchluessel], *, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, dict[str, Any]]:
    """B-2: je Kalendermonat, den die Spiegel ALLER Bilanz-Sensoren DIESES Monats voll decken, ``{HA-Entity:
    SensorMonatswert}`` aus dem Kanal-Δ — ohne Deckel, ohne Rücksprung-Verwurf. Monate ohne volle Deckung fehlen
    (dort bleibt der HA-Leser). Die Sensormenge je Monat folgt den Filtern aktiv · Anschaffung · Stilllegung des
    Monats (``ist_aktiv_im_monat``, wie die Monats-Fakten, P10) — ein Gerät, das es im Monat nicht gab, verlangt keinen
    Kanal, eines, das es gab, schon (Nachmessung E4a-2, Punkt 5). EINE Anweisung für alle Monate (die Monatsränder
    als Grenzen)."""
    from backend.services.ha_statistics_service import SensorMonatswert

    if not monate_liste:
        return {}
    jetzt = _jetzt(jetzt)
    se = soll_ende(jetzt)
    fenster = {m: kalendermonatsfenster(*m) for m in set(monate_liste)}
    fenster = {m: f for m, f in fenster.items() if f[0] < se}
    if not fenster:
        return {}
    stamm = await _stamm(db, anlage_id)
    cache: dict = {}
    sensoren_je = {m: await _bilanz_sensoren(stamm, lambda i, m=m: i.ist_aktiv_im_monat(*m), _letzter_tag(*m), cache)
                   for m in fenster}
    alle = {k for s in sensoren_je.values() for k in s.values()}
    if not alle:
        return {}
    kanaele = await kanaele_laden(db, anlage_id, alle)
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    if not mengen:
        return {}
    grenzen = sorted({g for f in fenster.values() for g in f})
    pos = {g: j for j, g in enumerate(grenzen)}
    je = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt)
    out: dict[MonatsSchluessel, dict[str, Any]] = {}
    for m, (von, bis) in fenster.items():
        sensoren = sensoren_je[m]
        if not sensoren or pos[bis] != pos[von] + 1:
            continue
        z = {k: lst[pos[von]] for k, lst in je.items()}
        if not all(z.get(k) is not None and z[k].voll for k in sensoren.values()):
            continue
        out[m] = {
            sid: SensorMonatswert(
                sensor_id=sid, start_wert=round(z[key].wert_von, 3), end_wert=round(z[key].wert_bis, 3),
                differenz=round(z[key].delta, 2), verworfen_kwh=0.0, nachtrag_kwh=0.0,
                intervalle=max(1, round((z[key].gedeckt_bis - z[key].gedeckt_von) / _STUNDE)),
            )
            for sid, key in sensoren.items()
        }
    return out


async def monatswerte_mit_kanaelen(
    db: AsyncSession, anlage_id: int, antworten: Sequence, *, monate: Optional[Sequence[MonatsSchluessel]] = None,
    jetzt: Optional[int] = None,
) -> list:
    """``MonatswertResponse`` je Monat (wie ``get_monatswerte``/``get_alle_monatswerte``) mit dem Kanal-Δ der
    Bilanz-Sensoren, wo ``kanal_kalendermonate`` den Monat nennt; Nicht-Bilanz-Sensoren und alle übrigen Monate
    bleiben, wie der HA-Leser sie liefert. ``monate``: der Monat je Antwort (sonst ``antwort.jahr/monat``).
    Rückgabe in derselben Reihenfolge."""
    antworten = list(antworten)
    if monate is None:
        monate = [(getattr(a, "jahr", None), getattr(a, "monat", None)) for a in antworten]
    monate = list(monate)
    ersatz = await kanal_kalendermonate(db, anlage_id, [m for m in monate if None not in m], jetzt=jetzt)
    out = []
    for a, m in zip(antworten, monate):
        e = ersatz.get(m)
        out.append(a if not e else a.model_copy(update={"sensoren": [e.get(w.sensor_id, w) for w in a.sensoren]}))
    return out


__all__ = [
    "FASSUNG_WEG2", "KanalZeitraum", "als_kanaltag", "als_monatssumme", "bilanz_ziele", "ist_bilanz_schluessel",
    "kanal_kalendermonate", "kanal_monate", "kanal_tage", "lade_monats_summen", "mische_bilanz", "mische_komponenten", "mische_verworfen",
    "monate_bilanz", "monatswerte_mit_kanaelen", "tage_bilanz", "waehle_und_komponiere",
]
