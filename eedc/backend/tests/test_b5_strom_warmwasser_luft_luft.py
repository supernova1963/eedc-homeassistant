"""B5 — der Warmwasser-STROM einer Split-Klimaanlage (zweite Hälfte von N-304).

N-304 gab `warmwasser_kwh` die Bedingung `!luft_luft`: eine Split-Klimaanlage
hat keinen Warmwasserkreis. Für den zugehörigen **Strom** galt derselbe Satz und
stand trotzdem nicht da — `strom_warmwasser_kwh` wurde einer Klimaanlage mit
getrennter Strommessung weiter angeboten, und der Daten-Checker verlangte ihn
unter dem Label „Strom Heizen/Warmwasser".

⚠ **Warum es nicht früher auffiel:** die Bedingungs-Auswertung war eine Kette
aus `elif bedingung == "…"` und konnte genau **eine** Bedingung ausdrücken.
`strom_warmwasser_kwh` braucht zwei (getrennte Strommessung **und** keine
Klimaanlage). Der Nachzug hing also nicht am Vergessen, sondern an einer
Struktur, die den Fall nicht formulieren konnte.
"""

from datetime import date

from backend.core.field_definitions import (
    INVESTITION_FELDER,
    bedingung_erfuellt,
    get_felder_fuer_investition,
)
# Auf Modulebene, damit `Base.metadata.create_all` in der `db`-Fixture die
# Tabellen kennt — ein Import erst IM Test kommt dafür zu spät.
from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)

KLIMA_GETRENNT = {"wp_art": "luft_luft", "getrennte_strommessung": True}
WP_GETRENNT = {"wp_art": "luft_wasser", "getrennte_strommessung": True}


def _feldnamen(parameter):
    return {f["feld"] for f in get_felder_fuer_investition("waermepumpe", parameter)}


def test_die_klimaanlage_bekommt_keinen_warmwasser_strom_mehr():
    felder = _feldnamen(KLIMA_GETRENNT)
    assert "strom_warmwasser_kwh" not in felder
    # Die Heiz-Achse existiert an einer Klimaanlage sehr wohl — dieselbe
    # Trennlinie wie bei `heizenergie_kwh` in N-304.
    assert "strom_heizen_kwh" in felder


def test_die_klassische_waermepumpe_behaelt_ihn():
    """Gegenprobe — sonst hätte der Fix das Feld für alle abgeschaltet."""
    felder = _feldnamen(WP_GETRENNT)
    assert "strom_warmwasser_kwh" in felder
    assert "strom_heizen_kwh" in felder


def test_ohne_getrennte_strommessung_bleibt_es_bei_der_alten_regel():
    """Die erste Bedingung wirkt unverändert — beide Teile des UND zählen."""
    assert "strom_warmwasser_kwh" not in _feldnamen({"wp_art": "luft_wasser"})
    assert "stromverbrauch_kwh" in _feldnamen({"wp_art": "luft_wasser"})


def test_altbestand_ohne_wp_art_gilt_nicht_als_klimaanlage():
    """Eine fehlende Angabe schaltet die Erwartung nicht ab (N-304-Regel)."""
    assert "strom_warmwasser_kwh" in _feldnamen({"getrennte_strommessung": True})


# ─── Der Auswerter selbst ───────────────────────────────────────────────────

def test_eine_liste_von_bedingungen_gilt_als_UND():
    werte = {"a": True, "b": False}
    assert bedingung_erfuellt(["a", "!b"], werte)
    assert not bedingung_erfuellt(["a", "b"], werte)
    assert not bedingung_erfuellt(["!a", "!b"], werte)


def test_einzelne_bedingung_und_negation_verhalten_sich_wie_bisher():
    werte = {"a": True, "b": False}
    assert bedingung_erfuellt("a", werte)
    assert not bedingung_erfuellt("!a", werte)
    assert bedingung_erfuellt("!b", werte)
    assert bedingung_erfuellt(None, werte)


def test_ein_unbekannter_schluessel_zeigt_das_feld():
    """Fail-open, bitgleich zum früheren Verhalten.

    Die Gegenrichtung wäre schlimmer: ein Tippfehler ließe ein bereits
    ZUGEORDNETES Feld unsichtbar verschwinden und unlöschbar zurückbleiben.
    Ein Auswerter, der stattdessen wirft, wäre die F-59-Klasse (latenter 500er).
    """
    assert bedingung_erfuellt("gibt_es_nicht", {"a": True})
    assert bedingung_erfuellt(["a", "gibt_es_nicht"], {"a": True})


def test_jede_bedingung_der_registry_ist_ein_bekannter_schluessel():
    """Der Wächter, der das Fail-open trägt.

    Weil ein Tippfehler zur Laufzeit **nicht** auffällt (das Feld erscheint
    einfach), muss er hier auffallen. Ohne diesen Test wäre `fail-open` eine
    Einladung, eine Bedingung stillschweigend wirkungslos zu machen.
    """
    from backend.core.field_definitions import _bedingungs_werte

    bekannt = set(_bedingungs_werte({}))
    unbekannt = []
    for typ, felder in INVESTITION_FELDER.items():
        # N-79-Nebenbefund (29.08.): hier stand `if not isinstance(felder, list):
        # continue` — das übersprang `sonstiges`, dessen Registry-Eintrag ein
        # **Dict von Listen** ist. Heute trägt dort kein Feld eine `bedingung`,
        # der Wächter hatte also eine blinde Stelle ohne Schaden. Sie bleibt
        # nicht stehen: `get_stand_felder` löst dieselbe Form seit je auf.
        listen = felder.values() if isinstance(felder, dict) else [felder]
        for feld in [f for liste in listen for f in liste]:
            bedingung = feld.get("bedingung")
            if not bedingung:
                continue
            tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
            for token in tokens:
                schluessel = token[1:] if token.startswith("!") else token
                if schluessel not in bekannt:
                    unbekannt.append((typ, feld["feld"], token))

    assert not unbekannt, f"Bedingung ohne Auswertung: {unbekannt}"


# ─── Der Daten-Checker zieht nach ───────────────────────────────────────────
#
# Harness wie in `test_wp_klimaanlage_phase1.py` — dieselbe Fläche, dieselbe
# Aufrufform (`_check_wp_monatsdaten` ist synchron und nimmt inv/name/param/
# monatsdaten).


async def _wp_befunde(db, *, parameter: dict, imd_daten: dict | None) -> list:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="B5", leistung_kwp=10.0,
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
    if imd_daten is not None:
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2025, monat=1, verbrauch_daten=imd_daten,
        ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       einspeisung_kwh=200.0, netzbezug_kwh=150.0))
    await db.commit()

    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    wp = next(i for i in geladen.investitionen if i.typ == "waermepumpe")
    # ⚠ Die erwarteten Monate kommen aus der ANLAGEN-Liste, nicht aus der
    # Investition. Ein leeres `[]` an dieser Stelle liefert null Befunde — die
    # Probe wäre gegenstandslos und trotzdem grün.
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    assert monatsdaten, "ohne Anlagen-Monatszeile prueft der Check gar nichts"
    return DatenChecker(db)._check_wp_monatsdaten(
        wp, wp.bezeichnung, wp.parameter, monatsdaten,
    )


async def test_der_checker_verlangt_von_der_klimaanlage_kein_warmwasser(db):
    """Sonst forderte er ein Feld, das der Monatsabschluss nicht mehr anbietet.

    Genau die Klasse, an der N-86 schon einmal hing: dieselbe Anlage, zwei
    Flächen, gegenteilige Aussage.
    """
    ergebnisse = await _wp_befunde(
        db, parameter=KLIMA_GETRENNT, imd_daten={"strom_heizen_kwh": 210.0},
    )
    fehlend = [e for e in ergebnisse if "fehlt" in e.meldung]
    assert not fehlend, [e.meldung for e in fehlend]


async def test_die_klassische_wp_verlangt_weiterhin_beide_seiten(db):
    """Gegenprobe — nur der Heizstrom reicht dort NICHT.

    Ohne sie könnte der Fix die Warmwasser-Erwartung für alle abschalten.
    """
    ergebnisse = await _wp_befunde(
        db, parameter=WP_GETRENNT, imd_daten={"strom_heizen_kwh": 210.0},
    )
    # Die klassische WP kennt beide Seiten der Achse; fehlt eine, ist die Zeile
    # trotzdem vollständig genug (der Check verlangt EINE der beiden) — die
    # Erwartung selbst bleibt aber „Heizen/Warmwasser".
    strom = [e for e in ergebnisse if "Strom" in e.meldung and "fehlt" in e.meldung]
    assert not strom, [e.meldung for e in strom]


async def test_nur_warmwasser_gepflegt_ist_an_der_klimaanlage_eine_LUECKE(db):
    """Der Fall, an dem sich die alte von der neuen Logik trennt.

    Alt: „fehlt", wenn Heizen **und** Warmwasser leer sind — ein an einer
    Klimaanlage gepflegter Warmwasser-Wert deckte die fehlende Heiz-Zeile also
    zu. Neu: an einer Klimaanlage zählt allein der Heizstrom, denn die
    Warmwasser-Seite gibt es dort nicht (das Feld wird gar nicht mehr
    angeboten). Ohne diese Probe wäre die Bedingungs-Änderung ungedeckt — die
    beiden anderen Checker-Proben fallen bei altem Code nicht.
    """
    ergebnisse = await _wp_befunde(
        db, parameter=KLIMA_GETRENNT, imd_daten={"strom_warmwasser_kwh": 80.0},
    )
    strom = [e for e in ergebnisse if "Strom" in e.meldung and "fehlt" in e.meldung]
    assert len(strom) == 1, [e.meldung for e in ergebnisse]
    assert "Strom Heizen fehlt" in strom[0].meldung


async def test_nur_warmwasser_gepflegt_reicht_der_klassischen_wp_weiter(db):
    """Gegenprobe: dort ist Warmwasser eine echte Seite der Achse."""
    ergebnisse = await _wp_befunde(
        db, parameter=WP_GETRENNT, imd_daten={"strom_warmwasser_kwh": 80.0},
    )
    strom = [e for e in ergebnisse if "Strom" in e.meldung and "fehlt" in e.meldung]
    assert not strom, [e.meldung for e in strom]


async def test_der_checker_meldet_der_klimaanlage_nur_strom_heizen(db):
    """Fehlt der Heizstrom, heißt die Meldung nicht mehr „Heizen/Warmwasser"."""
    ergebnisse = await _wp_befunde(db, parameter=KLIMA_GETRENNT, imd_daten=None)
    strom = [e for e in ergebnisse if "Strom" in e.meldung and "fehlt" in e.meldung]
    assert len(strom) == 1, [e.meldung for e in ergebnisse]
    assert "Strom Heizen fehlt" in strom[0].meldung
    assert "Warmwasser" not in strom[0].meldung


async def test_der_klassischen_wp_bleibt_das_alte_label(db):
    """Gegenprobe zum Label — es darf nicht für alle umgeschrieben werden."""
    ergebnisse = await _wp_befunde(db, parameter=WP_GETRENNT, imd_daten=None)
    strom = [e for e in ergebnisse if "Strom" in e.meldung and "fehlt" in e.meldung]
    assert len(strom) == 1, [e.meldung for e in ergebnisse]
    assert "Strom Heizen/Warmwasser fehlt" in strom[0].meldung


# ── Dritte Fläche derselben Regel: die kWh-Zähler-ABDECKUNG ──────────────
#
# Gemeldet von **OB73-gif** (#263, 25.08.2026): *„1 von 4 Komponenten ohne
# vollständige kWh-Zähler-Abdeckung … Midea Portasplit (waermepumpe):
# strom_heizen_kwh, strom_warmwasser_kwh"*.
#
# `_check_energieprofil_abdeckung` forderte bei `getrennte_strommessung` beide
# Seiten der Achse — **ohne** die `luft_luft`-Ausnahme, die oben im
# Monatsdaten-Check und 150 Zeilen tiefer bei den Zusatz-Zählern längst steht.
# Für ihn war der Hinweis **unauflösbar**: den Warmwasser-Strom gibt es an
# seinem Gerät nicht, und der Monatsabschluss bietet das Feld gar nicht mehr an
# (N-304). Die Folgewellen-Klasse aus #236 — ein Filter auf einer Schicht
# reicht nicht, wenn mehrere Pfade dieselbe Frage stellen.


async def _abdeckungs_befunde(db, *, parameter: dict, gemappte_felder: dict) -> list:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="B5-Abdeckung", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Midea Portasplit",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {
        f: {"strategie": "sensor", "sensor_id": f"sensor.{f}"}
        for f in gemappte_felder
    }}}}
    await db.commit()

    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    return DatenChecker(db)._check_energieprofil_abdeckung(geladen)


def _details(ergebnisse) -> str:
    return " ".join(
        (e.details or "") + " " + (e.meldung or "") for e in ergebnisse
    )


async def test_abdeckung_verlangt_von_der_klimaanlage_keinen_warmwasser_strom(db):
    """Der Melder-Fall: nur `strom_heizen_kwh` gemappt ⇒ vollständig."""
    ergebnisse = await _abdeckungs_befunde(
        db, parameter=KLIMA_GETRENNT, gemappte_felder=["strom_heizen_kwh"],
    )
    assert "strom_warmwasser_kwh" not in _details(ergebnisse)


async def test_abdeckung_haelt_der_klassischen_wp_beide_seiten_vor(db):
    """Gegenprobe: eine Luft-Wasser-WP hat den Warmwasserkreis sehr wohl.

    Ohne sie wäre der Fix oben eine Nullprüfung — die Beinahe-Falle aus F-33.
    """
    ergebnisse = await _abdeckungs_befunde(
        db, parameter=WP_GETRENNT, gemappte_felder=["strom_heizen_kwh"],
    )
    assert "strom_warmwasser_kwh" in _details(ergebnisse)


async def test_abdeckung_meldet_der_klimaanlage_weiterhin_fehlenden_heizstrom(db):
    """`strom_heizen_kwh` bleibt gefordert — bewusst nicht Teil des Fixes.

    Ob ein zugeordneter Betriebsmodus-Sensor ihn ersetzen kann, hängt davon
    ab, ob `getrennte_strommessung` an diesem Gerät überhaupt richtig gesetzt
    ist (der Aggregator ignoriert dann `stromverbrauch_kwh`, #183). Offener
    Punkt — diese Probe hält fest, dass er offen IST und nicht versehentlich
    mitgelöst wurde.
    """
    ergebnisse = await _abdeckungs_befunde(
        db, parameter=KLIMA_GETRENNT, gemappte_felder=[],
    )
    assert "strom_heizen_kwh" in _details(ergebnisse)

