"""kWp-anteilige PV-Verteilung — Read-time-SoT (kWp-Verteilung-Etappe).

Multi-String-Anlagen mit nur EINEM Gesamt-PV-Wert (ein manuell eingetragenes
Aggregat in ``Monatsdaten.pv_erzeugung_kwh`` bzw. ein importiertes Gesamt-
Aggregat) bekommen die Erzeugung anteilig nach ``leistung_kwp`` auf die
einzelnen PV-Module/Strings aufgeschlüsselt — zur **Lesezeit**, nie als
geschriebener Wert (Design final, [[project_kwp_verteilung_aggregator]],
Anlass NongJoWo #289 + JayJayX #651).

Invariante: ``Monatsdaten.pv_erzeugung_kwh`` ist ein optionales, rein
manuelles/importiertes Aggregat und wird NIE programmatisch gefüllt. Die
Pro-Modul-Sicht wird aus Aggregat + im Monat aktiven Modulen deterministisch
neu gebildet — es gibt damit keine „historisch verteilten Werte" zum
Rekonstruieren.

Präzedenz (``resolve_pv_je_modul``):
  1. alle aktiven Module haben Pro-Modul-Werte → ``gemessen`` (wir glauben dem
     User; keine Provenance, kein Hinweis)
  2. sonst Aggregat gesetzt → nach kWp verteilen → ``verteilt``
  3. sonst → ``fehlt``

Σ-Invariante (Symmetrie-Test Pflicht, [[feedback_aggregator_symmetrie]]):
Σ der zurückgegebenen Pro-Modul-Werte == Gesamterzeugung — also == Summe der
gemessenen Werte (Fall 1) bzw. == Aggregat (Fall 2). Die Verteilung rundet
NICHT, damit die Summe exakt erhalten bleibt; Rundung ist Aufgabe der
Anzeige-Schicht.

Architektur-Anker: ADR-001 (core/berechnungen). 0-Werte gelten als Daten
(``is not None``, CLAUDE.md „0-Werte prüfen") — ein Aggregat von 0 (dunkler
Wintermonat) ist „verteilt", nicht „fehlt".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Herkunft eines aufgelösten Pro-Modul-Werts.
QUELLE_GEMESSEN = "gemessen"
QUELLE_VERTEILT = "verteilt"
QUELLE_FEHLT = "fehlt"

# Monats-Klassifikation für den Daten-Checker (Severity-Mapping beim Aufrufer).
STATUS_OK = "ok"                # vollständig gemessen → OK
STATUS_VERTEILT = "verteilt"    # Aggregat deckt ab → INFO
STATUS_TEIL_LUECKE = "teil_luecke"  # teilgemessen, kein Aggregat → WARNING
STATUS_FEHLT = "fehlt"          # gar keine PV-Quelle → ERROR


@dataclass(frozen=True)
class PvModul:
    """Eingabe: ein im Monat aktives PV-Modul.

    - ``inv_id``: Investitions-ID
    - ``leistung_kwp``: kWp für die Gewichtung (SoT-Wert via ``get_inv_value``)
    - ``eigen_kwh``: gemessener Pro-Modul-Wert aus den IMD; ``None`` = nicht
      erfasst (löst Aggregat-Verteilung aus, sobald nicht alle Module messen).
    """

    inv_id: int
    leistung_kwp: float
    eigen_kwh: Optional[float]


@dataclass(frozen=True)
class PvModulWert:
    """Ausgabe: aufgelöster Pro-Modul-Wert + Herkunft."""

    inv_id: int
    pv_erzeugung_kwh: float
    quelle: str  # QUELLE_GEMESSEN | QUELLE_VERTEILT | QUELLE_FEHLT


def verteile_basis_kwh_nach_kwp(
    basis_kwh: float,
    module: list[tuple[int, float]],
) -> dict[int, float]:
    """Verteilt ``basis_kwh`` anteilig nach kWp auf die Module.

    Args:
        basis_kwh: Gesamt-Erzeugung, die verteilt werden soll.
        module: ``[(inv_id, leistung_kwp), …]``.

    Returns:
        ``{inv_id: kwh}`` mit ``Σ == basis_kwh``. Fallback bei ``Σ kWp == 0``:
        Gleichverteilung (#229-Muster, repliziert aus import_export/helpers.py).
        Leere Modul-Liste → ``{}``. Es wird NICHT gerundet (Summen-Treue).
    """
    if not module:
        return {}
    total_kwp = sum(max(0.0, kwp or 0.0) for _, kwp in module)
    if total_kwp > 0:
        return {
            inv_id: basis_kwh * (max(0.0, kwp or 0.0) / total_kwp)
            for inv_id, kwp in module
        }
    # keine kWp-Werte → gleichmäßig verteilen
    n = len(module)
    return {inv_id: basis_kwh / n for inv_id, _ in module}


def resolve_pv_je_modul(
    *,
    aggregat_kwh: Optional[float],
    module: list[PvModul],
) -> dict[int, PvModulWert]:
    """Löst die Pro-Modul-PV-Erzeugung zur Lesezeit auf (Präzedenz siehe Modul-Doc).

    Args:
        aggregat_kwh: ``Monatsdaten.pv_erzeugung_kwh`` (manuelles Aggregat) oder
            ``None``. 0 zählt als Daten (``is not None``).
        module: im Monat aktive PV-Module (anschaffungs-/stilllegungs- und
            aktiv-gefiltert beim Aufrufer).

    Returns:
        ``{inv_id: PvModulWert}``. Σ der Werte == Gesamterzeugung.

    **Teil-Lücke ohne Aggregat — die Σ-Abweichung dort ist GEWOLLT (N42):**

    Messen nur MANCHE Module und es gibt kein Aggregat, liefert dieser Helper
    für alle Module ``QUELLE_FEHLT``/``0.0`` — bewusst: als **Anlagen-Summe**
    wäre eine Teilsumme irreführend, sie sähe wie die Gesamterzeugung aus und
    wäre systematisch zu klein.

    Eine **Pro-Modul-Sicht** kennt aber keine Anlagen-Summe und darf einen
    vorhandenen Messwert deshalb nicht wegwerfen. Read-Sites dürfen in genau
    diesem Fall (und nur in ihm) auf die Rohwerte zurückfallen — so gebaut in
    ``api/routes/cockpit/pv_strings.py`` (``if quelle == PV_QUELLE_FEHLT``).

    Folge: **Σ pv_strings ≠ Σ /monatsdaten/aggregiert** — die Pro-Modul-Sicht
    zeigt den Messwert, die Anlagen-Summe zeigt nichts. Das ist **kein
    Aggregations-Drift** und darf nicht „geheilt" werden: die beiden Sichten
    antworten auf verschiedene Fragen. Festgehalten in
    ``test_teilluecke_ohne_aggregat_behaelt_messwert``.

    Wer einen Σ-Symmetrie-Wächter für diese beiden Endpoints baut
    ([[feedback_aggregator_symmetrie]] verlangt einen), **muss diesen Fall
    ausnehmen** — sonst schlägt er auf der gewollten Asymmetrie an, und der
    nächste Durchgang „korrigiert" die Ausnahme zurück (A14/N42).
    """
    if not module:
        return {}

    if all(m.eigen_kwh is not None for m in module):
        return {
            m.inv_id: PvModulWert(m.inv_id, m.eigen_kwh or 0.0, QUELLE_GEMESSEN)
            for m in module
        }

    if aggregat_kwh is not None:
        verteilt = verteile_basis_kwh_nach_kwp(
            aggregat_kwh, [(m.inv_id, m.leistung_kwp) for m in module]
        )
        return {
            m.inv_id: PvModulWert(m.inv_id, verteilt.get(m.inv_id, 0.0), QUELLE_VERTEILT)
            for m in module
        }

    return {m.inv_id: PvModulWert(m.inv_id, 0.0, QUELLE_FEHLT) for m in module}


def gesamt_pv_kwh(
    *,
    aggregat_kwh: Optional[float],
    module: list[PvModul],
) -> float:
    """Gesamt-PV eines Monats nach derselben Präzedenz wie ``resolve_pv_je_modul``.

    Convenience für Read-Sites, die nur die Summe brauchen (z. B. ``/aggregiert``):
    Summe der gemessenen Werte, sonst das Aggregat, sonst 0. Deckungsgleich mit
    ``Σ resolve_pv_je_modul`` (Σ-Invariante).
    """
    return sum(w.pv_erzeugung_kwh for w in resolve_pv_je_modul(
        aggregat_kwh=aggregat_kwh, module=module).values())


def klassifiziere_pv_monat(
    *,
    n_aktive_module: int,
    n_gemessen: int,
    aggregat_kwh: Optional[float],
) -> str:
    """Klassifiziert die PV-Quellenlage eines Monats (Daten-Checker-SoT).

    Liefert ``STATUS_OK`` (gemessen vollständig), ``STATUS_VERTEILT`` (Aggregat
    deckt fehlende Module ab → INFO), ``STATUS_TEIL_LUECKE`` (ein Teil der
    Module gemessen, kein Aggregat → WARNING) oder ``STATUS_FEHLT`` (gar keine
    PV-Quelle → ERROR). Diese 3-stufige Konvention (Gernot 2026-06-06) wird vom
    Daten-Checker auf Severity gemappt.
    """
    if n_aktive_module <= 0:
        return STATUS_FEHLT
    if n_gemessen >= n_aktive_module:
        return STATUS_OK
    if aggregat_kwh is not None:
        return STATUS_VERTEILT
    if n_gemessen > 0:
        return STATUS_TEIL_LUECKE
    return STATUS_FEHLT
