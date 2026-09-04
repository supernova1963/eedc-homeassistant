"""N-386: ein Balkonkraftwerk ohne zugeordnete Module zählt jetzt überall mit.

**Der Defekt.** Der Monats-Daten-Check und ``GET /monatsdaten/{id}`` bildeten
ihre PV-Erzeugung aus ``typ == "pv-module"`` allein, die Monats-Fakten (und
damit *Auswertungen → Tabelle*, Cockpit, Finanzen) aus **Modulen plus
Balkonkraftwerk**. Zwei Sichten desselben Monats nannten verschiedene Zahlen.

⛔ **Der Nenner war schon richtig, der Zähler nicht.** ``monatsdaten.py:471``
bildet die kWp seit F-58 mit ``mit_bkw=True`` — und schreibt als Begründung
dazu: *„weil `pv_erzeugung` unten die anlagenweite Erzeugung ist"*. Genau das
war sie nicht. Gemessen an einer nachgestellten Anlage (Dach-Modul 100 kWh +
Balkonkraftwerk 50 kWh, wahr sind 150): Prüfung 3 meldete bei **120 kWh**
Einspeisung *„Einspeisung > PV-Erzeugung (100)"* — für eine Menge, die die
Anlage erzeugt hatte. Und die genannte Zahl fand der Anwender in keiner Sicht
wieder.

⚑ **Betroffen war nur der historische Erfassungsweg: ein Balkonkraftwerk ohne
zugeordnete PV-Module.** Seit v4.0.18 lassen sich einem BKW Module zuordnen
(N-266) — dessen Kinder sind selbst ``pv-module`` und lagen damit ohnehin in
beiden Mengen. Von vier gemessenen Konstellationen waren drei immer richtig;
diese Datei pinnt alle vier, damit die Reparatur nicht die heilen Fälle bewegt.

⚠ **Warum der P11-Wächter das nicht fangen konnte:** Er erkennt eine Σ-Stelle
daran, dass sie ``PV_ERZEUGER_TYPEN`` bildet, und sichert gegen
**Doppelzählung**. Wer ``typ == "pv-module"`` schreibt, bildet die Menge nie.
Der Fix zieht beide Stellen durch ``erzeuger_traeger`` — das erledigt die
Abtretung **und** macht sie für den Wächter sichtbar.

Schwesterdateien: ``test_bkw_parent_pv_module_n266.py`` (die Wert-Tests der
Abtretung selbst — dort steht, was ``erzeuger_traeger`` leistet),
``test_bkw_erzeuger_sichten_f10.py`` (die String-Sichten, die schon seit F-10
beide Erzeuger-Typen übergeben — das Vorbild für diesen Fix) und
``test_daten_checker_bkw_kind_deckt_f39.py`` (der Daten-Checker auf derselben
BKW-Kind-Achse).
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten

JAHR, MONAT = 2026, 8
DACH_KWH = 100.0
BKW_KWH = 50.0
WAHR = DACH_KWH + BKW_KWH
#: Bewusst ZWISCHEN 100 und 150: unter der wahren Erzeugung, über der
#: schmalen. Genau in diesem Fenster wird der Unterschied sichtbar.
EINSPEISUNG = 120.0


async def _anlage(
    db,
    name: str,
    *,
    bkw_wert: Optional[float],
    kind_werte: Sequence[Optional[float]] = (),
    kinder_ab: date = date(2023, 1, 1),
) -> Anlage:
    """Dach-Modul (100 kWh) + ein Balkonkraftwerk, dessen Kinder frei wählbar sind.

    ``kind_werte`` leer  → BKW **ohne** Modul-Kinder (der historische Weg).
    Ein ``None`` darin   → Kind ohne eigenen Messwert (Lückenfüllung aus dem BKW).
    """
    a = Anlage(anlagenname=name, leistung_kwp=5.0, standort_land="DE")
    db.add(a)
    await db.flush()

    dach = Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Dach", aktiv=True,
        anschaffungsdatum=date(2024, 10, 1), leistung_kwp=4.0,
    )
    db.add(dach)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=dach.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"pv_erzeugung_kwh": DACH_KWH},
    ))

    bkw = Investition(
        anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", aktiv=True,
        anschaffungsdatum=date(2023, 1, 1), leistung_kwp=0.8,
    )
    db.add(bkw)
    await db.flush()
    if bkw_wert is not None:
        db.add(InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=JAHR, monat=MONAT,
            verbrauch_daten={"pv_erzeugung_kwh": bkw_wert},
        ))

    for i, wert in enumerate(kind_werte):
        kind = Investition(
            anlage_id=a.id, typ="pv-module", bezeichnung=f"Balkon-Modul {i + 1}",
            aktiv=True, anschaffungsdatum=kinder_ab, leistung_kwp=0.4,
            parent_investition_id=bkw.id,
        )
        db.add(kind)
        await db.flush()
        if wert is not None:
            db.add(InvestitionMonatsdaten(
                investition_id=kind.id, jahr=JAHR, monat=MONAT,
                verbrauch_daten={"pv_erzeugung_kwh": wert},
            ))

    db.add(Monatsdaten(
        anlage_id=a.id, jahr=JAHR, monat=MONAT,
        einspeisung_kwh=EINSPEISUNG, netzbezug_kwh=30.0,
    ))
    await db.commit()

    geladen = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalars().one()
    await db.refresh(geladen, ["investitionen"])
    return geladen


async def _drei_pfade(db, anlage: Anlage) -> tuple[Optional[float], float, Optional[float]]:
    """Die drei Lesepfade, die alle „PV-Erzeugung des Monats" meinen."""
    from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
    from backend.services.daten_checker import DatenChecker
    from backend.services.monats_fakten import lade_monats_fakten
    from backend.services.pv_monatswerte import lade_pv_je_monat, pv_summe_je_monat

    checker = (await DatenChecker(db)._get_pv_erzeugung_map(anlage)).get((JAHR, MONAT))

    fakt = (await lade_monats_fakten(
        db, anlage.id, von=(JAHR, MONAT), bis=(JAHR, MONAT),
    ))[0]

    # ⛔ Die ECHTE Route rufen, nicht ihren Lesepfad nachbauen. Die erste
    # Fassung dieser Datei baute hier `erzeuger_traeger(...)` selbst nach — der
    # Sprengsatz an `monatsdaten.py` blieb daraufhin stumm, weil die Probe die
    # Datei gar nicht berührte, die sie prüfen sollte. Sie zeigte aufs falsche
    # Objekt und hätte den Defekt nicht gefangen.
    from backend.api.routes.monatsdaten import get_monatsdaten

    md_id = (await db.execute(
        select(Monatsdaten.id).where(
            Monatsdaten.anlage_id == anlage.id,
            Monatsdaten.jahr == JAHR,
            Monatsdaten.monat == MONAT,
        )
    )).scalars().one()
    antwort = await get_monatsdaten(md_id, db)
    # Die Route reicht die PV nicht durch, sie VERRECHNET sie — gemessen wird
    # deshalb die Wirkung: `direktverbrauch = max(0, PV − Einspeisung − Ladung)`.
    # Das ist die Größe, an der Eigenverbrauch, EV-Quote und Autarkie hängen.
    #
    # ⚠ Zurückgegeben wird der ROHE Direktverbrauch, nicht eine daraus
    # zurückgerechnete PV. Die erste Fassung rechnete `direktverbrauch +
    # Einspeisung` — das gilt nur, solange die PV über der Einspeisung liegt.
    # Unterhalb greift das `max(0, …)`, und die Rückrechnung log dann über die
    # Klemmung hinweg. Jede Probe formuliert ihre Erwartung deshalb selbst mit
    # `erwarteter_direktverbrauch()`.
    return checker, fakt.erzeugung.pv_kwh, antwort.kennzahlen.direktverbrauch_kwh


def erwarteter_direktverbrauch(pv_kwh: float) -> float:
    """Was die Route aus einer gegebenen Erzeugung machen MUSS — inkl. Klemmung."""
    return max(0.0, pv_kwh - EINSPEISUNG)


# ══════════════════════════════════════════════════════════════════════════
# 1 · Der Befund: das Balkonkraftwerk OHNE Modul-Kinder
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_bkw_ohne_kinder_zaehlt_in_allen_drei_sichten(db) -> None:
    """Der historische Erfassungsweg — bis N-386 fehlten hier 50 von 150 kWh."""
    anlage = await _anlage(db, "OhneKinder", bkw_wert=BKW_KWH)
    checker, fakten, route = await _drei_pfade(db, anlage)

    assert fakten == pytest.approx(WAHR), (
        "Aufbau-Kontrolle: die Monats-Fakten waren nie betroffen und müssen "
        f"Module + BKW nennen. Erwartet {WAHR}, gefunden {fakten}."
    )
    assert checker == pytest.approx(WAHR), (
        "Der Daten-Check muss dieselbe Anlagen-Erzeugung sehen wie die "
        "Auswertungstabelle. Sonst nennt er dem Anwender eine PV-Zahl, die in "
        f"keiner Sicht steht. Erwartet {WAHR}, gefunden {checker}."
    )
    assert route == pytest.approx(erwarteter_direktverbrauch(WAHR)), (
        "Autarkie, Eigenverbrauchsquote und der Direktverbrauch dieses Monats "
        f"hängen an derselben Erzeugung: {WAHR} − {EINSPEISUNG} = "
        f"{erwarteter_direktverbrauch(WAHR)} kWh. Ohne das Balkonkraftwerk "
        "rechnete die Route `max(0, 100 − 120)` und meldete **0** — der Monat "
        f"sah aus, als wäre nichts direkt verbraucht worden. Gefunden {route}."
    )


@pytest.mark.asyncio
async def test_einspeisung_unter_der_wahren_erzeugung_meldet_nichts(db) -> None:
    """Die Folge, um die es geht — die Falschmeldung selbst.

    120 kWh Einspeisung liegen unter den erzeugten 150, aber über den 100, die
    der Check vor N-386 sah. Die Prüfung darf hier nicht anschlagen.
    """
    from backend.services.daten_checker import DatenChecker

    anlage = await _anlage(db, "Falschmeldung", bkw_wert=BKW_KWH)
    checker = DatenChecker(db)
    pv_map = await checker._get_pv_erzeugung_map(anlage)
    pv = pv_map.get((JAHR, MONAT))

    assert pv is not None and 120.0 <= pv, (
        "Mit der wahren Erzeugung (150) ist eine Einspeisung von 120 plausibel. "
        f"Der Check sieht {pv} — bei 100 meldete er „Einspeisung > PV-Erzeugung“ "
        "an einer Anlage, an der nichts falsch war."
    )


@pytest.mark.asyncio
async def test_zaehler_und_nenner_bleiben_dieselbe_grundgesamtheit(db) -> None:
    """Die F-58-Regel gilt weiter — nur jetzt auf der WEITEN Menge.

    Der spezifische Ertrag ist die eine der sechs Größen, für die der Nenner
    zählt. Zieht man den Zähler auf Module + Balkonkraftwerk und lässt den
    Nenner bei den Modulen, entsteht ein zu hoher spezifischer Ertrag — der
    Fehler, den F-58 an dieser Stelle gerade beseitigt hat, nur in der
    Gegenrichtung. Diese Probe hält beide Seiten zusammen.
    """
    from backend.api.routes.monatsdaten import get_monatsdaten

    anlage = await _anlage(db, "ZaehlerNenner", bkw_wert=BKW_KWH)
    md_id = (await db.execute(
        select(Monatsdaten.id).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().one()
    kennzahlen = (await get_monatsdaten(md_id, db)).kennzahlen

    kwp_weit = 4.0 + 0.8          # Dach-Modul + Balkonkraftwerk
    # `abs=0.1`: die Sicht rundet auf eine Nachkommastelle (31,2 statt 31,25).
    # Die zu prüfende Verwechslung liegt bei 37,5 — sechs Einheiten daneben und
    # von dieser Toleranz weit entfernt.
    assert kennzahlen.spezifischer_ertrag_kwh_kwp == pytest.approx(
        WAHR / kwp_weit, abs=0.1
    ), (
        f"Zähler {WAHR} kWh (Module + BKW) gehört auf den Nenner {kwp_weit} kWp "
        "(Module + BKW). Steht dort nur die Modul-kWp (4,0), meldet die Sicht "
        f"{WAHR / 4.0:.1f} statt {WAHR / kwp_weit:.1f} kWh/kWp — dieselbe "
        "Grundgesamtheits-Verletzung wie vor F-58, nur andersherum. "
        f"Gefunden {kennzahlen.spezifischer_ertrag_kwh_kwp}."
    )


# ══════════════════════════════════════════════════════════════════════════
# 2 · Die drei Konstellationen, die schon vorher richtig waren
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "name,kind_werte",
    [
        ("beide Kinder messen", (30.0, 20.0)),
        ("kein Kind misst — der BKW-Wert füllt beide Lücken", (None, None)),
        ("nur ein Kind misst — der Rest kommt aus dem BKW-Wert", (30.0, None)),
    ],
)
@pytest.mark.asyncio
async def test_bkw_mit_modul_kindern_bleibt_unveraendert(db, name, kind_werte) -> None:
    """Die Reparatur darf die heilen Fälle nicht bewegen.

    Ein BKW mit `pv-module`-Kindern hat seine Erzeugung abgetreten (N-266,
    ADR-002/P11). Nähme der Fix das BKW zusätzlich auf, stünden 200 statt 150 —
    genau die Doppelzählung, gegen die der Selektor gebaut ist.
    """
    anlage = await _anlage(
        db, f"MitKindern-{len(kind_werte)}", bkw_wert=BKW_KWH, kind_werte=kind_werte,
    )
    checker, fakten, route = await _drei_pfade(db, anlage)

    assert (checker, fakten, route) == pytest.approx(
        (WAHR, WAHR, erwarteter_direktverbrauch(WAHR))
    ), (
        f"Konstellation „{name}“: Check und Fakten müssen {WAHR} kWh nennen, "
        f"die Route daraus {erwarteter_direktverbrauch(WAHR)} kWh "
        f"Direktverbrauch. Gefunden Check {checker} / Fakten {fakten} / "
        f"Route {route}. Ein Erzeugungswert von 200 bedeutet, dass das "
        "abgetretene Balkonkraftwerk zusätzlich zu seinen Kindern gezählt wurde."
    )


@pytest.mark.asyncio
async def test_anlage_ohne_balkonkraftwerk_bleibt_bitgleich(db) -> None:
    """Die Gegenprobe: ohne BKW ändert der Selektor nichts.

    Ohne sie wäre nicht gezeigt, dass die Reparatur eng ist — sie könnte
    schlicht jede Anlage anders rechnen.
    """
    from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
    from backend.services.daten_checker import DatenChecker

    a = Anlage(anlagenname="OhneBKW", leistung_kwp=4.0, standort_land="DE")
    db.add(a)
    await db.flush()
    dach = Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Dach", aktiv=True,
        anschaffungsdatum=date(2024, 10, 1), leistung_kwp=4.0,
    )
    db.add(dach)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=dach.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"pv_erzeugung_kwh": DACH_KWH},
    ))
    db.add(Monatsdaten(
        anlage_id=a.id, jahr=JAHR, monat=MONAT,
        einspeisung_kwh=80.0, netzbezug_kwh=30.0,
    ))
    await db.commit()
    anlage = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalars().one()
    await db.refresh(anlage, ["investitionen"])

    assert erzeuger_traeger(anlage.investitionen) == list(anlage.investitionen)
    wert = (await DatenChecker(db)._get_pv_erzeugung_map(anlage)).get((JAHR, MONAT))
    assert wert == pytest.approx(DACH_KWH)


# ══════════════════════════════════════════════════════════════════════════
# 3 · Die Zeitkante, die der Selektor-Docstring selbst benennt
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_kinder_erst_nach_dem_geprueften_monat_angeschafft(db) -> None:
    """Ein BKW, dessen Module ERST SPÄTER dazukamen — was gilt im Monat davor?

    ``abgetretene_bkw_ids`` ist ausdrücklich **ohne** Datumsfilter gebaut
    (*„die Abtretung ist eine Aussage über die Struktur, nicht über einen
    Zeitraum. Wer im Monat 03/2025 rechnet, filtert seine Menge vorher"*). Die
    Monats-Fakten filtern **nicht** vorher — sie bilden die Menge einmal über
    alle Investitionen. Dieser Test hält fest, was daraus für einen Monat vor
    der Modul-Anschaffung folgt.

    ⛔ **Bis 2026-09-04 lieferten alle drei Sichten hier 100,0 statt 150,0
    kWh.** Das Balkonkraftwerk galt als abgetreten, weil seine Kinder in der
    Menge standen — obwohl die im geprüften Monat noch gar nicht angeschafft
    waren. Wer seinem bestehenden BKW Module zuordnete, verlor dessen Erzeugung
    damit **rückwirkend in jedem Vormonat**, in dem es der einzige Erzeuger war.

    ⚠ **Der Fall war unauffällig, weil alle drei Sichten denselben zu kleinen
    Wert nannten** — es gab keinen Widerspruch zu sehen. Eine Probe, die nur
    die Symmetrie prüft, hätte ihn deshalb als „in Ordnung" durchgewinkt; diese
    prüft die **Höhe**.

    Der Fix zieht den Selektor hinter den Zeitfilter — an allen drei Orten, die
    ihn zeitblind anwandten: ``pv_monatswerte.lade_pv_je_monat`` (der SoT, in
    der Monatsschleife), ``monats_fakten`` (je IMD-Zeile) und den beiden
    Aufrufern, die nun die volle Menge übergeben statt vorzufiltern.
    """
    anlage = await _anlage(
        db, "KinderSpaeter", bkw_wert=BKW_KWH, kind_werte=(30.0, 20.0),
        kinder_ab=date(2026, 12, 1),        # nach dem geprüften August
    )
    checker, fakten, route = await _drei_pfade(db, anlage)

    assert (checker, fakten) == pytest.approx((WAHR, WAHR)), (
        "Im August 2026 gibt es die Modul-Kinder noch nicht — das "
        f"Balkonkraftwerk trägt seine {BKW_KWH} kWh hier selbst. Erwartet "
        f"{WAHR} in beiden Sichten, gefunden Check {checker} / Fakten {fakten}. "
        "Ein Wert von 100 bedeutet, dass die Abtretung zeitblind entschieden "
        "wurde und die Erzeugung rückwirkend verschwindet."
    )
    assert route == pytest.approx(erwarteter_direktverbrauch(WAHR)), (
        "Und die Route muss aus genau dieser Erzeugung rechnen. Gefunden "
        f"{route}, erwartet {erwarteter_direktverbrauch(WAHR)}."
    )
