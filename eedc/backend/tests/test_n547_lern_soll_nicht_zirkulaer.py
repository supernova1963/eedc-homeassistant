"""N-547: das Korrekturprofil lernt gegen das rohe, gekappte SOLL — nicht gegen
seine eigene Ausgabe.

⛔ **Der Defekt.** Bis zum 22.09.2026 las `korrekturprofil_aggregator` sein SOLL
aus `TagesZusammenfassung.pv_prognose_stundenprofil`. Das ist die **korrigierte**
Kanon-Ausgabe — also das Produkt genau der Faktoren, die der Aggregator gerade
lernt. Aus `f_neu = IST / (roh × f_alt)` wird über den gepoolten Quotienten der
Fixpunkt von `f ↦ r/f`, und der ist **√r, nicht r**. Bei einem wahren Verhältnis
r = 0,85 konvergieren die Faktoren auf 0,922 statt 0,850: die Prognose liegt an
**jedem** Tag um 8,5 % zu hoch — in der Kachel, im HA-Sensor, in der Aussicht.

⭐ **Warum das keine Probe der alten Art fangen konnte.** Jede einzelne Stunde
ist für sich korrekt gerechnet; kein Aufruf ist falsch, keine Formel kippt. Der
Fehler lebt ausschließlich in der **Rückkopplung über Tage** — er wird erst
sichtbar, wenn man den Regelkreis wirklich dreht. Probe (a) dreht ihn 52 Mal.

Hermetisch: In-Memory-DB, fester Stichtag `HEUTE`, Aggregator und Kanon mit
`heute=`. ⛔ **Keine echte Uhr** (Wächter `test_konformitaet_echte_uhr_in_tests`),
**kein Netz** (Socket-Sperre `conftest.py:128-160`) — die Open-Meteo-Schicht wird
in (c)/(f) auf HTTP-Ebene gefälscht, damit der echte Cache-Schlüssel mitgemessen
wird.

Abgedeckt:
  (a) Rundlauf über 52 Tage ⇒ Stufenfaktor **r** (Sprengsatz: Leser zurück auf
      `pv_prognose_stundenprofil` ⇒ √r)
  (b) Live schreibt `pv_prognose_kwh` **roh/ungekappt** + beide Lern-Felder;
      ohne Kanon-Stundenprofil bleiben sie NULL
  (c) Prefetch schreibt Vorhersage-Profil + Lern-Felder, **0 zusätzliche
      Open-Meteo-Abrufe**, #306 und `tage=[None]` sauber
  (d) Übergangsregel an den REALEN Gates (SW 10, Skalar 7, Ende nach 365 Tagen)
  (e) Migration idempotent + Ü1-Rettung über `aggregate_day`
  (f) gesäte AC-Grenze: die Lern-SOLL-Slots liegen **unter** der Grenze
  (g) die drei `pv_prognose_kwh`-Leser bleiben unberührt (roher Eingang)
"""

from __future__ import annotations

import math
from contextlib import asynccontextmanager
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.prognose_korrektur import korrigiere_tagesprofil
from backend.core.investition_parameter import PARAM_WECHSELRICHTER
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.korrekturprofil import (
    PROFIL_TYP_SKALAR,
    PROFIL_TYP_SONNENSTAND_WETTER,
    PROFIL_TYP_STUNDE,
    Korrekturprofil,
)
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.korrekturprofil_aggregator import (
    _KEEP_TAGE,
    _upsert_profil,
    aggregiere_korrekturprofil_anlage,
)
from backend.services.korrekturprofil_lookup import (
    MIN_DATENPUNKTE_SONNENSTAND_WETTER,
    MIN_TAGE_SKALAR,
    invalidate_cache,
    korrekturfaktoren_fuer_tag,
    lookup_korrekturfaktor,
)

pytestmark = pytest.mark.asyncio

LAT, LON = 48.1, 11.6            # München
HEUTE = date(2026, 6, 1)         # fester Stichtag — nie `date.today()`
LERN_TAGE = 52
LERN_VON = HEUTE - timedelta(days=LERN_TAGE)
R_WAHR = 0.85                    # die Wahrheit, die gelernt werden SOLL
KWP = 10.0


def _roh_profil(kwp: float = KWP, spitze: int = 13) -> list[float]:
    """24 Backward-Slots (kWh) — Glocke um die Mittagsspitze."""
    out: list[float] = []
    for h in range(24):
        d = abs(h - spitze)
        out.append(
            round(kwp * 0.8 * max(0.0, math.cos(math.pi * d / 16.0)) ** 1.5, 3)
            if d < 8 else 0.0
        )
    return out


async def _anlage(db: AsyncSession, **kw) -> Anlage:
    anlage = Anlage(
        anlagenname="N-547", leistung_kwp=KWP, latitude=LAT, longitude=LON,
        standort_land="DE", prognose_quelle="eedc", **kw,
    )
    db.add(anlage)
    await db.commit()
    await db.refresh(anlage)
    return anlage


# ══════════════════════════════════════════════════════════════════════════
# (a) Der Rundlauf — die Probe, die den Defekt überhaupt sichtbar macht
# ══════════════════════════════════════════════════════════════════════════

async def _lernschleife(db: AsyncSession, anlage: Anlage) -> list:
    """52 Tage drehen: jeden Tag Faktoren nachschlagen, die **Vorhersage**
    daraus bauen (das ist das zirkuläre Feld), das **Lern-SOLL** daneben roh
    ablegen, IST = r × SOLL messen, aggregieren.

    ⭐ Der Aufbau ist bewusst für BEIDE Lesarten gültig: beide Felder werden
    jeden Tag geschrieben. Welches der Aggregator nimmt, entscheidet allein
    der Produktcode — deshalb schlägt der Sprengsatz hier durch, ohne dass die
    Probe etwas anderes täte.
    """
    roh = _roh_profil()
    ist = [round(R_WAHR * v, 3) for v in roh]
    soll_tag = round(sum(roh), 1)

    for i in range(LERN_TAGE):
        tag = LERN_VON + timedelta(days=i)
        invalidate_cache(anlage.id)
        faktoren = await korrekturfaktoren_fuer_tag(
            db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=tag,
        )
        vorhersage = korrigiere_tagesprofil(roh, faktoren).stundenprofil_export_kwh
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=tag,
            # das ZIRKULÄRE Feld (korrigierte Vorhersage)
            pv_prognose_stundenprofil=list(vorhersage),
            pv_prognose_kwh=soll_tag,
            # das neue, NICHT zirkuläre Lern-SOLL (roh, unkorrigiert)
            lern_soll_stundenprofil_kwh=list(roh),
            lern_soll_kwh=soll_tag,
            stunden_verfuegbar=24, datenquelle="wetter_prognose",
        ))
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=h, pv_kw=ist[h],
            ))
        await db.commit()
        await aggregiere_korrekturprofil_anlage(
            anlage, db, heute=tag + timedelta(days=1),
        )
        invalidate_cache(anlage.id)

    return await korrekturfaktoren_fuer_tag(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=HEUTE,
    )


async def test_a_rundlauf_konvergiert_auf_r_und_nicht_auf_wurzel_r(db):
    """Nach 52 Tagen mit IST = 0,85 × SOLL steht der Stundenfaktor auf 0,85.

    ⛔ **Die Gegenzahl steht mit in der Meldung**, weil sie den Defekt
    benennt: √0,85 = 0,922. Wer den Aggregator zurück auf
    `pv_prognose_stundenprofil` dreht, landet dort — das ist der Sprengsatz
    dieser Probe, und er ist gefahren (Bericht §4).
    """
    anlage = await _anlage(db)
    faktoren = await _lernschleife(db, anlage)

    wurzel = round(math.sqrt(R_WAHR), 3)
    for stunde in (10, 13, 15):
        f = faktoren[stunde]
        assert f is not None, f"Stunde {stunde} ohne Kaskaden-Treffer nach 52 Tagen"
        assert abs(f - R_WAHR) <= 0.005, (
            f"Stunde {stunde}: Faktor {f} statt {R_WAHR}. "
            f"Liegt er bei ~{wurzel}, lernt der Aggregator wieder gegen seine "
            "eigene korrigierte Ausgabe (N-547) — der Fixpunkt von f ↦ r/f "
            "ist die WURZEL des wahren Verhältnisses, nicht das Verhältnis."
        )

    kp = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=HEUTE, stunde=13,
    )
    assert kp is not None and kp.stufe == PROFIL_TYP_STUNDE, (
        f"Erwartet Stufe 'stunde', bekommen: {kp.stufe if kp else None}"
    )


async def test_a2_die_vorhersage_bleibt_die_vorhersage(db):
    """Gegenprobe zur Trennung: das alte Feld trägt weiter die KORRIGIERTE
    Reihe, das neue die rohe — sonst wäre die Trennung nur behauptet."""
    anlage = await _anlage(db)
    await _lernschleife(db, anlage)

    zeile = (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == HEUTE - timedelta(days=1),
        )
    )).scalar_one()

    roh = _roh_profil()
    assert zeile.lern_soll_stundenprofil_kwh[13] == pytest.approx(roh[13]), (
        "Das Lern-SOLL ist nicht mehr die rohe Reihe."
    )
    assert zeile.pv_prognose_stundenprofil[13] < roh[13], (
        "Die Vorhersage müsste nach 51 Lerntagen unter der Rohprognose liegen "
        f"(Faktor ~{R_WAHR}) — sie steht auf "
        f"{zeile.pv_prognose_stundenprofil[13]} gegen roh {roh[13]}."
    )


# ══════════════════════════════════════════════════════════════════════════
# (d) Die Übergangsregel — an den REALEN Gates des Lookups
# ══════════════════════════════════════════════════════════════════════════

async def _profil(db: AsyncSession, anlage_id: int, typ: str) -> Korrekturprofil:
    return (await db.execute(
        select(Korrekturprofil).where(
            Korrekturprofil.anlage_id == anlage_id,
            Korrekturprofil.profil_typ == typ,
        )
    )).scalar_one()


async def _seed_altprofil(
    db: AsyncSession, anlage_id: int, typ: str, *,
    faktoren: dict, datenpunkte: dict, tage: int,
    faktor_skalar: float | None = None, umstellung: date | None = None,
) -> None:
    """Ein Profil, wie es VOR N-547 in der DB steht: ohne Marken, ohne Datum."""
    db.add(Korrekturprofil(
        anlage_id=anlage_id, investition_id=None, quelle="openmeteo",
        profil_typ=typ, bin_definition={}, faktoren=faktoren,
        datenpunkte_pro_bin=datenpunkte, tage_eingegangen=tage,
        faktor_skalar=faktor_skalar, lern_umstellung_am=umstellung,
    ))
    await db.commit()


async def test_d1_bin_unter_dem_gate_behaelt_alten_wert_und_alte_zahl(db):
    """SW-Gate ist 10 Stunden je Bin. Mit 5 neuen bleibt alles beim Alten —
    **inklusive der Datenpunktzahl**: sie ist es, die den Lookup passieren
    lässt. Nur den Faktor zu halten und die Zählung zu ersetzen hieße, den Bin
    still stillzulegen."""
    anlage = await _anlage(db)
    await _seed_altprofil(
        db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER,
        faktoren={"110_30_klar": 0.60}, datenpunkte={"110_30_klar": 40}, tage=40,
    )

    await _upsert_profil(
        db, anlage_id=anlage.id, profil_typ=PROFIL_TYP_SONNENSTAND_WETTER,
        bin_definition={}, faktoren={"110_30_klar": 0.90},
        datenpunkte_pro_bin={"110_30_klar": 5},
        tage_eingegangen=5, heute=HEUTE,
    )
    await db.commit()

    p = await _profil(db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER)
    assert p.faktoren == {"110_30_klar": 0.60}
    assert p.datenpunkte_pro_bin == {"110_30_klar": 40}
    assert p.lern_basis_pro_bin == {"110_30_klar": "alt"}
    assert p.lern_umstellung_am == HEUTE, (
        "Der erste Lauf nach dem Update muss den Beginn der Keep-Regel setzen."
    )


async def test_d2_bin_ueber_dem_gate_nimmt_den_neuen_wert(db):
    """Dieselbe Zeile, 12 statt 5 neue Stunden (Gate 10) ⇒ Wechsel auf neu."""
    anlage = await _anlage(db)
    await _seed_altprofil(
        db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER,
        faktoren={"110_30_klar": 0.60}, datenpunkte={"110_30_klar": 40}, tage=40,
    )
    assert MIN_DATENPUNKTE_SONNENSTAND_WETTER == 10, (
        "Die Probe rechnet mit dem realen Gate — wenn es sich ändert, muss sie "
        "es merken, statt eine eigene Zahl mitzuschleppen."
    )

    await _upsert_profil(
        db, anlage_id=anlage.id, profil_typ=PROFIL_TYP_SONNENSTAND_WETTER,
        bin_definition={}, faktoren={"110_30_klar": 0.90},
        datenpunkte_pro_bin={"110_30_klar": 12},
        tage_eingegangen=12, heute=HEUTE,
    )
    await db.commit()

    p = await _profil(db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER)
    assert p.faktoren == {"110_30_klar": 0.90}
    assert p.datenpunkte_pro_bin == {"110_30_klar": 12}
    assert p.lern_basis_pro_bin == {"110_30_klar": "neu"}


async def test_d3_skalar_haelt_tage_eingegangen_und_faktor_skalar(db):
    """Ü3: beim Skalar hängt **Stufe 4 der ganzen Kaskade** an zwei Feldern,
    die nicht in `faktoren` stehen — `tage_eingegangen` (das Gate, 7) und
    `faktor_skalar` (der gelesene Wert). Wer nur `faktoren` hält, schaltet die
    letzte Rückfallebene ab, ohne dass es jemand sieht."""
    anlage = await _anlage(db)
    await _seed_altprofil(
        db, anlage.id, PROFIL_TYP_SKALAR,
        faktoren={"value": 0.95}, datenpunkte={"value": 151}, tage=151,
        faktor_skalar=0.95,
    )
    assert MIN_TAGE_SKALAR == 7

    await _upsert_profil(
        db, anlage_id=anlage.id, profil_typ=PROFIL_TYP_SKALAR,
        bin_definition={"variante": "o12"}, faktoren={"value": 0.80},
        datenpunkte_pro_bin={"value": 3}, tage_eingegangen=3,
        heute=HEUTE, faktor_skalar=0.80,
    )
    await db.commit()

    p = await _profil(db, anlage.id, PROFIL_TYP_SKALAR)
    assert p.faktoren == {"value": 0.95}
    assert p.tage_eingegangen == 151
    assert p.faktor_skalar == 0.95
    assert p.lern_basis_pro_bin == {"value": "alt"}

    invalidate_cache(anlage.id)
    kp = await lookup_korrekturfaktor(
        db, anlage_id=anlage.id, lat=LAT, lon=LON, datum=HEUTE, stunde=3,
    )
    assert kp is not None and kp.stufe == PROFIL_TYP_SKALAR and kp.faktor == 0.95, (
        "Stufe 4 fällt aus — genau der Ausfall, gegen den Ü3 geschrieben ist."
    )


async def test_d4_nach_dem_keep_fenster_gilt_wieder_vollersatz(db):
    """Nach `_KEEP_TAGE` Tagen ersetzt der neue Wert den alten auch unter dem
    Gate. ⛔ Ohne dieses Ende bliebe ein saisonal nie wieder belegter Bin
    **für immer** auf seinem zirkulär gelernten Faktor stehen."""
    anlage = await _anlage(db)
    await _seed_altprofil(
        db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER,
        faktoren={"110_30_klar": 0.60}, datenpunkte={"110_30_klar": 40}, tage=40,
        umstellung=HEUTE - timedelta(days=_KEEP_TAGE + 1),
    )

    await _upsert_profil(
        db, anlage_id=anlage.id, profil_typ=PROFIL_TYP_SONNENSTAND_WETTER,
        bin_definition={}, faktoren={"110_30_klar": 0.90},
        datenpunkte_pro_bin={"110_30_klar": 5},
        tage_eingegangen=5, heute=HEUTE,
    )
    await db.commit()

    p = await _profil(db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER)
    assert p.faktoren == {"110_30_klar": 0.90}
    assert p.lern_basis_pro_bin == {"110_30_klar": "neu"}

    # Gegenrichtung: einen Tag INNERHALB des Fensters wird gehalten.
    p.faktoren = {"110_30_klar": 0.60}
    p.datenpunkte_pro_bin = {"110_30_klar": 40}
    p.lern_basis_pro_bin = None
    p.lern_umstellung_am = HEUTE - timedelta(days=_KEEP_TAGE)
    await db.commit()
    await _upsert_profil(
        db, anlage_id=anlage.id, profil_typ=PROFIL_TYP_SONNENSTAND_WETTER,
        bin_definition={}, faktoren={"110_30_klar": 0.90},
        datenpunkte_pro_bin={"110_30_klar": 5},
        tage_eingegangen=5, heute=HEUTE,
    )
    await db.commit()
    p = await _profil(db, anlage.id, PROFIL_TYP_SONNENSTAND_WETTER)
    assert p.faktoren == {"110_30_klar": 0.60}, (
        f"Am Tag {_KEEP_TAGE} muss noch gehalten werden — die Grenze ist "
        "inklusiv, sonst kippt das Fenster einen Tag zu früh."
    )


async def test_d5_altbestand_ueberlebt_den_ersten_lauf_ohne_lern_soll(db):
    """**Die eigentliche Regression, gegen die die Keep-Regel steht.**

    Am Morgen nach dem Update gibt es noch KEINE einzige Lern-SOLL-Zeile. Ohne
    Übergangsregel liefe der nächtliche Aggregator mit leeren Pools durch und
    überschriebe jeden Bin mit nichts — das Korrekturprofil einer Anlage wäre
    über Nacht weg, die Prognose fiele wochenlang auf den Legacy-Skalar.
    """
    anlage = await _anlage(db)
    await _seed_altprofil(
        db, anlage.id, PROFIL_TYP_STUNDE,
        faktoren={"6": {"13": 0.88}}, datenpunkte={"6_13": 60}, tage=60,
    )
    await _seed_altprofil(
        db, anlage.id, PROFIL_TYP_SKALAR,
        faktoren={"value": 0.95}, datenpunkte={"value": 151}, tage=151,
        faktor_skalar=0.95,
    )
    # Eine Bestandszeile OHNE Lern-SOLL (genau der Zustand nach dem Update).
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=HEUTE - timedelta(days=1),
        pv_prognose_stundenprofil=_roh_profil(), pv_prognose_kwh=40.0,
        stunden_verfuegbar=24, datenquelle="wetter_prognose",
    ))
    for h in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=HEUTE - timedelta(days=1),
            stunde=h, pv_kw=_roh_profil()[h] * R_WAHR,
        ))
    await db.commit()

    await aggregiere_korrekturprofil_anlage(anlage, db, heute=HEUTE)

    st = await _profil(db, anlage.id, PROFIL_TYP_STUNDE)
    assert st.faktoren == {"6": {"13": 0.88}}, (
        f"Der Stunden-Bin wurde überschrieben: {st.faktoren}"
    )
    assert st.datenpunkte_pro_bin == {"6_13": 60}
    assert st.lern_basis_pro_bin == {"6_13": "alt"}

    sk = await _profil(db, anlage.id, PROFIL_TYP_SKALAR)
    assert sk.faktor_skalar == 0.95 and sk.tage_eingegangen == 151


# ══════════════════════════════════════════════════════════════════════════
# (g) Die drei `pv_prognose_kwh`-Leser bleiben unberührt
# ══════════════════════════════════════════════════════════════════════════

async def test_g_genauigkeits_schwelle_rechnet_weiter_mit_dem_rohen_tageswert(db):
    """W1: `pv_prognose_kwh` ist und bleibt der ROHE Tageswert, und die drei
    Leser multiplizieren ihn mit dem Legacy-Lernfaktor. Die neuen Felder
    daneben ändern daran nichts — geprüft am HA-Export-Pfad
    (`prognose_genauigkeit_service`), der die Abweichungs-Ampel speist."""
    import backend.api.routes.live_wetter as lw
    from backend.services import prognose_genauigkeit_service as pgs

    anlage = await _anlage(db)
    roh, lernfaktor, ist = 100.0, 0.9, 81.0   # eedc = 90 ⇒ Fehler (90-81)/81

    async def _fake_lernfaktor(anlage_id, db_, quelle="openmeteo"):
        return lernfaktor

    for i in range(1, 6):
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=HEUTE - timedelta(days=i),
            pv_prognose_kwh=roh,
            # dieselbe Zeile trägt jetzt zusätzlich das GEKAPPTE Lern-SOLL —
            # es darf den Leser nicht anfassen.
            lern_soll_kwh=roh * 0.7,
            lern_soll_stundenprofil_kwh=_roh_profil(),
            komponenten_kwh={"pv_1": ist},
            stunden_verfuegbar=24, datenquelle="wetter_prognose",
        ))
    await db.commit()

    orig = lw._get_lernfaktor
    lw._get_lernfaktor = _fake_lernfaktor
    try:
        mae, n = await pgs.eedc_mae_prozent(db, anlage.id, heute=HEUTE, tage=30)
    finally:
        lw._get_lernfaktor = orig

    erwartet = round(abs((roh * lernfaktor - ist) / ist) * 100, 1)  # der Layer rundet auf 1
    assert n == 5
    assert mae == pytest.approx(erwartet, abs=0.05), (
        f"MAE {mae} statt {erwartet} — der Leser rechnet nicht mehr mit dem "
        "rohen Tageswert × Legacy-Faktor."
    )


# ══════════════════════════════════════════════════════════════════════════
# Gemeinsame Open-Meteo-Fälschung für (c) und (f)
#
# ⭐ Gefälscht wird die **HTTP-Schicht** (`solar_forecast_service.httpx`), nicht
# `get_solar_prognose`. Nur so läuft der echte Cache-Schlüssel mit
# (`gti:lat:lon:neigung:ausrichtung:abruf_days:modell`) — und genau er ist die
# Behauptung von B3: der Kanon-Aufruf im Prefetch kostet **null** zusätzliche
# Abrufe, weil er denselben Schlüssel trifft. Mit einem Fake auf
# `get_solar_prognose` wäre diese Aussage ungemessen.
# ══════════════════════════════════════════════════════════════════════════

_OM_TAGE = 16


def _om_antwort(start: date) -> dict:
    """Eine Open-Meteo-Antwort, wie `fetch_gti_forecast` sie erwartet."""
    zeiten: list[str] = []
    gti: list[float] = []
    for i in range(_OM_TAGE):
        tag = start + timedelta(days=i)
        for h in range(24):
            zeiten.append(f"{tag.isoformat()}T{h:02d}:00")
            d = abs(h - 12)
            gti.append(round(950.0 * max(0.0, math.cos(math.pi * d / 14.0)) ** 1.5, 1)
                       if d < 7 else 0.0)
    n = len(zeiten)
    tage = [(start + timedelta(days=i)).isoformat() for i in range(_OM_TAGE)]
    return {
        "hourly": {
            "time": zeiten,
            "global_tilted_irradiance": gti,
            "shortwave_radiation": [v * 0.8 for v in gti],
            "temperature_2m": [20.0] * n,
            "snowfall": [0.0] * n,
            "cloud_cover": [10] * n,
            "precipitation": [0.0] * n,
            "weather_code": [0] * n,
        },
        "daily": {
            "time": tage,
            "temperature_2m_max": [24.0] * _OM_TAGE,
            "temperature_2m_min": [12.0] * _OM_TAGE,
            "sunshine_duration": [36000.0] * _OM_TAGE,
            "precipitation_sum": [0.0] * _OM_TAGE,
            "snowfall_sum": [0.0] * _OM_TAGE,
            "weather_code": [0] * _OM_TAGE,
            "shortwave_radiation_sum": [6.0] * _OM_TAGE,
        },
    }


class _Antwort:
    def __init__(self, daten: dict) -> None:
        self._daten = daten

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._daten


def _falsche_open_meteo(monkeypatch, start: date) -> list[dict]:
    """Zählt jeden **HTTP-Abruf** und liefert dieselbe Antwort zurück."""
    import backend.services.solar_forecast_service as sfs
    from backend.services.wetter import cache as wetter_cache

    wetter_cache._cache.clear()
    abrufe: list[dict] = []
    daten = _om_antwort(start)

    class _Client:
        def __init__(self, *a, **kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **kw):
            abrufe.append(dict(params or {}))
            return _Antwort(daten)

    monkeypatch.setattr(
        sfs, "httpx", SimpleNamespace(
            AsyncClient=_Client,
            TimeoutException=Exception,
            HTTPStatusError=Exception,
            RequestError=Exception,
        ),
    )
    return abrufe


async def _pv_modul(db: AsyncSession, anlage: Anlage, **felder) -> Investition:
    inv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="String Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=KWP,
        anschaffungskosten_gesamt=10000.0, aktiv=True,
        ausrichtung="Süd", neigung_grad=35, parameter={}, **felder,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return inv


# ══════════════════════════════════════════════════════════════════════════
# (c) Der Prefetch
# ══════════════════════════════════════════════════════════════════════════

def _speichern_in_die_testdb(monkeypatch, db: AsyncSession) -> None:
    """`_speichere_prognose` öffnet über `get_session()` eine EIGENE Sitzung —
    in Tests zeigt die auf die Wegwerf-Datei der Produktiv-Engine (N-414) und
    damit auf eine DB ohne unsere Anlage. Für die Probe wird sie auf die
    Test-Sitzung umgelenkt; der Aufrufpfad selbst bleibt unangetastet."""
    import backend.core.database as dbmod

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr(dbmod, "get_session", _session)


async def _prefetch_umgebung(monkeypatch) -> None:
    """Die beiden Nicht-Solar-Abrufe des Prefetch stilllegen — sie gehen an
    andere Endpunkte und würden ohne Fake echtes Netz anfassen."""
    import backend.services.prefetch_service as pf

    async def _leer(*a, **kw):
        return {}

    monkeypatch.setattr(pf, "fetch_open_meteo_forecast", _leer)
    monkeypatch.setattr(pf, "_prefetch_live_wetter", _leer)


async def test_c_prefetch_schreibt_vorhersage_und_lern_soll_ohne_zusatz_abruf(
    db, monkeypatch,
):
    """Der Prefetch legt Day-Ahead-Vorhersage **und** Lern-SOLL an — und der
    Kanon-Aufruf dafür kostet **0 zusätzliche Open-Meteo-Abrufe**.

    ⛔ Die Null ist die eigentliche Aussage: eine Orientierungsgruppe ⇒ **ein**
    HTTP-Abruf, obwohl `get_solar_prognose` zweimal läuft (einmal für den
    Prefetch selbst, einmal im Kanon). Stünde hier 2, hätte der Umbau die
    Open-Meteo-Last verdoppelt.
    """
    import backend.services.prefetch_service as pf

    anlage = await _anlage(db)
    await _pv_modul(db, anlage)
    abrufe = _falsche_open_meteo(monkeypatch, HEUTE)
    await _prefetch_umgebung(monkeypatch)
    _speichern_in_die_testdb(monkeypatch, db)

    # Der Kanon schlägt den Legacy-Skalar nach — der liest sonst die DB.
    import backend.api.routes.live_wetter as lw

    async def _skalar(anlage_id, db_, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(lw, "_get_lernfaktor", _skalar)

    ergebnis = await pf._prefetch_for_anlage(anlage, db, heute=HEUTE)
    assert ergebnis["status"] == "ok"

    assert len(abrufe) == 1, (
        f"{len(abrufe)} Open-Meteo-Abrufe statt 1 — der Kanon trifft den "
        f"Cache-Schlüssel des Prefetch nicht mehr. Parameter: {abrufe}"
    )

    zeile = (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == HEUTE,
        )
    )).scalar_one()

    assert zeile.pv_prognose_kwh and zeile.pv_prognose_kwh > 0
    assert zeile.pv_prognose_stundenprofil is not None, (
        "Ohne Live-Besuch entsteht kein Day-Ahead-Profil — genau die Lücke, "
        "die B3 schließt."
    )
    assert zeile.lern_soll_stundenprofil_kwh is not None
    assert len(zeile.lern_soll_stundenprofil_kwh) == 24
    assert zeile.lern_soll_kwh == pytest.approx(
        round(sum(zeile.lern_soll_stundenprofil_kwh), 1), abs=0.15,
    ), "Tages-SOLL ist nicht die Summe seiner Slots."
    # Ohne Kappung ist das Lern-SOLL die rohe Reihe — und die Vorhersage
    # daneben ist die mit 0,9 korrigierte.
    assert zeile.pv_prognose_stundenprofil[12] < zeile.lern_soll_stundenprofil_kwh[12]


async def test_c2_unvollstaendiger_fanout_friert_auch_kein_lern_soll_ein(
    db, monkeypatch,
):
    """#306 gilt für die neuen Felder genauso: ein untergewichteter Fan-out
    ist keine kleinere Wahrheit, sondern eine falsche Zahl."""
    import backend.services.prefetch_service as pf
    import backend.services.prognose_kanon as pk

    anlage = await _anlage(db)
    await _pv_modul(db, anlage)
    _falsche_open_meteo(monkeypatch, HEUTE)
    await _prefetch_umgebung(monkeypatch)
    _speichern_in_die_testdb(monkeypatch, db)

    # ⚠ Der Tag trägt bewusst eine VOLLSTÄNDIGE Reihe und ein Profil — nur
    # `om_vollstaendig` steht auf False. Sonst prüfte die Probe den
    # Profil-Guard (das tut b2) statt des #306-Riegels, und ein Sprengsatz am
    # Riegel bliebe still (gemessen 22.09.).
    roh = _roh_profil()

    async def _unvollstaendig(db_, anlage_, days=4, skip_jitter=False, heute=None):
        return pk.KanonPrognose(
            tage=[pk.KanonTag(
                datum=HEUTE.isoformat(), om_kwh=round(sum(roh), 1),
                eedc_kwh=round(sum(roh) * 0.9, 1),
                vm_kwh=None, nm_kwh=None,
                profil=korrigiere_tagesprofil(roh, [0.9] * 24),
                om_stundenprofil_kwh=[round(v, 3) for v in roh],
                om_vollstaendig=False,
            )],
            rest_heute_kwh=None, ist_bisher_kwh=None,
            heute_rollend_kwh=None, skalar_fallback=None,
        )

    monkeypatch.setattr(pk, "kanon_tagesprognose", _unvollstaendig)
    await pf._prefetch_for_anlage(anlage, db, heute=HEUTE)

    zeile = (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
        )
    )).scalar_one_or_none()
    if zeile is not None:
        assert zeile.lern_soll_stundenprofil_kwh is None
        assert zeile.lern_soll_kwh is None
        assert zeile.pv_prognose_stundenprofil is None


async def test_c3_kanon_ohne_tag_stuerzt_nicht_ab(db, monkeypatch):
    """Ü2-Absicherung: `tage = [None]` (der Fall, den `days=1` nach
    Mitternacht erzeugt hätte) darf den Prefetch nicht umbringen.

    ⚠ **Was sie belegt und was nicht** (gemessen am Sprengsatz, 22.09.): ein
    None-Zugriff INNERHALB des `try` um den Kanon-Aufruf wird dort ohnehin
    geschluckt — dagegen prüft diese Probe nichts. Sie greift für die Guards
    **hinter** dem `try` (`kanon_nutzbar`, `hat_lern_reihe`); ein Sprengsatz
    dort macht sie rot.
    """
    import backend.services.prefetch_service as pf
    import backend.services.prognose_kanon as pk

    anlage = await _anlage(db)
    await _pv_modul(db, anlage)
    _falsche_open_meteo(monkeypatch, HEUTE)
    await _prefetch_umgebung(monkeypatch)
    _speichern_in_die_testdb(monkeypatch, db)

    async def _leerer_tag(db_, anlage_, days=4, skip_jitter=False, heute=None):
        return pk.KanonPrognose(
            tage=[None], rest_heute_kwh=None, ist_bisher_kwh=None,
            heute_rollend_kwh=None, skalar_fallback=None,
        )

    monkeypatch.setattr(pk, "kanon_tagesprognose", _leerer_tag)
    ergebnis = await pf._prefetch_for_anlage(anlage, db, heute=HEUTE)
    assert ergebnis["status"] == "ok"


# ══════════════════════════════════════════════════════════════════════════
# (f) Die AC-Grenze — das Lern-SOLL ist GEKAPPT
# ══════════════════════════════════════════════════════════════════════════

async def test_f_lern_soll_liegt_unter_der_ac_grenze(db, monkeypatch):
    """Mit gepflegter Wechselrichter-Grenze liegt **jeder** Lern-SOLL-Slot
    unter ihr — und die Rohsumme darüber.

    ⛔ Das ist keine Kosmetik: ein **ungekapptes** SOLL hieße, dass der
    Aggregator die physikalische Grenze des Wechselrichters als dauerhaften
    Prognosefehler in die Mittagsfaktoren schreibt. Die Anlage würde für
    Abregelung bestraft, die sie nicht vermeiden kann.
    """
    import backend.services.prognose_kanon as pk
    import backend.api.routes.live_wetter as lw

    grenze = 4.0
    anlage = await _anlage(db)
    modul = await _pv_modul(db, anlage)
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1500.0,
        aktiv=True,
        parameter={PARAM_WECHSELRICHTER["MAX_LEISTUNG_KW"]: grenze},
    )
    db.add(wr)
    await db.commit()
    await db.refresh(wr)
    modul.parent_investition_id = wr.id
    await db.commit()

    _falsche_open_meteo(monkeypatch, HEUTE)

    async def _skalar(anlage_id, db_, quelle="openmeteo"):
        return 1.0

    monkeypatch.setattr(lw, "_get_lernfaktor", _skalar)

    kanon = await pk.kanon_tagesprognose(
        db, anlage, days=1, skip_jitter=True, heute=HEUTE,
    )
    tag = kanon.tage[0]
    assert tag.grenzen_kw, (
        "Ohne zugeordnete Grenze misst diese Probe nichts — "
        f"zuordne_grenzen lieferte {tag.grenzen_kw!r} (Modul {modul.id})."
    )

    ueber = [(h, v) for h, v in enumerate(tag.om_stundenprofil_kwh) if v > grenze + 1e-6]
    assert not ueber, f"Lern-SOLL-Slots über der Grenze {grenze} kW: {ueber}"
    assert tag.abregelung_om_kwh and tag.abregelung_om_kwh > 0, (
        "Ohne Abregelung greift die Kappung gar nicht — die Probe wäre blind."
    )
    assert tag.roh_kwh > tag.om_kwh, (
        f"roh_kwh {tag.roh_kwh} müsste über dem gekappten om_kwh {tag.om_kwh} "
        "liegen — sonst ist die Rohsumme nicht roh."
    )
    assert tag.roh_kwh == pytest.approx(
        tag.om_kwh + tag.abregelung_om_kwh, abs=0.11,
    )


# ══════════════════════════════════════════════════════════════════════════
# (b) Der Live-Pfad — `pv_prognose_kwh` ist ab jetzt ROH
# ══════════════════════════════════════════════════════════════════════════

_GRENZE_KW = 4.0


def _kanon_tag(mit_stundenprofil: bool = True):
    """Ein Kanon-Tag mit echter Kappung — roh > gekappt > korrigiert.

    Drei verschiedene Zahlen, damit die Probe unterscheiden KANN, welche der
    Live-Pfad schreibt. Mit nur einer wäre sie blind.
    """
    import backend.services.prognose_kanon as pk

    roh = _roh_profil()
    gekappt = [min(v, _GRENZE_KW) for v in roh]
    profil = korrigiere_tagesprofil(gekappt, [0.9] * 24)
    return pk.KanonTag(
        datum=HEUTE.isoformat(),
        om_kwh=round(sum(gekappt), 1),
        eedc_kwh=profil.tageswert_kwh,
        vm_kwh=None, nm_kwh=None,
        profil=profil if mit_stundenprofil else None,
        om_stundenprofil_kwh=[round(v, 3) for v in gekappt] if mit_stundenprofil else None,
        om_vollstaendig=True,
        abregelung_om_kwh=round(sum(roh) - sum(gekappt), 2),
        abregelung_om_stundenprofil_kwh=[round(r - g, 3) for r, g in zip(roh, gekappt)],
        grenzen_kw={"wr:1": _GRENZE_KW},
    )


async def _live_mit_kanon(db, monkeypatch, tag) -> list[tuple]:
    """Fährt den Live-Erfolgspfad und fängt die Argumente von
    `_speichere_prognose` ab (Muster wie `test_live_wetter_erfolgspfad`)."""
    import backend.api.routes.live_wetter as lw
    import backend.services.prognose_kanon as pk

    zeiten = [f"{HEUTE.isoformat()}T{h:02d}:00" for h in range(24)]
    wetter = {
        "hourly": {
            "time": zeiten,
            "temperature_2m": [15.0] * 24,
            "weather_code": [1] * 24,
            "cloud_cover": [30] * 24,
            "precipitation": [0.0] * 24,
            "shortwave_radiation": [0.0] * 6 + [300.0] * 12 + [0.0] * 6,
            "sunshine_duration": [0.0] * 6 + [3000.0] * 12 + [0.0] * 6,
            "global_tilted_irradiance": [0.0] * 6 + [400.0] * 12 + [0.0] * 6,
        },
        "daily": {
            "temperature_2m_min": ["11.0"], "temperature_2m_max": ["19.0"],
            "sunrise": [f"{HEUTE.isoformat()}T06:00"],
            "sunset": [f"{HEUTE.isoformat()}T20:00"],
        },
    }
    monkeypatch.setattr(lw, "_cache_get", lambda *a, **k: (wetter, None, True))

    async def _kanon(db_, anlage_, days=4, skip_jitter=False, heute=None):
        return pk.KanonPrognose(
            tage=[tag, None, None, None], rest_heute_kwh=1.0,
            ist_bisher_kwh=0.0, heute_rollend_kwh=1.0, skalar_fallback=0.9,
        )

    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon)

    aufrufe: list[tuple] = []

    async def _nichts():
        return None

    def _mitschnitt(*args, **kwargs):
        aufrufe.append((args, kwargs))
        return _nichts()

    monkeypatch.setattr(lw, "_speichere_prognose", _mitschnitt)
    return aufrufe


async def test_b_live_schreibt_den_rohen_tageswert_und_das_lern_soll(
    db, monkeypatch,
):
    """W1: der Live-Pfad schreibt `pv_prognose_kwh` **roh und ungekappt** —
    dieselbe Lage wie der Prefetch. Bis 22.09.2026 schrieb er `eedc_kwh`
    (korrigiert **und** gekappt) in dasselbe Feld; „letzter gewinnt" machte
    daraus eine Größe, die je nach Tageszeit etwas anderes bedeutete."""
    from backend.api.routes.live_wetter import get_live_wetter

    anlage = await _anlage(db)
    await _pv_modul(db, anlage)
    tag = _kanon_tag()
    aufrufe = await _live_mit_kanon(db, monkeypatch, tag)

    res = await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)
    assert res["verfuegbar"] is True, f"Erfolgspfad nicht erreicht: {res.get('grund')}"
    assert len(aufrufe) == 1, "Der Persistenz-Aufruf fehlt."

    args, kwargs = aufrufe[0]
    geschrieben = args[2]

    assert geschrieben == pytest.approx(tag.roh_kwh, abs=0.05), (
        f"Geschrieben wurde {geschrieben}. Roh (Soll) = {tag.roh_kwh}, "
        f"gekappt = {tag.om_kwh}, korrigiert = {tag.eedc_kwh} — der Live-Pfad "
        "schreibt wieder eine andere Lage als der Prefetch (N-547/W1)."
    )
    assert geschrieben != pytest.approx(tag.eedc_kwh, abs=0.05)
    assert geschrieben != pytest.approx(tag.om_kwh, abs=0.05)

    assert kwargs["lern_kwh"] == tag.om_kwh, "Lern-SOLL-Tageswert ist nicht om_kwh."
    assert kwargs["lern_stundenprofil"] == tag.om_stundenprofil_kwh
    assert max(kwargs["lern_stundenprofil"]) <= _GRENZE_KW + 1e-6, (
        "Das Lern-SOLL muss GEKAPPT sein."
    )
    # Die Vorhersage daneben ist die korrigierte Reihe (2 Nachkommastellen aus
    # dem Chart-Slot) — nicht dieselbe Zahl wie das Lern-SOLL.
    assert kwargs["pv_stundenprofil"][12] == pytest.approx(
        tag.profil.stundenprofil_export_kwh[12], abs=0.01,
    )


async def test_b2_ohne_kanon_stundenprofil_bleiben_die_lern_felder_leer(
    db, monkeypatch,
):
    """Im OpenMeteo-Schätzpfad (Tagessumme ohne Hourly) gibt es keine gekappte
    Reihe — dann NULL statt einer erfundenen. ⛔ Auch `lern_soll_kwh`: dort ist
    `om_kwh` die UNGEKAPPTE Summe und damit das falsche SOLL."""
    from backend.api.routes.live_wetter import get_live_wetter

    anlage = await _anlage(db)
    await _pv_modul(db, anlage)
    tag = _kanon_tag(mit_stundenprofil=False)
    aufrufe = await _live_mit_kanon(db, monkeypatch, tag)

    await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)
    assert len(aufrufe) == 1
    _, kwargs = aufrufe[0]
    assert kwargs["lern_stundenprofil"] is None
    assert kwargs["lern_kwh"] is None, (
        "Ohne Stundenreihe ist `om_kwh` die ungekappte Tagessumme — als "
        "Lern-SOLL wäre sie auf einer gekappten Anlage unerreichbar."
    )


async def test_b3_speichere_prognose_legt_die_felder_an_und_haelt_sie(
    db, monkeypatch,
):
    """Die Schreibfunktion selbst: Stundenreihe **first-write-wins**,
    Tageswert **rollend** — beide Pfade (INSERT und UPDATE)."""
    from backend.api.routes.live_wetter import _speichere_prognose

    anlage = await _anlage(db)
    _speichern_in_die_testdb(monkeypatch, db)
    erst = _roh_profil()
    spaeter = [round(v * 1.1, 3) for v in erst]

    await _speichere_prognose(
        anlage.id, HEUTE, 60.0, lern_stundenprofil=erst, lern_kwh=40.0,
    )
    zeile = (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.datum == HEUTE)
    )).scalar_one()
    assert zeile.lern_soll_stundenprofil_kwh == erst
    assert zeile.lern_soll_kwh == 40.0

    await _speichere_prognose(
        anlage.id, HEUTE, 62.0, lern_stundenprofil=spaeter, lern_kwh=41.0,
    )
    await db.refresh(zeile)
    assert zeile.lern_soll_stundenprofil_kwh == erst, (
        "Die Lern-Reihe ist Day-Ahead — der zweite Abruf des Tages darf sie "
        "nicht überschreiben."
    )
    assert zeile.lern_soll_kwh == 41.0, (
        "Der Tageswert rollt dagegen mit, wie `pv_prognose_kwh` auch."
    )


# ══════════════════════════════════════════════════════════════════════════
# (e) Migration + Ü1-Rettung
# ══════════════════════════════════════════════════════════════════════════

_NEUE_SPALTEN = {
    "tages_zusammenfassung": ("lern_soll_stundenprofil_kwh", "lern_soll_kwh"),
    "korrekturprofile": ("lern_basis_pro_bin", "lern_umstellung_am"),
}


async def test_e1_migration_legt_die_spalten_an_und_ist_idempotent(tmp_path):
    """Zweimal migrieren darf nicht knallen — und eine Bestandszeile behält
    NULL (kein Backfill, „nicht erhoben" ist keine Zahl)."""
    from sqlalchemy import inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.core.database import Base, run_migrations
    import backend.models  # noqa: F401  — Modelle registrieren

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'m.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Den Zustand VOR N-547 herstellen.
            for tabelle, spalten in _NEUE_SPALTEN.items():
                for spalte in spalten:
                    await conn.execute(
                        text(f"ALTER TABLE {tabelle} DROP COLUMN {spalte}")
                    )
            await conn.execute(text(
                "INSERT INTO tages_zusammenfassung (anlage_id, datum, "
                "stunden_verfuegbar, source_provenance, created_at, updated_at) "
                "VALUES (1, '2026-05-01', 24, '{}', '2026-05-01', '2026-05-01')"
            ))

        for lauf in (1, 2):
            async with engine.begin() as conn:
                await run_migrations(conn)
            async with engine.begin() as conn:
                def _spalten(sync_conn, tabelle):
                    return {c["name"] for c in inspect(sync_conn).get_columns(tabelle)}

                for tabelle, spalten in _NEUE_SPALTEN.items():
                    vorhanden = await conn.run_sync(_spalten, tabelle)
                    fehlend = set(spalten) - vorhanden
                    assert not fehlend, f"Lauf {lauf}, {tabelle}: {fehlend} fehlen"

        async with engine.begin() as conn:
            res = await conn.execute(text(
                "SELECT lern_soll_kwh, lern_soll_stundenprofil_kwh "
                "FROM tages_zusammenfassung WHERE datum = '2026-05-01'"
            ))
            assert res.fetchone() == (None, None), (
                "Bestandszeilen dürfen keinen Wert bekommen — ein Backfill aus "
                "der korrigierten Reihe wäre geraten, nicht gemessen."
            )
    finally:
        await engine.dispose()


async def test_e2_aggregate_day_rettet_das_lern_soll(db):
    """Ü1 — **die blockierende Bedingung des ganzen Baus.**

    `aggregate_day` macht ein Delete-and-Recreate der TZ-Zeile, und der Job
    `energie_profil_heute` läuft **alle 15 Minuten**. Stünden die beiden neuen
    Felder nicht in `_PROGNOSE_FELDER_RETTEN`, wäre das Lern-SOLL binnen einer
    Viertelstunde wieder weg — genau so verlor v3.31.7 den Day-Ahead-Snapshot,
    und die Korrekturprofil-Heatmap blieb monatelang leer.
    """
    from unittest.mock import AsyncMock, patch
    from datetime import datetime

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    anlage = await _anlage(db, sensor_mapping={})
    tag = HEUTE - timedelta(days=1)
    reihe = _roh_profil()

    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=tag, stunden_verfuegbar=24,
        datenquelle="ha_statistiken",
        pv_prognose_kwh=60.2, pv_prognose_stundenprofil=reihe,
        lern_soll_stundenprofil_kwh=reihe, lern_soll_kwh=42.0,
    ))
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(tag, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug", value_kwh=100.0,
    ))
    await db.commit()

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        # Zählerlücken wie HA (E5): der Snapshot-Tageswert kommt aus der Tagestabelle.
        "backend.services.snapshot.aggregator.snapshot_tagestabelle",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ), patch(
        # Die beiden Holer, die sonst echtes Netz anfassen (Open-Meteo-Archiv
        # und aWATTar) — die Socket-Sperre lässt sie nicht durch, und ein
        # blockierter Zugriff gehört nicht in eine grüne Probe.
        "backend.services.energie_profil._helpers._get_wetter_ist",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.energie_profil._helpers._get_strompreis_stunden",
        new=AsyncMock(return_value=SimpleNamespace(
            sensor={}, bezug={}, einspeisung={}, boerse={},
        )),
    ):
        ergebnis = await aggregate_day(anlage, tag, db, source=Source.SCHEDULER)

    assert ergebnis is not None
    assert ergebnis.lern_soll_stundenprofil_kwh == reihe, (
        "Das Lern-SOLL hat das Delete-and-Recreate nicht überlebt — "
        "`_PROGNOSE_FELDER_RETTEN` fehlt das Feld (Ü1)."
    )
    assert ergebnis.lern_soll_kwh == 42.0
