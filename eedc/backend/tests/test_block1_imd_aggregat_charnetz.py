"""Block 1 — Charakterisierungs-Netz für die monatliche per-Typ-IMD-Aggregation.

Pinnt den IST-Stand der vier (real fünf, inkl. Vorjahr-Variante) Read-Sites,
die je eigenständig über `InvestitionMonatsdaten.verbrauch_daten` iterieren und
per `if inv.typ == "..."` Monats-Aggregate bilden — BEVOR die Logik in einen
gemeinsamen per-Zeilen-Resolver (`core/berechnungen/imd_monatsaggregat`) wandert.

Sites (siehe docs/drafts/BLOCK1-FELD-MATRIX-20260614.md):
  1  get_aktueller_monat            (aktueller_monat.py, aktueller Monat)
  1b get_aktueller_monat .vorjahr   (aktueller_monat.py, Vorjahr-Variante)
  2  list_monatsdaten_aggregiert    (monatsdaten.py, /aggregiert)
  3  get_komponenten_zeitreihe      (cockpit/komponenten.py)
  4  get_cockpit_uebersicht         (cockpit/uebersicht.py)

Die Fixture nutzt bewusst SAUBERE Pipeline-Daten (heizenergie_kwh/warmwasser_kwh,
KEIN waerme_kwh, KEIN Legacy-heizung_kwh, KEIN Dienstwagen) — so liefern alle
Sites deckungsgleiche Energie-Aggregate und das Netz bleibt durch das gesamte
Refactoring byte-identisch grün. Die bewussten Verhaltensänderungen D1 (WP-
Resolver-Vereinheitlichung) und D3 (Dienstwagen-Filter in Site 2) bekommen eigene
gezielte Regressionstests in den jeweiligen Fix-Commits.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


# ── Fixture: eine Multi-Komponenten-Anlage mit Stilllegungs-Fall ────────────

async def _seed(db) -> int:
    anlage = Anlage(anlagenname="Block1-Charnetz", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    # Monatsdaten-Zeilen (Basis-Zähler) für aktuellen Monat + Vorjahr
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=4,
                       einspeisung_kwh=400.0, netzbezug_kwh=300.0))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=4,
                       einspeisung_kwh=350.0, netzbezug_kwh=280.0))

    def inv(typ, parameter=None, stilllegung=None):
        i = Investition(
            anlage_id=anlage.id, typ=typ, bezeichnung=f"{typ}-test",
            anschaffungsdatum=date(2024, 1, 1), aktiv=True,
            parameter=parameter or {},
        )
        if stilllegung is not None:
            i.stilllegungsdatum = stilllegung
        return i

    pv = inv("pv-module")
    speicher = inv("speicher")
    speicher_alt = inv("speicher", stilllegung=date(2025, 12, 31))  # vor 2026/4 → exkludiert
    wp = inv("waermepumpe", parameter={"getrennte_strommessung": True})
    eauto = inv("e-auto")
    wallbox = inv("wallbox")
    bkw = inv("balkonkraftwerk")
    sonstiges = inv("sonstiges", parameter={"kategorie": "verbraucher"})
    db.add_all([pv, speicher, speicher_alt, wp, eauto, wallbox, bkw, sonstiges])
    await db.flush()

    def imd(i, jahr, monat, **felder):
        db.add(InvestitionMonatsdaten(
            investition_id=i.id, jahr=jahr, monat=monat, verbrauch_daten=felder))

    # ── aktueller Monat 2026/4 ──
    imd(pv, 2026, 4, pv_erzeugung_kwh=1000)
    imd(speicher, 2026, 4, ladung_kwh=500, entladung_kwh=450,
        ladung_netz_kwh=120, speicher_ladepreis_cent=25)
    imd(speicher_alt, 2026, 4, ladung_kwh=999, entladung_kwh=999)  # muss verschwinden
    imd(wp, 2026, 4, heizenergie_kwh=800, warmwasser_kwh=200,
        strom_heizen_kwh=250, strom_warmwasser_kwh=80)
    # E-Auto bewusst OHNE verbrauch_kwh: das Feld ist als ladung-Legacy-Fallback
    # in get_eauto_ladung_kwh überladen und würde den E-Mob-Pool/Netz-Split
    # verfälschen. Ø-Verbrauch-„gemessen"-Pfad ist in test_emob_readsite_symmetrie
    # abgedeckt.
    imd(eauto, 2026, 4, km_gefahren=1500, v2h_entladung_kwh=50)
    imd(wallbox, 2026, 4, ladung_kwh=400, ladung_pv_kwh=250, ladung_netz_kwh=150)
    imd(bkw, 2026, 4, pv_erzeugung_kwh=120, eigenverbrauch_kwh=90,
        speicher_ladung_kwh=30, speicher_entladung_kwh=25)
    imd(sonstiges, 2026, 4, verbrauch_sonstig_kwh=200)

    # ── Vorjahr 2025/4 (für aktueller_monat.vorjahr) ──
    imd(pv, 2025, 4, pv_erzeugung_kwh=900)
    imd(speicher, 2025, 4, ladung_kwh=400, entladung_kwh=360)
    imd(wp, 2025, 4, heizenergie_kwh=700, warmwasser_kwh=180,
        strom_heizen_kwh=220, strom_warmwasser_kwh=70)
    imd(eauto, 2025, 4, km_gefahren=1200)
    imd(wallbox, 2025, 4, ladung_kwh=350, ladung_pv_kwh=200, ladung_netz_kwh=150)

    await db.commit()
    return anlage.id


# ── Site 1: get_aktueller_monat (aktueller Monat) ───────────────────────────

async def test_charnetz_aktueller_monat(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    anlage_id = await _seed(db)
    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)

    # PV = PV-Modul + BKW
    assert am.pv_erzeugung_kwh == pytest.approx(1120.0)
    # Speicher (Alt-Speicher exkludiert)
    assert am.speicher_ladung_kwh == pytest.approx(500.0)
    assert am.speicher_entladung_kwh == pytest.approx(450.0)
    # WP (getrennte Strommessung)
    assert am.wp_strom_kwh == pytest.approx(330.0)
    assert am.wp_waerme_kwh == pytest.approx(1000.0)
    # E-Mob-Pool (Wallbox = Quelle, da Heimladung)
    assert am.emob_ladung_kwh == pytest.approx(400.0)
    assert am.emob_ladung_pv_kwh == pytest.approx(250.0)
    assert am.emob_ladung_netz_kwh == pytest.approx(150.0)
    assert am.emob_km == pytest.approx(1500.0)
    assert am.emob_v2h_kwh == pytest.approx(50.0)
    # Ohne gemessenen verbrauch_kwh → Ladungs-Näherung (400 kWh / 1500 km)
    assert am.emob_verbrauch_quelle == "ladung"
    assert am.emob_verbrauch_100km == pytest.approx(26.67, abs=0.1)
    # BKW
    assert am.bkw_erzeugung_kwh == pytest.approx(120.0)
    assert am.bkw_eigenverbrauch_kwh == pytest.approx(90.0)


# ── Site 1b: get_aktueller_monat .vorjahr ───────────────────────────────────

async def test_charnetz_aktueller_monat_vorjahr(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    anlage_id = await _seed(db)
    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)
    vj = am.vorjahr or {}

    assert vj.get("pv_erzeugung_kwh") == pytest.approx(900.0)
    assert vj.get("speicher_ladung_kwh") == pytest.approx(400.0)
    assert vj.get("speicher_entladung_kwh") == pytest.approx(360.0)
    assert vj.get("wp_strom_kwh") == pytest.approx(290.0)
    assert vj.get("wp_waerme_kwh") == pytest.approx(880.0)
    # E-Mob-Vorjahr: max(eauto_ladung=0, wb_ladung=350) = 350; km vom E-Auto
    assert vj.get("emob_ladung_kwh") == pytest.approx(350.0)
    assert vj.get("emob_km") == pytest.approx(1200.0)


# ── Site 2: list_monatsdaten_aggregiert ─────────────────────────────────────

async def test_charnetz_aggregiert(db):
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    anlage_id = await _seed(db)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    assert len(rows) == 1
    r = rows[0]

    assert r.pv_erzeugung_kwh == pytest.approx(1120.0)
    # QUIRK (IST-Stand, gepinnt): Site 2 addiert BKW-`speicher_*_kwh` in DENSELBEN
    # speicher_ladung/entladung-Akku wie der echte Speicher (monatsdaten.py:300-302)
    # → 500+30 / 450+25. Siehe BLOCK1-FELD-MATRIX D2. Bleibt durch das Refactoring
    # erhalten (verhaltensneutral), bis als separater Entscheid adressiert.
    assert r.speicher_ladung_kwh == pytest.approx(530.0)
    assert r.speicher_entladung_kwh == pytest.approx(475.0)
    assert r.wp_strom_kwh == pytest.approx(330.0)
    assert r.wp_strom_heizen_kwh == pytest.approx(250.0)
    assert r.wp_strom_warmwasser_kwh == pytest.approx(80.0)
    assert r.wp_heizung_kwh == pytest.approx(800.0)
    assert r.wp_warmwasser_kwh == pytest.approx(200.0)
    assert r.eauto_km == pytest.approx(1500.0)
    assert r.wallbox_ladung_kwh == pytest.approx(400.0)
    assert r.wallbox_ladung_pv_kwh == pytest.approx(250.0)


# ── Site 3: get_komponenten_zeitreihe ───────────────────────────────────────

async def test_charnetz_komponenten(db):
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    anlage_id = await _seed(db)
    resp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=2026, db=db)
    monate = [m for m in resp.monatswerte if (m.jahr, m.monat) == (2026, 4)]
    assert len(monate) == 1
    m = monate[0]

    assert m.speicher_ladung_kwh == pytest.approx(500.0)
    assert m.speicher_entladung_kwh == pytest.approx(450.0)
    assert m.speicher_arbitrage_kwh == pytest.approx(120.0)
    assert m.wp_strom_kwh == pytest.approx(330.0)
    assert m.wp_waerme_kwh == pytest.approx(1000.0)
    assert m.wp_heizung_kwh == pytest.approx(800.0)
    assert m.wp_warmwasser_kwh == pytest.approx(200.0)
    assert m.wp_strom_heizen_kwh == pytest.approx(250.0)
    assert m.wp_strom_warmwasser_kwh == pytest.approx(80.0)
    assert m.emob_km == pytest.approx(1500.0)
    assert m.emob_ladung_kwh == pytest.approx(400.0)
    assert m.emob_ladung_pv_kwh == pytest.approx(250.0)
    assert m.emob_ladung_netz_kwh == pytest.approx(150.0)
    assert m.emob_v2h_kwh == pytest.approx(50.0)
    assert m.bkw_erzeugung_kwh == pytest.approx(120.0)
    assert m.bkw_eigenverbrauch_kwh == pytest.approx(90.0)
    assert m.bkw_speicher_ladung_kwh == pytest.approx(30.0)
    assert m.bkw_speicher_entladung_kwh == pytest.approx(25.0)
    assert m.sonstiges_verbrauch_kwh == pytest.approx(200.0)
    assert resp.hat_arbitrage is True
    assert resp.hat_v2h is True


# ── Site 4: get_cockpit_uebersicht ──────────────────────────────────────────

async def test_charnetz_uebersicht(db):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    anlage_id = await _seed(db)
    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    assert ueb.speicher_ladung_kwh == pytest.approx(500.0)
    assert ueb.speicher_entladung_kwh == pytest.approx(450.0)
    assert ueb.wp_strom_kwh == pytest.approx(330.0)
    assert ueb.wp_waerme_kwh == pytest.approx(1000.0)
    assert ueb.wp_heizung_kwh == pytest.approx(800.0)
    assert ueb.wp_warmwasser_kwh == pytest.approx(200.0)
    assert ueb.emob_ladung_kwh == pytest.approx(400.0)
    assert ueb.emob_pv_anteil_prozent == pytest.approx(62.5, abs=0.1)
    assert ueb.emob_km == pytest.approx(1500.0)
    assert ueb.bkw_erzeugung_kwh == pytest.approx(120.0)
    assert ueb.bkw_eigenverbrauch_kwh == pytest.approx(90.0)
    assert ueb.sonstiges_verbrauch_kwh == pytest.approx(200.0)


# ── Pflicht-Symmetrie: gemeinsame Felder über die Read-Sites deckungsgleich ──

async def test_symmetrie_cross_site(db):
    """Aggregator-Symmetrie ([[feedback_aggregator_symmetrie]]): aktueller_monat,
    Komponenten und Übersicht liefern für DIESELBE Anlage deckungsgleiche
    per-Typ-Aggregate (Site-zu-Site verglichen, nicht gegen Konstanten) — bricht
    sofort, wenn eine Site erneut driftet. Dies ist der Drift-Lock für Block 1:
    ein statischer Layer-Wächter ist hier nicht sinnvoll (dieselben IMD-Felder
    lesen ~10 legitime Nicht-Block-1-Sites), der behaviorale Test fängt
    semantische Drift, nicht nur syntaktische.

    /aggregiert ist bewusst NICHT dabei: andere Form (Einzelmonat) + BKW-Speicher-
    Lump-Quirk in speicher_ladung — eigene Charakterisierung oben.
    """
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    anlage_id = await _seed(db)
    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)
    resp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=2026, db=db)
    k = next(m for m in resp.monatswerte if (m.jahr, m.monat) == (2026, 4))
    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    # Speicher
    assert am.speicher_ladung_kwh == k.speicher_ladung_kwh == ueb.speicher_ladung_kwh
    assert am.speicher_entladung_kwh == k.speicher_entladung_kwh == ueb.speicher_entladung_kwh
    # WP
    assert am.wp_strom_kwh == k.wp_strom_kwh == ueb.wp_strom_kwh
    assert am.wp_waerme_kwh == k.wp_waerme_kwh == ueb.wp_waerme_kwh
    # E-Mob (Pool)
    assert am.emob_ladung_kwh == k.emob_ladung_kwh == ueb.emob_ladung_kwh
    assert am.emob_km == k.emob_km == ueb.emob_km
    # BKW
    assert am.bkw_erzeugung_kwh == k.bkw_erzeugung_kwh == ueb.bkw_erzeugung_kwh
    assert am.bkw_eigenverbrauch_kwh == k.bkw_eigenverbrauch_kwh == ueb.bkw_eigenverbrauch_kwh
