"""RF-83 … RF-85 (5.11.2026): benannte Proben für die Zweige, die die Testdateien vor dem Schnitt nicht betraten.

Gemessen über die Bogen-Spur der direkten Testdateien am HEAD `2966f1a77` (51 Dateien, `1709 passed`): offen waren in
``community_service.py::prepare_community_data`` die unbekannte Anlage und der einzelne Ost-West-Erzeuger, in
``vorschlag_service.py::VorschlagService._get_berechnete_werte`` die unbekannte Investition, der Modus
``getrennte_cops``, ein unbekannter Modus, eine Arbeitszahl 0, der Gesamtstrom aus getrennter Messung und die
Jahresfahrleistung, in ``korrekturprofil_aggregator.py::aggregiere_korrekturprofil_anlage`` die Anlage ohne Koordinaten,
der Stichtag aus der Uhr, die ganze Stufe ``sonnenstand_wetter``, die Prognose-Schwelle 0,05 kWh, ein Bin mit
Σ Prognose < 1 kWh und eine Stundenzeile ohne Snapshot. Die Proben halten das Verhalten des HEAD fest (am HEAD grün);
die Fixture-GMs ``community-daten``/``vorschlag-werte`` und der Zusatz-GM ``rf83/gm-korrekturprofil.py`` decken die
Zweige vollständig — diese Datei hält sie im Gate der Suite.

Schwesterdateien: test_n617_community_stammdaten_heute.py, test_stillgelegter_speicher_kapazitaet_f24.py,
test_community_payload_monats_fakten.py (Community-Datensatz); test_waerme_vorschlag_b1.py, test_n391_gesamtwaerme.py,
test_407_tachostand.py, test_vorschlag_ladepreis_r15_2.py (Vorschläge); test_korrekturprofil_stunde_variante_a.py,
test_n547_lern_soll_nicht_zirkulaer.py, test_s5_stunden_der_tage.py (Korrekturprofil).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.models.korrekturprofil import (
    PROFIL_TYP_SONNENSTAND_WETTER,
    PROFIL_TYP_STUNDE,
    Korrekturprofil,
)
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services import community_service, korrekturprofil_aggregator
from backend.services.community_service import prepare_community_data
from backend.services.korrekturprofil_aggregator import aggregiere_korrekturprofil_anlage
from backend.services.vorschlag_service import VorschlagQuelle, VorschlagService

D0 = date(2024, 1, 1)


# ── RF-83 Community-Datensatz ─────────────────────────────────────────────────────────────────────────────────────

async def _anlage_mit(db, invs: list[dict], **anlage_kw) -> int:
    a = Anlage(anlagenname="RF-83", leistung_kwp=6.0, standort_plz="10115", standort_land="DE",
               **{"installationsdatum": D0, **anlage_kw})
    db.add(a)
    await db.flush()
    for kw in invs:
        db.add(Investition(anlage_id=a.id, anschaffungskosten_gesamt=1.0, **{"anschaffungsdatum": D0, **kw}))
    await db.commit()
    return a.id


async def test_unbekannte_anlage_liefert_none(db):
    assert await prepare_community_data(db, 999_999) is None


async def test_einzelner_ost_west_erzeuger_wird_uebernommen(db):
    aid = await _anlage_mit(db, [dict(typ="pv-module", bezeichnung="OW", leistung_kwp=8.0, neigung_grad=12,
                                      ausrichtung="Ost-West")])
    d = await prepare_community_data(db, aid, include_monatswerte=False)
    assert (d["neigung_grad"], d["ausrichtung"]) == (12, "ost-west")


async def test_spanne_genau_45_grad_mischt_nicht(db):
    """Süd (180) + Südost (135): Spanne 45 ist nicht > 45 ⇒ Label des ganzzahligen Mittels 157 ⇒ „süd-ost"."""
    aid = await _anlage_mit(db, [
        dict(typ="pv-module", bezeichnung="S", leistung_kwp=6.0, neigung_grad=30, ausrichtung="Süd"),
        dict(typ="pv-module", bezeichnung="SO", leistung_kwp=3.0, neigung_grad=15, ausrichtung="Südost"),
    ])
    d = await prepare_community_data(db, aid, include_monatswerte=False)
    assert (d["neigung_grad"], d["ausrichtung"]) == (22, "süd-ost")


async def test_bkw_ohne_oder_mit_null_anzahl_zaehlt_einfach(db):
    aid = await _anlage_mit(db, [
        dict(typ="balkonkraftwerk", bezeichnung="a", parameter={"leistung_wp": 600}),
        dict(typ="balkonkraftwerk", bezeichnung="b", parameter={"leistung_wp": 300, "anzahl": 0}),
    ])
    d = await prepare_community_data(db, aid, include_monatswerte=False)
    assert d["bkw_wp"] == 900


async def test_sonstiges_hoechstens_drei_bezeichnungen_ohne_leere(db):
    aid = await _anlage_mit(db, [dict(typ="sonstiges", bezeichnung=b) for b in ("Sauna", "", "Pool", "Teich", "Garage")])
    d = await prepare_community_data(db, aid, include_monatswerte=False)
    assert (d["hat_sonstiges"], d["sonstiges_bezeichnung"]) == (True, "Sauna, Pool, Teich")


async def test_ohne_installationsdatum_gilt_das_jahr_der_uhr(db, monkeypatch):
    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2031, 3, 1, 12, 0)

    monkeypatch.setattr(community_service, "datetime", _Uhr)
    aid = await _anlage_mit(db, [], installationsdatum=None)
    d = await prepare_community_data(db, aid, include_monatswerte=False)
    assert (d["installation_jahr"], d["neigung_grad"], d["ausrichtung"], d["region"]) == (2031, 30, "süd", "BE")


async def test_payload_schluessel_reihenfolge_bleibt(db):
    """Der Draht-Vertrag mit eedc-community: Schlüssel und Reihenfolge des Datensatzkopfs (der Server rechnet nicht nach)."""
    aid = await _anlage_mit(db, [])
    d = await prepare_community_data(db, aid, include_monatswerte=False)
    assert list(d) == [
        "region", "kwp", "ausrichtung", "neigung_grad", "speicher_kwh", "installation_jahr", "hat_waermepumpe",
        "hat_eauto", "hat_wallbox", "hat_balkonkraftwerk", "hat_sonstiges", "wp_art", "kuehlung_art", "wallbox_kw",
        "bkw_wp", "sonstiges_bezeichnung", "monatswerte", "monate_vollstaendig", "soll_jahr_kwh",
    ]
    assert d["monate_vollstaendig"] is False and d["monatswerte"] == []


# ── RF-84 Vorschlagswerte ─────────────────────────────────────────────────────────────────────────────────────────

async def _inv(db, typ: str, parameter, monate: dict[tuple[int, int], dict] | None = None) -> tuple[int, int]:
    a = Anlage(anlagenname="RF-84", leistung_kwp=9.9)
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ=typ, bezeichnung=typ, parameter=parameter)
    db.add(inv)
    await db.flush()
    for (j, m), daten in (monate or {}).items():
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=j, monat=m, verbrauch_daten=daten))
    await db.commit()
    return a.id, inv.id


async def _berechnet(db, aid, iid, feld, jahr=2026, monat=3):
    return await VorschlagService(db)._get_berechnete_werte(aid, feld, jahr, monat, iid)


async def test_unbekannte_investition_liefert_nichts(db):
    aid, _ = await _inv(db, "waermepumpe", {"jaz": 3.0})
    assert await _berechnet(db, aid, 999_999, "waerme_kwh") == []


GETRENNT = {(2026, 3): {"stromverbrauch_kwh": 412.6, "strom_heizen_kwh": 301.2, "strom_warmwasser_kwh": 111.4}}


async def test_getrennte_cops_je_funktion(db):
    aid, iid = await _inv(db, "waermepumpe", {"effizienz_modus": "getrennte_cops", "cop_heizung": 3.9, "cop_warmwasser": 2.7,
                                              "getrennte_strommessung": True}, GETRENNT)
    heiz = await _berechnet(db, aid, iid, "heizenergie_kwh")
    ww = await _berechnet(db, aid, iid, "warmwasser_kwh")
    assert [(v.wert, v.konfidenz, v.details["cop"], v.details["sprosse"]) for v in heiz] == [(round(301.2 * 3.9, 1), 60, 3.9, "F5")]
    assert [(v.wert, v.details["cop"]) for v in ww] == [(round(111.4 * 2.7, 1), 2.7)]


async def test_unbekannter_modus_und_arbeitszahl_null_ohne_vorschlag(db):
    aid, iid = await _inv(db, "waermepumpe", {"effizienz_modus": "irgendwas", "jaz": 3.0, "scop_heizung": 4.0,
                                              "getrennte_strommessung": True}, GETRENNT)
    assert await _berechnet(db, aid, iid, "heizenergie_kwh") == []
    aid, iid = await _inv(db, "waermepumpe", {"effizienz_modus": "gesamt_jaz", "jaz": 0},
                          {(2026, 3): {"stromverbrauch_kwh": 250.0}})
    assert await _berechnet(db, aid, iid, "waerme_kwh") == []


async def test_gesamtstrom_aus_getrennter_messung(db):
    aid, iid = await _inv(db, "waermepumpe", {"getrennte_strommessung": True}, {
        **GETRENNT, (2026, 4): {"strom_heizen_kwh": 80.0},
    })
    v = await _berechnet(db, aid, iid, "stromverbrauch_kwh")
    assert [(x.wert, x.quelle, x.konfidenz, x.details) for x in v] == [
        (412.6, VorschlagQuelle.BERECHNUNG, 95, {"strom_heizen": 301.2, "strom_warmwasser": 111.4}),
    ]
    assert await _berechnet(db, aid, iid, "stromverbrauch_kwh", monat=4) == []   # WW-Strom fehlt ⇒ keine Summe


async def test_km_aus_jahresfahrleistung(db):
    aid, iid = await _inv(db, "e-auto", {"jahresfahrleistung_km": 12345})
    v = await _berechnet(db, aid, iid, "km_gefahren")
    assert [(x.wert, x.quelle, x.konfidenz, x.beschreibung) for x in v] == [
        (1029.0, VorschlagQuelle.PARAMETER, 30, "Aus Jahresfahrleistung: 12345 km ÷ 12"),
    ]


# ── RF-85 Korrekturprofil ─────────────────────────────────────────────────────────────────────────────────────────

LAT, LON = 48.1, 11.6
STICHTAG = date(2026, 6, 20)


async def _seed_wetter(db) -> Anlage:
    """12 Junitage: 11–13 Uhr IST 4,0 / SOLL 2,0 bei klarem Wetter (Faktor 2,0 ⇒ Klemme 1,3), 14 Uhr SOLL 0,04
    (unter der Schwelle), 15 Uhr SOLL 0,05 (über der Schwelle, aber Σ 0,6 kWh < 1)."""
    a = Anlage(anlagenname="RF-85", leistung_kwp=9.9, latitude=LAT, longitude=LON)
    db.add(a)
    await db.flush()
    for t in range(1, 13):
        d = date(2026, 6, t)
        stunden = {11: (4.0, 2.0), 12: (4.0, 2.0), 13: (4.0, 2.0), 14: (1.0, 0.04), 15: (1.0, 0.05)}
        profil = [0.0] * 24
        for h, (_, s) in stunden.items():
            profil[h] = s
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=d, lern_soll_stundenprofil_kwh=profil,
                                    lern_soll_kwh=round(sum(s for _, s in stunden.values()), 4), stunden_verfuegbar=24))
        for h, (ist, _) in stunden.items():
            db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=h, pv_kw=ist, bewoelkung_prozent=5,
                                      niederschlag_mm=0.0, wetter_code=0))
    await db.commit()
    return a


async def _profil(db, aid, typ) -> Korrekturprofil:
    return (await db.execute(select(Korrekturprofil).where(
        Korrekturprofil.anlage_id == aid, Korrekturprofil.profil_typ == typ))).scalar_one()


async def test_ohne_koordinaten_uebersprungen(db):
    a = Anlage(anlagenname="ohne", leistung_kwp=5.0, latitude=48.0, longitude=None)
    db.add(a)
    await db.commit()
    assert await aggregiere_korrekturprofil_anlage(a, db) == {
        "status": "skipped", "grund": "Anlage hat keine Koordinaten — Sonnenstand nicht berechenbar",
    }


async def test_stufe_sonnenstand_wetter_geklemmt_und_schwellen(db):
    a = await _seed_wetter(db)
    r = await aggregiere_korrekturprofil_anlage(a, db, heute=STICHTAG)
    assert r["status"] == "ok" and r["tage_eingegangen"] == 12 and r["skalar"] == 1.3
    sw = await _profil(db, a.id, PROFIL_TYP_SONNENSTAND_WETTER)
    assert sw.faktoren and set(sw.faktoren.values()) == {1.3}
    assert all(k.endswith("_klar") for k in sw.faktoren)
    # 14 Uhr fällt an der Prognose-Schwelle aus; 15 Uhr ergibt Bins mit Σ Prognose < 1 kWh ⇒ kein Faktor
    assert sum(sw.datenpunkte_pro_bin.values()) == 36
    assert sw.bin_definition["wetterklassen"] == ["klar", "diffus", "wechselhaft"]
    # stunde: der Juni-Monat (12 Tage) und das Quartal liegen unter 15, der Gesamt-Pool (30 Tage, 12 ≥ 7) trägt — die
    # Kaskade füllt damit JEDEN Monat mit denselben drei Stunden; 14 und 15 Uhr fehlen (Schwelle bzw. Σ Prognose < 1)
    st = await _profil(db, a.id, PROFIL_TYP_STUNDE)
    assert st.faktoren == {str(m): {"11": 1.3, "12": 1.3, "13": 1.3} for m in range(1, 13)}
    assert st.datenpunkte_pro_bin == {f"{m}_{h}": 12 for m in range(1, 13) for h in (11, 12, 13)}
    assert r["bins_stunde"] == 36


async def test_stichtag_aus_der_uhr(db, monkeypatch):
    a = await _seed_wetter(db)

    class _Tag(date):
        @classmethod
        def today(cls):
            return STICHTAG

    monkeypatch.setattr(korrekturprofil_aggregator, "date", _Tag)
    ohne = await aggregiere_korrekturprofil_anlage(a, db)
    mit = await aggregiere_korrekturprofil_anlage(a, db, heute=STICHTAG)
    assert ohne == mit and ohne["bins_stunde"] == 36


async def test_stundenzeile_ohne_snapshot_faellt_aus(db, monkeypatch):
    """Eine Mischzeile eines Kanal-Tags liegt auf Slot 0 des Folgetags — trägt der keinen Snapshot, fällt sie aus."""
    a = await _seed_wetter(db)
    echt = korrekturprofil_aggregator.lade_ist_wetter_stunden

    async def mit_fremder(db_, aid, tage):
        return list(await echt(db_, aid, tage)) + [(STICHTAG - timedelta(days=1), 0, 9.0, 5, 0.0, 0, None)]

    monkeypatch.setattr(korrekturprofil_aggregator, "lade_ist_wetter_stunden", mit_fremder)
    r = await aggregiere_korrekturprofil_anlage(a, db, heute=STICHTAG)
    assert (r["tage_eingegangen"], r["bins_stunde"]) == (12, 36)
    assert set((await _profil(db, a.id, PROFIL_TYP_STUNDE)).datenpunkte_pro_bin) == {
        f"{m}_{h}" for m in range(1, 13) for h in (11, 12, 13)}


@pytest.mark.parametrize("feld", ["sum_ist", "sum_prog"])
def test_bin_akkumulator_startet_bei_null(feld):
    """Kleine Gegenprobe zur Form: der Akkumulator der Bin-Stufen beginnt bei 0,0 (Σ über Stunden)."""
    acc = korrekturprofil_aggregator._BinAccumulator()
    assert (getattr(acc, feld), acc.anzahl) == (0.0, 0)
