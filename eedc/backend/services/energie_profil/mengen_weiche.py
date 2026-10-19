"""Die Mengen-Weiche des Schreibers — an einem Kanal-Tag schreibt ``aggregate_day`` keine gefalteten Mengen
(HA-Bauform S5, Etappe E-S5-3; Bauplan S5 §4 **S5-R2**, §3 (B), §10h 1–5).

**Was die Weiche entscheidet.** Seit S5a liest jede Sicht, Kennzahl und Checker-Regel die Mengen eines Kanal-Tags aus den
Kanälen (Mischzeilen ``kanal_stunden.stunden_der_tage``, Tageskomponenten ``komponenten_der_tage``, Überschuss/Defizit
``ueberschuss_defizit_der_tage``). Die gefalteten Mengen der Stunden- und Tageszeile hätten dort keinen Leser mehr — sie
zu schreiben wäre die Driftquelle selbst (Konzept §7, S5-E3). Die Weiche nennt je Tag, was leer bleibt:

* **Kanal-Tag** = Tag, dessen Bilanz-Gruppe Wahl ``kanal`` hat (``bilanz_leser.kanal_tage``, derselbe Begriff wie die
  Leser). An einem anderen Tag leert die Weiche nichts — der Bestand schreibt wie bisher (Lesart 1, S5-R3).
* An einem Kanal-Tag **je Gruppe mit Wahl ``kanal``** (Bilanz immer; Wärmepumpe, E-Mobilität, Sonstiges nach ihrer
  eigenen Tageswahl): die TEP-Mengen-Spalten der Gruppe (``kanal/stunden_adapter.FELDER_JE_GRUPPE``), ihre Achsen in
  ``spannen`` (``kanal_stunden.ACHSEN_JE_GRUPPE``, S5-R5), die TZ-Felder ``ueberschuss_kwh``/``defizit_kwh`` (Bilanz), ihre
  Schlüssel in ``komponenten_kwh`` (genau die Schlüssel, die die Lesestelle aus dem Kanal nimmt: Bilanz
  ``ist_bilanz_schluessel`` wie ``mische_komponenten``, Wärmepumpe und Sonstiges die Ziel-Schlüssel ihrer Zähler mit
  Tageswert, die E-Mobilität ihr ganzer Präfix ``wallbox_*``/``eauto_*`` — Wallbox-Regel N-555),
  ihre Achsen in ``verworfen`` (die Regelmarke ``{}`` bleibt — R9, E7) und in ``nachtrag``.
* **Was bleibt:** die Bahnen der Stundenzeile (SoC, Preise, Wetter, Leistungspfad ``komponenten``, Zählwerke,
  Betriebsart — S5-R4) und die Kennzahlen der Tageszeile (Peaks, Vollzyklen, Wetter, Börse). Die drei
  **Mengen-Ableitungen** ``performance_ratio``, ``einspeisung_neg_preis_kwh`` und ``emob_ladung_*_abgeleitet_kwh`` bleiben
  in der Zeile — an einem Kanal-Tag aus den Kanal-Stunden gerechnet (``kanal_stunden.performance_ratio_des_kanal_tags``,
  ``einspeisung_neg_preis_der_kanal_stunden``, ``ladeanteil_der_kanal_stunden``; die E-Mob-Ableitung nur, wenn auch die
  E-Mob-Gruppe Wahl ``kanal`` hat).

**Eine Anwendung, nach dem Bauen.** ``aggregate_day`` baut die Zeilen wie immer (kein Zweig in ``verrechne_stunde``
oder ``baue_*``) und gibt sie vor dem Schreiben durch die Weiche: jede Stundenzeile vor ``db.add`` (``Weiche.stunde``),
die Tageszeile vor Provenance und Restore (``Weiche.tageszeile``) — damit gewinnt die Weiche auch über die
Preserve-Logik (ein ``MANUAL_REPAIR`` holt an einem Kanal-Tag keine alten Bilanz-Schlüssel zurück).

**Richtung: die Wahl zum Schreibzeitpunkt, in beide Richtungen** (§10h 3). Die Wahl kommt aus ``kanal_stundentag`` mit
der Uhr der Lese-Schicht — am laufenden Tag die Wahl bis zur fälligen Stunde. Verliert ein Tag seine Kanal-Deckung (Quelle
verworfen, Zuordnung entfernt), schreibt die nächste Aggregation wieder Mengen.

**Herkunft** (§10h 4): die Tageszeile eines Kanal-Tags trägt ``boundary_range.TZ_QUELLE_KANAL`` als Provenance-Quelle,
die geleerten Gruppen im Eintrag (``gruppen``); ``datenquelle`` bleibt der Trigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

#: Die TZ-Felder der Bilanz, die an einem Kanal-Tag leer bleiben (die Lesestelle ist ``ueberschuss_defizit_der_tage``).
TZ_FELDER_BILANZ: tuple[str, ...] = ("ueberschuss_kwh", "defizit_kwh")


def _ohne_achsen(werte: Optional[dict], achsen: frozenset[str]) -> Optional[dict]:
    """Ein ``{achse: …}``-Dict (``spannen``, ``verworfen``, ``nachtrag``) ohne die Achsen ``achsen`` — ``None``, wenn nichts
    bleibt."""
    rest = {a: v for a, v in (werte or {}).items() if a not in achsen}
    return rest or None


@dataclass(frozen=True)
class Weiche:
    """Was ``aggregate_day`` an einem Tag leer lässt (``mengen_weiche``). Ohne Gruppen: Bestandstag, die Weiche ist ohne
    Wirkung."""

    #: Die Gruppen, deren Mengen leer bleiben (Ordnung Bilanz, Wärmepumpe, E-Mobilität, Sonstiges) — ``()``: Bestandstag.
    gruppen: tuple[str, ...] = ()
    #: Der Kanal-Stundentag (``kanal_stundentag``) und seine Stunden (``stunden_aus_kanaelen``, die Werte der
    #: Mischzeilen), aus denen die Kennzahlen kommen.
    tag: Any = None
    stunden: Any = None
    tep_spalten: frozenset[str] = frozenset()
    achsen: frozenset[str] = frozenset()
    #: Die Ziel-Schlüssel der Bilanz-Zähler (``bilanz_leser.bilanz_ziele``) — ``None``: die Bilanz bleibt.
    bilanz_ziele: Optional[frozenset[str]] = None
    #: Die ``komponenten_kwh``-Schlüssel der Geräte-Gruppen mit Wahl ``kanal`` (Wärmepumpe, Sonstiges).
    geraete_schluessel: frozenset[str] = frozenset()
    #: Die Präfixe einer Gruppe, der der ganze Präfix gehört — die E-Mobilität (``wallbox_*``/``eauto_*``, Wallbox-Regel
    #: N-555; ``kanal_stunden._ohne_emob``).
    praefixe: tuple[str, ...] = ()

    def leerer_schluessel(self, key: str) -> bool:
        """Kommt der ``komponenten_kwh``-Schlüssel an diesem Tag aus dem Kanal (und bleibt in der Tageszeile leer)?"""
        if key in self.geraete_schluessel or (self.praefixe and str(key).startswith(self.praefixe)):
            return True
        if self.bilanz_ziele is None:
            return False
        from backend.services.kanal.bilanz_leser import ist_bilanz_schluessel

        return ist_bilanz_schluessel(key, self.bilanz_ziele)

    def stunde(self, profil) -> None:
        """Die Mengen-Spalten und Achsen der Gruppen in einer fertig gebauten Stundenzeile leeren (vor ``db.add``)."""
        if not self.gruppen:
            return
        for spalte in self.tep_spalten:
            setattr(profil, spalte, None)
        profil.spannen = _ohne_achsen(profil.spannen, self.achsen)

    def tageszeile(self, zusammenfassung, *, anlage, invs, gti_summe: float, boerse, lade_anteil,
                   tz_source_label: str) -> tuple[Any, str]:
        """Die Tageszeile eines Kanal-Tags (vor Provenance und Restore): Mengen der Gruppen leer, die drei
        Mengen-Ableitungen aus den Kanal-Stunden, Herkunft ``TZ_QUELLE_KANAL``. Rückgabe ``(lade_anteil, tz_source_label)``
        für ``schreibe_provenance_und_restore``; an einem Bestandstag unverändert."""
        if not self.gruppen:
            return lade_anteil, tz_source_label
        from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
        from backend.services.energie_profil.kanal_stunden import (
            GRUPPE_EMOB, einspeisung_neg_preis_der_kanal_stunden, ladeanteil_der_kanal_stunden,
            performance_ratio_des_kanal_tags,
        )
        from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

        z = zusammenfassung
        for feld in TZ_FELDER_BILANZ:
            setattr(z, feld, None)
        z.komponenten_kwh = {k: v for k, v in (z.komponenten_kwh or {}).items() if not self.leerer_schluessel(k)} or None
        z.verworfen = _ohne_achsen(z.verworfen, self.achsen) or {}
        z.nachtrag = _ohne_achsen(z.nachtrag, self.achsen)
        # ``self.stunden``: die Kanal-Stunden in der Form der Mischzeilen (drei Stellen, wie ``/stunden`` sie zeigt).
        kwp = anlagen_kwp(invs, z.datum, mit_bkw=True, referenzwert=anlage.leistung_kwp)
        z.performance_ratio = performance_ratio_des_kanal_tags(self.tag, self.stunden, gti_summe, kwp)
        z.einspeisung_neg_preis_kwh = einspeisung_neg_preis_der_kanal_stunden(self.stunden, boerse)
        if GRUPPE_EMOB in self.gruppen:
            lade_anteil = ladeanteil_der_kanal_stunden(self.stunden)
            z.emob_ladung_pv_abgeleitet_kwh = lade_anteil.pv_kwh if lade_anteil is not None else None
            z.emob_ladung_netz_abgeleitet_kwh = lade_anteil.netz_kwh if lade_anteil is not None else None
            z.emob_ladung_speicher_abgeleitet_kwh = lade_anteil.speicher_kwh if lade_anteil is not None else None
        # Transienter Marker (nicht gemappt) wie ``komponenten_frisch``: die Werkbank-Rückmeldung nennt die leeren Gruppen.
        z.mengen_weiche = self
        return lade_anteil, TZ_QUELLE_KANAL

    def herkunft(self, zusammenfassung) -> None:
        """Die geleerten Gruppen in jeden Provenance-Eintrag mit Quelle ``TZ_QUELLE_KANAL`` (nach dem Seed)."""
        if not self.gruppen:
            return
        from sqlalchemy.orm.attributes import flag_modified

        from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

        prov = dict(zusammenfassung.source_provenance or {})
        for feld, eintrag in prov.items():
            if isinstance(eintrag, dict) and eintrag.get("source") == TZ_QUELLE_KANAL:
                prov[feld] = {**eintrag, "gruppen": list(self.gruppen)}
        zusammenfassung.source_provenance = prov
        flag_modified(zusammenfassung, "source_provenance")


#: Der Bestandstag — die Weiche ohne Wirkung.
KEINE_WEICHE = Weiche()


def _geraete_schluessel(tag, gruppen: tuple[str, ...]) -> frozenset[str]:
    """Die ``komponenten_kwh``-Schlüssel der Geräte-Gruppen: die Ziel-Schlüssel ihrer Zähler mit Tageswert — dieselben
    Schlüssel, die ``kanal_stunden.geraete_komponenten_der_kanal_tage`` aus dem Kanal liefert."""
    from backend.services.energie_profil.kanal_stunden import _tages_delta

    out: set[str] = set()
    for g in gruppen:
        gs = tag.gruppen[g]
        delta = _tages_delta(gs)
        out |= {e.target_key for e in gs.eintraege if e.schluessel in delta}
    return frozenset(out)


async def mengen_weiche(db, anlage, datum: date) -> Weiche:
    """**Die Mengen-Weiche eines Tages** — EIN Kanal-Stundentag (``kanal_stunden.kanal_stunden``, Uhr der Lese-Schicht).
    Kein Kanal-Tag der Bilanz ⇒ ``KEINE_WEICHE``."""
    from backend.services.energie_profil.kanal_stunden import (
        ACHSEN_JE_GRUPPE, FELDER_JE_GRUPPE, GRUPPE_BILANZ, GRUPPE_EMOB, GRUPPE_SONSTIGES, GRUPPE_WP, kanal_stunden,
    )
    from backend.core.berechnungen.energie import WALLBOX_KOMPONENTEN_PREFIXE
    from backend.services.kanal.bilanz_leser import bilanz_ziele

    k = await kanal_stunden(db, anlage.id, datum)
    if k is None or GRUPPE_BILANZ not in k[0].gruppen:
        return KEINE_WEICHE
    tag, ks = k
    gruppen = tuple(g for g in (GRUPPE_BILANZ, GRUPPE_WP, GRUPPE_EMOB, GRUPPE_SONSTIGES) if g in tag.gruppen)
    return Weiche(
        gruppen=gruppen, tag=tag, stunden=ks,
        tep_spalten=frozenset(f for g in gruppen for f in FELDER_JE_GRUPPE.get(g, ())),
        achsen=frozenset(a for g in gruppen for a in ACHSEN_JE_GRUPPE.get(g, ())),
        bilanz_ziele=frozenset((await bilanz_ziele(db, anlage.id, [datum]))[datum]),
        geraete_schluessel=_geraete_schluessel(tag, tuple(g for g in gruppen[1:] if g != GRUPPE_EMOB)),
        praefixe=WALLBOX_KOMPONENTEN_PREFIXE if GRUPPE_EMOB in gruppen else (),
    )


__all__ = ["KEINE_WEICHE", "TZ_FELDER_BILANZ", "Weiche", "mengen_weiche"]
