"""Der Cockpit-Block *Wärme/Klima* — was er **zeigt** und was er **einmal sagt**.

**D-Sicht** (Konzept Wärme/Klima §6, Entscheid Gernot 14.09.2026): Der Block
zeigt Kacheln und Zeilen **nur mit Zahl**. Was die Ausstattung nicht hergibt,
steht **einmal je Sicht** im Kasten *„Was noch möglich wäre"* — mit dem
Handgriff daneben, nicht als sechs Kacheln mit „—".

## Der Anlass, in einem Satz

*„Das release ich so nicht."* (Gernot, 14.09.2026) — Cockpit → Monat zeigte im
Block **vier** Striche mit Grund-Texten, während dietmar1968s selbstgebautes
Dashboard auf **derselben Datenlage** überall Zahlen zeigt und „–" nur dort, wo
wirklich nichts ist. Gemessen stimmte beides; der Unterschied war die Form.

## Zwei Bauteile, und beide entstehen genau einmal

* {@link geraete_zeilen} — die Tabelle *„Zahlen je Gerät"*. Sie liest die
  Kennzahlen aus ``services/waermepumpe_kennzahlen_je_geraet.py``, also aus
  **derselben** Stelle wie der Komponenten-Hub. Der Hub-Link bleibt daneben; er
  führt jetzt zu *mehr* (Verlauf, Saison, Wirtschaftlichkeit) statt zu dem, was
  hier fehlte.
* {@link was_noch_moeglich} — der Kasten. Er fragt für jeden Grund die
  **Klasse** ({@link grund_klasse}): *Ausstattung* ⇒ Kasten mit Handgriff ·
  *Zeitraum* ⇒ „—" ohne Text an der Kachel. Die Klassifizierung steht an der
  Grund-Konstante im Layer, nicht hier und erst recht nicht im Client — sonst
  stünde dieselbe Aussage an zwei Orten (die W-3-Klasse).

## Dazu drei Faltungen „anlagenweit aus den Geräte-Mengen"

{@link achsen_der_anlage} · {@link schranken_eingang} ·
{@link funktions_eingaenge_der_anlage}. Sie beantworten *„was gilt für die
Anlage?"* aus dem, **was je Gerät schon aufgelöst ist** — Konzept Wärme/Klima
§7: *„Addiert wird, was je Gerät schon aufgelöst ist"*, nie die Auflösung der
Anlagensumme. D1 und K3 sind zu diesem Zeitpunkt längst je Gerät gefallen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AbstractSet, Iterable, Optional, Sequence

from pydantic import BaseModel, Field

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_BAUARTEN_GEMISCHT,
    GRUND_FREMDSTROM,
    GRUND_FREMDWAERME,
    GRUND_GERAETE_OHNE_WAERME,
    GRUND_GERAETE_VERSCHIEDEN,
    GRUND_FUNKTION_NICHT_DECKUNGSGLEICH,
    GRUND_KEIN_STROM,
    GRUND_ZEITRAUM,
    HANDGRIFF_JE_GRUND,
    deckung_aus_geraeten,
    ist_ausstattungs_grund,
)
from backend.core.betriebsmodus import HEIZEN, WAERME_ACHSEN, WARMWASSER
from backend.core.tageswert_grund import (
    GRUND_KEINE_ZAEHLERSTAENDE,
    GRUND_ZAEHLER_RUECKSPRUNG,
    TAGESWERT_GRUND_KURZ,
)
from backend.services.waermepumpe_kennzahlen_je_geraet import (
    GeraetKennzahlen, GeraetMengen,
)

#: Wohin der Handgriff führt. **Drei Ziele, nicht mehr** — jeder Grund gehört zu
#: genau einer Fläche:
#:
#: * *Datenquellen* — ein Zähler fehlt oder ein Kennzeichen ist nicht gesetzt.
#: * *Daten* (Daten-Checker · Reparatur-Werkbank) — die Messung ist da, aber
#:   lückenhaft. ⭐ **Der Daten-Checker bleibt der Ort für Reparatur-Hinweise**
#:   (D-Sicht); der Kasten verweist dorthin, statt sie zu wiederholen.
#: * *Komponenten-Hub* — die Zahl gibt es, nur nicht anlagenweit.
#:
#: ⚠ Ein Grund ohne Eintrag bekommt **keinen** Link. Ein Link, der auf eine
#: Sicht führt, die dasselbe sagt, ist schlechter als keiner — dieselbe Regel
#: wie bei ``GRUENDE_HUB_HILFT``.
LINK_DATENQUELLEN = "#/einstellungen/datenquellen"
LINK_DATEN = "#/einstellungen/daten"
LINK_HUB = "#/komponenten/waermepumpe"

LINK_JE_GRUND: dict[str, str] = {
    GRUND_BAUARTEN_GEMISCHT: LINK_HUB,
    GRUND_GERAETE_OHNE_WAERME: LINK_HUB,
    GRUND_GERAETE_VERSCHIEDEN: LINK_HUB,
    GRUND_FUNKTION_NICHT_DECKUNGSGLEICH: LINK_DATENQUELLEN,
    GRUND_FREMDSTROM: LINK_DATENQUELLEN,
    GRUND_FREMDWAERME: LINK_DATENQUELLEN,
    GRUND_KEIN_STROM: LINK_DATENQUELLEN,
    GRUND_ZEITRAUM: LINK_DATEN,
    TAGESWERT_GRUND_KURZ[GRUND_KEINE_ZAEHLERSTAENDE]: LINK_DATEN,
    TAGESWERT_GRUND_KURZ[GRUND_ZAEHLER_RUECKSPRUNG]: LINK_DATEN,
}


def _link(grund: str) -> Optional[str]:
    """Das Ziel des Handgriffs — Default *Datenquellen*, wo einer existiert.

    ⚠ **Kein Link ohne Handgriff.** Ein Grund, für den es nichts zu tun gibt
    (*„… aus verschiedenen Monaten"* hat einen Handgriff, *„Nutzenergie und
    Strom … aus verschiedenen Monaten"* ebenfalls), bekommt keine Schaltfläche,
    die ins Leere führt.
    """
    if grund in LINK_JE_GRUND:
        return LINK_JE_GRUND[grund]
    return LINK_DATENQUELLEN if grund in HANDGRIFF_JE_GRUND else None


class WpGeraetZeile(BaseModel):
    """Eine Zeile der Tabelle *„Zahlen je Gerät"* im Block.

    ⛔ **Der Client rechnet hier nichts** (ADR-002/**P12**, ``check:cop-roh``):
    Jede Arbeitszahl steht fertig mit ihrem Grund daneben; „—" entsteht aus
    ``None``, nicht aus einer Division im Browser.
    """

    investition_id: int
    name: str
    strom_kwh: Optional[float] = None
    waerme_kwh: Optional[float] = None
    #: Warum die Wärme-Zelle leer ist — **R-4**, damit auch sie keinen Strich
    #: ohne Grund trägt.
    #:
    #: ⛔ **Nicht neu klassifiziert, sondern abgeleitet:** Steht Strom, aber
    #: keine Wärme, dann sperrt ``arbeitszahl`` genau an ``q <= 0``, und ihr
    #: Grund IST die Aussage über die fehlende Wärme (*„kein Wärmemengenzähler
    #: zugeordnet"*, im Tag auch die W-18-Form). Ihn hier zu wiederholen wäre
    #: ein zweiter Wortlaut; ihn aus dem Text zu erraten wäre die W-3-Klasse.
    #: Die Bedingung ist deshalb **strukturell** — die Sperrreihenfolge von
    #: ``arbeitszahl`` steht in ihrem Docstring.
    waerme_grund: Optional[str] = None
    jaz: Optional[float] = None
    jaz_grund: Optional[str] = None
    jaz_heizen: Optional[float] = None
    jaz_heizen_grund: Optional[str] = None
    jaz_warmwasser: Optional[float] = None
    jaz_warmwasser_grund: Optional[str] = None
    jaz_kuehlen: Optional[float] = None
    jaz_kuehlen_grund: Optional[str] = None
    #: Die **Wärme-Achsen** dieses Geräts (WK-16h/**R-1**) — Namen aus dem
    #: Kanon (``heizen`` · ``warmwasser``).
    #:
    #: ⭐ **Wozu die Anzeige sie braucht.** Eine Zelle ohne Zahl hat zwei ganz
    #: verschiedene Bedeutungen: *„die Zahl fehlt"* (Strich mit dem Grund als
    #: Tooltip) und *„danach ist hier nicht zu fragen"* (**leer**). Beide sind
    #: ``None`` — das Feld hier trennt sie. Aus dem Grund allein ginge es
    #: nicht: Eine nicht geltende Achse hat gar keinen.
    #:
    #: ⚠ **Der Default ist „beide", nicht die leere Liste** — und eine leere
    #: Liste gilt beim Lesen wie „beide" (Backend wie Client). Fail-open wie in
    #: der Registry: Eine Zeile, die das Feld nicht trägt, soll keine Spalte
    #: verschwinden lassen; die Gegenrichtung — eine gemessene Zahl still
    #: ausblenden — wäre der teurere Fehler.
    achsen: list[str] = Field(default_factory=lambda: sorted(WAERME_ACHSEN))


#: Die Namen der Größen, die im Kasten stehen können. **Sie sind Bezeichner,
#: keine Sätze** — der Client fragt mit ihnen ab, ob eine Kachel in den Kasten
#: gewandert ist, statt Grund-**Texte** zu vergleichen.
#:
#: ⭐ **Warum nicht über den Grund-Text** (gemessen 14.09.2026): Die Tages-Route
#: reicht an derselben Kachel die **Kurzform** des W-18-Grundes herein, während
#: unter der Wärme-Kachel die **Langform** steht. Ein Text-Vergleich im Client
#: hätte dort nie getroffen — und zwar still. Ein Name ist ein Schlüssel, ein
#: Satz ist eine Formulierung.
GROESSE_ARBEITSZAHL = "Arbeitszahl"
GROESSE_ARBEITSZAHL_HEIZEN = "Arbeitszahl Heizen"
GROESSE_ARBEITSZAHL_WARMWASSER = "Arbeitszahl Warmwasser"
GROESSE_ARBEITSZAHL_KUEHLEN = "Arbeitszahl Kühlen"
GROESSE_WAERME = "Wärme erzeugt"

#: Der Wortschatz als Menge — der Client-Spiegel wird daran geprüft.
GROESSEN_IM_KASTEN: frozenset[str] = frozenset({
    GROESSE_ARBEITSZAHL,
    GROESSE_ARBEITSZAHL_HEIZEN,
    GROESSE_ARBEITSZAHL_WARMWASSER,
    GROESSE_ARBEITSZAHL_KUEHLEN,
    GROESSE_WAERME,
})


class WpMoeglichZeile(BaseModel):
    """Eine Zeile des Kastens *„Was noch möglich wäre"*.

    Eine Zeile **je Grund**, nicht je Kachel: Derselbe fehlende Zähler sperrt
    regelmäßig zwei Kennzahlen, und zweimal denselben Satz zu lesen ist genau
    die Wiederholung, die der Kasten abschaffen soll.
    """

    #: Die betroffenen Größen als **Bezeichner** — womit der Client abfragt.
    groessen: list[str]
    #: Dieselben Größen als **Anzeigetext** („A · B"). Die Trennung ist
    #: Absicht: Wer eine Beschriftung ändert, soll keine Abfrage brechen.
    groesse: str
    grund: str
    handgriff: Optional[str] = None
    link: Optional[str] = None


def _r(wert: Optional[float], stellen: int = 2) -> Optional[float]:
    return round(wert, stellen) if wert is not None else None


def geraete_zeilen(
    kennzahlen: Sequence[GeraetKennzahlen],
) -> list[WpGeraetZeile]:
    """Die Tabelle *„Zahlen je Gerät"* — aus der einen Rechenstelle.

    ⚠ **Geräte ohne jede Menge fallen heraus.** Ein im Zeitraum stillstehendes
    (oder stillgelegtes) Gerät als Zeile aus Strichen zu zeigen wäre genau die
    Strich-Flut, gegen die die D-Sicht gebaut ist. Ein Gerät mit Strom **oder**
    Wärme bleibt — auch wenn seine Arbeitszahl gesperrt ist: Dann trägt die
    Zeile die Mengen und den Grund, und das ist eine Auskunft.
    """
    zeilen: list[WpGeraetZeile] = []
    for k in kennzahlen:
        m = k.mengen
        # E4d (Bauplan §8a, Rest N-585): ein Gerät, dessen Strom UND Wärme gemessen 0 sind, bleibt als Zeile stehen —
        # „kein Betrieb im Zeitraum" ist eine Auskunft mit Mengen 0 (und dem Zeitraum-Grund „—" ohne Text), kein
        # stillstehendes Gerät ohne Messung.
        if m.strom_kwh <= 0 and m.waerme_kwh <= 0 and not getattr(m, "kein_betrieb", False):
            continue
        zeilen.append(WpGeraetZeile(
            investition_id=m.inv_id,
            name=m.name,
            strom_kwh=_r(m.strom_kwh, 1),
            # P4: eine fehlende Wärme ist keine 0 — sie ist keine Zahl. Eine GEMESSENE 0 schon (E4d).
            waerme_kwh=(
                _r(m.waerme_kwh, 1) if m.waerme_kwh > 0 or getattr(m, "kein_betrieb", False) else None
            ),
            waerme_grund=(
                k.gesamt.grund
                if (m.waerme_kwh <= 0 and m.strom_kwh > 0) else None
            ),
            jaz=_r(k.gesamt.wert),
            jaz_grund=k.gesamt.grund,
            jaz_heizen=_r(k.je_funktion.heizen.wert),
            jaz_heizen_grund=k.je_funktion.heizen.grund,
            jaz_warmwasser=_r(k.je_funktion.warmwasser.wert),
            jaz_warmwasser_grund=k.je_funktion.warmwasser.grund,
            jaz_kuehlen=_r(k.kuehlen.wert),
            jaz_kuehlen_grund=k.kuehlen.grund,
            # Sortiert, damit die Antwort stabil ist (ein `frozenset` hat keine
            # Reihenfolge, und die Antwort wird verglichen).
            achsen=sorted(m.waerme_achsen),
        ))
    return zeilen


def achsen_der_anlage(
    kennzahlen: Sequence[GeraetKennzahlen],
) -> frozenset[str]:
    """Welche Wärme-Achsen gibt es **anlagenweit**? (WK-16h/**R-2**)

    Die Vereinigung über die Geräte, die im Zeitraum **beitragen**. Eine
    anlagenweite Funktions-Arbeitszahl gibt es nur für eine Achse, die
    mindestens eines dieser Geräte hat; für die andere steht weder Zahl noch
    Grund noch eine Zeile im Kasten.

    ⭐ **Der Anlass, gemessen an der Demo-Anlage der r28 am 15.06.2026** (N-499):
    An diesem Tag trägt allein die **Split-Klimaanlage** Strom bei. Im Kasten
    stand *„Arbeitszahl Heizen · Arbeitszahl Warmwasser — Strom nicht getrennt
    je Funktion gemessen → Getrennte Strommessung einschalten und beide Zähler
    zuordnen"* — ein Handgriff, der an einem Gerät ohne Warmwasserkreis ins
    Leere führt, für eine Achse, die es an der ganzen beitragenden Ausstattung
    nicht gibt.

    ⚠ **Beitrag statt Bestand**, dieselbe Regel wie in {@link schranken_eingang}
    und in ``deckung_aus_geraeten`` (N-441): Ein Gerät ohne Strom in diesem
    Zeitraum öffnet keine Achse — es steht in keinem Nenner.

    ⛔ **Trägt kein Gerät bei, gelten die Achsen aller übergebenen Geräte**, und
    zur Not beide. Eine leere Menge hieße *„es gibt hier keine Funktion"* — das
    ist eine Aussage über die Ausstattung, und eine leere Liste ist keine
    Messung (ADR-002/**P4**).
    """
    beitragend = [k.mengen for k in kennzahlen if k.mengen.strom_kwh > 0]
    quelle = beitragend or [k.mengen for k in kennzahlen]
    if not quelle:
        return WAERME_ACHSEN
    return frozenset().union(*(m.waerme_achsen for m in quelle))


#: Welche Größe zu welcher Spalte der Tabelle *„Zahlen je Gerät"* gehört — und
#: welche Achse sie voraussetzt. ``None`` heißt: keine Wärme-Achse nötig.
_GERAET_GROESSEN: tuple[tuple[str, str, str, Optional[str]], ...] = (
    (GROESSE_ARBEITSZAHL, "jaz", "jaz_grund", None),
    (GROESSE_ARBEITSZAHL_HEIZEN, "jaz_heizen", "jaz_heizen_grund", HEIZEN),
    (GROESSE_ARBEITSZAHL_WARMWASSER, "jaz_warmwasser", "jaz_warmwasser_grund",
     WARMWASSER),
    (GROESSE_ARBEITSZAHL_KUEHLEN, "jaz_kuehlen", "jaz_kuehlen_grund", None),
)


def was_noch_moeglich(
    gruende: Iterable[tuple[str, Optional[str]]],
    geraete: Sequence[WpGeraetZeile] = (),
) -> list[WpMoeglichZeile]:
    """Der Kasten — **jeder Ausstattungs-Grund genau einmal**.

    Args:
        gruende: Paare ``(Größen-Name, Grund)`` der **anlagenweiten** Zahlen.
            Ein Grund, der die Klasse *Zeitraum* trägt, erscheint **nicht** —
            dort steht an der Kachel ein „—" ohne Text, und der Kasten bliebe
            sonst im Juni voll mit Sätzen, zu denen es nichts zu tun gibt.
        geraete: die Zeilen der Tabelle *„Zahlen je Gerät"*. Ihre
            **Ausstattungs**-Gründe kommen mit in den Kasten, mit dem
            Gerätenamen davor (*„Bosch Climate 5000 Multisplit: kein
            Wärmemengenzähler zugeordnet"*).

    ⭐ **Warum die Geräte-Gründe dazugehören** (WK-16h/**R-4**, N-502). Bis zum
    15.09.2026 trug der Kasten nur die anlagenweiten Zahlen. Gemessen an der
    Demo-Anlage der r28: *Cockpit → Monat Juni* zeigte die Bosch-Zeile mit
    74,2 kWh Strom und **vier** Strichen, und nirgends im Block stand, dass ihr
    der Wärmemengenzähler fehlt — der einzige Hinweis war der Schranken-Satz an
    der Kachel darüber, und der erklärt das „≥", nicht den Strich.

    ⛔ **Dedupliziert gegen die anlagenweiten Zeilen**, und zwar am **rohen**
    Grund: Sagt die Anlage schon *„kein Kältemengenzähler zugeordnet"*, ist
    *„Bosch …: kein Kältemengenzähler zugeordnet"* daneben keine zweite
    Auskunft, sondern dieselbe zweimal — genau die Wiederholung, gegen die der
    Kasten gebaut ist.

    ⚠ **Eine nicht geltende Achse bringt nichts mit** — sie hat keinen Grund
    (``ARBEITSZAHL_GILT_NICHT``), und ``achsen`` hält die Frage zusätzlich
    zurück: Ein Gerät ohne Warmwasserkreis soll im Kasten nicht unter
    *Arbeitszahl Warmwasser* auftauchen, auch nicht, wenn dort eines Tages ein
    Grund stünde.

    ⭐ **Die Reihenfolge ist die der Aufrufer-Liste**, nicht alphabetisch: Die
    Gesamtzahl steht oben, die Funktionen darunter, die Geräte dahinter —
    dieselbe Reihenfolge, in der der Anwender sie im Block gesucht hat.
    """
    reihenfolge: list[str] = []
    groessen: dict[str, list[str]] = {}
    roh_je_zeile: dict[str, str] = {}
    generisch: set[str] = set()

    def _nimm(groesse: str, grund: Optional[str], praefix: str = "") -> bool:
        """Legt die Zeile an (oder erweitert sie) — ``False``, wenn sie nicht in
        den Kasten gehört (Zeitraum-Grund). **Der Rückgabewert trägt R-5:** eine
        Größe gilt nur dann als *von einer Geräte-Zeile erklärt*, wenn wirklich
        eine entstanden ist. Ohne ihn verschwand die anlagenweite Zeile
        *„Arbeitszahl Kühlen — kein Kältemengenzähler zugeordnet"*, weil ein
        Gerät daneben einen **Zeitraum**-Grund trug (*„kein Kühlbetrieb"*), den
        der Kasten gar nicht führt (gemessen r28/Demo, Juni 2026)."""
        if not grund or not ist_ausstattungs_grund(grund):
            return False
        zeile = f"{praefix}{grund}" if praefix else grund
        if zeile not in groessen:
            groessen[zeile] = []
            roh_je_zeile[zeile] = grund
            reihenfolge.append(zeile)
            if not praefix:
                generisch.add(zeile)
        if groesse not in groessen[zeile]:
            groessen[zeile].append(groesse)
        return True

    for groesse, grund in gruende:
        _nimm(groesse, grund)
    anlagenweit = set(roh_je_zeile.values())
    mit_geraete_zeile: set[str] = set()
    for g in geraete:
        for groesse, wert_feld, grund_feld, achse in _GERAET_GROESSEN:
            if achse is not None and achse not in (g.achsen or WAERME_ACHSEN):
                continue
            if getattr(g, wert_feld) is not None:
                continue
            grund = getattr(g, grund_feld)
            if not grund or grund in anlagenweit:
                continue
            if _nimm(groesse, grund, praefix=f"{g.name}: "):
                mit_geraete_zeile.add(groesse)

    # ── R-5 (WK-16j): keine generische Zeile neben einer Geräte-Zeile ──────
    #
    # **Für eine Größe steht genau EINE Auskunft im Kasten, und es ist die
    # konkretere.** Nennt eine Geräte-Zeile das Gerät und den Handgriff, ist die
    # anlagenweite Zeile daneben dieselbe Auskunft ohne Adresse — und ihr
    # Handgriff kann sogar in die Irre führen. Gemessen an der Prüfstand-Anlage
    # der r28 (September 2026, *Cockpit → Monat*):
    #
    #   *„Arbeitszahl Heizen · Arbeitszahl Warmwasser — Nutzenergie und Strom
    #   dieser Funktion stammen von verschiedenen Geräten → Getrennte
    #   Strommessung am zweiten Gerät einschalten und zuordnen, wenn es sie gibt"*
    #   *„Arbeitszahl Heizen · Arbeitszahl Warmwasser — Vaillant aroTHERM plus:
    #   Wärme nicht je Funktion gemessen → Einen zweiten Wärmemengenzähler setzen …"*
    #
    # Zwei Zeilen für dieselben zwei Größen; die erste zeigte auf die
    # Brauchwasser-WP, die **keine zweite Funktion hat**, während die zweite das
    # Gerät nennt, an dem es wirklich etwas zu tun gibt.
    #
    # ⛔ **Die Gegenrichtung bleibt, wie sie ist** (``anlagenweit`` oben): Trägt
    # die Geräte-Zeile **denselben** Grund, verschwindet sie — dann sagt die
    # anlagenweite Zeile bereits dasselbe, und der Gerätename brächte keine
    # neue Auskunft. Die Regel greift also genau dort, wo die beiden Sätze
    # **verschieden** sind.
    #
    # ⚠ **Die Größe bleibt im Kasten**, nur in der anderen Zeile — der Client
    # fragt über den Größen-**Namen** (``imKasten``), nicht über den Text; keine
    # Kachel kommt dadurch zurück.
    for zeile in list(reihenfolge):
        if zeile not in generisch:
            continue
        rest = [g for g in groessen[zeile] if g not in mit_geraete_zeile]
        if rest:
            groessen[zeile] = rest
        else:
            reihenfolge.remove(zeile)

    return [
        WpMoeglichZeile(
            groessen=list(groessen[z]),
            groesse=" · ".join(groessen[z]),
            grund=z,
            handgriff=HANDGRIFF_JE_GRUND.get(roh_je_zeile[z]),
            link=_link(roh_je_zeile[z]),
        )
        for z in reihenfolge
    ]


def schranken_eingang(
    kennzahlen: Sequence[GeraetKennzahlen],
) -> tuple[float, list[str]]:
    """Wieviel Strom steht im Nenner **ohne** gemessene Wärme — und von wem?

    Der Eingang der Schranke (**E1b**). ``(0.0, [])`` heißt: Jedes Gerät, das
    Strom beisteuert, steuert auch gemessene Wärme bei — dann ist die
    anlagenweite Zahl die gewohnte Arbeitszahl und trägt kein „≥".

    ⚠ **Gezählt wird der BEITRAG, nicht der Bestand** — ein Gerät ohne Strom in
    diesem Zeitraum macht keine Schranke auf. Dieselbe Regel wie in
    ``deckung_aus_geraeten`` (N-441).
    """
    menge = 0.0
    namen: list[str] = []
    for k in kennzahlen:
        m = k.mengen
        if m.strom_kwh <= 0 or m.hat_waermemessung:
            continue
        menge += m.strom_kwh
        if m.name and m.name not in namen:
            namen.append(m.name)
    return menge, namen


def traegt_menge(mengen: Optional[object]) -> bool:
    """Trägt diese Zeile überhaupt eine Menge? — **die S5-Weiche** (WK-16i).

    Die eine Frage hinter *„die Monatszeile gewinnt, wo sie eine Zahl trägt"*,
    und sie wird **zweimal in derselben Sicht** gestellt: je Gerät (ersetzt der
    Rückfall diese Tabellenzeile?) und anlagenweit (kommen die Eingänge der
    Funktions-Arbeitszahl aus der Zeile oder aus den Geräte-Mengen?). Zwei
    Schreibweisen wären die F-56-Klasse — eine Regel, zwei Stellen, eine Drift.

    ⚠ **Strom ODER Wärme, nichts Feineres.** Beide Größen sind je Gerät bereits
    kanonisch aufgelöst (K3 und D1); trägt eine Zeile eine Funktions-Achse, so
    trägt sie zwangsläufig auch die Summe darüber (``get_wp_strom_kwh`` addiert
    die feine Aufteilung, ``waerme_gesamt_kwh`` die Summanden). Eine Zeile ohne
    beides trägt nichts — und **nicht** „eine gemessene 0": Die gibt es hier
    nicht, weil ohne Zeile gar nicht erst addiert wird.

    Args:
        mengen: ``WpFakten`` oder ``GeraetMengen`` — beide tragen ``strom_kwh``
            und ``waerme_kwh`` unter demselben Namen für dieselbe Größe.
    """
    return mengen is not None and (
        getattr(mengen, "strom_kwh", 0.0) > 0 or getattr(mengen, "waerme_kwh", 0.0) > 0
    )


@dataclass(frozen=True)
class FunktionsEingaengeDerAnlage:
    """Die **anlagenweiten** Eingänge der Funktions-Arbeitszahl (WK-16i, N-503).

    ⭐ **Die Feldnamen sind die von** {@link
    backend.services.monats_fakten.WpFakten}, **und das ist Absicht.** Dieselbe
    Frage hat zwei Herkünfte — die Monatszeile und die Geräte-Mengen —, und der
    Aufrufer soll dafür **einen** Codeweg haben, nicht zwei. Genau die Bauform,
    mit der {@link backend.services.waermepumpe_kennzahlen_je_geraet.GeraetMengen}
    ihre zwei Herkünfte trägt: *„Die Felder tragen die Namen der Größen, nicht
    die der Datenbankspalten."*

    ⚠ **Sie ist kein Ersatz für die Monatszeile, sondern ihr Rückfall** (S5).
    Trägt die Zeile eine Menge, gilt sie; diese Faltung entsteht nur, wo sie
    nichts trägt — im laufenden Monat also immer, denn einen automatischen
    Monatsabschluss gibt es nicht.
    """

    heizung_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    strom_heizen_kwh: float = 0.0
    strom_warmwasser_kwh: float = 0.0
    #: Mindestens **ein beitragendes** Gerät führt ``getrennte_strommessung``
    #: — dieselbe ``any``-Semantik wie ``WpFakten.hat_split`` und wie der Tag
    #: (``views.py::_wp_getrennte_strommessung_tag``). ⚠ *Beitragend* heißt hier
    #: **mit Strom**: Das Kennzeichen ist eine Aussage über die Messung dieses
    #: Zeitraums, die Mengen darüber sind es nicht (WK-16j).
    hat_split: bool = False
    #: **N-479 — hier bewusst immer ``False``, und das ist eine Grenze, keine
    #: Lücke.** Das Gegenstück ``WpFakten`` beantwortet die Frage „ist diese
    #: Funktion GEMESSEN (auch wenn 0 herauskam)?" aus der Monatszeile, die den
    #: Zählerstand selbst trägt. Dieser Zwilling springt genau dann ein, wenn es
    #: **keine** Monatszeile gibt — er kennt nur Geräte-Kennzahlen und kann eine
    #: gemessene Null nicht von einer fehlenden Messung trennen. Eine Näherung
    #: über „das Gerät hat die Achse" wäre eine zweite, schwächere Regel neben
    #: der echten; dann lieber kein Zeitraum-Grund als ein falscher. Dieser Pfad
    #: verhält sich damit unverändert wie vor N-479.
    heizung_gemessen: bool = False
    warmwasser_gemessen: bool = False
    strom_heizen_gemessen: bool = False
    strom_warmwasser_gemessen: bool = False
    #: Mindestens ein beitragendes Gerät misst seine Wärme mit EINEM
    #: gemeinsamen Zähler (N-391). Ohne das Feld sagte die leere Funktions-Zeile
    #: *„kein Wärmemengenzähler zugeordnet"* an einer Anlage, deren Zähler
    #: zugeordnet **ist** — die W-18-Klasse.
    waerme_ist_gesamt: bool = False
    #: Welche Geräte stehen im **Zähler** bzw. im **Nenner** je Funktion — die
    #: Identitäten, nicht ihre Anzahl (N-441). Namen wie in ``WpFakten``.
    geraete_q_heizen: frozenset[int] = field(default_factory=frozenset)
    geraete_e_heizen: frozenset[int] = field(default_factory=frozenset)
    geraete_q_warmwasser: frozenset[int] = field(default_factory=frozenset)
    geraete_e_warmwasser: frozenset[int] = field(default_factory=frozenset)

    def deckung_je_funktion(self, funktion: str) -> Optional[bool]:
        """Deckt sich der Geräte-Kreis von Zähler und Nenner? — wie ``WpFakten``.

        Dieselbe Layer-Regel ({@link
        backend.core.berechnungen.waermepumpe_kennzahl.deckung_aus_geraeten}),
        nur auf den Geräte-Mengen statt auf den Monatszeilen. **Ohne sie wäre
        der Rückfall eine neue Falschaussage:** An der nachgestellten
        Prüfstand-Anlage steuert ein Gerät Heiz- und Warmwasser-**Strom** bei
        und misst seine Wärme mit einem Gesamtzähler, ein anderes steuert
        Warmwasser-**Wärme** ohne eigenen Funktions-Strom bei. Die Quotienten
        daraus (3,35 / 4,21) stehen für keine Anlage — und derselbe Monat nach
        dem Abschluss sperrt sie mit genau diesem Grund (gemessen an r28,
        Juli und August 2026: *„Nutzenergie und Strom dieser Funktion stammen
        von verschiedenen Geräten"*). Konzept Wärme/Klima §7.

        ⛔ **``kuehlen`` beantwortet diese Faltung NICHT** (``None`` — *die
        Frage stellt sich nicht*). Sie liefert die Eingänge, deren **Mengen**
        sie auch liefert; die anlagenweite Kälte und der Kühlstrom kommen im
        laufenden Monat weiterhin aus der Monatszeile. Eine Deckungs-Aussage
        aus einer anderen Quelle als die Mengen wäre genau die Mischung, gegen
        die R2 steht. ⚠ In der Rückfall-Lage sagt die Monatszeile dazu
        ebenfalls ``None`` — sie trägt dort keine Kälte —, die Auskunft ist
        also dieselbe, nicht nur eine Vereinfachung.
        """
        if funktion == "heizen":
            return deckung_aus_geraeten(self.geraete_e_heizen, self.geraete_q_heizen)
        if funktion == "warmwasser":
            return deckung_aus_geraeten(
                self.geraete_e_warmwasser, self.geraete_q_warmwasser,
            )
        return None


def _mengen_der_achse(
    m: GeraetMengen, achse: str, achsen: AbstractSet[str],
) -> tuple[float, float]:
    """Welche **Mengen** steuert dieses Gerät zu ``achse`` bei? (**WK-16j/R-4**)

    Die **Mengen-Seite** der Ein-Achsen-Regel, die WK-16h/**R-1** für die
    **Kennzahl** gezogen hat (``waermepumpe_kennzahl.arbeitszahl_je_funktion``,
    Argument ``gesamt``): *Hat eine Einheit genau EINE Wärme-Achse, ist die
    Funktions-Arbeitszahl dieser Achse die Gesamt-Arbeitszahl* — Strom und Wärme
    sind per Bauart dieser Funktion zugeordnet, ein getrennter Zähler könnte
    nichts anderes messen (Konzept Wärme/Klima [5.1a]).

    ⛔ **Sie muss anlagenweit GLEICH gelten, sonst widerspricht der Block sich
    selbst.** Gemessen an der Prüfstand-Anlage der r28 (September 2026): Die
    Brauchwasser-WP *Stiebel WWK 300* steuerte ihre 60,8 kWh Warmwasser-**Wärme**
    bei, ihre 18,4 kWh Strom aber **nicht** — sie stehen unter
    ``stromverbrauch_kwh``, nicht unter ``strom_warmwasser_kwh``. Die Deckung
    Warmwasser fiel damit auch an einer Anlage, an der es nichts zu beanstanden
    gibt, und im Kasten stand ein generischer Handgriff (*„Getrennte
    Strommessung am zweiten Gerät einschalten"*) für ein Gerät **ohne zweite
    Funktion**. Die Tabelle daneben zeigte für dasselbe Gerät **3,31**.

    ⚠ **Sie ersetzt nur einen Grund, nie eine Zahl** — dieselbe Schranke wie im
    Layer: Wo die feinen Zähler **beide** Seiten hergeben, bleiben sie stehen.
    Sie sind eine Messung *dieser* Funktion; der Gesamtzähler wäre dafür der
    gröbere Nenner (er enthält Standby und Steuerung, K1).

    ⛔ **Und sie greift nicht, wo im Zeitraum funktionsfremder Strom gemessen
    ist.** Der tragende Satz lautet *„sein ganzer Strom **ist** der Strom dieser
    Achse"* — er gilt für ein Gerät ohne zweite **Funktion**, nicht für jedes
    Gerät mit einer Wärme-**Achse**. Eine Split-Klimaanlage hat nach der
    Registry nur *Heizen* (kein Warmwasserkreis, N-304), **kühlt** aber; ihren
    Junistrom als *Strom Heizen* auszuweisen wäre eine Falschaussage über eine
    Menge (gemessen an der Demo-Anlage der r28, 15.06.2026: die Bosch
    Multisplit hätte **2,15 kWh „Strom Heizen"** getragen, an einem Tag mit
    gemessenem Kühlstrom). ⚠ Die Bauart wird dabei **nicht** gefragt
    (ADR-002/**P13**), sondern die **Messung** — dieselbe Größe, mit der
    E7/Option A den Nenner kürzt.

    ⚠ **Die Grenze, die bleibt:** Ohne Betriebsart-Zähler weiß eedc von einem
    Kühlbetrieb nichts; dort greift die Regel wie bei einem Ein-Funktions-Gerät.
    Dieselbe Annahme trifft WK-16h für die Kennzahl je Gerät.

    Returns:
        ``(Nutzenergie, Strom)`` dieser Achse — die beiden Seiten **eines**
        Quotienten, aus denen Σ und Geräte-Identität (N-441) entstehen.
    """
    fein_q = m.heizung_kwh if achse == HEIZEN else m.warmwasser_kwh
    fein_e = m.strom_heizen_kwh if achse == HEIZEN else m.strom_warmwasser_kwh
    nur_diese_funktion = (
        len(achsen) == 1
        and m.modus_strom_kuehlen_kwh <= 0
        and m.funktionsfremd_abzug_kwh <= 0
    )
    if nur_diese_funktion and not (fein_q > 0 and fein_e > 0):
        return m.waerme_kwh, m.strom_kwh
    return fein_q, fein_e


def funktions_eingaenge_der_anlage(
    kennzahlen: Sequence[GeraetKennzahlen],
) -> FunktionsEingaengeDerAnlage:
    """Σ über die Geräte, die die Achse **haben** — die eine Faltung (**WK-16i**).

    Der Rückfall für **S5 anlagenweit**: Fehlt die Monatszeile, entstehen
    Heizwärme, Warmwasser-Wärme, Strom Heizen, Strom Warmwasser, ``hat_split``
    und die Deckung je Funktion aus **denselben** Geräte-Mengen, die die Tabelle
    *„Zahlen je Gerät"* speisen. Zwei Quellen für einen Bildschirm wären zwei
    Zahlen (**S1**) — genau der Widerspruch, der N-503 ausgelöst hat: der Kasten
    sagte *„Strom nicht getrennt je Funktion gemessen"*, während die Tabelle
    direkt darunter 5,58 und 3,32 zeigte.

    ⚠ **Der Strom-Beitrag entscheidet über die beiden KENNZEICHEN, nicht über
    die Mengen** (seit WK-16j präzisiert). ``hat_split`` und
    ``waerme_ist_gesamt`` sind Aussagen über die **Messung dieses Zeitraums** —
    ein Gerät ohne Strom schaltet keine getrennte Strommessung frei, dieselbe
    Regel wie in {@link achsen_der_anlage} und {@link schranken_eingang}
    (N-441). ⛔ **Mengen und Identitäten bekommen den Riegel nicht:** Ein Gerät,
    das Wärme **ohne** Strom beisteuert, ist der Anlassfall von N-441 selbst
    (Wärme von A, Funktions-Strom von B). Es aus dem Zähler-Kreis zu werfen
    hieße, genau die Lage stumm zu stellen, gegen die die Deckung gebaut ist.

    ⭐ **Die Ein-Achsen-Regel gilt hier wie je Gerät** (**WK-16j/R-4**,
    {@link _mengen_der_achse}) — sonst zeigt die Tabelle *Zahlen je Gerät* für
    die Brauchwasser-WP **3,31** und der Kasten darüber behauptet, ihr Strom sei
    nicht je Funktion gemessen.

    ⛔ **Und nur die Geräte, die die Achse haben** (WK-16h/**R-1**,
    ``field_definitions.wp_waerme_achsen``): Die Heizwärme einer
    Brauchwasser-Wärmepumpe gehört in keine anlagenweite Heiz-Arbeitszahl — an
    diesem Gerät gibt es die Achse nicht, und ein Altwert in der Zeile ändert
    daran nichts (ADR-002/**P13**).

    ⚠ **Roh-Wärme, nicht die „getrennte" Teilmenge.** Summiert werden
    ``heizung_kwh``/``warmwasser_kwh`` (je Gerät bereits kanonisch aufgelöst,
    D1), nicht ``heizung_getrennt_kwh`` — dieselbe Wahl, die ``WpFakten`` für
    den abgeschlossenen Monat trifft und der Tag für seine Summe. Die andere
    wäre eine **dritte** Antwort auf dieselbe Frage; dass Zähler und Nenner
    dabei auseinanderlaufen können, beantwortet die Deckung darüber — mit einem
    Grund, nicht mit einer stillen Kürzung.
    """
    heizung = warmwasser = strom_heizen = strom_warmwasser = 0.0
    hat_split = waerme_ist_gesamt = False
    je_achse: dict[str, tuple[set[int], set[int]]] = {
        HEIZEN: (set(), set()), WARMWASSER: (set(), set()),
    }
    summe: dict[str, list[float]] = {HEIZEN: [0.0, 0.0], WARMWASSER: [0.0, 0.0]}
    for k in kennzahlen:
        m = k.mengen
        achsen = m.waerme_achsen or WAERME_ACHSEN
        # ⚠ **Der Strom-Beitrag entscheidet nur über die beiden KENNZEICHEN.**
        # Sie sind Aussagen über die *Messung* dieses Zeitraums: Ein Gerät ohne
        # Strom schaltet keine getrennte Strommessung frei und stellt keinen
        # gemeinsamen Wärmemengenzähler in Rechnung (N-441, *Beitrag statt
        # Bestand*). ⛔ **Für die Mengen und die Identitäten gilt er NICHT** —
        # ein Gerät, das Wärme ohne Strom beisteuert, ist der Anlassfall von
        # N-441 selbst (Wärme von A, Funktions-Strom von B ⇒ eine Zahl, deren
        # Zähler und Nenner verschiedene Geräte meinen). Es aus dem Zähler-Kreis
        # zu werfen hieße, genau diese Lage stumm zu stellen.
        if m.strom_kwh > 0:
            hat_split = hat_split or m.hat_getrennte_strommessung
            waerme_ist_gesamt = waerme_ist_gesamt or m.waerme_ist_gesamt_getrennt
        for achse in (HEIZEN, WARMWASSER):
            if achse not in achsen:
                continue
            q, e = _mengen_der_achse(m, achse, achsen)
            summe[achse][0] += q
            summe[achse][1] += e
            if q > 0:
                je_achse[achse][0].add(m.inv_id)
            if e > 0:
                je_achse[achse][1].add(m.inv_id)
    heizung, strom_heizen = summe[HEIZEN]
    warmwasser, strom_warmwasser = summe[WARMWASSER]
    q_h, e_h = je_achse[HEIZEN]
    q_w, e_w = je_achse[WARMWASSER]
    return FunktionsEingaengeDerAnlage(
        heizung_kwh=heizung,
        warmwasser_kwh=warmwasser,
        strom_heizen_kwh=strom_heizen,
        strom_warmwasser_kwh=strom_warmwasser,
        hat_split=hat_split,
        waerme_ist_gesamt=waerme_ist_gesamt,
        geraete_q_heizen=frozenset(q_h),
        geraete_e_heizen=frozenset(e_h),
        geraete_q_warmwasser=frozenset(q_w),
        geraete_e_warmwasser=frozenset(e_w),
    )
