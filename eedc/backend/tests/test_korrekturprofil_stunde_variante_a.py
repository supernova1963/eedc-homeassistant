"""Akzeptanztests: stunde-Korrekturprofil (Variante A — Saisonbin × Stunde).

Jahreszeitlich aufgelöste Stundenkorrektur für saisonale Verschattung
(belaubte Bäume): das Sonnenstand-Profil mittelt belaubt/kahl beim gleichen
Sonnenstand weg, das (Monat × Stunde)-Profil trennt es.

Abgedeckt (siehe Übergabe-Prompt UEBERGABE-t2-saisonale-prognose-korrektur):
1. Aggregator: Faktoren pro (Monat, Stunde) aus bekanntem Fixture,
   Saisonbin-Kaskade Monat (≥15 Tage) → Quartal (≥15) → Gesamt (rollierend
   30 Tage, ≥7) bei dünner Belegung; zu dünne Zellen bleiben leer.
2. Lookup: Stufen-Reihenfolge sonnenstand_wetter → stunde → sonnenstand →
   skalar; Mindestbelegung ≥50 Stunden pro Saisonbin; ohne stunde-Profil
   unverändertes Verhalten.
3. E2E-Invariante: Day-Ahead-Stundenprofil mit stunde-Profil ≠ ohne,
   Tagessumme = Σ der korrigierten Stunden.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.korrekturprofil import (
    PROFIL_TYP_SKALAR,
    PROFIL_TYP_SONNENSTAND,
    PROFIL_TYP_SONNENSTAND_WETTER,
    PROFIL_TYP_STUNDE,
    Korrekturprofil,
)
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.korrekturprofil_aggregator import (
    aggregiere_korrekturprofil_anlage,
)
from backend.services.korrekturprofil_lookup import (
    MIN_STUNDEN_STUNDE_SAISONBIN,
    invalidate_cache,
    lookup_korrekturfaktor,
)
from backend.services.wetter.solar_position import bin_key, solar_position_lokal

LAT, LON = 48.1, 11.6  # München — Juni-Mittag liegt sicher über dem Horizont

# Fester Stichtag für deterministische Pools (statt date.today()):
# Gesamt-Fenster (30 Tage rollierend) = 2026-05-02 .. 2026-05-31.
HEUTE = date(2026, 6, 1)


def _prog_profil(werte: dict[int, float]) -> list[float]:
    """24er-Stundenprofil mit kWh-Werten an den angegebenen Slots."""
    profil = [0.0] * 24
    for stunde, kwh in werte.items():
        profil[stunde] = kwh
    return profil


async def _seed_anlage(db: AsyncSession) -> Anlage:
    anlage = Anlage(
        anlagenname="Stunde-Test", leistung_kwp=9.9, latitude=LAT, longitude=LON
    )
    db.add(anlage)
    await db.commit()
    await db.refresh(anlage)
    return anlage


async def _seed_tag(
    db: AsyncSession,
    anlage_id: int,
    datum: date,
    stunden: dict[int, tuple[float, float]],
) -> None:
    """Ein Tag mit Day-Ahead-Profil + stündlichem IST.

    `stunden` = {stunde: (ist_kw, prognose_kwh)}.
    """
    db.add(
        TagesZusammenfassung(
            anlage_id=anlage_id,
            datum=datum,
            pv_prognose_stundenprofil=_prog_profil(
                {h: prog for h, (_, prog) in stunden.items()}
            ),
            stunden_verfuegbar=24,
        )
    )
    for h, (ist, _) in stunden.items():
        db.add(
            TagesEnergieProfil(
                anlage_id=anlage_id, datum=datum, stunde=h, pv_kw=ist
            )
        )


async def _seed_fixture(db: AsyncSession) -> Anlage:
    """2 Monate × feste Stunden-Paare (Übergabe-Akzeptanzkriterium).

    - Mai 1.–16. (16 Tage):   h9 IST 2.0 / Prog 2.5 (→ 0.8), h10 3.0/2.5 (→ 1.2)
    - April 10.–19. (10 Tage): h9 IST 2.75 / Prog 2.5 (→ 1.1) — Monat zu dünn
    - April 1.–3. (3 Tage):    h13 1.0/1.0 — überall unter den Schwellen
    """
    anlage = await _seed_anlage(db)
    for tag in range(1, 17):
        await _seed_tag(
            db, anlage.id, date(2026, 5, tag), {9: (2.0, 2.5), 10: (3.0, 2.5)}
        )
    for tag in range(10, 20):
        await _seed_tag(db, anlage.id, date(2026, 4, tag), {9: (2.75, 2.5)})
    for tag in range(1, 4):
        await _seed_tag(db, anlage.id, date(2026, 4, tag), {13: (1.0, 1.0)})
    await db.commit()
    return anlage


async def _lade_stunde_profil(db: AsyncSession, anlage_id: int) -> Korrekturprofil:
    result = await db.execute(
        select(Korrekturprofil).where(
            Korrekturprofil.anlage_id == anlage_id,
            Korrekturprofil.profil_typ == PROFIL_TYP_STUNDE,
        )
    )
    profil = result.scalar_one_or_none()
    assert profil is not None, "stunde-Profil wurde nicht geschrieben"
    return profil


# ── 1. Aggregator ───────────────────────────────────────────────────────────


async def test_monat_granularitaet_liefert_erwartete_faktoren(db: AsyncSession):
    """Mai hat ≥15 Tage → Zellen kommen aus dem Monats-Pool."""
    anlage = await _seed_fixture(db)
    result = await aggregiere_korrekturprofil_anlage(anlage, db, heute=HEUTE)
    assert result["status"] == "ok"

    profil = await _lade_stunde_profil(db, anlage.id)
    assert profil.faktoren["5"]["9"] == pytest.approx(0.8)
    assert profil.faktoren["5"]["10"] == pytest.approx(1.2)
    assert profil.datenpunkte_pro_bin["5_9"] == 16
    assert profil.datenpunkte_pro_bin["5_10"] == 16
    assert profil.bin_definition["saisonbin"] == "monat"


async def test_kaskade_faellt_auf_quartal_bei_duennem_monat(db: AsyncSession):
    """April h9 hat nur 10 Tage (<15) → Quartal-Pool Q2 (April+Mai, 26 Tage).

    Erwarteter Faktor = Σ(IST)/Σ(Prognose) über beide Monate:
    (16·2.0 + 10·2.75) / (26·2.5) = 59.5/65 = 0.915.
    Juni (0 eigene Tage, gleiches Quartal) bekommt dieselbe Zelle.
    """
    anlage = await _seed_fixture(db)
    await aggregiere_korrekturprofil_anlage(anlage, db, heute=HEUTE)

    profil = await _lade_stunde_profil(db, anlage.id)
    assert profil.faktoren["4"]["9"] == pytest.approx(0.915)
    assert profil.datenpunkte_pro_bin["4_9"] == 26
    assert profil.faktoren["6"]["9"] == pytest.approx(0.915)
    assert profil.datenpunkte_pro_bin["6_9"] == 26


async def test_kaskade_faellt_auf_gesamt_rollierend(db: AsyncSession):
    """Dezember hat weder Monats- noch Quartals-Daten → Gesamt-Pool
    (letzte 30 Tage rollierend, analog Skalar): nur Mai 2.–16. liegt im
    Fenster (15 Tage) — Faktor wie Mai, aber eigener Datenpunkte-Stand."""
    anlage = await _seed_fixture(db)
    await aggregiere_korrekturprofil_anlage(anlage, db, heute=HEUTE)

    profil = await _lade_stunde_profil(db, anlage.id)
    assert profil.faktoren["12"]["9"] == pytest.approx(0.8)
    assert profil.datenpunkte_pro_bin["12_9"] == 15
    assert profil.faktoren["12"]["10"] == pytest.approx(1.2)
    assert profil.datenpunkte_pro_bin["12_10"] == 15


async def test_zu_duenne_zellen_bleiben_leer(db: AsyncSession):
    """April 1.–3. h13: 3 Tage, außerhalb des Gesamt-Fensters — unter allen
    Schwellen → keine h13-Zelle in keinem Monat (kein erfundener Default)."""
    anlage = await _seed_fixture(db)
    result = await aggregiere_korrekturprofil_anlage(anlage, db, heute=HEUTE)

    profil = await _lade_stunde_profil(db, anlage.id)
    for monat_faktoren in profil.faktoren.values():
        assert "13" not in monat_faktoren
    assert not any(k.endswith("_13") for k in profil.datenpunkte_pro_bin)
    # h9 + h10 kaskadieren in alle 12 Monate (Monat/Quartal/Gesamt) → 24 Zellen
    assert result["bins_stunde"] == 24


# ── 2. Lookup-Kaskade ───────────────────────────────────────────────────────


def _stunde_profil_row(
    anlage_id: int,
    faktoren: dict,
    datenpunkte: dict,
) -> Korrekturprofil:
    return Korrekturprofil(
        anlage_id=anlage_id,
        investition_id=None,
        quelle="openmeteo",
        profil_typ=PROFIL_TYP_STUNDE,
        bin_definition={"saisonbin": "monat"},
        faktoren=faktoren,
        datenpunkte_pro_bin=datenpunkte,
        tage_eingegangen=30,
    )


def _sonnenstand_row(anlage_id: int, bk: str, faktor: float) -> Korrekturprofil:
    return Korrekturprofil(
        anlage_id=anlage_id,
        investition_id=None,
        quelle="openmeteo",
        profil_typ=PROFIL_TYP_SONNENSTAND,
        bin_definition={"azimut_aufloesung": 10, "elevation_aufloesung": 10},
        faktoren={bk: faktor},
        datenpunkte_pro_bin={bk: 100},
        tage_eingegangen=60,
    )


JUNI_TAG = date(2026, 6, 15)
STUNDE = 12


def _juni_bin_key() -> str:
    sp = solar_position_lokal(LAT, LON, JUNI_TAG, STUNDE)
    bk = bin_key(sp.azimut, sp.elevation, 10, 10)
    assert bk is not None
    return bk


async def test_stunde_stufe_greift_bei_ausreichender_belegung(db: AsyncSession):
    anlage = await _seed_anlage(db)
    db.add(
        _stunde_profil_row(
            anlage.id,
            faktoren={"6": {"12": 0.75, "9": 0.8}},
            datenpunkte={"6_12": 30, "6_9": 25},  # Σ 55 ≥ 50
        )
    )
    await db.commit()
    invalidate_cache(anlage.id)

    res = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=JUNI_TAG, stunde=STUNDE
    )
    assert res is not None
    assert res.stufe == PROFIL_TYP_STUNDE
    assert res.faktor == pytest.approx(0.75)
    assert res.bin_key == "6_12"
    assert res.datenpunkte == 30


async def test_stunde_steht_vor_sonnenstand(db: AsyncSession):
    """Beide Profile vorhanden → stunde gewinnt (saisonale Trennung)."""
    anlage = await _seed_anlage(db)
    db.add(
        _stunde_profil_row(
            anlage.id,
            faktoren={"6": {"12": 0.75}},
            datenpunkte={"6_12": 60},
        )
    )
    db.add(_sonnenstand_row(anlage.id, _juni_bin_key(), 0.95))
    await db.commit()
    invalidate_cache(anlage.id)

    res = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=JUNI_TAG, stunde=STUNDE
    )
    assert res is not None
    assert res.stufe == PROFIL_TYP_STUNDE
    assert res.faktor == pytest.approx(0.75)


async def test_sonnenstand_wetter_steht_vor_stunde(db: AsyncSession):
    """Wetterstratifizierte Stufe bleibt vorn, wenn Klasse + Bin belegt."""
    anlage = await _seed_anlage(db)
    bk = _juni_bin_key()
    db.add(
        Korrekturprofil(
            anlage_id=anlage.id,
            investition_id=None,
            quelle="openmeteo",
            profil_typ=PROFIL_TYP_SONNENSTAND_WETTER,
            bin_definition={
                "azimut_aufloesung": 10,
                "elevation_aufloesung": 10,
                "wetterklassen": ["klar", "diffus", "wechselhaft"],
            },
            faktoren={f"{bk}_klar": 0.9},
            datenpunkte_pro_bin={f"{bk}_klar": 20},
            tage_eingegangen=60,
        )
    )
    db.add(
        _stunde_profil_row(
            anlage.id, faktoren={"6": {"12": 0.75}}, datenpunkte={"6_12": 60}
        )
    )
    await db.commit()
    invalidate_cache(anlage.id)

    res = await lookup_korrekturfaktor(
        db,
        anlage_id=anlage.id,
        lat=LAT,
        lon=LON,
        datum=JUNI_TAG,
        stunde=STUNDE,
        klasse="klar",
    )
    assert res is not None
    assert res.stufe == PROFIL_TYP_SONNENSTAND_WETTER


async def test_mindestbelegung_unterschritten_faellt_auf_sonnenstand(
    db: AsyncSession,
):
    """Saisonbin-Summe < 50 → stunde-Stufe wird übersprungen."""
    anlage = await _seed_anlage(db)
    db.add(
        _stunde_profil_row(
            anlage.id,
            faktoren={"6": {"12": 0.75}},
            datenpunkte={"6_12": MIN_STUNDEN_STUNDE_SAISONBIN - 1},
        )
    )
    db.add(_sonnenstand_row(anlage.id, _juni_bin_key(), 0.95))
    await db.commit()
    invalidate_cache(anlage.id)

    res = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=JUNI_TAG, stunde=STUNDE
    )
    assert res is not None
    assert res.stufe == PROFIL_TYP_SONNENSTAND
    assert res.faktor == pytest.approx(0.95)


async def test_fehlende_zelle_faellt_durch(db: AsyncSession):
    """Saisonbin gut belegt, aber Stunde ohne Zelle (z. B. Nacht) →
    nächste Stufe (hier Skalar)."""
    anlage = await _seed_anlage(db)
    db.add(
        _stunde_profil_row(
            anlage.id, faktoren={"6": {"12": 0.75}}, datenpunkte={"6_12": 60}
        )
    )
    db.add(
        Korrekturprofil(
            anlage_id=anlage.id,
            investition_id=None,
            quelle="openmeteo",
            profil_typ=PROFIL_TYP_SKALAR,
            bin_definition={"variante": "o12"},
            faktoren={"value": 1.05},
            datenpunkte_pro_bin={"value": 40},
            tage_eingegangen=40,
            faktor_skalar=1.05,
        )
    )
    await db.commit()
    invalidate_cache(anlage.id)

    res = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=JUNI_TAG, stunde=4
    )
    assert res is not None
    assert res.stufe == PROFIL_TYP_SKALAR
    assert res.faktor == pytest.approx(1.05)


async def test_ohne_profile_liefert_none(db: AsyncSession):
    """Regression: ohne Profile bleibt der Legacy-Fallback-Pfad (None)."""
    anlage = await _seed_anlage(db)
    invalidate_cache(anlage.id)

    res = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=JUNI_TAG, stunde=STUNDE
    )
    assert res is None


# ── 3. E2E: Anwendung im Day-Ahead-Stundenprofil ───────────────────────────


async def test_day_ahead_profil_mit_stunde_profil_korrigiert(db: AsyncSession):
    """Wie live_wetter: pro Stunde Lookup → GTI × Faktor. Mit stunde-Profil
    weicht das Profil ab, Stunden ohne Zelle bleiben unverändert und die
    Tagessumme ist exakt die Σ der korrigierten Stunden."""
    anlage = await _seed_anlage(db)
    faktoren = {"6": {str(h): (0.8 if h < 12 else 1.1) for h in range(8, 17)}}
    datenpunkte = {f"6_{h}": 10 for h in range(8, 17)}  # Σ 90 ≥ 50
    db.add(_stunde_profil_row(anlage.id, faktoren=faktoren, datenpunkte=datenpunkte))
    await db.commit()
    invalidate_cache(anlage.id)

    gti = [0.0] * 24
    for h, wert in zip(range(6, 19), [50, 120, 200, 300, 380, 420, 430, 400, 340, 260, 170, 90, 40]):
        gti[h] = float(wert)

    korrigiert: list[float] = []
    for h in range(24):
        kp = await lookup_korrekturfaktor(
            db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=JUNI_TAG, stunde=h
        )
        faktor = kp.faktor if kp is not None else None
        korrigiert.append(gti[h] * faktor if faktor is not None else gti[h])

    # Profil verändert sich nur in den belegten Stunden 8–16
    assert korrigiert != gti
    for h in (6, 7, 17, 18):
        assert korrigiert[h] == gti[h]
    for h in range(8, 12):
        assert korrigiert[h] == pytest.approx(gti[h] * 0.8)
    for h in range(12, 17):
        assert korrigiert[h] == pytest.approx(gti[h] * 1.1)

    # Tagessumme = Σ der korrigierten Stunden (Konsistenz-Invariante,
    # unabhängig nachgerechnet)
    erwartet = (
        sum(gti[h] for h in (6, 7, 17, 18))
        + sum(gti[h] * 0.8 for h in range(8, 12))
        + sum(gti[h] * 1.1 for h in range(12, 17))
    )
    assert sum(korrigiert) == pytest.approx(erwartet)
