"""B2 — ein Wetterwert wird nicht aus der Historie geschätzt.

**Der Befund, gemessen am 29.09.2026** (Paket „Die Wetterreihe geradeziehen",
#395 Punkt 1). ``VorschlagService.get_vorschlaege`` lieferte für jedes
Nicht-Stand-Feld den **Vormonatswert** mit Konfidenz 80, und
``MonatsdatenForm.tsx`` füllte damit **jedes leere** Basis-Feld vor. Für die
drei Wetterfelder ist das doppelt falsch:

1. *Sachlich.* Ein Wetterwert ist die Messung EINES Monats. Der Vormonat, das
   Vorjahr und der Zwölf-Monats-Schnitt beschreiben andere Monate — für dieses
   Feld sind sie keine Schätzung, sondern eine fremde Messung. Dieselbe
   Begründung, mit der ``ist_stand_feld`` seit 05.09.2026 dieselben drei
   Quellen ausschließt, nur aus der anderen Richtung: dort ist der Vormonat der
   **Anfang** des Werts, hier ist er schlicht ein **anderer** Wert.

2. *In der Wirkung schlimmer.* Beide Speicherwege stempeln jedes gesendete Feld
   als ``manual:form`` = ``SourcePriority.MANUAL`` mit dem Vermerk „Niemals von
   Maschine überschreiben" (FrodoVDR #251). **Ein Wert, den niemand getippt
   hat, trug damit den Stempel einer Handeingabe und war gegen jede externe
   Quelle verriegelt.** An einer echten Anlage gemessen: 4 von 38 Monatspaaren
   in **beiden** Wetterfeldern identisch; für 2026-02 stand 44,0 h, wo der
   Dienst 70,8 h sagt — 38 % zu niedrig.

**Warum am Backend und nicht am Prefill-Loop des Formulars:** eine Wahrheit.
Das Formular erbt daraus automatisch — das Feld bleibt leer, der Wetter-Knopf
sieht wieder eine **Lücke** und füllt sie (er füllt seit N-426 nur noch
Lücken, und ein vorbelegtes Feld ist keine). Damit heilt B2 die Ursache und
nicht das Symptom.

⚠ **Die Gegenrichtung gehört dazu.** Genau **fünf** Felder bekamen am offenen
Monat einer echten Anlage ``vormonat`` als besten Vorschlag: die drei
Wetterfelder und die beiden externen Ladefelder am E-Auto. Die zwei letzten
sind Mengen desselben Haushalts und behalten ihren Vorschlag — eine Regel, die
sie mitnähme, wäre zu weit gefasst.

Schwesterdateien: ``test_wetter_lueckenschluss.py`` (was den weggefallenen
Vorschlag ersetzt — ohne sie wäre diese Datei ein Rückschritt) ·
``test_wetterreihe_ein_lineal.py`` (warum der Wert überhaupt eine Quelle
braucht) · ``test_wetter_nachzug_und_checker.py`` (wie der Altbestand
geradegezogen wird).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.field_definitions import WETTER_FELDER, ist_wetter_feld
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.vorschlag_service import VorschlagQuelle, VorschlagService

JAHR, MONAT = 2026, 3

#: Die drei Felder, um die es geht — als Literal, damit die Probe nicht
#: dieselbe Ableitung prüft, die sie beweisen soll.
DIE_DREI = {"globalstrahlung_kwh_m2", "sonnenstunden", "durchschnittstemperatur"}

#: Die Quellen, die eine HISTORIE befragen. Eine Rechnung oder ein
#: mitgeschriebener Messwert bleibt erlaubt und ist nicht gemeint.
HISTORIE = {
    VorschlagQuelle.VORMONAT,
    VorschlagQuelle.VORJAHR,
    VorschlagQuelle.DURCHSCHNITT,
}


async def _anlage_mit_historie(db) -> Anlage:
    """Eine Anlage, deren Vorgeschichte für JEDE Historien-Quelle reicht.

    Vierzehn Monate zurück — sonst käme der Ø-12-Monate-Vorschlag ohnehin nicht
    zustande (er verlangt mindestens drei Werte), und die Probe wäre grün, ohne
    etwas gemessen zu haben.
    """
    a = Anlage(anlagenname="Historie", leistung_kwp=10.0, latitude=50.9, longitude=7.5)
    db.add(a)
    await db.flush()

    jahr, monat = JAHR, MONAT
    for i in range(1, 15):
        monat -= 1
        if monat == 0:
            jahr, monat = jahr - 1, 12
        db.add(Monatsdaten(
            anlage_id=a.id, jahr=jahr, monat=monat,
            einspeisung_kwh=100.0 + i, netzbezug_kwh=50.0 + i,
            globalstrahlung_kwh_m2=100.0 + i,
            sonnenstunden=200.0 + i,
            durchschnittstemperatur=10.0 + i,
        ))
    await db.flush()
    await db.commit()
    return a


# ══════════════════════════════════════════════════════════════════════════
# 0 · Vorbedingung — die Ableitung trifft genau die drei Felder
# ══════════════════════════════════════════════════════════════════════════


def test_die_gruppe_wetter_traegt_genau_diese_drei_felder():
    """Ohne diese Klausel prüften alle anderen eine Menge, die sie nicht kennen.

    Kommt ein viertes Wetterfeld in die Registry, meldet diese Probe es — und
    der Bauer entscheidet bewusst, ob die Regel für es gilt, statt es
    stillschweigend mitzunehmen.
    """
    assert set(WETTER_FELDER) == DIE_DREI, (
        f"Gruppe „wetter\" in der Registry: {sorted(WETTER_FELDER)}"
    )
    for feld in DIE_DREI:
        assert ist_wetter_feld(feld) is True, feld
    for feld in ("einspeisung_kwh", "netzbezug_kwh", "ladung_extern_kwh", "", "sonne"):
        assert ist_wetter_feld(feld) is False, feld


# ══════════════════════════════════════════════════════════════════════════
# 1 · Kein Historien-Vorschlag für ein Wetterfeld
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("feld", sorted(DIE_DREI))
async def test_kein_vormonats_vorschlag_fuer_wetterfelder(db, feld):
    """Der Kern des Funds: die Historie schlägt für dieses Feld nichts vor."""
    a = await _anlage_mit_historie(db)
    dienst = VorschlagService(db)

    vorschlaege = await dienst.get_vorschlaege(a.id, feld, JAHR, MONAT)

    aus_historie = [v for v in vorschlaege if v.quelle in HISTORIE]
    assert not aus_historie, (
        f"{feld}: {[(v.quelle.value, v.wert, v.konfidenz) for v in aus_historie]} — "
        "ein Wetterwert ist die Messung eines ANDEREN Monats. Im Formular "
        "vorbelegt bekäme er den Stempel `manual:form` und wäre gegen jede "
        "Korrektur verriegelt."
    )


@pytest.mark.asyncio
async def test_die_vorgeschichte_reicht_wirklich(db):
    """Gegenprobe zur Probe: an einem Mengenfeld liefert dieselbe DB alle drei.

    Ohne sie könnte die Klausel darüber grün sein, weil schlicht keine
    Vorgeschichte da ist — und der Defekt stünde unentdeckt daneben.
    """
    a = await _anlage_mit_historie(db)
    dienst = VorschlagService(db)

    vorschlaege = await dienst.get_vorschlaege(a.id, "einspeisung_kwh", JAHR, MONAT)

    quellen = {v.quelle for v in vorschlaege}
    assert HISTORIE <= quellen, (
        f"Erwartet Vormonat + Vorjahr + Ø 12 Monate, bekommen {sorted(q.value for q in quellen)}"
    )


# ══════════════════════════════════════════════════════════════════════════
# 2 · Gegenrichtung — die E-Auto-Felder behalten ihren Vorschlag
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("feld", ["ladung_extern_kwh", "ladung_extern_euro"])
async def test_eauto_behaelt_seinen_vormonats_vorschlag(db, feld):
    """Die beiden anderen Felder der ``vormonat``-Klasse sind NICHT gemeint.

    Sie sind Mengen desselben Haushalts — der Vormonat ist dafür eine
    brauchbare Schätzung und das übliche Verhalten. Eine Regel, die sie
    mitnähme, wäre an der Kategorie vorbeiformuliert.
    """
    a = Anlage(anlagenname="E-Auto", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=30000.0, aktiv=True,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=JAHR, monat=MONAT - 1,
        verbrauch_daten={feld: 42.0},
    ))
    await db.flush()
    await db.commit()

    vorschlaege = await VorschlagService(db).get_vorschlaege(
        a.id, feld, JAHR, MONAT, investition_id=inv.id
    )

    vormonat = [v for v in vorschlaege if v.quelle is VorschlagQuelle.VORMONAT]
    assert vormonat, (
        f"{feld} hat seinen Vormonats-Vorschlag verloren — die Wetter-Regel "
        "greift zu weit."
    )
    assert vormonat[0].wert == pytest.approx(42.0)
