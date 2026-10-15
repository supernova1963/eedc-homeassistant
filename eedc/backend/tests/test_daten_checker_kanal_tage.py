"""Daten-Checker auf Kanal-Tagen (HA-Bauform S3, Etappe E-S3-3; Bauplan §5).

Ein Kanal-Tag ist ein Tag, dessen Bilanz-Gruppe aus den Kanälen kommt (``bilanz_leser.kanal_tage``, Wahl ``kanal`` —
dieselbe Quellenwahl wie Cockpit → Tag). Geprüft an der Achsen-Form M01 (HA, Spiegel aus der Recorder-Statistik, Tage
über ``aggregate_day``; alle 33 Tage sind Kanal-Tage), Uhr der Matrix gestellt (keine Probe liest die Uhr):

* **E7 «Bestandstage ohne Regelmarke»** überspringt Kanal-Tage (dort rechnet Cockpit → Tag nicht nach N-92); wurde einer
  übersprungen, nennt die Zeile «k von n Bestandstagen». Gegenprobe ohne Kanalzeilen: der heutige Wortlaut, alle Tage.
* **«Einspeisung über Erzeugung»** liest an einem Kanal-Tag die Bilanz des Tages-Lesers (Weg 2, kein Deckel), nicht die
  Stundenzeilen: ein Sprung im Einspeise-Kanal ⇒ Befund; eine verfälschte Stundenzeile an einem Kanal-Tag ⇒ keiner.
  Gegenprobe ohne Kanalzeilen: wie heute aus den Stundenzeilen.
* **Counter-Spike / Doppelerfassung (``_spike_tage``, Entscheid H-1 → A)**: nur Bestandstage tragen Spitzen bei; an einem
  Kanal-Tag ist ein Sprung in HAs ``sum`` HAs Zahl (S3-R9, N-586). Form M03 (Zählersprung N3) mit und ohne Kanäle ⇒ keine
  Spitze (wie heute: der Schreiber klemmt die Stunde); eine Spitze in der Stundenzeile eines Kanal-Tags zählt nicht, die
  eines Bestandstags daneben schon.
* **N-267 ``hat_stundenwerte``**: Stundenzeilen ODER Kanal-Stunden der Bilanz-Gruppe; ein Kanal außerhalb der Gruppe
  (Wallbox, abgeleitet) zählt nicht.

Schwesterdateien: test_zaehlerluecken_e7_bestandstage.py, test_zaehlerluecken_einspeisung_ueber_erzeugung.py
(dieselben Prüfungen ohne Kanäle), test_kanal_stunden_sichten.py (die Sichten an einem Kanal-Tag),
test_n586_checker_ha_zaehlersprung.py (die Spiegel-Meldung).
"""

from __future__ import annotations

import inspect
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.daten_checker import DatenChecker
from backend.services.kanal import bilanz_leser
from backend.tests import kanal_bilanz_gleichheit as kg

BESTAND_OHNE = date(2026, 5, 20)      # vor dem ersten Kanal-Stand (Reihe ab 31.05. 18:00) ⇒ Bestandstag
BESTAND_MIT = date(2026, 5, 21)
KANAL_OHNE = (date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12))
SPRUNG_TAG = date(2026, 6, 15)
VERFAELSCHT_TAG = date(2026, 6, 20)


@pytest.fixture
def uhr(monkeypatch):
    """Die Uhr der Leser steht auf der Uhr der Matrix (``kg.JETZT_TS``)."""
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


def _quelle():
    return patch(
        "backend.services.energie_profil.aggregations_quelle.ermittle_aggregations_quelle",
        new=AsyncMock(return_value=SimpleNamespace(vorhanden=True)),
    )


async def _anlage(ds) -> Anlage:
    return (await ds.db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == ds.aid)
    )).scalar_one()


async def _ohne_kanalzeilen(ds) -> None:
    """Gegenprobe: dieselben Tages- und Stundenzeilen, aber kein Kanal trägt eine Zeile ⇒ jeder Tag ist Bestandstag."""
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
    await ds.db.commit()


# ── E7: Bestandstage ohne Regelmarke ────────────────────────────────────────


async def _e7_lage(ds) -> None:
    """Drei Kanal-Tage ohne Marke, ein Bestandstag ohne und einer mit Marke (beide mit Stundenzeile)."""
    await ds.db.execute(update(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum.in_(KANAL_OHNE),
    ).values(verworfen=None))
    for d, marke in ((BESTAND_OHNE, None), (BESTAND_MIT, {})):
        ds.db.add(TagesZusammenfassung(anlage_id=ds.aid, datum=d, verworfen=marke))
        ds.db.add(TagesEnergieProfil(anlage_id=ds.aid, datum=d, stunde=12, pv_kw=1.0))
    await ds.db.commit()


async def test_e7_kanal_tage_zaehlen_nicht_und_die_zeile_nennt_von_n_bestandstagen(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _e7_lage(ds)
        with _quelle():
            (e,) = await DatenChecker(ds.db)._check_bestandstage_ohne_regelmarke(await _anlage(ds))
    assert e.meldung == ("1 von 2 Bestandstagen sind vor dem Umbau gerechnet (keine Regelmarke) "
                         "— 2026-05-20 … 2026-05-20")
    assert e.action_params == {"anlage_id": e.action_params["anlage_id"], "von": "2026-05-20", "bis": "2026-05-20"}


async def test_e7_nur_kanal_tage_ohne_marke_bleibt_still(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _e7_lage(ds)
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == BESTAND_OHNE,
        ).values(verworfen={}))
        await ds.db.commit()
        with _quelle():
            assert await DatenChecker(ds.db)._check_bestandstage_ohne_regelmarke(await _anlage(ds)) == []


async def test_e7_gegenprobe_ohne_kanalzeilen_der_heutige_wortlaut_ueber_alle_tage(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _e7_lage(ds)
        await _ohne_kanalzeilen(ds)
        with _quelle():
            (e,) = await DatenChecker(ds.db)._check_bestandstage_ohne_regelmarke(await _anlage(ds))
    assert e.meldung == "4 Tag(e) sind vor dem Umbau gerechnet (keine Regelmarke) — 2026-05-20 … 2026-06-12"


# ── Einspeisung über Erzeugung ──────────────────────────────────────────────


async def _einspeise_sprung(ds, kwh: float) -> None:
    """Der Einspeise-Kanal springt am ``SPRUNG_TAG`` ab 12:00 um ``kwh`` (``state`` und ``sum``, wie HA ihn führt);
    die Stundenzeilen bleiben, wie ``aggregate_day`` sie geschrieben hat."""
    kid = (await ds.db.execute(select(Kanal.id).where(
        Kanal.anlage_id == ds.aid, Kanal.key == "basis:einspeisung"))).scalar_one()
    ab = int(datetime.combine(SPRUNG_TAG, datetime.min.time()).timestamp()) + 12 * 3600
    await ds.db.execute(text("UPDATE kanal_statistik SET sum = sum + :k, state = state + :k "
                             "WHERE kanal_id = :i AND start_ts >= :ab"), {"k": kwh, "i": kid, "ab": ab})
    await ds.db.commit()


async def _verfaelsche_stundenzeilen(ds) -> None:
    await ds.db.execute(update(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == VERFAELSCHT_TAG,
        TagesEnergieProfil.stunde == 12,
    ).values(einspeisung_kw=99.0))
    await ds.db.commit()


async def test_einspeisung_ueber_erzeugung_liest_am_kanal_tag_den_tages_leser(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _einspeise_sprung(ds, 50.0)
        await _verfaelsche_stundenzeilen(ds)
        (e,) = await DatenChecker(ds.db)._check_einspeisung_ueber_erzeugung(await _anlage(ds))
    # Der Sprung im Kanal (Weg 2, kein Deckel) ist ein Befund; die verfälschte Stundenzeile am 20.06. ist keiner —
    # an einem Kanal-Tag zählt die Zeile nicht.
    assert e.meldung == "1 Tag(e) mit mehr Einspeisung als Erzeugung (2026-06-15 … 2026-06-15)"
    assert "2026-06-15: Einspeisung 56,0 kWh, PV 18,0 kWh, Entladung 0,0 kWh" in e.details
    assert "2026-06-20" not in e.details


async def test_einspeisung_gegenprobe_ohne_kanalzeilen_wie_heute_aus_den_stundenzeilen(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _einspeise_sprung(ds, 50.0)
        await _verfaelsche_stundenzeilen(ds)
        await _ohne_kanalzeilen(ds)
        (e,) = await DatenChecker(ds.db)._check_einspeisung_ueber_erzeugung(await _anlage(ds))
    assert e.meldung == "1 Tag(e) mit mehr Einspeisung als Erzeugung (2026-06-20 … 2026-06-20)"
    assert "2026-06-15" not in e.details


async def test_ein_pruefungslauf_liest_die_kanal_tage_einmal(uhr, monkeypatch):
    """E7 fragt den Bereich aller Tage mit Stundenzeilen; «Einspeisung über Erzeugung» liegt darin — kein zweiter
    Aufruf des Tages-Lesers im selben Prüflauf."""
    aufrufe = []
    echt = bilanz_leser.kanal_tage

    async def _zaehlend(*a, **k):
        aufrufe.append(a[2:4])
        return await echt(*a, **k)

    monkeypatch.setattr(bilanz_leser, "kanal_tage", _zaehlend)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _e7_lage(ds)
        c, a = DatenChecker(ds.db), await _anlage(ds)
        with _quelle():
            await c._check_bestandstage_ohne_regelmarke(a)
        await c._check_einspeisung_ueber_erzeugung(a)
    assert aufrufe == [(BESTAND_OHNE, kg.TAGE[-1])]


# ── N-267: Stundenwerte für den Zeittarif ───────────────────────────────────


async def _kanal(db, aid: int, key: str) -> None:
    k = Kanal(anlage_id=aid, key=key, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    db.add(KanalStatistik(kanal_id=k.id, start_ts=1_780_000_000, state=1.0, sum=1.0, familie=FAMILIE_SPIEGEL))


async def _anlage_mit(db, *, kanaele=(), mit_stundenzeile=False):
    a = Anlage(anlagenname="N-267", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB")
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Akku")
    db.add_all([wb, sp])
    await db.flush()
    for key in kanaele:
        await _kanal(db, a.id, key.format(wb=wb.id, sp=sp.id))
    if mit_stundenzeile:
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=date(2026, 6, 1), stunde=12, pv_kw=1.0))
    await db.commit()
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == a.id)
    )).scalar_one()


@pytest.mark.parametrize("kanaele, stundenzeile, erwartet", [
    ((), False, False),
    ((), True, True),
    (("basis:netzbezug",), False, True),
    (("inv:{sp}:ladung_kwh",), False, True),                                  # Speicher gehört zur Bilanz-Gruppe
    (("inv:{wb}:ladung_kwh", "abgeleitet:basis:netzbezug_bewertet_kwh"), False, False),   # Wallbox, abgeleitet: nein
])
async def test_n267_stundenzeilen_oder_kanal_stunden_der_bilanz_gruppe(db, kanaele, stundenzeile, erwartet):
    a = await _anlage_mit(db, kanaele=kanaele, mit_stundenzeile=stundenzeile)
    assert await DatenChecker(db)._hat_stundenwerte(a) is erwartet


async def test_n267_ein_kanal_ohne_zeile_ist_keine_stunde(db):
    a = Anlage(anlagenname="N-267 leer", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Kanal(anlage_id=a.id, key="basis:netzbezug", einheit="kWh", art=ART_SUM))
    await db.commit()
    a = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == a.id)
    )).scalar_one()
    assert await DatenChecker(db)._hat_stundenwerte(a) is False


def test_n267_check_anlage_fragt_die_hilfsfunktion():
    src = inspect.getsource(DatenChecker.check_anlage)
    assert "hat_stundenwerte = await self._hat_stundenwerte(anlage)" in src


def test_die_tages_leser_kommen_aus_dem_lesepfad_nicht_aus_der_tabelle():
    """Kanal-Tage werden über ``bilanz_leser.kanal_tage`` bestimmt — kein ``kanal_statistik``-SQL in den beiden
    Prüfungen (Bauplan §5: «Kanal-Tage lesen den Tages-Leser, nie die Tabelle roh»)."""
    from backend.services.daten_checker.energieprofil import EnergieprofilChecks as E

    for f in (E._bilanz_kanal_tage, E._bestandstage_ohne_marke, E._tagesbilanzen, E._spike_stundenzeilen, E._spike_tage,
              E._check_bestandstage_ohne_regelmarke, E._check_einspeisung_ueber_erzeugung):
        assert "kanal_statistik" not in inspect.getsource(f).lower().replace("kanalstatistik", "kanal_statistik")
    assert "kanal_tage" in inspect.getsource(E._bilanz_kanal_tage)


# ── Counter-Spike / Doppelerfassung: nur Bestandstage (Entscheid H-1 → A) ───


async def _kwp(a) -> float:
    from backend.core.berechnungen.anlagen_kwp import anlagen_kwp

    return anlagen_kwp(a.investitionen, kg.TAGE[-1], mit_bkw=True, referenzwert=a.leistung_kwp)


async def test_spike_m03_zaehlersprung_mit_und_ohne_kanaele_keine_spitze_wie_heute(uhr, monkeypatch):
    """N3 ist ein reiner Sprung ohne Reset-Muster: die Spiegel-Prüfung meldet ihn nicht, und an einem Kanal-Tag trägt
    er keine Spitze bei (benannte Grenze). Ohne Kanäle wie heute: der Schreiber hat die Stunde geklemmt."""
    from backend.services.daten_checker.energieprofil import EnergieprofilChecks

    echt = EnergieprofilChecks._spike_tage

    async def _im_matrix_fenster(self, anlage, von, bis, kwp):   # die Leser fragen die letzten 30 Tage ab heute
        return await echt(self, anlage, kg.TAGE[0], kg.TAGE[-1], kwp)

    async with kg.datenstand("achsen", "M03", "HA") as ds:
        a = await _anlage(ds)
        assert await DatenChecker(ds.db)._spike_tage(a, kg.TAGE[0], kg.TAGE[-1], await _kwp(a)) == {}
        monkeypatch.setattr(EnergieprofilChecks, "_spike_tage", _im_matrix_fenster)
        (ok,) = await DatenChecker(ds.db)._check_energieprofil_plausibilitaet(a)
        assert ok.meldung.startswith("Keine Counter-Spikes")
        monkeypatch.setattr(EnergieprofilChecks, "_spike_tage", echt)
        await _ohne_kanalzeilen(ds)
        assert await DatenChecker(ds.db)._spike_tage(a, kg.TAGE[0], kg.TAGE[-1], await _kwp(a)) == {}


async def _spitzen(ds) -> None:
    """Eine Spitze in der Stundenzeile eines Kanal-Tags (20.06.) und eines Bestandstags davor (20.05.)."""
    await ds.db.execute(update(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == VERFAELSCHT_TAG,
        TagesEnergieProfil.stunde == 12,
    ).values(pv_kw=500.0))
    ds.db.add(TagesZusammenfassung(anlage_id=ds.aid, datum=BESTAND_OHNE, verworfen={}))
    ds.db.add(TagesEnergieProfil(anlage_id=ds.aid, datum=BESTAND_OHNE, stunde=12, pv_kw=500.0))
    await ds.db.commit()


async def test_spike_nur_der_bestandstag_traegt_eine_spitze_der_kanal_tag_nicht(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _spitzen(ds)
        a = await _anlage(ds)
        tage = await DatenChecker(ds.db)._spike_tage(a, BESTAND_OHNE, kg.TAGE[-1], await _kwp(a))
    assert tage == {BESTAND_OHNE: [(12, "pv_kw", 500.0)]}


async def test_spike_gegenprobe_ohne_kanalzeilen_beide_tage_wie_heute(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _spitzen(ds)
        await _ohne_kanalzeilen(ds)
        a = await _anlage(ds)
        tage = await DatenChecker(ds.db)._spike_tage(a, BESTAND_OHNE, kg.TAGE[-1], await _kwp(a))
    assert set(tage) == {BESTAND_OHNE, VERFAELSCHT_TAG}
