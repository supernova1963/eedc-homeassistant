"""N-391c — **D1 an den Geldpfaden und im Nicht-DB-Pfad.**

**SOLL Wärme/Klima §3.3 (S1) · Konzept K1 · BERECHNUNGEN §3.5 (D1) ·
ADR-002/P4 · ADR-002/P9.**

⛔ **Der Befund, gemessen am 14.09.2026 über die echten Lesetüren.** Seit
WK-14b gibt es das Feld *Wärme gesamt* (``waerme_kwh``) und die Vorrangregel
**D1** (``waerme_gesamt_kwh``: „liegt eine gemessene Gesamtwärme vor, gilt
sie"). Hub, HA-Export, Monats-Fakten, Tag, Checker und Community lesen sie —
**vier Lesestellen taten es nicht**, und anders als in N-391b (dort stand D1 auf
der falschen *Ebene*) stand sie hier **gar nicht**. Für dieselbe Anlage
(Lage B: *Wärme gesamt* 3.000 kWh, Strom 1.000 kWh, Gas 10 ct, Netz 30 ct):

=======================================  ==================  ================
Sicht                                    vorher (Lage B)     Lage D (Bestand)
=======================================  ==================  ================
Jahresformel ``alternativkosten``        **−300,00 €**       33,33 €
Cockpit → Monat, Zeile „Ersparnis …"     **gar keine Zeile** 33,33 €
Aussichten ``wp_alternativ_ersparnis``   **0,00 €**          790,00 €
Cockpit → Monat, Nicht-DB-Quellen        **keine Wärme**     3.000 kWh
=======================================  ==================  ================

⭐ **Das sind drei Geldpfade.** An der Jahresformel hängen die Aussichten, der
ROI-Fortschritt und die Jahres-Ersparnis des HA-Exports; sie ist der SoT, den
`BERECHNUNGEN.md` namentlich führt. Die −300 € sind nicht „eine Null": Der
WP-Strom wurde weiter belastet, nur die Gas-Ersparnis daneben fiel weg. Genau
die Anwender, für die das Feld gebaut wurde, bekamen die schlechteste Zahl.

⚠ **Die Gegenrichtung ist der Grund, warum ``waerme_kwh`` NICHT einfach als
dritter Summand nachgetragen wurde** (Klausel d2): Wer Gesamtzähler **und**
Aufteilung pflegt, zählte dann 3000 + 2100 + 900 = 6000. D1 fällt deshalb **je
Gerät vor dem Summieren** — dieselbe Reihenfolge wie im DB-Zweig
(``monats_fakten`` löst je IMD-Zeile auf und addiert erst danach) und wie im
Tagespfad seit N-391b.

Schwesterdateien: ``test_n391_gesamtwaerme.py`` (der Erfassungsweg, von dem
dieser Bau die Lagen erbt), ``test_n391b_tag_je_geraet.py`` (dieselbe Regel auf
der Ebenen-Achse im Tagespfad), ``test_b5_ersparnis_symmetrie.py`` (Hub ·
Cockpit-Monat · Export für dieselbe Wärmepumpe).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.alternativkosten import (
    berechne_wp_alternativkosten_ersparnis,
)
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.tests.test_n391_gesamtwaerme import LAGE_B, LAGE_BEIDES, LAGE_D
from backend.tests.test_r2_je_funktion import JAHR, MONAT, _WP, _anlage, _geraet

#: Dieselbe Wärmepumpe wie in ``test_n391_gesamtwaerme``, nur mit dem
#: Alt-Energieträger, den die Geldpfade brauchen: Gas zu 10 ct, η 0,90.
_WP_GAS = dict(_WP, alter_energietraeger="gas", alter_preis_cent_kwh=10.0)

#: Die drei Bestandszahlen, gegen die Lage B antritt — vor dem Bau an Lage D
#: gemessen und seither unverändert (Klausel e).
BESTAND_JAHRESFORMEL_EURO = 33.33
BESTAND_MONATSZEILE_EURO = 33.33
BESTAND_AUSSICHTEN_EURO = 790.0
BESTAND_NICHT_DB_KWH = 3000.0


async def _mit_tarif(db, name: str) -> Anlage:
    a = await _anlage(db, name)
    db.add(Strompreis(
        anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2025, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    return a


async def _monatszeile(db, daten: dict, name: str):
    """Cockpit → Monat über die echte Route; die WP-Zeilen des T-Kontos."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    a = await _mit_tarif(db, name)
    await _geraet(db, a, "WP", dict(_WP_GAS), dict(daten))
    await db.commit()
    res = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    return [z for z in res.investitionen_financials if z.typ == "waermepumpe"]


def _jahresformel(daten: dict) -> float:
    """Die Funktion, die ``alternativkosten.py:210`` enthält — ein Monat."""
    class _Wp:
        id = 1
        parameter = _WP_GAS

    return berechne_wp_alternativkosten_ersparnis(
        [_Wp()], {(1, JAHR, MONAT): dict(daten)},
        {(JAHR, MONAT): 10.0}, {(JAHR, MONAT): 30.0}, 30.0,
    )


async def _aussichten(db, daten: dict, name: str) -> float:
    """Die thermische Gewichtung über die echte Route (``/aussichten/finanzen``)."""
    from backend.api.routes.aussichten import get_finanz_prognose

    a = await _mit_tarif(db, name)
    await _geraet(db, a, "WP", dict(_WP_GAS), dict(daten))
    db.add(Monatsdaten(
        anlage_id=a.id, jahr=JAHR, monat=MONAT, pv_erzeugung_kwh=800.0,
        netzbezug_kwh=300.0, einspeisung_kwh=400.0, gaspreis_cent_kwh=10.0,
    ))
    await db.commit()
    res = await get_finanz_prognose(a.id, monate=12, db=db)
    return res.wp_alternativ_ersparnis_euro


async def _nicht_db(
    db, monkeypatch, felder_je_geraet: list[dict], name: str,
    parameter_je_geraet: list[dict] | None = None,
):
    """Cockpit → Monat mit Werten **nur aus HA-Statistik**, kein IMD-Satz.

    Genau die Lage eines Anwenders, der *Wärme gesamt* per Sensor/MQTT/Connector
    führt und für diesen Monat noch keine gespeicherte Zeile hat. Muster aus
    ``test_bkw_pv_achse_laufender_monat``.

    ``parameter_je_geraet`` ist **additiv** (Vorgabe: ``_WP_GAS`` für jedes
    Gerät, wie bisher) und wird von ``test_n451b_k3_laufender_monat`` gebraucht:
    Die K3-Stufenregel hängt an ``getrennte_strommessung``, also muss dieselbe
    Werte-Lage mit **verschiedenen** Parametern fahrbar sein. Ein zweiter
    Nachbau dieser Bühne wäre die Drift-Klasse, gegen die dieses Paket baut.

    ⚠ **Bewusst ein FESTER Monat statt ``datetime.now()``**, anders als das
    Vorbild: Eine Probe, die die echte Uhr liest, wettet auf die Stunde ihres
    Laufs (N-167) — der Wächter ``test_konformitaet_echte_uhr_in_tests`` hält
    die Baseline abschmelzend und lässt keine neue Fundstelle zu. Für den
    geprüften Weg macht es keinen Unterschied: ``_collect_ha_statistics_data``
    wird **unabhängig** vom laufenden Monat gesammelt, nur der MQTT-Zweig ist
    daran gegated — und der ist hier ohnehin leer.
    """
    import backend.api.routes.aktueller_monat as am

    a = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(
        anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(
        anlage_id=a.id, jahr=JAHR, monat=MONAT,
        netzbezug_kwh=4.0, einspeisung_kwh=320.0,
    ))
    geraete = []
    for i, _ in enumerate(felder_je_geraet):
        inv = Investition(
            anlage_id=a.id, typ="waermepumpe", bezeichnung=f"WP{i + 1}",
            anschaffungsdatum=date(2024, 1, 1),
            anschaffungskosten_gesamt=12000.0,
            parameter=dict(
                parameter_je_geraet[i] if parameter_je_geraet else _WP_GAS
            ),
        )
        db.add(inv)
        geraete.append(inv)
    await db.commit()

    info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92,
                             abdeckung_von=None)
    werte = {
        f"inv_{inv.id}_{feld}": (wert, info)
        for inv, felder in zip(geraete, felder_je_geraet)
        for feld, wert in felder.items()
    }

    async def _leer(*args, **kwargs):
        return {}

    async def _ha_stats(anlage, j, m):
        return dict(werte)

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha_stats)

    return await am.get_aktueller_monat(
        anlage_id=a.id, jahr=JAHR, monat=MONAT, db=db,
    )


# ═══ a — Cockpit → Monat: die Zeile entsteht, und sie nennt dieselbe Zahl ═══

@pytest.mark.asyncio
async def test_a_monatszeile_gibt_es_in_lage_b_und_nennt_dieselbe_ersparnis(
    db, monkeypatch,
):
    """**Die Zeile fehlte ganz** — nicht „stand auf 0".

    ``waerme_total`` war die blosse Summe der beiden Achsen und damit 0; die
    Bedingung ``waerme_total > 0 and strom is not None`` fiel durch, und
    ``_baue_investition_financial`` gab für diese Wärmepumpe kein
    Ersparnis-Detail zurück. Der Komponenten-Hub nannte für dieselbe Anlage
    seit WK-14b eine Ersparnis (``dashboards.py:1253``) — zwei Sichten, zwei
    Auskünfte (S1).
    """
    b = await _monatszeile(db, LAGE_B, "N-391c Monat B")
    d = await _monatszeile(db, LAGE_D, "N-391c Monat D")

    assert len(b) == 1, "die Zeile entstand in Lage B gar nicht"
    assert b[0].ersparnis_label == "Ersparnis vs. Alternative"
    assert b[0].ersparnis_euro == pytest.approx(BESTAND_MONATSZEILE_EURO)
    # Gleichung statt zwei Pins: dieselbe Wärme, derselbe Strom, dieselbe Zahl.
    assert b[0].ersparnis_euro == pytest.approx(d[0].ersparnis_euro)
    # A6: der gedruckte Rechenweg nennt die Wärme, mit der gerechnet wurde.
    assert b[0].berechnung == d[0].berechnung


@pytest.mark.asyncio
async def test_a2_gesamtzaehler_neben_der_aufteilung_zaehlt_einmal(db):
    """Gegenprobe zu a: Lage BEIDES bleibt bei 3.000 kWh Wärme, nicht 6.000.

    Ohne sie wäre Klausel a auch mit ``waerme_kwh`` als drittem Summanden grün
    — und genau das ist die Bauform, die der Auftrag verbietet.
    """
    beides = await _monatszeile(db, LAGE_BEIDES, "N-391c Monat BEIDES")

    assert len(beides) == 1
    assert beides[0].ersparnis_euro == pytest.approx(BESTAND_MONATSZEILE_EURO)
    # N-555 (§11): deutsche Schreibweise über `core/zahlenformat.py`.
    assert "3.000,0 kWh" in (beides[0].berechnung or ""), beides[0].berechnung


# ═══ b — die Jahresformel: Aussichten, ROI, HA-Export-Jahresersparnis ═══════

def test_b_jahresformel_lage_b_gleich_lage_d_und_groesser_null():
    """**Der teuerste der vier Befunde.** −300,00 € statt 33,33 €.

    ``gas_kosten_altanlage(0, …)`` ist 0, der WP-Strom wird aber weiter voll
    zum Netztarif belastet (S1b) — die Ersparnis war nicht bloß weg, sie war
    negativ. Diese Summe trägt ``bisherige_wp_ersparnis`` in den Aussichten und
    im ROI-Fortschritt.
    """
    b = _jahresformel(LAGE_B)
    d = _jahresformel(LAGE_D)

    assert b > 0, "vor dem Bau: −300,00 € (nur Stromkosten, keine Gas-Ersparnis)"
    assert b == pytest.approx(d)
    assert b == pytest.approx(BESTAND_JAHRESFORMEL_EURO, abs=0.01)


def test_b2_jahresformel_zaehlt_die_waerme_nicht_doppelt():
    """Lage BEIDES bleibt bei 33,33 € — mit drei Summanden wären es 66,67 €."""
    assert _jahresformel(LAGE_BEIDES) == pytest.approx(
        BESTAND_JAHRESFORMEL_EURO, abs=0.01
    )


# ═══ c — die thermische Gewichtung der WP-Prognose ══════════════════════════

@pytest.mark.asyncio
async def test_c_aussichten_thermische_gewichtung(db):
    """``gesamt_wp_thermisch`` war 0 ⇒ der ganze WP-Zweig der Prognose entfiel.

    Die Größe wiegt in der Mischung von Alt-Preis und Wirkungsgrad **und**
    verteilt die Jahres-Ersparnis auf die Geräte (``wp_ersparnis_je_inv``). Mit
    Gewicht 0 bekam die Wärmepumpe, um die es geht, aus beidem nichts.
    """
    b = await _aussichten(db, LAGE_B, "N-391c Aussicht B")
    d = await _aussichten(db, LAGE_D, "N-391c Aussicht D")

    assert b == pytest.approx(d)
    assert b == pytest.approx(BESTAND_AUSSICHTEN_EURO, abs=0.01)


# ═══ d — der Nicht-DB-Pfad (MQTT · Connector · HA-Statistik) ════════════════

@pytest.mark.asyncio
async def test_d_nicht_db_pfad_kennt_waerme_gesamt(db, monkeypatch):
    """Wer *Wärme gesamt* per Sensor führt, sah im laufenden Monat **keine** Wärme.

    ``typ_aggregation`` hob für ``waermepumpe`` nur ``heizenergie_kwh`` und
    ``warmwasser_kwh`` in die Top-Level-Größe; ``waerme_kwh`` stand zwar in
    ``resolved`` (die Registry kennt es seit WK-14b), wurde aber nie
    aggregiert. Gemessen: ``wp_waerme_kwh`` **None**.
    """
    res = await _nicht_db(
        db, monkeypatch,
        [{"waerme_kwh": 3000.0, "stromverbrauch_kwh": 1000.0}],
        "N-391c NichtDB B",
    )

    assert res.wp_waerme_kwh == pytest.approx(BESTAND_NICHT_DB_KWH)
    assert res.wp_strom_kwh == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_d2_nicht_db_pfad_zaehlt_die_waerme_nicht_doppelt(db, monkeypatch):
    """**Die Gegenprobe, die die Bauform erzwingt: 3.000, nicht 6.000.**

    Ein dritter Summand in ``typ_aggregation`` hätte Klausel d grün gemacht und
    diese hier rot. D1 muss **je Gerät vor** dem Summieren fallen.
    """
    res = await _nicht_db(
        db, monkeypatch,
        [{"waerme_kwh": 3000.0, "heizenergie_kwh": 2100.0,
          "warmwasser_kwh": 900.0, "stromverbrauch_kwh": 1000.0}],
        "N-391c NichtDB BEIDES",
    )

    assert res.wp_waerme_kwh == pytest.approx(3000.0), "3000+2100+900 wären 6000"


@pytest.mark.asyncio
async def test_d3_nicht_db_pfad_loest_je_geraet_auf(db, monkeypatch):
    """Zwei Wärmepumpen, die verschieden zählen — 30 + (20 + 5) = **55**.

    Dieselbe Lehre wie N-391b im Tagespfad: ``waerme_kwh`` ist ein Feld **am
    Gerät**. Fiele D1 auf den Anlagensummen (``waerme_gesamt_kwh(30, 20, 5)``),
    verschwände die Aufteilung von WP2 still hinter dem Gesamtwert von WP1 und
    die Sicht nennte **30** — eine Teilsumme ohne Hinweis (P4).
    """
    res = await _nicht_db(
        db, monkeypatch,
        [{"waerme_kwh": 30.0, "stromverbrauch_kwh": 10.0},
         {"heizenergie_kwh": 20.0, "warmwasser_kwh": 5.0,
          "stromverbrauch_kwh": 10.0}],
        "N-391c NichtDB je Geraet",
    )

    assert res.wp_waerme_kwh == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_d4_eine_gemessene_null_verdraengt_keine_aufteilung(db, monkeypatch):
    """``waerme_kwh`` = 0,0 ist kein Gesamtwert — die Bedingung von D1 ist ``if
    waerme_kwh``, nicht ``is not None``.

    Ein Gesamtzähler, der in diesem Monat 0 gemeldet hat, darf eine gepflegte
    Aufteilung nicht verdrängen. Die Klausel hält die Herkunfts-Marke mit fest:
    Die Zahl kommt aus der Quelle, die D1 gewonnen hat, nicht aus der 0.
    """
    res = await _nicht_db(
        db, monkeypatch,
        [{"waerme_kwh": 0.0, "heizenergie_kwh": 2100.0,
          "warmwasser_kwh": 900.0, "stromverbrauch_kwh": 1000.0}],
        "N-391c NichtDB Null",
    )

    assert res.wp_waerme_kwh == pytest.approx(3000.0)


# ═══ e — Bestandsprobe: Lage D bewegt sich in keinem der vier Pfade ═════════

@pytest.mark.asyncio
async def test_e_bestand_lage_d_bitgleich(db, monkeypatch):
    """Eine Zahl je Pfad, vor dem Bau erhoben — der Bestand ist unberührt.

    Lage D ist der Anwender, der seinen Wärmemengenzähler **nur auf dem
    Heizkreis** hat und ihn wie eh unter *Heizwärme* führt. Für ihn ändert
    dieser Bau nichts, und das ist die Zusage aus N-391 („wer die Summe weiter
    unter Heizwärme führt, sieht exakt dieselben Zahlen").
    """
    assert _jahresformel(LAGE_D) == pytest.approx(
        BESTAND_JAHRESFORMEL_EURO, abs=0.01
    )
    zeilen = await _monatszeile(db, LAGE_D, "N-391c Bestand Monat")
    assert zeilen[0].ersparnis_euro == pytest.approx(BESTAND_MONATSZEILE_EURO)
    assert await _aussichten(db, LAGE_D, "N-391c Bestand Aussicht") == (
        pytest.approx(BESTAND_AUSSICHTEN_EURO, abs=0.01)
    )
    res = await _nicht_db(
        db, monkeypatch,
        [{"heizenergie_kwh": 3000.0, "stromverbrauch_kwh": 1000.0}],
        "N-391c Bestand NichtDB",
    )
    assert res.wp_waerme_kwh == pytest.approx(BESTAND_NICHT_DB_KWH)
