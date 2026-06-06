"""Counter-Aggregate (WP-Kompressor-Starts, Betriebsstunden) — Stunden-Σ aus
dem Tages-Boundary-Diff ableiten.

Hintergrund (KONZEPT-COUNTER-DAILY-DRIFT.md, Variante 2-light): Zwei Pfade
tragen denselben Counter-Tageswert auf unterschiedlichen Wegen:

- `TagesEnergieProfil.wp_starts_anzahl[h]` — Stunden-Σ aus Snapshot-Inkrementen
  (`get_hourly_counter_sum_by_feld`).
- `TagesZusammenfassung.komponenten_starts[inv_id]` — Boundary-Diff über das
  Tagesfenster (`get_daily_counter_deltas_by_inv`).

Bei sauberen Snapshots gilt `Σ_h wp_starts_anzahl[h] == Σ_inv komponenten_starts`.
Bei NULL-Slots / Snapshot-Lücken divergieren beide Sichten — das UI zeigt dann
zwei unterschiedliche „Tages-Starts" für denselben Tag.

Wie der kWh-Pfad seit Etappe 4 wählen wir EINE Quelle pro Tag: der
Boundary-Diff (HA-konform, robust gegen NULL-Slots) gewinnt; die Stunden-Σ
wird daraus abgeleitet (reskaliert). Bei sauberen Daten bleibt die Stunden-Σ
unverändert (verhaltensneutral). Die Pflicht-Invariante `pruefe_counter_konsistent`
macht eine Rest-Drift sichtbar (analog `pruefe_*` im kWh-Pfad, ADR-001).

Float- vs. Zähl-Counter: WP-Starts sind ganzzahlig (Zähl-Counter), Betriebs-
stunden gebrochen (`FLOAT_COUNTER_FELDER`). Die Ganzzahl-Verteilung nutzt das
Größter-Rest-Verfahren, damit Σ exakt erhalten bleibt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─── Invariante ───────────────────────────────────────────────────────────────

@dataclass
class CounterKonsistenzBericht:
    """Ergebnis der Counter-Konsistenz-Prüfung (Stunden-Σ vs. Tages-Boundary-Diff)."""
    konsistent: bool
    name: str
    erwartet: float       # Tages-Boundary-Diff (Σ_inv) — die SoT
    tatsaechlich: float   # Σ_h der Stunden-Σ
    toleranz: float
    details: str = ""

    @property
    def abweichung(self) -> float:
        return abs(self.tatsaechlich - self.erwartet)

    def __str__(self) -> str:
        status = "✓" if self.konsistent else "✗"
        return (
            f"{status} {self.name}: erwartet={self.erwartet:.3f}, "
            f"tatsächlich={self.tatsaechlich:.3f}, "
            f"Δ={self.abweichung:.3f} (Toleranz {self.toleranz:.3f})"
            f"{' — ' + self.details if self.details else ''}"
        )


def pruefe_counter_konsistent(
    stunden: dict[int, Optional[float]],
    tages_summe: float,
    *,
    name: str = "counter",
    toleranz: float = 0.5,
) -> CounterKonsistenzBericht:
    """Prüft: `Σ_h stunden[h] == tages_summe` (Boundary-Diff = SoT).

    Args:
        stunden: `{h: wert}` der Stunden-Σ (None = Snapshot-Lücke, zählt nicht).
        tages_summe: Tages-Boundary-Diff über alle Investitionen für dieses Feld.
        name: Label für die Diagnose-Meldung (z. B. `counter:wp_starts_anzahl`).
        toleranz: akzeptierte Abweichung (Default 0.5 — deckt Float-Rundung +
            Ganzzahl-Restverteilung ab).
    """
    s = sum(v for v in stunden.values() if v is not None)
    return CounterKonsistenzBericht(
        konsistent=abs(s - tages_summe) <= toleranz,
        name=name,
        erwartet=tages_summe,
        tatsaechlich=s,
        toleranz=toleranz,
    )


def assert_counter_konsistent(
    stunden: dict[int, Optional[float]],
    tages_summe: float,
    *,
    name: str = "counter",
    toleranz: float = 0.5,
) -> CounterKonsistenzBericht:
    """`pruefe_counter_konsistent`-Variante, die bei Verletzung wirft (Tests/CI)."""
    bericht = pruefe_counter_konsistent(
        stunden, tages_summe, name=name, toleranz=toleranz
    )
    assert bericht.konsistent, str(bericht)
    return bericht


# ─── Ableitung Stunden-Σ aus Boundary-Diff ─────────────────────────────────────

def _ganzzahlig_verteilen(
    stunden: dict[int, Optional[float]],
    gewichte: dict[int, float],
    ziel_summe: int,
) -> dict[int, Optional[float]]:
    """Verteilt `ziel_summe` ganzzahlig auf die Slots in `gewichte` (Profil-
    proportional, Größter-Rest-Verfahren) — Σ bleibt exakt `ziel_summe`.
    Slots außerhalb `gewichte` (Lücken) bleiben unverändert.
    """
    out: dict[int, Optional[float]] = dict(stunden)
    if not gewichte or ziel_summe <= 0:
        for h in gewichte:
            out[h] = 0
        return out

    g_summe = sum(gewichte.values())
    if g_summe <= 0:
        # Kein Profil (alle belegten Slots 0): gleichmäßig auf die Slots.
        gewichte = {h: 1.0 for h in gewichte}
        g_summe = float(len(gewichte))

    roh = {h: (gewichte[h] / g_summe) * ziel_summe for h in gewichte}
    floor = {h: int(roh[h]) for h in gewichte}
    rest = ziel_summe - sum(floor.values())
    # Rest an die größten Nachkommaanteile vergeben (deterministisch).
    nach_rest = sorted(gewichte, key=lambda h: (roh[h] - floor[h], -h), reverse=True)
    for i in range(rest):
        floor[nach_rest[i % len(nach_rest)]] += 1
    for h in gewichte:
        out[h] = floor[h]
    return out


def verteile_counter_auf_stunden(
    stunden: dict[int, Optional[float]],
    tages_summe: float,
    *,
    as_float: bool = False,
) -> dict[int, Optional[float]]:
    """Leitet die Stunden-Σ aus dem Tages-Boundary-Diff ab (eine Quelle/Tag).

    Der Boundary-Diff (`tages_summe`) ist die SoT. Stimmt die eigenständig aus
    Snapshots gerechnete Stunden-Σ damit überein (saubere Daten), bleibt
    `stunden` unverändert. Weicht sie ab (NULL-Slots / Snapshot-Lücken), wird
    `tages_summe` anhand des vorhandenen Stundenprofils reskaliert, sodass
    `Σ_h == tages_summe`.

    Args:
        stunden: `{h: wert}` der eigenständig gerechneten Stunden-Σ (None = Lücke).
        tages_summe: Tages-Boundary-Diff über alle Investitionen für dieses Feld.
        as_float: True für Float-Counter (Betriebsstunden), False für Zähl-Counter
            (Starts) → Ganzzahl-Verteilung mit Größter-Rest-Verfahren.

    Returns:
        Reskalierte `{h: wert}`-Map mit `Σ_h == tages_summe`. Lücken (None)
        bleiben Lücken.
    """
    belegte = {h: v for h, v in stunden.items() if v is not None}
    aktuelle_summe = sum(belegte.values())

    # Saubere Daten: Stunden-Σ deckt sich mit dem Boundary-Diff → unverändert.
    toleranz = 1e-9 if as_float else 0.5
    if abs(aktuelle_summe - tages_summe) <= toleranz:
        return dict(stunden)

    if tages_summe <= 0:
        # Boundary-Diff sagt: kein Ereignis am Tag → belegte Slots auf 0 ziehen.
        return {
            h: ((0.0 if as_float else 0) if v is not None else None)
            for h, v in stunden.items()
        }

    if as_float:
        if aktuelle_summe > 0:
            faktor = tages_summe / aktuelle_summe
            skaliert = {h: belegte[h] * faktor for h in belegte}
        else:
            ziel = list(belegte.keys()) or list(range(24))
            anteil = tages_summe / len(ziel)
            skaliert = {h: anteil for h in ziel}
        out = dict(stunden)
        for h, v in skaliert.items():
            out[h] = round(v, 3)
        return out

    # Zähl-Counter: ganzzahlig profil-proportional verteilen.
    gewichte = belegte if aktuelle_summe > 0 else {h: 1.0 for h in (belegte or {h: 0 for h in range(24)})}
    return _ganzzahlig_verteilen(stunden, gewichte, int(round(tages_summe)))
