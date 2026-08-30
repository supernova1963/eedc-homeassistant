"""Monatsbericht — der Context des PDF (#395 Punkt 4, OB73-gif).

**Der Melderwunsch, wörtlich:** *„die Ablage der Monatsdaten als PDF im Stile
der Cockpit Monats Ansicht"*. Konzept ``docs/KONZEPT-MONATSBERICHT.md``
(abgenommen Gernot, 2026-08-30).

## Warum dieses Modul keine Zahlen bildet

Eine Social-Media-Textvorlage gab es schon einmal (Issue #16, v2.5.0); sie ist
in v4.0.5 zurückgebaut worden (``07682e14``). Mit ihr verschwand **N-7** — sie
trug eine **eigene** Netto-Ertrag-Kurzformel ohne §51, USt, BKW-Rest und
Grundpreis. Der Fund wurde nie behoben, er ist mit dem zweiten Text weggefallen.
**Genau das darf nicht wiederkommen**, und diesmal in einem Text, der öffentlich
gepostet wird.

Die Sicherung ist baulich, nicht disziplinarisch: Dieses Modul erzeugt den
Context aus **fertig formatierten Zeichenketten**; das Template schreibt sie
unverändert hin und rechnet nichts.

⭐ **Seit 2026-08-30 gibt es nur noch EINEN Renderer**, und das ist die stärkere
Fassung derselben Sicherung. Bis dahin stand daneben ein Markdown-Renderer für
den Forumspost, gehalten von der Probe „beide Formate, jede Zahl gleich". Mit
dem Entscheid, das Thema *Teilen* nicht zu verfolgen, ist sein Zweck entfallen
— und mit ihm die zweite Bildungsstelle, die es zu bewachen galt. Übrig bleibt
``test_das_template_schreibt_die_werte_unveraendert``: der Renderer darf eine
Zahl auf dem Weg nicht anfassen.

## Woher die Werte kommen

Ausschließlich aus zwei bestehenden Routen — dieses Modul faltet **nichts**
selbst (ADR-002/**P10**):

* ``api/routes/aktueller_monat.py::get_aktueller_monat`` — nimmt ``jahr`` und
  ``monat`` seit jeher als Parameter; die Datenschicht war für den Bericht
  bereits vollständig da.
* ``api/routes/cockpit/nachhaltigkeit.py::get_nachhaltigkeit`` — die CO₂-Zahlen.
  ⛔ **Nicht selbst rechnen:** ``berechne_co2_bilanz`` ist nach ADR-001/**DI-2**
  die einzige Konstruktions-Stelle, und der Wächter ``check:co2-roh`` hält die
  Client-Hälfte derselben Linie. Der Abruf entfällt, wenn das Thema abgewählt ist.

## Die zwei Ausnahmen, und warum sie benannt sind

Zwei Zahlen der Monatsansicht sind **Zusammensetzungen** aus gelieferten
Feldern und haben keinen Layer-SoT: die **SOLL-Erfüllung** (``lib/sollErfuellung.ts``)
und das **Monatsergebnis** (``v4/MonatBilanz.tsx::baueMonatKpis``). Beide stehen
im Bericht, weil eine Monatsansicht ohne sie nicht „im Stile der Cockpit
Monats Ansicht" ist — beide sind hier aus **gelieferten** Feldern gebildet, mit
den Wächtern der Client-Seite (``soll_pv_kwh <= 0 → keine Quote``; ``!= None``
statt Falsy, damit 0 € nicht verschwindet). Das ist eine **zweite
Bildungsstelle**, und sie ist als solche im Fundregister vermerkt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.services.pdf.formatierung import (
    LEER,
    fmt_einheit,
    fmt_euro,
    fmt_kwh,
    fmt_pct,
    fmt_zahl,
)

#: Die Themenschalter des Berichts (Konzept §2, Abnahme Punkt 1).
#: Reihenfolge = Reihenfolge im Dokument.
#:
#: ⚠ **Spiegel von** ``frontend/src/components/DokumentationsDialog.tsx::MONATSBERICHT_THEMEN``.
#: Die Verbindung war bis 2026-08-30 **nur ein Kommentar** — kein Test, keiner
#: der `check:*`. Drift hieß: ein Schalter, der still nichts tut, oder ein
#: Thema, das niemand wählen kann. Seither hält ``npm run check:spiegel-backend``
#: beide Listen zusammen.
THEMEN: tuple[str, ...] = ("energie", "komponenten", "finanzen", "co2", "community")

THEMA_LABELS: dict[str, str] = {
    "energie": "Energie",
    "komponenten": "Komponenten",
    "finanzen": "Finanzen",
    "co2": "CO₂",
    "community": "Community",
}

MONAT_NAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


@dataclass
class Zeile:
    """Eine Werte-Zeile. ``wert`` ist **fertig formatiert** — beide Renderer
    schreiben sie unverändert hin. Genau das ist die N-7-Sicherung."""
    label: str
    wert: str
    hinweis: Optional[str] = None


@dataclass
class Balken:
    """Ein Segment einer Anteils-Leiste.

    ``anteil`` ist der Breitenanteil in Prozent — **eine Darstellungsgröße**,
    keine Aussage: Jede Zahl, die der Bericht behauptet, steht als
    :class:`Zeile` daneben. Beide Renderer schreiben die Zeilen; nur das
    PDF zeichnet zusätzlich die Leiste.
    """
    label: str
    wert: str
    anteil: float
    farbe: str


@dataclass
class Abschnitt:
    """Ein Berichtsabschnitt.

    ``park_id`` ist der **Anker in die Monatsansicht**: die Park-ID der Anzeige,
    die diesen Abschnitt dort trägt. ``None`` = der Abschnitt hat in der Ansicht
    keine eigene parkbare Anzeige und wird nie unterdrückt.

    ⛔ **Der Anker steht am Abschnitt, nicht in einer Liste.** Die Park-Doktrin
    verbietet die statische Park-ID-Liste („IDs immer aus dem Render-Pfad
    ableiten, nie hart daneben"); eine solche Liste im Backend driftet beim
    ersten neuen Element, und ``check:park-leertest`` sähe sie nicht. Hier
    **zählt niemand die Park-IDs der Sicht auf** — jeder Abschnitt nennt nur
    seinen eigenen Anker, und der Client schickt, was bei ihm geparkt ist.
    Kommt in der Ansicht ein Element dazu, das der Bericht nicht kennt, fehlt
    hier nichts: es gibt dann keinen Abschnitt, den es ausblenden könnte.
    """
    schluessel: str
    titel: str
    thema: str
    zeilen: list[Zeile]
    park_id: Optional[str] = None
    hinweis: Optional[str] = None
    #: Wie das **PDF** diesen Abschnitt zeigt: ``"tabelle"`` (Vorgabe) oder
    #: ``"kacheln"``. Der Markdown-Renderer kennt nur Tabellen und ignoriert
    #: das Feld — die Zeilen sind in beiden Formaten dieselben, damit
    #: ``test_beide_formate_nennen_dieselben_zahlen`` unberührt bleibt.
    darstellung: str = "tabelle"
    #: Anteils-Leiste, nur PDF. Ihre Werte sind die Zeilen des Abschnitts.
    balken: Optional[list[Balken]] = None
    #: Fertiges SVG als ``data:``-URI, nur PDF.
    #:
    #: ⛔ **Das Chart entsteht hier im Builder, nie im Template** — ein Template,
    #: das rechnet, ist die zweite Bildungsstelle, gegen die dieses Modul gebaut
    #: ist (N-7). Ein Chart darf eine **Reihe zeigen**, über die der Bericht
    #: keine einzelne Zahl behauptet (30 Tage, 24 Stunden); seine **Aussagen**
    #: (bester Tag, Ø …) stehen als Zeilen und werden aus **derselben Liste**
    #: gebildet, die das Chart zeichnet.
    chart: Optional[str] = None


def _z(label: str, wert: str, hinweis: Optional[str] = None) -> Zeile:
    return Zeile(label=label, wert=wert, hinweis=hinweis)


def _hat(zeilen: Iterable[Zeile]) -> bool:
    """Trägt der Abschnitt mindestens einen echten Wert?

    F-43-Klasse: ein Abschnitt aus lauter Gedankenstrichen ist keine Aussage,
    sondern eine Seite Papier. Er entfällt, statt Leere zu drucken."""
    return any(z.wert not in (LEER, "", None) for z in zeilen)


# ─────────────────────────────────────────────────────────────────────────────
# Die zwei Zusammensetzungen — hier, damit sie EINEN Ort haben (s. Modul-Kopf)
# ─────────────────────────────────────────────────────────────────────────────

def soll_erfuellung_prozent(d: Any) -> Optional[float]:
    """Spiegel von ``lib/sollErfuellung.ts::sollErfuellungProzent``.

    Der ``<= 0``-Zweig ist nicht Kosmetik: ein SOLL von 0 (Monat in der Zukunft,
    null abgelaufene Tage) hat keine Erfüllungsquote — eine Division stünde dort
    als „∞ %"."""
    if d.soll_pv_kwh is None or d.pv_erzeugung_kwh is None or d.soll_pv_kwh <= 0:
        return None
    return d.pv_erzeugung_kwh / d.soll_pv_kwh * 100


def soll_fenster_text(d: Any) -> Optional[str]:
    """Spiegel von ``lib/sollErfuellung.ts::sollFensterText``.

    Ohne diesen Text behauptet die kWh-Zahl im laufenden Monat ein zu niedriges
    Monats-SOLL (N-69)."""
    if (
        d.soll_pv_tage is None
        or d.soll_pv_tage_gesamt is None
        or d.soll_pv_tage >= d.soll_pv_tage_gesamt
    ):
        return None
    return f"anteilig · {d.soll_pv_tage} von {d.soll_pv_tage_gesamt} Tagen"


def monatsergebnis_euro(d: Any) -> Optional[float]:
    """Spiegel von ``v4/MonatBilanz.tsx::baueMonatKpis`` („Monatsergebnis").

    ``is not None`` statt Falsy-Prüfung — sonst verschwände ein Ergebnis von
    0 € (CLAUDE.md, „0-Werte prüfen")."""
    if d.gesamtnettoertrag_euro is None:
        return None
    return (
        d.gesamtnettoertrag_euro
        - (d.betriebskosten_anteilig_euro or 0)
        + (d.sonstige_netto_euro or 0)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Abschnitte
# ─────────────────────────────────────────────────────────────────────────────

#: Die Felder, an denen sich entscheidet, ob der Monat überhaupt gemessen wurde.
#: **Bewusst eine ausgeschriebene Liste und kein „irgendein Wert ist gesetzt".**
#: Stammdaten (Speicherkapazität, Gerätenamen, kWp) liegen unabhängig vom Monat
#: vor; ein Bericht, der sie für einen Monat ohne jede Messung ausdruckt, sieht
#: gefüllt aus und ist leer. (`spez_ertrag` stand hier bis N-355 als zweites
#: Beispiel: er kam als 0.0 statt `None`, wenn keine PV vorlag. Das ist an der
#: Quelle behoben — der Fall gehört jetzt zur Liste, nicht zur Ausnahme.)
MESSFELDER: tuple[str, ...] = (
    "pv_erzeugung_kwh", "eigenverbrauch_kwh", "einspeisung_kwh",
    "netzbezug_kwh", "gesamtverbrauch_kwh",
    "speicher_ladung_kwh", "speicher_entladung_kwh",
    "wp_strom_kwh", "wp_waerme_kwh",
    "emob_ladung_kwh", "emob_km",
    "bkw_erzeugung_kwh",
    "sonstiges_erzeugung_kwh", "sonstiges_verbrauch_kwh",
)


def hat_messwerte(d: Any) -> bool:
    """Wurde in diesem Monat überhaupt etwas gemessen?"""
    return any(getattr(d, f, None) is not None for f in MESSFELDER)


def _abschnitte_energie(d: Any) -> list[Abschnitt]:
    aus: list[Abschnitt] = []

    kennzahlen = [
        _z("PV-Erzeugung", fmt_kwh(d.pv_erzeugung_kwh)),
        _z("Eigenverbrauch", fmt_kwh(d.eigenverbrauch_kwh)),
        _z("Einspeisung", fmt_kwh(d.einspeisung_kwh)),
        _z("Netzbezug", fmt_kwh(d.netzbezug_kwh)),
        _z("Gesamtverbrauch", fmt_kwh(d.gesamtverbrauch_kwh)),
        _z("Autarkie", fmt_pct(d.autarkie_prozent)),
        _z("Eigenverbrauchsquote", fmt_pct(d.eigenverbrauch_quote_prozent)),
        # ⚑ Ohne gemessene PV-Zahl liefert die Route hier `None`, nicht 0.0 —
        # seit **N-355**, der den Zähler-Zweig in `spezifischer_ertrag_kwh_kwp`
        # nachgezogen hat. Bis dahin stand an dieser Stelle eine eigene Sperre
        # im Bericht; sie ist mit dem Quell-Fix entfallen, statt als zweiter
        # Turm über demselben Sachverhalt stehenzubleiben.
        _z("Spezifischer Ertrag", fmt_einheit(d.spez_ertrag, "kWh/kWp", decimals=1)),
    ]
    if _hat(kennzahlen):
        # Der KPI-Strip der Monatsansicht — im PDF als Kachelreihe, im Markdown
        # als Tabelle. Dieselben Zeilen, zwei Darstellungen: `darstellung` ist
        # eine Anweisung ans Template, keine zweite Zahlenquelle.
        aus.append(Abschnitt("kennzahlen", "Kennzahlen", "energie", kennzahlen,
                             darstellung="kacheln"))

    # Vorjahresvergleich — die Anzeige dahinter ist „Vergleich (IST/VM/VJ)".
    vj = d.vorjahr or {}
    vergleich = [
        _z("PV-Erzeugung Vorjahr", fmt_kwh(vj.get("pv_erzeugung_kwh"))),
        _z("Eigenverbrauch Vorjahr", fmt_kwh(vj.get("eigenverbrauch_kwh"))),
        _z("Einspeisung Vorjahr", fmt_kwh(vj.get("einspeisung_kwh"))),
        _z("Netzbezug Vorjahr", fmt_kwh(vj.get("netzbezug_kwh"))),
        _z("Autarkie Vorjahr", fmt_pct(vj.get("autarkie_prozent"))),
    ]
    if _hat(vergleich):
        aus.append(Abschnitt(
            "vergleich", "Vergleich mit dem Vorjahresmonat", "energie", vergleich,
            park_id="el:bilanz-vergleich",
        ))

    fenster = soll_fenster_text(d)
    prognose = [
        _z("PVGIS-SOLL", fmt_kwh(d.soll_pv_kwh, 1), hinweis=fenster),
        _z("PVGIS-SOLL (ganzer Monat)", fmt_kwh(d.soll_pv_kwh_monat, 1)),
        _z("SOLL-Erfüllung", fmt_pct(soll_erfuellung_prozent(d)),
           hinweis="PV-Ertrag ÷ PVGIS-SOLL × 100"),
    ]
    if _hat(prognose):
        aus.append(Abschnitt(
            "prognose", "Prognose (PVGIS)", "energie", prognose,
            park_id="el:bilanz-monatsprognose",
            hinweis=(
                "Im laufenden Monat deckt das SOLL nur die abgelaufenen Tage ab."
                if fenster else None
            ),
        ))

    grundlast = [
        _z("Grundlast (Median Nacht)", fmt_einheit(d.grundlast_kw, "kW", decimals=3)),
        _z("Grundlast-Energie", fmt_kwh(d.grundlast_kwh)),
        _z("Anteil am Gesamtverbrauch", fmt_pct(d.grundlast_anteil_prozent)),
    ]
    if _hat(grundlast):
        aus.append(Abschnitt(
            "grundlast", "Grundlast", "energie", grundlast,
            park_id="el:bilanz-grundlast",
        ))

    verteilung = [
        _z("Direktverbrauch", fmt_kwh(d.direktverbrauch_kwh)),
        _z("Speicher-Entladung", fmt_kwh(d.speicher_entladung_kwh)),
        _z("Einspeisung", fmt_kwh(d.einspeisung_kwh)),
    ]
    if _hat(verteilung):
        # Die Leiste zeigt genau die drei Zeilen darüber — keine eigene Größe.
        posten = [
            ("Direktverbrauch", d.direktverbrauch_kwh, "#8b5cf6"),
            ("Speicher-Entladung", d.speicher_entladung_kwh, "#3b82f6"),
            ("Einspeisung", d.einspeisung_kwh, "#10b981"),
        ]
        gemessen = [(lab, float(v), farbe) for lab, v, farbe in posten if v]
        summe = sum(v for _, v, _ in gemessen)
        aus.append(Abschnitt(
            "pv_verteilung", "PV-Verteilung", "energie", verteilung,
            park_id="el:bilanz-verteilung",
            balken=([Balken(label=lab, wert=fmt_kwh(v), anteil=v / summe * 100, farbe=farbe)
                     for lab, v, farbe in gemessen] if summe > 0 else None),
        ))

    pv_geraete = [
        *(d.komponenten_geraete or {}).get("pv-module", []),
        *(d.komponenten_geraete or {}).get("wechselrichter", []),
    ]
    if len(pv_geraete) >= 2:
        # EINE Zeile statt einer Zeile je Gerät: Gerätenamen sind kein Wert, und
        # eine Tabellenspalte voller leerer Zellen liest sich in keinem der
        # beiden Formate.
        aus.append(Abschnitt(
            "pv_geraete", "PV-Erzeugung aus", "energie",
            [_z("Beteiligte Geräte", ", ".join(pv_geraete))],
            park_id="el:bilanz-geraete",
        ))

    return aus


def _abschnitte_komponenten(d: Any) -> list[Abschnitt]:
    aus: list[Abschnitt] = []

    if d.hat_speicher:
        speicher = [
            _z("Ladung", fmt_kwh(d.speicher_ladung_kwh)),
            _z("Entladung", fmt_kwh(d.speicher_entladung_kwh)),
            _z("Wirkungsgrad", fmt_pct(d.speicher_wirkungsgrad_prozent)),
            _z("Vollzyklen", fmt_zahl(d.speicher_vollzyklen, 2)),
            _z("Kapazität", fmt_kwh(d.speicher_kapazitaet_kwh, 1)),
            _z("Auslastung", fmt_pct(d.speicher_auslastung_prozent)),
            _z("Ersparnis", fmt_euro(d.speicher_ersparnis_euro)),
        ]
        if _hat(speicher):
            aus.append(Abschnitt("speicher", "Speicher", "komponenten", speicher))

        detail = [
            _z("Netzladung (Arbitrage)", fmt_kwh(d.speicher_ladung_netz_kwh)),
            _z("Kosten der Netzladung", fmt_euro(d.speicher_ladung_netz_kosten_euro)),
            _z("Preis der Netzladung",
               fmt_einheit(d.speicher_ladung_netz_preis_cent, "ct/kWh")),
        ]
        if _hat(detail):
            aus.append(Abschnitt(
                "speicher_detail", "Speicher — Details", "komponenten", detail,
                park_id="el:speicher-detail",
            ))

    if d.hat_waermepumpe:
        wp = [
            _z("Stromverbrauch", fmt_kwh(d.wp_strom_kwh)),
            _z("Wärmemenge", fmt_kwh(d.wp_waerme_kwh),
               hinweis="teilweise abgeleitet" if d.wp_waerme_abgeleitet else None),
            _z("Arbeitszahl", fmt_zahl(d.wp_jaz, 2),
               hinweis=d.wp_jaz_grund or d.wp_jaz_hinweis),
            _z("Ersparnis", fmt_euro(d.wp_ersparnis_euro)),
        ]
        if _hat(wp) or d.wp_jaz_grund:
            aus.append(Abschnitt("waermepumpe", "Wärmepumpe", "komponenten", wp))

        aufteilung = [
            _z("Wärme Heizung", fmt_kwh(d.wp_heizung_kwh)),
            _z("Wärme Warmwasser", fmt_kwh(d.wp_warmwasser_kwh)),
            _z("Arbeitszahl Heizen", fmt_zahl(d.wp_jaz_heizen, 2),
               hinweis=d.wp_jaz_heizen_grund),
            _z("Arbeitszahl Warmwasser", fmt_zahl(d.wp_jaz_warmwasser, 2),
               hinweis=d.wp_jaz_warmwasser_grund),
            _z("Arbeitszahl Kühlen", fmt_zahl(d.wp_jaz_kuehlen, 2),
               hinweis=d.wp_jaz_kuehlen_grund),
        ]
        if _hat(aufteilung):
            aus.append(Abschnitt(
                "wp_aufteilung", "Wärmepumpe — Wärme-Aufteilung", "komponenten",
                aufteilung, park_id="el:wp-aufteilung",
            ))

        strom = [
            _z("Strom Heizung", fmt_kwh(d.wp_strom_heizen_kwh)),
            _z("Strom Warmwasser", fmt_kwh(d.wp_strom_warmwasser_kwh)),
        ]
        if _hat(strom):
            aus.append(Abschnitt(
                "wp_strom", "Wärmepumpe — Strom-Aufteilung", "komponenten", strom,
                park_id="el:wp-detail",
            ))

        modus = [
            _z("Heizen", fmt_kwh(d.wp_modus_strom_heizen_kwh)),
            _z("Warmwasser", fmt_kwh(d.wp_modus_strom_warmwasser_kwh)),
            _z("Kühlen", fmt_kwh(d.wp_modus_strom_kuehlen_kwh)),
            _z("Lüften", fmt_kwh(d.wp_modus_strom_lueften_kwh)),
            _z("Entfeuchten", fmt_kwh(d.wp_modus_strom_entfeuchten_kwh)),
            _z("nicht aufgeteilt", fmt_kwh(d.wp_modus_nicht_aufgeteilt_kwh)),
        ]
        if _hat(modus):
            aus.append(Abschnitt(
                "wp_modus", "Wärmepumpe — Betriebsarten", "komponenten", modus,
                park_id="el:wp-modus-split",
                hinweis=(
                    "Teilmengen des Stromverbrauchs, keine Summanden."
                    + (" Gemessen." if d.wp_modus_gemessen else "")
                ),
            ))

    if d.hat_emobilitaet:
        emob = [
            _z("Ladung", fmt_kwh(d.emob_ladung_kwh)),
            _z("Gefahrene Kilometer", fmt_einheit(d.emob_km, "km", decimals=0)),
            _z("Ø Verbrauch", fmt_einheit(d.emob_verbrauch_100km, "kWh/100 km", decimals=1)),
            _z("Ersparnis", fmt_euro(d.emob_ersparnis_euro)),
        ]
        if _hat(emob):
            aus.append(Abschnitt("emob", "E-Mobilität", "komponenten", emob))

        herkunft = [
            _z("Ladung aus PV", fmt_kwh(d.emob_ladung_pv_kwh)),
            _z("Ladung aus dem Netz", fmt_kwh(d.emob_ladung_netz_kwh)),
            _z("Ladung extern", fmt_kwh(d.emob_ladung_extern_kwh)),
            _z("V2H-Rückspeisung", fmt_kwh(d.emob_v2h_kwh)),
        ]
        if _hat(herkunft):
            aus.append(Abschnitt(
                "emob_herkunft", "E-Mobilität — Lade-Herkunft", "komponenten",
                herkunft, park_id="el:emob-detail",
            ))

    if d.hat_balkonkraftwerk:
        bkw = [
            _z("Erzeugung", fmt_kwh(d.bkw_erzeugung_kwh)),
            _z("Eigenverbrauch", fmt_kwh(d.bkw_eigenverbrauch_kwh)),
        ]
        if _hat(bkw):
            aus.append(Abschnitt("bkw", "Balkonkraftwerk", "komponenten", bkw))

    if d.hat_sonstiges:
        sonstiges: list[Zeile] = []
        for g in d.sonstiges_geraete or []:
            if g.kategorie == "erzeuger":
                sonstiges.append(_z(
                    g.bezeichnung,
                    f"{fmt_kwh(g.erzeugung_kwh)} erzeugt",
                    hinweis=f"Eigenverbrauch {fmt_kwh(g.eigenverbrauch_kwh)} · "
                            f"Einspeisung {fmt_kwh(g.einspeisung_kwh)}",
                ))
            else:
                sonstiges.append(_z(
                    g.bezeichnung,
                    f"{fmt_kwh(g.verbrauch_kwh)} verbraucht",
                    hinweis=f"aus PV {fmt_kwh(g.bezug_pv_kwh)} · "
                            f"aus Netz {fmt_kwh(g.bezug_netz_kwh)}",
                ))
        if sonstiges:
            aus.append(Abschnitt("sonstiges", "Sonstiges", "komponenten", sonstiges))

    return aus


def _abschnitte_finanzen(d: Any) -> list[Abschnitt]:
    aus: list[Abschnitt] = []

    bilanz = [
        _z("Einspeise-Erlös", fmt_euro(d.einspeise_erloes_euro)),
        _z("Eigenverbrauchs-Ersparnis", fmt_euro(d.ev_ersparnis_euro)),
        _z("Netzbezugskosten", fmt_euro(d.netzbezug_kosten_euro)),
        _z("davon Grundgebühr", fmt_euro(d.grundgebuehr_euro)),
        _z("Netto-Ertrag", fmt_euro(d.netto_ertrag_euro),
           hinweis="vor Betriebskosten"),
        _z("Gesamt-Nettoertrag", fmt_euro(d.gesamtnettoertrag_euro),
           hinweis="Erlöse + Einsparungen − Kosten"),
        _z("Betriebskosten (anteilig)", fmt_euro(d.betriebskosten_anteilig_euro)),
        _z("Sonstige Positionen (netto)", fmt_euro(d.sonstige_netto_euro)),
        _z("Monatsergebnis", fmt_euro(monatsergebnis_euro(d)),
           hinweis="Gesamt-Nettoertrag − Betriebskosten + Sonstiges"),
    ]
    if d.nicht_vergueteter_erloes_euro is not None:
        bilanz.append(_z(
            "§51 EEG — entgangener Erlös",
            fmt_euro(d.nicht_vergueteter_erloes_euro),
            hinweis=f"{fmt_kwh(d.einspeisung_neg_preis_kwh, 1)} zu Negativpreisen",
        ))
    if _hat(bilanz):
        # Die Tarif-Zeile ist eine ANNOTATION zur Bilanz und parkt MIT ihr
        # (Gernot 2026-07-09, `v4/MonatRahmen.tsx::finanzTeaserBlock`).
        preis_hinweis = "gewichtet über die Zeitfenster" if d.netzbezug_preis_zeittarif else None
        if d.netzbezug_durchschnittspreis_cent is not None:
            bilanz.append(_z(
                "Netzbezugspreis Ø",
                fmt_einheit(d.netzbezug_durchschnittspreis_cent, "ct/kWh"),
                hinweis="dynamischer Tarif",
            ))
        elif d.netzbezug_preis_cent is not None:
            bilanz.append(_z(
                "Netzbezugspreis",
                fmt_einheit(d.netzbezug_preis_cent, "ct/kWh"),
                hinweis=preis_hinweis,
            ))
        if d.einspeise_preis_cent is not None:
            bilanz.append(_z(
                "Einspeisevergütung",
                fmt_einheit(d.einspeise_preis_cent, "ct/kWh"),
            ))
        aus.append(Abschnitt(
            "finanzen", "Finanzen", "finanzen", bilanz,
            park_id="el:finanzen-bilanz",
        ))

    return aus


def _abschnitte_co2(monat: Any) -> list[Abschnitt]:
    """CO₂ — die Werte kommen fertig aus ``/cockpit/nachhaltigkeit``.

    ``monat`` ist die ``NachhaltigkeitMonat``-Zeile des Berichtsmonats oder
    ``None``. Ein fehlender Monat heißt: Die CO₂-Zeitreihe kennt ihn nicht
    (``_hat_substanz`` dort) — dann steht kein Abschnitt da, keine Null.
    """
    if monat is None:
        return []
    zeilen = [
        _z("Eingespart gesamt", fmt_einheit(monat.co2_gesamt_kg, "kg", decimals=1)),
        _z("davon PV", fmt_einheit(monat.co2_pv_kg, "kg", decimals=1)),
        _z("davon Wärmepumpe", fmt_einheit(monat.co2_wp_kg, "kg", decimals=1)),
        _z("davon E-Mobilität", fmt_einheit(monat.co2_emob_kg, "kg", decimals=1)),
        _z("Kumuliert bis einschließlich dieses Monats",
           fmt_einheit(monat.co2_kumuliert_kg, "kg", decimals=1)),
    ]
    return [Abschnitt("co2", "CO₂-Bilanz", "co2", zeilen)]


# ─────────────────────────────────────────────────────────────────────────────
# Der Context
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Die grafisch aufbereiteten Abschnitte (Stufe 2)
#
# Sie speisen sich aus zwei Quellen, die `AktuellerMonatResponse` NICHT trägt —
# gemessen am 30.08. (`typisches_tagesprofil` · `peak_*` · `kategorien`: je 0
# Treffer in `aktueller_monat.py`). Das Konzept behauptete das Gegenteil; der
# erste Bau ist dem Satz gefolgt und hat sechs von vierzehn Anzeigen der
# Monatsfläche ausgelassen.
# ─────────────────────────────────────────────────────────────────────────────

def _abschnitt_verlauf(tage: list[Any], tage_im_monat: int) -> Optional[Abschnitt]:
    """Tagesverlauf des Monats — Aussagen als Zeilen, die Reihe als Chart.

    ``TagWerteResponse.erzeugung`` ist ``Optional``: ``None`` heißt „an diesem
    Tag hat kein Erzeuger einen kWh-Wert getragen". Ein solcher Tag geht
    **weder in den Ø noch als Null-Balken** ins Chart — sonst behauptete der
    Bericht einen Ertragseinbruch, wo nur die Messung fehlt.
    """
    from backend.services.pdf.charts import tagesverlauf_chart

    tagnummern = [t.datum.day for t in tage]
    erzeugung = [t.erzeugung for t in tage]
    verbrauch = [t.gesamtverbrauch for t in tage]
    gemessen = [(t.datum.day, t.erzeugung) for t in tage if t.erzeugung is not None]
    if not gemessen:
        return None

    bester = max(gemessen, key=lambda x: x[1])
    schwaechster = min(gemessen, key=lambda x: x[1])
    schnitt = sum(v for _, v in gemessen) / len(gemessen)

    zeilen = [
        _z("Bester Tag", f"{bester[0]}. · {fmt_kwh(bester[1], 1)}"),
        _z("Schwächster Tag", f"{schwaechster[0]}. · {fmt_kwh(schwaechster[1], 1)}"),
        _z("Ø je Tag", fmt_kwh(schnitt, 1)),
        # ⛔ Der Nenner ist die Länge des MONATS, nicht die Zahl der gelieferten
        # Zeilen: `baue_tage_werte` gibt nur Tage zurück, die Daten tragen. Mit
        # `len(tage)` stand hier an echten Daten „23 von 23" — eine Aussage, die
        # per Konstruktion immer aufgeht und deshalb keine ist. `tage_im_monat`
        # kommt aus `get_monatsauswertung` (dort der SoT), nicht aus einer
        # eigenen Kalenderrechnung.
        _z("Tage mit gemessener Erzeugung", f"{len(gemessen)} von {tage_im_monat}"),
    ]
    return Abschnitt(
        "verlauf", "Verlauf", "energie", zeilen,
        park_id="el:verlauf",
        chart=tagesverlauf_chart(tagnummern, erzeugung, verbrauch),
        hinweis=(
            None if len(gemessen) >= tage_im_monat
            else "Tage ohne gemessene Erzeugung sind ausgelassen, nicht als 0 gezählt."
        ),
    )


def _abschnitte_kategorien(kategorien: list[Any]) -> list[Abschnitt]:
    """Erzeugung und Verbrauch nach Kategorie — je eine Anteils-Leiste."""
    from backend.api.routes.energie_profil.views import ENERGIE_KATEGORIEN

    aus: list[Abschnitt] = []
    gruppen = (
        ("kategorien_erzeugung", "Erzeugung nach Kategorie", "erzeuger",
         "el:kategorien-erzeugung"),
        ("kategorien_verbrauch", "Verbrauch nach Kategorie", "verbraucher",
         "el:kategorien-verbrauch"),
    )
    for schluessel, titel, gruppe, park_id in gruppen:
        posten = [
            k for k in kategorien
            if k.kategorie in ENERGIE_KATEGORIEN
            and ENERGIE_KATEGORIEN[k.kategorie][1] == gruppe
            and abs(k.kwh) > 0
        ]
        if not posten:
            continue
        summe = sum(abs(k.kwh) for k in posten) or 1.0
        zeilen = [
            _z(ENERGIE_KATEGORIEN[k.kategorie][0], fmt_kwh(abs(k.kwh)),
               hinweis=(fmt_pct(k.anteil_prozent) if k.anteil_prozent is not None else None))
            for k in posten
        ]
        # ⛔ Die Farbe kommt aus der Kategorie, nicht aus der Reihenfolge: Ein
        # Palettenindex hätte derselben Kategorie je nach Datenlage einen
        # anderen Ton gegeben — Regel 0a verlangt das Gegenteil.
        balken = [
            Balken(
                label=ENERGIE_KATEGORIEN[k.kategorie][0],
                wert=fmt_kwh(abs(k.kwh)),
                anteil=abs(k.kwh) / summe * 100,
                farbe=ENERGIE_KATEGORIEN[k.kategorie][2],
            )
            for k in posten
        ]
        aus.append(Abschnitt(schluessel, titel, "energie", zeilen,
                             park_id=park_id, balken=balken))
    return aus


def _abschnitt_tagesprofil(profil: list[Any]) -> Optional[Abschnitt]:
    """Typisches Tagesprofil — Ø-Leistung je Stunde über den Monat."""
    from backend.services.pdf.charts import tagesprofil_chart

    if not profil:
        return None
    stunden = [p.stunde for p in profil]
    pv = [p.pv_kw for p in profil]
    verbrauch = [p.verbrauch_kw for p in profil]
    pv_gemessen = [(p.stunde, p.pv_kw) for p in profil if p.pv_kw is not None]
    verb_gemessen = [v for v in verbrauch if v is not None]
    if not pv_gemessen and not verb_gemessen:
        return None

    zeilen: list[Zeile] = []
    if pv_gemessen:
        spitze = max(pv_gemessen, key=lambda x: x[1])
        zeilen.append(_z("PV-Spitze (Ø)", f"{spitze[0]}:00 Uhr · "
                                          f"{fmt_einheit(spitze[1], 'kW', decimals=2)}"))
    if verb_gemessen:
        zeilen.append(_z("Verbrauch Ø", fmt_einheit(
            sum(verb_gemessen) / len(verb_gemessen), "kW", decimals=2)))
        zeilen.append(_z("Verbrauchs-Spitze (Ø)", fmt_einheit(
            max(verb_gemessen), "kW", decimals=2)))
    return Abschnitt(
        "tagesprofil", "Typisches Tagesprofil", "energie", zeilen,
        park_id="el:tagesprofil",
        chart=tagesprofil_chart(stunden, pv, verbrauch),
        hinweis="Stundenmittel über alle Tage des Monats.",
    )


def _abschnitte_peaks(auswertung: Any) -> list[Abschnitt]:
    """Spitzenstunden — je eine Zeile pro Stunde, in beiden Formaten."""
    aus: list[Abschnitt] = []
    paare = (
        ("peak_netzbezug", "Top Netzbezug-Stunden", auswertung.peak_netzbezug,
         "el:peak-netzbezug"),
        ("peak_einspeisung", "Top Einspeise-Stunden", auswertung.peak_einspeisung,
         "el:peak-einspeisung"),
    )
    for schluessel, titel, stunden, park_id in paare:
        posten = list(stunden or [])[:5]
        if not posten:
            continue
        zeilen = [
            _z(f"{p.datum.strftime('%d.%m.')} · {p.stunde}:00 Uhr",
               fmt_einheit(p.wert_kw, "kW", decimals=2))
            for p in posten
        ]
        aus.append(Abschnitt(schluessel, titel, "energie", zeilen, park_id=park_id))
    return aus


def _abschnitt_community(vergleich: Optional[dict], d: Any) -> Optional[Abschnitt]:
    """Community-Vergleich für den Berichtsmonat.

    ⛔ **Kein Stand-Datum** (Entscheid Gernot, 30.08.): Der Vergleichsmonat *ist*
    der Berichtsmonat, damit ist der Vergleich definiert — wann er gezogen wurde,
    ändert die Aussage nicht. Mitgenommen wird die **Anzahl der verglichenen
    Anlagen**: ein Vergleich gegen 3 Anlagen ist etwas anderes als gegen 300.

    ⚠ Diese Anzeige gibt es auf *Cockpit → Monat* **nicht** — sie wurde dort mit
    ``748849b2`` bewusst durch einen Cross-Link zur Community-Achse ersetzt. Der
    Abschnitt steht hier auf Gernots Vorgabe (30.08.), nicht als Übernahme vom
    Bildschirm; ``park_id`` bleibt deshalb ``None``, denn eine nie gerenderte
    Anzeige kann niemand parken.
    """
    if not vergleich:
        return None
    anzahl = vergleich.get("anzahl_anlagen") or 0
    if anzahl <= 0:
        return None

    def _median(feld: str) -> Optional[float]:
        eintrag = vergleich.get(feld)
        return eintrag.get("median") if isinstance(eintrag, dict) else None

    posten = (
        ("Spezifischer Ertrag", d.spez_ertrag, _median("spez_ertrag"),
         lambda v: fmt_einheit(v, "kWh/kWp", decimals=1)),
        ("Autarkie", d.autarkie_prozent, _median("autarkie"), fmt_pct),
        ("Eigenverbrauchsquote", d.eigenverbrauch_quote_prozent,
         _median("eigenverbrauch"), fmt_pct),
        ("Einspeisung", d.einspeisung_kwh, _median("einspeisung"), fmt_kwh),
        ("Netzbezug", d.netzbezug_kwh, _median("netzbezug"), fmt_kwh),
    )
    zeilen: list[Zeile] = []
    for label, eigen, median, formatierer in posten:
        if eigen is None and median is None:
            continue
        zeilen.append(_z(
            label,
            formatierer(eigen),
            hinweis=(f"Community-Median {formatierer(median)}"
                     if median is not None else "kein Community-Median"),
        ))
    if not _hat(zeilen):
        return None

    zeilen.append(_z("Verglichene Anlagen", fmt_zahl(anzahl, 0)))
    return Abschnitt(
        "community", "Community-Vergleich", "community", zeilen,
        hinweis="Median aller Anlagen, die ihre Werte für diesen Monat geteilt haben.",
    )


def _logo_data_url() -> str:
    """eedc-Logo als ``data:``-URI — **dasselbe Muster** wie
    ``builders/anlagendokumentation.py:248``. Fehlt die Datei, bleibt der Kopf
    ohne Logo; das Markenband trägt die Identität ohnehin auf jeder Seite."""
    import base64
    from pathlib import Path as _Path

    pfad = _Path(__file__).resolve().parents[4] / "logo.png"
    if not pfad.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(pfad.read_bytes()).decode("ascii")


async def _energie_aufbereitet(
    db: AsyncSession, anlage: Anlage, jahr: int, monat: int,
) -> list[Abschnitt]:
    """Verlauf · Kategorien · Tagesprofil · Spitzenstunden.

    Zwei Quellen, beide bestehend — dieses Modul faltet nichts selbst
    (ADR-002/**P10**):

    * :func:`get_monatsauswertung` — die Logik liegt in der Route, es gibt
      keinen Service darunter; direkt aufgerufen mit gesetzten Argumenten,
      dasselbe Muster wie ``get_aktueller_monat`` oben.
    * :func:`baue_tage_werte` — hier bewusst der **Service** statt der Route
      ``get_tage_werte``: die tut nichts weiter, als ihn nach einer
      Anlagenprüfung aufzurufen, die hier schon geschehen ist.
    """
    import calendar

    from backend.api.routes.energie_profil.views import get_monatsauswertung
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    aus: list[Abschnitt] = []

    auswertung = await get_monatsauswertung(anlage.id, jahr, monat, 10, db)

    letzter = calendar.monthrange(jahr, monat)[1]
    tage = await baue_tage_werte(db, anlage, date(jahr, monat, 1), date(jahr, monat, letzter))
    verlauf = _abschnitt_verlauf(list(tage or []), auswertung.tage_im_monat or letzter)
    if verlauf is not None:
        aus.append(verlauf)

    aus += _abschnitte_kategorien(list(auswertung.kategorien or []))
    profil = _abschnitt_tagesprofil(list(auswertung.typisches_tagesprofil or []))
    if profil is not None:
        aus.append(profil)
    aus += _abschnitte_peaks(auswertung)
    return aus


async def _community_vergleich(jahr: int, monat: int) -> Optional[dict]:
    """Monats-Benchmark vom Community-Server — oder ``None``.

    ⛔ **Der Bericht darf daran nicht scheitern** (ADR-002/**P4**). Die Quelle
    ist ``api/routes/community.py::get_monatsbenchmark``, und das ist ein
    ``httpx``-Aufruf an einen **externen** Server: nicht erreichbar, langsam,
    ohne Daten für den Monat, 5xx — jeder dieser Fälle ist normal und keiner
    davon kostet die übrigen fünfzehn Abschnitte. Der Abschnitt entfällt dann,
    statt mit Gedankenstrichen dazustehen.
    """
    from backend.api.routes.community import get_monatsbenchmark

    try:
        return await get_monatsbenchmark(jahr, monat)
    except Exception:  # noqa: BLE001 — jeder Fehlschlag bedeutet dasselbe: kein Abschnitt
        return None


async def build_monatsbericht_context(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
    *,
    themen: Optional[Iterable[str]] = None,
    geparkte_ids: Iterable[str] = (),
) -> dict:
    """Context für ``templates/monatsbericht.html``.

    Args:
        themen: Auswahl aus :data:`THEMEN`. ``None`` = alle.
        geparkte_ids: Park-IDs, die der Client aus seinem ``localStorage``
            mitschickt (``eedc-park:v4-cockpit-monat``). Leer = vollständiger
            Bericht — das ist der Fall „anderer Browser" und darf **nichts**
            weglassen.

    ⛔ **Anlagenname und Standort stehen immer drin.** Bis 2026-08-30 gab es
    dafür einen Schalter; seine Begründung war der Forumspost („wer teilt,
    schaltet ab"). Mit dem Entscheid, das Thema *Teilen* nicht zu verfolgen,
    ist sie entfallen — der Bericht nennt die Anlage wie jeder andere Bericht
    dieser Anlage auch. „Anonymisiert" war und bleibt **kein** Angebot: ein
    PV-Monatsbericht ist über Ertragsprofil, Standort und Tarif praktisch
    eindeutig; der anonyme Weg ist der Community-Hash.

    Raises:
        LookupError: Die Anlage gibt es nicht.
    """
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if anlage is None:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")

    aktive_themen = list(THEMEN) if themen is None else [t for t in THEMEN if t in set(themen)]
    geparkt = set(geparkte_ids)

    # Lazy, damit der Import-Graph dieses Moduls nicht die halbe API zieht.
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    d = await get_aktueller_monat(anlage_id, jahr, monat, db)

    # F-43-Klasse: ohne eine einzige Messung wird KEIN Abschnitt gebaut. Sonst
    # druckte der Bericht Stammdaten (Speicherkapazität, Gerätenamen) unter
    # Überschriften, die eine Messung versprechen — und einen spezifischen
    # Ertrag von „0,0 kWh/kWp" neben einer PV-Erzeugung „–".
    # ⚠ Die Themenauswahl bleibt davon unberührt: der Anwender hat sie getroffen,
    # und der Bericht sagt weiter, wonach er gefragt wurde.
    abschnitte: list[Abschnitt] = []
    if hat_messwerte(d):
        if "energie" in aktive_themen:
            abschnitte += _abschnitte_energie(d)
            abschnitte += await _energie_aufbereitet(db, anlage, jahr, monat)
        if "komponenten" in aktive_themen:
            abschnitte += _abschnitte_komponenten(d)
        if "finanzen" in aktive_themen:
            abschnitte += _abschnitte_finanzen(d)
        if "co2" in aktive_themen:
            from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
            nachhaltigkeit = await get_nachhaltigkeit(anlage_id, db)
            zeile = next(
                (m for m in nachhaltigkeit.monatswerte
                 if m.jahr == jahr and m.monat == monat),
                None,
            )
            abschnitte += _abschnitte_co2(zeile)
        if "community" in aktive_themen:
            gemeinschaft = await _community_vergleich(jahr, monat)
            abschnitt = _abschnitt_community(gemeinschaft, d)
            if abschnitt is not None:
                abschnitte.append(abschnitt)

    # ⚑ Erst bauen, dann filtern. Ein geparktes Element blendet aus, es rechnet
    # nicht um — die Zahlen der übrigen Abschnitte dürfen sich dadurch nicht
    # ändern. Beim Filtern NACH dem Bau ist das baulich sicher statt geprüft.
    sichtbar = [a for a in abschnitte if a.park_id is None or a.park_id not in geparkt]
    weggelassen = [a.titel for a in abschnitte if a.park_id is not None and a.park_id in geparkt]

    standort_teile = [anlage.standort_plz, anlage.standort_ort]
    standort = " ".join(t for t in standort_teile if t)

    return {
        "logo": _logo_data_url(),
        "anlage": {
            "name": anlage.anlagenname,
            "standort": standort,
            "leistung_kwp": fmt_einheit(anlage.leistung_kwp, "kWp"),
        },
        "zeitraum": {
            "jahr": jahr,
            "monat": monat,
            "label": f"{MONAT_NAMEN[monat]} {jahr}",
        },
        "themen": aktive_themen,
        "thema_labels": THEMA_LABELS,
        "abschnitte": sichtbar,
        "weggelassen": weggelassen,
        "hinweise": list(d.hinweise or []),
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "leer": len(sichtbar) == 0,
    }
