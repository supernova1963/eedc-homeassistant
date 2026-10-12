"""N-736 (12.10.2026) — die Monats-Fakten tragen eine Netz-0 ohne Herkunft nicht mehr als Messwert in die Bilanz.

**Der Befund.** ``Monatsdaten.einspeisung_kwh``/``netzbezug_kwh`` sind ``NOT NULL`` mit Default 0. Legt ein Import die Zeile
ohne Netzfelder an (Fall G: Portal-Import nur mit Wallbox-Daten ⇒ ``0.0 / 0.0``, ``source_provenance = {}``), trug
``ZaehlerFakten`` diese 0, und jede Sicht über die Fakten rechnete daraus Eigenverbrauch = PV und Autarkie 100 %: gemessen
(Probe ``MESSUNG-F2-FAKTEN-DEFAULT0.md``, Variante «G+IMD»: die PV 1200 kWh steht als Modul-Zeile in der DB) Übersicht
EV 1200 / 100 %, HA-Sensor 100 %, Community-Upload 100 % / 1200 kWh / 456 kg CO₂, Jahresbericht-Zeile 1200 / 100 %,
Nachhaltigkeit 456 kg / 100 %, Tabelle 1200 / 100 % / 360 €, Aussichten → Finanzen 10 090 kWh/Jahr bei 100 %. *Cockpit →
Monat* behandelt dasselbe Feld seit N-734 als „nicht erfasst" und nimmt es aus der HA-Statistik (250 / 700 / 66,7 %).

**Die Regel** (Entscheid Master 12.10.2026, Option 2 + a + b): ``MetaFakten.netzbezug_erfasst``/``einspeisung_erfasst``/
``netz_erfasst`` aus ``roh.netzfeld_ist_erfasst`` (``bau._zaehler_fakten``); (b) ein nicht erfasstes Feld füllt die
Tagesebene, wo sie es erfasst; (a) die Bilanz-Grundmenge (Muster N-659) ist ``hat_zaehlerzeile and netz_erfasst and
erzeuger_aktiv`` — der Monat fällt aus Eigenverbrauch, Autarkie, Ersparnis, USt und CO₂ wie ein Monat ohne Zählerzeile,
seine PV bleibt in der Anzeige. Tabelle und Jahresbericht-Zeile zeigen die Netz-, Bilanz- und Geldfelder als ``None``.

**Erwartete Werte, vorher festgelegt.** G+IMD: Übersicht/HA-Sensor/Jahresbericht-KPI ``pv 1200 · ev 0 · autarkie 0`` (die
Bilanz-Grundmenge ist leer — dieselbe Zahl wie für eine Anlage, deren einziger Monat keine Zählerzeile hat); Community
``[]``; Jahresbericht-Zeile und Tabelle ``pv 1200``, Netz/EV/Autarkie ``None``; Nachhaltigkeit ``co2_pv 0 · autarkie None``;
Aussichten ``jahres_eigenverbrauch 3027 · quote 30 %`` (die Standard-Prognose ohne Historie, wie für G). Cockpit → Monat/Jahr
unverändert 250 / 700 / 66,7 %. Gegenfälle: dieselbe Anlage mit **eingetragener** Einspeisung 0 und Netzbezug 300 (Formular,
``manual:form``) ⇒ überall EV 1200, Einspeisung 0, Autarkie 80 % (Bestandsschutz Balkonkraftwerk ohne Einspeisung); mit
``legacy:unknown`` (Etappe-3d-Migration) dieselben Zahlen.

Uhr-Unabhängigkeit: alle Daten liegen in 2025 (abgeschlossen), kein ``date.today()`` in den Erwartungen.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.monats_fakten import TAGESWERT_ZAEHLER, lade_monats_fakten
from backend.tests import factories

J, M = 2025, 7
HA = {"pv_erzeugung_kwh": 1200.0, "netzbezug_kwh": 250.0, "einspeisung_kwh": 700.0}


async def _anlage(db) -> Anlage:
    a = await factories.anlage(db)
    await factories.strompreis(db, a.id, date(2024, 1, 1),
                               netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0)
    await factories.investition(db, a.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    await factories.investition(db, a.id, "wallbox", bezeichnung="WB")
    await db.commit()
    return a


async def _pv_als_modulzeile(db, aid: int) -> None:
    inv = (await db.execute(
        select(Investition).where(Investition.anlage_id == aid, Investition.typ == "pv-module")
    )).scalar_one()
    await factories.imd(db, inv.id, J, M, {"pv_erzeugung_kwh": 1200.0})
    await db.commit()


async def _fall_g(db, *, mit_pv_zeile: bool) -> Anlage:
    """Fall G: der Portal-Import legt die Zeile NUR mit der Wallbox an ⇒ Netzfelder 0,0 ohne Herkunftseintrag."""
    a = await _anlage(db)
    r = await apply_import(
        anlage_id=a.id, data=ApplyRequest(monate=[ApplyMonthInput(jahr=J, monat=M, wallbox_ladung_kwh=150.0)]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )
    assert r.erfolg, r.fehler
    await db.commit()
    if mit_pv_zeile:
        await _pv_als_modulzeile(db, a.id)
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalar_one()
    # Vorbedingung des Falls — sonst prüfte dieser Test nichts.
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (0.0, 0.0)
    assert not {"einspeisung_kwh", "netzbezug_kwh"} & set(md.source_provenance or {})
    return a


async def _fall_erfasst(db, quelle: str) -> Anlage:
    """Gegenfall: Einspeisung 0 und Netzbezug 300 sind GELIEFERT (Herkunftseintrag) — die 0 ist ein Wert."""
    from backend.services.provenance import seed_provenance

    a = await _anlage(db)
    md = Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=0.0, netzbezug_kwh=300.0)
    seed_provenance(md, source=quelle, writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    db.add(md)
    await db.commit()
    await _pv_als_modulzeile(db, a.id)
    return a


def _ha_statistik(monkeypatch) -> None:
    import backend.api.routes.aktueller_monat as am

    async def _leer(*_a, **_k):
        return {}

    async def _ha(anlage, j, m):  # noqa: ARG001
        return {k: (v, am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92)) for k, v in HA.items()}

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)


# ─── die Sichten einzeln (je eine Zahl, die sie bisher falsch nannten) ─────────────────────────────────────────────────

async def _uebersicht(db, aid):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    return (await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)).model_dump()


async def _ha_sensoren(db, aid) -> dict:
    from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == aid)
    )).scalar_one()
    return {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True)}


async def _community(db, aid) -> list[dict]:
    from backend.services.community_service import prepare_community_data

    return (await prepare_community_data(db, aid))["monatswerte"]


async def _jahresbericht(db, aid) -> tuple[dict, dict]:
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    ctx = await build_jahresbericht_context(db, aid, J)
    return next(z for z in ctx["monats_zeilen"] if z["monat"] == M), ctx["kpis"]


async def _nachhaltigkeit(db, aid):
    from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit

    nh = await get_nachhaltigkeit(aid, db)
    return next(m for m in nh.monatswerte if (m.jahr, m.monat) == (J, M)), nh


async def _tabelle(db, aid) -> dict:
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    return next(z.model_dump() for z in await list_monatsdaten_aggregiert(aid, jahr=J, db=db) if z.monat == M)


async def _finanzen(db, aid) -> dict:
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose

    return (await get_finanz_prognose(aid, monate=12, db=db)).model_dump()


# ─── Fall G+IMD: der Monat fällt aus der Bilanz, die PV bleibt ─────────────────────────────────────────────────────────

async def test_uebersicht_und_ha_sensor_ohne_den_monat(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    ue = await _uebersicht(db, a.id)
    assert ue["pv_erzeugung_kwh"] == pytest.approx(1200.0)          # die PV bleibt in der Anzeige
    assert ue["eigenverbrauch_kwh"] == pytest.approx(0.0)           # vorher 1200
    assert ue["autarkie_prozent"] == pytest.approx(0.0)             # vorher 100,0
    assert ue["ev_ersparnis_euro"] == pytest.approx(0.0)            # vorher 360,00 €
    s = await _ha_sensoren(db, a.id)
    assert s["pv_erzeugung_gesamt_kwh"] == pytest.approx(1200.0)
    assert s["eigenverbrauch_gesamt_kwh"] == pytest.approx(0.0)     # vorher 1200
    assert s["autarkie_prozent"] == pytest.approx(0.0)              # vorher 100,0
    assert s["eigenverbrauch_quote_prozent"] == pytest.approx(0.0)  # vorher 100,0


async def test_community_teilt_den_monat_nicht(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    assert await _community(db, a.id) == []                         # vorher Autarkie 100 %, EV 1200, CO₂ 456 kg


async def test_jahresbericht_zeile_leer_und_kpis_ohne_den_monat(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    zeile, kpis = await _jahresbericht(db, a.id)
    assert zeile["pv_erzeugung_kwh"] == pytest.approx(1200.0)
    assert {k: zeile[k] for k in ("eigenverbrauch_kwh", "einspeisung_kwh", "netzbezug_kwh", "autarkie_prozent",
                                  "einsp_erloes_euro", "ev_ersparnis_euro", "netto_ertrag_euro")} == dict.fromkeys(
        ("eigenverbrauch_kwh", "einspeisung_kwh", "netzbezug_kwh", "autarkie_prozent",
         "einsp_erloes_euro", "ev_ersparnis_euro", "netto_ertrag_euro"))
    assert kpis["pv_erzeugung_kwh"] == pytest.approx(1200.0)
    assert kpis["eigenverbrauch_kwh"] == pytest.approx(0.0)         # vorher 1200
    assert kpis["autarkie_prozent"] == pytest.approx(0.0)           # vorher 100,0


async def test_nachhaltigkeit_ohne_pv_co2_und_ohne_autarkie(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    monat, nh = await _nachhaltigkeit(db, a.id)
    assert monat.co2_pv_kg == pytest.approx(0.0)                    # vorher 456,0 (= 1200 × 0,38)
    assert monat.autarkie_prozent is None                           # vorher 100,0
    assert nh.autarkie_durchschnitt_prozent == pytest.approx(0.0)   # der Monat zählt nicht in den Ø


async def test_tabelle_zeile_bleibt_mit_leeren_netz_und_geldfeldern(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    z = await _tabelle(db, a.id)
    assert z["id"] is not None                                      # die Zeile bleibt (Datensatz zum Öffnen)
    assert z["pv_erzeugung_kwh"] == pytest.approx(1200.0)
    for feld in ("einspeisung_kwh", "netzbezug_kwh", "eigenverbrauch_kwh", "gesamtverbrauch_kwh", "autarkie_prozent",
                 "eigenverbrauchsquote_prozent", "ev_ersparnis_euro", "einspeise_erloes_euro", "netzbezug_kosten_euro",
                 "netto_ertrag_euro"):
        assert z[feld] is None, feld                                # vorher EV 1200, Autarkie 100, 360 €
    assert z["wallbox_ladung_kwh"] == pytest.approx(150.0)          # die übrigen Felder bleiben


async def test_finanz_prognose_schreibt_keine_100_prozent_fort(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    fp = await _finanzen(db, a.id)
    assert fp["eigenverbrauchsquote_prozent"] != pytest.approx(100.0)
    assert fp["jahres_eigenverbrauch_kwh"] == pytest.approx(3027.0)  # vorher 10 090 (Standard-Prognose ohne Historie)
    assert fp["bisherige_ertraege_euro"] == pytest.approx(0.0)       # vorher 360,00 €


async def test_cockpit_monat_und_jahr_unveraendert(db, monkeypatch):
    """Cockpit → Monat/Jahr lesen die Monatsroute (HA-Statistik) — N-736 berührt sie nicht."""
    import backend.api.routes.aktueller_monat as am
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr

    a = await _fall_g(db, mit_pv_zeile=True)
    _ha_statistik(monkeypatch)
    d = (await am.get_aktueller_monat(anlage_id=a.id, jahr=J, monat=M, db=db)).model_dump()
    assert (d["netzbezug_kwh"], d["einspeisung_kwh"], d["eigenverbrauch_kwh"]) == (250.0, 700.0, 500.0)
    assert d["autarkie_prozent"] == pytest.approx(66.7, abs=0.05)
    juli = next(m for m in (await get_cockpit_jahr(anlage_id=a.id, jahr=J, db=db))["monate"] if m["monat"] == M)
    assert (juli["netzbezug_kwh"], juli["einspeisung_kwh"]) == (250.0, 700.0)
    assert juli["autarkie_prozent"] == pytest.approx(66.7, abs=0.05)


async def test_fall_g_ohne_pv_zeile_bleibt_bei_null(db):
    """Fall G ohne Modul-Zeile: die Fakten sehen keine PV — es bleibt bei 0 (keine falsche Zahl, wie vorher)."""
    a = await _fall_g(db, mit_pv_zeile=False)
    ue = await _uebersicht(db, a.id)
    assert (ue["pv_erzeugung_kwh"], ue["eigenverbrauch_kwh"], ue["autarkie_prozent"]) == (0.0, 0.0, 0.0)
    assert await _community(db, a.id) == []
    z = await _tabelle(db, a.id)
    assert z["eigenverbrauch_kwh"] is None and z["autarkie_prozent"] is None


async def test_fakt_traegt_die_flags(db):
    a = await _fall_g(db, mit_pv_zeile=True)
    f = next(f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (J, M))
    assert f.meta.hat_zaehlerzeile is True
    assert (f.meta.einspeisung_erfasst, f.meta.netzbezug_erfasst, f.meta.netz_erfasst) == (False, False, False)
    assert (f.zaehler.einspeisung_kwh, f.zaehler.netzbezug_kwh) == (0.0, 0.0)   # ZaehlerFakten bleibt float


# ─── Gegenfälle: eine gelieferte 0 bleibt eine 0 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quelle", ["manual:form", "legacy:unknown"])
async def test_erfasste_null_bleibt_ueberall_eine_null(db, quelle):
    """Bestandsschutz (Balkonkraftwerk ohne Einspeisung): Einspeisung 0 MIT Herkunftseintrag — formular- oder
    migrationsgestempelt — ist ein Messwert. PV 1200, Einspeisung 0, Netzbezug 300 ⇒ EV 1200, Autarkie 80 %."""
    a = await _fall_erfasst(db, quelle)
    ue = await _uebersicht(db, a.id)
    assert (ue["einspeisung_kwh"], ue["netzbezug_kwh"]) == (0.0, 300.0)
    assert ue["eigenverbrauch_kwh"] == pytest.approx(1200.0)
    assert ue["autarkie_prozent"] == pytest.approx(80.0)
    s = await _ha_sensoren(db, a.id)
    assert s["autarkie_prozent"] == pytest.approx(80.0)
    mw = await _community(db, a.id)
    assert [(w["einspeisung_kwh"], w["netzbezug_kwh"], w["autarkie_prozent"]) for w in mw] == [(0.0, 300.0, 80.0)]
    zeile, kpis = await _jahresbericht(db, a.id)
    assert (zeile["einspeisung_kwh"], zeile["eigenverbrauch_kwh"]) == (0.0, 1200.0)
    assert zeile["autarkie_prozent"] == pytest.approx(80.0)
    assert kpis["autarkie_prozent"] == pytest.approx(80.0)
    monat, _ = await _nachhaltigkeit(db, a.id)
    assert monat.autarkie_prozent == pytest.approx(80.0)
    assert monat.co2_pv_kg == pytest.approx(456.0)                  # 1200 × 0,38 — hier ist der EV gemessen
    z = await _tabelle(db, a.id)
    assert (z["einspeisung_kwh"], z["netzbezug_kwh"], z["eigenverbrauch_kwh"]) == (0.0, 300.0, 1200.0)
    assert z["autarkie_prozent"] == pytest.approx(80.0)


# ─── (b): die Tagesebene füllt nur das nicht erfasste Feld ─────────────────────────────────────────────────────────────

async def _fall_b(db) -> Anlage:
    """Einspeisung 700 eingetragen, Netzbezug NICHT erfasst (0 ohne Eintrag); die Tagesebene misst 250 kWh Netzbezug.
    Dazu ein Speicher mit Zeile und eine Wallbox-Ladung ohne PV-Anteil: die Schicht lädt die Tagesebene dann nur für den
    Ladeanteil — die Stunden für diesen Monat nur, weil sein Netzfeld nicht erfasst ist (``laden.py``, N-736)."""
    from backend.services.provenance import seed_provenance

    a = await _anlage(db)
    speicher = await factories.investition(db, a.id, "speicher", bezeichnung="Akku")
    wallbox = (await db.execute(
        select(Investition).where(Investition.anlage_id == a.id, Investition.typ == "wallbox")
    )).scalar_one()
    md = Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=700.0, netzbezug_kwh=0.0)
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh"])
    db.add(md)
    db.add(InvestitionMonatsdaten(investition_id=speicher.id, jahr=J, monat=M,
                                  verbrauch_daten={"ladung_kwh": 10.0, "entladung_kwh": 9.0}))
    db.add(InvestitionMonatsdaten(investition_id=wallbox.id, jahr=J, monat=M,
                                  verbrauch_daten={"ladung_kwh": 150.0}))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(J, M, 1), komponenten_kwh={}))
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=date(J, M, 1), stunde=12, pv_kw=0.0, verbrauch_kw=0.0,
                              einspeisung_kw=5.0, netzbezug_kw=250.0))
    await db.commit()
    await _pv_als_modulzeile(db, a.id)
    return a


async def test_tagesebene_fuellt_nur_das_nicht_erfasste_feld(db):
    a = await _fall_b(db)
    f = next(f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (J, M))
    assert f.zaehler.netzbezug_kwh == pytest.approx(250.0)          # aus der Tagesebene
    assert f.zaehler.einspeisung_kwh == pytest.approx(700.0)        # eingetragen — die Tagesebene (5) überschreibt nicht
    assert (f.meta.einspeisung_erfasst, f.meta.netzbezug_erfasst, f.meta.netz_erfasst) == (True, True, True)
    assert TAGESWERT_ZAEHLER in f.meta.tageswert_gruppen
    ue = await _uebersicht(db, a.id)
    assert (ue["einspeisung_kwh"], ue["netzbezug_kwh"]) == (700.0, 250.0)   # der Monat ist in der Bilanz


async def test_ohne_tageswert_des_feldes_bleibt_es_nicht_erfasst(db):
    """Die Tagesebene ist geladen, trägt aber keinen Netzbezug (keine Stundenzeile) ⇒ das Feld bleibt nicht erfasst."""
    from backend.services.provenance import seed_provenance

    a = await _anlage(db)
    md = Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=700.0, netzbezug_kwh=0.0)
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh"])
    db.add(md)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(J, M, 1), komponenten_kwh={"pv_1": 40.0}))
    await db.commit()
    await _pv_als_modulzeile(db, a.id)
    f = next(f for f in await lade_monats_fakten(db, a.id, inkl_nur_tageswerte=True) if f.schluessel == (J, M))
    assert (f.meta.einspeisung_erfasst, f.meta.netzbezug_erfasst, f.meta.netz_erfasst) == (True, False, False)
    assert TAGESWERT_ZAEHLER not in f.meta.tageswert_gruppen


# ─── Checker-Text sagt, was die Sichten jetzt tun ──────────────────────────────────────────────────────────────────────

async def test_checker_nennt_den_monat_als_aus_der_bilanz_genommen(db):
    from backend.services.daten_checker import DatenChecker

    a = await _fall_g(db, mit_pv_zeile=True)
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == a.id)
    )).scalar_one()
    mds = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalars().all())
    ergebnisse = await DatenChecker(db)._check_monatsdaten_plausibilitaet(anlage, mds)
    netz = next(e for e in ergebnisse if e.meldung.endswith("Netzbezug nicht erfasst"))
    assert "lassen den Monat bis dahin aus Eigenverbrauch, Autarkie, Ersparnis und CO₂ heraus" in netz.details
    assert "der Community-Upload teilt ihn nicht" in netz.details
    assert "rechnen bis dahin mit 0" not in netz.details


# ─── Klassen-Stellen ohne eigene Sicht (Einwertung Master 12.10.2026, Punkt 6) ─────────────────────────────────────────

async def test_ust_grundlage_ohne_den_monat(db):
    """``ust_satz.py:71`` (``grundgesamtheit``): der Monat mit nicht erfasstem Netzfeld zählt nicht in die USt-Grundlage.

    Dieselbe Fixture G+IMD, dazu Regelbesteuerung (19 %) und 12 000 € Anschaffung des Moduls. Vorher (Sprengsatz S14):
    Grundgesamtheit 1 Monat mit EV 1200 kWh, Satz 0,00792 €/kWh, USt des Zeitraums **9,50 €** — eine USt auf 1200 kWh,
    die niemand gemessen hat. Nachher: kein Monat, der Satz des Jahres ist nicht ermittelbar (``euro_je_kwh None``), die
    USt des Zeitraums 0,00 €."""
    from backend.services.ust_satz import grundgesamtheit, ust_eigenverbrauch_zeitraum, ust_jahresanteil, ust_satz_des_jahres

    a = await _fall_g(db, mit_pv_zeile=True)
    a.steuerliche_behandlung = "regelbesteuerung"
    a.ust_satz_prozent = 19.0
    invs = list((await db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars().all())
    next(i for i in invs if i.typ == "pv-module").anschaffungskosten_gesamt = 12000.0
    await db.commit()
    fakten = await lade_monats_fakten(db, a.id)
    assert grundgesamtheit(fakten, J) == []
    anteil = ust_jahresanteil(fakten, J)
    assert (anteil.monate, anteil.eigenverbrauch_kwh) == (0, 0.0)
    satz = ust_satz_des_jahres(a, invs, fakten, J)
    assert satz is not None and satz.euro_je_kwh is None
    assert ust_eigenverbrauch_zeitraum(a, invs, fakten) == pytest.approx(0.0)


async def test_bkw_anteil_im_monat_nicht_bewertbar(db):
    """``monats_fakten/ableitungen.py:342`` (``bkw_beitrag_im_monat``) leitet den Anteil EINES Balkonkraftwerks am
    Eigenverbrauch der Anlage ab (BKW-Hub, ROI-Zeile, T-Konto von Cockpit → Monat). Fixture G+IMD plus ein BKW mit 120 kWh.
    Vorher (Sprengsatz S15): ``anteilig`` 120 kWh — 120/1320 der Erzeugung hinter dem Zähler × EV 1320 (= PV, weil die
    Einspeisung 0 ohne Herkunft galt). Nachher: ``nicht_bewertbar``, 0 kWh — wie ein Monat ohne Zählerzeile."""
    from backend.services.monats_fakten import bkw_beitrag_im_monat

    a = await _fall_g(db, mit_pv_zeile=True)
    bkw = await factories.investition(db, a.id, "balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8)
    await factories.imd(db, bkw.id, J, M, {"pv_erzeugung_kwh": 120.0})
    await db.commit()
    f = next(f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (J, M))
    assert f.erzeugung.hinter_zaehler_kwh == pytest.approx(1320.0)
    b = bkw_beitrag_im_monat(bkw.id, f, zeile_erzeugung_kwh=120.0, zeile_eigenverbrauch_kwh=0.0, abgetreten=False)
    assert (b.anteil.quelle, b.anteil.bewertbar, b.anteil.kwh) == ("nicht_bewertbar", False, 0.0)
    assert (b.anteil_bewertet.quelle, b.anteil_bewertet.kwh) == ("nicht_bewertbar", 0.0)


async def test_komponenten_hub_netzkosten_ohne_den_monat(db):
    """``cockpit/komponenten.py:273``: Netzbezugskosten und Einspeise-Erlös je Monat nur mit erfassten Netzfeldern.
    Fixture G+IMD, Tarif mit 12 € Grundpreis. Vorher (Sprengsatz S16): Netzbezugskosten 12,00 € (0 kWh × 30 ct + Grundpreis)
    — eine Stromrechnung aus einem Netzbezug, den niemand gemessen hat. Nachher: der Sonst-Zweig wie ohne Zeile, 0,00 €
    (bewusst so belassen, Einwertung Master Punkt 4: kein „–" im Hub)."""
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.models.strompreis import Strompreis

    a = await _fall_g(db, mit_pv_zeile=True)
    sp = (await db.execute(select(Strompreis).where(Strompreis.anlage_id == a.id))).scalar_one()
    sp.grundpreis_euro_monat = 12.0
    await db.commit()
    zr = await get_komponenten_zeitreihe(anlage_id=a.id, jahr=J, db=db)
    juli = next(m for m in zr.monatswerte if (m.jahr, m.monat) == (J, M))
    assert juli.netzbezug_kosten_euro == pytest.approx(0.0)
    assert juli.einspeise_erloes_euro == pytest.approx(0.0)
