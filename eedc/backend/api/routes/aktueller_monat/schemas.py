"""Antwortmodelle und Konstanten von *Cockpit → Monat* (`/api/aktueller-monat`).

Reine Datenvertraege ohne Logik und ohne Datenbankzugriff — importierbar von jedem Modul des
Pakets, ohne einen Zyklus zu bilden.
"""
# Reiner Umzug aus `api/routes/aktueller_monat.py` (18.09.2026, Vorlage 1 des Refactorings
# grosser Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# exportiert alle Namen weiter, die Tests und Aufrufer bisher aus dem Modul importierten.

from datetime import datetime
from typing import NamedTuple, Optional
from pydantic import BaseModel, Field
from backend.services.waerme_klima_block import WpGeraetZeile, WpMoeglichZeile
from backend.core.berechnungen import anteilig, autarkie_prozent, einspeise_erloes_euro
from backend.services.wp_wirtschaftlichkeit import wp_ersparnis_berechnung


MONAT_NAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

class DatenquelleInfo(BaseModel):
    """Quellenangabe für ein einzelnes Feld."""
    quelle: str          # "ha_sensor" | "local_connector" | "gespeichert"
    konfidenz: int       # 95, 90, 85
    zeitpunkt: Optional[str] = None
    # Zeitraum, den der Wert tatsächlich misst — bisher nur beim Connector
    # gesetzt, dessen Delta aus zwei Zähler-Snapshots stammt und den Monat
    # nicht abdecken MUSS (frisch eingerichteter Connector). Leer = Abdeckung
    # unbekannt bzw. nicht anwendbar.
    abdeckung_von: Optional[datetime] = None
    abdeckung_bis: Optional[datetime] = None


#: Anzeigename der Erlös-Zeile im Regelfall — BKW und *Sonstiges/Erzeuger*
#: speisen ins öffentliche Netz ein. Die Kategorie *Abgabe an Dritte* setzt
#: stattdessen `SONSTIGES_ABGABE_LABEL` (§9.2).
ERLOES_LABEL_EINSPEISUNG: str = "Einspeisung"


class InvestitionFinancialDetail(BaseModel):
    """Finanzielle Details einer einzelnen Investition für den T-Konto-View."""
    investition_id: int
    bezeichnung: str
    typ: str
    betriebskosten_monat_euro: float = 0.0
    #: Der Jahresbetrag, aus dem `betriebskosten_monat_euro` der Zwölftel ist
    #: (A6: die Kachel nennt „Betriebskosten/Jahr ÷ 12", der Jahreswert stand
    #: bis 2026-09-13 auf keiner Fläche). Quelle ist dieselbe wie oben —
    #: `Investition.betriebskosten_jahr`; der Client teilt NICHT selbst.
    betriebskosten_jahr_euro: float = 0.0
    erloes_euro: Optional[float] = None      # z.B. BKW-Einspeisung
    #: Herleitung der Erlös-Zeile. Sie ist NICHT für alle Typen dieselbe: beim
    #: BKW rechnet eedc `Einspeisung × Vergütung`, bei einem sonstigen Erzeuger
    #: steht dort ein **gepflegter** Betrag (Konzept §9 Weg 2). Der Client hat
    #: den Satz bis 2026-09-02 fest verdrahtet und hätte damit für den zweiten
    #: Fall eine Rechnung behauptet, die niemand angestellt hat (Regel A6:
    #: Formel **+ eingesetzte Werte**). Wer den Wert bildet, beschreibt ihn.
    erloes_formel: Optional[str] = None
    #: Die **eingesetzten Werte** zur Formel darüber (Style-Guide A6: Formel sagt
    #: WAS gerechnet wird, die Berechnung WOMIT). Bis 2026-09-13 standen beide in
    #: `erloes_formel` in EINER Zeile („Einspeisung × Einspeisevergütung — 123,4
    #: kWh × 8,20 ct/kWh") und damit unter der Überschrift „Formel" — an jeder
    #: anderen Kachel stehen sie getrennt. `None` bei den **gepflegten** Erlösen:
    #: dort gibt es keine Rechnung, nur eine Herkunftsangabe (Konzept §9 Weg 2).
    #: ⛔ Der Wert wird hier gebildet, nicht im Client — eine im Client
    #: nachgerechnete Herleitung führt auf eine andere Zahl als die Zeile daneben.
    erloes_berechnung: Optional[str] = None
    #: Anzeigename der Erlös-Zeile („{Gerät} — {erloes_label}"). Kommt aus dem
    #: Backend statt aus dem Client, weil ihn die **Kategorie** entscheidet:
    #: ein Gerät der Kategorie *Abgabe an Dritte* trägt keinen Einspeise-Erlös,
    #: sondern den Erlös des dritten Wegs (§9.2). Der Client hatte „Einspeisung"
    #: bis 2026-09-06 hart verdrahtet und nannte damit im T-Konto ein Wort, das
    #: in der Energiebilanz derselben Anlage nicht vorkommt (Melder rilmor-mhrs,
    #: #402). Regel 0 verlangt für die Geldzeile denselben Namen wie für die
    #: Energiezeile; Bauform wie `ersparnis_label`.
    erloes_label: str = ERLOES_LABEL_EINSPEISUNG
    ersparnis_euro: Optional[float] = None   # Eigenverbrauch, WP, eMob, Speicher, ...
    ersparnis_label: str = ""                # "Eigenverbrauch-Ersparnis", "Ersparnis vs. Alternative", ...
    formel: Optional[str] = None
    berechnung: Optional[str] = None
    # Sonstige Positionen (z.B. AG-Vergütung Dienstwagen, THG-Quote, Reparaturen).
    # Werden je Investition aggregiert; Detail-Zeilen rendert das Frontend.
    sonstige_ertraege_euro: float = 0.0
    sonstige_ausgaben_euro: float = 0.0


class SonstigesGeraet(BaseModel):
    """Ein einzelnes „Sonstiges"-Gerät mit seinen Energiewerten — für die Sonder-
    Darstellung im Cockpit: zwei Blöcke (Erzeuger/Verbraucher), darin pro Gerät
    eine eigene Werte-Zeile mit Bezeichnung."""
    bezeichnung: str
    kategorie: str  # "erzeuger" | "verbraucher" | "abgabe" (§9.2)
    # Abgabe an Dritte (§9.2)
    abgabe_kwh: Optional[float] = None
    erloes_euro: Optional[float] = None
    # Erzeuger
    erzeugung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    # Verbraucher
    verbrauch_kwh: Optional[float] = None
    bezug_pv_kwh: Optional[float] = None
    bezug_netz_kwh: Optional[float] = None


class AktuellerMonatResponse(BaseModel):
    """Aggregierte Übersicht des aktuellen Monats."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    aktualisiert_um: str

    # Verfügbare Quellen
    quellen: dict[str, bool]
    #: Beschriftung für Werte, die weniger enthalten als ihr Name sagt (P4-Form,
    #: gerendert über `unvollstaendigHerkunft` + `HerkunftZeile`). Leer =
    #: vollständig. Wird **nur** gefüllt, wenn die PV-Zahl dieses Monats aus der
    #: gespeicherten Zeile stammt — kommt sie aus Sensor, Connector oder MQTT,
    #: sagt `pv_vollstaendig` der Monats-Fakten nichts über sie aus.
    hinweise: list[str] = []
    #: Warum eine Kachel **leer** bleibt — je Basis-Größe der fertige Satz aus
    #: `core/monatswert_grund.py` (N-472, W-18-Klasse eine Zeitebene höher).
    #: Nur für Größen ohne Wert gesetzt; eine Größe mit Zahl steht nicht drin.
    #:
    #: ⚠ Bewusst nur die **drei Basis-Größen** (PV · Einspeisung · Netzbezug).
    #: Autarkie, Eigenverbrauch und Gesamtverbrauch entstehen aus ihnen — an
    #: jeder abgeleiteten Kachel denselben Grund zu wiederholen wäre genau die
    #: Strich-Flut, gegen die die D-Sicht gebaut ist (WK-16ab/E-2).
    datenlage_gruende: dict[str, str] = {}

    # Energie-Bilanz (kWh)
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    direktverbrauch_kwh: Optional[float] = None  # PV direkt verbraucht (ohne Speicher): EV − Speicher-Entladung; günstigster Verbrauch (nur entgangene Einspeisung)
    gesamtverbrauch_kwh: Optional[float] = None

    # Quoten (%)
    autarkie_prozent: Optional[float] = None
    eigenverbrauch_quote_prozent: Optional[float] = None
    # Spezifischer Ertrag kWh/kWp — gleiche Basis wie der Community-Vergleich
    # (anlage.leistung_kwp), damit die Abweichung zum Community-Median stimmt.
    spez_ertrag: Optional[float] = None

    # Komponenten — Speicher
    speicher_ladung_kwh: Optional[float] = None
    speicher_entladung_kwh: Optional[float] = None
    speicher_ladung_netz_kwh: Optional[float] = None   # Arbitrage-Ladung vom Netz
    # F-22: SoC-KORRIGIERT (nicht der rohe Quotient) — der Ladestand am
    # Monatsrand ist herausgerechnet und der Wert auf 100 % geklemmt.
    speicher_wirkungsgrad_prozent: Optional[float] = None
    speicher_vollzyklen: Optional[float] = None        # Entladung / Kapazität
    speicher_kapazitaet_kwh: Optional[float] = None    # Aus Investition.parameter
    # F-22: worauf der η beruht — `soc_korrigiert` (Ladestand herausgerechnet,
    # der Regelfall) · `roh-unkorrigiert` (kein SoC verfügbar, Wert plausibel
    # aber ungenau — der Client kennzeichnet ihn) · `fenster-zu-kurz` /
    # `nicht-ermittelbar` (kein Wert, Grund steht unter der Kachel, ADR-002/P4).
    speicher_wirkungsgrad_quelle: Optional[str] = None
    # Etappe C (#264), Bedeutung seit F-22 geschärft: „für diesen Monat ist kein
    # belastbarer η ermittelbar" — nicht mehr „der SoC ist gedriftet". Drift
    # allein blendet NICHTS mehr aus, sie wird herausgerechnet; ausgeblendet
    # wird nur, was ohne SoC-Randwerte und ohne langes Fenster unbestimmbar ist.
    # Name bleibt für Bestandsclients, die ihn lesen.
    speicher_soc_drift_signifikant: bool = False
    speicher_effektiver_ladepreis_cent: Optional[float] = None
    speicher_effektiver_ladepreis_quelle: Optional[str] = None  # dyn-tarif | boersenpreis
    # R15-1 (Rainer-Kostenkacheln): Kosten der Netzladung + verwendeter Preis
    speicher_ladung_netz_kosten_euro: Optional[float] = None
    speicher_ladung_netz_preis_cent: Optional[float] = None
    speicher_ladung_netz_preis_quelle: Optional[str] = None  # tep | imd | bezugspreis
    # #358 Phase 1 — Auslastung und Netto-Nutzen des Zeitraums.
    # `basis` = Kapazität × Tage (theoretisch verfügbare Menge). Sie steht als
    # eigenes Feld daneben, damit die Jahres-Sicht Entladung und Basis SUMMIEREN
    # und einmal teilen kann: Auslastungen mehrerer Monate lassen sich nicht
    # mitteln (Februar wiegt weniger als Juli). Ohne gepflegte Kapazität bleiben
    # beide `None` — „unbekannt", nicht 0.
    speicher_auslastungs_basis_kwh: Optional[float] = None
    speicher_auslastung_prozent: Optional[float] = None
    # Σ der Speicher-Ersparnisse des Monats — dieselbe Zahl wie im T-Konto
    # (Spread-SoT), aufgesammelt statt zweitgerechnet.
    speicher_ersparnis_euro: Optional[float] = None
    hat_speicher: bool = False

    # Komponenten — Wärmepumpe
    wp_strom_kwh: Optional[float] = None
    wp_waerme_kwh: Optional[float] = None
    wp_heizung_kwh: Optional[float] = None
    wp_warmwasser_kwh: Optional[float] = None
    # ── Arbeitszahl: die Zahl UND ihre Begründung (R2, Befund W-3) ──────────
    #
    # ⛔ **Bis 2026-08-26 lieferte diese Response nur `wp_waerme_kwh` und
    # `wp_strom_kwh`, und der Client bildete den Quotienten selbst.** Er
    # **konnte** die Sperre nicht kennen, die der Komponenten-Hub und die
    # Cockpit-Übersicht anwenden — Folge: dieselbe Anlage zeigte im Hub „—"
    # und im Cockpit eine Zahl. Zwei Sichten, zwei Antworten auf dieselbe
    # Frage (ADR-001, SOLL §3.3/S1).
    #
    # SoT ist `core/berechnungen/waermepumpe_kennzahl.arbeitszahl`.
    wp_jaz: Optional[float] = None
    #: Warum es **keine** Arbeitszahl gibt — nie ein „—" ohne Grund (S3).
    wp_jaz_grund: Optional[str] = None
    #: Die Zahl existiert, ist aber erklärungsbedürftig (Fall H-B: ein großer
    #: Teil der Wärme kam direkt elektrisch). **Kein Fehler, keine Bewertung.**
    wp_jaz_hinweis: Optional[str] = None
    #: Die beiden Zahlen, aus denen die Arbeitszahl **tatsächlich** entstanden
    #: ist (kWh) — für die Herleitung an der Kachel.
    #:
    #: ⚠ ``wp_jaz_nenner_kwh`` ist **nicht** ``wp_strom_kwh``: der funktions-
    #: fremde Anteil (Kühlen, Lüften, Entfeuchten) ist abgezogen. Wer die
    #: Herleitung im Client aus den Anzeigefeldern nachbaut, zeigt bei jeder
    #: Anlage mit erfasstem Betriebsmodus eine Rechnung, die nicht auf die Zahl
    #: daneben führt. Deshalb kommen beide aus dem Layer — wie ``grund`` und
    #: ``hinweis`` (W-3: dieselbe Regel an drei Stellen war der teure Fall).
    wp_jaz_zaehler_kwh: Optional[float] = None
    wp_jaz_nenner_kwh: Optional[float] = None
    #: Ist ein Teil der Wärme aus `Strom × JAZ` gerechnet statt gemessen?
    #: Gleicher Name wie im Komponenten-Hub (`KomponentenMonat`), damit dieselbe
    #: Größe in beiden Sichten gleich heißt (S1).
    wp_waerme_abgeleitet: bool = False
    #: Steht mindestens eine hier gesperrte Kennzahl im **Komponenten-Hub**?
    #:
    #: Der Hub rechnet je Gerät; was aus dem Zusammenspiel MEHRERER Geräte
    #: entsteht, gibt es dort nicht. Nur dann lohnt der Weg — die Liste der
    #: Gründe steht im Layer (``GRUENDE_HUB_HILFT``), damit der Client keine
    #: Grund-Texte vergleichen muss.
    wp_hub_hilft: bool = False
    #: **Wie viel** davon gerechnet ist — die Menge neben dem Flag darüber.
    #:
    #: ⚠ Das Flag beantwortet „ist *irgendein* Teil gerechnet?" und ist damit
    #: für eine **Kennzahl** die richtige Auskunft: `jaz_belastbar`
    #: (`monats_fakten/`) sperrt alles-oder-nichts, und zwar mit Grund —
    #: gemessene Wärme durch den **Gesamt**strom geteilt gäbe eine zu kleine
    #: JAZ, also falsch statt unbekannt.
    #:
    #: ⭐ Für eine **Menge** gilt das nicht. Ein Verlauf, der nur gemessene
    #: Wärme zeigen soll (Konzept Wärme/Klima §8/E7, SOLL §3.3), braucht
    #: `waerme_kwh − waerme_abgeleitet_kwh` — und das ist bei gemischter Lage
    #: (Wärmepumpe mit Wärmemengenzähler + Klimaanlage ohne) eine ganz andere
    #: Aussage als das Flag: dort ist der größte Teil der Wärme gemessen,
    #: während das Flag bereits True ist. **Zwei Objekte, zwei Regeln.**
    wp_waerme_abgeleitet_kwh: Optional[float] = None
    # B4 (05.09.2026, C-2): Herkunft der Wärme und Vorbehalt an Ersparnis/CO₂,
    # fertig formuliert aus dem Layer (`waermepumpe_kennzahl.waerme_herkunft` /
    # `ersparnis_vorbehalt`) — dieselben Worte wie im Komponenten-Hub (B3).
    # SOLL §6 (05.09.): eine geschätzte Wärme erscheint als geschätzt.
    wp_waerme_herkunft: Optional[str] = None
    wp_ersparnis_vorbehalt: Optional[str] = None
    # B6/Y-3: die Rechnung hinter der Zahl, aus dem Layer-Ergebnis — der Client
    # baut keinen Formeltext mehr selbst (A6, ADR-002/P12).
    wp_ersparnis_berechnung: Optional[str] = None
    # #191: Strom-Aufteilung Heizung/Warmwasser. Nur gesetzt wenn mindestens
    # eine WP-Investition `getrennte_strommessung=true` hat. Sonst None →
    # Frontend zeigt nur den Gesamtstromverbrauch.
    wp_strom_heizen_kwh: Optional[float] = None
    wp_strom_warmwasser_kwh: Optional[float] = None
    # #263 K-2 (S4): Aufteilung nach Betriebsmodus — **Teilmengen** von
    # `wp_strom_kwh`, nie Summanden. Alle vier fehlen gemeinsam, wenn kein
    # Modus erfasst ist (eine 0 hieße „hat nicht geheizt", ADR-002/P4).
    wp_modus_strom_heizen_kwh: Optional[float] = None
    wp_modus_strom_kuehlen_kwh: Optional[float] = None
    #: N-336: die dritte ableitbare Betriebsart. ⚠ **Nicht** dasselbe wie
    #: `wp_strom_warmwasser_kwh` darüber — das ist ein Summand aus der
    #: getrennten Strommessung, dies eine Teilmenge des Gesamtstroms.
    wp_modus_strom_warmwasser_kwh: Optional[float] = None
    #: E4 (Konzept §2.3): eigene Segmente statt stummer Restmenge. Nur aus
    #: **gemessenen** Betriebsart-Zählern — der abgeleitete Split kann sie
    #: nicht und lässt sie bei 0. Sie bekommen keine Kennzahl (*erfassen ja,
    #: bewerten nein*) und fallen aus dem Nenner der Arbeitszahl.
    #: W-4 (SOLL §4.1): Arbeitszahl je Funktion — mit ihrem Grund, wenn es sie
    #: nicht gibt. Erscheint nur bei getrennter Strommessung; ohne sie liegt E
    #: je Funktion nicht vor und beide tragen denselben Grund.
    wp_jaz_heizen: Optional[float] = None
    wp_jaz_heizen_grund: Optional[str] = None
    wp_jaz_warmwasser: Optional[float] = None
    wp_jaz_warmwasser_grund: Optional[str] = None
    #: W-5: Arbeitszahl **Kühlen** (Kältemenge ÷ Kühlstrom). Bewusst nicht
    #: „SEER" — das ist eine genormte Prüfstandsgröße, dies ein gemessener
    #: Quotient über einen Zeitraum.
    wp_jaz_kuehlen: Optional[float] = None
    wp_jaz_kuehlen_grund: Optional[str] = None
    #: **E1b (14.09.2026): die anlagenweite Zahl darf eine untere SCHRANKE sein.**
    #: ``True`` ⇒ ``wp_jaz`` ist ein **Mindestwert** („≥ 3,25"), weil im Nenner
    #: Strom steht, dem keine gemessene Wärme gegenübersteht (Klimaanlage ohne
    #: Wärmemengenzähler, Heizstab). Mehr Strom im Nenner kann den Quotienten
    #: nur kleiner machen — die Aussage bleibt wahr (ADR-002/**P4** verbietet
    #: falsche Zahlen, nicht wahre Schranken).
    #:
    #: ⛔ **Der Client rechnet daraus nichts** — er setzt ein „≥" davor
    #: (``check:cop-roh``). Die Entscheidung, ob eine Schranke vorliegt, gehört
    #: in den Layer; im Client wäre sie eine zweite Regel über denselben
    #: Sachverhalt.
    wp_jaz_ist_schranke: bool = False
    #: Der EINE Satz unter der Schranke: *„Klimaanlage: Strom ohne Wärmemessung
    #: enthalten"*. Er nennt die Ursache, er bewertet nicht.
    wp_jaz_schranke_hinweis: Optional[str] = None
    #: **D-Sicht 3: die Kennzahlen JE GERÄT stehen im Block selbst.** Bis
    #: 14.09.2026 gab es sie nur im Komponenten-Hub, und der Block verwies mit
    #: einem Link dorthin — bei gemischter Ausstattung blieb der Anwender damit
    #: vor vier Strichen stehen, obwohl jedes seiner Geräte eine saubere Zahl
    #: hat. Quelle ist **dieselbe** Rechenstelle wie im Hub
    #: (``services/waermepumpe_kennzahlen_je_geraet.py``).
    wp_geraete: list[WpGeraetZeile] = Field(default_factory=list)
    #: **D-Sicht 1: was die Ausstattung nicht hergibt — einmal je Sicht.**
    #: Größen ohne Zahl erscheinen nicht mehr als Kachel mit „—", sondern hier,
    #: mit dem Handgriff und dem Weg dorthin. Ein Grund der Klasse *Zeitraum*
    #: („kein Heizbetrieb in diesem Zeitraum") steht **nicht** darin — dort gibt
    #: es nichts zu tun, und die Kachel zeigt ein „—" ohne Text.
    wp_moeglich: list[WpMoeglichZeile] = Field(default_factory=list)
    #: Bauschnitt 6b: die **gemessene Kälte** des Monats — dieselbe Menge, die
    #: die Arbeitszahl Kühlen daneben als Zähler benutzt. ``None`` statt 0,0,
    #: wo kein Kältemengenzähler etwas gemeldet hat: die Monats-Fakten füllen
    #: dort 0,0 (`or 0.0`), und eine 0 ohne Zähler ist keine Messung (P4).
    wp_kaelte_kwh: Optional[float] = None
    wp_modus_strom_lueften_kwh: Optional[float] = None
    wp_modus_strom_entfeuchten_kwh: Optional[float] = None
    #: **R-C (WK-16f, N-398):** die abgegebene Nutzenergie derselben zwei
    #: Betriebsarten — **nur mit Zahl** (D-Sicht). E4 bleibt: Menge, keine
    #: Kennzahl. Bis zum 14.09.2026 las diese zwei Registry-Felder niemand.
    wp_modus_nutzenergie_lueften_kwh: Optional[float] = None
    wp_modus_nutzenergie_entfeuchten_kwh: Optional[float] = None
    wp_modus_nicht_aufgeteilt_kwh: Optional[float] = None
    wp_modus_abdeckung_h: Optional[float] = None
    #: **W-17b** — die Grundmenge, auf die sich die Aufteilung bezieht.
    #: Bewusst **nicht** `wp_strom_kwh`: dort steckt auch der Strom von Geraeten
    #: ohne Modus-Signal. Der Balken steht sonst unter einer Kachel mit einer
    #: groesseren Zahl, ohne dass die Differenz irgendwo benannt waere
    #: (dietmar1968, T89667 #210: Balken 30 kWh unter Kachel 284 kWh).
    wp_modus_strom_bezug_kwh: Optional[float] = None
    #: #263 — die Aufteilung ist GEMESSEN (Betriebsart-Zähler) statt aus dem
    #: Betriebsmodus abgeleitet. Dann ist `wp_modus_abdeckung_h` 0, ohne dass
    #: etwas fehlt — ein Zähler zählt kWh, keine Stunden mit Signal.
    wp_modus_gemessen: Optional[bool] = None
    # Issue #169: Kompressor-Starts. Quelle: TagesZusammenfassung.komponenten_starts
    # über die Tage des Monats, summiert über alle WP-Investitionen.
    wp_starts_max_tag: Optional[int] = None
    wp_starts_summe_monat: Optional[int] = None
    # Issue #238: Betriebsstunden analog zu den Starts (gleiche Counter-Architektur,
    # Feld `wp_betriebsstunden` in komponenten_starts). Stunden → float.
    wp_betriebsstunden_max_tag: Optional[float] = None
    wp_betriebsstunden_summe_monat: Optional[float] = None
    hat_waermepumpe: bool = False

    # Komponenten — E-Mobilität
    emob_ladung_kwh: Optional[float] = None
    emob_km: Optional[float] = None
    # Ø Verbrauch (kWh/100 km) zentral via core/berechnungen/emob.py (gemessen > Ladung).
    emob_verbrauch_100km: Optional[float] = None
    emob_verbrauch_quelle: str = "keine"
    emob_ladung_pv_kwh: Optional[float] = None       # PV-Anteil der Ladung
    emob_ladung_netz_kwh: Optional[float] = None     # Netz-Anteil
    emob_ladung_extern_kwh: Optional[float] = None   # Extern (Ladesäule o.ä.)
    emob_v2h_kwh: Optional[float] = None             # V2H-Rückspeisung
    #: N-557 (Konzept Regel 10): „Ladung gesamt" = Heimladung + Extern, soweit
    #: Extern bekannt ist — eine **eigene** Anzeige-Größe. `emob_ladung_kwh` bleibt
    #: die Heimladung (PV-Anteil, T-Konto, CO₂ und Community rechnen mit ihr).
    emob_ladung_gesamt_kwh: Optional[float] = None
    #: N-557: die **Menge** hinter `emob_verbrauch_100km` (gemessener Fahrverbrauch
    #: bzw. Heim + Extern), damit ein Zeitraum Σ Monatswerte ÷ Σ km bilden kann,
    #: statt die Ladung neu zu teilen (Cockpit → Jahr). `None` ohne Basis.
    emob_verbrauch_basis_kwh: Optional[float] = None
    hat_emobilitaet: bool = False

    # Komponenten — BKW
    bkw_erzeugung_kwh: Optional[float] = None
    bkw_eigenverbrauch_kwh: Optional[float] = None
    hat_balkonkraftwerk: bool = False

    # Komponenten — Sonstiges
    sonstiges_erzeugung_kwh: Optional[float] = None    # Erzeuger-Typ
    # §9.2 — Abgabe an Dritte: der dritte Weg der Verwendung (nicht im
    # Eigenverbrauch, nicht in der Netz-Einspeisung).
    abgabe_dritte_kwh: Optional[float] = None
    sonstiges_eigenverbrauch_kwh: Optional[float] = None
    sonstiges_einspeisung_kwh: Optional[float] = None
    sonstiges_verbrauch_kwh: Optional[float] = None    # Verbraucher-Typ
    sonstiges_bezug_pv_kwh: Optional[float] = None
    sonstiges_bezug_netz_kwh: Optional[float] = None
    # Pro-Gerät-Aufschlüsselung für die Sonder-Darstellung (2 Blöcke Erzeuger/
    # Verbraucher, darin je Gerät eine eigene Werte-Zeile mit Bezeichnung).
    sonstiges_geraete: list[SonstigesGeraet] = []
    hat_sonstiges: bool = False

    # Finanzen (Euro)
    einspeise_erloes_euro: Optional[float] = None
    # §51 EEG: was der Abzug gekostet hat. `None` = keine Tages-Aggregate bzw.
    # Anlage unterliegt nicht §51; `0.0` = betroffen, aber in dem Monat keine
    # Einspeisung zu Negativpreisen. Der Erlös oben ist bereits gekürzt — ohne
    # diesen Ausweis bliebe die Kürzung unsichtbar (Versprechen im Anlage-
    # Formular: „der entgangene Erlös wird im Cockpit als §51-Verlust ausgewiesen").
    einspeisung_neg_preis_kwh: Optional[float] = None
    nicht_vergueteter_erloes_euro: Optional[float] = None
    netzbezug_kosten_euro: Optional[float] = None
    # Arbeitspreis-Anteil der Netzbezugskosten OHNE Grundpreis
    # (`netzbezug_kwh × Preis`). Reiner Ausweis für Sichten, die kWh und € so
    # nebeneinander stellen, dass ein Leser sie dividiert — dort muss der
    # Ø-Preis herauskommen. Kein zweiter Kostenposten; verrechnet wird
    # weiterhin ausschließlich `netzbezug_kosten_euro`.
    netzbezug_arbeitspreis_kosten_euro: Optional[float] = None
    ev_ersparnis_euro: Optional[float] = None
    netto_ertrag_euro: Optional[float] = None
    wp_ersparnis_euro: Optional[float] = None
    emob_ersparnis_euro: Optional[float] = None
    #: N-555 (Nebenfund 2): der Rechenweg hinter `emob_ersparnis_euro` — je Fahrzeug
    #: die Zeile, die das T-Konto dort schon trägt (km × SEIN Vergleichsverbrauch ×
    #: Benzinpreis des Monats). Der Client zeigte im Fallback „7/100 × 1,80 €", zwei
    #: Werte, mit denen seit dem Drift-Audit A2 nicht mehr gerechnet wird.
    emob_ersparnis_berechnung: Optional[str] = None
    # Sonstige Positionen aggregiert (z.B. AG-Vergütung Dienstwagen, THG-Quote,
    # Reparaturen). Detail-Zeilen pro Investition stehen in
    # investitionen_financials. Frontend addiert sonstige_netto auf
    # nettoNachAllem; gesamtnettoertrag enthält sie bewusst NICHT (Backward-Compat).
    sonstige_ertraege_euro: float = 0.0
    sonstige_ausgaben_euro: float = 0.0
    sonstige_netto_euro: float = 0.0
    # G19-1: davon Anlage-Ebene (Monatsdaten.sonstige_positionen) — reiner
    # Ausweis für die T-Konto-Zeile „Anlage — Sonstige …", bereits in den
    # sonstige_*-Totals enthalten (kein zweiter Posten, R15-5-Muster).
    anlage_sonstige_ertraege_euro: float = 0.0
    anlage_sonstige_ausgaben_euro: float = 0.0
    gesamtnettoertrag_euro: Optional[float] = None  # Erlöse + Einsparungen − Kosten

    # Tarif-Info
    netzbezug_preis_cent: Optional[float] = None      # Verwendeter Tarif
    # N-267: sagt der Anzeige, dass der Preis daneben ein ueber die Stunden
    # GEWICHTETER Wert ist und nicht der Arbeitspreis aus den Stammdaten. Ohne
    # ihn stuende „Netzbezugspreis 26,25" neben einem Tarif, der 30,00 nennt —
    # und niemand koennte die Differenz erklaeren. Dieselbe Rolle, die
    # `netzbezug_durchschnittspreis_cent` beim dynamischen Tarif hat.
    netzbezug_preis_zeittarif: bool = False
    einspeise_preis_cent: Optional[float] = None
    netzbezug_durchschnittspreis_cent: Optional[float] = None  # Flexibler Tarif (Monatsdurchschnitt)
    #: **Der Preis, mit dem das Geld dieses Monats gerechnet wurde** — das
    #: Ergebnis der vollen Kaskade (`aufgeloester_monatspreis`), zu dem die
    #: beiden Felder darunter (`_herkunft`, `_abdeckung`) gehören.
    #:
    #: ⛔ **Bis 2026-09-17 fehlte er, und das war der Fehler:** Herkunft und
    #: Abdeckung wurden ausgeliefert, der zugehörige **Wert** nicht. Die Kachel
    #: zeigte deshalb `netzbezug_durchschnittspreis_cent ?? netzbezug_preis_cent`
    #: — im laufenden Monat ohne Abschluss also den **Stammpreis**, während die
    #: Formelzeile darüber „Ø deiner gemessenen Stundenpreise" sagte und die
    #: Kosten daneben mit dem gemessenen Ø gerechnet waren. Drei Zahlen, eine
    #: Kachel (OB73-gif, #412-Folgemeldung).
    #:
    #: SOLL Flex-Tarife **H-2**: die Beschriftung beschreibt die Zahl daneben.
    #: `netzbezug_preis_cent` bleibt unverändert der **Tarif**-Wert („Verwendeter
    #: Tarif") — beide nebeneinander sind eine Aussage, eines allein ist keine.
    netzbezug_preis_effektiv_cent: Optional[float] = None
    #: Welche Stufe der Preis-Kaskade gegriffen hat: ``gepflegt`` (abgerechneter
    #: Ø aus dem Monatsabschluss) · ``gemessen`` (Ø der mitgeschriebenen
    #: Stundenpreise) · ``zeitfenster`` (HT/NT, über den Netzbezug gewichtet) ·
    #: ``stamm`` (die Tarifspalte). ⚠ Ohne diese Angabe wäre ein **gemessener**
    #: Preis in der Anzeige von einem Stammpreis nicht zu unterscheiden — die
    #: Formel-Zeile der Kachel nannte bis 11.09.2026 beide „Arbeitspreis aus dem
    #: Strompreis-Tarif" (P4: die Antwort sagt, was sie ist).
    netzbezug_preis_herkunft: Optional[str] = None
    #: Anteil der Monatsstunden mit Preisdaten (0..1) — **nur** bei
    #: ``gemessen``. Ein Ø aus 40 % der Stunden hat dieselbe Herkunft wie einer
    #: aus 98 %, aber nicht dieselbe Belastbarkeit; im **laufenden** Monat ist
    #: er zwangsläufig klein (die Abdeckung misst gegen den vollen Monat).
    netzbezug_preis_abdeckung: Optional[float] = None
    # G19-1 K3 (R19-3): Grundgebühr des Monats — steckt bereits in
    # netzbezug_kosten_euro (reiner Ausweis, kein zweiter Posten).
    grundgebuehr_euro: Optional[float] = None
    # G19-1 K3: jährliche Zähler-/Messstellengebühr vom Tarif — reiner Ausweis
    # in der Jahresaufstellung, NICHT in Kosten/Netto-Ertrag verrechnet.
    zaehlergebuehr_euro_jahr: Optional[float] = None

    # Vergleiche
    vorjahr: Optional[dict] = None
    # PVGIS-SOLL des Monats. Im LAUFENDEN Monat nur der Anteil der abgelaufenen
    # Tage (N-69) — sonst stünde ein voller Monats-Nenner über einem
    # angefangenen Ertrag. `soll_pv_tage`/`_gesamt` benennen das Fenster, damit
    # die Anzeige „anteilig" sagen kann statt eine gekürzte Zahl als Monats-SOLL
    # auszugeben; `tage == tage_gesamt` heißt „voller Monat".
    soll_pv_kwh: Optional[float] = None
    soll_pv_tage: Optional[int] = None
    soll_pv_tage_gesamt: Optional[int] = None
    # Dasselbe SOLL **ungekürzt** — die Prognose für den ganzen Monat.
    # Melder dietmar1968 (T89667 #155, 14.08.2026): der Fortschritt gegen die
    # volle Monatsprognose war ihm wichtig und ist mit N-69 aus der Anzeige
    # verschwunden. Die Größe steht hier, statt im Client aus `soll_pv_kwh`
    # zurückgerechnet zu werden: die Kürzung ist zwar linear und damit exakt
    # umkehrbar, der gelieferte Wert ist aber auf **eine Stelle gerundet**, und
    # die Umkehrung multipliziert diesen Rest mit `tage_gesamt ÷ tage` — am
    # Monatsersten das 28- bis 31-Fache (gemessen: 1388,0 statt 1387,9 am 4.).
    # Im abgeschlossenen Monat ist der Wert identisch mit `soll_pv_kwh`.
    soll_pv_kwh_monat: Optional[float] = None

    # Grundlast (Nacht-Sockel; R12-1 ersetzt PVGIS-SOLL/IST). `grundlast_kwh` ist
    # additiv → Cockpit/Jahr summiert die Monate (analog soll_pv_kwh).
    grundlast_kw: Optional[float] = None              # Median der Nacht-Stunden-Leistung
    grundlast_kwh: Optional[float] = None             # geschätzte Grundlast-Energie (kW × 24 × Tage)
    grundlast_anteil_prozent: Optional[float] = None  # Anteil am Gesamtverbrauch

    # Betriebskosten (anteilig, Σ betriebskosten_jahr / 12 aller aktiven Investitionen)
    betriebskosten_anteilig_euro: Optional[float] = None
    #: Die beiden Summanden der Zeile darüber (A6). Die T-Konto-Zeile
    #: „Betriebskosten (anteilig)" erscheint GENAU DANN, wenn es keine
    #: Per-Investition-Zeilen gibt — der Anwender sieht die Summanden also
    #: nirgends sonst und braucht die Herleitung dort am nötigsten.
    betriebskosten_anteilig_jahr_euro: Optional[float] = None
    betriebskosten_anteilig_anzahl: Optional[int] = None

    # Per-Investition Finanzdetails (für T-Konto)
    investitionen_financials: list[InvestitionFinancialDetail] = []

    # Aktive Geräte je Typ im Monat (Namen) — macht in aggregierten Blöcken
    # kenntlich, woraus die Summe besteht (z. B. PV aus mehreren Strings + WR,
    # E-Mob aus Auto + Wallbox). Deckungsgleich mit der Aggregation (ist_aktiv_im_monat).
    komponenten_geraete: dict[str, list[str]] = {}

    # Quellenangabe pro Feld
    feld_quellen: dict[str, DatenquelleInfo] = {}

class SollPv(NamedTuple):
    """Das PVGIS-SOLL eines Monats in seinen zwei Lesarten.

    ``anteilig`` ist die Zahl, gegen die die Erfüllungsquote rechnet (N-69:
    Nenner auf die abgelaufenen Tage gekürzt). ``monat`` ist dieselbe Prognose
    **ungekürzt** — der Fortschritts-Bezug, den dietmar1968 vermisst hat
    (T89667 #155). Beide kommen aus **einem** Datenbank-Zugriff; der volle Wert
    wird bewusst nicht im Client zurückgerechnet, weil ``anteilig`` gerundet
    ausgeliefert wird und die Umkehrung den Rundungsrest mit
    ``tage_gesamt ÷ tage`` multipliziert.

    Im abgeschlossenen Monat sind beide gleich.
    """

    anteilig: Optional[float]
    monat: Optional[float]
