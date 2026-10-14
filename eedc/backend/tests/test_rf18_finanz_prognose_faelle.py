"""RF-18 — drei Fälle der Finanz-Prognose, die weder die übrige Suite noch die Golden-Master-Bestände erreichen.

Der Schnitt von ``get_finanz_prognose`` (RF-18, Serie „Funktion vor Datei", 14.10.2026) ist ein reiner Umzug: die
101 Werkzeug-Zeilen ``if "<k>" in _out`` werden unbedingt, und ``komponenten_beitraege_zusammenstellen`` gibt vier
Blöcke samt Verzweigungen an Hilfen derselben Datei ab. Die Vorlage RF-18 (§4.6/§4.7) hat gemessen, dass zwei
Sprengsätze sonst still bleiben (S5, S6) und zwei Zweige ungedeckt sind:

* **F1** — Etappe C (#264): der stundengranulare Ladepreis überstimmt den Param-Mittelwert nur mit belastbarer Quelle.
  (a) ``dyn-tarif`` 22,5 ct überstimmt, (b) ``datenbasis-zu-duenn`` 22,5 ct nicht, (c) ein Fehler des Helpers lässt
  den Param-Wert stehen und wird über den Logger der Zerlegung gemeldet.
* **F2** — die Speicher-Historie liest die Netzladung auch aus dem Alt-Schlüssel ``speicher_ladung_netz_kwh``.
* **F3** — zwei private E-Autos, eines ohne Kilometer: nur das Auto mit Kilometern trägt eine Benzin-Zeile, die
  Summe der Zeilen bleibt die Aggregat-Ersparnis.

Rechnung F1/F2 (ein Speicher, sechs Monate je 100 kWh Ladung, 90 kWh Entladung, 40 kWh Netzladung; Tarif 30 ct Bezug,
8 ct Einspeisung, η 95 %): Prognose-Entladung 1 080 kWh/Jahr, Netz-Anteil 40 %, projizierte Netzladung
1 080 / 0,95 × 0,4 = 454,74 kWh, davon entladen 432 kWh. PV-Teil 648 kWh × 22 ct = 142,56 €; Netz-Teil
432 × 30 ct − 454,74 × Ladepreis. Ladepreis 12 ct (Param) ⇒ 217,59 €, 22,5 ct ⇒ 169,84 €, ohne Netzladung
1 080 × 22 ct = 237,60 €.

Schwesterdateien: test_n571_leerstring_legt_keine_route_lahm.py (Speicher-Parameter der Aussicht),
test_speicher_wirtschaftlichkeit_netzanteil.py (Spread-Formel, Alt-Schlüssel im IST-Aggregat),
test_aussichten_multi_eauto.py (mehrere E-Autos), test_rf17_wp_hub_faelle.py (dieselbe Fall-Probe für den WP-Hub).
"""
import logging
from datetime import date

import pytest

from backend.api.routes.aussichten import finanz_zerlegung
from backend.api.routes.aussichten.finanzen import get_finanz_prognose
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis
from backend.services.speicher_wirtschaftlichkeit import EffektiverLadepreisErgebnis

_PARAM_EURO = 217.59      # Ladepreis 12 ct (Param-Mittelwert)
_DYN_EURO = 169.84        # Ladepreis 22,5 ct (Etappe C)
_OHNE_NETZ_EURO = 237.60  # reiner Spread


async def _anlage(db, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for monat in range(1, 7):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat, einspeisung_kwh=200.0, netzbezug_kwh=150.0))
    return anlage


async def _speicher_anlage(db, netz_schluessel: str | None = "ladung_netz_kwh") -> int:
    anlage = await _anlage(db, "RF-18 Speicher")
    sp = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="RF-18 Speicher",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0,
        parameter={"kapazitaet_kwh": 10, "wirkungsgrad_prozent": 95, "arbitrage_faehig": True,
                   "lade_durchschnittspreis_cent": 12},
    )
    db.add(sp)
    await db.flush()
    for monat in range(1, 7):
        daten = {"ladung_kwh": 100.0, "entladung_kwh": 90.0}
        if netz_schluessel:
            daten[netz_schluessel] = 40.0
        db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=2025, monat=monat, verbrauch_daten=daten))
    await db.flush()
    return anlage.id


def _ladepreis(quelle: str, cent: float | None) -> EffektiverLadepreisErgebnis:
    return EffektiverLadepreisErgebnis(
        quelle=quelle, effektiver_ladepreis_cent=cent, netz_lade_kwh=240.0,
        netzlade_stunden_mit_preis=10, netzlade_stunden_gesamt=10, stunden_gesamt_im_fenster=100,
    )


def _speicher_zeile(r):
    zeilen = [k for k in r.komponenten_beitraege if k.typ == "speicher"]
    assert len(zeilen) == 1
    return zeilen[0]


@pytest.mark.parametrize(("quelle", "cent", "erwartet"), [
    ("keine-tep-daten", None, _PARAM_EURO),
    ("dyn-tarif", 22.5, _DYN_EURO),
    ("datenbasis-zu-duenn", 22.5, _PARAM_EURO),
])
async def test_f1_etappe_c_ueberstimmt_nur_mit_belastbarer_quelle(db, monkeypatch, quelle, cent, erwartet):
    anlage_id = await _speicher_anlage(db)

    async def _helfer(_db, *, anlage_id, von, bis):
        assert von == date(2024, 1, 1)
        return _ladepreis(quelle, cent)

    # Am benutzenden Modul — dort ruft die Etappe C den Helper.
    monkeypatch.setattr(finanz_zerlegung, "berechne_effektiver_ladepreis", _helfer)
    r = await get_finanz_prognose(anlage_id, monate=12, db=db)

    assert r.speicher_ev_erhoehung_kwh == 1080.0
    assert r.speicher_ev_erhoehung_euro == pytest.approx(erwartet, abs=0.005)
    assert _speicher_zeile(r).beitrag_euro_jahr == pytest.approx(erwartet, abs=0.005)


async def test_f1_fehler_des_ladepreis_helpers_laesst_den_param_wert_stehen(db, monkeypatch, caplog):
    anlage_id = await _speicher_anlage(db)

    async def _helfer(_db, *, anlage_id, von, bis):
        raise RuntimeError("RF-18-Probe")

    monkeypatch.setattr(finanz_zerlegung, "berechne_effektiver_ladepreis", _helfer)
    with caplog.at_level(logging.WARNING, logger="backend.api.routes.aussichten.finanz_zerlegung"):
        r = await get_finanz_prognose(anlage_id, monate=12, db=db)

    assert r.speicher_ev_erhoehung_euro == pytest.approx(_PARAM_EURO, abs=0.005)
    meldungen = [
        rec for rec in caplog.records
        if rec.name == "backend.api.routes.aussichten.finanz_zerlegung" and rec.levelno == logging.WARNING
    ]
    assert len(meldungen) == 1
    assert meldungen[0].getMessage() == (
        f"aussichten: effektiver-Ladepreis-Lookup fehlgeschlagen (anlage={anlage_id}): RF-18-Probe"
    )


@pytest.mark.parametrize(("schluessel", "erwartet"), [
    ("ladung_netz_kwh", _PARAM_EURO),
    ("speicher_ladung_netz_kwh", _PARAM_EURO),   # Alt-Schlüssel — dieselbe Netzladung
    (None, _OHNE_NETZ_EURO),                     # Gegenanker: ohne Netzladung reiner Spread
])
async def test_f2_speicher_historie_liest_den_alt_schluessel(db, schluessel, erwartet):
    anlage_id = await _speicher_anlage(db, netz_schluessel=schluessel)
    r = await get_finanz_prognose(anlage_id, monate=12, db=db)
    assert r.speicher_ev_erhoehung_euro == pytest.approx(erwartet, abs=0.005)
    assert _speicher_zeile(r).beitrag_euro_jahr == pytest.approx(erwartet, abs=0.005)


async def test_f3_zweites_e_auto_ohne_km_traegt_keine_benzin_zeile(db):
    anlage = await _anlage(db, "RF-18 E-Autos")
    autos = []
    for name in ("RF-18 mit km", "RF-18 ohne km"):
        ea = Investition(
            anlage_id=anlage.id, typ="e-auto", bezeichnung=name, anschaffungsdatum=date(2024, 1, 1),
            anschaffungskosten_gesamt=30000.0,
            parameter={"vergleich_verbrauch_l_100km": 7.0, "benzinpreis_euro": 1.8, "verbrauch_kwh_100km": 18},
        )
        db.add(ea)
        autos.append(ea)
    await db.flush()
    for monat in range(1, 7):
        db.add(InvestitionMonatsdaten(
            investition_id=autos[0].id, jahr=2025, monat=monat,
            verbrauch_daten={"km_gefahren": 1000.0, "ladung_netz_kwh": 120.0, "ladung_pv_kwh": 60.0},
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=autos[1].id, jahr=2025, monat=monat,
            verbrauch_daten={"ladung_netz_kwh": 50.0, "ladung_pv_kwh": 30.0},
        ))
    await db.flush()

    r = await get_finanz_prognose(anlage.id, monate=12, db=db)

    # 12 000 km/Jahr × 7 l/100 km × 1,80 € = 1 512 € Benzin; Strom (2 040 kWh Netz + 1 080 kWh PV) × 30 ct = 936 €
    # — beides nur über das Auto mit Kilometern (km-Anteil 100 %).
    benzin = [k for k in r.komponenten_beitraege if k.typ == "e-auto-benzin"]
    assert [(k.bezeichnung, k.beitrag_euro_jahr) for k in benzin] == [("RF-18 mit km (vs. Benzin)", 576.0)]
    assert r.eauto_alternativ_ersparnis_euro == pytest.approx(576.0, abs=0.005)
