"""RF-43 … RF-46 (4.11.2026): benannte Proben für die Zweige des ROI-Dashboards, die vor dem Phasen-Schnitt keine
ROI-Testdatei betrat (Zeilen- und Bogenspur `refactoring-werkzeug/rf43/`, Bauform RF-1: erst die Probe, dann der Schnitt).
Alle Fälle sind am HEAD vor dem Schnitt (`46b9aa9ad`) grün und beschreiben das Verhalten von dort.

Schwesterdateien: `test_roi_bkw_hierarchie_381.py` (F-33-Systemkopf, hier die Variante BKW nur mit Speicher-Kind),
`test_roi_summe_symmetrie_f37.py` (F-37-Kürzung des PV-Topfs), `test_roi_dashboard_benzinpreis.py` (Rangfolge des
Benzinpreises), `test_emob_pv_anteil_sichten_symmetrie.py` (N-188 IST-PV-Anteil), `test_roi_amortisation_jahr.py`
(Kalender-Treppe N-525). Gate des Schnitts zusammen mit dem Golden Master `skript-golden-master-investitionen.py`.

Je Phase (Funktionsname nach dem Schnitt):
* `pv_systeme_zeilen` — BKW-Kopf mit eigenem Beitrag (F-33), Modul ohne Nennleistung, DC-Speicher ohne Kapazität,
  DC-Speicher im IST-Modus mit dünner Ladepreis-Datenbasis.
* `standalone_zeilen` — AC-Speicher im IST-Modus mit dünner Datenbasis, BKW ohne Leistungsangabe (800 Wp).
* `get_roi_dashboard` — Anlage ohne ein einziges Anschaffungsdatum (Treppe als Index, kein Break-Even-Jahr).
* `lade_roi_eingaenge` — unbekannte Anlage (404), Anlage ohne Investitionen, IST-PV-Anteil höchstens einmal je Request,
  WP-/Wallbox-Tarif neben dem allgemeinen, gepflegte Einspeisevergütung **0** (`is not None`), anlagenweite Ausgabe als
  Kapital-Ereignis im Jahr ihres Monats (nachgerüstet nach der Gegenprobe: der Sprengsatz «anlagenweite Kapital-
  Ereignisse weg» war in den ROI-Tests und im Golden Master still).
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.api.routes.investitionen import roi_eingaenge, roi_pv
from backend.api.routes.investitionen.roi import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.services.speicher_wirtschaftlichkeit import EffektiverLadepreisErgebnis

J = 2026


async def _roi(db, anlage_id, *, strompreis_cent=30.0, einspeiseverguetung_cent=8.0, jahr=J):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=strompreis_cent, einspeiseverguetung_cent=einspeiseverguetung_cent,
        benzinpreis_euro=None, jahr=jahr, db=db,
    )


async def _anlage(db, name="RF-43", *, monatsdaten=True):
    a = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    if monatsdaten:
        db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=5, netzbezug_kwh=100.0, einspeisung_kwh=50.0))
    return a


def _inv(a, typ, bez, **kw):
    kw.setdefault("anschaffungsdatum", date(2025, 1, 1))
    return Investition(anlage_id=a.id, typ=typ, bezeichnung=bez, **kw)


def _zeile(result, inv_id):
    return next(b for b in result.berechnungen if b.investition_id == inv_id)


def _komponente(zeile, inv_id):
    return next(k for k in (zeile.komponenten or []) if k.investition_id == inv_id)


def _duenn():
    """Ladepreis-Ergebnis «Datenbasis zu dünn»: 5 von 20 Netzlade-Stunden mit Preis ⇒ 25 % Abdeckung."""
    return EffektiverLadepreisErgebnis(
        quelle="datenbasis-zu-duenn", effektiver_ladepreis_cent=21.0, netz_lade_kwh=31.6,
        netzlade_stunden_mit_preis=5, netzlade_stunden_gesamt=20, stunden_gesamt_im_fenster=720,
    )


async def _speicher_ist_monate(db, sp_id):
    """Drei Monate mit Entladung — `aggregiere_speicher_ist` liefert ab drei Monaten ein Aggregat (IST-Modus)."""
    for monat in (2, 3, 4):
        db.add(InvestitionMonatsdaten(investition_id=sp_id, jahr=J, monat=monat, verbrauch_daten={
            "ladung_kwh": 120.0, "entladung_kwh": 110.0, "ladung_netz_kwh": 20.0,
        }))
    await db.flush()


# ============================================================================
# pv_systeme_zeilen
# ============================================================================


async def test_bkw_kopf_nur_mit_speicher_kind_traegt_seine_pauschale(db):
    """F-33: ein BKW ohne Modul-Kinder trägt seine eigene Erzeugung — mit nur einem Speicher-Kind steht seine
    Pauschale (800 Wp × 0,9 kWh/Wp, 80 % Eigenverbrauch × 30 ct + Rest × 8 ct = 184,32 €) in der Systemzeile,
    und seine kWp zählen in `system_kwp`."""
    a = await _anlage(db)
    bkw = _inv(a, "balkonkraftwerk", "Balkon", anschaffungskosten_gesamt=800.0, parameter={"leistung_wp": 800})
    db.add(bkw)
    await db.flush()
    sp = _inv(a, "speicher", "Akku", parent_investition_id=bkw.id, anschaffungskosten_gesamt=500.0,
              parameter={"kapazitaet_kwh": 2.0})
    db.add(sp)
    await db.flush()

    r = await _roi(db, a.id)
    zeile = _zeile(r, bkw.id)
    assert zeile.investition_typ == "balkonkraftwerk"
    kopf = _komponente(zeile, bkw.id)
    assert kopf.einsparung is None
    assert kopf.detail["hinweis"] == "Balkonkraftwerk - eigene Erzeugung, Einsparung in der Systemzeile"
    assert zeile.detail_berechnung["system_kwp"] == pytest.approx(0.8)
    speicher_anteil = _komponente(zeile, sp.id).einsparung or 0.0
    assert zeile.jahres_einsparung == pytest.approx(172.80 + 11.52 + speicher_anteil, abs=0.02)


async def test_modul_ohne_nennleistung_bekommt_keinen_anteil(db):
    """Ein Modul ohne kWp (weder Spalte noch Parameter) bekommt 0 € und 0 kg — kein Anteil am PV-Topf; das Modul
    mit Nennleistung trägt 100 %."""
    a = await _anlage(db)
    wr = _inv(a, "wechselrichter", "WR", anschaffungskosten_gesamt=1000.0)
    db.add(wr)
    await db.flush()
    mit = _inv(a, "pv-module", "Dach", parent_investition_id=wr.id, leistung_kwp=5.0, anschaffungskosten_gesamt=5000.0)
    ohne = _inv(a, "pv-module", "Garage", parent_investition_id=wr.id, anschaffungskosten_gesamt=900.0)
    db.add_all([mit, ohne])
    await db.flush()

    zeile = _zeile(await _roi(db, a.id), wr.id)
    k_ohne = _komponente(zeile, ohne.id)
    assert k_ohne.einsparung == 0
    assert k_ohne.co2_einsparung_kg == 0
    assert k_ohne.detail["anteil_prozent"] == 0.0
    assert _komponente(zeile, mit.id).detail["anteil_prozent"] == 100.0


async def test_dc_speicher_ohne_kapazitaet_nennt_den_hinweis(db):
    """N127: ein DC-Speicher ohne gepflegte Kapazität steht ohne Klammerzusatz da, ohne Einsparung und mit dem
    Hinweis, die Kapazität nachzutragen."""
    a = await _anlage(db)
    wr = _inv(a, "wechselrichter", "WR", anschaffungskosten_gesamt=1000.0)
    db.add(wr)
    await db.flush()
    pv = _inv(a, "pv-module", "Dach", parent_investition_id=wr.id, leistung_kwp=5.0, anschaffungskosten_gesamt=5000.0)
    sp = _inv(a, "speicher", "Akku", parent_investition_id=wr.id, anschaffungskosten_gesamt=4000.0, parameter={})
    db.add_all([pv, sp])
    await db.flush()

    k = _komponente(_zeile(await _roi(db, a.id), wr.id), sp.id)
    assert k.bezeichnung == "Akku"
    assert k.einsparung is None
    assert k.detail["hinweis"].startswith("Keine Kapazität gepflegt")
    assert k.detail["modus"] == "prognose"


async def test_dc_speicher_ist_duenne_datenbasis_nennt_die_abdeckung(db, monkeypatch):
    """Etappe C1: im IST-Modus nennt die Komponente die Preis-Abdeckung, wenn der Ladepreis-Helfer «Datenbasis zu
    dünn» meldet (Badge im Frontend)."""
    async def _fake(*_a, **_k):
        return _duenn()
    monkeypatch.setattr(roi_pv, "berechne_effektiver_ladepreis", _fake)
    a = await _anlage(db)
    wr = _inv(a, "wechselrichter", "WR", anschaffungskosten_gesamt=1000.0)
    db.add(wr)
    await db.flush()
    pv = _inv(a, "pv-module", "Dach", parent_investition_id=wr.id, leistung_kwp=5.0, anschaffungskosten_gesamt=5000.0)
    sp = _inv(a, "speicher", "Akku", parent_investition_id=wr.id, anschaffungskosten_gesamt=4000.0,
              parameter={"kapazitaet_kwh": 5.0})
    db.add_all([pv, sp])
    await db.flush()
    await _speicher_ist_monate(db, sp.id)

    k = _komponente(_zeile(await _roi(db, a.id), wr.id), sp.id)
    assert k.detail["modus"] == "ist"
    assert k.detail["ladepreis_abdeckung_prozent"] == 25.0


# ============================================================================
# standalone_zeilen
# ============================================================================


async def test_ac_speicher_ist_duenne_datenbasis_nennt_die_abdeckung(db, monkeypatch):
    """Derselbe Badge am eigenständigen (AC-)Speicher — der häufigste Fall."""
    async def _fake(*_a, **_k):
        return _duenn()
    monkeypatch.setattr(roi_pv, "berechne_effektiver_ladepreis", _fake)
    a = await _anlage(db)
    sp = _inv(a, "speicher", "AC-Akku", anschaffungskosten_gesamt=4000.0, parameter={"kapazitaet_kwh": 5.0})
    db.add(sp)
    await db.flush()
    await _speicher_ist_monate(db, sp.id)

    zeile = _zeile(await _roi(db, a.id), sp.id)
    assert zeile.detail_berechnung["modus"] == "ist"
    assert zeile.detail_berechnung["ladepreis_abdeckung_prozent"] == 25.0


async def test_bkw_ohne_leistungsangabe_nennt_800_wp(db):
    """F-35-Anzeige: ohne gepflegte Leistung nennt die Zeile die Standardleistung 800 Wp."""
    a = await _anlage(db)
    bkw = _inv(a, "balkonkraftwerk", "Balkon", anschaffungskosten_gesamt=600.0, parameter={})
    db.add(bkw)
    await db.flush()

    zeile = _zeile(await _roi(db, a.id), bkw.id)
    assert zeile.detail_berechnung["leistung_wp"] == 800
    assert zeile.detail_berechnung["hinweis"] == "Balkonkraftwerk 800 Wp"


# ============================================================================
# get_roi_dashboard (Gesamt)
# ============================================================================


async def test_ohne_anschaffungsdatum_laeuft_die_treppe_als_index(db):
    """N-525: ohne ein einziges Anschaffungsdatum gibt es kein Basisjahr — die Zeilen tragen kein Jahr, die Treppe
    läuft als Index ab 0, und ein Break-Even-Jahr wird nicht genannt."""
    a = await _anlage(db)
    wr = _inv(a, "wechselrichter", "WR", anschaffungskosten_gesamt=1000.0, anschaffungsdatum=None)
    db.add(wr)
    await db.flush()
    pv = _inv(a, "pv-module", "Dach", parent_investition_id=wr.id, leistung_kwp=5.0,
              anschaffungskosten_gesamt=5000.0, anschaffungsdatum=None)
    bkw = _inv(a, "balkonkraftwerk", "Balkon", anschaffungskosten_gesamt=600.0, parameter={"leistung_wp": 800},
               anschaffungsdatum=None)
    db.add_all([pv, bkw])
    await db.flush()

    r = await _roi(db, a.id)
    assert r.basis_jahr is None
    assert r.gesamt_amortisation_jahr is None
    assert all(b.anschaffungsjahr is None for b in r.berechnungen)
    assert r.amortisations_verlauf and r.amortisations_verlauf[0].jahr == 0


# ============================================================================
# lade_roi_eingaenge
# ============================================================================


async def test_unbekannte_anlage_ist_404(db):
    with pytest.raises(HTTPException) as e:
        await _roi(db, 999999)
    assert e.value.status_code == 404
    assert e.value.detail == "Anlage nicht gefunden"


async def test_anlage_ohne_investitionen_liefert_leere_rechnung(db):
    a = await _anlage(db)
    await db.flush()
    r = await _roi(db, a.id)
    assert r.berechnungen == []
    assert r.gesamt_kapitaleinsatz == 0
    assert r.gesamt_jahres_einsparung == 0
    assert r.gesamt_roi_prozent is None
    assert r.basis_jahr is None


async def test_ist_pv_ladeanteil_hoechstens_einmal_je_request(db, monkeypatch):
    """N-188: zwei E-Autos ohne gepflegten PV-Anteil ⇒ die Fakten-Schicht wird EINMAL gefragt, beide Zeilen
    rechnen mit dem IST-Anteil."""
    aufrufe = []

    async def _fake(*_a, **_k):
        aufrufe.append(1)
        return 42.0
    monkeypatch.setattr(roi_eingaenge, "ist_pv_ladeanteil_prozent", _fake)
    a = await _anlage(db)
    e1 = _inv(a, "e-auto", "Auto 1", anschaffungskosten_gesamt=40000.0, anschaffungskosten_alternativ=30000.0,
              parameter={"jahresfahrleistung_km": 10000, "verbrauch_kwh_100km": 18})
    e2 = _inv(a, "e-auto", "Auto 2", anschaffungskosten_gesamt=30000.0, anschaffungskosten_alternativ=25000.0,
              parameter={"jahresfahrleistung_km": 10000, "verbrauch_kwh_100km": 18})
    db.add_all([e1, e2])
    await db.flush()

    r = await _roi(db, a.id)
    assert len(aufrufe) == 1
    # Beide Zeilen mit demselben Anteil ⇒ dieselben Stromkosten bei gleicher Fahrleistung und gleichem Verbrauch.
    assert _zeile(r, e1.id).detail_berechnung["strom_kosten_euro"] == _zeile(r, e2.id).detail_berechnung["strom_kosten_euro"]


async def _anlage_mit_tarifen(db, *, wp=None, wallbox=None, einspeise=8.0):
    a = await _anlage(db, "Tarife")
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=einspeise))
    if wp is not None:
        db.add(Strompreis(anlage_id=a.id, verwendung="waermepumpe", gueltig_ab=date(2023, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=wp, einspeiseverguetung_cent_kwh=0.0))
    if wallbox is not None:
        db.add(Strompreis(anlage_id=a.id, verwendung="wallbox", gueltig_ab=date(2023, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=wallbox, einspeiseverguetung_cent_kwh=0.0))
    wp_inv = _inv(a, "waermepumpe", "WP", anschaffungskosten_gesamt=15000.0, anschaffungskosten_alternativ=8000.0,
                  parameter={"effizienz_modus": "gesamt_jaz", "jaz": 4.0, "heizwaermebedarf_kwh": 8000,
                             "warmwasserbedarf_kwh": 2000, "alter_energietraeger": "gas", "wp_art": "luft_wasser"})
    ea = _inv(a, "e-auto", "Auto", anschaffungskosten_gesamt=40000.0, anschaffungskosten_alternativ=30000.0,
              parameter={"jahresfahrleistung_km": 10000, "verbrauch_kwh_100km": 20, "pv_ladeanteil_prozent": 0})
    bkw = _inv(a, "balkonkraftwerk", "Balkon", anschaffungskosten_gesamt=600.0, parameter={"leistung_wp": 800})
    db.add_all([wp_inv, ea, bkw])
    await db.flush()
    return a, wp_inv, ea, bkw


async def test_wp_und_wallbox_tarif_neben_dem_allgemeinen(db):
    """Die Wärmepumpe rechnet mit dem WP-Tarif (20 ct statt 30 ct), das E-Auto lädt zum Wallbox-Tarif (40 ct);
    ohne eigene Tarife beide mit dem allgemeinen. Preise aus der DB, ohne Override."""
    a, wp_inv, ea, _ = await _anlage_mit_tarifen(db, wp=20.0, wallbox=40.0)
    r = await _roi(db, a.id, strompreis_cent=None, einspeiseverguetung_cent=None)
    wp_kosten = _zeile(r, wp_inv.id).detail_berechnung["wp_kosten_euro"]
    strom_kosten = _zeile(r, ea.id).detail_berechnung["strom_kosten_euro"]
    # 10.000 kWh / JAZ 4 = 2.500 kWh × 20 ct = 500 €; 10.000 km × 20 kWh/100 km = 2.000 kWh × 40 ct (PV-Anteil 0) = 800 €
    assert wp_kosten == pytest.approx(500.0, abs=0.01)
    assert strom_kosten == pytest.approx(800.0, abs=0.01)


async def test_ohne_eigene_tarife_gilt_der_allgemeine(db):
    a, wp_inv, ea, _ = await _anlage_mit_tarifen(db)
    r = await _roi(db, a.id, strompreis_cent=None, einspeiseverguetung_cent=None)
    assert _zeile(r, wp_inv.id).detail_berechnung["wp_kosten_euro"] == pytest.approx(750.0, abs=0.01)
    assert _zeile(r, ea.id).detail_berechnung["strom_kosten_euro"] == pytest.approx(600.0, abs=0.01)


async def test_gepflegte_einspeiseverguetung_null_bleibt_null(db):
    """`is not None` statt truthy: eine im Tarif gepflegte 0 ist ein Wert — das BKW bekommt keinen Einspeise-Erlös
    (800 Wp × 0,9 × 80 % × 30 ct = 172,80 €, der Rest × 0 ct)."""
    a, _, _, bkw = await _anlage_mit_tarifen(db, einspeise=0.0)
    r = await _roi(db, a.id, strompreis_cent=None, einspeiseverguetung_cent=None)
    assert _zeile(r, bkw.id).jahres_einsparung == pytest.approx(172.80, abs=0.01)


async def test_anlagenweite_ausgabe_stuft_die_treppe_im_jahr_ihres_monats(db):
    """N-525 + Bauschritt 4: eine Ausgabe auf der Monatsdaten-Zeile (ohne Komponente) steht in der Kalender-Treppe als
    Kapital im Jahr ihres Monats (2026), nicht im Anschaffungsjahr (2024) — und nur dort."""
    a = Anlage(anlagenname="Treppe anlagenweit", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=4, netzbezug_kwh=100.0, einspeisung_kwh=50.0,
                       sonstige_positionen=[{"bezeichnung": "Dachreparatur", "betrag": 700.0, "typ": "ausgabe"}]))
    bkw = _inv(a, "balkonkraftwerk", "Balkon", anschaffungskosten_gesamt=600.0, parameter={"leistung_wp": 800},
               anschaffungsdatum=date(2024, 3, 1))
    db.add(bkw)
    await db.flush()

    r = await _roi(db, a.id, jahr=None)
    kapital = {p.jahr: p.kapitaleinsatz_kumuliert_euro for p in r.amortisations_verlauf}
    assert kapital[2024] == pytest.approx(600.0)
    assert kapital[2025] == pytest.approx(600.0)
    assert kapital[2026] == pytest.approx(1300.0)
    assert r.gesamt_sonstige_ausgaben_euro == pytest.approx(700.0)
