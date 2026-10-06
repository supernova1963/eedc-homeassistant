"""Monats-Fakten — die Feldgruppen des `MonatsFakt` (Konzept §3): Zähler, Erzeugung, BKW, Speicher, E-Mob, Sonstiges,
Tarif, EEG, Meta und der Fakt selbst; dazu der Monatsschlüssel und die Quellenmarken der Tageswerte (N-121).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from backend.core.berechnungen import PvModulWert, VerbrauchsKennzahlen
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.models.monatsdaten import Monatsdaten
from backend.services.eauto_wirtschaftlichkeit import EmobLadungPool
from backend.services.monats_fakten.fakten_wp import WpFakten


# (jahr, monat) — die Achse dieser Schicht.
MonatsSchluessel = tuple[int, int]

#: Feldgruppen, die aus der lokalen Tagesebene **gefüllt** werden können, wenn
#: die DB-Quelle für sie nichts hergibt (``inkl_nur_tageswerte``, Fund N-121).
#: Sie landen in ``MetaFakten.tageswert_gruppen`` — eine Sicht, die zwischen
#: „kein Gerät" und „aus Tageswerten belegt" unterscheiden muss, liest sie dort,
#: statt aus einer 0 zu raten (P4).
TAGESWERT_ZAEHLER = "zaehler"

TAGESWERT_PV = "pv"

TAGESWERT_BKW = "bkw"

TAGESWERT_SPEICHER = "speicher"

#: Sonderfall unter den Gruppen: hier kommt aus der Tagesebene **keine Menge**,
#: sondern nur die *Aufteilung* der Heimladung in PV und Netz (N-141 Weg c).
#: Die Ladungsmenge selbst stammt weiter aus der Monatszeile.
TAGESWERT_EMOB_ANTEIL = "emob_anteil"
#: HA-Bauform E4c: die Lademengen (Wallbox/E-Auto) aus der E-Mob-Gruppe der Kanäle, nicht aus einer Monatszeile.
TAGESWERT_EMOB = "emob"
#: HA-Bauform E4c: die Sonstiges-Geräte (Verbraucher aus ihrer Gruppe, Erzeuger aus dem Kanal-Monat der Bilanz).
TAGESWERT_SONSTIGES = "sonstiges"
#: HA-Bauform E4d: die Wärmepumpen (Strom, Wärme, Betriebsart-Strom, Kälte, Strom je Betriebsart) aus der WP-Gruppe der
#: Kanäle, nicht aus einer Monatszeile.
TAGESWERT_WP = "waermepumpe"

# ═══════════════════════════════════════════════════════════════════════════
# Feldgruppen (KONZEPT-MONATS-FAKTEN.md §3)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ZaehlerFakten:
    """Die gemessenen Zählerwerte des Monats (``Monatsdaten``)."""

    einspeisung_kwh: float = 0.0
    netzbezug_kwh: float = 0.0

@dataclass(frozen=True)
class ErzeugungFakten:
    """Alles, was im Monat hinter dem Hauszähler erzeugt wurde.

    Drei Summen, die **nicht** dasselbe sind und deshalb getrennt stehen:

    - ``pv_module_kwh`` — die P7-aufgelöste Modul-PV. Fehlt einem aktiven Modul der
      Wert und gibt es kein Aggregat, trägt sie seit N-626 (Gernot 04.10.2026) die
      **vorhandenen** Werte (``pv_teilsumme_je_monat``) und ``pv_vollstaendig`` ist
      ``False``; bis dahin war sie dort ``None`` (N42) und mit ihr fiel die ganze
      Modulsumme aus ``pv_kwh``. ``None`` heißt jetzt: kein Modul hat einen Wert.
      Wer summiert, behandelt ``None`` als Lücke, **nie** als 0. Ein Anlagen-Aggregat steht für alle PV-Quellen: die
      Module bekommen nur, was nach Abzug der eigenen BKW-Werte bleibt (N-611),
      und teilen diesen Rest nach kWp mit den Balkonkraftwerken ohne eigenen
      Wert (N-621, ``bkw_aus_anlagenwert_kwh``).
    - ``pv_kwh`` — Module + Balkonkraftwerk (eigener Wert ``bkw_kwh`` **und**
      Anteil am Anlagenwert ``bkw_aus_anlagenwert_kwh``). Die PV-Achse:
      spezifischer Ertrag, Performance Ratio, SOLL/IST **und** der Eingang der
      Finanz-Zeile (P9).
    - ``hinter_zaehler_kwh`` — zusätzlich die sonstigen Erzeuger (BHKW/Mini-KWK).
      **Nur** diese Summe geht in Eigenverbrauch/Autarkie: an EINEM Netzanschluss
      messen die Zähler die Summe aller dahinter liegenden Erzeuger (v3.45.4).
      Sie gehört ausdrücklich **nicht** in PV-eigene Kennzahlen — ein BHKW ist
      energetisch Erzeuger, aber kein PV-Modul.
    """

    pv_module_kwh: Optional[float] = None
    bkw_kwh: float = 0.0
    sonstige_erzeuger_kwh: float = 0.0
    pv_kwh: float = 0.0
    hinter_zaehler_kwh: float = 0.0
    #: Pro-Modul-Auflösung mit Quelle/Status je Investition (``PvModulWert``) —
    #: für String-Vergleiche, die den einzelnen Wert und seine Herkunft zeigen.
    pv_je_modul: dict[int, PvModulWert] = field(default_factory=dict)
    #: False = die Modul-Auflösung hat eine Lücke (``pv_module_kwh is None``).
    pv_vollstaendig: bool = True
    #: N-621: Σ der Anteile, die Balkonkraftwerke OHNE eigenen Wert in einem
    #: Monat mit **gespeichertem** Anlagenwert (``Monatsdaten.pv_erzeugung_kwh``)
    #: bekommen — der kWp-Anteil am Rest, den die eigenen Werte aller Quellen
    #: nicht erklären. Additiv in ``pv_kwh`` und ``hinter_zaehler_kwh``; ohne
    #: Anlagenwert 0.0. Bewusst **nicht** in ``bkw_kwh`` und nicht in
    #: ``BkwFakten``: das sind die eigenen Werte des Geräts (IST-Quelle je Typ),
    #: und die BKW-Finanzzeile bekäme sonst eine verteilte Zahl als eigenen
    #: Ertrag. Ein BKW mit Anteil trägt im Monat keinen Ersatz-Eigenverbrauch
    #: (P9-Zusatzregel, ``roh.py::falte``) und keinen Tageswert (``bau.py``).
    bkw_aus_anlagenwert_kwh: float = 0.0
    #: HA-Bauform E4b (N-588 — geführt, NICHT bewertet): ``max(0, Σ String-Zähler − Anlagenzähler)`` des Monats aus
    #: dem Kanal-Leser (``services/kanal/bilanz_leser``, W2-R3). ``None`` ohne Anlagenzähler oder ohne Kanal-Deckung
    #: des Monats — der Bestandspfad (gespeicherte Werte, Tageszeilen) liefert keinen Wert. Geht in keine Bilanz,
    #: keine Ersparnis und kein CO₂: ``pv_kwh``, Eigenverbrauch und Ergebnis-Leiter bleiben die Σ der Strings.
    wandlungsverluste_kwh: Optional[float] = None
    #: Σ der Geräte-Werte desselben Kanal-Monats — Bezug der Prozentangabe (``wandlungsverluste_prozent``).
    wandlungsverluste_bezug_kwh: Optional[float] = None

@dataclass(frozen=True)
class BkwFakten:
    """Balkonkraftwerk — Erzeugung, gemessener EV und der **Rest**-EV (P9).

    ``rest_eigenverbrauch_kwh`` ist der Wert für die Finanz-Zeile und kommt aus
    ``bkw_finanz_beitrag``: er ist **nur** dann besetzt, wenn die Erzeugung des
    Monats fehlt (Datenlücke) — sonst steckt der Eigenverbrauch bereits in der
    Ableitung aus ``pv_kwh`` und ein zweiter Term wäre Doppelzählung.
    ``eigenverbrauch_gemessen_kwh`` bleibt daneben der ROHE Wert für die Anzeige.

    ``erzeugung_je_investition`` ist dieselbe Erzeugung, nur nicht summiert (F-10):
    String-Vergleiche stellen **jeden** Erzeuger einzeln seinem SOLL gegenüber,
    und ein Balkonkraftwerk steht nicht in ``ErzeugungFakten.pv_je_modul`` — dort
    stehen ausschließlich ``pv-module``. Bewusst ein eigenes Feld statt einer
    Erweiterung von ``pv_je_modul``: dessen Summe ``pv_module_kwh`` geht in die
    ROI-Rechnung, wo das BKW eine eigene Zeile hat und sonst doppelt zählte.
    """

    erzeugung_kwh: float = 0.0
    eigenverbrauch_gemessen_kwh: float = 0.0
    rest_eigenverbrauch_kwh: float = 0.0
    speicher_ladung_kwh: float = 0.0
    speicher_entladung_kwh: float = 0.0
    #: ``{investition_id: erzeugung_kwh}`` aus den IMD-Zeilen des Monats.
    #: Σ der Werte == ``erzeugung_kwh`` — **außer** wenn der Monat seine BKW-Zahl
    #: aus der Tagesebene bezieht (``TAGESWERT_BKW``): die Tagessumme ist
    #: anlagenweit und lässt sich nicht je Investition aufteilen. Dann bleibt
    #: dieses Feld **leer**, während ``erzeugung_kwh`` einen Wert trägt. Wer je
    #: Investition auswertet, behandelt das wie eine Lücke, nicht wie 0.
    erzeugung_je_investition: dict[int, float] = field(default_factory=dict)

@dataclass(frozen=True)
class SpeicherFakten:
    """Stationärer Speicher des Monats.

    ``netzladung_*``: Arbitrage. Der Ø-Ladepreis wird **mengengewichtet** und nur
    über Zeilen mit gepflegtem Preis gebildet (Summe + Gewicht getrennt gehalten,
    damit ein Aufrufer über Monate hinweg korrekt weiter gewichten kann statt
    Mittelwerte zu mitteln).
    """

    ladung_kwh: float = 0.0
    entladung_kwh: float = 0.0
    netzladung_kwh: float = 0.0
    netzladung_preis_summe_cent_kwh: float = 0.0
    netzladung_gewicht_kwh: float = 0.0

    @property
    def netzladung_preis_cent(self) -> Optional[float]:
        """Mengengewichteter Ø Ladepreis — ``None`` ohne gepflegten Preis."""
        if self.netzladung_gewicht_kwh <= 0:
            return None
        return self.netzladung_preis_summe_cent_kwh / self.netzladung_gewicht_kwh

@dataclass(frozen=True)
class EmobFakten:
    """E-Mobilität des Monats — **ohne Dienstwagen**.

    ⭐ **N-555 Stufe 2 (Konzept Heimladung/Fahrverbrauch 7.2, Regel 3, G1):** der Topf
    ``ladung_kwh``/``ladung_pv_kwh``/``ladung_netz_kwh`` ist die **private Heimladung** —
    ``Σ je_auto`` (eigene Messungen, zugeordneter Rest, Schätzungen der privaten Autos),
    in jedem Monat, auch wenn die Wallbox geladen hat. Gast und Dienstwagen stehen nicht
    darin; die **Messung der Wallbox** (Regel 0, mit Gast und Dienstwagen) ist
    ``wallbox_summe``, der Rest ohne Empfänger ``rest_*`` bei ``rest_zugeordnet = False``,
    die gemessene dienstliche Ladung ``dienstlich_gemessen_*``. Der Absatz unten
    beschreibt die Quellenwahl bis Stufe 1 (eine Quelle je Monat); ``quelle`` sagt seit
    Stufe 2 nur noch, was den Monat bestimmt.

    Die Heimladungs-Trias (``ladung_kwh == ladung_pv_kwh + ladung_netz_kwh``)
    kommt geschlossen aus EINER Quelle (``get_emob_heimladung_canonical``,
    Entscheidung 1 von ``KONZEPT-WALLBOX-EAUTO.md``); feldweises ``max()`` über
    getrennte Töpfe konnte einen PV-Anteil > 100 % erzeugen (#262).

    **Die Quellenwahl ist hier eine Monats-Entscheidung.** Wer über einen längeren
    Zeitraum aggregiert, hat die Wahl: Σ der Monats-Trias (jeder Monat wählt seine
    Quelle) **oder** eine EINMALIGE Poolung über den ganzen Zeitraum. Beides ist
    vertretbar und beides ist heute im Baum — die Cockpit-Übersicht poolt einmal
    global. Damit ein Umhängen keine Zahl **still** verschiebt, reicht diese
    Gruppe die Rohdicts beider Quellen mit durch (``eauto_ladedaten`` /
    ``wallbox_ladedaten``, bereits dienstwagen- und laufzeitgefiltert): der
    Aufrufer kann sie über denselben SoT global poolen.

    ``eauto_summe`` / ``wallbox_summe`` sind dieselben Rohdicts, aber je Quelle
    **getrennt** und über denselben SoT-Leser aufsummiert
    (``summiere_emob_quelle``) — für Sichten, die die beiden Seiten einzeln
    ausweisen müssen statt sie zu poolen. Sie sind **kein** Ersatz
    für die Trias oben: wer eine Gesamt-Heimladung braucht, nimmt den Pool,
    sonst zählt derselbe Fluss zweimal (die Wallbox misst am Ladepunkt, was das
    E-Auto als Ladung meldet). ``quelle`` ist in beiden leer — die Quellen-Wahl
    trifft nur der Pool.

    ⚠ **Die durchgereichten Zeilen tragen den abgeleiteten PV-Anteil** (F-16):
    ``eauto_ladedaten``/``wallbox_ladedaten`` und die beiden Summen darüber sind
    bereits durch ``services/emob_ladeanteil.reichere_ladezeilen_an`` gelaufen,
    genauso wie die Trias oben. Wer sie neu poolt, bekommt deshalb dieselbe
    Aufteilung wie die Trias — vorher bekam er die ungeteilten Rohwerte und
    zeigte 0 % neben dem abgeleiteten Anteil derselben Größe.

    ``dienstlich_*`` ist der herausgefilterte Anteil — nicht verworfen, sondern
    getrennt ausgewiesen, weil er als *Ausgabe* (dienstliche Ladekosten) bewertet
    wird. Seit N-633 (05.10.2026) bewertet ihn die Schicht selbst
    (``dienstliche_ladekosten_euro``, Layer-Formel ``berechne_dienstliche_ladekosten``
    mit den Preisen aus ``TarifFakten`` desselben Monats) — der eine Posten, den alle
    Sichten lesen. Bis dahin rechneten Übersicht, HA-Export und Aussichten ihn je
    selbst und falteten ihn in die Sonstigen Positionen; Cockpit → Monat/Jahr,
    Tabelle und PDF führten ihn gar nicht.
    """

    ladung_kwh: float = 0.0
    ladung_pv_kwh: float = 0.0
    ladung_netz_kwh: float = 0.0
    #: Steht die Aufteilung ``ladung_pv_kwh``/``ladung_netz_kwh`` so in den
    #: Monatsdaten, oder ist sie aus der Tagesebene **abgeleitet** (N-141 Weg c)?
    #: Eine Wallbox misst ihren PV-Anteil nicht; fehlt er, galt bisher die ganze
    #: Heimladung als Netzstrom. Wer die Zahl anzeigt, sagt mit diesem Flag, dass
    #: sie gerechnet ist — eine Schätzung, die aussieht wie eine Messung, ist
    #: genau der Fehler, den die P4-Linie verhindern soll.
    #: ⚠ **Die Trias bleibt geschlossen**: abgeleitet wird der *Anteil*, und er
    #: wird auf die kanonische ``ladung_kwh`` angewandt — nicht die kWh der
    #: Tagesebene übernommen (sonst #262-Klasse, PV-Anteil > 100 %).
    ladung_anteil_abgeleitet: bool = False
    extern_kwh: float = 0.0
    extern_euro: float = 0.0
    ladevorgaenge: float = 0.0
    quelle: str = "leer"
    km: float = 0.0
    fahrverbrauch_kwh: float = 0.0
    v2h_entladung_kwh: float = 0.0
    #: km je Fahrzeug (``Investition.id``) — Voraussetzung dafür, dass eine
    #: Ersparnis je Fahrzeug mit DESSEN Verbrauchs-Parameter gerechnet wird (G20-2).
    km_je_fahrzeug: dict[int, float] = field(default_factory=dict)
    #: Elektrischer Fahrverbrauch je Fahrzeug (``Investition.id``) — dieselbe
    #: Begründung wie ``km_je_fahrzeug`` eine Zeile höher, eine Stufe weiter:
    #: der elektrische Fahranteil eines Plug-in-Hybrids folgt aus DESSEN
    #: Fahrverbrauch und DESSEN ``verbrauch_kwh_100km`` (#331, Phase 4). Die
    #: anlagenweite Summe ``fahrverbrauch_kwh`` darüber bleibt unverändert —
    #: additiv statt umgedeutet (Muster ``BkwFakten.erzeugung_je_investition``).
    fahrverbrauch_je_fahrzeug: dict[int, float] = field(default_factory=dict)
    dienstlich_ladung_pv_kwh: float = 0.0
    dienstlich_ladung_netz_kwh: float = 0.0
    #: N-555: stammt die dienstliche Menge (ganz oder teilweise) aus dem
    #: Fahrverbrauch eines Dienstwagens ohne eigene Ladefelder? Die Menge ist
    #: dieselbe wie vor N-555 (Konzept Regel 2-Ü: Dienstwagen unverändert); das
    #: Kennzeichen sagt nur, dass sie eine Schätzung ist, statt es zu verschweigen.
    dienstlich_geschaetzt: bool = False
    #: N-633: die dienstlichen Ladekosten des Monats in € (PV-Anteil × Netzbezugspreis +
    #: Netzanteil × effektiver Wallbox-Preis, ``core/berechnungen/dienstliche_ladekosten.py``),
    #: ungerundet. Posten „Dienstliche Ladekosten" der Ergebnis-Leiter (Stufe 1, −).
    #: ⛔ NICHT Teil von ``SonstigesFakten.ausgaben_euro`` — die ist Eingang des
    #: Kapitaleinsatzes (F-19), der Posten ist laufender Aufwand.
    dienstliche_ladekosten_euro: float = 0.0
    #: ⭐ N-555 Stufe 2 (Konzept Regel 2/3): die Heimladung JEDES privaten Autos im Monat
    #: (``inv_id → AutoHeimladung``: gemessen, Rest-Anteil nach km, Schätzung oder 0) — aus
    #: der einen Funktion. Wer je Fahrzeug rechnet (Übersicht, Jahresbericht), liest hier.
    je_auto: dict = field(default_factory=dict)
    #: Regel 2 Schritt 2/3: der Rest der Wallbox und ob er an private Autos ging.
    rest_pv_kwh: float = 0.0
    rest_netz_kwh: float = 0.0
    rest_zugeordnet: bool = False
    #: Trägt eine private Wallbox einen Wert (auch 0) oder — laufend — eine Quelle?
    wallbox_hat_wert: bool = False
    #: Ist eine private Wallbox im Monat in Betrieb (auch ohne Zeile)?
    wallbox_in_betrieb: bool = False
    #: Regel 3 / E3: die gemessene dienstliche Ladung (vom Rest abgezogen) — der
    #: Community-Payload kürzt das Wallbox-Feld darum.
    dienstlich_gemessen_pv_kwh: float = 0.0
    dienstlich_gemessen_netz_kwh: float = 0.0
    #: Regel 3 / E3 / E7: Dienstwagen ohne bzw. mit eigener Messung (``inv_id``s).
    dienstwagen_ungemessen: frozenset = frozenset()
    dienstwagen_gemessen: frozenset = frozenset()
    #: Regel 3: eine dienstliche Wallbox in Betrieb (dann zählen die Dienstwagen nicht).
    dienstliche_wallbox_in_betrieb: bool = False
    #: E3: ist im Monat ein Dienstwagen in Betrieb (auch ohne Zeile)? Dann kann er an der
    #: privaten Wallbox geladen haben — die Zahl der Ladevorgänge ist nicht aufteilbar.
    dienstwagen_in_betrieb: bool = False
    #: Regel 8 (E5): E-Autos, deren gespeichertes ``ladung_kwh`` „Heim: gesamt" ist (nach
    #: Herkunft) — für *Cockpit → Monat*, das die gespeicherte Zeile neu entscheidet.
    heim_gesamt_ids: frozenset = frozenset()
    #: Regel 3: die gespeicherten Zeilen der Dienstwagen und dienstlichen Wallboxen
    #: (``inv_id →``, roh) — für *Cockpit → Monat*, das den Monat neu entscheidet.
    dienstlich_ladedaten_je_inv: dict = field(default_factory=dict)
    eauto_ladedaten: tuple[dict, ...] = ()
    wallbox_ladedaten: tuple[dict, ...] = ()
    #: N-555: dieselben privaten Zeilen (E-Auto und Wallbox) je ``Investition.id`` —
    #: für *Cockpit → Monat*, das die gespeicherte Zeile mit Live- und
    #: HA-Statistik-Werten zusammenführt und dann die eine Funktion fragt.
    ladedaten_je_inv: dict[int, dict] = field(default_factory=dict)
    eauto_summe: EmobLadungPool = field(
        default_factory=lambda: EmobLadungPool(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "")
    )
    wallbox_summe: EmobLadungPool = field(
        default_factory=lambda: EmobLadungPool(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "")
    )
    #: Dieselben Summen **ohne** die Ableitung — ausschließlich für den
    #: Community-Payload. Er trägt Werte an einen fremden Server, der die
    #: Rohdaten nie gesehen hat und nichts nachrechnet; eine Schätzung wäre dort
    #: in einem Benchmark nicht mehr als solche erkennbar, und der Anlagen-Hash
    #: bewegte sich ohne neue Messung. Jede andere Sicht nimmt die angereicherten
    #: Felder darüber — wer hier greift, ohne den Payload zu bauen, erzeugt genau
    #: die zweite Zahl, die F-16 aufgelöst hat.
    eauto_summe_gemessen: EmobLadungPool = field(
        default_factory=lambda: EmobLadungPool(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "")
    )
    wallbox_summe_gemessen: EmobLadungPool = field(
        default_factory=lambda: EmobLadungPool(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "")
    )

@dataclass(frozen=True)
class SonstigesGeraetFakten:
    """Die Mengen EINES sonstigen Geräts im Monat.

    Kategorie-bewusst aufgelöst wie die Anlagen-Summen: beim Erzeuger bleiben
    ``bezug_*`` leer, beim Verbraucher ``eigenverbrauch``/``einspeisung`` — die
    Entscheidung fällt ``imd_typ_beitrag``, nicht der Aufrufer (ADR-001).
    """

    erzeugung_kwh: float = 0.0
    abgabe_kwh: float = 0.0
    verbrauch_kwh: float = 0.0
    eigenverbrauch_kwh: float = 0.0
    einspeisung_kwh: float = 0.0
    bezug_pv_kwh: float = 0.0
    bezug_netz_kwh: float = 0.0
    #: Konzept §9 Weg 2: gepflegter Erlös DIESES Erzeugers in €. Er ersetzt
    #: keine Anlagengröße, sondern kommt hinzu — eedc kennt nur einen
    #: Einspeisesatz je Anlage, und der bewertet nur den Anlagenzähler.
    einspeise_erloes_euro: float = 0.0
    #: Wurde der Erlös in diesem Monat **gepflegt** — auch als 0? Die Zahl
    #: darüber trennt das nicht (fehlend und `None` werden beide zu `0.0`).
    #: Die **Kapitalrechnung** braucht die Trennung: eine gepflegte 0 heißt
    #: „unentgeltlich abgegeben" und ist eine Aussage, ein fehlender Wert heißt
    #: „nicht bewertet". Gleiche Bauform wie ``hat_erzeuger_zeile`` (ADR-002/P4).
    hat_einspeise_erloes: bool = False

@dataclass(frozen=True)
class SonstigesFakten:
    """Sonstige Verbraucher + die manuell gepflegten Finanz-Positionen.

    ``erzeugung_kwh``/``verbrauch_kwh`` stammen aus Investitionen vom Typ
    ``sonstiges`` (kategorie-bewusst aufgelöst). Die Euro-Positionen dagegen
    kommen aus **allen** sichtbaren IMD-Zeilen — unabhängig vom Typ (#310 war ein
    Typ-Ausschluss: PV/WR fehlten im Aggregat) — **plus** den Basis-Positionen auf
    der ``Monatsdaten``-Zeile (G19-1), die genau wie IMD-Positionen wirken.

    ``anlage_*_euro`` ist der **Anteil der Basis-Positionen allein** — er steckt
    in ``ertraege_euro``/``ausgaben_euro`` bereits mit drin und steht hier
    zusätzlich, weil zwei Sichten ihn getrennt ausweisen (Zeile „Anlage —
    Sonstige …" im Monatsbericht und in der Komponenten-Zeitreihe). Ohne dieses
    Feld müsste der Aufrufer ihn zurückrechnen oder ``Monatsdaten`` selbst
    anfassen — beides ist genau das, was P10 abstellt.

    ``hat_erzeuger_zeile`` trennt „Erzeuger hat 0 kWh geliefert" von „es gibt
    keinen" (P4). Feiner als der bloße Typ, weil ``sonstiges`` auch Verbraucher
    umfasst.

    ``eigenverbrauch_kwh``/``einspeisung_kwh``/``bezug_*`` sind mit **C1d**
    dazugekommen — bis dahin waren sie die einzigen Größen des Komponenten-
    Detailblocks der Monatsroute, die die Schicht nicht kannte, und genau das
    hielt die letzte anlagenweite Faltung des Baums am Leben (N-107).
    """

    erzeugung_kwh: float = 0.0
    #: §9.2 — Σ der an Dritte abgegebenen kWh (Kategorie „abgabe"). Sie stehen
    #: NICHT in ``erzeugung_kwh`` und werden in ``kennzahlen`` vom Eigenverbrauch
    #: abgezogen: der dritte Weg neben Eigenverbrauch und Netz-Einspeisung.
    abgabe_kwh: float = 0.0
    verbrauch_kwh: float = 0.0
    eigenverbrauch_kwh: float = 0.0
    einspeisung_kwh: float = 0.0
    bezug_pv_kwh: float = 0.0
    bezug_netz_kwh: float = 0.0
    #: Konzept §9 Weg 2 — Σ der gepflegten Erzeuger-Erlöse (§9-Fall: eigener
    #: Einspeisetarif). **Kein** Teil von ``ertraege_euro``: das sind die
    #: sonstigen Positionen aus dem Monatsabschluss, dies hier ist ein
    #: gemessener Monatswert je Erzeuger.
    einspeise_erloes_euro: float = 0.0
    ertraege_euro: float = 0.0
    ausgaben_euro: float = 0.0
    netto_euro: float = 0.0
    anlage_ertraege_euro: float = 0.0
    anlage_ausgaben_euro: float = 0.0
    hat_erzeuger_zeile: bool = False
    #: Gegenstück für die Verbraucherseite (Heizstab, Pool, Klimasplit). Erst
    #: mit ihm lässt sich die Spalte „Sonstiges Verbrauch" leer lassen, wo es
    #: gar kein solches Gerät gibt, statt eine 0 zu behaupten.
    hat_verbraucher_zeile: bool = False
    #: Dieselben sechs Mengen je ``Investition.id`` — die Aufschlüsselung der
    #: Summen oben, nicht eine zweite Quelle. Enthalten sind nur Geräte, die im
    #: Monat **sichtbar** waren (Laufzeit-Filter der Schicht); wer die Liste
    #: durchgeht, hat den ``ist_aktiv_im_monat``-Filter damit schon hinter sich.
    je_geraet: dict[int, SonstigesGeraetFakten] = field(default_factory=dict)

@dataclass(frozen=True)
class TarifFakten:
    """Die Preise, die für **diesen** Monat galten (ADR-002/**P8**).

    Stichtag ist der Monatserste; ein Tarif ab Monatsmitte gilt erst im
    Folgemonat. ``netzbezug_preis_cent`` ist der **effektive** Preis: der
    abgerechnete Flex-Ø des Monats hat Vorrang vor dem Stammdaten-Arbeitspreis
    (``resolve_netzbezug_preis_cent``) — wer ihn übergeht, verliert ihn still.

    Kraftstoff- und Gaspreis stehen daneben, weil sie dieselbe Stichtags-Regel
    tragen: sie sind Monatswerte der ``Monatsdaten``-Zeile, kein Stammdatum.

    ``wallbox_preis_effektiv_cent`` ist derselbe Flex-Vorrang wie oben, nur auf
    dem Wallbox-Tarif: **der abgerechnete Flex-Ø gilt für den ganzen Zähler**,
    also auch für einen dienstlich geladenen Wagen. Die dienstlichen Ladekosten
    (Cockpit/Übersicht) sind heute der einzige Konsument; für die Wärmepumpe gibt
    es die Entsprechung, sobald sie gebraucht wird — ein ungenutztes Feld wäre
    nur eine weitere Stelle, die veraltet.
    """

    netzbezug_preis_cent: float = NETZBEZUG_DEFAULT_CENT
    #: Welche Stufe der Kaskade den Preis geliefert hat (``gepflegt`` ·
    #: ``gemessen`` · ``zeitfenster`` · ``stamm``) — die Zahl allein sagt es
    #: nicht, und eine Sicht muss es aussprechen können (P4, #412).
    netzbezug_preis_herkunft: Optional[str] = None
    netzbezug_stammpreis_cent: float = NETZBEZUG_DEFAULT_CENT
    einspeiseverguetung_cent: float = EINSPEISEVERGUETUNG_DEFAULT_CENT
    grundpreis_euro_monat: float = 0.0
    wp_preis_cent: float = NETZBEZUG_DEFAULT_CENT
    wallbox_preis_cent: float = NETZBEZUG_DEFAULT_CENT
    wallbox_preis_effektiv_cent: float = NETZBEZUG_DEFAULT_CENT
    kraftstoffpreis_euro: Optional[float] = None
    gaspreis_cent_kwh: Optional[float] = None

@dataclass(frozen=True)
class EegFakten:
    """§51 EEG — Einspeisung zu negativen Preisen.

    ``None`` heißt **nicht** 0: entweder unterliegt die Anlage dem §51 nicht
    (manueller Schalter, Default aus), oder es gibt für den Monat keine
    Strompreis-Mitschrift. Eine 0 wäre dort eine Aussage, die niemand belegen kann.
    """

    neg_preis_kwh: Optional[float] = None

@dataclass(frozen=True)
class MetaFakten:
    """Herkunft und Vollständigkeit — damit eine Lücke sichtbar bleibt (P4).

    ``monatsdaten`` ist die ORM-Zeile und wird **nur** für den Flex-Ø-Override
    der Finanz-Zeile durchgereicht (P8, zweite Form). Sie ist ``None``, wenn für
    den Monat keine Zählerzeile existiert.

    ``erzeuger_aktiv`` trägt die Anschaffungsdatum-Grenze auf Monatsebene: war in
    diesem Monat überhaupt ein Erzeuger hinter dem Zähler aktiv (PV-Modul, BKW
    oder ein sonstiger Erzeuger)? Sichten, die Energiebilanz und Erträge auf das
    „PV-Fenster" beschränken, lesen dieses Flag, statt die Regel je Sicht neu zu
    bauen. Ohne registrierten Erzeuger ist es ``True`` — der Filter greift dann
    nicht und das Verhalten bleibt unverändert.

    ``typen_mit_zeile`` beantwortet „hat dieser Gerätetyp im Monat überhaupt
    etwas beigetragen?" und ist die Grundlage dafür, **``None`` statt ``0``**
    auszuliefern (P4). Es ist ausdrücklich **nicht** ``aktive_investitionen``:
    eine aktive Wärmepumpe ohne gepflegte Zeile ist aktiv und hat trotzdem nichts
    geliefert — wer die beiden verwechselt, macht aus „—" eine 0. Dienstwagen
    sind ausgenommen, weil sie auch aus dem E-Mob-Pool herausfallen.

    ``tageswert_gruppen`` nennt die Feldgruppen, die **nicht** aus der DB kommen,
    sondern aus der lokalen Tagesebene (nur mit ``inkl_nur_tageswerte``, N-121).
    Leer heißt: alles steht so in der DB. Eine Sicht, die solche Monate zeigt,
    sagt es — sie tragen weder ``id`` noch Zählerzeile, und der fehlende
    Monatsabschluss wird als Fehlerquelle ohnehin schon vom Daten-Checker
    ausgewiesen (``daten_checker/monatsdaten.py``, Kategorie
    ``MONATSDATEN_VOLLSTAENDIGKEIT``, mit Link auf den Abschluss).
    """

    monatsdaten: Optional[Monatsdaten] = None
    hat_zaehlerzeile: bool = False
    erzeuger_aktiv: bool = True
    pv_vollstaendig: bool = True
    aktive_investitionen: tuple[int, ...] = ()
    typen_mit_zeile: frozenset[str] = frozenset()
    tageswert_gruppen: frozenset[str] = frozenset()

@dataclass(frozen=True)
class MonatsFakt:
    """Die vollständige, kanonisch aufgelöste Wahrheit über EINEN Monat.

    Wer ihn hat, braucht keine ORM-Zeile mehr anzufassen und trifft keine
    Auflösungsentscheidung mehr selbst.
    """

    jahr: int
    monat: int
    zaehler: ZaehlerFakten
    erzeugung: ErzeugungFakten
    bkw: BkwFakten
    speicher: SpeicherFakten
    emob: EmobFakten
    wp: WpFakten
    sonstiges: SonstigesFakten
    tarif: TarifFakten
    eeg: EegFakten
    kennzahlen: VerbrauchsKennzahlen
    meta: MetaFakten

    @property
    def schluessel(self) -> MonatsSchluessel:
        return (self.jahr, self.monat)

    @property
    def stichtag(self) -> date:
        """Der Monatserste — der Stichtag, mit dem der Tarif geladen wurde (P8)."""
        return date(self.jahr, self.monat, 1)
