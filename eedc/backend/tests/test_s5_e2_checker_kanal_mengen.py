"""Daten-Checker-Regeln auf Mengen lesen die Lesestelle (HA-Bauform S5, Etappe E-S5-2; Bauplan §5, §10f).

Jede Regel, die eine Tagesmenge der Tageszeile prüft, liest sie seit S5a über ``kanal_stunden`` (``pv_ist_je_tag``,
``komponenten_der_tage``, ``verworfen_der_tage``) — an einem Kanal-Tag der Bilanz also die Menge von *Cockpit → Tag*
(HA-Spiegel bzw. eigene Zählerstände), an einem Bestandstag die gespeicherte Tageszeile wie bisher. Folge, je Regel
geprobt: **ein Kanal-Tag mit abweichender gespeicherter Tageszeile ergibt keinen Befund; derselbe Tag ohne Kanalzeilen
(Bestandstag) den Befund wie vor S5.**

Datenstand: die Achsen-Matrix (``kanal_bilanz_gleichheit.datenstand``, HA, Spiegel aus der Recorder-Statistik, Tage
über ``aggregate_day``; Juni/Juli 2026 sind Kanal-Tage). Die Regeln mit Rückschau ab «heute» bekommen einen festen Tag
(``datetime.date`` als Unterklasse mit festem ``today()`` — keine echte Uhr, Wächter ``test_konformitaet_echte_uhr_in_tests``);
die HA-Vergleiche (Drift, Vorzeichen, leere Tage) einen HA-Leser, der für jeden Tag die Kanal-Komponenten liefert —
also genau das, was HA dort zeigt.

Dazu die INFO-Zeile «n Tage ohne Kanal-Deckung» (S5-E2 b) und die Lesart-1-Regel N-567 («Nachtrag nach eingefrorenem
Zähler» nimmt Kanal-Tage aus). ⛔ E-Mob-Doppelzählung (H-E, Bericht E-S5-2): die Schlüssel ``wallbox_<id>``/``eauto_<id>``
gehören zu keiner Bilanz-Achse — ``komponenten_der_tage`` trägt sie an jedem Tag aus der Tageszeile; der Befund bleibt an
einem Kanal-Tag (gemessen, Probe unten), bis der Master entscheidet.

Schwesterdateien: test_daten_checker_kanal_tage.py (E-S3-3: E7, Einspeisung über Erzeugung, Spitzen),
test_s5_stunden_der_tage.py (die Lesestelle selbst).
"""

from __future__ import annotations

import datetime as _dt
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from backend.models import Anlage
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.daten_checker import DatenChecker
from backend.services.kanal import bilanz_leser
from backend.tests import kanal_bilanz_gleichheit as kg

#: «Heute» der Proben: der Tag nach dem letzten Matrix-Tag (Rückschau 30/90/180 Tage über Juni/Juli 2026).
HEUTE = date(2026, 7, 4)
TAG = date(2026, 6, 10)             # ein Kanal-Tag der Matrix
BESTAND = (date(2026, 5, 20), date(2026, 5, 21))      # vor dem ersten Kanal-Stand ⇒ Bestandstage


class _FesterTag(_dt.date):
    @classmethod
    def today(cls):
        return cls(HEUTE.year, HEUTE.month, HEUTE.day)


@pytest.fixture
def uhr(monkeypatch):
    """Die Uhr der Leser steht auf der Uhr der Matrix (``kg.JETZT_TS``)."""
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


@contextmanager
def heute_fest():
    """«Heute» der Regeln steht auf ``HEUTE`` — nur für die Dauer des Prüfungsaufrufs. Die Regeln importieren ``date``
    beim Aufruf (``from datetime import date``) bzw. am Modul (``emob``); sie bekommen eine Unterklasse mit festem
    ``today()``. Das ``datetime``-Modul selbst bleibt für SQLAlchemy unverändert (dessen Typprüfung hält die echte
    Klasse) — ersetzt wird nur der Eintrag in ``sys.modules`` für die Dauer des Aufrufs."""
    import sys
    import types

    import backend.services.daten_checker.emob as emob

    echt_modul, echt_emob = sys.modules["datetime"], emob.date
    ersatz = types.ModuleType("datetime")
    ersatz.__dict__.update(echt_modul.__dict__)
    ersatz.date = _FesterTag
    sys.modules["datetime"], emob.date = ersatz, _FesterTag
    try:
        yield
    finally:
        sys.modules["datetime"], emob.date = echt_modul, echt_emob


async def _anlage(ds) -> Anlage:
    return (await ds.db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == ds.aid)
    )).scalar_one()


async def _ohne_kanalzeilen(ds) -> None:
    """Gegenprobe: kein Kanal trägt eine Zeile ⇒ jeder Tag ist Bestandstag. Seit S5b (E-S5-3) schreibt ``aggregate_day``
    an einem Kanal-Tag keine Mengen in die Tageszeile — der Tag verliert hier seine Kanal-Deckung und wird neu aggregiert
    (§10h 3: die nächste Aggregation schreibt wieder Mengen), damit die Tageszeile die Bestandswerte trägt wie bis
    E-S5-2. Die Gegenproben verfälschen die Tageszeile danach."""
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
    await ds.db.commit()
    await kg.neu_aggregieren(ds)


async def _tz_setzen(ds, tage, **werte) -> None:
    await ds.db.execute(update(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum.in_(tuple(tage))).values(**werte))
    await ds.db.commit()


async def _komp(ds) -> dict:
    """Die Tageskomponenten am Endpunkt (``komponenten_der_tage``): an einem Kanal-Tag aus den Kanälen — die
    gespeicherte Zeile trägt dort seit S5b keine Mengen —, an einem Bestandstag die Tageszeile."""
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

    return {d: dict(k or {}) for d, k in (await komponenten_der_tage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])).items()}


def _ha(monkeypatch, werte_je_tag: dict) -> None:
    """HA verfügbar; der HA-Tagesleser liefert je Tag ``werte_je_tag[datum]`` (die Komponenten, die HA zeigt)."""
    import backend.services.ha_statistics_service as ha
    import backend.services.snapshot.lts_aggregator as lts

    async def _lts(anlage, invs_by_id, datum):
        return dict(werte_je_tag.get(datum, {}))

    monkeypatch.setattr(ha, "get_ha_statistics_service", lambda: SimpleNamespace(is_available=True))
    monkeypatch.setattr(lts, "get_komponenten_tageskwh_lts", _lts)


# ── «Verdacht auf PV-Doppelerfassung» (PV-Tagessumme → pv_ist_je_tag) ─────────


async def _pv_vielfach(ds) -> None:
    """Die gespeicherte PV dreier Tage auf das 30-Fache (spez. Ertrag ≫ 7 kWh/kWp) — die Kanäle bleiben."""
    komp = await _komp(ds)
    for d in (TAG, date(2026, 6, 11), date(2026, 6, 12)):
        await _tz_setzen(ds, [d], komponenten_kwh={k: (v * 30 if k.startswith("pv_") else v) for k, v in komp[d].items()})


async def test_pv_ueber_erfassung_kanal_tag_mit_falscher_tageszeile_kein_verdacht(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _pv_vielfach(ds)
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_pv_ueber_erfassung(a)
    assert not [e for e in erg if "Doppelerfassung" in e.meldung], [e.meldung for e in erg]


async def test_pv_ueber_erfassung_gegenprobe_bestandstag_verdacht_wie_bisher(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        await _pv_vielfach(ds)
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_pv_ueber_erfassung(a)
    (e,) = [e for e in erg if "Doppelerfassung" in e.meldung]
    assert "an 3 Tagen" in e.details


# ── Σ PV-Tageswerte eines Monats (Monatsdaten-Prüfung 3/3b) ────────────────


async def test_tages_pv_summe_monat_kanal_tage_aus_dem_spiegel_bestand_aus_der_tageszeile(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        komp = await _komp(ds)
        kanal = await DatenChecker(ds.db)._tages_pv_summe_monat(ds.aid, 2026, 6)
        await _pv_vielfach(ds)
        assert await DatenChecker(ds.db)._tages_pv_summe_monat(ds.aid, 2026, 6) == pytest.approx(kanal, abs=1e-9)
        await _ohne_kanalzeilen(ds)
        komp = await _komp(ds)
        await _pv_vielfach(ds)
        bestand = await DatenChecker(ds.db)._tages_pv_summe_monat(ds.aid, 2026, 6)
    gespeichert = sum(v for d, k in komp.items() if d.month == 6 for s, v in k.items() if s.startswith("pv_"))
    zuschlag = sum(v * 29 for d in (TAG, date(2026, 6, 11), date(2026, 6, 12))
                   for s, v in komp[d].items() if s.startswith("pv_"))
    assert bestand == pytest.approx(gespeichert + zuschlag, abs=1e-6)


# ── Drift gegen HA (eedc-Seite → komponenten_der_tage) ──────────────────────


async def test_drift_kanal_tag_mit_falscher_tageszeile_kein_befund(uhr, monkeypatch):
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        ha = await komponenten_der_tage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
        _ha(monkeypatch, ha)
        await _tz_setzen(ds, [TAG], komponenten_kwh={k: v / 2 for k, v in ha[TAG].items()})
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_datenquelle_drift(a)
    assert [e.schwere for e in erg] == ["ok"], [e.meldung for e in erg]


async def test_drift_gegenprobe_bestandstag_befund_wie_bisher(uhr, monkeypatch):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        komp = await _komp(ds)
        _ha(monkeypatch, komp)
        await _tz_setzen(ds, [TAG], komponenten_kwh={k: v / 2 for k, v in komp[TAG].items()})
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_datenquelle_drift(a)
    assert [e.details for e in erg if TAG.isoformat() in (e.details or "")], [e.meldung for e in erg]


# ── Batterie-Vorzeichen (gespeichertes Netto → komponenten_der_tage) ────────


def _vertauscht(komp: dict) -> dict:
    return {k: (-v if k.startswith("batterie_") else v) for k, v in komp.items()}


async def test_vorzeichen_kanal_tag_mit_vertauschter_tageszeile_kein_befund(uhr, monkeypatch):
    from backend.core.berechnungen import summe_batterie_netto_kwh
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

    async with kg.datenstand("achsen", "M02", "HA") as ds:
        ha = await komponenten_der_tage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
        tage = [d for d, k in ha.items() if abs(summe_batterie_netto_kwh(k or {})) >= 1.0]
        assert tage, "Form M02 trägt kein Speicher-Netto ≥ 1 kWh"
        _ha(monkeypatch, ha)
        await _tz_setzen(ds, tage[:1], komponenten_kwh=_vertauscht(ha[tage[0]]))
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_batterie_vorzeichen_historie(a)
    assert [e.schwere for e in erg] == ["ok"], [e.meldung for e in erg]


async def test_vorzeichen_gegenprobe_bestandstag_befund_wie_bisher(uhr, monkeypatch):
    from backend.core.berechnungen import summe_batterie_netto_kwh

    async with kg.datenstand("achsen", "M02", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        komp = await _komp(ds)
        tage = [d for d, k in komp.items() if abs(summe_batterie_netto_kwh(k)) >= 1.0]
        _ha(monkeypatch, komp)
        await _tz_setzen(ds, tage[:1], komponenten_kwh=_vertauscht(komp[tage[0]]))
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_batterie_vorzeichen_historie(a)
    assert any(tage[0].isoformat() in (e.details or "") + e.meldung for e in erg if e.schwere != "ok"), \
        [e.meldung for e in erg]


# ── Leere Tage trotz Zähler (gespeicherte Seite → komponenten_der_tage) ─────


async def test_leere_tage_kanal_tag_mit_leerer_tageszeile_kein_befund(uhr, monkeypatch):
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        ha = await komponenten_der_tage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
        _ha(monkeypatch, ha)
        await _tz_setzen(ds, [TAG], komponenten_kwh={})
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_leere_tage_trotz_zaehler(a)
    assert all(TAG.isoformat() not in (e.details or "") + e.meldung for e in erg), [e.meldung for e in erg]
    assert [e.schwere for e in erg] == ["ok"]


async def test_leere_tage_gegenprobe_bestandstag_befund_wie_bisher(uhr, monkeypatch):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        _ha(monkeypatch, await _komp(ds))
        await _tz_setzen(ds, [TAG], komponenten_kwh={})
        a = await _anlage(ds)
        with heute_fest():
            erg = await DatenChecker(ds.db)._check_leere_tage_trotz_zaehler(a)
    assert any(e.schwere != "ok" and TAG.isoformat() in (e.details or "") + e.meldung for e in erg), \
        [(e.schwere, e.meldung) for e in erg]


# ── E-Mob-Doppelzählung: seit S5b (E-S5-3, §10h 6) an einem E-Mob-Kanal-Tag die Kanal-Werte (E-S5-2 H-E erledigt) ──


async def _emob_doppelt(ds, komp) -> tuple:
    a = await _anlage(ds)
    wb = next(i.id for i in a.investitionen if i.typ == "wallbox")
    ea = next(i.id for i in a.investitionen if i.typ == "e-auto")
    await _tz_setzen(ds, [TAG], komponenten_kwh={**komp[TAG], f"wallbox_{wb}": -5.0, f"eauto_{ea}": -5.0})
    a = await _anlage(ds)
    with heute_fest():
        return await DatenChecker(ds.db)._check_emob_doppelzaehlung_tage(a)


async def test_emob_doppelzaehlung_kanal_tag_liest_die_kanaele(uhr):
    """Seit S5b mischt ``komponenten_der_tage`` an einem Kanal-Tag auch die E-Mob-Gruppe (Wahl ``kanal``) aus den
    Kanälen — eine verfälschte (doppelt zählende) Tageszeile ergibt dort keinen Befund (E-S5-2 H-E → S5b)."""
    async with kg.datenstand("achsen", "M08", "HA") as ds:
        erg = await _emob_doppelt(ds, await _komp(ds))
    assert not [e for e in erg if e.schwere == "warning"], [e.meldung for e in erg]


async def test_emob_doppelzaehlung_gegenprobe_bestandstag_befund_wie_bisher(uhr):
    async with kg.datenstand("achsen", "M08", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        erg = await _emob_doppelt(ds, await _komp(ds))
    (e,) = [e for e in erg if e.schwere == "warning"]
    assert TAG.isoformat() in e.meldung


# ── N-567 «Nachtrag nach eingefrorenem Zähler»: Kanal-Tage zählen nicht (§10f) ──


async def test_nachtrag_kanal_tag_kein_befund(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _tz_setzen(ds, [TAG], nachtrag={"pv": 12.5})
        assert await DatenChecker(ds.db)._check_nachtrag_nach_eingefrorenem_zaehler(await _anlage(ds)) == []


async def test_nachtrag_gegenprobe_bestandstag_befund_wie_bisher(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        await _tz_setzen(ds, [TAG], nachtrag={"pv": 12.5})
        (e,) = await DatenChecker(ds.db)._check_nachtrag_nach_eingefrorenem_zaehler(await _anlage(ds))
    assert e.meldung == "1 Tag(e) mit Nachtrag nach eingefrorenem Zähler (2026-06-10 … 2026-06-10)"


# ── INFO «n Tage ohne Kanal-Deckung» (S5-E2 b) ──────────────────────────────


async def _bestandstage(ds) -> None:
    for d in BESTAND:
        ds.db.add(TagesZusammenfassung(anlage_id=ds.aid, datum=d, verworfen={}, stunden_verfuegbar=24))
        ds.db.add(TagesEnergieProfil(anlage_id=ds.aid, datum=d, stunde=12, pv_kw=1.0))
    ds.db.add(TagesZusammenfassung(anlage_id=ds.aid, datum=date(2026, 7, 20)))     # Prognose-Zeile: zählt nicht
    await ds.db.commit()


async def test_info_tage_ohne_kanal_deckung_nennt_zahl_aeltesten_und_juengsten(uhr):
    from backend.services.daten_checker import CheckKategorie

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _bestandstage(ds)
        (e,) = await DatenChecker(ds.db)._check_tage_ohne_kanal_deckung(await _anlage(ds))
    assert e.kategorie == CheckKategorie.ENERGIEPROFIL_ABDECKUNG and e.schwere == "info"
    assert e.meldung == ("2 Tage ohne Kanal-Deckung — Mengen aus den gespeicherten Stundenwerten "
                         "(2026-05-20 … 2026-05-21)")
    assert e.action_kind is None and "Mit Kanal-Deckung: 33 Tag(e)" in e.details


async def test_info_ohne_lesart1_tage_still(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        assert await DatenChecker(ds.db)._check_tage_ohne_kanal_deckung(await _anlage(ds)) == []


async def test_info_gegenprobe_ohne_kanalzeilen_jeder_tag_mit_stunden(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _bestandstage(ds)
        await _ohne_kanalzeilen(ds)
        (e,) = await DatenChecker(ds.db)._check_tage_ohne_kanal_deckung(await _anlage(ds))
    assert e.meldung.startswith("35 Tage ohne Kanal-Deckung") and e.meldung.endswith("(2026-05-20 … 2026-07-03)")


def test_info_steht_im_pruefungslauf_nach_e7():
    import inspect

    src = inspect.getsource(DatenChecker.check_anlage)
    assert src.index("_check_bestandstage_ohne_regelmarke") < src.index("_check_tage_ohne_kanal_deckung")
