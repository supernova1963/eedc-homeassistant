"""Monats-Fakten — die EINE Aufbereitung der Monatszeile vor jeder Read-Site.

**Warum es diesen Service gibt.** Die Drift-Inventur vom 2026-07-31 (23 Sichten
× 18 kanonische Größen, 72 Kandidaten-Zellen) fand **keinen einzigen Rechenfehler**
im Berechnungs-Layer. Sie fand sechsmal dieselbe Struktur: *jede Sicht faltet die
Rohdaten selbst zu Monatswerten*, und dabei fällt jedes Mal etwas anderes weg —
mal V2H, mal der Erzeuger hinter dem Zähler, mal der Aggregat-Fallback, mal der
Monatstarif, mal der Dienstwagen-Filter. Der härteste Beleg (F-5), an einer Anlage
gemessen, die nur das Anlagen-Aggregat pflegt:

===========================  ==========  ==============
Sicht                        PV          Netto-Ertrag
===========================  ==========  ==============
Cockpit · HA-Export          1.000 kWh   212,00 €
Aussichten · Jahresbericht    0 kWh       32,00 €
===========================  ==========  ==============

85 % Abweichung — weil zwei Sichten ``lade_pv_je_monat`` nutzen und fünf roh
``verbrauch_daten["pv_erzeugung_kwh"]`` summieren.

**Das hier ist keine Erfindung, sondern eine Verallgemeinerung.**
``services/pv_monatswerte.py`` ist bereits genau diese Schicht — für genau EINE
Größe, mit derselben Begründung im Docstring („die Eingabe musste bisher jede
Read-Site selbst zusammensuchen … zwei davon sind an der Formel vorbeigelaufen").
Seit es ihn gibt, ist in der PV-Auflösung keine neue Drift entstanden; die
verbleibenden Befunde sind genau die Sichten, die ihn *nicht* benutzen. Dieses
Modul zieht dieselbe Bauform von einer Größe auf die ganze Monatszeile
(``docs/KONZEPT-MONATS-FAKTEN.md``, ADR-002/**P10**).

**Schichtung (ADR-001).** Die Schicht ist **Eingabe-Aufbereitung, keine Formel**:
sie enthält keine einzige Aggregat-Formel, sondern lädt, filtert und *ruft* die
SoT-Helfer aus ``core/berechnungen/`` (``imd_typ_beitrag``, ``bkw_finanz_beitrag``,
``erzeugung_hinter_zaehler_kwh``, ``berechne_verbrauchs_kennzahlen``) sowie die
bestehenden Service-SoT (``lade_pv_je_monat``, ``get_emob_heimladung_canonical``,
``lade_tarife_fuer_anlage``, ``get_neg_preis_einspeisung_je_monat``). DB-I/O gehört
laut ADR-001 in ``services/`` — deshalb liegt sie hier und nicht in ``core/``.

**Alle Zeitfilter (``aktiv`` · Anschaffung · Stilllegung) und der
Dienstwagen-Filter werden GENAU HIER angewandt, einmal** (#153/#155/#236/#308,
[[feedback_anschaffungsdatum_grenze]], [[feedback_dienstwagen_alle_checks]]).

**Was die Schicht bewusst NICHT tut** (``KONZEPT-MONATS-FAKTEN.md`` §4):
Live, Prognose und **jeden Schreibpfad** — sie ist reines Lesen. Sie rechnet auch
keine Euro-Beträge aus, für die es einen Formel-Helfer gibt: der Aufrufer bekommt
die Mengen *und* den Monatstarif und ruft den Helfer selbst.

**Eine Grenze ist seit N-121 (2026-08-03) verschoben, und zwar bewusst.** Bis
dahin stand hier „keine Tages-/Stundenebene — der Tag hat mit
``bilanz_aus_stundenrows`` eine eigene, korrekte Quelle". Das stimmt weiterhin
für die *Formel*: gefaltet wird nach wie vor mit genau diesem Layer-Helfer, hier
entsteht keine zweite Faltung. Was sich geändert hat, ist die **Grundgesamtheit**:
mit ``inkl_nur_tageswerte=True`` kennt die Schicht auch Monate, deren einzige Spur
die Tagesebene ist, und füllt damit die Lücken der übrigen. Auslöser war, dass es
**keinen automatischen Monatsabschluss** gibt — der laufende Monat hat nie eine
``Monatsdaten``-Zeile und fehlte im Jahres-Verlauf deshalb immer. Der Default
bleibt **aus**; Datensatz-Listen sehen unverändert nur, was wirklich in der DB
steht. Details, Messwerte und die Grenzen der Quelle:
``energie_profil/monats_aus_tagen.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeise_preis_cent,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen import (
    PvModulWert,
    VerbrauchsKennzahlen,
    abgetretene_bkw_ids,
    berechne_verbrauchs_kennzahlen,
    bkw_finanz_beitrag,
    erzeugung_hinter_zaehler_kwh,
    hat_gemessene_betriebsart,
    imd_typ_beitrag,
)
from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD
from backend.core.investition_parameter import ist_dienstlich
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.field_definitions import get_emob_pv_netz_kwh, get_wp_strom_kwh
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.eauto_wirtschaftlichkeit import (
    EmobLadungPool,
    get_emob_heimladung_canonical,
    summiere_emob_quelle,
)
from backend.services.einspeise_erloes_service import (
    get_neg_preis_einspeisung_je_monat,
)
from backend.services.emob_ladeanteil import (
    hat_gepflegten_pv_anteil,
    reichere_ladezeilen_an,
)
from backend.services.energie_profil.modus_split_monat import (
    lade_modus_split_ohne_abschluss,
)
from backend.services.energie_profil.monats_aus_tagen import (
    TagesMonatsSumme,
    lade_monats_summen_aus_tagen,
)
from backend.services.finanz_zeilen import FinanzZeileEingabe
from backend.services.pv_monatswerte import lade_pv_je_monat, pv_summe_je_monat
from backend.utils.sonstige_positionen import (
    berechne_md_sonstige_summen,
    berechne_sonstige_summen,
)

# (jahr, monat) — die Achse dieser Schicht.
MonatsSchluessel = tuple[int, int]

#: Typen, die hinter denselben Hauszähler speisen und deshalb ein
#: „PV-Fenster" öffnen (Anschaffungsdatum-Grenze, s. `MetaFakten.erzeuger_aktiv`).
_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")

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

    - ``pv_module_kwh`` — die P7-aufgelöste Modul-PV. ``None`` heißt „mindestens
      ein aktives Modul ohne Wert und ohne Aggregat" (N42) — eine Teilsumme wäre
      als Anlagenerzeugung irreführend. Wer summiert, behandelt ``None`` als
      Lücke, **nie** als 0.
    - ``pv_kwh`` — Module + Balkonkraftwerk. Die PV-Achse: spezifischer Ertrag,
      Performance Ratio, SOLL/IST **und** der Eingang der Finanz-Zeile (P9).
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
    getrennt ausgewiesen, weil er als *Ausgabe* (dienstliche Ladekosten) in die
    Sonstige-Summen gehört. Die Bewertung in Euro bleibt beim Aufrufer, weil sie
    den Monatstarif braucht (der liegt in ``TarifFakten``).
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
    eauto_ladedaten: tuple[dict, ...] = ()
    wallbox_ladedaten: tuple[dict, ...] = ()
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
class WpFakten:
    """Wärmepumpe des Monats — kanonisch gelesen (D1, ``imd_typ_beitrag``)."""

    strom_kwh: float = 0.0
    waerme_kwh: float = 0.0
    heizung_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    strom_heizen_kwh: float = 0.0
    strom_warmwasser_kwh: float = 0.0
    #: True, sobald **eine** aktive WP getrennte Strommessung führt.
    hat_split: bool = False

    # ── Modus-Split (#263 K-2) ───────────────────────────────────────────────
    #: **Teilmengen** von ``strom_kwh``, keine Summanden — nie addieren
    #: (Präzedenz: ``ladung_pv_kwh`` bei der Wallbox, Konzept §3.1).
    modus_strom_heizen_kwh: float = 0.0
    modus_strom_kuehlen_kwh: float = 0.0
    #: Stunden mit gültigem Modus-Signal — das Qualitätsmaß neben den Mengen.
    modus_abdeckung_h: float = 0.0
    #: #263 — die Aufteilung ist **gemessen** (Betriebsart-Zähler) statt aus
    #: dem Betriebsmodus abgeleitet. Ein Zähler hat keine „Stunden mit Signal",
    #: deshalb kann ``modus_abdeckung_h`` dabei 0 sein, ohne dass etwas fehlt.
    modus_gemessen: bool = False
    #: Gesamtstrom **nur der Geräte mit Modus-Split** — die Bezugsgröße für
    #: {@link modus_nicht_aufgeteilt_kwh}. Auf Anlagenebene ist `strom_kwh` der
    #: falsche Bezug: er trägt auch Wärmepumpen ohne Modus-Sensor.
    modus_strom_bezug_kwh: float = 0.0
    #: Anteil von ``waerme_kwh``, der aus ``Strom × JAZ`` stammt statt aus
    #: einem Wärmemengenzähler. **Trägt die JAZ-Sperre aus Konzept §3.5** —
    #: siehe {@link jaz_belastbar}.
    waerme_abgeleitet_kwh: float = 0.0

    @property
    def jaz_belastbar(self) -> bool:
        """Darf aus diesen Zahlen eine JAZ/COP gebildet werden? (Konzept §3.5)

        ``False``, sobald **irgendein** Teil der Wärme abgeleitet ist. Nicht
        „den abgeleiteten Teil abziehen": dann teilte man gemessene Wärme durch
        den **Gesamt**strom und bekäme eine zu kleine JAZ — falsch statt
        unbekannt. Die Kachel bleibt „—", bis ein Wärmemengenzähler da ist.
        """
        return self.waerme_abgeleitet_kwh <= 0

    @property
    def modus_nicht_aufgeteilt_kwh(self) -> float:
        """``Gesamt − Σ Teilmengen`` — Standby, Lüften, Entfeuchten, Unbestimmt.

        **Wird nie gespeichert** (Konzept §3.1, Folge 2) und ist deshalb immer
        vollständig: für Altmonate, Ausfälle, Importe und manuelle Pflege
        gleichermaßen. Auf 0 geklemmt — die Invariante hält das schon im
        Schreibpfad, aber eine negative „Restmenge" wäre auf jeder Fläche
        Unsinn.

        ⚠ Bezug ist {@link modus_strom_bezug_kwh}, **nicht** ``strom_kwh``:
        anlagenweit trägt letzteres auch Wärmepumpen ohne Modus-Sensor, deren
        Verbrauch dann als „nicht aufgeteilt" der Klimaanlage erschiene
        (an einer Instanz gemessen: 96,4 statt 6,4 kWh).
        """
        return max(
            0.0,
            self.modus_strom_bezug_kwh
            - self.modus_strom_heizen_kwh
            - self.modus_strom_kuehlen_kwh,
        )

    @property
    def hat_modus_split(self) -> bool:
        """Gibt es überhaupt eine Aufteilung zu zeigen?

        ⚠ **Zwei Wege, ein Ergebnis** (#263): abgeleitet aus dem Betriebsmodus
        (dann gibt es Abdeckungs-Stunden) **oder** gemessen aus
        Betriebsart-Zählern (dann gibt es keine — ein Zähler zählt kWh, keine
        Stunden mit Signal). Nur die Abdeckung zu prüfen hieße, eine gemessene
        Aufteilung nirgends zu zeigen.
        """
        return self.modus_abdeckung_h > 0 or self.modus_gemessen


@dataclass(frozen=True)
class SonstigesGeraetFakten:
    """Die Mengen EINES sonstigen Geräts im Monat.

    Kategorie-bewusst aufgelöst wie die Anlagen-Summen: beim Erzeuger bleiben
    ``bezug_*`` leer, beim Verbraucher ``eigenverbrauch``/``einspeisung`` — die
    Entscheidung fällt ``imd_typ_beitrag``, nicht der Aufrufer (ADR-001).
    """

    erzeugung_kwh: float = 0.0
    verbrauch_kwh: float = 0.0
    eigenverbrauch_kwh: float = 0.0
    einspeisung_kwh: float = 0.0
    bezug_pv_kwh: float = 0.0
    bezug_netz_kwh: float = 0.0
    #: Konzept §9 Weg 2: gepflegter Erlös DIESES Erzeugers in €. Er ersetzt
    #: keine Anlagengröße, sondern kommt hinzu — eedc kennt nur einen
    #: Einspeisesatz je Anlage, und der bewertet nur den Anlagenzähler.
    einspeise_erloes_euro: float = 0.0


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


# ═══════════════════════════════════════════════════════════════════════════
# Der Ladepfad
# ═══════════════════════════════════════════════════════════════════════════


async def lade_monats_fakten(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
    tarif_cache: Optional[dict[date, dict]] = None,
    inkl_nur_tageswerte: bool = False,
) -> list[MonatsFakt]:
    """Baut die Monats-Fakten einer Anlage — ein Query-Satz, danach reine Faltung.

    Args:
        db: Session.
        anlage_id: Anlage.
        von: frühester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        bis: spätester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        tarif_cache: derselbe Cache, den der Aufrufer an ``baue_finanz_zeile``
            weiterreicht. Ohne ihn löst der Tarif-Stichtag **zweimal** je Monat
            auf — einmal hier, einmal im Finanz-Zeilen-Builder (Risiko 2 des
            Konzepts, „Ladezeit"). Wer keine Finanz-Zeile baut, lässt ihn weg.
        inkl_nur_tageswerte: nimmt Monate mit auf, deren einzige Spur die lokale
            **Tagesebene** ist, und füllt damit die Lücken der übrigen Monate
            (Fund **N-121**, Default **aus**). Gedacht für **Zeitreihen** — der
            laufende Monat hat nie einen Monatsabschluss und fehlte deshalb im
            Jahres-Verlauf immer. Für Datensatz-Listen (*Auswertungen → Tabelle*)
            bleibt es aus: dort wäre so ein Monat eine Zeile, die man weder
            bearbeiten noch löschen kann. Kostet **keine** HA-Abfrage (die
            Tagesebene liegt lokal, s. ``energie_profil/monats_aus_tagen.py``).

    Returns:
        Nach ``(jahr, monat)`` aufsteigend sortierte Liste. Enthalten ist jeder
        Monat, für den es eine Zählerzeile, eine sichtbare IMD-Zeile oder eine
        aufgelöste PV gibt — Monate ohne jede Spur fehlen. Ein Monat **ohne**
        Zählerzeile ist enthalten (``meta.hat_zaehlerzeile is False``), damit eine
        Sicht die Lücke ausweisen kann, statt sie zu übersehen.

    Die Investitionen werden **ohne** ``aktiv``-Filter geladen (#123: historische
    Kennzahlen dürfen später deaktivierte Komponenten nicht rückwirkend
    ausblenden); die Sichtbarkeit entscheidet je Monat ``ist_aktiv_im_monat`` —
    das deckt alle drei Achsen ab (``aktiv``-Override, Anschaffung, Stilllegung).
    """
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = list(inv_result.scalars().all())
    inv_by_id = {i.id: i for i in investitionen}

    imd_rows = await _lade_imd(db, [i.id for i in investitionen], von, bis)
    md_rows = await _lade_monatsdaten(db, anlage_id, von, bis)
    monatsdaten_by_ym = {(m.jahr, m.monat): m for m in md_rows}

    # PV über den Read-time-SoT (P7): gemessene Modulwerte + Lücken aus dem
    # Anlagen-Aggregat. NIE die Rohspalte direkt — sie ist entweder eine
    # Teilsumme oder sie überschreibt Messungen.
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    pv_je_modul = await lade_pv_je_monat(db, anlage_id, pv_module, jahr=_ein_jahr(von, bis))
    pv_summen = pv_summe_je_monat(pv_je_modul)

    # N-266: Balkonkraftwerke, unter denen `pv-module` hängen. Ihre Erzeugung
    # steckt seit E4 in `pv_je_modul` (der BKW-Monatswert füllt dort die Lücken
    # seiner Kinder) und darf deshalb nicht zusätzlich als `bkw_erzeugung`
    # gezählt werden. Ohne Modul-Kinder ist die Menge leer und alles bleibt
    # bitgleich zu vorher.
    abgetretene_bkw = abgetretene_bkw_ids(investitionen)

    neg_preis_je_monat = await get_neg_preis_einspeisung_je_monat(db, anlage_id)

    # Roh-Faltung je Monat aus den sichtbaren IMD-Zeilen.
    roh: dict[MonatsSchluessel, _RohMonat] = {}
    #: (jahr, monat) → {investition_id_als_string: (hat_gespeicherten_split,
    #: gepflegter_wp_strom_kwh)} — die Buchführung für den Modus-Lesepfad (F-52).
    #: Sie entsteht **in diesem Durchlauf**, damit der Lesepfad je *Gerät*
    #: entscheiden kann, statt je Monat: eine Anlage mit zwei Wärmepumpen kann
    #: für die eine einen Abschluss haben und für die andere nicht.
    wp_je_monat: dict[MonatsSchluessel, dict[str, tuple[bool, float]]] = {}
    for imd in imd_rows:
        inv = inv_by_id.get(imd.investition_id)
        # #153/#155/#236/#308: vor Anschaffung / nach Stilllegung / deaktiviert
        # zählt nichts — der EINE Ort, an dem dieser Filter gilt.
        if inv is None or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue
        daten = imd.verbrauch_daten or {}
        roh.setdefault((imd.jahr, imd.monat), _RohMonat()).falte(
            inv, daten,
            abgetretene_bkw=abgetretene_bkw,
            source_provenance=imd.source_provenance,
        )
        if inv.typ == "waermepumpe":
            # #263 — eine **gemessene** Betriebsart-Aufteilung wirkt hier wie
            # ein gelaufener Monatsabschluss: der aus dem Betriebsmodus
            # gerechnete Split wird für dieses Gerät NICHT zusätzlich
            # angewandt, sonst stünde dieselbe Menge zweimal in der Zeile.
            # Dieselbe Weiche, kein zweiter Mechanismus (ADR-002/P8).
            wp_je_monat.setdefault((imd.jahr, imd.monat), {})[str(inv.id)] = (
                float(daten.get(MODUS_ABDECKUNG_FELD) or 0) > 0
                or hat_gemessene_betriebsart(daten),
                get_wp_strom_kwh(daten, inv.parameter),
            )

    # ── Modus-Split für Monate ohne Abschluss (F-52) ─────────────────────────
    #
    # **Der zweite Aufrufer, den `modus_split_monat.py` im eigenen Modul-Kopf
    # beschreibt.** Er fehlte: die drei Modus-Felder stehen nur in der
    # IMD-Zeile, und dorthin schreibt allein der von Hand gestartete
    # Monatsabschluss. Der *laufende* Monat hat nie einen — wer den
    # Betriebsmodus heute zuordnet, sah bis hierher in **allen vier** Sichten
    # nichts (Komponenten-Hub, Cockpit Monat, Cockpit Jahr, HA-Sensoren), und
    # zwar bis zum nächsten Abschluss. Gemeldet von kingcap1 (#263).
    #
    # **Gespeichert schlägt gerechnet** — dieselbe Reihenfolge wie beim
    # Schreibpfad (ADR-002/P8: ein Wert trägt den Stichtag seines Monats). Wo
    # ein Abschluss gelaufen ist, gilt sein Ergebnis, auch wenn die Tagesebene
    # inzwischen etwas anderes hergäbe.
    #
    # ⚠ **Die Invariante gilt hier genauso**, und sie ist der Grund, warum
    # dieser Block nicht einfach addiert: Beim Abschluss *verworfene* Splits
    # (Σ Teilmengen > Gesamt) hinterlassen keine Spur — ohne erneute Prüfung
    # kämen sie über diesen Weg zurück und die Invariante wäre umgangen.
    #
    # **Kosten:** eine `SELECT DISTINCT datum … WHERE betriebsmodus_je_wp IS NOT
    # NULL`. Eine Anlage ohne Modus-Zuordnung bricht dort ab und lädt nichts
    # (`modus_split_monat.py`, Modul-Kopf) — deshalb genügt als Vorbedingung,
    # dass es überhaupt eine Wärmepumpe gibt.
    if any(i.typ == "waermepumpe" for i in investitionen):
        await _ergaenze_modus_split_ohne_abschluss(
            db, anlage_id, roh, wp_je_monat, inv_by_id, von=von, bis=bis
        )

    # Die lokale Tagesebene als **zusätzliche** Grundgesamtheit (N-121). Ohne
    # das Flag wird sie nicht einmal geladen — die Kosten trägt nur, wer sie
    # bestellt.
    #
    # ⚠ Seit N-141 Weg (c) gibt es einen **zweiten** Grund, sie zu laden, und er
    # hat nichts mit der Grundgesamtheit zu tun: der PV-Anteil der Heimladung
    # ist nirgends gemessen und wird aus der Tagesebene abgeleitet. Ohne dieses
    # Nachladen sähe genau EINE Sicht (Cockpit → Monat, der einzige Aufrufer mit
    # dem Flag) einen PV-Anteil, während Komponenten-Hub, CO₂-Bilanz und
    # E-Auto-Ersparnis weiter 0 % behaupten — zwei Zahlen für dieselbe Größe,
    # die Klasse hinter #331 und F-15. Deshalb **bedingt**: nur wenn ein Monat
    # überhaupt Heimladung ohne gepflegten PV-Anteil trägt. Eine Anlage ohne
    # Wallbox und ohne E-Auto zahlt dafür nichts (Entscheid Gernot 2026-08-08).
    tages_summen: dict[MonatsSchluessel, TagesMonatsSumme] = {}
    nur_fuer_ladeanteil = not inkl_nur_tageswerte and any(
        m.emob_ladung_ohne_pv_anteil for m in roh.values()
    )
    if inkl_nur_tageswerte or nur_fuer_ladeanteil:
        tages_summen = await lade_monats_summen_aus_tagen(
            db, anlage_id, von=von, bis=bis
        )

    kandidaten = (
        set(monatsdaten_by_ym)
        | set(pv_summen)
        | set(pv_je_modul)
        | set(roh)
        # ⚠ Nur mit dem Flag erweitert die Tagesebene die Grundgesamtheit. Wurde
        # sie allein für den Ladeanteil geholt, darf sie KEINE zusätzlichen
        # Monate aufmachen — sonst tauchten in jeder Sicht plötzlich Monate auf,
        # die nur eine Tagesspur haben. Das ist genau die Wirkung, die N-121
        # hinter das Flag gestellt hat.
        | (set(tages_summen) if inkl_nur_tageswerte else set())
    )

    if tarif_cache is None:
        tarif_cache = {}
    fakten: list[MonatsFakt] = []
    for schluessel in sorted(k for k in kandidaten if _im_fenster(k, von, bis)):
        fakten.append(
            await _baue_fakt(
                db,
                anlage_id,
                schluessel,
                roh.get(schluessel, _RohMonat()),
                monatsdaten=monatsdaten_by_ym.get(schluessel),
                pv_modul_summe=pv_summen.get(schluessel),
                pv_je_modul=pv_je_modul.get(schluessel, {}),
                investitionen=investitionen,
                neg_preis_kwh=(neg_preis_je_monat or {}).get(schluessel),
                tarif_cache=tarif_cache,
                tages_summe=tages_summen.get(schluessel),
            )
        )
    return fakten


async def _ergaenze_modus_split_ohne_abschluss(
    db: AsyncSession,
    anlage_id: int,
    roh: dict[MonatsSchluessel, _RohMonat],
    wp_je_monat: dict[MonatsSchluessel, dict[str, tuple[bool, float]]],
    inv_by_id: dict[int, Investition],
    *,
    von: Optional[MonatsSchluessel],
    bis: Optional[MonatsSchluessel],
) -> None:
    """Trägt den Modus-Split der Tagesebene nach, wo kein Abschluss ihn hält (F-52).

    Ändert ``roh`` an Ort und Stelle. **Die Regeln stehen nicht hier** — sie
    liegen in ``lade_modus_split_ohne_abschluss``, weil der HA-Export dieselben
    braucht und seine IMD-Zeilen je Investition faltet (P10-Restschuld). Ein
    Nachbau daneben wäre die Drift-Klasse, an der F-52 selbst entstanden ist.

    ⚠ **Es entsteht hier ein neuer Monat**, wo bisher keine Gerätespur lag —
    und das ist gewollt: ein Monat mit Modus-Spur *hat* eine, sie steht nur in
    Stundenzeilen statt in einer Monatszeile. Das ist nicht die N-121-Falle
    (dort ging es um Monate mit reiner Tagesspur ohne jeden Gerätebezug).
    """
    angewandt = await lade_modus_split_ohne_abschluss(
        db, anlage_id, inv_by_id=inv_by_id, gespeichert=wp_je_monat,
        von=von, bis=bis,
    )
    for schluessel, je_inv in angewandt.items():
        for split in je_inv.values():
            r = roh.setdefault(schluessel, _RohMonat())
            r.wp_modus_strom_heizen += split.heizen_kwh
            r.wp_modus_strom_kuehlen += split.kuehlen_kwh
            r.wp_modus_abdeckung_h += split.abdeckung_h
            r.wp_modus_strom_bezug += split.bezug_kwh


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
    Handwert, zieht ``investitionen/crud.py`` ihn als ``pv_anteil_prozent`` in
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

    - ``pv_erzeugung_kwh`` ist ``erzeugung.pv_kwh`` — Module **und** BKW, weil der
      Aggregat-Helfer daraus den Eigenverbrauch ableitet (P9).
    - ``bkw_eigenverbrauch_kwh`` ist der **Rest**-Eigenverbrauch aus
      ``bkw_finanz_beitrag``, nie der gemessene Rohwert — sonst zählt derselbe
      Fluss zweimal.
    """
    return FinanzZeileEingabe(
        jahr=fakt.jahr,
        monat=fakt.monat,
        einspeisung_kwh=fakt.zaehler.einspeisung_kwh,
        netzbezug_kwh=fakt.zaehler.netzbezug_kwh,
        pv_erzeugung_kwh=fakt.erzeugung.pv_kwh,
        speicher_ladung_kwh=fakt.speicher.ladung_kwh,
        speicher_entladung_kwh=fakt.speicher.entladung_kwh,
        v2h_entladung_kwh=fakt.emob.v2h_entladung_kwh,
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
    )


# ═══════════════════════════════════════════════════════════════════════════
# Interna
# ═══════════════════════════════════════════════════════════════════════════


class _RohMonat:
    """Sammelt die sichtbaren IMD-Zeilen EINES Monats, typweise kanonisch.

    Bewusst veränderlich und modul-privat: das Ergebnis nach außen sind die
    eingefrorenen Feldgruppen. Jede Auflösung läuft über ``imd_typ_beitrag``
    (ADR-001) — hier steht kein einziger Literal-Schlüssel auf
    ``verbrauch_daten`` (P6).
    """

    def __init__(self) -> None:
        #: Typen, die in diesem Monat eine SICHTBARE Zeile beigetragen haben.
        #: Trennt „0 gemessen" von „gar nicht vorhanden" (P4) — nicht dasselbe
        #: wie `aktive_investitionen`: eine aktive Wärmepumpe ohne gepflegte
        #: Zeile ist aktiv, hat aber nichts beigetragen.
        self.typen_mit_zeile: set[str] = set()
        #: Hat ein sonstiger **Erzeuger** beigetragen? Feiner als der Typ:
        #: `sonstiges` deckt Erzeuger und Verbraucher ab, und nur der Erzeuger
        #: gehört in die Erzeugungs-Anzeige.
        self.hat_sonstigen_erzeuger = False
        #: Spiegelbild dazu für die **Verbraucher**-Seite. Ohne ihn müsste eine
        #: Sicht aus „Verbrauch == 0" auf „gibt es nicht" schließen — genau die
        #: Verwechslung, die `hat_sonstigen_erzeuger` auf der anderen Seite
        #: verhindert (P4).
        self.hat_sonstigen_verbraucher = False
        self.pv_je_modul_roh: dict[int, float] = {}
        self.bkw_je_investition: dict[int, float] = {}
        self.bkw_erzeugung = 0.0
        self.bkw_eigenverbrauch = 0.0
        self.bkw_rest_eigenverbrauch = 0.0
        self.bkw_speicher_ladung = 0.0
        self.bkw_speicher_entladung = 0.0
        self.speicher_ladung = 0.0
        self.speicher_entladung = 0.0
        self.speicher_netzladung = 0.0
        self.speicher_preis_summe = 0.0
        self.speicher_preis_gewicht = 0.0
        self.wp_strom = 0.0
        self.wp_waerme = 0.0
        self.wp_heizung = 0.0
        self.wp_warmwasser = 0.0
        self.wp_strom_heizen = 0.0
        self.wp_strom_warmwasser = 0.0
        self.wp_hat_split = False
        self.wp_modus_strom_heizen = 0.0
        self.wp_modus_strom_kuehlen = 0.0
        self.wp_modus_abdeckung_h = 0.0
        #: #263 — mindestens ein Gerät bringt die Aufteilung GEMESSEN mit.
        self.wp_modus_gemessen = False
        self.wp_modus_strom_bezug = 0.0
        self.wp_waerme_abgeleitet = 0.0
        self.eauto_ladedaten: list[dict] = []
        self.wallbox_ladedaten: list[dict] = []
        self.eauto_km = 0.0
        self.eauto_km_je_fahrzeug: dict[int, float] = {}
        self.eauto_fahrverbrauch_je_fahrzeug: dict[int, float] = {}
        self.eauto_fahrverbrauch = 0.0
        self.eauto_v2h = 0.0
        self.dienstlich_pv = 0.0
        self.dienstlich_netz = 0.0
        self.sonstiges_erzeugung = 0.0
        self.sonstiges_verbrauch = 0.0
        self.sonstiges_eigenverbrauch = 0.0
        self.sonstiges_einspeisung = 0.0
        self.sonstiges_bezug_pv = 0.0
        self.sonstiges_bezug_netz = 0.0
        self.sonstiges_einspeise_erloes_euro = 0.0
        #: Je `Investition.id` dieselben sechs Größen — für Sichten, die die
        #: Geräte einzeln ausweisen (Monatsroute: „Sonstige Geräte"). Die
        #: Summen oben bleiben die Wahrheit der Anlage; diese Gruppe ist ihre
        #: Aufschlüsselung, nicht eine zweite Quelle.
        self.sonstiges_je_geraet: dict[int, dict[str, float]] = {}
        self.ertraege_euro = 0.0
        self.ausgaben_euro = 0.0

    @property
    def emob_ladung_ohne_pv_anteil(self) -> bool:
        """Gibt es Heimlade-Zeilen, aber keine erfasste PV-/Netz-Aufteilung?

        Die **Vorprüfung** vor dem Nachladen der Tagesebene (N-141 Weg c): nur
        wenn sie zutrifft, lohnt die zusätzliche Query. Sie liest ausschließlich
        die bereits gefalteten Rohzeilen, kostet also nichts.

        Bewusst grob — ob am Ende überhaupt Ladung > 0 herauskommt, entscheidet
        erst der Pool in `_baue_fakt`. Eine zu großzügige Vorprüfung kostet eine
        Query zu viel; eine zu strenge verlöre den Wert still.
        """
        if not (self.eauto_ladedaten or self.wallbox_ladedaten):
            return False
        return not hat_gepflegten_pv_anteil(
            self.eauto_ladedaten, self.wallbox_ladedaten
        )

    def falte(
        self,
        inv: Investition,
        data: dict,
        *,
        abgetretene_bkw: frozenset = frozenset(),
        source_provenance: dict | None = None,
    ) -> None:
        """Faltet EINE IMD-Zeile ein.

        ``source_provenance`` ist die Per-Feld-Herkunft **derselben** Zeile. Sie
        wird nur für eine Frage gebraucht: ist die Heizwärme gemessen oder aus
        ``Strom × JAZ`` abgeleitet (#263 K-2, Konzept §3.5)? Default ``None``
        heißt „gemessen wie bisher" und hält Bestands-Tests unverändert gültig.

        ``abgetretene_bkw`` sind die IDs der Balkonkraftwerke, unter denen
        `pv-module` hängen (N-266). **Pflicht-Argument im Geiste, mit Default
        aus Bequemlichkeit für Tests:** ohne die Menge zählt die Erzeugung eines
        abtretenden BKW zweimal — einmal über seine Kinder in
        ``pv_je_modul``/``pv_module_kwh``, einmal hier in ``bkw_erzeugung``.
        Betroffen wären Autarkie, Eigenverbrauchsquote, CO₂, Finanzen,
        Community-Payload und HA-Export.
        """
        b = imd_typ_beitrag(inv, data, source_provenance)
        # Dienstwagen zählen NICHT als Beitrag: sie sind aus dem E-Mob-Pool der
        # Anlage herausgefiltert, und eine Sicht, die daraufhin „0 kWh geladen"
        # schriebe statt „keine Daten", behauptete etwas über ein Fahrzeug, das
        # sie gar nicht auswertet ([[feedback_dienstwagen_alle_checks]]).
        if not (inv.typ in ("e-auto", "wallbox") and ist_dienstlich(inv)):
            self.typen_mit_zeile.add(inv.typ)

        if inv.typ == "balkonkraftwerk":
            # N-266: Hängen `pv-module` an diesem BKW, hat es seine Erzeugung
            # abgetreten — sie steht schon in `pv_je_modul` (dort füllt der
            # BKW-Monatswert die Lücken seiner Kinder, `pv_monatswerte.py`
            # Stufe 2). Hier zählt sie deshalb 0.
            #
            # ⚠ Und der **Rest-Eigenverbrauch** wird damit ebenfalls 0, nicht
            # etwa der Ersatzträger: P9 sagt, der Ersatzträger greift genau
            # dann, wenn die Erzeugung **nirgends** in die PV-Summe eingeht. Hier
            # geht sie ein, nur über die Kinder — der selbst verbrauchte Anteil
            # steckt also wie im Normalfall bereits in der Ableitung
            # `PV − Einspeisung − Speicherladung`. Ihn zusätzlich zu tragen wäre
            # exakt die Doppelzählung, gegen die P9 geschrieben ist.
            hat_abgetreten = inv.id in abgetretene_bkw
            # P9: je (BKW, Monat) trägt genau EINER der beiden Werte die
            # Finanz-Zeile — die Entscheidung fällt der Helfer, nie der Aufrufer.
            beitrag = bkw_finanz_beitrag(
                erzeugung_kwh=b.bkw_erzeugung,
                eigenverbrauch_kwh=b.bkw_eigenverbrauch,
            )
            if hat_abgetreten:
                beitrag = bkw_finanz_beitrag(erzeugung_kwh=None, eigenverbrauch_kwh=None)
            else:
                self.bkw_erzeugung += b.bkw_erzeugung
            # Je Investition zusätzlich zur Summe (F-10): der String-Vergleich
            # des Jahresbericht-PDF stellt jeden Erzeuger einzeln seinem SOLL
            # gegenüber und findet ein BKW in `pv_je_modul` nicht — dort stehen
            # nur `pv-module`. Die Summe `bkw_erzeugung` hilft ihm nicht, sobald
            # zwei Balkonkraftwerke da sind. Rein additiv; `pv_je_modul` und
            # `pv_module_kwh` bleiben unberührt, weil `pv_module_kwh` in die
            # ROI-Rechnung geht, wo das BKW bewusst eine eigene Zeile hat
            # (`investitionen/crud.py::get_pv_erzeugung`) und sonst doppelt zählte.
            #
            # N-266: ein abtretendes BKW steht hier NICHT. Beide Leser dieses
            # Felds addieren es neben `pv_je_modul` — der String-Vergleich des
            # PDF (dort ist das BKW seit E2 keine eigene Zeile mehr) und die
            # ROI-Gewichtung in `aussichten.py` (`_erz_gewichte` + `_bkw_gewichte`).
            # Dort wäre es die Doppelzählung ein zweites Mal, auf der Geldachse.
            if not hat_abgetreten:
                self.bkw_je_investition[inv.id] = (
                    self.bkw_je_investition.get(inv.id, 0.0) + b.bkw_erzeugung
                )
            self.bkw_eigenverbrauch += b.bkw_eigenverbrauch
            self.bkw_rest_eigenverbrauch += beitrag.rest_eigenverbrauch_kwh
            self.bkw_speicher_ladung += b.bkw_speicher_ladung
            self.bkw_speicher_entladung += b.bkw_speicher_entladung

        elif inv.typ == "speicher":
            self.speicher_ladung += b.speicher_ladung
            self.speicher_entladung += b.speicher_entladung
            self.speicher_netzladung += b.speicher_arbitrage
            if b.speicher_ladepreis_cent > 0 and b.speicher_arbitrage > 0:
                self.speicher_preis_summe += b.speicher_ladepreis_cent * b.speicher_arbitrage
                self.speicher_preis_gewicht += b.speicher_arbitrage

        elif inv.typ == "waermepumpe":
            self.wp_strom += b.wp_strom
            self.wp_waerme += b.wp_waerme
            self.wp_heizung += b.wp_heizung
            self.wp_warmwasser += b.wp_warmwasser
            self.wp_strom_heizen += b.wp_strom_heizen
            self.wp_strom_warmwasser += b.wp_strom_warmwasser
            self.wp_hat_split = self.wp_hat_split or b.wp_hat_split
            self.wp_modus_strom_heizen += b.wp_modus_strom_heizen
            self.wp_modus_strom_kuehlen += b.wp_modus_strom_kuehlen
            self.wp_modus_abdeckung_h += b.wp_modus_abdeckung_h
            self.wp_modus_gemessen = self.wp_modus_gemessen or b.wp_modus_gemessen
            self.wp_modus_strom_bezug += b.wp_modus_strom_bezug
            self.wp_waerme_abgeleitet += b.wp_waerme_abgeleitet

        elif inv.typ in ("e-auto", "wallbox"):
            if ist_dienstlich(inv):
                # Dienstlich geladen ist keine private Ersparnis — der Anteil
                # wird herausgefiltert, aber nicht verworfen: er gehört als
                # Ausgabe in die Sonstige-Summen (Bewertung beim Aufrufer, sie
                # braucht den Monatstarif). [[feedback_dienstwagen_alle_checks]]
                pv_kwh, netz_kwh = get_emob_pv_netz_kwh(data)
                self.dienstlich_pv += pv_kwh
                self.dienstlich_netz += netz_kwh
            elif inv.typ == "e-auto":
                self.eauto_ladedaten.append(data)
                self.eauto_km += b.eauto_km
                self.eauto_fahrverbrauch += b.eauto_verbrauch
                self.eauto_v2h += b.eauto_v2h
                if b.eauto_km:
                    self.eauto_km_je_fahrzeug[inv.id] = (
                        self.eauto_km_je_fahrzeug.get(inv.id, 0.0) + b.eauto_km
                    )
                if b.eauto_verbrauch:
                    self.eauto_fahrverbrauch_je_fahrzeug[inv.id] = (
                        self.eauto_fahrverbrauch_je_fahrzeug.get(inv.id, 0.0)
                        + b.eauto_verbrauch
                    )
            else:
                self.wallbox_ladedaten.append(data)

        elif inv.typ == "pv-module":
            # Nur zur Monats-Kandidatur; der WERT kommt aus der P7-Auflösung.
            self.pv_je_modul_roh[inv.id] = b.pv_erzeugung

        elif inv.typ == "sonstiges":
            self.sonstiges_erzeugung += b.sonstiges_erzeugung
            self.sonstiges_verbrauch += b.sonstiges_verbrauch
            self.sonstiges_eigenverbrauch += b.sonstiges_eigenverbrauch
            self.sonstiges_einspeisung += b.sonstiges_einspeisung
            self.sonstiges_bezug_pv += b.sonstiges_bezug_pv
            self.sonstiges_bezug_netz += b.sonstiges_bezug_netz
            self.sonstiges_einspeise_erloes_euro += b.sonstiges_einspeise_erloes_euro
            g = self.sonstiges_je_geraet.setdefault(
                inv.id,
                {"erzeugung": 0.0, "verbrauch": 0.0, "eigenverbrauch": 0.0,
                 "einspeisung": 0.0, "bezug_pv": 0.0, "bezug_netz": 0.0,
                 "einspeise_erloes_euro": 0.0},
            )
            g["erzeugung"] += b.sonstiges_erzeugung
            g["verbrauch"] += b.sonstiges_verbrauch
            g["eigenverbrauch"] += b.sonstiges_eigenverbrauch
            g["einspeisung"] += b.sonstiges_einspeisung
            g["bezug_pv"] += b.sonstiges_bezug_pv
            g["bezug_netz"] += b.sonstiges_bezug_netz
            g["einspeise_erloes_euro"] += b.sonstiges_einspeise_erloes_euro
            # Ein Erzeuger mit 0 kWh im Monat ist ein echter 0-Wert, kein
            # „nicht vorhanden" — deshalb zählt auch die Kategorie, nicht nur
            # ein Beitrag > 0.
            if b.sonstiges_erzeugung or (inv.parameter or {}).get("kategorie") == "erzeuger":
                self.hat_sonstigen_erzeuger = True
            # Dieselbe Regel auf der Verbraucherseite: ein Heizstab, der im
            # Monat 0 kWh gezogen hat, ist ein echter 0-Wert.
            if b.sonstiges_verbrauch or (inv.parameter or {}).get("kategorie") == "verbraucher":
                self.hat_sonstigen_verbraucher = True

        # #310: die Finanz-Positionen hängen NICHT am Typ — eine Reparatur am
        # Wechselrichter ist so real wie eine am Speicher.
        summen = berechne_sonstige_summen(data)
        self.ertraege_euro += summen["ertraege_euro"]
        self.ausgaben_euro += summen["ausgaben_euro"]


async def _baue_fakt(
    db: AsyncSession,
    anlage_id: int,
    schluessel: MonatsSchluessel,
    roh: _RohMonat,
    *,
    monatsdaten: Optional[Monatsdaten],
    pv_modul_summe: Optional[float],
    pv_je_modul: dict[int, PvModulWert],
    investitionen: list[Investition],
    neg_preis_kwh: Optional[float],
    tarif_cache: dict[date, dict],
    tages_summe: Optional[TagesMonatsSumme] = None,
) -> MonatsFakt:
    jahr, monat = schluessel

    # ── Lücken aus der Tagesebene füllen (N-121, nur mit `inkl_nur_tageswerte`) ──
    # Präzedenz wie bei P7: was in der DB steht, gewinnt. Die Tageswerte füllen
    # **Lücken**, sie überschreiben nichts — und zwar feldgruppen-weise, nicht
    # monatsweise: ein Monat, dessen einzige DB-Spur eine Sonstiges-Zeile ist,
    # bekommt dadurch seine PV, statt sie still als 0 zu zeichnen.
    tageswert_gruppen: set[str] = set()

    zaehler = ZaehlerFakten(
        einspeisung_kwh=(monatsdaten.einspeisung_kwh or 0.0) if monatsdaten else 0.0,
        netzbezug_kwh=(monatsdaten.netzbezug_kwh or 0.0) if monatsdaten else 0.0,
    )
    if monatsdaten is None and tages_summe is not None:
        zaehler = ZaehlerFakten(
            einspeisung_kwh=tages_summe.einspeisung_kwh,
            netzbezug_kwh=tages_summe.netzbezug_kwh,
        )
        tageswert_gruppen.add(TAGESWERT_ZAEHLER)

    # PV nur, wenn die P7-Auflösung nichts ergab (`None` = kein Modulwert und
    # kein Anlagen-Aggregat). Ein aufgelöster Wert — auch ein teilweise
    # geschätzter — bleibt unangetastet.
    if pv_modul_summe is None and tages_summe is not None and tages_summe.pv_module_kwh > 0:
        pv_modul_summe = tages_summe.pv_module_kwh
        pv_vollstaendig = True
        tageswert_gruppen.add(TAGESWERT_PV)
    else:
        pv_vollstaendig = pv_modul_summe is not None or not pv_je_modul

    # BKW nur ohne eigene IMD-Zeile im Monat.
    bkw_erzeugung = roh.bkw_erzeugung
    if (
        "balkonkraftwerk" not in roh.typen_mit_zeile
        and tages_summe is not None
        and tages_summe.bkw_kwh > 0
    ):
        bkw_erzeugung = tages_summe.bkw_kwh
        tageswert_gruppen.add(TAGESWERT_BKW)

    pv_kwh = (pv_modul_summe or 0.0) + bkw_erzeugung
    erzeugung = ErzeugungFakten(
        pv_module_kwh=pv_modul_summe,
        bkw_kwh=bkw_erzeugung,
        sonstige_erzeuger_kwh=roh.sonstiges_erzeugung,
        pv_kwh=pv_kwh,
        # Netzpunkt-Bilanz: der sonstige Erzeuger speist hinter denselben Zähler.
        hinter_zaehler_kwh=erzeugung_hinter_zaehler_kwh(pv_kwh, roh.sonstiges_erzeugung),
        pv_je_modul=pv_je_modul,
        pv_vollstaendig=pv_vollstaendig,
    )

    # ── PV-Anteil der Heimladung: echter Wert gewinnt, sonst ableiten ──────
    # Rahmenbedingung 1 (N-141 Weg c): die Ableitung füllt NUR Lücken. Gepflegt
    # ist der Anteil, sobald irgendeine Quellzeile den Schlüssel trägt — auch
    # mit **0**. Das ist bewusst `is not None` und nicht `> 0`: eine gepflegte
    # 0 („diesen Monat nur nachts geladen") ist eine Aussage, keine Lücke, und
    # sie darf keine Schätzung auslösen (CLAUDE.md §0-Werte prüfen).
    #
    # ⚠ **Angereichert wird VOR dem Pool, nicht danach (F-16).** Bis `a7a50abc`
    # saß die Ableitung unter `pool` und traf damit nur die Felder
    # `ladung_pv_kwh`/`ladung_netz_kwh` — jede Sicht, die die mitgereichten
    # Rohdicts selbst poolt (Cockpit → Jahr, Jahresbericht-PDF) oder die IMD
    # direkt liest (Komponenten-Hub, Aussichten, HA-Export), zeigte weiter 0 %.
    # Unterhalb des Pools angesetzt gilt die Aufteilung für jeden dieser Wege.
    eauto_ladedaten, wallbox_ladedaten, anteil_abgeleitet = reichere_ladezeilen_an(
        eauto_daten=roh.eauto_ladedaten,
        wallbox_daten=roh.wallbox_ladedaten,
        quote=tages_summe.abgeleiteter_pv_anteil if tages_summe is not None else None,
    )
    if anteil_abgeleitet:
        tageswert_gruppen.add(TAGESWERT_EMOB_ANTEIL)

    pool = get_emob_heimladung_canonical(
        eauto_imd_data=eauto_ladedaten,
        wallbox_imd_data=wallbox_ladedaten,
    )

    emob = EmobFakten(
        ladung_kwh=pool.ladung_kwh,
        ladung_pv_kwh=pool.pv_kwh,
        ladung_netz_kwh=pool.netz_kwh,
        ladung_anteil_abgeleitet=anteil_abgeleitet,
        extern_kwh=pool.extern_kwh,
        extern_euro=pool.extern_euro,
        ladevorgaenge=pool.ladevorgaenge,
        quelle=pool.quelle,
        km=roh.eauto_km,
        fahrverbrauch_kwh=roh.eauto_fahrverbrauch,
        v2h_entladung_kwh=roh.eauto_v2h,
        km_je_fahrzeug=dict(roh.eauto_km_je_fahrzeug),
        fahrverbrauch_je_fahrzeug=dict(roh.eauto_fahrverbrauch_je_fahrzeug),
        dienstlich_ladung_pv_kwh=roh.dienstlich_pv,
        dienstlich_ladung_netz_kwh=roh.dienstlich_netz,
        eauto_ladedaten=tuple(eauto_ladedaten),
        wallbox_ladedaten=tuple(wallbox_ladedaten),
        eauto_summe=summiere_emob_quelle(eauto_ladedaten),
        wallbox_summe=summiere_emob_quelle(wallbox_ladedaten),
        # Ungeschätzt — nur für den Community-Payload (s. Feld-Docstring).
        eauto_summe_gemessen=summiere_emob_quelle(roh.eauto_ladedaten),
        wallbox_summe_gemessen=summiere_emob_quelle(roh.wallbox_ladedaten),
    )

    md_summen = berechne_md_sonstige_summen(monatsdaten) if monatsdaten else None
    ertraege = roh.ertraege_euro + (md_summen["ertraege_euro"] if md_summen else 0.0)
    ausgaben = roh.ausgaben_euro + (md_summen["ausgaben_euro"] if md_summen else 0.0)

    tarif = await _lade_tarif(db, anlage_id, schluessel, monatsdaten, tarif_cache)

    speicher = SpeicherFakten(
        ladung_kwh=roh.speicher_ladung,
        entladung_kwh=roh.speicher_entladung,
        netzladung_kwh=roh.speicher_netzladung,
        netzladung_preis_summe_cent_kwh=roh.speicher_preis_summe,
        netzladung_gewicht_kwh=roh.speicher_preis_gewicht,
    )
    # Speicher nur ohne eigene IMD-Zeile im Monat. Die Netzladung (Arbitrage)
    # bleibt dabei ungefüllt: sie ist eine **Preis**-Aussage, und die trägt die
    # Tagesebene nicht — eine 0 daneben wäre keine Messung, sondern eine
    # Behauptung über einen nie gepflegten Wert.
    if (
        "speicher" not in roh.typen_mit_zeile
        and tages_summe is not None
        and (tages_summe.speicher_ladung_kwh > 0 or tages_summe.speicher_entladung_kwh > 0)
    ):
        speicher = SpeicherFakten(
            ladung_kwh=tages_summe.speicher_ladung_kwh,
            entladung_kwh=tages_summe.speicher_entladung_kwh,
        )
        tageswert_gruppen.add(TAGESWERT_SPEICHER)

    return MonatsFakt(
        jahr=jahr,
        monat=monat,
        zaehler=zaehler,
        erzeugung=erzeugung,
        bkw=BkwFakten(
            erzeugung_kwh=bkw_erzeugung,
            eigenverbrauch_gemessen_kwh=roh.bkw_eigenverbrauch,
            rest_eigenverbrauch_kwh=roh.bkw_rest_eigenverbrauch,
            speicher_ladung_kwh=roh.bkw_speicher_ladung,
            speicher_entladung_kwh=roh.bkw_speicher_entladung,
            # Leer lassen, sobald die Zahl von der Tagesebene kommt: dort ist sie
            # anlagenweit, eine Aufteilung wäre erfunden (s. Feld-Docstring).
            erzeugung_je_investition=(
                {} if TAGESWERT_BKW in tageswert_gruppen
                else dict(roh.bkw_je_investition)
            ),
        ),
        speicher=speicher,
        emob=emob,
        wp=WpFakten(
            strom_kwh=roh.wp_strom,
            waerme_kwh=roh.wp_waerme,
            heizung_kwh=roh.wp_heizung,
            warmwasser_kwh=roh.wp_warmwasser,
            strom_heizen_kwh=roh.wp_strom_heizen,
            strom_warmwasser_kwh=roh.wp_strom_warmwasser,
            hat_split=roh.wp_hat_split,
            modus_strom_heizen_kwh=roh.wp_modus_strom_heizen,
            modus_strom_kuehlen_kwh=roh.wp_modus_strom_kuehlen,
            modus_abdeckung_h=roh.wp_modus_abdeckung_h,
            modus_gemessen=roh.wp_modus_gemessen,
            modus_strom_bezug_kwh=roh.wp_modus_strom_bezug,
            waerme_abgeleitet_kwh=roh.wp_waerme_abgeleitet,
        ),
        sonstiges=SonstigesFakten(
            erzeugung_kwh=roh.sonstiges_erzeugung,
            verbrauch_kwh=roh.sonstiges_verbrauch,
            eigenverbrauch_kwh=roh.sonstiges_eigenverbrauch,
            einspeisung_kwh=roh.sonstiges_einspeisung,
            bezug_pv_kwh=roh.sonstiges_bezug_pv,
            bezug_netz_kwh=roh.sonstiges_bezug_netz,
            einspeise_erloes_euro=roh.sonstiges_einspeise_erloes_euro,
            je_geraet={
                inv_id: SonstigesGeraetFakten(
                    erzeugung_kwh=g["erzeugung"],
                    verbrauch_kwh=g["verbrauch"],
                    eigenverbrauch_kwh=g["eigenverbrauch"],
                    einspeisung_kwh=g["einspeisung"],
                    bezug_pv_kwh=g["bezug_pv"],
                    bezug_netz_kwh=g["bezug_netz"],
                    einspeise_erloes_euro=g.get("einspeise_erloes_euro", 0.0),
                )
                for inv_id, g in roh.sonstiges_je_geraet.items()
            },
            ertraege_euro=round(ertraege, 2),
            ausgaben_euro=round(ausgaben, 2),
            netto_euro=round(ertraege - ausgaben, 2),
            anlage_ertraege_euro=round(md_summen["ertraege_euro"], 2) if md_summen else 0.0,
            anlage_ausgaben_euro=round(md_summen["ausgaben_euro"], 2) if md_summen else 0.0,
            hat_erzeuger_zeile=roh.hat_sonstigen_erzeuger,
            hat_verbraucher_zeile=roh.hat_sonstigen_verbraucher,
        ),
        tarif=tarif,
        eeg=EegFakten(neg_preis_kwh=neg_preis_kwh),
        kennzahlen=berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=erzeugung.hinter_zaehler_kwh,
            einspeisung_kwh=zaehler.einspeisung_kwh,
            netzbezug_kwh=zaehler.netzbezug_kwh,
            speicher_ladung_kwh=speicher.ladung_kwh,
            speicher_entladung_kwh=speicher.entladung_kwh,
            v2h_entladung_kwh=emob.v2h_entladung_kwh,
        ),
        meta=MetaFakten(
            monatsdaten=monatsdaten,
            hat_zaehlerzeile=monatsdaten is not None,
            erzeuger_aktiv=_erzeuger_aktiv(investitionen, jahr, monat),
            pv_vollstaendig=erzeugung.pv_vollstaendig,
            aktive_investitionen=tuple(
                i.id for i in investitionen if i.ist_aktiv_im_monat(jahr, monat)
            ),
            typen_mit_zeile=frozenset(roh.typen_mit_zeile),
            tageswert_gruppen=frozenset(tageswert_gruppen),
        ),
    )


async def _lade_tarif(
    db: AsyncSession,
    anlage_id: int,
    schluessel: MonatsSchluessel,
    monatsdaten: Optional[Monatsdaten],
    cache: dict[date, dict],
) -> TarifFakten:
    """Tarif zum Monatsersten (P8) — ein Cache-Eintrag je Stichtag pro Anfrage."""
    stichtag = date(schluessel[0], schluessel[1], 1)
    if stichtag not in cache:
        cache[stichtag] = await lade_tarife_fuer_anlage(db, anlage_id, target_date=stichtag)
    tarife = cache[stichtag]

    allgemein = tarife.get("allgemein")
    stammpreis = (
        allgemein.netzbezug_arbeitspreis_cent_kwh if allgemein else NETZBEZUG_DEFAULT_CENT
    )
    # Komponenten-Tarif über die SoT-Kaskade (Komponente → allgemein → Default)
    # statt handschriftlich: ein Spezialtarif-Datensatz OHNE Arbeitspreis fiel
    # in der Handschrift auf `None` durch, statt auf den allgemeinen Tarif.
    wallbox_cent = resolve_strompreis_for_komponente(tarife, "wallbox", fallback=stammpreis)
    return TarifFakten(
        # Flex-Ø des Monats vor dem Stammdaten-Arbeitspreis (P8, zweite Form).
        netzbezug_preis_cent=resolve_netzbezug_preis_cent(monatsdaten, stammpreis),
        netzbezug_stammpreis_cent=stammpreis,
        # #392: der Monatswert der variablen Vergütung schlägt den Stammwert —
        # dieselbe zweite P8-Form wie beim Netzbezug eine Zeile darüber.
        einspeiseverguetung_cent=resolve_einspeise_preis_cent(
            monatsdaten,
            allgemein.einspeiseverguetung_cent_kwh
            if allgemein
            else EINSPEISEVERGUETUNG_DEFAULT_CENT,
        ),
        grundpreis_euro_monat=(allgemein.grundpreis_euro_monat or 0.0) if allgemein else 0.0,
        wp_preis_cent=resolve_strompreis_for_komponente(
            tarife, "waermepumpe", fallback=stammpreis
        ),
        wallbox_preis_cent=wallbox_cent,
        # Der Flex-Ø gilt für den ganzen Zähler — auch für die Wallbox.
        wallbox_preis_effektiv_cent=resolve_netzbezug_preis_cent(monatsdaten, wallbox_cent),
        kraftstoffpreis_euro=monatsdaten.kraftstoffpreis_euro if monatsdaten else None,
        gaspreis_cent_kwh=monatsdaten.gaspreis_cent_kwh if monatsdaten else None,
    )


def _erzeuger_aktiv(investitionen: list[Investition], jahr: int, monat: int) -> bool:
    """War im Monat ein Erzeuger hinter dem Zähler aktiv? (Anschaffungs-Grenze)

    Ohne registrierten Erzeuger ``True`` — der Filter greift dann nicht und das
    Verhalten bleibt unverändert.
    """
    erzeuger = [
        i for i in investitionen
        if i.typ in _ERZEUGER_TYPEN
        or (i.typ == "sonstiges"
            and (getattr(i, "parameter", None) or {}).get("kategorie") == "erzeuger")
    ]
    if not erzeuger:
        return True
    return any(e.ist_aktiv_im_monat(jahr, monat) for e in erzeuger)


async def _lade_imd(
    db: AsyncSession,
    inv_ids: list[int],
    von: Optional[MonatsSchluessel],
    bis: Optional[MonatsSchluessel],
) -> list[InvestitionMonatsdaten]:
    if not inv_ids:
        return []
    query = select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id.in_(inv_ids)
    )
    # Grob auf Jahre vorfiltern; der monatsgenaue Schnitt passiert unten.
    if von is not None:
        query = query.where(InvestitionMonatsdaten.jahr >= von[0])
    if bis is not None:
        query = query.where(InvestitionMonatsdaten.jahr <= bis[0])
    return list((await db.execute(query)).scalars().all())


async def _lade_monatsdaten(
    db: AsyncSession,
    anlage_id: int,
    von: Optional[MonatsSchluessel],
    bis: Optional[MonatsSchluessel],
) -> list[Monatsdaten]:
    query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if von is not None:
        query = query.where(Monatsdaten.jahr >= von[0])
    if bis is not None:
        query = query.where(Monatsdaten.jahr <= bis[0])
    return list((await db.execute(query.order_by(Monatsdaten.jahr, Monatsdaten.monat))).scalars().all())


def _ein_jahr(
    von: Optional[MonatsSchluessel], bis: Optional[MonatsSchluessel]
) -> Optional[int]:
    """Das Jahr, wenn das Fenster in genau einem liegt — sonst ``None``.

    Nur ein Query-Filter: die PV-Auflösung liefert monatsweise, der monatsgenaue
    Schnitt passiert danach.
    """
    if von is not None and bis is not None and von[0] == bis[0]:
        return von[0]
    return None


def _im_fenster(
    schluessel: MonatsSchluessel,
    von: Optional[MonatsSchluessel],
    bis: Optional[MonatsSchluessel],
) -> bool:
    if von is not None and schluessel < von:
        return False
    if bis is not None and schluessel > bis:
        return False
    return True
