"""Ein Verbrenner-Anteil, fuenf Sichten — #331 gegen die Drift-Klasse.

Die E-Auto-Ersparnis wird an **fuenf** Stellen gebildet, und nur zwei davon
rechnen sie nicht selbst, sondern ueber `services/eauto_wirtschaftlichkeit.py`:

===================================  ==========================================
Sicht                                Weg
===================================  ==========================================
Cockpit → Übersicht                  `berechne_eauto_ersparnis_periode` je Auto
Komponenten-Hub (E-Auto-Dashboard)   `berechne_eauto_ersparnis_periode`
HA-Export (Anlagen-Sensoren)         eigene Monatsschleife
HA-Export (Fahrzeug-Sensor)          eigene Monatsschleife
Auswertungen → Finanzen (Aussichten) eigene Monatsschleife
===================================  ==========================================

⚠ **Zwei der fünf wurden beim Bau von #331 zuerst übersehen.** Das Konzept
führt die Aussichten in der Achsen-Tabelle unter „wer liest sie" — tatsächlich
*rechnet* `aussichten.py` die Ersparnis inline mit einer eigenen Schleife
(`agg["bisherige_ersparnis"]`). Ohne diesen Test wäre #331 mit einer bekannten
Drift ausgeliefert worden: *Auswertungen → Finanzen* hätte für einen
Plug-in-Hybrid mehr Ersparnis genannt als jede andere Sicht
([[feedback_aggregations_drift]]).

**Geprüft wird die Differenz, nicht die Absolutzahl.** Die fünf Sichten haben
verschiedene Bezugsgrößen (die Aussichten nennen einen Ertrag inklusive
Einspeisung und Eigenverbrauch, der Hub eine reine Fahrzeug-Ersparnis) — was
übereinstimmen muss, ist der **Betrag, den der Verbrenner-Anteil abzieht**.
Dieselbe Anlage einmal mit und einmal ohne gepflegtes
`eigener_verbrauch_l_100km`; die Fixture ist so gebaut, dass der Abzug in allen
fünf Sichten exakt derselbe sein muss (ein Monat, ein Preis, ein Fahrzeug).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import (
    calculate_anlage_sensors,
    calculate_investition_sensors,
)
from backend.api.routes.investitionen.dashboards import get_eauto_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

# 1000 km, 90 kWh Fahrverbrauch bei 18 kWh/100 km ⇒ 500 km elektrisch,
# 500 km Verbrenner. 500 / 100 × 6 L × 1,80 € = 54,00 €.
ERWARTETER_ABZUG_EURO = 54.0

#: ⚠ **Die Bezugsgrößen sind NICHT alle gleich, und das wird hier benannt statt
#: weggemittelt.** Vier Sichten nennen den historischen Zeitraum (ein Monat in
#: dieser Fixture); der Anlagen-Sensor `jahres_ersparnis_euro` rechnet den
#: Zeitraum ausdrücklich auf ein Jahr hoch (`/ Monate × 12`). Ein Test, der
#: überall dieselbe Zahl erwartete, wäre entweder rot oder — schlimmer — mit
#: einer Toleranz grün gebogen worden.
ERWARTETE_ABZUEGE = {
    "Cockpit": ERWARTETER_ABZUG_EURO,
    "Aussichten": ERWARTETER_ABZUG_EURO,
    "Hub": ERWARTETER_ABZUG_EURO,
    "HA-Export (Fahrzeug)": ERWARTETER_ABZUG_EURO,
    "HA-Export (Anlage, annualisiert)": ERWARTETER_ABZUG_EURO * 12,
}


async def _anlage_mit_fahrzeug(db, *, eigener_verbrauch: float | None) -> int:
    anlage = Anlage(anlagenname=f"PHEV {eigener_verbrauch}", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    # Ein Monat, ein Kraftstoffpreis — damit der Abzug in jeder Sicht mit
    # demselben Preis gebildet wird und ein Vergleich überhaupt trägt.
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=6,
        einspeisung_kwh=400.0, netzbezug_kwh=100.0, kraftstoffpreis_euro=1.80,
    ))

    params = {
        "verbrauch_kwh_100km": 18,
        "vergleich_verbrauch_l_100km": 7.5,
        "benzinpreis_euro": 1.80,
    }
    if eigener_verbrauch is not None:
        params["eigener_verbrauch_l_100km"] = eigener_verbrauch

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    auto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Hybrid",
                       anschaffungsdatum=date(2024, 1, 1),
                       anschaffungskosten_gesamt=30000.0, parameter=params)
    db.add_all([pv, auto])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=auto.id, jahr=2026, monat=6,
        verbrauch_daten={
            "km_gefahren": 1000.0,
            "verbrauch_kwh": 90.0,          # ⇒ 500 km elektrisch
            "ladung_pv_kwh": 60.0,
            "ladung_netz_kwh": 40.0,
        },
    ))
    await db.commit()
    return anlage.id


async def _fuenf_sichten(db, anlage_id: int) -> dict[str, float]:
    """⚠ **Fünf**, nicht vier — die fünfte kam beim Schreiben dieses Tests dazu.

    Der HA-Export bildet die E-Auto-Ersparnis an **zwei** Stellen: einmal
    anlagenweit in `calculate_anlage_sensors` (die in `kumulative_ersparnis`
    einfließt) und einmal je Fahrzeug in `calculate_investition_sensors` für
    den Sensor `e_auto_ersparnis_vs_benzin_euro`. Beide rechnen ihre eigene
    Monatsschleife.
    """
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    hub = await get_eauto_dashboard(anlage_id=anlage_id, db=db)

    anlage = await db.get(Anlage, anlage_id)
    anlage_sensoren = await calculate_anlage_sensors(db, anlage)
    ha_jahr = next(
        s.value for s in anlage_sensoren
        if s.definition.key == "jahres_ersparnis_euro"
    )

    auto = (await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id, Investition.typ == "e-auto",
        )
    )).scalars().first()
    inv_sensoren = await calculate_investition_sensors(db, auto, None)
    ha_fahrzeug = next(
        s.value for s in inv_sensoren
        if s.definition.key == "e_auto_ersparnis_vs_benzin_euro"
    )

    return {
        "Cockpit": cockpit.emob_ersparnis_euro,
        "Aussichten": aussichten.bisherige_ertraege_euro,
        "Hub": hub[0].zusammenfassung["ersparnis_vs_benzin_euro"],
        "HA-Export (Anlage, annualisiert)": ha_jahr,
        "HA-Export (Fahrzeug)": ha_fahrzeug,
    }


@pytest.mark.asyncio
async def test_alle_fuenf_sichten_ziehen_denselben_kraftstoff_ab(db):
    ohne = await _fuenf_sichten(db, await _anlage_mit_fahrzeug(db, eigener_verbrauch=None))
    mit = await _fuenf_sichten(db, await _anlage_mit_fahrzeug(db, eigener_verbrauch=6.0))

    abzuege = {sicht: ohne[sicht] - mit[sicht] for sicht in ohne}
    # ⚠ **Alle Abweichungen sammeln, nicht bei der ersten abbrechen.** Eine
    # Schleife mit `assert` im Rumpf reißt bei der ersten Sicht — die übrigen
    # sind dann nicht mehr geprüft, und eine Sprengsatz-Probe belegt nur die
    # erste. Genau das ist beim Rot-Verifizieren dieser Datei aufgefallen.
    abweichungen = {
        sicht: (abzug, ERWARTETE_ABZUEGE[sicht])
        for sicht, abzug in abzuege.items()
        if abs(abzug - ERWARTETE_ABZUEGE[sicht]) > 0.05
    }
    assert not abweichungen, (
        "Diese Sichten ziehen einen anderen Kraftstoff-Betrag ab: "
        + "; ".join(
            f"{sicht}: {ist:.2f} € statt {soll:.2f} €"
            for sicht, (ist, soll) in abweichungen.items()
        )
        + f" — alle fuenf: { ({k: round(v, 2) for k, v in abzuege.items()}) }"
    )


@pytest.mark.asyncio
async def test_ohne_das_feld_nennt_keine_sicht_einen_abzug(db):
    """Die BEV-Invarianz auch auf Endpoint-Ebene, nicht nur in der Formel."""
    anlage_id = await _anlage_mit_fahrzeug(db, eigener_verbrauch=None)
    hub = await get_eauto_dashboard(anlage_id=anlage_id, db=db)
    z = hub[0].zusammenfassung
    assert z["fossile_kosten_euro"] == 0.0
    assert z["km_verbrenner"] == 0.0
    # ⚠ Und der Anteil wird gar nicht erst gebildet: ohne Verbrenner gibt es
    # nichts aufzuteilen. Die erste Fassung dieses Tests hat hier 500 km
    # „Verbrenner-Anteil" für ein BEV gefunden — der Fahrverbrauch deckte nur
    # die halbe Strecke, und die Aufteilung lief trotzdem. Sichtbar war die
    # Zahl nicht (die Anzeige hängt an den Kosten), in der Response stand sie.
    assert z["phev_anteil_quelle"] == "unbestimmt"
    assert z["km_elektrisch"] == pytest.approx(1000.0)
