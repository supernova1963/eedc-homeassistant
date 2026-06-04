"""
Zentraler Prognosequellen-Adapter-Layer (Konzept KONZEPT-PROGNOSE-ADAPTER-LAYER,
Issue #297-Folge, Tracking #110).

**Ziel:** Jede Prognosequelle (OpenMeteo/GTI, Solcast, IST) wird hier auf ein
**kanonisches** ``StundenProfil`` (24 Backward-Slots, Index = Slot ``h`` =
Intervall ``[h-1, h)``) normalisiert — die Slot-Zuordnung selbst lebt zentral in
``core/berechnungen/slot_konvention.py`` (Stufe 1, v3.35.2), die *Profil-
Assemblierung* pro Quelle hier (Stufe 2).

**Bewusste Form (Stufe 2/3):** Die Normalizer sind **reine Transforms über bereits
gefetchte Rohdaten** — kein eigenes I/O. So bleibt der parallele ``asyncio.gather``-
Fan-out im Vergleich-Tab (``api/routes/prognosen.py``) unangetastet (Konzept §6).
Eine async-fetchende Adapter-Variante ist Stufe 4 (zusammen mit ``live_wetter``).

**Verhaltensneutralität:** Diese Normalizer reproduzieren die zuvor in
``prognosen.py`` inline gebaute Logik *byte-genau* (gleiche Formeln, gleiche
Rundung, gleiche Ausgabe-Reihenfolge). ``present_stunden`` trägt, welche Slots
echte Datenpunkte haben (IST: nur abgelaufene Stunden; OpenMeteo: nur Indizes mit
GTI-Wert) — damit die variabel lange Ausgabe des Vergleich-Tabs erhalten bleibt.

Nuancen (Konzept §3): IST ist None-tolerant (Datenlücke = ``kw=None``, #135);
Solcast trägt p10/p90-Bänder und füllt fehlende Slots mit 0 (wie bisher); die
Tagessumme einer Quelle stammt NICHT zwingend aus ``Σ slots`` (OpenMeteo/Solcast
ziehen ihren Tageswert aus separaten Tages-Formeln) — die Σ-Invariante gilt hart
nur für IST (dort ist der Tageswert konstruktiv die Slot-Summe).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.core.berechnungen.slot_konvention import openmeteo_preceding_hour_slot

# Leistungsabnahme pro °C über 25 °C (typisch Silizium). Bislang in mehreren
# Modulen dupliziert (prognosen.py, live_wetter.py, solar_forecast_service.py);
# für den OpenMeteo-GTI-Normalizer ist dies die maßgebliche Konstante.
TEMP_COEFFICIENT = 0.004


@dataclass(frozen=True)
class StundenProfil:
    """Kanonisches 24-Slot-Stundenprofil einer Prognosequelle.

    ``slots_kw[h]`` ist die Leistung [kW] im Backward-Slot ``h`` = ``[h-1, h)``.
    ``None`` = Datenlücke (IST ohne gemappten Zähler, #135) — NICHT 0.
    ``present_stunden`` listet (in Ausgabe-Reihenfolge) die Slots mit echtem
    Datenpunkt; alles außerhalb ist „nicht vorhanden" (≠ Lücke mit kw=None).
    """

    datum: date
    quelle: str  # "openmeteo" | "solcast" | "ist"
    slots_kw: tuple[float | None, ...]  # len 24, Index = Backward-Slot
    present_stunden: tuple[int, ...]
    tageswert_kwh: float | None = None
    p10_kw: tuple[float | None, ...] | None = None
    p90_kw: tuple[float | None, ...] | None = None
    unvollstaendig: bool = False  # IST: echtes Datenloch in abgelaufener Stunde


def openmeteo_gti_profil(
    gti_values: list,
    temps: list,
    tag_idx: int,
    kwp: float,
    system_losses: float,
    datum: date | None = None,
) -> StundenProfil:
    """Normalisiert OpenMeteo-GTI-Rohwerte zu einem 24-Slot-Profil (kW).

    Reproduziert die Vergleich-Tab-Formel (``prognosen.py`` vor der Migration):
    ``pv_kw = gti·kwp·(1−losses)/1000`` mit Modultemperatur-Korrektur, ``max(0, …)``,
    ``round(…, 2)``. ``gti_values``/``temps`` sind die *globalen* Stunden-Arrays
    (bis 72 Werte); ``tag_idx`` 0=heute/1=morgen/2=übermorgen wählt das 24er-Fenster.

    OpenMeteos preceding-hour-Wert@Index ``h`` IST bereits Backward-Slot ``h``
    (``openmeteo_preceding_hour_slot`` = Identität, #297, KEIN Shift).
    """
    slots: list[float | None] = [0.0] * 24
    present: list[int] = []
    start = tag_idx * 24
    ende = min(start + 24, len(gti_values))
    for i in range(start, ende):
        h = openmeteo_preceding_hour_slot(i % 24)
        gti = gti_values[i] or 0
        if gti > 0 and kwp > 0:
            pv_kw = gti * kwp * (1 - system_losses) / 1000
            temp = temps[i] if i < len(temps) and temps[i] is not None else None
            if temp is not None:
                aufheizung = min(25, gti / 40)
                modul_temp = temp + aufheizung
                if modul_temp > 25:
                    pv_kw *= (1 - (modul_temp - 25) * TEMP_COEFFICIENT)
            pv_kw = max(0, pv_kw)
        else:
            pv_kw = 0
        slots[h] = round(pv_kw, 2)
        present.append(h)
    return StundenProfil(
        datum=datum,
        quelle="openmeteo",
        slots_kw=tuple(slots),
        present_stunden=tuple(present),
        tageswert_kwh=round(sum(v for v in slots if v), 2),
    )


def solcast_profil(solcast, datum: date | None = None) -> StundenProfil:
    """Normalisiert einen ``SolcastForecast`` zu einem 24-Slot-Profil (kW) mit
    p10/p90-Band. Fehlende Slots werden — wie bisher im Vergleich-Tab — mit 0
    gefüllt (nicht ``None``); Solcast liefert ein durchgehendes 24er-Raster.
    Slot-Mapping passiert bereits im ``solcast_service`` (period_start/-end →
    Backward-Slot via ``slot_konvention``).
    """
    hk = solcast.hourly_kw
    h10 = solcast.hourly_p10_kw
    h90 = solcast.hourly_p90_kw
    slots = tuple(hk[h] if h < len(hk) else 0 for h in range(24))
    p10 = tuple(h10[h] if h < len(h10) else 0 for h in range(24))
    p90 = tuple(h90[h] if h < len(h90) else 0 for h in range(24))
    return StundenProfil(
        datum=datum,
        quelle="solcast",
        slots_kw=slots,
        present_stunden=tuple(range(24)),
        tageswert_kwh=solcast.daily_kwh,
        p10_kw=p10,
        p90_kw=p90,
    )


def ist_profil(ist_rows, jetzt_stunde: int, datum: date | None = None) -> StundenProfil:
    """Normalisiert IST-Stundenzeilen (``TagesEnergieProfil`` für heute) zu einem
    None-toleranten 24-Slot-Profil. ``ist_rows`` muss nach ``stunde`` sortiert sein.

    Issue #135: ``pv_kw=None`` = Datenlücke → Slot bleibt ``None`` und fließt NICHT
    in den Tageswert. Eine Lücke in einer bereits abgelaufenen Stunde (``stunde <
    jetzt_stunde``) setzt ``unvollstaendig=True``; die gerade abgeschlossene Stunde
    wird bewusst nicht geflaggt (HA-Hourly-Row-Verzögerung, siehe prognosen.py).

    ``tageswert_kwh`` ist hier die **rohe, ungerundete** Slot-Summe (≥ 0.0) — der
    Vergleich-Tab braucht sie unverändert für die ``verbleibend``-Rechnung und
    rundet erst an der Response-Grenze (verhaltensneutral zum Inline-Stand).
    """
    slots: list[float | None] = [None] * 24
    present: list[int] = []
    tageswert = 0.0
    unvollstaendig = False
    for row in ist_rows:
        present.append(row.stunde)
        if row.pv_kw is None:
            if row.stunde < jetzt_stunde:
                unvollstaendig = True
            slots[row.stunde] = None
            continue
        slots[row.stunde] = round(row.pv_kw, 2)
        tageswert += row.pv_kw
    return StundenProfil(
        datum=datum,
        quelle="ist",
        slots_kw=tuple(slots),
        present_stunden=tuple(present),
        tageswert_kwh=tageswert,  # roh/ungerundet — Endpoint rundet an Response-Grenze
        unvollstaendig=unvollstaendig,
    )
