"""C1b — `cockpit/komponenten.py` bezieht seine Monatszeile aus den Fakten (P10).

Die Migration von `get_komponenten_zeitreihe` auf `services/monats_fakten.py`
(ADR-002/**P10**, Register-ID **N-17**) war als *deckungsgleich* geplant: der
Auftrag hatte sechs Eigenschaften am Code als „gleich" belegt. Alle 2068
vorhandenen Tests liefen nach dem Umbau ohne Anpassung durch — das ist ein
Beleg, aber kein vollständiger. Dieses Modul hält die Eigenschaften fest, die
der Auftrag ausdrücklich *belegt statt angenommen* haben wollte, und die eine
Stelle, an der sich das Verhalten **ändert**.

Was hier geprüft wird:

1. ``hat_arbitrage`` / ``hat_v2h`` waren Schleifen-Variablen über ALLE Monate
   und sind jetzt ``any(...)`` über die Fakten — gleiche Aussage, auch wenn das
   auslösende Ereignis in einem anderen Monat liegt als der Rest der Daten.
2. Die Route filtert Investitionen bei ``jahr is not None`` vorab über
   ``aktiv_im_jahr`` (Blockschalter), die Schicht filtert je Monat. Der
   Monatsfilter ist der feinere — belegt an einer im Zieljahr stillgelegten
   Komponente: der Block bleibt sichtbar, die Monate nach der Stilllegung nicht.
3. Der BKW-Akku bleibt vom stationären Speicher getrennt (hier gibt es das
   N-28-Problem von C1a nicht — diese Sicht hielt beide schon immer getrennt).
4. Der Ø-Arbitragepreis ist **mengengewichtet**, nicht das Mittel der Preise.
5. **Die eine Verhaltensänderung:** ein Monat, in dem als einzige Komponente ein
   Dienstwagen gepflegt ist, erzeugt keine Zeile mehr aus lauter Nullen.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_SONSTIGES
from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)
from backend.tests import factories


async def _zeitreihe(db: AsyncSession, anlage_id: int, jahr: int | None = None):
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    return await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=jahr, db=db)


async def _anlage(db: AsyncSession, name: str) -> int:
    return (await factories.anlage(db, anlagenname=name)).id


def _monat(antwort, monat: int, jahr: int | None = None):
    for m in antwort.monatswerte:
        if m.monat == monat and (jahr is None or m.jahr == jahr):
            return m
    return None


# ── 1. Flags gelten über den ganzen Zeitraum ────────────────────────────────

async def test_flags_gelten_ueber_alle_monate(db):
    """`hat_arbitrage`/`hat_v2h` sind Zeitraum-Aussagen, keine Monatswerte.

    Arbitrage passiert nur im Januar, V2H nur im März. Beide Flags müssen wahr
    sein — sie schalten im Frontend ganze Blöcke, nicht einzelne Zellen.
    """
    anlage_id = await _anlage(db, "C1bFlags")
    speicher = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
    )
    eauto = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Auto",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_E_AUTO["V2H_FAEHIG"]: True},
    )
    db.add_all([speicher, eauto])
    await db.flush()
    db.add_all([
        # Januar: Netzladung (Arbitrage), kein V2H.
        InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=1,
            verbrauch_daten={"ladung_kwh": 300.0, "entladung_kwh": 270.0,
                             "ladung_netz_kwh": 80.0},
        ),
        # März: V2H, keine Netzladung.
        InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2025, monat=3,
            verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0,
                             "v2h_entladung_kwh": 40.0},
        ),
    ])
    await db.commit()

    antwort = await _zeitreihe(db, anlage_id, jahr=2025)
    assert antwort.hat_arbitrage is True, "Netzladung im Januar zählt für 2025"
    assert antwort.hat_v2h is True, "V2H im März zählt für 2025"
    assert _monat(antwort, 1).speicher_arbitrage_kwh == 80.0
    assert _monat(antwort, 3).emob_v2h_kwh == 40.0

    # Ein Jahr ohne diese Ereignisse schaltet die Blöcke wieder ab.
    leer = await _zeitreihe(db, anlage_id, jahr=2024)
    assert leer.hat_arbitrage is False
    assert leer.hat_v2h is False


# ── 2. Blockschalter vs. Monatsfilter ───────────────────────────────────────

async def test_im_zieljahr_stillgelegte_komponente(db):
    """`aktiv_im_jahr` schaltet den Block, `ist_aktiv_im_monat` die Zeilen.

    Der Speicher wird Ende Juni 2025 stillgelegt. `hat_speicher` bleibt für
    2025 wahr (er war im Jahr in Betrieb), aber eine IMD-Zeile aus dem August
    darf nicht mehr zählen — der Monatsfilter der Schicht ist der feinere, und
    das Ergebnis ändert sich dadurch nicht gegenüber dem alten Loop-Filter.
    """
    anlage_id = await _anlage(db, "C1bStill")
    speicher = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=date(2025, 6, 30),
    )
    db.add(speicher)
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=5,
            verbrauch_daten={"ladung_kwh": 100.0, "entladung_kwh": 90.0},
        ),
        InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=8,
            verbrauch_daten={"ladung_kwh": 999.0, "entladung_kwh": 999.0},
        ),
    ])
    await db.commit()

    antwort = await _zeitreihe(db, anlage_id, jahr=2025)
    assert antwort.hat_speicher is True, "im Jahr in Betrieb → Block sichtbar"
    assert _monat(antwort, 5).speicher_ladung_kwh == 100.0
    assert _monat(antwort, 8) is None, (
        "nach der Stilllegung gepflegte Werte erzeugen keine Zeile "
        "([[feedback_anschaffungsdatum_grenze]], #236)"
    )


# ── 3. BKW-Akku bleibt getrennt ─────────────────────────────────────────────

async def test_bkw_akku_zaehlt_nicht_in_den_stationaeren_speicher(db):
    """Diese Sicht hält BKW-Akku und Speicher getrennt — und tut es weiter.

    Anders als `list_monatsdaten_aggregiert` (C1a, Altbestand N-28) hat die
    Komponenten-Zeitreihe die beiden nie in eine Summe geworfen. Die Schicht
    trennt sie ebenfalls (`SpeicherFakten` ↔ `BkwFakten`), der Umbau erhält das.
    """
    anlage_id = await _anlage(db, "C1bBkw")
    speicher = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung="Hausakku",
        anschaffungsdatum=date(2024, 1, 1),
    )
    bkw = Investition(
        anlage_id=anlage_id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add_all([speicher, bkw])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=4,
            verbrauch_daten={"ladung_kwh": 200.0, "entladung_kwh": 180.0},
        ),
        InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=2025, monat=4,
            verbrauch_daten={"pv_erzeugung_kwh": 60.0, "eigenverbrauch_kwh": 45.0,
                             "speicher_ladung_kwh": 30.0,
                             "speicher_entladung_kwh": 27.0},
        ),
    ])
    await db.commit()

    april = _monat(await _zeitreihe(db, anlage_id, jahr=2025), 4)
    assert april.speicher_ladung_kwh == 200.0, "nur der stationäre Speicher"
    assert april.speicher_entladung_kwh == 180.0
    assert april.bkw_speicher_ladung_kwh == 30.0
    assert april.bkw_speicher_entladung_kwh == 27.0
    assert april.bkw_erzeugung_kwh == 60.0
    assert april.bkw_eigenverbrauch_kwh == 45.0, "der GEMESSENE Wert, nicht der Rest"


# ── 4. Ø-Arbitragepreis mengengewichtet ─────────────────────────────────────

async def test_arbitrage_preis_ist_mengengewichtet(db):
    """Zwei Speicher, verschiedene Mengen und Preise → Ø nach Menge.

    100 kWh × 10 ct + 300 kWh × 30 ct = 10 000 ct auf 400 kWh ⇒ 25,00 ct.
    Das ungewichtete Mittel wäre 20,00 ct — genau die Verwechslung, die der
    Auftrag als „gleich zur Schicht" belegt hatte und die hier festgehalten wird.
    Ein dritter Speicher lädt aus dem Netz **ohne** gepflegten Preis: seine Menge
    zählt in `speicher_arbitrage_kwh`, aber nicht in die Preisgewichtung.
    """
    anlage_id = await _anlage(db, "C1bArbitrage")
    invs = [
        Investition(anlage_id=anlage_id, typ="speicher", bezeichnung=f"Akku {n}",
                    anschaffungsdatum=date(2024, 1, 1))
        for n in range(3)
    ]
    db.add_all(invs)
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(
            investition_id=invs[0].id, jahr=2025, monat=2,
            verbrauch_daten={"ladung_kwh": 100.0, "ladung_netz_kwh": 100.0,
                             "speicher_ladepreis_cent": 10.0},
        ),
        InvestitionMonatsdaten(
            investition_id=invs[1].id, jahr=2025, monat=2,
            verbrauch_daten={"ladung_kwh": 300.0, "ladung_netz_kwh": 300.0,
                             "speicher_ladepreis_cent": 30.0},
        ),
        InvestitionMonatsdaten(
            investition_id=invs[2].id, jahr=2025, monat=2,
            verbrauch_daten={"ladung_kwh": 500.0, "ladung_netz_kwh": 500.0},
        ),
    ])
    await db.commit()

    februar = _monat(await _zeitreihe(db, anlage_id, jahr=2025), 2)
    assert februar.speicher_arbitrage_kwh == 900.0, "alle drei Netzladungen"
    assert februar.speicher_arbitrage_preis_cent == 25.0, (
        "mengengewichtet (25,00), nicht das Mittel der Preise (20,00) — und die "
        "preislose Zeile verwässert den Ø nicht"
    )


# ── 5. Die eine Verhaltensänderung ──────────────────────────────────────────

async def test_dienstwagen_allein_erzeugt_keine_nullzeile(db):
    """Ein Monat mit NUR einem Dienstwagen liefert keine Zeile aus Nullen mehr.

    **Sichtbare Änderung dieses Umbaus.** Der alte Loop legte den Monatseintrag
    an, *bevor* er den Dienstwagen übersprang — der Monat erschien danach mit
    lauter Nullen in „Auswertungen → Komponenten". Das behauptete „0 kWh
    geladen" über ein Fahrzeug, das diese Sicht ausdrücklich nicht auswertet
    (`services/monats_fakten.py::_RohMonat.falte`,
    [[feedback_dienstwagen_alle_checks]]) — dieselbe Klasse, gegen die
    `docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md` steht.

    Betroffen ist nur der Monat, in dem der Dienstwagen die **einzige** Spur
    ist: sobald eine andere Komponente oder eine Finanz-Position dazukommt,
    entsteht die Zeile wie bisher — mit dem Dienstwagen weiterhin draußen.
    """
    anlage_id = await _anlage(db, "C1bDienst")
    dienst = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Firmenwagen",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_E_AUTO["IST_DIENSTLICH"]: True},
    )
    privat = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Privatwagen",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_E_AUTO["IST_DIENSTLICH"]: False},
    )
    db.add_all([dienst, privat])
    await db.flush()
    db.add_all([
        # Juni: nur der Dienstwagen.
        InvestitionMonatsdaten(
            investition_id=dienst.id, jahr=2025, monat=6,
            verbrauch_daten={"ladung_kwh": 400.0, "ladung_pv_kwh": 250.0,
                             "km_gefahren": 2500.0},
        ),
        # Juli: Dienstwagen UND Privatwagen.
        InvestitionMonatsdaten(
            investition_id=dienst.id, jahr=2025, monat=7,
            verbrauch_daten={"ladung_kwh": 400.0, "ladung_pv_kwh": 250.0,
                             "km_gefahren": 2500.0},
        ),
        InvestitionMonatsdaten(
            investition_id=privat.id, jahr=2025, monat=7,
            verbrauch_daten={"ladung_kwh": 80.0, "ladung_pv_kwh": 60.0,
                             "km_gefahren": 500.0},
        ),
    ])
    await db.commit()

    antwort = await _zeitreihe(db, anlage_id, jahr=2025)
    assert _monat(antwort, 6) is None, (
        "ein Monat, dessen einzige Spur ein Dienstwagen ist, erzeugt keine "
        "Zeile aus Nullen mehr"
    )
    juli = _monat(antwort, 7)
    assert juli is not None, "sobald etwas Auswertbares dabei ist, bleibt die Zeile"
    assert juli.emob_ladung_kwh == 80.0, "nur der Privatwagen im Pool"
    assert juli.emob_km == 500.0


async def test_dienstwagen_mit_finanzposition_behaelt_seine_zeile(db):
    """Die Finanz-Positionen eines Dienstwagens zählen weiter — und tragen den Monat.

    Der Dienstwagen fällt aus dem Energie-Pool, nicht aus der Buchhaltung:
    `_RohMonat.falte` liest `berechne_sonstige_summen` typ- und
    dienstwagen-**unabhängig** (#310). Ohne diesen Test sähe der Fall oben wie
    „Dienstwagen-Monate verschwinden immer" aus, und das wäre falsch.
    """
    anlage_id = await _anlage(db, "C1bDienstGeld")
    dienst = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Firmenwagen",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_E_AUTO["IST_DIENSTLICH"]: True},
    )
    db.add(dienst)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=dienst.id, jahr=2025, monat=6,
        verbrauch_daten={
            "ladung_kwh": 400.0,
            "sonstige_positionen": [
                {"bezeichnung": "Reifenwechsel", "betrag": 120.0, "typ": "ausgabe"},
            ],
        },
    ))
    await db.commit()

    juni = _monat(await _zeitreihe(db, anlage_id, jahr=2025), 6)
    assert juni is not None, "die Finanz-Position trägt den Monat"
    assert juni.sonstige_ausgaben_euro == 120.0
    assert juni.sonderkosten_euro == 120.0
    assert juni.emob_ladung_kwh == 0.0, "die Energie bleibt draußen"


# ── 6. Bitgleich über alle Wege zusammen ────────────────────────────────────

async def test_alle_wege_in_einem_monat(db):
    """Eine Anlage, die jeden Weg pflegt — der Regressionsanker der Etappe.

    Modul-PV, BKW mit Akku, stationärer Speicher mit Arbitrage, WP mit
    getrennter Strommessung, E-Auto + Wallbox (Pool!), Dienstwagen, sonstiger
    Erzeuger, sonstiger Verbraucher, Finanz-Positionen auf IMD- **und**
    Anlage-Ebene. Die Werte sind die des alten Faltungs-Loops.
    """
    anlage_id = await _anlage(db, "C1bVoll")
    pv = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1))
    bkw = Investition(anlage_id=anlage_id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1))
    speicher = Investition(anlage_id=anlage_id, typ="speicher", bezeichnung="Akku",
                           anschaffungsdatum=date(2024, 1, 1))
    wp = Investition(
        anlage_id=anlage_id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"getrennte_strommessung": True},
    )
    eauto = Investition(anlage_id=anlage_id, typ="e-auto", bezeichnung="Auto",
                        anschaffungsdatum=date(2024, 1, 1))
    wallbox = Investition(anlage_id=anlage_id, typ="wallbox", bezeichnung="WB",
                          anschaffungsdatum=date(2024, 1, 1))
    dienst = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Firmenwagen",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_E_AUTO["IST_DIENSTLICH"]: True},
    )
    erzeuger = Investition(
        anlage_id=anlage_id, typ="sonstiges", bezeichnung="BHKW",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_SONSTIGES["KATEGORIE"]: "erzeuger"},
    )
    verbraucher = Investition(
        anlage_id=anlage_id, typ="sonstiges", bezeichnung="Heizstab",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={PARAM_SONSTIGES["KATEGORIE"]: "verbraucher"},
    )
    db.add_all([pv, bkw, speicher, wp, eauto, wallbox, dienst, erzeuger, verbraucher])
    await db.flush()

    db.add(Monatsdaten(
        anlage_id=anlage_id, jahr=2025, monat=9,
        einspeisung_kwh=400.0, netzbezug_kwh=250.0,
        sonstige_positionen=[
            {"bezeichnung": "Direktvermarktung", "betrag": 15.0, "typ": "ertrag"},
        ],
    ))
    db.add_all([
        # Finanz-Position an einem Typ, den der Energie-Loop nie sah (#310) —
        # sie hängt an derselben Zeile wie der Modulwert (eine IMD je Monat).
        InvestitionMonatsdaten(
            investition_id=pv.id, jahr=2025, monat=9,
            verbrauch_daten={"pv_erzeugung_kwh": 900.0, "sonstige_positionen": [
                {"bezeichnung": "Modulreinigung", "betrag": 80.0, "typ": "ausgabe"},
            ]}),
        InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=2025, monat=9,
            verbrauch_daten={"pv_erzeugung_kwh": 70.0, "eigenverbrauch_kwh": 55.0,
                             "speicher_ladung_kwh": 20.0,
                             "speicher_entladung_kwh": 18.0}),
        InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=9,
            verbrauch_daten={"ladung_kwh": 240.0, "entladung_kwh": 216.0,
                             "ladung_netz_kwh": 40.0,
                             "speicher_ladepreis_cent": 12.0}),
        InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=9,
            verbrauch_daten={"waerme_kwh": 600.0, "heizung_kwh": 450.0,
                             "warmwasser_kwh": 150.0,
                             "strom_heizen_kwh": 120.0,
                             "strom_warmwasser_kwh": 50.0}),
        InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2025, monat=9,
            verbrauch_daten={"ladung_kwh": 180.0, "ladung_pv_kwh": 120.0,
                             "ladung_netz_kwh": 60.0, "km_gefahren": 1000.0,
                             "verbrauch_kwh": 170.0, "v2h_entladung_kwh": 25.0}),
        # Wallbox misst denselben Fluss aus Ladepunkt-Sicht → darf NICHT addiert
        # werden (#262). Der Pool wählt EINE Quelle, und zwar **strukturell**:
        # Wallbox mit Heimladung gewinnt, unabhängig von der Magnitude.
        InvestitionMonatsdaten(
            investition_id=wallbox.id, jahr=2025, monat=9,
            verbrauch_daten={"ladung_kwh": 175.0, "ladung_pv_kwh": 115.0}),
        InvestitionMonatsdaten(
            investition_id=dienst.id, jahr=2025, monat=9,
            verbrauch_daten={"ladung_kwh": 500.0, "ladung_pv_kwh": 300.0,
                             "km_gefahren": 3000.0}),
        InvestitionMonatsdaten(investition_id=erzeuger.id, jahr=2025, monat=9,
                               verbrauch_daten={"erzeugung_kwh": 130.0}),
        InvestitionMonatsdaten(investition_id=verbraucher.id, jahr=2025, monat=9,
                               verbrauch_daten={"verbrauch_kwh": 90.0}),
    ])
    await db.commit()

    antwort = await _zeitreihe(db, anlage_id, jahr=2025)
    sep = _monat(antwort, 9)
    assert sep is not None

    assert sep.speicher_ladung_kwh == 240.0
    assert sep.speicher_entladung_kwh == 216.0
    assert sep.speicher_effizienz_prozent == 90.0
    assert sep.speicher_arbitrage_kwh == 40.0
    assert sep.speicher_arbitrage_preis_cent == 12.0

    assert sep.wp_waerme_kwh == 600.0
    assert sep.wp_strom_kwh == 170.0, "getrennte Strommessung: Heizen + Warmwasser"
    assert sep.wp_heizung_kwh == 450.0
    assert sep.wp_warmwasser_kwh == 150.0
    assert sep.wp_cop == round(600.0 / 170.0, 2)

    # Pool statt Summe: 175 (Wallbox gewinnt strukturell) statt 355 — und der
    # Dienstwagen mit seinen 500 kWh ist gar nicht erst dabei. Der Netz-Anteil
    # wird abgeleitet: 175 − 115 = 60 (`get_emob_pv_netz_kwh`, #262).
    assert sep.emob_ladung_kwh == 175.0
    assert sep.emob_ladung_pv_kwh == 115.0
    assert sep.emob_ladung_netz_kwh == 60.0
    assert sep.emob_km == 1000.0, "km nur vom privaten E-Auto"
    assert sep.emob_v2h_kwh == 25.0, "V2H nur vom E-Auto — die Wallbox kennt es nicht"
    assert sep.emob_verbrauch_kwh == 170.0
    assert sep.emob_verbrauch_100km == 17.0
    assert sep.emob_verbrauch_quelle == "gemessen"

    assert sep.bkw_erzeugung_kwh == 70.0
    assert sep.bkw_eigenverbrauch_kwh == 55.0
    assert sep.bkw_speicher_ladung_kwh == 20.0

    assert sep.sonstiges_erzeugung_kwh == 130.0
    assert sep.sonstiges_verbrauch_kwh == 90.0

    # 15 € Anlage-Ertrag, 80 € IMD-Ausgabe am PV-Modul.
    assert sep.sonstige_ertraege_euro == 15.0
    assert sep.sonstige_ausgaben_euro == 80.0
    assert sep.sonstige_netto_euro == -65.0
    assert sep.sonderkosten_euro == 80.0
    assert sep.anlage_sonstige_ertraege_euro == 15.0
    assert sep.anlage_sonstige_ausgaben_euro == 0.0

    assert antwort.hat_speicher and antwort.hat_waermepumpe
    assert antwort.hat_emobilitaet and antwort.hat_balkonkraftwerk
    assert antwort.hat_sonstiges and antwort.hat_arbitrage and antwort.hat_v2h
    assert antwort.emob_verbrauch_100km_gesamt == 17.0
