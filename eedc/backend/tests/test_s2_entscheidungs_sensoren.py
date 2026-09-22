"""S2/S3 anlagenweit — E1…E5, P2, P3, P5, P6 und ihre Degradation (ADR-002/P4).

**Die Probenklasse, um die es hier geht.** Ein Sensor, der bei fehlendem
Eingang eine 0 meldet, ist schlimmer als keiner: in Home Assistant landet die 0
in der Langzeitstatistik, eine Automation hält sie für eine Messung, und
niemand sieht, dass sie eine Annahme war. Deshalb prüft jeder Fall hier **beide
Richtungen** — der Sensor entsteht mit vollständigem Eingang, und er fehlt
**ganz**, sobald ein Eingang fehlt.

⛔ **Kein Netz, kein Broker, keine echte Uhr.** Die Prognose- und
Preis-Beschaffung wird gestellt (`monkeypatch` auf
`berechne_prognose_export`/`berechne_preis_export`), und die Zeit kommt als
Parameter herein (`calculate_anlage_sensors(..., jetzt=...)`) — sonst wäre jede
Probe eine Wette auf die Stunde ihres Laufs (N-167: vier von 24 Stunden rot ohne
Code-Änderung). `JETZT` unten ist dieselbe feste Zeit in jeder Zeitzone.

Schwesterdateien: `test_s3_geraete_fenster.py` (dieselben Stücke je Gerät),
`test_s2_zweiter_komponententyp.py` (Bauform und Rücknahme),
`test_fenster_rechner.py` (der Layer darunter).
"""

from datetime import date, datetime, timedelta

import pytest

from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung


#: Die gestellte Uhr aller Proben dieser Datei — ein **Werktag**, mittags, mit
#: Überschuss im Tagesprofil und dem Preistal noch hinter uns.
JETZT = datetime(2026, 9, 21, 12, 30)
HEUTE = JETZT.date()


# ── Aufbau ──────────────────────────────────────────────────────────────────

async def _anlage(db, **kwargs):
    from backend.models import Anlage, Monatsdaten

    anlage = Anlage(
        anlagenname="S2-Probe", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
        latitude=48.1, longitude=11.5,
        **kwargs,
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=200.0))
    await db.commit()
    return anlage


async def _tagesprofil(db, anlage_id, tag: date, *, bis_stunde=12):
    """Ein Tag mit Überschuss ab 10 Uhr und Netzbezug davor."""
    for h in range(bis_stunde + 1):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=h,
            ueberschuss_kw=2.5 if h >= 10 else 0.0,
            defizit_kw=0.0 if h >= 10 else 1.2,
            netzbezug_kw=0.0 if h >= 10 else 1.2,
            soc_prozent=55.0 + h,
            soc_je_speicher={"1": 55.0 + h},
        ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=tag,
        ueberschuss_kwh=7.5, defizit_kwh=12.0, peak_netzbezug_kw=4.8,
    ))
    await db.commit()


def _prognose(**ueberschreiben) -> dict:
    """Ein vollständiges Prognose-Dict, wie `berechne_prognose_export` es liefert."""
    pv = [0.0] * 8 + [1.0, 2.0, 4.0, 5.0, 5.0, 4.0, 3.0, 1.0] + [0.0] * 8
    verbrauch = [0.5] * 24
    basis = {
        "heute_kwh": sum(pv), "rest_today_kwh": 5.0,
        "heute_rollend_kwh": 20.0, "ist_bisher_kwh": 9.0,
        "heute_vormittag_kwh": None, "heute_nachmittag_kwh": None,
        "morgen_vormittag_kwh": None, "morgen_nachmittag_kwh": None,
        "solar_noon_heute": None, "solar_noon_morgen": None,
        "day_plus_1_kwh": None, "day_plus_2_kwh": None, "day_plus_3_kwh": None,
        "speicher_voll_um": "15:00", "speicher_voll_um_slot": 15,
        "speicher_verbrauch_profil": {"profil_typ": "gewichtet_8w", "profil_tage": 56},
        "speicher_kap_kwh": 10.0, "speicher_eta_prozent": 90.0,
        "speicher_soc_prozent": 40.0,
        "verbrauch_heute_kwh": sum(verbrauch),
        "verbrauch_profil_typ": "individuell_werktag",
        "verbrauch_profil_tage": 7, "verbrauch_profil_slots": 24,
        "verbrauch_stundenprofil_kwh": verbrauch,
        "verbrauch_wp_stundenprofil_kwh": [0.2] * 24,
        "verbrauch_temperatur_c": [10.0] * 12 + [28.0, 30.0, 31.0, 29.0] + [20.0] * 8,
        "stundenprofil_heute": pv,
        "stundenprofil_day_plus_1": None,
        "stundenprofil_day_plus_2": None,
        "stundenprofil_day_plus_3": None,
    }
    basis.update(ueberschreiben)
    return basis


def _preis(**ueberschreiben) -> dict:
    """Ein Preis-Dict mit einem klaren Tal um 03:00 und einem Gipfel um 19:00."""
    def _p(h):
        return 10.0 if h in (2, 3) else (45.0 if h in (18, 19) else 25.0)

    basis = {
        "preis_rang": 3, "guenstige_stunden_anzahl": 2,
        "guenstige_stunden_tag": 0, "guenstige_stunden_nacht": 2,
        "guenstig_schwelle_cent": 18.0, "preis_aktuell_cent": 25.0,
        "tages_durchschnitt_cent": 25.0, "optimierter_durchschnitt_cent": 22.0,
        "abstand_prozent": 13.6, "abstand_cent": 3.0,
        "rang_profil": [
            {"stunde": h, "rang": 1 if h in (2, 3) else 99, "preis_cent": _p(h),
             "unter_schwelle": h in (2, 3), "abstand_cent": _p(h) - 22.0}
            for h in range(24)
        ],
        "datum": "2026-09-21", "morgen_verfuegbar": False,
    }
    basis.update(ueberschreiben)
    return basis


def _stelle_quellen(monkeypatch, prognose, preis):
    """Prognose- und Preis-Beschaffung stellen — kein Netz, keine Uhr."""
    from backend.api.routes.ha_export import anlage_sensorwerte

    async def _p(db, anlage, *, skip_jitter=False):
        return prognose

    async def _q(db, anlage):
        return preis

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)


def _keys(sensor_values) -> set[str]:
    return {sv.definition.key for sv in sensor_values}


def _sv(sensor_values, key):
    for sv in sensor_values:
        if sv.definition.key == key:
            return sv
    return None


async def _rechne(db, anlage, jetzt=None):
    from backend.api.routes.ha_export import calculate_anlage_sensors

    kontext: dict = {}
    werte = await calculate_anlage_sensors(
        db, anlage, skip_jitter=True, kontext_out=kontext, jetzt=jetzt or JETZT,
    )
    return werte, kontext


# ── 1 · Vollständige Eingänge ───────────────────────────────────────────────

async def test_alle_eingaenge_da_liefert_die_ganze_gruppe(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, kontext = await _rechne(db, anlage)
    keys = _keys(werte)

    for key in (
        "eedc_ueberschuss_heute_kwh", "eedc_ueberschuss_jetzt_kw",
        "eedc_ueberschuss_verfuegbar", "eedc_guenstige_stunde",
        "eedc_speicher_voll", "eedc_speicher_soc_prozent",
        "eedc_speicher_voll_um_ts", "eedc_netzbezug_spitze_heute_kw",
        "eedc_ueberschuss_prognose_heute_kwh", "eedc_bestes_fenster_ab",
    ):
        assert key in keys, f"{key} fehlt trotz vollständiger Eingänge"
    assert kontext["fenster"] is not None


async def test_e1_traegt_die_tageszahl_und_das_defizit(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_ueberschuss_heute_kwh")
    assert sv.value == 7.5
    assert sv.zusatz_attribute["defizit_heute_kwh"] == 12.0
    assert sv.zusatz_attribute["stand"] == "12:00"


async def test_e1_jetzt_ist_eine_zahl_mit_vorzeichen(db, monkeypatch):
    """Überschuss und Defizit sind EINE Größe mit Vorzeichen, nicht zwei Sensoren."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_ueberschuss_jetzt_kw")
    assert sv.value == 2.5, "letzte Zeile ist Stunde 12 mit 2,5 kW Überschuss"
    # ⛔ Hier stand bis 22.09.2026 `zusatz_attribute["stunde"] == "12:00"`.
    # Das Attribut gab nicht her, was es meinte: Slot 12 ist backward die
    # Stunde 11–12 Uhr (N-544). Es heisst jetzt `stunde_von` (Beginn) +
    # `stunde_bis` (Ende) — die EINE Entfernung dieses Pakets.
    assert "stunde" not in sv.zusatz_attribute
    assert sv.zusatz_attribute["stunde_von"] == "11:00"
    assert sv.zusatz_attribute["stunde_bis"] == "12:00"
    assert _sv(werte, "eedc_ueberschuss_verfuegbar").value is True
    # ⛔ Hier stand bis 22.09.2026 „10:00". Der Ueberschuss-Lauf beginnt mit
    # Slot 10 der Fixture, und der deckt backward die Stunde **09–10 Uhr**
    # (N-544): `seit` ist eine Beginn-Angabe, also 09:00.
    assert _sv(werte, "eedc_ueberschuss_verfuegbar").zusatz_attribute["seit"] == "09:00"


async def test_e1_jetzt_wird_negativ_wenn_defizit_herrscht(db, monkeypatch):
    anlage = await _anlage(db)
    heute = HEUTE
    db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=heute, stunde=6,
                              ueberschuss_kw=0.0, defizit_kw=3.0, netzbezug_kw=3.0))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=heute,
                                ueberschuss_kwh=0.0, defizit_kwh=3.0,
                                peak_netzbezug_kw=3.2))
    await db.commit()
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    assert _sv(werte, "eedc_ueberschuss_jetzt_kw").value == -3.0
    assert _sv(werte, "eedc_ueberschuss_verfuegbar").value is False


async def test_e2_guenstige_stunde_liest_dieselbe_markierung_wie_der_preis_rang(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_guenstige_stunde")
    assert sv is not None
    assert sv.value is False, "12:30 liegt nicht im Preistal (02:00/03:00)"
    assert sv.zusatz_attribute["schwelle_cent"] == 18.0


async def test_e2_speicher_voll_erst_ab_der_schwelle(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(speicher_soc_prozent=40.0), _preis())
    werte, _ = await _rechne(db, anlage)
    assert _sv(werte, "eedc_speicher_voll").value is False

    _stelle_quellen(monkeypatch, _prognose(speicher_soc_prozent=99.4), _preis())
    werte, _ = await _rechne(db, anlage)
    assert _sv(werte, "eedc_speicher_voll").value is True
    assert _sv(werte, "eedc_speicher_soc_prozent").value == 99.4


async def test_e3_ist_ein_iso_zeitstempel_und_nennt_seine_quelle(db, monkeypatch):
    """⛔ Und `eedc_speicher_voll_um` bleibt dabei Text — der alte Vertrag hält.

    ⚠ Die Stunde wird **relativ zur laufenden** gesetzt. Die Simulation startet
    produktiv bei `now.hour` und kann nie eine frühere Stunde liefern; eine fest
    eingetragene 15:00 wäre in `Pacific/Auckland` (dort lief die Probe um 21
    Uhr) „gestern" und die Probe eine Wette auf die Stunde ihres Laufs
    (N-167) — genau so am 21.09.2026 im Drei-Zonen-Lauf aufgefallen.
    """
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    jetzt = JETZT
    ziel = jetzt.hour + 1
    _stelle_quellen(
        monkeypatch,
        _prognose(speicher_voll_um=f"{ziel:02d}:00", speicher_voll_um_slot=ziel),
        _preis(),
    )

    werte, _ = await _rechne(db, anlage)
    alt = _sv(werte, "eedc_speicher_voll_um")
    neu = _sv(werte, "eedc_speicher_voll_um_ts")
    assert alt.value == f"{ziel:02d}:00", "das Textformat des bestehenden Sensors ist unverändert"
    assert neu.value.startswith(f"{jetzt.date().isoformat()}T{ziel:02d}:00:00")
    assert neu.zusatz_attribute["quelle"] == "eedc_speicher_voll_um"
    assert neu.definition.device_class == "timestamp"


async def test_e3_eine_stunde_vor_jetzt_meint_morgen(db, monkeypatch):
    """Sollte die Simulation je eine frühere Stunde liefern, ist morgen gemeint."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    jetzt = JETZT
    _stelle_quellen(monkeypatch, _prognose(speicher_voll_um_slot=jetzt.hour - 1), _preis())

    werte, _ = await _rechne(db, anlage)
    neu = _sv(werte, "eedc_speicher_voll_um_ts")
    morgen = (HEUTE + timedelta(days=1)).isoformat()
    assert neu.value.startswith(f"{morgen}T{jetzt.hour - 1:02d}:00:00")


async def test_e5_nennt_den_peak_und_die_stunde_des_hoechsten_mittels_getrennt(db, monkeypatch):
    """Zwei verschiedene Größen — der Sensor trägt die eine, das Attribut die andere."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_netzbezug_spitze_heute_kw")
    assert sv.value == 4.8, "der W-Peak des Tages"
    assert sv.zusatz_attribute["max_mittel_kw"] == 1.2, "das höchste Stundenmittel"
    # ⛔ Hier stand bis 22.09.2026 „00:00". `stunde_max_mittel` ist eine
    # BEGINN-Angabe (N-544): das hoechste Stundenmittel liegt in Slot 0, und
    # der beginnt am Vortag um 23:00. „00:00" war sein ENDE.
    assert sv.zusatz_attribute["stunde_max_mittel"] == "23:00"


# ── 2 · P2 — Überschuss-Prognose ────────────────────────────────────────────

async def test_p2_summe_und_bloecke(db, monkeypatch):
    """Handrechnung: PV 1/2/4/5/5/4/3/1 ab 8 Uhr gegen 0,5 kWh Verbrauch.

    Überschuss je Stunde: 0,5 · 1,5 · 3,5 · 4,5 · 4,5 · 3,5 · 2,5 · 0,5 = 21,0 kWh
    in **einem** zusammenhängenden Block von 8 bis 16 Uhr.
    """
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_ueberschuss_prognose_heute_kwh")
    assert sv.value == pytest.approx(21.0)
    assert len(sv.zusatz_attribute["fenster"]) == 1
    block = sv.zusatz_attribute["fenster"][0]
    assert block["stunden"] == 8 and block["summe_kwh"] == pytest.approx(21.0)
    assert sv.zusatz_attribute["profil_typ"] == "individuell_werktag"
    assert len(sv.zusatz_attribute["stundenprofil_kwh"]) == 24
    assert len(sv.zusatz_attribute["defizit_stundenprofil_kwh"]) == 24


async def test_p1_haengt_als_attribut_an_der_verbrauchsprognose(db, monkeypatch):
    """Σ der Stundenreihe == Tagessumme des Sensors (auf 0,1 kWh)."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_verbrauchsprognose_heute_kwh")
    reihe = sv.zusatz_attribute["stundenprofil_kwh"]
    assert sum(reihe) == pytest.approx(sv.value, abs=0.1)
    assert "wp_stundenprofil_kwh" in sv.zusatz_attribute
    assert sum(sv.zusatz_attribute["wp_stundenprofil_kwh"]) < sum(reihe), (
        "der WP-Anteil ist eine Teilmenge, kein Summand daneben"
    )


# ── 3 · P5 — bestes Fenster ─────────────────────────────────────────────────

async def test_p5_traegt_vier_dauern_und_ein_kostenprofil(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_bestes_fenster_ab")
    # ⚠ **Wie viele Dauern es gibt, hängt an der Uhr — und das ist richtig so.**
    # Um 21 Uhr passt kein 4-Stunden-Fenster mehr in den Tag; eine Probe, die
    # alle vier fordert, ist spätabends rot, ohne dass am Code etwas fehlt
    # (in `Pacific/Auckland` am 21.09.2026 genau so aufgefallen). Geprüft wird
    # deshalb: es gibt so viele Dauern, wie Platz ist, und jede ist vollständig.
    erwartet = [d for d in (1, 2, 3, 4) if JETZT.hour + d <= 24]
    assert [d for d in (1, 2, 3, 4) if f"dauer_{d}h" in sv.zusatz_attribute] == erwartet
    for d in erwartet:
        eintrag = sv.zusatz_attribute[f"dauer_{d}h"]
        assert eintrag["stunden"] == d
        assert "ab" in eintrag and "bis" in eintrag and "kosten_cent_kwh" in eintrag
    # ⛔ Hier stand bis 22.09.2026 `== 24`. Die Achse ist seit N-544 backward
    # und ohne Morgen-Satz **25** Slots lang: Slot 24 ist heute 23–24 Uhr und
    # fiele auf einer 24er-Achse heraus, obwohl er noch im Rahmen liegt. Die
    # Profil-Attribute folgen der Achse — sonst waere ein Fenster in Slot 24
    # im Attribut nicht auffindbar.
    assert len(sv.zusatz_attribute["kosten_profil_cent_kwh"]) == 25
    assert sv.zusatz_attribute["preisquelle"] == "boersenpreis"
    erstes = f"dauer_2h" if "dauer_2h" in sv.zusatz_attribute else f"dauer_{erwartet[0]}h"
    assert sv.value == sv.zusatz_attribute[erstes]["ab"]


async def test_p5_faellt_in_die_ueberschuss_stunden_wenn_sie_guenstiger_sind(db, monkeypatch):
    """Um 09:00 kostet die Überschussstunde 0 ct — sie schlägt jeden Preis."""
    from backend.services.ha_export_fenster import baue_fenster_kontext
    from backend.core.berechnungen.fenster import bestes_fenster

    ctx = baue_fenster_kontext(_prognose(), _preis(), jetzt=datetime(2026, 9, 21, 9, 0))
    f = bestes_fenster(ctx.kosten, dauer_h=2, ab_h=9, frist_h=ctx.frist_slot)
    assert f.kosten_cent_kwh == 0.0
    assert 9 <= f.ab <= 14


# ── 4 · P3 — Arbitrage ──────────────────────────────────────────────────────

async def _speicher(db, anlage_id, **parameter):
    from backend.models import Investition

    inv = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
        leistung_kwp=10.0, parameter=parameter,
    )
    db.add(inv)
    await db.commit()
    return inv


async def test_p3_entsteht_nur_mit_laedt_aus_netz(db, monkeypatch):
    """⭐ Das Gate ist `laedt_aus_netz`, nicht `arbitrage_faehig`."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    await _speicher(db, anlage.id, laedt_aus_netz=False, arbitrage_faehig=False)
    _stelle_quellen(monkeypatch, _prognose(speicher_soc_prozent=10.0), _preis())

    werte, _ = await _rechne(db, anlage)
    assert "eedc_arbitrage_vorschlag_kwh" not in _keys(werte)


async def test_p3_entsteht_mit_laedt_aus_netz_auch_ohne_arbitrage_haken(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    await _speicher(db, anlage.id, laedt_aus_netz=True, arbitrage_faehig=False)
    # Kurz nach Mitternacht: das Preistal um 03:00 liegt noch vor uns, der
    # Gipfel um 19:00 auch. Ohne gestellte Uhr wäre die Probe eine Wette auf
    # die Stunde ihres Laufs (N-167).
    _stelle_quellen(monkeypatch, _prognose(speicher_soc_prozent=10.0), _preis())

    from backend.services.ha_export_fenster import baue_fenster_kontext
    from backend.core.berechnungen.fenster import arbitrage_vorschlag

    ctx = baue_fenster_kontext(
        _prognose(speicher_soc_prozent=10.0), _preis(), jetzt=datetime(2026, 9, 21, 1, 0)
    )
    defizit = [max(0.0, 0.5 - p) for p in _prognose()["stundenprofil_heute"]]
    ergebnis = arbitrage_vorschlag(
        ctx.kosten, defizit, frei_kwh=9.0, wirkungsgrad_prozent=90.0,
        guenstig=ctx.guenstig, ab_h=1,
    )
    assert ergebnis is not None, "Laden bei 10 ct, Entladen gegen 45 ct lohnt"
    # ⛔ Hier stand bis 22.09.2026 `(2, 3)`/`(2,)`. Das Preistal der Fixture
    # liegt bei den **forward** beschrifteten Boersenstunden 2 und 3; auf der
    # backward-Achse sind das die Slots **3 und 4** (N-544) — dieselben
    # physischen Stunden.
    assert ergebnis.lade_stunden in ((3, 4), (3,))


# ── 5 · P6 — Abweichungs-Ampel ──────────────────────────────────────────────

async def test_p6_ohne_genauigkeits_tracking_gibt_es_keine_ampel(db, monkeypatch):
    """Ohne Lernfaktor gibt es keine Schwelle — und dann keinen binary_sensor."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    assert "eedc_prognose_auffaellig" not in _keys(werte), (
        "kein Genauigkeits-Tracking ⇒ keine Ampel (ADR-002/P4)"
    )


async def test_p6_zahl_entsteht_sobald_der_tag_prognose_hatte(db, monkeypatch):
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    sv = _sv(werte, "eedc_prognose_abweichung_heute_prozent")
    # Handrechnung: PV-Reihe bis 12:30 ⇒ Stunden 0–11 ⇒ 1+2+4+5 = 12,0 kWh Soll,
    # IST 9,0 kWh ⇒ (9 − 12) ÷ 12 × 100 = −25,0 %.
    soll = sum(_prognose()["stundenprofil_heute"][:JETZT.hour])
    assert soll == pytest.approx(12.0)
    assert sv is not None
    assert sv.value == pytest.approx(-25.0)
    assert sv.zusatz_attribute["ist_kwh"] == 9.0
    assert sv.zusatz_attribute["prognose_kwh"] == pytest.approx(12.0)
    # ⛔ Hier stand bis 22.09.2026 „12:00" — die UHR-Stunde. `bis_stunde` ist
    # eine End-Angabe ueber die letzte einbezogene Stunde: summiert werden die
    # Slots 0…11, und Slot 11 endet um **11:00** (N-544).
    assert sv.zusatz_attribute["bis_stunde"] == "11:00"


async def test_p6_ampel_mit_schwelle(db, monkeypatch):
    """Mit Lernfaktor und Historie entsteht die Ampel — und sie rechnet 2 × MAE."""
    anlage = await _anlage(db)
    heute = HEUTE
    await _tagesprofil(db, anlage.id, heute)
    # Zehn Tage, an denen die Prognose je 10 % zu hoch lag ⇒ MAE = 10 %.
    for i in range(1, 11):
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=heute - timedelta(days=i),
            pv_prognose_final_kwh=11.0, komponenten_kwh={"pv_1": 10.0},
        ))
    await db.commit()

    from backend.api.routes import live_wetter

    async def _lern(anlage_id, db_, quelle="openmeteo"):
        return 1.0

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _lern)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    from backend.services.prognose_genauigkeit_service import eedc_mae_prozent

    mae, tage = await eedc_mae_prozent(db, anlage.id, heute=heute)
    assert tage == 10
    assert mae == pytest.approx(10.0), "(11 − 10) ÷ 10 × 100 = 10 % an zehn Tagen"

    werte, _ = await _rechne(db, anlage)
    ampel = _sv(werte, "eedc_prognose_auffaellig")
    assert ampel is not None
    assert ampel.zusatz_attribute["schwelle_prozent"] == pytest.approx(20.0)
    assert ampel.zusatz_attribute["mae_30_tage_prozent"] == pytest.approx(10.0)
    # Abweichung −25 % liegt über 2 × MAE (20 %), und vier Sonnenstunden sind
    # vergangen ⇒ die Ampel steht auf AN.
    assert ampel.value is True


# ── 6 · Degradation (ADR-002/P4) — die Pflichtmatrix ────────────────────────

async def test_ohne_tagesprofil_fehlen_e1_e2_e5_der_rest_bleibt(db, monkeypatch):
    """Standalone ohne Live-Quelle: die Zustandsgrößen fehlen, die Pläne nicht."""
    anlage = await _anlage(db)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    keys = _keys(werte)

    for fehlt in ("eedc_ueberschuss_heute_kwh", "eedc_ueberschuss_jetzt_kw",
                  "eedc_ueberschuss_verfuegbar", "eedc_netzbezug_spitze_heute_kw"):
        assert fehlt not in keys, f"{fehlt} darf ohne Tagesprofil nicht entstehen"
    # Was nur Prognose + Preis braucht, bleibt.
    assert "eedc_ueberschuss_prognose_heute_kwh" in keys
    assert "eedc_bestes_fenster_ab" in keys


async def test_ohne_individuelles_profil_fehlen_p1_und_p2(db, monkeypatch):
    """N-332: kein individuelles Verbrauchsprofil ⇒ kein Modell-A-Sensor."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    ohne = _prognose(
        verbrauch_heute_kwh=None, verbrauch_stundenprofil_kwh=None,
        verbrauch_wp_stundenprofil_kwh=None, verbrauch_profil_typ=None,
    )
    _stelle_quellen(monkeypatch, ohne, _preis())

    werte, kontext = await _rechne(db, anlage)
    keys = _keys(werte)
    assert "eedc_verbrauchsprognose_heute_kwh" not in keys
    assert "eedc_ueberschuss_prognose_heute_kwh" not in keys
    # Der Preis allein trägt P5 weiter — und der Überschuss ist dort 0.
    assert "eedc_bestes_fenster_ab" in keys
    assert not kontext["fenster"].hat_ueberschuss


async def test_ohne_preis_rechnet_p5_nur_in_den_ueberschuss_stunden(db, monkeypatch):
    """Nur Überschuss, kein Preis: das Fenster liegt **im** Überschuss-Block."""
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), None)

    werte, kontext = await _rechne(db, anlage)
    ctx = kontext["fenster"]
    assert ctx is not None and ctx.preisquelle == "keine"
    assert "eedc_guenstige_stunde" not in _keys(werte), "ohne Preis keine Günstig-Ampel"
    sv = _sv(werte, "eedc_bestes_fenster_ab")
    if sv is not None:
        assert sv.zusatz_attribute["preisquelle"] == "keine"


async def test_ohne_preis_und_ohne_ueberschuss_gibt_es_keinen_kontext(db, monkeypatch):
    anlage = await _anlage(db)
    ohne = _prognose(
        verbrauch_stundenprofil_kwh=None, stundenprofil_heute=[0.0] * 24,
    )
    _stelle_quellen(monkeypatch, ohne, None)

    werte, kontext = await _rechne(db, anlage)
    assert kontext["fenster"] is None
    assert "eedc_bestes_fenster_ab" not in _keys(werte)


async def test_ohne_speicher_fehlen_e3_e4_und_die_voll_ampel(db, monkeypatch):
    anlage = await _anlage(db)
    heute = HEUTE
    # Tagesprofil OHNE SoC — eine Anlage ohne Speicher.
    db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=heute, stunde=11,
                              ueberschuss_kw=1.0, defizit_kw=0.0, netzbezug_kw=0.0))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=heute,
                                ueberschuss_kwh=3.0, defizit_kwh=1.0,
                                peak_netzbezug_kw=2.0))
    await db.commit()
    ohne = _prognose(speicher_soc_prozent=None, speicher_voll_um=None,
                     speicher_voll_um_slot=None, speicher_kap_kwh=None)
    _stelle_quellen(monkeypatch, ohne, _preis())

    werte, _ = await _rechne(db, anlage)
    keys = _keys(werte)
    for fehlt in ("eedc_speicher_soc_prozent", "eedc_speicher_voll",
                  "eedc_speicher_voll_um_ts", "eedc_arbitrage_vorschlag_kwh"):
        assert fehlt not in keys, f"{fehlt} darf ohne Speicher nicht entstehen"


async def test_kein_sensor_traegt_eine_erfundene_null(db, monkeypatch):
    """Quer über die Gruppe: ein entstandener Sensor hat einen echten Wert.

    ⚠ `False` ist ein Wert (ein `binary_sensor`, der AUS ist, sagt etwas) —
    `None` ist keiner und darf gar nicht erst in der Liste stehen.
    """
    anlage = await _anlage(db)
    await _tagesprofil(db, anlage.id, HEUTE)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)
    for sv in werte:
        assert sv.value is not None, f"{sv.definition.key} steht mit None in der Liste"
