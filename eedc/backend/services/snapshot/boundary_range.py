"""
Typed Range über Snapshot-Boundaries (Etappe 3c P2, KONZEPT-ENERGIEPROFIL-3C.md).

Kapselt die Backward-Konvention nach Issue #144 für Hourly-Slots
und das HA-konforme Tagesfenster für Boundary-Diff-Tagesgesamt.
Konsumenten dürfen Slot-Indices nicht selbst rechnen — sie iterieren über
`boundary_offsets` und `slot_pairs`, lesen Snapshots an `boundary_at(offset)`
und nehmen für jeden Slot das Tupel `(slot_idx, prev_offset, curr_offset)`.

Backward-Konvention #144 (Slot 0..23):
    Snapshots @ Vortag 23:00, Heute 00:00, ..., Heute 23:00 → 25 Boundaries
    Slot h = snap[curr=h] − snap[prev=h-1]                  → 24 Slots
    Slot 0  = Energie [Vortag 23:00, Heute 00:00)
    Slot 23 = Energie [Heute 22:00, Heute 23:00)

HA-Tagesgesamt (Boundary-Diff über [Heute 00:00, Folgetag 00:00)):
    Snapshots @ Heute 00:00, Folgetag 00:00 → 2 Boundaries
    Tagesgesamt = snap[24] − snap[0]

Beide Fenster sind 24 Stunden lang, aber semantisch verschieden — Konsumenten
dürfen nicht erwarten, dass `Σ slot[0..23] == Tagesgesamt` ist (Slot-Σ deckt
[Vortag-23, Heute-23) ab, nicht [Heute-00, Folgetag-00)).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

#: Die Herkunfts-Kennung einer Tageszeile, deren Werte aus den HA-LTS-Stunden
#: stammen (Σ der 24 Rückwärts-Slots). **Eine Konstante für Schreiber und
#: Leser** (N-434): Der Energieprofil-Aggregator schreibt sie, die Tagessichten
#: lesen an ihr ab, in welchem Fenster `komponenten_kwh` steht. Zwei Literale
#: wären die F-56-Klasse — benennt jemand die Kennung um, läse der Leser still
#: das falsche Fenster.
TZ_QUELLE_LTS: str = "external:ha_statistics:daily"

#: Präfix der Wärmepumpen-Schlüssel in `komponenten_kwh` bzw. ihrer Provenance.
_WP_PROVENANCE_PRAEFIX = "komponenten_kwh.waermepumpe_"


def tageszeile_ist_rueckwaerts(
    source_provenance: Optional[dict[str, Any]],
    verworfen: Optional[dict[str, Any]] = None,
) -> bool:
    """Steht der Wärmepumpen-Tagesstrom dieser Tageszeile im Rückwärtsfenster?

    ``True``, wenn

    * die Zeile die **Regelmarke** trägt (``verworfen is not None``, Zählerlücken
      wie HA R9/E5): seit dem Umbau ist `komponenten_kwh` in **beiden** Pfaden
      Σ der Stunden-Slots [Vortag 23:00, Heute 23:00) — auch im Snapshot-Pfad
      (Standalone), der vorher im Kalendertag rechnete. Ohne diesen Schalter
      läsen die vier WP-Sichten die Teilmengen eines Standalone-Tages im
      falschen Fenster („2,23 statt 4,04"-Klasse, Ü1); **oder**
    * ein ``komponenten_kwh.waermepumpe_*``-Eintrag die Quelle
      {@link TZ_QUELLE_LTS} trägt (N-434) — dann ist der Wert Σ der LTS-Slots,
      auch bei einer Zeile von vor dem Umbau.

    Jede Teilmenge desselben Geräts muss dann über
    {@link BoundaryRange.for_day_backward} gelesen werden.

    ``False`` sonst — auch ohne Provenance und ohne Marke (Snapshot-Altbestand,
    Fixture): dann gilt das bisherige Tagesfenster [00:00, 24:00). Eine Zeile
    ohne Angabe wird nicht umgedeutet.
    """
    if verworfen is not None:
        return True
    if not isinstance(source_provenance, dict):
        return False
    for key, eintrag in source_provenance.items():
        if not str(key).startswith(_WP_PROVENANCE_PRAEFIX):
            continue
        if isinstance(eintrag, dict) and eintrag.get("source") == TZ_QUELLE_LTS:
            return True
    return False


@dataclass(frozen=True)
class BoundaryRange:
    """Typed Range über Snapshot-Zeitstempel für eine bestimmte Aggregat-Variante."""

    datum: date
    boundary_offsets: tuple[int, ...]
    """Stunden-Offsets relativ zu `datum` 00:00, an denen Snapshots gelesen werden."""

    slot_pairs: tuple[tuple[int, int, int], ...]
    """Liste von `(slot_idx, prev_offset, curr_offset)` für die Slot-Aggregation.

    Leer für `for_day_total` — dort `boundary_offsets` direkt nutzen.
    """

    @classmethod
    def for_hourly_slots(cls, datum: date) -> "BoundaryRange":
        """Backward-Hourly nach Issue #144.

        25 Boundaries (offsets `-1..23`), 24 Slots (`0..23`).
        Slot h = `snap[curr=h] − snap[prev=h-1]`.
        Slot 0 = Energie [Vortag 23:00, Heute 00:00).
        """
        return cls(
            datum=datum,
            boundary_offsets=tuple(range(-1, 24)),
            slot_pairs=tuple((h, h - 1, h) for h in range(24)),
        )

    @classmethod
    def for_day_backward(cls, datum: date) -> "BoundaryRange":
        """Tagesgesamt über das **Rückwärtsfenster** — dasselbe wie Σ der Slots.

        2 Boundaries (offsets `-1` und `23`).
        Tagesgesamt = `snap[23] − snap[-1]` = Energie [Vortag 23:00, Heute 23:00).

        ⭐ **Warum es dieses Fenster als Tageswert gibt (N-434, 11.09.2026).** Im
        HA-Add-on entsteht `TagesZusammenfassung.komponenten_kwh` als Σ der 24
        LTS-Slots (`get_komponenten_tageskwh_lts`) — also in DIESEM Fenster, nicht
        in [00:00, 24:00). Wer einen zweiten Zähler desselben Geräts als Teilmenge
        dagegenstellt (die gemessenen Betriebsart-Zähler), muss ihn im selben
        Fenster lesen. Sonst erscheint die Differenz zweier Randstunden als
        Messung: 1,8 von 7,0 kWh „nicht aufgeteilt" bei einem Gerät, das nur
        heizt — oder die Aufteilung verschwindet, weil die Teilmenge größer
        wirkt als ihr Ganzes. Welches Fenster eine Tageszeile trägt, sagt
        {@link tageszeile_ist_rueckwaerts}.
        """
        return cls(
            datum=datum,
            boundary_offsets=(-1, 23),
            slot_pairs=(),
        )

    @classmethod
    def for_day_total(cls, datum: date) -> "BoundaryRange":
        """HA-konformer Tagesgesamt-Range.

        2 Boundaries (offsets `0` und `24`).
        Tagesgesamt = `snap[24] − snap[0]` = Energie [Heute 00:00, Folgetag 00:00).
        Wird in Päckchen 3 (E2) primärer Truth-Pfad für TagesZusammenfassung-Felder.
        """
        return cls(
            datum=datum,
            boundary_offsets=(0, 24),
            slot_pairs=(),
        )

    def boundary_at(self, offset: int) -> datetime:
        """Zeitstempel für einen Boundary-Offset (Stunden seit `datum` 00:00)."""
        return datetime.combine(self.datum, datetime.min.time()) + timedelta(hours=offset)


#: Welches Tagesfenster ein Gerätetyp trägt — **die eine Tabelle** (SOLL §3.3/S1a).
#:
#: ``"rueckwaerts"`` = immer [Vortag 23:00, Heute 23:00) · ``"bedingt"`` = das
#: Fenster der Tageszeile (``tageszeile_ist_rueckwaerts``) · ein Typ, der hier
#: **fehlt**, bekommt [00:00, 24:00) — bitgleich zu vor N-444.
#:
#: ⛔ **Ein neuer Typ in ``TAGESDETAIL_AUSGABE`` gehört hierher**, und zwar
#: bewusst: ``test_n444_tagesdetail_ein_fenster.py::TestJederTypHatEinFenster``
#: verlangt für jeden dort vorkommenden Typ einen Eintrag. Der stille Default
#: soll niemanden treffen, der ein Feld hinzufügt, ohne über sein Fenster
#: nachgedacht zu haben.
TAGESFENSTER_JE_TYP: dict[str, str] = {
    # Bezug: `TagesZusammenfassung.komponenten_kwh` — sein Fenster hängt an der
    # HERKUNFT der Tageszeile (HA-Add-on: Σ der LTS-Slots ⇒ rückwärts;
    # Snapshot-Pfad: [00:00, 24:00)). Quelle: `energie_profil/aggregator.py`
    # schreibt die Provenance, `tageszeile_ist_rueckwaerts` liest sie.
    "waermepumpe": "bedingt",
    # Bezug: `Σ max(0, −batterie_kw)` über die 24 Stundenzeilen —
    # `core/berechnungen/tagesbilanz.py::bilanz_aus_stundenrows`, ausgeliefert
    # über `services/energie_profil/tage_werte.py`. Die Stundenzeile liegt seit
    # N-382 IMMER rückwärts (`core/berechnungen/slot_konvention.py`).
    "speicher": "rueckwaerts",
    # Bezug: Σ der Wallbox-/E-Auto-Serien aus `TagesEnergieProfil.komponenten` —
    # gebucketet mit `slot_konvention.leistungspfad_slot`
    # (`services/energie_profil/aggregator.py`), gelesen in
    # `frontend/src/v4/TagKomponenten.tsx`. Ebenfalls immer rückwärts.
    "wallbox": "rueckwaerts",
    "e-auto": "rueckwaerts",
}


def tagesfenster_fuer(
    typ: Optional[str], datum: date, *, tageszeile_rueckwaerts: bool
) -> BoundaryRange:
    """Das Tagesfenster, in dem der Tageswert dieses Gerätetyps steht (N-444).

    ⛔ **Warum es diese Funktion gibt (SOLL §3.3/S1a, abgenommen 12.09.2026).**
    Jede Teilmenge, jeder Anteil und jeder Quotient einer Tagessicht wird in dem
    Fenster erhoben, in dem **der Bezug dieser Zeile** steht. Der Bezug ist je
    Gerätetyp verschieden — und darum ist die Regel **nicht** „alle rückwärts":

    ======================  ====================================  ==================
    Typ                     Bezug der Tageszeile                  Fenster
    ======================  ====================================  ==================
    ``waermepumpe``         ``TagesZusammenfassung.komponenten_    **bedingt** —
                            kwh`` (``energie_profil/              ``tageszeile_ist_
                            aggregator.py`` schreibt, N-434)      rueckwaerts``
    ``speicher``            ``Σ max(0, −batterie_kw)``            **immer**
                            (``core/berechnungen/tagesbilanz.py``  rückwärts
                            über ``energie_profil/tage_werte.py``)
    ``wallbox`` /           ``Σ`` der Serien aus ``TagesEnergie    **immer**
    ``e-auto``              Profil.komponenten`` (``energie_       rückwärts
                            profil/aggregator.py`` nach ``slot_
                            konvention.leistungspfad_slot``)
    *unbekannt*             — (kein Tages-Bezug bekannt)          ``[00:00, 24:00)``
    ======================  ====================================  ==================

    **Der Unterschied zwischen „bedingt" und „immer" ist gemessen, nicht
    stilistisch.** Bei der Wärmepumpe hängt das Fenster des Bezugs am
    Deployment: im HA-Add-on ist ``komponenten_kwh`` die Σ der 24 LTS-Slots
    (rückwärts), im Snapshot-Pfad steht dort [00:00, 24:00). Bei Speicher und
    E-Mobilität hängt der Bezug an den **Stundenzeilen**, und die liegen seit
    N-382 unbedingt rückwärts — der Versatz ist dort in **jeder** Installation
    da. Ein unbedingter Schalter über alle Typen machte die Arbeitszahl im
    Snapshot-Pfad wieder falsch (``test_n435_tages_jaz_ein_fenster.py::
    test_snapshot_tag_bleibt_im_tagesfenster``).

    **Was der Versatz anrichtet** (Demo-DB, 12.09.2026): an 18 von 182 Tagen
    weicht die Speicher-Ladung zwischen den beiden Fenstern um mehr als 5 % ab,
    am 25.11.2025 um +131,9 % (1,11 gegen 2,58 kWh). Der Zähler
    ``ladung_netz_kwh`` konnte damit größer sein als sein eigener Bezug — im
    Client still auf 100 % gekappt (``Math.min(1, …)``).

    ⚑ **Der nächste Leser ist der Bereichs-Leser.**
    ``services/snapshot/bereichs_leser.py::lade_tageswerte_je_feld`` trägt
    heute ``rueckwaerts_tage`` **je Tag**, nicht je Typ — das genügt, solange
    ihm sein einziger Aufrufer (``energie_profil/waerme_verlauf.py``) nur
    Wärme-/Kälte-Felder hereinreicht. Sobald ein Aufrufer Typen **mischt**,
    braucht er dieselbe Tabelle; er wird dann hierher umgehängt und nicht mit
    einer zweiten Weiche versehen (F-56). ⛔ In N-444 **nicht** umgebaut: es
    gibt keinen Konsumenten.

    Args:
        typ: ``Investition.typ``. Unbekannt/``None`` ⇒ ``for_day_total``.
        datum: der Tag, dessen Fenster gefragt ist.
        tageszeile_rueckwaerts: Ergebnis von {@link tageszeile_ist_rueckwaerts}
            für **dieselbe** Tageszeile, aus der der Aufrufer seinen Bezug nimmt.
    """
    modus = TAGESFENSTER_JE_TYP.get(typ or "")
    if modus == "rueckwaerts" or (modus == "bedingt" and tageszeile_rueckwaerts):
        return BoundaryRange.for_day_backward(datum)
    return BoundaryRange.for_day_total(datum)
