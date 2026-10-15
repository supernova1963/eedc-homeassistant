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

**Komposition je Stunde (S3-R3)** — die Bilanz-Gruppe über DIESELBE Funktion wie der Tag,
``bilanz_leser.waehle_und_komponiere``, je Slot mit dem Zeitraum der Stunde. Vorbereitet werden nur die Eingänge:

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

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.bilanz_zeitraum import BilanzZeitraum
from backend.core.berechnungen.pv_verteilung import PvTraeger
from backend.core.berechnungen.slot_konvention import lts_boundary_index
from backend.models.kanal import ART_SUM
from backend.services.kanal import bilanz_leser, geraete_leser, wp_leser
from backend.services.kanal.bilanz_adapter import zaehler_eintraege
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.lesen import Stunden, Zeitraum, kanaele_laden, stunden_stapel, zeitraum_stapel
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


def slots_der_stunden(datum: date, st: Stunden) -> tuple[tuple[Optional[float], ...], tuple[Optional[int], ...]]:
    """Die Zeilen eines Kanals im Tagesfenster auf die 24 Backward-Slots (``lts_boundary_index``). Fallen zwei Zeilen
    auf einen Slot (Herbst-Umstellung), trägt er beide Zuwächse und beide Spannen; ein Slot ohne Zeile bleibt ``None``."""
    menge: list[Optional[float]] = [None] * SLOTS
    spanne: list[Optional[int]] = [None] * SLOTS
    for w in st.werte:
        h = lts_boundary_index(datetime.fromtimestamp(w.start_ts), datum)
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


async def _gruppen_stunden(
    db: AsyncSession, anlage_id: int, datum: date, gruppe: str, wahl: Quellenwahl, keys: set[str],
    eintraege: Sequence[TabellenEintrag], jetzt: int,
) -> GruppenStunden:
    """EIN ``stunden_stapel`` über die Mengen-Kanäle der Gruppe im Tagesfenster."""
    von, bis = tagesfenster(datum)
    mengen = [k for k in (await kanaele_laden(db, anlage_id, keys)).values() if k.art == ART_SUM]
    je = await stunden_stapel(db, mengen, von, bis, jetzt=jetzt) if mengen else {}
    slots = {key: slots_der_stunden(datum, st) for key, st in je.items()}
    gedeckt_von, gedeckt_bis, groesste = _abdeckung(list(je.values()))
    return GruppenStunden(
        gruppe=gruppe, wahl=wahl, mengen={k: m for k, (m, _s) in slots.items()},
        spannen={k: s for k, (_m, s) in slots.items()}, gedeckt_von=gedeckt_von, gedeckt_bis=gedeckt_bis,
        groesste_spanne=groesste, eintraege=tuple(e for e in eintraege if e.schluessel in slots),
    )


# ── Bilanz-Gruppe: Tageswahl, Entweder-oder des Tages, Komposition je Stunde ─


def _zeitraum_der_stunde(key: str, von: int, change: float, spanne: Optional[int]) -> Zeitraum:
    """Ein belegter Slot als voll gedeckter Zeitraum der Stunde — der Eingang von ``waehle_und_komponiere``."""
    return Zeitraum(key=key, art=ART_SUM, einheit="kWh", von=von, bis=von + _STUNDE, delta=change, teil_delta=None,
                    gedeckt_von=von, gedeckt_bis=von + _STUNDE, rand_spanne=spanne, voll=True, grund=None,
                    laufend=False)


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


def _komposition_der_stunde(gs: GruppenStunden, h: int, traeger: Sequence[PvTraeger], dc_grund: Optional[str],
                            von: int, az_abzug: float = 0.0) -> tuple[Optional[BilanzZeitraum], list[PvTraeger]]:
    """``waehle_und_komponiere`` mit dem Zeitraum der Stunde (S3-R3). ``az_abzug`` mindert das Δ des Anlagenzählers
    der Stunde — die Tagesrest-Skalierung (S3-R4) als Eingang, nicht als zweite Komposition."""
    belegt = {key for key, m in gs.mengen.items() if m[h] is not None}
    eintraege_h = [e for e in gs.eintraege if e.schluessel in belegt]
    ergebnisse = {}
    for key in belegt:
        change = gs.mengen[key][h] - (az_abzug if key == bilanz_leser._AGGREGAT_KEY else 0.0)
        ergebnisse[key] = _zeitraum_der_stunde(key, von + h * _STUNDE, change, gs.spannen[key][h])
    traeger_h = _traeger_der_stunde(traeger, gs.eintraege, belegt)
    kz = bilanz_leser.waehle_und_komponiere(eintraege_h, ergebnisse, traeger_h, lueckentag=False, dc_grund=dc_grund)
    return (kz.komposition if kz.wahl.quelle == QUELLE_KANAL else None), traeger_h


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


def _kompositionen(gs: GruppenStunden, traeger: Sequence[PvTraeger], dc_grund: Optional[str], von: int,
                   tag: BilanzZeitraum) -> tuple[list[Optional[BilanzZeitraum]], list[int], Optional[float]]:
    """Je Slot die Komposition der Stunde (S3-R3), die Klemm-Stunden und — S3-R4 — die Tagesrest-Skalierung: der Rest
    des Anlagenzählers je Stunde wird auf den Rest der Tageskomposition skaliert (``rest_h × Rest_Tag / Σ_h rest_h``),
    indem das Δ des Anlagenzählers der Stunde um ``(1 − Faktor) × rest_h`` sinkt. Gemessene Geräte bleiben ``change``."""
    roh = [_komposition_der_stunde(gs, h, traeger, dc_grund, von) for h in range(SLOTS)]
    reste = [_rest(k) for k, _t in roh]
    faktor = rest_faktor(reste, _rest(tag))
    kompositionen: list[Optional[BilanzZeitraum]] = []
    klemm: list[int] = []
    for h, (k, traeger_h) in enumerate(roh):
        if faktor is not None and reste[h] > 0 and abs(faktor - 1.0) > _KLEMM_TOL:
            k, traeger_h = _komposition_der_stunde(gs, h, traeger, dc_grund, von, (1.0 - faktor) * reste[h])
        kompositionen.append(k)
        if klemm_der_stunde(k, traeger_h):
            klemm.append(h)
    return kompositionen, klemm, faktor


async def _bilanz(db: AsyncSession, anlage_id: int, datum: date, jetzt: int, tag: dict) -> Quellenwahl:
    """Die Bilanz-Gruppe: Tageswahl der Tages-Leser; bei ``kanal`` Stunden, Komposition je Stunde, Klemm-Stunden."""
    kz = (await bilanz_leser.tage_bilanz(db, anlage_id, datum, datum, jetzt=jetzt)).get(datum)
    if kz is None:
        return Quellenwahl(QUELLE_BESTAND, {"": "keine_faellige_stunde"}, {})
    if kz.wahl.quelle != QUELLE_KANAL or kz.komposition is None:
        return kz.wahl
    stamm = await bilanz_leser._stamm(db, anlage_id)
    aktiv = (lambda i: i.ist_aktiv_an(datum))
    eintraege = await stamm.eintraege(db, aktiv, datum)
    deltas = {e.schluessel: bilanz_leser._gedeckt(kz.wahl.ergebnisse.get(e.schluessel), True)[1] for e in eintraege}
    gewaehlt = resolve_either_or_eintraege(
        eintraege, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: deltas.get(e.schluessel) is not None,
    )
    gewaehlt = [e for e in gewaehlt if deltas.get(e.schluessel) is not None]
    gs = await _gruppen_stunden(db, anlage_id, datum, GRUPPE_BILANZ, kz.wahl, {e.schluessel for e in gewaehlt},
                                gewaehlt, jetzt)
    traeger = bilanz_leser._traeger(stamm.invs, aktiv)
    kompositionen, klemm, faktor = _kompositionen(gs, traeger, bilanz_leser._dc_grund(stamm.invs, aktiv),
                                                  tagesfenster(datum)[0], kz.komposition)
    tag["gruppen"][GRUPPE_BILANZ] = gs
    tag["bilanz"] = BilanzStunden(tuple(kompositionen), kz.komposition, tuple(traeger), tuple(klemm), faktor)
    return kz.wahl


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


async def _geraete(db: AsyncSession, anlage_id: int, datum: date, jetzt: int, tag: dict) -> dict[str, Quellenwahl]:
    stamm = await geraete_leser._stamm(db, anlage_id)
    emob_b, sonst_b = await geraete_leser._bedarf(db, stamm, lambda i: i.ist_aktiv_an(datum), datum)
    von, bis = tagesfenster(datum)
    z = await _tages_deltas(db, anlage_id, emob_b.keys() | sonst_b.keys(), von, bis, jetzt)
    out: dict[str, Quellenwahl] = {}
    keys: dict[str, set[str]] = {}
    for gruppe, bedarf in ((GRUPPE_EMOB, emob_b), (GRUPPE_SONSTIGES, sonst_b)):
        g = geraete_leser.waehle_gruppe(bedarf, z)
        out[gruppe] = g.wahl
        if g.kanal:
            keys[gruppe] = _gewaehlte_keys(g, bedarf)
    if keys:
        alle = set().union(*keys.values())
        gs = await _gruppen_stunden(db, anlage_id, datum, "geraete", out[next(iter(keys))], alle,
                                    await _tageszaehler(db, anlage_id, datum, tag), jetzt)
        for gruppe, ks in keys.items():
            tag["gruppen"][gruppe] = _teilgruppe(gs, gruppe, out[gruppe], ks)
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


async def _wp(db: AsyncSession, anlage_id: int, datum: date, jetzt: int, tag: dict) -> Quellenwahl:
    stamm = await wp_leser._stamm(db, anlage_id)
    bedarf = await wp_leser._bedarf(db, stamm, lambda i: i.ist_aktiv_an(datum))
    von, bis = tagesfenster(datum)
    w = wp_leser.waehle_wp(bedarf, await _tages_deltas(db, anlage_id, bedarf.keys(), von, bis, jetzt))
    if w.kanal:
        gs = await _gruppen_stunden(db, anlage_id, datum, GRUPPE_WP, w.wahl, bedarf.keys(),
                                    await _tageszaehler(db, anlage_id, datum, tag), jetzt)
        tag["gruppen"][GRUPPE_WP] = _teilgruppe(gs, GRUPPE_WP, w.wahl, set(gs.mengen))
    return w.wahl


async def _tageszaehler(db: AsyncSession, anlage_id: int, datum: date, tag: dict) -> list[TabellenEintrag]:
    """Die Zähler, die der Tagespfad an diesem Tag nähme (alle Kategorien; ``bilanz_adapter.zaehler_eintraege``) —
    einmal je Kanal-Stundentag."""
    if "zaehler" not in tag:
        stamm = await geraete_leser._stamm(db, anlage_id)
        invs_by_id = {str(i.id): i for i in stamm.invs if i.ist_aktiv_an(datum)}
        tag["zaehler"] = await zaehler_eintraege(db, stamm.anlage, invs_by_id, datum)
    return tag["zaehler"]


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


__all__ = [
    "BilanzStunden", "GRUPPEN", "GRUPPE_BILANZ", "GRUPPE_EMOB", "GRUPPE_SONSTIGES", "GRUPPE_WP", "GruppenStunden",
    "KanalStundentag", "SLOTS", "kanal_stundentag", "klemm_der_stunde", "slots_der_stunden",
]
