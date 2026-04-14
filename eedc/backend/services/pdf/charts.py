"""
Matplotlib-Charts für die WeasyPrint-Pipeline.

Liefert Charts als Base64-kodierte PNGs, die direkt in `<img src="data:...">`
gehängt werden können — keine temporären Dateien, keine Pfad-Auflösung.
"""
from __future__ import annotations

import base64
import io
from typing import Iterable

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

_PRIMARY = "#1565c0"
_PRIMARY_DARK = "#0d47a1"
_ACCENT = "#43a047"
_NETZ = "#e53935"
_GRAY = "#90a4ae"


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def pv_erzeugung_chart(monats_labels: list[str], pv_kwh: list[float], prognose_kwh: list[float] | None = None) -> str:
    """Balkendiagramm PV-Erzeugung pro Monat, optional mit PVGIS-Prognose-Linie."""
    fig, ax = plt.subplots(figsize=(8, 3.0))
    x = list(range(len(monats_labels)))
    ax.bar(x, pv_kwh, color=_PRIMARY, label="IST", width=0.7)
    if prognose_kwh and any(prognose_kwh):
        ax.plot(x, prognose_kwh, color=_NETZ, marker="o", linewidth=1.5, label="PVGIS-Prognose")
    ax.set_xticks(x)
    ax.set_xticklabels(monats_labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("kWh")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(fontsize=8, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_data_uri(fig)


def energie_fluss_chart(monats_labels: list[str], eigenverbrauch_kwh: list[float], einspeisung_kwh: list[float], netzbezug_kwh: list[float]) -> str:
    """Gestapelte Bars: Eigenverbrauch + Einspeisung (PV-Aufteilung) und Netzbezug daneben."""
    fig, ax = plt.subplots(figsize=(8, 3.0))
    x = list(range(len(monats_labels)))
    width = 0.4
    x1 = [i - width / 2 for i in x]
    x2 = [i + width / 2 for i in x]
    ax.bar(x1, eigenverbrauch_kwh, width=width, color=_ACCENT, label="Eigenverbrauch")
    ax.bar(x1, einspeisung_kwh, width=width, bottom=eigenverbrauch_kwh, color=_PRIMARY, label="Einspeisung")
    ax.bar(x2, netzbezug_kwh, width=width, color=_NETZ, label="Netzbezug")
    ax.set_xticks(x)
    ax.set_xticklabels(monats_labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("kWh")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(fontsize=8, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_data_uri(fig)


def autarkie_chart(monats_labels: list[str], autarkie_prozent: list[float]) -> str:
    """Linien-Chart für die monatliche Autarkie-Quote."""
    fig, ax = plt.subplots(figsize=(8, 2.6))
    x = list(range(len(monats_labels)))
    ax.plot(x, autarkie_prozent, color=_PRIMARY_DARK, marker="o", linewidth=1.8)
    ax.fill_between(x, autarkie_prozent, color=_PRIMARY, alpha=0.15)
    ax.set_xticks(x)
    ax.set_xticklabels(monats_labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Autarkie %")
    ax.set_ylim(0, max(100, max(autarkie_prozent) if autarkie_prozent else 100))
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_data_uri(fig)
