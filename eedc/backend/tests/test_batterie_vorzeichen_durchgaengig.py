"""Durchgängigkeits-Test: EINE Batterie-Vorzeichen-Konvention überall.

Kanonik (SoT ``core.berechnungen.batterie_kw_spalte``): **ENTLADUNG positiv**
(Quelle), **LADUNG negativ** (Senke) — für
``TagesEnergieProfil.batterie_kw`` (Spalte A), das per-Stunde-/Tages-
``komponenten[batterie_*]`` (B/C) UND alle Consumer.

Dieser Test verankert die Konvention an allen Berechnungs-Stellen, damit ein
künftiger Eingriff an EINER Stelle (ohne die anderen) sofort rot wird
([[feedback_aggregator_symmetrie]]). Hintergrund: die Spalte wurde historisch
als ``ladung − entladung`` (Ladung positiv) geschrieben, während Vertrag +
Consumer Entladung positiv erwarten → Chart zeigte Laden als Erzeugung,
``speicher_ladung``/``-entladung`` vertauscht, Achse-2-Dauerflip.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen import batterie_kw_spalte, summe_batterie_netto_kwh
from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
from backend.services.snapshot.komponenten_beitraege import investition_beitraege


# ─── SoT-Helper (Spalte A) ──────────────────────────────────────────────────

def test_helper_entladung_positiv():
    """Bilanz-Netto (Ladung positiv) → Spalte (Entladung positiv) = Negation."""
    # Netto +2 = Ladungs-Überhang → Spalte negativ (Senke)
    assert batterie_kw_spalte(2.0) == -2.0
    # Netto -3 = Entladungs-Überhang → Spalte positiv (Quelle)
    assert batterie_kw_spalte(-3.0) == 3.0
    assert batterie_kw_spalte(0.0) == 0.0
    assert batterie_kw_spalte(None) is None


# ─── komponenten_kwh (C, Boundary-Produzent) ────────────────────────────────

def test_komponenten_beitraege_speicher_entladung_positiv():
    """investition_beitraege Speicher: ENTLADUNG +1, LADUNG -1 — gleich wie
    die Spalte (sonst flippt eine der beiden Achse-2-/TZ-Invarianten)."""
    inv = SimpleNamespace(id=5, typ="speicher", parameter={}, parent_investition_id=None)
    sm = {"felder": {
        "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.lade"},
        "entladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.entlade"},
    }}
    vz = {b.feld: b.vorzeichen for b in investition_beitraege(inv, sm)}
    assert vz["ladung_kwh"] == -1
    assert vz["entladung_kwh"] == +1


def test_spalte_und_komponenten_gleiches_vorzeichen():
    """Cross-Check A↔C: Beim Laden müssen Spalte UND komponenten_kwh-Beitrag
    dasselbe (negative) Vorzeichen haben."""
    inv = SimpleNamespace(id=5, typ="speicher", parameter={}, parent_investition_id=None)
    sm = {"felder": {
        "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.lade"},
        "entladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.entlade"},
    }}
    vz = {b.feld: b.vorzeichen for b in investition_beitraege(inv, sm)}

    # Reiner Lade-Tag: Bilanz-Netto = +5 (Ladung positiv)
    spalte_laden = batterie_kw_spalte(5.0)          # → -5 (Senke)
    komp_laden = 5.0 * vz["ladung_kwh"]             # → -5 (Senke)
    assert spalte_laden < 0 and komp_laden < 0
    # summe_batterie_netto_kwh liest komponenten in Spalten-Konvention
    assert summe_batterie_netto_kwh({"batterie_5": komp_laden}) == spalte_laden


# ─── Consumer: tagesbilanz speicher_ladung/-entladung ───────────────────────

def _row(batterie_kw):
    return SimpleNamespace(
        pv_kw=0.0, verbrauch_kw=0.0, einspeisung_kw=0.0, netzbezug_kw=0.0,
        batterie_kw=batterie_kw, waermepumpe_kw=0.0,
    )


def test_tagesbilanz_ladung_entladung_nicht_vertauscht():
    """Mit Entladung-positiver Spalte trennt tagesbilanz korrekt:
    positiv → Entladung, negativ → Ladung (Betrag)."""
    rows = [_row(2.0), _row(2.0), _row(-3.0)]  # 4 kWh entladen, 3 kWh geladen
    bilanz = bilanz_aus_stundenrows(rows)
    assert abs(bilanz.speicher_entladung_kwh - 4.0) < 1e-9
    assert abs(bilanz.speicher_ladung_kwh - 3.0) < 1e-9
