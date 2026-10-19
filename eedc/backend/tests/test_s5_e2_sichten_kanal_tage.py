"""Sichten an Kanal-Tagen, S5a Teil 2 (HA-Bauform S5, Etappe E-S5-2; Bauplan §3 (A), §4 S5-R5/S5-R7, §7, §10c M-1).

* **HA-Export-Steuerung** (``anlage_steuerung``): an einem Kanal-Tag kommen die Stunden aus ``stunden_der_tage``
  (Mischzeilen, Beginn-Raster) — ``eedc_ueberschuss_heute_kwh`` = *Cockpit → Tag* (``tage-werte``), ``…_jetzt_kw`` =
  die Mischzeile der letzten Stunde mit Wert, ``seit``/``stunde_von``/``stunde_max_mittel`` am Raster der Zeile
  (S4-R-3b: Beginn im Kalendertag), Netzbezugs-Spitze aus der Tageszeile unverändert. Gegenprobe ohne Kanalzeilen:
  die Tageszeile und die Backward-Beschriftung wie bisher.
* **Spannen-Stunden leer statt 0,0** (S5-R5, H-2c): eine Stunde ohne eigene Zeile an einem WP-Kanal-Tag (Lücke 10–12,
  HAs Lückenregel legt die Menge in Stunde 12) zeigt im Wärme-Verlauf ``None``; Stunde 12 trägt die Energie, Σ = Balken.
* **W-3** (S5-R7): der Wärme-Verlauf liest an einem WP-Kanal-Tag den Modus-Split aus dem abgeleiteten Kanal wie
  *Cockpit → Tag* — auch wenn die Modus-Spur der Stundenzeilen etwas anderes sagt.
* **M-1 (a) Wochenmuster**: gebündelte Zeilen (Spanne > 1) fallen aus dem Mittel; ohne Bündel unverändert.
* **M-1 (b) ``_ist_heute``**: ohne Marke ``{}``.
* **Werkbank-Vorschau** (§7, S5a-Fassung): eine Zeile mit den Kanal-Gruppen eines Kanal-Tags, keine an einem Bestandstag.

Schwesterdateien: test_s5_e2_checker_kanal_mengen.py, test_s5_stunden_der_tage.py, test_kanal_stunden_sichten.py.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.kanal import bilanz_leser
from backend.tests import kanal_bilanz_gleichheit as kg

TAG = date(2026, 6, 10)


@pytest.fixture
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


async def _anlage(ds) -> Anlage:
    return (await ds.db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == ds.aid)
    )).scalar_one()


async def _ohne_kanalzeilen(ds) -> None:
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
    await ds.db.commit()


# ── HA-Export-Steuerung ──────────────────────────────────────────────────────


async def _steuerung(ds) -> dict:
    from backend.api.routes.ha_export.anlage_steuerung import steuerungs_sensoren

    werte: list = []
    await steuerungs_sensoren(anlage=await _anlage(ds), db=ds.db, sensor_values=werte, prognose=None, preis=None,
                              fenster_ctx=None, heute=TAG, jetzt_stunde=14)
    return {sv.definition.key: sv for sv in werte}


def _lauf_beginn(zeilen) -> int | None:
    """Beginn (Wanduhr-Stunde) des letzten zusammenhängenden Überschuss-Laufs bis zur letzten Zeile mit Wert."""
    start = None
    for z in zeilen:
        if z.ueberschuss_kw is None and z.defizit_kw is None:
            continue
        start = (z.stunde if start is None else start) if (z.ueberschuss_kw or 0) - (z.defizit_kw or 0) > 0 else None
    return start


async def test_steuerung_kanal_tag_wie_cockpit_tag(uhr):
    from backend.api.routes.energie_profil.tage import get_tage_werte
    from backend.core.berechnungen.slot_konvention import ist_beginn_raster
    from backend.services.energie_profil.kanal_stunden import stunden_der_tage

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG,
        ).values(ueberschuss_kwh=999.0, defizit_kwh=999.0, peak_netzbezug_kw=4.2))
        await ds.db.commit()
        sv = await _steuerung(ds)
        tw = {z.datum: z for z in await get_tage_werte(ds.aid, TAG, TAG, ds.db)}[TAG]
        zeilen = [z for z in await stunden_der_tage(ds.db, ds.aid, TAG, TAG) if z.datum == TAG]
    assert zeilen and all(ist_beginn_raster(z) for z in zeilen)
    e1 = sv["eedc_ueberschuss_heute_kwh"]
    assert round(e1.value, 3) == tw.ueberschuss_kwh and e1.value != 999.0
    assert e1.zusatz_attribute["defizit_heute_kwh"] == tw.defizit_kwh
    mit = [z for z in zeilen if z.ueberschuss_kw is not None or z.defizit_kw is not None]
    letzte = mit[-1]
    jetzt = sv["eedc_ueberschuss_jetzt_kw"]
    assert jetzt.value == round((letzte.ueberschuss_kw or 0.0) - (letzte.defizit_kw or 0.0), 2)
    assert jetzt.zusatz_attribute["stunde_von"] == f"{letzte.stunde:02d}:00"
    assert jetzt.zusatz_attribute["stunde_bis"] == f"{(letzte.stunde + 1) % 24:02d}:00"
    assert e1.zusatz_attribute["stand"] == f"{(letzte.stunde + 1) % 24:02d}:00"
    seit = _lauf_beginn(zeilen)
    assert sv["eedc_ueberschuss_verfuegbar"].zusatz_attribute.get("seit") == (
        f"{seit:02d}:00" if seit is not None else None)
    spitze = sv["eedc_netzbezug_spitze_heute_kw"]
    assert spitze.value == 4.2
    netz = [(z.stunde, z.netzbezug_kw) for z in zeilen if z.netzbezug_kw is not None]
    assert spitze.zusatz_attribute["stunde_max_mittel"] == f"{max(netz, key=lambda x: x[1])[0]:02d}:00"


async def test_steuerung_gegenprobe_bestandstag_tageszeile_und_backward_beschriftung(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG,
        ).values(ueberschuss_kwh=11.25, defizit_kwh=3.5, peak_netzbezug_kw=4.2))
        await ds.db.commit()
        await _ohne_kanalzeilen(ds)
        sv = await _steuerung(ds)
        zeilen = list((await ds.db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG,
        ).order_by(TagesEnergieProfil.stunde))).scalars())
    assert sv["eedc_ueberschuss_heute_kwh"].value == 11.25
    assert sv["eedc_ueberschuss_heute_kwh"].zusatz_attribute["defizit_heute_kwh"] == 3.5
    letzte = [z for z in zeilen if z.ueberschuss_kw is not None or z.defizit_kw is not None][-1]
    assert sv["eedc_ueberschuss_jetzt_kw"].zusatz_attribute["stunde_von"] == f"{(letzte.stunde - 1) % 24:02d}:00"
    assert sv["eedc_ueberschuss_jetzt_kw"].zusatz_attribute["stunde_bis"] == f"{letzte.stunde % 24:02d}:00"


# ── Spannen-Stunden leer statt 0,0 (Wärme-Verlauf je Stunde) ────────────────


async def _luecke_10_bis_12(ds) -> None:
    """Die WP-Kanäle verlieren die Zeilen der Stunden 10 und 11 von ``TAG`` — HA legt deren Menge in Stunde 12 (Spanne 3)."""
    ab = int(datetime.combine(TAG, datetime.min.time()).timestamp()) + 10 * 3600
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid, Kanal.key.like(f"inv:{ds.ids['WP']}:%"))
    await ds.db.execute(delete(KanalStatistik).where(
        KanalStatistik.kanal_id.in_(ids), KanalStatistik.start_ts >= ab, KanalStatistik.start_ts < ab + 2 * 3600))
    await ds.db.commit()


async def test_spannen_stunden_leer_stunde_12_traegt_die_energie(uhr):
    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.api.routes.energie_profil.waerme import get_waerme_verlauf_stunden

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        await _luecke_10_bis_12(ds)
        st = await get_waerme_verlauf_stunden(ds.aid, datum=TAG, db=ds.db)
        tag = await get_tag_detail(ds.aid, datum=TAG, db=ds.db)
    assert st.raster == "beginn"
    je = {z.stunde: z for z in st.stunden}
    assert je[10].wp_waerme_kwh is None and je[11].wp_waerme_kwh is None
    assert je[12].wp_waerme_kwh == pytest.approx(3 * 0.9, abs=1e-3)
    assert je[9].wp_waerme_kwh == pytest.approx(0.9, abs=1e-3)
    assert sum(z.wp_waerme_kwh or 0.0 for z in st.stunden) == pytest.approx(tag.wp_waerme_kwh, abs=0.01)


async def test_spannen_stunden_ohne_luecke_unveraendert(uhr):
    from backend.api.routes.energie_profil.waerme import get_waerme_verlauf_stunden

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        st = await get_waerme_verlauf_stunden(ds.aid, datum=TAG, db=ds.db)
    assert all(z.wp_waerme_kwh == pytest.approx(0.9, abs=1e-3) for z in st.stunden)


def test_verteile_linie_bestandstag_behaelt_die_null():
    """Ohne WP-Kanal-Tag (``wp_aus_kanal`` falsch) bleibt eine Stunde ohne Form 0,0 — Bestandstage unverändert."""
    from backend.api.routes.energie_profil.waerme import _verteile_linie

    form = [None] * 24
    form[12] = 3.0
    form[13] = 1.0
    args = (("wp_waerme_kwh",), None, {"wp_waerme_kwh": {"1": {"waerme_kwh": 4.0}}}, {"inv:1:waerme_kwh": form},
            {"wp_waerme_kwh": "waerme_kwh"})
    bestand, _, leer_b = _verteile_linie(*args, False)
    kanal, _, leer_k = _verteile_linie(*args, True)
    assert bestand[10] == 0.0 and not any(leer_b)
    assert kanal[10] is None and leer_k[10] and kanal[12] == bestand[12]


# ── W-3: Modus-Split im Wärme-Verlauf aus dem Kanal ──────────────────────────


async def test_w3_verlauf_tag_gleich_cockpit_tag_auch_gegen_die_modus_spur(uhr):
    """Die Modus-Spur der Stundenzeilen sagt am ``TAG`` «Kühlen» — der abgeleitete Kanal (Mitschrift) sagt Heizen/
    Warmwasser. Cockpit → Tag liest den Kanal; der Wärme-Verlauf seit W-3 auch."""
    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.services.energie_profil.waerme_verlauf import lade_waerme_verlauf

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        await ds.db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum.in_((TAG, date(2026, 6, 11))),
        ).values(betriebsmodus_je_wp={str(wp): "kuehlen"}))
        await ds.db.commit()
        a = await _anlage(ds)
        invs = {str(i.id): i for i in a.investitionen}
        (v,) = [z for z in await lade_waerme_verlauf(ds.db, a, invs, TAG, TAG) if z.datum == TAG]
        t = await get_tag_detail(ds.aid, datum=TAG, db=ds.db)
    assert v.stapel.heizen_kwh == pytest.approx(t.wp_modus_strom_heizen_kwh, abs=1e-3)
    assert v.stapel.warmwasser_kwh == pytest.approx(t.wp_modus_strom_warmwasser_kwh, abs=1e-3)
    assert v.stapel.kuehlen_kwh == pytest.approx(t.wp_modus_strom_kuehlen_kwh or 0.0, abs=1e-3)
    assert v.stapel.heizen_kwh > 0 and v.stapel.kuehlen_kwh == 0.0


def test_w3_splits_mit_kanal_kanal_gewinnt_sonst_die_modus_spur():
    """H-2a je Gerät (dieselbe Weiche wie *Cockpit → Tag*): ein Gerät mit Zeilen im abgeleiteten Kanal nimmt den
    Kanal-Split (auch einen leeren — er verdrängt die Modus-Spur), ein Gerät ohne behält die Modus-Spur; leere fallen."""
    from backend.core.berechnungen.modus_split import ModusSplit
    from backend.services.energie_profil.kanal_stunden import splits_mit_kanal

    spur = {"1": ModusSplit(kwh_je_modus={"kuehlen": 2.0}, abdeckung_h=10.0),
            "2": ModusSplit(kwh_je_modus={"heizen": 1.0}, abdeckung_h=5.0)}
    kanal = {"1": ModusSplit(kwh_je_modus={"heizen": 3.0}, abdeckung_h=20.0), "3": ModusSplit(kwh_je_modus={})}
    out = splits_mit_kanal(spur, kanal)
    assert out == {"2": spur["2"], "1": kanal["1"]}


# ── M-1 (a): Wochenmuster ohne gebündelte Zeilen ─────────────────────────────


def _zeile(d: date, stunde: int, pv: float, spannen=None):
    return SimpleNamespace(datum=d, stunde=stunde, pv_kw=pv, verbrauch_kw=None, netzbezug_kw=None,
                           einspeisung_kw=None, batterie_kw=None, spannen=spannen)


async def _wochenmuster(db, monkeypatch, zeilen):
    from backend.api.routes.energie_profil.serien import get_wochenmuster
    from backend.services.energie_profil import kanal_stunden

    async def _stunden(*a, **k):
        return zeilen

    monkeypatch.setattr(kanal_stunden, "stunden_der_tage", _stunden)
    a = Anlage(anlagenname="Wochenmuster", leistung_kwp=10.0)
    db.add(a)
    await db.commit()
    return await get_wochenmuster(a.id, von=date(2026, 6, 1), bis=date(2026, 6, 30), db=db)


async def test_wochenmuster_tagesstand_kanal_keine_punkte_statt_eines_buendels(db, monkeypatch):
    """Ein Tagesstand-Kanal (eine Zeile je Tag mit Spanne 23) gab bis M-1 in Stunde 22 den ganzen Tag als «kW»."""
    zeilen = [_zeile(date(2026, 6, 1), 22, 35.9, {"pv": 23}), _zeile(date(2026, 6, 1), 23, 0.0)]
    punkte = await _wochenmuster(db, monkeypatch, zeilen)
    assert [(p.stunde, p.pv_kw, p.anzahl_tage) for p in punkte] == [(23, 0.0, 1)]


async def test_wochenmuster_ohne_buendel_unveraendert(db, monkeypatch):
    zeilen = [_zeile(date(2026, 6, 1), 12, 4.0), _zeile(date(2026, 6, 8), 12, 2.0), _zeile(date(2026, 6, 8), 13, None)]
    punkte = await _wochenmuster(db, monkeypatch, zeilen)
    assert [(p.wochentag, p.stunde, p.pv_kw, p.anzahl_tage) for p in punkte] == [(0, 12, 3.0, 2)]


# ── M-1 (b): `_ist_heute` ohne Marke `{}` ────────────────────────────────────


async def test_ist_heute_ohne_marke_leeres_dict(db, monkeypatch):
    import backend.api.routes.prognosen as prognosen

    gesehen = {}

    def _ist_profil(rows, *, jetzt_stunde, datum, verworfen):
        gesehen["verworfen"] = verworfen
        return SimpleNamespace(tageswert_kwh=0.0, unvollstaendig=False, stunden=[])

    monkeypatch.setattr(prognosen, "ist_profil", _ist_profil)
    monkeypatch.setattr(prognosen, "_profil_zu_eintraegen", lambda p: [])
    await prognosen._ist_heute(db, 1, date(2026, 6, 10), datetime(2026, 6, 10, 12), [])
    assert gesehen["verworfen"] == {}


# ── Werkbank-Vorschau ────────────────────────────────────────────────────────


async def test_werkbank_vorschau_nennt_die_kanal_gruppen(uhr):
    from backend.services.repair_orchestrator import _kanal_hinweis

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        (tag,) = await _kanal_hinweis(ds.db, ds.aid, TAG, TAG)
        (bereich,) = await _kanal_hinweis(ds.db, ds.aid, date(2026, 5, 30), date(2026, 6, 3))
    assert tag.startswith("Dieser Tag liest seine Mengen für PV, Netz und Speicher und die Wärmepumpe aus dem HA-Spiegel")
    assert "an Cockpit → Tag/Monat/Jahr ändert er für diese Gruppen nichts" in tag
    assert bereich.startswith("3 von 5 Tagen des Bereichs lesen ihre Mengen für")


async def test_werkbank_vorschau_bestandstag_keine_zeile(uhr):
    from backend.services.repair_orchestrator import _kanal_hinweis

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        assert await _kanal_hinweis(ds.db, ds.aid, TAG, TAG) == []


async def test_werkbank_bereichs_vorschau_traegt_die_zeile(uhr):
    from backend.services.repair_orchestrator import RepairOperationRequest, _plan_reaggregate_range

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        req = RepairOperationRequest(operation="reaggregate_range", anlage_id=ds.aid,
                                     params={"von": "2026-06-08", "bis": "2026-06-12"})
        _, warnungen, _ = await _plan_reaggregate_range(req, ds.db)
    assert warnungen[-1].startswith("5 von 5 Tagen des Bereichs lesen ihre Mengen für PV, Netz und Speicher aus")
