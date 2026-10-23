"""WP-Stromaufteilung (K1/K3/K5): Vorrangkette, Toleranzen, `WpStromAufteilung`, `get_wp_strom_kwh`.
"""
# Reiner Umzug aus `core/field_definitions.py` (18.09.2026, Vorlage 3 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert
# alle Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from dataclasses import dataclass
from typing import Final, Literal
from backend.core.field_definitions.auswahl import get_felder_fuer_investition


#: Die zwei **Summanden**-Achsen des Wärmepumpen-Stroms (Gegenstück zu den
#: Betriebsart-Teilmengen). Nur die Namen — welche davon ein konkretes Gerät
#: hat, beantwortet `feine_strom_achsen` an der Registry.
FEINE_STROM_FELDER: Final[tuple[str, ...]] = (
    "strom_heizen_kwh", "strom_warmwasser_kwh",
)

#: Die Feldnamen, unter denen eine **Gesamt**-Strommenge einer Wärmepumpe in
#: einer Monatszeile stehen kann — das kanonische Feld und seine zwei
#: Legacy-Namen. ⭐ Sie stehen hier als Liste, seit K3 Regel 4 (R-1) fragen muss,
#: ob **überhaupt** eine Gesamtmenge da ist: dieselbe Kette ein zweites Mal
#: hinzuschreiben wäre die F-56-Form.
WP_GESAMT_STROM_FELDER: Final[tuple[str, ...]] = (
    "stromverbrauch_kwh", "strom_kwh", "verbrauch_kwh",
)

def feine_strom_achsen(parameter: dict) -> list[str]:
    """Welche feinen Strom-Achsen **hat** dieses Gerät? (K3, SOLL §3.2)

    Die Frage ist eine Eigenschaft des **Geräts**, nicht der Erfassung: Eine
    Luft-Wasser-Wärmepumpe hat Heizen und Warmwasser, eine Split-Klimaanlage
    nur Heizen (kein Warmwasserkreis — ``strom_warmwasser_kwh`` trägt
    ``!luft_luft``, N-304/B5).

    ⚠ **Deshalb wird die Registry mit gesetztem Kennzeichen befragt**, auch wenn
    es an der Investition aus ist: ``getrennte_strommessung`` sagt, ob die Achsen
    *getrennt erfasst werden*, nicht ob es sie *gibt*. Ohne diese Normalisierung
    meldete ein Gerät mit ausgeschaltetem Kennzeichen „gar keine Achsen" — und
    K3 könnte in dieser Richtung (Kennzeichen aus, feiner Zähler zugeordnet)
    nicht greifen.

    ⭐ **Registry statt Bauart-Abfrage** (R1): ``ist_luft_luft_waermepumpe`` hier
    aufzurufen wäre die zweite Stelle, die dieselbe Frage beantwortet — genau
    die Drift-Klasse, an der F-56 entstanden ist.

    ⛔ **Hier stand sie bis zum 13.09.2026 nicht, sondern in**
    ``services/snapshot/komponenten_beitraege.py`` — mit einem *lokalen* Import
    auf dieses Modul, weil ein Modul-Import zirkulär gewesen wäre. Sie ist
    hierher gezogen worden, als {@link wp_strom_stufe} dieselbe Frage stellte:
    Die K3-Stufenregel steht seither an **einer** Stelle statt an zweien (F-56).

    ⚠ **Seit WK-16d (14.09.2026) fragt die Stufenregel sie nicht mehr** — ein
    Gesamtzähler ist die Menge, ob die Aufteilung vollständig ist oder nicht.
    Geblieben ist ihr **zweiter** Leser, und der ist der ältere: die
    Beitragsschicht des Tages braucht die Namen der Achsen, die sie emittiert,
    wenn kein Gesamtzähler zugeordnet ist. Sie bleibt hier, damit *„welche
    Achsen hat dieses Gerät?"* weiterhin an **einer** Stelle beantwortet wird.
    """
    angeboten = {
        f["feld"] for f in get_felder_fuer_investition(
            "waermepumpe", {**(parameter or {}), "getrennte_strommessung": True},
        )
    }
    return [f for f in FEINE_STROM_FELDER if f in angeboten]

#: Wie weit darf der Gesamtzähler **unter** der Summe der Achsen liegen, bevor
#: eedc ihn für widersprüchlich hält? — **eine** Stelle für beide Ebenen
#: (WK-16d/K1). Anteilig, weil ein Zählerstand mit der Menge rundet; mit einem
#: Mindestwert, weil 1 % einer kleinen Menge unter jeder Rundung liegt.
WP_STROM_TOLERANZ_ANTEIL: Final[float] = 0.01

#: Mindest-Toleranz einer **Monats**zeile (kWh) — wie beim Wärme-Zwilling in
#: ``daten_checker/monatsdaten.py`` (N-391).
WP_STROM_TOLERANZ_MIN_MONAT_KWH: Final[float] = 0.5

#: Mindest-Toleranz eines **Tages** (kWh). Ein Zehntel der Monatsschwelle:
#: dieselbe Rundung, ein Dreißigstel der Menge.
WP_STROM_TOLERANZ_MIN_TAG_KWH: Final[float] = 0.05

def wp_strom_toleranz_kwh(
    feine_summe_kwh: float,
    *,
    mindest_kwh: float = WP_STROM_TOLERANZ_MIN_MONAT_KWH,
) -> float:
    """Die Toleranz für *„Gesamtzähler kleiner als die Summe der Achsen?"*.

    ⛔ **Sie steht hier und nicht bei den zwei Fragern** ({@link
    wp_strom_stufe} und der Daten-Checker, der dieselbe Lage meldet): Zwei
    Schwellen für dieselbe Frage wären die F-56-Klasse — die Fläche würde eine
    Lage bemängeln, die die Rechnung daneben durchgehen lässt, oder umgekehrt.
    """
    return max(abs(feine_summe_kwh) * WP_STROM_TOLERANZ_ANTEIL, mindest_kwh)

def wp_strom_stufe(
    *,
    hat_gesamtzaehler: bool,
    gesamt_kwh: float | None = None,
    feine_summe_kwh: float | None = None,
    toleranz_mindest_kwh: float = WP_STROM_TOLERANZ_MIN_MONAT_KWH,
    hat_feine_achsen: bool = True,
    hat_betriebsart_zaehler: bool = False,
) -> Literal["fein", "gesamt", "betriebsart"]:
    """K3 in EINER Stelle — die Regel, nicht ihre Eingänge (Konzept Kap. 3).

    Die Vorrangkette für *„welche Menge ist der Stromverbrauch dieses
    Geräts?"*:

    1. **Ein Gesamtzähler ist die Menge** (K1 — *„die Gesamtmenge ist immer die
       Wahrheit"*) ⇒ ``"gesamt"``. Die feinen Achsen (Heizen/Warmwasser) und die
       Betriebsart-Zähler sind die **Aufteilung darunter**; was er mehr misst
       als sie, heißt *nicht aufgeteilt* (K5, {@link wp_strom_aufteilung}).
    2. **Es sei denn, er misst weniger als die Aufteilung** — mehr als die
       Toleranz ({@link wp_strom_toleranz_kwh}) darunter ⇒ ``"fein"``, und der
       Daten-Checker nennt den Widerspruch. Zwilling der Wärme-Invariante aus
       N-391: nur **diese** Richtung ist ein Fehler.
    3. **Kein Gesamtzähler** ⇒ ``"fein"``: die Aufteilung ist dann die einzige
       Messung, die es gibt, ob sie vollständig ist oder nicht. Sie zu verwerfen
       hieße den Block verschwinden zu lassen (#263, OB73-gif).
    4. **Auch keine feinen Achsen, aber gemessene Betriebsart-Zähler** ⇒
       ``"betriebsart"``: dann sind *sie* die einzige Messung, und derselbe Satz
       aus Regel 3 gilt für sie (**R-1**, Konzept Kap. 3/K3, 15.09.2026).

    ⛔ **Regel 4 fehlte bis zum 15.09.2026, und der Satz von Regel 3 galt
    trotzdem schon** (N-486). Gemessen:
    ``get_wp_strom_kwh({'betriebsart_strom_heizen_kwh': 700}, {'wp_art':
    'luft_luft'})`` = **0,0**. Wer an seiner Split-Klimaanlage nur
    Betriebsart-Zähler zuordnete, bekam **gar keinen** Strom — keine Kosten,
    kein CO₂, keine Kennzahl —, während die Datenquellen-Fläche daneben
    „ausgewertet in …" behauptete. Die Begründung ist die **der Kategorie**,
    nicht des Beispiels: *ein Zähler, der misst, ist die einzige Messung, die es
    gibt.* Sie trägt für die feinen Achsen (Regel 3) und für die
    Betriebsart-Zähler gleichermaßen.

    ⚠ **Die Reihenfolge ist keine Geschmacksfrage.** Die Betriebsart-Zähler sind
    **Teilmengen** (Konzept Kap. 3, Familientabelle) — neben einer
    Summanden-Achse dürfen sie die Menge nicht tragen, sonst stünde in derselben
    Zeile eine Teilmenge an der Stelle eines Summanden. Sie kommen deshalb erst,
    wenn **weder** ein Gesamtzähler **noch** eine feine Achse da ist; dann teilen
    sie nichts mehr auf, sondern *sind* die Menge (Modus-Rest 0).

    ⚠ **E7 bleibt unberührt.** Die Summe ist eine **Menge**, kein
    Funktions-Nenner: ``arbeitszahl_je_funktion`` nimmt weiterhin ausschließlich
    den gemessenen Strom *dieser* Funktion, und der steht in
    ``strom_heizen_kwh``/``strom_warmwasser_kwh`` — in dieser Stufe gibt es ihn
    per Definition nicht.

    ⛔ **Hier stand bis zum 14.09.2026 eine erste Stufe: „Die feine Aufteilung
    ist vollständig ⇒ fein; ein zusätzlicher Gesamtzähler wird verworfen, sonst
    zählte derselbe Strom zweimal."** Der Satz stimmte für die *Doppelzählung*
    und war für die *Menge* falsch. Misst der Gesamtzähler **mehr** als die
    beiden Achsen — Standby, Steuerung, Umwälzpumpen; bei dietmar1968 145 von
    2193 kWh im Jahr, 6,6 % —, verlor eedc diese Kilowattstunden aus Strom,
    Kosten, CO₂ und Arbeitszahl-Nenner. Das verletzt **K1** und **K5**.
    *Doppelzählung entsteht beim **Addieren** von Gesamt und Achsen, nicht beim
    **Ersetzen*** — die alte Regel verhinderte das Falsche und verwarf dabei
    eine Messung.

    ⚠ **Tag und Monat beantworten „belegt?" verschieden — und sie MÜSSEN das.**
    Der Tag fragt *„ist ein Zähler zugeordnet?"* (``ist_verfuegbar``), der Monat
    *„steht ein Wert in der Zeile?"* (``data.get(feld) is not None``); eine
    Monatszeile darf ohne jeden Zähler von Hand gepflegt sein. Was beide teilen,
    ist die **Vorrangkette** — sie steht deshalb hier und nicht zweimal (F-56).
    Auf der Zuordnungs-Ebene gibt es keine Werte; dort bleiben ``gesamt_kwh``
    und ``feine_summe_kwh`` leer und Regel 2 greift nicht.

    ⛔ **Das Kennzeichen ``getrennte_strommessung`` steht nicht mehr hier.** Es
    beantwortet die andere Frage — *„sind die feinen Achsen **Summanden**?"* —
    und die stellt {@link get_wp_strom_kwh} vor dem Aufruf. K3 gilt weiter in
    beide Richtungen: Kennzeichen **aus**, kein Gesamtzähler, aber ein feiner
    Zähler zugeordnet ⇒ Regel 3, er trägt.

    Args:
        hat_gesamtzaehler: trägt dieses Gerät ``stromverbrauch_kwh`` — in der
            Ebene des Aufrufers (Zuordnung bzw. Zeilenwert).
        gesamt_kwh: sein Wert, wo es einen gibt (Monatszeile). ``None`` auf der
            Zuordnungs-Ebene.
        feine_summe_kwh: die Menge, die die Aufteilung sonst trüge — also genau
            das, was der feine Zweig von {@link get_wp_strom_kwh} rechnet.
        toleranz_mindest_kwh: ``WP_STROM_TOLERANZ_MIN_MONAT_KWH`` oder
            ``…_TAG_KWH``, je nach Ebene des Aufrufers.
        hat_feine_achsen: trägt dieses Gerät eine **Summanden**-Achse
            (``strom_heizen_kwh``/``strom_warmwasser_kwh``) — in der Ebene des
            Aufrufers. ⚠ **Default ``True``**, damit ein Aufrufer, der die Frage
            nicht stellt, bitgleich zu vor dem 15.09.2026 antwortet: Regel 4
            greift dann nie.
        hat_betriebsart_zaehler: trägt es einen **gemessenen**
            Betriebsart-Stromzähler (Gerätefeld oder Innengerät) — nur dann gibt
            es Regel 4 überhaupt.

    Returns:
        ``"gesamt"`` (``stromverbrauch_kwh`` trägt die Menge), ``"fein"`` (die
        Summanden-Achsen tragen sie) oder ``"betriebsart"`` (Σ der gemessenen
        Betriebsart-Ströme trägt sie).
    """
    def _ohne_gesamtzaehler() -> Literal["fein", "betriebsart"]:
        # Regel 4 vor Regel 3 nur dort, wo Regel 3 nichts zu tragen hat.
        if not hat_feine_achsen and hat_betriebsart_zaehler:
            return "betriebsart"
        return "fein"

    if not hat_gesamtzaehler:
        return _ohne_gesamtzaehler()
    if gesamt_kwh is not None and feine_summe_kwh is not None:
        if gesamt_kwh < feine_summe_kwh - wp_strom_toleranz_kwh(
            feine_summe_kwh, mindest_kwh=toleranz_mindest_kwh,
        ):
            return _ohne_gesamtzaehler()
    return "gesamt"

def wp_feine_summe_kwh(
    strom_heizen_kwh: float | None,
    strom_warmwasser_kwh: float | None,
    funktionsfremd_kwh: float = 0.0,
    *,
    betriebsart_gemessen: bool = False,
) -> float:
    """Was die **Summanden**-Aufteilung eines Geräts trägt (K4).

    ``strom_heizen_kwh + strom_warmwasser_kwh`` und — bei **gemessener**
    Betriebsart — die funktionsfremden Teilmengen (W-16: ein gemessener
    Betriebsart-Zähler steht *neben* den beiden Achsen, nicht darin; ein
    **abgeleiteter** Split verteilt dagegen die vorhandene Menge, ihn zu
    addieren wäre die Doppelzählung von W-16b).

    ⭐ **Warum das eine eigene Funktion ist** (WK-16c, 14.09.2026): Die Formel
    wird an **zwei** Ebenen gebraucht — an der Monatszeile von {@link
    wp_strom_aufteilung} und an den Tageswerten der Verteilungs-Sicht
    (``services/waerme_verteilung.py``), die keine ``verbrauch_daten``-Zeile
    hat, sondern Snapshot-Summen je Gerät. Sie dort nachzubauen wäre die
    F-56-Klasse; die **Eingänge** dürfen sich unterscheiden, die Formel nicht.
    """
    summe = float((strom_heizen_kwh or 0) + (strom_warmwasser_kwh or 0))
    if betriebsart_gemessen:
        summe += float(funktionsfremd_kwh or 0.0)
    return summe

def wp_nicht_aufgeteilt_kwh(
    menge_kwh: float, feine_summe_kwh: float, *, hat_aufteilung: bool,
) -> float:
    """Der **Zähler**-Rest eines Geräts (K5) — ``Menge − Aufteilung ≥ 0``.

    Standby, Steuerung, Umwälzpumpen — dietmar1968s „Systemverbrauch".

    ⚠ **``hat_aufteilung`` ist keine Formsache:** *„nicht aufgeteilt"* setzt
    eine Aufteilung voraus. Wer nur einen Gesamtzähler pflegt, hat keinen Rest,
    sondern nur eine Menge; dass die Achsen fehlen, sagt der Daten-Checker.

    ⛔ **Nicht zu verwechseln mit dem Modus-Rest**
    (``WpFakten.modus_nicht_aufgeteilt_kwh`` bzw.
    ``TagesStapel.nicht_aufgeteilt_kwh``). Zwei Reste zweier verschiedener
    Aufteilungen derselben Menge; sie zu addieren wäre Doppelzählung
    (Konzept Wärme/Klima Kap. 3, Zwei-Reste-Tabelle).

    Zweiter Aufrufer neben {@link wp_strom_aufteilung}: die Tagesebene der
    Verteilungs-Sicht — s. {@link wp_feine_summe_kwh}.
    """
    return max(0.0, menge_kwh - feine_summe_kwh) if hat_aufteilung else 0.0

@dataclass(frozen=True)
class WpStromAufteilung:
    """Menge **und** Rest einer Monatszeile — K1 und K5 in einer Antwort.

    ⭐ **Warum der Rest hier entsteht und nicht beim Leser.** Er ist die
    Differenz zweier Größen, die nur diese Funktion beide kennt: der gewählten
    Menge und der Summe, die die Aufteilung trägt. Ein Leser, der ihn selbst
    bildete, müsste die Stufenregel nachbauen — die F-56-Klasse.
    """

    #: Die Menge dieses Geräts (K1) — was jede Bilanz, jede Kosten- und jede
    #: CO₂-Rechnung liest.
    menge_kwh: float
    #: Was die feine Aufteilung trägt: ``strom_heizen_kwh + strom_warmwasser_kwh``
    #: und — bei **gemessener** Betriebsart — die funktionsfremden Teilmengen
    #: (W-16). 0.0 im Nicht-getrennt-Zweig: dort gibt es keine Summanden.
    feine_summe_kwh: float
    #: ``Menge − Aufteilung ≥ 0``, der **Zähler**-Rest (K5): Standby, Steuerung,
    #: Umwälzpumpen — dietmar1968s „Systemverbrauch".
    #:
    #: ⛔ **Nicht zu verwechseln mit** ``WpFakten.modus_nicht_aufgeteilt_kwh``.
    #: Das sind **zwei** Reste zweier **verschiedener** Aufteilungen derselben
    #: Menge, und beide sind richtig: hier der Rest der **Summanden**-Achsen
    #: (Heizen/Warmwasser), dort der Rest der **Betriebsart**-Teilmengen
    #: (Stunden ohne Modus-Signal). Sie zu addieren wäre Doppelzählung.
    #:
    #: ⚠ **0.0, solange es gar keine Aufteilung gibt** — *„nicht aufgeteilt"*
    #: setzt eine Aufteilung voraus. Wer nur einen Gesamtzähler pflegt, hat
    #: keinen Rest, sondern nur eine Menge; dass die Achsen fehlen, sagt der
    #: Daten-Checker, nicht diese Zahl.
    nicht_aufgeteilt_kwh: float
    #: Welche Regel gewonnen hat — s. {@link wp_strom_stufe}.
    stufe: Literal["fein", "gesamt"]
    #: Regel 2: der Gesamtzähler steht **unter** der Aufteilung (jenseits der
    #: Toleranz). Die Achsen tragen, und der Daten-Checker meldet es.
    gesamtzaehler_zu_klein: bool

def wp_strom_aufteilung(
    data: dict | None, params: dict | None = None,
) -> WpStromAufteilung:
    """Menge, Aufteilung und Rest einer Monatszeile (K1 · K3 · K5).

    Die **eine** Auflösung hinter {@link get_wp_strom_kwh}; dessen Rückgabe ist
    ``menge_kwh``. Wer zusätzlich den Rest oder den Widerspruch braucht — die
    Monats-Fakten und der Daten-Checker —, ruft diese Tür.
    """
    d = data or {}
    if not d:
        return WpStromAufteilung(0.0, 0.0, 0.0, "fein", False)

    # Lokaler Import: `betriebsart_gemessen` liest `basis_feld_key` aus diesem
    # Modul — ein Import auf Modulebene wäre zirkulär.
    from backend.core.berechnungen.betriebsart_gemessen import (
        modus_strom_zeile,
        summanden_gelten,
    )

    # N-766: dasselbe Kennzeichen wie die Frage darunter („sind die Achsen
    # Summanden?"). Die Menge der Stufe «betriebsart» bleibt Σ der
    # Betriebsart-Zähler: mit Kennzeichen erreicht man sie nur ohne Achsen,
    # ohne Kennzeichen zählen die Achsen nicht.
    zeile = modus_strom_zeile(d, summanden_zaehlen=summanden_gelten(params))

    if not (params or {}).get("getrennte_strommessung"):
        # ⚠ **Im Nicht-getrennt-Zweig wird NICHTS addiert und nichts
        # aufgeteilt:** ``stromverbrauch_kwh`` ist der Zählerstand des ganzen
        # Geräts und enthält den Kühlbetrieb bereits. Die feinen Felder sind
        # hier keine Summanden (das sagt gerade das fehlende Kennzeichen), es
        # gibt also auch keinen Rest einer Summanden-Aufteilung.
        #
        # ⭐ **R-1/K3 Regel 4 (15.09.2026, N-486):** Steht hier **gar keine**
        # Gesamtmenge — weder das kanonische Feld noch einer der beiden
        # Legacy-Namen —, dann sind die gemessenen Betriebsart-Zähler die
        # einzige Messung, die es gibt, und sie tragen. Das ist der Satz von
        # Regel 3, eine Familie weiter. ⚠ Der Zweig steht **vor** der
        # Menge-Zeile darunter, aber **hinter** der Frage nach dem Gesamtwert:
        # ein zugeordneter Gesamtzähler bleibt die Menge (K1), die
        # Betriebsart-Zähler bleiben seine Aufteilung.
        # ⛔ **Die Bedingung wird hier NICHT nachgebaut** — sonst stünde K3
        # Regel 4 an zwei Stellen, und genau das hat der Sprengsatz S1 am
        # 15.09.2026 sichtbar gemacht: Regel 4 aus ``wp_strom_stufe``
        # herausgenommen, und diese Zeile trug sie trotzdem weiter (F-56 in
        # Reinform, im selben Bau entstanden).
        if wp_strom_stufe(
            hat_gesamtzaehler=any(
                d.get(f) is not None for f in WP_GESAMT_STROM_FELDER
            ),
            # Ohne Kennzeichen sind die feinen Felder **keine** Summanden (das
            # sagt gerade das fehlende Kennzeichen) — sie können hier nichts
            # tragen, und Regel 3 hat nichts, worauf sie fallen könnte.
            hat_feine_achsen=False,
            hat_betriebsart_zaehler=zeile.gemessen,
        ) == "betriebsart":
            return WpStromAufteilung(
                menge_kwh=zeile.gemessene_summe_kwh,
                # Es gibt keine **Summanden**-Aufteilung — also auch keinen
                # Summanden-Rest (K5 setzt eine Aufteilung voraus). Der
                # Modus-Rest ist 0, weil die Menge Σ der Teilmengen IST; er
                # entsteht ohnehin woanders (`WpFakten.modus_nicht_aufgeteilt_kwh`).
                feine_summe_kwh=0.0,
                nicht_aufgeteilt_kwh=0.0,
                stufe="betriebsart",
                gesamtzaehler_zu_klein=False,
            )
        return WpStromAufteilung(
            menge_kwh=float(
                d.get("stromverbrauch_kwh")
                or d.get("strom_kwh")
                or d.get("verbrauch_kwh")
                or 0
            ),
            feine_summe_kwh=0.0,
            nicht_aufgeteilt_kwh=0.0,
            stufe="gesamt" if d.get("stromverbrauch_kwh") is not None else "fein",
            gesamtzaehler_zu_klein=False,
        )

    # W-16 und die Begründung stehen im Docstring von `wp_feine_summe_kwh` —
    # seit WK-16c an einer Stelle, weil die Tagesebene der Verteilungs-Sicht
    # dieselbe Formel auf Snapshot-Summen anwendet (F-56).
    feine_summe = wp_feine_summe_kwh(
        d.get("strom_heizen_kwh"), d.get("strom_warmwasser_kwh"),
        zeile.funktionsfremd_kwh, betriebsart_gemessen=zeile.gemessen,
    )

    gesamt = d.get("stromverbrauch_kwh")
    # R-1/K3 Regel 4: „hat feine Achsen?" fragt die **Zeile**, wie überall im
    # Monatspfad — `is not None`, nicht truthy: ein Warmwasser-Strom von 0,0 im
    # Sommer ist eine Messung und hält die Summanden-Familie offen.
    hat_f5_wert = any(d.get(f) is not None for f in FEINE_STROM_FELDER)
    stufe = wp_strom_stufe(
        hat_gesamtzaehler=gesamt is not None,
        gesamt_kwh=float(gesamt) if gesamt is not None else None,
        feine_summe_kwh=feine_summe,
        hat_feine_achsen=hat_f5_wert,
        hat_betriebsart_zaehler=zeile.gemessen,
    )
    if stufe == "betriebsart":
        # Kennzeichen gesetzt, aber keine der beiden Achsen gepflegt — das
        # Kennzeichen sagt, dass die Achsen *Summanden wären*, nicht dass sie
        # da sind (K3 gilt in beide Richtungen). Dann tragen die gemessenen
        # Betriebsart-Zähler, und zwar **alle vier**: bis zum 15.09.2026 stand
        # hier nur ihr funktionsfremder Teil (über `wp_feine_summe_kwh`), der
        # Heizstrom fiel heraus.
        return WpStromAufteilung(
            menge_kwh=zeile.gemessene_summe_kwh,
            feine_summe_kwh=0.0,
            nicht_aufgeteilt_kwh=0.0,
            stufe="betriebsart",
            gesamtzaehler_zu_klein=False,
        )
    zu_klein = gesamt is not None and stufe == "fein"
    menge = float(gesamt) if stufe == "gesamt" else feine_summe
    # K5 setzt eine Aufteilung voraus — s. Feld-Docstring. `is not None`, nicht
    # truthy: ein Warmwasser-Strom von 0,0 im Sommer ist eine Messung.
    hat_aufteilung = (
        any(d.get(f) is not None for f in FEINE_STROM_FELDER)
        or (zeile.gemessen and zeile.funktionsfremd_kwh > 0)
    )
    return WpStromAufteilung(
        menge_kwh=menge,
        feine_summe_kwh=feine_summe,
        nicht_aufgeteilt_kwh=wp_nicht_aufgeteilt_kwh(
            menge, feine_summe, hat_aufteilung=hat_aufteilung,
        ),
        stufe=stufe,
        gesamtzaehler_zu_klein=zu_klein,
    )

def nenner_ist_feine_summe(data: dict | None, params: dict | None) -> bool:
    """Ist der WP-Strom **dieser Monatszeile** die Summe der feinen Achsen?

    Die Frage, die {@link
    backend.core.berechnungen.betriebsart_gemessen.funktionsfremd_abzug_kwh}
    als ``hat_split`` stellt — *„steht der funktionsfremde Anteil überhaupt im
    Nenner?"*. Sie hängt an der **Stufe**, die {@link get_wp_strom_kwh} für
    diese Zeile gewählt hat, nicht am Kennzeichen ``getrennte_strommessung``.

    ⛔ **Der Unterschied ist gemessen und kostet 20 %** (N-462, 13.09.2026):
    Fällt die Zeile auf den Gesamtzähler zurück, steckt der Kühlstrom darin —
    wie im Nicht-getrennt-Zweig — und muss abgezogen werden. Am Kennzeichen
    festgemacht, zeigte dasselbe Gerät mit denselben Zählern **3,0 statt 3,75**,
    allein weil ein Schalter gesetzt war, der in dieser Lage nichts misst. Das
    ist die S1-Verletzung, gegen die E7 gebaut wurde, mit umgekehrtem Vorzeichen
    (Klasse N-450: *„denselben Layer zu rufen genügt nicht, es müssen dieselben
    EINGÄNGE sein"*).

    ⭐ **Seit WK-16d (14.09.2026) heißt „fein" seltener und genauer.** Ein
    zugeordneter Gesamtzähler ist jetzt die Menge (K1), auch neben einer
    vollständigen Aufteilung — der Nenner ist dann **nicht** mehr die feine
    Summe, und der funktionsfremde Anteil steckt in ihm und muss abgezogen
    werden. Die Antwort folgt weiterhin der Stufe und nur der Stufe; dass sie
    sich mit der Stufe mitverändert, ist genau der Punkt von N-450.
    """
    d = data or {}
    if not (params or {}).get("getrennte_strommessung"):
        # ⚠ **Der Monat hat für Geräte ohne Kennzeichen keine „fein"-Lage.**
        # {@link get_wp_strom_kwh} liest dort ausschließlich
        # ``stromverbrauch_kwh``/``strom_kwh``/``verbrauch_kwh`` — die feinen
        # Felder einer Monatszeile sind ohne Kennzeichen keine Summanden. Der
        # Nenner ist also nie die feine Summe. (Der **Tag** kennt den Rückfall
        # auf einen feinen Zähler auch ohne Kennzeichen, weil dort ein
        # *zugeordneter* feiner Zähler die einzige Messung sein kann — die zwei
        # Ebenen sind hier verschieden, und jede Antwort ist für ihre Ebene
        # exakt.)
        return False
    return wp_strom_aufteilung(d, params).stufe == "fein"

def get_wp_strom_kwh(data: dict, params: dict | None = None) -> float:
    """Wärmepumpen-Stromverbrauch in kWh — single source of truth.

    Bei `getrennte_strommessung=True` entscheidet die Vorrangkette aus
    {@link wp_strom_stufe}: ein belegter **Gesamtzähler ist die Menge** (K1),
    die feinen Achsen sind die Aufteilung darunter; misst er weniger als sie,
    tragen sie; ohne ihn tragen sie ohnehin. Ohne das Kennzeichen wird der
    Gesamt-Sensor genutzt
    (`stromverbrauch_kwh`/`strom_kwh`/`verbrauch_kwh`-Legacy-Fallbacks).
    Wer neben der Menge den **Rest** braucht, ruft
    {@link wp_strom_aufteilung} — diese Funktion ist deren ``menge_kwh``.

    ⛔ **Hier stand bis zum 13.09.2026: „das alte `stromverbrauch_kwh`-Feld wird
    ignoriert, auch wenn ein parallel laufender Sensor noch hineinschreibt."**
    Das war der Vorrang der **Absicht** vor der **Messung** und damit K3 verletzt
    (SOLL §3.2, W-1/W-1b): Wer den Schalter umlegte, verlor rückwirkend jede
    Monatszahl, für die er einen Gesamtzähler gepflegt hatte — in Cockpit
    Monat/Jahr, Komponenten-Hub, Kosten, CO₂, PDF, Community und den
    HA-Sensoren. Der Tagespfad hat diesen Vorrang am 26.08.2026 abgelegt
    (`komponenten_beitraege`), der Monatspfad erst jetzt; dazwischen lagen
    18 Tage, in denen Tag und Monat für dasselbe Gerät verschiedene Zahlen
    nannten (gemessen: Arbeitszahl 5,0 statt 3,0).

    ⛔ **Und bis zum 14.09.2026 stand daneben: „solange die feine Achse
    unvollständig ist."** Dieser Halbsatz war der Rest derselben Klasse. Bei
    *vollständiger* Achse wurde der Gesamtzähler verworfen — und mit ihm alles,
    was er **mehr** misst als die zwei Summanden (Standby, Steuerung,
    Umwälzpumpen: dietmar1968s „Systemverbrauch", 145 von 2193 kWh). Seit WK-16d
    gilt K1 ohne diesen Vorbehalt; der Rest heißt *nicht aufgeteilt*.
    **#183 bleibt ausgeschlossen, nur mit anderer Begründung:** Nicht die Wahl
    der Menge trennt die drei JAZ, sondern die Wahl des **Nenners** — und
    ``arbeitszahl_je_funktion`` nimmt für eine Funktions-Arbeitszahl
    ausschließlich den gemessenen Strom **dieser** Funktion (E7), nie diese
    Menge. Der Gesamtzähler kann deshalb neben zwei Funktionszahlen stehen,
    ohne dass eine dritte aus einer anderen Quelle entsteht.
    **`is not None`, nicht truthy:** ein Warmwasser-Strom von 0,0 im Sommer ist
    eine Messung, keine Leerstelle.
    ⚠ **Die Grenze:** Der Monat entscheidet an der **Zeile**, der Tag an der
    **Zuordnung**. Steht ein feiner Zähler zugeordnet, hat aber in einem Monat
    keinen Wert in der Zeile, fällt der Monat auf den Gesamtzähler und der Tag
    nicht — der Daten-Checker nennt genau diesen Monat (N-443).

    Hintergrund #183: Mit beiden Pfaden parallel driften die drei JAZ-Werte
    (Gesamt vs. Heizen vs. Warmwasser) gegeneinander, weil der Gesamt-JAZ
    aus der alten Quelle gerechnet wird, die getrennten JAZ aber aus den
    neuen Sensoren — Folge: Gesamt-JAZ kann mathematisch außerhalb der
    gewichteten Mitte der beiden Einzel-JAZ liegen.

    ⭐ **W-16 (2026-08-26): Der getrennte Zweig kannte nur zwei Funktionen.**
    ``strom_heizen_kwh + strom_warmwasser_kwh`` war der ganze Verbrauch,
    solange eine Wärmepumpe nur heizen und Warmwasser machen konnte. Seit
    **R1/W-2** ist ein **Kühlzähler an jeder Bauart** zuordenbar — und sein
    Strom stand in **keinem** der beiden Felder. Folge an einer nachgestellten
    Anlage gemessen (MartyBrs Bauform, T89667 #200): **950 statt 1050 kWh**,
    also 100 kWh, die in Kosten, CO₂ und Verbrauchsseite fehlten.

    ⭐ **Und die zweite Folge, W-16b:** Weil der Nenner den Kühlstrom nie
    enthielt, zog ``arbeitszahl(...)`` ihn über ``strom_funktionsfremd_kwh``
    ein **zweites** Mal ab — 3600 ÷ 850 statt 3600 ÷ 950, die Anlage sah 12 %
    besser aus, als sie ist. Mit der Ergänzung hier wird jener Abzug wieder
    richtig, **ohne dass ein Aufrufer sich ändert**.

    ⚠ **Nur der GEMESSENE Split wird addiert, und das ist der Kern.** Ein
    **abgeleiteter** Split (aus dem Stunden-Signal) verteilt den *vorhandenen*
    Gesamtstrom auf Betriebsarten — sein Kühlanteil ist bereits Teil der
    **Summe** ``strom_heizen_kwh + strom_warmwasser_kwh``. Ihn zu addieren wäre
    genau die Doppelzählung, die W-16b beseitigt, nur andersherum.
    ``ModusStromZeile.gemessen`` trennt die beiden Fälle; ``funktionsfremd_kwh``
    ist die **eine Stelle**, die sagt, welche Betriebsarten keine bewertete
    Nutzenergie haben (Kühlen · Lüften · Entfeuchten, **E4**) — sie hier
    aufzuzählen wäre die Bauform, an der W-14 entstanden ist.

    ⛔ **Hier stand bis zum 12.09.2026 „Teil von ``strom_heizen_kwh``", und die
    Begründung war eine Aussage über die Physik.** Beides war zu eng bzw.
    falsch begründet. Der tragende Grund ist **arithmetisch**: Der abgeleitete
    Split wird auf **die Menge dieses Geräts** normiert — tagesweise auf
    ``TagesZusammenfassung.komponenten_kwh[waermepumpe_<id>]``
    (``modus_split.py``), monatsweise auf genau diese Funktion
    (``energie_profil/modus_split_schreiben.py``). Sein Kühlanteil ist damit per
    Konstruktion ein **Ausschnitt aus der Menge**, unabhängig davon, was der
    Zähler physisch misst. *(Bis zum 14.09.2026 stand hier statt „die Menge"
    der engere Satz „genau ``strom_heizen_kwh + strom_warmwasser_kwh``, weil die
    Beitragsschicht beide Felder in EINEN Ziel-Key addiert". Seit WK-16d trägt
    derselbe Ziel-Key den Gesamtzähler, sobald einer zugeordnet ist — die
    Begründung gilt unverändert, nur ist sie jetzt an der Menge festgemacht
    statt an einer ihrer möglichen Herkünfte.)*

    ⛔ **In welchem der zwei Felder er sitzt, ist nicht gespeichert.** Der Monat
    hält nur ``modus_strom_<modus>_kwh`` je Betriebsart, ohne Zuordnung zu einer
    der beiden Summanden-Achsen. Deshalb gibt es **keine** Korrektur je Funktion
    (SOLL-§9-**E7**: der Nenner einer Funktions-Arbeitszahl ist der *gemessene*
    Strom dieser Funktion) — und deshalb kürzt ein abgeleiteter Anteil auch die
    **Gesamt**-Arbeitszahl nicht (*Ergänzung zu E7*, Option A; die Regel steht
    in ``berechnungen/betriebsart_gemessen.funktionsfremd_abzug_kwh``).

    ⚠ **Im Nicht-getrennt-Zweig wird NICHTS addiert:** ``stromverbrauch_kwh``
    ist der Zählerstand des ganzen Geräts und enthält den Kühlbetrieb bereits.
    """
    return wp_strom_aufteilung(data, params).menge_kwh
