"""F-16 — jede Sicht nennt **denselben** PV-Anteil der Heimladung.

**Warum dieser Test neben `test_emob_readsite_symmetrie.py` steht, und nicht
darin.** Jener Test prüft die Heimladungs-**Summe** über die Read-Sites, und
genau deshalb blieb er grün, als `a7a50abc` die Ableitung des PV-Anteils
einführte: die Ableitung ändert die Summe nicht, sondern nur ihre **Aufteilung**
zwischen PV und Netz. Ein Symmetrie-Test kann die falsche Größe prüfen und dabei
grün bleiben, während die Drift danebensteht — nach der Ableitung zeigte der
Komponenten-Hub weiterhin 0 % PV, während Cockpit und Auswertungen für dieselbe
Ladung einen abgeleiteten Anteil nannten. Dieser Test schließt die Lücke: er
vergleicht die **Aufteilung**.

Alle Fixtures teilen dieselbe Ausgangslage — die, in der die Ableitung
überhaupt greift:

    Heimladung ist erfasst, ein PV-Anteil ist es **nicht**, und die Tagesebene
    trägt eine Ableitung.

Das ist ausdrücklich der Fall, den die Fixture von `test_emob_readsite_
symmetrie.py` nicht abbildet: sie pflegt `ladung_pv_kwh`, und ein gepflegter
Wert schaltet die Ableitung ab. Eine Fixture, die den zu prüfenden Zustand nicht
herstellt, ist die Klasse, an der schon #356 gescheitert ist.

**Die Gegenrichtung gehört dazu** (zweiter Block): wo ein PV-Anteil gepflegt ist,
darf sich **nichts** bewegen — auch nicht bei einer gepflegten 0.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung

JAHR, MONAT = 2026, 4
ANSCHAFFUNG = date(2024, 1, 1)

#: Die Tagesebene sagt: von 400 kWh Ladung kamen 300 aus der Sonne ⇒ 75 %.
#: Bewusst eine ANDERE Ladungsmenge als die Monatszeile (500 kWh): abgeleitet
#: wird der Anteil, nicht die Kilowattstunde. Wer die kWh übernähme, käme auf
#: 300/500 = 60 % — die Probe unterscheidet die beiden Bauformen.
TAGES_PV, TAGES_NETZ = 300.0, 100.0
ERWARTETER_ANTEIL = 75.0
HEIMLADUNG_KWH = 500.0


async def _seed(
    db,
    *,
    gepflegter_pv_anteil: float | None = None,
    mit_wallbox: bool = True,
    gepflegter_netz_anteil: float | None = None,
) -> int:
    """evcc-loses Setup: der Zähler zählt kWh, den PV-Anteil kennt er nicht.

    ``gepflegter_pv_anteil`` schreibt einen erfassten Wert in die Lade-Zeile —
    der Torwächter muss die Ableitung dann abschalten.

    ⚠ ``mit_wallbox=False`` ist **nicht** dieselbe Probe mit weniger Geräten.
    Liegt eine Wallbox vor, ist sie die kanonische Quelle, und die E-Auto-Sichten
    ziehen ihre PV-/Netz-Werte km-anteilig aus dem **Wallbox-Pool** — der Pfad,
    der die Zeile des Fahrzeugs selbst liest, läuft dann gar nicht. Genau das hat
    hier einen Sprengsatz stumm bleiben lassen: sabotiert war ein Pfad, den die
    Fixture nicht betrat. Der Steckerlader (Ladung am Fahrzeug, keine Wallbox)
    ist die Konstellation, die ihn betritt.
    """
    anlage = Anlage(anlagenname="F16", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    ea = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
        anschaffungsdatum=ANSCHAFFUNG, aktiv=True,
        parameter={"verbrauch_kwh_100km": 20, "vergleich_verbrauch_l_100km": 7.5},
    )
    db.add(ea)

    lade_daten: dict = {"ladung_kwh": HEIMLADUNG_KWH, "ladevorgaenge": 20}
    if gepflegter_pv_anteil is not None:
        lade_daten["ladung_pv_kwh"] = gepflegter_pv_anteil
    if gepflegter_netz_anteil is not None:
        lade_daten["ladung_netz_kwh"] = gepflegter_netz_anteil

    if mit_wallbox:
        wb = Investition(
            anlage_id=anlage.id, typ="wallbox", bezeichnung="SMA eCharger",
            anschaffungsdatum=ANSCHAFFUNG, aktiv=True,
        )
        db.add(wb)
        await db.flush()
        db.add(InvestitionMonatsdaten(
            investition_id=wb.id, jahr=JAHR, monat=MONAT, verbrauch_daten=lade_daten,
        ))
        ea_daten = {"km_gefahren": 2000}
    else:
        await db.flush()
        ea_daten = {**lade_daten, "km_gefahren": 2000}

    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=JAHR, monat=MONAT, verbrauch_daten=ea_daten,
    ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=date(JAHR, MONAT, 15),
        emob_ladung_pv_abgeleitet_kwh=TAGES_PV,
        emob_ladung_netz_abgeleitet_kwh=TAGES_NETZ,
    ))
    await db.commit()
    return anlage.id


async def _anteile_je_sicht(db, anlage_id: int) -> dict[str, float]:
    """Der PV-Anteil der Heimladung in Prozent, je Read-Site einmal erhoben.

    Jede Zeile ist eine Sicht, die den Anteil an eine Oberfläche oder an Home
    Assistant ausliefert. Es wird **gesammelt statt assertet** — eine Schleife
    mit `assert` im Rumpf reißt an der ersten Abweichung, und die übrigen
    Sichten blieben unbelegt (Lehre aus #331).
    """
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import (
        _load_emob_pool_ctx,
        calculate_investition_sensors,
    )
    from backend.api.routes.investitionen import (
        get_eauto_dashboard,
        get_wallbox_dashboard,
    )
    from backend.models import Investition
    from sqlalchemy import select

    anteile: dict[str, float] = {}

    def _prozent(pv: float | None, ladung: float | None) -> float | None:
        if not ladung:
            return None
        return round((pv or 0.0) / ladung * 100, 1)

    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, db=db)
    anteile["cockpit_monat"] = _prozent(am.emob_ladung_pv_kwh, am.emob_ladung_kwh)

    # Auswertungen → Komponenten liefert den Anteil je Monat fertig gerundet —
    # dieselbe Zahl, die die KPI-Kachel zeigt.
    komp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=JAHR, db=db)
    monat = [m for m in komp.monatswerte if (m.jahr, m.monat) == (JAHR, MONAT)]
    if monat:
        anteile["auswertungen_komponenten"] = monat[0].emob_pv_anteil_prozent or 0.0

    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=JAHR, db=db)
    anteile["cockpit_jahr"] = (
        round(ueb.emob_pv_anteil_prozent, 1)
        if ueb.emob_pv_anteil_prozent is not None
        else 0.0
    )

    wb_dash = await get_wallbox_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, db=db
    )
    if wb_dash:
        anteile["hub_wallbox"] = round(
            wb_dash[0].zusammenfassung["pv_anteil_prozent"], 1
        )

    ea_dash = await get_eauto_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, db=db
    )
    anteile["hub_eauto"] = round(
        ea_dash[0].zusammenfassung["pv_anteil_heim_prozent"], 1
    )

    # HA-Export: derselbe Weg wie die Route `/ha/export/sensors` — Pool-Kontext einmal,
    # dann je Investition. Der Sensor `e_auto_pv_anteil_prozent` ist der Wert,
    # der in der HA-Langzeitstatistik landet.
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all()
    emob_ctx = await _load_emob_pool_ctx(db, invs)
    for inv in invs:
        for sv in await calculate_investition_sensors(db, inv, None, emob_ctx):
            if sv.definition.key == "e_auto_pv_anteil_prozent" and sv.value is not None:
                anteile["ha_sensor"] = round(float(sv.value), 1)

    return anteile


# ═══════════════════════════════════════════════════════════════════════
# Der Fund: dieselbe Größe, überall dieselbe Zahl
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("mit_wallbox", [True, False], ids=["wallbox", "steckerlader"])
async def test_alle_sichten_nennen_denselben_abgeleiteten_pv_anteil(db, mit_wallbox):
    """Ohne gepflegten PV-Anteil zeigen **alle** Sichten den abgeleiteten.

    Vor F-16 sahen ihn vier von achtzehn Lesestellen: die Ableitung saß
    oberhalb des Heimladungs-Pools, und wer die Rohzeilen selbst poolte oder die
    `InvestitionMonatsdaten` direkt las, bekam den ungeteilten Wert (0 % PV).

    Beide Konstellationen, weil sie **verschiedene Codepfade** betreten (s.
    ``_seed``): mit Wallbox laufen die E-Auto-Sichten über den km-anteiligen
    Pool, ohne Wallbox über die Zeile des Fahrzeugs selbst.
    """
    anlage_id = await _seed(db, mit_wallbox=mit_wallbox)
    anteile = await _anteile_je_sicht(db, anlage_id)

    assert anteile, "keine einzige Sicht hat geantwortet — die Probe misst nichts"
    abweichungen = {
        sicht: wert
        for sicht, wert in anteile.items()
        if wert is None or abs(wert - ERWARTETER_ANTEIL) > 0.2
    }
    assert not abweichungen, (
        f"erwartet {ERWARTETER_ANTEIL} % in jeder Sicht, abweichend: {abweichungen} "
        f"(alle: {anteile})"
    )


@pytest.mark.asyncio
async def test_abgeleitet_wird_der_anteil_nicht_die_kilowattstunde(db):
    """Die Trias bleibt geschlossen, auch wenn die Tagesebene weniger kennt.

    Die Tagesspur trägt 400 kWh, die Monatszeile 500. Wer die abgeleiteten
    **kWh** übernähme, käme auf 300/500 = 60 % und im umgekehrten Fall auf über
    100 % (#262). Übernommen wird der **Anteil**: 75 % von 500 = 375 kWh.
    """
    from backend.services.monats_fakten import lade_monats_fakten

    anlage_id = await _seed(db)
    fakten = await lade_monats_fakten(
        db, anlage_id, von=(JAHR, MONAT), bis=(JAHR, MONAT)
    )
    emob = fakten[0].emob

    assert emob.ladung_kwh == pytest.approx(HEIMLADUNG_KWH)
    assert emob.ladung_pv_kwh == pytest.approx(375.0), "75 % von 500, nicht 300"
    assert emob.ladung_pv_kwh + emob.ladung_netz_kwh == pytest.approx(emob.ladung_kwh)
    assert emob.ladung_anteil_abgeleitet is True, "die Schätzung muss sich zu erkennen geben"


@pytest.mark.asyncio
async def test_community_payload_bleibt_gemessen(db):
    """Die eine Sicht, die den abgeleiteten Anteil **nicht** sehen darf.

    Der Community-Server hat die Rohdaten nie gesehen und rechnet nichts nach —
    eine Schätzung wäre dort in einem Benchmark nicht mehr als solche erkennbar,
    und der Anlagen-Hash bewegte sich ohne neue Messung.
    """
    from backend.models import Monatsdaten
    from backend.services.community_service import prepare_community_data

    anlage_id = await _seed(db)
    # Der Payload nimmt nur Monate mit Zählerzeile UND PV auf (`_monatswert`) —
    # ohne diese beiden zusätzlichen Zeilen prüfte die Probe eine leere Liste.
    pv = Investition(
        anlage_id=anlage_id, typ="pv-module", bezeichnung="String Süd",
        anschaffungsdatum=ANSCHAFFUNG, aktiv=True, leistung_kwp=10.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"pv_erzeugung_kwh": 900.0},
    ))
    db.add(Monatsdaten(
        anlage_id=anlage_id, jahr=JAHR, monat=MONAT,
        einspeisung_kwh=400.0, netzbezug_kwh=200.0,
    ))
    await db.commit()

    daten = await prepare_community_data(db, anlage_id)
    treffer = [
        w for w in (daten or {}).get("monatswerte", [])
        if (w["jahr"], w["monat"]) == (JAHR, MONAT)
    ]

    assert treffer, "kein Monatswert im Payload — die Probe misst nichts"
    assert "wallbox_ladung_pv_kwh" not in treffer[0], (
        "der Payload trägt einen geschätzten PV-Anteil an einen fremden Server"
    )
    assert treffer[0]["wallbox_ladung_kwh"] == pytest.approx(HEIMLADUNG_KWH), (
        "die gemessene Ladungsmenge selbst gehört weiterhin hinein"
    )


# ═══════════════════════════════════════════════════════════════════════
# N-188: die Prognose-Achse rät den Anteil nicht mehr
# ═══════════════════════════════════════════════════════════════════════


async def _roi_stromkosten(db, anlage_id: int) -> float:
    """Die Netz-Stromkosten des E-Autos aus der ROI-Prognose.

    Die eine Größe der ROI-Zeile, die direkt am PV-Anteil hängt: je mehr Sonne,
    desto weniger bezahlter Netzstrom.
    """
    from backend.api.routes.investitionen.crud import get_roi_dashboard

    roi = await get_roi_dashboard(
        anlage_id=anlage_id,
        strompreis_cent=30.0,
        einspeiseverguetung_cent=8.0,
        benzinpreis_euro=1.75,
        jahr=None,
        db=db,
    )
    eauto = [b for b in roi.berechnungen if b.investition_typ == "e-auto"]
    assert eauto, "kein E-Auto in der ROI-Antwort — die Probe misst nichts"
    return eauto[0].detail_berechnung["strom_kosten_euro"]


@pytest.mark.asyncio
async def test_roi_prognose_nimmt_den_ist_anteil_statt_des_defaults(db):
    """Ohne gepflegten ``pv_ladeanteil_prozent`` rechnet die Prognose mit dem IST.

    Vorher stand dieselbe Anlage auf **60 %** in der Prognose (Hand-Default) und
    dem gemessenen Anteil im IST — zwei Zahlen für dieselbe Größe, nur auf zwei
    Zeitachsen (N-188). Der Beweis läuft über drei Läufe statt über eine
    nachgerechnete Konstante: **ungepflegt ≡ gepflegt 75 %** und
    **ungepflegt ≢ gepflegt 60 %**. Ohne den zweiten Teil wäre der erste auch
    dann grün, wenn gar nichts gelesen würde.
    """
    ungepflegt = await _roi_stromkosten(db, await _seed(db))

    async def _mit_parameter(anteil: float) -> float:
        from sqlalchemy import select

        from backend.models import Investition

        anlage_id = await _seed(db)
        ea = (await db.execute(
            select(Investition).where(
                Investition.anlage_id == anlage_id, Investition.typ == "e-auto"
            )
        )).scalar_one()
        ea.parameter = {**(ea.parameter or {}), "pv_ladeanteil_prozent": anteil}
        await db.commit()
        return await _roi_stromkosten(db, anlage_id)

    assert ungepflegt == pytest.approx(await _mit_parameter(ERWARTETER_ANTEIL), abs=0.01), (
        "die Prognose nimmt den IST-Anteil nicht"
    )
    assert ungepflegt != pytest.approx(await _mit_parameter(60.0), abs=0.01), (
        "die Probe kann den alten Default gar nicht unterscheiden — sie beweist nichts"
    )


@pytest.mark.asyncio
async def test_aussichten_historie_rechnet_mit_dem_abgeleiteten_anteil(db):
    """Die zweite Prognose-Quelle (`aussichten.py`) zieht denselben Anteil.

    Sie leitet ihre Quote aus der rohen Historie ab (``netz / (pv + netz)``) und
    ist damit die unauffälligere der beiden: sie **sieht aus** wie eine
    Ableitung, nahm aber die ungeteilte Rohaufteilung als Basis — also 100 %
    Netz.

    Der Beweis läuft über **Gleichheit mit dem gepflegten Fall**, nicht über
    eine Richtung: abgeleitete 375/125 müssen dasselbe ergeben wie von Hand
    gepflegte 375/125. Die Richtung allein wäre hier trügerisch, weil dieselbe
    Route den Netz-Anteil roh liest (``daten.get("ladung_netz_kwh")`` statt über
    ``get_emob_pv_netz_kwh``) — eine Zeile ohne den Schlüssel sieht dort netz=0
    statt „ungeteilt", und ein Richtungsvergleich gegen sie belegte eher jenen
    Rohkey-Fund als diesen Bau. Deshalb zusätzlich die dritte Messung unten,
    die den ungeteilten Fall **explizit** pflegt.
    """
    from backend.api.routes.aussichten import get_finanz_prognose

    async def _ertraege(**seed) -> float:
        # ⚠ **Steckerlader-Zuschnitt, und das ist keine Vereinfachung.** Diese
        # Schleife liest die Zeile des **Fahrzeugs**. Im evcc-Zuschnitt trägt
        # sie nur km — Netzladung 0, PV-Anteil ohne Wirkung, alle drei Läufe
        # wären gleich und die Probe bewiese nichts.
        antwort = await get_finanz_prognose(
            anlage_id=await _seed(db, mit_wallbox=False, **seed), monate=12, db=db
        )
        return antwort.bisherige_ertraege_euro

    abgeleitet = await _ertraege()
    gepflegt_gleich = await _ertraege(
        gepflegter_pv_anteil=375.0, gepflegter_netz_anteil=125.0
    )
    ungeteilt = await _ertraege(
        gepflegter_pv_anteil=0.0, gepflegter_netz_anteil=HEIMLADUNG_KWH
    )

    assert abgeleitet == pytest.approx(gepflegt_gleich, abs=0.01), (
        "die Aussichten sehen den abgeleiteten Anteil nicht "
        f"({abgeleitet} vs. gepflegt {gepflegt_gleich})"
    )
    assert abgeleitet > ungeteilt, (
        "die Probe kann ungeteilte von aufgeteilter Ladung nicht unterscheiden "
        f"({abgeleitet} vs. ungeteilt {ungeteilt}) — sie beweist nichts"
    )


# ═══════════════════════════════════════════════════════════════════════
# Die Gegenrichtung: ein gepflegter Wert gewinnt, auch die 0
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("gepflegt,erwartet", [
    (200.0, 40.0),   # 200 von 500 kWh — die Messung, nicht die 75 % der Ableitung
    (0.0, 0.0),      # „diesen Monat nur nachts geladen" ist eine Aussage (F-15)
])
async def test_gepflegter_pv_anteil_schlaegt_die_ableitung_in_allen_sichten(
    db, gepflegt, erwartet
):
    """Wo gemessen wurde, wird nicht geschätzt — und zwar in jeder Sicht gleich.

    Die gepflegte **0** ist der schärfere der beiden Fälle: sie ist die
    F-15-Klasse eine Ebene weiter. Ein Torwächter, der auf ``> 0`` statt auf
    ``is not None`` prüft, überschriebe sie mit einer Schätzung und wäre in
    dieser Probe an der 0-Zeile sichtbar.
    """
    anlage_id = await _seed(db, gepflegter_pv_anteil=gepflegt)
    anteile = await _anteile_je_sicht(db, anlage_id)

    assert anteile, "keine einzige Sicht hat geantwortet — die Probe misst nichts"
    abweichungen = {
        sicht: wert
        for sicht, wert in anteile.items()
        if wert is None or abs(wert - erwartet) > 0.2
    }
    assert not abweichungen, (
        f"gepflegt {gepflegt} kWh ⇒ erwartet {erwartet} %, abweichend: "
        f"{abweichungen} (alle: {anteile})"
    )
