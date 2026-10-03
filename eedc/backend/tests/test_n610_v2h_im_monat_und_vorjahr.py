"""N-610 — Cockpit → Monat rechnet die Bilanz über den Layer: V2H-Entladung zählt zum Eigenverbrauch; das Vorjahr ist
derselbe Monat.

Gemessen im Bau (C5c, r28-Kopie): `aktueller_monat/aggregation.py::berechne_bilanzwerte` rechnete den Eigenverbrauch
inline als `Direktverbrauch + Speicher-Entladung − Abgabe` — ohne V2H. Der Layer (`core/berechnungen/verbrauch.py`) und
damit Monats-Fakten, Übersicht, Monatsreihe, PDF, HA-Export und der Vorjahres-Block rechnen mit V2H. r28 A1 Nov 2024:
direkt 420,92 kWh, als Vorjahr 445,9 kWh (V2H 25 kWh); alle 17 Paar-Differenzen der Kopien == V2H des Monats.

Fixture (wie der r28-Fall, verkleinert): PV 500 kWh, Einspeisung 100, Netzbezug 300, Speicher Ladung 120 / Entladung 116,
E-Auto mit V2H-Entladung 25 kWh — Juni 2024 und Juni 2025 gleich.

Schwesterdateien: test_ergebnis_symmetrie_monat_jahr.py, test_vorjahr_gesamtnettoertrag_symmetrie.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def anlage_mit_v2h(db) -> int:
    a = Anlage(anlagenname="V2H", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=10.0))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Akku", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    auto = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1),
                       parameter={"v2h_faehig": True})
    db.add_all([pv, sp, auto])
    await db.flush()
    for jahr in (2024, 2025):
        db.add(Monatsdaten(anlage_id=a.id, jahr=jahr, monat=6, einspeisung_kwh=100.0, netzbezug_kwh=300.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=jahr, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
        db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=jahr, monat=6,
                                      verbrauch_daten={"ladung_kwh": 120.0, "entladung_kwh": 116.0}))
        db.add(InvestitionMonatsdaten(investition_id=auto.id, jahr=jahr, monat=6,
                                      verbrauch_daten={"km_gefahren": 500, "v2h_entladung_kwh": 25.0}))
    await db.commit()
    return a.id


@pytest.mark.asyncio
async def test_monat_zaehlt_die_v2h_entladung_zum_eigenverbrauch(db):
    aid = await anlage_mit_v2h(db)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    # Direkt 500 − 100 − 120 = 280; EV = 280 + 116 + 25 = 421 (ohne V2H: 396).
    assert d.direktverbrauch_kwh == pytest.approx(280.0)
    assert d.eigenverbrauch_kwh == pytest.approx(421.0), "ohne V2H wären es 396 kWh (N-610)"
    assert d.gesamtverbrauch_kwh == pytest.approx(721.0)
    assert d.autarkie_prozent == pytest.approx(round(421 / 721 * 100, 1))


@pytest.mark.asyncio
async def test_monat_und_uebersicht_nennen_denselben_eigenverbrauch(db):
    aid = await anlage_mit_v2h(db)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    ue = await get_cockpit_uebersicht(anlage_id=aid, jahr=2025, db=db)
    assert ue.eigenverbrauch_kwh == pytest.approx(d.eigenverbrauch_kwh, abs=0.05)
    assert ue.autarkie_prozent == pytest.approx(d.autarkie_prozent, abs=0.05)


# ── Schritt 2: der Vorjahres-Block ist derselbe Monat (Symmetrie über alle Felder) ─────────────────────────────

async def _fixture_w3(db):
    from backend.tests.test_ergebnis_symmetrie_monat_jahr import anlage_alle_achsen
    return await anlage_alle_achsen(db), [(2026, m) for m in range(1, 13)]  # 2026 ohne Daten: Vorjahr = 2025


async def _fixture_n605(db):
    from backend.tests.test_n605_wp_ersparnis_aus_geraetezeilen import _anlage
    return await _anlage(db), [(2025, 6)]


async def _fixture_n607(db):
    from backend.tests.test_n607_ev_preis_monatsroute import _anlage
    return await _anlage(db), [(2025, 7)]


async def _fixture_v2h(db):
    return await anlage_mit_v2h(db), [(2025, 6)]


def _erwartete_anwesenheit(feld: str, d: dict) -> bool:
    """Die Anwesenheitsregeln des Vorjahres-Blocks bis 03.10.2026 (gelesen gegen `b8c59b08:…/vergleich.py`),
    UNABHÄNGIG vom Code nachgeschrieben — sonst prüfte die Probe nur, dass zwei Stellen denselben Fehler machen."""
    from backend.api.routes.aktueller_monat.vergleich import VORJAHR_QUELLFELD

    v = d.get(VORJAHR_QUELLFELD.get(feld, feld))
    immer = ("einspeisung_kwh", "netzbezug_kwh", "netzbezug_durchschnittspreis_cent", "einspeise_durchschnittspreis_cent",
             "eigenverbrauch_kwh", "direktverbrauch_kwh", "gesamtverbrauch_kwh", "autarkie_prozent")
    if feld in immer:
        return True
    if feld in ("pv_erzeugung_kwh", "speicher_ladung_kwh", "speicher_entladung_kwh", "wp_strom_kwh", "wp_waerme_kwh",
                "wp_modus_kuehlen_kwh", "emob_ladung_kwh", "emob_km"):
        return v is not None and v > 0
    if d.get("netzbezug_preis_effektiv_cent") is None:   # ohne Tarif kein Finanzblock
        return False
    if feld == "einspeise_erloes_euro":
        return (d.get("einspeisung_kwh") or 0) > 0 and v is not None
    if feld == "ev_ersparnis_euro":
        return (d.get("eigenverbrauch_kwh") or 0) > 0 and v is not None
    if feld in ("wp_ersparnis_euro", "emob_ersparnis_euro"):
        return bool(v)
    if feld in ("netzbezug_kosten_euro", "netzbezug_arbeitspreis_kosten_euro"):
        return v is not None
    return True  # übriger Finanzblock


async def _vergleiche_vorjahr_mit_monat(db, aid, jahr, monat) -> int:
    from backend.api.routes.aktueller_monat.vergleich import VORJAHR_FELDER, VORJAHR_QUELLFELD

    d = await get_aktueller_monat(anlage_id=aid, jahr=jahr, monat=monat, db=db)
    vj = d.vorjahr
    direkt = (await get_aktueller_monat(anlage_id=aid, jahr=jahr - 1, monat=monat, db=db)).model_dump()
    if vj is None:
        assert direkt["einspeisung_kwh"] is None, f"{jahr - 1}-{monat}: Vorjahr fehlt, obwohl der Monat Daten hat"
        return 0
    n = 0
    for feld in VORJAHR_FELDER:
        soll_da = _erwartete_anwesenheit(feld, direkt)
        assert (feld in vj) == soll_da, f"{jahr - 1}-{monat} {feld}: im Block {feld in vj}, erwartet {soll_da}"
        if not soll_da:
            continue
        erwartet = direkt.get(VORJAHR_QUELLFELD.get(feld, feld))
        if feld in ("gesamtverbrauch_kwh", "autarkie_prozent") and not (direkt.get("gesamtverbrauch_kwh") or 0) > 0:
            erwartet = None
        assert vj[feld] == erwartet, f"{jahr - 1}-{monat} {feld}: Vorjahr {vj[feld]!r} ≠ Monat {erwartet!r}"
        n += 1
    assert set(vj) <= set(VORJAHR_FELDER)
    return n


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", [_fixture_w3, _fixture_n605, _fixture_n607, _fixture_v2h],
                         ids=["W3", "N-605-zwei-WP", "N-607-Stundenpreise", "V2H-Speicher"])
async def test_vorjahr_block_ist_der_monat_selbst(db, fixture):
    """N-610: für jedes Feld des Vorjahres-Blocks gilt vorjahr.X == Monat(J−1).X — die Klasse, nicht der Einzelfall.
    Bis 03.10.2026 hatte das Vorjahr einen eigenen Pfad und wich je nach Achse ab (N-608 Preis, V2H, Rundung)."""
    aid, monate = await fixture(db)
    geprueft = 0
    for jahr, monat in monate:
        geprueft += await _vergleiche_vorjahr_mit_monat(db, aid, jahr, monat)
    assert geprueft > 0


async def _anlage_mit_nullen_und_negativer_wp(db) -> int:
    """PV, ein E-Auto mit 0 km und 0 kWh Ladung (eine gepflegte 0), eine Wärmepumpe, deren Strom teurer ist als die
    ersetzte Wärme (negative Ersparnis) — Juni 2024 und Juni 2025."""
    a = Anlage(anlagenname="Nullen", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    auto = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1), parameter={})
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0})
    db.add_all([pv, auto, wp])
    await db.flush()
    for jahr in (2024, 2025):
        db.add(Monatsdaten(anlage_id=a.id, jahr=jahr, monat=6, einspeisung_kwh=100.0, netzbezug_kwh=300.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=jahr, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 400.0}))
        db.add(InvestitionMonatsdaten(investition_id=auto.id, jahr=jahr, monat=6,
                                      verbrauch_daten={"km_gefahren": 0, "ladung_kwh": 0.0}))
        db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=jahr, monat=6, verbrauch_daten={
            "heizenergie_kwh": 100.0, "warmwasser_kwh": 0.0, "stromverbrauch_kwh": 250.0}))
    await db.commit()
    return a.id


@pytest.mark.asyncio
async def test_vorjahr_null_setzt_kein_feld_und_negative_ersparnis_steht(db):
    """Zwei Anwesenheitsregeln, die der Umbau tragen muss: eine gepflegte 0 setzt kein Feld im Block (die Kachel zeigt
    sonst ein Δ gegen „0"), eine NEGATIVE WP-Ersparnis steht darin (`if wp_ersparnis_vj:` war ≠ 0, nicht > 0)."""
    aid = await _anlage_mit_nullen_und_negativer_wp(db)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    vj = d.vorjahr
    assert "emob_km" not in vj and "emob_ladung_kwh" not in vj, vj
    assert vj["wp_ersparnis_euro"] < 0, vj.get("wp_ersparnis_euro")
    assert await _vergleiche_vorjahr_mit_monat(db, aid, 2025, 6) > 0


# ── Nacharbeit: Robustheit und `ohne_vorjahr` ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vorjahr_das_wirft_kippt_den_monat_nicht(db, monkeypatch):
    """Wirft die Berechnung des Vorjahresmonats, antwortet der Monat trotzdem: `vorjahr` None, ein Hinweis nennt es
    (der alte Pfad fing Finanz-Ausnahmen ab; der neue ruft eine ganze Monatsberechnung)."""
    import backend.api.routes.aktueller_monat as am

    aid = await anlage_mit_v2h(db)
    original = am._berechne_monat

    async def _vorjahr_wirft(anlage_id, jahr, monat, db_, **kw):
        if kw.get("ohne_vorjahr"):
            raise RuntimeError("Probe: Vorjahresmonat nicht berechenbar")
        return await original(anlage_id, jahr, monat, db_, **kw)

    monkeypatch.setattr(am, "_berechne_monat", _vorjahr_wirft)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    assert d.eigenverbrauch_kwh == pytest.approx(421.0)
    assert d.vorjahr is None
    assert "Vorjahresvergleich für 06/2024 nicht berechenbar." in d.hinweise


@pytest.mark.asyncio
async def test_der_vorjahresmonat_laedt_kein_eigenes_vorjahr(db, monkeypatch):
    """`ohne_vorjahr`: der von `_load_vorjahr` gerufene Monat lädt kein Vorjahr des Vorjahres (keine Rekursion,
    kein zweiter Monatslauf). Gezählt über die Aufrufe von `_load_vorjahr`."""
    import backend.api.routes.aktueller_monat as am

    aid = await anlage_mit_v2h(db)
    original = am._load_vorjahr
    aufrufe = []

    async def _gezaehlt(*a, **kw):
        aufrufe.append(a[2:4])
        return await original(*a, **kw)

    monkeypatch.setattr(am, "_load_vorjahr", _gezaehlt)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    assert d.vorjahr is not None
    assert aufrufe == [(2025, 6)], aufrufe


@pytest.mark.asyncio
async def test_die_monate_der_jahresroute_tragen_kein_vorjahr(db):
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr

    aid = await anlage_mit_v2h(db)
    j = await get_cockpit_jahr(anlage_id=aid, jahr=2025, db=db)
    assert j["monate"], "Fixture: das Jahr hat Monate"
    assert all(m.get("vorjahr") is None for m in j["monate"])
