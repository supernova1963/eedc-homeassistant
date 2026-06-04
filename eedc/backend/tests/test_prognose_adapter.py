"""
Tests für den zentralen Prognosequellen-Adapter-Layer (services/prognose_adapter).

Spiegelt den Symmetrie-Anker aus ``test_slot_konvention_quellen.py`` auf die
Profil-*Assemblierung*: ein und dasselbe physische Intervall ``[05:00, 06:00)``
muss bei OpenMeteo/GTI, Solcast und IST in **denselben Slot 6** fallen — jetzt
über die Normalizer, die der Vergleich-Tab konsumiert (Stufe 2/3 des Konzepts).

Plus: OpenMeteo-Formel-Golden (Temperatur-Korrektur), Solcast-Null-Füllung +
p10/p90-Band, IST-None-Toleranz (#135) und das ``unvollstaendig``-Flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.services.prognose_adapter import (
    ist_profil,
    openmeteo_gti_profil,
    solcast_profil,
)
from backend.services.solcast_service import SolcastForecast

DATUM = date(2026, 6, 4)


@dataclass
class _IstRow:
    """Minimaler Stand-in für eine TagesEnergieProfil-Stundenzeile."""

    stunde: int
    pv_kw: float | None


def _solcast(hourly_kw, p10=None, p90=None, daily=42.0) -> SolcastForecast:
    return SolcastForecast(
        daily_kwh=daily,
        daily_p10_kwh=daily * 0.8,
        daily_p90_kwh=daily * 1.2,
        tomorrow_kwh=daily,
        tomorrow_p10_kwh=daily * 0.8,
        tomorrow_p90_kwh=daily * 1.2,
        hourly_kw=hourly_kw,
        hourly_p10_kw=p10 if p10 is not None else [v * 0.8 for v in hourly_kw],
        hourly_p90_kw=p90 if p90 is not None else [v * 1.2 for v in hourly_kw],
    )


# ─── OpenMeteo-GTI-Normalizer ───────────────────────────────────────────────


def test_openmeteo_gti_intervall_05_06_in_slot_6_kein_shift():
    gti = [0.0] * 24
    gti[6] = 500.0  # preceding-hour: Wert@6 = [05:00, 06:00)
    p = openmeteo_gti_profil(gti, [15.0] * 24, tag_idx=0, kwp=10.0, system_losses=0.14, datum=DATUM)
    assert p.slots_kw[6] > 0, "[05,06)-Energie nicht in Slot 6"
    assert all(v == 0 for i, v in enumerate(p.slots_kw) if i != 6), "Energie im falschen Slot (+1-Shift?, #297)"
    assert p.present_stunden == tuple(range(24))
    assert p.quelle == "openmeteo"


def test_openmeteo_temperatur_korrektur_golden():
    # gti=800, temp=30, kwp=10, losses=0.14:
    #   pv = 800*10*0.86/1000 = 6.88
    #   aufheizung = min(25, 800/40=20) = 20 → modul_temp = 50
    #   *(1 - (50-25)*0.004) = *(1-0.1) = *0.9 → 6.192 → round2 = 6.19
    gti = [0.0] * 24
    gti[8] = 800.0
    temps = [0.0] * 24
    temps[8] = 30.0
    p = openmeteo_gti_profil(gti, temps, tag_idx=0, kwp=10.0, system_losses=0.14)
    assert p.slots_kw[8] == 6.19


def test_openmeteo_tag_idx_waehlt_24er_fenster():
    gti = [0.0] * 72
    gti[24 + 6] = 500.0  # morgen, Slot 6
    p = openmeteo_gti_profil(gti, [15.0] * 72, tag_idx=1, kwp=10.0, system_losses=0.14)
    assert p.slots_kw[6] > 0
    assert all(v == 0 for i, v in enumerate(p.slots_kw) if i != 6)


def test_openmeteo_truncierte_gti_nur_vorhandene_slots():
    gti = [0.0] * 50  # übermorgen (idx 48,49) nur teilweise vorhanden
    p = openmeteo_gti_profil(gti, [15.0] * 50, tag_idx=2, kwp=10.0, system_losses=0.14)
    assert p.present_stunden == (0, 1)


# ─── Solcast-Normalizer ─────────────────────────────────────────────────────


def test_solcast_intervall_05_06_in_slot_6():
    hk = [0.0] * 24
    hk[6] = 3.0
    p = solcast_profil(_solcast(hk), datum=DATUM)
    assert p.slots_kw[6] == 3.0
    assert p.p10_kw[6] == 3.0 * 0.8
    assert p.p90_kw[6] == 3.0 * 1.2
    assert p.quelle == "solcast"
    assert p.tageswert_kwh == 42.0


def test_solcast_fehlende_slots_mit_null_gefuellt():
    p = solcast_profil(_solcast([1.0] * 10), datum=DATUM)  # nur 10 Stunden geliefert
    assert p.present_stunden == tuple(range(24))
    assert p.slots_kw[10] == 0
    assert p.slots_kw[23] == 0
    assert all(v is not None for v in p.slots_kw), "Solcast füllt mit 0, nicht None"


# ─── IST-Normalizer ─────────────────────────────────────────────────────────


def test_ist_intervall_05_06_in_slot_6():
    rows = [_IstRow(6, 2.5)]
    p = ist_profil(rows, jetzt_stunde=12, datum=DATUM)
    assert p.slots_kw[6] == 2.5
    assert p.present_stunden == (6,)
    assert p.quelle == "ist"


def test_ist_none_toleranz_und_unvollstaendig_flag(monkeypatch=None):
    rows = [_IstRow(0, 1.0), _IstRow(1, 2.0), _IstRow(3, None), _IstRow(4, 4.0)]
    p = ist_profil(rows, jetzt_stunde=5, datum=DATUM)
    assert p.slots_kw[3] is None, "Datenlücke muss None bleiben (#135)"
    assert p.present_stunden == (0, 1, 3, 4)
    assert p.tageswert_kwh == 7.0  # 1+2+4, None fließt nicht ein
    assert p.unvollstaendig is True, "Lücke in abgelaufener Stunde 3 < jetzt 5"


def test_ist_luecke_in_aktueller_stunde_nicht_geflaggt():
    # Stunde 5 == jetzt_stunde → HA-Hourly-Row-Verzögerung, nicht als Loch werten.
    rows = [_IstRow(4, 4.0), _IstRow(5, None)]
    p = ist_profil(rows, jetzt_stunde=5, datum=DATUM)
    assert p.unvollstaendig is False
    assert p.tageswert_kwh == 4.0


def test_ist_tageswert_roh_ungerundet():
    rows = [_IstRow(7, 1.234), _IstRow(8, 2.345)]
    p = ist_profil(rows, jetzt_stunde=12, datum=DATUM)
    assert p.tageswert_kwh == 1.234 + 2.345  # roh, nicht gerundet


# ─── Symmetrie über alle drei Quellen ───────────────────────────────────────


def test_symmetrie_alle_quellen_intervall_05_06_in_slot_6():
    """Dasselbe physische [05:00, 06:00) landet bei OpenMeteo, Solcast und IST in Slot 6."""
    # OpenMeteo
    gti = [0.0] * 24
    gti[6] = 500.0
    om = openmeteo_gti_profil(gti, [15.0] * 24, tag_idx=0, kwp=10.0, system_losses=0.14)
    # Solcast
    hk = [0.0] * 24
    hk[6] = 3.0
    sc = solcast_profil(_solcast(hk))
    # IST
    ist = ist_profil([_IstRow(6, 2.5)], jetzt_stunde=12)

    assert om.slots_kw[6] > 0
    assert sc.slots_kw[6] > 0
    assert ist.slots_kw[6] == 2.5
    # und nirgends sonst Energie
    assert all(v == 0 for i, v in enumerate(om.slots_kw) if i != 6)
    assert all(v == 0 for i, v in enumerate(sc.slots_kw) if i != 6)
    assert all(v in (None, 0) for i, v in enumerate(ist.slots_kw) if i != 6)


# ─── Golden-Äquivalenz: alte Inline-Logik == neuer Adapter-Pfad ──────────────

_TEMP_COEFFICIENT = 0.004


def _alt_openmeteo_inline(gti_values, temps, kwp, losses):
    """Verbatim-Nachbau der vor der Migration in prognosen.py inlinen Schleife.

    Gibt pro Tag eine Liste ``(stunde, kw)`` zurück (Ausgabe-Reihenfolge wie die
    alten ``StundenProfilEintrag``-Listen).
    """
    tagesprofile = [[], [], []]
    for i in range(min(72, len(gti_values))):
        tag_idx = i // 24
        h = i % 24  # openmeteo_preceding_hour_slot = Identität
        gti = gti_values[i] or 0
        if gti > 0 and kwp > 0:
            pv_kw = gti * kwp * (1 - losses) / 1000
            temp = temps[i] if i < len(temps) and temps[i] is not None else None
            if temp is not None:
                aufheizung = min(25, gti / 40)
                modul_temp = temp + aufheizung
                if modul_temp > 25:
                    pv_kw *= (1 - (modul_temp - 25) * _TEMP_COEFFICIENT)
            pv_kw = max(0, pv_kw)
        else:
            pv_kw = 0
        if tag_idx < 3:
            tagesprofile[tag_idx].append((h, round(pv_kw, 2)))
    return tagesprofile


def _neu_openmeteo_via_adapter(gti_values, temps, kwp, losses):
    out = []
    for tag_idx in range(3):
        p = openmeteo_gti_profil(gti_values, temps, tag_idx, kwp=kwp, system_losses=losses)
        out.append([(h, p.slots_kw[h]) for h in p.present_stunden])
    return out


def test_golden_openmeteo_realistisches_3tage_profil():
    # Realistisches, leicht asymmetrisches 72h-Profil mit Temperatur über/unter 25°C.
    gti = [0.0] * 72
    temps = [0.0] * 72
    werte = [40, 130, 280, 440, 590, 690, 745, 760, 715, 600, 430, 250, 110, 25]
    for tag in range(3):
        for offset, (h, val) in enumerate(zip(range(6, 20), werte)):
            gti[tag * 24 + h] = float(val) * (1 + 0.1 * tag)
            temps[tag * 24 + h] = 18.0 + offset  # steigt über 25°C → Korrektur greift
    alt = _alt_openmeteo_inline(gti, temps, kwp=9.5, losses=0.14)
    neu = _neu_openmeteo_via_adapter(gti, temps, kwp=9.5, losses=0.14)
    assert neu == alt


def test_golden_ist_inline_aequivalenz():
    # Alte Inline-IST-Logik vs. ist_profil — inkl. None-Lücke + Summe.
    rows = [_IstRow(6, 1.111), _IstRow(7, None), _IstRow(8, 3.333), _IstRow(9, 2.0)]
    jetzt = 11

    # alt:
    alt_profil = []
    alt_sum = 0.0
    alt_unvoll = False
    for row in rows:
        if row.pv_kw is None:
            if row.stunde < jetzt:
                alt_unvoll = True
            alt_profil.append((row.stunde, None))
            continue
        alt_profil.append((row.stunde, round(row.pv_kw, 2)))
        alt_sum += row.pv_kw

    p = ist_profil(rows, jetzt_stunde=jetzt)
    neu_profil = [(h, p.slots_kw[h]) for h in p.present_stunden]
    assert neu_profil == alt_profil
    assert p.tageswert_kwh == alt_sum
    assert p.unvollstaendig == alt_unvoll
