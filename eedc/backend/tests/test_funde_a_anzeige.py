"""Fund-Päckchen A «Anzeige-Fehler» (22.11.2026) — vier Rechenfehler, die ein Anwender sieht.

* **A1 — Arbeitszahl am Teil-Tag.** Eine Arbeitszahl entsteht nur aus Wärme und Strom DESSELBEN Zeitfensters
  (``core/berechnungen/waermepumpe_kennzahl.py``, Abschnitt «Ein Zeitfenster»). Gemessen nach «Daten vor der Änderung
  löschen» am WP-Stromfeld: *Cockpit → Tag* zeigte am ersten Teil-Tag 9,0 (57,6 ÷ 6,4, Wärme 0–24 Uhr, Strom ab 08:00);
  jetzt 6,0 (38,4 ÷ 6,4) — die Wärme der Stunden mit Strom, wie an den vollen Tagen desselben Sensors. Ohne Stundenwerte
  (Tagesränder aus Zählerständen) bleibt die Zahl «—» mit «Zähler messen verschiedene Zeiträume».
* **A2 — Wärme ohne Strom (H-1 aus N-806).** Ein Monat mit Wärme, aber ohne gemessenen Strom trägt in der Jahresformel
  (Aussichten → Finanzen, HA-Export) und im Export-Sensor je Wärmepumpe keine Ersparnis und kein Zwölftel — wie die
  Gerätezeile (vorher 109,10 € bei 400 kWh Wärme).
* **A3 — USt auf den Eigenverbrauch je Komponente (K-1).** Kosten einer Komponente zählen nur über ihre aktiven Monate
  des Jahres (vorher 80,94 € statt 68,97 € bei einem Speicher ab Juli).
* **A4 — Prognose ohne stillgelegte Wärmepumpen (K-2).** Die Zusatzkosten der Altheizung tragen nur heute aktive
  Wärmepumpen in die Zukunft (vorher 600 €/Jahr einer stillgelegten WP in ``wp_alternativ_ersparnis_euro``).

Messtest vor/nach: ``~/.claude/plans/golden-master/funde-a-2026-11-22/test_mess_funde_a.py``.

Schwesterdateien: test_funde_b.py, test_funde_c.py (die Päckchen B und C desselben Tags).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_ZEITRAUM,
    mengen_im_stromfenster,
    zeitraum_versetzt,
)

# ── A1: der Baustein ─────────────────────────────────────────────────────────────────────────────────────────────────

W, S = "inv:4:heizenergie_kwh", "inv:4:stromverbrauch_kwh"


def test_a1_teil_tag_zaehlt_die_waerme_nur_in_den_strom_stunden():
    mengen = {W: (2.4,) * 24, S: (None,) * 8 + (0.4,) * 16}
    spannen = {W: (3600,) * 24, S: (None,) * 8 + (3600,) * 16}
    assert mengen_im_stromfenster(mengen, spannen) == {W: pytest.approx(16 * 2.4)}


def test_a1_voller_tag_ist_bitgleich_das_tages_delta():
    werte = tuple(0.1 * i + 0.7 for i in range(24))
    mengen = {W: werte, S: (0.5,) * 24}
    assert mengen_im_stromfenster(mengen, {W: (3600,) * 24, S: (3600,) * 24})[W] == sum(werte)


def test_a1_spanne_des_stroms_deckt_die_fehlenden_stunden_davor():
    """Ein Strom-Zuwachs über drei Stunden (Lücke davor) misst diese drei Stunden — die Wärme dort zählt."""
    mengen = {W: (1.0,) * 24, S: (None,) * 9 + (1.5,) + (0.5,) * 14}
    spannen = {W: (3600,) * 24, S: (None,) * 9 + (3 * 3600,) + (3600,) * 14}
    assert mengen_im_stromfenster(mengen, spannen)[W] == pytest.approx(17.0)   # Stunden 7 … 23


def test_a1_waerme_stunde_ueber_den_fensterrand_wird_nicht_verteilt():
    mengen = {W: (None,) * 7 + (3.0,) + (1.0,) * 16, S: (None,) * 7 + (0.5,) * 17}
    spannen = {W: (None,) * 7 + (3 * 3600,) + (3600,) * 16, S: (None,) * 7 + (3600,) * 17}
    assert mengen_im_stromfenster(mengen, spannen)[W] == pytest.approx(16.0)   # die 3,0 reicht vor 07:00 zurück


def test_a1_ohne_strom_stunde_kein_eingriff_und_andere_geraete_unberuehrt():
    mengen = {W: (1.0,) * 24, S: (None,) * 24, "inv:5:heizenergie_kwh": (1.0,) * 24, "inv:5:stromverbrauch_kwh": (0.2,) * 24}
    out = mengen_im_stromfenster(mengen, {})
    assert W not in out and out["inv:5:heizenergie_kwh"] == pytest.approx(24.0)


@pytest.mark.parametrize("fenster, soll", [
    ({"stromverbrauch_kwh": (8, None), "heizenergie_kwh": (None, None)}, True),     # Strom ab 08:00, Wärme ganzer Tag
    ({"stromverbrauch_kwh": (None, 20), "heizenergie_kwh": (None, None)}, True),    # Strom bis 20:00
    ({"stromverbrauch_kwh": (8, None), "heizenergie_kwh": (8, None)}, False),       # beide ab 08:00
    ({"stromverbrauch_kwh": (None, None), "heizenergie_kwh": (11, None)}, False),   # Strom ohne Wärme senkt nur
    ({"stromverbrauch_kwh": (8, None)}, False),                                       # keine Wärme
    ({"strom_heizen_kwh": (8, None), "strom_warmwasser_kwh": (None, None), "warmwasser_kwh": (None, None)}, False),
])
def test_a1_zeitraum_versetzt(fenster, soll):
    assert zeitraum_versetzt(fenster) is soll


# ── A1: Bestandstag über die Route (Tagesränder aus Zählerständen) ────────────────────────────────────────────────────

TAG = date(2025, 7, 15)
T0 = datetime.combine(TAG, datetime.min.time())


async def _bestand_tag(db, *, strom_ab: int, waerme_ab: int):
    from backend.api.routes.energie_profil.views import get_tag_detail
    from backend.models import Anlage, Investition
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.models.tages_energie_profil import TagesZusammenfassung

    a = Anlage(anlagenname="A1", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2025, 1, 1),
                      anschaffungskosten_gesamt=1000.0, parameter={"wp_art": "luft_wasser"})
    db.add(inv)
    await db.flush()
    felder = {}
    for feld, ab, kwh_h in (("stromverbrauch_kwh", strom_ab, 0.8), ("heizenergie_kwh", waerme_ab, 2.4)):
        felder[feld] = {"strategie": "sensor", "sensor_id": f"sensor.{feld}"}
        for h, wert in ((ab, 1000.0), (24, 1000.0 + kwh_h * (24 - ab))):
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{inv.id}:{feld}", zeitpunkt=T0 + timedelta(hours=h),
                                  wert_kwh=wert, quelle="ha_statistics"))
    a.sensor_mapping = {"investitionen": {str(inv.id): {"felder": felder}}}
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG,
                                komponenten_kwh={f"waermepumpe_{inv.id}": 0.8 * (24 - strom_ab)}))
    await db.commit()
    return await get_tag_detail(a.id, TAG, db)


async def test_a1_bestandstag_strom_spaeter_als_waerme_zeigt_keine_arbeitszahl(db):
    r = await _bestand_tag(db, strom_ab=8, waerme_ab=0)
    # vorher 4,5 (57,6 ÷ 12,8) ohne Grund
    assert r.wp_jaz is None and r.wp_jaz_grund == GRUND_ZEITRAUM
    assert r.wp_waerme_kwh == pytest.approx(57.6)                    # die Kachel zeigt weiter die gemessene Wärme
    assert [(g.jaz, g.jaz_grund) for g in r.wp_geraete] == [(None, GRUND_ZEITRAUM)]


async def test_a1_bestandstag_gleicher_zeitraum_bleibt_eine_zahl(db):
    r = await _bestand_tag(db, strom_ab=8, waerme_ab=8)
    assert r.wp_jaz == pytest.approx(3.0) and r.wp_jaz_grund is None


# ── A1: Kanal-Tag über die Route (Welt der Löschen-Proben) ────────────────────────────────────────────────────────────

from backend.tests import test_sensorwechsel_wegb_loeschen_proben as P  # noqa: E402
from backend.tests.test_sensorwechsel_wegb_loeschen_proben import stehende_uhr  # noqa: E402,F401 — Fixture


async def test_a1_kanal_tag_nach_loeschen_am_wp_stromfeld(db, monkeypatch, stehende_uhr):  # noqa: F811
    """«löschen» am WP-Stromfeld am 04.11. 10:20, der neue Sensor führt Stände ab 08:00: der Teil-Tag rechnet mit der
    Wärme ab 08:00 (38,4 ÷ 6,4 = 6,0 statt 57,6 ÷ 6,4 = 9,0) — dieselbe Zahl wie der volle Folgetag desselben Sensors."""
    from sqlalchemy.orm.attributes import flag_modified

    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.models.investition import Investition
    from backend.services.kanal import merken

    wps, wph = "sensor.wp_strom", "sensor.wp_heiz"
    e_neu = datetime(2026, 11, 4, 8)
    v = P.ep(P.START) - 5 * P.STUNDE
    monkeypatch.setitem(P.FELDER, "wp", ("4", "stromverbrauch_kwh", "inv:4:stromverbrauch_kwh", "waermepumpe_4"))
    serien = {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), P.WB: (v, lambda _e: 1.32),
              P.NEU: (P.ep(e_neu), lambda _e: 0.4), P.C: (P.ep(e_neu), lambda _e: 0.3),
              wps: (v, lambda _e: 0.8), wph: (v, lambda _e: 2.4)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=True)
    db.add(Investition(id=4, anlage_id=w.a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1)))
    a = await P.anlage(w)
    m = json.loads(json.dumps(a.sensor_mapping))
    m["investitionen"]["4"] = {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": wps},
                                          "heizenergie_kwh": {"strategie": "sensor", "sensor_id": wph}}}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    P.frisch(w)
    await P._bis_zum_wechsel(w, P.T0)
    await P.loeschen(w, P.T0, "inv_energy_4_stromverbrauch_kwh", quelle="ha_app", entity_id=P.NEU)
    await P._nach_dem_wechsel(w, P.T0)

    async def tag(d):
        P.frisch(w)
        merken.invalidiere(w.a.id)
        r = await get_tag_detail(anlage_id=w.a.id, datum=d, db=w.db)
        await w.db.commit()
        return r

    teil = await tag(date(2026, 11, 4))
    assert teil.wp_abdeckung_hinweis == "gemessen ab 08:00 Uhr"
    assert teil.wp_waerme_kwh == pytest.approx(57.6)                 # Kachel: die gemessene Wärme des Tages
    assert (teil.wp_jaz_zaehler_kwh, teil.wp_jaz_nenner_kwh) == (pytest.approx(38.4), pytest.approx(6.4))
    assert teil.wp_jaz == pytest.approx(6.0)                         # vorher 9,0
    assert [g.jaz for g in teil.wp_geraete] == [pytest.approx(6.0)]


# ── A2: Wärme ohne Strom ─────────────────────────────────────────────────────────────────────────────────────────────

PARAM = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "jaz": 3.5, "alter_energietraeger": "gas",
         "alter_preis_cent_kwh": 12.13, "alternativ_zusatzkosten_jahr": 662.28}
PREIS = 31.69


def _jf(wps, imd):
    from backend.core.berechnungen.alternativkosten import berechne_wp_alternativkosten_ersparnis

    return berechne_wp_alternativkosten_ersparnis(wps, imd, {}, {(j, m): PREIS for (_i, j, m) in imd}, PREIS)


def _zeile(daten) -> float:
    from backend.services.wp_wirtschaftlichkeit import wp_ersparnis_zeile

    z = wp_ersparnis_zeile(waerme_kwh=daten.get("heizenergie_kwh"), strom_kwh=daten.get("stromverbrauch_kwh"),
                           strom_kuehlen_kwh=0.0, strompreis_cent=PREIS, parameter=PARAM, gaspreis_cent=None,
                           null_ist_kein_betrieb=True)
    return z.ersparnis_euro if z is not None else 0.0


@pytest.mark.parametrize("daten", [{"heizenergie_kwh": 400.0, "stromverbrauch_kwh": 0.0}, {"heizenergie_kwh": 400.0}])
def test_a2_waerme_ohne_strom_traegt_keine_ersparnis_und_kein_zwoelftel(daten):
    wp = SimpleNamespace(id=1, parameter=PARAM)
    assert _jf([wp], {(1, 2026, 7): daten}) == 0.0                   # vorher 109,10 € (Gas 53,91 + Zwölftel 55,19)
    assert _zeile(daten) == 0.0


def test_a2_sammelaufruf_gleich_summe_der_gerätezeilen_mit_einem_monat_ohne_strom():
    a, b = SimpleNamespace(id=1, parameter=PARAM), SimpleNamespace(id=2, parameter=PARAM)
    imd = {(1, 2026, 6): {"heizenergie_kwh": 400.0, "stromverbrauch_kwh": 100.0},
           (1, 2026, 7): {"heizenergie_kwh": 400.0},
           (2, 2026, 7): {"heizenergie_kwh": 300.0, "stromverbrauch_kwh": 80.0}}
    gesamt = _jf([a, b], imd)
    assert gesamt == pytest.approx(_jf([a], imd) + _jf([b], imd), abs=1e-9)
    assert gesamt == pytest.approx(sum(_zeile(d) for d in imd.values()), abs=1e-9)


@pytest.mark.parametrize("daten", [{"heizenergie_kwh": 400.0, "stromverbrauch_kwh": 0.0}, {"heizenergie_kwh": 400.0}])
async def test_a2_export_sensor_je_waermepumpe_ohne_strom_leer(db, daten):
    from sqlalchemy import select

    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

    a = Anlage(anlagenname="A2", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     aktiv=True, anschaffungskosten_gesamt=15000, parameter=dict(PARAM))
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=7, verbrauch_daten=dict(daten)))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=7, einspeisung_kwh=0, netzbezug_kwh=100))
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=PREIS, einspeiseverguetung_cent_kwh=8.0))
    await db.commit()
    sp = (await db.execute(select(Strompreis).where(Strompreis.anlage_id == a.id))).scalar_one()
    svs = await calculate_investition_sensors(db, wp, sp)
    # vorher 109,10 €; ohne bewertbaren Monat entsteht der Sensor nicht (wie ohne ersetzte Heizung, N-88)
    assert [s.value for s in svs if s.definition.key == "wp_ersparnis_euro"] == []


# ── A3: USt je Komponente über ihre aktiven Monate ──────────────────────────────────────────────────────────────────

def _inv(id_, gesamt, bk, ab, bis=None):
    from backend.models import Investition

    return Investition(id=id_, anlage_id=1, typ="pv-module" if id_ == 1 else "speicher", bezeichnung=str(id_),
                       anschaffungskosten_gesamt=gesamt, betriebskosten_jahr=bk, anschaffungsdatum=ab,
                       stilllegungsdatum=bis, aktiv=True)


def _fakten(jahr, monate, ev, pv):
    meta = SimpleNamespace(hat_zaehlerzeile=True, netz_erfasst=True, erzeuger_aktiv=True)
    return [SimpleNamespace(jahr=jahr, monat=m, meta=meta,
                            kennzahlen=SimpleNamespace(eigenverbrauch_kwh=ev / len(monate)),
                            erzeugung=SimpleNamespace(wandlungsverluste_kwh=None, verluste_grund=None,
                                                      pv_kwh=pv / len(monate)))
            for m in monate]


ANLAGE_REGEL = SimpleNamespace(steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0)


@pytest.mark.parametrize("speicher", [
    (date(2026, 7, 1), None),                      # Anschaffung im Juli
    (date(2020, 1, 1), date(2026, 6, 30)),         # Stilllegung Ende Juni
])
def test_a3_ust_zaehlt_die_kosten_einer_komponente_nur_ueber_ihre_aktiven_monate(speicher):
    from backend.services.ust_satz import ust_eigenverbrauch_zeitraum, ust_satz_des_jahres

    invs = [_inv(1, 20000.0, 0, date(2024, 1, 1)), _inv(2, 6000.0, 120.0, *speicher)]
    f = _fakten(2026, range(1, 13), 3000.0, 10000.0)
    # (1 000 × 12 + 420 × 6) / 12 = 1 210 € ⇒ 12,1 ct/kWh × 3 000 kWh × 19 % — vorher 1 420 € ⇒ 80,94 €
    assert round(ust_eigenverbrauch_zeitraum(ANLAGE_REGEL, invs, f), 2) == 68.97
    satz = ust_satz_des_jahres(ANLAGE_REGEL, invs, f, 2026)
    assert satz.euro_je_kwh * 3000.0 == pytest.approx(ust_eigenverbrauch_zeitraum(ANLAGE_REGEL, invs, f))


def test_a3_ganzjaehrige_komponenten_unveraendert():
    from backend.services.ust_satz import ust_eigenverbrauch_zeitraum

    invs = [_inv(1, 20000.0, 0, date(2024, 1, 1)), _inv(2, 6000.0, 120.0, date(2020, 1, 1))]
    assert round(ust_eigenverbrauch_zeitraum(ANLAGE_REGEL, invs, _fakten(2026, range(1, 13), 3000.0, 10000.0)), 2) \
        == 80.94


def test_a3_komponente_ausserhalb_der_monate_des_jahresanteils_traegt_nichts():
    """Laufendes Jahr mit Abschlüssen Januar–Juni, Speicher ab Juli: er trägt in diesem Satz nichts."""
    from backend.services.ust_satz import ust_eigenverbrauch_zeitraum

    nur_pv = [_inv(1, 20000.0, 0, date(2024, 1, 1))]
    mit_speicher = nur_pv + [_inv(2, 6000.0, 120.0, date(2026, 7, 1))]
    f = _fakten(2026, range(1, 7), 1500.0, 5000.0)
    assert ust_eigenverbrauch_zeitraum(ANLAGE_REGEL, mit_speicher, f) == ust_eigenverbrauch_zeitraum(ANLAGE_REGEL, nur_pv, f)


# ── A4: Prognose ohne stillgelegte Wärmepumpen ──────────────────────────────────────────────────────────────────────

async def _prognose(db, zusatz_a: float):
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

    anlage = Anlage(anlagenname="A4", leistung_kwp=10.0, latitude=48.0, installationsdatum=date(2020, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, netzbezug_arbeitspreis_cent_kwh=PREIS,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2020, 1, 1)))
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m, netzbezug_kwh=100.0, einspeisung_kwh=0.0))
    for name, ab, bis, monate, zus in (("WP A", date(2025, 1, 1), date(2025, 6, 30), range(1, 7), zusatz_a),
                                       ("WP B", date(2025, 7, 1), None, range(7, 13), 600.0)):
        inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung=name, anschaffungsdatum=ab,
                          stilllegungsdatum=bis, anschaffungskosten_gesamt=20000.0,
                          parameter={**PARAM, "alternativ_zusatzkosten_jahr": zus})
        db.add(inv)
        await db.flush()
        for m in monate:
            db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2025, monat=m,
                                          verbrauch_daten={"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 400.0}))
    await db.commit()
    return await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)


async def test_a4_stillgelegte_waermepumpe_traegt_keine_zusatzkosten_in_die_zukunft(db):
    mit = await _prognose(db, 600.0)
    ohne = await _prognose(db, 0.0)
    # vorher lag `mit` um 600 €/Jahr darüber (gemessen 1 507,85 statt 907,85 €)
    assert mit.wp_alternativ_ersparnis_euro == pytest.approx(ohne.wp_alternativ_ersparnis_euro)
    assert mit.jahres_netto_ertrag_euro == pytest.approx(ohne.jahres_netto_ertrag_euro)


def test_a4_layer_nur_heute_aktive_mit_ersatz():
    from backend.core.berechnungen.alternativkosten import wp_zusatzkosten_jahr_heute

    def wp(zus, aktiv, traeger="gas"):
        return SimpleNamespace(parameter={"alternativ_zusatzkosten_jahr": zus, "alter_energietraeger": traeger},
                               ist_aktiv_im_monat=lambda j, m, a=aktiv: a)
    assert wp_zusatzkosten_jahr_heute([wp(600, False), wp(300, True), wp(200, True, "nichts")], date(2026, 11, 22)) == 300
