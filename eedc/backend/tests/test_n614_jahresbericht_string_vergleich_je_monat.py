"""N-614 — Jahresbericht-PDF, Abschnitt „String-Vergleich": die Abtretung eines Balkonkraftwerks gilt je Monat.

Seit N-266 darf ein Balkonkraftwerk Parent von `pv-module` sein; es tritt dann
Erzeugung und kWp an seine Kinder ab. ``pdf/builders/jahresbericht.py`` wandte
den Selektor ``erzeuger_traeger`` bis 03.10.2026 **einmal über alle Erzeuger
des Berichts** an — derselbe Fehler, den N-613 in *Komponenten → PV-Strings*
behoben hat. Ein BKW, dem im Berichtszeitraum Module zugeordnet wurden, hatte
keine Zeile, und seine Erzeugung aus den Monaten davor fehlte in der Summe des
Abschnitts (gemessen: 930 gegen 1860 kWh in der Monatstabelle desselben PDFs;
mit Anlagenwert 1070 gegen 2000; Kinder mitten im Jahr 11 680 gegen 12 276).

Gehalten wird:

1. Σ String-IST des Abschnitts = PV der Monatstabelle desselben PDFs = ``pv_kwh``
   der Monats-Fakten (Einzeljahr und Gesamtzeitraum).
2. Das BKW hat eine eigene Zeile für die Monate, in denen es selbst trägt — es
   sind dieselben Zeilen wie in *Komponenten → PV-Strings*.
3. SOLL je Zeile Monat für Monat: nur die Monate, in denen die Zeile trägt, und
   der kWp-Anteil über dem Nenner der Menge, die in diesem Monat trägt — BKW und
   Kinder stehen nie zugleich im Nenner (Kinder bewusst mit 0,6 kWp ≠ 0,4 des
   BKW-Anteils, damit ein falscher Nenner eine andere Zahl ergibt; die Lehre aus
   N-613, wo ein Nenner-Sprengsatz bei gleichen kWp stumm blieb).
4. Ohne BKW mit später zugeordneten Kindern bleibt der Abschnitt wie vorher —
   die Jahresformel (Jahres-SOLL × kWp-Anteil × Jahre) ist hier ausgeschrieben.

PVGIS-Monatswerte sind ungleich (``1000 + 10·m``), damit eine Probe, die die
falschen Monate zählt, eine andere Zahl liefert als eine, die nur ihre Anzahl
trifft.

Schwesterdateien: test_n613_pv_strings_abtretung_je_monat.py (dieselbe Regel in
*Komponenten → PV-Strings*), test_n614_selektor_nach_zeitfilter_co2_kanon.py und
test_n615_tag_abtretung_am_datum.py (dieselbe Klasse an anderen Stellen),
test_pdf_jahresbericht_module_monatswerte.py (Modul-Prognose im PDF).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

D0 = date(2024, 1, 1)
SEP_25 = date(2025, 9, 1)
E_M = {m: 1000.0 + 10 * m for m in range(1, 13)}

SUED = ("Süd", "pv-module", 6.0, D0, None)
WEST = ("West", "pv-module", 4.0, D0, None)
BALKON = ("Balkon", "balkonkraftwerk", 0.8, D0, None)


def _kinder(ab: date, kwp: float = 0.4) -> list[tuple]:
    return [("Kind 1", "pv-module", kwp, ab, "Balkon"), ("Kind 2", "pv-module", kwp, ab, "Balkon")]


async def _anlage(db, invs, werte, *, agg=None, modprog=None) -> tuple[int, dict[str, int]]:
    """``invs``: ``[(name, typ, kWp, anschaffung, parent-name)]``; ``werte``: ``{(j, m): {name: kWh}}``."""
    a = Anlage(anlagenname="N614", leistung_kwp=10.8)
    db.add(a)
    await db.flush()
    ids: dict[str, int] = {}
    for name, typ, kwp, ab, parent in invs:
        inv = Investition(
            anlage_id=a.id, typ=typ, bezeichnung=name, leistung_kwp=kwp, anschaffungsdatum=ab,
            anschaffungskosten_gesamt=1.0, parent_investition_id=ids[parent] if parent else None,
        )
        db.add(inv)
        await db.flush()
        ids[name] = inv.id
    for (j, m) in sorted(set(werte) | set(agg or {})):
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                           pv_erzeugung_kwh=(agg or {}).get((j, m))))
        for name, kwh in werte.get((j, m), {}).items():
            db.add(InvestitionMonatsdaten(investition_id=ids[name], jahr=j, monat=m,
                                          verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    db.add(PVGISPrognose(
        anlage_id=a.id, abgerufen_am=datetime(2025, 1, 1), latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, jahresertrag_kwh=12000.0,
        spezifischer_ertrag_kwh_kwp=1000.0, gesamt_leistung_kwp=12.0,
        monatswerte=[{"monat": m, "e_m": E_M[m]} for m in range(1, 13)],
        module_monatswerte=(
            {str(ids[n]): [{"monat": m, "e_m": v} for m in range(1, 13)] for n, v in modprog.items()}
            if modprog else None
        ),
    ))
    await db.commit()
    return a.id, ids


def _jahr(j: int, namen: list[str], monate=range(1, 13)) -> dict:
    basis = {"Süd": 550.0, "West": 380.0, "Balkon": 70.0, "Kind 1": 30.0, "Kind 2": 40.0}
    return {(j, m): {n: basis[n] + m for n in namen} for m in monate}


def _mitten_im_jahr(kind_kwp: float = 0.4) -> tuple[list, dict]:
    """Kinder ab 01.09.2025: 2024 und Jan–Aug 2025 trägt das BKW, ab September die Kinder."""
    w: dict = {}
    w.update(_jahr(2024, ["Süd", "West", "Balkon"]))
    w.update(_jahr(2025, ["Süd", "West", "Balkon"], range(1, 9)))
    w.update(_jahr(2025, ["Süd", "West", "Kind 1", "Kind 2"], range(9, 13)))
    w.update(_jahr(2026, ["Süd", "West", "Kind 1", "Kind 2"], range(1, 7)))
    return [SUED, WEST, BALKON, *_kinder(SEP_25, kind_kwp)], w


def _zeilen(ctx) -> list[tuple]:
    return [(s["bezeichnung"], s["leistung_kwp"], round(s["prognose_kwh"], 2), round(s["ist_kwh"], 2))
            for s in ctx["string_vergleiche"]]


async def _summen(db, aid, jahr):
    ctx = await build_jahresbericht_context(db, aid, jahr)
    von, bis = ((jahr, 1), (jahr, 12)) if jahr else (None, None)
    fakten = await lade_monats_fakten(db, aid, von=von, bis=bis)
    return (
        ctx,
        round(sum(s["ist_kwh"] for s in ctx["string_vergleiche"]), 2),
        round(sum(z["pv_erzeugung_kwh"] for z in ctx["monats_zeilen"]), 2),
        round(sum(f.erzeugung.pv_kwh for f in fakten), 2),
    )


# ── 1 + 2: Summe und Zeilen ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_k3_bkw_traegt_bis_august_summe_gleich_monatstabelle(db):
    """K3: Kinder ab 09/2025, im Mai 2025 misst nur das BKW (930) neben Süd und West."""
    aid, _ = await _anlage(db, [SUED, WEST, BALKON, *_kinder(SEP_25)],
                           {(2025, 5): {"Süd": 550.0, "West": 380.0, "Balkon": 930.0}})
    for jahr in (2025, None):
        ctx, ist, tabelle, fakten = await _summen(db, aid, jahr)
        assert (ist, tabelle, fakten) == (1860.0, 1860.0, 1860.0), jahr
        # Seit N-616 (04.10.2026) zählt jede Zeile nur die Monate, in denen sie einen Wert hat — hier nur den
        # Mai (e_m 1050, Nenner der tragenden Menge Süd + West + BKW = 10,8). Bis dahin stand hier das SOLL
        # Jan–Aug (BKW 619,26) bzw. das volle Jahr (Süd 7100) gegen einen einzigen gemessenen Monat; die
        # Kinder ohne einen einzigen Wert hatten SOLL ohne IST und fallen jetzt weg (keine Zeile ohne SOLL
        # und IST — Bestand). Gehalten bleibt die N-614-Substanz: das BKW hat eine eigene Zeile, Σ = Tabelle.
        assert _zeilen(ctx) == [
            ("Süd", 6.0, 583.33, 550.0), ("West", 4.0, 388.89, 380.0), ("Balkon", 0.8, 77.78, 930.0),
        ], jahr


@pytest.mark.asyncio
async def test_k4_dach_luecke_mit_anlagenwert(db):
    """K4: Dach ohne eigene Werte, BKW 930, Anlagenwert 2000 — das BKW zählt neben der Verteilung."""
    aid, _ = await _anlage(db, [SUED, WEST, BALKON, *_kinder(SEP_25)],
                           {(2025, 5): {"Balkon": 930.0}}, agg={(2025, 5): 2000.0})
    for jahr in (2025, None):
        ctx, ist, tabelle, fakten = await _summen(db, aid, jahr)
        assert (ist, tabelle, fakten) == (2000.0, 2000.0, 2000.0), jahr
        # N-616: die Kinder haben im Zeitraum keinen Monat mit Wert ⇒ weder SOLL noch IST ⇒ keine Zeile.
        assert [(z[0], z[3]) for z in _zeilen(ctx)] == [
            ("Süd", 642.0), ("West", 428.0), ("Balkon", 930.0),
        ], jahr


@pytest.mark.asyncio
async def test_kinder_mitten_im_jahr_einzeljahr_und_gesamtzeitraum(db):
    invs, werte = _mitten_im_jahr()
    aid, _ = await _anlage(db, invs, werte)
    erwartet = {2024: 12234.0, 2025: 12276.0, 2026: 6084.0, None: 30594.0}
    for jahr, summe in erwartet.items():
        ctx, ist, tabelle, fakten = await _summen(db, aid, jahr)
        assert (ist, tabelle, fakten) == (summe, summe, summe), jahr
    ctx = await build_jahresbericht_context(db, aid, None)
    zeilen = {z[0]: z for z in _zeilen(ctx)}
    # BKW: 2024 voll (12 780 × 0,8 / 10,8 = 946,67) + 2025 Jan–Aug (619,26); Kinder: 2025 Sep–Dez + 2026
    # Jan–Jun — seit N-616 nur die Monate mit Wert ((4420 + 6210) × 0,4 / 10,8 = 393,70; bis dahin das volle
    # Jahr 2026, 637,04, gegen sechs gemessene Monate).
    assert zeilen["Balkon"] == ("Balkon", 0.8, 1565.93, 1514.0)
    assert zeilen["Kind 1"][2] == 393.7


@pytest.mark.asyncio
async def test_reine_bkw_anlage_mit_spaeten_kindern(db):
    w: dict = {}
    w.update(_jahr(2024, ["Balkon"]))
    w.update(_jahr(2025, ["Balkon"], range(1, 9)))
    w.update(_jahr(2025, ["Kind 1", "Kind 2"], range(9, 13)))
    aid, _ = await _anlage(db, [BALKON, *_kinder(SEP_25)], w)
    ctx, ist, tabelle, fakten = await _summen(db, aid, 2025)
    assert (ist, tabelle, fakten) == (960.0, 960.0, 960.0)
    # Jan–Aug trägt das BKW allein: das ganze Anlagen-SOLL dieser Monate (8360), danach die Kinder je zur Hälfte.
    assert _zeilen(ctx) == [
        ("Balkon", 0.8, 8360.0, 596.0), ("Kind 1", 0.4, 2210.0, 162.0), ("Kind 2", 0.4, 2210.0, 202.0),
    ]
    ctx, ist, tabelle, fakten = await _summen(db, aid, None)
    assert (ist, tabelle, fakten) == (1878.0, 1878.0, 1878.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("jahr", [2024, 2025, 2026, None])
async def test_dieselben_zeilen_wie_komponenten_pv_strings(db, jahr):
    """Die Zeilen des Abschnitts sind die von *Komponenten → PV-Strings* (der Kommentar im Builder sagt es zu).

    Das PDF lässt eine Zeile ohne SOLL und ohne IST weg; im Einzeljahr fehlen dort
    außerdem Erzeuger, die im Jahr nicht aktiv waren (Kinder 2024) — beides
    Zeilen, die die Komponenten-Sicht leer zeigt.
    """
    invs, werte = _mitten_im_jahr()
    aid, _ = await _anlage(db, invs, werte)
    ctx = await build_jahresbericht_context(db, aid, jahr)
    if jahr is None:
        ps = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
        sicht = [s.bezeichnung for s in ps.strings if s.ist_gesamt_kwh or s.prognose_gesamt_kwh]
    else:
        ps = await get_pv_strings(anlage_id=aid, jahr=jahr, db=db)
        sicht = [s.bezeichnung for s in ps.strings if s.ist_jahr_kwh or s.prognose_jahr_kwh]
    assert [s["bezeichnung"] for s in ctx["string_vergleiche"]] == sicht


# ── 3: der Nenner je Monat ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nenner_je_monat_nie_bkw_und_kinder_zugleich(db):
    """Kinder 2 × 0,6 kWp (Σ 1,2 ≠ 0,8 des BKW): Jan–Aug Nenner 10,8, Sep–Dez 11,2.

    Süd = 8360 × 6/10,8 + 4420 × 6/11,2 = 7012,30. Mit der Struktur als Nenner
    (11,2 in jedem Monat) wären es 6846,43, mit BKW und Kindern zugleich (12,0)
    6390,00. Σ SOLL ist das volle Anlagen-SOLL des Jahres — nichts doppelt, nichts fehlt.
    """
    invs, werte = _mitten_im_jahr(kind_kwp=0.6)
    aid, _ = await _anlage(db, invs, werte)
    ctx = await build_jahresbericht_context(db, aid, 2025)
    zeilen = {z[0]: z for z in _zeilen(ctx)}
    assert zeilen["Süd"][2] == 7012.3
    assert zeilen["Kind 1"][2] == 236.79
    assert round(sum(s["prognose_kwh"] for s in ctx["string_vergleiche"]), 2) == 12780.0


@pytest.mark.asyncio
async def test_modul_prognose_nur_fuer_die_monate_der_zeile(db):
    """Hat das BKW eine eigene Modul-Prognose (80 je Monat), zählt sie nur Jan–Aug 2025 (640)."""
    invs, werte = _mitten_im_jahr()
    aid, _ = await _anlage(db, invs, werte, modprog={"Süd": 600.0, "West": 400.0, "Balkon": 80.0})
    ctx = await build_jahresbericht_context(db, aid, 2025)
    zeilen = {z[0]: z for z in _zeilen(ctx)}
    assert zeilen["Balkon"][2] == 640.0
    assert zeilen["Süd"][2] == 7200.0
    assert zeilen["Kind 1"][2] == 163.7      # ohne eigene Modul-Prognose: 4420 × 0,4 / 10,8


# ── 4: ohne späte Kinder unverändert ─────────────────────────────────────────

def _jahresformel(zeilen_kwp: dict[str, float], anzahl_jahre: int) -> dict[str, float]:
    """Die Formel bis 03.10.2026 und für jede Anlage ohne selbst tragendes BKW: Jahres-SOLL × Anteil × Jahre."""
    gesamt = sum(zeilen_kwp.values())
    return {n: sum(E_M.values()) * (k / gesamt) * anzahl_jahre for n, k in zeilen_kwp.items()}


UNVERAENDERT = {
    "reine Module": ([SUED, WEST], ["Süd", "West"], {"Süd": 6.0, "West": 4.0}),
    "Module + BKW ohne Kinder": ([SUED, WEST, BALKON], ["Süd", "West", "Balkon"],
                                 {"Süd": 6.0, "West": 4.0, "Balkon": 0.8}),
    "BKW mit Kindern von Anfang an": ([SUED, WEST, BALKON, *_kinder(D0)], ["Süd", "West", "Kind 1", "Kind 2"],
                                      {"Süd": 6.0, "West": 4.0, "Kind 1": 0.4, "Kind 2": 0.4}),
    "reine BKW-Anlage": ([BALKON], ["Balkon"], {"Balkon": 0.8}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", list(UNVERAENDERT))
async def test_ohne_spaete_kinder_jahresformel_unveraendert(db, fall):
    invs, namen, kwp = UNVERAENDERT[fall]
    werte: dict = {}
    werte.update(_jahr(2024, namen))
    werte.update(_jahr(2025, namen))
    aid, _ = await _anlage(db, invs, werte)
    for jahr, jahre in ((2025, 1), (None, 2)):
        ctx, ist, tabelle, fakten = await _summen(db, aid, jahr)
        assert ist == tabelle == fakten, (fall, jahr)
        soll = {s["bezeichnung"]: s["prognose_kwh"] for s in ctx["string_vergleiche"]}
        assert soll == _jahresformel(kwp, jahre), (fall, jahr)
