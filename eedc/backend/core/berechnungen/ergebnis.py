"""Ergebnis-Leiter, SOLL-Erfüllung und Zeitraum-Faltung — Monat und Jahr aus EINER Rechnung.

Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026, Vorlage Fassung 2; Register N-584 · N-600 · N-356 · N-601 ·
N-602). Bis dahin entstanden Netto-Ertrag, Monats-/Jahresergebnis und SOLL-Erfüllung an zwölf Stellen mit verschiedener
Zusammensetzung: Cockpit → Monat rechnete ``Einspeise-Erlös + EV-Ersparnis`` (ohne USt, BKW-Rest, Erlös eigener Satz,
Sonstiges), die Übersicht die GLOSSAR-Definition, der Browser faltete das Jahr Feld für Feld, das PDF spiegelte die
Browser-Formeln. Dieselbe Anlage hatte bei Regelbesteuerung im Monat 212,00 € und in der Übersicht 206,30 € (N-601), ein
Jahr mit einem Monat ohne Netzbezugswert 198 % Autarkie (N-584, #421).

## Die Leiter (``berechne_ergebnis``)

::

    Stufe 1  Netto-Ertrag (PV)            = Einspeise-Erlös + EV-Ersparnis + BKW-Rest-Ersparnis + Erlös eigener Satz
                                            + Sonstige Positionen (netto) − Dienstliche Ladekosten
                                            − USt-Anteil auf den Eigenverbrauch
    Stufe 2  Ergebnis vor Betriebskosten  = Netto-Ertrag + WP-Ersparnis + E-Mob-Ersparnis − Stromrechnung (inkl. Grundgebühr)
    Stufe 3  Monats-/Jahresergebnis       = Stufe 2 − Betriebskosten (anteilig, nur im Zeitraum aktive Komponenten)

* Stufe 1 ist die GLOSSAR-Definition „Netto-Ertrag (PV)" und die Zahl der Vier-Wege-Symmetrie
  (Übersicht · PDF-Jahresbericht · HA-Sensor · Aussichten-Rückblick). Sie gilt für Monat, Jahr und Gesamt gleich.
* Stufe 2 hat im UI **keinen eigenen Namen** (Antwortfeld ``ergebnis_vor_betriebskosten_euro``); sie steht nur als
  Zwischenzeile in der Herleitung. „Ergebnis nach Stromrechnung" ist der Name, den die Komponenten-Tabelle bisher für
  eine Zahl **nach** Betriebskosten benutzte — also Stufe 3 (Gegenprüfung G4).
* **Dienstliche Ladekosten** (N-633, 05.10.2026) sind ein eigener Posten der Stufe 1: was ein Dienstwagen zu Hause
  geladen hat, PV-Anteil zum Netzbezugspreis (nimmt die EV-Gutschrift zurück), Netzanteil zum Wallbox-Tarif
  (``dienstliche_ladekosten.py``, Entscheid 31.07.). Die Monats-Fakten bilden ihn (``EmobFakten.
  dienstliche_ladekosten_euro``); alle Sichten lesen dasselbe Feld. Bis dahin falteten Übersicht, HA-Export und
  Aussichten ihn in die Sonstigen Positionen, Cockpit → Monat/Jahr, Tabelle und PDF führten ihn nicht (M09: 104,40 €
  gegen 122,40 €). Er steht NICHT in den Sonstigen Ausgaben: die sind Eingang des Kapitaleinsatzes (F-19).
* **Speicher-Ersparnis** steht nicht in der Leiter: sie ist eine Zuordnung innerhalb der EV-Ersparnis
  (``KomponentenFinanzTabelle.tsx``); **Netzladung** steckt in der Stromrechnung.

## Fehlende Eingänge — eine Regel für Monat, Vorjahr und Jahr (E5, E10/G2)

Eine Stufe ist ``None``, wenn einer ihrer **Pflichtposten** fehlt: Stufe 1 braucht Einspeise-Erlös und EV-Ersparnis,
Stufe 2 zusätzlich die Stromrechnung; Stufe 3 hat keine eigene Pflicht (Betriebskosten dürfen fehlen = 0). Optionale
Posten (WP, E-Mob, BKW-Rest, Erzeuger-Erlös, Sonstiges, USt) fehlen als 0 und stehen in ``fehlende_posten``, wenn die
Komponente existiert (``komponenten_vorhanden``), aber keinen Wert hat. Die Faltung (``falte_zeitraum``) wendet
dieselbe Regel an: fehlt einem Monat der Grundgesamtheit ein Pflichtposten, ist die Stufe im Zeitraum ``None``, und
``fehlende_posten`` nennt die Monate („Stromrechnung (Sep 2026)“). ⛔ Eine Zahl „Stromkosten aus 8 von 9 Monaten" wäre das ``or 0``, das E5 im
Vorjahr streicht, nur mit Ausweis — dieselbe Lücke hätte drei Regeln bekommen.

## Der Layer rundet nicht (G8)

Die Aufrufer runden heute an verschiedenen Stellen (Monatsroute je Posten auf 2 Stellen, Übersicht erst am
Antwortrand, HA-Sensor nie, Tag gar nicht). Ein rundender Layer wäre höchstens zu einer Seite bitgleich. Er rechnet
deshalb mit den Floats, die er bekommt; gerundet wird am Antwortrand wie bisher. Das gilt seit der Nachmessung
(03.10.2026) auch für ``falte_zeitraum``: die zwei Client-Rundungen, die sie für die P6-Bitgleichheit portiert hatte
(``sonstiges_geraete.*``, ``grundlast_anteil_prozent``), stehen jetzt am Rand der Jahresroute
(``services/jahres_aggregat.py::runde_rand``) — P6 danach erneut bitgleich.

## USt-Anteil eines Monats (E1/G1)

``ust_satz_euro_je_kwh`` liefert die USt je kWh Eigenverbrauch eines Kalenderjahres — aufgebaut auf
``berechne_ust_eigenverbrauch`` (keine zweite Formel: die Funktion ist linear im Eigenverbrauch, der Satz ist ihr Wert
für 1 kWh). ``USt-Anteil_Monat = EV_Monat × Satz``; Σ der ungerundeten Monatsanteile == Jahreswert (N-130). **Welche
Investitionen und Monate in den Satz eingehen, entscheidet NICHT dieser Layer**, sondern ``services/ust_satz.py`` —
Aufbereitung ≠ Formel (ADR-001).

## SOLL-Erfüllung (N-69, N-356)

``soll_erfuellung`` ist der Wortlaut von ``lib/sollErfuellung.ts`` und ``pdf/builders/monatsbericht.py`` (beide bis
03.10.2026 eigene Bildungsstellen): Fenster-Quote ``PV ÷ SOLL(abgelaufene Tage)``, Monats-Quote ``PV ÷ SOLL(ganzer
Monat)``, Fenstertext ``anteilig · t von T Tagen``. Ein SOLL ≤ 0 hat keine Quote.

## Zeitraum-Faltung (``falte_zeitraum``, N-584)

Bis 03.10.2026 faltete der Browser (``v4/JahrAggregat.tsx::baueJahrAlsMonat``) die zwölf Monatsantworten — eine
Aggregation außerhalb des Layers und außerhalb jedes Backend-Wächters (D3 zurückgenommen, ADR-001-Nachtrag). Die
Regeln sind übernommen; geändert sind genau zwei:

* **Quoten paarweise (R-Q):** Autarkie, EV-Quote, Speicher-Auslastung, Netzlade-Ø-Preis entstehen aus Summen über
  **genau die Monate, die beide Größen tragen** (Bauform ``gewichtet``). Ein Monat mit Eigenverbrauch, aber ohne
  Gesamtverbrauch, fällt aus Zähler **und** Nenner — vorher stand er im Zähler und machte 198 % daraus. Jede dieser
  Quoten trägt Zähler, Nenner und Fenstertext („aus 8 von 9 Monaten"), damit die Herleitung auf die Zahl führt.
* **Ergebnisgrößen über die Leiter** auf den Jahressummen ihrer Posten, mit der None-Regel oben.

Alles andere ist Wort für Wort die Client-Regel (Feldtabelle):

=====================================  ==========================================================================
Summe null-bewusst (alle ``None`` ⇒ ``None``)  Mengen (kWh), Geld (€), Zähler, Grundgebühr, SOLL + Fenster-Tage
Quote paarweise                         ``autarkie_prozent``, ``eigenverbrauch_quote_prozent``,
                                        ``speicher_auslastung_prozent``, ``speicher_ladung_netz_preis_cent``
mengengewichteter Ø (``gewichtet``)     ``netzbezug_preis_cent``, ``einspeise_preis_cent``,
                                        ``netzbezug_durchschnittspreis_cent`` (nur wenn ein Monat ihn trägt)
Mittel der Monate                       ``speicher_effektiver_ladepreis_cent``, ``grundlast_kw``
Maximum                                 ``speicher_kapazitaet_kwh``, ``wp_starts_max_tag``, ``wp_betriebsstunden_max_tag``
letzter vorhandener Wert                ``zaehlergebuehr_euro_jahr``
ODER über die Monate                    ``hat_*``, ``wp_modus_gemessen``
Layer-Original                          ``speicher_wirkungsgrad`` (``fenster_lang``), ``eauto_effizienz_zeitraum``
Kennzahlen der Übersicht (P12)          alle WP-Kennzahlen (``wp_jaz*``, Modus-Reste, Geräte) — ohne Übersicht wie bisher
=====================================  ==========================================================================

Die Funktionen nehmen **Antwort-Dicts** (``AktuellerMonatResponse.model_dump()``) und geben eines zurück — kein ORM,
keine Session. Die Monatsauswahl (welche Monate geladen werden, welche abgeschlossen sind) ist Aufbereitung und liegt in
``services/jahres_aggregat.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Optional, Sequence

from backend.core.berechnungen.emob import EffizienzWert, eauto_effizienz_zeitraum
from backend.core.berechnungen.pv_verteilung import verluste_grund_zeitraum, wandlungsverluste_prozent
from backend.core.berechnungen.speicher_wirkungsgrad import speicher_wirkungsgrad
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    berechne_ust_eigenverbrauch,
)

MONAT_KURZ = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

# ─────────────────────────────────────────────────────────────────────────────
# Die Leiter
# ─────────────────────────────────────────────────────────────────────────────

#: Posten der Leiter: Schlüssel → (Anzeigename, Vorzeichen, Stufe, Pflicht, Komponente für ``fehlende_posten``,
#: Antwortfeld). Die Reihenfolge ist die der Herleitung.
POSTEN: tuple[tuple[str, str, int, int, bool, Optional[str], str], ...] = (
    ("einspeise_erloes", "Einspeise-Erlös", +1, 1, True, None, "einspeise_erloes_euro"),
    ("ev_ersparnis", "Eigenverbrauchs-Ersparnis", +1, 1, True, None, "ev_ersparnis_euro"),
    ("bkw_rest_ersparnis", "BKW-Ersparnis", +1, 1, False, "balkonkraftwerk", "bkw_ersparnis_euro"),
    ("erzeuger_erloes", "Erlös eigener Satz", +1, 1, False, "erzeuger", "erzeuger_erloes_euro"),
    ("sonstige_netto", "Sonstige Positionen", +1, 1, False, "sonstiges", "sonstige_netto_euro"),
    ("dienstliche_ladekosten", "Dienstliche Ladekosten", -1, 1, False, "emob", "dienstliche_ladekosten_euro"),
    ("ust_anteil", "USt auf Eigenverbrauch", -1, 1, False, "ust", "ust_eigenverbrauch_euro"),
    ("wp_ersparnis", "WP-Ersparnis", +1, 2, False, "waermepumpe", "wp_ersparnis_euro"),
    ("emob_ersparnis", "E-Mobilität-Ersparnis", +1, 2, False, "emob", "emob_ersparnis_euro"),
    ("stromkosten", "Stromrechnung", -1, 2, True, None, "netzbezug_kosten_euro"),
    ("betriebskosten", "Betriebskosten", -1, 3, False, None, "betriebskosten_anteilig_euro"),
)

#: Posten, die in der Herleitung NUR erscheinen, wenn sie ≠ 0 sind (N-600-Zuschnitt 02.10., Gernot).
NUR_WENN_UNGLEICH_NULL = frozenset({
    "bkw_rest_ersparnis", "erzeuger_erloes", "sonstige_netto", "dienstliche_ladekosten", "ust_anteil", "wp_ersparnis",
    "emob_ersparnis",
})

STUFEN_NAME = {1: "Netto-Ertrag", 2: "Ergebnis vor Betriebskosten", 3: "Ergebnis"}


@dataclass(frozen=True)
class ErgebnisEingang:
    """Die bewerteten Posten eines Zeitraums (€). ``None`` = nicht vorhanden / nicht bewertbar."""

    einspeise_erloes: Optional[float] = None
    ev_ersparnis: Optional[float] = None
    bkw_rest_ersparnis: Optional[float] = None
    erzeuger_erloes: Optional[float] = None
    sonstige_netto: Optional[float] = None
    #: N-633: Aufwand, positiv übergeben (die Leiter zieht ihn ab).
    dienstliche_ladekosten: Optional[float] = None
    ust_anteil: Optional[float] = None
    wp_ersparnis: Optional[float] = None
    emob_ersparnis: Optional[float] = None
    stromkosten: Optional[float] = None
    betriebskosten: Optional[float] = None
    #: Komponenten, deren Posten fehlen DARF, aber als fehlend genannt wird (``waermepumpe`` · ``emob`` · ``ust`` …).
    komponenten_vorhanden: frozenset[str] = frozenset()
    #: Vom Aufrufer bereits ermittelte Lücken (Faltung: „Stromrechnung (Sep 2026)") — werden übernommen.
    fehlende_posten: tuple[str, ...] = ()


@dataclass(frozen=True)
class EingesetzterWert:
    """Ein Summand der Herleitung — Name, Betrag MIT Vorzeichen, Antwortfeld."""

    name: str
    betrag: float
    feld: str
    #: +1 Ertrag, −1 Aufwand — unabhängig vom Betrag (ein Aufwand von 0,00 € bleibt ein Aufwand).
    vorzeichen: int = 1


@dataclass(frozen=True)
class Herleitung:
    """Formel und eingesetzte Werte einer Stufe — Wert und Erklärung aus EINER Quelle (Style-Guide A6)."""

    formel: str
    eingesetzte_werte: tuple[EingesetzterWert, ...]
    ergebnis: Optional[float]


@dataclass(frozen=True)
class ErgebnisLeiter:
    netto_ertrag: Optional[float]
    vor_betriebskosten: Optional[float]
    ergebnis: Optional[float]
    herleitung: dict[str, Herleitung]
    fehlende_posten: tuple[str, ...]


def _summand(wert: Optional[float]) -> float:
    return wert if wert is not None else 0.0


def berechne_ergebnis(e: ErgebnisEingang) -> ErgebnisLeiter:
    """Die drei Stufen samt Herleitung. Rundet nicht (G8)."""
    werte = {k: getattr(e, k) for k, *_ in POSTEN}
    fehlend: list[str] = list(e.fehlende_posten)
    stufe_ok = {1: True, 2: True, 3: True}
    for schluessel, name, _vz, stufe, pflicht, komponente, _feld in POSTEN:
        if werte[schluessel] is not None:
            continue
        if pflicht:
            for s in range(stufe, 4):
                stufe_ok[s] = False
            if not any(f == name or f.startswith(f"{name} (") for f in fehlend):
                fehlend.append(name)
        elif komponente is not None and komponente in e.komponenten_vorhanden and name not in fehlend:
            fehlend.append(name)

    def summe_bis(stufe: int) -> float:
        s = 0.0
        for schluessel, _n, vz, st, *_r in POSTEN:
            if st <= stufe:
                s = s + vz * _summand(werte[schluessel])
        return s

    netto = summe_bis(1) if stufe_ok[1] else None
    vor_bk = summe_bis(2) if stufe_ok[2] else None
    ergebnis = summe_bis(3) if stufe_ok[3] else None

    def herleitung(stufe: int, ergebnis_wert: Optional[float]) -> Herleitung:
        teile: list[tuple[int, EingesetzterWert]] = []
        for schluessel, name, vz, st, pflicht, _k, feld in POSTEN:
            if st > stufe:
                continue
            w = werte[schluessel]
            # Optionale Posten nur, wenn sie etwas beitragen (N-600-Zuschnitt); Betriebskosten stehen immer da,
            # weil sie die Stufe 3 von Stufe 2 trennen.
            if schluessel in NUR_WENN_UNGLEICH_NULL and not w:
                continue
            teile.append((vz, EingesetzterWert(name, vz * _summand(w), feld, vz)))
        formel = "".join(
            (("− " if vz < 0 else "") if i == 0 else (" − " if vz < 0 else " + ")) + t.name
            for i, (vz, t) in enumerate(teile)
        )
        return Herleitung(formel=formel, eingesetzte_werte=tuple(t for _vz, t in teile), ergebnis=ergebnis_wert)

    return ErgebnisLeiter(
        netto_ertrag=netto,
        vor_betriebskosten=vor_bk,
        ergebnis=ergebnis,
        herleitung={
            "netto_ertrag": herleitung(1, netto),
            "vor_betriebskosten": herleitung(2, vor_bk),
            "ergebnis": herleitung(3, ergebnis),
        },
        fehlende_posten=tuple(fehlend),
    )


# ─────────────────────────────────────────────────────────────────────────────
# USt-Anteil (E1) — Satz je kWh aus der Jahresfunktion
# ─────────────────────────────────────────────────────────────────────────────

def ust_satz_euro_je_kwh(
    jahresanteil: UstJahresanteil,
    *,
    bemessungsgrundlage_euro: float,
    betriebskosten_jahr_euro: float,
    ust_satz_prozent: float,
) -> float:
    """USt je kWh Eigenverbrauch eines Kalenderjahres (€/kWh).

    Der Wert von ``berechne_ust_eigenverbrauch`` für **1 kWh** Eigenverbrauch bei der PV-Erzeugung und Monatszahl des
    Jahres — die Jahresfunktion ist linear im Eigenverbrauch, eine zweite Formel gibt es damit nicht. Ein Jahr ohne PV
    hat den Satz 0.
    """
    return berechne_ust_eigenverbrauch(
        [replace(jahresanteil, eigenverbrauch_kwh=1.0)],
        bemessungsgrundlage_euro=bemessungsgrundlage_euro,
        betriebskosten_jahr_euro=betriebskosten_jahr_euro,
        ust_satz_prozent=ust_satz_prozent,
    )


def ust_anteil_euro(eigenverbrauch_kwh: Optional[float], satz_euro_je_kwh: Optional[float]) -> Optional[float]:
    """USt-Anteil eines Zeitraums = EV × Satz. ``None``, wenn eins von beiden fehlt."""
    if eigenverbrauch_kwh is None or satz_euro_je_kwh is None:
        return None
    return max(eigenverbrauch_kwh, 0.0) * satz_euro_je_kwh


# ─────────────────────────────────────────────────────────────────────────────
# SOLL-Erfüllung (N-69)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SollErfuellung:
    prozent: Optional[float]
    monat_prozent: Optional[float]
    fenster_text: Optional[str]
    anteilig: bool


def soll_erfuellung(
    pv_kwh: Optional[float],
    soll_kwh: Optional[float],
    soll_tage: Optional[int],
    soll_tage_gesamt: Optional[int],
    soll_monat_kwh: Optional[float] = None,
) -> SollErfuellung:
    """Fenster-Quote, Monats-Quote, Fenstertext — Wortlaut von ``lib/sollErfuellung.ts``."""
    prozent = (
        pv_kwh / soll_kwh * 100
        if soll_kwh is not None and pv_kwh is not None and soll_kwh > 0 else None
    )
    monat_prozent = (
        pv_kwh / soll_monat_kwh * 100
        if soll_monat_kwh is not None and soll_monat_kwh > 0 and pv_kwh is not None else None
    )
    anteilig = soll_tage is not None and soll_tage_gesamt is not None and soll_tage < soll_tage_gesamt
    return SollErfuellung(
        prozent=prozent,
        monat_prozent=monat_prozent,
        fenster_text=f"anteilig · {soll_tage} von {soll_tage_gesamt} Tagen" if anteilig else None,
        anteilig=anteilig,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Zeitraum-Faltung
# ─────────────────────────────────────────────────────────────────────────────

def _js_round(x: float) -> float:
    """``Math.round`` (JS): halbe Werte Richtung +∞ — der Client rundete so; Python ``round`` wäre Banker's Rounding."""
    r = math.floor(x)
    return float(r + 1) if x - r >= 0.5 else float(r)


def summe(werte: Iterable[Optional[float]]) -> Optional[float]:
    """Σ null-bewusst: nur wenn KEIN Wert vorliegt ⇒ ``None`` (sonst 0 + …)."""
    vorhanden = [v for v in werte if v is not None]
    if not vorhanden:
        return None
    s = 0
    for v in vorhanden:
        s = s + v
    return s


def _max(werte: Iterable[Optional[float]]) -> Optional[float]:
    vorhanden = [v for v in werte if v is not None]
    return max(vorhanden) if vorhanden else None


def mittel(werte: Iterable[Optional[float]]) -> Optional[float]:
    vorhanden = [v for v in werte if v is not None]
    if not vorhanden:
        return None
    s = 0
    for v in vorhanden:
        s = s + v
    return s / len(vorhanden)


def quote(zaehler: Optional[float], nenner: Optional[float], faktor: float = 100) -> Optional[float]:
    if zaehler is None or nenner is None or nenner == 0:
        return None
    return zaehler / nenner * faktor


def gewichtet(preise: Sequence[Optional[float]], mengen: Sequence[Optional[float]]) -> Optional[float]:
    """Mengengewichteter Ø — Σ(Preis × Menge) / Σ Menge; ohne Menge das ungewichtete Mittel (Client-Regel)."""
    produkt = 0.0
    menge = 0.0
    for p, m in zip(preise, mengen):
        if p is None or m is None:
            continue
        produkt += p * m
        menge += m
    if menge == 0:
        return mittel(preise)
    return produkt / menge


@dataclass(frozen=True)
class PaarQuote:
    """Quote aus EINER Grundgesamtheit (R-Q) — mit Zähler, Nenner und den beitragenden Monaten."""

    wert: Optional[float]
    zaehler: Optional[float]
    nenner: Optional[float]
    monate: tuple[int, ...]
    von_monaten: int

    @property
    def fenster_text(self) -> Optional[str]:
        """„aus 8 von 9 Monaten" — nur, wenn nicht jeder Monat beiträgt."""
        if self.von_monaten == 0 or len(self.monate) >= self.von_monaten:
            return None
        return f"aus {len(self.monate)} von {self.von_monaten} Monaten"


def quote_paarweise(
    zeilen: Sequence[Mapping[str, Any]],
    zaehler_feld: str,
    nenner_feld: str,
    *,
    faktor: float = 100,
    monat_feld: str = "monat",
) -> PaarQuote:
    """Σ Zähler ÷ Σ Nenner über genau die Zeilen, die BEIDE Größen tragen (Bauform ``gewichtet``)."""
    z_sum: Optional[float] = None
    n_sum: Optional[float] = None
    monate: list[int] = []
    for zeile in zeilen:
        z = zeile.get(zaehler_feld)
        n = zeile.get(nenner_feld)
        if z is None or n is None:
            continue
        z_sum = z if z_sum is None else z_sum + z
        n_sum = n if n_sum is None else n_sum + n
        monate.append(zeile.get(monat_feld))
    return PaarQuote(
        wert=quote(z_sum, n_sum, faktor),
        zaehler=z_sum,
        nenner=n_sum,
        monate=tuple(monate),
        von_monaten=len(zeilen),
    )


def _oder0(v: Optional[float]) -> float:
    """``?? 0`` (JS) — 0 bleibt 0, nur ``None`` wird 0."""
    return v if v is not None else 0


def _union(listen: Iterable[Iterable[str]]) -> list[str]:
    return list(dict.fromkeys(x for liste in listen for x in liste))


def ergebnis_eingang_aus_antwort(d: Mapping[str, Any], komponenten: frozenset[str] = frozenset()) -> ErgebnisEingang:
    """Die Posten einer (Monats-)Antwort als Eingang der Leiter — für Faltung und Leser derselben Felder."""
    return ErgebnisEingang(
        einspeise_erloes=d.get("einspeise_erloes_euro"),
        ev_ersparnis=d.get("ev_ersparnis_euro"),
        bkw_rest_ersparnis=d.get("bkw_ersparnis_euro"),
        erzeuger_erloes=d.get("erzeuger_erloes_euro"),
        sonstige_netto=d.get("sonstige_netto_euro"),
        dienstliche_ladekosten=d.get("dienstliche_ladekosten_euro"),
        ust_anteil=d.get("ust_eigenverbrauch_euro"),
        wp_ersparnis=d.get("wp_ersparnis_euro"),
        emob_ersparnis=d.get("emob_ersparnis_euro"),
        stromkosten=d.get("netzbezug_kosten_euro"),
        betriebskosten=d.get("betriebskosten_anteilig_euro"),
        komponenten_vorhanden=komponenten,
    )


def _monatsliste(monate: Sequence[int]) -> str:
    return ", ".join(MONAT_KURZ[m] for m in monate if 1 <= m <= 12)


def falte_posten(monate: Sequence[Mapping[str, Any]], jahr: int) -> ErgebnisEingang:
    """Jahressummen der Leiter-Posten mit der None-Regel (G2): fehlt ein Pflichtposten in einem Monat, ist er im
    Zeitraum ``None`` und der Monat steht in ``fehlende_posten``."""
    werte: dict[str, Optional[float]] = {}
    fehlend: list[str] = []
    for schluessel, name, _vz, _st, pflicht, _k, feld in POSTEN:
        if pflicht:
            ohne = [m.get("monat") for m in monate if m.get(feld) is None]
            if ohne:
                werte[schluessel] = None
                fehlend.append(f"{name} ({_monatsliste(ohne)} {jahr})")
                continue
        werte[schluessel] = summe(m.get(feld) for m in monate)
    return ErgebnisEingang(**werte, fehlende_posten=tuple(fehlend))


def falte_zeitraum(
    monate: Sequence[Mapping[str, Any]],
    jahr: int,
    kennzahlen: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Faltet Monatsantworten zu EINER Antwort derselben Gestalt (``monat=0``, ``monat_name=str(jahr)``).

    Regeln s. Modul-Docstring. ``kennzahlen`` ist die Übersicht des Jahres (``CockpitUebersichtResponse``-Dict) — sie
    liefert die WP-Kennzahlen (P12); ohne sie bleiben die Mengen, und die Kennzahlen fehlen (wie im Client).
    """
    k = kennzahlen
    f = lambda key: [m.get(key) for m in monate]  # noqa: E731

    pv = summe(f("pv_erzeugung_kwh"))
    ev = summe(f("eigenverbrauch_kwh"))
    speicher_ladung = summe(f("speicher_ladung_kwh"))
    speicher_entladung = summe(f("speicher_entladung_kwh"))
    eta = speicher_wirkungsgrad(speicher_ladung, speicher_entladung, langes_fenster_quelle="fenster_lang")
    speicher_ladung_netz = summe(f("speicher_ladung_netz_kwh"))
    wp_strom = summe(f("wp_strom_kwh"))
    emob = eauto_effizienz_zeitraum(
        EffizienzWert(None, m.get("emob_verbrauch_quelle") or "keine", m.get("emob_verbrauch_basis_kwh"),
                      m.get("emob_km") or 0.0)
        for m in monate
    )

    # R-Q: Quoten aus einer Grundgesamtheit je Quote.
    q_autarkie = quote_paarweise(monate, "eigenverbrauch_kwh", "gesamtverbrauch_kwh")
    q_ev_quote = quote_paarweise(monate, "eigenverbrauch_kwh", "pv_erzeugung_kwh")
    q_auslastung = quote_paarweise(monate, "speicher_entladung_kwh", "speicher_auslastungs_basis_kwh")
    q_netzladung = quote_paarweise(monate, "speicher_ladung_netz_kosten_euro", "speicher_ladung_netz_kwh")
    # HA-Bauform E4b: Wandlungsverluste des Zeitraums = Σ der Monatswerte (``None``, wenn kein Monat
    # einen trägt); Prozent über die Monate, die Verluste UND Bezug tragen.
    q_verluste = quote_paarweise(monate, "wandlungsverluste_kwh", "wandlungsverluste_bezug_kwh")

    netzbezug_preis_effektiv = [
        m.get("netzbezug_durchschnittspreis_cent") if m.get("netzbezug_durchschnittspreis_cent") is not None
        else m.get("netzbezug_preis_cent")
        for m in monate
    ]

    # Per-Investition-Finanzdetails: Σ je Investition, Identität vom ersten Vorkommen; Monats-Formeln entfallen.
    financials: dict[int, dict[str, Any]] = {}
    for m in monate:
        for fin in m.get("investitionen_financials") or []:
            prev = financials.get(fin["investition_id"])
            if prev is None:
                neu = dict(fin)
                neu.update(formel=None, berechnung=None, erloes_berechnung=None, betriebskosten_jahr_euro=None)
                financials[fin["investition_id"]] = neu
                continue
            prev["betriebskosten_monat_euro"] = prev["betriebskosten_monat_euro"] + fin["betriebskosten_monat_euro"]
            for feld in ("erloes_euro", "ersparnis_euro"):
                a, b = prev.get(feld), fin.get(feld)
                prev[feld] = None if a is None and b is None else (a if a is not None else 0) + (b if b is not None else 0)
            prev["sonstige_ertraege_euro"] = prev["sonstige_ertraege_euro"] + fin["sonstige_ertraege_euro"]
            prev["sonstige_ausgaben_euro"] = prev["sonstige_ausgaben_euro"] + fin["sonstige_ausgaben_euro"]
            if not prev.get("ersparnis_label") and fin.get("ersparnis_label"):
                prev["ersparnis_label"] = fin["ersparnis_label"]

    geraete: dict[str, list[str]] = {}
    for m in monate:
        for typ, namen in (m.get("komponenten_geraete") or {}).items():
            geraete[typ] = _union([geraete.get(typ, []), namen])

    sg: dict[str, dict[str, Any]] = {}
    sg_felder = ("erzeugung_kwh", "eigenverbrauch_kwh", "einspeisung_kwh", "verbrauch_kwh",
                 "bezug_pv_kwh", "bezug_netz_kwh", "abgabe_kwh", "erloes_euro")
    for m in monate:
        for g in m.get("sonstiges_geraete") or []:
            key = f"{g['kategorie']}|{g['bezeichnung']}"
            a = sg.setdefault(key, {"bezeichnung": g["bezeichnung"], "kategorie": g["kategorie"],
                                    **{x: 0 for x in sg_felder}})
            for x in sg_felder:
                a[x] = a[x] + (g.get(x) if g.get(x) is not None else 0)
    # Rundung am Rand (G8, Nachmessung 03.10.): hier nur „0 ⇒ kein Wert", gerundet wird in `jahres_aggregat.runde_rand`.
    nz = lambda v: v if v > 0 else None  # noqa: E731
    sonstiges_geraete = [
        {"bezeichnung": g["bezeichnung"], "kategorie": g["kategorie"], **{x: nz(g[x]) for x in sg_felder}}
        for g in sg.values()
    ]

    feld_quellen: dict[str, Any] = {}
    for m in monate:
        feld_quellen.update(m.get("feld_quellen") or {})

    erster = monate[0] if monate else {}

    gl_kwh = summe(f("grundlast_kwh"))
    gl_basis = summe(m.get("gesamtverbrauch_kwh") for m in monate if m.get("grundlast_kwh") is not None)
    gl_anteil = (
        (gl_kwh / gl_basis) * 100
        if gl_kwh is not None and gl_basis is not None and gl_basis > 0 else None
    )

    def kz(name: str, rueckfall: Any = None) -> Any:
        if k is None:
            return rueckfall
        v = k.get(name)
        return v if v is not None else rueckfall

    modus_heizen = summe(f("wp_modus_strom_heizen_kwh"))
    modus_kuehlen = summe(f("wp_modus_strom_kuehlen_kwh"))
    modus_ww = summe(f("wp_modus_strom_warmwasser_kwh"))

    # Ergebnis-Leiter auf den Jahressummen (G2).
    komponenten = frozenset(
        x for x, flag in (("waermepumpe", any(m.get("hat_waermepumpe") for m in monate)),
                          ("emob", any(m.get("hat_emobilitaet") for m in monate)),
                          ("ust", any(m.get("ust_eigenverbrauch_euro") is not None for m in monate)))
        if flag
    )
    eingang = replace(falte_posten(monate, jahr), komponenten_vorhanden=komponenten)
    leiter = berechne_ergebnis(eingang)
    soll = soll_erfuellung(pv, summe(f("soll_pv_kwh")), summe(f("soll_pv_tage")), summe(f("soll_pv_tage_gesamt")))

    return {
        "anlage_id": erster.get("anlage_id", 0),
        "anlage_name": erster.get("anlage_name", ""),
        "jahr": jahr,
        "monat": 0,
        "monat_name": str(jahr),
        "aktualisiert_um": erster.get("aktualisiert_um", ""),
        "quellen": erster.get("quellen") or {},
        "hinweise": _union(m.get("hinweise") or [] for m in monate),

        "pv_erzeugung_kwh": pv,
        "einspeisung_kwh": summe(f("einspeisung_kwh")),
        "netzbezug_kwh": summe(f("netzbezug_kwh")),
        "eigenverbrauch_kwh": ev,
        "direktverbrauch_kwh": summe(f("direktverbrauch_kwh")),
        "gesamtverbrauch_kwh": summe(f("gesamtverbrauch_kwh")),
        "wandlungsverluste_kwh": summe(f("wandlungsverluste_kwh")),
        "wandlungsverluste_bezug_kwh": q_verluste.nenner,
        "wandlungsverluste_prozent": wandlungsverluste_prozent(q_verluste.zaehler, q_verluste.nenner),
        # N-588: die bewertete Menge des Jahres = Σ der bewerteten Monatsmengen; der Grund nicht bewerteter Verluste.
        "eigenverbrauch_ohne_verluste_kwh": summe(f("eigenverbrauch_ohne_verluste_kwh")),
        "verluste_grund": verluste_grund_zeitraum(
            (m.get("wandlungsverluste_kwh"), m.get("verluste_grund")) for m in monate),
        "autarkie_prozent": q_autarkie.wert,
        "autarkie_zaehler_kwh": q_autarkie.zaehler,
        "autarkie_nenner_kwh": q_autarkie.nenner,
        "autarkie_fenster": q_autarkie.fenster_text,
        "eigenverbrauch_quote_prozent": q_ev_quote.wert,
        "eigenverbrauch_quote_zaehler_kwh": q_ev_quote.zaehler,
        "eigenverbrauch_quote_nenner_kwh": q_ev_quote.nenner,
        "eigenverbrauch_quote_fenster": q_ev_quote.fenster_text,
        "spez_ertrag": summe(f("spez_ertrag")),

        "speicher_ladung_kwh": speicher_ladung,
        "speicher_entladung_kwh": speicher_entladung,
        "speicher_ladung_netz_kwh": speicher_ladung_netz,
        "speicher_wirkungsgrad_prozent": eta.prozent,
        "speicher_vollzyklen": summe(f("speicher_vollzyklen")),
        "speicher_kapazitaet_kwh": _max(f("speicher_kapazitaet_kwh")),
        "speicher_auslastungs_basis_kwh": summe(f("speicher_auslastungs_basis_kwh")),
        "speicher_auslastung_prozent": q_auslastung.wert,
        "speicher_auslastung_zaehler_kwh": q_auslastung.zaehler,
        "speicher_auslastung_nenner_kwh": q_auslastung.nenner,
        "speicher_auslastung_fenster": q_auslastung.fenster_text,
        "speicher_ersparnis_euro": summe(f("speicher_ersparnis_euro")),
        "hat_speicher": any(m.get("hat_speicher") for m in monate),
        "speicher_soc_drift_signifikant": False,
        "speicher_wirkungsgrad_quelle": eta.quelle,
        "speicher_effektiver_ladepreis_cent": mittel(f("speicher_effektiver_ladepreis_cent")),
        "speicher_effektiver_ladepreis_quelle": next(
            (m.get("speicher_effektiver_ladepreis_quelle") for m in monate if m.get("speicher_effektiver_ladepreis_quelle")),
            None),
        "speicher_ladung_netz_kosten_euro": summe(f("speicher_ladung_netz_kosten_euro")),
        "speicher_ladung_netz_preis_cent": q_netzladung.wert,
        "speicher_ladung_netz_preis_quelle": next(
            (m.get("speicher_ladung_netz_preis_quelle") for m in monate if m.get("speicher_ladung_netz_preis_quelle")),
            None),

        "wp_strom_kwh": wp_strom,
        "wp_waerme_kwh": summe(f("wp_waerme_kwh")),
        "wp_heizung_kwh": summe(f("wp_heizung_kwh")),
        "wp_warmwasser_kwh": summe(f("wp_warmwasser_kwh")),
        "wp_strom_heizen_kwh": summe(f("wp_strom_heizen_kwh")),
        "wp_modus_strom_heizen_kwh": modus_heizen,
        "wp_modus_strom_kuehlen_kwh": modus_kuehlen,
        "wp_modus_strom_warmwasser_kwh": modus_ww,
        "wp_modus_abdeckung_h": summe(f("wp_modus_abdeckung_h")),
        "wp_modus_gemessen": any(bool(m.get("wp_modus_gemessen")) for m in monate),
        "wp_modus_nicht_aufgeteilt_kwh": kz("wp_modus_nicht_aufgeteilt_kwh", max(
            0,
            (wp_strom if wp_strom is not None else 0) - (modus_heizen if modus_heizen is not None else 0)
            - (modus_kuehlen if modus_kuehlen is not None else 0)
            - (modus_ww if modus_ww is not None else 0),
        )),
        "wp_modus_strom_lueften_kwh": kz("wp_modus_strom_lueften_kwh", summe(f("wp_modus_strom_lueften_kwh"))),
        "wp_modus_strom_entfeuchten_kwh": kz("wp_modus_strom_entfeuchten_kwh", summe(f("wp_modus_strom_entfeuchten_kwh"))),
        "wp_modus_nutzenergie_lueften_kwh": kz(
            "wp_modus_nutzenergie_lueften_kwh", summe(f("wp_modus_nutzenergie_lueften_kwh"))),
        "wp_modus_nutzenergie_entfeuchten_kwh": kz(
            "wp_modus_nutzenergie_entfeuchten_kwh", summe(f("wp_modus_nutzenergie_entfeuchten_kwh"))),
        "wp_modus_strom_bezug_kwh": kz("wp_modus_strom_bezug_kwh", summe(f("wp_modus_strom_bezug_kwh"))),
        "wp_jaz": kz("wp_cop"),
        "wp_jaz_grund": kz("wp_cop_grund"),
        "wp_jaz_hinweis": kz("wp_cop_hinweis"),
        "wp_jaz_zaehler_kwh": kz("wp_jaz_zaehler_kwh"),
        "wp_jaz_nenner_kwh": kz("wp_jaz_nenner_kwh"),
        "wp_waerme_abgeleitet": kz("wp_waerme_abgeleitet", any(bool(m.get("wp_waerme_abgeleitet")) for m in monate)),
        "wp_waerme_herkunft": kz("wp_waerme_herkunft"),
        "wp_ersparnis_vorbehalt": kz("wp_ersparnis_vorbehalt"),
        "wp_jaz_heizen": kz("wp_jaz_heizen"),
        "wp_jaz_heizen_grund": kz("wp_jaz_heizen_grund"),
        "wp_jaz_warmwasser": kz("wp_jaz_warmwasser"),
        "wp_jaz_warmwasser_grund": kz("wp_jaz_warmwasser_grund"),
        "wp_jaz_kuehlen": kz("wp_jaz_kuehlen"),
        "wp_jaz_kuehlen_grund": kz("wp_jaz_kuehlen_grund"),
        "wp_jaz_ist_schranke": kz("wp_cop_ist_schranke", False),
        "wp_jaz_schranke_hinweis": kz("wp_cop_schranke_hinweis"),
        "wp_geraete": kz("wp_geraete", []),
        "wp_moeglich": kz("wp_moeglich", []),
        "wp_kaelte_kwh": (k.get("wp_kaelte_kwh") if k is not None else summe(f("wp_kaelte_kwh"))),
        "wp_strom_warmwasser_kwh": summe(f("wp_strom_warmwasser_kwh")),
        "wp_starts_summe_monat": summe(f("wp_starts_summe_monat")),
        "wp_starts_max_tag": _max(f("wp_starts_max_tag")),
        "wp_betriebsstunden_summe_monat": summe(f("wp_betriebsstunden_summe_monat")),
        "wp_betriebsstunden_max_tag": _max(f("wp_betriebsstunden_max_tag")),
        "hat_waermepumpe": any(m.get("hat_waermepumpe") for m in monate),

        "emob_ladung_kwh": summe(f("emob_ladung_kwh")),
        "emob_km": summe(f("emob_km")),
        "emob_verbrauch_100km": emob.wert,
        "emob_verbrauch_quelle": emob.quelle,
        "emob_verbrauch_basis_kwh": summe(f("emob_verbrauch_basis_kwh")),
        "emob_ladung_gesamt_kwh": summe(f("emob_ladung_gesamt_kwh")),
        "emob_ladung_pv_kwh": summe(f("emob_ladung_pv_kwh")),
        "emob_ladung_netz_kwh": summe(f("emob_ladung_netz_kwh")),
        "emob_ladung_extern_kwh": summe(f("emob_ladung_extern_kwh")),
        "emob_v2h_kwh": summe(f("emob_v2h_kwh")),
        "hat_emobilitaet": any(m.get("hat_emobilitaet") for m in monate),

        "bkw_erzeugung_kwh": summe(f("bkw_erzeugung_kwh")),
        "bkw_eigenverbrauch_kwh": summe(f("bkw_eigenverbrauch_kwh")),
        "hat_balkonkraftwerk": any(m.get("hat_balkonkraftwerk") for m in monate),

        "sonstiges_erzeugung_kwh": summe(f("sonstiges_erzeugung_kwh")),
        "sonstiges_eigenverbrauch_kwh": summe(f("sonstiges_eigenverbrauch_kwh")),
        "sonstiges_einspeisung_kwh": summe(f("sonstiges_einspeisung_kwh")),
        "sonstiges_verbrauch_kwh": summe(f("sonstiges_verbrauch_kwh")),
        "abgabe_dritte_kwh": summe(f("abgabe_dritte_kwh")),
        "sonstiges_bezug_pv_kwh": summe(f("sonstiges_bezug_pv_kwh")),
        "sonstiges_bezug_netz_kwh": summe(f("sonstiges_bezug_netz_kwh")),
        "sonstiges_geraete": sonstiges_geraete,
        "hat_sonstiges": any(m.get("hat_sonstiges") for m in monate),

        "einspeise_erloes_euro": summe(f("einspeise_erloes_euro")),
        "einspeisung_neg_preis_kwh": summe(f("einspeisung_neg_preis_kwh")),
        "nicht_vergueteter_erloes_euro": summe(f("nicht_vergueteter_erloes_euro")),
        "netzbezug_kosten_euro": summe(f("netzbezug_kosten_euro")),
        "netzbezug_arbeitspreis_kosten_euro": summe(f("netzbezug_arbeitspreis_kosten_euro")),
        "ev_ersparnis_euro": summe(f("ev_ersparnis_euro")),
        "bkw_ersparnis_euro": summe(f("bkw_ersparnis_euro")),
        "erzeuger_erloes_euro": summe(f("erzeuger_erloes_euro")),
        "ust_eigenverbrauch_euro": summe(f("ust_eigenverbrauch_euro")),
        "netto_ertrag_euro": leiter.netto_ertrag,
        "wp_ersparnis_euro": summe(f("wp_ersparnis_euro")),
        "emob_ersparnis_euro": summe(f("emob_ersparnis_euro")),
        "sonstige_ertraege_euro": _oder0(summe(f("sonstige_ertraege_euro"))),
        "sonstige_ausgaben_euro": _oder0(summe(f("sonstige_ausgaben_euro"))),
        "sonstige_netto_euro": _oder0(summe(f("sonstige_netto_euro"))),
        "dienstliche_ladekosten_euro": _oder0(summe(f("dienstliche_ladekosten_euro"))),
        "anlage_sonstige_ertraege_euro": _oder0(summe(f("anlage_sonstige_ertraege_euro"))),
        "anlage_sonstige_ausgaben_euro": _oder0(summe(f("anlage_sonstige_ausgaben_euro"))),
        "betriebskosten_anteilig_euro": summe(f("betriebskosten_anteilig_euro")),
        "ergebnis_vor_betriebskosten_euro": leiter.vor_betriebskosten,
        "ergebnis_euro": leiter.ergebnis,
        "ergebnis_herleitung": herleitung_als_dict(leiter),
        "fehlende_posten": list(leiter.fehlende_posten),
        "soll_erfuellung_prozent": soll.prozent,
        "soll_erfuellung_monat_prozent": None,
        "soll_fenster_text": soll.fenster_text,

        "netzbezug_preis_cent": gewichtet(netzbezug_preis_effektiv, f("netzbezug_kwh")),
        "einspeise_preis_cent": gewichtet(f("einspeise_preis_cent"), f("einspeisung_kwh")),
        "netzbezug_durchschnittspreis_cent": (
            gewichtet(netzbezug_preis_effektiv, f("netzbezug_kwh"))
            if any(m.get("netzbezug_durchschnittspreis_cent") is not None for m in monate) else None
        ),
        # N-610-Nacharbeit: dieselbe Regel für die gepflegte Einspeisevergütung — trägt ein Monat sie, ist der Jahreswert der
        # einspeisegewichtete Ø des aufgelösten Satzes (`einspeise_preis_cent` = gepflegt, sonst Tarif), sonst None.
        "einspeise_durchschnittspreis_cent": (
            gewichtet(f("einspeise_preis_cent"), f("einspeisung_kwh"))
            if any(m.get("einspeise_durchschnittspreis_cent") is not None for m in monate) else None
        ),
        "grundgebuehr_euro": summe(f("grundgebuehr_euro")),
        "zaehlergebuehr_euro_jahr": next(
            (v for v in reversed(f("zaehlergebuehr_euro_jahr")) if v is not None), None),

        "soll_pv_kwh": summe(f("soll_pv_kwh")),
        "soll_pv_tage": summe(f("soll_pv_tage")),
        "soll_pv_tage_gesamt": summe(f("soll_pv_tage_gesamt")),
        "grundlast_kw": mittel(f("grundlast_kw")),
        "grundlast_kwh": gl_kwh,
        "grundlast_anteil_prozent": gl_anteil,
        "vorjahr": None,

        "investitionen_financials": list(financials.values()),
        "komponenten_geraete": geraete,
        "feld_quellen": feld_quellen,
    }


def herleitung_als_dict(leiter: ErgebnisLeiter, runde: Optional[int] = None) -> dict[str, Any]:
    """Die Herleitung als Antwortfeld (``ergebnis_herleitung``). ``runde`` rundet NUR die Ausgabe (Antwortrand)."""
    r = (lambda v: round(v, runde) if v is not None else None) if runde is not None else (lambda v: v)  # noqa: E731
    return {
        stufe: {
            "formel": h.formel,
            "eingesetzte_werte": [
                {"name": w.name, "betrag_euro": r(w.betrag), "feld": w.feld, "vorzeichen": w.vorzeichen}
                for w in h.eingesetzte_werte
            ],
            "ergebnis_euro": r(h.ergebnis),
        }
        for stufe, h in leiter.herleitung.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# Vergleichsjahre (Vorjahr / Ø-Jahr) aus der Monatsreihe
# ─────────────────────────────────────────────────────────────────────────────

def jahr_vergleich_aus(
    zeilen: Sequence[Mapping[str, Any]], jahr: int, auswahl: Optional[Sequence[int]] = None,
) -> dict[str, Any]:
    """Σ der aggregierten Monatszeilen EINES Jahres, wahlweise nur über eine Monatsauswahl (N-37).

    Wie ``jahrVergleichAus`` (Client bis 03.10.2026), aber die Autarkie **paarweise** (R-Q): ein Monat ohne
    Gesamtverbrauch fällt aus Zähler und Nenner.
    """
    zulaessig = set(auswahl) if auswahl is not None else None
    j = [r for r in zeilen if r.get("jahr") == jahr and (zulaessig is None or r.get("monat") in zulaessig)]
    s = lambda feld: summe(r.get(feld) for r in j)  # noqa: E731
    autarkie = quote_paarweise(j, "eigenverbrauch_kwh", "gesamtverbrauch_kwh")
    return {
        "jahr": jahr,
        "pv": s("pv_erzeugung_kwh"),
        "ev": s("eigenverbrauch_kwh"),
        "direkt": s("direktverbrauch_kwh"),
        "einsp": s("einspeisung_kwh"),
        "netz": s("netzbezug_kwh"),
        "gesamt": s("gesamtverbrauch_kwh"),
        "autarkie": autarkie.wert,
        # Zähler/Nenner der paarweisen Quote — das Ø-Jahr mittelt DIESE, nicht die Prozente und nicht die freien
        # Summen (sonst stünde der Monat ohne Gesamtverbrauch im Ø wieder im Zähler, N-584 eine Ebene höher).
        "autarkie_zaehler": autarkie.zaehler,
        "autarkie_nenner": autarkie.nenner,
        "monate": sorted({r.get("monat") for r in j}),
    }


def mittel_jahre(
    jahre: Sequence[Mapping[str, Any]], grundgesamtheit: Optional[Sequence[int]] = None,
) -> Optional[dict[str, Any]]:
    """Ø über mehrere Vergleichsjahre — nur Jahre, die die Grundgesamtheit GANZ abdecken (wie ``mittelJahre``).

    Die Autarkie des Mittels ist die Quote der gemittelten paarweisen Zähler und Nenner der Jahre — nicht mehr das
    Mittel der Jahres-Prozente (N-604-Klasse, dieselbe Regel wie R-Q).
    """
    g = set(grundgesamtheit) if grundgesamtheit else None
    beitragend = [
        j for j in jahre
        if j["monate"] and (g is None or g.issubset(set(j["monate"])))
    ]
    if not beitragend:
        return None
    m = lambda feld: mittel(j.get(feld) for j in beitragend)  # noqa: E731
    paar = [j for j in beitragend if j.get("autarkie_zaehler") is not None and j.get("autarkie_nenner") is not None]
    autarkie = (
        quote(mittel(j["autarkie_zaehler"] for j in paar), mittel(j["autarkie_nenner"] for j in paar))
        if paar else None
    )
    return {
        "jahr": 0,
        "pv": m("pv"), "ev": m("ev"), "direkt": m("direkt"),
        "einsp": m("einsp"), "netz": m("netz"), "gesamt": m("gesamt"),
        "autarkie": autarkie,
        "monate": sorted({x for j in beitragend for x in j["monate"]}),
        "count": len(beitragend),
    }
