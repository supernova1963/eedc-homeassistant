"""Die Monats-KPIs — N-92 für den Altbestand, R8 für Tage mit Regelmarke.

`get_monatsauswertung` war der **Zwilling** von `core/berechnungen/tagesbilanz.py`
mit einer eigenen N-92-Zählung über die Stunden des Monats (N-129-Klasse: eine
zweite Implementierung derselben Formel). ⭐ **Seit „Zählerlücken wie HA"
(26.09.2026) faltet der Monat TAGESbilanzen** (`monatsbilanz_aus_tagen`, R8):
jeder Tag rechnet nach seiner Regelmarke, der Monat summiert.

**Umgeschrieben, nicht gelockert** (Vorlage Fassung 7 §8): Die drei Lagen von
N-92 stehen hier weiter — als **Altbestand** (Tage ohne Regelmarke rechnen N-92
wie bisher, E6: ihre Stunden haben die Lückenenergie verloren) **und** als Tage
**mit** Regelmarke (R7/R8: Unterdrückung nur im Total-Fall oder bei
``verworfen``). Dazu die R8-Lagen aus P12: ein PV-toter Tag lässt den Monats-EV
stehen, ein Einspeisungs-toter ebenso, ein ``verworfen``-Tag nimmt ihn, ein
Altbestandstag mit N-92-``None`` nimmt ihn.

Schwesterdateien: test_tagesbilanz_pv_nicht_erfasst.py (der Tag),
test_tage_werte_symmetrie.py (Σ Tage == Monat).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.energie_profil.views import get_monatsauswertung
from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

ALTBESTAND = None
MARKE = {}


def _stunde(aid: int, tag: date, h: int, *, pv=None, vb=None, ei=None, nz=None):
    return TagesEnergieProfil(
        anlage_id=aid, datum=tag, stunde=h,
        pv_kw=pv, verbrauch_kw=vb, einspeisung_kw=ei, netzbezug_kw=nz,
        batterie_kw=None, waermepumpe_kw=None,
    )


async def _anlage(db, rows_fn, marken: dict | None = None) -> int:
    """``marken``: {tag: verworfen} — ohne Eintrag gibt es keine Tageszeile (Altbestand)."""
    anlage = Anlage(anlagenname="N92-Abdeckung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add_all(rows_fn(anlage.id))
    jetzt = datetime(2026, 9, 26)
    for tag, verworfen in (marken or {}).items():
        db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=tag, verworfen=verworfen,
                                    source_provenance={}, created_at=jetzt, updated_at=jetzt))
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
@pytest.mark.parametrize("regel,erwartet", [(ALTBESTAND, None), (MARKE, 62.5)],
                         ids=["altbestand-n92", "regelmarke-r8"])
async def test_einspeisung_teilabgedeckt(db, regel, erwartet):
    """PV über 8 Stunden, Einspeisung nur über 6.

    Altbestand: die Quote ist keine Aussage (N-92). Regelmarke: EV = 16 − 6,
    Quote 62,5 % — wie HA (P11 auf Monatsebene)."""
    tag = date(2026, 5, 10)

    def rows(aid):
        r = [_stunde(aid, tag, h, pv=2.0, ei=1.0) for h in range(8, 14)]
        r += [_stunde(aid, tag, h, pv=2.0) for h in (14, 15)]
        return r

    aid = await _anlage(db, rows, {tag: regel} if regel is not None else None)
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    assert monat.pv_kwh == 16.0
    assert monat.einspeisung_kwh == 6.0
    assert monat.eigenverbrauch_prozent == erwartet


@pytest.mark.asyncio
@pytest.mark.parametrize("regel", [ALTBESTAND, MARKE], ids=["altbestand-n92", "regelmarke-r8"])
async def test_netzbezug_nie_gemessen_unterdrueckt_die_autarkie(db, regel):
    """Verbrauch gemessen, Netzbezug nirgends ⇒ nicht „100 % Autarkie" — in
    beiden Regeln (unter R7 ist Netzbezug ein Total-Fall)."""
    tag = date(2026, 5, 11)

    def rows(aid):
        return [_stunde(aid, tag, h, vb=1.0, ei=2.0) for h in range(8, 16)]

    aid = await _anlage(db, rows, {tag: regel} if regel is not None else None)
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    assert monat.netzbezug_kwh == 0.0
    assert monat.autarkie_prozent is None  # 100.0 wäre der Befund


@pytest.mark.asyncio
@pytest.mark.parametrize("regel", [ALTBESTAND, MARKE], ids=["altbestand-n92", "regelmarke-r8"])
async def test_volle_abdeckung_liefert_beide_quoten_unveraendert(db, regel):
    """Gegenprobe: keine Regel darf den Normalfall verschieben — mit gemessenen
    Nullen auf beiden Achsen."""
    tag = date(2026, 5, 12)

    def rows(aid):
        r = [_stunde(aid, tag, h, pv=4.0, vb=1.0, ei=3.0, nz=0.0) for h in range(9, 15)]
        r += [_stunde(aid, tag, 22, pv=0.0, vb=1.0, ei=0.0, nz=1.0)]
        return r

    aid = await _anlage(db, rows, {tag: regel} if regel is not None else None)
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    assert monat.pv_kwh == 24.0
    assert monat.verbrauch_kwh == 7.0          # R7: 24 PV + 1 Netz − 18 Einsp
    assert monat.autarkie_prozent == pytest.approx(round(6 / 7 * 100, 1))
    assert monat.eigenverbrauch_prozent == 25.0


# ── P12: R8 symmetrisch ───────────────────────────────────────────────────


def _voller_tag(aid, tag, *, pv=True, ei=True):
    return [_stunde(aid, tag, h, pv=(3.0 if pv else None), vb=1.0,
                    ei=(2.0 if ei else None), nz=0.0) for h in range(10, 14)]


@pytest.mark.asyncio
async def test_p12_pv_toter_tag_laesst_den_monats_ev_stehen(db):
    t1, t2 = date(2026, 6, 1), date(2026, 6, 2)
    aid = await _anlage(db, lambda a: _voller_tag(a, t1) + _voller_tag(a, t2, pv=False),
                        {t1: MARKE, t2: MARKE})
    monat = await get_monatsauswertung(aid, jahr=2026, monat=6, top_n=10, db=db)
    # Der Total-Fall-Tag propagiert nicht (W4): Σ PV − Σ Einsp = 12 − 16 = −4.
    # ⭐ Vorlage §10 (Entscheid Master 26.09.): EV einmal bei 0 geklemmt — eine
    # Quote unter 0 ist keine Kennzahl, sondern ein Widerspruch der Eingänge
    # (PV-Ausfall bei laufender Einspeisung). Bis dahin stand hier −33,3 % „wie
    # HA"; die Zahl bleibt stehen (kein None, G3), aber als 0.
    assert monat.eigenverbrauch_prozent == 0.0


@pytest.mark.asyncio
async def test_p12_einspeisungs_toter_tag_laesst_den_monats_ev_stehen(db):
    t1, t2 = date(2026, 6, 1), date(2026, 6, 2)
    aid = await _anlage(db, lambda a: _voller_tag(a, t1) + _voller_tag(a, t2, ei=False),
                        {t1: MARKE, t2: MARKE})
    monat = await get_monatsauswertung(aid, jahr=2026, monat=6, top_n=10, db=db)
    assert monat.eigenverbrauch_prozent == pytest.approx(round((24 - 8) / 24 * 100, 1))


@pytest.mark.asyncio
async def test_p12_verworfen_tag_nimmt_dem_monat_den_ev(db):
    t1, t2 = date(2026, 6, 1), date(2026, 6, 2)
    aid = await _anlage(db, lambda a: _voller_tag(a, t1) + _voller_tag(a, t2),
                        {t1: MARKE, t2: {"pv": 31368.0}})
    monat = await get_monatsauswertung(aid, jahr=2026, monat=6, top_n=10, db=db)
    assert monat.eigenverbrauch_prozent is None
    assert monat.autarkie_prozent is None


@pytest.mark.asyncio
async def test_p12_altbestandstag_mit_n92_none_nimmt_dem_monat_den_ev(db):
    t1, t2 = date(2026, 6, 1), date(2026, 6, 2)

    def rows(a):
        r = _voller_tag(a, t1)
        r += [_stunde(a, t2, h, pv=3.0, vb=1.0, ei=2.0, nz=0.0) for h in range(10, 13)]
        r += [_stunde(a, t2, 13, pv=3.0, vb=1.0, nz=0.0)]      # Einspeisung fehlt 1 h
        return r

    aid = await _anlage(db, rows, {t1: MARKE})                 # t2 ohne Marke
    monat = await get_monatsauswertung(aid, jahr=2026, monat=6, top_n=10, db=db)
    assert monat.eigenverbrauch_prozent is None


@pytest.mark.asyncio
async def test_p12_monat_gleich_summe_der_tage(db):
    t1, t2 = date(2026, 6, 1), date(2026, 6, 2)
    aid = await _anlage(db, lambda a: _voller_tag(a, t1) + _voller_tag(a, t2, ei=False),
                        {t1: MARKE, t2: MARKE})
    monat = await get_monatsauswertung(aid, jahr=2026, monat=6, top_n=10, db=db)
    assert monat.pv_kwh == 24.0
    assert monat.einspeisung_kwh == 8.0
    # Verbrauch = Σ Tages-Gesamtverbrauch: t1 = 12 PV − 8 Einsp = 4; t2 = Total-Fall
    assert monat.verbrauch_kwh == 4.0
