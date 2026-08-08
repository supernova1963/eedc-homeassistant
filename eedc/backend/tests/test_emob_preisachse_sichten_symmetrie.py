"""Ein Strompreis, fünf Sichten — F-18 · N-181 gegen die Preisachsen-Drift.

Bis 2026-08-08 löste jede Sicht den Netzbezugspreis der E-Auto-Ladung selbst
auf, und zwar auf **vier** verschiedene Arten:

===================================  ==========================================
Cockpit → Jahr                       der **heute** gültige Wallbox-Tarif
HA-Export (Anlagen-Sensoren)         der **heute** gültige ALLGEMEINE Tarif
HA-Export (Fahrzeug-Sensor)          der **heute** gültige ALLGEMEINE Tarif
Komponenten-Hub                      km-gewichteter Monats-Ø (Wallbox-Tarif)
Auswertungen → Aussichten            Monatspreis inkl. Flex-Ø (ALLGEMEIN)
===================================  ==========================================

Der heutige Tarif ist schlicht falsch: eine Preiserhöhung bewertete damit die
gesamte Ladehistorie rückwirkend neu. An einer laufenden Box gemessen (Anlage
mit vier Tarifstufen, 40 → 32 → 34 → 31,5 ct): Cockpit **2376,54 €**, Hub
**2335,44 €** — bei identischer kWh-Basis, die Benzinkosten stimmten auf vier
Cent überein. Der ausgelieferte HA-Sensor `e_auto_ersparnis_vs_benzin_euro`
trug dabei die falsche Seite.

⚠ **Der P8-Wächter konnte das nicht sehen.** Alle vier beteiligten Dateien
stehen in `P8_BASELINE_AUSNAHMEN` — sie brauchen den heutigen Tarif
legitimerweise auch, nämlich für die Hochrechnung nach vorn. Eine
Wächter-Baseline ist eine Aussage über sein **Sichtfeld**, nicht über den Baum.

**Geprüft wird eine DOPPEL-Differenz über vier Anlagen**, nicht die Absolutzahl.
Der erste Entwurf verglich nur „fester Tarif" gegen „Tarifwechsel" und lief bei
zwei Sichten in die Gegenrichtung (−180 statt +60). ⚠ **Die Ursache war meine
Erwartung, nicht der Code:** `bisherige_ertraege_euro` der Aussichten und
`jahres_ersparnis_euro` des HA-Exports enthalten auch den Einspeiseerlös und die
**Eigenverbrauchs-Ersparnis** — und die hängt am selben Tarif. Ein billigerer
Januar senkt den vermiedenen Netzbezug stärker, als er die Ladung verbilligt.

Deshalb je Tarifprofil **zwei** Anlagen, identisch bis auf die Netzladung:

    (mit_ladung − ohne_ladung)  bei Tarifwechsel   = −(300×20ct + 300×40ct) = −180 €
    (mit_ladung − ohne_ladung)  bei festem Tarif   = −(600×40ct)            = −240 €
    Differenz der Differenzen                       = +60 €

Alles, was nicht an der Ladung hängt, kürzt sich in der inneren Differenz
heraus. Wer den heutigen Tarif nimmt, misst hier **0**.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import (
    _load_emob_pool_ctx,
    calculate_anlage_sensors,
    calculate_investition_sensors,
)
from backend.api.routes.investitionen.dashboards import get_eauto_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

#: Sechs Monate à 100 kWh Netzladung. Mit Tarifwechsel kosten die ersten drei
#: 20 ct statt 40 ct ⇒ 300 kWh × 20 ct = **60,00 €** weniger Stromkosten, also
#: exakt so viel MEHR Ersparnis.
ERWARTETE_DIFFERENZ_EURO = 60.0

#: ⚠ Die Bezugsgrößen sind nicht alle gleich — der Anlagen-Sensor
#: `jahres_ersparnis_euro` rechnet den Zeitraum ausdrücklich auf ein Jahr hoch
#: (`/ Monate × 12`). Bei sechs Monaten ist das der Faktor 2. Ein Test, der
#: überall dieselbe Zahl erwartete, wäre mit einer Toleranz grün gebogen worden.
ERWARTETE_DIFFERENZEN = {
    "Cockpit": ERWARTETE_DIFFERENZ_EURO,
    "Aussichten": ERWARTETE_DIFFERENZ_EURO,
    "Hub": ERWARTETE_DIFFERENZ_EURO,
    "HA-Export (Fahrzeug)": ERWARTETE_DIFFERENZ_EURO,
    "HA-Export (Anlage, annualisiert)": ERWARTETE_DIFFERENZ_EURO * 2,
}

MONATE = [(2026, m) for m in range(1, 7)]


async def _anlage(db, *, tarifwechsel: bool, mit_wallbox: bool, netzladung: float = 100.0) -> int:
    """Sechs Monate Ladung; optional Tarifwechsel, optional evcc-Konstellation.

    ⚠ **`mit_wallbox` ist keine Kosmetik.** Trägt eine Wallbox die Ladung, gilt
    die Pool-Regel und die E-Auto-Sichten ziehen km-anteilig aus dem
    Wallbox-Topf; ohne sie lesen sie die Zeile des Fahrzeugs. Das sind zwei
    verschiedene Codepfade, und eine Probe, die nur einen betritt, lässt einen
    Sprengsatz im anderen stumm (die Lehre aus Sitzung 13).
    """
    anlage = Anlage(
        anlagenname=f"Preisachse {tarifwechsel}/{mit_wallbox}/{netzladung}",
        leistung_kwp=10.0,
    )
    db.add(anlage)
    await db.flush()

    if tarifwechsel:
        db.add(Strompreis(
            anlage_id=anlage.id, gueltig_ab=date(2026, 1, 1),
            gueltig_bis=date(2026, 3, 31),
            netzbezug_arbeitspreis_cent_kwh=20.0, einspeiseverguetung_cent_kwh=8.0,
        ))
        db.add(Strompreis(
            anlage_id=anlage.id, gueltig_ab=date(2026, 4, 1),
            netzbezug_arbeitspreis_cent_kwh=40.0, einspeiseverguetung_cent_kwh=8.0,
        ))
    else:
        db.add(Strompreis(
            anlage_id=anlage.id, gueltig_ab=date(2026, 1, 1),
            netzbezug_arbeitspreis_cent_kwh=40.0, einspeiseverguetung_cent_kwh=8.0,
        ))

    for jahr, monat in MONATE:
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=jahr, monat=monat,
            einspeisung_kwh=400.0, netzbezug_kwh=200.0, kraftstoffpreis_euro=1.80,
        ))

    params = {
        "verbrauch_kwh_100km": 18,
        "vergleich_verbrauch_l_100km": 7.5,
        "benzinpreis_euro": 1.80,
    }
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2025, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    auto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="BEV",
                       anschaffungsdatum=date(2025, 1, 1),
                       anschaffungskosten_gesamt=30000.0, parameter=params)
    db.add_all([pv, auto])
    wallbox = None
    if mit_wallbox:
        wallbox = Investition(
            anlage_id=anlage.id, typ="wallbox", bezeichnung="WB",
            anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1500.0,
        )
        db.add(wallbox)
    await db.flush()

    for jahr, monat in MONATE:
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=jahr, monat=monat,
            verbrauch_daten={"pv_erzeugung_kwh": 800.0},
        ))
        # km IMMER am Fahrzeug — sie sind der Verteilschlüssel des Pools.
        auto_daten = {"km_gefahren": 500.0, "verbrauch_kwh": 90.0}
        lade_daten = {"ladung_pv_kwh": 50.0, "ladung_netz_kwh": netzladung}
        if wallbox is None:
            auto_daten |= lade_daten
        else:
            db.add(InvestitionMonatsdaten(
                investition_id=wallbox.id, jahr=jahr, monat=monat,
                verbrauch_daten=lade_daten,
            ))
        db.add(InvestitionMonatsdaten(
            investition_id=auto.id, jahr=jahr, monat=monat,
            verbrauch_daten=auto_daten,
        ))
    await db.commit()
    return anlage.id


async def _fuenf_sichten(db, anlage_id: int) -> dict[str, float]:
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
    # ⚠ MIT Pool-Kontext, wie in Produktion (`ha_export.py:1509`). Ohne ihn
    # liest der Fahrzeug-Sensor die eigene (bei evcc leere) Zeile — ein Pfad,
    # den es im Betrieb nicht gibt. Genau daran zeigte der erste Entwurf
    # 54 statt 60 € im Wallbox-Fall.
    alle_invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all()
    emob_ctx = await _load_emob_pool_ctx(db, alle_invs)
    inv_sensoren = await calculate_investition_sensors(db, auto, None, emob_ctx)
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


async def _ladungs_differenz(db, *, tarifwechsel: bool, mit_wallbox: bool) -> dict[str, float]:
    """Was die Netzladung in jeder Sicht KOSTET — alles andere kürzt sich weg."""
    mit = await _fuenf_sichten(db, await _anlage(
        db, tarifwechsel=tarifwechsel, mit_wallbox=mit_wallbox, netzladung=100.0))
    ohne = await _fuenf_sichten(db, await _anlage(
        db, tarifwechsel=tarifwechsel, mit_wallbox=mit_wallbox, netzladung=0.0))
    return {s: mit[s] - ohne[s] for s in mit}


@pytest.mark.parametrize("mit_wallbox", [False, True], ids=["steckerlader", "wallbox"])
@pytest.mark.asyncio
async def test_alle_sichten_bewerten_die_historie_mit_dem_monatstarif(db, mit_wallbox):
    fest = await _ladungs_differenz(db, tarifwechsel=False, mit_wallbox=mit_wallbox)
    gewechselt = await _ladungs_differenz(db, tarifwechsel=True, mit_wallbox=mit_wallbox)

    differenzen = {s: gewechselt[s] - fest[s] for s in fest}
    # Alle Abweichungen sammeln statt bei der ersten abzubrechen — sonst belegt
    # eine Sprengsatz-Probe nur die erste Sicht.
    abweichungen = {
        sicht: (diff, ERWARTETE_DIFFERENZEN[sicht])
        for sicht, diff in differenzen.items()
        if abs(diff - ERWARTETE_DIFFERENZEN[sicht]) > 0.05
    }
    assert not abweichungen, (
        "Diese Sichten bewerten die Historie nicht mit dem Monatstarif: "
        + "; ".join(
            f"{sicht}: {ist:.2f} € statt {soll:.2f} €"
            for sicht, (ist, soll) in abweichungen.items()
        )
        + f" — alle fuenf: { ({k: round(v, 2) for k, v in differenzen.items()}) }"
    )


@pytest.mark.asyncio
async def test_ohne_tarifwechsel_bewegt_die_umstellung_keine_zahl(db):
    """Die Migrationszusage: wer nie den Tarif gewechselt hat, sieht nichts.

    Der mengengewichtete Ø eines einzigen Tarifs **ist** dieser Tarif — sonst
    hätte die Umstellung bei jedem Anwender eine Zahl bewegt, statt nur bei
    denen mit echter Historie.
    """
    sichten = await _fuenf_sichten(
        db, await _anlage(db, tarifwechsel=False, mit_wallbox=True)
    )
    # 6 × 500 km = 3000 km × 7,5 L/100km × 1,80 € = 405 € Benzin
    # 6 × 100 kWh = 600 kWh × 40 ct = 240 € Strom ⇒ 165 € Ersparnis
    assert sichten["Cockpit"] == pytest.approx(165.0, abs=0.05)
    assert sichten["Hub"] == pytest.approx(165.0, abs=0.05)
    assert sichten["HA-Export (Fahrzeug)"] == pytest.approx(165.0, abs=0.05)


@pytest.mark.asyncio
async def test_wallbox_ladung_erreicht_die_aussichten(db):
    """F-17: die Sicht, die als einzige keine Pool-Attribution hatte.

    Bei einem evcc-Setup liegt die Ladung auf der Wallbox. Vorher sah
    `aussichten.py` dort **null** Netzladung und zog gar keine Stromkosten ab —
    die ausgewiesene Ersparnis war um genau diesen Betrag zu hoch.
    """
    mit_wb = await _fuenf_sichten(
        db, await _anlage(db, tarifwechsel=False, mit_wallbox=True)
    )
    ohne_wb = await _fuenf_sichten(
        db, await _anlage(db, tarifwechsel=False, mit_wallbox=False)
    )
    # Dieselbe Ladung, nur an anderer Stelle erfasst ⇒ dieselbe Zahl.
    assert mit_wb["Aussichten"] == pytest.approx(ohne_wb["Aussichten"], abs=0.05)
    assert mit_wb["Cockpit"] == pytest.approx(ohne_wb["Cockpit"], abs=0.05)
