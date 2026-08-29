"""Der Sizing-Endpoint liefert, was die Formel rechnet — und sagt, worauf sie steht.

Die Layer-Tests (`test_speicher_sizing.py`) prüfen Simulation, Kalibrierung und
Bewertung. Hier geht es um die Strecke davor und danach: Stunden aus
`TagesEnergieProfil`, vollständige Tage, Basis-Auswahl (gemessen ⟷ gepflegt),
Tarif — und darum, dass eine dünne Datenlage als solche ankommt statt als Kurve.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.api.routes.investitionen import get_speicher_sizing
from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.speicher_sizing_service import MIN_TAGE_FUER_AUSSAGE


async def _seed(db, *, mit_speicher: bool = True, mit_tarif: bool = True) -> int:
    anlage = Anlage(anlagenname="Sizing-Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    if mit_speicher:
        db.add(Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher 10 kWh",
            anschaffungsdatum=date(2024, 1, 1),
            parameter={
                "kapazitaet_kwh": 10, "nutzbare_kapazitaet_kwh": 8.0,
                "wirkungsgrad_prozent": 90,
            },
        ))
    if mit_tarif:
        db.add(Strompreis(
            anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
            netzbezug_arbeitspreis_cent_kwh=35.0,
            einspeiseverguetung_cent_kwh=8.0,
        ))
    return anlage.id


def _tag(db, anlage_id: int, tag: date, *, pv_mittag: float = 6.0, verbrauch: float = 0.7):
    """Ein vollständiger Tag: PV am Mittag, Grundlast rund um die Uhr."""
    for h in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=h,
            pv_kw=pv_mittag if 10 <= h < 16 else 0.0,
            verbrauch_kw=verbrauch,
        ))


async def _sizing(db, anlage_id: int, **kw):
    """Ruft die Route so, wie FastAPI sie rufen würde — mit ALLEN Query-Parametern.

    ⚠ Warum es diesen Helfer gibt (2026-08-29, beim Bau von N-274 gemessen):
    Ein weggelassener Query-Parameter traegt beim **direkten** Aufruf nicht
    `None`, sondern das `Query`-**Objekt** als Wert — `Query(None) is None` ist
    `False`. Wer `richtpreis_eur_je_kwh` hier vergisst, schickt dem Service also
    ein `Query`-Objekt statt einer Zahl, und die Multiplikation in der Bewertung
    wirft. Die neun Bestandsaufrufe umgingen das nur, weil sie `von`/`bis`
    ausdruecklich uebergaben; der zehnte Test haette es nicht gewusst.

    Deshalb steht die Vollstaendigkeit **hier an einer Stelle** statt in jedem
    Aufruf. Ein neuer Query-Parameter der Route gehoert in diese Vorgabeliste.
    """
    vorgabe = {"von": None, "bis": None, "richtpreis_eur_je_kwh": None}
    return await get_speicher_sizing(anlage_id, **{**vorgabe, **kw}, db=db)


async def test_kurve_deckt_50_bis_200_prozent_ab_und_ankert_auf_heute(db):
    anlage_id = await _seed(db)
    for i in range(30):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    faktoren = [p.faktor for p in antwort.kurve]
    assert faktoren[0] == 0.5 and faktoren[-1] == 2.0
    heute = next(p for p in antwort.kurve if p.faktor == 1.0)
    assert heute.delta_netzbezug_kwh == 0.0
    assert heute.kapazitaet_kwh == 8.0, "ohne Kalibrierung die gepflegte NETTO-Kapazität"


async def test_ohne_kalibrierbare_soc_bewegung_wird_gepflegt_gerechnet_und_gesagt(db):
    """Die Tage tragen keinen SoC — die Basis ist dann gepflegt, nicht gemessen."""
    anlage_id = await _seed(db)
    for i in range(30):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.basis_kalibriert is False
    assert antwort.basis_kapazitaet_kwh == 8.0
    assert antwort.basis_roundtrip_prozent == 90.0
    assert antwort.kalibrierung_paare_entladen is None


async def test_nutzen_ist_der_spread_nicht_der_bezugspreis(db):
    """Der gesparte Netzbezug allein wäre zu hoch — die Einspeisung geht ab."""
    anlage_id = await _seed(db)
    for i in range(60):
        _tag(db, anlage_id, date(2026, 5, 1) + timedelta(days=i))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    gross = next(p for p in antwort.kurve if p.faktor == 2.0)
    assert gross.delta_netzbezug_kwh < 0 and gross.delta_einspeisung_kwh < 0
    nur_bezug = -gross.delta_netzbezug_kwh * 0.35 * 365 / antwort.tage_simuliert
    assert gross.nutzen_euro_jahr is not None
    assert gross.nutzen_euro_jahr < nur_bezug, (
        "wer nur den Bezug bewertet, verkauft die entgangene Einspeisung als Gewinn"
    )


async def test_angebrochene_tage_gehen_nicht_in_die_simulation(db):
    """23 Stunden sind kein Tag — der Speicherstand liefe sonst über die Lücke."""
    anlage_id = await _seed(db)
    _tag(db, anlage_id, date(2026, 6, 1))
    for h in range(23):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=date(2026, 6, 2), stunde=h,
            pv_kw=0.0, verbrauch_kw=0.7,
        ))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.tage_mit_daten == 2
    assert antwort.tage_simuliert == 1


async def test_kurze_historie_wird_als_solche_gemeldet(db):
    """Das Konzept verlangt 6–12 Monate — darunter sagt die Antwort es."""
    anlage_id = await _seed(db)
    for i in range(30):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.historie_reicht is False
    assert antwort.min_tage_fuer_aussage == MIN_TAGE_FUER_AUSSAGE
    assert antwort.kurve, "der Hinweis ersetzt die Kurve nicht, er begleitet sie"


async def test_ohne_speicher_und_ohne_kalibrierung_bleibt_die_kurve_leer(db):
    """Ohne jede Basis gibt es kein „50 % … 200 %" — und keine erfundene Kurve."""
    anlage_id = await _seed(db, mit_speicher=False)
    for i in range(5):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.kurve == []
    assert antwort.anzahl_speicher == 0
    assert antwort.basis_kapazitaet_kwh == 0.0
    assert antwort.tage_mit_daten == 5, "die Daten sind da, nur die Bezugsgröße fehlt"


async def test_anlage_ohne_stundendaten_antwortet_leer_statt_zu_werfen(db):
    anlage_id = await _seed(db)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.kurve == []
    assert antwort.tage_mit_daten == 0
    assert antwort.von is None


async def test_der_verwendete_tarif_wird_ausgewiesen(db):
    """Die Kurve rechnet mit dem HEUTIGEN Tarif — dann muss sie ihn auch nennen."""
    anlage_id = await _seed(db)
    _tag(db, anlage_id, date(2026, 6, 1))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.bezug_preis_cent == 35.0
    assert antwort.einspeise_verg_cent == 8.0
    assert antwort.richtpreis_eur_je_kwh == pytest.approx(500.0)


async def test_zeitraum_grenzen_werden_beachtet(db):
    anlage_id = await _seed(db)
    _tag(db, anlage_id, date(2026, 6, 10))
    _tag(db, anlage_id, date(2026, 7, 10))
    await db.commit()

    nur_juni = await _sizing(db, anlage_id, von=date(2026, 6, 1), bis=date(2026, 6, 30))

    assert nur_juni.von == date(2026, 6, 10)
    assert nur_juni.bis == date(2026, 6, 10)
    assert nur_juni.tage_simuliert == 1


# ── N-274 (MeinerB, Discussion #380) ────────────────────────────────────────
# An der Amortisation haengt ein URTEIL, nicht nur eine Zahl: unter 15 Jahren
# „amortisiert in gut X Jahren", darueber „das rechnet sich nicht". Bis zum
# 2026-08-29 rechnete sie ausnahmslos mit 500 €/kWh, und es gab keinen Weg,
# eine eigene Zahl einzusetzen. Bernds Fall: 1.000 € statt 1.600 € fuer
# 3,2 kWh (312 €/kWh) ⇒ angezeigte Amortisation 1,6-fach zu lang.


async def test_ohne_angabe_gilt_weiter_der_richtwert(db):
    """Die Vorgabe darf sich durch den neuen Parameter NICHT verschieben.

    Der Bestandsfall ist der wichtigere von beiden: wer nichts eingibt, muss
    exakt dieselbe Zahl sehen wie vorher.
    """
    anlage_id = await _seed(db)
    _tag(db, anlage_id, date(2026, 6, 1))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.richtpreis_eur_je_kwh == pytest.approx(500.0)


async def test_eigener_preis_erreicht_die_mehrkosten_und_die_amortisation(db):
    """Der eigene Preis wirkt — und zwar proportional auf BEIDE abgeleiteten Groessen.

    Gegen den Richtwert gemessen, nicht gegen eine erwartete Konstante: die
    Bewertung ist `mehrkosten = mehr_kwh × preis` und
    `amortisation = mehrkosten ÷ nutzen_jahr`. Halbiert man den Preis, muessen
    beide Groessen halbiert herauskommen — an denselben Daten, im selben Lauf.
    """
    anlage_id = await _seed(db)
    for i in range(30):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    voll = await _sizing(db, anlage_id, richtpreis_eur_je_kwh=500.0)
    halb = await _sizing(db, anlage_id, richtpreis_eur_je_kwh=250.0)

    assert halb.richtpreis_eur_je_kwh == pytest.approx(250.0)

    # Nur Punkte oberhalb der heutigen Kapazitaet tragen Mehrkosten.
    paare = [
        (v, h) for v, h in zip(voll.kurve, halb.kurve)
        if v.mehrkosten_euro is not None and v.mehrkosten_euro > 0
    ]
    assert paare, "kein Punkt mit Mehrkosten — die Probe wuerde nichts messen"

    for v, h in paare:
        assert h.mehrkosten_euro == pytest.approx(v.mehrkosten_euro / 2, rel=0.02)
        if v.amortisation_jahre is not None:
            assert h.amortisation_jahre is not None
            assert h.amortisation_jahre == pytest.approx(
                v.amortisation_jahre / 2, rel=0.02
            )


async def test_gegenprobe_der_preis_kommt_wirklich_aus_dem_parameter(db):
    """⚑ GEGENPROBE — sie ist der eigentliche Waechter dieses Fundes.

    Ein Test, der nur `richtpreis_eur_je_kwh == 312.0` prueft, bliebe gruen,
    wenn die Route den Wert zwar AUSWEIST, aber weiter mit 500 rechnet — genau
    die Bauform, an der der erste W1-Waechter am 2026-08-29 gescheitert ist
    („ein Pruefer, der bei zurueckgebautem Fix gruen bleibt, hat nichts
    gemessen"). Deshalb wird hier die GERECHNETE Groesse gegen den Richtwert
    gehalten: mit 312 statt 500 muessen die Mehrkosten SINKEN.
    """
    anlage_id = await _seed(db)
    for i in range(30):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    richtwert = await _sizing(db, anlage_id)                                # 500
    bernd = await _sizing(db, anlage_id, richtpreis_eur_je_kwh=312.0)

    teuer = [p.mehrkosten_euro for p in richtwert.kurve
             if p.mehrkosten_euro is not None and p.mehrkosten_euro > 0]
    billig = [p.mehrkosten_euro for p in bernd.kurve
              if p.mehrkosten_euro is not None and p.mehrkosten_euro > 0]
    assert teuer and len(teuer) == len(billig)
    assert all(b < t for b, t in zip(billig, teuer)), (
        "die Mehrkosten haben sich nicht bewegt — der Parameter wird ausgewiesen, "
        "aber nicht gerechnet"
    )


async def test_der_eigene_preis_wird_nicht_gespeichert(db):
    """„Fluechtiger Wert neben dem Slider" (Entscheid Gernot 2026-08-18).

    Der naechste Abruf ohne Angabe muss wieder den Richtwert liefern. Waere der
    Preis irgendwo abgelegt worden, stuende hier 312.
    """
    anlage_id = await _seed(db)
    _tag(db, anlage_id, date(2026, 6, 1))
    await db.commit()

    await _sizing(db, anlage_id, richtpreis_eur_je_kwh=312.0)
    danach = await _sizing(db, anlage_id)

    assert danach.richtpreis_eur_je_kwh == pytest.approx(500.0)
