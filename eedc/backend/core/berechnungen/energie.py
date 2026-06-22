"""Energie-Aggregate aus den zentralen Tabellen.

Single Source of Truth für:
- Whitelist-Prefixe für PV-Erzeugungs-Komponenten in komponenten_kwh
- Tages-Summen aus dem komponenten_kwh-JSON

Konsumenten importieren ausschließlich aus diesem Modul, NICHT inline
re-implementieren. Konformitäts-Test prüft, dass die Prefix-Tuple bzw.
Inline-`startswith("pv_")`-Patterns außerhalb dieses Layers nicht auftauchen.
"""

from __future__ import annotations

from typing import Optional


# ─── Whitelist-Konstante (SoT) ──────────────────────────────────────────────

# Komponenten-Keys in TagesZusammenfassung.komponenten_kwh, die zur PV-
# Tageserzeugung beitragen. Ein neues PV-Präfix (z. B. `wr_`) muss hier
# ergänzt werden — sonst zählen Daten-Checker, Drift-Check, Genauigkeits-
# Tracking und Reparatur-Werkbank ihn nicht mit.
#
# Spiegel im Frontend: `frontend/src/lib/constants.ts:PV_KOMPONENTEN_PREFIXE`
# (TypeScript kann nicht aus diesem Layer importieren) — dort ebenfalls ergänzen.
#
# Vor Hinzufügen eines neuen Präfixes prüfen:
# - Wird der Boundary-Pfad (lts_aggregator.py:237+ oder snapshot/aggregator.py)
#   diesen Präfix tatsächlich schreiben?
# - Ist das Naming-Schema zwischen Live-Tagesverlauf-Service
#   (live_sensor_config.TV_SERIE_CONFIG → live_tagesverlauf_service:148) und
#   Boundary-Aggregator identisch? Bei Mismatch entsteht Doppelzählung
#   (BKW-Bug 2026-05-19, Rainer-PN).
PV_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("pv_", "bkw_")


# Pro Kategorie der Per-Stunde-TEP-Felder die zugehörigen komponenten_kwh-
# Präfixe, damit die Invariante (siehe core/berechnungen/invarianten.py) für
# jede Kategorie symmetrisch laufen kann (v3.33.0, Issue #290).
WAERMEPUMPE_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("waermepumpe_",)
WALLBOX_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("wallbox_", "eauto_")
BATTERIE_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("batterie_",)


# ─── Σ-Helper ───────────────────────────────────────────────────────────────


def _summe_prefix(
    komponenten_kwh: Optional[dict],
    prefixe: tuple[str, ...],
    nur_positiv: bool = False,
) -> float:
    """Σ aller komponenten_kwh-Werte deren Key mit einem der Präfixe beginnt."""
    if not komponenten_kwh:
        return 0.0
    return sum(
        float(v)
        for k, v in komponenten_kwh.items()
        if isinstance(v, (int, float))
        and (not nur_positiv or v > 0)
        and any(k.startswith(p) for p in prefixe)
    )


def summe_pv_bkw_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Tages-PV-Σ aus dem JSON-Feld `TagesZusammenfassung.komponenten_kwh`.

    Whitelist auf `PV_KOMPONENTEN_PREFIXE`, nur positive Werte
    (Verbraucher-Sub-Keys mit negativem Vorzeichen werden ignoriert).
    """
    return _summe_prefix(komponenten_kwh, PV_KOMPONENTEN_PREFIXE, nur_positiv=True)


# ─── Netzpunkt-Bilanz: Gesamterzeugung hinter dem Hauszähler ────────────────


def erzeugung_hinter_zaehler_kwh(*erzeuger_kwh: Optional[float]) -> float:
    """Σ aller Erzeuger-Beiträge *hinter dem Hauszähler* — Eingang der Netzpunkt-Bilanz.

    PV-Module + Balkonkraftwerk + **sonstige Erzeuger** (z. B. Mini-BHKW/KWK).
    An EINEM Netzanschluss messen die Zähler (`einspeisung_kwh`/`netzbezug_kwh`)
    die Summe ALLER dahinter liegenden Erzeuger. Deshalb MUSS die Eigenverbrauchs-/
    Autarkie-Ableitung (`berechne_verbrauchs_kennzahlen`) diese Gesamtsumme als
    „Erzeugung" bekommen — sonst wird die Bilanz still verfälscht: ein ignorierter
    Erzeuger drückt `direktverbrauch = max(0, Erzeugung − Einspeisung − …)` zu
    niedrig (auf 0 geklemmt), und Autarkie/EV-Quote werden unterschätzt
    (Konzept „Sonstiger Erzeuger", 2026-06-22).

    Achsen-Trennung (bewusst): PV-EIGENE Kennzahlen (spez. Ertrag, Performance-
    Ratio, SOLL/IST, kWp) nutzen NUR die PV-Erzeugung, NICHT diese Summe — ein
    sonstiger Erzeuger ist energetisch Erzeuger, aber kein PV-Modul. CO₂-/
    Wirtschaftlichkeits-Bewertung bleibt ebenfalls quellenspezifisch (ein BHKW
    spart kein CO₂, sondern emittiert; Brennstoffkosten sind ein eigener Posten).
    Insel-Anlagen (kein Netzanschluss, kein Bezug/keine Einspeisung) fallen nicht
    unter diesen Begriff — das ist ein Anlagen-Merkmal (eigenes KZ, geplant).

    None-tolerant (None → 0.0). Aufrufer übergeben i. d. R. die schon
    zusammengefasste PV-(inkl. BKW-)Erzeugung + die Sonstiges-Erzeugung.
    """
    return sum(float(x or 0.0) for x in erzeuger_kwh)


def summe_waermepumpe_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Σ aller `waermepumpe_<id>`-Keys (immer ≥ 0, elektrischer Verbrauch)."""
    return _summe_prefix(komponenten_kwh, WAERMEPUMPE_KOMPONENTEN_PREFIXE)


def summe_wallbox_eauto_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Σ aller `wallbox_<id>` + `eauto_<id>`-Keys.

    Spiegelt das TEP-Feld `wallbox_kw`, das im Aggregator als
    `snap_h.get("wallbox") + snap_h.get("eauto")` zusammengesetzt wird.
    """
    return _summe_prefix(komponenten_kwh, WALLBOX_KOMPONENTEN_PREFIXE)


def summe_batterie_netto_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Σ aller `batterie_<id>`-Keys, signed (Ladung − Entladung)."""
    return _summe_prefix(komponenten_kwh, BATTERIE_KOMPONENTEN_PREFIXE)


def wert_basis_kwh(komponenten_kwh: Optional[dict], feld: str) -> Optional[float]:
    """Liest `einspeisung` / `netzbezug` aus dem Basis-Slot — None wenn nicht gemappt."""
    if not komponenten_kwh:
        return None
    v = komponenten_kwh.get(feld)
    return float(v) if isinstance(v, (int, float)) else None
