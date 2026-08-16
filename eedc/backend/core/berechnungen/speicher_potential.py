"""Hätte ein größerer Speicher etwas gebracht? — die gedeckelte Antwort.

**Warum diese Datei existiert (#358 Phase 2, gemessen 2026-08-12):**
`docs/archive/KONZEPT-SPEICHER-AUSWERTUNG.md` §2 schlug dafür vor::

    ungenutztes_potential_kwh = Σ (einspeisung an Tagen mit SoC_max ≥ 95 %)

Diese Zahl beantwortet ihre eigene Frage **nicht**. An zwölf Junitagen der
Dev-Anlage ergibt sie **471 kWh** „ungenutztes Potential" — die Einspeisung fällt
dort fast vollständig in Stunden mit vollem Speicher. Gleichzeitig fiel der
Speicher in **keiner** dieser Nächte unter **31 %**. Wer daraufhin Kapazität
dazukauft, hat am nächsten Morgen mehr Restladung und gibt sie **nie** ab: der
reale Nutzen ist null, während die Kennzahl 471 kWh ausweist. Im Winter kippt es
in die Gegenrichtung (November: SoC-Maximum 2 %) — dort fehlt die Sonne, nicht
der Speicher.

**Der begrenzende Faktor ist nicht die Sonne, sondern die Nacht.** Zusätzliche
Kapazität nützt nur, wenn beides zusammenkommt:

1. Es war Überschuss da, den der volle Speicher nicht mehr aufnehmen konnte, und
2. der Speicher lief vor dem nächsten Sonnenaufgang **leer**, sodass die
   zusätzliche Ladung auch wieder abgegeben worden wäre.

Deshalb ist die Kennzahl hier ein **Minimum aus beidem**, je Lade-Entlade-Zyklus.
Sie fällt kleiner aus als die naive Summe — das ist ihr Zweck: eine Zahl, an der
eine Kaufentscheidung hängt, darf nicht größer sein als der Nutzen, den sie
verspricht (Gernots Entscheid 2026-08-12; die Alternative „naive Summe mit
Kleingedrucktem" wurde ausdrücklich verworfen).

**Was diese Kennzahl NICHT ist:** eine Simulation. Sie sagt, wie viel ein
beliebig großer Speicher an den beobachteten Tagen **höchstens** zusätzlich
durchgesetzt hätte — nicht, welche Kapazität dafür nötig gewesen wäre und was sie
gekostet hätte. Das ist Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

#: Ab hier gilt der Speicher als voll — Überschuss geht dann zwangsläufig ins Netz.
#: 95 % statt 100 %, weil Hersteller-SoC oben abflacht (Balancing) und ein
#: Speicher praktisch nie exakt 100 % meldet.
SOC_VOLL_PROZENT = 95.0

#: Ab hier gilt er als leer, **wenn nichts Genaueres bekannt ist**. Symmetrisch
#: gedacht, aber aus einem anderen Grund: unterhalb der Entladetiefe-Reserve gibt
#: das Gerät nichts mehr ab, der gemeldete Rest-SoC ist für das Haus nicht
#: verfügbar.
#:
#: ⚠ **Als feste Zahl war das ein Fehler** (#379, kingcap1/Glen, gemessen
#: 2026-08-15). Wer eine eigene Entlade-Untergrenze fährt — bei ihm 20 % —, dessen
#: Speicher erreicht diese 5 % **nie**. Dann bleibt `lief_leer` False, die
#: Fehlmenge bleibt 0, und `nutzbar_kwh = min(überschuss, 0)` ist **strukturell**
#: 0: Die Sicht behauptet „ein größerer Speicher hätte nichts gebracht", obwohl
#: sie es gar nicht messen konnte. Sein Beleg: 4.974 kWh Überschuss bei vollem
#: Speicher, 0/207 Nächte „leer", während seine SoC-Kurve nachts auf 21 %
#: läuft und dort dreht — der Speicher **war** aufgebraucht.
#:
#: Deshalb ist dieser Wert nur noch der **Rückfall**; die tatsächliche Schwelle
#: kommt aus `leer_schwelle_prozent()`.
SOC_LEER_PROZENT = 5.0

#: Obergrenze der abgeleiteten Schwelle. Eine „Reserve", die mehr als die Hälfte
#: der Brutto-Kapazität beansprucht, ist keine Reserve mehr, sondern mit hoher
#: Wahrscheinlichkeit ein Pflegefehler (die N-235-Klasse: Wh gegen kWh, gleicher
#: Zahlenwert). Ohne diesen Deckel würde ein einziger vertippter Wert den halben
#: Ladestandsbereich als „leer" gelten lassen und die Kennzahl in die
#: **Gegenrichtung** verfälschen — zu hoch statt zu niedrig.
SOC_LEER_MAX_PROZENT = 50.0

#: Aufschlag auf die **abgeleitete** Schwelle, in Prozentpunkten.
#:
#: ⚠ **Beim Bau gemessen, nicht angenommen:** Glens Speicher ist auf 20 %
#: Untergrenze eingestellt, seine SoC-Kurve dreht bei **21 %**. Eine harte
#: `<= 20`-Grenze trifft ihn damit **nie** — der Fehler aus #379 wiederholte sich
#: eine Etage tiefer, nur mit einer anderen Zahl. Drei Gründe, alle systematisch
#: in dieselbe Richtung: Wechselrichter schalten mit Puffer ab, der SoC wird in
#: ganzen Prozent gemeldet, und diese Auswertung liest **Stundenmittel** — der
#: tatsächliche Tiefpunkt liegt zwischen zwei Stundenwerten.
#:
#: **Gilt ausdrücklich nur für die abgeleitete Schwelle, nie für den Rückfall.**
#: Auf 5 % addiert würde er Bestandszahlen bewegen, und „wer nichts pflegt, sieht
#: das Verhalten von vorher" ist Abnahmekriterium dieses Baus. Der Rückfall ist
#: ohnehin schon ein großzügiges „praktisch leer" — kein Gerät entlädt auf 0 —,
#: während die abgeleitete Grenze ein exakter Sollwert ist, den das Gerät mit
#: Puffer einhält.
SOC_LEER_TOLERANZ_PP = 3.0


def leer_schwelle_prozent(
    kapazitaet_brutto_kwh: Optional[float],
    nutzbare_kapazitaet_kwh: Optional[float],
) -> float:
    """Ab welchem Ladestand gibt **dieser** Speicher nichts mehr ab?

    Leitet die Schwelle aus dem Verhältnis der beiden gepflegten Kapazitäten ab:
    ``(1 − nutzbar ÷ brutto) × 100``. Bei 24 von 30 kWh sind das 20 % — genau die
    Untergrenze, die der Anwender eingestellt hat.

    **Warum kein eigenes Eingabefeld** (Entscheid Gernot 2026-08-15): Das Feld
    `nutzbare_kapazitaet_kwh` gibt es seit v4.0.2, es steht im Speicher-Formular
    und trägt genau diese Aussage. Ein zweites Feld „Entladegrenze %" wäre
    dieselbe Information ein zweites Mal — und damit die Drift-Klasse, gegen die
    hier gerade gebaut wird.

    **Die Annahme, und sie ist bewusst:** die Reserve sitzt **unten**. Bei
    Heimspeichern ist das der Normalfall; die Oberseite deckt bereits
    `SOC_VOLL_PROZENT` ab (Balancing), und eine gewollte *Lade*-Grenze erkennt
    `speicher_sizing.SocNutzung.laedt_planmaessig_voll` an den Daten selbst.
    Sitzt die Reserve im Einzelfall doch oben, fällt die Schwelle zu hoch aus —
    die Kennzahl wird dann konservativer, nicht großzügiger, und bleibt damit auf
    der Seite, auf der eine Kaufentscheidung sie verträgt.

    Gibt den Rückfall `SOC_LEER_PROZENT` zurück, wenn nichts Genaueres bekannt
    ist: keine der beiden Kapazitäten gepflegt, unplausible Werte (≤ 0), oder
    ``nutzbar >= brutto`` (dann gibt es keine Reserve). **Wer nichts pflegt, sieht
    exakt das Verhalten von vorher** — das ist Abnahmekriterium, keine Nebenfolge.
    """
    if not kapazitaet_brutto_kwh or kapazitaet_brutto_kwh <= 0:
        return SOC_LEER_PROZENT
    if not nutzbare_kapazitaet_kwh or nutzbare_kapazitaet_kwh <= 0:
        return SOC_LEER_PROZENT
    if nutzbare_kapazitaet_kwh >= kapazitaet_brutto_kwh:
        return SOC_LEER_PROZENT

    abgeleitet = (1.0 - nutzbare_kapazitaet_kwh / kapazitaet_brutto_kwh) * 100.0
    if abgeleitet <= SOC_LEER_PROZENT:
        return SOC_LEER_PROZENT
    return min(abgeleitet + SOC_LEER_TOLERANZ_PP, SOC_LEER_MAX_PROZENT)


@dataclass(frozen=True)
class SpeicherStunde:
    """Eine Stundenzeile, so weit sie hier gebraucht wird.

    Alle Energiemengen in kWh, ``soc_prozent`` in Prozent. ``None`` heißt
    „nicht gemessen" und wird **nicht** als 0 gedeutet — eine Stunde ohne SoC
    kann weder „voll" noch „leer" belegen.
    """

    soc_prozent: Optional[float]
    einspeisung_kwh: float = 0.0
    netzbezug_kwh: float = 0.0


@dataclass
class ZyklusBefund:
    """Ein Überschuss-Ereignis und das, was die folgende Nacht daraus machte."""

    #: Einspeisung, während der Speicher voll war — die Obergrenze der Aufnahme.
    ueberschuss_kwh: float = 0.0
    #: Netzbezug, nachdem der Speicher leer war — der Bedarf, den er hätte decken können.
    fehlmenge_kwh: float = 0.0
    #: Wurde der Speicher vor dem nächsten Überschuss überhaupt leer?
    lief_leer: bool = False

    @property
    def nutzbar_kwh(self) -> float:
        """Was ein größerer Speicher hier **wirklich** durchgesetzt hätte."""
        return min(self.ueberschuss_kwh, self.fehlmenge_kwh)


@dataclass
class PotentialErgebnis:
    """Auswertung über einen Zeitraum."""

    #: Σ der gedeckelten Werte — die Zahl, die eine Kaufentscheidung tragen darf.
    nutzbares_zusatzpotential_kwh: float = 0.0
    #: Σ der Überschüsse — die naive Zahl aus dem Konzept, als Vergleich mitgeführt.
    ueberschuss_gesamt_kwh: float = 0.0
    #: Stunden, in denen der Speicher voll war (Diagnose, unabhängig vom Nutzen).
    stunden_voll: int = 0
    #: Zyklen, in denen der Speicher vor dem nächsten Überschuss leer lief.
    zyklen_leergelaufen: int = 0
    #: Zyklen mit Überschuss insgesamt.
    zyklen_gesamt: int = 0
    zyklen: list[ZyklusBefund] = field(default_factory=list)

    @property
    def deckelung_greift(self) -> bool:
        """True, wenn die ehrliche Zahl unter der naiven liegt.

        Das ist der Normalfall und der Grund für diese Datei — die Sicht muss
        es sagen können, statt zwei Zahlen kommentarlos nebeneinanderzustellen.
        """
        return self.nutzbares_zusatzpotential_kwh < self.ueberschuss_gesamt_kwh


def ist_voll(soc: Optional[float]) -> bool:
    """Zählt diese Stunde als „Speicher voll"? ``None`` belegt nichts.

    Öffentlich, weil die Monats-Aufschlüsselung (`speicher_potential_service`)
    denselben Schwellenbegriff braucht — ein zweiter Vergleich gegen
    `SOC_VOLL_PROZENT` daneben wäre dieselbe Regel an zwei Orten.
    """
    return soc is not None and soc >= SOC_VOLL_PROZENT


def ist_leer(soc: Optional[float], schwelle: Optional[float] = None) -> bool:
    """Gegenstück zu `ist_voll` — und aus demselben Grund öffentlich.

    ``schwelle`` ist die anlagenspezifische Untergrenze aus
    `leer_schwelle_prozent()`. Ohne Angabe gilt der Rückfall `SOC_LEER_PROZENT`;
    der Default steht hier, damit Bestandsaufrufer unverändert weiterlaufen —
    nicht, damit man ihn weglassen darf, wo die Kapazität bekannt ist (#379).
    """
    if soc is None:
        return False
    return soc <= (SOC_LEER_PROZENT if schwelle is None else schwelle)


def berechne_zusatzpotential(
    stunden: Sequence[SpeicherStunde] | Iterable[SpeicherStunde],
    leer_schwelle: Optional[float] = None,
) -> PotentialErgebnis:
    """Wertet eine **durchgehende** Stundenreihe aus (chronologisch, lückenlos).

    Der Ablauf folgt dem Gerät, nicht dem Kalender: Ein Zyklus beginnt, sobald
    der Speicher voll ist und trotzdem eingespeist wird, und endet mit dem
    nächsten solchen Ereignis. Dazwischen zählt der Netzbezug **ab dem Moment,
    in dem der Speicher leer ist** — vorher hätte auch ein größerer Speicher
    nichts beigetragen, weil der vorhandene noch lieferte.

    Bewusst über die Reihe statt je Kalendertag: die Nacht liegt über
    Mitternacht, und ein tagweiser Schnitt würde jede zweite Fehlmenge
    zerschneiden.

    ``leer_schwelle`` kommt aus `leer_schwelle_prozent()` und entscheidet, ab
    wann die Nacht als „aufgebraucht" zählt. Wird sie weggelassen, gilt der
    Rückfall — und für jeden Anwender mit eigener Entlade-Untergrenze ist das
    Ergebnis dann strukturell 0 (#379).
    """
    ergebnis = PotentialErgebnis()
    aktueller: Optional[ZyklusBefund] = None
    leer_erreicht = False
    vorige_war_ueberschuss = False

    for stunde in stunden:
        voll = ist_voll(stunde.soc_prozent)
        if voll:
            ergebnis.stunden_voll += 1

        einspeisung = stunde.einspeisung_kwh or 0.0
        if voll and einspeisung > 0:
            if not vorige_war_ueberschuss:
                # **Jede** Überschuss-Phase bekommt ihren eigenen Zyklus, nicht
                # erst die nach einem Leerlaufen: sonst sammelt ein Zyklus die
                # Überschüsse mehrerer Tage ein, und die eine Nacht, in der der
                # Speicher tatsächlich leer lief, rechtfertigt sie alle
                # rückwirkend — die Kennzahl fiele zu hoch aus, also genau in
                # die Richtung, gegen die diese Datei gebaut ist. (Der Test
                # `test_zwei_zyklen_werden_getrennt_bewertet` hat den Fehler
                # gefunden, bevor er ausgeliefert war.)
                aktueller = ZyklusBefund()
                ergebnis.zyklen.append(aktueller)
                ergebnis.zyklen_gesamt += 1
                leer_erreicht = False
            aktueller.ueberschuss_kwh += einspeisung
            vorige_war_ueberschuss = True
            continue

        vorige_war_ueberschuss = False

        if aktueller is None:
            # Vor dem ersten Überschuss gibt es nichts zu decken — ein leerer
            # Speicher am Anfang der Reihe belegt keine verpasste Ladung.
            continue

        if ist_leer(stunde.soc_prozent, leer_schwelle):
            if not leer_erreicht:
                leer_erreicht = True
                aktueller.lief_leer = True
                ergebnis.zyklen_leergelaufen += 1

        if leer_erreicht:
            aktueller.fehlmenge_kwh += stunde.netzbezug_kwh or 0.0

    ergebnis.ueberschuss_gesamt_kwh = sum(z.ueberschuss_kwh for z in ergebnis.zyklen)
    ergebnis.nutzbares_zusatzpotential_kwh = sum(z.nutzbar_kwh for z in ergebnis.zyklen)
    return ergebnis
