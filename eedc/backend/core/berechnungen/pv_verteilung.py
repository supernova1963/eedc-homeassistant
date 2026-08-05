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

**Präzedenz je Modul** (``resolve_pv_je_modul``) — Gernot 2026-07-29:

  1. Modul hat einen eigenen Wert → ``gemessen``. **Immer und ausnahmslos.**
  2. Modul ohne eigenen Wert, Aggregat gesetzt → Anteil am **Rest**
     (``Aggregat − Σ gemessene``), kWp-gewichtet → ``verteilt``
  3. Modul ohne eigenen Wert, kein Aggregat → ``fehlt``

Die Regel ist **modulweise**, nicht anlagenweit. Bis 2026-07-29 galt sie
anlagenweit: sobald **ein** Modul keinen Wert hatte, wurde das Aggregat über
**alle** Module verteilt — die echten Messwerte der übrigen Strings wurden
dabei verworfen und durch kWp-Anteile ersetzt. Das war nicht der Zweck des
Aggregats: es existiert, um **Lücken zu füllen** (Anlass war ein Anwender mit
Nur-Gesamt-Historie und neu unterstützten Einzelstrings), nicht um Messungen
zu überschreiben. Teil-Messung ist außerdem kein Sonderfall — sie entsteht bei
jedem Sensor-Aussetzer, jedem neu angelegten String und in jedem Monat vor der
Umstellung auf Pro-String-Messung.

**Das Aggregat ist reiner Eingang dieser Auflösung.** Es darf in keiner
einzelnen Berechnung direkt gelesen werden; jede PV-Zahl kommt aus der
Pro-Modul-Schicht bzw. deren Summe (siehe ``ist_vollstaendig``).

Σ-Invariante (Symmetrie-Test Pflicht, [[feedback_aggregator_symmetrie]]):
Σ der zurückgegebenen Pro-Modul-Werte == Gesamterzeugung — == Σ der gemessenen
Werte (keine Lücken) bzw. == Aggregat (Lücken + Aggregat). Die Verteilung
rundet NICHT, damit die Summe exakt erhalten bleibt; Rundung ist Aufgabe der
Anzeige-Schicht. **Eine Ausnahme:** übersteigt Σ der gemessenen Werte das
Aggregat, wird der Rest auf 0 geklemmt statt negativ verteilt — dann ist
Σ > Aggregat. Das ist ein Messfehler und gehört gemeldet, nicht weggerechnet.

**Unvollständigkeit ist ein eigener Zustand, keine kleine Zahl.** Bleibt auch
nur ein Modul auf ``fehlt``, ist die Σ **keine Anlagensumme** — sie sähe wie
die Gesamterzeugung aus und wäre systematisch zu klein. Plausibilitäts-Prüfung
dafür: ``ist_vollstaendig``. Die Pro-Modul-Sicht zeigt trotzdem, was gemessen
wurde (das ist der Sinn der modulweisen Regel).

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
    - ``eigen_ist_abgeleitet``: der gespeicherte Wert IST bereits eine
      kWp-Zerlegung (#352) — ein Import oder ein übernommener Connector-/
      Cloud-Vorschlag hat ihn geschrieben, gemessen wurde er nie. Der Wert
      bleibt unangetastet (er steht so in der DB), nur seine **Herkunft** ist
      ``verteilt`` statt ``gemessen``. Die Markierung kommt aus
      ``InvestitionMonatsdaten.source_provenance`` (Ladepfad
      ``services/pv_monatswerte.py``).
    """

    inv_id: int
    leistung_kwp: float
    eigen_kwh: Optional[float]
    eigen_ist_abgeleitet: bool = False


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

    Messen nur MANCHE Module und es gibt kein Aggregat, behalten die messenden
    Module ihren Wert (Regel 1), die übrigen bleiben ``QUELLE_FEHLT``/``0.0``.
    Die **Anlagen-Summe** darf daraus nicht gebildet werden — sie wäre eine
    Teilsumme, sähe wie die Gesamterzeugung aus und wäre systematisch zu klein.
    Dafür gibt es ``ist_vollstaendig``; Anlagen-Read-Sites fragen sie, bevor sie
    summieren (so gebaut in ``api/routes/monatsdaten.py``).

    Folge: **Σ pv_strings ≠ Σ /monatsdaten/aggregiert** — die Pro-Modul-Sicht
    zeigt die Messwerte, die Anlagen-Summe zeigt nichts. Das ist **kein
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

    gemessen_summe = sum(m.eigen_kwh or 0.0 for m in module if m.eigen_kwh is not None)
    luecken = [m for m in module if m.eigen_kwh is None]

    verteilt: dict[int, float] = {}
    if luecken and aggregat_kwh is not None:
        # Der Rest, den die gemessenen Module NICHT erklären. Negativ = die
        # Messungen übersteigen das Aggregat; dann ist eine der beiden Quellen
        # falsch. Auf 0 klemmen statt negative kWh zu verteilen — die Meldung
        # ist Sache des Daten-Checkers, nicht dieser Formel.
        rest = max(0.0, aggregat_kwh - gemessen_summe)
        verteilt = verteile_basis_kwh_nach_kwp(
            rest, [(m.inv_id, m.leistung_kwp) for m in luecken]
        )

    out: dict[int, PvModulWert] = {}
    for m in module:  # Eingabe-Reihenfolge erhalten (deterministisch)
        if m.eigen_kwh is not None:
            # #352: Ein gespeicherter Wert, der selbst schon eine Zerlegung ist,
            # bleibt als Zahl unverändert — aber er behauptet keine Messung.
            # Sonst kürt das String-Ranking einen „besten String" aus Zahlen,
            # die per Konstruktion proportional zur kWp sind, und der
            # Daten-Checker meldet OK statt INFO.
            out[m.inv_id] = PvModulWert(
                m.inv_id,
                m.eigen_kwh,
                QUELLE_VERTEILT if m.eigen_ist_abgeleitet else QUELLE_GEMESSEN,
            )
        elif aggregat_kwh is not None:
            out[m.inv_id] = PvModulWert(
                m.inv_id, verteilt.get(m.inv_id, 0.0), QUELLE_VERTEILT
            )
        else:
            out[m.inv_id] = PvModulWert(m.inv_id, 0.0, QUELLE_FEHLT)
    return out


def ist_vollstaendig(werte: dict[int, PvModulWert]) -> bool:
    """Ist die Σ der aufgelösten Werte eine **Anlagensumme**?

    Nur wenn jedes Modul aufgelöst ist (gemessen oder verteilt). Bleibt eines
    auf ``fehlt``, ist die Σ eine Teilsumme — die darf keine Read-Site als
    Gesamterzeugung ausweisen (N42). Leere Modul-Liste → ``False``: „keine
    Module" ist keine vollständige Erzeugung, sondern gar keine Aussage.
    """
    return bool(werte) and all(w.quelle != QUELLE_FEHLT for w in werte.values())


def gesamt_pv_kwh(
    *,
    aggregat_kwh: Optional[float],
    module: list[PvModul],
) -> Optional[float]:
    """Gesamt-PV eines Monats nach derselben Präzedenz wie ``resolve_pv_je_modul``.

    ``None`` = **unvollständig** (mindestens ein Modul unaufgelöst) — bewusst
    keine Teilsumme, siehe ``ist_vollstaendig``. Sonst Σ der Pro-Modul-Werte,
    deckungsgleich mit ``Σ resolve_pv_je_modul`` (Σ-Invariante).
    """
    werte = resolve_pv_je_modul(aggregat_kwh=aggregat_kwh, module=module)
    if not ist_vollstaendig(werte):
        return None
    return sum(w.pv_erzeugung_kwh for w in werte.values())


def klassifiziere_pv_monat(
    *,
    n_aktive_module: int,
    n_gemessen: int,
    aggregat_kwh: Optional[float],
    n_abgeleitet: int = 0,
) -> str:
    """Klassifiziert die PV-Quellenlage eines Monats (Daten-Checker-SoT).

    Liefert ``STATUS_OK`` (gemessen vollständig), ``STATUS_VERTEILT`` (Aggregat
    deckt fehlende Module ab → INFO), ``STATUS_TEIL_LUECKE`` (ein Teil der
    Module gemessen, kein Aggregat → WARNING) oder ``STATUS_FEHLT`` (gar keine
    PV-Quelle → ERROR). Diese 3-stufige Konvention (Gernot 2026-06-06) wird vom
    Daten-Checker auf Severity gemappt.

    Args:
        n_gemessen: Module mit einem **gemessenen** Pro-Modul-Wert.
        n_abgeleitet: Module, deren gespeicherter Wert selbst eine
            kWp-Zerlegung ist (#352). Sie decken den Monat ab wie ein
            Aggregat — deshalb ``STATUS_VERTEILT`` und **nicht**
            ``STATUS_FEHLT``: die Zahlen sind da, sie sind nur gerechnet.
            Ohne diesen Zweig würde ein vollständig importierter Monat nach
            der Markierung plötzlich als ERROR gemeldet.
    """
    if n_aktive_module <= 0:
        return STATUS_FEHLT
    if n_gemessen >= n_aktive_module:
        return STATUS_OK
    if aggregat_kwh is not None:
        return STATUS_VERTEILT
    if n_gemessen + n_abgeleitet >= n_aktive_module and n_abgeleitet > 0:
        return STATUS_VERTEILT
    if n_gemessen > 0:
        return STATUS_TEIL_LUECKE
    return STATUS_FEHLT
