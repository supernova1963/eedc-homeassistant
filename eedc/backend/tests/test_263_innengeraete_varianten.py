"""#263: die Variantenmatrix — jede Kombination, jede Fläche.

**Warum diese Datei neben `test_263_innengeraete.py` steht.** Dort steht je
Eigenschaft eine Probe mit einem Sprengsatz — „greift die Basis-Key-Auflösung?",
„räumt das Löschen auf?". Hier steht die andere Frage, die Gernot am 2026-08-21
gestellt hat: *kommt bei JEDER Datenlage auf JEDER Fläche die richtige Zahl an?*

Die Matrix ist bewusst vollständig statt beispielhaft — die Klasse von Fehlern,
die eedc wiederholt getroffen hat, entsteht genau dort: eine Größe ist an drei
von vier Stellen richtig (F-52: „drei von vier Sichten richtig, eine falsch";
#236: „Filter auf einer Schicht reicht nicht bei parallelen Pfaden").

**Varianten** (Zeilen) × **Flächen** (Spalten):

| | Datenlage |
| --- | --- |
| V1 | Luft-Wasser — muss bitgleich bleiben |
| V2 | Luft-Luft, nichts zugeordnet |
| V3 | Luft-Luft, nur Modus-Signal ⇒ abgeleitet |
| V4 | Luft-Luft, Betriebsart-Zähler am Gerät ⇒ gemessen |
| V5 | Luft-Luft + Liste, Zähler je Innengerät ⇒ Σ |
| V6 | Luft-Luft + Liste, Gerätefeld UND Innengeräte ⇒ Gerätefeld |
| V7 | Luft-Luft + Liste, Modus UND Zähler ⇒ gemessen, nie addiert |
| V8 | Luft-Luft, nur Lüften/Entfeuchten gemessen |
| V9 | zwei Geräte gemischt (eines gemessen, eines abgeleitet) |

Flächen: Komponenten-Hub · Cockpit Monat · Cockpit Jahr · Monatsabschluss ·
Datenquellen-Fläche · Live-Bild.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.betriebsmodus import (
    BETRIEBSART_NUTZENERGIE_FELD,
    BETRIEBSART_STROM_FELD,
    ENTFEUCHTEN,
    HEIZEN,
    KUEHLEN,
    LUEFTEN,
    MODUS_ABDECKUNG_FELD,
    MODUS_STROM_FELD,
)
from backend.core.field_definitions import (
    feld_je_innengeraet,
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
)
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.investition import InvestitionMonatsdaten  # noqa: F401
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)

JAHR, MONAT = 2025, 6

LISTE = [{"id": 1, "bezeichnung": "Büro"}, {"id": 3, "bezeichnung": "Wohnzimmer"}]

#: Der Gesamtverbrauch aller Varianten — damit die Teilmengen vergleichbar sind.
GESAMT = 100.0


def _p(art="luft_luft", liste=None) -> dict:
    p: dict = {"wp_art": art, "effizienz_modus": "gesamt_jaz", "jaz": 3.5}
    if liste:
        p["innengeraete"] = liste
    return p


# ─── Die neun Datenlagen ────────────────────────────────────────────────────

VARIANTEN: dict[str, tuple[dict, dict, dict]] = {
    # name: (parameter, verbrauch_daten, erwartung)
    "V1_luft_wasser": (
        _p("luft_wasser"),
        {"stromverbrauch_kwh": GESAMT, "heizenergie_kwh": 300.0},
        {"split": False},
    ),
    "V2_luft_luft_leer": (
        _p(),
        {"stromverbrauch_kwh": GESAMT},
        {"split": False},
    ),
    "V3_nur_modus": (
        _p(),
        {"stromverbrauch_kwh": GESAMT,
         MODUS_STROM_FELD[HEIZEN]: 20.0,
         MODUS_STROM_FELD[KUEHLEN]: 60.0,
         MODUS_ABDECKUNG_FELD: 500.0},
        {"split": True, "gemessen": False, "heizen": 20.0, "kuehlen": 60.0,
         "rest": 20.0, "abdeckung": 500.0},
    ),
    "V4_zaehler_am_geraet": (
        _p(),
        {"stromverbrauch_kwh": GESAMT,
         BETRIEBSART_STROM_FELD[HEIZEN]: 25.0,
         BETRIEBSART_STROM_FELD[KUEHLEN]: 55.0},
        {"split": True, "gemessen": True, "heizen": 25.0, "kuehlen": 55.0,
         "rest": 20.0, "abdeckung": 0.0},
    ),
    "V5_zaehler_je_innengeraet": (
        _p(liste=LISTE),
        {"stromverbrauch_kwh": GESAMT,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 30.0,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3): 12.0,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[HEIZEN], 1): 8.0},
        {"split": True, "gemessen": True, "heizen": 8.0, "kuehlen": 42.0,
         "rest": 50.0, "abdeckung": 0.0},
    ),
    "V6_geraet_schlaegt_innengeraete": (
        _p(liste=LISTE),
        {"stromverbrauch_kwh": GESAMT,
         BETRIEBSART_STROM_FELD[KUEHLEN]: 70.0,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 30.0,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3): 12.0},
        # 70, NICHT 112 (Summe) und nicht 42 (nur die Innengeräte).
        {"split": True, "gemessen": True, "heizen": 0.0, "kuehlen": 70.0,
         "rest": 30.0, "abdeckung": 0.0},
    ),
    "V7_gemessen_schlaegt_abgeleitet": (
        _p(liste=LISTE),
        {"stromverbrauch_kwh": GESAMT,
         MODUS_STROM_FELD[HEIZEN]: 20.0,
         MODUS_STROM_FELD[KUEHLEN]: 60.0,
         MODUS_ABDECKUNG_FELD: 500.0,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 30.0,
         feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3): 12.0},
        # **Ganz oder gar nicht:** Sobald ein Betriebsart-Zähler da ist, gilt
        # die Messung für die ganze Zeile. Heizen steht auf 0, weil dafür kein
        # Zähler existiert — nicht auf 20 aus der Rechnung. Sonst trüge ein
        # Balken zwei Herkünfte unter einem Etikett.
        {"split": True, "gemessen": True, "heizen": 0.0, "kuehlen": 42.0,
         "rest": 58.0, "abdeckung": 500.0},
    ),
    "V8_nur_lueften_entfeuchten": (
        _p(),
        {"stromverbrauch_kwh": GESAMT,
         BETRIEBSART_STROM_FELD[LUEFTEN]: 5.0,
         BETRIEBSART_STROM_FELD[ENTFEUCHTEN]: 7.0},
        # Heizen/Kühlen bleiben 0 — der Block erscheint trotzdem, weil gemessen
        # wurde.
        #
        # ⛔ **Hier stand bis zum 26.08.2026 `"rest": 100.0`** mit der Begründung
        # „‚Nicht aufgeteilt' trägt Lüften und Entfeuchten mit". Das hielt den
        # Entscheid vom 25.08. fest (*erst differenzieren, wenn Anwender es
        # verlangen*) — und der ist durch **E4** abgelöst (Konzept §2.3, 26.08.:
        # *sie erscheinen in der Aufteilung, bekommen aber keine Kennzahl*).
        # Die Probe hatte recht, solange die Regel galt; sie wird umgestellt,
        # nicht gelöscht.
        #
        # 100 − 5 − 7 = 88: die beiden gemessenen Betriebsarten haben jetzt
        # eigene Segmente und verlassen die Restmenge. Ohne den Abzug stünde
        # dieselbe Menge zweimal.
        {"split": True, "gemessen": True, "heizen": 0.0, "kuehlen": 0.0,
         "lueften": 5.0, "entfeuchten": 7.0, "rest": 88.0, "abdeckung": 0.0},
    ),
}


async def _baue(db, parameter: dict, daten: dict):
    """Anlage + eine Wärmepumpe + eine Monatszeile."""
    anlage = Anlage(anlagenname="Varianten", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=JAHR, monat=MONAT, verbrauch_daten=daten,
    ))
    await db.commit()
    return anlage, inv


# ─── Fläche 1: Komponenten-Hub ──────────────────────────────────────────────

@pytest.mark.parametrize("name", list(VARIANTEN))
async def test_komponenten_hub(db, name):
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard

    parameter, daten, erwartet = VARIANTEN[name]
    anlage, _inv = await _baue(db, parameter, daten)

    antwort = await get_waermepumpe_dashboard(anlage.id, strompreis_cent=30.0, db=db)
    z = antwort[0].zusammenfassung

    if not erwartet["split"]:
        assert "modus_strom_heizen_kwh" not in z, (
            f"{name}: eine Aufteilung wird gezeigt, wo es keine gibt")
        return

    assert z.get("modus_gemessen", False) is erwartet["gemessen"], name
    assert z["modus_strom_heizen_kwh"] == pytest.approx(erwartet["heizen"]), name
    assert z["modus_strom_kuehlen_kwh"] == pytest.approx(erwartet["kuehlen"]), name
    # E4: Lüften/Entfeuchten haben eigene Segmente. Die Varianten ohne eigene
    # Erwartung tragen 0 — dort gibt es keine solchen Zähler.
    assert z["modus_strom_lueften_kwh"] == pytest.approx(erwartet.get("lueften", 0.0)), name
    assert z["modus_strom_entfeuchten_kwh"] == pytest.approx(
        erwartet.get("entfeuchten", 0.0)), name
    assert z["modus_nicht_aufgeteilt_kwh"] == pytest.approx(erwartet["rest"]), name
    assert z["modus_abdeckung_h"] == pytest.approx(erwartet["abdeckung"]), name


# ─── Fläche 2: Cockpit → Monat ──────────────────────────────────────────────

@pytest.mark.parametrize("name", list(VARIANTEN))
async def test_cockpit_monat(db, name):
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    parameter, daten, erwartet = VARIANTEN[name]
    anlage, _inv = await _baue(db, parameter, daten)

    antwort = await get_aktueller_monat(anlage.id, jahr=JAHR, monat=MONAT, db=db)

    if not erwartet["split"]:
        assert antwort.wp_modus_strom_heizen_kwh is None, name
        assert antwort.wp_modus_strom_kuehlen_kwh is None, name
        return

    assert bool(antwort.wp_modus_gemessen) is erwartet["gemessen"], name
    assert antwort.wp_modus_strom_heizen_kwh == pytest.approx(erwartet["heizen"]), name
    assert antwort.wp_modus_strom_kuehlen_kwh == pytest.approx(erwartet["kuehlen"]), name
    # E4: dieselben vier Segmente wie im Hub — die beiden Flächen dürfen für
    # dieselbe Anlage keine verschiedenen Restmengen ausweisen.
    assert antwort.wp_modus_strom_lueften_kwh == pytest.approx(
        erwartet.get("lueften", 0.0)), name
    assert antwort.wp_modus_strom_entfeuchten_kwh == pytest.approx(
        erwartet.get("entfeuchten", 0.0)), name
    assert antwort.wp_modus_nicht_aufgeteilt_kwh == pytest.approx(erwartet["rest"]), name


# ─── Die Invariante, quer über alle Varianten ───────────────────────────────

@pytest.mark.parametrize("name", list(VARIANTEN))
async def test_teilmengen_ueberschreiten_nie_den_gesamtwert(db, name):
    """Σ Teilmengen + Rest == Gesamtverbrauch, und keine Teilmenge > Gesamt.

    Das ist die Probe gegen die Doppelzählung: würde eedc irgendwo Gerätefeld
    **und** Innengeräte addieren (V6) oder gemessen **und** abgeleitet (V7),
    liefe die Summe über den Gesamtwert und der Rest würde negativ.
    """
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard

    parameter, daten, erwartet = VARIANTEN[name]
    anlage, _inv = await _baue(db, parameter, daten)
    z = (await get_waermepumpe_dashboard(
        anlage.id, strompreis_cent=30.0, db=db))[0].zusammenfassung

    if not erwartet["split"]:
        return
    heizen = z["modus_strom_heizen_kwh"]
    kuehlen = z["modus_strom_kuehlen_kwh"]
    # E4: seit dem 26.08. sind es vier Teilmengen, nicht zwei. Ohne die beiden
    # neuen hier wäre die Invariante blind für genau den Fehler, den sie fangen
    # soll — eine Menge, die ihr Segment verlässt, ohne aus dem Rest zu gehen.
    lueften = z["modus_strom_lueften_kwh"]
    entfeuchten = z["modus_strom_entfeuchten_kwh"]
    rest = z["modus_nicht_aufgeteilt_kwh"]
    teilmengen = heizen + kuehlen + lueften + entfeuchten
    assert teilmengen <= GESAMT + 1e-6, f"{name}: Teilmengen > Gesamt"
    assert rest >= 0, f"{name}: negativer Rest ⇒ irgendwo wurde addiert"
    assert teilmengen + rest == pytest.approx(GESAMT), name


# ─── Fläche 3: Monatsabschluss + Fläche 4: Datenquellen ─────────────────────

@pytest.mark.parametrize("name", list(VARIANTEN))
def test_monatsabschluss_bietet_genau_die_passenden_felder(name):
    parameter, _daten, _erwartet = VARIANTEN[name]
    felder = {f["feld"] for f in get_felder_fuer_investition("waermepumpe", parameter)}

    if parameter["wp_art"] != "luft_luft":
        assert not any(f.startswith("betriebsart_") for f in felder), (
            f"{name}: Betriebsart-Felder an einer Luft-Wasser-Wärmepumpe")
        return

    # Alle acht am Gerät …
    assert BETRIEBSART_STROM_FELD[LUEFTEN] in felder
    assert BETRIEBSART_NUTZENERGIE_FELD[ENTFEUCHTEN] in felder
    # … und je Innengerät genau die der gepflegten IDs.
    ids = {g["id"] for g in parameter.get("innengeraete", [])}
    for gid in ids:
        assert feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], gid) in felder
    fremde = {f for f in felder if f.endswith("-2")}
    assert fremde == set(), f"{name}: Felder einer nicht existierenden ID {fremde}"


@pytest.mark.parametrize("name", list(VARIANTEN))
async def test_datenquellen_flaeche_zeigt_dieselben_felder(db, name):
    """**Die ROUTE**, nicht die Registry: was der Anwender zuzuordnen bekommt."""
    from backend.api.routes.datenquellen import get_datenquellen_felder

    parameter, daten, _erwartet = VARIANTEN[name]
    anlage, inv = await _baue(db, parameter, daten)

    antwort = await get_datenquellen_felder(anlage.id, db=db)
    gruppe = next(g for g in antwort["gruppen"] if g["id"] == f"inv:{inv.id}")
    felder = {f["feld"] for f in gruppe["felder"]}

    if parameter["wp_art"] != "luft_luft":
        # ⛔ Hier stand bis zum 26.08.2026 `assert not any(...)` — die Fläche
        # durfte an einer Luft-Wasser-WP **kein** Betriebsart-Feld zeigen.
        # R1/W-2 hat das abgelöst (MartyBr, T89667 #200: getrennter Kühlzähler
        # an genau so einer Anlage). Sie stehen jetzt hinter „Weitere Größen
        # erfassen" — die Fläche bleibt kurz, der Weg ist offen.
        erweitert = {f["feld"] for f in gruppe["felder"] if f.get("erweitert")}
        vorn = {f["feld"] for f in gruppe["felder"] if not f.get("erweitert")}
        assert not any(f.startswith("betriebsart_") for f in vorn), (
            f"{name}: Betriebsart-Felder in der ERSTEN REIHE einer Luft-Wasser-WP")
        assert {f for f in felder if f.startswith("betriebsart_")} <= erweitert, (
            f"{name}: Betriebsart-Feld ohne Erweitert-Marke")
        assert "soll_temperatur_c" not in felder, name
        return

    assert BETRIEBSART_STROM_FELD[KUEHLEN] in felder, name
    assert "soll_temperatur_c" in felder and "ist_temperatur_c" in felder, name
    for gid in {g["id"] for g in parameter.get("innengeraete", [])}:
        assert feld_je_innengeraet("ist_temperatur_c", gid) in felder, name
        assert feld_je_innengeraet(BETRIEBSART_STROM_FELD[HEIZEN], gid) in felder, name
    # Der Betriebsmodus bleibt EIN Feld je Gerät.
    assert "betriebsmodus" in felder
    assert not any(f.startswith("betriebsmodus-") for f in felder), name


@pytest.mark.parametrize("name", list(VARIANTEN))
async def test_ein_zustandsfeld_bekommt_nie_ein_mqtt_topic(db, name):
    """Quer über alle Varianten: kein `climate`-Feld wird als Topic angeboten.

    Ein Topic dafür wäre eine Lücke, die niemand schließen kann — der
    MQTT-Parser ist `float(payload)`.
    """
    from backend.api.routes.datenquellen import get_datenquellen_felder

    parameter, daten, _erwartet = VARIANTEN[name]
    anlage, inv = await _baue(db, parameter, daten)
    antwort = await get_datenquellen_felder(anlage.id, db=db)
    gruppe = next(g for g in antwort["gruppen"] if g["id"] == f"inv:{inv.id}")

    for f in gruppe["felder"]:
        if f["feld"].startswith("betriebsmodus"):
            assert not f.get("standard_topic"), f"{name}: {f['feld']} hat ein Topic"
            assert f.get("nur_ha") is True, f"{name}: {f['feld']} ist nicht HA-only"
        if f["feld"].startswith("betriebsart_"):
            assert f.get("standard_topic"), (
                f"{name}: {f['feld']} ist eine Zahl und braucht ein Topic")
            assert f.get("zustand") is False, f"{name}: {f['feld']} gilt als Zustand"


# ─── Fläche 5: Live-Bild ────────────────────────────────────────────────────

class _Anlage:
    """Die Anlage, die der Live-Builder für Bilanzgrößen braucht."""
    id = 1
    anlagenname = "Varianten"
    leistung_kwp = 10.0

def test_live_zeigt_je_innengeraet_und_summiert_nichts():
    """Die Innengeräte-Werte sind Anzeige, keine Bilanz.

    Sie dürfen weder in `summe_verbrauch_kw` noch in die Komponenten-Liste
    laufen: die Geräteleistung zählt dort bereits, und ein Innengerät ist ihre
    Teilmenge.
    """
    from backend.services.live_komponenten_builder import build_komponenten

    class _Inv:
        id = 7
        typ = "waermepumpe"
        bezeichnung = "Klima"
        parameter = _p(liste=LISTE)

    inv_values = {"7": {
        "leistung_w": 600.0,
        feld_je_innengeraet("leistung_w", 1): 677.0,
        feld_je_innengeraet("ist_temperatur_c", 1): 22.4,
        feld_je_innengeraet("soll_temperatur_c", 1): 21.0,
        feld_je_innengeraet("leistung_w", 3): 14.0,
    }}
    ergebnis = build_komponenten(
        anlage=_Anlage(), basis_values={}, inv_values=inv_values,
        investitionen={"7": _Inv()}, inv_live_map={"7": {}},
    )

    geraete = {g["innengeraet_id"]: g for g in ergebnis["innengeraete"]}
    assert set(geraete) == {1, 3}, "beide Innengeräte mit Werten erwartet"
    assert geraete[1]["bezeichnung"] == "Büro"
    assert geraete[1]["ist_temperatur_c"] == pytest.approx(22.4)
    assert geraete[1]["leistung_w"] == pytest.approx(677.0)
    assert geraete[3]["ist_temperatur_c"] is None, "kein Sensor ⇒ kein Wert, keine 0"

    # Die Bilanz kennt nur die Geräteleistung (600 W = 0,6 kW).
    assert ergebnis["summe_verbrauch_kw"] == pytest.approx(0.6), (
        "die Innengeräte-Leistung darf die Summe nicht erhöhen")
    assert len(ergebnis["komponenten"]) == 1, "ein Gerät, eine Komponente"


def test_live_laesst_ein_innengeraet_ohne_jeden_wert_weg():
    from backend.services.live_komponenten_builder import build_komponenten

    class _Inv:
        id = 7
        typ = "waermepumpe"
        bezeichnung = "Klima"
        parameter = _p(liste=LISTE)

    ergebnis = build_komponenten(
        anlage=_Anlage(), basis_values={}, inv_values={"7": {"leistung_w": 600.0}},
        investitionen={"7": _Inv()}, inv_live_map={"7": {}},
    )
    assert ergebnis["innengeraete"] == [], (
        "ein Innengerät ohne Sensor bekommt keine leere Kachel")


# ─── V9: zwei Geräte, gemischte Herkunft ────────────────────────────────────

async def test_v9_zwei_geraete_gemischt(db):
    """Eine Klimaanlage gemessen, eine Wärmepumpe abgeleitet — die
    anlagenweite Summe trägt beide, und zwar je Gerät richtig aufgelöst."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="Zwei", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()

    gemessen = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=_p(liste=LISTE),
    )
    abgeleitet = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=_p(),
    )
    db.add_all([gemessen, abgeleitet])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=gemessen.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={
            "stromverbrauch_kwh": 100.0,
            feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 1): 42.0,
        },
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=abgeleitet.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={
            "stromverbrauch_kwh": 200.0,
            MODUS_STROM_FELD[HEIZEN]: 150.0,
            MODUS_ABDECKUNG_FELD: 700.0,
        },
    ))
    await db.commit()

    antwort = await get_aktueller_monat(anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert antwort.wp_modus_strom_kuehlen_kwh == pytest.approx(42.0)
    assert antwort.wp_modus_strom_heizen_kwh == pytest.approx(150.0)
    # Bezug sind BEIDE Geräte (300), Rest = 300 − 42 − 150.
    assert antwort.wp_modus_nicht_aufgeteilt_kwh == pytest.approx(108.0)
    assert bool(antwort.wp_modus_gemessen) is True


# ─── Registry-Deckung: kein Feld ohne Einheit, Label, Hinweis ───────────────

def test_jedes_neue_feld_traegt_label_einheit_und_hinweis():
    """Gernots Doktrin: eedc sagt exakt, was es je Feld braucht."""
    felder = [
        f for f in get_alle_felder_fuer_investition("waermepumpe", _p(liste=LISTE))
        if f["feld"].startswith("betriebsart_")
    ]
    assert len(felder) == 8 * 3, "8 Felder am Gerät + 8 je Innengerät × 2"
    for f in felder:
        assert f["einheit"] == "kWh", f
        assert f["label"] and not f["label"].endswith(":"), f
        assert len(f.get("hinweis", "")) > 80, f"Hinweis zu dünn: {f['feld']}"
        assert f.get("csv_suffix"), f
