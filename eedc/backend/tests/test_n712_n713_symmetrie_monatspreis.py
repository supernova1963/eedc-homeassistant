"""N-712 + N-713 — jede Sicht liest den Monatspreis aus den Monats-Fakten (eine Quelle, ADR-002/P8 + P10).

Gemessen am HEAD `98abc801` (acht Monate 07/2025–02/2026; E-Auto 1000 km, 90 kWh Netz-, 60 kWh PV-Ladung je Monat;
Wärmepumpe 1000 kWh Wärme, 300 kWh Strom je Monat; Gas 12 ct, Benzin 1,80 €). Werte in €:

| Fall | Größe | Cockpit (Monats-Fakten) | E-Auto-/WP-Hub | HA-Anlagensensoren (bisherige) | Aussichten (bisherige) |
| --- | --- | --- | --- | --- | --- |
| B allg 30 ab 09 + WP 22 ab 12 | WP | 418,64 | **466,67** | 418,67 | 418,67 |
| C allg 35 ab 09 + WP 22 ab 12 | E-Auto | 675,00 | **666,00** | **666,00** | 675,00 |
| C | WP | 373,64 | **421,67** | **343,67** | **343,67** |
| G allg 35 ab 09 + Wallbox 25 ab 12 | E-Auto | 702,00 | **711,00** | **693,00** | 702,00 |
| G | WP | 256,64 | 226,67 | 226,67 | 226,67 |
| K5a allg 30 ab 07, Monats-Ø 24 gepflegt, kein WP-Tarif | WP | 490,64 | **346,67** | **346,67** | **346,67** |

dazu der HA-Sensor je Wärmepumpe `wp_ersparnis_euro` in K5a **346,67** (N-713). N-712: Monate vor dem ersten Tarif
rechneten die Sichten mit dem HEUTIGEN Tarif (Hub: dem heutigen Komponenten-Tarif) statt mit der Vorbelegung 30 ct der
Monats-Fakten. N-713: ohne eigenen WP-Tarif nahmen sie den Stammpreis statt der N-663-Kaskade (gepflegt → gemessen →
Zeitfenster → Stamm). Soll: alle wie die Monats-Fakten.

Die Erwartungswerte sind von Hand gerechnet (Kommentar je Fall), nicht von einer Sicht abgeschrieben; das Cockpit rundet
die WP-Ersparnis je Gerätezeile auf Cent (N-609) und liegt bis zu 8 × 0,005 € daneben.

Erweitert im Bau (Päckchen I1, Entscheid Gernot 12.10.2026 «Kanon ist der Monatspreis der Monats-Fakten»): dazu der
HA-Sensor je E-Auto, Cockpit → Jahr (Σ Cockpit → Monat, am HEAD in allen vier Fällen daneben), der Monatspreis der
Schicht selbst (`tarif_des_monats` = `MonatsFakt.tarif`), die gewichteten Monatspreise der Hubs (Wallbox-, Sonstiges-,
E-Auto-Hub über `_gewichtete_monatspreise`) und Cockpit → Monat (vor dem ersten Tarif: Posten mit der Vorbelegung und
der Herkunft „vorbelegung"; mit gepflegtem Monats-Ø ohne WP-/Wallbox-Tarif: T-Konto und WP-Aggregat mit dem Ø).

Schwesterdateien: test_n693_ersatzpreis_vor_dem_ersten_tarif.py (derselbe Ersatzpreis im HA-Sensor je Investition),
test_n663_wp_preis_flex_monatsdurchschnitt.py (die WP-Kaskade in den Monats-Fakten), test_n459_wp_strom_voll_belastet.py
(dieselbe WP-Ersparnis in fünf Sichten).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
# Der WP-Hub fragt `sensor_snapshots` (Lebensdauer-Zähler); das Modell hängt nicht an `backend.models` — ohne diesen
# Import fehlt die Tabelle im Schema des ersten Tests eines Prozesses.
import backend.models.sensor_snapshot  # noqa: E402,F401

MONATE = [(2025, m) for m in range(7, 13)] + [(2026, 1), (2026, 2)]
WP_PARAM = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "waermebedarf_kwh": 12000.0, "jaz": 3.5,
            "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12.0, "alternativ_zusatzkosten_jahr": 0.0}

#: (Tarife, gepflegter Monats-Ø, E-Auto-Ersparnis, WP-Ersparnis) — von Hand:
#: E-Auto: Benzin 8000 km × 7,5 l/100 km × 1,80 € = 1080 €; Netz 90 kWh × Monatspreis; PV 60 kWh × Preis der
#:         Eigenverbrauchs-Ersparnis des Monats (Allgemeintarif bzw. 30 ct ohne Tarif bzw. der gepflegte Ø).
#: WP:     alte Heizung 8 × 1000 kWh ÷ 0,9 × 12 ct = 1066,67 €; WP 300 kWh × WP-Preis des Monats.
FAELLE = {
    # Netz 90 × 8 × 0,30 = 216; PV 480 × 0,30 = 144 ⇒ 720.   WP 300 × (5 × 0,30 + 3 × 0,22) = 648 ⇒ 418,67.
    "B": ([(30.0, date(2025, 9, 1), "allgemein"), (22.0, date(2025, 12, 1), "waermepumpe")], None, 720.00, 418.67),
    # Netz 90 × (2 × 0,30 + 6 × 0,35) = 243; PV 60 × 2,70 = 162 ⇒ 675.   WP 300 × (2 × 0,30 + 3 × 0,35 + 3 × 0,22) = 693.
    "C": ([(35.0, date(2025, 9, 1), "allgemein"), (22.0, date(2025, 12, 1), "waermepumpe")], None, 675.00, 373.67),
    # Netz 90 × (2 × 0,30 + 3 × 0,35 + 3 × 0,25) = 216; PV 162 ⇒ 702.   WP 300 × (2 × 0,30 + 6 × 0,35) = 810.
    "G": ([(35.0, date(2025, 9, 1), "allgemein"), (25.0, date(2025, 12, 1), "wallbox")], None, 702.00, 256.67),
    # Monats-Ø 24 schlägt den Tarif 30 (ganzer Zähler): Netz 720 × 0,24 = 172,8; PV 480 × 0,24 = 115,2 ⇒ 792.
    # WP ohne eigenen Tarif hängt am Hauszähler (N-663): 2400 × 0,24 = 576 ⇒ 490,67.
    "K5a": ([(30.0, date(2025, 7, 1), "allgemein")], 24.0, 792.00, 490.67),
}

#: Der Monatspreis der Schicht je Fall und Monat 07/2025 … 02/2026 (von Hand, ct/kWh): (Netzbezug, WP, Wallbox).
#: Vor dem ersten Tarif die Vorbelegung 30; ohne eigenen WP-/Wallbox-Tarif der Hauszähler (N-663/#412), mit
#: gepflegtem Monats-Ø der Ø.
MONATSPREISE = {
    "B": [(30.0, 30.0, 30.0)] * 5 + [(30.0, 22.0, 30.0)] * 3,
    "C": [(30.0, 30.0, 30.0)] * 2 + [(35.0, 35.0, 35.0)] * 3 + [(35.0, 22.0, 35.0)] * 3,
    "G": [(30.0, 30.0, 30.0)] * 2 + [(35.0, 35.0, 35.0)] * 3 + [(35.0, 35.0, 25.0)] * 3,
    "K5a": [(24.0, 24.0, 24.0)] * 8,
}


async def _anlage(db, tarife, monats_oe):
    a = Anlage(anlagenname="N712", leistung_kwp=10.0, installationsdatum=date(2025, 7, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    for preis, ab, verwendung in tarife:
        db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=preis, einspeiseverguetung_cent_kwh=8.0,
                          gueltig_ab=ab, verwendung=verwendung, anbieter="Werk", tarifname=f"{verwendung} {preis}"))
    for j, m in MONATE:
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=200.0, netzbezug_kwh=150.0,
                           kraftstoffpreis_euro=1.80, gaspreis_cent_kwh=12.0,
                           netzbezug_durchschnittspreis_cent=monats_oe))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=12000.0, leistung_kwp=10.0)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="EA", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=35000.0, anschaffungskosten_alternativ=30000.0, parameter={})
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=20000.0, anschaffungskosten_alternativ=8000.0, parameter=WP_PARAM)
    db.add_all([pv, ea, wp])
    await db.flush()
    for j, m in MONATE:
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=j, monat=m, verbrauch_daten={
            "km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0}))
        db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=j, monat=m, verbrauch_daten={
            "heizenergie_kwh": 800.0, "warmwasser_kwh": 200.0, "stromverbrauch_kwh": 300.0}))
    await db.commit()
    return a, ea, wp


def _ohne_netz(monkeypatch):
    """Prognose und Börsenpreis der Anlagen-Sensoren gestellt (wie `test_n693_…`) — sie brauchen das Netz."""
    from backend.api.routes.ha_export import anlage_sensorwerte

    async def _leer(*_a, **_k):
        return {}

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _leer)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _leer)


def _spion(monkeypatch, modul, name):
    """Fängt die Rückgabe einer Phase (`_out`-Dict) am echten Aufrufweg ab — die bisherigen Ersparnisse sind kein
    eigener Sensor bzw. kein eigenes Antwortfeld, sie gehen in ROI, Amortisation und den Fortschritt ein."""
    original = getattr(modul, name)
    gefangen: dict = {}

    def _sync(*a, **k):
        out = original(*a, **k)
        gefangen.update(out)
        return out

    async def _async(*a, **k):
        out = await original(*a, **k)
        gefangen.update(out)
        return out

    import inspect

    monkeypatch.setattr(modul, name, _async if inspect.iscoroutinefunction(original) else _sync)
    return gefangen


def _sensor(werte, key):
    sv = next((s for s in werte if s.definition.key == key), None)
    return None if sv is None else sv.value


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_jede_sicht_nennt_die_ersparnis_der_monats_fakten(db, monkeypatch, fall):
    from backend.api.routes.aussichten import finanzen as aussichten_finanzen
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import anlage_sensoren, calculate_investition_sensors
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
    from backend.api.routes.investitionen.dashboard_waermepumpe import get_waermepumpe_dashboard
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage

    tarife, monats_oe, ea_soll, wp_soll = FAELLE[fall]
    anlage, ea, wp = await _anlage(db, tarife, monats_oe)
    _ohne_netz(monkeypatch)
    ha_anlage = _spion(monkeypatch, anlage_sensoren, "alternativkosten_und_co2")
    aussichten = _spion(monkeypatch, aussichten_finanzen, "alternativkosten_rueckblick")

    cockpit = await get_cockpit_uebersicht(anlage.id, jahr=None, db=db)
    eauto_hub = (await get_eauto_dashboard(anlage.id, strompreis_cent=None, db=db))[0].zusammenfassung
    wp_hub = (await get_waermepumpe_dashboard(anlage.id, strompreis_cent=None, db=db))[0].zusammenfassung
    tarif = (await lade_tarife_fuer_anlage(db, anlage.id))["allgemein"]
    ha_wp = _sensor(await calculate_investition_sensors(db, wp, tarif), "wp_ersparnis_euro")
    ha_ea = _sensor(await calculate_investition_sensors(db, ea, tarif), "e_auto_ersparnis_vs_benzin_euro")
    await anlage_sensoren.calculate_anlage_sensors(db, anlage, skip_jitter=True)
    await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)

    # Cockpit → Jahr (die Jahresroute, Σ Cockpit → Monat) — Σ der beiden Kalenderjahre ist dieselbe Zahl.
    from backend.services.jahres_aggregat import baue_jahr

    koepfe = [(await baue_jahr(db, anlage.id, jahr))["kopf"] for jahr in (2025, 2026)]
    koepfe = [k if isinstance(k, dict) else k.model_dump() for k in koepfe]

    def _summe(feld):
        werte = [k.get(feld) for k in koepfe]
        return None if any(w is None for w in werte) else round(sum(werte), 2)

    ist = {
        "E-Auto Cockpit": cockpit.emob_ersparnis_euro,
        "E-Auto Cockpit Jahr": _summe("emob_ersparnis_euro"),
        "E-Auto-Hub": eauto_hub["ersparnis_vs_benzin_euro"],
        "E-Auto HA-Sensor": round(ha_ea, 2),
        "E-Auto HA-Anlage": round(ha_anlage["bisherige_eauto_ersparnis"], 2),
        "E-Auto Aussichten": round(aussichten["bisherige_eauto_ersparnis"], 2),
        "WP Cockpit": cockpit.wp_ersparnis_euro,
        "WP Cockpit Jahr": _summe("wp_ersparnis_euro"),
        "WP-Hub": wp_hub["ersparnis_euro"],
        "WP HA-Sensor": round(ha_wp, 2),
        "WP HA-Anlage": round(ha_anlage["bisherige_wp_ersparnis"], 2),
        "WP Aussichten": round(aussichten["bisherige_wp_ersparnis"], 2),
    }
    soll = {k: (ea_soll if k.startswith("E-Auto") else wp_soll) for k in ist}
    # N-609: das Cockpit rundet die WP-Ersparnis je Gerätezeile auf Cent — acht Monate, höchstens 8 × 0,005 €.
    toleranz = {k: (0.04 if k.startswith("WP Cockpit") else 0.005) for k in ist}
    abweichend = {
        k: (v, soll[k]) for k, v in ist.items() if v is None or v != pytest.approx(soll[k], abs=toleranz[k])
    }
    assert not abweichend, f"{fall}: Sicht (ist, von Hand) {abweichend}"

#: Speicher-Hub (N-712, gleiche Form): Ladung 100, Entladung 90 kWh je Monat, keine Netzladung, keine Stundenpreise;
#: Netzbezug 150 kWh je Monat (die Gewichte des Ø). Fall C: der Ø-Bezugspreis der Monats-Fakten ist
#: (2 × 30 + 6 × 35) ÷ 8 = 33,75 ct — am HEAD 35,00 ct (die Monate vor dem ersten Tarif mit dem heutigen Tarif).
@pytest.mark.asyncio
async def test_speicher_hub_bewertet_die_monate_vor_dem_ersten_tarif_wie_die_monats_fakten(db):
    from backend.api.routes.investitionen.dashboard_speicher import get_speicher_dashboard
    from backend.core.berechnungen.speicher_wirtschaftlichkeit import berechne_speicher_ersparnis

    anlage, _, _ = await _anlage(db, FAELLE["C"][0], None)
    sp = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="SP", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=8000.0, parameter={"kapazitaet_kwh": 10.0})
    db.add(sp)
    await db.flush()
    for j, m in MONATE:
        db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=j, monat=m,
                                      verbrauch_daten={"ladung_kwh": 100.0, "entladung_kwh": 90.0}))
    await db.commit()

    hub = (await get_speicher_dashboard(
        anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None, db=db,
    ))[0].zusammenfassung
    soll = berechne_speicher_ersparnis(
        entladung_kwh=720.0, bezug_preis_cent=33.75, einspeise_verg_cent=8.0,
        ladung_netz_kwh=0.0, wirkungsgrad_prozent=90.0, lade_preis_cent=None,
    ).ersparnis_euro
    assert hub["ersparnis_euro"] == pytest.approx(round(soll, 2), abs=0.005), (hub["ersparnis_euro"], soll)



@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_monatspreis_der_schicht_je_monat(db, fall):
    """Der Kanon selbst: `tarif_des_monats` und `tarife_der_monate` nennen je Monat den Preis von Hand, und die
    Monats-Fakten tragen genau dieses Objekt (`MonatsFakt.tarif`)."""
    from backend.services.monats_fakten import lade_monats_fakten, tarif_des_monats, tarife_der_monate

    anlage, _, _ = await _anlage(db, FAELLE[fall][0], FAELLE[fall][1])
    gesamt = await tarife_der_monate(db, anlage.id, MONATE)
    fakten = {(f.jahr, f.monat): f for f in await lade_monats_fakten(db, anlage.id)}
    for (j, m), (netz, wp_p, wb_p) in zip(MONATE, MONATSPREISE[fall]):
        einzeln = await tarif_des_monats(db, anlage.id, j, m, fakten[(j, m)].meta.monatsdaten)
        for quelle, t in (("einzeln", einzeln), ("gesamt", gesamt[(j, m)]), ("fakt", fakten[(j, m)].tarif)):
            ist = (t.netzbezug_preis_cent, t.wp_preis_cent, t.wallbox_preis_effektiv_cent)
            assert ist == (netz, wp_p, wb_p), (fall, (j, m), quelle, ist)


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_gewichtete_monatspreise_der_hubs_lesen_die_schicht(db, fall):
    """Wallbox-Hub (`wallbox`, gleichgewichtet), Sonstiges-Hub (`allgemein`) und E-Auto-Hub lesen ihre Monatspreise
    über `_gewichtete_monatspreise` — je Monat der Preis der Schicht, der Fallback (heutiger Tarif) nur ohne Gewichte."""
    from backend.api.routes.investitionen.dashboard_basis import _gewichtete_monatspreise

    anlage, _, _ = await _anlage(db, FAELLE[fall][0], FAELLE[fall][1])
    gewichte = {k: 1.0 for k in MONATE}
    for verwendung, spalte in (("wallbox", 2), ("allgemein", 0)):
        erg = await _gewichtete_monatspreise(
            db, anlage.id, verwendung, gewichte, fallback_bezug=99.0, fallback_einspeise=99.0,
        )
        soll = {k: p[spalte] for k, p in zip(MONATE, MONATSPREISE[fall])}
        assert erg.bezug_lookup == soll, (fall, verwendung, erg.bezug_lookup)
        assert erg.bezug_cent == pytest.approx(sum(soll.values()) / len(soll)), (fall, verwendung)


@pytest.mark.asyncio
async def test_cockpit_monat_vor_dem_ersten_tarif_rechnet_mit_der_vorbelegung(db, monkeypatch):
    """Fall C, 07/2025 (erster Tarif ab 09/2025): Cockpit → Monat nennt die Posten mit der Vorbelegung — wie die
    Monats-Fakten und Cockpit → Übersicht — und sagt es in der Herkunft des Preises (P4)."""
    from backend.api.routes import aktueller_monat as amr
    from backend.core.wirtschaftlichkeit_defaults import EINSPEISEVERGUETUNG_DEFAULT_CENT, NETZBEZUG_DEFAULT_CENT

    anlage, _, _ = await _anlage(db, FAELLE["C"][0], None)
    r = await amr.get_aktueller_monat(anlage_id=anlage.id, jahr=2025, monat=7, db=db)
    assert NETZBEZUG_DEFAULT_CENT == 30.0
    assert r.netzbezug_preis_effektiv_cent == 30.0
    assert r.netzbezug_preis_herkunft == "vorbelegung"
    # Die Preise der Antwort (Tarif-Zeile und Rechenweg im T-Konto) — die Vorbelegung, mit der gerechnet ist.
    assert (r.netzbezug_preis_cent, r.einspeise_preis_cent) == (30.0, EINSPEISEVERGUETUNG_DEFAULT_CENT)
    assert r.netzbezug_kosten_euro == pytest.approx(45.00)            # 150 kWh × 30 ct, kein Grundpreis
    assert r.einspeise_erloes_euro == pytest.approx(round(200 * EINSPEISEVERGUETUNG_DEFAULT_CENT / 100, 2))
    # E-Auto: 1000 km × 7,5 l × 1,80 € = 135 − Netz 90 × 0,30 − PV 60 × 0,30 = 90,00.
    assert r.emob_ersparnis_euro == pytest.approx(90.00)
    # WP: 1000 kWh ÷ 0,9 × 12 ct = 133,33 − 300 × 0,30 = 43,33.
    assert r.wp_ersparnis_euro == pytest.approx(43.33, abs=0.005)
    assert not [p for p in (r.fehlende_posten or []) if "Stromrechnung" in p], r.fehlende_posten
    assert r.ergebnis_euro is not None
    # Cockpit → Jahr 2025: zwei Monate mit Vorbelegung, vier mit Tarif — die Herkunft behauptet keinen Tarif für alle.
    from backend.services.jahres_aggregat import baue_jahr

    kopf = (await baue_jahr(db, anlage.id, 2025))["kopf"]
    kopf = kopf if isinstance(kopf, dict) else kopf.model_dump()
    assert kopf["netzbezug_preis_herkunft"] == "gemischt", kopf["netzbezug_preis_herkunft"]


@pytest.mark.asyncio
async def test_cockpit_monat_mit_monats_oe_ohne_wp_und_wallbox_tarif(db, monkeypatch):
    """K5a, 10/2025: T-Konto (WP- und E-Auto-Zeile) und das WP-Aggregat ohne Gerätezeile nehmen den gepflegten
    Monats-Ø (24 ct) — den Preis der Schicht —, nicht die Spalte des Allgemeintarifs (30 ct)."""
    from backend.api.routes import aktueller_monat as amr

    anlage, _, wp = await _anlage(db, FAELLE["K5a"][0], FAELLE["K5a"][1])
    # Der Zweig OHNE Gerätezeile (`waerme.py`, N-609) rechnet aus den Mengen der Quellen-Kaskade je Gerät; die Fixture
    # trägt keine (sie hat Gerätezeilen, und die gewinnen danach). Damit sein PREIS gemessen wird, bekommt er die
    # Mengen der WP dieses Monats (1000 kWh Wärme, 300 kWh Strom) — sonst nichts.
    from backend.api.routes.aktueller_monat.aggregation import _WP_STROM_K3_SUFFIX, _WP_WAERME_D1_SUFFIX

    _original = amr.waerme_klima_monat
    gefangen: dict = {}

    async def _mit_mengen(**k):
        k["resolved"] = {**(k.get("resolved") or {}),
                         f"inv_{wp.id}_{_WP_WAERME_D1_SUFFIX}": (1000.0, None),
                         f"inv_{wp.id}_{_WP_STROM_K3_SUFFIX}": (300.0, None)}
        out = await _original(**k)
        gefangen.update(out)
        return out

    monkeypatch.setattr(amr, "waerme_klima_monat", _mit_mengen)
    r = await amr.get_aktueller_monat(anlage_id=anlage.id, jahr=2025, monat=10, db=db)
    # WP: 133,33 − 300 × 0,24 = 61,33.   E-Auto: 135 − 90 × 0,24 − 60 × 0,24 = 99,00.
    ist = {
        "WP T-Konto": (r.wp_ersparnis_euro, r.wp_ersparnis_berechnung),
        "WP ohne Gerätezeile": (gefangen.get("wp_ersparnis"), gefangen.get("wp_ersparnis_berechnung_text")),
        "E-Auto T-Konto": (r.emob_ersparnis_euro, r.emob_ersparnis_berechnung),
    }
    soll = {"WP T-Konto": 61.33, "WP ohne Gerätezeile": 61.33, "E-Auto T-Konto": 99.00}
    abweichend = {k: v for k, v in ist.items() if v[0] is None or v[0] != pytest.approx(soll[k], abs=0.005)}
    assert not abweichend, abweichend
