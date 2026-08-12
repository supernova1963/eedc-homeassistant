"""Was-wäre-wenn-Sizing: „lohnt sich ein größerer Speicher?" (#358 Phase 3).

**Warum diese Datei existiert.** Phase 2 (`speicher_potential.py`) beantwortet
„hätte mehr Kapazität *überhaupt* etwas gebracht?" mit einer gedeckelten
Obergrenze. Sie sagt bewusst **nicht**, *wie viel* Kapazität nötig gewesen wäre
und was sie gekostet hätte. Genau das rechnet diese Datei: eine
**Vorwärtssimulation** über die real gemessenen Stundenwerte, mit variierter
Kapazität.

## Die drei Entscheidungen, an denen das steht (gemessen 2026-08-12, 355 Tage)

**1. Eingang ist PV + Hausverbrauch — nicht `batterie_kw`.** Die Simulation
fährt den Speicher selbst, sie braucht seine gemessene Bewegung nicht. Das ist
kein Zufall, sondern der Grund, warum auch Anlagen mit **invertierter
Vorzeichen-Historie** (Daten-Checker `BATTERIE_VORZEICHEN_HISTORIE`) auswertbar
bleiben: die Validierung fiel auf der Alt-Hälfte (+2,4 % Einspeisung / −2,8 %
Netzbezug) sogar besser aus als auf der korrigierten.

**2. Simuliert wird mit der *effektiv genutzten* Kapazität, nicht mit dem
Typenschild.** Aus der SoC-Bewegung derselben Anlage: 8,2–8,4 kWh effektiv und
84,6–86,7 % Roundtrip, gepflegt sind 12,1 kWh / 95 %. Mit den gepflegten
Parametern verfehlt die Simulation den Netzbezug um **−17,5 %**, mit den
kalibrierten um **−4,3 %**.

⛔ **Das ist KEIN Gerätebefund.** Gegenprobe an 28 Tagen mit vollem
SoC-Durchlauf (100 → 0 %): Median-Ladung **12,0 kWh** — die gepflegten 12,1 kWh
stimmen. Die kleinere Zahl ist der Teil, den die Anlage im Alltag *wirklich*
bewegt: Reserven, Ladestrategie, Leistungsgrenzen, Standby. Wer mit dem
Typenschild simuliert, **überschätzt den Speichernutzen systematisch** — dieselbe
Richtung, in die schon die verworfene Phase-2-Formel falsch lag. Diese Datei darf
die Kalibrierung deshalb nicht als „Ihr Speicher ist kleiner als angegeben"
verkaufen, und die Sicht tut es auch nicht.

**3. Der Wirkungsgrad sitzt ganz auf der Ladeseite.** Weil die Kalibrierung die
Kapazität auf der **Entladeseite** misst (was kommt je 100 % SoC heraus), ist der
Speicherinhalt bereits „abgabefertige" Energie. Die Verluste einmal beim Laden zu
verrechnen ist damit vollständig; sie zusätzlich beim Entladen anzusetzen wäre
Doppelzählung.

## Was diese Simulation NICHT kann

Sie kennt nur das beobachtete Wetter und das beobachtete Verbrauchsverhalten —
und dieses Verhalten ist bereits auf den **vorhandenen** Speicher eingespielt
(Lastverschiebung). Sie trägt die individuelle Saisonalität, aber sie ist keine
Vorhersage. Die Sicht sagt das als Pflicht-Hinweis, statt eine Genauigkeit zu
versprechen, die die Methode nicht hat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, Optional, Sequence

#: Ein Stundenwert gilt als bilanzkonsistent, wenn
#: ``pv − verbrauch + batterie − (einspeisung − netzbezug)`` betragsmäßig
#: darunter bleibt. 0,15 kWh ist die Schwelle, mit der die Vorprüfung
#: 182 von 183 Alt-Tagen sauber dem invertierten Regime zuordnen konnte.
BILANZ_TOLERANZ_KWH: float = 0.15

#: Mindest-SoC-Hub eines Stundenpaares, das in die Kalibrierung eingeht.
#: Kleine Sprünge tragen zu viel Quantisierungs- und Rundungsrauschen: bei 1 pp
#: Hub schlägt ein 0,05-kWh-Messfehler mit 5 kWh/100 % durch.
MIN_SOC_HUB_PROZENTPUNKTE: float = 10.0

#: Mindest-Batterieleistung (kWh in der Stunde), ab der ein Paar als eindeutig
#: geladen bzw. entladen gilt — trennt echte Bewegung von Standby-Rauschen.
MIN_BATTERIE_KWH: float = 0.2

#: Mindestanzahl Paare **je Seite**. Die Entladeseite ist die dünnere (an der
#: Vorprüfungs-Anlage n≈100 gegen n≈430 beim Laden), und sie ist zugleich die,
#: die die Kapazität bestimmt — eine Kalibrierung, die nur die Ladeseite belegt,
#: ist keine.
MIN_PAARE_JE_SEITE: int = 20

#: Plausibles Band für den gemessenen Roundtrip. Über 100 % ist physikalisch
#: unmöglich (⇒ Datenfehler, keine Kalibrierung), unter 50 % ist kein Speicher
#: mehr, sondern eine kaputte Messkette.
ROUNDTRIP_MIN: float = 0.5
ROUNDTRIP_MAX: float = 1.0

#: Richtwert für die Amortisations-Aussage, wenn der Nutzer keine eigenen
#: Kosten kennt: Endkunden-Nachrüstpreis je kWh nutzbarer Kapazität (2026).
#: Bewusst grob und in der Sicht als Annahme benannt — die Aussage „über
#: 30 Jahre" kippt an ±100 €/kWh nicht.
RICHTPREIS_EUR_JE_KWH: float = 500.0

#: Tage im Bezugsjahr für die Hochrechnung eines Teilzeitraums.
TAGE_JE_JAHR: float = 365.0


@dataclass(frozen=True)
class SizingStunde:
    """Eine Stundenzeile, so weit die Simulation sie braucht.

    Alle Energiemengen in **kWh der Stunde**; ``soc_prozent`` in Prozent.
    ``batterie_kwh`` folgt dem Spalten-SoT (`core.berechnungen.batterie_kw_spalte`):
    **positiv = Entladung**, negativ = Ladung. ``None`` heißt durchgehend „nicht
    gemessen" und wird nirgends als 0 gedeutet.
    """

    zeit: datetime
    pv_kwh: Optional[float]
    verbrauch_kwh: Optional[float]
    soc_prozent: Optional[float] = None
    batterie_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None


@dataclass(frozen=True)
class SimErgebnis:
    """Was ein Speicher dieser Größe über den Zeitraum bewirkt hätte."""

    kapazitaet_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    #: PV, die im Haus geblieben ist (inkl. der Verluste des Speichers) — die
    #: Größe, die „Eigenverbrauch" in allen anderen Sichten meint.
    eigenverbrauch_kwh: float
    pv_kwh: float
    verbrauch_kwh: float
    #: Was der Roundtrip gekostet hat. Steht getrennt, weil ``eigenverbrauch``
    #: sie enthält und die Differenz sonst als Rechenfehler gelesen wird.
    speicherverluste_kwh: float
    #: Stunden ohne PV- oder Verbrauchswert — übersprungen, nicht als 0 gerechnet.
    stunden_ohne_eingang: int


#: Ab diesem Anteil an Tagen, die den Speicher bis `SOC_VOLL_PROZENT` füllen,
#: gilt: die Anlage lädt planmäßig voll. Darunter deutet die Lücke zwischen
#: gepflegter und gemessener Kapazität auf eine **Ladegrenze** (der Anwender
#: will gar nicht auf 100 %), darüber auf **Ladeverluste**. 20 % ist bewusst
#: niedrig: eine Anlage mit Ladegrenze erreicht die Schwelle an **keinem** Tag,
#: eine Winteranlage ohne Grenze an vielen Sommertagen (Referenzanlage 247/361).
ANTEIL_TAGE_VOLL_SCHWELLE: float = 0.20

#: Ab hier gilt ein Ladestand als „voll" bzw. „leer" — dieselben Schwellen wie
#: in `speicher_potential.py` (Phase 2), damit zwei Blöcke desselben Hubs nicht
#: verschiedene Definitionen von „voll" verwenden.
SOC_VOLL_PROZENT: float = 95.0
SOC_LEER_PROZENT: float = 5.0


@dataclass(frozen=True)
class SocNutzung:
    """Welchen Ladestands-Bereich die Anlage im Alltag tatsächlich fährt.

    **Der Grund für diese Auswertung** (N-238, Gernots Einwand 2026-08-12): die
    gepflegte nutzbare Kapazität ist eine **Absicht** — sie trägt genau den
    Fall „ich will meinen Speicher nicht dauernd auf 100 % laden". Die
    gemessene effektive Kapazität ist **Verhalten**. Liegen beide auseinander,
    gibt es zwei völlig verschiedene Ursachen, und ohne diese Zahlen lassen sie
    sich nicht unterscheiden:

    * Die Anlage erreicht die oberen Ladestände **gar nicht** ⇒ Ladegrenze,
      also gewollt; dann gehört die *gepflegte* Zahl überprüft.
    * Die Anlage lädt voll durch, die Kapazität kommt trotzdem kleiner heraus
      ⇒ **Ladeverluste** (an der Referenzanlage nimmt der Speicher im obersten
      SoC-Fünftel 18,7 kWh je 100 % SoC auf gegen 7–9,5 in der Mitte — die
      Absorptionsphase); dann ist die gepflegte Zahl richtig und die kleinere
      beschreibt den Durchsatz.
    """

    stunden_mit_soc: int
    tage_mit_soc: int
    #: 5./50./95.-Perzentil des Stunden-SoC — der Bereich, in dem sie wirklich lebt.
    soc_p5: float
    soc_median: float
    soc_p95: float
    #: Median des **Tages**-Maximums: „wie weit lädt sie an einem typischen Tag?"
    tages_max_median: float
    #: Tage, an denen der Speicher `SOC_VOLL_PROZENT` erreicht hat.
    tage_bis_voll: int
    #: Tage, an denen er unter `SOC_LEER_PROZENT` gefallen ist.
    tage_bis_leer: int

    @property
    def anteil_tage_voll(self) -> float:
        return self.tage_bis_voll / self.tage_mit_soc if self.tage_mit_soc else 0.0

    @property
    def laedt_planmaessig_voll(self) -> bool:
        """True = die Lücke ist Verlust, False = die Lücke ist eine Ladegrenze.

        Das ist die Aussage, die die Sicht braucht — nicht die Rohzahlen.
        """
        return self.anteil_tage_voll >= ANTEIL_TAGE_VOLL_SCHWELLE


def messe_soc_nutzung(stunden: Sequence[SizingStunde]) -> Optional[SocNutzung]:
    """Perzentile und Tages-Extreme des Ladestands. ``None`` ohne SoC-Werte.

    Bewusst **ohne** Bilanzprobe: hier wird der SoC selbst ausgewertet, nicht
    die Energiebilanz — eine Stunde mit invertiertem `batterie_kwh` trägt einen
    völlig korrekten Ladestand. Die Vorzeichen-Frage betrifft nur die
    Kalibrierung.
    """
    mit_soc = [z for z in stunden if z.soc_prozent is not None]
    if not mit_soc:
        return None

    werte = sorted(z.soc_prozent for z in mit_soc)
    n = len(werte)

    def perzentil(p: float) -> float:
        return werte[min(n - 1, max(0, int(p * (n - 1))))]

    je_tag: dict = {}
    for z in mit_soc:
        je_tag.setdefault(z.zeit.date(), []).append(z.soc_prozent)
    maxima = [max(v) for v in je_tag.values()]

    return SocNutzung(
        stunden_mit_soc=n,
        tage_mit_soc=len(je_tag),
        soc_p5=perzentil(0.05),
        soc_median=perzentil(0.5),
        soc_p95=perzentil(0.95),
        tages_max_median=median(maxima),
        tage_bis_voll=sum(1 for m in maxima if m >= SOC_VOLL_PROZENT),
        tage_bis_leer=sum(
            1 for v in je_tag.values() if min(v) <= SOC_LEER_PROZENT
        ),
    )


@dataclass(frozen=True)
class Kalibrierung:
    """Effektiv genutzte Kapazität und Roundtrip, aus der SoC-Bewegung gemessen."""

    #: kWh, die je 100 % SoC **herauskommen** — die Größe, mit der simuliert wird.
    kapazitaet_kwh: float
    #: kWh, die je 100 % SoC **hineingehen**. Nur zur Nachvollziehbarkeit.
    ladung_je_100_prozent_kwh: float
    #: ``kapazitaet_kwh / ladung_je_100_prozent_kwh`` — 0…1.
    roundtrip: float
    paare_laden: int
    paare_entladen: int
    #: Stunden, die die Bilanzprobe verworfen hat (Vorzeichen-Regime, Lücken).
    stunden_verworfen: int


@dataclass(frozen=True)
class SizingPunkt:
    """Ein Punkt der Sizing-Kurve — eine Kapazität und ihr Ertrag."""

    faktor: float
    kapazitaet_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    eigenverbrauch_kwh: float
    #: Gegen die Basis (= heutige Kapazität). Negativ = weniger als heute.
    delta_netzbezug_kwh: float
    delta_einspeisung_kwh: float
    #: Auf ein volles Jahr hochgerechneter Netto-Nutzen. ``None`` ohne Preise.
    nutzen_euro_jahr: Optional[float] = None
    #: Was die Kapazitätsdifferenz zum Richtpreis kostet (0 bei Verkleinerung).
    mehrkosten_euro: Optional[float] = None
    #: ``mehrkosten / nutzen_euro_jahr``. ``None``, wenn eine der beiden Seiten
    #: fehlt oder der Nutzen ≤ 0 ist — „unendlich lang" ist keine Jahreszahl.
    amortisation_jahre: Optional[float] = None


@dataclass(frozen=True)
class SizingBewertung:
    """Die Preisseite der Kurve.

    ``bezug_preis_cent`` und ``einspeise_verg_cent`` sind der **Spread-Kanon**
    (Gernot 2026-08-04): gesparter Netzbezug zählt zum Bezugspreis, die dafür
    entgangene Einspeisung wird abgezogen. Nur den Bezugspreis anzusetzen ist
    genau der Fehler, den v4.0.5 aus `aktueller_monat.py` entfernt hat (bei
    30/8 ct 36 % zu hoch).
    """

    bezug_preis_cent: float
    einspeise_verg_cent: float
    #: Länge des ausgewerteten Zeitraums — die Kurve rechnet auf ein Jahr hoch.
    tage_im_zeitraum: int
    richtpreis_eur_je_kwh: float = RICHTPREIS_EUR_JE_KWH


# --------------------------------------------------------------- Simulation --


def simuliere_speicher(
    stunden: Sequence[SizingStunde] | Iterable[SizingStunde],
    kap_kwh: float,
    eta: float,
    start_soc_anteil: float = 0.5,
) -> SimErgebnis:
    """Fährt einen Speicher der Größe ``kap_kwh`` durch die Stundenreihe.

    Pro Stunde ``netto = pv − verbrauch``. Überschuss lädt (der Wirkungsgrad
    frisst dabei seinen Anteil, s. Modul-Docstring Punkt 3), Defizit entlädt;
    was der Speicher nicht aufnimmt, geht ins Netz, was er nicht deckt, kommt
    von dort.

    ``start_soc_anteil`` ist über einen realistischen Auswertungszeitraum
    praktisch bedeutungslos (ein halber Speicher gegen mehrere MWh Durchsatz);
    er existiert, damit kurze Testreihen deterministisch sind.

    Bei ``kap_kwh <= 0`` läuft dieselbe Bilanz **ohne** Speicher — das ist der
    ehrliche untere Anker der Kurve, kein Sonderfall.
    """
    kap = max(0.0, kap_kwh)
    wirkungsgrad = max(0.0, min(1.0, eta))
    soc = kap * max(0.0, min(1.0, start_soc_anteil))
    start_inhalt = soc

    pv_summe = 0.0
    verbrauch_summe = 0.0
    einspeisung = 0.0
    netzbezug = 0.0
    ohne_eingang = 0

    for zeile in stunden:
        if zeile.pv_kwh is None or zeile.verbrauch_kwh is None:
            # Eine Stunde ohne Eingang ist keine Stunde mit 0 kWh Verbrauch —
            # als 0 gerechnet würde sie dem simulierten Speicher eine Ladepause
            # schenken, die es nie gab.
            ohne_eingang += 1
            continue

        pv = zeile.pv_kwh
        verbrauch = zeile.verbrauch_kwh
        pv_summe += pv
        verbrauch_summe += verbrauch
        netto = pv - verbrauch

        if netto > 0:
            # Aufnahmefähigkeit auf der EINGANGS-Seite: um den Inhalt um
            # (kap − soc) zu heben, müssen (kap − soc)/η hinein.
            aufnahme = (kap - soc) / wirkungsgrad if wirkungsgrad > 0 else 0.0
            ladung = min(netto, max(0.0, aufnahme))
            soc = min(kap, soc + ladung * wirkungsgrad)
            einspeisung += netto - ladung
        else:
            defizit = -netto
            entladung = min(defizit, soc)
            soc -= entladung
            netzbezug += defizit - entladung

    eigenverbrauch = pv_summe - einspeisung
    # Energieerhaltung: rein = pv + netzbezug, raus = verbrauch + einspeisung
    # + Verluste + was im Speicher liegen blieb.
    verluste = (
        pv_summe + netzbezug - verbrauch_summe - einspeisung - (soc - start_inhalt)
    )

    return SimErgebnis(
        kapazitaet_kwh=round(kap, 3),
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        eigenverbrauch_kwh=eigenverbrauch,
        pv_kwh=pv_summe,
        verbrauch_kwh=verbrauch_summe,
        speicherverluste_kwh=max(0.0, verluste),
        stunden_ohne_eingang=ohne_eingang,
    )


# ------------------------------------------------------------- Kalibrierung --


def _ist_bilanzkonsistent(zeile: SizingStunde) -> bool:
    """``pv − verbrauch + batterie == einspeisung − netzbezug`` (± Toleranz).

    Der Zweck ist **nicht** Datenqualität im Allgemeinen, sondern eine einzige
    Frage: trägt diese Stunde das heutige oder das invertierte Vorzeichen von
    ``batterie_kwh``? Fehlt ein Summand, kann die Probe nichts belegen — dann
    gilt die Stunde als nicht verwertbar, nicht als „in Ordnung".
    """
    teile = (
        zeile.pv_kwh,
        zeile.verbrauch_kwh,
        zeile.batterie_kwh,
        zeile.einspeisung_kwh,
        zeile.netzbezug_kwh,
    )
    if any(t is None for t in teile):
        return False
    pv, verbrauch, batterie, einspeisung, netzbezug = teile
    rest = (pv - verbrauch + batterie) - (einspeisung - netzbezug)
    return abs(rest) <= BILANZ_TOLERANZ_KWH


def kalibriere_speicher(
    stunden: Sequence[SizingStunde],
) -> Optional[Kalibrierung]:
    """Misst effektive Kapazität und Roundtrip aus der SoC-Bewegung.

    Ausgewertet werden **benachbarte** Stundenpaare (genau eine Stunde
    auseinander) mit deutlichem SoC-Hub. Aus jedem Paar folgt „wie viele kWh
    entsprechen 100 % SoC" — die Ladeseite liefert die Eingangs-, die
    Entladeseite die Ausgangsgröße; ihr Quotient ist der Roundtrip.

    Drei Dinge sind hier Pflicht, nicht Geschmack:

    1. **Bilanzprobe je Stunde.** Eine Anlage mit invertierter
       Vorzeichen-Historie mischt sonst zwei Regime: die erste Fassung dieser
       Messung ergab an genau diesem Datenbestand **0,91 kWh/100 %** statt 8,3.
    2. **Median, keine Ausgleichsrechnung.** Least-Squares über alle Paare wird
       von SoC-Sprüngen an Tagesgrenzen dominiert, weil es quadratisch gewichtet.
    3. **Beide Seiten belegt.** Die Entladeseite ist die dünnere und zugleich
       die, die die Kapazität bestimmt.

    ⚠ **Was diese Zahl trägt, ist die Jahres-Validierung — nicht der Median**
    (nachgemessen 2026-08-12 auf Gernots Rückfrage zu N-238). Der Paar-Median
    ist **schwellenabhängig**: mit `MIN_SOC_HUB_PROZENTPUNKTE` = 3 statt 10
    liefert derselbe Datenbestand **9,64 kWh** statt 8,35, weil dann die vielen
    kleinen SoC-Schritte mit ihrer Quantisierung dominieren. Entschieden hat ein
    Parametergitter gegen das real gemessene Jahr (355 Tage, Σ der absoluten
    Abweichung auf Einspeisung **und** Netzbezug):

    ==============================  ===========  ==========  =====
    Parametrisierung                Einspeisung  Netzbezug   Σ|Δ|
    ==============================  ===========  ==========  =====
    **gebaut (8,35 · 86,7 %)**      +2,2 %       −5,4 %      7,6
    ≥ 3 pp (9,64 · 97,6 %)          +3,7 %       −12,1 %     15,8
    gepflegt (12,1 · 95 %)          +1,9 %       −17,5 %     19,4
    bestes Gitter (7,5 · 80 %)      +1,3 %       −0,1 %      1,4
    ==============================  ===========  ==========  =====

    Die 10-pp-Schwelle landet also nahe am Optimum und klar vor beiden
    Alternativen — aber sie ist **kalibriert, nicht hergeleitet**. Wer sie
    ändert, misst die Jahres-Abweichung neu und schreibt sie hier hin; ein
    besserer Median allein belegt nichts.

    Returns:
        ``None``, wenn eine Seite zu dünn ist oder der Roundtrip außerhalb des
        plausiblen Bandes liegt. Der Aufrufer fällt dann auf die **gepflegten**
        Parameter zurück und weist die Unsicherheit aus — still weiterrechnen
        wäre die schlechteste der drei Möglichkeiten.
    """
    laden: list[float] = []
    entladen: list[float] = []
    verworfen = 0

    for vorher, nachher in zip(stunden, stunden[1:]):
        if nachher.zeit - vorher.zeit != timedelta(hours=1):
            continue  # Lücke oder Tagesgrenze ohne Nachbarn — kein Paar.
        if not _ist_bilanzkonsistent(nachher):
            verworfen += 1
            continue

        soc_vor, soc_nach = vorher.soc_prozent, nachher.soc_prozent
        batterie = nachher.batterie_kwh
        if soc_vor is None or soc_nach is None or batterie is None:
            continue
        hub = soc_nach - soc_vor
        if abs(hub) < MIN_SOC_HUB_PROZENTPUNKTE:
            continue

        if hub > 0 and batterie <= -MIN_BATTERIE_KWH:
            laden.append(-batterie / hub * 100.0)
        elif hub < 0 and batterie >= MIN_BATTERIE_KWH:
            entladen.append(batterie / -hub * 100.0)

    if len(laden) < MIN_PAARE_JE_SEITE or len(entladen) < MIN_PAARE_JE_SEITE:
        return None

    je_100_laden = median(laden)
    je_100_entladen = median(entladen)
    if je_100_laden <= 0 or je_100_entladen <= 0:
        return None

    roundtrip = je_100_entladen / je_100_laden
    if not (ROUNDTRIP_MIN <= roundtrip <= ROUNDTRIP_MAX):
        return None

    return Kalibrierung(
        kapazitaet_kwh=je_100_entladen,
        ladung_je_100_prozent_kwh=je_100_laden,
        roundtrip=roundtrip,
        paare_laden=len(laden),
        paare_entladen=len(entladen),
        stunden_verworfen=verworfen,
    )


# ------------------------------------------------------------ Sizing-Kurve --


def nutzen_euro(
    delta_netzbezug_kwh: float,
    delta_einspeisung_kwh: float,
    bewertung: SizingBewertung,
) -> float:
    """Netto-Nutzen einer Kapazitätsänderung im Zeitraum (Spread-Kanon).

    ``gesparter Netzbezug × Bezugspreis − entgangene Einspeisung × Vergütung``.

    Beide Deltas kommen negativ herein, wenn die größere Batterie beides senkt.
    Sie sind **nicht** gleich groß: die Differenz ist der Roundtrip-Verlust —
    genau deshalb reicht es nicht, den Spread auf eine der beiden Mengen zu
    legen, und genau deshalb steht die Bewertung hier und nicht am Aufrufer.
    """
    gespart = -delta_netzbezug_kwh * bewertung.bezug_preis_cent / 100.0
    entgangen = -delta_einspeisung_kwh * bewertung.einspeise_verg_cent / 100.0
    return gespart - entgangen


def sizing_kurve(
    stunden: Sequence[SizingStunde],
    basis: Kalibrierung,
    faktoren: Sequence[float],
    *,
    bewertung: Optional[SizingBewertung] = None,
) -> list[SizingPunkt]:
    """Simuliert die Reihe für jede Kapazität ``basis × faktor``.

    Bezugspunkt jeder Δ-Angabe ist ``faktor == 1.0``, also die **heutige**
    Kapazität — nicht der kleinste Punkt der Kurve. Er wird immer mitsimuliert,
    auch wenn er nicht in ``faktoren`` steht.

    Ohne ``bewertung`` bleiben die Euro-Felder ``None``: eine Anlage ohne
    gepflegten Tarif bekommt die Energie-Kurve, keine erfundenen Preise.
    """
    referenz = simuliere_speicher(stunden, basis.kapazitaet_kwh, basis.roundtrip)

    punkte: list[SizingPunkt] = []
    for faktor in faktoren:
        ergebnis = simuliere_speicher(
            stunden, basis.kapazitaet_kwh * faktor, basis.roundtrip
        )
        d_netz = ergebnis.netzbezug_kwh - referenz.netzbezug_kwh
        d_ein = ergebnis.einspeisung_kwh - referenz.einspeisung_kwh

        nutzen_jahr: Optional[float] = None
        mehrkosten: Optional[float] = None
        amortisation: Optional[float] = None
        if bewertung is not None and bewertung.tage_im_zeitraum > 0:
            hochrechnung = TAGE_JE_JAHR / bewertung.tage_im_zeitraum
            nutzen_jahr = nutzen_euro(d_netz, d_ein, bewertung) * hochrechnung
            mehr_kwh = max(0.0, ergebnis.kapazitaet_kwh - referenz.kapazitaet_kwh)
            mehrkosten = mehr_kwh * bewertung.richtpreis_eur_je_kwh
            if mehr_kwh > 0 and nutzen_jahr > 0:
                amortisation = mehrkosten / nutzen_jahr

        punkte.append(SizingPunkt(
            faktor=faktor,
            kapazitaet_kwh=ergebnis.kapazitaet_kwh,
            einspeisung_kwh=ergebnis.einspeisung_kwh,
            netzbezug_kwh=ergebnis.netzbezug_kwh,
            eigenverbrauch_kwh=ergebnis.eigenverbrauch_kwh,
            delta_netzbezug_kwh=d_netz,
            delta_einspeisung_kwh=d_ein,
            nutzen_euro_jahr=nutzen_jahr,
            mehrkosten_euro=mehrkosten,
            amortisation_jahre=amortisation,
        ))

    return punkte


__all__ = [
    "ANTEIL_TAGE_VOLL_SCHWELLE",
    "BILANZ_TOLERANZ_KWH",
    "MIN_PAARE_JE_SEITE",
    "MIN_SOC_HUB_PROZENTPUNKTE",
    "RICHTPREIS_EUR_JE_KWH",
    "Kalibrierung",
    "SimErgebnis",
    "SizingBewertung",
    "SizingPunkt",
    "SizingStunde",
    "SocNutzung",
    "kalibriere_speicher",
    "messe_soc_nutzung",
    "nutzen_euro",
    "simuliere_speicher",
    "sizing_kurve",
]
