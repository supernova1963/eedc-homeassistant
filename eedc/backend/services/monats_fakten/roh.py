"""Monats-Fakten — der Rohmonat: `_RohMonat` faltet die geladenen `InvestitionMonatsdaten` einer Anlage je Monat
(`falte`), die Lader holen den Query-Satz, die Fensterhelfer schneiden von/bis.
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen import (
    abdeckung_ueber_geraete,
    bkw_finanz_beitrag,
    ersetzt_keine_heizung,
    imd_typ_beitrag,
)
from backend.core.investition_parameter import (
    PARAM_WAERMEPUMPE,
    ist_dienstlich,
    ist_luft_luft_waermepumpe,
)
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.emob_ladeanteil import braucht_tages_quote, hat_gepflegten_pv_anteil
from backend.core.field_definitions import ist_heim_gesamt
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.services.monats_fakten.fakten import MonatsSchluessel


#: Typen, die hinter denselben Hauszähler speisen und deshalb ein
#: „PV-Fenster" öffnen (Anschaffungsdatum-Grenze, s. `MetaFakten.erzeuger_aktiv`).
_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")

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
        self.wp_strom_nicht_aufgeteilt = 0.0
        self.wp_waerme = 0.0
        self.wp_strom_mit_ersatz = 0.0
        self.wp_waerme_mit_ersatz = 0.0
        self.wp_heizung = 0.0
        self.wp_warmwasser = 0.0
        self.wp_strom_heizen = 0.0
        self.wp_strom_warmwasser = 0.0
        self.wp_hat_split = False
        #: N-479: hat **mindestens ein** Gerät des Monats die Größe gemessen —
        #: unabhängig davon, ob dabei 0 herauskam? Das ``sum()`` darunter kann
        #: die Frage nicht beantworten, weil eine gemessene Null und ein
        #: fehlender Zähler beide 0.0 beitragen. Ohne diese vier Marken meldet
        #: der Monat im Sommer den Ausstattungs-Grund („kein Wärmemengenzähler
        #: zugeordnet") statt des Zeitraum-Grunds („kein Heizbetrieb").
        self.wp_heizung_gemessen = False
        self.wp_warmwasser_gemessen = False
        self.wp_strom_heizen_gemessen = False
        self.wp_strom_warmwasser_gemessen = False
        #: N-391: mindestens ein Gerät des Monats misst die Wärme mit EINEM
        #: gemeinsamen Zähler (Feld ``waerme_kwh``).
        self.wp_waerme_ist_gesamt = False
        self.wp_modus_strom_heizen = 0.0
        self.wp_modus_strom_kuehlen = 0.0
        #: N-336 — nur aus dem abgeleiteten Split; die Gegenrichtung zu E4.
        self.wp_modus_strom_warmwasser = 0.0
        #: E4 — nur aus gemessenen Zaehlern; der abgeleitete Split kann sie nicht.
        self.wp_modus_strom_lueften = 0.0
        self.wp_modus_strom_entfeuchten = 0.0
        #: SOLL-§9-E7/Option A — je Zeile entschieden, hier nur summiert.
        self.wp_modus_strom_funktionsfremd_abzug = 0.0
        #: W-5 — die Kältemenge, nur gemessen.
        self.wp_nutzenergie_kuehlen = 0.0
        #: R-C/N-398 — die zwei Mengen ohne Kennzahl (E4).
        self.wp_nutzenergie_lueften = 0.0
        self.wp_nutzenergie_entfeuchten = 0.0
        self.wp_modus_abdeckung_h = 0.0
        #: #263 — mindestens ein Gerät bringt die Aufteilung GEMESSEN mit.
        self.wp_modus_gemessen = False
        self.wp_modus_strom_bezug = 0.0
        self.wp_waerme_abgeleitet = 0.0
        # ── R2/Gerät: Zählt der Block Geräte, die keine Wärme melden? ───────
        #
        # SOLL §4.2 Fall 1: *„Wenn der Zähler mehr enthält als das Gerät."*
        # Der Block *Wärme/Klima* aggregiert **alle** Wärmepumpen der Anlage —
        # bei dietmar1968 ausweislich seines eigenen Screenshots „Aggregiert
        # aus: Wärmepumpe · Klimaanlage". Meldet nur eines der beiden Geräte
        # Wärme, steht im Nenner der Strom von zwei Geräten und im Zähler die
        # Wärme von einem. Die Arbeitszahl ist dann systematisch zu niedrig.
        #
        # ⭐ **Das ist die einzige der vier §4.2-Lagen, die eedc aus den Daten
        # SELBST erkennen kann** — sie braucht keine Angabe des Anwenders. Die
        # übrigen drei (Heizstab am Zähler, bivalenter Zweiterzeuger,
        # Zeitraum-Versatz) sind von außen nicht sichtbar.
        #
        # ⛔ **Mengen von `Investition.id`, keine Anzahlen (N-441, 12.09.2026).**
        # Zwei Anzahlen sagen nur, wie VIELE Geräte je Seite beitragen — nicht,
        # ob es dieselben sind. Wärme von A und Strom von B ergab `1 == 1` und
        # damit „deckungsgleich": **3,0 ohne Grund**, als belastbar an die
        # Community.
        self.wp_geraete_mit_strom: set[int] = set()
        self.wp_geraete_mit_waerme: set[int] = set()
        # R2/Bauart (SOLL §5): Wie viele der stromtragenden Geräte sind
        # Split-Klimaanlagen (Luft-Luft), wie viele klassische Wärmepumpen?
        # Stehen BEIDE im Block, gibt es keine gemeinsame Kennzahl.
        self.wp_geraete_luft_luft = 0
        self.wp_geraete_luft_wasser = 0
        # ── R2 JE FUNKTION (10.09.2026) ────────────────────────────────────
        # Wie viele Geraete tragen den **Strom** einer Funktion bei, wie viele
        # ihre **Waerme**? Sind es dieselben (Mengengleichheit), ist die
        # Funktion sauber abgegrenzt und ihre Kennzahl darf erscheinen — auch
        # wenn der Block als GANZES gemischt ist.
        #
        # ⭐ **Beidseitig, und das ist der Kern.** Eine einseitige Regel
        # („jedes Geraet mit Strom liefert auch Waerme") faengt nur den Nenner.
        # Der Zaehler kippt genauso: `heizenergie_kwh` traegt NUR
        # `!brauchwasser` (field_definitions/registry.py::INVESTITION_FELDER), eine Split-Klima darf
        # also Heizwaerme melden. Meldet sie welche, ohne Heizstrom
        # beizusteuern, waere die Heiz-Arbeitszahl zu HOCH — gemessen an der
        # A8-Bauform 4,25 statt 3,75.
        #
        # ⛔ Und die Gegenrichtung ist kein Papierfall: `strom_warmwasser_kwh`
        # wird **ungefiltert** gelesen (imd_monatsaggregat.py:276, mit
        # ausdruecklicher Begruendung), und bis 22.08.2026 wurde das Feld einer
        # Klimaanlage mit getrennter Strommessung angeboten. Altbestand steht
        # dort also, ohne Waerme daneben.
        self.wp_geraete_e_heizen: set[int] = set()
        self.wp_geraete_q_heizen: set[int] = set()
        self.wp_geraete_e_warmwasser: set[int] = set()
        self.wp_geraete_q_warmwasser: set[int] = set()
        self.wp_geraete_e_kuehlen: set[int] = set()
        self.wp_geraete_q_kuehlen: set[int] = set()
        #: R2/W-7 + R2/F12: die Abgrenzungs-Störung des Blocks. **Sobald EIN
        #: Gerät gestört ist, ist der Block gestört** — dieselbe Faltung wie
        #: `wp_hat_split`. Ein Block, der Strom eines Geräts mit Heizstab am
        #: Zähler trägt, hat keine belastbare Gesamt-Arbeitszahl, auch wenn das
        #: zweite Gerät sauber misst.
        self.wp_abgrenzung: Optional[str] = None
        #: N-609: je ``Investition.id`` ``[strom, wärme, kühlstrom]`` — dieselben Beiträge wie die Summen.
        self.wp_je_geraet: dict[int, list[float]] = {}
        self.eauto_ladedaten: list[dict] = []
        #: N-555: dieselben E-Auto-Zeilen je ``Investition.id`` — die eine Funktion
        #: (``entscheide_emob_heimladung``) entscheidet je Auto, und ihre Schätzung
        #: ist je Auto. Parallel zu ``eauto_ladedaten`` (gleiche Reihenfolge).
        self.eauto_ladedaten_ids: list[int] = []
        self.wallbox_ladedaten: list[dict] = []
        self.wallbox_ladedaten_ids: list[int] = []
        #: N-555: Dienstwagen und dienstliche Wallboxen je ``Investition.id`` —
        #: ihre Menge rechnet jetzt die eine Funktion (bitgleich), nicht mehr diese
        #: Faltung über die Lese-Hilfe mit ihrem stillen Fahrverbrauch-Ersatz.
        self.dienstlich_je_inv: dict[int, dict] = {}
        #: N-555 Stufe 2 (Regel 3): welche der dienstlichen Zeilen eine **Wallbox** ist —
        #: ihre Menge ist die dienstliche Ladung; ein Dienstwagen daneben zählt nicht.
        self.dienstliche_wallbox_ids: set[int] = set()
        #: N-555 Stufe 2 (Regel 8, E5): E-Autos (privat und dienstlich), deren
        #: ``ladung_kwh`` „Heim: gesamt" ist — Herkunft weder fehlend noch ``legacy:unknown``
        #: (``field_definitions.ist_heim_gesamt``). Der alte Gesamtwert zählt nur ohne Wallbox.
        self.heim_gesamt_ids: set[int] = set()
        self.eauto_km = 0.0
        self.eauto_km_je_fahrzeug: dict[int, float] = {}
        self.eauto_fahrverbrauch_je_fahrzeug: dict[int, float] = {}
        self.eauto_fahrverbrauch = 0.0
        self.eauto_v2h = 0.0
        self.sonstiges_erzeugung = 0.0
        self.sonstiges_verbrauch = 0.0
        self.sonstiges_eigenverbrauch = 0.0
        self.sonstiges_einspeisung = 0.0
        self.sonstiges_bezug_pv = 0.0
        self.sonstiges_bezug_netz = 0.0
        self.sonstiges_einspeise_erloes_euro = 0.0
        self.sonstiges_abgabe = 0.0
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
        # N-555 Stufe 2 (S2-4): die Ableitung gilt je Zeile — die Vorprüfung fragt beides.
        # Die monatsweise Frage bleibt, damit kein Monat seine Tagesebene verliert, den sie
        # bisher geladen hat (die Tagesebene füllt dann auch andere Lücken, s. `laden.py`).
        return not hat_gepflegten_pv_anteil(
            self.eauto_ladedaten, self.wallbox_ladedaten
        ) or braucht_tages_quote(self.eauto_ladedaten, self.wallbox_ladedaten)

    def falte(
        self,
        inv: Investition,
        data: dict,
        *,
        abgetretene_bkw: frozenset = frozenset(),
        bkw_mit_anlagenanteil: frozenset = frozenset(),
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

        ``bkw_mit_anlagenanteil`` (N-621) sind die IDs der Balkonkraftwerke, die
        in diesem Monat ihren Anteil am gespeicherten Anlagenwert bekommen
        (``pv_monatswerte.lade_pv_je_monat``, ``bkw_anteile``). Für sie gilt
        dasselbe wie für ein abtretendes BKW: ihre Erzeugung geht über einen
        anderen Weg in die PV-Summe (``ErzeugungFakten.bkw_aus_anlagenwert_kwh``),
        der Ersatzträger von P9 entfällt.
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
            # ⚠ N-621 — P9-Zusatzregel: ein BKW ohne eigene Erzeugung, das in
            # diesem Monat einen Anteil am gespeicherten Anlagenwert bekommt,
            # trägt KEINEN Ersatz-Eigenverbrauch. Seine Erzeugung geht über den
            # Anteil in `pv_kwh` ein, der selbst verbrauchte Teil steckt damit
            # schon in der Ableitung `PV − Einspeisung − Speicherladung` — ein
            # zweiter Term wäre die Doppelzählung, gegen die P9 geschrieben ist
            # (gemessen vorher: Anlagenwert 1000, Strings 550 + 380, BKW-Zeile
            # nur mit Eigenverbrauch 30 ⇒ PV 930 + Ersatz-EV 30). Dieselbe Form
            # wie die Abtretung im Absatz darüber, aus demselben Grund. Gilt
            # für jeden Empfänger des Anteils, auch wenn der Rest 0 ist — der
            # Anlagenwert sagt dann, dass das BKW nichts erzeugt hat.
            if hat_abgetreten or inv.id in bkw_mit_anlagenanteil:
                beitrag = bkw_finanz_beitrag(erzeugung_kwh=None, eigenverbrauch_kwh=None)
            if not hat_abgetreten:
                self.bkw_erzeugung += b.bkw_erzeugung
            # Je Investition zusätzlich zur Summe (F-10): der String-Vergleich
            # des Jahresbericht-PDF stellt jeden Erzeuger einzeln seinem SOLL
            # gegenüber und findet ein BKW in `pv_je_modul` nicht — dort stehen
            # nur `pv-module`. Die Summe `bkw_erzeugung` hilft ihm nicht, sobald
            # zwei Balkonkraftwerke da sind. Rein additiv; `pv_je_modul` und
            # `pv_module_kwh` bleiben unberührt, weil `pv_module_kwh` in die
            # ROI-Rechnung geht, wo das BKW bewusst eine eigene Zeile hat
            # (`investitionen/roi.py::get_roi_dashboard`, innere `get_pv_erzeugung`) und sonst doppelt zählte.
            #
            # N-266: ein abtretendes BKW steht hier NICHT. Beide Leser dieses
            # Felds addieren es neben `pv_je_modul` — der String-Vergleich des
            # PDF (dort ist das BKW seit E2 keine eigene Zeile mehr) und die
            # ROI-Gewichtung in `aussichten/finanz_zerlegung.py::roi_und_fortschritt`
            # (`_erz_gewichte` + `_bkw_gewichte`).
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
            # N-609: die Mengen je Gerät aus DEMSELBEN Beitrag wie die Summen darunter (K3 · D1 · Kühlanteil).
            _geraet = self.wp_je_geraet.setdefault(inv.id, [0.0, 0.0, 0.0])
            _geraet[0] += b.wp_strom
            _geraet[1] += b.wp_waerme
            _geraet[2] += b.wp_modus_strom_kuehlen
            self.wp_strom += b.wp_strom
            # WK-16d: der Rest der Summanden-Achsen, je Geraet aufgeloest und
            # erst danach summiert — wie die Menge darueber. Auf der
            # Anlagensumme gebildet waere er fuer eine Mischanlage sinnlos.
            self.wp_strom_nicht_aufgeteilt += b.wp_strom_nicht_aufgeteilt
            self.wp_waerme += b.wp_waerme
            # N-256: dieselben Mengen noch einmal, aber nur über die Geräte, die
            # überhaupt eine Heizung ersetzt haben. KEINE Aufteilung je Gerät —
            # zwei zusätzliche Summen, additiv neben den bestehenden. Sie sind
            # die Grundmenge des **fossilen Vergleichs**; `wp_waerme`/`wp_strom`
            # bleiben die Mengen der Anlage und werden von niemandem umgedeutet.
            if not ersetzt_keine_heizung(
                (inv.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
            ):
                self.wp_strom_mit_ersatz += b.wp_strom
                self.wp_waerme_mit_ersatz += b.wp_waerme
            self.wp_heizung += b.wp_heizung
            self.wp_warmwasser += b.wp_warmwasser
            self.wp_strom_heizen += b.wp_strom_heizen
            self.wp_strom_warmwasser += b.wp_strom_warmwasser
            # N-479: ODER über die Geräte — ein einziges gemessenes Gerät macht
            # die Funktion für diesen Monat „gemessen". Dieselbe Bauform wie
            # ``wp_hat_split`` darunter.
            self.wp_heizung_gemessen = (
                self.wp_heizung_gemessen or b.wp_heizung_gemessen)
            self.wp_warmwasser_gemessen = (
                self.wp_warmwasser_gemessen or b.wp_warmwasser_gemessen)
            self.wp_strom_heizen_gemessen = (
                self.wp_strom_heizen_gemessen or b.wp_strom_heizen_gemessen)
            self.wp_strom_warmwasser_gemessen = (
                self.wp_strom_warmwasser_gemessen or b.wp_strom_warmwasser_gemessen)
            self.wp_hat_split = self.wp_hat_split or b.wp_hat_split
            self.wp_waerme_ist_gesamt = (
                self.wp_waerme_ist_gesamt or b.wp_waerme_ist_gesamt
            )
            self.wp_modus_strom_heizen += b.wp_modus_strom_heizen
            self.wp_modus_strom_kuehlen += b.wp_modus_strom_kuehlen
            self.wp_modus_strom_warmwasser += b.wp_modus_strom_warmwasser
            self.wp_modus_strom_lueften += b.wp_modus_strom_lueften
            self.wp_modus_strom_entfeuchten += b.wp_modus_strom_entfeuchten
            # SOLL-§9-E7/Option A: die Entscheidung ist in `b` schon gefallen
            # (je Gerät). Hier wird nur addiert — anlagenweit wäre sie falsch,
            # sobald ein F5-Gerät neben einem nicht-F5-Gerät steht.
            self.wp_modus_strom_funktionsfremd_abzug += (
                b.wp_modus_strom_funktionsfremd_abzug
            )
            self.wp_nutzenergie_kuehlen += b.wp_nutzenergie_kuehlen
            self.wp_nutzenergie_lueften += b.wp_nutzenergie_lueften
            self.wp_nutzenergie_entfeuchten += b.wp_nutzenergie_entfeuchten
            # W-17: derselbe Grund wie im abgeleiteten Zweig oben — `b` ist der
            # Beitrag EINES Geraets zu diesem Monat. Beide Zweige schreiben in
            # dasselbe `_RohMonat`; das Maximum ueber beide ist deshalb das
            # Maximum ueber alle Geraete des Monats, egal auf welchem Weg sie
            # hereinkommen.
            self.wp_modus_abdeckung_h = abdeckung_ueber_geraete(
                self.wp_modus_abdeckung_h, b.wp_modus_abdeckung_h,
            )
            self.wp_modus_gemessen = self.wp_modus_gemessen or b.wp_modus_gemessen
            self.wp_modus_strom_bezug += b.wp_modus_strom_bezug
            self.wp_waerme_abgeleitet += b.wp_waerme_abgeleitet
            # ⭐ **N-441/Fall J: der Geräte-Kreis des Nenners wird NACH dem
            # Abzug gezählt.** `arbeitszahl` zieht den funktionsfremden Strom
            # (Kühlen · Lüften · Entfeuchten, W-14/E4) vom Nenner ab. Ein
            # Zweitgerät, das ausschliesslich kühlt, steht damit **nicht** im
            # Nenner der Gesamtzahl — es darf sie auch nicht sperren. Gemessen:
            # 2400 kWh Waerme ÷ 800 kWh Heizstrom = 3,0 existiert, wurde aber
            # mit „nicht alle Geraete melden Waerme" unterdrueckt, waehrend
            # Heizen und Kuehlen daneben beide 3,0 zeigten.
            if b.wp_strom > 0:
                # R2/Bauart: nur Geräte, die auch **Strom** beitragen — ein
                # stillstehendes Zweitgerät soll die Kennzahl des laufenden
                # nicht sperren. Dieselbe Zusicherung wie beim Tages-Zweig der
                # Abgrenzungs-Störung, wo genau das schon einmal nötig war.
                #
                # ⚠ Die Bauart-Zaehler bleiben bei „Strom > 0" — sie zaehlen
                # STAMMDATEN (welche Bauarten stehen im Block?), nicht den
                # Nenner. Ein reines Kuehlgeraet ist weiterhin ein Geraet der
                # Anlage, und eine gemischte Bauart bleibt gemischt.
                if ist_luft_luft_waermepumpe(inv):
                    self.wp_geraete_luft_luft += 1
                else:
                    self.wp_geraete_luft_wasser += 1
            if b.wp_strom - (
                b.wp_modus_strom_kuehlen
                + b.wp_modus_strom_lueften
                + b.wp_modus_strom_entfeuchten
            ) > 0:
                self.wp_geraete_mit_strom.add(inv.id)
            if b.wp_waerme > 0:
                self.wp_geraete_mit_waerme.add(inv.id)
            # R2 je Funktion: je Seite EINES Quotienten zaehlen. Gezaehlt wird
            # der **Beitrag**, nicht die Stammdaten-Zusicherung — nur so faengt
            # die Regel den Altbestand, den die Bauart-Bedingung nicht kennt.
            #
            # ⚠ `wp_strom` (das ungeteilte `stromverbrauch_kwh`) zaehlt hier
            # bewusst NICHT mit: Es gehoert zu KEINER Funktion. Genau deshalb
            # stoert die Klimaanlage in A5 die Heiz-Arbeitszahl nicht — ihre
            # 200 kWh stehen in keinem der beiden Quotienten.
            #
            # ⛔ **Gesammelt werden IDs, nicht Anzahlen (N-441).** „Ein Geraet
            # hier, ein Geraet dort" ergab `(1, 1)` und galt als deckungsgleich
            # — der Anlassfall (Waerme von A, Heizstrom von B) lieferte 3,0 ohne
            # jeden Grund. Die Regel prueft seither Identitaet.
            if b.wp_strom_heizen > 0:
                self.wp_geraete_e_heizen.add(inv.id)
            if b.wp_heizung > 0:
                self.wp_geraete_q_heizen.add(inv.id)
            if b.wp_strom_warmwasser > 0:
                self.wp_geraete_e_warmwasser.add(inv.id)
            if b.wp_warmwasser > 0:
                self.wp_geraete_q_warmwasser.add(inv.id)
            if b.wp_modus_strom_kuehlen > 0:
                self.wp_geraete_e_kuehlen.add(inv.id)
            if b.wp_nutzenergie_kuehlen > 0:
                self.wp_geraete_q_kuehlen.add(inv.id)
            # Erste gemeldete Störung gewinnt. Zwei verschiedene Störungen an
            # zwei Geräten wären beide richtig — die Kachel trägt aber nur einen
            # Grund, und beide führen zu derselben Folge (keine Kennzahl).
            if self.wp_abgrenzung is None and b.wp_abgrenzung:
                self.wp_abgrenzung = b.wp_abgrenzung

        elif inv.typ in ("e-auto", "wallbox"):
            if ist_dienstlich(inv):
                # Dienstlich geladen ist keine private Ersparnis — der Anteil
                # wird herausgefiltert, aber nicht verworfen: er gehört als
                # Ausgabe in die Sonstige-Summen (Bewertung beim Aufrufer, sie
                # braucht den Monatstarif). [[feedback_dienstwagen_alle_checks]]
                #
                # N-555: die Menge rechnet die eine Funktion (`bau.py`, über
                # `entscheide_emob_heimladung`) — bitgleich zu vorher, aber der
                # Fahrverbrauch als Schätzung steht dort ausdrücklich. Hier stand
                # `get_emob_pv_netz_kwh(data)`, dessen Ersatz still einsprang.
                self.dienstlich_je_inv[inv.id] = data
                if inv.typ == "wallbox":
                    self.dienstliche_wallbox_ids.add(inv.id)
                elif ist_heim_gesamt(data, source_provenance):
                    self.heim_gesamt_ids.add(inv.id)
            elif inv.typ == "e-auto":
                if ist_heim_gesamt(data, source_provenance):
                    self.heim_gesamt_ids.add(inv.id)
                self.eauto_ladedaten.append(data)
                self.eauto_ladedaten_ids.append(inv.id)
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
                self.wallbox_ladedaten_ids.append(inv.id)

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
            self.sonstiges_abgabe += b.sonstiges_abgabe
            g = self.sonstiges_je_geraet.setdefault(
                inv.id,
                {"erzeugung": 0.0, "verbrauch": 0.0, "eigenverbrauch": 0.0,
                 "einspeisung": 0.0, "bezug_pv": 0.0, "bezug_netz": 0.0,
                 "einspeise_erloes_euro": 0.0, "abgabe": 0.0,
                 "hat_einspeise_erloes": False},
            )
            g["erzeugung"] += b.sonstiges_erzeugung
            g["verbrauch"] += b.sonstiges_verbrauch
            g["eigenverbrauch"] += b.sonstiges_eigenverbrauch
            g["einspeisung"] += b.sonstiges_einspeisung
            g["bezug_pv"] += b.sonstiges_bezug_pv
            g["bezug_netz"] += b.sonstiges_bezug_netz
            g["einspeise_erloes_euro"] += b.sonstiges_einspeise_erloes_euro
            # ODER über die Monate: EIN gepflegter Monat genügt, damit das
            # Gerät als bewertbar gilt. Die Zahl der Monate MIT Wert zählt der
            # Aufrufer selbst (F-20: eigene Monatszahl je Posten).
            g["hat_einspeise_erloes"] = (
                g["hat_einspeise_erloes"] or b.hat_einspeise_erloes
            )
            g["abgabe"] += b.sonstiges_abgabe
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
