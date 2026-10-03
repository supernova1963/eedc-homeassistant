"""#341/#348 — Merkmale je Knoten im Live-Energiefluss (Bau A, Paket A1).

Der Energiefluss gruppiert künftig, was nicht in eine Reihe passt (Bau A §A3).
Entscheiden kann das nur der Client (er kennt die Breite), die Merkmale kennt
nur das Backend. Paket A1 liefert deshalb sechs optionale Felder je Knoten —
**reine Anreicherung**, keine Summe und kein Residual liest sie:

* ``typ`` — an jedem Investitions-Knoten, nie an ``netz``/``haushalt``/``pv_gesamt``;
* ``kategorie`` — nur bei Sonstiges, an **allen vier** Buchungszweigen;
* ``ausrichtung_label`` — nur ``pv_*``, nur bei gepflegter Ausrichtung
  (``pv_orientation.ausrichtung_label``: kein Süd-Default, Ost-West-Text vor
  Alt-Grad, ``0`` ist Süd, nicht lesbarer Freitext ist nicht gepflegt);
* ``traeger_id`` — Wechselrichter oder Balkonkraftwerk; der Rest-Knoten eines
  abtretenden BKW trägt seine eigene ID;
* ``traeger_label`` (Nachtrag A1b) — die Bezeichnung dieses Trägers, genau dann
  gesetzt, wenn ``traeger_id`` es ist (die Gruppe heißt „<Name> (n)");
* ``kapazitaet_kwh`` — nur ``batterie_*``, über den SoT-Helper;
* ``fahrzeuge`` + ``fahrzeuge_zuordnung`` — nur ``wallbox_*``, aus derselben
  Zuordnung wie ``parent_key``, mit beiden knotenlosen Auto-Klassen.

⛔ **Alle Proben laufen über die ROUTE** (``GET /api/live/{id}`` mit dem echten
Router und ``response_model``): FastAPI verwirft ein Feld, das der Builder
setzt, aber ``LiveKomponente`` nicht deklariert, **still** — ``abgabe`` steckt
seit jeher in genau dieser Falle. Eine Probe direkt am Builder sähe sie nicht.
Nur die Service-Grenze ist gestellt (Live-Werte, Tages-kWh, Betriebsmodus);
Investitionen kommen aus der Datenbank, mit echten IDs und dem
``aktiv_jetzt()``-Filter des Service.

Issues #341 (Rainer, „bei 4 Solarquellen zu eng") und #348 (Safi105,
„gruppieren"); Vorlage ``plans/vorlage-bau-a-energiefluss-gruppierung.md``
Fassung 2, §A1. Eine Datei für beide Issues (Master-Abweichung vom
Gegenentwurf: neben ``test_n348_…`` — anderer Fund — wäre ein
``test_348_``-Präfix eine vermeidbare Verwechslung).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from backend.api.deps import get_db
from backend.api.routes import live_dashboard
from backend.services import betriebsmodus_live
from backend.services import live_power_service as lps
from backend.services.pv_orientation import ausrichtung_label, hat_ausrichtung
from backend.tests import factories

#: Die Felder, die A1 (und der Nachtrag A1b: `traeger_label`) neu an einen Knoten legt.
NEUE_FELDER = (
    "typ", "kategorie", "ausrichtung_label", "traeger_id", "traeger_label",
    "kapazitaet_kwh", "fahrzeuge", "fahrzeuge_zuordnung",
)


# ── Prüfstand: der echte Router, gestellte Service-Grenze ────────────────────

@pytest_asyncio.fixture
async def abruf(db, monkeypatch):
    """``await abruf(anlage, basis, werte, live_map=None)`` → Response-JSON.

    ``werte`` ist nach Investition geschlüsselt (``{inv: {"leistung_w": …}}``)
    und wird hier auf ``str(inv.id)`` umgesetzt — so wie der Service sie
    liefert. ``live_map`` (gleiche Schlüsselform) nennt die Entities; ohne
    Angabe bekommt jedes Feld seine eigene, eine geteilte Entity (Dedup) muss
    die Probe ausdrücklich setzen.
    """
    stand: dict = {}

    def _collect(self, anlage, *args, **kwargs):  # noqa: ARG001
        return stand["basis"], stand["werte"]

    async def _keine_kwh(*args, **kwargs):  # noqa: ARG001
        return {}

    async def _kein_modus(*args, **kwargs):  # noqa: ARG001
        return {}

    monkeypatch.setattr(
        lps, "extract_live_config",
        lambda anlage: ({"einspeisung_w": "sensor.e"}, stand["live_map"], {}, {}),
    )
    monkeypatch.setattr(lps, "extract_quellen_live", lambda anlage: ({}, {}, set()))
    monkeypatch.setattr(lps, "HA_INTEGRATION_AVAILABLE", False)
    monkeypatch.setattr(lps.LivePowerService, "_collect_values", _collect)
    monkeypatch.setattr(lps, "safe_get_tages_kwh", _keine_kwh)
    monkeypatch.setattr(betriebsmodus_live, "lade_betriebsmodus_live", _kein_modus)

    app = FastAPI()
    app.include_router(live_dashboard.router, prefix="/api/live")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        async def _abruf(anlage, basis: dict, werte: dict, live_map: dict | None = None) -> dict:
            stand["basis"] = basis
            stand["werte"] = {str(inv.id): dict(v) for inv, v in werte.items()}
            if live_map is None:
                live_map = {
                    inv: {feld: f"sensor.{inv.id}.{feld}" for feld in v}
                    for inv, v in werte.items()
                }
            stand["live_map"] = {str(inv.id): dict(v) for inv, v in live_map.items()}
            antwort = await client.get(f"/api/live/{anlage.id}")
            assert antwort.status_code == 200, antwort.text
            return antwort.json()

        yield _abruf


async def _anlage(db):
    return await factories.anlage(db, anlagenname="Merkmale", standort_land="DE")


async def _inv(db, anlage, typ: str, bezeichnung: str | None = None, **felder):
    return await factories.investition(
        db, anlage.id, typ, bezeichnung=bezeichnung or typ, **felder,
    )


def _knoten(res: dict) -> dict[str, dict]:
    return {k["key"]: k for k in res["komponenten"]}


_NETZ = {"einspeisung_w": 0.0, "netzbezug_w": 500.0}


# ── typ ──────────────────────────────────────────────────────────────────────

async def test_typ_an_jedem_investitions_knoten_und_nie_an_netz_haushalt(db, abruf):
    """Jeder Investitions-Knoten trägt seinen Typ; ``netz``/``haushalt`` nie."""
    a = await _anlage(db)
    pv = await _inv(db, a, "pv-module")
    sp = await _inv(db, a, "speicher")
    wp = await _inv(db, a, "waermepumpe")
    wb = await _inv(db, a, "wallbox")
    auto = await _inv(db, a, "e-auto")
    so = await _inv(db, a, "sonstiges", parameter={"kategorie": "verbraucher"})
    bkw = await _inv(db, a, "balkonkraftwerk")
    res = await abruf(a, _NETZ, {
        pv: {"leistung_w": 3000.0}, sp: {"leistung_w": -500.0}, wp: {"leistung_w": 800.0},
        wb: {"leistung_w": 7000.0}, auto: {"leistung_w": 6800.0},
        so: {"leistung_w": 200.0}, bkw: {"leistung_w": 400.0},
    })
    k = _knoten(res)
    assert k[f"pv_{pv.id}"]["typ"] == "pv-module"
    assert k[f"pv_{bkw.id}"]["typ"] == "balkonkraftwerk"
    assert k[f"batterie_{sp.id}"]["typ"] == "speicher"
    assert k[f"waermepumpe_{wp.id}"]["typ"] == "waermepumpe"
    assert k[f"wallbox_{wb.id}"]["typ"] == "wallbox"
    assert k[f"eauto_{auto.id}"]["typ"] == "e-auto"
    assert k[f"sonstige_{so.id}"]["typ"] == "sonstiges"
    assert k["netz"]["typ"] is None
    assert k["haushalt"]["typ"] is None


async def test_pv_gesamt_traegt_keine_merkmale(db, abruf):
    """Der Summen-Knoten ohne Einzelstrings ist schon das Aggregat — kein Merkmal."""
    a = await _anlage(db)
    sp = await _inv(db, a, "speicher")
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 4000.0}, {sp: {"leistung_w": 500.0}})
    pv = _knoten(res)["pv_gesamt"]
    for feld in NEUE_FELDER:
        assert pv[feld] is None, feld


# ── kategorie ────────────────────────────────────────────────────────────────

async def test_kategorie_an_allen_vier_sonstiges_zweigen(db, abruf):
    """Erzeuger · Abgabe · Speicher (Bidirektional-Zweig) · Verbraucher/Zähler/leer (else).

    Der Sonstiges-Speicher läuft durch den Bidirektional-Zweig und heißt
    trotzdem ``sonstige_<id>`` (F-70) — gerade dort fehlte das Feld leicht.
    ``""`` ist „Automatisch" (N-573) und zählt als nicht gepflegt.
    """
    a = await _anlage(db)
    erz = await _inv(db, a, "sonstiges", "BHKW", parameter={"kategorie": "erzeuger"})
    abg = await _inv(db, a, "sonstiges", "Mieter", parameter={"kategorie": "abgabe"})
    spe = await _inv(db, a, "sonstiges", "Akku", parameter={"kategorie": "speicher"})
    vrb = await _inv(db, a, "sonstiges", "Pool", parameter={"kategorie": "verbraucher"})
    zae = await _inv(db, a, "sonstiges", "Zähler", parameter={"kategorie": "zaehler"})
    auto_kat = await _inv(db, a, "sonstiges", "Auto", parameter={"kategorie": ""})
    ohne = await _inv(db, a, "sonstiges", "Ohne", parameter={})
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 3000.0}, {
        erz: {"leistung_w": 900.0}, abg: {"leistung_w": 300.0}, spe: {"leistung_w": -700.0},
        vrb: {"leistung_w": 400.0}, zae: {"leistung_w": 100.0},
        auto_kat: {"leistung_w": 50.0}, ohne: {"leistung_w": 60.0},
    })
    k = _knoten(res)
    assert k[f"sonstige_{erz.id}"]["kategorie"] == "erzeuger"
    assert k[f"sonstige_{abg.id}"]["kategorie"] == "abgabe"
    assert k[f"sonstige_{spe.id}"]["kategorie"] == "speicher"
    assert k[f"sonstige_{spe.id}"]["erzeugung_kw"] == pytest.approx(0.7)  # wirklich Bidi-Zweig
    assert k[f"sonstige_{vrb.id}"]["kategorie"] == "verbraucher"
    assert k[f"sonstige_{zae.id}"]["kategorie"] == "zaehler"
    assert k[f"sonstige_{auto_kat.id}"]["kategorie"] is None
    assert k[f"sonstige_{ohne.id}"]["kategorie"] is None
    for key, knoten in k.items():
        assert knoten["typ"] == "sonstiges" or knoten["kategorie"] is None, key


async def test_kategorie_nie_ausserhalb_von_sonstiges(db, abruf):
    """Auch ein Speicher, eine Wallbox oder eine WP mit einem Schlüssel
    ``kategorie`` im ``parameter`` tragen das Feld nicht — es ist der
    Buchungszweig der Sonstigen, kein allgemeines Merkmal."""
    a = await _anlage(db)
    sp = await _inv(db, a, "speicher", parameter={"kategorie": "speicher"})
    wb = await _inv(db, a, "wallbox", parameter={"kategorie": "verbraucher"})
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 2000.0}, {
        sp: {"leistung_w": 300.0}, wb: {"leistung_w": 1000.0},
    })
    k = _knoten(res)
    assert k[f"batterie_{sp.id}"]["kategorie"] is None
    assert k[f"wallbox_{wb.id}"]["kategorie"] is None


# ── kapazitaet_kwh ───────────────────────────────────────────────────────────

async def test_kapazitaet_ueber_den_sot_helper_nur_am_speicher(db, abruf):
    """Nutzbar vor Brutto (E17-Fallback), Wert nur im ``parameter`` (#229-Klasse),
    und ⛔ nie aus der Mehrzweck-Spalte ``leistung_kwp``."""
    a = await _anlage(db)
    netto = await _inv(db, a, "speicher", "Netto",
                       parameter={"kapazitaet_kwh": 10.0, "nutzbare_kapazitaet_kwh": 9.2})
    brutto = await _inv(db, a, "speicher", "Brutto", parameter={"kapazitaet_kwh": 7.5})
    spalte = await _inv(db, a, "speicher", "Spalte", leistung_kwp=12.0, parameter={})
    so_akku = await _inv(db, a, "sonstiges", "Akku",
                         parameter={"kategorie": "speicher", "kapazitaet_kwh": 5.0})
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 3000.0}, {
        netto: {"leistung_w": 500.0}, brutto: {"leistung_w": -400.0},
        spalte: {"leistung_w": 300.0}, so_akku: {"leistung_w": 200.0},
    })
    k = _knoten(res)
    assert k[f"batterie_{netto.id}"]["kapazitaet_kwh"] == pytest.approx(9.2)
    assert k[f"batterie_{brutto.id}"]["kapazitaet_kwh"] == pytest.approx(7.5)
    assert k[f"batterie_{spalte.id}"]["kapazitaet_kwh"] is None
    assert k[f"sonstige_{so_akku.id}"]["kapazitaet_kwh"] is None


# ── fahrzeuge + fahrzeuge_zuordnung ──────────────────────────────────────────

async def test_eine_wallbox_eindeutig_mit_beiden_knotenlosen_autoklassen(db, abruf):
    """Eine Wallbox ⇒ ``eindeutig``. In ``fahrzeuge`` stehen:

    * das Auto mit eigenem Knoten (``kw`` aus dem Knoten, ``parent_key`` gesetzt),
    * das **SoC-only**-Auto (kein Knoten, ``kw=None``),
    * das **Dedup**-Auto — es teilt den Leistungssensor mit der Wallbox, der
      häufigste reale Aufbau — ebenfalls ohne Knoten, ``kw=None``.
    """
    a = await _anlage(db)
    wb = await _inv(db, a, "wallbox", "Carport")
    mit = await _inv(db, a, "e-auto", "ID.4")
    soc = await _inv(db, a, "e-auto", "Zoe")
    dup = await _inv(db, a, "e-auto", "Model 3")
    werte = {
        wb: {"leistung_w": 7000.0},
        mit: {"leistung_w": 3000.0, "soc": 52.4},
        soc: {"soc": 81.0},
        dup: {"leistung_w": 7000.0, "soc": 40.0},
    }
    live_map = {
        wb: {"leistung_w": "sensor.wb"},
        mit: {"leistung_w": "sensor.id4", "soc": "sensor.id4_soc"},
        soc: {"soc": "sensor.zoe_soc"},
        dup: {"leistung_w": "sensor.wb", "soc": "sensor.m3_soc"},
    }
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 9000.0}, werte, live_map)
    k = _knoten(res)
    wallbox = k[f"wallbox_{wb.id}"]
    assert wallbox["fahrzeuge_zuordnung"] == "eindeutig"
    assert wallbox["fahrzeuge"] == [
        {"investition_id": mit.id, "label": "ID.4", "soc": 52.0, "kw": 3.0, "v2h": False},
        {"investition_id": soc.id, "label": "Zoe", "soc": 81.0, "kw": None, "v2h": False},
        {"investition_id": dup.id, "label": "Model 3", "soc": 40.0, "kw": None, "v2h": False},
    ]
    assert k[f"eauto_{mit.id}"]["parent_key"] == f"wallbox_{wb.id}"
    assert f"eauto_{soc.id}" not in k and f"eauto_{dup.id}" not in k


async def test_zwei_wallboxen_geschaetzt_und_parent_key_aus_derselben_zuordnung(db, abruf):
    """Zwei Wallboxen ⇒ ``geschaetzt`` an beiden. Die Zuordnung ist EINE Quelle:
    das Knoten-Auto steht genau in der ``fahrzeuge``-Liste der Wallbox, auf die
    sein ``parent_key`` zeigt — und sie hängt nicht an der Reihenfolge, in der
    die Live-Werte ankommen (Investitions-IDs, reihum)."""
    a = await _anlage(db)
    wb1 = await _inv(db, a, "wallbox", "Garage")
    wb2 = await _inv(db, a, "wallbox", "Carport")
    zoe = await _inv(db, a, "e-auto", "Zoe")      # nur Ladestand, kleinste Auto-ID
    id4 = await _inv(db, a, "e-auto", "ID.4")     # eigener Knoten
    werte = {
        wb1: {"leistung_w": 0.0}, wb2: {"leistung_w": 11000.0},
        zoe: {"soc": 60.0}, id4: {"leistung_w": 11000.0, "soc": 30.0},
    }
    ergebnisse = []
    for reihenfolge in (list(werte), list(reversed(werte))):
        res = await abruf(a, {**_NETZ, "pv_gesamt_w": 12000.0},
                          {inv: werte[inv] for inv in reihenfolge})
        ergebnisse.append(res)
        k = _knoten(res)
        for wb in (wb1, wb2):
            assert k[f"wallbox_{wb.id}"]["fahrzeuge_zuordnung"] == "geschaetzt"
        eltern = k[f"eauto_{id4.id}"]["parent_key"]
        in_liste = [
            key for key in (f"wallbox_{wb1.id}", f"wallbox_{wb2.id}")
            if any(f["investition_id"] == id4.id for f in k[key]["fahrzeuge"])
        ]
        assert in_liste == [eltern]
        # Reihum nach ID: Zoe → erste Wallbox, ID.4 → zweite.
        assert eltern == f"wallbox_{wb2.id}"
        assert [f["investition_id"] for f in k[f"wallbox_{wb1.id}"]["fahrzeuge"]] == [zoe.id]
    assert ergebnisse[0]["komponenten"] != [] and (
        _knoten(ergebnisse[0])[f"eauto_{id4.id}"]["parent_key"]
        == _knoten(ergebnisse[1])[f"eauto_{id4.id}"]["parent_key"]
    )


async def test_v2h_auto_hinter_wallbox_meldet_richtung_ueber_das_vorzeichen(db, abruf):
    """``kw`` ist vorzeichenbehaftet: ein entladendes V2H-Auto steht mit negativem
    Wert in der Kachel — die Richtung, die Tooltip und Overlay (A4/A5) zeigen."""
    a = await _anlage(db)
    wb = await _inv(db, a, "wallbox")
    auto = await _inv(db, a, "e-auto", "Ioniq 5", parameter={"v2h_faehig": True})
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 1000.0}, {
        wb: {"leistung_w": -3000.0}, auto: {"leistung_w": -3000.0, "soc": 70.0},
    })
    fz = _knoten(res)[f"wallbox_{wb.id}"]["fahrzeuge"]
    assert fz == [{"investition_id": auto.id, "label": "Ioniq 5", "soc": 70.0,
                   "kw": -3.0, "v2h": True}]


async def test_ohne_live_wallbox_keine_fahrzeuge_und_kein_parent(db, abruf):
    """Liefert keine Wallbox live, ist das Auto ein eigenständiger Verbraucher —
    kein ``parent_key`` (unverändert), und niemand trägt ``fahrzeuge``."""
    a = await _anlage(db)
    await _inv(db, a, "wallbox")  # erfasst, aber ohne Live-Wert
    auto = await _inv(db, a, "e-auto")
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 1000.0}, {auto: {"leistung_w": 2000.0}})
    k = _knoten(res)
    assert k[f"eauto_{auto.id}"]["parent_key"] is None
    assert all(knoten["fahrzeuge"] is None for knoten in k.values())


# ── ausrichtung_label (über die Route) ───────────────────────────────────────

async def test_ausrichtung_label_ueber_die_route(db, abruf):
    """Die fünf tragenden Fälle der Vorlage, jeder an einem eigenen String:

    * ``ausrichtung_grad = 0`` ⇒ „Süd" (⛔ ``is not None``, nie truthy);
    * gar keine Ausrichtung ⇒ **kein** Label (die Süd-Default-Probe);
    * Ost-West-Text + liegengebliebener Alt-Grad ⇒ „Ost-West" (Präzedenz N-527);
    * nicht lesbarer Freitext („Süd-Ost") ⇒ nicht gepflegt;
    * −90° und „Ost" (Spalte) ⇒ dasselbe Label (gleiche Gruppe ⇔ gleiches Label).
    """
    a = await _anlage(db)
    null_grad = await _inv(db, a, "pv-module", "Null", parameter={"ausrichtung_grad": 0})
    ohne = await _inv(db, a, "pv-module", "Ohne", parameter={})
    ow = await _inv(db, a, "pv-module", "OW", ausrichtung="Ost-West",
                    parameter={"ausrichtung_grad": 0})
    frei = await _inv(db, a, "pv-module", "Frei", ausrichtung="Süd-Ost", parameter={})
    ost_grad = await _inv(db, a, "pv-module", "OstGrad", parameter={"ausrichtung_grad": -90})
    ost_text = await _inv(db, a, "pv-module", "OstText", ausrichtung="Ost", parameter={})
    res = await abruf(a, _NETZ, {inv: {"leistung_w": 500.0}
                                 for inv in (null_grad, ohne, ow, frei, ost_grad, ost_text)})
    k = _knoten(res)
    assert k[f"pv_{null_grad.id}"]["ausrichtung_label"] == "Süd"
    assert k[f"pv_{ohne.id}"]["ausrichtung_label"] is None
    assert k[f"pv_{ow.id}"]["ausrichtung_label"] == "Ost-West"
    assert k[f"pv_{frei.id}"]["ausrichtung_label"] is None
    assert k[f"pv_{ost_grad.id}"]["ausrichtung_label"] == "Ost"
    assert k[f"pv_{ost_text.id}"]["ausrichtung_label"] == "Ost"


def _pv(spalte=None, **parameter):
    """Ein Erzeuger mit Spalte ``ausrichtung`` (Text) und ``parameter``-JSON."""
    return SimpleNamespace(ausrichtung=spalte, parameter=parameter)


@pytest.mark.parametrize("inv,label", [
    (_pv(ausrichtung_grad=0), "Süd"),
    (_pv(ausrichtung_grad="0"), "Süd"),
    (_pv(ausrichtung_grad=-90), "Ost"),
    (_pv(ausrichtung_grad=90), "West"),
    (_pv(ausrichtung_grad=180), "Nord"),
    (_pv(ausrichtung_grad=-180), "Nord"),
    (_pv(ausrichtung_grad=-45), "Südost"),
    (_pv(ausrichtung_grad=45), "Südwest"),
    (_pv(ausrichtung_grad=-135), "Nordost"),
    (_pv(ausrichtung_grad=135), "Nordwest"),
    (_pv(ausrichtung_grad=20), "Süd"),
    (_pv(ausrichtung_grad=-70), "Ost"),
    (_pv("Südwest"), "Südwest"),
    (_pv(ausrichtung="süd"), "Süd"),
    (_pv(ausrichtung="Ost-West (gemischt)"), "Ost-West"),
    (_pv("east-west", ausrichtung_grad=0), "Ost-West"),
    (_pv(ausrichtung="Ost-West"), "Ost-West"),        # N-528: nur im parameter
    (_pv("Ost-West"), "Ost-West"),                    # Spalte
    (_pv(None, ausrichtung="West"), "West"),
    (_pv(None, ausrichtung=90), "West"),
    (_pv("West", ausrichtung_grad=0), "Süd"),          # Grad vor Text, wie get_pv_azimut
    (_pv(), None),
    (_pv(""), None),
    (_pv("Süd-Ost"), None),
    (_pv("SSW"), None),
    (_pv(ausrichtung_grad=""), None),
    (_pv(ausrichtung_grad=None), None),
])
def test_ausrichtung_label_faelle(inv, label):
    assert ausrichtung_label(inv) == label
    assert hat_ausrichtung(inv) is (label is not None)


def test_get_pv_azimut_behaelt_seinen_sued_default():
    """Die Gegenrichtung: der Prognose-Leser behält den Default — geteilt wird
    der Leser, nicht die Semantik."""
    from backend.services.pv_orientation import get_pv_azimut

    assert get_pv_azimut(_pv()) == 0
    assert get_pv_azimut(_pv(), default=7) == 7
    assert get_pv_azimut(_pv(ausrichtung_grad=0), default=7) == 0
    assert get_pv_azimut(_pv("Südost")) == -45
    assert get_pv_azimut(_pv("Süd-Ost"), default=11) == 11


# ── traeger_id ───────────────────────────────────────────────────────────────

async def test_traeger_id_wechselrichter_bkw_und_bkw_rest(db, abruf):
    """WR-Kind → WR-ID · BKW-Kind → BKW-ID · BKW-Rest → **eigene** ID (dieselbe
    Gruppe wie seine Module) · Modul ohne Parent und alleinstehendes BKW → keiner."""
    a = await _anlage(db)
    wr = await _inv(db, a, "wechselrichter", "WR")
    am_wr = await _inv(db, a, "pv-module", "Dach", parent_investition_id=wr.id)
    bkw = await _inv(db, a, "balkonkraftwerk", "BKW")
    am_bkw = await _inv(db, a, "pv-module", "Gaube", parent_investition_id=bkw.id)
    frei = await _inv(db, a, "pv-module", "Garage")
    solo = await _inv(db, a, "balkonkraftwerk", "Balkon")
    res = await abruf(a, _NETZ, {
        am_wr: {"leistung_w": 3000.0},
        bkw: {"leistung_w": 800.0}, am_bkw: {"leistung_w": 500.0},   # Rest 300 W
        frei: {"leistung_w": 1000.0}, solo: {"leistung_w": 400.0},
    })
    k = _knoten(res)
    assert k[f"pv_{am_wr.id}"]["traeger_id"] == wr.id
    assert k[f"pv_{am_bkw.id}"]["traeger_id"] == bkw.id
    assert k[f"pv_{bkw.id}"]["traeger_id"] == bkw.id
    assert k[f"pv_{bkw.id}"]["erzeugung_kw"] == pytest.approx(0.3)  # wirklich der Rest-Knoten
    assert k[f"pv_{frei.id}"]["traeger_id"] is None
    assert k[f"pv_{solo.id}"]["traeger_id"] is None
    # ⛔ Nie über parent_key — der zeichnete eine Linie zum Parent.
    assert all(k[key]["parent_key"] is None for key in k if key.startswith("pv_"))


async def test_stillgelegter_traeger_degradiert_definiert(db, abruf):
    """Fehlt der Parent in der Live-Menge (``aktiv_jetzt()``), trägt der String
    keinen Träger — die Kachel fällt definiert auf die letzte Stufe."""
    a = await _anlage(db)
    alt = await _inv(db, a, "wechselrichter", "Alt", stilllegungsdatum=date(2025, 1, 1))
    aus = await _inv(db, a, "wechselrichter", "Aus", aktiv=False)
    s1 = await _inv(db, a, "pv-module", "S1", parent_investition_id=alt.id)
    s2 = await _inv(db, a, "pv-module", "S2", parent_investition_id=aus.id)
    res = await abruf(a, _NETZ, {s1: {"leistung_w": 1000.0}, s2: {"leistung_w": 1000.0}})
    k = _knoten(res)
    assert k[f"pv_{s1.id}"]["traeger_id"] is None
    assert k[f"pv_{s2.id}"]["traeger_id"] is None


async def test_speicher_am_wechselrichter_bekommt_keinen_traeger(db, abruf):
    """``traeger_id`` ist ein PV-Merkmal — ein DC-Speicher mit WR-Parent trägt keins."""
    a = await _anlage(db)
    wr = await _inv(db, a, "wechselrichter")
    sp = await _inv(db, a, "speicher", parent_investition_id=wr.id)
    res = await abruf(a, {**_NETZ, "pv_gesamt_w": 1000.0}, {sp: {"leistung_w": 400.0}})
    assert _knoten(res)[f"batterie_{sp.id}"]["traeger_id"] is None


# ── traeger_label (Nachtrag A1b) ─────────────────────────────────────────────
#
# Die Response kannte keinen Wechselrichter-Namen — eine Träger-Gruppe hieß im
# Client „PV-Gruppe 1". `traeger_label` trägt den Namen, und zwar aus DERSELBEN
# Entscheidung wie `traeger_id` (`live_komponenten_builder._traeger`): gesetzt
# genau dann, wenn die ID gesetzt ist.

async def test_traeger_label_ist_der_name_des_traegers(db, abruf):
    """WR-Kind → Name des WR · BKW-Kind → Name des BKW · BKW-Rest → sein EIGENER
    Name (derselbe wie der seiner Gruppe) · ohne Träger → keiner."""
    a = await _anlage(db)
    wr = await _inv(db, a, "wechselrichter", "Fronius Symo")
    am_wr = await _inv(db, a, "pv-module", "Dach", parent_investition_id=wr.id)
    bkw = await _inv(db, a, "balkonkraftwerk", "Balkon Süd")
    am_bkw = await _inv(db, a, "pv-module", "Gaube", parent_investition_id=bkw.id)
    frei = await _inv(db, a, "pv-module", "Garage")
    solo = await _inv(db, a, "balkonkraftwerk", "Balkon")
    res = await abruf(a, _NETZ, {
        am_wr: {"leistung_w": 3000.0},
        bkw: {"leistung_w": 800.0}, am_bkw: {"leistung_w": 500.0},   # Rest 300 W
        frei: {"leistung_w": 1000.0}, solo: {"leistung_w": 400.0},
    })
    k = _knoten(res)
    assert k[f"pv_{am_wr.id}"]["traeger_label"] == "Fronius Symo"
    assert k[f"pv_{am_bkw.id}"]["traeger_label"] == "Balkon Süd"
    assert k[f"pv_{bkw.id}"]["traeger_label"] == "Balkon Süd"
    assert k[f"pv_{bkw.id}"]["erzeugung_kw"] == pytest.approx(0.3)  # wirklich der Rest-Knoten
    assert k[f"pv_{frei.id}"]["traeger_label"] is None
    assert k[f"pv_{solo.id}"]["traeger_label"] is None


async def test_traeger_label_genau_dann_wenn_traeger_id(db, abruf):
    """An JEDEM Knoten der Response: ``traeger_label`` gesetzt ⇔ ``traeger_id``
    gesetzt — über alle Träger-Fälle, einen stillgelegten und einen inaktiven
    Parent, einen DC-Speicher am WR und die Nicht-PV-Knoten."""
    a = await _anlage(db)
    wr = await _inv(db, a, "wechselrichter", "WR")
    alt = await _inv(db, a, "wechselrichter", "Alt", stilllegungsdatum=date(2025, 1, 1))
    aus = await _inv(db, a, "wechselrichter", "Aus", aktiv=False)
    bkw = await _inv(db, a, "balkonkraftwerk", "BKW")
    werte = {
        await _inv(db, a, "pv-module", "S1", parent_investition_id=wr.id): {"leistung_w": 1000.0},
        await _inv(db, a, "pv-module", "S2", parent_investition_id=alt.id): {"leistung_w": 900.0},
        await _inv(db, a, "pv-module", "S3", parent_investition_id=aus.id): {"leistung_w": 800.0},
        await _inv(db, a, "pv-module", "S4", parent_investition_id=bkw.id): {"leistung_w": 300.0},
        bkw: {"leistung_w": 600.0},                                     # Rest 300 W
        await _inv(db, a, "pv-module", "S5"): {"leistung_w": 700.0},
        await _inv(db, a, "speicher", "DC", parent_investition_id=wr.id): {"leistung_w": 400.0},
        await _inv(db, a, "waermepumpe", "WP"): {"leistung_w": 900.0},
    }
    res = await abruf(a, _NETZ, werte)
    knoten = res["komponenten"]
    mit_id = [k["key"] for k in knoten if k["traeger_id"] is not None]
    assert len(mit_id) == 3                        # S1 (WR) · S4 (BKW) · BKW-Rest
    for k in knoten:
        assert (k["traeger_label"] is None) == (k["traeger_id"] is None), k["key"]


async def test_stillgelegter_traeger_hat_weder_id_noch_label(db, abruf):
    """Fehlt der Parent in der Live-Menge (``aktiv_jetzt()``), tragen die Strings
    BEIDE Felder nicht — kein Name eines Geräts, das nicht mehr läuft."""
    a = await _anlage(db)
    alt = await _inv(db, a, "wechselrichter", "Alt", stilllegungsdatum=date(2025, 1, 1))
    aus = await _inv(db, a, "wechselrichter", "Aus", aktiv=False)
    s1 = await _inv(db, a, "pv-module", "S1", parent_investition_id=alt.id)
    s2 = await _inv(db, a, "pv-module", "S2", parent_investition_id=aus.id)
    res = await abruf(a, _NETZ, {s1: {"leistung_w": 1000.0}, s2: {"leistung_w": 1000.0}})
    k = _knoten(res)
    for s in (s1, s2):
        assert k[f"pv_{s.id}"]["traeger_id"] is None
        assert k[f"pv_{s.id}"]["traeger_label"] is None


def test_demo_daten_tragen_die_namen_ihrer_zwei_wechselrichter():
    """Die Demo-Anlage (Lab-Durchklick): jeder PV-String trägt den Namen seines
    Demo-Wechselrichters, und das Feld überlebt das Response-Modell."""
    daten = live_dashboard.LiveDashboardResponse(
        **live_dashboard._generate_demo_data(1, "Demo"),
    ).model_dump()
    pv = [k for k in daten["komponenten"] if k["key"].startswith("pv_")]
    assert len(pv) == 6
    namen = {k["traeger_id"]: k["traeger_label"] for k in pv}
    assert namen == {20: "WR Hausdach", 21: "WR Garage"}
    for k in pv:
        assert k["traeger_label"] is not None and k["traeger_id"] is not None


# ── Bilanz bitgleich: reine Anreicherung ─────────────────────────────────────
#
# Die Response ist feldweise dieselbe wie vor A1 — bis auf die neuen Felder
# (die Serialisierung trägt jetzt an jedem Knoten `"typ": null` usw., deshalb
# kein Bytevergleich). Die Sollwerte `_VORHER` sind die Ausgabe der Route auf
# HEAD `2aa53742` (vor A1), gemessen am 28.09. mit dem Vergleichsskript des
# Bauberichts (`opus-berichte/BAU-A-A1-A2.md`) — als Literal, damit sie nicht aus
# dem neuen Code abgeleitet werden. Schlüssel sind auf Namen normiert
# (`pv_<id>` → `pv_Dach`), damit die Probe nicht an Autoinkrement-IDs hängt.

async def _k1_haus(db):
    """Zwei Strings am WR (Süd per Grad, Ost per Text), Speicher entlädt, WP mit
    Heizen/Warmwasser-Split, Netzbezug."""
    a = await _anlage(db)
    wr = await _inv(db, a, "wechselrichter", "WR")
    sued = await _inv(db, a, "pv-module", "Sued", parent_investition_id=wr.id,
                      parameter={"ausrichtung_grad": 0}, leistung_kwp=6.0)
    ost = await _inv(db, a, "pv-module", "Ost", parent_investition_id=wr.id,
                     ausrichtung="Ost", leistung_kwp=4.0)
    sp = await _inv(db, a, "speicher", "Akku", parameter={"kapazitaet_kwh": 10.0})
    wp = await _inv(db, a, "waermepumpe", "WP")
    werte = {
        sued: {"leistung_w": 3200.0}, ost: {"leistung_w": 1100.0},
        sp: {"leistung_w": -800.0, "soc": 64.0},
        wp: {"leistung_heizen_w": 1500.0, "leistung_warmwasser_w": 300.0},
    }
    namen = {x.id: x.bezeichnung for x in (wr, sued, ost, sp, wp)}
    return a, {"einspeisung_w": 0.0, "netzbezug_w": 200.0}, werte, None, namen


async def _k2_emobilitaet(db):
    """PV-Summensensor, zwei Wallboxen, drei Autos: mit eigenem Knoten, nur
    Ladestand, Leistungssensor mit der ersten Wallbox geteilt (Dedup)."""
    a = await _anlage(db)
    wb1 = await _inv(db, a, "wallbox", "Garage")
    wb2 = await _inv(db, a, "wallbox", "Carport")
    id4 = await _inv(db, a, "e-auto", "ID4")
    zoe = await _inv(db, a, "e-auto", "Zoe")
    m3 = await _inv(db, a, "e-auto", "M3")
    werte = {
        wb1: {"leistung_w": 7000.0}, wb2: {"leistung_w": 0.0},
        id4: {"leistung_w": 6800.0, "soc": 50.0}, zoe: {"soc": 81.0},
        m3: {"leistung_w": 7000.0, "soc": 33.0},
    }
    live_map = {
        wb1: {"leistung_w": "sensor.wb1"}, wb2: {"leistung_w": "sensor.wb2"},
        id4: {"leistung_w": "sensor.id4", "soc": "sensor.id4_soc"},
        zoe: {"soc": "sensor.zoe_soc"},
        m3: {"leistung_w": "sensor.wb1", "soc": "sensor.m3_soc"},
    }
    namen = {x.id: x.bezeichnung for x in (wb1, wb2, id4, zoe, m3)}
    basis = {"einspeisung_w": 0.0, "netzbezug_w": 1000.0, "pv_gesamt_w": 6000.0}
    return a, basis, werte, live_map, namen


async def _k3_sonstige_bkw_v2h(db):
    """Abtretendes BKW mit Modul (Rest 300 W), alle vier Sonstiges-Zweige und ein
    V2H-Auto ohne Wallbox, das entlädt (F-69), Einspeisung."""
    a = await _anlage(db)
    bkw = await _inv(db, a, "balkonkraftwerk", "BKW")
    gaube = await _inv(db, a, "pv-module", "Gaube", parent_investition_id=bkw.id)
    erz = await _inv(db, a, "sonstiges", "BHKW", parameter={"kategorie": "erzeuger"})
    abg = await _inv(db, a, "sonstiges", "Mieter", parameter={"kategorie": "abgabe"})
    spe = await _inv(db, a, "sonstiges", "Heimakku", parameter={"kategorie": "speicher"})
    vrb = await _inv(db, a, "sonstiges", "Pool", parameter={"kategorie": "verbraucher"})
    v2h = await _inv(db, a, "e-auto", "Ioniq", parameter={"v2h_faehig": True})
    werte = {
        bkw: {"leistung_w": 800.0}, gaube: {"leistung_w": 500.0},
        erz: {"leistung_w": 900.0}, abg: {"leistung_w": 300.0},
        spe: {"leistung_w": -700.0}, vrb: {"leistung_w": 400.0},
        v2h: {"leistung_w": -2000.0, "soc": 70.0},
    }
    namen = {x.id: x.bezeichnung for x in (bkw, gaube, erz, abg, spe, vrb, v2h)}
    return a, {"einspeisung_w": 500.0, "netzbezug_w": 0.0}, werte, None, namen


KONSTELLATIONEN = {
    "k1_haus": _k1_haus,
    "k2_emobilitaet": _k2_emobilitaet,
    "k3_sonstige_bkw_v2h": _k3_sonstige_bkw_v2h,
}


def _normiert(res: dict, namen: dict[int, str]) -> dict:
    """Response ohne Zeitstempel und ohne die neuen Felder, Schlüssel auf Namen."""
    import re

    def _key(k):
        if k is None:
            return None
        m = re.fullmatch(r"(.*)_(\d+)", k)
        return f"{m.group(1)}_{namen[int(m.group(2))]}" if m and int(m.group(2)) in namen else k

    out = {k: v for k, v in res.items() if k != "zeitpunkt"}
    out["komponenten"] = [
        {**{f: w for f, w in knoten.items() if f not in NEUE_FELDER},
         "key": _key(knoten["key"]), "parent_key": _key(knoten.get("parent_key"))}
        for knoten in res["komponenten"]
    ]
    out["gauges"] = [{**g, "key": _key(g["key"])} for g in res["gauges"]]
    return out


# N-603 (03.10.2026): das Label des Restverbrauchs-Knotens heißt „Restverbrauch" (bis dahin „Haushalt") — die
# einzige bewusste Änderung an diesem Abzug (drei Stellen); Schlüssel und Werte unverändert.
_VORHER: dict = {'k1_haus': {'anlage_id': 1,
             'anlage_name': 'Merkmale',
             'verfuegbar': True,
             'komponenten': [{'key': 'pv_Sued',
                              'label': 'Sued',
                              'icon': 'sun',
                              'erzeugung_kw': 3.2,
                              'verbrauch_kw': None,
                              'parent_key': None,
                              'leistung_kwp': 6.0,
                              'betriebsmodus': None,
                              'betriebsmodus_label': None},
                             {'key': 'pv_Ost',
                              'label': 'Ost',
                              'icon': 'sun',
                              'erzeugung_kw': 1.1,
                              'verbrauch_kw': None,
                              'parent_key': None,
                              'leistung_kwp': 4.0,
                              'betriebsmodus': None,
                              'betriebsmodus_label': None},
                             {'key': 'batterie_Akku',
                              'label': 'Akku',
                              'icon': 'battery',
                              'erzeugung_kw': 0.8,
                              'verbrauch_kw': None,
                              'parent_key': None,
                              'leistung_kwp': None,
                              'betriebsmodus': None,
                              'betriebsmodus_label': None},
                             {'key': 'waermepumpe_WP',
                              'label': 'WP',
                              'icon': 'heater',
                              'erzeugung_kw': None,
                              'verbrauch_kw': 1.8,
                              'parent_key': None,
                              'leistung_kwp': None,
                              'betriebsmodus': None,
                              'betriebsmodus_label': None},
                             {'key': 'netz',
                              'label': 'Stromnetz',
                              'icon': 'zap',
                              'erzeugung_kw': 0.2,
                              'verbrauch_kw': None,
                              'parent_key': None,
                              'leistung_kwp': None,
                              'betriebsmodus': None,
                              'betriebsmodus_label': None},
                             {'key': 'haushalt',
                              'label': 'Restverbrauch',
                              'icon': 'home',
                              'erzeugung_kw': None,
                              'verbrauch_kw': 3.5,
                              'parent_key': None,
                              'leistung_kwp': None,
                              'betriebsmodus': None,
                              'betriebsmodus_label': None}],
             'summe_erzeugung_kw': 5.3,
             'summe_verbrauch_kw': 5.3,
             'summe_pv_kw': 4.3,
             'gauges': [{'key': 'netz',
                         'label': 'Netz',
                         'wert': 200.0,
                         'min_wert': -200.0,
                         'max_wert': 200.0,
                         'einheit': 'W'},
                        {'key': 'soc_Akku',
                         'label': 'Akku',
                         'wert': 64.0,
                         'min_wert': 0.0,
                         'max_wert': 100.0,
                         'einheit': '%'},
                        {'key': 'pv_leistung',
                         'label': 'PV-Leistung',
                         'wert': 43.0,
                         'min_wert': 0.0,
                         'max_wert': 120.0,
                         'einheit': '% kWp'},
                        {'key': 'autarkie',
                         'label': 'Autarkie',
                         'wert': 96.0,
                         'min_wert': 0.0,
                         'max_wert': 100.0,
                         'einheit': '%'},
                        {'key': 'eigenverbrauch',
                         'label': 'Eigenverbr.',
                         'wert': 100.0,
                         'min_wert': 0.0,
                         'max_wert': 100.0,
                         'einheit': '%'}],
             'heute_pv_kwh': None,
             'heute_einspeisung_kwh': None,
             'heute_netzbezug_kwh': None,
             'heute_eigenverbrauch_kwh': None,
             'gestern_pv_kwh': None,
             'gestern_einspeisung_kwh': None,
             'gestern_netzbezug_kwh': None,
             'gestern_eigenverbrauch_kwh': None,
             'heute_kwh_pro_komponente': None,
             'warmwasser_temperatur_c': None,
             'innengeraete': None},
 'k2_emobilitaet': {'anlage_id': 1,
                    'anlage_name': 'Merkmale',
                    'verfuegbar': True,
                    'komponenten': [{'key': 'wallbox_Garage',
                                     'label': 'Garage',
                                     'icon': 'plug',
                                     'erzeugung_kw': None,
                                     'verbrauch_kw': 7.0,
                                     'parent_key': None,
                                     'leistung_kwp': None,
                                     'betriebsmodus': None,
                                     'betriebsmodus_label': None},
                                    {'key': 'wallbox_Carport',
                                     'label': 'Carport',
                                     'icon': 'plug',
                                     'erzeugung_kw': None,
                                     'verbrauch_kw': 0.0,
                                     'parent_key': None,
                                     'leistung_kwp': None,
                                     'betriebsmodus': None,
                                     'betriebsmodus_label': None},
                                    {'key': 'eauto_ID4',
                                     'label': 'ID4',
                                     'icon': 'car',
                                     'erzeugung_kw': None,
                                     'verbrauch_kw': 6.8,
                                     'parent_key': 'wallbox_Garage',
                                     'leistung_kwp': None,
                                     'betriebsmodus': None,
                                     'betriebsmodus_label': None},
                                    {'key': 'pv_gesamt',
                                     'label': 'PV Gesamt 10.0 kWp',
                                     'icon': 'sun',
                                     'erzeugung_kw': 6.0,
                                     'verbrauch_kw': None,
                                     'parent_key': None,
                                     'leistung_kwp': None,
                                     'betriebsmodus': None,
                                     'betriebsmodus_label': None},
                                    {'key': 'netz',
                                     'label': 'Stromnetz',
                                     'icon': 'zap',
                                     'erzeugung_kw': 1.0,
                                     'verbrauch_kw': None,
                                     'parent_key': None,
                                     'leistung_kwp': None,
                                     'betriebsmodus': None,
                                     'betriebsmodus_label': None},
                                    {'key': 'haushalt',
                                     'label': 'Restverbrauch',
                                     'icon': 'home',
                                     'erzeugung_kw': None,
                                     'verbrauch_kw': 0.0,
                                     'parent_key': None,
                                     'leistung_kwp': None,
                                     'betriebsmodus': None,
                                     'betriebsmodus_label': None}],
                    'summe_erzeugung_kw': 7.0,
                    'summe_verbrauch_kw': 7.0,
                    'summe_pv_kw': 6.0,
                    'gauges': [{'key': 'netz',
                                'label': 'Netz',
                                'wert': 1000.0,
                                'min_wert': -1000.0,
                                'max_wert': 1000.0,
                                'einheit': 'W'},
                               {'key': 'soc_ID4',
                                'label': 'ID4',
                                'wert': 50.0,
                                'min_wert': 0.0,
                                'max_wert': 100.0,
                                'einheit': '%'},
                               {'key': 'soc_Zoe',
                                'label': 'Zoe',
                                'wert': 81.0,
                                'min_wert': 0.0,
                                'max_wert': 100.0,
                                'einheit': '%'},
                               {'key': 'soc_M3',
                                'label': 'M3',
                                'wert': 33.0,
                                'min_wert': 0.0,
                                'max_wert': 100.0,
                                'einheit': '%'},
                               {'key': 'pv_leistung',
                                'label': 'PV-Leistung',
                                'wert': 60.0,
                                'min_wert': 0.0,
                                'max_wert': 120.0,
                                'einheit': '% kWp'},
                               {'key': 'autarkie',
                                'label': 'Autarkie',
                                'wert': 86.0,
                                'min_wert': 0.0,
                                'max_wert': 100.0,
                                'einheit': '%'},
                               {'key': 'eigenverbrauch',
                                'label': 'Eigenverbr.',
                                'wert': 100.0,
                                'min_wert': 0.0,
                                'max_wert': 100.0,
                                'einheit': '%'}],
                    'heute_pv_kwh': None,
                    'heute_einspeisung_kwh': None,
                    'heute_netzbezug_kwh': None,
                    'heute_eigenverbrauch_kwh': None,
                    'gestern_pv_kwh': None,
                    'gestern_einspeisung_kwh': None,
                    'gestern_netzbezug_kwh': None,
                    'gestern_eigenverbrauch_kwh': None,
                    'heute_kwh_pro_komponente': None,
                    'warmwasser_temperatur_c': None,
                    'innengeraete': None},
 'k3_sonstige_bkw_v2h': {'anlage_id': 1,
                         'anlage_name': 'Merkmale',
                         'verfuegbar': True,
                         'komponenten': [{'key': 'pv_BKW',
                                          'label': 'BKW',
                                          'icon': 'sun',
                                          'erzeugung_kw': 0.3,
                                          'verbrauch_kw': None,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'pv_Gaube',
                                          'label': 'Gaube',
                                          'icon': 'sun',
                                          'erzeugung_kw': 0.5,
                                          'verbrauch_kw': None,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'sonstige_BHKW',
                                          'label': 'BHKW',
                                          'icon': 'wrench',
                                          'erzeugung_kw': 0.9,
                                          'verbrauch_kw': None,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'sonstige_Mieter',
                                          'label': 'Mieter',
                                          'icon': 'wrench',
                                          'erzeugung_kw': None,
                                          'verbrauch_kw': 0.3,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'sonstige_Heimakku',
                                          'label': 'Heimakku',
                                          'icon': 'wrench',
                                          'erzeugung_kw': 0.7,
                                          'verbrauch_kw': None,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'sonstige_Pool',
                                          'label': 'Pool',
                                          'icon': 'wrench',
                                          'erzeugung_kw': None,
                                          'verbrauch_kw': 0.4,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'eauto_Ioniq',
                                          'label': 'Ioniq',
                                          'icon': 'car',
                                          'erzeugung_kw': 2.0,
                                          'verbrauch_kw': None,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'netz',
                                          'label': 'Stromnetz',
                                          'icon': 'zap',
                                          'erzeugung_kw': None,
                                          'verbrauch_kw': 0.5,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None},
                                         {'key': 'haushalt',
                                          'label': 'Restverbrauch',
                                          'icon': 'home',
                                          'erzeugung_kw': None,
                                          'verbrauch_kw': 3.2,
                                          'parent_key': None,
                                          'leistung_kwp': None,
                                          'betriebsmodus': None,
                                          'betriebsmodus_label': None}],
                         'summe_erzeugung_kw': 4.4,
                         'summe_verbrauch_kw': 4.4,
                         'summe_pv_kw': 0.8,
                         'gauges': [{'key': 'netz',
                                     'label': 'Netz',
                                     'wert': -500.0,
                                     'min_wert': -500.0,
                                     'max_wert': 500.0,
                                     'einheit': 'W'},
                                    {'key': 'soc_Ioniq',
                                     'label': 'Ioniq',
                                     'wert': 70.0,
                                     'min_wert': 0.0,
                                     'max_wert': 100.0,
                                     'einheit': '%'},
                                    {'key': 'pv_leistung',
                                     'label': 'PV-Leistung',
                                     'wert': 8.0,
                                     'min_wert': 0.0,
                                     'max_wert': 120.0,
                                     'einheit': '% kWp'},
                                    {'key': 'autarkie',
                                     'label': 'Autarkie',
                                     'wert': 100.0,
                                     'min_wert': 0.0,
                                     'max_wert': 100.0,
                                     'einheit': '%'},
                                    {'key': 'eigenverbrauch',
                                     'label': 'Eigenverbr.',
                                     'wert': 100.0,
                                     'min_wert': 0.0,
                                     'max_wert': 100.0,
                                     'einheit': '%'}],
                         'heute_pv_kwh': None,
                         'heute_einspeisung_kwh': None,
                         'heute_netzbezug_kwh': None,
                         'heute_eigenverbrauch_kwh': None,
                         'gestern_pv_kwh': None,
                         'gestern_einspeisung_kwh': None,
                         'gestern_netzbezug_kwh': None,
                         'gestern_eigenverbrauch_kwh': None,
                         'heute_kwh_pro_komponente': None,
                         'warmwasser_temperatur_c': None,
                         'innengeraete': None}}


@pytest.mark.parametrize("name", list(KONSTELLATIONEN))
async def test_bilanz_bitgleich_bis_auf_die_neuen_felder(db, abruf, name):
    a, basis, werte, live_map, namen = await KONSTELLATIONEN[name](db)
    res = await abruf(a, basis, werte, live_map)
    assert _normiert(res, namen) == _VORHER[name]
