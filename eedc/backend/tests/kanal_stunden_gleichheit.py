"""Baustein der Gleichheitsprobe „Kanal-Stundentag == Stundenzeile des Bestands" und des Wächters „Σ Stunden ≡ Tag"
(HA-Bauform S3, Etappe E-S3-1, Auftrag Punkte 4 und 5). Die Proben stehen in ``test_kanal_stunden_gleichheit.py`` und
``test_kanal_stunden_summe.py`` (kein ``test``-Präfix hier, dieselbe Regel wie ``kanal_bilanz_gleichheit.py``).

**Datenstände** wie ``kanal_bilanz_gleichheit.datenstand``: je Form beider Abnahme-Matrizen ``HA`` (Spiegel aus der
Recorder-Statistik, Tage über ``aggregate_day``) und ``MQTT`` (eigene Summe aus ``mqtt_energy_snapshots``, Tage über den
Snapshot-Pfad). Dazu derselbe Vergleich auf der Kanal-Mess-Kopie aus E-S3-0 (Werkzeug im Bericht).

**Was verglichen wird:** je Kanal-Tag und Stunde die Felder der Stundenzeile, die der Adapter trägt
(``stunden_adapter.FELDER``, nur die der Gruppen mit Wahl ``kanal``), gegen die Zeile, die ``aggregate_day``
geschrieben hat — seit HA-Bauform S4 (E-S4-1) die Kanal-Stunde ``h`` (Beginn) gegen den Bestands-Slot ``h+1`` (für
``h = 23`` Slot 0 des Folgetags, ``slot_konvention.bestandszeile_fuer_stundenbeginn``). **Abweichungen werden klassifiziert, nicht weggerundet** (``klasse``), in dieser Reihenfolge:

* ``bestand_ohne_zeile`` — der Bestand hat für die Stunde keine Stundenzeile (Tag ohne Stundenprofil: Retention nach
  730 Tagen; an der Kanal-Kopie die Füllung „Stunde ohne Stundenzeile = Zuwachs 0", Bauplan §10a);
* ``rundung`` — beide Werte da, Unterschied ≤ 0,005 kWh (die Toleranz der Bilanz-Gleichheit; der Bestand schreibt drei
  Stellen, die Kunst-Kopie trägt teils vier);
* ``komponenten_leistungspfad`` — ``komponenten`` der Stundenzeile ist der Leistungspfad (Stundenmittel der
  Leistungskurve, eigene Schlüssel, Senken negativ) und bleibt nach S3-R6 (erweitert 15.10., E-S3-1 H-1 → A) aus der
  Stundenzeile; der Adapter führt seine Zählerform als eigenes Feld — nie gleich, gezählt;
* ``ruecksprung_r4`` — ein Kanal einer betroffenen Achse fällt in der Stunde (der Bestand verwirft, R4);
* ``deckel_r3`` — die Tageszeile hat auf einer betroffenen Achse ``verworfen`` und der Kanal trägt in der Stunde mehr
  als ``kWp × 1,5 × n`` (der Bestand deckelt, R3; das Fenster kann größer sein — dann deckelt er nicht und es gibt
  keine Abweichung);
* ``spannen_fuellung`` (MQTT) bzw. ``luecke_ha`` (HA) — ein Kanal einer betroffenen Achse hat in der Stunde keine Zeile
  oder eine Spanne > 1 h (der Snapshot-Pfad füllt Lücken linear, ``_fill_gaps_linear``; HA und der Kanal tragen die
  Menge in der Folgestunde);
* ``klemm`` — eine Klemm-Stunde (W2-R5 hat einen kWp-Rest auf 0 geklemmt) für die PV und die abhängigen Felder;
* ``rest_skaliert`` — eine Stunde, deren Rest des Anlagenzählers auf den Tagesrest skaliert ist (S3-R4, berichtigt
  15.10.: ``rest_faktor`` ≠ 1 — der Tag hat eine Lücke oder eine Klemmung); der Bestand verteilt den ungekürzten Rest;
* ``erzeuger_hinter_dem_zaehler`` — die PV der Stunde unterscheidet sich genau um die Erzeuger hinter dem Zähler
  (Kategorie ``erzeugung_sonstiges``): der Bestand trägt sie nicht in ``pv_kw`` (benannt an der Kanal-Kopie);
* ``geraet_vor_anschaffung`` — die Stundenzeile trägt ein Gerät, das am Tag nicht aktiv ist (die Zählerauswahl des
  Tages kennt es nicht; benannt an der Kanal-Kopie, deren Kunst-Zeilen Geräte vor der Anschaffung tragen);
* ``zeitumstellung`` — ein Tag mit 23 oder 25 Stunden (an der Kanal-Kopie: ihre Zeilen liegen auf ``von + h · 3600``,
  Bauplan §10a — die Uhr-Abbildung des Bestands und der Kopie weichen dort voneinander ab);
* ``bestand_ohne_wert`` / ``kanal_ohne_wert`` — eine Seite ``None``;
* ``unbenannt`` — alles andere (muss 0 sein, sonst rot).

Felder, die von der PV und dem Netz abhängen (``verbrauch_kw``, ``ueberschuss_kw``, ``defizit_kw``), erben die Klasse
ihrer Achsen in derselben Stunde.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.slot_konvention import bestandszeile_fuer_stundenbeginn
from backend.core.berechnungen.spannen import achse_der_kategorie
from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.kanal.bilanz_leser import als_kanaltag
from backend.services.kanal.stunden_adapter import FELDER, FELDER_JE_GRUPPE, stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import (
    GRUPPE_BILANZ,
    SLOTS,
    KanalStundentag,
    kanal_stundentag,
)

TOL_GLEICH = 1e-9
TOL_RUNDUNG = 0.005 + 1e-9
TOL_SUMME = 1e-6
#: Die Achsen, von denen ein Feld der Stundenzeile abhängt.
_BILANZ_ACHSEN = frozenset({"pv", "einspeisung", "netzbezug", "batterie"})
ACHSEN_DES_FELDS: dict[str, frozenset[str]] = {
    "pv_kw": frozenset({"pv"}), "einspeisung_kw": frozenset({"einspeisung"}),
    "netzbezug_kw": frozenset({"netzbezug"}), "batterie_kw": frozenset({"batterie"}),
    "verbrauch_kw": _BILANZ_ACHSEN, "ueberschuss_kw": _BILANZ_ACHSEN, "defizit_kw": _BILANZ_ACHSEN,
    "waermepumpe_kw": frozenset({"waermepumpe"}), "wallbox_kw": frozenset({"wallbox"}),
}
_PV_ABHAENGIG = frozenset({"pv_kw", "verbrauch_kw", "ueberschuss_kw", "defizit_kw"})
KLASSEN = ("bestand_ohne_zeile", "rundung", "komponenten_leistungspfad", "ruecksprung_r4", "deckel_r3", "spannen_fuellung", "luecke_ha",
           "klemm", "rest_skaliert", "erzeuger_hinter_dem_zaehler", "geraet_vor_anschaffung", "zeitumstellung",
           "bestand_ohne_wert", "kanal_ohne_wert", "unbenannt")


# ── Bestand ─────────────────────────────────────────────────────────────────


async def bestand_zeilen(db: AsyncSession, aid: int, tage: Iterable[date]) -> dict[date, dict[int, Any]]:
    tage = list(tage)
    out: dict[date, dict[int, Any]] = {t: {} for t in tage}
    for r in (await db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == aid, TagesEnergieProfil.datum.in_(tage)))).scalars().all():
        out[r.datum][r.stunde] = r
    return out


async def bestand_verworfen(db: AsyncSession, aid: int, tage: Iterable[date]) -> dict[date, dict]:
    return {z.datum: dict(z.verworfen or {}) for z in (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == aid, TagesZusammenfassung.datum.in_(list(tage))))).scalars().all()}


# ── Bericht ─────────────────────────────────────────────────────────────────


@dataclass
class Bericht:
    #: Zahl der Feldvergleiche je Feld.
    verglichen: Counter = field(default_factory=Counter)
    #: Abweichungen je Klasse (ohne ``gleich``).
    klassen: Counter = field(default_factory=Counter)
    #: Abweichungen je (Klasse, Feld).
    je_feld: Counter = field(default_factory=Counter)
    #: Beispiele je Klasse (die ersten fünf): (Tag, Stunde, Feld, Bestand, Kanal).
    beispiele: dict = field(default_factory=dict)
    #: Tage je Wahl der Gruppen (``bilanz:kanal`` …) und Klemm-Stunden.
    tage: Counter = field(default_factory=Counter)
    klemm_stunden: int = 0

    def merke(self, klasse: str, feld: str, beispiel: tuple) -> None:
        self.klassen[klasse] += 1
        self.je_feld[(klasse, feld)] += 1
        liste = self.beispiele.setdefault(klasse, [])
        if len(liste) < 5:
            liste.append(beispiel)

    def dazu(self, anderer: "Bericht") -> None:
        self.verglichen.update(anderer.verglichen)
        self.klassen.update(anderer.klassen)
        self.je_feld.update(anderer.je_feld)
        self.tage.update(anderer.tage)
        self.klemm_stunden += anderer.klemm_stunden
        for k, v in anderer.beispiele.items():
            liste = self.beispiele.setdefault(k, [])
            liste.extend(v[: max(0, 5 - len(liste))])


# ── Klassifikation ──────────────────────────────────────────────────────────


@dataclass
class _Kontext:
    tag: KanalStundentag
    verworfen: dict
    kwp: Optional[float]
    art: str
    #: Geräte, die am Tag nicht aktiv sind (``ist_aktiv_an``) — als ``inv_id``-Zeichenkette.
    inaktiv: frozenset = frozenset()


def _kanaele_der_achse(tag: KanalStundentag, achse: str) -> list[tuple[Any, Any]]:
    """(Menge, Spanne) je Kanal der Achse — die Kanäle, die der Tag trägt."""
    out = []
    for gs in tag.gruppen.values():
        for e in gs.eintraege:
            if achse_der_kategorie(e.kategorie) == achse and e.schluessel in gs.mengen:
                out.append((gs.mengen[e.schluessel], gs.spannen[e.schluessel]))
    return out


def _achsen_klasse(kx: _Kontext, achse: str, h: int) -> Optional[str]:
    """Die Ursache einer Abweichung auf einer Achse in der Stunde — oder ``None``."""
    from backend.services.snapshot.plausibility import schwelle_pv_einspeisung_stunde_kwh

    kanaele = _kanaele_der_achse(kx.tag, achse)
    if any(m[h] is not None and m[h] < -TOL_GLEICH for m, _s in kanaele):
        return "ruecksprung_r4"
    if achse in kx.verworfen and achse in ("pv", "einspeisung"):
        n = max((round(s[h] / 3600) for _m, s in kanaele if s[h] is not None), default=1)
        schwelle = schwelle_pv_einspeisung_stunde_kwh(kx.kwp, spanne=n)
        summe = sum(m[h] for m, _s in kanaele if m[h] is not None)
        if schwelle is not None and summe > schwelle:
            return "deckel_r3"
    if any(m[h] is None or (s[h] or 3600) > 3600 for m, s in kanaele):
        return "spannen_fuellung" if kx.art == "MQTT" else "luecke_ha"
    return None


def _rest_skaliert(tag: KanalStundentag, h: int) -> bool:
    """Trägt die Stunde einen auf den Tag skalierten Rest des Anlagenzählers (S3-R4, Faktor ≠ 1)?"""
    b = tag.bilanz
    if b is None or b.rest_faktor is None or abs(b.rest_faktor - 1.0) <= TOL_GLEICH:
        return False
    k = b.kompositionen[h]
    return k is not None and k.pv is not None and k.pv.anlagenzaehler_kwh is not None and bool(k.marken)


def _erzeuger_differenz(kx: _Kontext, h: int) -> Optional[float]:
    werte = [gs.mengen[e.schluessel][h] for gs in kx.tag.gruppen.values() for e in gs.eintraege
             if e.kategorie == "erzeugung_sonstiges" and e.schluessel in gs.mengen]
    werte = [w for w in werte if w is not None]
    return sum(werte) if werte else None


def _vor_anschaffung(kx: _Kontext, bestand_komp: Optional[dict]) -> bool:
    """Trägt die Stundenzeile ein Gerät, das am Tag nicht aktiv ist? (Die Zeile kennt es, die Zählerauswahl des Tages
    nicht — benannt an der Kanal-Kopie, deren Kunst-Zeilen Geräte vor ihrer Anschaffung tragen.)"""
    for key, wert in (bestand_komp or {}).items():
        teile = str(key).rsplit("_", 1)
        if len(teile) == 2 and teile[1] in kx.inaktiv and wert is not None and abs(float(wert)) > TOL_GLEICH:
            return True
    return False


def klasse(kx: _Kontext, h: int, feld: str, soll, ist, pv_klasse: Optional[str],
           bestand_komp: Optional[dict] = None) -> Optional[str]:
    """Die Klasse einer Abweichung ``soll`` (Bestand) ↔ ``ist`` (Kanal) — ``None`` heißt gleich."""
    if feld == "komponenten":
        return None if soll == ist else "komponenten_leistungspfad"
    if feld != "spannen" and soll is not None and ist is not None:
        if abs(float(soll) - float(ist)) <= TOL_GLEICH:
            return None
        if abs(float(soll) - float(ist)) <= TOL_RUNDUNG:
            return "rundung"
    elif soll == ist:
        return None
    achsen = ACHSEN_DES_FELDS.get(feld) or frozenset(set(soll or {}) | set(ist or {}))
    for k in ("ruecksprung_r4", "deckel_r3", "spannen_fuellung", "luecke_ha"):
        if any(_achsen_klasse(kx, a, h) == k for a in achsen):
            return k
    if feld in _PV_ABHAENGIG and h in kx.tag.klemm_stunden:
        return "klemm"
    if feld in _PV_ABHAENGIG and _rest_skaliert(kx.tag, h):
        return "rest_skaliert"
    if feld in _PV_ABHAENGIG and pv_klasse == "erzeuger_hinter_dem_zaehler":
        return pv_klasse
    if feld == "pv_kw" and soll is not None and ist is not None:
        e = _erzeuger_differenz(kx, h)
        if e is not None and abs(float(ist) - float(soll) - e) <= TOL_RUNDUNG:
            return "erzeuger_hinter_dem_zaehler"
    if _vor_anschaffung(kx, bestand_komp):
        return "geraet_vor_anschaffung"
    if kx.tag.bis - kx.tag.von != 86400:
        return "zeitumstellung"
    if soll is None:
        return "bestand_ohne_wert"
    if ist is None:
        return "kanal_ohne_wert"
    return "unbenannt"


# ── Vergleich je Tag ────────────────────────────────────────────────────────


def felder_des_tags(tag: KanalStundentag) -> list[str]:
    """Die verglichenen Felder: die der Gruppen mit Wahl ``kanal``; ``spannen``/``komponenten``, wenn eine da ist."""
    out = [f for g in tag.gruppen for f in FELDER_JE_GRUPPE.get(g, ())]
    if tag.gruppen:
        out += ["spannen", "komponenten"]
    return [f for f in FELDER if f in out]


def vergleiche_tag(b: Bericht, kx: _Kontext, bestand: dict[date, dict[int, Any]]) -> None:
    """Je Stunde und Feld Bestand gegen Adapter (gerundet wie der Schreiber). Seit HA-Bauform S4 (E-S4-1, S4-R-3b) ist
    die Kanal-Stunde ``h`` ihr Beginn ``[h, h+1)``; verglichen wird sie mit der Bestandszeile, die dieselbe Stunde trägt
    (``slot_konvention.bestandszeile_fuer_stundenbeginn``: Slot ``h+1``, für ``h = 23`` Slot 0 des Folgetags)."""
    zeilen = stunden_aus_kanaelen(kx.tag).zeilen
    felder = felder_des_tags(kx.tag)
    for h in range(SLOTS):
        tag_b, slot = bestandszeile_fuer_stundenbeginn(kx.tag.datum, h)
        r = bestand.get(tag_b, {}).get(slot)
        pv_klasse = None
        for f in felder:
            soll = getattr(r, f, None) if r is not None else None
            if f == "spannen":
                soll = soll or None
            ist = getattr(zeilen[h], f)
            b.verglichen[f] += 1
            if r is None:
                k = None if ist is None else "bestand_ohne_zeile"
            else:
                k = klasse(kx, h, f, soll, ist, pv_klasse, r.komponenten)
            if f == "pv_kw":
                pv_klasse = k
            if k is not None:
                b.merke(k, f, (kx.tag.datum, h, f, soll, ist))


async def probe_tage(db: AsyncSession, aid: int, tage: list[date], *, jetzt: int, art: str) -> Bericht:
    """Die Gleichheitsprobe über ``tage``: nur Tage, an denen mindestens eine Gruppe aus den Kanälen kommt."""
    b = Bericht()
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    kwp = getattr(anlage, "leistung_kwp", None)
    bestand = await bestand_zeilen(db, aid, sorted(set(tage) | {t + timedelta(days=1) for t in tage}))
    verworfen = await bestand_verworfen(db, aid, tage)
    from backend.models.investition import Investition

    invs = (await db.execute(select(Investition).where(Investition.anlage_id == aid))).scalars().all()
    for d in tage:
        tag = await kanal_stundentag(db, aid, d, jetzt=jetzt)
        for g, w in tag.wahlen.items():
            b.tage[f"{g}:{w.quelle}"] += 1
        if not tag.gruppen:
            continue
        b.klemm_stunden += len(tag.klemm_stunden)
        if tag.bilanz is not None and tag.bilanz.rest_faktor != 1.0:
            f = tag.bilanz.rest_faktor
            b.tage["rest_faktor:" + ("nicht_skalierbar" if f is None else "ueber_1" if f > 1 + TOL_GLEICH
                                     else "unter_1" if f < 1 - TOL_GLEICH else "1")] += 1
        inaktiv = frozenset(str(i.id) for i in invs if not i.ist_aktiv_an(d))
        vergleiche_tag(b, _Kontext(tag, verworfen.get(d, {}), kwp, art, inaktiv), bestand)
    return b


# ── Σ Stunden ≡ Tag (Auftrag Punkt 5, S3-R4) ────────────────────────────────

#: Die Kategorien der Komposition, deren Σ über die Stunden dem Tag streng gleicht (Kanal-Δ, per Konstruktion).
SUMME_KATEGORIEN = ("einspeisung", "netzbezug", "ladung_batterie", "entladung_batterie", "erzeugung_sonstiges")
#: Die Mengen der Bilanz aus den Adapter-Zeilen (``bilanz_aus_stundenrows``) gegen den Kanal-Tag.
SUMME_BILANZ = ("erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh", "speicher_ladung_kwh", "speicher_entladung_kwh",
                "gesamtverbrauch_kwh", "eigenverbrauch_kwh")
#: Was in der Zeilenform netto ist (``batterie_kw``): fließen in einer Stunde Ladung UND Entladung, verrechnet die Zeile
#: sie — die Σ der Zeilen ist dann kleiner als der Tag (wie im Bestand, dessen Spalte ebenso netto ist).
_SPEICHER_FELDER = frozenset({"speicher_ladung_kwh", "speicher_entladung_kwh", "eigenverbrauch_kwh"})


@dataclass
class Summen:
    #: (Tag, Ebene, Schlüssel, Σ Stunden, Tag) je Abweichung über TOL_SUMME, die keine benannte Ausnahme ist (rot).
    abweichungen: list = field(default_factory=list)
    #: dasselbe je benannter Ausnahme: nur ``speicher_netto`` (Zeilenform, Stunde mit Ladung und Entladung, S3-R4/H-2).
    #: Eine Klemm-Ausnahme gibt es nicht mehr (S3-R4 berichtigt: Tagesrest-Skalierung).
    ausnahmen: dict = field(default_factory=dict)
    verglichen: Counter = field(default_factory=Counter)

    def dazu(self, anderer: "Summen") -> None:
        self.abweichungen += anderer.abweichungen
        for k, v in anderer.ausnahmen.items():
            self.ausnahmen.setdefault(k, []).extend(v)
        self.verglichen.update(anderer.verglichen)


def _summe(werte: Iterable[Optional[float]]) -> Optional[float]:
    werte = [w for w in werte if w is not None]
    return sum(werte) if werte else None


def _vergleiche_summe(s: Summen, d: date, ebene: str, key: str, stunden, tag, ausnahme: Optional[str]) -> None:
    """Σ Stunden gegen Tag; eine leere Stundenmenge ist 0 kWh (ein Tag ganz in einer Lücke trägt 0, wie HA)."""
    s.verglichen[ebene] += 1
    if abs(float(stunden or 0.0) - float(tag or 0.0)) <= TOL_SUMME:
        return
    eintrag = (d, ebene, key, stunden, tag)
    if ausnahme is None:
        s.abweichungen.append(eintrag)
    else:
        s.ausnahmen.setdefault(ausnahme, []).append(eintrag)


def _speicher_beidseitig(tag: KanalStundentag) -> bool:
    return any(kz is not None and kz.kat_summe.get("ladung_batterie") and kz.kat_summe.get("entladung_batterie")
               for kz in tag.bilanz.kompositionen)


def _pruefe_bilanz(s: Summen, tag: KanalStundentag) -> None:
    d, b = tag.datum, tag.bilanz
    for kat in SUMME_KATEGORIEN:
        _vergleiche_summe(s, d, "komposition", kat, _summe(kz.kat_summe.get(kat) for kz in b.kompositionen if kz),
                          b.tag.kat_summe.get(kat), None)
    _vergleiche_summe(s, d, "komposition", "pv", _summe(kz.kat_summe.get("pv") for kz in b.kompositionen if kz),
                      b.tag.kat_summe.get("pv"), None)
    zeilen = stunden_aus_kanaelen(tag, gerundet=False).zeilen
    stunden = bilanz_aus_stundenrows(zeilen, verworfen={})
    soll = als_kanaltag(d, b.tag).bilanz
    netto = "speicher_netto" if _speicher_beidseitig(tag) else None
    for f in SUMME_BILANZ:
        ausnahme = netto if f in _SPEICHER_FELDER else None
        _vergleiche_summe(s, d, "adapter", f, getattr(stunden, f), getattr(soll, f), ausnahme)
    keys = set(b.tag.komponenten) | {k for kz in b.kompositionen if kz for k in kz.komponenten}
    for key in sorted(keys):
        _vergleiche_summe(s, d, "komponenten", key, _summe(kz.komponenten.get(key) for kz in b.kompositionen if kz),
                          b.tag.komponenten.get(key), None)


def pruefe_summen(s: Summen, tag: KanalStundentag) -> None:
    """Σ der 24 Stunden gegen den Tag (S3-R4, berichtigt 15.10.): die Kategorien und die PV-Summe der Komposition je
    Stunde gegen die Tageskomposition, die Geräte-Schlüssel der Komposition, die Kanäle der Geräte- und WP-Gruppe gegen
    ihr Tages-Δ — alle streng; die Bilanz-Mengen der Adapter-Zeilen gegen den Kanal-Tag (``bilanz_leser.als_kanaltag``)
    streng bis auf ``speicher_netto`` (die Zeilenform verrechnet Ladung und Entladung derselben Stunde, H-2)."""
    if tag.bilanz is not None:
        _pruefe_bilanz(s, tag)
    for g, gs in tag.gruppen.items():
        if g == GRUPPE_BILANZ:
            continue
        for key, m in gs.mengen.items():
            z = gs.wahl.ergebnisse.get(key)
            _vergleiche_summe(s, tag.datum, g, key, _summe(m), z.delta if z is not None else None, None)


async def summen_tage(db: AsyncSession, aid: int, tage: list[date], *, jetzt: int) -> Summen:
    s = Summen()
    for d in tage:
        tag = await kanal_stundentag(db, aid, d, jetzt=jetzt)
        if tag.gruppen:
            pruefe_summen(s, tag)
    return s


__all__ = ["Bericht", "KLASSEN", "Summen", "bestand_zeilen", "klasse", "probe_tage", "pruefe_summen", "summen_tage",
           "vergleiche_tag"]
