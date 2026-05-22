"""Konsistenz-Invarianten zwischen den zentralen Aggregat-Tabellen.

Werden im Aggregator (`energie_profil/aggregator.py::aggregate_day`) am
Ende eines Schreib-Laufs aufgerufen, damit eine Drift sofort beim Schreiben
sichtbar wird — nicht erst, wenn ein Anwender sie meldet (BKW-Bug-Klasse,
Rainer-PN 2026-05-19).

Zwei API-Varianten pro Invariante:
- `pruefe_*` → liefert einen Bericht (Bool + Details), für Diagnose/UI
- `assert_*` → wirft AssertionError mit Bericht, für Tests/CI

Der Aggregator nutzt `pruefe_*` und loggt Warnungen — er soll keinen Tag
verloren gehen lassen, weil eine Invariante verletzt ist. Tests nutzen
`assert_*`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from backend.core.berechnungen.energie import summe_pv_bkw_kwh


@dataclass
class KonsistenzBericht:
    """Ergebnis einer Konsistenz-Prüfung."""
    konsistent: bool
    name: str
    erwartet: float
    tatsaechlich: float
    toleranz_kwh: float
    details: str = ""

    @property
    def abweichung_kwh(self) -> float:
        return abs(self.tatsaechlich - self.erwartet)

    def __str__(self) -> str:
        status = "✓" if self.konsistent else "✗"
        return (
            f"{status} {self.name}: erwartet={self.erwartet:.3f} kWh, "
            f"tatsächlich={self.tatsaechlich:.3f} kWh, "
            f"Δ={self.abweichung_kwh:.3f} kWh (Toleranz {self.toleranz_kwh:.3f})"
            f"{' — ' + self.details if self.details else ''}"
        )


def pruefe_tep_tz_konsistenz(
    tep_rows: Iterable,
    tz_komponenten_kwh: Optional[dict],
    toleranz_kwh: float = 0.5,
) -> KonsistenzBericht:
    """Prüft: Σ TagesEnergieProfil.pv_kw == summe_pv_bkw_kwh(tz.komponenten_kwh).

    Args:
        tep_rows: Iterable von TagesEnergieProfil-Rows (24 Stunden eines Tages)
        tz_komponenten_kwh: Das JSON-Feld aus TagesZusammenfassung.komponenten_kwh
        toleranz_kwh: Akzeptierte Abweichung (Default 0.5 kWh; Rundung auf 3
                      Stellen + Stunden-Riemann-Drift bei sub-stündlichen Punkten)

    Die Invariante kommt aus Etappe 4 (HA-LTS als SoT): wenn `aggregate_day`
    sauber arbeitet, müssen Stunden-Σ und Tages-Σ identisch sein. Verletzung
    deutet auf einen parallelen Schreibpfad (BKW-Klasse).
    """
    summe_tep = sum(
        (row.pv_kw or 0.0) for row in tep_rows
        if getattr(row, "pv_kw", None) is not None
    )
    summe_tz = summe_pv_bkw_kwh(tz_komponenten_kwh)

    abweichung = abs(summe_tep - summe_tz)
    konsistent = abweichung <= toleranz_kwh

    details = ""
    if not konsistent:
        details = (
            "Drift zwischen Stunden-Pfad (TagesEnergieProfil.pv_kw) und "
            "Tages-Pfad (komponenten_kwh PV+BKW). Mögliche Ursache: "
            "paralleler Schreibpfad mit Schema-Mismatch (siehe Memory "
            "feedback_aggregations_drift)."
        )

    return KonsistenzBericht(
        konsistent=konsistent,
        name="Σ TagesEnergieProfil.pv_kw == Σ komponenten_kwh[pv_*, bkw_*]",
        erwartet=summe_tep,
        tatsaechlich=summe_tz,
        toleranz_kwh=toleranz_kwh,
        details=details,
    )


def assert_tep_tz_konsistent(
    tep_rows: Iterable,
    tz_komponenten_kwh: Optional[dict],
    toleranz_kwh: float = 0.5,
) -> None:
    """Wirft AssertionError wenn `pruefe_tep_tz_konsistenz` fehlschlägt."""
    bericht = pruefe_tep_tz_konsistenz(tep_rows, tz_komponenten_kwh, toleranz_kwh)
    if not bericht.konsistent:
        raise AssertionError(str(bericht))


def pruefe_speicher_ladung_konsistenz(
    ladung_kwh: Optional[float],
    ladung_netz_kwh: Optional[float],
    toleranz_kwh: float = 0.1,
) -> KonsistenzBericht:
    """Prüft: ladung_netz_kwh ≤ ladung_kwh (Netzladung ist Teilmenge der Gesamtladung).

    Vertrag aus Issue #281: `ladung_kwh` eines Speichers ist die Gesamt-
    ladung (PV + Netz), `ladung_netz_kwh` der daraus stammende Netz-Anteil.
    Der implizite PV-Anteil `ladung_kwh − ladung_netz_kwh` darf nie negativ
    werden — sonst ist eine der beiden Zahlen falsch erfasst (z. B. Netz-
    Counter in den Gesamt-Slot gemappt, oder `ladung_kwh` versehentlich als
    reine PV-Ladung gepflegt).

    Args:
        ladung_kwh: Gesamtladung des Speichers in kWh (PV + Netz)
        ladung_netz_kwh: Netz-Anteil der Ladung in kWh
        toleranz_kwh: Akzeptierte Überschreitung (Default 0.1 kWh — Rundung)

    `None` wird als 0.0 gewertet. Reine PV-Speicher (Netz = 0) sind immer
    konsistent.

    HINWEIS: gilt für in sich geschlossene Werte. Auf eine über Monate
    HA-aggregierte Reihe NICHT pro Monat anwenden — dort ist ein kleiner
    Überhang durch Zähler-Schnappschüsse an der Monatsgrenze legitim; nutze
    dafür `pruefe_speicher_netzladung_kumulativ`.
    """
    gesamt = float(ladung_kwh or 0.0)
    netz = float(ladung_netz_kwh or 0.0)
    konsistent = netz <= gesamt + toleranz_kwh

    details = ""
    if not konsistent:
        details = (
            f"Netzladung ({netz:.3f} kWh) übersteigt die Gesamtladung "
            f"({gesamt:.3f} kWh) — der implizite PV-Anteil "
            f"(ladung_kwh − ladung_netz_kwh) wäre negativ. Mögliche Ursache: "
            "Netz-Sensor in den Gesamt-Ladung-Slot gemappt, oder `ladung_kwh` "
            "als reine PV-Ladung statt Gesamtladung gepflegt (Issue #281)."
        )

    return KonsistenzBericht(
        konsistent=konsistent,
        name="ladung_netz_kwh ≤ ladung_kwh (Speicher: Netz ⊆ Gesamt)",
        erwartet=gesamt,
        tatsaechlich=netz,
        toleranz_kwh=toleranz_kwh,
        details=details,
    )


def assert_speicher_ladung_konsistent(
    ladung_kwh: Optional[float],
    ladung_netz_kwh: Optional[float],
    toleranz_kwh: float = 0.1,
) -> None:
    """Wirft AssertionError wenn `pruefe_speicher_ladung_konsistenz` fehlschlägt."""
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh, ladung_netz_kwh, toleranz_kwh)
    if not bericht.konsistent:
        raise AssertionError(str(bericht))


def pruefe_speicher_netzladung_kumulativ(
    ladung_kwh_gesamt: Optional[float],
    ladung_netz_kwh_gesamt: Optional[float],
    toleranz_kwh: float = 0.1,
    toleranz_relativ: float = 0.02,
) -> KonsistenzBericht:
    """Prüft: Σladung_netz ≤ Σladung_kwh (kumulativ über die gesamte Historie).

    Wie bei `pruefe_speicher_ladung_konsistenz` ist `ladung_kwh` die Gesamt-
    ladung (PV + Netz), `ladung_netz_kwh` der Netz-Anteil. Die strikte
    Variante `ladung_netz ≤ ladung_kwh` gilt aber nur für in sich
    geschlossene Werte — NICHT pro Monat einer HA-aggregierten Reihe:

    Netz- und Gesamt-Ladungs-Zähler haben getrennte Monats-Schnappschüsse.
    Ein Ladevorgang über die Monatsgrenze (z. B. Netzladung bei niedrigem
    Tibber-Preis kurz nach Mitternacht) wird vom einen Zähler noch dem alten,
    vom anderen schon dem neuen Monat zugeschlagen. Der Überhang im einen
    Monat taucht im Nachbarmonat als Unterhang wieder auf — KUMULATIV gleicht
    er sich aus. Betrifft typisch Dezember/Januar (rapahl-PN 2026-05-22).

    Kumulativ ist `Σladung_netz > Σladung_kwh` daher ein echter Erfassungs-
    fehler: Netz-Sensor in den Gesamt-Ladung-Slot gemappt, oder `ladung_kwh`
    als reine PV-Ladung statt Gesamtladung gepflegt (Issue #281).

    Args:
        ladung_kwh_gesamt: Summe aller Monats-Gesamtladungen in kWh
        ladung_netz_kwh_gesamt: Summe aller Monats-Netzladungen in kWh
        toleranz_kwh: Akzeptierte absolute Überschreitung (Rundung)
        toleranz_relativ: Akzeptierte relative Überschreitung (Default 2 %) —
            deckt den einen, am Rand des Datenfensters noch nicht durch einen
            Nachbarmonat ausgeglichenen Monatsübergang ab.

    `None` wird als 0.0 gewertet.
    """
    gesamt = float(ladung_kwh_gesamt or 0.0)
    netz = float(ladung_netz_kwh_gesamt or 0.0)
    erlaubt = toleranz_kwh + toleranz_relativ * gesamt
    konsistent = netz <= gesamt + erlaubt

    details = ""
    if not konsistent:
        details = (
            f"Kumulierte Netzladung ({netz:.3f} kWh) übersteigt die kumulierte "
            f"Gesamtladung ({gesamt:.3f} kWh) — über die gesamte Historie "
            "unmöglich. Ein einzelner Monat darf das (Zähler-Schnappschuss an "
            "der Monatsgrenze), die Summe nicht. Mögliche Ursache: Netz-Sensor "
            "in den Gesamt-Ladung-Slot gemappt, oder `ladung_kwh` als reine "
            "PV-Ladung statt Gesamtladung gepflegt (Issue #281)."
        )

    return KonsistenzBericht(
        konsistent=konsistent,
        name="Σladung_netz ≤ Σladung_kwh (Speicher: Netz ⊆ Gesamt, kumulativ)",
        erwartet=gesamt,
        tatsaechlich=netz,
        toleranz_kwh=erlaubt,
        details=details,
    )


def assert_speicher_netzladung_kumulativ(
    ladung_kwh_gesamt: Optional[float],
    ladung_netz_kwh_gesamt: Optional[float],
    toleranz_kwh: float = 0.1,
    toleranz_relativ: float = 0.02,
) -> None:
    """Wirft AssertionError wenn `pruefe_speicher_netzladung_kumulativ` fehlschlägt."""
    bericht = pruefe_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt, ladung_netz_kwh_gesamt, toleranz_kwh, toleranz_relativ
    )
    if not bericht.konsistent:
        raise AssertionError(str(bericht))


def pruefe_speicher_durchsatz_konsistenz(
    ladung_kwh_gesamt: Optional[float],
    entladung_kwh_gesamt: Optional[float],
    toleranz_kwh: float = 0.1,
) -> KonsistenzBericht:
    """Prüft: Σentladung ≤ Σladung (kumulativ über die gesamte Historie).

    Ein EINZELNER Monat darf legitim mehr ent- als laden — der SoC-Übertrag
    aus dem Vormonat fließt ab (Carry-over, siehe `core/berechnungen/speicher`).
    KUMULATIV über die gesamte Historie ist `Σentladung > Σladung` jedoch
    physikalisch unmöglich: man kann nie insgesamt mehr entnehmen, als je
    eingespeist wurde.

    Verletzung deutet auf fehlerhaft erfasste oder importierte Monatswerte
    (z. B. Lade-/Entlade-Spalte beim Übertrag aus dem HA-Energy-Dashboard
    vertauscht).

    `None` wird als 0.0 gewertet.
    """
    gesamt_ladung = float(ladung_kwh_gesamt or 0.0)
    gesamt_entladung = float(entladung_kwh_gesamt or 0.0)
    konsistent = gesamt_entladung <= gesamt_ladung + toleranz_kwh

    details = ""
    if not konsistent:
        details = (
            f"Kumulierte Entladung ({gesamt_entladung:.3f} kWh) übersteigt die "
            f"kumulierte Ladung ({gesamt_ladung:.3f} kWh) — über die gesamte "
            "Historie unmöglich. Ein einzelner Monat darf das (SoC-Übertrag), "
            "die Summe nicht. Mögliche Ursache: Lade-/Entlade-Werte fehlerhaft "
            "erfasst oder beim Datenübertrag vertauscht."
        )

    return KonsistenzBericht(
        konsistent=konsistent,
        name="Σentladung ≤ Σladung (Speicher: kumulativer Durchsatz)",
        erwartet=gesamt_ladung,
        tatsaechlich=gesamt_entladung,
        toleranz_kwh=toleranz_kwh,
        details=details,
    )


def assert_speicher_durchsatz_konsistent(
    ladung_kwh_gesamt: Optional[float],
    entladung_kwh_gesamt: Optional[float],
    toleranz_kwh: float = 0.1,
) -> None:
    """Wirft AssertionError wenn `pruefe_speicher_durchsatz_konsistenz` fehlschlägt."""
    bericht = pruefe_speicher_durchsatz_konsistenz(
        ladung_kwh_gesamt, entladung_kwh_gesamt, toleranz_kwh
    )
    if not bericht.konsistent:
        raise AssertionError(str(bericht))
