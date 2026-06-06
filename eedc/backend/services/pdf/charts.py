"""SVG-Charts für die WeasyPrint-Pipeline — bewusst matplotlib-/numpy-frei.

Liefert Charts als inline-SVG in einem ``data:image/svg+xml``-URI, das direkt
in ``<img src="data:...">`` gehängt werden kann — keine temporären Dateien,
keine Pfad-Auflösung.

**Warum kein matplotlib mehr (#303 / #121):** numpy 2.x ist mit X86-V2-Baseline
gebaut; HA-als-Proxmox-VM mit Default-CPU-Typ ``kvm64`` reicht diesen
Befehlssatz nicht durch → ``RuntimeError: NumPy was built with baseline
optimizations (X86_V2)``. Der Jahresbericht ist der einzige PDF-Pfad mit
Diagrammen; matplotlib/numpy darf damit nicht im Pflicht-Pfad liegen. SVG wird
von WeasyPrint nativ gerendert, ist auflösungsunabhängig und ohne C-Extensions.

Die Funktionssignaturen sind unverändert zur matplotlib-Version, damit der
Builder (`builders/jahresbericht.py`) und das Template nicht angefasst werden
müssen.
"""
from __future__ import annotations

import base64
import math
from html import escape

_PRIMARY = "#1565c0"
_PRIMARY_DARK = "#0d47a1"
_ACCENT = "#43a047"
_NETZ = "#e53935"
_GRID = "#cfd8dc"
_AXIS = "#607d8b"
_TEXT = "#37474f"
_FONT = "font-family:'DejaVu Sans',Arial,Helvetica,sans-serif"

_W = 800.0
_PAD_L = 56.0   # Platz für y-Achsen-Beschriftung
_PAD_R = 18.0
_PAD_T = 34.0   # Platz für Legende
_PAD_B = 60.0   # Platz für x-Achsen-Beschriftung


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _svg_to_data_uri(svg: str) -> str:
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _nice_step(spanne: float) -> float:
    """Hübsche Schrittweite für ~4 Achsen-Intervalle."""
    if spanne <= 0:
        return 1.0
    roh = spanne / 4.0
    exp = math.floor(math.log10(roh))
    basis = 10.0 ** exp
    frac = roh / basis
    if frac <= 1:
        nice = 1.0
    elif frac <= 2:
        nice = 2.0
    elif frac <= 2.5:
        nice = 2.5
    elif frac <= 5:
        nice = 5.0
    else:
        nice = 10.0
    return nice * basis


def _fmt_tick(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.1f}"


def _label_step(n: int) -> int:
    """Bei vielen Kategorien nur jede k-te x-Beschriftung zeigen (statt Rotation)."""
    if n <= 16:
        return 1
    return math.ceil(n / 16)


def _axis_and_grid(labels: list[str], ymax: float, ystep: float, ylabel: str, height: float) -> tuple[list[str], float, float, float, float]:
    """Zeichnet Gitter, y-Achse, y-Ticks und x-Beschriftungen.

    Rückgabe: (svg_fragmente, plot_left, plot_bottom, plot_w, plot_h).
    """
    plot_left = _PAD_L
    plot_right = _W - _PAD_R
    plot_top = _PAD_T
    plot_bottom = height - _PAD_B
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    n = len(labels)

    parts: list[str] = []

    # Horizontale Gitterlinien + y-Ticks
    v = 0.0
    while v <= ymax + 1e-6:
        y = plot_bottom - plot_h * (v / ymax)
        parts.append(
            f'<line x1="{plot_left:.1f}" y1="{y:.1f}" x2="{plot_right:.1f}" y2="{y:.1f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{plot_left - 8:.1f}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'font-size="11" fill="{_TEXT}" style="{_FONT}">{_fmt_tick(v)}</text>'
        )
        v += ystep

    # y-Achsen-Titel (vertikal)
    ty = plot_top + plot_h / 2
    parts.append(
        f'<text x="16" y="{ty:.1f}" text-anchor="middle" font-size="11" fill="{_TEXT}" '
        f'style="{_FONT}" transform="rotate(-90 16 {ty:.1f})">{escape(ylabel)}</text>'
    )

    # Basislinie (x-Achse)
    parts.append(
        f'<line x1="{plot_left:.1f}" y1="{plot_bottom:.1f}" x2="{plot_right:.1f}" '
        f'y2="{plot_bottom:.1f}" stroke="{_AXIS}" stroke-width="1.2"/>'
    )

    # x-Beschriftungen (zentriert; bei vielen Kategorien ausgedünnt)
    step = _label_step(n)
    for i, lab in enumerate(labels):
        if i % step != 0:
            continue
        cx = plot_left + plot_w * (i + 0.5) / n
        parts.append(
            f'<text x="{cx:.1f}" y="{plot_bottom + 16:.1f}" text-anchor="middle" '
            f'font-size="10.5" fill="{_TEXT}" style="{_FONT}">{escape(str(lab))}</text>'
        )

    return parts, plot_left, plot_bottom, plot_w, plot_h


def _legend(items: list[tuple[str, str]]) -> str:
    """Legende oben links (Liste aus (Farbe, Label))."""
    parts: list[str] = []
    x = _PAD_L
    y = 16.0
    for color, label in items:
        parts.append(
            f'<rect x="{x:.1f}" y="{y - 9:.1f}" width="12" height="12" rx="2" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x + 17:.1f}" y="{y + 1:.1f}" font-size="11" fill="{_TEXT}" '
            f'style="{_FONT}">{escape(label)}</text>'
        )
        x += 17 + 7 * len(label) + 22
    return "".join(parts)


def _wrap(svg_body: str, height: float) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W:.0f} {height:.0f}" '
        f'width="{_W:.0f}" height="{height:.0f}" font-size="11">'
        f'<rect x="0" y="0" width="{_W:.0f}" height="{height:.0f}" fill="white"/>'
        f"{svg_body}</svg>"
    )


# ── Öffentliche Chart-Funktionen ─────────────────────────────────────────────

def pv_erzeugung_chart(monats_labels: list[str], pv_kwh: list[float], prognose_kwh: list[float] | None = None) -> str:
    """Balkendiagramm PV-Erzeugung pro Monat, optional mit PVGIS-Prognose-Linie."""
    height = 300.0
    labels = list(monats_labels)
    pv = [float(v or 0) for v in pv_kwh]
    prog = [float(v or 0) for v in (prognose_kwh or [])]
    hat_prognose = bool(prog) and any(prog)
    n = max(1, len(labels))

    rawmax = max(pv + (prog if hat_prognose else []) + [0.0]) or 1.0
    ystep = _nice_step(rawmax)
    ymax = ystep * math.ceil(rawmax / ystep) if ystep else 1.0
    ymax = ymax or 1.0

    legend_items = [(_PRIMARY, "IST")]
    if hat_prognose:
        legend_items.append((_NETZ, "PVGIS-Prognose"))

    parts, pl, pb, pw, ph = _axis_and_grid(labels, ymax, ystep, "kWh", height)
    parts.insert(0, _legend(legend_items))

    bw = (pw / n) * 0.62
    for i, val in enumerate(pv):
        cx = pl + pw * (i + 0.5) / n
        y = pb - ph * (val / ymax)
        parts.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
            f'height="{pb - y:.1f}" fill="{_PRIMARY}"/>'
        )

    if hat_prognose:
        pts = []
        for i, val in enumerate(prog):
            cx = pl + pw * (i + 0.5) / n
            y = pb - ph * (val / ymax)
            pts.append((cx, y))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{_NETZ}" stroke-width="1.8"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{_NETZ}"/>')

    return _svg_to_data_uri(_wrap("".join(parts), height))


def energie_fluss_chart(monats_labels: list[str], eigenverbrauch_kwh: list[float], einspeisung_kwh: list[float], netzbezug_kwh: list[float]) -> str:
    """Pro Monat: gestapelte Bar (Eigenverbrauch + Einspeisung) und Netzbezug-Bar daneben."""
    height = 300.0
    labels = list(monats_labels)
    ev = [float(v or 0) for v in eigenverbrauch_kwh]
    ein = [float(v or 0) for v in einspeisung_kwh]
    netz = [float(v or 0) for v in netzbezug_kwh]
    n = max(1, len(labels))

    rawmax = max([e + s for e, s in zip(ev, ein)] + netz + [0.0]) or 1.0
    ystep = _nice_step(rawmax)
    ymax = ystep * math.ceil(rawmax / ystep) if ystep else 1.0
    ymax = ymax or 1.0

    parts, pl, pb, pw, ph = _axis_and_grid(labels, ymax, ystep, "kWh", height)
    parts.insert(0, _legend([
        (_ACCENT, "Eigenverbrauch"),
        (_PRIMARY, "Einspeisung"),
        (_NETZ, "Netzbezug"),
    ]))

    slot = pw / n
    bw = slot * 0.30
    off = slot * 0.17
    for i in range(len(labels)):
        cx = pl + pw * (i + 0.5) / n
        # Linke gestapelte Bar: Eigenverbrauch (unten) + Einspeisung (oben)
        evh = ph * (ev[i] / ymax)
        einh = ph * (ein[i] / ymax)
        y_ev = pb - evh
        parts.append(
            f'<rect x="{cx - off - bw / 2:.1f}" y="{y_ev:.1f}" width="{bw:.1f}" '
            f'height="{evh:.1f}" fill="{_ACCENT}"/>'
        )
        parts.append(
            f'<rect x="{cx - off - bw / 2:.1f}" y="{y_ev - einh:.1f}" width="{bw:.1f}" '
            f'height="{einh:.1f}" fill="{_PRIMARY}"/>'
        )
        # Rechte Bar: Netzbezug
        nh = ph * (netz[i] / ymax)
        parts.append(
            f'<rect x="{cx + off - bw / 2:.1f}" y="{pb - nh:.1f}" width="{bw:.1f}" '
            f'height="{nh:.1f}" fill="{_NETZ}"/>'
        )

    return _svg_to_data_uri(_wrap("".join(parts), height))


def autarkie_chart(monats_labels: list[str], autarkie_prozent: list[float]) -> str:
    """Linien-/Flächen-Chart für die monatliche Autarkie-Quote (%)."""
    height = 250.0
    labels = list(monats_labels)
    werte = [float(v or 0) for v in autarkie_prozent]
    n = max(1, len(labels))

    rawmax = max(werte + [100.0])
    ystep = _nice_step(rawmax)
    ymax = ystep * math.ceil(rawmax / ystep) if ystep else 100.0
    ymax = ymax or 100.0

    parts, pl, pb, pw, ph = _axis_and_grid(labels, ymax, ystep, "Autarkie %", height)

    pts = []
    for i, val in enumerate(werte):
        cx = pl + pw * (i + 0.5) / n
        y = pb - ph * (val / ymax)
        pts.append((cx, y))

    if pts:
        # Füllfläche unter der Linie
        area = f"{pts[0][0]:.1f},{pb:.1f} " + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" {pts[-1][0]:.1f},{pb:.1f}"
        parts.append(f'<polygon points="{area}" fill="{_PRIMARY}" fill-opacity="0.15"/>')
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{_PRIMARY_DARK}" stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{_PRIMARY_DARK}"/>')

    return _svg_to_data_uri(_wrap("".join(parts), height))
