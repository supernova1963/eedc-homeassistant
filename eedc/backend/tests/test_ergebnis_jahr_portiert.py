"""Die Faltungs-Proben des Clients — umgezogen mit der Faltung (Paket „Ergebnisgrößen", 03.10.2026, Vorlage B4).

Bis 03.10.2026 faltete ``v4/JahrAggregat.tsx`` die Monatsantworten eines Jahres im Browser; elf Vitest-Dateien
prüften diese Faltung. Mit dem Umzug in den Layer (``core/berechnungen/ergebnis.py::falte_zeitraum``) und die
Aufbereitung (``services/jahres_aggregat.py``) wandert ihre Substanz hierher — **mit denselben Zahlen**, je Probe der
Herkunftsort in Klammern. Keine Probe verschwindet ohne Nachfolger (Liste alt → neu im Baubericht).

Bewusst geändert gegenüber dem Client sind genau die Regeln der Vorlage: Quoten paarweise (N-584) — in den
übernommenen Proben ohne Wirkung, weil ihre Monate beide Größen tragen — und das Ø-Jahr als Quote der gemittelten
paarweisen Mengen statt Mittel der Prozente (dort mit eigener Probe in ``test_ergebnis_leiter.py``).

Schwesterdateien: test_ergebnis_leiter.py (Regeln der Leiter), test_ergebnis_symmetrie_monat_jahr.py (W3),
test_n584_jahr_grundgesamtheit.py (P1).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.ergebnis import falte_zeitraum, jahr_vergleich_aus, mittel_jahre
from backend.services.jahres_aggregat import abgeschlossene_monate, monat_hat_daten, zu_ladende_monate


def _m(monat: int, **felder):
    return {"jahr": 2025, "monat": monat, **felder}


# ── Tarif-Zeile (JahrAggregat.preise.test.tsx) ──────────────────────────────────────────────────────────────────────

def test_einspeise_durchschnittspreis_wird_gefaltet():
    """N-610-Nacharbeit: der gepflegte Einspeise-Ø des Monats (`einspeise_durchschnittspreis_cent`, bis dahin nur im
    Vorjahres-Block) steht auch im Jahr — einspeisegewichtet über den aufgelösten Satz, sobald ein Monat ihn trägt (dieselbe
    Regel wie `netzbezug_durchschnittspreis_cent`); ohne Pflege in keinem Monat bleibt er None."""
    j = falte_zeitraum([_m(1, einspeisung_kwh=100, einspeise_preis_cent=10, einspeise_durchschnittspreis_cent=10),
                        _m(2, einspeisung_kwh=300, einspeise_preis_cent=8)], 2025)
    assert j["einspeise_durchschnittspreis_cent"] == pytest.approx((100 * 10 + 300 * 8) / 400)
    ohne = falte_zeitraum([_m(1, einspeisung_kwh=100, einspeise_preis_cent=8)], 2025)
    assert ohne["einspeise_durchschnittspreis_cent"] is None


def test_preise_netzbezug_mengengewichtet():
    j = falte_zeitraum([_m(1, netzbezug_kwh=400, netzbezug_preis_cent=40),
                        _m(7, netzbezug_kwh=100, netzbezug_preis_cent=20)], 2025)
    assert j["netzbezug_preis_cent"] == pytest.approx(36, abs=1e-6)  # ungewichtet wären es 30
    assert j["netzbezug_kwh"] == 500


def test_preise_einspeisung_mengengewichtet():
    j = falte_zeitraum([_m(1, einspeisung_kwh=50, einspeise_preis_cent=8),
                        _m(7, einspeisung_kwh=450, einspeise_preis_cent=12)], 2025)
    assert j["einspeise_preis_cent"] == pytest.approx(11.6, abs=1e-6)


def test_preise_monat_ohne_menge_verduennt_nicht():
    j = falte_zeitraum([_m(1, netzbezug_kwh=300, netzbezug_preis_cent=30),
                        _m(2, netzbezug_kwh=None, netzbezug_preis_cent=99)], 2025)
    assert j["netzbezug_preis_cent"] == pytest.approx(30, abs=1e-6)


def test_preise_ohne_jede_menge_monatsmittel():
    j = falte_zeitraum([_m(1, netzbezug_kwh=0, netzbezug_preis_cent=30),
                        _m(2, netzbezug_kwh=0, netzbezug_preis_cent=40)], 2025)
    assert j["netzbezug_preis_cent"] == pytest.approx(35, abs=1e-6)


def test_preise_durchschnittspreis_vor_tarif():
    j = falte_zeitraum([
        _m(1, netzbezug_kwh=100, netzbezug_preis_cent=30, netzbezug_durchschnittspreis_cent=22),
        _m(2, netzbezug_kwh=100, netzbezug_preis_cent=30, netzbezug_durchschnittspreis_cent=26),
    ], 2025)
    assert j["netzbezug_preis_cent"] == pytest.approx(24, abs=1e-6)
    assert j["netzbezug_durchschnittspreis_cent"] == pytest.approx(24, abs=1e-6)


def test_preise_ohne_durchschnittspreis_leer():
    j = falte_zeitraum([_m(1, netzbezug_kwh=100, netzbezug_preis_cent=30)], 2025)
    assert j["netzbezug_durchschnittspreis_cent"] is None
    assert j["netzbezug_preis_cent"] == pytest.approx(30, abs=1e-6)


# ── Speicher-η (JahrAggregat.speicherEta.test.tsx, N-252) ─────────────────────────────────────────────────────────

def _sp(m, ladung, entladung):
    return _m(m, speicher_ladung_kwh=ladung, speicher_entladung_kwh=entladung, hat_speicher=True)


def test_speicher_eta_plausibel_mit_langem_fenster():
    j = falte_zeitraum([_sp(1, 100, 88), _sp(2, 100, 90)], 2026)
    assert j["speicher_wirkungsgrad_prozent"] == pytest.approx(89, abs=1e-6)
    assert j["speicher_wirkungsgrad_quelle"] == "fenster_lang"


def test_speicher_eta_ueber_100_kein_wert():
    j = falte_zeitraum([_sp(1, 100, 110), _sp(2, 100, 104)], 2026)
    assert j["speicher_wirkungsgrad_prozent"] is None
    assert j["speicher_wirkungsgrad_quelle"] == "nicht-ermittelbar"


def test_speicher_eta_ohne_ladung():
    j = falte_zeitraum([_sp(1, 0, 0)], 2026)
    assert j["speicher_wirkungsgrad_prozent"] is None
    assert j["speicher_wirkungsgrad_quelle"] == "keine-ladung"


def test_speicher_eta_genau_100_ist_moeglich():
    j = falte_zeitraum([_sp(1, 100, 100)], 2026)
    assert j["speicher_wirkungsgrad_prozent"] == pytest.approx(100, abs=1e-6)
    assert j["speicher_wirkungsgrad_quelle"] == "fenster_lang"


# ── E-Mobilität (JahrAggregat.emob.test.tsx, N-557) ───────────────────────────────────────────────────────────────

def _em(m, heim, extern, km, fahrverbrauch):
    gesamt = heim + extern
    return _m(m, emob_ladung_kwh=heim, emob_ladung_extern_kwh=extern, emob_ladung_gesamt_kwh=gesamt, emob_km=km,
              emob_verbrauch_quelle="gemessen" if fahrverbrauch is not None else "ladung",
              emob_verbrauch_basis_kwh=fahrverbrauch if fahrverbrauch is not None else gesamt,
              hat_emobilitaet=True)


_EM_JAHR = [_em(m, 250, 50, 1500, None) for m in range(1, 7)] + [_em(m, 250, 50, 1500, 270) for m in range(7, 13)]


def test_emob_jahresquote_aus_monatswerten():
    j = falte_zeitraum(_EM_JAHR, 2025)
    assert j["emob_verbrauch_100km"] == pytest.approx(19.0, abs=1e-6)  # alte Formel: 16,7


def test_emob_gemessen_nur_wenn_jeder_monat_gemessen():
    assert falte_zeitraum(_EM_JAHR, 2025)["emob_verbrauch_quelle"] == "ladung"
    alle = falte_zeitraum([_em(7, 250, 0, 1500, 270), _em(8, 250, 0, 1000, 180)], 2025)
    assert alle["emob_verbrauch_quelle"] == "gemessen"
    assert alle["emob_verbrauch_100km"] == pytest.approx(18.0, abs=1e-6)


def test_emob_ladung_gesamt_heim_plus_extern():
    j = falte_zeitraum(_EM_JAHR, 2025)
    assert j["emob_ladung_gesamt_kwh"] == 3600
    assert j["emob_ladung_kwh"] == 3000


# ── WP-Kennzahlen der Übersicht (JahrAggregat.b4.test.tsx, wpFunktionsGruppen.test.tsx) ───────────────────────────

_WP = [_m(7, hat_waermepumpe=True, wp_strom_kwh=1000, wp_waerme_kwh=3500, wp_heizung_kwh=3500,
          wp_modus_strom_heizen_kwh=700, wp_modus_strom_kuehlen_kwh=250, wp_modus_strom_lueften_kwh=10,
          wp_modus_strom_entfeuchten_kwh=5, wp_modus_abdeckung_h=0, wp_modus_gemessen=True)]
_ROUTE = dict(
    wp_cop=3.5, wp_cop_grund=None, wp_cop_hinweis="HEIZSTAB", wp_jaz_zaehler_kwh=3500, wp_jaz_nenner_kwh=735,
    wp_waerme_abgeleitet=False, wp_waerme_herkunft="gemessen", wp_ersparnis_vorbehalt=None,
    wp_jaz_heizen=None, wp_jaz_heizen_grund="Strom nicht getrennt je Funktion gemessen",
    wp_jaz_warmwasser=None, wp_jaz_warmwasser_grund="Strom nicht getrennt je Funktion gemessen",
    wp_jaz_kuehlen=3.0, wp_jaz_kuehlen_grund=None,
    wp_modus_strom_lueften_kwh=10, wp_modus_strom_entfeuchten_kwh=5, wp_modus_strom_bezug_kwh=1000,
    wp_modus_nicht_aufgeteilt_kwh=35,
)


def test_wp_kennzahlen_aus_der_route():
    j = falte_zeitraum(_WP, 2025, _ROUTE)
    assert j["wp_jaz"] == 3.5 and j["wp_jaz_hinweis"] == "HEIZSTAB"
    assert j["wp_jaz_zaehler_kwh"] == 3500 and j["wp_jaz_nenner_kwh"] == 735
    assert j["wp_jaz_heizen_grund"] == "Strom nicht getrennt je Funktion gemessen"
    assert j["wp_jaz_kuehlen"] == 3.0 and j["wp_waerme_herkunft"] == "gemessen"
    assert j["wp_strom_kwh"] == 1000 and j["wp_modus_strom_heizen_kwh"] == 700


def test_wp_restmenge_aus_dem_layer():
    j = falte_zeitraum(_WP, 2025, _ROUTE)
    assert j["wp_modus_nicht_aufgeteilt_kwh"] == 35
    assert j["wp_modus_strom_lueften_kwh"] == 10 and j["wp_modus_strom_bezug_kwh"] == 1000


def test_wp_ohne_route_mengen_ja_kennzahlen_nein():
    j = falte_zeitraum(_WP, 2025, None)
    assert j["wp_jaz"] is None and j["wp_jaz_kuehlen"] is None
    assert j["wp_strom_kwh"] == 1000
    assert j["wp_modus_nicht_aufgeteilt_kwh"] == 50  # der alte Rest kannte E4 nie


def test_kaelte_aus_der_route_oder_summe():
    monate = [dict(jahr=2026, monat=7, wp_kaelte_kwh=400), dict(jahr=2026, monat=8, wp_kaelte_kwh=500)]
    assert falte_zeitraum(monate, 2026, {"wp_kaelte_kwh": 888})["wp_kaelte_kwh"] == 888
    assert falte_zeitraum(monate, 2026, {"wp_kaelte_kwh": None})["wp_kaelte_kwh"] is None
    assert falte_zeitraum(monate, 2026)["wp_kaelte_kwh"] == 900


# ── Grundlast (GrundlastSollIstKachel.test.tsx, R12-1) ───────────────────────────────────────────────────────────

def test_grundlast_summe_und_anteil_nur_ueber_monate_mit_daten():
    monate = [
        dict(jahr=2026, monat=1, grundlast_kw=0.4, grundlast_kwh=288, gesamtverbrauch_kwh=1000),
        dict(jahr=2026, monat=2, grundlast_kw=0.5, grundlast_kwh=372, gesamtverbrauch_kwh=900),
        dict(jahr=2026, monat=3, grundlast_kw=None, grundlast_kwh=None, gesamtverbrauch_kwh=500),
    ]
    j = falte_zeitraum(monate, 2026)
    assert j["grundlast_kwh"] == 660
    assert j["grundlast_kw"] == pytest.approx(0.45, abs=0.005)
    assert j["grundlast_anteil_prozent"] == pytest.approx(34.7, abs=0.05)


def test_grundlast_ohne_daten_null():
    j = falte_zeitraum([dict(jahr=2026, monat=1, grundlast_kw=None, grundlast_kwh=None)], 2026)
    assert j["grundlast_kwh"] is None and j["grundlast_anteil_prozent"] is None


# ── SOLL-Fenster (JahrSollFenster.test.tsx, N-69 — Winterborn 04.08.2026) ────────────────────────────────────────

_SOLL = [396.1, 615.7, 1052.7, 1411.8, 1466.2, 1477.2, 1509.0]
_IST = [330.11, 545.41, 1439.9, 1786.5, 1751.3, 1753.8, 1843.25]
_TAGE = [31, 28, 31, 30, 31, 30, 31]


def _jahr2026():
    monate = [dict(jahr=2026, monat=i + 1, soll_pv_kwh=s, pv_erzeugung_kwh=_IST[i], soll_pv_tage=_TAGE[i],
                   soll_pv_tage_gesamt=_TAGE[i]) for i, s in enumerate(_SOLL)]
    monate.append(dict(jahr=2026, monat=8, soll_pv_kwh=179.1, pv_erzeugung_kwh=264.75, soll_pv_tage=4,
                       soll_pv_tage_gesamt=31))
    return falte_zeitraum(monate, 2026)


def test_soll_fenster_summiert_die_tage():
    j = _jahr2026()
    assert j["soll_pv_tage"] == 216 and j["soll_pv_tage_gesamt"] == 243
    assert j["soll_pv_kwh"] == pytest.approx(8107.8, abs=0.05)


def test_soll_erfuellung_jahr_statt_104_prozent():
    j = _jahr2026()
    assert round(j["soll_erfuellung_prozent"]) == 120  # 119,8 %
    assert j["soll_fenster_text"] == "anteilig · 216 von 243 Tagen"


# ── Vergleichsjahre (JahrVergleichFenster.test.tsx, N-37) ───────────────────────────────────────────────────────

def _zeile(jahr, monat):
    return dict(jahr=jahr, monat=monat, pv_erzeugung_kwh=100, eigenverbrauch_kwh=60, direktverbrauch_kwh=40,
                einspeisung_kwh=40, netzbezug_kwh=30, gesamtverbrauch_kwh=90)


def _jz(jahr, monate):
    return [_zeile(jahr, m) for m in monate]


_BIS = lambda n: list(range(1, n + 1))  # noqa: E731


def test_vergleich_laufendes_jahr_beschnitten():
    rows = _jz(2026, _BIS(7)) + _jz(2025, _BIS(12))
    vj = jahr_vergleich_aus(rows, 2025, _BIS(7))
    assert vj["monate"] == _BIS(7) and vj["pv"] == 700 and vj["ev"] == 420
    assert vj["autarkie"] == pytest.approx(420 / 630 * 100, abs=1e-6)
    assert jahr_vergleich_aus(rows, 2025)["pv"] == 1200


def test_vergleich_luecke_im_angezeigten_jahr():
    g = [1, 2, 4, 5, 6, 7]
    vj = jahr_vergleich_aus(_jz(2026, g) + _jz(2025, _BIS(12)), 2025, g)
    assert vj["monate"] == g and vj["pv"] == 600


def test_vergleich_luecke_im_vergleichsjahr():
    vj = jahr_vergleich_aus(_jz(2026, _BIS(7)) + _jz(2025, [3, 4, 5, 6, 7]), 2025, _BIS(7))
    assert vj["monate"] == [3, 4, 5, 6, 7] and vj["pv"] == 500


def test_vergleich_abgeschlossenes_jahr_unveraendert():
    rows = _jz(2025, _BIS(12)) + _jz(2024, _BIS(12))
    assert jahr_vergleich_aus(rows, 2024, _BIS(12)) == jahr_vergleich_aus(rows, 2024)
    assert jahr_vergleich_aus(rows, 2024)["pv"] == 1200


def test_vergleich_ohne_ueberschneidung_null_nicht_0():
    vj = jahr_vergleich_aus(_jz(2026, _BIS(7)) + _jz(2025, [11, 12]), 2025, _BIS(7))
    assert vj["monate"] == [] and vj["pv"] is None and vj["autarkie"] is None


_WINTERBORN = _jz(2026, _BIS(6)) + _jz(2025, _BIS(12)) + _jz(2024, _BIS(12)) + _jz(2023, [6, 7, 8, 9, 10, 11, 12])


def _oe(rows, jahre, g):
    return mittel_jahre([jahr_vergleich_aus(rows, j, g) for j in jahre], g)


def test_mittel_teilweise_ueberschneidung_zaehlt_nicht():
    oj = _oe(_WINTERBORN, [2025, 2024, 2023], _BIS(6))
    assert oj["count"] == 2 and oj["pv"] == 600 and oj["monate"] == _BIS(6)


def test_mittel_ohne_ueberschneidung_none():
    rows = _jz(2026, _BIS(7)) + _jz(2025, [11, 12])
    assert mittel_jahre([jahr_vergleich_aus(rows, 2025, _BIS(7))], _BIS(7)) is None


def test_mittel_abgeschlossenes_jahr():
    oj = _oe(_WINTERBORN, [2024, 2023], _BIS(12))
    assert oj["count"] == 1 and oj["pv"] == 1200


# ── Monatsmenge (JahrMonatsmenge.test.tsx, N-65 — Winterborn 02.08.2026) ────────────────────────────────────────

_AM_2_AUGUST = date(2026, 8, 2)
_WB = [dict(jahr=j, monat=m) for j, ms in ((2026, _BIS(6)), (2025, _BIS(12)), (2024, _BIS(12)),
                                            (2023, [6, 7, 8, 9, 10, 11, 12])) for m in ms]
_jahresz = lambda j, ms: [dict(jahr=j, monat=m) for m in ms]  # noqa: E731


def test_menge_luecke_bis_heute():
    assert zu_ladende_monate(_WB, 2026, _AM_2_AUGUST) == _BIS(8)


def test_menge_mehrere_offene_monate():
    assert zu_ladende_monate(_jahresz(2026, _BIS(3)) + _jahresz(2025, _BIS(12)), 2026, _AM_2_AUGUST) == _BIS(8)


def test_menge_luecke_mitten_im_jahr():
    assert zu_ladende_monate(_jahresz(2026, [1, 2, 5, 6]) + _jahresz(2025, _BIS(12)), 2026, _AM_2_AUGUST) == _BIS(8)


def test_menge_abgeschlossenes_jahr():
    assert zu_ladende_monate(_WB, 2025, _AM_2_AUGUST) == _BIS(12)
    assert zu_ladende_monate(_WB, 2024, _AM_2_AUGUST) == _BIS(12)


def test_menge_startjahr_ab_inbetriebnahme():
    assert zu_ladende_monate(_WB, 2023, _AM_2_AUGUST) == [6, 7, 8, 9, 10, 11, 12]


def test_menge_vor_inbetriebnahme_und_zukunft_leer():
    assert zu_ladende_monate(_WB, 2022, _AM_2_AUGUST) == []
    assert zu_ladende_monate(_WB, 2027, _AM_2_AUGUST) == []
    assert zu_ladende_monate([], 2026, _AM_2_AUGUST) == []


def test_menge_erfasste_zeile_zaehlt_immer():
    rows = _jahresz(2026, _BIS(6) + [11]) + _jahresz(2025, _BIS(12))
    assert zu_ladende_monate(rows, 2026, _AM_2_AUGUST) == _BIS(8) + [11]


def test_menge_obermenge_invariante():
    for jahr in (2023, 2024, 2025, 2026):
        alt = {r["monat"] for r in _WB if r["jahr"] == jahr}
        assert alt <= set(zu_ladende_monate(_WB, jahr, _AM_2_AUGUST))


def test_monat_hat_daten_stammdaten_sind_keine_daten():
    assert not monat_hat_daten(dict(soll_pv_kwh=396.1, netzbezug_preis_cent=40, einspeise_preis_cent=8.2,
                                    speicher_kapazitaet_kwh=12.8))


def test_monat_hat_daten_gemessene_null_zaehlt():
    assert monat_hat_daten(dict(pv_erzeugung_kwh=0))
    assert monat_hat_daten(dict(netzbezug_kwh=12.5))
    assert monat_hat_daten(dict(wp_strom_kwh=60))


def test_monat_hat_daten_leer():
    assert not monat_hat_daten({})


def test_abgeschlossene_monate():
    assert abgeschlossene_monate(_BIS(8), 2026, _AM_2_AUGUST) == _BIS(7)
    assert abgeschlossene_monate(_BIS(12), 2025, _AM_2_AUGUST) == _BIS(12)
    assert abgeschlossene_monate([1], 2026, date(2026, 1, 15)) == []
