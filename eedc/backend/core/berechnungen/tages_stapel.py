"""Der Betriebsart-Stapel **eines Tages** — die Zusammenführung beider Zweige.

**Warum es dieses Modul gibt** (10.09.2026, Konzept Wärme/Klima §8,
Bauschnitt 4). Ein Tag kann seine Stromaufteilung aus **zwei** Quellen haben:

* **Zweig 1 — gemessene Betriebsart-Zähler** (F4): eigene kWh-Zähler je
  Betriebsart, ggf. je Innengerät.
* **Zweig 2 — aus dem Betriebsmodus abgeleitet**: die Stundenzeilen tragen den
  Modus, die Menge kommt aus dem Leistungspfad und wird auf die Tages-Zählersumme
  normiert (``falte_modus_split_tag``).

Die Weiche zwischen ihnen ist **SOLL §6.1/F4**, Invariante K2: *„Ein einziger
zugeordneter Zähler schaltet das Gerät ganz auf den gemessenen Weg und
**verdrängt** die abgeleitete Aufteilung."* Sie gilt **je Gerät**, nicht je
Anlage — eine Klimaanlage mit Betriebsart-Zählern und eine Wärmepumpe ohne
dürfen nebeneinander stehen.

⛔ **Bis hierher stand diese Zusammenführung ausgeschrieben in
``api/routes/energie_profil/tag.py::get_tag_detail``** — also in einer Route,
und damit für jeden anderen Leser unerreichbar. Beim Bau des Monats-Verlaufs
(x = Tage) hätte sie ein zweites Mal entstehen müssen: **F-56.** Die Probe
``test_263_t3_gemessene_betriebsart_tag.py`` sagt im Kopf, warum das teuer
gewesen wäre — *„die beiden Zweige treffen sich in ``get_tag_detail``, die
Vorrang-Regel ist nur im Paar prüfbar"*.

⚠ **Und der Fehler, den es ohne diese Datei gegeben hätte, ist gemessen:** Der
erste Bauplan für den Monats-Verlauf kannte nur Zweig 2. An **dietmars** Anlage
(drei Innengeräte mit Riemann-Zählern je Betriebsart seit 24.08.2026) hätte der
Monat damit einen anderen Stapel gezeigt als Tag und Jahr daneben — die
S1-Verletzung (*„dieselbe Größe trägt überall denselben Wert"*), also genau die
v4.0.1-Klasse.

**Rein und ohne Datenbank** (ADR-001): Die Eingänge lädt der Aufrufer — die
Route für einen Tag, der Bereichs-Leser für einen ganzen Monat. Gefaltet wird
hier, und zwar nur einmal.

---

## Die Stunden (11.09.2026, Bauschnitt 5)

⭐ **Die Stunde verteilt den Tag — sie rechnet ihn nicht neu.** Welches Gerät
mit welchem Zweig und welcher Menge beiträgt, entscheidet **dieselbe** Auswahl
wie für den Tag ({@link beitraege_des_tages}). Die Stunde bekommt je Gerät und
Segment die Tagesmenge × ihren Anteil an der gemessenen Stundenform. Damit ist
Σ Stunden = Tagesbalken je Segment **per Konstruktion** — das ist S1 innerhalb
des Blocks, und genau daran hing W-17b (dietmar1968: 30 kWh Balken unter einer
284-kWh-Kachel).

* **Zweig 2:** Anteil an der Modus-Form × Tagesmenge ist algebraisch derselbe
  Faktor wie in ``falte_modus_split_tag`` (Tagesmenge ÷ Stundensumme) — auch
  ohne Normierung und für Stunden ohne Modus (die gehen in den Rest).
* **Zweig 1:** je Feld verteilt, dann ``modus_strom_zeile`` **je Stunde** auf
  dieselbe Schlüsselmenge (explizite 0,0) — die Innengeräte-Regel bleibt an
  ihrer einen Stelle. Die Summanden eines Geräts mit getrennter Strommessung
  (N-766) gehören zur Schlüsselmenge und bekommen die Form ihres eigenen
  Zählers. Ohne feste Schlüsselmenge wäre sie nicht linear: fehlt
  das Gerätefeld in einer Stunde, summierte sie die Innengeräte (Probe der
  Gegenprüfung: 5,5 statt 4,0).
* **Keine Form, aber eine Menge** (z. B. ein Zähler, dessen ganzer Tagesverbrauch
  in der Stunde lag, die das Rückwärts-Raster dem Folgetag gibt): **nicht
  verteilen** — die Menge fehlt in den Stunden und wird als
  ``ohne_stundenform_kwh`` genannt (ADR-002/P4: keine erfundene Form).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional, Sequence

from backend.core.berechnungen.modus_split import (
    ModusSplit,
    ModusStunde,
    abdeckung_ueber_geraete,
    teilmengen_passen,
)
from backend.core.berechnungen.betriebsart_gemessen import (
    ModusStromZeile,
    funktionsfremd_abzug_kwh,
    geraetefeld_oder_innengeraete,
    modus_strom_zeile,
    summanden_gelten,
)
from backend.core.betriebsmodus import HEIZEN, KUEHLEN, WARMWASSER

#: Toleranz der Teilmengen-Invariante (kWh) — ``Σ Teilmengen ≤ Gesamt + x``.
#: ⚠ Passt ein Gerät nicht, wird es **ganz** ausgelassen statt gekappt: eine
#: stille Kappung machte aus einem Widerspruch eine plausible Zahl (SOLL §6.1,
#: Invariante am Gesamt-Stromzähler).
TEILMENGEN_TOLERANZ_KWH = 0.5

#: Anzahl der Stunden-Slots eines Tages (Rückwärts-Raster, Slot h = [h−1, h)).
STUNDEN = 24

#: Die Modi, die Zweig 2 als eigene Teilmenge zählt — alles andere ist Rest.
#: Dieselbe Menge wie in {@link beitraege_des_tages} (N-336: Warmwasser nur hier).
_ZWEIG2_MODI = (HEIZEN, KUEHLEN, WARMWASSER)

#: N-766: die Summanden-Felder, die Zweig 1 neben den Betriebsart-Zählern liest,
#: und ihre Schlüssel in den Tageswerten (``TAGESDETAIL_AUSGABE``).
SUMMANDEN_AUSGABE: dict[str, str] = {
    "wp_strom_heizen_kwh": "strom_heizen_kwh",
    "wp_strom_warmwasser_kwh": "strom_warmwasser_kwh",
}


def summanden_aus_tageswerten(
    werte_je_ausgabe: Mapping[str, Mapping[str, Optional[float]]],
) -> dict[str, dict[str, float]]:
    """``{ausgabe: {inv_id: kWh}}`` der Tageswerte → ``{inv_id: {feld: kWh}}`` der Summanden (N-766).

    Der Eingang ``summanden_je_inv`` von {@link beitraege_des_tages}. Nur Werte
    ``is not None`` (0,0 ist eine Messung); ob sie Summanden SIND, entscheidet
    dort das Kennzeichen des Geräts.
    """
    out: dict[str, dict[str, float]] = {}
    for ausgabe, feld in SUMMANDEN_AUSGABE.items():
        for inv_id, kwh in (werte_je_ausgabe.get(ausgabe) or {}).items():
            if kwh is not None:
                out.setdefault(str(inv_id), {})[feld] = float(kwh)
    return out


@dataclass(frozen=True)
class TagesStapel:
    """Die Betriebsart-Aufteilung eines Tages über **alle** Geräte der Anlage."""

    heizen_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    kuehlen_kwh: float = 0.0
    lueften_kwh: float = 0.0
    entfeuchten_kwh: float = 0.0
    #: Was von der Bezugsmenge nach Abzug aller Teilmengen übrig bleibt.
    nicht_aufgeteilt_kwh: float = 0.0
    #: ⚠ **W-17b: die Grundmenge, auf die sich der Stapel bezieht** — die Σ der
    #: Bezugsmengen der Geräte, die eine Aufteilung beigesteuert haben. Sie ist
    #: bewusst **nicht** der gesamte Wärmepumpen-Strom: dort steckt auch der
    #: Strom von Geräten ohne Aufteilung, der sonst als „nicht aufgeteilt" beim
    #: falschen Gerät erschiene (an einer Instanz gemessen: 96,4 statt 6,4 kWh).
    #: dietmar1968 sah 30 kWh Balken unter einer 284-kWh-Kachel; die Differenz
    #: muss benannt werden, statt stumm zu bleiben.
    bezug_kwh: float = 0.0
    #: Stunden mit Modus-Erkenntnis, **über Geräte gedeckelt** — zwei Geräte mit
    #: je 18 Stunden ergeben nicht 36 Stunden Erkenntnis (W-17, dietmar1968).
    abdeckung_h: float = 0.0
    #: Hat überhaupt ein Gerät beigetragen?
    #: ⚠ **Nicht zu verwechseln mit** {@link GeraeteBeitrag.hat_split} — dort
    #: heißt es *„dieses Gerät misst Heizen und Warmwasser getrennt"* (F5,
    #: ``getrennte_strommessung``), wie überall sonst im Baum
    #: (``ImdTypBeitrag.wp_hat_split``, ``WpFakten.hat_split``). Hier heißt es
    #: *„der Stapel ist nicht leer"*. Die Doppelbelegung ist Altbestand dieser
    #: Datei; sie steht hier benannt, damit niemand das eine für das andere
    #: liest.
    hat_split: bool = False
    #: Kam mindestens ein Beitrag aus **gemessenen** Betriebsart-Zählern?
    hat_gemessen: bool = False
    #: **SOLL-§9-E7 / Ergänzung (Option A):** Was vom Nenner einer Arbeitszahl
    #: abgezogen werden **darf** — die Tages-Entsprechung zu
    #: ``WpFakten.modus_strom_funktionsfremd_abzug_kwh``.
    #:
    #: ⛔ **Nicht** ``kuehlen + lueften + entfeuchten``. Ein Gerät mit
    #: getrennter Strommessung, dessen Aufteilung nur **abgeleitet** ist,
    #: steuert 0 bei: sein Kühlanteil ist eine Verteilung von
    #: ``strom_heizen + strom_warmwasser`` und steht nicht *neben* diesem
    #: Nenner, sondern **darin**. Entschieden wird je Gerät
    #: ({@link funktionsfremd_abzug_kwh}), hier nur summiert — eine Anlage darf
    #: ein F5-Gerät neben einem nicht-F5-Gerät haben.
    #:
    #: ⚠ Die Segment-Mengen darüber bleiben davon **unberührt** (K1): Balken,
    #: Restmenge und Stundenverteilung rechnen weiter mit dem vollen Kühlstrom.
    funktionsfremd_abzug_kwh: float = 0.0

    @property
    def ist_leer(self) -> bool:
        return not self.hat_split


@dataclass(frozen=True)
class GeraeteBeitrag:
    """Was **ein** Gerät zum Tagesstapel beiträgt — die Entscheidung des Tages.

    Sie wird für den Tag gefaltet und für die Stunden verteilt; beide lesen
    dieselbe Liste, damit die Stunde nichts entscheidet, was der Tag nicht
    schon entschieden hat.
    """

    inv_id: str
    gemessen: bool
    bezug_kwh: float
    #: **Ist der Bezug dieses Beitrags die feine Summe?** — ``bezug_kwh`` ist
    #: die K3-Stufe „fein" (``strom_heizen + strom_warmwasser``) und nicht der
    #: Gesamtzähler. **Nicht** die Bedeutung von ``TagesStapel.hat_split``
    #: darüber, und seit N-462 auch nicht mehr die von
    #: ``ImdTypBeitrag.wp_hat_split`` (dort ist es weiterhin das Kennzeichen und
    #: beantwortet die andere Frage: „liegt der Strom getrennt je Funktion vor?").
    #:
    #: Gebraucht für **SOLL-§9-E7/Option A**: Bei abgeleiteter Aufteilung darf
    #: der funktionsfremde Anteil einen **feinen** Nenner nicht kürzen — er
    #: verteilt ihn nur. Steht dort der **Gesamtzähler**, steckt der Kühlstrom
    #: darin und muss abgezogen werden, wie im Nicht-getrennt-Zweig. Die Regel
    #: steht im Layer ({@link funktionsfremd_abzug_kwh}), dieses Feld trägt bloß
    #: die Lage des Beitrags dorthin.
    hat_split: bool = False
    heizen_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    kuehlen_kwh: float = 0.0
    lueften_kwh: float = 0.0
    entfeuchten_kwh: float = 0.0
    nicht_aufgeteilt_kwh: float = 0.0
    abdeckung_h: float = 0.0
    #: Zweig 1: die Tageswerte je Feld, **unverändert samt Innengerät-Suffix** —
    #: die Stunde verteilt sie einzeln und löst danach je Stunde auf.
    #: ⚠ Nur Betriebsart-Zähler; die Summanden stehen in ``summanden``.
    felder: dict[str, float] = field(default_factory=dict)
    #: Zweig 1, N-766: die Summanden-Tageswerte (``strom_heizen_kwh``,
    #: ``strom_warmwasser_kwh``) — nur bei gesetztem Kennzeichen
    #: ``getrennte_strommessung``. Die Stunde verteilt sie nach der Form ihres
    #: eigenen Zählers, nicht als Teilmenge eines anderen.
    summanden: dict[str, float] = field(default_factory=dict)


def _nenner_ist_feine_summe(
    inv, inv_id_str: str, stufe_je_inv: Optional[dict[str, str]],
) -> bool:
    """Ist der Bezug dieses Geräts die feine Summe? — für SOLL-§9-E7/Option A.

    ⭐ **Die Stufe kommt vom Aufrufer** ({@link
    backend.services.snapshot.aggregator.get_wp_strom_stufe_je_investition}),
    denn sie hängt an der **Zuordnung** und die steht im ``sensor_mapping`` —
    das diese Faltung bewusst nicht sieht (sie faltet, sie lädt nicht). Dieselbe
    Bauform wie ``ist_verfuegbar`` in der Beitragsschicht: die Regel hier, die
    Eingänge beim Aufrufer.

    ⚠ **Ohne Angabe bleibt es beim Kennzeichen**, und das ist die vorsichtige
    Antwort: An einem F5-Gerät heißt sie „feine Summe" ⇒ kein Abzug ⇒ der Nenner
    bleibt so groß, wie er ohne diese Regel war (ADR-002/P4 — lieber keine
    Kürzung als eine erfundene). Sie ist zugleich das **alte** Verhalten, sodass
    ein Aufrufer, der die Stufe nicht liefert, nichts verschlechtert.

    ⚠ Bewusst ``getattr``: Die Faltung bekommt echte ``Investition``-Objekte
    ebenso wie die schlanken Doubles der Layer-Proben, und ein fehlendes
    ``parameter`` ist kein Grund für einen Absturz.
    """
    stufe = (stufe_je_inv or {}).get(inv_id_str)
    if stufe is not None:
        return stufe == "fein"
    return bool((getattr(inv, "parameter", None) or {}).get("getrennte_strommessung"))


def _summanden_des_geraets(
    inv, inv_id_str: str, summanden_je_inv: Optional[Mapping[str, Mapping[str, float]]],
) -> dict[str, float]:
    """N-766: die Summanden dieses Geräts für Zweig 1 — leer ohne Kennzeichen (s. ``summanden_gelten``)."""
    if not summanden_je_inv or not summanden_gelten(getattr(inv, "parameter", None)):
        return {}
    return {
        f: float(w) for f, w in (summanden_je_inv.get(inv_id_str) or {}).items()
        if f in SUMMANDEN_AUSGABE.values() and w is not None
    }


def beitraege_des_tages(
    gemessen_je_inv: dict[str, dict[str, float]],
    zaehler_strom_je_inv: dict[str, float],
    splits_je_inv: dict[str, ModusSplit],
    investitionen_by_id: dict,
    datum: date,
    *,
    stufe_je_inv: Optional[dict[str, str]] = None,
    summanden_je_inv: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> list[GeraeteBeitrag]:
    """Welches Gerät mit welchem Zweig beiträgt — die eine Auswahl (K2, Zeitfilter, Invariante).

    Args:
        gemessen_je_inv: ``{inv_id: {feldname: kwh}}`` aus
            ``get_betriebsart_strom_tageswerte`` — **mit unveränderten
            Feldnamen** samt Innengerät-Suffix. ⚠ Die Regel *Gerätefeld gewinnt,
            sonst Σ Innengeräte* löst ``modus_strom_zeile`` auf; sie hier vorab
            zu summieren wäre die Doppelzählungs-Klasse.
        zaehler_strom_je_inv: der **zählerbasierte** Tagesstrom je Gerät
            (``TagesZusammenfassung.komponenten_kwh``). ⛔ **Nicht** die Summe
            aus dem Leistungspfad — die weicht ab, und genau daran hängt W-17b.
            ⚠ Seit N-434 steht er im selben Fenster wie ``gemessen_je_inv``.
        splits_je_inv: ``{inv_id: ModusSplit}`` aus ``lade_modus_split_tag``
            bzw. dem Bereichs-Leser (Zweig 2).
        investitionen_by_id: für die Zeitfilterung (``ist_aktiv_an``).
        datum: der Tag — entscheidet, welches Gerät überhaupt zählt.
        stufe_je_inv: ``{inv_id: "fein"|"gesamt"}`` — welche K3-Stufe der Bezug
            dieses Geräts trägt (N-462). Kommt aus
            ``aggregator.get_wp_strom_stufe_je_investition``, weil sie am
            ``sensor_mapping`` hängt. Fehlt sie, gilt das Kennzeichen — das
            bisherige Verhalten (s. {@link _nenner_ist_feine_summe}).
        summanden_je_inv: N-766 — ``{inv_id: {"strom_heizen_kwh": kWh,
            "strom_warmwasser_kwh": kWh}}`` (``summanden_aus_tageswerten``),
            nur in Zweig 1 und nur bei gesetztem Kennzeichen des Geräts
            gelesen: Heizen und Warmwasser einer Wärmepumpe mit getrennter
            Strommessung und einem Betriebsart-Zähler (etwa Kühlen) sind
            gemessen. Fehlt er, wie bisher.

    Returns:
        Die Beiträge, Zweig 1 vor Zweig 2 — dieselbe Reihenfolge, in der die
        Tagesfaltung sie addiert.
    """
    beitraege: list[GeraeteBeitrag] = []
    gemessene_geraete: set[str] = set()

    # ── Zweig 1: gemessene Betriebsart-Zähler (Vorrang, SOLL §6.1/F4) ──────
    for inv_id_str, felder in gemessen_je_inv.items():
        inv = investitionen_by_id.get(inv_id_str)
        if inv is None or not inv.ist_aktiv_an(datum):
            continue
        summanden = _summanden_des_geraets(inv, inv_id_str, summanden_je_inv)
        zeile = modus_strom_zeile(
            {**felder, **summanden}, summanden_zaehlen=bool(summanden),
        )
        if not zeile.gemessen:
            continue
        # Ohne Tages-Bezug gibt es nichts, wovon die Teilmenge eine wäre.
        geraet_bezug = zaehler_strom_je_inv.get(inv_id_str)
        if geraet_bezug is None:
            continue
        if (
            zeile.heizen_kwh + zeile.warmwasser_kwh + zeile.kuehlen_kwh
            > float(geraet_bezug) + TEILMENGEN_TOLERANZ_KWH
        ):
            continue
        gemessene_geraete.add(inv_id_str)
        beitraege.append(GeraeteBeitrag(
            inv_id=inv_id_str,
            gemessen=True,
            bezug_kwh=float(geraet_bezug),
            hat_split=_nenner_ist_feine_summe(inv, inv_id_str, stufe_je_inv),
            heizen_kwh=zeile.heizen_kwh,
            # N-766: Warmwasser gemessen aus dem Summanden (nur mit Kennzeichen).
            warmwasser_kwh=zeile.warmwasser_kwh,
            kuehlen_kwh=zeile.kuehlen_kwh,
            # E4 (Konzept §2.3): Lüften und Entfeuchten sind erfassbar und
            # erscheinen in der Aufteilung — sie bekommen nur keine Kennzahl.
            lueften_kwh=zeile.lueften_kwh,
            entfeuchten_kwh=zeile.entfeuchten_kwh,
            nicht_aufgeteilt_kwh=max(
                0.0,
                float(geraet_bezug) - zeile.heizen_kwh - zeile.warmwasser_kwh
                - zeile.kuehlen_kwh - zeile.lueften_kwh - zeile.entfeuchten_kwh,
            ),
            felder=dict(felder),
            summanden=dict(summanden),
        ))

    # ── Zweig 2: aus dem Betriebsmodus abgeleitet ──────────────────────────
    for inv_id_str, split in splits_je_inv.items():
        # K2: ein Gerät, das oben schon gezählt hat, trägt hier nicht noch
        # einmal bei — der gemessene Weg verdrängt den abgeleiteten **ganz**.
        if inv_id_str in gemessene_geraete:
            continue
        inv = investitionen_by_id.get(inv_id_str)
        if inv is None or not inv.ist_aktiv_an(datum):
            continue
        if not teilmengen_passen(split, split.bezug_kwh):
            continue
        geraet_bezug = float(split.bezug_kwh or 0.0)
        beitraege.append(GeraeteBeitrag(
            inv_id=inv_id_str,
            gemessen=False,
            bezug_kwh=geraet_bezug,
            hat_split=_nenner_ist_feine_summe(inv, inv_id_str, stufe_je_inv),
            heizen_kwh=split.teilmenge_kwh(HEIZEN),
            kuehlen_kwh=split.teilmenge_kwh(KUEHLEN),
            # N-336: hier abgeleitet aus dem Modus (Zweig 1: aus dem Summanden, N-766).
            warmwasser_kwh=split.teilmenge_kwh(WARMWASSER),
            nicht_aufgeteilt_kwh=max(
                0.0,
                geraet_bezug
                - split.teilmenge_kwh(HEIZEN) - split.teilmenge_kwh(KUEHLEN)
                - split.teilmenge_kwh(WARMWASSER),
            ),
            abdeckung_h=split.abdeckung_h,
        ))
    return beitraege


def _falte(beitraege: Sequence[GeraeteBeitrag]) -> TagesStapel:
    """Summiert die Beiträge — in ihrer Reihenfolge, damit die Zahlen bitgleich bleiben."""
    heizen = warmwasser = kuehlen = lueften = entfeuchten = 0.0
    rest = bezug = abdeckung = abzug = 0.0
    for b in beitraege:
        bezug += b.bezug_kwh
        heizen += b.heizen_kwh
        kuehlen += b.kuehlen_kwh
        warmwasser += b.warmwasser_kwh
        lueften += b.lueften_kwh
        entfeuchten += b.entfeuchten_kwh
        rest += b.nicht_aufgeteilt_kwh
        # ⭐ **SOLL-§9-E7/Option A: abgezogen wird nur, was im Nenner steht.**
        # Die Regel wird GERUFEN, nicht nachgebaut — dieselbe Stelle, die der
        # Monatspfad ruft (F-56: eine Regel, zwei Codestellen, eine Drift).
        # ``ModusStromZeile`` ist hier bloß die Übergabeform; ihre Zahlen sind
        # die des Beitrags, ihr ``gemessen`` seine Herkunft.
        abzug += beitrag_abzug_kwh(b)
        if not b.gemessen:
            # W-17: Die Schleife läuft über die GERÄTE des Tages. Zwei Wärmepumpen
            # mit je 18 erfassten Stunden ergeben nicht 36 Stunden Erkenntnis,
            # sondern höchstens 18 — ein Tag hat 24. Genau diese Zahl hat
            # dietmar1968 gemeldet (T89667 #210). Die Regel steht im Layer-SoT.
            abdeckung = abdeckung_ueber_geraete(abdeckung, b.abdeckung_h)
    return TagesStapel(
        heizen_kwh=heizen,
        warmwasser_kwh=warmwasser,
        kuehlen_kwh=kuehlen,
        lueften_kwh=lueften,
        entfeuchten_kwh=entfeuchten,
        nicht_aufgeteilt_kwh=rest,
        bezug_kwh=bezug,
        abdeckung_h=abdeckung,
        hat_split=bool(beitraege),
        hat_gemessen=any(b.gemessen for b in beitraege),
        funktionsfremd_abzug_kwh=abzug,
    )


def beitrag_abzug_kwh(b: GeraeteBeitrag) -> float:
    """Der Nenner-Abzug **eines** Tages-Beitrags — SOLL-§9-E7/Option A.

    ⭐ **Herausgezogen am 14.09.2026 (WK-16a), damit die Tabelle „Zahlen je
    Gerät" denselben Abzug benutzt wie die Anlagensumme.** Vorher stand die
    Übergabe-Zeile inline in der Faltung; wer sie je Gerät brauchte, hätte sie
    abschreiben müssen — die F-56-Klasse (*eine Regel, zwei Codestellen, eine
    Drift*), und zwar an derselben Größe, an der sie zuletzt zugeschlagen hat.

    ``ModusStromZeile`` ist hier bloß die Übergabeform; ihre Zahlen sind die des
    Beitrags, ihr ``gemessen`` seine Herkunft.
    """
    return funktionsfremd_abzug_kwh(
        ModusStromZeile(
            heizen_kwh=b.heizen_kwh,
            kuehlen_kwh=b.kuehlen_kwh,
            warmwasser_kwh=b.warmwasser_kwh,
            lueften_kwh=b.lueften_kwh,
            entfeuchten_kwh=b.entfeuchten_kwh,
            gemessen=b.gemessen,
            abdeckung_h=b.abdeckung_h,
        ),
        hat_split=b.hat_split,
    )


def falte_tages_stapel(
    gemessen_je_inv: dict[str, dict[str, float]],
    zaehler_strom_je_inv: dict[str, float],
    splits_je_inv: dict[str, ModusSplit],
    investitionen_by_id: dict,
    datum: date,
    *,
    stufe_je_inv: Optional[dict[str, str]] = None,
    summanden_je_inv: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> TagesStapel:
    """Faltet beide Zweige eines Tages zu **einem** Stapel.

    Args wie {@link beitraege_des_tages}.

    Returns:
        Den ``TagesStapel``. Trägt **kein** Gerät bei, ist er leer statt eine
        Reihe von Nullen (ADR-002/P4: keine Aussage statt einer 0).
    """
    return _falte(beitraege_des_tages(
        gemessen_je_inv, zaehler_strom_je_inv, splits_je_inv,
        investitionen_by_id, datum, stufe_je_inv=stufe_je_inv,
        summanden_je_inv=summanden_je_inv,
    ))


# ── Die Stunden ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StundenFormen:
    """Die gemessene **Form** der Stunden je Gerät — sie verteilt, sie entscheidet nichts.

    Jede Liste hat 24 Einträge (Slot h = [h−1, h)); ``None`` heißt „in diesem
    Slot kein Wert" und trägt keinen Anteil.
    """

    #: Zweig 1: je Gerät je Feld (samt Suffix) die Slot-Mengen des Zählers.
    felder_je_inv: dict[str, dict[str, list[Optional[float]]]] = field(default_factory=dict)
    #: Zweig 1, Rest-Form: der Gesamtstrom des Geräts je Slot aus dem Zählerpfad.
    gesamt_je_inv: dict[str, list[Optional[float]]] = field(default_factory=dict)
    #: Rückfall für den Gesamtstrom und Zweig 2: die Stundenzeilen (Leistungspfad)
    #: mit Modus und Slot.
    modus_stunden_je_inv: dict[str, list[ModusStunde]] = field(default_factory=dict)


@dataclass(frozen=True)
class StundenVerteilung:
    """Der Tagesstapel auf 24 Stunden verteilt."""

    #: 24 Einträge. Jeder trägt das **Tor des Tages** (``hat_split``,
    #: ``hat_gemessen``, ``abdeckung_h``) — hat der Tag eine Aufteilung, gilt sie
    #: für jede seiner Stunden; auch eine Stunde, die nur Rest trägt, bleibt
    #: sichtbar, sonst verlöre die Zeichnung ihre Summe.
    stunden: list[TagesStapel]
    #: Menge, für die es keine Stundenform gab — sie fehlt in den Stunden (P4).
    ohne_stundenform_kwh: float = 0.0
    #: ⭐ **Dieselben Stunden, nur noch je Gerät aufgeschlüsselt** (WK-16c,
    #: 14.09.2026) — ``{inv_id: [24 TagesStapel]}``. Sie entstehen in der
    #: Schleife darunter ohnehin und wurden bis dahin unmittelbar addiert; die
    #: Verteilungs-Sicht braucht sie getrennt, weil ein Segment dort *Gerät ×
    #: Funktion* ist („WP Heizen" neben „Klima Heizen", Konzept Kap. 7/E1:
    #: Mengen ja, Kennzahlen nein).
    #:
    #: ⚠ **Die Summe über die Geräte ist ``stunden``, bitgleich** — es ist keine
    #: zweite Rechnung, sondern dieselbe eine Stufe früher abgegriffen. Wer hier
    #: etwas anderes summiert, hat einen Fehler, keine zweite Wahrheit.
    je_geraet: dict[str, list[TagesStapel]] = field(default_factory=dict)


def verteile_menge(
    menge: float, form: Sequence[Optional[float]],
) -> tuple[list[float], float]:
    """Eine Menge nach einer Form auf 24 Slots — oder gar nicht.

    Returns:
        ``(24 Werte, nicht_verteilt)``. Ohne positive Form bleibt die ganze Menge
        unverteilt; sie wird nie gleichmäßig verteilt (das wäre eine erfundene
        Form).
    """
    if menge <= 0:
        return [0.0] * STUNDEN, 0.0
    gewichte = [
        max(0.0, float(form[h])) if h < len(form) and form[h] is not None else 0.0
        for h in range(STUNDEN)
    ]
    summe = sum(gewichte)
    if summe <= 0:
        return [0.0] * STUNDEN, float(menge)
    return [menge * g / summe for g in gewichte], 0.0


def verteile_felder_auf_stunden(
    felder_je_inv: Mapping[str, Mapping[str, float]],
    formen_je_inv: Mapping[str, Mapping[str, Sequence[Optional[float]]]],
    basis_feld: str,
) -> tuple[list[float], float]:
    """Eine Linie (Wärme, Kälte) je Gerät und je Feld auf 24 Stunden — N-437.

    **Dieselbe Bauform wie der Stapel** (`verteile_tages_stapel_auf_stunden`,
    Zweig 1): je Gerät je Feld die Tagesmenge nach **seiner** Form, danach je
    Stunde mit der einen Regel aufgelöst (``geraetefeld_oder_innengeraete`` —
    Gerätefeld schlägt Σ Innengeräte, nie addiert). Weil ein Feld ohne
    Tageswert in ``felder_je_inv`` gar nicht vorkommt, nimmt jede Stunde
    dieselbe Quelle wie der Tag.

    ⛔ **Nie die Summe über Geräte auf die Summe ihrer Formen.** Eine Menge ist
    über Geräte addierbar (SOLL §5), eine Form nicht: Bis 11.09.2026 stand die
    Wärme eines Geräts dadurch in den Stunden eines anderen (gemessen im
    Snapshot-Pfad und im HA-Hauptpfad bei Rücksprung/Tagesreset).

    Returns:
        ``(24 Werte, ohne_stundenform_kwh)`` — der Rest **je Gerät gegen den
        aufgelösten Tageswert** gemessen, wie beim Stapel: So zählen
        verdrängte Innengerät-Felder nie mit (P4: genannt, nicht erfunden).
    """
    je_stunde = [0.0] * STUNDEN
    ohne = 0.0
    for inv_id, felder in felder_je_inv.items():
        formen = formen_je_inv.get(inv_id, {})
        verteilt = {
            feld: verteile_menge(float(wert or 0.0), formen.get(feld, [None] * STUNDEN))[0]
            for feld, wert in felder.items()
        }
        geraet = [
            geraetefeld_oder_innengeraete({f: w[h] for f, w in verteilt.items()}, basis_feld)
            or 0.0
            for h in range(STUNDEN)
        ]
        tageswert = geraetefeld_oder_innengeraete(dict(felder), basis_feld) or 0.0
        ohne += max(0.0, tageswert - sum(geraet))
        for h in range(STUNDEN):
            je_stunde[h] += geraet[h]
    # Rundungsreste der Division sind keine fehlende Form.
    return je_stunde, (ohne if ohne > 1e-6 else 0.0)


def _modus_form(stunden: Sequence[ModusStunde], gehoert_dazu) -> list[float]:
    form = [0.0] * STUNDEN
    for s in stunden:
        if s.stunde is None or not 0 <= s.stunde < STUNDEN:
            continue
        if gehoert_dazu(s.modus):
            form[s.stunde] += abs(float(s.kwh or 0.0))
    return form


def gesamt_form(inv_id: str, formen: StundenFormen) -> list[Optional[float]]:
    """Gesamtstrom je Slot: Zählerpfad, sonst Leistungspfad der Stundenzeilen.

    ⚠ **Seit WK-16c öffentlich** (14.09.2026): Die Verteilungs-Sicht verteilt
    den Zähler-Rest eines F5-Geräts über **dieselbe** Restform wie Zweig 1
    darunter. Sie mit einem führenden Unterstrich privat zu lassen und daneben
    nachzubauen wäre die F-56-Klasse; sie zu kopieren erst recht.
    """
    gesamt = formen.gesamt_je_inv.get(inv_id)
    if gesamt and any(v is not None for v in gesamt):
        return list(gesamt)
    return _modus_form(formen.modus_stunden_je_inv.get(inv_id, ()), lambda _m: True)


def verteile_tages_stapel_auf_stunden(
    beitraege: Sequence[GeraeteBeitrag],
    formen: StundenFormen,
) -> StundenVerteilung:
    """Verteilt die Beiträge des Tages auf 24 Stunden (s. Modul-Kopf, *Die Stunden*)."""
    tag = _falte(beitraege)
    seg = ("heizen", "warmwasser", "kuehlen", "lueften", "entfeuchten", "rest")
    je_stunde = {k: [0.0] * STUNDEN for k in seg}
    # WK-16c: dieselben Zahlen, eine Stufe früher abgegriffen (s. `je_geraet`).
    je_geraet: dict[str, list[TagesStapel]] = {}
    ohne = 0.0

    for b in beitraege:
        geraet = {k: [0.0] * STUNDEN for k in seg}
        if b.gemessen:
            # Je Feld verteilen, dann je Stunde auflösen — auf DIESELBE
            # Schlüsselmenge, damit „Gerätefeld gewinnt" in jeder Stunde gilt.
            formen_felder = formen.felder_je_inv.get(b.inv_id, {})
            verteilt: dict[str, list[float]] = {}
            roh: dict[str, list[float]] = {}
            # N-766: die Summanden gehören zur Schlüsselmenge — je mit der Form
            # ihres eigenen Zählers (der Aufrufer legt sie in `felder_je_inv`).
            for feld, tageswert in {**b.felder, **b.summanden}.items():
                form = formen_felder.get(feld, [None] * STUNDEN)
                verteilt[feld], _ = verteile_menge(float(tageswert or 0.0), form)
                roh[feld] = [float(v) if v is not None else 0.0 for v in
                             (list(form) + [None] * STUNDEN)[:STUNDEN]]
            rest_form: list[float] = []
            gesamt = gesamt_form(b.inv_id, formen)
            mit_summanden = bool(b.summanden)
            for h in range(STUNDEN):
                z = modus_strom_zeile(
                    {f: w[h] for f, w in verteilt.items()}, summanden_zaehlen=mit_summanden,
                )
                geraet["heizen"][h] = z.heizen_kwh
                geraet["warmwasser"][h] = z.warmwasser_kwh
                geraet["kuehlen"][h] = z.kuehlen_kwh
                geraet["lueften"][h] = z.lueften_kwh
                geraet["entfeuchten"][h] = z.entfeuchten_kwh
                z_roh = modus_strom_zeile(
                    {f: w[h] for f, w in roh.items()}, summanden_zaehlen=mit_summanden,
                )
                g = gesamt[h] if h < len(gesamt) and gesamt[h] is not None else 0.0
                rest_form.append(max(
                    0.0,
                    g - z_roh.heizen_kwh - z_roh.warmwasser_kwh - z_roh.kuehlen_kwh
                    - z_roh.lueften_kwh - z_roh.entfeuchten_kwh,
                ))
            geraet["rest"], _ = verteile_menge(b.nicht_aufgeteilt_kwh, rest_form)
        else:
            stunden = formen.modus_stunden_je_inv.get(b.inv_id, ())
            for key, modus, menge in (
                ("heizen", HEIZEN, b.heizen_kwh),
                ("kuehlen", KUEHLEN, b.kuehlen_kwh),
                ("warmwasser", WARMWASSER, b.warmwasser_kwh),
            ):
                geraet[key], _ = verteile_menge(
                    menge, _modus_form(stunden, lambda m, _mo=modus: m == _mo),
                )
            geraet["rest"], _ = verteile_menge(
                b.nicht_aufgeteilt_kwh,
                _modus_form(stunden, lambda m: m not in _ZWEIG2_MODI),
            )

        # Was die Stunden dieses Geräts NICHT tragen, je Segment gegen den Tag
        # gemessen — so zählen verdrängte Innengeräte-Felder nie mit.
        for key, tageswert in (
            ("heizen", b.heizen_kwh), ("warmwasser", b.warmwasser_kwh),
            ("kuehlen", b.kuehlen_kwh), ("lueften", b.lueften_kwh),
            ("entfeuchten", b.entfeuchten_kwh), ("rest", b.nicht_aufgeteilt_kwh),
        ):
            ohne += max(0.0, tageswert - sum(geraet[key]))
            for h in range(STUNDEN):
                je_stunde[key][h] += geraet[key][h]
        # WK-16c: die Stunden DIESES Geräts, bevor sie in die Summe fallen. Das
        # Tor (`hat_split`/`hat_gemessen`/`abdeckung_h`) ist das des Tages —
        # dieselbe Begründung wie bei `stunden_stapel` unten.
        je_geraet[b.inv_id] = [
            TagesStapel(
                heizen_kwh=geraet["heizen"][h],
                warmwasser_kwh=geraet["warmwasser"][h],
                kuehlen_kwh=geraet["kuehlen"][h],
                lueften_kwh=geraet["lueften"][h],
                entfeuchten_kwh=geraet["entfeuchten"][h],
                nicht_aufgeteilt_kwh=geraet["rest"][h],
                bezug_kwh=sum(geraet[k][h] for k in seg),
                abdeckung_h=b.abdeckung_h,
                hat_split=True,
                hat_gemessen=b.gemessen,
            )
            for h in range(STUNDEN)
        ]

    stunden_stapel = [
        TagesStapel(
            heizen_kwh=je_stunde["heizen"][h],
            warmwasser_kwh=je_stunde["warmwasser"][h],
            kuehlen_kwh=je_stunde["kuehlen"][h],
            lueften_kwh=je_stunde["lueften"][h],
            entfeuchten_kwh=je_stunde["entfeuchten"][h],
            nicht_aufgeteilt_kwh=je_stunde["rest"][h],
            bezug_kwh=sum(je_stunde[k][h] for k in seg),
            abdeckung_h=tag.abdeckung_h,
            hat_split=tag.hat_split,
            hat_gemessen=tag.hat_gemessen,
            # ⚠ `funktionsfremd_abzug_kwh` bleibt hier bewusst 0: Die Stunde
            # verteilt **Mengen**, und ein Nenner-Abzug ist keine Menge, die
            # man auf 24 Slots legt. Wer eine Stunden-Arbeitszahl bauen will,
            # holt ihn je Stunde aus denselben Beiträgen — nicht aus diesem
            # Feld, das dort nichts behauptet.
        )
        for h in range(STUNDEN)
    ]
    # Rundungsreste der Division sind keine fehlende Form.
    return StundenVerteilung(
        stunden=stunden_stapel,
        ohne_stundenform_kwh=ohne if ohne > 1e-6 else 0.0,
        je_geraet=je_geraet,
    )
