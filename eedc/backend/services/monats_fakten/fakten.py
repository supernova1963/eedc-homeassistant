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

    #: Einspeisung des Monats in kWh vom Hauszähler (``Monatsdaten.einspeisung_kwh``, ``bau._zaehler_fakten``); ohne
    #: Zeile (N-751) bzw. bei nicht erfasstem Feld der Zeile (N-736, nur wenn die Tagesebene es erfasst) steht der Wert
    #: der Tagesebene, und ``MetaFakten.einspeisung_erfasst`` sagt, ob er erfasst ist.
    einspeisung_kwh: float = 0.0
    #: Netzbezug des Monats in kWh vom Hauszähler (``Monatsdaten.netzbezug_kwh``, ``bau._zaehler_fakten``); ohne Zeile
    #: (N-751) bzw. bei nicht erfasstem Feld der Zeile (N-736, nur wenn die Tagesebene es erfasst) steht der Wert der
    #: Tagesebene, und ``MetaFakten.netzbezug_erfasst`` sagt, ob er erfasst ist.
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

    #: Σ der PV-Module des Monats in kWh aus der P7-Auflösung (``pv_monatswerte.lade_pv_je_monat``), ohne sie der
    #: Modul-Tageswert der Tagesebene (N-121), sonst die Teilsumme der vorhandenen Modulwerte (N-626) — ``None``, wenn
    #: nichts davon einen Wert hat (``bau._pv_aus_tagen``).
    pv_module_kwh: Optional[float] = None
    #: Eigene Erzeugung der Balkonkraftwerke in kWh: Σ der BKW-Zeilen ohne abtretende BKW (N-266), ohne BKW-Zeile und
    #: ohne Anteil am Anlagenwert der BKW-Tageswert bzw. der Rest des Anlagenzählers (N-640, ``bau._bkw_rest``).
    bkw_kwh: float = 0.0
    #: Σ der Erzeugung sonstiger Geräte in kWh (BHKW, Mini-KWK) aus der Kategorie-Weiche von ``imd_typ_beitrag`` —
    #: Erzeuger (mit Ersatzfeld, N-667) und Geräte ohne Kategorie; Verbraucher, Zähler und Abgabe tragen 0 — dieselbe
    #: Zahl wie ``SonstigesFakten.erzeugung_kwh``.
    sonstige_erzeuger_kwh: float = 0.0
    #: Die PV des Monats in kWh: ``pv_module_kwh`` (``None`` als 0) + ``bkw_kwh`` + ``bkw_aus_anlagenwert_kwh`` (N-621,
    #: ``bau._erzeugung``).
    pv_kwh: float = 0.0
    #: Alles hinter dem Hauszähler Erzeugte in kWh: ``pv_kwh`` + ``sonstige_erzeuger_kwh``
    #: (``energie.erzeugung_hinter_zaehler_kwh``, ``bau._erzeugung``) — der Eingang von Eigenverbrauch und Autarkie.
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
    #: N-664 (K4): dieselben Anteile je Balkonkraftwerk (``{investition_id: kwh}``, Σ = ``bkw_aus_anlagenwert_kwh``) —
    #: der Komponenten-Hub zeigt sie je Gerät mit Kennzeichen „geschätzt (kWp-Anteil)". Ein Schlüssel heißt: dieses
    #: BKW ist im Monat Empfänger des Anlagenwerts, auch mit 0 (der Anlagenwert sagt dann, dass es nichts erzeugt hat).
    #: Leer ohne Anlagenwert. Bewusst neben, nicht in ``BkwFakten`` — Begründung eine Zeile höher.
    bkw_aus_anlagenwert_je_investition: dict[int, float] = field(default_factory=dict)
    #: HA-Bauform E4b: ``max(0, Σ String-Zähler − Anlagenzähler)`` des Monats aus dem Kanal-Leser
    #: (``services/kanal/bilanz_leser``, W2-R3). ``None`` ohne Anlagenzähler oder ohne Kanal-Deckung des Monats — der
    #: Bestandspfad (gespeicherte Werte, Tageszeilen) liefert keinen Wert. Geht in keine BILANZ (F2): ``pv_kwh``,
    #: Eigenverbrauch, Autarkie und EV-Quote bleiben die Σ der Strings. Geld, USt und CO₂ bewerten den Eigenverbrauch
    #: OHNE sie, wenn der Messpunkt-Vertrag hält (N-588, ``pv_verteilung.eigenverbrauch_ohne_verluste_kwh``).
    wandlungsverluste_kwh: Optional[float] = None
    #: Σ der Geräte-Werte desselben Kanal-Monats — Bezug der Prozentangabe (``wandlungsverluste_prozent``).
    wandlungsverluste_bezug_kwh: Optional[float] = None
    #: N-588: warum die Verluste dieses Monats NICHT bewertet werden (``pv_verteilung.wandlungsverluste_grund``:
    #: ``dc_speicher`` · ``dc_speicher_angenommen`` · ``ueber_schwelle`` · ``bkw_ausserhalb``);
    #: ``None`` = bewertet bzw. keine Verluste.
    verluste_grund: Optional[str] = None

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

    #: Erzeugung der Balkonkraftwerke in kWh — dieselbe Zahl wie ``ErzeugungFakten.bkw_kwh`` (``bau._bkw_rest``: Σ der
    #: BKW-Zeilen ohne abtretende BKW, N-266, sonst Tageswert bzw. Rest des Anlagenzählers, N-640).
    erzeugung_kwh: float = 0.0
    #: Σ des gemessenen Eigenverbrauchs (``eigenverbrauch_kwh``) aller BKW-Zeilen in kWh, roh für die Anzeige
    #: (``roh._falte_bkw``).
    eigenverbrauch_gemessen_kwh: float = 0.0
    #: Ersatz-Eigenverbrauch der Finanz-Zeile in kWh (P9, ``bkw_finanz.bkw_finanz_beitrag``): der gemessene
    #: Eigenverbrauch der BKW-Zeilen ohne Erzeugung > 0, summiert — 0 für ein abtretendes BKW (N-266) und für ein BKW
    #: mit Anteil am Anlagenwert (N-621).
    rest_eigenverbrauch_kwh: float = 0.0
    #: Σ der Ladung des Speichers am Balkonkraftwerk (``speicher_ladung_kwh`` der BKW-Zeilen) in kWh — nicht Teil von
    #: ``SpeicherFakten``.
    speicher_ladung_kwh: float = 0.0
    #: Σ der Entladung des Speichers am Balkonkraftwerk (``speicher_entladung_kwh`` der BKW-Zeilen) in kWh — nicht Teil
    #: von ``SpeicherFakten``.
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

    Bedeutung beider Herkünfte: **der Preis, zu dem die Netzladung gekauft
    wurde.** Mit Speicher-Zeile ist es der Ø der Handeingabe
    (``speicher_ladepreis_cent``); im Tageswert-Rückfall (Monat ohne
    Speicher-Zeile, Entscheid Gernot 13.10.2026) der TEP-gewichtete Preis der
    Tage wie in *Cockpit → Tag* (`netzladung_tage.netzladung_aus_tagen`) — ohne
    Stundenpreis bleibt das Gewicht 0 und jeder Leser fällt auf den Bezugspreis.
    """

    #: Ladung der Speicher in kWh, Σ von ``ladung_kwh`` der Speicher-Zeilen; ohne Speicher-Zeile im Monat der Tageswert
    #: der Tagesebene (#427, ``bau._speicher_aus_tagen``).
    ladung_kwh: float = 0.0
    #: Entladung der Speicher in kWh, Σ von ``entladung_kwh`` der Speicher-Zeilen; ohne Speicher-Zeile im Monat der
    #: Tageswert der Tagesebene (#427, ``bau._speicher_aus_tagen``).
    entladung_kwh: float = 0.0
    #: Netzladung (Arbitrage) der Speicher in kWh, Σ von ``ladung_netz_kwh`` der Speicher-Zeilen; ohne Speicher-Zeile
    #: die Netzladung der Tage (``netzladung_tage.netzladung_aus_tagen``, #427), ohne Netzlade-Zähler 0.
    netzladung_kwh: float = 0.0
    #: Σ Ladepreis × Netzladung (ct/kWh × kWh) über die Speicher-Zeilen mit Ladepreis > 0 und Netzladung > 0 — der
    #: Zähler von ``netzladung_preis_cent``; ohne Speicher-Zeile die TEP-gewichtete Summe der Tage (#427).
    netzladung_preis_summe_cent_kwh: float = 0.0
    #: Σ der Netzladung der Speicher-Zeilen mit Ladepreis > 0 in kWh — der Nenner von ``netzladung_preis_cent``; ohne
    #: Speicher-Zeile das Gewicht der Tage (#427), ohne Stundenpreis 0.
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

    #: Private Heimladung des Monats in kWh: Σ der Heimladung je privatem Auto (eigene Messung, zugeordneter Rest,
    #: Schätzung — ``je_auto``), in einem Monat ohne Auto-Zeile und ohne Dienstwagen der Rest der Wallbox (W-1); Gast
    #: und Dienstwagen stehen nicht darin (N-555 Regel 3, ``emob_heimladung_phasen._topf_des_monats``).
    ladung_kwh: float = 0.0
    #: PV-Teil der privaten Heimladung in kWh, gebildet wie ``ladung_kwh`` (Σ je Auto, W-1-Rest); gemessen oder aus der
    #: Tagesebene abgeleitet (N-141, ``ladung_anteil_abgeleitet``).
    ladung_pv_kwh: float = 0.0
    #: Netz-Teil der privaten Heimladung in kWh, gebildet wie ``ladung_kwh`` (Σ je Auto, W-1-Rest) — eedcs Zuteilung,
    #: nicht der zum Wallbox-Tarif abgerechnete Netzbezug (``wallbox_netz_eigener_tarif_kwh``).
    ladung_netz_kwh: float = 0.0
    #: N-771 (30.10.2026): Σ gemessener **Netzbezug zum Wallbox-Tarif** aller Wallboxen (privat und dienstlich) — Teilmenge
    #: der Ladung, nur für die Stromrechnung (``tarif.komponenten_anteile``); ``None`` = nicht gemessen (F3 wie an der WP).
    #: ⚠ Nicht ``ladung_netz_kwh``: die ist eedcs Zuteilung (N-569), dies die abgerechnete Menge.
    wallbox_netz_eigener_tarif_kwh: Optional[float] = None
    #: … und die Ladung ALLER Wallboxen des Monats — die Obergrenze der Klemme (F7).
    wallbox_ladung_alle_kwh: float = 0.0
    #: F12 (E6, F12a = A): die Netzladung der Wallbox-Zeilen nach der bisherigen Regel (Zähler des Versorgers, evcc-Wert,
    #: sonst Tagesquote; ``reader.get_emob_pv_netz_kwh`` über die angereicherten Zeilen, privat und dienstlich) — N_wb im
    #: gemeinsamen Zähler (``tarif.komponenten_anteile``). Keine eigene Zuteilung; ohne Wallbox-Zeile 0.
    wallbox_netzladung_kwh: float = 0.0
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
    #: Auswärts geladene kWh der privaten E-Mobilität, geschlossen aus EINER Seite (``waehle_extern_paar``: Wallbox-
    #: oder E-Auto-Seite mit den höheren externen Kosten, bei Gleichstand die größere Menge, dann die Wallbox; N-728).
    extern_kwh: float = 0.0
    #: Kosten der externen Ladung in € — das Paar zu ``extern_kwh`` aus derselben Seite (``waehle_extern_paar``, N-728).
    extern_euro: float = 0.0
    #: Zahl der Ladevorgänge des Monats: das Maximum aus Wallbox-Seite und E-Auto-Seite
    #: (``emob_heimladung_phasen._topf_des_monats``).
    ladevorgaenge: float = 0.0
    quelle: str = "leer"
    #: Gefahrene Kilometer der privaten E-Autos, Σ von ``km_gefahren`` ihrer Zeilen (``roh._falte_emob``; Dienstwagen
    #: ausgenommen).
    km: float = 0.0
    #: Fahrverbrauch der privaten E-Autos in kWh, Σ des Felds Verbrauch (``verbrauch_kwh``) ihrer Zeilen — eine eigene
    #: Menge neben der Heimladung (N-555, ``roh._falte_emob``).
    fahrverbrauch_kwh: float = 0.0
    #: Ins Haus entladene Energie der privaten E-Autos (V2H) in kWh, Σ von ``v2h_entladung_kwh`` ihrer Zeilen — Eingang
    #: des Eigenverbrauchs (``bau._kennzahlen``).
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
    #: PV-Teil der dienstlichen Ladung in kWh (N-555 Regel 3, ``_dienstliche_ladung_des_monats``): die Zeilen der
    #: dienstlichen Wallboxen und, ohne dienstliche Wallbox in Betrieb, die eigene Messung jedes Dienstwagens — ein
    #: Dienstwagen ohne Messung trägt hier 0.
    dienstlich_ladung_pv_kwh: float = 0.0
    #: Netz-Teil der dienstlichen Ladung in kWh, gebildet wie ``dienstlich_ladung_pv_kwh`` — ein Dienstwagen ohne eigene
    #: Messung trägt hier seinen Fahrverbrauch als Schätzung (N-555 Regel 3, ``dienstlich_geschaetzt``).
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
    #: Netz-Teil des Wallbox-Rests in kWh: Wallbox-Ladung − gemessene Autos und Dienstwagen (≥ 0) abzüglich
    #: ``rest_pv_kwh`` (N-555 Regel 2 Schritt 2, ``emob_heimladung_phasen._rest_der_wallbox``); 0, wenn die Wallbox
    #: keinen Wert trägt.
    rest_netz_kwh: float = 0.0
    rest_zugeordnet: bool = False
    #: Trägt eine private Wallbox einen Wert (auch 0) oder — laufend — eine Quelle?
    wallbox_hat_wert: bool = False
    #: Ist eine private Wallbox im Monat in Betrieb (auch ohne Zeile)?
    wallbox_in_betrieb: bool = False
    #: Regel 3 / E3: die gemessene dienstliche Ladung (vom Rest abgezogen) — der
    #: Community-Payload kürzt das Wallbox-Feld darum.
    dienstlich_gemessen_pv_kwh: float = 0.0
    #: Netz-Teil der gemessenen dienstlichen Ladung in kWh — Σ über die Dienstwagen mit eigener Messung
    #: (``dienstwagen_gemessen``), wie der PV-Teil darüber.
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

    #: Erzeugung dieses Geräts in kWh — dieselbe Kategorie-Weiche wie die Anlagensumme (``imd_typ_beitrag``: Erzeuger
    #: mit Ersatzfeld N-667 und Gerät ohne Kategorie; Verbraucher, Zähler und Abgabe 0).
    erzeugung_kwh: float = 0.0
    #: An Dritte abgegebene kWh dieses Geräts (Kategorie „abgabe", Feld ``abgabe_kwh``, §9.2); jede andere Kategorie
    #: trägt 0.
    abgabe_kwh: float = 0.0
    #: Verbrauch dieses Geräts in kWh (``verbrauch_sonstig_kwh``, sonst ``verbrauch_kwh``) — als Verbraucher oder ohne
    #: Kategorie; Erzeuger, Zähler und Abgabe tragen 0 (``imd_typ_beitrag``).
    verbrauch_kwh: float = 0.0
    #: Gepflegter Eigenverbrauch dieses Geräts (``eigenverbrauch_kwh``) in kWh — als Erzeuger oder ohne Kategorie;
    #: Verbraucher, Zähler und Abgabe tragen 0 (``imd_typ_beitrag``).
    eigenverbrauch_kwh: float = 0.0
    #: Gepflegte Einspeisung dieses Geräts (``einspeisung_kwh``) in kWh — als Erzeuger oder ohne Kategorie; Verbraucher,
    #: Zähler und Abgabe tragen 0 (``imd_typ_beitrag``).
    einspeisung_kwh: float = 0.0
    #: Gepflegter PV-Bezug dieses Geräts (``bezug_pv_kwh``) in kWh — als Verbraucher oder ohne Kategorie; Erzeuger,
    #: Zähler und Abgabe tragen 0 (``imd_typ_beitrag``).
    bezug_pv_kwh: float = 0.0
    #: Gepflegter Netzbezug dieses Geräts (``bezug_netz_kwh``) in kWh — als Verbraucher oder ohne Kategorie; Erzeuger,
    #: Zähler und Abgabe tragen 0 (``imd_typ_beitrag``).
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

    #: Σ der Erzeugung der sonstigen Geräte in kWh über ``je_geraet`` (``roh._falte_sonstiges``; Kategorie-Weiche in
    #: ``imd_typ_beitrag``) — dieselbe Zahl wie ``ErzeugungFakten.sonstige_erzeuger_kwh``.
    erzeugung_kwh: float = 0.0
    #: §9.2 — Σ der an Dritte abgegebenen kWh (Kategorie „abgabe"). Sie stehen
    #: NICHT in ``erzeugung_kwh`` und werden in ``kennzahlen`` vom Eigenverbrauch
    #: abgezogen: der dritte Weg neben Eigenverbrauch und Netz-Einspeisung.
    abgabe_kwh: float = 0.0
    #: Σ des Verbrauchs der sonstigen Geräte in kWh über ``je_geraet`` — Verbraucher und Geräte ohne Kategorie
    #: (``imd_typ_beitrag``, ``roh._falte_sonstiges``).
    verbrauch_kwh: float = 0.0
    #: Σ des gepflegten Eigenverbrauchs der sonstigen Erzeuger und Geräte ohne Kategorie in kWh über ``je_geraet`` (C1d,
    #: ``roh._falte_sonstiges``).
    eigenverbrauch_kwh: float = 0.0
    #: Σ der gepflegten Einspeisung der sonstigen Erzeuger und Geräte ohne Kategorie in kWh über ``je_geraet`` (C1d,
    #: ``roh._falte_sonstiges``).
    einspeisung_kwh: float = 0.0
    #: Σ des gepflegten PV-Bezugs der sonstigen Verbraucher und Geräte ohne Kategorie in kWh über ``je_geraet`` (C1d,
    #: ``roh._falte_sonstiges``).
    bezug_pv_kwh: float = 0.0
    #: Σ des gepflegten Netzbezugs der sonstigen Verbraucher und Geräte ohne Kategorie in kWh über ``je_geraet`` (C1d,
    #: ``roh._falte_sonstiges``).
    bezug_netz_kwh: float = 0.0
    #: Konzept §9 Weg 2 — Σ der gepflegten Erzeuger-Erlöse (§9-Fall: eigener
    #: Einspeisetarif). **Kein** Teil von ``ertraege_euro``: das sind die
    #: sonstigen Positionen aus dem Monatsabschluss, dies hier ist ein
    #: gemessener Monatswert je Erzeuger.
    einspeise_erloes_euro: float = 0.0
    #: Σ der Ertrags-Positionen des Monats in € aus allen Geräte-Zeilen jedes Typs (#310, ``berechne_sonstige_summen``)
    #: plus den Basis-Positionen der Monatszeile (G19-1), auf 2 Stellen gerundet (``bau._baue_fakt``).
    ertraege_euro: float = 0.0
    #: Σ der Ausgaben-Positionen des Monats in € aus allen Geräte-Zeilen jedes Typs (#310, ``berechne_sonstige_summen``)
    #: plus den Basis-Positionen der Monatszeile (G19-1), auf 2 Stellen gerundet (``bau._baue_fakt``).
    ausgaben_euro: float = 0.0
    #: Sonstige Positionen netto in €: Erträge − Ausgaben, auf 2 Stellen gerundet (``bau._sonstiges_fakten``).
    netto_euro: float = 0.0
    #: Der Ertrags-Anteil der Basis-Positionen der Monatszeile in € (``berechne_md_sonstige_summen``, G19-1), auf 2
    #: Stellen gerundet, ohne Zeile 0 — in ``ertraege_euro`` schon enthalten.
    anlage_ertraege_euro: float = 0.0
    #: Der Ausgaben-Anteil der Basis-Positionen der Monatszeile in € (``berechne_md_sonstige_summen``, G19-1), auf 2
    #: Stellen gerundet, ohne Zeile 0 — in ``ausgaben_euro`` schon enthalten.
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
class NetzanteilPreise:
    """N-770/N-771 F6 (Bauplan §2): die Zeitfenster-Preise (HT/NT) eines Monats, wenn der Kanal des Felds «Netzbezug zum
    WP-/Wallbox-Tarif» den Monat deckt (``monats_fakten/tarif.py::_netzanteil_preise``) — ``komponenten_anteile`` setzt
    sie ein, sobald es den Anteil der Verwendung ansetzt.

    * ``komponente_cent``: ``((verwendung, ct), …)`` — der Komponenten-Tarif über N gewichtet statt über den Haus-Netzbezug.
    * ``haushalt_rest_cent``: ``((verwendungen, ct), …)`` — der Haushaltstarif über (Netzbezug − Σ N) der angesetzten
      Verwendungen gewichtet (je Teilmenge, weil eine Verwendung ohne gemessenes N den Rest nicht kürzt)."""

    komponente_cent: tuple[tuple[str, float], ...] = ()
    haushalt_rest_cent: tuple[tuple[frozenset, float], ...] = ()

    def komponente(self, verwendung: str) -> Optional[float]:
        return dict(self.komponente_cent).get(verwendung)

    def haushalt_rest(self, verwendungen) -> Optional[float]:
        return dict(self.haushalt_rest_cent).get(frozenset(verwendungen))


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

    #: Netzbezugspreis des Monats in ct/kWh am Monatsersten (P8) über die ganze Kaskade abgerechneter Monats-Ø →
    #: gemessener Ø → Zeitfenster → Stammpreis (#412, ``strompreis_aggregator.aufgeloester_monatspreis``); die Stufe
    #: steht in ``netzbezug_preis_herkunft``.
    netzbezug_preis_cent: float = NETZBEZUG_DEFAULT_CENT
    #: Welche Stufe der Kaskade den Preis geliefert hat (``gepflegt`` ·
    #: ``gemessen`` · ``zeitfenster`` · ``stamm``) — die Zahl allein sagt es
    #: nicht, und eine Sicht muss es aussprechen können (P4, #412).
    netzbezug_preis_herkunft: Optional[str] = None
    #: Arbeitspreis des allgemeinen Tarifs am Monatsersten in ct/kWh, mit HT/NT-Fenstern über den gemessenen Netzbezug
    #: des Monats gewichtet (N-267, ``strompreis_aggregator.wirksamer_arbeitspreis_cent``) — ohne abgerechneten oder
    #: gemessenen Monats-Ø.
    netzbezug_stammpreis_cent: float = NETZBEZUG_DEFAULT_CENT
    #: Einspeisevergütung des Monats in ct/kWh: der Monatssatz der variablen Vergütung
    #: (``Monatsdaten.einspeise_durchschnittspreis_cent``, #392) vor dem Satz des allgemeinen Tarifs am Monatsersten
    #: (``strompreise.resolve_einspeise_preis_cent``), ohne Tarif der Default.
    einspeiseverguetung_cent: float = EINSPEISEVERGUETUNG_DEFAULT_CENT
    #: N-769: Σ der Grundpreise ALLER im Monat gültigen Tarife — allgemein plus ein EIGENER WP-/Wallbox-Tarif
    #: (``tarif.grundpreis_des_monats``); gehört nur in die Stromrechnung.
    grundpreis_euro_monat: float = 0.0
    #: Preis des WP-Stroms in ct/kWh am Monatsersten: mit eigenem Wärmepumpen-Tarif dessen Arbeitspreis mit Zeitfenstern
    #: (``tarif._komponenten_preis``), ohne ihn der Preis des Hauszählers mit der ganzen Kaskade, also
    #: ``netzbezug_preis_cent`` (N-663).
    wp_preis_cent: float = NETZBEZUG_DEFAULT_CENT
    #: Arbeitspreis des Wallbox-Tarifs am Monatsersten in ct/kWh, mit HT/NT-Fenstern über den Netzbezug des Hauses
    #: gewichtet; ohne eigenen Wallbox-Tarif der des allgemeinen Tarifs (``tarif._komponenten_preis``).
    wallbox_preis_cent: float = NETZBEZUG_DEFAULT_CENT
    #: Preis der Wallbox-Ladung in ct/kWh: die Kaskade des Monatspreises über den Tarif der Wallbox — abgerechneter
    #: Monats-Ø → gemessener Ø → Zeitfenster → ``wallbox_preis_cent`` (N-717/N-433, ``aufgeloester_monatspreis``).
    wallbox_preis_effektiv_cent: float = NETZBEZUG_DEFAULT_CENT
    #: N-770/N-771: gilt im Monat ein EIGENER WP- bzw. Wallbox-Tarif (nicht der Rückfall auf den allgemeinen)? Nur dann
    #: rechnet die Stromrechnung einen gemessenen Netzbezug zum Komponenten-Tarif mit dessen Preis (``komponenten_anteile``).
    wp_eigener_tarif: bool = False
    wallbox_eigener_tarif: bool = False
    #: F12 (N-770/N-771 E6): gilt ein GEMEINSAMER Tarif für Wärmepumpe und Wallbox (Verwendung ``waermepumpe_wallbox``,
    #: ``tarif.komponenten_tarif_gemeinsam``)? Dann trägt das Feld an der WP den gemeinsamen Netzbezug N_g, und
    #: ``komponenten_anteile`` rechnet einen Anteil ``waermepumpe_wallbox`` (F12a = A). ``wp_eigener_tarif`` ist dann
    #: ``True``, ``wallbox_eigener_tarif`` ``False`` (ein Feld an der Wallbox zählt nicht).
    komponenten_tarif_gemeinsam: bool = False
    #: N-770/N-771 F6: die HT/NT-Preise über N bzw. (Netzbezug − N), wenn der Kanal des Felds den Monat deckt; sonst ``None``.
    netzanteil_preise: Optional[NetzanteilPreise] = None
    #: Kraftstoffpreis des Monats in €/l aus der Monatszeile (``Monatsdaten.kraftstoffpreis_euro``); ``None`` ohne Zeile
    #: oder ohne Wert.
    kraftstoffpreis_euro: Optional[float] = None
    #: Gas-/Ölpreis des Monats für den WP-Alternativvergleich in ct/kWh aus der Monatszeile
    #: (``Monatsdaten.gaspreis_cent_kwh``); ``None`` ohne Zeile oder ohne Wert.
    gaspreis_cent_kwh: Optional[float] = None

@dataclass(frozen=True)
class EegFakten:
    """§51 EEG — Einspeisung zu negativen Preisen.

    ``None`` heißt **nicht** 0: entweder unterliegt die Anlage dem §51 nicht
    (manueller Schalter, Default aus), oder es gibt für den Monat keine
    Strompreis-Mitschrift. Eine 0 wäre dort eine Aussage, die niemand belegen kann.
    """

    #: Einspeisung zu negativen Preisen in kWh: Σ von ``einspeisung_neg_preis_kwh`` der Tage des Monats
    #: (``einspeise_erloes_service.get_neg_preis_einspeisung_je_monat``); ``None`` ohne §51-Pflicht oder ohne Tag mit
    #: Strompreis-Mitschrift.
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
    #: ⭐ N-736 (12.10.2026): trägt der Monat für Einspeisung bzw. Netzbezug einen **erfassten** Wert? Die Spalten der
    #: Zählerzeile sind ``NOT NULL`` mit Default 0 — eine Zeile, die ein Import ohne Netzfelder anlegte, steht mit 0,0
    #: da, und ``ZaehlerFakten`` trägt diese 0 (die Felder bleiben ``float``). Erfasst heißt: die Zeile trägt das Feld
    #: (``roh.netzfeld_ist_erfasst``, N-734 — Herkunftseintrag oder Wert ≠ 0) **oder** die Tagesebene hat es gefüllt
    #: (``TAGESWERT_ZAEHLER``, nur wo sie es selbst erfasst). ⭐ N-751 (16.10.2026): **ohne Zeile** tragen die beiden
    #: Feld-Flags die Marken der Tagesebene (``TagesMonatsSumme.*_erfasst``; ohne Tagesebene ``False``) — vorher immer
    #: ``False``. ``netz_erfasst`` = Zeile **und** beide Felder erfasst — ohne Zeile weiter immer ``False``, es schließt
    #: ``hat_zaehlerzeile`` also weiter ein (Community-Filter, Bilanz-Grundmengen). Wer einen Monat ohne Zeile beurteilt
    #: (Monatsliste von Cockpit → Jahr, ``api/routes/monatsdaten.py::_ohne_netz_bilanz``), liest die Feld-Flags.
    #: Die Bilanz-Grundmenge der Fakten-Sichten (Muster N-659) ist
    #: ``hat_zaehlerzeile and netz_erfasst and erzeuger_aktiv`` — ein Monat mit nicht erfasstem Netzfeld fällt aus
    #: Eigenverbrauch, Autarkie, Ersparnis, USt und CO₂ wie ein Monat ohne Zählerzeile; seine PV bleibt in der Anzeige.
    #: Default ``False`` wie ``hat_zaehlerzeile`` — ein von Hand gebauter Fakt ohne Zeile bleibt einer ohne Zeile.
    netzbezug_erfasst: bool = False
    einspeisung_erfasst: bool = False
    netz_erfasst: bool = False
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

    #: Kalenderjahr — mit ``monat`` der Schlüssel des Fakts (``schluessel``, ``MonatsSchluessel``; ``bau._baue_fakt``).
    jahr: int
    #: Kalendermonat 1–12 — mit ``jahr`` der Schlüssel des Fakts; ``stichtag`` ist sein Monatserster (P8).
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
