"""
Daten-Checker — Stammdaten, Strompreise & Investitionen (`StammdatenChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date, timedelta
from typing import Optional

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.utils.investition_filter import sort_investitionen_nach_typ
from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN
from backend.core.investition_kennwerte import get_speicher_kapazitaet_kwh
from backend.core.investition_parameter import (
    BKW_EINSPEISEGRENZE_W_TYPISCH,
    PARAM_E_AUTO,
    PARAM_PV_MODULE,
    PARAM_SPEICHER,
    PARAM_WAERMEPUMPE,
    ist_dienstlich,
)
from backend.core.berechnungen import (
    pruefe_speicher_netzladung_kumulativ,
    speicher_effizienz_prozent,
)
from backend.core.berechnungen.alternativkosten import ersetzt_keine_heizung
from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT
from backend.core.field_definitions import (
    get_speicher_netzladung_kwh,
    ist_zaehler_kategorie,
)
from backend.core.investition_parameter import PARAM_SONSTIGES as _PARAM_SONSTIGES
from backend.core.investition_kennwerte import (
    get_bkw_kwp,
    get_pv_kwp,
    get_wr_grenze_kw,
)

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

# Ab diesem DC/AC-Verhältnis meldet der Stammdaten-Check. Bewusst weit oberhalb
# der üblichen Auslegung (1,1–1,3; Ost/West bis ~1,5, #354-Melder 1,38): bis
# dahin ist Überbelegung eine Entwurfsentscheidung, darüber wahrscheinlicher
# ein Pflegefehler. Entscheid Gernot 2026-08-04.
DC_AC_MELDESCHWELLE = 2.0

# Ab dieser auf ein Jahr hochgerechneten Einspeisemenge weist der Checker darauf
# hin, dass ein Tarif mit 0 ct/kWh rechnet (F-38, #382). Darunter schweigt er:
# Ein Nulleinspeisungs-System (BKW mit AC-Grenze ≤ Hausverbrauch) speist nur die
# Regelungstoleranz seines Wechselrichters ein — beim Melder ~5 kWh in fünf
# Monaten, also gut 12 kWh/Jahr. Die Schwelle liegt bewusst darüber und
# gleichzeitig weit unter jeder Anlage, bei der ein vergessener Vergütungssatz
# Geld kostet: 50 kWh sind bei üblichen 8 ct rund 4 € im Jahr.
EINSPEISUNG_MELDESCHWELLE_KWH_JAHR = 50.0

# Ab dieser Abweichung meldet der Checker, dass die gepflegte Anlagenleistung
# nicht zur Summe der Erzeuger-Investitionen passt (F-58, NoahPaulick T89667
# #188). 0,1 kWp ist dieselbe Toleranz, die die Modul-Detail-Rechenprobe
# darunter benutzt — sie fängt Rundung, nicht Pflege.
#
# ⚠ Verglichen wird gegen ZWEI Summen: mit und ohne Balkonkraftwerk. Passt der
# gepflegte Wert zu einer von beiden, schweigt der Checker. Grund: fachlich ist
# ein BKW eine eigene Anlage und gehört nicht in die kWp der Hauptanlage
# (N-76 Stufe 1, Entscheid Gernot 2026-08-04) — wer es trotzdem eingerechnet
# hat, hat aber nichts Falsches gemessen, sondern eine andere Konvention
# gewählt. Nur eine Zahl, die zu KEINER der beiden passt, ist ein Pflegefehler.
# Ohne diese Zweiseitigkeit bekäme jeder BKW-Anwender wieder die Meldung, die
# Stufe 1 gerade abgeschafft hat ([[feedback_daten_checker_kein_akzeptiert]]).
ANLAGENLEISTUNG_TOLERANZ_KWP = 0.1


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


class StammdatenChecks:
    """Prüfungen für Stammdaten, Strompreise und Investitions-Stammwerte."""

    # ─── Stammdaten ──────────────────────────────────────────────────────

    def _check_stammdaten(
        self,
        anlage: Anlage,
        pvgis_prognose: Optional[PVGISPrognose] = None,
        pr: float = 1.0,
        pr_count: int = 0,
    ) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.STAMMDATEN

        # Installationsdatum
        # ⚑ FEHLER, nicht Warnung (Bewertungsgrenze E4c, 2026-08-16): Dieses Datum
        # ist der Anker dafür, ab wann eedc überhaupt Zählerwerte erwartet. Fehlt
        # er, fällt der Erwartungsrahmen auf die Erzeuger bzw. auf die vorhandenen
        # Daten selbst zurück (`core/monats_luecken.ermittle_start_anker`) — eine
        # Lücke am Anfang kann dann niemand mehr sehen, weil der Anfang aus der
        # Lücke abgeleitet wird.
        if anlage.installationsdatum is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung="Installationsdatum nicht gesetzt",
                details=(
                    "Ohne dieses Datum weiß eedc nicht, ab wann es Zählerwerte für "
                    "Einspeisung und Netzbezug erwarten darf — eine fehlende Zeile "
                    "am Anfang der Historie fällt dann nicht auf. Trage die "
                    "Inbetriebnahme deiner Anlage ein."
                ),
                link="/einstellungen/anlage",
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung="Installationsdatum vorhanden",
            ))

        # N-243: Erzeuger, der ÄLTER ist als das Installationsdatum der Anlage.
        # Dann gab es Erzeugung, bevor die Anlage laut Stammdaten existierte —
        # eines der beiden Daten stimmt nicht, und der erwartete Monatsbereich
        # beginnt zu spät (der Anker ist seit N-243 das Installationsdatum).
        # ⚠ Dieser WARNUNGS-Befund bleibt bewusst auf Erzeuger beschränkt: Nur bei
        # ihnen stimmt wirklich eines der beiden Daten nicht (es gab Erzeugung,
        # bevor es die Anlage gab). Eine Wallbox, ein E-Auto oder eine Heizung aus
        # der Zeit vor der PV-Anlage ist dagegen der Normalfall und völlig korrekt
        # gepflegt — als Defekt gemeldet wäre das die F-30-Klasse und würde
        # Anwender zum Umdatieren drängen; genau das hat fridolin22 (Forum T77723
        # #773) getan und dabei die echte Historie seines Fahrzeugs verloren.
        #
        # ⚑ Ergänzt 2026-08-16 (Bewertungsgrenze E4b): Die anderen Typen bekommen
        # jetzt trotzdem eine Zeile — aber als INFO und mit umgekehrter Richtung
        # ("pflege Zählerwerte nach bzw. korrigiere das Anlagendatum", NICHT
        # "datiere das Gerät um"). Der Zustand ist zulässig und bleibt es; was ihn
        # erwähnenswert macht, ist die Auskunft, dass für die Zeit davor keine
        # Bilanz existiert. Siehe den Block direkt darunter.
        if anlage.installationsdatum is not None:
            fruehere = [
                inv for inv in (anlage.investitionen or [])
                if inv.typ in PV_ERZEUGER_TYPEN
                and inv.anschaffungsdatum is not None
                and inv.anschaffungsdatum < anlage.installationsdatum
            ]
            if fruehere:
                aeltester = min(fruehere, key=lambda i: i.anschaffungsdatum)
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=(
                        f"Erzeuger älter als die Anlage: "
                        f"{aeltester.anschaffungsdatum.strftime('%d.%m.%Y')}"
                    ),
                    details=(
                        f"„{aeltester.bezeichnung}“ wurde laut Anschaffungsdatum am "
                        f"{aeltester.anschaffungsdatum.strftime('%d.%m.%Y')} angeschafft, "
                        f"die Anlage ist aber erst ab dem "
                        f"{anlage.installationsdatum.strftime('%d.%m.%Y')} eingetragen"
                        + (f" ({len(fruehere)} Erzeuger betroffen)" if len(fruehere) > 1 else "")
                        + ". Für die Monate dazwischen fragt eedc keine Zählerwerte ab, "
                        "obwohl dort bereits Strom erzeugt wurde. Korrigiere das Datum, "
                        "das nicht stimmt — meist das Installationsdatum der Anlage."
                    ),
                    link="/einstellungen/anlage",
                ))

            # E4b: Geräte, die KEINE Erzeuger sind und älter als die Anlage. Das
            # ist zulässig und häufig — deshalb INFO (Auskunft), nicht WARNING
            # (Defekt). Gemeldet wird nicht das Gerät, sondern die Datenlage: Für
            # die Zeit vor der Anlage gibt es keine Einspeisungs- und
            # Netzbezugswerte und damit keine Bilanz; eedc kann für diese Monate
            # nicht sagen, ob der Strom gekauft oder selbst erzeugt war.
            aeltere_geraete = [
                inv for inv in (anlage.investitionen or [])
                if inv.typ not in PV_ERZEUGER_TYPEN
                and inv.anschaffungsdatum is not None
                and inv.anschaffungsdatum < anlage.installationsdatum
            ]
            if aeltere_geraete:
                aeltestes = min(aeltere_geraete, key=lambda i: i.anschaffungsdatum)
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung=(
                        f"Gerät älter als die Anlage: „{aeltestes.bezeichnung}“ seit "
                        f"{aeltestes.anschaffungsdatum.strftime('%d.%m.%Y')}"
                    ),
                    details=(
                        f"Deine Anlage ist seit dem "
                        f"{anlage.installationsdatum.strftime('%d.%m.%Y')} eingetragen"
                        + (
                            f" ({len(aeltere_geraete)} Geräte betroffen)"
                            if len(aeltere_geraete) > 1 else ""
                        )
                        + ". Das ist normal: Ein Auto oder eine Heizung aus der Zeit "
                        "vor der PV-Anlage ist der Regelfall. Für die Monate davor "
                        "liegen keine Einspeisungs- und Netzbezugswerte vor — eedc "
                        "kann dort nicht sagen, ob der Strom gekauft oder selbst "
                        "erzeugt war. Hast du Zählerwerte aus dieser Zeit, pflege sie "
                        "nach; stimmt das Datum der Anlage nicht, korrigiere dieses. "
                        "Datiere nicht das Gerät um — die Anschaffungshistorie ginge "
                        "verloren."
                    ),
                    link="/einstellungen/anlage",
                ))

        # Leistung kWp
        if not anlage.leistung_kwp or anlage.leistung_kwp <= 0:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung="Anlagenleistung fehlt oder ist 0",
                details="Leistung in kWp ist für alle Berechnungen erforderlich",
                link="/einstellungen/anlage",
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"Anlagenleistung: {anlage.leistung_kwp} kWp",
            ))

        # Koordinaten für PVGIS
        if anlage.latitude is None or anlage.longitude is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Keine Koordinaten hinterlegt",
                details="Koordinaten werden für die PVGIS-Solarprognose benötigt",
                link="/einstellungen/anlage",
            ))

        # Standort für Community-Vergleich
        if not anlage.standort_ort and not anlage.standort_plz:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Kein Standort hinterlegt (Ort/PLZ)",
                details="Wird für den Community-Benchmark-Vergleich nach Region benötigt",
                link="/einstellungen/anlage",
            ))

        # PV-Module vorhanden. Filter respektiert Stilllegungsdatum (#608
        # MartyBr): String-Verlegung zwischen Wechselrichtern wird über
        # stilllegungsdatum-Setzen + neue Investition erfasst — der alte
        # String soll dann nicht mehr zur Σ aktiver kWp beitragen.
        heute = date.today()
        pv_module = [i for i in anlage.investitionen if i.typ == "pv-module" and i.ist_aktiv_an(heute)]
        hat_bkw = any(i.typ == "balkonkraftwerk" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
        if not pv_module:
            if hat_bkw:
                # BKW-only Setup: kein Fehler, nur Hinweis
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung="Nur Balkonkraftwerk, keine PV-Module angelegt",
                    details="PVGIS-Prognose und String-Vergleich sind ohne PV-Module nicht verfügbar",
                    link="/einstellungen/investitionen",
                ))
            else:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung="Keine PV-Module als Investition angelegt",
                    details="PV-Module werden für Erzeugungs-Auswertung benötigt",
                    link="/einstellungen/investitionen",
                ))
        else:
            # Σ der installierten Modulleistung (DC) — **ohne** Balkonkraftwerk.
            #
            # Ein BKW ist fachlich eine EIGENE Anlage mit eigener
            # MaStR-Registrierung; seine Wp gehören nicht in die kWp der
            # Hauptanlage. Solange es mitgezählt wurde, bekam **jeder** Anwender
            # mit BKW hier eine Abweichungs-Meldung, ohne dass etwas falsch
            # gepflegt gewesen wäre — am eigenen Demo-Bestand 20,8 gegen 20,0
            # ([[feedback_daten_checker_kein_akzeptiert]], N-76).
            #
            # kWp über den SoT-Helper (#229-Klasse, N66): wer die Nennleistung
            # nur im Detail-Feld (`parameter`) gepflegt hat, hat in der Spalte
            # NULL stehen. Der frühere Spalten-Direktzugriff las dort 0 und
            # meldete eine Abweichung, die es nicht gibt.
            summe_kwp = sum(get_pv_kwp(m) for m in pv_module)
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"PV-Module: {summe_kwp:.1f} kWp ({len(pv_module)} Modul-Gruppen)",
                details=(
                    "Das Feld „Anlagenleistung“ meint die installierte "
                    "Modulleistung (DC). Ein Balkonkraftwerk zählt nicht mit — "
                    "es ist eine eigene Anlage."
                ),
            ))

            ergebnisse.extend(
                self._check_anlagenleistung_gegen_module(anlage, summe_kwp, heute)
            )

            ergebnisse.extend(self._check_dc_ac_verhaeltnis(anlage, pv_module, heute))

            # Ursache benennen statt nur die Summe (R22-2b, PN 89782 Rainer):
            # die Summenregel oben sagt „Anlagenleistung passt nicht zu den
            # Modulen" und lässt den Nutzer alle Strings durchsuchen. Wo
            # Modul-Details gepflegt sind, ist die Rechenprobe eindeutig — sie
            # zeigt den verursachenden String. Ergänzung, kein Ersatz: ohne
            # Modul-Details (optionale Felder) bleibt die Summenregel die
            # einzige Prüfung.
            for modul in pv_module:
                params = modul.parameter or {}
                anzahl = params.get(PARAM_PV_MODULE["ANZAHL_MODULE"])
                wp = params.get(PARAM_PV_MODULE["MODUL_LEISTUNG_WP"])
                if not anzahl or not wp:
                    continue
                berechnet = float(anzahl) * float(wp) / 1000
                gepflegt = get_pv_kwp(modul)
                if gepflegt and abs(berechnet - gepflegt) > 0.1:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{modul.bezeichnung}: Modul-Details passen nicht zur Leistung",
                        details=(
                            f"{int(anzahl)} Module × {int(wp)} Wp = {berechnet:.2f} kWp, "
                            f"eingetragen: {gepflegt:.2f} kWp"
                        ),
                        link="/einstellungen/investitionen",
                    ))

        # Performance Ratio Hinweis (PVGIS-Systemverluste ggf. zu hoch)
        if pr_count >= 6 and pr > 1.1 and pvgis_prognose:
            system_losses = pvgis_prognose.system_losses if pvgis_prognose.system_losses is not None else 14
            abweichung_pct = round((pr - 1) * 100)
            # Der Hinweis nannte bis 02.08. Befund und Handlung, aber nicht die
            # Folge — dietmar1968 (#89667/87): „Für den ersten Hinweis bräuchte
            # ich eine Erklärung." Ohne die Folge ist die angebotene Handlung
            # nicht zu bewerten: die Systemverluste sind eine ANNAHME der
            # Prognose, und sie zu senken hebt das SOLL. Damit fallen Performance
            # Ratio und jede SOLL-Erfüllung (Prognose-vs-IST, Jahresbericht),
            # ohne dass sich ein einziger IST-Wert ändert.
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"PVGIS-Systemverluste ggf. zu hoch ({system_losses:.0f}%)",
                details=(
                    f"Anlage produziert Ø {abweichung_pct}% mehr als die PVGIS-Prognose "
                    f"(Performance Ratio: {pr:.2f} über {pr_count} Monate). Die "
                    f"{system_losses:.0f}% sind eine Annahme der Prognose, keine Messung. "
                    f"Wirksam wird eine Änderung erst mit einem neuen PVGIS-Abruf "
                    f"(Solarprognose → „Neue Prognose abrufen“ → „Speichern & Aktivieren“). "
                    f"Folge: das SOLL steigt, deshalb sinken Performance Ratio und "
                    f"SOLL-Erfüllung in Prognose-vs-IST und im Jahresbericht — die "
                    f"IST-Werte bleiben unverändert. Die bisherige Prognose bleibt als "
                    f"Historie erhalten und lässt sich wieder aktivieren. Wer die "
                    f"Prognose bewusst als konservative Untergrenze behält, lässt sie "
                    f"stehen."
                ),
                link="/einstellungen/solarprognose",
            ))

        return ergebnisse

    def _check_anlagenleistung_gegen_module(
        self, anlage: Anlage, summe_pv_kwp: float, heute: date,
    ) -> list[CheckErgebnis]:
        """Passt die gepflegte Anlagenleistung zur Summe der Erzeuger? (F-58)

        **Warum es diese Prüfung wieder gibt.** `Anlage.leistung_kwp` ist der
        Nenner jeder spezifischen Kennzahl — spezifischer Ertrag, Performance
        Ratio, Auslastung, Doppelerfassungs-Verdacht. Bis zum 04.08. hielt ein
        Summenvergleich ihn gegen die Investitionen; mit N-76 Stufe 1 ist er
        entfallen, und danach hielt ihn **nichts** mehr. Der Setup-Wizard
        erzeugt die PV-Module *aus* diesem Feld — sie stimmen also anfangs
        überein und laufen erst auseinander, wenn jemand die Investitionen
        korrigiert.

        Genau das ist NoahPaulick passiert (T89667 #188, v4.0.26): Er hat eine
        ursprünglich gemeinsam erfasste Anlage getrennt und die PV-Module
        korrigiert. Der Referenzwert blieb stehen, und der Daten-Checker meldete
        ihm vier Tage „PV-Doppelerfassung" bei einem spezifischen Ertrag, der um
        den Faktor 2 danebenlag — während derselbe Checker die abweichende
        Anlagenleistung eine Zeile darüber als „OK" bestätigte.

        **Der Anwender behält seine Eingabe** (Entscheid Gernot 2026-08-24):
        eedc leitet den Wert nicht ab und überschreibt ihn nicht, es sagt nur,
        dass zwei seiner Angaben nicht zusammenpassen — und welche.

        Zur Zweiseitigkeit des Vergleichs siehe `ANLAGENLEISTUNG_TOLERANZ_KWP`.
        """
        from backend.core.berechnungen.anlagen_kwp import summe_erzeuger_kwp

        gepflegt = anlage.leistung_kwp or 0
        if gepflegt <= 0:
            return []  # der ERROR eine Prüfung darüber deckt das schon ab

        # Beide zulässigen Konventionen. `summe_pv_kwp` kommt vom Aufrufer und
        # ist bereits ohne BKW gerechnet — die zweite Summe holt es dazu.
        mit_bkw = summe_erzeuger_kwp(anlage.investitionen, heute, mit_bkw=True)
        if summe_pv_kwp <= 0 and mit_bkw <= 0:
            return []  # keine gepflegten Erzeuger — nichts zu vergleichen

        for summe in (summe_pv_kwp, mit_bkw):
            if summe > 0 and abs(gepflegt - summe) <= ANLAGENLEISTUNG_TOLERANZ_KWP:
                return []

        bkw_zusatz = (
            f" (mit Balkonkraftwerk {mit_bkw:.2f} kWp)"
            if mit_bkw > summe_pv_kwp + ANLAGENLEISTUNG_TOLERANZ_KWP else ""
        )
        return [CheckErgebnis(
            kategorie=CheckKategorie.STAMMDATEN.value,
            schwere=CheckSeverity.WARNING,
            meldung=(
                f"Anlagenleistung {gepflegt:.2f} kWp passt nicht zu den "
                f"Modulen ({summe_pv_kwp:.2f} kWp)"
            ),
            details=(
                f"Unter „Anlage“ stehen {gepflegt:.2f} kWp, die Summe der "
                f"angelegten PV-Module ergibt {summe_pv_kwp:.2f} kWp"
                f"{bkw_zusatz}. eedc rechnet den spezifischen Ertrag, die "
                "Performance Ratio und die Plausibilitätsprüfungen mit der "
                "Modulsumme — die Anlagenleistung geht dagegen an den "
                "Community-Vergleich. Solange beide auseinanderlaufen, "
                "vergleichst du dich dort mit einer anderen Anlagengröße als "
                "der, die du auswertest. Korrigiere den Wert, der nicht stimmt: "
                "die Anlagenleistung unter „Einstellungen → Anlage“ oder die "
                "Leistung der einzelnen Module unter „Investitionen“."
            ),
            link="/einstellungen/anlage",
        )]

    def _check_dc_ac_verhaeltnis(
        self, anlage: Anlage, pv_module: list, heute: date,
    ) -> list[CheckErgebnis]:
        """DC/AC-Verhältnis je Wechselrichter — meldet erst bei Unplausiblem.

        **Überbelegung ist der Normalfall, kein Mangel** (Entscheid Gernot
        2026-08-04, #354). Mehr Modulleistung als Wechselrichter-Leistung ist
        gewollte Auslegung: man tauscht Ertrag in der Mittagsspitze gegen
        Ertrag im Schwachlicht. Üblich sind 1,1–1,3, bei Ost/West bis etwa 1,5;
        der Melder von #354 liegt bei 1,38. Ein Check, der das anmeckert,
        erzieht den Anwender dazu, falsche Zahlen einzutragen, damit Ruhe ist.

        Gemeldet wird deshalb erst oberhalb von `DC_AC_MELDESCHWELLE` — dort ist
        die wahrscheinlichste Erklärung nicht mehr die Auslegung, sondern ein
        Pflegefehler: die Wechselrichter-Leistung steht im kWp-Feld des Strings
        (genau der Fall aus #354) oder umgekehrt.

        Die Prüfung trat 2026-08-04 an die Stelle des früheren Abgleichs
        „Σ Module ≠ Anlagenleistung", der Überbelegung gar nicht kannte und beim
        Balkonkraftwerk zusätzlich falsch-positiv meldete (N-76).

        ⚠ Sie ersetzt ihn **nicht** — das war der Fehler. DC/AC misst Module
        gegen Wechselrichter; niemand hielt danach die Anlagenleistung noch
        gegen irgendetwas, obwohl sie der Nenner jeder spezifischen Kennzahl
        ist. Den Abgleich selbst führt seit F-58 wieder
        {@link _check_anlagenleistung_gegen_module}, jetzt beidseitig (mit und
        ohne BKW) statt einseitig.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.STAMMDATEN

        wechselrichter = [
            i for i in anlage.investitionen
            if i.typ == "wechselrichter" and i.ist_aktiv_an(heute)
        ]
        if not wechselrichter:
            return ergebnisse

        for wr in wechselrichter:
            grenze_kw = get_wr_grenze_kw(wr)
            if not grenze_kw:
                continue
            dc_kwp = sum(
                get_pv_kwp(m) for m in pv_module
                if getattr(m, "parent_investition_id", None) == wr.id
            )
            if dc_kwp <= 0:
                continue
            verhaeltnis = dc_kwp / grenze_kw
            if verhaeltnis <= DC_AC_MELDESCHWELLE:
                continue
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{wr.bezeichnung}: Modulleistung ist mehr als das "
                        f"{DC_AC_MELDESCHWELLE:.0f}-fache der Wechselrichter-Leistung",
                details=(
                    f"{dc_kwp:.2f} kWp Module an {grenze_kw:.2f} kW "
                    f"(Verhältnis {verhaeltnis:.2f}). Überbelegung ist normal, "
                    f"dieses Verhältnis aber ungewöhnlich hoch — steht in einem "
                    f"„Leistung (kWp)“-Feld versehentlich die Wechselrichter-"
                    f"Leistung statt der Modulleistung?"
                ),
                link="/einstellungen/investitionen",
            ))

        return ergebnisse

    # ─── Strompreise ─────────────────────────────────────────────────────

    def _check_strompreise(
        self, anlage: Anlage, monatsdaten: list | None = None
    ) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.STROMPREISE

        # Nur allgemeine Tarife prüfen
        tarife = sorted(
            [s for s in anlage.strompreise if s.verwendung == "allgemein"],
            key=lambda s: s.gueltig_ab,
        )

        if not tarife:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung="Kein Strompreis vorhanden",
                details="Strompreise sind für Finanz-Auswertungen und ROI-Berechnungen erforderlich",
                link="/einstellungen/strompreise",
            ))
            return ergebnisse

        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.OK,
            meldung=f"{len(tarife)} Strompreis-Tarif(e) vorhanden",
        ))

        # ── Tarif ohne Einspeisevergütung, obwohl eingespeist wird ───────────
        # Seit 08.08.2026 belegt eedc das Feld mit **0** vor, statt einen
        # EEG-Satz aus der Anlagengröße zu raten (die Sätze ändern sich
        # laufend; den geltenden kennt nur der Betreiber). Damit die 0 nicht
        # still bleibt, meldet sie der Checker — aber nur, wenn tatsächlich
        # eingespeist wurde: 0 ct ist bei Volleinspeisung ohne Vergütung oder
        # nach dem Ende der EEG-Förderung ein richtiger Wert, und ein Hinweis,
        # den niemand abstellen kann, ist die P-6-Falle.
        # F-38 (#382 azywietz-web): Zwei Korrekturen an dieser Regel.
        #
        # (1) **Eine Schwelle.** Sie löste bei JEDER erfassten Kilowattstunde
        #     aus. Ein Balkonkraftwerk mit Nulleinspeisung (AC-Grenze ≤
        #     Hausverbrauch) speist trotzdem eine Regelungstoleranz ein — beim
        #     Melder ~5 kWh in fünf Monaten — und 0 ct ist dort der RICHTIGE
        #     Wert. Ohne Schwelle war das ein Hinweis, den nur ein FALSCHER
        #     Vergütungssatz abstellt: die P-6-Falle, vor der der Kommentar
        #     unter dieser Regel seit dem 08.08. selbst warnt.
        # (2) **Der Text fordert nicht mehr, er nennt die Rechenfolge.**
        #     Maßgabe Gernots (18.08.): „Was der Benutzer einträgt, wird
        #     gerechnet." Eine 0 im Feld ist eine Angabe, keine Nachlässigkeit
        #     — eedc bewertet sie nicht (`feedback_eedc_ist_nicht_die_strom_
        #     polizei`). Deshalb INFO statt WARNING: es liegt kein Datenfehler
        #     vor, sondern eine Folge der Eingabe.
        #
        # Was die Meldung trotzdem rechtfertigt: seit dem 08.08. belegt eedc das
        # Feld mit 0 VOR (statt einen EEG-Satz zu raten, Forum T89667 #122) —
        # „nie angefasst" und „bewusst 0" sind im Feld nicht unterscheidbar. Die
        # Zeile ist der Ersatz für diese fehlende Unterscheidung, nicht eine
        # Aufforderung.
        # #392: Tarife mit variabler Vergütung ausgenommen — dort ist der
        # Stammwert nur der Fallback, der Satz des Monats steht in
        # `Monatsdaten.einspeise_durchschnittspreis_cent`. Ein 0-ct-Stammwert
        # ist bei so einem Tarif keine „0-ct-Rechnung", und die Meldung wäre
        # durch keine richtige Eingabe abstellbar (P-6-Falle).
        gratis_tarife = [
            t for t in tarife
            if not t.einspeiseverguetung_cent_kwh
            and not getattr(t, "einspeisung_variabel", False)
        ]
        gratis_monate = [
            m for m in (monatsdaten or [])
            if (m.einspeisung_kwh or 0) > 0
            # Stichtag ist der Monatserste, wie bei `baue_finanz_zeile` —
            # über das geteilte P8-Prädikat statt handgeschriebener Vergleiche.
            and any(t.gilt_am(date(m.jahr, m.monat, 1)) for t in gratis_tarife)
        ]
        einspeisung_kwh = sum((m.einspeisung_kwh or 0) for m in gratis_monate)
        # Auf ein Jahr hochgerechnet, damit die Schwelle nicht von der Länge des
        # erfassten Zeitraums abhängt: fünf Monate mit 5 kWh sind dieselbe Lage
        # wie zwölf mit 12.
        jahres_einspeisung = (
            einspeisung_kwh * 12 / len(gratis_monate) if gratis_monate else 0.0
        )
        if gratis_monate and jahres_einspeisung >= EINSPEISUNG_MELDESCHWELLE_KWH_JAHR:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=(
                    f"{len(gratis_tarife)} Tarif(e) rechnen die Einspeisung mit "
                    f"0 ct/kWh"
                ),
                details=(
                    "eedc rechnet den Einspeise-Erlös dieser Zeiträume mit 0 ct/kWh — "
                    "so, wie es im Tarif steht; in Cockpit, ROI und Jahresbericht "
                    "bleibt er damit 0 €. Richtig ist das bei Nulleinspeisung, bei "
                    "unvergüteter Volleinspeisung und nach dem Ende der EEG-Förderung. "
                    "Wer eine Vergütung bekommt, trägt seinen Satz ein — bei "
                    "gestaffelter EEG-Vergütung den nach kWp gewichteten Mischsatz, "
                    "denn eedc rechnet flat mit dem Wert."
                ),
                link="/einstellungen/strompreise",
            ))

        # ── Monate MIT DATEN vor dem ersten Tarif ────────────────────────────
        # Diese rechnen still mit der Vorbelegung (NETZBEZUG_DEFAULT_CENT).
        # Der Fall entsteht regelmäßig bei Neuinstallationen: erst Monate aus
        # der HA-Statistik importieren, danach den Tarif anlegen — dessen
        # Formular schlägt „heute" als Gültigkeitsbeginn vor (Forum simon42
        # #89667/60). Bewusst an den DATEN gemessen, nicht am
        # `installationsdatum`: das ist nullable, und genau bei frischen
        # Installationen leer — die Prüfung wurde dann komplett übersprungen.
        erster_tarif_ab = tarife[0].gueltig_ab
        monate_ohne_tarif = [
            m for m in (monatsdaten or [])
            # Stichtag ist der Monatserste (`baue_finanz_zeile`): ein Tarif ab
            # dem 15. gilt erst für den Folgemonat.
            if erster_tarif_ab > date(m.jahr, m.monat, 1)
        ]
        if monate_ohne_tarif:
            aeltester = min((m.jahr, m.monat) for m in monate_ohne_tarif)
            ergebnisse.append(CheckErgebnis(
                # ERROR statt WARNING (Gernot, 2026-08-15): Der Fallback auf die
                # Vorbelegung ist als *Rechenweg* in Ordnung — eedc muss mit
                # irgendetwas rechnen —, aber das Ergebnis ist ein **geratener
                # Preis auf gemessenen Mengen**. Netto-Ertrag, ROI und
                # Jahresbericht dieser Monate tragen damit eine Zahl, die nicht
                # aus den Daten des Betreibers stammt; das ist ein Fehler und
                # keine Randnotiz. Auflösbar ist er in einem Schritt (Gültig-ab
                # des ältesten Tarifs zurückziehen), deshalb keine P-6-Falle.
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung=(
                    f"{len(monate_ohne_tarif)} Monat(e) mit Daten liegen vor dem "
                    f"ersten Tarif ({erster_tarif_ab.strftime('%m/%Y')})"
                ),
                details=(
                    f"Ab {aeltester[1]:02d}/{aeltester[0]} sind Werte erfasst, aber kein "
                    f"Strompreis hinterlegt — diese Monate rechnen mit der Vorbelegung "
                    f"{NETZBEZUG_DEFAULT_CENT:.0f} ct/kWh. Beim ältesten Tarif das "
                    f"Gültig-ab-Datum auf den Beginn der Daten zurücksetzen; die "
                    f"Auswertungen rechnen sofort neu."
                ),
                link="/einstellungen/strompreise",
            ))

        # ── Lücken ZWISCHEN Tarifen ──────────────────────────────────────────
        # Anker ist der früheste bekannte Betriebsbeginn: Inbetriebnahme oder
        # der erste Monat mit Daten, je nachdem was früher liegt.
        anker = [d for d in (
            anlage.installationsdatum,
            date(*min((m.jahr, m.monat) for m in monatsdaten), 1) if monatsdaten else None,
        ) if d]
        if anker:
            start = min(anker)
            for tarif in tarife:
                # Der führende Fall ist oben schon (präziser) gemeldet.
                if tarif.gueltig_ab > start and not (
                    monate_ohne_tarif and tarif.gueltig_ab == erster_tarif_ab
                ):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"Strompreis-Lücke: {start.strftime('%d.%m.%Y')} bis {tarif.gueltig_ab.strftime('%d.%m.%Y')}",
                        link="/einstellungen/strompreise",
                    ))
                # Nächster erwarteter Start (Tag nach gueltig_bis)
                if tarif.gueltig_bis:
                    start = tarif.gueltig_bis + timedelta(days=1)
                else:
                    start = date.today()  # Offenes Ende = aktuell gültig

        # ── Zwei Tarife derselben Verwendung mit IDENTISCHEM Gültig-ab ───────
        # B6 (#392-Rest, Prüfbericht 2026-08-22): `lade_tarife_fuer_anlage`
        # sortiert `gueltig_ab DESC` und nimmt den ersten je Verwendung — bei
        # Gleichstand entscheidet die DB-Reihenfolge, welcher Satz rechnet:
        # ein stummer Münzwurf. NUR dieser Gleichstand ist die Anomalie. Die
        # normale Tarif-Folge (neuer Satz beginnt, der alte bleibt offen) ist
        # der gestützte Weg — der jüngere gewinnt deterministisch ab seinem
        # Beginn — und bleibt bewusst ohne Meldung: eine Überlappungs-Warnung
        # darauf wäre eine Dauer-Meldung auf funktionierenden Anlagen
        # (P-6-Falle; gemessen 22.08.: kein Auto-Schließen beim Anlegen).
        nach_start: dict[tuple[str, date], list] = {}
        for t in anlage.strompreise:
            nach_start.setdefault(
                (t.verwendung or "allgemein", t.gueltig_ab), []
            ).append(t)
        for (verwendung, ab), gleich in sorted(nach_start.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if len(gleich) < 2:
                continue
            namen = ", ".join(
                t.tarifname or f"{t.netzbezug_arbeitspreis_cent_kwh:.1f} ct"
                for t in gleich
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{len(gleich)} Tarife ({verwendung}) beginnen am selben Tag "
                    f"({ab.strftime('%d.%m.%Y')})"
                ),
                details=(
                    f"Betroffen: {namen}. Bei gleichem Gültig-ab-Datum ist nicht "
                    "bestimmt, welcher der Sätze rechnet — eedc nimmt einen der "
                    "beiden, ohne dass eine Regel entscheidet. Einen der Tarife "
                    "löschen oder sein Gültig-ab-Datum anpassen; danach ist die "
                    "Wahl eindeutig."
                ),
                link="/einstellungen/strompreise",
            ))

        # Spezialtarife prüfen (WP / E-Auto)
        verwendungen = {s.verwendung for s in anlage.strompreise}
        heute = date.today()
        hat_wp = any(i.typ == "waermepumpe" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
        hat_eauto = any(i.typ == "e-auto" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
        # Wer einen Einheitstarif hat — der Normalfall —, kann diesen Hinweis
        # durch keine Eingabe abstellen; genau deshalb kam die Bitte ums
        # Quittieren (dietmar1968, Forum #89667/87). Quittieren ist
        # ausgeschlossen ([[feedback_daten_checker_kein_akzeptiert]]), und eine
        # schärfere Bedingung gibt es nicht: ein Wärmestrom-Tarif ist unabhängig
        # von jedem anderen Parameter, „habe ich nicht" ist im Datenmodell nicht
        # von „noch nicht eingetragen" zu unterscheiden. Also sagt der Hinweis,
        # was ohne ihn passiert, und dass Nichtstun in Ordnung ist — wie der
        # Ladetarif-Hinweis darunter. Die Meldung beschreibt seither einen
        # Zustand statt einen Mangel zu behaupten.
        if hat_wp and "waermepumpe" not in verwendungen:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Wärmepumpe rechnet mit dem allgemeinen Tarif",
                details=(
                    "Es ist kein Tarif mit Verwendung „Wärmepumpe“ hinterlegt — "
                    "der WP-Strom wird deshalb mit dem allgemeinen Arbeitspreis "
                    "bewertet. Wer einen eigenen Wärmestrom-Tarif hat (§14a, "
                    "separater Zähler), ergänzt ihn hier. Wer einen Einheitstarif "
                    "hat, muss nichts tun: die Rechnung stimmt dann bereits, und "
                    "dieser Hinweis bleibt als Information stehen."
                ),
                link="/einstellungen/strompreise",
            ))
        # Ladetarif hängt an der Verwendung `wallbox` — „e-auto" gibt es als
        # Verwendung nicht (`Strompreis.verwendung`: allgemein | waermepumpe |
        # wallbox), das Formular bietet sie nicht an und
        # `resolve_strompreis_for_komponente` kennt sie auch nicht. Der Hinweis
        # war damit unerfüllbar: er stand bei jedem E-Auto dauerhaft, ohne dass
        # ihn irgendeine Eingabe hätte abstellen können. Was ein Anwender
        # wirklich hinterlegen kann und was gelesen wird, ist der Wallbox-Tarif
        # — beide Dashboards ziehen ihn („E-Auto lädt über Wallbox",
        # investitionen/dashboards.py). Wallbox ohne E-Auto zählt genauso: der
        # Ladetarif hängt am Ladepunkt.
        hat_wallbox = any(i.typ == "wallbox" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
        if (hat_eauto or hat_wallbox) and "wallbox" not in verwendungen:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Kein Ladetarif hinterlegt",
                details="E-Auto/Wallbox vorhanden – bei eigenem Ladetarif einen "
                        "Strompreis mit Verwendung „Wallbox“ ergänzen. Ohne ihn "
                        "rechnet eedc die Ladung mit dem allgemeinen Tarif.",
                link="/einstellungen/strompreise",
            ))

        # Plausibilität der Werte
        for tarif in tarife:
            name = tarif.tarifname or f"ab {tarif.gueltig_ab.strftime('%d.%m.%Y')}"
            preis = tarif.netzbezug_arbeitspreis_cent_kwh
            if preis is not None and (preis < 5 or preis > 80):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"Arbeitspreis ungewöhnlich: {preis:.1f} ct/kWh ({name})",
                    details="Erwarteter Bereich: 5–80 ct/kWh",
                    link="/einstellungen/strompreise",
                ))

            verg = tarif.einspeiseverguetung_cent_kwh
            if verg is not None and (verg < 0 or verg > 30):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"Einspeisevergütung ungewöhnlich: {verg:.1f} ct/kWh ({name})",
                    details="Erwarteter Bereich: 0–30 ct/kWh",
                    link="/einstellungen/strompreise",
                ))

        return ergebnisse

    # ─── Investitionen ───────────────────────────────────────────────────

    def _check_speicher_kapazitaet_einheit(
        self, inv, name: str, kap_kwh, alle_invs
    ) -> list[CheckErgebnis]:
        """Wh statt kWh — erkannt am **Widerspruch**, nicht an einer Schwelle (N-235).

        Das Balkonkraftwerk fragt seine Akku-Kapazität in **Wh**
        (`BalkonkraftwerkFelder.tsx`, „z.B. 1600 Wh für Anker SOLIX"), die
        Speicher-Investition daneben in **kWh** (`SpeicherFelder.tsx`). Wer den
        Zahlenwert von oben nach unten überträgt, liegt um **Faktor 1000**
        daneben — und nichts fiel bisher auf: Vollzyklen, Auslastung,
        Speicher-ROI und die Ladeprognose rechnen still gegen einen Nenner,
        den es nicht gibt. Real eingetreten bei azywietz-web (Discussion #366,
        11.08.2026): Anker Solarbank 3 mit 5.376 **Wh**, in eedc als 5.376
        **kWh** geführt.

        **Warum keine absolute Obergrenze** (Entscheid Gernot 11.08.2026): Eine
        Grenze „mehr als X kWh ist unplausibel" wäre geraten und meldete bei
        einer echten Großanlage dauerhaft falsch — und eine Meldung, die man
        nicht wegklicken kann, muss richtig sein
        ([[feedback_daten_checker_kein_akzeptiert]]). Hier braucht es keine:
        Zwei gepflegte Felder desselben Geräts tragen **denselben Zahlenwert**
        in zwei Einheiten. Ein Speicher mit 5.376 kWh neben einem
        Balkonkraftwerk mit 5.376 Wh existiert nicht.

        Gemeldet wird nur, was der Anwender selbst auflösen kann — mit der
        Zahl, die er eintragen soll. **Kein stiller Umbau seiner Daten.**
        """
        ergebnisse: list[CheckErgebnis] = []
        if kap_kwh is None or kap_kwh <= 0:
            return ergebnisse

        parent_id = getattr(inv, "parent_investition_id", None)
        if not parent_id:
            return ergebnisse

        # Wie in `_check_bkw_akku_erfassungsweg`: über die bereits geladene
        # Liste, NICHT über die `parent`-Beziehung — die ist nicht eager
        # geladen, ein Zugriff wäre im Async-Kontext ein MissingGreenlet.
        parent = next(
            (p for p in (alle_invs or []) if p.id == parent_id and p.typ == "balkonkraftwerk"),
            None,
        )
        if parent is None:
            return ergebnisse

        roh_wh = (parent.parameter or {}).get("speicher_kapazitaet_wh")
        try:
            wh = float(roh_wh)
        except (TypeError, ValueError):
            return ergebnisse
        if wh <= 0:
            return ergebnisse

        # Derselbe Zahlenwert in zwei Einheiten. Toleranz nur gegen
        # Tipp-/Rundungsnähe (5376 vs. 5375), nicht als Schwelle.
        if abs(wh - kap_kwh) > max(1.0, wh * 0.01):
            return ergebnisse

        def _de(wert: float, nachkomma: int) -> str:
            return f"{wert:_.{nachkomma}f}".replace(".", ",").replace("_", ".")

        ergebnisse.append(CheckErgebnis(
            kategorie=CheckKategorie.INVESTITIONEN,
            schwere=CheckSeverity.WARNING,
            meldung=f"{name}: Kapazität vermutlich in Wh statt kWh eingetragen",
            details=(
                f"„{parent.bezeichnung}“ nennt {_de(wh, 0)} Wh, dieser Speicher "
                f"{_de(kap_kwh, 0)} kWh — derselbe Zahlenwert in zwei Einheiten. "
                f"Gemeint sind vermutlich {_de(wh / 1000.0, 3)} kWh. Solange die "
                "Kapazität tausendfach zu groß ist, rechnen Vollzyklen, Auslastung "
                "und die Wirtschaftlichkeit des Speichers gegen einen Nenner, den "
                "es nicht gibt."
            ),
            link="/einstellungen/investitionen",
            investition_id=inv.id,
        ))
        return ergebnisse

    def _check_wechselrichter_pv_altbestand(
        self, inv, name: str, sensor_mapping: dict,
    ) -> list[CheckErgebnis]:
        """Eine alte PV-Zuordnung am Wechselrichter — und wohin sie gehoert.

        Der Wechselrichter ist **kein PV-Erzeuger** (Entscheid 24.08.2026,
        Begruendung in `core/field_definitions.py`). Sein `pv_erzeugung_kwh`
        traegt seither `nur_bestand`: nicht mehr pflegbar, nur noch sichtbar,
        solange eine Zuordnung daran haengt.

        ⚠ **Warum WARNING und nicht INFO** — anders als beim BKW-Akku
        (`_check_bkw_akku_erfassungsweg`, dort INFO): Dort liegen die Werte
        vor und werden angezeigt, nur eben monatlich. Hier wird der Sensor
        **von niemandem gelesen**, und schlimmer: solange er hing, meldete die
        Zuordnungs-Flaeche die PV als abgedeckt (er besetzte die Gruppe
        `pv_energie`). Die Live-Kachel fiel dadurch auf die Hochrechnung aus der
        Leistung zurueck — beim Melder von #388 rund 31 % zu hoch. Das ist ein
        Defekt in seinen Zahlen, keine Auskunft.

        Gemeldet wird beides, was es geben kann: eine **Sensor-Zuordnung** und
        ein von Hand gepflegter **Monatswert**. Nichts wird angefasst
        ([[feedback_kein_grosser_heiler_knopf]]); der Text nennt die Handlung.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        inv_map = ((sensor_mapping or {}).get("investitionen") or {})
        eintrag = inv_map.get(str(inv.id)) or inv_map.get(inv.id) or {}
        felder = (eintrag.get("felder") or {}) if isinstance(eintrag, dict) else {}
        zuordnung = felder.get("pv_erzeugung_kwh")
        hat_zuordnung = bool(
            zuordnung.get("entity_id") if isinstance(zuordnung, dict) else zuordnung
        )

        monate = sorted(
            (imd.jahr, imd.monat)
            for imd in (inv.monatsdaten or [])
            if (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh") is not None
        )
        if not hat_zuordnung and not monate:
            return ergebnisse

        teile: list[str] = []
        if hat_zuordnung:
            teile.append(
                "Am Wechselrichter haengt ein PV-Zaehler. Er wird nicht "
                "ausgewertet: eedc fuehrt die PV-Erzeugung an den PV-Modulen "
                "und -- fuer die ganze Anlage -- unter Anlage (Basis) als "
                "PV-Erzeugung Zaehlerstand."
            )
        if monate:
            von = f"{monate[0][1]:02d}/{monate[0][0]}"
            bis = f"{monate[-1][1]:02d}/{monate[-1][0]}"
            zeitraum = von if len(monate) == 1 else f"{von} bis {bis}"
            teile.append(
                f"Fuer {len(monate)} Monate ({zeitraum}) ist hier ausserdem ein "
                "PV-Monatswert von Hand gepflegt. Auch er zaehlt nirgends mit."
            )
        teile.append(
            "So gehoert es zugeordnet: Misst du je String, dann am jeweiligen "
            "PV-Modul. Hast du nur einen Zaehler fuer die ganze Anlage, dann "
            "unter Einstellungen -> Datenquellen in der Gruppe Anlage (Basis) "
            "bei PV-Erzeugung Zaehlerstand -- eedc verteilt die Menge dann "
            "nach kWp auf deine Module. "
            "Die alte Zuordnung kannst du danach entfernen; sie bleibt so "
            "lange sichtbar, bis du sie loeschst."
        )
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING,
            meldung=f"{name}: PV-Zuordnung am Wechselrichter wird nicht ausgewertet",
            details=" ".join(teile),
            link="/einstellungen/datenquellen",
        ))
        return ergebnisse

    def _check_bkw_akku_erfassungsweg(self, inv, name: str, alle_invs) -> list[CheckErgebnis]:
        """Weist Weg-B-Altbestand auf den Kanon hin — mit benannter Handlung.

        Ein BKW-Akku wird als **eigene Speicher-Investition mit Parent
        Balkonkraftwerk** erfasst (Kanon seit 2026-07-31): nur so hat er
        Live-Leistung, Ladestand, Energiefluss-Knoten und Tages-/Stundenwerte.
        Die BKW-eigenen Felder `speicher_ladung_kwh`/`speicher_entladung_kwh`
        kennen nur einen Monatswert und sind seither `nur_manuell` — erfassbar,
        aber nicht mehr zuordenbar (`core/field_definitions.py`).

        Gemeldet wird NUR, wer die alten Felder tatsächlich gepflegt hat und
        noch kein Speicher-Kind am BKW hängen hat. Kein stiller Umbau seiner
        Daten ([[feedback_kein_grosser_heiler_knopf]]), sondern ein Hinweis mit
        Handlung ([[feedback_reparatur_statt_loesch_features]]) — die gepflegten
        Werte bleiben unangetastet und weiter sichtbar.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        # Hängt schon ein Speicher am BKW? Dann ist der Anwender auf Weg A.
        # Bewusst über die bereits geladene Investitions-Liste statt über die
        # `children`-Backref: die ist NICHT eager-geladen (`__init__.py` lädt
        # `Anlage.investitionen` + `Investition.monatsdaten`), ein Zugriff wäre
        # im Async-Kontext ein Lazy-Load und damit ein MissingGreenlet-Fehler.
        if any(
            k.typ == "speicher" and k.parent_investition_id == inv.id
            for k in (alle_invs or [])
        ):
            return ergebnisse

        monate = sorted(
            (imd.jahr, imd.monat)
            for imd in (inv.monatsdaten or [])
            if any(
                (imd.verbrauch_daten or {}).get(f) is not None
                for f in ("speicher_ladung_kwh", "speicher_entladung_kwh")
            )
        )
        if not monate:
            return ergebnisse

        von = f"{monate[0][1]:02d}/{monate[0][0]}"
        bis = f"{monate[-1][1]:02d}/{monate[-1][0]}"
        zeitraum = von if len(monate) == 1 else f"{von} bis {bis}"
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO,
            meldung=f"{name}: Akku-Werte nur als Monatswert erfasst",
            details=(
                f"Für {len(monate)} Monate ({zeitraum}) sind Lade-/Entlademengen "
                "direkt am Balkonkraftwerk gepflegt. In dieser Form gibt es sie "
                "nur monatlich — im Live-Dashboard, im Tagesverlauf und im "
                "Energiefluss fehlt der Akku. "
                "Empfohlen: den Akku zusätzlich als eigene Investition vom Typ "
                "„Speicher“ anlegen und unter „Gehört zu“ "
                "dieses Balkonkraftwerk wählen; die Lade-/Entladesensoren "
                "dann dort zuordnen. "
                "Die bereits gepflegten Monatswerte bleiben erhalten und werden "
                "weiter angezeigt — es geht nichts verloren."
            ),
            link="/einstellungen/investitionen",
        ))
        return ergebnisse

    def _check_investitionen(self, anlage: Anlage, monatsdaten: list[Monatsdaten]) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        # Reihenfolge nach Typ (#214 detLAN: WP vor Wallbox), nicht DB-ID.
        # Stilllegungsdatum-Filter via `ist_aktiv_an` (#608 Sweep): stillgelegte
        # Investitionen brauchen keine Stamm-Daten-Pflege mehr — Ausrichtung,
        # kWp, Anschaffungskosten sind dann historisch fixiert oder irrelevant.
        heute = date.today()
        aktive = sort_investitionen_nach_typ(i for i in anlage.investitionen if i.ist_aktiv_an(heute))
        if not aktive:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Keine aktiven Investitionen vorhanden",
                link="/einstellungen/investitionen",
            ))
            return ergebnisse

        # PV-Erzeugung anlagenweit prüfen (kWp-Verteilung-Etappe): gemessen=OK,
        # über Aggregat verteilt=INFO, Teil-Lücke=WARNING, gar keine PV-Quelle=
        # ERROR. Ersetzt die frühere Pro-Modul-„fehlt"-WARNING — ein einzelner
        # Gesamtwert (Monatsdaten.pv_erzeugung_kwh) deckt jetzt alle Strings ab.
        ergebnisse.extend(self._check_pv_erzeugung(anlage, monatsdaten))

        for inv in aktive:
            name = f"{inv.bezeichnung} ({inv.typ})"
            param = inv.parameter or {}
            # IA-V4 #243: alle in diesem Durchlauf erzeugten Befunde (inkl. der
            # _check_*_monatsdaten-Helper) dieser Investition zuordnen — der
            # Komponenten-Hub filtert darauf. Tagging am Schleifenende, da das
            # anlagenweite _check_pv_erzeugung VOR der Schleife läuft.
            _start = len(ergebnisse)

            # Typ-spezifische Prüfungen
            if inv.typ == "pv-module":
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

            elif inv.typ == "balkonkraftwerk":
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
                            f"Die Module leisten {modul_w:.0f} W. Ohne die "
                            "Wechselrichter-Leistung rechnet die Prognose mit dieser "
                            "vollen Leistung — bei Überbelegung (z. B. 1.260 W Module "
                            "an 600 W Wechselrichter) fällt sie dadurch zu hoch aus. "
                            "Mit gepflegtem Wert wird stündlich gekappt."
                        ),
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "pv_erzeugung_kwh", "PV-Erzeugung", CheckSeverity.WARNING, monatsdaten,
                ))
                ergebnisse.extend(
                    self._check_bkw_akku_erfassungsweg(inv, name, anlage.investitionen)
                )

            elif inv.typ == "speicher":
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
                    if not param.get("lade_durchschnittspreis_cent"):
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: Arbitrage aktiv, aber Ø Ladepreis fehlt",
                            details="Wird für Arbitrage-Einsparungsberechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))
                    if not param.get("entlade_vermiedener_preis_cent"):
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: Arbitrage aktiv, aber Ø Entladepreis fehlt",
                            details="Wird für Arbitrage-Einsparungsberechnung benötigt",
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
                        link="/einstellungen/monatsdaten",
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
                        f"Über die gesamte Historie stehen {gesamt_entladung_kwh:.0f} kWh "
                        f"Entladung gegen {gesamt_ladung_kwh:.0f} kWh Ladung "
                        f"({_eta:.0f} %). Ein Speicher kann nicht mehr abgeben, als er "
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
                        link="/einstellungen/monatsdaten",
                    ))

            elif inv.typ == "e-auto":
                # Dienstwagen: keine PV-Ladungs-/ROI-Checks (kein PV-Bezug, kein Invest)
                if ist_dienstlich(param):
                    continue
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
                # Kanon seit v3.25.0: `v2h_faehig` (im Code selbst als „Bug #1
                # v3.25.0" vermerkt, s. `live_komponenten_builder.py`). Bis
                # 2026-08-23 stand hier `nutzt_v2h` — dieser Prüfer hat damit
                # nie gemeldet.
                if (
                    param.get(PARAM_E_AUTO["V2H_FAEHIG"])
                    and not param.get(PARAM_E_AUTO["V2H_ENTLADE_PREIS_CENT"])
                ):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: V2H aktiv, aber Entladepreis fehlt",
                        details="Wird für V2H-Einsparungsberechnung benötigt",
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "ladung_pv_kwh", "Ladung PV", CheckSeverity.INFO, monatsdaten,
                ))

            elif inv.typ == "wallbox":
                if not param.get("max_ladeleistung_kw") and not param.get("leistung_kw"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Ladeleistung (kW) fehlt",
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "ladung_kwh", "Ladung gesamt", CheckSeverity.INFO, monatsdaten,
                ))

            elif inv.typ == "wechselrichter":
                if not param.get("max_leistung_kw") and not param.get("leistung_ac_kw"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Leistung (kW) fehlt",
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_wechselrichter_pv_altbestand(
                    inv, name, anlage.sensor_mapping or {},
                ))

            elif inv.typ == "waermepumpe":
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
                # `core/field_definitions.py:722` bewusst an der Bauart bleiben:
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
                            meldung=f"{name}: JAZ unplausibel ({jaz:.1f})",
                            details="Typischer Bereich: 1,5–7,0 (Luft-WP ca. 2,5–4,5, Sole-WP ca. 3,5–5,5)",
                            link="/einstellungen/investitionen",
                        ))
                elif effizienz_modus == "scop":
                    scop_h = param.get("scop_heizung")
                    scop_ww = param.get("scop_warmwasser")
                    if scop_h is None or scop_ww is None:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: SCOP-Werte fehlen (Modus: EU-Label SCOP)",
                            details="SCOP Heizung und SCOP Warmwasser werden für Einsparungs-Berechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))
                elif effizienz_modus == "getrennte_cops":
                    cop_h = param.get("cop_heizung")
                    cop_ww = param.get("cop_warmwasser")
                    if cop_h is None or cop_ww is None:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: COP-Werte fehlen (Modus: Getrennte COPs)",
                            details="COP Heizung und COP Warmwasser werden für Einsparungs-Berechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))

                # Alter Energieträger / Preis für Vergleichsrechnung
                alter_preis = param.get("alter_preis_cent_kwh")
                if alter_preis is None and not ersetzt_nichts:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Alter Energiepreis nicht gesetzt",
                        details="Wird für Einsparungs-Berechnung vs. Gas-/Ölheizung benötigt",
                        link="/einstellungen/investitionen",
                    ))

                # Wärmebedarf für Jahres-Einsparungsschätzung
                if not param.get("heizwaermebedarf_kwh") and not ersetzt_nichts:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Heizwärmebedarf nicht gesetzt",
                        details="Wird für Jahres-Einsparungsschätzung verwendet (kWh/Jahr)",
                        link="/einstellungen/investitionen",
                    ))

                # Monatsdaten-Vollständigkeit der WP prüfen
                ergebnisse.extend(
                    self._check_wp_monatsdaten(inv, name, param, monatsdaten)
                )

            # Allgemeine Prüfungen für alle Typen
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
            # (#377). `investitionen/dashboards.py` schließt ihn ausdrücklich
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

            for _e in ergebnisse[_start:]:
                _e.investition_id = inv.id

        return ergebnisse
