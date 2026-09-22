"""Sizing und Speicher-Potential rechnen mit den HEUTE laufenden Speichern (N-546).

**Der Fall, und er ist eine richtige Erfassung** (Radiocarbonat, T89667 #358):
Wer seinen alten Speicher gegen einen neuen tauscht, legt nach unserer Anleitung
das alte Gerät mit **Stilllegungsdatum** an und das neue daneben. Beide Sichten
holten bis zum 2026-09-22 **alle** Investitionen vom Typ Speicher — ohne `aktiv`,
ohne `stilllegungsdatum`. Beim Melder stand deshalb 15,3 kWh statt 10,24 kWh in
der Basis; der Unterschied ist exakt das ausgebaute Gerät.

Getroffen sind drei Größen derselben Faltung, und die zweite ist die
unauffälligste: **Kapazität** (Summe), **Wirkungsgrad** (`aggregiere_speicher_basis`
nimmt das **Minimum** — ein ausgemusterter Speicher mit 85 % zieht die Basis
dauerhaft herunter, auch wenn er im Keller nicht mehr steht) und **Leer-Schwelle**
(aus dem Verhältnis netto zu brutto, also aus **beiden** Summen).

**Stichtag ist `date.today()`, nicht das Fenster-Ende** (Entscheid 2026-09-22):
Beide Sichten fragen nach vorn — „lohnt sich ein größerer Speicher?" und „was
hätte ein größerer gebracht?" beziehen sich auf das Gerät, das **heute** dasteht;
die Stundenhistorie liefert nur das Verbrauchs- und PV-Muster. Dieselbe Begründung
trägt schon der Tarif im Modul-Docstring von `speicher_sizing_service.py`.

Die Zahlen der Probe sind die des Melders (10,24 + 5,06 = 15,3).
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.api.routes.investitionen import (
    get_speicher_potential,
    get_speicher_sizing,
)
from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil

#: Der laufende Speicher: 12,8 kWh brutto, 10,24 kWh nutzbar (die Melder-Zahl),
#: 95 % Wirkungsgrad. Daraus leitet sich die Leer-Schwelle ab
#: (`leer_schwelle_prozent`, 3 pp Toleranz): **23,0 %** im Sizing (rechnet mit
#: den rohen Summen), **23,3 %** im Potential (rechnet mit den auf eine
#: Nachkommastelle **gerundeten** Kapazitäten — Bestand, hier nicht angefasst).
LAUFEND = {"kapazitaet_kwh": 12.8, "nutzbare_kapazitaet_kwh": 10.24,
           "wirkungsgrad_prozent": 95}
#: Das abgelöste Gerät: 5,06 kWh, 85 % — beides so gewählt, dass es in **jeder**
#: der drei Größen sichtbar würde. Summe netto 15,3 (die falsche Zahl des
#: Melders), Summe brutto 17,86 ⇒ Leer-Schwelle **17,3 %** (Sizing, aus
#: 15,3/17,86) bzw. **17,5 %** (Potential, aus den gerundeten 15,3/17,9).
ABGELOEST = {"kapazitaet_kwh": 5.06, "nutzbare_kapazitaet_kwh": 5.06,
             "wirkungsgrad_prozent": 85}

#: ⚠ **Feste Daten, kein `date.today()` in dieser Probe** — der Wächter
#: `test_konformitaet_echte_uhr_in_tests.py` verlangt es, und er hat recht:
#: eine Probe, die die Prozessuhr liest, wettet auf den Tag ihres Laufs und
#: gibt in Berlin, UTC und Auckland nicht zwingend dieselbe Antwort. Der
#: Prüfling ruft `date.today()` selbst; ein Datum weit davor bzw. weit danach
#: entscheidet den Vergleich in **jeder** Zone gleich.
STILLGELEGT_VERGANGENHEIT = date(2021, 3, 31)
STILLGELEGT_ZUKUNFT = date(2099, 12, 31)


async def _seed(db, *, zweites: dict | None = None, aktiv: bool = True,
                stillgelegt: date | None = None) -> int:
    """Eine Anlage, der laufende Speicher — und optional ein zweites Gerät."""
    anlage = Anlage(anlagenname="N-546", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher neu",
        anschaffungsdatum=date(2025, 6, 1), parameter=dict(LAUFEND),
    ))
    if zweites is not None:
        db.add(Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher alt",
            anschaffungsdatum=date(2015, 1, 1), parameter=dict(zweites),
            aktiv=aktiv, stilllegungsdatum=stillgelegt,
        ))
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=35.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    return anlage.id


def _tag(db, anlage_id: int, tag: date, *, soc: float | None = None):
    """Ein vollständiger Tag: PV am Mittag, Grundlast rund um die Uhr.

    ``soc`` setzt den **Tiefpunkt**: die Nachtstunden tragen ihn, tagsüber
    stehen 80 %. Kein `batterie_kw` — die Kalibrierung soll ausdrücklich nicht
    greifen, damit die Antwort die **gepflegte** Basis zeigt.
    """
    for h in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=h,
            pv_kw=6.0 if 10 <= h < 16 else 0.0, verbrauch_kw=0.7,
            soc_prozent=None if soc is None else (80.0 if 10 <= h < 16 else soc),
        ))


async def _sizing(db, anlage_id: int, **kw):
    """Wie FastAPI rufen würde — mit ALLEN Query-Parametern (s. `_sizing` in
    `test_speicher_sizing_route.py`: ein weggelassener trägt das `Query`-Objekt)."""
    vorgabe = {"von": None, "bis": None, "richtpreis_eur_je_kwh": None}
    return await get_speicher_sizing(anlage_id, **{**vorgabe, **kw}, db=db)


async def _potential(db, anlage_id: int, **kw):
    vorgabe = {"von": None, "bis": None}
    return await get_speicher_potential(anlage_id, **{**vorgabe, **kw}, db=db)


# ── (a)+(b)+(d) Sizing: Kapazität, Wirkungsgrad, Anzahl ─────────────────────


async def test_sizing_basis_ist_nur_der_laufende_speicher(db):
    """10,24 statt 15,3 — und 95 % statt 85 %.

    Der Wirkungsgrad ist der schärfere der beiden Belege: er ist ein
    **Minimum**, also nicht einmal proportional zur Kapazität. Ein Prüfer, der
    nur die Summe misst, bliebe bei einem ausgebauten Gerät **gleicher** Größe
    stumm.
    """
    anlage_id = await _seed(db, zweites=ABGELOEST, stillgelegt=STILLGELEGT_VERGANGENHEIT)
    for i in range(30):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.gepflegte_kapazitaet_kwh == 10.2, "Σ netto nur des laufenden Geräts"
    assert antwort.basis_kalibriert is False, "ohne SoC-Bewegung gilt die gepflegte Basis"
    assert antwort.basis_kapazitaet_kwh == 10.2
    assert antwort.gepflegter_wirkungsgrad_prozent == 95.0, (
        "das Minimum darf den ausgebauten Speicher nicht mehr sehen"
    )
    assert antwort.anzahl_speicher == 1
    heute = next(p for p in antwort.kurve if p.faktor == 1.0)
    assert heute.kapazitaet_kwh == 10.2, "auch die Kurve steht auf der gefilterten Basis"


# ── (c) Sizing: Leer-Schwelle ───────────────────────────────────────────────


async def test_sizing_leer_schwelle_kommt_aus_dem_laufenden_geraet(db):
    """Der Tiefpunkt 20 % ist „leer" für 12,8/10,24 — und nicht für die Summe.

    Die Schwelle steht in keiner Antwort-Zahl; sie wirkt über
    `soc_nutzung.tage_bis_leer`. Gefiltert: 23,0 % ⇒ 20 % zählt als leer (3 von
    3 Tagen). Ungefiltert wären es 17,3 % ⇒ 0 Tage — und die Sicht behauptete,
    dieser Speicher werde nie aufgebraucht.
    """
    anlage_id = await _seed(db, zweites=ABGELOEST, stillgelegt=STILLGELEGT_VERGANGENHEIT)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i), soc=20.0)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.soc_nutzung is not None
    assert antwort.soc_nutzung.tage_mit_soc == 3
    assert antwort.soc_nutzung.tage_bis_leer == 3


# ── (a)+(c)+(d) Potential ───────────────────────────────────────────────────


async def test_potential_kapazitaeten_und_schwelle_nur_vom_laufenden_geraet(db):
    anlage_id = await _seed(db, zweites=ABGELOEST, stillgelegt=STILLGELEGT_VERGANGENHEIT)
    for h in range(10, 14):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=date(2026, 6, 10), stunde=h,
            soc_prozent=100.0, einspeisung_kw=5.0,
        ))
    await db.commit()

    antwort = await _potential(db, anlage_id)

    assert antwort.kapazitaet_kwh == 10.2, "netto: 15,3 wäre die Melder-Zahl"
    assert antwort.kapazitaet_brutto_kwh == 12.8, "brutto: 17,9 wäre sie ungefiltert"
    assert antwort.soc_leer_prozent == 23.3, "ungefiltert wären es 17,5"
    assert antwort.soc_leer_ist_abgeleitet is True
    assert antwort.anzahl_speicher == 1


# ── (e) Gegenrichtung: Stilllegung in der Zukunft ───────────────────────────


async def test_stilllegung_in_der_zukunft_zaehlt_heute_noch_mit(db):
    """Angekündigt ist nicht ausgebaut — sonst wäre der Filter ein Datumsfehler.

    Ohne diesen Fall bliebe unbelegt, dass der **Stichtag** gelesen wird und
    nicht bloß die Anwesenheit eines Datums.
    """
    anlage_id = await _seed(db, zweites=ABGELOEST, stillgelegt=STILLGELEGT_ZUKUNFT)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i), soc=20.0)
    await db.commit()

    sizing = await _sizing(db, anlage_id)
    potential = await _potential(db, anlage_id)

    assert sizing.gepflegte_kapazitaet_kwh == 15.3
    assert sizing.gepflegter_wirkungsgrad_prozent == 85.0
    assert sizing.anzahl_speicher == 2
    assert sizing.soc_nutzung is not None
    assert sizing.soc_nutzung.tage_bis_leer == 0, "Schwelle 17,3 % ⇒ 20 % ist nicht leer"

    assert potential.kapazitaet_kwh == 15.3
    assert potential.kapazitaet_brutto_kwh == 17.9
    assert potential.soc_leer_prozent == 17.5
    assert potential.anzahl_speicher == 2


# ── (f) Abgewählt ohne Datum ────────────────────────────────────────────────


async def test_abgewaehltes_geraet_ohne_stilllegungsdatum_zaehlt_nicht(db):
    """`aktiv = False` ist der zweite Weg, ein Gerät aus dem Betrieb zu nehmen."""
    anlage_id = await _seed(db, zweites=ABGELOEST, aktiv=False, stillgelegt=None)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i))
    await db.commit()

    sizing = await _sizing(db, anlage_id)
    potential = await _potential(db, anlage_id)

    assert sizing.gepflegte_kapazitaet_kwh == 10.2
    assert sizing.gepflegter_wirkungsgrad_prozent == 95.0
    assert sizing.anzahl_speicher == 1
    assert potential.kapazitaet_kwh == 10.2
    assert potential.anzahl_speicher == 1


# ── (g) Leere Antwort ───────────────────────────────────────────────────────


async def test_ohne_stundendaten_traegt_auch_die_leere_antwort_die_gefilterte_basis(db):
    """Der zweite `return` des Service ist eine eigene Konstruktion (`:217`).

    Er wurde beim Bau des Filters nicht angefasst — genau deshalb steht er hier:
    beide Rückgabewege tragen `anzahl_speicher` und die gepflegten Größen.
    """
    anlage_id = await _seed(db, zweites=ABGELOEST, stillgelegt=STILLGELEGT_VERGANGENHEIT)
    await db.commit()

    antwort = await _sizing(db, anlage_id)

    assert antwort.kurve == []
    assert antwort.tage_mit_daten == 0
    assert antwort.gepflegte_kapazitaet_kwh == 10.2
    assert antwort.gepflegter_wirkungsgrad_prozent == 95.0
    assert antwort.anzahl_speicher == 1
