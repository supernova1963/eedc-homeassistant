"""Die Bezugspreis-Reihen des HA-Exports — Eingänge sammeln, nicht rechnen.

Die Formeln stehen im Layer (`core/berechnungen/preis_reihe.py`, ADR-001); hier
wird geholt, was sie brauchen: die Tarifzeile zum Stichtag **heute und morgen**,
die Börse auf der backward-Achse, die Einspeisevergütung des laufenden Monats
und — für einen dynamischen Tarif — der **abgeleitete** Aufschlag.

## Warum „heute UND morgen" (ADR-002/P8)

Die Achse des Fenster-Kontexts reicht bis morgen 23 Uhr. Ein Tarifwechsel zum
Monatsersten liegt damit regelmäßig **mitten** in der Reihe: Wer für beide Tage
den heutigen Tarif nähme, zeigte für morgen einen Preis, der morgen nicht mehr
gilt — und ein Fenster über Mitternacht würde am falschen Preis gemessen.
`lade_tarife_je_stichtag` beantwortet beide Stichtage in **einer** Abfrage.

## Warum der Aufschlag abgeleitet wird und nicht gepflegt

Entscheid Gernot, 22.09.2026 („Probieren wir es"). Die Annahme ist schmal:
*Endpreis = (1 + USt) × Börse + ein über den Zeitraum konstanter Anteil.* Sie
braucht kein Tarifmodell und kein neues Pflegefeld, nur zwei Zahlen, die eedc
ohnehin hat. Drei Stufen, jede nennt sich selbst (`aufschlag_quelle`):

1. **Abrechnung** — der jüngste Monat mit `Monatsdaten.netzbezug_durchschnittspreis_cent`,
   dessen Erster **im Tarifzeitraum** liegt (P8: ein Ø aus der Zeit vor dem
   Tarifwechsel beschreibt einen anderen Vertrag). Gegengerechnet wird das
   **verbrauchsgewichtete** Börsenmittel desselben Monats.
2. **Sensor** — die letzten 7 Tage, in denen `strompreis_cent` **und**
   `boersenpreis_cent` in derselben Zeile des Tagesprofils stehen. Beide liegen
   **forward** (N-387) und sind deshalb ohne Verschiebung paarbar; ≥ 24 Paare,
   Median.
3. **keiner** — dann bleibt die nackte Börse als beschriftete Näherung.

⚠ **Der Bezug einer Stunde liegt backward, die Börse forward** — für Stufe 1
werden sie über `slot_konvention.forward_stunde_zu_backward_slot` gepaart. Für
Stufe 2 nicht: dort stehen **beide** Größen forward in derselben Zeile.

## Memoisierung

Der abgeleitete Aufschlag kostet zwei Abfragen und im schlechtesten Fall einen
Marktabruf. Er ändert sich im Tagesverlauf nicht (die Abrechnung des Vormonats
ist fix, der 7-Tage-Median bewegt sich um Hundertstel), der Publish-Takt liegt
aber bei bis zu 5 Minuten. Deshalb ein Prozess-Cache je
``(anlage_id, tarif_id, heute)`` — der Tageswechsel setzt ihn von selbst zurück,
weil das Datum im Schlüssel steht.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select

from backend.core.berechnungen.preis_reihe import (
    MINDEST_PAARE,
    PreisReihe,
    aufschlag_aus_abrechnung,
    aufschlag_aus_stunden,
    bezugspreis_reihe,
    boersenmittel_gewichtet,
    ist_dynamisch,
)
from backend.core.berechnungen.slot_konvention import forward_stunde_zu_backward_slot
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

#: So viele Tage weit sucht Stufe 2 nach gemessenen Stunden.
SENSOR_FENSTER_TAGE = 7

#: Ab dieser Abdeckung gilt das Börsenprofil eines Abrechnungsmonats als
#: brauchbar. Darunter wird **einmal** nachgeholt (s. `_boersenmittel_monat`):
#: ein Monat, in dem nur drei Tage Börsenstunden tragen, ergäbe ein Mittel über
#: drei Tage und damit einen Aufschlag, der die anderen 28 nicht beschreibt.
MINDEST_ABDECKUNG = 0.8

#: Prozess-Cache: (anlage_id, tarif_id, heute) → Aufschlag | None.
_aufschlag_cache: dict[tuple, "Optional[Aufschlag]"] = {}

#: Welche Monate in diesem Prozess schon einen Marktabruf ausgelöst haben —
#: (anlage_id, jahr, monat). Höchstens **einer** je Monat und Prozess: ein
#: fehlgeschlagener Abruf darf nicht bei jedem Publish-Takt wiederholt werden.
_markt_nachgeholt: set[tuple] = set()


@dataclass(frozen=True)
class Aufschlag:
    """Der abgeleitete Aufschlag brutto samt seiner Herkunft."""

    cent: float
    #: `abrechnung <JJJJ-MM>` · `sensor <n> tage`
    quelle: str
    #: Womit gerechnet wurde — Börsenmittel (Stufe 1) bzw. Paarzahl (Stufe 2).
    basis: str


@dataclass(frozen=True)
class Bezugspreise:
    """Was die Sensoren und der Fenster-Kontext an Preisen brauchen."""

    allgemein: PreisReihe
    waermepumpe: PreisReihe
    #: Einspeisevergütung ct/kWh des laufenden Monats, oder `None`.
    verguetung_cent: Optional[float]
    #: `vertrag` · `monatswert` — oder der **Grund**, wenn es keine gibt.
    verguetung_quelle: Optional[str]
    verguetung_grund: Optional[str]
    #: Trägt der Tarif `einspeisung_variabel`?
    einspeisung_variabel: bool
    #: Der Aufschlag, wenn einer abgeleitet werden konnte (nur dynamisch).
    aufschlag: Optional[Aufschlag]
    #: `Anlage.ust_satz_prozent` bzw. der Default.
    ust_prozent: float
    #: Die Tarifzeilen, aus denen die Reihen entstanden sind (für Attribute).
    tarif_heute: Any = None
    tarif_morgen: Any = None
    #: Trägt ein **dynamischer** Tarif gepflegte Zeitfenster, die ignoriert werden?
    zeitfenster_ignoriert: bool = False
    #: ⭐ Hat die Wärmepumpe eine **eigene** Tarifzeile — oder fällt sie auf
    #: `allgemein` zurück? `tarife_zum_stichtag` beantwortet das nicht am
    #: Ergebnis: es setzt den allgemeinen Tarif ausdrücklich als Fallback ein,
    #: und danach sind die beiden Zeilen ununterscheidbar. Das Attribut
    #: `waermepumpe_cent` soll aber genau dann **fehlen**, wenn es keinen
    #: eigenen WP-Tarif gibt — eine zweite Zahl, die dieselbe ist, ist keine
    #: Information, sondern eine Frage („warum steht das da?").
    wp_eigener_tarif: bool = False

    def reihe(self, verwendung: str) -> PreisReihe:
        return self.waermepumpe if verwendung == "waermepumpe" else self.allgemein


def _ust_prozent(anlage) -> float:
    from backend.core.berechnungen.preis_reihe import UST_DEFAULT_PROZENT

    roh = getattr(anlage, "ust_satz_prozent", None)
    try:
        wert = float(UST_DEFAULT_PROZENT if roh is None else roh)
    except (TypeError, ValueError):
        return UST_DEFAULT_PROZENT
    return wert if 0.0 <= wert < 100.0 else UST_DEFAULT_PROZENT


def _boerse_backward(preis: Optional[dict], laenge: int) -> list[Optional[float]]:
    """Die Börsenreihen von heute und morgen auf die backward-Achse legen.

    Dieselbe Verschiebung wie im Fenster-Kontext — über **dieselbe** benannte
    Funktion, nicht über ein zweites `h + 1`.
    """
    preis = preis or {}
    out: list[Optional[float]] = [None] * laenge
    for versatz, schluessel in ((0, "rang_profil"), (24, "rang_profil_morgen")):
        for eintrag in (preis.get(schluessel) or []):
            h = eintrag.get("stunde")
            if h is None or not (0 <= h < 24):
                continue
            slot = versatz + forward_stunde_zu_backward_slot(h)
            if 0 <= slot < laenge:
                out[slot] = eintrag.get("preis_cent")
    return out


async def _boerse_slot_null(db, anlage_id: int, heute: date) -> Optional[float]:
    """Slot 0 der Achse = **gestern 23 Uhr**, aus dem persistierten Tagesprofil.

    Die Börsenreihe von heute beginnt backward bei Slot 1; Slot 0 gehört dem
    Vortag und steht nur in `TagesEnergieProfil.boersenpreis_cent` (forward,
    Zeile `stunde = 23`). Für ein Fenster „ab jetzt" ist er nie im Rahmen — er
    macht die **Reihe** vollständig, die als Attribut mitgeht.
    """
    from backend.services.preis_tag import persistierte_preise

    try:
        gestern = await persistierte_preise(db, anlage_id, heute - timedelta(days=1))
    except Exception as e:          # ein fehlender Vortag darf nichts kippen
        logger.debug("Bezugspreis: Slot 0 nicht ermittelbar (%s): %s", anlage_id, e)
        return None
    return gestern.get(23)


# ─────────────────────────────────────────────────────────────────────────────
# Der Aufschlag
# ─────────────────────────────────────────────────────────────────────────────

async def _boersenmittel_monat(
    db, anlage, tarif, jahr: int, monat: int
) -> tuple[Optional[float], str]:
    """Das verbrauchsgewichtete Börsenmittel eines Monats — und wie gut es gedeckt ist.

    Der **Bezug** einer Stunde liegt backward (`netzbezug_kw`), die **Börse**
    forward (`boersenpreis_cent`) — beide in derselben Zeile, aber für
    verschiedene Stunden. Gepaart wird deshalb über
    `forward_stunde_zu_backward_slot`: der Börsenpreis der Zeile `stunde = h`
    gehört zum Bezug der Zeile `stunde = h + 1` (bzw. zu Slot 0 des Folgetags).
    """
    von = date(jahr, monat, 1)
    bis = date(jahr + (monat == 12), (monat % 12) + 1, 1) - timedelta(days=1)

    res = await db.execute(
        select(
            TagesEnergieProfil.datum, TagesEnergieProfil.stunde,
            TagesEnergieProfil.netzbezug_kw, TagesEnergieProfil.boersenpreis_cent,
        ).where(
            TagesEnergieProfil.anlage_id == anlage.id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        )
    )
    zeilen = list(res.all())
    bezug_je: dict[tuple, float] = {}
    boerse_je: dict[tuple, float] = {}
    for datum, stunde, netzbezug, boerse in zeilen:
        if netzbezug is not None:
            bezug_je[(datum, stunde)] = float(netzbezug)
        if boerse is not None:
            # forward `h` → backward-Slot `h + 1`; Slot 24 ist Slot 0 des Folgetags.
            slot = forward_stunde_zu_backward_slot(stunde)
            ziel_datum, ziel_slot = (datum, slot) if slot < 24 else (datum + timedelta(days=1), 0)
            boerse_je[(ziel_datum, ziel_slot)] = float(boerse)

    mit_bezug = [k for k, v in bezug_je.items() if v > 0]
    if not mit_bezug:
        return None, "kein Netzbezug erfasst"
    gedeckt = sum(1 for k in mit_bezug if k in boerse_je)
    abdeckung = gedeckt / len(mit_bezug)

    if abdeckung < MINDEST_ABDECKUNG:
        nachgeholt = await _hole_boerse_nach(db, anlage, jahr, monat, von, bis, boerse_je)
        if nachgeholt:
            gedeckt = sum(1 for k in mit_bezug if k in boerse_je)
            abdeckung = gedeckt / len(mit_bezug)
        if abdeckung < MINDEST_ABDECKUNG:
            return None, f"Börse deckt nur {abdeckung:.0%} der Bezugsstunden"

    mittel = boersenmittel_gewichtet(
        (boerse_je.get(k), bezug_je[k]) for k in mit_bezug
    )
    return mittel, f"{gedeckt} von {len(mit_bezug)} Bezugsstunden"


async def _hole_boerse_nach(db, anlage, jahr, monat, von, bis, boerse_je: dict) -> bool:
    """Fehlende Börsentage **einmal je Monat und Prozess** über die Markt-API nachholen.

    ⚠ **Höchstens einmal.** Ein Monat, für den die API nichts mehr hergibt
    (aWATTar hält kein unbegrenztes Archiv), würde sonst bei **jedem**
    Publish-Takt erneut abgefragt — bei einem 5-Minuten-Takt 288 Abrufe am Tag
    für eine Antwort, die sich nicht ändert.

    Die Demo-Kopien tragen gar keine Börsenstunden; ein Add-on mit Netz schreibt
    sie täglich mit (`energie_profil/_helpers.py`: „Börsenpreis (aWATTar API,
    immer)"), dieser Zweig ist dort also der Ausnahmefall.
    """
    schluessel = (anlage.id, jahr, monat)
    if schluessel in _markt_nachgeholt:
        return False
    _markt_nachgeholt.add(schluessel)

    from backend.services.preis_tag import markt_der_anlage
    from backend.services.strompreis_markt_service import fetch_marktpreise

    markt = markt_der_anlage(anlage)
    tag = von
    geholt = 0
    while tag <= bis:
        try:
            preise = await fetch_marktpreise(tag, markt)
        except Exception as e:
            logger.debug("Bezugspreis: Marktabruf %s fehlgeschlagen: %s", tag, e)
            preise = None
        if preise:
            geholt += 1
            for h, p in preise.items():
                slot = forward_stunde_zu_backward_slot(int(h))
                ziel = (tag, slot) if slot < 24 else (tag + timedelta(days=1), 0)
                boerse_je.setdefault(ziel, float(p))
        tag += timedelta(days=1)
    logger.info(
        "Bezugspreis: %d Börsentage für %04d-%02d nachgeholt (Anlage %s)",
        geholt, jahr, monat, anlage.id,
    )
    return geholt > 0


async def _aufschlag_aus_abrechnung(db, anlage, tarif, *, heute: date) -> Optional[Aufschlag]:
    """Stufe 1 — der jüngste abgerechnete Monat **im Tarifzeitraum**."""
    gueltig_ab = getattr(tarif, "gueltig_ab", None)
    res = await db.execute(
        select(Monatsdaten)
        .where(
            Monatsdaten.anlage_id == anlage.id,
            Monatsdaten.netzbezug_durchschnittspreis_cent.isnot(None),
        )
        .order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())
    )
    for md in res.scalars().all():
        erster = date(md.jahr, md.monat, 1)
        if gueltig_ab is not None and erster < gueltig_ab:
            continue        # P8: ein Ø aus der Zeit davor beschreibt einen anderen Vertrag
        if erster >= heute.replace(day=1):
            continue        # der laufende Monat ist nicht abgerechnet
        mittel, basis = await _boersenmittel_monat(db, anlage, tarif, md.jahr, md.monat)
        if mittel is None:
            continue
        cent = aufschlag_aus_abrechnung(
            md.netzbezug_durchschnittspreis_cent, mittel, _ust_prozent(anlage)
        )
        if cent is None:
            continue
        return Aufschlag(
            cent=cent,
            quelle=f"abrechnung {md.jahr:04d}-{md.monat:02d}",
            basis=f"Börsenmittel {mittel:.2f} ct ({basis})",
        )
    return None


async def _aufschlag_aus_sensor(db, anlage, tarif, *, heute: date) -> Optional[Aufschlag]:
    """Stufe 2 — gemessene Stunden des Preissensors gegen die Börse derselben Zeile.

    Beide Größen liegen **forward** (N-387) und sind damit direkt paarbar; eine
    Verschiebung wäre hier der Fehler, nicht die Korrektur.
    """
    ab = heute - timedelta(days=SENSOR_FENSTER_TAGE)
    gueltig_ab = getattr(tarif, "gueltig_ab", None)
    if gueltig_ab is not None and gueltig_ab > ab:
        ab = gueltig_ab
    res = await db.execute(
        select(TagesEnergieProfil.strompreis_cent, TagesEnergieProfil.boersenpreis_cent)
        .where(
            TagesEnergieProfil.anlage_id == anlage.id,
            TagesEnergieProfil.datum >= ab,
            TagesEnergieProfil.datum <= heute,
            TagesEnergieProfil.strompreis_cent.isnot(None),
            TagesEnergieProfil.boersenpreis_cent.isnot(None),
        )
    )
    paare = [(e, b) for e, b in res.all()]
    if len(paare) < MINDEST_PAARE:
        return None
    cent = aufschlag_aus_stunden(paare, _ust_prozent(anlage))
    if cent is None:
        return None
    return Aufschlag(
        cent=cent,
        quelle=f"sensor {SENSOR_FENSTER_TAGE} tage",
        basis=f"{len(paare)} gemessene Stunden (Median)",
    )


async def lade_aufschlag(db, anlage, tarif, *, heute: date) -> Optional[Aufschlag]:
    """Der abgeleitete Aufschlag — Abrechnung › gemessene Stunden › `None`.

    Memoisiert je `(anlage, tarif, heute)`; der Tageswechsel setzt den Cache von
    selbst zurück, weil das Datum im Schlüssel steht.
    """
    if not ist_dynamisch(tarif):
        return None
    schluessel = (getattr(anlage, "id", None), getattr(tarif, "id", None), heute)
    if schluessel in _aufschlag_cache:
        return _aufschlag_cache[schluessel]

    try:
        ergebnis = await _aufschlag_aus_abrechnung(db, anlage, tarif, heute=heute)
        if ergebnis is None:
            ergebnis = await _aufschlag_aus_sensor(db, anlage, tarif, heute=heute)
    except Exception as e:          # ein Aufschlag ist eine Zugabe, kein Muss
        logger.warning(
            "Bezugspreis: Aufschlag nicht ableitbar (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        ergebnis = None

    _aufschlag_cache[schluessel] = ergebnis
    return ergebnis


# ─────────────────────────────────────────────────────────────────────────────
# Der Einstieg
# ─────────────────────────────────────────────────────────────────────────────

async def lade_bezugspreise(
    db, anlage, preis: Optional[dict], monatsdaten: Optional[list], *, heute: date,
    laenge: int = 48,
) -> Bezugspreise:
    """Alles, was die Preis-Sensoren und der Fenster-Kontext brauchen — **einmal** je Lauf.

    Args:
        preis: das Dict aus `berechne_preis_export` (Börse), oder `None`.
        monatsdaten: die schon geladenen `Monatsdaten` der Anlage — für die
            variable Einspeisevergütung des laufenden Monats (#392). Eine zweite
            Abfrage wäre hier eine zweite Wahrheit über denselben Monat.
        laenge: Achsenlänge; die Reihen sind so lang wie die Achse des
            Fenster-Kontexts.
    """
    from backend.api.routes.strompreise import (
        lade_tarife_je_stichtag,
        resolve_einspeise_preis_cent,
    )
    from backend.core.berechnungen.zeittarif import hat_zeitfenster

    morgen = heute + timedelta(days=1)
    je_stichtag = await lade_tarife_je_stichtag(db, anlage.id, [heute, morgen])
    tarife_heute = je_stichtag.get(heute) or {}
    tarife_morgen = je_stichtag.get(morgen) or {}

    allgemein_heute = tarife_heute.get("allgemein")
    ust = _ust_prozent(anlage)
    aufschlag = await lade_aufschlag(db, anlage, allgemein_heute, heute=heute)

    boerse = _boerse_backward(preis, laenge)
    if ist_dynamisch(allgemein_heute) and boerse and boerse[0] is None:
        boerse[0] = await _boerse_slot_null(db, anlage.id, heute)

    def _reihe_fuer(verwendung: str) -> PreisReihe:
        """Heute aus dem heutigen Tarif, morgen aus dem morgigen — eine Reihe (Ü2)."""
        t_heute = tarife_heute.get(verwendung)
        t_morgen = tarife_morgen.get(verwendung)
        reihe_h = bezugspreis_reihe(
            tarif=t_heute, heute=heute, laenge=laenge,
            boerse_backward=boerse,
            aufschlag_cent=(aufschlag.cent if aufschlag else None), ust_prozent=ust,
        )
        if t_morgen is t_heute or laenge <= 25:
            return reihe_h
        # Tarifwechsel morgen: die zweite Tageshälfte kommt aus dem Tarif zum
        # Stichtag morgen. Die Achse bleibt dieselbe — nur die Quelle wechselt
        # am Slot 25 (morgen 00:00).
        reihe_m = bezugspreis_reihe(
            tarif=t_morgen, heute=heute, laenge=laenge,
            boerse_backward=boerse,
            aufschlag_cent=(aufschlag.cent if aufschlag else None), ust_prozent=ust,
        )
        preise = reihe_h.preis_cent[:25] + reihe_m.preis_cent[25:]
        guenstig = reihe_h.guenstig[:25] + reihe_m.guenstig[25:]
        quelle = reihe_h.quelle if reihe_h.quelle == reihe_m.quelle else "zeitfenster"
        return PreisReihe(preise, guenstig, quelle)

    # ── Vergütung: Stammwert, oder der Monatswert bei variabler Vergütung ──
    verguetung_cent: Optional[float] = None
    verguetung_quelle: Optional[str] = None
    verguetung_grund: Optional[str] = None
    variabel = bool(getattr(allgemein_heute, "einspeisung_variabel", False))
    if allgemein_heute is None:
        verguetung_grund = "kein Tarif hinterlegt"
    elif variabel:
        laufend = next(
            (m for m in (monatsdaten or [])
             if m.jahr == heute.year and m.monat == heute.month), None,
        )
        if laufend is not None and getattr(laufend, "einspeise_durchschnittspreis_cent", None) is not None:
            verguetung_cent = resolve_einspeise_preis_cent(laufend, None)
            verguetung_quelle = "monatswert"
        else:
            # ⛔ **Kein Rückfall auf den Stammwert** (#392): Wer „variable
            # Vergütung" gepflegt hat, sagt damit, dass der Stammwert den Monat
            # nicht beschreibt. Ihn trotzdem auszugeben wäre eine stille
            # Ersetzung (Flex §8).
            verguetung_grund = (
                f"variable Vergütung, aber kein Monatswert für "
                f"{heute.year:04d}-{heute.month:02d}"
            )
    else:
        roh = getattr(allgemein_heute, "einspeiseverguetung_cent_kwh", None)
        if roh is not None:
            verguetung_cent = float(roh)
            verguetung_quelle = "vertrag"
        else:
            verguetung_grund = "Tarif ohne Einspeisevergütung"

    return Bezugspreise(
        allgemein=_reihe_fuer("allgemein"),
        waermepumpe=_reihe_fuer("waermepumpe"),
        verguetung_cent=verguetung_cent,
        verguetung_quelle=verguetung_quelle,
        verguetung_grund=verguetung_grund,
        einspeisung_variabel=variabel,
        aufschlag=aufschlag,
        ust_prozent=ust,
        tarif_heute=allgemein_heute,
        tarif_morgen=tarife_morgen.get("allgemein"),
        zeitfenster_ignoriert=bool(
            ist_dynamisch(allgemein_heute) and hat_zeitfenster(allgemein_heute)
        ),
        wp_eigener_tarif=(
            tarife_heute.get("waermepumpe") is not None
            and tarife_heute.get("waermepumpe") is not allgemein_heute
        ),
    )
