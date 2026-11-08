"""N-391 — **EIN Wärmemengenzähler über Heizung und Warmwasser hat einen Ort.**

**SOLL Wärme/Klima §3.2a (R1) · §3.2b (R2) · §6 Sprosse F6 · Konzept §2.1 (Q_ges)
· K1 (die Gesamtmenge ist die Wahrheit) · ADR-002/P4, P12.**

⛔ **Der Anlassfall, gemessen am 14.09.2026 an den echten Routen.** Eine
Luft-Wasser-Wärmepumpe mit Umschaltventil hat EINEN Vorlauf; der
Wärmemengenzähler sitzt dort und misst beide Funktionen. Ein Feld dafür gab es
nicht — das Handbuch schickte solche Anwender auf *Heizwärme*. Mit getrennter
Strommessung (F5) rechnete eedc daraus in **vier** Sichten (Hub, Cockpit → Monat,
→ Jahr, → Tag):

    Arbeitszahl Heizen = 3000 kWh Gesamtwärme ÷ 600 kWh Heizstrom = **5,0**

statt der wahren 3,0 — **ohne jeden Grund daneben**, und 5,0 ist für eine
moderne Wärmepumpe eine gute, plausible Zahl. Der Plausibilitäts-Prüfer schweigt
(er sieht nur die Gesamt-Arbeitszahl 3,0 gegen die Schwelle 7,0), das Handbuch
versprach ausdrücklich das Gegenteil („die getrennten Arbeitszahlen bleiben ohne
Zahl"), und SOLL §6 führt die Sprosse **F6** mit der Zusage „keine Zahl je
Funktion". Drei Zusagen, eine Falschzahl.

⭐ **Die Lese-Hälfte stand schon.** ``waerme_gesamt_kwh`` (D1, seit 26.08.):
*„Liegt eine gemessene Gesamtwärme vor, gilt sie. Sonst ist die Wärme die Summe
ihrer beiden Achsen."* Es fehlte der **Erfassungsweg** — ohne Registry-Eintrag
kein Formularfeld, kein Zuordnungs-Slot, kein CSV-Suffix. Der Bau vollendet einen
halben Mechanismus; er erfindet keinen.

⛔ **Was hier ausdrücklich NICHT gesperrt wird — die Gegenprobe zur Sperre.**
Wer den Wärmemengenzähler **nur auf dem Heizkreis** hat (Lage D, die Sprosse
zwischen F6 und F7), trägt weiterhin *Heizwärme* — und seine Arbeitszahl Heizen
ist **richtig**. In den Daten ist diese Lage von der alten Falscheingabe nicht zu
unterscheiden; genau deshalb heilt keine Sperre, sondern nur ein Feld
(``waerme_kwh``), das der Anwender selbst füllt. Aus demselben Grund behält die
Funktions-Zahl auch, wer **Gesamtwert und Aufteilung** pflegt: seine
Einzelwerte sind gemessen, Zähler und Nenner tragen dieselbe Funktion, R2 ist
erfüllt.

**Migration: keine.** Kein Feld wird umbenannt, kein Wert verschoben. Wer die
Summe weiter unter *Heizwärme* führt, sieht exakt dieselben Zahlen wie bisher —
bis er selbst umträgt.

Schwesterdateien: ``test_n441_geraete_identitaet.py`` (P18 — dieselbe Zeile auf
der Perioden-Achse), ``test_r2_je_funktion.py`` (die Geräte-Dimension desselben
Quotienten, N-427/N-438), ``test_waerme_vorschlag_b1.py`` (F2 schlägt jetzt
*Wärme gesamt* vor), ``test_soll_waerme_klima_simulation_anlagen.py`` (A10/8ear —
die Nachbarlage, die unberührt bleibt).
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.api.routes.import_export.csv_operations import (
    get_csv_template_info,
    import_csv,
)
from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_WAERME_NICHT_JE_FUNKTION,
    geraete_mit_gesamtwaerme,
    waerme_gesamt_je_geraet,
    waerme_gesamt_kwh,
)
from backend.core.field_definitions import (
    BEDARF_GRUPPEN_ALTERNATIV,
    INVESTITION_FELDER,
    get_feld_bedarf,
)
from backend.models import Anlage, Investition, Monatsdaten  # noqa: F401
from backend.models.investition import InvestitionMonatsdaten
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.community_service import prepare_community_data
from backend.tests.test_csv_vorlage_rundlauf_f55 import _FakeUpload
from backend.services.monats_fakten import lade_monats_fakten
from backend.tests.test_bs6_kaelte_je_tag import (
    DATUM as TAG_DATUM,
)
from backend.tests.test_bs6_kaelte_je_tag import (
    _tageszaehler,
    _tageszeile,
    _zaehler,
)
from backend.tests.test_r2_je_funktion import (
    JAHR,
    MONAT,
    _WP,
    _anlage,
    _geraet,
    _jahr,
    _monat,
)

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

#: Die nachgestellte Lage B+F5: EIN Wärmemengenzähler über 3.000 kWh, Strom
#: getrennt 600 (Heizen) + 400 (Warmwasser). Wahre Gesamt-Arbeitszahl: 3,0.
LAGE_B = {"strom_heizen_kwh": 600.0, "strom_warmwasser_kwh": 400.0,
          "waerme_kwh": 3000.0}
#: Lage D — derselbe Strom, aber der Zähler misst **nur** den Heizkreis.
LAGE_D = {"strom_heizen_kwh": 600.0, "strom_warmwasser_kwh": 400.0,
          "heizenergie_kwh": 3000.0}
#: Gesamtzähler **und** Aufteilung, widerspruchsfrei.
LAGE_BEIDES = {"strom_heizen_kwh": 600.0, "strom_warmwasser_kwh": 400.0,
               "waerme_kwh": 3000.0, "heizenergie_kwh": 2100.0,
               "warmwasser_kwh": 900.0}


async def _hub(db, anlage_id) -> dict:
    from backend.api.routes.investitionen.dashboards import (
        get_waermepumpe_dashboard,
    )

    geraete = await get_waermepumpe_dashboard(
        anlage_id, strompreis_cent=30.0, db=db,
    )
    return geraete[0].zusammenfassung


async def _lage(db, daten: dict, name: str = "N-391"):
    a = await _anlage(db, name)
    await _geraet(db, a, "WP", dict(_WP), dict(daten))
    await db.commit()
    return a


# ═══ K1 — der Gesamtwert schlägt die Summanden (D1) ═════════════════════════

@pytest.mark.asyncio
async def test_k1_gesamtwert_vor_summanden(db):
    """Die Vorrangregel ist K1, nicht Bequemlichkeit: die Gesamtmenge ist die Wahrheit.

    ⚠ **Bewusst die Gegenrichtung zur Stromseite** (`wp_strom_stufe`/K3): Dort
    gewinnt die vollständige feine Aufteilung, weil `getrennte_strommessung`
    erklärt, dass die zwei Zähler zusammen das Ganze sind. Auf der Wärmeseite
    gibt es keine solche Erklärung.
    """
    # ⚠ **Die Aufteilung ist hier bewusst UNvollständig** (2100 + 800 = 2900
    # gegen 3000): Wären beide Wege zahlengleich, könnte die Probe nicht
    # unterscheiden, welchen eedc genommen hat — sie wäre grün, auch wenn D1
    # ausgebaut wäre.
    a = await _lage(db, {"strom_heizen_kwh": 600.0, "strom_warmwasser_kwh": 400.0,
                         "waerme_kwh": 3000.0, "heizenergie_kwh": 2100.0,
                         "warmwasser_kwh": 800.0})

    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))

    assert fakten[0].wp.waerme_kwh == pytest.approx(3000.0), "die Summe wäre 2900"
    assert fakten[0].wp.waerme_ist_gesamt is True
    # Die Aufteilung steht daneben, nicht an ihrer Stelle.
    assert fakten[0].wp.heizung_kwh == pytest.approx(2100.0)
    assert fakten[0].wp.warmwasser_kwh == pytest.approx(800.0)


# ═══ K2 — die Falschzahl ist weg, mit Grund statt Zahl ══════════════════════

@pytest.mark.asyncio
async def test_k2_arbeitszahl_heizen_ist_weg_und_nennt_den_grund(db):
    """5,0 war die Gesamtwärme über dem Heizstrom — in vier Sichten, ohne Grund.

    ⚠ Der Grund ist der **Spiegel** von „Strom nicht getrennt je Funktion
    gemessen", derselbe Satzbau: es ist derselbe Sachverhalt in der anderen
    Größe. Zwei Sprachen für eine Sache wären die N-327-Klasse.
    """
    a = await _lage(db, LAGE_B)

    hub = await _hub(db, a.id)
    m = await _monat(db, a.id)
    j = await _jahr(db, a.id)

    assert hub["jaz_heizen"] is None, "5,0 = 3000 ÷ 600 war die Zahl"
    assert hub["jaz_heizen_grund"] == GRUND_WAERME_NICHT_JE_FUNKTION
    assert hub["jaz_warmwasser_grund"] == GRUND_WAERME_NICHT_JE_FUNKTION, (
        "der alte Satz (kein Wärmemengenzähler zugeordnet) war falsch — "
        "der Zähler IST zugeordnet, er misst nur beide Funktionen"
    )
    assert m.wp_jaz_heizen is None
    assert m.wp_jaz_heizen_grund == GRUND_WAERME_NICHT_JE_FUNKTION
    assert m.wp_jaz_warmwasser_grund == GRUND_WAERME_NICHT_JE_FUNKTION
    assert j.wp_jaz_heizen is None
    assert j.wp_jaz_heizen_grund == GRUND_WAERME_NICHT_JE_FUNKTION


# ═══ K3 — die Gegenproben: wer je Funktion misst, behält seine Zahlen ═══════

@pytest.mark.asyncio
async def test_k3_lage_d_behaelt_ihre_richtige_zahl(db):
    """**Die Gegenprobe, an der jede reine Sperre scheitert.**

    Wärmemengenzähler **nur auf dem Heizkreis**, Warmwasser ungemessen: 3000 ÷
    600 = 5,0 ist hier **richtig**. In den Daten ist diese Lage von der alten
    Falscheingabe nicht zu unterscheiden — eine Sperre „F5 und nur eine
    Wärmeachse" nähme ihr die Zahl weg. Deshalb hängt die Sperre am **Feld**,
    das der Anwender füllt, nicht an einer geratenen Lage.
    """
    a = await _lage(db, LAGE_D, name="N-391 Lage D")

    hub = await _hub(db, a.id)
    m = await _monat(db, a.id)

    assert hub["jaz_heizen"] == pytest.approx(5.0)
    assert hub["jaz_heizen_grund"] is None
    assert m.wp_jaz_heizen == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_k3b_gesamtzaehler_neben_der_aufteilung_sperrt_nichts(db):
    """Wer beides pflegt, behält beide Zahlen — sie sind gemessen und abgegrenzt.

    ⛔ Ein „sobald ein Gesamtwert dasteht, sperre beide" wäre dieselbe Übersperre
    wie in K3, nur eine Ebene höher: 2100 ÷ 600 und 900 ÷ 400 stammen aus
    Zählern **derselben** Funktion. Gesperrt wird nur, wofür es keinen eigenen
    Wärmewert gibt.
    """
    a = await _lage(db, LAGE_BEIDES, name="N-391 beides")

    hub = await _hub(db, a.id)

    assert hub["jaz_heizen"] == pytest.approx(3.5)
    assert hub["jaz_warmwasser"] == pytest.approx(2.25)
    assert hub["gesamt_waerme_kwh"] == pytest.approx(3000.0)


# ═══ K4/K5 — die Mengen und die Gesamtzahl bleiben, überall dieselben ═══════

@pytest.mark.asyncio
async def test_k4_der_hub_verliert_die_waerme_nicht(db):
    """**V-1**: Die Hub-SUMME las roh, was die Zeile seit N-441 kanonisch liest.

    Gemessen vor dem Bau: ``gesamt_waerme_kwh`` 0,0 · ``durchschnitt_cop`` None ·
    ``ersparnis_euro`` None — während *Cockpit → Monat* für dieselbe Zeile 3.000
    kWh und 3,0 zeigte. Dieselbe Anlage, zwei Auskünfte (S1).
    """
    a = await _lage(db, LAGE_B)

    hub = await _hub(db, a.id)

    assert hub["gesamt_waerme_kwh"] == pytest.approx(3000.0)
    assert hub["durchschnitt_cop"] == pytest.approx(3.0)
    assert hub["ersparnis_euro"] is not None, "ohne Wärme gab es keine Ersparnis"
    # Die Kachel *Heizwärme* zeigt NICHT die Gesamtmenge — sie ist ein
    # Einzelwert, und den gibt es hier nicht.
    assert not hub["gesamt_heizenergie_kwh"]


@pytest.mark.asyncio
async def test_k5_dieselbe_gesamtzahl_in_hub_monat_und_jahr(db):
    """S1: eine Größe, ein Wert — 3.000 ÷ 1.000 = 3,0."""
    a = await _lage(db, LAGE_B)

    hub = await _hub(db, a.id)
    m = await _monat(db, a.id)
    j = await _jahr(db, a.id)

    assert hub["durchschnitt_cop"] == pytest.approx(3.0)
    assert m.wp_jaz == pytest.approx(3.0)
    assert j.wp_cop == pytest.approx(3.0)
    assert m.wp_waerme_kwh == pytest.approx(3000.0)
    assert j.wp_waerme_kwh == pytest.approx(3000.0)


@pytest.mark.asyncio
async def test_k5b_der_tag_liest_dieselbe_regel(db):
    """Cockpit → Tag: bis zum Bau stand dort ``waerme_gesamt_kwh(None, …)``.

    Der Tag konnte die Vorrangregel gar nicht anwenden — das erste Argument war
    fest ``None``, weil es das Feld nicht gab. Jetzt kommt sein Tageswert über
    denselben Aggregator wie Heizwärme und Warmwasser-Wärme.
    """
    from backend.api.routes.energie_profil.views import get_tag_detail

    a = await _anlage(db, "N-391 Tag")
    a.sensor_mapping = {"investitionen": {}}
    inv = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=dict(_WP),
    )
    db.add(inv)
    await db.flush()
    _tageszaehler(db, a, inv, "waerme_kwh", 30.0)
    _tageszaehler(db, a, inv, "strom_heizen_kwh", 6.0)
    _tageszaehler(db, a, inv, "strom_warmwasser_kwh", 4.0)
    _tageszeile(db, a, {inv.id: 10.0})
    a.sensor_mapping = dict(a.sensor_mapping)
    await db.commit()

    tag = await get_tag_detail(a.id, TAG_DATUM, db)

    assert tag.wp_waerme_kwh == pytest.approx(30.0)
    assert tag.wp_jaz == pytest.approx(3.0)
    assert tag.wp_jaz_heizen is None
    assert tag.wp_jaz_heizen_grund == GRUND_WAERME_NICHT_JE_FUNKTION


# ═══ K6/K7 — die beiden Ausgänge: HA-Sensoren und Community ════════════════

@pytest.mark.asyncio
async def test_k6_die_ha_sensoren_tragen_die_waerme(db):
    """``ha_export`` faltet je Investition und las die Wärme roh (P10-Restschuld).

    Ohne die Umhängung meldeten *Arbeitszahl* und *Ersparnis* dieser Wärmepumpe
    nichts — in Home Assistant, wo die Zahl in Automationen weiterläuft und ein
    einmal publizierter Wert stehen bleibt.
    """
    from backend.api.routes.ha_export import calculate_investition_sensors

    a = await _lage(db, LAGE_B)
    inv = (await db.execute(
        select(Investition).where(Investition.anlage_id == a.id)
    )).scalars().first()

    werte = {s.definition.key: s.value
             for s in await calculate_investition_sensors(db, inv, None)}

    assert werte["wp_cop_durchschnitt"] == pytest.approx(3.0), (
        "ohne Wärme lieferte der Sensor keinen Wert, nur einen Grund"
    )
    assert werte.get("wp_ersparnis_euro")


@pytest.mark.asyncio
async def test_k7_der_community_payload_verliert_die_waerme_nicht(db):
    """Kein neues Payload-Feld: der Server liest ``wp_heizwaerme_kwh`` nur in der Summe.

    ⚠ Gemessen an der **echten** Route (``prepare_community_data``) — der
    Payload entsteht nur, wenn Zählerzeile, PV und ein abgeschlossener Monat
    zusammenkommen.
    """
    from backend.tests.test_n441_geraete_identitaet import (
        _community_anlage,
        _monatswert,
    )

    anlage_id = await _community_anlage(db, [dict(LAGE_B)])

    juli = _monatswert(await prepare_community_data(db, anlage_id))

    assert juli["wp_heizwaerme_kwh"] == pytest.approx(3000.0, abs=0.1)
    assert juli["wp_stromverbrauch_kwh"] == pytest.approx(1000.0, abs=0.1)


# ═══ K8/K9 — der Melder: keine Falschforderung, eine echte Invariante ══════

async def _wp_befunde(db, daten: dict) -> list:
    """Der Daten-Checker über eine WP mit **einer** Monatszeile."""
    from sqlalchemy.orm import selectinload

    from backend.services.daten_checker import DatenChecker

    a = await _anlage(db, "N-391 Checker")
    inv = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(JAHR, MONAT, 1), anschaffungskosten_gesamt=12000.0,
        parameter=dict(_WP),
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=JAHR, monat=MONAT, verbrauch_daten=dict(daten),
    ))
    db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT,
                       einspeisung_kwh=200.0, netzbezug_kwh=150.0))
    await db.commit()

    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == a.id)
    )).scalar_one()
    wp = next(i for i in geladen.investitionen if i.typ == "waermepumpe")
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == a.id)
    )).scalars().all())
    assert monatsdaten, "ohne Anlagen-Monatszeile prueft der Check gar nichts"
    return DatenChecker(db)._check_wp_monatsdaten(
        wp, wp.bezeichnung, wp.parameter, monatsdaten,
    )


@pytest.mark.asyncio
async def test_k8_der_checker_fordert_keine_heizwaerme_mehr(db):
    """*Heizwärme* und *Wärme gesamt* sind eine Alternativ-Gruppe.

    Sie weiter anzumahnen wäre die N-86-Klasse: Die Zuordnungs-Fläche sagt für
    dasselbe Feld „bereits zugeordnet", der Checker „fehlt" — dieselbe Anlage,
    zwei Aussagen.
    """
    befunde = await _wp_befunde(db, LAGE_B)

    assert not [b for b in befunde if "Heizwärme fehlt" in b.meldung], (
        [b.meldung for b in befunde]
    )
    # Gegenprobe: ohne jede Wärme mahnt er weiter.
    ohne = await _wp_befunde(db, {"strom_heizen_kwh": 600.0,
                                  "strom_warmwasser_kwh": 400.0})
    assert [b for b in ohne if "Heizwärme fehlt" in b.meldung]


@pytest.mark.asyncio
async def test_k9_die_invariante_meldet_den_widerspruch(db):
    """Gesamtwärme kleiner als ihre Aufteilung — die Menge verschwände lautlos.

    ⚠ **Nur diese Richtung.** Ist der Gesamtwert GRÖSSER als die Summe der
    Achsen, ist das der Normalfall einer halb gemessenen Aufteilung (eine Achse
    eigens gezählt, der Rest im Gesamtzähler) und kein Fehler.
    """
    befunde = await _wp_befunde(db, {
        "strom_heizen_kwh": 600.0, "strom_warmwasser_kwh": 400.0,
        "waerme_kwh": 2100.0, "heizenergie_kwh": 2100.0, "warmwasser_kwh": 900.0,
    })

    treffer = [b for b in befunde if "Gesamtwärme kleiner" in b.meldung]
    assert len(treffer) == 1, [b.meldung for b in befunde]
    assert f"{MONAT:02d}/{JAHR}" in treffer[0].meldung
    assert "Wärme gesamt" in treffer[0].details

    # Gegenprobe: widerspruchsfrei ⇒ still.
    still = await _wp_befunde(db, LAGE_BEIDES)
    assert not [b for b in still if "Gesamtwärme kleiner" in b.meldung]


# ═══ K10 — die beiden Registries führen dasselbe Feld ══════════════════════

def test_k10_der_client_spiegelt_das_feld():
    """**V-4**: Die zwei Feld-Registries sind nur durch Kommentare verbunden.

    `check-spiegel-backend.mjs` deckt sie nicht ab, und kein pytest verglich sie.
    Wer ein Feld nur auf einer Seite anlegt, bekommt es entweder im
    Monatsabschluss (Client) oder auf der Zuordnungs-Fläche (Backend) —
    lautlos. Diese Probe deckt genau das neue Feld, nicht die ganze Registry:
    der baumweite Wächter ist ein eigener Fund.
    """
    backend_labels = {f["feld"]: f["label"]
                      for f in INVESTITION_FELDER["waermepumpe"]}
    assert backend_labels["waerme_kwh"] == "Wärme gesamt"

    quelle = (_FRONTEND / "src/lib/fieldDefinitions.ts").read_text(encoding="utf-8")
    assert "feld: 'waerme_kwh'" in quelle, (
        "ohne Spiegel fehlt das Feld im Monatsabschluss"
    )
    assert "label: 'Wärme gesamt'" in quelle, "beide SoT bleiben wortgleich"


# ═══ K11 — der Erfassungsweg trägt: CSV rein und raus ══════════════════════

@pytest.mark.asyncio
async def test_k11_csv_rundlauf_traegt_den_gesamtwert(db):
    """Ohne ``csv_suffix`` überspringen Export und Custom-Import das Feld still.

    Geprüft wird der **Rundlauf** (Vorlage → Import), nicht Export→Import: Der
    Export liest denselben Suffix wie der Import und wäre auch dann grün, wenn
    die Vorlage die Spalte gar nicht anbietet (F-55).
    """
    a = Anlage(anlagenname="N-391 CSV", leistung_kwp=10.0,
               installationsdatum=date(2024, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WpKeller",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter={"wp_art": "luft_wasser"},
    )
    db.add(inv)
    await db.commit()

    vorlage = await get_csv_template_info(a.id, db)
    spalte = f"{inv.bezeichnung}_Waerme_Gesamt_kWh"
    assert spalte in vorlage.spalten, vorlage.spalten

    puffer = StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(vorlage.spalten)
    schreiber.writerow([
        "2024" if s == "Jahr" else "3" if s == "Monat"
        else "3000" if s == spalte else ""
        for s in vorlage.spalten
    ])

    ergebnis = await import_csv(
        anlage_id=a.id, file=_FakeUpload(puffer.getvalue()),
        ueberschreiben=True, auto_wetter=False, db=db,
    )
    assert ergebnis.erfolg, ergebnis.fehler
    assert not ergebnis.fehler, ergebnis.fehler

    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id,
        )
    )).scalars().first()
    assert imd is not None and imd.verbrauch_daten["waerme_kwh"] == pytest.approx(3000.0)


# ═══ K12 — Alternativ-Gruppe: EIN Weg genügt, Summanden bleiben Summanden ══

@pytest.mark.asyncio
async def test_k12_ein_belegter_weg_deckt_die_waerme_gruppe(db):
    """Die Zuordnungs-Fläche verlangt keinen zweiten Wärmemengenzähler.

    ⛔ **Die Unterscheidung, ohne die N-391 an N-456 gescheitert wäre:**
    ``heizenergie_kwh`` und ``waerme_kwh`` sind an jedem Gerät beide „pflicht" —
    nach der Summanden-Regel von N-456 wären damit beide zu liefern. Sie sind
    aber **Alternativen** (``BEDARF_GRUPPEN_ALTERNATIV``), und ``wp_strom``
    bleibt daneben unverändert eine Summanden-Gruppe.
    """
    from backend.services.datenquellen_validierung import stufe_bedarf_ein
    from backend.services.mqtt_topic_registry import build_expected_topics

    a = await _anlage(db, "N-391 Gruppe")
    inv = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter=dict(_WP),
    )
    db.add(inv)
    await db.commit()

    eintraege = [e for e in await build_expected_topics(db, a)
                 if e["typ"] == "waermepumpe" and e["kategorie"] == "energy"]
    je_feld = {e["feld"]: e for e in eintraege}
    assert je_feld["waerme_kwh"]["bedarf_gruppe"] == "wp_waerme"
    assert je_feld["heizenergie_kwh"]["bedarf_gruppe"] == "wp_waerme"
    # Der Alternativ-Weg wird NICHT als „muss dieses Gerät liefern" markiert …
    assert je_feld["waerme_kwh"]["pflicht_am_geraet"] is False
    assert je_feld["heizenergie_kwh"]["pflicht_am_geraet"] is False
    # … die beiden Strom-Summanden sehr wohl (N-456 hält).
    assert je_feld["strom_heizen_kwh"]["pflicht_am_geraet"] is True
    assert je_feld["strom_warmwasser_kwh"]["pflicht_am_geraet"] is True

    def _eingabe(belegt: set[str]) -> list[dict]:
        return [
            {"id": e["feld"], "feld": e["feld"], "typ": "waermepumpe",
             "belegt": e["feld"] in belegt,
             "bedarf": e["bedarf"], "bedarf_gruppe": e["bedarf_gruppe"],
             "bedingung_anlage": None, "inv_id": str(inv.id),
             "pflicht_am_geraet": e["pflicht_am_geraet"]}
            for e in eintraege
        ]

    # Ein belegter gemeinsamer Wärmemengenzähler deckt die Gruppe.
    bedarf = stufe_bedarf_ein(_eingabe({"waerme_kwh"}), {"waermepumpe"})
    assert bedarf["heizenergie_kwh"]["bedarf"] == "inaktiv"
    assert bedarf["heizenergie_kwh"]["grund"] == "gruppe:wp_waerme"

    # Gegenprobe (N-456): ein belegter Heizstrom deckt den Warmwasser-Strom NICHT.
    strom = stufe_bedarf_ein(_eingabe({"strom_heizen_kwh"}), {"waermepumpe"})
    assert strom["strom_warmwasser_kwh"]["bedarf"] == "pflicht"


def test_k12b_die_gruppen_menge_sagt_es_einmal():
    """Die Unterscheidung steht an der Gruppe, nicht in zwei Konsumenten."""
    assert "wp_waerme" in BEDARF_GRUPPEN_ALTERNATIV
    assert "wp_strom" not in BEDARF_GRUPPEN_ALTERNATIV, (
        "bei getrennter Strommessung sind die beiden Felder Summanden (N-456)"
    )
    assert get_feld_bedarf("waermepumpe", "waerme_kwh")[1] == "wp_waerme"
    assert get_feld_bedarf("waermepumpe", "heizenergie_kwh")[1] == "wp_waerme"


def test_k13_gemessene_null_ist_kein_gesamtwert():
    """D1 «gepflegt» heißt > 0: eine gemessene 0 von «Wärme gesamt» gilt nicht als Gesamtwert, die Achsen zählen.

    Festschreibung eines Entscheids (Master, 8.11.2026, Päckchen T), kein Wächter. Grund: ein Gesamtzähler, der im
    Monat oder am Tag keinen neuen Stand liefert (eingefroren, Statistik-Lücke, erst seit kurzem zugeordnet), ergibt
    Δ = 0 — die Achsen tragen dann die bessere Zahl; sonst verlöre ein Gerät seine Aufteilung an einen Zähler, der
    nichts gemeldet hat ({@link geraete_mit_gesamtwaerme}). Der umgekehrte Fall (0 richtig, Achsen falsch) hieße, zwei
    Zähler messen dieselbe Wärme falsch — das entscheidet kein Programm. Die Lücke schließt der Daten-Checker
    («„Wärme gesamt“ ist 0, Heizwärme + Warmwasser-Wärme sind größer», `test_rf50_checker_export_jahr_phasen.py`).
    Dieselbe Weiche an fünf Stellen: Monat, Tag, Stunde, laufender Monat, Checker.
    """
    assert waerme_gesamt_kwh(0.0, 20, 5) == 25
    assert waerme_gesamt_kwh(0.0, None, None) == 0.0
    assert waerme_gesamt_kwh(None, None, None) == 0.0
    assert geraete_mit_gesamtwaerme({"1": 0.0, "2": 30}) == frozenset({"2"})
    assert waerme_gesamt_je_geraet({"1": 0.0}, {"1": 20}, {"1": 5}) == {"1": 25}
