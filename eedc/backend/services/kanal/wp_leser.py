"""Leser der Wärmepumpen-Gruppe aus Kanälen (HA-Bauform E4d, Bauplan §6 U4, §3b; Auftrag Punkt 2).

**Je Zeitraum EINE Quellenwahl für die WP-Gruppe, getrennt von der Bilanz-, E-Mob- und Sonstiges-Gruppe** (dieselbe
Regel wie ``geraete_leser.waehle_gruppe``): ``kanal`` nur, wenn JEDER benötigte Kanal den Zeitraum voll deckt; sonst
``bestand`` — der heutige Leser, Lesart 1 (Bauplan §3b; im Monat ohne Abschluss: der Modus-Split der Tagesebene,
``energie_profil/modus_split_monat.py``, und sonst nichts).

**Die WP-Gruppe** = je aktiver Wärmepumpe

* jedes Energiefeld mit Zähler (``KUMULATIVE_ZAEHLER_FELDER['waermepumpe']`` und ihre Innengerät-Felder,
  ``snapshot/keys.feld_hat_zaehler``: HA-Sensor oder MQTT) — Strom (Gesamt · Heizen · Warmwasser), Wärme (Gesamt ·
  Heizwärme · Warmwasser-Wärme), Betriebsart-Strom und -Nutzenergie (Kälte). Die Felder, die ein Abschluss in die
  Monatszeile schriebe. ⚠ **Die Wärme wird nicht nach dem Etikett geteilt** (Bauplan §8a, W1): ein Wärmezähler ohne
  Funktionstrennung bleibt ``waerme_kwh``;
* für ein Gerät mit Betriebsart-Mitschrift und ohne gemessene Betriebsart-Zähler der abgeleitete Strom je Betriebsart
  (``modus_strom.py``): ``modus_strom_heizen_kwh`` · ``modus_strom_warmwasser_kwh`` · ``modus_strom_kuehlen_kwh`` und
  ``modus_abdeckung_h`` — genau die Felder, die der Monatsabschluss für die Aufteilung speichert (``MODUS_SPLIT_FELDER``).
  Lüften/Entfeuchten führt der Kanal, gelesen werden sie nicht (§5.4, D11).

Ergebnis je Gerät eine Zeile ``{feld: Δ}`` in der Form einer Monatszeile — **keine Regel im Leser**: K3, D1, die
Betriebsart-Weiche, die Teilmengen-Invariante und die abgeleitete Heizwärme entscheiden die Monats-Fakten bzw. die
Faltung zur Lesezeit (P10), genau wie im abgeschlossenen Monat.

Fenster: Monat = ``fenster.monatsfenster`` (die Grenze der Monats-Fakten), Kalendermonat =
``fenster.kalendermonatsfenster`` (Cockpit → Monat). Aktiv-Filter je Zeitraum (``ist_aktiv_im_monat``, P10).

Schwesterdateien: ``modus_strom.py`` (der abgeleitete Kanal), ``geraete_leser.py`` (Vorbild, E-Mob und Sonstiges),
``bilanz_leser.py``, ``lesen.py``, ``quellenwahl.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD, MODUS_STROM_FELD
from backend.models.kanal import ART_SUM
from backend.services.kanal.fenster import kalendermonatsfenster, monate, monatsgrenzen
from backend.services.kanal.lesen import GRUND_KEIN_KANAL, Zeitraum, kanaele_laden, reihe_stapel, soll_ende
from backend.services.kanal.quellenwahl import GRUND_KEINE_EINGAENGE, QUELLE_BESTAND, QUELLE_KANAL, Quellenwahl

MonatsSchluessel = tuple[int, int]

#: Typ der Gruppe.
WP_TYP = "waermepumpe"
#: Die abgeleiteten Felder, die eine Zeile trägt (Feldname der Monatszeile → Modus des Kanals).
ABGELEITETE_FELDER: dict[str, str] = {feld: modus for modus, feld in MODUS_STROM_FELD.items()}


@dataclass(frozen=True)
class WpZeitraum:
    """Die WP-Gruppe in einem Zeitraum: die Wahl und bei ``kanal`` die Zeilen je Gerät."""

    wahl: Quellenwahl
    #: inv_id → ``{feld: Δ}`` (ungerundet) — nur bei Wahl ``kanal``.
    zeilen: dict[int, dict[str, float]] = field(default_factory=dict)
    #: Geräte, deren Zeile den abgeleiteten Strom je Betriebsart trägt.
    abgeleitet: frozenset[int] = frozenset()

    @property
    def kanal(self) -> bool:
        return self.wahl.quelle == QUELLE_KANAL


@dataclass
class _Bedarf:
    #: inv_id → Felder mit Zähler (alle müssen decken).
    direkt: dict[int, list[str]] = field(default_factory=dict)
    #: Geräte mit abgeleitetem Strom je Betriebsart.
    abgeleitet: set[int] = field(default_factory=set)

    def keys(self) -> set[str]:
        from backend.services.kanal.modus_strom import abdeckung_key, modus_strom_key

        out = {f"inv:{i}:{f}" for i, fs in self.direkt.items() for f in fs}
        for i in self.abgeleitet:
            out |= {modus_strom_key(i, m) for m in ABGELEITETE_FELDER.values()} | {abdeckung_key(i)}
        return out

    @property
    def leer(self) -> bool:
        return not (self.direkt or self.abgeleitet)


def wp_felder(inv, inv_map: dict, hat_feld) -> list[str]:
    """Die Energiefelder einer Wärmepumpe mit Zähler — Registry-Felder und ihre Innengerät-Varianten."""
    from backend.core.field_definitions import basis_feld_key
    from backend.services.snapshot.keys import KUMULATIVE_ZAEHLER_FELDER

    basis = KUMULATIVE_ZAEHLER_FELDER.get(WP_TYP, ())
    zugeordnet = [f for f in ((inv_map.get(str(inv.id)) or {}).get("felder") or {})
                  if basis_feld_key(f) in basis and f not in basis]
    return [f for f in (*basis, *sorted(zugeordnet)) if hat_feld(inv, f)]


async def _bedarf(db: AsyncSession, stamm, aktiv) -> _Bedarf:
    from backend.services.kanal.modus_strom import abzuleitende_geraete

    b = _Bedarf()
    inv_map = ((stamm.anlage.sensor_mapping or {}).get("investitionen") or {})
    wps = [i for i in stamm.invs if i.typ == WP_TYP and aktiv(i)]
    if not wps:
        return b
    for inv in wps:
        felder = wp_felder(inv, inv_map, stamm.hat_feld)
        if felder:
            b.direkt[inv.id] = felder
    if stamm.abzuleiten is None:
        stamm.abzuleiten = set(await abzuleitende_geraete(db, stamm.anlage, stamm.invs, stamm.hat_feld))
    b.abgeleitet = {i.id for i in wps if i.id in stamm.abzuleiten}
    return b


def _voll(z: Optional[Zeitraum]) -> bool:
    return z is not None and z.voll and z.delta is not None


def waehle_wp(bedarf: _Bedarf, ergebnisse: dict[str, Zeitraum]) -> WpZeitraum:
    """Die Wahl der WP-Gruppe in EINEM Zeitraum und bei ``kanal`` die Zeilen. Reine Funktion."""
    from backend.services.kanal.modus_strom import abdeckung_key, modus_strom_key

    if bedarf.leer:
        return WpZeitraum(Quellenwahl(QUELLE_BESTAND, {"": GRUND_KEINE_EINGAENGE}, {}))
    gruende: dict[str, str] = {}
    zeilen: dict[int, dict[str, float]] = {}

    def _nimm(inv_id: int, feld: str, key: str) -> None:
        z = ergebnisse.get(key)
        if _voll(z):
            zeilen.setdefault(inv_id, {})[feld] = z.delta
        else:
            gruende[key] = GRUND_KEIN_KANAL if z is None else (z.grund or "nicht_voll")

    for inv_id, felder in bedarf.direkt.items():
        for f in felder:
            _nimm(inv_id, f, f"inv:{inv_id}:{f}")
    for inv_id in bedarf.abgeleitet:
        for feld, modus in ABGELEITETE_FELDER.items():
            _nimm(inv_id, feld, modus_strom_key(inv_id, modus))
        _nimm(inv_id, MODUS_ABDECKUNG_FELD, abdeckung_key(inv_id))
    vorhanden = {k: ergebnisse[k] for k in bedarf.keys() if k in ergebnisse}
    if gruende:
        return WpZeitraum(Quellenwahl(QUELLE_BESTAND, gruende, vorhanden))
    return WpZeitraum(Quellenwahl(QUELLE_KANAL, {}, vorhanden), zeilen, frozenset(bedarf.abgeleitet))


@dataclass
class _WpStamm:
    anlage: object
    invs: list
    hat_feld: object
    abzuleiten: Optional[set] = None


async def _stamm(db: AsyncSession, anlage_id: int) -> _WpStamm:
    from backend.services.kanal.geraete_leser import _stamm as _geraete_stamm

    s = await _geraete_stamm(db, anlage_id)
    return _WpStamm(s.anlage, s.invs, s.hat_feld)


async def _je_zeitraum(
    db: AsyncSession, stamm: _WpStamm, fenster: dict[MonatsSchluessel, tuple[int, int]], jetzt: int,
) -> dict[MonatsSchluessel, WpZeitraum]:
    """Je Monat (mit seinem Fenster) die Wahl der WP-Gruppe — EINE Lese-Anweisung für alle Monate (die Ränder)."""
    if not fenster:
        return {}
    bedarf = {m: await _bedarf(db, stamm, lambda i, m=m: i.ist_aktiv_im_monat(*m)) for m in fenster}
    keys = {k for b in bedarf.values() for k in b.keys()}
    if not keys:
        return {}
    kanaele = await kanaele_laden(db, stamm.anlage.id, keys)
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    grenzen = sorted({g for f in fenster.values() for g in f})
    pos = {g: j for j, g in enumerate(grenzen)}
    je = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt) if mengen and len(grenzen) >= 2 else {}
    out: dict[MonatsSchluessel, WpZeitraum] = {}
    for m, (von, bis) in fenster.items():
        if bedarf[m].leer or pos[bis] != pos[von] + 1:
            continue
        out[m] = waehle_wp(bedarf[m], {k: lst[pos[von]] for k, lst in je.items()})
    return out


def uhr() -> int:
    """Die Uhr des Lesers — EINE Stelle (``bilanz_leser.uhr``; die Matrizen stellen sie)."""
    from backend.services.kanal import bilanz_leser

    return bilanz_leser.uhr()


async def hat_wp_kanaele(db: AsyncSession, anlage_id: int) -> bool:
    """Hat die Anlage überhaupt einen Kanal einer Wärmepumpe? (billiger Vorfilter, ein Index-Schritt)"""
    from sqlalchemy import and_, select

    from backend.models.investition import Investition
    from backend.models.kanal import Kanal

    ids = [str(i) for i in (await db.execute(select(Investition.id).where(and_(
        Investition.anlage_id == anlage_id, Investition.typ == WP_TYP)))).scalars().all()]
    if not ids:
        return False
    from sqlalchemy import or_

    return (await db.execute(select(Kanal.id).where(and_(
        Kanal.anlage_id == anlage_id, or_(*[Kanal.key.like(f"inv:{i}:%") for i in ids]),
    )).limit(1))).scalar() is not None


async def wp_monate(
    db: AsyncSession, anlage_id: int, *, von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, WpZeitraum]:
    """Je Monat (``fenster.monatsfenster``, die Grenze der Monats-Fakten) mit fälliger Stunde die Wahl der WP-Gruppe.
    Offenes ``von``: ab dem ersten Kanal-Stand der Anlage; offenes ``bis``: bis zum laufenden Monat."""
    from backend.services.kanal.bilanz_leser import _erster_kanal_monat

    if not await hat_wp_kanaele(db, anlage_id):
        return {}
    jetzt = uhr() if jetzt is None else int(jetzt)
    if von is None:
        von = await _erster_kanal_monat(db, anlage_id)
        if von is None:
            return {}
    if bis is None:
        d = datetime.fromtimestamp(jetzt).date()
        bis = (d.year, d.month)
    liste = monate(von, bis)
    if not liste:
        return {}
    grenzen = monatsgrenzen(von, bis)
    se = soll_ende(jetzt)
    fenster = {m: (grenzen[i], grenzen[i + 1]) for i, m in enumerate(liste) if grenzen[i] < se}
    return await _je_zeitraum(db, await _stamm(db, anlage_id), fenster, jetzt)


async def wp_kalendermonate(
    db: AsyncSession, anlage_id: int, monate_liste: Sequence[MonatsSchluessel], *, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, WpZeitraum]:
    """Dasselbe über den Kalendermonat (``fenster.kalendermonatsfenster``) — der Zeitraum von Cockpit → Monat."""
    if not await hat_wp_kanaele(db, anlage_id):
        return {}
    jetzt = uhr() if jetzt is None else int(jetzt)
    se = soll_ende(jetzt)
    fenster = {m: kalendermonatsfenster(*m) for m in set(monate_liste)}
    fenster = {m: f for m, f in fenster.items() if f[0] < se}
    if not fenster:
        return {}
    return await _je_zeitraum(db, await _stamm(db, anlage_id), fenster, jetzt)


__all__ = [
    "ABGELEITETE_FELDER", "WpZeitraum", "hat_wp_kanaele", "uhr", "waehle_wp", "wp_felder", "wp_kalendermonate",
    "wp_monate",
]
