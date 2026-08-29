"""
Zeittarif (HT/NT) — N-267, Melder MeinerB (Bernd) in Discussion #380.

**Was hier bewiesen wird, und warum in dieser Form.** Der Fund ist keine
Anzeigefrage: ein Zeitfenster ändert den Preis, mit dem ein vergangener Monat
gerechnet wird. Eine Probe, die nur den *ausgewiesenen* Preis prüft, würde
grün bleiben, wenn der Preis zwar richtig gebildet, aber nirgends **verrechnet**
wird — das ist die N-274-Bauform (dort blieben elf von dreizehn Proben unter dem
Sprengsatz grün). Deshalb prüfen ``W-Z1`` und ``W-Z2`` die **gerechneten
Kosten** bzw. den gerechneten Preis, nicht ein Response-Feld.

Die Wächter im Einzelnen (Konzept ``docs/drafts/KONZEPT-ZEITTARIF.md`` §6):

===== =======================================================================
W-Z1  Zwei gleiche Monate, gleiche Stundenmengen — einer mit Fenster, einer
      ohne — müssen **verschiedene Netzbezugskosten** ergeben.
W-Z2  Der wirksame Preis liegt **strikt zwischen** NT und HT, sobald in beiden
      Bändern Bezug lag. (Invariante: kein Rechenweg kann sie zufällig treffen.)
W-Z3  Anlage **ohne** Fenster: jede Zahl unverändert — der Nicht-Regressions-
      Beweis für den gesamten Bestand.
W-Z4  Kein zweiter Bauort: nur ``preis_je_slot`` hält ein Fenster gegen eine
      Stunde.
===== =======================================================================

⚠ **Die Slot-Konvention hat eine eigene Gruppe, und das ist der Kern des Baus.**
``TagesEnergieProfil.stunde`` ist ein Backward-Slot (#144): Slot ``h`` trägt die
Energie ``[h-1, h)``. Bernds Fenster **19:00–20:00 ist Slot 20**. Wer den
Slot-Index für eine Uhrzeit hält, gibt der falschen Stunde den Niedertarif — und
das fällt niemandem auf, weil beide Zahlen für sich plausibel aussehen.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.core.berechnungen.netzbezug_kosten import berechne_netzbezug_kosten
from backend.core.berechnungen.zeittarif import (
    gewichteter_arbeitspreis_cent,
    hat_zeitfenster,
    preis_je_slot,
    uhrzeit_des_slots,
)
from backend.models.strompreis import Strompreis, StrompreisZeitfenster
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.services.strompreis_aggregator import wirksamer_arbeitspreis_cent
from backend.tests import factories


# ═══════════════════════════════════════════════════════════════════════
# Hilfen
# ═══════════════════════════════════════════════════════════════════════

def _fenster(von: int, bis: int, preis: float, tage: str = "0123456") -> StrompreisZeitfenster:
    return StrompreisZeitfenster(
        von_stunde=von, bis_stunde=bis, arbeitspreis_cent_kwh=preis, wochentage=tage
    )


async def _anlage_mit_tarif(db, *, ht: float = 30.0, fenster=()) -> tuple:
    a = await factories.anlage(db)
    await db.flush()
    tarif = await factories.strompreis(
        db, a.id, date(2020, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=ht, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = list(fenster)
    await db.commit()
    return a, tarif


async def _stunden(db, anlage_id: int, tage: list[date], kw_je_slot: dict[int, float]):
    """Netzbezug je Backward-Slot für jeden genannten Tag."""
    for tag in tage:
        for slot, kw in kw_je_slot.items():
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=tag, stunde=slot, netzbezug_kw=kw,
            ))
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════
# Die Slot-Konvention (#144) — der Kern, deshalb zuerst
# ═══════════════════════════════════════════════════════════════════════

def test_slot_traegt_die_vorangehende_stunde():
    """Slot ``h`` = Energie ``[h-1, h)``, Slot 0 gehört dem **Vortag**."""
    assert uhrzeit_des_slots(date(2026, 8, 29), 20).hour == 19
    assert uhrzeit_des_slots(date(2026, 8, 29), 23).hour == 22
    vortag = uhrzeit_des_slots(date(2026, 8, 29), 0)
    assert (vortag.date(), vortag.hour) == (date(2026, 8, 28), 23)


def test_bernds_fenster_trifft_slot_20_und_nicht_slot_19():
    """19:00–20:00 ist Slot **20**.

    ⭐ Diese Probe ist der eigentliche Grund für ``uhrzeit_des_slots``. Ohne die
    Umrechnung läge der Niedertarif auf Slot 19 — also physisch auf 18:00–19:00,
    eine Stunde zu früh. Der Monatspreis wäre dann **plausibel und falsch**.
    """
    tarif = Strompreis(
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = [_fenster(19, 20, 15.0)]
    tag = date(2026, 8, 29)

    assert preis_je_slot(tarif, tag, 20) == 15.0, "Slot 20 = 19:00-20:00 = im Fenster"
    assert preis_je_slot(tarif, tag, 19) == 30.0, "Slot 19 = 18:00-19:00 = davor"
    assert preis_je_slot(tarif, tag, 21) == 30.0, "Slot 21 = 20:00-21:00 = danach"


def test_nachtstrom_laeuft_ueber_mitternacht():
    """22–06 deckt Slot 23 des Tages und die Slots 0–6 des Folgetages."""
    tarif = Strompreis(
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = [_fenster(22, 6, 12.0)]
    tag, folgetag = date(2026, 8, 29), date(2026, 8, 30)

    assert preis_je_slot(tarif, tag, 23) == 12.0, "22:00-23:00"
    assert preis_je_slot(tarif, folgetag, 0) == 12.0, "Vortag 23:00-00:00"
    assert preis_je_slot(tarif, folgetag, 6) == 12.0, "05:00-06:00"
    assert preis_je_slot(tarif, folgetag, 7) == 30.0, "06:00-07:00 — draussen"
    assert preis_je_slot(tarif, tag, 22) == 30.0, "21:00-22:00 — davor"


def test_wochentag_gilt_fuer_den_tag_der_uhrzeit():
    """„Mo–Fr 22–06" deckt Freitag 22–24, **nicht** Samstag 00–06.

    Die andere Lesart ist genauso vertretbar — deshalb ist sie ausdrücklich
    festgelegt und nicht geraten, und die Gegenrichtung bleibt ausdrückbar
    (zweites Fenster Sa 00–06). Der Docstring von ``deckt_uhrzeit`` sagt es.
    """
    tarif = Strompreis(
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = [_fenster(22, 6, 12.0, tage="01234")]  # Mo-Fr
    freitag, samstag = date(2026, 8, 28), date(2026, 8, 29)
    assert freitag.weekday() == 4 and samstag.weekday() == 5

    assert preis_je_slot(tarif, freitag, 23) == 12.0, "Fr 22:00-23:00"
    # ⭐ Slot 0 des SAMSTAGS traegt die Uhrzeit Freitag 23:00 — er faellt also
    # unter die Mo-Fr-Maske, obwohl seine Slot-Nummer am Samstag haengt. Genau
    # hier trennt sich „Tag der Uhrzeit" von „Tag des Slots"; ein erster Entwurf
    # dieser Probe erwartete 30.0 und lag falsch.
    assert preis_je_slot(tarif, samstag, 0) == 12.0, "Fr 23:00-00:00 — noch Freitag"
    assert preis_je_slot(tarif, samstag, 1) == 30.0, "Sa 00:00-01:00 — Maske greift"
    assert preis_je_slot(tarif, samstag, 3) == 30.0, "Sa 02:00-03:00 — Maske greift"


# ═══════════════════════════════════════════════════════════════════════
# W-Z2 — die Invariante
# ═══════════════════════════════════════════════════════════════════════

def test_wz2_preis_liegt_strikt_zwischen_nt_und_ht():
    tarif = Strompreis(
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = [_fenster(19, 20, 15.0)]
    tag = date(2026, 8, 29)
    # 1 kWh im Fenster (Slot 20), 3 kWh ausserhalb
    slots = [(tag, 20, 1.0), (tag, 8, 1.0), (tag, 12, 1.0), (tag, 18, 1.0)]

    preis = gewichteter_arbeitspreis_cent(tarif, slots)
    assert preis is not None
    assert 15.0 < preis < 30.0
    assert preis == pytest.approx((1 * 15.0 + 3 * 30.0) / 4)  # 26,25


def test_ohne_gemessenen_bezug_kein_erfundener_preis():
    """Kein Netzbezug ⇒ ``None``, nicht 0 ct — der Aufrufer nimmt den Stammpreis."""
    tarif = Strompreis(
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = [_fenster(19, 20, 15.0)]
    tag = date(2026, 8, 29)
    assert gewichteter_arbeitspreis_cent(tarif, []) is None
    assert gewichteter_arbeitspreis_cent(tarif, [(tag, 20, None)]) is None
    assert gewichteter_arbeitspreis_cent(tarif, [(tag, 20, 0.0)]) is None
    # Negativer Zaehler-Glitch wird geklemmt, nicht gutgeschrieben
    assert gewichteter_arbeitspreis_cent(tarif, [(tag, 20, -5.0)]) is None


def test_ohne_fenster_ist_der_preis_der_stammpreis():
    """Der rechnerische Kern von W-Z3: jede Stunde traegt denselben Preis."""
    tarif = Strompreis(
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    tarif.zeitfenster = []
    tag = date(2026, 8, 29)
    assert not hat_zeitfenster(tarif)
    assert gewichteter_arbeitspreis_cent(
        tarif, [(tag, h, 1.0) for h in range(24)]
    ) == pytest.approx(30.0)


# ═══════════════════════════════════════════════════════════════════════
# Der Service — gegen die Datenbank
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_service_gewichtet_ueber_die_stundenzeilen(db):
    a, tarif = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    # Juli 2026: an drei Tagen je 1 kWh im Fenster (Slot 20) und 3 kWh ausserhalb
    await _stunden(db, a.id, [date(2026, 7, d) for d in (1, 2, 3)],
                   {20: 1.0, 8: 1.0, 12: 1.0, 18: 1.0})

    preis = await wirksamer_arbeitspreis_cent(db, a.id, 2026, 7, tarif)
    assert preis == pytest.approx(26.25)


@pytest.mark.asyncio
async def test_service_faellt_ohne_stundenwerte_auf_den_stammpreis(db):
    """Handgetragene Monate: der Hochtarif — zu hoch, aber nie erfunden."""
    a, tarif = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    assert await wirksamer_arbeitspreis_cent(db, a.id, 2026, 7, tarif) == 30.0


@pytest.mark.asyncio
async def test_service_fragt_ohne_fenster_die_datenbank_gar_nicht(db):
    """Kein Fenster ⇒ Stammpreis, und zwar ohne Abfrage (W-Z3, Laufzeit-Hälfte)."""
    a, tarif = await _anlage_mit_tarif(db, ht=30.0, fenster=[])
    await _stunden(db, a.id, [date(2026, 7, 1)], {20: 1.0})
    assert await wirksamer_arbeitspreis_cent(db, a.id, 2026, 7, tarif) == 30.0


# ═══════════════════════════════════════════════════════════════════════
# W-Z1 / W-Z3 — die GERECHNETEN Kosten, nicht der ausgewiesene Preis
# ═══════════════════════════════════════════════════════════════════════

async def _netzbezug_kosten(db, anlage, jahr: int, monat: int) -> float:
    """Die Netzbezugskosten des Monats in Euro, wie eine Sicht sie bekommt.

    Bewusst ueber den Formel-SoT ``berechne_netzbezug_kosten`` und die
    ``FinanzMonatsZeile`` — also ueber den Weg, den Cockpit, PDF und
    HA-Export gehen, nicht ueber eine im Test nachgebaute Multiplikation.
    """
    fakten = await lade_monats_fakten(db, anlage.id, von=(jahr, monat), bis=(jahr, monat))
    assert fakten, "Monat muss in den Fakten stehen"
    cache: dict = {}
    zeile = await baue_finanz_zeile(
        db, anlage.id, finanz_zeile_eingabe(fakten[0]), tarif_cache=cache
    )
    return berechne_netzbezug_kosten(zeile.netzbezug_kwh, zeile.netzbezug_preis_cent)


@pytest.mark.asyncio
async def test_wz1_das_fenster_aendert_die_gerechneten_kosten(db):
    """⭐ Der Wächter, der bei zurückgebautem Fix rot werden MUSS.

    Zwei identische Monate, identische Stundenmengen — der Unterschied ist
    ausschließlich das Fenster. Geprüft werden die **Netzbezugskosten in Euro**,
    also die Zahl, die der Anwender sieht, nicht ein Preisfeld daneben.
    """
    stunden = {20: 1.0, 8: 1.0, 12: 1.0, 18: 1.0}  # 4 kWh/Tag, 1 davon im Fenster

    ohne, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[])
    await _stunden(db, ohne.id, [date(2026, 7, d) for d in range(1, 4)], stunden)
    await factories.monatsdaten(db, ohne.id, 2026, 7, netzbezug_kwh=12.0, einspeisung_kwh=0.0)
    await db.commit()

    mit, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    await _stunden(db, mit.id, [date(2026, 7, d) for d in range(1, 4)], stunden)
    await factories.monatsdaten(db, mit.id, 2026, 7, netzbezug_kwh=12.0, einspeisung_kwh=0.0)
    await db.commit()

    kosten_ohne = await _netzbezug_kosten(db, ohne, 2026, 7)
    kosten_mit = await _netzbezug_kosten(db, mit, 2026, 7)

    assert kosten_ohne == pytest.approx(12.0 * 30.0 / 100)          # 3,60 €
    assert kosten_mit == pytest.approx(12.0 * 26.25 / 100)          # 3,15 €
    assert kosten_mit < kosten_ohne, (
        "Das Zeitfenster muss in den GERECHNETEN Kosten ankommen — steht der "
        "Preis nur in der Antwort, ist der Fix nicht gebaut (N-274-Bauform)."
    )


@pytest.mark.asyncio
async def test_wz1b_der_zweite_bildungsort_ist_ebenfalls_eingehaengt(db):
    """⭐ Diese Probe existiert, WEIL der Sprengsatz sie erzwungen hat.

    Der erste Entwurf von ``W-Z1`` maß die Kosten über ``baue_finanz_zeile`` —
    und blieb bei **16 von 16** grün, als die Einhängung in
    ``monats_fakten::_lade_tarif`` zurückgebaut wurde. Der Grund ist banal und
    genau die N-274-Bauform: es gibt **zwei** Bildungsorte, und die Probe traf
    nur einen.

    ``MonatsFakt.tarif`` ist dabei der **größere** von beiden — Cockpit (Monat,
    Jahr), Jahresbericht-PDF, HA-Export und Aussichten lesen ihn. Ein Fund, der
    nur die Finanzzeile heilt, hätte in genau diesen Sichten den Hochtarif
    stehen lassen, während die Tabelle daneben den gewichteten Preis nennt —
    „zwei Zahlen auf einer Seite".

    ⚑ Geprüft wird der Preis **und** eine daraus gerechnete Größe, nicht nur
    das Feld: ein Preis, den niemand verrechnet, ist kein Fix.
    """
    stunden = {20: 1.0, 8: 1.0, 12: 1.0, 18: 1.0}
    a, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    await _stunden(db, a.id, [date(2026, 7, d) for d in range(1, 4)], stunden)
    await factories.monatsdaten(db, a.id, 2026, 7, netzbezug_kwh=12.0, einspeisung_kwh=0.0)
    await db.commit()

    fakten = await lade_monats_fakten(db, a.id, von=(2026, 7), bis=(2026, 7))
    tarif = fakten[0].tarif

    assert tarif.netzbezug_preis_cent == pytest.approx(26.25), (
        "Die Monats-Fakten muessen den gewichteten Preis tragen — sie sind der "
        "Pfad von Cockpit, PDF, HA-Export und Aussichten (ADR-002/P10)."
    )
    assert tarif.netzbezug_stammpreis_cent == pytest.approx(26.25)
    assert berechne_netzbezug_kosten(
        fakten[0].zaehler.netzbezug_kwh, tarif.netzbezug_preis_cent
    ) == pytest.approx(12.0 * 26.25 / 100)


@pytest.mark.asyncio
async def test_wz1c_die_emob_preisachse_ist_ebenfalls_eingehaengt(db):
    """Der DRITTE Bildungsort — ``monats_strompreis_lookup`` (F-18).

    Ohne ihn stuende in der E-Mob-Ersparnis der Hochtarif, waehrend Cockpit
    daneben den gewichteten Preis nennt. Dieselbe Lehre wie eine Probe hoeher,
    nur an der dritten Stelle: **jede** Bildungsstelle braucht ihre eigene
    Gegenprobe, sonst deckt die Suite die Klasse nur scheinbar ab.
    """
    from backend.api.routes.strompreise import monats_strompreis_lookup

    a, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    await _stunden(db, a.id, [date(2026, 7, d) for d in range(1, 4)],
                   {20: 1.0, 8: 1.0, 12: 1.0, 18: 1.0})

    lookup = await monats_strompreis_lookup(
        db, a.id, "wallbox", [(2026, 7)], fallback_bezug=99.0
    )
    assert lookup[(2026, 7)] == pytest.approx(26.25)


@pytest.mark.asyncio
async def test_wz1d_cockpit_monat_ist_ebenfalls_eingehaengt(db):
    """⭐ Die VIERTE Bildungsstelle — vom Konzept übersehen, beim Bau gefunden.

    Das Konzept nannte drei Bildungsstellen; ``aktueller_monat.py`` bildet den
    Preis eine Ebene darüber (``netzbezug_preis_effektiv_cent``) und war deshalb
    in keiner Grep-Zählung. Aus ihm entstehen die **Netzbezugskosten**, die
    **EV-Ersparnis** und das ausgelieferte Feld ``netzbezug_preis_cent``, das
    das T-Konto anzeigt.

    ⚑ Ohne diese Einhängung nennte Cockpit → **Monat** den Hochtarif, während
    Cockpit → **Jahr** daneben den gewichteten Preis zeigt — zwei Zahlen auf
    einer Seite, die v4.0.1-Klasse. *Eine Zählung aus einem Grep ist eine
    Behauptung, kein Befund.*
    """
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    a, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    await _stunden(db, a.id, [date(2026, 7, d) for d in range(1, 4)],
                   {20: 1.0, 8: 1.0, 12: 1.0, 18: 1.0})
    await factories.monatsdaten(db, a.id, 2026, 7, netzbezug_kwh=12.0, einspeisung_kwh=0.0)
    await db.commit()

    antwort = await get_aktueller_monat(a.id, jahr=2026, monat=7, db=db)

    assert antwort.netzbezug_preis_cent == pytest.approx(26.25), (
        "Cockpit → Monat muss denselben gewichteten Preis nennen wie Cockpit → Jahr"
    )
    assert antwort.netzbezug_kosten_euro == pytest.approx(12.0 * 26.25 / 100, abs=0.01)


@pytest.mark.asyncio
async def test_wz3_eine_anlage_ohne_fenster_bewegt_keine_zahl(db):
    """Der Nicht-Regressions-Beweis für den gesamten Bestand.

    Dieselben Daten, einmal ohne Fenster und einmal mit einem Fenster, das den
    **HT-Preis** trägt: beide müssen exakt dasselbe ergeben. Damit ist gezeigt,
    dass nicht der Zeittarif-PFAD die Zahl bewegt, sondern nur ein
    abweichender Preis darin.
    """
    stunden = {h: 1.0 for h in range(24)}

    ohne, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[])
    await _stunden(db, ohne.id, [date(2026, 7, 1)], stunden)
    await factories.monatsdaten(db, ohne.id, 2026, 7, netzbezug_kwh=24.0, einspeisung_kwh=0.0)
    await db.commit()

    gleich, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 30.0)])
    await _stunden(db, gleich.id, [date(2026, 7, 1)], stunden)
    await factories.monatsdaten(db, gleich.id, 2026, 7, netzbezug_kwh=24.0, einspeisung_kwh=0.0)
    await db.commit()

    assert await _netzbezug_kosten(db, ohne, 2026, 7) == pytest.approx(
        await _netzbezug_kosten(db, gleich, 2026, 7)
    )


@pytest.mark.asyncio
async def test_der_monatswert_schlaegt_den_zeittarif(db):
    """Der eingetragene Ø-Preis gewinnt — die P8-Präzedenz bleibt unberührt.

    Das ist der Ausweg für handgetragene Monate (Konzept §4b): Wer den Ø aus
    seiner Abrechnung kennt, trägt ihn ein und braucht keine Stundenwerte.
    """
    a, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    await _stunden(db, a.id, [date(2026, 7, 1)], {20: 1.0, 8: 3.0})
    await factories.monatsdaten(
        db, a.id, 2026, 7, netzbezug_kwh=12.0, einspeisung_kwh=0.0,
        netzbezug_durchschnittspreis_cent=20.0,
    )
    await db.commit()

    assert await _netzbezug_kosten(db, a, 2026, 7) == pytest.approx(12.0 * 20.0 / 100)


# ═══════════════════════════════════════════════════════════════════════
# W-Z4 — kein zweiter Bauort
# ═══════════════════════════════════════════════════════════════════════

def test_wz4_nur_eine_stelle_haelt_ein_fenster_gegen_eine_stunde():
    """``deckt_uhrzeit`` darf baumweit nur aus ``zeittarif.py`` gerufen werden.

    ⚠ **Was er kann und was nicht:** Er zählt Aufrufe der Methode. Wer die
    Fenstergrenzen von Hand vergleicht (``von_stunde <= h < bis_stunde``
    irgendwo im Baum), läuft durch — dafür gibt es die zweite Hälfte unten.
    Beide zusammen decken die wahrscheinliche Form ab; für jede denkbare
    bräuchte es einen AST-Lauf über Vergleichsausdrücke, und das steht in
    keinem Verhältnis.
    """
    import pathlib
    import re

    wurzel = pathlib.Path(__file__).resolve().parents[1]
    erlaubt = {"core/berechnungen/zeittarif.py", "models/strompreis.py"}

    aufrufer, handvergleich = [], []
    for pfad in wurzel.rglob("*.py"):
        rel = pfad.relative_to(wurzel).as_posix()
        if rel.startswith(("tests/", "venv/")):
            continue
        text = pfad.read_text(encoding="utf-8")
        if ".deckt_uhrzeit(" in text and rel not in erlaubt:
            aufrufer.append(rel)
        # Handvergleich gegen die Fenstergrenzen
        if re.search(r"von_stunde\s*<=|<\s*\w*\.?bis_stunde", text) and rel not in erlaubt:
            handvergleich.append(rel)

    assert not aufrufer, (
        f"Zweiter Bauort fuer die Fenster-Pruefung: {aufrufer} — "
        "`preis_je_slot` ist die eine Stelle (N-267)."
    )
    assert not handvergleich, (
        f"Fenstergrenzen von Hand verglichen: {handvergleich} — "
        "`deckt_uhrzeit` benutzen, sonst driftet die Mitternachts-Regel."
    )


@pytest.mark.asyncio
async def test_fenster_haengen_am_tarif_und_werden_mitgeladen(db):
    """``lazy="selectin"`` — ein Lazy-Load bräche in der AsyncSession ab."""
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage

    a, _ = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    db.expunge_all()

    tarife = await lade_tarife_fuer_anlage(db, a.id, target_date=date(2026, 7, 1))
    geladen = tarife["allgemein"]
    assert geladen is not None
    assert [f.von_stunde for f in geladen.zeitfenster] == [19]


@pytest.mark.asyncio
async def test_geloeschter_tarif_nimmt_seine_fenster_mit(db):
    """``delete-orphan`` — sonst bleiben verwaiste Fenster in der Tabelle."""
    a, tarif = await _anlage_mit_tarif(db, ht=30.0, fenster=[_fenster(19, 20, 15.0)])
    assert (await db.execute(select(StrompreisZeitfenster))).scalars().all()

    await db.delete(tarif)
    await db.commit()
    assert not (await db.execute(select(StrompreisZeitfenster))).scalars().all()
