"""RF-64 … RF-66 — benannte Proben für die Zweige der drei Daten-Checker-Methoden, die der Golden Master nicht trifft.

Komplexitäts-Refactoring der Session P3-B (Bauplan RF-40 Paket 3, Bauform RF-1): ``QuellenChecks._check_datenquelle_drift``
(Drift gegen HA-LTS), ``EnergieprofilChecks._check_energieprofil_abdeckung`` (kWh-Zähler-Abdeckung) und
``SensorChecks._check_sensor_mapping_lts`` (Langzeitstatistik der zugeordneten Sensoren) wurden in Phasen geschnitten.
Der Worktree-GM ``daten-checker`` läuft ohne HA: die Drift-Prüfung kehrt dort vor der ersten Tageszeile um, die
LTS-Prüfung meldet nur «nicht erreichbar». Diese Proben sind **am HEAD vor dem Schnitt grün** gemessen und halten fest,
was der Schnitt nicht verschieben darf:

* **RF-64** — die Schwelle ``Δ ≥ 2 kWh UND Δ/max ≥ 5 %`` an der Kante (beide Achsen), Achse 1: eine Seite 0 meldet,
  beide 0 nicht, nur LTS-lesbare PV-Keys (#311); Achse 2 (N-201): beide Seiten > 0, ``batterie_*`` draußen, PV nicht
  doppelt; die Aktiv-Grenze je Tag (N-64), der LTS-Read einmal je Tag (ein Fehler überspringt den Tag in beiden Achsen),
  die 20er-Kappung samt Reihenfolge Tageszeilen · Komponentenzeilen · «… plus N weitere», je Komponente EIN Eintrag.
* **RF-65** — MQTT-Zählerstände zählen wie ein HA-Sensor (N-328), die Reihenfolge nach Typ (#214), die volle
  Meldungs-Reihenfolge (Basis · WARNING · Modul-Kind F-39 · gemappt · Anlagen-Zählerstand Achse C · Quelle Achse B),
  das «Alle»-Präfix, Wallbox-Schwäche B, Dienstwagen und Stilllegung außerhalb des Nenners.
* **RF-66** — die Reihenfolge der fünf Befunde und der zwei OK-Zeilen, Summen-fähig statt vorhanden (ein Stand braucht
  keine Summen-Spalte), die Kürzung der Beispiele nach fünf, die Sammelregeln (Live/Strategie/ohne ID/kein Dict,
  stillgelegt, verwaist, N-310-Adresse, Nicht-Energie-Feld), ohne Sensoren/ohne Mapping leer, ohne HA ein INFO.

Schwesterdateien: ``test_etappe_6_drift_check.py``, ``test_n201_drift_zweite_achse.py`` (RF-64) ·
``test_daten_checker_custom_import_quelle.py``, ``test_n328_mqtt_zaehler_erkennen.py``,
``test_daten_checker_wallbox_schwaeche_ab.py``, ``test_daten_checker_bkw_kind_deckt_f39.py``,
``test_daten_checker_pv_anlagenzaehler_deckt.py`` (RF-65) · ``test_daten_checker_lts_summen_spalte.py``,
``test_daten_checker_zaehler_helfer_empfehlung.py``, ``test_d3_zaehler_flankenpruefungen.py`` (RF-66). Keine DB, kein Netz,
keine Uhr: die Methoden bekommen ungespeicherte Model-Objekte und eine gestellte DB-Antwort (Muster
``test_etappe_6_drift_check.py``); die Tage sind fest, weil die gestellte DB das 90-Tage-Fenster nicht filtert.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.daten_checker import CheckSeverity, DatenChecker

T0 = date(2026, 3, 1)


# ─── RF-64: Drift-Prüfung ────────────────────────────────────────────────────


def _inv(inv_id, typ, bez=None, **kw):
    kw.setdefault("anschaffungsdatum", date(2024, 1, 1))
    kw.setdefault("aktiv", True)
    kw.setdefault("parameter", {})
    return Investition(id=inv_id, anlage_id=1, typ=typ, bezeichnung=bez or f"{typ} {inv_id}", **kw)


async def _drift(eedc_je_tag: dict, ha_je_tag, invs: list, aufrufe: list | None = None):
    """``eedc_je_tag``: {datum: komponenten_kwh}; ``ha_je_tag(datum, invs_by_id)`` → dict (oder wirft)."""
    tz_list = [
        SimpleNamespace(id=i, anlage_id=1, datum=d, komponenten_kwh=k)
        for i, (d, k) in enumerate(eedc_je_tag.items())
    ]
    db = MagicMock()
    n = {"n": 0}

    async def _execute(stmt):
        n["n"] += 1
        res = MagicMock()
        sc = MagicMock()
        sc.all = MagicMock(return_value=tz_list if n["n"] == 1 else invs)
        res.scalars = MagicMock(return_value=sc)
        return res

    db.execute = _execute

    async def _lts(anlage, invs_by_id, datum):
        if aufrufe is not None:
            aufrufe.append((datum, sorted(invs_by_id)))
        return ha_je_tag(datum, invs_by_id)

    async def _komp(db_, anlage_id, von, bis, komponenten_je_tag=None, *, gruppen=None):
        return dict(eedc_je_tag)

    with patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=SimpleNamespace(is_available=True)), \
            patch("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts", side_effect=_lts), \
            patch("backend.services.energie_profil.kanal_stunden.komponenten_der_tage", new=_komp), \
            patch("backend.services.kanal.konsistenz.spiegel_quellen_anzahl",   # N-790: Anlage ohne HA-Spiegel
                  new=AsyncMock(return_value=0)):
        return await DatenChecker(db)._check_datenquelle_drift(SimpleNamespace(id=1, sensor_mapping={}))


def _tageszeilen(erg):
    return [e for e in erg if e.action_kind == "reaggregate_day" and e.investition_id is None]


async def test_rf64_schwelle_beide_kanten_gleichzeitig_achse_1():
    """Δ = 2 kWh bei genau 5 % meldet; Δ = 2 bei 4 % und Δ = 1,8 bei 9 % bleiben still (UND, nicht ODER)."""
    d1, d2, d3 = T0, T0 + timedelta(days=1), T0 + timedelta(days=2)
    eedc = {d1: {"pv_3": 38.0}, d2: {"pv_3": 48.0}, d3: {"pv_3": 18.2}}
    ha = {d1: 40.0, d2: 50.0, d3: 20.0}
    erg = await _drift(eedc, lambda d, _i: {"pv_3": ha[d]}, [_inv(3, "pv-module")])
    zeilen = _tageszeilen(erg)
    assert [z.action_params["datum"] for z in zeilen] == [d1.isoformat()]
    assert zeilen[0].meldung == f"{d1.isoformat()}: PV 38,0 → HA 40,0 kWh (Δ +2,0 kWh, +5,0 %)"


async def test_rf64_schwelle_beide_kanten_gleichzeitig_achse_2():
    """Dieselbe Schwelle je Komponente: nur der Tag an der Kante (2 kWh, 5 %) zählt."""
    d1, d2, d3 = T0, T0 + timedelta(days=1), T0 + timedelta(days=2)
    eedc = {d1: {"wallbox_5": 38.0}, d2: {"wallbox_5": 48.0}, d3: {"wallbox_5": 18.2}}
    ha = {d1: 40.0, d2: 50.0, d3: 20.0}
    erg = await _drift(eedc, lambda d, _i: {"wallbox_5": ha[d]}, [_inv(5, "wallbox", "Box")])
    assert [e.meldung for e in erg] == [
        f"Box: 1 Tag(e) weichen von HA-Statistics ab (größte Abweichung {d1.isoformat()}: "
        "38,0 → 40,0 kWh, Δ +2,0 kWh, +5,0 %)"
    ]
    assert erg[0].investition_id == 5


async def test_rf64_achse_1_eine_seite_null_meldet_beide_null_nicht():
    """Achse 1 schließt nur «beide Seiten ≤ 0» aus — eedc 0 gegen HA 30 ist Drift, ein fehlender eedc-Key ebenso."""
    d1, d2, d3 = T0, T0 + timedelta(days=1), T0 + timedelta(days=2)
    eedc = {d1: {"pv_3": 0.0}, d2: {"netzbezug": 3.0}, d3: {"pv_3": 0.0}}
    ha = {d1: {"pv_3": 30.0}, d2: {"pv_3": 30.0}, d3: {"pv_3": 0.0}}
    erg = await _drift(eedc, lambda d, _i: ha[d], [_inv(3, "pv-module")])
    assert [z.action_params["datum"] for z in _tageszeilen(erg)] == [d1.isoformat(), d2.isoformat()]


async def test_rf64_achse_1_nur_lts_lesbare_pv_keys():
    """#311: ein PV-Key, den der LTS-Read nicht liefert, ist «nicht gelesen», nicht «HA = 0»."""
    eedc = {T0: {"pv_3": 30.0, "pv_4": 20.0}}
    erg = await _drift(eedc, lambda d, _i: {"pv_3": 30.0, "pv_4": None}, [_inv(3, "pv-module"), _inv(4, "pv-module")])
    assert [e.schwere for e in erg] == [CheckSeverity.OK.value]
    # Liest HA keinen PV-Key, findet am Tag gar kein Vergleich statt.
    erg = await _drift(eedc, lambda d, _i: {"wallbox_5": 1.0}, [_inv(3, "pv-module")])
    assert [e.schwere for e in erg] == [CheckSeverity.OK.value]


async def test_rf64_achse_2_beide_seiten_groesser_null_ohne_batterie_ohne_pv():
    """N-201: eine Seite 0 oder fehlend ist eine Lücke (anderer Turm); ``batterie_*`` und PV-Keys nie in Achse 2."""
    eedc = {T0: {"wallbox_5": 0.0, "batterie_6": 1.0, "pv_3": 30.0, "waermepumpe_8": "x"}}
    ha = {"wallbox_5": 10.0, "batterie_6": 9.0, "pv_3": 30.0, "eauto_7": 12.0, "waermepumpe_8": 20.0}
    erg = await _drift(eedc, lambda d, _i: ha, [_inv(3, "pv-module"), _inv(5, "wallbox"), _inv(7, "e-auto")])
    assert [e.schwere for e in erg] == [CheckSeverity.OK.value]


async def test_rf64_aktiv_grenze_je_tag():
    """N-64: der LTS-Read bekommt je Tag nur die an diesem Tag aktiven Investitionen."""
    vor, nach = date(2026, 1, 10), date(2026, 1, 20)
    still = date(2026, 1, 25)
    aufrufe: list = []
    invs = [
        _inv(3, "pv-module", anschaffungsdatum=date(2026, 1, 15)),
        _inv(4, "pv-module", stilllegungsdatum=date(2026, 1, 22)),
        _inv(5, "wallbox", aktiv=False),
    ]
    await _drift({vor: {}, nach: {}, still: {}}, lambda d, _i: {}, invs, aufrufe)
    assert aufrufe == [(vor, ["4"]), (nach, ["3", "4"]), (still, ["3"])]


async def test_rf64_lts_read_einmal_je_tag_und_fehler_ueberspringt_den_tag():
    """Der LTS-Read läuft EINMAL je Tag (die zweite Achse liest den aufgehobenen); ein Fehler nimmt den Tag aus beiden Achsen."""
    d1, d2 = T0, T0 + timedelta(days=1)
    aufrufe: list = []

    def _ha(d, _i):
        if d == d2:
            raise RuntimeError("Recorder weg")
        return {"pv_3": 40.0, "wallbox_5": 40.0}

    eedc = {d1: {"pv_3": 30.0, "wallbox_5": 30.0}, d2: {"pv_3": 1.0, "wallbox_5": 1.0}}
    erg = await _drift(eedc, _ha, [_inv(3, "pv-module"), _inv(5, "wallbox", "Box")], aufrufe)
    assert [a[0] for a in aufrufe] == [d1, d2]
    assert [e.action_params["datum"] for e in erg] == [d1.isoformat(), d1.isoformat()]
    assert erg[1].meldung.startswith("Box: 1 Tag(e)")


async def test_rf64_kappung_20_und_reihenfolge_tage_komponenten_rest():
    """23 Drift-Tage ⇒ 20 Tageszeilen nach |Δ| absteigend, dann die Komponentenzeile, zuletzt «… plus 3 weitere»."""
    eedc, ha = {}, {}
    for i in range(23):
        d = T0 + timedelta(days=i)
        eedc[d] = {"pv_3": 50.0, "wallbox_5": 10.0}
        ha[d] = {"pv_3": 50.0 + 3 + i, "wallbox_5": 10.0 + (5.0 if i == 4 else 0.0)}
    erg = await _drift(eedc, lambda d, _i: ha[d], [_inv(3, "pv-module"), _inv(5, "wallbox", "Box")])
    tage = _tageszeilen(erg)
    assert len(tage) == 20
    assert [z.action_params["datum"] for z in tage] == [(T0 + timedelta(days=i)).isoformat() for i in range(22, 2, -1)]
    assert len(erg) == 22
    assert erg[20].investition_id == 5 and erg[20].meldung.startswith("Box: 1 Tag(e)")
    assert erg[21].meldung == "… plus 3 weitere Tag(e) mit Drift"
    assert erg[21].action_kind is None


async def test_rf64_je_komponente_ein_eintrag_schlimmster_tag_groesste_zuerst():
    """N-201: je Komponente EIN Eintrag mit dem schlimmsten Tag als Ziel; die Komponente mit dem größten Δ zuerst."""
    eedc, ha = {}, {}
    for i, (wb, wp) in enumerate(((3.0, 9.0), (6.0, 0.0), (4.0, 0.0))):
        d = T0 + timedelta(days=i)
        eedc[d] = {"wallbox_5": 20.0, "waermepumpe_8": 30.0}
        ha[d] = {"wallbox_5": 20.0 + wb, "waermepumpe_8": 30.0 + wp}
    erg = await _drift(eedc, lambda d, _i: ha[d], [_inv(5, "wallbox", "Box"), _inv(8, "waermepumpe", "WP")])
    assert [e.investition_id for e in erg] == [8, 5]
    assert erg[0].meldung.startswith("WP: 1 Tag(e) weichen von HA-Statistics ab (größte Abweichung " + T0.isoformat())
    d_schlimm = (T0 + timedelta(days=1)).isoformat()
    assert erg[1].meldung.startswith(f"Box: 3 Tag(e) weichen von HA-Statistics ab (größte Abweichung {d_schlimm}")
    assert erg[1].action_params == {"anlage_id": 1, "datum": d_schlimm}
    assert "an 3 Tag(en)" in erg[1].details


# ─── RF-65: Energieprofil-Abdeckung ──────────────────────────────────────────


def _anlage(invs, mapping):
    a = Anlage(id=1, anlagenname="T", leistung_kwp=10.0, sensor_mapping=mapping)
    a.investitionen = invs
    return a


def _s(sid):
    return {"strategie": "sensor", "sensor_id": sid}


def _abdeckung(anlage, monatsdaten=None, mqtt=None):
    erg = DatenChecker(db=None)._check_energieprofil_abdeckung(anlage, monatsdaten, mqtt)
    return [e.meldung for e in erg if e.kategorie == "energieprofil_abdeckung"]


def test_rf65_mqtt_zaehlerstaende_zaehlen_wie_ha_sensor():
    """N-328: angekommene MQTT-Zählerstände decken Basis und Gerät — ohne sie (``None``) bleibt es bei den Warnungen."""
    a = _anlage([_inv(3, "pv-module")], {})
    mqtt = {"basis:einspeisung", "basis:netzbezug", "inv:3:pv_erzeugung_kwh"}
    m = _abdeckung(a, [], mqtt)
    assert m[:2] == [
        "Basis-Zähler (Einspeisung + Netzbezug) gemappt",
        "Alle 1 aktiven Komponenten haben kWh-Zähler gemappt",
    ]
    m = _abdeckung(a, [], None)
    assert m[:2] == [
        "Kein Basis-Zähler für: Einspeisung, Netzbezug",
        "1 von 1 Komponenten ohne vollständige kWh-Zähler-Abdeckung",
    ]


def test_rf65_reihenfolge_nach_typ_nicht_nach_id():
    """#214: die Details nennen die Wärmepumpe vor der Wallbox, auch wenn die Wallbox die kleinere ID hat."""
    a = _anlage([_inv(2, "wallbox", "Box"), _inv(9, "waermepumpe", "WP")], {"basis": {"einspeisung": _s("s.e"), "netzbezug": _s("s.n")}})
    erg = DatenChecker(db=None)._check_energieprofil_abdeckung(a, [])
    warn = [e for e in erg if e.schwere == CheckSeverity.WARNING]
    assert len(warn) == 1
    assert warn[0].details.endswith("Details: WP (waermepumpe): stromverbrauch_kwh; Box (wallbox): ladung_kwh")


def test_rf65_volle_meldungs_reihenfolge_mit_anlagen_zaehlerstand_und_modul_kind():
    """Basis · WARNING · Modul-Kind (F-39) · gemappt (ohne «Alle») · Anlagen-Zählerstand (Achse C) — in dieser Reihenfolge."""
    invs = [
        _inv(1, "balkonkraftwerk", "BKW"),
        _inv(2, "pv-module", "Modul", parent_investition_id=1),
        _inv(3, "waermepumpe", "WP"),
        _inv(4, "wallbox", "Box"),
        _inv(5, "speicher", "Akku"),
        _inv(6, "wechselrichter", "WR"),
        _inv(7, "e-auto", "Alt", stilllegungsdatum=date(2025, 1, 1)),
        _inv(8, "e-auto", "Dienst", parameter={"ist_dienstlich": True}),
    ]
    mapping = {
        "basis": {"einspeisung": _s("s.e"), "netzbezug": _s("s.n"), "pv_gesamt": _s("s.pv")},
        "investitionen": {
            "3": {"felder": {"stromverbrauch_kwh": _s("s.wp")}},
            "5": {"felder": {"ladung_kwh": _s("s.l"), "entladung_kwh": _s("s.el")}},
        },
    }
    m = _abdeckung(_anlage(invs, mapping), [])
    assert m[:5] == [
        "Basis-Zähler (Einspeisung + Netzbezug) gemappt",
        "1 von 5 Komponenten ohne vollständige kWh-Zähler-Abdeckung",
        "1 Balkonkraftwerk(e) über die zugeordneten PV-Module gedeckt",
        "2 aktiven Komponenten haben kWh-Zähler gemappt",
        "1 Erzeuger über den Anlagen-Zählerstand abgedeckt",
    ]


def test_rf65_achse_b_quelle_und_wallbox_schwaeche_b():
    """Achse B: ohne Zähler zählt die manuelle Quelle (Basis-Zeile und Quellen-Zeile); ein E-Auto unter einer Wallbox mit
    Zähler fällt aus dem Nenner (Wallbox-Schwäche B); gemappt ohne «Alle», weil eine Quelle daneben steht."""
    invs = [_inv(4, "wallbox", "Box"), _inv(6, "e-auto", "Auto"), _inv(5, "speicher", "Akku")]
    mapping = {"investitionen": {"4": {"felder": {"ladung_kwh": _s("s.wb")}}}}
    md = [SimpleNamespace(datenquelle=" "), SimpleNamespace(datenquelle="custom_import"), SimpleNamespace(datenquelle="csv")]
    m = _abdeckung(_anlage(invs, mapping), md)
    assert m[:3] == [
        "Basis-Zähler über Custom-Import befüllt",
        "1 aktiven Komponenten haben kWh-Zähler gemappt",
        "1 Komponente(n) über Custom-Import befüllt",
    ]


# ─── RF-66: Sensor-Mapping LTS ───────────────────────────────────────────────


class _Ha:
    is_available = True

    def __init__(self, fehlend=(), ohne_sum=()):
        self.fehlend, self.ohne_sum, self.gefragt = set(fehlend), set(ohne_sum), None

    def filter_summen_faehige_sensor_ids(self, sids):
        self.gefragt = sorted(sids)
        return ([s for s in sids if s not in self.fehlend | self.ohne_sum],
                [s for s in sids if s in self.ohne_sum], [s for s in sids if s in self.fehlend])


async def _lts(anlage, ha, monkeypatch):
    import backend.services.ha_statistics_service as ha_mod
    monkeypatch.setattr(ha_mod, "get_ha_statistics_service", lambda: ha)
    return await DatenChecker(db=None)._check_sensor_mapping_lts(anlage)


def _lts_anlage():
    invs = [_inv(3, "waermepumpe", "WP"), _inv(4, "sonstiges", "Gas", parameter={"kategorie": "zaehler"})]
    mapping = {
        "basis": {"einspeisung": _s("s.e_out"), "netzbezug": _s("s.e_in"), "pv_gesamt": _s("s.pv")},
        "investitionen": {
            "3": {"felder": {"stromverbrauch_kwh": _s("s.wp"), "wp_starts_anzahl": _s("s.starts"),
                             "wp_betriebsstunden": _s("s.stunden")}},
            "4": {"felder": {"zaehlerstand": _s("s.gas")}},
        },
    }
    return _anlage(invs, mapping)


async def test_rf66_reihenfolge_der_fuenf_befunde(monkeypatch):
    """kWh fehlt · Counter fehlt · kWh ohne Summe · Counter ohne Summe · Stand fehlt — keine OK-Zeile daneben."""
    ha = _Ha(fehlend={"s.e_out", "s.starts", "s.gas"}, ohne_sum={"s.e_in", "s.stunden"})
    erg = await _lts(_lts_anlage(), ha, monkeypatch)
    assert [e.meldung for e in erg] == [
        "1 kWh-Sensor(en) nicht in HA-Long-Term-Statistics",
        "1 Counter-Sensor(en) ohne state_class — Korrektur-Werkzeuge wirken nicht",
        "1 kWh-Sensor(en) ohne Summen-Spalte — Tages- und Stundenwerte bleiben leer",
        "1 Counter-Sensor(en) ohne Summen-Spalte — Korrektur-Werkzeuge wirken nicht",
        "1 Zählerstand-Sensor(en) nicht in HA-Long-Term-Statistics",
    ]
    assert ha.gefragt == sorted({"s.e_out", "s.e_in", "s.pv", "s.wp", "s.starts", "s.stunden", "s.gas"})


async def test_rf66_summen_faehig_statt_vorhanden_stand_ohne_summe_ist_ok(monkeypatch):
    """Ein Stand ohne Summen-Spalte ist in Ordnung (D3); ein kWh-Sensor ohne Summen-Spalte nicht — das kWh-OK entfällt."""
    ha = _Ha(ohne_sum={"s.gas", "s.pv"})
    erg = await _lts(_lts_anlage(), ha, monkeypatch)
    assert [(e.schwere, e.meldung) for e in erg] == [
        (CheckSeverity.WARNING, "1 kWh-Sensor(en) ohne Summen-Spalte — Tages- und Stundenwerte bleiben leer"),
        (CheckSeverity.OK, "Alle 1 Zählerstand-Sensor(en) in HA-Long-Term-Statistics verfügbar"),
    ]
    erg = await _lts(_lts_anlage(), _Ha(), monkeypatch)
    assert [e.meldung for e in erg] == [
        "Alle 1 Zählerstand-Sensor(en) in HA-Long-Term-Statistics verfügbar",
        "Alle 4 kWh-Sensor(en) im Mapping in HA-Long-Term-Statistics verfügbar",
    ]


@pytest.mark.parametrize("art", ["kwh_fehlt", "counter_fehlt", "kwh_ohne_sum", "counter_ohne_sum", "stand_fehlt"])
async def test_rf66_beispiele_nach_fuenf_gekuerzt(art, monkeypatch):
    """Jeder Befund nennt höchstens fünf Sensoren und zählt den Rest: «(+1 weitere)» bei sechs."""
    feld = {"kwh_fehlt": "stromverbrauch_kwh", "kwh_ohne_sum": "stromverbrauch_kwh", "counter_fehlt": "wp_starts_anzahl",
            "counter_ohne_sum": "wp_starts_anzahl", "stand_fehlt": "zaehlerstand"}[art]
    typ = "sonstiges" if art == "stand_fehlt" else "waermepumpe"
    invs = [_inv(i, typ, f"G{i}") for i in range(1, 7)]
    mapping = {"investitionen": {str(i): {"felder": {feld: _s(f"s.{i}")}} for i in range(1, 7)}}
    sids = {f"s.{i}" for i in range(1, 7)}
    ha = _Ha(ohne_sum=sids) if art.endswith("ohne_sum") else _Ha(fehlend=sids)
    erg = await _lts(_anlage(invs, mapping), ha, monkeypatch)
    assert len(erg) == 1 and erg[0].meldung.startswith("6 ")
    assert erg[0].details.endswith("(s.5) (+1 weitere)")
    assert "(s.6)" not in erg[0].details


async def test_rf66_sammelregeln(monkeypatch):
    """Live-Zuordnung, andere Strategie, ohne ID, kein Dict und stillgelegte Geräte fallen heraus; ein verwaister Eintrag
    bleibt («Inv. 99»), eine Innengeräte-Adresse wird aufgelöst (N-310), ein Preis-Feld ist nicht zuständig."""
    invs = [_inv(3, "waermepumpe", "WP"), _inv(5, "speicher", "Alt", stilllegungsdatum=date(2025, 1, 1)),
            _inv(6, "speicher", "Akku")]
    mapping = {
        "basis": {"einspeisung": {"strategie": "manuell", "sensor_id": "s.x"}, "netzbezug": _s(""),
                  "pv_gesamt": "kaputt", "live": {"leistung_w": "s.live"}, "strompreis": _s("s.preis")},
        "investitionen": {
            "3": {"felder": {"betriebsart_strom_kuehlen_kwh-3": _s("s.kuehl"), "x": "kein dict",
                             "stromverbrauch_kwh": {"strategie": "keine"}, "strom_heizen_kwh": _s("")},
                  "live": {"leistung_w": _s("s.wp_live")}},
            "4": "kein dict",
            "5": {"felder": {"ladung_kwh": _s("s.alt")}},
            "6": {"felder": {"speicher_ladepreis_cent": _s("s.ct")}},
            "99": {"felder": {"ladung_kwh": _s("s.weg")}},
        },
    }
    ha = _Ha(fehlend={"s.kuehl", "s.weg"})
    erg = await _lts(_anlage(invs, mapping), ha, monkeypatch)
    assert ha.gefragt == ["s.kuehl", "s.weg"]
    assert len(erg) == 1
    assert erg[0].details.endswith("Betroffen: WP: Strom Kühlbetrieb (s.kuehl); Inv. 99: Ladung gesamt (s.weg)")


async def test_rf66_leer_ohne_mapping_ohne_sensoren_und_info_ohne_ha(monkeypatch):
    """Ohne Mapping und ohne prüfbaren Sensor keine Zeile; ohne HA ein INFO statt einer Prüfung."""
    assert await _lts(_anlage([], {}), _Ha(), monkeypatch) == []
    assert await _lts(_anlage([], {"basis": {"strompreis": _s("s.p")}}), _Ha(), monkeypatch) == []
    weg = SimpleNamespace(is_available=False)
    erg = await _lts(_anlage([], {"basis": {"einspeisung": _s("s.e")}}), weg, monkeypatch)
    assert [(e.schwere, e.meldung) for e in erg] == [
        (CheckSeverity.INFO, "HA Long-Term-Statistics nicht erreichbar — Mapping-Prüfung übersprungen"),
    ]
