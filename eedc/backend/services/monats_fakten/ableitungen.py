"""Monats-Fakten — Ableitungen für Aufrufer: `FinanzZeileEingabe` aus einem Fakt, Kennzahlen-Summen, der Hinweis
auf unvollständige PV-Monate (N42) und der PV-Ladeanteil (N-314).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from typing import Iterable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen import VerbrauchsKennzahlen, berechne_verbrauchs_kennzahlen
from backend.services.finanz_zeilen import FinanzZeileEingabe
from backend.services.monats_fakten.fakten import MonatsFakt, MonatsSchluessel
from backend.services.monats_fakten.laden import lade_monats_fakten


async def ist_pv_ladeanteil_prozent(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
) -> Optional[float]:
    """Wie viel Prozent der Heimladung kam bisher aus eigener Sonne? (N-188)

    Der **gemessene bzw. abgeleitete IST-Anteil** über den Zeitraum, in Prozent
    — für die Prognose-Achse, die ihn bisher als Handwert mit Default 60 %
    führte. Dieselbe Anlage stand damit auf 60 % in der Prognose und 0 % im IST;
    seit der Ableitung (N-141 Weg c) gibt es einen belegten Wert, und die
    Prognose darf ihn nehmen, statt eine Zahl zu raten.

    ⚠ **Gewichtet über die Ladung, nicht über die Monate.** Ein Monat mit 5 kWh
    Heimladung darf den Jahresanteil nicht so stark bewegen wie einer mit 300.
    Deshalb Σ PV ÷ Σ Ladung und nicht der Mittelwert der Monatsanteile.

    ⚠ **Ein gepflegter Parameter schlägt diesen Wert** — die Entscheidung trifft
    der Aufrufer, nicht diese Funktion. Sie sagt nur, was das IST hergibt.

    ⚠ **Woher die Obergrenze kommt — sie steht NICHT in dieser Funktion.**
    Der Wert ist ein Rechen-**Eingang**: fehlt am Fahrzeug der gepflegte
    Handwert, zieht ``investitionen/roi.py`` ihn als ``pv_anteil_prozent`` in
    die E-Auto-Wirtschaftlichkeit, und ``core/calculations.py`` bildet daraus
    ``netz_anteil = 1 − pv_anteil/100``. Über 100 % würde dieser Faktor negativ
    und das Laden *verdiente* Geld. Dass das nicht passieren kann, ist eine
    **geerbte** Garantie, keine hiesige: ``summiere_emob_quelle`` konstruiert
    ``ladung_kwh`` als ``pv + netz`` (statt das Feld zu lesen), und
    ``get_emob_pv_netz_kwh`` klemmt den abgeleiteten Netz-Anteil mit
    ``max(0, total − pv)``. Damit gilt ``ladung_kwh ≥ pv`` strukturell — auch
    wenn eine erfasste Zeile ``ladung_pv_kwh > ladung_kwh`` trägt (an Anlage 1
    real vorhanden, 2026-06: 100,5 kWh PV bei 86,0 kWh Gesamt). Das war der
    #262-Befund und ist dort gelöst.

    ⚠ **Hier deshalb bewusst KEIN eigener Deckel** (N-314, am Code widerlegt):
    er würde einen Zustand abfangen, den die Schicht darunter nicht mehr
    zulässt, und dabei die echte Garantie verdecken — bräche jemand
    ``get_emob_pv_netz_kwh``, bliebe der Fehler unter dem Deckel unsichtbar.
    Gewächtert wird die Garantie stattdessen dort, wo sie entsteht:
    ``test_n314_pv_ladeanteil_spanne.py``.

    ⚠ **Was davon NICHT gedeckt ist:** dass die widersprüchliche Zeile selbst
    niemandem gemeldet wird. Das ist ein eigener offener Fund (**N-201**,
    fehlende Plausibilitätsregel im Daten-Checker).

    Returns:
        ``0…100``, oder ``None``, wenn im Zeitraum keine Heimladung stattfand —
        „keine Aussage", nicht 0 %.
    """
    fakten = await lade_monats_fakten(db, anlage_id, von=von, bis=bis)
    ladung = sum(f.emob.ladung_kwh for f in fakten)
    if ladung <= 0:
        return None
    return sum(f.emob.ladung_pv_kwh for f in fakten) / ladung * 100

def finanz_zeile_eingabe(fakt: MonatsFakt) -> FinanzZeileEingabe:
    """Übersetzt einen ``MonatsFakt`` in die Eingabe des Finanz-Zeilen-Builders.

    Damit wird ``baue_finanz_zeile`` **Konsument** dieser Schicht: die zwölf
    site-eigenen Dicts, aus denen die vier Finanz-Sichten ihre Zeile bisher jede
    für sich zusammengesetzt haben, entstehen ab jetzt an einer Stelle.

    Zwei Punkte, an denen die Übersetzung nicht beliebig ist:

    - ``pv_erzeugung_kwh`` ist ``erzeugung.hinter_zaehler_kwh`` — Module, BKW
      **und** die sonstigen Erzeuger, weil der Aggregat-Helfer daraus den
      Eigenverbrauch ableitet (P9) und der Zähler am EINEN Netzanschluss die
      Summe aller dahinter liegenden Erzeuger misst.

      ⛔ **Hier stand bis 2026-09-03 ``erzeugung.pv_kwh`` (ohne Sonstiges).** Das
      war eine **Entscheidung** (v3.45.4: „ein Erdgas-BHKW verdrängt Netzbezug,
      aber nicht kostenlos"), gewächtert von zwei Proben und der F-1-Regel.
      ⚑ **Ihre Begründung deckte die Kategorie nie ab** — ein Windrad und eine
      Wasserkraftanlage haben keinen Brennstoff; dort schloss die Regel eine
      tatsächlich kostenlose Kilowattstunde ohne Grund aus dem Geldwert aus.
      Der Entscheid ist —
      **abgelöst am 2026-09-03 durch den Maintainer**, wörtlich: *„Sonstige
      Erzeuger werden nicht wirtschaftlich ausgewertet, und deren produzierter
      Strom geht vollständig in der EV-Ersparnis und Einspeisung auf."* Nicht
      wirtschaftlich ausgewertet heißt: **als Komponente** (keine eigene Zeile,
      Wirtschaftlichkeit „nicht bewertet", Ertrag über „Ertrag/Jahr"); sein Strom
      zählt in der **Anlagen**-Bilanz voll — auf beiden Achsen, Menge wie Geld.

      ⚑ **Die Umsetzung war zusätzlich in sich falsch, und das hat den Anlass
      gegeben:** Der
      Subtrahend derselben Formel ist ``zaehler.einspeisung_kwh`` — der
      **Hauszähler**, der die Einspeisung *aller* Erzeuger misst. Die
      beabsichtigte Abgrenzung (PV-rein) kam damit nur heraus, solange der
      sonstige Erzeuger **nichts einspeiste** — genau der Fall beider damaliger
      Proben. Sobald er einspeist, wurde seine **ganze Erzeugung** von der PV
      abgezogen, nicht etwa sein Eigenverbrauch. An einer Probe-Anlage gemessen (PV 1000, BHKW 200
      davon 150 eingespeist, Hauszähler-Einspeisung 750): Diese Sicht lieferte
      **250 kWh / 75,00 €**, während sie die Menge **450,0 kWh** in derselben
      Zeile auswies — und Cockpit und T-Konto 135,00 € nannten. Weder 450 noch
      400 (Bilanz minus BHKW-Eigenverbrauch), sondern 250: **kein Entscheid
      ergibt diese Zahl.**

      ⚑ **Der geltende Vertrag** (Maintainer, 2026-09-03): *Ein sonstiger
      Erzeuger wird nicht wirtschaftlich ausgewertet — als **Komponente** —, aber
      sein erzeugter Strom geht **vollständig** in der EV-Ersparnis und der
      Einspeisung der **Anlage** auf.* Die Einspeise-Seite tat das schon (sie
      liest den Hauszähler); die Eigenverbrauchs-Seite zieht damit nach.
      ⭐ Und sie liest jetzt dasselbe Feld wie ``kennzahlen_aus_fakten`` weiter
      unten: Menge und Geldwert stimmen **konstruktionsbedingt** überein, nicht
      durch Nachrechnen. Genau das war der Gegenstand von **N-131** und **N-375**.
    - ``bkw_eigenverbrauch_kwh`` ist der **Rest**-Eigenverbrauch aus
      ``bkw_finanz_beitrag``, nie der gemessene Rohwert — sonst zählt derselbe
      Fluss zweimal. ⚠ Unberührt: ``hinter_zaehler_kwh`` ist ``pv_kwh`` **plus**
      ``sonstiges_erzeugung``; das BKW steckt in beiden gleichermaßen, die
      P9-Mechanik ändert sich nicht.
    """
    return FinanzZeileEingabe(
        jahr=fakt.jahr,
        monat=fakt.monat,
        einspeisung_kwh=fakt.zaehler.einspeisung_kwh,
        netzbezug_kwh=fakt.zaehler.netzbezug_kwh,
        pv_erzeugung_kwh=fakt.erzeugung.hinter_zaehler_kwh,
        speicher_ladung_kwh=fakt.speicher.ladung_kwh,
        speicher_entladung_kwh=fakt.speicher.entladung_kwh,
        v2h_entladung_kwh=fakt.emob.v2h_entladung_kwh,
        abgabe_dritte_kwh=fakt.sonstiges.abgabe_kwh,
        bkw_eigenverbrauch_kwh=fakt.bkw.rest_eigenverbrauch_kwh,
        neg_preis_kwh=fakt.eeg.neg_preis_kwh,
        monatsdaten=fakt.meta.monatsdaten,
    )

def kennzahlen_aus_fakten(fakten: Iterable[MonatsFakt]) -> VerbrauchsKennzahlen:
    """Verbrauchs-Kennzahlen über MEHRERE Monate — Mengen summieren, dann rechnen.

    **Nicht dasselbe wie die Summe der Monats-Kennzahlen**, und der Unterschied
    ist keine Rundung: ``direktverbrauch = max(0, PV − Einspeisung − Ladung)``
    klemmt bei 0. Monatsweise geklemmt und dann summiert kommt ein anderer (in der
    Regel höherer) Eigenverbrauch heraus als aus den Perioden-Summen. Die vier
    Finanz-Sichten rechnen heute über die Perioden-Summen — genau das tut diese
    Funktion, damit ein Umhängen auf die Schicht keine Zahl **still** verschiebt.
    Wer die Monatszahl braucht, nimmt ``fakt.kennzahlen``.
    """
    fakten = list(fakten)
    return berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=sum(f.erzeugung.hinter_zaehler_kwh for f in fakten),
        einspeisung_kwh=sum(f.zaehler.einspeisung_kwh for f in fakten),
        netzbezug_kwh=sum(f.zaehler.netzbezug_kwh for f in fakten),
        speicher_ladung_kwh=sum(f.speicher.ladung_kwh for f in fakten),
        speicher_entladung_kwh=sum(f.speicher.entladung_kwh for f in fakten),
        v2h_entladung_kwh=sum(f.emob.v2h_entladung_kwh for f in fakten),
        abgabe_dritte_kwh=sum(f.sonstiges.abgabe_kwh for f in fakten),
    )

def pv_erzeugungs_monate(fakten: Iterable[MonatsFakt]) -> set[MonatsSchluessel]:
    """Die Monate, in denen die Anlage PV erzeugt hat — der Nenner des spezifischen Ertrags.

    Ein Monat zählt, wenn die Modul-Auflösung einen Eintrag hat (gemessen, über den
    Anlagenwert verteilt oder als Lücke), ein Balkonkraftwerk einen eigenen Wert > 0
    meldet oder ein Balkonkraftwerk ohne eigenen Wert seinen Anteil am gespeicherten
    Anlagenwert trägt (N-621, ``ErzeugungFakten.bkw_aus_anlagenwert_kwh``). Ein Monat
    ohne jede dieser Spuren trägt 0 zur PV-Summe bei und würde als Nenner-Monat den
    Jahreswert verzerren.

    ⭐ **Eine Stelle für die Kachel und den HA-Sensor** (N-621 H1, Entscheid des Masters
    04.10.2026): *Cockpit → Übersicht* (``cockpit/uebersicht.py``) und der HA-Sensor
    ``spezifischer_ertrag_kwh_kwp`` (``ha_export/anlage_energie.py``) nennen für dieselbe
    Anlage denselben Wert, also dieselbe Monatsmenge. Bis dahin zählte der HA-Export nur
    Monate mit Modul-Eintrag: eine reine Balkonkraftwerk-Anlage stand dort bei 143,75
    statt 586,73 kWh/kWp (Übersicht), und mit dem BKW-Anteil aus N-621 allein wären es
    1 105,77 geworden.

    Nicht dieselbe Frage wie ``hat_pv_imd`` in ``api/routes/monatsdaten.py``: dort geht es
    je **Zeile** um „Wert oder Lücke anzeigen" (P4, ``None`` statt 0) — eine BKW-Zeile mit
    gepflegter 0 und die Tagesebene zählen dort mit, hier nicht.
    """
    return {
        f.schluessel for f in fakten
        if f.erzeugung.pv_je_modul
        or f.bkw.erzeugung_kwh > 0
        or f.erzeugung.bkw_aus_anlagenwert_kwh > 0
    }

def pv_unvollstaendig_monate(fakten: Iterable[MonatsFakt]) -> list[MonatsSchluessel]:
    """Die Monate, deren PV-Achse eine **Teilsumme** ist — chronologisch.

    ``pv_vollstaendig is False`` heißt: mindestens ein im Monat aktives Modul
    hat keinen Wert und es gibt kein Anlagen-Aggregat, das die Lücke füllt
    (``pv_summe_je_monat`` → ``None``). ``ErzeugungFakten.pv_kwh`` trägt dann
    die vorhandenen Werte (seit N-626: die gemessenen Module plus Balkonkraftwerk;
    bis 04.10.2026 fiel die ganze Modulsumme weg und mit einem BKW stand dessen
    Erzeugung allein da) — eine Teilsumme. Sie ist nie zu hoch; ob sie zu niedrig
    ist, hängt am fehlenden Modul: war es im Monat wirklich außer Betrieb, stimmt
    sie (Gernot zu N-626, 04.10.2026: ein Modul-Ausfall kann auch korrekt sein).
    """
    return [
        (f.jahr, f.monat) for f in fakten if not f.erzeugung.pv_vollstaendig
    ]

def pv_unvollstaendig_hinweis(fakten: Iterable[MonatsFakt]) -> Optional[str]:
    """**Der eine Satz**, mit dem eine Sicht eine PV-Teilsumme beschriftet.

    ``None`` heißt „vollständig" — die Sicht rendert dann nichts.

    Warum es diese Funktion gibt und nicht je Route einen eigenen Satz: Das
    Flag ``ErzeugungFakten.pv_vollstaendig`` wurde gesetzt, getestet — und von
    **keiner** Route gelesen (0 Treffer in ``backend/api``, gemessen 29.08.2026).
    Genau das nennt ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` §2.4 den
    schärfsten Einzelbefund der Inventur: *ein Provenance-Flag ohne Leser ist
    kein Provenance.* §3 Regel 2 verlangt deshalb: wer eines einführt, liefert
    es im selben Schritt aus.

    **Beschriften, nicht unterdrücken** — ``pv_kwh`` ist eine **additive Summe**
    und damit nie zu hoch (§3): fehlt dem Modul Erzeugung, ist sie zu niedrig;
    war es wirklich außer Betrieb, stimmt sie (N-626). Der Satz sagt deshalb
    beides, bedingt — nicht mehr „zu niedrig" schlechthin. Der Nutzer weiß, in
    welche Richtung er korrigieren muss; eine Unterdrückung nähme ihm eine
    brauchbare Zahl. Die Gegenprobe steht eine Ebene tiefer: ``tagesbilanz`` unterdrückt
    ``eigenverbrauch``, weil das eine **Differenz** ist.

    ⛔ **Ausdrücklich KEIN zweiter Melder.** Dass PV-Werte fehlen, meldet der
    Daten-Checker längst (``daten_checker/energieprofil.py::_check_pv_erzeugung``
    → WARNING „PV-Erzeugung unvollständig in N Monat(en)", ERROR „PV-Erzeugung
    fehlt"), samt Link auf den Monatsabschluss. Diese Funktion baut daneben
    keine zweite Befundliste auf, sondern beantwortet die andere Frage: der
    Checker sagt *„was musst du nachtragen?"* (anlagenweit, mit Reparaturweg),
    die Beschriftung sagt *„worauf beruht **diese** Zahl?"* (genau der gezeigte
    Zeitraum, am Wert). Das ist die Zuständigkeitsgrenze aus §4 des Konzepts —
    und die Trennung, die beim Rückbau von N-346 gerissen war: dort stand eine
    **zweite Kategorie** über einem schon gemeldeten Sachverhalt.
    """
    monate = pv_unvollstaendig_monate(fakten)
    if not monate:
        return None
    namen = ", ".join(f"{m:02d}/{j}" for j, m in monate[:6])
    if len(monate) > 6:
        namen += f" (+{len(monate) - 6} weitere)"
    return (
        f"Die PV-Erzeugung ist in {len(monate)} Monat(en) eine Teilsumme "
        f"({namen}): dort fehlt mindestens einem Modul der Monatswert und es gibt "
        "keinen Gesamtwert zum Verteilen. War das Modul in diesem Monat wirklich "
        "außer Betrieb, stimmt die Zahl; sonst fehlt seine Erzeugung — in der "
        "PV-Erzeugung, im spezifischen Ertrag und im daraus gerechneten Ertrag."
    )
