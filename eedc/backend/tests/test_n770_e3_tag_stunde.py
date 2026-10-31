"""N-770 / N-771 E3 — Tag und Stunde mit gemessenem Netzbezug zum WP-Tarif (Bauplan F5 mit F9 = A, F6, F10).

Die Stunden des Felds «Netzbezug zum WP-Tarif» kommen NUR aus seinem Kanal ``inv:<id>:netzbezug_eigener_tarif_kwh``
(F9 = A, Entscheid Gernot 31.10.2026). Deckt der Kanal den Monat und setzt der Monat den Anteil an, rechnet jede Stunde
``(Netzbezug_h − N_h) × H_h + N_h × W_h`` und die EV-Ersparnis je Tag P_d = S_d − N_d zum WP-Tarif — Σ Tage = Monat
(Stromrechnung und EV-Ersparnis), auch mit HT/NT an Haushalts- und WP-Tarif (F6: Haushaltspreis über Netzbezug − N,
WP-Tarif über N gewichtet).

Testmonat Juni 2025 (keine Zeitumstellung in Berlin, UTC, Auckland), 30 Bestandstage. Je Stunde mit Beginn h:
Netzbezug 1 kWh; N = 0,5 und WP-Strom 0,8 für 1 ≤ h ≤ 21 (sonst 0 — damit die Randstunde 23:00, in der das
Bestandstagesfenster [Vortag 23:00, 23:00) und der Kalendermonat auseinanderliegen, nichts trägt); PV 2 kWh für 10 ≤ h ≤ 14
(Einspeisung 0). Monat: Netzbezug 720, S = 504, N = 315, P = 189, EV = 300. Tarife: Haushalt 30 ct (NT 22–06: 20 ct),
WP 22 ct (NT 22–06: 15 ct), Grundpreise 14 + 10 €.

Sprengsatz (im Bericht gefahren): ``tage_netzanteil.netzanteile_der_tage`` liefert leer (N_h im Tagespfad ignoriert)
⇒ die Σ-Proben mit Feld rot.

Schwesterdateien: test_n770_netzbezug_komponenten_tarif.py (Monat, E1–E2), test_n770_e4_prognose_roi.py,
test_n771_f11_wallbox_netzladung.py, test_n767_wp_eigener_tarif.py (Daten-Checker), test_tage_werte_symmetrie.py.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.strompreis import StrompreisZeitfenster
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.tage_werte import baue_tage_werte
from backend.services.monats_fakten import lade_monats_fakten

J, M = 2025, 6
TAGE = calendar.monthrange(J, M)[1]
H, H_NT, W, W_NT = 30.0, 20.0, 22.0, 15.0


def _n(h: int) -> float:
    return 0.5 if 1 <= h <= 21 else 0.0


def _wp(h: int) -> float:
    return 0.8 if 1 <= h <= 21 else 0.0


def _pv(h: int) -> float:
    return 2.0 if 10 <= h <= 14 else 0.0


async def _anlage(db, *, mit_feld: bool = True, kanal_ab: date | None = date(J, 5, 31), zeitfenster: bool = True,
                  monatswert_n: float | None = None) -> Anlage:
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-770 E3", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    allg = Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=H, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=14.0)
    wpt = Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1),
                     netzbezug_arbeitspreis_cent_kwh=W, einspeiseverguetung_cent_kwh=0.0, grundpreis_euro_monat=10.0)
    db.add_all([allg, wpt])
    await db.flush()
    if zeitfenster:
        db.add(StrompreisZeitfenster(strompreis_id=allg.id, von_stunde=22, bis_stunde=6, arbeitspreis_cent_kwh=H_NT))
        db.add(StrompreisZeitfenster(strompreis_id=wpt.id, von_stunde=22, bis_stunde=6, arbeitspreis_cent_kwh=W_NT))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"effizienz_modus": "gesamt_jaz", "jaz": 3.5})
    db.add_all([pv, wp])
    await db.flush()
    s_monat = sum(_wp(h) for h in range(24)) * TAGE
    n_monat = sum(_n(h) for h in range(24)) * TAGE
    vd = {"stromverbrauch_kwh": s_monat, "heizenergie_kwh": s_monat * 3.5}
    if mit_feld:
        vd["netzbezug_eigener_tarif_kwh"] = n_monat if monatswert_n is None else monatswert_n
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=J, monat=M, verbrauch_daten=vd))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=J, monat=M,
                                  verbrauch_daten={"pv_erzeugung_kwh": sum(_pv(h) for h in range(24)) * TAGE}))
    md = Monatsdaten(anlage_id=anlage.id, jahr=J, monat=M, netzbezug_kwh=24.0 * TAGE, einspeisung_kwh=0.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    # Stundenzeilen: Backward-Slot s des Tages D trägt die Stunde mit Beginn s−1 (Slot 0 = Vortag 23:00).
    for tag in [date(J, M, 1) + timedelta(days=i) for i in range(TAGE)]:
        for s in range(24):
            h = (s - 1) % 24
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=s, pv_kw=_pv(h), einspeisung_kw=0.0,
                                      netzbezug_kw=1.0, verbrauch_kw=1.0 + _pv(h), waermepumpe_kw=_wp(h)))
    if kanal_ab is not None:
        k = Kanal(anlage_id=anlage.id, key=f"inv:{wp.id}:netzbezug_eigener_tarif_kwh", einheit="kWh", art="sum")
        db.add(k)
        await db.flush()
        t0 = datetime.combine(kanal_ab, datetime.min.time())
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(t0.timestamp()), familie="spiegel", offset=0.0))
        summe, t = 0.0, t0
        while t < datetime(J, M + 1, 1, 1):
            summe += _n(t.hour)
            db.add(KanalStatistik(kanal_id=k.id, start_ts=int(t.timestamp()), sum=summe, familie="spiegel"))
            t += timedelta(hours=1)
    await db.commit()
    return anlage


async def _monat(db, anlage):
    return await get_aktueller_monat(anlage.id, J, M, db)


async def _tage(db, anlage):
    return await baue_tage_werte(db, anlage, date(J, M, 1), date(J, M, TAGE))


def _h(h: int, zf: bool) -> float:
    return H_NT if zf and (h >= 22 or h < 6) else H


def _w(h: int, zf: bool) -> float:
    return W_NT if zf and (h >= 22 or h < 6) else W


@pytest.mark.parametrize("zf", [False, True], ids=["festpreis", "ht_nt"])
async def test_summe_der_tage_gleich_monat_mit_feld(db, zf):
    """Σ Tage == Monat: Stromrechnung (Arbeitspreis) und EV-Ersparnis — mit Feld und Kanal, mit und ohne HT/NT."""
    anlage = await _anlage(db, zeitfenster=zf)
    monat = await _monat(db, anlage)
    tage = await _tage(db, anlage)
    soll = TAGE * sum((1.0 - _n(h)) * _h(h, zf) + _n(h) * _w(h, zf) for h in range(24)) / 100
    assert monat.netzbezug_arbeitspreis_kosten_euro == pytest.approx(soll, abs=0.01)
    assert sum(t.netzbezug_kosten for t in tage) == pytest.approx(soll, abs=1e-6)
    assert sum(t.ev_ersparnis for t in tage) == pytest.approx(monat.ev_ersparnis_euro, abs=0.01)
    assert monat.netzbezug_anteile and monat.netzbezug_anteile[0]["kwh"] == pytest.approx(315.0)


@pytest.mark.parametrize("zf", [False, True], ids=["festpreis", "ht_nt"])
async def test_ohne_feld_bitgleich_und_summe_gleich_monat(db, zf):
    anlage = await _anlage(db, mit_feld=False, kanal_ab=None, zeitfenster=zf)
    monat = await _monat(db, anlage)
    tage = await _tage(db, anlage)
    assert monat.netzbezug_anteile is None
    soll = TAGE * sum(_h(h, zf) for h in range(24)) / 100
    assert sum(t.netzbezug_kosten for t in tage) == pytest.approx(soll, abs=1e-6)
    assert monat.netzbezug_arbeitspreis_kosten_euro == pytest.approx(soll, abs=0.01)


async def test_f6_haushaltspreis_ueber_netzbezug_minus_n_wp_tarif_ueber_n(db):
    anlage = await _anlage(db, zeitfenster=True)
    (fakt,) = [f for f in await lade_monats_fakten(db, anlage.id) if (f.jahr, f.monat) == (J, M)]
    f6 = fakt.tarif.netzanteil_preise
    rest = [(1.0 - _n(h), _h(h, True)) for h in range(24)]
    assert f6.haushalt_rest(["waermepumpe"]) == pytest.approx(sum(k * p for k, p in rest) / sum(k for k, _ in rest), abs=1e-4)
    ns = [(_n(h), _w(h, True)) for h in range(24)]
    assert f6.komponente("waermepumpe") == pytest.approx(sum(k * p for k, p in ns) / sum(k for k, _ in ns), abs=1e-4)
    # Kopfzahl bleibt der Haushaltspreis über den ganzen Netzbezug.
    assert fakt.tarif.netzbezug_preis_cent == pytest.approx(sum(_h(h, True) for h in range(24)) / 24, abs=1e-4)


async def test_zuordnungsmonat_nicht_gemessen(db):
    """F10: beginnt der Kanal des Felds im Monat, gilt der Monat als nicht gemessen — auch mit Monatswert."""
    anlage = await _anlage(db, kanal_ab=date(J, M, 15))
    (fakt,) = [f for f in await lade_monats_fakten(db, anlage.id) if (f.jahr, f.monat) == (J, M)]
    assert fakt.wp.netz_eigener_tarif_kwh is None
    monat = await _monat(db, anlage)
    assert monat.netzbezug_anteile is None
    tage = await _tage(db, anlage)
    assert sum(t.netzbezug_kosten for t in tage) == pytest.approx(TAGE * sum(_h(h, True) for h in range(24)) / 100)


async def test_monatswert_ohne_kanal_monat_wie_e2_tage_ungeteilt(db):
    """F9-Grenze: ohne Kanal gilt der Monatswert (E2), die Tage teilen nicht — Σ Tage ≠ Monat (benannt)."""
    anlage = await _anlage(db, kanal_ab=None, zeitfenster=False)
    monat = await _monat(db, anlage)
    assert monat.netzbezug_anteile[0]["kwh"] == pytest.approx(315.0)
    tage = await _tage(db, anlage)
    assert sum(t.netzbezug_kosten for t in tage) == pytest.approx(TAGE * 24 * H / 100)
    assert monat.netzbezug_arbeitspreis_kosten_euro == pytest.approx((720 - 315) * H / 100 + 315 * W / 100, abs=0.01)


async def test_klemme_des_monats_folgt_in_den_stunden(db):
    """F7: ist N im Monat geklemmt (Monatswert 630 > S = 504), tragen die Stunden die Klemme im Verhältnis
    angesetzt ÷ gemessen (504 ÷ 630) — der Kanal (315) bleibt die Stundenform."""
    anlage = await _anlage(db, zeitfenster=False, monatswert_n=630.0)    # Monatswert > S = 504 ⇒ auf 504 geklemmt
    monat = await _monat(db, anlage)
    a = monat.netzbezug_anteile[0]
    assert a["geklemmt"] and a["kwh"] == pytest.approx(504.0)
    tage = await _tage(db, anlage)
    # Stunden: Kanal 315 kWh × (504 / 630) = 252 kWh zum WP-Tarif.
    assert sum(t.netzbezug_kosten for t in tage) == pytest.approx(
        (720 - 252) * H / 100 + 252 * W / 100, abs=1e-6)


async def test_cockpit_laufender_monat_ohne_fakt_aus_kanal_zeile(db):
    """Laufender Monat ohne Abschluss: N aus der Kanal-Zeile der WP-Gruppe, Tarif über ``tarif_des_monats``."""
    from backend.api.routes.aktueller_monat.finanzen import komponenten_anteile_des_monats
    from backend.services.monats_fakten.fakten_wp import WpFakten

    anlage = await _anlage(db, zeitfenster=False)
    wp = WpFakten(strom_kwh=504.0, netz_eigener_tarif_kwh=315.0)
    a = await komponenten_anteile_des_monats(db, anlage.id, J, M, None, wp, 720.0)
    assert a is not None and a.netz[0].kwh == pytest.approx(315.0) and a.netz[0].cent == pytest.approx(W)
    assert a.wp_pv_kwh == pytest.approx(189.0)
    assert await komponenten_anteile_des_monats(db, anlage.id, J, M, None, WpFakten(strom_kwh=504.0), 720.0) is None
