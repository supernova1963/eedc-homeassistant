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
Tages-/Stundenebene (der Tag hat mit ``bilanz_aus_stundenrows`` eine eigene,
korrekte Quelle), Live, Prognose und **jeden Schreibpfad** — sie ist reines Lesen.
Sie rechnet auch keine Euro-Beträge aus, für die es einen Formel-Helfer gibt: der
Aufrufer bekommt die Mengen *und* den Monatstarif und ruft den Helfer selbst.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen import (
    PvModulWert,
    VerbrauchsKennzahlen,
    berechne_verbrauchs_kennzahlen,
    bkw_finanz_beitrag,
    erzeugung_hinter_zaehler_kwh,
    imd_typ_beitrag,
)
from backend.core.investition_parameter import ist_dienstlich
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.field_definitions import get_emob_pv_netz_kwh
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.eauto_wirtschaftlichkeit import get_emob_heimladung_canonical
from backend.services.einspeise_erloes_service import (
    get_neg_preis_einspeisung_je_monat,
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
    """

    erzeugung_kwh: float = 0.0
    eigenverbrauch_gemessen_kwh: float = 0.0
    rest_eigenverbrauch_kwh: float = 0.0
    speicher_ladung_kwh: float = 0.0
    speicher_entladung_kwh: float = 0.0


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

    ``dienstlich_*`` ist der herausgefilterte Anteil — nicht verworfen, sondern
    getrennt ausgewiesen, weil er als *Ausgabe* (dienstliche Ladekosten) in die
    Sonstige-Summen gehört. Die Bewertung in Euro bleibt beim Aufrufer, weil sie
    den Monatstarif braucht (der liegt in ``TarifFakten``).
    """

    ladung_kwh: float = 0.0
    ladung_pv_kwh: float = 0.0
    ladung_netz_kwh: float = 0.0
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
    dienstlich_ladung_pv_kwh: float = 0.0
    dienstlich_ladung_netz_kwh: float = 0.0
    eauto_ladedaten: tuple[dict, ...] = ()
    wallbox_ladedaten: tuple[dict, ...] = ()


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


@dataclass(frozen=True)
class SonstigesFakten:
    """Sonstige Verbraucher + die manuell gepflegten Finanz-Positionen.

    ``erzeugung_kwh``/``verbrauch_kwh`` stammen aus Investitionen vom Typ
    ``sonstiges`` (kategorie-bewusst aufgelöst). Die Euro-Positionen dagegen
    kommen aus **allen** sichtbaren IMD-Zeilen — unabhängig vom Typ (#310 war ein
    Typ-Ausschluss: PV/WR fehlten im Aggregat) — **plus** den Basis-Positionen auf
    der ``Monatsdaten``-Zeile (G19-1), die genau wie IMD-Positionen wirken.
    """

    erzeugung_kwh: float = 0.0
    verbrauch_kwh: float = 0.0
    ertraege_euro: float = 0.0
    ausgaben_euro: float = 0.0
    netto_euro: float = 0.0


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
    """

    monatsdaten: Optional[Monatsdaten] = None
    hat_zaehlerzeile: bool = False
    erzeuger_aktiv: bool = True
    pv_vollstaendig: bool = True
    aktive_investitionen: tuple[int, ...] = ()


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

    neg_preis_je_monat = await get_neg_preis_einspeisung_je_monat(db, anlage_id)

    # Roh-Faltung je Monat aus den sichtbaren IMD-Zeilen.
    roh: dict[MonatsSchluessel, _RohMonat] = {}
    for imd in imd_rows:
        inv = inv_by_id.get(imd.investition_id)
        # #153/#155/#236/#308: vor Anschaffung / nach Stilllegung / deaktiviert
        # zählt nichts — der EINE Ort, an dem dieser Filter gilt.
        if inv is None or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue
        roh.setdefault((imd.jahr, imd.monat), _RohMonat()).falte(inv, imd.verbrauch_daten or {})

    kandidaten = (
        set(monatsdaten_by_ym)
        | set(pv_summen)
        | set(pv_je_modul)
        | set(roh)
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
            )
        )
    return fakten


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
        self.pv_je_modul_roh: dict[int, float] = {}
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
        self.eauto_ladedaten: list[dict] = []
        self.wallbox_ladedaten: list[dict] = []
        self.eauto_km = 0.0
        self.eauto_km_je_fahrzeug: dict[int, float] = {}
        self.eauto_fahrverbrauch = 0.0
        self.eauto_v2h = 0.0
        self.dienstlich_pv = 0.0
        self.dienstlich_netz = 0.0
        self.sonstiges_erzeugung = 0.0
        self.sonstiges_verbrauch = 0.0
        self.ertraege_euro = 0.0
        self.ausgaben_euro = 0.0

    def falte(self, inv: Investition, data: dict) -> None:
        b = imd_typ_beitrag(inv, data)

        if inv.typ == "balkonkraftwerk":
            # P9: je (BKW, Monat) trägt genau EINER der beiden Werte die
            # Finanz-Zeile — die Entscheidung fällt der Helfer, nie der Aufrufer.
            beitrag = bkw_finanz_beitrag(
                erzeugung_kwh=b.bkw_erzeugung,
                eigenverbrauch_kwh=b.bkw_eigenverbrauch,
            )
            self.bkw_erzeugung += b.bkw_erzeugung
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
            else:
                self.wallbox_ladedaten.append(data)

        elif inv.typ == "pv-module":
            # Nur zur Monats-Kandidatur; der WERT kommt aus der P7-Auflösung.
            self.pv_je_modul_roh[inv.id] = b.pv_erzeugung

        elif inv.typ == "sonstiges":
            self.sonstiges_erzeugung += b.sonstiges_erzeugung
            self.sonstiges_verbrauch += b.sonstiges_verbrauch

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
) -> MonatsFakt:
    jahr, monat = schluessel

    zaehler = ZaehlerFakten(
        einspeisung_kwh=(monatsdaten.einspeisung_kwh or 0.0) if monatsdaten else 0.0,
        netzbezug_kwh=(monatsdaten.netzbezug_kwh or 0.0) if monatsdaten else 0.0,
    )

    pv_kwh = (pv_modul_summe or 0.0) + roh.bkw_erzeugung
    erzeugung = ErzeugungFakten(
        pv_module_kwh=pv_modul_summe,
        bkw_kwh=roh.bkw_erzeugung,
        sonstige_erzeuger_kwh=roh.sonstiges_erzeugung,
        pv_kwh=pv_kwh,
        # Netzpunkt-Bilanz: der sonstige Erzeuger speist hinter denselben Zähler.
        hinter_zaehler_kwh=erzeugung_hinter_zaehler_kwh(pv_kwh, roh.sonstiges_erzeugung),
        pv_je_modul=pv_je_modul,
        pv_vollstaendig=pv_modul_summe is not None or not pv_je_modul,
    )

    pool = get_emob_heimladung_canonical(
        eauto_imd_data=roh.eauto_ladedaten,
        wallbox_imd_data=roh.wallbox_ladedaten,
    )
    emob = EmobFakten(
        ladung_kwh=pool.ladung_kwh,
        ladung_pv_kwh=pool.pv_kwh,
        ladung_netz_kwh=pool.netz_kwh,
        extern_kwh=pool.extern_kwh,
        extern_euro=pool.extern_euro,
        ladevorgaenge=pool.ladevorgaenge,
        quelle=pool.quelle,
        km=roh.eauto_km,
        fahrverbrauch_kwh=roh.eauto_fahrverbrauch,
        v2h_entladung_kwh=roh.eauto_v2h,
        km_je_fahrzeug=dict(roh.eauto_km_je_fahrzeug),
        dienstlich_ladung_pv_kwh=roh.dienstlich_pv,
        dienstlich_ladung_netz_kwh=roh.dienstlich_netz,
        eauto_ladedaten=tuple(roh.eauto_ladedaten),
        wallbox_ladedaten=tuple(roh.wallbox_ladedaten),
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

    return MonatsFakt(
        jahr=jahr,
        monat=monat,
        zaehler=zaehler,
        erzeugung=erzeugung,
        bkw=BkwFakten(
            erzeugung_kwh=roh.bkw_erzeugung,
            eigenverbrauch_gemessen_kwh=roh.bkw_eigenverbrauch,
            rest_eigenverbrauch_kwh=roh.bkw_rest_eigenverbrauch,
            speicher_ladung_kwh=roh.bkw_speicher_ladung,
            speicher_entladung_kwh=roh.bkw_speicher_entladung,
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
        ),
        sonstiges=SonstigesFakten(
            erzeugung_kwh=roh.sonstiges_erzeugung,
            verbrauch_kwh=roh.sonstiges_verbrauch,
            ertraege_euro=round(ertraege, 2),
            ausgaben_euro=round(ausgaben, 2),
            netto_euro=round(ertraege - ausgaben, 2),
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
        einspeiseverguetung_cent=(
            allgemein.einspeiseverguetung_cent_kwh
            if allgemein
            else EINSPEISEVERGUETUNG_DEFAULT_CENT
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
