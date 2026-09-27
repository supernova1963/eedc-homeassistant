"""N-555 Stufe 3 — Ladeblock-Zuordnung (Konzept Heimladung/Fahrverbrauch 7.2, Regel 9, Anhang D).

Abnahme am **nachgestellten Zwei-Auto-Fall** aus Gernots evcc-Sitzungen (Lab-Recorder
Juni–August 2026, Wallbox 1360 / Fahrzeug 2614, nur lesend exportiert —
``fixtures/n555_stufe3_evcc_sitzungen.json``, erzeugt über die echte
``get_hourly_slots_for_day`` gegen eine Kopie der Recorder-Tabellen). Die zwölf Sitzungen
werden auf zwei synthetische Fahrzeug-Zähler verteilt (Auftrag S3-5):
A = S1, S3, S5, S7, S0a, S0c · B = S2, S4, S6, S8, S0b, S0d.

Proben P1–P10 (Auftrag S3-5) und W-C (Anhang D); jede trägt einen Sprengsatz im Baubericht
(``~/.claude/plans/opus-berichte/N555-S3-BAU.md``).

Schwesterdateien: test_n555_stufe2_messung_je_auto.py (Regel 2/3/7, der Entscheid ohne Blöcke),
test_zaehlerluecken_lts_tabelle.py (die Slot-Tabelle, aus der die Blöcke lesen),
test_daten_checker_emob_pool_pflege.py (Regel 7).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.emob_ladeblock import EmobLadeblock
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services import emob_ladebloecke_speicher as speicher
from backend.services.emob_ladebloecke import (
    BlockMonat,
    FahrzeugSprung,
    WallboxStunde,
    bilde_ladebloecke,
    block_monate,
    stunden_beginn,
    verteile_auf_monate,
)
from backend.services.emob_ladebloecke_speicher import (
    aktualisiere_ladebloecke_des_tages,
    wallbox_stunden_aus_tabelle,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "n555_stufe3_evcc_sitzungen.json").read_text()
)
A, B = 1, 2
#: Sitzung → (Tag, Slot des Sprungs, Auto). Slot h = Stunde [h−1, h).
SITZUNGEN = {
    "S0a": ("2026-06-05", 17, A), "S0b": ("2026-06-05", 18, B), "S0c": ("2026-06-05", 19, A),
    "S0d": ("2026-06-06", 17, B), "S1": ("2026-07-08", 19, A), "S2": ("2026-07-15", 11, B),
    "S3": ("2026-07-27", 10, A), "S4": ("2026-08-06", 18, B), "S5": ("2026-08-06", 20, A),
    "S6": ("2026-08-20", 20, B), "S7": ("2026-08-21", 16, A), "S8": ("2026-08-23", 12, B),
}
REIHENFOLGE = sorted(SITZUNGEN, key=lambda s: (SITZUNGEN[s][0], SITZUNGEN[s][1]))


def _tabelle_stunden(tag: str) -> dict:
    """Die Stunden eines Fixture-Tages in der Form von ``TagesTabelle.stunden``."""
    t = FIXTURE["tage"][tag]
    out = {}
    for h in range(24):
        k = str(h)
        w = t["wallbox"].get(k)
        if not w:
            continue
        nb, ei = t["netzbezug"].get(k), t["einspeisung"].get(k)
        bl, be = t["batt_ladung"].get(k), t["batt_entladung"].get(k)
        spannen = {}
        if w[1] > 1:
            spannen["wallbox"] = w[1]
        if nb and nb[1] > 1:
            spannen["netzbezug"] = nb[1]
        out[h] = {
            "wallbox": w[0],
            "netzbezug": nb[0] if nb else None,
            "einspeisung": ei[0] if ei else None,
            "batterie_netto": (bl[0] - be[0]) if bl and be else None,
            "spannen": spannen or None,
        }
    return out


def _fahrzeug_slots(tag: str, auto: int) -> dict:
    """Der synthetische Zähler eines Autos an einem Tag: nur seine Sitzungssprünge."""
    return {
        h: (FIXTURE["tage"][t]["fahrzeug"][str(h)][0], 1)
        for s, (t, h, a) in SITZUNGEN.items() if t == tag and a == auto
    }


def _zeitreihe():
    stunden = []
    for tag in sorted(FIXTURE["tage"]):
        stunden += wallbox_stunden_aus_tabelle(date.fromisoformat(tag), _tabelle_stunden(tag))
    spruenge = [
        FahrzeugSprung(a, stunden_beginn(date.fromisoformat(t), h), FIXTURE["tage"][t]["fahrzeug"][str(h)][0])
        for s, (t, h, a) in SITZUNGEN.items()
    ]
    return stunden, spruenge


@pytest.fixture(scope="module")
def harness():
    stunden, spruenge = _zeitreihe()
    bloecke = bilde_ladebloecke(stunden, spruenge)
    return {"stunden": stunden, "spruenge": spruenge,
            "je_sitzung": dict(zip(REIHENFOLGE, bloecke)), "bloecke": bloecke}


# ═════════════════════════════════════════════════════════════════════════════
# S3-1 / S3-5 (a) — der Harness über die zwölf Sitzungen
# ═════════════════════════════════════════════════════════════════════════════

def test_p1_autos_und_rest_ergeben_die_wallbox(harness):
    """P1: Σ A + Σ B + Rest = Wallbox über die Sitzungstage, Rest < 0,2 kWh."""
    wb = sum(s.kwh for s in harness["stunden"])
    a = sum(b.kwh for b in harness["bloecke"] if b.inv_id == A)
    b_ = sum(b.kwh for b in harness["bloecke"] if b.inv_id == B)
    rest = wb - a - b_
    assert wb == pytest.approx(108.734, abs=1e-6)
    assert abs(rest) < 0.2
    assert a + b_ + rest == pytest.approx(wb)


def test_p2_menge_je_auto_ist_die_summe_der_spruenge(harness):
    """P2 (G2): Σ der monatsverteilten Blöcke je Auto = Σ seiner Sprünge — exakt."""
    je = block_monate(harness["bloecke"])
    for auto in (A, B):
        spruenge = sum(s.kwh for s in harness["spruenge"] if s.inv_id == auto)
        verteilt = sum(m.get(auto, BlockMonat()).kwh for m in je.values())
        assert verteilt == pytest.approx(spruenge, abs=1e-9)
    assert sum(s.kwh for s in harness["spruenge"] if s.inv_id == A) == pytest.approx(57.552)
    assert sum(s.kwh for s in harness["spruenge"] if s.inv_id == B) == pytest.approx(51.155)


def test_p3_uebergabe_in_derselben_stunde_wird_nach_restmengen_geteilt(harness):
    """P3 (W5): 05.06.2026 17–18 Uhr, Wallbox 0,790 — S0b (B) 0,414, S0c (A) den Rest 0,376."""
    stunde = datetime(2026, 6, 5, 17)
    s0b = {s.beginn: s.kwh for s in harness["je_sitzung"]["S0b"].stunden}
    s0c = {s.beginn: s.kwh for s in harness["je_sitzung"]["S0c"].stunden}
    assert s0b == {stunde: pytest.approx(0.414)}
    assert s0c[stunde] == pytest.approx(0.376)
    assert s0c[datetime(2026, 6, 5, 18)] == pytest.approx(2.843)


def test_p4_zwei_vorgaenge_am_selben_tag_ueberlappen_nicht(harness):
    """P4: 06.08.2026 — S4 (B) 15–18 Uhr, S5 (A) 18–20 Uhr, keine Stunde doppelt."""
    s4 = harness["je_sitzung"]["S4"]
    s5 = harness["je_sitzung"]["S5"]
    assert [s.beginn.hour for s in s4.stunden] == [15, 16, 17]
    assert [s.beginn.hour for s in s5.stunden] == [18, 19]
    assert not {s.beginn for s in s4.stunden} & {s.beginn for s in s5.stunden}
    assert sum(s.kwh for s in s4.stunden) == pytest.approx(8.765)
    assert sum(s.kwh for s in s5.stunden) == pytest.approx(3.046)


def test_p5_gebuendelte_wallbox_stunde_27_07(harness):
    """P5 (W-A, Anhang D): die 11,413 kWh stehen in EINEM Bündel (n = 49). Menge = Sprung,
    Kennzeichen 1,0, Lücke vermerkt, kein ableitbarer PV-Anteil (⇒ Wallbox-Monatsanteil)."""
    s3 = harness["je_sitzung"]["S3"]
    assert s3.kwh == pytest.approx(11.413)
    assert s3.stunden_gedeckt == pytest.approx(1.0)
    assert s3.luecke is True
    assert [(s.kwh, s.n) for s in s3.stunden] == [(pytest.approx(11.413), 49)]
    assert s3.pv_kwh is None
    bm = block_monate([s3])[(2026, 7)][A]
    assert bm.kwh_ohne_pv == pytest.approx(11.413)
    assert bm.ladevorgaenge_mit_luecke == 1 and bm.ladevorgaenge_ungedeckt == 0


def test_p6_drip_stunde_bei_s1_gehoert_nicht_zur_menge(harness):
    """P6: 07.07.2026 20–21 Uhr trägt 0,022 kWh (angesteckt über Nacht). Die Stunden 13–19 Uhr
    decken den Sprung auf 0,05 kWh — der Drip bleibt im Rest, Kennzeichen 0,9988."""
    s1 = harness["je_sitzung"]["S1"]
    assert datetime(2026, 7, 7, 20) not in {s.beginn for s in s1.stunden}
    assert [s.beginn.hour for s in s1.stunden] == [13, 14, 15, 16, 17, 18]
    assert s1.stunden_gedeckt == pytest.approx(0.9988)


def test_p7_monatswechsel_synthetisch_verteilt_nach_blockenergie():
    """P7 (W3): S7 auf 31.07. 21 Uhr … 01.08. 02 Uhr verschoben ⇒ Juli 9,992 / August 4,769."""
    werte = [1.484, 4.346, 4.158, 3.509, 1.258]
    beginn = datetime(2026, 7, 31, 21)
    stunden = [WallboxStunde(beginn + timedelta(hours=i), w) for i, w in enumerate(werte)]
    (block,) = bilde_ladebloecke(stunden, [FahrzeugSprung(A, beginn + timedelta(hours=4), 14.761)])
    monate = verteile_auf_monate(block)
    assert monate[(2026, 7)][0] == pytest.approx(9.992, abs=5e-4)
    assert monate[(2026, 8)][0] == pytest.approx(4.769, abs=5e-4)
    assert sum(k for k, _ in monate.values()) == pytest.approx(14.761)


def test_p8_pv_anteil_des_blocks_aus_der_stundenrechnung(harness):
    """P8 (D-2): der PV-Anteil eines Blocks ist die Stundenrechnung (Einspeise-Deckung) über
    seine ableitbaren Stunden, auf den Sprung skaliert.

    Abgenommen als Konsistenzprobe (Master 27.09.), keine Toleranz gegen evcc. Benannte Grenze:
    mit der Regel bis 4.0.50 kWh-gewichtet 77,7 % gegen evcc 98,4 %; seit N-569 (Speicher-
    Entladung ist Eigenstrom, Anhang E) 96,9 % — s. `test_n569_fixture_pv_anteil_und_speicheranteil`.
    """
    from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab, stunde_aus_bilanzwerten

    # S1: 08.07. 13–19 Uhr, alle Stunden n = 1; Σ Blockenergie 18,580 ≠ Sprung 18,602 —
    # so prüft die Probe auch die Skalierung auf den Sprung (G2).
    s4 = harness["je_sitzung"]["S1"]
    stunden = _tabelle_stunden("2026-07-08")
    pv = 0.0
    for s in s4.stunden:
        h = s.beginn.hour + 1
        st = stunden[h]
        teil = leite_pv_anteil_ab([stunde_aus_bilanzwerten(
            ladung=st["wallbox"], netzbezug=st["netzbezug"], einspeisung=st["einspeisung"],
            batterie_spalte=-st["batterie_netto"],
        )])
        pv += s.kwh * teil.pv_kwh / teil.ladung_kwh
    assert sum(s.kwh for s in s4.stunden) != pytest.approx(s4.kwh, abs=1e-3)
    assert s4.pv_kwh == pytest.approx(pv * s4.kwh / sum(s.kwh for s in s4.stunden), abs=1e-3)


def test_kennzeichen_unter_eins_wenn_die_wallbox_die_menge_nicht_zaehlt():
    """Anhang D (W-A): ``stunden_gedeckt`` < 1 nur, wenn die Wallbox die Menge wirklich nicht
    gezählt hat — gestellt: Sprung 10 kWh, Wallbox-Stunden 4 kWh. Menge bleibt der Sprung."""
    b0 = datetime(2026, 8, 1, 10)
    (block,) = bilde_ladebloecke(
        [WallboxStunde(b0, 2.0), WallboxStunde(b0 + timedelta(hours=1), 2.0)],
        [FahrzeugSprung(A, b0 + timedelta(hours=1), 10.0)],
    )
    assert block.kwh == 10.0
    assert block.stunden_gedeckt == pytest.approx(0.4)
    assert block_monate([block])[(2026, 8)][A].ladevorgaenge_ungedeckt == 1


def test_p10_sprung_ohne_blockstunde_zaehlt_im_monat_des_sprungs():
    """P10 (G2): Wallbox ganz ausgefallen — Monat des Sprungs, Kennzeichen 0, kein Anteil."""
    (block,) = bilde_ladebloecke([], [FahrzeugSprung(A, datetime(2026, 8, 1, 0), 7.0)])
    assert block.stunden == () and block.stunden_gedeckt == 0.0 and block.pv_kwh is None
    assert verteile_auf_monate(block) == {(2026, 8): (7.0, None)}
    bm = block_monate([block])[(2026, 8)][A]
    pv, netz = bm.aufteilung(0.25)          # der Wallbox-Monatsanteil teilt die Menge (D-2)
    assert (pv, netz) == (pytest.approx(1.75), pytest.approx(5.25))


def test_d4_mikrosprung_ist_kleinstblock_aber_kein_ladevorgang():
    """D-4: 0,004 kWh (Standby-Drip des Fahrzeug-Zählers) — die Menge zählt, kein Ladevorgang."""
    b0 = datetime(2026, 7, 9, 12)
    (block,) = bilde_ladebloecke([WallboxStunde(b0, 0.004)], [FahrzeugSprung(A, b0, 0.004)])
    bm = block_monate([block])[(2026, 7)][A]
    assert bm.kwh == pytest.approx(0.004) and bm.ladevorgaenge == 0


def test_schranke_voriger_sprung_irgendeines_autos():
    """Punkt 2: höchstens bis zur Stunde des vorigen Sprungs (einschließlich) — auch eines
    anderen Autos. Der Block von B nimmt keine Stunde vor A's Sprung."""
    b0 = datetime(2026, 8, 2, 10)
    stunden = [WallboxStunde(b0 + timedelta(hours=i), 3.0) for i in range(4)]
    a_, b_ = bilde_ladebloecke(stunden, [
        FahrzeugSprung(A, b0 + timedelta(hours=1), 2.0),
        FahrzeugSprung(B, b0 + timedelta(hours=3), 9.0),
    ])
    # A nimmt 2 aus seiner Sprungstunde (11 Uhr); B nimmt 13, 12 und den Rest 1 von 11 Uhr —
    # 10 Uhr liegt vor dem vorigen Sprung und bleibt, obwohl B's Menge nicht erreicht ist.
    assert [(s.beginn.hour, s.kwh) for s in a_.stunden] == [(11, 2.0)]
    assert min(s.beginn for s in b_.stunden) == b0 + timedelta(hours=1)
    assert b_.stunden_gedeckt == pytest.approx((1.0 + 3.0 + 3.0) / 9.0, abs=1e-4)


# ═════════════════════════════════════════════════════════════════════════════
# S3-2/S3-3 — Ablage und Hook (über die Datenbank)
# ═════════════════════════════════════════════════════════════════════════════

async def _lab_anlage(db):
    a = Anlage(anlagenname="S3", leistung_kwp=12.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1))
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="A", anschaffungsdatum=date(2024, 1, 1))
    eb = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="B", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([wb, ea, eb])
    await db.flush()
    await db.commit()
    return a, wb, ea, eb


async def _hook_ueber_die_fixture(db, monkeypatch, a, ea, eb):
    """Ruft den Hook Tag für Tag in Datumsfolge auf, wie `aggregate_day` es täte — die
    Stunden von D−1 liegen danach als `TagesEnergieProfil` (Spalten-Konvention)."""
    monkeypatch.setattr(
        speicher, "fahrzeug_zaehler_lts",
        lambda anlage, invs, datum: {"zaehler.A": ea.id, "zaehler.B": eb.id},
    )
    geschrieben = []
    for tag in sorted(FIXTURE["tage"]):
        d = date.fromisoformat(tag)
        stunden = _tabelle_stunden(tag)
        tabelle = SimpleNamespace(stunden=stunden, zusatz_slots={
            "zaehler.A": _fahrzeug_slots(tag, A), "zaehler.B": _fahrzeug_slots(tag, B),
        })
        geschrieben += await aktualisiere_ladebloecke_des_tages(
            db, a, d, {}, tabelle, "external:ha_statistics:hourly",
        ) or []
        for h, s in stunden.items():
            db.add(TagesEnergieProfil(
                anlage_id=a.id, datum=d, stunde=h, wallbox_kw=s["wallbox"],
                netzbezug_kw=s["netzbezug"], einspeisung_kw=s["einspeisung"],
                batterie_kw=None if s["batterie_netto"] is None else -s["batterie_netto"],
                spannen=s["spannen"],
            ))
        await db.commit()
    return geschrieben


@pytest.mark.asyncio
async def test_hook_schreibt_dieselben_bloecke_wie_der_harness(db, monkeypatch, harness):
    """S3-3: Tag für Tag über den Hook (D−1 aus den gespeicherten Stunden, voriger Sprung aus
    den gespeicherten Blöcken) entstehen dieselben zwölf Blöcke wie in einem Zug."""
    a, wb, ea, eb = await _lab_anlage(db)
    await _hook_ueber_die_fixture(db, monkeypatch, a, ea, eb)
    zeilen = (await db.execute(select(EmobLadeblock).order_by(EmobLadeblock.ende))).scalars().all()
    assert len(zeilen) == 12
    for z, s in zip(zeilen, REIHENFOLGE):
        erwartet = harness["je_sitzung"][s]
        assert z.investition_id == (ea.id if erwartet.inv_id == A else eb.id)
        assert z.kwh == pytest.approx(erwartet.kwh)
        assert z.stunden_gedeckt == pytest.approx(erwartet.stunden_gedeckt, abs=1e-4)
        assert z.luecke == erwartet.luecke
        assert (z.pv_kwh is None) == (erwartet.pv_kwh is None)
        if z.pv_kwh is not None:
            assert z.pv_kwh == pytest.approx(erwartet.pv_kwh, abs=1e-3)
        assert z.quelle == "ha_statistics" and z.regel == "sprung_rueckwaerts"


@pytest.mark.asyncio
async def test_p9_zweiter_lauf_aendert_nichts(db, monkeypatch):
    """P9: jeder Tag ein zweites Mal durch den Hook — die Tabelle bleibt Zeile für Zeile gleich."""
    a, wb, ea, eb = await _lab_anlage(db)
    await _hook_ueber_die_fixture(db, monkeypatch, a, ea, eb)

    def _stand(zeilen):
        return [(z.investition_id, z.beginn, z.ende, z.kwh, z.pv_kwh, z.netz_kwh, z.stunden,
                 z.stunden_gedeckt, z.luecke) for z in zeilen]

    vorher = _stand((await db.execute(select(EmobLadeblock).order_by(EmobLadeblock.ende))).scalars().all())
    for tag in sorted(FIXTURE["tage"]):
        tabelle = SimpleNamespace(stunden=_tabelle_stunden(tag), zusatz_slots={
            "zaehler.A": _fahrzeug_slots(tag, A), "zaehler.B": _fahrzeug_slots(tag, B),
        })
        await aktualisiere_ladebloecke_des_tages(
            db, a, date.fromisoformat(tag), {}, tabelle, "external:ha_statistics:hourly",
        )
        await db.commit()
    db.expire_all()
    nachher = _stand((await db.execute(select(EmobLadeblock).order_by(EmobLadeblock.ende))).scalars().all())
    assert nachher == vorher


@pytest.mark.asyncio
async def test_hook_ohne_fahrzeug_zaehler_raeumt_den_tag(db, monkeypatch):
    """D-5: ohne Wallbox-Zähler oder ohne Auto mit „Heim: gesamt" keine Blöcke — alte des
    Tages werden entfernt (eine gelöschte Zuordnung hinterlässt keine Messung)."""
    a, wb, ea, eb = await _lab_anlage(db)
    db.add(EmobLadeblock(anlage_id=a.id, investition_id=ea.id, beginn=datetime(2026, 8, 6, 15),
                         ende=datetime(2026, 8, 6, 18), kwh=8.0, stunden=[], stunden_gedeckt=0.0,
                         luecke=False, regel="sprung_rueckwaerts", quelle="ha_statistics"))
    await db.commit()
    monkeypatch.setattr(speicher, "fahrzeug_zaehler_lts", lambda *a_, **k: {})
    tab = SimpleNamespace(stunden=_tabelle_stunden("2026-08-06"), zusatz_slots={})
    assert await aktualisiere_ladebloecke_des_tages(
        db, a, date(2026, 8, 6), {}, tab, "external:ha_statistics:hourly",
    ) is None
    await db.commit()
    assert (await db.execute(select(EmobLadeblock))).scalars().all() == []


def test_fahrzeug_zaehler_nur_neben_einer_wallbox_mit_ladezaehler():
    """D-5: der Hook greift bei Wallbox-Ladezähler UND Auto mit Quelle an „Heim: gesamt" —
    auch bei EINEM Auto; ohne Wallbox-Zähler nicht."""
    wb = SimpleNamespace(id=1, typ="wallbox", ist_aktiv_an=lambda d: True)
    ea = SimpleNamespace(id=2, typ="e-auto", ist_aktiv_an=lambda d: True)
    sensor = lambda eid: {"strategie": "sensor", "sensor_id": eid}  # noqa: E731
    mit = SimpleNamespace(sensor_mapping={"investitionen": {
        "1": {"felder": {"ladung_kwh": sensor("sensor.wb")}},
        "2": {"felder": {"ladung_kwh": sensor("sensor.auto")}},
    }})
    ohne_wb = SimpleNamespace(sensor_mapping={"investitionen": {
        "2": {"felder": {"ladung_kwh": sensor("sensor.auto")}},
    }})
    invs = {"1": wb, "2": ea}
    assert speicher.fahrzeug_zaehler_lts(mit, invs, date(2026, 8, 1)) == {"sensor.auto": 2}
    assert speicher.fahrzeug_zaehler_lts(ohne_wb, invs, date(2026, 8, 1)) == {}


# ═════════════════════════════════════════════════════════════════════════════
# S3-4 — der Leser: W-C, Monats-Fakten, Regel 7, E-Auto-Hub
# ═════════════════════════════════════════════════════════════════════════════

from backend.services.energie_profil.monats_aus_tagen import emob_je_auto  # noqa: E402
from backend.services.monats_fakten import lade_monats_fakten  # noqa: E402

PROV_FORM = {"verbrauch_daten.ladung_kwh": {"source": "manual:form"}}


async def _marken(db, anlage_id, von: date, bis: date, *, ohne: tuple = ()):
    d = von
    while d <= bis:
        if d not in ohne:
            db.add(TagesZusammenfassung(anlage_id=anlage_id, datum=d, verworfen={}))
        d += timedelta(days=1)
    await db.commit()


def _block(anlage_id, inv_id, stunden: list[tuple[datetime, float]], kwh: float, pv=None):
    ende = max(b for b, _ in stunden) + timedelta(hours=1)
    return EmobLadeblock(
        anlage_id=anlage_id, investition_id=inv_id, beginn=min(b for b, _ in stunden), ende=ende,
        kwh=kwh, pv_kwh=pv, netz_kwh=None if pv is None else kwh - pv,
        stunden=[{"beginn": b.isoformat(), "kwh": k, "n": 1, "pv_anteil": None} for b, k in stunden],
        stunden_gedeckt=round(sum(k for _, k in stunden) / kwh, 4), luecke=False,
        regel="sprung_rueckwaerts", quelle="ha_statistics",
    )


@pytest.mark.asyncio
async def test_wc_bloecke_gelten_nur_mit_marke_an_jedem_tag(db):
    """W-C (Anhang D): ein Tag des Monats ohne Regelmarke ⇒ keine Blöcke (Stufe 2);
    alle Tage mit Marke ⇒ die Blockmenge."""
    a, wb, ea, eb = await _lab_anlage(db)
    db.add(_block(a.id, ea.id, [(datetime(2026, 6, 10, 12), 5.0)], 5.0, pv=4.0))
    await db.commit()
    await _marken(db, a.id, date(2026, 6, 1), date(2026, 6, 30), ohne=(date(2026, 6, 20),))
    invs = [wb, ea, eb]
    assert await emob_je_auto(db, a.id, invs, 2026, 6) == {}
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 6, 20), verworfen={}))
    await db.commit()
    bm = (await emob_je_auto(db, a.id, invs, 2026, 6))[ea.id]
    assert (bm.kwh, bm.pv_kwh, bm.ladevorgaenge) == (5.0, 4.0, 1)


@pytest.mark.asyncio
async def test_wc_altbestand_ohne_marke_zaehlt_nicht(db):
    """W-C: eine Tageszeile ohne Regelmarke (NULL, Altbestand) erfüllt die Bedingung nicht."""
    a, wb, ea, eb = await _lab_anlage(db)
    db.add(_block(a.id, ea.id, [(datetime(2026, 6, 10, 12), 5.0)], 5.0))
    await _marken(db, a.id, date(2026, 6, 1), date(2026, 6, 30), ohne=(date(2026, 6, 3),))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 6, 3), verworfen=None))
    await db.commit()
    assert await emob_je_auto(db, a.id, [wb, ea, eb], 2026, 6) == {}


async def _zwei_auto_monat(db, *, a_zeile=None):
    """Juni 2026: Wallbox 40 kWh (20 PV), Auto A mit Zähler (gespeichert „Heim: gesamt" 30),
    Auto B ohne Messung. A's Blöcke im Juni: 12 kWh (PV 9)."""
    a, wb, ea, eb = await _lab_anlage(db)
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=6,
                                  verbrauch_daten={"ladung_kwh": 40.0, "ladung_pv_kwh": 20.0}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2026, monat=6,
                                  verbrauch_daten=a_zeile or {"ladung_kwh": 30.0, "km_gefahren": 100},
                                  source_provenance=PROV_FORM))
    db.add(InvestitionMonatsdaten(investition_id=eb.id, jahr=2026, monat=6,
                                  verbrauch_daten={"km_gefahren": 100}))
    db.add(_block(a.id, ea.id, [(datetime(2026, 6, 10, 12), 12.0)], 12.0, pv=9.0))
    await db.commit()
    await _marken(db, a.id, date(2026, 6, 1), date(2026, 6, 30))
    return a, wb, ea, eb


@pytest.mark.asyncio
async def test_s3_4_bloecke_sind_die_messung_des_autos_in_den_monats_fakten(db):
    """Regel 9 Punkt 3: A trägt seine Blöcke (12 kWh, PV 9), nicht den gespeicherten
    „Heim: gesamt" (30); B bekommt den Rest 28 kWh (PV 11)."""
    a, wb, ea, eb = await _zwei_auto_monat(db)
    (fakt,) = [f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (2026, 6)]
    je = fakt.emob.je_auto
    assert fakt.emob.ladung_kwh == pytest.approx(40.0)
    assert fakt.emob.ladung_pv_kwh == pytest.approx(20.0)
    assert je[ea.id].ladung_kwh == pytest.approx(12.0)
    assert je[ea.id].pv_kwh == pytest.approx(9.0)
    assert je[eb.id].ladung_kwh == pytest.approx(28.0)
    assert je[eb.id].pv_kwh == pytest.approx(11.0)


@pytest.mark.asyncio
async def test_s3_4_ohne_marke_rechnet_der_monat_nach_stufe_2(db):
    """W-C über die Schicht: fehlt die Marke an einem Tag, trägt A seinen gespeicherten Wert."""
    a, wb, ea, eb = await _zwei_auto_monat(db)
    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == a.id, TagesZusammenfassung.datum == date(2026, 6, 15),
    ))).scalar_one()
    tz.verworfen = None
    await db.commit()
    from backend.services.emob_kontext import lade_emob_kontext
    imd = (await db.execute(select(InvestitionMonatsdaten))).scalars().all()
    kontext = await lade_emob_kontext(db, a.id, [wb, ea, eb], imd)
    e = kontext.ctx.entscheide[(2026, 6)]
    assert e.je_auto[ea.id].ladung_kwh == pytest.approx(30.0)
    assert e.bloecke_je_auto == {}


@pytest.mark.asyncio
async def test_s3_4_heim_pv_netz_gehen_vor_den_bloecken(db):
    """D-5: „Heim: PV/Netz" am Auto sind seine Messung — die Blöcke treten nur an die Stelle
    von „Heim: gesamt"."""
    a, wb, ea, eb = await _zwei_auto_monat(
        db, a_zeile={"ladung_pv_kwh": 3.0, "ladung_netz_kwh": 2.0, "km_gefahren": 100},
    )
    from backend.services.emob_kontext import lade_emob_kontext
    imd = (await db.execute(select(InvestitionMonatsdaten))).scalars().all()
    e = (await lade_emob_kontext(db, a.id, [wb, ea, eb], imd)).ctx.entscheide[(2026, 6)]
    assert (e.je_auto[ea.id].pv_kwh, e.je_auto[ea.id].netz_kwh) == (3.0, 2.0)
    assert ea.id not in e.bloecke_je_auto


@pytest.mark.asyncio
async def test_s3_4_kontext_und_schicht_sehen_dieselbe_messung(db):
    """Regel 6: E-Mob-Kontext (Hubs, Aussichten, HA-Export) und Monats-Fakten entscheiden mit
    denselben Blöcken — A 12 kWh, Topf 40 kWh."""
    a, wb, ea, eb = await _zwei_auto_monat(db)
    from backend.services.emob_kontext import lade_emob_kontext
    imd = (await db.execute(select(InvestitionMonatsdaten))).scalars().all()
    e = (await lade_emob_kontext(db, a.id, [wb, ea, eb], imd)).ctx.entscheide[(2026, 6)]
    assert e.je_auto[ea.id].ladung_kwh == pytest.approx(12.0)
    assert e.je_auto[ea.id].pv_kwh == pytest.approx(9.0)
    assert e.je_auto[eb.id].ladung_kwh == pytest.approx(28.0)
    assert e.bloecke_je_auto[ea.id].ladevorgaenge == 1


@pytest.mark.asyncio
async def test_s3_4_regel_7_vergleicht_die_monatsverteilten_spruenge(db):
    """Regel 7 (W3): ein Vorgang über den Monatswechsel — gespeichert steht die ganze Menge
    (40) im August, die Wallbox teilt ihn (Juli 30, August 10). Stufe 2 warnt im August
    (Überschuss 30 > 10); mit den Blöcken vergleicht der Checker dieselbe Größe und schweigt."""
    from backend.services.daten_checker.emob import EmobChecks

    a, wb, ea, eb = await _lab_anlage(db)
    await db.delete(eb)
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=7,
                                  verbrauch_daten={"ladung_kwh": 30.0}))
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=8,
                                  verbrauch_daten={"ladung_kwh": 10.0}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2026, monat=8,
                                  verbrauch_daten={"ladung_kwh": 40.0}, source_provenance=PROV_FORM))
    stunden = [(datetime(2026, 7, 31, 14) + timedelta(hours=i), 3.0) for i in range(10)]
    stunden.append((datetime(2026, 8, 1, 0), 10.0))
    db.add(_block(a.id, ea.id, stunden, 40.0))
    await db.commit()
    await _marken(db, a.id, date(2026, 7, 1), date(2026, 8, 31))
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == a.id)
        .options(__import__("sqlalchemy.orm", fromlist=["selectinload"]).selectinload(Anlage.investitionen)
                 .selectinload(Investition.monatsdaten))
    )).scalar_one()
    checks = EmobChecks()
    checks.db = db
    heute = date(2026, 9, 27)
    ohne = checks._check_emob_pool_pflege(anlage, heute=heute)
    assert any("mehr zu Hause geladen" in e.meldung for e in ohne)
    bloecke = await checks._emob_bloecke_fuer_pflege(anlage, heute=heute)
    assert bloecke[(2026, 7)][ea.id].kwh == pytest.approx(30.0)
    assert bloecke[(2026, 8)][ea.id].kwh == pytest.approx(10.0)
    mit = checks._check_emob_pool_pflege(anlage, heute=heute, bloecke=bloecke)
    assert not any("mehr zu Hause geladen" in e.meldung for e in mit)


@pytest.mark.asyncio
async def test_s3_4_dienstwagen_mit_bloecken_ist_gemessen(db):
    """Regel 3 + 9: ein Dienstwagen mit Zähler — seine Blöcke sind die dienstliche Ladung und
    fehlen im Rest der privaten Wallbox; auch ohne Monatszeile."""
    from backend.services.emob_kontext import lade_emob_kontext

    a, wb, ea, eb = await _lab_anlage(db)
    eb.parameter = {"ist_dienstlich": True}
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=6,
                                  verbrauch_daten={"ladung_kwh": 40.0, "ladung_pv_kwh": 20.0}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2026, monat=6,
                                  verbrauch_daten={"km_gefahren": 100}))
    db.add(_block(a.id, eb.id, [(datetime(2026, 6, 10, 12), 15.0)], 15.0, pv=6.0))
    await db.commit()
    await _marken(db, a.id, date(2026, 6, 1), date(2026, 6, 30))
    imd = (await db.execute(select(InvestitionMonatsdaten))).scalars().all()
    e = (await lade_emob_kontext(db, a.id, [wb, ea, eb], imd)).ctx.entscheide[(2026, 6)]
    assert e.dienstlich_je_inv[eb.id].pv_kwh == pytest.approx(6.0)
    assert e.dienstlich_je_inv[eb.id].netz_kwh == pytest.approx(9.0)
    assert e.je_auto[ea.id].ladung_kwh == pytest.approx(25.0)   # 40 − 15


@pytest.mark.asyncio
async def test_s3_4_e_auto_hub_zeigt_die_ladevorgaenge(db):
    """Auftrag S3-4: der E-Auto-Hub zeigt je Monat „aus n Ladevorgängen" (und das Kennzeichen)."""
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard

    a, wb, ea, eb = await _zwei_auto_monat(db)
    db.add(_block(a.id, ea.id, [(datetime(2026, 6, 12, 12), 2.0)], 5.0))   # ungedeckt 0,4
    await db.commit()
    dashboards = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db)
    (dash_a,) = [d for d in dashboards if d.investition.id == ea.id]
    (zeile,) = [m for m in dash_a.monatsdaten if (m.jahr, m.monat) == (2026, 6)]
    assert zeile.verbrauch_daten["ladung_aus_bloecken"] is True
    assert zeile.verbrauch_daten["ladevorgaenge_bloecke"] == 2
    assert zeile.verbrauch_daten["ladevorgaenge_ungedeckt"] == 1
    assert zeile.verbrauch_daten["ladung_kwh"] == pytest.approx(17.0)


# ═════════════════════════════════════════════════════════════════════════════
# S3-3 — über Mitternacht und über Tage (D−1 aus den gespeicherten Stunden)
# ═════════════════════════════════════════════════════════════════════════════

async def _tag_durch_den_hook(db, a, d: date, stunden: dict, zusatz: dict):
    tabelle = SimpleNamespace(stunden=stunden, zusatz_slots=zusatz)
    out = await aktualisiere_ladebloecke_des_tages(
        db, a, d, {}, tabelle, "external:ha_statistics:hourly",
    )
    for h, s in stunden.items():
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=h, wallbox_kw=s["wallbox"],
                                  netzbezug_kw=s.get("netzbezug"), einspeisung_kw=s.get("einspeisung")))
    await db.commit()
    return out


@pytest.mark.asyncio
async def test_p7_monatswechsel_ueber_den_hook(db, monkeypatch):
    """P7 über die Ablage: S7 auf 31.07. 21 Uhr … 01.08. 02 Uhr. Der Sprung liegt an 01.08.
    (Slot 2), zwei Stunden an 31.07. (gespeichert, D−1) ⇒ Juli 9,992 / August 4,769."""
    from backend.services.energie_profil.monats_aus_tagen import emob_je_auto_monate

    a, wb, ea, eb = await _lab_anlage(db)
    monkeypatch.setattr(speicher, "fahrzeug_zaehler_lts", lambda *a_, **k: {"z.A": ea.id})
    await _tag_durch_den_hook(db, a, date(2026, 7, 31),
                              {22: {"wallbox": 1.484}, 23: {"wallbox": 4.346}}, {"z.A": {}})
    await _tag_durch_den_hook(db, a, date(2026, 8, 1),
                              {0: {"wallbox": 4.158}, 1: {"wallbox": 3.509}, 2: {"wallbox": 1.258}},
                              {"z.A": {2: (14.761, 1)}})
    await _marken(db, a.id, date(2026, 7, 1), date(2026, 8, 31))
    je = await emob_je_auto_monate(db, a.id, [wb, ea, eb], [(2026, 7), (2026, 8)],
                                   heute=date(2026, 9, 27))
    assert je[(2026, 7)][ea.id].kwh == pytest.approx(9.992, abs=5e-4)
    assert je[(2026, 8)][ea.id].kwh == pytest.approx(4.769, abs=5e-4)
    assert je[(2026, 8)][ea.id].ladevorgaenge == 1 and (2026, 7) in je


@pytest.mark.asyncio
async def test_schon_vergebene_energie_eines_vortags_blocks_bleibt_vergeben(db, monkeypatch):
    """S3-3: teilt sich eine Stunde von D−1 mit einem gespeicherten Block, fehlt dessen Anteil in
    der Restmenge — B (Sprung an D) bekommt aus 22–23 Uhr nur, was A übrig ließ (2 von 3)."""
    a, wb, ea, eb = await _lab_anlage(db)
    monkeypatch.setattr(speicher, "fahrzeug_zaehler_lts",
                        lambda *a_, **k: {"z.A": ea.id, "z.B": eb.id})
    await _tag_durch_den_hook(db, a, date(2026, 8, 9), {23: {"wallbox": 3.0}},
                              {"z.A": {23: (1.0, 1)}, "z.B": {}})
    (b_,) = await _tag_durch_den_hook(db, a, date(2026, 8, 10),
                                      {0: {"wallbox": 1.0}, 1: {"wallbox": 1.0}},
                                      {"z.A": {}, "z.B": {1: (5.0, 1)}})
    assert [(s.beginn, s.kwh) for s in b_.stunden] == [
        (datetime(2026, 8, 9, 22), pytest.approx(2.0)),
        (datetime(2026, 8, 9, 23), pytest.approx(1.0)),
        (datetime(2026, 8, 10, 0), pytest.approx(1.0)),
    ]
    assert b_.stunden_gedeckt == pytest.approx(0.8)


# ═════════════════════════════════════════════════════════════════════════════
# D-6 — die Fahrzeug-Zähler im selben HA-Lesezugriff
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_d6_zusatz_zaehler_aendern_die_tabelle_nicht():
    """D-6: `lts_tagestabelle(zusatz_schluessel=…)` liest den Fahrzeug-Zähler im selben Zugriff
    und gibt ihn roh in `zusatz_slots` zurück — Stunden, Tageswerte und Verworfenes bleiben
    bitgleich; ein Zusatz-Zähler allein verhindert den Rückfall auf den Snapshot-Pfad nicht."""
    from backend.tests.test_zaehlerluecken_lts_tabelle import _inv, _reihe, _s, _svc_sql, _tabelle
    from backend.services.snapshot import lts_aggregator
    from unittest.mock import patch

    von, bis = datetime(2026, 5, 14, 12), datetime(2026, 5, 15, 22)
    zeilen = {
        "sensor.wb": _reihe(von, bis, 100.0, lambda t: 3.0 if 12 <= t.hour <= 14 else 0.0),
        "sensor.netz": _reihe(von, bis, 800.0, 0.5),
        "sensor.auto": _reihe(von, bis, 50.0, lambda t: 9.0 if t.hour == 14 else 0.0),
    }
    svc = _svc_sql(zeilen)
    mapping = {"basis": {"netzbezug": _s("sensor.netz")},
               "investitionen": {"1": {"felder": {"ladung_kwh": _s("sensor.wb")}},
                                 "2": {"felder": {"ladung_kwh": _s("sensor.auto")}}}}
    invs = {"1": _inv(1, "wallbox"), "2": _inv(2, "e-auto")}
    ohne = await _tabelle(svc, mapping, invs)
    anlage = SimpleNamespace(id=1, anlagenname="T", leistung_kwp=10.0, sensor_mapping=mapping)
    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=svc):
        mit = await lts_aggregator.lts_tagestabelle(
            anlage, invs, date(2026, 5, 15), zusatz_schluessel=["sensor.auto"],
        )
        nur_zusatz = await lts_aggregator.lts_tagestabelle(
            SimpleNamespace(id=1, anlagenname="T", leistung_kwp=10.0, sensor_mapping={
                "basis": {"netzbezug": _s("sensor.fehlt")}}),
            {}, date(2026, 5, 15), zusatz_schluessel=["sensor.auto"],
        )
    assert mit.stunden == ohne.stunden
    assert mit.komponenten_kwh == ohne.komponenten_kwh
    assert mit.verworfen == ohne.verworfen
    assert ohne.zusatz_slots == {}
    assert mit.zusatz_slots["sensor.auto"][16] == (9.0, 1)   # _reihe: Stand bei start_ts, Zuwachs danach
    assert nur_zusatz is None


# ═════════════════════════════════════════════════════════════════════════════
# S3-4 — Cockpit → Monat (laufender Monat, eigener Entscheid)
# ═════════════════════════════════════════════════════════════════════════════

def test_s3_4_laufender_monat_entscheidet_mit_den_bloecken():
    """Cockpit → Monat entscheidet im laufenden Monat selbst (HA-Werte der Wallbox, keine
    Monatszeile) — mit denselben Blöcken wie die Schicht: A trägt 12, B den Rest 28."""
    from backend.api.routes.aktueller_monat.aggregation import emob_heimladung_pool
    from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo

    live = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)

    def _ns(i, typ):
        return SimpleNamespace(id=i, typ=typ, parameter={}, aktiv=True,
                               ist_aktiv_im_monat=lambda j, m: True)

    invs = [_ns(5, "wallbox"), _ns(7, "e-auto"), _ns(8, "e-auto")]
    resolved = {"inv_5_ladung_kwh": (40.0, live), "inv_5_ladung_pv_kwh": (20.0, live),
                "inv_7_km_gefahren": (100.0, live), "inv_8_km_gefahren": (100.0, live)}
    bm = BlockMonat(kwh=12.0, pv_kwh=9.0, ladevorgaenge=1)
    out = emob_heimladung_pool(
        direct_fields=set(), investitionen=invs, jahr=2026, monat=9, resolved=resolved,
        ist_aktueller_monat=True, bloecke={7: bm},
    )
    e = out["emob_entscheid"]
    assert (e.je_auto[7].pv_kwh, e.je_auto[7].netz_kwh) == (pytest.approx(9.0), pytest.approx(3.0))
    assert e.je_auto[8].ladung_kwh == pytest.approx(28.0)


# ═════════════════════════════════════════════════════════════════════════════
# Nachträge Master 27.09. — Dienstwagen-Zähler, NF-1, NF-3
# ═════════════════════════════════════════════════════════════════════════════

def test_dienstwagen_mit_zaehler_gehoert_zu_den_fahrzeug_zaehlern():
    """Bestätigt 27.09.: auch ein Dienstwagen mit Zähler an „Heim: gesamt" bekommt Blöcke — sein
    Sprung begrenzt die Blöcke der anderen Autos (Regel 9 Punkt 2), seine Menge ist dienstlich."""
    wb = SimpleNamespace(id=1, typ="wallbox", ist_aktiv_an=lambda d: True, parameter={})
    dw = SimpleNamespace(id=3, typ="e-auto", ist_aktiv_an=lambda d: True, parameter={"ist_dienstlich": True})
    sensor = lambda eid: {"strategie": "sensor", "sensor_id": eid}  # noqa: E731
    anlage = SimpleNamespace(sensor_mapping={"investitionen": {
        "1": {"felder": {"ladung_kwh": sensor("sensor.wb")}},
        "3": {"felder": {"ladung_kwh": sensor("sensor.dienstwagen")}},
    }})
    assert speicher.fahrzeug_zaehler_lts(anlage, {"1": wb, "3": dw}, date(2026, 8, 1)) == {
        "sensor.dienstwagen": 3,
    }


@pytest.mark.asyncio
async def test_dienstwagen_sprung_begrenzt_den_block_des_privaten_autos(db, monkeypatch):
    """Über den Hook: der Dienstwagen springt 10–11 Uhr um 3 (die 9-Uhr-Stunde mit 2 kWh braucht
    er nicht), das private Auto danach bis 13 Uhr mit einer Wallbox-Lücke — sein Block nimmt
    keine Stunde vor dem Dienstwagen-Sprung, auch nicht die freie 9-Uhr-Stunde."""
    a, wb, ea, eb = await _lab_anlage(db)
    eb.parameter = {"ist_dienstlich": True}
    await db.commit()
    monkeypatch.setattr(speicher, "fahrzeug_zaehler_lts",
                        lambda *a_, **k: {"z.A": ea.id, "z.D": eb.id})
    bloecke = await _tag_durch_den_hook(
        db, a, date(2026, 8, 12),
        {10: {"wallbox": 2.0}, 11: {"wallbox": 3.0}, 12: {"wallbox": 1.0}, 13: {"wallbox": 1.0}},
        {"z.D": {11: (3.0, 1)}, "z.A": {13: (4.0, 1)}},
    )
    dw_block, a_block = bloecke
    assert dw_block.inv_id == eb.id and dw_block.stunden_gedeckt == pytest.approx(1.0)
    assert [s.beginn.hour for s in a_block.stunden] == [11, 12]   # Slots 12, 13
    assert a_block.stunden_gedeckt == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_nf1_energieprofil_loeschen_raeumt_die_ladebloecke(db):
    """NF-1: „Energieprofil löschen" (je Anlage und alle) nimmt die Ladeblöcke mit."""
    from backend.api.routes.energie_profil.repair import delete_alle_rohdaten, delete_rohdaten

    a, wb, ea, eb = await _lab_anlage(db)
    db.add(_block(a.id, ea.id, [(datetime(2026, 6, 10, 12), 5.0)], 5.0))
    await db.commit()
    await delete_rohdaten(a.id, db=db)
    assert (await db.execute(select(EmobLadeblock))).scalars().all() == []
    db.add(_block(a.id, ea.id, [(datetime(2026, 6, 11, 12), 5.0)], 5.0))
    await db.commit()
    await delete_alle_rohdaten(db=db)
    assert (await db.execute(select(EmobLadeblock))).scalars().all() == []


@pytest.mark.asyncio
async def test_nf3_wc_bis_gestern_heutige_bloecke_nur_mit_heutiger_zeile(db):
    """NF-3: Marken bis gestern genügen — zwischen 00:00 und 00:15 fällt der laufende Monat
    nicht nach Stufe 2 zurück. Blöcke von heute zählen erst mit der heutigen Tageszeile."""
    a, wb, ea, eb = await _lab_anlage(db)
    heute = date(2026, 9, 15)
    db.add(_block(a.id, ea.id, [(datetime(2026, 9, 10, 12), 5.0)], 5.0))
    db.add(_block(a.id, ea.id, [(datetime(2026, 9, 15, 9), 2.0)], 2.0))
    await db.commit()
    await _marken(db, a.id, date(2026, 9, 1), date(2026, 9, 14))
    invs = [wb, ea, eb]
    bm = (await emob_je_auto(db, a.id, invs, 2026, 9, heute=heute))[ea.id]
    assert bm.kwh == pytest.approx(5.0)                     # ohne den Block von heute
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=heute, verworfen={}))
    await db.commit()
    bm = (await emob_je_auto(db, a.id, invs, 2026, 9, heute=heute))[ea.id]
    assert bm.kwh == pytest.approx(7.0)


# ═════════════════════════════════════════════════════════════════════════════
# N-569 — Regel B (Speicher-Entladung ist Eigenstrom) und „davon aus dem Speicher"
# ═════════════════════════════════════════════════════════════════════════════

def test_n569_fixture_pv_anteil_und_speicheranteil(harness):
    """Anhang E: an den zwölf Sitzungen (elf mit ableitbarer Stunde) kWh-gewichtet PV 96,9 %
    (Fable-Messung; evcc 98,4 %; mit dem früheren Speicherabzug 77,7 %), davon aus dem Speicher
    21,7 % der Ladung — Teilmenge des PV-Anteils in jedem Block."""
    mit = [b for b in harness["bloecke"] if b.pv_kwh is not None]
    menge = sum(b.kwh for b in mit)
    assert 100 * sum(b.pv_kwh for b in mit) / menge == pytest.approx(96.9, abs=0.05)
    assert 100 * sum(b.speicher_kwh for b in mit) / menge == pytest.approx(21.7, abs=0.05)
    assert all(0.0 <= b.speicher_kwh <= b.pv_kwh + 1e-9 for b in mit)
    s1 = harness["je_sitzung"]["S1"]                 # 08.07.: Hausakku lieferte je Stunde 2 kWh
    assert (s1.pv_kwh, s1.speicher_kwh) == (pytest.approx(17.601), pytest.approx(9.011))


def test_n569_speicheranteil_je_auto_ist_nur_ausweis():
    """Keine Wirkung: mit Speicher-Tagesanteil bleiben PV, Netz, Topf, Rest und Dienstwagen
    bitgleich — nur `speicher_kwh` je Auto kommt hinzu, nie über dessen PV-Teil."""
    from backend.services.eauto_wirtschaftlichkeit import entscheide_emob_heimladung

    kw = dict(
        eauto_je_inv={1: {"ladung_pv_kwh": 30.0, "ladung_netz_kwh": 10.0}, 2: {"km_gefahren": 50}},
        wallbox_zeilen=[{"ladung_kwh": 100.0, "ladung_pv_kwh": 60.0}], wallbox_in_betrieb=True,
    )
    ohne = entscheide_emob_heimladung(**kw)
    mit = entscheide_emob_heimladung(**kw, speicher_quote=0.5)
    assert mit.pool == ohne.pool
    assert (mit.rest_pv_kwh, mit.rest_netz_kwh) == (ohne.rest_pv_kwh, ohne.rest_netz_kwh)
    for i in (1, 2):
        assert (mit.je_auto[i].pv_kwh, mit.je_auto[i].netz_kwh) == (ohne.je_auto[i].pv_kwh, ohne.je_auto[i].netz_kwh)
        assert ohne.je_auto[i].speicher_kwh is None
    assert mit.je_auto[1].speicher_kwh == pytest.approx(20.0)      # 40 × 0,5, unter PV 30
    assert mit.je_auto[2].speicher_kwh == pytest.approx(30.0)      # 60 × 0,5 = 30, PV-Teil 30


def test_n569_speicheranteil_nie_ueber_dem_pv_teil():
    """Teilmenge: ein Tagesanteil, der mehr Speicher behauptete als PV da ist, wird gekappt."""
    from backend.services.eauto_wirtschaftlichkeit import entscheide_emob_heimladung

    e = entscheide_emob_heimladung(
        eauto_je_inv={1: {"ladung_pv_kwh": 5.0, "ladung_netz_kwh": 35.0}},
        wallbox_zeilen=[{"ladung_kwh": 40.0, "ladung_pv_kwh": 5.0}], wallbox_in_betrieb=True,
        speicher_quote=0.5,
    )
    assert e.je_auto[1].speicher_kwh == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_n569_tagesebene_faltet_den_speicheranteil(db):
    """Tagesebene → Monat: `emob_ladung_speicher_abgeleitet_kwh` je Tag, der Monatsanteil ist
    Teil des PV-Anteils; ein Monat ohne Speicherwert hat keine Aussage."""
    from backend.services.energie_profil.monats_aus_tagen import (
        lade_monats_summen_aus_tagen,
        lade_speicher_anteile,
    )

    a, wb, ea, eb = await _lab_anlage(db)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 6, 3), verworfen={},
                                emob_ladung_pv_abgeleitet_kwh=8.0, emob_ladung_netz_abgeleitet_kwh=2.0,
                                emob_ladung_speicher_abgeleitet_kwh=3.0))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 6, 4), verworfen={},
                                emob_ladung_pv_abgeleitet_kwh=6.0, emob_ladung_netz_abgeleitet_kwh=4.0,
                                emob_ladung_speicher_abgeleitet_kwh=1.0))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 7, 4), verworfen={},
                                emob_ladung_pv_abgeleitet_kwh=6.0, emob_ladung_netz_abgeleitet_kwh=4.0))
    await db.commit()
    summen = await lade_monats_summen_aus_tagen(db, a.id)
    assert summen[(2026, 6)].abgeleiteter_pv_anteil == pytest.approx(0.7)
    assert summen[(2026, 6)].abgeleiteter_speicher_anteil == pytest.approx(0.2)
    assert summen[(2026, 7)].abgeleiteter_speicher_anteil is None
    assert await lade_speicher_anteile(db, a.id, [(2026, 6), (2026, 7)]) == {(2026, 6): pytest.approx(0.2)}


@pytest.mark.asyncio
async def test_n569_hub_zeigt_davon_aus_dem_speicher(db):
    """E-Auto-Hub: Kachel-Unterzeile (`speicher_anteil_heim_prozent`) und Monatszeile
    (`ladung_speicher_kwh`) aus dem Speicheranteil des Monats; ohne Tagesanteil keine Zeile."""
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard

    a, wb, ea, eb = await _zwei_auto_monat(db)        # A: Blöcke 12 kWh (PV 9) im Juni
    dash = {d.investition.id: d for d in await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db)}
    assert dash[ea.id].zusammenfassung["speicher_anteil_heim_prozent"] is None
    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == a.id, TagesZusammenfassung.datum == date(2026, 6, 10),
    ))).scalar_one()
    tz.emob_ladung_pv_abgeleitet_kwh, tz.emob_ladung_netz_abgeleitet_kwh = 6.0, 4.0
    tz.emob_ladung_speicher_abgeleitet_kwh = 2.5            # Monatsanteil 0,25
    await db.commit()
    dash = {d.investition.id: d for d in await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db)}
    (zeile_b,) = [m for m in dash[eb.id].monatsdaten if (m.jahr, m.monat) == (2026, 6)]
    assert zeile_b.verbrauch_daten["ladung_speicher_kwh"] == pytest.approx(7.0)   # 28 × 0,25
    assert dash[eb.id].zusammenfassung["speicher_anteil_heim_prozent"] == pytest.approx(25.0)
    # A trägt Blöcke ohne Speicherteil: Teil ohne Anteil = 0 ⇒ Speicher 0 (keine Zeile in der Tabelle)
    (zeile_a,) = [m for m in dash[ea.id].monatsdaten if (m.jahr, m.monat) == (2026, 6)]
    assert "ladung_speicher_kwh" not in zeile_a.verbrauch_daten
    assert zeile_b.verbrauch_daten["ladung_pv_kwh"] == pytest.approx(11.0)       # PV unverändert


@pytest.mark.asyncio
async def test_n569_community_payload_unberuehrt_vom_speicheranteil(db):
    """Keine Wirkung auf den Community-Payload: mit und ohne Speicher-Tagesanteil derselbe."""
    from backend.services import community_service

    from backend.models.monatsdaten import Monatsdaten

    a, wb, ea, eb = await _zwei_auto_monat(db)
    a.plz = "10115"
    db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2024, 1, 1),
                       leistung_kwp=10.0))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, pv_erzeugung_kwh=900.0,
                       einspeisung_kwh=500.0, netzbezug_kwh=100.0))
    await db.commit()
    fn = community_service.prepare_community_data
    vorher = await fn(db, a.id)
    assert vorher is not None and vorher.get("monatswerte"), "Probe braucht einen echten Payload"
    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == a.id, TagesZusammenfassung.datum == date(2026, 6, 10),
    ))).scalar_one()
    tz.emob_ladung_pv_abgeleitet_kwh, tz.emob_ladung_netz_abgeleitet_kwh = 6.0, 4.0
    tz.emob_ladung_speicher_abgeleitet_kwh = 2.5
    await db.commit()
    nachher = await fn(db, a.id)
    assert json.dumps(vorher, sort_keys=True, default=str) == json.dumps(nachher, sort_keys=True, default=str)
