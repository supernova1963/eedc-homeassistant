"""Diagnose-Paket v4 — Datenauszug einer Anlage als ZIP (Konzept/Bauplan «Diagnose-Paket v4», 14.11.2026).

Module (Lade-Ebenen, Bauplan §3.1): ``register`` (Spalten-Register, nur stdlib + Parameter-Registry; werkzeugtauglich) ·
``bereinigung`` (Log-Bereinigung, Blatt-Regel, Marken) · ``auszug`` (eine Lese-Transaktion, Tabellen-Mitglieder) ·
``lage`` (Lage zur Laufzeit) · ``ha_abgleich`` (Spiegel ↔ HA, lesend) · ``ablage`` (temporäre Datei, Marke, Ablauf) ·
``paket`` (``bereitstellen``). Kein Import hier — das Werkzeug lädt ``register`` ohne Backend-Last.
"""
