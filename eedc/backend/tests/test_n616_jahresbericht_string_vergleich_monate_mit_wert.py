"""N-616 + N-620 — Jahresbericht-PDF, Abschnitt „String-Vergleich": dieselben Monate und dieselbe Zeile wie Komponenten → PV-Strings.

**N-616.** Bis 04.10.2026 stand je Zeile das volle Jahres-SOLL (× Jahre im Gesamtzeitraum) gegen das IST der
erfassten Monate. Im laufenden Jahr, im Jahr der Inbetriebnahme, bei Zubau oder Stilllegung und im
Gesamtzeitraum nannte jede Zeile damit eine Abweichung, die nur das Datum maß (gemessen über
``build_jahresbericht_context``: 2026 mit 6 von 12 Monaten −52 %, Gesamtzeitraum 30 von 36 Monaten −20 %),
und der spezifische Ertrag im Gesamtzeitraum teilte durch alle Jahre des Berichts (ein Balkonkraftwerk
mit 20 von 36 Monaten 631 statt 1.136 kWh/kWp). Jetzt gilt die Regel der String-Sicht: SOLL nur über die
Monate, in denen die Zeile einen Wert hat (``lade_pv_je_monat``, Quelle gemessen oder verteilt), im
Anschaffungs-/Stilllegungsmonat auf die Laufzeit gekürzt (F-34, ``soll_im_laufmonat``); der spezifische
Ertrag im Gesamtzeitraum ist der saisonal gewichtete Jahreswert der Layer-Formel
``berechne_spez_ertrag_annualisiert`` (dieselbe wie Cockpit-Kachel und HA-Sensor), je Zeile über ihre Monate
und mit ihrem Monats-SOLL als Gewicht.

**N-620.** Das IST je Zeile kam aus den Monats-Fakten (``pv_je_modul`` bzw. ``bkw.erzeugung_je_investition``),
PV-Strings nimmt ``lade_pv_je_monat`` über Module UND Balkonkraftwerke. In einem Monat mit Anlagenwert und
einem BKW ohne eigenen Wert nannten beide Sichten verschiedene Zeilenwerte (Balkon 68 gegen 192,7, WestP
1.726 gegen 1.602, Σ gleich). Jetzt dieselbe Auflösung; ein verteilter Wert trägt dieselbe Kennzeichnung.
Seit N-621 teilen die Monats-Fakten den Rest genauso (der BKW-Anteil steht in ``bkw_aus_anlagenwert_kwh``).

Gehalten wird:

1. Teiljahr: SOLL = Σ PVGIS der Monate mit Wert × kWp-Anteil (ungleiche kWp 6/4) — dieselbe Zahl wie PV-Strings.
2. Inbetriebnahme am 10.05.: der Mai zählt mit 22/31 (F-34) — dieselbe Zahl wie PV-Strings.
3. Gesamtzeitraum: spez. Ertrag = IST ÷ (kWp × Σ Monatsgewichte der Monate der Zeile); im Einzeljahr IST ÷ kWp.
4. Ein vollständig erfasstes Jahr (auch mit Modul-Prognose) ist exakt die frühere Jahresformel.
5. Das Template nennt „n von N Monaten" und den Grund nur, wenn eine Zeile weniger Monate hat.
6. N-620: IST je Zeile = PV-Strings in beiden BKW-Speicherformen (Spalte und ``leistung_wp × anzahl``), Σ wie
   vorher, Kennzeichnung „geschätzt (kWp-Anteil)"; die Monats-Fakten teilen den Rest seit N-621 genauso.

PVGIS-Monatswerte sind ungleich (``1000 + 10·m``), damit eine Probe, die die falschen Monate zählt, eine andere
Zahl liefert als eine, die nur ihre Anzahl trifft.

Schwesterdateien: test_n614_jahresbericht_string_vergleich_je_monat.py (Abtretung je Monat im selben Abschnitt),
test_n613_pv_strings_abtretung_je_monat.py (dieselbe Regel in *Komponenten → PV-Strings*),
test_pdf_jahresbericht_module_monatswerte.py (Modul-Prognose im PDF).
"""

from __future__ import annotations

import re
from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

D0 = date(2024, 1, 1)
E_M = {m: 1000.0 + 10 * m for m in range(1, 13)}
SUED = ("Süd", "pv-module", 6.0, D0, None, None)
WEST = ("West", "pv-module", 4.0, D0, None, None)
BALKON = ("Balkon", "balkonkraftwerk", 0.8, D0, None, None)


async def _anlage(db, invs, werte, *, agg=None, modprog=None, bkw_wp=False) -> tuple[int, dict[str, int]]:
    """``invs``: ``[(name, typ, kWp, anschaffung, stilllegung, parent-name)]``; ``werte``: ``{(j, m): {name: kWh}}``."""
    a = Anlage(anlagenname="N616", leistung_kwp=10.8)
    db.add(a)
    await db.flush()
    ids: dict[str, int] = {}
    for name, typ, kwp, ab, still, parent in invs:
        kw = dict(anlage_id=a.id, typ=typ, bezeichnung=name, anschaffungsdatum=ab, stilllegungsdatum=still,
                  anschaffungskosten_gesamt=1.0, parent_investition_id=ids[parent] if parent else None)
        if bkw_wp and typ == "balkonkraftwerk":
            kw["parameter"] = {"leistung_wp": int(kwp * 500), "anzahl": 2}   # kWp nur in leistung_wp × anzahl
        else:
            kw["leistung_kwp"] = kwp
        inv = Investition(**kw)
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
    basis = {"Süd": 550.0, "West": 380.0, "Balkon": 70.0, "WestP": 300.0}
    return {(j, m): {n: basis[n] + m for n in namen} for m in monate}


def _sv(ctx) -> dict[str, dict]:
    return {s["bezeichnung"]: s for s in ctx["string_vergleiche"]}


async def _pv_strings(db, aid, jahr) -> dict[str, tuple[float, float]]:
    if jahr is None:
        r = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
        return {s.bezeichnung: (s.prognose_gesamt_kwh, s.ist_gesamt_kwh) for s in r.strings}
    r = await get_pv_strings(anlage_id=aid, jahr=jahr, db=db)
    return {s.bezeichnung: (s.prognose_jahr_kwh, s.ist_jahr_kwh) for s in r.strings}


def _teiljahr() -> dict:
    w: dict = {}
    w.update(_jahr(2024, ["Süd", "West"]))
    w.update(_jahr(2025, ["Süd", "West"]))
    w.update(_jahr(2026, ["Süd", "West"], range(1, 7)))
    return w


# ── 1: Teiljahr ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_teiljahr_soll_nur_ueber_die_erfassten_monate(db):
    """2026 mit Jan–Jun: SOLL = Σ e_m(1..6) × Anteil — nicht das volle Jahr (vorher 7.100 gegen 3.321, −53 %)."""
    aid, _ = await _anlage(db, [SUED, WEST], _teiljahr())
    ctx = await build_jahresbericht_context(db, aid, 2026)
    sv = _sv(ctx)
    jan_jun = sum(E_M[m] for m in range(1, 7))                    # 6210
    assert round(sv["Süd"]["prognose_kwh"], 6) == round(jan_jun * 6.0 / 10.0, 6) == 3726.0
    assert round(sv["West"]["prognose_kwh"], 6) == round(jan_jun * 4.0 / 10.0, 6)
    assert sv["Süd"]["monate"] == 6 and ctx["string_vergleich_monate_zeitraum"] == 12
    assert ctx["string_vergleich_teilzeitraum"] is True
    assert round(sv["Süd"]["abweichung_prozent"], 1) == -10.9
    ps = await _pv_strings(db, aid, 2026)
    for name, s in sv.items():
        assert (round(s["prognose_kwh"], 1), round(s["ist_kwh"], 1)) == ps[name], name


@pytest.mark.asyncio
async def test_gesamtzeitraum_soll_und_spez_ueber_die_monate_der_zeile(db):
    """30 von 36 Monaten: SOLL zweimal das volle Jahr + Jan–Jun; spez saisonal gewichtet über dieselben Monate."""
    aid, _ = await _anlage(db, [SUED, WEST], _teiljahr())
    ctx = await build_jahresbericht_context(db, aid, None)
    sv = _sv(ctx)
    assert sv["Süd"]["monate"] == 30 and ctx["string_vergleich_monate_zeitraum"] == 36
    assert round(sv["Süd"]["prognose_kwh"], 6) == round((2 * sum(E_M.values()) + 6210.0) * 0.6, 6)
    jahre = 2 + sum(E_M[m] for m in range(1, 7)) / sum(E_M.values())
    assert sv["Süd"]["spezifischer_ertrag"] == pytest.approx(sv["Süd"]["ist_kwh"] / (6.0 * jahre), rel=1e-12)
    ps = await _pv_strings(db, aid, None)
    for name, s in sv.items():
        assert (round(s["prognose_kwh"], 1), round(s["ist_kwh"], 1)) == ps[name], name


@pytest.mark.asyncio
async def test_gesamtzeitraum_spez_eines_erst_spaeter_tragenden_bkw(db):
    """BKW trägt 2024 + Jan–Aug 2025 (20 Monate), danach zwei Module als Kinder ab 01.09.2025.

    Vorher ÷ 3 Jahre (631 kWh/kWp), jetzt saisonal gewichtet über die 20 Monate (1.144,1).
    """
    kinder = [("Kind 1", "pv-module", 0.4, date(2025, 9, 1), None, "Balkon"),
              ("Kind 2", "pv-module", 0.4, date(2025, 9, 1), None, "Balkon")]
    w: dict = {}
    w.update(_jahr(2024, ["Süd", "Balkon"]))
    w.update(_jahr(2025, ["Süd", "Balkon"], range(1, 9)))
    w.update({(2025, m): {"Süd": 550.0 + m, "Kind 1": 30.0 + m, "Kind 2": 40.0 + m} for m in range(9, 13)})
    w.update({(2026, m): {"Süd": 550.0 + m, "Kind 1": 30.0 + m, "Kind 2": 40.0 + m} for m in range(1, 7)})
    aid, _ = await _anlage(db, [SUED, BALKON, *kinder], w)
    ctx = await build_jahresbericht_context(db, aid, None)
    bkw = _sv(ctx)["Balkon"]
    assert bkw["monate"] == 20 and bkw["ist_kwh"] == 1514.0
    jahre = 1 + sum(E_M[m] for m in range(1, 9)) / sum(E_M.values())
    assert round(bkw["spezifischer_ertrag"], 2) == round(1514.0 / (0.8 * jahre), 2) == 1144.09


# ── 2: Inbetriebnahme mitten im Monat ────────────────────────────────────────

@pytest.mark.asyncio
async def test_inbetriebnahme_mitten_im_monat_kuerzt_wie_pv_strings(db):
    """Anschaffung 10.05.2025: der Mai zählt mit 22 von 31 Tagen (F-34), Jan–Apr gar nicht."""
    ab = date(2025, 5, 10)
    invs = [("Süd", "pv-module", 6.0, ab, None, None), ("West", "pv-module", 4.0, ab, None, None)]
    aid, _ = await _anlage(db, invs, _jahr(2025, ["Süd", "West"], range(5, 13)))
    ctx = await build_jahresbericht_context(db, aid, 2025)
    sued = _sv(ctx)["Süd"]
    erwartet = E_M[5] * 0.6 * 22 / 31 + sum(E_M[m] for m in range(6, 13)) * 0.6
    assert sued["prognose_kwh"] == pytest.approx(erwartet, abs=1e-9)
    assert sued["monate"] == 8
    ps = await _pv_strings(db, aid, 2025)
    assert round(sued["prognose_kwh"], 1) == ps["Süd"][0]


# ── 4: vollständig erfasst = frühere Jahresformel, exakt ─────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("modprog", [None, {"Süd": 600.0, "West": 410.0}])
async def test_vollstaendiges_jahr_exakt_die_jahresformel(db, modprog):
    """Jede Zeile hat jeden Monat: SOLL ist bitgleich die Formel bis 04.10.2026, ohne Hinweis im Template."""
    import backend.services.pdf.engine as engine

    aid, _ = await _anlage(db, [SUED, WEST, BALKON], _jahr(2025, ["Süd", "West", "Balkon"]), modprog=modprog)
    ctx = await build_jahresbericht_context(db, aid, 2025)
    sv = _sv(ctx)
    for name, kwp in (("Süd", 6.0), ("West", 4.0), ("Balkon", 0.8)):
        if modprog and name in modprog:
            alt = sum({m: modprog[name] for m in range(1, 13)}.values()) * 1
        else:
            alt = sum(E_M.values()) * (kwp / 10.8) * 1
        assert sv[name]["prognose_kwh"] == alt, name          # exakt, nicht nur gerundet
        assert sv[name]["spezifischer_ertrag"] == sv[name]["ist_kwh"] / kwp / 1, name
    assert ctx["string_vergleich_teilzeitraum"] is False
    html = engine.render_html("jahresbericht.html", ctx)
    teil = html.split("String-Vergleich SOLL/IST")[1].split("Finanz-Übersicht")[0]
    assert "von 12 Monaten" not in teil and "zählen nur die Monate" not in teil


# ── 5: das Template sagt es ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_nennt_die_monate_und_den_grund(db):
    import backend.services.pdf.engine as engine

    aid, _ = await _anlage(db, [SUED, WEST], _teiljahr())
    for jahr, text in ((2026, "6 von 12 Monaten"), (None, "30 von 36 Monaten")):
        ctx = await build_jahresbericht_context(db, aid, jahr)
        html = engine.render_html("jahresbericht.html", ctx)
        teil = html.split("String-Vergleich SOLL/IST")[1].split("Finanz-Übersicht")[0]
        assert text in teil, jahr
        assert "zählen nur die Monate, in denen für ihn ein Wert erfasst ist" in teil, jahr
        assert ("Jahreswert, saisonal gewichtet" in teil) is (jahr is None), jahr


# ── 6: N-620 — dieselbe Zeile wie PV-Strings ────────────────────────────────

def _bkw_ohne_wert_neben_anlagenwert() -> tuple[list, dict, dict]:
    """Süd misst, WestP (ab 15.06.2024, kWp nur im parameter-JSON) ohne Wert in 2026, BKW ohne Wert im Februar.

    Januar und Februar 2026 tragen einen Anlagenwert — der Rest verteilt sich nach kWp.
    """
    westp = ("WestP", "pv-module", 4.0, date(2024, 6, 15), None, None)
    w: dict = {}
    w.update(_jahr(2025, ["Süd", "WestP", "Balkon"]))
    w.update({(2026, 1): {"Süd": 551.0, "Balkon": 21.0}, (2026, 2): {"Süd": 552.0},
              (2026, 3): {"Süd": 553.0, "WestP": 303.0, "Balkon": 23.0}})
    return [SUED, westp, BALKON], w, {(2026, 1): 1200.0, (2026, 2): 1300.0}


@pytest.mark.asyncio
@pytest.mark.parametrize("bkw_wp", [False, True])
@pytest.mark.parametrize("jahr", [2025, 2026, None])
async def test_n620_ist_je_zeile_wie_pv_strings(db, jahr, bkw_wp):
    """Beide Speicherformen der BKW-Leistung: PDF und PV-Strings nennen dieselbe Zahl je Zeile, Σ unverändert."""
    invs, w, agg = _bkw_ohne_wert_neben_anlagenwert()
    aid, _ = await _anlage(db, invs, w, agg=agg, bkw_wp=bkw_wp)
    ctx = await build_jahresbericht_context(db, aid, jahr)
    ps = await _pv_strings(db, aid, jahr)
    for name, s in _sv(ctx).items():
        assert round(s["ist_kwh"], 1) == ps[name][1], (name, jahr, bkw_wp)
    von, bis = ((jahr, 1), (jahr, 12)) if jahr else (None, None)
    fakten = await lade_monats_fakten(db, aid, von=von, bis=bis)
    assert round(sum(s["ist_kwh"] for s in ctx["string_vergleiche"]), 6) == round(sum(f.erzeugung.pv_kwh for f in fakten), 6)


@pytest.mark.asyncio
async def test_n620_bkw_bekommt_seinen_kwp_anteil_und_die_kennzeichnung(db):
    """Februar 2026: Anlagenwert 1300 − Süd 552 = 748 Rest, verteilt auf WestP (4 kWp) und BKW (0,8 kWp)."""
    import backend.services.pdf.engine as engine

    invs, w, agg = _bkw_ohne_wert_neben_anlagenwert()
    aid, ids = await _anlage(db, invs, w, agg=agg)
    ctx = await build_jahresbericht_context(db, aid, 2026)
    sv = _sv(ctx)
    # Januar: Rest 1200 − 551 − 21 = 628 nur an WestP (das BKW misst selbst). Februar: 748 nach kWp 4 : 0,8.
    assert sv["Balkon"]["ist_kwh"] == pytest.approx(21.0 + 748.0 * 0.8 / 4.8 + 23.0)
    assert sv["WestP"]["ist_kwh"] == pytest.approx(628.0 + 748.0 * 4.0 / 4.8 + 303.0)
    assert sv["Balkon"]["ist_verteilt"] is True and sv["Süd"]["ist_verteilt"] is False
    html = engine.render_html("jahresbericht.html", ctx)
    teil = html.split("String-Vergleich SOLL/IST")[1].split("Finanz-Übersicht")[0]
    assert teil.count("geschätzt (kWp-Anteil)") == 3          # Balkon, WestP, Fußnote
    # Die Monats-Fakten teilen den Rest seit N-621 genauso (vorher: WestP 748, BKW 0): Februar ohne BKW-Wert, der
    # Anteil des BKW steht in `bkw_aus_anlagenwert_kwh`, nicht in `BkwFakten` (eigene Werte).
    feb = {f.schluessel: f for f in await lade_monats_fakten(db, aid, von=(2026, 2), bis=(2026, 2))}[(2026, 2)]
    assert feb.erzeugung.pv_kwh == pytest.approx(1300.0) and feb.bkw.erzeugung_je_investition == {}
    assert feb.erzeugung.pv_je_modul[ids["WestP"]].pv_erzeugung_kwh == pytest.approx(748.0 * 4.0 / 4.8)
    assert feb.erzeugung.bkw_aus_anlagenwert_kwh == pytest.approx(748.0 * 0.8 / 4.8)
    assert re.search(r"Balkon", teil)


# ── Nacharbeit nach der Nachmessung: zwei Sprengsätze blieben stumm ─────────

@pytest.mark.asyncio
async def test_stilllegungsmonat_wird_gekuerzt_in_pdf_und_pv_strings(db):
    """Ost stillgelegt am 20.08.2025: der August zählt 20 von 31 Tagen — im PDF und in *Komponenten → PV-Strings*.

    Ohne die Stilllegungs-Kante (``bis=None``) stand der volle August im SOLL (Nachmessung: 1840,8 → 1929,2).
    """
    ost = ("Ost", "pv-module", 4.0, D0, date(2025, 8, 20), None)
    w = _jahr(2025, ["Süd"])
    for m in range(1, 9):                         # Ost misst bis zu seiner Stilllegung
        w[(2025, m)]["Ost"] = 300.0 + m
    aid, _ = await _anlage(db, [SUED, ost], w)
    ctx = await build_jahresbericht_context(db, aid, 2025)
    erwartet = (sum(E_M[m] for m in range(1, 8)) * 0.4 + E_M[8] * 0.4 * 20 / 31)
    assert _sv(ctx)["Ost"]["prognose_kwh"] == pytest.approx(erwartet, abs=1e-9)
    assert _sv(ctx)["Ost"]["monate"] == 8
    ps = await _pv_strings(db, aid, 2025)
    assert ps["Ost"][0] == round(erwartet, 1)


@pytest.mark.asyncio
async def test_aktiver_string_ohne_wert_bekommt_fuer_den_monat_kein_soll(db):
    """West hat im März keinen Wert, Süd schon, kein Anlagenwert: der März zählt für West nicht (11 Monate)."""
    w = _jahr(2025, ["Süd", "West"])
    del w[(2025, 3)]["West"]
    aid, _ = await _anlage(db, [SUED, WEST], w)
    ctx = await build_jahresbericht_context(db, aid, 2025)
    west = _sv(ctx)["West"]
    assert west["monate"] == 11
    assert west["prognose_kwh"] == pytest.approx((sum(E_M.values()) - E_M[3]) * 0.4, abs=1e-9)
    assert _sv(ctx)["Süd"]["monate"] == 12
    ps = await _pv_strings(db, aid, 2025)
    assert round(west["prognose_kwh"], 1) == ps["West"][0]


@pytest.mark.asyncio
async def test_spez_gesamtzeitraum_ist_der_jahreswert_der_cockpit_kachel(db):
    """Ein String, nur Mai–September erfasst, Erzeugung genau nach den PVGIS-Gewichten ⇒ derselbe Jahreswert wie
    die Kachel in *Cockpit → Übersicht* (eine lineare Hochrechnung Monate ÷ 12 läge hier daneben)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    w = {(2025, m): {"Süd": round(E_M[m] / sum(E_M.values()) * 1000.0 * 6.0, 6)} for m in range(5, 10)}
    aid, _ = await _anlage(db, [SUED], w)
    ctx = await build_jahresbericht_context(db, aid, None)
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=None, db=db)
    assert _sv(ctx)["Süd"]["spezifischer_ertrag"] == pytest.approx(1000.0, rel=1e-9)
    assert _sv(ctx)["Süd"]["spezifischer_ertrag"] == pytest.approx(u.spezifischer_ertrag_kwh_kwp, abs=0.5)
    ctx_jahr = await build_jahresbericht_context(db, aid, 2025)
    assert _sv(ctx_jahr)["Süd"]["spezifischer_ertrag"] == pytest.approx(sum(z["Süd"] for z in w.values()) / 6.0)
