"""RF-50 … RF-52 — benannte Proben für die Zweige, die vor dem Schnitt weder die direkten Tests noch ein Golden Master traf.

Komplexitäts-Refactoring der Sitzung S5 (Bauplan RF-40, Bauform RF-1): ``MonatsdatenChecks._check_wp_monatsdaten``
(Daten-Checker, WP-Monatswerte), ``preise_speicher_sensoren`` (HA-Export Stufe 3b) und ``falte_zeitraum`` (Layer,
Jahres-Faltung) wurden in Phasen geschnitten. Diese Proben sind **am HEAD vor dem Schnitt grün** gemessen und halten
fest, was der Schnitt nicht verschieben darf:

* **RF-50** — die 25-%-Schwelle der Rest-Frage (an der Schwelle still, darüber INFO), der Widerspruch Gesamtwärme < Σ
  Achsen, der Modus-Widerspruch mit seiner Toleranz 0,5 kWh, die Fehlend-Meldungen je Messmodus (nicht getrennt ⇒
  «Stromverbrauch», getrennt ⇒ «Strom Heizen/Warmwasser», Klimaanlage ⇒ «Strom Heizen», eine Seite ⇒ eigene Zeile), die
  Kürzung der Monatslisten nach sechs Monaten und die OK-Zeile.
* **RF-51** — Bezugspreis mit/ohne Börse (Formeltext je Quelle), Eigenverbrauchswert nur bei vollständigem Bezugspreis,
  η der Anlage nur, wenn **alle** Speicher einen haben, Speicherstrom = Vergütung ÷ η, Netzladen = Bezug ÷ η nur mit
  Netzladung, «leer um»/«reicht bis Mitternacht» aus der SoC-Reihe, Abregelung 0 ist ein Wert, §51 = Börse < 0 ∧ PV > 0,
  ohne Bezugspreise keine Preis-Sensoren.
* **RF-52** — verbrauchsgewichtete Preise (Monate ohne Netzbezug fallen aus dem Gewicht; ohne jede Menge das Mittel),
  Grundlast-Anteil nur über Monate mit Grundlast, ``wp_modus_nicht_aufgeteilt``-Rückfall mit Klemme ≥ 0, Quote mit
  Nenner 0, Σ der Investitions-Finanzzeilen und der sonstigen Geräte, die Schlüssel-Reihenfolge der Antwort.

Schwesterdateien: ``test_n443_f5_ein_stromfeld_fehlt.py``, ``test_n391_gesamtwaerme.py``, ``test_n578_wp_gesamtwert.py``,
``test_daten_checker_wp_modus_widerspruch.py`` (RF-50) · ``test_s3b_preise_speicher_sensoren.py``,
``test_s3b_preis_reihe_layer.py`` (RF-51) · ``test_ergebnis_jahr_portiert.py``, ``test_ergebnis_leiter.py``,
``test_n584_jahr_grundgesamtheit.py`` (RF-52). Keine DB, kein Netz, keine Uhr: die Checker-Methode bekommt schlanke
Doubles (Muster ``test_n451_monatspfad_k3.py``), die Export-Phase gestellte Preis-Objekte, die Faltung Antwort-Dicts.
"""

from __future__ import annotations

from backend.tests.werkzeug_befund import befund_link
from datetime import date
from types import SimpleNamespace

import pytest

from backend.api.routes.ha_export.anlage_preise_speicher import WirkungsgradInfo, preise_speicher_sensoren
from backend.core.berechnungen.ergebnis import falte_zeitraum
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity


# ═════════════════════════════════════════════════════════════════════════════
# RF-50 · _check_wp_monatsdaten
# ═════════════════════════════════════════════════════════════════════════════

LW_GETRENNT = {"wp_art": "luft_wasser", "getrennte_strommessung": True}
LW_GESAMT = {"wp_art": "luft_wasser"}
LL_GETRENNT = {"wp_art": "luft_luft", "getrennte_strommessung": True}


class _Inv:
    def __init__(self, param: dict, zeilen: dict[tuple[int, int], dict]):
        self.id = 7
        self.typ = "waermepumpe"
        self.bezeichnung = "WP"
        self.parameter = param
        self.anschaffungsdatum = date(2025, 1, 1)
        self.stilllegungsdatum = None
        self.aktiv = True
        self.monatsdaten = [
            SimpleNamespace(jahr=j, monat=m, verbrauch_daten=d, source_provenance={})
            for (j, m), d in zeilen.items()
        ]

    def ist_aktiv_im_monat(self, _j, _m):
        return True


def _pruefe(param: dict, zeilen: dict[tuple[int, int], dict], monate=None) -> list:
    inv = _Inv(param, zeilen)
    md = [SimpleNamespace(jahr=j, monat=m) for (j, m) in (monate or zeilen)]
    return DatenChecker(None)._check_wp_monatsdaten(inv, "WP", param, md)


def _meldungen(erg, teil: str) -> list:
    return [e for e in erg if teil in e.meldung]


_W = {"heizenergie_kwh": 1000.0, "warmwasser_kwh": 200.0}


def test_rf50_rest_genau_an_der_schwelle_bleibt_still():
    """Rest 100 von 400 kWh = genau 25 % ⇒ keine Frage (die Regel ist «>», nicht «≥»)."""
    erg = _pruefe(LW_GETRENNT, {(2025, 3): {**_W, "stromverbrauch_kwh": 400.0, "strom_heizen_kwh": 250.0,
                                            "strom_warmwasser_kwh": 50.0}})
    assert _meldungen(erg, "misst er nur die Wärmepumpe") == []


def test_rf50_rest_ueber_der_schwelle_stellt_die_frage_mit_dem_groessten_monat():
    """Rest 101 von 400 kWh > 25 % ⇒ INFO; das Beispiel ist der Monat mit dem größten Anteil."""
    erg = _pruefe(LW_GETRENNT, {
        (2025, 3): {**_W, "stromverbrauch_kwh": 400.0, "strom_heizen_kwh": 249.0, "strom_warmwasser_kwh": 50.0},
        (2025, 4): {**_W, "stromverbrauch_kwh": 400.0, "strom_heizen_kwh": 150.0, "strom_warmwasser_kwh": 50.0},
    })
    frage = _meldungen(erg, "misst er nur die Wärmepumpe")
    assert len(frage) == 1 and frage[0].schwere == CheckSeverity.INFO
    assert "(03/2025, 04/2025)" in frage[0].meldung
    assert frage[0].details.startswith("In 04/2025 liegen 200 von 400 kWh")


def test_rf50_ohne_aufteilende_achse_keine_rest_frage():
    """Nur eine gemessene 0 auf einer Achse ⇒ Rest in voller Höhe, aber keine Aufteilung ⇒ keine Frage."""
    erg = _pruefe(LW_GETRENNT, {(2025, 3): {**_W, "stromverbrauch_kwh": 400.0, "strom_heizen_kwh": 0.0,
                                            "strom_warmwasser_kwh": 0.0}})
    assert _meldungen(erg, "misst er nur die Wärmepumpe") == []


def test_rf50_gesamtzaehler_unter_den_achsen_ist_ein_widerspruch_ohne_rest_frage():
    erg = _pruefe(LW_GETRENNT, {(2025, 3): {**_W, "stromverbrauch_kwh": 100.0, "strom_heizen_kwh": 250.0,
                                            "strom_warmwasser_kwh": 50.0}})
    assert len(_meldungen(erg, "Gesamtzähler kleiner als die Summe der Achsen (03/2025)")) == 1
    assert _meldungen(erg, "misst er nur die Wärmepumpe") == []


def test_rf50_gesamtwaerme_unter_den_achsen_und_toleranz():
    """Gesamtwärme 1000 < 800 + 300 ⇒ Warnung; 1000 gegen 1000,5 (Toleranz 0,5) ⇒ still."""
    erg = _pruefe(LW_GESAMT, {
        (2025, 3): {"stromverbrauch_kwh": 300.0, "waerme_kwh": 1000.0, "heizenergie_kwh": 800.0, "warmwasser_kwh": 300.0},
        (2025, 4): {"stromverbrauch_kwh": 300.0, "waerme_kwh": 1000.0, "heizenergie_kwh": 800.0, "warmwasser_kwh": 200.5},
    })
    w = _meldungen(erg, "Gesamtwärme kleiner als Heizwärme + Warmwasser-Wärme")
    assert len(w) == 1 and "(03/2025)" in w[0].meldung and w[0].schwere == CheckSeverity.WARNING
    assert befund_link(w[0]) is not None and w[0].investition_id == 7


_WAERME_NULL = "„Wärme gesamt“ ist 0, Heizwärme + Warmwasser-Wärme sind größer"


def test_t_gesamtwaerme_null_neben_achsen_eigene_warnung():
    """Päckchen T: «Wärme gesamt» = gemessene 0 bei 800 + 300 ⇒ genau eine eigene Warnung, der Zwilling schweigt
    (dessen Details sagen «eedc rechnet mit der Gesamtwärme» — bei 0 rechnet eedc nach D1 mit den Achsen)."""
    erg = _pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 300.0, "waerme_kwh": 0.0,
                                          "heizenergie_kwh": 800.0, "warmwasser_kwh": 300.0}})
    w = _meldungen(erg, _WAERME_NULL)
    assert len(w) == 1 and w[0].meldung.endswith("(03/2025)") and w[0].schwere == CheckSeverity.WARNING
    assert befund_link(w[0]) is not None and w[0].investition_id == 7
    assert "mit den beiden Einzelwerten" in w[0].details
    assert _meldungen(erg, "Gesamtwärme kleiner als Heizwärme + Warmwasser-Wärme") == []


def test_t_gesamtwaerme_null_ohne_achsen_still():
    """Gesamt 0, Achsen 0 bzw. None ⇒ still (kein Widerspruch, eine echte Null)."""
    erg = _pruefe(LW_GESAMT, {
        (2025, 3): {"stromverbrauch_kwh": 300.0, "waerme_kwh": 0.0, "heizenergie_kwh": 0.0, "warmwasser_kwh": 0.0},
        (2025, 4): {"stromverbrauch_kwh": 300.0, "waerme_kwh": 0.0},
    })
    assert _meldungen(erg, _WAERME_NULL) == []


def test_t_gesamtwaerme_none_neben_achsen_still():
    """Gesamt None (kein Wert) neben Achsen > 0 ⇒ still: getrennte Zähler sind der Normalfall."""
    erg = _pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 800.0,
                                          "warmwasser_kwh": 300.0}})
    assert _meldungen(erg, _WAERME_NULL) == []


def test_t_gesamtwaerme_null_unter_der_toleranz_still():
    """Gesamt 0, Achsen zusammen 0,4 kWh ≤ 0,5 ⇒ still (Toleranz wie beim Zwilling)."""
    erg = _pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 300.0, "waerme_kwh": 0.0,
                                          "heizenergie_kwh": 0.3, "warmwasser_kwh": 0.1}})
    assert _meldungen(erg, _WAERME_NULL) == []


def test_rf50_modus_widerspruch_mit_toleranz():
    """Σ Modus-Strom 300,6 > 300 + 0,5 ⇒ Warnung; 300,5 ⇒ still."""
    erg = _pruefe(LW_GESAMT, {
        (2025, 3): {**_W, "stromverbrauch_kwh": 300.0, "modus_strom_heizen_kwh": 200.0, "modus_strom_kuehlen_kwh": 100.6},
        (2025, 4): {**_W, "stromverbrauch_kwh": 300.0, "modus_strom_heizen_kwh": 200.0, "modus_strom_kuehlen_kwh": 100.5},
    })
    w = _meldungen(erg, "Heiz- und Kühlstrom zusammen größer als der Gesamtverbrauch")
    assert len(w) == 1 and w[0].meldung.endswith("(03/2025)")


def _sieben(daten: dict) -> dict:
    return {(2025, m): dict(daten) for m in range(1, 8)}


def test_rf50_monatslisten_werden_nach_sechs_gekuerzt():
    """Sieben Monate in jeder Liste ⇒ «… (+1)» an den drei Widersprüchen, «(+1 weitere)» an den Fehlend-Zeilen."""
    erg = _pruefe(LW_GESAMT, _sieben({"stromverbrauch_kwh": 300.0, "waerme_kwh": 100.0, "heizenergie_kwh": 800.0,
                                     "warmwasser_kwh": 300.0, "modus_strom_heizen_kwh": 400.0}))
    assert "06/2025 … (+1))" in _meldungen(erg, "Heiz- und Kühlstrom")[0].meldung
    assert "06/2025 … (+1))" in _meldungen(erg, "Gesamtwärme kleiner")[0].meldung
    erg = _pruefe(LW_GETRENNT, _sieben({**_W, "stromverbrauch_kwh": 100.0, "strom_heizen_kwh": 250.0,
                                       "strom_warmwasser_kwh": 50.0}))
    assert "06/2025 … (+1))" in _meldungen(erg, "Gesamtzähler kleiner")[0].meldung
    erg = _pruefe(LW_GETRENNT, _sieben({**_W, "stromverbrauch_kwh": 400.0, "strom_heizen_kwh": 150.0,
                                       "strom_warmwasser_kwh": 50.0}))
    assert "06/2025 … (+1))" in _meldungen(erg, "misst er nur die Wärmepumpe")[0].meldung
    erg = _pruefe(LW_GESAMT, _sieben({"waerme_kwh": 900.0}))
    f = _meldungen(erg, "Stromverbrauch fehlt in 7 Monat(en)")
    assert len(f) == 1 and f[0].details.endswith("06/2025 (+1 weitere)")


def test_rf50_fehlend_nicht_getrennt_heisst_stromverbrauch():
    """Ohne getrennte Strommessung ⇒ «Stromverbrauch fehlt»; mit Gesamtwärme fehlt keine Heizwärme."""
    erg = _pruefe(LW_GESAMT, {(2025, 3): {"waerme_kwh": 900.0}, (2025, 4): {"stromverbrauch_kwh": 200.0, "waerme_kwh": 800.0}})
    f = _meldungen(erg, "fehlt in")
    assert [e.meldung for e in f] == ["WP: Stromverbrauch fehlt in 1 Monat(en)"]
    assert f[0].details == "03/2025" and f[0].schwere == CheckSeverity.WARNING


def test_rf50_fehlend_getrennt_beide_seiten_und_eine_seite():
    erg = _pruefe(LW_GETRENNT, {
        (2025, 3): {**_W},                                                      # beide Seiten leer
        (2025, 4): {**_W, "strom_warmwasser_kwh": 40.0},                        # nur Heizen fehlt
        (2025, 5): {**_W, "strom_heizen_kwh": 300.0},                           # nur Warmwasser fehlt
        (2025, 6): {"heizenergie_kwh": 1000.0, "strom_heizen_kwh": 300.0},     # kein Warmwasser ⇒ nichts
    })
    m = [e.meldung for e in _meldungen(erg, "fehlt in")]
    assert m == ["WP: Strom Heizen/Warmwasser fehlt in 1 Monat(en)", "WP: Strom Heizen fehlt in 1 Monat(en)",
                 "WP: Strom Warmwasser fehlt in 1 Monat(en)"]
    assert _meldungen(erg, "Monatsdaten vollständig") == []


def test_rf50_fehlend_klimaanlage_hat_nur_strom_heizen():
    erg = _pruefe(LL_GETRENNT, {(2025, 3): {"heizenergie_kwh": 500.0}})
    assert [e.meldung for e in _meldungen(erg, "fehlt in")] == ["WP: Strom Heizen fehlt in 1 Monat(en)"]


def test_rf50_heizwaerme_fehlt_und_ok_zeile():
    erg = _pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 200.0}})
    h = _meldungen(erg, "Heizwärme fehlt")
    assert len(h) == 1 and h[0].schwere == CheckSeverity.INFO and h[0].details == "03/2025"
    ok = _pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 200.0, "heizenergie_kwh": 800.0}})
    assert [e.meldung for e in ok] == ["WP: Monatsdaten vollständig (1 Monate)"]


def test_d5_heizwaerme_ueber_nutzenergie_heizbetrieb_fehlt_nicht():
    """E6.D D5: wer die Heizwärme je Betriebsart misst («Nutzenergie Heizbetrieb»), hat nichts nachzutragen — dieselbe
    Weiche (`heizwaerme_kwh`, D1) wie die Schwester-Prüfung «Strom Heizen fehlt»; vorher stand «Heizwärme fehlt»."""
    erg = _pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 200.0, "betriebsart_nutzenergie_heizen_kwh": 800.0}})
    assert _meldungen(erg, "Heizwärme fehlt") == []
    assert [e.meldung for e in erg] == ["WP: Monatsdaten vollständig (1 Monate)"]
    # Gegenprobe: ohne jede Heizwärme bleibt der Befund.
    assert len(_meldungen(_pruefe(LW_GESAMT, {(2025, 3): {"stromverbrauch_kwh": 200.0}}), "Heizwärme fehlt")) == 1


def test_rf50_ohne_erwartete_monate_keine_meldung():
    assert DatenChecker(None)._check_wp_monatsdaten(_Inv(LW_GESAMT, {}), "WP", LW_GESAMT, []) == []


def test_rf50_reihenfolge_der_meldungen():
    """Modus → Wärme → Gesamtzähler → Rest-Frage → Fehlend → Seiten → Heizwärme: die Reihenfolge ist Vertrag."""
    erg = _pruefe(LW_GETRENNT, {
        (2025, 3): {"stromverbrauch_kwh": 100.0, "strom_heizen_kwh": 250.0, "strom_warmwasser_kwh": 50.0,
                    "waerme_kwh": 100.0, "heizenergie_kwh": 800.0, "warmwasser_kwh": 300.0,
                    "modus_strom_heizen_kwh": 400.0},
        (2025, 4): {"stromverbrauch_kwh": 400.0, "strom_heizen_kwh": 150.0, "strom_warmwasser_kwh": 50.0,
                    "heizenergie_kwh": 800.0, "warmwasser_kwh": 100.0},
        (2025, 5): {"warmwasser_kwh": 100.0},
        (2025, 6): {"heizenergie_kwh": 800.0, "warmwasser_kwh": 100.0, "strom_heizen_kwh": 300.0},
    })
    folge = [e.meldung.split(": ", 1)[1][:30] for e in erg]
    assert folge == [
        "Heiz- und Kühlstrom zusammen g", "Gesamtwärme kleiner als Heizwä", "Gesamtzähler kleiner als die S",
        "Der Gesamtzähler misst deutlic", "Strom Heizen/Warmwasser fehlt ", "Strom Warmwasser fehlt in 1 Mo",
        "Heizwärme fehlt in 1 Monat(en)",
    ]


# ═════════════════════════════════════════════════════════════════════════════
# RF-51 · preise_speicher_sensoren
# ═════════════════════════════════════════════════════════════════════════════

HEUTE = date(2026, 9, 22)
STUNDE = 14            # backward-Slot 15


def _reihe(quelle="tarif", jetzt=30.0, vollstaendig=True):
    preise = [30.0] * 48
    preise[STUNDE + 1] = jetzt
    return SimpleNamespace(quelle=quelle, preis_cent=preise, ist_vollstaendig=vollstaendig, hat_preis=True)


def _bezug(reihe=None, aufschlag=None, verguetung=8.0):
    return SimpleNamespace(
        allgemein=reihe or _reihe(), aufschlag=aufschlag,
        waermepumpe=SimpleNamespace(hat_preis=False, quelle=None, preis_cent=[]), wp_eigener_tarif=False,
        ust_prozent=19.0, tarif_heute=None, zeitfenster_ignoriert=False, verguetung_grund=None,
        verguetung_cent=verguetung, verguetung_quelle="tarif", einspeisung_variabel=False,
    )


def _eta(*werte, netz=True):
    return {i + 1: WirkungsgradInfo(w, "parameter" if w is not None else None, "gepflegt", netz)
            for i, w in enumerate(werte)}


async def _lauf(*, bezugspreise="std", speicher_eta=None, prognose=None, preis=None) -> dict:
    sv: list = []
    rueck = await preise_speicher_sensoren(
        anlage=None, sensor_values=sv, prognose=prognose, preis=preis, fenster_ctx=None,
        bezugspreise=_bezug() if bezugspreise == "std" else bezugspreise,
        speicher_eta=speicher_eta or {}, heute=HEUTE, jetzt_stunde=STUNDE,
    )
    assert rueck == {}
    keys = [s.definition.key for s in sv]
    assert len(keys) == len(set(keys))
    return {s.definition.key: s for s in sv}


async def test_rf51_bezugspreis_boerse_plus_aufschlag():
    aufschlag = SimpleNamespace(cent=12.5, quelle="gepflegt", basis="vertrag")
    s = await _lauf(bezugspreise=_bezug(_reihe("boerse_plus_aufschlag", jetzt=25.0), aufschlag), preis={"markt": "DE"})
    b = s["eedc_bezugspreis_jetzt_cent"]
    assert b.value == 25.0
    assert b.berechnung.startswith("(1 + 19 % USt) × Börsenpreis + ") and b.berechnung.endswith("ct Aufschlag (gepflegt)")
    assert b.zusatz_attribute["markt"] == "DE" and b.zusatz_attribute["aufschlag_cent"] == 12.5
    assert s["eedc_eigenverbrauch_wert_cent"].value == 17.0


async def test_rf51_nackte_boerse_ohne_eigenverbrauchswert():
    s = await _lauf(bezugspreise=_bezug(_reihe("boersenpreis", jetzt=12.0, vollstaendig=False)), preis={"markt": "AT"})
    b = s["eedc_bezugspreis_jetzt_cent"]
    assert b.berechnung == "Börsenpreis der laufenden Stunde — Näherung ohne ableitbaren Aufschlag"
    assert b.zusatz_attribute["aufschlag_quelle"] == "keiner" and b.zusatz_attribute["markt"] == "AT"
    assert "dynamischer Tarif ohne ableitbaren Aufschlag" in b.zusatz_attribute["eigenverbrauch_wert_grund"]
    assert "eedc_eigenverbrauch_wert_cent" not in s
    assert s["eedc_einspeiseverguetung_cent"].value == 8.0


async def test_rf51_zeitfenster_und_tarif_texte():
    s = await _lauf(bezugspreise=_bezug(_reihe("zeitfenster")))
    assert s["eedc_bezugspreis_jetzt_cent"].berechnung == "Arbeitspreis des Zeitfensters, das die laufende Stunde deckt"
    assert "markt" not in s["eedc_bezugspreis_jetzt_cent"].zusatz_attribute
    s = await _lauf()
    assert s["eedc_bezugspreis_jetzt_cent"].berechnung == "Arbeitspreis des Tarifs"


async def test_rf51_eigenverbrauchswert_ist_bezug_minus_verguetung():
    s = await _lauf()
    ev = s["eedc_eigenverbrauch_wert_cent"]
    assert ev.value == 22.0 and "ct Bezug −" in ev.berechnung and ev.berechnung.endswith("ct Vergütung")
    s = await _lauf(bezugspreise=_bezug(verguetung=None))
    assert "eedc_eigenverbrauch_wert_cent" not in s and "eedc_einspeiseverguetung_cent" not in s


async def test_rf51_eta_anlage_nur_wenn_alle_speicher_einen_haben():
    s = await _lauf(speicher_eta=_eta(95.0, 90.0))
    assert s["eedc_speicher_strom_kosten_cent"].value == round(8.0 / 0.90, 2)
    assert s["eedc_speicher_strom_kosten_cent"].zusatz_attribute["wirkungsgrad_prozent"] == 90.0
    assert s["eedc_speicher_netzladen_kosten_cent"].value == round(30.0 / 0.90, 2)
    s = await _lauf(speicher_eta=_eta(95.0, None))
    assert "eedc_speicher_strom_kosten_cent" not in s and "eedc_speicher_netzladen_kosten_cent" not in s


async def test_rf51_netzladekosten_nur_wenn_ein_speicher_aus_dem_netz_laedt():
    s = await _lauf(speicher_eta=_eta(95.0, netz=False))
    assert "eedc_speicher_strom_kosten_cent" in s and "eedc_speicher_netzladen_kosten_cent" not in s


async def test_rf51_ohne_bezugspreise_keine_preis_sensoren():
    prognose = {"speicher_soc_pro_stunde": {14: 50.0, 24: 40.0}, "speicher_sim_start_stunde": 14,
                "abregelung_om_kwh": 1.5}
    s = await _lauf(bezugspreise=None, speicher_eta=_eta(95.0), prognose=prognose)
    assert sorted(s) == ["eedc_abregelung_heute_kwh", "eedc_speicher_reicht_bis_mitternacht"]


async def test_rf51_leer_um_und_reicht_bis_mitternacht():
    leer = await _lauf(prognose={"speicher_soc_pro_stunde": {14: 50.0, 15: 20.0, 16: 1.5, 17: 1.0, 24: 1.0},
                                 "speicher_sim_start_stunde": 14})
    assert leer["eedc_speicher_reicht_bis_mitternacht"].value is False
    # Übergang in Slot 16 ⇒ «leer um» = ENDE von Slot 16 = 16:00 (nicht der Tiefststand, Slot 17 ⇒ 17:00).
    assert leer["eedc_speicher_leer_um_ts"].value.startswith("2026-09-22T16:00:00")
    assert leer["eedc_speicher_reicht_bis_mitternacht"].zusatz_attribute["min_soc_prozent"] == 1.0
    assert leer["eedc_speicher_reicht_bis_mitternacht"].zusatz_attribute["min_soc_um"].startswith("2026-09-22T17:00:00")
    reicht = await _lauf(prognose={"speicher_soc_pro_stunde": {14: 50.0, 20: 30.0, 24: 10.0},
                                   "speicher_sim_start_stunde": 14})
    assert reicht["eedc_speicher_reicht_bis_mitternacht"].value is True and "eedc_speicher_leer_um_ts" not in reicht
    # Schon leer beim Start und leer bis Mitternacht: kein Übergang ⇒ kein «leer um», aber «reicht» AUS (End-SoC ≤ 2 %).
    schon = await _lauf(prognose={"speicher_soc_pro_stunde": {14: 1.0, 24: 1.0}, "speicher_sim_start_stunde": 14})
    assert schon["eedc_speicher_reicht_bis_mitternacht"].value is False and "eedc_speicher_leer_um_ts" not in schon
    assert "eedc_speicher_reicht_bis_mitternacht" not in await _lauf(prognose={})


async def test_rf51_abregelung_null_ist_ein_wert():
    s = await _lauf(prognose={"abregelung_om_kwh": 0.0})
    assert s["eedc_abregelung_heute_kwh"].value == 0.0
    assert "eedc_abregelung_heute_kwh" not in await _lauf(prognose={})


def _rang(jetzt: float, spaeter: dict | None = None) -> dict:
    preise = {STUNDE: jetzt, **(spaeter or {})}
    return {"rang_profil": [{"stunde": h, "preis_cent": preise.get(h, 10.0)} for h in range(24)]}


async def test_rf51_paragraf_51_boerse_negativ_und_pv():
    pv = [0.0] * 25
    pv[STUNDE + 1] = 2.0
    s = await _lauf(prognose={"stundenprofil_heute": pv}, preis=_rang(-1.0, {18: -2.0}))
    e = s["eedc_einspeisung_unerwuenscht"]
    assert e.value is True and e.zusatz_attribute["negative_stunden_heute"] == 2
    assert e.zusatz_attribute["naechste_negative_ab"] == "14:00"
    ohne_pv = await _lauf(prognose={"stundenprofil_heute": [0.0] * 25}, preis=_rang(-1.0))
    assert ohne_pv["eedc_einspeisung_unerwuenscht"].value is False
    positiv = await _lauf(prognose={"stundenprofil_heute": pv}, preis=_rang(3.0, {18: -2.0}))
    assert positiv["eedc_einspeisung_unerwuenscht"].value is False
    assert positiv["eedc_einspeisung_unerwuenscht"].zusatz_attribute["naechste_negative_ab"] == "18:00"
    assert "eedc_einspeisung_unerwuenscht" not in await _lauf(prognose={"stundenprofil_heute": pv})


async def test_rf51_sensor_reihenfolge():
    """Bezug → Vergütung → EV-Wert → Speicherstrom → Netzladen → leer um → reicht → Abregelung → §51."""
    pv = [0.0] * 25
    pv[STUNDE + 1] = 2.0
    s = await _lauf(speicher_eta=_eta(95.0), preis=_rang(-1.0),
                    prognose={"speicher_soc_pro_stunde": {14: 50.0, 15: 1.0, 24: 1.0}, "speicher_sim_start_stunde": 14,
                              "abregelung_om_kwh": 0.5, "stundenprofil_heute": pv})
    assert list(s) == [
        "eedc_bezugspreis_jetzt_cent", "eedc_einspeiseverguetung_cent", "eedc_eigenverbrauch_wert_cent",
        "eedc_speicher_strom_kosten_cent", "eedc_speicher_netzladen_kosten_cent", "eedc_speicher_leer_um_ts",
        "eedc_speicher_reicht_bis_mitternacht", "eedc_abregelung_heute_kwh", "eedc_einspeisung_unerwuenscht",
    ]


# ═════════════════════════════════════════════════════════════════════════════
# RF-52 · falte_zeitraum
# ═════════════════════════════════════════════════════════════════════════════


def test_rf52_netzbezug_preis_gewichtet_monate_ohne_bezug_fallen_aus_dem_gewicht():
    j = falte_zeitraum([dict(monat=1, netzbezug_kwh=100.0, netzbezug_preis_cent=30.0),
                        dict(monat=2, netzbezug_kwh=0.0, netzbezug_preis_cent=40.0),
                        dict(monat=3, netzbezug_kwh=None, netzbezug_preis_cent=50.0)], 2026)
    assert j["netzbezug_preis_cent"] == 30.0
    ohne = falte_zeitraum([dict(monat=1, netzbezug_kwh=0.0, netzbezug_preis_cent=30.0),
                           dict(monat=2, netzbezug_kwh=0.0, netzbezug_preis_cent=40.0)], 2026)
    assert ohne["netzbezug_preis_cent"] == 35.0      # ohne jede Menge: das ungewichtete Mittel (Client-Regel)


def test_rf52_einspeisepreis_gewichtet_und_durchschnitt_nur_wenn_gepflegt():
    j = falte_zeitraum([dict(monat=1, einspeisung_kwh=300.0, einspeise_preis_cent=8.0),
                        dict(monat=2, einspeisung_kwh=100.0, einspeise_preis_cent=12.0)], 2026)
    assert j["einspeise_preis_cent"] == 9.0 and j["einspeise_durchschnittspreis_cent"] is None
    assert j["netzbezug_durchschnittspreis_cent"] is None


def test_rf52_grundlast_anteil_nur_ueber_monate_mit_grundlast():
    j = falte_zeitraum([dict(monat=1, grundlast_kwh=50.0, gesamtverbrauch_kwh=500.0, grundlast_kw=0.2),
                        dict(monat=2, grundlast_kwh=None, gesamtverbrauch_kwh=500.0, grundlast_kw=0.4)], 2026)
    assert j["grundlast_anteil_prozent"] == 10.0 and j["grundlast_kwh"] == 50.0
    assert j["grundlast_kw"] == pytest.approx(0.3)
    null = falte_zeitraum([dict(monat=1, grundlast_kwh=5.0, gesamtverbrauch_kwh=0.0)], 2026)
    assert null["grundlast_anteil_prozent"] is None


def test_rf52_wp_modus_nicht_aufgeteilt_rueckfall_und_klemme():
    j = falte_zeitraum([dict(monat=1, wp_strom_kwh=100.0, wp_modus_strom_heizen_kwh=60.0,
                             wp_modus_strom_warmwasser_kwh=30.0)], 2026)
    assert j["wp_modus_nicht_aufgeteilt_kwh"] == 10.0
    ueber = falte_zeitraum([dict(monat=1, wp_strom_kwh=100.0, wp_modus_strom_heizen_kwh=80.0,
                                 wp_modus_strom_kuehlen_kwh=30.0)], 2026)
    assert ueber["wp_modus_nicht_aufgeteilt_kwh"] == 0
    kz = falte_zeitraum([dict(monat=1, wp_strom_kwh=100.0)], 2026, {"wp_modus_nicht_aufgeteilt_kwh": 7.0})
    assert kz["wp_modus_nicht_aufgeteilt_kwh"] == 7.0
    kz_none = falte_zeitraum([dict(monat=1, wp_strom_kwh=100.0)], 2026, {"wp_modus_nicht_aufgeteilt_kwh": None})
    assert kz_none["wp_modus_nicht_aufgeteilt_kwh"] == 100.0
    assert falte_zeitraum([dict(monat=1)], 2026)["wp_modus_nicht_aufgeteilt_kwh"] == 0


def test_rf52_quote_mit_nenner_null():
    j = falte_zeitraum([dict(monat=1, eigenverbrauch_kwh=50.0, gesamtverbrauch_kwh=0.0, pv_erzeugung_kwh=0.0)], 2026)
    assert j["autarkie_prozent"] is None and j["autarkie_nenner_kwh"] == 0.0 and j["autarkie_zaehler_kwh"] == 50.0
    assert j["eigenverbrauch_quote_prozent"] is None


def _fin(inv_id, **w):
    basis = dict(investition_id=inv_id, betriebskosten_monat_euro=1.0, erloes_euro=None, ersparnis_euro=None,
                 sonstige_ertraege_euro=0.0, sonstige_ausgaben_euro=0.0, ersparnis_label="", formel="f",
                 berechnung="b", erloes_berechnung="e", betriebskosten_jahr_euro=12.0)
    return {**basis, **w}


def test_rf52_investitions_finanzzeilen_summieren_je_investition():
    j = falte_zeitraum([
        dict(monat=1, investitionen_financials=[_fin(1, ersparnis_euro=5.0), _fin(2)]),
        dict(monat=2, investitionen_financials=[_fin(1, ersparnis_euro=None, erloes_euro=3.0, ersparnis_label="WP",
                                                     sonstige_ertraege_euro=2.0, sonstige_ausgaben_euro=1.5),
                                                _fin(2, ersparnis_label="")]),
    ], 2026)
    fin = {f["investition_id"]: f for f in j["investitionen_financials"]}
    assert list(fin) == [1, 2]
    assert fin[1]["betriebskosten_monat_euro"] == 2.0 and fin[1]["ersparnis_euro"] == 5.0 and fin[1]["erloes_euro"] == 3.0
    assert fin[1]["sonstige_ertraege_euro"] == 2.0 and fin[1]["sonstige_ausgaben_euro"] == 1.5
    assert fin[1]["ersparnis_label"] == "WP"
    assert fin[1]["formel"] is None and fin[1]["berechnung"] is None and fin[1]["erloes_berechnung"] is None
    assert fin[1]["betriebskosten_jahr_euro"] is None
    assert fin[2]["erloes_euro"] is None and fin[2]["ersparnis_euro"] is None and fin[2]["ersparnis_label"] == ""


def test_rf52_sonstige_geraete_summieren_null_wird_kein_wert():
    g = dict(bezeichnung="Pool", kategorie="verbraucher", verbrauch_kwh=10.0, bezug_netz_kwh=None, erloes_euro=0.0)
    j = falte_zeitraum([dict(monat=1, sonstiges_geraete=[g]), dict(monat=2, sonstiges_geraete=[{**g, "verbrauch_kwh": 5.5}])],
                       2026)
    assert j["sonstiges_geraete"] == [{
        "bezeichnung": "Pool", "kategorie": "verbraucher", "erzeugung_kwh": None, "eigenverbrauch_kwh": None,
        "einspeisung_kwh": None, "verbrauch_kwh": 15.5, "bezug_pv_kwh": None, "bezug_netz_kwh": None,
        "abgabe_kwh": None, "erloes_euro": None,
    }]


def test_rf52_geraete_und_feld_quellen():
    j = falte_zeitraum([dict(monat=1, komponenten_geraete={"speicher": ["A"]}, feld_quellen={"x": "a"}),
                        dict(monat=2, komponenten_geraete={"speicher": ["B", "A"]}, feld_quellen={"x": "b", "y": "c"})], 2026)
    assert j["komponenten_geraete"] == {"speicher": ["A", "B"]} and j["feld_quellen"] == {"x": "b", "y": "c"}


#: Die Schlüssel der Jahres-Antwort in ihrer Reihenfolge (am HEAD `c28461eca` gemessen) — die Phasen setzen die Antwort
#: aus Teilstücken zusammen, und die Reihenfolge ist Teil dessen, was der Golden Master `cockpit-monat` vergleicht.
_SCHLUESSEL = """
anlage_id anlage_name jahr monat monat_name aktualisiert_um quellen hinweise pv_erzeugung_kwh einspeisung_kwh netzbezug_kwh
eigenverbrauch_kwh direktverbrauch_kwh gesamtverbrauch_kwh wandlungsverluste_kwh wandlungsverluste_bezug_kwh
wandlungsverluste_prozent eigenverbrauch_ohne_verluste_kwh verluste_grund autarkie_prozent autarkie_zaehler_kwh
autarkie_nenner_kwh autarkie_fenster eigenverbrauch_quote_prozent eigenverbrauch_quote_zaehler_kwh
eigenverbrauch_quote_nenner_kwh eigenverbrauch_quote_fenster spez_ertrag speicher_ladung_kwh speicher_entladung_kwh
speicher_ladung_netz_kwh speicher_wirkungsgrad_prozent speicher_vollzyklen speicher_kapazitaet_kwh
speicher_auslastungs_basis_kwh speicher_auslastung_prozent speicher_auslastung_zaehler_kwh speicher_auslastung_nenner_kwh
speicher_auslastung_fenster speicher_ersparnis_euro hat_speicher speicher_soc_drift_signifikant speicher_wirkungsgrad_quelle
speicher_effektiver_ladepreis_cent speicher_effektiver_ladepreis_quelle speicher_ladung_netz_kosten_euro
speicher_ladung_netz_preis_cent speicher_ladung_netz_preis_quelle wp_strom_kwh wp_waerme_kwh wp_heizung_kwh
wp_warmwasser_kwh wp_strom_heizen_kwh wp_modus_strom_heizen_kwh wp_modus_strom_kuehlen_kwh wp_modus_strom_warmwasser_kwh
wp_modus_abdeckung_h wp_modus_gemessen wp_modus_nicht_aufgeteilt_kwh wp_modus_strom_lueften_kwh
wp_modus_strom_entfeuchten_kwh wp_modus_nutzenergie_lueften_kwh wp_modus_nutzenergie_entfeuchten_kwh
wp_modus_strom_bezug_kwh wp_jaz wp_jaz_grund wp_jaz_hinweis wp_jaz_zaehler_kwh wp_jaz_nenner_kwh wp_waerme_abgeleitet
wp_waerme_herkunft wp_ersparnis_vorbehalt wp_jaz_heizen wp_jaz_heizen_grund wp_jaz_warmwasser wp_jaz_warmwasser_grund
wp_jaz_kuehlen wp_jaz_kuehlen_grund wp_jaz_ist_schranke wp_jaz_schranke_hinweis wp_heizstab_kwh wp_jaz_ohne_zusatzheizung
wp_jaz_ohne_zusatzheizung_grund wp_jaz_ohne_zusatzheizung_hinweis wp_jaz_ohne_zusatzheizung_zaehler_kwh
wp_jaz_ohne_zusatzheizung_nenner_kwh wp_geraete wp_moeglich wp_kaelte_kwh wp_strom_warmwasser_kwh wp_starts_summe_monat
wp_starts_max_tag wp_betriebsstunden_summe_monat wp_betriebsstunden_max_tag hat_waermepumpe emob_ladung_kwh emob_km
emob_verbrauch_100km emob_verbrauch_quelle emob_verbrauch_basis_kwh emob_ladung_gesamt_kwh emob_ladung_pv_kwh
emob_ladung_netz_kwh emob_ladung_extern_kwh emob_v2h_kwh hat_emobilitaet bkw_erzeugung_kwh bkw_eigenverbrauch_kwh
hat_balkonkraftwerk sonstiges_erzeugung_kwh sonstiges_eigenverbrauch_kwh sonstiges_einspeisung_kwh sonstiges_verbrauch_kwh
abgabe_dritte_kwh sonstiges_bezug_pv_kwh sonstiges_bezug_netz_kwh sonstiges_geraete hat_sonstiges einspeise_erloes_euro
einspeisung_neg_preis_kwh nicht_vergueteter_erloes_euro netzbezug_kosten_euro netzbezug_arbeitspreis_kosten_euro
ev_ersparnis_euro bkw_ersparnis_euro erzeuger_erloes_euro ust_eigenverbrauch_euro netto_ertrag_euro wp_ersparnis_euro
emob_ersparnis_euro sonstige_ertraege_euro sonstige_ausgaben_euro sonstige_netto_euro dienstliche_ladekosten_euro
anlage_sonstige_ertraege_euro anlage_sonstige_ausgaben_euro betriebskosten_anteilig_euro ergebnis_vor_betriebskosten_euro
ergebnis_euro ergebnis_herleitung fehlende_posten soll_erfuellung_prozent soll_erfuellung_monat_prozent soll_fenster_text
netzbezug_preis_cent netzbezug_preis_herkunft einspeise_preis_cent netzbezug_durchschnittspreis_cent
einspeise_durchschnittspreis_cent grundgebuehr_euro grundgebuehr_aufteilung netzbezug_anteile ev_ersparnis_wp_tarif_kwh
ev_ersparnis_wp_tarif_cent zaehlergebuehr_euro_jahr soll_pv_kwh soll_pv_tage soll_pv_tage_gesamt grundlast_kw grundlast_kwh
grundlast_anteil_prozent vorjahr investitionen_financials komponenten_geraete feld_quellen
""".split()


def test_rf52_schluessel_und_reihenfolge_der_jahresantwort():
    assert list(falte_zeitraum([dict(monat=1)], 2026)) == _SCHLUESSEL
    assert list(falte_zeitraum([], 2026, {"wp_cop": 3.0})) == _SCHLUESSEL
