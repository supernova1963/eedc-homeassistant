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

import logging
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.core.berechnungen.slot_konvention import (
    backward_slot_aus_period_end,
    backward_slot_aus_period_start,
    openmeteo_preceding_hour_slot,
)

logger = logging.getLogger(__name__)

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

    @property
    def hat_messung(self) -> bool:
        """Trägt **mindestens ein** Slot einen Wert? — der Träger für „0 oder —".

        ``tageswert_kwh`` kann das nicht beantworten: ``ist_profil`` startet die
        Summe bei ``0.0`` und liefert sie **nie** als ``None``. Ein Tag ohne
        jeden Zähler und eine gemessene Null (Nacht, Schnee, Anlage aus) haben
        dort denselben Wert. Genau derselbe Träger-Gedanke wie
        ``TagesBilanz.pv_erfasst``: *True, sobald EINE Stunde einen Wert trug.*

        ⛔ Deshalb ist ``tageswert_kwh is not None`` als Unterdrückungs-Regel
        **falsch** — sie wäre immer wahr und machte aus „—" eine 0,0 für
        Anlagen, die gar nichts messen (N-52/N-344 (1), gemessen 29.08.2026).
        """
        return any(v is not None for v in self.slots_kw)


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

    **Achtung (A11/R21-1):** dieser Normalizer rechnet EINE Orientierung mit
    EINER kWp — er ist die Ein-String-Form. Der Prognosen-Vergleich nutzt ihn
    seit v4.0.1 NICHT mehr; seine OM-Roh-Kurve kommt aus dem Multi-String-
    Fan-out des Prognose-Kanons (``KanonTag.om_stundenprofil_kwh``), damit
    Kurve und Tageswert derselben Spalte zusammenpassen. Wer ihn neu einsetzt,
    muss ihn **pro Orientierungsgruppe** aufrufen und die Slots summieren —
    sonst ist der Ein-Abruf-Kollaps zurück. Bleibt hier als Roh-GTI-Baustein
    (und trägt den quellenübergreifenden Slot-Symmetrie-Test).
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

    ``datum`` wählt seit #357 das Profil dieses Tages, sofern Solcast eines
    liefert; sonst bleibt es bei ``hourly_kw`` (heute). Der Tageswert bleibt
    dabei der des jeweiligen Tages aus ``tage_voraus`` — er kommt aus dem
    Sensor-State und ist die genauere Zahl als die Summe der 30-Min-Buckets.
    """
    tages_profil = solcast.profil_fuer(datum) if datum is not None else None
    hk = tages_profil.p50 if tages_profil else solcast.hourly_kw
    h10 = tages_profil.p10 if tages_profil else solcast.hourly_p10_kw
    h90 = tages_profil.p90 if tages_profil else solcast.hourly_p90_kw
    slots = tuple(hk[h] if h < len(hk) else 0 for h in range(24))
    p10 = tuple(h10[h] if h < len(h10) else 0 for h in range(24))
    p90 = tuple(h90[h] if h < len(h90) else 0 for h in range(24))
    tageswert = solcast.daily_kwh
    if tages_profil is not None:
        tag = next(
            (t for t in solcast.tage_voraus if t.get("datum") == datum.isoformat()),
            None,
        )
        if tag is not None:
            tageswert = tag["kwh"]
    return StundenProfil(
        datum=datum,
        quelle="solcast",
        slots_kw=slots,
        present_stunden=tuple(range(24)),
        tageswert_kwh=tageswert,
        p10_kw=p10,
        p90_kw=p90,
    )


# ── SFML (Tom-HA / Solar Forecast ML) Stundenprofil ──────────────────────────
# Anders als OpenMeteo/Solcast liefert SFML ein *echtes* mehrtägiges Stundenprofil
# (evcc-Sensor `…_evcc_solar_prognose`, Attribut `forecast`). Diese Normalizer
# bilden die Roh-Buckets auf das kanonische Backward-Slot-Raster ab, damit das
# Live-Dashboard bei gewählter SFML-Quelle SFMLs eigene Kurvenform zeigt statt
# SFMLs Tagessumme über die OpenMeteo-GTI-Form zu „schmieren" (Einzelquellen-
# Treue, Tracking #110 „A"). KEIN Cross-Quellen-Vergleich.

def _parse_lokale_zeit(wert) -> datetime | None:
    """SFML-Zeitstring → naive Lokalzeit (Europe/Berlin).

    evcc liefert lokale ISO-Strings ohne tz (``2026-06-06T13:00:00``); die
    Slot-Helper rechnen rein wall-clock. tz-aware Eingaben werden defensiv auf
    Berliner Lokalzeit reduziert.
    """
    if not wert:
        return None
    try:
        dt = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo("Europe/Berlin")).replace(tzinfo=None)
    return dt


def sfml_stundenprofile_aus_forecast(
    forecast, heute: date, max_tage: int = 3,
) -> list[list[float]]:
    """SFML/evcc ``forecast`` (``[{start, end, value}]``, **Wh**) → Tages-Stundenprofile.

    Rückgabe: ``max_tage`` Listen à 24 kWh-Slots (Backward-Konvention #144,
    Slot ``h`` = Energie ``[h-1, h)``). Index 0 = heute, 1 = morgen, …

    - **Einheit:** evcc liefert Wh → ÷1000 = kWh (KRITISCH: nicht doppelt skalieren).
    - **Slot:** über das Perioden-Ende (``end``) auf den Backward-Slot abgebildet
      (``backward_slot_aus_period_end``); fehlt ``end``, dient ``start`` als
      Fallback (``backward_slot_aus_period_start``). NICHT naiv per Stunde indexiert
      — die zentrale Slot-Konvention (#144/#297) gilt auch hier, damit SFML im
      Vergleich deckungsgleich zu OpenMeteo/Solcast/IST liegt.
    - **Mehrtägig:** Buckets werden über ihr ``slot_date`` den Tages-Offsets ab
      ``heute`` zugeordnet; alles außerhalb ``[heute, heute+max_tage)`` verworfen.
    """
    profile = [[0.0] * 24 for _ in range(max_tage)]
    if not forecast:
        return profile
    for eintrag in forecast:
        if not isinstance(eintrag, dict):
            continue
        wh = eintrag.get("value")
        if wh is None:
            continue
        try:
            kwh = float(wh) / 1000.0
        except (ValueError, TypeError):
            continue
        ende = _parse_lokale_zeit(eintrag.get("end"))
        if ende is not None:
            slot_date, slot = backward_slot_aus_period_end(ende)
        else:
            start = _parse_lokale_zeit(eintrag.get("start"))
            if start is None:
                continue
            slot_date, slot = backward_slot_aus_period_start(start)
        tag_offset = (slot_date - heute).days
        if 0 <= tag_offset < max_tage and 0 <= slot < 24:
            profile[tag_offset][slot] += kwh
    return [[round(v, 3) for v in tag] for tag in profile]


def sfml_stundenprofil_aus_hours(hours) -> list[float]:
    """SFML ``prognose_heute.hours`` (``{"HH:00": kWh}``, 24 h heute) → 24 kWh-Slots
    (Backward). **Fallback**, wenn die reichere evcc-``forecast`` fehlt — nur heute.

    Schlüssel ``"HH:00"`` = Produktion der Uhr-Stunde ``[HH, HH+1)`` →
    Backward-Slot ``HH+1`` (vgl. ``backward_slot_aus_period_start`` auf ``HH:00``).
    Die letzte Stunde (``23:00``) fiele auf Slot 0 des Folgetags und wird verworfen
    (nachts ~0).
    """
    slots = [0.0] * 24
    if not isinstance(hours, dict):
        return slots
    for key, val in hours.items():
        if val is None:
            continue
        try:
            stunde = int(str(key).split(":")[0])
            kwh = float(val)
        except (ValueError, TypeError):
            continue
        # period_start-Semantik (HH:00 → Slot HH+1); 23:00 → Folgetag, verworfen.
        if 0 <= stunde <= 22:
            slots[stunde + 1] += kwh
    return [round(v, 3) for v in slots]


def sfml_profil(slots_kw, datum: date | None = None) -> StundenProfil:
    """Verpackt ein bereits Backward-Slot-aligntes SFML-Tagesprofil (24 kWh-Werte)
    in das kanonische ``StundenProfil`` (für den Vergleich-Tab, analog
    ``solcast_profil``). Fehlende/None-Slots werden zu 0 — SFML liefert ein
    durchgehendes Raster."""
    slots = tuple(
        round(float(slots_kw[h]), 2) if h < len(slots_kw) and slots_kw[h] is not None else 0.0
        for h in range(24)
    )
    return StundenProfil(
        datum=datum,
        quelle="sfml",
        slots_kw=slots,
        present_stunden=tuple(range(24)),
        tageswert_kwh=round(sum(slots), 2),
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
