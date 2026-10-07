"""Leser der E-Mob- und der Sonstiges-Gruppe aus Kanälen (HA-Bauform E4c, Bauplan §6 U5/U6, §3b; Auftrag Punkt 1, 2, 4).

**Zwei Gruppen, je Zeitraum EINE Quellenwahl, getrennt von der Bilanz-Gruppe** (eine Gruppe kann decken, die andere
nicht; Auftrag Punkt 4). Je Gruppe gilt dieselbe Regel wie in der Bilanz-Gruppe (§3b, B-4): ``kanal`` nur, wenn jeder
benötigte Kanal den Zeitraum voll deckt — in einer Ersatzgruppe (Entweder-oder, W2-R4) genügt einer, und der ERSTE mit
voller Deckung trägt; sonst ``bestand`` (der heutige Leser, Lesart 1 — im Monat ohne Abschluss: nichts).

* **E-Mob-Gruppe** — je aktivem Gerät (Wallbox, E-Auto, auch dienstlich) jedes Energiefeld mit Zähler
  (``KUMULATIVE_ZAEHLER_FELDER`` des Typs, ``feld_hat_zaehler``: HA-Sensor oder MQTT) — die Felder, die ein Abschluss in
  die Monatszeile schriebe —, dazu der abgeleitete PV-Anteil (``abgeleitet.py``) jedes Geräts, das ihn braucht (auf der
  Wallbox-Achse, ohne gemessene Aufteilung). **Die Regeln wendet NICHT dieser Leser an:** er liefert je Gerät eine Zeile
  ``{feld: Δ}``; Wallbox-Regel, Pool, Rest nach km und Dienstwagen-Filter entscheiden die Monats-Fakten über die eine
  Funktion (``eauto_wirtschaftlichkeit.entscheide_emob_heimladung``) zur Lesezeit — genau wie im abgeschlossenen Monat
  (ADR-002/P10). Die Aufteilung kommt als Anteil ``Σ Δ abgeleitet / Σ Δ Ladung`` der abgeleiteten Geräte; er wird wie
  die Quote der Tagesebene auf die Ladung der Zeilen angewandt (``emob_ladeanteil.reichere_ladezeilen_an``).
* **Sonstiges-Gruppe** — je aktivem Sonstiges-Gerät seine Energiefelder in der Reihenfolge der Kategorie
  (``sonstiges_feld_reihenfolge``) als EINE Ersatzgruppe (wie ``investition_beitraege``), OHNE die Felder der Erzeugung
  hinter dem Zähler (``_categorize_counter`` → ``erzeugung_sonstiges``) — die gehören zur Bilanz-Gruppe und kommen aus
  deren Komposition (``bilanz_leser.als_monatssumme`` → ``sonstige_erzeuger_je_inv``).

Fenster: Monat = ``fenster.monatsfenster`` (die Grenze der Monats-Fakten, wie die Bilanz-Gruppe), Kalendermonat =
``fenster.kalendermonatsfenster`` (Cockpit → Monat). Aktiv-Filter je Zeitraum (``ist_aktiv_im_monat``, P10).

Schwesterdateien: ``abgeleitet.py``, ``bilanz_leser.py``, ``lesen.py``, ``quellenwahl.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_SUM
from backend.services.kanal.abgeleitet import EMOB_TYPEN, abgeleitet_key, lade_auswahl, verfuegbarkeit
from backend.services.kanal.fenster import kalendermonatsfenster, monate, monatsgrenzen
from backend.services.kanal.lesen import GRUND_KEIN_KANAL, Zeitraum, kanaele_laden, reihe_stapel, soll_ende
from backend.services.kanal.quellenwahl import GRUND_KEINE_EINGAENGE, QUELLE_BESTAND, QUELLE_KANAL, Quellenwahl

MonatsSchluessel = tuple[int, int]

#: Herkunft der Zeilen, die die Monats-Fakten aus einer Gruppe dieses Lesers falten (``source_provenance`` der Zeile):
#: keine gespeicherte, keine alte — „Heim: gesamt" gilt (``field_definitions.ist_heim_gesamt``, Regel 8).
HERKUNFT_KANAL = "kanal"


# ── Ergebnisformen ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GruppeZeitraum:
    """Eine Gruppe in einem Zeitraum: die Wahl und bei ``kanal`` die Zeilen je Gerät."""

    wahl: Quellenwahl
    #: inv_id → ``{feld: Δ}`` (ungerundet) — nur bei Wahl ``kanal``.
    zeilen: dict[int, dict[str, float]] = field(default_factory=dict)
    #: E-Mob: Σ Δ abgeleitet (PV-Teil) und Σ Δ Ladung der Geräte, die die Ableitung brauchen.
    abgeleitet_pv_kwh: float = 0.0
    abgeleitet_ladung_kwh: float = 0.0

    @property
    def kanal(self) -> bool:
        return self.wahl.quelle == QUELLE_KANAL

    @property
    def quote(self) -> Optional[float]:
        """Der PV-Anteil der Heimladung im Zeitraum (0…1) — ``None`` ohne abzuleitende Ladung („keine Aussage")."""
        if not self.kanal or self.abgeleitet_ladung_kwh <= 0:
            return None
        return max(0.0, min(1.0, self.abgeleitet_pv_kwh / self.abgeleitet_ladung_kwh))


@dataclass(frozen=True)
class GeraeteZeitraum:
    emob: GruppeZeitraum
    sonstiges: GruppeZeitraum


def herkunft_der_zeile(zeile: dict) -> dict:
    """``source_provenance`` einer Kanal-Zeile in der Form der persistenten Schreibwege (``verbrauch_daten.<feld>``)."""
    return {f"verbrauch_daten.{f}": {"source": HERKUNFT_KANAL} for f in zeile}


# ── Bedarf je Zeitraum ──────────────────────────────────────────────────────


@dataclass
class _Bedarf:
    #: inv_id → Felder, die ALLE decken müssen.
    direkt: dict[int, list[str]] = field(default_factory=dict)
    #: inv_id → Ersatzgruppen (geordnet; einer je Gruppe muss decken, der erste deckende trägt).
    ersatz: dict[int, list[list[str]]] = field(default_factory=dict)
    #: inv_id → Ladezähler der Wallbox-Achse (Basis des Anteils) für die Geräte mit abgeleitetem Kanal.
    abgeleitet: dict[int, tuple[str, ...]] = field(default_factory=dict)

    def keys(self) -> set[str]:
        out = {f"inv:{i}:{f}" for i, fs in self.direkt.items() for f in fs}
        out |= {f"inv:{i}:{f}" for i, gs in self.ersatz.items() for g in gs for f in g}
        out |= {abgeleitet_key(i) for i in self.abgeleitet}
        out |= {k for ks in self.abgeleitet.values() for k in ks}
        return out

    @property
    def leer(self) -> bool:
        return not (self.direkt or self.ersatz)


@dataclass
class _Stamm:
    anlage: Any
    invs: list
    hat_feld: Any
    _auswahl: dict = field(default_factory=dict)

    async def auswahl(self, db, tag: date):
        if tag not in self._auswahl:
            self._auswahl[tag] = await lade_auswahl(db, self.anlage, self.invs, tag, self.hat_feld)
        return self._auswahl[tag]


async def _stamm(db: AsyncSession, anlage_id: int) -> _Stamm:
    """Stammdaten samt Verfügbarkeit; im Lade-Kontext einer Anfrage einmal (samt Ladeauswahl je Tag)."""
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.services.kanal.lade_kontext import gemerkt

    async def _laden() -> _Stamm:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all())
        return _Stamm(anlage, invs, await verfuegbarkeit(db, anlage))

    return await gemerkt(db, ("geraete_stamm", anlage_id), _laden)


def _emob_felder(inv, hat_feld) -> list[str]:
    from backend.services.snapshot.keys import KUMULATIVE_ZAEHLER_FELDER

    return [f for f in KUMULATIVE_ZAEHLER_FELDER.get(inv.typ, ()) if hat_feld(inv, f)]


def _sonstiges_gruppe(inv, hat_feld) -> list[str]:
    from backend.core.field_definitions import SONSTIGES_KATEGORIE_UNGEPFLEGT, sonstiges_feld_reihenfolge
    from backend.services.snapshot.keys import _categorize_counter

    params = inv.parameter if isinstance(getattr(inv, "parameter", None), dict) else {}
    kategorie = params.get("kategorie", SONSTIGES_KATEGORIE_UNGEPFLEGT)
    return [f for f in sonstiges_feld_reihenfolge(kategorie)
            if hat_feld(inv, f) and _categorize_counter(f, "sonstiges", params) != "erzeugung_sonstiges"]


async def _bedarf(db, stamm: _Stamm, aktiv, stichtag: date) -> tuple[_Bedarf, _Bedarf]:
    emob, sonst = _Bedarf(), _Bedarf()
    for inv in stamm.invs:
        if not aktiv(inv):
            continue
        if inv.typ in EMOB_TYPEN:
            felder = _emob_felder(inv, stamm.hat_feld)
            if felder:
                emob.direkt[inv.id] = felder
        elif inv.typ == "sonstiges":
            gruppe = _sonstiges_gruppe(inv, stamm.hat_feld)
            if gruppe:
                sonst.ersatz[inv.id] = [gruppe]
    if emob.direkt:
        a = await stamm.auswahl(db, stichtag)
        emob.abgeleitet = {i: a.ladung[i] for i in a.abzuleiten if i in emob.direkt}
    return emob, sonst


# ── Wahl je Gruppe (rein) ───────────────────────────────────────────────────


def _voll(z: Optional[Zeitraum]) -> bool:
    return z is not None and z.voll and z.delta is not None


def waehle_gruppe(bedarf: _Bedarf, ergebnisse: dict[str, Zeitraum]) -> GruppeZeitraum:
    """Die Wahl einer Gruppe in EINEM Zeitraum und bei ``kanal`` die Zeilen. Reine Funktion."""
    if bedarf.leer:
        return GruppeZeitraum(Quellenwahl(QUELLE_BESTAND, {"": GRUND_KEINE_EINGAENGE}, {}))
    gruende: dict[str, str] = {}

    def _grund(key: str) -> None:
        z = ergebnisse.get(key)
        gruende[key] = GRUND_KEIN_KANAL if z is None else (z.grund or "nicht_voll")

    zeilen: dict[int, dict[str, float]] = {}
    for inv_id, felder in bedarf.direkt.items():
        for f in felder:
            key = f"inv:{inv_id}:{f}"
            if _voll(ergebnisse.get(key)):
                zeilen.setdefault(inv_id, {})[f] = ergebnisse[key].delta
            else:
                _grund(key)
    for inv_id, gruppen in bedarf.ersatz.items():
        for gruppe in gruppen:
            gewaehlt = next((f for f in gruppe if _voll(ergebnisse.get(f"inv:{inv_id}:{f}"))), None)
            if gewaehlt is None:
                _grund(f"inv:{inv_id}:{gruppe[0]}")
            else:
                zeilen.setdefault(inv_id, {})[gewaehlt] = ergebnisse[f"inv:{inv_id}:{gewaehlt}"].delta
    pv = ladung = 0.0
    for inv_id, ladekeys in bedarf.abgeleitet.items():
        ak = abgeleitet_key(inv_id)
        if not _voll(ergebnisse.get(ak)):
            _grund(ak)
            continue
        if not all(_voll(ergebnisse.get(k)) for k in ladekeys):
            for k in ladekeys:
                if not _voll(ergebnisse.get(k)):
                    _grund(k)
            continue
        pv += ergebnisse[ak].delta
        ladung += sum(ergebnisse[k].delta for k in ladekeys)
    vorhanden = {k: ergebnisse[k] for k in bedarf.keys() if k in ergebnisse}
    if gruende:
        return GruppeZeitraum(Quellenwahl(QUELLE_BESTAND, gruende, vorhanden))
    return GruppeZeitraum(Quellenwahl(QUELLE_KANAL, {}, vorhanden), zeilen, abgeleitet_pv_kwh=pv,
                          abgeleitet_ladung_kwh=ladung)


# ── Zeiträume ───────────────────────────────────────────────────────────────


def uhr() -> int:
    """Die Uhr des Lesers (Unix-Sekunden) — EINE Stelle (die Matrizen stellen sie wie ``bilanz_leser.uhr``)."""
    from backend.services.kanal import bilanz_leser

    return bilanz_leser.uhr()


def _letzter_tag(jahr: int, monat: int) -> date:
    return (date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)) - timedelta(days=1)


async def _je_zeitraum(
    db: AsyncSession, stamm: _Stamm, fenster: dict[MonatsSchluessel, tuple[int, int]], jetzt: int,
) -> dict[MonatsSchluessel, GeraeteZeitraum]:
    """Je Monat (mit seinem Fenster) die Wahl beider Gruppen — EINE Lese-Anweisung für alle Monate (die Ränder). Im
    Lade-Kontext einer Anfrage einmal je Fenstersatz (HA-Bauform E4f)."""
    from backend.services.kanal.lade_kontext import gemerkt

    if not fenster:
        return {}
    schluessel = ("geraete_je_zeitraum", stamm.anlage.id, tuple(sorted(fenster.items())), jetzt)
    return dict(await gemerkt(db, schluessel, lambda: _je_zeitraum_rechnen(db, stamm, fenster, jetzt)))


async def _je_zeitraum_rechnen(
    db: AsyncSession, stamm: _Stamm, fenster: dict[MonatsSchluessel, tuple[int, int]], jetzt: int,
) -> dict[MonatsSchluessel, GeraeteZeitraum]:
    bedarf = {m: await _bedarf(db, stamm, lambda i, m=m: i.ist_aktiv_im_monat(*m), _letzter_tag(*m))
              for m in fenster}
    keys = {k for e, s in bedarf.values() for k in e.keys() | s.keys()}
    if not keys:
        return {}
    kanaele = await kanaele_laden(db, stamm.anlage.id, keys)
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    grenzen = sorted({g for f in fenster.values() for g in f})
    pos = {g: j for j, g in enumerate(grenzen)}
    je = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt) if mengen and len(grenzen) >= 2 else {}
    out: dict[MonatsSchluessel, GeraeteZeitraum] = {}
    for m, (von, bis) in fenster.items():
        e_bedarf, s_bedarf = bedarf[m]
        if e_bedarf.leer and s_bedarf.leer:
            continue
        if pos[bis] != pos[von] + 1:          # das Fenster ist kein einzelnes Intervall der Grenzen
            continue
        ergebnisse = {k: lst[pos[von]] for k, lst in je.items()}
        out[m] = GeraeteZeitraum(waehle_gruppe(e_bedarf, ergebnisse), waehle_gruppe(s_bedarf, ergebnisse))
    return out


async def geraete_monate(
    db: AsyncSession, anlage_id: int, *, von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, GeraeteZeitraum]:
    """Je Monat (``fenster.monatsfenster``, die Grenze der Monats-Fakten) mit fälliger Stunde die Wahl beider Gruppen.
    Offenes ``von``: ab dem ersten Kanal-Stand der Anlage; offenes ``bis``: bis zum laufenden Monat."""
    from backend.services.kanal.bilanz_leser import _erster_kanal_monat

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
    stamm = await _stamm(db, anlage_id)
    return await _je_zeitraum(db, stamm, fenster, jetzt)


async def geraete_kalendermonate(
    db: AsyncSession, anlage_id: int, monate_liste: Sequence[MonatsSchluessel], *, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, GeraeteZeitraum]:
    """Dasselbe über den Kalendermonat (``fenster.kalendermonatsfenster``) — der Zeitraum von Cockpit → Monat."""
    jetzt = uhr() if jetzt is None else int(jetzt)
    se = soll_ende(jetzt)
    fenster = {m: kalendermonatsfenster(*m) for m in set(monate_liste)}
    fenster = {m: f for m, f in fenster.items() if f[0] < se}
    if not fenster:
        return {}
    stamm = await _stamm(db, anlage_id)
    return await _je_zeitraum(db, stamm, fenster, jetzt)


async def geraete_sensorwerte_kalendermonate(
    db: AsyncSession, anlage_id: int, monate_liste: Sequence[MonatsSchluessel], *, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, dict[str, Any]]:
    """HA-Bauform E4f (Auftrag Punkt 2, E4c H-5): die Kalendermonats-Schreibwege für E-Mob und Sonstiges.

    Je Kalendermonat und Gruppe (E-Mob · Sonstiges) DIESELBE Quellenwahl wie ``geraete_kalendermonate`` (Cockpit →
    Monat, E4c): deckt eine Gruppe den Kalendermonat aus den Kanälen — die E-Mob-Gruppe nur samt dem abgeleiteten
    PV-Anteil der Geräte, die ihn brauchen —, wird für jedes Feld ihrer Zeilen (E-Mob: jedes Zählerfeld; Sonstiges: je
    Ersatzgruppe das gewählte, W2-R4) der HA-Sensor des Feldes (``sensor_mapping``, Strategie ``sensor``) als
    ``{HA-Entity: SensorMonatswert}`` aus dem Kanal-Δ genannt — ohne Deckel, ohne Rücksprung-Verwurf, wie die
    Bilanz-Gruppe (``bilanz_leser.kanal_kalendermonate``, B-2). Eine Gruppe ohne volle Deckung fehlt (dort bleibt der
    HA-Leser, Lesart 1).

    ⚠ Der abgeleitete PV-Anteil selbst ist kein Sensor und wird hier NICHT als Wert genannt: die Monats-Fakten wenden
    ihn zur Lesezeit auch auf gespeicherte Monate an (E4c, N-631 „eine Aufteilung mit und ohne Abschluss").
    """
    from backend.services.ha_statistics_service import SensorMonatswert

    if not monate_liste:
        return {}
    je = await geraete_kalendermonate(db, anlage_id, monate_liste, jetzt=jetzt)
    if not je:
        return {}
    from backend.models.anlage import Anlage

    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    inv_map = ((anlage.sensor_mapping or {}).get("investitionen") or {})

    def _sensor(inv_id: int, feld: str) -> Optional[str]:
        cfg = (((inv_map.get(str(inv_id)) or {}).get("felder") or {}).get(feld)) or {}
        return cfg.get("sensor_id") if cfg.get("strategie") == "sensor" else None

    out: dict[MonatsSchluessel, dict[str, Any]] = {}
    for m, g in je.items():
        werte: dict[str, Any] = {}
        for gruppe in (g.emob, g.sonstiges):
            if not gruppe.kanal:
                continue
            for inv_id, zeile in gruppe.zeilen.items():
                for feld in zeile:
                    sid = _sensor(inv_id, feld)
                    z = gruppe.wahl.ergebnisse.get(f"inv:{inv_id}:{feld}")
                    if sid is None or z is None or z.delta is None:
                        continue
                    werte[sid] = SensorMonatswert(
                        sensor_id=sid, start_wert=round(z.wert_von, 3), end_wert=round(z.wert_bis, 3),
                        differenz=round(z.delta, 2), verworfen_kwh=0.0, nachtrag_kwh=0.0,
                        intervalle=max(1, round((z.gedeckt_bis - z.gedeckt_von) / 3600)),
                    )
        if werte:
            out[m] = werte
    return out


async def emob_quoten(
    db: AsyncSession, anlage_id: int, *, von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
) -> dict[MonatsSchluessel, Optional[float]]:
    """Je Monat, dessen E-Mob-Gruppe die Kanäle voll decken, der PV-Anteil der Heimladung (``None`` = keine Aussage).
    Monate ohne Deckung fehlen — dort gilt die Quote der Tagesebene (Lesart 1)."""
    return {m: g.emob.quote for m, g in (await geraete_monate(db, anlage_id, von=von, bis=bis)).items()
            if g.emob.kanal}


__all__ = [
    "GeraeteZeitraum", "GruppeZeitraum", "HERKUNFT_KANAL", "emob_quoten", "geraete_kalendermonate", "geraete_monate",
    "geraete_sensorwerte_kalendermonate",
    "herkunft_der_zeile", "uhr", "waehle_gruppe",
]
