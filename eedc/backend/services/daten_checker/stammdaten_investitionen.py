"""
Daten-Checker — die Investitions-Prüfungen je Typ (RF-19, Serie „Funktion vor Datei“).

Der Orchestrator `StammdatenChecks._check_investitionen` bleibt in `stammdaten.py` — dort rufen ihn die Tests,
dort liest er `date.today()` (aktive Investitionen, Wallbox heute in Betrieb), dort stehen die Typ-Weiche, der
Dienstwagen-Sprung (`continue`: kein weiterer Befund für das Gerät) und das Tagging je Gerät (IA-V4 #243).
Hier stehen seine Phasen, wortgleich umgezogen: je Investitionstyp eine Methode und die Prüfungen für alle
Typen. Meldung, Schwere, Kategorie und Link jeder Zeile sind Anwender-Verträge (Handbuch Daten-Checker §4.3);
die Reihenfolge der Meldungen ergibt sich aus der Aufrufreihenfolge im Orchestrator.

Die Phasen sind Methoden (Mixin), weil sie Prüfungen anderer Mixins des Pakets rufen
(`_check_investition_monatsdaten`, `_check_wp_monatsdaten`, `_check_werte_in_nicht_gefuehrten_feldern`) und
die Typ-Helfer, die in `stammdaten.py` stehen (`_check_speicher_kapazitaet_einheit`,
`_check_bkw_akku_erfassungsweg`, `_check_wechselrichter_pv_altbestand`).
"""

from typing import Optional

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.core.investition_kennwerte import (
    get_bkw_kwp,
    get_pv_kwp,
    get_speicher_kapazitaet_kwh,
    get_wr_grenze_kw,
)
from backend.core.investition_parameter import (
    BKW_EINSPEISEGRENZE_W_TYPISCH,
    PARAM_E_AUTO,
    PARAM_SPEICHER,
    PARAM_WAERMEPUMPE,
)
from backend.core.investition_parameter import PARAM_SONSTIGES as _PARAM_SONSTIGES
from backend.core.berechnungen import (
    pruefe_speicher_netzladung_kumulativ,
    speicher_effizienz_prozent,
)
from backend.core.berechnungen.alternativkosten import ersetzt_keine_heizung
from backend.core.field_definitions import (
    URTEIL_GILT,
    feld_urteil,
    get_speicher_netzladung_kwh,
    ist_zaehler_kategorie,
)

from .kategorien import CheckErgebnis, CheckSeverity, LINK_MONATSDATEN
from backend.core.zahlenformat import fmt_zahl


def _effizienz_achsen_hinweis(
    param: dict, praefix: str, kennzahl: str, modus_text: str,
    heiz_gilt: bool, ww_gilt: bool,
) -> Optional[tuple[str, str]]:
    """Fehlt ein Effizienz-Wert auf einer Achse, die es am Gerät **gibt**?

    Gibt ``(meldung, details)`` ohne den Gerätenamen zurück — oder ``None``,
    wenn nichts zu melden ist.

    ⭐ **WK-15c (14.09.2026), Fund N-1 aus WK-15b.** Bis dahin verlangten beide
    Hinweise **beide** Werte, ohne zu fragen, ob das Gerät die Achsen hat:
    Eine **Brauchwasser**-Wärmepumpe wurde nach `scop_heizung`/`cop_heizung`
    gefragt (sie gibt keine Heizwärme ab), eine **Split-Klimaanlage** nach
    `scop_warmwasser`/`cop_warmwasser` (sie hat keinen Warmwasserkreis, N-304).
    Beides **WARNING** und nur durch eine erfundene Zahl abstellbar — genau der
    Fehler, den Handbuch §5/Schritt 7 uns zuschreibt, eine Stufe lauter als der
    Bedarfs-Hinweis, den WK-15b abgeräumt hat. Die Zahl bewegt an der fehlenden
    Achse ohnehin nichts: `berechne_waermepumpe_einsparung` multipliziert sie
    dort mit einer Menge, die seit WK-15c **0** ist.

    ⚠ **Der Wortlaut bleibt, wo beide Achsen gelten** — an einer klassischen
    Wärmepumpe steht dieselbe Meldung wie immer, auch wenn nur einer der beiden
    Werte fehlt (Bestand, bitgleich). Nur wo das Gerät **eine** Achse hat, nennt
    die Meldung sie: sonst hieße „SCOP-Werte fehlen" dort *ein* Wert, und der
    Anwender suchte den zweiten.
    """
    achsen = (
        ("Heizung", f"{praefix}_heizung", heiz_gilt, "Heiz-Achse"),
        ("Warmwasser", f"{praefix}_warmwasser", ww_gilt, "Warmwasser-Achse"),
    )
    fehlend = [a for a in achsen if a[2] and param.get(a[1]) is None]
    if not fehlend:
        return None
    if heiz_gilt and ww_gilt:
        return (
            f"{kennzahl}-Werte fehlen (Modus: {modus_text})",
            f"{kennzahl} Heizung und {kennzahl} Warmwasser werden für "
            f"Einsparungs-Berechnung benötigt",
        )
    label, _key, _gilt, _achse = fehlend[0]
    fehlende_achse = next(a for a in achsen if not a[2])
    return (
        f"{kennzahl} {label} fehlt (Modus: {modus_text})",
        f"{kennzahl} {label} wird für die Einsparungs-Berechnung benötigt. "
        f"Nach {kennzahl} {fehlende_achse[0]} fragt eedc an diesem Gerät nicht "
        f"— es hat keine {fehlende_achse[3]}.",
    )


def _ist_zaehler(inv) -> bool:
    """Ist das ein *Sonstiges*-Gerät der Kategorie ``zaehler`` (#377)?

    Bewusst NICHT `zaehlerstaende.ist_zaehler_investition` importiert: Dieses
    Modul hängt sonst am Zählerstände-Service, der seinerseits Snapshots und
    `InvestitionMonatsdaten` lädt — für eine reine Typfrage ein zu schwerer
    Import. Die **Entscheidung** kommt trotzdem aus dem einen SoT
    (`ist_zaehler_kategorie`), nur der Zugriff auf den Parameter steht hier.
    """
    if inv.typ != "sonstiges":
        return False
    return ist_zaehler_kategorie(
        (inv.parameter or {}).get(_PARAM_SONSTIGES["KATEGORIE"])
    )


class StammdatenInvestitionenChecks:
    """Phasen von `StammdatenChecks._check_investitionen`: je Investitionstyp eine, dazu «alle Typen» (RF-19)."""

    def _check_typ_pv_module(
        self, kat, inv, name: str,
    ) -> list[CheckErgebnis]:
        """PV-Module: Leistung (kWp) und Ausrichtung/Neigung."""
        ergebnisse: list[CheckErgebnis] = []
        if not get_pv_kwp(inv):  # #229-Klasse (N66): Spalte ODER Detail-Feld
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Leistung (kWp) fehlt",
                link="/einstellungen/investitionen",
            ))
        if not inv.ausrichtung or inv.neigung_grad is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"{name}: Ausrichtung/Neigung fehlt",
                details="Wird für PVGIS-Solarprognose benötigt",
                link="/einstellungen/investitionen",
            ))
        # PV-Erzeugungs-Vollständigkeit: anlagenweit in
        # _check_pv_erzeugung (kWp-Verteilung) — hier NICHT pro Modul
        # prüfen, sonst meldet jeder String „fehlt", obwohl ein
        # Gesamt-Aggregat alle deckt.
        return ergebnisse

    def _check_typ_balkonkraftwerk(
        self, kat, inv, name: str, param: dict, anlage: Anlage, monatsdaten: list[Monatsdaten],
    ) -> list[CheckErgebnis]:
        """Balkonkraftwerk: Leistung, Wechselrichter-Grenze (#347), PV-Erzeugung (N-651), Akku-Erfassungsweg."""
        ergebnisse: list[CheckErgebnis] = []
        if not param.get("leistung_wp"):
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Leistung (Wp) fehlt",
                link="/einstellungen/investitionen",
            ))
        # #347: Überbelegung ist beim BKW der Normalfall. Ohne gepflegte
        # Wechselrichter-Leistung kappt die Prognose nicht und rechnet
        # mit der vollen Modulleistung — an sonnigen Tagen mehr, als das
        # Gerät je einspeisen kann. Gemeldet wird erst oberhalb der
        # typischen Einspeisegrenze: darunter ist Überbelegung
        # unwahrscheinlich und der Hinweis wäre reines Nörgeln.
        modul_w = get_bkw_kwp(inv) * 1000
        if (
            modul_w > BKW_EINSPEISEGRENZE_W_TYPISCH
            and get_wr_grenze_kw(inv) is None
        ):
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Wechselrichter-Leistung fehlt",
                details=(
                    f"Die Module leisten {fmt_zahl(modul_w, 0)} W. Ohne die "
                    "Wechselrichter-Leistung rechnet die Prognose mit dieser "
                    "vollen Leistung — bei Überbelegung (z. B. 1.260 W Module "
                    "an 600 W Wechselrichter) fällt sie dadurch zu hoch aus. "
                    "Mit gepflegtem Wert wird stündlich gekappt."
                ),
                link="/einstellungen/investitionen",
            ))
        # N-651: „PV-Erzeugung fehlt" nur, wenn weder ein eigener Wert noch ein Anlagenwert
        # (`Monatsdaten.pv_erzeugung_kwh`, der Anlagenzähler) den Monat trägt. Ohne eigenen Zähler bekommt das
        # Balkonkraftwerk seinen kWp-Anteil am Rest des Anlagenwerts (P7, N-621) — das ist kein Fehlen. Bis
        # 10.10.2026 meldete der Checker hier eine Lücke neben der OK-Meldung der anlagenweiten PV-Prüfung.
        mit_anlagenwert = frozenset(
            (anlagenzeile.jahr, anlagenzeile.monat) for anlagenzeile in monatsdaten
            if anlagenzeile.pv_erzeugung_kwh is not None
        )
        ergebnisse.extend(self._check_investition_monatsdaten(
            inv, name, "pv_erzeugung_kwh", "PV-Erzeugung", CheckSeverity.WARNING, monatsdaten,
            gedeckt=mit_anlagenwert,
        ))
        ergebnisse.extend(
            self._check_bkw_akku_erfassungsweg(inv, name, anlage.investitionen)
        )
        return ergebnisse

    def _check_typ_speicher(
        self, kat, inv, name: str, param: dict, anlage: Anlage, monatsdaten: list[Monatsdaten],
    ) -> list[CheckErgebnis]:
        """Speicher: Kapazität (E16, N-235), Arbitrage-Preise, Ladung je Monat, Netzladung/Wirkungsgrad kumulativ."""
        ergebnisse: list[CheckErgebnis] = []
        # Diese Meldung ist die Bedingung, unter der `None` als
        # Helper-Rückgabe freigegeben wurde (E16): der fehlende Wert
        # wird ausgewiesen, statt dass irgendwo eine 10 entsteht.
        kap = get_speicher_kapazitaet_kwh(inv)
        if kap is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Kapazität (kWh) fehlt",
                link="/einstellungen/investitionen",
            ))
        ergebnisse.extend(
            self._check_speicher_kapazitaet_einheit(
                inv, name, kap, anlage.investitionen
            )
        )
        # Kanon seit v3.25.0: `arbitrage_faehig`. Bis 2026-08-23 stand
        # hier `nutzt_arbitrage` — der Name VOR der Umbenennung. Damit
        # war die Bedingung dauerhaft falsch und dieser Prüfer hat nie
        # gemeldet; ein Speicher mit aktivierter Arbitrage und fehlendem
        # Ø Ladepreis blieb unbeanstandet.
        if param.get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"]):
            # ⭐ Der Text nennt seit 2026-08-30 die GEMEINTE Größe
            # — die Präzisierung steht HINTER „fehlt", nicht davor:
            # die Kernaussage bleibt so als Satzteil zusammen, und
            # eine bestehende Gegenprobe sucht genau danach
            # (test_daten_checker_arbitrage_v2h_preise_397).
            # (rapahl, PN 91806). Es gibt zwei mit fast gleichem Namen,
            # und beide zu Recht:
            #   • `lade_durchschnittspreis_cent` — Stammdaten-Annahme,
            #     aus der Prognose und ROI rechnen (`aussichten/finanzen.py`,
            #     `investitionen/roi.py`). DAS prüft diese Zeile.
            #   • `speicher_ladepreis_cent` — der gemessene Monatswert,
            #     im Monatsabschluss erfassbar und per Sensor füllbar
            #     (`monats_fakten/`).
            # Er hatte den Sensor zugeordnet, sah daneben 24,79 ct
            # stehen und las die Meldung als Widerspruch. Sie war
            # richtig — sie sagte nur nicht, welchen Preis sie meint.
            if not param.get("lade_durchschnittspreis_cent"):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{name}: Arbitrage aktiv, aber Ø Ladepreis fehlt (Stammdaten-Wert)",
                    details=(
                        "Gemeint ist der Erwartungswert in den Stammdaten des "
                        "Speichers — aus ihm rechnen Prognose und ROI in die "
                        "Zukunft. Ein zugeordneter Preis-Sensor oder ein "
                        "gepflegter Monatswert ersetzt ihn nicht: der misst, "
                        "was war, dieser schätzt, was kommt."
                    ),
                    link="/einstellungen/investitionen",
                ))
            if not param.get("entlade_vermiedener_preis_cent"):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{name}: Arbitrage aktiv, aber Ø Entladepreis fehlt (Stammdaten-Wert)",
                    details=(
                        "Gemeint ist der Erwartungswert in den Stammdaten des "
                        "Speichers — der Preis, den eine entladene "
                        "Kilowattstunde vermeidet. Aus ihm rechnen Prognose "
                        "und ROI in die Zukunft; gemessene Monatswerte "
                        "ersetzen ihn nicht."
                    ),
                    link="/einstellungen/investitionen",
                ))
        ergebnisse.extend(self._check_investition_monatsdaten(
            inv, name, "ladung_kwh", "Speicher-Ladung", CheckSeverity.WARNING, monatsdaten,
        ))
        # #281 / rapahl-PN 2026-05-22: Netzladung darf die Gesamt-
        # ladung nicht übersteigen, sonst wäre der implizite PV-Anteil
        # negativ. KUMULATIV prüfen, nicht pro Monat: Netz- und Gesamt-
        # Ladungs-Zähler haben getrennte Monats-Schnappschüsse, ein
        # Ladevorgang über die Monatsgrenze (Tibber-Nachtladung) landet
        # beim einen Zähler noch im alten, beim anderen schon im neuen
        # Monat. Erst die Summe über die Historie ist aussagekräftig.
        gesamt_ladung_kwh = 0.0
        gesamt_netzladung_kwh = 0.0
        gesamt_entladung_kwh = 0.0
        for imd in inv.monatsdaten:
            vd = imd.verbrauch_daten or {}
            gesamt_ladung_kwh += float(vd.get("ladung_kwh") or 0.0)
            gesamt_netzladung_kwh += get_speicher_netzladung_kwh(vd)
            gesamt_entladung_kwh += float(vd.get("entladung_kwh") or 0.0)
        bericht = pruefe_speicher_netzladung_kumulativ(
            gesamt_ladung_kwh, gesamt_netzladung_kwh,
        )
        if not bericht.konsistent:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Netzladung übersteigt Gesamtladung (kumulativ)",
                details=bericht.details,
                # Kumulativ über die ganze Historie — es gibt keinen
                # einen Monat, der aufzuschlagen wäre.
                link=LINK_MONATSDATEN,
            ))

        # F-22 (rapahl-PN 2026-08-08, seine ZWEITE zu diesem Thema):
        # Der Layer klemmt den Wirkungsgrad bewusst nicht — „Diagnose
        # statt stillem Cap" (core/berechnungen/speicher.py). Die
        # Diagnose gab es bis v4.0.11 nirgends; der Cap war weg und
        # niemand sagte etwas. Hier ist sie.
        #
        # KUMULATIV, aus demselben Grund wie beim Netzladungs-Check:
        # ein EINZELNER Monat darf legitim über 100 % liegen, weil
        # Energie aus dem Vormonat abfließt. Über die ganze Historie
        # kann er es nicht — dort mittelt sich der Ladestand aus, und
        # mehr Entladung als Ladung heißt: eine der beiden Größen wird
        # falsch gemessen oder gepflegt.
        #
        # Die mit Abstand häufigste Ursache ist die aus #281: `ladung_kwh`
        # als reine PV-Ladung gepflegt, Netzladung separat daneben. Dann
        # ist der Nenner zu klein — und der Check oben schlägt NICHT an,
        # solange Netz < Gesamt bleibt. Deshalb steht das im Befundtext.
        #
        # Seit N-264 über den Diagnose-Helper statt inline: `speicher_
        # effizienz_prozent` ist genau für diesen einen Zweck gebaut
        # (ungekappt, damit man den Überschuss SIEHT) und hatte nach
        # N-252 sonst keinen Verwender mehr — ein ungenutzter Helper
        # neben einer handgeschriebenen Kopie derselben Formel ist die
        # Ausgangslage, aus der N-252 entstanden ist.
        if gesamt_ladung_kwh > 0 and gesamt_entladung_kwh > gesamt_ladung_kwh:
            _eta = speicher_effizienz_prozent(
                gesamt_ladung_kwh, gesamt_entladung_kwh
            ) or 0.0
            _hinweis = (
                f"Über die gesamte Historie stehen {fmt_zahl(gesamt_entladung_kwh, 1)} kWh "
                f"Entladung gegen {fmt_zahl(gesamt_ladung_kwh, 1)} kWh Ladung "
                f"({fmt_zahl(_eta, 0)} %). Ein Speicher kann nicht mehr abgeben, als er "
                "aufgenommen hat."
            )
            if gesamt_netzladung_kwh > 0:
                _hinweis += (
                    " Häufigste Ursache: „Ladung“ enthält nur die PV-Ladung. "
                    "Dort gehört die GESAMTE Ladung hinein — die Netzladung "
                    "ist ein Teil davon, kein zweiter Posten daneben."
                )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Entladung übersteigt Ladung (kumulativ)",
                details=_hinweis,
                link=LINK_MONATSDATEN,
            ))
        return ergebnisse

    def _check_typ_e_auto(
        self, kat, inv, name: str, param: dict, monatsdaten: list[Monatsdaten], hat_wallbox: bool,
    ) -> list[CheckErgebnis]:
        """E-Auto (privat; den Dienstwagen überspringt der Orchestrator): Fahrleistung, Alternativkosten, Ladung PV."""
        ergebnisse: list[CheckErgebnis] = []
        # Kanon seit v3.25.0: `jahresfahrleistung_km`. Bis 2026-08-23
        # stand hier `km_jahr` — der Vor-Umbenennungs-Name. Die linke
        # Hälfte der Bedingung war damit immer wahr, der Prüfer hing
        # allein am Verbrauch: Wer den Verbrauch gepflegt hatte, aber
        # keine Fahrleistung, bekam nie einen Hinweis.
        if (
            not param.get(PARAM_E_AUTO["JAHRESFAHRLEISTUNG_KM"])
            and not param.get(PARAM_E_AUTO["VERBRAUCH_KWH_100KM"])
        ):
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"{name}: Fahrleistung/Verbrauch fehlt",
                details="Wird für E-Auto Einsparungs-Berechnung benötigt",
                link="/einstellungen/investitionen",
            ))
        if inv.anschaffungskosten_alternativ is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Alternativkosten (Verbrenner) fehlen",
                details="Werden für ROI-Berechnung benötigt (Vergleich mit Verbrenner-Alternative)",
                link="/einstellungen/investitionen",
            ))
        # ⛔ HIER STAND EIN PRÜFER „V2H aktiv, aber Entladepreis fehlt"
        # — er ist mit #397 ERSATZLOS ENTFALLEN, und zwar bewusst.
        #
        # Seine Aussage war sachlich falsch: `v2h_entlade_preis_cent`
        # ist ein OVERRIDE, kein benötigter Wert. Ohne ihn rechnet
        # `dashboards.py` über `berechne_v2h_ersparnis` mit dem Spread
        # aus den GEPFLEGTEN Tarifen (Bezug − Einspeisevergütung) —
        # der belastbareren Grundlage. Wer dem Hinweis folgte,
        # ersetzte eine Messung durch eine Schätzung.
        #
        # Bis 2026-08-23 stand die Bedingung auf dem Vor-Kanon-Namen
        # `nutzt_v2h` und hat deshalb nie gemeldet; erst `4e97cc56`
        # machte sie scharf — und damit den Hinweis sichtbar, den es
        # nie hätte geben dürfen. Die Abwesenheit ist gewächtert
        # (`test_v2h_entladepreis_ist_kein_mangel_397`), sonst wäre
        # eine versehentliche Streichung von dieser hier
        # ununterscheidbar.
        #
        # ⚠ Abgrenzung zum Speicher (derselbe Fix, andere Antwort):
        # Dort sind Ø Lade-/Entladepreis KEIN Override, sondern die
        # einzige Quelle — Arbitrage lebt von zwei Preisen zu
        # verschiedenen UHRZEITEN, und ein eedc-Tarif kennt keine
        # Uhrzeit. Deshalb wurden die beiden Speicher-Felder pflegbar
        # gemacht, statt ihre Prüfer zu streichen.
        # F-64 (gruaGit, Discussion #396): NUR ohne Wallbox einfordern.
        # `core/field_definitions.py` gibt dem E-Auto-Feld
        # `ladung_pv_kwh` die Bedingung `bedingung_anlage:
        # "keine_wallbox"` — mit Wallbox ist SIE die kanonische Quelle
        # der Heimladung, und das Formular blendet das Feld am Fahrzeug
        # aus. Der Hinweis war damit unauflösbar: sein „Beheben"-Knopf
        # führt in ein Formular ohne dieses Feld, und wer den Wert
        # trotzdem einträgt, erzeugt die Doppelzählung, die die
        # Bedingung verhindern soll.
        # Dieselbe Regel steht ausformuliert in `energieprofil.py`
        # (`_check_tages_zusatzfelder`) — hier fehlte sie, dort nicht.
        # ⚑ N-555 Stufe 2 (26.09.2026): Seitdem bietet das Formular die
        # Heim-Felder auch neben einer Wallbox an (Konzept Regel 8) — die
        # Bedingung hier bleibt trotzdem: mit Wallbox trägt SIE den Rest,
        # eine Messung am Auto ist dort freiwillig und nichts, was fehlt.
        if not hat_wallbox:
            ergebnisse.extend(self._check_investition_monatsdaten(
                inv, name, "ladung_pv_kwh", "Ladung PV", CheckSeverity.INFO, monatsdaten,
            ))
        return ergebnisse

    def _check_typ_wallbox(
        self, kat, inv, name: str, param: dict, monatsdaten: list[Monatsdaten],
    ) -> list[CheckErgebnis]:
        """Wallbox: Ladeleistung und Ladung gesamt je Monat."""
        ergebnisse: list[CheckErgebnis] = []
        if not param.get("max_ladeleistung_kw") and not param.get("leistung_kw"):
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Ladeleistung (kW) fehlt",
                link="/einstellungen/investitionen",
            ))
        ergebnisse.extend(self._check_investition_monatsdaten(
            inv, name, "ladung_kwh", "Ladung gesamt", CheckSeverity.INFO, monatsdaten,
        ))
        return ergebnisse

    def _check_typ_wechselrichter(
        self, kat, inv, name: str, param: dict, anlage: Anlage,
    ) -> list[CheckErgebnis]:
        """Wechselrichter: Leistung (Kanon und Alt-Name) und PV-Altbestand (#388)."""
        ergebnisse: list[CheckErgebnis] = []
        if not param.get("max_leistung_kw") and not param.get("leistung_ac_kw"):
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Leistung (kW) fehlt",
                link="/einstellungen/investitionen",
            ))
        ergebnisse.extend(self._check_wechselrichter_pv_altbestand(
            inv, name, anlage.sensor_mapping or {},
        ))
        return ergebnisse

    def _check_typ_waermepumpe(
        self, kat, inv, name: str, param: dict, monatsdaten: list[Monatsdaten],
    ) -> list[CheckErgebnis]:
        """Wärmepumpe: Alternativkosten (F-41), Effizienz (WK-15c), alter Preis, Bedarf (WK-15b), Monatswerte."""
        ergebnisse: list[CheckErgebnis] = []
        # F-41 (#383 azywietz-web, 18.08.): Bis v4.0.20 hingen DREI
        # Hinweise an EINEM Prädikat — der **Bauart**
        # (`ist_luft_luft_waermepumpe`). Das war an beiden Enden falsch:
        #
        # * **Falsch-positiv:** Jede Wärmepumpe im **Neubau** bekam die
        #   zwei INFO, obwohl „Nichts ersetzt (Neubau)" gepflegt war —
        #   wozu das Investitionsformular ausdrücklich rät. Sie waren
        #   nicht auflösbar, und ein Hinweis, den der Anwender nicht
        #   auflösen kann, ist ein Fehler bei uns
        #   ([[feedback_daten_checker_kein_akzeptiert]]).
        # * **Falsch-negativ:** Eine Klimaanlage, mit der jemand
        #   **tatsächlich heizt**, bekam sie nie zu sehen — obwohl ihre
        #   Ersparnis genau daran hängt (N-88/F2b, Gernot 16.08.).
        #
        # Seit v4.0.18 ist die Frage ein Feld: `alter_energietraeger`.
        # Die Rechnung respektiert es an sieben Stellen, der Checker
        # nicht. **Messbarkeit → Bauart, Bewertbarkeit → Pflege** —
        # deshalb fragen diese beiden INFO ab jetzt `ersetzt_keine_heizung`,
        # während `daten_checker/energieprofil.py:419`,
        # `daten_checker/monatsdaten.py:848` und
        # `core/field_definitions/registry.py::INVESTITION_FELDER` bewusst an der Bauart bleiben:
        # Sie fragen nach einem **Wärmemengenzähler**, den ein
        # Splitgerät physisch nicht hat. Konzept: `docs/KONZEPT-263-klima-split.md` §7 E-C.
        ersetzt_nichts = ersetzt_keine_heizung(
            param.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
        )

        # Die WARNING hängt an KEINER der beiden Achsen — und das ist der
        # dritte Teil von F-41. `anschaffungskosten_alternativ` fragt
        # „Was hättest du stattdessen kaufen müssen?" und speist über
        # `core/berechnungen/investitionskosten.py` die
        # USt-Bemessungsgrundlage, den Amortisations-Fortschritt und die
        # Amortisationsdauer. Mit *Ersetzen* hat das nichts zu tun: Ein
        # Neubau ersetzt keine Heizung, hat aber trotzdem keinen
        # Gaskessel gekauft. Negativbeweis: in `investitionskosten.py`
        # und allen weiteren Lesestellen des Feldes kommt
        # `alter_energietraeger` 0-mal vor.
        #
        # Auflösbar war sie immer (eine 0 genügt, die Prüfung ist
        # `is None`) — sie hat es nur nicht gesagt. Der Defekt ist die
        # **Beschriftung**; derselbe Zusatz steht seit jeher an fünf
        # anderen Investitionstypen (`investitionFormHelpers.ts`).
        if inv.anschaffungskosten_alternativ is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: Alternativkosten (Gas-/Ölheizung) fehlen",
                details=(
                    "Was hätte eine neue Gas-/Ölheizung gekostet? eedc zieht "
                    "diesen Betrag von den Anschaffungskosten ab — nur die "
                    "Differenz muss sich amortisieren. Gab es keine "
                    "Alternative (z. B. im Neubau), trag 0 ein; das ist eine "
                    "gültige Antwort und lässt den Hinweis verschwinden."
                ),
                link="/einstellungen/investitionen",
            ))

        # Welche Wärme-Achsen hat dieses Gerät? — **die Registry
        # antwortet, nie die Bauart** (ADR-002/P13, SOLL Wärme/Klima R1).
        # Beide Fragen stehen hier oben, weil zwei Prüfungen darunter sie
        # brauchen: die Effizienz-Werte (WK-15c/N-1) und der Bedarf
        # (WK-15b/F-1). **Warum `feld_urteil`** und nicht
        # `groesse_gibt_es_am_geraet` oder `feld_herabgestuft`: siehe den
        # Kommentar am Bedarf weiter unten — dort steht die Messung.
        heiz_achse_gilt = feld_urteil(
            "waermepumpe", "heizenergie_kwh", param,
        ) == URTEIL_GILT
        ww_achse_gilt = feld_urteil(
            "waermepumpe", "warmwasser_kwh", param,
        ) == URTEIL_GILT

        # Effizienz-Parameter je nach Berechnungsmodus prüfen
        effizienz_modus = param.get("effizienz_modus", "gesamt_jaz")
        if effizienz_modus == "gesamt_jaz":
            jaz = param.get("jaz")
            if jaz is None:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{name}: JAZ nicht gesetzt",
                    details="Jahresarbeitszahl wird für COP-Berechnung der Heizenergie benötigt",
                    link="/einstellungen/investitionen",
                ))
            elif not (1.5 <= jaz <= 7.0):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{name}: JAZ unplausibel ({fmt_zahl(jaz, 1)})",
                    details="Typischer Bereich: 1,5–7,0 (Luft-WP ca. 2,5–4,5, Sole-WP ca. 3,5–5,5)",
                    link="/einstellungen/investitionen",
                ))
        elif effizienz_modus in ("scop", "getrennte_cops"):
            # WK-15c/N-1: gefragt wird nur nach Achsen, die es am Gerät
            # gibt — die Registry entscheidet das, nicht die Bauart.
            hinweis = _effizienz_achsen_hinweis(
                param,
                *(("scop", "SCOP", "EU-Label SCOP")
                  if effizienz_modus == "scop"
                  else ("cop", "COP", "Getrennte COPs")),
                heiz_gilt=heiz_achse_gilt, ww_gilt=ww_achse_gilt,
            )
            if hinweis:
                meldung, details = hinweis
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{name}: {meldung}",
                    details=details,
                    link="/einstellungen/investitionen",
                ))

        # Alter Energieträger / Preis für Vergleichsrechnung
        alter_preis = param.get("alter_preis_cent_kwh")
        if alter_preis is None and not ersetzt_nichts:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"{name}: Alter Energiepreis nicht gesetzt",
                details=(
                    "Wird für die Einsparungs-Berechnung gegenüber der "
                    "ersetzten Heizung benötigt (#411: der Träger ist "
                    "gepflegt — Gas, Öl oder Strom-Direktheizung)."
                ),
                link="/einstellungen/investitionen",
            ))

        # Wärmebedarf für Jahres-Einsparungsschätzung
        #
        # ⚠ **Zwei Fragen, nicht eine** — die zweite fehlte bis zum
        # 14.09.2026 (WK-15/F-1). `ersetzt_nichts` oben beantwortet die
        # **Bewertbarkeit** („gibt es eine Altanlage?"); unbeantwortet
        # blieb die **Messbarkeit**: *Hat dieses Gerät die Größe
        # überhaupt?* Eine Brauchwasser-Wärmepumpe gibt keine Heizwärme
        # ab — die Registry sagt das seit A6 (`heizenergie_kwh` trägt
        # `!brauchwasser`), und der Monats-Checker fragt sie seit B2
        # (`_check_wp_monatsdaten`). Dieser Block fragte gar nichts.
        #
        # Gemessen am „Stiebel Eltron WWK 300" (Prüfstand-Lage F, Demo-DB
        # r28 **und** HAOS-Lab): INFO „Heizwärmebedarf nicht gesetzt",
        # obwohl `docs/HANDBUCH_WAERME_KLIMA.md` §6/F wörtlich zusagt
        # *„… die Heiz-Achse wird weder angeboten noch erwartet, und der
        # Daten-Checker verlangt sie nicht."* Abstellen konnte der
        # Anwender den Hinweis nur, indem er eine Zahl **erfindet** —
        # genau das nennt Handbuch §5/Schritt 7 einen Fehler bei uns
        # ([[feedback_daten_checker_kein_akzeptiert]]).
        # **Klasse N-86/N-304:** eine Regel gilt auf einer Fläche und auf
        # der zweiten nicht.
        #
        # ⛔ Deshalb steht hier die **Registry** und keine `wp_art`-Frage
        # (ADR-002/P13, SOLL Wärme/Klima R1: die Bauart entscheidet keine
        # Größe). ⚠ Und zwar `feld_urteil`, **nicht**
        # `groesse_gibt_es_am_geraet`: das liefert für `heizenergie_kwh`
        # an einer Brauchwasser-WP `True` (gemessen), denn die Bedingung
        # ist dort **weich** — „untypisch, nicht unmöglich", wer doch
        # einen kleinen Heizkreis hat, trägt ihn unter *Weitere Größen
        # erfassen* ein. Für den Lesepfad ist das richtig, für diese
        # Frage zu weit. ⚠ Ebenso wenig `feld_herabgestuft`: das ist auch
        # an der **Klimaanlage** wahr (kein Wärmemengenzähler möglich),
        # und die soll den Hinweis behalten — wer mit ihr heizt, braucht
        # den Bedarf für seine Ersparnis (N-88/F2b).
        if not ersetzt_nichts:
            if heiz_achse_gilt:
                # N-2 (WK-15c): auch ein gepflegter **Gesamtbedarf**
                # beantwortet die Frage — die JAZ-Rechnung liest ihn vor
                # der Summe aus Heiz- und Warmwasserbedarf. Die
                # Warmwasser-INFO darunter kannte ihn seit WK-15b, diese
                # hier nicht; zwei Hinweise, eine Frage, eine Antwort.
                if not param.get("heizwaermebedarf_kwh") and not param.get("waermebedarf_kwh"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Heizwärmebedarf nicht gesetzt",
                        details="Wird für Jahres-Einsparungsschätzung verwendet (kWh/Jahr)",
                        link="/einstellungen/investitionen",
                    ))
            # Ohne Heiz-Achse **fällt die Frage nicht weg, sie wechselt
            # die Achse.** Dieselbe Schätzung läuft für ein solches Gerät
            # über den Warmwasserbedarf: `_wp_nicht_bewertbar`
            # (`investitionen/roi.py`) lässt die ROI-Zeile nur mit
            # **einem** gepflegten Bedarf überhaupt rechnen und schreibt
            # sonst „Nicht bewertet: kein Wärmebedarf gepflegt" — ohne
            # diesen Zweig stünde der Anwender vor genau dieser Zeile,
            # und kein Hinweis sagte ihm mehr, welches Feld sie meint.
            # Es bleibt bei **einem** Hinweis je Gerät; er nennt nur die
            # Achse, die dieses Gerät hat.
            #
            # `waermebedarf_kwh` (Gesamtbedarf, kein Formularfeld, kommt
            # aus Importen) zählt mit — die JAZ-Rechnung dort liest ihn
            # **vor** der Summe aus Heiz- und Warmwasserbedarf; wer ihn
            # gepflegt hat, dem fehlt nichts.
            elif (
                ww_achse_gilt
                and not param.get("warmwasserbedarf_kwh")
                and not param.get("waermebedarf_kwh")
            ):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung=f"{name}: Warmwasserbedarf nicht gesetzt",
                    details=(
                        "Wird für Jahres-Einsparungsschätzung verwendet "
                        "(kWh/Jahr). Nach dem Heizwärmebedarf fragt eedc "
                        "an diesem Gerät nicht — es hat keine Heiz-Achse."
                    ),
                    link="/einstellungen/investitionen",
                ))

        # Monatsdaten-Vollständigkeit der WP prüfen
        ergebnisse.extend(
            self._check_wp_monatsdaten(inv, name, param, monatsdaten)
        )
        return ergebnisse

    def _check_alle_typen(
        self, kat, inv, name: str, param: dict,
    ) -> list[CheckErgebnis]:
        """Für jeden Typ: Werte in nicht geführten Feldern (N-393), Anschaffungsdatum, Anschaffungskosten (D3)."""
        ergebnisse: list[CheckErgebnis] = []
        # N-393: ein gespeicherter Wert in einem Feld, das dieses Gerät nach
        # seinen Einstellungen nicht (mehr) führt — für JEDEN Typ, nicht nur
        # die Klimaanlage (die war bis 05.09.2026 der einzige Fall, N-379).
        ergebnisse.extend(
            self._check_werte_in_nicht_gefuehrten_feldern(inv, name, param)
        )
        if inv.anschaffungsdatum is None:
            # v4.0.1: von INFO auf ERROR hochgestuft. Ohne das Datum zählt die
            # Komponente in JEDER Auswertung über den gesamten Zeitraum mit —
            # auch vor der Anschaffung ([[feedback_anschaffungsdatum_grenze]])
            # — und die Amortisationskurve hat keinen Nullpunkt (`basis_jahr`).
            # Für neue Investitionen ist das Feld seither Pflicht; hier geht es
            # um Bestand, deshalb Sprung direkt in dessen Formular.
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung=f"{name}: Anschaffungsdatum fehlt",
                details=(
                    "Ohne Anschaffungsdatum zählt die Komponente auch für Zeiträume "
                    "vor der Anschaffung mit, und die Amortisationsrechnung hat "
                    "keinen Startpunkt."
                ),
                link=f"/einstellungen/komponenten?bearbeiten={inv.id}",
            ))

        # ⛔ **Verbrauchszähler ausgenommen (D3, 22.08.2026, Entscheid
        # Gernot).** Die Begründung dieser INFO lautet „Werden für
        # ROI-Berechnung benötigt" — und für einen Gas-, Wasser- oder
        # Ölzähler stimmt sie nicht: Er wird **erfasst, nicht bewertet**
        # (#377). `investitionen/dashboard_sonstiges.py` schließt ihn ausdrücklich
        # aus der Wirtschaftlichkeit aus, mit genau diesem Satz; Gas- und
        # Wasserkosten sind Haushaltskosten und gehören nicht in die
        # Bewertung der PV-Anlage.
        #
        # Ein Hinweis mit erfundenem Grund ist die schlechtere Sorte
        # Falschmeldung: Er lässt sich nur durch eine Eingabe abstellen, die
        # anschließend nirgends gelesen wird
        # ([[feedback_daten_checker_kein_akzeptiert]]).
        #
        # ⚠ Das **Anschaffungsdatum** bleibt bewusst Pflicht (ERROR oben) —
        # es begrenzt den Zeitraum, in dem das Gerät zählt, und diese Frage
        # hat auch ein Zähler (Konzept #377 §8, Entscheid 2).
        if inv.anschaffungskosten_gesamt is None and not _ist_zaehler(inv):
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"{name}: Anschaffungskosten fehlen",
                details="Werden für ROI-Berechnung benötigt",
                link="/einstellungen/investitionen",
            ))
        return ergebnisse
