"""S3 je Gerät — P4 (Warmwasser) · P7 (Heizfenster) · P8 (Kühlfenster) · P9 (Sonstiges).

**Die Regel, die jede Probe hier prüft, ist die Aufnahmeregel** (Konzept §5):
ein Stück entsteht nur, wenn eedc alle drei Fragen mit einer vorhandenen
Größe beantworten kann — *wie viel* (Menge des Geräts), *wogegen*
(Stundenreihe), *was kommt heraus* (Fenster mit Betrag). Fehlt eine Antwort,
fehlt der Sensor — nicht sein Wert.

⚠ **Die Achse entscheidet, nicht die Bauart** (ADR-002/P13). Keine Probe hier
setzt `wp_art`; die Geräte unterscheiden sich allein darin, welche Achse
gemessen bzw. gepflegt ist.

⛔ **Keine echte Uhr.** Jeder Kontext bekommt eine gestellte Zeit (`HEUTE`/`_ctx`) —
sonst wäre jede Probe eine Wette auf die Stunde ihres Laufs (N-167).

Schwesterdateien: `test_s2_entscheidungs_sensoren.py` (dieselben Stücke
anlagenweit), `test_fenster_rechner.py` (der Layer darunter).
"""

from datetime import date, datetime, timedelta

import pytest

from backend.services.ha_export_fenster import baue_fenster_kontext


#: Die gestellte Uhr dieser Datei — ein Werktag im September.
HEUTE = date(2026, 9, 21)


# ── Aufbau ──────────────────────────────────────────────────────────────────

def _prognose(**ueberschreiben) -> dict:
    pv = [0.0] * 8 + [1.0, 2.0, 4.0, 5.0, 5.0, 4.0, 3.0, 1.0] + [0.0] * 8
    basis = {
        # Die Felder, die `prognose_und_preis_sensoren` liest — der Kontext-Aufbau
        # braucht nur die drei Reihen, der volle Lauf die ganze Antwort.
        "heute_kwh": sum(pv), "rest_today_kwh": 0.0, "heute_rollend_kwh": sum(pv),
        "ist_bisher_kwh": 0.0, "day_plus_1_kwh": None, "day_plus_2_kwh": None,
        "day_plus_3_kwh": None, "speicher_voll_um": None,
        "verbrauch_heute_kwh": 12.0, "verbrauch_profil_slots": 24,
        "stundenprofil_heute": pv,
        "verbrauch_stundenprofil_kwh": [0.5] * 24,
        "verbrauch_wp_stundenprofil_kwh": [0.0] * 5 + [1.5, 1.5, 1.0] + [0.2] * 16,
        "verbrauch_temperatur_c": [12.0] * 13 + [30.0, 33.0, 31.0] + [20.0] * 8,
        "verbrauch_profil_typ": "individuell_werktag",
        "verbrauch_profil_tage": 7,
    }
    basis.update(ueberschreiben)
    return basis


def _preis(**ueberschreiben) -> dict:
    def _p(h):
        return 10.0 if h in (2, 3, 4) else (45.0 if h in (18, 19) else 25.0)

    basis = {
        "rang_profil": [
            {"stunde": h, "rang": 1 if h in (2, 3, 4) else 99, "preis_cent": _p(h),
             "unter_schwelle": h in (2, 3, 4)}
            for h in range(24)
        ],
        "guenstig_schwelle_cent": 18.0,
        # Die Felder, die `prognose_und_preis_sensoren` liest — der Kontext-Aufbau
        # braucht nur `rang_profil`, der volle Lauf die ganze Antwort.
        "preis_rang": 99, "guenstige_stunden_anzahl": 3,
        "guenstige_stunden_tag": 0, "guenstige_stunden_nacht": 3,
        "preis_aktuell_cent": 25.0, "tages_durchschnitt_cent": 25.0,
        "optimierter_durchschnitt_cent": 22.0,
        "abstand_prozent": 13.6, "abstand_cent": 3.0,
        "datum": "2026-09-21", "morgen_verfuegbar": False,
    }
    basis.update(ueberschreiben)
    return basis


def _ctx(stunde: int = 0, **prognose_ueberschreiben):
    """Ein Fenster-Kontext mit **gestellter** Uhr (N-167)."""
    return baue_fenster_kontext(
        _prognose(**prognose_ueberschreiben), _preis(),
        jetzt=datetime.combine(HEUTE, datetime.min.time()).replace(hour=stunde),
    )


async def _anlage(db, sensor_mapping=None):
    from backend.models import Anlage, Monatsdaten

    anlage = Anlage(
        anlagenname="S3-Probe", leistung_kwp=10.0,
        installationsdatum=date(2024, 1, 1),
        latitude=48.1, longitude=11.5,
        sensor_mapping=sensor_mapping or {},
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=200.0))
    await db.commit()
    return anlage


async def _geraet(db, anlage, typ: str, parameter: dict, zeilen: dict):
    """Ein Gerät samt Monatszeilen. ``zeilen``: {(jahr, monat): verbrauch_daten}."""
    from backend.models.investition import Investition, InvestitionMonatsdaten

    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung=f"{typ} Probe",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=5000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    for (jahr, monat), daten in zeilen.items():
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=jahr, monat=monat, verbrauch_daten=daten,
        ))
    await db.commit()
    return inv


def _letzte_monate(heute: date, n: int = 3) -> list[tuple[int, int]]:
    out, jahr, monat = [], heute.year, heute.month
    for _ in range(n):
        monat -= 1
        if monat == 0:
            jahr, monat = jahr - 1, 12
        out.append((jahr, monat))
    return out


async def _rechne(db, inv, ctx, modus_map=None):
    from backend.api.routes.ha_export import calculate_investition_sensors

    return await calculate_investition_sensors(
        db, inv, None, None, modus_map, fenster_ctx=ctx,
    )


def _sv(werte, key):
    for sv in werte:
        if sv.definition.key == key:
            return sv
    return None


def _keys(werte):
    return {sv.definition.key for sv in werte}


# ── E2 je Gerät — Warmwasserbetrieb ─────────────────────────────────────────

async def test_wp_warmwasserbetrieb_folgt_dem_betriebsmodus(db):
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})

    werte = await _rechne(db, inv, _ctx(), modus_map={inv.id: "warmwasser"})
    assert _sv(werte, "wp_warmwasserbetrieb").value is True

    werte = await _rechne(db, inv, _ctx(), modus_map={inv.id: "heizen"})
    assert _sv(werte, "wp_warmwasserbetrieb").value is False


async def test_ohne_modus_zuordnung_gibt_es_den_sensor_nicht(db):
    """Dieselbe Leer-Regel wie bei `wp_betriebsmodus` (#398) — keine tote Entität."""
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})

    werte = await _rechne(db, inv, _ctx(), modus_map={})
    assert "wp_warmwasserbetrieb" not in _keys(werte)


# ── P4 — Warmwasser-Fenster ─────────────────────────────────────────────────

async def test_p4_gemessen_schlaegt_abgeleitet(db):
    """F-56: liegt ein Warmwasser-**Zähler** vor, trägt er die Menge.

    Handrechnung: 90 kWh gemessen in einem 30-Tage-Monat ⇒ 3 kWh/Tag.
    Der abgeleitete Modus-Split daneben (30 kWh) wird NICHT benutzt.
    """
    heute = date(2026, 9, 21)
    anlage = await _anlage(db)
    jahr, monat = _letzte_monate(heute, 1)[0]
    inv = await _geraet(
        db, anlage, "waermepumpe",
        {"getrennte_strommessung": True},
        {(jahr, monat): {
            "stromverbrauch_kwh": 300.0,
            "strom_heizen_kwh": 210.0,
            "strom_warmwasser_kwh": 90.0,
            "modus_strom_warmwasser_kwh": 30.0,
        }},
    )
    werte = await _rechne(db, inv, _ctx(stunde=0))
    sv = _sv(werte, "wp_warmwasser_fenster_ab")
    assert sv is not None
    assert sv.zusatz_attribute["herkunft"] == "gemessen"
    import calendar
    tage = calendar.monthrange(jahr, monat)[1]
    assert sv.zusatz_attribute["menge_kwh"] == pytest.approx(round(90.0 / tage, 1))


async def test_p4_abgeleitet_wenn_kein_zaehler_da_ist(db):
    """⛔ Und dann entsteht das Fenster trotzdem — die Hilfe behauptete Gegenteiliges."""
    heute = date(2026, 9, 21)
    anlage = await _anlage(db)
    jahr, monat = _letzte_monate(heute, 1)[0]
    inv = await _geraet(
        db, anlage, "waermepumpe", {},
        {(jahr, monat): {
            "stromverbrauch_kwh": 300.0,
            "modus_strom_warmwasser_kwh": 60.0,
            "modus_abdeckung_h": 700.0,
        }},
    )
    werte = await _rechne(db, inv, _ctx(stunde=0))
    sv = _sv(werte, "wp_warmwasser_fenster_ab")
    assert sv is not None
    assert sv.zusatz_attribute["herkunft"] == "abgeleitet"
    assert sv.zusatz_attribute["menge_kwh"] > 0


async def test_p4_liegt_im_ueberschuss_wenn_er_die_menge_deckt(db):
    """⭐ Der Überschuss schlägt das Preistal — und das ist richtig so.

    1 kWh Warmwasserstrom je Tag, verteilt auf zwei Stunden, sind 0,5 kWh je
    Stunde. Mittags stehen 3,5–4,5 kWh Überschuss zur Verfügung; die Menge ist
    dort **vollständig** gedeckt und kostet 0 ct. Das Preistal um 02:00 kostet
    10 ct. Eine Automation, die den Warmwasserspeicher mittags lädt, zahlt
    nichts — sie verdrängt Einspeisung, keinen Netzbezug.
    """
    heute = date(2026, 9, 21)
    anlage = await _anlage(db)
    jahr, monat = _letzte_monate(heute, 1)[0]
    import calendar
    tage = calendar.monthrange(jahr, monat)[1]
    inv = await _geraet(
        db, anlage, "waermepumpe", {"getrennte_strommessung": True},
        {(jahr, monat): {"stromverbrauch_kwh": 100.0, "strom_heizen_kwh": 70.0,
                         "strom_warmwasser_kwh": float(tage)}},   # genau 1 kWh/Tag
    )
    werte = await _rechne(db, inv, _ctx(stunde=0))
    sv = _sv(werte, "wp_warmwasser_fenster_ab")
    assert sv.zusatz_attribute["menge_kwh"] == pytest.approx(1.0)
    assert sv.zusatz_attribute["kosten_cent_kwh"] == pytest.approx(0.0)
        # ⛔ Hier stand bis 22.09.2026 `8 <= … <= 14`. Der PV-Wert an Index 8
        # deckt backward die Stunde **07–08 Uhr** (N-544) — das Fenster beginnt
        # also um 07:00, nicht um 08:00. Dieselbe physische Stunde, die richtige
        # Beschriftung.
    assert 7 <= int(sv.value[11:13]) <= 13, "das Fenster liegt in den Überschuss-Stunden"


async def test_p4_liegt_im_preistal_wenn_kein_ueberschuss_da_ist(db):
    """Ohne Überschussreihe gewinnt das Preistal — 02:00 mit 10 ct."""
    heute = date(2026, 9, 21)
    anlage = await _anlage(db)
    jahr, monat = _letzte_monate(heute, 1)[0]
    inv = await _geraet(
        db, anlage, "waermepumpe", {"getrennte_strommessung": True},
        {(jahr, monat): {"stromverbrauch_kwh": 100.0, "strom_heizen_kwh": 70.0,
                         "strom_warmwasser_kwh": 30.0}},
    )
    ctx = _ctx(stunde=0, verbrauch_stundenprofil_kwh=None)
    werte = await _rechne(db, inv, ctx)
    sv = _sv(werte, "wp_warmwasser_fenster_ab")
    assert sv.value.startswith("2026-09-21T02:00") or sv.value.startswith("2026-09-21T03:00")
    assert sv.zusatz_attribute["kosten_cent_kwh"] == pytest.approx(10.0)


async def test_p4_ohne_warmwasser_menge_kein_fenster(db):
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    werte = await _rechne(db, inv, _ctx())
    assert "wp_warmwasser_fenster_ab" not in _keys(werte)


async def test_p4_ohne_fenster_kontext_kein_fenster(db):
    """Ohne Preis UND ohne Überschuss gibt es keinen Kontext — und keinen Sensor."""
    heute = date(2026, 9, 21)
    anlage = await _anlage(db)
    jahr, monat = _letzte_monate(heute, 1)[0]
    inv = await _geraet(
        db, anlage, "waermepumpe", {"getrennte_strommessung": True},
        {(jahr, monat): {"stromverbrauch_kwh": 100.0, "strom_warmwasser_kwh": 30.0}},
    )
    werte = await _rechne(db, inv, None)
    assert "wp_warmwasser_fenster_ab" not in _keys(werte)


# ── P7 — Heizfenster ────────────────────────────────────────────────────────

async def test_p7_nennt_die_guenstigen_heizstunden_und_die_ersparnis(db):
    """Heizprofil 1,5/1,5/1,0 kWh um 5–7 Uhr; das Preistal liegt um 2–4 Uhr.

    Ab Mitternacht liegen beide vor uns — aber verschoben wird nur **innerhalb**
    der Heizzeit (die Stunden mit WP-Anteil). Das Tal 2–4 gehört nicht dazu;
    die Ersparnis entsteht allein aus der Umverteilung innerhalb 5–23 Uhr.
    """
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    ctx = _ctx(stunde=0)

    werte = await _rechne(db, inv, ctx)
    sv = _sv(werte, "wp_heizfenster_stunden")
    assert sv is not None
    assert sv.value >= 1
    # ⛔ Hier stand bis 22.09.2026 `== 24` — s. die Begruendung bei P5 in
    # `test_s2_entscheidungs_sensoren.py`: die backward-Achse ist ohne
    # Morgen-Satz 25 Slots lang.
    assert len(sv.zusatz_attribute["heizstrom_stundenprofil_kwh"]) == 25
    assert all(":" in h for h in sv.zusatz_attribute["guenstige_heizstunden"])
    assert sv.zusatz_attribute["profil_typ"] == "individuell_werktag"


async def test_p7_ohne_wp_profil_gibt_es_kein_heizfenster(db):
    """N-332: ohne individuelles Profil keine WP-Reihe — und kein Sensor."""
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    ctx = _ctx(stunde=0, verbrauch_wp_stundenprofil_kwh=None)

    werte = await _rechne(db, inv, ctx)
    assert "wp_heizfenster_stunden" not in _keys(werte)


async def test_p7_sommer_ohne_heizbedarf_gibt_es_kein_fenster(db):
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    ctx = _ctx(stunde=0, verbrauch_wp_stundenprofil_kwh=[0.0] * 24)

    werte = await _rechne(db, inv, ctx)
    assert "wp_heizfenster_stunden" not in _keys(werte)


# ── P8 — Kühlfenster ────────────────────────────────────────────────────────

def _mapping_mit_kuehlzaehler(inv_id: int) -> dict:
    return {"investitionen": {str(inv_id): {"felder": {
        "betriebsart_strom_kuehlen_kwh": {"strategie": "sensor",
                                          "sensor_id": "sensor.wp_kuehlen"},
    }}}}


async def test_p8_braucht_zaehler_und_menge(db):
    """⛔ Beide Kriterien: Kühl-Zähler **und** eine gemessene Kühlstrom-Menge."""
    heute = date(2026, 9, 21)
    jahr, monat = _letzte_monate(heute, 1)[0]
    zeile = {"stromverbrauch_kwh": 200.0, "betriebsart_strom_kuehlen_kwh": 60.0,
             "modus_abdeckung_h": 700.0}

    # (a) Zähler zugeordnet + Menge ⇒ Fenster
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {(jahr, monat): zeile})
    anlage.sensor_mapping = _mapping_mit_kuehlzaehler(inv.id)
    await db.commit()
    await db.refresh(inv)
    werte = await _rechne(db, inv, _ctx(stunde=6))
    assert "wp_kuehlfenster_ab" in _keys(werte)

    # (b) dieselbe Menge, aber KEIN zugeordneter Zähler und kein gemessenes Feld
    anlage2 = await _anlage(db)
    inv2 = await _geraet(
        db, anlage2, "waermepumpe", {},
        {(jahr, monat): {"stromverbrauch_kwh": 200.0,
                         "modus_strom_kuehlen_kwh": 60.0,
                         "modus_abdeckung_h": 700.0}},
    )
    werte2 = await _rechne(db, inv2, _ctx(stunde=6))
    assert "wp_kuehlfenster_ab" not in _keys(werte2), (
        "eine abgeleitete Kühlmenge ist kein Zähler (Wärme/Klima R1)"
    )


async def test_p8_liegt_vor_der_hitzespitze(db):
    """Temperaturmaximum um 14 Uhr ⇒ das Fenster endet spätestens 14:00."""
    heute = date(2026, 9, 21)
    jahr, monat = _letzte_monate(heute, 1)[0]
    anlage = await _anlage(db)
    inv = await _geraet(
        db, anlage, "waermepumpe", {},
        {(jahr, monat): {"stromverbrauch_kwh": 200.0,
                         "betriebsart_strom_kuehlen_kwh": 60.0,
                         "modus_abdeckung_h": 700.0}},
    )
    anlage.sensor_mapping = _mapping_mit_kuehlzaehler(inv.id)
    await db.commit()
    await db.refresh(inv)

    werte = await _rechne(db, inv, _ctx(stunde=6))
    sv = _sv(werte, "wp_kuehlfenster_ab")
    assert sv.zusatz_attribute["temperatur_max_um"] == "14:00"
    stunde_ab = int(sv.value[11:13])
    assert 6 <= stunde_ab <= 12, "das 2-Stunden-Fenster endet spätestens um 14:00"
    assert sv.zusatz_attribute["ueberschuss_kwh_im_fenster"] >= 0


async def test_p8_nach_der_spitze_gibt_es_kein_vorkuehlen_mehr(db):
    heute = date(2026, 9, 21)
    jahr, monat = _letzte_monate(heute, 1)[0]
    anlage = await _anlage(db)
    inv = await _geraet(
        db, anlage, "waermepumpe", {},
        {(jahr, monat): {"stromverbrauch_kwh": 200.0,
                         "betriebsart_strom_kuehlen_kwh": 60.0,
                         "modus_abdeckung_h": 700.0}},
    )
    anlage.sensor_mapping = _mapping_mit_kuehlzaehler(inv.id)
    await db.commit()
    await db.refresh(inv)

    werte = await _rechne(db, inv, _ctx(stunde=20))
    assert "wp_kuehlfenster_ab" not in _keys(werte)


# ── P9 — Sonstiges/Verbraucher ──────────────────────────────────────────────

async def test_p9_liefert_erst_den_geraetesensor_dann_das_fenster(db):
    """⭐ P9 ist auch Stufe 1 — bis hierher gab es für ein solches Gerät gar keinen kWh-Wert."""
    heute = HEUTE
    anlage = await _anlage(db)
    zeilen = {(heute.year, heute.month): {
        "verbrauch_sonstig_kwh": 120.0, "bezug_pv_kwh": 90.0, "bezug_netz_kwh": 30.0,
    }}
    for jahr, monat in _letzte_monate(heute, 3):
        zeilen[(jahr, monat)] = {
            "verbrauch_sonstig_kwh": 150.0, "bezug_pv_kwh": 100.0, "bezug_netz_kwh": 50.0,
        }
    inv = await _geraet(db, anlage, "sonstiges", {"kategorie": "verbraucher"}, zeilen)

    ctx = _ctx(stunde=0)
    werte = await _rechne(db, inv, ctx)

    monat_sv = _sv(werte, "sonstiges_verbrauch_monat_kwh")
    assert monat_sv is not None and monat_sv.value == pytest.approx(120.0)
    assert monat_sv.zusatz_attribute["pv_anteil_prozent"] == pytest.approx(75.0)
    assert monat_sv.zusatz_attribute["bezug_netz_kwh"] == pytest.approx(30.0)

    fenster_sv = _sv(werte, "sonstiges_fenster_ab")
    assert fenster_sv is not None
    assert fenster_sv.zusatz_attribute["menge_kwh"] > 0


async def test_p9_erzeuger_bekommt_keinen_verbraucher_sensor(db):
    """Die Kategorie entscheidet — ein BHKW ist kein verschiebbarer Verbraucher."""
    heute = HEUTE
    anlage = await _anlage(db)
    inv = await _geraet(
        db, anlage, "sonstiges", {"kategorie": "erzeuger"},
        {(HEUTE.year, HEUTE.month): {"erzeugung_kwh": 300.0}},
    )
    werte = await _rechne(db, inv, _ctx(stunde=0))
    assert "sonstiges_verbrauch_monat_kwh" not in _keys(werte)
    assert "sonstiges_fenster_ab" not in _keys(werte)


async def test_p9_ohne_zaehlerwerte_kein_sensor(db):
    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "sonstiges", {"kategorie": "verbraucher"}, {})
    werte = await _rechne(db, inv, _ctx(stunde=0))
    assert "sonstiges_verbrauch_monat_kwh" not in _keys(werte)


# ── Eine Rechnung je Publish-Lauf ───────────────────────────────────────────

async def test_die_mengenneutrale_grundrechnung_entsteht_einmal_je_anlage(db, monkeypatch):
    """⭐ Der Kontext wird **einmal** gebildet und an jedes Gerät gereicht.

    ⚠ **Und die Zahl daneben ist die ehrliche Grenze dieser Zusage.** Der
    Bauplan verlangte „``kosten_profil`` genau einmal je Publish-Lauf". Das
    trägt für die **mengenneutrale** Grundrechnung (1 kWh je Slot) — sie ist
    für alle gleich. Es trägt **nicht** für ein Gerät mit bekannter Menge: in
    einer Stunde mit 3 kWh Überschuss ist eine 1-kWh-Warmwasserladung gratis,
    eine 9-kWh-Autoladung zu zwei Dritteln nicht. Ein gemeinsames Profil für
    beide wäre nicht sparsam, sondern falsch (`fenster_fuer_menge`).
    **Gemessen wird deshalb: 1 Grundrechnung + genau eine je Geräte-Fenster** —
    nicht eine je gelesenem Sensor und nicht eine je Dauer.
    """
    from backend.core.berechnungen import fenster as layer
    from backend.services import ha_export_fenster

    heute = HEUTE
    monate = _letzte_monate(heute, 1)
    anlage = await _anlage(db)
    for _ in range(2):
        await _geraet(
            db, anlage, "waermepumpe", {"getrennte_strommessung": True},
            {monate[0]: {"stromverbrauch_kwh": 100.0, "strom_heizen_kwh": 70.0,
                         "strom_warmwasser_kwh": 30.0}},
        )

    profil_aufrufe: list[str] = []
    echt_profil = layer.kosten_profil
    echt_kontext = ha_export_fenster.baue_fenster_kontext

    def _zaehlend(*a, **k):
        profil_aufrufe.append("x")
        return echt_profil(*a, **k)

    kontext_aufrufe: list[str] = []

    def _kontext_zaehlend(*a, **k):
        kontext_aufrufe.append("x")
        return echt_kontext(*a, **k)

    monkeypatch.setattr(layer, "kosten_profil", _zaehlend)
    monkeypatch.setattr(ha_export_fenster, "kosten_profil", _zaehlend, raising=False)

    from backend.api.routes.ha_export import anlage_sensoren, anlage_sensorwerte

    monkeypatch.setattr(anlage_sensoren, "baue_fenster_kontext", _kontext_zaehlend)

    async def _p(db_, anlage_, *, skip_jitter=False):
        return _prognose()

    async def _q(db_, anlage_):
        return _preis()

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)

    from backend.services.ha_mqtt_sync import publish_anlage_sensors
    from backend.api.routes.ha_export import calculate_anlage_sensors, calculate_investition_sensors
    from backend.models.investition import Investition
    from sqlalchemy import select

    kontext: dict = {}
    await calculate_anlage_sensors(db, anlage, skip_jitter=True, kontext_out=kontext)
    geraete = list((await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )).scalars().all())
    for inv in geraete:
        await calculate_investition_sensors(
            db, inv, None, None, None, fenster_ctx=kontext.get("fenster")
        )

    assert len(kontext_aufrufe) == 1, (
        f"der Fenster-Kontext wurde {len(kontext_aufrufe)}× gebaut — er gehört "
        f"einmal je Anlage gebaut und dann gereicht"
    )
    assert len(profil_aufrufe) == 1 + len(geraete), (
        f"{len(profil_aufrufe)} Kostenprofile bei {len(geraete)} Geräten — erwartet "
        f"ist die eine mengenneutrale Grundrechnung plus genau eine je Geräte-Fenster"
    )
