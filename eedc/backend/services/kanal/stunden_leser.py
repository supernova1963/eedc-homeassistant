"""Der Kanal-Stundentag — die 24 Stunden eines Kanal-Tags aus den Kanälen (HA-Bauform S3, Etappe E-S3-1; Bauplan §4).

**Stand E-S3-1: gebaut und gegen den Bestand geprüft, von KEINER Sicht gelesen** (Umschalten ist E-S3-2; der Wächter
``test_kanal_lesen_waechter.py`` hält fest, dass außerhalb ``services/kanal/`` niemand die Lese-Schicht importiert).
Gleichheitsprobe ``tests/kanal_stunden_gleichheit.py``, Wächter „Σ Stunden ≡ Tag" ``tests/test_kanal_stunden_summe.py``.

**Je Gruppe dieselbe Quellenwahl wie der Tag (S3-R1)** — kein Tag halb/halb:

* **Bilanz** (Netz, PV/Balkonkraftwerk samt Anlagenzähler, Speicher, Erzeuger hinter dem Zähler): die Wahl der
  Tages-Leser, ``bilanz_leser.tage_bilanz`` (Lückentag wie HA).
* **Geräte** (E-Mob und Sonstiges, je eine Wahl) und **Wärmepumpe**: ihre Tageswahl entsteht hier — dieselbe
  ``_bedarf``-Logik und dieselbe Wahl (``geraete_leser.waehle_gruppe``, ``wp_leser.waehle_wp``) wie der Monat, mit dem
  Tagesfenster und ``ist_aktiv_an(tag)`` statt ``ist_aktiv_im_monat`` (Bauplan §10a, ⚑ E-S3-0).

Wahl ``bestand`` ⇒ die Gruppe fehlt im Ergebnis (``gruppen``); der Aufrufer rechnet sie wie heute aus den Stundenzeilen.

**Stunde = HAs ``change`` im Backward-Raster (S3-R2).** ``lesen.stunden_stapel`` über ``fenster.tagesfenster(D)`` —
EINE Anweisung je Gruppe; Slot ``h`` = ``change`` der Zeile, deren Stand den Zähler ``h`` setzt
(``slot_konvention.lts_boundary_index``, dieselbe Abbildung wie ``get_hourly_slots_for_day``: Herbst-Doppelslot trägt
beide Zeilen, Frühjahr ein leerer Slot). Eine Stunde ohne Zeile ist **keine 0**: der Slot bleibt ``None``, die nächste
belegte Stunde trägt den Zuwachs und ihre ``spanne > 3600``. **HA-Kanäle wörtlich (S3-R9):** kein Deckel, keine
Reset-Regel, keine Lückenfüllung — auch nicht für die eigene Summe eines MQTT-Kanals beim Lesen (sie hat ihre Regeln
beim Schreiben).

**Komposition je Stunde (S3-R3)** — die Bilanz-Gruppe über DIESELBE Layer-Funktion wie der Tag,
``komponiere_bilanz_zeitraum`` (W2), je Slot mit den Δ der Stunde. Die Wahl von ``bilanz_leser.waehle_und_komponiere``
steht in der Stunde fest (jeder belegte Kanal ist voll gedeckt); sie wird je Belegung einmal bestimmt (``_vorlage``,
E-S3-6 Gate B — die Probe ``test_kanal_stunden_vorlage.py`` hält die Gleichheit zu ``waehle_und_komponiere`` fest).
Vorbereitet werden nur die Eingänge:

* Entweder-oder: die Wahl des Tages (``resolve_either_or_eintraege`` mit „Kanal deckt den Tag") gilt für jede Stunde —
  ⚑ so verstanden, weil eine je Stunde neu gewählte Ersatzgruppe in der Lücke des ersten Kanals den zweiten nähme und
  dessen Menge neben dem Lückenbündel des ersten zählte (S3-R1 „kein Tag halb/halb", S3-R4 „Σ Stunden ≡ Tag").
* Ein Kanal ohne Zeile in der Stunde geht in die Stunde nicht ein; ein PV-Gerät, dessen Kanal den Tag trägt, das in der
  Stunde aber keine Zeile hat, ist in der Stunde auch kein Empfänger des Anlagenzähler-Rests (sein Zuwachs steht in der
  Folgestunde) — ⚑ es fällt aus den Trägern der Stunde.

**Σ Stunden ≡ Tag (S3-R4, berichtigt 15.10. nach E-S3-1 H-3):** der Rest des Anlagenzählers je Stunde (für die Geräte
ohne eigenes Δ) wird auf den Rest der Tageskomposition skaliert — ``rest_h × Rest_Tag / Σ_h rest_h`` (``rest_faktor``; ohne
Lücke und ohne Klemmung 1). So zählt die Lückenmenge eines Zählers nicht doppelt (erst als Rest, dann als Bündel), und
jedes Gerät, die PV-Summe, Gesamt- und Eigenverbrauch des Tages sind die Σ ihrer Stunden. ``klemm_stunden`` nennt die
Stunden, in denen W2-R5 einen kWp-Rest auf 0 geklemmt hat (Anlagenzähler-Rest oder Kinder-Rest eines Balkonkraftwerks).

**Abdeckung je Gruppe (S3-R7):** ``gedeckt_von``/``gedeckt_bis`` (die Spanne, über die ALLE Kanäle der Gruppe gemessen
sind) und die größte Spanne. Lade-Kontext: ein Kanal-Stundentag je Anfrage und Tag (``lade_kontext.gemerkt``).

Datenform der Stundenzeile: ``stunden_adapter.py``. Schwesterdateien: ``bilanz_leser.py``, ``geraete_leser.py``,
``wp_leser.py``, ``lesen.py``, ``fenster.py``.
"""

from __future__ import annotations

import dataclasses
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.bilanz_zeitraum import BilanzZeitraum, Eingang, komponiere_bilanz_zeitraum
from backend.core.berechnungen.pv_verteilung import PvTraeger
from backend.core.berechnungen.slot_konvention import lts_boundary_index
from backend.models.kanal import ART_SUM
from backend.services.kanal import bilanz_leser, geraete_leser, wp_leser
from backend.services.kanal.bilanz_adapter import zaehler_eintraege
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.lesen import (
    GRUND_ENDET_VOR_BIS, Stunden, Zeitraum, kanaele_laden, reihe_stapel, soll_ende, stunden_stapel, zeitraum_stapel,
)
from backend.services.kanal.quellenwahl import QUELLE_BESTAND, QUELLE_KANAL, Quellenwahl
from backend.services.snapshot.komponenten_beitraege import resolve_either_or_eintraege
from backend.services.snapshot.tages_tabelle import TabellenEintrag

GRUPPE_BILANZ = "bilanz"
GRUPPE_EMOB = "emob"
GRUPPE_SONSTIGES = "sonstiges"
GRUPPE_WP = "wp"
GRUPPEN = (GRUPPE_BILANZ, GRUPPE_EMOB, GRUPPE_SONSTIGES, GRUPPE_WP)

SLOTS = 24
_STUNDE = 3600
#: Klemm-Erkennung: eine Überschreitung unter dieser Menge ist Gleitkomma-Rauschen der Summen, keine Klemmung.
_KLEMM_TOL = 1e-9


# ── Ergebnisformen ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GruppenStunden:
    """Eine Gruppe mit Wahl ``kanal``: je Kanal-Schlüssel 24 Slots und die Abdeckung der Gruppe."""

    gruppe: str
    wahl: Quellenwahl
    #: Kanal-Schlüssel → je Slot 0…23 der Zuwachs (HAs ``change``) — ``None``: der Slot hat keine Zeile.
    mengen: dict[str, tuple[Optional[float], ...]]
    #: Kanal-Schlüssel → je Slot die Spanne in Sekunden (3600 lückenlos, größer: der Zuwachs trägt fehlende Stunden).
    spannen: dict[str, tuple[Optional[int], ...]]
    #: Die Spanne, über die ALLE Kanäle der Gruppe gemessen sind (S3-R7) — ``None`` ohne Zeile.
    gedeckt_von: Optional[int]
    gedeckt_bis: Optional[int]
    #: Die größte Spanne eines Kanals der Gruppe in Sekunden (innen und über die Ränder).
    groesste_spanne: Optional[int]
    #: Die Zähler der Gruppe, die der Tag trägt (Entweder-oder des Tages), mit Kategorie, Ziel und Vorzeichen.
    eintraege: tuple[TabellenEintrag, ...] = ()


@dataclass(frozen=True)
class BilanzStunden:
    """Die Bilanz-Gruppe je Stunde: die Komposition (W2) je Slot, die Träger und die Klemm-Stunden."""

    #: je Slot die Komposition der Stunde — ``None``: kein Kanal der Gruppe hat in der Stunde eine Zeile.
    kompositionen: tuple[Optional[BilanzZeitraum], ...]
    #: die Komposition des Tages (dieselbe wie ``bilanz_leser.kanal_tage``) — der Maßstab für Σ Stunden.
    tag: BilanzZeitraum
    traeger: tuple[PvTraeger, ...]
    klemm_stunden: tuple[int, ...]
    #: S3-R4: der Faktor der Tagesrest-Skalierung (1 ohne Lücke und ohne Klemmung; ``None``: nicht skalierbar).
    rest_faktor: Optional[float] = 1.0


@dataclass(frozen=True)
class KanalStundentag:
    """Die Stunden eines Tages aus den Kanälen, je Gruppe mit Wahl ``kanal``."""

    datum: date
    von: int
    bis: int
    #: je Gruppe die Tageswahl (auch ``bestand`` — dann fehlt die Gruppe in ``gruppen``).
    wahlen: dict[str, Quellenwahl]
    gruppen: dict[str, GruppenStunden] = field(default_factory=dict)
    bilanz: Optional[BilanzStunden] = None

    @property
    def klemm_stunden(self) -> tuple[int, ...]:
        return self.bilanz.klemm_stunden if self.bilanz is not None else ()


# ── Slots ───────────────────────────────────────────────────────────────────


def slots_der_stunden(datum: date, st: Stunden,
                      slot_je_ts: Optional[dict] = None) -> tuple[tuple[Optional[float], ...], tuple[Optional[int], ...]]:
    """Die Zeilen eines Kanals im Tagesfenster auf die 24 Backward-Slots (``lts_boundary_index``). Fallen zwei Zeilen
    auf einen Slot (Herbst-Umstellung), trägt er beide Zuwächse und beide Spannen; ein Slot ohne Zeile bleibt ``None``.
    ``slot_je_ts``: ein Merkzettel ``start_ts → Slot`` desselben Tages (alle Kanäle einer Gruppe teilen die Stunden)."""
    menge: list[Optional[float]] = [None] * SLOTS
    spanne: list[Optional[int]] = [None] * SLOTS
    merk = {} if slot_je_ts is None else slot_je_ts
    for w in st.werte:
        h = merk.get(w.start_ts)
        if h is None:
            h = merk[w.start_ts] = lts_boundary_index(datetime.fromtimestamp(w.start_ts), datum)
        if not 0 <= h < SLOTS or w.change is None:
            continue
        menge[h] = (menge[h] or 0.0) + w.change
        spanne[h] = (spanne[h] or 0) + int(w.spanne or _STUNDE)
    return tuple(menge), tuple(spanne)


def _abdeckung(stunden: Sequence[Stunden]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    von = [s.gedeckt_von for s in stunden]
    bis = [s.gedeckt_bis for s in stunden]
    spannen = [s.groesste_spanne for s in stunden if s.groesste_spanne is not None]
    gedeckt_von = max(von) if von and None not in von else None
    gedeckt_bis = min(bis) if bis and None not in bis else None
    return gedeckt_von, gedeckt_bis, (max(spannen) if spannen else None)


async def _lies_stunden(db: AsyncSession, anlage_id: int, keys: set[str], datum: date,
                       jetzt: int) -> dict[str, Stunden]:
    """EIN ``stunden_stapel`` über die Mengen-Kanäle ``keys`` im Tagesfenster."""
    von, bis = tagesfenster(datum)
    mengen = [k for k in (await kanaele_laden(db, anlage_id, keys)).values() if k.art == ART_SUM]
    return await stunden_stapel(db, mengen, von, bis, jetzt=jetzt) if mengen else {}


def _gruppe_aus(datum: date, gruppe: str, wahl: Quellenwahl, je: dict, eintraege: Sequence[TabellenEintrag],
                ) -> GruppenStunden:
    """Eine Gruppe aus den Stunden ihrer Kanäle im Tagesfenster (``Stunden`` des Tages oder sein Ausschnitt aus einem
    Bereich — dieselben Zeilen, dieselbe Abdeckung)."""
    merk: dict = {}
    slots = {key: slots_der_stunden(datum, st, merk) for key, st in je.items()}
    gedeckt_von, gedeckt_bis, groesste = _abdeckung(list(je.values()))
    return GruppenStunden(
        gruppe=gruppe, wahl=wahl, mengen={k: m for k, (m, _s) in slots.items()},
        spannen={k: s for k, (_m, s) in slots.items()}, gedeckt_von=gedeckt_von, gedeckt_bis=gedeckt_bis,
        groesste_spanne=groesste, eintraege=tuple(e for e in eintraege if e.schluessel in slots),
    )


# ── Bilanz-Gruppe: Tageswahl, Entweder-oder des Tages, Komposition je Stunde ─


def _traeger_der_stunde(traeger: Sequence[PvTraeger], eintraege_tag: Sequence[TabellenEintrag],
                        belegt: set[str]) -> list[PvTraeger]:
    """Die Träger der Stunde: ohne die PV-Geräte, deren Kanal den Tag trägt, die aber in der Stunde keine Zeile haben
    (ihr Zuwachs steht in der Folgestunde — sie sind in der Stunde weder gemessen noch Empfänger des Rests)."""
    stumm = {e.sensor_key.split(":", 2)[1] for e in eintraege_tag
             if e.kategorie == "pv" and e.sensor_key.startswith("inv:") and e.schluessel not in belegt}
    return [t for t in traeger if str(t.inv_id) not in stumm]


def klemm_der_stunde(k: Optional[BilanzZeitraum], traeger: Sequence[PvTraeger]) -> bool:
    """Hat W2-R5 in dieser Stunde einen kWp-Rest auf 0 geklemmt (S3-R4)? Zwei Stellen klemmen
    (``pv_verteilung.loese_pv_zeitraum_auf``): der Rest des Anlagenzählers für die Geräte ohne eigenes Δ (Module ohne
    Wert, Balkonkraftwerke ohne Δ) und der Kinder-Rest eines Balkonkraftwerks (``bkw_kinder_luecken_kwh``). Gelesen aus
    Eingang und Ergebnis der Komposition, nicht nachgerechnet."""
    if k is None or k.pv is None:
        return False
    eigen = {e.pv_inv_id: e.delta for e in k.mit_wert if e.kategorie == "pv" and e.pv_inv_id is not None}
    # Kinder je Träger: unter den PV-Trägern ist ein Elternteil immer das abtretende Balkonkraftwerk (N-266) — der
    # Wechselrichter als Parent eines Moduls ist kein Träger und fällt hier heraus.
    ids = {t.inv_id for t in traeger}
    kinder: dict[int, list[int]] = {}
    for t in traeger:
        if t.parent_id in ids:
            kinder.setdefault(t.parent_id, []).append(t.inv_id)
    for b, kids in kinder.items():
        luecke = [i for i in kids if i not in eigen]
        if b in eigen and luecke and sum(eigen[i] for i in kids if i in eigen) > eigen[b] + _KLEMM_TOL:
            return True
    az = k.pv.anlagenzaehler_kwh
    if az is None:
        return False
    empfaenger = [t for t in traeger if t.inv_id not in eigen and t.inv_id not in kinder
                  and not (t.parent_id in kinder and t.parent_id in eigen)]
    return bool(empfaenger) and k.pv.geraete_kwh - k.pv.verteilter_rest_kwh > az + _KLEMM_TOL


@dataclass(frozen=True)
class _Vorlage:
    """Was an einer Stunde nur von ihrer Belegung (den Kanälen mit Zeile) abhängt, nicht von den Werten: die Eingänge
    nach dem Entweder-oder in der Reihenfolge von ``waehle_und_komponiere`` (je mit dem Kanal, dessen ``change`` ihr Δ
    ist) und die Träger der Stunde. Einmal je Belegung und Tag (E-S3-6, Gate B)."""

    eingaenge: tuple[tuple[str, Eingang], ...]
    traeger: tuple[PvTraeger, ...]


def _pv_inv_id(e: TabellenEintrag) -> Optional[int]:
    """Das PV-Gerät eines Zählers wie ``bilanz_leser.waehle_und_komponiere`` — ``None`` für den Anlagenzähler."""
    if e.kategorie == "pv" and e.sensor_key != bilanz_leser._AGGREGAT_KEY:
        return int(e.sensor_key.split(":", 2)[1])
    return None


def _vorlage(gs: GruppenStunden, belegt: frozenset, traeger: Sequence[PvTraeger]) -> _Vorlage:
    """Die Vorlage einer Belegung. In einer Stunde ist jeder belegte Kanal voll gedeckt (Δ = ``change``), also wählt
    ``waehle_und_komponiere`` dort immer ``kanal`` und nimmt je Entweder-oder-Gruppe den ersten belegten Zähler —
    genau das, was ``resolve_either_or_eintraege`` mit „hat Daten" hier tut. Die Probe
    ``test_kanal_stunden_vorlage.py`` vergleicht die Komposition je Stunde mit ``waehle_und_komponiere``."""
    eintraege_h = [e for e in gs.eintraege if e.schluessel in belegt]
    gewaehlt = resolve_either_or_eintraege(eintraege_h, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: True)
    return _Vorlage(
        tuple((e.schluessel, Eingang(e.kategorie, e.target_key, e.vorzeichen, None, _pv_inv_id(e))) for e in gewaehlt),
        tuple(_traeger_der_stunde(traeger, gs.eintraege, belegt)),
    )


def _komposition_der_stunde(gs: GruppenStunden, h: int, traeger: Sequence[PvTraeger], dc_grund: Optional[str],
                            vorlagen: dict, az_abzug: float = 0.0) -> tuple[Optional[BilanzZeitraum], list[PvTraeger]]:
    """Die Komposition der Stunde (S3-R3) über DIESELBE Layer-Funktion wie der Tag (``komponiere_bilanz_zeitraum``),
    mit den Eingängen der Belegung (``_vorlage``; ``vorlagen`` merkt sie je Tag). ``az_abzug`` mindert das Δ des
    Anlagenzählers der Stunde — die Tagesrest-Skalierung (S3-R4) als Eingang, nicht als zweite Komposition. Ohne
    belegten Zähler ``None`` (wie ``waehle_und_komponiere`` ohne Eingang)."""
    belegt = frozenset(key for key, m in gs.mengen.items() if m[h] is not None)
    v = vorlagen.get(belegt)
    if v is None:
        v = vorlagen[belegt] = _vorlage(gs, belegt, traeger)
    traeger_h = list(v.traeger)
    if not v.eingaenge:
        return None, traeger_h
    eingaenge = [Eingang(e.kategorie, e.ziel, e.vorzeichen,
                         gs.mengen[key][h] - (az_abzug if key == bilanz_leser._AGGREGAT_KEY else 0.0), e.pv_inv_id)
                 for key, e in v.eingaenge]
    return komponiere_bilanz_zeitraum(eingaenge, traeger_h, dc_grund=dc_grund), traeger_h


def _rest(k: Optional[BilanzZeitraum]) -> float:
    """Der Rest des Anlagenzählers, den die Geräte ohne eigenes Δ bekommen (``PvZeitraum.verteilter_rest_kwh``)."""
    if k is None or k.pv is None or k.pv.anlagenzaehler_kwh is None:
        return 0.0
    return k.pv.verteilter_rest_kwh


def rest_faktor(rest_stunden: Sequence[float], rest_tag: float) -> Optional[float]:
    """S3-R4 (berichtigt 15.10.): der Faktor, mit dem der Stundenrest auf den Tagesrest skaliert wird —
    ``Rest_Tag / Σ_h rest_h``. 1 ohne Rest; ``None``, wenn der Tag einen Rest hat, die Stunden aber keinen (nicht
    skalierbar — der Wächter meldet den Tag)."""
    summe = sum(rest_stunden)
    if summe <= _KLEMM_TOL:
        return 1.0 if rest_tag <= _KLEMM_TOL else None
    return rest_tag / summe


def _kompositionen(gs: GruppenStunden, traeger: Sequence[PvTraeger], dc_grund: Optional[str],
                   tag: BilanzZeitraum) -> tuple[list[Optional[BilanzZeitraum]], list[int], Optional[float]]:
    """Je Slot die Komposition der Stunde (S3-R3), die Klemm-Stunden und — S3-R4 — die Tagesrest-Skalierung: der Rest
    des Anlagenzählers je Stunde wird auf den Rest der Tageskomposition skaliert (``rest_h × Rest_Tag / Σ_h rest_h``),
    indem das Δ des Anlagenzählers der Stunde um ``(1 − Faktor) × rest_h`` sinkt. Gemessene Geräte bleiben ``change``."""
    vorlagen: dict = {}
    roh = [_komposition_der_stunde(gs, h, traeger, dc_grund, vorlagen) for h in range(SLOTS)]
    reste = [_rest(k) for k, _t in roh]
    faktor = rest_faktor(reste, _rest(tag))
    kompositionen: list[Optional[BilanzZeitraum]] = []
    klemm: list[int] = []
    for h, (k, traeger_h) in enumerate(roh):
        if faktor is not None and reste[h] > 0 and abs(faktor - 1.0) > _KLEMM_TOL:
            k, traeger_h = _komposition_der_stunde(gs, h, traeger, dc_grund, vorlagen, (1.0 - faktor) * reste[h])
        kompositionen.append(k)
        if klemm_der_stunde(k, traeger_h):
            klemm.append(h)
    return kompositionen, klemm, faktor


@dataclass(frozen=True)
class _BilanzPlan:
    """Die Tageswahl der Bilanz-Gruppe mit Wahl ``kanal``: Komposition des Tages, Stammdaten, die Zähler des Tages."""

    kz: Any
    stamm: Any
    datum: date
    gewaehlt: tuple[TabellenEintrag, ...]

    @property
    def keys(self) -> set[str]:
        return {e.schluessel for e in self.gewaehlt}

    def aktiv(self, inv) -> bool:
        return inv.ist_aktiv_an(self.datum)


async def _bilanz_plan(db: AsyncSession, anlage_id: int, datum: date, kz) -> tuple[Quellenwahl, Optional[_BilanzPlan]]:
    """Die Wahl der Tages-Leser (``tage_bilanz``) und bei ``kanal`` die Zähler des Tages (Entweder-oder des Tages)."""
    if kz is None:
        return Quellenwahl(QUELLE_BESTAND, {"": "keine_faellige_stunde"}, {}), None
    if kz.wahl.quelle != QUELLE_KANAL or kz.komposition is None:
        return kz.wahl, None
    stamm = await bilanz_leser._stamm(db, anlage_id)
    eintraege = await stamm.eintraege(db, (lambda i: i.ist_aktiv_an(datum)), datum)
    deltas = {e.schluessel: bilanz_leser._gedeckt(kz.wahl.ergebnisse.get(e.schluessel), True)[1] for e in eintraege}
    gewaehlt = resolve_either_or_eintraege(
        eintraege, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: deltas.get(e.schluessel) is not None,
    )
    return kz.wahl, _BilanzPlan(kz, stamm, datum, tuple(e for e in gewaehlt if deltas.get(e.schluessel) is not None))


def _bilanz_bauen(plan: _BilanzPlan, je: dict, tag: dict) -> None:
    """Stunden, Komposition je Stunde und Klemm-Stunden der Bilanz-Gruppe eines Tages (S3-R3/R4)."""
    gs = _gruppe_aus(plan.datum, GRUPPE_BILANZ, plan.kz.wahl, je, plan.gewaehlt)
    traeger = bilanz_leser._traeger(plan.stamm.invs, plan.aktiv)
    kompositionen, klemm, faktor = _kompositionen(gs, traeger, bilanz_leser._dc_grund(plan.stamm.invs, plan.aktiv),
                                                  plan.kz.komposition)
    tag["gruppen"][GRUPPE_BILANZ] = gs
    tag["bilanz"] = BilanzStunden(tuple(kompositionen), plan.kz.komposition, tuple(traeger), tuple(klemm), faktor)


async def _bilanz(db: AsyncSession, anlage_id: int, datum: date, jetzt: int, tag: dict) -> Quellenwahl:
    """Die Bilanz-Gruppe: Tageswahl der Tages-Leser; bei ``kanal`` Stunden, Komposition je Stunde, Klemm-Stunden."""
    kz = (await bilanz_leser.tage_bilanz(db, anlage_id, datum, datum, jetzt=jetzt)).get(datum)
    wahl, plan = await _bilanz_plan(db, anlage_id, datum, kz)
    if plan is not None:
        _bilanz_bauen(plan, await _lies_stunden(db, anlage_id, plan.keys, datum, jetzt), tag)
    return wahl


# ── Geräte- und WP-Gruppe: Tageswahl (dieselbe `_bedarf`-Logik wie der Monat) ─


async def _tages_deltas(db: AsyncSession, anlage_id: int, keys: set[str], von: int, bis: int,
                        jetzt: int) -> dict[str, Zeitraum]:
    mengen = [k for k in (await kanaele_laden(db, anlage_id, keys)).values() if k.art == ART_SUM]
    return await zeitraum_stapel(db, mengen, von, bis, jetzt=jetzt) if mengen else {}


def _gewaehlte_keys(gruppe: geraete_leser.GruppeZeitraum, bedarf) -> set[str]:
    """Die Kanäle, die eine Geräte-Gruppe am Tag trägt: die gewählten Felder je Gerät und den abgeleiteten Anteil."""
    keys = {f"inv:{i}:{f}" for i, zeile in gruppe.zeilen.items() for f in zeile}
    keys |= {k for k in bedarf.keys() if k.startswith("abgeleitet:")}
    keys |= {k for ks in bedarf.abgeleitet.values() for k in ks}
    return keys


def _zaehler_der_gruppe(eintraege: Sequence[TabellenEintrag], keys: set[str]) -> list[TabellenEintrag]:
    """Die Zähler des Tagespfads (Kategorie, Ziel, Vorzeichen), deren Kanal die Gruppe trägt — Entweder-oder des Tages
    über dieselbe Funktion wie der Tagespfad (``resolve_either_or_eintraege``, „Kanal da")."""
    return list(resolve_either_or_eintraege(
        [e for e in eintraege if e.schluessel in keys], gruppe_fn=lambda e: e.gruppe,
        hat_tagesdaten_fn=lambda e: e.schluessel in keys,
    ))


async def _geraete_bedarf(db: AsyncSession, anlage_id: int, datum: date):
    stamm = await geraete_leser._stamm(db, anlage_id)
    return await geraete_leser._bedarf(db, stamm, lambda i: i.ist_aktiv_an(datum), datum)


def _geraete_wahl(emob_b, sonst_b, z: dict) -> tuple[dict[str, Quellenwahl], dict[str, set[str]]]:
    """Die Tageswahl von E-Mob und Sonstiges und je Gruppe mit ``kanal`` ihre Kanäle."""
    out: dict[str, Quellenwahl] = {}
    keys: dict[str, set[str]] = {}
    for gruppe, bedarf in ((GRUPPE_EMOB, emob_b), (GRUPPE_SONSTIGES, sonst_b)):
        g = geraete_leser.waehle_gruppe(bedarf, z)
        out[gruppe] = g.wahl
        if g.kanal:
            keys[gruppe] = _gewaehlte_keys(g, bedarf)
    return out, keys


async def _geraete_bauen(db: AsyncSession, anlage_id: int, datum: date, out: dict, keys: dict, je: dict,
                         tag: dict) -> None:
    """E-Mob und Sonstiges aus EINEM gemeinsamen Stunden-Stapel."""
    gs = _gruppe_aus(datum, "geraete", out[next(iter(keys))], je, await _tageszaehler(db, anlage_id, datum, tag))
    for gruppe, ks in keys.items():
        tag["gruppen"][gruppe] = _teilgruppe(gs, gruppe, out[gruppe], ks)


async def _geraete(db: AsyncSession, anlage_id: int, datum: date, jetzt: int, tag: dict) -> dict[str, Quellenwahl]:
    emob_b, sonst_b = await _geraete_bedarf(db, anlage_id, datum)
    von, bis = tagesfenster(datum)
    out, keys = _geraete_wahl(emob_b, sonst_b,
                              await _tages_deltas(db, anlage_id, emob_b.keys() | sonst_b.keys(), von, bis, jetzt))
    if keys:
        alle = set().union(*keys.values())
        await _geraete_bauen(db, anlage_id, datum, out, keys, await _lies_stunden(db, anlage_id, alle, datum, jetzt),
                             tag)
    return out


def _teilgruppe(gs: GruppenStunden, gruppe: str, wahl: Quellenwahl, keys: set[str]) -> GruppenStunden:
    """Eine Teilgruppe aus einem gemeinsamen Stunden-Stapel (E-Mob und Sonstiges lesen in EINER Anweisung)."""
    mengen = {k: v for k, v in gs.mengen.items() if k in keys}
    spannen = {k: v for k, v in gs.spannen.items() if k in keys}
    return GruppenStunden(
        gruppe=gruppe, wahl=wahl, mengen=mengen, spannen=spannen, gedeckt_von=gs.gedeckt_von,
        gedeckt_bis=gs.gedeckt_bis, groesste_spanne=gs.groesste_spanne,
        eintraege=tuple(_zaehler_der_gruppe(gs.eintraege, set(mengen))),
    )


async def _wp_bedarf(db: AsyncSession, anlage_id: int, datum: date, stamm=None):
    """Der Bedarf der WP-Gruppe am Tag. ``stamm``: derselbe WP-Stamm für viele Tage (die abzuleitenden Geräte hängen
    nicht am Tag — ``wp_leser._stamm`` merkt sie sich je Stamm, ein frischer Stamm fragt die Mitschrift-Kanäle neu)."""
    stamm = stamm if stamm is not None else await wp_leser._stamm(db, anlage_id)
    return await wp_leser._bedarf(db, stamm, lambda i: i.ist_aktiv_an(datum))


async def _wp_bauen(db: AsyncSession, anlage_id: int, datum: date, wahl: Quellenwahl, je: dict, tag: dict) -> None:
    gs = _gruppe_aus(datum, GRUPPE_WP, wahl, je, await _tageszaehler(db, anlage_id, datum, tag))
    tag["gruppen"][GRUPPE_WP] = _teilgruppe(gs, GRUPPE_WP, wahl, set(gs.mengen))


async def _wp(db: AsyncSession, anlage_id: int, datum: date, jetzt: int, tag: dict) -> Quellenwahl:
    bedarf = await _wp_bedarf(db, anlage_id, datum)
    von, bis = tagesfenster(datum)
    w = wp_leser.waehle_wp(bedarf, await _tages_deltas(db, anlage_id, bedarf.keys(), von, bis, jetzt))
    if w.kanal:
        await _wp_bauen(db, anlage_id, datum, w.wahl, await _lies_stunden(db, anlage_id, bedarf.keys(), datum, jetzt),
                        tag)
    return w.wahl


async def _tageszaehler(db: AsyncSession, anlage_id: int, datum: date, tag: dict) -> list[TabellenEintrag]:
    """Die Zähler, die der Tagespfad an diesem Tag nähme (alle Kategorien; ``bilanz_adapter.zaehler_eintraege``) —
    einmal je Kanal-Stundentag."""
    if "zaehler" not in tag:
        stamm = await geraete_leser._stamm(db, anlage_id)
        invs_by_id = {str(i.id): i for i in stamm.invs if i.ist_aktiv_an(datum)}
        tag["zaehler"] = await zaehler_eintraege(db, stamm.anlage, invs_by_id, datum)
    return tag["zaehler"]


# ── Strom je Betriebsart je Stunde (Wärme-Sichten, E-S3-2 Nachbau H-1 → A) ──────────────────────────────────────


async def modus_strom_stunden(
    db: AsyncSession, anlage_id: int, datum: date, inv_ids, *, jetzt: Optional[int] = None,
) -> dict[int, dict[str, tuple[Optional[float], ...]]]:
    """Je Gerät je Betriebsart (``MODUS_STROM_ERFASST`` und ``rest``) die 24 Slots des abgeleiteten kWh-Kanals
    ``abgeleitet:inv:<id>:modus_strom_<art>_kwh`` (E4d) — HAs ``change`` wie jeder Mengen-Kanal, EINE Anweisung. Die
    WP-Gruppe des Kanal-Stundentags trägt nur Heizen/Warmwasser/Kühlen (die Felder der Monatszeile); die Stundenform des
    Rests und der erfassten Lüften/Entfeuchten braucht alle sechs (Σ = Strom des Geräts, ``modus_strom.py``)."""
    from backend.core.berechnungen.modus_split import MODUS_STROM_ERFASST, MODUS_STROM_REST
    from backend.services.kanal.modus_strom import modus_strom_key

    jetzt = bilanz_leser.uhr() if jetzt is None else int(jetzt)
    keys = {modus_strom_key(i, m): (int(i), m) for i in inv_ids for m in (*MODUS_STROM_ERFASST, MODUS_STROM_REST)}
    out: dict[int, dict[str, tuple[Optional[float], ...]]] = {}
    merk: dict = {}
    for key, st in (await _lies_stunden(db, anlage_id, set(keys), datum, jetzt)).items():
        inv_id, art = keys[key]
        out.setdefault(inv_id, {})[art] = slots_der_stunden(datum, st, merk)[0]
    return out


# ── Bereich: EIN `stunden_stapel` je Gruppe über viele Tage (E-S3-2 Nachbau, Bauplan §10c L-1) ──────────────────
#
# `tage-werte` und `monat` brauchen die Stunden vieler Kanal-Tage. Je Tag ein Kanal-Stundentag kostete je Tag und Gruppe
# eine Stunden- und eine Randstand-Anweisung. Der Bereichs-Leser wählt je Tag wie der Tages-Leser (dieselben Pläne), liest
# aber je Gruppe EINEN `stunden_stapel` über `[tagesfenster(von)[0], tagesfenster(bis)[1])` und EINEN `reihe_stapel` für
# die Tageswahl der Geräte und der WP, und schneidet je Tag aus — dieselben Zeilen, dieselbe Abdeckung wie der Tages-Leser
# (Probe `test_kanal_stundentage_bereich.py`, bitgleich).

_UNBEKANNT = object()


@dataclass(frozen=True)
class Ausschnitt:
    """Die Stunden eines Kanals in einem Tagesfenster, aus einem Bereich geschnitten — die Felder von ``Stunden``, die
    der Kanal-Stundentag liest."""

    werte: list
    gedeckt_von: Optional[int]
    gedeckt_bis: Optional[int]
    groesste_spanne: Optional[int]


def _vor_des_bereichs(st: Stunden) -> Optional[int]:
    """Der Stand vor dem Bereich (Zeitpunkt), wie ``stunden_stapel`` ihn las — aus der ersten Zeile oder der Abdeckung."""
    if st.werte:
        w = st.werte[0]
        return w.start_ts - w.spanne if w.change is not None and w.spanne is not None else None
    return st.gedeckt_von - _STUNDE if st.gedeckt_von is not None else None


def _nach_des_bereichs(st: Stunden, letzte: int):
    """Die erste Zeile hinter dem Bereich — ``None`` (es gibt keine), ihr Zeitpunkt, oder ``_UNBEKANNT``, wenn der
    Bereich es nicht verrät (dann liest der Tag selbst)."""
    if st.grund == GRUND_ENDET_VOR_BIS:
        return None
    innen = max((w.spanne for w in st.werte if w.spanne is not None), default=0)
    if st.groesste_spanne is not None and st.groesste_spanne > innen:
        return letzte + st.groesste_spanne
    return _UNBEKANNT


def ausschnitt(st: Stunden, ts: Sequence[int], von: int, bis: int) -> Optional[Ausschnitt]:
    """Das Tagesfenster ``[von, bis)`` aus dem Bereichs-Ergebnis ``st`` (``ts`` = die Zeitpunkte seiner Zeilen) — wie
    ``stunden_stapel`` über das Fenster. ``None``: der Schwanz einer Lücke reicht über den Bereich hinaus und ist nicht
    bestimmbar."""
    i, j = bisect_left(ts, von), bisect_left(ts, bis)
    werte = st.werte[i:j]
    vor = ts[i - 1] if i > 0 else _vor_des_bereichs(st)
    letzte = werte[-1].start_ts if werte else vor
    spannen = [w.spanne for w in werte if w.spanne is not None]
    if letzte is not None and letzte + _STUNDE < bis:
        nach = ts[j] if j < len(ts) else _nach_des_bereichs(st, letzte)
        if nach is _UNBEKANNT:
            return None
        if nach is not None:
            spannen.append(nach - letzte)
    anfang = vor if vor is not None else (werte[0].start_ts if werte else None)
    return Ausschnitt(werte, anfang + _STUNDE if anfang is not None else None,
                      letzte + _STUNDE if letzte is not None else None, max(spannen) if spannen else None)


class _Bereich:
    """Die Stunden der Kanäle ``keys`` über einen Tagesbereich — EINE Anweisung; je Tag ein Ausschnitt."""

    def __init__(self, db: AsyncSession, anlage_id: int, jetzt: int):
        self.db, self.anlage_id, self.jetzt = db, anlage_id, jetzt
        self.je: dict[str, tuple[Stunden, list[int]]] = {}

    async def laden(self, keys: set[str], tage: Sequence[date]) -> "_Bereich":
        mengen = [k for k in (await kanaele_laden(self.db, self.anlage_id, keys)).values() if k.art == ART_SUM]
        if mengen:
            je = await stunden_stapel(self.db, mengen, tagesfenster(tage[0])[0], tagesfenster(tage[-1])[1],
                                      jetzt=self.jetzt)
            self.je = {k: (st, [w.start_ts for w in st.werte]) for k, st in je.items()}
        return self

    async def tag(self, keys: set[str], datum: date) -> dict:
        """Die Stunden der Kanäle ``keys`` am Tag — aus dem Bereich, sonst (Schwanz unbestimmt) vom Tag selbst."""
        von, bis = tagesfenster(datum)
        out = {}
        for k in keys:
            if k in self.je:
                a = ausschnitt(*self.je[k], von, bis)
                if a is None:
                    return await _lies_stunden(self.db, self.anlage_id, keys, datum, self.jetzt)
                out[k] = a
        return out


async def _deltas_bereich(db: AsyncSession, anlage_id: int, keys: set[str], tage: Sequence[date],
                          jetzt: int) -> dict[date, dict[str, Zeitraum]]:
    """Δ und Abdeckung je Tag für die Tageswahl — EIN ``reihe_stapel`` über die Tagesgrenzen (wie ``tage_bilanz``)."""
    mengen = [k for k in (await kanaele_laden(db, anlage_id, keys)).values() if k.art == ART_SUM]
    if not mengen:
        return {d: {} for d in tage}
    grenzen = [tagesfenster(d)[0] for d in tage] + [tagesfenster(tage[-1])[1]]
    je = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt)
    return {d: {k: liste[i] for k, liste in je.items()} for i, d in enumerate(tage)}


async def _bilanz_bereich(db: AsyncSession, anlage_id: int, tage: Sequence[date], jetzt: int, tags: dict,
                          wahlen: dict) -> None:
    tb = await bilanz_leser.tage_bilanz(db, anlage_id, tage[0], tage[-1], jetzt=jetzt)
    plaene = {}
    for d in tage:
        wahlen[d][GRUPPE_BILANZ], plan = await _bilanz_plan(db, anlage_id, d, tb.get(d))
        if plan is not None:
            plaene[d] = plan
    keys = set().union(*(p.keys for p in plaene.values())) if plaene else set()
    bereich = await _Bereich(db, anlage_id, jetzt).laden(keys, tage)
    for d, plan in plaene.items():
        _bilanz_bauen(plan, await bereich.tag(plan.keys, d), tags[d])


async def _geraete_bereich(db: AsyncSession, anlage_id: int, tage: Sequence[date], jetzt: int, tags: dict,
                           wahlen: dict) -> None:
    bedarfe = {d: await _geraete_bedarf(db, anlage_id, d) for d in tage}
    alle = set().union(*(e.keys() | s.keys() for e, s in bedarfe.values()))
    z = await _deltas_bereich(db, anlage_id, alle, tage, jetzt)
    plaene = {}
    for d in tage:
        out, keys = _geraete_wahl(*bedarfe[d], z[d])
        wahlen[d].update(out)
        if keys:
            plaene[d] = (out, keys, set().union(*keys.values()))
    bereich = await _Bereich(db, anlage_id, jetzt).laden(set().union(*(p[2] for p in plaene.values())) if plaene
                                                         else set(), tage)
    for d, (out, keys, ks) in plaene.items():
        await _geraete_bauen(db, anlage_id, d, out, keys, await bereich.tag(ks, d), tags[d])


async def _wp_bereich(db: AsyncSession, anlage_id: int, tage: Sequence[date], jetzt: int, tags: dict,
                      wahlen: dict) -> None:
    stamm = await wp_leser._stamm(db, anlage_id)
    bedarfe = {d: await _wp_bedarf(db, anlage_id, d, stamm) for d in tage}
    z = await _deltas_bereich(db, anlage_id, set().union(*(b.keys() for b in bedarfe.values())), tage, jetzt)
    plaene = {}
    for d in tage:
        w = wp_leser.waehle_wp(bedarfe[d], z[d])
        wahlen[d][GRUPPE_WP] = w.wahl
        if w.kanal:
            plaene[d] = w.wahl
    bereich = await _Bereich(db, anlage_id, jetzt).laden(
        set().union(*(bedarfe[d].keys() for d in plaene)) if plaene else set(), tage)
    for d, wahl in plaene.items():
        await _wp_bauen(db, anlage_id, d, wahl, await bereich.tag(bedarfe[d].keys(), d), tags[d])


# ── Fassade ─────────────────────────────────────────────────────────────────


async def kanal_stundentag(
    db: AsyncSession, anlage_id: int, datum: date, *, jetzt: Optional[int] = None,
) -> KanalStundentag:
    """Der Kanal-Stundentag einer Anlage — je Gruppe mit Wahl ``kanal`` die 24 Slots. Im Lade-Kontext einer Anfrage
    einmal je Tag (``lade_kontext.gemerkt``)."""
    from backend.services.kanal.lade_kontext import gemerkt

    jetzt = bilanz_leser.uhr() if jetzt is None else int(jetzt)
    return await gemerkt(db, ("kanal_stundentag", anlage_id, datum, jetzt),
                         lambda: _kanal_stundentag(db, anlage_id, datum, jetzt))


async def _kanal_stundentag(db: AsyncSession, anlage_id: int, datum: date, jetzt: int) -> KanalStundentag:
    von, bis = tagesfenster(datum)
    tag: dict = {"gruppen": {}, "bilanz": None}
    wahlen = {GRUPPE_BILANZ: await _bilanz(db, anlage_id, datum, jetzt, tag)}
    wahlen.update(await _geraete(db, anlage_id, datum, jetzt, tag))
    wahlen[GRUPPE_WP] = await _wp(db, anlage_id, datum, jetzt, tag)
    return KanalStundentag(datum=datum, von=von, bis=bis, wahlen=wahlen, gruppen=dict(tag["gruppen"]),
                           bilanz=tag["bilanz"])




async def kanal_stundentage(
    db: AsyncSession, anlage_id: int, von: date, bis: date, *, jetzt: Optional[int] = None,
    gruppen: Sequence[str] = GRUPPEN,
) -> dict[date, KanalStundentag]:
    """Der Kanal-Stundentag jedes Tages ``von`` … ``bis`` — je Tag und je gefragter Gruppe dasselbe Ergebnis wie
    ``kanal_stundentag``, gelesen mit EINEM ``stunden_stapel`` je Gruppe über den ganzen Bereich (Bauplan §10c L-1).
    Tage ohne fällige Stunde liest der Tages-Leser. Im Lade-Kontext einmal je Bereich und Gruppensatz.

    ``gruppen`` (Entscheid L-1b → A): nur diese Gruppen werden gelesen; ``wahlen`` und ``gruppen`` des Ergebnisses
    nennen nur sie. Eine Sicht fragt nach den Gruppen, deren Stunden sie liest — ``tage-werte`` und ``monat`` lesen aus
    den Stunden eines Kanal-Tags nur die stundengepaarten Größen der Bilanz (Direktverbrauch, Überschuss, Defizit, Zahl
    der Stunden) und den WP-Strom (``wp_strom_kwh``, ``wp_erfasst``), also Bilanz und WP; die Geräte-Gruppe (E-Mob,
    Sonstiges) liest dort niemand. ``/stunden`` (der Geräte-Stapel) liest alle Gruppen über den Tages-Leser."""
    from backend.services.kanal.lade_kontext import gemerkt

    jetzt = bilanz_leser.uhr() if jetzt is None else int(jetzt)
    gefragt = frozenset(gruppen)
    return await gemerkt(db, ("kanal_stundentage", anlage_id, von, bis, jetzt, gefragt),
                         lambda: _kanal_stundentage(db, anlage_id, von, bis, jetzt, gefragt))


def _nur(tag: KanalStundentag, gefragt: frozenset) -> KanalStundentag:
    """Ein Kanal-Stundentag eingeschränkt auf die gefragten Gruppen."""
    return dataclasses.replace(
        tag, wahlen={g: w for g, w in tag.wahlen.items() if g in gefragt},
        gruppen={g: gs for g, gs in tag.gruppen.items() if g in gefragt},
        bilanz=tag.bilanz if GRUPPE_BILANZ in gefragt else None,
    )


async def _kanal_stundentage(db: AsyncSession, anlage_id: int, von: date, bis: date, jetzt: int,
                             gefragt: frozenset = frozenset(GRUPPEN)) -> dict[date, KanalStundentag]:
    se = soll_ende(jetzt)
    alle = bilanz_leser._tage(von, bis)
    tage = [d for d in alle if tagesfenster(d)[0] < se]
    tags = {d: {"gruppen": {}, "bilanz": None} for d in tage}
    wahlen: dict[date, dict] = {d: {} for d in tage}
    for gruppe, lauf in ((GRUPPE_BILANZ, _bilanz_bereich), (GRUPPE_EMOB, _geraete_bereich), (GRUPPE_WP, _wp_bereich)):
        if tage and (gruppe in gefragt or (gruppe == GRUPPE_EMOB and GRUPPE_SONSTIGES in gefragt)):
            await lauf(db, anlage_id, tage, jetzt, tags, wahlen)
    out = {d: _nur(KanalStundentag(datum=d, von=tagesfenster(d)[0], bis=tagesfenster(d)[1], wahlen=wahlen[d],
                                   gruppen=dict(tags[d]["gruppen"]), bilanz=tags[d]["bilanz"]), gefragt) for d in tage}
    for d in alle:
        if d not in out:
            out[d] = _nur(await _kanal_stundentag(db, anlage_id, d, jetzt), gefragt)
    return dict(sorted(out.items()))


__all__ = [
    "Ausschnitt", "BilanzStunden", "GRUPPEN", "GRUPPE_BILANZ", "GRUPPE_EMOB", "GRUPPE_SONSTIGES", "GRUPPE_WP",
    "GruppenStunden", "KanalStundentag", "SLOTS", "ausschnitt", "kanal_stundentag", "kanal_stundentage",
    "klemm_der_stunde", "modus_strom_stunden", "slots_der_stunden",
]
